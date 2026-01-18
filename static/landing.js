const revealElements = document.querySelectorAll(".reveal");
const revealObserver = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add("is-visible");
        revealObserver.unobserve(entry.target);
      }
    });
  },
  { threshold: 0.2 }
);

revealElements.forEach((el) => revealObserver.observe(el));

const navLinks = document.querySelectorAll(".nav a[href^='#']");
const sectionTargets = Array.from(navLinks)
  .map((link) => document.querySelector(link.getAttribute("href")))
  .filter(Boolean);

const navObserver = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      navLinks.forEach((link) => {
        link.classList.toggle(
          "active",
          link.getAttribute("href") === `#${entry.target.id}`
        );
      });
    });
  },
  { rootMargin: "-40% 0px -50% 0px", threshold: 0.1 }
);

sectionTargets.forEach((section) => navObserver.observe(section));

navLinks.forEach((link) => {
  link.addEventListener("click", (event) => {
    const targetId = link.getAttribute("href");
    if (!targetId || targetId === "#") return;
    const target = document.querySelector(targetId);
    if (!target) return;
    event.preventDefault();
    target.scrollIntoView({ behavior: "smooth", block: "start" });
  });
});

document.querySelectorAll("[data-transition]").forEach((cta) => {
  cta.addEventListener("click", (event) => {
    if (event.metaKey || event.ctrlKey) return;
    event.preventDefault();
    document.body.classList.add("page-transition");
    setTimeout(() => {
      window.location.href = cta.getAttribute("href");
    }, 220);
  });
});

const prefersReducedMotion = window.matchMedia(
  "(prefers-reduced-motion: reduce)"
).matches;

if (!prefersReducedMotion && window.gsap) {
  gsap.registerPlugin(ScrollTrigger);
  const createdTriggers = [];

  document.querySelectorAll("[data-scroll-reveal]").forEach((element) => {
    if (!element.textContent || !element.textContent.trim()) return;

    const baseOpacity = Number(element.dataset.baseOpacity || 0.1);
    const baseRotation = Number(element.dataset.baseRotation || 3);
    const blurStrength = Number(element.dataset.blur || 4);
    const enableBlur = element.dataset.enableBlur !== "false";
    const rotationEnd = element.dataset.rotationEnd || "bottom bottom";
    const wordAnimationEnd = element.dataset.wordAnimationEnd || "bottom bottom";

    const fragment = document.createDocumentFragment();
    const originalNodes = Array.from(element.childNodes);
    element.textContent = "";
    originalNodes.forEach((node) => {
      if (node.nodeType === Node.TEXT_NODE) {
        const parts = node.textContent.split(/(\s+)/);
        parts.forEach((part) => {
          if (!part) return;
          if (/\s+/.test(part)) {
            fragment.appendChild(document.createTextNode(part));
          } else {
            const span = document.createElement("span");
            span.className = "word";
            span.textContent = part;
            fragment.appendChild(span);
          }
        });
      } else if (node.nodeName === "BR") {
        fragment.appendChild(document.createElement("br"));
      }
    });
    element.appendChild(fragment);

    const wordSpans = element.querySelectorAll(".word");
    gsap.set(wordSpans, {
      opacity: baseOpacity,
      filter: enableBlur ? `blur(${blurStrength}px)` : "none",
    });
    gsap.set(element, { rotate: 0 });

    const rotationTween = gsap.fromTo(
      element,
      { rotate: baseRotation },
      {
        rotate: 0,
        ease: "power2.out",
        immediateRender: false,
        scrollTrigger: {
          trigger: element,
          start: "top 85%",
          end: rotationEnd,
          scrub: true,
        },
      }
    );
    createdTriggers.push(rotationTween.scrollTrigger);

    const wordTween = gsap.to(wordSpans, {
      opacity: 1,
      filter: "blur(0px)",
      ease: "power2.out",
      stagger: 0.04,
      scrollTrigger: {
        trigger: element,
        start: "top 90%",
        end: wordAnimationEnd,
        scrub: true,
      },
    });
    createdTriggers.push(wordTween.scrollTrigger);

    window.addEventListener("beforeunload", () => {
      createdTriggers.forEach((trigger) => trigger && trigger.kill());
    });
  });
} else {
  document.querySelectorAll("[data-scroll-reveal]").forEach((element) => {
    element.style.opacity = 1;
    element.style.filter = "none";
    element.style.transform = "none";
  });
}

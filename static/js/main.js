document.addEventListener("DOMContentLoaded", () => {
  // Auto-dismiss flash messages after 4 seconds
  const flashes = document.querySelectorAll(".flash");
  flashes.forEach(flash => {
    setTimeout(() => {
      flash.style.opacity = "0";
      flash.style.transform = "translateX(20px)";
      flash.style.transition = "all 0.3s ease";
      setTimeout(() => flash.remove(), 300);
    }, 4000);
  });

  // Client-side net weight calculation for Production step
  const grossInput = document.getElementById("gross_weight_kg");
  const coreInput = document.getElementById("core_weight_kg");
  const netInput = document.getElementById("net_weight_kg");

  if (grossInput && coreInput && netInput) {
    const calculateNet = () => {
      const gross = parseFloat(grossInput.value) || 0;
      const core = parseFloat(coreInput.value) || 0;
      const net = gross - core;

      if (net > 0) {
        netInput.value = net.toFixed(3);
      } else {
        netInput.value = "";
      }
    };

    grossInput.addEventListener("input", calculateNet);
    coreInput.addEventListener("input", calculateNet);
  }

  // ── Mobile table scroll hint ──────────────────────────────────────────────
  // The CSS adds a right-edge fade on .table-wrap to signal horizontal scroll.
  // Remove it when the table actually fits, so non-scrolling tables look clean.
  const updateTableScrollHints = () => {
    document.querySelectorAll(".table-wrap").forEach(wrap => {
      const overflowing = wrap.scrollWidth > wrap.clientWidth + 1;
      wrap.classList.toggle("no-scroll", !overflowing);
    });
  };
  updateTableScrollHints();
  window.addEventListener("resize", updateTableScrollHints);
});
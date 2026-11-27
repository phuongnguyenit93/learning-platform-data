# The Metal Pipeline on macOS and Testing Java 2D in Java 17

## 1. What Is the Metal Pipeline?

Java 2D is Java's graphics platform, providing APIs to draw geometry, images, text, and color effects. Swing and AWT rely on Java 2D to render user interfaces and content onto the screen.

On macOS, Java 2D can use a **rendering pipeline** to translate Java drawing commands into native graphics operations. Starting in Java 17, HotSpot/JDK introduced a pipeline powered by **Apple Metal**, delivered via JEP 382 (*New macOS Rendering Pipeline*). This pipeline offers a modern alternative to the legacy OpenGL pipeline.

Metal is Apple's low-level graphics API designed to leverage the GPU and OS graphics capabilities. Java 2D preserves the exact same Java APIs—such as `Graphics2D`, `BufferedImage`, `VolatileImage`, `JComponent`, and `paintComponent()`. Selecting Metal changes Java 2D's internal backend implementation without requiring rewrites of Swing or AWT code.

In Java 17, Metal is **available but disabled by default**. Applications must opt into the pipeline via a system property:

~~~text
-Dsun.java2d.metal=true
~~~

The Metal pipeline requires macOS 10.14.x or later. On older macOS releases, requests to enable Metal are ignored. Oracle confirms that Metal is supported in JDK 17 and JDK 18, and only becomes the default pipeline starting in JDK 19.

An important point when reading Java 2D documentation: **Java 17 and Java 19+ have different defaults**. When running specifically on JDK 17, never assume Metal is active just because the runtime supports it.

## 2. Metal, OpenGL, and JDK Versions

### 2.1. Pipeline Status by Version

| Runtime | Metal | OpenGL on macOS |
|---|---|---|
| JDK 17 | Supported, disabled by default; enable with `-Dsun.java2d.metal=true`. | Default pipeline in standard JDK 17 builds. |
| JDK 18 | Supported, disabled by default. | Still the standard default pipeline. |
| JDK 19 and later | Metal is enabled by default. | No longer the default pipeline. |

Apple has marked OpenGL as a deprecated API. However, in JDK 17, OpenGL remains the default rendering path for compatibility. When testing Java 17 applications, you can use it as a baseline for comparison against Metal; for new projects, prioritize testing Metal and plan JDK upgrades when appropriate.

### 2.2. Selecting the Pipeline via System Property

On JDK 17, enable Metal:

~~~text
java -Dsun.java2d.metal=true -jar app.jar
~~~

Disable the Metal request to fall back to JDK 17's default pipeline:

~~~text
java -Dsun.java2d.metal=false -jar app.jar
~~~

You can request OpenGL explicitly when you need a baseline test run:

~~~text
java -Dsun.java2d.opengl=true -jar app.jar
~~~

The `sun.java2d.metal` and `sun.java2d.opengl` properties are internal JDK implementation options, not Java SE APIs guaranteed across every vendor or build. Set them on the command line when launching the JVM. Do not wait until Swing components are created or AWT initializes to call `System.setProperty()`; by then Java 2D may have already selected its pipeline.

### 2.3. Do Not Confuse Java 2D Metal with JavaFX Metal

JEP 382 applies to the JDK's Java 2D pipeline used by Swing and AWT. JavaFX has its own rendering system (Prism) and separate pipeline options. Enabling `-Dsun.java2d.metal=true` does not switch JavaFX to Metal.

If an application mixes Swing and JavaFX, test both graphics stacks according to their respective runtimes and documentation. Never use a JavaFX test result to conclude that the Java 2D pipeline is active.

## 3. Which Areas Does the Java 2D Pipeline Affect?

Java 2D exposes a unified graphics API, while the pipeline determines how primitives execute on the specific platform. Common operations include:

- Drawing lines, rectangles, ellipses, paths, and polygons.
- Fills, gradients, strokes, and clipping.
- Alpha compositing and transparency.
- Image drawing, scaling, rotation, and transforms.
- Glyph and text rendering.
- Rendering to windows, back buffers, or potentially accelerated offscreen surfaces.

For example, the code below does not need to know whether the machine uses Metal or OpenGL:

~~~java
void drawScene(Graphics2D g) {
    g.setColor(Color.BLUE);
    g.fillRoundRect(20, 20, 180, 90, 18, 18);
    g.setColor(Color.WHITE);
    g.drawString("Java 2D", 55, 72);
}
~~~

On macOS with JDK 17, the active pipeline handles applicable operations. Some operations may be GPU-accelerated, while others fall through software paths. Using Metal does not mean every `Graphics2D` call runs on the GPU.

### 3.1. Important Rendering Surfaces

| Target Surface | Testing Characteristics |
|---|---|
| On-screen Swing/AWT windows | Most critical for confirming desktop applications work with the actual display pipeline. |
| `VolatileImage` | Can reside on an accelerated surface; suitable for testing potentially accelerated offscreen paths. |
| `BufferStrategy` back buffer | Suitable for continuous drawing, animations, or AWT-based games. |
| `BufferedImage` | Image in Java memory; normally uses software rendering paths, ideal for pixel verification and image processing. |

**Rendering solely to a `BufferedImage` is not enough to prove Metal is being used.** Oracle notes that rendering into a `BufferedImage` almost always goes through software loops. To test the display pipeline, open a real window and render onto the screen; supplement with `VolatileImage` or `BufferStrategy` if the application uses them.

## 4. Prerequisites Before Testing Metal

Before enabling Metal, verify the environment:

1. The machine runs macOS 10.14.x or later.
2. The actual JVM is JDK 17, not another JRE/JDK silently chosen by an IDE or launcher.
3. The JDK build matches the machine's CPU architecture and macOS version.
4. The machine has an active desktop graphics session and Metal-capable hardware.
5. The application runs in a session with a display; do not run window tests in a headless environment.
6. Any native libraries or desktop frameworks used by the app are compatible with the active JDK.

Verify the runtime:

~~~text
java -version
java -XshowSettings:properties -version
~~~

When confirming the exact executable in use:

~~~text
which java
which javac
~~~

On macOS, inspect the architecture and OS version:

~~~text
sw_vers
uname -m
~~~

If using an IDE, check Project SDK, Gradle/Maven JVM, and Run Configuration JVM options. An IDE might compile with one JDK yet launch the application with another.

### 4.1. Checking Headless Mode

Java 2D can still create and manipulate `BufferedImage` instances in headless mode, but that cannot test the on-screen window pipeline.

You can print the status:

~~~java
System.out.println(
        "Headless: " + java.awt.GraphicsEnvironment.isHeadless());
~~~

If the output is `true`, move UI tests to a macOS host with a desktop session. Never pass `-Djava.awt.headless=true` for Metal pipeline tests.

## 5. Enabling Metal in a Java 17 Application

### 5.1. Running a JAR from the Terminal

~~~text
java -Dsun.java2d.metal=true -jar desktop-app.jar
~~~

If running a class directly:

~~~text
java -Dsun.java2d.metal=true -cp out com.example.DesktopApp
~~~

If the application has external dependencies:

~~~text
java -Dsun.java2d.metal=true -cp "out:lib/*" com.example.DesktopApp
~~~

On macOS, multi-entry classpaths use `:`. Substitute class names, directories, and JARs for your actual project.

### 5.2. Configuring in an IDE

In the Run/Debug Configuration, add the JVM option:

~~~text
-Dsun.java2d.metal=true
~~~

This is a VM option, not a program argument. Placing it in program arguments passes it to the application as a CLI string, and the JVM will not enable the pipeline.

### 5.3. Configuring via Gradle

For a `JavaExec` task, you can pass the JVM argument in the task configuration:

~~~kotlin
tasks.register<JavaExec>("runWithMetal") {
    classpath = sourceSets["main"].runtimeClasspath
    mainClass.set("com.example.DesktopApp")
    jvmArgs("-Dsun.java2d.metal=true")
}
~~~

Task and main class names are illustrative. If using Kotlin DSL, place the configuration in your project's build script; for Maven or IDEs, configure VM options in the corresponding launcher.

### 5.4. Setting the Property Before AWT Initialization

Do not set the property inside `paintComponent()` or after creating a `JFrame`:

~~~java
// Do not use this to switch pipelines after the GUI has initialized.
System.setProperty("sun.java2d.metal", "true");
~~~

Pass the property when starting the JVM. This ensures pipeline selection happens from the start and keeps test runs reproducible.

## 6. Creating a Java 2D Smoke Test

A useful smoke test should draw a variety of primitives commonly used in real applications:

- Backgrounds and basic geometry.
- Text in different fonts.
- Gradients and alpha compositing.
- Antialiasing.
- Transforms, clipping, and strokes.
- Raster images with transparency.
- Repaints, resizing, and window state changes.

The example below creates a Swing window and draws directly onto the visible display surface. It checks whether the application starts, repaints, and displays content cleanly when running with Metal.

Create `Java2DMetalSmokeTest.java`:

~~~java
import java.awt.AlphaComposite;
import java.awt.BasicStroke;
import java.awt.Color;
import java.awt.Font;
import java.awt.Graphics;
import java.awt.Graphics2D;
import java.awt.RenderingHints;
import java.awt.geom.AffineTransform;
import java.awt.geom.Ellipse2D;
import java.awt.geom.RoundRectangle2D;
import java.awt.image.BufferedImage;
import javax.swing.JFrame;
import javax.swing.JPanel;
import javax.swing.SwingUtilities;

public final class Java2DMetalSmokeTest {
    private Java2DMetalSmokeTest() {
    }

    private static final class DemoPanel extends JPanel {
        private final BufferedImage tile = createTile();

        DemoPanel() {
            setBackground(new Color(28, 32, 42));
        }

        @Override
        protected void paintComponent(Graphics graphics) {
            super.paintComponent(graphics);

            Graphics2D g = (Graphics2D) graphics.create();
            try {
                g.setRenderingHint(
                        RenderingHints.KEY_ANTIALIASING,
                        RenderingHints.VALUE_ANTIALIAS_ON);
                g.setRenderingHint(
                        RenderingHints.KEY_TEXT_ANTIALIASING,
                        RenderingHints.VALUE_TEXT_ANTIALIAS_ON);
                g.setRenderingHint(
                        RenderingHints.KEY_RENDERING,
                        RenderingHints.VALUE_RENDER_QUALITY);

                int width = getWidth();
                int height = getHeight();

                g.setPaint(new java.awt.GradientPaint(
                        0, 0, new Color(40, 90, 160),
                        width, height, new Color(24, 28, 48)));
                g.fillRect(0, 0, width, height);

                g.setColor(new Color(255, 255, 255, 210));
                g.setFont(new Font(Font.SANS_SERIF, Font.BOLD, 28));
                g.drawString("Java 2D / Metal pipeline smoke test", 28, 52);

                g.setPaint(new java.awt.GradientPaint(
                        40, 90, new Color(40, 190, 180),
                        260, 220, new Color(70, 90, 220)));
                g.fill(new RoundRectangle2D.Double(
                        40, 90, 220, 130, 24, 24));

                g.setComposite(AlphaComposite.getInstance(
                        AlphaComposite.SRC_OVER, 0.55f));
                g.setColor(new Color(255, 120, 60));
                g.fill(new Ellipse2D.Double(160, 135, 150, 120));
                g.setComposite(AlphaComposite.SrcOver);

                g.setColor(new Color(255, 255, 255, 220));
                g.setStroke(new BasicStroke(
                        4.0f, BasicStroke.CAP_ROUND,
                        BasicStroke.JOIN_ROUND));
                g.drawRoundRect(330, 100, 220, 110, 22, 22);

                AffineTransform old = g.getTransform();
                g.rotate(Math.toRadians(-8), 660, 165);
                g.setColor(new Color(250, 220, 90));
                g.fillRoundRect(590, 115, 150, 90, 18, 18);
                g.setTransform(old);

                g.drawImage(tile, 40, 270, 220, 150, null);
                g.setColor(Color.WHITE);
                g.setFont(new Font(Font.MONOSPACED, Font.PLAIN, 16));
                g.drawString("resize / repaint / alpha / transform", 290, 315);

                g.setClip(290, 340, 380, 100);
                g.setColor(new Color(120, 220, 150));
                for (int i = 0; i < 20; i++) {
                    g.drawLine(290, 340 + i * 7, 760, 440 - i * 5);
                }
            } finally {
                g.dispose();
            }
        }

        private static BufferedImage createTile() {
            BufferedImage image = new BufferedImage(
                    320, 200, BufferedImage.TYPE_INT_ARGB);
            Graphics2D g = image.createGraphics();
            try {
                g.setColor(new Color(255, 255, 255, 0));
                g.fillRect(0, 0, image.getWidth(), image.getHeight());
                g.setColor(new Color(245, 245, 250, 220));
                g.fillRoundRect(10, 10, 300, 180, 26, 26);
                g.setColor(new Color(30, 60, 100));
                g.setFont(new Font(Font.SANS_SERIF, Font.BOLD, 24));
                g.drawString("BufferedImage source", 28, 105);
            } finally {
                g.dispose();
            }
            return image;
        }
    }

    public static void main(String[] args) {
        System.out.println("Java: " + System.getProperty("java.version"));
        System.out.println("OS: " + System.getProperty("os.name"));
        System.out.println("Metal requested: "
                + System.getProperty("sun.java2d.metal", "(default)"));

        SwingUtilities.invokeLater(() -> {
            JFrame frame = new JFrame("Java 2D Metal Smoke Test");
            frame.setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);
            frame.setContentPane(new DemoPanel());
            frame.setSize(820, 520);
            frame.setLocationByPlatform(true);
            frame.setVisible(true);
        });
    }
}
~~~

Compile and run:

~~~text
javac --release 17 -encoding UTF-8 Java2DMetalSmokeTest.java
java -Dsun.java2d.metal=true Java2DMetalSmokeTest
~~~

When the window appears, resize it, switch between windows, minimize/restore, and observe the rendering. Check that there are no missing paint regions, abnormal flickering, incorrect alpha blending, corrupted text, or crashes.

`BufferedImage` in the example is only an image source. Primary drawing is performed on the visible `JPanel` on screen, allowing the test to exercise macOS's Java 2D pipeline.

## 7. Testing VolatileImage and Accelerated Surfaces

Some applications render offscreen first and copy onto the screen. `VolatileImage` is an image type that can reside on an accelerated surface whose contents may be lost when the system changes graphics state.

You can inspect surface acceleration capabilities once a visible component exists:

~~~java
import java.awt.Graphics2D;
import java.awt.GraphicsConfiguration;
import java.awt.Transparency;
import java.awt.image.VolatileImage;

static void inspectVolatileSurface(
        GraphicsConfiguration configuration) {

    VolatileImage image =
            configuration.createCompatibleVolatileImage(
                    640, 360, Transparency.TRANSLUCENT);

    try {
        int validation = image.validate(configuration);

        Graphics2D g = image.createGraphics();
        try {
            g.fillRect(0, 0, 640, 360);
            g.drawString("Offscreen Java 2D", 24, 40);
        } finally {
            g.dispose();
        }

        System.out.println("Validation result: " + validation);
        System.out.println("Accelerated: "
                + image.getCapabilities().isAccelerated());
        System.out.println("Contents lost: " + image.contentsLost());
    } finally {
        image.flush();
    }
}
~~~

Call this method after a component is visible and has a `GraphicsConfiguration`, such as via `component.getGraphicsConfiguration()`.

`ImageCapabilities.isAccelerated()` reports whether the surface is accelerated according to the implementation. It **does not specifically confirm that Metal is the active backend**; a surface could be accelerated by another pipeline or remain unaccelerated depending on runtime and hardware.

### 7.1. Handling VolatileImage Content Loss

A `VolatileImage` can lose its contents when display modes, surfaces, or graphics resources change. Applications must check `contentsLost()` and redraw if needed.

General handling pattern:

~~~java
do {
    int state = image.validate(configuration);

    if (state == VolatileImage.IMAGE_INCOMPATIBLE) {
        image.flush();
        image = configuration.createCompatibleVolatileImage(
                width, height, Transparency.TRANSLUCENT);
    }

    if (state == VolatileImage.IMAGE_RESTORED
            || state == VolatileImage.IMAGE_INCOMPATIBLE) {
        // Redraw all content into the image.
    }

    // If IMAGE_OK, the current content can be used.
} while (image.contentsLost());
~~~

In production code, manage image recreation, ownership, and synchronization with the component lifecycle. Never assume `VolatileImage` retains contents permanently.

## 8. Visual Testing: Functionality and Pipeline Are Two Different Goals

A Java 2D test suite should separate at least two test categories:

### 8.1. Functional Testing with BufferedImage

Use `BufferedImage` when you want deterministic pixel verification:

- Background colors, dimensions, and shape positions.
- Alpha compositing with predictable values.
- Image cropping, scaling, and transforms.
- Clipping and paint bounds.
- Generated image content.

Example:

~~~java
BufferedImage image = new BufferedImage(
        200, 120, BufferedImage.TYPE_INT_ARGB);

Graphics2D g = image.createGraphics();
try {
    g.setColor(Color.RED);
    g.fillRect(10, 10, 50, 40);
} finally {
    g.dispose();
}

int pixel = image.getRGB(20, 20);
if (pixel != Color.RED.getRGB()) {
    throw new AssertionError("Unexpected pixel color");
}
~~~

This tests drawing logic and color output. It does not prove Metal was initialized because `BufferedImage` typically uses software rendering.

### 8.2. UI Integration Testing on macOS

To verify Metal:

1. Launch the JVM with `-Dsun.java2d.metal=true`.
2. Create a real Swing/AWT window.
3. Render content onto a visible component.
4. Exercise repaints, resizing, minimize/restore, and user interactions.
5. Capture screenshots using `java.awt.Robot` or UI test tooling.
6. Compare against an appropriate baseline and inspect logs/diagnostics on issues.

These tests must run on macOS with a desktop session and the proper JDK 17. A Linux CI runner or headless test cannot verify Metal on macOS.

### 8.3. Visual Regression Testing

Screenshots from Metal and OpenGL may differ slightly due to:

- Glyph rasterization and antialiasing differences.
- Subpixel coordinate rounding.
- Display color profiles and color management.
- HiDPI scaling and backing scale factors.
- Driver/hardware differences or macOS updates.

Therefore, do not compare screenshots byte-for-byte by default. Use color-difference thresholds, maximum differing region tolerances, geometry/edge checks, and targeted assertions for critical content. Text and gradient regions typically require higher tolerance than solid flat regions.

## 9. Checking the Pipeline and Primitive Tracing

### 9.1. Logging Runtime Configuration

Inside your program, you can print:

~~~java
System.out.println("java.version="
        + System.getProperty("java.version"));
System.out.println("os.name="
        + System.getProperty("os.name"));
System.out.println("sun.java2d.metal="
        + System.getProperty("sun.java2d.metal"));
System.out.println("sun.java2d.opengl="
        + System.getProperty("sun.java2d.opengl"));
~~~

Property values reflect the requested configuration or read value, not a definitive runtime confirmation of the active backend. If Metal fails to initialize, the implementation may fall back to another path. Cross-check with runtime/build info, diagnostic logs, and on-screen results.

Java SE does not provide a public, portable API to directly query "is the Metal pipeline rendering this frame?". Do not treat `GraphicsEnvironment`, `GraphicsConfiguration`, or a single property string as absolute proof.

### 9.2. Primitive Tracing

Java 2D can count executed drawing primitives:

~~~text
java -Dsun.java2d.metal=true -Dsun.java2d.trace=count Java2DMetalSmokeTest
~~~

When the JVM exits, primitive tracing prints the list of primitives and call counts to the console. It can help spot operations executing via software loops. For instance, primitives like `MaskBlit` or `General*` often indicate part of an operation went through software paths.

Primitive tracing is a diagnostic tool for **primitive execution paths**, not standalone proof that the Metal pipeline was selected. Even an accelerated pipeline can use software fallbacks for operations unsupported or unaccelerated by the backend.

### 9.3. Do Not Use OpenGL Diagnostics as Proof for Metal

Some Java 2D documentation describes `J2D_TRACE_LEVEL` for observing OpenGL initialization on Linux/Windows. Do not generalize that every message from that environment variable serves as official diagnostics for Metal across all JDK 17 builds.

When diagnosing a Metal initialization failure, collect startup logs for your exact JDK build, macOS version, machine architecture, and JVM options, and construct a minimal reproducer. Include full environment details and reproduction steps in any bug reports.

## 10. Comparing Metal Against the Baseline on JDK 17

To evaluate Metal's impact, run the exact same application and workload under both configurations:

~~~text
# Run A: request Metal
java -Dsun.java2d.metal=true -jar app.jar

# Run B: do not request Metal; JDK 17 uses default pipeline
java -Dsun.java2d.metal=false -jar app.jar
~~~

On standard JDK 17 builds, Run B uses OpenGL as the baseline. If you want to request OpenGL explicitly:

~~~text
java -Dsun.java2d.opengl=true -jar app.jar
~~~

Do not compare a Metal run on a newer machine against an OpenGL run on a different machine and attribute the entire difference to the pipeline. Keep environments as identical as possible.

### 10.1. Metrics to Measure

| Metric | How to Observe |
|---|---|
| UI startup time | Measure from launch until the window displays and becomes interactive. |
| Frame render time | Measure time to generate and display a frame under a realistic workload. |
| Interaction smoothness | Observe animations, scrolling, resizing, dragging, and window switching. |
| CPU usage | Monitor process CPU utilization under identical workloads. |
| GPU/energy | Use macOS system tools to observe GPU and energy usage. |
| Visual quality | Compare screenshots, text, alpha blending, clipping, transforms, and colors. |
| Stability | Watch for crashes, visual artifacts, missed repaints, and sleep/wake issues. |

Metal is designed around a modern graphics API and can improve performance or energy efficiency on capable hardware. However, actual outcomes depend on workload, hardware, and drivers. Never assume Metal is faster for every drawing operation.

### 10.2. Controlled Benchmarking

For meaningful results:

1. Use the exact same JDK vendor/build and application.
2. Use the same Mac, display, resolution, and scale factor.
3. Use identical data, window size, and interaction sequence.
4. Perform warm-up runs before recording metrics.
5. Run multiple iterations and compare median, p95, or frame-time distributions.
6. Separate startup time from steady-state rendering time.
7. Avoid logging or file I/O inside the measured render loop.
8. Measure CPU, GPU/energy, and visual quality—not just FPS.

Do not wrap `System.nanoTime()` around a single `drawString()` call and draw conclusions about GPU speed. Java 2D may buffer or defer work until synchronization/flush time; benchmarks must reflect a full rendering cycle.

### 10.3. Avoid Skewed Benchmarks on the Event Dispatch Thread

Swing handles events and repaints on the Event Dispatch Thread (EDT). Running long computations or `Thread.sleep()` inside `paintComponent()` freezes the UI and invalidates benchmark measurements.

Keep `paintComponent()` focused strictly on painting current state. Perform heavy computations on worker threads, update the model safely, and request repaints. When benchmarking animations, use an appropriate scheduler to advance state and measure frame times without blocking the EDT.

## 11. Operations to Include in Java 2D Test Suites

Real desktop applications do more than draw plain rectangles. Build a test suite covering these groups:

| Group | Sample Operations | What to Observe |
|---|---|---|
| Geometry | `drawLine`, `fillRect`, `draw(Shape)`, `fill(Shape)` | Position, dimensions, strokes, and clipping. |
| Antialiasing | Diagonal lines, ellipses, curved paths | Edges free of unexpected jaggedness. |
| Alpha | `AlphaComposite.SrcOver`, RGBA images | Color blending and transparent regions. |
| Gradient | `GradientPaint`, `LinearGradientPaint` | Smooth color transitions without banding or reversed direction. |
| Transform | Scale, rotate, translate, shear | Accurate coordinates and transform origins. |
| Text | Regular, bold, italic fonts, Unicode glyphs | No missing glyphs or erratic baseline shifts. |
| Image | PNG/JPEG, large images, transparent images | Colors, scaling, clipping, and content updates. |
| Clip | `setClip`, `clip` | No drawing bleeding outside clip bounds. |
| Buffering | `VolatileImage`, `BufferStrategy` | No content loss or flickering. |
| Window lifecycle | Resize, minimize, restore, move across displays | Surfaces recreated and repainted completely. |

### 11.1. HiDPI and Retina

On Retina displays, logical component dimensions and physical pixels can differ. Test across multiple scale factors if the product supports multi-monitor setups:

- Text remains crisp and readable at expected UI sizes.
- Hairline strokes do not disappear when scaled.
- Icons and images do not blur unexpectedly.
- Popups, tooltips, and child windows appear at the right coordinates.
- Dragging windows between displays with different scale factors does not corrupt the surface.

Never hardcode the assumption that one logical pixel equals one physical pixel. Use Java AWT/Swing display and layout APIs properly.

### 11.2. Fonts and Text

Text rendering can differ subtly across pipelines, OS versions, and fonts. Test:

- System fonts and application-bundled fonts.
- Vietnamese diacritics and required Unicode glyphs.
- Small, large, bold, and italic sizes.
- Text over light, dark, and transparent backgrounds.
- Scaled or transformed text if used by the application.

If screenshots vary slightly along glyph edges, evaluate using an appropriate tolerance. Missing glyphs, garbled characters, or visibly shifted baselines are bugs to investigate.

## 12. Troubleshooting When Enabling Metal

### 12.1. Property Enabled but No Observed Difference

Possible causes:

- The active JVM is not the expected JDK 17.
- The property was passed as a program argument by mistake.
- The property was set after AWT initialized.
- macOS is older than 10.14.
- The JDK build or hardware does not support the pipeline in the current configuration.
- The workload primarily renders into `BufferedImage` instead of accelerated on-screen surfaces.

How to resolve:

1. Print `java.version`, `os.name`, and properties at startup.
2. Verify IDE/launcher VM options.
3. Run a smoke test with a visible window.
4. Exercise `VolatileImage` or `BufferStrategy` if the app uses offscreen accelerated surfaces.
5. Collect runtime logs and re-test on a supported JDK build and macOS version.

### 12.2. Visual Artifacts or Crashes

If encountering corrupt paint areas, flicker, crashes, or errors when switching displays:

1. Build a minimal Swing/Java 2D reproducer.
2. Record JDK vendor, full version, CPU architecture, and macOS version.
3. Record JVM options, especially `sun.java2d.metal`.
4. Identify the triggering operation: alpha, transform, text, resize, sleep/wake, or multi-monitor.
5. Compare the exact same operation without requesting Metal to isolate the issue.
6. Collect logs, screenshots, and reproduction steps before filing a report.

Do not disable Metal across an entire product based on a single unreproduced artifact. Isolate the exact triggering operation and environment.

### 12.3. Lower Performance Than Expected

Metal does not guarantee every drawing operation is accelerated. If performance is low:

- Check whether the destination surface supports acceleration.
- Avoid repeatedly reading pixels back from accelerated surfaces unnecessarily.
- Avoid allocating new objects, fonts, or images on every repaint.
- Cache immutable images and resources appropriately.
- Profile commonly used primitives in the application.
- Use primitive tracing to spot software fallback paths.
- Compare using representative workloads rather than synthetic micro-demos alone.

Some operations may fall back to software paths while still producing correct output. The goal is identifying actual bottlenecks before altering rendering code.

## 13. Limitations and What Not to Infer

- The Metal pipeline is an internal Java 2D implementation detail; applications do not invoke Metal APIs directly through `Graphics2D`.
- Enabling the property only requests pipeline selection; do not treat the property value as proof that the pipeline initialized successfully.
- Some primitives may still fall back to software even when Metal is active.
- `BufferedImage` is useful for pixel tests but cannot prove hardware acceleration.
- `VolatileImage.isAccelerated()` reports surface acceleration capability, not specifically the Metal backend.
- Screenshots may differ subtly due to fonts, HiDPI, color profiles, and rasterization.
- JDK 17 defaults differ from JDK 19+; always specify the runtime when comparing.
- JavaFX has its own pipeline; Java 2D properties do not control Prism.
- Switching graphics pipelines does not change Java API semantics, though it can expose rasterization differences or native/driver bugs.

## 14. Practical Testing Checklist on macOS

### Before Running

- [ ] Confirm JDK 17 and exact build version.
- [ ] Confirm macOS 10.14 or later.
- [ ] Confirm the app runs in a desktop session, not headless.
- [ ] Pass `-Dsun.java2d.metal=true` in VM options.
- [ ] Record machine architecture and display details.

### During Execution

- [ ] Window opens and repaints normally.
- [ ] Geometry, text, images, alpha, and transforms render accurately.
- [ ] Resizing, minimizing/restoring, and switching windows produce no artifacts.
- [ ] Retina/multi-monitor setups work if supported by the product.
- [ ] `VolatileImage`/`BufferStrategy` paths work if used by the application.
- [ ] Logs and screenshots are captured if errors occur.

### When Comparing

- [ ] Use identical JDK, machine, data, and interactions.
- [ ] Perform warm-ups and multiple measurement runs.
- [ ] Compare median/p95 rather than a single sample.
- [ ] Measure CPU, frame time, stability, and visual quality.
- [ ] Use reasonable tolerances for pixels and text.
- [ ] Do not treat primitive tracing or property values as sole confirmation of Metal.

## 15. Practice Exercises

### Exercise 1 — Enable Metal on JDK 17

Run `Java2DMetalSmokeTest` with `-Dsun.java2d.metal=true`. Print `java.version`, `os.name`, and the property value. Capture the window after resizing and switching between windows.

### Exercise 2 — Compare Against the Default Pipeline

Run the same program with `-Dsun.java2d.metal=true` and `-Dsun.java2d.metal=false`. Compare visuals, text, repaints, and smoothness. Note explicitly that standard JDK 17 uses OpenGL as the baseline when Metal is disabled.

### Exercise 3 — Compare BufferedImage and VolatileImage

Draw the same shape onto a `BufferedImage` and a `VolatileImage`. Check pixel snapshots, `isAccelerated()`, and `contentsLost()`. Explain why these two surfaces do not validate the same rendering path.

### Exercise 4 — Test Alpha and Transforms

Create overlapping shapes with varying alpha values, rotations, scaling, and clipping. Compare screenshots on Metal and baseline. Distinguish meaningful visual defects from acceptable rasterization tolerance differences.

### Exercise 5 — Test HiDPI

Run the application on a Retina display and, if available, an external display with a different scale factor. Drag the window back and forth and inspect text, icons, popups, geometry, and repaints.

### Exercise 6 — Primitive Tracing

Run with `-Dsun.java2d.trace=count`. Record the invoked primitives and identify any indicating software loops. Explain why this reports primitive execution rather than direct proof of the Metal pipeline.

### Exercise 7 — Benchmark a Real Workload

Choose an actual screen or rendering flow in your application. Measure frame times and CPU after warm-up across multiple runs on the same machine. Compare Metal against baseline results, and state the limitations of your measurements.

## 16. Key Principles to Remember

- JEP 382 introduced the Metal pipeline to Java 2D on macOS in JDK 17.
- On JDK 17, Metal is disabled by default; enable it with `-Dsun.java2d.metal=true`.
- Metal requires macOS 10.14.x or later; verify your actual JDK build and hardware.
- Metal became the default macOS pipeline in JDK 19; do not assume that default applies retroactively to JDK 17.
- Swing/AWT Java 2D APIs remain unchanged across pipelines.
- `BufferedImage` is suited for pixel tests but typically uses software rendering; testing Metal requires rendering to visible windows and optionally `VolatileImage`/`BufferStrategy`.
- `VolatileImage.isAccelerated()` indicates surface acceleration, not specifically the Metal backend.
- `-Dsun.java2d.trace=count` helps reveal software primitives; it is not standalone confirmation of the active pipeline.
- Test visuals, repaints, resizing, HiDPI, multi-monitor setups, stability, and performance.
- Compare pipelines on the same runtime, hardware, data, and workload; measure across multiple runs with reasonable tolerances.
- JavaFX has its own pipeline and is not controlled by Java 2D properties.
- `sun.java2d.metal` is an internal implementation property; set it at startup and verify on the target JDK/macOS environment.

### References

- [JDK 17 Release Notes — JEP 382: New macOS Rendering Pipeline](https://www.oracle.com/java/technologies/javase/17-relnote-issues.html).
- [JEP 382 — New macOS Rendering Pipeline](https://openjdk.org/jeps/382).
- [Oracle Java 17 Troubleshooting Guide — Java 2D](https://docs.oracle.com/en/java/javase/17/troubleshoot/java-2d.html).
- [Oracle Java 17 Troubleshooting Guide — Java 2D Properties](https://docs.oracle.com/en/java/javase/17/troubleshoot/java-2d-properties.html).
- [Oracle Java 17 Troubleshooting Guide — Java 2D Pipeline Rendering](https://docs.oracle.com/en/java/javase/17/troubleshoot/java-2d-pipeline-rendering-selection-and-properties.html).
- [JDK 19 Release Notes — Metal Is Now the Default Java 2D Rendering Pipeline on macOS](https://www.oracle.com/java/technologies/javase/19-relnote-issues.html).

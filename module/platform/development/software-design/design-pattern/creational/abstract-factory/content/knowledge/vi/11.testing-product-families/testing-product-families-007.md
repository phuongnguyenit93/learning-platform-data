# Kiểm thử chọn biến thể, cấu hình sai và sản phẩm không được hỗ trợ

> **Chương:** Kiểm thử  
> **Module:** `SOFTWARE_DESIGN_DESIGN_PATTERN_CREATIONAL_ABSTRACT_FACTORY` — Học về Abstract Factory trong Design Pattern.  
> **Mục tiêu:** Thiết kế và thực hiện kiểm thử cho việc chọn họ sản phẩm theo cấu hình, phân biệt các dạng cấu hình không hợp lệ, xác minh hành vi khi một biến thể hoặc một sản phẩm không được hỗ trợ, và bảo đảm một `ConcreteFactory` không tạo lẫn sản phẩm từ nhiều họ.

## 1. Vì sao chọn đúng factory chưa đủ để kết luận hệ thống đúng?

Giả sử ứng dụng tạo giao diện theo nền tảng Windows hoặc macOS. Mỗi màn hình cần hai thành phần bắt buộc:

- `Button` để kích hoạt thao tác.
- `Checkbox` để bật/tắt lựa chọn.

Ứng dụng dùng một `UiFactory`:

~~~java
interface UiFactory {
    Button createButton();
    Checkbox createCheckbox();
}
~~~

Khi chọn Windows, hệ thống phải dùng `WindowsFactory` và nhận **cả** `WindowsButton` lẫn `WindowsCheckbox`; khi chọn macOS, phải dùng cả hai sản phẩm macOS. Một lỗi như sau vẫn có thể biên dịch:

~~~java
// Sai về họ, mặc dù đúng kiểu Checkbox.
final class WindowsFactory implements UiFactory {
    public Button createButton() {
        return new WindowsButton();
    }

    public Checkbox createCheckbox() {
        return new MacCheckbox();
    }
}
~~~

Trình biên dịch biết `MacCheckbox` là một `Checkbox`, nhưng **không tự chứng minh rằng nó cùng họ với `WindowsButton`**. Ngoài ra, factory có thể được triển khai đúng mà điểm chọn biến thể lại đọc cấu hình sai, rơi vào nhánh mặc định không mong muốn hoặc chọn một biến thể chưa đăng ký.

Vì thế, một chiến lược kiểm thử tốt cần trả lời **ba câu hỏi độc lập**:

1. **Chọn biến thể:** Cấu hình hợp lệ có trỏ đến factory đúng không?
2. **Xử lý lỗi cấu hình:** Các đầu vào thiếu, rỗng, không nhận diện được hoặc chưa hỗ trợ có được xử lý theo chính sách rõ ràng không?
3. **Hỗ trợ sản phẩm:** Factory có tạo đủ những sản phẩm bắt buộc và từ chối minh bạch sản phẩm tùy chọn chưa hỗ trợ không?

Mỗi câu hỏi cần điều kiện kiểm thử và thông báo lỗi phù hợp, thay vì chỉ kiểm tra rằng màn hình “không bị crash”.

## 2. Nhận diện ba mức hỗ trợ khác nhau

Trước khi viết test, phải thống nhất thuật ngữ:

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Biến thể đã biết** (*known variant*) | `Platform.LINUX` tồn tại trong enum | Ứng dụng có tên định danh, **chưa chắc đã triển khai** |
| **Biến thể được hỗ trợ** (*supported variant*) | Registry có provider cho `WINDOWS`, `MACOS` | Có thể chọn một factory để tạo họ sản phẩm bắt buộc |
| **Loại sản phẩm được hỗ trợ** (*supported product type*) | Windows có Slider, macOS chưa có | Một khả năng chỉ có ở một số họ, nếu hợp đồng **cho phép tùy chọn** |

Xét một hợp đồng trong đó `Button` và `Checkbox` **bắt buộc** với mọi họ, còn `Slider` là tính năng mở rộng **tùy chọn**:

| Họ | Đã khai báo tên | Có factory trong registry | Button | Checkbox | Slider tùy chọn |
| --- | --- | --- | --- | --- | --- |
| Windows | Có | Có | Có | Có | Có |
| macOS | Có | Có | Có | Có | Chưa |
| Linux | Có | Chưa | — | — | — |

Các kết luận kiểm thử rất khác nhau:

- Cấu hình `linux` là **tên hợp lệ**, nhưng **biến thể chưa được hỗ trợ**.
- Cấu hình `android` là **tên không nhận diện được**, vì không có trong enum.
- Chọn `macos` rồi yêu cầu `Slider` là **sản phẩm tùy chọn chưa được hỗ trợ**, dù macOS vẫn hỗ trợ đủ Button/Checkbox.
- Một factory đã đăng ký nhưng trả `null` từ `createCheckbox()` là **lỗi triển khai hợp đồng bắt buộc**, không được xem như “Checkbox tùy chọn”.

**Quy tắc quan trọng:** Nếu `Slider createSlider()` là phương thức bắt buộc trong chính `UiFactory`, mọi factory phải triển khai nó. Việc trả `null` hay ném `UnsupportedOperationException` tùy tiện sẽ phá kỳ vọng của client. Trong ví dụ dưới đây, ta dùng một **interface khả năng mở rộng riêng** để thể hiện rõ Slider chỉ tùy chọn.

## 3. Ma trận kiểm thử đầu vào cấu hình

Giả sử ứng dụng đọc thuộc tính `ui.platform`. Nhóm quyết định một chính sách cụ thể:

- **Không cung cấp cấu hình:** dùng mặc định `WINDOWS`, và ghi rõ chính sách này trong tài liệu.
- **Có cung cấp tên:** cắt khoảng trắng ngoài, không phân biệt chữ hoa/thường.
- **Chuỗi rỗng hoặc chỉ có khoảng trắng:** từ chối như cấu hình sai.
- **Tên không có trong enum:** báo **tên biến thể không hợp lệ**.
- **Tên có trong enum nhưng registry chưa đăng ký:** báo **biến thể chưa hỗ trợ**.
- **Tên đã đăng ký:** chọn đúng factory; không tự đổi sang họ khác.

| Giá trị cấu hình ban đầu | Sau chuẩn hóa | Kết quả mong đợi |
| --- | --- | --- |
| Không có property (`null`) | Mặc định `WINDOWS` | Chọn WindowsFactory |
| `"WINDOWS"` | `WINDOWS` | Chọn WindowsFactory |
| `" windows "` | `WINDOWS` | Chọn WindowsFactory |
| `"macos"` | `MACOS` | Chọn MacFactory |
| `""` | Rỗng | Lỗi cấu hình rỗng |
| `"   "` | Rỗng | Lỗi cấu hình rỗng |
| `"android"` | Không thuộc enum | Lỗi tên biến thể không hợp lệ |
| `"linux"` | `LINUX` nhưng chưa đăng ký | Lỗi biến thể chưa được hỗ trợ |

Đây là các **lớp tương đương của đầu vào** (*equivalence classes*). Kiểm thử chỉ một trường hợp `WINDOWS` là chưa đủ: hệ thống còn cần chứng minh các đầu vào không hợp lệ **không âm thầm rơi vào macOS hoặc Windows**.

Nếu ứng dụng khác yêu cầu **bắt buộc cung cấp** `ui.platform`, khi đó `null` cũng phải báo lỗi thay vì dùng mặc định. Điều quan trọng là **test phải bám đúng chính sách đã công bố**, chứ không phải mặc định luôn được phép fallback.

## 4. Thiết kế ranh giới để dễ kiểm thử

Luồng chọn factory nên được tách thành các bước rõ trách nhiệm:

~~~mermaid
flowchart TD
    A["Đọc cấu hình dạng chuỗi"] --> B["Chuẩn hóa / parse Platform"]
    B --> C{"Tên hợp lệ?"}
    C -->|Không| D["Báo InvalidConfiguration"]
    C -->|Có| E["Tra Registry"]
    E --> F{"Đã đăng ký?"}
    F -->|Không| G["Báo UnsupportedVariant"]
    F -->|Có| H["Tạo và kiểm tra UiFactory"]
    H --> I["Tạo Button + Checkbox cùng họ"]
    I --> J{"Yêu cầu Slider?"}
    J -->|Không| K["Màn hình hoạt động"]
    J -->|Có| L{"Factory có khả năng Slider?"}
    L -->|Có| M["Tạo Slider đúng họ"]
    L -->|Không| N["Báo UnsupportedProduct"]
~~~

Nên tách nơi **đọc cấu hình thật** khỏi một hàm thuần nhận chuỗi và trả `Platform`. Khi đó, test có thể truyền lần lượt `"windows"`, `"macos"`, `""`, `"linux"` mà không phải sửa property toàn cục giữa các lần kiểm thử.

Tương tự, thay vì để mọi màn hình tự tra registry, hãy chọn một `UiFactory` ở **composition root**, rồi truyền factory qua constructor. Test cho màn hình có thể cung cấp một factory giả để kiểm tra tình huống trả sản phẩm sai họ hoặc thiếu sản phẩm bắt buộc.

### Ranh giới của từng loại test

| Lớp được kiểm thử | Dữ liệu đầu vào | Khẳng định chính |
| --- | --- | --- |
| Parser cấu hình | Chuỗi hoặc `null` | Giá trị enum hoặc lỗi phù hợp |
| Registry | Enum, danh sách provider | Trả đúng factory, từ chối tên chưa đăng ký |
| ConcreteFactory | Factory Windows/macOS | Tạo sản phẩm thuộc đúng họ |
| Client màn hình | Một `UiFactory` được truyền vào | Không trộn họ, thiếu sản phẩm thì fail fast |
| Phần mở rộng tùy chọn | Factory có/không có `Slider` | Tạo được Slider hoặc báo không hỗ trợ rõ ràng |

Mã ở phần sau gom các cấp kiểm thử này vào một ví dụ nhỏ, tự chứa.

## 5. Ví dụ Java đầy đủ: kiểm thử các trường hợp thành công và thất bại

Lưu đoạn mã thành `ProductFamilySelectionTestDemo.java`. Ví dụ dùng Java tiêu chuẩn, không phụ thuộc JUnit. Để tập trung vào kiến trúc, widget được mô phỏng bằng chuỗi hiển thị và thuộc tính họ, thay vì gọi thư viện GUI native.

~~~java
import java.util.Collections;
import java.util.EnumMap;
import java.util.EnumSet;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.function.Supplier;

public class ProductFamilySelectionTestDemo {
    enum Platform { WINDOWS, MACOS, LINUX }

    // Product interface bắt buộc.
    interface Button {
        Platform family();
        String render();
    }

    interface Checkbox {
        Platform family();
        String render();
    }

    // Product interface tùy chọn.
    interface Slider {
        Platform family();
        String render();
    }

    // Abstract Factory cơ bản: mọi họ đều phải có Button và Checkbox.
    interface UiFactory {
        Platform family();
        Button createButton();
        Checkbox createCheckbox();
    }

    // Khả năng mở rộng: chỉ factory nào hỗ trợ Slider mới implement.
    interface SliderCapableFactory extends UiFactory {
        Slider createSlider();
    }

    // ConcreteProduct: các widget Windows.
    static final class WindowsButton implements Button {
        public Platform family() { return Platform.WINDOWS; }
        public String render() { return "[Windows] Button"; }
    }

    static final class WindowsCheckbox implements Checkbox {
        public Platform family() { return Platform.WINDOWS; }
        public String render() { return "[Windows] Checkbox"; }
    }

    static final class WindowsSlider implements Slider {
        public Platform family() { return Platform.WINDOWS; }
        public String render() { return "[Windows] Slider"; }
    }

    // ConcreteProduct: các widget macOS.
    static final class MacButton implements Button {
        public Platform family() { return Platform.MACOS; }
        public String render() { return "[macOS] Button"; }
    }

    static final class MacCheckbox implements Checkbox {
        public Platform family() { return Platform.MACOS; }
        public String render() { return "[macOS] Checkbox"; }
    }

    static final class WindowsFactory implements SliderCapableFactory {
        public Platform family() { return Platform.WINDOWS; }

        public Button createButton() {
            return new WindowsButton();
        }

        public Checkbox createCheckbox() {
            return new WindowsCheckbox();
        }

        public Slider createSlider() {
            return new WindowsSlider();
        }
    }

    static final class MacFactory implements UiFactory {
        public Platform family() { return Platform.MACOS; }

        public Button createButton() {
            return new MacButton();
        }

        public Checkbox createCheckbox() {
            return new MacCheckbox();
        }
        // Slider không phải phần bắt buộc của UiFactory.
    }

    static final class UnsupportedVariantException
            extends IllegalArgumentException {
        UnsupportedVariantException(String message) {
            super(message);
        }
    }

    static final class UnsupportedProductException
            extends IllegalStateException {
        UnsupportedProductException(String message) {
            super(message);
        }
    }

    // Chuyển chuỗi cấu hình thành giá trị enum.
    static Platform parsePlatform(String raw) {
        if (raw == null) {
            return Platform.WINDOWS; // Default đã công bố.
        }

        String normalized = raw.trim().toUpperCase(Locale.ROOT);
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException(
                    "ui.platform is blank");
        }

        try {
            return Platform.valueOf(normalized);
        } catch (IllegalArgumentException ex) {
            throw new IllegalArgumentException(
                    "Unknown ui.platform: " + raw, ex);
        }
    }

    static final class FactoryRegistry {
        private final EnumMap<Platform, Supplier<UiFactory>> providers =
                new EnumMap<>(Platform.class);

        FactoryRegistry(
                Map<Platform, Supplier<UiFactory>> registrations) {
            Objects.requireNonNull(registrations, "registrations");

            registrations.forEach((platform, supplier) -> {
                Objects.requireNonNull(platform, "platform");
                Objects.requireNonNull(supplier, "supplier");
                providers.put(platform, supplier);
            });

            if (providers.isEmpty()) {
                throw new IllegalArgumentException(
                        "At least one variant must be registered");
            }
        }

        Set<Platform> supported() {
            return Collections.unmodifiableSet(
                    EnumSet.copyOf(providers.keySet()));
        }

        UiFactory select(Platform requested) {
            Objects.requireNonNull(requested, "requested");

            Supplier<UiFactory> provider = providers.get(requested);
            if (provider == null) {
                throw new UnsupportedVariantException(
                        "Variant " + requested
                        + " is unsupported; supported: " + supported());
            }

            UiFactory factory = Objects.requireNonNull(
                    provider.get(), "Provider returned null");

            if (factory.family() != requested) {
                throw new IllegalStateException(
                        "Provider family mismatch: requested "
                        + requested + " but got " + factory.family());
            }

            return factory;
        }
    }

    static FactoryRegistry standardRegistry() {
        Map<Platform, Supplier<UiFactory>> registrations =
                new EnumMap<>(Platform.class);

        registrations.put(Platform.WINDOWS, WindowsFactory::new);
        registrations.put(Platform.MACOS, MacFactory::new);
        // LINUX có trong enum nhưng chưa được đăng ký.

        return new FactoryRegistry(registrations);
    }

    static UiFactory choose(String raw, FactoryRegistry registry) {
        return registry.select(parsePlatform(raw));
    }

    static final class LoginScreen {
        private final UiFactory factory;
        private final Button button;
        private final Checkbox checkbox;

        LoginScreen(UiFactory factory) {
            this.factory = Objects.requireNonNull(factory, "factory");
            this.button = factory.createButton();
            this.checkbox = factory.createCheckbox();

            // Hai sản phẩm bắt buộc không được null hoặc khác họ.
            ensureProduct(button == null ? null : button.family(),
                    factory.family(), "Button");
            ensureProduct(checkbox == null ? null : checkbox.family(),
                    factory.family(), "Checkbox");
        }

        private static void ensureProduct(
                Platform actual, Platform expected, String product) {
            if (actual == null) {
                throw new IllegalStateException(
                        "Missing " + product + " for " + expected);
            }
            if (actual != expected) {
                throw new IllegalStateException(
                        product + " family mismatch: expected "
                        + expected + " but got " + actual);
            }
        }

        String render() {
            return button.render() + " / " + checkbox.render();
        }

        // Chỉ dùng được khi factory khai báo hỗ trợ loại sản phẩm này.
        Slider slider() {
            if (!(factory instanceof SliderCapableFactory)) {
                throw new UnsupportedProductException(
                        "Slider is unsupported for " + factory.family());
            }

            Slider slider =
                    ((SliderCapableFactory) factory).createSlider();

            ensureProduct(slider == null ? null : slider.family(),
                    factory.family(), "Slider");

            return slider;
        }
    }

    // Bộ kiểm tra đơn giản không cần thư viện ngoài.
    private static int passed;

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
        passed++;
    }

    static void expectException(
            Class<? extends Throwable> expectedType,
            String messageFragment,
            Runnable operation) {
        try {
            operation.run();
        } catch (Throwable actual) {
            if (!expectedType.isInstance(actual)) {
                throw new AssertionError(
                        "Wrong exception type: " + actual, actual);
            }
            if (!String.valueOf(actual.getMessage())
                    .contains(messageFragment)) {
                throw new AssertionError(
                        "Unexpected error message: " + actual.getMessage());
            }
            passed++;
            return;
        }
        throw new AssertionError(
                "Expected " + expectedType.getSimpleName());
    }

    static void runTests() {
        FactoryRegistry registry = standardRegistry();

        // 1. Các biến thể thực sự được hỗ trợ.
        check(registry.supported().equals(
                EnumSet.of(Platform.WINDOWS, Platform.MACOS)),
                "Wrong supported variants");

        // 2. Default chỉ áp dụng nếu cấu hình vắng mặt.
        check(choose(null, registry).family() == Platform.WINDOWS,
                "Wrong default");

        // 3. Chuẩn hóa chữ hoa/thường và khoảng trắng.
        check(choose(" windows ", registry).family()
                == Platform.WINDOWS, "Cannot select Windows");
        check(choose("macos", registry).family()
                == Platform.MACOS, "Cannot select macOS");

        LoginScreen windows =
                new LoginScreen(choose("WINDOWS", registry));
        LoginScreen mac =
                new LoginScreen(choose("MACOS", registry));

        // 4. Client nhận đúng các sản phẩm của mỗi họ.
        check(windows.render().equals(
                "[Windows] Button / [Windows] Checkbox"),
                "Wrong Windows family");
        check(mac.render().equals(
                "[macOS] Button / [macOS] Checkbox"),
                "Wrong macOS family");

        // 5. Sản phẩm tùy chọn được hỗ trợ ở Windows.
        check(windows.slider().family() == Platform.WINDOWS,
                "Wrong Slider family");

        // 6. Sản phẩm tùy chọn không được hỗ trợ ở macOS.
        expectException(UnsupportedProductException.class,
                "Slider", () -> mac.slider());

        // 7. Tên không thuộc enum phải bị từ chối.
        expectException(IllegalArgumentException.class,
                "Unknown", () -> choose("android", registry));

        // 8. Cấu hình rỗng phải bị từ chối, không fallback.
        expectException(IllegalArgumentException.class,
                "blank", () -> choose("   ", registry));

        // 9. Tên hợp lệ nhưng chưa đăng ký: lỗi khác với Unknown.
        expectException(UnsupportedVariantException.class,
                "unsupported", () -> choose("linux", registry));

        // 10. Registry đăng ký sai concrete factory.
        Map<Platform, Supplier<UiFactory>> wrongRegistration =
                new EnumMap<>(Platform.class);
        wrongRegistration.put(Platform.WINDOWS, MacFactory::new);

        expectException(IllegalStateException.class, "mismatch",
                () -> new FactoryRegistry(wrongRegistration)
                        .select(Platform.WINDOWS));

        // 11. Factory trả về Checkbox từ một họ khác.
        UiFactory mixedFamilyFactory = new UiFactory() {
            public Platform family() { return Platform.WINDOWS; }
            public Button createButton() {
                return new WindowsButton();
            }
            public Checkbox createCheckbox() {
                return new MacCheckbox();
            }
        };

        expectException(IllegalStateException.class, "Checkbox",
                () -> new LoginScreen(mixedFamilyFactory));

        // 12. Thiếu sản phẩm bắt buộc không phải là "tùy chọn".
        UiFactory missingCheckboxFactory = new UiFactory() {
            public Platform family() { return Platform.WINDOWS; }
            public Button createButton() {
                return new WindowsButton();
            }
            public Checkbox createCheckbox() {
                return null;
            }
        };

        expectException(IllegalStateException.class, "Missing Checkbox",
                () -> new LoginScreen(missingCheckboxFactory));

        // 13. Không thể khởi tạo registry không có biến thể nào.
        expectException(IllegalArgumentException.class,
                "At least one variant",
                () -> new FactoryRegistry(
                        new EnumMap<Platform, Supplier<UiFactory>>(
                                Platform.class)));

        System.out.println("PASS: " + passed + " checks");
    }

    public static void main(String[] args) {
        if (args.length == 1 && "--test".equals(args[0])) {
            runTests();
            return;
        }

        // Phần demo: chạy với system property ui.platform.
        if (args.length != 0) {
            throw new IllegalArgumentException(
                    "Use --test or supply -Dui.platform");
        }

        FactoryRegistry registry = standardRegistry();
        UiFactory factory = choose(
                System.getProperty("ui.platform"), registry);

        System.out.println("Selected: " + factory.family());
        System.out.println(new LoginScreen(factory).render());
    }
}
~~~

### Giải thích hai lựa chọn thiết kế trong ví dụ

**Thứ nhất, giữ riêng `parsePlatform` và `FactoryRegistry.select`.** Hai loại lỗi được phát hiện đúng vị trí: chuỗi không thuộc enum bị từ chối khi parse, còn `LINUX` có tên hợp lệ nhưng không đăng ký bị từ chối trong registry.

**Thứ hai, dùng `SliderCapableFactory` để biểu diễn khả năng tùy chọn.** `MacFactory` vẫn là một factory hợp lệ vì đã tạo đủ `Button` và `Checkbox`. Khi client cố dùng `Slider`, màn hình phát sinh `UnsupportedProductException` rõ ràng. Nếu sản phẩm yêu cầu tất cả các họ đều phải có Slider, hãy chuyển `createSlider()` vào hợp đồng bắt buộc và cập nhật mọi concrete factory, thay vì giữ chính sách tùy chọn.

Để phục vụ bài kiểm thử, `family()` cung cấp metadata về họ cho mỗi sản phẩm. Trong ứng dụng thật, một test cũng có thể kiểm tra kiểu ConcreteProduct hoặc hành vi đặc thù của từng họ. Chỉ dựa vào giá trị `family()` tự khai báo chưa đủ để phát hiện một implementation cố tình gắn nhãn sai.

## 6. Chạy ví dụ và đọc kết quả

Nếu đã lưu tệp UTF-8 như ở mục 5, dùng JDK:

~~~bash
javac -encoding UTF-8 ProductFamilySelectionTestDemo.java
java ProductFamilySelectionTestDemo --test
~~~

Các phép kiểm tra trong `runTests()` đếm từng khẳng định thành công và từng exception được mong đợi. Với mã ở trên, kết quả dự kiến:

~~~text
PASS: 15 checks
~~~

Mười lăm phép kiểm tra trải trên các tình huống chọn biến thể, render sản phẩm đúng họ, sản phẩm tùy chọn, cấu hình lỗi, registry sai, sản phẩm bắt buộc thiếu và registry không có provider.

Chạy ứng dụng với một biến thể hợp lệ:

~~~bash
java -Dui.platform=WINDOWS ProductFamilySelectionTestDemo
java -Dui.platform=MACOS ProductFamilySelectionTestDemo
~~~

Kết quả dự kiến cho Windows:

~~~text
Selected: WINDOWS
[Windows] Button / [Windows] Checkbox
~~~

Và macOS:

~~~text
Selected: MACOS
[macOS] Button / [macOS] Checkbox
~~~

Chạy với biến thể **hợp lệ về tên nhưng chưa được hỗ trợ**:

~~~bash
java -Dui.platform=LINUX ProductFamilySelectionTestDemo
~~~

Ứng dụng kết thúc với lỗi nêu rõ biến thể không hỗ trợ, chẳng hạn:

~~~text
UnsupportedVariantException: Variant LINUX is unsupported; supported: [WINDOWS, MACOS]
~~~

Dòng trên minh họa **thông điệp chính** của lỗi; khi chạy JVM thật, tên exception có thể kèm tên lớp bao ngoài và stack trace. Đây là kết quả mong đợi của phép thử âm, không phải lỗi biên dịch.

Chạy với tên không hợp lệ:

~~~bash
java -Dui.platform=ANDROID ProductFamilySelectionTestDemo
~~~

Lỗi chính:

~~~text
IllegalArgumentException: Unknown ui.platform: ANDROID
~~~

Trong dự án thật, một tầng xử lý lỗi ở điểm khởi động có thể chuyển exception thành mã lỗi hoặc thông báo cấu hình thân thiện hơn. Không nên bắt mọi exception rồi sử dụng một factory mặc định mà không có chính sách sản phẩm rõ ràng.

## 7. Đọc đúng ý nghĩa của từng phép kiểm thử

### Kiểm thử 1: Chọn biến thể hợp lệ

~~~java
UiFactory factory = choose("macos", registry);
check(factory.family() == Platform.MACOS,
        "macOS selection returned wrong factory");
~~~

Test này xác minh **quy tắc lựa chọn**. Nó sẽ phát hiện việc đăng ký `MACOS` nhầm thành WindowsFactory nếu registry kiểm tra `factory.family()`. Nhưng riêng test này **chưa chứng minh** rằng `MacFactory.createButton()` và `createCheckbox()` tạo đúng lớp hoặc đúng hành vi.

### Kiểm thử 2: Factory không trộn họ

~~~java
UiFactory factory = new WindowsFactory();

check(factory.createButton() instanceof WindowsButton,
        "Wrong concrete Button");
check(factory.createCheckbox() instanceof WindowsCheckbox,
        "Wrong concrete Checkbox");
~~~

Test dùng `instanceof` trong **bộ kiểm thử factory** để chứng minh wiring. Đây là nơi thích hợp để biết lớp cụ thể; client sản phẩm bình thường chỉ nên làm việc với các interface.

Bộ kiểm thử cũng nên kiểm tra **hành vi chung** của Button/Checkbox, chẳng hạn trạng thái chọn và sự kiện kích hoạt, khi ứng dụng có các thao tác ấy. Factory trả đúng lớp chưa bảo đảm implementation của lớp đó luôn đúng hợp đồng.

### Kiểm thử 3: Đưa lỗi vào factory giả

Một factory giả trả `WindowsButton` nhưng trả `MacCheckbox` tạo được kiểu `UiFactory` hợp lệ khi biên dịch. Test negative trong ví dụ phải báo lỗi tại lúc khởi tạo `LoginScreen`, tránh để giao diện trộn họ đi sâu hơn vào ứng dụng.

Đó là một **kiểm thử bất biến** (*invariant test*): nếu đã chọn một họ, mọi sản phẩm trong bộ bắt buộc phải phù hợp với họ ấy.

### Kiểm thử 4: Thiếu sản phẩm bắt buộc

Đối với `UiFactory` cơ bản, `createCheckbox()` phải tạo một Checkbox hợp lệ. Nếu trả `null`, `LoginScreen` báo `Missing Checkbox`.

Điều này khác việc cố dùng Slider trên MacFactory: Slider được khai báo rõ là **khả năng tùy chọn** và được từ chối qua exception riêng. Test nên bảo vệ sự phân biệt này; nếu cho phép một factory thiếu tùy tiện cả Button lẫn Checkbox, Abstract Factory không còn bảo đảm một họ sản phẩm đầy đủ như thiết kế.

### Kiểm thử 5: Cấu hình sai phải thất bại rõ ràng

Ba trường hợp cần phân biệt:

| Đầu vào | Loại lỗi | Vì sao không fallback ngầm? |
| --- | --- | --- |
| `"  "` | Cấu hình rỗng | Có thể là giá trị cấu hình bị ghi sai |
| `"ANDROID"` | Tên không nhận diện | Có thể là typo hoặc phiên bản phần mềm không biết biến thể |
| `"LINUX"` | Biến thể đã biết nhưng chưa đăng ký | Người dùng đã yêu cầu một khả năng bản phát hành chưa cung cấp |

**Mặc định khi không có cấu hình** là một chính sách riêng. Nó không đồng nghĩa với quyền bỏ qua cấu hình đã được cung cấp nhưng sai.

## 8. Kiểm thử sản phẩm tùy chọn có ý nghĩa gì?

Đoạn mã sử dụng `SliderCapableFactory` thể hiện nguyên tắc:

~~~java
UiFactory factory = choose("macos", registry);

if (factory instanceof SliderCapableFactory) {
    Slider slider =
            ((SliderCapableFactory) factory).createSlider();
    // Sử dụng Slider...
} else {
    // Chính sách nghiệp vụ/UI: ẩn tính năng hoặc thông báo rõ.
}
~~~

Việc client biết **một khả năng mở rộng** là có chủ đích khi loại sản phẩm thực sự tùy chọn. Tuy nhiên, cần quyết định thống nhất:

- **Ẩn tính năng** nếu Slider không có là chấp nhận được?
- **Hiển thị disabled** kèm giải thích?
- **Từ chối mở màn hình** vì Slider là điều kiện bắt buộc của màn hình này?
- **Dùng widget thay thế** chỉ khi có giải pháp tương đương đã được kiểm chứng?

Ví dụ hoàn chỉnh chọn **ném lỗi rõ ràng** từ `LoginScreen.slider()`. Đó là một chính sách hợp lệ cho màn hình yêu cầu Slider; ứng dụng khác có thể chủ động ẩn hoặc vô hiệu hóa điều khiển.

Test phải khẳng định đúng chính sách được chọn, không chỉ kiểm tra xem có exception hay không. Chẳng hạn với tính năng tùy chọn, test rằng nút điều chỉnh âm lượng bị ẩn trên macOS có thể phù hợp hơn test expect exception ở lớp màn hình.

### Khi hỗ trợ sản phẩm là bắt buộc

Nếu cả Windows lẫn macOS đều phải cung cấp `Slider`, hợp đồng thay đổi thành:

~~~java
interface UiFactory {
    Button createButton();
    Checkbox createCheckbox();
    Slider createSlider();
}
~~~

Lúc này, `MacFactory` không còn được phép coi Slider là tùy chọn. Kiểm thử nên xác nhận **mọi factory đều triển khai và tạo Slider đúng họ**, và kiểm tra lỗi tại thời điểm build hoặc khởi động khi một provider không đáp ứng hợp đồng.

Cách tách `SliderCapableFactory` chỉ là một ví dụ minh họa **khả năng có điều kiện**, không phải quy tắc bắt buộc của Abstract Factory.

## 9. Kiểm thử cấu hình mà không làm rò rỉ trạng thái toàn cục

Một lỗi test dễ gặp là thay đổi `System.setProperty("ui.platform", ...)` trong nhiều bài kiểm tra, sau đó quên phục hồi. Vì property là trạng thái **toàn JVM**, các test chạy song song có thể ảnh hưởng lẫn nhau.

Ví dụ không tốt:

~~~java
System.setProperty("ui.platform", "MACOS");
// Test ...
// Không khôi phục lại property.
~~~

Cách đơn giản hơn là chuyển phần logic nhận chuỗi sang một hàm thuần:

~~~java
Platform chosen = parsePlatform("macos");
UiFactory factory = registry.select(chosen);
~~~

Test có thể kiểm tra trực tiếp parser và registry mà không chỉnh trạng thái global. Chỉ cần một số ít integration test đọc `System.getProperty` thật, với cơ chế lưu/khôi phục giá trị cũ hoặc chạy trong JVM riêng biệt.

Với một ứng dụng sử dụng file cấu hình hay biến môi trường, nguyên tắc tương tự: **tách đọc nguồn cấu hình ra khỏi chuẩn hóa và lựa chọn**, để phần lớn test đơn giản, lặp lại được và không phụ thuộc vào môi trường máy chạy.

## 10. Thiết kế test matrix cho từng bản phát hành

Khi có nhiều nền tảng và nhiều loại sản phẩm, có thể xây bảng theo hai chiều:

| Tình huống | Windows | macOS | Linux (chưa đăng ký) |
| --- | --- | --- | --- |
| Chọn factory theo cấu hình | Thành công | Thành công | Báo không hỗ trợ |
| Tạo Button bắt buộc | WindowsButton | MacButton | Không có factory |
| Tạo Checkbox bắt buộc | WindowsCheckbox | MacCheckbox | Không có factory |
| Dùng Slider tùy chọn | Thành công | Báo không hỗ trợ | Không có factory |
| Tên cấu hình hợp lệ? | Có | Có | Có |
| Factory thực sự đăng ký? | Có | Có | Không |

Bảng này giúp tránh hai nhầm lẫn:

1. **Test cho tất cả giá trị enum không có nghĩa mọi giá trị enum đều phải thành công.** Mỗi biến thể có thể có kỳ vọng khác nhau theo trạng thái hỗ trợ.
2. **Test cho từng product interface không thay thế test tính cùng họ.** `WindowsButton` và `MacCheckbox` đều có thể qua kiểm thử riêng, nhưng việc đặt chúng trong cùng một màn hình vẫn sai.

Nếu ứng dụng chuyển từ hai họ sang ba họ, hãy bổ sung một cột Linux và cập nhật kỳ vọng từ “chưa đăng ký” thành “được hỗ trợ” **sau khi provider Linux hoàn chỉnh và được đưa vào bản phát hành**.

### Những kiểm thử thêm khi số lượng factory tăng

Với registry có nhiều provider, nên kiểm tra thêm: id bị đăng ký trùng, nhà cung cấp trả `null`, provider trả factory khai báo sai họ, version API không tương thích và lỗi khi load plugin. Các ca này đặc biệt có giá trị khi sử dụng Java ServiceLoader, dependency injection hoặc plugin độc lập.

Những test ấy nằm ở **biên tích hợp của registry**, không nhất thiết cần xuất hiện trong từng unit test màn hình.

## 11. Khi một test âm không thất bại như mong đợi

Giả sử một lập trình viên thay đổi logic lựa chọn thành:

~~~java
// Chống mẫu: mọi biến thể khác Windows trở thành macOS.
UiFactory factory = platform == Platform.WINDOWS
        ? new WindowsFactory()
        : new MacFactory();
~~~

Chạy với `Platform.LINUX` sẽ trả MacFactory. Nếu bộ test chỉ kiểm tra Windows/macOS, lỗi có thể lọt qua. Nhưng test **known-but-unregistered** sẽ thất bại vì nó mong đợi `UnsupportedVariantException`.

Tương tự, nếu ai đó sửa:

~~~java
public Checkbox createCheckbox() {
    return new MacCheckbox(); // trong WindowsFactory
}
~~~

Kiểm thử hàm `select(WINDOWS)` có thể vẫn đạt, vì factory khai báo họ Windows. Nhưng kiểm thử **màn hình cùng họ** hoặc kiểm thử **ConcreteFactory cụ thể** sẽ phát hiện sai.

Cuối cùng, nếu chuyển `MacFactory` thành `SliderCapableFactory` nhưng `createSlider()` trả `null`, test cần báo lỗi **thiếu sản phẩm trong một khả năng đã công bố**, chứ không báo “macOS không hỗ trợ Slider”. Khi một factory tuyên bố có khả năng, implementation phải thực hiện đúng.

Các thay đổi cố ý gây lỗi để xem test có phát hiện được hay không là một dạng **mutation testing thủ công** hữu ích cho bài học. Trong dự án lớn, có thể tự động hóa bằng công cụ mutation testing để đánh giá khả năng phát hiện lỗi của test suite.

## 12. Checklist triển khai kiểm thử thực tế

Khi review hệ thống Abstract Factory, cần xác nhận:

1. **Hợp đồng rõ ràng:** sản phẩm nào bắt buộc, sản phẩm nào tùy chọn?
2. **Chính sách cấu hình rõ ràng:** khi thiếu, rỗng, sai tên hoặc chưa hỗ trợ sẽ làm gì?
3. **Tách parser và registry:** có thể test mà không cần sửa property toàn cục?
4. **Danh sách hỗ trợ chính xác:** dựa vào provider đã đăng ký, không đồng nhất với toàn bộ giá trị enum?
5. **Factory được chọn đúng:** variant `X` có trả factory của `X`?
6. **Không trộn họ:** mỗi concrete factory tạo đúng tất cả sản phẩm của nó?
7. **Không thiếu sản phẩm bắt buộc:** phương thức tạo có thể trả `null` hoặc exception trái hợp đồng không?
8. **Tùy chọn được xử lý có chủ đích:** sản phẩm không được hỗ trợ có thông báo hoặc hành vi UI rõ ràng?
9. **Kiểm thử thất bại có thông tin chẩn đoán:** tên variant, loại sản phẩm và danh sách được hỗ trợ có đủ?
10. **Kiểm thử tích hợp:** khi chạy với cấu hình hoặc plugin thực tế, danh sách hỗ trợ có khớp bản phát hành?

Một bộ kiểm thử có các ca âm tốt giúp phát hiện **lỗi định tuyến** và **lỗi hợp đồng** sớm, trước khi người dùng thấy giao diện sai nền tảng hoặc thiếu thành phần.

## 13. Bài tập tự luyện

**Bài 1 — Thêm Linux vào registry.** Viết `LinuxButton`, `LinuxCheckbox`, `LinuxFactory`, đăng ký `LINUX`. Đổi test `"linux"` từ kỳ vọng exception sang kiểm tra thành công; đồng thời bảo đảm Button/Checkbox được tạo đúng họ. Những test của Windows/macOS có cần thay đổi không?

**Bài 2 — Cấu hình rỗng.** Thay chính sách “vắng cấu hình dùng mặc định Windows” bằng chính sách “bắt buộc khai báo”. Sửa parser để `null` báo lỗi; viết test phân biệt `null`, `""` và `"  "`.

**Bài 3 — Factory trả nhầm họ.** Cố ý đổi `MacFactory.createCheckbox()` thành `new WindowsCheckbox()`. Dự đoán test nào thất bại và nguyên nhân. Giải thích vì sao kiểu trả về `Checkbox` không ngăn được lỗi.

**Bài 4 — Thêm sản phẩm bắt buộc.** Chuyển Slider từ `SliderCapableFactory` vào `UiFactory`. Cập nhật mọi concrete factory và viết lại các phép kiểm thử. Tại sao test “Slider không hỗ trợ trên macOS” không còn phù hợp?

**Bài 5 — Cấu hình ngoài dự kiến.** Xét các chuỗi `"macOS"`, `"  MACOS  "`, `"mac os"`, `"LINUX"` và `"ANDROID"`. Hãy phân loại từng đầu vào thành hợp lệ/được hỗ trợ, hợp lệ/chưa được hỗ trợ, hoặc không hợp lệ. Đề xuất thông báo lỗi có thể dùng trong sản phẩm thật.

### Câu hỏi ghi nhớ

- Vì sao cần kiểm thử parser và registry riêng thay vì chỉ test `main()`?
- Một giá trị trong enum đã đủ để kết luận biến thể đó được hỗ trợ chưa?
- Khác biệt giữa factory **trả sai họ** và factory **không có provider** là gì?
- Khi nào không hỗ trợ một loại sản phẩm là hợp lệ, và khi nào là vi phạm hợp đồng?
- Vì sao một test thành công của `WindowsButton` chưa đủ để chứng minh toàn bộ màn hình Windows đúng?
- Có thể kiểm thử config mà không gọi `System.setProperty` liên tục bằng cách nào?

**Ghi nhớ:** Để kiểm thử Abstract Factory đầy đủ, cần tách **tên biến thể hợp lệ**, **biến thể được đăng ký**, **sản phẩm bắt buộc của mỗi họ** và **khả năng tùy chọn**. Những trường hợp không hỗ trợ phải có kết quả được định nghĩa rõ, còn mọi factory được chọn phải cung cấp đúng họ sản phẩm đã cam kết. Các phép kiểm thử âm là phần thiết yếu để chứng minh hệ thống không âm thầm chọn sai biến thể hoặc chấp nhận những sản phẩm không hợp lệ.


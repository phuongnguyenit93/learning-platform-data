# Chứng minh đổi biến thể bằng cấu hình và kiểm thử mà không sửa logic nghiệp vụ

> **Chương:** Đánh giá thiết kế  
> **Học phần:** `SOFTWARE_DESIGN_DESIGN_PATTERN_CREATIONAL_ABSTRACT_FACTORY` — Học về Abstract Factory trong Design Pattern.  
> **Mục tiêu:** Chứng minh bằng ví dụ chạy được và phép kiểm thử rằng ứng dụng có thể thay **họ sản phẩm** qua cấu hình, trong khi mã nghiệp vụ vẫn hoạt động theo cùng một quy tắc và không cần chỉnh sửa khi chuyển biến thể.

## 1. Đánh giá thiết kế cần bằng chứng gì?

Một lợi ích thường được nhắc tới của mẫu thiết kế **Abstract Factory** là: khi ứng dụng cần các họ đối tượng khác nhau, mã sử dụng có thể làm việc với các interface chung thay vì phụ thuộc vào từng lớp cụ thể. Tuy nhiên, chỉ nhìn vào sơ đồ lớp và nói “dễ mở rộng” chưa đủ để đánh giá giải pháp.

Ta cần chứng minh ba điều có thể quan sát và kiểm thử:

1. **Đổi cấu hình → đổi đúng họ đối tượng:** cấu hình Windows phải tạo `WindowsButton` và `WindowsCheckbox`; cấu hình macOS phải tạo `MacButton` và `MacCheckbox`.
2. **Đổi cấu hình → hành vi khác biệt mong đợi:** giao diện được tạo và hiển thị theo biến thể đã chọn.
3. **Đổi cấu hình → quy tắc nghiệp vụ không thay đổi:** cùng dữ liệu đầu vào phải cho cùng kết quả nghiệp vụ, bất kể giao diện đang dùng Windows hay macOS.

Ngoài ra, để khẳng định **không phải sửa logic nghiệp vụ**, cần kiểm tra sự phân chia phụ thuộc: việc đọc cấu hình và chọn concrete factory phải nằm ở **điểm lắp ghép ứng dụng** (*composition root*); lớp nghiệp vụ không biết tên nền tảng và không tự `new` concrete product.

Đây là tiêu chí đánh giá thiết kế, không phải lời khẳng định rằng mọi thay đổi biến thể luôn miễn phí. Một biến thể mới vẫn phải có concrete product và concrete factory phù hợp; mục tiêu là **giữ các thay đổi đó ra khỏi logic nghiệp vụ đang ổn định**.

## 2. Tình huống: màn hình thanh toán Windows và macOS

Ứng dụng bán hàng có màn hình thanh toán gồm:

- Nút **Thanh toán** (`Button`).
- Ô chọn **Xuất hóa đơn** (`Checkbox`).
- Quy tắc tính số tiền cần thanh toán (`CheckoutService`).

Yêu cầu giao diện:

| Cấu hình `ui.platform` | Button được tạo | Checkbox được tạo |
| --- | --- | --- |
| `WINDOWS` | `WindowsButton` | `WindowsCheckbox` |
| `MACOS` | `MacButton` | `MacCheckbox` |

Yêu cầu nghiệp vụ của ví dụ:

- `unitPrice` là đơn giá không âm.
- `quantity` là số lượng nguyên dương.
- Khi mua từ **3 sản phẩm trở lên**, giảm **10%** tổng tiền trước giảm (làm tròn phần giảm xuống đơn vị tiền nguyên).
- Quy tắc này **không phụ thuộc** nền tảng giao diện.

Với đơn giá **100.000** và số lượng **3**, kết quả phải là:

~~~text
Tạm tính = 100.000 × 3 = 300.000
Giảm giá = 300.000 × 10% = 30.000
Thành tiền = 270.000
~~~

Hai lần chạy trên Windows và macOS phải cùng trả về `270000`. Chỉ có cách thể hiện Button và Checkbox được phép thay đổi theo cấu hình.

> Các widget trong ví dụ bên dưới là lớp mô phỏng trả về chuỗi. Chúng minh họa cấu trúc Abstract Factory, **không phải widget native thật** và cũng không thực hiện giao dịch thanh toán.

## 3. Tách ba vùng trách nhiệm để việc đổi cấu hình không lan vào nghiệp vụ

~~~mermaid
flowchart TD
    C["Cấu hình khởi động: ui.platform"] --> R["Composition root: parse + chọn factory"]
    R --> W["WindowsFactory"]
    R --> M["MacFactory"]
    W --> A["GUIFactory interface"]
    M --> A
    A --> S["CheckoutScreen nhận GUIFactory"]
    S --> B["Button"]
    S --> X["Checkbox"]
    S --> D["CheckoutService: tính tổng và giảm giá"]
    D --> O["Kết quả nghiệp vụ"]
~~~

Sơ đồ diễn đạt các vai trò cần có:

| Vùng mã | Biết gì? | Không nên phải biết gì? |
| --- | --- | --- |
| **Composition root** | Giá trị `ui.platform`, cách chọn `WindowsFactory` hoặc `MacFactory` | Quy tắc tính tiền |
| **GUIFactory và ConcreteFactory** | Cách tạo Button/Checkbox của từng họ | Giảm giá, đơn giá, số lượng |
| **CheckoutScreen** | Cách gọi factory và dịch vụ qua hợp đồng | Quy tắc chọn factory theo chuỗi cấu hình |
| **CheckoutService** | Cách tính tổng tiền và giảm giá | `Platform`, `WindowsButton`, `MacCheckbox` và tên concrete factory |

Trong mẫu Abstract Factory, màn hình cần một **bộ sản phẩm đồng nhất**. Nó nhận một `GUIFactory`, sau đó gọi `createButton()` và `createCheckbox()` trên **cùng factory đó**.

Quy tắc thiết kế được mô tả như sau:

~~~text
factory = resolveFactory(readConfiguration())

button   = factory.createButton()
checkbox = factory.createCheckbox()

family(button) == family(checkbox) == selectedPlatform
businessResult(input, WINDOWS) == businessResult(input, MACOS)
~~~

Biểu thức `family(...)` là cách diễn đạt yêu cầu cùng họ, không bắt buộc là phương thức Java cần xuất hiện trong product interface.

Điều kiện cuối cùng về kết quả nghiệp vụ **chỉ đúng khi sự khác biệt giữa các biến thể không được yêu cầu làm thay đổi nghiệp vụ**. Trong bài toán này, Windows và macOS là các họ widget hiển thị, nên quy tắc giảm giá phải nhất quán.

## 4. Dùng cấu hình JVM để chọn biến thể

Thay vì viết điều kiện tạo factory bên trong màn hình, ứng dụng đọc tham số cấu hình **`ui.platform`** từ lúc khởi động.

Ví dụ hai lệnh chạy ứng dụng với hai cấu hình khác nhau:

~~~bash
java -Dui.platform=WINDOWS VariantConfigEvaluationDemo
java -Dui.platform=MACOS VariantConfigEvaluationDemo
~~~

`-Dui.platform=...` là **JVM system property**. Đây là một dạng cấu hình bên ngoài mã nguồn: cùng một bản biên dịch Java có thể nhận giá trị khác nhau ở từng lần khởi chạy.

Ưu điểm của cách này trong bài học:

- Không phải sửa hoặc biên dịch lại `CheckoutService` để chuyển từ Windows sang macOS.
- Không cần file cấu hình riêng cho ví dụ nhỏ.
- Có thể xác minh bằng cách chạy lại chương trình với giá trị khác.
- Dễ thử cấu hình không hợp lệ, ví dụ `-Dui.platform=LINUX` khi chưa có hỗ trợ Linux.

Ứng dụng thực tế cũng có thể đọc từ file `.properties`, biến môi trường hoặc trình quản lý cấu hình. Bất kể nguồn nào, **hãy chuyển giá trị cấu hình thành một enum hoặc định danh hợp lệ ở ranh giới ứng dụng**, sau đó chọn factory một lần cho phạm vi cần dùng.

### Tránh fallback sai khi gặp biến thể lạ

Không nên viết:

~~~java
GUIFactory factory = "WINDOWS".equals(rawPlatform)
        ? new WindowsFactory()
        : new MacFactory();
~~~

Đoạn mã này biến mọi giá trị khác `"WINDOWS"`, kể cả `"LINUX"` hay lỗi chính tả, thành macOS một cách âm thầm.

Giải pháp nên phân biệt:

- **Cấu hình không cung cấp**: có thể dùng mặc định đã được công bố, chẳng hạn Windows.
- **Cấu hình cung cấp nhưng không hợp lệ hoặc chưa hỗ trợ**: báo lỗi rõ ràng, tránh tạo giao diện sai kỳ vọng.

## 5. Ví dụ Java hoàn chỉnh: đổi cấu hình, giữ nguyên mã nghiệp vụ

Lưu toàn bộ đoạn mã sau thành `VariantConfigEvaluationDemo.java`. Ví dụ dùng Java tiêu chuẩn, không yêu cầu thư viện bên ngoài. Nó còn chứa một chế độ `--test` để tự kiểm tra các bằng chứng cần thiết.

~~~java
import java.util.Locale;
import java.util.Objects;

public class VariantConfigEvaluationDemo {

    // 1. Các biến thể được ứng dụng hỗ trợ.
    enum Platform {
        WINDOWS, MACOS
    }

    // 2. AbstractProduct: hợp đồng UI chung.
    interface Button {
        String render();
    }

    interface Checkbox {
        String render();
    }

    // 3. Các ConcreteProduct thuộc họ Windows.
    static final class WindowsButton implements Button {
        private final String label;

        WindowsButton(String label) {
            this.label = Objects.requireNonNull(label);
        }

        @Override
        public String render() {
            return "Windows Button: " + label;
        }
    }

    static final class WindowsCheckbox implements Checkbox {
        private final String label;

        WindowsCheckbox(String label) {
            this.label = Objects.requireNonNull(label);
        }

        @Override
        public String render() {
            return "Windows Checkbox: " + label;
        }
    }

    // 4. Các ConcreteProduct thuộc họ macOS.
    static final class MacButton implements Button {
        private final String label;

        MacButton(String label) {
            this.label = Objects.requireNonNull(label);
        }

        @Override
        public String render() {
            return "macOS Button: " + label;
        }
    }

    static final class MacCheckbox implements Checkbox {
        private final String label;

        MacCheckbox(String label) {
            this.label = Objects.requireNonNull(label);
        }

        @Override
        public String render() {
            return "macOS Checkbox: " + label;
        }
    }

    // 5. AbstractFactory: tạo trọn họ widget.
    interface GUIFactory {
        Button createButton(String label);
        Checkbox createCheckbox(String label);
    }

    // 6. ConcreteFactory: đúng sản phẩm của từng họ.
    static final class WindowsFactory implements GUIFactory {
        @Override
        public Button createButton(String label) {
            return new WindowsButton(label);
        }

        @Override
        public Checkbox createCheckbox(String label) {
            return new WindowsCheckbox(label);
        }
    }

    static final class MacFactory implements GUIFactory {
        @Override
        public Button createButton(String label) {
            return new MacButton(label);
        }

        @Override
        public Checkbox createCheckbox(String label) {
            return new MacCheckbox(label);
        }
    }

    // 7. Business logic: độc lập hoàn toàn với nền tảng UI.
    static final class CheckoutService {
        int calculateTotal(int unitPrice, int quantity) {
            if (unitPrice < 0 || quantity <= 0) {
                throw new IllegalArgumentException(
                        "Price must be nonnegative; quantity must be positive");
            }

            long subtotal = (long) unitPrice * quantity;
            long discount = quantity >= 3 ? subtotal / 10 : 0;

            // Không âm do đã kiểm tra input; phát hiện tràn int rõ ràng.
            return Math.toIntExact(subtotal - discount);
        }
    }

    // 8. Client: biết các interface, không chọn nền tảng.
    static final class CheckoutScreen {
        private final Button payButton;
        private final Checkbox invoiceCheckbox;
        private final CheckoutService service;

        CheckoutScreen(GUIFactory factory, CheckoutService service) {
            Objects.requireNonNull(factory);
            this.service = Objects.requireNonNull(service);

            // Cả hai product đến từ cùng một factory.
            this.payButton = factory.createButton("Thanh toán");
            this.invoiceCheckbox = factory.createCheckbox("Xuất hóa đơn");
        }

        String render() {
            return payButton.render() + "\n" + invoiceCheckbox.render();
        }

        int checkout(int unitPrice, int quantity) {
            return service.calculateTotal(unitPrice, quantity);
        }
    }

    // 9. Composition root: chỉ ở đây mới đọc và chọn biến thể.
    static Platform parsePlatform(String raw) {
        Objects.requireNonNull(raw, "ui.platform");

        try {
            return Platform.valueOf(
                    raw.trim().toUpperCase(Locale.ROOT));
        } catch (IllegalArgumentException e) {
            throw new IllegalArgumentException(
                    "Unsupported ui.platform: " + raw, e);
        }
    }

    static GUIFactory resolveFactory(Platform platform) {
        Objects.requireNonNull(platform, "platform");

        switch (platform) {
            case WINDOWS:
                return new WindowsFactory();
            case MACOS:
                return new MacFactory();
            default:
                throw new IllegalArgumentException(
                        "No factory for platform: " + platform);
        }
    }

    // 10. Phép kiểm tra không cần JUnit hay thư viện ngoài.
    private static int passed;

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
        passed++;
    }

    static void selfTest() {
        GUIFactory windowsFactory = resolveFactory(Platform.WINDOWS);
        GUIFactory macFactory = resolveFactory(Platform.MACOS);

        // Bằng chứng A: factory tạo đúng họ sản phẩm.
        check(windowsFactory.createButton("test")
                instanceof WindowsButton, "Wrong Windows Button");
        check(windowsFactory.createCheckbox("test")
                instanceof WindowsCheckbox, "Wrong Windows Checkbox");
        check(macFactory.createButton("test")
                instanceof MacButton, "Wrong macOS Button");
        check(macFactory.createCheckbox("test")
                instanceof MacCheckbox, "Wrong macOS Checkbox");

        CheckoutService sameBusinessService = new CheckoutService();

        CheckoutScreen windows = new CheckoutScreen(
                windowsFactory, sameBusinessService);
        CheckoutScreen mac = new CheckoutScreen(
                macFactory, sameBusinessService);

        // Bằng chứng B: kết quả UI khác theo biến thể.
        check(windows.render().contains("Windows Button:"),
                "Windows UI is missing its Button");
        check(windows.render().contains("Windows Checkbox:"),
                "Windows UI is missing its Checkbox");
        check(mac.render().contains("macOS Button:"),
                "macOS UI is missing its Button");
        check(mac.render().contains("macOS Checkbox:"),
                "macOS UI is missing its Checkbox");
        check(!windows.render().equals(mac.render()),
                "UI should be different between the families");

        // Bằng chứng C: cùng dữ liệu, cùng quy tắc nghiệp vụ.
        int windowsTotal = windows.checkout(100_000, 3);
        int macTotal = mac.checkout(100_000, 3);

        check(windowsTotal == 270_000,
                "Wrong Windows checkout total");
        check(macTotal == 270_000,
                "Wrong macOS checkout total");
        check(windowsTotal == macTotal,
                "Business behavior changed with UI platform");

        // Trường hợp chưa đạt ngưỡng giảm giá.
        check(windows.checkout(100_000, 2) == 200_000,
                "Wrong Windows non-discount total");
        check(mac.checkout(100_000, 2) == 200_000,
                "Wrong macOS non-discount total");

        // Bằng chứng D: cấu hình được chuyển đổi đúng.
        check(parsePlatform(" windows ") == Platform.WINDOWS,
                "Cannot parse Windows platform");
        check(parsePlatform("macos") == Platform.MACOS,
                "Cannot parse macOS platform");

        boolean rejectedUnknown = false;
        try {
            parsePlatform("LINUX");
        } catch (IllegalArgumentException expected) {
            rejectedUnknown = true;
        }
        check(rejectedUnknown, "Unknown platform was accepted");

        boolean rejectedInvalidOrder = false;
        try {
            windows.checkout(100_000, 0);
        } catch (IllegalArgumentException expected) {
            rejectedInvalidOrder = true;
        }
        check(rejectedInvalidOrder,
                "Invalid order was not rejected");

        System.out.println("PASS: " + passed + " checks");
    }

    public static void main(String[] args) {
        if (args.length == 1 && "--test".equals(args[0])) {
            selfTest();
            return;
        }

        // Giá trị mặc định chỉ dùng khi chưa cung cấp property.
        String raw = System.getProperty("ui.platform", "WINDOWS");
        Platform platform = parsePlatform(raw);

        GUIFactory factory = resolveFactory(platform);
        CheckoutScreen screen = new CheckoutScreen(
                factory, new CheckoutService());

        System.out.println("selected=" + platform);
        System.out.println(screen.render());
        System.out.println("total=" + screen.checkout(100_000, 3));
    }
}
~~~

### Điểm cần quan sát trong mã nguồn

**`CheckoutService` không chứa một tham chiếu nào đến `Platform`, `GUIFactory`, `WindowsButton` hay `MacButton`.** Đầu vào của nó là `unitPrice` và `quantity`; đầu ra là tổng tiền được tính theo một quy tắc cố định.

**`CheckoutScreen` không có `switch(platform)` và không gọi `new WindowsButton(...)`.** Nó tạo sản phẩm thông qua `GUIFactory` đã được truyền vào constructor.

**Chỉ `parsePlatform(...)`, `resolveFactory(...)` và `main(...)` biết cách cấu hình được chuyển thành một concrete factory.** Các lớp sản phẩm vẫn được tạo theo đúng họ do factory đảm nhiệm.

Điều này giúp thay đổi biến thể theo cấu hình mà không phải chạm vào lớp nghiệp vụ. Các phép kiểm thử ngay trong tệp là **mã kiểm tra minh họa**, được gọi riêng bằng `--test`; ứng dụng chạy thông thường không phải kiểm tra kiểu cụ thể bằng `instanceof`.

## 6. Thực hiện phép chứng minh bằng ba lần chạy

Lưu tệp ở dạng UTF-8 và biên dịch một lần bằng JDK:

~~~bash
javac -encoding UTF-8 VariantConfigEvaluationDemo.java
~~~

### Lần 1 — Cấu hình Windows

~~~bash
java -Dui.platform=WINDOWS VariantConfigEvaluationDemo
~~~

Kết quả dự kiến:

~~~text
selected=WINDOWS
Windows Button: Thanh toán
Windows Checkbox: Xuất hóa đơn
total=270000
~~~

### Lần 2 — Cấu hình macOS

~~~bash
java -Dui.platform=MACOS VariantConfigEvaluationDemo
~~~

Kết quả dự kiến:

~~~text
selected=MACOS
macOS Button: Thanh toán
macOS Checkbox: Xuất hóa đơn
total=270000
~~~

Hai lệnh chạy dùng **cùng một tệp `.class`** được biên dịch từ cùng mã nguồn; chỉ khác giá trị JVM property.

| Giá trị kiểm chứng | Lần Windows | Lần macOS | Nhận xét |
| --- | --- | --- | --- |
| Cấu hình đã chọn | `WINDOWS` | `MACOS` | Khác nhau |
| Chuỗi render Button | Windows | macOS | Thay theo biến thể |
| Chuỗi render Checkbox | Windows | macOS | Thay theo biến thể |
| `unitPrice` | `100000` | `100000` | Giữ nguyên |
| `quantity` | `3` | `3` | Giữ nguyên |
| `total` | `270000` | `270000` | **Bất biến theo nền tảng** |
| Mã `CheckoutService` | Một implementation | Chính implementation đó | **Không cần chỉnh sửa** |

Ở đây “không sửa logic nghiệp vụ” được chứng minh ở hai góc độ: **cùng artifact biên dịch** được chạy với hai cấu hình khác nhau và **cùng quy tắc nghiệp vụ** trả về cùng kết quả.

Chỉ so sánh một cặp kết quả chưa chứng minh được mọi trường hợp; vì vậy còn cần các bài kiểm thử ở mục tiếp theo.

### Lần 3 — Chạy các kiểm thử

~~~bash
java VariantConfigEvaluationDemo --test
~~~

Kết quả dự kiến:

~~~text
PASS: 18 checks
~~~

Các phép kiểm tra sử dụng `AssertionError` để dừng khi điều kiện sai; nếu không có ngoại lệ và in ra thông báo PASS, bộ điều kiện trong `selfTest()` đã đạt. Đây là bộ kiểm thử tự chứa để minh họa; trong dự án thật, nên chuyển chúng thành các test tự động của hệ thống kiểm thử đang dùng.

> Nếu chạy thử với `-Dui.platform=LINUX`, `parsePlatform(...)` sẽ từ chối vì ứng dụng chưa công bố biến thể Linux. Chạy với cấu hình không hợp lệ không được âm thầm đổi sang macOS.

## 7. Ma trận kiểm thử: tách đúng các dạng bằng chứng

Một bộ kiểm thử tốt phải xem xét nhiều hơn việc “chạy không lỗi”. Có thể chia theo các mục tiêu độc lập:

| Mục tiêu | Cách kiểm chứng | Lỗi được phát hiện |
| --- | --- | --- |
| **Phân giải cấu hình** | `" windows "` → `WINDOWS`, `"macos"` → `MACOS` | Lỗi chuẩn hóa/chuyển đổi tên |
| **Từ chối cấu hình lạ** | `"LINUX"` khi chưa hỗ trợ → exception | Fallback âm thầm sang họ sai |
| **Nhất quán theo họ** | `WindowsFactory` trả đúng WindowsButton và WindowsCheckbox | Factory tạo trộn họ |
| **Biến thể thực sự khác** | Kết quả render của hai màn hình khác nhau | Factory tạo sai biến thể hoặc vô tình dùng chung implementation |
| **Nghiệp vụ bất biến** | `calculateTotal(100000, 3)` → `270000` cho cả hai màn hình | Logic bị phụ thuộc nền tảng |
| **Nhánh không giảm giá** | `calculateTotal(100000, 2)` → `200000` cho cả hai | Sai nhánh điều kiện nghiệp vụ |
| **Dữ liệu không hợp lệ** | `quantity=0` phải bị từ chối | Thiếu kiểm tra quy tắc nghiệp vụ |
| **Ranh giới phụ thuộc** | Review mã: `CheckoutService` không import/nhận `Platform` hoặc concrete GUI | Coupling không mong muốn |

Những mục tiêu trên giải đáp các câu hỏi khác nhau:

- Test factory đúng họ nói rằng việc **tạo đối tượng** nhất quán.
- Test render nói rằng **thay biến thể có hiệu lực**.
- Test tổng tiền nói rằng **kết quả nghiệp vụ không đổi** với cùng dữ liệu.
- Review phụ thuộc giúp chứng minh rằng **logic nghiệp vụ không cần sửa** vì ranh giới kiến trúc đã đúng.

Việc xuất hiện một test đúng kết quả chưa thể tự chứng minh cả kiến trúc không phụ thuộc vào nền tảng. Ngược lại, nhìn thấy interface sạch cũng chưa bảo đảm một concrete factory không vô tình trả sai sản phẩm. **Cần kết hợp kiểm thử hành vi với kiểm tra phụ thuộc.**

### Cách nâng cấp thành kiểm thử tự động ở dự án

Nếu dự án sử dụng JUnit, có thể kiểm thử theo bảng tham số gồm `WINDOWS` và `MACOS`, rồi khẳng định kết quả nghiệp vụ bằng nhau trên cùng bộ dữ liệu. Với kiểm thử tạo họ, đặt test ở package có quyền truy cập concrete product để xác nhận wiring. Với kiểm thử cấu trúc, có thể dùng quy tắc phân tích dependency hoặc quy ước review để bảo đảm package nghiệp vụ không phụ thuộc vào package GUI cụ thể.

Bài này dùng `selfTest()` không có thư viện bên ngoài nhằm bảo đảm người học có thể tự tái tạo kết quả trước khi tích hợp vào hạ tầng test.

## 8. Kiểm tra thay đổi mã nguồn khi chuyển biến thể

Với ứng dụng đã được thiết kế như ví dụ, việc chuyển từ Windows sang macOS **trong một lần chạy mới** chỉ là thay tham số:

~~~text
Trước: java -Dui.platform=WINDOWS VariantConfigEvaluationDemo
Sau:   java -Dui.platform=MACOS VariantConfigEvaluationDemo
~~~

Không có thay đổi nào ở các lớp:

~~~text
CheckoutService
CheckoutScreen
Button
Checkbox
GUIFactory
WindowsFactory
MacFactory
~~~

Khi đánh giá một mã nguồn thực tế, có thể xác nhận điều này bằng kiểm tra thay đổi trong hệ thống quản lý phiên bản. Ví dụ, nếu cấu hình được lưu trong file và hai lần triển khai chỉ khác giá trị `ui.platform`, so sánh commit hoặc cấu hình phát hành phải cho thấy **không có diff trong mã nghiệp vụ**.

Tuy nhiên, hai trường hợp cần tách rõ:

**Chuyển giữa hai biến thể đã hỗ trợ.** Thường chỉ cần đổi cấu hình và khởi tạo lại các thành phần theo factory được chọn. Đây là trường hợp đang được chứng minh.

**Bổ sung một biến thể hoàn toàn mới.** Vẫn cần viết các concrete product tương ứng, một concrete factory và đăng ký nó tại composition root. Lợi ích nằm ở việc `CheckoutService` và `CheckoutScreen` **không phải thêm nhánh chọn nền tảng**. Trong ví dụ hiện tại, `Platform` và `resolveFactory` sẽ phải mở rộng nếu thêm Linux.

Một test hồi quy nên xác nhận quy tắc nghiệp vụ cho **mọi biến thể đang hỗ trợ**, đặc biệt sau khi có thêm factory mới.

## 9. Đánh giá tác động của cách lựa chọn factory đến kiến trúc

### Cách làm không phù hợp: nghiệp vụ tự đọc cấu hình

~~~java
// Minh họa chống mẫu: trộn quyết định biến thể vào nghiệp vụ.
final class CheckoutServiceWithPlatform {
    int calculateTotal(int unitPrice, int quantity) {
        String platform = System.getProperty("ui.platform");

        if ("WINDOWS".equals(platform)) {
            // Một nhánh xử lý riêng cho Windows...
        } else {
            // Một nhánh xử lý riêng cho macOS...
        }

        // Quy tắc tổng tiền giờ phụ thuộc vào cấu hình giao diện.
        return unitPrice * quantity;
    }
}
~~~

Đây không phải một implementation hoàn chỉnh của quy tắc giảm giá ở mục 2. Đoạn mã chỉ minh họa **lỗi thiết kế**: lớp tính tiền đã trực tiếp biết đến nền tảng giao diện. Nó vừa làm thay đổi trách nhiệm, vừa tạo nguy cơ hai nhánh nghiệp vụ hành xử khác nhau.

### Cách làm phù hợp: lắp ghép ở ranh giới

~~~java
Platform chosen = parsePlatform(
        System.getProperty("ui.platform", "WINDOWS"));
GUIFactory factory = resolveFactory(chosen);
CheckoutService service = new CheckoutService();
CheckoutScreen screen = new CheckoutScreen(factory, service);
~~~

Ở đây, việc chọn nền tảng xảy ra tại một chỗ. Sau đó:

- `CheckoutScreen` sử dụng factory thông qua interface chung.
- `CheckoutService` thực hiện nghiệp vụ thông qua dữ liệu nghiệp vụ.
- `WindowsFactory` và `MacFactory` quyết định lớp cụ thể của các sản phẩm GUI.

Hướng phụ thuộc này giúp việc kiểm thử đơn giản hơn: có thể truyền một factory giả khi muốn kiểm thử màn hình, và kiểm thử `CheckoutService` trực tiếp mà không cần khởi động GUI hoặc giả lập hệ điều hành.

## 10. Các trường hợp dễ hiểu sai khi đọc kết quả

### 10.1. Kết quả tổng tiền bằng nhau không tự chứng minh không có coupling

Một implementation có thể chứa `if (platform == WINDOWS)` và `else` nhưng cả hai nhánh tạm thời vẫn trả cùng giá trị. Vì vậy, kết quả số học bằng nhau **chỉ chứng minh hành vi trên dữ liệu đã kiểm thử**; muốn chứng minh ranh giới thiết kế cần kiểm tra mã và hướng phụ thuộc.

### 10.2. Không được “chuyển họ” giữa chừng mà không tạo lại màn hình

Trong ví dụ, factory được chọn khi `main()` chạy và mỗi `CheckoutScreen` giữ các sản phẩm đã tạo. Đổi JVM property sau khi màn hình đang tồn tại **không tự biến `WindowsButton` thành `MacButton`**.

Nếu ứng dụng yêu cầu đổi theme trong lúc chạy, cần quy định cách tạo lại màn hình, đổi toàn bộ nhóm sản phẩm hoặc dùng cơ chế theme động riêng. Không nên tạo Button mới theo macOS trong khi Checkbox cũ vẫn thuộc Windows.

### 10.3. Đúng loại sản phẩm chưa chắc đã đúng họ

Một factory có thể trả `WindowsButton` và `MacCheckbox` mà vẫn biên dịch vì các phương thức trả về `Button` và `Checkbox`. Vì vậy, kiểm thử tính **cùng họ** là phần cần thiết của việc chứng minh đổi biến thể đúng.

### 10.4. Abstract Factory không bảo đảm nghiệp vụ bất biến một cách tự động

Nếu sản phẩm nghiệp vụ có ý định hỗ trợ quy tắc giảm giá khác nhau theo quốc gia, mức thành viên hoặc hợp đồng, cùng dữ liệu đầu vào chưa chắc phải có cùng kết quả trên các biến thể ấy. Khi đó, test phải kiểm chứng các quy tắc đã được định nghĩa cho từng biến thể.

Trong bài học này, biến thể là **Windows/macOS của giao diện**, nên tính tiền không thay đổi là yêu cầu hợp lý và có thể kiểm chứng.

### 10.5. Không nên dùng enum của nền tảng xuyên suốt tầng nghiệp vụ

Dù enum an toàn hơn chuỗi tự do, truyền `Platform` vào mọi lớp không tự tạo ra tính độc lập. Thiết kế chỉ thật sự có lợi khi lớp sử dụng nhận được **đúng hợp đồng nó cần**, chẳng hạn `GUIFactory` hoặc các `Button` và `Checkbox` đã tạo, còn `CheckoutService` nhận dữ liệu đơn hàng.

### 10.6. Không cần Abstract Factory cho mọi thay đổi giao diện

Nếu Windows và macOS chỉ khác màu sắc và font nhưng có thể dùng một implementation widget chung với stylesheet, đổi theme có thể đơn giản hơn. Abstract Factory hữu ích khi cần tạo **nhiều sản phẩm thuộc những họ implementation tương thích**, đặc biệt khi hành vi hoặc cách tích hợp của từng sản phẩm thực sự khác nhau.

## 11. Bài tập đánh giá thiết kế

**Bài 1 — Thêm Linux.** Mở rộng enum, viết `LinuxButton`, `LinuxCheckbox`, `LinuxFactory` và bổ sung một nhánh vào `resolveFactory`. Hãy dự đoán kết quả `checkout(100_000, 3)`, viết phép kiểm thử mới xác nhận giao diện Linux và chỉ ra những lớp **không phải sửa**.

**Bài 2 — Kiểm tra lỗi trộn họ.** Cố ý cho `MacFactory.createCheckbox()` trả về `WindowsCheckbox`. Chạy `--test` và giải thích tại sao test factory cần kiểm tra kiểu concrete ngay cả khi mã client chỉ dùng interface.

**Bài 3 — Kiểm tra nhánh nghiệp vụ.** Bổ sung các trường hợp: `quantity=1`, `quantity=3`, `quantity=10`, `unitPrice=0` và `unitPrice=-1`. Xác nhận hai biến thể GUI trả về cùng kết quả hoặc cùng kiểu lỗi nghiệp vụ.

**Bài 4 — Cấu hình không hợp lệ.** Thử `-Dui.platform=ANDROID`. Giải thích vì sao ứng dụng nên từ chối thay vì âm thầm chọn Windows/macOS. Nếu sản phẩm cho phép fallback, hãy thiết kế chính sách và thêm test tương ứng.

**Bài 5 — Đánh giá ranh giới phụ thuộc.** Một đồng nghiệp thêm `String platform = System.getProperty("ui.platform")` vào `CheckoutService` để “dễ tùy chỉnh”. Hãy xác định lý do thay đổi đó không phù hợp với mục tiêu của bài, đồng thời đề xuất vị trí đúng để xử lý cấu hình.

### Câu hỏi tự kiểm tra

1. Ba bằng chứng nào cho thấy đổi cấu hình có hiệu lực nhưng không đổi kết quả nghiệp vụ?
2. Tại sao cần kiểm thử cả việc tạo đúng họ và kết quả sử dụng sản phẩm?
3. Đâu là khác biệt giữa **đổi biến thể đã có** và **thêm một biến thể hoàn toàn mới**?
4. Vì sao truyền `GUIFactory` qua constructor giúp đánh giá phụ thuộc dễ hơn?
5. Nếu hai lần chạy trả cùng tổng tiền, còn cần kiểm tra điều gì để khẳng định thiết kế không gắn logic nghiệp vụ với hệ điều hành?

## 12. Kết luận đánh giá

| Tiêu chí | Bằng chứng trong ví dụ | Kết luận trong phạm vi bài |
| --- | --- | --- |
| Chuyển họ qua cấu hình | Hai lệnh `-Dui.platform` chạy trên cùng bản biên dịch | Đạt |
| Factory cung cấp sản phẩm đúng họ | Kiểm tra `WindowsButton/WindowsCheckbox` và `MacButton/MacCheckbox` | Đạt khi test PASS |
| Biến thể tác động đến UI | Kết quả render Windows và macOS khác nhau | Đạt |
| Nghiệp vụ nhất quán | Cùng input trả `270000`; có thêm nhánh không giảm giá | Đạt với dữ liệu đã kiểm thử |
| Nghiệp vụ không phụ thuộc UI | `CheckoutService` chỉ dùng đơn giá và số lượng | Đạt theo cấu trúc mã được trình bày |
| Lỗi cấu hình được phát hiện | Biến thể không thuộc enum bị từ chối | Đạt khi test PASS |

**Điểm cốt lõi:** Một thiết kế Abstract Factory tốt cho bài toán này cho phép cấu hình quyết định **họ sản phẩm tại composition root**, để client thao tác qua **product interface** và để quy tắc nghiệp vụ tiếp tục nằm trong lớp nghiệp vụ độc lập. Kết luận cần được kiểm tra bằng **chạy hai cấu hình, test tạo đúng họ, test kết quả nghiệp vụ và review hướng phụ thuộc**, không chỉ dựa vào sự hiện diện của tên lớp `AbstractFactory`.


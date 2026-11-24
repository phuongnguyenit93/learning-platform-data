# So sánh chi phí thêm loại sản phẩm với chi phí thêm họ sản phẩm

> **Chương:** Thêm loại sản phẩm  
> **Học phần:** `SOFTWARE_DESIGN_DESIGN_PATTERN_CREATIONAL_ABSTRACT_FACTORY` — Học về Abstract Factory trong Design Pattern.  
> **Mục tiêu:** Phân biệt hai chiều mở rộng của Abstract Factory, ước lượng phạm vi sửa đổi, hiểu tác động đến khả năng tương thích API và chọn cách tổ chức factory phù hợp với hướng thay đổi có khả năng xảy ra.

## 1. Cùng là mở rộng, nhưng thay đổi theo hai chiều khác nhau

Trong một ứng dụng desktop đa nền tảng, màn hình cài đặt cần những thành phần giao diện có thể sử dụng theo **cùng phong cách**. Ví dụ ban đầu có hai loại sản phẩm:

- **Button:** nút Lưu cấu hình.
- **Checkbox:** tùy chọn Bật thông báo.

Ứng dụng có hai họ giao diện:

- **Windows:** `WindowsButton` và `WindowsCheckbox`.
- **macOS:** `MacButton` và `MacCheckbox`.

Sơ đồ ma trận ban đầu:

| Họ sản phẩm \ Loại sản phẩm | Button | Checkbox |
| --- | --- | --- |
| Windows | `WindowsButton` | `WindowsCheckbox` |
| macOS | `MacButton` | `MacCheckbox` |

Abstract Factory có thể biểu diễn ma trận này bằng một hợp đồng tạo đối tượng:

~~~java
interface UiFactory {
    Button createButton();
    Checkbox createCheckbox();
}
~~~

Trong đó `Button` và `Checkbox` là **product interface**; `WindowsFactory` và `MacFactory` là **concrete factory**. Mỗi concrete factory cung cấp các sản phẩm thuộc đúng họ của mình.

Giờ nhóm nhận hai yêu cầu độc lập:

1. **Yêu cầu A — Thêm họ sản phẩm:** triển khai giao diện cho **Linux**, vẫn chỉ cần Button và Checkbox.
2. **Yêu cầu B — Thêm loại sản phẩm:** cần thêm **Slider** điều chỉnh âm lượng trên **cả Windows lẫn macOS**.

Hai yêu cầu đều làm số lượng lớp tăng, nhưng **đụng vào các điểm mở rộng khác nhau**. Đây là nguyên nhân khiến chi phí bảo trì của chúng thường khác nhau.

## 2. Thêm họ là thêm hàng; thêm loại là thêm cột

### Yêu cầu A: thêm họ Linux

| Họ \ Loại | Button | Checkbox |
| --- | --- | --- |
| Windows | `WindowsButton` | `WindowsCheckbox` |
| macOS | `MacButton` | `MacCheckbox` |
| **Linux (mới)** | **`LinuxButton`** | **`LinuxCheckbox`** |

Thay đổi chính:

- Tạo `LinuxButton implements Button`.
- Tạo `LinuxCheckbox implements Checkbox`.
- Tạo `LinuxFactory implements UiFactory`, trả về hai concrete product trên.
- Đăng ký hoặc cấu hình lựa chọn Linux ở **composition root**.
- Kiểm thử LinuxFactory tạo đúng họ và các sản phẩm Linux đáp ứng hợp đồng.

**Không cần đổi chữ ký** của `UiFactory.createButton()` hoặc `UiFactory.createCheckbox()`. Hai concrete factory Windows/macOS đang hoạt động cũng không nhất thiết phải sửa.

### Yêu cầu B: thêm loại Slider

| Họ \ Loại | Button | Checkbox | Slider mới |
| --- | --- | --- | --- |
| Windows | `WindowsButton` | `WindowsCheckbox` | **`WindowsSlider`** |
| macOS | `MacButton` | `MacCheckbox` | **`MacSlider`** |

Thay đổi chính:

- Tạo **product interface mới** `Slider`.
- Tạo `WindowsSlider implements Slider` và `MacSlider implements Slider`.
- Thêm `Slider createSlider()` vào **`UiFactory`**.
- **Cập nhật cả `WindowsFactory` và `MacFactory`** để hiện thực phương thức mới.
- Cập nhật những client cần Slider; bổ sung kiểm thử hợp đồng và tính cùng họ.

Với thiết kế interface factory có các phương thức trừu tượng, **mọi concrete factory** đều phải cung cấp sản phẩm thuộc loại mới, kể cả khi một màn hình hiện tại chưa gọi `createSlider()`.

### So sánh nhanh

| Câu hỏi | Thêm họ Linux | Thêm loại Slider |
| --- | --- | --- |
| Đang mở rộng theo chiều nào? | Hàng của ma trận | Cột của ma trận |
| Cần product interface mới? | Thường không | Có |
| Cần concrete product mới? | Một cho **mỗi loại hiện có** | Một cho **mỗi họ hiện có** |
| Cần concrete factory mới? | Có | Thường không |
| Phải sửa `UiFactory`? | Thường không | Có, thêm phương thức tạo |
| Phải sửa **mọi** concrete factory cũ? | Thường không | Có nếu phương thức mới bắt buộc |
| Điểm chọn biến thể cần cập nhật? | Có thể có | Không nhất thiết |
| Rủi ro lớn | Đăng ký sai, factory trộn họ, tích hợp nền tảng mới | Phá hợp đồng factory, bỏ sót implementation, tương thích plugin |
| Client cũ có thể giữ nguyên? | Thường có | Thường có về lời gọi, nhưng factory đang dùng phải được nâng cấp |

Từ **“thường”** rất quan trọng: chi phí thực tế phụ thuộc vào kiến trúc, cơ chế đăng ký, phần mềm bên thứ ba và độ phức tạp của sản phẩm, không chỉ phụ thuộc vào tên mẫu thiết kế.

## 3. Đếm số đối tượng để hiểu phạm vi thay đổi

Đặt:

- `F` = số **họ sản phẩm** đã hỗ trợ.
- `P` = số **loại sản phẩm** trong mỗi họ.

Khi tất cả các họ cung cấp đầy đủ các loại sản phẩm, số **lớp ConcreteProduct** là:

\[
C = F \times P
\]

Giả sử mỗi loại có một product interface, và mỗi họ có một concrete factory triển khai cùng một factory interface.

### Khi thêm một họ sản phẩm

Hệ thống từ `F` thành `F + 1` họ; số ConcreteProduct tăng:

\[
\Delta C_{\text{thêm họ}} = (F+1)P-FP = P
\]

Tối thiểu về mặt cấu trúc, thường cần:

- `P` concrete product mới.
- `1` concrete factory mới.
- Đăng ký biến thể mới và kiểm thử tương ứng.

### Khi thêm một loại sản phẩm

Hệ thống từ `P` thành `P + 1` loại; số ConcreteProduct tăng:

\[
\Delta C_{\text{thêm loại}} = F(P+1)-FP = F
\]

Tối thiểu về mặt cấu trúc, thường cần:

- `1` product interface mới.
- `F` concrete product mới.
- `1` phương thức tạo mới trên abstract factory.
- `F` concrete factory hiện có được cập nhật.
- Kiểm thử hợp đồng mới ở từng họ.

### Ví dụ với số lượng cụ thể

| Số họ `F` | Số loại `P` | ConcreteProduct ban đầu | Thêm 1 họ: lớp ConcreteProduct mới | Thêm 1 loại: lớp ConcreteProduct mới |
| ---: | ---: | ---: | ---: | ---: |
| 2 | 2 | 4 | 2 | 2 |
| 3 | 5 | 15 | 5 | 3 |
| 8 | 3 | 24 | 3 | 8 |
| 10 | 12 | 120 | 12 | 10 |

**Không thể kết luận “thêm loại luôn đắt hơn thêm họ” chỉ vì cách Abstract Factory được mô tả.** Nếu có nhiều loại nhưng rất ít họ, thêm họ mới có thể cần viết nhiều ConcreteProduct hơn. Nếu có rất nhiều họ, thêm loại mới có thể làm việc cập nhật factory lan rộng.

Các con số này đo **phạm vi thay đổi cơ học**. Chúng chưa biểu diễn công sức tích hợp một widget hệ điều hành, mức độ phức tạp của hành vi, tài liệu API, sự phụ thuộc giữa các module, quy trình phát hành hoặc rủi ro dữ liệu.

## 4. Chi phí nào không hiện trong phép đếm lớp?

Có bốn nhóm chi phí nên đánh giá riêng.

| Nhóm chi phí | Thêm họ | Thêm loại |
| --- | --- | --- |
| **Mã triển khai** | Viết toàn bộ các sản phẩm của nền tảng mới và một factory mới | Viết một sản phẩm mới cho từng họ và mở rộng các factory hiện có |
| **Lan truyền thay đổi** | Chủ yếu ở họ mới và điểm chọn/đăng ký | Chạm vào interface chung cùng mọi implementation của interface đó |
| **Kiểm thử** | Test đầy đủ từng loại sản phẩm của họ mới | Test loại sản phẩm mới trong tất cả họ và test lại factory |
| **Phát hành/tương thích** | Có thể chỉ thêm plugin hoặc module mới | Có thể buộc các plugin/library cũ triển khai API mới |

Ví dụ, một `LinuxButton` dùng thư viện hệ thống khó tích hợp có thể tốn nhiều ngày hơn việc thêm một `Slider` rất đơn giản vào năm họ đang có. Ngược lại, thay đổi `UiFactory` đang được nhiều plugin bên ngoài implement có thể đòi hỏi phối hợp phiên bản phức tạp dù `Slider` dễ viết.

**Do đó, hãy dùng mô hình `F × P` để phát hiện diện tích thay đổi, sau đó đánh giá độ khó kỹ thuật và phụ thuộc phát hành để dự toán thực tế.**

## 5. Tại sao thêm loại tác động đến hợp đồng Abstract Factory?

Giả sử trước thay đổi, một interface có hai phương thức trừu tượng:

~~~java
interface UiFactory {
    Button createButton();
    Checkbox createCheckbox();
}
~~~

Các factory đã triển khai:

~~~java
final class WindowsFactory implements UiFactory {
    public Button createButton() {
        return new WindowsButton();
    }

    public Checkbox createCheckbox() {
        return new WindowsCheckbox();
    }
}
~~~

Nếu bổ sung `Slider`:

~~~java
interface Slider {
    void setValue(int value);
    int getValue();
    String render();
}

interface UiFactory {
    Button createButton();
    Checkbox createCheckbox();
    Slider createSlider(); // Thành phần mới của hợp đồng
}
~~~

Thì `WindowsFactory` ở trên **không còn là implementation đầy đủ** của interface khi biên dịch lại. Tương tự, `MacFactory` cũng phải bổ sung:

~~~java
final class WindowsFactory implements UiFactory {
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
~~~

Nếu không có `createSlider()`, trình biên dịch có thể báo lỗi tương đương:

~~~text
WindowsFactory is not abstract and does not override
abstract method createSlider() in UiFactory
~~~

Đây là **chi phí lan truyền hợp đồng** mà thao tác thêm một concrete factory cho **họ mới** thông thường không gây ra.

### Phân biệt tương thích nguồn và tương thích nhị phân trong Java

Thêm một phương thức trừu tượng vào Java interface:

- **Không tương thích nguồn** với những class concrete cũ khi biên dịch lại mà chúng chưa triển khai phương thức mới.
- **Có thể tương thích nhị phân theo quy tắc liên kết của Java** đối với các class cũ đã biên dịch trước đó; vì vậy không nên khẳng định chắc chắn mọi class cũ đều lỗi ngay khi load.
- **Có thể gây `AbstractMethodError` lúc chạy** nếu mã mới gọi phương thức mới trên một implementation cũ không cung cấp nó.

Ví dụ, ứng dụng sử dụng plugin đóng gói riêng có thể vẫn tải được một factory cũ, nhưng khi màn hình mới gọi `factory.createSlider()`, phiên bản factory ấy không đáp ứng hợp đồng vừa mở rộng. Do đó phải có kế hoạch phát hành, kiểm tra phiên bản API hoặc ràng buộc khả năng hỗ trợ.

### Vì sao `default createSlider()` chưa chắc là lời giải?

Đôi khi người viết API thử thêm:

~~~java
interface UiFactory {
    Button createButton();
    Checkbox createCheckbox();

    default Slider createSlider() {
        throw new UnsupportedOperationException("Slider not supported");
    }
}
~~~

Factory cũ không phải triển khai ngay, nhưng client gọi `createSlider()` có thể nhận lỗi thời gian chạy. Điều này **làm yếu lời hứa** rằng một `UiFactory` cung cấp toàn bộ họ sản phẩm.

Cách dùng `default` chỉ phù hợp nếu hợp đồng chấp nhận **tính năng tùy chọn** và client có chính sách xử lý khi sản phẩm không khả dụng. Nếu tất cả họ bắt buộc hỗ trợ Slider, nên cập nhật implementation và kiểm thử rõ ràng.

## 6. Thêm họ mới thường giữ ổn định hợp đồng cũ

Với cùng hợp đồng `UiFactory` có Button và Checkbox, khi thêm Linux chỉ cần hiện thực một factory mới:

~~~java
final class LinuxFactory implements UiFactory {
    @Override
    public Button createButton() {
        return new LinuxButton();
    }

    @Override
    public Checkbox createCheckbox() {
        return new LinuxCheckbox();
    }
}
~~~

`WindowsFactory` và `MacFactory` không cần biết `LinuxFactory` được tạo ra. Màn hình cũng có thể tiếp tục nhận `UiFactory` qua constructor:

~~~java
final class SettingsScreen {
    private final Button saveButton;
    private final Checkbox notifications;

    SettingsScreen(UiFactory factory) {
        this.saveButton = factory.createButton();
        this.notifications = factory.createCheckbox();
    }
}
~~~

Khi client đã sử dụng đúng interface, có thể truyền `new LinuxFactory()` mà không sửa `SettingsScreen`.

**Tuy nhiên, chọn hoặc công bố Linux vẫn có chi phí:**

- Nếu dùng `switch (platform)` tập trung, bổ sung nhánh Linux.
- Nếu dùng `EnumMap<Platform, Supplier<UiFactory>>`, cập nhật enum nếu cần và thêm đăng ký factory Linux.
- Nếu dùng `ServiceLoader<UiFactory>` và plugin độc lập, đóng gói provider Linux cùng descriptor/`provides`; host có thể giữ nguyên mã nếu dùng định danh mở và API tương thích.
- Nếu Linux yêu cầu thư viện bản địa (*native dependency*), quy trình build, đóng gói và kiểm thử nền tảng mới có thể phức tạp.

Vì vậy, mẫu Abstract Factory chủ yếu giảm **lan truyền thay đổi tới client**, chứ không loại bỏ công sức triển khai một nền tảng mới.

## 7. Theo dõi thay đổi bằng sơ đồ

~~~mermaid
flowchart LR
    subgraph Existing["Trước thay đổi: 2 họ × 2 loại"]
        EF["UiFactory"]
        EW["WindowsFactory"]
        EM["MacFactory"]
        EF --> EW
        EF --> EM
    end
    A["Thêm họ Linux"] --> LF["LinuxFactory"]
    LF --> LP["LinuxButton + LinuxCheckbox"]
    B["Thêm loại Slider"] --> SI["Slider interface"]
    B --> AF["UiFactory.createSlider()"]
    AF --> UW["WindowsFactory: sửa"]
    AF --> UM["MacFactory: sửa"]
    UW --> WS["WindowsSlider"]
    UM --> MS["MacSlider"]
~~~

Ở nhánh **thêm họ**, thay đổi tập trung vào một nhóm lớp mới và nơi đăng ký. Ở nhánh **thêm loại**, một phương thức của hợp đồng chung kéo theo việc sửa nhiều lớp hiện có.

### Ma trận sau khi thực hiện cả hai yêu cầu

| Họ \ Loại | Button | Checkbox | Slider |
| --- | --- | --- | --- |
| Windows | `WindowsButton` | `WindowsCheckbox` | `WindowsSlider` |
| macOS | `MacButton` | `MacCheckbox` | `MacSlider` |
| Linux | `LinuxButton` | `LinuxCheckbox` | `LinuxSlider` |

Lúc này hệ thống có `F = 3`, `P = 3`, tức `9` loại ConcreteProduct cụ thể theo ma trận. Mỗi concrete factory phải trả về đủ ba sản phẩm của họ mình.

## 8. Ví dụ Java tự chứa sau khi mở rộng theo cả hai chiều

Ví dụ sau minh họa trạng thái **sau khi** đã hỗ trợ Linux và Slider. Nó cho phép kiểm tra rằng client dùng chung interface và mỗi factory tạo đầy đủ ba sản phẩm của cùng họ.

Lưu thành `ExpansionCostDemo.java`:

~~~java
public class ExpansionCostDemo {
    interface Button {
        String render();
    }

    interface Checkbox {
        String render();
    }

    interface Slider {
        void setValue(int value);
        int getValue();
        String render();
    }

    interface UiFactory {
        Button createButton();
        Checkbox createCheckbox();
        Slider createSlider();
    }

    static final class WindowsButton implements Button {
        public String render() {
            return "Windows Button";
        }
    }

    static final class WindowsCheckbox implements Checkbox {
        public String render() {
            return "Windows Checkbox";
        }
    }

    static final class MacButton implements Button {
        public String render() {
            return "macOS Button";
        }
    }

    static final class MacCheckbox implements Checkbox {
        public String render() {
            return "macOS Checkbox";
        }
    }

    static final class LinuxButton implements Button {
        public String render() {
            return "Linux Button";
        }
    }

    static final class LinuxCheckbox implements Checkbox {
        public String render() {
            return "Linux Checkbox";
        }
    }

    // Có thể dùng lớp cơ sở chung để tái sử dụng quy tắc giá trị.
    static abstract class BaseSlider implements Slider {
        private int value;

        @Override
        public final void setValue(int value) {
            if (value < 0 || value > 100) {
                throw new IllegalArgumentException(
                        "Slider value must be between 0 and 100");
            }
            this.value = value;
        }

        @Override
        public final int getValue() {
            return value;
        }

        protected final String text(String family) {
            return family + " Slider(" + value + ")";
        }
    }

    static final class WindowsSlider extends BaseSlider {
        @Override
        public String render() {
            return text("Windows");
        }
    }

    static final class MacSlider extends BaseSlider {
        @Override
        public String render() {
            return text("macOS");
        }
    }

    static final class LinuxSlider extends BaseSlider {
        @Override
        public String render() {
            return text("Linux");
        }
    }

    static final class WindowsFactory implements UiFactory {
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
        public Button createButton() {
            return new MacButton();
        }

        public Checkbox createCheckbox() {
            return new MacCheckbox();
        }

        public Slider createSlider() {
            return new MacSlider();
        }
    }

    static final class LinuxFactory implements UiFactory {
        public Button createButton() {
            return new LinuxButton();
        }

        public Checkbox createCheckbox() {
            return new LinuxCheckbox();
        }

        public Slider createSlider() {
            return new LinuxSlider();
        }
    }

    static final class SettingsScreen {
        private final Button button;
        private final Checkbox checkbox;
        private final Slider volume;

        SettingsScreen(UiFactory factory) {
            button = factory.createButton();
            checkbox = factory.createCheckbox();
            volume = factory.createSlider();
            volume.setValue(60);
        }

        String render() {
            return button.render() + " | "
                    + checkbox.render() + " | "
                    + volume.render();
        }
    }

    // Chỉ ở phần kiểm thử mới cần biết các lớp cụ thể.
    static void verifyFamily(
            UiFactory factory,
            Class<? extends Button> expectedButton,
            Class<? extends Checkbox> expectedCheckbox,
            Class<? extends Slider> expectedSlider) {
        if (!expectedButton.isInstance(factory.createButton())
                || !expectedCheckbox.isInstance(factory.createCheckbox())
                || !expectedSlider.isInstance(factory.createSlider())) {
            throw new AssertionError("Factory mixes product families");
        }

        Slider slider = factory.createSlider();
        slider.setValue(75);
        if (slider.getValue() != 75) {
            throw new AssertionError("Slider contract was violated");
        }

        boolean rejected = false;
        try {
            slider.setValue(101);
        } catch (IllegalArgumentException expected) {
            rejected = true;
        }
        if (!rejected) {
            throw new AssertionError("Slider accepted invalid value");
        }
    }

    public static void main(String[] args) {
        UiFactory windows = new WindowsFactory();
        UiFactory mac = new MacFactory();
        UiFactory linux = new LinuxFactory();

        verifyFamily(windows, WindowsButton.class,
                WindowsCheckbox.class, WindowsSlider.class);
        verifyFamily(mac, MacButton.class,
                MacCheckbox.class, MacSlider.class);
        verifyFamily(linux, LinuxButton.class,
                LinuxCheckbox.class, LinuxSlider.class);

        System.out.println(new SettingsScreen(windows).render());
        System.out.println(new SettingsScreen(mac).render());
        System.out.println(new SettingsScreen(linux).render());
        System.out.println("PASS: 3 families");
    }
}
~~~

Biên dịch và chạy bằng JDK:

~~~bash
javac -encoding UTF-8 ExpansionCostDemo.java
java ExpansionCostDemo
~~~

Kết quả dự kiến:

~~~text
Windows Button | Windows Checkbox | Windows Slider(60)
macOS Button | macOS Checkbox | macOS Slider(60)
Linux Button | Linux Checkbox | Linux Slider(60)
PASS: 3 families
~~~

Đoạn mã đặt mỗi ConcreteProduct vào một lớp lồng nên có thể biên dịch bằng **một file Java**. Trong dự án thực, các lớp thường được chia thành module hoặc package riêng để thể hiện ranh giới API và triển khai.

Ba factory **cùng dùng một hợp đồng** gồm `createButton()`, `createCheckbox()` và `createSlider()`. Khi chuyển họ được truyền vào `SettingsScreen`, mã màn hình **không phải đổi**. Khi thêm loại Slider, mặt khác, **cả ba factory** trong trạng thái cuối đều phải biết tạo Slider.

## 9. Kiểm thử chi phí thay đổi: những phép kiểm nào phải bổ sung?

Số lượng class không đủ để đánh giá mức độ sẵn sàng của thay đổi. Cần nhìn vào kiểm thử đặc thù.

### Với thay đổi thêm họ Linux

- Kiểm tra `LinuxFactory.createButton()` trả `LinuxButton`.
- Kiểm tra `LinuxFactory.createCheckbox()` trả `LinuxCheckbox`.
- Nếu hệ thống đã có Slider, kiểm tra `LinuxFactory.createSlider()` trả `LinuxSlider`.
- Kiểm thử hành vi chung của các product interface cho các ConcreteProduct Linux.
- Kiểm thử bước chọn hoặc đăng ký Linux trong composition root.
- Kiểm thử hồi quy để bảo đảm việc thêm Linux không làm thay đổi Windows/macOS.

### Với thay đổi thêm loại Slider

- Kiểm thử `setValue(0)`, `setValue(100)` và đọc lại bằng `getValue()` ở **mọi họ**.
- Kiểm thử các giá trị ngoài khoảng, ví dụ `-1` và `101`.
- Kiểm tra `WindowsFactory`, `MacFactory` và bất kỳ factory nào khác đều tạo Slider đúng họ.
- Kiểm thử các client mới sử dụng Slider qua `UiFactory`.
- Xác minh việc thay đổi abstract factory không phá bản build của provider ở module/plugin khác.
- Kiểm thử hồi quy Button và Checkbox, đặc biệt sau khi cập nhật interface và wiring factory.

### Phân biệt kiểm thử sản phẩm và kiểm thử factory

| Kiểm thử | Trả lời câu hỏi |
| --- | --- |
| **Product contract test** | `Slider` ở mọi họ có giữ ràng buộc giá trị 0–100 không? |
| **Factory family test** | `WindowsFactory` có tạo đúng `WindowsSlider` không? |
| **Client integration test** | `SettingsScreen` nhận `UiFactory` có render được trọn bộ không? |
| **API compatibility test** | Plugin cũ có tương thích khi thêm `createSlider()` không? |

Một product có thể hoạt động đúng nhưng được **factory sai họ** tạo ra; một factory tạo đúng lớp nhưng implementation vẫn có lỗi hành vi. Vì vậy các kiểm thử này bổ sung cho nhau.

## 10. Dự toán bằng mô hình chi phí có thể điều chỉnh

Để tránh dùng những nhận định như “luôn dễ” hoặc “luôn khó”, có thể lập mô hình công sức theo **số hạng**. Đây là **mô hình đánh giá**, không phải thời gian chuẩn cho mọi dự án.

Đặt:

- `c_p`: công sức trung bình tạo và kiểm thử **một ConcreteProduct mới**.
- `c_f`: công sức tạo và kiểm thử **một ConcreteFactory mới**.
- `c_u`: công sức sửa và kiểm thử **một ConcreteFactory hiện có** khi thêm phương thức.
- `c_a`: công sức thiết kế, công bố và kiểm tra thay đổi **factory API**.
- `c_r`: công sức cấu hình/đăng ký biến thể mới, cùng các kiểm thử tích hợp liên quan.

Khi thêm **một họ**:

\[
E_{\text{họ}} \approx P \cdot c_p + c_f + c_r
\]

Khi thêm **một loại**:

\[
E_{\text{loại}} \approx F \cdot c_p + F \cdot c_u + c_a
\]

Đây là công thức **giản lược**. Kiểm thử hồi quy, tài liệu, tích hợp hệ điều hành, quy trình phát hành và nâng cấp plugin cần cộng thêm nếu dự án có những yêu cầu đó. Hệ số `c_p` cũng có thể khác rất lớn giữa các họ hoặc các loại sản phẩm; khi cần chính xác hơn, dùng tổng của từng công việc thay cho số trung bình.

### Ví dụ minh họa, không phải số liệu thực tế

Giả sử hệ thống có `F = 4` họ, `P = 3` loại; nhóm tự ước lượng:

- `c_p = 2` đơn vị công sức.
- `c_f = 2`.
- `c_r = 1`.
- `c_u = 1`.
- `c_a = 3`.

Khi đó:

\[
E_{\text{họ}} \approx 3(2)+2+1 = 9
\]

\[
E_{\text{loại}} \approx 4(2)+4(1)+3 = 15
\]

Với **những giả định này**, thêm một loại tốn nhiều hơn thêm một họ. Nhưng nếu nền tảng mới cần viết một hệ adapter GUI phức tạp, hoặc `P` tăng lên 20 loại, kết luận có thể đảo chiều.

Điểm hữu ích của công thức là làm lộ **giả định và hạng mục chi phí**, giúp nhóm thảo luận dựa trên đặc điểm dự án thay vì định kiến rằng một kiểu mở rộng luôn rẻ hơn kiểu còn lại.

## 11. Kết nối với Open/Closed Principle

Abstract Factory thường được đánh giá theo **Open/Closed Principle (OCP)**: thành phần nên mở cho mở rộng nhưng hạn chế sửa mã đã ổn định.

### Mở rộng theo họ

Khi thêm `LinuxFactory`, các interface `Button`, `Checkbox` và `UiFactory` thường **không đổi**. Các client chỉ sử dụng interface cũng không đổi. Vì vậy, Abstract Factory thường có tính **mở rộng tốt theo chiều họ sản phẩm**.

### Mở rộng theo loại

Khi thêm `Slider`, hợp đồng `UiFactory` phải mở rộng; mọi concrete factory cũ cần triển khai phương thức mới. Điều này cho thấy **mẫu thiết kế không đóng hoàn toàn trước mọi loại thay đổi**.

Một kiến trúc không thể tối ưu đồng thời cho mọi chiều mở rộng mà không có đánh đổi. Việc chọn Abstract Factory nên dựa vào **hướng thay đổi thường xảy ra và các bất biến phải giữ**:

- Thường thêm **nền tảng/họ** nhưng loại widget khá ổn định → Abstract Factory rất phù hợp.
- Thường thêm **loại widget** trong khi có nhiều họ triển khai → cân nhắc chi phí nâng cấp interface chung.
- Cả hai chiều đều thay đổi nhanh → đánh giá cách chia nhóm sản phẩm, versioning API và ranh giới plugin ngay từ đầu.

## 12. Khi nào nên tách factory hoặc thay đổi thiết kế?

Không nên tách interface chỉ để tránh sửa vài dòng mã. Việc phân nhỏ cũng làm tăng số phụ thuộc và có thể đánh mất ràng buộc tạo **cùng họ**.

Các lựa chọn có thể cân nhắc:

| Cách tiếp cận | Khi phù hợp | Đánh đổi |
| --- | --- | --- |
| **Một `UiFactory` có đủ phương thức** | Các loại sản phẩm thật sự là một bộ bắt buộc cùng họ | Thêm loại mới đòi hỏi cập nhật mọi concrete factory |
| **Interface mở rộng** `UiFactoryWithSlider extends UiFactory` | Slider chỉ có ở một số họ hoặc cần nâng cấp plugin theo giai đoạn | Client phải biết/có cách kiểm tra khả năng hỗ trợ interface mở rộng |
| **Nhiều factory nhỏ theo nhóm widget** | Các nhóm sản phẩm có vòng đời thay đổi độc lập | Cần cơ chế phối hợp để giữ tính nhất quán phong cách nếu dùng chúng cùng nhau |
| **Theme/stylesheet** | Khác biệt chỉ là màu, font, kích thước với cùng implementation | Không giải quyết tốt khác biệt về hành vi hoặc API nền tảng |
| **Factory registry theo loại sản phẩm** | Loại sản phẩm rất mở, được nạp như extension độc lập | Có thể mất bảo đảm compile-time rằng mọi họ có đủ tất cả loại; cần kiểm tra runtime |

Ví dụ, `UiFactoryWithSlider` có thể được dùng ở giai đoạn chuyển tiếp:

~~~java
interface UiFactoryWithSlider extends UiFactory {
    Slider createSlider();
}
~~~

Những plugin cũ chỉ triển khai `UiFactory` có thể tiếp tục phục vụ màn hình không cần Slider. Màn hình mới cần một factory triển khai `UiFactoryWithSlider` hoặc một chính sách từ chối/fallback rõ ràng.

Cách làm này **không miễn phí**: client và composition root cần xử lý khả năng một biến thể chưa hỗ trợ Slider. Nếu yêu cầu sản phẩm bắt buộc mọi họ đều có Slider, việc cập nhật toàn bộ factory theo hợp đồng chung có thể đơn giản và dễ kiểm soát hơn.

## 13. Checklist đánh giá trước khi triển khai một thay đổi

Khi nhóm phát triển nhận yêu cầu mới, hãy trả lời lần lượt:

1. **Thay đổi theo hàng hay theo cột?** Thêm họ mới hay thêm loại sản phẩm mới?
2. **Có bao nhiêu họ `F` và loại `P` hiện tại?** Ma trận có đầy đủ các cặp không?
3. **Cần tạo bao nhiêu ConcreteProduct?** Với thêm họ là khoảng `P`; thêm loại là khoảng `F`.
4. **Có sửa abstract factory interface không?** Nếu có, những module nào đang implement interface đó?
5. **Có provider/plugin được phát hành độc lập không?** Cần kế hoạch tương thích và versioning API nào?
6. **Tính cùng họ được bảo đảm ở đâu?** Mỗi factory có trả đúng các ConcreteProduct của mình không?
7. **Mã client có đang phụ thuộc vào lớp cụ thể không?** Nếu có, phải sửa thêm những điểm nào?
8. **Bộ kiểm thử nào cần bổ sung?** Product contract, factory wiring, integration, hồi quy?
9. **Có thể phân biệt chức năng bắt buộc và tùy chọn không?** Tránh dùng `UnsupportedOperationException` thay cho một hợp đồng không rõ ràng.
10. **Các hệ số chi phí có hợp với dự án không?** Nền tảng mới có công cụ native khó tích hợp, hay loại sản phẩm mới ảnh hưởng đến nhiều plugin?

Khi trả lời được những câu hỏi trên, nhóm có cơ sở để chọn phương án và ước lượng tác động.

## 14. Bài tập vận dụng

### Bài 1 — Đếm thay đổi

Một ứng dụng có **6 họ**, mỗi họ có **4 loại sản phẩm**; mọi factory đều implement chung một interface.

- Có bao nhiêu ConcreteProduct trước thay đổi?
- Thêm họ thứ 7 cần tối thiểu bao nhiêu ConcreteProduct mới?
- Thêm loại sản phẩm thứ 5 cần bao nhiêu ConcreteProduct mới?
- Với thay đổi nào cần sửa **6 concrete factory** cũ?

**Gợi ý:** Ban đầu `6 × 4 = 24` ConcreteProduct; thêm họ cần `4` ConcreteProduct; thêm loại cần `6` ConcreteProduct và cập nhật cả `6` factory cũ.

### Bài 2 — Phân tích tương thích API

Ứng dụng phát hành `ui-api.jar` với `UiFactory` chỉ có Button và Checkbox, còn các khách hàng phát triển plugin factory riêng. Nhà cung cấp muốn thêm `Slider createSlider()`.

Hãy phân biệt:

- Điều gì xảy ra khi khách hàng **biên dịch lại** concrete factory cũ với API mới?
- Điều gì có thể xảy ra nếu chương trình mới gọi `createSlider()` trên **class plugin cũ đã biên dịch**?
- Bạn sẽ chọn nâng cấp đồng loạt, interface mở rộng hay `default` trong hoàn cảnh nào?

### Bài 3 — So sánh hướng thay đổi bằng dữ liệu

Giả sử `F = 3`, `P = 12`, `c_p = 1`, `c_f = 2`, `c_r = 1`, `c_u = 1` và `c_a = 2`.

Tính `E_{\text{họ}}` và `E_{\text{loại}}` theo công thức ở mục 10. Giải thích vì sao kết quả có thể khác trực giác “thêm loại lúc nào cũng tốn hơn”.

### Bài 4 — Nhận diện lựa chọn thiết kế

Một ứng dụng có 20 theme chỉ khác màu sắc và có hai loại widget. Một ứng dụng khác có ba hệ điều hành, mỗi hệ điều hành dùng API widget riêng với 15 loại thành phần. Có nên dùng cùng một chiến lược Abstract Factory cho cả hai? Hãy chỉ ra điều kiện khiến theme là đủ và điều kiện cần ConcreteProduct theo nền tảng.

### Bài 5 — Kiểm thử sau thay đổi

Dùng ví dụ `ExpansionCostDemo`, cố ý sửa `MacFactory.createSlider()` thành trả `new WindowsSlider()`. Dự đoán test nào phát hiện sai phạm. Sau đó trả đúng `MacSlider` và thử đặt giá trị 101 để kiểm tra quy tắc chung.

## 15. Câu hỏi tự kiểm tra và kết luận

1. Vì sao thêm một họ sản phẩm thường không đòi hỏi thay đổi `UiFactory`?
2. Vì sao thêm một loại sản phẩm có thể làm mọi concrete factory cũ phải sửa?
3. Công thức `F × P` đo được điều gì và **không** đo được điều gì?
4. Vì sao không thể kết luận chi phí chỉ bằng số lớp mới?
5. Rủi ro lớn của việc thêm phương thức trừu tượng vào interface được plugin bên ngoài implement là gì?
6. Làm thế nào kiểm thử cả hành vi Slider lẫn tính nhất quán họ sản phẩm?
7. Khi nào nên cân nhắc interface mở rộng hoặc nhiều factory nhỏ?

**Kết luận:** Trong Abstract Factory, **thêm họ sản phẩm** thường có chi phí tập trung vào **một concrete factory và các sản phẩm thuộc họ mới**; **thêm loại sản phẩm** thường có chi phí lan tới **hợp đồng abstract factory và mọi concrete factory hiện có**. Số ConcreteProduct cần thêm lần lượt là khoảng `P` và `F` với ma trận đầy đủ. Chi phí triển khai cuối cùng còn phụ thuộc độ khó hành vi, tích hợp, kiểm thử và tương thích API. Chọn thiết kế tốt nghĩa là hiểu chiều thay đổi nào đáng tối ưu và bảo đảm mọi họ sản phẩm tiếp tục đáp ứng hợp đồng chung.


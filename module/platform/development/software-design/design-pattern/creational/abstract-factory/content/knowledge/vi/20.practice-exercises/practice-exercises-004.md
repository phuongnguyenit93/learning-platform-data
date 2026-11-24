# Thêm Slider vào mọi họ và so sánh tác động với việc thêm biến thể

## 1. Bối cảnh và mục tiêu thực hành

Trong mẫu thiết kế khởi tạo **Abstract Factory**, một factory cung cấp các sản phẩm thuộc **cùng một họ** thông qua các product interface chung. Ví dụ, ứng dụng có hai họ giao diện **Light** và **Dark**; mỗi họ đều tạo được `Button` và `Checkbox`.

Yêu cầu mới xuất hiện theo hai hướng khác nhau:

- **Thêm loại sản phẩm:** Màn hình cài đặt cần thêm `Slider` để điều chỉnh âm lượng. **Mọi họ đang hỗ trợ** phải tạo được Slider phù hợp với giao diện của mình.
- **Thêm biến thể (họ mới):** Sau khi Slider hoạt động, ứng dụng hỗ trợ thêm giao diện **High Contrast** để tăng khả năng phân biệt các thành phần. Họ mới phải cung cấp đủ Button, Checkbox **và** Slider.

Hai thay đổi tưởng giống nhau vì đều có thêm class, nhưng phạm vi ảnh hưởng khác nhau. Bài thực hành này yêu cầu trực tiếp sửa mô hình, chạy test và **so sánh thay đổi khi thêm một trục sản phẩm với khi thêm một trục họ**.

Sau bài học, bạn cần có thể:

1. Mở rộng `AbstractFactory` và mọi `ConcreteFactory` khi thêm **một product type**.
2. Định nghĩa hợp đồng của `Slider` để các `ConcreteProduct` thực hiện nhất quán.
3. Thêm một concrete factory và các sản phẩm tương ứng khi thêm **family variant**.
4. Giữ client phụ thuộc interface và không tự khởi tạo concrete product.
5. Dùng ma trận kiểm thử để chứng minh từng họ cung cấp đủ loại sản phẩm và các product cùng họ tương thích.
6. Giải thích phần nào của thiết kế được giữ ổn định, phần nào phải chỉnh sửa và vì sao.

**Phạm vi ví dụ:** Java 17+ và JUnit 5. Đây là một ứng dụng dòng lệnh mô phỏng thành phần giao diện, nên `render()` trả chuỗi để kiểm thử; trong ứng dụng thực, product có thể tạo widget, DOM hoặc thành phần đồ họa.

## 2. Đề bài và quy tắc chấp nhận

Một `SettingsScreen` đang dùng `UiFactory` để tạo `Button` và `Checkbox`. Yêu cầu mới: thêm Slider điều chỉnh âm lượng từ **0 đến 100**, mặc định **50**.

### 2.1. Hợp đồng của Slider

| Tình huống | Hành vi bắt buộc |
| --- | --- |
| Vừa được tạo | `value() == 50` |
| `setValue(0)` | `value() == 0` |
| `setValue(100)` | `value() == 100` |
| `setValue(n)` với `0 <= n <= 100` | Lưu đúng `n` |
| `setValue(-1)` hoặc `setValue(101)` | Ném `IllegalArgumentException`, không đổi giá trị trước đó |
| `theme()` | Đúng họ của factory đã tạo |
| `render()` | Biểu diễn họ và giá trị hiện tại, ví dụ `LightSlider(80)` |

Với `UiFactory`, mỗi lời gọi `createSlider()` phải trả **một Slider mới, có trạng thái độc lập**. Đây là yêu cầu của bài tập; một Abstract Factory ngoài thực tế cũng có thể trả đối tượng dùng chung nếu hợp đồng cho phép.

### 2.2. Điều kiện hoàn thành

- [ ] `LightUiFactory` tạo đủ `LightButton`, `LightCheckbox`, `LightSlider`.
- [ ] `DarkUiFactory` tạo đủ `DarkButton`, `DarkCheckbox`, `DarkSlider`.
- [ ] `SettingsScreen` chỉ phụ thuộc `UiFactory`, `Button`, `Checkbox` và `Slider`.
- [ ] Không có lệnh `new LightSlider()` hay `new DarkSlider()` trong client.
- [ ] Slider của cả hai họ tuân thủ hợp đồng 0–100, mặc định 50.
- [ ] Mỗi lần tạo Slider cho trạng thái độc lập.
- [ ] Sau khi thêm `HighContrastUiFactory`, client vẫn không đổi logic dựng và render màn hình.
- [ ] Test chạy với **cả ba họ** và kiểm tra đúng theme của tất cả loại sản phẩm.
- [ ] Có bảng mô tả rõ những file/lớp chịu tác động theo từng hướng mở rộng.

## 3. Mô hình ban đầu: hai họ, hai loại sản phẩm

Giả sử mỗi họ có Button và Checkbox như sơ đồ:

~~~mermaid
classDiagram
    class UiFactory {
        <<interface>>
        +createButton() Button
        +createCheckbox() Checkbox
    }
    class Button {
        <<interface>>
        +render() String
    }
    class Checkbox {
        <<interface>>
        +render() String
    }
    class LightUiFactory
    class DarkUiFactory
    class LightButton
    class LightCheckbox
    class DarkButton
    class DarkCheckbox
    class SettingsScreen

    UiFactory <|.. LightUiFactory
    UiFactory <|.. DarkUiFactory
    Button <|.. LightButton
    Button <|.. DarkButton
    Checkbox <|.. LightCheckbox
    Checkbox <|.. DarkCheckbox
    LightUiFactory ..> LightButton : creates
    LightUiFactory ..> LightCheckbox : creates
    DarkUiFactory ..> DarkButton : creates
    DarkUiFactory ..> DarkCheckbox : creates
    SettingsScreen --> UiFactory : receives
~~~

Để có điểm xuất phát thực thi được, lưu đoạn dưới đây trong `BeforeSlider.java`. Các concrete product chỉ khác họ và cách hiển thị để giữ trọng tâm ở luồng khởi tạo.

~~~java
public final class BeforeSlider {
    enum Theme { LIGHT, DARK }

    interface UiProduct {
        Theme theme();
        String render();
    }

    interface Button extends UiProduct {}
    interface Checkbox extends UiProduct {}

    interface UiFactory {
        Button createButton();
        Checkbox createCheckbox();
    }

    record LightButton() implements Button {
        public Theme theme() { return Theme.LIGHT; }
        public String render() { return "LightButton"; }
    }

    record LightCheckbox() implements Checkbox {
        public Theme theme() { return Theme.LIGHT; }
        public String render() { return "LightCheckbox"; }
    }

    record DarkButton() implements Button {
        public Theme theme() { return Theme.DARK; }
        public String render() { return "DarkButton"; }
    }

    record DarkCheckbox() implements Checkbox {
        public Theme theme() { return Theme.DARK; }
        public String render() { return "DarkCheckbox"; }
    }

    static final class LightUiFactory implements UiFactory {
        public Button createButton() { return new LightButton(); }
        public Checkbox createCheckbox() { return new LightCheckbox(); }
    }

    static final class DarkUiFactory implements UiFactory {
        public Button createButton() { return new DarkButton(); }
        public Checkbox createCheckbox() { return new DarkCheckbox(); }
    }

    static final class SettingsScreen {
        private final UiFactory factory;

        SettingsScreen(UiFactory factory) {
            this.factory = factory;
        }

        String render() {
            Button button = factory.createButton();
            Checkbox checkbox = factory.createCheckbox();

            return button.render() + " | " + checkbox.render();
        }
    }

    public static void main(String[] args) {
        System.out.println(new SettingsScreen(new LightUiFactory()).render());
        System.out.println(new SettingsScreen(new DarkUiFactory()).render());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac BeforeSlider.java
java BeforeSlider
~~~

Kết quả dự kiến:

~~~text
LightButton | LightCheckbox
DarkButton | DarkCheckbox
~~~

Lúc này có **2 họ × 2 loại sản phẩm = 4 tổ hợp sản phẩm cụ thể**. Cả hai factory thực hiện cùng interface, còn client sử dụng sản phẩm thông qua abstraction.

## 4. Phần A — Thêm Slider vào **mọi họ hiện có**

Đây là thay đổi theo **chiều loại sản phẩm**. Trước khi xem lời giải, hãy tự thực hiện các bước dưới đây trên một bản sao của mô hình `BeforeSlider`.

### Bước A1. Tạo abstract product Slider

Thêm interface kế thừa `UiProduct`:

~~~java
interface Slider extends UiProduct {
    int value();
    void setValue(int value);
}
~~~

**Câu hỏi:** Vì sao `Slider` không nên kế thừa `Button`? Bởi vì Slider có hợp đồng trạng thái và thao tác riêng; mối quan hệ của chúng là **cùng thuộc họ sản phẩm**, không phải “Slider là một Button”.

### Bước A2. Mở rộng abstract factory

Từ interface cũ:

~~~java
interface UiFactory {
    Button createButton();
    Checkbox createCheckbox();
}
~~~

Sửa thành:

~~~java
interface UiFactory {
    Button createButton();
    Checkbox createCheckbox();
    Slider createSlider();
}
~~~

Đây là điểm thay đổi quan trọng: mọi concrete factory triển khai trực tiếp `UiFactory` giờ **phải cung cấp `createSlider()`**. Nếu chưa bổ sung phương thức, trình biên dịch Java báo class chưa thực hiện đầy đủ interface. Trong nhiều hệ thống, kiểu lỗi biên dịch này hữu ích vì chỉ rõ nơi cần hoàn thiện họ.

### Bước A3. Hiện thực Slider của Light và Dark

Tạo `LightSlider` và `DarkSlider` tuân theo **cùng hợp đồng** giá trị 0–100 nhưng có cách hiển thị theo họ. Có thể dùng một abstract base class chia sẻ thao tác kiểm tra phạm vi, miễn mỗi concrete Slider vẫn báo đúng theme.

Ví dụ hai phương thức factory sau là yêu cầu bắt buộc:

~~~java
// Trong LightUiFactory
@Override
public Slider createSlider() {
    return new LightSlider();
}

// Trong DarkUiFactory
@Override
public Slider createSlider() {
    return new DarkSlider();
}
~~~

**Lỗi cần tránh:** trả `new DarkSlider()` bên trong `LightUiFactory` chỉ vì DarkSlider cũng thực hiện interface `Slider`. Đúng interface về kiểu **không bảo đảm đúng họ**.

### Bước A4. Cập nhật client để sử dụng sản phẩm mới

`SettingsScreen` gọi thêm `factory.createSlider()`, đặt âm lượng bằng `slider.setValue(80)` rồi render cả ba sản phẩm. Client không biết `LightSlider` hay `DarkSlider` là lớp nào.

Đầu ra mong đợi sau Phần A:

~~~text
LightButton | LightCheckbox | LightSlider(80)
DarkButton | DarkCheckbox | DarkSlider(80)
~~~

**Yêu cầu thảo luận A:** Liệt kê những interface, concrete factory, concrete product, test và client thực sự cần sửa. Giải thích tại sao `UiFactory` buộc thay đổi khi thêm một loại sản phẩm bắt buộc.

## 5. Phần B — Thêm **biến thể High Contrast** sau khi đã có Slider

Đây là thay đổi theo **chiều họ sản phẩm**. Giữ nguyên bộ interface `UiFactory`, `Button`, `Checkbox`, `Slider` đã hoàn thiện ở Phần A.

Thêm:

- `HighContrastButton` thực hiện `Button`.
- `HighContrastCheckbox` thực hiện `Checkbox`.
- `HighContrastSlider` thực hiện `Slider` với cùng hợp đồng giá trị 0–100.
- `HighContrastUiFactory` thực hiện `UiFactory` và trả về đúng ba sản phẩm trên.

Nếu ví dụ dùng enum `Theme`, bổ sung `HIGH_CONTRAST`. Đăng ký factory mới tại composition root hoặc nơi chọn họ từ cấu hình.

~~~java
UiFactory factory = switch (themeChoice) {
    case "light" -> new LightUiFactory();
    case "dark" -> new DarkUiFactory();
    case "high-contrast" -> new HighContrastUiFactory();
    default -> throw new IllegalArgumentException("Unknown theme");
};

SettingsScreen screen = new SettingsScreen(factory);
System.out.println(screen.render(80));
~~~

Đoạn này mô tả **điểm chọn factory**, trong đó `themeChoice` là biến đầu vào giả định. Sau khi chọn xong, client vẫn nhận `UiFactory` và chạy cùng luồng.

Đầu ra kỳ vọng cho ba họ:

~~~text
LightButton | LightCheckbox | LightSlider(80)
DarkButton | DarkCheckbox | DarkSlider(80)
HighContrastButton | HighContrastCheckbox | HighContrastSlider(80)
~~~

**Yêu cầu thảo luận B:** Tại sao có thể thêm cả họ High Contrast mà không sửa danh sách phương thức trong `UiFactory` và không đưa `new HighContrastSlider()` vào `SettingsScreen`? Những nơi **vẫn phải thay đổi** là gì?

## 6. Lời giải tham khảo Java 17: hai chiều mở rộng cùng tồn tại

Sau khi tự làm Phần A và B, dùng một chương trình hoàn chỉnh sau để đối chiếu. Lưu dưới tên `AfterSlider.java`. Để tập trung vào Abstract Factory, phần hiển thị giả lập được trả dưới dạng chuỗi; `BaseSlider` chỉ tái sử dụng logic kiểm tra phạm vi giữa các concrete product.

~~~java
import java.util.List;
import java.util.Objects;

public final class AfterSlider {

    enum Theme { LIGHT, DARK, HIGH_CONTRAST }

    // Các abstract product
    interface UiProduct {
        Theme theme();
        String render();
    }

    interface Button extends UiProduct {}
    interface Checkbox extends UiProduct {}

    interface Slider extends UiProduct {
        int value();
        void setValue(int value);
    }

    // Abstract factory: mọi họ cung cấp đủ ba loại sản phẩm
    interface UiFactory {
        Button createButton();
        Checkbox createCheckbox();
        Slider createSlider();
    }

    // Những product sẵn có ở họ Light
    record LightButton() implements Button {
        public Theme theme() { return Theme.LIGHT; }
        public String render() { return "LightButton"; }
    }

    record LightCheckbox() implements Checkbox {
        public Theme theme() { return Theme.LIGHT; }
        public String render() { return "LightCheckbox"; }
    }

    // Những product sẵn có ở họ Dark
    record DarkButton() implements Button {
        public Theme theme() { return Theme.DARK; }
        public String render() { return "DarkButton"; }
    }

    record DarkCheckbox() implements Checkbox {
        public Theme theme() { return Theme.DARK; }
        public String render() { return "DarkCheckbox"; }
    }

    // Chia sẻ hợp đồng giá trị, không chia sẻ nhận diện họ
    static abstract class BaseSlider implements Slider {
        private int value = 50;

        @Override
        public final int value() {
            return value;
        }

        @Override
        public final void setValue(int value) {
            if (value < 0 || value > 100) {
                throw new IllegalArgumentException(
                    "Slider value must be in [0, 100]: " + value
                );
            }
            this.value = value;
        }
    }

    static final class LightSlider extends BaseSlider {
        @Override
        public Theme theme() { return Theme.LIGHT; }

        @Override
        public String render() {
            return "LightSlider(" + value() + ")";
        }
    }

    static final class DarkSlider extends BaseSlider {
        @Override
        public Theme theme() { return Theme.DARK; }

        @Override
        public String render() {
            return "DarkSlider(" + value() + ")";
        }
    }

    // Họ mới: High Contrast
    record HighContrastButton() implements Button {
        public Theme theme() { return Theme.HIGH_CONTRAST; }
        public String render() { return "HighContrastButton"; }
    }

    record HighContrastCheckbox() implements Checkbox {
        public Theme theme() { return Theme.HIGH_CONTRAST; }
        public String render() { return "HighContrastCheckbox"; }
    }

    static final class HighContrastSlider extends BaseSlider {
        @Override
        public Theme theme() { return Theme.HIGH_CONTRAST; }

        @Override
        public String render() {
            return "HighContrastSlider(" + value() + ")";
        }
    }

    // Hai concrete factory đã mở rộng ở Phần A
    static final class LightUiFactory implements UiFactory {
        @Override
        public Button createButton() { return new LightButton(); }

        @Override
        public Checkbox createCheckbox() { return new LightCheckbox(); }

        @Override
        public Slider createSlider() { return new LightSlider(); }
    }

    static final class DarkUiFactory implements UiFactory {
        @Override
        public Button createButton() { return new DarkButton(); }

        @Override
        public Checkbox createCheckbox() { return new DarkCheckbox(); }

        @Override
        public Slider createSlider() { return new DarkSlider(); }
    }

    // Concrete factory được thêm ở Phần B
    static final class HighContrastUiFactory implements UiFactory {
        @Override
        public Button createButton() {
            return new HighContrastButton();
        }

        @Override
        public Checkbox createCheckbox() {
            return new HighContrastCheckbox();
        }

        @Override
        public Slider createSlider() {
            return new HighContrastSlider();
        }
    }

    // Client không cần biết lớp cụ thể của từng sản phẩm
    static final class SettingsScreen {
        private final UiFactory factory;

        SettingsScreen(UiFactory factory) {
            this.factory = Objects.requireNonNull(factory);
        }

        String render(int volume) {
            Button button = factory.createButton();
            Checkbox checkbox = factory.createCheckbox();
            Slider slider = factory.createSlider();

            slider.setValue(volume);

            return button.render()
                + " | " + checkbox.render()
                + " | " + slider.render();
        }
    }

    public static void main(String[] args) {
        List<UiFactory> factories = List.of(
            new LightUiFactory(),
            new DarkUiFactory(),
            new HighContrastUiFactory()
        );

        for (UiFactory factory : factories) {
            System.out.println(new SettingsScreen(factory).render(80));
        }
    }
}
~~~

Chạy:

~~~bash
javac AfterSlider.java
java AfterSlider
~~~

Output dự kiến là ba dòng Light, Dark, HighContrast ở mục 5. Có ba điều đáng chú ý khi đọc lời giải:

1. `UiFactory` chỉ đổi **một lần ở Phần A** khi thêm loại sản phẩm. Phần B giữ nguyên contract ba phương thức tạo.
2. `LightUiFactory` và `DarkUiFactory` đều bổ sung `createSlider()`. Khi thêm `HighContrastUiFactory` ở Phần B, factory mới triển khai luôn đủ ba phương thức có sẵn.
3. Client biết thêm Slider vì **chức năng màn hình đã đổi**, nhưng client vẫn chỉ gọi `UiFactory` và `Slider`. Sau đó, thêm High Contrast không đòi sửa thân `SettingsScreen.render()`.

Để giảm trùng lặp, `BaseSlider` cung cấp state và kiểm tra phạm vi cho ba concrete Slider. Đây là lựa chọn triển khai, **không phải điều kiện bắt buộc của Abstract Factory**; mỗi họ có thể hiện thực Slider bằng kỹ thuật khác nhau, miễn tuân thủ product interface.

## 7. Kiểm thử: một bộ hợp đồng cho mọi họ

Đặt file `AfterSliderTest.java` trong cùng package với `AfterSlider.java` và cấu hình JUnit Jupiter 5 cùng module tham số hóa `junit-jupiter-params`. Trong bài tập này, bộ test phải xác minh cả **hợp đồng Slider**, **tính nhất quán họ** và **khả năng tái sử dụng client**.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.function.Supplier;
import java.util.stream.Stream;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.MethodSource;

class AfterSliderTest {

    record FamilyCase(
        String name,
        AfterSlider.Theme expected,
        Supplier<AfterSlider.UiFactory> factory,
        String expectedOutput
    ) {
        @Override
        public String toString() { return name; }
    }

    static Stream<FamilyCase> families() {
        return Stream.of(
            new FamilyCase(
                "Light",
                AfterSlider.Theme.LIGHT,
                AfterSlider.LightUiFactory::new,
                "LightButton | LightCheckbox | LightSlider(80)"
            ),
            new FamilyCase(
                "Dark",
                AfterSlider.Theme.DARK,
                AfterSlider.DarkUiFactory::new,
                "DarkButton | DarkCheckbox | DarkSlider(80)"
            ),
            new FamilyCase(
                "High Contrast",
                AfterSlider.Theme.HIGH_CONTRAST,
                AfterSlider.HighContrastUiFactory::new,
                "HighContrastButton | HighContrastCheckbox"
                    + " | HighContrastSlider(80)"
            )
        );
    }

    @ParameterizedTest(name = "{0} / Slider contract")
    @MethodSource("families")
    void slider_contract_is_shared_by_all_families(FamilyCase c) {
        AfterSlider.UiFactory factory = c.factory().get();
        AfterSlider.Slider slider = factory.createSlider();

        assertNotNull(slider);
        assertEquals(c.expected(), slider.theme());
        assertEquals(50, slider.value());

        slider.setValue(0);
        assertEquals(0, slider.value());

        slider.setValue(100);
        assertEquals(100, slider.value());

        assertThrows(IllegalArgumentException.class, () ->
            slider.setValue(-1));
        assertEquals(100, slider.value());

        assertThrows(IllegalArgumentException.class, () ->
            slider.setValue(101));
        assertEquals(100, slider.value());
    }

    @ParameterizedTest(name = "{0} / Factory completeness")
    @MethodSource("families")
    void factory_returns_complete_consistent_family(FamilyCase c) {
        AfterSlider.UiFactory factory = c.factory().get();

        AfterSlider.Button button = factory.createButton();
        AfterSlider.Checkbox checkbox = factory.createCheckbox();
        AfterSlider.Slider firstSlider = factory.createSlider();
        AfterSlider.Slider secondSlider = factory.createSlider();

        assertNotNull(button);
        assertNotNull(checkbox);
        assertNotNull(firstSlider);
        assertNotNull(secondSlider);

        assertEquals(c.expected(), button.theme());
        assertEquals(c.expected(), checkbox.theme());
        assertEquals(c.expected(), firstSlider.theme());
        assertEquals(c.expected(), secondSlider.theme());

        assertNotSame(firstSlider, secondSlider);
        firstSlider.setValue(90);
        assertEquals(50, secondSlider.value(),
            "Hai Slider mới không được chia sẻ state");
    }

    @ParameterizedTest(name = "{0} / SettingsScreen integration")
    @MethodSource("families")
    void same_client_supports_each_product_family(FamilyCase c) {
        AfterSlider.SettingsScreen screen =
            new AfterSlider.SettingsScreen(c.factory().get());

        assertEquals(c.expectedOutput(), screen.render(80));
    }
}
~~~

Với **3 họ** và **3 phương thức kiểm thử tham số hóa**, dự kiến có **9 lượt test**. Khi đang ở Phần A, có thể tạm chạy cùng suite trên hai `FactoryCase` Light và Dark trước khi bổ sung High Contrast.

Các test cố ý dùng **giá trị mong đợi độc lập** từ fixture. Nếu chỉ so `button.theme()` với `slider.theme()`, cả hai có thể cùng báo sai họ mà test vẫn xanh.

### 7.1. Ma trận bao phủ

| Họ | Button | Checkbox | Slider 0–100 | Slider độc lập | Client render |
| --- | :---: | :---: | :---: | :---: | :---: |
| Light | ✓ | ✓ | ✓ | ✓ | ✓ |
| Dark | ✓ | ✓ | ✓ | ✓ | ✓ |
| High Contrast | ✓ | ✓ | ✓ | ✓ | ✓ |

Dấu ✓ là **yêu cầu cần kiểm thử**, không phải kết quả chạy đã được ghi nhận. Khi thực thi thực tế, thay bằng trạng thái PASS/FAIL và lưu bằng chứng từ JUnit hoặc CI.

### 7.2. Kiểm tra chất lượng test bằng lỗi có chủ đích

| Cách làm sai | Test dự kiến bắt lỗi |
| --- | --- |
| `LightUiFactory.createSlider()` trả `new DarkSlider()` | `factory_returns_complete_consistent_family` và `slider_contract_is_shared_by_all_families` |
| `DarkSlider` khởi tạo giá trị 0 thay vì 50 | `slider_contract_is_shared_by_all_families` |
| `HighContrastSlider.setValue(101)` tự ép về 100 | Test yêu cầu ném `IllegalArgumentException` |
| Hai lần `createSlider()` cùng trả một instance | `assertNotSame(firstSlider, secondSlider)` |
| Client trực tiếp tạo `new LightSlider()` | Test họ Dark/High Contrast có thể cho output sai; cần thêm code review để xác nhận phụ thuộc abstraction |
| Client bỏ qua `Slider` | `same_client_supports_each_product_family` trả output thiếu phần Slider |

Test bảo vệ hành vi, nhưng kiểm tra **client không phụ thuộc concrete class** vẫn cần static analysis/code review vì một số vi phạm kiến trúc có thể tình cờ tạo ra output đúng.

## 8. So sánh tác động: thêm product type và thêm family variant

Bảng dưới thể hiện hai lần thay đổi **sau khi hệ thống đã có Light/Dark cùng Button/Checkbox**.

| Thành phần chịu tác động | Phần A: thêm **Slider** | Phần B: thêm **High Contrast** |
| --- | --- | --- |
| Abstract product interface | **Thêm `Slider`** | Dùng lại `Button`, `Checkbox`, `Slider` |
| Abstract factory interface | **Thêm `createSlider()`** | Không đổi |
| Concrete factory hiện có | **Sửa cả Light và Dark** | Không cần sửa Light/Dark |
| Concrete product | Thêm `LightSlider` và `DarkSlider` | Thêm cả ba product của High Contrast |
| Concrete factory mới | Không cần | **Thêm `HighContrastUiFactory`** |
| Client | Sửa nơi hiển thị Slider do yêu cầu nghiệp vụ mới | Không cần sửa logic tạo/sử dụng sản phẩm |
| Điểm chọn cấu hình | Thường giữ nguyên các họ cũ | Thêm lựa chọn High Contrast/đăng ký DI |
| Contract test | Bổ sung hợp đồng Slider và test mọi họ | Đăng ký họ mới để chạy lại **mọi** contract hiện có |
| Rủi ro chính | Một họ thiếu phương thức hoặc Slider hành xử khác contract | Factory mới thiếu loại hoặc trộn sản phẩm khác họ |

### 8.1. Phân tích số tổ hợp

Gọi:

- `F` = số họ sản phẩm (product families).
- `P` = số loại sản phẩm (product types).

Nếu mỗi họ bắt buộc có **đủ mọi loại**, có tối thiểu **`F × P` cặp family–product** cần kiểm tra về mặt hành vi và khả năng tạo. Con số này **không nhất thiết bằng số class** nếu implementation tái sử dụng thành phần chung.

| Thời điểm | Số họ `F` | Số loại `P` | Cặp family–product |
| --- | ---: | ---: | ---: |
| Ban đầu | 2 | 2 | 4 |
| Sau Phần A: thêm Slider | 2 | 3 | 6 |
| Sau Phần B: thêm High Contrast | 3 | 3 | 9 |

Quy luật tổng quát:

- **Thêm một loại sản phẩm** khi có `F` họ làm số cặp tăng thêm **`F`** và thường buộc sửa `F` concrete factory hiện có.
- **Thêm một họ mới** khi có `P` loại làm số cặp tăng thêm **`P`**; thường chỉ thêm một concrete factory và `P` concrete product, không buộc đổi các factory cũ.

Abstract Factory tạo thuận lợi cho việc **thêm họ mới** khi bộ loại sản phẩm đã ổn định. Ngược lại, thêm **loại sản phẩm mới** là thay đổi lan rộng vì lời hứa của mọi factory phải được mở rộng. Đây là một trade-off thiết kế, không phải lỗi riêng của Java.

### 8.2. Nhìn qua nguyên tắc Open/Closed

Ở mức **client**, việc thay họ từ Light sang High Contrast có thể đạt tính mở rộng mà không sửa logic của client: một concrete factory mới được tiêm vào `UiFactory`.

Ở mức **abstract factory interface**, việc thêm Slider thay đổi hợp đồng mà các concrete factory đã triển khai, nên code hiện có phải sửa. Vì thế không nên diễn giải rằng “Abstract Factory bảo đảm mọi mở rộng đều không sửa code cũ”.

Câu nhận xét chính xác hơn: **Abstract Factory phù hợp với hệ thống mà tập product type tương đối ổn định, còn số family variant có thể tăng**. Nếu thường xuyên thêm product type, cần cân nhắc chi phí sửa tất cả factory.

## 9. Hai hướng mở rộng dưới dạng sơ đồ quyết định

~~~mermaid
flowchart TD
    R["Có yêu cầu mới?"] --> Q{"Thêm loại product hay thêm family?"}
    Q -->|"Thêm Slider"| P1["Định nghĩa Slider interface"]
    P1 --> P2["Thêm UiFactory.createSlider()"]
    P2 --> P3["Cập nhật tất cả concrete factory"]
    P3 --> P4["Test Slider trên mọi họ"]
    Q -->|"Thêm High Contrast"| F1["Tạo mọi concrete product của họ mới"]
    F1 --> F2["Tạo HighContrastUiFactory"]
    F2 --> F3["Đăng ký chọn/tiêm factory mới"]
    F3 --> F4["Chạy lại contract test cho họ mới"]
~~~

Điểm xuất phát khác nhau dẫn đến thay đổi khác nhau. Vì thế khi review PR, cần xem yêu cầu đang mở rộng **trục nào** và kiểm tra phần code tương ứng.

## 10. Những cách xử lý dễ gây lỗi

### 10.1. Để Slider tự chọn theme qua biến toàn cục

~~~java
// Không phù hợp khi cần bảo đảm một màn hình dùng cùng một họ:
Slider slider = new GlobalThemeSlider(); // tự đọc global theme
~~~

Nếu theme toàn cục đổi giữa lúc factory tạo Button và Slider, các sản phẩm có thể khác họ. Trong mô hình bài tập, factory đã được chọn mang trách nhiệm cấp sản phẩm đồng nhất: `LightUiFactory.createSlider()` trả `LightSlider`, tương tự với các họ khác.

Trong hệ thống cho phép thay theme động, cần xác định vòng đời của màn hình và tái tạo/cập nhật sản phẩm nhất quán theo một cấu hình được chụp tại thời điểm sử dụng.

### 10.2. Thêm Slider vào client bằng cách kiểm tra kiểu factory

~~~java
// Cách triển khai làm client biết các concrete family:
if (factory instanceof LightUiFactory) {
    slider = new LightSlider();
} else {
    slider = new DarkSlider();
}
~~~

Khi thêm High Contrast, phải bổ sung một nhánh nữa, thậm chí dễ tạo sai product. Dùng `factory.createSlider()` giúp trách nhiệm chọn concrete product nằm đúng ở concrete factory.

### 10.3. Dùng `createProduct("slider")` thay mọi phương thức có kiểu

Một factory chung có thể trả `Object` theo chuỗi:

~~~java
Object product = factory.createProduct("slider");
~~~

Cách này có thể tránh sửa interface khi thêm tên sản phẩm, nhưng đánh đổi khả năng kiểm tra kiểu lúc biên dịch, khả năng tự khám phá API và tính đầy đủ của họ. Client phải cast/kiểm tra lỗi khi chạy. Chỉ dùng registry động khi sản phẩm thật sự được định danh động và có chiến lược kiểm soát contract phù hợp; không mặc định đây là lời giải tốt hơn cho bài tập.

### 10.4. Thêm Slider như một khả năng tùy chọn không có chủ đích

Nếu `UiFactory.createSlider()` trả `null` trong họ không hỗ trợ, bài tập thất bại vì yêu cầu là **mọi họ đều có Slider**. Trong hệ thống thật, nếu tính năng chỉ dành cho một số họ, hãy thể hiện khả năng tùy chọn một cách minh bạch qua interface/capability riêng, hoặc cấu hình hỗ trợ được kiểm tra trước. Đừng âm thầm nới lỏng hợp đồng bắt buộc.

### 10.5. Quên mở rộng bộ test khi thêm một họ

Nếu source dữ liệu test vẫn chỉ chứa Light và Dark, tất cả test cũ có thể xanh dù `HighContrastUiFactory` trả sản phẩm sai. Nên có danh sách family chính thức và cơ chế bảo đảm test fixture bao phủ danh sách đó. Ví dụ test ở mục 7 đã thêm High Contrast để tránh bỏ sót.

## 11. Bài tập nâng cao: thiết kế để giảm chi phí thay đổi

Sau khi hoàn thành phần bắt buộc, chọn một trong hai yêu cầu nâng cao:

**Tình huống 1 — thêm loại sản phẩm thứ tư: `Dialog`.** Hãy dự đoán số cặp family–product từ 9 tăng lên bao nhiêu, những concrete factory nào cần sửa và cần thêm test gì. Sau đó thử hiện thực `Dialog` cho cả Light, Dark và High Contrast.

**Tình huống 2 — Slider không phải khả năng của mọi họ.** Giả sử có họ `TextOnly` chỉ tạo Button/Checkbox. Hãy đề xuất cách biểu diễn rằng Slider là tính năng tùy chọn, chẳng hạn tách `SliderCapableFactory` với một khả năng được công bố rõ ràng. Phân tích cách client kiểm tra capability và nguy cơ đánh mất lời hứa “mọi factory tạo đủ cả họ” nếu nới lỏng interface bừa bãi.

Gợi ý cho tình huống 1: từ `F = 3, P = 3` tăng thành `F = 3, P = 4`, tức **12 cặp**. Đây là một lần mở rộng theo chiều product type, nên phải bổ sung `createDialog()` cho cả ba concrete factory hiện có.

Với tình huống 2, không có một câu trả lời duy nhất. Chọn thiết kế dựa trên hợp đồng nghiệp vụ: nếu Slider **bắt buộc cho mọi màn hình**, hãy giữ contract chung; nếu thực sự tùy chọn, mô hình hóa riêng capability để client xử lý tường minh.

## 12. Câu hỏi phản tư sau khi hoàn thành

1. Vì sao khi thêm Slider, trình biên dịch yêu cầu các concrete factory hiện có phải thay đổi?
2. Vì sao khi thêm High Contrast, `UiFactory` không cần thêm phương thức?
3. Nếu `LightUiFactory.createSlider()` trả `DarkSlider`, Java có thể vẫn biên dịch không? Kiểm thử nào bắt lỗi?
4. Tại sao `SettingsScreen` có thể cần sửa khi thêm product type nhưng giữ nguyên khi thêm family variant?
5. Công thức `F × P` mô tả điều gì? Vì sao không nên dùng nó để khẳng định luôn có đúng `F × P` class trong production?
6. Có nên thêm `createSlider()` vào mọi factory nếu chỉ một họ cần Slider? Bạn sẽ thay đổi đặc tả hoặc cấu trúc interface thế nào?
7. Những bài test nào cần mở rộng khi thêm một family hoàn toàn mới?
8. Khi nào Abstract Factory không còn là lựa chọn thuận lợi vì product types thay đổi liên tục?

## 13. Đáp án trọng tâm và tiêu chí tự chấm

| Tiêu chí | Điểm gợi ý | Điều cần kiểm chứng |
| --- | ---: | --- |
| Thêm Slider đúng hợp đồng | 25 | Mặc định 50, biên 0/100, từ chối ngoài biên, giữ state |
| Đồng nhất họ Light/Dark | 20 | Concrete factories trả đúng Slider của từng họ |
| Thêm High Contrast đầy đủ | 20 | Có đủ Button/Checkbox/Slider và factory mới |
| Client chỉ dùng abstraction | 15 | Không tự khởi tạo concrete products hoặc kiểm tra concrete factory |
| Bộ test đầy đủ | 15 | Contract, factory completeness, state independence, client integration |
| Phân tích hai hướng mở rộng | 5 | Nêu đúng phạm vi sửa đổi và tổng tổ hợp 4 → 6 → 9 |
| **Tổng** | **100** | |

Tự kiểm tra kiến thức quan trọng nhất:

- **Thêm product type (Slider):** thêm interface sản phẩm, thêm phương thức vào abstract factory, bổ sung concrete product và sửa **mọi concrete factory hiện có**. Client liên quan đến tính năng Slider cũng cần dùng sản phẩm mới.
- **Thêm family variant (High Contrast):** thêm bộ concrete product và concrete factory mới, đăng ký lựa chọn factory, mở rộng dữ liệu kiểm thử; **không cần** sửa abstract factory hoặc logic client vốn chỉ dựa trên interface chung.
- **Độ phủ:** từ **4** tổ hợp ban đầu thành **6** sau khi thêm Slider, thành **9** sau khi thêm High Contrast.
- **Giá trị của mẫu thiết kế:** giữ client độc lập với lớp cụ thể và bảo đảm mỗi factory cung cấp một **họ sản phẩm nhất quán**. Chi phí của tính nhất quán này là sự phối hợp thay đổi rộng khi tập loại sản phẩm bắt buộc được mở rộng.

## 14. Ghi nhớ

Bài thực hành này minh họa hai hướng tiến hóa của Abstract Factory: **thêm loại sản phẩm** và **thêm họ sản phẩm**. Với Slider mới, hợp đồng của factory thay đổi và mọi họ phải được cập nhật; với High Contrast mới, hợp đồng cũ được tái sử dụng và chủ yếu bổ sung triển khai. Hãy luôn kiểm thử đủ **family × product type**, giữ client phụ thuộc abstraction và đánh giá tần suất thay đổi của từng trục trước khi chọn thiết kế cho hệ thống thực tế.

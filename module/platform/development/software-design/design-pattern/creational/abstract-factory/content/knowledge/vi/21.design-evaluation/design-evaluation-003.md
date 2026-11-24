# Kiểm tra mỗi họ đáp ứng đầy đủ hợp đồng và quy tắc tương thích

**Chương:** Đánh giá thiết kế  
**Chuyên đề:** `SOFTWARE_DESIGN_DESIGN_PATTERN_CREATIONAL_ABSTRACT_FACTORY` — Học về abstract factory trong design pattern.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Đánh giá từng **họ sản phẩm** trong Abstract Factory theo cả **hợp đồng interface** và **quy tắc tương thích** giữa các sản phẩm.
- Phân biệt những lỗi Java phát hiện khi biên dịch với những lỗi chỉ bộc lộ khi chạy hoặc quan sát trải nghiệm.
- Thiết lập ma trận kiểm tra để không bỏ sót sản phẩm của họ `Light`, `Dark` hoặc `HighContrast`.
- Viết một bộ kiểm tra hợp đồng (`contract tests`) dùng chung cho nhiều factory cụ thể.
- Phân tích các trường hợp factory trả về `null`, sai họ, trộn họ hoặc tạo sản phẩm đúng kiểu nhưng sai quy ước hành vi.

## 1. Bài toán đánh giá: đủ sản phẩm vẫn chưa chắc đúng

Giả sử ứng dụng Java dùng **Abstract Factory** để tạo thành phần giao diện theo ba họ: `Light`, `Dark` và `HighContrast`. Mỗi họ cần hai loại sản phẩm: `Button` và `Checkbox`.

| Họ sản phẩm | `Button` bắt buộc | `Checkbox` bắt buộc | Factory |
| --- | --- | --- | --- |
| Light | `LightButton` | `LightCheckbox` | `LightUiFactory` |
| Dark | `DarkButton` | `DarkCheckbox` | `DarkUiFactory` |
| HighContrast | `HighContrastButton` | `HighContrastCheckbox` | `HighContrastUiFactory` |

**Cột** biểu thị loại sản phẩm; **hàng** biểu thị họ sản phẩm. Để một họ hợp lệ, factory của họ đó phải tạo được mọi loại sản phẩm được hứa trong hợp đồng, và các sản phẩm phải phối hợp đúng quy tắc mà ứng dụng kỳ vọng.

Ví dụ, `DarkUiFactory` có hai phương thức `createButton()` và `createCheckbox()`. Trình biên dịch có thể xác nhận hai phương thức được triển khai với kiểu trả về hợp lệ. Tuy nhiên, đoạn sau vẫn có thể biên dịch:

```java
// Giả sử các class và interface đã được định nghĩa trong dự án.
final class BrokenDarkFactory implements UiFactory {
    public Button createButton() {
        return new DarkButton();
    }

    public Checkbox createCheckbox() {
        return new LightCheckbox(); // Đúng interface, sai họ sản phẩm.
    }
}
```

`LightCheckbox` vẫn là một `Checkbox`, vì vậy **type checker không tự hiểu** quy tắc “mọi sản phẩm của Dark phải thuộc họ Dark”. Tương tự, `createCheckbox()` có thể trả về `null` mà không bị trình biên dịch từ chối. Đó là lý do cần đánh giá thiết kế ở **nhiều lớp hợp đồng**.

## 2. Ba lớp hợp đồng cần kiểm tra

| Lớp kiểm tra | Câu hỏi chính | Cơ chế phát hiện |
| --- | --- | --- |
| **Hợp đồng cấu trúc / kiểu dữ liệu** | Factory có triển khai đủ phương thức? Kiểu trả về có thỏa `Button`, `Checkbox`? | Trình biên dịch Java kiểm tra `implements UiFactory`. |
| **Hợp đồng tạo sản phẩm / họ sản phẩm** | Mỗi phương thức có trả về sản phẩm hợp lệ? Có `null`? Sản phẩm có đúng họ được chọn? | Contract test chạy trên từng concrete factory. |
| **Hợp đồng tương thích / hành vi** | Các sản phẩm cùng họ có sử dụng quy ước chung? Trạng thái chọn, focus, nhãn và hành vi có hoạt động như yêu cầu? | Test hành vi, kiểm tra thuộc tính thiết kế và thử trên giao diện thực tế. |

### 2.1. Kiểm tra hợp đồng interface

```java
interface Button {
    String render(String label);
}

interface Checkbox {
    String render(String label, boolean checked);
}

interface UiFactory {
    Button createButton();
    Checkbox createCheckbox();
}
```

Một lớp khai báo `implements UiFactory` nhưng thiếu `createCheckbox()` sẽ không biên dịch nếu lớp đó là lớp cụ thể (`concrete class`). Khi bổ sung phương thức trừu tượng mới vào `UiFactory`, các factory cụ thể cũng phải cung cấp implementation phù hợp. Đây là cơ chế tốt để ngăn **thiếu phương thức**.

Nhưng compiler không mặc nhiên bảo đảm phương thức **trả về giá trị khác `null`**, **thuộc đúng họ**, hoặc **hoạt động đúng quy tắc nghiệp vụ**. Những điều đó cần được đưa thành tiêu chí kiểm tra riêng.

### 2.2. Kiểm tra tính đầy đủ của từng họ

Với mỗi hàng trong ma trận, cần kiểm tra:

1. Tạo được một factory thuộc họ đó.
2. Gọi được **mọi** phương thức tạo đã công bố trong interface.
3. Mỗi phương thức trả về sản phẩm sử dụng được theo hợp đồng; với ví dụ này, kết quả không được `null`.
4. Mỗi sản phẩm thuộc **họ được yêu cầu**, không phải họ khác.
5. Các sản phẩm có thể được dùng cùng nhau theo quy tắc của ứng dụng.

Chỉ nhìn tên lớp `DarkUiFactory` hoặc thấy các phương thức `createButton()`, `createCheckbox()` là chưa đủ. Phải kiểm tra **giá trị được trả về**.

### 2.3. Kiểm tra tương thích của các sản phẩm cùng họ

“Tương thích” phụ thuộc vào miền ứng dụng. Trong một bộ giao diện, có thể cần:

- **Bộ token dùng chung**: sản phẩm dùng đúng họ giao diện, bộ màu chữ/nền và quy ước focus đã được thống nhất.
- **Trạng thái và tương tác**: checkbox thể hiện rõ trạng thái checked/unchecked; nút có nhãn, hỗ trợ hành động đúng theo cách client kỳ vọng.
- **Cách phối hợp**: nút và checkbox không tạo ra trải nghiệm lẫn lộn giữa Light, Dark và HighContrast.
- **Khả năng thay thế**: client chỉ dùng interface vẫn làm việc với tất cả các họ.

Không nên kiểm tra cứng rằng **mọi thuộc tính của button bằng mọi thuộc tính của checkbox**. Hai loại thành phần có thể có nền, đường viền hoặc kích thước riêng mà vẫn cùng một họ. Chỉ các quy tắc **đã được định nghĩa là dùng chung** mới cần bằng nhau; đặc thù từng loại sản phẩm phải được kiểm tra theo hợp đồng riêng của loại đó.

## 3. Cách xây dựng một ma trận contract test

Một ma trận test có thể bắt đầu từ cùng những tiêu chí đối với mọi factory:

| Tiêu chí | Light | Dark | HighContrast |
| --- | --- | --- | --- |
| `createButton()` trả về non-null `Button` | ✓ cần kiểm tra | ✓ cần kiểm tra | ✓ cần kiểm tra |
| `createCheckbox()` trả về non-null `Checkbox` | ✓ cần kiểm tra | ✓ cần kiểm tra | ✓ cần kiểm tra |
| Button thuộc họ được chọn | ✓ | ✓ | ✓ |
| Checkbox thuộc họ được chọn | ✓ | ✓ | ✓ |
| Hai sản phẩm cùng tuân thủ token chung của họ | ✓ | ✓ | ✓ |
| Button render được nhãn hợp lệ | ✓ | ✓ | ✓ |
| Checkbox biểu diễn được cả hai trạng thái | ✓ | ✓ | ✓ |
| Các kiểm tra giao diện thực tế theo đặc tả của họ | ✓ | ✓ | ✓ |

Dấu ✓ ở đây là **mục tiêu kiểm tra**, không phải khẳng định chương trình đã chạy pass. Nếu sau này thêm loại sản phẩm `Dialog`, hãy **thêm cột/tiêu chí cho Dialog ở mọi họ**. Nếu thêm họ `HighContrast` vào hệ thống đang có Light và Dark, hãy chạy cùng bộ kiểm tra cho factory mới; đồng thời chạy lại kiểm tra của những họ cũ để bắt hồi quy.

Ý tưởng quan trọng là **dùng một bộ tiêu chí chung** thay vì viết mỗi factory một tập test hoàn toàn khác nhau. Khi thay đổi hợp đồng, chỉ cần cập nhật tiêu chí ở một nơi rồi áp dụng trên tất cả factory được hỗ trợ.

## 4. Ví dụ Java hoàn chỉnh: kiểm tra mọi factory theo một hợp đồng

Ví dụ sau dùng giao diện console để tập trung vào đánh giá thiết kế. Đối tượng `Palette` đại diện **các token chung của cả họ**, gồm tên họ, màu chữ, màu bề mặt và màu focus. Button và Checkbox có thể có cách hiển thị riêng, nhưng đều phải tham chiếu các token chung phù hợp.

Để dễ chạy thử, toàn bộ ví dụ nằm trong file **`FactoryContractEvaluationDemo.java`**, dùng Java 8 trở lên. Các phép kiểm tra ném `IllegalStateException` khi vi phạm hợp đồng; cách này hoạt động cả khi JVM **không bật** từ khóa `assert`.

```java
import java.util.Objects;

// 1. Những họ mà ứng dụng hỗ trợ.
enum Family {
    LIGHT, DARK, HIGH_CONTRAST
}

// 2. Quy ước chung giữa các sản phẩm cùng họ.
final class Palette {
    final Family family;
    final String foreground;
    final String background;
    final String focus;

    Palette(Family family, String foreground, String background, String focus) {
        this.family = Objects.requireNonNull(family, "family");
        this.foreground = Objects.requireNonNull(foreground, "foreground");
        this.background = Objects.requireNonNull(background, "background");
        this.focus = Objects.requireNonNull(focus, "focus");
    }

    boolean sameSharedTokens(Palette other) {
        return other != null
            && family == other.family
            && foreground.equals(other.foreground)
            && background.equals(other.background)
            && focus.equals(other.focus);
    }
}

final class Palettes {
    static final Palette LIGHT =
        new Palette(Family.LIGHT, "#111111", "#FFFFFF", "#1769AA");
    static final Palette DARK =
        new Palette(Family.DARK, "#FFFFFF", "#202124", "#8AB4F8");
    static final Palette HIGH_CONTRAST =
        new Palette(Family.HIGH_CONTRAST, "#FFFFFF", "#000000", "#00FFFF");

    private Palettes() { }
}

// 3. Hợp đồng loại sản phẩm.
interface Button {
    Palette palette();
    String render(String label);
}

interface Checkbox {
    Palette palette();
    String render(String label, boolean checked);
}

// 4. Hợp đồng abstract factory: mọi họ phải cung cấp đủ hai sản phẩm.
interface UiFactory {
    Button createButton();
    Checkbox createCheckbox();
}

// Lớp nền chỉ gom hành vi lặp lại cho ví dụ console.
abstract class BaseButton implements Button {
    private final Palette palette;

    BaseButton(Palette palette) {
        this.palette = Objects.requireNonNull(palette, "palette");
    }

    @Override
    public final Palette palette() {
        return palette;
    }

    @Override
    public final String render(String label) {
        return "[" + palette.family + "] Button: " + label;
    }
}

abstract class BaseCheckbox implements Checkbox {
    private final Palette palette;

    BaseCheckbox(Palette palette) {
        this.palette = Objects.requireNonNull(palette, "palette");
    }

    @Override
    public final Palette palette() {
        return palette;
    }

    @Override
    public final String render(String label, boolean checked) {
        return "[" + palette.family + "] Checkbox: " + label
            + " " + (checked ? "[x]" : "[ ]");
    }
}

// 5. Concrete products của ba họ.
final class LightButton extends BaseButton {
    LightButton() { super(Palettes.LIGHT); }
}

final class LightCheckbox extends BaseCheckbox {
    LightCheckbox() { super(Palettes.LIGHT); }
}

final class DarkButton extends BaseButton {
    DarkButton() { super(Palettes.DARK); }
}

final class DarkCheckbox extends BaseCheckbox {
    DarkCheckbox() { super(Palettes.DARK); }
}

final class HighContrastButton extends BaseButton {
    HighContrastButton() { super(Palettes.HIGH_CONTRAST); }
}

final class HighContrastCheckbox extends BaseCheckbox {
    HighContrastCheckbox() { super(Palettes.HIGH_CONTRAST); }
}

// 6. Concrete factories: mỗi factory tạo trọn một họ.
final class LightUiFactory implements UiFactory {
    @Override
    public Button createButton() {
        return new LightButton();
    }

    @Override
    public Checkbox createCheckbox() {
        return new LightCheckbox();
    }
}

final class DarkUiFactory implements UiFactory {
    @Override
    public Button createButton() {
        return new DarkButton();
    }

    @Override
    public Checkbox createCheckbox() {
        return new DarkCheckbox();
    }
}

final class HighContrastUiFactory implements UiFactory {
    @Override
    public Button createButton() {
        return new HighContrastButton();
    }

    @Override
    public Checkbox createCheckbox() {
        return new HighContrastCheckbox();
    }
}

// 7. Hai factory lỗi: vẫn implements UiFactory và vẫn biên dịch.
final class MixedDarkFactory implements UiFactory {
    @Override
    public Button createButton() {
        return new DarkButton();
    }

    @Override
    public Checkbox createCheckbox() {
        return new LightCheckbox(); // Lỗi: trộn Light với Dark.
    }
}

final class MissingDarkFactory implements UiFactory {
    @Override
    public Button createButton() {
        return new DarkButton();
    }

    @Override
    public Checkbox createCheckbox() {
        return null; // Lỗi: phương thức tồn tại nhưng thiếu sản phẩm.
    }
}

// 8. Bộ contract test dùng chung cho mọi factory.
public final class FactoryContractEvaluationDemo {
    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }

    private static Palette expectedPalette(Family family) {
        switch (family) {
            case LIGHT:
                return Palettes.LIGHT;
            case DARK:
                return Palettes.DARK;
            case HIGH_CONTRAST:
                return Palettes.HIGH_CONTRAST;
            default:
                throw new IllegalArgumentException("Họ không hỗ trợ: " + family);
        }
    }

    private static UiFactory factoryFor(Family family) {
        switch (family) {
            case LIGHT:
                return new LightUiFactory();
            case DARK:
                return new DarkUiFactory();
            case HIGH_CONTRAST:
                return new HighContrastUiFactory();
            default:
                throw new IllegalArgumentException("Họ không hỗ trợ: " + family);
        }
    }

    static void verifyFactoryContract(Family expected, UiFactory factory) {
        Objects.requireNonNull(expected, "expected");
        Objects.requireNonNull(factory, "factory");

        // Kiểm tra tính đầy đủ: mọi sản phẩm trong hợp đồng đều tồn tại.
        Button button = factory.createButton();
        Checkbox checkbox = factory.createCheckbox();
        require(button != null, "Thiếu Button cho " + expected);
        require(checkbox != null, "Thiếu Checkbox cho " + expected);

        Palette buttonPalette = button.palette();
        Palette checkboxPalette = checkbox.palette();
        require(buttonPalette != null, "Button thiếu palette");
        require(checkboxPalette != null, "Checkbox thiếu palette");

        // Kiểm tra cùng họ và đúng họ mà nơi lắp ráp đã chọn.
        require(buttonPalette.family == expected
                && checkboxPalette.family == expected,
                "Trộn họ hoặc trả về sai họ: " + expected);

        // Kiểm tra các token chung của từng sản phẩm theo đặc tả.
        Palette contract = expectedPalette(expected);
        require(buttonPalette.sameSharedTokens(contract),
                "Button sai token chung của " + expected);
        require(checkboxPalette.sameSharedTokens(contract),
                "Checkbox sai token chung của " + expected);

        // Kiểm tra hành vi tối thiểu mà client sẽ sử dụng.
        String buttonText = button.render("Lưu");
        String checkedText = checkbox.render("Nhận thông báo", true);
        String uncheckedText = checkbox.render("Nhận thông báo", false);
        require(buttonText != null && buttonText.contains("Lưu"),
                "Button không hiển thị nhãn");
        require(checkedText != null && checkedText.contains("[x]"),
                "Checkbox không biểu diễn checked");
        require(uncheckedText != null && uncheckedText.contains("[ ]"),
                "Checkbox không biểu diễn unchecked");

        System.out.println("PASS " + expected);
    }

    private static void verifyExpectedFailure(
            String name, Family expected, UiFactory faultyFactory) {
        try {
            verifyFactoryContract(expected, faultyFactory);
            throw new AssertionError("Không phát hiện lỗi của " + name);
        } catch (IllegalStateException violation) {
            System.out.println("DETECTED " + name + ": "
                    + violation.getMessage());
        }
    }

    public static void main(String[] args) {
        // Mỗi họ hợp lệ đều chạy cùng một bộ tiêu chí.
        for (Family family : Family.values()) {
            verifyFactoryContract(family, factoryFor(family));
        }

        // Minh họa bộ tiêu chí bắt được các lỗi không lộ lúc biên dịch.
        verifyExpectedFailure("mixed", Family.DARK, new MixedDarkFactory());
        verifyExpectedFailure("missing", Family.DARK, new MissingDarkFactory());
    }
}
```

### Biên dịch và quan sát

Lưu file, sau đó chạy:

```bash
javac -encoding UTF-8 FactoryContractEvaluationDemo.java
java FactoryContractEvaluationDemo
```

Đầu ra dự kiến:

```text
PASS LIGHT
PASS DARK
PASS HIGH_CONTRAST
DETECTED mixed: Trộn họ hoặc trả về sai họ: DARK
DETECTED missing: Thiếu Checkbox cho DARK
```

Ba dòng `PASS` cho biết những factory hợp lệ vượt qua **các tiêu chí đã mã hóa trong ví dụ**, chứ không tự chứng minh toàn bộ hệ thống giao diện đạt chất lượng. Hai dòng `DETECTED` là bằng chứng rằng bộ kiểm tra bắt được lỗi trộn họ và thiếu sản phẩm dù hai factory lỗi vẫn triển khai đầy đủ `UiFactory` về mặt cú pháp.

### Đọc kết quả của từng bước kiểm tra

1. `factory.createButton()` và `factory.createCheckbox()` xác nhận các đường tạo sản phẩm đều có kết quả.
2. `buttonPalette.family == expected` và `checkboxPalette.family == expected` xác nhận **cả hai sản phẩm** khớp với họ đã chọn.
3. `sameSharedTokens(expectedPalette(expected))` kiểm tra các token **được quy định chung**. Đây là yêu cầu cụ thể của ví dụ, không bắt mọi thuộc tính hiển thị của Button và Checkbox giống hệt nhau.
4. `render()` được gọi với trạng thái và nhãn mẫu để kiểm tra hành vi tối thiểu client sử dụng.
5. Một hàm `verifyFactoryContract()` được dùng cho **mọi họ**. Khi thêm một họ, đưa factory mới vào tập kiểm tra; khi thêm một loại sản phẩm, mở rộng bộ tiêu chí tương ứng.

Trong hệ thống thực, không nhất thiết phải đưa `family()` hay `palette()` vào mọi product interface chỉ phục vụ test. Ví dụ dùng `Palette` như một phần thiết kế để minh họa quy tắc rõ ràng. Ở dự án có sản phẩm phức tạp, có thể kiểm tra bằng **hành vi quan sát được**, thông tin style, contract của component, hoặc cơ chế kiểm chứng test hỗ trợ sẵn có.

## 5. Quy trình đánh giá một concrete factory trước khi tích hợp

Một quy trình thực tế có thể tiến hành như sau:

**Bước 1 — Chốt hợp đồng sản phẩm.** Liệt kê `UiFactory` tạo những loại nào và từng loại công bố những thao tác gì. Nếu chỉ có `Button` và `Checkbox`, cả hai phải được kiểm tra; nếu thêm `Dialog`, bổ sung ngay tiêu chí cho `Dialog`.

**Bước 2 — Xác định tiêu chuẩn của mỗi họ.** Ví dụ Light có bộ token Light, Dark có bộ token Dark. Các quy tắc về focus, trạng thái, kết nối dữ liệu hoặc định dạng giao tiếp phải được mô tả đủ rõ để kiểm tra, thay vì chỉ dựa vào tên lớp.

**Bước 3 — Chạy một contract test với từng factory.** Dùng chung tập phép thử, truyền lần lượt `LightUiFactory`, `DarkUiFactory` và `HighContrastUiFactory` cùng họ kỳ vọng. Kiểm tra cả kết quả khác `null`, đúng họ và hành vi tối thiểu.

**Bước 4 — Thử tình huống lỗi.** Chủ động thay một sản phẩm bằng biến thể sai họ, hoặc cho một đường tạo trả về `null`, để xác nhận bộ kiểm tra có thể phát hiện những vi phạm mà compiler bỏ qua. Những tình huống này có thể kiểm thử bằng factory giả trong bộ test, không cần đưa lớp lỗi vào code production.

**Bước 5 — Kiểm tra tích hợp ở client.** Đảm bảo màn hình sử dụng một factory đã được chọn cho phạm vi cần đồng bộ, không âm thầm tạo lại sản phẩm cụ thể hay lấy thêm sản phẩm từ một factory khác.

**Bước 6 — Kiểm tra trải nghiệm và chạy lại sau thay đổi.** Với UI thật, kiểm tra các trạng thái hover, focus, disabled, checked, văn bản và tương phản theo yêu cầu. Sau khi đổi interface, thêm loại sản phẩm hoặc sửa shared tokens, chạy lại các test cho **toàn bộ họ** để tìm hồi quy.

## 6. Đừng nhầm “đúng họ” với “mọi sản phẩm giống nhau”

Hai sản phẩm có thể thuộc cùng một họ nhưng có kiểu hiển thị khác nhau vì trách nhiệm khác nhau:

| Thành phần | Một thuộc tính riêng hợp lý | Quy tắc chung cần giữ |
| --- | --- | --- |
| `Button` | Màu nền và kích thước theo vai trò hành động | Thuộc họ đã chọn; tuân thủ bộ token chung và khả năng nhận biết focus |
| `Checkbox` | Hình dạng dấu chọn và vị trí nhãn | Thuộc họ đã chọn; trạng thái checked/unchecked rõ ràng |
| `Dialog` (nếu có) | Kích thước vùng nội dung và nút đóng | Thuộc họ đã chọn; đồng bộ quy ước focus, chữ và điều hướng |

Vì vậy, một test so sánh toàn bộ cấu trúc DOM, mọi thuộc tính CSS hoặc chuỗi `render()` giữa các sản phẩm thường quá cứng và dễ tạo báo động giả. Hãy tách:

- **Invariants theo họ**: các điều kiện chung bắt buộc, chẳng hạn định danh họ hoặc bộ token đã thống nhất.
- **Invariants theo loại sản phẩm**: các hành vi riêng như render nhãn button hay phản ánh trạng thái checkbox.
- **Invariants tại điểm tích hợp**: client chỉ lắp ráp các sản phẩm tương thích và quản lý đúng vòng đời của chúng.

Nếu sản phẩm có tính chất bất biến, nên tạo hoặc kiểm tra chúng sao cho không thể bị sửa tùy tiện sau khi factory cung cấp. Nếu có trạng thái thay đổi, test cần xét cả quá trình chuyển trạng thái; chỉ nhìn giá trị ban đầu chưa đủ.

## 7. Những sai sót khi tự đánh giá thiết kế

| Cách kiểm tra thiếu sót | Vì sao chưa đủ? | Cải thiện |
| --- | --- | --- |
| “Có `implements UiFactory` là hợp lệ” | Chỉ xác nhận phương thức và kiểu dữ liệu; vẫn có thể trả `null` hoặc sai họ. | Bổ sung kiểm tra sản phẩm thực tế và quy tắc theo họ. |
| Chỉ kiểm tra `createButton()` | Bỏ sót `Checkbox` hoặc các loại sản phẩm khác. | Duyệt đủ các phương thức của contract. |
| Chỉ dùng `instanceof Button` | Không chứng minh button là sản phẩm của họ được chọn. | Kiểm tra đặc tả họ hoặc hành vi kỳ vọng. |
| Dựa vào `getClass().getSimpleName()` chứa “Dark” | Tên lớp có thể đổi, sản phẩm có thể dùng decorator/proxy. | Kiểm tra thuộc tính/hành vi có ý nghĩa trong hợp đồng. |
| Chỉ so sánh kết quả với snapshot văn bản | Snapshot có thể đổi vì định dạng mà không đổi hành vi; cũng có thể bỏ qua trạng thái quan trọng. | Tách kiểm tra ngữ nghĩa và kiểm tra hiển thị. |
| Chỉ chạy test cho họ mới | Thay đổi ở abstract product hoặc shared code có thể làm hỏng họ cũ. | Chạy lại cùng bộ contract test cho tất cả họ. |
| Dùng `assert` nhưng chạy JVM không có `-ea` | Phép kiểm tra bằng `assert` thường bị tắt mặc định. | Dùng framework test hoặc điều kiện ném lỗi rõ ràng. |
| Ép mọi thuộc tính Button bằng Checkbox | Nhầm thống nhất họ với đồng nhất kiểu dáng giữa các loại sản phẩm. | Chỉ so sánh quy tắc chung đã được đặc tả. |

## 8. Khi thêm họ hoặc thêm loại sản phẩm, cần đánh giá lại điều gì?

**Tình huống A — Thêm họ `HighContrast`:** Hợp đồng `UiFactory` vẫn có `createButton()` và `createCheckbox()`. Bạn thêm `HighContrastButton`, `HighContrastCheckbox`, `HighContrastUiFactory`, đăng ký nơi lựa chọn factory và chạy bộ contract test cho họ mới. Đồng thời chạy lại Light và Dark để chắc chắn những phần dùng chung không gây hồi quy.

**Tình huống B — Thêm loại sản phẩm `Dialog`:** `UiFactory` có thêm `createDialog()`; mọi factory cụ thể phải triển khai phương thức đó. Compiler giúp phát hiện factory thiếu implementation. Tuy nhiên, cần thêm vào bộ contract test các phép kiểm tra như: dialog khác `null`, đúng họ, có thể hiển thị/đóng theo hợp đồng và phối hợp phù hợp với những sản phẩm còn lại.

**Tình huống C — Cho phép đổi theme khi đang chạy:** Việc tạo sản phẩm mới từ Dark không tự thay thế Button Light đã có trên màn hình. Cần xác định **phạm vi nhất quán** (màn hình, request hoặc phiên người dùng), cập nhật cả nhóm sản phẩm liên quan và kiểm tra trạng thái sau khi đổi. Đây là trách nhiệm thiết kế vòng đời/tích hợp bên cạnh hợp đồng của từng factory.

Có thể tóm tắt tác động bằng một quy tắc: **thêm hàng** vào ma trận thì kiểm tra toàn bộ sản phẩm của họ mới; **thêm cột** thì kiểm tra loại sản phẩm mới trên **mọi họ**. Bất kỳ thay đổi nào ở hợp đồng chung đều cần được kiểm tra trên các họ hiện có.

## 9. Bài luyện tập và tự kiểm tra

**Câu 1.** Tại sao `DarkUiFactory` trả về `new LightCheckbox()` vẫn có thể biên dịch khi `createCheckbox()` trả về `Checkbox`?

**Đáp án gợi ý:** `LightCheckbox` vẫn triển khai `Checkbox`. Java kiểm tra kiểu trả về phù hợp nhưng không mặc nhiên biết yêu cầu tương thích giữa hai sản phẩm thuộc cùng một họ. Test cần xác nhận sản phẩm đúng họ và tuân thủ quy tắc chung.

**Câu 2.** Có phải kiểm tra `createButton() != null` và `createCheckbox() != null` là đủ để tuyên bố một họ hợp lệ?

**Đáp án gợi ý:** Chưa. Hai kết quả vẫn có thể thuộc các họ khác nhau hoặc không tuân thủ hành vi và tiêu chuẩn giao diện. Cần kiểm tra cả tính nhất quán và khả năng sử dụng.

**Câu 3.** Nếu Button của họ Dark dùng nền đậm hơn Checkbox của họ Dark thì có tự động vi phạm Abstract Factory không?

**Đáp án gợi ý:** Không. Hai loại sản phẩm có thể có style riêng. Vi phạm chỉ xảy ra nếu chúng trái quy tắc chung hoặc yêu cầu tương thích đã được đặc tả. Không nên ép mọi thuộc tính giống nhau.

**Câu 4.** Khi thêm `createDialog()` vào `UiFactory`, compiler phát hiện được điều gì và test vẫn phải kiểm tra điều gì?

**Đáp án gợi ý:** Compiler phát hiện các concrete factory thiếu phương thức bắt buộc hoặc sai kiểu trả về. Test vẫn cần kiểm tra kết quả không `null`, đúng họ, hành vi dialog và phối hợp với các sản phẩm khác.

**Bài thực hành.** Hãy sửa `HighContrastUiFactory.createCheckbox()` trong ví dụ để trả về `new DarkCheckbox()`. Dự đoán và đối chiếu thông báo từ `verifyFactoryContract(Family.HIGH_CONTRAST, ...)`. Sau đó sửa thành `return null;` để thấy kiểm tra tính đầy đủ phát hiện một lỗi khác. Khôi phục implementation đúng và kiểm tra lại cả ba họ.

## Kết luận

Đánh giá thiết kế **Abstract Factory** không dừng ở việc xác nhận factory đã `implements` đủ interface. Mỗi họ phải cung cấp **đầy đủ các loại sản phẩm**, trả về **đối tượng hợp lệ thuộc đúng họ**, và đáp ứng **những quy tắc tương thích được đặc tả** khi client phối hợp các sản phẩm đó. Kết hợp kiểm tra của trình biên dịch với bộ **contract test dùng chung cho mọi factory** và kiểm tra tích hợp thực tế giúp phát hiện các lỗi `null`, trộn họ, sai token và sai hành vi trước khi chúng lan tới client. Các quy tắc cần được xác định rõ theo từng họ, từng loại sản phẩm và phạm vi sử dụng, tránh kiểm tra cứng những khác biệt hợp lệ giữa các thành phần.

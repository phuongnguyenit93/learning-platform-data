# Client tự new sản phẩm hoặc trộn sản phẩm từ nhiều factory

**Chương:** Lỗi thường gặp  
**Chuyên đề:** `SOFTWARE_DESIGN_DESIGN_PATTERN_CREATIONAL_ABSTRACT_FACTORY` — Học về abstract factory trong design pattern.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Nhận diện hai lỗi thiết kế phổ biến khi dùng **Abstract Factory**: client tự khởi tạo sản phẩm cụ thể bằng `new` và client vô tình trộn các sản phẩm của nhiều họ.
- Giải thích vì sao mã có thể **biên dịch và chạy được** nhưng vẫn phá vỡ tính nhất quán của họ sản phẩm.
- Sửa thiết kế bằng cách chọn **một factory phù hợp cho một phạm vi sử dụng** và yêu cầu các sản phẩm thông qua factory đó.
- Phân biệt nơi được phép tạo implementation cụ thể với lớp client chỉ nên biết interface.
- Xây dựng các bước kiểm tra để phát hiện lỗi khi thêm họ giao diện hoặc thay cấu hình lúc chạy.

## 1. Bối cảnh: một màn hình phải dùng một họ sản phẩm nhất quán

Giả sử ứng dụng Java có màn hình thiết lập (`PreferencesPage`) gồm nút lưu (`Button`) và ô chọn nhận thông báo (`Checkbox`). Ứng dụng hỗ trợ hai họ giao diện: `Light` và `Dark`.

| Họ giao diện | Nút (`Button`) | Ô chọn (`Checkbox`) | Factory |
| --- | --- | --- | --- |
| Light | `LightButton` | `LightCheckbox` | `LightUiFactory` |
| Dark | `DarkButton` | `DarkCheckbox` | `DarkUiFactory` |

**Loại sản phẩm** là cột của bảng: `Button`, `Checkbox`. **Họ sản phẩm** là hàng: `Light`, `Dark`. Một factory cụ thể tạo ra một bộ sản phẩm thuộc cùng hàng. Nếu sau này có thêm `HighContrast`, ta bổ sung sản phẩm và factory tương ứng cho họ mới.

Trong thiết kế đúng, một màn hình được cấu hình theo `Dark` sẽ nhận cả `DarkButton` **và** `DarkCheckbox`. Nếu nhận `LightButton` và `DarkCheckbox` cùng lúc, các thành phần có thể khác quy tắc màu, đường viền, biểu tượng chọn, trạng thái focus và cách biểu đạt tương tác.

Abstract Factory giúp đặt việc tạo bộ sản phẩm vào một đầu mối; tuy nhiên, pattern **không tự ngăn** lập trình viên gọi trực tiếp constructor hoặc lấy sản phẩm từ nhiều factory khác họ. Hai lỗi đó cần được nhận diện và phòng tránh ở thiết kế client.

## 2. Lỗi thứ nhất: client tự `new` sản phẩm cụ thể

### Đoạn mã có vấn đề

Xét mã Java sau, giả sử các interface `Button`, `Checkbox` và các lớp sản phẩm đã tồn tại:

```java
// Phản ví dụ: màn hình biết quá nhiều lớp triển khai.
final class PreferencesPage {
    private final Button saveButton = new LightButton();
    private final Checkbox alertsCheckbox = new LightCheckbox();

    String render() {
        return saveButton.render() + "\n"
             + alertsCheckbox.render(true);
    }
}
```

Điểm nguy hiểm không nằm ở từ khóa `new` nói chung, mà ở **việc client trực tiếp chọn và tạo các sản phẩm thuộc một họ cụ thể**. Khi yêu cầu thay đổi sang Dark hoặc HighContrast:

1. `PreferencesPage` phải sửa code để biết thêm các lớp `DarkButton`, `DarkCheckbox` hoặc viết các nhánh điều kiện theo `theme`.
2. Nếu nhiều màn hình có cùng cách làm, logic chọn họ bị lặp trên toàn hệ thống.
3. Một lần chỉnh sửa thiếu đồng bộ có thể khiến nút dùng Dark nhưng ô chọn vẫn dùng Light.
4. Bài kiểm thử `PreferencesPage` phụ thuộc trực tiếp vào sản phẩm thật, khó thay bằng bản giả lập (`fake`) để kiểm thử riêng logic màn hình.

Mẫu thiết kế dần mất lợi ích **đảo ngược phụ thuộc**: client sử dụng sản phẩm bị buộc chặt vào lớp triển khai cụ thể thay vì các giao diện trừu tượng.

### Cách sửa: inject một `UiFactory`

Để màn hình nhận abstract factory qua constructor, rồi yêu cầu factory tạo đủ sản phẩm:

```java
final class PreferencesPage {
    private final Button saveButton;
    private final Checkbox alertsCheckbox;

    PreferencesPage(UiFactory factory) {
        this.saveButton = factory.createButton();
        this.alertsCheckbox = factory.createCheckbox();
    }

    String render() {
        return saveButton.render() + "\n"
             + alertsCheckbox.render(true);
    }
}
```

Mã này vẫn có hành động **tạo sản phẩm**, nhưng client gọi **phương thức trừu tượng** của factory mà không gọi `new LightButton()` hoặc `new DarkCheckbox()`. Khi thay họ, ta chỉ thay instance `UiFactory` được truyền vào, không thay logic của `PreferencesPage`.

Không nên hiểu thành quy tắc “mọi `new` đều sai”. Những câu lệnh như `new LightButton()` **đúng chỗ** trong `LightUiFactory`; `new DarkUiFactory()` **đúng chỗ** tại điểm cấu hình/lắp ráp ứng dụng (composition root). Client vẫn có thể `new` các đối tượng thuộc trách nhiệm riêng của nó, chẳng hạn giá trị nội bộ không phụ thuộc việc chọn họ sản phẩm.

## 3. Lỗi thứ hai: trộn sản phẩm lấy từ nhiều factory

Ngay cả khi client không trực tiếp `new LightButton()`, việc dùng factory vẫn có thể sai:

```java
// Phản ví dụ: hai factory thuộc hai họ khác nhau.
UiFactory lightFactory = new LightUiFactory();
UiFactory darkFactory = new DarkUiFactory();

Button saveButton = lightFactory.createButton();
Checkbox alertsCheckbox = darkFactory.createCheckbox();

System.out.println(saveButton.render());
System.out.println(alertsCheckbox.render(true));
```

Ví dụ trên chỉ cần các interface trả về đúng kiểu `Button` và `Checkbox` là **được Java chấp nhận**. Trình biên dịch không biết rằng nút và ô chọn phải cùng một theme. Kết quả có thể là:

```text
[Light] Button: Lưu, nền sáng
[Dark] Checkbox: Nhận thông báo [x], nền tối
```

Đây là lỗi **nhất quán họ sản phẩm**: từng đối tượng tự hoạt động đúng nhưng toàn bộ màn hình sai quy ước giao diện. Lỗi dễ bị bỏ sót vì nó không nhất thiết gây exception; chỉ xuất hiện qua hành vi, giao diện hoặc test nghiệp vụ.

### Tại sao interface không bắt được lỗi này?

`UiFactory` thường khai báo:

```java
interface UiFactory {
    Button createButton();
    Checkbox createCheckbox();
}
```

Hai factory cụ thể đều trả về các kiểu này. Hệ kiểu Java chỉ kiểm tra **đối tượng có thỏa hợp đồng `Button`/`Checkbox` hay không**, không mặc nhiên kiểm tra hai kết quả có thuộc cùng một họ về mặt thiết kế. Nếu cần bảo đảm mạnh hơn, dự án có thể bổ sung cơ chế kiểm thử hợp đồng, cấu trúc package, hoặc biểu diễn họ bằng kiểu/generic phù hợp; song lựa chọn đó có thêm chi phí phức tạp. Với ví dụ cơ bản, cách hiệu quả nhất là **chọn đúng một factory cho màn hình** và chỉ lấy các sản phẩm trong màn hình qua factory đó.

### Cách sửa: truyền một factory duy nhất vào client

```java
UiFactory selectedFactory = new DarkUiFactory();
PreferencesPage page = new PreferencesPage(selectedFactory);

System.out.println(page.render());
```

Giờ `PreferencesPage` gọi `selectedFactory.createButton()` và `selectedFactory.createCheckbox()` từ **cùng một factory**. Nếu chọn Light, cặp sản phẩm đều thuộc Light; nếu chọn Dark, cặp sản phẩm đều thuộc Dark.

“Một factory” ở đây nghĩa là **một họ được chọn nhất quán trong phạm vi phải đồng bộ**, chẳng hạn màn hình, request hoặc phiên người dùng. Không bắt buộc cả ứng dụng phải giữ đúng một factory toàn cục hay dùng Singleton. Hai màn hình độc lập có thể dùng hai họ khác nhau nếu đó là yêu cầu có chủ đích.

## 4. Ví dụ Java chạy được: từ cấu hình đến màn hình

Ví dụ sau tập trung vào luồng đúng: điểm khởi động lựa chọn một `UiFactory`, `PreferencesPage` chỉ nhận factory qua constructor và tạo cả hai sản phẩm từ cùng nguồn. Hàm `render()` trả về chuỗi để quan sát trên console; đây là mô phỏng thành phần giao diện, không phụ thuộc thư viện UI.

Lưu toàn bộ mã vào một file **`AbstractFactoryPitfallsDemo.java`** (Java 8 trở lên).

```java
import java.util.Locale;
import java.util.Objects;

// Abstract products
interface Button {
    String render();
}

interface Checkbox {
    String render(boolean checked);
}

// Abstract factory: hợp đồng của mọi họ sản phẩm.
interface UiFactory {
    Button createButton();
    Checkbox createCheckbox();
}

// Các sản phẩm thuộc họ Light
final class LightButton implements Button {
    @Override
    public String render() {
        return "[Light] Button: Lưu, nền sáng";
    }
}

final class LightCheckbox implements Checkbox {
    @Override
    public String render(boolean checked) {
        return "[Light] Checkbox: Nhận thông báo "
             + (checked ? "[x]" : "[ ]") + ", nền sáng";
    }
}

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

// Các sản phẩm thuộc họ Dark
final class DarkButton implements Button {
    @Override
    public String render() {
        return "[Dark] Button: Lưu, nền tối";
    }
}

final class DarkCheckbox implements Checkbox {
    @Override
    public String render(boolean checked) {
        return "[Dark] Checkbox: Nhận thông báo "
             + (checked ? "[x]" : "[ ]") + ", nền tối";
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

// Client không biết LightButton, DarkCheckbox hay tên theme.
final class PreferencesPage {
    private final Button saveButton;
    private final Checkbox alertsCheckbox;

    PreferencesPage(UiFactory factory) {
        Objects.requireNonNull(factory, "factory");
        // Cả hai sản phẩm luôn được yêu cầu từ cùng một factory.
        this.saveButton = Objects.requireNonNull(
            factory.createButton(), "saveButton");
        this.alertsCheckbox = Objects.requireNonNull(
            factory.createCheckbox(), "alertsCheckbox");
    }

    String render() {
        return saveButton.render() + System.lineSeparator()
             + alertsCheckbox.render(true);
    }
}

// Composition root: nơi chọn triển khai theo cấu hình đầu vào.
public final class AbstractFactoryPitfallsDemo {
    private static UiFactory chooseFactory(String theme) {
        String normalized = Objects.requireNonNull(theme, "theme")
                .trim().toLowerCase(Locale.ROOT);

        switch (normalized) {
            case "light":
                return new LightUiFactory();
            case "dark":
                return new DarkUiFactory();
            default:
                throw new IllegalArgumentException(
                    "Theme không hỗ trợ: " + theme);
        }
    }

    public static void main(String[] args) {
        String theme = args.length == 0 ? "light" : args[0];
        UiFactory factory = chooseFactory(theme);
        PreferencesPage page = new PreferencesPage(factory);
        System.out.println(page.render());
    }
}
```

### Biên dịch và chạy

```bash
javac -encoding UTF-8 AbstractFactoryPitfallsDemo.java
java AbstractFactoryPitfallsDemo light
java AbstractFactoryPitfallsDemo dark
```

Chạy với `light`:

```text
[Light] Button: Lưu, nền sáng
[Light] Checkbox: Nhận thông báo [x], nền sáng
```

Chạy với `dark`:

```text
[Dark] Button: Lưu, nền tối
[Dark] Checkbox: Nhận thông báo [x], nền tối
```

Truyền `blue` sẽ nhận `IllegalArgumentException` vì chưa có họ tương ứng. Việc báo lỗi rõ ràng giúp phát hiện cấu hình sai thay vì âm thầm trộn hoặc chọn một họ bất ngờ.

**Dòng quan trọng nhất** trong client không phải nhánh `switch` mà là:

```java
PreferencesPage(UiFactory factory) {
    this.saveButton = factory.createButton();
    this.alertsCheckbox = factory.createCheckbox();
}
```

`PreferencesPage` không chọn theme; nó chỉ yêu cầu hai sản phẩm theo một hợp đồng. Việc chọn `LightUiFactory` hay `DarkUiFactory` diễn ra trong `chooseFactory()` tại ranh giới khởi động.

## 5. Quy tắc sở hữu trách nhiệm tạo đối tượng

Một điểm hay gây hiểu nhầm: có phải khi dùng Abstract Factory, cả ứng dụng đều không được viết `new`?

**Không.** Cần phân biệt **tạo đối tượng nói chung** với **client tự chọn lớp sản phẩm cụ thể**:

| Vị trí trong chương trình | Ví dụ | Nhận xét |
| --- | --- | --- |
| Concrete factory | `new DarkButton()` trong `DarkUiFactory.createButton()` | Đúng trách nhiệm của factory. |
| Composition root | `new DarkUiFactory()` sau khi đọc cấu hình | Đúng chỗ chọn implementation cho ứng dụng. |
| Client của họ giao diện | `factory.createButton()` | Đúng: chỉ phụ thuộc abstraction. |
| Client của họ giao diện | `new DarkButton()` bên trong màn hình | Dấu hiệu phụ thuộc sai chỗ, làm mất khả năng đổi họ. |
| Client tạo dữ liệu nội bộ | `new ArrayList<>()` để lưu trạng thái không phụ thuộc theme | Không phải lỗi Abstract Factory. |

Trong dự án thực tế, có thể để **composition root tạo sẵn sản phẩm** rồi inject `Button` và `Checkbox` vào client; cũng có thể inject `UiFactory` nếu client cần tạo sản phẩm theo thời điểm hoặc nhiều lần. Điều quan trọng là **việc chọn họ vẫn thuộc về composition root hoặc cơ chế cấu hình tập trung**, còn việc tạo các sản phẩm cùng họ đi qua một factory phù hợp.

Nếu client chỉ nhận hai sản phẩm đã tạo sẵn, nơi lắp ráp phải đảm bảo hai đối tượng lấy từ cùng họ:

```java
UiFactory factory = chooseFactory(theme);
Button button = factory.createButton();
Checkbox checkbox = factory.createCheckbox();
// Truyền cả hai vào constructor của client nhận sản phẩm.
```

Không nên inject hai factory độc lập chỉ để mỗi thành phần tự chọn một họ; cách đó đẩy nguy cơ phối trộn trở lại client.

## 6. Bốn tình huống dễ tái diễn lỗi

### 6.1. Thêm họ sản phẩm mới nhưng quên sửa nơi khởi tạo

Giả sử thêm `HighContrastButton`, `HighContrastCheckbox` và `HighContrastUiFactory`. Nếu một số màn hình còn gọi `new DarkButton()`, chúng không chuyển sang họ mới dù cấu hình hệ thống đã chọn `high-contrast`.

**Cách phòng tránh:** tìm các nơi sử dụng concrete product trong tầng client, loại bỏ việc tự lựa chọn, và đưa lựa chọn factory vào vùng khởi tạo. Khi thêm họ mới, factory mới phải tạo đầy đủ các loại sản phẩm được khai báo trong `UiFactory`.

### 6.2. Trộn sản phẩm khi lắp ráp màn hình

Một composition root viết vội có thể tạo:

```java
UiFactory primary = new DarkUiFactory();
UiFactory fallback = new LightUiFactory();

Button button = primary.createButton();
Checkbox checkbox = fallback.createCheckbox(); // Lệch họ
```

Ngay cả khi lỗi nằm trong **composition root** thay vì lớp màn hình, kết quả vẫn bị trộn. Vì vậy, tập trung mã khởi tạo **giảm nơi có thể sai** nhưng không thay thế nhu cầu kiểm tra tính nhất quán của họ sản phẩm.

### 6.3. Đổi theme giữa vòng đời màn hình

Ví dụ, `Button` được tạo trước khi theme chuyển từ Light sang Dark nhưng `Checkbox` được tạo sau khi chuyển. Nếu mỗi lần gọi factory lại tra cứu một “theme hiện tại” có thể thay đổi, một màn hình vẫn có nguy cơ trộn họ.

**Cách phòng tránh:** quy định rõ thời điểm chọn theme cho phạm vi màn hình/request. Khi đổi theme lúc chạy, cập nhật hoặc tạo lại **toàn bộ nhóm thành phần liên quan** theo một chính sách nhất quán, thay vì thay lần lượt một vài sản phẩm mà không đồng bộ trạng thái.

### 6.4. Dùng factory khác họ cho các phần cùng một trải nghiệm

Một màn hình có thể được chia thành nhiều panel. Nếu từng panel tự lấy factory từ một biến global hoặc tự đọc cấu hình, chúng có thể chọn khác họ trong cùng một lần render.

**Cách phòng tránh:** root chọn một factory cho phạm vi cần đồng bộ, sau đó truyền cùng lựa chọn xuống các panel. Việc dùng hai họ trong cùng ứng dụng vẫn hợp lệ nếu các phạm vi độc lập và yêu cầu thiết kế cho phép.

## 7. Kiểm tra sau khi sửa

Có thể dùng bảng kiểm tra nhỏ sau để đảm bảo mỗi họ tạo đúng bộ sản phẩm:

| Cấu hình đầu vào | Factory được chọn | `Button` kỳ vọng | `Checkbox` kỳ vọng |
| --- | --- | --- | --- |
| `light` | `LightUiFactory` | `LightButton` | `LightCheckbox` |
| `dark` | `DarkUiFactory` | `DarkButton` | `DarkCheckbox` |
| `high-contrast` (nếu đã hỗ trợ) | `HighContrastUiFactory` | `HighContrastButton` | `HighContrastCheckbox` |
| Giá trị không hợp lệ | Không khởi tạo màn hình | Không có | Không có |

Khi kiểm thử ở mức factory, có thể kiểm tra loại sản phẩm trả về (ví dụ `factory.createButton() instanceof DarkButton` và `factory.createCheckbox() instanceof DarkCheckbox` cho `DarkUiFactory`). Ở mức giao diện, cần kiểm tra **thuộc tính hiển thị và tương tác thực tế** vì đúng class vẫn có thể có màu sắc, trạng thái focus hoặc hành vi không nhất quán.

Nếu viết test cho client, truyền vào một `UiFactory` giả để xác nhận client gọi đủ `createButton()` và `createCheckbox()`, không tự tạo sản phẩm cụ thể. Các kiểm tra này tương ứng với ba loại lỗi khác nhau:

1. **Chọn sai họ:** root trả về factory không đúng cấu hình.
2. **Trả về sai thành viên của họ:** concrete factory trả về một sản phẩm thuộc họ khác; Java có thể vẫn chấp nhận kiểu trả về.
3. **Client bỏ qua factory:** màn hình tự `new` hoặc lấy sản phẩm bổ sung từ nguồn khác.

## 8. Bài tự kiểm tra

**Câu 1.** Đoạn mã dưới đây có vấn đề gì?

```java
final class Toolbar {
    private final Button save = new DarkButton();
}
```

**Gợi ý đáp án:** `Toolbar` phụ thuộc trực tiếp vào sản phẩm `DarkButton`. Nếu toolbar phải đổi theo theme, hãy inject `Button` đã được tạo từ factory hoặc inject một `UiFactory` được chọn bên ngoài.

**Câu 2.** Vì sao đoạn mã dưới đây có thể biên dịch mà vẫn sai?

```java
Button button = new LightUiFactory().createButton();
Checkbox checkbox = new DarkUiFactory().createCheckbox();
```

**Gợi ý đáp án:** Mỗi biến có kiểu hợp lệ (`Button`/`Checkbox`), nhưng hai đối tượng thuộc hai họ khác nhau. Đây là ràng buộc **ngữ nghĩa** của màn hình, không được bảo đảm tự động bằng các interface cơ bản.

**Câu 3.** Nếu hai factory đều là `LightUiFactory` nhưng khác instance, liệu luôn sai không?

**Gợi ý đáp án:** Không nhất thiết. Vấn đề là **trộn họ không tương thích**, không phải số lượng instance factory. Tuy vậy, dùng một lựa chọn factory trong phạm vi màn hình làm quan hệ phụ thuộc rõ hơn và tránh sai sót cấu hình.

**Câu 4.** Khi thêm họ `HighContrast`, bạn cần sửa `PreferencesPage` trong ví dụ hoàn chỉnh không?

**Gợi ý đáp án:** Không. Tạo `HighContrastButton`, `HighContrastCheckbox` và `HighContrastUiFactory`; thêm lựa chọn `high-contrast` ở điểm khởi động. `PreferencesPage` tiếp tục nhận `UiFactory`.

**Câu 5.** Nếu muốn chọn theme khác cho từng người dùng đồng thời, có nhất thiết đưa `UiFactory` vào biến `static` toàn cục không?

**Gợi ý đáp án:** Không. Có thể chọn factory theo request/session rồi truyền vào object graph của người dùng tương ứng. Một singleton global có thể khiến cấu hình giữa các người dùng ảnh hưởng lẫn nhau.

## Kết luận

Hai lỗi **client tự `new` sản phẩm cụ thể** và **trộn sản phẩm từ nhiều factory thuộc các họ khác nhau** đều phá vỡ mục đích sử dụng Abstract Factory. Lỗi đầu làm client phụ thuộc implementation và rải logic chọn họ khắp chương trình; lỗi sau khiến một nhóm thành phần không còn nhất quán dù code vẫn đúng kiểu và chạy được. Hướng thiết kế an toàn là chọn factory ở ranh giới khởi tạo, truyền một lựa chọn factory phù hợp vào phạm vi cần đồng bộ, và để các sản phẩm được tạo qua hợp đồng `UiFactory`. Cần kiểm tra cả hợp đồng kiểu dữ liệu lẫn tính nhất quán thực tế của sản phẩm trong cùng một họ.

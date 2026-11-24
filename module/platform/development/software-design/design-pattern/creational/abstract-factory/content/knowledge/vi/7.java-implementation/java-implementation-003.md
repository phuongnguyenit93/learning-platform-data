# Khai báo `GUIFactory` với `createButton()` và `createCheckbox()`

Trong mẫu thiết kế **Abstract Factory**, ứng dụng cần một cách để tạo **nhiều loại sản phẩm thuộc cùng một họ** mà mã sử dụng không phải biết tên lớp cụ thể của từng sản phẩm. Với ví dụ giao diện đồ họa, hai loại sản phẩm là **nút bấm** (`Button`) và **ô chọn** (`Checkbox`); mỗi loại có các phiên bản dành cho Windows hoặc macOS. Giao diện `GUIFactory` chính là hợp đồng để tạo ra cả hai sản phẩm.

Bài học thuộc chương **Hiện thực bằng Java** của module `SOFTWARE_DESIGN_DESIGN_PATTERN_CREATIONAL_ABSTRACT_FACTORY`, trong lộ trình **học về Abstract Factory trong design pattern**. Trọng tâm là **thiết kế và khai báo đúng interface `GUIFactory`**, hiểu kiểu trả về của `createButton()` và `createCheckbox()`, sau đó thấy cách hai Concrete Factory tuân theo hợp đồng này trong Java.

Sau bài học, bạn có thể:

- Khai báo hai **product interface** `Button` và `Checkbox`.
- Viết `GUIFactory` với đúng hai phương thức tạo sản phẩm, dùng kiểu trả về trừu tượng.
- Giải thích tại sao `GUIFactory` không chứa `new WindowsButton()` hay điều kiện chọn hệ điều hành.
- Hiện thực `WindowsFactory` và `MacFactory` trả về các sản phẩm cùng họ.
- Truyền một `GUIFactory` vào mã khách hàng để tránh phụ thuộc trực tiếp vào implementation.
- Nhận biết các giới hạn của hợp đồng interface và những thay đổi cần cân nhắc khi bổ sung sản phẩm mới.

## 1. Bài toán cần giải quyết

Giả sử ứng dụng phải hiển thị nút bấm và ô chọn theo giao diện của nền tảng đang sử dụng.

| Nền tảng | Button | Checkbox |
| --- | --- | --- |
| Windows | `WindowsButton` | `WindowsCheckbox` |
| macOS | `MacButton` | `MacCheckbox` |

Hai chiều trong bảng là:

1. **Loại sản phẩm (product type):** `Button` và `Checkbox`.
2. **Biến thể/họ sản phẩm (product family):** Windows và macOS.

Nếu mỗi màn hình tự tạo đối tượng như sau, mã nghiệp vụ phải biết nền tảng và tên lớp cụ thể:

~~~java
Button button;
Checkbox checkbox;

if (platform == Platform.WINDOWS) {
    button = new WindowsButton();
    checkbox = new WindowsCheckbox();
} else {
    button = new MacButton();
    checkbox = new MacCheckbox();
}
~~~

Khi thêm một màn hình mới, lập trình viên dễ sao chép lại khối chọn biến thể. Khi thêm nền tảng thứ ba, nhiều nơi có thể phải sửa. Thậm chí việc khởi tạo `WindowsButton` cùng `MacCheckbox` vẫn có thể được trình biên dịch chấp nhận nếu cả hai đều thực hiện các interface sản phẩm tương ứng.

Ý tưởng của Abstract Factory là chuyển trách nhiệm tạo **cả họ sản phẩm** sang một đối tượng factory. Mỗi màn hình chỉ nhận một đối tượng kiểu `GUIFactory` và gọi `createButton()`, `createCheckbox()`.

## 2. Khai báo các interface của sản phẩm trước

`GUIFactory` phải mô tả **nó tạo ra loại đối tượng nào**. Do đó, cần khai báo hai abstraction của sản phẩm trước khi khai báo factory.

File `src/main/java/example/gui/Button.java`:

~~~java
package example.gui;

public interface Button {
    String render();
}
~~~

File `src/main/java/example/gui/Checkbox.java`:

~~~java
package example.gui;

public interface Checkbox {
    String render();
    boolean isChecked();
    void setChecked(boolean checked);
}
~~~

Ở ví dụ này:

- `Button` là hợp đồng dành cho mọi loại nút bấm. Phương thức `render()` trả về một chuỗi mô phỏng cách trình bày để dễ chạy bằng Java thuần.
- `Checkbox` là hợp đồng dành cho mọi ô chọn. Ngoài `render()`, nó công bố trạng thái được chọn và phương thức thay đổi trạng thái.
- Các interface **không nhắc đến** Windows hay macOS; chúng đại diện cho **loại sản phẩm**, không đại diện cho biến thể.

`render()` trả chuỗi chỉ là cách mô phỏng phục vụ bài học; trong Swing, JavaFX hoặc một framework GUI khác, sản phẩm có thể có phương thức vẽ, thành phần UI hay hành vi tương tác hoàn toàn khác. Điều quan trọng là hai biến thể của cùng một loại sản phẩm thực hiện **cùng hợp đồng**.

## 3. Khai báo `GUIFactory` — phần cốt lõi

File `src/main/java/example/gui/GUIFactory.java`:

~~~java
package example.gui;

public interface GUIFactory {
    Button createButton();
    Checkbox createCheckbox();
}
~~~

Đây là khai báo tối thiểu và đầy đủ cho nhu cầu tạo hai loại sản phẩm:

| Thành phần | Ý nghĩa |
| --- | --- |
| `public interface GUIFactory` | Định nghĩa một **Abstract Factory** độc lập với nền tảng cụ thể |
| `Button createButton();` | Hứa cung cấp một đối tượng đáp ứng hợp đồng `Button` |
| `Checkbox createCheckbox();` | Hứa cung cấp một đối tượng đáp ứng hợp đồng `Checkbox` |
| Không có thân phương thức | Quyết định **tạo lớp cụ thể nào** thuộc về các lớp hiện thực `GUIFactory` |
| Không nhận tham số nền tảng | Biến thể được thể hiện bởi **factory đã được lựa chọn** |

Trong Java, các phương thức ở interface như trên mặc định là `public abstract`; không bắt buộc viết rõ hai từ khóa. Hai khai báo sau tương đương về mức truy cập và trách nhiệm trong ví dụ này:

~~~java
Button createButton();
public abstract Button createButton();
~~~

Các phương thức `createButton()` và `createCheckbox()` trả về **interface sản phẩm**, không trả về `WindowsButton` hay `MacCheckbox`. Nhờ đó, một phương thức của mã khách hàng chỉ cần xử lý `Button`, `Checkbox`, bất kể factory đang là `WindowsFactory` hay `MacFactory`.

**Quan trọng:** tên `GUIFactory` là tên thiết kế, không phải một kiểu có sẵn của Java. Tên `createButton()` và `createCheckbox()` cũng do chúng ta đặt. Điều làm nên Abstract Factory là **một abstraction khai báo các phương thức tạo một nhóm loại sản phẩm liên quan**; các implementation có trách nhiệm tạo ra các phiên bản tương thích.

### Vì sao không viết `createButton(Platform platform)`?

Có thể thiết kế một factory nhận `platform` ở từng phương thức rồi tự `switch` để chọn đối tượng. Tuy nhiên, như vậy mã khách hàng vẫn phải truyền quyết định chọn họ mỗi khi tạo sản phẩm; còn nguy cơ truyền hai nền tảng khác nhau cho `createButton()` và `createCheckbox()`.

Trong phiên bản đang học, ứng dụng **chọn một concrete factory** tại điểm cấu hình, sau đó gọi cả hai phương thức trên chính factory đó:

~~~java
GUIFactory factory = new WindowsFactory();
Button button = factory.createButton();
Checkbox checkbox = factory.createCheckbox();
~~~

Kết quả dự kiến là `WindowsButton` và `WindowsCheckbox`. Nếu chọn `new MacFactory()`, hai lệnh tạo tương tự sẽ sinh sản phẩm macOS.

Một factory cụ thể có thể nhận tham số trong **constructor của nó** (màu sắc, font, theme, cấu hình hệ thống), còn chữ ký hai phương thức tạo ở `GUIFactory` vẫn giữ ổn định nếu không cần tham số theo từng sản phẩm.

## 4. Mối quan hệ giữa các abstraction và implementation

~~~mermaid
classDiagram
    class GUIFactory {
      <<interface>>
      +createButton() Button
      +createCheckbox() Checkbox
    }
    class WindowsFactory
    class MacFactory
    class Button {
      <<interface>>
      +render() String
    }
    class Checkbox {
      <<interface>>
      +render() String
      +isChecked() boolean
      +setChecked(boolean)
    }
    class WindowsButton
    class MacButton
    class WindowsCheckbox
    class MacCheckbox
    GUIFactory <|.. WindowsFactory
    GUIFactory <|.. MacFactory
    Button <|.. WindowsButton
    Button <|.. MacButton
    Checkbox <|.. WindowsCheckbox
    Checkbox <|.. MacCheckbox
    GUIFactory ..> Button : createButton
    GUIFactory ..> Checkbox : createCheckbox
~~~

Đọc sơ đồ theo hai hướng:

1. **Theo loại sản phẩm:** `WindowsButton` và `MacButton` đều là `Button`. `WindowsCheckbox` và `MacCheckbox` đều là `Checkbox`.
2. **Theo họ sản phẩm:** `WindowsFactory` tạo cả hai sản phẩm Windows, trong khi `MacFactory` tạo cả hai sản phẩm macOS.

Nhiệm vụ của `GUIFactory` là buộc các factory cụ thể phải có **cả hai phương thức** `createButton()` và `createCheckbox()`. Quy tắc tạo các sản phẩm thuộc cùng một họ là cam kết thiết kế của mỗi implementation; **Java interface không tự kiểm tra tính tương thích giữa hai đối tượng được tạo**.

## 5. Hiện thực các sản phẩm cụ thể trong Java

Để thấy rõ các giá trị trả về, sau đây là phiên bản mô phỏng sản phẩm trên Windows và macOS. Những lớp này có thể giữ phạm vi truy cập package-private vì factory cùng nằm trong package `example.gui`.

File `src/main/java/example/gui/WindowsProducts.java`:

~~~java
package example.gui;

final class WindowsButton implements Button {
    @Override
    public String render() {
        return "[Windows Button: OK]";
    }
}

final class WindowsCheckbox implements Checkbox {
    private boolean checked;

    @Override
    public String render() {
        return "[Windows Checkbox: " + (checked ? "checked" : "unchecked") + "]";
    }

    @Override
    public boolean isChecked() {
        return checked;
    }

    @Override
    public void setChecked(boolean checked) {
        this.checked = checked;
    }
}
~~~

File `src/main/java/example/gui/MacProducts.java`:

~~~java
package example.gui;

final class MacButton implements Button {
    @Override
    public String render() {
        return "(macOS Button: OK)";
    }
}

final class MacCheckbox implements Checkbox {
    private boolean checked;

    @Override
    public String render() {
        return "(macOS Checkbox: " + (checked ? "checked" : "unchecked") + ")";
    }

    @Override
    public boolean isChecked() {
        return checked;
    }

    @Override
    public void setChecked(boolean checked) {
        this.checked = checked;
    }
}
~~~

Vì trong mỗi file trên không có lớp `public`, Java cho phép đặt hai lớp package-private cùng file. Trong dự án lớn, có thể tách mỗi lớp ra file riêng để tổ chức mã dễ bảo trì hơn.

Các implementation của `Button` và `Checkbox` được phân biệt bằng chuỗi `render()` để dễ quan sát. Tính đúng đắn của bài toán **không dựa vào định dạng chuỗi cụ thể**; mục đích của chúng là minh họa sản phẩm cùng loại có thể khác nhau theo nền tảng.

## 6. Hiện thực hai Concrete Factory

Sau khi có `GUIFactory` và các sản phẩm cụ thể, mỗi concrete factory hiện thực **đủ hai phương thức**.

File `src/main/java/example/gui/WindowsFactory.java`:

~~~java
package example.gui;

public final class WindowsFactory implements GUIFactory {
    @Override
    public Button createButton() {
        return new WindowsButton();
    }

    @Override
    public Checkbox createCheckbox() {
        return new WindowsCheckbox();
    }
}
~~~

File `src/main/java/example/gui/MacFactory.java`:

~~~java
package example.gui;

public final class MacFactory implements GUIFactory {
    @Override
    public Button createButton() {
        return new MacButton();
    }

    @Override
    public Checkbox createCheckbox() {
        return new MacCheckbox();
    }
}
~~~

Ba chi tiết quan trọng:

**Thứ nhất, chữ ký phải khớp hợp đồng.** Cả hai lớp đều phải cung cấp `public Button createButton()` và `public Checkbox createCheckbox()`. Annotation `@Override` giúp trình biên dịch kiểm tra phương thức đang ghi đè đúng hợp đồng.

**Thứ hai, các phương thức trả về một abstraction.** Java cho phép `return new WindowsButton();` trong phương thức có kiểu trả về `Button` vì `WindowsButton implements Button`. Điều tương tự đúng với `Checkbox`.

**Thứ ba, factory chịu trách nhiệm về tính nhất quán của họ sản phẩm.** Khi một `WindowsFactory` trả `new MacCheckbox()`, đoạn mã vẫn có thể biên dịch vì `MacCheckbox implements Checkbox`, nhưng nó vi phạm ý nghĩa của `WindowsFactory`. Đây là lỗi thiết kế hoặc lỗi nghiệp vụ cần được phát hiện bằng kiểm thử và review.

Một lỗi chữ ký phổ biến:

~~~java
// Sai: phương thức createCheckbox() chưa được hiện thực.
// Lớp này sẽ không biên dịch nếu không được khai báo abstract.
final class IncompleteFactory implements GUIFactory {
    @Override
    public Button createButton() {
        return new WindowsButton();
    }
}
~~~

Đoạn trên được trình bày **có chủ ý như một ví dụ lỗi**. Trình biên dịch buộc lớp concrete phải hiện thực đầy đủ các phương thức abstract của `GUIFactory`, nhờ đó không bỏ quên một loại sản phẩm khi bổ sung factory mới.

## 7. Sử dụng `GUIFactory` từ mã khách hàng

Ứng dụng sử dụng `GUIFactory` qua constructor injection: `Screen` không tự tạo `WindowsButton` hay `MacCheckbox`, cũng không chứa điều kiện chọn nền tảng.

File `src/main/java/example/gui/Main.java`:

~~~java
package example.gui;

import java.util.Objects;

enum Platform {
    WINDOWS, MAC
}

final class FactorySelector {
    private FactorySelector() {}

    static GUIFactory forPlatform(Platform platform) {
        Objects.requireNonNull(platform, "platform");
        switch (platform) {
            case WINDOWS:
                return new WindowsFactory();
            case MAC:
                return new MacFactory();
            default:
                throw new IllegalArgumentException("Unsupported platform: " + platform);
        }
    }
}

final class Screen {
    private final Button button;
    private final Checkbox checkbox;

    Screen(GUIFactory factory) {
        Objects.requireNonNull(factory, "factory");
        this.button = Objects.requireNonNull(factory.createButton(), "button");
        this.checkbox = Objects.requireNonNull(factory.createCheckbox(), "checkbox");
    }

    void show() {
        System.out.println(button.render());
        checkbox.setChecked(true);
        System.out.println(checkbox.render());
    }
}

public final class Main {
    public static void main(String[] args) {
        Platform platform = Platform.WINDOWS;
        GUIFactory factory = FactorySelector.forPlatform(platform);
        Screen screen = new Screen(factory);
        screen.show();
    }
}
~~~

Đây là mã Java thuần, phù hợp với Java 8+; ví dụ không phụ thuộc thư viện giao diện đồ họa bên ngoài. Nếu chạy `Main` với `Platform.WINDOWS`, kết quả dự kiến:

~~~text
[Windows Button: OK]
[Windows Checkbox: checked]
~~~

Đổi thành `Platform.MAC` sẽ dùng `MacFactory` và cho kết quả:

~~~text
(macOS Button: OK)
(macOS Checkbox: checked)
~~~

Chuỗi kết quả chỉ thể hiện hành vi giả lập của `render()`.

### Lần theo luồng khởi tạo

~~~mermaid
flowchart TD
    A["Main: chọn Platform"] --> B["FactorySelector.forPlatform(...)"]
    B --> C["Một GUIFactory cụ thể"]
    C --> D["Screen(GUIFactory)"]
    D --> E["factory.createButton()"]
    D --> F["factory.createCheckbox()"]
    E --> G["Button cùng họ"]
    F --> H["Checkbox cùng họ"]
    G --> I["Screen.show()"]
    H --> I
~~~

`Main` hoặc phần khởi tạo ứng dụng là **composition root**, nơi chọn concrete factory theo cấu hình. Sau đó `Screen` chỉ biết `GUIFactory`, `Button` và `Checkbox`. Việc dùng **cùng một đối tượng factory** cho cả hai phương thức tạo giúp tập trung quy tắc chọn họ sản phẩm vào một nơi.

`Objects.requireNonNull(...)` ở `Screen` cho thông báo lỗi rõ khi mã khách hàng nhận factory hoặc sản phẩm `null`. Đây là kiểm tra phòng vệ được thêm vào ví dụ, không phải quy tắc tự động do Abstract Factory cung cấp.

## 8. Hợp đồng của `createButton()` và `createCheckbox()` quy định được gì?

Khai báo interface tạo ra một số ràng buộc tại thời điểm biên dịch, nhưng không diễn đạt hết mọi quy tắc kinh doanh.

| Quy tắc | Java interface kiểm tra được? | Cách bảo đảm |
| --- | --- | --- |
| `createButton()` có thể được gọi qua `GUIFactory` | Có | Chữ ký phương thức trong interface |
| Kết quả của `createButton()` tương thích với `Button` | Có | Kiểu trả về `Button` |
| `createCheckbox()` tương thích với `Checkbox` | Có | Kiểu trả về `Checkbox` |
| Concrete factory phải cung cấp đủ hai phương thức | Có, với lớp concrete | `implements GUIFactory` |
| Hai sản phẩm thật sự thuộc cùng một họ | Không | Implementation đúng và unit test |
| Hai phương thức không bao giờ trả về `null` | Không | Quy ước hợp đồng, kiểm tra runtime và test |
| Mỗi lần gọi phải tạo một instance mới | Không | Chỉ cam kết và kiểm thử nếu ứng dụng yêu cầu |

Chẳng hạn, có thể nêu quy ước trả về như sau trong Javadoc của `GUIFactory`:

~~~java
/**
 * Tạo Button và Checkbox thuộc cùng một họ giao diện.
 * Mỗi phương thức trả về đối tượng khác null.
 * Phạm vi sống của đối tượng được quyết định bởi implementation.
 */
public interface GUIFactory {
    Button createButton();
    Checkbox createCheckbox();
}
~~~

Javadoc làm rõ **ý định thiết kế**, nhưng trình biên dịch Java không tự biến câu “khác null” thành một phép kiểm tra runtime. Nếu dùng annotation `@NonNull` từ một thư viện phân tích tĩnh, mức độ bảo đảm còn tùy công cụ và cấu hình dự án.

Một kiểm tra JUnit đơn giản có thể minh họa hợp đồng:

~~~java
// Đoạn mã trong phương thức @Test, với import JUnit phù hợp.
GUIFactory factory = new WindowsFactory();

Button button = factory.createButton();
Checkbox checkbox = factory.createCheckbox();

assertNotNull(button);
assertNotNull(checkbox);
assertTrue(button instanceof WindowsButton);
assertTrue(checkbox instanceof WindowsCheckbox);
~~~

Các kiểm tra kiểu cụ thể phù hợp khi ánh xạ Windows → `WindowsButton`/`WindowsCheckbox` là một cam kết của thiết kế. Nếu hệ thống cho phép wrapper hoặc decorator, nên ưu tiên kiểm tra hành vi quan sát được và sự tương thích của hai sản phẩm. Đây chỉ là đoạn **minh họa test**, không phải bộ kiểm thử hoàn chỉnh của bài.

## 9. Các lựa chọn thiết kế khi mở rộng `GUIFactory`

### 9.1. Thêm họ sản phẩm mới

Nếu cần hỗ trợ Linux, có thể bổ sung `LinuxButton`, `LinuxCheckbox` và `LinuxFactory implements GUIFactory`. **Chữ ký `GUIFactory` không cần thay đổi** khi chỉ thêm một biến thể mới, vì cả hai phương thức vẫn tạo `Button` và `Checkbox`. Điểm lựa chọn concrete factory tại `FactorySelector` cần nhận biết nền tảng Linux.

### 9.2. Thêm một loại sản phẩm mới

Giả sử giao diện cần thêm `TextField`. Khi thêm:

~~~java
public interface GUIFactory {
    Button createButton();
    Checkbox createCheckbox();
    TextField createTextField();
}
~~~

tất cả concrete factory đang implement `GUIFactory` phải cung cấp `createTextField()` tương ứng, nếu không chúng sẽ không biên dịch. Đây là **đánh đổi chủ yếu** của Abstract Factory: dễ thêm *họ sản phẩm mới*, nhưng thêm *loại sản phẩm mới* tác động đến mọi factory.

Đoạn trên là một **hướng mở rộng minh họa**: `TextField` chưa được khai báo trong bộ mã chạy ở các phần trước. Không thêm dòng đó vào `GUIFactory.java` của ví dụ hiện tại nếu chưa có interface và implementation của `TextField`.

### 9.3. Tham số khi tạo sản phẩm

Nếu mỗi nút cần một nhãn khác nhau, có thể thiết kế:

~~~java
public interface GUIFactory {
    Button createButton(String label);
    Checkbox createCheckbox(boolean initiallyChecked);
}
~~~

Đây là một **hợp đồng thay thế**, không phải phiên bản cần ghép vào mã phía trên. Khi dùng cách này, tất cả concrete factory và điểm gọi phải cập nhật chữ ký. Tham số `label` hoặc `initiallyChecked` mô tả dữ liệu của **mỗi sản phẩm**, trong khi biến thể Windows/macOS vẫn do đối tượng concrete factory quyết định.

### 9.4. Factory không nhất thiết tạo mới mỗi lần

Tên `createButton()` gợi ý việc tạo đối tượng, nhưng bản thân interface **không bắt buộc** gọi `new` trong mỗi lần thực thi. Một concrete factory có thể trả sản phẩm dùng chung nếu điều đó phù hợp với hợp đồng và vòng đời sản phẩm. Tuy nhiên, đối tượng GUI có trạng thái như `Checkbox` thường không nên dùng chung giữa các màn hình nếu chúng cần trạng thái độc lập. Trong bộ mã minh họa, cả hai factory tạo instance mới cho mỗi lần gọi.

### 9.5. Không để factory trở thành nơi xử lý tất cả nghiệp vụ

`GUIFactory` chỉ nên chịu trách nhiệm **cung cấp sản phẩm cùng họ**. Không nên đưa vào nó chức năng đăng nhập, lưu dữ liệu, quản lý điều hướng hay mọi thao tác trên giao diện. Khi abstraction phình to hoặc các factory chỉ dùng được một phần nhỏ các phương thức, cần xem lại ranh giới của họ sản phẩm và nguyên tắc phân tách interface.

## 10. Lỗi thường gặp khi khai báo `GUIFactory`

| Cách khai báo hoặc sử dụng | Vấn đề | Cách sửa |
| --- | --- | --- |
| `WindowsButton createButton();` trong `GUIFactory` | Interface phụ thuộc trực tiếp vào một nền tảng | Trả về `Button` |
| `Object createCheckbox();` | Mất hợp đồng kiểu sản phẩm, khách hàng phải ép kiểu | Trả về `Checkbox` |
| Chỉ khai báo `createButton()` | Factory chưa cung cấp đầy đủ họ sản phẩm cần dùng | Thêm `createCheckbox()` |
| Gọi `new WindowsButton()` trong `Screen` | Mã khách hàng lại phụ thuộc implementation | Gọi `factory.createButton()` |
| Tự `switch(platform)` ở mọi màn hình | Phân tán quyết định chọn biến thể | Chọn factory tại composition root |
| `WindowsFactory` trả `MacCheckbox` | Hai sản phẩm khác họ, dù chữ ký hợp lệ | Sửa implementation và thêm kiểm thử |
| Mỗi phương thức tạo nhận một tham số `platform` độc lập | Có thể vô tình trộn biến thể | Dùng một factory được chọn sẵn |
| Cho rằng interface bảo đảm kết quả khác `null` | Java không kiểm tra bất biến đó | Tài liệu hóa, kiểm tra runtime và unit test |

Phân biệt thêm hai khái niệm thường bị nhầm: **`GUIFactory` là Abstract Factory**, tức một interface chứa các phương thức tạo **nhiều loại sản phẩm liên quan**. Các phương thức `createButton()` và `createCheckbox()` là thao tác tạo sản phẩm của Abstract Factory; chỉ có tên `create...` không tự biến toàn bộ thiết kế thành mẫu **Factory Method**. Factory Method là một mẫu riêng, thường dùng cơ chế kế thừa để quyết định đối tượng nào được tạo.

## 11. Bài tập thực hành

**Bài 1 — Điền chữ ký còn thiếu.** Giả sử đã có hai interface `Button` và `Checkbox`. Điền chỗ trống để `GUIFactory` tạo đủ hai loại sản phẩm mà không phụ thuộc Windows/macOS:

~~~java
public interface GUIFactory {
    // TODO: Khai báo phương thức tạo Button.
    // TODO: Khai báo phương thức tạo Checkbox.
}
~~~

Đáp án cốt lõi là `Button createButton();` và `Checkbox createCheckbox();`.

**Bài 2 — Tìm lỗi chữ ký.** Đoạn sau vi phạm mục tiêu nào?

~~~java
public interface GUIFactory {
    WindowsButton createButton();
    Checkbox createCheckbox();
}
~~~

Gợi ý: `WindowsButton` là một lớp cụ thể của riêng một nền tảng. Nó khiến việc hiện thực `MacFactory` phải tuân theo kiểu trả về gắn với Windows, trái với mục tiêu trừu tượng hóa họ sản phẩm.

**Bài 3 — Thêm concrete factory.** Giả sử cần hỗ trợ `LinuxFactory`. Hãy tạo `LinuxButton implements Button`, `LinuxCheckbox implements Checkbox` và `LinuxFactory implements GUIFactory`. Sau đó bổ sung case Linux tại `FactorySelector`. Không cần đổi hai chữ ký trong `GUIFactory`.

**Bài 4 — Xác định trách nhiệm.** Với luồng `Main → FactorySelector → GUIFactory → Screen`, hãy chỉ ra nơi cần đặt (a) điều kiện chọn nền tảng; (b) lệnh `new WindowsCheckbox()`; (c) thao tác `checkbox.setChecked(true)`. Gợi ý: lần lượt là điểm cấu hình/chọn factory, `WindowsFactory` và mã sử dụng sản phẩm.

## 12. Checklist trước khi hoàn tất khai báo

- [ ] Đã có interface `Button` và `Checkbox` diễn tả **hai loại sản phẩm khác nhau**.
- [ ] `GUIFactory` là interface dùng kiểu trả về `Button` và `Checkbox`.
- [ ] Đã khai báo đúng `Button createButton();` và `Checkbox createCheckbox();`.
- [ ] `GUIFactory` không nhắc đến lớp cụ thể `WindowsButton`, `MacCheckbox` hoặc nền tảng trong chữ ký của hai phương thức.
- [ ] Mỗi concrete factory implement **đủ hai phương thức** và trả sản phẩm cùng họ.
- [ ] Mã khách hàng nhận một `GUIFactory`, không tự chọn constructor theo nền tảng.
- [ ] Đã xác định rõ hợp đồng về `null`, vòng đời, tham số và cách kiểm chứng tính nhất quán của họ sản phẩm.
- [ ] Phân biệt được việc **thêm họ mới** với việc **thêm loại sản phẩm mới** khi xem xét mở rộng.

**Ghi nhớ:** Phần cốt lõi của bài là khai báo `GUIFactory` như sau:

~~~java
public interface GUIFactory {
    Button createButton();
    Checkbox createCheckbox();
}
~~~

Hai phương thức là hai **điểm tạo loại sản phẩm** thống nhất; việc chọn họ Windows, macOS hoặc một biến thể khác nằm ở concrete factory được cung cấp cho mã khách hàng. Đây là nền tảng để triển khai Abstract Factory trong Java theo nguyên tắc phụ thuộc vào abstraction.

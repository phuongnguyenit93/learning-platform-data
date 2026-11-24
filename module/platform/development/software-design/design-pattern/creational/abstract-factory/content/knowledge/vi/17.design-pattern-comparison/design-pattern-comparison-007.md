# Kết hợp Factory Method hoặc Prototype bên trong một ConcreteFactory

**Abstract Factory**, **Factory Method** và **Prototype** đều thuộc nhóm mẫu thiết kế khởi tạo (*creational design patterns*), nhưng chúng giải quyết những câu hỏi khác nhau. Abstract Factory xác định **những loại sản phẩm nào phải được tạo theo cùng một họ**. Factory Method cung cấp **một điểm mở rộng thông qua kế thừa để quyết định đối tượng cụ thể được tạo ra**. Prototype tạo sản phẩm mới bằng **sao chép một đối tượng mẫu**.

Ba mẫu này có thể **kết hợp**, bởi việc chọn **họ sản phẩm** và cơ chế **tạo từng sản phẩm** là hai quyết định độc lập. Một ConcreteFactory trong Abstract Factory có thể trực tiếp gọi `new`, sử dụng Factory Method qua các phương thức được override, hoặc sao chép những prototype đã cấu hình. Client vẫn dùng cùng một interface Abstract Factory.

Bài thuộc chương **So sánh mẫu thiết kế** của module `SOFTWARE_DESIGN_DESIGN_PATTERN_CREATIONAL_ABSTRACT_FACTORY` trong lộ trình **Học về abstract factory trong design pattern**. Trọng tâm là lựa chọn và hiện thực hai cách kết hợp **Factory Method hoặc Prototype bên trong một ConcreteFactory**, hiểu lợi ích, chi phí, giới hạn và cách kiểm chứng kết quả trong Java.

Sau bài này, bạn có thể:

- Phân biệt **vai trò tạo họ sản phẩm** của Abstract Factory với **cơ chế tạo một sản phẩm** của Factory Method và Prototype.
- Viết một Abstract Factory sử dụng các **factory method được lớp con override** để khởi tạo từng sản phẩm.
- Viết một ConcreteFactory **lưu prototype và trả về bản sao độc lập** qua phương thức `copy()`.
- Nhận biết vì sao **không phải mọi phương thức tên `create...` đều cấu thành mẫu Factory Method** theo nghĩa đầy đủ.
- Giữ tính nhất quán của họ, kiểm soát trạng thái mutable, tham số constructor và vòng đời.
- Đánh giá khi nào nên kết hợp mẫu thiết kế và khi nào gọi constructor trực tiếp là đủ.

## 1. Ba mẫu giải quyết ba câu hỏi khác nhau

Giả sử ứng dụng có hai loại sản phẩm `Button` và `Checkbox`, với hai họ giao diện **Windows** và **macOS**:

~~~java
interface GUIFactory {
    Button createButton();
    Checkbox createCheckbox();
}
~~~

| Mẫu thiết kế | Câu hỏi chính | Vai trò trong ví dụ GUI |
| --- | --- | --- |
| **Abstract Factory** | Làm sao tạo **nhiều loại sản phẩm liên quan** thuộc một họ mà client không phụ thuộc lớp cụ thể? | `GUIFactory` định nghĩa `createButton()` và `createCheckbox()`; Windows/Mac factory tạo sản phẩm tương ứng |
| **Factory Method** | Làm sao cho lớp con quyết định **implementation nào được khởi tạo**, trong khi lớp cha giữ quy trình chung? | Một lớp cha cài đặt luồng tạo, gọi `protected createRawButton()` để lớp Windows/Mac override |
| **Prototype** | Làm sao tạo đối tượng bằng **sao chép từ một mẫu đã cấu hình**? | ConcreteFactory giữ `Button`/`Checkbox` mẫu và gọi `copy()` để cung cấp sản phẩm |

Điểm cần nắm: **Abstract Factory chọn bộ sản phẩm về mặt hợp đồng**, còn Factory Method hay Prototype là một lựa chọn **hiện thực hóa** quá trình tạo đối tượng. Chúng không buộc phải xuất hiện cùng nhau.

### Hai trục độc lập

| Trục | Lựa chọn | Thay đổi ở đâu? |
| --- | --- | --- |
| **Họ sản phẩm** | Windows, macOS, Linux... | Chọn `ConcreteFactory` phù hợp |
| **Cơ chế tạo sản phẩm** | Gọi `new`, Factory Method, Prototype, DI provider... | Chi tiết bên trong factory |

Một `WindowsGUIFactory` có thể thay cách tạo `WindowsButton` từ constructor sang Factory Method mà `GUIFactory` không đổi. Tương tự, một `MacGUIFactory` có thể dùng prototype vì mỗi widget có cấu hình ban đầu phức tạp. **Client không nhất thiết biết hay quan tâm cơ chế nào được sử dụng**.

## 2. Cấu trúc tối thiểu: Abstract Factory với constructor trực tiếp

Trước khi kết hợp thêm mẫu, cần có một cấu trúc nền rõ ràng:

~~~java
interface Button {
    String render();
}

interface Checkbox {
    String render();
}

interface GUIFactory {
    Button createButton();
    Checkbox createCheckbox();
}

final class WindowsGUIFactory implements GUIFactory {
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

`WindowsButton` và `WindowsCheckbox` ở đoạn trên được giả định đã có và cùng triển khai các product interface. Client chỉ phụ thuộc `GUIFactory`:

~~~java
final class Screen {
    private final Button button;
    private final Checkbox checkbox;

    Screen(GUIFactory factory) {
        this.button = factory.createButton();
        this.checkbox = factory.createCheckbox();
    }

    void show() {
        System.out.println(button.render());
        System.out.println(checkbox.render());
    }
}
~~~

Cách này đã là một triển khai **Abstract Factory hợp lệ**. Nếu constructor đơn giản, không có logic chung cần tái sử dụng và không có cấu hình mẫu phức tạp, **không nhất thiết cần thêm Factory Method hoặc Prototype**.

Khi nào một cơ chế khác có giá trị? Chẳng hạn:

- Mọi factory phải làm chung một quy trình **kiểm tra kết quả**, chuẩn hóa thuộc tính hoặc ghi nhận số liệu, nhưng lớp con cần quyết định sản phẩm cụ thể.
- Sản phẩm có một **trạng thái cấu hình mẫu** tốn công xây dựng; mỗi lần tạo sản phẩm cần bắt đầu từ trạng thái đó rồi có thể thay đổi độc lập.
- Có nhiều cách tạo sản phẩm trong cùng một họ và cần một điểm mở rộng rõ ràng để thay đổi cơ chế tạo mà không sửa quy trình chung.

## 3. Kết hợp với Factory Method: lớp cha giữ quy trình, lớp con chọn sản phẩm

Trong **Factory Method**, một lớp creator thường có một thao tác chung và gọi một **phương thức có thể được override** để lấy sản phẩm cụ thể. Khi áp dụng cùng Abstract Factory, ta có thể tạo lớp nền `ValidatingGUIFactory`:

~~~java
abstract class ValidatingGUIFactory implements GUIFactory {
    @Override
    public final Button createButton() {
        Button button = createRawButton();
        return java.util.Objects.requireNonNull(
                button, "createRawButton() returned null");
    }

    @Override
    public final Checkbox createCheckbox() {
        Checkbox checkbox = createRawCheckbox();
        return java.util.Objects.requireNonNull(
                checkbox, "createRawCheckbox() returned null");
    }

    protected abstract Button createRawButton();
    protected abstract Checkbox createRawCheckbox();
}
~~~

Ở đây:

1. `GUIFactory` vẫn là **Abstract Factory**: mô tả hai **loại sản phẩm** mà mọi factory phải tạo.
2. `ValidatingGUIFactory.createButton()` và `createCheckbox()` giữ **quy trình chung**, trong ví dụ là kiểm tra khác `null`.
3. `createRawButton()` và `createRawCheckbox()` là các **Factory Method hook**: lớp con override để lựa chọn cách tạo một sản phẩm cụ thể.
4. Hai phương thức public được đánh dấu `final` để lớp con không vô tình bỏ qua bước kiểm tra chung. Đây là một quyết định thiết kế, không phải yêu cầu bắt buộc của mẫu.

ConcreteFactory Windows chỉ cần định nghĩa các điểm mở rộng:

~~~java
final class WindowsGUIFactory extends ValidatingGUIFactory {
    @Override
    protected Button createRawButton() {
        return new WindowsButton();
    }

    @Override
    protected Checkbox createRawCheckbox() {
        return new WindowsCheckbox();
    }
}
~~~

Mac factory hiện thực tương ứng:

~~~java
final class MacGUIFactory extends ValidatingGUIFactory {
    @Override
    protected Button createRawButton() {
        return new MacButton();
    }

    @Override
    protected Checkbox createRawCheckbox() {
        return new MacCheckbox();
    }
}
~~~

Đây là sự kết hợp rõ ràng giữa **Abstract Factory** và cơ chế **Factory Method**: các factory tạo **bộ sản phẩm**, còn các hook trong từng ConcreteFactory chọn **cách tạo mỗi thành viên**.

### Một nhầm lẫn thường gặp về tên gọi

Vì `GUIFactory` có phương thức `createButton()`, đôi khi người học kết luận rằng “Abstract Factory tự động là Factory Method”. Các mẫu có quan hệ gần gũi, nhưng trong thiết kế cụ thể **chỉ đặt tên `create...` chưa đủ để chứng minh cấu trúc Factory Method**. Điểm quan trọng của ví dụ là **lớp cha khai báo phương thức tạo có thể override và một thao tác chung gọi phương thức ấy**, trao quyền chọn sản phẩm cho lớp con.

Ngược lại, việc một concrete factory đơn giản viết `return new WindowsButton()` đã hoàn toàn đáp ứng Abstract Factory mà không cần thêm một tầng creator riêng.

~~~mermaid
classDiagram
    class GUIFactory {
        <<interface>>
        +createButton() Button
        +createCheckbox() Checkbox
    }
    class ValidatingGUIFactory {
        <<abstract>>
        +createButton() Button
        +createCheckbox() Checkbox
        #createRawButton() Button
        #createRawCheckbox() Checkbox
    }
    class WindowsGUIFactory {
        #createRawButton() Button
        #createRawCheckbox() Checkbox
    }
    class MacGUIFactory {
        #createRawButton() Button
        #createRawCheckbox() Checkbox
    }
    GUIFactory <|.. ValidatingGUIFactory
    ValidatingGUIFactory <|-- WindowsGUIFactory
    ValidatingGUIFactory <|-- MacGUIFactory
~~~

## 4. Ví dụ Java hoàn chỉnh cho cách kết hợp Factory Method

Toàn bộ mã sau thuộc **một file độc lập `FactoryMethodDemo.java`**, có thể biên dịch bằng Java 8 trở lên. Chỉ lớp `FactoryMethodDemo` được khai báo `public`. Các đoạn ở mục trước chỉ để giải thích, không dán lại vào cùng file.

~~~java
import java.util.Objects;

interface Button {
    String render();
}

interface Checkbox {
    String render();
}

interface GUIFactory {
    Button createButton();
    Checkbox createCheckbox();
}

final class WindowsButton implements Button {
    @Override
    public String render() {
        return "Windows button";
    }
}

final class WindowsCheckbox implements Checkbox {
    @Override
    public String render() {
        return "Windows checkbox";
    }
}

final class MacButton implements Button {
    @Override
    public String render() {
        return "macOS button";
    }
}

final class MacCheckbox implements Checkbox {
    @Override
    public String render() {
        return "macOS checkbox";
    }
}

// Quy trình tạo chung + các Factory Method hook.
abstract class ValidatingGUIFactory implements GUIFactory {
    @Override
    public final Button createButton() {
        Button result = createRawButton();
        return Objects.requireNonNull(result, "button");
    }

    @Override
    public final Checkbox createCheckbox() {
        Checkbox result = createRawCheckbox();
        return Objects.requireNonNull(result, "checkbox");
    }

    protected abstract Button createRawButton();
    protected abstract Checkbox createRawCheckbox();
}

final class WindowsGUIFactory extends ValidatingGUIFactory {
    @Override
    protected Button createRawButton() {
        return new WindowsButton();
    }

    @Override
    protected Checkbox createRawCheckbox() {
        return new WindowsCheckbox();
    }
}

final class MacGUIFactory extends ValidatingGUIFactory {
    @Override
    protected Button createRawButton() {
        return new MacButton();
    }

    @Override
    protected Checkbox createRawCheckbox() {
        return new MacCheckbox();
    }
}

final class Screen {
    private final Button button;
    private final Checkbox checkbox;

    Screen(GUIFactory factory) {
        Objects.requireNonNull(factory, "factory");
        this.button = factory.createButton();
        this.checkbox = factory.createCheckbox();
    }

    void show() {
        System.out.println(button.render());
        System.out.println(checkbox.render());
    }
}

public final class FactoryMethodDemo {
    public static void main(String[] args) {
        new Screen(new WindowsGUIFactory()).show();
        new Screen(new MacGUIFactory()).show();
    }
}
~~~

Các lệnh chạy nếu lưu file ở thư mục làm việc dành riêng cho ví dụ:

~~~bash
javac FactoryMethodDemo.java
java FactoryMethodDemo
~~~

Đầu ra dự kiến:

~~~text
Windows button
Windows checkbox
macOS button
macOS checkbox
~~~

**Quan sát:** `Screen` không biết Windows/Mac cũng không biết các hook `createRaw...()`. Nó chỉ gọi hai phương thức của `GUIFactory`. Lớp `ValidatingGUIFactory` kiểm tra `null` một lần cho mọi họ; lớp con quyết định implementation cụ thể cho từng sản phẩm.

### Khi nào cách này có ích?

- Nhiều ConcreteFactory cần **cùng một quy trình tạo**: validation, cấp mã định danh, ghi nhận số liệu hoặc kiểm tra cấu hình, và mỗi lớp con chỉ khác bước khởi tạo.
- Quy tắc chung đủ ổn định để kế thừa; các hook có ranh giới rõ ràng, không buộc lớp con hiểu quá nhiều chi tiết nội bộ.
- Ứng dụng đã dùng một **lớp cơ sở** cho các factory và cần điểm mở rộng tạo sản phẩm nhất quán.

### Đánh đổi

Phương án này bổ sung **kế thừa** và thêm các phương thức hook. Nếu việc tạo chỉ có một lệnh `new` và không có quy trình chung đáng kể, lớp `ValidatingGUIFactory` có thể là một abstraction thừa. Nếu các bước tạo rất khác nhau theo biến thể, một quy trình chung duy nhất có thể trở nên rối rắm hoặc ép lớp con vào luồng xử lý không phù hợp.

Ngoài ra, kiểm tra `null` **không tự bảo đảm** cả hai sản phẩm thuộc đúng họ: `WindowsGUIFactory.createRawCheckbox()` vẫn có thể nhầm trả `new MacCheckbox()`. Cần có kiểm thử riêng theo họ sản phẩm.

## 5. Kết hợp với Prototype: ConcreteFactory sao chép đối tượng mẫu

**Prototype** sử dụng một đối tượng được cấu hình sẵn làm **mẫu**. Khi cần sản phẩm mới, factory gọi một thao tác như `copy()` trên mẫu thay vì tự dựng lại mọi thuộc tính từ đầu.

Ví dụ, một ô chọn mang theme, trạng thái mặc định và nhiều thuộc tính trình bày. Một ConcreteFactory có thể giữ hai mẫu:

~~~java
final class DarkGUIFactory implements GUIFactory {
    private final Button buttonPrototype =
            new ThemedButton(Theme.DARK, "Confirm");
    private final Checkbox checkboxPrototype =
            new ThemedCheckbox(Theme.DARK, false);

    @Override
    public Button createButton() {
        return buttonPrototype.copy();
    }

    @Override
    public Checkbox createCheckbox() {
        return checkboxPrototype.copy();
    }
}
~~~

Ở đây interface sản phẩm phải công bố `copy()` (hoặc ConcreteFactory phụ thuộc vào một interface prototype riêng):

~~~java
interface Button {
    Button copy();
    String render();
}

interface Checkbox {
    Checkbox copy();
    boolean isChecked();
    void setChecked(boolean checked);
    String render();
}
~~~

Factory vẫn thực hiện hợp đồng **Abstract Factory** là tạo `Button` và `Checkbox` thuộc họ Dark; cách làm cụ thể của nó là **sao chép prototype**. `LightGUIFactory` có thể giữ hai mẫu Light và dùng đúng cơ chế đó.

~~~mermaid
flowchart TD
    A["Client"] --> B["GUIFactory.createButton / createCheckbox"]
    B --> C["DarkGUIFactory"]
    C --> D["buttonPrototype.copy()"]
    C --> E["checkboxPrototype.copy()"]
    D --> F["Button Dark mới"]
    E --> G["Checkbox Dark mới"]
~~~

### Vì sao copy phải được thiết kế rõ ràng?

Trong Java, `Object.clone()` là cơ chế cũ có nhiều góc cạnh: `Cloneable` là marker interface, `clone()` của `Object` có quyền truy cập `protected` và việc sao chép mặc định theo trường là **shallow copy**. Với sản phẩm có dữ liệu mutable, sao chép nông có thể làm các đối tượng chia sẻ state không mong muốn.

Với ví dụ học tập, sử dụng **phương thức `copy()` và copy constructor tường minh** thường dễ đọc và kiểm tra hơn. Điều này không có nghĩa `clone()` bị cấm, mà là ngữ nghĩa sao chép cần được thiết kế cụ thể.

## 6. Ví dụ Java hoàn chỉnh cho cách kết hợp Prototype

Ví dụ này **độc lập** với `FactoryMethodDemo.java` ở mục 4. Hãy chạy trong thư mục riêng hoặc project riêng vì các ví dụ dùng lại tên `Button`, `Checkbox`, `GUIFactory`. Lưu đoạn sau thành `PrototypeDemo.java` (Java 8+):

~~~java
import java.util.Objects;

enum Theme {
    LIGHT, DARK
}

interface Button {
    Theme theme();
    String render();
    Button copy();
}

interface Checkbox {
    Theme theme();
    boolean isChecked();
    void setChecked(boolean checked);
    String render();
    Checkbox copy();
}

interface GUIFactory {
    Button createButton();
    Checkbox createCheckbox();
}

final class ThemedButton implements Button {
    private final Theme theme;
    private final String label;

    ThemedButton(Theme theme, String label) {
        this.theme = Objects.requireNonNull(theme, "theme");
        this.label = Objects.requireNonNull(label, "label");
    }

    @Override
    public Theme theme() {
        return theme;
    }

    @Override
    public String render() {
        return theme + " button: " + label;
    }

    @Override
    public Button copy() {
        return new ThemedButton(theme, label);
    }
}

final class ThemedCheckbox implements Checkbox {
    private final Theme theme;
    private boolean checked;

    ThemedCheckbox(Theme theme, boolean checked) {
        this.theme = Objects.requireNonNull(theme, "theme");
        this.checked = checked;
    }

    @Override
    public Theme theme() {
        return theme;
    }

    @Override
    public boolean isChecked() {
        return checked;
    }

    @Override
    public void setChecked(boolean checked) {
        this.checked = checked;
    }

    @Override
    public String render() {
        return theme + " checkbox: "
                + (checked ? "checked" : "unchecked");
    }

    @Override
    public Checkbox copy() {
        return new ThemedCheckbox(theme, checked);
    }
}

final class LightGUIFactory implements GUIFactory {
    private final Button buttonPrototype =
            new ThemedButton(Theme.LIGHT, "Confirm");
    private final Checkbox checkboxPrototype =
            new ThemedCheckbox(Theme.LIGHT, false);

    @Override
    public Button createButton() {
        return buttonPrototype.copy();
    }

    @Override
    public Checkbox createCheckbox() {
        return checkboxPrototype.copy();
    }
}

final class DarkGUIFactory implements GUIFactory {
    private final Button buttonPrototype =
            new ThemedButton(Theme.DARK, "Confirm");
    private final Checkbox checkboxPrototype =
            new ThemedCheckbox(Theme.DARK, false);

    @Override
    public Button createButton() {
        return buttonPrototype.copy();
    }

    @Override
    public Checkbox createCheckbox() {
        return checkboxPrototype.copy();
    }
}

public final class PrototypeDemo {
    public static void main(String[] args) {
        GUIFactory factory = new DarkGUIFactory();

        Button button = factory.createButton();
        Checkbox first = factory.createCheckbox();
        Checkbox second = factory.createCheckbox();

        first.setChecked(true);

        System.out.println(button.render());
        System.out.println(first.render());
        System.out.println(second.render());
        System.out.println("Same checkbox instance: "
                + (first == second));

        GUIFactory lightFactory = new LightGUIFactory();
        System.out.println(lightFactory.createButton().render());
    }
}
~~~

Chạy bằng:

~~~bash
javac PrototypeDemo.java
java PrototypeDemo
~~~

Đầu ra dự kiến:

~~~text
DARK button: Confirm
DARK checkbox: checked
DARK checkbox: unchecked
Same checkbox instance: false
LIGHT button: Confirm
~~~

**Điểm cần quan sát:** hai lần gọi `createCheckbox()` từ cùng `DarkGUIFactory` cho ra **hai instance khác nhau**, nhưng cả hai vẫn thuộc theme Dark. Thay đổi trạng thái `first` không làm `second` chuyển sang `checked`.

Đó là một ví dụ nhỏ về hợp đồng sao chép: bản sao giữ **cấu hình ban đầu cần thiết** (theme và trạng thái mặc định), đồng thời có **trạng thái độc lập** ở những trường được phép thay đổi.

### Khi nào Prototype đáng cân nhắc?

- Đối tượng mẫu có **cấu hình mặc định phức tạp** (theme, style, cấu trúc cây, nhiều tùy chọn) và muốn nhân bản cấu hình nhất quán.
- Loại sản phẩm cụ thể có thể thay đổi theo runtime hoặc cấu hình; factory chỉ cần biết interface `copy()` thay vì mọi tham số khởi tạo.
- Cần sinh nhiều instance từ cùng một mẫu, sau đó cho mỗi instance thay đổi trạng thái độc lập.

### Prototype không tự động nhanh hơn constructor

Ở ví dụ `ThemedCheckbox`, `copy()` thực chất vẫn gọi `new ThemedCheckbox(...)`. Đây là cơ chế nhân bản cấu hình, **không chứng minh lợi ích hiệu năng**. Với đối tượng nhỏ, tạo mới trực tiếp có thể ngắn gọn và nhanh tương đương hoặc tốt hơn. Chỉ khẳng định Prototype cải thiện hiệu suất nếu đã xác định chi phí khởi tạo được tiết kiệm và có đo đạc thực tế.

## 7. Shallow copy, deep copy và nguy cơ chia sẻ trạng thái

Một số sản phẩm có các trường tham chiếu đến đối tượng mutable, chẳng hạn `List<String>` lưu phím tắt hoặc `Map<String, String>` lưu thiết lập. Nếu sao chép chỉ chuyển tham chiếu, sửa bản sao có thể làm mẫu và những bản sao khác cùng thay đổi.

**Ví dụ sai về sao chép danh sách mutable**:

~~~java
final class WidgetConfig {
    private final java.util.List<String> shortcuts;

    WidgetConfig(java.util.List<String> shortcuts) {
        this.shortcuts = shortcuts;
    }

    WidgetConfig copyWrong() {
        // Hai đối tượng vẫn chia sẻ cùng danh sách.
        return new WidgetConfig(shortcuts);
    }
}
~~~

Nếu danh sách được phép thay đổi, cần xác định chính sách:

~~~java
final class WidgetConfig {
    private final java.util.List<String> shortcuts;

    WidgetConfig(java.util.List<String> shortcuts) {
        this.shortcuts = new java.util.ArrayList<>(shortcuts);
    }

    WidgetConfig copy() {
        return new WidgetConfig(shortcuts);
    }
}
~~~

Trong phiên bản sau, constructor tạo một danh sách mới và `copy()` cũng xây dựng đối tượng có danh sách riêng. Đây là **sao chép sâu đến cấp độ danh sách** khi phần tử là `String` bất biến. Nếu phần tử là đối tượng mutable, phải tiếp tục quyết định cách sao chép từng phần tử; `new ArrayList<>(...)` chỉ sao chép danh sách, không tự nhân bản toàn bộ đồ thị đối tượng.

### Đối tượng nào thường không nên sao chép nguyên trạng?

- **Listener, callback, subscription:** bản sao có thể vô tình giữ handler trỏ về widget hoặc màn hình cũ.
- **Socket, file handle, connection:** copy tham chiếu không tạo một tài nguyên độc lập và dễ gây lỗi đóng tài nguyên.
- **Lock hoặc state đa luồng:** chia sẻ sai có thể phá vỡ tính độc lập hoặc thứ tự đồng bộ.
- **Mã định danh duy nhất:** bản sao có thể cần ID mới thay vì sao chép ID của mẫu.
- **Cache gắn với instance:** cần xem có nên dùng chung, đặt lại hay sao chép theo chính sách riêng.

Một phương thức `copy()` tốt cần nêu rõ **những phần được sao chép**, **những phần được tạo mới** và **những dependency được chia sẻ có chủ đích**. Prototype giữ cấu hình; không nên hiểu “copy” là sao chép mù quáng toàn bộ trạng thái chạy.

## 8. Giữ sự tương thích của họ sản phẩm khi phối hợp các mẫu

Tại sao **Abstract Factory** vẫn cần thiết nếu đã có Factory Method hoặc Prototype? Vì chỉ biết cách tạo từng đối tượng **không bảo đảm chúng thuộc cùng họ**.

~~~java
// Có thể biên dịch nếu các lớp đều thực hiện đúng interface:
Button button = new WindowsButton();
Checkbox checkbox = new MacCheckbox();
~~~

Tương tự, concrete factory sử dụng Prototype vẫn có thể gắn nhầm:

~~~java
// Ví dụ lỗi: factory Dark giữ một mẫu Checkbox Light.
private final Checkbox checkboxPrototype =
        new ThemedCheckbox(Theme.LIGHT, false);
~~~

Khi đó `createCheckbox()` vẫn trả về `Checkbox` hợp lệ, và bản sao vẫn độc lập về trạng thái, **nhưng sai họ** so với `DarkGUIFactory`.

Ba lớp bảo đảm nên tách bạch:

1. **Kiểu sản phẩm:** `createButton()` trả đối tượng thực hiện `Button`.
2. **Cơ chế tạo:** Factory Method gọi hook thích hợp hoặc Prototype trả bản sao đúng theo quy ước.
3. **Họ sản phẩm:** mọi sản phẩm do một concrete factory cung cấp thuộc cùng biến thể, thỏa mãn tính tương thích.

Không cơ chế nào ở hai mục đầu **tự động chứng minh** mục thứ ba. Cần thiết kế ranh giới factory rõ ràng và kiểm thử mỗi concrete factory.

## 9. Kiểm thử hai cách kết hợp

### 9.1. Test cho ConcreteFactory dùng Factory Method

Với ví dụ `FactoryMethodDemo.java`, ta có thể kiểm tra rằng hai factory trả sản phẩm đúng loại và không trả `null`:

~~~java
// Ví dụ JUnit Jupiter 5, dùng các kiểu của FactoryMethodDemo.java.
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class FactoryMethodContractTest {
    @Test
    void windowsFactoryUsesWindowsProducts() {
        GUIFactory factory = new WindowsGUIFactory();
        assertInstanceOf(WindowsButton.class, factory.createButton());
        assertInstanceOf(WindowsCheckbox.class, factory.createCheckbox());
    }

    @Test
    void macFactoryUsesMacProducts() {
        GUIFactory factory = new MacGUIFactory();
        assertInstanceOf(MacButton.class, factory.createButton());
        assertInstanceOf(MacCheckbox.class, factory.createCheckbox());
    }
}
~~~

`assertInstanceOf` có trong JUnit Jupiter từ phiên bản 5.8; dự án cần dùng phiên bản hỗ trợ phép kiểm tra này. Nếu hợp đồng cho phép decorator hoặc proxy thay thế các lớp cụ thể, nên kiểm tra **hành vi và biến thể** thay vì luôn khóa cứng tên lớp.

### 9.2. Test cho ConcreteFactory dùng Prototype

Với ví dụ `PrototypeDemo.java`:

~~~java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class PrototypeFactoryContractTest {
    private void assertFamily(GUIFactory factory, Theme theme) {
        Button button = factory.createButton();
        Checkbox checkbox = factory.createCheckbox();

        assertNotNull(button);
        assertNotNull(checkbox);
        assertEquals(theme, button.theme());
        assertEquals(theme, checkbox.theme());
    }

    @Test
    void factoriesPreserveFamily() {
        assertFamily(new LightGUIFactory(), Theme.LIGHT);
        assertFamily(new DarkGUIFactory(), Theme.DARK);
    }

    @Test
    void copiedCheckboxesDoNotShareMutableState() {
        GUIFactory factory = new DarkGUIFactory();
        Checkbox first = factory.createCheckbox();
        Checkbox second = factory.createCheckbox();

        assertNotSame(first, second);
        first.setChecked(true);

        assertTrue(first.isChecked());
        assertFalse(second.isChecked());
        assertFalse(factory.createCheckbox().isChecked());
    }
}
~~~

Test thứ hai phát hiện tình huống `copy()` trả về **chính prototype** hoặc chia sẻ trạng thái checked giữa các bản sao. Nó cũng xác minh prototype không bị thay đổi do client sửa một sản phẩm đã cấp.

**Lưu ý về hợp đồng vòng đời:** chỉ dùng `assertNotSame` khi factory thực sự **cam kết tạo sản phẩm độc lập**. Abstract Factory không mặc định yêu cầu mỗi lần gọi phải có instance mới; trong hệ thống cho phép singleton sản phẩm bất biến, việc bắt buộc `assertNotSame` sẽ là test quá chặt.

### 9.3. Kiểm thử điều gì ở mỗi lớp?

| Đối tượng kiểm thử | Nên xác minh | Không nên suy diễn |
| --- | --- | --- |
| `GUIFactory` và từng concrete factory | Đầy đủ loại sản phẩm, đúng họ, kết quả hợp lệ | Kiểu trả về của Java bảo đảm đúng họ |
| Factory Method hook | Lớp con chọn đúng implementation; quy trình chung được chạy | Mọi phương thức tên `create` đều là mẫu Factory Method riêng |
| `copy()` của Prototype | Giữ cấu hình cần thiết; state mutable được tách đúng mức | `clone()`/copy luôn là deep copy |
| Client dùng `GUIFactory` | Không cần biết họ hoặc cơ chế tạo sản phẩm | Client phải biết factory đang dùng `new` hay prototype |

## 10. Chọn cơ chế theo nguyên nhân thay đổi

| Điều kiện trong dự án | Lựa chọn thường hợp lý | Lý do |
| --- | --- | --- |
| Constructor đơn giản, ít quy tắc khởi tạo | `new` trực tiếp trong ConcreteFactory | Ít lớp, dễ đọc, đáp ứng đủ Abstract Factory |
| Nhiều họ dùng chung quy trình tạo nhưng khác bước khởi tạo sản phẩm | Factory Method hook | Giữ quy trình chung, cho lớp con quyết định từng sản phẩm |
| Mẫu sản phẩm có cấu hình phức tạp và cần nhiều bản sao | Prototype | Nhân bản trạng thái mẫu qua `copy()` có quy ước |
| Cần chọn nhà cung cấp ở runtime và framework DI đã hỗ trợ | DI/provider | Giữ Abstract Factory khi nó thể hiện nhóm sản phẩm tương thích thực sự |
| Mỗi loại sản phẩm có constructor khác nhau, không có luồng chung | Direct creation hoặc helper nhỏ | Kế thừa Factory Method có thể gây phức tạp |
| Sản phẩm sở hữu tài nguyên không sao chép được | Constructor/builder/factory specialized | Prototype cần quy tắc sao chép phức tạp và dễ lỗi |
| Các họ không còn hỗ trợ cùng tập loại sản phẩm | Xem lại interface Abstract Factory | Factory Method/Prototype không sửa được hợp đồng họ quá rộng |

### Ba câu hỏi để tránh kết hợp thừa

1. **Quy trình tạo có thực sự cần tái sử dụng bằng kế thừa?** Nếu không, Factory Method hook có thể chỉ làm tăng số phương thức.
2. **Đối tượng mẫu có mang cấu hình đáng sao chép không?** Nếu không, dùng `new` có thể đơn giản hơn Prototype.
3. **Cả hai loại sản phẩm có thật sự cần đi theo cùng một họ không?** Nếu không, việc ghép thành Abstract Factory có thể tạo coupling không cần thiết.

Hãy chọn cơ chế đơn giản nhất đáp ứng hợp đồng và khả năng thay đổi của hệ thống. “Kết hợp càng nhiều design pattern càng tốt” không phải mục tiêu thiết kế.

## 11. Rủi ro khi phối hợp các mẫu

### 11.1. Quá nhiều tầng lớp và phương thức

Nếu với mỗi sản phẩm đều có `ProductCreator`, `ConcreteProductCreator`, `PrototypeProvider`, `ConcreteFactory`, `FactoryRegistry` nhưng hệ thống chỉ có vài constructor đơn giản, developer phải đi qua nhiều file mới tìm thấy một lệnh tạo đối tượng. Chi phí bảo trì và review có thể tăng hơn lợi ích trừu tượng hóa.

### 11.2. Kế thừa không thích hợp với biến thể

Factory Method dựa vào override. Nếu một họ cần logic tạo hoàn toàn khác hoặc nhiều tổ hợp hành vi tại runtime, ép tất cả vào một lớp cha có thể dẫn đến hook trống, override nhiều phương thức không liên quan, hoặc `if/else` phức tạp trong lớp cha. Khi đó, composition bằng collaborator hoặc provider có thể phù hợp hơn kế thừa.

### 11.3. Copy không tách đúng state

Một `Checkbox` có trạng thái mutable không nên được trả về cùng một instance cho nhiều màn hình nếu các màn hình cần độc lập. Sao chép nông một đối tượng chứa `List` hoặc listener cũng dễ rò rỉ trạng thái. Test phải phản ánh **hợp đồng cụ thể về state**, không chỉ kiểm tra kiểu.

### 11.4. Cấu hình prototype bị sửa sau khi tạo factory

Nếu ConcreteFactory cho client giữ tham chiếu đến prototype mutable, một nơi có thể sửa mẫu và khiến các sản phẩm tạo sau thay đổi ngoài ý muốn. Nên giữ prototype ở trạng thái ổn định hoặc **sao chép phòng vệ** khi nhận prototype từ bên ngoài.

### 11.5. Nhầm phạm vi sống và tài nguyên

Prototype phù hợp với state sao chép được. Copy kết nối mạng đang mở hoặc một GUI widget đang gắn vào event loop có thể không hợp lệ. Nếu sản phẩm phải đăng ký callback hoặc mở tài nguyên mới, cơ chế `copy()` cần tạo lại những thành phần theo đúng vòng đời; nếu quá khó, nên quay về factory chuyên dụng hoặc builder.

### 11.6. Hợp đồng factory vẫn có thể bị vi phạm

Dù dùng Factory Method hay Prototype, concrete factory vẫn có thể trả `null` hoặc sản phẩm sai họ. Đừng dùng tên mẫu như một sự bảo đảm; phải có test hợp đồng đúng như client kỳ vọng.

## 12. Quy trình áp dụng vào codebase Java hiện hữu

Khi nhận nhiệm vụ thay đổi cơ chế tạo sản phẩm trong Abstract Factory, nên thực hiện theo trình tự:

1. **Ghi hợp đồng hiện tại:** `GUIFactory` cần trả những loại sản phẩm nào, biến thể ra sao, có quy tắc vòng đời hay `null` không.
2. **Phân loại chi phí tạo:** constructor trực tiếp đủ dùng, có quy trình kiểm tra lặp, hay có cấu hình mẫu cần sao chép?
3. **Chọn một cơ chế bên trong factory:** Factory Method nếu cần template + hook; Prototype nếu cần copy state mẫu; `new` trực tiếp nếu không cần lớp bổ sung.
4. **Giữ API client ổn định:** cố gắng để `GUIFactory.createButton()`/`createCheckbox()` giữ cùng hợp đồng; tránh rò rỉ `clone()`, constructor hoặc tên subclass vào code khách hàng.
5. **Xác định dữ liệu dùng chung có chủ đích:** đối với Prototype, ghi rõ trường nào được chia sẻ, trường nào phải deep copy, trường nào khởi tạo lại.
6. **Kiểm tra tính nhất quán của họ:** mỗi ConcreteFactory tạo đúng nhóm sản phẩm, kể cả khi phần khởi tạo được ủy quyền cho hook hoặc prototype.
7. **Test từng lớp trách nhiệm:** test hợp đồng factory, test hook khi có quy trình chung, test copy independence với state mutable.
8. **Đánh giá khả năng đọc và chi phí bảo trì:** nếu việc điều hướng giữa lớp cha, subclass và prototype nhiều hơn lợi ích mang lại, thu gọn thiết kế.

Ví dụ, khi thay `new DarkCheckbox()` bằng `checkboxPrototype.copy()`, không nên chỉ kiểm tra màn hình vẫn hiển thị Dark. Cần kiểm tra **hai checkbox ở hai màn hình không chia sẻ trạng thái** và factory vẫn trả đúng loại sản phẩm.

## 13. Bài tập phân tích

### Bài tập A — Xác định mẫu nào đang hoạt động

~~~java
interface GUIFactory {
    Button createButton();
    Checkbox createCheckbox();
}

final class DarkFactory implements GUIFactory {
    private final Button prototype = new DarkButton();

    @Override
    public Button createButton() {
        return prototype.copy();
    }

    @Override
    public Checkbox createCheckbox() {
        return new DarkCheckbox();
    }
}
~~~

**Hỏi:** Thiết kế dùng mẫu nào ở mức hợp đồng? Trong các phương thức tạo sản phẩm, phương thức nào áp dụng Prototype? Có bắt buộc cả hai phương thức phải dùng Prototype mới được gọi là Abstract Factory không?

*Gợi ý:* `DarkFactory` vẫn là một ConcreteFactory trong Abstract Factory. Cơ chế tạo từng loại sản phẩm có thể khác nhau nếu hợp đồng về họ và hành vi được giữ.

### Bài tập B — Có thật sự cần Factory Method?

Hai factory chỉ khác nhau ở `new WindowsButton()` và `new MacButton()`, không có bước xử lý chung khác. Nhóm đề xuất lớp `AbstractButtonCreator`, hai lớp con và một `GUIFactory` chỉ để gọi creator.

**Hỏi:** Lợi ích cụ thể nào đủ để trả chi phí thêm ba lớp? Khi không có lợi ích rõ ràng, bạn có giữ constructor trực tiếp không?

### Bài tập C — Phát hiện lỗi copy

~~~java
final class CheckboxState {
    final java.util.List<String> listeners;

    CheckboxState(java.util.List<String> listeners) {
        this.listeners = listeners;
    }

    CheckboxState copy() {
        return new CheckboxState(listeners);
    }
}
~~~

**Hỏi:** Hai bản sao có chia sẻ cùng `List` không? Nếu sửa danh sách của một bản sao, bản còn lại có bị ảnh hưởng không? Khi nào nên tạo danh sách mới và khi nào việc sao chép listener vẫn chưa đủ an toàn?

### Bài tập D — Kiểm thử họ sản phẩm

Một `DarkGUIFactory` dùng Prototype tạo `Button` và `Checkbox`. `Button` có `theme() == DARK` nhưng `Checkbox` có `theme() == LIGHT`. Test hiện tại chỉ kiểm tra `assertNotNull`.

**Hỏi:** Những assertion nào cần bổ sung để phát hiện sai họ? Nếu checkbox có state mutable, cần test thêm điều gì về hai lần gọi `createCheckbox()`?

### Bài tập E — So sánh chi phí thay đổi

Ứng dụng cần tạo các widget có hàng chục thuộc tính trình bày nhưng chỉ ba loại cấu hình chuẩn. Nhóm đang gọi một constructor với nhiều tham số tại mỗi factory. Đề xuất dùng Prototype.

**Hỏi:** Những thuộc tính nào phải được copy, phần nào phải khởi tạo lại, test nào chứng minh hai bản sao độc lập? Lợi ích gì nếu cấu hình thường xuyên thay đổi? Khi nào Builder có thể phù hợp hơn?

## 14. Checklist trước khi kết hợp mẫu thiết kế

- [ ] Đã xác định đúng **trách nhiệm của Abstract Factory** là tạo một họ gồm những loại sản phẩm liên quan.
- [ ] Đã tách bạch **chọn họ sản phẩm** và **cơ chế tạo từng sản phẩm**.
- [ ] Chỉ dùng Factory Method khi có quy trình chung và hook kế thừa tạo giá trị thực tế.
- [ ] Chỉ dùng Prototype khi có cấu hình mẫu cần tái sử dụng và ngữ nghĩa sao chép được định nghĩa rõ.
- [ ] Không coi mọi phương thức tên `create...` là bằng chứng đủ cho mẫu Factory Method.
- [ ] Mã khách hàng chỉ sử dụng `GUIFactory` và product interface, không phụ thuộc `new`, hook hay prototype.
- [ ] Mỗi ConcreteFactory tạo **đủ loại sản phẩm, cùng họ, đúng hợp đồng**.
- [ ] Với sản phẩm mutable, `copy()` không làm rò rỉ trạng thái giữa mẫu và các bản sao.
- [ ] Không copy mù quáng socket, listener, lock, ID hoặc tài nguyên có vòng đời đặc biệt.
- [ ] Không khẳng định Prototype nhanh hơn nếu chưa có phép đo với trường hợp thực tế.
- [ ] Có unit test cho từng concrete factory, cơ chế tạo và các bất biến quan trọng.
- [ ] Đã so sánh chi phí abstraction mới với cách tạo trực tiếp đơn giản hơn.

**Ghi nhớ:** Abstract Factory trả lời **“lấy một bộ sản phẩm thuộc họ nào?”**; Factory Method trả lời **“lớp con nào quyết định từng sản phẩm được khởi tạo?”**; Prototype trả lời **“làm thế nào sinh sản phẩm từ một mẫu có sẵn?”**. Khi kết hợp, hãy giữ hợp đồng tạo họ sản phẩm ổn định và chỉ dùng cơ chế bổ sung khi nó thật sự giúp quản lý thay đổi, cấu hình hoặc vòng đời của đối tượng.

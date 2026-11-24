# Xây dựng Application nhận GUIFactory và phối hợp các sản phẩm

Trong **Abstract Factory**, việc khai báo `GUIFactory` và hiện thực các `ConcreteFactory` mới giải quyết được phần **tạo đối tượng**. Bước tiếp theo là đưa chúng vào một ứng dụng thực tế: lớp `Application` cần một nút bấm (`Button`) và một ô chọn (`Checkbox`), phải làm cho chúng hoạt động cùng nhau, nhưng **không nên tự quyết định** dùng `WindowsButton`, `MacButton` hay các lớp cụ thể khác.

Cách triển khai là để `Application` **nhận một đối tượng `GUIFactory` từ bên ngoài**, gọi các phương thức tạo sản phẩm trên chính factory đó, rồi phối hợp những sản phẩm thông qua interface. Nơi khởi động ứng dụng chọn concrete factory phù hợp với cấu hình. Nhờ vậy, cùng một `Application` có thể phục vụ nhiều họ giao diện mà không phải viết lại logic điều phối.

Bài thuộc chương **Hiện thực bằng Java** của module `SOFTWARE_DESIGN_DESIGN_PATTERN_CREATIONAL_ABSTRACT_FACTORY`, trong lộ trình **Học về abstract factory trong design pattern**. Trọng tâm là **xây dựng `Application` nhận `GUIFactory` và phối hợp các sản phẩm**, với ví dụ Java chạy độc lập, phân tích vòng đời và phương pháp kiểm thử.

Sau bài này, bạn có thể:

- Khai báo constructor `Application(GUIFactory factory)` và lưu/khai thác dependency theo abstraction.
- Tạo `Button` và `Checkbox` từ **cùng một factory đã chọn**.
- Gắn sự kiện của nút bấm với trạng thái ô chọn mà không biết các lớp cụ thể.
- Đặt logic chọn Windows/macOS ở điểm khởi tạo (*composition root*).
- Phân biệt trách nhiệm của `Application`, `GUIFactory`, concrete factory và concrete product.
- Viết unit test cho hoạt động điều phối của `Application` bằng fake factory.

## 1. Xác định trách nhiệm của từng thành phần

Giả sử ứng dụng có một nút “Toggle” và một ô chọn. Khi người dùng nhấn nút, trạng thái ô chọn đảo từ *chưa chọn* sang *đã chọn*, hoặc ngược lại. Ứng dụng chạy trên Windows hay macOS thì quy tắc tương tác này vẫn giống nhau; chỉ **cách hiển thị** các điều khiển là khác.

| Thành phần | Trách nhiệm | Điều không cần biết |
| --- | --- | --- |
| `Application` | Yêu cầu các sản phẩm, gắn sự kiện và điều phối thao tác chung | Tên các lớp `WindowsButton`, `MacCheckbox`... |
| `GUIFactory` | Khai báo cách yêu cầu `Button` và `Checkbox` | Chi tiết dựng từng sản phẩm |
| `WindowsFactory` | Tạo `WindowsButton` và `WindowsCheckbox` | Luồng tương tác của `Application` |
| `MacFactory` | Tạo `MacButton` và `MacCheckbox` | Luồng tương tác của `Application` |
| `Button` | Khai báo thao tác với nút, bao gồm sự kiện nhấn | Cách một concrete factory chọn nền tảng |
| `Checkbox` | Khai báo đọc/đổi trạng thái ô chọn | Cách một concrete factory chọn nền tảng |
| `Demo.main()` | Chọn cấu hình nền tảng và cung cấp factory cho `Application` | Chi tiết điều phối button và checkbox |

Điểm quan trọng: **`Application` được phép phối hợp các đối tượng**, bởi đó là trách nhiệm của nó. Điều cần tránh là để `Application` **tự chọn constructor cụ thể theo nền tảng** mỗi khi cần tạo UI.

~~~mermaid
flowchart TD
    P["Cấu hình nền tảng"] --> C["Composition root / Demo.main"]
    C --> WF["WindowsFactory"]
    C --> MF["MacFactory"]
    WF --> F["GUIFactory được chọn"]
    MF --> F
    F --> A["Application(GUIFactory)"]
    A --> B["createButton() → Button"]
    A --> X["createCheckbox() → Checkbox"]
    B --> E["Sự kiện click"]
    E --> X
~~~

Sơ đồ thể hiện **một trong hai** concrete factory được chọn cho một instance `Application`. Nó không hàm ý cả Windows và macOS cùng được lắp ráp vào một instance.

## 2. Đoạn mã ban đầu: Application vừa chọn vừa điều phối

Một cách viết thường gặp là phân nhánh trực tiếp trong lớp ứng dụng:

~~~java
final class Application {
    private Button button;
    private Checkbox checkbox;

    Application(Platform platform) {
        if (platform == Platform.WINDOWS) {
            button = new WindowsButton();
            checkbox = new WindowsCheckbox();
        } else if (platform == Platform.MACOS) {
            button = new MacButton();
            checkbox = new MacCheckbox();
        } else {
            throw new IllegalArgumentException("Unsupported platform");
        }

        button.onClick(() ->
                checkbox.setChecked(!checkbox.isChecked()));
    }
}
~~~

Đoạn mã rút gọn này cho thấy hai trách nhiệm bị đặt trong một constructor:

1. **Lựa chọn họ sản phẩm:** đọc `Platform` và dùng các lệnh `new` để quyết định hai implementation cụ thể.
2. **Điều phối sản phẩm:** nối sự kiện của `Button` với trạng thái `Checkbox`.

Khi thêm Linux, nhánh khởi tạo của `Application` lại phải thay đổi dù quy tắc “nhấn nút thì đảo trạng thái ô chọn” giữ nguyên. Nếu có nhiều màn hình cùng cần những thành phần thuộc một nền tảng, logic chọn có thể xuất hiện ở nhiều nơi. Một lỗi ghép nhầm `WindowsButton` với `MacCheckbox` cũng không nhất thiết bị trình biên dịch phát hiện.

Trong Abstract Factory, ta chuyển **trách nhiệm thứ nhất** ra ngoài `Application` và giữ **trách nhiệm thứ hai** tại lớp điều phối.

## 3. Định nghĩa sản phẩm và hợp đồng factory

Trước tiên, `Application` cần những hành vi nào từ sản phẩm?

- `Button` cho phép đăng ký xử lý sự kiện, mô phỏng một lần nhấn và hiển thị mô tả.
- `Checkbox` cho phép đọc/đổi trạng thái đã chọn và hiển thị mô tả.

Hai product interface trong ví dụ:

~~~java
interface Button {
    void onClick(Runnable handler);
    void click();
    String render();
}

interface Checkbox {
    boolean isChecked();
    void setChecked(boolean checked);
    String render();
}
~~~

`Runnable` là functional interface có sẵn trong Java. Đăng ký `Runnable` qua `onClick(...)` là cách mô phỏng một event handler gọn, không cần thư viện GUI. Trong Swing, JavaFX hoặc một framework khác, cách đăng ký và phát sự kiện sẽ theo API riêng của framework.

Abstract Factory khai báo **hai phương thức tạo sản phẩm liên quan**:

~~~java
interface GUIFactory {
    Button createButton();
    Checkbox createCheckbox();
}
~~~

Chữ ký `Button createButton()` có nghĩa: “Hãy cung cấp một đối tượng thực hiện `Button`”. Nó không nói sản phẩm phải là Windows hay macOS. Tương tự, `Checkbox createCheckbox()` không cho biết lớp cụ thể được tạo.

Khi factory là `WindowsFactory`, cả hai phương thức cần tạo sản phẩm thuộc họ Windows; khi là `MacFactory`, cả hai phải tạo sản phẩm thuộc họ macOS. **Đây là cam kết của từng concrete factory**, không phải điều Java tự suy ra chỉ từ kiểu trả về `Button` và `Checkbox`.

## 4. Application chỉ nhận GUIFactory và lắp ráp tương tác

Phần quan trọng nhất có thể viết độc lập với mọi lớp sản phẩm cụ thể:

~~~java
import java.util.Objects;

final class Application {
    private final Button button;
    private final Checkbox checkbox;

    Application(GUIFactory factory) {
        Objects.requireNonNull(factory, "factory");

        this.button = Objects.requireNonNull(
                factory.createButton(), "button");
        this.checkbox = Objects.requireNonNull(
                factory.createCheckbox(), "checkbox");

        button.onClick(() ->
                checkbox.setChecked(!checkbox.isChecked()));
    }

    void runDemo() {
        System.out.println(button.render());
        System.out.println(checkbox.render());

        // Mô phỏng người dùng nhấn nút trong ví dụ console.
        button.click();
        System.out.println(checkbox.render());
    }
}
~~~

Constructor giải quyết **ba bước**:

1. **Nhận factory:** `Application(GUIFactory factory)` thể hiện phụ thuộc qua interface và cho phép bên ngoài quyết định biến thể.
2. **Lấy bộ sản phẩm:** cùng một `factory` tạo `button` và `checkbox`. `Application` chỉ giữ chúng dưới kiểu `Button`, `Checkbox`.
3. **Phối hợp hành vi:** gắn handler `button.onClick(...)`; khi nút được nhấn, handler đọc trạng thái ô chọn rồi ghi lại trạng thái ngược lại.

Từ đoạn code trên có thể thấy `Application` **không nhập hay tham chiếu** `WindowsButton`, `WindowsCheckbox`, `MacButton`, `MacCheckbox`. Khi đổi họ sản phẩm, logic tương tác vẫn không thay đổi.

Việc dùng `Objects.requireNonNull` giúp thất bại sớm nếu factory hoặc sản phẩm bị trả về `null`. Đây là kiểm tra phòng vệ được thêm vào `Application`, không phải bảo đảm mặc định của Abstract Factory.

### Vì sao tạo sản phẩm trong constructor?

Ở ví dụ này, mỗi `Application` sở hữu một cặp button/checkbox cho toàn bộ vòng đời của nó. Vì vậy tạo trong constructor và lưu vào các trường `final` là dễ hiểu. Nếu ứng dụng quản lý **nhiều cửa sổ**, mỗi cửa sổ cần các điều khiển khác nhau, có thể giữ lại `GUIFactory` và gọi các phương thức tạo cho từng cửa sổ:

~~~java
final class WindowBuilder {
    private final GUIFactory factory;

    WindowBuilder(GUIFactory factory) {
        this.factory = factory;
    }

    void openNewWindow() {
        Button button = factory.createButton();
        Checkbox checkbox = factory.createCheckbox();
        // Gắn hành vi và đưa sản phẩm vào cửa sổ mới.
    }
}
~~~

Đây là một **phương án vòng đời khác**, không thay thế code chạy chính. Abstract Factory không quy định sản phẩm phải được tạo một lần, tạo lại mỗi lần hay cache; quyết định này phụ thuộc vòng đời và hợp đồng của từng sản phẩm.

## 5. Ví dụ Java hoàn chỉnh có thể chạy

Ví dụ sau ghép tất cả thành phần trong **một file** `src/main/java/example/abstractfactory/Demo.java`. Mã dùng Java 8+; không cần Swing/JavaFX để chạy vì `render()` trả chuỗi và `click()` mô phỏng sự kiện. Chỉ `Demo` được khai báo `public`, các kiểu còn lại có quyền truy cập trong package. Các đoạn code ở mục trước là phần giải thích và không được dán lặp thêm vào cùng file này.

~~~java
package example.abstractfactory;

import java.util.Locale;
import java.util.Objects;

enum Platform {
    WINDOWS, MACOS
}

interface Button {
    void onClick(Runnable handler);
    void click();
    String render();
}

interface Checkbox {
    boolean isChecked();
    void setChecked(boolean checked);
    String render();
}

interface GUIFactory {
    Button createButton();
    Checkbox createCheckbox();
}

final class WindowsButton implements Button {
    private Runnable handler = () -> {};

    @Override
    public void onClick(Runnable handler) {
        this.handler = Objects.requireNonNull(handler, "handler");
    }

    @Override
    public void click() {
        handler.run();
    }

    @Override
    public String render() {
        return "[Windows Button: Toggle]";
    }
}

final class WindowsCheckbox implements Checkbox {
    private boolean checked;

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
        return "[Windows Checkbox: "
                + (checked ? "checked" : "unchecked") + "]";
    }
}

final class MacButton implements Button {
    private Runnable handler = () -> {};

    @Override
    public void onClick(Runnable handler) {
        this.handler = Objects.requireNonNull(handler, "handler");
    }

    @Override
    public void click() {
        handler.run();
    }

    @Override
    public String render() {
        return "(macOS Button: Toggle)";
    }
}

final class MacCheckbox implements Checkbox {
    private boolean checked;

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
        return "(macOS Checkbox: "
                + (checked ? "checked" : "unchecked") + ")";
    }
}

final class WindowsFactory implements GUIFactory {
    @Override
    public Button createButton() {
        return new WindowsButton();
    }

    @Override
    public Checkbox createCheckbox() {
        return new WindowsCheckbox();
    }
}

final class MacFactory implements GUIFactory {
    @Override
    public Button createButton() {
        return new MacButton();
    }

    @Override
    public Checkbox createCheckbox() {
        return new MacCheckbox();
    }
}

final class Application {
    private final Button button;
    private final Checkbox checkbox;

    Application(GUIFactory factory) {
        Objects.requireNonNull(factory, "factory");
        this.button = Objects.requireNonNull(
                factory.createButton(), "button");
        this.checkbox = Objects.requireNonNull(
                factory.createCheckbox(), "checkbox");

        button.onClick(() ->
                checkbox.setChecked(!checkbox.isChecked()));
    }

    void runDemo() {
        System.out.println(button.render());
        System.out.println(checkbox.render());
        button.click();
        System.out.println(checkbox.render());
    }
}

final class GUIFactorySelector {
    private GUIFactorySelector() {}

    static GUIFactory forPlatform(Platform platform) {
        Objects.requireNonNull(platform, "platform");
        switch (platform) {
            case WINDOWS:
                return new WindowsFactory();
            case MACOS:
                return new MacFactory();
            default:
                throw new IllegalArgumentException(
                        "Unsupported platform: " + platform);
        }
    }
}

public final class Demo {
    public static void main(String[] args) {
        Platform platform = args.length == 0
                ? Platform.WINDOWS
                : Platform.valueOf(
                        args[0].toUpperCase(Locale.ROOT));

        GUIFactory factory = GUIFactorySelector.forPlatform(platform);
        Application app = new Application(factory);
        app.runDemo();
    }
}
~~~

### Chạy ví dụ

Đặt file tại đường dẫn nói trên. Từ thư mục gốc của dự án ví dụ, bạn có thể biên dịch và chạy bằng JDK tương thích:

~~~bash
javac -d out src/main/java/example/abstractfactory/Demo.java
java -cp out example.abstractfactory.Demo WINDOWS
java -cp out example.abstractfactory.Demo MACOS
~~~

Đây là **hướng dẫn thực hành**; không phải log từ một lần chạy đã được thực thi.

Với đối số `WINDOWS`, đầu ra dự kiến:

~~~text
[Windows Button: Toggle]
[Windows Checkbox: unchecked]
[Windows Checkbox: checked]
~~~

Với `MACOS`, đầu ra dự kiến:

~~~text
(macOS Button: Toggle)
(macOS Checkbox: unchecked)
(macOS Checkbox: checked)
~~~

So sánh hai lần chạy: hai dòng `render()` phản ánh sản phẩm thuộc nền tảng khác nhau, nhưng **logic nút nhấn đảo trạng thái ô chọn vẫn là cùng một đoạn code trong `Application`**.

### Sự kiện được phối hợp như thế nào?

~~~mermaid
sequenceDiagram
    participant M as Demo.main
    participant F as GUIFactory
    participant A as Application
    participant B as Button
    participant C as Checkbox
    M->>A: new Application(factory)
    A->>F: createButton()
    F-->>A: Button
    A->>F: createCheckbox()
    F-->>A: Checkbox
    A->>B: onClick(handler)
    M->>A: runDemo()
    A->>B: click()
    B-->>A: Chạy handler đã đăng ký
    A->>C: isChecked()
    C-->>A: false
    A->>C: setChecked(true)
~~~

Sơ đồ tập trung vào một lần nhấn đầu tiên. Trong ví dụ, handler do `Application` đăng ký; nó truy cập `checkbox` qua interface và không cần biết checkbox được tạo bởi Windows hay macOS factory.

## 6. Composition root là nơi quyết định chọn concrete factory

`GUIFactorySelector.forPlatform(...)` có thể dùng `switch` hoặc được thay bằng cấu hình dependency injection. Dù chọn cách nào, **phần chọn biến thể nên nằm ở nơi lắp ráp ứng dụng** thay vì lặp lại trong `Application`:

~~~java
GUIFactory factory =
        GUIFactorySelector.forPlatform(Platform.MACOS);

Application application = new Application(factory);
application.runDemo();
~~~

Trong ví dụ:

1. `Demo.main()` biết nền tảng đang được yêu cầu.
2. `GUIFactorySelector` biết ánh xạ từ nền tảng sang concrete factory.
3. `Application` biết hợp đồng của factory và các sản phẩm, nhưng không biết ánh xạ trên.

Điểm lắp ráp này thường được gọi là *composition root*. Việc dùng một lớp `GUIFactorySelector` riêng là lựa chọn tổ chức; nếu ứng dụng nhỏ, phép chọn trực tiếp trong `main()` cũng có thể rõ ràng. Không cần tạo thêm một abstraction cho mỗi lệnh `new`.

### Vì sao không gọi `GUIFactorySelector` trong Application?

Nếu constructor là `Application(Platform platform)` rồi bên trong tự gọi `GUIFactorySelector.forPlatform(platform)`, lớp `Application` vẫn phải biết **nguồn chọn biến thể** và phải gọi đến thành phần lựa chọn. Điều đó hạn chế việc cấp một factory giả trong unit test và làm mờ ranh giới dependency.

Constructor `Application(GUIFactory factory)` thể hiện rõ nguyên tắc **Dependency Inversion**: mã điều phối phụ thuộc vào **abstraction**, và một thành phần bên ngoài quyết định cung cấp implementation nào.

### Factory được chọn một lần hay theo từng màn hình?

Điều này phụ thuộc phạm vi hiệu lực của biến thể:

- **Một nền tảng ổn định cho toàn ứng dụng:** có thể chọn factory một lần khi khởi động rồi cấp cho các màn hình.
- **Một chủ đề giao diện thay đổi khi chạy:** có thể cần tạo lại sản phẩm hoặc xây dựng lại màn hình khi đổi theme; giữ nguyên factory cũ không tự cập nhật giao diện.
- **Nhiều cửa sổ/phiên độc lập:** mỗi phiên có thể nhận factory tương ứng với cấu hình riêng.

Trong cả ba trường hợp, nguyên tắc giữ nguyên: **đối tượng điều phối nhận dependency phù hợp với phạm vi sống của nó**, không tự tái diễn các nhánh chọn biến thể ở mọi thao tác.

## 7. Điều phối sản phẩm và bảo toàn tính nhất quán của họ

Mã `Application` lấy hai sản phẩm từ cùng một factory:

~~~java
Button button = factory.createButton();
Checkbox checkbox = factory.createCheckbox();
~~~

Đó là cách **giảm nguy cơ** ghép nhầm sản phẩm. Ví dụ `WindowsFactory` cần cung cấp cả `WindowsButton` và `WindowsCheckbox`. Nhưng Java chỉ kiểm tra rằng kiểu trả về tương thích với `Button` và `Checkbox`; **nó không ngăn** implementation sau:

~~~java
final class BrokenWindowsFactory implements GUIFactory {
    @Override
    public Button createButton() {
        return new WindowsButton();
    }

    @Override
    public Checkbox createCheckbox() {
        return new MacCheckbox(); // Sai họ, vẫn có thể biên dịch
    }
}
~~~

Để bảo vệ quy tắc cùng họ, cần test mỗi concrete factory hoặc dùng các hợp đồng thể hiện rõ thuộc tính tương thích trong hệ thống thật. `Application` không nên tự chữa lỗi này bằng những nhánh như `if (checkbox instanceof MacCheckbox)`; như vậy lớp điều phối lại phải biết các implementation cụ thể.

### Không phải mọi phương thức của Application đều thuộc factory

Ví dụ handler:

~~~java
button.onClick(() ->
        checkbox.setChecked(!checkbox.isChecked()));
~~~

Đây là **logic phối hợp giao diện**, không phải logic tạo sản phẩm. Đưa nó vào `WindowsFactory` và `MacFactory` sẽ khiến cùng một quy tắc tương tác bị lặp theo từng nền tảng. Hãy giữ nó tại `Application` hoặc một thành phần điều phối chung tương đương.

Ngược lại, nếu mỗi nền tảng có cách tạo nút cần nhiều dependency nội bộ, phần đó thuộc concrete factory và implementation sản phẩm, không nên bị kéo vào `Application`.

## 8. Unit test: kiểm tra Application bằng fake GUIFactory

Lợi ích lớn của constructor injection là có thể kiểm tra **cách `Application` lắp ráp tương tác** mà không cần tạo giao diện thực. Ta cung cấp một fake factory có thể quan sát được:

~~~java
package example.abstractfactory;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class ApplicationTest {

    static final class FakeButton implements Button {
        Runnable handler;

        @Override
        public void onClick(Runnable handler) {
            this.handler = handler;
        }

        @Override
        public void click() {
            if (handler == null) {
                throw new IllegalStateException("No handler registered");
            }
            handler.run();
        }

        @Override
        public String render() {
            return "Fake button";
        }
    }

    static final class FakeCheckbox implements Checkbox {
        boolean checked;

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
            return "Fake checkbox";
        }
    }

    static final class FakeFactory implements GUIFactory {
        final FakeButton button = new FakeButton();
        final FakeCheckbox checkbox = new FakeCheckbox();
        int buttonCreations;
        int checkboxCreations;

        @Override
        public Button createButton() {
            buttonCreations++;
            return button;
        }

        @Override
        public Checkbox createCheckbox() {
            checkboxCreations++;
            return checkbox;
        }
    }

    @Test
    void createsProductsOnceAndTogglesCheckboxOnClick() {
        FakeFactory factory = new FakeFactory();

        new Application(factory);

        assertEquals(1, factory.buttonCreations);
        assertEquals(1, factory.checkboxCreations);
        assertFalse(factory.checkbox.isChecked());

        factory.button.click();
        assertTrue(factory.checkbox.isChecked());

        factory.button.click();
        assertFalse(factory.checkbox.isChecked());
    }

    @Test
    void rejectsNullFactoryAndNullProducts() {
        assertThrows(NullPointerException.class,
                () -> new Application(null));

        GUIFactory brokenFactory = new GUIFactory() {
            @Override
            public Button createButton() {
                return null;
            }

            @Override
            public Checkbox createCheckbox() {
                return new FakeCheckbox();
            }
        };

        assertThrows(NullPointerException.class,
                () -> new Application(brokenFactory));
    }
}
~~~

Đây là nội dung minh họa file `src/test/java/example/abstractfactory/ApplicationTest.java`. Test sử dụng JUnit Jupiter (JUnit 5); dự án cần cấu hình phụ thuộc JUnit và test engine tương ứng. Test không khởi động Windows hay macOS UI mà chỉ kiểm tra **trách nhiệm của `Application`**:

1. Nó yêu cầu từng sản phẩm **một lần** trong constructor theo thiết kế ví dụ.
2. Nó đã đăng ký sự kiện cho button.
3. Khi button được click, trạng thái checkbox được đảo đúng.
4. Nó không chấp nhận factory hoặc sản phẩm `null`.

**Giới hạn của test trên:** số lần tạo sản phẩm “một lần” là **quyết định cụ thể của phiên bản `Application` đang học**, không phải luật chung của Abstract Factory. Nếu ứng dụng thật cần tạo sản phẩm cho từng cửa sổ, assertion về số lần gọi sẽ khác.

Ngoài `ApplicationTest`, cần một nhóm **test contract riêng cho concrete factory**: `WindowsFactory` phải tạo đúng họ Windows; `MacFactory` phải tạo đúng họ macOS. Unit test `Application` với fake factory **không thể thay thế** việc kiểm tra tính nhất quán của concrete factory thực.

## 9. Những lỗi thường gặp khi Application sử dụng factory

| Hiện tượng | Vấn đề | Hướng xử lý |
| --- | --- | --- |
| `Application` chứa `switch(platform)` và gọi constructor cụ thể | Lặp trách nhiệm chọn biến thể | Đưa lựa chọn ra composition root, truyền `GUIFactory` |
| `Application` gọi `new WindowsFactory()` ngay trong constructor | Không thể đổi biến thể qua injection | Nhận `GUIFactory` qua tham số |
| Button từ factory A, checkbox từ factory B | Có thể trộn hai họ | Lấy bộ sản phẩm từ **cùng factory đã chọn** |
| `Application` ép kiểu `(WindowsButton) factory.createButton()` | Phụ thuộc lại vào implementation | Chỉ dùng API của `Button`; xem lại contract nếu thiếu hành vi |
| Factory xử lý luôn sự kiện “click thì đảo checkbox” | Trộn khởi tạo với điều phối hành vi chung | Đặt wiring sự kiện tại `Application` hoặc controller |
| Factory trả `null` | Crash tại nơi sử dụng | Ghi rõ hợp đồng và test; kiểm tra sớm nếu cần |
| Một factory singleton cache checkbox có trạng thái cho nhiều cửa sổ | Dễ chia sẻ trạng thái ngoài ý muốn | Định nghĩa vòng đời sản phẩm và tránh dùng chung object mutable không phù hợp |
| Đổi theme nhưng giữ lại sản phẩm cũ | Giao diện không nhất quán với cấu hình mới | Xác định điểm tái tạo hoặc cập nhật sản phẩm |
| Test `Application` luôn tạo UI thật | Khó cô lập, chậm, phụ thuộc môi trường | Dùng fake factory; kiểm thử tích hợp UI ở tầng riêng |

### Vì sao không truyền sẵn Button và Checkbox?

Một constructor `Application(Button button, Checkbox checkbox)` vẫn có thể là thiết kế hợp lý, đặc biệt nếu ứng dụng chỉ cần một cặp sản phẩm đã được lắp ráp sẵn. Nhưng khi `Application` cần **tự tạo thêm các thành phần thuộc cùng họ** hoặc kiểm soát thời điểm tạo, nhận `GUIFactory` sẽ thể hiện trách nhiệm đó rõ hơn.

Ngược lại, nếu tất cả sản phẩm đã được tạo ở composition root và `Application` không cần tạo thêm đối tượng, việc tiêm trực tiếp sản phẩm có thể đơn giản hơn. Đừng bổ sung factory chỉ để tăng số lớp; chọn abstraction theo nhu cầu quản lý vòng đời và nhóm sản phẩm.

### Vì sao không dùng một GUIFactory cho tất cả trường hợp?

Abstract Factory không có nghĩa **mọi loại sản phẩm trong cả chương trình** phải nằm trong một interface. `GUIFactory` nên tập trung vào những sản phẩm liên quan cùng biến thể. Những đối tượng không liên quan, như cơ sở dữ liệu hoặc logger, có thể có dependency riêng. Nếu mọi factory phải implement hàng chục phương thức mà chỉ vài nền tảng hỗ trợ, hợp đồng có thể đang quá rộng.

## 10. Mở rộng Application khi thêm biến thể hoặc sản phẩm

**Thêm họ sản phẩm.** Giả sử thêm Linux với `LinuxButton` và `LinuxCheckbox`. Cần tạo `LinuxFactory implements GUIFactory` và cập nhật nơi chọn factory. Nếu các product interface không đổi và hai lớp mới tuân theo hợp đồng, **`Application` giữ nguyên**.

**Thêm loại sản phẩm.** Giả sử mọi nền tảng cần thêm `Slider`. Khi đó có thể bổ sung `Slider createSlider()` vào `GUIFactory`, hiện thực ở tất cả concrete factory và cập nhật `Application` nếu nó có nhiệm vụ điều phối slider. Đây là thay đổi **theo chiều loại sản phẩm** nên ảnh hưởng rộng hơn.

**Sản phẩm chỉ một vài họ hỗ trợ.** Nếu chỉ desktop cần `NativeMenuBar`, không nên mặc định thêm `createNativeMenuBar()` vào mọi `GUIFactory`, buộc Web phải trả `null`. Cân nhắc một interface năng lực riêng hoặc factory chuyên biệt; các client desktop yêu cầu dependency phù hợp.

**Mở thêm nhiều cửa sổ.** Cân nhắc giữ `GUIFactory` làm field và tạo cặp `Button`/`Checkbox` mới khi mở cửa sổ. Mỗi cặp cần được gắn sự kiện riêng; đừng để một checkbox của cửa sổ A bị điều khiển bởi button của cửa sổ B.

**Kết hợp dependency injection framework.** Framework DI có thể cấp `WindowsFactory` hoặc `MacFactory` dưới kiểu `GUIFactory` theo cấu hình. Điều này thay đổi **cách cấp dependency**, không thay đổi vai trò của `Application`. Cần xác định scope của factory và những sản phẩm được tạo, tránh chia sẻ sai đối tượng có trạng thái.

## 11. Bài tập thực hành

### Bài tập 1 — Hoàn thiện constructor Application

Điền các phần còn thiếu để `Application` không phụ thuộc lớp Windows/macOS:

~~~java
final class Application {
    private final Button button;
    private final Checkbox checkbox;

    Application(GUIFactory factory) {
        // TODO: lấy button và checkbox từ factory
        // TODO: khi nhấn button, đảo trạng thái checkbox
    }
}
~~~

Gợi ý: dùng `factory.createButton()`, `factory.createCheckbox()` và `button.onClick(...)`. Nếu khai báo trường `final`, cả hai trường phải được gán trong constructor.

### Bài tập 2 — Thêm một biến thể

Tạo `LinuxButton`, `LinuxCheckbox` và `LinuxFactory implements GUIFactory`. Bổ sung `LINUX` trong `Platform` và ánh xạ mới ở `GUIFactorySelector`. Dự đoán những dòng nào trong `Application` cần sửa: **không dòng nào**, nếu mọi hợp đồng và quy tắc tương tác đều giữ nguyên.

### Bài tập 3 — Tìm lỗi ghép họ

Factory Windows sau có lỗi gì?

~~~java
final class WindowsFactory implements GUIFactory {
    @Override
    public Button createButton() {
        return new WindowsButton();
    }

    @Override
    public Checkbox createCheckbox() {
        return new MacCheckbox();
    }
}
~~~

Hãy giải thích vì sao Java có thể cho biên dịch và thiết kế một test phát hiện việc trả sản phẩm không cùng họ. Có thể quan sát hành vi `render()` trong ví dụ hoặc dùng thuộc tính/cơ chế kiểm thử phù hợp hơn trong sản phẩm thật.

### Bài tập 4 — Thay đổi vòng đời

Yêu cầu mới: một `Application` có thể mở ba cửa sổ, mỗi cửa sổ có checkbox độc lập. Việc lưu một checkbox duy nhất trong constructor còn phù hợp không? Hãy đề xuất cách sử dụng `GUIFactory` cho từng cửa sổ và kiểm tra rằng click ở cửa sổ này không ảnh hưởng cửa sổ khác.

### Bài tập 5 — Test bằng fake

Mở rộng `ApplicationTest` để ghi nhận **số lần** handler được gọi sau ba lần click hoặc để xác minh `Application` bỏ qua đầu vào không hợp lệ theo hợp đồng bạn chọn. Tránh làm test phụ thuộc vào chuỗi trang trí của từng nền tảng nếu mục tiêu chỉ là kiểm tra logic điều phối.

## 12. Checklist trước khi hoàn thành Application

- [ ] Constructor của `Application` nhận `GUIFactory` qua tham số hoặc một cơ chế injection tương đương.
- [ ] `Application` không tạo trực tiếp `WindowsButton`, `MacButton` và các concrete product.
- [ ] `Button` và `Checkbox` được lấy từ cùng factory phù hợp với một biến thể.
- [ ] `Application` phối hợp sản phẩm bằng phương thức thuộc **product interface**.
- [ ] Điểm khởi động ứng dụng là nơi chọn concrete factory theo cấu hình.
- [ ] Đã xác định rõ factory/sản phẩm được tạo một lần hay cho từng cửa sổ, từng request.
- [ ] Có quy tắc xử lý factory hoặc sản phẩm `null` nếu hợp đồng có khả năng gặp.
- [ ] Đã tách unit test logic điều phối của `Application` khỏi test từng concrete factory.
- [ ] Khi thêm một họ mới, có thể giữ nguyên logic trong `Application` nếu hợp đồng không đổi.
- [ ] Khi thêm loại sản phẩm mới, đã đánh giá tác động lên interface factory và các concrete factory.

**Ghi nhớ:** `Application` là **khách hàng của Abstract Factory**. Nó nhận `GUIFactory`, lấy các sản phẩm qua `createButton()` và `createCheckbox()`, rồi phối hợp chúng qua `Button` và `Checkbox`. Quyết định dùng Windows hay macOS thuộc **composition root và concrete factory**, nhờ vậy cùng một logic ứng dụng có thể làm việc với nhiều họ sản phẩm tương thích.

# Vai trò ConcreteProduct trong việc cung cấp hành vi cho từng biến thể

> **Chương:** Cấu trúc và cộng tác  
> **Học phần:** `SOFTWARE_DESIGN_DESIGN_PATTERN_CREATIONAL_ABSTRACT_FACTORY` — Học về Abstract Factory trong Design Pattern.  
> **Mục tiêu:** Phân biệt trách nhiệm của *AbstractProduct*, *ConcreteProduct*, *AbstractFactory* và *ConcreteFactory*; giải thích cách một ConcreteProduct cung cấp hành vi của biến thể cụ thể thông qua hợp đồng chung; quan sát sự cộng tác giữa factory, client và các sản phẩm khi chạy.

## 1. Từ nhu cầu tạo đối tượng đến nhu cầu sử dụng hành vi

Giả sử một ứng dụng desktop hỗ trợ giao diện Windows và macOS. Màn hình đăng nhập cần hai loại thành phần:

- **Button:** hiển thị nút Đăng nhập và phản hồi khi được kích hoạt.
- **Checkbox:** hiển thị tùy chọn Ghi nhớ đăng nhập và duy trì trạng thái được chọn.

Mỗi nền tảng có hai sản phẩm tương ứng:

| Loại sản phẩm | Họ Windows | Họ macOS |
| --- | --- | --- |
| Button | `WindowsButton` | `MacButton` |
| Checkbox | `WindowsCheckbox` | `MacCheckbox` |

Abstract Factory giải quyết việc tạo **một họ các đối tượng liên quan**. Tuy nhiên, sau khi đối tượng được tạo ra, công việc thực tế như hiển thị, xử lý kích hoạt và cập nhật trạng thái phải do một thành phần khác thực hiện.

Thành phần ấy chính là **ConcreteProduct**: lớp hiện thực một *product interface* và cung cấp hành vi cụ thể cho một biến thể.

Một nút Windows không chỉ mang cái tên `WindowsButton`. Nó là đối tượng hiện thực hành vi nút theo thiết kế Windows. Tương tự, `MacCheckbox` chịu trách nhiệm cách một ô chọn của họ macOS thể hiện trạng thái và thực hiện các thao tác mà interface đã quy định.

## 2. Vị trí ConcreteProduct trong cấu trúc Abstract Factory

Abstract Factory có bốn nhóm vai trò chính:

| Vai trò | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| **AbstractProduct** | Công bố các thao tác chung cho **một loại sản phẩm** | `Button`, `Checkbox` |
| **ConcreteProduct** | Hiện thực hợp đồng ấy bằng hành vi và trạng thái của **một biến thể** | `WindowsButton`, `MacCheckbox` |
| **AbstractFactory** | Công bố cách tạo **nhiều loại sản phẩm** trong cùng họ | `GUIFactory` |
| **ConcreteFactory** | Khởi tạo các ConcreteProduct thuộc **đúng họ** của nó | `WindowsFactory`, `MacFactory` |

**Client** (ví dụ `LoginScreen`) chỉ sử dụng `GUIFactory` và các AbstractProduct. Nó không cần biết có bao nhiêu lớp Button hoặc Checkbox cụ thể.

~~~mermaid
classDiagram
    direction TB

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
        +activate() String
    }

    class Checkbox {
        <<interface>>
        +render() String
        +setSelected(boolean) void
        +isSelected() boolean
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

    WindowsFactory ..> WindowsButton : creates
    WindowsFactory ..> WindowsCheckbox : creates
    MacFactory ..> MacButton : creates
    MacFactory ..> MacCheckbox : creates
~~~

Các mũi tên `creates` cho thấy factory **khởi tạo** sản phẩm; các mũi tên hiện thực interface cho thấy sản phẩm **cung cấp hành vi**. Hai quan hệ này không nên bị nhầm lẫn.

Ví dụ, `WindowsFactory.createButton()` trả về một `WindowsButton`, nhưng khi client gọi `button.activate()`, hành vi của phương thức ấy nằm trong `WindowsButton`. Factory không cần trực tiếp xử lý lần kích hoạt nút.

## 3. AbstractProduct xác định hợp đồng; ConcreteProduct hiện thực hợp đồng

Xét hai interface chung:

~~~java
interface Button {
    String render();
    String activate();
}

interface Checkbox {
    String render();
    void setSelected(boolean selected);
    boolean isSelected();
}
~~~

Đây là **hợp đồng** mà client có thể dựa vào:

- Mọi Button đều có thể `render()` và `activate()`.
- Mọi Checkbox đều có thể `render()`, nhận trạng thái mới qua `setSelected(...)` và trả trạng thái hiện tại bằng `isSelected()`.
- Client không cần biết thao tác đó được thực hiện trong lớp Windows hay macOS.

Interface chưa định nghĩa chính xác cách một Button trông như thế nào hoặc một Checkbox thể hiện dấu chọn ra sao. Đó là khoảng biến thiên dành cho ConcreteProduct.

### Cùng kiểu trừu tượng, khác cách hiện thực

~~~java
final class WindowsButton implements Button {
    @Override
    public String render() {
        return "[Windows] Button: kiểu Windows";
    }

    @Override
    public String activate() {
        return "[Windows] Button đã được kích hoạt";
    }
}

final class MacButton implements Button {
    @Override
    public String render() {
        return "[macOS] Button: kiểu macOS";
    }

    @Override
    public String activate() {
        return "[macOS] Button đã được kích hoạt";
    }
}
~~~

Hai lớp có **cùng phương thức theo interface**, nhưng mỗi lớp cung cấp **cách thể hiện riêng**.

Với GUI thực tế, khác biệt có thể nằm ở màu, kích thước, trạng thái focus/hover/disabled, hiệu ứng nhấn, cách truy cập API giao diện nền tảng hoặc cách kết nối sự kiện. Ở các ví dụ học thuật trong bài, phương thức chỉ trả về chuỗi mô phỏng. Chúng **không tự vẽ giao diện Windows/macOS thật**.

Điểm cần ghi nhớ: factory có trách nhiệm trả về đối tượng nào; **ConcreteProduct có trách nhiệm làm gì khi các phương thức của đối tượng đó được gọi**.

## 4. ConcreteProduct còn quản lý trạng thái và quy tắc tương tác

Không phải mọi khác biệt chỉ là giao diện hiển thị. Một sản phẩm cũng có thể có trạng thái và quy tắc điều khiển riêng.

Hai Checkbox sau cùng triển khai `Checkbox`:

~~~java
final class WindowsCheckbox implements Checkbox {
    private boolean selected;

    @Override
    public void setSelected(boolean selected) {
        this.selected = selected;
    }

    @Override
    public boolean isSelected() {
        return selected;
    }

    @Override
    public String render() {
        return "[Windows] Checkbox " + (selected ? "[x]" : "[ ]");
    }
}

final class MacCheckbox implements Checkbox {
    private boolean selected;

    @Override
    public void setSelected(boolean selected) {
        this.selected = selected;
    }

    @Override
    public boolean isSelected() {
        return selected;
    }

    @Override
    public String render() {
        return "[macOS] Checkbox " + (selected ? "(on)" : "(off)");
    }
}
~~~

Khi client thực hiện:

~~~java
Checkbox rememberMe = /* một checkbox thuộc họ đã chọn */;
rememberMe.setSelected(true);
System.out.println(rememberMe.render());
~~~

thì kết quả render phụ thuộc vào **lớp ConcreteProduct thực tế**:

| Đối tượng thực tế | Kết quả minh họa khi được chọn |
| --- | --- |
| `WindowsCheckbox` | `[Windows] Checkbox [x]` |
| `MacCheckbox` | `[macOS] Checkbox (on)` |

Nhưng **ý nghĩa của trạng thái** phải nhất quán: gọi `setSelected(true)` khiến `isSelected()` trả về `true` trên cả hai họ. Sự thay đổi về hình thức hoặc cơ chế thao tác không được làm sai hợp đồng chung.

Đây là điểm liên quan đến nguyên tắc **thay thế Liskov (Liskov Substitution Principle)**: client phải có thể sử dụng một ConcreteProduct thông qua AbstractProduct mà các kỳ vọng chung đã công bố vẫn được giữ nguyên. Nếu một Checkbox macOS trả về `false` sau `setSelected(true)` mà không có quy tắc hợp đồng nào cho phép, nó không phải implementation đúng chỉ vì mang giao diện macOS.

### Phân biệt trạng thái UI với nghiệp vụ đăng nhập

Checkbox biết mình đã được chọn hay chưa; Button biết cách phản hồi thao tác kích hoạt. Nhưng việc **ghi nhớ phiên đăng nhập**, **xác thực mật khẩu** hay **gọi API đăng nhập** là trách nhiệm của phần nghiệp vụ hoặc bộ điều khiển màn hình, không nhất thiết thuộc ConcreteProduct.

Trong một UI thực, Button thường phát ra sự kiện để mã điều khiển gọi dịch vụ đăng nhập. Cách tổ chức đó cho phép thay giao diện Windows bằng macOS mà không phải viết lại quy trình xác thực.

## 5. Factory tạo sản phẩm; client gọi hành vi; ConcreteProduct thực thi

Hãy theo dõi một luồng từ lúc ứng dụng chọn Windows đến khi màn hình tương tác với hai sản phẩm:

~~~mermaid
sequenceDiagram
    participant App as Điểm khởi động
    participant Factory as WindowsFactory
    participant Screen as LoginScreen
    participant Button as WindowsButton
    participant Checkbox as WindowsCheckbox

    App->>Factory: tạo hoặc chọn WindowsFactory
    App->>Screen: truyền GUIFactory
    Screen->>Factory: createButton()
    Factory-->>Screen: Button (WindowsButton)
    Screen->>Factory: createCheckbox()
    Factory-->>Screen: Checkbox (WindowsCheckbox)
    Screen->>Button: render()
    Button-->>Screen: chuỗi hiển thị Windows
    Screen->>Checkbox: setSelected(true)
    Screen->>Checkbox: render()
    Checkbox-->>Screen: chuỗi trạng thái Windows
    Screen->>Button: activate()
    Button-->>Screen: kết quả kích hoạt Windows
~~~

Luồng có ba thời điểm với trách nhiệm khác nhau:

1. **Lựa chọn họ:** điểm khởi động quyết định dùng `WindowsFactory` hay `MacFactory`.
2. **Khởi tạo sản phẩm:** concrete factory trả về các ConcreteProduct thuộc cùng họ.
3. **Thực hiện hành vi:** client gọi qua interface; Java dispatch đến implementation của đối tượng cụ thể đang được tham chiếu.

Phép gọi:

~~~java
Button button = factory.createButton();
System.out.println(button.render());
~~~

không yêu cầu client kiểm tra kiểu bằng `instanceof`. Dù biến `button` có kiểu tĩnh là `Button`, việc gọi `render()` vẫn chạy implementation của `WindowsButton` hoặc `MacButton` đang được giữ trong biến. Đây là **đa hình (polymorphism)** tại thời điểm chạy.

## 6. Ví dụ Java tự chứa: hai họ, cùng hành vi chung

Dưới đây là ví dụ có thể biên dịch bằng JDK tiêu chuẩn. Mã được đặt trong một tệp để tiện học; các kiểu được khai báo lồng nhau nhằm minh họa rõ cấu trúc.

Lưu thành `ConcreteProductDemo.java`:

~~~java
public class ConcreteProductDemo {

    // AbstractProduct: hợp đồng dùng chung cho mỗi loại sản phẩm.
    interface Button {
        String render();
        String activate();
    }

    interface Checkbox {
        String render();
        void setSelected(boolean selected);
        boolean isSelected();
    }

    // ConcreteProduct thuộc họ Windows.
    static final class WindowsButton implements Button {
        @Override
        public String render() {
            return "[Windows] Button: kiểu Windows";
        }

        @Override
        public String activate() {
            return "[Windows] Button đã được kích hoạt";
        }
    }

    static final class WindowsCheckbox implements Checkbox {
        private boolean selected;

        @Override
        public String render() {
            return "[Windows] Checkbox "
                    + (selected ? "[x]" : "[ ]");
        }

        @Override
        public void setSelected(boolean selected) {
            this.selected = selected;
        }

        @Override
        public boolean isSelected() {
            return selected;
        }
    }

    // ConcreteProduct thuộc họ macOS.
    static final class MacButton implements Button {
        @Override
        public String render() {
            return "[macOS] Button: kiểu macOS";
        }

        @Override
        public String activate() {
            return "[macOS] Button đã được kích hoạt";
        }
    }

    static final class MacCheckbox implements Checkbox {
        private boolean selected;

        @Override
        public String render() {
            return "[macOS] Checkbox "
                    + (selected ? "(on)" : "(off)");
        }

        @Override
        public void setSelected(boolean selected) {
            this.selected = selected;
        }

        @Override
        public boolean isSelected() {
            return selected;
        }
    }

    // AbstractFactory: danh sách loại sản phẩm có thể tạo.
    interface GUIFactory {
        Button createButton();
        Checkbox createCheckbox();
    }

    // ConcreteFactory: chọn đúng ConcreteProduct trong mỗi họ.
    static final class WindowsFactory implements GUIFactory {
        @Override
        public Button createButton() {
            return new WindowsButton();
        }

        @Override
        public Checkbox createCheckbox() {
            return new WindowsCheckbox();
        }
    }

    static final class MacFactory implements GUIFactory {
        @Override
        public Button createButton() {
            return new MacButton();
        }

        @Override
        public Checkbox createCheckbox() {
            return new MacCheckbox();
        }
    }

    // Client: chỉ biết GUIFactory, Button, Checkbox.
    static final class LoginScreen {
        private final Button loginButton;
        private final Checkbox rememberMe;

        LoginScreen(GUIFactory factory) {
            this.loginButton = factory.createButton();
            this.rememberMe = factory.createCheckbox();
        }

        void simulateInteraction() {
            System.out.println(loginButton.render());
            System.out.println(rememberMe.render());

            rememberMe.setSelected(true);

            System.out.println(rememberMe.render());
            System.out.println(loginButton.activate());
            System.out.println("rememberMe=" + rememberMe.isSelected());
        }
    }

    public static void main(String[] args) {
        System.out.println("=== Windows ===");
        new LoginScreen(new WindowsFactory()).simulateInteraction();

        System.out.println("=== macOS ===");
        new LoginScreen(new MacFactory()).simulateInteraction();
    }
}
~~~

Chạy:

~~~bash
javac ConcreteProductDemo.java
java ConcreteProductDemo
~~~

Kết quả dự kiến:

~~~text
=== Windows ===
[Windows] Button: kiểu Windows
[Windows] Checkbox [ ]
[Windows] Checkbox [x]
[Windows] Button đã được kích hoạt
rememberMe=true
=== macOS ===
[macOS] Button: kiểu macOS
[macOS] Checkbox (off)
[macOS] Checkbox (on)
[macOS] Button đã được kích hoạt
rememberMe=true
~~~

Quan sát ba điểm:

- **Factory khác nhau** tạo ra các đối tượng thuộc hai họ khác nhau; không phải sửa `LoginScreen`.
- **ConcreteProduct khác nhau** cung cấp chuỗi hiển thị và kết quả kích hoạt khác nhau.
- **Hành vi dùng chung** vẫn được giữ: sau `setSelected(true)`, cả hai Checkbox đều có `isSelected() == true`.

Ví dụ sử dụng chuỗi để mô phỏng giao diện và phản hồi. Trong mã GUI thật, ConcreteProduct có thể bao bọc widget nguyên bản (*native widget*), gọi thư viện vẽ hoặc tích hợp cơ chế sự kiện của nền tảng.

## 7. Ranh giới trách nhiệm: đâu là hành vi của ConcreteProduct?

Không phải mọi hành vi phụ thuộc vào màn hình đều nên đặt trong ConcreteProduct. Hãy xác định ranh giới theo **hợp đồng sản phẩm**.

| Hành vi hoặc quyết định | Thành phần thường chịu trách nhiệm | Vì sao |
| --- | --- | --- |
| Chọn Windows hay macOS lúc khởi động | Composition root / cấu hình ứng dụng | Quyết định biến thể dùng chung |
| Tạo Button và Checkbox tương ứng | ConcreteFactory | Giữ các sản phẩm cùng họ |
| Hiển thị kiểu Button theo nền tảng | ConcreteProduct Button | Hành vi riêng của từng phiên bản Button |
| Duy trì trạng thái được chọn của Checkbox | ConcreteProduct Checkbox | Trạng thái theo hợp đồng Checkbox |
| Tích hợp sự kiện nhấn với widget nền tảng | ConcreteProduct / adapter của UI | Khác nhau theo công nghệ giao diện |
| Kiểm tra tên đăng nhập và mật khẩu | Dịch vụ nghiệp vụ / bộ điều khiển | Không phụ thuộc vào biến thể giao diện |
| Quyết định điều hướng sau đăng nhập | Bộ điều khiển / ứng dụng | Luồng nghiệp vụ của màn hình |

**Điểm quan trọng:** ConcreteProduct **không phải lớp chứa mọi logic phát sinh trên màn hình**. Nó chứa hành vi và trạng thái phù hợp với **vai trò sản phẩm** mà interface công bố, cùng phần hiện thực riêng cho nền tảng đó.

### Biến thể có thể khác cả hình thức lẫn cơ chế

Ví dụ, `WindowsButton` có thể được triển khai bằng một API widget Windows, còn `MacButton` dùng widget macOS. Bên dưới, các lớp có thể đăng ký callback hoặc xử lý focus khác nhau. Tuy nhiên, khi client chỉ cần “kích hoạt nút” hoặc “gắn handler”, hai lớp phải cung cấp khả năng đó qua **cùng một hợp đồng trừu tượng**.

Sự khác biệt về cách hiện thực **không có nghĩa** các interface được phép thay đổi ý nghĩa tùy nền tảng. Nếu Button của một họ yêu cầu client gọi thêm một phương thức riêng mới hoạt động đúng, client có thể buộc phải downcast và mất lợi ích đa hình.

## 8. Tính tương thích theo họ: factory hỗ trợ, sản phẩm thực hiện

Một thuộc tính quan trọng của Abstract Factory là nhóm các sản phẩm **được thiết kế để sử dụng cùng nhau**:

~~~text
Họ Windows: WindowsFactory
                 |---> WindowsButton
                 +---> WindowsCheckbox

Họ macOS:   MacFactory
                 |---> MacButton
                 +---> MacCheckbox
~~~

Factory không nhất thiết có chức năng kiểm tra mọi thuộc tính của các sản phẩm. **Chính các phương thức tạo của từng ConcreteFactory** cần trả về đúng ConcreteProduct. Nếu viết sai:

~~~java
// Ví dụ sai: lớp WindowsFactory lại cung cấp Checkbox của macOS.
@Override
public Checkbox createCheckbox() {
    return new MacCheckbox();
}
~~~

đoạn mã vẫn có thể biên dịch vì `MacCheckbox` triển khai `Checkbox`. Nhưng màn hình dùng WindowsFactory sẽ có một Button theo Windows và một Checkbox theo macOS: **đúng kiểu Java, sai quy tắc cùng họ**.

Do đó, cần phân biệt hai kiểu kiểm tra:

1. **Kiểm tra hợp đồng sản phẩm:** `WindowsCheckbox` và `MacCheckbox` đều có hành vi đúng như `Checkbox` quy định.
2. **Kiểm tra tính nhất quán của họ:** `WindowsFactory` chỉ tạo sản phẩm Windows; `MacFactory` chỉ tạo sản phẩm macOS.

Hai yêu cầu bổ sung cho nhau. Một ConcreteProduct đúng hành vi vẫn có thể bị tạo từ factory sai họ; ngược lại, một factory trả đúng loại lớp chưa chứng minh rằng phương thức trong lớp ấy hoạt động chính xác.

## 9. Kiểm thử ConcreteProduct và ConcreteFactory

Nên kiểm thử hai cấp độ riêng biệt.

### 9.1. Kiểm thử hợp đồng chung của từng ConcreteProduct

Ví dụ, mọi Checkbox đều phải nhận và trả đúng trạng thái đã đặt:

~~~java
static void verifyCheckboxContract(Checkbox checkbox) {
    checkbox.setSelected(true);
    if (!checkbox.isSelected()) {
        throw new AssertionError("Checkbox did not select");
    }

    checkbox.setSelected(false);
    if (checkbox.isSelected()) {
        throw new AssertionError("Checkbox did not deselect");
    }
}
~~~

Trong `ConcreteProductDemo`, có thể gọi phương thức này với:

~~~java
verifyCheckboxContract(new WindowsCheckbox());
verifyCheckboxContract(new MacCheckbox());
~~~

Bởi vì cả hai tham số được tiếp nhận dưới kiểu `Checkbox`, cùng một kiểm tra dùng được cho mọi biến thể. Khi có thêm Linux, kiểm tra tương tự có thể áp dụng cho `LinuxCheckbox` mà không cần viết lại quy tắc trạng thái chung.

Đối với Button, có thể kiểm tra rằng `render()` hoặc `activate()` trả về kết quả theo hợp đồng, đồng thời kiểm tra riêng các khác biệt có chủ đích của từng nền tảng.

### 9.2. Kiểm thử factory không trộn họ

Ở cấp độ kiểm thử factory, có thể kiểm tra kiểu cụ thể:

~~~java
GUIFactory windows = new WindowsFactory();
GUIFactory mac = new MacFactory();

if (!(windows.createButton() instanceof WindowsButton)
        || !(windows.createCheckbox() instanceof WindowsCheckbox)) {
    throw new AssertionError("WindowsFactory mixes product families");
}

if (!(mac.createButton() instanceof MacButton)
        || !(mac.createCheckbox() instanceof MacCheckbox)) {
    throw new AssertionError("MacFactory mixes product families");
}
~~~

Việc dùng `instanceof` trong **kiểm thử các factory cụ thể** có mục tiêu xác minh wiring, vì ở đây ta chủ động biết các lớp cụ thể. **Mã nghiệp vụ của client** không cần và không nên lặp lại những kiểm tra đó để quyết định mỗi lần render hoặc kích hoạt.

Trong ứng dụng thật, phần kiểm thử sản phẩm còn có thể bao phủ focus, keyboard navigation, accessibility, phản hồi khi disabled, xử lý lỗi và những quy tắc native UI. Những kiểm tra đó thuộc hợp đồng và yêu cầu hành vi cụ thể của widget, khác với việc xác minh đường đi tạo sản phẩm.

## 10. Những sai lầm thường gặp khi thiết kế ConcreteProduct

### Sai lầm 1 — Cho factory xử lý mọi thao tác của sản phẩm

~~~java
// Ví dụ thiết kế ràng buộc client vào factory sau khi tạo:
factory.drawButton(button);
factory.handleCheckboxState(checkbox);
~~~

Nếu mọi thao tác đều quay về factory, factory có nguy cơ trở thành lớp khổng lồ chứa logic của các sản phẩm. Thông thường, factory chỉ nên **tạo** đối tượng, còn phương thức của đối tượng nên xử lý phần hành vi tương ứng:

~~~java
Button button = factory.createButton();
button.render();
button.activate();
~~~

Đây là phân chia trách nhiệm phổ biến, không phải lệnh cấm tuyệt đối đối với các factory có thêm chính sách khởi tạo hoặc cấu hình. Cần xem mục tiêu của factory trong thiết kế cụ thể.

### Sai lầm 2 — ConcreteProduct không tuân thủ ngữ nghĩa interface

Một `MacCheckbox.setSelected(true)` không cập nhật trạng thái, trong khi `WindowsCheckbox` cập nhật đúng, sẽ khiến client phải viết ngoại lệ riêng. Thay vì phân nhánh theo lớp cụ thể, hãy giữ nguyên **hợp đồng chung** và đặt chi tiết cách thực hiện trong từng lớp.

### Sai lầm 3 — Client kiểm tra kiểu cụ thể để gọi phương thức riêng

~~~java
// Mã client bắt đầu biết cả lớp cụ thể:
if (button instanceof WindowsButton) {
    // xử lý riêng cho Windows
} else if (button instanceof MacButton) {
    // xử lý riêng cho macOS
}
~~~

Nếu client thường xuyên cần thao tác này, hãy xem xét liệu interface `Button` có thiếu một khả năng chung hoặc trách nhiệm nền tảng đang nằm sai chỗ. Có thể mở rộng hợp đồng hợp lý hoặc tách thêm một interface chuyên biệt, nhưng không nên thêm các phương thức chỉ dành cho một biến thể vào hợp đồng chung một cách tùy tiện.

### Sai lầm 4 — Lẫn hành vi sản phẩm với nghiệp vụ

Không nên gắn việc xác thực tài khoản trực tiếp vào `WindowsButton` và `MacButton` chỉ vì màn hình đăng nhập có nút. Hai lớp nên xử lý phần giao diện hoặc sự kiện chung; bộ điều khiển hoặc dịch vụ đăng nhập xử lý nghiệp vụ.

### Sai lầm 5 — Cho các sản phẩm của cùng loại chia sẻ trạng thái ngoài ý muốn

Nếu mỗi lần `createCheckbox()` tạo một Checkbox độc lập, hai ô chọn khác nhau không nên vô tình dùng chung một biến `static selected`. Khi thực sự muốn chia sẻ trạng thái, thiết kế cần xác định rõ nguồn trạng thái và vòng đời. Việc một số implementation dùng chung tài nguyên native không tự động có nghĩa trạng thái lựa chọn của mọi đối tượng là chung.

## 11. Khi mở rộng biến thể hoặc loại sản phẩm

### Thêm họ Linux

Có thể tạo:

- `LinuxButton implements Button` với hành vi theo yêu cầu Linux.
- `LinuxCheckbox implements Checkbox` với trạng thái và cách thể hiện Linux.
- `LinuxFactory implements GUIFactory` trả về hai ConcreteProduct này.

**Client có thể giữ nguyên**, miễn là dùng factory thông qua `GUIFactory` và Linux hiện thực đầy đủ các hợp đồng. Đây là một trong những lợi ích của Abstract Factory khi mở rộng theo **họ sản phẩm**.

### Thêm một loại sản phẩm như TextField

Khi màn hình cần ô nhập văn bản, thiết kế thường phải:

1. Tạo AbstractProduct mới `TextField`.
2. Tạo `WindowsTextField` và `MacTextField`, mỗi lớp hiện thực hành vi chung theo họ của mình.
3. Thêm `createTextField()` vào `GUIFactory`.
4. Cập nhật **mọi ConcreteFactory** để tạo đúng TextField của họ.

Đây là thay đổi theo **loại sản phẩm**, nên hợp đồng factory phải được mở rộng và các factory hiện có đều chịu ảnh hưởng. Sự khác biệt giữa thêm họ và thêm loại cần được cân nhắc khi quyết định mức độ nhóm các sản phẩm vào cùng một abstract factory.

## 12. Bài tập: tự xác định đúng ConcreteProduct

**Tình huống A — Hành vi khác nhưng hợp đồng giống nhau.** Hai Button khác hiệu ứng nhấn và thông báo accessibility, nhưng đều phát ra cùng sự kiện kích hoạt. Hãy xác định những phần thuộc ConcreteProduct và phần nào thuộc bộ điều khiển màn hình.

**Tình huống B — Hợp đồng bị phá vỡ.** `LinuxCheckbox.setSelected(true)` chỉ tô màu giao diện mà `isSelected()` vẫn trả về `false`. Hãy chỉ ra vì sao lớp này không đáp ứng hợp đồng `Checkbox`.

**Tình huống C — Factory trả nhầm họ.** `MacFactory.createButton()` trả `MacButton`, còn `createCheckbox()` trả `WindowsCheckbox`. Mã có biên dịch được không? Tính đúng đắn về kiểu và tính đúng đắn về họ khác nhau ở đâu?

**Tình huống D — Mở rộng sản phẩm.** Thêm `TextField`. Hãy liệt kê những ConcreteProduct nào phải được thêm cho Windows và macOS, đồng thời xác định phương thức nào của `GUIFactory` và các ConcreteFactory cần thay đổi.

### Câu hỏi ghi nhớ

1. `AbstractProduct` định nghĩa điều gì, và `ConcreteProduct` chịu trách nhiệm điều gì?
2. Tại sao việc factory trả về một `Button` không có nghĩa factory cũng phải thực hiện `render()`?
3. Java chọn implementation của `button.render()` dựa vào điều gì khi `button` có kiểu khai báo là `Button`?
4. Vì sao hai ConcreteProduct có thể khác về giao diện nhưng phải giữ cùng ngữ nghĩa của hợp đồng?
5. Trong trường hợp nào `instanceof` có thể hợp lý ở kiểm thử nhưng là dấu hiệu không tốt ở mã client?
6. Khi ConcreteProduct chứa quá nhiều nghiệp vụ, những phần nào nên chuyển ra ngoài?

**Ghi nhớ:** **ConcreteFactory quyết định tạo sản phẩm cụ thể nào; ConcreteProduct cung cấp hành vi và trạng thái của sản phẩm ấy; AbstractProduct cho phép client sử dụng các hành vi chung mà không phụ thuộc vào lớp của từng biến thể.** Ba vai trò cộng tác để ứng dụng có thể thay trọn họ giao diện trong khi vẫn giữ mã client ổn định và ngữ nghĩa sử dụng nhất quán.


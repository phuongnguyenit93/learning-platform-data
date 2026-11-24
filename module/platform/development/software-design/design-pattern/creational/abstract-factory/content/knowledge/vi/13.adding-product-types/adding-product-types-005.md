# Cân nhắc tách factory theo năng lực khi một số họ không hỗ trợ sản phẩm mới

Trong **Abstract Factory**, một interface chung khai báo các phương thức tạo **những loại sản phẩm liên quan**; mỗi concrete factory tạo một **họ sản phẩm tương thích**. Thiết kế này rất thuận tiện khi bổ sung *một biến thể mới* với đủ các loại sản phẩm đã có. Nhưng khi cần bổ sung *một loại sản phẩm mới*, tình hình khác hẳn: nếu thêm phương thức vào Abstract Factory, các concrete factory hiện có đều phải đối mặt với hợp đồng mới.

Vấn đề đặc biệt rõ khi sản phẩm mới chỉ có ý nghĩa với **một số họ**. Ví dụ, ứng dụng chạy trên Windows, macOS và trình duyệt đều cần nút bấm và ô chọn; nhưng chỉ bản desktop mới sử dụng **thanh menu gốc của hệ điều hành** (*native menu bar*). Nếu buộc Web factory tạo thanh menu gốc, ta sẽ phải phát minh hành vi “không hỗ trợ”, làm yếu hợp đồng và tăng gánh nặng bảo trì.

Bài thuộc chương **Thêm loại sản phẩm** của module `SOFTWARE_DESIGN_DESIGN_PATTERN_CREATIONAL_ABSTRACT_FACTORY`, trong lộ trình **Học về abstract factory trong design pattern**. Mục tiêu là đưa ra một cách suy xét có hệ thống: **khi nào nên giữ chung factory, khi nào nên tách interface theo năng lực và làm sao vẫn giữ tính nhất quán của họ sản phẩm**.

Sau bài này, bạn có thể:

- Phân biệt **thêm họ**, **thêm loại sản phẩm** và **bổ sung một năng lực chỉ có ở một số họ**.
- Nhận ra vì sao trả `null` hoặc ném `UnsupportedOperationException` trong factory chung thường là dấu hiệu của hợp đồng sai ranh giới.
- So sánh hai cách tách: **factory năng lực độc lập** và **interface factory chuyên biệt kế thừa interface chung**.
- Viết Java để mã khách hàng chỉ yêu cầu những năng lực nó thực sự dùng.
- Xác định nguy cơ trộn sản phẩm từ hai biến thể khi tách factory và cách ngăn ngừa.
- Lập kế hoạch thay đổi interface, composition root và unit test khi nâng cấp hệ thống đang hoạt động.

## 1. Làm rõ ba chiều thay đổi

Hãy xét thiết kế ban đầu:

~~~java
interface GUIFactory {
    Button createButton();
    Checkbox createCheckbox();
}
~~~

Ứng dụng có ba concrete factory: `WindowsGUIFactory`, `MacGUIFactory` và `WebGUIFactory`.

| Thay đổi | Ví dụ | Tác động thường gặp |
| --- | --- | --- |
| **Thêm họ sản phẩm** | Thêm Linux với `LinuxButton` và `LinuxCheckbox` | Thêm implementation và concrete factory; chữ ký `GUIFactory` có thể giữ nguyên |
| **Thêm loại sản phẩm chung** | Mọi nền tảng đều cần `TextField` | Thêm `createTextField()` và hiện thực ở mọi concrete factory |
| **Thêm năng lực cho một tập con** | Windows/macOS cần `NativeMenuBar`, Web không có sản phẩm tương đương | Cần xem lại ranh giới factory; không nhất thiết mở rộng `GUIFactory` |

Đừng đánh đồng **họ sản phẩm** với **loại sản phẩm**. Trong ví dụ, Windows/macOS/Web là *họ*; `Button`, `Checkbox` và `NativeMenuBar` là *loại*. Hệ thống phát triển không đồng đều khi các họ không còn cùng hỗ trợ một tập loại sản phẩm.

### Ma trận năng lực là điểm bắt đầu

| Năng lực cần tạo sản phẩm | Windows | macOS | Web |
| --- | :---: | :---: | :---: |
| `Button` | Có | Có | Có |
| `Checkbox` | Có | Có | Có |
| `NativeMenuBar` | Có | Có | Không áp dụng |

**“Không áp dụng”** khác **“chưa hiện thực”**:

- *Chưa hiện thực*: nền tảng cần cung cấp sản phẩm theo hợp đồng nhưng nhóm chưa viết code; phải xem đó là việc còn thiếu.
- *Không áp dụng*: nền tảng không có khái niệm sản phẩm tương đương và client của nền tảng ấy không cần nó; không nên ép implementation mô phỏng chức năng chỉ để đủ chữ ký.

Trước khi sửa interface, nhóm phát triển phải thống nhất một ô “không áp dụng” có thật sự là thiếu năng lực, hay có thể định nghĩa lại sản phẩm ở mức trừu tượng hơn mà **mọi họ đều hỗ trợ có ý nghĩa**.

## 2. Điều gì xảy ra nếu cứ thêm phương thức vào `GUIFactory`?

Thử mở rộng hợp đồng chung:

~~~java
interface GUIFactory {
    Button createButton();
    Checkbox createCheckbox();
    NativeMenuBar createNativeMenuBar();
}
~~~

Windows và macOS có thể tạo sản phẩm thực, nhưng `WebGUIFactory` phải chọn một trong các cách sau:

~~~java
// Cách 1: trả null
@Override
public NativeMenuBar createNativeMenuBar() {
    return null;
}

// Cách 2: ném ngoại lệ khi được gọi
@Override
public NativeMenuBar createNativeMenuBar() {
    throw new UnsupportedOperationException("No native menu bar on Web");
}

// Cách 3: trả sản phẩm giả không thực hiện gì
@Override
public NativeMenuBar createNativeMenuBar() {
    return new NoOpNativeMenuBar();
}
~~~

Các đoạn trên là **ba phương án minh họa riêng biệt**, không phải ba phương thức được đặt cạnh nhau trong cùng một lớp. `NoOpNativeMenuBar` là lớp giả định.

| Cách xử lý | Nguy cơ |
| --- | --- |
| Trả `null` | Caller tin có sản phẩm sẽ phải kiểm tra `null` ở mọi nơi; dễ gặp `NullPointerException` |
| Ném `UnsupportedOperationException` | Interface quảng bá phương thức mà một concrete factory không hỗ trợ; lỗi chuyển từ compile time sang runtime |
| Trả đối tượng no-op | Có thể báo thành công dù tính năng không hoạt động, che giấu lỗi trong trải nghiệm người dùng |
| Cố tạo sản phẩm Web tương tự | Có nguy cơ đánh tráo ý nghĩa: menu HTML trong trang chưa chắc tương đương *native* menu bar của OS |

**Không phải mọi no-op đều sai.** Nếu hợp đồng sản phẩm **chủ đích** định nghĩa thao tác tùy chọn và không hành động là kết quả hợp lệ, một Null Object có thể hữu ích. Nhưng với nhu cầu “khởi tạo thanh menu gốc của hệ điều hành”, đối tượng giả thường không đáp ứng ý nghĩa mà client kỳ vọng.

Thêm phương thức trừu tượng vào interface còn kéo theo các thay đổi ngoài mã chạy: factory hiện có, adapter, lớp giả dùng trong test, tài liệu API và các plugin biên dịch độc lập có thể phải nâng cấp. Ở Java, lớp triển khai cũ chưa có phương thức mới có thể tạo vấn đề tương thích khi phương thức được gọi trong runtime; cần đánh giá theo cách đóng gói/phát hành thực tế.

**Câu hỏi cốt lõi**: “Mọi implementation của `GUIFactory` có cam kết tạo được `NativeMenuBar` đúng nghĩa không?” Nếu câu trả lời là *không*, hãy cân nhắc tách hợp đồng theo năng lực.

## 3. Phương án A — Tách một factory năng lực độc lập

Giữ nguyên phần sản phẩm chung:

~~~java
interface GUIFactory {
    Button createButton();
    Checkbox createCheckbox();
}

interface NativeMenuBarFactory {
    NativeMenuBar createNativeMenuBar();
}
~~~

Những họ có khả năng tạo menu gốc có thể triển khai **cả hai interface**:

~~~java
final class WindowsGUIFactory implements GUIFactory, NativeMenuBarFactory {
    @Override
    public Button createButton() {
        return new WindowsButton();
    }

    @Override
    public Checkbox createCheckbox() {
        return new WindowsCheckbox();
    }

    @Override
    public NativeMenuBar createNativeMenuBar() {
        return new WindowsNativeMenuBar();
    }
}
~~~

Trong khi đó, Web chỉ cần hợp đồng phù hợp với mình:

~~~java
final class WebGUIFactory implements GUIFactory {
    @Override
    public Button createButton() {
        return new WebButton();
    }

    @Override
    public Checkbox createCheckbox() {
        return new WebCheckbox();
    }
}
~~~

Các kiểu sản phẩm `WindowsButton`, `WebCheckbox`, `NativeMenuBar`… sẽ được định nghĩa đầy đủ ở ví dụ tự chứa phía dưới. Đoạn này trước hết minh họa **cách tổ chức interface**.

Mã màn hình chung phụ thuộc `GUIFactory`. Thành phần chuyên trách menu gốc phụ thuộc `NativeMenuBarFactory`:

~~~java
final class NativeMenuController {
    private final NativeMenuBarFactory menuFactory;

    NativeMenuController(NativeMenuBarFactory menuFactory) {
        this.menuFactory = menuFactory;
    }

    void openMenu() {
        NativeMenuBar menu = menuFactory.createNativeMenuBar();
        menu.show();
    }
}
~~~

**Lợi ích:** các họ không hỗ trợ thanh menu gốc không phải implement phương thức giả. Code client chung chỉ có các phương thức mà mọi họ đều đáp ứng; code chuyên biệt công bố năng lực nó cần ngay tại constructor.

**Đánh đổi quan trọng:** nếu composition root truyền `new WindowsGUIFactory()` cho màn hình và `new MacGUIFactory()` cho `NativeMenuController`, màn hình Windows có thể bị ghép với menu macOS. Hai interface tách biệt **không tự bảo đảm** các dependency được lấy từ cùng họ. Đội ngũ phải giữ quy tắc ghép cặp ở nơi khởi tạo, trong cấu hình DI hoặc một đối tượng “bundle” rõ ràng.

## 4. Phương án B — Tạo interface cho một tập họ có cùng năng lực

Nếu toàn bộ nhóm **desktop** đều cần cả nút, ô chọn và thanh menu gốc, ta có thể biểu diễn hợp đồng rộng hơn bằng **interface kế thừa**:

~~~java
interface GUIFactory {
    Button createButton();
    Checkbox createCheckbox();
}

interface DesktopGUIFactory extends GUIFactory {
    NativeMenuBar createNativeMenuBar();
}
~~~

Khi ấy:

~~~java
final class WindowsGUIFactory implements DesktopGUIFactory {
    @Override
    public Button createButton() {
        return new WindowsButton();
    }

    @Override
    public Checkbox createCheckbox() {
        return new WindowsCheckbox();
    }

    @Override
    public NativeMenuBar createNativeMenuBar() {
        return new WindowsNativeMenuBar();
    }
}
~~~

`MacGUIFactory` cũng implement `DesktopGUIFactory`, trong khi `WebGUIFactory` **chỉ implement `GUIFactory`**.

Nhờ kiểu `DesktopGUIFactory`, màn hình desktop có thể tạo cả ba loại sản phẩm qua **chính một factory**:

~~~java
final class DesktopScreen {
    private final DesktopGUIFactory factory;

    DesktopScreen(DesktopGUIFactory factory) {
        this.factory = factory;
    }

    void show() {
        factory.createButton().render();
        factory.createCheckbox().render();
        factory.createNativeMenuBar().show();
    }
}
~~~

Với thiết kế này, `new DesktopScreen(new WebGUIFactory())` **không biên dịch**: `WebGUIFactory` không implement `DesktopGUIFactory`. Đây là lợi ích của việc thể hiện năng lực bắt buộc bằng **kiểu dữ liệu**, thay vì để client gọi rồi chờ `UnsupportedOperationException`.

Mặt khác, kiểu này gắn **tập năng lực desktop** với cùng một abstraction. Nó phù hợp khi đó là một nhóm có ý nghĩa và ổn định, không phù hợp nếu trong thực tế có những nền tảng desktop không có menu gốc hoặc ứng dụng chỉ cần menu mà không cần các thành phần khác.

### Khi nào chọn A, khi nào chọn B?

| Tiêu chí | Factory năng lực độc lập | Interface chuyên biệt kế thừa |
| --- | --- | --- |
| Mức độ độc lập của năng lực mới | Cao, có thể dùng riêng | Gắn với hợp đồng của nhóm đặc thù |
| Client chỉ cần thanh menu gốc | Nhận `NativeMenuBarFactory` | Có thể phải nhận `DesktopGUIFactory` rộng hơn nhu cầu |
| Client cần đồng thời nút, ô chọn, menu cùng họ | Composition root phải ghép nhất quán | Một `DesktopGUIFactory` cấp cả bộ |
| Một họ không thuộc desktop nhưng vẫn có menu gốc | Dễ implement năng lực | Phân loại `DesktopGUIFactory` có thể không đúng |
| Chi phí quản lý | Thêm interface và dây nối dependency | Thêm phân cấp interface và xác định tập họ thuộc nhóm |

Hai cách không loại trừ nhau: có thể tạo `NativeMenuBarFactory` riêng và sau đó khai báo `DesktopGUIFactory extends GUIFactory, NativeMenuBarFactory`. Như vậy **client chỉ cần menu** nhận interface nhỏ, còn **client cần toàn bộ bộ sản phẩm desktop** nhận một hợp đồng gộp mạnh hơn.

## 5. Phương án kết hợp: vừa tách năng lực, vừa giữ tính nhất quán của họ

Một thiết kế khá linh hoạt:

~~~java
interface GUIFactory {
    Button createButton();
    Checkbox createCheckbox();
}

interface NativeMenuBarFactory {
    NativeMenuBar createNativeMenuBar();
}

interface DesktopGUIFactory extends GUIFactory, NativeMenuBarFactory {
    // Kế thừa đủ ba phương thức; không cần khai báo lại.
}
~~~

Đây là **một hợp đồng kết hợp**, không phải phiên bản thứ ba tạo thêm loại sản phẩm. Mỗi interface có vai trò:

- `GUIFactory`: phần cơ bản dùng ở mọi nền tảng.
- `NativeMenuBarFactory`: năng lực tùy nền tảng, có thể dùng riêng.
- `DesktopGUIFactory`: lời hứa một factory tạo được **cả họ sản phẩm desktop** gồm ba loại.

~~~mermaid
classDiagram
    class GUIFactory {
        <<interface>>
        +createButton() Button
        +createCheckbox() Checkbox
    }
    class NativeMenuBarFactory {
        <<interface>>
        +createNativeMenuBar() NativeMenuBar
    }
    class DesktopGUIFactory {
        <<interface>>
    }
    class WindowsGUIFactory
    class MacGUIFactory
    class WebGUIFactory
    GUIFactory <|-- DesktopGUIFactory
    NativeMenuBarFactory <|-- DesktopGUIFactory
    DesktopGUIFactory <|.. WindowsGUIFactory
    DesktopGUIFactory <|.. MacGUIFactory
    GUIFactory <|.. WebGUIFactory
~~~

Khi cần cả ba sản phẩm thuộc một biến thể, client chỉ nhận **một** `DesktopGUIFactory`. Như vậy giảm nguy cơ trộn Windows button với Mac native menu do lắp ráp hai factory độc lập sai cách. Tuy nhiên, hợp đồng kiểu dữ liệu vẫn **không thể ngăn một implementation viết sai** (ví dụ `WindowsGUIFactory.createNativeMenuBar()` lại trả đối tượng Mac); phải dùng unit test để kiểm tra quy tắc tương thích.

## 6. Ví dụ Java hoàn chỉnh, chạy bằng Java 8+

Để tự quan sát, có thể đặt toàn bộ đoạn dưới vào `Demo.java` và chạy bằng JDK 8 trở lên. Ví dụ mô phỏng sản phẩm GUI bằng chuỗi; không cần thư viện UI ngoài. Chỉ `Demo` được khai báo `public` nên các lớp khác có thể cùng ở một file. Các đoạn code ở mục 2–5 là **phương án minh họa**, không ghép chung với file này vì có các interface trùng tên.

~~~java
import java.util.Objects;

enum Platform {
    WINDOWS, MAC, WEB
}

interface Button {
    Platform platform();
    String render();
}

interface Checkbox {
    Platform platform();
    String render();
}

interface NativeMenuBar {
    Platform platform();
    String show();
}

interface GUIFactory {
    Button createButton();
    Checkbox createCheckbox();
}

interface NativeMenuBarFactory {
    NativeMenuBar createNativeMenuBar();
}

interface DesktopGUIFactory extends GUIFactory, NativeMenuBarFactory {
}

final class WindowsButton implements Button {
    @Override
    public Platform platform() {
        return Platform.WINDOWS;
    }

    @Override
    public String render() {
        return "Windows Button";
    }
}

final class WindowsCheckbox implements Checkbox {
    @Override
    public Platform platform() {
        return Platform.WINDOWS;
    }

    @Override
    public String render() {
        return "Windows Checkbox";
    }
}

final class WindowsNativeMenuBar implements NativeMenuBar {
    @Override
    public Platform platform() {
        return Platform.WINDOWS;
    }

    @Override
    public String show() {
        return "Windows native menu bar";
    }
}

final class MacButton implements Button {
    @Override
    public Platform platform() {
        return Platform.MAC;
    }

    @Override
    public String render() {
        return "macOS Button";
    }
}

final class MacCheckbox implements Checkbox {
    @Override
    public Platform platform() {
        return Platform.MAC;
    }

    @Override
    public String render() {
        return "macOS Checkbox";
    }
}

final class MacNativeMenuBar implements NativeMenuBar {
    @Override
    public Platform platform() {
        return Platform.MAC;
    }

    @Override
    public String show() {
        return "macOS native menu bar";
    }
}

final class WebButton implements Button {
    @Override
    public Platform platform() {
        return Platform.WEB;
    }

    @Override
    public String render() {
        return "Web Button";
    }
}

final class WebCheckbox implements Checkbox {
    @Override
    public Platform platform() {
        return Platform.WEB;
    }

    @Override
    public String render() {
        return "Web Checkbox";
    }
}

final class WindowsGUIFactory implements DesktopGUIFactory {
    @Override
    public Button createButton() {
        return new WindowsButton();
    }

    @Override
    public Checkbox createCheckbox() {
        return new WindowsCheckbox();
    }

    @Override
    public NativeMenuBar createNativeMenuBar() {
        return new WindowsNativeMenuBar();
    }
}

final class MacGUIFactory implements DesktopGUIFactory {
    @Override
    public Button createButton() {
        return new MacButton();
    }

    @Override
    public Checkbox createCheckbox() {
        return new MacCheckbox();
    }

    @Override
    public NativeMenuBar createNativeMenuBar() {
        return new MacNativeMenuBar();
    }
}

final class WebGUIFactory implements GUIFactory {
    @Override
    public Button createButton() {
        return new WebButton();
    }

    @Override
    public Checkbox createCheckbox() {
        return new WebCheckbox();
    }
}

// Client chung dùng đúng hai loại sản phẩm phổ biến.
final class CommonScreen {
    private final GUIFactory factory;

    CommonScreen(GUIFactory factory) {
        this.factory = Objects.requireNonNull(factory, "factory");
    }

    void show() {
        Button button = Objects.requireNonNull(
                factory.createButton(), "button");
        Checkbox checkbox = Objects.requireNonNull(
                factory.createCheckbox(), "checkbox");
        System.out.println(button.render());
        System.out.println(checkbox.render());
    }
}

// Client desktop yêu cầu đủ ba sản phẩm cùng một họ.
final class DesktopScreen {
    private final DesktopGUIFactory factory;

    DesktopScreen(DesktopGUIFactory factory) {
        this.factory = Objects.requireNonNull(factory, "factory");
    }

    void show() {
        new CommonScreen(factory).show();
        NativeMenuBar menu = Objects.requireNonNull(
                factory.createNativeMenuBar(), "nativeMenuBar");
        System.out.println(menu.show());
    }
}

public final class Demo {
    public static void main(String[] args) {
        new DesktopScreen(new WindowsGUIFactory()).show();
        new DesktopScreen(new MacGUIFactory()).show();
        new CommonScreen(new WebGUIFactory()).show();
    }
}
~~~

**Đầu ra dự kiến:**

~~~text
Windows Button
Windows Checkbox
Windows native menu bar
macOS Button
macOS Checkbox
macOS native menu bar
Web Button
Web Checkbox
~~~

Chú ý:

1. `CommonScreen` chỉ biết `GUIFactory` và không cần thao tác menu gốc.
2. `DesktopScreen` nhận `DesktopGUIFactory`, nên từ kiểu tham số đã thể hiện yêu cầu “ba loại sản phẩm cùng được hỗ trợ”.
3. `WebGUIFactory` không có phương thức `createNativeMenuBar()` và không bị buộc viết implementation giả.
4. `Platform platform()` trên sản phẩm là API minh họa để unit test quan sát nguồn gốc họ sản phẩm. Hệ thống thật có thể xác minh bằng hành vi hoặc hợp đồng khác.
5. Các phương thức `render()` và `show()` trả chuỗi mô phỏng; chúng không vẽ giao diện thật.

### Đặt điểm chọn factory ở đâu?

Ví dụ `Demo.main()` trực tiếp tạo ba trường hợp để minh họa. Trong ứng dụng thực tế, composition root có thể đọc cấu hình hệ điều hành, profile hoặc ngữ cảnh yêu cầu rồi chọn factory. Chỉ nhánh desktop mới tạo `DesktopScreen`; nhánh Web tạo `CommonScreen`. Việc phát hiện năng lực và quyết định cấp dependency nằm **ở ranh giới khởi tạo**, không nên rải `if (platform == ...)` trong từng nút bấm hoặc màn hình.

Nếu biến thể đổi trong runtime, cần xác định vòng đời và nơi thay factory: chọn một lần khi khởi động không phản ánh được thay đổi của từng request.

## 7. Nhìn lại nguyên tắc thay thế và phân tách interface

Hai nguyên tắc thiết kế giải thích vì sao giải pháp này hữu ích:

**Interface Segregation Principle (ISP).** Client chỉ nên phụ thuộc vào những phương thức nó thật sự cần. Một màn hình Web không sử dụng native menu bar không có lý do phải phụ thuộc một `GUIFactory` bắt buộc có phương thức đó.

**Liskov Substitution Principle (LSP).** Nếu một factory được trình bày như implementation của hợp đồng cho phép client tạo native menu bar, client có lý do kỳ vọng lời gọi ấy hoạt động theo đúng quy định. Một `WebGUIFactory` luôn ném ngoại lệ cho phương thức vốn được quảng bá như khả năng bình thường có thể vi phạm kỳ vọng thay thế. Nếu ngay từ đầu **hợp đồng công khai mô tả phương thức tùy chọn** và quy định cách xử lý rõ ràng thì đánh giá khác; không nên gán nhãn vi phạm LSP mà bỏ qua nội dung hợp đồng.

Các interface tách biệt giúp **thể hiện ranh giới năng lực tại compile time**, nhưng không thay thế mọi phép kiểm tra runtime: ví dụ một factory vẫn có thể tạo sản phẩm sai biến thể hoặc trả `null`, và Java type system không tự phát hiện.

## 8. Tránh hai cực đoan khi mở rộng factory

### Cực đoan A: gom mọi năng lực vào một interface

~~~java
interface EverythingGUIFactory {
    Button createButton();
    Checkbox createCheckbox();
    NativeMenuBar createNativeMenuBar();
    // Ngoài ra còn nhiều phương thức chỉ vài nền tảng hỗ trợ...
}
~~~

Kết quả thường là các factory chứa nhiều method giả, nhiều nhánh kiểm tra tính năng, test double phình to. Mỗi lần thêm một loại sản phẩm riêng của một họ lại yêu cầu cập nhật tất cả implementation.

### Cực đoan B: tách từng sản phẩm thành factory riêng bất chấp quan hệ họ

~~~java
interface ButtonFactory {
    Button createButton();
}

interface CheckboxFactory {
    Checkbox createCheckbox();
}

interface NativeMenuBarFactory {
    NativeMenuBar createNativeMenuBar();
}
~~~

Nếu mọi màn hình đều cần button và checkbox **phải cùng nền tảng**, việc chia tách quá nhỏ khiến nơi lắp ráp phải bảo toàn quan hệ đó thủ công. Một `GUIFactory` chung cho bộ sản phẩm thực sự luôn đi cùng nhau vẫn có ích.

Vì vậy, mục tiêu không phải *càng ít* hay *càng nhiều* factory càng tốt, mà là **mỗi hợp đồng phải diễn tả một tập năng lực có ý nghĩa đối với những client sử dụng nó**.

## 9. Quy trình quyết định khi có yêu cầu sản phẩm mới

Khi có đề xuất thêm phương thức `createNewProduct()` vào một Abstract Factory, hãy tiến hành:

1. **Định nghĩa sản phẩm mới bằng yêu cầu hành vi.** Sản phẩm phải làm được gì? Có ý nghĩa giống nhau trên mọi họ không, hay là tính năng đặc thù của một nền tảng?
2. **Lập ma trận sản phẩm × họ.** Với từng họ, ghi “có thể tạo”, “dự kiến tạo”, “không áp dụng”, “chưa xác định”. Không đoán từ tên lớp hoặc nền tảng.
3. **Xác định client cần gì.** Client nào dùng loại sản phẩm mới? Client có đồng thời cần sản phẩm chung và yêu cầu chúng thuộc cùng một họ không?
4. **Kiểm tra sự thật về tính tùy chọn.** Nếu có thể thiếu sản phẩm, client có được phép hoạt động thiếu nó không? “Không có” là trường hợp hợp lệ hay lỗi cấu hình?
5. **So sánh phương án mở rộng interface chung với tách capability.** Tính số concrete factory, adapter, test double, cấu hình DI và nơi khởi tạo phải sửa.
6. **Đánh giá cách ghép cùng họ.** Nếu chia hai factory độc lập, xác định cách ràng buộc Windows với Windows, Mac với Mac. Nếu cần hợp đồng gộp, cân nhắc interface chuyên biệt kế thừa.
7. **Ghi rõ cách chuyển đổi.** Hệ thống đang có plugin/client bên ngoài cần phân kỳ phiên bản hay không? Có thể giữ interface cũ và chuyển client dần không?
8. **Viết test theo hợp đồng mới.** Các factory chung vẫn phải đáp ứng sản phẩm chung; các factory hỗ trợ capability mới cần test riêng và test tính nhất quán của bộ sản phẩm.

Một sơ đồ lựa chọn:

~~~mermaid
flowchart TD
    A["Cần thêm loại sản phẩm"] --> B{"Mọi họ có cung cấp sản phẩm này theo cùng hợp đồng?"}
    B -->|Có| C["Xem xét thêm phương thức vào Abstract Factory chung"]
    B -->|Không| D{"Đây là năng lực có ý nghĩa với một tập họ cụ thể?"}
    D -->|Có| E["Tách capability thành interface riêng"]
    E --> F{"Client cần cả năng lực mới và bộ sản phẩm chung cùng họ?"}
    F -->|Có| G["Cân nhắc interface gộp kế thừa cả hai"]
    F -->|Không| H["Tiêm interface capability nhỏ"]
    D -->|Chưa rõ| I["Làm rõ yêu cầu và tính tương đương của sản phẩm"]
    C --> J["Đánh giá số factory/test/API phải cập nhật"]
    G --> J
    H --> J
~~~

Không có nhánh nào tự động dẫn đến một cấu trúc duy nhất. Một ứng dụng nhỏ với hai biến thể thường có chi phí cấu hình khác hệ thống plugin hàng chục nhà cung cấp được phát hành độc lập.

## 10. So sánh chi phí thay đổi bằng một tình huống giả định

Giả sử có **năm** họ GUI, nhưng chỉ **hai** họ hỗ trợ native menu bar. Có ba hướng cần cân nhắc:

| Hướng | Công việc chính | Chi phí/rủi ro đặc trưng |
| --- | --- | --- |
| Thêm `createNativeMenuBar()` vào `GUIFactory` | Cập nhật interface và cả 5 concrete factory | 3 factory không áp dụng vẫn phải xử lý phương thức; client phải hiểu ngoại lệ |
| Tách `NativeMenuBarFactory` riêng | Thêm interface, cập nhật 2 họ hỗ trợ và nơi lắp ráp client | Cần bảo toàn cặp factory cùng họ nếu client nhận hai dependency riêng |
| Tách capability và thêm `DesktopGUIFactory` gộp | Thêm hai interface nhỏ, cập nhật 2 họ hỗ trợ, cấp đúng type cho client desktop | Thêm mức abstraction và cần quy ước rõ thế nào là “desktop” |

**Số factory liên quan là chỉ số ban đầu, không phải tổng chi phí.** Có thể ước lượng:

\[
C_{\text{change}} \approx C_{\text{API}}
  + \sum C_{\text{affected factory}}
  + C_{\text{tests}}
  + C_{\text{integration}}
  + C_{\text{release}}
\]

Chi phí `C_{\text{API}}` gồm thiết kế/chuyển đổi hợp đồng; tổng `C_{\text{affected factory}}` bao gồm thời gian viết, sửa mock và kiểm tra implementation; `C_{\text{integration}}` là wiring, DI, ghép cùng họ; `C_{\text{release}}` là phối hợp phiên bản/module nếu có.

**Số liệu giả định minh họa**, không phải kết quả đo đạc:

| Khoản việc | Mở rộng chung | Tách capability + interface gộp |
| --- | ---: | ---: |
| Thiết kế hợp đồng | 1 giờ | 3 giờ |
| Sửa factory hỗ trợ (2 họ) | 4 giờ | 4 giờ |
| Sửa factory không hỗ trợ (3 họ) | 3 giờ | 0 giờ |
| Test và test double | 3 giờ | 2 giờ |
| Điều chỉnh điểm khởi tạo | 1 giờ | 2 giờ |
| **Tổng giả định** | **12 giờ** | **11 giờ** |

Chênh lệch một giờ chưa đủ để kết luận trong mọi dự án. Nếu các họ tiếp tục phát triển không đồng đều, chi phí thay đổi interface chung có thể lặp lại ở các đợt sau. Ngược lại, nếu hầu hết họ sắp hỗ trợ sản phẩm mới, việc tách có thể chỉ khiến architecture phức tạp hơn. Hãy ghi lại giả định và cập nhật khi xuất hiện dữ liệu từ những thay đổi thực tế.

## 11. Những cách thay thế cần cân nhắc

### 11.1. Mọi họ đều có một năng lực tương đương ở mức abstraction cao hơn

Đôi khi tên `NativeMenuBar` quá gắn với desktop. Nếu yêu cầu thực sự là “cung cấp điểm điều hướng chính”, cả Web và desktop có thể cung cấp `NavigationComponent` với hình thức khác nhau. Khi đó, **mọi họ** có thể triển khai một loại sản phẩm chung có ý nghĩa.

Tuy nhiên, không nên đổi tên chỉ để buộc các hành vi rất khác nhau vào cùng interface. Cần chứng minh client có thể dùng `NavigationComponent` mà không phải viết lại nhiều `instanceof` hoặc phân nhánh theo nền tảng.

### 11.2. Chỉ một client cần capability, không cần cả bộ sản phẩm

Nếu một dịch vụ chuyên tạo native menu chỉ cần `NativeMenuBar`, tiêm `NativeMenuBarFactory` độc lập có thể đủ. Không cần buộc dịch vụ ấy biết `Button` và `Checkbox` thông qua `DesktopGUIFactory`.

### 11.3. Capability phát hiện được ở runtime

Với plugin được cài động, đôi khi không biết khả năng tại compile time. Có thể có registry/cơ chế tìm `NativeMenuBarFactory` và trả về `Optional<NativeMenuBarFactory>` ở ranh giới điều phối. Cách này có thêm trách nhiệm xử lý “không tìm thấy” nhưng không bắt mỗi `GUIFactory` giả hỗ trợ menu. Nếu một client không thể hoạt động thiếu menu, hãy từ chối cấu hình sớm thay vì im lặng bỏ qua.

### 11.4. Một số nền tảng có fallback đúng nghĩa

Ví dụ ứng dụng yêu cầu “hiển thị menu điều hướng”, không nhất thiết là native. Nếu fallback Web menu có hành vi đáp ứng cùng một hợp đồng sản phẩm, việc tạo sản phẩm Web hợp lệ có thể tốt hơn tách capability. Yếu tố quyết định là **hợp đồng chức năng**, không phải tên hệ điều hành.

### 11.5. Không nhất thiết áp dụng Abstract Factory cho một năng lực duy nhất

Nếu chỉ có **một loại sản phẩm độc lập**, một provider, DI binding hoặc factory đơn giản có thể rõ hơn. Abstract Factory có giá trị nhất khi thiết kế cần **tạo một nhóm loại sản phẩm liên quan** và chuyển giữa các họ một cách nhất quán.

## 12. Kế hoạch chuyển đổi từ factory chung đã phình to

Giả sử codebase đã thêm `createNativeMenuBar()` vào `GUIFactory` và Web đang ném `UnsupportedOperationException`. Một hướng refactor có kiểm soát:

1. **Xác nhận cách dùng thực tế:** tìm mọi caller của `createNativeMenuBar()`; ghi nơi nào phụ thuộc vào interface chung, nơi nào chỉ hoạt động trên desktop.
2. **Định nghĩa contract capability:** thêm `NativeMenuBarFactory` và, nếu hữu ích, `DesktopGUIFactory`. Ghi rõ kết quả khác `null` và khả năng hỗ trợ.
3. **Cho các factory desktop implement contract mới:** Windows/macOS trả sản phẩm phù hợp; giữ code gọi chung hiện tại khi đang chuyển đổi.
4. **Chuyển client theo năng lực:** màn hình chung chỉ nhận `GUIFactory`, màn hình desktop nhận `DesktopGUIFactory`, client menu độc lập nhận `NativeMenuBarFactory`.
5. **Cập nhật composition root và DI:** cấp cùng một concrete desktop factory cho client cần một bộ sản phẩm nhất quán; không tạo cặp Windows/Mac lệch nhau.
6. **Viết test hợp đồng:** mọi `GUIFactory` vẫn tạo `Button` và `Checkbox`; mọi `DesktopGUIFactory` tạo thêm `NativeMenuBar` đúng họ.
7. **Loại bỏ method sai ranh giới khỏi interface chung** sau khi không còn caller lệ thuộc và đã đánh giá yêu cầu tương thích phiên bản/module. Với API công khai, có thể cần adapter hoặc kỳ phát hành breaking change.

Điểm then chốt là **đổi cả hợp đồng và cách các client lấy dependency**. Chỉ tạo thêm `NativeMenuBarFactory` nhưng vẫn để mọi màn hình gọi `GUIFactory.createNativeMenuBar()` thì chưa giải quyết được vấn đề gốc.

## 13. Kiểm thử sau khi tách factory theo năng lực

Nên có hai lớp kiểm tra: **hợp đồng sản phẩm chung** và **khả năng desktop**.

Các kiểm tra JUnit Jupiter dưới đây dựa trên các class trong file `Demo.java` ở mục 6. Trong dự án thật, đặt test cùng package với các kiểu package-private hoặc tách kiểu cần dùng ra file `public` thích hợp.

~~~java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class FactoryCapabilityTest {

    private void assertCoreFamily(GUIFactory factory, Platform platform) {
        Button button = factory.createButton();
        Checkbox checkbox = factory.createCheckbox();

        assertNotNull(button);
        assertNotNull(checkbox);
        assertEquals(platform, button.platform());
        assertEquals(platform, checkbox.platform());
    }

    private void assertDesktopFamily(
            DesktopGUIFactory factory, Platform platform) {
        assertCoreFamily(factory, platform);

        NativeMenuBar menu = factory.createNativeMenuBar();
        assertNotNull(menu);
        assertEquals(platform, menu.platform());
        assertFalse(menu.show().isEmpty());
    }

    @Test
    void windowsProvidesCompleteDesktopFamily() {
        assertDesktopFamily(new WindowsGUIFactory(), Platform.WINDOWS);
    }

    @Test
    void macProvidesCompleteDesktopFamily() {
        assertDesktopFamily(new MacGUIFactory(), Platform.MAC);
    }

    @Test
    void webProvidesOnlyRequiredCoreProducts() {
        assertCoreFamily(new WebGUIFactory(), Platform.WEB);
    }
}
~~~

Test này cố tình **không gọi `createNativeMenuBar()` trên `WebGUIFactory`**: đó không phải phần của hợp đồng mà Web cam kết. Sự phân tách này giúp test tránh phát minh phương thức giả hoặc kỳ vọng ngoại lệ để kiểm tra điều vốn không áp dụng.

Hãy kiểm tra thêm **đặc tính của sản phẩm**, không chỉ biến thể gắn nhãn. Ví dụ một menu Windows thật cần hoạt động cùng cơ chế giao diện Windows, và các sản phẩm không được chia sẻ trạng thái không an toàn giữa các màn hình. `platform()` ở ví dụ chỉ là phương tiện quan sát, chưa đủ chứng minh mọi tương tác thực tế đúng.

### Kiểm thử trường hợp ghép nhầm họ

Với phương án tách hai factory độc lập, unit test của từng factory **không phát hiện** composition root chọn Windows cho nút nhưng Mac cho menu. Cần có kiểm thử tích hợp điểm lắp ráp, hoặc sử dụng `DesktopGUIFactory` như phương án gộp nếu client luôn cần bộ sản phẩm cùng họ.

Ngược lại, `DesktopGUIFactory` không ngăn lập trình viên **viết sai một concrete factory**. Vẫn phải kiểm tra từng concrete factory tạo đúng các thành viên trong họ.

## 14. Bài tập phân tích

### Tình huống A — Tính năng đặc thù theo nền tảng

Một `DocumentFactory` chung tạo `Editor` và `Viewer` cho Windows, Web và Android. Chỉ Android cần thêm `ShareSheet` gốc của hệ điều hành.

**Yêu cầu:** lập ma trận sản phẩm × nền tảng và giải thích vì sao `createShareSheet()` có thể thuộc `AndroidShareFactory` riêng. Client nào nên nhận factory năng lực? Nếu một màn hình Android cần cả `Editor` và `ShareSheet` cùng cấu hình, có nên tạo interface gộp không?

### Tình huống B — Khả năng thiếu do chưa làm xong

Một nhóm muốn tách `createTextField()` ra vì Web chưa kịp triển khai, mặc dù yêu cầu sản phẩm quy định **mọi nền tảng đều phải có text field**.

**Yêu cầu:** phân biệt **thiếu implementation** và **không có khả năng**. Trong trường hợp này, giữ `createTextField()` trong `GUIFactory` có thể tạo động lực hoàn tất hợp đồng đúng cho mọi họ.

### Tình huống C — Chọn interface cho client

Cho ba client: `SimpleScreen` chỉ cần `Button` và `Checkbox`; `TrayMenuService` chỉ cần native menu; `DesktopShell` phải tạo cả ba loại sản phẩm cùng nền tảng.

**Yêu cầu:** chọn tham số constructor cho mỗi client trong số `GUIFactory`, `NativeMenuBarFactory` và `DesktopGUIFactory`. Giải thích trường hợp nào có nguy cơ trộn hai họ nếu nhận hai factory độc lập.

### Tình huống D — Phát hiện lỗi định nghĩa hợp đồng

Một concrete factory Web implement `createNativeMenuBar()` bằng cách trả `null`; client gọi `factory.createNativeMenuBar().show()`.

**Yêu cầu:** nêu lỗi runtime có thể gặp, chi phí khi caller phải kiểm tra `null`, và cách thay đổi interface để client Web không bao giờ được hứa có native menu bar.

### Tình huống E — Nguy cơ tách quá mức

Tất cả năm nền tảng của ứng dụng đều cần `Button`, `Checkbox` và `TextField`, và các sản phẩm phải theo cùng theme. Một nhóm đề xuất ba factory độc lập vì “interface càng nhỏ càng tốt”.

**Yêu cầu:** giải thích vì sao một `GUIFactory` chung vẫn có thể phù hợp hơn nếu nó thể hiện một họ sản phẩm thống nhất; chỉ ra chi phí bảo toàn tính tương thích khi chia tách.

## 15. Checklist trước khi chọn phương án

- [ ] Đã xác định rõ sản phẩm mới là **loại sản phẩm chung** hay **năng lực chỉ một tập họ hỗ trợ**.
- [ ] Đã phân biệt **không áp dụng** với **chưa hiện thực** trong ma trận họ sản phẩm.
- [ ] Không buộc factory thiếu năng lực phải trả `null`, no-op hoặc ném ngoại lệ chỉ để đáp ứng một interface quá rộng.
- [ ] Đã mô tả đúng hợp đồng chức năng; không đổi tên sản phẩm để che giấu sự khác biệt thực chất.
- [ ] Client chung phụ thuộc phần `GUIFactory` thực sự có ở mọi họ.
- [ ] Client chuyên biệt nhận factory nhỏ theo năng lực mà nó sử dụng.
- [ ] Nếu client cần cả sản phẩm chung và riêng **cùng họ**, đã có cách lắp ráp nhất quán hoặc interface gộp `DesktopGUIFactory`.
- [ ] Đã ước lượng số concrete factory, adapter, mock/test double, client và cấu hình triển khai chịu tác động.
- [ ] Đã xác định cách xử lý tương thích API khi thay đổi interface đang được dùng ở nhiều module.
- [ ] Có kiểm thử cho **hợp đồng chung**, **hợp đồng capability** và **tính nhất quán sản phẩm của từng concrete factory**.
- [ ] Đã cân nhắc chi phí abstraction mới so với nhu cầu phát triển hiện tại và tương lai.

**Ghi nhớ:** Khi thêm một loại sản phẩm vào Abstract Factory, **hãy hỏi trước liệu tất cả họ có thật sự cần và có thể tạo ra sản phẩm đó theo cùng một hợp đồng hay không**. Nếu chỉ một tập họ có năng lực ấy, việc tách factory theo năng lực giúp interface chính xác hơn và tránh kéo các implementation không liên quan vào thay đổi. Khi nhiều sản phẩm phải luôn thuộc cùng biến thể, có thể dùng một interface factory chuyên biệt **gộp các năng lực cần thiết** để bảo toàn ý nghĩa của Abstract Factory.

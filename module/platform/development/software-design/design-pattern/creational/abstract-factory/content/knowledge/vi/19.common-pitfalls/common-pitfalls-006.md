# Trả về `null` hoặc ném `UnsupportedOperationException` để che lấp hợp đồng không phù hợp

Trong mẫu thiết kế **Abstract Factory**, interface factory hứa cung cấp một nhóm **loại sản phẩm liên quan**; mỗi concrete factory tạo các sản phẩm thuộc một họ tương thích. Một lỗi thường gặp xuất hiện khi người thiết kế mở rộng factory chung bằng sản phẩm mà **một số họ hoàn toàn không hỗ trợ**, rồi viết các implementation không phù hợp bằng cách **trả về `null`** hoặc **ném `UnsupportedOperationException`**.

Lúc này mã vẫn có thể biên dịch, nhưng lời hứa từ interface trở nên mơ hồ: phương thức có vẻ luôn tạo được sản phẩm, trong khi một số factory chỉ tạo được kết quả “không có gì” hoặc thất bại khi được gọi. Lỗi chuyển từ nơi định nghĩa kiến trúc sang nơi sử dụng, khiến client phải thêm điều kiện kiểm tra và dễ gặp sự cố runtime.

Bài thuộc phần **Lỗi thường gặp** của module `SOFTWARE_DESIGN_DESIGN_PATTERN_CREATIONAL_ABSTRACT_FACTORY`, trong lộ trình **Học về abstract factory trong design pattern**. Trọng tâm là nhận ra **hợp đồng factory không phù hợp với năng lực thực tế của các họ sản phẩm**, hiểu vì sao các cách “chữa cháy” bằng `null` hoặc ngoại lệ thường làm vấn đề trầm trọng hơn, và biết cách sửa ranh giới abstraction trong Java.

Sau bài học, bạn cần có khả năng:

- Đọc một interface Abstract Factory và xác định phương thức nào đang **hứa quá khả năng** của một số concrete factory.
- Phân biệt **thiếu implementation**, **không có năng lực**, **không có dữ liệu ở thời điểm gọi** và **lỗi runtime hợp lệ**.
- Giải thích tác động của `null`, `UnsupportedOperationException` và đối tượng *no-op* đến mã khách hàng.
- Cân nhắc hai hướng sửa: **tách factory theo năng lực** hoặc **định nghĩa lại loại sản phẩm chung**.
- Viết ví dụ Java mà client chỉ yêu cầu những khả năng được bảo đảm qua type.
- Kiểm thử hợp đồng của từng factory và phát hiện sản phẩm được tạo sai họ.

## 1. Hợp đồng Abstract Factory thật sự hứa điều gì?

Xét một ứng dụng giao diện đa nền tảng có ba họ sản phẩm: **Windows**, **macOS** và **Web**. Cả ba đều có nút bấm và ô chọn:

~~~java
interface GUIFactory {
    Button createButton();
    Checkbox createCheckbox();
}
~~~

`Button` và `Checkbox` là hai **loại sản phẩm**; `WindowsButton`/`WindowsCheckbox`, `MacButton`/`MacCheckbox` và `WebButton`/`WebCheckbox` là các **họ sản phẩm**. Khách hàng nhận `GUIFactory` có thể sử dụng cả hai phương thức mà không cần biết họ cụ thể.

Về mặt kiểu dữ liệu, Java bảo đảm phương thức có kiểu trả về tương thích `Button` hoặc `Checkbox`. Java **không tự bảo đảm** kết quả khác `null`, thuộc đúng họ hay có hành vi hợp lệ. Những điều này cần được nêu rõ trong hợp đồng API và kiểm thử.

Một hợp đồng thiết kế tốt thường diễn đạt các kỳ vọng sau:

1. **Tính đầy đủ:** mỗi concrete factory triển khai đúng những loại sản phẩm mà interface công bố.
2. **Tính nhất quán:** những sản phẩm do cùng factory cung cấp thuộc một họ tương thích.
3. **Tính thay thế:** client lập trình theo interface có thể dùng mọi concrete factory đúng với những điều kiện mà hợp đồng đã công bố.
4. **Quy ước kết quả:** có trả `null` không, có ngoại lệ nào, sản phẩm sống trong bao lâu và khi nào được tạo.

Vấn đề phát sinh khi yêu cầu thứ nhất bị phá vỡ trên thực tế, nhưng interface vẫn giả vờ như mọi họ đều hỗ trợ đủ tất cả sản phẩm.

## 2. Tình huống gây lỗi: thêm sản phẩm không phải họ nào cũng có

Giả sử ứng dụng desktop muốn thêm **biểu tượng trên khay hệ thống** (*native system tray icon*). Windows và macOS có khái niệm này, nhưng một ứng dụng chạy trong trang Web thông thường không có một biểu tượng khay hệ thống gốc tương đương.

Ma trận sản phẩm:

| Loại sản phẩm | Windows | macOS | Web |
| --- | :---: | :---: | :---: |
| `Button` | Có | Có | Có |
| `Checkbox` | Có | Có | Có |
| `NativeTrayIcon` | Có | Có | Không áp dụng |

Một thay đổi không cẩn thận:

~~~java
interface GUIFactory {
    Button createButton();
    Checkbox createCheckbox();
    NativeTrayIcon createTrayIcon(); // Mọi factory bị buộc có phương thức
}
~~~

Ngay lúc này `WebGUIFactory` không còn một cách triển khai **có ý nghĩa** cho `createTrayIcon()`. Nếu trả `null` hoặc ném ngoại lệ, ta chưa giải quyết nguyên nhân gốc: **`GUIFactory` đang mô tả một năng lực không thuộc mọi họ**.

### Đây là “không áp dụng” hay “chưa được làm”?

Hai trường hợp dẫn tới hướng xử lý rất khác:

- **Chưa hiện thực:** sản phẩm mới là yêu cầu chung của tất cả họ, nhưng một nhóm chưa hoàn thành. Không nên dùng `null` để hợp thức hóa mã chưa xong; cần hoàn tất implementation hoặc quản lý tiến độ/phát hành.
- **Không áp dụng:** một họ thực sự không có và không cần hành vi tương ứng. Cần điều chỉnh ranh giới interface hoặc cách diễn đạt abstraction.

Ví dụ `TextField` là một loại điều khiển mà cả Windows, macOS và Web đều phải có theo yêu cầu sản phẩm; không thể tự viện lý do “Web chưa viết xong” để tách nó thành khả năng tùy chọn. Ngược lại, **khay hệ thống gốc** không phải sản phẩm tương đương với một vùng thông báo nằm trong trang Web.

## 3. Anti-pattern thứ nhất: trả về `null`

Một implementation sai ranh giới có thể được viết như sau:

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

    @Override
    public NativeTrayIcon createTrayIcon() {
        return null; // Web không có native system tray
    }
}
~~~

Giả sử mã khách hàng tin vào interface chung:

~~~java
void initializeTray(GUIFactory factory) {
    NativeTrayIcon tray = factory.createTrayIcon();
    tray.show(); // NullPointerException nếu factory là WebGUIFactory
}
~~~

Nếu bắt mọi client thêm kiểm tra:

~~~java
NativeTrayIcon tray = factory.createTrayIcon();
if (tray != null) {
    tray.show();
}
~~~

ta đã biến một lời hứa “factory tạo biểu tượng” thành một giao thức ngầm: “có thể trả không có gì; client tự đoán cách xử lý”. Những hệ quả điển hình:

1. **Mất tính rõ ràng tại compile time:** loại `GUIFactory` không thể hiện factory nào thực sự có khả năng tạo tray.
2. **Lỗi bị đẩy xuống client:** một client thiếu kiểm tra sẽ gặp `NullPointerException`.
3. **Hành vi có thể bị bỏ qua âm thầm:** client kiểm tra `null` rồi bỏ qua việc khởi tạo tray, dù đó có thể là yêu cầu bắt buộc của giao diện desktop.
4. **Điều kiện rò rỉ khắp codebase:** nhiều client phải học logic “Web không có tray”.
5. **Khó viết test hợp đồng chung:** test `assertNotNull(factory.createTrayIcon())` không thể áp dụng cho mọi concrete factory.

Lưu ý quan trọng: **trả `null` không phải lúc nào cũng sai trong Java**. Nếu hợp đồng rõ ràng quy định một kết quả có thể vắng mặt, API có thể dùng `Optional<NativeTrayIcon>`, một kiểu kết quả có trạng thái, hoặc một quy ước `null` đã được tài liệu hóa. Tuy nhiên, nếu **khả năng hỗ trợ khác nhau theo từng họ ổn định**, `Optional` chỉ biểu diễn sự vắng mặt ở runtime; nó **không tự sửa** một interface factory đang hứa sai năng lực.

## 4. Anti-pattern thứ hai: luôn ném `UnsupportedOperationException`

Một cách chữa cháy khác:

~~~java
@Override
public NativeTrayIcon createTrayIcon() {
    throw new UnsupportedOperationException(
            "Native tray is not available in Web");
}
~~~

Khác với `null`, mã không chạy tiếp với đối tượng không tồn tại; việc gọi phương thức sẽ thất bại ngay. Điều này có thể dễ chẩn đoán hơn một `NullPointerException` phát sinh xa nguồn tạo đối tượng, nhưng **không làm hợp đồng trở nên đúng** nếu client vẫn có quyền kỳ vọng mọi `GUIFactory` tạo được tray.

Khi một client cần tray để hoàn thành công việc, việc tiêm `WebGUIFactory` vào client đó đáng ra phải bị từ chối ở bước lắp ráp dependency. Với interface chung quá rộng, ứng dụng chỉ phát hiện không phù hợp **khi thực sự gọi** `createTrayIcon()`.

~~~mermaid
flowchart TD
    A["Client nhận GUIFactory"] --> B["Gọi createTrayIcon()"]
    B --> C{"Concrete factory có năng lực?"}
    C -->|Có| D["Trả NativeTrayIcon"]
    C -->|Không| E["Trả null / throw"]
    E --> F["Runtime failure hoặc client phải xử lý ngoại lệ"]
~~~

Tuy nhiên, **`UnsupportedOperationException` không phải luôn là dấu hiệu vi phạm thiết kế**. Trong Java, có các interface hoặc API **công khai quy định một số thao tác là tùy chọn**. Ví dụ nhiều collection không sửa đổi cho phép đọc nhưng ném `UnsupportedOperationException` khi gọi thao tác thêm/xóa. Nếu hợp đồng đã quy định rõ điều kiện hỗ trợ, việc ném ngoại lệ có thể phù hợp.

Ở đây, vấn đề cụ thể là **một Abstract Factory được dùng như hợp đồng tạo một họ sản phẩm đầy đủ**, nhưng một số concrete factory **vĩnh viễn không thể cung cấp sản phẩm mà interface đang quảng bá**. Nếu mọi caller phải hiểu tập con năng lực của từng họ, nên xem lại kiểu factory hoặc cấu trúc capability.

## 5. Anti-pattern thứ ba: trả đối tượng no-op để che thiếu năng lực

Giả sử muốn loại bỏ `null` và ngoại lệ, một nhóm tạo:

~~~java
final class NoOpTrayIcon implements NativeTrayIcon {
    @Override
    public void show() {
        // Không thực hiện gì.
    }
}
~~~

Trong khi đó:

~~~java
NativeTrayIcon tray = factory.createTrayIcon();
tray.show(); // Không lỗi, nhưng cũng không hiển thị gì
~~~

Nếu client cần biểu tượng khay để người dùng truy cập ứng dụng, hành vi **“không làm gì”** là thất bại về chức năng dù test chỉ kiểm tra “không ném ngoại lệ” vẫn có thể xanh.

**Null Object là một mẫu hữu ích khi “không hành động” là hành vi hợp lệ theo hợp đồng.** Chẳng hạn `NoOpMetricsRecorder` có thể phù hợp nếu việc thu thập số liệu là tùy chọn và không được phép làm hỏng nghiệp vụ chính. Nhưng `NoOpTrayIcon` không thể thay thế `NativeTrayIcon` có nghĩa vụ xuất hiện trên khay hệ thống nếu người dùng yêu cầu chức năng đó.

Khi review một no-op product, hãy hỏi: “Nếu phương thức trả thành công mà không tạo hiệu quả quan sát được, client có còn hoàn thành đúng lời hứa với người dùng không?” Nếu không, no-op chỉ đang **giấu lỗi tại một vị trí khó nhìn hơn**.

## 6. Phân biệt các trạng thái thường bị trộn lẫn

| Tình huống | Ví dụ | Cách xử lý nên cân nhắc |
| --- | --- | --- |
| **Họ không hỗ trợ năng lực** | Web không tạo native tray | Tách capability; client chuyên biệt nhận interface phù hợp |
| **Implementation chưa hoàn tất** | Windows phải hỗ trợ tray nhưng chưa viết | Hoàn tất tính năng hoặc đánh dấu chưa sẵn sàng; không giả vờ hoàn thành |
| **Thiếu dữ liệu của một lần gọi** | Tra cứu đơn hàng không tìm thấy | Dùng kiểu kết quả phù hợp, `Optional` nếu có ý nghĩa |
| **Dữ liệu đầu vào không hợp lệ** | Factory cần theme nhưng nhận `null` | Xác định hợp đồng validation; ném `IllegalArgumentException` hoặc `NullPointerException` có chủ đích |
| **Lỗi tài nguyên tại runtime** | Tray có hỗ trợ nhưng OS API tạm lỗi | Lỗi miền hoặc ngoại lệ phù hợp; xử lý/log/retry theo chính sách |
| **Thao tác được ghi rõ là tùy chọn** | Collection không hỗ trợ sửa đổi | `UnsupportedOperationException` có thể phù hợp với hợp đồng công bố |
| **Không hành động là kết quả hợp lệ** | Thu thập metrics bị tắt theo cấu hình | Một no-op product có thể có ý nghĩa |

Điểm chung cần tránh là dùng một biểu hiện `null`/`UnsupportedOperationException` cho **tất cả những trường hợp**. Không có dữ liệu, thiếu năng lực, lỗi cấu hình và lỗi runtime là những vấn đề khác nhau; nếu thiết kế đánh đồng chúng, code khách hàng sẽ khó xử lý chính xác.

## 7. Cách sửa: tách hợp đồng theo năng lực

Với ví dụ GUI, giữ `GUIFactory` mô tả **phần chung**:

~~~java
interface GUIFactory {
    Button createButton();
    Checkbox createCheckbox();
}
~~~

Tách khả năng tạo tray ra khỏi phần chung:

~~~java
interface TrayIconFactory {
    NativeTrayIcon createTrayIcon();
}
~~~

Những client chỉ cần `Button` và `Checkbox` nhận `GUIFactory`. Những client **chỉ cần tray** nhận `TrayIconFactory`. Với client desktop phải tạo cả ba sản phẩm **cùng một họ**, có thể sử dụng một interface gộp:

~~~java
interface DesktopGUIFactory extends GUIFactory, TrayIconFactory {
    // Kế thừa cả ba phương thức.
}
~~~

Windows/macOS triển khai `DesktopGUIFactory`, Web chỉ triển khai `GUIFactory`. Khi đó:

~~~java
final class DesktopShell {
    private final DesktopGUIFactory factory;

    DesktopShell(DesktopGUIFactory factory) {
        this.factory = factory;
    }

    void openTray() {
        factory.createTrayIcon().show();
    }
}
~~~

`new DesktopShell(new WebGUIFactory())` sẽ **không biên dịch**, vì `WebGUIFactory` không phải `DesktopGUIFactory`. Việc thiếu khả năng được thể hiện **ngay trong kiểu tham số**, thay vì đợi đến lúc một phương thức ném ngoại lệ.

### Tại sao không truyền hai factory hoàn toàn độc lập?

Nếu một client nhận `GUIFactory` và `TrayIconFactory` qua hai tham số:

~~~java
DesktopShell(GUIFactory guiFactory, TrayIconFactory trayFactory) {
    // ...
}
~~~

composition root có thể vô tình ghép **Windows GUI với macOS tray**. Đó là một lỗi của **tính nhất quán họ sản phẩm**. Nếu client cần cả bộ và mọi sản phẩm phải cùng biến thể, `DesktopGUIFactory` có thể gộp hai capability dưới **một concrete factory**. Nếu các khả năng thật sự độc lập và được phép trộn, việc tiêm hai factory riêng cũng có thể hợp lý.

~~~mermaid
classDiagram
    class GUIFactory {
        <<interface>>
        +createButton() Button
        +createCheckbox() Checkbox
    }
    class TrayIconFactory {
        <<interface>>
        +createTrayIcon() NativeTrayIcon
    }
    class DesktopGUIFactory {
        <<interface>>
    }
    class WindowsFactory
    class MacFactory
    class WebFactory
    GUIFactory <|-- DesktopGUIFactory
    TrayIconFactory <|-- DesktopGUIFactory
    DesktopGUIFactory <|.. WindowsFactory
    DesktopGUIFactory <|.. MacFactory
    GUIFactory <|.. WebFactory
~~~

Đây là một cách áp dụng **Interface Segregation Principle**: mỗi client chỉ phụ thuộc những phương thức nó có lý do sử dụng. Các factory Web không phải có phương thức tray giả, trong khi client desktop có hợp đồng đầy đủ.

## 8. Ví dụ Java tự chứa: hợp đồng chính xác thay vì trả `null`

Đoạn mã sau đặt trong một file `Demo.java` (Java 8+), dùng các phương thức trả chuỗi để mô phỏng giao diện. Chỉ `Demo` là `public`; các kiểu còn lại package-private. Các đoạn mã ở các mục trước là **biến thể minh họa**, không ghép lại cùng file này.

~~~java
import java.util.Objects;

enum Platform {
    WINDOWS, MACOS, WEB
}

interface Button {
    Platform platform();
    String draw();
}

interface Checkbox {
    Platform platform();
    String draw();
}

interface NativeTrayIcon {
    Platform platform();
    void show();
}

interface GUIFactory {
    Button createButton();
    Checkbox createCheckbox();
}

interface TrayIconFactory {
    NativeTrayIcon createTrayIcon();
}

interface DesktopGUIFactory extends GUIFactory, TrayIconFactory {
}

final class WindowsButton implements Button {
    @Override
    public Platform platform() {
        return Platform.WINDOWS;
    }

    @Override
    public String draw() {
        return "Windows button";
    }
}

final class WindowsCheckbox implements Checkbox {
    @Override
    public Platform platform() {
        return Platform.WINDOWS;
    }

    @Override
    public String draw() {
        return "Windows checkbox";
    }
}

final class WindowsTrayIcon implements NativeTrayIcon {
    @Override
    public Platform platform() {
        return Platform.WINDOWS;
    }

    @Override
    public void show() {
        System.out.println("Windows native tray icon");
    }
}

final class MacButton implements Button {
    @Override
    public Platform platform() {
        return Platform.MACOS;
    }

    @Override
    public String draw() {
        return "macOS button";
    }
}

final class MacCheckbox implements Checkbox {
    @Override
    public Platform platform() {
        return Platform.MACOS;
    }

    @Override
    public String draw() {
        return "macOS checkbox";
    }
}

final class MacTrayIcon implements NativeTrayIcon {
    @Override
    public Platform platform() {
        return Platform.MACOS;
    }

    @Override
    public void show() {
        System.out.println("macOS native tray icon");
    }
}

final class WebButton implements Button {
    @Override
    public Platform platform() {
        return Platform.WEB;
    }

    @Override
    public String draw() {
        return "Web button";
    }
}

final class WebCheckbox implements Checkbox {
    @Override
    public Platform platform() {
        return Platform.WEB;
    }

    @Override
    public String draw() {
        return "Web checkbox";
    }
}

final class WindowsFactory implements DesktopGUIFactory {
    @Override
    public Button createButton() {
        return new WindowsButton();
    }

    @Override
    public Checkbox createCheckbox() {
        return new WindowsCheckbox();
    }

    @Override
    public NativeTrayIcon createTrayIcon() {
        return new WindowsTrayIcon();
    }
}

final class MacFactory implements DesktopGUIFactory {
    @Override
    public Button createButton() {
        return new MacButton();
    }

    @Override
    public Checkbox createCheckbox() {
        return new MacCheckbox();
    }

    @Override
    public NativeTrayIcon createTrayIcon() {
        return new MacTrayIcon();
    }
}

final class WebFactory implements GUIFactory {
    @Override
    public Button createButton() {
        return new WebButton();
    }

    @Override
    public Checkbox createCheckbox() {
        return new WebCheckbox();
    }
}

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
        System.out.println(button.draw());
        System.out.println(checkbox.draw());
    }
}

final class DesktopScreen {
    private final DesktopGUIFactory factory;

    DesktopScreen(DesktopGUIFactory factory) {
        this.factory = Objects.requireNonNull(factory, "factory");
    }

    void show() {
        new CommonScreen(factory).show();
        NativeTrayIcon tray = Objects.requireNonNull(
                factory.createTrayIcon(), "tray");
        tray.show();
    }
}

public final class Demo {
    public static void main(String[] args) {
        new DesktopScreen(new WindowsFactory()).show();
        new DesktopScreen(new MacFactory()).show();
        new CommonScreen(new WebFactory()).show();
    }
}
~~~

**Kết quả mô phỏng dự kiến:**

~~~text
Windows button
Windows checkbox
Windows native tray icon
macOS button
macOS checkbox
macOS native tray icon
Web button
Web checkbox
~~~

Trong ví dụ:

- `CommonScreen` luôn nhận `GUIFactory`, vì nó chỉ cần hai sản phẩm chung.
- `DesktopScreen` nhận `DesktopGUIFactory`, vì nó cần đủ ba loại sản phẩm và phải ghép chúng theo cùng biến thể.
- `WebFactory` không có `createTrayIcon()`, do đó không cần trả `null` hoặc ném `UnsupportedOperationException`.
- Composition root (ở đây là `Demo.main()`) cấp factory phù hợp với từng loại client.
- `Objects.requireNonNull` giúp báo lỗi sớm nếu implementation vi phạm quy ước trả sản phẩm hợp lệ; **không phải** giải pháp thay thế việc thiết kế contract cho đúng.

Lớp `NativeTrayIcon` trong ví dụ mô phỏng sự kiện bằng `System.out.println`; nó không sử dụng API khay hệ thống thật. Trong dự án desktop thực tế có thể dùng Java AWT `SystemTray`/`TrayIcon` hoặc API của framework phù hợp, đồng thời kiểm tra khả năng hỗ trợ của hệ điều hành và môi trường đang chạy.

## 9. Khi nào nên giữ một sản phẩm chung thay vì tách capability?

Đôi khi sản phẩm mới thực ra **có thể được trừu tượng hóa theo một nhu cầu chung**. Nếu mục tiêu là “cung cấp điều hướng chính” và cả desktop lẫn Web đều có cách cung cấp chức năng này, một interface `NavigationComponent` có thể có ý nghĩa hơn `NativeTrayIcon`.

Khi đó, mọi concrete factory có thể triển khai `createNavigation()` để trả một đối tượng đáp ứng hợp đồng:

~~~java
interface NavigationComponent {
    void open();
}

interface NavigationFactory {
    NavigationComponent createNavigation();
}
~~~

Đây là **một thiết kế thay thế** cho một yêu cầu khác, không phải phương thức cần thêm vào `GUIFactory` của file `Demo.java`.

Hãy thận trọng: không nên đổi tên `NativeTrayIcon` thành `NavigationComponent` chỉ để “đủ số họ” nếu các client vẫn cần những hành vi chỉ có trên desktop. Abstraction chỉ tốt khi **mỗi implementation thực hiện được cùng hành vi mà client cần**, không bắt client kiểm tra `instanceof` hoặc phân nhánh theo nền tảng ở mọi nơi.

## 10. `Optional`, Result và ngoại lệ: chọn theo ý nghĩa nghiệp vụ

Một số API thật sự có kết quả tùy chọn:

~~~java
Optional<NativeTrayIcon> findExistingTrayIcon();
~~~

Tên `findExistingTrayIcon()` thể hiện việc **tra cứu** một đối tượng đã tồn tại và có thể không tìm thấy. `Optional.empty()` phù hợp khi vắng mặt là một trường hợp bình thường **được mô tả trong hợp đồng**.

Nhưng nếu yêu cầu của client là “tạo một native tray icon và bảo đảm nó hiển thị”, việc đổi `NativeTrayIcon createTrayIcon()` thành `Optional<NativeTrayIcon> createTrayIcon()` không giải quyết triệt để: client vẫn phải hỏi tại runtime Web có hỗ trợ hay không, dù khả năng này là đặc tính ổn định của họ.

Tương tự, khi một factory có thể hỗ trợ tray nhưng hệ điều hành hiện tại không cho phép tạo (ví dụ chế độ headless), có thể dùng một kiểu kết quả với lý do lỗi hoặc ngoại lệ thích hợp theo API. Đây là **lỗi điều kiện thực thi**, khác với việc Web factory **không có năng lực về mặt thiết kế**.

Một quy tắc thực dụng:

| Ý nghĩa thực tế | Cách biểu đạt thường rõ hơn |
| --- | --- |
| Client luôn cần sản phẩm và họ có thể tạo | Phương thức factory trả sản phẩm; thất bại thực sự được mô tả trong contract |
| Một loại client cần năng lực mà nhiều họ không có | Interface capability riêng, composition root cấp đúng dependency |
| Một đối tượng có thể không tồn tại khi tra cứu | `Optional<T>` hoặc kiểu kết quả có trạng thái |
| Thao tác là tùy chọn theo contract được công bố | Có thể dùng ngoại lệ được quy định, hoặc phương thức kiểm tra năng lực |
| Không hành động là kết quả hợp lệ | Null Object/no-op có thể phù hợp |
| Khởi tạo thất bại do môi trường hoặc cấu hình | Lỗi/exception phù hợp với nguyên nhân; log và xử lý ở ranh giới thích hợp |

Không có công cụ nào thay thế được việc **định nghĩa đúng lời hứa của interface**. Thay `null` bằng `Optional`, hoặc thay ngoại lệ bằng một no-op object, đôi khi chỉ đổi bề ngoài của cùng một lỗi thiết kế.

## 11. Unit test phải kiểm tra hợp đồng, không “hợp thức hóa” anti-pattern

Một test như sau là dấu hiệu đáng nghi:

~~~java
@Test
void webDoesNotSupportTray() {
    GUIFactory factory = new WebGUIFactory();
    assertThrows(UnsupportedOperationException.class,
            factory::createTrayIcon);
}
~~~

Nếu interface có ý nghĩa **mọi factory đều phải tạo sản phẩm**, test trên đang xác nhận một implementation không phù hợp thay vì kiểm tra đúng contract. Bài kiểm tra thích hợp hơn sau khi tách interface là:

- Mọi `GUIFactory` tạo được `Button` và `Checkbox` phù hợp.
- Mọi `DesktopGUIFactory` tạo được thêm `NativeTrayIcon` hợp lệ.
- Sản phẩm tạo ra thuộc **đúng họ** và có thể phối hợp.
- Một client desktop không nhận được Web factory qua kiểu `DesktopGUIFactory`.

Ví dụ JUnit Jupiter (JUnit 5) dùng các kiểu từ file `Demo.java`:

~~~java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class FactoryContractTest {
    private void assertCommonFamily(
            GUIFactory factory, Platform expected) {
        Button button = factory.createButton();
        Checkbox checkbox = factory.createCheckbox();

        assertNotNull(button);
        assertNotNull(checkbox);
        assertAll("common family",
                () -> assertEquals(expected, button.platform()),
                () -> assertEquals(expected, checkbox.platform()),
                () -> assertEquals(button.platform(), checkbox.platform()));
    }

    private void assertDesktopFamily(
            DesktopGUIFactory factory, Platform expected) {
        assertCommonFamily(factory, expected);

        NativeTrayIcon tray = factory.createTrayIcon();
        assertNotNull(tray);
        assertEquals(expected, tray.platform());
        assertDoesNotThrow(tray::show);
    }

    @Test
    void windowsFactoryCreatesCompleteDesktopFamily() {
        assertDesktopFamily(new WindowsFactory(), Platform.WINDOWS);
    }

    @Test
    void macFactoryCreatesCompleteDesktopFamily() {
        assertDesktopFamily(new MacFactory(), Platform.MACOS);
    }

    @Test
    void webFactoryCreatesCommonFamily() {
        assertCommonFamily(new WebFactory(), Platform.WEB);
    }
}
~~~

`FactoryContractTest` minh họa các kiểm tra tối thiểu. `assertDoesNotThrow(tray::show)` chỉ chứng minh thao tác mô phỏng không ném ngoại lệ; **nó không tự chứng minh biểu tượng hiển thị đúng trong OS thật**. Với GUI thật cần có kiểm thử tích hợp phù hợp với framework, môi trường desktop và điều kiện hỗ trợ `SystemTray`.

Một sai lầm khác là chỉ kiểm tra hai sản phẩm **cùng nhau** mà quên biến thể kỳ vọng. Ví dụ cả `Button` và `Checkbox` của `WindowsFactory` đều bị tạo theo Web; phép kiểm tra `button.platform() == checkbox.platform()` vẫn qua. Vì vậy ví dụ kiểm tra **từng sản phẩm so với `expected`** trước khi kiểm tra tính nhất quán.

## 12. Ranh giới giữa LSP, ISP và hợp đồng rõ ràng

**Interface Segregation Principle (ISP)** khuyến khích mỗi client phụ thuộc vào nhóm phương thức nó cần. Nếu client Web chỉ cần nút và ô chọn, việc buộc nó biết phương thức tray không hợp lý. Tách `GUIFactory` và `TrayIconFactory` giúp biểu đạt hai nhóm năng lực khác nhau.

**Liskov Substitution Principle (LSP)** liên quan đến việc có thể thay thế một đối tượng bằng implementation của interface/base type **mà vẫn tuân theo những điều kiện đã được công bố**. Nếu client có quyền giả định `GUIFactory.createTrayIcon()` tạo được một tray hợp lệ, `WebGUIFactory` luôn trả `null` hoặc ném `UnsupportedOperationException` có thể làm hỏng khả năng thay thế ấy.

Nhưng không nên kết luận “hễ ném `UnsupportedOperationException` là vi phạm LSP” trong mọi API. Nếu **hợp đồng công khai ngay từ đầu quy định rõ thao tác tùy chọn và cách xử lý khi không hỗ trợ**, các implementation làm đúng quy định có thể vẫn thỏa mãn hợp đồng. Vấn đề của bài là việc dùng ngoại lệ để **che giấu một interface đã lựa chọn sai ranh giới**, khiến client chịu chi phí kiểm tra không cần thiết.

**Dependency Inversion Principle (DIP)** xuất hiện khi client desktop phụ thuộc `DesktopGUIFactory` như một abstraction; composition root cung cấp `WindowsFactory` hoặc `MacFactory`. Mã nghiệp vụ không cần tự `new` một concrete factory rồi bắt lỗi trong từng phương thức.

Ba nguyên tắc này bổ trợ nhau, nhưng **một cấu trúc nhiều interface chưa tự động tốt hơn**. Nếu mọi họ đều hỗ trợ đầy đủ các sản phẩm và client luôn cần dùng chúng cùng nhau, một Abstract Factory thống nhất có thể đơn giản và chính xác hơn.

## 13. Quy trình refactor khi hệ thống đã có `null` hoặc ngoại lệ

Với một codebase Java hiện hữu đã thêm `createTrayIcon()` vào `GUIFactory` và Web đang trả `null`, nên tiến hành có kiểm soát:

1. **Tìm chính xác các implementation và call site:** xem interface, concrete factory, test double, adapter và các nơi gọi `createTrayIcon()`. Tập trung vào chỗ **quy tắc chọn khả năng** đang lặp hoặc bị đẩy sang client.
2. **Làm rõ yêu cầu sản phẩm:** đánh dấu theo họ là “bắt buộc”, “không áp dụng”, “chưa triển khai” hoặc “tùy ngữ cảnh runtime”. Không xếp thiếu triển khai vào “không áp dụng” chỉ để tránh sửa.
3. **Xác định hợp đồng chung thật sự:** giữ `createButton()`, `createCheckbox()` trong `GUIFactory` nếu mọi họ đều có; đưa `createTrayIcon()` sang `TrayIconFactory`.
4. **Quyết định nhu cầu ghép cùng họ:** nếu client cần cả GUI và tray cùng biến thể, cân nhắc `DesktopGUIFactory extends GUIFactory, TrayIconFactory`; nếu năng lực độc lập, tiêm interface nhỏ riêng.
5. **Chuyển các concrete factory hỗ trợ:** Windows/macOS implement interface phù hợp, trả về sản phẩm hợp lệ; Web chỉ implement phần chung.
6. **Chuyển client:** luồng desktop khai báo constructor nhận `DesktopGUIFactory`; luồng Web không gọi phương thức tray và không cần kiểm tra `null` cho sản phẩm không áp dụng.
7. **Cập nhật composition root/DI:** cấp đúng loại factory tại điểm lắp ráp. Không ghép các factory từ hai biến thể khác nhau trong cùng một client cần sản phẩm tương thích.
8. **Đổi test theo đúng hợp đồng:** bỏ các test chỉ xác nhận factory Web luôn throw/null để thay bằng test phần chung, test capability và test phối hợp.
9. **Đánh giá tương thích API:** nếu `GUIFactory` là API công khai của plugin hoặc thư viện, việc xóa phương thức có thể gây breaking change; cân nhắc adapter hoặc phiên bản API mới theo kế hoạch phát hành.
10. **Loại bỏ đường đi lỗi thời sau khi hoàn tất chuyển đổi:** chỉ xóa nhánh trả `null`/throw và các kiểm tra vòng vo khi không còn caller hợp lệ dựa vào đường đi ấy.

### Dấu hiệu nên tìm trong review

| Dấu hiệu trong Java | Câu hỏi cần đặt |
| --- | --- |
| `return null;` bên trong một phương thức `create...()` | Kết quả vắng mặt có nằm trong hợp đồng hay chỉ do họ không hỗ trợ? |
| `throw new UnsupportedOperationException(...)` trong concrete factory | Tại sao factory phải implement phương thức nó không thể thực hiện? |
| `return new NoOp...();` | Không làm gì có thật sự là hành vi hợp lệ của sản phẩm? |
| `if (factory instanceof WindowsFactory)` ở client | Có đang rò rỉ lựa chọn biến thể hoặc thiếu interface capability? |
| `if (factory.createX() != null)` lặp lại | Có nên thể hiện tính tùy chọn bằng kiểu riêng hoặc chọn đúng factory sớm hơn? |
| `@Test` xác nhận concrete factory throw cho tính năng bắt buộc | Test đang bảo vệ hợp đồng hay bảo vệ workaround? |
| `default createX() { throw ...; }` trong interface chung | Default này có hành vi hợp lệ cho mọi factory hay chỉ tránh lỗi compile? |

Tránh sửa theo kiểu tìm và thay thế máy móc: cùng một `return null` có thể mang ý nghĩa khác nhau tùy quy ước API. Nên đọc ngữ cảnh và kiểm tra những client thật sự đang phụ thuộc vào giá trị đó.

## 14. Các đánh đổi của giải pháp tách capability

| Lựa chọn | Điểm mạnh | Chi phí / giới hạn |
| --- | --- | --- |
| Một interface `GUIFactory` lớn | Một entry point, dễ hiểu khi mọi họ có cùng tập sản phẩm | Nếu vài họ thiếu năng lực sẽ phát sinh throw/null/no-op và test phức tạp |
| `GUIFactory` + `TrayIconFactory` riêng | Client chỉ phụ thuộc năng lực cần thiết | Composition root phải quản lý thêm dependency; có nguy cơ ghép sai họ nếu client nhận hai factory |
| `DesktopGUIFactory` kế thừa hai capability | Client desktop nhận một factory có đủ ba sản phẩm | Thêm tầng interface; chỉ hợp lý nếu nhóm desktop thật sự đồng nhất |
| Chuyển sang `NavigationComponent` chung | Có thể phù hợp nếu nhu cầu thực sự giống nhau trên mọi họ | Dễ trừu tượng hóa quá mức, giấu những khác biệt quan trọng |
| `Optional`/Result cho phương thức tạo | Diễn tả sự vắng mặt hoặc lỗi hợp lệ khi chúng thuộc hợp đồng | Client vẫn xử lý runtime, không sửa lỗi phân loại năng lực theo họ |

Không nên chọn giải pháp chỉ dựa trên số lượng class ít nhất. Một interface nhỏ hơn có thể giúp API chính xác và giảm thay đổi lan truyền; nhưng quá nhiều interface một phương thức cũng có thể làm sơ đồ phụ thuộc khó theo dõi. Hãy giữ những sản phẩm thực sự cần đi cùng nhau dưới một hợp đồng chung, và tách những khả năng chỉ một số client/họ sử dụng.

## 15. Bài tập tự luyện

### Bài tập A — Phân tích factory trả `null`

`DocumentFactory` tạo `Editor` và `Viewer` cho Windows, Web và Android. Nhóm Android muốn thêm `ShareSheet`, một sản phẩm gắn với hệ điều hành. `WebDocumentFactory.createShareSheet()` trả `null`.

**Yêu cầu:** nêu ba tác động đến client, xác định `ShareSheet` có phải sản phẩm chung thật sự không, và đề xuất interface capability phù hợp. Nếu một client Android cần đồng thời `Editor` và `ShareSheet` cùng ngữ cảnh, bạn bảo đảm sự tương thích như thế nào?

### Bài tập B — Phân biệt ngoại lệ đúng và sai hợp đồng

Đánh giá hai trường hợp:

1. `WebFactory.createNativeTrayIcon()` luôn ném `UnsupportedOperationException` dù interface chung không ghi phương thức là tùy chọn.
2. Một collection chỉ đọc ném `UnsupportedOperationException` khi gọi `add()`, đúng như hợp đồng thao tác tùy chọn đã công bố.

**Yêu cầu:** giải thích vì sao không nên đánh giá cả hai trường hợp chỉ dựa vào tên exception. Quy tắc nào khác nhau trong lời hứa của API?

### Bài tập C — Chọn abstraction cho client

Hệ thống có `Dashboard` chỉ dùng `Button`/`Checkbox`, `TrayService` chỉ dùng `NativeTrayIcon`, và `DesktopShell` luôn cần cả ba sản phẩm cùng nền tảng.

**Yêu cầu:** gán cho từng client một trong các type `GUIFactory`, `TrayIconFactory` hoặc `DesktopGUIFactory`, rồi giải thích vì sao `DesktopShell` có thể hưởng lợi từ interface gộp.

### Bài tập D — Tránh test “xanh giả”

Một test chỉ kiểm tra:

~~~java
assertDoesNotThrow(() -> factory.createTrayIcon().show());
~~~

`WebFactory` trả một `NoOpTrayIcon` và test qua.

**Yêu cầu:** test đã chứng minh được điều gì và chưa chứng minh được điều gì? Nếu yêu cầu là biểu tượng phải xuất hiện trên khay hệ thống, nên bổ sung lớp kiểm thử nào và nên cấp factory type gì cho client?

### Bài tập E — Khi không cần tách

Một nhóm muốn chuyển `createTextField()` khỏi `GUIFactory` chỉ vì implementation Windows chưa hoàn thành, mặc dù cả Windows, macOS, Web đều phải có text field.

**Yêu cầu:** phân biệt “không có năng lực” với “chưa triển khai”. Giải thích vì sao giữ hợp đồng chung và hoàn tất `WindowsTextField` có thể phù hợp hơn.

## 16. Checklist nhận diện và khắc phục

- [ ] Xác định những phương thức factory có `return null`, `UnsupportedOperationException` hoặc sản phẩm no-op.
- [ ] Đọc hợp đồng để biết kết quả có được phép vắng mặt và ngoại lệ có được công bố hay không.
- [ ] Phân loại đúng “không áp dụng”, “chưa triển khai”, “không có dữ liệu” và “lỗi runtime”.
- [ ] Có ma trận những loại sản phẩm mà từng họ **thực sự hỗ trợ**.
- [ ] Interface chung chỉ cam kết những khả năng có ý nghĩa cho mọi concrete factory thực hiện nó.
- [ ] Client chuyên biệt nhận đúng interface capability khi cần sản phẩm riêng.
- [ ] Nếu cần nhiều loại sản phẩm **cùng họ**, có cách ghép factory nhất quán.
- [ ] Không dùng `Optional`, no-op hoặc default throw chỉ để che việc định nghĩa sai hợp đồng.
- [ ] Có test cho từng concrete factory theo đúng hợp đồng nó implement; test không “hợp thức hóa” lỗi thiếu năng lực.
- [ ] Đã đánh giá thay đổi API, adapter, DI, tương thích plugin và lộ trình chuyển client.
- [ ] Đã tính đến trường hợp ngoại lệ hoặc `null` thật sự hợp lệ theo hợp đồng đã công bố.

**Ghi nhớ:** Nếu một concrete factory **vĩnh viễn không thể tạo loại sản phẩm được Abstract Factory công bố**, việc trả `null` hay ném `UnsupportedOperationException` chỉ chuyển một sai lệch thiết kế thành lỗi runtime. Hãy sửa **lời hứa của interface**: giữ phần sản phẩm chung, tách capability dành cho những họ thực sự hỗ trợ và yêu cầu client nhận đúng loại factory. Khi một thao tác thật sự tùy chọn, hãy công bố và kiểm thử quy ước đó rõ ràng thay vì để client tự suy đoán.

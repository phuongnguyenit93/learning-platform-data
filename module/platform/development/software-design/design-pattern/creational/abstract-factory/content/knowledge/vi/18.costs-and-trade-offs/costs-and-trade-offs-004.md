# Đánh giá chi phí bảo trì khi các họ sản phẩm phát triển không đồng đều

**Abstract Factory** giúp mã khách hàng tạo và sử dụng **một họ sản phẩm tương thích** thông qua các interface chung. Lợi ích rõ nhất xuất hiện khi những biến thể khác nhau cùng cần một tập loại sản phẩm tương đối ổn định: muốn bổ sung họ mới, ta tạo một `ConcreteFactory` mới và các implementation tương ứng.

Tuy nhiên, trong dự án thực tế, các **họ sản phẩm không nhất thiết phát triển cùng tốc độ hoặc cùng nhu cầu**. Một giao diện Windows có thể cần biểu tượng ở khay hệ thống, trong khi giao diện Web không có khái niệm đó. Một nhà cung cấp thanh toán có tính năng hoàn tiền từng phần, nhà cung cấp khác chỉ hoàn toàn bộ. Nếu liên tục mở rộng cùng một `AbstractFactory` để chứa mọi khả năng riêng của từng họ, chi phí bảo trì có thể vượt quá lợi ích ban đầu.

Bài học thuộc chương **Chi phí và đánh đổi** của module `SOFTWARE_DESIGN_DESIGN_PATTERN_CREATIONAL_ABSTRACT_FACTORY`, trong lộ trình **Học về abstract factory trong design pattern**. Trọng tâm là **đánh giá chi phí bảo trì khi các họ sản phẩm tiến hóa không đồng đều**, từ thay đổi source code, kiểm thử, phối hợp phát hành đến các phương án chia tách hợp đồng. Mục tiêu là quyết định dựa trên tính chất thay đổi thật sự, thay vì mặc định phải mở rộng một interface chung.

Sau bài này, bạn sẽ có thể:

- Phân biệt việc **thêm họ sản phẩm** với việc **thêm loại sản phẩm** và **thêm khả năng chỉ một số họ hỗ trợ**.
- Nhận diện chi phí phát sinh khi một thay đổi cục bộ buộc tất cả `ConcreteFactory` phải cập nhật.
- Ước lượng phạm vi sửa mã, số lượng kiểm thử và chi phí phối hợp khi các họ có nhịp phát triển khác nhau.
- Đề xuất cách giữ hợp đồng chung ổn định, tách khả năng tùy chọn hoặc tổ chức factory theo từng nhóm khả năng.
- Giải thích đánh đổi của mỗi phương án bằng ví dụ Java, không chỉ bằng khẩu hiệu thiết kế.

## 1. Hai trục phát triển của Abstract Factory

Xét một hệ thống giao diện có ba biến thể: **Windows**, **Web** và **thiết bị nhúng**. Ban đầu, cả ba đều cần hai loại sản phẩm chung:

~~~java
interface GUIFactory {
    Button createButton();
    Checkbox createCheckbox();
}
~~~

Mỗi factory tạo các sản phẩm thích hợp với môi trường tương ứng:

| Họ sản phẩm | `Button` | `Checkbox` |
| --- | --- | --- |
| Windows | `WindowsButton` | `WindowsCheckbox` |
| Web | `WebButton` | `WebCheckbox` |
| Embedded | `EmbeddedButton` | `EmbeddedCheckbox` |

Ở giai đoạn này, `GUIFactory` là một hợp đồng **tương đối đồng nhất**: mọi họ đều đáp ứng hai loại sản phẩm mà mã khách hàng thực sự cần.

Sau vài đợt phát triển, yêu cầu bắt đầu khác nhau:

| Loại sản phẩm/khả năng | Windows | Web | Embedded |
| --- | --- | --- | --- |
| Nút bấm | Có | Có | Có |
| Ô chọn | Có | Có | Có |
| Biểu tượng khay hệ thống của OS | Có | Không có khái niệm tương đương | Không có khái niệm tương đương |
| Tích hợp thông báo của trình duyệt | Không | Có | Không |
| Phản hồi nút bấm phần cứng | Không | Không | Có |

Ma trận này cho thấy sự khác biệt giữa:

1. **Loại sản phẩm chung**: mọi họ đều có `Button` và `Checkbox`; một `GUIFactory` chung có ý nghĩa.
2. **Khả năng riêng của từng họ**: tray icon, browser notification hoặc hardware feedback không nhất thiết là những sản phẩm mà **mọi** factory phải tạo.

Lưu ý: từ **“họ sản phẩm”** nói đến *biến thể* như Windows/Web/Embedded; từ **“loại sản phẩm”** nói đến *vai trò trừu tượng* như `Button` hoặc `Checkbox`. Nhầm hai trục này dễ dẫn đến kết luận sai về khả năng mở rộng của Abstract Factory.

### Vì sao gọi là phát triển không đồng đều?

Sự không đồng đều có thể xuất hiện theo nhiều cách:

- **Khác tính năng:** chỉ một số họ có sản phẩm hoặc năng lực mới.
- **Khác nhịp phát hành:** Windows đã hỗ trợ API mới, nhưng bản Embedded phải duy trì giao thức cũ nhiều tháng.
- **Khác mức độ sử dụng:** ứng dụng Web thay đổi giao diện thường xuyên, trong khi bản Embedded được cập nhật rất ít.
- **Khác giới hạn môi trường:** khả năng có ý nghĩa trên nền tảng này nhưng không tồn tại trên nền tảng khác.
- **Khác yêu cầu tương thích:** một họ có thể thay đổi constructor hoặc SDK nền tảng mà các họ còn lại không đổi.

Không phải mọi khác biệt đều cần sửa Abstract Factory. Nếu Windows chỉ thay cách vẽ `WindowsButton` nhưng vẫn tuân theo `Button`, `GUIFactory` có thể hoàn toàn ổn định. Chi phí lớn xuất hiện khi **sự khác biệt bị đẩy lên hợp đồng chung**.

## 2. Chi phí lan truyền khi thêm phương thức vào interface chung

Giả sử nhóm Windows cần thêm biểu tượng khay hệ thống. Một cách viết vội vàng là bổ sung:

~~~java
interface GUIFactory {
    Button createButton();
    Checkbox createCheckbox();

    TrayIcon createTrayIcon(); // Chỉ Windows thực sự cần
}
~~~

Ngay lập tức phát sinh câu hỏi: `WebFactory` và `EmbeddedFactory` sẽ hiện thực `createTrayIcon()` như thế nào?

~~~java
final class WebFactory implements GUIFactory {
    @Override
    public Button createButton() {
        return new WebButton();
    }

    @Override
    public Checkbox createCheckbox() {
        return new WebCheckbox();
    }

    @Override
    public TrayIcon createTrayIcon() {
        throw new UnsupportedOperationException(
                "System tray is unavailable on Web");
    }
}
~~~

*Đoạn trên là ví dụ phản diện:* `TrayIcon` và các sản phẩm Web được giả định đã khai báo; nó minh họa việc thêm một phương thức **không thuộc hợp đồng chung thật sự**. Lớp vẫn có thể biên dịch, nhưng lời gọi `createTrayIcon()` có thể thất bại lúc chạy. Nếu Java client chỉ nhìn kiểu `GUIFactory`, client không biết mọi factory có hỗ trợ phương thức này hay không.

Hai phương án chữa cháy thường thấy cũng có vấn đề:

- Trả về `null`: mọi caller phải nhớ kiểm tra, dễ gặp `NullPointerException` và làm yếu hợp đồng trả về.
- Trả một `NoOpTrayIcon`: có thể che giấu một tính năng thực sự không được hỗ trợ, khiến người dùng nghĩ biểu tượng đã hiển thị. Null Object chỉ hợp lý nếu hành vi “không làm gì” **được xác định là một kết quả hợp lệ** của nghiệp vụ.

Nếu thêm một phương thức abstract vào Java interface, các lớp triển khai phải được cập nhật để **biên dịch lại từ source**. Với các module đã biên dịch riêng, sự khác biệt phiên bản có thể bộc lộ khi runtime gọi phương thức mới trên implementation cũ; thay đổi API vì vậy còn kéo theo quản lý tương thích và phát hành.

**Chi phí thật sự** không nằm ở ba dòng khai báo mới, mà ở các lớp, test, tài liệu, dependency và người bảo trì bị kéo vào thay đổi không thuộc nhu cầu của họ.

## 3. Nhận diện những nhóm chi phí bảo trì

Khi đánh giá một thay đổi của `AbstractFactory`, không nên chỉ đếm số dòng code mới. Có ít nhất sáu nhóm chi phí cần xem xét:

| Nhóm chi phí | Câu hỏi đánh giá | Dấu hiệu dễ quan sát |
| --- | --- | --- |
| **Thay đổi source** | Bao nhiêu factory/client/interface phải sửa? | Một tính năng của Windows làm thay đổi cả Web và Embedded |
| **Tương thích API** | Có thay đổi chữ ký mà plugin hoặc module cũ đang implement không? | Build bị hỏng, adapter cũ không triển khai phương thức mới |
| **Kiểm thử hồi quy** | Những họ nào phải chạy thêm test hoặc mock mới? | Test double của mọi họ phải thêm method dù không dùng |
| **Điều kiện đặc biệt** | Có bao nhiêu nhánh “không hỗ trợ”? | `null`, `UnsupportedOperationException`, `instanceof`, cờ tính năng |
| **Phối hợp phát hành** | Bao nhiêu nhóm/nhà cung cấp cần cập nhật đồng thời? | Một nhóm trì hoãn release vì nhóm khác chưa sửa factory |
| **Độ khó nhận thức** | Người sửa một họ có phải hiểu các họ không liên quan? | Interface lớn, nhiều phương thức chỉ một nền tảng sử dụng |

Một factory lớn không nhất thiết sai: nếu mọi biến thể đều phải cung cấp tất cả sản phẩm và có quy tắc tương thích chặt chẽ, hợp đồng chung vẫn tạo nhiều giá trị. **Vấn đề là mức độ đồng nhất thực tế**, không phải số phương thức tuyệt đối.

### Chi phí thay đổi lan theo kiểu nào?

~~~mermaid
flowchart TD
    A["Windows cần TrayIcon"] --> B{"Thêm vào GUIFactory chung?"}
    B -->|Có| C["Đổi interface chung"]
    C --> D["Sửa WebFactory / EmbeddedFactory"]
    C --> E["Sửa test doubles / adapters"]
    D --> F["Thêm null, no-op hoặc throw?"]
    E --> G["Kiểm thử và phát hành phối hợp"]
    B -->|Không, tách capability| H["Định nghĩa TrayIconFactory riêng"]
    H --> I["Windows cung cấp capability"]
    I --> J["Cập nhật nơi dùng tray"]
~~~

Sơ đồ chỉ mô tả các **khả năng xảy ra**, không khẳng định phương án tách capability luôn rẻ hơn. Nó cũng có chi phí: thêm abstraction, thêm cấu hình và phải định nghĩa nơi sử dụng khả năng tùy chọn.

## 4. Ước lượng chi phí thay đổi thay vì tranh luận cảm tính

Có thể dùng một bảng kiểm kê theo **thay đổi cụ thể**. Giả sử hệ thống có ba factory Windows/Web/Embedded; chỉ Windows yêu cầu sản phẩm TrayIcon.

| Hoạt động | Mở rộng `GUIFactory` chung | Tách `TrayIconFactory` riêng |
| --- | --- | --- |
| Interface mới hoặc sửa interface cũ | Sửa `GUIFactory` | Thêm interface khả năng nhỏ |
| Factory cần triển khai phương thức mới | Cả 3 factory | Factory liên quan đến Windows |
| Test double/adapter của interface chung | Có thể phải sửa tất cả | Thường giữ nguyên test double của `GUIFactory` |
| Client dùng chức năng tray | Phải kiểm tra có hỗ trợ hay không | Chỉ nhận `TrayIconFactory` ở luồng desktop |
| Rủi ro thay đổi API chung | Cao hơn | Thấp hơn đối với `GUIFactory` |
| Chi phí bổ sung abstraction | Thấp lúc đầu | Thêm một interface và đường cấp dependency |

Một mô hình ước lượng **đơn giản**, dùng để suy nghĩ chứ không phải công thức chuẩn:

\[
C_{\text{change}}
\approx C_{\text{interface}} + \sum_{i=1}^{N} C_{\text{factory},i}
+ C_{\text{tests}} + C_{\text{integration}} + C_{\text{coordination}}
\]

Trong đó:

- \(N\) là số factory **thực sự bị ảnh hưởng**, không mặc định bằng số họ trong hệ thống.
- \(C_{\text{factory},i}\) gồm sửa implementation, kiểm tra hành vi và xử lý tương thích của factory thứ \(i\).
- \(C_{\text{tests}}\) gồm test hợp đồng, test theo biến thể và cập nhật test doubles.
- \(C_{\text{integration}}\) gồm dây nối dependency, cấu hình, thử nghiệm tương thích và triển khai.
- \(C_{\text{coordination}}\) gồm việc thống nhất thay đổi giữa các nhóm và lịch phát hành.

**Ví dụ số hoàn toàn giả định** để minh họa cách tính công sức:

| Khoản việc | Mở rộng interface chung | Tách khả năng riêng |
| --- | ---: | ---: |
| Thiết kế, sửa hợp đồng | 1 giờ | 2 giờ |
| Viết implementation Windows | 3 giờ | 3 giờ |
| Sửa Web và Embedded | 2 giờ | 0 giờ |
| Điều chỉnh tests/doubles | 3 giờ | 1 giờ |
| Kết nối client và kiểm tra tích hợp | 2 giờ | 3 giờ |
| Phối hợp phát hành | 2 giờ | 1 giờ |
| **Tổng ước lượng minh họa** | **13 giờ** | **10 giờ** |

Các số **chỉ là giả định**, không phải dữ liệu thực nghiệm. Với một ứng dụng nhỏ, chi phí thêm interface có thể khiến phương án tách capability đắt hơn. Nhưng nếu có **nhiều họ** và thay đổi chỉ diễn ra ở một vài họ, phần chi phí sửa các implementation không liên quan có thể tăng liên tục theo thời gian.

Để đánh giá đúng trong dự án, hãy thay các con số trên bằng thông tin từ các lần thay đổi gần đây: số file phải sửa, số test thất bại, thời gian sửa build, thời gian review, số nhóm bị phụ thuộc và số lỗi hồi quy. Đừng suy ra “ít dòng code hơn” là “ít chi phí bảo trì hơn” khi chưa tính vòng đời của hợp đồng.

## 5. Giữ phần chung nhỏ, tách khả năng chỉ một số họ hỗ trợ

Với ví dụ GUI, giải pháp thường phù hợp là giữ `GUIFactory` cho những sản phẩm **mọi họ thực sự cung cấp**, và tách phần riêng thành một abstraction khác.

~~~java
interface GUIFactory {
    Button createButton();
    Checkbox createCheckbox();
}

interface TrayIconFactory {
    TrayIcon createTrayIcon();
}
~~~

`WindowsFactory` có thể implement cả hai interface:

~~~java
final class WindowsFactory implements GUIFactory, TrayIconFactory {
    @Override
    public Button createButton() {
        return new WindowsButton();
    }

    @Override
    public Checkbox createCheckbox() {
        return new WindowsCheckbox();
    }

    @Override
    public TrayIcon createTrayIcon() {
        return new WindowsTrayIcon();
    }
}
~~~

Trong khi đó, `WebFactory` chỉ implement `GUIFactory`:

~~~java
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
~~~

Kết quả:

- Luồng chung dùng `GUIFactory`, không bị ảnh hưởng bởi nhu cầu tray của Windows.
- Luồng riêng cho desktop nhận `TrayIconFactory`, có thể yêu cầu khả năng đó ngay trong chữ ký constructor.
- Web không phải cung cấp một `createTrayIcon()` giả hoặc ném ngoại lệ.
- Khi một họ desktop khác hỗ trợ tray, nó có thể implement `TrayIconFactory` mà không sửa `GUIFactory`.

Đây là cách áp dụng **Interface Segregation Principle**: client chỉ phụ thuộc các phương thức nó cần. Tuy nhiên, **tách hợp đồng không miễn phí**: cần thêm type, wiring và xác định nơi nào có thể yêu cầu capability. Nếu có hàng chục interface một phương thức mà không có nhu cầu tách độc lập, kiến trúc có thể khó hiểu hơn.

## 6. Ví dụ Java tự chứa: phần dùng chung và phần chỉ dành cho Windows

Ví dụ dưới đây mô phỏng `Button`, `Checkbox` và `TrayIcon` bằng chuỗi để tập trung vào **ranh giới dependency**. Toàn bộ mã có thể đặt trong một file `Demo.java` và biên dịch bằng Java 8 trở lên. Chỉ lớp `Demo` là `public`; các kiểu còn lại ở mức package-private.

~~~java
interface Button {
    String draw();
}

interface Checkbox {
    String draw();
}

interface TrayIcon {
    String description();
}

// Hợp đồng chung cho mọi họ GUI trong ứng dụng.
interface GUIFactory {
    Button createButton();
    Checkbox createCheckbox();
}

// Hợp đồng riêng khi một nền tảng có khay hệ thống.
interface TrayIconFactory {
    TrayIcon createTrayIcon();
}

final class WindowsButton implements Button {
    @Override
    public String draw() {
        return "Windows button";
    }
}

final class WindowsCheckbox implements Checkbox {
    @Override
    public String draw() {
        return "Windows checkbox";
    }
}

final class WindowsTrayIcon implements TrayIcon {
    @Override
    public String description() {
        return "Windows tray icon";
    }
}

final class WebButton implements Button {
    @Override
    public String draw() {
        return "Web button";
    }
}

final class WebCheckbox implements Checkbox {
    @Override
    public String draw() {
        return "Web checkbox";
    }
}

final class WindowsFactory implements GUIFactory, TrayIconFactory {
    @Override
    public Button createButton() {
        return new WindowsButton();
    }

    @Override
    public Checkbox createCheckbox() {
        return new WindowsCheckbox();
    }

    @Override
    public TrayIcon createTrayIcon() {
        return new WindowsTrayIcon();
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

// Client chung chỉ biết các sản phẩm mà mọi họ hỗ trợ.
final class Screen {
    private final GUIFactory factory;

    Screen(GUIFactory factory) {
        this.factory = factory;
    }

    void show() {
        System.out.println(factory.createButton().draw());
        System.out.println(factory.createCheckbox().draw());
    }
}

// Client chuyên biệt chỉ hoạt động khi có tray capability.
final class DesktopTrayService {
    private final TrayIconFactory trayFactory;

    DesktopTrayService(TrayIconFactory trayFactory) {
        this.trayFactory = trayFactory;
    }

    void start() {
        System.out.println(trayFactory.createTrayIcon().description());
    }
}

enum Platform {
    WINDOWS, WEB
}

public final class Demo {
    private static void showScreen(GUIFactory factory) {
        new Screen(factory).show();
    }

    public static void main(String[] args) {
        Platform platform = Platform.WINDOWS;

        switch (platform) {
            case WINDOWS:
                WindowsFactory windows = new WindowsFactory();
                showScreen(windows);
                new DesktopTrayService(windows).start();
                break;
            case WEB:
                showScreen(new WebFactory());
                break;
            default:
                throw new IllegalArgumentException("Unknown platform");
        }
    }
}
~~~

Với `Platform.WINDOWS`, đầu ra mô phỏng:

~~~text
Windows button
Windows checkbox
Windows tray icon
~~~

Với `Platform.WEB`, đầu ra:

~~~text
Web button
Web checkbox
~~~

Mã `Screen` dùng chung không cần `if (platform == WINDOWS)`, không phụ thuộc `TrayIconFactory` và không phải xử lý sản phẩm không tồn tại. Phần chọn nền tảng nằm ở `Demo.main()`, tức **composition root**; chỉ luồng Windows mới tạo `DesktopTrayService`.

Đổi lại, `Demo.main()` có thêm phần lắp ráp khác nhau theo nền tảng. Đó là **chi phí có chủ đích ở ranh giới khởi tạo**, giúp tránh đặt nhiều điều kiện đặc biệt trong từng màn hình. Nếu số nền tảng lớn, có thể tách composition root hoặc dùng DI/configuration; không cần vội tạo một lớp điều phối chung khổng lồ.

## 7. Nếu không thể tách interface ngay thì sao?

Trong dự án đã công bố API lâu dài, thay đổi hợp đồng cần tính đến phiên bản và khách hàng cũ. Một số hướng chuyển tiếp:

### 7.1. Adapter cho phiên bản cũ

Nếu có một `LegacyGUIFactory` đang được nhiều module sử dụng, có thể giữ giao diện cũ rồi tạo adapter sang phần hợp đồng mới. Chỉ đổi client đã sẵn sàng; chưa cần bắt mọi plugin cập nhật cùng lúc. Chi phí là có thêm lớp trung gian và cần test mapping giữa hai hợp đồng.

### 7.2. Interface mở rộng có chọn lọc

Nếu **mọi factory desktop** thực sự phải có tray icon, nhưng Web không có, có thể khai báo:

~~~java
interface GUIFactory {
    Button createButton();
    Checkbox createCheckbox();
}

interface DesktopGUIFactory extends GUIFactory {
    TrayIcon createTrayIcon();
}
~~~

Khi đó, client desktop nhận `DesktopGUIFactory`; client chung nhận `GUIFactory`. Cách kế thừa interface này phù hợp nếu **hệ phân loại “desktop” ổn định** và mọi thành viên đều thực hiện đầy đủ hợp đồng mở rộng. Nếu có desktop không hỗ trợ tray, nên dùng khả năng tách rời như `TrayIconFactory` ở phần trước, thay vì buộc mọi desktop giả hỗ trợ.

### 7.3. Khả năng tùy chọn hoặc tra cứu tính năng

Một số hệ thống plugin cần phát hiện khả năng tại runtime. Chúng có thể cung cấp cơ chế như `supportsFeature(...)` hoặc registry capability riêng. Cách này hữu ích khi các plugin được cài và nâng cấp độc lập, nhưng đưa thêm quy tắc đàm phán phiên bản, xử lý thiếu khả năng và kiểm thử tương thích. Không nên biến mỗi lời gọi nghiệp vụ thành chuỗi `if (supports...)` nếu có thể đưa lựa chọn đến ranh giới điều phối.

### 7.4. Giá trị mặc định và `default method`

Java cho phép interface có `default method`, có thể giảm thay đổi bắt buộc tại compile-time trong một số trường hợp. Tuy nhiên:

~~~java
interface GUIFactory {
    Button createButton();
    Checkbox createCheckbox();

    default TrayIcon createTrayIcon() {
        throw new UnsupportedOperationException("No tray support");
    }
}
~~~

Đây chỉ là cách **cung cấp implementation mặc định**; nó **không biến tray thành khả năng chung** và vẫn để lại nguy cơ lỗi ở runtime. Nên dùng mặc định khi hành vi mặc định thật sự hợp lệ và hữu ích cho tất cả những implementation chưa ghi đè, không dùng nó để che giấu khác biệt thiết kế.

## 8. Thay đổi không đồng đều: không phải trường hợp nào cũng cần tách factory

| Diễn biến | Chi phí với Abstract Factory hiện tại | Cách cân nhắc |
| --- | --- | --- |
| Windows đổi hình thức hiển thị `Button` nhưng interface `Button` không đổi | Chủ yếu sửa implementation Windows và test liên quan | **Giữ GUIFactory chung** |
| Thêm một họ mới, ví dụ macOS, cũng có `Button` và `Checkbox` | Thêm các sản phẩm và `MacFactory` | **Abstract Factory phù hợp** |
| Chỉ Windows cần `TrayIcon` | Thêm vào factory chung tạo nhiều phương thức giả | **Tách capability hoặc factory chuyên biệt** |
| Web thêm API animation cho `WebButton` mà các client chung không cần | Không nhất thiết tác động `GUIFactory` | Giữ API riêng hoặc abstraction nhỏ tại nơi dùng |
| Mọi họ đều cần thêm `TextField` | Phải cập nhật mọi concrete factory và contract test | **Mở rộng GUIFactory có thể hợp lý** |
| Một plugin cũ chưa nâng cấp lên giao thức mới | Cần cân nhắc tương thích và triển khai | Adapter, versioned contract hoặc capability negotiation |
| Hai họ ngày càng ít dùng chung loại sản phẩm | Hợp đồng chung mất ý nghĩa, nhiều nhánh xử lý ngoại lệ | Xem xét **chia lại ranh giới họ** |

Điểm quyết định là **độ ổn định của tập loại sản phẩm chung**. Một họ mới có thể dễ thêm vào Abstract Factory; nhưng một sản phẩm mới chỉ một họ sử dụng lại là dạng thay đổi khác hoàn toàn.

## 9. Kiểm thử cần thay đổi như thế nào khi khả năng bị phân tách?

Một bộ test hợp đồng cho phần chung nên chạy với **tất cả factory thực hiện `GUIFactory`**:

~~~java
// Đoạn minh họa sử dụng JUnit Jupiter 5;
// giả định các kiểu ở ví dụ Demo.java có thể truy cập từ test.
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class FactoryContractTest {
    private void assertCoreProducts(GUIFactory factory) {
        assertNotNull(factory.createButton());
        assertNotNull(factory.createCheckbox());
    }

    @Test
    void windowsHasCoreProducts() {
        assertCoreProducts(new WindowsFactory());
    }

    @Test
    void webHasCoreProducts() {
        assertCoreProducts(new WebFactory());
    }

    @Test
    void windowsHasTrayCapability() {
        TrayIconFactory trayFactory = new WindowsFactory();
        assertNotNull(trayFactory.createTrayIcon());
    }
}
~~~

Trong codebase thực, test hợp đồng còn nên kiểm tra **hành vi** (nút và ô chọn render đúng tiêu chí của họ tương ứng), tài nguyên và quy tắc tương thích. Các assertion `assertNotNull` ở trên chỉ minh họa cách **phân chia phạm vi test**:

- Test **chung** áp dụng cho mọi `GUIFactory`.
- Test **tray** chỉ áp dụng cho các implementation của `TrayIconFactory`.
- Khi có một capability mới dành riêng cho Web, thêm test capability đó mà không buộc Windows/Embedded giả triển khai nó.

Nếu có nhiều concrete factory, có thể dùng JUnit parameterized test hoặc test contract kế thừa để tránh sao chép. Dù tổ chức thế nào, một factory được thêm vào hệ thống vẫn phải được **đăng ký và chạy test hợp đồng chung**; không thể chỉ dựa vào việc lớp implement interface để suy ra sản phẩm đúng cùng họ.

## 10. Quy trình đánh giá chi phí bảo trì trong một thay đổi thật

Khi nhận yêu cầu bổ sung tính năng cho một biến thể, có thể làm theo quy trình sau:

1. **Vẽ ma trận capability:** liệt kê các loại sản phẩm/khả năng theo từng họ; ghi rõ bắt buộc, tùy chọn hoặc không áp dụng.
2. **Đánh dấu phạm vi tính năng mới:** thay đổi thực sự cần bao nhiêu họ; đây là sản phẩm mới hay chỉ là thay đổi bên trong một implementation cũ?
3. **Truy vết hợp đồng công khai:** liệt kê các interface, concrete factory, adapter, plugin, dependency injection binding và client bị tác động bởi từng phương án.
4. **Đếm số nhánh ngoại lệ:** tìm những chỗ sẽ phải trả `null`, ném ngoại lệ, ghi đè mặc định hoặc kiểm tra platform chỉ để đáp ứng interface chung.
5. **Ước lượng công sức kiểm thử/phát hành:** test chung, test riêng, mock, khả năng tương thích với module được deploy độc lập và nhóm sở hữu các module đó.
6. **So sánh ít nhất hai phương án:** mở rộng interface chung với tách capability; nếu chỉ có một product type, cân nhắc factory đơn giản hoặc DI.
7. **Ghi rõ giả định và rủi ro:** chẳng hạn “tray sẽ chỉ tồn tại ở desktop”, “Web dự kiến bổ sung notification khác tray”, “module Embedded mỗi quý mới được release”.
8. **Chọn phương án có chi phí thay đổi tổng thể hợp lý:** cân bằng công sức hiện tại với khả năng mở rộng trong tương lai; không tối ưu theo số lớp ít nhất.

Nên theo dõi một vài chỉ số **qua nhiều lần thay đổi**, thay vì dùng một phép đo đơn lẻ:

| Chỉ số | Cách thu thập | Ý nghĩa |
| --- | --- | --- |
| Số concrete factory phải sửa cho mỗi tính năng | So sánh diff của những change request tương tự | Mức lan truyền thay đổi |
| Tỷ lệ phương thức factory không được họ hỗ trợ | Đếm method trả `null`/throw/no-op | Dấu hiệu interface mất tính đồng nhất |
| Số test doubles cần sửa theo interface | Diff trong thư mục test hoặc thống kê build | Chi phí duy trì hợp đồng chung |
| Số nhánh theo platform/provider trong client | Code review, tìm kiếm có ngữ cảnh | Mức rò rỉ lựa chọn biến thể |
| Số lần triển khai phối hợp bắt buộc | Thông tin release/module dependency | Rủi ro đồng bộ giữa các nhóm |
| Lỗi hồi quy do sai họ sản phẩm | Test failures/issue tracking | Chất lượng bảo toàn quy tắc tương thích |

Những số liệu này là **công cụ hỗ trợ quyết định**, không phải ngưỡng quy định cho tất cả dự án. Một dự án có ba nhà cung cấp và release tập trung sẽ khác nhiều với hệ sinh thái hàng chục plugin được nâng cấp độc lập.

## 11. Các đánh đổi cần nói rõ khi chọn kiến trúc

**Giữ một Abstract Factory lớn** có ưu điểm là client nhìn thấy một điểm tạo sản phẩm thống nhất và các nhóm có thể đọc cùng một hợp đồng. Nó hữu ích khi tất cả họ cùng hỗ trợ đầy đủ sản phẩm và có yêu cầu tương thích mạnh. Chi phí tăng khi nhiều phương thức chỉ dành cho một vài họ.

**Tách nhiều factory theo khả năng** giảm việc buộc các họ không liên quan phải cập nhật. Đổi lại, số interface và cấu hình tăng; đội ngũ phải quản lý mối quan hệ giữa capability, cách cung cấp dependency và vị trí cần ghép chúng.

**Dùng một factory đơn giản hoặc DI** có thể tiết kiệm công sức nếu ứng dụng không thật sự có nhiều loại sản phẩm phải đi cùng nhau. Khi những đối tượng chỉ liên quan lỏng lẻo, ghép chúng vào một Abstract Factory tạo ràng buộc nhân tạo.

**Chấp nhận một lớp chọn biến thể tập trung** thường vẫn hợp lý. Tránh lý tưởng “không có `if` ở đâu cả”: mục tiêu là giữ mã nghiệp vụ tránh phải biết mọi biến thể, còn ranh giới cấu hình có quyền quyết định dùng concrete factory nào.

Khi họ sản phẩm phát triển quá lệch, có lúc **cần thay đổi chính cách phân chia họ**. Ví dụ “Desktop” không phải một họ đồng nhất nếu một số desktop không có system tray; lúc ấy khả năng tray có thể trở thành một dependency độc lập.

## 12. Bài tập phân tích

### Bài tập A — Một tính năng chỉ tồn tại ở một họ

`GUIFactory` hiện có `createButton()` và `createCheckbox()` cho Windows/Web. Nhóm Web cần thêm `createBrowserNotification()` nhưng Windows không hỗ trợ khái niệm này.

Hãy chỉ ra:

1. Nếu thêm vào `GUIFactory`, lớp nào phải thay đổi dù không sử dụng sản phẩm mới?
2. Việc trả `null` trong `WindowsFactory` sẽ ảnh hưởng gì đến hợp đồng?
3. Một `BrowserNotificationFactory` riêng có lợi ích gì, và chi phí cấu hình mới nằm ở đâu?

### Bài tập B — Tính năng mới cần cho tất cả họ

Cả Windows, Web và Embedded đều phải hỗ trợ một loại `TextField` chung. Phân tích vì sao lúc này thêm `createTextField()` vào `GUIFactory` có thể đúng, dù cả ba concrete factory phải sửa. Hãy liệt kê các test cần bổ sung để kiểm tra sản phẩm từ mọi họ.

### Bài tập C — Mô hình ước lượng

Một hệ thống có sáu concrete factory. Một thay đổi chỉ cần ở hai họ. Giả sử mỗi factory phải sửa tốn trung bình 1,5 giờ và hai phương án có chi phí cố định (thiết kế + integration) lần lượt là 2 giờ cho interface chung và 7 giờ cho capability riêng. **Chỉ tính các khoản này**:

- Phương án sửa cả sáu factory: `2 + 6 × 1,5 = 11 giờ`.
- Phương án sửa hai factory liên quan: `7 + 2 × 1,5 = 10 giờ`.

Theo các giả định đó, phương án hai thấp hơn 1 giờ. Hãy bổ sung chi phí test, phát hành và rủi ro tương thích để xem lựa chọn có thay đổi không. Bài toán không có “đáp án chung” ngoài việc dùng dữ liệu thực tế.

### Bài tập D — Dấu hiệu tách quá mức

Một nhóm tạo bảy interface factory khác nhau, mỗi interface có một phương thức, dù tất cả họ đều hỗ trợ đầy đủ các sản phẩm và luôn được tạo/triển khai cùng nhau. Hãy giải thích chi phí mới của việc tách và khi nào nên cân nhắc gom lại thành một hợp đồng tạo họ sản phẩm nhất quán.

## 13. Checklist quyết định cho kiến trúc sư và người bảo trì

- [ ] Đã phân biệt **họ sản phẩm** và **loại sản phẩm** khi nói về mở rộng.
- [ ] Đã có ma trận các khả năng chung và riêng theo từng họ.
- [ ] Đã xác định nhu cầu mới thực sự liên quan đến tất cả họ hay chỉ một tập con.
- [ ] Không thêm một phương thức vào interface chung nếu phần lớn implementation chỉ có thể trả `null`, throw hoặc no-op không có ý nghĩa.
- [ ] Đã tính chi phí sửa source, tương thích API, test, mock, release và phối hợp nhóm.
- [ ] Đã so sánh phương án giữ interface chung với tách capability / interface mở rộng / adapter phù hợp.
- [ ] Các client chung chỉ phụ thuộc vào sản phẩm mà mọi họ cam kết cung cấp.
- [ ] Các client chuyên biệt nhận dependency mô tả đúng capability chúng cần.
- [ ] Mỗi factory có test hợp đồng chung; capability riêng có test riêng.
- [ ] Đã ghi rõ giả định về nhịp phát hành, khả năng tương thích và nhu cầu tương lai.

**Điểm cốt lõi:** Abstract Factory tiết kiệm chi phí bảo trì khi **hợp đồng về các loại sản phẩm chung đủ ổn định** và ứng dụng cần chuyển đổi giữa các họ tương thích. Khi các họ phát triển không đồng đều, hãy đánh giá **chi phí thay đổi lan sang những implementation không liên quan**. Giữ phần chung đúng nghĩa chung, tách khả năng riêng khi có lý do và đo phạm vi tác động của từng lựa chọn trước khi mở rộng thiết kế.

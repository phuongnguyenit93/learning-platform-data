# Đánh giá lợi ích về tính nhất quán, khả năng thay thế và cô lập phụ thuộc

**Abstract Factory** là mẫu thiết kế khởi tạo (creational design pattern) cung cấp một hợp đồng để tạo **các nhóm đối tượng liên quan** mà mã sử dụng chúng không cần gọi trực tiếp các lớp hiện thực cụ thể. Trong chủ đề *Chi phí và đánh đổi*, điều cần đánh giá không chỉ là khả năng tạo đối tượng, mà là liệu cơ chế này có giúp hệ thống **nhất quán**, **dễ thay thế** và **ít phụ thuộc vào chi tiết triển khai** đến mức xứng đáng với số lớp và interface phát sinh hay không.

Ba lợi ích này liên quan chặt chẽ nhưng không đồng nghĩa:

| Lợi ích | Câu hỏi cần trả lời | Kết quả kỳ vọng |
| --- | --- | --- |
| **Tính nhất quán** (consistency) | Các đối tượng cùng hoạt động có được tạo theo một quy tắc thống nhất? | Hạn chế trộn các sản phẩm thuộc những họ không tương thích |
| **Khả năng thay thế** (replaceability) | Có thể chuyển từ họ sản phẩm A sang B mà ít sửa mã nghiệp vụ không? | Đổi factory được cung cấp cho client thay vì sửa hàng loạt chỗ khởi tạo |
| **Cô lập phụ thuộc** (dependency isolation) | Mã nghiệp vụ có phải biết các lớp, thư viện hoặc nền tảng cụ thể không? | Client phụ thuộc vào interface; mã chọn và lắp ghép hiện thực tập trung ở ranh giới hệ thống |

Đây là những **lợi ích có điều kiện**, không phải bảo đảm tự động của mọi chương trình có tên lớp kết thúc bằng `Factory`.

## 1. Bối cảnh: chọn một họ sản phẩm cho toàn bộ màn hình

Xét một ứng dụng cần hiển thị **Button** (nút bấm) và **Checkbox** (ô chọn) theo giao diện Windows hoặc macOS:

| Họ sản phẩm | Loại Button | Loại Checkbox |
| --- | --- | --- |
| Windows | WindowsButton | WindowsCheckbox |
| macOS | MacButton | MacCheckbox |

**Button** và **Checkbox** là hai *loại sản phẩm* (abstract products). Các lớp WindowsButton, MacButton, WindowsCheckbox và MacCheckbox là *biến thể cụ thể* (concrete products). Mỗi hàng trong bảng là một *họ sản phẩm* (product family).

Nếu màn hình tự tạo từng thành phần tại nhiều vị trí, các quyết định chọn biến thể có thể bị phân tán:

~~~java
// Ví dụ minh họa cách ghép không nhất quán.
Button button = new WindowsButton();
Checkbox checkbox = new MacCheckbox();
~~~

Đoạn mã có thể hợp lệ về kiểu dữ liệu nhưng vi phạm quy ước giao diện của ứng dụng: nút bấm dùng phong cách Windows, ô chọn dùng phong cách macOS. Trong một hệ thống khác, việc trộn họ còn có thể gây lỗi cấu hình hoặc giao thức thực sự. **Abstract Factory giải quyết vấn đề ở thời điểm tạo một bộ sản phẩm**, bằng cách để một concrete factory chịu trách nhiệm cung cấp các thành viên của cùng một họ.

## 2. Lợi ích thứ nhất: tính nhất quán giữa các sản phẩm

### 2.1. Cơ chế tạo ra lợi ích

Một abstract factory khai báo các thao tác tạo những loại sản phẩm mà client cần:

~~~java
interface GUIFactory {
    Button createButton();
    Checkbox createCheckbox();
}
~~~

Một concrete factory cho Windows triển khai **cả hai phương thức** để trả về biến thể Windows; concrete factory cho macOS làm tương tự cho macOS. Client nhận **một factory** rồi dùng chính factory đó để tạo các sản phẩm liên quan.

Nhờ vậy, quy tắc **“một màn hình sử dụng một họ giao diện”** được đặt ở một vị trí thiết kế rõ ràng:

- Quyết định chọn họ diễn ra khi cung cấp `GUIFactory` cho màn hình.
- Các vị trí tạo Button và Checkbox cùng dựa trên factory đã chọn.
- Khi cần sửa quy tắc khởi tạo của một họ, lập trình viên có một nơi chịu trách nhiệm rõ ràng để kiểm tra.

Điều này giảm nguy cơ nhầm biến thể khi một màn hình có nhiều thành phần hoặc khi cách chọn nền tảng thay đổi.

### 2.2. Phạm vi bảo đảm: nhất quán bằng quy ước triển khai

Cần phân biệt **thiết kế khuyến khích tính nhất quán** với **chứng minh tính nhất quán bằng hệ thống kiểu**. Chữ ký `Button createButton()` không ngăn một lập trình viên viết sai:

~~~java
// Sai về quy ước họ sản phẩm nhưng vẫn có thể biên dịch.
final class BrokenWindowsFactory implements GUIFactory {
    public Button createButton() {
        return new WindowsButton();
    }

    public Checkbox createCheckbox() {
        return new MacCheckbox();
    }
}
~~~

Để lợi ích thực sự tồn tại, cần:

1. Mỗi concrete factory trả về đúng bộ biến thể theo quy tắc của họ.
2. Client không bỏ qua factory để trực tiếp khởi tạo hoặc trộn sản phẩm từ nhiều factory.
3. Có kiểm thử hoặc kiểm tra cấu hình xác nhận từng factory tạo các thành viên tương thích.

**Cách đánh giá:** kiểm tra các đường đi tạo đối tượng. Nếu trước đây nhiều nơi tự lựa chọn lớp cụ thể và nay chỉ còn một đầu mối chọn họ, khả năng duy trì tính nhất quán đã tăng. Nếu client vẫn dùng `new WindowsButton()` rải rác, lợi ích chưa đạt được dù đã tồn tại `GUIFactory`.

## 3. Lợi ích thứ hai: thay thế cả họ sản phẩm

### 3.1. Thay đổi quyết định cấu hình thay vì thay đổi mã nghiệp vụ

Một client chỉ cần hợp đồng `Button`, `Checkbox` và `GUIFactory` sẽ không phụ thuộc vào việc họ đang dùng là Windows hay macOS. Khi chuyển nền tảng, ứng dụng có thể cung cấp một concrete factory khác tại nơi lắp ghép các thành phần (*composition root*).

~~~text
SettingsScreen(GUIFactory)
    + WindowsFactory  -> WindowsButton + WindowsCheckbox
    + MacFactory      -> MacButton     + MacCheckbox
~~~

Mã vẽ màn hình giữ nguyên khi thay cả họ. Việc chọn factory có thể dựa trên cấu hình, nền tảng, tham số khởi chạy hoặc một cơ chế dependency injection.

### 3.2. “Thay thế” có nghĩa chính xác là gì?

Khả năng thay thế được hiểu là **thay một tập các hiện thực có cùng hợp đồng quan sát được từ phía client**. Nó không có nghĩa mọi tính năng đặc thù của các nền tảng đều giống nhau, cũng không đồng nghĩa có thể đổi các đối tượng đang hoạt động ngay lập tức mà không xử lý trạng thái.

Ví dụ, nếu `SettingsScreen` lưu Button và Checkbox ngay trong constructor, muốn chuyển họ khi ứng dụng đang chạy có thể cần tạo lại màn hình hoặc thiết kế quy trình cập nhật trạng thái. Abstract Factory **không tự triển khai cơ chế chuyển nóng** (*hot switching*).

Khi một họ mới xuất hiện, chẳng hạn Linux, đội phát triển thường phải thêm `LinuxButton`, `LinuxCheckbox` và `LinuxFactory`. Client đã dùng các interface có thể giữ nguyên; nhưng **phần chọn factory, đóng gói và kiểm thử họ mới** vẫn phải được cập nhật.

**Cách đánh giá:** thử thêm một họ mới và đếm các vị trí phải chỉnh sửa. Nếu những thay đổi chủ yếu nằm ở hiện thực của họ và ở bước cấu hình, còn mã nghiệp vụ giữ nguyên, mục tiêu thay thế đã đạt được. Nếu mọi màn hình đều phải thêm `if (platform == ...)`, việc trừu tượng hóa chưa hiệu quả.

## 4. Lợi ích thứ ba: cô lập phụ thuộc vào chi tiết triển khai

### 4.1. Hướng phụ thuộc được thiết kế có chủ đích

Không dùng factory, một màn hình có thể trực tiếp nhập các lớp theo nền tảng và tự khởi tạo chúng. Khi dùng Abstract Factory, client có thể chỉ biết các interface:

~~~mermaid
flowchart LR
    Composition["Composition root: chọn họ"] --> WindowsFactory["WindowsFactory"]
    Composition --> MacFactory["MacFactory"]
    Composition --> Client["SettingsScreen"]
    Client --> Contracts["GUIFactory, Button, Checkbox"]
    WindowsFactory -. "implements" .-> Contracts
    MacFactory -. "implements" .-> Contracts
    WindowsFactory --> WinProducts["WindowsButton, WindowsCheckbox"]
    MacFactory --> MacProducts["MacButton, MacCheckbox"]
    WinProducts -. "implements" .-> Contracts
    MacProducts -. "implements" .-> Contracts
~~~

Đây là một ứng dụng của **Dependency Inversion Principle** (nguyên tắc đảo ngược phụ thuộc): mã cấp cao sử dụng hợp đồng trừu tượng, thay vì biết các lớp khởi tạo cụ thể. Hệ quả có ích:

- **Giảm thay đổi lan truyền:** đổi thư viện hoặc hiện thực giao diện có thể được xử lý trong concrete products và concrete factory tương ứng.
- **Dễ kiểm thử độc lập:** có thể đưa một factory giả (*fake/stub*) vào client, tránh cần giao diện hoặc dịch vụ thật.
- **Rõ ranh giới tích hợp:** mã lựa chọn nhà cung cấp/nền tảng và mã nghiệp vụ được đặt ở những vị trí có trách nhiệm khác nhau.

Tuy nhiên, **phụ thuộc vẫn tồn tại ở nơi lắp ghép và ở thời điểm chạy**. Ứng dụng vẫn phải có các lớp, thư viện và cấu hình cần thiết để tạo WindowsButton hoặc MacButton. Abstract Factory **không tự loại bỏ** dependency, chi phí khởi tạo hay yêu cầu đóng gói; nó chỉ giúp client không phải biết trực tiếp các chi tiết đó.

### 4.2. Cô lập phụ thuộc chỉ hiệu quả khi interface không rò rỉ chi tiết

Giả sử interface `Button` trả về `WindowsNativeHandle`. Dù client không gọi `new WindowsButton()`, mã sử dụng interface vẫn phải biết kiểu dữ liệu của Windows. Khi đó việc cô lập phụ thuộc bị suy giảm.

Một hợp đồng hợp lý nên biểu đạt nhu cầu chung của client, chẳng hạn `render()`, `onClick()` hoặc một mô hình dữ liệu trung lập. Nếu API giữa các nền tảng khác nhau quá sâu, hệ thống có thể cần **Adapter** hoặc thiết kế lại abstraction; thêm factory đơn thuần chưa giải quyết được.

**Cách đánh giá:** kiểm tra import, kiểu tham số, kiểu trả về và module dependency của client. Những phần này có còn phụ thuộc trực tiếp vào SDK hoặc lớp cụ thể không? Có thể chạy kiểm thử client với factory giả mà không tải thư viện nền tảng không? Đây là bằng chứng thực tế rõ hơn việc chỉ đếm số interface.

## 5. Ví dụ Java hoàn chỉnh: ba lợi ích trong một thiết kế

Chương trình sau dùng một tệp `Main.java`. Để dễ chạy độc lập, `render()` trả về chuỗi thay vì gọi API cửa sổ thật. Mã minh họa đúng ba điểm: **một factory tạo trọn một họ**, **client không đổi khi thay factory**, và **client có thể kiểm thử với fake factory**.

~~~java
public class Main {
    // Hợp đồng của hai loại sản phẩm.
    interface Button {
        String render();
    }

    interface Checkbox {
        String render();
    }

    // Abstract Factory: tạo toàn bộ các loại sản phẩm liên quan.
    interface GUIFactory {
        Button createButton();
        Checkbox createCheckbox();
    }

    // Các biến thể của họ Windows.
    static final class WindowsButton implements Button {
        public String render() {
            return "[Windows] Button";
        }
    }

    static final class WindowsCheckbox implements Checkbox {
        public String render() {
            return "[Windows] Checkbox";
        }
    }

    // Các biến thể của họ macOS.
    static final class MacButton implements Button {
        public String render() {
            return "[macOS] Button";
        }
    }

    static final class MacCheckbox implements Checkbox {
        public String render() {
            return "[macOS] Checkbox";
        }
    }

    // Mỗi concrete factory cung cấp một họ nhất quán.
    static final class WindowsFactory implements GUIFactory {
        public Button createButton() {
            return new WindowsButton();
        }

        public Checkbox createCheckbox() {
            return new WindowsCheckbox();
        }
    }

    static final class MacFactory implements GUIFactory {
        public Button createButton() {
            return new MacButton();
        }

        public Checkbox createCheckbox() {
            return new MacCheckbox();
        }
    }

    // Client chỉ dùng hợp đồng; không biết các lớp Windows/Mac.
    static final class SettingsScreen {
        private final Button button;
        private final Checkbox checkbox;

        SettingsScreen(GUIFactory factory) {
            this.button = factory.createButton();
            this.checkbox = factory.createCheckbox();
        }

        String render() {
            return button.render() + " | " + checkbox.render();
        }
    }

    // Fake factory dùng được mà không cần các biến thể thật.
    static final class FakeFactory implements GUIFactory {
        public Button createButton() {
            return () -> "[Test] Button";
        }

        public Checkbox createCheckbox() {
            return () -> "[Test] Checkbox";
        }
    }

    public static void main(String[] args) {
        // Composition root: một quyết định chọn cả họ.
        GUIFactory factory = args.length > 0
                && "mac".equalsIgnoreCase(args[0])
                ? new MacFactory()
                : new WindowsFactory();

        System.out.println(new SettingsScreen(factory).render());
        System.out.println(new SettingsScreen(new FakeFactory()).render());
    }
}
~~~

Biên dịch và chạy ở thư mục chứa `Main.java`:

~~~text
javac Main.java
java Main
[Windows] Button | [Windows] Checkbox
[Test] Button | [Test] Checkbox

java Main mac
[macOS] Button | [macOS] Checkbox
[Test] Button | [Test] Checkbox
~~~

Liên hệ kết quả với ba lợi ích:

1. **Nhất quán:** `WindowsFactory` luôn tạo cả hai biến thể Windows; `MacFactory` luôn tạo cả hai biến thể macOS. Một instance của `SettingsScreen` lấy các thành phần từ đúng factory được truyền vào.
2. **Thay thế:** hai lần chạy sử dụng cùng mã `SettingsScreen`; chỉ lựa chọn `GUIFactory` ở `main()` thay đổi.
3. **Cô lập phụ thuộc:** `SettingsScreen` khai báo trường kiểu `Button`, `Checkbox` và nhận `GUIFactory`; `FakeFactory` chứng minh có thể thay nguồn tạo đối tượng mà không sửa client.

Trong phần mềm thật, **kiểm thử tự động** cần thêm assertion về hành vi và quy tắc cùng họ. Việc ví dụ in chuỗi đúng chỉ minh họa cấu trúc phụ thuộc, chưa chứng minh được toàn bộ chất lượng hay tương thích của một thư viện giao diện.

## 6. Chi phí và những đánh đổi của Abstract Factory

Lợi ích tăng lên nhờ có các hợp đồng và ranh giới rõ ràng. Chính các thành phần này cũng làm tăng chi phí thiết kế, phát triển và bảo trì.

| Chi phí / đánh đổi | Nguyên nhân | Tác động cần tính đến |
| --- | --- | --- |
| **Thêm lớp và interface** | Mỗi loại cần hợp đồng; mỗi họ cần các hiện thực và factory tương ứng | Tốn công đặt tên, tổ chức tệp, đọc và điều hướng mã |
| **Khó bổ sung loại sản phẩm mới** | Abstract factory có thêm phương thức tạo mới | Mọi concrete factory phải cập nhật để đáp ứng hợp đồng mới |
| **Dễ có abstraction quá rộng** | Tập hợp quá nhiều loại sản phẩm không liên quan vào một factory | Client bị phụ thuộc vào interface lớn, khó triển khai và kiểm thử |
| **Chi phí quản lý biến thể** | Mỗi họ có thể có cách cài đặt riêng và ràng buộc tương thích khác nhau | Cần kiểm thử từng họ và các trường hợp cấu hình hợp lệ |
| **Khó biểu đạt khác biệt đặc thù** | Interface chung chỉ mô tả hành vi mà các họ cùng hỗ trợ | Có thể phải dùng Adapter, tách interface, hoặc chấp nhận thiếu chức năng đặc thù |
| **Gia tăng cấu hình lúc khởi tạo** | Phải chọn và cung cấp factory tại composition root | Cần xác định vòng đời, phạm vi sử dụng và xử lý cấu hình sai |

### 6.1. Khi thêm họ mới và khi thêm loại mới

Gọi `P` là số **loại sản phẩm** mà mỗi họ phải hỗ trợ, `F` là số **họ sản phẩm**. Trong thiết kế đơn giản với một lớp concrete product cho mỗi cặp (loại, họ), có khoảng **`P × F` lớp sản phẩm cụ thể**, thêm `P` interface sản phẩm, một abstract factory và `F` concrete factory. Đây chỉ là mô hình ước lượng; số lớp thực tế có thể khác do tái sử dụng hoặc gom triển khai.

Ví dụ với 3 loại và 4 họ, có thể phải duy trì 12 lớp sản phẩm cụ thể:

- **Thêm họ thứ năm:** thêm tối đa 3 sản phẩm cụ thể và 1 concrete factory (nếu các họ có cấu trúc giống nhau); các interface cũ không nhất thiết thay đổi.
- **Thêm loại thứ tư:** thêm hợp đồng loại mới, phương thức tạo mới và cập nhật **cả 4 concrete factory hiện có**, cùng những hiện thực cụ thể tương ứng.

Vì vậy, Abstract Factory thường phù hợp khi **các loại sản phẩm tương đối ổn định** nhưng hệ thống có nhu cầu **thêm hoặc đổi họ**. Khi các loại thay đổi liên tục còn số họ ít, chi phí sửa interface factory và toàn bộ hiện thực có thể lớn hơn lợi ích.

### 6.2. Không tự mặc định có lợi về hiệu năng

Gọi một phương thức factory thường không phải chi phí đáng kể so với kết nối mạng, truy vấn dữ liệu hoặc dựng UI, nhưng không có nghĩa mọi triển khai đều tương đương hiệu năng. Factory có thể thực hiện tra cứu cấu hình, cấp phát, quản lý tài nguyên hoặc khởi tạo kết nối đắt đỏ. Chỉ kết luận về hiệu năng sau khi đo **đường đi thật** của ứng dụng, đặc biệt khi việc tạo đối tượng diễn ra trong vòng lặp nóng.

### 6.3. Những tình huống dễ áp dụng sai

- **Chỉ có một loại sản phẩm:** nếu chỉ cần tạo một `Logger` với vài biến thể, một factory đơn giản, Factory Method hoặc dependency injection trực tiếp thường dễ hiểu hơn.
- **Không tồn tại yêu cầu nhất quán theo nhóm:** nếu Button và Checkbox được lựa chọn hoàn toàn độc lập mà không có quy tắc phối hợp, ép chúng vào cùng factory có thể tạo ràng buộc nhân tạo.
- **Các họ không chia sẻ hợp đồng hợp lý:** ví dụ hai nhà cung cấp có mô hình giao dịch hoặc giới hạn chức năng quá khác nhau. Che sự khác biệt bằng interface chung có thể dẫn đến phương thức không hỗ trợ hoặc lỗi ở thời điểm chạy.
- **Client vẫn gọi sản phẩm cụ thể ở khắp nơi:** có thêm factory nhưng mã nghiệp vụ tiếp tục `new` các lớp nền tảng làm mất phần lớn lợi ích cô lập và chọn họ tập trung.

## 7. Đánh giá lợi ích theo bằng chứng trong dự án

Để đánh giá thực tế, không nhất thiết cần một điểm số tuyệt đối. Nên bắt đầu từ **một thay đổi điển hình mà dự án thật sự dự kiến thực hiện** rồi xem thiết kế phản ứng thế nào.

| Tiêu chí | Cách kiểm tra | Dấu hiệu tốt | Dấu hiệu cần xem lại |
| --- | --- | --- | --- |
| **Nhất quán** | Rà soát cách một màn hình/dịch vụ lấy các sản phẩm liên quan | Một factory tạo trọn họ; quy tắc tương thích có kiểm thử | Các sản phẩm được chọn độc lập, có đường đi trộn họ |
| **Khả năng thay thế** | Thử thêm một họ giả định hoặc đổi họ bằng cấu hình | Chủ yếu thêm concrete products, concrete factory, cấu hình | Phải sửa nhiều client và rải thêm điều kiện chọn nền tảng |
| **Cô lập phụ thuộc** | Kiểm tra import và chữ ký các interface trong module nghiệp vụ | Client chỉ tham chiếu hợp đồng; dùng fake factory dễ dàng | Interface lộ kiểu SDK; client biết tên lớp cụ thể |
| **Chi phí mở rộng loại** | Giả lập thêm một loại sản phẩm vào bộ | Số loại ổn định, việc cập nhật các factory chấp nhận được | Thường xuyên phải mở rộng factory và cập nhật nhiều họ |
| **Mức độ phức tạp** | So sánh với factory đơn giản/DI trực tiếp | Mỗi abstraction có trách nhiệm dễ giải thích | Nhiều lớp chuyển tiếp chỉ để tạo một đối tượng đơn lẻ |

**Ví dụ đánh giá A — ứng dụng UI đa nền tảng:** ứng dụng luôn cần tạo Button, Checkbox và Menu theo cùng phong cách; dự kiến thêm nền tảng mới. Abstract Factory có khả năng mang lại giá trị rõ ràng: một factory chọn nguyên bộ thành phần, client ít phụ thuộc nền tảng và việc thêm họ mới tương đối gọn. Chi phí phù hợp khi số loại thành phần không biến động quá thường xuyên.

**Ví dụ đánh giá B — dịch vụ chỉ cần một bộ gửi thông báo:** hệ thống chỉ chọn một hiện thực `NotificationSender` (ví dụ email hoặc SMS) tại khởi động, không cần tạo thêm các sản phẩm có liên hệ với nó. Lợi ích chọn bộ sản phẩm nhất quán hầu như không có; inject trực tiếp `NotificationSender` hoặc dùng factory đơn giản thường ít phức tạp hơn.

**Ví dụ đánh giá C — tích hợp nhiều cloud provider:** mỗi nhà cung cấp có storage client và queue client. Một factory theo nhà cung cấp *có thể* giúp tạo bộ client đồng nhất, nhưng cần làm rõ sự khác nhau về độ tin cậy, giao dịch, quyền truy cập và cách xử lý lỗi. Nếu interface chung che giấu những khác biệt ảnh hưởng nghiệp vụ, lợi ích cô lập chỉ mang tính hình thức. Có thể cần Adapter và các hợp đồng được thiết kế cẩn thận trước khi dùng Abstract Factory.

### Một quy trình quyết định ngắn

1. **Liệt kê các loại sản phẩm** mà cùng một client cần phối hợp; ghi rõ quy tắc tương thích giữa chúng.
2. **Liệt kê các họ** dự kiến tồn tại và mức độ thường xuyên phải chuyển hoặc bổ sung họ.
3. **Vẽ luồng khởi tạo hiện tại** để xem lựa chọn biến thể có bị rải ở nhiều chỗ hay không.
4. **Phác thảo abstract product và abstract factory** với ít phương thức nhất đáp ứng nhu cầu client.
5. **Thử hai thay đổi:** thêm một họ và thêm một loại; so sánh số nơi phải sửa, mức độ phụ thuộc và công kiểm thử.
6. **Chọn thiết kế đơn giản nhất đáp ứng ràng buộc thực tế.** Nếu không có nhu cầu tạo đồng bộ nhiều loại sản phẩm theo từng họ, Abstract Factory chưa chắc là lựa chọn tốt.

## 8. Quan hệ với Dependency Injection, Factory Method và Adapter

Ba kỹ thuật này có thể xuất hiện cùng Abstract Factory nhưng giải quyết các khía cạnh khác nhau:

| Kỹ thuật | Trọng tâm | Quan hệ với Abstract Factory |
| --- | --- | --- |
| **Dependency Injection (DI)** | Cung cấp phụ thuộc từ bên ngoài cho đối tượng | Có thể inject một `GUIFactory` vào client; DI không tự quy định cấu trúc họ sản phẩm |
| **Factory Method** | Đặt việc tạo một loại sản phẩm sau một phương thức có thể được thay đổi bởi lớp con hoặc hiện thực | Thường phù hợp hơn khi bài toán chủ yếu xoay quanh một loại sản phẩm |
| **Adapter** | Chuyển giao diện của một hiện thực hiện có thành hợp đồng client cần | Có thể bọc SDK nền tảng thành các concrete products, giúp abstract product không lộ kiểu đặc thù |

Abstract Factory tập trung vào **việc tạo bộ sản phẩm liên quan**, DI tập trung vào **cách cung cấp phụ thuộc**, còn Adapter tập trung vào **cách tương thích giao diện**. Kết hợp đúng vai trò của chúng có thể giảm phụ thuộc hơn so với dùng một mẫu đơn lẻ.

## 9. Kết luận thực hành

Khi xem xét Abstract Factory, hãy ghi nhớ **ba lợi ích tương ứng với ba điều kiện phải kiểm chứng**:

1. **Nhất quán:** mỗi concrete factory phải tạo các sản phẩm thuộc một họ hợp lệ và client phải dùng cùng nguồn tạo cho bộ sản phẩm liên quan.
2. **Thay thế:** client phải dựa trên hợp đồng chung; việc đổi họ nằm chủ yếu ở bước chọn hoặc cung cấp factory.
3. **Cô lập phụ thuộc:** hợp đồng không được làm lộ chi tiết của SDK hoặc hiện thực cụ thể; phụ thuộc vào chi tiết được tập trung tại ranh giới tích hợp.

Đổi lại, hệ thống gánh thêm interface, concrete factories, các hiện thực theo từng họ và công kiểm thử. **Lợi ích thường vượt chi phí khi có nhiều loại sản phẩm phải phối hợp nhất quán, có từ hai họ trở lên và các họ có khả năng thay đổi hoặc được bổ sung.** Nếu nhu cầu chỉ là tạo một đối tượng độc lập, thiết kế đơn giản hơn thường dễ bảo trì hơn.

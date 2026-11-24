# Bảng tiêu chí lựa chọn dựa trên số họ, số loại sản phẩm và hướng mở rộng

## 1. Vì sao cần so sánh theo số họ và số loại sản phẩm?

Khi thiết kế hệ thống Java, câu hỏi thường không phải «có dùng được **Abstract Factory** không?» mà là **«mẫu này có làm thay đổi ít phần mã hơn khi yêu cầu phát triển hay không?»**. Một ứng dụng chỉ có một loại logger cần thay implementation khác hẳn ứng dụng phải tạo đồng bộ nút bấm, hộp thoại và checkbox theo Windows, macOS hoặc Linux.

Abstract Factory thuộc nhóm **Creational Design Patterns** (mẫu thiết kế khởi tạo). Nó cung cấp hợp đồng để tạo ra **nhiều loại đối tượng liên quan hoặc phụ thuộc nhau** mà client không phải biết lớp sản phẩm cụ thể. Khi quyết định chọn mẫu, ba câu hỏi đặc biệt quan trọng:

1. Hệ thống có **bao nhiêu họ sản phẩm**?
2. Mỗi họ cần cung cấp **bao nhiêu loại sản phẩm**?
3. Trong tương lai, hệ thống **thường thêm họ mới** hay **thêm loại sản phẩm mới**?

Bài này là một công cụ so sánh và ra quyết định. Các con số giúp nhìn rõ hướng mở rộng, nhưng không thay thế việc xem xét nhu cầu nghiệp vụ, độ phức tạp, quy tắc tương thích và phạm vi thay đổi thực tế.

## 2. Mô hình hóa bằng H và P

Đặt:

- **H** (*families*): số **họ sản phẩm**, hay số biến thể trọn bộ. Ví dụ `Windows`, `macOS` và `Linux` tương ứng `H = 3`.
- **P** (*product types*): số **loại sản phẩm** mà mỗi họ cần cung cấp. Ví dụ `Button`, `Dialog` và `Checkbox` tương ứng `P = 3`.
- **Ô (họ, loại)**: một lựa chọn concrete product hoặc cách cài đặt cho vai trò đó trong một họ.

Trong mô hình đơn giản, nếu mỗi loại sản phẩm ở mỗi họ có một lớp triển khai riêng, số lớp concrete product là khoảng **H × P**.

| Loại sản phẩm | Họ Windows | Họ macOS | Họ Linux |
| --- | --- | --- | --- |
| `Button` | `WindowsButton` | `MacButton` | `LinuxButton` |
| `Dialog` | `WindowsDialog` | `MacDialog` | `LinuxDialog` |
| `Checkbox` | `WindowsCheckbox` | `MacCheckbox` | `LinuxCheckbox` |

Bảng trên có **H = 3** cột họ và **P = 3** hàng loại sản phẩm, tương ứng **9 ô triển khai**. Cấu trúc Abstract Factory thường có thêm:

- **P product interface**: `Button`, `Dialog` và `Checkbox`.
- **Một abstract factory interface**: `UIFactory` khai báo ba phương thức tạo.
- **H concrete factory**: `WindowsUIFactory`, `MacUIFactory` và `LinuxUIFactory`.
- **Client**: chỉ biết `UIFactory` và các product interface.

Ví dụ hợp đồng:

~~~java
interface Button {
    void render();
}

interface Dialog {
    void show();
}

interface Checkbox {
    boolean isChecked();
}

interface UIFactory {
    Button createButton();
    Dialog createDialog();
    Checkbox createCheckbox();
}
~~~

**Giới hạn của cách đếm:** `H × P` là mô hình hình chữ nhật dễ học, không phải định luật về số class. Hai họ có thể tái sử dụng một product implementation; một loại sản phẩm có thể có nhiều cấu hình; và một số tổ hợp có thể không được hỗ trợ. Hãy xem `H` và `P` là **số vai trò/họ theo thiết kế**, không phải số class bắt buộc phải tồn tại.

### 2.1. Họ sản phẩm khác tập hợp các lớp bất kỳ

Một họ chỉ có ý nghĩa khi các sản phẩm trong nó cần được **phối hợp theo một quy tắc chung**. Chẳng hạn, màn hình đang chạy giao diện macOS nên dùng cả nút bấm và hộp thoại thuộc họ macOS.

Không nên gom `PaymentGateway` và `Logger` thành một «họ» chỉ vì hai lớp đều được tạo ở lúc khởi động. Nếu lựa chọn nhà cung cấp thanh toán và loại logger **độc lập**, một abstract factory duy nhất có thể làm tăng ghép nối không cần thiết.

Có thể đặt một câu hỏi kiểm tra:

> Khi chuyển cấu hình từ họ A sang họ B, có cần đổi **nhiều loại sản phẩm cùng lúc** để hệ thống hoạt động đúng hoặc nhất quán không?

Nếu câu trả lời là có và các loại sản phẩm có hợp đồng chung, Abstract Factory là một ứng viên mạnh.

## 3. Bảng tiêu chí chính: H, P và hướng mở rộng

Bảng sau mô tả các khuynh hướng lựa chọn, **không phải ngưỡng cứng**. Số lượng class và chi phí bảo trì phụ thuộc vào quy mô mã, API chung, số client và cách triển khai.

| Tình huống | Dấu hiệu về H/P | Hướng nên cân nhắc | Lý do |
| --- | --- | --- | --- |
| Chỉ tạo một lớp đơn giản | `H = 1, P = 1` | Constructor hoặc dependency injection trực tiếp | Chưa có lợi ích rõ khi thêm hệ thống factory |
| Một loại sản phẩm, nhiều implementation | `H > 1, P = 1` | Factory đơn giản, Factory Method hoặc cấp dependency qua interface | Chưa xuất hiện nhu cầu đồng bộ **nhiều loại** sản phẩm |
| Một họ có nhiều loại sản phẩm | `H = 1, P > 1` | Tạo trực tiếp, module lắp ghép hoặc factory gọn nếu khởi tạo phức tạp | Không có lựa chọn giữa các **họ** để cô lập |
| Nhiều họ, nhiều loại, phải tương thích | `H > 1, P > 1` | **Abstract Factory** | Tập trung chọn một họ và tạo đồng bộ nhiều loại sản phẩm |
| Nhiều họ mới được bổ sung thường xuyên | `H` tăng nhanh, `P` khá ổn định | **Abstract Factory thường thuận lợi** | Có thể thêm concrete factory/họ mới mà client giữ nguyên hợp đồng |
| Nhiều loại sản phẩm mới được bổ sung thường xuyên | `P` tăng nhanh, có nhiều họ cũ | Cân nhắc chia factory, phân tách hợp đồng hoặc cách tổ chức khác | Mỗi loại mới có thể buộc cập nhật mọi concrete factory |
| Các vai trò thay đổi độc lập | Có nhiều biến thể nhưng không có quy tắc cùng họ | Factory riêng, dependency injection, Strategy hoặc composition | Một họ «cố định» sẽ áp đặt sự kết hợp không cần thiết |
| Chỉ vài tổ hợp hợp lệ trong ma trận | Hệ sản phẩm **thưa** (sparse) | Thiết kế capability/adapter theo tổ hợp thực, hoặc nhiều factory nhỏ | Một factory buộc triển khai mọi loại có thể tạo phương thức không hỗ trợ |
| Nhiều bước tạo **một** đối tượng phức tạp | Không đặc trưng bởi H/P | Builder | Vấn đề chính là quy trình lắp ráp một đối tượng |

### 3.1. Không có công thức «H từ 3 trở lên thì bắt buộc dùng Abstract Factory»

Ví dụ:

- **H = 2, P = 2**, nhưng có 30 màn hình phụ thuộc các sản phẩm cùng theme: Abstract Factory có thể đem lại lợi ích rõ ràng.
- **H = 10, P = 1**, nhưng chỉ một client chọn một strategy: một factory đơn giản có thể đủ.
- **H = 2, P = 12**, nhưng mỗi loại sản phẩm thay đổi giao diện thường xuyên: một abstract factory lớn có thể là điểm nghẽn.

Điều cần đo không chỉ là **độ lớn H/P hiện tại**, mà còn là **quy tắc tương thích, tần suất thay đổi và phạm vi lan truyền của thay đổi**.

## 4. Hướng mở rộng ảnh hưởng tới chi phí sửa mã như thế nào?

Giả sử ta bắt đầu bằng `H = 2` họ và `P = 3` loại sản phẩm:

~~~text
              Button        Dialog        Checkbox
Light         LightButton   LightDialog   LightCheckbox
Dark          DarkButton    DarkDialog    DarkCheckbox
~~~

### 4.1. Thêm một họ mới: tăng H

Muốn bổ sung họ **High Contrast**, trong cấu trúc đầy đủ thường cần:

1. Bổ sung sản phẩm `HighContrastButton`.
2. Bổ sung sản phẩm `HighContrastDialog`.
3. Bổ sung sản phẩm `HighContrastCheckbox`.
4. Viết `HighContrastUIFactory implements UIFactory`.
5. Cập nhật nơi chọn factory/cấu hình để biết thêm họ High Contrast.
6. Kiểm tra các sản phẩm tạo ra cùng một họ và tương thích nhau.

**Thông thường không phải sửa `UIFactory` hoặc client đang dùng interface**, miễn hợp đồng sản phẩm giữ nguyên.

Trong mô hình đơn giản, lượng triển khai mới tăng theo **P loại sản phẩm cho mỗi họ** cộng một concrete factory. Có thể nói chi phí triển khai của một họ mới **tỷ lệ với P** trong mô hình này, nhưng đây không phải độ phức tạp thuật toán runtime.

### 4.2. Thêm một loại sản phẩm mới: tăng P

Muốn thêm loại `Slider` cho tất cả các họ, thường phải:

1. Tạo interface `Slider`.
2. Thêm `Slider createSlider()` vào `UIFactory`.
3. Tạo `LightSlider` và `DarkSlider`.
4. Bổ sung phương thức `createSlider()` trong `LightUIFactory` và `DarkUIFactory`.
5. Cập nhật tất cả concrete factory khác hiện có nếu nhiều họ hơn.
6. Bổ sung kiểm thử hợp đồng Slider và kiểm thử tạo sản phẩm từng họ.

**Điểm đau:** interface `UIFactory` bị thay đổi và **mọi concrete factory hiện tại** phải đáp ứng phương thức mới. Trong mô hình đơn giản, công việc triển khai tăng theo **H họ hiện có**, dù những client không dùng Slider thường không cần sửa.

### 4.3. Bảng so sánh tác động

| Loại thay đổi | Product interface | Abstract factory interface | Concrete product | Concrete factory | Client hiện có |
| --- | --- | --- | --- | --- | --- |
| **Thêm một họ** | Thường giữ nguyên | Thường giữ nguyên | Thêm tối đa khoảng `P` triển khai (nếu mỗi ô riêng) | Thêm một factory | Thường giữ nguyên; thay cách chọn tại root |
| **Thêm một loại sản phẩm** | Thêm một interface | Thêm một phương thức tạo | Thêm tối đa khoảng `H` triển khai | Sửa `H` factory | Client cũ thường giữ nguyên; client cần loại mới phải bổ sung logic |
| **Thay constructor của một concrete product** | Thường giữ nguyên | Giữ nguyên | Sửa lớp liên quan | Sửa cách tạo của factory tương ứng | Thường giữ nguyên |
| **Đổi hợp đồng chung của một loại sản phẩm** | Sửa interface của loại đó | Có thể giữ nguyên nếu kiểu trả về không đổi | Sửa các implementation liên quan | Có thể sửa tùy cách khởi tạo | Những client phụ thuộc hợp đồng thay đổi có thể phải sửa |
| **Đổi họ theo cấu hình** | Giữ nguyên | Giữ nguyên | Không cần sửa | Không cần sửa nếu họ đã tồn tại | Cấp concrete factory khác tại điểm lắp ghép |

Ở đây **«thêm một loại»** giả định mọi họ đều hỗ trợ loại sản phẩm đó. Nếu chỉ một vài họ có Slider, việc mở rộng một factory interface chung có thể không phù hợp: các họ khác có nguy cơ phải ném `UnsupportedOperationException`. Hãy xem xét **phân tách interface factory** theo năng lực trước khi đưa ra một phương thức không thực hiện được ở mọi họ.

### 4.4. Chi phí thiết kế khác với số lớp cần viết

Số class chỉ là dấu hiệu ban đầu. Khi đánh giá thực tế còn phải xem:

- Số nơi phải sửa và kiểm tra khi thêm một biến thể.
- Số client đang sử dụng trực tiếp lớp cụ thể.
- Mức độ lặp trong các nhánh `if/switch` chọn sản phẩm.
- Chi phí đảm bảo các sản phẩm trong cùng họ vẫn tương thích.
- Khả năng dùng chung triển khai giữa các họ.
- API công khai có người tiêu dùng bên ngoài hay không.
- Khả năng kiểm thử độc lập khi thêm họ hoặc loại sản phẩm.

Đôi khi một concrete factory có ít code nhưng dùng nhiều cấu hình, lifecycle và tài nguyên, nên chi phí kiểm thử/triển khai còn đáng kể hơn số dòng code.

## 5. Sơ đồ quyết định theo chiều biến động

~~~mermaid
flowchart TD
    A["Cần thay đổi cách tạo đối tượng?"] --> B{"Có nhiều loại sản phẩm liên quan?"}
    B -->|Không| C["Tạo trực tiếp / Factory Method / factory đơn giản"]
    B -->|Có| D{"Nhiều họ được chọn theo một ngữ cảnh?"}
    D -->|Không| E["Lắp ghép trực tiếp hoặc factory nhỏ"]
    D -->|Có| F{"Sản phẩm phải tương thích trong từng họ?"}
    F -->|Không| G["Tách những lựa chọn độc lập"]
    F -->|Có| H{"Hướng mở rộng nổi bật?"}
    H -->|Thêm họ, giữ loại| I["Abstract Factory thuận lợi"]
    H -->|Thêm loại, ít đổi họ| J["Cân nhắc chi phí sửa mọi factory"]
    H -->|Cả hai đều biến động| K["Chia ranh giới factory / capability phù hợp"]
    I --> L["Kiểm tra hợp đồng và vòng đời"]
    J --> L
    K --> L
~~~

Sơ đồ không thay thế việc thiết kế **hợp đồng Abstract Product**. Hai biến thể của cùng một loại phải có những thao tác chung với ý nghĩa tương đương. Nếu client luôn phải ép kiểu từ `Button` sang `WindowsButton`, việc đếm H và P chưa giải quyết được vấn đề phụ thuộc.

## 6. So sánh Abstract Factory với các lựa chọn gần kề

### 6.1. Tạo trực tiếp hoặc dependency injection

Khi chỉ có một implementation và một vài nơi dùng:

~~~java
BookingService service = new BookingService(
    new SimpleNotifier()
);
~~~

Việc tạo trực tiếp ở **composition root** có thể hoàn toàn hợp lý. Chỉ riêng việc dùng `new` không phải là lý do để thêm Abstract Factory.

Nếu có nhiều implementation của **một** interface, có thể chọn dependency khi lắp ghép mà chưa cần một factory tạo cả họ:

~~~java
Notifier notifier = useSms
        ? new SmsNotifier()
        : new EmailNotifier();
~~~

Đây chỉ là lựa chọn một vai trò sản phẩm; chưa có quy tắc kết hợp nhiều loại sản phẩm.

### 6.2. Factory đơn giản (Simple Factory)

Một hàm hoặc lớp có thể nhận enum rồi trả về một sản phẩm:

~~~java
static Button createButton(Theme theme) {
    switch (theme) {
        case LIGHT:
            return new LightButton();
        case DARK:
            return new DarkButton();
        default:
            throw new IllegalArgumentException("Theme không hỗ trợ");
    }
}
~~~

Đây là ví dụ **Simple Factory** (cách gọi thông dụng, không phải một trong năm mẫu khởi tạo GoF). Nó thường gọn khi `P = 1` hoặc logic lựa chọn nhỏ.

Nếu client cần cả Button và Dialog, rồi tự gọi hai hàm chọn khác nhau, phải kiểm soát để chúng nhận **cùng theme**. Abstract Factory biểu diễn rõ ràng hơn yêu cầu một **đối tượng factory đã được chọn** tạo cả họ.

### 6.3. Factory Method

Factory Method theo mô tả GoF dựa vào một **điểm mở rộng trong lớp Creator**, thường để lớp con ghi đè phương thức tạo sản phẩm:

~~~java
interface Document {
    void open();
}

abstract class Editor {
    protected abstract Document createDocument();

    void openNewDocument() {
        createDocument().open();
    }
}
~~~

Ở đây, lớp con của `Editor` quyết định loại `Document` được tạo. Nếu điểm biến thiên chính là **một sản phẩm được chọn qua lớp con**, Factory Method có thể thích hợp.

Abstract Factory thường được dùng khi client nhận **một factory object qua composition**, và factory đó có các phương thức tạo **nhiều loại sản phẩm của một họ**. Hai mẫu có thể kết hợp; tên phương thức `create...()` một mình không đủ để kết luận là Factory Method pattern.

### 6.4. Builder và Prototype

| Mẫu | Trọng tâm | Có giải quyết trực tiếp ma trận H × P không? |
| --- | --- | --- |
| **Builder** | Từng bước lắp ráp **một đối tượng phức tạp**, có thể có nhiều tùy chọn | Không mặc nhiên; có thể được một factory tạo hoặc sử dụng |
| **Prototype** | Tạo instance mới bằng cách **sao chép từ một prototype** | Không mặc nhiên; concrete factory có thể dùng prototype để tạo sản phẩm |
| **Abstract Factory** | Tạo **nhiều loại sản phẩm theo cùng họ** | Có; đây là câu hỏi thiết kế trung tâm |

Nếu một `ReportRequest` có 20 tham số, Builder có thể giải quyết vấn đề tốt hơn. Nếu cần bộ `PdfFormatter` + `PdfExporter` hoặc bộ `HtmlFormatter` + `HtmlExporter`, lựa chọn một họ có thể phù hợp Abstract Factory. Hai mẫu không loại trừ nhau.

### 6.5. Strategy và Bridge: khi các chiều biến thiên độc lập

**Strategy** giúp đóng gói và thay thế một **cách thực hiện hành vi**. Ví dụ chọn thuật toán định giá, không nhất thiết cần tạo nhiều đối tượng thuộc cùng một họ. Một concrete strategy có thể được chọn tại composition root mà không phải dùng Abstract Factory.

**Bridge** giúp tách các chiều trừu tượng và triển khai có thể thay đổi độc lập. Nếu «theme» và «nền tảng» cần kết hợp tự do, ép mọi cặp thành một họ riêng có thể làm số tổ hợp tăng nhanh. Khi ấy cân nhắc tách hai chiều theo composition thay vì viết `WindowsDarkFactory`, `WindowsLightFactory`, `MacDarkFactory`, `MacLightFactory` cho mọi tổ hợp.

Không có công thức rằng Strategy hoặc Bridge luôn thay thế được Abstract Factory. Vấn đề cần xác định là **những lựa chọn có buộc phải đi theo một họ hay có thể cấu hình độc lập?**

### 6.6. Bảng chọn mẫu theo vấn đề

| Vấn đề nổi bật | Lựa chọn khởi đầu thường hợp lý |
| --- | --- |
| Chỉ một lớp đơn giản cần tạo | Constructor trực tiếp |
| Thay một dependency qua interface | DI / factory đơn giản |
| Lớp con quyết định sản phẩm ở một điểm mở rộng | Factory Method |
| Chọn **cả một họ gồm nhiều loại sản phẩm tương thích** | **Abstract Factory** |
| Lắp ráp một đối tượng phức tạp nhiều bước | Builder |
| Sao chép đối tượng đã cấu hình làm mẫu | Prototype |
| Đóng gói thuật toán có thể thay thế | Strategy |
| Hai chiều thay đổi độc lập và cần kết hợp tự do | Cân nhắc Bridge hoặc composition nhiều dependency |

## 7. Ví dụ Java đầy đủ: H = 2, P = 2

Ví dụ sau dùng **hai họ** `Light` và `Dark`, **hai loại sản phẩm** `Button` và `Dialog`. Nó cho thấy vì sao một client có thể chọn **một factory** và nhận trọn bộ sản phẩm tương thích.

Lưu vào tệp **`FamilyCriteriaDemo.java`**:

~~~java
// Abstract Product 1
interface Button {
    String render();
}

// Abstract Product 2
interface Dialog {
    String render();
}

// Abstract Factory: tạo P = 2 loại sản phẩm.
interface UIFactory {
    Button createButton();
    Dialog createDialog();
}

// Họ Light
class LightButton implements Button {
    @Override
    public String render() {
        return "[Light] Button";
    }
}

class LightDialog implements Dialog {
    @Override
    public String render() {
        return "[Light] Dialog";
    }
}

// Họ Dark
class DarkButton implements Button {
    @Override
    public String render() {
        return "[Dark] Button";
    }
}

class DarkDialog implements Dialog {
    @Override
    public String render() {
        return "[Dark] Dialog";
    }
}

// Concrete Factory 1
class LightUIFactory implements UIFactory {
    @Override
    public Button createButton() {
        return new LightButton();
    }

    @Override
    public Dialog createDialog() {
        return new LightDialog();
    }
}

// Concrete Factory 2
class DarkUIFactory implements UIFactory {
    @Override
    public Button createButton() {
        return new DarkButton();
    }

    @Override
    public Dialog createDialog() {
        return new DarkDialog();
    }
}

// Client chỉ sử dụng hợp đồng, không biết các lớp cụ thể.
class ReportScreen {
    private final Button button;
    private final Dialog dialog;

    ReportScreen(UIFactory factory) {
        button = factory.createButton();
        dialog = factory.createDialog();
    }

    void show() {
        System.out.println(button.render());
        System.out.println(dialog.render());
    }
}

public class FamilyCriteriaDemo {
    public static void main(String[] args) {
        // Composition root: kiểm chứng lần lượt cả hai họ.
        UIFactory[] factories = {
            new LightUIFactory(),
            new DarkUIFactory()
        };

        for (UIFactory factory : factories) {
            new ReportScreen(factory).show();
        }
    }
}
~~~

Biên dịch và chạy bằng JDK:

~~~bash
javac -encoding UTF-8 FamilyCriteriaDemo.java
java FamilyCriteriaDemo
~~~

Kết quả mong đợi:

~~~text
[Light] Button
[Light] Dialog
[Dark] Button
[Dark] Dialog
~~~

Chương trình có **H = 2** concrete factory, **P = 2** product interface và **4 concrete product** riêng. `ReportScreen` chỉ nhận `UIFactory`; nó không cần kiểm tra Light/Dark để khởi tạo Button hoặc Dialog.

### 7.1. Thử mở rộng theo họ

Giả sử cần thêm **High Contrast** mà không thêm vai trò sản phẩm mới. Theo cấu trúc hiện tại, ta có thể viết:

~~~java
class HighContrastButton implements Button {
    @Override
    public String render() {
        return "[High Contrast] Button";
    }
}

class HighContrastDialog implements Dialog {
    @Override
    public String render() {
        return "[High Contrast] Dialog";
    }
}

class HighContrastUIFactory implements UIFactory {
    @Override
    public Button createButton() {
        return new HighContrastButton();
    }

    @Override
    public Dialog createDialog() {
        return new HighContrastDialog();
    }
}
~~~

Đoạn mở rộng trên có thể thêm vào ví dụ Java; sau đó đăng ký `HighContrastUIFactory` tại composition root. **Không phải đổi `UIFactory` hoặc `ReportScreen`**.

Đó là ưu điểm của Abstract Factory khi **số họ tăng** và **tập loại sản phẩm giữ nguyên**.

### 7.2. Thử mở rộng theo loại sản phẩm

Giả sử muốn bổ sung `Checkbox`. Cần sửa hợp đồng:

~~~java
interface Checkbox {
    boolean isChecked();
}

// Trong UIFactory hiện có cần bổ sung:
// Checkbox createCheckbox();
~~~

Sau đó `LightUIFactory`, `DarkUIFactory` và cả `HighContrastUIFactory` (nếu đã thêm) đều phải triển khai `createCheckbox()`. Từng họ cần product implementation tương ứng.

Client **không gọi** `createCheckbox()` thường không phải sửa, nhưng **các concrete factory đều chịu tác động** của việc thay abstract factory interface. Đó là chi phí cần tính nếu số loại sản phẩm có xu hướng tăng liên tục.

## 8. Ba tình huống lựa chọn trong thực tế

### 8.1. Giao diện đa nền tảng: H tăng, P ổn định

Một ứng dụng desktop có bộ sản phẩm:

- `Button`, `Dialog`, `Checkbox`, `Menu`.
- Các họ Windows, macOS và Linux.
- Mỗi màn hình phải sử dụng những widget thống nhất theo nền tảng.

Ở đây `H = 3, P = 4`; nhu cầu thực tế là **thêm hỗ trợ nền tảng mới** trong khi các vai trò GUI tương đối ổn định.

**Nhận định:** Abstract Factory hợp lý. Thêm hệ điều hành mới thường chỉ yêu cầu bộ concrete product tương ứng, một concrete factory và cập nhật composition root. Mã màn hình dùng các interface có thể giữ nguyên.

Cần chú ý những thành phần không tồn tại trên mọi nền tảng; một contract quá rộng sẽ dẫn tới phương thức không hỗ trợ. Khi đó có thể chia ranh giới factory theo capability thay vì giả định ma trận đầy đủ.

### 8.2. Công cụ plugin với nhiều loại mới: P tăng nhanh

Giả sử một hệ thống báo cáo hiện chỉ có **PDF và HTML** (`H = 2`), nhưng mỗi tháng lại bổ sung nhiều loại thành phần: bảng, biểu đồ, biểu mẫu, chữ ký, chú giải, video nhúng, v.v. (`P` tăng liên tục).

Nếu một `ReportFactory` khai báo phương thức tạo mọi thành phần, mỗi plugin mới buộc cả `PdfReportFactory` và `HtmlReportFactory` cập nhật, kể cả khi một thành phần không có ý nghĩa ở HTML/PDF.

**Nhận định:** một Abstract Factory duy nhất có thể không phù hợp. Nên phân nhóm theo năng lực thực sự chung, giữ interface nhỏ, hoặc thiết kế registry/plugin riêng cho thành phần tùy chọn. Có thể vẫn dùng Abstract Factory trong **những nhóm sản phẩm cố định** mà tương thích theo định dạng là điều kiện bắt buộc.

### 8.3. Chọn một bộ adapter tương thích: H và P đều có ý nghĩa

Hệ thống đặt phòng hỗ trợ hai bộ tích hợp:

- **Provider A:** `PaymentClientA` và `RefundClientA`.
- **Provider B:** `PaymentClientB` và `RefundClientB`.

Nếu một phiên giao dịch cần **payment** và **refund** thuộc cùng nhà cung cấp, thì `H = 2, P = 2` và có ràng buộc tương thích rõ ràng.

**Nhận định:** Abstract Factory là ứng viên tốt để tạo bộ `PaymentPort` và `RefundPort` theo provider. Client không cần biết SDK của A hay B, và giảm nguy cơ thu tiền ở A nhưng gửi yêu cầu hoàn tiền sang B.

Tuy nhiên, quy tắc hoàn tiền vẫn phải gắn với **giao dịch đã phát sinh**, chứ không đơn thuần lấy «provider hiện tại» khi user hoàn tiền sau nhiều ngày. Cần lưu provider/transaction ID của giao dịch và tạo/cấp adapter theo đúng ngữ cảnh lịch sử. Abstract Factory hỗ trợ lựa chọn họ, không tự giải quyết vòng đời giao dịch.

## 9. Ma trận hướng thay đổi: đừng chỉ nhìn vào con số hiện tại

Một cách thực tế là xem **đường phát triển của mã nguồn**, không chỉ đếm class hôm nay.

| | **P ít thay đổi** | **P tăng thường xuyên** |
| --- | --- | --- |
| **H ít thay đổi** | Có thể đủ với lắp ghép trực tiếp hoặc factory nhỏ; dùng Abstract Factory nếu quy tắc đồng bộ đặc biệt quan trọng | Cẩn trọng với một factory interface lớn; cân nhắc chia vai trò |
| **H tăng thường xuyên** | **Vùng thuận lợi cho Abstract Factory** khi các họ có cùng tập loại sản phẩm | Cả hai chiều mở rộng đều tốn công; cân nhắc phân vùng họ, capability và chuẩn hóa contract |

**Giải thích ô cuối:** khi cả H lẫn P đều tăng thường xuyên, hệ thống có thể chịu số lượng tổ hợp thực thi ngày càng lớn. Abstract Factory vẫn có thể hữu ích ở **một phần miền bài toán** có các họ rõ ràng, nhưng không nên giả định một interface duy nhất chứa mọi product type có thể mở rộng vô hạn.

### 9.1. Công thức tham khảo cho ma trận đầy đủ

Trong mô hình giả định:

- Mỗi họ có đúng một implementation cho mỗi loại sản phẩm.
- Không có implementation dùng chung giữa các họ.
- Không có loại sản phẩm tùy chọn.
- Mỗi họ có một concrete factory.

Có thể dự kiến:

\[
N_{\text{concrete products}} = H \times P
\]

Ví dụ:

| H | P | Số cặp họ × loại trong mô hình | Diễn giải |
| ---: | ---: | ---: | --- |
| 2 | 2 | 4 | Nhỏ, dễ minh họa và kiểm chứng |
| 3 | 4 | 12 | Phải kiểm soát tính nhất quán của nhiều sản phẩm |
| 5 | 8 | 40 | Số tổ hợp cần duy trì/kiểm thử đã đáng chú ý |
| 10 | 12 | 120 | Cần xem khả năng dùng chung, chia factory hoặc giảm tổ hợp |

**Không nên coi các số 12, 40 hay 120 là ngưỡng chuyển mẫu thiết kế.** Chúng chỉ minh họa tác động của việc tăng hai chiều. Nếu dùng chung implementation, có thể ít class hơn; nếu mỗi cặp có nhiều biến thể con, có thể nhiều class hơn.

Trong quá trình phát triển, cần đánh giá cả **chi phí thay đổi** và **chi phí kiểm thử tương thích**, không chỉ số lượng đối tượng được khởi tạo lúc runtime.

## 10. Những sai lầm khi dùng bảng H/P

**Sai lầm 1 — «H > 1 và P > 1 thì luôn phải dùng Abstract Factory».** Không. Nếu các sản phẩm được chọn độc lập và không có quy tắc cùng họ, nên tách các quyết định và sử dụng factory/strategy tương ứng.

**Sai lầm 2 — «Abstract Factory luôn tạo ít class hơn».** Thường ngược lại: mẫu thêm interface và concrete factory để đổi lấy khả năng giảm phụ thuộc giữa client và implementation. Nó tối ưu **ranh giới thay đổi**, không phải số class tuyệt đối.

**Sai lầm 3 — «Interface tự bảo đảm sản phẩm cùng họ».** Không. `DarkUIFactory.createDialog()` vẫn có thể trả `LightDialog` vì cả hai cùng implement `Dialog`. Cần kiểm thử tính tương thích/đúng họ và thiết kế concrete factory phù hợp.

**Sai lầm 4 — «Thêm loại sản phẩm chỉ cần sửa UIFactory».** Chưa đủ. Mọi concrete factory phải triển khai phương thức mới, và thường cần concrete product tương ứng cho từng họ.

**Sai lầm 5 — «Thêm họ mới không bao giờ ảnh hưởng code hiện có».** Không hoàn toàn. Cần cập nhật nơi chọn factory, cấu hình, đăng ký dependency và kiểm thử; client thường giữ nguyên **nếu các hợp đồng chung không đổi**.

**Sai lầm 6 — «Factory phải tạo mọi sản phẩm của họ ngay một lúc».** Không. Một factory có thể được giữ trong client và chỉ tạo product khi cần. Điều quan trọng là các lời gọi thuộc **cùng lựa chọn họ**.

**Sai lầm 7 — «Chỉ có một họ hôm nay thì tuyệt đối không dùng Abstract Factory».** Nếu có yêu cầu chắc chắn về mở rộng theo provider/nền tảng và cần bảo đảm một bộ sản phẩm chung, việc đặt hợp đồng factory sớm có thể có lý. Ngược lại, một nhu cầu mơ hồ «biết đâu sau này» chưa đủ để biện minh cho cấu trúc phức tạp.

**Sai lầm 8 — «H × P là công thức chính xác tính số file và thời gian viết code».** Không. Đây là mô hình giảng giải đơn giản, bỏ qua tái sử dụng code, factory tổ hợp, cấu hình và những tổ hợp không tồn tại.

## 11. Checklist ra quyết định cho một dự án Java

Trước khi chọn Abstract Factory, trả lời các câu hỏi sau:

1. **Loại sản phẩm:** client cần những vai trò sản phẩm nào? Có ít nhất hai vai trò liên quan được dùng cùng nhau không?
2. **Họ:** có những bộ biến thể nào? Có yêu cầu phối hợp chúng theo một lựa chọn chung không?
3. **Hợp đồng:** các biến thể của từng loại có thể dùng cùng một product interface ổn định không?
4. **Hướng mở rộng:** 6–12 tháng tới nhiều khả năng tăng H, tăng P, hay tăng cả hai?
5. **Độ lan truyền:** hiện có bao nhiêu nơi `new` các lớp cụ thể hoặc phân nhánh theo platform/provider?
6. **Bảo đảm tương thích:** factory có thể tạo sản phẩm khác họ mà không bị phát hiện không? Kiểm tra ở đâu?
7. **Nơi lắp ghép:** composition root hoặc điểm tạo dependency nào quyết định họ?
8. **Vòng đời:** sản phẩm có cần tái sử dụng, tạo mới cho mỗi request hay thay khi cấu hình đổi không?
9. **Phương án gọn hơn:** chỉ dùng một factory đơn giản, Factory Method, Builder hoặc DI có giải quyết đủ yêu cầu không?
10. **Chi phí bảo trì:** nếu thêm một loại sản phẩm mới, nhóm có chấp nhận sửa tất cả concrete factory không?

Có thể chốt bằng ba câu hỏi quyết định:

> **Có một họ thực sự cần được chọn đồng bộ không?**  
> **Các client có thể dùng các product interface chung không?**  
> **Hướng thay đổi chủ yếu có thuận lợi cho việc bổ sung họ hơn là liên tục bổ sung loại sản phẩm không?**

Khi cả ba đều rõ, Abstract Factory thường đáng được ưu tiên. Nếu chỉ câu thứ nhất đúng nhưng hai câu sau chưa ổn, cần xem xét lại **ranh giới sản phẩm** trước khi triển khai.

## 12. Tự đánh giá qua các tình huống

**Câu 1.** Một ứng dụng có sáu loại logger nhưng không có sản phẩm phụ thuộc đi kèm. Có phải `H = 6, P = 1` nên Abstract Factory là lựa chọn bắt buộc?

**Trả lời:** Không. Đây chủ yếu là nhiều implementation của **một** loại sản phẩm. Dependency injection, Simple Factory hoặc Factory Method có thể đơn giản và đủ yêu cầu.

**Câu 2.** Một hệ GUI có ba họ và bốn loại sản phẩm. Theo mô hình hình chữ nhật, nếu thêm một họ thứ tư thì có bao nhiêu ô sản phẩm mới?

**Trả lời:** Thêm **4 ô**, một cho mỗi loại sản phẩm hiện tại, cùng concrete factory của họ mới nếu mỗi họ có một factory. Con số thực tế có thể thấp hơn nếu sản phẩm được tái sử dụng giữa các họ.

**Câu 3.** Cũng hệ đó, nếu thêm loại sản phẩm thứ năm cho mọi họ thì điều gì phải sửa?

**Trả lời:** Thêm product interface cho loại mới, thêm phương thức tạo vào abstract factory, thêm implementation cho từng họ, và sửa các concrete factory tương ứng. Khi đang có ba họ, sẽ có ba factory cần cung cấp phương thức mới.

**Câu 4.** Hệ thống có `H = 5, P = 5` nhưng mỗi role thay đổi độc lập. Có nên bắt tất cả dùng chung một Abstract Factory không?

**Trả lời:** Không nên chỉ dựa vào số đếm. Khi không có quy tắc đồng bộ theo họ, gộp vào một factory có thể tạo ghép nối giả. Tách các lựa chọn độc lập thường phù hợp hơn.

**Câu 5.** Vì sao có thể vẫn dùng Abstract Factory khi `H = 2, P = 2`?

**Trả lời:** Khi nhiều client phải dùng hai sản phẩm tương thích theo một biến thể, việc tập trung chọn họ và ẩn lớp cụ thể có thể mang lại giá trị ngay cả ở quy mô nhỏ.

**Câu 6.** Nếu có nhiều loại sản phẩm nhưng số họ ít và gần như không đổi, còn các loại mới được thêm thường xuyên, phải lưu ý gì?

**Trả lời:** Việc thêm một phương thức vào abstract factory sẽ làm mọi concrete factory phải cập nhật. Có thể cân nhắc factory nhỏ theo nhóm vai trò ổn định hoặc kiến trúc khác hỗ trợ plugin/capability thay vì một hợp đồng khổng lồ.

**Câu 7.** Concrete factory tạo đúng lớp theo theme nhưng các sản phẩm không tương thích về phiên bản giao thức. Abstract Factory có tự khắc phục không?

**Trả lời:** Không. Các interface chung chỉ bảo đảm một phần hợp đồng kiểu. Tính tương thích thực tế cần quy tắc phiên bản, triển khai đúng và các phép kiểm thử phù hợp.

## 13. Tổng kết

**Bảng tiêu chí lựa chọn Abstract Factory cần xét đồng thời số họ (H), số loại sản phẩm (P) và chiều thay đổi trong tương lai.** Mẫu này đặc biệt có lợi khi có **nhiều loại sản phẩm phải tương thích trong một họ**, client sử dụng được những interface ổn định và hệ thống thường **thêm họ mới** hơn là liên tục đổi tập loại sản phẩm.

Trong mô hình cơ bản, thêm một họ thường phát sinh công việc theo **P**, còn thêm một loại sản phẩm thường tác động tới **H concrete factory**. Đó là lý do Abstract Factory thuận lợi cho mở rộng theo **họ sản phẩm**, nhưng có đánh đổi khi mở rộng theo **loại sản phẩm**. Hãy dùng bảng so sánh như công cụ dự đoán phạm vi thay đổi, không như một quy tắc máy móc dựa trên các ngưỡng số lượng.

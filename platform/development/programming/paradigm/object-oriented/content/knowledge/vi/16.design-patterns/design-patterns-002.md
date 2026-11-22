# Factory Method và Abstract Factory trong Java

> **Nhóm:** Mẫu thiết kế (Design Patterns) → *Creational patterns* (nhóm mẫu khởi tạo).  
> **Mục tiêu:** Biết vì sao cần tách việc tạo đối tượng khỏi mã sử dụng, triển khai đúng cấu trúc **Factory Method** và **Abstract Factory**, nhận biết khác biệt, lựa chọn theo bài toán, và tránh nhầm với hàm tạo đối tượng thông thường.

## 1. Vấn đề chung: mã nghiệp vụ bị ràng buộc vào cách tạo đối tượng

Xét một ứng dụng có thể gửi thông báo qua email hoặc SMS. Nếu lớp nghiệp vụ tự quyết định implementation:

~~~java
void notifyCustomer(String channel, String customerId, String message) {
    if ("email".equals(channel)) {
        new EmailSender().send(customerId, message);
    } else if ("sms".equals(channel)) {
        new SmsSender().send(customerId, message);
    } else {
        throw new IllegalArgumentException("Unsupported channel");
    }
}
~~~

Khi thêm kênh mới, phải sửa `if/else` ở nơi đang sử dụng. Mã tạo đối tượng và logic điều phối thông báo bị trộn chung. Nếu nhiều nơi cùng chọn kênh, các nhánh dễ bị lặp.

Hai mẫu dưới đây cùng sử dụng **abstraction** để giảm coupling nhưng có trọng tâm khác nhau:

- **Factory Method** để **class cha định nghĩa một điểm mở rộng tạo sản phẩm**, còn class con quyết định tạo loại sản phẩm nào.
- **Abstract Factory** để client sử dụng **một đối tượng factory** tạo ra **một họ sản phẩm liên quan**, mà không biết các class cụ thể của họ đó.

Đừng vội thêm factory khi chỉ có một `new` đơn giản, ít khả năng thay đổi. Factory trở nên hữu ích khi việc tạo đối tượng là một **điểm biến thiên có chủ đích**.

## 2. Factory Method — trì hoãn quyết định tạo sản phẩm cho lớp con

**Định nghĩa theo GoF:** Định nghĩa interface cho việc tạo một đối tượng; để subclass quyết định class nào được khởi tạo. Factory Method cho phép class hoãn việc khởi tạo sản phẩm cụ thể cho các subclass.

Các vai trò điển hình:

| Vai trò | Chức năng | Ví dụ |
|---|---|---|
| **Product** | Hợp đồng của đối tượng được tạo | `Sender` |
| **Concrete Product** | Các implementation của Product | `EmailSender`, `SmsSender` |
| **Creator** | Chứa luồng xử lý chung và khai báo factory method | `NotificationCampaign` |
| **Concrete Creator** | Ghi đè factory method để trả sản phẩm cụ thể | `EmailCampaign`, `SmsCampaign` |

Điểm quan trọng: **Creator không nhất thiết chỉ là một “lớp nhà máy”**. Nó thường chứa logic xử lý thật, gọi factory method để lấy cộng tác viên phù hợp. Trong ví dụ dưới đây, `notifyCustomer` là luồng chung; `createSender` là factory method.

### 2.1. Java chạy độc lập: tạo kênh gửi thông báo

Tạo tệp `FactoryMethodDemo.java`. Mã chạy bằng Java 17+ và không gọi dịch vụ email/SMS thật.

~~~java
import java.util.List;
import java.util.Objects;

// Product: client chỉ cần thao tác trên hợp đồng này.
interface Sender {
    void send(String customerId, String message);
}

// Concrete products: các adapter mô phỏng để dễ chạy demo.
final class EmailSender implements Sender {
    @Override
    public void send(String customerId, String message) {
        System.out.printf("[EMAIL] %s: %s%n", customerId, message);
    }
}

final class SmsSender implements Sender {
    @Override
    public void send(String customerId, String message) {
        System.out.printf("[SMS] %s: %s%n", customerId, message);
    }
}

// Creator: thuật toán chung, đồng thời công bố factory method.
abstract class NotificationCampaign {
    public final void notifyCustomer(String customerId, String message) {
        Objects.requireNonNull(customerId, "customerId");
        Objects.requireNonNull(message, "message");

        if (customerId.isBlank() || message.isBlank()) {
            throw new IllegalArgumentException("Blank customer/message");
        }

        // Không cần biết Sender cụ thể là email hay SMS.
        Sender sender = Objects.requireNonNull(
                createSender(), "createSender returned null");
        sender.send(customerId, message);
    }

    protected abstract Sender createSender(); // Factory Method
}

// Concrete creators: lựa chọn sản phẩm bằng polymorphism.
final class EmailCampaign extends NotificationCampaign {
    @Override
    protected Sender createSender() {
        return new EmailSender();
    }
}

final class SmsCampaign extends NotificationCampaign {
    @Override
    protected Sender createSender() {
        return new SmsSender();
    }
}

public class FactoryMethodDemo {
    public static void main(String[] args) {
        List<NotificationCampaign> campaigns = List.of(
                new EmailCampaign(),
                new SmsCampaign()
        );

        for (NotificationCampaign campaign : campaigns) {
            campaign.notifyCustomer("CUST-42", "Don hang da xac nhan");
        }
    }
}
~~~

Chạy từ thư mục chứa tệp:

~~~bash
javac FactoryMethodDemo.java
java FactoryMethodDemo
~~~

Kết quả:

~~~text
[EMAIL] CUST-42: Don hang da xac nhan
[SMS] CUST-42: Don hang da xac nhan
~~~

**Điều đang diễn ra:**

1. Client chọn `EmailCampaign` hoặc `SmsCampaign` tại điểm lắp ghép (ví dụ ở `main`).
2. Client gọi **cùng API** `notifyCustomer(customerId, message)`.
3. Creator thực hiện kiểm tra đầu vào rồi gọi `createSender()`.
4. Phương thức được dispatch động tới subclass; subclass tạo `EmailSender` hoặc `SmsSender`.
5. Luồng xử lý chung không cần `if (sender instanceof EmailSender)` hay sửa khi có một Concrete Creator mới.

Trong hệ thống thật, `EmailSender` có thể gọi provider email và `SmsSender` gọi gateway SMS. `customerId` ở đây là ID chung, không phải địa chỉ email hay số điện thoại; các adapter thật sẽ cần cơ chế tra thông tin liên hệ và quy tắc xử lý lỗi phù hợp.

### 2.2. Sơ đồ quan hệ

~~~mermaid
classDiagram
    class Sender {
        <<interface>>
        +send(customerId, message) void
    }
    class EmailSender {
        +send(customerId, message) void
    }
    class SmsSender {
        +send(customerId, message) void
    }
    class NotificationCampaign {
        <<abstract>>
        +notifyCustomer(customerId, message) void
        #createSender() Sender
    }
    class EmailCampaign {
        #createSender() Sender
    }
    class SmsCampaign {
        #createSender() Sender
    }

    Sender <|.. EmailSender
    Sender <|.. SmsSender
    NotificationCampaign <|-- EmailCampaign
    NotificationCampaign <|-- SmsCampaign
    NotificationCampaign ..> Sender : sử dụng
    EmailCampaign ..> EmailSender : tạo
    SmsCampaign ..> SmsSender : tạo
~~~

Đây là **Factory Method đúng cấu trúc GoF**, vì **subclass ghi đè một phương thức tạo sản phẩm của Creator**. Nó không chỉ là một hàm có chữ “factory” trong tên.

### 2.3. Khi nào nên dùng?

Factory Method hữu ích khi có một **quy trình ổn định ở Creator** nhưng thành phần cần tạo trong quy trình khác nhau theo loại Creator: xuất báo cáo bằng renderer phù hợp, tạo message sender cho từng chiến dịch, tạo parser chuyên biệt trong một pipeline, tạo document trong một editor.

Đánh đổi: mỗi biến thể có thể cần một Concrete Creator, tăng số class và sử dụng kế thừa. Nếu đối tượng chỉ khác nhau qua cấu hình runtime hoặc Creator không thực sự chứa hành vi chung, truyền một factory hoặc chiến lược bằng composition có thể ngắn gọn hơn.

## 3. Abstract Factory — tạo một họ sản phẩm đồng bộ

**Định nghĩa theo GoF:** Cung cấp interface để tạo ra **các họ đối tượng liên quan hoặc phụ thuộc lẫn nhau** mà client không cần chỉ ra các class cụ thể.

Ví dụ: một ứng dụng desktop hỗ trợ giao diện **Light** và **Dark**. Mỗi theme gồm nhiều thành phần: `Button` và `Checkbox`. Client mong muốn các thành phần được tạo **đồng bộ trong cùng theme**.

| Họ sản phẩm | Button | Checkbox |
|---|---|---|
| **Light** | `LightButton` | `LightCheckbox` |
| **Dark** | `DarkButton` | `DarkCheckbox` |

Nếu client khởi tạo riêng lẻ từng class ở mọi nơi, có thể vô tình phối `LightButton` với `DarkCheckbox`. Abstract Factory gom việc lựa chọn cả họ vào một nơi.

### 3.1. Java chạy độc lập: Light/Dark UI

Tạo tệp **riêng** `AbstractFactoryDemo.java`, biên dịch và chạy độc lập với ví dụ Factory Method.

~~~java
import java.util.Objects;

// Abstract products: hợp đồng của từng loại thành phần UI.
interface Button {
    String render();
}

interface Checkbox {
    String render();
}

// Abstract factory: danh sách sản phẩm mà MỌI họ cần cung cấp.
interface UiFactory {
    Button createButton();
    Checkbox createCheckbox();
}

// Họ Light: hai sản phẩm có cùng phong cách.
final class LightButton implements Button {
    @Override
    public String render() {
        return "Button[LIGHT]";
    }
}

final class LightCheckbox implements Checkbox {
    @Override
    public String render() {
        return "Checkbox[LIGHT]";
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

// Họ Dark: cùng interface sản phẩm, implementation khác.
final class DarkButton implements Button {
    @Override
    public String render() {
        return "Button[DARK]";
    }
}

final class DarkCheckbox implements Checkbox {
    @Override
    public String render() {
        return "Checkbox[DARK]";
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

// Client chỉ biết các abstraction Button, Checkbox và UiFactory.
final class SettingsScreen {
    private final Button button;
    private final Checkbox checkbox;

    SettingsScreen(UiFactory factory) {
        Objects.requireNonNull(factory, "factory");

        // Tất cả thành phần được tạo qua CÙNG MỘT factory.
        this.button = Objects.requireNonNull(
                factory.createButton(), "button");
        this.checkbox = Objects.requireNonNull(
                factory.createCheckbox(), "checkbox");
    }

    void render() {
        System.out.println(button.render() + " | " + checkbox.render());
    }
}

public class AbstractFactoryDemo {
    public static void main(String[] args) {
        UiFactory light = new LightUiFactory();
        UiFactory dark = new DarkUiFactory();

        new SettingsScreen(light).render();
        new SettingsScreen(dark).render();
    }
}
~~~

Chạy:

~~~bash
javac AbstractFactoryDemo.java
java AbstractFactoryDemo
~~~

Kết quả:

~~~text
Button[LIGHT] | Checkbox[LIGHT]
Button[DARK] | Checkbox[DARK]
~~~

`SettingsScreen` chỉ biết **Abstract Products** (`Button`, `Checkbox`) và **Abstract Factory** (`UiFactory`). Nó không khởi tạo hoặc import `DarkButton` / `LightCheckbox`.

Một concrete factory tạo ra **cùng họ** các sản phẩm; chỉ cần thay `UiFactory` ở **composition root** là chuyển cả bộ giao diện. Nếu factory cụ thể trả về các sản phẩm lẫn theme, đó là lỗi implementation/hợp đồng họ sản phẩm; interface Java không tự kiểm tra được tính đồng bộ này.

### 3.2. Sơ đồ Abstract Factory

~~~mermaid
flowchart TD
    Client["SettingsScreen (client)"] --> Abstract["UiFactory"]
    Client --> BP["Button"]
    Client --> CP["Checkbox"]
    Light["LightUiFactory"] -.->|"implements"| Abstract
    Dark["DarkUiFactory"] -.->|"implements"| Abstract
    Light --> LB["LightButton"]
    Light --> LC["LightCheckbox"]
    Dark --> DB["DarkButton"]
    Dark --> DC["DarkCheckbox"]
    LB -.->|"implements"| BP
    DB -.->|"implements"| BP
    LC -.->|"implements"| CP
    DC -.->|"implements"| CP
~~~

Đặc trưng dễ nhận biết: **một factory có nhiều phương thức tạo các loại Product khác nhau** như `createButton()` và `createCheckbox()`; mỗi Concrete Factory triển khai toàn bộ phương thức để sản xuất **một biến thể nhất quán**.

### 3.3. Khi nào nên dùng?

- Có **nhiều loại sản phẩm liên quan** và cần chọn đồng thời một họ: Light/Dark UI, bộ connector cloud của AWS/Azure (storage, queue, notification), các thành phần xuất tài liệu theo định dạng, adapter cho nhiều nhà cung cấp cùng hệ sinh thái.
- Cần đổi họ sản phẩm trong cấu hình khởi động hoặc trong lúc dựng một phiên làm việc mà client không phụ thuộc vào class cụ thể.
- Cần cô lập các quy tắc tạo bộ sản phẩm và kiểm thử tính tương thích của sản phẩm trong cùng họ.

**Đánh đổi quan trọng:** Thêm **họ mới** thường chỉ cần thêm một Concrete Factory và các Concrete Product. Nhưng thêm **loại sản phẩm mới** vào interface (ví dụ `createSlider()`) có thể đòi sửa tất cả Concrete Factory. Abstract Factory phù hợp khi danh sách loại sản phẩm tương đối ổn định, còn số họ thay đổi.

## 4. So sánh trực diện

| Tiêu chí | Factory Method | Abstract Factory |
|---|---|---|
| Bài toán cốt lõi | Thay cách tạo **một loại Product** trong thuật toán của Creator | Tạo **một họ các Product liên quan** |
| Cơ chế biến thiên đặc trưng | **Kế thừa + override** một factory method | **Composition**: truyền đối tượng factory vào client |
| Giao diện sáng tạo | `protected Sender createSender()` trong Creator | `UiFactory` có `createButton()` và `createCheckbox()` |
| Khi thêm biến thể | Thêm Concrete Creator + Product tương ứng | Thêm Concrete Factory + các Product thuộc họ mới |
| Khi thêm loại sản phẩm hoàn toàn mới | Có thể cần thêm abstraction/quy trình Creator mới | Thường phải bổ sung API và cập nhật mọi concrete factory |
| Client chính | Làm việc qua Creator (hoặc gọi operation chung của Creator) | Làm việc qua Abstract Factory và Abstract Products |
| Ví dụ ở trên | `EmailCampaign` chọn `EmailSender` | `DarkUiFactory` tạo cả `DarkButton` + `DarkCheckbox` |
| Điểm cần chú ý | Dễ sinh nhiều subclass chỉ để chọn một sản phẩm | Khó mở rộng theo chiều thêm loại sản phẩm |

**Hai mẫu không loại trừ nhau.** Một concrete factory trong Abstract Factory có thể dùng các factory method bên trong để tạo mỗi loại sản phẩm. Sự khác biệt nằm ở **ý đồ thiết kế và cấu trúc client sử dụng**, không nằm ở tên phương thức.

## 5. Phân biệt với Simple Factory và static factory method

Nhiều tài liệu gọi mọi hàm trả về object là “Factory Method”, dẫn đến nhầm lẫn.

**Simple Factory** thường là một class hoặc hàm tập trung việc chọn implementation bằng tham số:

~~~java
enum Channel { EMAIL, SMS }

final class SenderFactory {
    static Sender create(Channel channel) {
        return switch (channel) {
            case EMAIL -> new EmailSender();
            case SMS -> new SmsSender();
        };
    }
}

// Client:
Sender sender = SenderFactory.create(Channel.EMAIL);
~~~

Đoạn trên giả sử dùng lại các class `Sender`, `EmailSender`, `SmsSender` từ ví dụ `FactoryMethodDemo.java` (nếu đặt trong cùng package). Đây là **simple factory** theo cách gọi thông dụng: một hàm tự quyết định theo enum, **không có Creator/subclass ghi đè factory method**. Khi thêm enum mới, phải sửa `switch`; simple factory vẫn có thể hoàn toàn phù hợp với hệ thống nhỏ.

**Static factory method** là một phương thức `static` tạo hoặc trả về object, ví dụ `List.of(...)` và `LocalDate.of(...)` trong Java. Đây là một cách thiết kế API, **không đồng nghĩa** với pattern **Factory Method** GoF. Static factory có thể trả object mới, object được lưu đệm hoặc một implementation ẩn tùy hợp đồng API.

Tên gọi không quyết định pattern. Hãy hỏi **điểm biến thiên nằm ở subclass nào, hay ở đối tượng factory nào, hay đơn giản chỉ ở tham số truyền vào?**

## 6. Factory khác DI và Strategy ở đâu?

**Dependency Injection (DI)** là kỹ thuật **cấp dependency từ ngoài vào đối tượng**. Trong `new SettingsScreen(new DarkUiFactory())`, ta có constructor injection cho `UiFactory`; Abstract Factory là loại dependency đang được cấp. DI không tự động là Factory Method/Abstract Factory.

**Strategy** đóng gói một **thuật toán/hành vi có thể thay thế**. Factory tạo ra **đối tượng**. Chúng có thể kết hợp: factory tạo hoặc chọn `PricingStrategy`; service dùng Strategy để tính giá.

Một quy tắc thực dụng:

- Nếu khác biệt nằm ở **cách vận hành hàm hiện có**, ưu tiên xét Strategy.
- Nếu khác biệt nằm ở **class được tạo trong một quy trình chung mà subclass có quyền quyết định**, xét Factory Method.
- Nếu cần tạo **bộ sản phẩm cùng biến thể** (nhiều interface liên quan), xét Abstract Factory.
- Nếu chỉ cần chọn một implementation tại khởi động và ít biến thể, DI bằng constructor ở composition root có thể đã đủ.

Trong Spring, `@Bean` và DI container giải quyết khởi tạo, wiring và vòng đời bean, nhưng **không tự động** làm mọi đoạn `@Bean` thành Factory Method/Abstract Factory theo GoF. Khi chỉ cần cấu hình một `Sender`, có thể inject trực tiếp; không phải lúc nào cũng cần thêm một lớp factory.

## 7. Thiết kế sạch khi dùng factory trong ứng dụng thực tế

### 7.1. Tách nơi lựa chọn biến thể khỏi client

Cả hai ví dụ đều có điểm **composition root**:

~~~java
// Factory Method:
NotificationCampaign campaign = new EmailCampaign();

// Abstract Factory:
UiFactory uiFactory = new DarkUiFactory();
SettingsScreen screen = new SettingsScreen(uiFactory);
~~~

Với cấu hình runtime, quyết định biến thể có thể nằm ở `main`, module bootstrap hoặc cấu hình DI. Client chính không nên rải `new DarkButton()` hay `if (factory instanceof DarkUiFactory)` khắp logic.

Cần phân biệt **đổi cấu hình giữa các lần khởi động** với **đổi biến thể cho từng request**. Nếu mỗi HTTP request cần nhà cung cấp khác nhau, một singleton factory cố định từ startup không đủ; có thể cần registry/selector kiểm soát quyền chọn, hoặc truyền factory phù hợp vào từng request. Lựa chọn này phụ thuộc ngữ cảnh vận hành, không phải bản thân mẫu tự cung cấp.

### 7.2. Không lộ class cụ thể trong API trừ khi có lý do chính đáng

Nếu `UiFactory.createButton()` trả về `DarkButton` và client phải ép kiểu để gọi hành vi độc quyền, mục tiêu tách concrete product sẽ suy yếu. Interface sản phẩm nên thể hiện các thao tác **thực sự cần cho client**, tránh nhét phương thức chỉ phù hợp với một họ.

Không nên tạo một interface với hàng chục phương thức mà đa số implementation chỉ ném `UnsupportedOperationException`. Xem lại việc chia interface, giới hạn hỗ trợ hoặc cách biểu diễn capability.

### 7.3. Xác định thời điểm tạo, quyền sở hữu và vòng đời

Hai demo dùng `new` nên mỗi lần gọi factory method có thể tạo đối tượng mới. Trong thực tế, các dependency đắt tiền như HTTP client, connection pool hoặc SDK có thể cần tái sử dụng. Factory **có thể** trả object đã tạo trước, object từ pool hoặc object mới, miễn hợp đồng cho phép.

Cần mô tả rõ:
- Object do factory trả về có giữ trạng thái riêng của request không?
- Có an toàn khi chia sẻ giữa nhiều thread không?
- Ai chịu trách nhiệm đóng `AutoCloseable` và quản lý vòng đời tài nguyên?
- Client có được thay đổi trạng thái sản phẩm sau khi tạo không?

Đừng dùng cache/singleton mặc định chỉ vì một factory gọi nhiều lần; nhất là với sản phẩm giữ dữ liệu người dùng hoặc ngữ cảnh giao dịch.

### 7.4. Xử lý lỗi tạo đối tượng

Khởi tạo có thể thất bại vì cấu hình sai, thiếu thông tin xác thực, provider không khả dụng hoặc tài nguyên cạn. Phân biệt **lỗi cấu hình khi khởi động** và **lỗi xử lý khi gọi operation**. Contract nên nói rõ factory có thể trả `null` hay phải ném exception; mặc định trả về object hợp lệ hoặc ném exception có ngữ nghĩa rõ ràng giúp client đơn giản hơn.

## 8. Kiểm thử theo đúng mục tiêu mẫu

### Factory Method: kiểm tra thuật toán chung thực sự dùng sản phẩm được tạo

Vì `Sender` chỉ in console trong demo, một bài kiểm thử có thể tạo Creator trả một fake Sender và ghi nhận lời gọi. Đoạn sau dùng các class `NotificationCampaign`/`Sender` từ ví dụ Factory Method; test chạy với JUnit Jupiter:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

class FactoryMethodContractTest {
    @Test
    void creatorDelegatesToProduct() {
        AtomicInteger sent = new AtomicInteger();
        NotificationCampaign campaign = new NotificationCampaign() {
            @Override
            protected Sender createSender() {
                return (id, message) -> {
                    assertEquals("CUST-1", id);
                    assertEquals("Hello", message);
                    sent.incrementAndGet();
                };
            }
        };

        campaign.notifyCustomer("CUST-1", "Hello");
        assertEquals(1, sent.get());
    }

    @Test
    void invalidInputIsRejectedBeforeCreation() {
        AtomicInteger creations = new AtomicInteger();
        NotificationCampaign campaign = new NotificationCampaign() {
            @Override
            protected Sender createSender() {
                creations.incrementAndGet();
                return (id, msg) -> {};
            }
        };

        assertThrows(IllegalArgumentException.class,
                () -> campaign.notifyCustomer("", "Hello"));
        assertEquals(0, creations.get());
    }
}
~~~

### Abstract Factory: kiểm tra một họ sản phẩm nhất quán

Test có thể tạo từng concrete factory, kiểm tra nó tạo đủ các sản phẩm không `null`, thực hiện được thao tác theo interface và tuân thủ quy ước theme. Ví dụ JUnit Jupiter, sử dụng class trong `AbstractFactoryDemo.java`:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class AbstractFactoryContractTest {
    @Test
    void darkFactoryCreatesMatchingProducts() {
        UiFactory factory = new DarkUiFactory();

        Button button = assertDoesNotThrow(factory::createButton);
        Checkbox checkbox = assertDoesNotThrow(factory::createCheckbox);

        assertNotNull(button);
        assertNotNull(checkbox);
        assertEquals("Button[DARK]", button.render());
        assertEquals("Checkbox[DARK]", checkbox.render());
    }
}
~~~

Kiểm thử bên trên dùng output demo làm tín hiệu kiểm tra theme. Trong ứng dụng UI thật, có thể kiểm tra qua thuộc tính theme/token được công bố trên abstraction hoặc dùng screenshot/visual tests ở cấp tích hợp. Test này không đủ chứng minh giao diện hiển thị đúng trong mọi môi trường.

**Lưu ý khi thực thi:** Mỗi ví dụ chính là một tệp `.java` riêng; đặt test cùng package/source set thích hợp và thêm dependency `org.junit.jupiter:junit-jupiter` cùng JUnit test runner. Các đoạn test cần class của ví dụ tương ứng trên classpath.

## 9. Câu hỏi ra quyết định và bài tập

### Bảng tình huống

| Tình huống | Lựa chọn cân nhắc | Vì sao |
|---|---|---|
| Một công cụ import chung, subclass XML/JSON tạo parser phù hợp | **Factory Method** | Creator giữ quy trình import, subclass chọn parser |
| App tạo cả Button, Checkbox, Dialog theo Light/Dark | **Abstract Factory** | Chọn một **họ sản phẩm** đồng bộ |
| Một hàm trả Sender theo enum EMAIL/SMS | **Simple Factory** | Tập trung việc tạo bằng tham số, không dùng subclass Creator |
| Service chỉ cần một `EmailSender` đã cấu hình tại startup | **Constructor DI** | Có thể đủ đơn giản, tránh factory không cần thiết |
| Thay đổi thuật toán giảm giá trên cùng đối tượng đơn hàng | **Strategy** | Biến thiên là hành vi/thuật toán |
| Cần tạo các adapter Storage + Queue + Email theo AWS/Azure | **Abstract Factory** (nếu cần một họ nhất quán) | Nhiều product cùng provider, cần tránh cấu hình pha trộn |

### Bài tập 1 — Factory Method

Thiết kế một quy trình `DocumentExporter.export(Document)` cố định gồm kiểm tra đầu vào, tạo `Renderer` và gọi `render(Document)`. Viết hai subclass `PdfExporter` và `HtmlExporter` ghi đè `createRenderer()`. Kiểm tra rằng lớp Creator không import `PdfRenderer`/`HtmlRenderer`; khi thêm `MarkdownExporter`, thuật toán chung không đổi. Có thể triển khai renderer demo trả `String` để không cần thư viện PDF thật.

### Bài tập 2 — Abstract Factory

Thiết kế `CloudFactory` có `createObjectStorage()` và `createMessageQueue()`. Cài đặt `AwsFactory` và `AzureFactory`, mỗi factory cung cấp đúng hai adapter tương ứng. Một `BackupWorkflow` chỉ nhận `CloudFactory`. Viết unit test dùng factory giả để kiểm tra workflow; sau đó kiểm tra lỗi thiết kế nếu người triển khai vô tình tạo Storage của AWS và Queue của Azure trong cùng factory.

### Tự kiểm tra

1. Trong Factory Method, đối tượng nào **sở hữu thuật toán chung**, đối tượng nào **quyết định class sản phẩm**?
2. Nếu client cần ba loại sản phẩm cùng theme, mẫu nào giúp tránh chọn từng loại rời rạc?
3. Vì sao `static Sender create(Channel)` không tự động là Factory Method theo GoF?
4. Với Abstract Factory, thêm **họ mới** và thêm **loại sản phẩm mới** ảnh hưởng tới mã nguồn khác nhau thế nào?
5. Khi nào truyền một dependency bằng constructor là đủ, không cần dựng thêm tầng factory?

**Ghi nhớ:** **Factory Method** mở rộng *cách tạo một Product bên trong quy trình Creator thông qua subclass*. **Abstract Factory** đóng gói *việc tạo nhiều Product liên quan thành một họ nhất quán thông qua một đối tượng factory*. Hãy chọn theo **điểm biến thiên của bài toán**, không theo việc mã có chứa từ “Factory”.
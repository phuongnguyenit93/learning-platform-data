# Tên, qualifier và khóa định danh của thành phần

## 1. Bài toán: một hợp đồng có nhiều hiện thực

Trong **Dependency Injection (DI)**, một lớp nghiệp vụ khai báo **phụ thuộc cần sử dụng**, còn nơi lắp ghép quyết định tạo và cung cấp đối tượng cụ thể. Khi chỉ có một hiện thực phù hợp, constructor injection rất trực quan:

~~~java
NotificationSender sender = new EmailSender();
ReceiptService receipts = new ReceiptService(sender);
~~~

Đây là cách **lắp ghép bằng Java thuần**: `ReceiptService` nhận một đối tượng thỏa hợp đồng `NotificationSender`. Nhưng nếu ứng dụng có cả `EmailSender` và `SmsSender`, câu hỏi mới xuất hiện:

> Khi nhiều đối tượng cùng đáp ứng một hợp đồng, ứng dụng chọn **đối tượng nào**, dựa vào **thông tin định danh nào**, và **ai chịu trách nhiệm chọn**?

Đó là vấn đề **lựa chọn thành phần (component selection)**. Tên, qualifier và khóa định danh giúp biểu diễn lựa chọn, nhưng chúng không có ý nghĩa giống nhau ở mọi hệ thống.

Ví dụ có hai mục đích khác nhau:

- **Biên nhận đơn hàng luôn gửi bằng email:** Quyết định sử dụng `EmailSender` có thể được đưa ra **một lần tại composition root**, sau đó tiêm instance đã chọn vào `ReceiptService`.
- **Người dùng chọn email hoặc SMS ở mỗi yêu cầu:** Quyết định thực sự **thay đổi theo từng thao tác**. Một thành phần điều phối thông báo có thể nhận một registry ánh xạ `Channel.EMAIL`/`Channel.SMS` tới đúng sender.

Bài học thuộc chương **Lựa chọn thành phần** của module **DEPENDENCY_INJECTION**. Mục tiêu là hiểu quan hệ giữa hợp đồng và định danh, thực hành lựa chọn bằng constructor injection và composition root trong Java thuần, rồi mới liên hệ các khái niệm bean name và qualifier của DI container.

## 2. Phân biệt type, name, qualifier và key

Bốn yếu tố dưới đây có thể trùng giá trị văn bản nhưng phục vụ những vai trò khác nhau.

| Yếu tố | Nó trả lời câu hỏi gì? | Ví dụ | Lưu ý |
| --- | --- | --- | --- |
| **Type / hợp đồng** | Đối tượng có **khả năng** nào? | `NotificationSender` | Nhiều lớp có thể cùng hiện thực một type |
| **Name / tên thành phần** | Thành phần được **đăng ký hoặc gọi tên** ra sao trong một registry/container? | `"emailSender"` | Quy tắc duy nhất, phạm vi và mặc định phụ thuộc cơ chế đăng ký |
| **Qualifier / dấu phân biệt** | Trong nhiều thành phần hợp type, **loại nào phù hợp với điểm tiêm**? | `"email"`, `"primary"` hoặc annotation có thuộc tính | Một qualifier có thể là chuỗi hoặc metadata có kiểu; tùy DI framework |
| **Key / khóa tra cứu** | Dùng **giá trị nào** để lấy một lựa chọn từ bảng ánh xạ? | `Channel.EMAIL` | Có thể là `enum`, chuỗi, record hay value object |

**Type** thể hiện khả năng. **Name** định danh trong một hệ thống đăng ký. **Qualifier** thêm điều kiện để chọn ứng viên đáp ứng một điểm tiêm. **Key** là dữ liệu dùng để tra cứu, đặc biệt khi lựa chọn theo runtime.

Ví dụ, `EmailSender` có thể:

- Có kiểu `NotificationSender`;
- Được container đăng ký với tên `"transactionalEmailSender"`;
- Mang qualifier ngữ nghĩa `"transactional"`;
- Được gắn với khóa `Channel.EMAIL` trong registry do ứng dụng tự xây.

Những thông tin này **không bắt buộc phải bằng nhau**. Không nên suy ra khóa `Channel.EMAIL` từ tên Java class `EmailSender` hoặc đổi tên biến thì tự động thay đổi qualifier ở mọi nơi.

### “Danh tính thành phần” không phải “danh tính đối tượng nghiệp vụ”

Tên component `"emailSender"` xác định một thành phần trong hệ thống lắp ghép. Ngược lại, `orderId` hoặc `tenantId` định danh đơn hàng hoặc tenant trong miền nghiệp vụ. Trộn chúng vào cùng một chuỗi tự do dễ gây nhầm ý nghĩa và khó kiểm tra cấu hình.

Ví dụ, `"primary"` đôi khi là qualifier của một implementation, nhưng không thể dùng nó như chứng cứ rằng người dùng có quyền truy cập tenant mang mã `"primary"`. **Khóa chọn thành phần không thay thế kiểm tra xác thực và phân quyền.**

## 3. Vì sao chọn theo type có thể chưa đủ?

Giả sử hai implementation:

~~~java
interface NotificationSender {
    void send(String destination, String message);
}

final class EmailSender implements NotificationSender {
    public void send(String destination, String message) {
        System.out.println("EMAIL " + destination + ": " + message);
    }
}

final class SmsSender implements NotificationSender {
    public void send(String destination, String message) {
        System.out.println("SMS " + destination + ": " + message);
    }
}
~~~

Đoạn mã trên là minh họa các type; ví dụ chạy đầy đủ sẽ xuất hiện ở phần sau.

Nếu một container quản lý **hai đối tượng cùng type** `NotificationSender` mà một điểm tiêm chỉ yêu cầu `NotificationSender`, container có thể không có đủ dữ kiện để chọn một ứng viên. Tùy framework và cấu hình, việc này có thể dẫn đến lỗi *ambiguous dependency*, cần chỉ rõ qualifier, ưu tiên mặc định hoặc cấu hình đăng ký phù hợp.

Trong **manual DI**, chính composition root phải chọn:

~~~java
NotificationSender email = new EmailSender();
NotificationSender sms = new SmsSender();

// Phụ thuộc bên dưới đã được chọn rõ ràng trước khi tiêm.
ReceiptService receipts = new ReceiptService(email);
~~~

Như vậy, việc nhiều implementation cùng type **không làm Java constructor injection bị mơ hồ**. Constructor chỉ nhận đúng tham chiếu mà caller truyền; sự mơ hồ xuất hiện ở **bước chọn tham chiếu**, nhất là khi một container thực hiện tự động.

Sơ đồ:

~~~mermaid
flowchart TB
    Root["Composition root"]
    Email["EmailSender : NotificationSender"]
    Sms["SmsSender : NotificationSender"]
    Receipt["ReceiptService"]
    Root -->|"tạo"| Email
    Root -->|"tạo"| Sms
    Root -->|"chọn EmailSender và tiêm"| Receipt
    Receipt -->|"gửi biên nhận qua tham chiếu đã chọn"| Email
~~~

Ở mô hình này, `ReceiptService` không cần biết tên đăng ký, qualifier, tên class của adapter, hoặc cách chọn implementation. Đây thường là lựa chọn đơn giản nhất khi **chính sách chọn không thay đổi theo từng request**.

## 4. Hai kiểu lựa chọn: cấu hình tĩnh và lựa chọn tại runtime

### 4.1. Chọn một lần ở composition root

Ví dụ: mọi biên nhận đơn hàng phải gửi bằng email. Composition root tạo sender cho email và truyền nó vào service:

~~~java
NotificationSender sender = new EmailSender();
ReceiptService receipts = new ReceiptService(sender);
~~~

Nếu sau này dùng adapter email khác, chỉ cần thay lựa chọn tại nơi lắp ghép. Service giữ hợp đồng `NotificationSender` và không biết chi tiết.

Lựa chọn cũng có thể phụ thuộc **cấu hình khởi động**:

~~~java
// Phác họa: config là cấu hình đã được validate trước đó.
NotificationSender sender = config.useSandbox()
        ? new ConsoleSender()
        : new ProductionEmailSender(config.emailSettings());
ReceiptService receipts = new ReceiptService(sender);
~~~

Đây là phác họa nguyên tắc; các kiểu `ConsoleSender`, `ProductionEmailSender` và `config` cần được định nghĩa theo ứng dụng. Điểm quan trọng là **cấu hình lựa chọn được xử lý ở composition root**, không giấu trong constructor của `ReceiptService`.

### 4.2. Chọn theo dữ liệu của từng thao tác

Giả sử thông báo marketing có thể gửi qua email hoặc SMS theo lựa chọn đã được xác thực của người dùng. Một thao tác nhận `Channel` và cần tra đúng sender.

Trong trường hợp này, bắt `NotificationRouter` có một sender cố định là không đủ. Có thể dùng **registry** ánh xạ khóa ngữ nghĩa sang sender:

~~~text
Channel.EMAIL --> EmailSender
Channel.SMS   --> SmsSender
~~~

Đó là một **dependency map có kiểu** được xây tại composition root. Nghiệp vụ nhìn thấy `Channel` (khái niệm miền nghiệp vụ) và hợp đồng `NotificationSender`, nhưng không biết tên bean trong container.

Điểm khác với service locator là registry này có **vai trò hẹp và rõ**: cung cấp các sender cho một tập kênh thông báo cụ thể. Service locator tổng quát dạng `getBean(String)`, `resolve(Class<?>)` có thể khiến bất kỳ service nào tự ý lấy bất kỳ phụ thuộc nào, làm danh sách dependency thật của service bị ẩn.

## 5. Ví dụ Java thuần: registry theo khóa có kiểu và chọn implementation

Lưu toàn bộ mã bên dưới thành **`ComponentSelectionDemo.java`**. Mã dùng Java 11 trở lên và không cần Spring hay DI container.

~~~java
import java.util.Collections;
import java.util.EnumMap;
import java.util.EnumSet;
import java.util.Map;
import java.util.Objects;

public final class ComponentSelectionDemo {

    // Key có kiểu, ổn định trong phạm vi các kênh được hỗ trợ.
    public enum Channel {
        EMAIL,
        SMS
    }

    public interface NotificationSender {
        void send(String destination, String message);
    }

    public static final class EmailSender implements NotificationSender {
        @Override
        public void send(String destination, String message) {
            System.out.println("EMAIL -> " + destination + ": " + message);
        }
    }

    public static final class SmsSender implements NotificationSender {
        @Override
        public void send(String destination, String message) {
            System.out.println("SMS -> " + destination + ": " + message);
        }
    }

    // Chỉ dùng khi lắp ghép. Từ chối một key được đăng ký hai lần.
    public static final class SenderBindings {
        private final EnumMap<Channel, NotificationSender> entries =
                new EnumMap<>(Channel.class);

        public SenderBindings bind(
                Channel channel, NotificationSender sender) {
            Objects.requireNonNull(channel, "channel");
            Objects.requireNonNull(sender, "sender");

            if (entries.containsKey(channel)) {
                throw new IllegalArgumentException(
                        "Đăng ký trùng kênh: " + channel);
            }
            entries.put(channel, sender);
            return this;
        }

        public SenderRegistry build() {
            return new SenderRegistry(entries);
        }
    }

    // Registry bất biến về ánh xạ key -> instance sau khi build.
    public static final class SenderRegistry {
        private final Map<Channel, NotificationSender> senders;

        private SenderRegistry(Map<Channel, NotificationSender> configured) {
            EnumMap<Channel, NotificationSender> copy =
                    new EnumMap<>(Channel.class);
            copy.putAll(Objects.requireNonNull(configured, "configured"));

            if (!copy.keySet().containsAll(EnumSet.allOf(Channel.class))) {
                throw new IllegalArgumentException(
                        "Thiếu đăng ký cho một hoặc nhiều kênh");
            }

            this.senders = Collections.unmodifiableMap(copy);
        }

        public NotificationSender require(Channel channel) {
            Objects.requireNonNull(channel, "channel");
            NotificationSender selected = senders.get(channel);
            if (selected == null) {
                throw new IllegalArgumentException(
                        "Không hỗ trợ kênh: " + channel);
            }
            return selected;
        }
    }

    // Trường hợp 1: policy chọn sẵn kênh biên nhận ở composition root.
    public static final class ReceiptService {
        private final NotificationSender sender;

        public ReceiptService(NotificationSender sender) {
            this.sender = Objects.requireNonNull(sender, "sender");
        }

        public void sendReceipt(String destination, String orderId) {
            if (destination == null || destination.isBlank()) {
                throw new IllegalArgumentException("destination không hợp lệ");
            }
            if (orderId == null || !orderId.matches("[A-Z0-9-]+")) {
                throw new IllegalArgumentException("orderId không hợp lệ");
            }

            sender.send(destination, "Biên nhận cho " + orderId);
        }
    }

    // Trường hợp 2: channel được chọn riêng cho mỗi thao tác.
    public static final class NotificationRouter {
        private final SenderRegistry registry;

        public NotificationRouter(SenderRegistry registry) {
            this.registry = Objects.requireNonNull(registry, "registry");
        }

        public void deliver(
                Channel channel, String destination, String message) {
            Objects.requireNonNull(channel, "channel");
            if (destination == null || destination.isBlank()) {
                throw new IllegalArgumentException("destination không hợp lệ");
            }
            if (message == null || message.isBlank()) {
                throw new IllegalArgumentException("message không hợp lệ");
            }

            registry.require(channel).send(destination, message);
        }
    }

    public static void main(String[] args) {
        // Composition root chọn và đăng ký instance có chủ đích.
        SenderRegistry registry = new SenderBindings()
                .bind(Channel.EMAIL, new EmailSender())
                .bind(Channel.SMS, new SmsSender())
                .build();

        // Chọn một lần: ReceiptService chỉ biết NotificationSender.
        ReceiptService receipts =
                new ReceiptService(registry.require(Channel.EMAIL));
        receipts.sendReceipt("an@example.com", "ORDER-001");

        // Chọn theo từng lời gọi: Router được tiêm registry có kiểu.
        NotificationRouter router = new NotificationRouter(registry);
        router.deliver(Channel.SMS, "0900000000", "Đơn hàng đã gửi");
        router.deliver(Channel.EMAIL, "binh@example.com", "Thông báo mới");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ComponentSelectionDemo.java
java ComponentSelectionDemo
~~~

Kết quả dự kiến:

~~~text
EMAIL -> an@example.com: Biên nhận cho ORDER-001
SMS -> 0900000000: Đơn hàng đã gửi
EMAIL -> binh@example.com: Thông báo mới
~~~

### Chú ý các quyết định thiết kế trong ví dụ

**`SenderBindings` dùng khi lắp ghép.** Nó từ chối đăng ký trùng `Channel`. Điều này giúp phát hiện lỗi cấu hình ngay tại composition root thay vì chấp nhận hành vi “đăng ký sau đè đăng ký trước” một cách âm thầm.

**`SenderRegistry` nhận bản sao.** `EnumMap` được sao chép khi `build()` hoàn tất và bọc bằng `Collections.unmodifiableMap`. Sau đó, sửa builder không ảnh hưởng tới bảng ánh xạ đã lắp ghép. Tính bất biến ở đây chỉ áp dụng cho **ánh xạ**; từng đối tượng sender có thể mang trạng thái nội bộ mutable và phải được đánh giá riêng về thread safety.

**Kiểm tra đủ key tại startup.** Ví dụ giả định **cả EMAIL và SMS là bắt buộc**, nên `build()` từ chối cấu hình thiếu một kênh. Với hệ thống cho phép tắt SMS, chính sách hợp lệ có thể khác: chỉ yêu cầu các kênh thực sự được bật và đưa ra lỗi rõ nếu có request yêu cầu kênh không hỗ trợ. Cần chọn một chính sách nhất quán.

**`ReceiptService` không biết registry.** Nó nhận đúng một sender đã được chọn và chỉ dùng khả năng gửi. Đây là thiết kế phù hợp khi định tuyến không phải trách nhiệm của service.

**`NotificationRouter` biết `Channel` theo yêu cầu nghiệp vụ.** Router cần lựa chọn lúc chạy, nên giữ một registry được tiêm là hợp lý. Nó không cần biết `EmailSender` hay `SmsSender` là class gì.

Sơ đồ tổng quát:

~~~mermaid
flowchart TB
    Root["App.main() — composition root"]
    Root -->|"bind Channel.EMAIL"| Email["EmailSender"]
    Root -->|"bind Channel.SMS"| Sms["SmsSender"]
    Root -->|"build"| Registry["SenderRegistry (key -> sender)"]
    Registry -->|"EMAIL"| Email
    Registry -->|"SMS"| Sms
    Root -->|"require EMAIL, tiêm sender"| Receipt["ReceiptService"]
    Root -->|"tiêm registry"| Router["NotificationRouter"]
    Receipt -.->|"gửi bằng sender đã chọn"| Email
    Router -->|"tra channel khi gọi"| Registry
~~~

## 6. Kiểm thử lựa chọn đúng, thiếu key và trùng key

Một registry chỉ có giá trị nếu lựa chọn ổn định và lỗi cấu hình được phát hiện đúng. Test nên kiểm tra cả **đường thành công** và **đường sai**:

- Đăng ký `EMAIL` và `SMS` dẫn đến đúng sender.
- `ReceiptService` được lắp bằng sender email dù tồn tại nhiều implementation.
- `NotificationRouter` chọn đúng sender dựa vào `Channel` của lời gọi.
- Đăng ký trùng cùng một key bị từ chối, không bị ghi đè âm thầm.
- Thiếu một key bắt buộc khiến build graph thất bại trước khi xử lý request.
- Tham số hoặc dữ liệu không hợp lệ không gọi nhầm một sender khác.

Lưu **`ComponentSelectionDemoTest.java`** cạnh tệp ví dụ:

~~~java
public final class ComponentSelectionDemoTest {

    static final class RecordingSender
            implements ComponentSelectionDemo.NotificationSender {
        int calls;
        String lastDestination;
        String lastMessage;

        @Override
        public void send(String destination, String message) {
            calls++;
            lastDestination = destination;
            lastMessage = message;
        }
    }

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    static void expectIllegalArgument(Runnable action) {
        try {
            action.run();
        } catch (IllegalArgumentException expected) {
            return;
        }
        throw new AssertionError("Phải ném IllegalArgumentException");
    }

    public static void main(String[] args) {
        RecordingSender email = new RecordingSender();
        RecordingSender sms = new RecordingSender();

        ComponentSelectionDemo.SenderRegistry registry =
                new ComponentSelectionDemo.SenderBindings()
                        .bind(ComponentSelectionDemo.Channel.EMAIL, email)
                        .bind(ComponentSelectionDemo.Channel.SMS, sms)
                        .build();

        // Cùng một contract, chọn được đúng từng instance.
        check(registry.require(ComponentSelectionDemo.Channel.EMAIL) == email,
                "EMAIL phải trỏ đến email sender");
        check(registry.require(ComponentSelectionDemo.Channel.SMS) == sms,
                "SMS phải trỏ đến SMS sender");

        // Chọn tĩnh: biên nhận luôn dùng email.
        ComponentSelectionDemo.ReceiptService receipts =
                new ComponentSelectionDemo.ReceiptService(
                        registry.require(ComponentSelectionDemo.Channel.EMAIL));
        receipts.sendReceipt("an@example.com", "ORDER-001");
        check(email.calls == 1, "Email phải được gọi một lần");
        check(sms.calls == 0, "SMS không được gọi khi gửi biên nhận");

        // Chọn động: kênh truyền vào từng lần gọi.
        ComponentSelectionDemo.NotificationRouter router =
                new ComponentSelectionDemo.NotificationRouter(registry);
        router.deliver(
                ComponentSelectionDemo.Channel.SMS,
                "0900000000",
                "Xác nhận số điện thoại");
        check(sms.calls == 1, "Router phải chọn SMS");
        check("0900000000".equals(sms.lastDestination),
                "Router truyền sai người nhận");

        router.deliver(
                ComponentSelectionDemo.Channel.EMAIL,
                "binh@example.com",
                "Thông báo email");
        check(email.calls == 2, "Router phải chọn email");

        // Một key không được đăng ký hai lần.
        ComponentSelectionDemo.SenderBindings duplicate =
                new ComponentSelectionDemo.SenderBindings()
                        .bind(ComponentSelectionDemo.Channel.EMAIL, email);
        expectIllegalArgument(() ->
                duplicate.bind(ComponentSelectionDemo.Channel.EMAIL, sms));

        // Không công bố registry thiếu kênh bắt buộc.
        ComponentSelectionDemo.SenderBindings incomplete =
                new ComponentSelectionDemo.SenderBindings()
                        .bind(ComponentSelectionDemo.Channel.EMAIL, email);
        expectIllegalArgument(() -> incomplete.build());

        // Đầu vào sai không được phát tán thông báo.
        expectIllegalArgument(() ->
                router.deliver(
                        ComponentSelectionDemo.Channel.SMS, "  ", "Thông báo"));
        check(sms.calls == 1, "Không được gửi khi destination không hợp lệ");

        System.out.println("Tất cả kiểm thử đều đạt.");
    }
}
~~~

Chạy:

~~~bash
javac ComponentSelectionDemo.java ComponentSelectionDemoTest.java
java ComponentSelectionDemoTest
~~~

Test này dùng Java thuần, không cần DI container hay framework mocking. Nó xác nhận behavior của **composition root + registry + consumer** chứ không chỉ kiểm tra rằng hàm `get()` trả một đối tượng bất kỳ.

Có thể bổ sung test cho việc chỉnh sửa builder sau `build()`, kiểm tra không làm thay đổi registry cũ; hoặc thêm kênh mới vào `enum Channel` và xác nhận startup phải có binding tương ứng.

## 7. Khi nào dùng string key, enum hay kiểu định danh riêng?

Một khóa tốt cần ổn định, có ý nghĩa và có thể kiểm tra ở ranh giới cấu hình.

| Cách biểu diễn | Điểm mạnh | Rủi ro / tình huống nên cân nhắc |
| --- | --- | --- |
| `String`, ví dụ `"email"` | Thuận tiện cho YAML, biến môi trường, cấu hình ngoài | Dễ gõ sai, đổi tên tùy tiện, trùng nghĩa và khó tìm tham chiếu |
| `enum Channel` | Tập giá trị đóng, kiểm tra kiểu ở compile time, hỗ trợ `EnumMap` | Cần sửa/mở rộng code khi xuất hiện kênh mới; không phù hợp khóa plugin hoàn toàn động |
| Value object/record như `ComponentKey` | Có thể kiểm tra chuẩn tên, namespace, version và đặc tính miền | Phải thiết kế quy tắc so sánh, chuẩn hóa và serialize nhất quán |
| `Class<T>` | Tiện cho ánh xạ theo type | Không đủ để phân biệt nhiều instance có cùng type; dễ thành service locator tổng quát |

Ở bài ví dụ, hai kênh được xác định rõ và ít thay đổi, nên `enum` đơn giản và mạnh hơn các chuỗi rải rác.

Nếu một hệ thống plugin cho phép bên thứ ba đăng ký kênh mới mà không biên dịch lại, `String` hoặc một value object có namespace có thể phù hợp hơn. Lúc ấy, cần quy định rõ:

- Khóa có **phân biệt chữ hoa/thường** hay không?
- Có chuẩn hóa dấu cách hoặc alias cũ không?
- Một khóa có bắt buộc **duy nhất trong phạm vi** tenant, module hoặc toàn ứng dụng không?
- Khóa có đổi theo version không, và cấu hình cũ có được hỗ trợ không?
- Nếu khóa không tồn tại, hệ thống trả lỗi gì và ở giai đoạn nào?

Không dùng tên class như `com.example.EmailSender` làm key nghiệp vụ mặc định. Refactor package/class là thay đổi kỹ thuật, không nhất thiết phải ảnh hưởng đến cấu hình và hợp đồng bên ngoài.

### Một ví dụ định danh có cấu trúc

~~~java
// Java 16+: minh họa key có namespace và name, không phải file chạy độc lập.
record ComponentKey(String namespace, String name) {
    ComponentKey {
        if (namespace == null || namespace.isBlank()
                || name == null || name.isBlank()) {
            throw new IllegalArgumentException("Key không hợp lệ");
        }
    }
}
~~~

Có thể thêm version hoặc loại kênh nếu ứng dụng cần. Nhưng nếu chỉ có `EMAIL` và `SMS`, record trên có thể là mức độ phức tạp không cần thiết. **Chọn kiểu khóa theo khả năng biến đổi đã biết**, không cần xây cơ chế plugin tổng quát trước khi có nhu cầu.

## 8. Qualifier trong DI container: cùng nguyên tắc, khác cách diễn đạt

Khi dùng DI container, việc chọn một implementation thường được biểu diễn bằng **metadata tại điểm đăng ký hoặc điểm tiêm**. Các khái niệm phổ biến:

- **Tên thành phần/bean name:** một định danh do cấu hình hoặc container gán.
- **Qualifier:** một dấu phân biệt hoặc ràng buộc bổ sung để chọn ứng viên trong những đối tượng có type phù hợp.
- **Mặc định/ưu tiên:** một số container có cách đánh dấu ứng viên ưu tiên khi không chỉ định rõ qualifier.
- **Collection injection:** có thể lấy nhiều implementation của một type để tổ chức lựa chọn, tùy framework.

Ví dụ dạng khái niệm trong Spring:

~~~java
// Chỉ minh họa annotation; yêu cầu thư viện và cấu hình Spring tương ứng.
final class ReceiptService {
    private final NotificationSender sender;

    ReceiptService(@Qualifier("email") NotificationSender sender) {
        this.sender = sender;
    }
}
~~~

Ở đây, qualifier `"email"` là một phần **cơ chế lắp ghép container**, nhằm phân biệt ứng viên đáp ứng `NotificationSender`. Nó không có nghĩa `ReceiptService` phải tự hỏi container “hãy lấy bean tên email” trong từng lần gửi.

Spring còn có các khái niệm như `@Primary` và đăng ký bean theo tên; Jakarta CDI có hệ qualifier annotation riêng. **Quy tắc chọn chính xác, tên annotation, cách giải quyết nhiều ứng viên và thứ tự ưu tiên phụ thuộc framework/phiên bản**, nên cần đối chiếu tài liệu framework khi triển khai. Ví dụ annotation ở đây là cú pháp minh họa, không phải mã Java thuần của phần thực hành.

Quan trọng hơn: cùng mục tiêu lựa chọn có thể được thực hiện **không cần framework** bằng:

~~~java
ReceiptService receipts = new ReceiptService(emailSender);
~~~

Container có thể tự động giải quyết cách **chọn và truyền** theo cấu hình; tư duy thiết kế vẫn là xác định đúng hợp đồng, ý nghĩa của qualifier và scope của instance.

## 9. Định danh ổn định không được làm mờ quyền sở hữu và scope

Hai thành phần có cùng type và qualifier khác nhau vẫn có thể có **vòng đời khác nhau**. Ví dụ:

- `EmailSender` có client HTTP dùng chung trong suốt đời ứng dụng.
- `SmsSender` có session giao dịch được tạo theo request.
- `NotificationRouter` sống suốt ứng dụng.

Nếu registry app-scoped giữ **session thực** của một request trong field, bạn đã tạo **captive dependency**: router giữ một resource ngắn hạn vượt vòng đời. Đổi tên bean hoặc qualifier không sửa được lỗi scope này.

Phải phân biệt:

1. **Chọn hiện thực nào:** khóa/qualifier quyết định sender hoặc cách tạo sender.
2. **Lấy instance ở scope nào:** dùng chung, tạo mới hay lấy theo request.
3. **Ai sở hữu và đóng instance:** composition root, request boundary, factory hoặc caller.

Nếu SMS cần session riêng cho từng lần gửi, registry app-scoped có thể giữ **factory tạo session** hoặc giữ một sender được thiết kế tạo/đóng session trong thao tác, thay vì giữ session đã mở của request đầu tiên.

~~~mermaid
flowchart LR
    Router["NotificationRouter dùng chung"]
    Binding["Channel.SMS -> SmsSenderFactory"]
    Session["SmsSession theo request/tác vụ"]
    Router --> Binding
    Binding -->|"create vào đúng scope"| Session
    Session -->|"close khi kết thúc"| End["Kết thúc tác vụ"]
~~~

Cần thêm quản lý tài nguyên và thread safety thích hợp khi triển khai thực tế; sơ đồ chỉ diễn đạt quan hệ vòng đời.

## 10. Lỗi cấu hình và chính sách fallback

Khi có nhiều implementation, **thất bại chọn thành phần** cần được xử lý minh bạch.

| Tình huống | Chính sách thường phù hợp | Tại sao |
| --- | --- | --- |
| Hai binding cho cùng khóa trong cùng scope | Từ chối lúc build/startup | Tránh “last registration wins” vô tình |
| Thiếu binding bắt buộc | Fail fast lúc lắp ghép | Không chuyển lỗi đến request đầu tiên |
| Request chọn kênh chưa hỗ trợ | Trả lỗi có nghĩa; không chọn đại một adapter khác | Bảo vệ ý nghĩa lựa chọn của người dùng |
| Nhiều bean cùng type, không có qualifier đủ rõ | Yêu cầu điểm tiêm hoặc cấu hình làm rõ lựa chọn | Tránh chọn sai hiện thực |
| Key từ cấu hình đổi tên | Có chiến lược migrate/alias đã định nghĩa | Tránh phá cấu hình vận hành |
| Adapter đã chọn bị lỗi runtime | Xử lý theo chính sách retry/failover riêng | Lựa chọn đúng không đảm bảo mạng luôn hoạt động |

**Không tự ý fallback từ SMS sang email** chỉ vì thiếu một binding hoặc gửi SMS thất bại: điều đó có thể thay đổi kênh liên lạc mà người dùng đã chọn, có tác động đến quyền riêng tư hoặc quy tắc nghiệp vụ. Fallback chỉ nên xảy ra khi **chính sách sản phẩm cho phép**, dữ liệu liên hệ phù hợp và các điều kiện cần đã được xác thực.

Khóa định danh không phải thông tin bí mật. Không dùng **giá trị key** hoặc **tên bean** để thay thế xác thực và phân quyền. Ví dụ, request gửi `Channel.EMAIL` không chứng minh người gọi có quyền gửi tới bất kỳ địa chỉ nào.

## 11. Anti-pattern: rải tên và lấy dependency từ container ngay trong nghiệp vụ

Một service biết chính xác tên bean và tự gọi container:

~~~java
// Phác họa anti-pattern, phụ thuộc vào API của container.
final class WrongReceiptService {
    private final BeanContainer container;

    WrongReceiptService(BeanContainer container) {
        this.container = container;
    }

    void sendReceipt(String destination) {
        NotificationSender sender =
                (NotificationSender) container.get("emailSender");
        sender.send(destination, "Biên nhận");
    }
}
~~~

Các kiểu `BeanContainer` và `get` chỉ để minh họa, không thuộc Java chuẩn. Vấn đề:

- **Phụ thuộc thật bị ẩn:** constructor chỉ nói service cần container, không nói nó cần `NotificationSender`.
- **Tên bean trở thành chi tiết nghiệp vụ:** đổi cấu hình đăng ký có thể làm service lỗi khi chạy.
- **Kiểm thử khó hơn:** test phải dựng container giả hoặc giả lập cơ chế tra cứu không liên quan đến hành vi gửi biên nhận.
- **Khó kiểm soát scope:** service có thể lấy resource có vòng đời không phù hợp hoặc giữ nhầm đối tượng ngắn hạn.

Nếu lựa chọn là cố định, tiêm đúng `NotificationSender` đã chọn. Nếu lựa chọn là hành vi nghiệp vụ thực sự động, tiêm một **registry/router/factory chuyên biệt có hợp đồng rõ**. Không phải mọi thao tác lookup đều xấu; điều cần tránh là biến toàn bộ container thành “hộp dịch vụ” mà bất kỳ service nào cũng có thể truy cập tùy ý.

## 12. Cách ra quyết định khi thiết kế lựa chọn thành phần

Một quy trình nhỏ, có thể dùng ngay khi review composition root:

1. **Xác định khả năng cần dùng:** Ví dụ `NotificationSender.send`. Hợp đồng nên mô tả khả năng của caller, không bắt caller biết adapter nội bộ.
2. **Xác định số lựa chọn và thời điểm quyết định:** Một hiện thực tại startup hay thay đổi theo từng thao tác?
3. **Đặt tên có ý nghĩa ổn định:** Chẳng hạn `EMAIL`, `SMS` hoặc qualifier `transactional`, tránh dùng tên biến/package như cấu hình nghiệp vụ.
4. **Định nghĩa phạm vi duy nhất:** Trong một registry, mỗi key chỉ có một binding? Trong container, qualifier kết hợp type ra một ứng viên hợp lệ?
5. **Kiểm tra đầy đủ ở điểm lắp ghép:** Fail fast với duplicate/required missing, tạo graph hoàn chỉnh rồi mới công bố.
6. **Xem lại lifecycle:** Key/qualifier không giải quyết vấn đề shared mutable state, request scope hoặc tài nguyên cần đóng.
7. **Test quyết định lựa chọn:** Chứng minh đúng sender được gọi; thử cả cấu hình thiếu/trùng và dữ liệu runtime không hợp lệ.

### Bài tập thực hành

**Bài 1 — Thêm kênh mới:** Mở rộng `Channel` bằng `PUSH` và thêm `PushSender`. Quan sát vì sao `SenderRegistry.build()` báo thiếu đăng ký cho đến khi composition root khai báo binding. Thiết kế test bảo đảm thông báo PUSH không bị gửi qua SMS.

**Bài 2 — Lựa chọn tĩnh theo môi trường:** Viết hai implementation `PaymentGateway`, gồm sandbox và production, cùng một `PaymentService`. Chọn gateway bằng cấu hình đã được xác thực tại startup. Giữ `PaymentService` không biết tên class hoặc tên bean.

**Bài 3 — Key dạng chuỗi:** Thay `Channel` bằng `String` vì ứng dụng cần kênh do plugin đăng ký. Đề xuất quy tắc chuẩn hóa, phát hiện trùng key và xử lý unknown key. Giải thích vì sao đổi tên Java class không nên làm hỏng cấu hình kênh.

**Bài 4 — Qualifier và scope:** Một registry sống suốt ứng dụng giữ ba sender, trong đó một sender giữ state theo request. Hãy chỉ ra sai phạm vòng đời và thiết kế lại binding để registry giữ factory hoặc sender an toàn cho nhiều request.

**Bài 5 — Test âm:** Xây một cấu hình có hai binding cho `EMAIL`, một cấu hình thiếu `SMS` và một request có destination trống. Xác định lỗi nào phải xuất hiện ở lúc build và lỗi nào phải xuất hiện ở lúc xử lý request.

Để tự đánh giá, hãy trả lời ba câu: **Thành phần đáp ứng hợp đồng nào? Lựa chọn được xác định bằng tên, qualifier hay key nào? Quyết định đó nên diễn ra tại composition root hay theo từng thao tác?** Khi phân biệt được ba yếu tố này, bạn có thể tổ chức lựa chọn các thành phần trong Java thuần bằng constructor injection và composition root, rồi chuyển sang DI container mà vẫn kiểm soát được scope và vòng đời.

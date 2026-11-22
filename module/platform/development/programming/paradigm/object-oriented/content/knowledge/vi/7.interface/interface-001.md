# Giao diện như một hợp đồng và một vai trò trong Java

Trong Java, **giao diện (`interface`)** là một cách mô tả **khả năng mà một đối tượng cam kết cung cấp**, để mã sử dụng có thể gọi khả năng đó mà không cần biết đối tượng thuộc lớp cụ thể nào.

Hãy tưởng tượng ứng dụng cần gửi thông báo. Mã nghiệp vụ chỉ quan tâm việc **gửi một thông báo tới người nhận**. Nó không nên phải biết nơi gửi là email, SMS, thông báo trong ứng dụng, hay một phiên bản giả lập phục vụ kiểm thử. Ta có thể đặt tên chung cho khả năng đó là `DeliveryChannel`.

Hai cách nhìn bổ sung cho nhau:

- **Giao diện như hợp đồng:** nếu một lớp `implements DeliveryChannel`, lớp đó phải cung cấp các thao tác của giao diện và đáp ứng những quy tắc sử dụng đã công bố.
- **Giao diện như vai trò:** một đối tượng có thể được sử dụng *trong vai trò* kênh gửi thông báo, ngay cả khi bản chất của đối tượng còn có những khả năng khác. Một lớp có thể thực hiện nhiều vai trò thông qua nhiều interface.

Hợp đồng giúp các bên phối hợp ổn định. Vai trò giúp ta nói về **điều đối tượng làm được** thay vì hỏi **nó được tạo từ lớp nào**.

## 1. Interface định nghĩa những gì?

Ví dụ đơn giản:

~~~java
interface DeliveryChannel {
    DeliveryReceipt deliver(Notice notice);
}
~~~

Đối với Java compiler, giao diện này khai báo một thao tác có tên `deliver`, nhận `Notice` và trả về `DeliveryReceipt`.

Ở ngữ cảnh này, phương thức được hiểu là `public abstract` dù không viết rõ hai từ khóa đó. Một class cụ thể triển khai giao diện phải cung cấp phiên bản `public` tương ứng, trừ khi class cũng là abstract.

Tuy nhiên, **chữ ký phương thức chưa phải toàn bộ hợp đồng**. Người viết và người sử dụng giao diện còn phải thống nhất:

| Câu hỏi | Quy ước cần có |
|---|---|
| Ai được gọi? | Mã đang giữ một tham chiếu kiểu `DeliveryChannel` |
| Đầu vào nào hợp lệ? | `Notice` khác `null`, có người nhận và nội dung hợp lệ |
| Lời gọi thành công có ý nghĩa gì? | Trong ví dụ học tập: hoàn tất một lần **mô phỏng** gửi |
| Giá trị trả về nói gì? | `DeliveryReceipt` khác `null`, cho biết kênh và thông tin thao tác |
| Đầu vào có bị sửa không? | Không; `Notice` được thiết kế bất biến |
| Nếu không thực hiện được thì sao? | Thông báo lỗi theo quy ước, không tự ý trả `null` hoặc coi như thành công |
| Có gây tác dụng phụ không? | Phải nói rõ trong hợp đồng thực tế; ví dụ dưới chỉ mô phỏng, không gửi mạng thật |

Interface cung cấp **khung cú pháp được compiler kiểm tra**. Quy tắc như “không trả `null`”, “không âm thầm bỏ thông báo” hoặc “phải dùng đúng người nhận” là **hợp đồng hành vi**, được giữ bằng thiết kế, kiểm tra và kiểm thử.

## 2. Ví dụ Java hoàn chỉnh: cùng một vai trò, nhiều cách thực hiện

Tình huống: hệ thống gửi lời chào đến người dùng thông qua một kênh được cấu hình từ bên ngoài. Ta có một service chung, hai cách gửi mô phỏng và một vai trò phụ dùng để kiểm tra sức khỏe kênh.

Lưu toàn bộ vào **`Demo.java`**, chạy với Java 17 trở lên:

~~~java
import java.util.Objects;

public class Demo {
    public static void main(String[] args) {
        NotificationService byEmail = new NotificationService(
                new EmailChannel()
        );

        DeliveryReceipt emailReceipt = byEmail.sendWelcome("U-01");
        System.out.println(emailReceipt.channel()
                + " -> " + emailReceipt.detail());

        SmsChannel sms = new SmsChannel();

        // Cùng một đối tượng, nhìn qua hai vai trò.
        DeliveryChannel deliveryRole = sms;
        HealthCheck healthRole = sms;

        NotificationService bySms = new NotificationService(deliveryRole);
        DeliveryReceipt smsReceipt = bySms.sendWelcome("U-02");

        System.out.println(smsReceipt.channel()
                + " -> " + smsReceipt.detail());
        System.out.println("SMS sẵn sàng: " + healthRole.isHealthy());
    }
}

// Dữ liệu gửi đi: recipientId là mã người nhận logic,
// không phải địa chỉ email hay số điện thoại thực.
record Notice(String recipientId, String text) {
    Notice {
        Objects.requireNonNull(recipientId, "recipientId");
        Objects.requireNonNull(text, "text");

        if (recipientId.isBlank() || text.isBlank()) {
            throw new IllegalArgumentException(
                    "Người nhận và nội dung không được rỗng");
        }
    }
}

record DeliveryReceipt(String channel, String detail) {
    DeliveryReceipt {
        Objects.requireNonNull(channel, "channel");
        Objects.requireNonNull(detail, "detail");

        if (channel.isBlank()) {
            throw new IllegalArgumentException("Thiếu tên kênh");
        }
    }
}

/**
 * Hợp đồng mô phỏng gửi thông báo:
 * - notice phải khác null;
 * - trả về DeliveryReceipt khác null khi hoàn tất bình thường;
 * - không sửa notice;
 * - không có hoạt động gửi mạng thật trong bài minh họa.
 *
 * @throws NullPointerException nếu notice là null
 */
interface DeliveryChannel {
    DeliveryReceipt deliver(Notice notice);
}

// Cách thực hiện thứ nhất.
final class EmailChannel implements DeliveryChannel {
    @Override
    public DeliveryReceipt deliver(Notice notice) {
        Objects.requireNonNull(notice, "notice");

        return new DeliveryReceipt(
                "EMAIL",
                notice.recipientId() + ": " + notice.text()
        );
    }
}

// Một vai trò độc lập: kiểm tra sức khỏe.
interface HealthCheck {
    boolean isHealthy();
}

// Một lớp có thể đồng thời đảm nhiệm nhiều vai trò.
final class SmsChannel implements DeliveryChannel, HealthCheck {
    @Override
    public DeliveryReceipt deliver(Notice notice) {
        Objects.requireNonNull(notice, "notice");

        return new DeliveryReceipt(
                "SMS",
                notice.recipientId() + ": " + notice.text()
        );
    }

    @Override
    public boolean isHealthy() {
        return true; // Trạng thái giả lập cho mục đích học tập.
    }
}

// Client phụ thuộc vào hợp đồng, không phụ thuộc EmailChannel/SmsChannel.
final class NotificationService {
    private final DeliveryChannel channel;

    NotificationService(DeliveryChannel channel) {
        this.channel = Objects.requireNonNull(channel, "channel");
    }

    DeliveryReceipt sendWelcome(String recipientId) {
        Notice notice = new Notice(recipientId, "Chào mừng bạn!");
        return channel.deliver(notice);
    }
}
~~~

Chạy:

~~~bash
javac Demo.java
java Demo
~~~

Kết quả:

~~~text
EMAIL -> U-01: Chào mừng bạn!
SMS -> U-02: Chào mừng bạn!
SMS sẵn sàng: true
~~~

Các lớp `EmailChannel` và `SmsChannel` **chưa gửi email hoặc SMS thật**. Mục đích của ví dụ là để thấy cách tách giao diện và cách thực hiện. Trong hệ thống thật, mỗi adapter cần ánh xạ mã người nhận sang địa chỉ phù hợp, xử lý sự cố mạng, timeout và bảo đảm kết quả có ngữ nghĩa đã thống nhất.

### Đọc chương trình qua ba góc nhìn

**Góc nhìn của client:** `NotificationService` chỉ có field kiểu `DeliveryChannel`. Từ đó, nó được phép gọi `deliver(Notice)` mà không cần biết công thức hay quy trình nội bộ của từng kênh.

**Góc nhìn của implementation:** `EmailChannel` và `SmsChannel` khai báo `implements DeliveryChannel`, cung cấp `deliver()` công khai, kiểm tra đầu vào và trả kết quả theo hợp đồng chung.

**Góc nhìn vai trò:** đối tượng `sms` vừa là `DeliveryChannel`, vừa là `HealthCheck`. Hai biến `deliveryRole` và `healthRole` có thể giữ tham chiếu tới **cùng một đối tượng**, nhưng mỗi biến chỉ bộc lộ những thao tác thuộc kiểu giao diện được khai báo cho nó.

Không cần tạo hai đối tượng chỉ vì đối tượng đó có hai vai trò.

~~~mermaid
classDiagram
    class DeliveryChannel {
        <<interface>>
        +deliver(Notice) DeliveryReceipt
    }
    class HealthCheck {
        <<interface>>
        +isHealthy() boolean
    }
    class EmailChannel {
        +deliver(Notice) DeliveryReceipt
    }
    class SmsChannel {
        +deliver(Notice) DeliveryReceipt
        +isHealthy() boolean
    }
    class NotificationService {
        -DeliveryChannel channel
        +sendWelcome(String) DeliveryReceipt
    }
    DeliveryChannel <|.. EmailChannel
    DeliveryChannel <|.. SmsChannel
    HealthCheck <|.. SmsChannel
    NotificationService --> DeliveryChannel : phụ thuộc
~~~

## 3. “Là một vai trò” khác “là một loại thực thể” thế nào?

Một **class** thường chứa cách cài đặt và trạng thái cụ thể. Một **interface** thường nêu ra một khả năng mà nhiều kiểu đối tượng khác nhau có thể đảm nhiệm.

Ví dụ một ứng dụng có thể xác định:

~~~java
interface Printable {
    void print();
}

interface Exportable {
    byte[] export();
}
~~~

Một báo cáo có thể đóng vai `Printable` để in và `Exportable` để xuất file. Một hóa đơn cũng có thể đóng những vai trò đó, dù báo cáo và hóa đơn không cần có chung một lớp cha nghiệp vụ cụ thể.

Ngôn ngữ kiểu thể hiện rất rõ ý tưởng này:

~~~java
void printDocument(Printable document) {
    document.print();
}
~~~

Đoạn phương thức trên minh họa trong một lớp thích hợp. Người gọi chỉ cần một đối tượng làm được vai trò `Printable`. Hàm không cần nhận `Invoice`, `PdfReport`, hoặc kiểm tra từng kiểu bằng chuỗi `if/else`.

Trong Java, interface **cũng là một kiểu dữ liệu (reference type)**. Có thể dùng nó cho kiểu biến, tham số, kiểu trả về, tham số generic hoặc field. Nó không chỉ là tài liệu mô tả kiến trúc.

Ví dụ trong JDK:

| Interface | Vai trò được biểu diễn | Đối tượng cụ thể có thể thực hiện |
|---|---|---|
| `Runnable` | Có hành vi `run()` | Một tác vụ được đưa cho executor/thread |
| `Comparable<T>` | Có thứ tự tự nhiên để so sánh với kiểu phù hợp | `String`, `Integer`, nhiều value object |
| `Comparator<T>` | Có chiến lược so sánh hai giá trị | Comparator theo giá, ngày, tên |
| `Iterable<T>` | Có thể duyệt các phần tử | Một collection hoặc kiểu tùy biến |
| `AutoCloseable` | Có thể đóng tài nguyên | File stream, tài nguyên tùy biến |

Một đối tượng có thể triển khai nhiều interface mà không cần đi theo một cây phân cấp lớp duy nhất.

## 4. Kiểu khai báo quyết định thao tác có thể gọi

Xét phần này của ví dụ:

~~~java
SmsChannel sms = new SmsChannel();

DeliveryChannel channel = sms;
HealthCheck monitor = sms;

channel.deliver(new Notice("U-10", "Xin chào"));
System.out.println(monitor.isHealthy());
~~~

Khi biến `channel` có kiểu `DeliveryChannel`, ta **không thể** viết trực tiếp `channel.isHealthy()`, dù đối tượng thực tế cũng là `SmsChannel`:

~~~java
// channel.isHealthy(); // Lỗi biên dịch: phương thức không thuộc
//                     // kiểu DeliveryChannel.
~~~

Điều này là có chủ đích. Một phần của hệ thống chỉ cần khả năng gửi thì không nên phụ thuộc vô tình vào API giám sát.

Nếu thực sự cần giám sát, truyền một tham số `HealthCheck` riêng hoặc thiết kế dependency phù hợp. Đừng liên tục ép kiểu sang `SmsChannel` để “lấy thêm” các phương thức ngoài hợp đồng; ép kiểu như thế làm client phụ thuộc ngược lại implementation cụ thể.

**Đa hình (polymorphism)** xảy ra tại lời gọi `channel.deliver(...)`: Java thực hiện `deliver()` của class cụ thể đang được tham chiếu, chứ không thực hiện một “thuật toán mặc định” do tên biến quyết định.

## 5. Một contract tốt cần đi xa hơn compiler

Xét trường hợp một lớp khác khai báo:

~~~java
final class BrokenChannel implements DeliveryChannel {
    @Override
    public DeliveryReceipt deliver(Notice notice) {
        return null;
    }
}
~~~

Class này **biên dịch được**, vì trả về `null` là hợp lệ về mặt kiểu tham chiếu. Nhưng nó **vi phạm hợp đồng hành vi** đã nói rõ kết quả không được null.

Hoặc một class có thể:

- Trả receipt cho **người nhận khác** với đầu vào.
- Ném `UnsupportedOperationException` với mọi `Notice` hợp lệ.
- Trả kết quả “đã gửi” dù không thực hiện thao tác được quy định.
- Thay đổi dữ liệu đầu vào trái với cam kết.
- Bất ngờ yêu cầu người gọi truyền một kiểu con bí mật, dù giao diện chấp nhận kiểu cha rộng hơn.

Compiler không tự chứng minh những quy tắc đó.

### Các phần của hợp đồng hành vi

| Thành phần | Ý nghĩa | Ví dụ với `DeliveryChannel` |
|---|---|---|
| **Precondition** | Điều kiện người gọi cần đáp ứng | Truyền `Notice` khác null và hợp lệ |
| **Postcondition** | Cam kết sau khi hoàn thành bình thường | Trả `DeliveryReceipt` khác null |
| **Invariant** | Điều kiện đối tượng phải duy trì | Receipt có tên kênh hợp lệ |
| **Failure contract** | Khi nào, bằng cách nào thông báo lỗi | `NullPointerException` nếu truyền notice null |
| **Side-effect contract** | Trạng thái nào có thể bị tác động | Ví dụ mô phỏng không thực hiện gửi mạng thật |

Đừng tùy tiện thêm vào giao diện các cam kết mà mọi implementation không thể giữ. Chẳng hạn, nếu hứa “`deliver()` luôn hoàn thành trong 1 ms”, một adapter HTTP thực tế rất khó đáp ứng. Hợp đồng nên đủ mạnh để client dùng đúng, nhưng vẫn cho phép nhiều cách triển khai hợp lệ.

### Nguyên tắc thay thế

Một lớp triển khai giao diện phải được sử dụng thay cho các lớp triển khai khác **trong phạm vi hợp đồng** mà không làm client gặp bất ngờ trái với lời hứa chung. Điều này gần với **Liskov Substitution Principle (LSP)**.

Nhưng không có yêu cầu rằng:

- Hai kênh phải dùng cùng thuật toán.
- Hai receipt phải chứa cùng tên kênh.
- Hai provider có cùng hiệu năng nếu hợp đồng không quy định.
- Mọi implementation đều phải được tạo và quản lý theo một cách.

Phần khác biệt chính là chi tiết thực hiện. Phần ổn định là hợp đồng mà client dựa vào.

## 6. Hợp đồng giúp client độc lập với cách gửi

Đối tượng `NotificationService` trong ví dụ chính nhận `DeliveryChannel` qua constructor. Nơi tạo ứng dụng có thể truyền `new EmailChannel()` hoặc `new SmsChannel()`; mã `sendWelcome` chỉ biết `deliver(Notice)` và không cần sửa khi chuyển kênh.

~~~java
DeliveryChannel selected = new SmsChannel();
NotificationService service = new NotificationService(selected);
DeliveryReceipt result = service.sendWelcome("U-04");
~~~

Cách nhận một dependency đã có từ bên ngoài gọi là **constructor injection**. Nó giúp cô lập nơi lựa chọn implementation, nhưng không có nghĩa mỗi class phải tạo thêm một interface. Chọn hợp đồng khi nó phản ánh **khả năng mà client thực sự cần**; bài *Lập trình dựa trên giao diện* sẽ phân tích hướng phụ thuộc, composition root và fake test cụ thể hơn.

## 7. Một vai trò không nên hứa những khả năng không có

Nếu `DeliveryChannel` còn buộc mọi implementation phải `revoke(messageId)`, một kênh không thể thu hồi tin đã gửi sẽ phải viết method vô nghĩa hoặc luôn ném lỗi. Tốt hơn là tách hai vai trò độc lập:

~~~java
interface Sender {
    DeliveryReceipt deliver(Notice notice);
}

interface Revocable {
    void revoke(String messageId);
}
~~~

Một lớp chỉ nên `implements Revocable` khi có thể thực sự đáp ứng hợp đồng hủy. Client chỉ cần gửi thì yêu cầu `Sender`; client cần thu hồi mới yêu cầu `Revocable`. Đây là ý tưởng của **Interface Segregation Principle (ISP)**: giới hạn phụ thuộc theo nhu cầu, không phải tách máy móc một phương thức thành một interface. Bài *Giao diện nhỏ và phân tách vai trò* có quy trình refactor hợp đồng quá rộng.

## 8. Vai trò và họ lớp có triển khai chung là hai trục khác nhau

| Câu hỏi | Interface | Abstract class |
|---|---|---|
| Mục tiêu chủ yếu | Nêu hợp đồng hành vi của một vai trò | Chia sẻ trạng thái, constructor hoặc thuật toán của một họ lớp |
| Khả năng kết hợp | Class `implements` nhiều interface | Class trực tiếp `extends` tối đa một superclass |
| Trạng thái instance | Không khai báo field instance | Có thể giữ field instance và invariant |
| Constructor | Không có | Có |

Ví dụ `Invoice` và `AnalyticsReport` cùng có thể `implements Exportable` dù không có cùng superclass nghiệp vụ. Nếu một nhóm exporter thực sự cần cùng bộ nhớ đệm và constructor cấu hình, nhóm đó có thể dùng một abstract base class **đồng thời** implement `Exportable`; exporter khác có thể implement trực tiếp. Lựa chọn giữa kế thừa và composition được minh họa trọn vẹn ở bài *Chọn giao diện hay lớp trừu tượng*.

## 9. Một số thành viên Java interface có sẵn cách thực hiện

Mặc dù phần chính của `DeliveryChannel` là phương thức `public abstract` `deliver`, Java 17 còn cho interface chứa:

~~~java
interface Greeter {
    String greet(String name); // Ngầm public abstract

    default String greetEveryone() {
        return greet("mọi người");
    }

    static boolean hasName(String name) {
        return name != null && !name.isBlank();
    }

    private static String normalize(String name) {
        return name.strip();
    }
}
~~~

`default` có thân dùng chung cho implementation; `static` được gọi qua `Greeter.hasName(...)`, không phải instance; `private` là helper chỉ dùng **bên trong interface** (ví dụ trên chưa dùng đến `normalize`). Field trong interface luôn ngầm `public static final`, **không** tạo trạng thái riêng cho từng object. Nếu hai interface độc lập có default method cùng chữ ký, class có thể cần tự override để giải quyết. Bài *Thành viên mặc định và giới hạn tùy ngôn ngữ* giải thích đầy đủ modifier, xung đột, giới hạn `Object` và khác biệt phiên bản.

## 10. Interface như một vai trò có thể truyền vào callback

Một interface chỉ có **một abstract method** có thể được khai báo là *functional interface* và triển khai bằng lambda.

Ví dụ:

~~~java
@FunctionalInterface
interface PriceRule {
    long apply(long originalPriceVnd);
}
~~~

Sử dụng:

~~~java
PriceRule tenPercentOff = original -> original * 90 / 100;

System.out.println(tenPercentOff.apply(200_000)); // 180000
~~~

Biến `tenPercentOff` đảm nhiệm vai trò `PriceRule`, mặc dù ta không viết một class named implementation bằng tay. Lambda được Java chuyển thành một đối tượng có thể thực hiện hợp đồng functional interface.

Trong ví dụ này, công thức chỉ minh họa giảm giá 10% với số nguyên dương đủ nhỏ để không tràn `long`; hợp đồng tài chính thực tế phải nêu rõ kiểm tra số âm, làm tròn và xử lý overflow.

Các interface như `Runnable`, `Comparator<T>`, `Predicate<T>`, `Function<T,R>` là những ví dụ quen thuộc về cách **vai trò** cho phép truyền hành vi qua tham số.

`@FunctionalInterface` giúp compiler kiểm tra rằng interface vẫn có đúng một abstract method theo quy tắc áp dụng. Annotation hữu ích nhưng không bắt buộc để Java nhận diện functional interface hợp lệ.

## 11. Một hợp đồng rõ cho phép kiểm tra client bằng fake

Không cần gửi SMS thật để biết `NotificationService` tạo `Notice` đúng. Một test double có thể lưu thông báo nhận được:

~~~java
final class RecordingChannel implements DeliveryChannel {
    Notice last;

    @Override
    public DeliveryReceipt deliver(Notice notice) {
        last = java.util.Objects.requireNonNull(notice);
        return new DeliveryReceipt("FAKE", "Đã nhận");
    }
}

RecordingChannel fake = new RecordingChannel();
NotificationService service = new NotificationService(fake);
service.sendWelcome("U-03");
if (!"U-03".equals(fake.last.recipientId())) {
    throw new AssertionError("Sai người nhận");
}
~~~

Đoạn kiểm thử dùng lại `Notice`, `DeliveryReceipt` và `NotificationService` ở ví dụ chính. Nó chỉ xác nhận **client gọi đúng hợp đồng**, không chứng minh adapter email/SMS thật hoạt động. Phần kiểm thử nhiều implementation cùng một hợp đồng và phát hiện vi phạm semantics là trọng tâm của bài *Thay thế cách thực hiện mà giữ hợp đồng*.

## 12. Tiến hóa interface là thay đổi lời hứa với nhiều bên

Khi một interface được nhiều module sử dụng, việc thay đổi `deliver(Notice)` thành `deliver(String)` có thể khiến các class triển khai và client không biên dịch. Thêm abstract method cũng thường buộc các concrete implementer bổ sung mã; thêm default method giảm một số tác động về nguồn nhưng vẫn có thể gây xung đột và thay đổi hành vi.

Nguy hiểm hơn là **giữ nguyên chữ ký nhưng đổi ý nghĩa kết quả**. Ví dụ, nếu `DeliveryReceipt` trước đây có nghĩa *nhà cung cấp đã tiếp nhận*, không được âm thầm đổi thành *người nhận đã xem* mà vẫn gọi đó là cùng một cam kết. Caller có thể đưa ra quyết định sai dù mọi mã vẫn biên dịch.

Khi thay kênh, hãy giữ nhất quán điều kiện đầu vào, kết quả, lỗi và side effects đã hứa. Nếu cần đổi semantics, hãy công bố phiên bản hợp đồng mới hoặc chiến lược chuyển đổi rõ ràng, đồng thời chạy kiểm thử hành vi của mỗi implementation.

## 13. Khi nào không nên tạo interface mới?

Interface hữu ích nhưng cũng có chi phí bảo trì. Hãy cân nhắc không tạo thêm một interface nếu:

- Chỉ có một class đơn giản và chưa có ranh giới phụ thuộc cần ổn định.
- Interface phản chiếu gần như mọi public method của class mà không tạo ra vai trò rõ ràng.
- Các consumer liên tục ép kiểu sang implementation cụ thể để dùng những method bị bỏ ngoài interface.
- Interface chứa nhiều phương thức chỉ có một phần implementation hỗ trợ.
- API còn thay đổi nhanh, chưa rõ hợp đồng ổn định cho consumer.

Ngược lại, interface đặc biệt phù hợp với **adapter tích hợp bên ngoài, chiến lược có thể thay thế, plugin, callback, cộng tác giữa module và dependency injection**.

Một tiêu chí thực dụng: mô tả interface bằng một câu **“đối tượng này có thể…”**. Nếu câu ấy rõ ràng, có người dùng cụ thể và có cam kết kiểm chứng được, interface có cơ sở tốt để tồn tại.

## 14. Tình huống luyện tập

### Tình huống 1 — Thiết kế theo vai trò

Một hệ thống có `PdfReport`, `Invoice`, `EmailMessage`. `PdfReport` có thể in và xuất file; `Invoice` có thể in; `EmailMessage` có thể gửi. Nên ép tất cả `extends Document` có mọi phương thức `print()`, `export()`, `send()` không?

**Gợi ý:** không nhất thiết. Có thể dùng các interface theo vai trò `Printable`, `Exportable`, `Sendable`; mỗi lớp chỉ `implements` những khả năng thật sự cung cấp.

### Tình huống 2 — Nhận diện vi phạm hợp đồng

~~~java
class NullChannel implements DeliveryChannel {
    @Override
    public DeliveryReceipt deliver(Notice notice) {
        return null;
    }
}
~~~

**Đáp án:** class có thể biên dịch nhưng vi phạm hợp đồng `deliver` phải trả receipt khác null khi hoàn thành bình thường.

### Tình huống 3 — Vai trò khác kiểu thực tế

~~~java
SmsChannel sms = new SmsChannel();
DeliveryChannel sender = sms;
HealthCheck health = sms;
~~~

Hỏi: có bao nhiêu đối tượng `SmsChannel` được tạo? Có thể gọi `sender.isHealthy()` trực tiếp không?

**Đáp án:** một đối tượng; `sender.isHealthy()` không biên dịch được vì phương thức không thuộc interface `DeliveryChannel`, dù `health.isHealthy()` hợp lệ.

### Tình huống 4 — Client phụ thuộc implementation

~~~java
class Job {
    private final EmailChannel channel = new EmailChannel();
}
~~~

Hỏi: muốn kiểm thử `Job` bằng kênh giả thì nên thay đổi hướng phụ thuộc ra sao?

**Gợi ý:** cho `Job` nhận `DeliveryChannel` qua constructor; nơi tạo `Job` cung cấp `EmailChannel` thật hoặc `RecordingChannel` giả theo môi trường.

### Tình huống 5 — Interface quá rộng

Nếu mọi class thực hiện `StorageManager` phải có cả `upload()`, `read()`, `delete()`, nhưng một module chỉ được phép đọc, thiết kế nào dễ đảm bảo quyền hạn hơn?

**Gợi ý:** một vai trò `ReadableStorage` chỉ công khai `read()`, và các vai trò ghi/xóa chỉ được cấp cho nơi có quyền tương ứng. Phân tách vai trò cũng giúp giảm API mà code sử dụng có thể gọi nhầm.

### Tình huống 6 — Dùng interface để biểu thị thuật toán

Muốn sắp xếp danh sách nhân viên theo tên hoặc lương, bạn có cần sửa class `Employee` mỗi khi đổi tiêu chí?

**Gợi ý:** không. Có thể truyền một `Comparator<Employee>` khác nhau vào thao tác sắp xếp. `Comparator` biểu thị **vai trò chiến lược so sánh**, còn class `Employee` biểu thị thực thể dữ liệu. Khi tiêu chí đổi, client chọn một implementation hoặc lambda khác.

## Ghi nhớ khi thiết kế Java OOP

Hãy chọn giao diện bằng cách bắt đầu từ **người sử dụng**: họ cần đối tượng làm điều gì, đầu vào hợp lệ ra sao, kết quả nào có thể tin cậy và lỗi được xử lý như thế nào? Sau đó cho các class triển khai những hành vi đó bằng chi tiết riêng.

Một interface tốt mang tên một **vai trò có ý nghĩa**, bộc lộ các thao tác đủ nhỏ để client sử dụng độc lập, và có một **hợp đồng hành vi rõ ràng**. Class implement giao diện được thay đổi thuật toán, cấu trúc dữ liệu hoặc nhà cung cấp, nhưng phải tiếp tục thực hiện những cam kết mà client dựa vào. Nhờ thế, thiết kế OOP linh hoạt hơn mà vẫn dễ đọc, dễ thử nghiệm và có thể mở rộng có kiểm soát.
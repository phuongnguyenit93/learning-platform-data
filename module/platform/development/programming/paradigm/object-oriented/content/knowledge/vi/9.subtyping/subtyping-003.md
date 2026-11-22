# Tương thích kiểu theo tên và theo cấu trúc trong Java OOP

Khi một phương thức nhận tham số kiểu `MessageSender`, đối tượng nào được phép truyền vào? Liệu chỉ cần đối tượng có phương thức `send(...)` đúng tên và tham số là đủ, hay lớp của nó phải **khai báo quan hệ** với `MessageSender`?

Đó là khác biệt giữa **nominal typing** (tương thích kiểu theo tên/quan hệ khai báo) và **structural typing** (tương thích kiểu theo cấu trúc). Java sử dụng **nominal subtyping** cho quan hệ kiểu con giữa class/interface: để một kiểu được xem là kiểu con của interface/lớp khác, phải có quan hệ kế thừa hoặc triển khai được khai báo trong hệ phân cấp kiểu. Hai lớp tình cờ có cùng các phương thức **không tự động** tương thích.

## 1. Hai cách xác định kiểu có tương thích

**Theo tên (nominal)**: Java xem xét **danh tính kiểu và quan hệ kế thừa/triển khai đã khai báo**. Ví dụ `EmailSender implements MessageSender` nên `EmailSender` là kiểu con của `MessageSender`.

**Theo cấu trúc (structural)**: trong một hệ thống kiểu có cơ chế này, một giá trị có thể được chấp nhận khi nó cung cấp **tập thành viên phù hợp** mà nơi sử dụng đòi hỏi, dù không khai báo trực tiếp quan hệ `implements`. Chi tiết kiểm tra cấu trúc phụ thuộc từng ngôn ngữ, như kiểu tham số, kiểu trả về, quyền truy cập và các quy tắc khác.

| Tiêu chí | Theo tên (nominal) | Theo cấu trúc (structural) |
| --- | --- | --- |
| Dựa vào | Danh tính kiểu và quan hệ subtype được khai báo | Hình dạng/các thành viên mà kiểu cung cấp |
| Hai lớp có cùng phương thức | Chưa chắc tương thích | Có thể tương thích nếu đáp ứng hợp đồng cấu trúc |
| Quan hệ với hợp đồng | Thường được ghi rõ như `implements`, `extends` | Có thể được xác định ngầm khi kiểm tra kiểu |
| Ví dụ ngôn ngữ | Java với quan hệ class/interface | TypeScript có hệ thống kiểu phần lớn theo cấu trúc; interface trong Go được thỏa mãn ngầm |
| Ưu điểm | Hợp đồng công khai, chủ đích rõ ở định nghĩa kiểu | Linh hoạt với những kiểu đã có hình dạng phù hợp |
| Điểm cần cân nhắc | Phải khai báo/gắn kết kiểu, hoặc cần adapter | Giống hình dạng chưa chắc giống ngữ nghĩa |

**Lưu ý:** “tương thích kiểu” nói chung còn bao gồm những quy tắc khác như chuyển kiểu nguyên thủy, boxing/unboxing hay generic. Bài này tập trung vào **tương thích kiểu con giữa các lớp và interface**, không khẳng định mọi phép gán hợp lệ trong Java đều là quan hệ kế thừa.

## 2. Java không chấp nhận chỉ vì phương thức trùng chữ ký

Xét mã Java sau:

~~~java
interface MessageSender {
    void send(String receiver, String content);
}

class EmailSender implements MessageSender {
    @Override
    public void send(String receiver, String content) {
        System.out.println("Email đến " + receiver + ": " + content);
    }
}

// Cùng public method, cùng tham số/kiểu trả về, nhưng KHÔNG implements.
class LegacySmsSdk {
    public void send(String receiver, String content) {
        System.out.println("SMS đến " + receiver + ": " + content);
    }
}
~~~

Cả `EmailSender` và `LegacySmsSdk` đều có `public void send(String, String)`, nhưng chỉ `EmailSender` được công nhận là **kiểu con của `MessageSender`**:

~~~java
MessageSender sender = new EmailSender();  // Hợp lệ.

// LỖI BIÊN DỊCH:
// MessageSender sender2 = new LegacySmsSdk();
~~~

Lý do: định nghĩa `LegacySmsSdk` không có quan hệ `implements MessageSender` (trực tiếp hay được kế thừa từ một kiểu cha phù hợp). Java không “so hình dạng” từng class để suy ra interface này được triển khai chỉ vì phương thức tương tự.

~~~mermaid
classDiagram
    class MessageSender {
        <<interface>>
        +send(String,String) void
    }
    class EmailSender {
        +send(String,String) void
    }
    class LegacySmsSdk {
        +send(String,String) void
    }
    MessageSender <|.. EmailSender
~~~

Đường nét đứt với tam giác biểu thị `EmailSender implements MessageSender`. `LegacySmsSdk` đứng độc lập dù có chữ ký phương thức giống. Đây là điểm phân biệt trực quan giữa **“có hình dạng tương tự”** và **“đã xác lập quan hệ kiểu con”**.

## 3. Ví dụ hoàn chỉnh: dùng adapter để kết nối lớp không cùng hệ kiểu

Trong dự án thực tế, một SDK bên thứ ba có thể đã tồn tại và ta không được sửa mã của nó để thêm `implements MessageSender`. Ta có thể viết một **adapter** triển khai interface của ứng dụng rồi ủy quyền thao tác cho SDK.

Lưu đoạn sau vào tệp `NominalTypingDemo.java`, chạy bằng **Java 11+**:

~~~java
import java.util.List;
import java.util.Objects;

public class NominalTypingDemo {

    interface MessageSender {
        void send(String receiver, String content);
    }

    static final class EmailSender implements MessageSender {
        @Override
        public void send(String receiver, String content) {
            System.out.println("EMAIL -> " + receiver + ": " + content);
        }
    }

    // Giả lập thư viện ngoài có method phù hợp, nhưng không implements.
    static final class LegacySmsSdk {
        public void send(String receiver, String content) {
            System.out.println("SMS -> " + receiver + ": " + content);
        }
    }

    // Cầu nối: công bố hợp đồng của ứng dụng, dùng lại SDK sẵn có.
    static final class SmsSenderAdapter implements MessageSender {
        private final LegacySmsSdk sdk;

        SmsSenderAdapter(LegacySmsSdk sdk) {
            this.sdk = Objects.requireNonNull(sdk, "sdk");
        }

        @Override
        public void send(String receiver, String content) {
            sdk.send(receiver, content);
        }
    }

    static final class NotificationService {
        void notifyCustomer(MessageSender sender,
                            String receiver, String content) {
            Objects.requireNonNull(sender, "sender");
            if (receiver == null || receiver.isBlank()
                    || content == null || content.isBlank()) {
                throw new IllegalArgumentException(
                        "Người nhận/nội dung phải hợp lệ");
            }
            sender.send(receiver, content);
        }
    }

    public static void main(String[] args) {
        MessageSender email = new EmailSender();
        LegacySmsSdk externalSdk = new LegacySmsSdk();
        MessageSender sms = new SmsSenderAdapter(externalSdk);

        NotificationService service = new NotificationService();

        service.notifyCustomer(email, "KH-01", "Đơn đã xác nhận");
        service.notifyCustomer(sms, "KH-02", "Đơn đang giao");

        List<MessageSender> channels = List.of(email, sms);
        for (MessageSender channel : channels) {
            channel.send("KH-03", "Khuyến mãi");
        }

        // KHÔNG BIÊN DỊCH, dù LegacySmsSdk có đúng method send:
        // MessageSender incompatible = externalSdk;
    }
}
~~~

Chạy:

~~~bash
javac NominalTypingDemo.java
java NominalTypingDemo
~~~

Kết quả:

~~~text
EMAIL -> KH-01: Đơn đã xác nhận
SMS -> KH-02: Đơn đang giao
EMAIL -> KH-03: Khuyến mãi
SMS -> KH-03: Khuyến mãi
~~~

Trong ví dụ này:

1. `NotificationService` yêu cầu tham số **`MessageSender`**, một hợp đồng của ứng dụng.
2. `EmailSender` trực tiếp triển khai hợp đồng ấy.
3. `LegacySmsSdk` cung cấp chức năng tương tự nhưng **không phải một `MessageSender`** trong hệ kiểu Java.
4. `SmsSenderAdapter` là một kiểu con thật sự của `MessageSender` và gọi `sdk.send(...)` để thực thi.
5. Dù `NotificationService` không biết đối tượng nhận là loại nào, lời gọi `send(...)` được phân phối tới implementation runtime tương ứng (**đa hình**).

~~~mermaid
classDiagram
    class MessageSender {
        <<interface>>
        +send(String,String) void
    }
    class EmailSender
    class SmsSenderAdapter {
        -sdk LegacySmsSdk
        +send(String,String) void
    }
    class LegacySmsSdk {
        +send(String,String) void
    }
    class NotificationService {
        +notifyCustomer(MessageSender,String,String) void
    }

    MessageSender <|.. EmailSender
    MessageSender <|.. SmsSenderAdapter
    SmsSenderAdapter --> LegacySmsSdk : delegates
    NotificationService --> MessageSender : depends on
~~~

**Adapter không làm `LegacySmsSdk` trở thành subtype.** Nó tạo ra một **đối tượng adapter** có subtype relationship hợp lệ và giữ tham chiếu tới đối tượng SDK. Nhờ đó không phải sửa thư viện ngoài, đồng thời ý nghĩa của hợp đồng `MessageSender` vẫn được kiểm soát ở ranh giới ứng dụng.

## 4. Structural typing sẽ nhìn tình huống này khác thế nào?

Để đối chiếu nguyên lý, đây là một ví dụ **TypeScript (không phải Java)**:

~~~typescript
type Sender = {
    send(receiver: string, content: string): void;
};

class LegacySmsSdk {
    send(receiver: string, content: string): void {
        console.log(receiver, content);
    }
}

const sender: Sender = new LegacySmsSdk(); // Hợp lệ theo cấu trúc
sender.send("KH-01", "Xin chào");
~~~

`LegacySmsSdk` không cần khai báo `implements Sender` ở đây, vì kiểu của instance thỏa mãn hình dạng `Sender` mà TypeScript kiểm tra.

Trong Java, đoạn tương ứng sẽ **không** biên dịch nếu thiếu quan hệ subtype khai báo. Đây là khác biệt về **quy tắc hệ kiểu**, không phải chuyện cú pháp `implements` chỉ để trang trí.

### “Giống cấu trúc” chưa chắc “giống ý nghĩa”

Hai lớp đều có `void send(String, String)`, nhưng một phương thức có thể là gửi thông báo, phương thức khác lại gửi dữ liệu vào hệ thống kiểm toán. Các chữ ký trùng nhau **không bảo đảm** ngữ nghĩa, hợp đồng lỗi, bảo mật, thứ tự tham số hay hiệu ứng phụ giống nhau.

Nominal typing buộc lớp chủ động nhận một vai trò qua quan hệ được khai báo. Structural typing giúp tích hợp linh hoạt nhưng **vẫn cần thiết kế hợp đồng ngữ nghĩa rõ ràng**. Không hệ kiểu nào có thể tự chứng minh rằng một lời gọi thực hiện đúng nghiệp vụ chỉ qua tên và chữ ký.

## 5. Kiểu con Java được xác định như thế nào?

Các trường hợp cốt lõi:

~~~java
class Animal {
    void eat() {}
}

class Dog extends Animal {
    void bark() {}
}

interface RunnableTask {
    void run();
}

class ReportTask implements RunnableTask {
    @Override
    public void run() {}
}
~~~

| Phép gán | Kết quả | Lý do |
| --- | --- | --- |
| `Animal animal = new Dog();` | Hợp lệ | `Dog extends Animal` |
| `RunnableTask task = new ReportTask();` | Hợp lệ | `ReportTask implements RunnableTask` |
| `Object obj = new Dog();` | Hợp lệ | Các class Java kế thừa từ `Object` trực tiếp/gián tiếp |
| `Dog dog = new Animal();` | Không hợp lệ | Không phải mọi `Animal` là `Dog` |
| `RunnableTask task = new Dog();` | Không hợp lệ | `Dog` không được khai báo là subtype của `RunnableTask` |
| `Animal a = new ReportTask();` | Không hợp lệ | Không có quan hệ kiểu con giữa hai class |

**Subtype là quan hệ có hướng:** nếu `Dog extends Animal`, từ `Dog` có thể mở rộng lên `Animal` (*upcast*) mà không cần ép tường minh. Chiều ngược lại không tự hợp lệ.

Quan hệ được truyền qua các cấp:

~~~java
interface Identifiable {
    String id();
}

interface Named extends Identifiable {
    String name();
}

class Customer implements Named {
    @Override
    public String id() { return "C01"; }

    @Override
    public String name() { return "An"; }
}
~~~

~~~java
Named a = new Customer();
Identifiable b = new Customer(); // Hợp lệ qua Named extends Identifiable
~~~

`Customer` không cần viết trực tiếp `implements Identifiable` bởi nó đã khai báo `implements Named` và `Named` kế thừa `Identifiable`. **Tương thích theo tên không có nghĩa là chỉ tìm đúng chữ `implements X` trên dòng class hiện tại**; Java tính cả quan hệ subtype hợp lệ qua chuỗi kế thừa class và interface.

Cũng có trường hợp implementation được kế thừa từ superclass mà subclass khai báo `implements` interface:

~~~java
interface Greeter {
    String greet();
}

class BaseGreeter {
    public String greet() {
        return "Xin chào";
    }
}

class GreeterAdapter extends BaseGreeter implements Greeter {
    // Không cần viết lại greet() vì đã kế thừa implementation public.
}
~~~

`GreeterAdapter` là `Greeter` nhờ **khai báo `implements`**, dù bản thân nó không ghi đè `greet()` một lần nữa.

## 6. Hai interface có phương thức giống nhau vẫn là hai kiểu khác nhau

~~~java
interface Storable {
    void save(String value);
}

interface Auditable {
    void save(String value);
}

class FileStore implements Storable {
    @Override
    public void save(String value) {
        System.out.println("Lưu: " + value);
    }
}
~~~

~~~java
Storable s = new FileStore(); // Đúng.

// Auditable a = new FileStore(); // Sai: không implements Auditable.
~~~

Tuy `Storable` và `Auditable` có cùng một phương thức, Java vẫn coi chúng là **hai danh tính kiểu độc lập**. Nếu một lớp thực sự muốn đáp ứng cả hai:

~~~java
class DualStore implements Storable, Auditable {
    @Override
    public void save(String value) {
        System.out.println(value);
    }
}
~~~

Một implementation `save(String)` có thể thỏa cả hai interface vì chữ ký trùng và tương thích, nhưng quan hệ với **cả hai interface được khai báo rõ ràng**.

Điểm này giúp tránh hiểu nhầm: **cùng cấu trúc không tạo quan hệ subtype; nhưng khi quan hệ subtype đã tồn tại, một implementation có thể đáp ứng các hợp đồng có chữ ký tương thích**.

## 7. Java có “structural typing” qua lambda và method reference không?

Java hỗ trợ **functional interface**: interface có một phương thức trừu tượng chức năng (SAM). Lambda và method reference có thể được chuyển thành giá trị của **kiểu functional interface đích** nếu chữ ký và quy tắc liên quan phù hợp.

~~~java
@FunctionalInterface
interface TextFormatter {
    String format(String raw);
}

class PrefixFormatter {
    String prefix(String raw) {
        return "[INFO] " + raw;
    }
}
~~~

~~~java
PrefixFormatter legacy = new PrefixFormatter();

// LỖI: PrefixFormatter không implements TextFormatter.
// TextFormatter a = legacy;

// Hợp lệ: method reference được chuyển theo target type TextFormatter.
TextFormatter b = legacy::prefix;

System.out.println(b.format("Đã lưu")); // [INFO] Đã lưu
~~~

Điều này trông giống “chỉ cần phương thức có hình dạng phù hợp”, nhưng **không phải** Java tự động coi `PrefixFormatter` là subtype của `TextFormatter`. Thay vào đó, Java tạo/biểu diễn một giá trị của **functional interface đích** với hành vi gọi tới phương thức được tham chiếu.

Một lambda cũng cần **target type**:

~~~java
TextFormatter upper = text -> text.toUpperCase();

System.out.println(upper.format("java")); // JAVA
~~~

Lambda Java không có kiểu class tự chứa độc lập như một đối tượng `PrefixFormatter` được gán theo cấu trúc. Compiler cần một functional interface tương ứng làm đích, ví dụ khi gán biến hoặc truyền tham số.

**Kết luận đúng:** method reference/lambda làm việc với **kiểu hàm có cấu trúc chữ ký phù hợp** ở vị trí chuyển đổi, nhưng quan hệ class/interface thông thường của Java vẫn chủ yếu là **nominal**.

## 8. Cần phân biệt subtype với “có thể ép kiểu”

Một phép ép kiểu tường minh **không tạo ra** quan hệ subtype còn thiếu.

~~~java
interface MessageSender {
    void send(String receiver, String content);
}

class LegacySmsSdk {
    public void send(String receiver, String content) { }
}
~~~

Dòng sau có thể khiến compiler chấp nhận cú pháp khi ép qua `Object`, nhưng thất bại ở runtime:

~~~java
LegacySmsSdk legacy = new LegacySmsSdk();

// Biên dịch được vì ép qua Object, nhưng ném ClassCastException:
MessageSender sender = (MessageSender) (Object) legacy;
~~~

Đừng dùng cast như một cách bắt Java bỏ qua hợp đồng nominal. **Adapter** mới là giải pháp đúng nếu cần dùng một lớp đã có API phù hợp trong một giao diện của ứng dụng.

Ngược lại, một tham chiếu lớp cha thực sự giữ object lớp con thì có thể downcast an toàn khi đã kiểm tra:

~~~java
Animal animal = new Dog();

if (animal instanceof Dog) {
    Dog dog = (Dog) animal;
    dog.bark();
}
~~~

`instanceof` kiểm tra khả năng tương thích **theo kiểu thực tế** của đối tượng, không kiểm tra xem nó có tự nhiên sở hữu một tập tên phương thức nào đó hay không.

## 9. Generics: cùng quan hệ subtype nhưng collection chưa chắc gán được

Nếu `EmailSender implements MessageSender`, thì:

~~~java
EmailSender email = new EmailSender();
MessageSender sender = email; // Đúng.
~~~

Nhưng điều đó **không kéo theo**:

~~~java
List<EmailSender> emails = List.of(new EmailSender());

// LỖI: generic List<T> trong Java bất biến (invariant).
// List<MessageSender> senders = emails;
~~~

Nếu cho phép gán trên, người gọi có thể tưởng mình được thêm `SmsSenderAdapter` vào một `List<EmailSender>`, gây phá vỡ tính an toàn kiểu.

Khi muốn một phương thức **chỉ đọc danh sách phần tử thuộc một subtype của `MessageSender`**, có thể dùng wildcard:

~~~java
static void announce(
        List<? extends MessageSender> senders, String message) {
    for (MessageSender sender : senders) {
        sender.send("KH-01", message);
    }
}
~~~

~~~java
List<EmailSender> emails = List.of(new EmailSender());
announce(emails, "Thông báo");
~~~

`? extends MessageSender` cho phép **đọc ra** dưới kiểu `MessageSender` nhưng không thể thêm một `MessageSender` tùy ý vào danh sách này (ngoại trừ `null` theo quy tắc của Java). Đây là cách variance ở generics hoạt động, **khác với** việc xác định quan hệ nominal/structural của chính `EmailSender` và `MessageSender`.

Để dùng `List` trong các đoạn mã rời của phần này, cần `import java.util.List;` và các lớp/interface mẫu phải được định nghĩa trong phạm vi phù hợp.

## 10. Cùng hình dạng dữ liệu không làm hai record trở thành cùng kiểu

Với Java **17+**, hai `record` có thành phần cùng tên/cùng kiểu vẫn là hai **kiểu nominal khác nhau**:

~~~java
record Point(int x, int y) {}
record Position(int x, int y) {}

Point point = new Point(3, 5);
Position position = new Position(3, 5);

// LỖI BIÊN DỊCH:
// Position p = point;

System.out.println(point.equals(position)); // false
~~~

`Point` và `Position` không cùng class, không có quan hệ subtype thích hợp. Dù dữ liệu có cấu trúc giống nhau, chúng có thể mang **ý nghĩa miền nghiệp vụ khác nhau**: tọa độ hình học, vị trí trên bản đồ, v.v.

Có thể chuyển đổi **tường minh** khi thực sự muốn:

~~~java
Position p = new Position(point.x(), point.y());
~~~

Đó là **tạo một object khác bằng ánh xạ dữ liệu**, không phải gán tham chiếu theo subtype. Thao tác này cần được quyết định rõ thay vì tự động coi hai khái niệm bằng nhau chỉ vì cùng field.

## 11. Thiết kế API dựa trên hợp đồng nominal

Một API Java thường rõ ràng hơn khi kiểu tham số bộc lộ **năng lực mà nó cần**, thay vì yêu cầu một class cụ thể hoặc dựa vào reflection kiểm tra phương thức cùng tên.

Ví dụ:

~~~java
interface Exporter {
    void export(String fileName);
}

class ReportService {
    private final Exporter exporter;

    ReportService(Exporter exporter) {
        this.exporter = exporter;
    }

    void createReport() {
        // Tạo dữ liệu báo cáo...
        exporter.export("report.csv");
    }
}
~~~

`ReportService` chỉ cần biết đối tượng được truyền vào **tuân thủ hợp đồng `Exporter`**. Cách triển khai có thể là ghi CSV, xuất PDF hay chuyển tới một dịch vụ khác, miễn hành vi phù hợp. Hợp đồng nominal này hỗ trợ dependency injection và đa hình.

Nếu thư viện ngoài có phương thức tương tự nhưng không thực hiện `Exporter`, dùng **adapter** hoặc **method reference** (nếu hợp đồng là functional interface và chữ ký phù hợp) có thể là những cách tích hợp:

~~~java
// Ví dụ minh họa khi có một object legacy với phương thức
// void save(String fileName):
Exporter exporter = legacy::save;
~~~

Bản thân `legacy` **không trở thành subtype của `Exporter`**. Biểu thức method reference cung cấp một giá trị đáp ứng functional interface đích.

Không nên lạm dụng reflection để gọi method chỉ dựa vào tên/đối số trong những nơi đã biết hợp đồng Java. Reflection có thể hữu ích trong framework hoặc plugin đặc thù, nhưng bỏ qua nhiều kiểm tra tĩnh, phức tạp hơn và dễ lỗi runtime.

## 12. Các trường hợp dễ nhầm

| Nhận định | Đúng hay sai? | Giải thích |
| --- | --- | --- |
| “Hai class có cùng public method thì gán cho nhau được” | **Sai** trong Java thông thường | Thiếu quan hệ subtype nominal |
| “Class phải ghi trực tiếp `implements I` mới là subtype của I” | **Sai** | Có thể kế thừa quan hệ qua lớp/interface cha |
| “Một implementation kế thừa từ superclass có thể đáp ứng interface” | **Đúng** | Nếu class khai báo/nhận quan hệ interface hợp lệ và method kế thừa phù hợp |
| “Lớp implements hai interface cùng method phải viết hai bản sao method” | **Sai** | Một implementation tương thích đủ đáp ứng cả hai |
| “Lambda làm Java tự coi mọi object cùng hình dạng là subtype” | **Sai** | Lambda/method reference có chuyển đổi theo target functional interface |
| “Ép kiểu có thể biến class không implements thành interface” | **Sai** | Runtime vẫn kiểm tra kiểu, có thể ném `ClassCastException` |
| “`List<Sub>` là `List<Super>` khi Sub extends Super” | **Sai** | Generic Java mặc định bất biến |
| “Hai record có field giống nhau luôn là cùng kiểu” | **Sai** | Record vẫn có danh tính kiểu riêng |
| “Tương thích kiểu theo tên chỉ cần tên class viết giống nhau” | **Sai** | Là danh tính kiểu và quan hệ kiểu, không phải so chuỗi tên đơn giản |

## 13. Bài luyện tập có lời giải

**Câu 1.** Điều gì xảy ra?

~~~java
interface Readable {
    String read();
}

class FileSource {
    public String read() {
        return "Dữ liệu";
    }
}

// Readable input = new FileSource();
~~~

**Đáp án:** Dòng gán bị lỗi biên dịch. `FileSource` có phương thức cùng chữ ký nhưng không được khai báo là subtype của `Readable`. Có thể dùng một adapter `implements Readable` hoặc method reference `Readable input = new FileSource()::read;` vì `Readable` là functional interface.

**Câu 2.** Nếu `class SecureFileSource extends FileSource implements Readable { }`, lớp này có bắt buộc override `read()` không?

**Đáp án:** Không. `SecureFileSource` thỏa quan hệ nominal qua `implements Readable`, và thừa hưởng một implementation `public read()` phù hợp từ `FileSource`.

**Câu 3.** Vì sao `MessageSender sender = new SmsSenderAdapter(sdk)` hợp lệ dù `sdk` không implements `MessageSender`?

**Đáp án:** Đối tượng **được gán** là instance của `SmsSenderAdapter`, class thực sự `implements MessageSender`. Adapter giữ `sdk` bên trong và ủy quyền, không thay danh tính kiểu của `sdk`.

**Câu 4.** `interface A { void go(); }`, `interface B { void go(); }`, `class X implements A { public void go(){} }`. Có thể gán `B b = new X();` không?

**Đáp án:** Không. Hai interface cùng hình dạng nhưng không có quan hệ subtype với `X` theo kiểu `B`. Nếu `X` thực hiện cả hai, cần khai báo quan hệ đó (trực tiếp hoặc qua hierarchy phù hợp).

**Câu 5.** Tại sao có thể gán `Base x = new Derived();` nhưng không thể gán `List<Base> list = new ArrayList<Derived>();`?

**Đáp án:** Dòng đầu dựa vào quan hệ lớp con–lớp cha. Dòng sau bị từ chối vì các thể hiện `List<Base>` và `List<Derived>` không có quan hệ subtype tương ứng trong generics bất biến của Java. Dùng wildcard đúng nhu cầu khi cần đọc các subtype.

**Câu 6.** Trong TypeScript, một object có `send(receiver, content)` phù hợp có thể được dùng như `Sender` mà không khai báo `implements Sender`. Đó là hình thức tương thích gì?

**Đáp án:** Theo cấu trúc (*structural*), dựa trên thành viên đáp ứng hợp đồng. Cùng đoạn logic suy luận không áp dụng cho class/interface thông thường của Java.

**Câu 7.** Khi hai hệ thống dùng hai lớp `Customer` khác nhau nhưng đều có `id` và `name`, có nên ép gán trực tiếp để tái sử dụng không?

**Đáp án:** Không. Các kiểu có thể mang ràng buộc và ý nghĩa nghiệp vụ khác nhau. Nên ánh xạ dữ liệu một cách tường minh, dùng adapter hoặc định nghĩa hợp đồng chung ở ranh giới tích hợp khi thích hợp.

## Tóm ý cần nắm

Trong Java, **tương thích kiểu con** là câu chuyện về **danh tính kiểu và quan hệ `extends`/`implements` hợp lệ**, không phải chỉ nhìn hai class có những phương thức/field giống nhau. Hệ thống kiểu theo cấu trúc có thể chấp nhận một giá trị từ hình dạng thành viên phù hợp mà không cần khai báo quan hệ trực tiếp; đó là lựa chọn thiết kế khác của ngôn ngữ.

Khi gặp lỗi *incompatible types*, hãy hỏi: **(1)** Kiểu khai báo của biểu thức là gì? **(2)** Có quan hệ subtype nominal tới kiểu đích không? **(3)** Đây là chuyển đổi đặc biệt của Java hay một generic invariant? **(4)** Nếu hai hệ thống không cùng hợp đồng, có nên tạo adapter/chuyển đổi thay vì ép kiểu? Trả lời các câu đó thường chỉ ra nguyên nhân chính xác của lỗi và phương án thiết kế rõ ràng hơn.
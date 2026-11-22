# Gán trực tiếp vào field và ảnh hưởng đến tính tường minh

Trong Dependency Injection (DI), một đối tượng **sử dụng** một dịch vụ khác nên nhận dịch vụ đó từ bên ngoài, thay vì tự quyết định cách tạo và cấu hình nó. Có nhiều cách đưa dependency vào đối tượng: qua constructor, qua setter hoặc **gán trực tiếp vào field** (*field injection*). Cách thứ ba trông ngắn gọn, nhưng có thể làm các phụ thuộc bắt buộc trở nên khó nhìn thấy, khiến đối tượng tồn tại ở trạng thái chưa sẵn sàng và làm kiểm thử phức tạp hơn.

Bài học thuộc chương **Các cách truyền phụ thuộc** này tập trung vào ý nghĩa của việc gán trực tiếp vào field trong Java thuần và trong DI container, so sánh với constructor injection, đồng thời liên hệ đến Inversion of Control (IoC), composition root, scope và vòng đời đối tượng.

Sau bài này, bạn có thể:

- Phân biệt **field injection** với việc một lớp tự khởi tạo field bằng `new`, và với phép gán field nằm **bên trong constructor**.
- Giải thích vì sao yêu cầu dependency qua constructor thường tường minh hơn yêu cầu ngầm qua field.
- Quan sát lỗi do một field bắt buộc chưa được gán và viết lại ví dụ bằng Java thuần.
- Chọn giữa constructor injection, setter injection và field injection theo ràng buộc thực tế.
- Hiểu giới hạn của annotation và DI container khi quản lý field, lifecycle và kiểm thử.

## 1. “Gán trực tiếp vào field” nghĩa là gì?

Một **field** là biến thành viên lưu trạng thái của đối tượng. Trong ngữ cảnh DI, **field injection** là việc một thành phần bên ngoài cung cấp dependency bằng cách đặt giá trị trực tiếp vào field của đối tượng, thường **sau khi đối tượng đã được tạo**.

Cần phân biệt ba cách viết có bề ngoài tương tự nhưng mang ý nghĩa thiết kế khác nhau.

### 1.1. Lớp tự tạo dependency tại chỗ: không phải DI

~~~java
final class OrderService {
    private final NotificationSender sender =
            new ConsoleNotificationSender();
}
~~~

Ở đây OrderService **tự chọn và tạo** ConsoleNotificationSender. Field được khởi tạo ngay khi đối tượng được tạo, nhưng dependency không được một thành phần bên ngoài cung cấp. Vì vậy đây là **khởi tạo nội bộ**, không phải dependency injection. Hệ quả là OrderService bị gắn với một triển khai cụ thể.

### 1.2. Mã bên ngoài gán trực tiếp vào field: field injection thủ công

~~~java
final class OrderService {
    NotificationSender sender; // package-private: chỉ để minh họa
}

// Mã lắp ghép, trong cùng package:
OrderService service = new OrderService();
service.sender = new ConsoleNotificationSender();
~~~

Đối tượng được tạo trước, rồi mã lắp ghép đặt dependency vào field. Đây là **field injection thủ công**. Java cho phép gán như vậy khi phạm vi truy cập field hợp lệ; `package-private` chỉ cho mã cùng package truy cập. Nếu dùng field `public`, mọi mã có thể gán, làm mất khả năng kiểm soát trạng thái.

Việc dùng field có thể gán từ bên ngoài trong ví dụ chỉ giúp thấy cơ chế, **không phải khuyến nghị để mở các field nghiệp vụ thành public**.

### 1.3. Container gán vào field `private`

Trong một số DI framework, ta có thể khai báo field bằng annotation; container sử dụng cơ chế nội bộ, thường là reflection, để đưa dependency vào. Ví dụ cú pháp Spring:

~~~java
// Chỉ minh họa cú pháp framework; không biên dịch bằng Java thuần.
class OrderService {
    @Autowired
    private NotificationSender sender;
}
~~~

Mã ứng dụng không trực tiếp gán `sender`; container quản lý việc đó. **Java thuần không tự xử lý `@Autowired`**. Nếu bạn gọi `new OrderService()` ở ngoài container, annotation này không tự tạo hoặc truyền NotificationSender.

Với field injection do container thực hiện, cần biết rõ giai đoạn injection trong lifecycle của framework. Đừng giả định field đã được gán ngay trong constructor hoặc khi đối tượng được tạo thủ công.

### 1.4. Gán field trong constructor không phải field injection

~~~java
final class OrderService {
    private final NotificationSender sender;

    OrderService(NotificationSender sender) {
        this.sender = java.util.Objects.requireNonNull(sender);
    }
}
~~~

Dòng `this.sender = sender` vẫn là phép gán vào field, nhưng **dependency đi vào thông qua tham số constructor**. Đây là **constructor injection**, không được gọi là field injection chỉ vì có thao tác gán. Điểm phân biệt là **đường đi của dependency vào đối tượng**.

## 2. Vì sao tính tường minh lại quan trọng?

Một dependency có thể là **bắt buộc** khi đối tượng không thể hoàn thành chức năng nếu thiếu nó. Người đọc API của lớp cần nhận ra yêu cầu đó ở ngay thời điểm tạo đối tượng.

Với field injection:

~~~java
OrderService service = new OrderService();
~~~

Dòng mã này có thể biên dịch thành công dù `service.sender` chưa được gán. Người đọc phải xem bên trong class, annotation hoặc cấu hình container mới biết cách sử dụng service cho đúng.

Với constructor injection:

~~~java
OrderService service = new OrderService(sender);
~~~

Dòng khởi tạo biểu lộ rõ rằng service cần một NotificationSender. Không có một constructor rỗng tương ứng thì mã bên ngoài không thể bỏ qua tham số bắt buộc.

| Tiêu chí | Gán trực tiếp vào field | Constructor injection |
| --- | --- | --- |
| Nhìn constructor biết dependency bắt buộc? | Thường **không**, nếu constructor không khai báo dependency | **Có**, dependency thể hiện thành tham số |
| Đối tượng có thể được tạo khi thiếu dependency? | **Có thể**, vì field tham chiếu mặc định là `null` | Không qua constructor yêu cầu dependency; vẫn cần kiểm tra `null` |
| Thay dependency sau khi tạo? | Có thể nếu field còn cho phép ghi | Không qua field `private final` |
| Xác nhận invariant ngay lúc tạo? | Khó hơn do có bước gán sau khi tạo | Thuận tiện kiểm tra ở constructor |
| Tạo thủ công trong test? | Phải biết và thực hiện bước gán bổ sung | Truyền fake/mock ngay tại `new` |
| Ràng buộc với container/reflection? | Thường có nếu field `private` được container quản lý | Java thuần dùng được trực tiếp |
| Dùng chung một interface theo DIP? | Có thể | Có thể |

Các nhận xét này nói về **tính tường minh và khả năng kiểm soát trạng thái**, không phải khẳng định field injection luôn hỏng. DI container có thể phát hiện dependency chưa được cấu hình và báo lỗi khi khởi tạo ứng dụng; tuy nhiên constructor của class vẫn không diễn đạt đầy đủ nhu cầu đó với người dùng class ở Java thuần.

## 3. Vấn đề “đối tượng đã tồn tại nhưng chưa sẵn sàng”

Field tham chiếu của Java được gán giá trị mặc định là `null` nếu không được khởi tạo tường minh. Vì vậy đối tượng có thể tồn tại hợp lệ về mặt cú pháp nhưng chưa thỏa điều kiện để chạy nghiệp vụ.

~~~mermaid
flowchart TD
    A["new OrderService()"] --> B["Đối tượng tồn tại"]
    B --> C{"Field sender đã được gán?"}
    C -->|"Chưa"| D["Gọi nghiệp vụ: nguy cơ NullPointerException"]
    C -->|"Rồi"| E["Gọi nghiệp vụ"]
    F["Composition root hoặc DI container"] -->|"Gán field sau khi tạo"| C
~~~

Sơ đồ cho thấy một **khoảng trống về thời gian** giữa bước tạo đối tượng và bước inject dependency. Nếu đối tượng bị sử dụng quá sớm, một field bắt buộc có thể vẫn rỗng.

Ngoài lỗi `NullPointerException`, tình trạng tạo rồi mới gán còn gây các vấn đề:

- **Trạng thái trung gian:** đối tượng đã được trả về cho mã khác nhưng chưa có đủ collaborator.
- **Dễ quên bước lắp ghép:** đặc biệt trong bài kiểm thử hoặc khi ai đó tự gọi `new` ngoài container.
- **Có thể bị ghi đè:** field không `final` có thể bị thay đổi sau khi hoạt động; cần chủ động kiểm soát nếu không muốn đổi dependency.
- **Khó theo dõi yêu cầu:** dependency được thể hiện ở field, annotation và cấu hình hơn là tại chữ ký constructor.

Các framework có quy tắc lifecycle riêng để hạn chế việc cung cấp đối tượng chưa khởi tạo xong. Dẫu vậy, một lớp được xây dựng theo field injection thường ít an toàn hơn khi được dùng độc lập ngoài cơ chế lifecycle đó.

## 4. Thực hành: hai cách truyền cùng một dependency bằng Java thuần

Chương trình sau chạy với **Java 17 trở lên**, không cần thư viện hoặc DI container. Chúng ta giả lập việc một đơn hàng cần gửi thông báo xác nhận. Vì chỉ minh họa kỹ thuật DI, nơi gửi thông báo ở đây là console, không gửi email thật.

Lưu toàn bộ đoạn mã vào `Main.java`:

~~~java
import java.util.Objects;

record Order(String id) {}

// Hợp đồng được phần nghiệp vụ sử dụng.
interface NotificationSender {
    void sendConfirmation(String orderId);
}

final class ConsoleNotificationSender implements NotificationSender {
    @Override
    public void sendConfirmation(String orderId) {
        System.out.println("Da gui xac nhan: " + orderId);
    }
}

// Cách 1: field injection thủ công, chỉ để quan sát rủi ro.
final class FieldInjectedOrderService {
    NotificationSender sender; // package-private cho ví dụ cùng package

    void place(Order order) {
        if (order == null || order.id() == null
                || order.id().isBlank()) {
            throw new IllegalArgumentException("Ma don khong hop le");
        }

        // Có thể lỗi nếu người lắp ghép chưa gán sender.
        sender.sendConfirmation(order.id());
    }
}

// Cách 2: constructor injection thể hiện dependency bắt buộc.
final class ConstructorInjectedOrderService {
    private final NotificationSender sender;

    ConstructorInjectedOrderService(NotificationSender sender) {
        this.sender = Objects.requireNonNull(sender, "sender");
    }

    void place(Order order) {
        if (order == null || order.id() == null
                || order.id().isBlank()) {
            throw new IllegalArgumentException("Ma don khong hop le");
        }

        sender.sendConfirmation(order.id());
    }
}

// Composition root: chọn và tạo dependency tại điểm bắt đầu.
public class Main {
    public static void main(String[] args) {
        NotificationSender sender = new ConsoleNotificationSender();

        // Một đối tượng field-injected có thể bị dùng khi chưa sẵn sàng.
        FieldInjectedOrderService incomplete =
                new FieldInjectedOrderService();

        try {
            incomplete.place(new Order("O-01"));
        } catch (NullPointerException expected) {
            System.out.println("Field injection: sender chua duoc gan");
        }

        // Phải nhớ thực hiện bước gán thứ hai.
        FieldInjectedOrderService fieldService =
                new FieldInjectedOrderService();
        fieldService.sender = sender;
        fieldService.place(new Order("O-02"));

        // Đối tượng constructor-injected nhận dependency lúc tạo.
        ConstructorInjectedOrderService constructorService =
                new ConstructorInjectedOrderService(sender);
        constructorService.place(new Order("O-03"));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac Main.java
java Main
~~~

Kết quả dự kiến:

~~~text
Field injection: sender chua duoc gan
Da gui xac nhan: O-02
Da gui xac nhan: O-03
~~~

Ví dụ chủ động bắt một `NullPointerException` để minh họa tình huống dependency chưa được gán. Trong chương trình thực tế, **không nên dùng exception này như một bước bình thường của luồng nghiệp vụ**.

Điểm cần quan sát:

1. `new FieldInjectedOrderService()` tạo được đối tượng, dù `sender` đang là `null`.
2. Để đối tượng hoạt động, composition root phải nhớ gán `fieldService.sender = sender`. Bước này dễ bị bỏ sót hoặc đặt sai thời điểm.
3. `new ConstructorInjectedOrderService(sender)` yêu cầu truyền dependency ngay khi tạo. Constructor cũng kiểm tra `null` để từ chối cấu hình sai sớm.
4. Hai service đều làm việc với `NotificationSender` là interface. Nhờ vậy, có thể thay ConsoleNotificationSender bằng adapter khác mà không sửa logic gọi thông báo. Đây là hướng thiết kế phù hợp **Dependency Inversion Principle (DIP)**.

**Lưu ý về truy cập:** field `sender` được để package-private chỉ để mã Main cùng package có thể gán. Khi chuyển các lớp sang nhiều package, cách này không còn hoạt động từ bên ngoài package. Mở field thành `public` chỉ để “inject” sẽ khiến trạng thái lớp khó được bảo vệ; trong thiết kế thông thường, nên giữ field `private` và lựa chọn một đường truyền dependency có chủ đích.

## 5. Hệ quả trong kiểm thử: biết dependency bằng cách nào?

Kiểm thử nghiệp vụ thường cần fake để quan sát lời gọi, tránh khởi động hạ tầng. Với constructor injection, việc xây dựng đối tượng cần kiểm thử diễn đạt ngay những dependency phải cấp:

~~~java
RecordingSender fake = new RecordingSender();
ConstructorInjectedOrderService service =
        new ConstructorInjectedOrderService(fake);
~~~

Với field injection thủ công, mã kiểm thử có thêm bước dễ quên:

~~~java
RecordingSender fake = new RecordingSender();
FieldInjectedOrderService service =
        new FieldInjectedOrderService();
service.sender = fake; // nếu quên, chỉ khi gọi place(...) mới phát hiện
~~~

Nếu field là `private` và container dùng reflection để inject, test bằng Java thuần sẽ không thể gán trực tiếp từ một lớp bên ngoài. Khi đó người viết test có thể phải khởi động container, dùng công cụ reflection hoặc thêm API chỉ để phục vụ test. Những cách này không phải lúc nào cũng sai, nhưng làm test phụ thuộc nhiều hơn vào cơ chế tạo đối tượng.

Thử tự viết một test nhỏ bằng Java thuần. Giữ `Main.java` ở trên và lưu đoạn dưới vào `OrderServiceTest.java` trong cùng thư mục:

~~~java
final class RecordingSender implements NotificationSender {
    String lastOrderId;
    int callCount;

    @Override
    public void sendConfirmation(String orderId) {
        lastOrderId = orderId;
        callCount++;
    }
}

public class OrderServiceTest {
    public static void main(String[] args) {
        RecordingSender fake = new RecordingSender();
        ConstructorInjectedOrderService service =
                new ConstructorInjectedOrderService(fake);

        service.place(new Order("TEST-01"));

        if (fake.callCount != 1
                || !"TEST-01".equals(fake.lastOrderId)) {
            throw new AssertionError("Gui thong bao khong dung");
        }

        // Dependency bat buoc thieu se bi tu choi ngay khi new.
        boolean rejectedNull = false;
        try {
            new ConstructorInjectedOrderService(null);
        } catch (NullPointerException expected) {
            rejectedNull = true;
        }

        if (!rejectedNull) {
            throw new AssertionError("Phai tu choi sender null");
        }

        System.out.println("PASS");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac Main.java OrderServiceTest.java
java OrderServiceTest
~~~

Kết quả dự kiến: `PASS`.

Test xác minh hai điều: service sử dụng đúng NotificationSender và từ chối một dependency bắt buộc không hợp lệ ngay khi khởi tạo. Đây là lợi ích của **API tường minh và invariant được kiểm tra sớm**; chưa phải kiểm thử bộ gửi thông báo thực tế. Adapter thật vẫn cần kiểm thử tích hợp nếu có kết nối mạng hoặc hệ thống ngoài.

## 6. Field injection trong DI container: điều gì được che giấu?

Một số framework cho phép viết ngắn gọn như sau:

~~~java
// Minh họa kiểu sử dụng Spring; không thuộc ví dụ Java thuần.
@Component
class OrderService {
    @Autowired
    private NotificationSender sender;

    void place(String orderId) {
        sender.sendConfirmation(orderId);
    }
}
~~~

Khi container quản lý bean và injection được cấu hình đúng, container có thể tìm triển khai NotificationSender và gán vào field. Điều này tiết kiệm mã constructor, nhưng tạo ra **một hợp đồng khởi tạo ngầm**:

- Chữ ký `OrderService()` không cho biết rõ một NotificationSender là bắt buộc.
- `new OrderService()` bên ngoài container không có hành vi injection tương tự.
- Việc injection xảy ra ở giai đoạn lifecycle do framework quyết định; gọi phương thức cần dependency trước giai đoạn đó có thể lỗi.
- Muốn hiểu đầy đủ cách tạo lớp, người đọc phải biết annotation, cơ chế cấu hình và quy tắc của framework.

Không nên kết luận rằng container **luôn** để thiếu dependency đến khi gọi nghiệp vụ: nhiều container có thể báo lỗi khi khởi động nếu thiếu bean bắt buộc. Vấn đề của field injection vẫn là **nhu cầu phụ thuộc khó thấy hơn khi chỉ nhìn vào API của lớp**.

Field injection bằng reflection cũng không phải lựa chọn tốt để xây dựng một đối tượng bất biến với các dependency bắt buộc là field `private final`. Constructor injection phù hợp hơn cho invariant đó vì giá trị được đặt lúc tạo đối tượng.

## 7. So sánh với setter injection và constructor injection

Không phải mọi dependency đều có cùng nhu cầu. Sự khác nhau nằm ở **thời điểm**, **cách kiểm tra hợp lệ** và **ai được phép thay dependency**.

### Constructor injection: ưu tiên cho dependency bắt buộc

~~~java
final class PriceService {
    private final TaxPolicy policy;

    PriceService(TaxPolicy policy) {
        this.policy = java.util.Objects.requireNonNull(policy);
    }
}
~~~

Đối tượng chỉ có thể được tạo thông qua constructor yêu cầu TaxPolicy; field `final` biểu đạt rằng tham chiếu dependency không bị gán lại sau khi khởi tạo. **Constructor injection thường là lựa chọn mặc định tốt cho cộng tác viên bắt buộc**. Tuy nhiên, nếu TaxPolicy là đối tượng mutable thì từ khóa `final` chỉ giữ cố định tham chiếu, không khiến toàn bộ đồ thị đối tượng bất biến.

### Setter injection: thích hợp khi cho phép cấu hình hay thay đổi sau khi tạo

~~~java
final class ReportService {
    private AuditLogger auditLogger;

    void setAuditLogger(AuditLogger auditLogger) {
        this.auditLogger = auditLogger; // có thể kiểm tra hợp lệ tại đây
    }
}
~~~

Setter biểu lộ rõ một thao tác cấu hình có tên, có thể thực hiện kiểm tra và kiểm soát ghi đè. Phù hợp khi dependency thực sự **không bắt buộc** hoặc được phép cấu hình lại một cách có chủ ý. Nếu dependency là bắt buộc, setter vẫn có nguy cơ tạo trạng thái trung gian “chưa sẵn sàng”; cần thiết kế quy tắc hoàn tất cấu hình riêng.

### Field injection: đơn giản về cú pháp, kém rõ ở hợp đồng tạo đối tượng

~~~java
final class ReportService {
    AuditLogger auditLogger; // dự kiến được gán sau khi new
}
~~~

Field injection có thể phù hợp trong những môi trường bị framework kiểm soát chặt và quy ước nhóm đã rõ ràng, nhưng đổi lại việc hiểu dependency thường cần đọc toàn bộ class và cơ chế container. Đối với Java thuần và học nền tảng DI, constructor injection giúp quan sát rõ hơn **ai tạo, ai truyền và khi nào đối tượng sẵn sàng**.

| Tình huống | Cách thường nên cân nhắc | Lý do |
| --- | --- | --- |
| Service không thể hoạt động khi thiếu một dependency | Constructor injection | Thể hiện yêu cầu ngay ở chữ ký khởi tạo |
| Dependency là lựa chọn cấu hình, có thể bật/tắt | Constructor với giá trị mặc định rõ ràng hoặc setter | Biểu đạt tính tùy chọn một cách chủ đích |
| Cần thay collaborator khi đối tượng đã chạy | Setter hoặc cơ chế cấu hình có kiểm soát | Cho phép kiểm tra và đồng bộ khi thay đổi |
| Framework quản lý toàn bộ lifecycle và cho phép field injection | Có thể dùng, hiểu rõ đánh đổi | Cần ý thức về API ngầm và cách test |
| Muốn tránh lệ thuộc vào container trong unit test | Constructor injection | Tạo đối tượng và fake bằng Java thuần |

## 8. Liên hệ với composition root, scope và vòng đời

**Composition root** là nơi ứng dụng quyết định chọn, tạo và lắp ghép các dependency. Với constructor injection, việc lắp ghép thường thể hiện trong cùng một biểu thức:

~~~java
NotificationSender sender = new ConsoleNotificationSender();
ConstructorInjectedOrderService service =
        new ConstructorInjectedOrderService(sender);
~~~

Với field injection, composition root hoặc container phải tạo đối tượng trước rồi thực hiện bước gán tiếp theo:

~~~java
NotificationSender sender = new ConsoleNotificationSender();
FieldInjectedOrderService service =
        new FieldInjectedOrderService();
service.sender = sender;
~~~

Trong ví dụ đơn giản, hai cách cuối cùng đều cung cấp được cùng một NotificationSender. Tuy nhiên, khi đồ thị đối tượng có nhiều nhánh, việc phải nhớ các bước gán bổ sung làm cho thời điểm “lắp ghép xong” khó nhận ra.

**Scope** trả lời câu hỏi một đối tượng được dùng trong bao lâu: toàn ứng dụng, mỗi request hay mỗi thao tác. **Vòng đời** xác định lúc tạo, cấp dependency, sử dụng và giải phóng tài nguyên. Việc chọn field injection **không quyết định scope**. Một field có thể trỏ đến dependency dùng chung hoặc có vòng đời ngắn, tùy cấu hình. Nếu gán một dependency có scope ngắn vào một service sống lâu, cần xem lại cơ chế quản lý scope; cả field injection lẫn constructor injection đều không tự sửa được sai lệch này.

Một hệ quả khác của việc để dependency ghi được sau khi khởi tạo là **thay đổi khi có nhiều luồng**. Nếu một thread đang chạy nghiệp vụ trong khi thread khác gán lại field, ứng dụng phải tự bảo đảm an toàn luồng và quy tắc visibility thích hợp. Tránh coi việc đổi dependency bằng phép gán field là giải pháp cấu hình động an toàn mặc định.

Cuối cùng, việc inject một đối tượng giữ tài nguyên (`AutoCloseable`, kết nối, client mạng) không đồng nghĩa người tiêu thụ có quyền đóng nó. Nơi tạo hoặc quản lý vòng đời cần quy định rõ ai đóng và lúc nào, bất kể đường injection là field hay constructor.

## 9. Các dấu hiệu cần xem lại trong code

| Dấu hiệu | Rủi ro hoặc nhầm lẫn | Hướng xử lý |
| --- | --- | --- |
| `new Service()` thành công nhưng service không chạy khi thiếu field | Dependency bắt buộc bị ẩn khỏi API | Chuyển thành tham số constructor và kiểm tra hợp lệ |
| Dùng `public SomeRepository repository;` chỉ để inject | Mã bất kỳ có thể ghi đè trạng thái | Giữ encapsulation, dùng constructor hoặc setter có kiểm soát |
| Có `@Autowired private ...` rồi test bằng `new` | Annotation không được container xử lý | Tạo qua container khi cần test tích hợp, hoặc chuyển constructor injection |
| Trong constructor gọi phương thức sử dụng field được container inject | Field có thể chưa được inject vào thời điểm đó | Tránh sử dụng field theo cách này; đưa dependency bắt buộc vào constructor |
| Có nhiều field `@Autowired` nhưng constructor rỗng | Khó nhận ra số lượng dependency khi sử dụng lớp | Cân nhắc constructor rõ tham số và xem lại trách nhiệm của lớp |
| Cố giải quyết vòng phụ thuộc bằng gán field sau | Che giấu coupling và tạo trạng thái khởi tạo khó hiểu | Thiết kế lại ranh giới trách nhiệm và hướng phụ thuộc |
| Field `final` bị hiểu nhầm là “object hoàn toàn bất biến” | Đối tượng được tham chiếu vẫn có thể mutable | Xem xét thread safety và nội dung trạng thái của dependency |

Một điểm cần làm rõ là **DIP** và **DI** không phải cùng một khái niệm. Dùng field injection với interface phù hợp vẫn có thể tuân thủ Dependency Inversion Principle về hướng phụ thuộc mã nguồn. Nhưng việc tuân thủ DIP **không** giải quyết nhược điểm về tính tường minh và thời điểm khởi tạo của field injection. Constructor injection giúp trình bày dependency rõ ràng hơn ngay cả khi hai cách đều đang phụ thuộc vào cùng một interface.

## 10. Bài tập suy luận và thực hành

**Bài tập 1 — Nhận diện cơ chế**

Xem ba đoạn sau:

~~~java
// A
private Logger logger = new ConsoleLogger();

// B
Logger logger; // composition root gán sau khi new

// C
private final Logger logger;
Service(Logger logger) { this.logger = logger; }
~~~

Hãy phân loại: A là **tự khởi tạo phụ thuộc**, B là **field injection thủ công** nếu field được bên ngoài gán, C là **constructor injection**. Đoạn C có phép gán vào field nhưng không được gọi là field injection.

**Bài tập 2 — Tìm thời điểm phát hiện lỗi**

Một đối tượng có field `NotificationSender sender` chưa gán. Trường hợp nào có thể phát hiện lỗi sớm hơn?

- Dùng field injection thủ công: lỗi có thể chỉ xuất hiện khi gọi phương thức sử dụng field, trừ khi ứng dụng tự kiểm tra.
- Dùng constructor injection và `Objects.requireNonNull(sender)`: thiếu dependency được phát hiện ngay tại thời điểm tạo đối tượng.
- Dùng DI container với field injection bắt buộc: thời điểm báo lỗi phụ thuộc vào cơ chế khởi tạo và kiểm tra của container, có thể ngay lúc bootstrap.

**Bài tập 3 — Refactor**

Từ đoạn mã:

~~~java
final class InvoiceService {
    InvoiceRepository repository;
    PaymentGateway paymentGateway;

    void pay(Invoice invoice) {
        paymentGateway.charge(invoice);
        repository.save(invoice);
    }
}
~~~

Hãy chuyển hai collaborator thành field `private final`, bổ sung constructor nhận `InvoiceRepository` và `PaymentGateway` với kiểm tra `null`, rồi tạo `InvoiceService` tại composition root. Thử gắn fake vào constructor để kiểm tra lời gọi `charge` và `save` bằng Java thuần.

**Câu hỏi nâng cao:** Nếu InvoiceService có tới mười dependency bắt buộc, có nên chuyển một nửa sang field injection để constructor ngắn đi?

Không nên chọn cách đó chỉ để che số lượng tham số. Constructor dài có thể là dấu hiệu InvoiceService đang giữ nhiều trách nhiệm hoặc phạm vi use case quá rộng. Hãy xem lại thiết kế, phân chia trách nhiệm và cách nhóm những khả năng có quan hệ thực sự trước khi thay đổi cơ chế injection.

## Tổng kết

**Field injection là việc dependency được gán trực tiếp vào field từ bên ngoài, thường sau khi đối tượng được tạo.** Nó khác với việc tự `new` dependency ở field và khác với việc gán `this.field` trong constructor. Điểm đánh đổi lớn nhất là **phụ thuộc bắt buộc ít tường minh ở API khởi tạo**; đối tượng có thể tồn tại trước khi sẵn sàng.

Với Java thuần, hãy ưu tiên **constructor injection** cho dependency bắt buộc: đưa abstraction vào constructor, kiểm tra invariant, giữ field `private final` khi phù hợp, và lắp ghép đồ thị đối tượng tại composition root. Chỉ chọn setter hoặc field injection khi có lý do cụ thể về cấu hình, vòng đời hoặc yêu cầu framework, đồng thời bảo đảm cách kiểm thử và quản lý scope phản ánh đúng cơ chế đó.

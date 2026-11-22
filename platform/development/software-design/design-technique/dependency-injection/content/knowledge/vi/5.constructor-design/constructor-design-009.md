# Tránh tạo phụ thuộc mặc định ngầm bên trong constructor

## 1. Vì sao constructor là ranh giới quan trọng của Dependency Injection?

Trong **Dependency Injection (DI)**, một đối tượng nhận các cộng tác viên (dependency) cần thiết từ bên ngoài, thay vì tự quyết định cách tạo chúng. Đây là một cách thực hiện **Inversion of Control (IoC)**: quyền chọn implementation, cấu hình và lắp ghép được chuyển ra ngoài lớp làm nghiệp vụ.

**Constructor injection** thể hiện rõ ý tưởng đó: constructor nhận dependency bắt buộc và thiết lập một đối tượng sẵn sàng hoạt động. Chẳng hạn, `OrderService` cần `AuditRecorder` để ghi sự kiện đơn hàng đã được xác nhận. Khi dependency được truyền qua constructor, người tạo `OrderService` phải đưa ra lựa chọn cụ thể.

Một lỗi thiết kế dễ bị bỏ qua là **constructor âm thầm tạo một implementation mặc định** nếu caller không cung cấp dependency. Mã ban đầu có vẻ tiện lợi, nhưng làm mờ việc ai quyết định đối tượng được dùng, cấu hình ở đâu và ai sở hữu vòng đời tài nguyên.

**Mục tiêu bài học:**

- Nhận diện các dạng phụ thuộc mặc định bị tạo ngầm trong constructor.
- Giải thích tác động tới khả năng thay thế implementation, cấu hình, kiểm thử và quản lý vòng đời.
- Viết constructor injection tường minh bằng Java thuần, với composition root chịu trách nhiệm lắp ghép.
- Phân biệt dependency bắt buộc, giá trị mặc định hợp lệ và dependency thực sự tùy chọn.
- Biết khi nào nên dùng factory, cấu hình tại điểm khởi động hoặc DI container.

## 2. Ví dụ vấn đề: truyền `null` sẽ kích hoạt hành vi ngầm

Xem thiết kế sau, trong đó `OrderService` cần một nơi ghi nhật ký hoạt động:

```java
// Minh họa lỗi thiết kế; các interface/class liên quan
// được định nghĩa đầy đủ trong ví dụ chạy được ở mục 4.
final class OrderService {
    private final AuditRecorder recorder;

    OrderService(AuditRecorder recorder) {
        this.recorder = recorder != null
                ? recorder
                : new ConsoleAuditRecorder();
    }

    void confirm(String orderId) {
        recorder.record("ORDER_CONFIRMED:" + orderId);
    }
}
```

Hai lời gọi dưới đây tạo ra hai hành vi khác nhau:

```java
new OrderService(customRecorder); // Ghi audit vào nơi caller chọn.
new OrderService(null);           // Âm thầm chuyển sang console.
```

Constructor có chữ ký `OrderService(AuditRecorder recorder)`, nhưng `recorder` thực chất được xem là tùy chọn. Người đọc chữ ký không biết `null` có ý nghĩa “dùng console”. Một lỗi lắp ghép vô tình truyền `null` cũng có thể biến thành một dịch vụ hoạt động bằng adapter không mong muốn.

Nếu audit là yêu cầu bắt buộc, việc âm thầm dùng console thay cho hệ thống audit thật có thể làm mất sự kiện ở nơi cần theo dõi. Nếu dependency là kết nối database, HTTP client hoặc email sender, mặc định ngầm còn có thể kéo theo I/O, credential, kết nối, thread hoặc tài nguyên không được quản lý rõ ràng.

Vấn đề **không nằm ở mọi biểu thức `new` xuất hiện trong constructor**. Vấn đề nằm ở chỗ lớp nghiệp vụ tự chọn và tạo một *cộng tác viên có vai trò độc lập* mà đáng ra được chọn tại nơi lắp ghép.

## 3. Những dạng mặc định ngầm thường gặp

### 3.1. Fallback khi dependency bằng `null`

```java
this.recorder = recorder == null
        ? new ConsoleAuditRecorder()
        : recorder;
```

Mẫu này biến `null` thành một lựa chọn cấu hình không được nêu rõ. Nếu caller vô tình quên dependency, lỗi sẽ không xuất hiện ngay ở điểm khởi tạo.

Ngay cả khi `ConsoleAuditRecorder` không mở tài nguyên ngoài, `OrderService` vẫn biết implementation cụ thể. Việc chuyển sang một thư viện audit khác sẽ có nguy cơ buộc phải sửa mã nghiệp vụ.

### 3.2. Constructor không tham số tự tạo collaborator

```java
// Ví dụ minh họa cách làm cần cân nhắc.
OrderService() {
    this(new ConsoleAuditRecorder());
}
```

Constructor không tham số thường xuất hiện để “khởi tạo cho nhanh”, nhưng nó che quyết định chọn implementation vào bên trong chính lớp nghiệp vụ. Kết quả là `new OrderService()` có thể chạy khác nhau tùy cấu hình cứng trong mã.

Nếu đây là API cố ý cung cấp một cấu hình mẫu cho người dùng thư viện, cần ghi rõ hợp đồng và giới hạn. Đối với dịch vụ nghiệp vụ có dependency bắt buộc, một **factory đặt tại ranh giới ứng dụng** thường giúp lựa chọn mặc định minh bạch hơn.

### 3.3. Chủ động tạo dependency dù đã có tham số

```java
OrderService(AuditRecorder recorder) {
    // Tham số bị bỏ qua: điểm injection chỉ còn mang tính hình thức.
    this.recorder = new ConsoleAuditRecorder();
}
```

Đây không còn là constructor injection đúng nghĩa cho `AuditRecorder`, vì giá trị được cung cấp không chi phối đối tượng được sử dụng. Test truyền fake cũng không thể cô lập tác động của adapter thật.

### 3.4. Dùng Service Locator hoặc trạng thái toàn cục làm mặc định

```java
this.recorder = recorder != null
        ? recorder
        : GlobalRegistry.get(AuditRecorder.class);
```

Mẫu này có thể không tạo đối tượng bằng `new`, nhưng dependency vẫn bị **tìm kiếm ngầm** trong constructor. Test phải chuẩn bị registry toàn cục và việc lắp ghép bị phân tán. Đây là một biểu hiện của Service Locator; việc kiểm soát object graph trở nên khó theo dõi hơn.

### 3.5. Mặc định che lỗi cấu hình hoặc lỗi tài nguyên

```java
// Pseudocode: ví dụ về ý tưởng cần tránh.
try {
    this.recorder = createRemoteAuditRecorder();
} catch (RuntimeException ex) {
    this.recorder = new ConsoleAuditRecorder();
}
```

Nếu hệ thống audit từ xa là một yêu cầu bắt buộc, fallback này biến lỗi kết nối thành lỗi ngầm của hành vi ứng dụng. Khi cần failover thật, hãy thiết kế rõ chính sách retry/fallback, quan sát lỗi, điều kiện chấp nhận hạ cấp dịch vụ và vị trí chịu trách nhiệm; đừng để constructor tùy ý quyết định.

## 4. Cách làm rõ ràng: dependency bắt buộc, được truyền tường minh

Đặt toàn bộ mã sau trong `App.java`; chương trình sử dụng Java thuần và không cần DI container.

```java
import java.util.Objects;

// Hợp đồng mà nghiệp vụ thực sự cần.
interface AuditRecorder {
    void record(String event);
}

// Adapter dành cho ứng dụng demo, không kết nối tới dịch vụ ngoài.
final class ConsoleAuditRecorder implements AuditRecorder {
    @Override
    public void record(String event) {
        System.out.println("AUDIT " + event);
    }
}

final class OrderService {
    private final AuditRecorder recorder;

    OrderService(AuditRecorder recorder) {
        // Sai cấu hình thì báo lỗi tại thời điểm tạo đối tượng.
        this.recorder = Objects.requireNonNull(recorder, "recorder");
    }

    void confirm(String orderId, long amountVnd) {
        if (orderId == null || orderId.trim().isEmpty()) {
            throw new IllegalArgumentException("Mã đơn không hợp lệ");
        }
        if (amountVnd <= 0) {
            throw new IllegalArgumentException("Số tiền phải dương");
        }

        recorder.record("ORDER_CONFIRMED:" + orderId + ":" + amountVnd);
    }
}

public class App {
    public static void main(String[] args) {
        // Composition root: nơi chọn, tạo và lắp ghép các đối tượng.
        AuditRecorder recorder = new ConsoleAuditRecorder();
        OrderService orders = new OrderService(recorder);

        orders.confirm("ORDER-123", 250_000);
    }
}
```

Chạy:

```bash
javac App.java
java App
```

Kết quả dự kiến:

```text
AUDIT ORDER_CONFIRMED:ORDER-123:250000
```

Trong ví dụ này:

1. `OrderService` chỉ biết hợp đồng `AuditRecorder`, không biết `ConsoleAuditRecorder` được tạo như thế nào.
2. `App.main` là **composition root**, chọn adapter demo và đưa vào constructor.
3. Nếu caller truyền `null`, `Objects.requireNonNull` ném `NullPointerException` ngay lúc khởi tạo; không còn hành vi mặc định khó phát hiện.
4. Trường `recorder` là `final`, giúp thể hiện rằng tham chiếu tới collaborator được cố định sau khi khởi tạo. Điều này **không tự bảo đảm** bản thân implementation là bất biến hoặc thread-safe.

Đổi từ `ConsoleAuditRecorder` sang một adapter lưu file, database hoặc gọi API có thể thực hiện ở composition root, miễn adapter mới đáp ứng contract `AuditRecorder`. Khi thay adapter, vẫn cần kiểm thử tích hợp cho cách ghi dữ liệu thực tế, cấu hình và lỗi I/O.

### 4.1. Minh họa ranh giới quyền quyết định

```text
               Composition root (App.main)
                /                    \
        chọn implementation       tạo OrderService
        tạo AuditRecorder         truyền recorder
                \                    /
                 v                  v
             AuditRecorder <---- OrderService
              (hợp đồng)          (sử dụng)
                 ^
                 |
          ConsoleAuditRecorder
          (triển khai cho demo)
```

Phần **sử dụng phụ thuộc** được tách khỏi phần **tạo và lắp ghép**. Đây chính là lý do constructor injection thường là bước đầu trước khi cân nhắc tự động hóa bằng DI container.

## 5. Kiểm thử bằng fake: lỗi mặc định ngầm trở nên rõ ràng

Tạo file `OrderServiceTest.java` cùng thư mục với `App.java`:

```java
final class RecordingAuditRecorder implements AuditRecorder {
    int calls;
    String lastEvent;

    @Override
    public void record(String event) {
        calls++;
        lastEvent = event;
    }
}

public class OrderServiceTest {
    public static void main(String[] args) {
        RecordingAuditRecorder fake = new RecordingAuditRecorder();
        OrderService orders = new OrderService(fake);

        orders.confirm("TEST-001", 75_000);

        if (fake.calls != 1
                || !"ORDER_CONFIRMED:TEST-001:75000".equals(fake.lastEvent)) {
            throw new AssertionError("Không gọi đúng dependency được inject");
        }

        boolean rejectedMissingDependency = false;
        try {
            new OrderService(null);
        } catch (NullPointerException expected) {
            rejectedMissingDependency = true;
        }

        if (!rejectedMissingDependency) {
            throw new AssertionError("Constructor phải từ chối dependency null");
        }

        System.out.println("PASS");
    }
}
```

Chạy:

```bash
javac App.java OrderServiceTest.java
java OrderServiceTest
```

Kết quả: `PASS`.

Bài kiểm thử chứng minh `OrderService` dùng đúng đối tượng được inject và **không âm thầm thay fake bằng adapter mặc định**. Test cũng kiểm tra lỗi thiếu dependency xảy ra tại constructor thay vì xuất hiện muộn khi xử lý nghiệp vụ.

Tuy nhiên, test bằng fake chỉ xác minh cách lớp nghiệp vụ hợp tác với `AuditRecorder`. Nó không chứng minh adapter audit thật kết nối đúng, ghi đủ dữ liệu hay xử lý được sự cố; cần thêm kiểm thử tích hợp và cấu hình khởi động thích hợp.

## 6. Mặc định hợp lệ nên được khai báo ở đâu?

“Mặc định” không nhất thiết là xấu. Điều quan trọng là **ai đưa ra lựa chọn và liệu lựa chọn đó có tường minh hay không**.

### 6.1. Chọn adapter mặc định tại composition root

Nếu bản demo dùng console, môi trường kiểm thử dùng fake và môi trường chạy thật dùng adapter từ xa, các lựa chọn có thể nằm ở nơi khởi động:

```java
// Ví dụ cấu hình ở ranh giới ứng dụng.
static OrderService createForDemo() {
    return new OrderService(new ConsoleAuditRecorder());
}
```

Factory này nằm **ngoài `OrderService`**. Tên `createForDemo` giúp người gọi thấy mục đích của lựa chọn. Ứng dụng thực có thể đặt những factory tương tự trong module cấu hình, với dependency, credential và lifecycle được quản lý tập trung.

Nếu cấu hình có nhiều môi trường, composition root có thể đọc một giá trị cấu hình hợp lệ rồi chọn implementation. Cấu hình thiếu hoặc không hợp lệ cần gây lỗi rõ ràng, nhất là với dependency phục vụ yêu cầu bắt buộc.

### 6.2. Giá trị mặc định không phải lúc nào cũng là dependency

Tạo giá trị bất biến và chỉ dùng nội bộ có thể là trách nhiệm bình thường của constructor:

```java
final class SearchRequest {
    private final int pageSize;

    SearchRequest(Integer requestedSize) {
        // Mặc định cho dữ liệu đầu vào: không tạo collaborator bên ngoài.
        this.pageSize = requestedSize == null ? 20 : requestedSize;
        if (pageSize <= 0) {
            throw new IllegalArgumentException("pageSize phải dương");
        }
    }

    int pageSize() {
        return pageSize;
    }
}
```

Ở đây, `20` là **quy tắc mặc định cho dữ liệu**, không phải một adapter có hành vi, I/O hoặc vòng đời riêng. Nếu quy tắc này thuộc hợp đồng của `SearchRequest`, việc đặt nó trong constructor có thể hợp lý và dễ kiểm thử.

Tương tự, tạo `new ArrayList<>()`, `new Money(...)` hoặc một đối tượng giá trị dùng riêng trong nội bộ không mặc nhiên vi phạm DI. Cần phân biệt **đối tượng dữ liệu thuộc sở hữu của lớp** với **cộng tác viên độc lập** mà lớp sử dụng để hoàn thành công việc.

### 6.3. Một dependency thực sự tùy chọn

Nếu nghiệp vụ cho phép **không gửi telemetry**, cách diễn đạt tường minh là tạo một adapter `NoOpTelemetry` và để nơi lắp ghép chủ động chọn:

```java
interface Telemetry {
    void track(String event);
}

final class NoOpTelemetry implements Telemetry {
    @Override
    public void track(String event) {
        // Cố ý không thu thập telemetry.
    }
}

final class ReportService {
    private final Telemetry telemetry;

    ReportService(Telemetry telemetry) {
        this.telemetry = java.util.Objects.requireNonNull(
                telemetry, "telemetry");
    }
}
```

Composition root có thể gọi `new ReportService(new NoOpTelemetry())` khi chấp nhận bỏ qua telemetry. Như vậy, quyết định “không gửi” là **một lựa chọn rõ ràng**. Không nên dùng No-Op để che giấu một yêu cầu ghi audit, gửi thông báo hay lưu dữ liệu bắt buộc.

Một lựa chọn khác là mô tả tính tùy chọn trong API, chẳng hạn bằng đối tượng cấu hình hoặc một kiểu giá trị phù hợp. Dù dùng cách nào, hãy ghi rõ “không có dependency” là tình huống nghiệp vụ hợp lệ hay là lỗi cấu hình.

## 7. Vì sao mặc định ngầm gây chi phí trong hệ thống thật?

| Rủi ro | Khi constructor tự chọn mặc định | Khi lắp ghép tường minh |
| --- | --- | --- |
| **Phát hiện lỗi cấu hình** | Giá trị `null` có thể bị biến thành một adapter không mong muốn. | Thiếu dependency bắt buộc gây lỗi sớm tại điểm tạo đối tượng. |
| **Khả năng kiểm thử** | Test có thể vô tình sử dụng file, mạng, clock, console hoặc global registry thật. | Test truyền fake, stub hoặc clock cố định theo mục đích. |
| **Thay implementation** | Lớp nghiệp vụ cần sửa vì tham chiếu tới implementation mặc định. | Thay adapter ở composition root hoặc cấu hình DI. |
| **Quan sát hành vi** | Hai caller cùng dùng constructor nhưng kết quả tùy cách xử lý ngầm của `null`. | Các lựa chọn được thể hiện trực tiếp tại nơi lắp ghép. |
| **Quản lý scope** | Constructor có thể tạo tài nguyên dùng riêng dù nên dùng chung, hoặc ngược lại. | Nơi lắp ghép quyết định tạo một lần hay tạo theo request. |
| **Quản lý vòng đời** | Không rõ ai đóng kết nối, stream hoặc thread pool được tạo trong constructor. | Thành phần sở hữu tài nguyên được xác định tại ranh giới khởi tạo. |
| **Chi phí thay đổi** | Cấu hình và chính sách chọn adapter nằm rải rác trong lớp nghiệp vụ. | Lựa chọn được tập trung và dễ rà soát. |

### 7.1. Tài nguyên có vòng đời: nguy cơ khó nhìn từ constructor

Ví dụ, nếu mỗi lần tạo `OrderService` đều tự khởi tạo HTTP client hoặc thread pool mới, hệ thống có thể tạo nhiều tài nguyên hơn cần thiết. Nếu dependency triển khai `AutoCloseable`, người thiết kế phải định nghĩa rõ ai sở hữu và gọi `close()`.

DI **không tự đóng tài nguyên**. Composition root hoặc lớp quản lý lifecycle cần thực hiện việc đó theo đúng hợp đồng của dependency. DI container có thể cung cấp lifecycle hooks, nhưng không bảo đảm mọi tài nguyên được giải phóng đúng nếu scope hoặc cấu hình sai.

### 7.2. Mặc định cho đối tượng có trạng thái

Một collaborator ghi nhớ `currentUser`, session, request ID hoặc dữ liệu tạm không thể tùy tiện tạo một lần rồi dùng chung cho tất cả người dùng. Ngược lại, một thành phần thread-safe quản lý connection pool có thể cần chia sẻ để tránh mở quá nhiều kết nối.

Việc chuyển quyền tạo dependency ra khỏi constructor của dịch vụ nghiệp vụ giúp dễ quyết định **scope**: singleton dùng chung, đối tượng mới cho từng lần tạo, hay đối tượng gắn với một request. Không có scope nào phù hợp cho mọi dependency; phải xét trạng thái, concurrency và ownership của từng implementation.

### 7.3. Ẩn lỗi có thể nghiêm trọng hơn ném lỗi

Nếu nhà cung cấp thông báo bắt buộc không cấu hình được, việc âm thầm thay bằng console làm ứng dụng trông như đang hoạt động nhưng người dùng không nhận được thông báo. Nếu vận hành có chủ đích cho phép chạy chế độ giảm chức năng, cần có chính sách rõ, giám sát được và được quyết định ở ranh giới thích hợp. Constructor không nên tự suy đoán chính sách vận hành từ việc gặp `null` hoặc một exception.

## 8. Các trường hợp ngoại lệ cần đánh giá theo ngữ cảnh

Không có quy tắc tuyệt đối “constructor không được gọi `new`”. Cần xét vai trò và phạm vi đối tượng được tạo.

- **Tạo dữ liệu nội bộ:** `new ArrayList<>()` để lưu trạng thái riêng hoặc tạo value object bất biến thường hợp lý; đó không nhất thiết là dependency cần inject.
- **Ủy quyền sang constructor chính:** một constructor tiện ích có thể gọi `this(...)` với giá trị cấu hình thuần túy đã công bố rõ. Nhưng nếu nó ngầm tạo database client, clock hệ thống hoặc SMTP sender thì cần xem lại tính thay thế và khả năng kiểm thử.
- **Dependency phải tạo cùng tham số động mỗi lần xử lý:** cân nhắc inject một **factory** hoặc collaborator có nhiệm vụ tạo đối tượng theo ngữ cảnh; factory cũng cần được cấp từ bên ngoài nếu nó thực hiện quyết định phụ thuộc có thể thay thế.
- **Thư viện cung cấp API mặc định công khai:** một constructor tiện ích cố ý chọn implementation có thể chấp nhận được trong SDK nhỏ nếu hành vi được mô tả rõ và vẫn có lối inject để tùy biến. Đó là quyết định API có đánh đổi, không nên sao chép máy móc sang mọi lớp nghiệp vụ.

Một tín hiệu quan trọng là **đối tượng mới có hành vi phụ thuộc vào môi trường hay không**. Clock hệ thống, random generator, client kết nối ngoài, hệ thống file, bộ gửi email và database repository thường đáng được cung cấp tường minh nếu ứng dụng cần kiểm thử quyết định theo thời gian, dữ liệu hoặc I/O. Còn đối tượng dữ liệu đơn giản thường có thể được tạo cục bộ.

## 9. Quy trình refactor constructor đang tạo mặc định ngầm

Giả sử đang có:

```java
// Pseudocode: các lớp JdbcInvoiceRepository/SmtpInvoiceSender
// đại diện cho adapter thực tế của ứng dụng.
InvoiceService(InvoiceRepository repository, InvoiceSender sender) {
    this.repository = repository == null
            ? new JdbcInvoiceRepository()
            : repository;
    this.sender = sender == null
            ? new SmtpInvoiceSender()
            : sender;
}
```

Có thể refactor theo các bước:

1. **Xác định dependency bắt buộc:** `InvoiceService` có thể hoạt động hợp lệ nếu không có repository hoặc sender không? Nếu câu trả lời là không, không nên coi `null` là một lựa chọn hợp lệ.
2. **Sửa constructor thành hợp đồng rõ ràng:** gán `this.repository = Objects.requireNonNull(repository, "repository")` và tương tự với `sender`. Với những dependency có thể bỏ qua, mô tả tính tùy chọn thành một phần rõ ràng của API.
3. **Chuyển lựa chọn adapter ra composition root:** nơi khởi động đọc cấu hình, tạo repository và sender tương ứng, rồi gọi constructor với cả hai đối tượng.
4. **Làm rõ ownership và scope:** đảm bảo có chỗ đóng database pool/client khi ứng dụng kết thúc; không nhầm đối tượng gắn với request thành đối tượng chia sẻ toàn cục.
5. **Bổ sung kiểm thử có ý nghĩa:** test nghiệp vụ dùng fake, test khởi động phát hiện thiếu cấu hình, test tích hợp xác minh adapter thật.
6. **Bỏ những nhánh fallback cũ:** sau khi mọi đường tạo đối tượng đã được chuyển, xóa constructor không tham số hay hàm tạo ngầm không còn cần thiết.

Không cần DI container để làm các bước trên. Khi object graph lớn, container có thể hỗ trợ lắp ghép; tư duy kiểm soát phụ thuộc và fail-fast vẫn giữ nguyên.

## 10. Bài tập thực hành và câu hỏi tự đánh giá

**Bối cảnh:** `ReportService` tạo báo cáo, sử dụng `ReportRepository` để lấy dữ liệu và `ReportPublisher` để xuất báo cáo. Constructor hiện tại có hai fallback:

```java
// Pseudocode: chỉ minh họa hai dependency.
ReportService(ReportRepository repository, ReportPublisher publisher) {
    this.repository = repository != null
            ? repository
            : new SqlReportRepository();
    this.publisher = publisher != null
            ? publisher
            : new LocalFilePublisher();
}
```

Hãy thực hiện:

1. Nêu hai quyết định đang bị giấu trong constructor; chỉ rõ vì sao truyền `null` dễ gây lỗi cấu hình.
2. Viết lại constructor injection với `Objects.requireNonNull`; nếu hai dependency bắt buộc, hai trường nên có kiểu và phạm vi nhìn thấy như thế nào?
3. Phác thảo một `main` làm composition root để chọn `SqlReportRepository` và `LocalFilePublisher`. Chỉ rõ đối tượng nào có thể sở hữu tài nguyên cần đóng.
4. Tạo fake `ReportRepository` trả về dữ liệu cố định và fake `ReportPublisher` ghi nhớ báo cáo đã xuất; viết bài test xác minh `ReportService` sử dụng đúng chúng.
5. Giả sử môi trường demo muốn dùng repository trong bộ nhớ. Hãy chỉ ra cách chọn nó ở composition root mà không sửa `ReportService`.
6. Nếu `ReportPublisher` chỉ mang tính tùy chọn ở một use case, hãy đề xuất cách mô tả tính tùy chọn tường minh và điều kiện nào khiến No-Op publisher là không phù hợp.

**Đối chiếu định hướng:** `ReportService` nên phụ thuộc vào hợp đồng của repository và publisher; các triển khai cụ thể thuộc về nơi lắp ghép. Test dùng fake xác minh nghiệp vụ nhưng không thay kiểm thử SQL, file hoặc cấu hình runtime. Nếu báo cáo bắt buộc phải xuất, `NoOpReportPublisher` không được sử dụng để âm thầm che thiếu cấu hình.

**Ghi nhớ:** Constructor injection có giá trị vì nó **buộc caller công khai lựa chọn dependency bắt buộc** và giúp đối tượng được tạo ở trạng thái hợp lệ. Hãy báo lỗi sớm khi thiếu dependency, chuyển việc chọn implementation và quản lý tài nguyên về composition root, và chỉ giữ mặc định bên trong constructor khi chúng thực sự thuộc hợp đồng giá trị của đối tượng. Đây là nền tảng chắc chắn để học quản lý scope, vòng đời và mở rộng sang DI container về sau.

# Interface injection và hợp đồng dành cho thao tác cung cấp phụ thuộc

## 1. Bối cảnh: cung cấp phụ thuộc thông qua một hợp đồng bắt buộc

Trong **Dependency Injection (DI)**, một đối tượng nhận những thành phần nó cần từ bên ngoài, thay vì tự tạo hoặc tự tìm kiếm chúng. Đây là một cách áp dụng **Inversion of Control (IoC)**: việc khởi tạo và lắp ghép được chuyển ra ngoài lớp dùng phụ thuộc, thường tại **composition root**.

Có nhiều cách đưa phụ thuộc vào đối tượng: truyền qua constructor, thông qua phương thức setter, hoặc thông qua một **interface chuyên quy định thao tác nhận phụ thuộc**. Cách thứ ba gọi là **interface injection**.

Với interface injection, lớp **nhận phụ thuộc** phải triển khai một interface khai báo phương thức injection. Bên lắp ghép chỉ cần biết interface đó để gọi phương thức cung cấp dependency. Nhờ vậy, thao tác inject được mô tả bằng một hợp đồng có thể kiểm tra tại thời điểm biên dịch.

Ví dụ về hợp đồng injection:

```java
interface AuditSinkAware {
    void injectAuditSink(AuditSink auditSink);
}
```

Để có thể được cung cấp `AuditSink` theo hợp đồng này, lớp nghiệp vụ phải `implements AuditSinkAware` và hiện thực `injectAuditSink(...)`.

Điều cần phân biệt ngay từ đầu:

- **`AuditSink`** là *hợp đồng của dịch vụ được sử dụng*: nó mô tả đối tượng ghi nhật ký hoạt động được phép làm gì.
- **`AuditSinkAware`** là *hợp đồng của đối tượng cần nhận dịch vụ*: nó mô tả cách cung cấp `AuditSink` cho đối tượng đó.
- Một method có tên `setAuditSink` **chưa đủ** để coi là interface injection. Dấu hiệu đặc trưng là **lớp nhận triển khai một interface dành cho injection**, và bên lắp ghép gọi nó thông qua hợp đồng đó.

Bài này đi từ Java thuần đến các đánh đổi về thời điểm lắp ghép, khả năng kiểm thử, scope và vòng đời, trước khi quyết định liệu có cần DI container hay không.

## 2. Cấu trúc và luồng điều khiển

Giả sử `OrderService` cần `AuditSink` để ghi lại sự kiện đơn hàng đã xác nhận.

```text
        COMPOSITION ROOT / INJECTOR
                 |
                 | tạo AuditSink
                 | tạo OrderService
                 | gọi injectAuditSink(...)
                 v
       AuditSinkAware (injection interface)
                 ^
                 | implements
             OrderService
                 |
                 | dùng trong nghiệp vụ
                 v
             AuditSink (service interface)
                 ^
                 | implements
          ConsoleAuditSink
```

Luồng này có bốn bước:

1. Nơi lắp ghép tạo một implementation của `AuditSink`.
2. Nơi lắp ghép tạo `OrderService`, lúc này đối tượng chưa có dependency bắt buộc.
3. Bên lắp ghép nhìn `OrderService` qua kiểu `AuditSinkAware`, rồi gọi `injectAuditSink(...)`.
4. Sau khi lắp ghép xong, đối tượng có thể xử lý nghiệp vụ và sử dụng `AuditSink`.

Đặc điểm ở bước 2 tạo ra điểm đánh đổi quan trọng: **interface injection thường để đối tượng tồn tại tạm thời ở trạng thái chưa được cấu hình đầy đủ**. Nếu có thể tạo dependency ngay khi tạo đối tượng, constructor injection thường tránh được trạng thái trung gian này.

## 3. Ví dụ hoàn chỉnh với Java thuần

Ví dụ dưới đây không dùng framework, container hay thư viện kiểm thử. Toàn bộ mã sau nằm trong file `InterfaceInjectionDemo.java`:

```java
import java.util.Objects;

// Hợp đồng của phụ thuộc mà nghiệp vụ sử dụng.
interface AuditSink {
    void record(String event);
}

// Hợp đồng dành cho đối tượng CẦN nhận phụ thuộc.
interface AuditSinkAware {
    void injectAuditSink(AuditSink auditSink);
}

final class ConsoleAuditSink implements AuditSink {
    @Override
    public void record(String event) {
        System.out.println("AUDIT " + event);
    }
}

// Bên nhận phải triển khai hợp đồng injection.
final class OrderService implements AuditSinkAware {
    private AuditSink auditSink;

    @Override
    public void injectAuditSink(AuditSink auditSink) {
        Objects.requireNonNull(auditSink, "auditSink");

        // Chọn chính sách inject đúng một lần trong ví dụ này.
        if (this.auditSink != null) {
            throw new IllegalStateException(
                    "AuditSink đã được cung cấp trước đó");
        }

        this.auditSink = auditSink;
    }

    void confirm(String orderId, long totalVnd) {
        // Chặn việc dùng đối tượng trước khi lắp ghép xong.
        if (auditSink == null) {
            throw new IllegalStateException(
                    "Chưa inject AuditSink cho OrderService");
        }
        if (orderId == null || orderId.trim().isEmpty()) {
            throw new IllegalArgumentException("Mã đơn hàng không hợp lệ");
        }
        if (totalVnd <= 0) {
            throw new IllegalArgumentException("Tổng tiền phải dương");
        }

        auditSink.record("ORDER_CONFIRMED:" + orderId + ":" + totalVnd);
    }
}

public class InterfaceInjectionDemo {

    // Injector thủ công: phụ thuộc vào injection interface.
    static void wireAuditSink(AuditSinkAware receiver, AuditSink sink) {
        receiver.injectAuditSink(sink);
    }

    public static void main(String[] args) {
        // Composition root: chọn, tạo và lắp ghép các thành phần.
        AuditSink sink = new ConsoleAuditSink();
        OrderService orderService = new OrderService();

        wireAuditSink(orderService, sink);

        // Chỉ sử dụng sau khi quá trình injection hoàn tất.
        orderService.confirm("ORDER-007", 250_000);
    }
}
```

Biên dịch và chạy bằng JDK thông thường:

```bash
javac InterfaceInjectionDemo.java
java InterfaceInjectionDemo
```

Kết quả:

```text
AUDIT ORDER_CONFIRMED:ORDER-007:250000
```

### 3.1. Hợp đồng injection buộc lớp triển khai phương thức

Vì `OrderService implements AuditSinkAware`, Java yêu cầu lớp này cung cấp `injectAuditSink(AuditSink)` với chữ ký tương thích. Nếu bỏ phương thức mà không khai báo lớp `abstract`, mã sẽ không biên dịch.

Phần code lắp ghép:

```java
static void wireAuditSink(AuditSinkAware receiver, AuditSink sink) {
    receiver.injectAuditSink(sink);
}
```

không cần biết `receiver` là `OrderService` hay một lớp khác, miễn là lớp đó đáp ứng `AuditSinkAware`. Đây là ích lợi cụ thể của một **hợp đồng injection có kiểu tường minh**.

Tuy nhiên, kiểm tra lúc biên dịch chỉ chứng minh phương thức tồn tại. Java không tự bảo đảm phương thức ấy thật sự lưu dependency, kiểm tra `null`, chỉ được gọi một lần, hay luôn được gọi **trước khi** dùng đối tượng. Các nghĩa vụ đó thuộc về thiết kế và quá trình lắp ghép.

### 3.2. Chính sách inject đúng một lần

Ví dụ chọn quy tắc `injectAuditSink` chỉ được gọi **một lần** để tránh thay thế phụ thuộc khi dịch vụ đang hoạt động. Khi cố gọi lần thứ hai, nó ném `IllegalStateException`.

Đây là **quyết định của ví dụ**, không phải quy tắc bắt buộc của mọi interface injection. Một hệ thống có thể chủ ý hỗ trợ reconfiguration, nhưng khi đó phải quy định rõ thay đổi có được phép trong lúc nhiều luồng đang sử dụng đối tượng hay không, cách xử lý request đang chạy, và ai chịu trách nhiệm quản lý vòng đời của dependency cũ.

Đối tượng trong ví dụ được lắp ghép **trước khi đưa vào sử dụng**. Không nên gọi injection và xử lý nghiệp vụ đồng thời trên cùng một đối tượng chưa được công bố an toàn; cơ chế kiểm tra `null` và cờ inject một lần ở đây không đủ để làm quá trình khởi tạo đồng thời trở nên thread-safe.

## 4. Kiểm thử interface injection bằng fake

Ta thay `ConsoleAuditSink` bằng fake giữ lại sự kiện đã nhận. Tạo file `InterfaceInjectionTest.java` trong cùng thư mục với file trên:

```java
final class RecordingAuditSink implements AuditSink {
    String lastEvent;
    int callCount;

    @Override
    public void record(String event) {
        lastEvent = event;
        callCount++;
    }
}

public class InterfaceInjectionTest {
    public static void main(String[] args) {
        OrderService service = new OrderService();

        // Đối tượng chưa inject phải từ chối xử lý.
        boolean rejectedBeforeInjection = false;
        try {
            service.confirm("ORDER-TEST", 100_000);
        } catch (IllegalStateException expected) {
            rejectedBeforeInjection = true;
        }
        if (!rejectedBeforeInjection) {
            throw new AssertionError("Thiếu kiểm tra trạng thái injection");
        }

        // Inject fake thông qua đúng interface.
        RecordingAuditSink fake = new RecordingAuditSink();
        AuditSinkAware receiver = service;
        receiver.injectAuditSink(fake);

        service.confirm("ORDER-TEST", 100_000);
        if (fake.callCount != 1
                || !"ORDER_CONFIRMED:ORDER-TEST:100000"
                        .equals(fake.lastEvent)) {
            throw new AssertionError("Ghi sự kiện không đúng");
        }

        // Ví dụ yêu cầu inject tối đa một lần.
        boolean rejectedSecondInjection = false;
        try {
            receiver.injectAuditSink(new RecordingAuditSink());
        } catch (IllegalStateException expected) {
            rejectedSecondInjection = true;
        }
        if (!rejectedSecondInjection) {
            throw new AssertionError("Không chặn inject lần thứ hai");
        }

        System.out.println("PASS");
    }
}
```

Chạy:

```bash
javac InterfaceInjectionDemo.java InterfaceInjectionTest.java
java InterfaceInjectionTest
```

Kết quả: `PASS`.

Bài kiểm thử trên xác nhận ba đặc tính: không dùng trước khi inject, hành vi nghiệp vụ gọi đúng collaborator fake, và không inject lần hai. Nó không chứng minh cách ghi audit ra hệ thống thực tế hoạt động đúng; adapter thật vẫn cần kiểm thử tích hợp phù hợp.

Không cần mock framework hay DI container để thực hành interface injection. Về mặt kiểm thử, khác biệt lớn nhất so với constructor injection là test phải **tạo đối tượng, inject, rồi mới được sử dụng**. Thiếu bước giữa có thể tạo lỗi chỉ xuất hiện khi chạy.

## 5. Interface injection khác constructor injection và setter injection ra sao?

Ba cách truyền phụ thuộc thường gặp khác nhau chủ yếu ở **nơi hợp đồng được thể hiện** và **thời điểm dependency có mặt**.

| Tiêu chí | Constructor injection | Setter/method injection | Interface injection |
| --- | --- | --- | --- |
| Cách truyền | Qua tham số constructor. | Qua phương thức công khai, thường là setter. | Qua phương thức được khai báo trong **injection interface** mà lớp nhận triển khai. |
| Hợp đồng bắt buộc của lớp nhận | Chữ ký constructor. | Chữ ký method của chính lớp nhận; không cần interface injection riêng. | Interface quy định method injection, được Java kiểm tra khi triển khai. |
| Trạng thái ngay sau khởi tạo | Dependency bắt buộc đã có nếu constructor chạy thành công. | Có thể chưa có dependency. | Có thể chưa có dependency trước khi injector gọi method. |
| Thay dependency sau khởi tạo | Thường không cần; có thể giữ trường `final`. | Có thể cho phép, tùy thiết kế. | Tùy contract và implementation; không mặc định cho phép re-inject. |
| Độ phức tạp bổ sung | Constructor dài nếu lớp có quá nhiều dependency. | Cần đảm bảo thứ tự cấu hình và sử dụng. | Cần thêm injection interface và kiểm soát thứ tự lắp ghép. |
| Trường hợp phù hợp | Phần lớn dependency bắt buộc của nghiệp vụ. | Thành phần tùy chọn hoặc thay đổi cấu hình có kiểm soát. | Framework/plugin có hợp đồng chuẩn để cung cấp dependency sau khi tạo đối tượng. |

### 5.1. Constructor injection: phụ thuộc bắt buộc được cung cấp ngay

Cùng `AuditSink`, nếu sử dụng constructor injection, `OrderService` có thể viết:

```java
// Ví dụ minh họa riêng, không đặt trùng tên class trong cùng file demo.
final class ConstructorOrderService {
    private final AuditSink auditSink;

    ConstructorOrderService(AuditSink auditSink) {
        this.auditSink = java.util.Objects.requireNonNull(
                auditSink, "auditSink");
    }

    void confirm(String orderId, long totalVnd) {
        auditSink.record("ORDER_CONFIRMED:" + orderId + ":" + totalVnd);
    }
}
```

Lớp này không có trạng thái “đã tạo nhưng chưa inject”. Một composition root có thể tạo `new ConstructorOrderService(sink)` rồi sử dụng ngay. Đây thường là lựa chọn mặc định cho dependency cần có để lớp hoạt động đúng.

Nếu chỉ cần đảm bảo rằng `OrderService` nhận `AuditSink`, không có yêu cầu đặc biệt về lifecycle hay hợp đồng do framework chỉ định, **interface injection thêm một bước mà constructor injection có thể tránh được**.

### 5.2. Setter injection: method được gọi nhưng không bắt buộc theo interface riêng

```java
final class SetterOrderService {
    private AuditSink auditSink;

    public void setAuditSink(AuditSink auditSink) {
        this.auditSink = java.util.Objects.requireNonNull(
                auditSink, "auditSink");
    }
}
```

Đây là setter injection khi bên ngoài gọi `setAuditSink(...)` để cung cấp dependency. Không có `AuditSinkAware` hay interface tương đương mà lớp phải triển khai.

Nếu thêm `implements AuditSinkAware` và thực hiện đúng `injectAuditSink(...)`, thiết kế mới có đặc trưng **interface injection**. Hai cách có thể dùng phương thức trông rất giống nhau, nhưng khác ở chỗ **interface injection chuẩn hóa thao tác cấp dependency thành một hợp đồng riêng**.

### 5.3. DI container và các method được gắn annotation

Một số DI container có thể gọi setter hoặc method được đánh dấu bằng annotation, ví dụ một method có `@Inject` theo chuẩn thư viện thích hợp. **Method injection dựa trên annotation không mặc nhiên là interface injection**: nếu lớp không triển khai interface quy định thao tác nhận dependency, thì không có hợp đồng kiểu `AuditSinkAware` như trong bài này.

Mặt khác, một framework có thể định nghĩa interface callback mà các lớp triển khai để nhận đối tượng framework cung cấp. Cách đó *có thể* mang hình thức interface injection, nhưng cần xem rõ contract và cơ chế framework cụ thể. Không nên nhầm việc nhận cả một container rồi tự gọi `get(...)` ở mọi nơi với một ranh giới DI tốt: nó dễ biến thành **Service Locator**, che giấu dependency thật và khiến logic nghiệp vụ phụ thuộc vào cơ chế tra cứu của framework.

## 6. Khi nào interface injection có giá trị?

Interface injection phù hợp nhất khi **bên tạo hoặc quản lý đối tượng có quyền áp đặt một hợp đồng injection thống nhất**, đặc biệt nếu đối tượng đã được khởi tạo trước lúc có đủ dependency.

### 6.1. Hệ thống plugin hoặc extension

Ví dụ, một plugin được một cơ chế mở rộng tạo bằng constructor không tham số. Sau đó host muốn cung cấp một `AuditSink` cho những plugin hỗ trợ ghi audit:

```java
// Minh họa API của host, không phụ thuộc framework cụ thể.
static void configurePlugin(Object plugin, AuditSink sink) {
    if (plugin instanceof AuditSinkAware) {
        ((AuditSinkAware) plugin).injectAuditSink(sink);
    }
}
```

Host không cần biết lớp plugin cụ thể, chỉ cần biết plugin có thực thi `AuditSinkAware` hay không. Tuy vậy, nếu `AuditSink` là **dependency bắt buộc** của mọi plugin, gọi injection có điều kiện rồi bỏ qua trường hợp không triển khai interface sẽ tạo lỗi tiềm ẩn. Khi đó host nên áp đặt contract bắt buộc ở API plugin hoặc báo lỗi cấu hình ngay.

### 6.2. Đối tượng được tạo bởi một bên thứ ba

Có trường hợp thư viện hoặc framework kiểm soát việc khởi tạo, trong khi ứng dụng chỉ nhận đối tượng sau đó. Nếu không thể thay đổi constructor và có một API chính thức để cung cấp dependency, interface injection giúp hợp thức hóa bước bổ sung đó.

Tuy nhiên, trước khi chọn cách này, hãy kiểm tra xem framework đã có constructor factory, adapter hoặc lifecycle callback phù hợp chưa. Không nên bổ sung một hệ thống injection riêng khi cơ chế khởi tạo được thiết kế tốt đã giải quyết được vấn đề.

### 6.3. Bắt buộc một nhóm đối tượng thực hiện cùng thao tác cung cấp phụ thuộc

Nếu nhiều đối tượng thật sự cần một dependency có cùng vai trò và host chịu trách nhiệm inject, việc triển khai chung `AuditSinkAware` cho phép host lắp ghép qua một kiểu tường minh. Nhưng nếu các đối tượng có nhu cầu khác nhau, một interface quá rộng như `AllDependenciesAware` với hàng chục phương thức sẽ tạo coupling và làm khó việc phát triển độc lập.

Thiết kế nên ưu tiên **interface nhỏ, đúng vai trò**; chỉ những lớp thật sự cần `AuditSink` mới phải triển khai `AuditSinkAware`.

## 7. Những chi phí và giới hạn cần nhận diện

### 7.1. Trạng thái chưa hoàn chỉnh và thứ tự khởi tạo

Nguy cơ lớn nhất của interface injection là lớp có thể được tạo ra trước khi nhận phụ thuộc bắt buộc. Đối tượng có thể bị sử dụng quá sớm, hoặc một đường khởi tạo nào đó quên gọi injector.

Trong ví dụ, `confirm(...)` báo lỗi rõ ràng nếu `auditSink == null`. Đây là biện pháp phát hiện lỗi khi chạy, không thể thay thế đảm bảo từ constructor injection. Khi dùng interface injection, cần có **quy tắc về thời điểm hoàn thành lắp ghép** và kiểm tra fail-fast tại ranh giới bắt đầu sử dụng hoặc khởi động hệ thống.

### 7.2. Ràng buộc của injection interface

Lớp nhận phải biết và triển khai `AuditSinkAware`. Nếu interface này do một framework định nghĩa, lớp có thể phải biết về framework đó; thay framework sẽ khiến code nhận dependency cần thay đổi. Nếu interface là hợp đồng thuộc ứng dụng, coupling với framework giảm đi, nhưng vẫn có thêm loại và phương thức cần duy trì.

Điểm cân nhắc không phải “có interface là tốt”: cần hỏi **hợp đồng này đem lại ích lợi thực tế nào cho bên lắp ghép**. Nếu bên lắp ghép chỉ tạo một loại đối tượng cụ thể, interface injection có thể dư thừa.

### 7.3. Sự nhất quán khi inject lại và việc dùng đồng thời

Nếu method injection cho phép thay dependency sau khi khởi tạo, đối tượng có thể quan sát hai triển khai khác nhau giữa các lần sử dụng. Trong môi trường đa luồng, việc ghi lại tham chiếu dependency còn đòi hỏi cơ chế an toàn bộ nhớ và quy tắc đồng bộ phù hợp.

Ví dụ ở mục 3 chọn inject một lần và chỉ xuất bản đối tượng sau khi lắp ghép hoàn tất. Lựa chọn này giúp phạm vi hành vi dễ lý giải, nhưng **không biến quá trình inject thành thread-safe** nếu nhiều luồng tự ý gọi nó đồng thời.

### 7.4. Scope và vòng đời của collaborator

Dependency có thể là một đối tượng dùng chung, đối tượng mới cho từng tác vụ hoặc đối tượng gắn với một request. Nếu inject một collaborator giữ trạng thái của người dùng vào dịch vụ tồn tại xuyên suốt nhiều request, nguy cơ lẫn dữ liệu vẫn xuất hiện như ở các phương pháp DI khác.

Nếu dependency sở hữu file, connection, socket hay executor, contract phải quy định ai tạo và ai đóng. Việc implement `AuditSinkAware` **không tự chuyển quyền sở hữu tài nguyên** cho `OrderService`, và không tự gọi `close()`. DI container có thể hỗ trợ lifecycle, nhưng vẫn cần scope và cấu hình đúng.

### 7.5. Kiểm thử và quan sát lỗi

Test phải nhớ gọi đúng trình tự `new` → `inject` → `use`. Khác với constructor injection, một test vô tình bỏ bước inject vẫn biên dịch được và có thể chỉ thất bại lúc chạy.

Vì vậy, một bộ kiểm thử thích hợp nên bao gồm: hành vi khi chưa inject, kiểm tra `null`, quy tắc inject lại, thực thi với fake, và thử khởi tạo cả object graph bằng cấu hình mà ứng dụng thực tế sử dụng.

## 8. Hướng dẫn lựa chọn phương pháp

| Tình huống | Gợi ý | Lý do |
| --- | --- | --- |
| Dependency cần có để nghiệp vụ luôn hoạt động đúng; tự kiểm soát quá trình tạo đối tượng | **Constructor injection** | Làm rõ yêu cầu ngay khi khởi tạo, có thể giữ trường `final`, tránh trạng thái trung gian. |
| Dependency thật sự tùy chọn hoặc cần cấu hình muộn, không có contract injection chung | **Setter/method injection** nếu có lợi ích cụ thể | Không phải thêm một interface chỉ để gọi một setter. |
| Host/plugin framework yêu cầu một nhóm đối tượng nhận cùng loại dependency qua một contract | **Interface injection** | Host có thể gọi injection qua interface và kiểm tra lớp triển khai tại compile time. |
| Logic tạo và dùng dependency đang nằm lẫn trong lớp nghiệp vụ | **Tách composition root** trước | Tập trung quyết định triển khai, scope và vòng đời bên ngoài nghiệp vụ. |
| Object graph lớn, nhiều scope/cấu hình | **Cân nhắc DI container** | Container có thể giảm việc lắp ghép thủ công, nhưng không bắt buộc để có DI. |
| Value object, DTO hoặc phép tính đơn giản không có collaborator cần hoán đổi | **Tạo trực tiếp** | Không tăng độ phức tạp vô ích. |

Có thể tự trả lời bốn câu hỏi trước khi chọn interface injection:

1. **Ai tạo đối tượng nhận dependency?** Có thực sự không thể dùng constructor để nhận dependency ngay từ đầu không?
2. **Ai gọi injection method?** Có một injector hoặc framework cần làm việc với nhiều implementation thông qua cùng một contract không?
3. **Khi nào đối tượng hợp lệ để sử dụng?** Có bảo đảm injection hoàn tất và báo lỗi sớm nếu thiếu dependency không?
4. **Ai quản lý scope, thay thế và giải phóng dependency?** Quy tắc đó có được ghi rõ và có kiểm thử phù hợp không?

Nếu câu trả lời cho hai câu đầu không thể hiện một nhu cầu thực tế, constructor injection thường đơn giản và an toàn hơn cho dependency bắt buộc.

## 9. Bài tập thực hành: thiết kế contract injection cho bộ xử lý báo cáo

**Bối cảnh:** một host tạo các `ReportProcessor` từ plugin bằng constructor không tham số. Sau khi tạo, host cần cung cấp `ReportStore` để plugin lưu kết quả. Một số plugin không cần lưu dữ liệu.

Thực hiện các yêu cầu:

1. Định nghĩa `ReportStore` với một phương thức `save(String reportId, String content)`.
2. Định nghĩa `ReportStoreAware` với `injectReportStore(ReportStore store)`. Cho `PersistingReportProcessor` triển khai interface này và mô tả trạng thái trước/sau injection.
3. Viết một hàm `configurePlugin(Object plugin, ReportStore store)` kiểm tra `instanceof ReportStoreAware` và inject nếu được hỗ trợ.
4. Viết fake `ReportStore` ghi nhớ số lần gọi `save` để kiểm tra plugin sử dụng dependency đúng.
5. Phân tích điều gì phải thay đổi nếu **mọi plugin** đều bắt buộc có `ReportStore`, hoặc nếu host có thể truyền dependency vào constructor ngay từ đầu.

**Gợi ý tự đối chiếu:** nếu việc lưu báo cáo chỉ dành cho một số plugin, interface injection có thể là hợp đồng tùy chọn của host. Nếu tất cả plugin đều bắt buộc nhận `ReportStore`, host cần contract bắt buộc và xác thực rõ ràng; cách dùng `instanceof` rồi bỏ qua không triển khai sẽ che lỗi. Nếu chủ động tạo plugin bằng constructor với đầy đủ dependency, constructor injection thường diễn đạt yêu cầu tốt hơn.

**Điểm cần nhớ:** Interface injection đặc trưng bởi **hợp đồng dành cho đối tượng nhận dependency**. Cơ chế này giúp bên lắp ghép gọi thao tác cung cấp phụ thuộc qua một kiểu chung, nhưng cũng tạo thêm interface và trạng thái có thể chưa được cấu hình. Với hầu hết dependency bắt buộc trong Java thuần, hãy ưu tiên constructor injection tại composition root. Chỉ dùng interface injection khi yêu cầu về host, plugin hoặc vòng đời đối tượng thật sự cần hợp đồng cấp phụ thuộc riêng.

# Thứ tự ưu tiên cấu hình cụ thể so với cấu hình mặc định của @Transactional

## 1. Vấn đề: nhiều nơi cùng khai báo transaction thì Spring nghe ai?

Trong Spring Framework, `@Transactional` mô tả cách quản lý transaction cho lời gọi một phương thức: propagation, isolation, read-only, timeout, rollback rules và transaction manager. Khi cùng một service có cấu hình trên **lớp**, **phương thức**, đôi khi cả **interface/lớp cha**, người đọc dễ nhầm Spring sẽ gộp từng thuộc tính, hoặc lấy một giá trị "mặc định" từ lớp rồi chỉ thay thuộc tính được ghi ở phương thức.

Quy tắc cần nắm: **khai báo transaction ở vị trí cụ thể nhất có hiệu lực cho phương thức được gọi sẽ được ưu tiên**. Trong tình huống phổ biến, `@Transactional` đặt **trực tiếp trên method của lớp triển khai** thắng `@Transactional` đặt ở **cấp lớp**. Nếu method không khai báo, cấu hình ở lớp là chính sách dự phòng cho các method thuộc phạm vi mà Spring nhận diện.

Điểm quan trọng thứ hai: **một annotation ở method không được hợp nhất từng thuộc tính với annotation ở class**. Ví dụ class khai báo `readOnly = true`, method chỉ viết `@Transactional` thì method lấy **các mặc định của chính annotation**: `readOnly = false`, `propagation = REQUIRED`, ...; không ngầm thừa hưởng `readOnly = true` hoặc các `rollbackFor` ở lớp.

Điểm quan trọng thứ ba: **chọn cấu hình metadata khác với thực tế tạo transaction vật lý**. Method có cấu hình riêng nhưng `PROPAGATION_REQUIRED` tham gia transaction đã mở thì một số thiết lập ở method không thay được thuộc tính của transaction ngoài.

Bài học phân biệt ba câu hỏi độc lập:

1. **Spring chọn annotation ở đâu?** Method cụ thể, class, nơi được kế thừa, hay không có annotation.
2. **Các thuộc tính của annotation được giải nghĩa ra sao?** Giá trị ghi tường minh so với mặc định của `@Transactional`, rollback rule và default của manager.
3. **Transaction thực sự nhận thuộc tính nào?** Tạo transaction mới hay tham gia một transaction vật lý đã tồn tại; có proxy/transaction advice hoạt động hay không.

## 2. Những giá trị mặc định khi dùng @Transactional

Nếu method có `@Transactional` nhưng không khai báo thêm thuộc tính, về cơ bản Spring dùng các giá trị sau (khi không có cấu hình mặc định toàn cục đã được thay đổi):

| Thuộc tính | Mặc định của `@Transactional` | Ý nghĩa |
| --- | --- | --- |
| `propagation` | `Propagation.REQUIRED` | Không có transaction phù hợp thì tạo; có rồi thì tham gia |
| `isolation` | `Isolation.DEFAULT` | Không ép một isolation riêng; dùng isolation mặc định của hệ transaction/DB |
| `readOnly` | `false` | Transaction đọc-ghi; `true` là hint, không phải cơ chế phân quyền |
| `timeout` | `TransactionDefinition.TIMEOUT_DEFAULT` (-1) | Dùng default timeout của transaction manager/hệ nền, hoặc không giới hạn khi không có hỗ trợ |
| `rollbackFor`, `noRollbackFor` | Mảng rỗng | Mặc định rollback với `RuntimeException` hoặc `Error`; thường không rollback với checked `Exception` |
| `transactionManager`/`value` | Chuỗi rỗng | Không chỉ định manager riêng trên annotation; dùng cơ chế chọn manager của Spring |
| `label` | Mảng rỗng | Không thêm nhãn giao dịch tùy chọn |

**Hai kiểu “mặc định” không nên đánh đồng:**

- `@Transactional` ở **cấp class** là **mặc định theo vị trí** cho method không có annotation cụ thể hơn.
- Các giá trị trong bảng là **mặc định của thuộc tính annotation** khi bạn viết `@Transactional` mà không cung cấp giá trị, hoặc chỉ cung cấp một phần thuộc tính.

Ví dụ `@Transactional(readOnly = true)` vẫn sử dụng `REQUIRED` và rollback rules mặc định. Ngược lại, khi có annotation ở method chỉ chứa `propagation = REQUIRES_NEW`, các thuộc tính khác của **annotation method** nhận giá trị mặc định của chúng; chúng không lấy các giá trị còn thiếu từ annotation class.

`Isolation.DEFAULT` không có nghĩa “READ_COMMITTED trong mọi DB”. Timeout mặc định không phải một số giây cố định; còn `readOnly = true` có thể chỉ là gợi ý tối ưu cho driver/ORM. Những chi tiết này phụ thuộc manager và tài nguyên đang dùng.

## 3. Cấu hình ở method ưu tiên hơn cấu hình ở class

Xét một service Spring:

~~~java
@Service
@Transactional(readOnly = true)
public class CatalogService {
    public Product findById(long id) {
        // Không có @Transactional riêng:
        // được áp dụng metadata readOnly=true ở class.
        return repository.findById(id).orElseThrow();
    }

    @Transactional(readOnly = false, propagation = Propagation.REQUIRES_NEW)
    public void changePrice(long id, long newPrice) {
        // Metadata method ưu tiên:
        // readOnly=false và REQUIRES_NEW.
        repository.updatePrice(id, newPrice);
    }

    @Transactional
    public void refreshCounters() {
        // Toàn bộ metadata @Transactional method được chọn.
        // readOnly=false, propagation=REQUIRED theo mặc định annotation.
        repository.refreshCounters();
    }
}
~~~

Đây là **đoạn minh họa**, không phải chương trình chạy độc lập: `Product`, `repository` và các phương thức dữ liệu chưa được định nghĩa. Giả định ba method được gọi từ ngoài qua Spring proxy và không có transaction bao ngoài, ta suy ra:

| Method | Annotation được chọn | Propagation hiệu lực | Read-only được yêu cầu |
| --- | --- | --- | --- |
| `findById` | Class `@Transactional(readOnly=true)` | `REQUIRED` | `true` |
| `changePrice` | Method `@Transactional(readOnly=false, propagation=REQUIRES_NEW)` | `REQUIRES_NEW` | `false` |
| `refreshCounters` | Method `@Transactional` | `REQUIRED` | `false` |

Điều thường bị bỏ sót nằm ở `refreshCounters`: dù không viết `readOnly=false`, method **không bị giữ read-only theo class**. Chỉ riêng việc đặt một `@Transactional` mới trên method đã khiến Spring chọn metadata method đó.

Một ví dụ sắc nét hơn về thuộc tính không được ghép từng phần:

~~~java
@Transactional(
    readOnly = true,
    propagation = Propagation.SUPPORTS,
    rollbackFor = IOException.class,
    transactionManager = "catalogTx"
)
public class CatalogService {
    @Transactional(timeout = 10)
    public void updateItem() {
        // Annotation method được chọn đầy đủ.
    }
}
~~~

Giả định `CatalogService` được Spring quản lý và advice áp dụng, cấu hình của `updateItem()` là:

- `timeout = 10` giây (ghi ở method).
- `propagation = REQUIRED` (default của annotation method), **không phải** `SUPPORTS` từ class.
- `readOnly = false` (default của annotation method), **không phải** `true` từ class.
- Không có `rollbackFor = IOException.class` từ class; dùng rollback rule mặc định cho method, trừ khi có global default được cấu hình thêm.
- `transactionManager` của method là chuỗi rỗng; **không mặc nhiên lấy** `"catalogTx"` từ class. Spring sẽ giải quyết manager theo cơ chế mặc định/qualifier phù hợp.

Nếu một method bắt buộc giữ manager và rollback rule ở cấp class nhưng cần sửa riêng timeout, hãy **khai báo lại các thuộc tính bắt buộc đó ở annotation method**, hoặc dùng annotation tổng hợp (composed annotation) có chính sách nhất quán. Đừng cho rằng Spring “thừa kế phần còn thiếu” của annotation class.

## 4. Đồ thị quyết định: chọn metadata rồi mới quyết định giao dịch

~~~mermaid
flowchart TD
    A["Caller gọi method qua Spring proxy"] --> B{"Transaction advice có hiệu lực?"}
    B -->|"Không"| X["Không áp dụng semantics @Transactional tại điểm gọi này"]
    B -->|"Có"| C{"Có metadata @Transactional<br/>trên method cụ thể nhất?"}
    C -->|"Có"| D["Chọn metadata của method"]
    C -->|"Không"| E{"Có metadata class / hierarchy<br/>được Spring nhận diện?"}
    E -->|"Có"| F["Chọn metadata class/hierarchy phù hợp"]
    E -->|"Không"| G["Không có transaction attribute cho method"]
    D --> H["Giải nghĩa toàn bộ thuộc tính<br/>và fallback mặc định"]
    F --> H
    H --> I["Chọn TransactionManager"]
    I --> J{"Propagation và transaction hiện tại?"}
    J -->|"Tạo transaction mới"| K["Áp dụng thuộc tính được hỗ trợ khi begin"]
    J -->|"Tham gia transaction có sẵn"| L["Dùng physical transaction ngoài;<br/>kiểm tra/đánh dấu rollback theo scope"]
    K --> M["Thực thi, commit/rollback"]
    L --> M
~~~

Đồ thị này là **quy trình đọc cấu hình**. Nó không mô tả một thứ tự tuyến tính cố định cho mọi trường hợp inheritance, bridge method và proxy. Quy tắc chính thức là vị trí **most derived** phù hợp có ưu tiên; khi có interface và superclass, cách chọn còn phụ thuộc phương thức cụ thể Spring đang phân giải.

**Không có annotation ở method và class** thì framework không tự dựng một transaction chỉ vì method gọi DAO. Tuy nhiên method có thể gọi repository tự khai báo transaction riêng hoặc chạy trong transaction do caller tạo; đó là ranh giới khác.

## 5. Khi có interface, superclass và lớp triển khai

Trong dự án thực tế, một method có thể xuất hiện ở interface, superclass, và implementation. Cách tiếp cận an toàn là đặt semantics quan trọng **trên method public của concrete service class**, để người đọc và proxy cùng nhận thấy cấu hình cần áp dụng.

### 5.1. Lớp triển khai có cấu hình cụ thể

~~~java
public interface PaymentOperations {
    void submit();
}

@Transactional(readOnly = true)
public class PaymentService implements PaymentOperations {
    @Override
    @Transactional(readOnly = false, rollbackFor = IOException.class)
    public void submit() {
        // Metadata trực tiếp trên PaymentService.submit được ưu tiên.
    }
}
~~~

Đoạn code minh họa metadata; `IOException` là ví dụ rule, method này không thực sự ném IOException. Nếu method không có `@Transactional` riêng, class-level `readOnly=true` sẽ là fallback cho method của class thuộc phạm vi được Spring áp dụng.

### 5.2. Không suy ra một thứ tự cứng cho mọi tình huống kế thừa

- Nếu **implementation method** khai báo trực tiếp `@Transactional`, nó là vị trí cụ thể cần được ưu tiên trong tình huống phổ biến.
- Annotation trên **concrete class** thường dùng làm chính sách chung cho các method được khai báo/áp dụng trong class.
- Spring có thể tìm annotation trên method/type của **interface hoặc superclass** trong proxy mode; không nên xem một thứ tự ưu tiên tự viết trên giấy là bảo đảm cho mọi biến thể overload, bridge method, proxy hoặc metadata tổng hợp.
- Tài liệu Spring lưu ý: annotation **ở cấp subclass** không tự áp dụng ngược cho các method **chỉ được khai báo trong ancestor class**; khi cần chính sách subclass bao phủ inherited method, hãy **redeclare/override** method ở subclass và kiểm chứng.
- Với interface annotation, Spring có thể hỗ trợ trong proxy mode (bao gồm class-based proxy từ Spring 5.0), nhưng **AspectJ weaving không thừa hưởng annotation từ interface theo Java**. Do đó Spring khuyến nghị chú thích concrete class/method, tránh trông chờ interface-only metadata khi đổi cơ chế AOP.

Cùng tên method nhưng khác tham số là **overload khác nhau**; đặt `@Transactional` trên `save(String)` không làm nó tự áp dụng cho `save(long)`, trừ khi có cấu hình class-level hoặc metadata khác ở method thứ hai.

### 5.3. Composed annotation là một nguồn metadata có thể tái sử dụng

Ví dụ nếu phần lớn method ghi cần cùng manager và rollback rule:

~~~java
import java.io.IOException;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.transaction.annotation.Transactional;

@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@Transactional(transactionManager = "catalogTx", rollbackFor = IOException.class)
public @interface CatalogWriteTx {
}
~~~

Sau đó đặt `@CatalogWriteTx` trên method cần quy tắc này. Nó là **meta-annotation** có semantics giao dịch, không chỉ là nhãn trang trí. Cần có bean transaction manager tương ứng và cấu hình Spring AOP hợp lệ. Nếu đặt thêm một `@Transactional` riêng trên chính method hoặc phối hợp nhiều annotation transaction cạnh tranh, đừng đoán cách merge; giữ một chính sách rõ ràng, tránh cấu hình nhập nhằng.

## 6. Rollback rule: mức ưu tiên **bên trong một annotation** khác với mức ưu tiên của annotation

Hai khái niệm dễ bị nhầm:

- **Ưu tiên nơi khai báo:** method-level annotation được chọn trước class-level annotation. Các rule ở class không tự được ghép vào annotation ở method.
- **Ưu tiên giữa rollback rules đã có trong cùng cấu hình được chọn:** khi một exception khớp nhiều rule, rule khớp **cụ thể nhất (strongest match)** thắng.

Ví dụ:

~~~java
@Transactional(
    rollbackFor = Exception.class,
    noRollbackFor = DuplicateOrderException.class
)
public void persistOrder() {
    // ...
}
~~~

Giả sử `DuplicateOrderException extends RuntimeException`, exception này khớp cả `Exception.class` và `DuplicateOrderException.class`; vì rule `noRollbackFor` cụ thể hơn nên policy yêu cầu **không rollback vì loại exception đó**. Với một subclass khác của `Exception` không khớp rule ngoại lệ hẹp, `rollbackFor=Exception.class` vẫn áp dụng.

Ví dụ về **ưu tiên nơi khai báo**:

~~~java
@Transactional(rollbackFor = IOException.class)
public class ImportService {
    @Transactional
    public void importData() throws IOException {
        // Nếu IOException thoát khỏi proxy, annotation method
        // không giữ rollbackFor=IOException.class của class.
    }
}
~~~

Ở cấu hình mặc định của Spring Framework 6.1/6.2, method `importData` sẽ **không yêu cầu rollback chỉ vì checked IOException**; transaction có thể commit trước khi exception được chuyển tiếp. Nếu muốn rollback:

~~~java
@Transactional(rollbackFor = IOException.class)
public void importData() throws IOException {
    // ...
}
~~~

Đặt rule **trực tiếp ở method**. Nếu class cũng dùng `readOnly`, `transactionManager` hay propagation riêng, lặp lại các thuộc tính thiết yếu tại method khi cần, vì Spring không tự gộp chúng.

**Ưu tiên dùng rule kiểu `Class`**, ví dụ `rollbackFor = IOException.class` hoặc `noRollbackFor = BusinessException.class`. Các rule `rollbackForClassName`/`noRollbackForClassName` khớp chuỗi con tên exception, có thể vô tình khớp `CustomExceptionV2` hoặc inner class, nên không xem pattern gần giống tên là “match chính xác”.

Ngoài checked exception, theo mặc định Spring rollback khi `RuntimeException`/`Error` **thoát khỏi ranh giới được advice quản lý**. Nếu method nuốt exception rồi trả về bình thường, proxy không quan sát được nó; điều này không được sửa bởi bất cứ quy tắc ưu tiên annotation nào.

## 7. Mặc định toàn cục, manager và các phiên bản Spring

Có nhiều loại “global default”. Nên đặt chúng đúng tầng:

### 7.1. @EnableTransactionManagement kích hoạt cơ chế, không tự ghi đè method

`@EnableTransactionManagement` (hoặc `<tx:annotation-driven/>` trong XML) bật infrastructure xử lý transaction annotation cho các bean thuộc application context phù hợp. Nó có thiết lập như `mode` (proxy/AspectJ), kiểu proxy và `order` của advice.

**`order` của transaction advice không phải thứ tự ưu tiên giữa `@Transactional` ở method và class.** Nó điều khiển thứ tự advice/AOP so với advice khác (logging, retry...), không khiến class-level metadata thắng method-level.

Nếu không có transaction advice thực sự được áp dụng, tranh luận method-level hay class-level sẽ không tạo ra rollback trong thực tế. Trong proxy mode, lời gọi `this.anotherTransactionalMethod()` không đi qua proxy, nên annotation của method được gọi **không tạo transaction boundary mới**.

### 7.2. Default transaction manager

Khi annotation không chỉ định `transactionManager`, Spring dùng cơ chế tìm default transaction manager: một manager phù hợp đã được cấu hình/định danh, `TransactionManagementConfigurer` hoặc qualifier trên bean/class trong những tình huống hỗ trợ. Với nhiều manager, nên chỉ định rõ để tránh nhầm nguồn dữ liệu.

~~~java
@Transactional(transactionManager = "ordersTx", readOnly = true)
class OrdersService {
    @Transactional(readOnly = false)
    public void saveOrder() {
        // Method này KHÔNG tự thừa hưởng "ordersTx" từ annotation class.
        // Cần xác minh manager mặc định hoặc khai báo lại ordersTx tại method.
    }
}
~~~

Cách tường minh:

~~~java
@Transactional(transactionManager = "ordersTx", readOnly = false)
public void saveOrder() {
    // ...
}
~~~

Hai đoạn chỉ minh họa annotation; chưa có bean `ordersTx` và implementation method nên chưa thể chạy độc lập. **Mặc định chọn manager** và **default của thuộc tính annotation** là hai vấn đề khác nhau.

### 7.3. Default rollback toàn cục từ Spring Framework 6.2

Trong Spring Framework **6.2+**, có thể đổi policy rollback mặc định cho mọi checked exception:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.RollbackOn;

@Configuration
@EnableTransactionManagement(rollbackOn = RollbackOn.ALL_EXCEPTIONS)
class TransactionConfig {
}
~~~

Đây là **đoạn cho Spring Framework 6.2+**, không dùng nguyên xi trong ví dụ Spring Boot 3.3.5 bên dưới (Boot 3.3.x dùng Spring Framework 6.1.x). Khi bật `ALL_EXCEPTIONS`, checked exception cũng là rollback theo default mới, kể cả khi method chỉ đặt `@Transactional`. **Rule rollback riêng của transaction** có ưu tiên đối với loại exception mà nó khớp, còn global policy là fallback cho exception chưa có rule chuyên biệt.

Cấu hình này không làm class-level `rollbackFor` tự nhập vào method-level `@Transactional`; nó tác động đến **default rollback decision** sau khi metadata riêng đã được giải nghĩa.

### 7.4. Default timeout và isolation

`@Transactional(timeout = 5)` là giá trị tường minh của method khi manager phải mở transaction mới; nếu method chỉ `@Transactional`, timeout thường lấy default manager/hệ thống. `Isolation.DEFAULT` nhờ nguồn dữ liệu cung cấp isolation mặc định; không tự gán một mức cố định cho tất cả DB.

Nếu default transaction manager có timeout 30 giây mà method yêu cầu 5 giây và thực sự mở transaction mới, method thường yêu cầu 5 giây. Nhưng nếu method **tham gia transaction đang tồn tại**, thuộc tính timeout của physical transaction ngoài vẫn là điểm quyết định; tham gia không tương đương mở lại thời hạn.

## 8. Cấu hình method được chọn vẫn có thể không thay được transaction đã tồn tại

Xét hai bean Spring khác nhau:

~~~java
@Service
class OuterService {
    private final InnerService inner;

    OuterService(InnerService inner) {
        this.inner = inner;
    }

    @Transactional(readOnly = true)
    public void outer() {
        inner.inner();
    }
}

@Service
class InnerService {
    @Transactional(readOnly = false, propagation = Propagation.REQUIRED)
    public void inner() {
        // Metadata method: readOnly=false, REQUIRED.
        // Nhưng method đang tham gia transaction vật lý readOnly=true của outer.
    }
}
~~~

Đây là mã **minh họa thiếu imports và bootstrap**, không phải chương trình độc lập. Giả sử hai service đi qua proxy, dùng cùng một manager và resource:

- Spring chọn metadata `inner()` với `readOnly=false` vì annotation method đó trực tiếp.
- Do `REQUIRED` và outer đã có transaction, inner **tham gia transaction vật lý của outer**, không tạo physical transaction mới.
- Theo chế độ mặc định, khai báo isolation/timeout/readOnly của scope tham gia có thể bị **bỏ qua**, nên transaction vật lý vẫn mang thuộc tính từ outer. Manager có chế độ `validateExistingTransaction` có thể từ chối trường hợp không tương thích, ví dụ inner read-write tham gia outer read-only.
- `readOnly` chủ yếu là hint; không nên lấy một lần UPDATE thành công hay thất bại làm phép thử duy nhất cho policy.

Nếu inner dùng `REQUIRES_NEW` thay vì `REQUIRED`, Spring tạo một physical transaction độc lập và có thể áp dụng thuộc tính riêng của inner trong giới hạn manager/DB hỗ trợ. Cần cân nhắc connection pool vì outer thường vẫn giữ tài nguyên trong thời gian inner chạy.

Bảng tóm lược:

| Tình huống | Spring chọn metadata nào? | Physical transaction nhận thuộc tính nào? |
| --- | --- | --- |
| Method có `@Transactional`, không có transaction ngoài | Method | Thuộc tính method khi manager mở transaction mới |
| Method không annotation, class có `@Transactional`, không có transaction ngoài | Class | Thuộc tính class khi manager mở transaction mới |
| Method `REQUIRED` gọi trong outer đã có transaction | Method ở scope inner | Thường dùng thuộc tính physical transaction của outer, có thể validate mismatch |
| Method `REQUIRES_NEW` gọi qua proxy khi outer đang chạy | Method ở scope inner | Transaction mới độc lập, dùng thuộc tính method có hỗ trợ |
| Method annotated nhưng gọi trực tiếp qua `this` trong cùng bean | Annotation tồn tại trong code | Không có advice riêng ở lời gọi self-invocation; không suy ra có transaction mới |
| Method không có annotation ở mọi nguồn được nhận diện | Không có metadata cho method | Không được transaction advice mở transaction riêng cho lời gọi đó |

Vì vậy “method thắng class” là **quy tắc chọn metadata**, không phải lời hứa rằng manager sẽ sửa isolation/read-only của một physical transaction đang hoạt động.

## 9. Ví dụ chạy được với Java 17 và Spring JDBC: kiểm chứng cả readOnly và rollbackFor

Ví dụ này tạo một ứng dụng CLI Spring Boot nhỏ với JDBC/H2. Nó chứng minh hai ý:

1. Method không annotate dùng `readOnly=true` từ **class**.
2. Method có `@Transactional` của riêng nó dùng `readOnly=false` mặc định và **không giữ `rollbackFor=IOException.class`** từ class. Khi method ghi dữ liệu rồi ném checked `IOException`, giao dịch commit theo rollback policy mặc định của Spring Framework 6.1.
3. Method khai báo tường minh `rollbackFor=IOException.class` rollback cùng loại exception đó.

Dùng Spring Boot **3.3.5**, tương ứng hệ Spring Framework **6.1.x**, để cố định kết quả checked exception mặc định. Giả định JDK 17+, Maven và khả năng tải dependencies. Có đúng **ba tệp**:

~~~text
tx-precedence-demo/
├── pom.xml
└── src/main/java/example/precedence/
    ├── TxPrecedenceApplication.java
    └── LedgerService.java
~~~

### 9.1. Tệp pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>tx-precedence-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 9.2. Tệp src/main/java/example/precedence/TxPrecedenceApplication.java

~~~java
package example.precedence;

import java.io.IOException;
import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@SpringBootApplication
@EnableTransactionManagement
public class TxPrecedenceApplication {
    public static void main(String[] args) {
        SpringApplication.run(TxPrecedenceApplication.class, args);
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }

    @Bean
    CommandLineRunner demo(JdbcTemplate jdbc, LedgerService service) {
        return args -> {
            jdbc.execute(
                "CREATE TABLE ledger (id INT PRIMARY KEY, amount INT NOT NULL)"
            );
            jdbc.update("INSERT INTO ledger (id, amount) VALUES (?, ?)", 1, 100);

            // Method chỉ dùng annotation class.
            service.showClassPolicy();

            // Method có @Transactional riêng: checked IOException
            // không kích hoạt rollback trong policy mặc định 6.1.
            try {
                service.addWithDefault(10);
            } catch (IOException ex) {
                System.out.println("CAUGHT " + ex.getMessage());
            }
            System.out.println("AFTER_DEFAULT=" + amount(jdbc));

            // Method yêu cầu rollback cụ thể cho IOException.
            try {
                service.addWithRollbackRule(30);
            } catch (IOException ex) {
                System.out.println("CAUGHT " + ex.getMessage());
            }
            System.out.println("AFTER_EXPLICIT_ROLLBACK=" + amount(jdbc));
        };
    }

    private static Integer amount(JdbcTemplate jdbc) {
        return jdbc.queryForObject(
            "SELECT amount FROM ledger WHERE id = ?", Integer.class, 1
        );
    }
}
~~~

### 9.3. Tệp src/main/java/example/precedence/LedgerService.java

~~~java
package example.precedence;

import java.io.IOException;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

// Chính sách chung áp dụng khi method không có annotation riêng.
@Service
@Transactional(readOnly = true, rollbackFor = IOException.class)
public class LedgerService {
    private final JdbcTemplate jdbc;

    public LedgerService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void showClassPolicy() {
        printPolicy("CLASS");
        // Không ghi dữ liệu; readOnly=true chỉ là hint.
        jdbc.queryForObject(
            "SELECT amount FROM ledger WHERE id = ?", Integer.class, 1
        );
    }

    // Annotation method được chọn toàn bộ: readOnly=false,
    // rollback mặc định với RuntimeException/Error, không phải IOException.
    @Transactional
    public void addWithDefault(int delta) throws IOException {
        printPolicy("METHOD_DEFAULT");
        jdbc.update(
            "UPDATE ledger SET amount = amount + ? WHERE id = ?", delta, 1
        );
        throw new IOException("checked-default");
    }

    // Phương thức tự khai báo rõ rollback rule cần thiết.
    @Transactional(readOnly = false, rollbackFor = IOException.class)
    public void addWithRollbackRule(int delta) throws IOException {
        printPolicy("METHOD_ROLLBACK");
        jdbc.update(
            "UPDATE ledger SET amount = amount + ? WHERE id = ?", delta, 1
        );
        throw new IOException("checked-rollback");
    }

    private void printPolicy(String label) {
        System.out.println(
            label
            + " active=" + TransactionSynchronizationManager.isActualTransactionActive()
            + ", readOnly=" + TransactionSynchronizationManager.isCurrentTransactionReadOnly()
        );
    }
}
~~~

Chạy từ thư mục có `pom.xml`:

~~~bash
mvn -q spring-boot:run
~~~

Các **dòng ứng dụng tự in** theo thứ tự (không tính log Spring Boot/Hikari):

~~~text
CLASS active=true, readOnly=true
METHOD_DEFAULT active=true, readOnly=false
CAUGHT checked-default
AFTER_DEFAULT=110
METHOD_ROLLBACK active=true, readOnly=false
CAUGHT checked-rollback
AFTER_EXPLICIT_ROLLBACK=110
~~~

Diễn giải:

1. Runner được Spring inject `LedgerService` proxy và gọi `showClassPolicy()` từ **bên ngoài bean**. Không có method annotation, nên Spring dùng class policy và mở transaction có flag `readOnly=true`.
2. `addWithDefault(10)` có method `@Transactional`. Mặc dù class khai báo `rollbackFor=IOException.class`, method này **không kế thừa rule đó**. Nó yêu cầu transaction đọc-ghi; khi ném checked `IOException`, advice áp dụng default (không rollback) và commit UPDATE trước khi chuyển exception ra caller. Số tiền từ 100 thành 110.
3. `addWithRollbackRule(30)` ghi dữ liệu rồi ném `IOException`. Vì method có `rollbackFor=IOException.class`, Spring rollback UPDATE; số tiền vẫn 110.
4. `catch` nằm ở `CommandLineRunner`, tức **bên ngoài proxy**, nên không làm thay đổi quyết định commit/rollback của transaction advice.
5. Việc in `isCurrentTransactionReadOnly()` là kiểm tra **flag trong Spring transaction context**, không chứng minh database luôn chặn ghi khi read-only. Trạng thái dữ liệu sau hoàn tất transaction mới là kiểm chứng quan trọng của commit/rollback.

Ví dụ dùng một `JdbcTransactionManager` và một H2 `DataSource`; không có service gọi nội bộ `this.*` nên không vướng self-invocation. Nếu đổi sang Spring Framework 6.2+ và bật `rollbackOn=ALL_EXCEPTIONS`, hãy dự đoán lại kết quả của `addWithDefault`: default rollback cho checked exception lúc đó đã thay đổi.

## 10. Khi yêu cầu cấu hình riêng: thiết kế rõ thay vì dựa vào “kế thừa ngầm”

Một số cách tổ chức code tránh nhầm:

### 10.1. Class policy chung, method policy đầy đủ

~~~java
@Transactional(readOnly = true, transactionManager = "mainTx")
class CustomerService {
    public Customer find(long id) {
        // Class policy.
        return loadCustomer(id);
    }

    @Transactional(
        readOnly = false,
        propagation = Propagation.REQUIRED,
        transactionManager = "mainTx",
        rollbackFor = IOException.class
    )
    public void importCustomer() throws IOException {
        // Method policy rõ ràng.
    }
}
~~~

Đây là **trích đoạn**; `Customer` và `loadCustomer` chưa có implementation. Điều quan trọng là method ghi có đầy đủ thuộc tính cần giữ, không phó mặc cho annotation class.

### 10.2. Tách read service và write service

Nếu chính sách đọc và ghi khác nhau về manager, timeout hoặc rollback, có thể tách thành hai bean service. Khi đó class-level policy ngắn gọn hơn, ít override và dễ kiểm tra proxy boundary. Tuy vậy tách lớp chỉ để tránh khai báo lại 1–2 thuộc tính không luôn cần thiết; ưu tiên ranh giới nghiệp vụ rõ ràng.

### 10.3. Viết integration test đúng tầng

Với một dự đoán về ưu tiên cấu hình:

- **Gọi qua Spring proxy** từ bean/test client khác để chắc chắn advice chạy. Không dùng `new Service()` hay self-invocation để thử property selection.
- **Quan sát flag** trong transaction khi phù hợp: `TransactionSynchronizationManager.isActualTransactionActive()`, `isCurrentTransactionReadOnly()` và log từ `org.springframework.transaction`. Flag cho biết trạng thái Spring context, không khẳng định DB đã commit.
- **Gây lỗi sau một thay đổi dữ liệu**, sau đó kiểm tra lại DB từ một transaction/connection khác. Phân biệt checked exception với unchecked exception, policy lớp với policy method.
- **Kiểm tra manager thật** nếu có nhiều `PlatformTransactionManager`; chọn sai bean có thể làm test thất bại vì nguồn kết nối khác, không phải do annotation precedence.
- Nếu test framework tự mở transaction quanh test, method `REQUIRED` của service có thể tham gia transaction test; tránh đọc sai kết quả của commit/rollback. Với `@Transactional` trên test, Spring TestContext có mặc định rollback sau test; khi thử commit thật cần kiểm soát transaction test hoặc tách test caller.
- Dùng kiểm tra explicit cho thuộc tính quan trọng nếu một refactor có thể thay đổi annotation: tên manager, propagation, rollback rule và liệu có transaction outer.

## 11. Bẫy thường gặp khi đọc thứ tự ưu tiên

| Ngộ nhận | Thực tế cần nhớ |
| --- | --- |
| “Method chỉ đặt `timeout=5` nên giữ toàn bộ thuộc tính class” | Method annotation thay toàn bộ metadata annotation; các thuộc tính khác dùng default của nó |
| “Có `@Transactional` tại class thì method riêng vẫn phải đọc-only” | Method có `@Transactional` riêng có default `readOnly=false`, trừ khi ghi lại `true` |
| “`rollbackFor` ở class áp dụng cả khi method có annotation riêng” | Rule ở class không tự ghép vào method annotation; cần ghi lại hoặc dùng default toàn cục thích hợp |
| “`isolation=SERIALIZABLE` trên inner method luôn nâng isolation DB” | `REQUIRED` đang tham gia physical transaction khác có thể bỏ qua yêu cầu isolation inner |
| “`order` của `@EnableTransactionManagement` làm method annotation thắng class” | `order` điều khiển thứ tự advice, không phải cơ chế chọn metadata theo vị trí |
| “Chỉ cần annotate interface là chắc chắn đúng mọi proxy/AspectJ mode” | Có giới hạn đặc biệt với interface annotation; ưu tiên annotate concrete implementation |
| “Method private/final hoặc tự gọi `this.method()` luôn nhận advice” | Proxy mode có giới hạn visibility/override và chỉ bắt lời gọi qua proxy |
| “`readOnly=true` chắc chắn gây lỗi nếu ghi DB” | Đây là hint, tùy transaction manager/driver/database |
| “Checked exception luôn commit” | Đó là default phổ biến trước khi đổi global rollback policy; rule cụ thể hoặc Spring 6.2+ ALL_EXCEPTIONS có thể làm rollback |
| “Class-level metadata tự áp vào tất cả method khai báo trong superclass” | Spring lưu ý subclass annotation không tự áp ngược ancestor methods; có thể phải override/redeclare |
| “Cứ cùng @Transactional thì các manager tự liên thông” | Chọn manager cụ thể quyết định resource; annotation không biến hai DataSource độc lập thành một transaction |

## 12. Cách tự suy luận một tình huống mới

Giả sử có:

~~~java
@Transactional(readOnly = true, rollbackFor = Exception.class)
public class OrderService {
    public Order get(long id) { /* ... */ return null; }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void save(Order order) { /* ... */ }

    @Transactional(readOnly = false, noRollbackFor = BusinessException.class)
    public void finalizeOrder() { /* ... */ }
}
~~~

Đây là pseudocode Java minh họa signature; `Order` và `BusinessException` là loại nghiệp vụ giả định. Hãy làm theo thứ tự:

1. **`get`:** không annotation riêng ⇒ dùng metadata class (read-only, rollbackFor `Exception.class`, propagation default REQUIRED).
2. **`save`:** method annotation được chọn ⇒ REQUIRES_NEW; `readOnly` mặc định **false**, không lấy `true` của class; `rollbackFor=Exception.class` của class cũng không được giữ.
3. **`finalizeOrder`:** method annotation được chọn ⇒ REQUIRED mặc định; readOnly false, noRollbackFor cho BusinessException; không lấy `rollbackFor=Exception.class` từ class. Nếu BusinessException là unchecked, rule riêng `noRollbackFor` được dùng.
4. Sau đó mới hỏi method thực sự được gọi **qua proxy** không, có **outer transaction** không, manager nào chịu trách nhiệm, và kết quả commit/rollback cuối cùng xảy ra lúc nào.

**Câu hỏi kiểm tra:** Nếu `save` thay thành `@Transactional(timeout=3)`, propagation có tiếp tục là `REQUIRES_NEW` không? **Không** — method annotation mới có propagation mặc định `REQUIRED`. Nếu người đọc muốn đồng thời 3 giây và REQUIRES_NEW, phải khai báo `@Transactional(timeout=3, propagation=Propagation.REQUIRES_NEW)`.

**Câu hỏi kiểm tra:** Nếu outer method có `readOnly=true` rồi gọi `finalizeOrder` từ bean khác qua proxy, method-level `readOnly=false` có làm physical transaction thành read-write không? Với `REQUIRED` tham gia transaction sẵn có, **không mặc nhiên**; cấu hình của outer vẫn chi phối physical transaction và manager có thể báo mismatch.

## Tài liệu tham khảo

- [Spring Framework — Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): quy tắc most-derived, method/class, mặc định thuộc tính, manager và lưu ý proxy.
- [Spring Framework — Understanding declarative transaction implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): AOP proxy, transaction interceptor và transaction manager.
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): physical/logical transaction, REQUIRED và REQUIRES_NEW, validate existing transactions.
- [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html): rollback rules, strongest match, checked và unchecked exceptions.
- [Spring Framework — Transactional API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/Transactional.html): thuộc tính annotation và ý nghĩa của readOnly/rollbackFor.

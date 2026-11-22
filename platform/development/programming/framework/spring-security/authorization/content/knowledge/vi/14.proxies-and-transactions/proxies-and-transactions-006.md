# Thứ tự interceptor bảo mật với @Transactional và các advice khác

## 1. Vì sao thứ tự interceptor quyết định hành vi bảo mật?

Một phương thức service của Spring có thể đồng thời có `@PreAuthorize`, `@PostAuthorize`, `@Transactional` và những advice khác như ghi log, audit, cache hoặc retry. Các annotation này không đơn giản là những câu lệnh chạy tuần tự theo thứ tự xuất hiện trong mã nguồn. Phần lớn được xử lý bởi **Spring AOP advisor/interceptor** bao quanh lời gọi phương thức.

Với cùng một phương thức, thứ tự advisor quyết định:

- **Ai chạy trước thân phương thức?** Kiểm tra quyền có xảy ra trước khi mở transaction, ghi log hoặc thực hiện thao tác nặng không?
- **Ai chạy sau thân phương thức?** Một lần kiểm tra `@PostAuthorize` có diễn ra trước hay sau khi transaction được commit?
- **Exception có đi qua transaction interceptor không?** Nếu lỗi phân quyền được ném sau khi transaction đã kết thúc, transaction đó không thể được rollback chỉ nhờ exception ấy.
- **Advice nào có thể bỏ qua advice khác?** Cache hit, gọi không qua proxy hoặc chuyển luồng với `@Async` có thể làm đường chạy khác dự đoán.

Bài học tập trung vào **Spring Security method authorization trong ứng dụng Spring MVC/servlet dùng Spring AOP ở chế độ proxy**, kết hợp transaction kiểu imperative (JDBC/JPA). Đối với reactive transaction, AspectJ weaving và các cấu hình AOP khác, cơ chế chi tiết có thể khác và cần kiểm tra riêng.

## 2. Spring AOP tạo thành một chuỗi bọc lồng nhau

Khi một lời gọi đi qua proxy đến service, có thể hình dung:

```text
Client
  |
  v
Spring AOP proxy
  |-- Advice thứ tự cao hơn (số order nhỏ) : trước
  |    |-- Advice kế tiếp                 : trước
  |    |    |-- Transaction interceptor   : begin
  |    |    |    |-- Method body
  |    |    |-- Transaction interceptor   : commit/rollback
  |    |-- Advice kế tiếp                 : sau
  |-- Advice thứ tự cao hơn              : sau
  |
  v
Client nhận kết quả / exception
```

**Quy tắc:** trong Spring AOP, advisor có `order` **nhỏ hơn** có **độ ưu tiên cao hơn**, được chạy sớm hơn khi đi vào lời gọi và kết thúc muộn hơn khi đi ra. Ví dụ `order=100` là lớp bao **ngoài** `order=200`.

Đối với advice kiểu `@Around`, trình tự được hiểu là:

```text
Outer.before
  Inner.before
    Method
  Inner.after
Outer.after
```

Vì vậy, nói "advisor A chạy trước B" chỉ mô tả chiều **đi vào**. Với kiểm tra sau khi phương thức thực thi, thứ tự đi ra **đảo ngược**. Đó là chìa khóa để hiểu sự tương tác của `@PostAuthorize` với transaction.

Điểm cần phân biệt:

- **Advisor order**: thứ tự giữa các interceptor áp dụng cho cùng join point; có thể thiết lập với `Ordered`, `@Order`, hoặc cấu hình riêng của từng hạ tầng.
- **Thứ tự annotation trong source**: đổi chỗ hai dòng `@Transactional` và `@PreAuthorize` **không tự đổi advisor order**.
- **Thứ tự gọi các service**: gọi `serviceA` rồi `serviceB` là thứ tự nghiệp vụ, khác với thứ tự interceptor bọc từng phương thức.

Khi hai advisor có cùng giá trị `order` mà không có quy tắc ràng buộc khác, không nên dựa vào thứ tự tình cờ do container đăng ký.

## 3. Các interceptor Method Security và thứ tự mặc định

Khi bật:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
```

Spring Security đăng ký những advisor tương ứng với các tính năng method security được bật. Với thiết lập mặc định của `@EnableMethodSecurity`, `@PreAuthorize`, `@PostAuthorize`, `@PreFilter` và `@PostFilter` được hỗ trợ; `@Secured` và JSR-250 cần bật riêng bằng thuộc tính cấu hình.

Theo thứ tự được Spring Security định nghĩa qua `AuthorizationInterceptorsOrder`, các vị trí thường gặp là:

| Advisor liên quan | Order | Vai trò |
| --- | ---: | --- |
| `@PreFilter` | 100 | Lọc tham số đầu vào trước thân phương thức |
| `@PreAuthorize` | 200 | Kiểm tra quyền trước thân phương thức |
| `@Secured`, khi được bật | 300 | Kiểm tra quyền theo annotation `@Secured` |
| JSR-250, khi được bật | 400 | Kiểm tra `@RolesAllowed` / annotation liên quan |
| `@PostAuthorize` | 500 | Kiểm tra quyền dựa trên kết quả sau khi phương thức trả về |
| `@PostFilter` | 600 | Lọc tập hợp kết quả |

Một số phiên bản mới có thêm advisor bảo mật giá trị trả về (chẳng hạn `SECURE_RESULT` ở vị trí khác trong cùng chuỗi). **Chỉ các advisor thực sự được bật và khớp phương thức mới chạy**; bảng là mốc tư duy để thiết kế, không có nghĩa mỗi phương thức luôn chạy đủ sáu interceptor. Kiểm tra phiên bản Spring Security đang dùng khi cần giá trị order chính xác.

Ví dụ, nếu một phương thức được bảo vệ bởi `@PreAuthorize` và `@PostAuthorize`, hai interceptor có thể được hình dung như:

```text
@PreAuthorize  (200): kiểm tra lúc vào
  @PostAuthorize (500): bao quanh lời gọi; kiểm tra lúc ra
    method body
  @PostAuthorize (500): đánh giá returnObject
@PreAuthorize (200): kết thúc
```

Nếu `@PostFilter` cũng áp dụng, vì `600` nằm **bên trong** `500`, quá trình lọc sau method thường xảy ra trong đường đi ra **trước** kiểm tra `@PostAuthorize`. Tránh đưa giả định về thứ tự này vào nghiệp vụ nếu có các cấu hình interceptor tùy biến; cần test thực tế.

## 4. @Transactional đứng ở đâu nếu giữ cấu hình thông thường?

Spring Framework gán mặc định `order = Ordered.LOWEST_PRECEDENCE` cho transaction advice kích hoạt bởi `@EnableTransactionManagement`. Con số này biểu thị độ ưu tiên rất thấp so với các advisor method security ở 100–600.

Ví dụ một method có `@PreAuthorize`, `@PostAuthorize` và `@Transactional`; giả sử không có transaction bên ngoài và không có advisor khác thay đổi thứ tự:

```text
Caller
  -> @PreAuthorize (order 200): ALLOW
     -> @PostAuthorize (order 500): enter wrapper
        -> Transaction advice (LOWEST_PRECEDENCE): BEGIN
           -> Method body / repository / write
        <- Transaction advice: COMMIT nếu thân phương thức thành công
     <- @PostAuthorize: kiểm tra returnObject, có thể DENY
  <- Caller nhận kết quả hoặc AccessDeniedException
```

**Hệ quả quan trọng:**

1. `@PreAuthorize` có thể từ chối trước khi transaction mới được mở; điều này thường giúp tránh một transaction không cần thiết.
2. Nếu biểu thức `@PreAuthorize` gọi bean policy để query DB, lệnh kiểm tra đó có thể thực thi **ngoài transaction của phương thức được bảo vệ**, vì transaction advice nằm bên trong. Tính nhất quán giữa "kiểm tra quyền" và "ghi" cần được thiết kế chủ động.
3. Nếu `@PostAuthorize` từ chối **sau khi transaction đã commit**, exception ấy không thể quay lại rollback những thay đổi đã commit.
4. Nếu đã có **transaction ở caller bên ngoài**, mọi phép đo hoặc kết luận về transaction active phải xét transaction đang được thừa hưởng; chuỗi trên chỉ diễn tả trường hợp tự mở một transaction mới tại method này.

Do đó, kết hợp `@PostAuthorize` với **phương thức ghi database** là một lựa chọn rủi ro. Spring Security chính thức khuyên tránh dùng `@PostAuthorize` cho các lớp thực hiện database write, đặc biệt khi cùng phương thức cũng có `@Transactional`.

### Ví dụ dễ gây lỗi

```java
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InvoiceService {
    private final InvoiceRepository repository;

    public InvoiceService(InvoiceRepository repository) {
        this.repository = repository;
    }

    // CHỈ MINH HỌA RỦI RO: không dùng làm thiết kế cập nhật hóa đơn.
    @Transactional
    @PostAuthorize("returnObject.ownerUsername == authentication.name")
    public Invoice updateOwnerNote(Long id, String text) {
        Invoice invoice = repository.findById(id).orElseThrow();
        invoice.setNote(text);
        return invoice;
    }
}
```

Đây là **một thành phần Spring**, giả định entity `Invoice` và repository có sẵn. Khi method hoàn tất và transaction commit, `@PostAuthorize` mới có thể kiểm tra `returnObject` trong cấu hình thứ tự thường gặp. Người gọi trái quyền có thể nhận `AccessDeniedException`, **nhưng cập nhật đã commit**. Từ chối HTTP không đồng nghĩa với rollback dữ liệu.

Thiết kế phù hợp hơn là **kiểm tra quyền trước thao tác ghi** và ràng buộc truy vấn cập nhật với tenant/owner/ACL đáng tin cậy:

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InvoiceWriteService {
    private final InvoiceRepository repository;

    public InvoiceWriteService(InvoiceRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize(
        "hasAuthority('invoice:write') and " +
        "@invoicePolicy.canEdit(authentication, #invoiceId)"
    )
    @Transactional
    public void editNote(Long invoiceId, String note) {
        Invoice invoice = repository.findById(invoiceId).orElseThrow();
        invoice.setNote(note);
    }
}
```

Đoạn trên là ví dụ **giới hạn ở method-level authorization**. Trong hệ thống nhiều người dùng, kiểm tra `canEdit` trước khi transaction mở có thể gặp race/TOCTOU nếu quyền hoặc owner thay đổi giữa lúc kiểm tra và lúc ghi. Với cập nhật nhạy cảm, nên tái xác minh ràng buộc trong cùng transaction hoặc dùng câu `UPDATE ... WHERE id = ? AND tenant_id = ? AND owner_id = ?` cùng phiên bản/locking phù hợp; không dùng owner/tenant do client khai làm nguồn sự thật.

## 5. Khi nào cần transaction bao cả phần kiểm tra quyền?

Có nghiệp vụ cần kiểm tra trước ghi và dùng cùng snapshot/transaction, hoặc muốn exception từ `@PostAuthorize` được transaction interceptor thấy trước lúc quyết định commit. Khi ấy có thể cấu hình transaction advice có độ ưu tiên **cao hơn** security advice:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableTransactionManagement(order = 0)
@EnableMethodSecurity
public class TxAndSecurityConfig {
}
```

Với `order=0`, transaction advisor nằm ngoài `@PreAuthorize(200)` và `@PostAuthorize(500)` trên cùng join point:

```text
Caller
  -> Transaction advice (0): BEGIN
     -> @PreAuthorize (200): ALLOW hoặc DENY
        -> @PostAuthorize (500): enter
           -> Method body
        <- @PostAuthorize (500): kiểm tra kết quả
  <- Transaction advice: COMMIT nếu mọi thứ thành công,
                         ROLLBACK nếu exception phù hợp đi ra
```

Nếu `@PostAuthorize` ném `AccessDeniedException`, đó là runtime exception; với rollback rules mặc định và transaction còn đang hoạt động tại điểm interceptor quan sát exception, transaction sẽ rollback.

**Tuy nhiên không nên đổi `@EnableTransactionManagement(order = 0)` chỉ để "chữa" một phép kiểm tra quyền sau ghi:** cấu hình order ảnh hưởng các transaction advisor do hạ tầng này đăng ký trong phạm vi context, khiến transaction có thể bắt đầu **trước cả kiểm tra quyền**. Điều này gây thêm chi phí, thay đổi vòng đời transaction và ảnh hưởng tương tác với logging, cache, retry hay lazy loading. Transaction rollback cũng **không thu hồi** email đã gửi, event đã phát ra ngoài giao dịch, thay đổi ở transaction `REQUIRES_NEW` đã commit riêng hay side effect bên ngoài.

Ưu tiên phân quyền **trước khi thay đổi dữ liệu**. Nếu cần một kiểm tra quyền hậu xử lý cho kết quả đọc thuần túy, `@PostAuthorize` phù hợp hơn. Nếu buộc phải phối hợp transaction và post authorization, viết integration test chứng minh kết quả **và** trạng thái database, không chỉ kiểm tra exception.

### @EnableMethodSecurity(offset) có ý nghĩa gì?

`@EnableMethodSecurity(offset = n)` (từ Spring Security 6.3) cộng `n` vào các order mặc định của nhóm interceptor bảo mật do annotation này kích hoạt. Ví dụ:

```java
@Configuration
@EnableMethodSecurity(offset = 50)
class OffsetMethodSecurityConfig {
}
```

Khi đó `@PreFilter` thường từ 100 thành 150, `@PreAuthorize` từ 200 thành 250, `@PostAuthorize` từ 500 thành 550, v.v. Điều này giúp **dịch chuyển cả nhóm** đối với advisor khác; nó không thay đổi thứ tự tương đối giữa những advisor bảo mật cùng nhóm. Không tự ý dùng offset cực lớn hoặc giá trị trùng advisor khác; cần kiểm tra thứ tự thực sau cấu hình.

**Điểm phân biệt:** `@EnableTransactionManagement(order = ...)` đặt order cho **transaction advisor**. `@EnableMethodSecurity(offset = ...)` dịch chuyển các **security advisors**. Đặt `@Order` lên class service **không** phải cách mặc định để chỉnh hai order này.

## 6. Điều chỉnh @Aspect khác: audit, logging, metrics

Đối với custom advice viết bằng `@Aspect`, có thể đặt `@Order` trên aspect bean. Ví dụ dưới đây dùng `@Order(250)`, nghĩa là với method chỉ được bảo vệ bởi `@PreAuthorize(200)` và transaction advisor mặc định, audit advice chạy **sau kiểm tra đầu vào thành công** nhưng **trước khi transaction bắt đầu**:

```java
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Aspect
@Component
@Order(250)
public class ServiceAuditAspect {
    @Around("execution(* com.example.application.service.*.*(..))")
    public Object audit(ProceedingJoinPoint invocation) throws Throwable {
        String operation = invocation.getSignature().getName();
        try {
            return invocation.proceed();
        } finally {
            // Gửi bản ghi audit qua thành phần đáng tin cậy của ứng dụng.
            // Không ghi token, credential hoặc toàn bộ dữ liệu nhạy cảm.
            System.out.println("operation-finished=" + operation);
        }
    }
}
```

Đây là **class thành phần**: pointcut chỉ hoạt động khi cấu trúc package khớp, ứng dụng bật Spring AOP và bean được đăng ký. `finally` chạy cả khi method bên trong ném exception; nó không chứng minh giao dịch đã commit và không được ghi sự kiện "thao tác thành công" mà thiếu kết quả thực.

Nếu cần ghi lại **mọi nỗ lực gọi**, kể cả những lần bị từ chối bởi `@PreAuthorize`, có thể đặt audit **ngoài** authorization, ví dụ order nhỏ hơn 200. Đổi lại, advice ngoài có thể nhận dữ liệu người gọi chưa được cấp quyền, nên ghi log ở mức tối thiểu, kiểm soát thông tin nhạy cảm và phân biệt `attempt`, `denied`, `success`.

Không suy luận `@Order(250)` luôn chạy sau **mọi** kiểm tra security: `@Secured(300)` và JSR-250 (400) nếu được bật sẽ nằm **bên trong** nó. Muốn một audit chạy sau tất cả kiểm tra "trước method", cần rà soát advisor nào thực sự được sử dụng, các order tùy chỉnh và cân nhắc đặt audit tại biên nghiệp vụ đã được bảo vệ.

### Sơ đồ thứ tự có custom advice

Với `@PreAuthorize(200)`, audit `@Order(250)`, `@PostAuthorize(500)` và transaction mặc định:

```text
PreAuthorize: check
  Audit: enter
    PostAuthorize: enter
      Transaction: begin
        Method
      Transaction: commit
    PostAuthorize: check
  Audit: exit
Return / exception
```

Nếu `PostAuthorize` từ chối, `Audit` sẽ thấy exception trong `finally`; tuy nhiên transaction bên trong đã kết thúc. Điều này cho thấy **vị trí ghi log, vị trí check quyền và vị trí commit là ba việc độc lập**.

## 7. Các advice khác và những tác dụng khó quan sát

| Advice/tính năng | Vì sao thứ tự đáng quan tâm? | Cần xác minh |
| --- | --- | --- |
| `@Cacheable` | Cache hit có thể trả kết quả mà không gọi `proceed()`; nếu cache advisor ở ngoài kiểm tra quyền, method security bên trong có thể bị bỏ qua trên cache hit | Quyền phải được kiểm tra trên mỗi đường truy cập; cache key cần scope đúng principal/tenant khi dữ liệu khác nhau theo người |
| `@Retryable` / retry advice | Retry ở bên ngoài transaction thường tạo transaction mới cho từng lần thử; vị trí security quyết định check quyền chạy một lần hay mỗi lần retry | Quyền có thay đổi giữa các lần thử không, side effect có idempotent không, transaction có thật sự mới cho mỗi attempt không |
| `@Async` | Có ranh giới executor/thread khác; SecurityContext và transaction kiểu imperative thường gắn với thread | Advice security chạy ở thread nào, SecurityContext được truyền thế nào, transaction mở ở đâu |
| Logging/metrics `@Around` | Đặt ở ngoài authorization có thể đo cả request bị từ chối; đặt bên trong sẽ chỉ thấy call vượt qua các kiểm tra bên ngoài | Không log sensitive arguments; phân biệt success/failure/deny |
| Event/audit side effects | Có thể được phát trước commit hoặc trước kiểm tra sau method | Dùng transaction-aware outbox/event timing phù hợp; không tuyên bố hoàn thành trước khi commit |
| Custom AuthorizationManager advisor | Có thể được đặt vào vị trí khác trong chain, thay thế hoặc kết hợp các advisor có sẵn | Kiểm thử order, phạm vi pointcut, trùng lặp hoặc bỏ sót kiểm tra |

**Cache là trường hợp đặc biệt nguy hiểm:** nếu kết quả user A được cache với key không chứa tenant/principal, user B có thể nhận dữ liệu A. Ngay cả khi cache order được điều chỉnh, dữ liệu nhiều tenant vẫn cần key chuẩn, partition dữ liệu và chính sách truy cập đến nguồn. `@Cacheable` đặt trên cùng method với `@PostAuthorize` cần kiểm tra cả cache hit và cache miss vì việc rút ngắn chuỗi có thể bỏ qua một phần advice.

Với retry, tài liệu Spring Framework mô tả cấu hình mặc định của tổ hợp `@Retryable` với `@Transactional` cho phép retry nằm ngoài để mỗi attempt chạy trong transaction riêng; tuy nhiên các phiên bản, cấu hình order và hệ thống retry cụ thể cần được xác nhận. **Không áp đặt** kết luận này cho mọi custom retry advisor.

Với async, **không thể suy luận bằng một bảng order số đơn thuần** sau khi lời gọi được chuyển sang worker thread. Với Spring Security, có thể dùng executor/decorator chuyên dụng để truyền `SecurityContext` đúng cách; vẫn phải xem service có thực thi kiểm tra quyền ở điểm thích hợp không. Transaction kiểu imperative không tự theo thread sang luồng khác.

## 8. Proxy và self-invocation: thứ tự đúng vẫn có thể không áp dụng

Ở chế độ proxy thông dụng, advice chạy khi một lời gọi **đi qua Spring proxy**. Gọi `this.otherMethod()` trong cùng instance thường đi thẳng tới method mà không quay qua proxy, kể cả khi `otherMethod()` có `@Transactional` hoặc `@PreAuthorize`.

Ví dụ **anti-pattern**:

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TransferService {
    public void processTransfer(Long accountId) {
        // Self-invocation: không đi qua proxy của bean hiện tại.
        this.persistTransfer(accountId);
    }

    @PreAuthorize("@accountPolicy.canTransfer(authentication, #accountId)")
    @Transactional
    public void persistTransfer(Long accountId) {
        // Thực hiện cập nhật dữ liệu. Đây là ví dụ thành phần.
    }
}
```

Nếu caller chỉ gọi `processTransfer` và method này không được bảo vệ ở điểm vào thích hợp, `persistTransfer` có thể không nhận advice bảo mật/giao dịch dự kiến. Thay vì "đổi order" để sửa lỗi này:

- Đặt điểm kiểm tra quyền tại **entry point service được gọi qua proxy**.
- Tách thao tác bảo vệ ra **một Spring bean khác** và gọi bean đó bằng dependency injection.
- Dùng kiểm tra quyền trong logic dữ liệu và transaction thực tế như lớp bảo vệ bổ sung.

Cần xét khả năng proxy đối với `private`, `final`, phương thức không public, proxy JDK/CGLIB và vị trí annotation. Spring Framework hỗ trợ một số method non-public cho class-based transactional proxy, nhưng không nên suy ra method security áp dụng giống hệt trong mọi trường hợp. Cách dễ kiểm chứng nhất: bảo vệ các public service method được gọi qua bean của Spring và viết integration test đường gọi thật.

## 9. Ví dụ Java 17 chạy độc lập: so sánh hai vị trí transaction

Chương trình dưới đây **mô phỏng chuỗi interceptor bằng Java thuần**, không sử dụng Spring, SQL hay transaction thật. Nó cố ý thể hiện sự khác nhau về vị trí xảy ra `post-check` và `commit`. Lưu vào `AdvisorOrderDemo.java`:

```java
public class AdvisorOrderDemo {

    static void preAuthorize(boolean allowed, Runnable next) {
        System.out.println("pre.check");
        if (!allowed) {
            throw new SecurityException("denied before");
        }
        next.run();
    }

    static void postAuthorize(boolean allowed, Runnable next) {
        next.run();
        System.out.println("post.check");
        if (!allowed) {
            throw new SecurityException("denied after");
        }
    }

    static void transaction(Runnable next) {
        System.out.println("tx.begin");
        try {
            next.run();
            System.out.println("tx.commit");
        } catch (RuntimeException ex) {
            System.out.println("tx.rollback");
            throw ex;
        }
    }

    static void write() {
        System.out.println("write");
    }

    static void defaultOrder() {
        System.out.println("-- default order --");
        try {
            preAuthorize(true,
                () -> postAuthorize(false,
                    () -> transaction(AdvisorOrderDemo::write)));
        } catch (SecurityException ex) {
            System.out.println("caller: " + ex.getMessage());
        }
    }

    static void transactionOuter() {
        System.out.println("-- transaction outer --");
        try {
            transaction(
                () -> preAuthorize(true,
                    () -> postAuthorize(false, AdvisorOrderDemo::write)));
        } catch (SecurityException ex) {
            System.out.println("caller: " + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        defaultOrder();
        transactionOuter();
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac AdvisorOrderDemo.java
java AdvisorOrderDemo
```

Stdout chính xác:

```text
-- default order --
pre.check
tx.begin
write
tx.commit
post.check
caller: denied after
-- transaction outer --
tx.begin
pre.check
write
post.check
tx.rollback
caller: denied after
```

Trong case đầu, `post.check` xảy ra **sau** `tx.commit`, nên exception do post check không còn ở trong lời gọi transaction. Case thứ hai cho thấy khi transaction bọc ngoài, exception từ `postAuthorize` đi xuyên qua transaction wrapper và kích hoạt nhánh rollback. **Không lấy ví dụ mô phỏng này làm bằng chứng transaction của ứng dụng đã rollback**: JPA flush, propagation, exception handling, outer transaction và side effect phải được kiểm thử trực tiếp.

## 10. Cách kiểm chứng advisor order của Spring thật

### 10.1 Kiểm tra chain đăng ký trên proxy

Với ứng dụng có Spring AOP proxy, có thể đọc danh sách advisor của bean bằng mã kiểm tra trong test hoặc công cụ debug:

```java
import org.springframework.aop.Advisor;
import org.springframework.aop.framework.Advised;
import org.springframework.core.Ordered;

// Đoạn minh họa trong Spring test có ApplicationContext tên context.
Object bean = context.getBean("invoiceWriteService");

if (bean instanceof Advised advised) {
    for (Advisor advisor : advised.getAdvisors()) {
        String order = (advisor instanceof Ordered ordered)
            ? Integer.toString(ordered.getOrder())
            : "not-explicit";
        System.out.println(advisor.getClass().getSimpleName()
            + " order=" + order);
    }
}
```

Mã này **không phải chương trình độc lập**: cần bean và `ApplicationContext` thực của ứng dụng. Một số hệ thống có proxy lồng nhau, advisor xuất hiện theo type/instance khác hoặc có infrastructure không hiển thị đầy đủ bằng cách in tên class. Quan trọng là **quan sát** chứ không hard-code assertion về tên bean nội bộ Spring nếu tên có thể thay đổi theo phiên bản.

### 10.2 Đo xem transaction đang active tại bước nào

Trong integration test hoặc custom logging **không chứa dữ liệu nhạy cảm**, tại service/policy có thể kiểm tra:

```java
import org.springframework.transaction.support.TransactionSynchronizationManager;

boolean active =
    TransactionSynchronizationManager.isActualTransactionActive();
```

Đặt việc ghi nhận `active` ở **đúng điểm**: trước method, trong body, sau method, trong custom advice. `isActualTransactionActive()` cho biết transaction active trên thread hiện tại; nó không chứng minh câu SQL đã commit/rollback hay tài nguyên bất kỳ tham gia transaction.

Nếu một cuộc gọi đã ở trong transaction bên ngoài, kết quả đo có thể là `true` ngay cả khi transaction advice riêng của phương thức chưa được thực thi. Nên test riêng tình huống caller không có transaction và tình huống có outer `@Transactional`.

### 10.3 Tập integration test tối thiểu

| Kịch bản | Điều cần assert |
| --- | --- |
| `@PreAuthorize` từ chối trước ghi | Method body và repository write không chạy |
| Quyền hợp lệ, method thành công | Dữ liệu commit theo kỳ vọng |
| `@PostAuthorize` từ chối sau method ghi với transaction nằm trong | Có thể nhận `AccessDeniedException` **sau commit**; assert trạng thái DB để phát hiện |
| Transaction bao ngoài post authorization theo cấu hình đã chủ đích | Runtime exception trước commit làm rollback DB tham gia transaction theo rollback rules |
| Lời gọi `this.securedMethod()` | Tái hiện và sửa việc bỏ qua security/tx advice |
| Cache miss/cache hit với hai user/tenant | Không trả nhầm dữ liệu; security vẫn được kiểm tra theo thiết kế |
| Retry gặp lỗi tạm thời | Số lần thử, trạng thái transaction và các side effect đúng |
| `@Async` hoặc executor | SecurityContext và transaction boundary đúng tại worker thread |

Sử dụng `@SpringBootTest` kết hợp database test thật hoặc test container để kiểm tra commit/rollback; test bằng mock thuần sẽ không chứng minh được dữ liệu đã commit. Nếu assert security, gọi service **qua bean lấy từ Spring context**. `@WithMockUser` giúp tạo security context cho test nhưng không thay thế việc kiểm tra đúng đường đi của proxy.

Đối với kiểm thử thứ tự audit, có thể dùng danh sách sự kiện trong test để thu `preAuth`, `audit.before`, `tx.active`, `audit.after`, `deny`. Tránh kiểm tra thứ tự dựa vào log mơ hồ hoặc chỉ kiểm tra response HTTP 403.

## 11. Quy tắc thiết kế đề xuất

1. **Kiểm tra quyền trước khi gây tác dụng phụ:** dùng `@PreAuthorize` hoặc AuthorizationManager và policy ở điểm service đủ tin cậy. Với write nhạy cảm, giữ điều kiện owner/tenant/ACL trong transaction/truy vấn để giảm race.
2. **Dùng post authorization chủ yếu cho read:** `@PostAuthorize` thích hợp với tài nguyên trả về cần được xác minh; không coi exception sau method là biện pháp rollback mặc định.
3. **Xác định rõ transaction boundary:** xét order, propagation, outer transaction, commit, rollback rules và sự kiện ngoài database.
4. **Giải thích ý định của custom advice:** muốn audit toàn bộ attempt hay chỉ thao tác đã qua kiểm tra? Muốn metrics gồm cả deny hay chỉ successful call?
5. **Coi cache, retry, async là thay đổi flow thực tế:** kiểm chứng cache hit, attempt thứ hai và worker thread.
6. **Đảm bảo lời gọi đi qua proxy:** tránh self-invocation cho các method dựa vào annotation AOP.
7. **Chỉ chỉnh advisor order khi có yêu cầu cụ thể và test chứng minh:** cập nhật version Spring có thể thay đổi advisor được đăng ký; đừng dùng các số order như công thức không cần xác minh.

## 12. Lỗi thường gặp và cách sửa

| Suy luận sai | Hậu quả có thể xảy ra | Cách hiểu/sửa |
| --- | --- | --- |
| "Viết `@Transactional` ở trên `@PreAuthorize` nên transaction chạy trước" | Dự đoán sai thứ tự | Advisor order do AOP xác định, không theo vị trí annotation |
| "`@PostAuthorize` ném exception thì chắc chắn rollback" | Ghi dữ liệu đã commit nhưng API trả 403 | Kiểm tra vị trí transaction; ưu tiên kiểm tra trước ghi |
| "Order nhỏ chạy trước cả chiều vào lẫn chiều ra" | Hiểu ngược thời điểm post check | Order nhỏ chạy trước lúc vào, **sau** lúc ra |
| "`@Order(250)` nghĩa là luôn qua tất cả security check" | Advice có thể chạy trước `@Secured`/JSR250 | Kiểm tra đầy đủ các advisor đang bật |
| "Đặt `@Order` trên service để đổi transaction order" | Cấu hình không đạt mục đích | Dùng `@EnableTransactionManagement(order=...)` hoặc cấu hình advisor phù hợp |
| "Policy check trước transaction luôn ổn định" | Race giữa việc kiểm tra quyền và ghi | Ràng buộc dữ liệu/locking/tx phù hợp; test race |
| "Cache hit vẫn chạy method security bên trong" | Có thể bỏ qua check và lộ cache chéo tenant | Kiểm tra order, key và quyền trên cả hit/miss |
| "`@Async` giữ nguyên SecurityContext và transaction" | Thiếu identity hoặc transaction trên worker thread | Thiết kế propagation riêng và integration test |
| "`this.method()` vẫn kích hoạt annotation" | Bỏ qua authorization/transaction | Gọi qua Spring bean/proxy hoặc tái thiết kế service |
| "HTTP 403 chứng minh không có thay đổi DB" | False negative trong test bảo mật | Assert DB thật và side effect sau request |

**Câu hỏi quyết định khi review:** "Lúc phương thức cập nhật dữ liệu, quyền đã được xác minh bằng dữ liệu đáng tin chưa? Lúc check hậu xử lý, transaction còn mở hay đã commit? Nếu có một advice trả sớm hoặc chuyển thread, kiểm tra quyền còn diễn ra không?"

## Tài liệu tham khảo chính thức

- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): mỗi annotation có interceptor riêng, `AuthorizationInterceptorsOrder`, `@EnableMethodSecurity(offset)` và cảnh báo `@PostAuthorize` với thao tác ghi.
- [Spring Security API — AuthorizationInterceptorsOrder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/method/AuthorizationInterceptorsOrder.html): tên và thứ tự advisor bảo mật.
- [Spring Security API — EnableMethodSecurity](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/method/configuration/EnableMethodSecurity.html): cấu hình method security và offset.
- [Spring Framework — AOP Advice Ordering](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html): quy tắc ưu tiên chiều vào và chiều ra, `@Order` và `Ordered`.
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): transaction proxy, mặc định order `LOWEST_PRECEDENCE`, self-invocation, rollback rules và tương tác với retry.
- [Spring Framework — Understanding AOP Proxies](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): proxy, cơ chế self-invocation và các giới hạn tương ứng.

# Chuẩn bị phương án khi thư mục chậm hoặc không sẵn sàng

Trong **Spring Data LDAP**, ứng dụng thường phụ thuộc vào một hoặc nhiều directory để tra cứu người dùng, nhóm, thông tin tổ chức hoặc dữ liệu định danh. Khi LDAP phản hồi chậm, mất kết nối, từ chối bind hoặc hết tài nguyên, lỗi có thể lan sang API, thread pool, connection pool và cuối cùng làm toàn bộ ứng dụng chậm theo.

Triển khai production cần chuẩn bị trước cách ứng dụng **phát hiện sự cố, giới hạn thời gian chờ, cô lập tải, giảm chức năng có kiểm soát và phục hồi**. Chỉ thêm một URL dự phòng hoặc tăng timeout không giải quyết được mọi trường hợp. LDAP server có thể vẫn mở TCP nhưng không trả kết quả; pool có thể hết context dù server đã khỏe; replica có thể kết nối được nhưng dữ liệu chưa đồng bộ.

Bài học thuộc chương **Triển khai**, hướng dẫn xây dựng phương án vận hành cho ứng dụng Spring Data LDAP khi directory chậm hoặc không sẵn sàng. Trọng tâm gồm:

1. Phân biệt timeout ở tầng JNDI, LDAP search, connection pool và HTTP.
2. Cấu hình timeout hữu hạn, pool có giới hạn và concurrency phù hợp.
3. Dùng readiness/liveness đúng mục đích; tránh restart dây chuyền khi LDAP gặp sự cố.
4. Áp dụng circuit breaker, bulkhead và retry có giới hạn.
5. Thiết kế degraded mode, cache và chính sách fail-closed cho xác thực/phân quyền.
6. Chuẩn bị failover, graceful shutdown, quan sát và runbook.
7. Kiểm thử sự cố mạng, TLS, pool exhaustion, server chậm và phục hồi.

## 1. Nhận diện đúng kiểu sự cố

“LDAP down” là mô tả quá chung. Mỗi kiểu lỗi cần cách xử lý khác nhau:

| Tình huống | Dấu hiệu | Tác động |
| --- | --- | --- |
| DNS không phân giải được hostname | Unknown host, DNS timeout | Không tìm được endpoint |
| TCP connection bị từ chối | Connection refused | Host/port không lắng nghe hoặc firewall từ chối |
| Kết nối TCP bị drop/blackhole | Connect timeout | Thread chờ đến hết connect timeout |
| TLS handshake/certificate lỗi | SSLHandshakeException, trust/hostname error | Không thiết lập được kênh bảo mật |
| Bind bị từ chối | AuthenticationException, invalid credentials | Credential, account hoặc policy sai |
| LDAP server mở kết nối nhưng không trả lời | Read timeout | Operation có thể treo đến hết read timeout |
| Search quá rộng hoặc server quá tải | TimeLimitExceeded, phản hồi tăng cao | Tăng latency, tiêu thụ tài nguyên |
| Kết quả vượt giới hạn | SizeLimitExceeded | Dữ liệu có thể không đầy đủ |
| Pool không còn context rảnh | Chờ mượn context, pool exhausted | Request chờ dù server có thể đang khỏe |
| Replica không đồng bộ | Đọc thấy dữ liệu cũ/khác nhau | Read-after-write hoặc phân quyền có thể sai |
| Referral trỏ sang server không truy cập được | PartialResultException hoặc lỗi referral | Một phần search không hoàn tất |
| Directory khôi phục nhưng connection cũ đã hỏng | Lỗi trên pooled context | Request đầu sau phục hồi vẫn có thể thất bại |

Hãy tách **khả năng kết nối**, **khả năng bind**, **khả năng thực hiện search**, **độ đầy đủ của kết quả** và **độ mới của dữ liệu**. Một phép thử TCP thành công chỉ chứng minh port có thể nhận kết nối; nó không chứng minh LDAP bind/search đang hoạt động đúng.

### 1.1. Luồng lỗi có thể lan rộng

```text
LDAP server chậm
      |
      v
LDAP operation giữ thread lâu
      |
      v
Request HTTP chờ LDAP
      |
      v
Tomcat/Jetty request threads bị chiếm
      |
      v
Request khác xếp hàng, timeout
      |
      v
Retry tăng tải và pool cạn
      |
      v
Toàn ứng dụng suy giảm
```

Mục tiêu vận hành là **cắt chuỗi lan truyền**: giới hạn mỗi lần chờ, giới hạn số operation đồng thời, không retry vô hạn và quyết định rõ chức năng nào có thể tiếp tục khi directory lỗi.

## 2. Thiết kế ngân sách thời gian từ request đến LDAP

Một HTTP request có deadline tổng thể. Các operation LDAP bên trong phải có giới hạn nhỏ hơn deadline đó để ứng dụng còn thời gian ánh xạ kết quả, ghi log và trả response.

Ví dụ ngân sách minh họa cho endpoint tra cứu hồ sơ:

```text
HTTP request deadline                         2,500 ms
|
|-- Wait for LDAP pool                         <= 200 ms
|-- Connect / TLS / bind (nếu tạo kết nối mới) <= 500 ms
|-- LDAP response read                         <= 1,200 ms
|-- Map result + build HTTP response            <= 200 ms
|
+-- Safety margin                              >= 400 ms
```

Các con số chỉ để minh họa cách chia ngân sách; cần đo latency thực tế, SLA của directory và timeout của ingress/gateway trước khi chọn giá trị production.

Không phải mọi operation đều thực hiện đủ từng bước trên. Nếu dùng connection pool, request có thể mượn context sẵn có; nếu kết nối mới, connect/TLS/bind mới xảy ra. Nếu dùng nhiều URL, thời gian thử từng endpoint có thể cộng dồn. Nếu một request gọi LDAP nhiều lần, cần tính tổng thời gian của tất cả operation và retry.

### 2.1. Năm giới hạn cần phân biệt

| Giới hạn | Điều khiển | Đơn vị | Giới hạn điều gì? |
| --- | --- | ---: | --- |
| Connect timeout | JNDI LDAP provider | ms | Thời gian thiết lập kết nối tới endpoint |
| Read timeout | JNDI LDAP provider | ms | Thời gian chờ phản hồi LDAP |
| Search time limit | JNDI SearchControls / LDAP query | ms | Thời gian xử lý một search theo yêu cầu gửi server |
| Pool max-wait | Spring LDAP PoolingContextSource | ms | Thời gian chờ context được trả về pool |
| HTTP/gateway deadline | Web server, reverse proxy, client | ms | Thời gian tổng của request |

**Một timeout không thay thế các timeout còn lại.** Ví dụ HTTP gateway cắt request sau 2,5 giây nhưng JNDI read timeout không đặt, operation LDAP có thể vẫn giữ thread ở phía server ứng dụng sau khi client đã ngắt kết nối.

### 2.2. JNDI connect timeout

Với JDK LDAP provider mặc định, thuộc tính môi trường thường dùng là:

- `com.sun.jndi.ldap.connect.timeout`
- Giá trị là chuỗi số nguyên milliseconds.
- Giá trị phải lớn hơn 0 để đặt giới hạn hữu hạn.

Nếu không đặt, provider có thể chờ theo TCP/network timeout mặc định, vốn có thể dài hơn nhiều so với thời gian request cho phép. Đây là thuộc tính riêng của JDK LDAP provider; nếu ứng dụng dùng provider khác, cần xác minh tên thuộc tính và hành vi của provider đó.

### 2.3. JNDI read timeout

Với JDK LDAP provider mặc định:

- `com.sun.jndi.ldap.read.timeout` giới hạn thời gian chờ phản hồi LDAP.
- Giá trị là chuỗi milliseconds.
- Không đặt hoặc đặt giá trị không dương có thể tương đương không giới hạn thời gian chờ.

Read timeout rất quan trọng khi server vẫn nhận kết nối nhưng bị treo, quá tải hoặc mạng không chuyển phản hồi. Nó không đồng nghĩa với search time limit: read timeout là giới hạn chờ ở client/provider; search time limit là giới hạn xử lý search được gửi trong LDAP request.

### 2.4. Cấu hình timeout trong LdapContextSource

Spring LDAP cho phép truyền JNDI environment properties qua `setBaseEnvironmentProperties(...)`:

```java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration(proxyBeanMethods = false)
public class LdapConnectionConfiguration {

    @Bean
    LdapContextSource ldapContextSource(
            LdapConnectionProperties properties) {

        LdapContextSource source = new LdapContextSource();
        source.setUrl(properties.url());
        source.setBase(properties.base());
        source.setUserDn(properties.bindDn());
        source.setPassword(properties.password());
        source.setBaseEnvironmentProperties(Map.of(
                "com.sun.jndi.ldap.connect.timeout", "500",
                "com.sun.jndi.ldap.read.timeout", "1200"));
        source.setPooled(false);
        return source;
    }
}
```

`LdapConnectionProperties` là cấu hình ứng dụng tự định nghĩa; ví dụ lược bỏ phần khai báo record và binding properties. Các giá trị `500` và `1200` là ví dụ, không phải ngưỡng bắt buộc cho mọi hệ thống.

Trong Spring container, lifecycle của bean `LdapContextSource` được Spring quản lý. Nếu tự tạo source ngoài container, cần hoàn tất cấu hình và khởi tạo theo lifecycle API trước khi dùng.

**Lưu ý tên property:** JDK LDAP provider dùng `com.sun.jndi.ldap.connect.timeout` và `com.sun.jndi.ldap.read.timeout`. Không tự đổi thành `java.naming.ldap.connect.timeout` nếu provider không tài liệu hóa tên đó.

### 2.5. Search time limit và count limit

Một truy vấn có thể được giới hạn riêng:

```java
import javax.naming.directory.SearchControls;
import org.springframework.ldap.core.LdapTemplate;

SearchControls controls = new SearchControls();
controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
controls.setCountLimit(100);
controls.setTimeLimit(800);

ldapTemplate.search(
        "ou=people",
        "(objectClass=inetOrgPerson)",
        controls,
        personMapper());
```

`setTimeLimit(800)` đặt search time limit theo milliseconds trong JNDI SearchControls; `setCountLimit(100)` giới hạn số entry. Server có thể kết thúc search với lỗi time/size limit. Không được xem tập kết quả bị giới hạn là đầy đủ nếu nghiệp vụ yêu cầu đồng bộ toàn bộ người dùng hoặc membership.

### 2.6. Nhiều URL có thể làm tổng thời gian kết nối dài hơn

Spring LDAP cho phép khai báo nhiều URL trong một `ContextSource` để hỗ trợ failover:

```java
source.setUrls(new String[] {
        "ldaps://ldap-a.example.org:636",
        "ldaps://ldap-b.example.org:636"
});
```

Các URL phải đại diện cho **cùng một directory logic** hoặc các replica có naming context, schema, quyền và semantics phù hợp. Không dùng danh sách URL này để gộp hai directory độc lập.

JDK provider có thể thử nhiều URL; connect timeout được áp dụng cho từng lần thử. Vì vậy tổng thời gian thử các endpoint có thể lớn hơn connect timeout đơn lẻ. Cần đo và tính vào ngân sách request. Failover cũng không đảm bảo dữ liệu replica mới nhất hoặc write đã đồng bộ ngay lập tức.

## 3. Connection pool phải có giới hạn và validation

Tạo kết nối LDAP có thể tốn thời gian do TCP, TLS handshake, bind và DNS. Pool giúp tái sử dụng context nhưng cũng tạo một tài nguyên hữu hạn. Khi pool hết context, request phải chờ hoặc bị từ chối.

Spring LDAP cung cấp `PoolingContextSource`. Những tham số vận hành cần quan tâm:

| Thuộc tính | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `maxActive` | Số context hoạt động tối đa theo loại pool | Phải phù hợp concurrency và giới hạn server |
| `maxIdle` | Số context idle tối đa | Tránh giữ quá nhiều connection lâu |
| `minIdle` | Số context idle tối thiểu | Có thể làm nóng pool, nhưng tạo connection sớm |
| `maxWait` | Thời gian chờ mượn context | Đặt hữu hạn; không chờ vô thời hạn |
| `testOnBorrow` | Validate context trước khi giao cho caller | Giảm nguy cơ nhận context chết, tăng chi phí mỗi lần mượn |
| `testWhileIdle` | Validate context khi đang idle | Giúp loại context cũ, cần cấu hình lịch eviction |
| `testOnReturn` | Validate khi trả context | Có thể tăng operation phụ |
| `nonTransientExceptions` | Exception khiến context bị loại khỏi pool | Mặc định có xử lý CommunicationException |

Theo tài liệu Spring LDAP, pool có thể kiểm tra context bằng một search validation ngắn; validator mặc định dùng timeout khoảng 500 ms và giới hạn một kết quả. Bật validation cho mọi lần borrow có chi phí và cần cân bằng với latency mục tiêu. Với môi trường có load balancer idle timeout hoặc firewall cắt connection, validation có thể hữu ích.

### 3.1. Đừng để pool chờ vô hạn

Nếu `maxWait` là giá trị không dương, pool có thể chờ vô hạn khi hết context (tùy cấu hình exhausted action). Điều này làm request threads bị giữ ngay cả khi JNDI read timeout đã được đặt.

Chọn:

- `maxActive` hữu hạn.
- `maxWait` hữu hạn và nhỏ hơn phần ngân sách còn lại của request.
- Khi pool cạn, trả lỗi có thể retry sau hoặc phản hồi 503/429 tùy nguyên nhân và hợp đồng API.
- Không dùng chế độ GROW để tạo connection không giới hạn khi tải tăng.

### 3.2. Cấu hình pool minh họa

API pool phụ thuộc phiên bản Spring LDAP/Commons Pool mà dependency management chọn. Mẫu sau minh họa các ý chính; đối chiếu setter và loại pool action trong đúng phiên bản dự án:

```java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.ldap.pool.validation.DefaultDirContextValidator;
import org.springframework.ldap.pool.factory.PoolingContextSource;
import org.springframework.ldap.core.support.LdapContextSource;

@Bean
LdapContextSource ldapTargetContextSource(LdapConnectionProperties properties) {
    LdapContextSource target = new LdapContextSource();
    target.setUrl(properties.url());
    target.setBase(properties.base());
    target.setUserDn(properties.bindDn());
    target.setPassword(properties.password());
    target.setPooled(false);
    target.setBaseEnvironmentProperties(Map.of(
            "com.sun.jndi.ldap.connect.timeout", "500",
            "com.sun.jndi.ldap.read.timeout", "1200"));
    return target;
}

@Bean
PoolingContextSource ldapPoolingContextSource(LdapContextSource target) {
    PoolingContextSource pool = new PoolingContextSource();
    pool.setContextSource(target);
    pool.setDirContextValidator(new DefaultDirContextValidator());
    pool.setMaxActive(16);
    pool.setMaxIdle(8);
    pool.setMaxWait(200);
    pool.setTestOnBorrow(true);
    return pool;
}
```

Các số liệu là ví dụ cho một service account cố định. Spring quản lý lifecycle của bean target trước khi inject vào pool; pool cần một validator khi bật test-on-borrow. Cấu hình eviction và loại pool action vẫn cần được chọn theo phiên bản Spring LDAP/Commons Pool và tải thực tế.

### 3.3. Không dùng native JNDI pool thay thế mà không đánh giá

Spring LDAP cảnh báo native JNDI pooling khá hạn chế về validation và maintenance. Tài liệu Spring LDAP khuyến nghị xem xét `PoolingContextSource` khi cần pooling. Native pool cũng không hoạt động phù hợp với các kết nối TLS theo mô tả của Spring LDAP.

Không bật đồng thời nhiều lớp pool mà chưa hiểu rõ vòng đời context; pool chồng pool làm khó xác định wait time, số connection thực tế và việc loại bỏ connection lỗi.

### 3.4. Pool theo principal và service account

Pool thường phù hợp nhất khi context dùng một service account cố định cho các operation đọc/ghi của ứng dụng. Nếu mỗi request bind bằng credential của một người dùng khác nhau, không được giả định pool có thể tái sử dụng context an toàn cho mọi principal. Tài liệu Spring LDAP cảnh báo `PoolingContextSource` giả định môi trường xác thực ổn định cho các context cùng nhóm.

Với LDAP authentication theo credential người dùng, cần dùng luồng bind chuyên biệt và xem xét cẩn thận pooling; không chia sẻ context đã bind của người này sang request của người khác.

## 4. Giới hạn concurrency bằng bulkhead

Ngay cả khi timeout đã đặt, quá nhiều request đồng thời có thể làm pool hết context, directory đạt giới hạn connection/thread và ứng dụng chiếm quá nhiều request thread để chờ LDAP.

**Bulkhead** giới hạn số operation LDAP đồng thời để lỗi ở directory không chiếm hết tài nguyên ứng dụng.

```text
HTTP request threads
       |
       v
Semaphore / bounded executor
       |
       +---- tối đa N LDAP operations ----> LDAP pool
       |
       +---- quá giới hạn -------------> reject nhanh
```

Chọn giới hạn dựa trên:

- Số connection server cho phép từ mỗi application instance.
- Số instance triển khai đồng thời.
- `maxActive` của pool.
- Mức concurrency thực tế của endpoint.
- Khả năng xử lý search của directory.

Ví dụ nếu có 5 pod và mỗi pod có pool 16 context, hệ thống có thể tạo đến 80 context hoạt động cho cùng service account, chưa tính health checks và job nền. Phải tính **tổng theo toàn bộ deployment**, không chỉ theo một JVM.

Không dùng executor có queue không giới hạn. Khi bulkhead đầy, trả lỗi có kiểm soát thay vì xếp hàng vô hạn và để request timeout ở gateway.

## 5. Circuit breaker: tạm ngừng gọi directory khi lỗi liên tiếp

Circuit breaker theo dõi kết quả operation và tạm chặn lời gọi khi dependency liên tục thất bại:

```text
             CLOSED
       (gọi LDAP bình thường)
              |
       lỗi vượt ngưỡng
              v
              OPEN
       (fail fast, không gọi LDAP)
              |
        hết thời gian chờ
              v
           HALF-OPEN
       (thử một số request nhỏ)
          /           \
       thành công    thất bại
          |             |
          v             v
        CLOSED         OPEN
```

Circuit breaker giúp tránh tiếp tục tạo request chờ vào directory đang lỗi, giảm số connection/thread bị giữ và tạo khoảng nghỉ cho server phục hồi.

### 5.1. Đặt circuit breaker quanh service operation

Ví dụ minh họa với Resilience4j:

```java
import io.github.resilience4j.circuitbreaker.annotation.CircuitBreaker;
import org.springframework.stereotype.Service;

@Service
public class PersonLookupService {

    private final PersonRepository repository;

    public PersonLookupService(PersonRepository repository) {
        this.repository = repository;
    }

    @CircuitBreaker(name = "ldapDirectory", fallbackMethod = "fallback")
    public PersonSummary findByUid(String uid) {
        return repository.findByUid(uid)
                .map(PersonSummary::from)
                .orElse(null);
    }

    private PersonSummary fallback(String uid, Throwable error) {
        throw new DirectoryUnavailableException(
                "Directory lookup is temporarily unavailable", error);
    }
}
```

Đây là mẫu minh họa; ứng dụng cần dependency/config Resilience4j và exception nghiệp vụ riêng. Method fallback phải có chữ ký tương thích với method gốc và thêm tham số Throwable ở cuối theo cơ chế Resilience4j.

Không biến mọi lỗi thành circuit failure:

- CommunicationException, ServiceUnavailableException, timeout hoặc pool exhaustion có thể là lỗi hạ tầng.
- AuthenticationException do credential cấu hình sai cần cảnh báo; retry liên tục không sửa được.
- NameNotFoundException là kết quả nghiệp vụ, không phải directory unavailable.
- SizeLimitExceededException có thể chỉ ra query/limit thiết kế sai, không nhất thiết là server outage.

### 5.2. Đừng đặt một circuit breaker cho mọi loại LDAP operation

Tra cứu danh bạ, kiểm tra nhóm quyền và bind xác thực có yêu cầu khác nhau. Có thể tách circuit breaker theo logical operation hoặc directory:

| Operation | Fallback |
| --- | --- |
| Danh bạ công khai/nội bộ | Có thể trả cache đã đánh dấu stale nếu policy cho phép |
| Xác minh credential | Fail closed; không chấp nhận vì LDAP đang lỗi |
| Kiểm tra group/role | Fail closed; không cấp quyền dựa trên dữ liệu thiếu |
| Cập nhật hồ sơ | Báo unavailable; không giả vờ đã ghi thành công |
| Job đồng bộ | Dừng có kiểm soát, lưu checkpoint và retry sau |

Circuit breaker không thay thế timeout. Nếu operation bị treo quá lâu, breaker chỉ có thể ghi nhận failure khi lời gọi kết thúc hoặc timeout wrapper thực sự kết thúc operation. Hãy đặt JNDI connect/read timeout và pool wait trước.

## 6. Retry: chỉ thử lại khi có cơ sở

Retry có thể giúp vượt qua lỗi mạng ngắn hạn, nhưng cũng có thể khuếch đại outage. Một lỗi khiến 100 request cùng retry 3 lần có thể tạo 300 operation mới lên directory đang quá tải.

### 6.1. Retry phù hợp

Có thể cân nhắc retry có giới hạn cho read-only search/lookup có tính idempotent và lỗi kết nối tạm thời hoặc server busy/unavailable.

Quy tắc:

- Giới hạn số lần thử, ví dụ tối đa 1 lần retry sau lần đầu.
- Dùng exponential backoff có jitter.
- Tổng thời gian retry phải nằm trong request/job deadline.
- Tôn trọng circuit breaker và bulkhead.
- Không retry đồng thời ở mọi tầng (HTTP client, service, LDAP wrapper, job scheduler).

### 6.2. Không retry mù quáng các thao tác ghi

Một tình huống nguy hiểm:

1. Ứng dụng gửi LDAP Add.
2. Server đã ghi entry thành công.
3. Phản hồi bị mất trên mạng.
4. Client timeout và nghĩ thao tác thất bại.
5. Client gửi lại Add.
6. Server trả entryAlreadyExists.

Lúc này trạng thái thật **không xác định chỉ từ timeout**. Với write, cần idempotency hoặc reconciliation:

- Lookup DN/định danh trước khi quyết định thử lại.
- So sánh nội dung hiện có với nội dung dự kiến.
- Dùng operation ID/marker nghiệp vụ nếu schema và chính sách cho phép.
- Phân biệt “đã ghi nhưng mất response” với “chưa ghi”.
- Không báo thành công cho caller cho đến khi xác minh trạng thái theo hợp đồng.

Đối với `modifyAttributes`, retry có thể tạo kết quả khác tùy loại modification: ADD cùng giá trị có thể lỗi duplicate; INCREMENT hoặc thay đổi trạng thái có thể không idempotent. Phải xét semantics cụ thể của operation.

### 6.3. Những lỗi không nên retry

| Lỗi | Hướng xử lý |
| --- | --- |
| Invalid credentials / AuthenticationException | Kiểm tra secret, account lock và bind DN |
| InsufficientAccessRightsException | Sửa ACL/authorization |
| Schema violation / ObjectClassViolationException | Sửa dữ liệu hoặc schema mapping |
| Invalid filter / InvalidSearchFilterException | Sửa filter và input validation |
| NameNotFoundException | Xử lý theo nghiệp vụ hoặc kiểm tra DN/base |
| Attribute/value constraint error | Sửa payload và quy tắc dữ liệu |

Retry các lỗi cấu hình/permission chỉ làm log ồn và tăng tải.

## 7. Degraded mode: chức năng nào vẫn chạy được?

Khi LDAP không sẵn sàng, ứng dụng nên có ma trận hành vi thay vì một fallback chung cho tất cả endpoint.

| Chức năng | LDAP không sẵn sàng | Hành vi an toàn |
| --- | --- | --- |
| Danh bạ cơ bản | Có thể dùng cache | Trả dữ liệu stale có timestamp nếu policy cho phép |
| Tra cứu hồ sơ chi tiết | Tùy trường dữ liệu | Chỉ trả cache của view đã được phê duyệt |
| Đăng nhập bằng LDAP bind | Không xác minh được credential | Từ chối tạm thời, không chấp nhận mật khẩu dựa trên cache |
| Kiểm tra role/group | Không xác minh được quyền hiện tại | Fail closed, không cấp quyền |
| Tạo/sửa/xóa LDAP entry | Không ghi được hoặc kết quả không rõ | Trả unavailable, reconciliation nếu timeout mơ hồ |
| Job đồng bộ nhân viên | Tạm ngừng | Giữ checkpoint, chạy lại có kiểm soát |
| Trang không phụ thuộc LDAP | Không bị ảnh hưởng | Tiếp tục phục vụ |

**Cache dữ liệu hồ sơ không phải cache quyền.** Một nhóm người dùng có thể đã bị thu hồi quyền trong LDAP nhưng cache vẫn còn membership cũ. Không dùng stale group membership để cấp quyền truy cập tài nguyên.

### 7.1. Cache stale có nhãn và giới hạn tuổi

```java
public record CachedPersonSummary(
        PersonSummary value,
        Instant fetchedAt) {

    public boolean isStale(Duration maxAge, Instant now) {
        return fetchedAt.plus(maxAge).isBefore(now);
    }
}
```

Response degraded có thể biểu diễn:

```json
{
  "data": {
    "uid": "lan",
    "displayName": "Nguyen Thi Lan"
  },
  "source": "cache",
  "stale": true,
  "fetchedAt": "2026-11-26T10:00:00Z"
}
```

Không trả cache cũ như thể vừa đọc directory thành công. Chọn `maxAge` theo độ nhạy và quy trình nghiệp vụ. Khi vượt tuổi tối đa, trả unavailable thay vì kéo dài stale vô hạn.

### 7.2. Cache phải tách theo view và tenant

Không cache toàn bộ entity LDAP rồi dùng chung cho endpoint có quyền khác nhau. Cache key cần bao gồm logical directory/tenant và view phù hợp; cache value chỉ nên chứa DTO được phép. Nếu cache phục vụ nhiều principal, authorization vẫn phải được đánh giá theo request hiện tại.

### 7.3. Không queue write vô hạn

Nếu LDAP tạm dừng, không nên nhận vô hạn lệnh ghi vào một queue trong RAM. Khi queue đầy hoặc ứng dụng restart, yêu cầu có thể mất. Nếu nghiệp vụ cho phép ghi bất đồng bộ:

- Dùng durable queue/outbox có persistence.
- Có idempotency key.
- Có giới hạn tuổi và số lượng backlog.
- Có trạng thái accepted/pending/failed rõ ràng cho caller.
- Có dead-letter/reconciliation và quy trình replay.

Nếu không có kiến trúc đó, trả 503 để caller thử lại theo hợp đồng là an toàn hơn.

## 8. Readiness, liveness và startup

Spring Boot Actuator có thể cung cấp `LdapHealthIndicator` để kiểm tra LDAP server. Tuy nhiên, **health endpoint tổng thể không tự động đồng nghĩa với readiness của pod**.

### 8.1. Liveness không nên phụ thuộc LDAP

Liveness trả lời: “Process này còn sống và có thể tiếp tục chạy không?”

Nếu LDAP tạm thời down mà liveness trả DOWN, Kubernetes có thể restart tất cả pod. Việc restart không làm LDAP khỏe hơn; khi các pod khởi động lại đồng loạt, chúng còn có thể tạo thêm connection và bind load, làm sự cố nặng hơn.

**Không đưa LDAP health vào liveness.** Liveness nên phản ánh trạng thái nội bộ của ứng dụng, chẳng hạn deadlock hoặc process không thể tiến triển.

### 8.2. Readiness phụ thuộc yêu cầu nghiệp vụ

Readiness trả lời: “Instance này có nên nhận traffic mới không?”

Nếu mọi endpoint quan trọng đều cần LDAP và không có degraded mode, có thể đưa LDAP check vào readiness. Nếu ứng dụng vẫn phục vụ được các chức năng không cần LDAP hoặc có cache hợp lệ, việc đánh DOWN toàn bộ pod có thể loại hết instance khỏi load balancer dù một phần dịch vụ vẫn hoạt động.

Spring Boot không tự thêm mọi external health indicator vào readiness group mặc định. Việc đưa LDAP vào readiness cần là **quyết định kiến trúc**, không bật theo thói quen.

### 8.3. Cấu hình Actuator minh họa

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,ldap
  health:
    ldap:
      enabled: true
```

Cấu hình trên minh họa trường hợp LDAP là dependency bắt buộc để instance nhận traffic chính. Nếu hệ thống có degraded mode và vẫn phục vụ một số route khi LDAP lỗi, hãy thiết kế readiness/custom health group theo hợp đồng traffic thay vì đưa `ldap` vào readiness mặc định.

Actuator health endpoint có thể tiết lộ chi tiết dependency. Chỉ expose qua mạng quản trị hoặc bảo vệ bằng authentication/network policy phù hợp; không công khai bind DN, hostname nội bộ, exception message hoặc cấu hình secret trong health details.

### 8.4. Kubernetes probes

```yaml
livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 2
```

Đây chỉ là ví dụ; cần cân nhắc tần suất health check, timeout, threshold và chi phí kiểm tra LDAP. Không để mỗi probe tạo một search nặng hoặc chạy nhanh hơn mức server chịu được.

Nếu startup kéo dài do cấu hình hoặc khởi tạo dependency, xem xét startupProbe để Kubernetes không kết luận liveness fail trước khi ứng dụng khởi động xong. Nhưng không nên chặn toàn bộ startup vô hạn chỉ vì LDAP đang outage nếu ứng dụng có thể khởi động ở trạng thái chưa ready.

## 9. Startup strategy: fail fast hay khởi động degraded?

| Chiến lược | Khi phù hợp | Rủi ro |
| --- | --- | --- |
| Fail fast khi LDAP không kết nối được | Ứng dụng không có chức năng hữu ích nào nếu thiếu directory; triển khai yêu cầu dependency sẵn sàng | Deployment có thể không lên trong outage LDAP |
| Khởi động nhưng chưa ready/degraded | Ứng dụng có endpoint độc lập hoặc cache hợp lệ | Cần quản lý readiness và mọi luồng LDAP khi dependency chưa phục hồi |

Không để startup hook gọi LDAP với timeout vô hạn. Nếu startup phải kiểm tra directory:

- Đặt timeout hữu hạn.
- Phân biệt lỗi cấu hình (certificate, credentials, base DN) với lỗi tạm thời.
- Có chính sách retry khởi động hữu hạn.
- Đặt readiness DOWN cho chức năng bắt buộc.
- Có cảnh báo rõ khi chạy degraded.

Một bean `LdapContextSource` được tạo không có nghĩa đã xác minh mọi search nghiệp vụ. Health check nên dùng một operation nhẹ, có quyền phù hợp và timeout ngắn.

## 10. Failover và replica

Spring LDAP cho phép nhiều URL trong một ContextSource. Cách này có thể hữu ích khi các endpoint là replica của **cùng directory logic**:

```java
source.setUrls(new String[] {
        "ldaps://ldap-a.example.org:636",
        "ldaps://ldap-b.example.org:636",
        "ldaps://ldap-c.example.org:636"
});
```

Trước khi triển khai, xác minh:

- Cùng naming context/base DN.
- Schema và attribute mapping tương thích.
- Cùng chính sách bind/ACL và TLS trust.
- Replica có replication lag bao lâu.
- Read-after-write có thể đọc từ replica khác hay không.
- URL failover theo thứ tự hay cơ chế khác trong provider đang dùng.
- Tổng thời gian thử nhiều URL nằm trong deadline.

### 10.1. Failover không giải quyết replication lag

Một write được gửi tới node A, sau đó read failover sang node B chưa nhận replication update. Ứng dụng có thể đọc thấy dữ liệu cũ hoặc không tìm thấy entry vừa tạo.

Đối với nghiệp vụ cần read-after-write:

- Ưu tiên đọc từ node có write hoặc node được đảm bảo consistency phù hợp.
- Thiết kế retry đọc có giới hạn nếu biết replication SLA.
- Không dùng dữ liệu replica cũ để quyết định authorization.
- Có reconciliation cho các thao tác ghi bị timeout.

### 10.2. Không đưa nhiều directory độc lập vào cùng URLs

Hai directory độc lập có thể có base DN, schema, credential và dữ liệu khác nhau. Dùng một danh sách URL như thể chúng là replica có thể khiến cùng một request đọc kết quả khác nhau tùy endpoint. Hãy dùng ContextSource/LdapTemplate riêng cho mỗi directory logic và chọn nguồn rõ ràng trong service.

### 10.3. Referral không phải failover miễn phí

LDAP referral có thể dẫn tới host/port khác, yêu cầu TLS và credential khác. Nếu bật follow, cần hiểu credential delegation, trust, timeout và giới hạn hop. Không dùng referral như một cách tự động truy cập mọi directory. Với referral không cần thiết, chọn policy rõ ràng như ignore/throw theo yêu cầu ứng dụng.

## 11. Xử lý lỗi theo loại

Spring LDAP dịch nhiều exception JNDI sang runtime exception trong package `org.springframework.ldap`. Ở service boundary, hãy phân loại lỗi và trả mã HTTP phù hợp, tránh đẩy stack trace hoặc thông tin directory cho client.

| Nhóm lỗi | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Kết nối | `CommunicationException` | Đánh dấu dependency unavailable, circuit breaker |
| Server unavailable | `ServiceUnavailableException` | Retry đọc có giới hạn nếu transient |
| Read timeout | Exception JNDI/Spring LDAP tương ứng | Cắt operation, ghi latency và timeout metric |
| Search time limit | `TimeLimitExceededException` | Thu hẹp query, không retry vô hạn |
| Search size limit | `SizeLimitExceededException` | Phân trang/giảm kết quả; xác định dữ liệu có đầy đủ không |
| Bind/authentication | `AuthenticationException` | Kiểm tra secret/account, không retry liên tục |
| Permission | LDAP result code phù hợp | Kiểm tra ACL và quyền nghiệp vụ |
| DN không tồn tại | `NameNotFoundException` | 404 hoặc xử lý theo domain |
| Pool exhausted | `NoSuchElementException` từ pool | Kiểm tra concurrency, maxActive, maxWait và leak context |
| TLS | `SSLHandshakeException` | Kiểm tra cert, truststore, hostname, clock |

Tên exception thực tế có thể khác tùy provider và lớp Spring translation. Hãy log cause chain đã redaction, không dựa vào một chuỗi message cố định để phân loại.

### 11.1. HTTP mapping

Một quy tắc tham khảo:

| Tình huống | HTTP response thường phù hợp |
| --- | --- |
| LDAP tạm thời unavailable/timeout | 503 Service Unavailable |
| Pool hoặc bulkhead quá tải | 503 hoặc 429 tùy hợp đồng tải |
| Entry không tồn tại | 404 Not Found |
| Caller không được phép | 403 Forbidden hoặc 404 theo chính sách chống enumeration |
| Dữ liệu/filter không hợp lệ | 400 Bad Request |
| Kết quả không đầy đủ do size/time limit | 503/422 hoặc domain error theo hợp đồng; không giả làm thành công đầy đủ |

Nếu dùng Retry-After, giá trị phải phản ánh thời gian thử lại hợp lý; không hứa directory sẽ phục hồi đúng thời điểm đó.

## 12. Observability: đo directory như một dependency production

Không đợi người dùng báo lỗi mới biết LDAP chậm. Theo dõi tối thiểu:

| Metric | Ý nghĩa |
| --- | --- |
| LDAP operation latency p50/p95/p99 | Độ trễ theo loại operation |
| LDAP success/error/timeout rate | Tỷ lệ operation thành công và thất bại |
| Connect/bind failure count | Vấn đề mạng, TLS, credentials |
| Pool active/idle/waiters | Mức sử dụng và tình trạng cạn pool |
| Pool borrow wait duration | Thời gian chờ lấy context |
| Circuit breaker state | CLOSED/OPEN/HALF_OPEN |
| Retry attempts | Số lần retry và tỷ lệ request phải retry |
| Bulkhead rejected count | Request bị từ chối vì vượt concurrency |
| Cache fallback rate / stale age | Tần suất và độ cũ của dữ liệu degraded |
| Replica/endpoint selected | Endpoint nào đang phục vụ request |

Phân tách metric theo logical directory và operation, ví dụ:

```text
directory=staff, operation=search-person, result=success
directory=staff, operation=bind-user, result=timeout
directory=partner, operation=lookup-contact, result=unavailable
```

Không dùng full DN, UID, email hoặc filter làm metric label vì cardinality cao và có thể chứa dữ liệu cá nhân. Không ghi bind password, raw credential, toàn bộ Attributes hoặc raw LDAP filter vào log.

### 12.1. Alert theo triệu chứng và mức ảnh hưởng

Alert nên xét:

- p95/p99 latency vượt ngưỡng liên tục.
- Timeout/error rate tăng.
- Pool waiters hoặc rejected count tăng.
- Circuit breaker mở lâu.
- Readiness chuyển DOWN.
- Cache stale age vượt mức tối đa.
- Replication lag hoặc replica mismatch nếu có metric.

Một lần health check thất bại không nhất thiết là outage; dùng cửa sổ thời gian và ngưỡng phù hợp để tránh alert flapping.

### 12.2. Health check phải nhẹ

Một health check nên:

- Thực hiện một bind/lookup/search rất nhỏ.
- Dùng timeout ngắn và có giới hạn.
- Không tìm toàn bộ người dùng hoặc membership.
- Không ghi dữ liệu.
- Không expose credential hoặc raw exception cho người dùng ngoài.

Nếu Actuator `LdapHealthIndicator` có sẵn, hiểu operation mà indicator thực hiện và timeout của context. Nếu tự viết indicator, không gọi một search nặng trên mỗi probe.

## 13. Graceful shutdown và deployment rollout

Khi triển khai phiên bản mới hoặc pod bị terminate:

1. Đưa instance ra khỏi readiness để ngừng nhận traffic mới.
2. Chờ request đang chạy trong khoảng termination grace period.
3. Dừng scheduler/job nền đang gọi LDAP.
4. Hoàn tất hoặc hủy có kiểm soát operation đang chờ.
5. Đóng pool/context source để giải phóng kết nối.
6. Ghi trạng thái job/checkpoint để instance khác tiếp tục nếu cần.

Không kill process ngay khi request LDAP còn đang ghi dữ liệu nếu nghiệp vụ cần reconciliation. Với write timeout hoặc process termination, trạng thái server có thể không xác định; cần kiểm tra lại trước khi replay.

### 13.1. Pool lifecycle

`PoolingContextSource` triển khai lifecycle để hủy pool khi Spring context đóng. Đảm bảo bean được Spring quản lý và không tạo pool thủ công không có đường đóng. Nếu dùng nhiều directory, đóng từng pool tương ứng.

### 13.2. Rolling deployment

Khi nhiều pod khởi động cùng lúc, tất cả có thể tạo pool ban đầu, health checks và connection burst. Cân nhắc:

- `minIdle` thấp hoặc bằng 0 nếu không cần warm-up lớn.
- Rolling update với maxSurge phù hợp.
- Giới hạn connection tổng của tất cả pod.
- Jitter cho job/health tasks.
- Không chạy full directory sync ngay khi tất cả pod cùng start.

## 14. Runbook khi LDAP chậm hoặc mất kết nối

Khi alert phát sinh, xử lý theo thứ tự để tìm đúng tầng lỗi:

### Bước 1: Xác định phạm vi

- Chỉ một logical directory hay tất cả?
- Chỉ một pod/zone hay toàn bộ deployment?
- Chỉ search hay bind và lookup cũng lỗi?
- Tăng latency hay hoàn toàn không kết nối?
- Readiness DOWN hay ứng dụng vẫn phục vụ cache/degraded mode?

### Bước 2: Kiểm tra mạng và TLS

- DNS có phân giải hostname không?
- TCP port 389/636 có truy cập được từ pod/host ứng dụng không?
- Certificate còn hạn, trust chain và hostname có đúng không?
- Có thay đổi firewall, route, DNS hoặc network policy gần đây không?

Không tắt kiểm tra certificate hoặc chuyển sang plain LDAP để “chữa cháy” mà không có phê duyệt bảo mật.

### Bước 3: Kiểm tra bind và quyền

- Bind DN/secret có bị rotate hoặc hết hạn?
- Service account có bị khóa?
- ACL/schema có thay đổi?
- Search base và filter có còn đúng?

Không log password để kiểm tra; dùng secret manager và công cụ quản trị được cấp quyền.

### Bước 4: Kiểm tra server và truy vấn

- Server CPU, memory, thread, connection count và replication status ra sao?
- Filter có dùng index phù hợp?
- Search scope có rộng bất thường?
- Có time/size limit hoặc referral issue?
- Có nhiều client khác gây tải?

### Bước 5: Kiểm tra ứng dụng

- Pool active/idle/waiters và borrow wait?
- Circuit breaker state?
- Bulkhead reject?
- Retry count có tăng?
- Request deadline có phù hợp?
- Có connection leak hoặc job đồng bộ chạy quá nhiều?

### Bước 6: Phục hồi có kiểm soát

- Xác nhận endpoint/replica khỏe bằng một probe nhỏ.
- Đóng hoặc loại context lỗi khỏi pool theo cơ chế validation/invalidation.
- Mở lại traffic theo readiness/circuit breaker, không đồng loạt retry vô hạn.
- Kiểm tra read-after-write và replication lag.
- Đối soát các write bị timeout hoặc job bị dừng giữa chừng.
- Theo dõi latency/error rate sau phục hồi.

## 15. Kiểm thử resilience trước khi triển khai

Không thể chứng minh phương án vận hành chỉ bằng unit test mapper. Cần integration test và fault injection trong môi trường test/staging có kiểm soát.

### 15.1. Ma trận kiểm thử

| Kịch bản | Cách mô phỏng | Kỳ vọng |
| --- | --- | --- |
| DNS lỗi | Hostname không tồn tại hoặc DNS test fail | Connect thất bại trong ngân sách |
| TCP refused | Tắt listener | Lỗi nhanh, không giữ request lâu |
| TCP blackhole | Drop packet giữa client/server | Connect timeout hữu hạn |
| LDAP read stall | Server nhận request nhưng trì hoãn response | Read timeout kích hoạt |
| Search chậm | Filter/search test có độ trễ | Search time limit hoặc HTTP deadline được áp dụng |
| TLS certificate không hợp lệ | Cert hết hạn/hostname mismatch trong test | Kết nối bị từ chối an toàn |
| Bind sai credential | Dùng secret test sai | Không retry liên tục |
| ACL từ chối | Principal thiếu quyền | Không fallback thành quyền rộng hơn |
| Pool exhaustion | Giữ hết context bằng test concurrency | Max wait/reject hữu hạn |
| Circuit open | Tạo chuỗi lỗi vượt threshold | Request fail fast |
| Bulkhead full | Gửi concurrency vượt giới hạn | Reject có kiểm soát |
| Replica lag | Test node B chậm cập nhật | Không dùng dữ liệu cũ cho authorization |
| Directory phục hồi | Bật lại server sau outage | Context lỗi bị loại, request mới phục hồi |
| Write response lost | Server ghi nhưng test proxy bỏ response | Reconciliation tránh duplicate write |
| Shutdown khi đang search | Terminate instance test có request chạy | Request drain/timeout; pool được đóng |

### 15.2. Kiểm tra timeout thực tế

Đo thời gian từ lúc request bắt đầu đến lúc exception được trả. Không chỉ assert loại exception. Kiểm tra:

- Connect timeout không vượt ngân sách đã đặt, tính cả số URL dự phòng.
- Read timeout hữu hạn khi server không trả response.
- Search time limit được truyền đúng và lỗi được xử lý như kết quả có thể không đầy đủ.
- Pool max-wait hữu hạn khi hết context.
- HTTP response được trả trước gateway deadline với margin.
- Retry tổng thể không vượt job/request deadline.

### 15.3. Kiểm tra sau phục hồi

Một server trở lại không đồng nghĩa mọi context cũ trong pool đều hợp lệ. Sau khi phục hồi:

- Thử lookup nhẹ bằng connection mới.
- Xác minh validation/invalidation của pool.
- Xác minh circuit breaker chuyển HALF_OPEN rồi CLOSED.
- Đo tỷ lệ request đầu tiên thất bại.
- Kiểm tra replica consistency và các write có trạng thái không rõ.

### 15.4. Dữ liệu và credential kiểm thử

Chỉ dùng directory test/staging, dữ liệu giả và service account giới hạn. Không chạy fault injection làm gián đoạn production nếu không có kế hoạch/ủy quyền riêng. Không dùng credential thật trong file test hoặc log.

## 16. Ví dụ cấu hình deployment tổng hợp

Ví dụ YAML dưới đây là cấu hình minh họa cho Spring Boot Actuator và các property ứng dụng tự định nghĩa:

```yaml
app:
  ldap:
    url: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    bind-dn: uid=app-reader,ou=services,dc=example,dc=org
    bind-password: ${LDAP_BIND_PASSWORD}
    connect-timeout-ms: 500
    read-timeout-ms: 1200
    search-timeout-ms: 800
    pool:
      max-active: 16
      max-idle: 8
      max-wait-ms: 200

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,ldap
  health:
    ldap:
      enabled: true
```

Các trường `app.ldap.*` là **property tự định nghĩa**, cần record `@ConfigurationProperties` và Java config ánh xạ chúng sang `LdapContextSource`, `SearchControls`, pool và resilience policy. Spring Boot không tự hiểu tất cả trường minh họa này chỉ vì chúng xuất hiện trong YAML.

Nếu ứng dụng có degraded mode và vẫn phục vụ một số route khi LDAP lỗi, cân nhắc bỏ LDAP khỏi readiness group chung hoặc tạo health group/route policy riêng. Không cấu hình liveness phụ thuộc LDAP.

## 17. Các lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ đặt HTTP timeout | LDAP thread có thể vẫn chờ | Đặt JNDI connect/read, search và pool timeout |
| Không đặt read timeout | Request treo khi server không trả lời | Đặt `com.sun.jndi.ldap.read.timeout` |
| Nhầm property JNDI | Timeout không có tác dụng | Dùng đúng tên theo provider; JDK LDAP dùng `com.sun.jndi.ldap.*` |
| Pool max-wait vô hạn | Request threads bị giữ khi pool cạn | Đặt maxWait hữu hạn |
| Pool không validate context | Context cũ có thể hỏng sau idle/network change | Cấu hình testOnBorrow/testWhileIdle theo tải |
| Tăng maxActive vô hạn | Directory bị quá tải connection | Giới hạn theo tổng số pod |
| Retry mọi exception | Tăng tải và che lỗi cấu hình | Chỉ retry lỗi transient, đọc idempotent |
| Retry LDAP Add/Modify mù quáng | Duplicate hoặc thay đổi dữ liệu nhiều lần | Reconcile trạng thái sau timeout |
| LDAP health nằm trong liveness | Kubernetes restart dây chuyền | Liveness chỉ theo trạng thái nội bộ |
| Mọi LDAP lỗi đều làm readiness DOWN | Chức năng độc lập cũng ngừng phục vụ | Quyết định theo dependency và degraded mode |
| Cache stale được dùng cho role/group | Cấp quyền theo dữ liệu cũ | Fail closed cho authz/authentication |
| Nhiều URL là hai directory độc lập | Kết quả phụ thuộc endpoint và base/schema | Một ContextSource cho một directory logic |
| Không tính replica lag | Read-after-write thất bại | Xác định consistency policy |
| Health check search quá rộng | Probe tự tạo tải lên LDAP | Dùng operation nhẹ và timeout ngắn |
| Không drain khi shutdown | Request/job bị dừng giữa operation | Readiness out, graceful shutdown, checkpoint |
| Log raw DN/filter/credential | Lộ dữ liệu nội bộ | Redact và dùng logical labels |

## 18. Bài tập tự luyện

**Câu 1.** Một request HTTP có deadline 2 giây. Vì sao không nên đặt LDAP read timeout 5 giây?

*Gợi ý:* LDAP operation có thể giữ thread lâu hơn deadline của caller. Chia ngân sách cho pool wait, connect/read, mapping và margin.

**Câu 2.** JNDI connect timeout và read timeout khác nhau thế nào?

*Gợi ý:* Connect timeout giới hạn mở kết nối; read timeout giới hạn chờ phản hồi LDAP sau khi kết nối được thiết lập.

**Câu 3.** Pool đã có 16 context hoạt động, request thứ 17 phải chờ. Tham số nào giới hạn thời gian chờ?

*Gợi ý:* Pool maxWait; đặt hữu hạn và kết hợp bulkhead.

**Câu 4.** LDAP down, liveness của tất cả pod chuyển DOWN và Kubernetes restart liên tục. Cấu hình nào cần xem lại?

*Gợi ý:* Không đưa external LDAP dependency vào liveness. Readiness mới là nơi cân nhắc dependency theo khả năng phục vụ.

**Câu 5.** Có thể dùng cache group membership cũ để cho phép người dùng truy cập khi LDAP lỗi không?

*Gợi ý:* Không nếu cache có thể chứa quyền đã bị thu hồi. Authentication và authorization nên fail closed.

**Câu 6.** LDAP Add timeout. Có nên gửi lại Add ngay không?

*Gợi ý:* Không. Server có thể đã ghi nhưng response bị mất. Lookup/reconcile trạng thái trước khi replay.

**Câu 7.** Ba URL LDAP có connect timeout 500 ms. Có thể cam kết request luôn kết nối trong 500 ms không?

*Gợi ý:* Không. Provider có thể thử nhiều URL; tổng thời gian thử có thể cộng dồn, ngoài DNS/TLS/bind.

**Câu 8.** Circuit breaker OPEN nhưng operation đang bị treo trong JNDI. Breaker có tự dừng network call không?

*Gợi ý:* Không mặc nhiên. Cần connect/read timeout hữu hạn; breaker chủ yếu ngăn lời gọi mới và theo dõi kết quả.

**Câu 9.** Khi nào nên đưa LDAP HealthIndicator vào readiness?

*Gợi ý:* Khi instance không thể phục vụ traffic quan trọng nếu LDAP unavailable. Nếu có degraded mode, cân nhắc route/health group phù hợp.

**Câu 10.** Directory đã phục hồi nhưng request đầu tiên vẫn lỗi trên pooled context cũ. Cần chuẩn bị gì?

*Gợi ý:* Validation/invalidation context, test-on-borrow hoặc cơ chế loại context lỗi và probe phục hồi.

## 19. Ghi nhớ

- **Phân loại lỗi trước khi xử lý:** DNS, TCP, TLS, bind, read timeout, search limit, pool exhaustion và replication lag là các vấn đề khác nhau.
- **Đặt timeout ở mọi tầng:** JNDI connect/read, search time limit, pool max-wait và HTTP deadline phải nằm trong một ngân sách tổng.
- Với JDK LDAP provider, tên property là **`com.sun.jndi.ldap.connect.timeout`** và **`com.sun.jndi.ldap.read.timeout`**, giá trị milliseconds.
- **Pool phải hữu hạn:** giới hạn maxActive, maxWait, concurrency; validate context theo tải và không dùng pool không giới hạn.
- **Bulkhead và circuit breaker** giúp cô lập dependency; chúng không thay thế timeout network.
- **Retry có chọn lọc:** ưu tiên read-only idempotent; không retry mù quáng Add/Modify sau timeout vì kết quả có thể không xác định.
- **Degraded mode có ranh giới:** cache danh bạ có thể chấp nhận nếu được đánh dấu stale; authentication và authorization phải fail closed.
- **Liveness không phụ thuộc LDAP.** Readiness có thể phụ thuộc LDAP nếu dependency bắt buộc để phục vụ traffic.
- **Failover URL chỉ dành cho cùng directory logic**; replica lag có thể làm đọc sau ghi không nhất quán.
- **Graceful shutdown và reconciliation** cần xử lý request/job đang chạy và write có trạng thái không rõ.
- Kiểm thử DNS, TCP blackhole, read stall, TLS, bind, pool exhaustion, circuit breaker, replica lag và phục hồi trước production.

**Tài liệu tham khảo chính thức:**

- [Spring LDAP — Configuration](https://docs.spring.io/spring-ldap/reference/configuration.html): ContextSource, URLs, environment properties, referral và pooling.
- [Spring LDAP — Pooling Support](https://docs.spring.io/spring-ldap/reference/pooling.html): PoolingContextSource, validation, maxActive, maxWait và exception invalidation.
- [Spring LDAP API — PoolingContextSource](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/pool/factory/PoolingContextSource.html): cấu hình pool và lifecycle.
- [Spring LDAP API — AbstractContextSource](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/support/AbstractContextSource.html): setUrls, setBaseEnvironmentProperties và native pooling.
- [Oracle Java — JNDI LDAP Provider Properties](https://docs.oracle.com/en/java/javase/26/docs/api/java.naming/module-summary.html): JDK provider connect/read timeout và môi trường JNDI.
- [Oracle JNDI Tutorial — Setting Timeout for LDAP Operations](https://docs.oracle.com/javase/tutorial/jndi/newstuff/readtimeout.html): read timeout và phân biệt connect timeout.
- [Oracle JNDI Tutorial — Connection Creation](https://docs.oracle.com/javase/tutorial/jndi/ldap/create.html): connect timeout và nhiều provider URL.
- [Spring Boot Actuator — Endpoints and Health](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): LdapHealthIndicator, readiness/liveness và Kubernetes probes.
- [Spring Boot 3.5 — Actuator Endpoints](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html): health groups và external dependency guidance.
- [Resilience4j — CircuitBreaker](https://resilience4j.readme.io/docs/circuitbreaker): state machine, failure classification, sliding window và event handling.
- [Spring Cloud CircuitBreaker — Resilience4j](https://docs.spring.io/spring-cloud-circuitbreaker/docs/current/reference/html/spring-cloud-circuitbreaker-resilience4j.html): tích hợp circuit breaker, TimeLimiter và Bulkhead trong Spring.
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/): repository, ODM và truy vấn LDAP.
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511): LDAP operations và result codes.

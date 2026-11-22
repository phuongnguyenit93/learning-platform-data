# Timeout, pooling và lỗi máy chủ thư mục

## 1. Bài toán trong Spring Boot Integration

Một dịch vụ **Spring Boot Integration** đồng bộ tài khoản nhân viên từ LDAP/Active Directory (AD), đối chiếu quyền trước khi gọi API nội bộ và gửi kết quả qua cơ sở dữ liệu hoặc broker. Đường tích hợp có thể gặp một số tình huống khó phân biệt: domain controller không phản hồi; kết nối cũ trong pool đã chết; tài khoản bind của ứng dụng hết hạn mật khẩu; LDAP trả referral; hoặc một truy vấn quá rộng bị server giới hạn.

Mỗi tình huống cần một phản ứng khác nhau. Nếu không đặt timeout, một thread xử lý HTTP hoặc message có thể bị giữ quá lâu. Nếu pooling không kiểm tra connection, người dùng gặp lỗi ngẫu nhiên sau thời gian nhàn rỗi. Nếu retry mọi lỗi, ứng dụng có thể lặp lại sai mật khẩu và gây khóa tài khoản. Nếu coi LDAP timeout là “không tìm thấy nhân viên”, ứng dụng có thể xóa nhầm dữ liệu cache hoặc đồng bộ sai.

Bài học này tập trung vào **ba lớp điều khiển**:

1. **Timeout:** giới hạn thời gian thiết lập kết nối, chờ phản hồi, mượn context và thời gian xử lý toàn luồng.
2. **Pooling:** tái sử dụng các `DirContext` khi phù hợp, đặt giới hạn và kiểm tra kết nối hỏng.
3. **Lỗi máy chủ thư mục:** phân loại, ghi nhận, retry/failover có kiểm soát và giữ đúng hợp đồng dữ liệu.

### Luồng minh họa

~~~mermaid
flowchart TD
    A[HTTP / Kafka / Scheduled sync] --> B[EmployeeDirectoryAdapter]
    B --> C{Circuit breaker cho phép?}
    C -- Không --> H[Trả DirectoryUnavailable / trì hoãn message]
    C -- Có --> D[Mượn DirContext từ pool]
    D --> E{Pool có context khả dụng?}
    E -- Không --> H
    E -- Có --> F[LDAP search với timeout]
    F --> G{Kết quả}
    G -- Tìm thấy --> I[Ánh xạ hồ sơ nội bộ]
    G -- Không tìm thấy hợp lệ --> J[Not found theo hợp đồng]
    G -- Server timeout / disconnect --> H
    G -- Bad credentials / schema / referral --> K[Phân loại, xử lý riêng]
    I --> L[DB / HTTP / Broker]
~~~

**Nguyên tắc thiết kế:** “LDAP không có bản ghi” chỉ có thể được xác nhận sau **một thao tác tìm kiếm hoàn tất thành công** trên phạm vi đúng. Lỗi kết nối, timeout hoặc chỉ nhận được một phần kết quả là trạng thái *không chắc chắn*, không được chuyển thành danh sách rỗng.

## 2. Những lớp timeout cần biết

LDAP client trong Spring thường dựa trên **Spring LDAP → JNDI → socket → máy chủ thư mục**. Các giới hạn thời gian hoạt động ở những lớp khác nhau và không thay thế nhau.

| Giới hạn | Áp dụng cho bước nào? | Cấu hình minh họa | Khi hết thời gian |
| --- | --- | --- | --- |
| TCP/connect timeout | Thiết lập kết nối tới một host LDAP | `com.sun.jndi.ldap.connect.timeout=2000` | Không thiết lập được socket trong giới hạn; có thể thử endpoint khác tùy provider/topology |
| LDAP read timeout | Chờ phản hồi LDAP sau khi gửi thao tác | `com.sun.jndi.ldap.read.timeout=5000` | Thao tác bị ngắt ở phía client; kết quả chưa chắc đã thất bại ở server |
| SearchControls time limit | Giới hạn thời gian tìm kiếm ở tầng search/JNDI | `SearchControls#setTimeLimit(3000)` | Có thể nhận lỗi time limit; không coi dữ liệu dở dang là đầy đủ |
| Pool borrow timeout | Đợi một `DirContext` rảnh khi pool đã đầy | `PoolConfig#setMaxWaitMillis(750)` | Không mượn được context trong thời gian cho phép |
| Tổng deadline của request/job | Ngân sách cho LDAP + kiểm tra + DB/API/broker | Timeout ở tầng service/caller | Dừng/đánh dấu công việc quá hạn, phải kiểm soát retry |
| Server-side search limit | Giới hạn server áp cho từng bind/query | Chính sách size/time limit của LDAP server | Server từ chối hoặc trả một phần kết quả |

### 2.1. Connect và read timeout của JDK LDAP provider

Với **JNDI LDAP provider tích hợp trong JDK**, hai property phổ biến là:

~~~properties
com.sun.jndi.ldap.connect.timeout=2000
com.sun.jndi.ldap.read.timeout=5000
~~~

Đơn vị là **mili giây**, biểu diễn bằng chuỗi số nguyên dương. Chúng là **thuộc tính đặc thù của provider JDK**, không phải tên property tiêu chuẩn bắt buộc mọi LDAP client phải hỗ trợ. Nếu không đặt connect timeout, JNDI có thể chờ theo thời gian kết nối mạng hệ điều hành. Nếu không đặt read timeout hoặc đặt giá trị `<= 0`, thao tác đọc có thể chờ vô hạn theo hành vi provider. Một số custom socket factory có thể không tuân thủ connect timeout; cần kiểm tra khi thay TLS/socket layer.

Không nên nhầm `connect.timeout=2000` với “toàn bộ truy vấn LDAP sẽ hoàn thành dưới 2 giây”: sau khi TCP kết nối, bind/TLS, search, truyền và đọc kết quả vẫn cần thời gian riêng. Với nhiều LDAP URL, mỗi lần thử endpoint có thể tiêu tốn ngân sách; tổng thời gian có thể lớn hơn timeout của một kết nối đơn lẻ.

### 2.2. Deadline ở cấp nghiệp vụ

Giả sử endpoint HTTP có SLA 3 giây. Nếu đặt LDAP read timeout 10 giây và pool borrow timeout 5 giây, chỉ riêng LDAP đã có khả năng vượt SLA. Một cấu hình ban đầu hợp lý phải tính:

~~~text
Ngân sách request ≈ pool-wait + connect/TLS/bind + search/read
                  + thời gian ánh xạ + downstream DB/HTTP
                  + khoảng an toàn cho retry/serialization
~~~

Ví dụ bắt đầu ở môi trường được đo tải: mượn pool tối đa `500 ms`, connect timeout `1.500 ms`, read timeout `3.000 ms`, toàn request `5.000 ms`. Đây chỉ là giá trị *minh họa*, chưa phải cấu hình tối ưu cho mọi doanh nghiệp. Nếu retry hoặc có nhiều DC, phải tính lại ngân sách tổng và không cộng vô hạn các lần thử.

Đặt timeout ở tầng HTTP/controller **không tự động hủy một LDAP socket call đang chặn**; cần giới hạn tại JNDI và quản lý thread/concurrency. Ngược lại, một future bị cancel không chứng minh search hoặc thao tác sửa thuộc tính đã được máy chủ dừng thực thi.

### 2.3. Time limit và size limit của search

`SearchControls.setTimeLimit(...)` và `setCountLimit(...)` giúp giới hạn search do ứng dụng phát ra. Để truy vấn một nhân viên theo mã cố định, nên giới hạn số kết quả (ví dụ 2, để còn nhận biết dữ liệu trùng) và search base rõ ràng. Tuy nhiên, server còn có chính sách riêng; khi gặp `TimeLimitExceededException`, `SizeLimitExceededException` hoặc `PartialResultException`, không được mặc định kết quả trả về đã đầy đủ.

## 3. Cấu hình timeout bằng Spring Boot

Khi có `spring-boot-starter-data-ldap`, Spring Boot có thể tự cấu hình `LdapContextSource` và `LdapTemplate`. Ví dụ dùng LDAPS cho môi trường vận hành:

~~~xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-data-ldap</artifactId>
</dependency>
~~~

~~~yaml
# application.yml
spring:
  ldap:
    urls:
      - ldaps://ldap-a.example.internal:636
      - ldaps://ldap-b.example.internal:636
    base: dc=example,dc=internal
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
    referral: ignore
    base-environment:
      "[com.sun.jndi.ldap.connect.timeout]": "2000"
      "[com.sun.jndi.ldap.read.timeout]": "5000"
~~~

| Property | Tác dụng |
| --- | --- |
| `spring.ldap.urls` | Danh sách LDAP server URL để tạo context; hỗ trợ phương án thử endpoint khác khi một endpoint không khả dụng |
| `spring.ldap.base` | Base DN của các thao tác; các DN ở API `LdapTemplate` thường tương đối với base |
| `spring.ldap.username/password` | Danh tính *service account* dùng cho các thao tác quản trị/đọc theo quyền được cấp |
| `spring.ldap.referral` | Chiến lược xử lý referral; chọn `ignore`/`follow`/`throw` sau khi hiểu topology |
| `spring.ldap.base-environment.*` | Thuộc tính môi trường JNDI, ví dụ timeout của JDK LDAP provider |

Các key JNDI được đặt trong ngoặc vuông và dấu nháy để **giữ nguyên dấu chấm** khi Spring Boot bind map sang môi trường `DirContext`. Không viết nhầm `spring.ldap.connect-timeout` rồi kỳ vọng Boot tự tạo timeout: ví dụ này dùng `base-environment` để truyền đúng hai khóa của JNDI provider.

### 3.1. Bảo mật LDAPS và StartTLS

`ldaps://` bảo vệ phiên kết nối ngay từ đầu bằng TLS. Kết nối LDAP thường (`ldap://`) không nên truyền mật khẩu bind ở dạng rõ trên mạng. Với Spring Boot hỗ trợ SSL bundle cho LDAP, có thể chỉ định `spring.ldap.ssl.bundle` trỏ tới bundle chứa trust material phù hợp; cơ chế này áp dụng cho LDAPS theo tài liệu phiên bản Boot đó. **StartTLS** là cơ chế nâng cấp một kết nối `ldap://` hiện có và cần `DirContextAuthenticationStrategy`/socket setup tương ứng; không đồng nhất StartTLS với LDAPS hay tự trộn cách cấu hình.

Chỉ sử dụng certificate hợp lệ và trust store được quản lý; **không tắt xác minh certificate/hostname** chỉ để hết lỗi kết nối. Trong production, tài khoản service chỉ có quyền tối thiểu, secret được cấp từ secret manager, rotation có kế hoạch và không log DN mật khẩu hoặc dữ liệu thuộc tính nhạy cảm.

### 3.2. Nhiều URL là failover, không phải bảo đảm HA tuyệt đối

Danh sách `spring.ldap.urls` hỗ trợ kết nối tới nhiều endpoint, nhưng:

- Không có bảo đảm rằng mọi request tự chia đều giữa các DC.
- Một context đã có TCP connection không tự di chuyển tức thời khi máy chủ đó ngừng hoạt động.
- Pool có thể chứa context đã mất kết nối sau sự cố mạng hoặc failover.
- Nhiều DC có thể chưa đồng bộ hoàn toàn; một thao tác đọc ngay sau ghi có thể thấy dữ liệu cũ nếu đổi endpoint.
- Một lỗi bind do tài khoản sai mật khẩu hoặc certificate lỗi **không** được coi là “server đang quá tải” để thử vô hạn.

Muốn tính sẵn sàng cao, cần kết hợp nhiều endpoint, DNS/health hợp lý, timeout hữu hạn, validation khi mượn context, retry có điều kiện và giám sát thực tế. Với Active Directory, cần hiểu sự khác nhau giữa domain controller, Global Catalog, referral, miền con và độ trễ replication.

## 4. Connection pooling: lợi ích, giới hạn và lựa chọn

Tạo kết nối LDAP thường bao gồm TCP, TLS và bind bằng tài khoản service. Nếu nhiều truy vấn ngắn lặp lại, chi phí khởi tạo này đáng kể. Pool tái sử dụng `DirContext` và hạn chế số lượng kết nối đồng thời tới directory server.

### 4.1. So sánh ba phương án

| Phương án | Đặc điểm | Phù hợp khi |
| --- | --- | --- |
| Không pooling | Mỗi thao tác mượn/mở context rồi đóng; đơn giản, không giữ connection cũ | Tải thấp, kiểm thử ban đầu, hoặc bind bằng credential thay đổi liên tục |
| JNDI native pooling | Bật qua `LdapContextSource.setPooled(true)`; nhiều cấu hình nằm ở JVM system properties | Yêu cầu đơn giản và đã hiểu giới hạn JNDI |
| Spring LDAP Commons Pool 2 | `PooledContextSource` bọc một `ContextSource`; giới hạn tổng/per-key, wait timeout, validation và evict | Dịch vụ có nhiều lần lookup/bind qua tài khoản service cố định, cần quan sát và kiểm soát pool |

Spring LDAP **không bật JNDI pooling theo mặc định**. Không nên bật đồng thời native pooling và Spring LDAP pooling trên cùng target context: hai lớp pool có thể che khuất kết nối chết và khiến đo lường khó chính xác.

### 4.2. Các kích thước cần điều chỉnh

| PoolConfig | Ý nghĩa |
| --- | --- |
| `maxTotal` | Tổng số context đang tồn tại trong pool, gồm active và idle |
| `maxTotalPerKey` | Giới hạn theo loại context/key; read-only và read-write có thể có pool riêng |
| `maxIdlePerKey` | Tối đa số context idle cho từng key |
| `minIdlePerKey` | Số context idle tối thiểu theo key khi cơ chế hỗ trợ tạo/duy trì |
| `maxWaitMillis` | Thời gian tối đa chờ khi đã đạt giới hạn và pool đang bận |
| `testOnBorrow` | Validate context trước khi bàn giao cho truy vấn |
| `testWhileIdle` | Định kỳ kiểm tra context idle, tránh để connection chết tồn tại mãi |
| `timeBetweenEvictionRunsMillis` | Chu kỳ chạy evictor/validator cho connection idle |

Ví dụ ứng dụng có 10 thread xử lý message, mỗi thread dùng một LDAP context tại một thời điểm. Có thể bắt đầu với `maxTotal=12`, `maxTotalPerKey=12` và `maxWaitMillis=750` rồi đo số connection thực tế, số waiter và P95 latency. **Không** nhân tùy tiện pool 100 connections cho mỗi pod nếu toàn cụm có 50 pod: tổng lên 5.000 connection có thể vượt giới hạn directory server.

### 4.3. Ví dụ Spring LDAP Pool 2 có validation

Spring LDAP cung cấp `PooledContextSource` dựa trên Apache Commons Pool 2. Khi dependency `spring-ldap-core` đã có qua starter, cần bảo đảm runtime có `commons-pool2` tương thích:

~~~xml
<dependency>
  <groupId>org.apache.commons</groupId>
  <artifactId>commons-pool2</artifactId>
</dependency>
~~~

Spring Boot dependency management/BOM quyết định phiên bản; đối chiếu BOM trong dự án nếu dùng dependency management tùy biến.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.ldap.core.support.LdapContextSource;
import org.springframework.ldap.pool2.factory.PoolConfig;
import org.springframework.ldap.pool2.factory.PooledContextSource;
import org.springframework.ldap.pool2.validation.DefaultDirContextValidator;

@Configuration
public class DirectoryPoolConfig {

    @Bean
    @Primary
    PooledContextSource pooledDirectoryContextSource(
            LdapContextSource bootConfiguredTarget) {

        // Mỗi JVM/pod có pool riêng; cần tính tổng trên cả deployment.
        PoolConfig config = new PoolConfig();
        config.setMaxTotal(12);
        config.setMaxTotalPerKey(12);
        config.setMaxIdlePerKey(6);
        config.setMinIdlePerKey(0);
        config.setBlockWhenExhausted(true);
        config.setMaxWaitMillis(750);

        // Phát hiện context chết do server restart, firewall hoặc TLS đóng.
        config.setTestOnBorrow(true);
        config.setTestWhileIdle(true);
        config.setTimeBetweenEvictionRunsMillis(30_000);
        config.setMinEvictableIdleTimeMillis(60_000);

        // Target do Boot tạo đã chứa urls/base/bind DN/timeout.
        // Để native JNDI pooling tắt, tránh chồng hai loại pool.
        PooledContextSource pooled = new PooledContextSource(config);
        pooled.setContextSource(bootConfiguredTarget);
        pooled.setDirContextValidator(new DefaultDirContextValidator());
        return pooled;
    }
}
~~~

Bean `@Primary` nói với Spring dùng `PooledContextSource` khi tự cấu hình `LdapTemplate`, trong khi bean `LdapContextSource` gốc vẫn làm target. Đây là mô hình Spring Boot tài liệu hóa; cần kiểm tra auto-configuration và bean resolution ở đúng phiên bản đang dùng. Nếu ứng dụng có nhiều directory tenant hoặc nhiều `LdapTemplate`, đặt qualifier rõ ràng, không tùy ý đánh dấu mọi context source là primary.

**`DefaultDirContextValidator`** thử một truy vấn kiểm tra nhẹ trước khi cho dùng lại context (mặc định tìm `objectClass=*` trên base tương đối, một kết quả). Với AD hoặc subtree không cho query ở base, cần đặt base/filter kiểm tra phù hợp, hoặc validation có thể liên tục trả false dù kết nối vẫn khỏe. `testOnBorrow=true` tăng độ tin cậy nhưng thêm một lần round-trip; đo latency thực tế trước khi quyết định duy trì nó cho mọi truy vấn.

Spring LDAP có thể invalid context ngay khi gặp exception được xem là non-transient như communication failure. Tuy nhiên, một kết nối mới mượn từ pool không phải bảo đảm thao tác phía sau sẽ thành công: server vẫn có thể ngừng đáp ứng trong lúc đang thực thi search. Vì vậy **pool validation + read timeout + retry có giới hạn** cần được thiết kế cùng nhau.

### 4.4. Vì sao không dùng cùng pool để bind bằng mật khẩu người dùng?

Pool được thiết kế hiệu quả nhất cho truy vấn từ **một service account ổn định**. Nếu mỗi request HTTP dùng tài khoản cá nhân khác nhau, context được tái sử dụng sai principal có nguy cơ dẫn đến lỗi hoặc sai ranh giới bảo mật. Đặc biệt, không bọc một `LdapContextSource` với `AuthenticationSource` thay đổi credential theo thread bằng pool dùng chung.

Với xác thực người dùng bằng LDAP bind, nên sử dụng một context phù hợp cho mỗi lần kiểm tra credential hoặc cơ chế xác thực chuyên dụng của Spring Security LDAP; không để cached authentication context của người này được cấp cho người khác. Việc đổi mật khẩu/khóa tài khoản phải có hiệu lực theo chính sách bảo mật, không phụ thuộc vào context cũ đã xác thực trước đó.

Lưu ý thêm: Spring LDAP có hai họ tên dễ nhầm:

- `org.springframework.ldap.pool.factory.PoolingContextSource` dựa trên Commons Pool thế hệ cũ.
- `org.springframework.ldap.pool2.factory.PooledContextSource` dựa trên Commons Pool 2 và được dùng trong ví dụ.

Đọc API của phiên bản Spring LDAP đang dùng trước khi sao chép setter và các default. Không đồng nhất `PooledContextSource` với `LdapContextSource#setPooled(true)` của JNDI native pool.

### 4.5. Kiểm soát pool exhaustion

Khi 12 context đang được mượn và request thứ 13 tới:

~~~text
request --> borrow context
             |
         pool đã đầy?
          /       \
        Không      Có
         |          |
      dùng ngay    chờ tối đa 750 ms
                     |
                 có context trả?
                  /        \
                Có         Không
                 |           |
            validate/use   pool borrow failure
~~~

Nếu không có `maxWaitMillis` hữu hạn, các thread có thể xếp hàng không giới hạn, khiến timeout toàn luồng vô nghĩa. Với retry tự động, một số request có thể chiếm nhiều lượt borrow và làm quá tải pool nhanh hơn. Cần đặt giới hạn số LDAP operation in-flight ở tầng ứng dụng, theo dõi số active/idle/waiter, và cân nhắc từ chối sớm khi circuit breaker đang mở.

## 5. Phân loại lỗi LDAP để xử lý đúng

Spring LDAP thường chuyển checked `javax.naming.NamingException` của JNDI thành các runtime exception cùng ý nghĩa trong namespace `org.springframework.ldap.*`. Không được bắt nhầm `javax.naming.AuthenticationException` khi tầng gọi đã qua `LdapTemplate` và chỉ phát Spring exception.

| Lỗi / tín hiệu | Khả năng nguyên nhân | Có retry ngay? | Cách xử lý |
| --- | --- | --- | --- |
| `org.springframework.ldap.CommunicationException` | Kết nối đứt, socket đóng, server không thể liên lạc, timeout mạng | Có điều kiện, số lần hữu hạn | Invalidate context, thử lại có backoff/jitter, đổi endpoint nếu phù hợp |
| `ServiceUnavailableException` | Directory server không phục vụ hoặc tạm không sẵn sàng | Có điều kiện | Kiểm tra server/bind/throttle, circuit breaker nếu lỗi liên tục |
| `AuthenticationException` | Bind DN/mật khẩu sai, tài khoản bị khóa/hết hạn hoặc policy xác thực | Không retry cùng credential | Phân biệt lỗi service account với credential người dùng, cảnh báo/đổi secret nếu cần |
| `NoPermissionException` | Tài khoản không có quyền truy cập DN/thuộc tính | Không retry | Sửa ACL/bind identity, tránh ghi log nội dung nhạy cảm |
| `NameNotFoundException` | Base DN hoặc entry không tồn tại | Không retry vô hạn | Phân biệt “không tìm thấy user hợp lệ” với sai base/config |
| `InvalidNameException` / `InvalidSearchFilterException` | DN hoặc filter không hợp lệ | Không retry | Sửa mapping/filter; escape input từ bên ngoài |
| `SizeLimitExceededException` | Search vượt số entry server/client cho phép | Thường không | Thu hẹp search base, filter, paging |
| `TimeLimitExceededException` | Server/client search time limit bị vượt | Theo chính sách | Tối ưu filter/index, giới hạn phạm vi và tăng giới hạn nếu có căn cứ |
| `PartialResultException` | Referral hoặc kết quả không đầy đủ, thường gặp một số topology AD | Không xem là empty result | Cấu hình referral đúng, báo kết quả chưa chắc chắn |
| `SchemaViolationException` / `AttributeModificationException` | Thao tác sửa DN/attribute vi phạm schema | Không retry | Sửa dữ liệu hoặc thao tác nghiệp vụ |
| `DataAccessResourceFailureException` khi borrow pool | Pool hết context, validation thất bại hoặc tạo context lỗi | Có điều kiện sau backoff | Quan sát pool wait, loại context chết, giảm concurrency |
| Lỗi TLS certificate / hostname | Trust chain không đúng, chứng chỉ hết hạn, tên không khớp | Không retry cùng cấu hình | Sửa trust/cert/DNS; không tắt xác minh TLS |

**Không dùng “exception class duy nhất” làm quy tắc tuyệt đối.** Một lỗi kết nối có thể bị bọc qua Spring Data access exception, pool exception hoặc lỗi TLS gốc; cần xem `cause chain` và error code LDAP của provider. Ngược lại, `NameNotFoundException` khi lookup DN cụ thể có thể là kết quả nghiệp vụ “không có”, nhưng khi tìm kiếm nhân viên mà base OU bị đổi tên thì đó là lỗi cấu hình nghiêm trọng.

### 5.1. Phân biệt bind của ứng dụng và bind người dùng

Hai request có thể đều gặp lỗi authentication nhưng ý nghĩa khác:

1. **Ứng dụng kết nối LDAP bằng service account:** lỗi bind khiến *mọi* lần lookup thất bại. Hệ thống nên cảnh báo vận hành, đánh dấu dependency unhealthy theo chính sách và tránh trả về “người dùng không tồn tại”.
2. **Người dùng đăng nhập bằng credential riêng:** sai password có thể trở thành kết quả xác thực không hợp lệ của request đó, nhưng đừng liên tục retry cùng mật khẩu; phải tuân thủ chính sách bảo mật của IdP/AD và không tiết lộ chi tiết “user tồn tại hay không” trên public response.

Hai loại bind nên tách context source/đường gọi, phân quyền và logging. Pool service account không được dùng để tránh cơ chế lockout ở bước xác thực người dùng.

### 5.2. Referral, PartialResultException và search nhiều domain

Một directory có thể trả referral tới một naming context hoặc domain controller khác. Spring Boot hỗ trợ `spring.ldap.referral` và LDAP provider có các chế độ:

- `ignore`: không tự follow referral; tùy provider/server có thể phát `PartialResultException`.
- `follow`: thử theo referral, có thêm kết nối/TLS/bind, latency và yêu cầu trust/credential phù hợp.
- `throw`: trả lỗi referral cho caller quyết định tiếp.

Trong môi trường AD nhiều domain, cần hiểu OU, naming context, Global Catalog và các thuộc tính được nhân bản. Đừng bật `spring.ldap.template.ignore-partial-result-exception=true` chỉ để “hết lỗi” rồi tin dữ liệu trả về đã đầy đủ. Chỉ chấp nhận bỏ qua partial result khi nghiệp vụ **thực sự cho phép kết quả thiếu** và có cảnh báo/đo lường.

## 6. Ví dụ tích hợp: tìm hồ sơ nhân viên với giới hạn và lỗi rõ ràng

Adapter phía dưới là biên giữa Spring Boot và directory server. Nó trả `Optional.empty()` **chỉ khi truy vấn LDAP hoàn tất bình thường mà không có kết quả**; đối với lỗi kết nối, nó ném một lỗi nghiệp vụ tạm thời để tầng HTTP/message consumer quyết định retry.

~~~java
// DirectoryProfile.java
public record DirectoryProfile(
        String uid,
        String displayName,
        String email) {
}
~~~

~~~java
// DirectoryTemporarilyUnavailable.java
public class DirectoryTemporarilyUnavailable extends RuntimeException {

    public DirectoryTemporarilyUnavailable(
            String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

~~~java
// EmployeeDirectoryAdapter.java
import java.util.List;
import java.util.Optional;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

import org.springframework.ldap.CommunicationException;
import org.springframework.ldap.ServiceUnavailableException;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.stereotype.Component;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

@Component
public class EmployeeDirectoryAdapter {
    private final LdapTemplate template;

    public EmployeeDirectoryAdapter(LdapTemplate template) {
        this.template = template;
    }

    public Optional<DirectoryProfile> findByUid(String uid) {
        if (uid == null || !uid.matches("[A-Za-z0-9._-]{1,64}")) {
            throw new IllegalArgumentException("uid không đúng định dạng");
        }

        // Truy vấn chỉ một OU đã biết, giới hạn kết quả và thời gian search.
        // base nằm tương đối với spring.ldap.base.
        LdapQuery lookup = query()
                .base("ou=people")
                .countLimit(2)
                .timeLimit(3_000)
                .attributes("uid", "cn", "mail")
                .where("uid").is(uid);

        try {
            List<DirectoryProfile> results = template.search(
                    lookup,
                    (AttributesMapper<DirectoryProfile>) attrs ->
                            new DirectoryProfile(
                                    getValue(attrs, "uid"),
                                    getValue(attrs, "cn"),
                                    getValue(attrs, "mail")));

            if (results.isEmpty()) {
                return Optional.empty();
            }
            if (results.size() != 1) {
                throw new IllegalStateException(
                        "LDAP trả nhiều hồ sơ cho cùng uid");
            }
            return Optional.of(results.get(0));
        } catch (CommunicationException | ServiceUnavailableException ex) {
            throw new DirectoryTemporarilyUnavailable(
                    "Không kết nối hoặc đọc được máy chủ thư mục", ex);
        }
    }

    private static String getValue(Attributes attrs, String name)
            throws NamingException {
        Attribute attribute = attrs.get(name);
        return attribute == null ? null : String.valueOf(attribute.get());
    }
}
~~~

**Lý do các lựa chọn trong code:**

- `LdapQueryBuilder.where("uid").is(uid)` tạo filter có escaping phù hợp, tránh ghép chuỗi filter bằng input từ HTTP (LDAP injection).
- `.base("ou=people")` thu hẹp phạm vi trong `spring.ldap.base`; không quét toàn directory.
- `.attributes(...)` giới hạn thông tin trả về, giảm lộ dữ liệu và giảm băng thông.
- `.countLimit(2)` giúp phát hiện dữ liệu trùng khi các quy tắc ánh xạ không đúng. Nếu server ném `SizeLimitExceededException` theo chính sách, adapter phải báo lỗi giới hạn thay vì khẳng định “không tìm thấy”.
- `.timeLimit(3_000)` là giới hạn search, trong khi read timeout 5.000 ms vẫn bảo vệ thao tác chờ phản hồi của provider. Đây là hai tầng giới hạn khác nhau.
- Trường `mail` không có giá trị được ánh xạ thành `null`; validation bắt buộc của dữ liệu nghiệp vụ nên làm trước khi cập nhật DB/đẩy message.

**Cần xác nhận schema thực tế:** Active Directory thường dùng `sAMAccountName` hoặc `userPrincipalName` thay vì `uid`. Ví dụ này minh họa LDAP directory phổ thông có `uid` và `ou=people`. Khi làm việc với AD, đổi filter/attribute/base theo hợp đồng tổ chức và có test với directory thật hoặc môi trường mô phỏng có schema tương đương.

### 6.1. Không nuốt lỗi thành kết quả rỗng

Đây là cách xử lý sai:

~~~java
// Sai: timeout bị biến thành "không có nhân viên".
try {
    return directoryAdapter.findByUid(uid);
} catch (RuntimeException ex) {
    return Optional.empty();
}
~~~

Nếu tác vụ đồng bộ nhận danh sách nhân viên theo chu kỳ, kết quả rỗng giả tạo có thể khiến downstream “đồng bộ xóa” hàng loạt. Với HTTP, nên trả response có trạng thái lỗi phụ thuộc máy chủ thư mục (thường `503 Service Unavailable` hoặc mapping lỗi hạ tầng tương đương). Với broker, nên giữ message chưa hoàn tất và dùng retry có giới hạn/backoff hoặc gửi sang retry topic/DLQ phù hợp. Với job theo lịch, lưu trạng thái `RETRY_PENDING` hoặc `FAILED_TRANSIENT` để kỳ sau tiếp tục.

### 6.2. Retry theo tính chất thao tác

| Tác vụ | Retry an toàn đến đâu? | Điều kiện bổ sung |
| --- | --- | --- |
| Search chỉ đọc theo `uid` | Có thể retry với backoff nhỏ | Giữ tổng deadline; tránh retry storm khi directory đã mất kết nối |
| Bind bằng mật khẩu người dùng | Không retry sai credential | Phân biệt lỗi user với lỗi mạng; tránh kích hoạt account lockout |
| Add/modify/delete LDAP entry | Chỉ retry khi có idempotency/kiểm tra trạng thái | Lỗi timeout không chứng minh server chưa thực thi thay đổi |
| Đồng bộ trạng thái vào SQL/MongoDB | Retry theo khóa nghiệp vụ ổn định | Unique key, upsert/transaction và trạng thái đồng bộ |
| Gửi HTTP hoặc message broker sau lookup | Theo hợp đồng downstream | Idempotency key, outbox/inbox, giới hạn retry và DLQ |

Ví dụ: worker nhận message `syncEmployee(employeeId=E42)`, lookup LDAP thành công rồi cập nhật bảng hồ sơ. Nếu SQL commit đã xong mà consumer chết trước khi ack broker, message được giao lại; worker cần upsert theo `employeeId` và version/modified timestamp phù hợp để không tạo hai người dùng hoặc gửi hai sự kiện giống nhau. LDAP pooling chỉ giúp hiệu quả kết nối, **không** tạo exactly-once ở luồng nhiều hệ thống.

### 6.3. Retry budget, circuit breaker và bulkhead

Một chính sách ban đầu cho tác vụ lookup chỉ đọc:

~~~text
1 request / message
    |
    |-- LDAP attempt #1
    |      lỗi kết nối/tạm không phục vụ?
    |          |
    |          +-- Nếu deadline còn, chờ 100–200 ms + jitter
    |                  |
    |                  +-- LDAP attempt #2
    |
    +-- Thành công: xử lý tiếp, giữ requestId
    +-- Thất bại: trả 503 / schedule retry / ghi incident
~~~

Không dùng vô hạn retry đồng thời ở cả HTTP client, worker và adapter LDAP. Đặt **một retry policy có chủ đích** ở tầng phù hợp, dùng exponential backoff + jitter nếu dự kiến sự cố kéo dài, và giới hạn concurrency để bảo vệ DC. Circuit breaker có thể chuyển sang trạng thái open sau nhiều lỗi kỹ thuật; **không** dùng lỗi “không tìm thấy nhân viên” hoặc “password sai” để tính thành lỗi availability.

Khi breaker đang mở, đường xử lý dữ liệu có thể hoãn bằng hàng đợi hoặc trả lỗi phụ thuộc. Chỉ dùng bản cache cũ cho dashboard hoặc thông tin không nhạy cảm nếu hợp đồng cho phép; **không** dùng cache cũ làm căn cứ xác thực, phân quyền hoặc xóa dữ liệu người dùng khi không thể hỏi directory.

## 7. Kiểm thử các trường hợp hỏng hóc

Kiểm thử cần tách **hợp đồng dữ liệu** khỏi **lỗi vận hành**. Embedded LDAP/UnboundID có thể kiểm chứng mapping và search; tình huống socket chậm, TLS lỗi, pool exhaustion hoặc failover cần môi trường tích hợp có kiểm soát, thường dùng LDAP test container hoặc proxy lỗi mạng.

| Ca thử nghiệm | Cách tạo tình huống | Kết quả cần kiểm tra |
| --- | --- | --- |
| Lookup hợp lệ | Seed một entry trong OU | Đúng `uid/cn/mail`; không lộ attribute khác |
| Không tồn tại | Query `uid` không có, server khỏe | `Optional.empty()`; không có retry |
| Filter injection | `uid` có ký tự đặc biệt hoặc input vượt schema | Input bị từ chối/được escape, không mở rộng phạm vi search |
| Connect timeout | LDAP host không bắt tay TCP hoặc bị chặn | Trả lỗi availability hữu hạn, không giữ thread vô thời hạn |
| Read timeout | TCP đã kết nối nhưng server không trả LDAP response | Exception/incident, không trả “không tìm thấy” |
| DC restart | Server khởi động lại khi pool đang giữ context idle | Context cũ bị loại nhờ validation/non-transient handling; connection mới có thể được tạo |
| Pool exhausted | Mở nhiều truy vấn đồng thời vượt `maxTotal` | Borrow hết hạn theo `maxWaitMillis`, không queue vô tận |
| Service bind sai password | Dùng secret sai trong test | Báo lỗi cấu hình/xác thực; không retry như lỗi tạm thời |
| User bind sai password | User test cố ý gửi credential sai | Trả kết quả xác thực không hợp lệ, không dùng pool service account chung |
| Referrals | Truy vấn qua naming context có referral | Hành vi đúng `ignore/follow/throw`; không ngầm coi partial result là đầy đủ |
| Search quá rộng | Query vượt size/time limit | Lỗi được phân loại, không áp dụng dữ liệu thiếu cho đồng bộ |
| TLS certificate hết hạn | Dùng test CA/cert hết hạn | Không bắt kết nối nếu không xác thực được cert; không tắt TLS validation |
| Failover giữa hai URL | Dừng endpoint đang phục vụ trong test | Có thể kết nối lại endpoint khỏe; đánh giá downtime và dữ liệu không nhất quán |
| Message redelivery | Consumer xử lý xong DB nhưng chưa ack broker | Xử lý lại cùng business key không nhân đôi tác dụng phụ |

### 7.1. Test riêng phân loại lỗi ở tầng adapter

Với unit test, mock `LdapTemplate.search(...)` để lần lượt trả kết quả rỗng, một kết quả, hoặc ném `CommunicationException` và `AuthenticationException` theo đúng API. Khẳng định:

- Chỉ đường search hoàn tất và không match mới trả `Optional.empty()`.
- `CommunicationException` được chuyển thành `DirectoryTemporarilyUnavailable`, bảo toàn cause.
- `AuthenticationException` của service account không bị biến thành “user không tồn tại”.
- Input bất thường không được đưa vào filter ghép chuỗi tùy ý.

Đây là kiểm thử chính sách, **không thay thế** integration test với LDAP thật/proxy. Không cần gọi LDAP production để thử timeout hoặc cố tình reset connection.

### 7.2. Test pool có ý nghĩa

Để test pool exhaustion, có thể tạo tối đa `maxTotal` thao tác được giữ mở trong test service, phát thêm một thao tác và đo thời gian thất bại gần `maxWaitMillis`. Sau khi trả context, assert số active trở lại và có thể borrow lại. Kiểm tra trực tiếp `getNumActive()`, `getNumIdle()`, `getNumWaiters()` của `PooledContextSource` hoặc thông qua JMX/Micrometer nếu đã tích hợp. Nhớ đóng context trong `finally` hoặc dùng API `LdapTemplate` để framework tự quản lý việc trả context; nếu quên đóng, pool sẽ cạn theo thời gian.

Với test failover, cần chứng minh **mức độ sẵn sàng quan sát được**, không giả định “có hai URL là không có downtime”. Đo P50/P95/P99 latency, số timeout, số retry, thời gian phục hồi và quan sát thay đổi kết quả giữa các domain controller đang replication.

## 8. Logging, metrics, readiness và xử lý sự cố

### 8.1. Những metric cần có

Đặt tên metric theo quy ước Micrometer của ứng dụng, ví dụ:

| Metric đề xuất | Nội dung cần đo | Ý nghĩa vận hành |
| --- | --- | --- |
| `ldap_operation_duration_seconds{operation,result}` | Thời gian search/bind/modify, phân tách kết quả | Nhận biết P95/P99 tăng hoặc server chậm |
| `ldap_operations_total{operation,result}` | Tổng số thao tác thành công, không match, timeout, lỗi bind | Phân biệt lỗi dữ liệu với sự cố hạ tầng |
| `ldap_pool_active` / `ldap_pool_idle` | Context đang mượn và sẵn sàng | Chẩn đoán pool cạn hoặc cấp quá nhiều connection |
| `ldap_pool_waiters` / `ldap_pool_borrow_timeout_total` | Số thread đợi và số lần mượn pool hết thời gian | Phát hiện backpressure, giới hạn pool không phù hợp |
| `ldap_retry_total{cause}` | Số lần retry theo nhóm nguyên nhân | Phát hiện retry storm, lỗi mạng kéo dài |
| `ldap_dependency_unavailable_total` | Số request/job không thể truy vấn directory | Theo dõi SLO của hệ thống tích hợp |
| `directory_sync_backlog` / `directory_sync_oldest_age_seconds` | Số message chưa xử lý và độ trễ tích lũy | Đánh giá tác động kinh doanh khi LDAP gián đoạn |

Không dùng `uid`, email, raw DN, địa chỉ IP người dùng hoặc request ID làm **metric label**, tránh cardinality lớn và rủi ro lộ thông tin. Các ID có thể được lưu theo chính sách bảo mật trong log/tracing có kiểm soát truy cập và retention; không ghi bind password, token, hash nhạy cảm hoặc toàn bộ LDAP entry.

Nếu có tracing từ HTTP client tới message broker, tạo span `ldap.search` với tên thao tác, endpoint đã được chuẩn hóa, timeout và trạng thái kết quả. Correlation ID của một lần đồng bộ giúp truy vết “LDAP trả thành công → ghi DB → gửi event” hoặc nơi thông điệp bị trì hoãn.

### 8.2. Readiness khác liveness

Ứng dụng Spring Boot có thể vẫn chạy khỏe trong khi LDAP đang mất kết nối. **Không** gắn mọi lỗi LDAP vào liveness khiến Kubernetes liên tục restart pod, đổ thêm tải kết nối mới lên directory server. Readiness nên phản ánh khả năng ứng dụng phục vụ *tác vụ bắt buộc cần LDAP* theo hợp đồng sản phẩm; nếu API có nhiều chức năng độc lập LDAP, health policy cần tinh tế hơn một công tắc all-or-nothing.

Một health check chỉ thử TCP/SSL có thể không phát hiện bind lỗi hoặc không có quyền search. Nhưng chạy một truy vấn LDAP nặng ở mỗi health probe sẽ gây tải và tạo tác động dây chuyền khi server yếu. Dùng lightweight probe, cache kết quả ngắn hạn hoặc phân nhóm readiness cho dependency theo chính sách SRE của hệ thống.

### 8.3. Quy trình ứng cứu khi lỗi LDAP tăng

1. **Xác định loại lỗi:** timeout mạng, authentication bind, TLS trust, query limit hay pool exhaustion? Kiểm tra cause chain và log/metric của cùng request.
2. **Khoanh vùng:** sự cố xảy ra với mọi pod hay riêng một host? Một DC hay cả directory domain? Có thay đổi secret, certificate, firewall, DNS, schema hoặc ACL gần đây không?
3. **Kiểm tra pool:** active/idle/waiter, maxWait, số context bị invalidate; pool đông vì truy vấn chậm hay vì thiếu trả context?
4. **Kiểm tra tác động:** backlog message, API 503, đồng bộ trễ, dữ liệu cache; đảm bảo các job không diễn giải lỗi thành “không tìm thấy nhân viên”.
5. **Giảm tải có kiểm soát:** chặn retry storm, mở breaker khi thích hợp, giới hạn số request đồng thời; chuyển message tạm thời qua retry queue nếu có.
6. **Khôi phục:** khi directory khỏe, cho breaker phục hồi, redrive message theo idempotency key; xác minh không sinh duplicate và kiểm tra lag/replication giữa các endpoint.
7. **Hậu kiểm:** điều chỉnh timeout, pool size, retention, cảnh báo và quy trình rotation; viết lại test sự cố đã gặp.

### Những cấu hình dễ dẫn đến kết quả sai

**Bẫy 1 – Tăng read timeout để “hết lỗi”:** nếu mục tiêu HTTP chỉ 3 giây, tăng LDAP read timeout lên 30 giây làm request chặn thread lâu hơn. Cần xác định nguyên nhân server chậm hoặc query quá rộng, không chỉ đẩy timeout lên cao.

**Bẫy 2 – Pool lớn bằng số request đồng thời cực đại:** nếu mỗi pod giữ hàng trăm context và deployment tăng replicas, tổng connections có thể vượt quota LDAP. Bắt đầu từ concurrency thực tế và đo pool wait/latency.

**Bẫy 3 – Cache kết quả “không tồn tại” khi server lỗi:** timeout khác với 0 bản ghi. Không được ghi negative cache, xóa nhân viên hoặc thu hồi quyền chỉ vì LDAP unavailable.

**Bẫy 4 – Nuốt partial/size limit:** trong một số phiên bản Boot, `spring.ldap.template.ignore-size-limit-exceeded-exception` có thể mặc định là `true`, còn `ignore-partial-result-exception` thường là `false`. Nếu logic đồng bộ cần danh sách đầy đủ, hãy đặt các chế độ này **tường minh** và kiểm thử. Ví dụ cấu hình nghiêm ngặt:

~~~yaml
spring:
  ldap:
    template:
      ignore-size-limit-exceeded-exception: false
      ignore-partial-result-exception: false
      ignore-name-not-found-exception: false
~~~

Không có một lựa chọn đúng cho mọi hệ thống: tra cứu một nhân viên và tìm toàn bộ thành viên nhóm có yêu cầu khác nhau. Khi sử dụng paged results hoặc ranged retrieval của AD, cần kết hợp chính sách paging/range với khả năng phát hiện dữ liệu chưa đủ.

**Bẫy 5 – Retry mọi exception như nhau:** service account sai password, TLS certificate không hợp lệ hoặc filter sai sẽ không tự hết nhờ retry. Trái lại retry dồn dập có thể gây khóa tài khoản hoặc làm DC quá tải.

**Bẫy 6 – Bật `follow` referral không kiểm soát:** referral có thể chuyển sang domain khác, thay đổi số endpoint, latency, chính sách TLS và tài khoản bind. Phải xác định những domain nào được phép truy vấn.

## 9. Bảng quyết định triển khai

| Yêu cầu nghiệp vụ | Cấu hình/hành vi đề xuất |
| --- | --- |
| Tìm một nhân viên cho API synchronous | Connect/read timeout hữu hạn; search base hẹp; `countLimit` thấp; mapping not-found riêng |
| Đồng bộ hàng chục nghìn user theo lịch | Paging, incremental sync, giới hạn tải; không áp dụng partial data như dữ liệu đầy đủ |
| Tải lookup cao qua service account cố định | `PooledContextSource` có validation, giới hạn pool và borrow timeout; giám sát waiter |
| Xác thực password cá nhân | Context/bind theo người dùng với chính sách bảo mật; tránh pool context chung theo dynamic principal |
| Nhiều domain controller | Nhiều URL/DNS phù hợp, validation, failover thử nghiệm, cân nhắc replication lag |
| Server lỗi tạm thời | Retry hữu hạn với backoff/jitter và budget; circuit breaker; message redrive/idempotency |
| Sai password/certificate/ACL | Chẩn đoán cấu hình, alert; không retry vô hạn |
| HTTP hoặc broker phụ thuộc LDAP | Không nhầm unavailable với not-found; status/requeue/dead-letter phù hợp |
| Xóa hoặc cập nhật dữ liệu downstream | Chỉ quyết định sau kết quả LDAP đầy đủ và đáng tin cậy; dùng transaction/idempotency |

### Câu hỏi tự kiểm tra

1. Connect timeout 2 giây và read timeout 5 giây có bảo đảm toàn request hoàn tất dưới 7 giây không? Vì sao?
2. Tại sao LDAP pool có 20 connection vẫn có thể khiến tất cả request bị giữ khi DC bị treo?
3. Vì sao một `CommunicationException` không được biến thành kết quả “user không tồn tại”?
4. Bật `testOnBorrow=true` phát hiện được những lỗi nào, và vẫn không ngăn được lỗi gì giữa lúc query đang chạy?
5. Sự khác nhau giữa service account bind và bind kiểm tra mật khẩu người dùng là gì?
6. Nếu search trả `PartialResultException` hoặc vượt size limit, điều gì có thể xảy ra nếu đồng bộ coi kết quả như danh sách đầy đủ?
7. Vì sao retry LDAP modify sau timeout phải đi kèm kiểm tra/idempotency, dù đó chỉ là một thao tác LDAP?

Khả năng chịu lỗi của ứng dụng LDAP không đến từ riêng một con số timeout hay kích thước pool. Trong một hệ thống **Spring Boot Integration** kết nối API, database, cache và broker, cần kết hợp **truy vấn đúng hợp đồng**, **giới hạn thời gian ở đúng tầng**, **pool có kiểm soát**, **phân loại exception**, **retry/idempotency có giới hạn** và **quan sát từ đầu đến cuối**.

## Tài liệu tham khảo

- [Spring Boot Reference — LDAP và Data Access](https://docs.spring.io/spring-boot/reference/data/nosql.html#data.nosql.ldap)
- [Spring Boot 3.5 — Common Application Properties (LDAP)](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/)
- [Spring LDAP — Configuration, Native Java LDAP Pooling](https://docs.spring.io/spring-ldap/reference/configuration.html)
- [Spring LDAP — Pooling Support](https://docs.spring.io/spring-ldap/reference/pooling.html)
- [Spring LDAP Javadoc — PooledContextSource](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/pool2/factory/PooledContextSource.html)
- [Spring LDAP Javadoc — PoolConfig](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/pool2/factory/PoolConfig.html)
- [Spring LDAP — Advanced LDAP Queries](https://docs.spring.io/spring-ldap/reference/query-builder-advanced.html)
- [Oracle JNDI LDAP — Connect and Read Timeout Properties](https://docs.oracle.com/en/java/javase/26/docs/api/java.naming/module-summary.html)




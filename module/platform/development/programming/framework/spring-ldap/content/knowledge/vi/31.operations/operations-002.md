# Timeout connect, read và response trong Spring LDAP

## 1. Bối cảnh vận hành: tại sao một truy vấn LDAP có thể “treo”?

Ứng dụng dùng Spring LDAP thường cần truy vấn thư mục để đăng nhập, tra cứu nhân viên, xác định nhóm hoặc cập nhật entry. Khi LDAP server chậm hoặc mạng gián đoạn, một thao tác LDAP có thể chiếm thread xử lý HTTP lâu hơn ngân sách thời gian của API. Một cấu hình chỉ định timeout không đúng tầng dễ dẫn tới tình huống ngược đời: dịch vụ đã trả lỗi cho người dùng nhưng thread vẫn tiếp tục đợi LDAP, hoặc TCP kết nối được rất nhanh mà tìm kiếm vẫn kéo dài.

Bài học thuộc phần **Vận hành** của **SPRING_LDAP** tập trung vào cách đặt và xác minh ba khái niệm:

- **Connect timeout:** ngân sách để thiết lập một kết nối TCP mới tới LDAP server.
- **Read timeout:** khoảng chờ dữ liệu trả về từ LDAP trên socket; trong JNDI của Java đây là cấu hình thường dùng để chặn việc đợi phản hồi vô thời hạn.
- **Response timeout / operation deadline:** thời hạn mà ứng dụng hoặc tác vụ nghiệp vụ chấp nhận chờ **toàn bộ kết quả**. Trong Spring LDAP sử dụng JNDI, đây không phải một thuộc tính JNDI chung, độc lập, có tên `response.timeout`.

Mục tiêu là biết cấu hình `ContextSource`/`LdapTemplate`, đặt giới hạn cho tìm kiếm, kiểm thử trên LDAPS/StartTLS, nhận diện tác động của pooling, xử lý lỗi và đo độ trễ an toàn. Ví dụ dùng Spring Boot 3.x, Java 17+, Spring LDAP và mô hình có server tại `ldaps://ldap.example.org:636`.

## 2. Phân biệt đúng phạm vi ba loại timeout

| Khái niệm | Bắt đầu tính khi nào? | Thường cấu hình ở đâu? | Điều gì *không* được bảo đảm? |
| --- | --- | --- | --- |
| Connect timeout | Khi client cố mở kết nối TCP mới | JNDI `com.sun.jndi.ldap.connect.timeout`, tính bằng mili giây | Không giới hạn tổng thời gian bind, search, TLS handshake hay nhiều lần retry |
| Read timeout | Khi JNDI chờ dữ liệu/phản hồi trên kết nối LDAP | JNDI `com.sun.jndi.ldap.read.timeout`, tính bằng mili giây | Không phải tổng deadline của một search nhiều phản hồi hoặc một chuỗi thao tác |
| Search time limit | Khi thực thi một truy vấn search | `SearchControls.setTimeLimit(...)` hoặc giới hạn từ LDAP server | Không bao trùm DNS, TCP, bind, mọi xử lý ứng dụng |
| Response deadline | Khi một request hoặc nghiệp vụ bắt đầu | Ở tầng service/API, job, gateway, async boundary hoặc công cụ giới hạn thời gian | Không tự hủy I/O LDAP đang chặn nếu tầng thấp hơn không hỗ trợ hủy |
| Pool borrow timeout | Khi đợi mượn kết nối từ pool | Tùy thư viện pooling và cấu hình pool | Không được điều khiển chỉ bằng JNDI connect/read timeout |

Trong JNDI LDAP provider phổ biến của JDK, hai property chính là:

~~~properties
com.sun.jndi.ldap.connect.timeout=1000
com.sun.jndi.ldap.read.timeout=2500
~~~

Các giá trị trên là **mili giây**. Chúng áp dụng cho những hoạt động JNDI phù hợp với cơ chế của provider; không nên xem là đồng hồ đếm ngược duy nhất bao bọc từ lúc vào API cho đến lúc trả HTTP response. Nếu không cấu hình timeout, các giai đoạn chờ có thể kéo dài rất lâu theo cấu hình hệ điều hành, JDK, LDAP server và các tầng mạng.

### 2.1. Nhìn một request theo trục thời gian

~~~mermaid
flowchart LR
    A["HTTP request"] --> B["Chọn endpoint / DNS"]
    B --> C["TCP connect"]
    C --> D["TLS + LDAP bind"]
    D --> E["LDAP search"]
    E --> F["Nhận các phản hồi"]
    F --> G["Mapping dữ liệu / HTTP response"]
~~~

Mỗi mũi tên là một giai đoạn có thể thất bại. Chỉ vì bước **TCP connect** hoàn tất trong 20 ms không có nghĩa bước **LDAP search** sẽ trả kết quả trước 2 giây. Nếu kết quả search được gửi thành nhiều đợt, mỗi lần socket có dữ liệu lại có thể tiếp tục tiến trình; `read.timeout` không mặc nhiên buộc tổng thời gian từ A đến G phải nhỏ hơn giá trị của nó.

Ví dụ:

1. TCP connect mất 100 ms.
2. Bind/TLS mất 500 ms.
3. Server gửi từng phần dữ liệu sau mỗi 1.500 ms và client đặt read timeout 2.000 ms.
4. Request vẫn có thể mất 6 giây hoặc hơn vì không có một khoảng chờ đọc riêng lẻ nào vượt 2.000 ms.

Do đó, điều kiện “read timeout = 2 giây” không tương đương “mọi API LDAP hoàn tất dưới 2 giây”.

## 3. Cấu hình connect và read timeout qua ContextSource

Spring LDAP cung cấp `ContextSource` để tạo/ngắt context LDAP và `LdapTemplate` để thực hiện các phép tìm kiếm hoặc chỉnh sửa entry. Với `LdapContextSource` dùng JNDI, có thể truyền hai cấu hình timeout trong môi trường JNDI khi khởi tạo bean.

### 3.1. Cấu hình ứng dụng

~~~yaml
# application.yml
app:
  ldap:
    url: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    user-dn: uid=svc-directory-reader,ou=service,dc=example,dc=org
    password: ${LDAP_SERVICE_PASSWORD}
    connect-timeout-ms: 1000
    read-timeout-ms: 2500
~~~

Đặt mật khẩu trong secret manager hoặc biến môi trường; không commit mật khẩu thực. LDAPS cần chứng chỉ server hợp lệ và một truststore tin cậy. Ví dụ này không dùng timeout âm hay không giới hạn làm giá trị mặc định.

### 3.2. Cấu hình Spring LDAP

~~~java
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class DirectoryLdapConfiguration {

    @Bean
    public LdapContextSource ldapContextSource(
            @Value("${app.ldap.url}") String url,
            @Value("${app.ldap.base}") String base,
            @Value("${app.ldap.user-dn}") String userDn,
            @Value("${app.ldap.password}") String password,
            @Value("${app.ldap.connect-timeout-ms}") int connectMs,
            @Value("${app.ldap.read-timeout-ms}") int readMs) {

        if (connectMs <= 0 || readMs <= 0) {
            throw new IllegalArgumentException("LDAP timeouts must be positive");
        }

        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase(base);
        source.setUserDn(userDn);
        source.setPassword(password);
        source.setPooled(false);

        source.setBaseEnvironmentProperties(Map.of(
                "com.sun.jndi.ldap.connect.timeout",
                Integer.toString(connectMs),
                "com.sun.jndi.ldap.read.timeout",
                Integer.toString(readMs)));

        return source;
    }

    @Bean
    public LdapTemplate ldapTemplate(LdapContextSource ldapContextSource) {
        return new LdapTemplate(ldapContextSource);
    }
}
~~~

**Cách đoạn mã hoạt động:**

- `setBaseEnvironmentProperties` bổ sung property cho môi trường JNDI khi Spring tạo LDAP context. Đặt chúng trên đúng `ContextSource` mà ứng dụng thực sự sử dụng.
- `connect.timeout` áp dụng khi provider cần tạo kết nối mới; `read.timeout` bảo vệ các lần chờ phản hồi LDAP, bao gồm phản hồi cho nhiều thao tác như bind/search.
- `setPooled(false)` giúp ví dụ dễ quan sát kết nối mới. Trong ứng dụng sử dụng pooling, cấu hình sẽ cần được kiểm tra thêm tại tầng pool.
- `LdapContextSource` là bean do Spring quản lý nên lifecycle khởi tạo được container thực hiện. Nếu tự tạo đối tượng bên ngoài Spring, cần bảo đảm gọi đúng bước khởi tạo theo API của `ContextSource`.
- Khi đã khai báo `ContextSource` thủ công, kiểm tra tương tác với Spring Boot LDAP auto-configuration và các injection point nếu dự án có nhiều bean `ContextSource`.

**Lưu ý về cấu hình TLS:** timeout kết nối TCP không thay thế xác minh TLS, và không phải bảo đảm tuyệt đối cho toàn bộ quá trình TLS handshake. Cần quan sát lỗi chứng chỉ, hostname và truststore độc lập với lỗi chờ connect/read. Với StartTLS, cần thiết lập chế độ yêu cầu TLS trước khi gửi thông tin bind; không cho phép cơ chế rơi về bind qua kênh không mã hóa.

## 4. Timeout trong phép tìm kiếm: SearchControls, filter và response

Ngay cả khi đã đặt read timeout, truy vấn search không có giới hạn có thể trả về hàng nghìn entry, đi qua nhiều đợt phản hồi và tốn CPU/heap khi ánh xạ dữ liệu. `SearchControls` cho phép chỉ định scope, tập thuộc tính trả về, giới hạn số entry và time limit riêng của search.

~~~java
import java.util.List;
import javax.naming.directory.SearchControls;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.filter.EqualsFilter;

public class DirectoryLookupService {
    private final LdapTemplate ldapTemplate;

    public DirectoryLookupService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findUid(String userProvidedUid) {
        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
        controls.setReturningAttributes(new String[] {"uid"});
        controls.setCountLimit(10);
        controls.setTimeLimit(1500); // mili giây; giới hạn cho search

        String filter = new EqualsFilter("uid", userProvidedUid).encode();

        return ldapTemplate.search(
                "ou=people",
                filter,
                controls,
                (AttributesMapper<String>) attrs ->
                        (String) attrs.get("uid").get());
    }
}
~~~

Các quyết định quan trọng:

- **Giới hạn base DN**: chỉ tìm trong `ou=people`, không quét toàn bộ cây.
- **Giới hạn dữ liệu**: chỉ lấy `uid` và tối đa 10 kết quả; số lượng thực tế phải được chọn theo nghiệp vụ.
- **Lọc an toàn**: `EqualsFilter` encode giá trị đưa vào filter, tránh ghép chuỗi filter trực tiếp từ đầu vào.
- **Giới hạn search**: `setTimeLimit(1500)` cung cấp giới hạn thời gian tìm kiếm theo cách JNDI/provider và LDAP server thực thi. Hành vi khi hết hạn có thể là exception hoặc kết quả không đầy đủ; xử lý theo hợp đồng nghiệp vụ.
- **Kiểm tra thuộc tính**: mapper trên giả định entry trả về luôn có `uid`. Trong hệ thống thực, cần xử lý trường hợp thuộc tính vắng mặt nếu schema/ACL cho phép, tránh `NullPointerException` che khuất nguyên nhân.

### 4.1. Vì sao SearchControls.timeLimit chưa phải response deadline?

Giới hạn search và timeout đọc phản hồi phục vụ các mục đích khác nhau. Search time limit nhắm vào phần **thực thi tìm kiếm**; read timeout chặn chờ dữ liệu trên kết nối. Một API có thể còn nhiều bước khác: lấy token, đọc nhóm, lookup từng DN, gọi dịch vụ phụ và ánh xạ kết quả. Nếu yêu cầu có ba lần gọi LDAP nối tiếp, mỗi lần đều được phép dùng gần hết read timeout thì tổng thời gian vượt ngân sách API là điều hoàn toàn có thể xảy ra.

LDAP server cũng có thể áp dụng giới hạn phía server cho `timeLimit`/`sizeLimit`, thường theo cấu hình và quyền của bind DN. Server-side limit nên được coi là hàng rào bổ sung, không thay thế giới hạn do client và tầng nghiệp vụ đặt ra.

### 4.2. Những loại response khác nhau

Trong LDAP, một search có thể gồm nhiều bản tin `SearchResultEntry`, `SearchResultReference` và kết thúc bằng `SearchResultDone`. Một số thao tác khác như bind hoặc modify nhận phản hồi kết thúc đơn lẻ. Vì thế, “response nhanh” có thể mang nghĩa rất khác nhau:

| Chỉ số | Đang đo | Phù hợp với |
| --- | --- | --- |
| First response latency | Thời gian tới phản hồi LDAP đầu tiên | Phân tích lúc chờ server bắt đầu trả dữ liệu |
| Search completion latency | Thời gian tới phản hồi kết thúc và kết quả search hoàn chỉnh | Search, phân trang, thống kê |
| End-to-end LDAP operation latency | Từ trước khi mượn kết nối đến khi nhận và xử lý xong kết quả | Health check, service method |
| HTTP/API response latency | Từ khi HTTP request vào tới khi ứng dụng gửi kết quả cho client | SLO người dùng và gateway |

Nếu đội ngũ cần “response timeout” cho nghiệp vụ, trước tiên phải nói rõ **response nào** và **điểm bắt đầu/kết thúc** của phép đo.

## 5. Đặt ngân sách thời gian theo SLA của ứng dụng

Giả sử API cần trả lời trong khoảng **3 giây**. Một phương án ban đầu để đo và tinh chỉnh:

| Tầng | Giá trị ví dụ | Ý nghĩa |
| --- | ---: | --- |
| Gateway / HTTP request budget | 3000 ms | Giới hạn phía client hoặc gateway |
| Deadline nội bộ của API | 2700 ms | Chừa thời gian cho serialization và truyền mạng |
| LDAP connect timeout | 600 ms | Chặn TCP connect quá chậm |
| LDAP read timeout | 1600 ms | Chặn một lần chờ phản hồi LDAP quá lâu |
| LDAP search time limit | 1200 ms | Hạn chế một thao tác search |
| Pool borrow timeout (nếu có) | 300 ms | Hạn chế thời gian chờ kết nối sẵn có |

**Đây là ví dụ ngân sách, không phải công thức khẳng định tổng thời gian sẽ bằng hoặc nhỏ hơn 2.700 ms.** Connect/read timeout không có cùng điểm bắt đầu, có thể lặp theo từng kết nối/đọc và không bao trùm mọi xử lý; giá trị pool borrow còn phụ thuộc thư viện. Deadline ở tầng nghiệp vụ chỉ hữu ích khi các thao tác thấp hơn cũng tuân thủ timeout hoặc cơ chế hủy phù hợp.

Nếu mỗi HTTP request có thể truy vấn LDAP nhiều lần, cần quản lý **thời gian còn lại** chứ không cấp nguyên ngân sách cho từng lần gọi:

~~~text
remaining = deadline - now
if remaining <= 0: stop before sending a new LDAP request
for each LDAP call:
    choose timeouts within remaining budget
    execute safely
    recompute remaining after call
~~~

Đây là **giả mã**, không phải API có sẵn của `LdapTemplate`. Một cơ chế time limiter chạy ở thread khác có thể trả timeout cho người gọi mà thread LDAP bên dưới vẫn đang chờ socket. Vì vậy không xem `CompletableFuture.orTimeout`, `Future.get(timeout)` hay timeout HTTP là cách chắc chắn để cắt I/O JNDI. Muốn kiểm soát tổng độ trễ, cần phối hợp timeout ở LDAP provider, pool, search, tầng ứng dụng và số lần retry.

**Nguyên tắc retry:** chỉ retry khi lỗi có khả năng tạm thời và nghiệp vụ cho phép. Search đọc có thể được thử lại trong giới hạn ngân sách; modify/add/delete cần xem xét tính idempotent và khả năng server đã thực thi thành công trước khi client gặp timeout. Không tự động gửi lại một phép ghi nếu không có chiến lược xác nhận trạng thái và chống ghi trùng.

## 6. Timeout và những yếu tố dễ gây bất ngờ

### 6.1. TLS và DNS

- DNS lookup có thể chịu timeout riêng của hệ điều hành hoặc trình phân giải tên; không suy ra rằng `connect.timeout` chắc chắn giới hạn toàn bộ bước DNS.
- Bắt tay TLS, xác minh chứng chỉ và phản hồi bind có thể gây độ trễ sau lúc TCP đã mở. Khi kiểm tra, phân biệt thời gian mở socket với thời gian nhận kết quả bind.
- Với LDAPS, xác minh CA chain và hostname. Với StartTLS, thực hiện upgrade kênh an toàn trước khi gửi credential. Không “sửa” timeout bằng cách bỏ qua xác minh chứng chỉ.
- Có nhiều endpoint hoặc referral thì mỗi kết nối tiếp theo có thể tiêu tốn thời gian riêng. Giới hạn referral và chỉ theo referral tới máy chủ đáng tin cậy nếu hệ thống cần chức năng đó.

### 6.2. Connection pooling

Khi dùng pool, một lần gọi có thể **không tạo TCP connection mới** mà mượn connection đang tồn tại:

1. Lấy connection từ pool — có thể phải chờ pool borrow timeout.
2. Nếu kết nối bị firewall hoặc server đóng trong lúc nhàn rỗi, thao tác đầu tiên có thể lỗi ở pha đọc.
3. Pool cần chính sách kiểm tra kết nối, loại bỏ connection hỏng, giới hạn thời gian idle và số connection phù hợp.
4. Các giá trị timeout của connection đang mở không được bảo đảm thay đổi chỉ bằng việc cập nhật cấu hình mới; cần xác minh vòng đời context và kế hoạch xoay vòng pool.

`LdapContextSource.setPooled(true)` liên quan JNDI connection pooling, còn `PoolingContextSource` (nếu dự án sử dụng) có cấu hình mượn/trả và validation riêng. Không nhầm `read.timeout` với pool borrow timeout. Nếu dùng StartTLS, kiểm tra giới hạn của cơ chế pool tương ứng; không giả định mọi cách pooling an toàn hoặc tương thích với StartTLS.

### 6.3. Tìm kiếm phân trang, tham chiếu và nhiều kết quả

- **Paged search** gồm nhiều request/response; timeout một trang không giới hạn toàn bộ phiên.
- **Referrals** có thể thêm kết nối tới server khác, mỗi nơi có độ trễ và chính sách TLS/ACL khác.
- **Dữ liệu lớn** làm chậm chuyển đổi entry sang object và truyền kết quả. Không gán toàn bộ thời gian này cho LDAP server.
- **Search scope rộng** hoặc filter thiếu chỉ mục có thể tạo server-side delay ngay cả khi mạng tốt.

## 7. Quan sát và chẩn đoán timeout

Khi gọi LDAP, ghi nhận thời gian bằng đồng hồ đơn điệu như `System.nanoTime()`, không dùng hiệu giữa hai mốc wall-clock cho latency. Thống kê nên bao gồm số lượng, tỉ lệ lỗi và p50/p95/p99 theo loại thao tác. Không log password, LDAP attributes nhạy cảm hay DN đầy đủ nếu không cần cho điều tra.

~~~java
long started = System.nanoTime();
String outcome = "success";
try {
    return directoryLookupService.findUid(userProvidedUid);
} catch (RuntimeException ex) {
    outcome = "error:" + ex.getClass().getSimpleName();
    throw ex;
} finally {
    long elapsedMs =
            java.util.concurrent.TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - started);
    // Gửi metric có tag operation, outcome, elapsedMs.
    // Không dùng giá trị uid hay full DN làm metric tag.
}
~~~

Đoạn trên là ví dụ chèn quanh lời gọi trong một method **có return type tương ứng**; biến `outcome` cần được sử dụng bởi hệ thống metric/log thực tế. Với service đang ở trong thread pool, đo cả **thời gian xếp hàng trước khi chạy**, vì thời gian chờ tài nguyên không xuất hiện trong latency của riêng LDAP method.

| Biểu hiện | Nhóm nguyên nhân có thể | Kiểm tra tiếp theo |
| --- | --- | --- |
| Lỗi ngay lúc mở connection | DNS, endpoint sai, firewall, LDAP server không lắng nghe | Kiểm tra host/cổng, log TCP, độ trễ connect |
| Kết nối được nhưng bind không có phản hồi | Server quá tải, TLS/bind handshake, đường truyền mất gói | Kiểm tra TLS, bind result, `read.timeout` và server log |
| Search chạy lâu rồi timeout | Filter không dùng index, search scope rộng, server quá tải | Xem base DN, scope, filter, server search log |
| Thỉnh thoảng timeout sau thời gian idle | Connection trong pool đã chết, NAT/firewall idle timeout | Kiểm tra validation, eviction, keepalive và cấu hình pool |
| Nhiều thao tác ngắn nhưng HTTP API chậm | Chuỗi LDAP call, pool wait, retry, JSON mapping | Trace toàn bộ request và số lần gọi LDAP |
| Client nhận timeout, server vẫn đang xử lý | Deadline của gateway ngắn hơn tác vụ LDAP | Đối chiếu deadline, search time limit và việc hủy truy vấn |
| Chỉ xảy ra sau đổi CA/certificate | TLS truststore/hostname/chain sai | Xác minh chứng chỉ và lỗi TLS, không tự tăng timeout |

Một số lỗi có thể xuất hiện dưới dạng `javax.naming.CommunicationException`, `javax.naming.NamingException` hoặc exception tương ứng được Spring LDAP chuyển đổi thành kiểu của Spring. Tìm kiếm vượt giới hạn có thể gây lỗi time limit, limit từ server hoặc partial result. **Không phân loại chỉ bằng tên exception**: xem nguyên nhân gốc, thời điểm lỗi, LDAP result code nếu có và các metric của server.

### 7.1. Quan hệ với health/readiness

Health check nên dùng truy vấn nhỏ tới entry ổn định, timeout hữu hạn và tần suất đủ thấp. Không đặt phép quét cây lớn trong readiness probe. Khi LDAP là phụ thuộc bắt buộc cho request cốt lõi, readiness có thể phản ánh tình trạng LDAP; nhưng liveness không nên thất bại chỉ vì LDAP tạm ngưng, để tránh restart loop. Đặt lịch cảnh báo dựa trên **tỉ lệ lỗi và độ trễ duy trì** thay vì một mẫu chậm đơn lẻ.

## 8. Thực hành với LDAP test environment

Trước khi chạy thử, tạo LDAP server thử nghiệm có TLS hợp lệ, tài khoản test chỉ đọc, base DN và entry giả. Sử dụng dữ liệu giả và thực hiện phép tìm kiếm an toàn; không cố làm chậm hoặc ngắt production directory.

### 8.1. Xác minh đường đi bình thường

~~~bash
# Bind qua LDAPS, hỏi mật khẩu tương tác để tránh đưa secret vào shell history.
ldapwhoami -x -H ldaps://ldap.example.org:636 \
  -D "uid=svc-directory-reader,ou=service,dc=example,dc=org" -W

# Search nhỏ, scope base, chỉ lấy thuộc tính cần thiết.
ldapsearch -LLL -x -H ldaps://ldap.example.org:636 \
  -D "uid=svc-directory-reader,ou=service,dc=example,dc=org" -W \
  -b "ou=health,dc=example,dc=org" -s base \
  "(objectClass=*)" ou
~~~

Những lệnh trên độc lập với timeout của ứng dụng Java. Chúng hữu ích để xác minh DNS/TLS/bind/ACL nhưng không chứng minh cấu hình `ContextSource` đã được áp dụng. Cần chạy ứng dụng để đo timeout JNDI.

### 8.2. Ma trận kiểm thử

| Ca | Tình huống | Kỳ vọng quan sát |
| --- | --- | --- |
| T1 | LDAP test hoạt động, mạng bình thường | Bind/search thành công; số đo nằm trong mức bình thường |
| T2 | TCP không thể thiết lập tới endpoint test | Thất bại có giới hạn ở tầng connect; thời gian thực tế phụ thuộc mạng |
| T3 | TCP kết nối được nhưng server test trì hoãn phản hồi LDAP | Chờ phản hồi gặp read timeout; ghi nhận thời gian và loại lỗi |
| T4 | Truy vấn test cố ý chậm do dataset/index test | Search time limit hoặc read timeout, tùy cách server phản hồi |
| T5 | Pool test trả về connection idle đã đóng | Lỗi ở thao tác mượn/đọc, sau đó pool loại bỏ connection hỏng |
| T6 | Một API gọi LDAP nhiều lần nối tiếp | HTTP latency có thể vượt một read timeout; đo end-to-end |
| T7 | Gateway deadline ngắn hơn LDAP operation | Client nhận timeout trong khi tác vụ dưới có thể còn chạy |
| T8 | Cấu hình TLS truststore sai trên môi trường test | Lỗi chứng chỉ/SSL riêng; tăng timeout không làm kết nối hợp lệ |

Có thể dùng proxy mạng trong lab để mô phỏng trễ hoặc ngắt kết nối, ví dụ Toxiproxy hoặc cấu hình Linux traffic control. Tạo test có thời hạn và hoàn nguyên trạng thái sau mỗi ca. Một server đang chờ vô thời hạn trong test không phải điều kiện hợp lệ để tiếp tục thử các ca khác trên cùng pool.

### 8.3. Bài tập tính ngân sách

Một API dùng LDAP theo trình tự:

- Lấy connection mất 100 ms.
- Bind và search thứ nhất mất 900 ms.
- Search thứ hai mất 1.400 ms.
- Mapping/serialization mất 250 ms.

**Tổng thời gian là khoảng 2.650 ms.** Nếu SLA của API chỉ 2.000 ms thì các thao tác riêng lẻ đều có thể đáp ứng `read.timeout=1500ms` mà API vẫn vi phạm SLA. Hãy đề xuất cách giảm số truy vấn, đặt operation deadline trước mỗi lần gọi, tối ưu filter/index và phân bổ ngân sách để đáp ứng SLA.

Một phương án là ngừng khởi tạo search thứ hai khi không đủ ngân sách còn lại, giảm số lượt truy vấn bằng cách lấy đúng thuộc tính ở lần đầu hoặc dùng cache được kiểm soát. Cần kiểm tra tính đúng đắn của dữ liệu và cơ chế hết hạn cache nếu chức năng dùng thông tin nhóm/quyền truy cập.

## 9. Checklist trước khi đưa ra vận hành

- [ ] Có định nghĩa rõ timeout nào là TCP connect, socket read, search time limit, pool borrow và API deadline.
- [ ] Mọi timeout quan trọng được cấu hình bằng đơn vị thống nhất (mili giây) và có giá trị dương hữu hạn.
- [ ] LDAP dùng LDAPS hoặc StartTLS bắt buộc và xác minh CA/hostname.
- [ ] Search giới hạn base DN, scope, thuộc tính, số kết quả và filter có thể dùng index.
- [ ] Có log/metric elapsed time theo loại thao tác, số lần retry và nhóm lỗi; không ghi secret hoặc dữ liệu LDAP nhạy cảm.
- [ ] Đã kiểm chứng timeout thực tế trong lab với tình huống TCP không kết nối được và server giữ connection nhưng chậm phản hồi.
- [ ] Đã kiểm tra kết nối trong pool, cách loại bỏ kết nối lỗi và giới hạn thời gian mượn.
- [ ] Đã xác nhận tổng latency của endpoint/API nằm trong SLO và có xử lý hợp lệ khi deadline hết.
- [ ] Chỉ retry những thao tác an toàn, có ngân sách retry và tránh nhân tải lên LDAP đang suy giảm.
- [ ] Readiness/alert phản ánh phụ thuộc thực tế; không restart toàn bộ ứng dụng khi LDAP chỉ bị chậm tạm thời.

Khi vận hành **Spring LDAP**, đặt `connect.timeout` và `read.timeout` là nền tảng để tránh chờ vô hạn. Một **response deadline** có ý nghĩa nghiệp vụ phải được thiết kế ở tầng phù hợp, dựa trên số lượt LDAP call, thời gian mượn kết nối, giới hạn search, TLS và tổng latency quan sát được.

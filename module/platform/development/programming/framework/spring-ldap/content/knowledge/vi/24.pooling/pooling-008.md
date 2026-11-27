# Đo hiệu quả pooling trước và sau cấu hình

Khi tích hợp **Spring LDAP**, bật pooling có thể giảm chi phí mở kết nối TCP, thực hiện TLS handshake và bind lại tài khoản dịch vụ trước mỗi lần truy vấn. Nhưng câu hỏi quyết định trong vận hành là: **pooling đã cải thiện hiệu năng bao nhiêu, dưới loại tải nào, và có làm tăng lỗi hoặc tài nguyên đang giữ hay không?** Để trả lời, cần một phép đo có đối chứng thay vì chỉ quan sát một yêu cầu chạy nhanh hơn.

Bài học thuộc chương **Pooling** của module **SPRING_LDAP**. Chúng ta sẽ xây dựng phép thử trước/sau cho các thao tác LDAP bằng `ContextSource` và `LdapTemplate`, hiểu các chỉ số độ trễ, throughput, số lần bind, kết nối active/idle, cách đo bằng Java/Micrometer và cách đọc kết quả. Những nguyên tắc này cũng áp dụng khi ứng dụng dùng `LdapClient` hoặc ODM thông qua nguồn context của Spring LDAP. Kiểm thử phải giữ đúng DN, schema, filter, quyền truy cập, TLS và dữ liệu để chênh lệch quan sát được thực sự liên quan đến pooling.

## 1. Xác định giả thuyết trước khi benchmark

Ví dụ, một API nội bộ thường xuyên tìm tên hiển thị và nhóm của người dùng từ LDAP bằng cùng tài khoản dịch vụ. Khi không có pool, từng request có thể tạo context/kết nối mới và lặp lại TCP/TLS/bind. Khi có pool, các request sau có thể mượn một context hợp lệ đã được xác thực.

Giả thuyết cụ thể có thể là:

> Ở cùng 200 lượt LDAP lookup/giây, bật pooling sẽ giảm p95 độ trễ của thao tác ít nhất 20%, giảm số kết nối/bind mới, đồng thời không làm tăng tỷ lệ lỗi và không vượt ngân sách kết nối của LDAP server.

Đây là **mục tiêu giả định để kiểm thử**, không phải mức tăng tốc mặc định của Spring LDAP. Kết quả phụ thuộc mạng, TLS, LDAP server, kiểu filter và dữ liệu, số replica, kích thước pool, idle timeout và việc validation có phát sinh thêm lượt LDAP search hay không.

Pooling tối ưu **chi phí chuẩn bị và quản lý kết nối**, không cache entry. Một phép tìm kiếm lọc sai hoặc thiếu index có thể vẫn chậm sau khi bật pool.

### Hai cấu hình so sánh

| Nhóm thử nghiệm | Nguồn context | Mục đích |
|---|---|---|
| **A — baseline** | `LdapContextSource` không bật pooling ở lớp đang đo | Đo chi phí lấy context và thao tác LDAP khi không tái sử dụng theo cơ chế được chọn |
| **B — pooling** | Cùng nguồn gốc, bọc bằng pool context có giới hạn và chính sách xác thực rõ ràng | Đo tác động của tái sử dụng context |

Để phép đối chứng sạch, tránh vô tình bật **JNDI native connection pooling** trong baseline hoặc chồng JNDI pool với `PoolingContextSource` ở cấu hình B. Nếu chủ đích của phép thử là so sánh **JNDI native pooling**, cần thiết kế A/B riêng, lưu ý pool JNDI có phạm vi JVM và điều kiện đủ để dùng lại kết nối phụ thuộc provider, giao thức TLS, xác thực.

## 2. Phân biệt các phần của độ trễ

Một lượt gọi `LdapTemplate.search(...)` có thể gồm:

```text
Request bắt đầu
    |
    |-- chờ mượn context từ pool (nếu pool đã cạn)
    |-- lấy / tạo context: có thể mở TCP, TLS, bind
    |-- gửi yêu cầu LDAP search
    |-- LDAP server thực hiện filter, truy vấn index, trả entry
    |-- đọc kết quả, ánh xạ AttributesMapper
    |-- đóng tài nguyên và hoàn trả context
    |
Request hoàn thành
```

Có ba tầng đo cần tách:

1. **Độ trễ chức năng (`end-to-end LDAP operation`):** từ trước lời gọi template đến sau khi trả kết quả hoặc exception; thường bao gồm lấy/trả context và ánh xạ dữ liệu.
2. **Độ trễ mượn context:** đo thời gian ở `ContextSource.getReadOnlyContext()` hoặc `getReadWriteContext()`. Với provider kết nối lười (lazy), lời gọi này không nhất thiết bao trọn mọi chi phí connect/TLS/bind.
3. **Độ trễ phía LDAP server:** server xử lý search/modify. Không thể suy ra chính xác chỉ bằng một timer ở client; cần log/metric server khi có thể.

Sự khác biệt quan trọng: nếu p95 của template tăng nhưng p95 xử lý search trên server vẫn thấp, nguyên nhân có thể nằm ở hàng đợi mượn pool, network hoặc client mapping. Nếu p95 phía server cùng tăng, cần kiểm tra filter, index và mức tải trên LDAP.

### Chỉ số cốt lõi

| Chỉ số | Đơn vị | Điều nó trả lời |
|---|---|---|
| p50, p95, p99 của LDAP operation | ms | Đa số request và nhóm request chậm nhất chịu ảnh hưởng ra sao? |
| Throughput thành công | thao tác/giây | Pool có giúp phục vụ nhiều công việc hơn dưới cùng giới hạn tài nguyên không? |
| Tỷ lệ lỗi và timeout | % và số lần | Tăng tốc có đi kèm sai hỏng, kết nối stale hoặc cạn pool không? |
| Thời gian chờ mượn context | ms | Pool có trở thành điểm nghẽn mới không? |
| Context active/idle, số request chờ | số lượng | Pool có đủ capacity hay đang giữ quá nhiều context rảnh? |
| Kết nối TCP mới và LDAP bind mới | lần/giây | Chi phí tạo phiên có thực sự giảm không? |
| Kết nối LDAP đang mở | số lượng | Ứng dụng và LDAP server đang giữ bao nhiêu tài nguyên? |
| CPU, bộ nhớ, GC của ứng dụng và LDAP server | %, MB, lần | Chi phí được giảm ở đâu, có chuyển thành tải nơi khác không? |
| Thời gian phục hồi sau restart/idle | ms, lỗi đầu tiên | Pool có xử lý context stale đúng không? |

**Không kết luận chỉ từ throughput.** Nếu cùng lúc tăng số thread, kích thước kết quả hoặc số replica, throughput cao hơn có thể do tải khác nhau chứ không do pool. Với benchmark ở tốc độ yêu cầu cố định, hãy ưu tiên so sánh latency, lỗi và tài nguyên dưới cùng tải; với benchmark tìm công suất tối đa, tăng tải theo từng bậc và báo cáo giới hạn cùng điều kiện.

## 3. Thiết kế A/B để kết quả có thể so sánh

### Giữ các biến không thuộc pooling ổn định

| Thành phần | Yêu cầu khi so sánh A với B |
|---|---|
| LDAP server và dữ liệu | Cùng endpoint, schema, index, kích thước directory và tình trạng replication |
| Query | Cùng base DN, search scope, filter, size/time limit, phân trang và thuộc tính yêu cầu |
| Danh tính | Cùng DN dịch vụ và quyền; không trộn user bind theo từng request vào pool dịch vụ |
| Network và TLS | Cùng vị trí triển khai, LDAPS/StartTLS, trust store và chứng chỉ |
| Ứng dụng | Cùng JVM, phiên bản Spring LDAP, mapper, heap, CPU, số thread và replica |
| Tải | Cùng mẫu username, tỷ lệ request, tốc độ gửi, concurrency và thời gian chạy |
| Đo đạc | Cùng công cụ, cách tính percentile, nhãn metric và thời gian thu thập |
| Cấu hình | Ghi lại giới hạn pool, validation, eviction, timeout và cơ chế pooling được dùng |

Để tránh ảnh hưởng của cache, JIT compilation và kết nối còn sót trong JVM, nên chạy **hai tiến trình/deployment tách biệt** cho A và B. Nếu dùng native JNDI pooling, thay đổi một thuộc tính ở runtime có thể không tạo ra phép đo sạch bởi pool/provider tồn tại ở phạm vi process.

### Trình tự benchmark

1. **Xác định một workload chuẩn:** ví dụ lookup `cn` theo `uid` và tìm nhóm của người dùng, dữ liệu thử nghiệm có tỷ lệ kết quả tìm thấy/không thấy giống production.
2. **Xác định các bậc tải:** tải thấp, tải bình thường, tải đỉnh và burst. Nêu rõ số request/giây hoặc concurrency, vì hai đại lượng không tương đương.
3. **Khởi động cùng điều kiện:** tạo lại deployment, chờ JVM và LDAP server ổn định; đo cold start riêng.
4. **Warm-up:** chạy trước một khoảng đủ để JIT, TLS session và pool đạt trạng thái tương đối ổn định. Không trộn số liệu warm-up vào số liệu steady state.
5. **Đo từng bậc tải đủ lâu:** lấy p50/p95/p99, throughput, lỗi, active/idle, thời gian chờ, bind/s và CPU.
6. **Lặp A/B nhiều vòng:** thay thứ tự thử nghiệm nếu có thể (ví dụ A–B–B–A) để giảm ảnh hưởng của tình trạng máy chủ thay đổi theo thời gian.
7. **Thử phục hồi:** sau khi đã có kết quả steady state, đo riêng trường hợp idle lâu, kết nối bị ngắt và LDAP server restart ở môi trường thử nghiệm.
8. **Lưu điều kiện và số liệu gốc:** thời gian đo, version, cấu hình, dataset, mã workload và nguồn metric. Bảng tổng hợp không thay thế được bằng chứng đo.

Không nhất thiết phải chạy mọi mức tải đến khi server quá tải. Dừng thử nghiệm nếu đã chạm giới hạn an toàn của môi trường lab hoặc ảnh hưởng đến dịch vụ chia sẻ.

## 4. Thiết kế workload đúng loại truy vấn LDAP

Trong một hệ thống thật, có nhiều kiểu truy vấn với đặc tính khác nhau:

| Workload | Đặc điểm | Tác động pooling thường có |
|---|---|---|
| Lookup `uid` duy nhất | Filter được index, ít entry, thời gian LDAP search ngắn | Phần chi phí kết nối có thể chiếm tỷ trọng lớn |
| Tìm nhóm của user | Một số truy vấn/entry, tùy schema và group size | Cần đo cả số lệnh LDAP phát sinh |
| Search diện rộng / filter kém | Trả nhiều entry hoặc server xử lý lâu | Lợi ích pooling có thể nhỏ so với thời gian search |
| Modify một entry | Có tác dụng phụ; quyền và replication liên quan | Đo trên dữ liệu lab, không lặp thao tác ghi mù quáng |
| User authentication | Bind bằng DN/credential riêng cho từng login | Không dùng tái sử dụng phiên đã bind làm bằng chứng xác thực |

Nên dùng tập `uid` thử nghiệm đã biết và phân phối đầu vào giống ứng dụng thật. Nếu tất cả request tìm cùng một entry, cache server, filesystem hoặc directory index có thể khiến kết quả quá lạc quan. Ngược lại, sinh ngẫu nhiên hoàn toàn nhiều DN không tồn tại sẽ đo một workload khác production.

**Phân tách authentication và lookup:** benchmark pooling cho DN dịch vụ cố định không được ngầm áp dụng cho user bind. Việc mỗi lần đăng nhập phải kiểm tra credential của đúng người là ranh giới bảo mật, ngay cả khi phải chấp nhận thêm chi phí.

## 5. Ví dụ cấu hình hai chế độ cho phép thử

Ví dụ dưới đây minh họa lựa chọn **bật hoặc tắt pool context** bằng biến cấu hình lúc khởi động. Nó dùng `org.springframework.ldap.pool.factory.PoolingContextSource` thuộc họ API Commons Pool 1. Một số phiên bản Spring LDAP dùng `org.springframework.ldap.pool2.factory.PooledContextSource` dựa trên Commons Pool 2 với API khác; phải kiểm tra phiên bản và dependency trước khi triển khai.

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;
import org.springframework.ldap.pool.factory.PoolingContextSource;
import org.springframework.ldap.pool.validation.DefaultDirContextValidator;

@Configuration
public class LdapBenchmarkConfiguration {

    @Bean("rawContextSource")
    LdapContextSource rawContextSource(Environment env) {
        LdapContextSource source = new LdapContextSource();
        source.setUrl(env.getRequiredProperty("app.ldap.url"));
        source.setBase(env.getRequiredProperty("app.ldap.base"));
        source.setUserDn(env.getRequiredProperty("app.ldap.bind-dn"));
        source.setPassword(env.getRequiredProperty("app.ldap.bind-password"));
        source.setPooled(false); // Không bật JNDI native pooling.
        return source;
    }

    @Bean("workloadContextSource")
    ContextSource workloadContextSource(
            @Qualifier("rawContextSource") LdapContextSource raw,
            Environment env) {
        boolean enabled = env.getProperty(
                "app.ldap.pool-enabled", Boolean.class, false);
        if (!enabled) {
            return raw; // A: baseline, không có context pool.
        }

        PoolingContextSource pool = new PoolingContextSource(raw);
        pool.setMaxActive(12);
        pool.setMaxIdle(4);
        pool.setMaxWait(1_500L);
        pool.setDirContextValidator(new DefaultDirContextValidator());
        pool.setTestOnBorrow(true);
        return pool; // B: context pooling.
    }

    @Bean
    LdapTemplate ldapTemplate(
            @Qualifier("workloadContextSource") ContextSource source) {
        return new LdapTemplate(source);
    }
}
```

Ví dụ cấu hình:

```properties
app.ldap.url=ldaps://ldap-test.example.org:636
app.ldap.base=dc=example,dc=org
app.ldap.bind-dn=cn=benchmark-reader,ou=services,dc=example,dc=org
# app.ldap.bind-password lấy từ secret manager hoặc biến môi trường.
# Tạo hai tiến trình độc lập, với giá trị false và true tương ứng.
app.ldap.pool-enabled=false
```

Chỉ thay `app.ldap.pool-enabled` giữa hai cấu hình; giữ nguyên URL, TLS, DN, secret, code lookup và lượng tải. Vì ví dụ B có bật `testOnBorrow`, kết quả so sánh phản ánh **pool với validation**. Nếu cần tách riêng chi phí của validator, thực hiện thêm vòng C với cùng pool nhưng thay đúng một cờ validation; ghi rõ đây là một thí nghiệm bổ sung.

Với `ldaps://`, đảm bảo trust store, chứng chỉ và hostname verification hợp lệ ở cả A/B. Không giảm bảo mật để đạt con số benchmark tốt hơn. Cấu hình mẫu chỉ dành cho một tài khoản dịch vụ quyền đọc; không đưa login theo user hoặc thao tác ghi production vào workload.

## 6. Ghi thời gian `LdapTemplate` bằng Micrometer

Ứng dụng có thể bọc thời gian thực thi một thao tác nghiệp vụ với `Timer`. Code dưới đây đo **toàn bộ lời gọi `LdapTemplate.search(...)`**, bao gồm việc lấy context, search, ánh xạ và dọn tài nguyên do template quản lý. Đây là metric từ góc nhìn ứng dụng, không phải thời gian xử lý riêng của LDAP server.

```java
import java.util.List;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

public final class MeasuredDirectoryLookup {
    private final LdapTemplate ldapTemplate;
    private final MeterRegistry registry;

    public MeasuredDirectoryLookup(
            LdapTemplate ldapTemplate, MeterRegistry registry) {
        this.ldapTemplate = ldapTemplate;
        this.registry = registry;
    }

    public List<String> searchNames(String uid) {
        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";
        try {
            LdapQuery request = query()
                    .base("ou=people")
                    .where("uid").is(uid);
            return ldapTemplate.search(request,
                    (AttributesMapper<String>) attrs ->
                            attrs.get("cn") == null
                                    ? null
                                    : (String) attrs.get("cn").get());
        } catch (RuntimeException ex) {
            outcome = "error";
            throw ex;
        } finally {
            Timer timer = Timer.builder("ldap.lookup.duration")
                    .description("LDAP lookup through LdapTemplate")
                    .tag("operation", "uid_search")
                    .tag("outcome", outcome)
                    .publishPercentileHistogram()
                    .register(registry);
            sample.stop(timer);
        }
    }
}
```

Lưu ý khi dùng metric:

- Không dùng `uid`, DN, filter đầy đủ, mật khẩu hoặc tên người dùng làm **metric label**; điều này gây lộ dữ liệu và tạo cardinality cao. Nhãn `operation`, `outcome` cần tập giá trị nhỏ, cố định.
- Đo ở cả nhánh thành công và lỗi. Nếu chỉ đo các lệnh thành công, cấu hình pooling gây nhiều timeout có thể vẫn trông “nhanh”.
- Khả năng tính p95/p99 tùy backend metrics và cấu hình histogram. Một timer chỉ có count/total time chưa đủ tự sinh percentile chính xác.
- Nếu công cụ quan sát có thể gắn trace ID, dùng ID để đối chiếu sự chậm ở ứng dụng với log server; không đưa secret vào trace.
- Với phép search trả nhiều entry, callback mapping và cách xử lý `NamingEnumeration` có thể chiếm nhiều thời gian; giữ cách map giống nhau trong A/B.

### Nếu muốn đo riêng thời gian lấy context

Có thể tạo một lớp `ContextSource` decorator ghi thời gian `getReadOnlyContext()` và `getReadWriteContext()` rồi chuyển tiếp context nguyên bản cho `LdapTemplate`. Ví dụ này đo thời gian gọi lấy context, **không can thiệp vào hành vi `close()`**:

```java
import java.util.function.Supplier;
import javax.naming.directory.DirContext;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.ldap.core.ContextSource;

public final class TimedContextSource implements ContextSource {
    private final ContextSource delegate;
    private final MeterRegistry registry;

    public TimedContextSource(ContextSource delegate, MeterRegistry registry) {
        this.delegate = delegate;
        this.registry = registry;
    }

    @Override
    public DirContext getReadOnlyContext() {
        return measure("read", delegate::getReadOnlyContext);
    }

    @Override
    public DirContext getReadWriteContext() {
        return measure("write", delegate::getReadWriteContext);
    }

    @Override
    public DirContext getContext(String principal, String credentials) {
        // Không dùng user bind ở benchmark tài khoản dịch vụ này.
        return delegate.getContext(principal, credentials);
    }

    private DirContext measure(String kind, Supplier<DirContext> action) {
        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";
        try {
            return action.get();
        } catch (RuntimeException ex) {
            outcome = "error";
            throw ex;
        } finally {
            sample.stop(Timer.builder("ldap.context.acquire")
                    .tag("kind", kind)
                    .tag("outcome", outcome)
                    .publishPercentileHistogram()
                    .register(registry));
        }
    }
}
```

Để dùng decorator, bọc `workloadContextSource` bằng lớp này **khi cấu hình bean cho benchmark** rồi truyền decorator vào `LdapTemplate`; cần tránh phụ thuộc bean vòng tròn khi đăng ký các bean trong Spring. Quan sát thời gian ở phương thức lấy context giúp phát hiện chờ pool, nhưng với một provider tạo kết nối vật lý khi sử dụng lần đầu, con số này **không bao gồm toàn bộ TCP/TLS/bind**. Để đo thời gian chờ pool thuần túy, cần metric từ chính thư viện pool hoặc instrument ở vị trí borrow thích hợp.

## 7. Đọc kết quả: ví dụ có số liệu minh họa

Giả sử A và B đều được thử ở tải **200 lookup/giây trong 10 phút**, sau cùng một thời gian warm-up, trên cùng LDAP server. Bảng dưới đây hoàn toàn **giả định** nhằm luyện cách diễn giải, không phải benchmark đã chạy của Spring LDAP:

| Chỉ số | A: không pool | B: có pool | Diễn giải ban đầu |
|---|---:|---:|---|
| Throughput thành công | 199,8/s | 199,9/s | Tải cố định; hai chế độ đều gần đạt tải mục tiêu |
| p50 của LDAP operation | 24 ms | 9 ms | Giảm 62,5% |
| p95 của LDAP operation | 80 ms | 30 ms | Giảm 62,5% |
| p99 của LDAP operation | 150 ms | 68 ms | Giảm khoảng 54,7% |
| Tỷ lệ lỗi | 0,10% | 0,10% | Chưa thấy chênh lệch tỷ lệ lỗi |
| Kết nối/bind mới mỗi giây | 200 | 4 | Giảm mạnh hoạt động tạo kết nối, cần xác minh từ log server |
| Số kết nối đang mở (trung bình) | 5 | 14 | Pool giữ nhiều kết nối dài hạn hơn |
| p95 thời gian lấy context | 18 ms | 5 ms | Phù hợp giả thuyết giảm khởi tạo kết nối |

Để tính phần trăm thay đổi của một đại lượng cần **giảm** (như latency), dùng:

\[
\text{Tỷ lệ cải thiện} =
\frac{\text{Baseline} - \text{Pooling}}{\text{Baseline}}
\times 100\%.
\]

Ví dụ p95 từ 80 ms xuống 30 ms:

\[
\frac{80-30}{80}\times 100\% = 62{,}5\%.
\]

Độ trễ giảm rõ rệt và số bind mới giảm là bằng chứng phù hợp với giả thuyết, **nhưng vẫn cần kiểm tra** khoảng biến động giữa các lần chạy, áp lực CPU/bộ nhớ của LDAP server, tính đúng của các phép đo bind mới và p95/p99 ở tải đỉnh. Số kết nối đang mở cao hơn không tự động là vấn đề nếu nằm trong ngân sách server; nó là một đánh đổi của việc giữ idle context.

### Nếu số liệu ngược lại thì sao?

| Kết quả bất ngờ | Nguyên nhân đáng kiểm tra |
|---|---|
| Pool bật nhưng bind/s không giảm | Pool chưa hoạt động, context không được tái sử dụng, phân nhóm xác thực quá nhiều hoặc số liệu phía server đang gộp ứng dụng khác |
| p50 giảm nhưng p99 tăng | Pool cạn vào đợt burst, validation đắt hoặc một số context stale gây timeout |
| p95 gần như không đổi | Search trên server mới là nút thắt; thao tác dài nên chi phí connect là tỷ trọng nhỏ |
| Bị lỗi ngay sau thời gian idle | Firewall/server đóng socket, validation/eviction chưa phù hợp |
| CPU LDAP server tăng sau khi bật pool | Quá nhiều request đồng thời, tăng truy vấn validation hoặc tải thử khác |
| Throughput B cao hơn nhưng lỗi cũng tăng | Đang đẩy server vào vùng quá tải; cần so sánh cùng tỷ lệ thành công và mục tiêu SLA |

Tránh kết luận từ một lần chạy đơn lẻ. Với các percentile ở phần đuôi, cần đủ số lượng request và nhiều lần lặp. Không tính trung bình đơn giản của các giá trị p95 từ các phân đoạn nếu muốn tìm p95 toàn bộ mẫu; cần tổng hợp histogram/raw samples theo cách phù hợp.

## 8. Đo tải cao và sizing sau khi thấy lợi ích

Kết quả tốt ở mức 200 request/giây không đảm bảo ứng dụng vẫn tốt khi tăng lên 800 request/giây. Pool có số context đang hoạt động hữu hạn; khi pool cạn, request phải chờ mượn context hoặc thất bại theo chính sách.

Một ước lượng ban đầu về số context active trung bình là:

\[
L \approx \lambda W,
\]

với \(\lambda\) là số thao tác LDAP/giây và \(W\) là thời gian trung bình giữ context tính bằng giây. Ví dụ 300 thao tác/giây, giữ 40 ms:

\[
L \approx 300 \times 0{,}040 = 12\ \text{context active trung bình}.
\]

Mười hai chỉ là **giá trị trung bình**; burst, tail latency và các thời điểm server chậm có thể yêu cầu nhiều hơn. Thử các giá trị `maxActive` khác nhau để tìm vùng cân bằng giữa thời gian chờ và số kết nối ở server. Một pool lớn hơn có thể làm giảm hàng đợi nhưng đồng thời đẩy quá nhiều lệnh vào LDAP server.

Với nhiều replica, phải tính **ngân sách kết nối toàn cụm**. Nếu có 8 instance và mỗi instance giữ tới 20 context, tổng có thể lên đến 160 context (chưa kể các kết nối khác). Đo server-side connection count và thông số cho từng instance, tránh tự cho rằng `maxActive` của một JVM là giới hạn của hệ thống.

## 9. Thử kết nối stale và lỗi phục hồi ngoài steady state

Một phép thử pooling đầy đủ cần phân biệt **hiệu năng khi ổn định** với **tính sẵn sàng khi gặp sự cố**. Thực hiện trên LDAP server hoặc hạ tầng **lab**:

1. **Cold start:** bắt đầu từ pool rỗng; đo request đầu tiên và tốc độ làm nóng. Thời gian này có thể cao hơn steady state.
2. **Idle timeout:** để pool rảnh lâu hơn giới hạn thiết bị mạng; đo tỷ lệ request đầu tiên thất bại và thời gian phục hồi.
3. **Restart LDAP server:** khởi động lại server thử nghiệm, đo số context bị loại và số lần kết nối lại.
4. **Validation:** so sánh cùng pool với `testOnBorrow` hoặc `testWhileIdle`; đo tỷ lệ lỗi giảm được và chi phí phép kiểm tra.
5. **Saturation:** dùng burst vượt capacity mong muốn, đo p95 chờ pool, số timeout và khả năng ứng dụng hồi phục sau khi tải giảm.
6. **Đổi mật khẩu dịch vụ:** kiểm tra quy trình tái tạo pool, số phiên cũ còn mở và phân loại lỗi bind, không sử dụng credential thật.

Khi LDAP search hoặc modify gặp timeout, không được tự động gửi lại mọi thao tác. Với phép ghi, phản hồi có thể mất sau khi server đã xử lý lệnh; cần kiểm tra trạng thái để tránh tác dụng phụ lặp lại. Trong phép thử này, ưu tiên thao tác đọc an toàn và dữ liệu thử nghiệm.

## 10. Báo cáo benchmark để người khác tái lập được

Một bảng số liệu không đủ nếu thiếu điều kiện thực hiện. Mẫu báo cáo nên ghi:

| Thông tin | Ví dụ cách ghi |
|---|---|
| Mục tiêu | Giảm p95 lookup ở tải 200/s; tỷ lệ lỗi không tăng |
| Phiên bản và môi trường | JDK, Spring LDAP, JNDI provider, CPU/RAM, số replica |
| LDAP server | Loại server, môi trường lab, quy mô dataset, chỉ số index liên quan |
| Bảo mật | LDAPS, trust store, trạng thái chứng chỉ, cơ chế bind dịch vụ |
| Truy vấn | Base DN, filter shape, scope, số entry, thuộc tính lấy, tỷ lệ hit/miss |
| Workload | RPS, concurrency, burst profile, thời gian warm-up và đo |
| Cấu hình A | `LdapContextSource` không pool; loại trừ pool khác |
| Cấu hình B | Loại pool, `maxActive`, `maxIdle`, validation, max wait/eviction |
| Metrics | p50/p95/p99, success/s, error %, borrow wait, bind/s, connections, CPU |
| Độ tin cậy | Số lần chạy, độ biến động giữa vòng, cách tổng hợp percentile |
| Kết luận | Lợi ích đo được, đánh đổi, giới hạn và việc cần kiểm chứng tiếp |

### Bài tập thực hành

Trên LDAP test server, tạo một nhánh `ou=people,dc=example,dc=org` và tài khoản dịch vụ quyền đọc. Chuẩn bị các entry có thuộc tính `uid` và `cn`. Dùng `LdapQueryBuilder` để tìm kiếm an toàn, cùng một tập đầu vào ở cả A và B.

1. Chạy **A không pool** tại 50, 200 và 400 lookup/giây; ghi số liệu sau warm-up.
2. Chạy **B có pool** ở cùng các mức tải; dùng cùng JVM settings và mã lookup.
3. Tính phần trăm thay đổi của p95/p99 và tỷ lệ kết nối/bind mới. Kiểm tra có tăng lỗi hay không.
4. Giữ tốc độ 200/s nhưng đổi `maxActive` qua ba mức khác nhau; quan sát lúc nào p95 chờ pool giảm và lúc nào server chịu thêm áp lực.
5. Thử idle lâu rồi restart LDAP server lab; ghi số request đầu tiên thất bại, thời gian phục hồi và tác động của validation.
6. Lặp thí nghiệm, lưu bảng kết quả, histogram và thông số thử; ghi ít nhất một giả thuyết đã được dữ liệu hỗ trợ hoặc bác bỏ.

### Câu hỏi tự kiểm tra

1. Vì sao benchmark A/B phải giữ nguyên LDAP filter, dữ liệu, TLS và mức tải?
2. Vì sao p95 của `LdapTemplate.search` không tự nó cho biết thời gian xử lý search trên LDAP server?
3. Nếu p50 giảm nhưng p99 tăng sau khi bật pool, cần kiểm tra những chỉ số nào?
4. Vì sao số kết nối đang mở tăng sau khi bật pooling có thể là một đánh đổi có chủ đích?
5. `maxWait` đo điều gì, và nó khác LDAP read timeout như thế nào?
6. Khi dùng nhiều replica, vì sao phải tính tổng ngân sách kết nối của toàn hệ thống?
7. Vì sao một lần đo ở tải thấp chưa đủ để chấp nhận cấu hình pool trong production?
8. Đối với user bind, vì sao không thể chỉ sử dụng lại một phiên xác thực cũ để cải thiện số liệu đăng nhập?

**Kết luận:** hiệu quả của pooling phải được chứng minh bằng **cùng workload, cùng điều kiện, nhiều lần đo và đầy đủ chỉ số độ trễ–lỗi–tài nguyên**. Một kết quả tốt không chỉ là p50 giảm, mà còn là p95/p99 ổn định, số bind mới hợp lý, không cạn pool, không vượt ngân sách kết nối, và phục hồi được khi context idle mất hiệu lực. Trong Spring LDAP, đo đúng còn giúp quyết định nên tối ưu kết nối, validation, pool size hay chính truy vấn LDAP.

### Tài liệu tham khảo

- [Spring LDAP Reference Documentation](https://docs.spring.io/spring-ldap/reference/)
- [Spring LDAP API — LdapTemplate](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html)
- [Micrometer Documentation — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Apache Commons Pool Documentation](https://commons.apache.org/proper/commons-pool/)

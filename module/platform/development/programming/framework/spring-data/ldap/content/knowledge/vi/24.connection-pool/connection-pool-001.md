# Chi phí tạo LDAP context và mục đích của pool

Trong **Spring Data LDAP**, ứng dụng Java có thể truy vấn dịch vụ thư mục LDAP bằng `LdapRepository` hoặc `LdapTemplate`, ánh xạ entry trong cây DN thành đối tượng Java và thực hiện các thao tác đọc/ghi. Tuy nhiên, trước khi server xử lý một filter như `(&(objectClass=inetOrgPerson)(uid=lan))`, phía ứng dụng cần có một **LDAP context** thích hợp để giao tiếp với directory. Việc tạo và hủy context liên tục có thể trở thành chi phí đáng kể khi nhiều request cùng truy cập LDAP.

**Connection pool** giữ lại các context/kết nối có thể tái sử dụng để giảm chi phí thiết lập lặp đi lặp lại, giới hạn số tài nguyên được sử dụng đồng thời và quản lý tình trạng kết nối. Bài học giải thích vì sao tạo context có thể tốn thời gian, pool hoạt động thế nào, lúc nào nên dùng và những điều kiện cần kiểm soát.

Sau bài học, bạn có thể:

- Phân biệt `DirContext`, `ContextSource`, kết nối LDAP bên dưới và entry có DN trong thư mục.
- Phân tích chi phí của TCP, TLS, LDAP bind và các thao tác khởi tạo trong mỗi lượt truy cập.
- Mô tả vòng đời **borrow → use → close/return → reuse** và lợi ích của pool khi nhiều request đọc LDAP.
- Nhận biết giới hạn của pool, tình huống kết nối lỗi/hết hạn, pool cạn và nguy cơ khi tái sử dụng phiên có danh tính người dùng thay đổi.
- Hiểu cách cấu hình một pool cho `LdapTemplate` và các repository Spring Data LDAP dùng chung một `ContextSource`.

## 1. LDAP context là gì?

Trong Java, thư viện **JNDI** cung cấp giao diện `javax.naming.directory.DirContext` cho các thao tác thư mục như `search`, `lookup`, `bind`, `modifyAttributes` và `unbind`. Một `DirContext` mang theo ngữ cảnh truy cập LDAP: máy chủ, thông tin xác thực, cấu hình kết nối và điểm xuất phát để thực hiện các thao tác.

Spring LDAP xây dựng các tầng trừu tượng trên JNDI:

| Thành phần | Vai trò |
| --- | --- |
| **LDAP server** | Lưu entry, quản lý DN, `objectClass`, schema, quyền truy cập và thực thi truy vấn |
| **LDAP connection** | Kênh giao tiếp tới server, thường qua TCP và có thể được bảo vệ bằng TLS |
| **`DirContext`** | Đối tượng JNDI để gửi thao tác LDAP trong một ngữ cảnh cấu hình/xác thực |
| **`ContextSource`** | Thành phần Spring LDAP cấp phát `DirContext` để dùng cho đọc, ghi hoặc xác thực |
| **`LdapTemplate` / `LdapClient`** | Tầng gọi LDAP và quản lý phần lớn vòng đời context cho từng thao tác |
| **Spring Data LDAP repository** | Tầng truy vấn/lưu entity được ánh xạ từ entry LDAP; phụ thuộc vào hạ tầng LDAP bên dưới |

**Không nên đồng nhất một đối tượng `DirContext` với một socket TCP độc lập.** Tùy JNDI provider, một context có thể tham chiếu tới kết nối được dùng chung hoặc tái sử dụng; việc kết nối thực tế đôi khi diễn ra khi tạo context, đôi khi chỉ khi thao tác đầu tiên cần liên lạc server. Pool của Spring LDAP quản lý việc mượn/trả các context đủ điều kiện sử dụng, còn provider và cấu hình quyết định cách socket được cấp phát.

Ví dụ, DN `uid=lan,ou=people,dc=example,dc=org` định danh một entry. Filter `(uid=lan)` xác định điều kiện tìm. `DirContext` là phương tiện để gửi yêu cầu tìm entry đó trong phạm vi search base/scope thích hợp; nó **không phải** entry hay DN.

## 2. Vì sao tạo LDAP context có chi phí?

Khi ứng dụng lấy một context mới mà không có kết nối sẵn để tái sử dụng, các bước sau có thể phát sinh:

1. **Định vị server:** phân giải tên miền qua DNS hoặc chọn một LDAP URL trong cấu hình; có thể có DNS cache hoặc danh sách server dự phòng.
2. **Thiết lập kết nối mạng:** tạo TCP connection đến LDAP server, chịu độ trễ mạng, giới hạn socket và khả năng chấp nhận kết nối của server.
3. **Thiết lập kênh bảo mật:** nếu dùng LDAPS hoặc StartTLS, thực hiện đàm phán TLS, trao đổi chứng chỉ, xác minh danh tính server và thiết lập khóa phiên; có thể có cơ chế tái sử dụng phiên TLS tùy stack.
4. **Xác thực LDAP (bind):** gửi thông tin principal/credentials hoặc thực hiện cơ chế xác thực được cấu hình. Bind có thể yêu cầu nhiều lượt trao đổi hơn với các cơ chế phức tạp.
5. **Khởi tạo trạng thái ngữ cảnh:** tạo đối tượng JNDI, chuẩn bị các thuộc tính môi trường và thực hiện những thao tác khởi tạo/kiểm tra cần thiết của ứng dụng.
6. **Thực thi thao tác:** sau khi có context thích hợp mới gửi LDAP search, kiểm tra filter, quyền truy cập, tra cứu entry và giải mã kết quả.

Không phải mọi bước đều xảy ra ở mỗi lần gọi, và thứ tự chính xác tùy JNDI provider, LDAP server và cấu hình. Một phần thời gian có thể phát sinh ở **lần dùng đầu tiên** thay vì ngay tại constructor của `DirContext`.

Có thể mô hình hóa để suy nghĩ về độ trễ:

```text
T_khong_pool ≈ T_chuan_bi_ket_noi + T_thao_tac_LDAP + T_xu_ly_ket_qua

T_co_pool    ≈ T_muon_context + T_kiem_tra_neu_bat
             + T_thao_tac_LDAP + T_xu_ly_ket_qua + T_tra_context
```

Trong đó `T_chuan_bi_ket_noi` có thể bao gồm DNS, TCP, TLS, bind. Khi pool không có context phù hợp, vẫn có thể phải trả chi phí tạo mới; do đó **pool không loại bỏ hoàn toàn việc mở kết nối**.

### Ví dụ độ trễ giả định

Một dịch vụ tra cứu hồ sơ theo `uid` nhận nhiều request liên tiếp. Giả sử trong một môi trường kiểm thử, việc chuẩn bị kết nối và bind mất **40 ms**, còn search và ánh xạ kết quả mất **8 ms**:

| Trạng thái | Chi phí minh họa | Tổng độ trễ gần đúng |
| --- | --- | --- |
| Mỗi request phải mở và bind mới | 40 ms + 8 ms | 48 ms |
| Mượn được context đã sẵn sàng trong pool | 1 ms + 8 ms | 9 ms |
| Pool chưa có context hoặc context bị loại do lỗi | 40 ms + 8 ms + chi phí quản lý | Có thể tương đương hoặc cao hơn không dùng pool |

**Các con số hoàn toàn giả định**, dùng để minh họa khoản thời gian có thể tiết kiệm, không phải benchmark hay cam kết hiệu năng của Spring LDAP. Với directory rất gần ứng dụng, tần suất truy cập thấp hoặc server phản hồi chậm vì truy vấn phức tạp, lợi ích thực tế có thể nhỏ hơn nhiều.

## 3. Vòng đời khi không có pool và khi có pool

### Không có pool dành riêng ở tầng ứng dụng

```text
Request A -> xin DirContext -> chuẩn bị kết nối/bind -> search -> close
Request B -> xin DirContext -> chuẩn bị kết nối/bind -> search -> close
Request C -> xin DirContext -> chuẩn bị kết nối/bind -> search -> close
```

Nếu JNDI provider không tự chia sẻ/tái sử dụng kết nối cho các context này, chi phí kết nối có thể lặp lại ở từng request. Việc gọi `close()` giải phóng tài nguyên của context; cách quản lý socket cụ thể còn phụ thuộc provider.

### Có pool của Spring LDAP

```text
                  ┌───────────────────────────┐
Request A ------> │      Context pool         │
                  │ idle: [ctx-1] [ctx-2]     │
                  │ active: [...]             │
                  └────────────┬──────────────┘
                               │ borrow ctx-1
                               v
                       search với ctx-1
                               │ close (trả về)
                               v
                  pool giữ ctx-1 để tái sử dụng
                               │ borrow lần sau
                               v
                     Request B dùng ctx-1
```

Pool thực hiện các bước chính:

- **Borrow:** cung cấp context nhàn rỗi phù hợp. Nếu chưa có, pool có thể tạo mới trong giới hạn đã cấu hình; nếu đạt giới hạn, caller có thể phải chờ hoặc nhận lỗi.
- **Use:** `LdapTemplate` hoặc repository thực hiện search/CRUD bằng context được mượn. Entry trả về vẫn được xử lý theo schema, `objectClass`, DN và filter như bình thường.
- **Return:** sau khi thao tác kết thúc và context được đóng qua lớp bọc của pool, tài nguyên hợp lệ được trả về danh sách nhàn rỗi. *Đóng context mượn từ pool* thường là thao tác trả về pool, không đồng nghĩa luôn đóng ngay TCP socket.
- **Validate/evict:** tùy cấu hình, pool kiểm tra context trước khi cấp phát, khi trả lại hoặc trong thời gian nhàn rỗi; context lỗi có thể bị loại và thay thế khi cần.
- **Shutdown:** khi ứng dụng dừng, pool giải phóng các tài nguyên mà nó quản lý.

**Quan trọng:** một context đang được mượn không nên bị dùng đồng thời tùy tiện từ nhiều thread. Một request hoàn tất phải trả context; giữ context lâu hoặc quên `close()` làm pool nhanh chóng cạn tài nguyên.

## 4. Pool giải quyết vấn đề gì và không giải quyết vấn đề gì?

| Vấn đề | Pool có giúp? | Giải thích |
| --- | --- | --- |
| Thiết lập TCP/TLS và LDAP bind lặp lại | **Có, khi tái sử dụng thành công** | Có thể tránh tạo lại kênh và phiên xác thực cho mỗi lần đọc/ghi |
| Quá nhiều kết nối mở đồng thời | **Có** | Giới hạn số context active/idle và điều phối request chờ mượn |
| Đột biến tải trong thời gian ngắn | **Có điều kiện** | Context sẵn có giúp giảm chi phí khởi tạo; pool cạn vẫn tạo hàng đợi |
| Socket bị server/firewall đóng khi idle | **Có điều kiện** | Validation và loại context hỏng giúp giảm lỗi khi tái sử dụng |
| Filter LDAP viết sai, sai search base hoặc schema | **Không** | Pool không thay đổi ngữ nghĩa truy vấn |
| Search chậm vì thiếu index/quyền/schema | **Không** | Cần tối ưu truy vấn và cấu hình directory |
| Mật khẩu sai, chứng chỉ TLS không tin cậy | **Không** | Cần sửa xác thực hoặc cấu hình TLS |
| Lỗi mạng/LDAP server ngừng hoạt động | **Không loại bỏ được** | Có thể phát hiện context hỏng, nhưng không khiến server sẵn sàng trở lại |

Pool là một cách **tiết kiệm chi phí khởi tạo và quản lý tài nguyên**, không phải cache kết quả search. Nếu entry `uid=lan` thay đổi, một lần search sau vẫn phải gửi yêu cầu LDAP tới server; pool không giữ bản sao entry để trả trực tiếp.

## 5. Spring Data LDAP dùng pool ở tầng nào?

Spring Data LDAP dựa vào hạ tầng Spring LDAP. `LdapRepository` và `LdapTemplate` thao tác qua **`ContextSource`**; pool phù hợp được đặt tại tầng cấp `DirContext` đó. Khi repository dùng chung một `ContextSource` đã cấu hình pooling, các thao tác tìm kiếm và CRUD của nó có thể nhận lợi ích tương tự thao tác gọi trực tiếp từ `LdapTemplate`.

Hai lựa chọn thường gặp:

| Cách pooling | Đặc điểm |
| --- | --- |
| **JNDI native pooling** | Provider Java quản lý pool ở mức runtime; Spring LDAP có cờ `LdapContextSource#setPooled(true)`, mặc định tắt; cấu hình phần lớn qua system properties và có hạn chế về kiểm tra connection |
| **Spring LDAP pooling** | Wrapper `ContextSource`, hỗ trợ cấu hình giới hạn theo pool, kiểm tra `DirContext` và xử lý context lỗi; có triển khai dựa trên Apache Commons Pool/Pool2 |

Không nên bật hai cơ chế một cách máy móc. Trong ví dụ dưới đây, **native pooling được tắt**, còn pool được quản lý ở tầng Spring LDAP.

### 5.1. Ví dụ cấu hình Spring LDAP pool bằng Java

Ví dụ sau minh họa `org.springframework.ldap.pool2.factory.PooledContextSource` và `PoolConfig` (dựa trên Spring LDAP có hỗ trợ module pool2). Ứng dụng cần dependency tương ứng với phiên bản Spring LDAP/Spring Data LDAP đang dùng, cùng thư viện Apache Commons Pool2 khi cần. Các giá trị cấu hình chỉ là **điểm khởi đầu để thử nghiệm**, không phải kích thước tối ưu cho mọi môi trường.

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;
import org.springframework.ldap.pool2.factory.PoolConfig;
import org.springframework.ldap.pool2.factory.PooledContextSource;
import org.springframework.ldap.pool2.validation.DefaultDirContextValidator;

@Configuration
public class LdapPoolConfiguration {

    @Bean
    public LdapContextSource ldapContextSource(
            @Value("${app.ldap.url}") String url,
            @Value("${app.ldap.bind-dn}") String bindDn,
            @Value("${app.ldap.bind-password}") String password) {

        LdapContextSource source = new LdapContextSource();
        source.setUrl(url); // Ví dụ: ldaps://directory.example.org:636
        source.setBase("dc=example,dc=org");
        source.setUserDn(bindDn);  // Tài khoản dịch vụ có quyền tối thiểu
        source.setPassword(password);
        source.setPooled(false); // Tắt native JNDI pooling
        return source;
    }

    @Bean
    public PooledContextSource pooledContextSource(
            LdapContextSource ldapContextSource) {

        PoolConfig options = new PoolConfig();
        options.setMaxTotal(12);        // Toàn pool tối đa 12 context
        options.setMaxTotalPerKey(8);  // Giới hạn cho từng loại context
        options.setMaxIdlePerKey(4);   // Giữ tối đa 4 context idle mỗi loại
        options.setMaxWaitMillis(2000); // Chờ mượn tối đa 2 giây
        options.setTestOnBorrow(true); // Kiểm tra trước khi dùng

        PooledContextSource pooled = new PooledContextSource(options);
        pooled.setContextSource(ldapContextSource);
        pooled.setDirContextValidator(new DefaultDirContextValidator());
        return pooled;
    }

    @Bean
    public LdapTemplate ldapTemplate(PooledContextSource pooledContextSource) {
        return new LdapTemplate(pooledContextSource);
    }
}
```

Các thuộc tính `app.ldap.url`, `app.ldap.bind-dn`, `app.ldap.bind-password` là ví dụ cấu hình của ứng dụng, **không phải** thuộc tính Spring Boot mặc định. Mật khẩu nên được nạp từ nơi quản lý secret hoặc biến môi trường bảo vệ, không ghi trực tiếp trong mã nguồn. Với LDAPS, cần cấu hình truststore và xác minh chứng chỉ server đúng cách.

Trong một ứng dụng có nhiều bean `ContextSource`, cần bảo đảm repository hoặc cơ chế tự cấu hình nhận **bean pool mong muốn** (chẳng hạn bằng cấu hình `LdapTemplate`/qualifier rõ ràng). Đối chiếu API và dependency với phiên bản đang dùng trước khi đưa đoạn code vào dự án; các lớp `PoolingContextSource` (Commons Pool cũ) và `PooledContextSource` (Pool2) có tên, tham số khác nhau.

### 5.2. Đọc LDAP với `LdapTemplate` sau khi có pool

```java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQueryBuilder;

public class PersonLookupService {
    private final LdapTemplate ldapTemplate;

    public PersonLookupService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findNames(String uid) {
        return ldapTemplate.search(
                LdapQueryBuilder.query()
                    .base("ou=people")
                    .where("objectClass").is("inetOrgPerson")
                    .and("uid").is(uid),
                (AttributesMapper<String>) attributes ->
                    (String) attributes.get("cn").get());
    }
}
```

Ngữ nghĩa filter `(uid=...)` và DN của entry **không đổi** khi bật pool. `LdapTemplate` giúp quản lý ngữ cảnh theo lượt thao tác; application service không cần tự mở và giữ `DirContext` giữa các HTTP request. Trong trường hợp làm việc trực tiếp với `ContextSource#getReadOnlyContext()`, lập trình viên phải đóng context sau khi dùng, kể cả khi có exception:

```java
DirContext ctx = contextSource.getReadOnlyContext();
try {
    // Thực hiện thao tác trên ctx.
} finally {
    ctx.close(); // Trả lại pool nếu ctx được cấp phát qua pool.
}
```

Đoạn thứ hai minh họa **quản lý vòng đời**. Trong Java thực tế cần khai báo `ctx`, `contextSource` và xử lý `NamingException` tại vị trí sử dụng.

## 6. Các thông số ảnh hưởng đến hiệu quả pool

| Thông số / hành vi | Ý nghĩa vận hành | Nếu cấu hình không phù hợp |
| --- | --- | --- |
| `maxTotal`, `maxTotalPerKey` | Giới hạn tổng và theo loại context của pool2 | Quá thấp gây chờ; quá cao có thể gây quá tải directory |
| `maxIdlePerKey`, `minIdlePerKey` | Số context nhàn rỗi giữ lại hoặc cố duy trì | Nhiều idle lãng phí tài nguyên; quá ít có thể tăng lần tạo mới |
| `maxWaitMillis` | Thời gian chờ mượn khi pool cạn | Chờ vô hạn làm request treo lâu; quá ngắn gây lỗi khi tải tăng |
| `testOnBorrow` | Kiểm tra context ngay trước khi giao cho request | Giảm dùng context chết nhưng thêm một thao tác LDAP |
| `testWhileIdle` / eviction | Kiểm tra/loại context trong thời gian nhàn rỗi | Nếu không có kiểm tra, context idle có thể bị đóng từ phía network/server |
| Timeout kết nối/đọc LDAP | Giới hạn thời gian giao tiếp mạng thực tế | Pool timeout **không thay thế** timeout TCP và timeout thao tác LDAP |

Với triển khai pool2, pool có thể phân loại context theo read-only/read-write, vì vậy cần hiểu giới hạn **theo loại** và giới hạn **tổng**. Khi giới hạn được sử dụng hết, không có nghĩa pool tự động mở thêm kết nối vô hạn. Chính sách chờ/cấp phát sẽ quyết định kết quả của request tiếp theo.

**Kiểm tra kết nối cũng có chi phí.** Nếu `testOnBorrow=true`, mỗi lần mượn có thể phát sinh một truy vấn xác nhận context còn hoạt động. Cần cân nhắc giữa độ ổn định và độ trễ; nếu server/network thường ngắt idle connection, validation mang lại lợi ích rõ hơn.

## 7. Khi nào nên và không nên dùng pool?

Pool thường phù hợp khi ứng dụng có **lưu lượng tìm kiếm lặp lại**, nhiều request dùng cùng tài khoản dịch vụ, và chi phí TCP/TLS/bind đáng kể so với search. Ví dụ, API lấy tên/đơn vị của người dùng qua `uid`, hoặc dịch vụ đọc group membership định kỳ, có thể tái sử dụng những context xác thực bằng **cùng service account**.

Ngược lại, cần cân nhắc hoặc tránh pooling khi:

- Hệ thống chỉ truy cập LDAP rất ít; chi phí giữ socket và vận hành pool có thể lớn hơn lợi ích.
- Context được tạo theo **tài khoản của từng người dùng** hoặc danh tính xác thực thay đổi theo request. Pool dùng chung context mà không tách danh tính có thể khiến thao tác chạy với quyền của người dùng khác.
- Ứng dụng thay đổi trạng thái bảo mật của context sau khi tạo, chẳng hạn thay principal, security protocol hoặc dùng StartTLS theo cách không được cơ chế pooling hỗ trợ an toàn.
- Chưa có chính sách timeout, giới hạn số context, thu hồi context lỗi và xử lý shutdown phù hợp.

Đặc biệt, tài liệu Spring LDAP lưu ý `PoolingContextSource` giả định các context read-only có cùng môi trường xác thực, tương tự cho read-write. Không bọc trực tiếp `LdapContextSource` sử dụng `AuthenticationSource` lấy credential khác nhau theo thread để chia sẻ một pool thông thường: context được tạo bằng credential của người dùng trước có nguy cơ bị mượn lại ở request sau. Việc kiểm tra password người dùng qua `ContextSource#getContext(principal, credentials)` phải tuân theo ngữ nghĩa xác thực riêng; Spring LDAP không sử dụng **native JNDI pooling** cho lời gọi này để password đổi có hiệu lực nhanh.

Pooling không làm dữ liệu tự động an toàn. Dù dùng kết nối sẵn có, vẫn phải dùng LDAPS/TLS hợp lệ, kiểm soát quyền service account, escape giá trị filter để tránh LDAP injection và giới hạn dữ liệu nhạy cảm ghi vào log.

## 8. Kiểm chứng lợi ích trong môi trường thử nghiệm

Để đánh giá có nên bật pool cho ứng dụng Spring Data LDAP, thực hiện trong directory test (hoặc môi trường tương đương production có dữ liệu giả):

1. **Đo đường cơ sở:** chạy cùng một tập search bằng `LdapTemplate`/repository với pooling tắt; thu thập thông lượng và latency ở các phân vị (ví dụ p50, p95, p99).
2. **Bật pool:** giữ nguyên query, search base, số thread và dataset; khởi động đủ để phân biệt thời gian làm nóng pool với trạng thái ổn định.
3. **Đo tài nguyên:** quan sát số context active/idle, số request đang chờ, số kết nối phía server và mức sử dụng CPU. `PooledContextSource` pool2 có các accessor như `getNumActive()`, `getNumIdle()` và `getNumWaiters()` để hỗ trợ quan sát.
4. **Thử tải tăng:** dùng nhiều request đồng thời hơn giới hạn pool; kiểm tra request chờ bao lâu và lỗi được báo ra sao khi hết `maxWaitMillis`.
5. **Thử kết nối chết:** để context idle qua khoảng thời gian server/firewall có thể ngắt, hoặc dừng rồi khôi phục directory test; quan sát hành vi validation, loại context lỗi và kết quả ở request sau.
6. **Thử thay đổi credential:** bảo đảm cơ chế xác thực người dùng không vô tình mượn phiên gắn với quyền của tài khoản khác; kiểm tra quy trình đổi/thu hồi mật khẩu service account và làm mới các context đã xác thực.

Đọc số liệu cùng bối cảnh: độ trễ do server tìm kiếm, thiếu index hoặc trả về rất nhiều entry sẽ không biến mất vì có pool. Cần tách riêng phần **chờ pool**, **thiết lập kết nối** và **thời gian thao tác LDAP** nếu công cụ đo cho phép.

## 9. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao việc tạo `DirContext` mới có thể chậm ngay cả khi filter `(uid=lan)` rất đơn giản?

*Gợi ý:* Thời gian kết nối, TLS và bind có thể lớn hơn thời gian server xử lý filter. Một số chi phí chỉ xuất hiện ở lần thao tác đầu tiên.

**Câu 2.** Pool có 8 context đang được mượn và không còn context nhàn rỗi; request thứ chín sẽ thế nào?

*Gợi ý:* Tùy `maxTotal`, `maxTotalPerKey` và chính sách cạn pool, request có thể được cấp mới, phải chờ hoặc thất bại. Không thể khẳng định chỉ từ con số 8.

**Câu 3.** Tại sao không nên chia sẻ một pool service account với các context gắn danh tính từng người dùng?

*Gợi ý:* Một context có quyền truy cập của người này không được phép phục vụ request dưới danh tính người khác; đó là lỗi cách ly thông tin xác thực.

**Câu 4.** Bật `testOnBorrow` có luôn làm LDAP nhanh hơn không?

*Gợi ý:* Không. Nó có thể tăng một khoản chi phí kiểm tra cho mỗi lần mượn, đổi lại giảm xác suất sử dụng context không còn hợp lệ.

## 10. Ghi nhớ

- Chi phí **tạo và xác thực** LDAP context có thể bao gồm DNS, TCP, TLS, bind và khởi tạo; tác động đáng kể khi lặp lại ở tải cao.
- Pool cho phép **mượn, sử dụng, trả lại và tái sử dụng** các context phù hợp, đồng thời kiểm soát số tài nguyên active/idle và thời gian chờ.
- Pool hoạt động ở **tầng `ContextSource`**, nên `LdapTemplate` và Spring Data LDAP repository có thể dùng chung hạ tầng pooling; pool không cache entry hoặc tăng tốc bản thân LDAP filter.
- Cần cấu hình giới hạn, timeout, kiểm tra kết nối, theo dõi tải và tránh chia sẻ context giữa những danh tính xác thực khác nhau.
- Chỉ kết luận pool có lợi khi đã đo trên workload và directory đại diện cho hệ thống thật.

**Tài liệu tham khảo:**

- [Spring LDAP Reference — Pooling Support](https://docs.spring.io/spring-ldap/reference/pooling.html)
- [Spring LDAP Reference — Configuration](https://docs.spring.io/spring-ldap/reference/configuration.html)
- [Spring LDAP API — PooledContextSource (Commons Pool2)](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/pool2/factory/PooledContextSource.html)
- [Oracle JNDI Tutorial — Connection Pooling](https://docs.oracle.com/javase/jndi/tutorial/ldap/connect/pool.html)

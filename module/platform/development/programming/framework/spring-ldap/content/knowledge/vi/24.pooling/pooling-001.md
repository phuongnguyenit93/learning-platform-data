# Vì sao LDAP context pooling cải thiện chi phí kết nối

Trong **Spring LDAP**, một thao tác tìm kiếm hoặc cập nhật entry thường đi qua `LdapTemplate`, lấy một LDAP context từ `ContextSource` rồi trả context sau khi thao tác kết thúc. Nếu mỗi lần lấy context đều phải thiết lập kết nối mạng và xác thực lại với máy chủ thư mục, ứng dụng sẽ tốn nhiều thời gian cho phần chuẩn bị, dù truy vấn LDAP thực tế rất ngắn. **LDAP context pooling** cho phép tái sử dụng tài nguyên kết nối/context đã được khởi tạo, qua đó giảm chi phí này khi ứng dụng gọi LDAP nhiều lần.

Đây là chủ đề thuộc chương **Pooling** của **SPRING_LDAP**. Để hiểu và áp dụng đúng, cần phân biệt DN, quyền của tài khoản bind, filter tìm kiếm, vòng đời context, kết nối TLS và cơ chế pool. Pooling chỉ tối ưu đường đi đến dịch vụ thư mục; các truy vấn, quyền truy cập và thao tác entry bằng `LdapTemplate`, `LdapClient` hoặc ODM vẫn phải tuân theo schema và quy tắc bảo mật của LDAP.

## 1. Một lời gọi LDAP phải trả những chi phí gì?

Một LDAP context, thường là `DirContext` hoặc `LdapContext` trong JNDI, đại diện cho môi trường làm việc với dịch vụ thư mục. Context giữ thông tin về máy chủ, cách xác thực và trạng thái phục vụ các thao tác như search, lookup, bind, modify hoặc unbind.

Khi ứng dụng cần tạo kết nối mới, các bước có thể gồm:

1. **Thiết lập đường truyền:** phân giải tên máy chủ khi cần và mở kết nối TCP đến LDAP server.
2. **Thiết lập bảo mật:** thực hiện TLS handshake nếu dùng LDAPS hoặc cơ chế StartTLS phù hợp.
3. **Xác thực (bind):** gửi danh tính, thông tin xác thực và chờ server chấp nhận.
4. **Thực hiện nghiệp vụ:** gửi LDAP search/modify/add/delete và nhận phản hồi.
5. **Giải phóng:** đóng context; kết nối mạng có thể bị đóng hoặc được trả về pool, tùy cấu hình.

Không phải môi trường nào cũng phát sinh đủ năm bước cho mỗi yêu cầu. Chẳng hạn, kết nối đã tồn tại không phải lặp TCP/TLS handshake; một số context được khởi tạo mà chưa kết nối vật lý cho tới thao tác đầu tiên. Điều cần phân biệt là **chi phí tạo phiên làm việc mới** và **chi phí của chính thao tác LDAP**.

| Thành phần chi phí | Khi thường xuyên tạo kết nối mới | Khi tái sử dụng context/kết nối hợp lệ |
|---|---|---|
| TCP và TLS handshake | Có thể lặp lại ở nhiều lời gọi | Chủ yếu trả ở lần tạo ban đầu hoặc khi phải tạo kết nối thay thế |
| LDAP bind | Có thể xác thực lại cho mỗi kết nối mới | Có thể tận dụng trạng thái xác thực của phiên đã tái sử dụng, tùy cơ chế pool |
| Search hoặc modify | Vẫn phải thực hiện | **Vẫn phải thực hiện** |
| Socket, CPU, bộ nhớ trên client/server | Tăng do tạo và hủy kết nối liên tục | Giảm hoạt động tạo/hủy; đổi lại tốn tài nguyên duy trì kết nối nhàn rỗi |
| Chờ tài nguyên | Chờ tạo kết nối | Có thể chờ mượn từ pool khi tất cả kết nối đều đang bận |

Pooling **không phải cache kết quả truy vấn**. Hai lần tìm kiếm cùng một filter vẫn là hai thao tác gửi đến LDAP server, trừ khi ứng dụng triển khai cơ chế cache dữ liệu riêng.

## 2. Cơ chế pooling giúp giảm độ trễ như thế nào?

Không có pool, mô hình đơn giản của mỗi lời gọi là:

```text
Ứng dụng → tạo context/kết nối → TCP/TLS → LDAP bind
         → gửi search → nhận kết quả → đóng context/kết nối
```

Với pool đã được làm nóng và còn kết nối hợp lệ:

```text
Ứng dụng → mượn context/kết nối → gửi search → nhận kết quả
         → trả về pool để thao tác sau sử dụng lại
```

Giả sử một hệ thống có thời gian trung bình như sau (số liệu **minh họa**, không phải benchmark của Spring LDAP):

| Công đoạn | Tạo kết nối mới | Tái sử dụng từ pool |
|---|---:|---:|
| TCP, TLS và LDAP bind | 12 ms | 0 ms trong lượt tái sử dụng thành công |
| Mượn/trả tài nguyên pool | 0 ms | 1 ms |
| Thực hiện LDAP search | 2 ms | 2 ms |
| **Tổng xấp xỉ** | **14 ms** | **3 ms** |

Với giả định này, phần tiết kiệm là khoảng 11 ms mỗi truy vấn sau khi pool đã sẵn sàng. Con số thực tế phụ thuộc độ trễ mạng, TLS, server, kích thước kết quả, filter, tải đồng thời, thời gian chờ pool và tỷ lệ context hỏng phải tạo lại. Khi search mất hàng trăm mili giây do filter không có index hoặc trả quá nhiều entry, tối ưu kết nối thường chỉ giải quyết một phần nhỏ tổng thời gian.

Ngoài độ trễ, pool còn giảm tốc độ mở và đóng socket, giảm các lần bind lặp lại và giúp server tránh phải xử lý quá nhiều phiên kết nối ngắn. Lợi ích rõ nhất thường xuất hiện ở các ứng dụng web hoặc service gọi LDAP lặp lại bằng **cùng tài khoản dịch vụ** để tra cứu DN, thuộc tính người dùng hoặc nhóm.

## 3. Pool thực sự giữ thứ gì?

Cần phân biệt hai cách triển khai có tên gần giống nhau:

| Cơ chế | Tài nguyên tái sử dụng | Điểm cần hiểu |
|---|---|---|
| **JNDI LDAP connection pooling** của Java LDAP provider | Kết nối LDAP bên dưới các context | Một context mới có thể sử dụng lại kết nối vật lý; việc gọi `close()` không nhất thiết đóng socket |
| **Context pooling** do thư viện quản lý, chẳng hạn `PoolingContextSource` khi có trong phiên bản/phụ thuộc Spring LDAP đang dùng | Đối tượng context được quản lý trong pool | Có thể cung cấp chính sách mượn/trả, giới hạn số context, kiểm tra hợp lệ và loại bỏ context hỏng theo khả năng của thư viện |

Do đó, câu “pooling tái sử dụng context” là cách nói khái quát. Với pool tích hợp trong JNDI, thứ được tái sử dụng trực tiếp chủ yếu là **kết nối mạng**. Với một context pool, ứng dụng mượn lại **context** do pool quản lý. Hai cơ chế có cùng mục tiêu giảm chi phí thiết lập nhưng khác vòng đời và cách cấu hình.

Trong Spring LDAP, `LdapTemplate` làm việc thông qua `ContextSource`. Code nghiệp vụ thông thường không cần tự giữ một `DirContext` toàn cục: template lấy context, thực thi thao tác và đóng/trả theo hợp đồng của nguồn context. Việc giữ một context để nhiều thread cùng dùng có thể gây xung đột trạng thái, sai quyền hoặc lỗi kết nối.

## 4. Ví dụ cấu hình JNDI pooling với Spring LDAP

Ví dụ dưới đây dùng `LdapContextSource` và `LdapTemplate` cho các truy vấn bằng **tài khoản dịch vụ**. Các giá trị kết nối được lấy từ cấu hình bảo mật của ứng dụng.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class LdapConfiguration {

    @Bean
    LdapContextSource ldapContextSource(Environment environment) {
        LdapContextSource source = new LdapContextSource();
        source.setUrl(environment.getRequiredProperty("app.ldap.url"));
        source.setBase(environment.getRequiredProperty("app.ldap.base"));
        source.setUserDn(environment.getRequiredProperty("app.ldap.bind-dn"));
        source.setPassword(environment.getRequiredProperty("app.ldap.bind-password"));

        // Bật cơ chế pooling của JNDI LDAP provider.
        source.setPooled(true);
        return source;
    }

    @Bean
    LdapTemplate ldapTemplate(LdapContextSource contextSource) {
        return new LdapTemplate(contextSource);
    }
}
```

Ví dụ cấu hình ứng dụng:

```properties
app.ldap.url=ldaps://ldap.example.org:636
app.ldap.base=dc=example,dc=org
app.ldap.bind-dn=cn=ldap-reader,ou=services,dc=example,dc=org
# app.ldap.bind-password lấy từ secret manager hoặc biến môi trường;
# không commit mật khẩu thật vào repository.
```

**Lưu ý quan trọng khi dùng LDAPS:** JNDI LDAP provider có thể chỉ cho phép pooling đối với giao thức `plain` theo mặc định. Nếu muốn pool kết nối `ldaps://`, cần xác minh và, khi phù hợp, cấu hình giao thức `ssl` cho JNDI provider **trước khi pool được khởi tạo**. Ví dụ các tùy chọn JVM:

```text
-Dcom.sun.jndi.ldap.connect.pool.protocol=ssl
-Dcom.sun.jndi.ldap.connect.pool.maxsize=16
-Dcom.sun.jndi.ldap.connect.pool.timeout=300000
```

Các thuộc tính JVM trên thuộc **JNDI LDAP provider**, không phải thuộc tính `app.ldap.*` của Spring. Giới hạn số kết nối có thể áp dụng theo từng nhóm kết nối có cùng tham số kết nối/xác thực, vì vậy không nên hiểu `maxsize=16` là giới hạn tuyệt đối mọi socket LDAP của toàn ứng dụng. `timeout` là thời gian nhàn rỗi tính bằng mili giây của kết nối trong pool. Giá trị chỉ mang tính khởi điểm minh họa; cần đo tải và kiểm tra khả năng hỗ trợ của JDK/provider thực tế.

Sau khi cấu hình, code sử dụng `LdapTemplate` gần như không thay đổi:

```java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;

LdapQuery query = LdapQueryBuilder.query()
        .base("ou=people")
        .where("uid").is(uid);

List<String> commonNames = ldapTemplate.search(
        query,
        (AttributesMapper<String>) attrs -> (String) attrs.get("cn").get()
);
```

Ở đây `uid` là đầu vào của phương thức nghiệp vụ. `LdapQueryBuilder` tạo filter và xử lý escaping giá trị đầu vào; pooling không thay thế biện pháp này. Cần đảm bảo entry thực sự có thuộc tính `cn` hoặc xử lý trường hợp thiếu thuộc tính. Base DN trong query là tương đối với base DN đã cấu hình ở `LdapContextSource`.

Nếu cần kiểm soát thời gian chờ, kiểm tra context trước khi mượn, dọn các context nhàn rỗi hoặc giới hạn tài nguyên chặt hơn, có thể cân nhắc `PoolingContextSource` và mô-đun pooling tương ứng với **phiên bản Spring LDAP** đang dùng. Không nên đồng thời bật nhiều tầng pool chỉ vì nghĩ rằng “nhiều pool sẽ nhanh hơn”; cần hiểu cách chúng quản lý vòng đời và đo kết quả.

## 5. Khi nào pooling có ích và khi nào không?

**Tình huống phù hợp:** một ứng dụng tra cứu quyền truy cập của người dùng qua nhiều request, sử dụng một DN dịch vụ chuyên đọc. Mỗi lần kiểm tra quyền, ứng dụng tra cứu nhóm hoặc thuộc tính người dùng bằng filter. Nếu phần lớn thời gian dành cho mở kết nối và bind, pool giúp các request kế tiếp tái sử dụng phiên LDAP đã xác thực.

**Tình huống lợi ích thấp:** ứng dụng hiếm khi gọi LDAP, mỗi lần truy vấn trả hàng chục nghìn entry, hoặc thời gian query chủ yếu nằm ở server do không có index, phân trang kém hay tìm kiếm quá rộng. Khi đó nên tối ưu filter, phạm vi DN, index, giới hạn kết quả và cách phân trang trước khi kỳ vọng pool giải quyết độ trễ.

**Tình huống phải cân nhắc kỹ:** xác thực từng người dùng bằng cách bind với DN và mật khẩu của chính họ. Kết nối của mỗi danh tính có ranh giới quyền khác nhau. Pool cho tài khoản dịch vụ không đồng nghĩa mọi kết nối xác thực người dùng sẽ được tái sử dụng an toàn hoặc hiệu quả. Các thao tác authenticate cần chiến lược và vòng đời context riêng phù hợp với mô hình bảo mật.

## 6. Những rủi ro phát sinh khi tái sử dụng kết nối

### 6.1. Kết nối nhàn rỗi có thể đã bị đóng

Firewall, load balancer hoặc LDAP server có thể ngắt socket sau một khoảng thời gian không hoạt động. Pool vẫn có thể giữ tài nguyên mà nó tưởng là hợp lệ. Lần mượn tiếp theo dẫn tới lỗi I/O, timeout hoặc cần tạo lại kết nối.

Cần chọn thời gian sống nhàn rỗi, cơ chế validation/eviction khi framework hỗ trợ, timeout và xử lý kết nối lỗi dựa trên thực tế hạ tầng. Không nên retry vô hạn một thay đổi LDAP: thao tác ghi có thể đã được server xử lý trước khi client nhận lỗi, và gửi lại có thể gây tác dụng phụ.

### 6.2. Pool quá nhỏ hoặc quá lớn đều có giá

Pool quá nhỏ có thể khiến các request phải chờ tài nguyên, tăng p95/p99 latency hoặc nhận lỗi khi hết thời gian chờ. Pool quá lớn làm tăng số socket, bộ nhớ, phiên xác thực và tài nguyên bị giữ trên LDAP server.

Ước lượng ban đầu có thể dùng quan hệ: **số kết nối đang bận trung bình ≈ số thao tác LDAP/giây × thời gian giữ một kết nối (giây)**. Ví dụ 120 thao tác/giây, mỗi thao tác giữ kết nối 25 ms, cho khoảng `120 × 0,025 = 3` kết nối bận trung bình. Đây **không phải** cấu hình pool cuối cùng, vì cần xét các đợt tăng tải, thời gian chờ, tài khoản/endpoint khác nhau và mức kết nối server cho phép.

### 6.3. Bảo mật và trạng thái xác thực vẫn quan trọng

- Dùng **LDAPS hoặc StartTLS** với xác minh chứng chỉ và trust store được cấu hình đúng. Không hạ mức bảo mật chỉ để bật pool.
- Với **StartTLS**, không mặc định rằng một kết nối sau khi nâng cấp TLS có thể đưa vào bất kỳ pool nào. Kiểm tra hỗ trợ và vòng đời của authentication strategy/JNDI provider; nếu không tương thích, giữ pooling tắt cho đường kết nối đó.
- Tách các danh tính và quyền truy cập. Không đưa context đã bind bằng credential của người dùng A vào nơi thao tác của người dùng B.
- Khi đổi mật khẩu tài khoản dịch vụ hoặc thay chứng chỉ, pool có thể giữ phiên cũ cho tới khi kết nối được thay thế. Thiết kế cơ chế khởi tạo lại/thu hồi pool phù hợp với việc xoay vòng secret.
- Không log mật khẩu, token hoặc toàn bộ dữ liệu nhạy cảm chỉ để chẩn đoán pool.

### 6.4. Pool không chữa được lỗi thiết kế LDAP

Pool không tạo index cho thuộc tính tìm kiếm, không thay đổi schema, không sửa DN sai, không tự escape filter, không giải quyết phân quyền và không bảo đảm server luôn sẵn sàng. Cần xử lý riêng timeout, referral, giới hạn kết quả, phân trang, quyền của bind DN và các mã lỗi LDAP.

## 7. Cách chứng minh pooling thực sự hiệu quả

So sánh **cùng một chức năng LDAP**, cùng dữ liệu, filter, server, cấu hình TLS và mức tải, ở hai trạng thái: tắt pool và bật pool. Sau thời gian khởi động/làm nóng phù hợp, kiểm tra ít nhất:

| Quan sát | Điều mong đợi | Dấu hiệu cần điều tra |
|---|---|---|
| p50, p95, p99 của thao tác LDAP | Độ trễ giảm nếu khởi tạo kết nối chiếm phần đáng kể | p95 tăng vì chờ pool hoặc context stale |
| Lượng kết nối/bind mới mỗi giây | Giảm ở tải lặp lại | Không giảm: pool chưa bật hoặc các kết nối không đủ điều kiện dùng chung |
| Số socket/kết nối LDAP đồng thời | Ổn định trong giới hạn server cho phép | Tăng không kiểm soát hoặc bị server từ chối |
| Lỗi timeout, reset, authentication | Không tăng so với ban đầu | Kết nối chết, chiến lược xác thực sai hoặc secret đã đổi |
| Thời gian chờ mượn, active/idle nếu pool có metric | Có dư địa ở tải mục tiêu | Pool cạn hoặc giữ tài nguyên quá lâu |

Với JNDI connection pooling tích hợp, không phải lúc nào ứng dụng cũng có sẵn metric active/idle thuận tiện như các thư viện pool chuyên dụng. Có thể kết hợp số liệu độ trễ tại ứng dụng, log phía LDAP server và quan sát kết nối mạng. Không dùng duy nhất số lần tạo đối tượng Java làm bằng chứng về số kết nối TCP: JNDI có thể tạo context mới nhưng dùng lại kết nối cũ.

Ngoài tải đều, cần thử **cold start**, tăng tải đột ngột, idle lâu rồi truy vấn lại, LDAP server restart/failover và xoay vòng mật khẩu. Chỉ bật pool trong môi trường sản xuất sau khi các thử nghiệm đó xác nhận cả hiệu năng lẫn an toàn truy cập.

## 8. Bài tập thực hành và câu hỏi tự kiểm tra

**Bài tập:** triển khai một endpoint dùng `LdapTemplate` tìm `cn` theo `uid` trong một thư mục thử nghiệm. Chạy cùng bộ truy vấn với pool tắt/bật, đo độ trễ và số kết nối LDAP mới trên server. Sau đó để ứng dụng nhàn rỗi lâu hơn idle timeout của hạ tầng và chạy lại. Ghi rõ cơ chế pool đã sử dụng (JNDI connection pool hay context pool), cấu hình JDK/TLS và lý do nếu kết quả không cải thiện.

Tự trả lời ba câu hỏi:

1. Vì sao pooling thường giúp nhiều hơn với 100 phép lookup ngắn so với một truy vấn LDAP rất nặng?
2. Vì sao bật `setPooled(true)` không đồng nghĩa mọi kết nối `ldaps://` hoặc StartTLS đều chắc chắn được tái sử dụng?
3. Vì sao không nên dùng chung một `DirContext` đã xác thực bằng tài khoản người dùng giữa nhiều request hoặc thread?

**Kết luận:** LDAP context pooling cải thiện chi phí kết nối bằng cách phân bổ chi phí TCP/TLS/bind cho nhiều thao tác LDAP thay vì lặp lại cho từng thao tác. Trong Spring LDAP, hiệu quả phụ thuộc cơ chế pool cụ thể, đặc tính `ContextSource`, cách xác thực, TLS, mức đồng thời và cách ứng dụng quản lý context. Chỉ số đúng để quyết định là độ trễ, tỷ lệ kết nối mới, tình trạng chờ pool và độ ổn định truy cập dưới tải thực tế.

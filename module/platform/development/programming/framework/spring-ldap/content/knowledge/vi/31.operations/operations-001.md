# Health check kết nối LDAP và kiểm tra quyền tối thiểu

## 1. Vì sao ứng dụng Spring LDAP cần health check riêng?

Ứng dụng dùng Spring LDAP có thể phụ thuộc vào LDAP để tìm tài khoản, tra cứu nhóm, xác thực người dùng hoặc cập nhật entry. Khi chức năng đăng nhập thất bại, nguyên nhân có thể là DNS, kết nối TCP, chứng chỉ TLS, tài khoản bind, truy vấn sai DN, schema thay đổi hoặc quyền truy cập bị thu hồi. Một phép kiểm tra chỉ mở được cổng 389/636 không đủ để khẳng định đường đi LDAP thực sự dùng được.

Trong vận hành, cần phân biệt **khả năng phục vụ** với **quyền truy cập đúng phạm vi**:

| Tầng kiểm tra | Câu hỏi cần trả lời | Dấu hiệu thành công | Điều chưa được chứng minh |
| --- | --- | --- | --- |
| DNS/TCP | Máy ứng dụng tìm thấy và kết nối tới LDAP server chứ? | Kết nối tới host, cổng đích | Chưa xác minh TLS, tài khoản hay ACL |
| TLS | Kênh có mã hóa và xác minh đúng máy chủ chứ? | Bắt tay TLS thành công, chứng chỉ hợp lệ | Chưa xác minh thông tin bind |
| Bind | Danh tính dịch vụ có đăng nhập được không? | Server chấp nhận thông tin xác thực | Chưa chứng minh quyền đọc entry cần thiết |
| Đọc entry mẫu | Ứng dụng có đọc được dữ liệu cần thiết không? | Truy vấn nhỏ tới DN đã biết trả về thuộc tính mong đợi | Chưa chứng minh không có quyền thừa |
| Kiểm tra ACL | Danh tính có đúng các quyền được cấp không? | Cho phép thao tác hợp lệ; từ chối thao tác ngoài phạm vi | Không thể kết luận chỉ từ một health check thành công |

**Mục tiêu học tập:** thiết kế được health check không gây tải lớn, cấu hình một danh tính chỉ có quyền đọc cần thiết, phân tích lỗi theo từng tầng và kiểm tra quyền tối thiểu trong môi trường thử nghiệm. Các ví dụ dùng Spring LDAP với `ContextSource`, `LdapTemplate` và Spring Boot Actuator; cách kiểm tra cũng áp dụng khi mã ứng dụng dùng `LdapClient` hoặc ODM.

## 2. Chọn phép thử đủ sâu nhưng ít tác động

Một LDAP probe phù hợp thường thực hiện theo thứ tự:

1. Kết nối tới endpoint LDAP qua **LDAPS** hoặc **StartTLS bắt buộc**, xác minh chứng chỉ máy chủ.
2. Bind bằng danh tính dành cho phép kiểm tra hoặc danh tính dịch vụ cần giám sát.
3. Thực hiện **một phép đọc** tới entry ổn định đã biết, ví dụ `ou=health,dc=example,dc=org`, và chỉ yêu cầu thuộc tính `ou`.
4. Trả trạng thái `UP` khi phép đọc đạt yêu cầu; trả `DOWN` và ghi nhận loại lỗi khi thất bại.

~~~mermaid
flowchart TD
    A["Health endpoint được gọi"] --> B["Mở kết nối TLS và bind"]
    B -->|Lỗi| X["DOWN: lỗi kết nối, TLS hoặc bind"]
    B -->|Thành công| C["Đọc entry probe theo DN cụ thể"]
    C -->|Entry hoặc thuộc tính không đọc được| Y["DOWN: lỗi truy vấn hoặc quyền đọc"]
    C -->|Đọc thành công| D["UP: đường đi LDAP được kiểm chứng"]
    D --> E["Kiểm tra ACL định kỳ bằng bộ thử riêng"]
~~~

Không dùng truy vấn quét toàn bộ cây, tìm kiếm không giới hạn kích thước hay ghi dữ liệu để làm health check. Probe nên chạy với thời gian chờ kết nối và đọc hữu hạn, tần suất vừa phải và DN ổn định. Ví dụ ban đầu có thể đặt timeout kết nối 2 giây, timeout đọc 3 giây rồi điều chỉnh dựa trên độ trễ thực tế và SLO của hệ thống.

**Giới hạn cần hiểu:** một probe dùng tài khoản riêng chỉ chứng minh *tài khoản đó* truy cập được LDAP. Nó không bảo đảm tài khoản chính của ứng dụng vẫn còn đủ quyền, hay thao tác cập nhật dữ liệu vẫn hoạt động. Những quyền nghiệp vụ phải được xác nhận bằng bài kiểm tra có kiểm soát phù hợp.

## 3. Thiết kế danh tính và ACL theo nguyên tắc quyền tối thiểu

Giả sử base DN là `dc=example,dc=org`, entry kiểm tra là `ou=health,dc=example,dc=org`, tài khoản là `uid=svc-ldap-probe,ou=service,dc=example,dc=org`. Quản trị viên tạo các entry này và gán ACL trên LDAP server trước khi triển khai ứng dụng.

| Đối tượng hoặc thao tác | Quyền mong muốn của `svc-ldap-probe` | Lý do |
| --- | --- | --- |
| Bind với mật khẩu riêng qua TLS | Được phép | Xác nhận đường xác thực dịch vụ |
| Đọc thuộc tính `ou` của entry `ou=health` | Được phép | Kiểm chứng truy cập ở mức ứng dụng |
| Đọc mật khẩu, khóa bí mật hay thuộc tính nhạy cảm | Không cấp | Không phục vụ mục đích giám sát |
| Liệt kê toàn bộ `ou=people` hoặc các nhánh nhạy cảm | Không cấp | Tránh lộ dữ liệu và quyền tìm kiếm quá rộng |
| Add, modify, delete, modDN ở bất kỳ nhánh nào | Không cấp | Health check chỉ cần đọc |
| Quản trị ACL hoặc thay đổi mật khẩu tài khoản khác | Không cấp | Tránh leo thang quyền |

Quy tắc ACL cụ thể khác nhau giữa OpenLDAP, Active Directory và sản phẩm LDAP khác. Với một số máy chủ, truy vấn entry bị chặn sẽ trả `insufficientAccessRights`; máy chủ khác có thể giấu entry và trả kết quả rỗng hoặc `noSuchObject`. Vì vậy **không được coi một kết quả tìm kiếm rỗng là bằng chứng đầy đủ rằng ACL đã đúng**, trừ khi đã biết chắc entry mục tiêu tồn tại.

Ngoài probe, mỗi danh tính nghiệp vụ cần một ma trận quyền riêng. Ví dụ một dịch vụ chỉ tra cứu người dùng có thể được tìm kiếm `ou=people` với bộ thuộc tính `uid`, `cn`, `mail`, nhưng không cần `userPassword`, quyền sửa hay quyền quản trị. Dịch vụ có chức năng cập nhật nhóm phải giới hạn quyền sửa ở đúng DN và thuộc tính mà chức năng đó thực sự sử dụng.

Đặt mật khẩu dịch vụ trong secret manager hoặc biến môi trường; không đưa mật khẩu vào mã nguồn, file commit, URL hay log. Dùng tài khoản riêng theo ứng dụng và môi trường để có thể thu hồi, xoay vòng và audit độc lập.

## 4. Ví dụ health check với Spring LDAP và Spring Boot Actuator

Ví dụ này giả định dự án Spring Boot 3.x, Java 17+, có `spring-ldap-core` và `spring-boot-starter-actuator` với phiên bản do Spring Boot quản lý. Probe sử dụng `LdapContextSource` riêng để không vô tình mượn quyền từ tài khoản quản trị mà ứng dụng dùng cho nghiệp vụ khác.

### 4.1. Cấu hình

~~~yaml
# application.yml
app:
  ldap:
    probe:
      url: ldaps://ldap.example.org:636
      base: dc=example,dc=org
      user-dn: uid=svc-ldap-probe,ou=service,dc=example,dc=org
      password: ${LDAP_PROBE_PASSWORD}
      entry-dn: ou=health   # DN tương đối so với base

management:
  health:
    ldap:
      enabled: false       # Tắt indicator LDAP mặc định nếu dùng probe tùy biến
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,ldapProbe
  endpoints:
    web:
      exposure:
        include: health
~~~

`ou=health` là DN **tương đối** vì `LdapContextSource` đã đặt base `dc=example,dc=org`. Entry này phải tồn tại, có thuộc tính `ou` và được cấp quyền đọc cho tài khoản probe. Trong thực tế, chứng chỉ máy chủ phải được JVM tin cậy thông qua truststore phù hợp; không tắt xác minh chứng chỉ để làm cho probe xanh.

### 4.2. Tạo ContextSource, LdapTemplate và HealthIndicator

~~~java
import java.util.Map;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;
import org.springframework.ldap.core.ContextSource;

@Configuration
public class LdapProbeConfiguration {

    @Bean("ldapProbeContextSource")
    LdapContextSource ldapProbeContextSource(
            @Value("${app.ldap.probe.url}") String url,
            @Value("${app.ldap.probe.base}") String base,
            @Value("${app.ldap.probe.user-dn}") String userDn,
            @Value("${app.ldap.probe.password}") String password) {

        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase(base);
        source.setUserDn(userDn);
        source.setPassword(password);
        source.setPooled(false);
        source.setBaseEnvironmentProperties(Map.of(
                "com.sun.jndi.ldap.connect.timeout", "2000",
                "com.sun.jndi.ldap.read.timeout", "3000"));
        return source;
    }

    @Bean("ldapProbeTemplate")
    LdapTemplate ldapProbeTemplate(
            @Qualifier("ldapProbeContextSource") ContextSource source) {
        return new LdapTemplate(source);
    }

    @Bean("ldapProbe")
    HealthIndicator ldapProbe(
            @Qualifier("ldapProbeTemplate") LdapTemplate template,
            @Value("${app.ldap.probe.entry-dn}") String entryDn) {

        return () -> {
            try {
                Boolean readable = template.lookup(
                        entryDn,
                        new String[] {"ou"},
                        (AttributesMapper<Boolean>) attrs ->
                                attrs.get("ou") != null);

                if (!Boolean.TRUE.equals(readable)) {
                    return Health.down()
                            .withDetail("reason", "probe_attribute_unavailable")
                            .build();
                }
                return Health.up().withDetail("check", "bind-and-read").build();
            } catch (Exception ex) {
                return Health.down()
                        .withDetail("reason", "ldap_probe_failed")
                        .withDetail("errorType", ex.getClass().getSimpleName())
                        .build();
            }
        };
    }
}
~~~

**Điểm cần quan sát trong đoạn mã:**

- `LdapContextSource` giữ cấu hình endpoint, base DN và danh tính bind; `LdapTemplate` quản lý vòng đời context trong thao tác `lookup`.
- `lookup` tới một DN đã biết với danh sách thuộc tính `{"ou"}` giúp tránh tìm kiếm toàn cây và tránh lấy thuộc tính không cần thiết.
- Giá trị `DOWN` không chỉ có nghĩa LDAP server đã tắt: mật khẩu sai, chứng chỉ không hợp lệ, entry probe biến mất hoặc quyền đọc bị thu hồi cũng có thể gây lỗi.
- `setPooled(false)` làm cho ví dụ không dựa vào kết nối JNDI được tái sử dụng. Nếu ứng dụng dùng connection pool, cần theo dõi cả lỗi khi mượn kết nối, kết nối cũ và cơ chế loại bỏ connection hỏng.
- Chỉ xuất loại lỗi tổng quát; không in mật khẩu, thuộc tính LDAP nhạy cảm hay stack trace qua health endpoint công khai.

Khi dùng `@Bean("ldapProbe")` kiểu `HealthIndicator`, Actuator nhận diện contributor `ldapProbe`. Sau khi readiness group được bật, kiểm tra bằng `GET /actuator/health/readiness`. Nhóm liveness chỉ nên phản ánh sức khỏe của chính tiến trình; **không** gắn sự cố LDAP tạm thời vào liveness, vì việc khởi động lại hàng loạt instance thường không sửa được lỗi LDAP ở phía ngoài.

Nếu dự án đã dùng `spring.ldap.*` và auto-configuration tạo `ContextSource` khác, bean probe ở trên cần có qualifier rõ ràng như ví dụ. Việc thêm bean thứ hai cũng có thể đòi hỏi cấu hình tường minh các injection point vốn đang dựa vào một bean duy nhất.

## 5. Phân biệt lỗi kết nối, xác thực, truy vấn và phân quyền

Có thể dùng công cụ dòng lệnh OpenLDAP để kiểm tra độc lập với mã Java. Các lệnh dưới đây lấy mật khẩu qua prompt `-W`, không đưa mật khẩu lên command line:

~~~bash
# 1. Kiểm tra bind qua LDAPS. Chứng chỉ server phải được client tin cậy.
ldapwhoami -x -H ldaps://ldap.example.org:636 \
  -D "uid=svc-ldap-probe,ou=service,dc=example,dc=org" -W

# 2. Kiểm tra đúng entry và thuộc tính được cấp quyền đọc.
ldapsearch -LLL -x -H ldaps://ldap.example.org:636 \
  -D "uid=svc-ldap-probe,ou=service,dc=example,dc=org" -W \
  -b "ou=health,dc=example,dc=org" -s base \
  "(objectClass=*)" ou

# Nếu hạ tầng dùng StartTLS thay cho LDAPS, yêu cầu TLS bắt buộc:
ldapwhoami -x -ZZ -H ldap://ldap.example.org:389 \
  -D "uid=svc-ldap-probe,ou=service,dc=example,dc=org" -W
~~~

Với OpenLDAP client, cần cấu hình CA tin cậy thích hợp (ví dụ `TLS_CACERT` trong cấu hình client); với Java, cấu hình truststore tương ứng. Không dùng `LDAPTLS_REQCERT=never` hay trust manager chấp nhận mọi chứng chỉ như một “cách khắc phục” lỗi TLS.

| Triệu chứng | Nguyên nhân thường gặp | Bước xác minh nên thực hiện |
| --- | --- | --- |
| Timeout, connection refused, không phân giải DNS | Mạng, firewall, host/cổng, LDAP server quá tải | Kiểm tra DNS, tuyến mạng, endpoint và timeout |
| Lỗi TLS/PKIX, hostname không khớp | CA chưa tin cậy, chứng chỉ hết hạn, tên máy chủ sai | Kiểm tra certificate chain, SAN, truststore và thời hạn |
| `invalidCredentials` (LDAP result code 49) | DN bind/mật khẩu sai, tài khoản khóa hoặc mật khẩu hết hạn | Xác minh DN và cơ chế quản lý secret với quản trị LDAP |
| `insufficientAccessRights` (code 50) | Thiếu quyền với entry hoặc thuộc tính | Kiểm tra ACL và DN thực tế của tài khoản bind |
| `noSuchObject`, kết quả rỗng | DN/base sai, entry đã xóa hoặc ACL che khuất entry | Đối chiếu DN tồn tại bằng tài khoản quản trị trong môi trường kiểm soát |
| `sizeLimitExceeded`, phản hồi rất chậm | Search scope, filter hoặc chỉ mục chưa phù hợp | Giới hạn base/scope/kết quả, kiểm tra filter và index |
| Chỉ probe thành công, API nghiệp vụ thất bại | Danh tính probe có quyền khác danh tính nghiệp vụ | Kiểm thử cả quyền cần thiết của danh tính nghiệp vụ |

Phần tử `errorType` của indicator là dấu vết cho điều tra, không thay thế log server, LDAP result code hoặc distributed tracing. Khi phân tích sự cố, đối chiếu timestamp, host, DN đã được rút gọn/anonymize nếu cần, loại thao tác và kết quả; bảo vệ log vì chúng có thể chứa đường dẫn thư mục hoặc thông tin tài khoản.

## 6. Kiểm tra quyền tối thiểu một cách có thể kiểm chứng

ACL cần được kiểm thử theo cả chiều **cho phép** và **từ chối**. Bài kiểm tra nên chạy trên môi trường LDAP thử nghiệm có dữ liệu giả, hoặc phạm vi kiểm tra được quản trị viên tạo riêng; tuyệt đối tránh thử ghi/xóa dữ liệu sản xuất để “xem ACL có chặn hay không”.

### 6.1. Chuẩn bị fixture và ma trận kiểm thử

Tạo hoặc xác nhận trước các entry giả lập, ví dụ:

- `ou=health,dc=example,dc=org`: entry mà tài khoản probe phải đọc được.
- `uid=acl-hidden,ou=restricted,dc=example,dc=org`: entry **chắc chắn tồn tại** nhưng probe không được đọc.
- `uid=acl-mutable,ou=fixtures,dc=example,dc=org`: entry dùng để kiểm tra từ chối ghi **chỉ trong môi trường cô lập**.

| Ca kiểm tra | Danh tính chạy | Thao tác | Kỳ vọng |
| --- | --- | --- | --- |
| P1 | `svc-ldap-probe` | Bind qua TLS | Thành công |
| P2 | `svc-ldap-probe` | Đọc `ou` tại `ou=health` | Thành công, giá trị hợp lệ |
| N1 | `svc-ldap-probe` | Đọc entry `uid=acl-hidden` | Không lộ entry/thuộc tính |
| N2 | `svc-ldap-probe` | Tìm toàn nhánh nhạy cảm | Không trả về dữ liệu ngoài phạm vi |
| N3 | `svc-ldap-probe` | Thử modify entry giả `uid=acl-mutable` | Bị từ chối, dữ liệu không đổi |
| C1 | Tài khoản quản trị của **môi trường test** | Xác minh các fixture có tồn tại | Đủ cơ sở phân biệt ACL với DN không tồn tại |

Với N1 và N2, một số server trả danh sách rỗng theo chính sách ẩn sự tồn tại của entry; server khác phát lỗi quyền truy cập. Test cần chấp nhận đúng hành vi bảo mật đã đặc tả cho server đó, nhưng **phải** xác minh bằng baseline của tài khoản test quản trị rằng fixture thực sự tồn tại. Với N3, kiểm tra lại giá trị trước/sau bằng tài khoản có quyền đọc để phát hiện thay đổi ngoài ý muốn. Không chạy N3 trên LDAP production.

### 6.2. Quy trình kiểm tra sau thay đổi ACL

1. Lập bảng DN, thuộc tính, thao tác và danh tính dự kiến được phép.
2. Xác nhận fixture bằng tài khoản test có quyền phù hợp; ghi nhận trạng thái ban đầu.
3. Chạy các ca dương tính với **chính danh tính dịch vụ** mà ứng dụng dùng.
4. Chạy các ca âm tính với fixture nhạy cảm giả, ghi nhận lỗi hoặc dữ liệu thực nhận.
5. Kiểm tra audit log phía LDAP server; đối chiếu DN đã bind với danh tính dự kiến, phát hiện tài khoản admin bị sử dụng nhầm.
6. Áp dụng cùng cấu hình ACL qua quy trình triển khai có kiểm soát; giám sát latency và lỗi sau khi thay đổi.

Khi ứng dụng phải sửa entry, hãy thêm ca **dương tính** cho đúng thuộc tính được phép sửa và ca **âm tính** cho thuộc tính bị cấm, nhưng chỉ thực hiện trên dữ liệu giả có cơ chế khôi phục. Thành công của một thao tác `read` không chứng minh quyền `write`; ngược lại, bị từ chối `write` là kết quả mong đợi của tài khoản chỉ đọc.

## 7. Giám sát, triển khai và phản ứng sự cố

Một health endpoint trả `UP` hoặc `DOWN` chưa đủ cho điều tra vận hành. Nên quan sát thêm **độ trễ probe** (p50/p95/p99), số lần lỗi theo nhóm (kết nối, TLS, bind, lookup, ACL), tỉ lệ lỗi nghiệp vụ phụ thuộc LDAP và thay đổi trạng thái qua từng endpoint/instance. Giới hạn tần suất probe và áp dụng ngưỡng cảnh báo có khoảng thời gian duy trì để giảm cảnh báo nhiễu do mạng chập chờn.

| Tình huống | Phản ứng ưu tiên |
| --- | --- |
| Readiness `DOWN` do LDAP không truy cập được | Điều tra kết nối/LDAP; tạm ngừng nhận lưu lượng yêu cầu LDAP theo chính sách của ứng dụng |
| Liveness `UP`, readiness `DOWN` | Giữ tiến trình hoạt động để có cơ hội hồi phục khi LDAP trở lại |
| Probe `UP`, đăng nhập người dùng lỗi | Kiểm tra đường xác thực của người dùng, filter tìm kiếm, nhóm và ACL tài khoản ứng dụng |
| Lỗi xuất hiện sau xoay vòng secret | Kiểm tra secret đã được cập nhật cho đúng danh tính và các instance đã nhận cấu hình mới |
| Lỗi chỉ ở một instance | So sánh DNS, truststore, secret, mạng và cấu hình của instance đó |
| Truy vấn LDAP ngày càng chậm | Kiểm tra timeout, query scope, index LDAP và tải server |

Trong triển khai Kubernetes, chỉ đưa `ldapProbe` vào **readiness** nếu sự cố LDAP khiến instance không thể phục vụ phần chức năng cốt lõi của nó. Nếu LDAP chỉ phục vụ một chức năng tùy chọn, cân nhắc theo dõi qua một health group riêng và giữ dịch vụ sẵn sàng cho phần chức năng còn lại.

Đối với connection pool, cần thêm phép kiểm tra kết nối khi mượn hoặc tái sử dụng context theo khả năng của thư viện và cấu hình đang dùng; health check mới không tự khẳng định mọi context trong pool đều khỏe. Khi gặp lỗi sporadic sau một thời gian nhàn rỗi, điều tra idle timeout của firewall/load balancer và cơ chế loại bỏ kết nối hỏng.

## 8. Bài thực hành: xác minh probe và ACL

**Bối cảnh:** một dịch vụ Spring Boot tra cứu người dùng bằng Spring LDAP. Nhóm vận hành vừa đổi chứng chỉ TLS và thu hẹp quyền của tài khoản LDAP.

**Yêu cầu:**

1. Tạo entry probe và tài khoản chỉ đọc như thiết kế ở mục 3 trong môi trường thử nghiệm.
2. Chạy `ldapwhoami` qua LDAPS và `ldapsearch` với scope `base` để xác nhận bind và phép đọc tối thiểu.
3. Bật indicator `ldapProbe`, gọi `/actuator/health/readiness` và xác minh trạng thái `UP`.
4. Trong test environment, lần lượt dùng mật khẩu sai, endpoint sai, CA chưa tin cậy và ACL chặn thuộc tính `ou`. Ghi nhận trạng thái, loại lỗi và phép thử nào phát hiện sự cố.
5. Thực hiện bộ kiểm tra N1–N3 với fixture giả lập; đối chiếu trạng thái trước/sau bằng tài khoản test quản trị.
6. Khôi phục cấu hình, xoay vòng secret đúng cách và chạy lại các ca dương tính.

**Tiêu chí hoàn thành:** probe dùng TLS đã được xác minh; chỉ đọc đúng DN/thuộc tính quy định; readiness phát hiện các lỗi có thể quan sát được; quyền ngoài phạm vi không làm lộ dữ liệu và không cho phép ghi; log và endpoint không tiết lộ secret. Có bảng kết quả gồm *ca kiểm tra, DN/thuộc tính, danh tính, kết quả mong đợi, kết quả thực tế, nhận định*.

## 9. Những sai lầm phổ biến cần tránh

- **Dùng tài khoản quản trị cho probe:** health vẫn `UP` dù tài khoản nghiệp vụ bị thu hồi quyền. Hãy kiểm tra bằng danh tính có quyền đúng với mục tiêu của phép thử.
- **Đo “health” bằng truy vấn rộng:** tải tăng và thời gian chạy biến động theo kích thước thư mục. Dùng DN cố định, danh sách thuộc tính ngắn, timeout rõ ràng.
- **Dùng một lỗi tìm kiếm rỗng làm bằng chứng ACL:** kết quả đó cũng có thể là DN sai hoặc dữ liệu đã xóa. Cần fixture được xác nhận tồn tại.
- **Cho phép TLS fallback sang kết nối không mã hóa:** kiểm tra có thể thành công nhưng đưa credential qua kênh không an toàn. Cấu hình LDAPS hoặc StartTLS bắt buộc và xác minh chứng chỉ.
- **Đưa LDAP vào liveness:** mất LDAP có thể làm toàn bộ pod khởi động lại liên tiếp. Quyết định dùng readiness hay health group riêng theo mức độ phụ thuộc thực tế.
- **Thử sửa/xóa ở production để chứng minh bị cấm:** một sai sót ACL có thể khiến thao tác thành công. Chỉ làm bài kiểm tra thay đổi trên fixture cô lập.

Kết quả vận hành đáng tin cậy đòi hỏi **hai cơ chế bổ trợ**: health check nhẹ, chạy thường xuyên để phát hiện gián đoạn truy cập; và bộ kiểm thử ACL có fixture, chạy khi thay đổi cấu hình hoặc theo lịch kiểm toán để chứng minh quyền tối thiểu được duy trì.

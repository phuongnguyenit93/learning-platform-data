# Externalized configuration và secret management trong Spring LDAP

Khi ứng dụng Spring LDAP chuyển từ máy phát triển sang môi trường kiểm thử hoặc production, địa chỉ LDAP server, base DN, tài khoản bind và các chính sách TLS thường khác nhau. Nếu tất cả các giá trị này được **hardcode trong Java** hoặc password được commit trong `application.yml`, mỗi lần đổi môi trường hoặc thay credential đều buộc ứng dụng thay mã nguồn, đồng thời tăng nguy cơ lộ bí mật.

**Externalized configuration** là đưa cấu hình ra khỏi mã ứng dụng để các môi trường có thể cấp giá trị riêng. **Secret management** là cách lưu, phân phối, sử dụng, xoay vòng và thu hồi những giá trị cần được bảo mật. Hai khái niệm liên quan chặt chẽ nhưng có mục tiêu riêng: một giá trị được truyền qua biến môi trường không vì thế mà tự động được bảo mật.

Bài học thuộc chương **Cấu hình ContextSource** của module SPRING_LDAP. Ta sẽ áp dụng hai khái niệm trên cho `LdapContextSource`, rồi kết nối với `LdapTemplate`, xác thực người dùng, TLS, pooling, xử lý lỗi và kiểm thử truy cập thư mục an toàn.

## 1. Những giá trị nào cần đưa ra khỏi mã nguồn?

Giả sử ứng dụng truy cập LDAP qua tài khoản dịch vụ:

~~~text
URL:       ldaps://ldap.example.org:636
Base DN:   dc=example,dc=org
Bind DN:   cn=app-reader,ou=services,dc=example,dc=org
Password:  <được hệ thống quản lý bí mật cung cấp>
~~~

Cấu hình này được dùng để tạo `LdapContextSource`. Nó giúp `LdapTemplate` hoặc API Spring LDAP tương ứng lấy JNDI context để thực hiện tìm kiếm và thao tác entry.

| Giá trị | Mục đích | Cách quản lý nên dùng |
| --- | --- | --- |
| `URL` / danh sách URL | Chọn LDAP endpoint | Cấu hình theo môi trường; giới hạn nơi được kết nối |
| `base DN` | Gốc để diễn giải tên LDAP tương đối | Cấu hình theo môi trường, xác minh phù hợp naming context |
| `bind DN` / username | Định danh tài khoản dịch vụ khi LDAP bind | Cấu hình vận hành có kiểm soát; có thể cần hạn chế hiển thị |
| **Bind password** | Xác thực tài khoản dịch vụ | **Secret manager hoặc kênh phân phối secret được quản trị** |
| Cấu hình CA/truststore | Xác minh chứng chỉ LDAP server | Cấu hình được quản trị; bảo vệ khóa hoặc password nếu có |
| Connect/read timeout | Giới hạn thời gian chờ | Cấu hình theo tính chất mạng và tải |
| Pooling settings | Quản lý việc tái sử dụng kết nối | Cấu hình có kiểm thử tương thích với TLS và danh tính bind |

**Phân loại dữ liệu quan trọng hơn tên tệp chứa nó.** URL và base DN không thường là secret theo nghĩa mật khẩu, nhưng có thể tiết lộ topology nội bộ. Bind DN có thể nhạy cảm về vận hành dù không chứng minh được quyền truy cập nếu thiếu password. Mật khẩu, private key và token truy cập kho bí mật phải được quản lý như secret.

Trong các ví dụ bên dưới, chỉ dùng địa chỉ và DN giả định. Không đưa mật khẩu thật vào bài học, mã nguồn, YAML được commit hay log.

## 2. Luồng dữ liệu cấu hình từ môi trường đến LDAP

~~~mermaid
flowchart TD
    A["Nguồn cấu hình<br/>profile / môi trường / config service"] --> B["Spring Environment"]
    S["Secret manager / secret mount<br/>bind password, private key"] --> B
    B --> C["Spring LDAP auto-configuration<br/>hoặc bean cấu hình"]
    C --> D["LdapContextSource"]
    D --> E["JNDI DirContext"]
    E --> F[("LDAP server qua TLS")]
    G["Business service"] --> H["LdapTemplate / LdapClient"]
    H --> D
    F --> H
~~~

Các ranh giới cần hiểu:

1. **Nguồn cấu hình:** chọn URL, base DN và tài khoản cho môi trường đang chạy. Nguồn có thể là biến môi trường, tệp cấu hình ngoài image hoặc dịch vụ quản lý cấu hình.
2. **Nguồn bí mật:** cung cấp password và các secret khác cho ứng dụng dưới danh tính workload được phép.
3. **Spring Environment:** kết hợp các nguồn thuộc tính theo quy tắc ưu tiên của Spring Boot; không tự biến thuộc tính thành bí mật hoặc bảo đảm không bị log.
4. **`LdapContextSource`:** nhận giá trị để tạo context LDAP và dùng credential của tài khoản dịch vụ khi cần bind.
5. **LDAP server:** xác thực danh tính bind, áp dụng ACL/schema, rồi mới cho phép thao tác.

**Khởi tạo thành công một bean không chứng minh password hợp lệ.** Việc mở kết nối và bind thực tế có thể diễn ra khi lấy hoặc sử dụng context, và pooling có thể thay đổi thời điểm đó. Do vậy cần thêm phép thử đọc nhỏ trên LDAP server đã cấu hình.

## 3. Cách đơn giản với Spring Boot: `spring.ldap.*`

Khi dự án dùng Spring Boot và auto-configuration Spring LDAP phù hợp, các thuộc tính thường gặp là `spring.ldap.urls`, `spring.ldap.base`, `spring.ldap.username` và `spring.ldap.password`.

Ví dụ `application.yml`:

~~~yaml
spring:
  ldap:
    urls: ${LDAP_URL:ldaps://ldap.example.org:636}
    base: ${LDAP_BASE:dc=example,dc=org}
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
~~~

Ý nghĩa của các placeholder:

| Placeholder | Giá trị do ai cung cấp? | Nếu không được cung cấp |
| --- | --- | --- |
| `${LDAP_URL:ldaps://ldap.example.org:636}` | Môi trường chạy | Dùng URL mặc định **chỉ dành cho ví dụ** |
| `${LDAP_BASE:dc=example,dc=org}` | Môi trường chạy | Dùng base mặc định **chỉ dành cho ví dụ** |
| `${LDAP_BIND_DN}` | Nguồn cấu hình triển khai | Cần được cấp trước khi tạo kết nối |
| `${LDAP_BIND_PASSWORD}` | Kênh phân phối secret | Cần được cấp; không đặt mật khẩu mặc định |

Đây là **placeholder của Spring**, không phải lệnh shell. Cơ chế phân giải và lỗi khi thiếu thuộc tính phụ thuộc cách property được dùng và cấu hình của ứng dụng; nên bổ sung kiểm tra bắt buộc, tránh khởi động với danh tính ẩn danh ngoài ý muốn.

Trong dự án thực, tốt hơn là **không dùng mặc định URL/base dành cho production** nếu điều đó có thể khiến một ứng dụng ở môi trường sai vô tình kết nối đến directory khác. Có thể bỏ phần `:giá trị-mặc-định` để yêu cầu mỗi môi trường cấp rõ ràng cả URL và base.

### Biến môi trường tương ứng

Spring Boot có cơ chế *relaxed binding*: một số thuộc tính `spring.ldap.*` có thể được cấp trực tiếp bằng biến môi trường theo quy tắc đặt tên.

~~~text
SPRING_LDAP_URLS       -> spring.ldap.urls
SPRING_LDAP_BASE       -> spring.ldap.base
SPRING_LDAP_USERNAME   -> spring.ldap.username
SPRING_LDAP_PASSWORD   -> spring.ldap.password
~~~

Cách này có thể tránh việc khai báo placeholder trong YAML. Tuy nhiên, **mật khẩu nằm trong biến môi trường vẫn là secret cần bảo vệ**: biến có thể bị lộ qua cấu hình orchestration, công cụ chẩn đoán, dump tiến trình, log hoặc quyền kiểm tra môi trường chạy.

Không truyền password qua tham số lệnh `--spring.ldap.password=...` nếu giá trị đó có thể xuất hiện trong process list hoặc shell history. Đừng đặt secret trực tiếp trong lệnh build image, các tùy chọn build hoặc Dockerfile.

### Chọn một hướng cấu hình rõ ràng

Với Boot auto-configuration, trước tiên xem các bean `ContextSource` và `LdapTemplate` thực tế được tạo ra. Nếu tự đăng ký `LdapContextSource` bean khác, hành vi auto-configuration có thể thay đổi theo điều kiện của phiên bản Spring Boot. Tránh cấu hình nhiều nguồn mà service không biết đang dùng bean nào.

## 4. Tách cấu hình theo môi trường

Các thuộc tính **không bí mật** thường được tách theo môi trường mà không cần thay code:

~~~yaml
# application.yml -- cấu hình chung được phép commit
spring:
  ldap:
    urls: ${LDAP_URL}
    base: ${LDAP_BASE}
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
~~~

Ví dụ các môi trường cấp dữ liệu khác nhau:

| Môi trường | LDAP URL | Base DN | Danh tính bind |
| --- | --- | --- | --- |
| Local | `ldaps://ldap.dev.example.org:636` | `dc=dev,dc=example,dc=org` | Tài khoản lab chỉ đọc |
| Staging | `ldaps://ldap.stage.example.org:636` | `dc=stage,dc=example,dc=org` | Tài khoản staging |
| Production | `ldaps://ldap.example.org:636` | `dc=example,dc=org` | Tài khoản production quyền tối thiểu |

Mỗi môi trường phải có **secret riêng**. Không dùng tài khoản production trong test vì dễ dẫn đến tác động nhầm vào thư mục thật và khiến phạm vi lộ bí mật rộng hơn.

Spring Boot hỗ trợ profile, tệp cấu hình ngoài ứng dụng, biến môi trường và các nguồn cấu hình khác. Một giá trị có thể xuất hiện ở nhiều nguồn; quy tắc ưu tiên phụ thuộc loại nguồn và cách cấu hình được nạp. Vì thế, khi điều tra, hãy xác định **giá trị cuối cùng thực sự được dùng** và nguồn cấp của nó, nhưng tránh in password ra log hoặc endpoint chẩn đoán.

Chọn rõ quy tắc môi trường ngay tại khâu triển khai: app production chỉ được truy cập LDAP production đã phê duyệt. Externalization giúp thay giá trị linh hoạt, nhưng **không thay cho kiểm soát quyền và kiểm soát endpoint**.

## 5. Secret management: lưu và phân phối mật khẩu bind

Một hệ thống quản lý secret giải quyết vòng đời của bí mật:

~~~mermaid
flowchart LR
    A["Tạo credential"] --> B["Lưu trong secret store"]
    B --> C["Cấp cho workload được phép"]
    C --> D["LdapContextSource sử dụng khi bind"]
    D --> E["Rotation / làm mới kết nối"]
    E --> F["Thu hồi credential cũ"]
    F --> G["Audit và kiểm tra"]
~~~

### Những yêu cầu thực tế

- **Lưu trữ:** secret được bảo vệ bởi chính sách truy cập và cơ chế mã hóa phù hợp; không lưu mật khẩu dạng rõ trong Git.
- **Truy cập:** danh tính máy chạy ứng dụng (*workload identity* hoặc cơ chế tương đương) chỉ được đọc đúng secret cần thiết.
- **Truyền tải:** tải secret qua kết nối bảo mật, tránh truyền qua kênh không đáng tin cậy.
- **Sử dụng:** cung cấp giá trị cho `LdapContextSource` qua property hoặc API an toàn; không phát tán password qua nhiều lớp nghiệp vụ.
- **Rotation:** có khả năng đổi password, cập nhật cấu hình và làm mới các LDAP connection đang dùng.
- **Audit:** ghi nhận ai có quyền đọc/thay secret và khi nào, nhưng không lưu nội dung secret trong log.

Một số nền tảng cung cấp dịch vụ quản lý secret chuyên dụng, ví dụ HashiCorp Vault, AWS Secrets Manager, Azure Key Vault hoặc Google Secret Manager. Cơ chế tích hợp cụ thể phụ thuộc môi trường chạy và thư viện được chọn. Không cần gắn mã nghiệp vụ Spring LDAP với tên nhà cung cấp nếu ứng dụng chỉ cần đọc một giá trị cấu hình.

### Secret không có nghĩa là mật khẩu đã được băm

LDAP server xác thực simple bind bằng password; `LdapContextSource` phải có credential mà client có thể dùng để xác thực. **Hash một chiều password của tài khoản dịch vụ rồi truyền giá trị hash như mật khẩu không phải giải pháp chung**: server thường kỳ vọng password tương ứng với credential thật, không phải một chuỗi hash do ứng dụng tự tạo. Kho secret thông thường bảo vệ và chỉ cấp giá trị cho workload được phép, thay vì biến password thành hash không sử dụng được.

### Thông tin nhạy cảm ngoài bind password

Nếu dùng mTLS hoặc cấu hình truststore chứa khóa, **private key** và password bảo vệ key store cũng cần được quản lý như secret. Chứng chỉ CA công khai thường không phải secret, nhưng phải bảo đảm nguồn cấp đáng tin cậy để tránh đưa CA độc hại vào truststore.

## 6. Phân phối secret bằng biến môi trường, tệp mount và secret manager

Có ba cách phổ biến. Không có cách nào tự động an toàn nếu thiếu phân quyền và vận hành đúng.

| Cơ chế | Cách ứng dụng nhận giá trị | Lưu ý |
| --- | --- | --- |
| **Environment variable** | `LDAP_BIND_PASSWORD` được cấp khi khởi chạy | Dễ tích hợp; hạn chế quyền xem environment và công cụ debug |
| **Mounted secret file** | Runtime gắn tệp bí mật chỉ workload được đọc | Phải hạn chế quyền tệp và xác định lúc đọc/làm mới giá trị |
| **Secret manager integration** | Workload có danh tính được phép lấy secret theo API hoặc qua agent | Cần policy, audit, kết nối bảo mật và chiến lược cache/rotation |

Ví dụ với container orchestration, Kubernetes Secret có thể được đưa vào container dưới dạng environment hoặc volume. **Kubernetes Secret không mặc nhiên đồng nghĩa dữ liệu được mã hóa end-to-end hay hoàn toàn vô hình với mọi quản trị viên**; cần RBAC, kiểm soát truy cập API và chính sách mã hóa lưu trữ thích hợp.

Tránh in secret ra output triển khai, ghi vào command line hoặc đặt dưới thư mục được ứng dụng web phục vụ công khai.

### Sử dụng Spring Boot config tree

Spring Boot hỗ trợ nhập các tệp một-giá-trị thành thuộc tính cấu hình qua `configtree:` trong những phiên bản có tính năng này. Giả sử runtime mount:

~~~text
/run/secrets/ldap/
└── spring.ldap.password
~~~

Trong đó **nội dung** của tệp `spring.ldap.password` là mật khẩu được cấp an toàn, không đưa ra ví dụ giá trị thật.

Cấu hình:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/ldap/"
  ldap:
    urls: ${LDAP_URL}
    base: ${LDAP_BASE}
    username: ${LDAP_BIND_DN}
    # spring.ldap.password được lấy từ file secret đã import.
~~~

Khi thư mục import bắt buộc bị thiếu, việc **không** thêm tiền tố `optional:` giúp phát hiện lỗi cấu hình sớm, theo cơ chế Config Data của Spring Boot. Vẫn cần kiểm tra tệp secret có mặt và nội dung đúng; một thư mục tồn tại không bảo đảm credential hợp lệ.

Một tệp secret được cập nhật ở runtime **không đồng nghĩa `LdapContextSource` và kết nối đang hoạt động tự đọc lại giá trị mới**. Cách ứng dụng nạp lại property, tạo bean mới hoặc tái khởi động/pool lại phải được thiết kế riêng.

## 7. Khai báo `LdapContextSource` thủ công với secret bên ngoài

Nếu không sử dụng Boot LDAP auto-configuration hoặc cần kiểm soát cách tạo bean, khai báo `LdapContextSource` trực tiếp:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class DirectoryLdapConfiguration {

    @Bean
    public LdapContextSource ldapContextSource(
            @Value("${app.ldap.url}") String url,
            @Value("${app.ldap.base}") String base,
            @Value("${app.ldap.bind-dn}") String bindDn,
            @Value("${app.ldap.bind-password}") String bindPassword) {

        if (url.isBlank() || base.isBlank()
                || bindDn.isBlank() || bindPassword.isBlank()) {
            throw new IllegalStateException(
                    "Missing required LDAP connection configuration");
        }

        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase(base);
        source.setUserDn(bindDn);
        source.setPassword(bindPassword);
        return source;
    }

    @Bean
    public LdapTemplate ldapTemplate(ContextSource contextSource) {
        return new LdapTemplate(contextSource);
    }
}
~~~

Cấu hình đi kèm:

~~~yaml
app:
  ldap:
    url: ${LDAP_URL}
    base: ${LDAP_BASE}
    bind-dn: ${LDAP_BIND_DN}
    bind-password: ${LDAP_BIND_PASSWORD}
~~~

Trong ví dụ này:

1. `@Value` đọc thuộc tính từ nguồn mà Spring Environment đã hợp nhất.
2. Validation đơn giản ngăn các giá trị rỗng được dùng ngoài ý muốn. Trong sản phẩm thật, còn cần kiểm tra hostname/URL, định dạng DN, giới hạn tên và chính sách endpoint.
3. `setUserDn(...)` nhận **danh tính bind**, thường là DN đầy đủ; nó không phải search base.
4. `setPassword(...)` truyền credential vào cấu hình context. Không ghi giá trị này vào exception hoặc log.
5. Spring quản lý lifecycle của bean; `LdapTemplate` nhận cùng `ContextSource` cho các thao tác LDAP.

**Chỉ chọn một đường cấu hình rõ ràng:** dùng `spring.ldap.*` auto-configuration hoặc bean thủ công với `app.ldap.*`. Khi có nhiều LDAP server và nhiều bean `ContextSource`, đặt tên/qualifier rõ ràng để tránh service truy vấn nhầm môi trường.

Khi dùng mã `@Value` như trên, property thiếu thường gây lỗi khi tạo bean; đoạn validation xử lý trường hợp property có mặt nhưng rỗng. Nó vẫn **không** kiểm tra được rằng password đúng hay LDAP server có thể kết nối.

## 8. Lưu ý về base DN, quyền và identity

Externalized configuration tạo điều kiện thay `base DN` theo môi trường, nhưng base DN ảnh hưởng trực tiếp cách Spring LDAP phân giải tên.

Giả sử:

~~~text
ContextSource.base = dc=example,dc=org
Query search base = ou=people

Search base hiệu lực:
ou=people,dc=example,dc=org
~~~

Nếu một môi trường khác cấu hình `ContextSource.base=ou=people,dc=example,dc=org`, query với `.base("ou=people")` có thể bị lặp `ou=people` và tìm sai nhánh.

Vì vậy, khi triển khai, phải kiểm thử **cặp context base + query base** trên DIT thật. Không coi base là một biến tùy ý có thể thay mà không ảnh hưởng code.

Tương tự, đổi `LDAP_BIND_DN` có thể đổi danh tính và ACL thực tế. Một service bind mới có thể truy cập ít hoặc nhiều thuộc tính hơn, khiến cùng một truy vấn trả kết quả khác. **Chỉ cần bảo vệ password là chưa đủ**: phải kiểm soát ai được sửa URL, base, bind DN và policy tương ứng.

## 9. Rotation: thay bind password mà vẫn giữ dịch vụ ổn định

**Rotation** là thay credential cũ bằng credential mới theo quy trình có kiểm soát. Với LDAP, secret mới trong kho chưa có nghĩa kết nối trong ứng dụng đã dùng được nó.

Quy trình mẫu:

~~~mermaid
flowchart TD
    A["Chuẩn bị credential mới theo chính sách LDAP"] --> B["Cập nhật secret store và version"]
    B --> C["Đưa giá trị mới đến workload"]
    C --> D["Làm mới ContextSource / context pool / phiên chạy"]
    D --> E{"Read probe qua TLS thành công?"}
    E -->|Có| F["Hoàn tất cutover, thu hồi credential cũ theo kế hoạch"]
    E -->|Không| G["Điều tra, kiểm soát rollback theo chính sách"]
~~~

Các bước thực tế cần thỏa điều kiện của LDAP server:

1. **Chuẩn bị:** xác định tài khoản dịch vụ, phạm vi ảnh hưởng, môi trường, nơi đang dùng secret và cách khôi phục khi có lỗi.
2. **Đổi phía server và secret store:** nếu hệ thống hỗ trợ giai đoạn chồng lấn bằng hai tài khoản/credential thì có thể chuyển dần; nếu server chỉ cho một password tại một thời điểm, cần kế hoạch cutover nhanh và xử lý gián đoạn có thể xảy ra.
3. **Cấp secret mới:** workload nhận đúng version hoặc giá trị mới qua cơ chế đã chọn.
4. **Làm mới runtime:** khởi động lại hoặc tái tạo bean/context/pool theo thiết kế; không giả định thay biến môi trường hoặc file mount đủ để một bean đã tạo tự nhận giá trị.
5. **Kiểm tra:** chạy phép đọc nhỏ có giới hạn để xác minh endpoint, TLS, credential, base DN và ACL.
6. **Thu hồi và quan sát:** vô hiệu hóa credential cũ khi an toàn, giám sát lỗi bind, timeout và sự tăng bất thường của connection.

Kết nối đã bind bằng credential cũ có thể còn hoạt động hoặc bị server ngắt khi password thay đổi, tùy server và cấu hình. Không dựa vào việc một connection còn tìm kiếm được để suy ra mọi kết nối đã dùng secret mới.

### Pooling làm rotation phức tạp hơn

Với pooling, thao tác mới có thể tái sử dụng connection đã tồn tại thay vì thực hiện bind mới. Cần hiểu:

- Pool có quản lý kết nối theo danh tính và credential như thế nào.
- Khi thay secret, connection cũ được invalidate/đóng ra sao.
- Connection mới có nhận đúng secret version không.
- StartTLS và pool có tương thích với nhau không.
- Giới hạn số kết nối và timeout có tránh tạo tải đột biến khi nhiều instance cùng khởi động lại không.

Không nên giải quyết rotation bằng cách sửa mật khẩu trong một biến global dùng chung nhưng giữ nguyên toàn bộ pool không được kiểm soát.

## 10. Những gì tuyệt đối không nên tiết lộ

| Vị trí | Rủi ro | Biện pháp |
| --- | --- | --- |
| Git repository / pull request | Secret tồn tại lâu trong lịch sử commit | Dùng placeholder và secret store; nếu lộ phải rotate, không chỉ xóa commit mới nhất |
| CI/CD log | Giá trị có thể xuất hiện trong command output | Mask, giới hạn quyền log và tránh in environment |
| Command line / container build | Secret xuất hiện trong history, process args hoặc image layer | Cấp secret ở runtime qua kênh thích hợp |
| Exception và debug JNDI | Thông số cấu hình hoặc credential bị in ra | Không log password, token, toàn bộ environment JNDI |
| Endpoint health, actuator, diagnostics | Người khác có thể xem thông tin cấu hình | Bảo vệ endpoint, kiểm tra sanitization và chỉ trả trạng thái cần thiết |
| Backup và snapshot | Secret lưu lại ngoài secret store | Áp dụng mã hóa, chính sách giữ/xóa và phân quyền sao lưu |
| Test fixture | Password thật vô tình đi vào pipeline | Dùng credential riêng cho lab hoặc dữ liệu giả |

Nếu secret đã bị đưa vào Git, việc xóa dòng khỏi phiên bản mới **không đủ để coi secret an toàn**: lịch sử, fork, cache và log có thể đã chứa giá trị. Biện pháp xử lý là thu hồi hoặc rotate credential theo quy trình sự cố, rồi đánh giá phạm vi lộ.

## 11. Kiểm tra cấu hình mà không làm lộ secret

Khi ứng dụng khởi động, nên kiểm tra các nhóm điều kiện:

| Nhóm kiểm tra | Ví dụ | Điều cần tránh |
| --- | --- | --- |
| Thuộc tính bắt buộc | URL, base, bind DN/password không rỗng | In password để chứng minh đã nạp |
| Endpoint | Hostname, port, TLS handshake và chứng chỉ hợp lệ | Tắt certificate verification khi gặp lỗi |
| Xác thực | Service bind thành công | Dùng tài khoản quản trị làm mặc định |
| Phạm vi truy vấn | Search base và scope đúng OU | Search toàn bộ directory chỉ để thử kết nối |
| Quyền | Tài khoản có thể đọc đúng entry/attribute cần thiết | Tăng quyền ACL không có cơ sở |
| Rotation | Instance mới dùng được secret version hiện hành | Giả định sửa file mount tự cập nhật connection pool |

Một phép thử đọc nhỏ bằng `LdapTemplate`:

~~~java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;

public class DirectoryReadProbe {
    private final LdapTemplate ldapTemplate;

    public DirectoryReadProbe(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findKnownUser() {
        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is("lab-user");

        return ldapTemplate.search(
                query,
                (AttributesMapper<String>) attributes ->
                        (String) attributes.get("cn").get());
    }
}
~~~

Giả sử `ContextSource.base=dc=example,dc=org` và entry thử nghiệm `uid=lab-user,ou=people,dc=example,dc=org` đã tồn tại, tài khoản dịch vụ có quyền đọc `cn`. Truy vấn này kiểm tra nhiều lớp: cấu hình URL/TLS, bind credential, base DN, filter, ACL và mapping.

**Trả về danh sách rỗng không mặc nhiên là lỗi password.** Có thể entry không tồn tại, OU sai, search scope không đủ sâu hoặc ACL che dữ liệu. Phải đối chiếu entry kiểm thử được biết trước và kiểm tra phản hồi LDAP.

Không dùng việc `LdapContextSource` bean được khởi tạo để khẳng định kết nối và bind đã thành công. Khi dùng readiness/health check, đặt timeout và tần suất hợp lý để không gây thêm tải lên LDAP server.

## 12. Phân biệt lỗi cấu hình, xác thực và truy vấn

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Thiếu property hoặc startup fail | Source config thiếu hoặc tên biến sai | Kiểm tra binding, profile và secret mount |
| Kết nối không thành công | URL, DNS, firewall, port, timeout | Kiểm tra endpoint và mạng |
| TLS handshake lỗi | CA/truststore, hostname, chế độ TLS | Xác minh certificate chain và truststore |
| `invalidCredentials (49)` | Bind DN/password sai, secret version cũ, account policy | Kiểm tra danh tính và rotation, không log password |
| `insufficientAccessRights (50)` | Credential đúng nhưng ACL không cho phép | Kiểm tra scope quyền của tài khoản |
| `noSuchObject (32)` | Base DN/query base sai hoặc lặp suffix | Xác định DN hiệu lực |
| Query có 0 kết quả | Filter/scope/OU không khớp | Dùng known entry và kiểm tra search |
| Ghi entry thất bại do schema | Thiếu MUST attribute/objectClass sai | Kiểm tra schema và code mapping |
| Lỗi ngắt quãng sau rotation | Nhiều instance/connection còn dùng secret cũ | Kiểm tra refresh và recycle pool |

Nguyên nhân và thông điệp chi tiết phụ thuộc LDAP server. Spring LDAP thường chuyển exception từ JNDI thành các loại exception riêng. Khi điều tra, lưu **loại lỗi, thao tác, môi trường và correlation ID** với phạm vi phù hợp; không xuất password hay toàn bộ cấu hình.

## 13. Bài thực hành: cấu hình hai môi trường và thay secret

Giả sử có hai LDAP server giả định:

~~~text
DEV:
  URL:       ldaps://ldap.dev.example.org:636
  Base:      dc=dev,dc=example,dc=org
  Bind DN:   cn=reader,ou=services,dc=dev,dc=example,dc=org

STAGING:
  URL:       ldaps://ldap.stage.example.org:636
  Base:      dc=stage,dc=example,dc=org
  Bind DN:   cn=reader,ou=services,dc=stage,dc=example,dc=org
~~~

Yêu cầu bài tập:

1. Viết `application.yml` dùng `spring.ldap.*` và placeholder môi trường, **không có password thật**.
2. Liệt kê giá trị nào là cấu hình thông thường, giá trị nào bắt buộc lấy từ secret store.
3. Nếu `ContextSource.base=dc=dev,dc=example,dc=org`, query nên dùng search base gì để tìm dưới `ou=people,dc=dev,dc=example,dc=org`?
4. Thiết kế phép thử đơn giản để phát hiện sai URL/TLS/bind/ACL trước khi mở chức năng tìm nhân viên.
5. Khi password tài khoản `reader` được thay đổi, tại sao không đủ nếu chỉ cập nhật biến môi trường trên nền tảng chạy?
6. Nếu secret bị commit nhầm trong một pull request, phải thực hiện những hành động gì?

### Đáp án gợi ý

**1. Cấu hình:**

~~~yaml
spring:
  ldap:
    urls: ${LDAP_URL}
    base: ${LDAP_BASE}
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
~~~

**2.** URL và base là cấu hình theo môi trường; bind DN là thông tin định danh vận hành cần kiểm soát; bind password bắt buộc là secret. Nếu có private key TLS hoặc password của keystore, chúng cũng là secret.

**3.** Search base tương đối là `ou=people`. Không lặp thêm suffix `dc=dev,dc=example,dc=org` đã nằm trong ContextSource base.

**4.** Dùng tài khoản chỉ đọc trên LDAPS với chứng chỉ được xác minh, tìm một entry lab chắc chắn tồn tại trong OU và yêu cầu thuộc tính được phép đọc. Đánh giá riêng lỗi mạng/TLS, bind và search/ACL.

**5.** Bean `LdapContextSource` hoặc connection pool có thể đã giữ password và các kết nối cũ. Cần cơ chế reload/recreate hoặc rolling restart cùng kiểm tra lại kết nối, tùy thiết kế ứng dụng.

**6.** Thu hồi/rotate credential theo quy trình sự cố, rà soát quyền và log truy cập, ngăn secret tiếp tục xuất hiện, rồi xử lý lịch sử/các bản sao ở phạm vi có thể. Chỉ xóa dòng trong commit mới không bảo đảm secret đã hết lộ.

### Câu hỏi tự kiểm tra

| Nhận định | Đúng hay sai? Vì sao? |
| --- | --- |
| “Password trong biến môi trường là an toàn tuyệt đối.” | **Sai.** Vẫn cần kiểm soát quyền đọc và khả năng lộ qua runtime/log. |
| “Cập nhật file Secret mount sẽ khiến mọi LDAP connection dùng password mới.” | **Sai.** Cần quy trình refresh context và pool. |
| “Base DN là một secret phải giấu như password.” | **Không mặc nhiên.** Thường là cấu hình, nhưng có thể tiết lộ topology và cần hạn chế phù hợp. |
| “Service bind thành công nghĩa là có quyền sửa mọi entry.” | **Sai.** LDAP ACL kiểm soát từng thao tác. |
| “Chỉ cần ứng dụng khởi động là chứng minh cấu hình LDAP đúng.” | **Sai.** Cần kiểm tra bind và thao tác truy cập thật. |
| “Externalization giải quyết được chuyện password bị hardcode.” | **Đúng một phần.** Cần phân phối secret, quyền, rotation và tránh lộ mới thực sự an toàn. |

## 14. Ghi nhớ khi triển khai

- **Externalized configuration** giúp thay URL, base DN và danh tính bind giữa các môi trường mà không sửa code. **Secret management** bảo vệ credential và quản lý toàn bộ vòng đời của nó.
- Với Spring Boot, có thể dùng `spring.ldap.urls`, `spring.ldap.base`, `spring.ldap.username` và `spring.ldap.password` từ property sources được quản trị. Với cấu hình bean thủ công, truyền những giá trị tương ứng vào `LdapContextSource`.
- **Không hardcode password hoặc để giá trị thật trong Git.** Ưu tiên secret store, workload identity và đường phân phối an toàn; environment variable hoặc secret mount vẫn cần phân quyền.
- **Credential rotation cần làm mới runtime và connection pool.** Thay secret trong kho không tự khiến context cũ sử dụng credential mới.
- **Giữ URL, base DN, TLS và ACL đúng môi trường.** Query base tương đối với ContextSource base; filter chứa input phải được escape qua builder.
- **Kiểm thử trên thư mục lab** với một entry đã biết, quyền tối thiểu và LDAPS/StartTLS đã xác minh chứng chỉ. Không dùng password hoặc tài khoản quản trị production trong test.

### Tài liệu tham khảo

- [Spring LDAP Reference Documentation](https://docs.spring.io/spring-ldap/reference/)
- [Spring Boot Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot Config Data và config tree](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files.configtree)
- [Spring Boot LDAP Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html)
- [RFC 4513 – LDAP Authentication Methods and Security Mechanisms](https://www.rfc-editor.org/rfc/rfc4513)

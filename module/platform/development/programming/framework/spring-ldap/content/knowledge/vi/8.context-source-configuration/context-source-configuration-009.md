# Kiểm tra kết nối và cấu hình sai ngay khi khởi động

Một dịch vụ Spring có thể khởi động thành công dù cấu hình LDAP chứa URL sai, base DN không tồn tại, mật khẩu tài khoản dịch vụ đã hết hạn hoặc chứng chỉ TLS không được tin cậy. Khi ứng dụng chỉ tạo bean `LdapContextSource` mà chưa thực hiện thao tác LDAP, nhiều lỗi **chưa bị phát hiện**. Chúng chỉ xuất hiện khi người dùng đăng nhập hoặc khi API đầu tiên gọi `LdapTemplate.search(...)`.

Bài thuộc chương **Cấu hình ContextSource** của module **SPRING_LDAP**. Mục tiêu là xác định những gì có thể kiểm tra **ngay tại thời điểm khởi động**, những gì cần **kết nối thực tế** mới xác minh được, và cách đưa kết quả vào chính sách khởi động hoặc readiness. Các ví dụ dùng `LdapContextSource`, `LdapTemplate`, JNDI và Spring Boot; nguyên tắc cũng áp dụng khi truy cập entry qua `LdapClient` hay LDAP ODM.

> **Nguyên tắc chính:** Cấu hình bean hợp lệ không đồng nghĩa LDAP đã sẵn sàng. Muốn phát hiện lỗi mạng, TLS, bind hoặc quyền đọc từ đầu, phải thực hiện **một thao tác LDAP thực** với danh tính và base mà ứng dụng sẽ dùng.

## 1. Những lỗi cần phát hiện trước khi phục vụ yêu cầu

Giả sử API nhân sự cần tìm người dùng dưới `ou=people,dc=example,dc=org`. Nó sử dụng tài khoản dịch vụ để tìm kiếm, sau đó có thể dùng một luồng authentication riêng để xác minh mật khẩu người dùng.

| Sai sót | Dấu hiệu thường gặp | Bước kiểm tra phù hợp |
| --- | --- | --- |
| Thiếu URL, base DN hoặc bind DN | Bean thiếu tham số, cấu hình rỗng | **Kiểm tra cấu hình cục bộ** trước khi tạo `ContextSource` |
| URL dùng scheme không được phép | Vô tình dùng `ldap://` thay `ldaps://` theo chính sách | **Kiểm tra URL** bằng parser/allowlist |
| Base DN sai cú pháp | `dc=example,dc=` hoặc tên không thể parse | **Parse DN** bằng `LdapName` |
| Host sai, DNS không phân giải, port không mở | Không tạo được kết nối | **Thử kết nối** với timeout |
| Chứng chỉ hết hạn/không được tin cậy hoặc hostname sai | TLS handshake/kiểm tra danh tính thất bại | **Kết nối LDAPS/StartTLS và xác minh TLS** |
| Bind DN hoặc mật khẩu sai, tài khoản bị khóa | LDAP từ chối xác thực tài khoản dịch vụ | **Thao tác thực bằng context có bind identity** |
| Base/OU không tồn tại | `NameNotFoundException` khi tra cứu | **Lookup một entry được biết phải có** |
| Tài khoản có thể bind nhưng không được đọc OU | Bị từ chối quyền hoặc thiếu thuộc tính | **Lookup/search với quyền đọc mà ứng dụng cần** |
| Filter, schema hoặc tên thuộc tính không phù hợp | Search không khớp, thiếu thuộc tính | **Kiểm tra một truy vấn đại diện**, test tích hợp riêng |
| Pool cũ, mạng thay đổi sau startup | Lỗi xuất hiện khi ứng dụng đang chạy | **Readiness/health và theo dõi runtime**, không chỉ startup probe |

**Chia thành hai lớp kiểm tra** giúp tiết kiệm thời gian và tránh kết luận sai: kiểm tra cục bộ phát hiện lỗi cấu hình rõ ràng mà không cần mạng; kiểm tra từ xa xác minh việc dịch vụ LDAP thực sự xử lý yêu cầu.

## 2. Điều gì diễn ra khi `LdapContextSource` được khởi tạo?

`ContextSource` là nguồn cấp LDAP context. Một triển khai phổ biến là `org.springframework.ldap.core.support.LdapContextSource`, có các cấu hình như:

~~~text
directory.url           = ldaps://directory.example.org:636
directory.base          = dc=example,dc=org
directory.bind-dn       = cn=app-reader,ou=service,dc=example,dc=org
directory.bind-password = [lấy từ nơi lưu secret]
~~~

Luồng khái niệm:

~~~mermaid
flowchart TD
    A["Nạp cấu hình ứng dụng"] --> B["Kiểm tra cấu hình cục bộ"]
    B --> C["Tạo và khởi tạo LdapContextSource"]
    C --> D{"Thực hiện LDAP probe?"}
    D -- "Không" --> E["Có thể khởi động dù LDAP không truy cập được"]
    D -- "Có" --> F["TLS + bind + lookup/search"]
    F --> G{"Thao tác đại diện thành công?"}
    G -- "Có" --> H["Đạt điều kiện LDAP ban đầu"]
    G -- "Không" --> I["Báo lỗi startup hoặc readiness theo chính sách"]
~~~

Spring quản lý vòng đời bean và gọi các bước khởi tạo thích hợp, trong đó có phương thức `afterPropertiesSet()` của các bean liên quan. **Không giả định chỉ cần gọi `afterPropertiesSet()` là đã xác minh được kết nối, bind, TLS và quyền đọc LDAP**. Việc khởi tạo nguồn context chủ yếu chuẩn bị các thiết lập. Một số provider có thể trì hoãn kết nối vật lý cho đến lúc thực hiện thao tác.

Ngay cả lệnh lấy `DirContext` cũng cần được đánh giá thận trọng: tùy provider, thời điểm tạo kết nối và thực hiện bind có thể khác nhau. Muốn một phép kiểm tra rõ ràng, hãy **đọc một entry/thuộc tính đã biết qua LDAP** để bắt buộc diễn ra tương tác thực với server.

### 2.1. Ba mức kiểm tra thường bị trộn lẫn

| Mức | Thực hiện gì? | Điều có thể kết luận |
| --- | --- | --- |
| **Local validation** | Kiểm tra property, URL, DN, secret không rỗng | Cấu hình có hình thức hợp lệ theo chính sách của ứng dụng |
| **Connectivity và authentication probe** | Kết nối, TLS, bind bằng tài khoản cấu hình | Server có thể được truy cập và chấp nhận danh tính trong lần kiểm tra |
| **Functional LDAP probe** | Lookup hoặc search một entry/thuộc tính bắt buộc | Đường đi thực tế gồm base, quyền và API đọc có thể hoạt động lúc kiểm tra |

Một kết quả probe thành công **không chứng minh** tất cả dữ liệu, schema, ACL của mọi OU hay mọi máy chủ replica đều đúng. Nó cũng không bảo đảm dịch vụ sẽ còn sẵn sàng sau một giờ. Vì vậy cần kết hợp với kiểm thử tích hợp và theo dõi vận hành.

## 3. Kiểm tra cấu hình cục bộ trước khi tạo kết nối

Hãy kiểm tra trước những điều không cần LDAP server:

1. **Thuộc tính bắt buộc** phải tồn tại, không rỗng: URL, base DN, bind DN, bí mật tương ứng nếu ứng dụng dùng bind có mật khẩu.
2. **Chính sách giao thức:** yêu cầu `ldaps://` hoặc StartTLS được thiết lập đúng; không tự động hạ cấp xuống kết nối không mã hóa.
3. **Cú pháp URL:** có scheme, host hợp lệ; từ chối URL chứa thông tin đăng nhập nhúng, query/fragment không được hỗ trợ trong cấu hình đang dùng.
4. **Cú pháp DN:** base và bind DN phải parse được theo quy tắc LDAP DN; không tách thủ công bằng dấu phẩy.
5. **Giới hạn thời gian:** giá trị timeout hợp lệ, không âm; các thông số của provider thường tính bằng mili giây.
6. **Ranh giới cấu hình:** môi trường test, staging và production phải có endpoint/base rõ ràng; không âm thầm chuyển sang server khác nếu cấu hình lỗi.

### 3.1. Ví dụ cấu hình Spring dùng `Environment`

Đoạn Java sau tập trung vào **kiểm tra trước khi tạo bean** và thiết lập timeout kết nối/đọc cho JNDI LDAP provider thông dụng của JDK.

~~~java
import java.net.URI;
import java.util.HashMap;
import java.util.Map;

import javax.naming.InvalidNameException;
import javax.naming.ldap.LdapName;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class LdapConfiguration {

    @Bean
    public LdapContextSource ldapContextSource(Environment environment)
            throws InvalidNameException {
        String url = required(environment.getProperty("directory.url"), "directory.url");
        String base = required(environment.getProperty("directory.base"), "directory.base");
        String bindDn = required(environment.getProperty("directory.bind-dn"), "directory.bind-dn");
        String password = required(
                environment.getProperty("directory.bind-password"),
                "directory.bind-password");

        URI parsed = URI.create(url);
        if (!"ldaps".equalsIgnoreCase(parsed.getScheme())
                || parsed.getHost() == null
                || parsed.getRawUserInfo() != null
                || parsed.getRawQuery() != null
                || parsed.getRawFragment() != null) {
            throw new IllegalArgumentException("LDAP URL không hợp lệ theo chính sách");
        }

        // Parse để bắt lỗi cú pháp; chưa kiểm tra entry có tồn tại.
        new LdapName(base);
        new LdapName(bindDn);

        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase(base);
        source.setUserDn(bindDn);
        source.setPassword(password);

        Map<String, Object> options = new HashMap<>();
        options.put("com.sun.jndi.ldap.connect.timeout", "2000");
        options.put("com.sun.jndi.ldap.read.timeout", "4000");
        source.setBaseEnvironmentProperties(options);
        return source;
    }

    @Bean
    public LdapTemplate ldapTemplate(ContextSource source) {
        return new LdapTemplate(source);
    }

    private static String required(String value, String property) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Thiếu cấu hình: " + property);
        }
        return value;
    }
}
~~~

Với bean được Spring quản lý, framework thực hiện lifecycle initialization của `LdapContextSource`; không cần tự gọi `afterPropertiesSet()` trong bean này. Ví dụ dùng **một LDAPS endpoint** và một tài khoản dịch vụ; nếu triển khai nhiều URL hoặc StartTLS thì phải thiết kế validation theo cấu trúc cấu hình tương ứng.

Thông số `com.sun.jndi.ldap.connect.timeout` và `com.sun.jndi.ldap.read.timeout` là **property của JNDI LDAP provider thuộc JDK**, không phải trường chuẩn của giao thức LDAP. Với provider khác, cần xác minh khả năng hỗ trợ và semantics của các property. **Read timeout không phải giới hạn cứng cho toàn bộ HTTP request.**

Mã ở trên **không hiển thị password khi báo lỗi**. Khi áp dụng thực tế, tránh in toàn bộ `Environment` hoặc các property bí mật. Cũng cần cấu hình truststore/CA và xác minh danh tính máy chủ TLS theo chính sách triển khai; sử dụng tiền tố `ldaps://` tự nó không chứng minh trust đã đúng.

### 3.2. Hạn chế của việc chỉ parse DN

~~~java
new LdapName("ou=people,dc=example,dc=org");
~~~

Lệnh này xác minh DN có cấu trúc parse được, nhưng **không gửi yêu cầu LDAP**. Nó không nói rằng `ou=people` tồn tại, máy chủ cho phép đọc OU đó hay schema có đúng thuộc tính mà ứng dụng cần. Các điều kiện này thuộc **functional probe** ở bước tiếp theo.

Tương tự, `URI.create(url)` giúp kiểm tra hình thức URL, nhưng không kiểm tra DNS, firewall, chứng chỉ hay trạng thái dịch vụ.

## 4. Kiểm tra LDAP thực khi khởi động

Một bài toán nghiệp vụ cụ thể: ứng dụng phụ thuộc bắt buộc vào thư mục nhân viên. Sau khi tạo `LdapTemplate`, hệ thống cần chứng minh rằng tài khoản `app-reader` có thể **đọc nhánh `ou=people`**. Thay vì chỉ kiểm tra TCP socket, hãy thực hiện lookup một entry ổn định và thuộc tính mà tài khoản này phải được phép đọc.

### 4.1. Dùng `ApplicationRunner` trong Spring Boot

Spring Boot có `ApplicationRunner` chạy trong giai đoạn khởi động ứng dụng. Ví dụ:

~~~java
import javax.naming.directory.Attribute;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;

@Configuration
public class LdapStartupProbe {

    @Bean
    public ApplicationRunner verifyDirectoryAtStartup(LdapTemplate ldapTemplate) {
        return arguments -> {
            String ou = ldapTemplate.lookup(
                    "ou=people",
                    (AttributesMapper<String>) attributes -> {
                        Attribute name = attributes.get("ou");
                        return name == null ? null : (String) name.get();
                    });

            if (!"people".equalsIgnoreCase(ou)) {
                throw new IllegalStateException(
                        "LDAP đã trả lời nhưng thiếu OU bắt buộc hoặc thuộc tính ou");
            }
        };
    }
}
~~~

Điều kiện thử nghiệm: `LdapContextSource` có base `dc=example,dc=org`; server phải tồn tại entry `ou=people,dc=example,dc=org` và tài khoản dịch vụ phải có quyền đọc thuộc tính `ou`. `lookup("ou=people", ...)` dùng DN **tương đối với base**; đưa cả DN đầy đủ vào đây sẽ sai khi context đã áp base.

Khi thực thi, thao tác này đi qua chuỗi tương tác thực: lấy context, thiết lập kết nối khi cần, xác minh TLS, sử dụng danh tính bind và yêu cầu LDAP đọc entry. Nếu kết nối hoặc thao tác thất bại, exception phát sinh trong runner sẽ làm **giai đoạn khởi động Spring Boot thất bại** theo chính sách fail-fast của ví dụ.

**Đừng đọc một entry ngẫu nhiên để probe.** Một entry người dùng có thể bị xóa/di chuyển, dẫn đến false alarm. Hãy chọn OU hoặc entry hệ thống **ổn định**, được quản trị bằng quy trình rõ ràng và có quyền đọc tối thiểu. Nếu yêu cầu nghiệp vụ chỉ cần kết nối mà không cần đọc OU, nên xác định một probe khác thể hiện đúng mức bảo đảm đó.

### 4.2. Vì sao lookup có giá trị hơn chỉ thử mở socket?

| Probe | Phát hiện được | Chưa chứng minh được |
| --- | --- | --- |
| Kết nối TCP đến host:port | DNS và cổng mạng phản hồi | TLS, LDAP protocol, mật khẩu, base/ACL |
| TLS handshake được xác minh | Danh tính endpoint và lớp kênh truyền ở thời điểm kiểm tra | Bind DN, mật khẩu, quyền đọc |
| Bind bằng tài khoản dịch vụ | Server chấp nhận danh tính | Nhánh/entry có tồn tại và được phép đọc |
| Lookup `ou=people` qua `LdapTemplate` | Đường đi kết nối, bind, DN tương đối, quyền đọc và thuộc tính yêu cầu hoạt động | Tất cả các OU, toàn bộ quyền ghi, mọi replica và trạng thái tương lai |
| Tìm theo filter nghiệp vụ mẫu | Một truy vấn đại diện hoạt động | Tính đúng đắn của mọi filter, hiệu năng ở tải cao |

Với các ứng dụng chỉ đọc danh bạ, probe **không cần tạo hay xóa entry**. Tránh kiểm tra ghi dữ liệu trong startup trừ khi có yêu cầu rất đặc biệt và vùng dữ liệu thử nghiệm riêng, vì các thao tác ghi có thể gây tác động nghiệp vụ khi ứng dụng khởi động lại liên tục.

## 5. Phân biệt fail-fast, startup probe và readiness

Không phải hệ thống nào cũng nên thất bại khi LDAP tạm thời không truy cập được. Chính sách phụ thuộc mức độ LDAP **bắt buộc** đối với chức năng chính của dịch vụ.

| Chính sách | Cách triển khai | Phù hợp khi | Rủi ro cần xét |
| --- | --- | --- | --- |
| **Fail-fast** | Runner thực hiện lookup, thất bại thì ném exception | Dịch vụ không thể hoạt động hợp lệ thiếu LDAP | LDAP gián đoạn có thể khiến nhiều bản sao cùng không khởi động |
| **Khởi động nhưng chưa ready** | Ứng dụng chạy, readiness báo không sẵn sàng cho đến khi LDAP ổn định | Hạ tầng điều phối cần chủ động ngừng gửi traffic | Phải bảo đảm các endpoint phụ thuộc LDAP không nhận traffic sớm |
| **Degraded mode** | Endpoint không dùng LDAP vẫn hoạt động; phần LDAP trả lỗi rõ ràng | LDAP chỉ là một phụ thuộc tùy chọn | Dễ che lỗi nếu biến mọi exception thành kết quả rỗng |
| **Chỉ kiểm tra cục bộ khi startup** | Validate property rồi để runtime xử lý lỗi kết nối | Có yêu cầu startup không phụ thuộc LDAP | Lỗi LDAP đầu tiên có thể xuất hiện khi phục vụ người dùng |

`ApplicationRunner` chạy trước khi Spring Boot thông báo ứng dụng đã hoàn tất giai đoạn ready, nhưng một web server có thể đã bind cổng trước khi runner chạy. Nếu yêu cầu **không nhận lưu lượng trước khi probe hoàn thành**, phải phối hợp readiness probe, routing và chính sách của nền tảng triển khai; đừng suy rằng runner một mình chặn mọi kết nối HTTP.

Đối với hệ thống đa replica, khởi động đồng thời có thể khiến tất cả instance cùng gọi LDAP. Probe cần **nhẹ, có timeout, không ghi dữ liệu** và tránh liên tục tìm kiếm trên toàn bộ cây. Không tự thiết kế vòng retry không giới hạn khiến khởi động treo hoặc tăng tải khi LDAP đang gặp sự cố.

## 6. TLS, xác thực và timeout trong phép kiểm tra khởi động

### 6.1. TLS phải được xác minh thực sự

Khi dùng `ldaps://directory.example.org:636`, cần cấu hình JDK truststore hoặc cơ chế tin cậy chứng chỉ của runtime phù hợp; xác minh chuỗi chứng chỉ, tên máy chủ và hiệu lực chứng chỉ. Với StartTLS, phải nâng cấp kênh **trước khi gửi thông tin xác thực nhạy cảm**. Một phép kiểm tra chỉ gọi `InetAddress.getByName` hoặc mở socket TCP **không đủ** để khẳng định kênh LDAP an toàn.

Không tắt xác minh chứng chỉ hoặc tạo `TrustManager` chấp nhận mọi chứng chỉ chỉ để “probe chạy được”. Cách khắc phục đúng là cài đặt trust chain, hostname và endpoint như môi trường thực.

### 6.2. Xác thực tài khoản dịch vụ khác với xác thực người dùng

`LdapContextSource.setUserDn(...)` và `setPassword(...)` thường mô tả danh tính tài khoản tra cứu. Probe ở trên kiểm tra **tài khoản dịch vụ có thể đọc OU**. Điều đó **không chứng minh** mật khẩu của mọi người dùng hợp lệ, tài khoản của họ chưa bị khóa hay luồng Spring Security LDAP/OIDC hoạt động đúng.

Muốn kiểm tra đăng nhập người dùng, hãy thiết kế test tích hợp riêng với tài khoản thử nghiệm và chính sách bảo mật phù hợp. Tránh chạy đăng nhập thử bằng thông tin mật khẩu của người dùng thật khi khởi động. Đặc biệt, kiểm tra dữ liệu đầu vào để không vô tình coi simple bind có tên/mật khẩu rỗng là xác thực thành công.

### 6.3. Timeout kết nối, timeout đọc và thời hạn search

| Thời hạn | Cấu hình thường gặp | Tác động |
| --- | --- | --- |
| Connect timeout | `com.sun.jndi.ldap.connect.timeout` | Giới hạn chờ thiết lập kết nối theo provider |
| Read timeout | `com.sun.jndi.ldap.read.timeout` | Giới hạn chờ nhận phản hồi theo provider |
| LDAP search time limit | `LdapQueryBuilder.timeLimit(...)` hoặc `SearchControls.setTimeLimit(...)` | Yêu cầu server giới hạn thời gian search; API Java dùng mili giây |
| Startup deadline | Chính sách của ứng dụng/container/orchestrator | Giới hạn tổng thời gian ứng dụng được phép khởi động |

Không nhầm một **search time limit** với toàn bộ thời hạn startup. Probe `lookup` có thể không sử dụng cùng cơ chế time limit với một search. Một lần lookup có thể chờ thêm thời gian DNS, TLS hoặc xử lý kết quả; nên đặt timeout provider và giới hạn startup ở tầng triển khai.

Khi bật pooling, một số lần lấy context có thể dùng lại kết nối đã được tạo. Probe khởi động với pool mới thường kiểm tra ít nhất một đường kết nối, nhưng **không bảo đảm mọi kết nối nhàn rỗi trong pool luôn còn sống**. Cần thêm chính sách tái tạo/kết nối, kiểm tra runtime và tuyệt đối không dùng lẫn kết nối mang danh tính người dùng khác nhau.


## 7. Duy trì readiness sau startup

Một lần probe thành công chỉ xác nhận trạng thái **tại thời điểm chạy**. LDAP server có thể mất kết nối, đổi chứng chỉ, khóa tài khoản dịch vụ hoặc thay đổi ACL sau đó. Đối với dịch vụ phụ thuộc LDAP, nên có một phép kiểm tra runtime phản ánh trạng thái sử dụng thực tế.

Trong ứng dụng có **Spring Boot Actuator**, có thể viết `HealthIndicator` riêng cho LDAP:

~~~java
import javax.naming.directory.Attribute;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.stereotype.Component;

@Component("directoryLdap")
public class DirectoryLdapHealthIndicator implements HealthIndicator {
    private final LdapTemplate template;

    public DirectoryLdapHealthIndicator(LdapTemplate template) {
        this.template = template;
    }

    @Override
    public Health health() {
        try {
            String ou = template.lookup(
                    "ou=people",
                    (AttributesMapper<String>) attrs -> {
                        Attribute name = attrs.get("ou");
                        return name == null ? null : (String) name.get();
                    });
            return "people".equalsIgnoreCase(ou)
                    ? Health.up().build()
                    : Health.down().build();
        } catch (RuntimeException failure) {
            // Không phát tán secret, DN nhạy cảm hoặc chi tiết lỗi tới endpoint.
            return Health.down().build();
        }
    }
}
~~~

Bean này báo trạng thái của **một đường đọc LDAP đã chọn**. Muốn dùng nó làm điều kiện readiness, phải **cấu hình health group/readiness probe của Spring Boot và cơ chế routing bên ngoài** để tín hiệu đó có tác dụng. Chỉ tạo bean `HealthIndicator` chưa tự động bảo đảm bộ cân bằng tải sẽ ngừng gửi traffic khi LDAP hỏng.

Không gọi health endpoint quá thường xuyên khiến hàng trăm instance đồng thời truy vấn OU, nhất là khi LDAP server đang quá tải. Hãy chọn nhịp kiểm tra, timeout hoặc cơ chế cache ngắn hạn thích hợp và tránh tác động ghi dữ liệu. Readiness có thể dùng để ngừng nhận traffic khi phụ thuộc bắt buộc chưa sẵn sàng. **Liveness** nên phản ánh việc tiến trình còn hoạt động được; một LDAP outage ngắn thường không phải lý do để liên tục restart ứng dụng.

| Tín hiệu | Điều có thể kết luận | Điều chưa được bảo đảm |
| --- | --- | --- |
| Bean `LdapContextSource` đã được tạo | Property hợp lệ để khởi tạo bean | Server đã kết nối hay xác thực |
| Startup lookup thành công | Một đường đọc qua LDAP hoạt động lúc khởi động | Mọi OU, mọi replica và lần truy cập sau |
| Health indicator UP | Probe hiện hành thỏa điều kiện của ứng dụng | Mọi nghiệp vụ LDAP đều thành công |
| Readiness UP | Theo chính sách điều phối, instance có thể nhận traffic | Không bao giờ mất kết nối trong lúc xử lý request |
| Liveness UP | Tiến trình đủ khỏe để tiếp tục | LDAP server còn hoạt động |

## 8. Chẩn đoán cấu hình sai theo từng tầng

Khi một phép thử khởi động thất bại, hãy giữ nguyên dấu hiệu đủ để người vận hành xác định nguyên nhân mà **không đưa thông tin đăng nhập vào log hoặc HTTP response**.

| Lớp lỗi | Dấu hiệu | Kiểm tra nên làm |
| --- | --- | --- |
| Cấu hình thiếu | `directory.url`, `directory.base`, `directory.bind-dn` hoặc secret rỗng | Xác minh nguồn property và secret |
| Cú pháp DN sai | Parse `LdapName` lỗi | Kiểm tra RDN và escaping DN |
| Địa chỉ mạng sai | DNS thất bại, port đóng, connect timeout | Xác minh host, DNS, firewall và timeout |
| Chứng chỉ TLS sai | Handshake thất bại, không tin CA, hostname không khớp | Kiểm tra truststore, CA, tên và thời hạn certificate |
| Bind tài khoản dịch vụ thất bại | LDAP từ chối bind | Kiểm tra bind DN, mật khẩu, trạng thái tài khoản |
| Base hoặc OU sai | Lookup không tìm thấy entry bắt buộc | Kiểm tra `ContextSource.base` và tên tương đối |
| Không đủ ACL | Bind được nhưng không đọc được OU/attribute | Cấp quyền đọc tối thiểu cho đúng nhánh |
| Server chậm | Read timeout hoặc search time limit | Xem tải server, filter, index và mạng |
| Referral/partial result | Truy vấn không hoàn tất ở naming context hiện tại | Xác định phạm vi và chính sách referral |
| Sự cố tạm thời | Lúc được lúc không, thường gặp trên replica/network | Theo dõi, retry có giới hạn và readiness |

Spring LDAP thường chuyển ngoại lệ JNDI sang các ngoại lệ truy cập LDAP của Spring. Lớp ngoại lệ cụ thể có thể khác theo phiên bản; ứng dụng nên phân biệt **cấu hình**, **authentication**, **communication**, **name not found**, **access denied** và **partial result** thay vì bắt tất cả rồi quy về “LDAP không có dữ liệu”.

**Không che lỗi bằng những cách sau:** tự hạ cấp từ LDAPS sang LDAP không mã hóa; chấp nhận mọi chứng chỉ; thử bằng tài khoản admin khi tài khoản dịch vụ thiếu quyền; trả danh sách rỗng cho mọi lỗi LDAP; tự động theo referral tới host không tin cậy; hoặc retry không giới hạn làm startup bị treo.

### 8.1. Chính sách retry ở startup

Với lỗi **cấu hình chắc chắn sai** (base DN không đúng cú pháp, thiếu secret, URL không hợp lệ), retry không đem lại lợi ích nếu cấu hình không thay đổi. Với lỗi **tạm thời** (LDAP chưa sẵn sàng ngay khi ứng dụng vừa được triển khai), có thể retry ít lần với khoảng giãn tăng dần và giới hạn tổng thời gian. Nếu quá thời hạn, chuyển sang fail-fast hoặc readiness DOWN theo chính sách đã định.

Hệ thống gồm nhiều instance cần tránh mọi instance cùng lúc retry mạnh, gây thêm tải cho LDAP server. Nếu retry, cần giới hạn, giãn nhịp và quan sát lỗi; tuyệt đối không gộp lỗi xác thực do mật khẩu sai với lỗi mất mạng rồi retry vô hạn.

## 9. Quy trình triển khai từ cấu hình tới trạng thái sẵn sàng

Một quy trình thực tế:

1. **Xác định phụ thuộc:** LDAP là bắt buộc cho toàn dịch vụ hay chỉ một số tính năng?
2. **Quy định cấu hình:** URL, base DN, bind DN, nguồn password, CA/truststore, timeout và pooling cho từng môi trường.
3. **Validate cục bộ:** kiểm tra không rỗng, schema URL và cú pháp DN trước khi tạo bean.
4. **Tạo `LdapContextSource`:** khởi tạo bean bằng Spring, giữ secret an toàn và quyền tài khoản dịch vụ tối thiểu.
5. **Probe thực tế:** lookup OU ổn định hoặc search nhỏ ở base đúng, với tài khoản truy vấn mà service sử dụng.
6. **Chọn hành vi khi lỗi:** fail-fast, readiness DOWN hoặc degraded mode; phân biệt lỗi có thể phục hồi.
7. **Cấu hình giám sát runtime:** ghi metric về thời gian probe, phân loại lỗi và sự thay đổi trạng thái; không đưa DN cá nhân hay secret vào metric labels.
8. **Kiểm thử phục hồi:** mô phỏng LDAP outage, thay đổi chứng chỉ, đổi ACL và xác minh ứng dụng xử lý đúng.

Không chạy tìm kiếm toàn bộ danh bạ hoặc thao tác ghi/xóa chỉ để kiểm tra health. Probe tốt là phép đọc nhỏ, ổn định, được cho phép bởi ACL và phản ánh đúng điều kiện cần thiết cho nghiệp vụ.

## 10. Kiểm thử theo lỗi cố ý

### 10.1. Dữ liệu mẫu

Giả sử LDAP server thử nghiệm có các entry:

~~~ldif
dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people

dn: uid=linh,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: linh
cn: Linh Nguyen
sn: Nguyen
mail: linh@example.org
~~~

Entry gốc `dc=example,dc=org` được giả định đã tồn tại. Tài khoản dịch vụ `cn=app-reader,ou=service,dc=example,dc=org` là tài khoản thử nghiệm, có quyền đọc đúng thuộc tính `ou` của entry `ou=people` và không có quyền ghi/xóa.

### 10.2. Ma trận kiểm thử

| Ca | Thay đổi trong môi trường test | Kết quả mong đợi |
| --- | --- | --- |
| A | URL LDAPS, CA, bind DN/secret và OU chính xác | Probe thành công |
| B | Thiếu `directory.url` | Fail-fast ở local validation |
| C | Dùng `ldap://` khi ứng dụng chỉ cho phép LDAPS | Từ chối cấu hình |
| D | Base DN sai cú pháp | Lỗi validation trước khi thử mạng |
| E | Host/port không truy cập được | Timeout hoặc lỗi kết nối đúng lớp |
| F | Truststore không tin CA | TLS validation thất bại |
| G | Hostname certificate không phù hợp | Bị từ chối theo chính sách TLS |
| H | Mật khẩu tài khoản dịch vụ sai | LDAP bind bị từ chối |
| I | `ou=people` không tồn tại dưới base | Lookup báo không tìm thấy |
| J | Bind thành công nhưng thiếu ACL đọc `ou` | Functional probe thất bại |
| K | LDAP phản hồi chậm | Timeout được ghi nhận; không treo startup vô hạn |
| L | LDAP ngừng sau startup | Readiness và API LDAP phản ánh đúng lỗi runtime |
| M | Nhiều instance khởi động đồng thời | Probe nhẹ, không ghi và không tạo bão request |

Các test cấu hình cục bộ có thể thực hiện mà không cần LDAP server. Các test TLS, bind, quyền đọc, schema, pooling, timeout và referral phải chạy trên **LDAP server thử nghiệm phù hợp với sản phẩm thật**. Mock `LdapTemplate` không thể chứng minh server đã chấp nhận bind hay cho phép đọc. Không thay mật khẩu, ngắt mạng hay sửa chứng chỉ trên hệ thống production để tạo lỗi kiểm thử.

### 10.3. Quan sát kết quả

Khi chạy các ca trên, ghi nhận loại lỗi, thời điểm xuất hiện (validation/bean creation/startup probe/runtime), độ trễ và trạng thái readiness. Xác nhận ứng dụng **không tuyên bố LDAP sẵn sàng** khi tài khoản dịch vụ thiếu quyền đọc OU bắt buộc. Đồng thời, xác nhận lỗi LDAP không bị chuyển thành thông báo “không có người dùng”.

Không log password, token, nội dung nhạy cảm của entry hay toàn bộ bộ cấu hình. Chỉ ghi các mã lỗi/tên thành phần ở mức cần thiết cho người vận hành.

## 11. Tự đánh giá

**Câu 1.** Spring tạo thành công `LdapContextSource`. Có thể kết luận LDAP server truy cập được và bind DN hợp lệ?

**Đáp án:** Chưa. Bean có thể chỉ hoàn tất cấu hình; cần một thao tác LDAP thật để xác minh TLS, bind và quyền theo yêu cầu.

**Câu 2.** Vì sao lookup một OU ổn định đáng tin hơn việc chỉ mở TCP socket?

**Đáp án:** Lookup kiểm tra đường thực thi LDAP với base, tài khoản, TLS và quyền đọc; TCP chỉ xác minh mức kết nối mạng.

**Câu 3.** `ApplicationRunner` chạy thành công một lần có bảo đảm LDAP sẽ luôn sẵn sàng?

**Đáp án:** Không. LDAP, mạng, chứng chỉ, ACL và kết nối pool có thể thay đổi. Cần giám sát runtime và readiness theo chính sách.

**Câu 4.** LDAP outage tạm thời có nên khiến liveness luôn DOWN?

**Đáp án:** Thông thường không. Liveness đánh giá tiến trình còn hoạt động; readiness phù hợp hơn để tạm ngừng nhận traffic khi phụ thuộc LDAP bắt buộc bị lỗi.

**Câu 5.** Khi TLS không tin chứng chỉ máy chủ, có nên tự chuyển sang kết nối không mã hóa để startup thành công?

**Đáp án:** Không. Cần sửa truststore, CA, hostname hoặc endpoint, không hạ cấp bảo mật.

**Câu 6.** Bind tài khoản dịch vụ thành công nhưng lookup `ou=people` bị từ chối. Có nên báo ready?

**Đáp án:** Không nếu việc đọc OU là chức năng bắt buộc. Cần kiểm tra lại ACL hoặc định nghĩa một probe đúng với quyền thật sự cần.

**Câu 7.** Nếu LDAP chỉ phục vụ tính năng phụ, có nhất thiết làm toàn ứng dụng fail-fast?

**Đáp án:** Không. Có thể dùng degraded mode và trả trạng thái lỗi cho tính năng liên quan, nếu chính sách nghiệp vụ cho phép.

**Ghi nhớ:** Phân biệt **kiểm tra cấu hình**, **xác minh kết nối/TLS và bind**, **kiểm tra thao tác LDAP đại diện** và **readiness sau khi khởi động**. Chọn chính sách fail-fast hoặc degraded mode theo vai trò của LDAP, không để cấu hình sai chỉ lộ ra khi người dùng gửi request đầu tiên.


# Trích xuất principal từ subject của chứng thư X.509

Khi dùng **X.509 client certificate** để xác thực trong Spring Security, trình duyệt, máy khách hoặc dịch vụ cung cấp chứng thư trong quá trình TLS handshake. Sau khi tầng TLS kiểm tra chứng thư theo chính sách của hệ thống, ứng dụng cần nhận diện **đối tượng ứng dụng** tương ứng với chứng thư. Một cách thường gặp là lấy giá trị `CN` (Common Name) từ trường **Subject** rồi dùng giá trị đó làm tên principal để tra cứu tài khoản và quyền.

Điểm quan trọng: **trích xuất principal** chỉ là thao tác đọc và diễn giải một thuộc tính danh tính. Nó **không** tự xác minh CA, chữ ký số, thời hạn, thu hồi chứng thư hay quyền truy cập. Cần phân biệt rõ định danh trong chứng thư, kết quả trích xuất và `Authentication` mà Spring Security dùng.

Bài học giải thích cú pháp Subject Distinguished Name (DN), cách trích xuất an toàn trong Java 17+, cơ chế mặc định của Spring Security, trường hợp CN thiếu/trùng/được escape, mối liên hệ với SAN và cách kiểm thử tích hợp.

## 1. Subject DN chứa gì?

Một chứng thư X.509 có các trường như **Subject**, **Issuer**, thời gian hiệu lực, khóa công khai, serial number, extensions và chữ ký. Subject thường là một **X.500 Distinguished Name (DN)** mô tả thực thể được cấp chứng thư.

Ví dụ Subject:

~~~text
CN=svc-orders,OU=Backend,O=Example Corp,C=VN
~~~

| Thuộc tính | Ý nghĩa | Được dùng thế nào |
| --- | --- | --- |
| `CN` | Common Name: tên chung của chủ thể | Có thể được cấu hình làm username/principal |
| `OU` | Organizational Unit | Cung cấp thông tin tổ chức, không tự động cấp role |
| `O` | Organization | Tên tổ chức trong Subject |
| `C` | Country | Mã quốc gia |
| `UID` | User identifier, nếu CA profile sử dụng | Có thể là ứng viên định danh tùy quy ước tổ chức |
| `emailAddress` hoặc OID tương ứng | Địa chỉ thư điện tử có thể xuất hiện trong DN | Không mặc nhiên đáng tin hay duy nhất |

Với DN ví dụ, nếu chính sách dựa vào CN thì principal dự kiến là:

~~~text
svc-orders
~~~

DN **khác** với principal trích xuất. Chuỗi `CN=svc-orders,OU=Backend,O=Example Corp,C=VN` là toàn bộ tên Subject; `svc-orders` chỉ là một giá trị thuộc tính được chọn theo quy tắc của ứng dụng.

Cần phân biệt thêm:

- **Subject** mô tả bên được cấp chứng thư; **Issuer** mô tả tổ chức/CA cấp chứng thư. Lấy CN từ Issuer sẽ tạo danh tính sai.
- **Subject DN** nằm ở trường Subject; **Subject Alternative Name (SAN)** là extension riêng, có thể chứa DNS name, email, URI, IP hoặc định danh khác. Chứng thư hiện đại có thể dùng SAN làm định danh chính.
- **Principal của Spring Security** là đối tượng ứng dụng sau khi tìm tài khoản. Nó có thể là `UserDetails` hoặc đối tượng domain tùy provider; không nhất thiết chỉ là String CN.

Không tự diễn giải `OU=Admins` thành quyền quản trị. Các thuộc tính Subject là dữ liệu nhận dạng do CA phát hành theo certificate profile, còn role/authority là quyết định của chính sách ứng dụng.

## 2. Dòng xử lý: TLS → Subject → principal → Authentication

Trong ứng dụng Spring Security Servlet hỗ trợ client certificate, luồng khái quát:

~~~text
Client gửi chứng thư trong TLS handshake
                 │
                 ▼
TLS endpoint xác minh chứng thư theo chính sách tin cậy
  (CA/trust anchor, chain, thời hạn, ràng buộc sử dụng...)
                 │
                 ▼
Servlet container cung cấp X509Certificate[] cho request
                 │
                 ▼
Spring Security X509AuthenticationFilter
                 │
                 ▼
X509PrincipalExtractor đọc Subject và chọn giá trị principal
                 │
                 ▼
PreAuthenticatedAuthenticationToken
                 │
                 ▼
PreAuthenticatedAuthenticationProvider
  tra tài khoản/quyền qua UserDetailsService hoặc dịch vụ tương đương
                 │
                 ▼
Authentication được dùng trong SecurityContext
                 │
                 ▼
Authorization: endpoint, method, resource
~~~

Trong Servlet API hiện đại (Jakarta), chứng thư máy khách do container đã xác thực có thể được cung cấp qua thuộc tính request `jakarta.servlet.request.X509Certificate`. Thực tế có nhận được thuộc tính này hay không phụ thuộc cấu hình TLS/container/proxy; `X509AuthenticationFilter` không thể suy ra chứng thư tin cậy từ một header bất kỳ do client tự đặt.

**Ranh giới tin cậy:** X.509 authentication ở Spring Security là một dạng **pre-authentication**. Spring Security giả định tầng TLS/container đã hoàn thành công việc xác thực chứng thư. Nếu lớp trước Spring Security không kiểm tra certificate chain, clientAuth hoặc trust store đúng cách, việc phân tích Subject hoàn hảo vẫn không làm hệ thống an toàn.

Ví dụ một client certificate có Subject `CN=svc-orders` nhưng được ký bởi CA không tin cậy: **không** được nhận principal `svc-orders` để đăng nhập. Quyết định chấp nhận chứng thư phải xảy ra trước khi mapping danh tính.

## 3. Trích xuất từ Java: ưu tiên X500Principal

Java cung cấp API để lấy Subject dưới dạng đối tượng chuẩn:

~~~java
X500Principal subject = certificate.getSubjectX500Principal();
String subjectDn = subject.getName(X500Principal.RFC2253);
~~~

Đây là **mảnh mã minh họa**, trong đó `certificate` là một `java.security.cert.X509Certificate` đã lấy từ nguồn đáng tin. Cần import `javax.security.auth.x500.X500Principal`.

Điểm cần nhớ:

- `getSubjectX500Principal()` trả về cấu trúc X.500 Subject; **không phải** chứng chỉ đã được xác thực chỉ vì gọi được phương thức này.
- `getName(X500Principal.RFC2253)` trả về dạng chuỗi theo quy tắc DN RFC 2253, thích hợp để parse bằng thư viện hiểu DN.
- `getSubjectDN()` của `X509Certificate` là API cũ trả về `Principal`; cách biểu diễn chuỗi có thể khác giữa provider. Tránh xây parser mới bằng cách gọi `getSubjectDN().getName()` rồi chia theo dấu phẩy.
- `X500Principal.CANONICAL` hữu ích trong một số phép so sánh/chuẩn hóa nhưng **không** biến CN hoặc DN thành định danh tài khoản ổn định của tổ chức.

Một DN có cấu trúc với escaping và đôi khi có Relative Distinguished Name (RDN) nhiều thuộc tính. Không coi nó là chuỗi CSV thông thường.

### Vì sao split hoặc regex ngây thơ có thể sai?

Hai Subject hợp lệ:

~~~text
CN=Lan Tran,OU=Platform,O=Example,C=VN
CN=Nguyen\, Lan,OU=Platform,O=Example,C=VN
~~~

Trong dòng thứ hai, `\,` là dấu phẩy **bên trong giá trị CN**, nên principal thực chất là **Nguyen, Lan**. Nếu viết `subjectDn.split(",")[0]` hoặc dùng regex dừng ở dấu phẩy đầu tiên, ta có thể cắt tên thành `Nguyen\` và tạo identity sai.

Thêm các trường hợp khó:

- CN nằm ở cuối DN, không phải đầu.
- Tên thuộc tính có thể khác chữ hoa/chữ thường, thứ tự RDN có thể thay đổi theo cách biểu diễn.
- Subject có thể không có CN, có nhiều CN hoặc là RDN đa giá trị phân tách bằng `+`.
- Giá trị DN có thể chứa dấu phẩy, dấu bằng, dấu cộng hoặc dấu gạch chéo ngược được escape.
- Một số thông tin Subject có thể được biểu diễn dưới dạng OID thay vì alias dễ đọc.
- Chuỗi ký tự Unicode phải được xử lý nhất quán; việc xóa accent, viết hoa/thường tùy tiện có thể tạo va chạm danh tính.

Vì vậy, với dữ liệu Subject tổng quát, **parse theo RDN** hoặc dùng extractor có hiểu X.500 sẽ đáng tin hơn regex trực tiếp trên chuỗi DN.

## 4. Java 17+: chương trình hoàn chỉnh lấy duy nhất một CN

Ví dụ sau dùng API có sẵn trong JDK 17 (không cần Spring). Nó tạo các `X500Principal` để mô phỏng trường Subject, phân tích DN bằng `LdapName`/`Rdn` và cố ý **từ chối** chứng thư không có đúng một CN không rỗng.

Tạo tệp **SubjectPrincipalDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.ldap.LdapName;
import javax.naming.ldap.Rdn;
import javax.security.auth.x500.X500Principal;

public class SubjectPrincipalDemo {

    static String singleCn(X500Principal subject) throws NamingException {
        LdapName dn = new LdapName(
                subject.getName(X500Principal.RFC2253));

        List<String> names = new ArrayList<>();
        for (Rdn rdn : dn.getRdns()) {
            Attribute cn = rdn.toAttributes().get("CN");
            if (cn == null) {
                continue;
            }

            for (int index = 0; index < cn.size(); index++) {
                Object raw = cn.get(index);
                if (!(raw instanceof String text)) {
                    throw new IllegalArgumentException("CN must be text");
                }
                names.add(text);
            }
        }

        if (names.size() != 1 || names.get(0).isBlank()) {
            throw new IllegalArgumentException(
                    "Subject must contain exactly one non-blank CN");
        }
        return names.get(0);
    }

    public static void main(String[] args) throws NamingException {
        X500Principal first = new X500Principal(
                "CN=Lan Tran,OU=Platform,O=Example,C=VN");
        X500Principal escaped = new X500Principal(
                "CN=Nguyen\\, Lan,OU=Platform,O=Example,C=VN");

        System.out.println("Simple CN: " + singleCn(first));
        System.out.println("Escaped CN: " + singleCn(escaped));

        try {
            singleCn(new X500Principal("OU=Platform,O=Example,C=VN"));
        } catch (IllegalArgumentException expected) {
            System.out.println("Missing CN rejected");
        }

        try {
            singleCn(new X500Principal(
                    "CN=Lan,CN=Other,O=Example,C=VN"));
        } catch (IllegalArgumentException expected) {
            System.out.println("Multiple CN rejected");
        }
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac SubjectPrincipalDemo.java
java SubjectPrincipalDemo
~~~

Kết quả stdout dự kiến chính xác:

~~~text
Simple CN: Lan Tran
Escaped CN: Nguyen, Lan
Missing CN rejected
Multiple CN rejected
~~~

**Vì sao chương trình xử lý được dấu phẩy escape?** `X500Principal` và `LdapName` hiểu cấu trúc DN; `Rdn.toAttributes()` trả lại giá trị thuộc tính CN đã được diễn giải, nên `Nguyen\, Lan` thành `Nguyen, Lan` thay vì bị cắt ở giữa. Việc đếm CN trước khi trả về ngăn chương trình tự chọn bừa một trong hai CN.

Giới hạn của ví dụ:

- Các `X500Principal` được **tạo từ chuỗi**, chỉ dùng để kiểm tra logic trích xuất. Chúng **không phải** certificate thật và không chứng minh CA/chuỗi chứng thư đã hợp lệ.
- Phương thức này thể hiện **chính sách một CN**. Có CA profile dùng Subject không chứa CN hoặc sử dụng định danh trong SAN; khi đó phải chọn quy tắc trích xuất khác thay vì bỏ qua lỗi.
- Cần áp dụng quy tắc định danh của tổ chức sau khi parse (ví dụ so khớp chính xác với danh sách service được cấp chứng thư). Không chấp nhận mọi CN tùy ý như một tài khoản có quyền.
- Không tự động `trim()` hay đổi chữ hoa/thường nếu hệ thống chưa quy định cách chuẩn hóa và kiểm tra trùng lặp. Các phép biến đổi đó có thể làm hai identity khác nhau trở thành một.

## 5. Regex trích xuất CN trong Spring Security

Các phiên bản Spring Security truyền thống sử dụng `SubjectDnX509PrincipalExtractor`, lấy Subject DN từ certificate và tìm principal bằng biểu thức chính quy. Mẫu thường được tài liệu mô tả là:

~~~regex
CN=(.*?)(?:,|$)
~~~

Chỉ có **một capturing group**: `(.*?)`. Với subject đơn giản `CN=svc-orders,OU=Backend,O=Example,C=VN`, kết quả là `svc-orders`. `(?:,|$)` là non-capturing group, kết thúc match ở dấu phẩy hoặc cuối chuỗi. Spring Security xử lý match không phân biệt chữ hoa/thường trong extractor cũ.

Khi dùng DSL Spring Security 6.x Servlet có thể đặt mẫu trích xuất:

~~~java
@Bean
SecurityFilterChain securityFilterChain(
        HttpSecurity http,
        UserDetailsService users) throws Exception {

    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/internal/**")
                    .hasAuthority("INTERNAL_ACCESS")
                    .anyRequest().authenticated())
            .x509(x509 -> x509
                    .subjectPrincipalRegex("CN=(.*?)(?:,|$)")
                    .userDetailsService(users))
            .build();
}
~~~

Đây là **mảnh cấu hình Spring** cần import `org.springframework.context.annotation.Bean`, `org.springframework.security.config.annotation.web.builders.HttpSecurity`, `org.springframework.security.web.SecurityFilterChain` và `org.springframework.security.core.userdetails.UserDetailsService`. Nó cần app Servlet có Spring Security, cấu hình TLS client certificate đúng, và một `UserDetailsService` thật trả về authority `INTERNAL_ACCESS` cho tài khoản được phép. Đoạn cấu hình **không tự khởi tạo máy chủ HTTPS**, cũng không tạo user service.

Nếu không cần override cách trích xuất mặc định, cấu hình `.x509(Customizer.withDefaults())` thường đủ để kích hoạt cơ chế X.509, với điều kiện phần TLS và dịch vụ tra tài khoản đã được cấu hình.

### Giới hạn của regex mặc định

Regex ở trên hữu ích với certificate profile có CN đơn giản nhưng có giới hạn:

1. **Escaped comma:** `CN=Nguyen\, Lan,...` có thể bị dừng giữa giá trị.
2. **Nhiều CN:** regex lấy một match mà không tự xác minh tính duy nhất của CN trong toàn DN.
3. **Thiếu CN:** không có match; extractor không thể tạo username hợp lệ. Không được đổi lỗi thành anonymous admin hoặc principal mặc định.
4. **CN nằm trong chuỗi thuộc tính lạ:** regex làm việc trên text, không hiểu đầy đủ ranh giới/escaping của X.500.
5. **CN không phải identity chính sách:** dù trích xuất đúng cũng có thể không có ánh xạ tài khoản hợp lệ.

Do đó, dùng regex chỉ khi **certificate profile được kiểm soát** và đã test đủ các trường hợp biên. Khi cần độ chắc chắn cao, sử dụng `X509PrincipalExtractor` tùy biến dựa trên parser X.500 và chính sách danh tính.

### Thay extractor trong ứng dụng

Một phương án thiết kế (mảnh mã định hướng, phụ thuộc phiên bản Spring Security):

~~~java
X509PrincipalExtractor extractor = certificate -> {
    try {
        return SubjectIdentityRules.singleCn(
                certificate.getSubjectX500Principal());
    } catch (NamingException ex) {
        throw new IllegalArgumentException(
                "Invalid certificate subject", ex);
    }
};
~~~

`SubjectIdentityRules.singleCn(...)` ở đây là **phương thức tự triển khai**, có thể chuyển logic từ chương trình ở mục 4 thành class ứng dụng. Khi cấu hình x509, nối extractor vào DSL bằng phương thức `x509PrincipalExtractor(...)` nếu phiên bản Spring Security hỗ trợ; hoặc cấu hình `X509AuthenticationFilter` tương ứng theo API phiên bản đang dùng. Không coi mảnh mã trên là một cấu hình hoàn chỉnh độc lập.

**Lưu ý về phiên bản:** Trong Spring Security 7.x, `SubjectDnX509PrincipalExtractor` và DSL `subjectPrincipalRegex(...)` đã được đánh dấu deprecated ở tài liệu API hiện hành; có class `SubjectX500PrincipalExtractor` để trích xuất CN hoặc email address từ X.500 principal theo cách có cấu trúc hơn. Với ứng dụng dùng Spring Security 6.x, hãy kiểm tra API tương ứng và chọn extractor hỗ trợ trong phiên bản đó; không import một class 7.x vào project 6.x rồi kỳ vọng biên dịch được.

## 6. SubjectX500PrincipalExtractor ở Spring Security 7.x

Với Spring Security 7.x, `SubjectX500PrincipalExtractor` được tài liệu API giới thiệu để trích xuất từ `X509Certificate.getSubjectX500Principal()`; mặc định lấy giá trị **CN**, và có thể cấu hình chọn thuộc tính emailAddress của Subject:

~~~java
SubjectX500PrincipalExtractor extractor =
        new SubjectX500PrincipalExtractor();

extractor.setExtractPrincipalNameFromEmail(true);
~~~

Đây là **mảnh mã dành cho Spring Security 7.x**, cần import `org.springframework.security.web.authentication.preauth.x509.SubjectX500PrincipalExtractor`. Khi tùy chọn là `true`, extractor lấy thông tin emailAddress **trong Subject DN**, **không phải tự động lấy rfc822Name từ SAN**. Sự phân biệt này quan trọng khi chứng thư chỉ mang email ở SAN.

Không tự chuyển mọi hệ thống từ CN sang emailAddress vì tên email có thể thay đổi, có thể tái sử dụng, và quy trình cấp chứng thư có thể chưa bảo đảm email là định danh duy nhất. Phải cập nhật đồng bộ chính sách CA, lookup và kiểm thử quyền.

## 7. Trích xuất đúng chưa có nghĩa user được xác thực/ủy quyền đúng

Giả sử Subject DN chứa `CN=svc-orders` và extractor trả về String `svc-orders`. Cần phân biệt:

| Bước | Dữ liệu đầu ra | Câu hỏi phải trả lời |
| --- | --- | --- |
| TLS validation | Chứng thư được chấp nhận theo chính sách TLS | Có phải chứng thư từ nguồn tin cậy và được phép dùng làm client certificate? |
| Principal extraction | `svc-orders` | Trường nào của chứng thư được quy định làm định danh? |
| Identity lookup | Tài khoản dịch vụ trong ứng dụng | Có đúng một account đang hoạt động được ánh xạ với principal này không? |
| Authority loading | Ví dụ `INTERNAL_ACCESS` | Account có quyền nào tại thời điểm xác thực? |
| Authorization | Allow/deny đối với request cụ thể | Quyền đó có đủ cho endpoint và resource đang truy cập không? |

Spring Security X.509 pre-authentication có thể dùng `UserDetailsService` để tra người dùng từ principal trích xuất. Nếu không có user tương ứng, ứng dụng phải xử lý như một lần xác thực không hợp lệ theo cấu hình. Nếu username được tìm thấy, quyền được cấp từ user store/provider, **không tự sinh ra từ CN hoặc OU**.

Chẳng hạn, một certificate do CA tin cậy cấp nhưng mang CN `visitor` không được tự động nhận quyền `INTERNAL_ACCESS`, trừ khi ứng dụng chủ động ánh xạ visitor thành account được cấp quyền. Cũng không tự động cho phép CN `admin` chỉ vì chữ này xuất hiện trong Subject.

Khi thiết kế ánh xạ, ưu tiên:

1. Xác định trust domain/issuer và certificate profile mà ứng dụng chấp nhận.
2. Định nghĩa thuộc tính danh tính sẽ đọc (CN, Subject UID, SAN URI hoặc tên khác).
3. Áp dụng quy tắc kiểm tra **duy nhất và ổn định** của danh tính trong phạm vi CA/tenant.
4. Tra account bằng khóa và chính sách được kiểm soát; fail closed khi không tìm thấy hoặc không duy nhất.
5. Nạp authorities qua user store và áp dụng chính sách chi tiết trên resource.

Việc một CN có cùng text ở hai CA khác nhau **không bảo đảm** hai chứng thư thuộc cùng một tài khoản. Nếu hệ thống tin nhiều CA/tenant, lookup theo CN đơn lẻ có thể gây va chạm; cần bổ sung ngữ cảnh issuer/trust domain hoặc sử dụng danh tính được CA profile định nghĩa là duy nhất.

## 8. Subject và SAN: chọn định danh theo certificate profile

Không phải mọi loại chứng thư nên lấy principal từ Subject CN.

| Hồ sơ chứng thư | Cách định danh nên cân nhắc | Rủi ro khi ép dùng CN |
| --- | --- | --- |
| Chứng thư người dùng nội bộ, CA quy định CN duy nhất | CN có kiểm soát và ánh xạ đến user account | Tên người có thể trùng hoặc đổi |
| Chứng thư service mTLS có SAN URI định danh workload | SAN URI theo namespace/workload ID được cấp phép | CN có thể chung, thiếu hoặc không ổn định |
| Chứng thư client có SAN rfc822Name | Email SAN nếu CA profile bảo đảm ràng buộc chủ thể | Email trong Subject không nhất thiết giống SAN |
| Chứng thư có Subject rỗng và SAN định danh chính | Đọc SAN bằng API chứng thư và kiểm tra loại SAN mong đợi | Regex CN không match |
| Nhiều CA/tenant phát hành cùng CN | Định danh kèm issuer/trust domain hoặc SAN ID toàn cục | Va chạm identity giữa nguồn cấp |

Trong JDK, `X509Certificate.getSubjectAlternativeNames()` cung cấp extension SAN ở dạng collection cấu trúc. Các mục SAN có **type** và **value** riêng; ví dụ dNSName, rfc822Name, uniformResourceIdentifier, iPAddress. Không áp dụng regex CN lên toàn bộ SAN rồi tự chọn giá trị đầu tiên. Xác định trước type, định dạng, giới hạn namespace, CA phát hành và chính sách so khớp.

Nếu workload sử dụng một URI danh tính như `spiffe://example.org/ns/prod/sa/orders`, đó thường là giá trị của **SAN URI** trong profile tương ứng, không phải Subject CN. Việc trích xuất SAN URI và so khớp trust domain là một chiến lược identity riêng, cần thực thi đúng tiêu chuẩn/hạ tầng được chọn.

## 9. Những lỗi parser và identity có thể trở thành lỗ hổng

### 9.1 Cắt chuỗi tại dấu phẩy hoặc dấu bằng

DN có escaping, nên `split(",")` và `split("=")` không phân tích đáng tin. Dùng API parser; nếu bắt buộc regex thì giới hạn rõ định dạng đầu vào bằng chính sách certificate issuance và kiểm thử case escape.

### 9.2 Chấp nhận CN đầu tiên khi có nhiều CN

Có thể xuất hiện nhiều RDN chứa cùng loại thuộc tính hoặc RDN nhiều giá trị. Nếu chính sách yêu cầu một CN, hãy **đếm và từ chối nếu số lượng khác một**. Không giả định giá trị đầu tiên luôn là đúng chỉ vì đọc được một chuỗi.

### 9.3 Dùng CN để phân quyền trực tiếp

Sai về bản chất:

~~~java
// Phản ví dụ: không dùng CN để tự cấp đặc quyền.
boolean isAdmin = extractedCn.equalsIgnoreCase("admin");
~~~

CN là một giá trị định danh được cấp trong chứng thư, không phải quyết định quyền nghiệp vụ. Hãy sử dụng principal để tìm account trong kho người dùng đáng tin cậy, sau đó đánh giá GrantedAuthority và resource policy.

### 9.4 Không xét chứng thư từ CA khác nhau

CA A và CA B có thể cấp certificate có cùng CN. Nếu cả hai được tin cậy nhưng policy không đồng nhất, map chỉ bằng CN có thể dẫn tới account collision. Khoanh vùng issuer/trust domain hoặc dùng khóa danh tính bảo đảm duy nhất.

### 9.5 Dùng fingerprint làm tên người dùng mà không xét vòng đời

Fingerprint của certificate thay đổi khi gia hạn/đổi chứng thư; issuer+serial xác định một chứng thư cụ thể và cũng có thể thay đổi khi renew. Nếu cần identity bền vững xuyên vòng đời, hãy chọn một thuộc tính được CA profile bảo đảm (ví dụ SAN workload ID), và quản lý mapping certificate → account có kiểm soát. Không có một khóa nào luôn phù hợp cho mọi hệ thống.

### 9.6 Tin chứng thư chuyển tiếp qua HTTP header không được bảo vệ

Nếu TLS chấm dứt tại reverse proxy, backend có thể không nhận chứng thư từ servlet container. Một header như `X-Client-Cert` **không có giá trị xác thực** khi client ngoài có thể tự gửi hoặc giả mạo. Muốn chuyển danh tính đã xác thực từ proxy vào backend, phải bảo đảm proxy xóa header do client gửi, chỉ chấp nhận từ kết nối proxy–backend tin cậy, xác thực kênh nội bộ, và xác minh nội dung được chuyển theo một hợp đồng rõ ràng. Không giả định Spring Security x509 tự hiểu mọi header chuyển tiếp.

### 9.7 Trộn lẫn Subject CN với TLS server name

CN/SAN dùng để xác minh **tên của server** trong HTTPS client là một bài toán khác với **trích xuất principal của client certificate** ở máy chủ. Tránh áp dụng máy móc quy tắc hostname verification cho mapping tài khoản client; cơ chế TLS và policy identity phải được định nghĩa riêng.

## 10. Cấu hình hạ tầng để Subject được lấy từ chứng thư thật

Trong ứng dụng Spring Boot Servlet sử dụng HTTPS trực tiếp, hạ tầng thường cần:

- **Server keystore**: khóa riêng và server certificate để thiết lập HTTPS.
- **Truststore cho client certificate**: chứa các trust anchor/CA mà server chấp nhận cho xác thực máy khách.
- **Client authentication mode**: chế độ yêu cầu hoặc đề nghị client certificate; nếu toàn bộ endpoint bắt buộc có cert, cấu hình tương ứng phải bảo đảm điều đó.
- **Certificate policy**: chain, thời hạn, key usage/extended key usage (khi áp dụng), constraints, revocation và các điều kiện doanh nghiệp khác do tầng TLS/hạ tầng thực hiện.
- **Spring Security x509 + user lookup**: nhận principal từ certificate đã được trình cho container, tra account và quyền.

Ví dụ một phần cấu hình TLS (các file và secret có thật phải do môi trường cung cấp):

~~~yaml
server:
  port: 8443
  ssl:
    enabled: true
    client-auth: need
    key-store: classpath:server-keystore.p12
    key-store-type: PKCS12
    trust-store: classpath:client-truststore.p12
    trust-store-type: PKCS12
~~~

Đây là **mảnh cấu hình minh họa**: còn phải cung cấp mật khẩu keystore/truststore qua cơ chế secrets phù hợp và đúng certificate/key. Không đặt mật khẩu hoặc khóa riêng vào tài liệu hay source code. `client-auth: need` yêu cầu chứng thư ở cấp TLS cho kết nối; `want` cho phép client không gửi chứng thư tùy cấu hình. Nếu chỉ một phần endpoint cần mTLS, có thể cần tách listener/gateway hoặc chính sách triển khai khác; không giả định đường dẫn HTTP có thể thay đổi quy tắc TLS handshake sau khi kết nối được thiết lập.

Nếu dùng Kubernetes ingress/API gateway/load balancer kết thúc TLS, hãy xác định chính xác vị trí kiểm tra mTLS và hợp đồng truyền danh tính vào ứng dụng. Kiểm thử từ bên ngoài tới backend để bảo đảm không thể bỏ qua proxy và tự cung cấp header giả.

## 11. Quan sát Subject bằng công cụ hệ thống

Để xem Subject DN của một certificate PEM trong môi trường kiểm thử:

~~~bash
openssl x509 -in client.pem -noout -subject -nameopt RFC2253
~~~

Để xem Subject Alternative Name:

~~~bash
openssl x509 -in client.pem -noout -ext subjectAltName
~~~

Lệnh OpenSSL có thể hiển thị kiểu format khác nhau theo phiên bản/cờ. Kết quả là dữ liệu để kiểm tra **profile**, không phải bằng chứng ứng dụng đã xác thực client qua TLS. Khi debug, hãy kiểm tra cả issuer, thời gian hiệu lực, EKU và cấu hình trust chain; riêng `-subject` không đủ kết luận chứng thư được chấp nhận.

Gửi request mTLS từ môi trường có client certificate và private key thử nghiệm:

~~~bash
curl --cert client.pem --key client-key.pem \
     --cacert server-ca.pem \
     https://localhost:8443/internal/whoami
~~~

Đây là **lệnh minh họa có điều kiện**: URL, CA, endpoint và credential phải tồn tại; không có stdout chuẩn cố định. Endpoint chỉ nên phản hồi username/authority ở môi trường phát triển, và tuyệt đối không gửi toàn bộ certificate/private key ra log. Nếu server không nhận certificate, kiểm tra handshake, truststore và chỗ kết thúc TLS trước khi debug regex.

Trong Servlet app có thể ghi log chẩn đoán an toàn bằng cách chỉ log tên nguồn identity và mã request. Tránh log PEM đầy đủ, thông tin định danh cá nhân hoặc toàn bộ Subject DN trong production trừ khi có nhu cầu và biện pháp bảo vệ dữ liệu rõ ràng.

## 12. Kiểm thử principal extraction

Một bộ test cho bộ trích xuất CN nên bao phủ ít nhất các tình huống sau:

| Subject hoặc môi trường | Kết quả mong đợi |
| --- | --- |
| `CN=svc-orders,OU=Backend,O=Example,C=VN` | `svc-orders` |
| `CN=Lan Tran,OU=Platform,O=Example,C=VN` | `Lan Tran` |
| `CN=Nguyen\, Lan,OU=Platform,O=Example,C=VN` | `Nguyen, Lan` |
| `OU=Platform,O=Example,C=VN` | Từ chối nếu policy yêu cầu CN |
| `CN=first,CN=second,O=Example,C=VN` | Từ chối nếu policy yêu cầu đúng một CN |
| CN rỗng hoặc chỉ whitespace | Từ chối |
| SAN định danh nhưng Subject không có CN | Từ chối theo chính sách CN; hoặc dùng extractor SAN có kiểm soát |
| Hai chứng thư từ hai CA cùng CN | Không nhập hai danh tính nếu trust domain/tenant khác |
| Certificate hợp lệ nhưng không có account tương ứng | Xác thực ứng dụng không thành công |
| Certificate/chain không đáng tin | TLS từ chối trước khi lấy principal |
| Certificate hợp lệ, account bị vô hiệu hóa | Không cấp access chỉ vì CN khớp |
| Certificate hợp lệ, thiếu authority của endpoint | Authorization từ chối |
| Header chứa DN giả do client gửi | Không được coi là chứng thư đã xác thực |

Nên kiểm thử ở **hai cấp**:

1. **Unit test parser:** dùng `X500Principal`/DN giả để xác minh việc tách CN, escape, số lượng thuộc tính và thông báo lỗi.
2. **Integration test TLS + Spring Security:** dùng test CA, certificate và account thật tại môi trường kiểm thử; quan sát ứng dụng nhận certificate qua container, chính sách trust hoạt động và `Authentication.getName()`/authorities phù hợp.

Test dùng MockMvc với request có certificate giả lập có thể hữu ích để kiểm tra filter/lookup, nhưng **không thay thế** kiểm thử TLS handshake và truststore thật. Một test đơn vị trích xuất trả đúng `svc-orders` không chứng minh đường truyền đã xác minh chứng thư.

## 13. Phân tích ba tình huống thực tế

### Tình huống A: Tên người dùng bị cắt ở dấu phẩy

Chứng thư có `CN=Nguyen\, Lan,...`, bộ regex cũ chỉ trả chuỗi trước dấu phẩy. Dẫn đến `UserDetailsService` không tìm thấy account hoặc tìm nhầm account có tên gần giống.

**Cách xử lý:** thay bằng extractor dùng `X500Principal`/`LdapName` hoặc chuẩn hóa profile cấp chứng thư; viết test với escaped comma.

### Tình huống B: Có chứng thư nhưng vẫn bị 403

TLS client certificate hợp lệ và principal trích xuất đúng, nhưng kho user không cấp authority mà endpoint yêu cầu. Đây thường là lỗi mapping tài khoản/quyền hoặc chính sách truy cập, không phải mặc định lỗi parser.

**Cách xử lý:** kiểm tra tài khoản được map từ principal nào, trạng thái enable/lock, authorities thật trên Authentication, và biểu thức `hasAuthority`/`hasRole` áp dụng ở endpoint. Không sửa bằng cách bỏ security cho toàn bộ URL.

### Tình huống C: Hệ thống dùng SAN URI, CN không đúng

CA cấp chứng thư workload với SAN URI là định danh chính; Subject có thể chung hoặc không có CN. Chọn CN sẽ tạo principal sai hoặc rỗng.

**Cách xử lý:** phối hợp với nhóm PKI để chốt certificate profile; định nghĩa extractor đọc đúng SAN type, kiểm tra trust domain và map account theo ID được tổ chức quản lý. Không lấy đại trường CN, OU hoặc email từ certificate nếu không có quy tắc rõ ràng.

## 14. Quy trình triển khai gợi ý

1. **Chốt certificate profile:** ai phát hành, trust anchor, loại chứng thư client, trường danh tính nào được bảo đảm, có SAN hay không, cấu trúc DN thế nào.
2. **Chốt quy tắc principal:** CN đơn, subject attribute khác hoặc SAN type cụ thể; xác định cách xử lý thiếu/trùng/escape/đổi tên.
3. **Cấu hình TLS:** kiểm tra chain, client-auth, truststore, TLS termination, đường đi qua proxy/gateway.
4. **Cài extractor đúng phiên bản Spring Security:** dùng class/API phù hợp với thư viện đang chạy; ưu tiên parser có cấu trúc cho DN phức tạp.
5. **Ánh xạ đến account và quyền:** fail closed khi không tìm thấy hoặc bị vô hiệu hóa; không cấp quyền từ text tự do trong Subject.
6. **Test đa tầng:** unit test extraction, integration test mTLS, certificate renewal, account revocation, phân quyền và va chạm identity.
7. **Theo dõi vận hành:** log lỗi có correlation ID và lý do cấp cao (không đưa private key/certificate nhạy cảm vào log), đo lỗi handshake/lookup độc lập.

### Những câu hỏi tự kiểm tra

- Nếu `Subject=CN=Lan Tran,OU=Platform,O=Example,C=VN` thì khác nhau thế nào giữa **DN** và **principal**?
- Vì sao `CN=Nguyen\, Lan` làm `split(",")` trả kết quả sai?
- Nếu client gửi chứng thư từ CA không tin cậy nhưng CN khớp tài khoản quản trị, vì sao không được cho đăng nhập?
- `SubjectX500PrincipalExtractor` đọc emailAddress ở Subject có giống đọc rfc822Name trong SAN không?
- Nếu hai CA phát hành cùng CN, ứng dụng cần thông tin nào để tránh nhầm danh tính?
- Principal được trích xuất thành công có đủ để quyết định `hasAuthority("INTERNAL_ACCESS")` hay chưa?

### Tài liệu kỹ thuật

- Spring Security – X.509 (Servlet): https://docs.spring.io/spring-security/reference/servlet/authentication/x509.html
- Spring Security – Pre-Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/preauth.html
- Spring Security – X509PrincipalExtractor API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/preauth/x509/X509PrincipalExtractor.html
- Spring Security – SubjectDnX509PrincipalExtractor API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/preauth/x509/SubjectDnX509PrincipalExtractor.html
- Spring Security – SubjectX500PrincipalExtractor API (7.x): https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/preauth/x509/SubjectX500PrincipalExtractor.html
- Java SE – X500Principal: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/security/auth/x500/X500Principal.html
- Java SE – X509Certificate: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/X509Certificate.html
- Java SE – LdapName: https://docs.oracle.com/en/java/javase/21/docs/api/java.naming/javax/naming/ldap/LdapName.html

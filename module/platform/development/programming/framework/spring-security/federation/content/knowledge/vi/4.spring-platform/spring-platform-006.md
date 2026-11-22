# Vai trò của phần mở rộng Spring Security Kerberos và kiểm tra tương thích

Spring Security Kerberos giúp ứng dụng Spring tích hợp **xác thực Kerberos**, đặc biệt là cơ chế **HTTP SPNEGO/Negotiate** để người dùng trong môi trường Active Directory hoặc Kerberos realm có thể đăng nhập vào ứng dụng web bằng thông tin xác thực hiện có. Giá trị của phần mở rộng này là nối các ticket Kerberos với mô hình `Authentication`, `AuthenticationManager`, `AuthenticationProvider` và `SecurityFilterChain` của Spring Security; nó không tạo ra một KDC, không cấp sẵn quyền nghiệp vụ và không tự làm cho mọi phiên bản Spring tương thích.

Bài học trả lời ba nhóm vấn đề: phần mở rộng giải quyết công việc gì và không giải quyết gì; các thành phần hoạt động như thế nào; cách **kiểm tra tương thích có bằng chứng** giữa Java, Spring Boot, Spring Framework, Spring Security, thư viện Kerberos, Servlet, máy chủ Kerberos và trình duyệt. Những ví dụ cấu hình chỉ được sử dụng sau khi đối chiếu phiên bản thực tế; ví dụ Java 17 độc lập ở phần sau minh họa bộ quy tắc kiểm tra sơ bộ, không thay phép thử Kerberos thật.

## 1. Kerberos là gì và đứng ở đâu trong kiến trúc?

Kerberos là giao thức xác thực dựa trên ticket và khóa mật mã. Trong mô hình thông thường:

- **Principal:** danh tính người dùng hoặc dịch vụ, ví dụ `alice@EXAMPLE.COM` hoặc `HTTP/portal.example.com@EXAMPLE.COM`.
- **Realm:** miền quản trị Kerberos (ví dụ `EXAMPLE.COM`), thường do một hoặc nhiều Key Distribution Center (KDC) phục vụ.
- **KDC:** trung tâm cung cấp các chức năng Authentication Service (AS) và Ticket-Granting Service (TGS); trong nhiều môi trường doanh nghiệp, Active Directory Domain Controller thực hiện vai trò này.
- **Ticket-Granting Ticket (TGT):** ticket cho phép client yêu cầu service ticket mà không nhập lại mật khẩu cho mỗi dịch vụ trong thời hạn hợp lệ.
- **Service ticket:** ticket dành cho một service principal cụ thể, ví dụ `HTTP/portal.example.com@EXAMPLE.COM`.
- **Keytab:** tệp chứa khóa dài hạn của principal dịch vụ để server xác minh ticket; phải quản lý như secret.
- **SPNEGO:** cơ chế thương lượng bảo mật được HTTP sử dụng qua `Negotiate`; trong bối cảnh này nó thường mang Kerberos service ticket qua GSS-API.

Lược đồ tổng quát:

~~~mermaid
sequenceDiagram
    participant U as Người dùng / trình duyệt
    participant K as KDC / Active Directory
    participant W as Ứng dụng Spring
    U->>K: Xác thực và nhận TGT (đã có từ phiên domain)
    U->>W: GET /secure
    W-->>U: 401 WWW-Authenticate: Negotiate
    U->>K: Xin service ticket cho HTTP/portal.example.com
    K-->>U: Service ticket
    U->>W: Authorization: Negotiate <SPNEGO token>
    W->>W: Xác minh ticket bằng keytab và ánh xạ principal
    W-->>U: 200 hoặc 403 theo quyền nghiệp vụ
~~~

Luồng trên là sơ đồ khái niệm: việc nhận TGT có thể diễn ra từ trước khi mở trình duyệt; một trình duyệt hoặc proxy có thể thực hiện nhiều bước thương lượng. Trạng thái `401` với header `WWW-Authenticate: Negotiate` thường là **challenge dự kiến** chứ chưa phải lỗi hệ thống. Sau xác thực, `403` nghĩa là người dùng đã được nhận diện nhưng không đủ quyền truy cập tài nguyên.

**Phân biệt:** Kerberos/SPNEGO là kỹ thuật xác thực chủ yếu có ích trong hệ thống realm/domain đã quản trị. OIDC/SAML dùng các trust contract và token/assertion khác; OAuth 2.0 access token cho API cũng không phải Kerberos service ticket. Khi cần SSO cho nhiều đối tác Internet, có thể để IdP/broker xác thực Kerberos ở phía nội bộ rồi phát hành OIDC/SAML ra ứng dụng, thay vì yêu cầu tất cả đối tác thiết lập trust Kerberos trực tiếp.

## 2. Phần mở rộng đóng vai trò gì trong Spring Security?

Spring Security gốc định nghĩa cơ chế chuỗi filter, authentication, authorization, session, bảo vệ request và tích hợp principal; Kerberos extension cung cấp các adapter để áp dụng nguyên tắc đó cho ticket Kerberos.

| Thành phần | Trách nhiệm | Điểm không được nhầm |
| --- | --- | --- |
| `SpnegoEntryPoint` | Trả challenge `WWW-Authenticate: Negotiate` khi cần xác thực bằng SPNEGO | Không tự xác thực ticket và không cấp role |
| `SpnegoAuthenticationProcessingFilter` | Đọc `Authorization: Negotiate ...`, tạo `KerberosServiceRequestToken`, gọi `AuthenticationManager` | Header có mặt không chứng minh token hợp lệ |
| `KerberosServiceRequestToken` | Vật mang token SPNEGO/Kerberos trong Spring Security | Không phải JWT, ID token hay SAML assertion |
| `KerberosServiceAuthenticationProvider` | Nhờ `KerberosTicketValidator` xác minh service ticket và nạp user/authorities | Ticket đúng vẫn cần policy quyền nội bộ |
| `SunJaasKerberosTicketValidator` | Triển khai xác minh ticket qua JAAS/GSS-API trên runtime phù hợp, dùng service principal và keytab | Cần JDK/JVM, realm, SPN, keytab và cấu hình KDC đúng |
| `UserDetailsService` | Ánh xạ username/principal đã xác thực sang tài khoản/authorities của ứng dụng | Không nên cấp admin chỉ vì principal thuộc domain |
| `KerberosAuthenticationProvider` | Hỗ trợ một luồng xác thực dùng username/password để thực hiện Kerberos client authentication khi có cấu hình phù hợp | Khác với server-side SPNEGO ticket validation |
| `KerberosRestTemplate` | Hỗ trợ client Java gọi backend bảo vệ bằng Kerberos/SPNEGO | Không biến REST API thành OAuth2 resource server |
| `SecurityFilterChain` | Điều phối filter, entry point và chính sách bảo vệ URL | Cần kiểm soát thứ tự, session và cơ chế fallback |

Tên package của các lớp trên trong nhánh được kiểm chứng là `org.springframework.security.kerberos.*`. **Tên package Java không đồng nghĩa groupId Maven.** GroupId của module đã đổi ở Spring Security 7; kiểm thử biên dịch chỉ bằng nhìn import chưa đủ.

Spring Security Kerberos còn cung cấp test-support như MiniKdc trong một số nhánh; hãy dùng đúng module test và phiên bản khi chọn fixture, thay vì tự suy ra tất cả API đã giống nhau qua mọi major.

## 3. Ranh giới trách nhiệm: Kerberos xác thực, ứng dụng cấp quyền

Nhìn vào hai phép kiểm độc lập:

1. **Authentication:** ticket được phát hành cho service principal đã cấu hình, còn hạn, xác minh được bằng khóa server chấp nhận, và ánh xạ được sang principal ứng dụng.
2. **Authorization:** principal đó có được xem tài liệu, truy cập endpoint, thay đổi cấu hình hoặc thao tác trong tenant hay không?

Ví dụ: ticket hợp lệ cho `alice@EXAMPLE.COM` không có nghĩa Alice được mở `/admin`. Service ticket cũng không cho biết quyền xem dữ liệu khách hàng B. `UserDetailsService` hoặc lớp ánh xạ quyền phải lấy role từ nguồn được ứng dụng tin cậy, kiểm tra trạng thái tài khoản và áp quyền tại request/resource.

Không tự đồng nhất:

- `REALM\alice` với `alice@REALM` hoặc email `alice@example.com` nếu chưa có mapping xác định;
- username không có realm với principal có realm;
- tài khoản hai domain có cùng phần tên trước dấu `@`;
- ticket Kerberos được xác minh với bearer access token được chấp nhận ở API;
- login domain thành công với quyền toàn hệ thống.

**Trong hệ thống federation**, AD forest trust/cross-realm trust là một cấu hình quản trị riêng: cần xác minh đường trust, principal, service ticket, keytab và chính sách truy cập. Một dịch vụ Spring không tự tạo trust giữa hai tổ chức khi thêm dependency Kerberos.

## 4. Khi nào dùng, khi nào chọn hướng khác?

| Bối cảnh | Kerberos/SPNEGO phù hợp? | Lý do |
| --- | --- | --- |
| Intranet Windows/AD, máy đã đăng nhập domain | Thường phù hợp | Trình duyệt có thể lấy service ticket mà không yêu cầu mật khẩu lần nữa |
| Web app nội bộ có domain Kerberos/MIT realm | Có thể phù hợp | Cần kiểm tra browser, DNS, KDC, SPN, keytab và hệ điều hành |
| API backend do Java client nội bộ gọi | Có thể dùng client Kerberos | Client cần cache ticket hoặc credential được quản lý, dịch vụ phải hỗ trợ Negotiate |
| Portal cho đối tác độc lập trên Internet | Thường cần broker/OIDC/SAML phía ngoài | Khó yêu cầu mọi đối tác có realm trust/browser policy Kerberos chung |
| Mobile/public SPA không thuộc domain | Thường không phải phương án chính | Không có bảo đảm client sở hữu ticket Kerberos và chính sách trình duyệt cần thiết |
| REST API dùng OAuth2 JWT | Dùng Resource Server OAuth2 cho API | Token Bearer JWT và SPNEGO là hai cơ chế khác nhau |

Có thể hỗ trợ đồng thời SPNEGO cho intranet và form/OIDC login cho người dùng bên ngoài, nhưng cần cấu hình rõ entry point, filter chain và chính sách fallback. Không tự hạ cấp sang Basic hoặc xử lý plaintext password trên mỗi request chỉ vì trình duyệt không thương lượng được.

## 5. Tương thích phiên bản: điểm thay đổi quan trọng giữa 2.x và 7.x

**Mốc đã đối chiếu với tài liệu chính thức ngày 07-11-2026:**

| Họ thư viện | GroupId Kerberos | Quan hệ được tài liệu xác nhận | Gợi ý |
| --- | --- | --- | --- |
| Spring Security Kerberos `2.2.0` (extension độc lập) | `org.springframework.security.kerberos` | Build/test trên **JDK 17, Spring Security 6.5.1, Spring Framework 6.2.8** | Dùng cùng dòng Spring Security 6, kiểm thử chính xác patch và Boot BOM đang sử dụng |
| Spring Security Kerberos `7.1.2` (đã tích hợp vào Spring Security) | `org.springframework.security` | Build/test trên **JDK 17, Spring Security 7.1.2, Spring Framework 7.0.10** | Giữ bộ module Spring Security 7 đồng bộ qua BOM |
| Nhánh 2.0.x cũ | `org.springframework.security.kerberos` | Tài liệu `2.0.1` ghi JDK 17, Spring Security 6.1.9, Spring Framework 6.0.20 | Không dùng số major 2.x làm bằng chứng cho mọi bản 6.x |
| Các nhánh preview/snapshot | Tùy nhánh | Phụ thuộc bản preview cụ thể | Không chọn làm baseline production chỉ từ tên artifact |

Điểm dễ sai: “thư viện Kerberos mới nhất vẫn là 2.x” chỉ đúng khi nói **dòng extension độc lập**; từ Spring Security 7, dự án đã được **hợp nhất vào Spring Security** và đổi coordinates. Không ghép `org.springframework.security.kerberos:...:2.2.0` tùy tiện với Spring Security 7.x. Các API/package có thể trông giống nhau nhưng phụ thuộc/ABI có thể khác; hành vi tải class lúc runtime mới cho thấy lỗi thật.

Các thông tin trên là **cấu hình đã được tài liệu xác nhận**, không phải lời cam kết rằng mọi biến thể Spring Boot, JDK vendor, servlet container, browser, AD/KDC đều tương thích. Sau một lần nâng cấp, luôn xác minh release notes, dependency graph và bài test SPNEGO thật.

### Bộ dependency tham khảo cho Spring Security 6

Với ứng dụng thuộc dòng Spring Boot 3.x/Spring Security 6.x đã được kiểm tra phiên bản, ví dụ Maven **chỉ minh họa tọa độ extension 2.2.0**:

~~~xml
<dependency>
    <groupId>org.springframework.security.kerberos</groupId>
    <artifactId>spring-security-kerberos-core</artifactId>
    <version>2.2.0</version>
</dependency>
<dependency>
    <groupId>org.springframework.security.kerberos</groupId>
    <artifactId>spring-security-kerberos-web</artifactId>
    <version>2.2.0</version>
</dependency>
~~~

Từ đó, đối chiếu `spring-security-core`, `spring-security-web` và `spring-framework` thực sự được giải quyết trong ứng dụng. Đừng cưỡng ép nâng một dependency transitive để lấy một API nào đó mà bỏ kiểm thử tương thích. Maven Central mô tả bản 2.2.0 có các phụ thuộc Spring Security 6.5.1; dự án của bạn có thể đang chọn patch khác theo BOM.

### Bộ dependency tham khảo cho Spring Security 7

Với Spring Boot thuộc nhánh quản lý Spring Security 7, theo tài liệu Spring Security:

~~~xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-kerberos-core</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-kerberos-web</artifactId>
</dependency>
~~~

Gradle khi BOM/plugin đã quản lý phiên bản:

~~~groovy
dependencies {
    implementation "org.springframework.security:spring-security-kerberos-core"
    implementation "org.springframework.security:spring-security-kerberos-web"
}
~~~

Nếu không dùng BOM, phải khai báo **phiên bản tương thích** cho từng module, không bỏ version rồi mong Gradle/Maven tự tìm đúng. Trong project dùng Spring Boot BOM, ưu tiên để BOM quản lý Spring Security, Spring Framework và Servlet stack; chỉ override nếu đã có lý do rõ và kiểm thử hệ quả.

**Không đưa cả hai bộ groupId vào một ứng dụng** để “dự phòng”: jar có thể mang cùng tên lớp, khiến dependency graph có nhiều thế hệ và việc class loader nạp lớp tùy thứ tự. Tương tự, đổi groupId mà quên thay toàn bộ references/dependency constraints/lockfile sẽ để lại jar cũ trên classpath.

Nguồn kiểm tra phiên bản và chuyển nhánh:

- [Spring Security Kerberos 2.2.0 Introduction](https://docs.spring.io/spring-security-kerberos/reference/introduction.html)
- [Spring Security 7.1.2 Kerberos Introduction](https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/introduction.html)
- [Spring Security 7 — What's New, Modules](https://docs.spring.io/spring-security/reference/7.0/whats-new.html)
- [Maven Central — Kerberos 2.2.0 core](https://central.sonatype.com/artifact/org.springframework.security.kerberos/spring-security-kerberos-core)

## 6. Ma trận tương thích cần kiểm thực tế

Xét ít nhất **ba lớp**:

### A. Tương thích code/dependency

- **JDK:** `java -version` và `javac -version` (nếu có compiler) phản ánh môi trường build; phải kiểm cả JVM trong container/runtime. Hai môi trường khác JDK major hoặc provider GSS/JAAS có thể khác hành vi.
- **Spring Boot/BOM:** ghi chính xác phiên bản Boot plugin/parent/dependency management; Boot 3 thường chọn Spring Security 6 và Spring Framework 6; Boot 4 chọn thế hệ Spring Security 7/Framework 7 phù hợp.
- **Spring Security và Kerberos:** chọn cặp phiên bản đã được tài liệu xác nhận, đồng bộ `spring-security-core`, `spring-security-web`, `spring-security-config` và hai module Kerberos; không để trộn Security 6 và 7.
- **Spring Framework và Servlet API:** code hiện đại thuộc namespace `jakarta.servlet.*`; ví dụ/document cũ có `javax.servlet.*` hoặc `WebSecurityConfigurerAdapter` thường không dùng trực tiếp trên nhánh mới.
- **Thư viện phụ trợ:** JAAS/GSS, HTTP client, LDAP support, test KDC; ghi các class linkage error nếu có.

### B. Tương thích môi trường Kerberos

- **KDC/AD:** realm, trust, encryption types được phép, principal người dùng/service, ticket policy, clock skew.
- **DNS/SPN:** tên host trình duyệt thực sự gọi có service principal HTTP tương ứng; alias, CNAME, reverse proxy và load balancer phải được thiết kế.
- **Keytab:** chứa đúng key của service principal với KVNO/enctype phù hợp; chỉ server được đọc; rotate key đồng bộ.
- **Client:** hệ điều hành/domain join, ticket cache, browser policy cho Negotiate, proxy cấu hình forwarding, TLS.
- **Container/Kubernetes:** có thể reach KDC/DNS, mount keytab riêng, truyền `krb5.conf` và service principal rõ; không phụ thuộc trạng thái domain login của máy developer.

### C. Tương thích vận hành và bảo mật

- **Authentication:** 401→Negotiate→ticket→Spring Authentication thành công, hoặc kết thúc với lỗi có kiểm soát.
- **Session:** session fixation protection, thời hạn, lưu `SecurityContext` khi phù hợp, logout, thay đổi role/revocation.
- **Authorization:** URL và từng tài nguyên được kiểm đúng vai trò; không mặc định mọi người trong realm đều là admin.
- **Observability:** log không rò ticket, keytab/password; phân biệt lỗi network, SPN, keytab, thiếu credential và lỗi quyền.

## 7. Cách kiểm tra dependency graph và API trước khi cấu hình

Chạy trên **module ứng dụng thật**, đúng branch và Gradle configuration đang chạy, ví dụ (Linux/macOS):

~~~bash
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-security-kerberos-core
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-security-kerberos-web
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-security-core
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-security-web
~~~

Trên Windows PowerShell, thay `./gradlew` bằng `.\gradlew.bat` khi dự án cung cấp wrapper batch. Với dự án Maven:

~~~bash
mvn -version
mvn dependency:tree
mvn dependency:tree -Dincludes=org.springframework.security,org.springframework.security.kerberos
mvn -DskipTests compile
~~~

**Cách đọc kết quả** (không giả lập stdout, vì mỗi dự án có dependency graph khác nhau):

1. Có đúng **một họ** Kerberos thuộc nhánh `2.x` hoặc `7.x` đã chọn không?
2. Các artifact `spring-security-*` có cùng dòng/phiên bản được BOM chọn không?
3. Có cả `jakarta.servlet` và thư viện cũ chỉ hỗ trợ `javax.servlet` trong đường dẫn runtime dẫn tới lỗi không?
4. Có thư viện cũ ép version của Spring Framework qua transitive dependency không?
5. Có lỗi `ClassNotFoundException`, `NoSuchMethodError`, `NoClassDefFoundError` sau nâng cấp không? Nếu có, đọc chính xác class/method và jar nơi nó được nạp, không quy mọi lỗi là “Kerberos không hoạt động”.
6. Jar chứa `SpnegoAuthenticationProcessingFilter` và `KerberosServiceAuthenticationProvider` thuộc đúng artifact/version được chọn không?

Có thể dùng `jar tf` hoặc `javap` khi cần điều tra chữ ký method; thí dụ:

~~~bash
jar tf path/to/spring-security-kerberos-web.jar
javap -classpath path/to/spring-security-kerberos-web.jar org.springframework.security.kerberos.web.authentication.SpnegoAuthenticationProcessingFilter
~~~

Trong lệnh thực, thay đường dẫn bằng **jar đã resolve**. Class `SpnegoAuthenticationProcessingFilter` trong nhánh hiện đại là Servlet filter, không phải auto-configured magic bean. Thêm dependency chưa làm cho SPNEGO login tự chạy; phải nối đúng filter, provider, entry point và đối tượng người dùng.

## 8. Điều kiện hạ tầng trước khi chạy SPNEGO

Để thí nghiệm chính xác, chuẩn bị thông tin từ quản trị domain/KDC:

| Thành phần | Giá trị minh họa | Kiểm tra cần thực hiện |
| --- | --- | --- |
| Realm | `EXAMPLE.COM` | Realm client và server được cấu hình, biết KDC |
| Host ứng dụng | `portal.example.com` | Trình duyệt thực sự truy cập host này, DNS/proxy ổn |
| Service principal | `HTTP/portal.example.com@EXAMPLE.COM` | Principal đã đăng ký đúng trong KDC/AD, không trùng SPN sai chủ |
| Keytab | `/etc/security/http-portal.keytab` | Đúng principal/KVNO/enctype, process server có quyền đọc |
| `krb5.conf` | `/etc/krb5.conf` | Realm mapping/KDC discovery, DNS phù hợp môi trường |
| User principal | `alice@EXAMPLE.COM` | User được domain/KDC xác thực, có quyền ở ứng dụng |
| Client | Máy domain/trình duyệt hỗ trợ Negotiate | Có credential cache và chính sách tin cậy URL |
| TLS/Proxy | `https://portal.example.com` | Header `Authorization` và `WWW-Authenticate` không bị proxy xóa |

Với client MIT Kerberos có sẵn, một chuỗi kiểm tra phổ biến là:

~~~bash
kinit alice@EXAMPLE.COM
klist
kvno HTTP/portal.example.com@EXAMPLE.COM
~~~

- `kinit` yêu cầu credential; đừng tự động nhúng mật khẩu vào script/test log.
- `klist` quan sát TGT/ticket cache của client.
- `kvno` yêu cầu service ticket cho SPN cụ thể; thành công chưa chứng minh web server có keytab đúng.
- `klist -k -e /etc/security/http-portal.keytab` có thể giúp người quản trị server xem principal/enctype trong keytab theo phiên bản công cụ; không chia sẻ keytab hay kết quả chứa thông tin nhạy cảm ngoài quyền hạn.
- `curl --negotiate -u : https://portal.example.com/secure` chỉ hoạt động khi bản curl có hỗ trợ SPNEGO/GSS và credential cache phù hợp; response khác nhau theo policy và tài nguyên nên không có stdout chung đảm bảo.

Có thể bật tạm debug của Kerberos JVM trong môi trường thử nghiệm, ví dụ `-Dsun.security.krb5.debug=true` hoặc bật debug JAAS theo cấu hình validator, rồi **tắt và làm sạch log** sau khi điều tra; log bảo mật có thể tiết lộ principal hoặc thông tin môi trường. Tránh ghi request header `Authorization: Negotiate` đầy đủ.

## 9. Tích hợp trong Spring Security: mô hình cấu hình hiện đại

Đối với ứng dụng **Servlet** có dependency đúng nhánh, các bước ghép thành phần gồm:

1. Tạo `SunJaasKerberosTicketValidator` với service principal và keytab path được cấp riêng.
2. Tạo `KerberosServiceAuthenticationProvider` trỏ tới validator và `UserDetailsService` ánh xạ principal/authorities.
3. Tạo `AuthenticationManager` chứa provider.
4. Tạo `SpnegoAuthenticationProcessingFilter` với authentication manager; cấu hình session strategy và security context repository theo cách ứng dụng lưu phiên.
5. Trong `SecurityFilterChain`, thiết lập `SpnegoEntryPoint` và gắn filter vào vị trí phù hợp trước `BasicAuthenticationFilter`, rồi đặt authorization rule.
6. Thử 401 challenge, xác thực ticket, ánh xạ user, phân quyền, lỗi SPN và logout bằng integration test.

**Ví dụ JavaConfig dưới đây là khung tích hợp cho ứng dụng Servlet**, cần project Spring Boot/Spring Security tương ứng và một `UserDetailsService` thực tế; không phải chương trình chạy độc lập và chưa có keytab/KDC nên không thể nhận 200 chỉ từ việc chép mã:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.kerberos.authentication.KerberosServiceAuthenticationProvider;
import org.springframework.security.kerberos.authentication.sun.SunJaasKerberosTicketValidator;
import org.springframework.security.kerberos.web.authentication.SpnegoAuthenticationProcessingFilter;
import org.springframework.security.kerberos.web.authentication.SpnegoEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.authentication.www.BasicAuthenticationFilter;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;

@Configuration
public class KerberosWebSecurityConfiguration {
    @Bean
    SunJaasKerberosTicketValidator kerberosTicketValidator() {
        String principal = System.getenv("KERBEROS_SERVICE_PRINCIPAL");
        String keytabPath = System.getenv("KERBEROS_KEYTAB_PATH");
        if (principal == null || principal.isBlank()
                || keytabPath == null || keytabPath.isBlank()) {
            throw new IllegalStateException("Kerberos service principal/keytab missing");
        }

        SunJaasKerberosTicketValidator validator =
                new SunJaasKerberosTicketValidator();
        validator.setServicePrincipal(principal);
        validator.setKeyTabLocation(new FileSystemResource(keytabPath));
        return validator;
    }

    @Bean
    KerberosServiceAuthenticationProvider kerberosProvider(
            SunJaasKerberosTicketValidator validator,
            UserDetailsService userDetailsService) {
        KerberosServiceAuthenticationProvider provider =
                new KerberosServiceAuthenticationProvider();
        provider.setTicketValidator(validator);
        provider.setUserDetailsService(userDetailsService);
        return provider;
    }

    @Bean
    SecurityFilterChain kerberosChain(
            HttpSecurity http, KerberosServiceAuthenticationProvider provider)
            throws Exception {
        SpnegoAuthenticationProcessingFilter spnego =
                new SpnegoAuthenticationProcessingFilter();
        spnego.setAuthenticationManager(new ProviderManager(provider));
        spnego.setSecurityContextRepository(
                new HttpSessionSecurityContextRepository());
        spnego.setSessionAuthenticationStrategy(
                new ChangeSessionIdAuthenticationStrategy());

        http.authorizeHttpRequests(auth -> auth
                    .requestMatchers("/health").permitAll()
                    .requestMatchers("/admin/**").hasRole("ADMIN")
                    .anyRequest().authenticated())
            .exceptionHandling(ex ->
                    ex.authenticationEntryPoint(new SpnegoEntryPoint()));
        http.addFilterBefore(spnego, BasicAuthenticationFilter.class);
        return http.build();
    }
}
~~~

**Giải thích các quyết định:**

- `UserDetailsService` phải được ứng dụng khai báo, thường lấy user/role từ dữ liệu đã được quản trị. Không dùng dữ liệu do browser tự gửi làm roles.
- Filter SPNEGO được tạo **bên trong security chain**, tránh vô ý đăng ký nó lần hai như một Servlet Filter độc lập do Spring Boot tự động nhận `@Bean Filter`.
- `HttpSessionSecurityContextRepository` và `ChangeSessionIdAuthenticationStrategy` là ví dụ cho ứng dụng có phiên; chính sách stateless cần thiết kế khác, và phải test session fixation, logout, replay/caching.
- Vị trí filter và entry point phải được thử cùng các authentication mechanisms khác; nếu dùng form/OIDC fallback cần nhiều policy/entry point phù hợp.
- `/admin/**` chỉ minh họa URL-level role; bảo vệ dữ liệu/đối tượng vẫn cần rule tại service.
- Đường dẫn keytab **không** nằm trong classpath hoặc jar. Secret manager/mount file cùng permission phù hợp an toàn hơn.
- Các method `setServicePrincipal`, `setKeyTabLocation`, `setTicketValidator`, `setUserDetailsService`, `setAuthenticationManager` có trong Javadoc của các nhánh đã đối chiếu; vẫn phải biên dịch với dependency thực tế sau khi chọn version.

Trong cấu hình trên, request tới endpoint yêu cầu xác thực có thể bị challenge. Khi trình duyệt cung cấp ticket phù hợp, `SpnegoAuthenticationProcessingFilter` gọi provider để kiểm ticket; Spring tạo authentication và thực thi authorization rule. Có keytab đúng nhưng `UserDetailsService` không nhận user cũng có thể dẫn đến đăng nhập thất bại.

### Lưu ý đặc biệt với Spring Security 7

Do Spring Security 7 gộp Kerberos vào dự án chính, thay **coordinates** và xem migration guide/releases của nhánh 7. Không assume snippet từ bài blog `WebSecurityConfigurerAdapter`/`antMatchers` hay XML Spring Security 3 copy nguyên xi sẽ biên dịch trên nhánh 7. Chọn API `SecurityFilterChain`, `authorizeHttpRequests` và module thuộc namespace `jakarta.servlet` khi phù hợp.

Nếu ứng dụng dùng WebFlux/reactive, đừng bê nguyên `SpnegoAuthenticationProcessingFilter`: class này là **Servlet filter**. Việc có thư viện trên classpath không tạo ra một chuỗi xác thực tương thích Reactive; phải xác định adapter hỗ trợ cụ thể và kiểm tra integration. Với ứng dụng Spring MVC, xác định xem security filter được đăng ký một lần ở đúng chain.

## 10. Java 17 chạy độc lập: chặn nhầm dòng dependency trước khi tích hợp

Trước khi thử Kerberos thật, một kiểm tra sơ bộ rất đơn giản có thể phát hiện hai nhóm sai phổ biến: phiên bản JDK quá thấp so với baseline đang xét và **trộn groupId/module major**. Ví dụ sau **không thể bảo đảm mọi patch tương thích**; nó chỉ xác nhận một quy tắc điều hướng ban đầu dựa trên hai dòng đã được tài liệu xác nhận.

Tạo file `KerberosCompatibilityDemo.java`:

~~~java
public class KerberosCompatibilityDemo {
    record Stack(int javaMajor, int springSecurityMajor,
                 int kerberosMajor, String groupId) {}

    static String evaluate(Stack stack) {
        if (stack.javaMajor() < 17) {
            return "REJECT: Java 17+ baseline required";
        }
        if (stack.springSecurityMajor() == 6
                && stack.kerberosMajor() == 2
                && stack.groupId().equals("org.springframework.security.kerberos")) {
            return "CANDIDATE: check exact 6.x/2.x versions and tests";
        }
        if (stack.springSecurityMajor() == 7
                && stack.kerberosMajor() == 7
                && stack.groupId().equals("org.springframework.security")) {
            return "CANDIDATE: check exact 7.x versions and tests";
        }
        return "REJECT: major line or Maven group mismatch";
    }

    public static void main(String[] args) {
        Stack legacy = new Stack(17, 6, 2,
                "org.springframework.security.kerberos");
        Stack integrated = new Stack(21, 7, 7,
                "org.springframework.security");
        Stack mixed = new Stack(21, 7, 2,
                "org.springframework.security.kerberos");
        Stack oldJdk = new Stack(11, 6, 2,
                "org.springframework.security.kerberos");

        System.out.println("Security 6: " + evaluate(legacy));
        System.out.println("Security 7: " + evaluate(integrated));
        System.out.println("Mixed: " + evaluate(mixed));
        System.out.println("Old JDK: " + evaluate(oldJdk));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac KerberosCompatibilityDemo.java
java KerberosCompatibilityDemo
~~~

Stdout chính xác:

~~~text
Security 6: CANDIDATE: check exact 6.x/2.x versions and tests
Security 7: CANDIDATE: check exact 7.x versions and tests
Mixed: REJECT: major line or Maven group mismatch
Old JDK: REJECT: Java 17+ baseline required
~~~

Tại sao dùng chữ **CANDIDATE**? Vì groupId đúng và major hợp lý chỉ là **điều kiện sơ bộ**, chưa xác minh patch version, Spring Framework, JVM provider, KDC, trình duyệt, SPN, keytab hoặc khả năng chạy. Ví dụ không phát hành ticket, không đọc `krb5.conf` và không được coi là integration test.

Trong CI, checker thực tế có thể đọc resolved dependency graph hoặc SBOM, so sánh BOM/lockfile và dùng Gradle/Maven fail build khi phát hiện hai module Kerberos khác generation. Không sửa bằng cách thêm cả hai dependency cho “an toàn”.

## 11. Kiểm thử tích hợp Kerberos có chứng cứ

Bài test sát thực tế cần môi trường có KDC/AD thử nghiệm hoặc fixture hỗ trợ, một service principal và keytab dùng riêng cho test. Không chạy xác thực thật trên keytab production trong CI public.

### Trình tự khuyến nghị

1. **Build test:** build được với Java và phiên bản Spring đã chọn, không có lỗi tải class hay phương thức thiếu.
2. **Dependency test:** lưu kết quả dependencyInsight/dependency tree, xác nhận đúng groupId và chỉ một generation.
3. **KDC test:** client xin được TGT và service ticket cho SPN web, dùng tài khoản và realm test.
4. **Server ticket test:** service có thể đọc keytab, validator nhận ticket đúng service, không nhận ticket sai SPN hoặc credential không hợp lệ.
5. **Browser SPNEGO test:** truy cập URL chuẩn, thấy 401 challenge, browser trả `Authorization: Negotiate`, xác thực thành công không cần nhập lại mật khẩu khi chính sách cho phép.
6. **Authorization test:** user hợp lệ nhưng không có quyền nhận `403` tại tài nguyên bảo vệ; role và membership vẫn do ứng dụng kiểm.
7. **Negative test:** thiếu ticket, expired/replayed ticket, wrong service principal, wrong keytab/KVNO, browser không có trusted URL, principal disabled bị từ chối có kiểm soát.
8. **Boundary test:** proxy/load balancer, HTTPS, nhiều node, DNS aliases, CNAME, session, failover KDC, rollback khi nâng version.
9. **Regression test:** form/OIDC fallback và CSRF/session/logout vẫn đúng sau thêm filter Kerberos.

Khi chạy test, ghi **expected và observed**; không tuyên bố SPNEGO thành công chỉ vì HTTP GET trả `200` từ endpoint public. Test nên gọi endpoint yêu cầu `authenticated()` và một endpoint kiểm tra role. Mở trình duyệt không có ticket không phải lúc nào cũng thất bại: nếu cấu hình fallback form hợp lệ, hệ thống có thể chuyển tới login form và vẫn bảo vệ tài nguyên.

### Ma trận negative testing

| Tình huống | Kỳ vọng | Vị trí điều tra |
| --- | --- | --- |
| Trình duyệt gửi request chưa đăng nhập | Challenge Negotiate hoặc fallback được định nghĩa | Entry point, browser policy |
| Browser không gửi header Negotiate | Không được tự xác thực user | Browser trusted sites, credential cache, proxy |
| Ticket cho `HTTP/other.example.com` | Không được chấp nhận cho `portal.example.com` | SPN, keytab, canonical host |
| Server keytab sai/đã rotate nhưng app chưa cập nhật | Xác thực ticket thất bại | KVNO, enctype, principal trong keytab |
| Chênh lệch thời gian quá chính sách KDC | Xác thực thất bại | NTP/clock skew |
| Principal hợp lệ nhưng user nội bộ disabled | Từ chối đăng nhập hoặc quyền theo policy | `UserDetailsService`, trạng thái user |
| Principal hợp lệ không có `ROLE_ADMIN` | `403` với `/admin/**` | Authorization rules, role mapping |
| Spring Security 7 nhưng dùng groupId extension 2.x | Fail dependency policy hoặc build/runtime validation | Dependency graph, class/linkage |
| Proxy chặn `WWW-Authenticate` hoặc `Authorization` | Thương lượng thất bại, không lách kiểm soát | Proxy header forwarding/TLS |
| Node A/B dùng keytab/realm khác nhau | Login lỗi theo node hoặc session bất ổn | Secret rollout, load balancing, session sharing |
| Đối tác không có Kerberos realm trust | Không giả định SSO qua SPNEGO | Kiến trúc federation, IdP/broker |

## 12. Những lỗi khó thường gặp và cách chẩn đoán

### 401 liên tục (challenge loop)

**Triệu chứng:** browser liên tục nhận `401 WWW-Authenticate: Negotiate` hoặc hỏi login nhiều lần.

**Khả năng:** browser không gửi ticket, URL không nằm trong trusted sites, máy chưa có TGT, browser chọn cơ chế khác, SPN không khớp hostname, proxy mất header. **Cách kiểm:** quan sát luồng HTTP ở môi trường test, kiểm `klist`, principal service, cấu hình browser và proxy. Không tự kết luận lỗi Java chỉ vì 401.

### `GSSException`, “Server not found in Kerberos database” hoặc “KDC not reachable”

Kiểm `krb5.conf`/DNS realm mapping, đường mạng tới KDC, SPN tồn tại, realm trust, hệ điều hành/JVM GSS provider. Lỗi tên service có thể do alias/CNAME dẫn client xin ticket sai principal. Kiểm chính xác FQDN mà client thực sự sử dụng.

### “Checksum failed”, “Integrity check failed”, “Cannot find key of appropriate type”

Có thể do keytab chứa khóa sai, sai KVNO sau rotation, enctype không khớp chính sách KDC/JDK hoặc principal service khác. Đối chiếu principal, KVNO, encryption types bằng công cụ dành cho quản trị; tạo keytab mới theo quy trình, hạn chế quyền đọc. Không vô hiệu hóa kiểm tra chữ ký/ticket để né lỗi.

### “Channel binding mismatch”

Có thể liên quan yêu cầu Extended Protection/channel binding, TLS termination hoặc provider hỗ trợ khác nhau. Kiểm tài liệu JDK/KDC/Windows và kiến trúc proxy. **Không khuyến nghị tắt Extended Protection trong registry như một bước sửa mặc định**; hành động đó có thể làm giảm bảo vệ. Ưu tiên cấu hình hợp lệ và kiểm thử với bên quản trị bảo mật.

### `NoSuchMethodError` / `NoClassDefFoundError` sau nâng Spring

Khả năng cao là không đồng bộ jar hoặc dùng API cũ. Ghi lại tên class/method, kiểm `dependencyInsight`, resolved artifacts, so sánh namespace `javax.servlet` và `jakarta.servlet`, BOM, classpath; chọn bộ module cùng thế hệ rồi test lại. Đừng thay code Spring Security 7 về `WebSecurityConfigurerAdapter` chỉ vì blog cũ có ví dụ.

### Đăng nhập thành công nhưng thiếu vai trò

Kerberos validator thường khẳng định principal, còn role cần `UserDetailsService`/policy khác. Kiểm ánh xạ tên principal (case/realm), trạng thái user, group/role source, quy tắc mapping và refresh quyền. Không gán `ROLE_USER` hay `ROLE_ADMIN` mặc định cho mọi ticket nếu ứng dụng có quyền phân tầng.

### Hoạt động khi chạy local nhưng lỗi trong container

Kiểm mounting keytab, `krb5.conf`, filesystem permissions, DNS, network tới KDC, clock time, Java vendor/provider, image path và service principal theo host public. Container không có ticket cache của máy developer; chạy local thành công không bảo đảm production.

## 13. Bảo mật và vận hành dài hạn

- **Keytab là secret:** mount theo nguyên tắc tối thiểu, không commit Git, không nhúng vào jar/image, không truyền qua chat/log, rotate cùng AD/KDC và quản lý rollback.
- **Dùng TLS** cho ứng dụng web; Kerberos xác thực không làm HTTPS dư thừa. Bảo vệ cookie phiên, CSRF và kênh proxy→backend.
- **Không mở rộng trust quá mức:** một realm được phép xác thực không tự cho mọi principal quyền admin; thêm tenant/resource authorization độc lập.
- **Không bật delegation bừa bãi:** nếu cần server gọi tiếp dịch vụ thứ ba bằng identity người dùng, thiết kế constrained delegation, SPN allowlist và kiểm soát quyền cụ thể. Unconstrained delegation tăng rủi ro lộ credential.
- **Không chấp nhận downgrade âm thầm:** nếu chính sách yêu cầu Kerberos, không cho fallback xác thực yếu hoặc Basic thiếu bảo vệ; nếu có fallback form/OIDC, định rõ ai được dùng và chính sách MFA.
- **Session và offboarding:** ticket hết hạn không tự đồng nghĩa cookie phiên ứng dụng bị thu hồi ngay. Cần thiết kế TTL, logout, deactivation, quyền mới và refresh session.
- **Theo dõi cảnh báo:** tỷ lệ 401/403, lỗi GSS/JAAS, lỗi KDC/DNS, keytab rotation, failed authorization, browser incompatibility; tránh log token đầy đủ.
- **Hỗ trợ nhiều node:** đồng bộ service identity/keys có kiểm soát, secret rollout, session strategy và kiểm thử sticky/non-sticky load balance.
- **Bản vá:** theo dõi release notes Spring Security, Kerberos modules, Spring Framework và JDK, phân biệt bản ổn định với milestone/RC/snapshot; ghi quyết định nâng cấp.

## 14. Quy trình ra quyết định tương thích trước khi triển khai

Có thể dùng các “cổng chất lượng” sau:

| Cổng | Điều kiện PASS | Nếu FAIL |
| --- | --- | --- |
| 1. Dependency | Spring Security, Framework, Boot, Kerberos cùng dòng được hỗ trợ và có graph không xung đột | Chỉnh version/BOM, loại artifact trùng |
| 2. API | Code compile với `SecurityFilterChain`, namespace Servlet và đúng phương thức có thật | Sửa API theo tài liệu **đúng version** |
| 3. KDC/SPN | Client xin được service ticket cho URL thật, server keytab đúng | Sửa DNS/SPN/keytab/realm với quản trị domain |
| 4. End-to-end | Browser/Java client hoàn tất Negotiate, server nhận diện đúng principal | Kiểm proxy/browser/cache/validator và trace test |
| 5. Authorization | Role, account state và quyền tài nguyên thực thi đúng; người không quyền nhận 403 | Sửa mapping và policy, không coi xác thực là quyền |
| 6. Hardening | TLS, secret, session, CSRF, rotation, log và fallback đáp ứng chính sách | Khắc phục trước khi public deployment |
| 7. Regression | Đăng nhập các luồng khác, multi-node và rollback không bị hỏng | Cập nhật integration tests/runbook |

Với mỗi cổng, giữ lại version/commit, build logs đã lọc secret, resolved dependency graph, test environment (OS/JDK/realm/browser) và kết quả PASS/FAIL. Đây là bằng chứng tin cậy hơn kết luận “đã thêm Kerberos dependency nên tương thích”.

## 15. Bài tập ứng dụng

### Bài tập 1: nhận diện vai trò

Intranet công ty A có `https://portal.example.com` và realm `EXAMPLE.COM`. Người dùng đã có TGT, browser gửi `Authorization: Negotiate` tới Portal.

Hãy trả lời:

1. Ai cấp TGT và service ticket?
2. Service principal nào được browser xin ticket?
3. Component Spring nào nhận header và component nào xác minh ticket?
4. Tại sao user có ticket hợp lệ vẫn có thể bị 403 với `/admin`?

**Đáp án:** KDC/AD; `HTTP/portal.example.com@EXAMPLE.COM`; `SpnegoAuthenticationProcessingFilter` và `KerberosServiceAuthenticationProvider`/`KerberosTicketValidator`; vì authorization thuộc role/resource policy ứng dụng, không do ticket tự quyết định.

### Bài tập 2: phát hiện nâng cấp sai

Một project nâng Spring Security từ 6.x lên 7.x nhưng giữ dependency:

~~~groovy
implementation "org.springframework.security.kerberos:spring-security-kerberos-web:2.2.0"
~~~

**Phân tích:** groupId và major của Kerberos extension 2.x không khớp generation Spring Security 7. Cần chuyển sang artifact `org.springframework.security:spring-security-kerberos-web` thuộc phiên bản 7 được BOM quản lý, đồng bộ core/web và kiểm dependency graph/compile/test. Không tự kết luận sẽ có lỗi nhất định nào nếu chưa quan sát build; đây là cấu hình không đúng dòng đã được tài liệu hướng dẫn.

### Bài tập 3: nguyên nhân 401

Máy developer login được `portal.example.com`, nhưng Kubernetes không. Trên pod không thấy `/etc/krb5.conf` và keytab chưa được mount, domain DNS truy cập từ pod bị chặn.

**Phân tích:** đây là khác biệt hạ tầng. Kiểm KDC reachability, krb5.conf, DNS, SPN, keytab path/permission, JDK provider và proxy. Việc đổi `HttpSecurity` một cách mò mẫm không giải quyết thiếu credential/service key.

## 16. Tóm lược và tài liệu gốc cần đối chiếu

- **Kerberos extension làm cầu nối:** ticket Kerberos/SPNEGO → Spring Security Authentication → user/authorities → authorization.
- **Tương thích là một ma trận:** tọa độ Maven + exact dependency versions + JDK/Servlet + KDC/AD + DNS/SPN/keytab + browser/proxy + session/security policy.
- **Spring Security 6 và 7 dùng tọa độ khác nhau:** extension `2.2.0` thuộc group `org.springframework.security.kerberos`, còn Kerberos `7.1.2` thuộc group `org.springframework.security`.
- **Một compile thành công chưa chứng minh đăng nhập thành công:** cần test tích hợp Kerberos thật và negative tests.
- **Xác thực không phải phân quyền:** user có service ticket vẫn có thể và phải bị từ chối khi không có quyền đối tượng.

Các nguồn tra cứu nên dùng trước mỗi lần nâng cấp:

1. [Tài liệu chính thức Spring Security Kerberos 2.2.0 — Introduction](https://docs.spring.io/spring-security-kerberos/reference/introduction.html).
2. [Tài liệu chính thức Spring Security 7.1 — Kerberos Introduction](https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/introduction.html).
3. [Spring Security 7.0 — What's New (Kerberos đã tích hợp)](https://docs.spring.io/spring-security/reference/7.0/whats-new.html).
4. [Kerberos 2.2.0 API — SPNEGO Filter](https://docs.spring.io/spring-security-kerberos/docs/2.2.0/api/org/springframework/security/kerberos/web/authentication/SpnegoAuthenticationProcessingFilter.html).
5. [Spring Security 7 API — SunJaasKerberosTicketValidator](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/authentication/sun/SunJaasKerberosTicketValidator.html).
6. [Spring Security 7 — Kerberos Samples](https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/samples.html).
7. [Maven Central — spring-security-kerberos-core 2.2.0](https://central.sonatype.com/artifact/org.springframework.security.kerberos/spring-security-kerberos-core).

**Ghi nhớ:** để dùng Kerberos đúng, hãy kiểm ba trục đồng thời — **đúng phiên bản thư viện**, **đúng hạ tầng ticket**, và **đúng quyền tài nguyên**. Không bỏ qua bất kỳ trục nào khi tích hợp hoặc nâng cấp Spring Security.
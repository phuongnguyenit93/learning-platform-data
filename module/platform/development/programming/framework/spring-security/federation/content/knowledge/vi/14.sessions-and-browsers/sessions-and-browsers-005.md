# Kho phiên phân tán, cân bằng tải và lựa chọn giữ phiên trên một nút

## 1. Bài toán SAML2 khi ứng dụng chạy trên nhiều nút

Một ứng dụng **Spring Security Servlet SAML2** đóng vai trò **Service Provider (SP/Relying Party)** thường chạy đằng sau **load balancer (LB)**, ingress hoặc reverse proxy. Khi triển khai hai hay nhiều instance, lưu trạng thái phiên vào bộ nhớ của mỗi instance có thể khiến đăng nhập SAML thất bại ngẫu nhiên hoặc người dùng bị yêu cầu đăng nhập lại.

Ví dụ ứng dụng có hai node **sp-a** và **sp-b**:

~~~text
                            HTTPS
Browser  ------------------------------------------> Load Balancer
                                                       |
                                       +---------------+---------------+
                                       |                               |
                                   Spring SP A                     Spring SP B
                                   HttpSession A                  HttpSession B
                                       |                               |
                                       +------- IdP (bên ngoài) -------+
~~~

Người dùng truy cập ứng dụng:

1. LB gửi GET **/saml2/authenticate/corp** đến node **A**.
2. Spring Security ở A tạo **AuthnRequest** và lưu thông tin yêu cầu đang chờ trong **HttpSession**.
3. Trình duyệt được chuyển đến IdP, đăng nhập hoặc MFA.
4. IdP đưa trình duyệt POST **SAMLResponse** về **/login/saml2/sso/corp** của SP.
5. LB có thể chuyển POST callback tới **B** thay vì A.
6. Nếu A và B giữ **HttpSession riêng**, B có thể không đọc được AuthnRequest đã lưu và không khôi phục được ngữ cảnh đăng nhập.

Hậu quả là **InResponseTo không tìm thấy request tương ứng**, login thất bại, bị chuyển về IdP nhiều lần, hoặc đã login ở A nhưng khi request sau đi B thì ứng dụng coi người dùng chưa xác thực.

Có hai lựa chọn kiến trúc chính:

- **Giữ phiên trên một nút (sticky session/session affinity)**: LB cố gắng chuyển các request thuộc một browser/session về **cùng node**; trạng thái HttpSession vẫn có thể là bộ nhớ cục bộ.
- **Kho phiên phân tán (distributed session store)**: các node dùng **cùng một kho phiên**, chẳng hạn **Spring Session + Redis** hoặc **Spring Session JDBC**; callback đến node nào cũng có thể đọc dữ liệu phiên nếu cookie, session ID, serialization và backend đều đúng.

Một mô hình thứ ba là **một node duy nhất**: đơn giản, phù hợp học tập hoặc dịch vụ nhỏ nhưng không có HA theo chiều ứng dụng.

**Mục tiêu:** hiểu dữ liệu SAML nằm ở đâu; khi nào sticky đủ và khi nào cần Spring Session; cách đồng bộ cookie, cân bằng tải, key/certificate, phiên đăng nhập và thử nghiệm failover mà không làm giảm các kiểm tra SAML.

## 2. Phân biệt năm loại trạng thái thường bị gọi chung là “phiên”

| Khái niệm | Ai quản lý? | Được dùng để làm gì? | Có tự chia sẻ qua nhiều node SP không? |
| --- | --- | --- | --- |
| **IdP SSO session** | Identity Provider | Giữ trạng thái người dùng đã đăng nhập tại IdP; có thể cho SSO sang SP khác. | **Không** phụ thuộc HttpSession SP; do hạ tầng IdP quản lý. |
| **SP HttpSession** | Servlet container hoặc Spring Session | Lưu SecurityContext và các trạng thái servlet theo ứng dụng SP. | Nếu lưu local: **không**. Nếu Spring Session shared store: **có**, theo cấu hình. |
| **Pending AuthnRequest** | Saml2AuthenticationRequestRepository | Liên kết SAMLResponse với request SP đã gửi, registrationId và request ID. | Mặc định trong **HttpSession**; việc chia sẻ tùy session store. |
| **Browser session cookie** | Trình duyệt, do SP phát hành | Chứa **session ID**, giúp SP tìm đúng HttpSession. | Cookie đi cùng browser; các node chỉ nhận ra khi kho phiên/định tuyến đúng. |
| **LB affinity mapping/cookie** | Load balancer | Ghi nhớ browser nên đi node A hay B. | Chỉ ảnh hưởng **định tuyến**, **không** biến local HttpSession A thành HttpSession B. |

**RelayState**, **AuthnRequest.ID** và **InResponseTo** không phải **session ID của browser**. Nếu dùng **CacheSaml2AuthenticationRequestRepository** tra theo RelayState hay InResponseTo, phải thiết kế ràng buộc browser/session và chống login CSRF; không tự xem một khóa cache như bằng chứng request thuộc browser hiện tại.

### HttpSessionSaml2AuthenticationRequestRepository

Với luồng SP-initiated phổ biến, **Spring Security** mặc định sử dụng **HttpSessionSaml2AuthenticationRequestRepository** để lưu **AbstractSaml2AuthenticationRequest** trong HttpSession. Spring Session thay thế cơ chế lưu phía sau HttpSession, vì vậy có thể dùng Redis/JDBC mà vẫn giữ ràng buộc request với browser session.

Sơ đồ:

~~~text
GET /saml2/authenticate/corp
      |
      v
Saml2WebSsoAuthenticationRequestFilter
      |
      +-- tạo AuthnRequest ID=_r123, registrationId=corp
      +-- HttpSessionSaml2AuthenticationRequestRepository.save(...)
      |         |
      |         +-- Local HttpSession A  HOẶC  Spring Session Redis
      v
Browser -> IdP -> POST SAMLResponse, InResponseTo=_r123
      |
      v
Saml2WebSsoAuthenticationFilter / token converter
      |
      +-- Load/remove AuthnRequest từ cùng browser session
      +-- Xác minh chữ ký, issuer, audience, time,
          destination, recipient, InResponseTo và chính sách chống replay
      v
Authenticated SecurityContext trong SP session
~~~

**Kho phiên phân tán không tự giải quyết mọi lỗi SAML.** Nếu cookie không được browser gửi về, Response sai issuer, AuthnRequest đã hết hạn, ID không khớp, chứng chỉ IdP sai, hoặc SP entityID/ACS khác nhau giữa hai node, Redis cũng không khiến Response hợp lệ.

## 3. Sticky session: giữ browser ở một node

**Sticky session/session affinity** là chính sách của load balancer cố gắng chuyển một chuỗi request có quan hệ tới cùng một backend.

Một số cơ chế:

| Cơ chế | Cách hoạt động | Giới hạn |
| --- | --- | --- |
| **Cookie-based affinity của LB** | LB đặt cookie/route token riêng, các request sau được chọn theo cookie đó. | Cookie có thể không được gửi ở SAML cross-site POST do SameSite/Secure; node chết thì local session có thể mất. |
| **Hash theo client IP** | LB định tuyến cùng IP tới cùng node. | NAT, mobile network, IPv6 prefix, proxy hoặc thay IP khiến độ ổn định thấp và phân phối tải lệch. |
| **Affinity theo ứng dụng/session ID** | LB đọc session cookie và ánh xạ tới node phù hợp. | Cần không bị nhầm cookie; **session ID có thể đổi sau login** do session fixation protection. |
| **Cookie route có thời hạn** | Route token gắn backend khi health và thời hạn phù hợp. | Hết cookie, cross-site request hoặc node fail có thể chọn node khác. |

Trong thực tế, một giải pháp sticky phải đúng trên **cả endpoint bắt đầu login và callback ACS**:

~~~text
Browser -> LB -> A : GET /saml2/authenticate/corp
Browser -> IdP    : xác thực
Browser -> LB -> A : POST /login/saml2/sso/corp
Browser -> LB -> A : GET /me
~~~

Nếu callback được đưa tới B trong khi AuthnRequest chỉ lưu tại A, SAML có thể thất bại. Nếu người dùng login thành công ở A nhưng request sau chuyển B, B không có SecurityContext trong local session nên yêu cầu login lại.

### Sticky không phải High Availability cho trạng thái phiên

- **Node A chết hoặc được redeploy**: local HttpSession A mất, LB chuyển browser sang B nhưng B không thể đọc trạng thái của A.
- **Deploy rolling update**: draining connections không mặc nhiên di chuyển session; các phiên cũ có thể bị ngắt khi node đóng.
- **Scale down**: loại backend có local sessions khiến người dùng trên backend đó đăng nhập lại.
- **Session timeout**: affinity còn nguyên nhưng server session đã hết hạn, browser vẫn phải đăng nhập lại.
- **Đổi session ID sau authentication**: nếu LB phụ thuộc session cookie thay vì affinity cookie riêng, mapping có thể thay đổi.

Vì vậy **sticky session giải quyết tính liên tục định tuyến khi node còn sống**, không phải cơ chế sao chép, sao lưu hoặc failover session.

### Khi nào sticky vẫn là lựa chọn hợp lý?

- Một hoặc vài instance, có thể chấp nhận người dùng đăng nhập lại nếu node chết.
- Yêu cầu SLA không đòi duy trì phiên qua rollout/failover.
- Hạ tầng chưa có Redis/JDBC và muốn tránh phụ thuộc shared session store.
- LB cookie-based affinity được cấu hình/kiểm thử đủ tốt cho **SAML cross-site POST** và mọi endpoint của SP.
- Có quy trình rollout drain, giảm tác động khi một node tắt.
- Không sử dụng nhiều vùng địa lý hoặc chuyển node thường xuyên.

**Không** chọn sticky chỉ vì “vài lần chạy thử thấy login được”. Phải thử MFA kéo dài, callback khác node, node failure, idle timeout, đổi cookie và restart.

## 4. Kho phiên phân tán: Spring Session thay HttpSession local

**Spring Session** cho phép servlet application tiếp tục sử dụng **HttpSession** API, nhưng thực tế lưu dữ liệu vào một **SessionRepository** nằm ngoài node, chẳng hạn Redis hoặc cơ sở dữ liệu quan hệ.

Mô hình Redis:

~~~text
                    HTTPS
Browser --------------------------------> Load Balancer
                                            |
                                 +----------+----------+
                                 |                     |
                               SP-A                  SP-B
                                 |                     |
                                 +------ Redis --------+
                                       shared sessions
                                       - AuthnRequest pending
                                       - SecurityContext
                                       - session attributes
                                       - idle expiration / TTL
~~~

Với cùng session cookie, **A và B cùng truy cập bản ghi session** đã lưu. Trường hợp callback tới B sau khi AuthnRequest được lưu từ A có thể thành công **nếu cùng khóa session, dữ liệu lưu/đọc thành công, cookie được gửi và toàn bộ kiểm tra SAML đạt**.

### Các lợi ích và chi phí

| Tính chất | Redis/JDBC shared session | Sticky + local HttpSession |
| --- | --- | --- |
| Callback bị LB chuyển sang node khác | Có thể đọc cùng pending AuthnRequest. | Có thể mất request vì khác local session. |
| Request tiếp theo chuyển node | Có thể đọc SecurityContext chung. | Có thể bị coi là chưa đăng nhập. |
| Node A chết | Phiên có thể tiếp tục tại B nếu shared store còn và phiên hợp lệ. | Local session A không chuyển sang B. |
| Node mới gia nhập | Không cần import local sessions nếu cùng repo. | Người dùng đang sticky vẫn chủ yếu ở node cũ. |
| Thông lượng và độ trễ | Thêm latency/traffic tới store; cần capacity planning. | Tránh round-trip shared store cho phần lớn đọc/ghi session. |
| Điểm lỗi tập trung | Redis/JDBC trở thành dependency quan trọng; cần HA và backup phù hợp. | Không phụ thuộc store chung; từng node có state riêng. |
| Rolling deploy | Có thể chuyển node, **nếu serialization/schema session tương thích**. | Thường khó giữ phiên khi loại node. |
| Bảo mật | Cần TLS, ACL, network isolation, TTL, access control cho store. | Cần bảo vệ memory/node; mất local sessions khi restart. |

**Distributed session không có nghĩa phân tán không trạng thái.** Ứng dụng vẫn **stateful**: HttpSession tồn tại bên ngoài instance. Spring Session không biến SAML SSO thành JWT stateless hoặc không cần cookie.

### Redis hay JDBC?

- **Redis**: đọc/ghi nhanh, TTL thuận tiện, phù hợp session có thời hạn; đổi lại phụ thuộc availability, memory budget, topology Redis và policy serialization.
- **JDBC**: có thể tận dụng DB/transaction/HA sẵn có, tiện kiểm soát dữ liệu và audit; đổi lại session traffic tăng tải DB, cần schema migration và cleanup jobs.
- **Local memory + sticky**: ít phụ thuộc hạ tầng nhưng mất phiên khi failover.

Cần quyết định theo tải, SLA, vận hành, chi phí, yêu cầu tuân thủ và đặc điểm sessions, không theo khẩu hiệu “Redis luôn tốt hơn DB”.

## 5. Bẫy của SAML cross-site POST: Cookie SameSite

Một SAML Web Browser SSO phổ biến sử dụng:

~~~text
GET SP /saml2/authenticate/corp   -> redirect IdP
POST IdP -> SP /login/saml2/sso/corp
~~~

Ở POST từ trang **IdP** về **SP**, browser có thể xem đây là **cross-site navigation với phương thức POST**. Nếu session cookie SP có **SameSite=Lax** hoặc **Strict**, browser có thể **không gửi cookie SP** trong callback đó. Khi ấy:

- Spring SP có thể tạo **session mới** và không tìm thấy AuthnRequest đã lưu ở session cũ.
- Một số LB affinity cookie cũng không được gửi, khiến callback đi **khác node**.
- Có Redis chung vẫn **không thể tìm ra đúng session** nếu không có cookie/ID đúng.
- Debug có thể nhầm lỗi cookie thành lỗi Redis hoặc lỗi IdP certificate.

**SameSite=None; Secure** là một lựa chọn phổ biến khi thực sự cần gửi session cookie trong cross-site POST. Tuy nhiên, cookie policy phải được đánh giá trong **toàn bộ mô hình CSRF/XSS, các browser, domain và yêu cầu bảo mật**; không tắt CSRF toàn ứng dụng để “sửa login”.

Trong **Spring Boot 3.3**, thuộc tính:

~~~yaml
server:
  servlet:
    session:
      cookie:
        same-site: none
        secure: true
        http-only: true
~~~

có thể cấu hình SameSite cho servlet session cookie, bao gồm Spring Session servlet SessionRepository do Boot auto-configure. **Secure** yêu cầu luồng browser bên ngoài dùng **HTTPS**; ví dụ local HTTP không đại diện behavior production.

### Session cookie và LB affinity cookie đều phải được thử

Một hệ thống có thể có:

~~~text
SESSION=<session-id>              (Spring Session)
LB_AFFINITY=<routing-token>      (Load Balancer)
~~~

Tên thực tế do cấu hình cụ thể quyết định; chúng không phải cùng một cookie. Nếu session cookie dùng SameSite=None nhưng affinity cookie dùng Lax, SAML callback POST có thể **đủ cookie để tìm session Redis**, nhưng LB vẫn đổi node. Với Redis shared store, tình huống đó thường không sao về session; với local HttpSession, đó là lỗi nghiêm trọng.

**Không sử dụng cookie domain rộng tùy tiện**, không tắt HttpOnly để JavaScript đọc session ID, không đưa session ID hoặc affinity token vào URL. Nếu proxy kết thúc TLS, phải nhất quán **forwarded proto/host** để Spring sinh đúng baseUrl, ACS và cookie policy.

### Một số điểm kiểm tra khi cookie không gửi

1. Browser DevTools → Network của **POST ACS**, quan sát **request Cookie header** và lý do browser chặn cookie.
2. Kiểm **SameSite**, **Secure**, **Domain**, **Path**, **Expires/Max-Age**, chính sách third-party/cross-site của browser.
3. Kiểm đúng host công khai của SP trước và sau redirect; tránh lúc dùng http://internal, lúc dùng https://app.example.com.
4. Kiểm browser thực tế, nhất là mobile, popup, cross-domain và điều hướng từ các IdP bên ngoài.
5. Kiểm cả **Spring SESSION/JSESSIONID cookie** lẫn **LB affinity cookie** nếu dùng sticky.
6. Kiểm session expiration và SAML AuthnRequest repository, không suy ra “không thấy request” chỉ vì Redis rỗng.

Một số browser có hành vi ngoại lệ/hạn chế khác nhau với SameSite; **không dựa vào ngoại lệ thời gian ngắn** hoặc kết quả ngẫu nhiên của một browser làm bảo đảm production.

## 6. Không làm mất bảo vệ chống login CSRF khi chuyển request store

Giữ **AuthnRequest trong HttpSession** có một lợi ích bảo mật quan trọng: request chờ gắn với **browser/session đã khởi tạo SSO**. Một Response do attacker tự chuẩn bị cho session của attacker sẽ không được xác nhận là request chờ của session nạn nhân.

Nếu tự chuyển sang cache toàn cục và tra request chỉ qua **RelayState hoặc InResponseTo**, có thể tạo lỗ hổng **login CSRF/login fixation**:

~~~text
Attacker khởi tạo SAML login trong browser của attacker
  -> có AuthnRequest ID=_attacker
  -> cache chung lưu request theo ID hoặc RelayState

Attacker khiến browser nạn nhân POST Response hợp lệ
  -> SP tra cache bằng ID/RelayState do request mang tới
  -> nếu không gắn với browser session nạn nhân, dễ chấp nhận nhầm
~~~

**Phân biệt hai mô hình “đều dùng Redis”:**

- **Spring Session Redis thay HttpSession backend**: HttpSession cookie của browser vẫn ràng buộc AuthnRequest chờ với đúng session; đây là hướng đơn giản để nhiều node chia sẻ phiên SAML.
- **Custom Saml2AuthenticationRequestRepository tra Redis bằng RelayState độc lập browser**: không mặc nhiên có ràng buộc browser; phải bổ sung correlation, TTL, one-time consume và chống replay/login CSRF.

Không thay request repository chỉ để “không phụ thuộc session” khi chưa phân tích các biện pháp an toàn tương đương. Spring Security có cơ chế custom/cache request repository nhưng việc vận dụng đòi hỏi hiểu security trade-offs.

## 7. Cấu hình Spring Boot 3.3.5 + Spring Session Redis + SAML SP

Ví dụ là một **Spring Security Servlet SAML2 Service Provider**, chạy **hai instance** chia sẻ Redis. Hệ thống thực tế cần **IdP metadata thật đã được tin cậy** và IdP đã đăng ký **SP entityID/ACS** đúng.

### 7.1. Phụ thuộc Maven đúng họ Boot 3.3

**pom.xml**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>saml-shared-session-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <repositories>
        <repository>
            <id>shibboleth-releases</id>
            <url>https://build.shibboleth.net/maven/releases/</url>
        </repository>
    </repositories>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-saml2-service-provider</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-redis</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.session</groupId>
            <artifactId>spring-session-data-redis</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Lưu ý tương thích:** Với **Boot 3.3**, sử dụng **spring-session-data-redis** và **spring-boot-starter-data-redis** như trên. Starter tên **spring-boot-starter-session-data-redis** được mô tả trong tài liệu Spring Boot thế hệ mới hơn; không sao chép dependency đó vào ví dụ Boot 3.3 khi chưa kiểm tra BOM/phiên bản.

**Không cần thêm @EnableRedisHttpSession** khi Spring Boot đã auto-configure một Spring Session store phù hợp. Gắn annotation thủ công có thể khiến một số thiết lập auto-config không còn áp dụng theo cách dự kiến; chỉ dùng khi thực sự muốn kiểm soát repository/TTL.

### 7.2. application.yml

**src/main/resources/application.yml**

~~~yaml
spring:
  data:
    redis:
      host: "${REDIS_HOST:127.0.0.1}"
      port: ${REDIS_PORT:6379}
  session:
    store-type: redis
    timeout: 30m
    redis:
      namespace: "samlsp:session"
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            assertingparty:
              metadata-uri: "${SAML_IDP_METADATA_URI}"

server:
  port: ${APP_PORT:8080}
  forward-headers-strategy: framework
  servlet:
    session:
      cookie:
        same-site: none
        secure: true
        http-only: true

app:
  node-id: "${INSTANCE_ID:node-local}"
~~~

Giải thích:

- **spring.data.redis.host/port:** kết nối Redis; local demo dùng 127.0.0.1:6379. Production cần Redis endpoint có TLS, network isolation, ACL/auth và HA riêng.
- **spring.session.store-type=redis:** chọn Redis session store; khi classpath chỉ có một Spring Session module, Boot 3.3 cũng có thể tự chọn, nhưng property làm mục đích rõ hơn.
- **spring.session.timeout=30m:** ví dụ thời gian session idle, không phải thời hạn SAML Assertion hay IdP SSO session.
- **spring.session.redis.namespace:** tách session keys theo ứng dụng/môi trường. **Các node của cùng một cụm SP phải dùng cùng namespace** nếu cần chia sẻ phiên; ứng dụng khác nên dùng namespace riêng.
- **SAML_IDP_METADATA_URI:** metadata URL IdP đã được tin cậy. Không có IdP hợp lệ, demo không thể hoàn tất SSO thật.
- **APP_PORT/INSTANCE_ID:** cho phép chạy hai process trên hai port khác nhau với nhãn node khác nhau khi thử nghiệm.
- **server.forward-headers-strategy=framework:** giúp dựng đúng external scheme/host nếu đặt sau proxy. Chỉ sử dụng forwarded headers được LB/proxy đáng tin ghi và **không cho Internet trực tiếp điều khiển X-Forwarded-* header**.
- **same-site:none + secure:true:** phục vụ các callback SAML cross-site POST khi chính sách cookie cho phép. Phải chạy browser qua HTTPS public endpoint; không kỳ vọng HTTP localhost minh họa được cookie production.

**Security trade-off:** nhờ Redis shared session, bất kỳ node nào cũng có thể đọc session nếu cùng cookie và store. Đó là mục tiêu của kiến trúc, nhưng Redis phải là backend **được bảo vệ như kho dữ liệu xác thực**, không phải Redis cache mở mạng.

### 7.3. Main class

**src/main/java/com/example/samlsession/SamlSessionApplication.java**

~~~java
package com.example.samlsession;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SamlSessionApplication {
    public static void main(String[] args) {
        SpringApplication.run(SamlSessionApplication.class, args);
    }
}
~~~

### 7.4. SecurityFilterChain

**src/main/java/com/example/samlsession/SecurityConfig.java**

~~~java
package com.example.samlsession;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/node", "/error",
                    "/saml2/metadata", "/saml2/metadata/**",
                    "/saml2/service-provider-metadata/**").permitAll()
                .anyRequest().authenticated()
            )
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults());

        return http.build();
    }
}
~~~

SAML AuthnRequest và SAMLResponse được xử lý qua Spring Security filters. **Không tạo controller nhận SAMLResponse thủ công**. SecurityContext sau khi login dùng **HttpSession đã được Spring Session thay backend bằng Redis**.

### 7.5. Controller phục vụ kiểm thử hai node

**src/main/java/com/example/samlsession/NodeController.java**

~~~java
package com.example.samlsession;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class NodeController {

    private final String nodeId;

    public NodeController(@Value("${app.node-id:node-local}") String nodeId) {
        this.nodeId = nodeId;
    }

    @GetMapping("/")
    public String home() {
        return "SAML shared-session SP";
    }

    @GetMapping("/node")
    public String node() {
        return "Serving from " + nodeId;
    }

    @GetMapping("/me")
    public String me() {
        return "Authenticated on " + nodeId;
    }
}
~~~

**GET /node** cho thấy request hiện đang đi đến node nào nhưng **không công khai session ID, cookie, NameID hoặc dữ liệu người dùng**. **GET /me** yêu cầu Authentication và thể hiện browser có duy trì phiên đăng nhập khi LB đổi node hay không.

### 7.6. Khởi động

Có hai điều kiện môi trường:

1. Redis đã chạy, cho phép hai instance kết nối tới cùng database/namespace theo cấu hình và policy.
2. Một IdP sandbox thật đã đăng ký SP metadata/ACS theo **địa chỉ HTTPS public của LB**, IdP verification cert đã được SP tin và SSO flow có thể hoạt động.

Chạy project bằng:

~~~bash
mvn spring-boot:run
~~~

Để thử hai process độc lập, dùng **hai terminal** với môi trường đã được thiết lập từ trước:

~~~text
Process A:
  APP_PORT = 8081
  INSTANCE_ID = sp-a
  REDIS_HOST = địa chỉ Redis dùng chung
  SAML_IDP_METADATA_URI = URL metadata IdP được phê duyệt

Process B:
  APP_PORT = 8082
  INSTANCE_ID = sp-b
  REDIS_HOST = cùng Redis của A
  SAML_IDP_METADATA_URI = cùng IdP configuration phù hợp
~~~

Ở mỗi terminal chạy **mvn spring-boot:run**. Front door HTTPS của LB trỏ vào A:8081 và B:8082. Hai process phải dùng **cùng code/build, namespace Redis, SP entityID/ACS và trust configuration**. Với deployment riêng host/container, cần cấu hình host/port thực và TLS ở proxy.

**Đừng** đăng ký **localhost:8081** là ACS cho A và **localhost:8082** là ACS cho B trong cùng ứng dụng nhiều node. IdP cần **một external SP entityID/ACS ổn định** mà browser truy cập qua LB, ví dụ **https://sp.example.org/login/saml2/sso/corp**.

### 7.7. Kết quả quan sát

- **GET /node** trả **Serving from sp-a** hoặc **Serving from sp-b** tùy node được LB chọn. Với local chỉ một process, trả nodeId tương ứng.
- **GET /saml2/authenticate/corp** khởi tạo AuthnRequest đến IdP theo registration corp.
- **POST /login/saml2/sso/corp** phải được framework xử lý; khi browser mang lại session cookie hợp lệ, một node khác có thể lấy pending request từ Redis để correlation.
- **GET /me** sau khi login SAML hợp lệ trả **Authenticated on sp-a** hoặc **Authenticated on sp-b**. Việc node thay đổi mà vẫn xác thực cho thấy session store/cookie và SecurityContext tiếp tục hoạt động, nhưng **chỉ integration test có ký SAML thật mới chứng minh toàn bộ SSO chính xác**.
- **GET /me** khi chưa login sẽ kích hoạt SAML login, không trả một principal giả.

Không có IdP metadata thật và Redis vận hành đúng thì chương trình có thể không khởi động hoặc không hoàn tất login; đó là giới hạn hợp lệ của ví dụ có phụ thuộc bên ngoài.

## 8. Spring Session Redis: cần kiểm tra ngoài vài dòng YAML

### 8.1. Hai node phải cùng phiên bản dữ liệu session

Các thuộc tính session có thể gồm:

- **SPRING_SECURITY_CONTEXT**, principal và Authentication của Spring Security;
- AbstractSaml2AuthenticationRequest đang chờ, tùy request repository/version;
- Các thuộc tính session khác của ứng dụng.

Spring Session Redis thường dùng **Java serialization** mặc định cho session attributes theo cấu hình/thế hệ được sử dụng. Khi node A ghi object và node B đọc, hai bên phải giải mã được cùng kiểu/class/serialVersionUID/schema. Trong rolling deploy, object/class từ bản cũ có thể không tương thích bản mới.

**Đừng giả định Redis tồn tại là xong.** Phải integration test:

1. A tạo AuthnRequest và ghi session vào Redis.
2. B đọc chính session ấy sau callback.
3. B đọc được SecurityContext mà A vừa lưu sau login.
4. Deploy A phiên bản cũ và B phiên bản mới trong khoảng chồng lấn; kiểm phiên có còn đọc/ghi được.
5. Dọn session cũ theo TTL và thay đổi serializer một cách có kế hoạch.
6. Kiểm sự kiện session fixation protection làm đổi session ID và cookie sau login.

Không tự bật JSON serializer cho session production rồi nghĩ nó luôn tương thích mọi Spring Security/SAML object. **Serialization phải được đánh giá an ninh**, cấu hình type whitelist/modules phù hợp và có test upgrade. Java native deserialization có rủi ro khi Redis bị truy cập trái phép; cô lập Redis và hạn chế ghi dữ liệu lạ.

### 8.2. Flush, save mode và tính nhất quán

Spring Session có các tham số như **spring.session.redis.flush-mode** và **save-mode**; chúng ảnh hưởng khi nào session ghi ra Redis và theo dõi thuộc tính thay đổi.

- **on-save** thường trì hoãn ghi đến lúc commit/save session ở cuối request; phải kiểm trạng thái AuthnRequest thực sự được lưu **trước khi redirect browser sang IdP**.
- **immediate** có thể ghi sớm hơn nhưng tăng I/O, tùy repository/phiên bản.
- Nếu ứng dụng thay đổi một object mutable trong session mà không gọi setAttribute theo cách framework theo dõi, save-mode có thể ảnh hưởng tính nhất quán.

**Đừng thay flush/save mode theo suy đoán.** Test với request/filter chain thực và quan sát session persistence theo cấu hình chính xác. Khi dùng nhiều node, chú ý **race condition** nếu các request đồng thời của cùng session thay đổi state; chiến lược merge/locking không tự được đảm bảo ở mọi backend.

### 8.3. TTL, timeout, eviction và logout

- **spring.session.timeout=30m** trong ví dụ là **thời gian không hoạt động của SP session**; không phải IdP SSO timeout.
- **AuthnRequest pending** nên có vòng đời ngắn, correlation một lần và hết hạn theo chính sách; khi dùng custom repository, cần TTL riêng phù hợp.
- Redis memory eviction có thể xóa session trước TTL nếu cấu hình/memory pressure không phù hợp.
- Khi session bị invalidate, cả A/B phải không còn chấp nhận cookie cũ sau khi state đã bị xóa khỏi shared store.
- **Local logout** làm mất session SP, không mặc nhiên đăng xuất khỏi IdP hoặc mọi SP khác; **SAML Single Logout (SLO)** cần cấu hình riêng.
- Nếu Redis không thể đọc/ghi, phải có **fail-closed behavior** hoặc degraded flow được đánh giá an ninh; không âm thầm tạo authenticated session từ dữ liệu không còn chứng minh được.

### 8.4. Redis availability và bảo vệ dữ liệu

Production cần kế hoạch cho:

- Redis **TLS** và mật khẩu/ACL/identity nếu hỗ trợ; network policy chỉ cho phép SP nodes truy cập.
- Redis HA (replica/sentinel/cluster/managed service), xử lý failover và khả năng mất bản ghi gần đây theo persistence/replication policy.
- Backup/restore nếu nghiệp vụ cần; với session data có thể ưu tiên khả năng phục hồi nhanh hơn việc khôi phục mọi phiên quá cũ.
- Giới hạn maxmemory/eviction policy, metrics số session, số lần login thất bại, latency, connection pool, timeouts.
- Keyspace namespace riêng cho app/môi trường, tránh xóa nhầm keys toàn Redis.
- Không log raw session, SAMLResponse, SecurityContext, cookie hoặc Redis credentials.
- Thử kịch bản Redis restart và leader failover thật, không chỉ health check endpoint /node.

Redis có thể là **single point of failure** nếu không có HA. Chọn distributed session không tự bảo đảm availability cao hơn local nếu shared store là một server không dự phòng.

## 9. Load balancer, HTTPS và forward headers

Kể cả đã dùng Redis, hai node phải thấy **cùng một địa chỉ SP bên ngoài**:

~~~text
Bên ngoài:
  https://sp.example.org/saml2/authenticate/corp
  https://sp.example.org/login/saml2/sso/corp
  https://sp.example.org/saml2/metadata/corp

Bên trong:
  http://sp-a:8080
  http://sp-b:8080
~~~

Nếu Spring tạo metadata hoặc AuthnRequest với **http://sp-a:8080/login/saml2/sso/corp**, IdP có thể từ chối vì ACS/Recipient/Destination không trùng public URL đã allowlist. Phải kiểm:

1. **SP entityID** thống nhất theo registration.
2. **ACS URL** giống giữa A/B và bằng URL HTTPS đã đăng ký tại IdP.
3. **IdP SSO URL, issuer và signing/verification credentials** được nạp giống nhau.
4. Forwarded proto/host/port của LB đúng, **được proxy ghi/ghi đè**, không tin header trực tiếp của client Internet.
5. Callback POST được LB route tới bất kỳ node khỏe, không vô tình chặn đường **/login/saml2/sso/** hoặc drop form fields.
6. LB response header/cookie rewriting không phá **Secure, SameSite, Path, Domain**.
7. Health check và readiness phân biệt **process sống** với **Redis/metadata dependencies đã sẵn sàng**.

**Không dùng IP address của node** làm SP entityID trong môi trường scale/failover. Mọi node trong một logical SP cần được IdP nhìn như cùng ứng dụng, trừ khi thiết kế nhiều registration/tenant có chủ đích.

### Sticky vẫn có thể dùng cùng Redis không?

Có. LB có thể tiếp tục sử dụng affinity để tối ưu cache locality/kết nối, nhưng với **Redis shared session**, **tính đúng đắn đăng nhập không được phụ thuộc vào callback luôn phải ở một node**. Đây là cách giảm rủi ro khi node fail. Đảm bảo Redis và cookie vẫn hoạt động khi affinity mất.

## 10. Chọn kiến trúc theo nhu cầu

| Bối cảnh | Khuyến nghị và đánh đổi |
| --- | --- |
| **Học tập, phát triển một instance** | **Local HttpSession** là đủ; ít thành phần. Không coi đó là HA. |
| **Hai node, downtime có thể khiến user login lại** | Có thể dùng **sticky + local sessions**, nhưng phải kiểm cookie cross-site POST và lên kế hoạch node drain. |
| **Nhiều node, rolling deploy, muốn giữ login khi một node fail** | **Spring Session Redis/JDBC** là lựa chọn đáng cân nhắc; không cần affinity cho tính đúng đắn nếu backend ổn định. |
| **Có sẵn HA RDBMS, Redis không được phép** | Xem xét **Spring Session JDBC**, schema/transaction/cleanup và tải DB. |
| **Nhiều vùng địa lý, độ trễ mạng lớn** | Phân tích latency, consistency, cookie domain, failover, region-local data, idempotency và routing policy; Redis một vùng có thể là nút nghẽn. |
| **Bảo mật nghiêm ngặt, chống login CSRF** | Giữ pending AuthnRequest ràng buộc browser/session; tránh kho lookup toàn cục chỉ bằng RelayState. |
| **Khối lượng session lớn, SLA cao** | Dự phòng shared store, quan sát metrics, test failover và phân tích chi phí serialization/Redis IO. |

**Kết luận lựa chọn:** nếu cần **failover thực sự mà vẫn giữ phiên**, chỉ sticky là chưa đủ. Nếu SLA cho phép người dùng login lại sau khi node chết, sticky có thể giảm chi phí vận hành. Nếu cần chuyển node chủ động, chia sẻ HttpSession bằng **Spring Session** giúp xử lý đúng điểm nghẽn.

## 11. Java 17 thuần: mô phỏng sticky và shared session

Chương trình sau **chạy độc lập với JDK 17**, không dùng Spring, Redis hay IdP. Nó mô phỏng session ID **demo-s1** được tạo trên A. Chỉ giữ session ID trong **local set của A** khiến B không nhận ra; một **shared set** mô phỏng kho lưu chung mà cả node đều thấy.

**SessionRoutingDemo.java**

~~~java
import java.util.HashSet;
import java.util.Set;

public class SessionRoutingDemo {
    public static void main(String[] args) {
        String sessionId = "demo-s1";

        Set<String> localA = new HashSet<>();
        Set<String> localB = new HashSet<>();
        Set<String> shared = new HashSet<>();

        localA.add(sessionId);
        shared.add(sessionId);

        System.out.println("local A before redirect: "
                + localA.contains(sessionId));
        System.out.println("local B on SAML callback: "
                + localB.contains(sessionId));
        System.out.println("shared store on B: "
                + shared.contains(sessionId));

        localA.clear(); // giả lập A chết và mất local sessions

        System.out.println("sticky fallback to local B: "
                + localB.contains(sessionId));
        System.out.println("shared store after A failure: "
                + shared.contains(sessionId));

        shared.remove(sessionId); // giả lập logout/invalidation

        System.out.println("shared store after logout: "
                + shared.contains(sessionId));
    }
}
~~~

Chạy:

~~~bash
javac SessionRoutingDemo.java
java SessionRoutingDemo
~~~

**stdout chính xác:**

~~~text
local A before redirect: true
local B on SAML callback: false
shared store on B: true
sticky fallback to local B: false
shared store after A failure: true
shared store after logout: false
~~~

Diễn giải:

- **local A before redirect=true**: request ở A thấy session đã tạo.
- **local B on SAML callback=false**: B không biết local session A.
- **shared store on B=true**: nếu backend session dùng chung, B tra được cùng ID.
- **sticky fallback to local B=false**: mất A thì sticky không thể khôi phục local state.
- **shared store after A failure=true**: shared state không phụ thuộc bộ nhớ của A trong mô phỏng.
- **shared store after logout=false**: invalidation trong shared backend khiến mọi node không còn thấy session ID.

**Giới hạn:** mô phỏng HashSet không có TLS, cookie, Redis, serialization, AuthnRequest hay chữ ký SAML. Nó **không chứng minh SAMLResponse thực sự hợp lệ**. Trong triển khai thật cần kiểm cả cookie browser, registrationId, trust IdP và SAML conditions.

## 12. Ma trận thử nghiệm end-to-end

Dùng **IdP sandbox** với metadata/cert đã tin cậy và front door HTTPS. Không dùng SAMLResponse giả unsigned để kết luận tình trạng session.

| # | Trường hợp | Kỳ vọng/điều cần đối chiếu |
| --- | --- | --- |
| 1 | Login bình thường, GET và ACS POST cùng node A | SSO thành công nếu SAML và cookie hợp lệ. |
| 2 | AuthnRequest tạo trên A, ACS callback tới B, local-only HttpSession | Có thể mất request/correlation và fail. |
| 3 | AuthnRequest tạo trên A, ACS tới B, Redis shared session | Có thể thành công khi cùng session cookie và data serialization ổn. |
| 4 | Redis shared session, login A, request /me tiếp theo chuyển B | B thấy authenticated SecurityContext. |
| 5 | Sticky local-only, đăng nhập A rồi A chết | B không có session của A, có thể cần login lại. |
| 6 | Redis shared session, đăng nhập A rồi A chết | B tiếp tục nếu Redis/keys/cookie/versions còn hợp lệ. |
| 7 | SameSite=Lax, cross-site POST không mang session cookie | Mất pending AuthnRequest bất kể local hay Redis; cần sửa cookie policy. |
| 8 | SP session cookie None/Secure đúng nhưng LB affinity cookie bị chặn | Sticky có thể mất tác dụng; Redis shared store vẫn có thể hoạt động. |
| 9 | Cookie SESSION hết hạn khi IdP MFA quá lâu | Không còn session/request đúng; không tắt InResponseTo để login bằng mọi giá. |
| 10 | Redis kết nối bị ngắt lúc lưu AuthnRequest | Không gửi flow như thể request đã lưu thành công; cần xử lý fail closed. |
| 11 | Redis bị ngắt lúc đọc callback | Không tạo authenticated session từ state thiếu; báo lỗi an toàn. |
| 12 | Redis evict session trước timeout | Mất trạng thái; cần capacity/eviction policy. |
| 13 | A/B khác serialization version của SecurityContext | B có thể không đọc session; test rolling upgrade và serializer. |
| 14 | A/B dùng khác namespace Redis | Session không chia sẻ; dù Redis cùng host cũng không đủ. |
| 15 | A/B dùng khác public SP entityID/ACS do forwarded headers sai | IdP hoặc SP từ chối destination/recipient/audience mismatch. |
| 16 | LB forward không đúng Content-Type/form fields của ACS POST | Spring không nhận SAMLResponse hợp lệ. |
| 17 | Logout tại A sau login ở B với Redis shared session | SP session bị invalidated cho các node; không suy ra IdP logout. |
| 18 | Browser gửi lại SAMLResponse sau khi request đã tiêu thụ | Không tự tạo session mới; phải chống replay/correlation. |
| 19 | Hai tab cùng login, request repository chỉ lưu một pending request | Một callback có thể thất bại; kiểm multi-tab/concurrent requests. |
| 20 | Sticky affinity hết hạn giữa redirect sang IdP và callback | Nếu local-only, dễ fail; nếu shared, không nên phụ thuộc affinity. |
| 21 | Deploy rolling update A cũ/B mới, Redis shared | Xác minh compatibility session serialization trước khi rollout. |
| 22 | Redis Sentinel/Cluster failover khi user đã đăng nhập | Kiểm mất phiên/độ trễ/connection reconnect theo HA policy. |
| 23 | Node B bị disable health check trong lúc browser POST callback | LB chọn backend khỏe; session continuity tùy store. |
| 24 | Browser đổi mạng/IP giữa SP GET và ACS POST | IP-hash affinity có thể mất; shared session không phụ thuộc IP khi cookie hợp lệ. |

Các bài test cần **quan sát request đến node nào** (nodeId/trace ID), session cookie có gửi không, Redis có bản ghi chưa, SAML request correlation có khớp không và Identity Provider có ký/đáp đúng không. Chỉ nhìn màn hình đăng nhập thành công ở một lần thử là chưa đủ.

### Cách kiểm nhanh qua browser

1. Trước login, mở **GET /node** vài lần để thấy LB phân phối, hoặc đọc LB request log theo trace ID.
2. Mở **/saml2/authenticate/corp**, ghi nhận node phát AuthnRequest bằng log đã lọc và thời điểm tạo request.
3. Sau IdP MFA, kiểm **POST /login/saml2/sso/corp** gửi cookie nào và tới node nào.
4. Sau login, gọi **/me** nhiều lần trong các điều kiện LB khác nhau.
5. Rút node đang phục vụ khỏi pool, gọi lại /me; session vẫn phải hợp lệ với shared store, hoặc theo policy chấp nhận login lại nếu dùng local sticky.
6. Logout/invalidate SP session, xác minh các node đều không chấp nhận session cũ.
7. Chạy lại với timeout, Redis restart và rolling deploy; ghi nhận kết quả và downtime chấp nhận được.

## 13. Bảng chẩn đoán lỗi nhanh

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm và sửa |
| --- | --- | --- |
| Login lúc được lúc không khi có 2 instance | AuthnRequest chỉ có trên node A, callback tới B | Kiểm LB node request/ACS; cấu hình sticky hoặc Spring Session shared. |
| Callback mất InResponseTo dù Redis có dữ liệu | Browser không gửi SESSION cookie hoặc sai session ID | Kiểm SameSite/Secure/Domain/Path, redirect hostname và rotation cookie. |
| Login được nhưng request sau yêu cầu login lại | Node khác không thấy SecurityContext hoặc session serialization lỗi | Kiểm Spring Session filter/repository, Redis keyspace và version. |
| Sticky vẫn mất login khi deploy | Node sticky bị kill, local sessions không được migrate | Dùng shared store hoặc chấp nhận re-login/drain. |
| Có Redis nhưng B không đọc session A | Khác namespace, DB, credentials, serializer hoặc TTL | So chính xác cấu hình Redis/namespace/serializer trên hai node. |
| Redis lỗi, toàn bộ SP auth gián đoạn | Shared store là dependency đơn điểm | Bật HA, monitoring, readiness và fail-closed policy. |
| Callback quay lại đúng node nhưng mất request | HttpSession hết hạn hoặc cookie bị chặn | Kiểm cookie và TTL, không đổ lỗi LB ngay. |
| SAMLResponse signature invalid | IdP verification certificate/metadata không khớp | Sửa trust/rotation, không bỏ signature validation. |
| ACS chứa http://internal:8080 | Proxy header scheme/host sai | Cấu hình external baseUrl/forwarded headers từ proxy tin cậy. |
| Truy cập /node được nhưng /me fail | Node health okay nhưng Redis/SAML dependencies không okay | Cần readiness check sâu hơn và logs phân tầng. |
| Session còn ở Redis nhưng user bị logout | Authentication/serializer/expiry/rotation/security policy mismatch | Kiểm trạng thái SecurityContext và chính sách session. |
| Sau local logout IdP vẫn tự login lại | IdP SSO session còn | Thiết kế SAML Single Logout nếu cần, phân biệt scope phiên. |
| Cùng account bị tạo nhiều phiên khi mở nhiều tab | Request repository/parallel login hoặc logic business | Kiểm correlation và session semantics, không disable CSRF. |

**Gợi ý logging an toàn:**

~~~text
event=saml_request_saved node=sp-a registration=corp trace=t-001
event=saml_response_received node=sp-b registration=corp trace=t-001
event=session_store_read node=sp-b result=found
event=saml_authentication_result result=success
~~~

Đây là **ví dụ cấu trúc log** (trace giả), không phải output tự động của Spring. Tránh log **session ID đầy đủ, cookie, SAMLResponse, Assertion, NameID, private signing key hoặc Redis password**. Trace ID phải không cho phép người khác đoán/đọc phiên.

## 14. Những sai lầm thường gặp

1. **“Sticky session là distributed session.”** Không; sticky chỉ chọn node, không chia sẻ HttpSession.
2. **“Có Redis là không cần cookie.”** Sai; browser vẫn phải gửi session identifier để node tìm đúng session.
3. **“Session cookie None là đủ cho sticky.”** Chưa chắc; LB có thể dùng affinity cookie riêng bị SameSite chặn.
4. **“Mất AuthnRequest thì bỏ InResponseTo.”** Nguy hiểm, làm yếu chống login CSRF và replay.
5. **“Dùng RelayState làm session ID.”** Sai; RelayState không mặc nhiên là browser-bound identifier đáng tin.
6. **“Redis là stateless.”** Sai; chỉ chuyển state ra khỏi tiến trình SP.
7. **“Node failover với sticky vẫn giữ session.”** Không khi local session không được sao chép.
8. **“Spring Boot 3.3 dùng cùng dependency Spring Session với Boot 4.”** Không nhất thiết; dùng dependency tương thích BOM/version.
9. **“Khác SP entityID/ACS ở A/B không ảnh hưởng.”** Sai; IdP và SAML validations có thể từ chối.
10. **“TTL Redis = Assertion lifetime = IdP SSO timeout.”** Sai; chúng là những đồng hồ/vòng đời độc lập.
11. **“Shared Redis bảo đảm mọi object session đọc được giữa mọi version.”** Sai; serialization schema phải tương thích.
12. **“Đã login tại SP thì IdP luôn logout theo.”** Sai; local logout và SAML Single Logout khác nhau.
13. **“Node khỏe là Redis cũng khỏe.”** Sai; phải có readiness và quan sát store riêng.
14. **“Có thể bỏ Secure cookie để HTTP test chạy.”** Không được suy ra production; cần HTTPS sandbox thực.
15. **“Có thể dùng mọi Redis cache công cộng để lưu SecurityContext.”** Nguy hiểm; session store cần quyền truy cập/tách mạng.
16. **“Cookie sticky hoặc session ID không phải bí mật.”** Sai; session identifier/affinity data phải được bảo vệ khỏi rò rỉ và fixation.
17. **“Tự cấu hình @EnableRedisHttpSession cùng Boot auto-config không có tác dụng phụ.”** Có thể thay đổi hành vi auto-config, cần kiểm thử.
18. **“Đọc SAMLResponse ở node B được thì bỏ qua signature/audience.”** Sai; shared session chỉ khôi phục state, không thay xác minh protocol.

## 15. Checklist production

**Kiến trúc và vận hành**

- [ ] Phân biệt local/sticky/shared session theo SLA và failure budget.
- [ ] Nếu multi-node cần failover phiên, dùng store chia sẻ thật và backend HA.
- [ ] Các node cùng app version hoặc serializer tương thích, registration/trust/namespace nhất quán.
- [ ] Tất cả node phục vụ **cùng SP public entityID và ACS HTTPS** theo hợp đồng IdP.
- [ ] Redis/JDBC có network policy, TLS/auth, TTL, capacity, backup/recovery theo nhu cầu.
- [ ] Có observability cho request store, session read/write, backend availability và SAML errors.
- [ ] Có test rolling deploy, scale-down, node kill và Redis failover.

**Cookie, browser và SAML**

- [ ] Test POST ACS từ IdP qua browser thật; session cookie được gửi và hợp lệ.
- [ ] Nếu dùng sticky, kiểm riêng affinity cookie khi cross-site POST.
- [ ] Cookie có Secure/HttpOnly/Domain/Path/SameSite phù hợp; HTTPS thực ở edge.
- [ ] Forwarded headers chỉ đến từ proxy đáng tin; Spring không tạo ACS nội bộ.
- [ ] Pending AuthnRequest giữ binding với browser/session; không chỉ lookup global bằng RelayState.
- [ ] Bảo toàn InResponseTo, issuer, signature, audience, destination, recipient, time và replay checks.
- [ ] Logout local/invalidation có hiệu lực trên mọi SP node; SLO được thiết kế riêng nếu cần.
- [ ] Không log raw session/cookie/Assertion; monitoring chỉ dùng dấu vết đã ẩn danh.

## 16. Câu hỏi ôn tập

**Câu 1.** LB luôn đưa browser về A, nhưng A chết. Với sticky + local HttpSession, B có tiếp tục session như cũ không?  
**Đáp án:** **Không**, trừ khi đã có cơ chế sao chép/session migration riêng. Sticky chỉ giữ định tuyến, không chuyển dữ liệu session.

**Câu 2.** Dùng Spring Session Redis, AuthnRequest tạo ở A và SAMLResponse POST vào B. Có thể hoàn tất login không?  
**Đáp án:** **Có thể**, nếu cùng session cookie/bản ghi Redis, request đã lưu và đọc được, phiên chưa hết hạn, serialized state tương thích và SAMLResponse đạt mọi kiểm tra bảo mật.

**Câu 3.** Redis chứa session đúng nhưng SAML callback POST không gửi cookie SP. Cần sửa Redis hay cookie?  
**Đáp án:** Trước tiên kiểm **SameSite/Secure/Domain/Path** và external HTTPS URL. Không có session ID đúng, B không thể tìm đúng bản ghi Redis.

**Câu 4.** SameSite=None trên SESSION cookie bảo đảm sticky LB luôn định tuyến về A chưa?  
**Đáp án:** **Chưa**. LB có thể dùng cookie affinity riêng, hoặc IP hash; phải kiểm từng cơ chế.

**Câu 5.** Có thể bỏ HttpSessionSaml2AuthenticationRequestRepository và tìm AuthnRequest bằng RelayState trong Redis không?  
**Đáp án:** Có thể thiết kế custom repository nhưng **không mặc nhiên an toàn**; phải duy trì browser/session binding, one-time use, TTL, chống login CSRF và replay.

**Câu 6.** Spring Session Redis có cần @EnableRedisHttpSession khi Spring Boot 3.3 auto-config đúng dependencies không?  
**Đáp án:** **Không bắt buộc**; Boot có auto-configuration. Thêm annotation thủ công khi cần kiểm soát và hiểu tác động.

**Câu 7.** Cả A/B cùng Redis nhưng đăng nhập ở A, /me tại B bị lỗi deserialize SecurityContext. Vì sao?  
**Đáp án:** Có thể object/class/serializer/schema version không tương thích, thiếu dependency hoặc session attributes không serializable; phải kiểm/đồng bộ và test rolling upgrade.

**Câu 8.** Người dùng logout khỏi SP qua node A, IdP vẫn giữ SSO session. Điều đó chứng minh Redis hỏng?  
**Đáp án:** **Không**. Local logout của SP và IdP SSO session là các phạm vi khác nhau; SAML SLO cần triển khai riêng nếu muốn logout liên ứng dụng.

## 17. Tài liệu tham khảo

1. [Spring Security — Producing AuthnRequests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html) — HttpSessionSaml2AuthenticationRequestRepository mặc định, custom repository, lưu request trong session và rủi ro login fixation nếu tra cache chỉ bằng RelayState.
2. [Spring Security — SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html) — filter chain AuthnRequest/Response, RelyingPartyRegistration, ACS, SAML session và xác thực.
3. [Spring Boot 3.3 — Spring Session](https://docs.spring.io/spring-boot/3.3/reference/web/spring-session.html) — auto-configuration Redis/JDBC, session timeout và cơ chế thay HttpSession.
4. [Spring Boot 3.3 — SameSite Cookies](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html#web.servlet.embedded-container.customizing.samesite) — thuộc tính server.servlet.session.cookie.same-site và tương tác với Spring Session.
5. [Spring Boot 3.3 — Redis](https://docs.spring.io/spring-boot/3.3/reference/data/nosql.html#data.nosql.redis) — spring-boot-starter-data-redis, connection configuration và RedisConnectionFactory.
6. [Spring Session — Spring Boot with Redis](https://docs.spring.io/spring-session/reference/3.1/guides/boot-redis.html) — dùng Spring Session Redis với Boot generation 3.x.
7. [Spring Session — Configuring Redis](https://docs.spring.io/spring-session/reference/3.3/configuration/redis.html) — namespace, flush/save mode, session serialization và index/expiry.
8. [OASIS — SAML 2.0 Profiles](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf) — Web Browser SSO, AuthnRequest/Response correlation và browser binding.

**Kết luận:** **Sticky session giữ các request ở cùng node nhưng không làm state sống qua node failure**. **Spring Session Redis/JDBC chia sẻ HttpSession thực sự**, cho phép các node phục vụ cùng browser session và pending SAML AuthnRequest nếu **cookie, serialization, trust SAML, public ACS và repository** đều đúng. Lựa chọn theo SLA và vận hành; dù dùng phương án nào, không hy sinh **InResponseTo, signature, issuer, audience và chống login CSRF** để chữa lỗi định tuyến.

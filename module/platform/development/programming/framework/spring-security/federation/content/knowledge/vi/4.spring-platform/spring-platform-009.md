# Chuẩn bị ứng dụng mẫu, IdP thử nghiệm, HTTPS và đồng bộ thời gian

> **Chủ đề:** Spring Security – federation. **Nền tảng:** Spring Boot/Spring Security, OpenID Connect (OIDC), IdP thử nghiệm, TLS và thời gian hệ thống. Bài thực hành dựng một ứng dụng web Java 17+ có đăng nhập qua Keycloak, chạy HTTPS ở địa chỉ localhost, rồi kiểm chứng những điều kiện nền tảng trước khi phát triển SAML, CAS hoặc Resource Server.

## 1. Mục tiêu và phạm vi bài thực hành

Sau bài này, người học có thể:

1. Tạo ứng dụng Spring Boot tối thiểu có `SecurityFilterChain` và một endpoint cần đăng nhập.
2. Khởi chạy IdP thử nghiệm độc lập, tạo realm, OIDC client và người dùng kiểm thử.
3. Kết nối ứng dụng với OIDC issuer bằng discovery; phân biệt địa chỉ issuer, authorization endpoint, redirect URI và client credential.
4. Bật HTTPS cho ứng dụng bằng chứng thư phát triển; hiểu sự khác nhau giữa **mã hóa đường truyền** và **tin cậy chứng thư**.
5. Kiểm tra đồng hồ của máy chạy ứng dụng, máy chạy IdP và môi trường container/VM; hiểu hệ quả với JWT, SAML, CAS và chứng thư TLS.
6. Chạy một bộ kiểm tra đúng/sai: đăng nhập thành công, sai redirect URI, chứng thư không tin cậy, sai issuer và lệch thời gian.
7. Biết những cấu hình nào **chỉ dùng trong phòng lab** và điều kiện bổ sung trước khi triển khai staging/production.

Bài triển khai một đường **OIDC Authorization Code** để có kết quả kiểm thử cụ thể. Các nguyên tắc HTTPS, danh tính issuer, đồng bộ thời gian và quản lý chứng thư tiếp tục áp dụng khi thay OIDC bằng **SAML 2.0**, **CAS** hoặc khi bổ sung **OAuth2 Resource Server**.

**Quy ước:** Những tên `lab`, `spring-lab`, `keycloak` là định danh của môi trường ví dụ. Mật khẩu và client secret phải do người học tự tạo, lưu ngoài mã nguồn. Các địa chỉ `localhost` chỉ đúng khi trình duyệt, Spring Boot và Keycloak cùng truy cập được cổng trên **một máy phát triển**.

## 2. Sơ đồ lab và ranh giới mạng

```text
Trình duyệt trên máy phát triển
       | 1. HTTPS https://localhost:8443/me
       v
[Spring Boot app]  (OIDC Relying Party / OAuth2 Client)
       | 2. Chuyển hướng trình duyệt đến IdP
       v
[Keycloak IdP/OP]  http://localhost:8081  (chỉ lab loopback)
       | 3. Người dùng đăng nhập; OP redirect về callback HTTPS
       v
https://localhost:8443/login/oauth2/code/keycloak
       | 4. Backend Spring dùng authorization code đổi token
       v
[Keycloak token endpoint]
       | 5. Spring kiểm tra ID Token và tạo phiên web
       v
https://localhost:8443/me  -> thông tin định danh thử nghiệm
```

**Các vai trò:**

| Thành phần | Trách nhiệm | Cần giữ nhất quán |
| --- | --- | --- |
| **Spring Boot web** | RP/client: tạo authorization request, nhận code, xác minh kết quả OIDC, lập phiên | `client-id`, secret, `redirect_uri` và issuer |
| **Keycloak** | OP/IdP: xác thực người dùng, phát code và token | Realm, endpoint discovery, keys, user/client, thời gian |
| **Trình duyệt** | Đi theo redirect, giữ session cookie của RP | Tin chứng thư của HTTPS app và đúng hostname |
| **Hệ điều hành/VM/Docker** | Cung cấp đồng hồ, DNS và mạng | Thời gian thật, timezone hiển thị, ánh xạ cổng |
| **TLS certificate / CA** | Xác thực endpoint và mã hóa kết nối | SAN, hạn hiệu lực, chuỗi CA, private key |

**Phân biệt hai mức bảo mật:** Ví dụ dùng **HTTPS cho ứng dụng**, nhưng **Keycloak `start-dev` qua HTTP chỉ được bind vào `127.0.0.1`** để học nhanh ở loopback. Đây **không phải mô hình HTTPS đầy đủ**. Khi triển khai staging, CI có mạng chia sẻ hoặc production, IdP **và** app đều phải dùng HTTPS với tên DNS/chứng thư được tin cậy; không đưa cấu hình IdP HTTP/`start-dev` ra mạng thật.

## 3. Chuẩn bị công cụ và lựa chọn phiên bản

### 3.1. Công cụ cần có

- **JDK 17 hoặc mới hơn**, tương thích với phiên bản Spring Boot được chọn. Kiểm tra bằng `java -version` và `javac -version`.
- **Docker Engine/Docker Desktop** để chạy Keycloak; kiểm tra `docker version`. Bật engine và cấp đủ CPU/RAM cho IdP.
- **Trình duyệt** và công cụ dòng lệnh `curl`; trên Windows PowerShell có thể gọi `curl.exe` để tránh alias `curl` của môi trường cũ.
- **Maven Wrapper** đi kèm dự án tạo từ Spring Initializr; vì vậy không bắt buộc cài Maven toàn cục.
- Công cụ `keytool` đi kèm JDK để tạo chứng thư phát triển, hoặc một CA tin cậy dành riêng cho môi trường lab như `mkcert`.
- Quyền kiểm tra trạng thái dịch vụ đồng bộ thời gian của máy host/VM.

Tạo dự án từ [Spring Initializr](https://start.spring.io/) với cấu hình minh họa:

| Thuộc tính | Giá trị dùng trong bài |
| --- | --- |
| Project | Maven |
| Language | Java |
| Spring Boot | Một bản ổn định đang được hỗ trợ, phù hợp Java đã cài |
| Group | `com.example` |
| Artifact | `federation-lab` |
| Package | `com.example.federationlab` |
| Dependencies | **Spring Web**, **Spring Security**, **OAuth2 Client** |

Tên starter cụ thể có thể thay đổi giữa các thế hệ Spring Boot; dùng danh mục dependency của Initializr cho **đúng phiên bản**. Đây là ứng dụng **Servlet web**, không phải WebFlux. Chưa cần OAuth2 Resource Server để thử login OIDC; khi xây API nhận Bearer Access Token, bổ sung dependency và cấu hình riêng.

Thử kiểm tra từ thư mục dự án:

```bash
java -version
javac -version
./mvnw -version
docker version
```

Trên Windows dùng `.\mvnw.cmd -version`. Nếu `java` và `javac` báo khác major version, cần sửa `JAVA_HOME`/`PATH` trước khi bắt đầu; không đánh giá một lỗi runtime là lỗi federation khi môi trường Java chưa sẵn sàng.

### 3.2. Giữ môi trường có thể lặp lại

Ghi nhận phiên bản Java, Spring Boot, Spring Security, Keycloak image, thông số cổng, realm/client và cách cấp chứng thư trong README nội bộ của phòng lab. Sử dụng image Keycloak cố định, ví dụ `26.8.1` như trang hướng dẫn Docker của Keycloak, để quy trình không tự thay đổi mỗi lần chạy; khi cập nhật image thì kiểm lại giao diện quản trị và luồng OIDC.

**Không lưu trong Git:** private key, `*.p12` chứa private key, mật khẩu key store, client secret, refresh token, session cookie hoặc bản dump token thật. Dùng biến môi trường hay secret manager; nếu dùng `certs/` trong project, thêm thư mục này vào `.gitignore` của dự án người học.

## 4. Khởi chạy Keycloak IdP thử nghiệm

### 4.1. Chạy container chỉ mở cổng loopback

Lệnh dưới dùng shell có Docker; chỉ bind host `127.0.0.1:8081` đến cổng `8080` trong container:

```bash
docker run -d --name keycloak-federation-lab \
  -p 127.0.0.1:8081:8080 \
  -e KC_BOOTSTRAP_ADMIN_USERNAME=labadmin \
  -e KC_BOOTSTRAP_ADMIN_PASSWORD=lab-admin-only-local \
  quay.io/keycloak/keycloak:26.8.1 \
  start-dev
```

**Mật khẩu admin ở đây là ví dụ dùng một lần trong lab bị giới hạn loopback; không dùng lại, không chuyển sang server dùng chung.** Khi vận hành thật phải dùng mật khẩu mạnh, cấp từ kho bí mật và chế độ Keycloak production. Người dùng Windows PowerShell có thể đặt lệnh thành **một dòng** (bỏ ký tự xuống dòng `\` của Bash).

Kiểm tra container và log khi cần:

```bash
docker ps --filter name=keycloak-federation-lab
docker logs keycloak-federation-lab
```

Sau khi server khởi động hoàn chỉnh, truy cập `http://localhost:8081/admin/` và đăng nhập bằng tài khoản admin lab. Nếu cổng 8081 đã dùng, chọn cổng host khác **và sửa tất cả URL issuer trong bài**; tránh thay mỗi một chỗ.

### 4.2. Tạo realm và OIDC client

Trong Keycloak Admin Console:

1. Tạo **realm** tên `lab`. Realm này tách người dùng/cấu hình lab khỏi realm quản trị.
2. Vào **Clients → Create client**, chọn **Client type = OpenID Connect**, **Client ID = spring-lab**.
3. Chọn **Client authentication = On** để dùng **confidential client** trên backend. Bật **Standard flow** (Authorization Code); không cần bật Direct Access Grants/password grant để làm bài.
4. Đặt **Valid redirect URIs** chính xác: `https://localhost:8443/login/oauth2/code/keycloak`. Nếu giao diện có Root URL/Home URL, có thể dùng `https://localhost:8443`. Không dùng wildcard `*` chỉ để giải quyết lỗi callback.
5. Lưu client và lấy **Client secret** ở tab Credentials. Đặt secret vào biến môi trường lúc chạy; không dán vào file nguồn hoặc log.
6. Tạo user `learner` trong **Users**, đặt mật khẩu tại **Credentials**, tắt **Temporary** nếu muốn đăng nhập trực tiếp mà không bị yêu cầu đổi mật khẩu trong bài. Chỉ dùng dữ liệu thử nghiệm, không nhập danh tính thật.
7. Xác nhận client được cấp scope `openid`; có thể thêm `profile`. `openid` xác định đây là yêu cầu OIDC chứ không chỉ OAuth2 authorization thuần túy.

Tên menu có thể dịch chuyển giữa các bản Keycloak; các khái niệm `Client authentication`, `Standard flow`, `Valid redirect URIs`, `Credentials` vẫn là điểm cần kiểm tra.

### 4.3. Kiểm tra OIDC Discovery trước khi viết Spring config

Truy cập URL:

```text
http://localhost:8081/realms/lab/.well-known/openid-configuration
```

Hoặc gọi:

```bash
curl -f http://localhost:8081/realms/lab/.well-known/openid-configuration
```

Phản hồi là JSON của OP; tìm các trường như `issuer`, `authorization_endpoint`, `token_endpoint`, `jwks_uri`. Giá trị `issuer` **phải tương ứng chính xác** với `http://localhost:8081/realms/lab` dùng trong Spring: cùng scheme, host, port và realm. Không tự biến `localhost` thành `127.0.0.1` trong một số URL rồi kỳ vọng mọi issuer/audience check vẫn nhất quán.

**Bẫy Docker:** Nếu sau này ứng dụng Spring cũng chạy trong một container, `localhost` bên trong container Spring trỏ về **chính container Spring**, không trỏ về host hay container Keycloak. Lúc đó phải thiết kế DNS/network để **trình duyệt, app và issuer metadata** dùng được endpoint phù hợp; không chỉ đổi issuer URI thành tên Docker service tùy tiện nếu giá trị `issuer` do Keycloak phát ra khác. Với bài này hãy chạy **Spring trên host**, Keycloak trong container để nhất quán URL.

## 5. Bật HTTPS cho ứng dụng Spring Boot

### 5.1. Vì sao cần HTTPS ngay từ lab?

Trong OIDC, trình duyệt mang authorization code về redirect URI và lưu cookie phiên của RP; TLS giúp bảo vệ các dữ liệu này trên đường truyền và xác minh máy chủ nhận. Trong SAML, trình duyệt gửi SAMLResponse tới ACS; trong CAS, trình duyệt mang service ticket về URL ứng dụng. Với production, các endpoint đăng nhập/callback cần HTTPS và chứng thư hợp lệ; ngoại lệ dùng HTTP localhost trong một số quy tắc phát triển **không phải giấy phép chạy HTTP trên mạng thật**.

HTTPS gồm hai phần:

- **Mã hóa và toàn vẹn:** kết nối TLS ngăn bên thứ ba trên đường truyền đọc/sửa nội dung trong điều kiện khóa/phiên không bị chiếm.
- **Xác thực endpoint:** trình duyệt/client kiểm tra chứng thư máy chủ, hostname/SAN, chuỗi CA và thời hạn. Một self-signed certificate mã hóa được nhưng **không tự được browser tin cậy**; người dùng không nên hình thành thói quen bỏ qua cảnh báo chứng thư.

### 5.2. Tạo keystore phát triển cho localhost

Tạo thư mục `certs` trong project rồi sinh một private key và chứng thư tự ký:

```bash
mkdir -p certs

keytool -genkeypair \
  -alias localhost \
  -keyalg RSA \
  -keysize 3072 \
  -storetype PKCS12 \
  -keystore certs/lab-https.p12 \
  -validity 30 \
  -dname "CN=localhost, OU=LocalLab, O=Training, C=VN" \
  -ext "SAN=dns:localhost,ip:127.0.0.1"
```

Trên Windows PowerShell tạo thư mục bằng `New-Item -ItemType Directory -Path certs` nếu chưa có, rồi chạy `keytool` với tất cả tham số trên một dòng. Khi `keytool` hỏi, đặt **mật khẩu keystore riêng** và lưu ở nơi an toàn. `-ext SAN` bảo đảm chứng thư khai báo tên `localhost` và loopback IP; chỉ có `CN` là chưa đủ cho kiểm tra hostname hiện đại.

Xuất **public certificate** để thử `curl` mà không tắt xác minh TLS:

```bash
keytool -exportcert -rfc \
  -alias localhost \
  -keystore certs/lab-https.p12 \
  -file certs/lab-https.pem
```

File `lab-https.pem` chỉ chứa public certificate; file `lab-https.p12` chứa private key và tuyệt đối không commit. Với browser, chứng thư tự ký thường báo không đáng tin; có thể thay bằng chứng thư từ **CA phát triển mà máy đã tin cậy** (chẳng hạn mkcert), hoặc import CA lab theo quy trình nội bộ. Tránh nhấn “bỏ qua cảnh báo” làm bước vận hành thường xuyên. Trong staging/production, dùng chứng thư do CA phù hợp cấp cho **FQDN thật** và quản lý luân chuyển tự động.

### 5.3. Cấu hình `application.yml`

File `src/main/resources/application.yml`:

```yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: file:./certs/lab-https.p12
    key-store-type: PKCS12
    key-store-password: ${LAB_TLS_KEYSTORE_PASSWORD}
    key-alias: localhost

spring:
  security:
    oauth2:
      client:
        provider:
          keycloak:
            issuer-uri: http://localhost:8081/realms/lab
        registration:
          keycloak:
            provider: keycloak
            client-id: spring-lab
            client-secret: ${LAB_OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile]
```

**Giải thích từng mối nối:**

- `server.port: 8443` và `server.ssl.*` yêu cầu embedded server nhận HTTPS bằng private key từ PKCS#12; `file:./certs/...` là đường dẫn tương đối thư mục khởi chạy.
- `provider.keycloak.issuer-uri` kích hoạt discovery OIDC; cần đúng `issuer` Keycloak thực sự công bố.
- `registration.keycloak` đặt **registrationId = keycloak**; do đó callback mặc định trở thành `/login/oauth2/code/keycloak`. Đây chính là URL đã đăng ký ở Keycloak.
- `scope: [openid, profile]` bật lớp OIDC; app nhận ID Token sau khi hoàn tất code flow.
- Hai biến môi trường giữ bí mật ra khỏi source. Không viết client secret thật trong `application.yml`, Git, ảnh chụp màn hình hay bài tập nộp.
- Ứng dụng chạy HTTPS nhưng **issuer lab HTTP chỉ trên loopback**; cần nâng cấp IdP lên HTTPS khi dùng mạng khác môi trường cá nhân.

Spring Boot có thể cấu hình TLS bằng `server.ssl` hoặc **SSL bundles** (`spring.ssl.bundle`), tùy mục tiêu. Ở đây dùng keystore trực tiếp để người mới thấy rõ chứng thư, cổng và mật khẩu; không cần thiết lập đồng thời hai cơ chế. Với cấu hình trên, Spring Boot mặc định **không tự mở thêm HTTP connector** trên 8080.

## 6. Viết ứng dụng mẫu OIDC với Spring Security

### 6.1. Class khởi động

File `src/main/java/com/example/federationlab/FederationLabApplication.java`:

```java
package com.example.federationlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FederationLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(FederationLabApplication.class, args);
    }
}
```

Spring Initializr thường sinh sẵn class ứng dụng tương đương; giữ **một** entry point phù hợp package, không tạo class trùng tên. Đây là chương trình Java dùng dependency Spring Boot/Maven, **không chạy độc lập bằng `javac` thuần**.

### 6.2. Cấu hình đăng nhập

File `src/main/java/com/example/federationlab/SecurityConfig.java`:

```java
package com.example.federationlab;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());
        return http.build();
    }
}
```

`oauth2Login` chuyển người dùng chưa đăng nhập sang flow OIDC/OAuth2, xác minh callback và thiết lập xác thực phiên web. `/` công khai giúp kiểm tra HTTPS không cần IdP; `/me` và các URL còn lại đòi đăng nhập. **Không tắt CSRF cho phiên trình duyệt**: Spring Security bảo vệ CSRF mặc định trong các trường hợp cần thiết. Không tự nhận `X-User`, `email` trên query string hay một token chưa xác minh làm kết quả đăng nhập.

### 6.3. Endpoint kiểm thử danh tính

File `src/main/java/com/example/federationlab/LabController.java`:

```java
package com.example.federationlab;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class LabController {

    @GetMapping("/")
    public String home() {
        return "Federation lab is running over HTTPS";
    }

    @GetMapping("/me")
    public Map<String, String> me(
            @AuthenticationPrincipal OidcUser user) {
        return Map.of(
            "issuer", user.getIdToken().getIssuer().toString(),
            "subject", user.getSubject()
        );
    }
}
```

**Tại sao chỉ trả `issuer` và `subject`?** Cặp `iss` + `sub` là định danh OIDC phù hợp để người học thấy mối liên hệ IdP–RP; không cần đưa raw ID Token, access token, email thật, cookie hay secret ra trang. Đừng dùng `sub` đơn lẻ làm mã người dùng toàn cục giữa nhiều issuer. Trong ứng dụng thực tế, thông tin phiên/cấu hình quyền phải được xử lý theo chính sách dữ liệu và phân quyền riêng.

Endpoint `/me` trong bài được bảo vệ bằng session sau OAuth2 login; việc hiển thị JSON **không có nghĩa** đây là OAuth2 Resource Server chấp nhận Bearer Access Token. Muốn dạy Resource Server, hãy xây API riêng với `oauth2ResourceServer`, audience/scope và bộ kiểm tra JWT tương ứng.

### 6.4. Lệnh chạy và biến môi trường

Trên Bash (Linux/macOS nếu đang dùng Bash), nhập hai secret theo prompt để tránh ghi nguyên secret vào shell history:

```bash
read -rsp "Keystore password: " LAB_TLS_KEYSTORE_PASSWORD
echo
export LAB_TLS_KEYSTORE_PASSWORD

read -rsp "OIDC client secret: " LAB_OIDC_CLIENT_SECRET
echo
export LAB_OIDC_CLIENT_SECRET

./mvnw spring-boot:run
```

Trên Windows PowerShell, ví dụ tương ứng:

```powershell
$env:LAB_TLS_KEYSTORE_PASSWORD = Read-Host "Keystore password"
$env:LAB_OIDC_CLIENT_SECRET = Read-Host "OIDC client secret"
.\mvnw.cmd spring-boot:run
```

Các giá trị nhập là **mật khẩu keystore đã tạo** và **secret client** từ Keycloak. Cách nhập PowerShell trên chỉ dùng máy lab riêng; nếu muốn che ký tự khi gõ, sử dụng cơ chế secret store an toàn được quản lý cho môi trường của mình. Sau khi thử nghiệm, có thể xóa hai biến môi trường khỏi phiên shell và ngừng container.

Khi ứng dụng khởi động, kiểm tra log thông báo embedded server lắng nghe cổng **8443**. Thông báo log có thể khác theo phiên bản; đừng phụ thuộc một câu chữ cố định. Nếu không thể tạo `ClientRegistration`, hãy kiểm tra IdP đang hoạt động, discovery URI và issuer trước khi sửa Java.

## 7. Kiểm thử HTTPS và đăng nhập từ đầu đến cuối

### 7.1. Kiểm tra TLS không bỏ qua kiểm tra chứng thư

Trên máy phát triển:

```bash
curl --cacert certs/lab-https.pem \
  -i https://localhost:8443/
```

Với endpoint `/`, phản hồi mong đợi có HTTP `200` và nội dung:

```text
Federation lab is running over HTTPS
```

Tham số `--cacert` chỉ định public certificate phù hợp; vì chứng thư bài này tự ký cho localhost, lệnh curl có thể xác thực chuỗi tin cậy mà **không dùng `-k`/`--insecure`**. Trên Windows thay `curl` bằng `curl.exe` nếu cần. `curl` không kiểm tra browser trust store theo cùng cách với tất cả trình duyệt; kiểm thử bằng browser vẫn phải bảo đảm chứng thư được tin cậy.

Kiểm tra endpoint yêu cầu xác thực:

```bash
curl --cacert certs/lab-https.pem \
  -I https://localhost:8443/me
```

Khi chưa có cookie đăng nhập, phản hồi thường **302 redirect** tới cơ chế login của Spring Security; nó chưa phải kết quả `/me`. Đừng đặt raw access token hay session cookie trong câu lệnh `curl` chia sẻ công khai để “vượt qua” đăng nhập.

### 7.2. Kiểm thử bằng trình duyệt

1. Đảm bảo browser có thể tin chứng thư localhost từ CA lab; xác minh thanh địa chỉ ghi `https://localhost:8443`.
2. Mở `https://localhost:8443/`; nhìn thấy chuỗi kiểm thử. Đây là kiểm tra Spring/HTTPS **độc lập** với IdP.
3. Mở `https://localhost:8443/me`; Spring Security chuyển tới trang đăng nhập và cung cấp tùy chọn **Keycloak**.
4. Chọn đăng nhập Keycloak; kiểm tra trình duyệt chuyển đến realm `lab` trên `http://localhost:8081`. Nhập tài khoản test `learner`.
5. Sau khi hoàn tất code flow, trình duyệt quay về HTTPS callback `/login/oauth2/code/keycloak` và tiếp tục đến `/me`.
6. Kết quả trả JSON có `issuer` trỏ đến realm `lab` và `subject` là ID ổn định do Keycloak cấp cho tài khoản test. Giá trị `subject` là duy nhất theo user, **không dự đoán trước hoặc hardcode**.
7. Tạo cửa sổ ẩn danh và vào `/me`: phải cần login mới nếu không có phiên RP; điều này giúp phân biệt phiên trình duyệt cục bộ với việc IdP còn SSO session.
8. Đăng xuất khỏi ứng dụng rồi kiểm tra lại. **Local logout** không đồng nghĩa đã kết thúc toàn bộ **OP SSO session**; federated logout cần cấu hình giao thức riêng.

Sơ đồ kết quả:

```text
GET /                       -> 200 khi TLS hoạt động
GET /me (không session)       -> redirect tới login
Chọn "Keycloak"              -> OP authorization endpoint
Đăng nhập user thử nghiệm      -> authorization code về HTTPS callback
Spring đổi code + xác minh     -> session RP được tạo
GET /me (có session)         -> 200, JSON {issuer, subject}
```

Ở bước xác minh bằng trình duyệt, `subject` có thể khác sau khi xóa/tạo lại user hoặc realm. Giá trị hiển thị là dữ liệu kiểm thử; đừng cho rằng hai lần tạo user cùng tên `learner` sẽ có `sub` giống nhau.

### 7.3. Kiểm thử “thất bại an toàn”

| Thử nghiệm | Kết quả đúng và ý nghĩa |
| --- | --- |
| Đổi redirect URI trong Keycloak thành URL không chứa callback thực | Keycloak từ chối/không thể hoàn tất auth code flow; **không** mở wildcard để né lỗi |
| Thay `issuer-uri` bằng URL sai realm/host/port | Discovery hoặc bước kiểm tra issuer thất bại; không chấp nhận token từ OP khác |
| Đổi hostname truy cập app thành tên không có trong SAN | TLS hostname verification thất bại; không tắt việc kiểm tra hostname |
| Không cung cấp `LAB_TLS_KEYSTORE_PASSWORD` | Ứng dụng không thể load private key/keystore hoặc bind HTTPS đúng; không được fallback ngầm sang HTTP |
| Không cung cấp `LAB_OIDC_CLIENT_SECRET` hoặc dùng secret sai | Token exchange không thành công; không log giá trị secret |
| Tắt Keycloak, giữ app HTTPS đang chạy | Trang `/` vẫn có thể hoạt động; login mới hoặc token exchange có thể thất bại; phân biệt lỗi IdP với lỗi TLS app |
| Gửi một ID Token trong Bearer header tới endpoint khác | Không mặc định được phép truy cập API; endpoint `/me` đang dùng **session**, không thiết kế để xác thực ID Token như Resource Server |

Các phép thử phá hỏng cấu hình chỉ thực hiện trên realm/app thử nghiệm, sau đó **khôi phục** thông số đã phê duyệt. Với certificate tự ký, browser báo `NET::ERR_CERT_AUTHORITY_INVALID` là hành vi mong đợi khi CA chưa được tin; cách sửa là thiết lập trust đúng, không viết code bỏ xác thực TLS.

## 8. Đồng bộ thời gian: điều kiện nền của federation

### 8.1. “Timezone” khác “clock skew”

**UTC** là cơ sở để đối chiếu mốc thời gian; timezone như Asia/Ho_Chi_Minh chỉ ảnh hưởng cách **hiển thị** giờ địa phương. Hai máy có timezone hiển thị khác nhau nhưng đồng bộ đúng UTC vẫn xác minh token bình thường. Ngược lại, hai máy cùng timezone nhưng **lệch đồng hồ thực** có thể khiến xác thực thất bại.

Các giá trị cần phân biệt:

- `iat`: thời điểm token được phát, có thể dùng trong một số kiểm tra chính sách.
- `nbf`: token **không hợp lệ trước** thời điểm này.
- `exp`: token **hết hiệu lực** từ thời điểm này.
- `auth_time` trong OIDC: thời điểm OP xác thực người dùng, liên quan yêu cầu `max_age`/reauthentication khi có.
- `NotBefore` và `NotOnOrAfter` trong SAML: cửa sổ hiệu lực của assertion/conditions.
- TTL/expiration của **authorization code**, **CAS Service Ticket**, cookie phiên, request correlation và một số nonce/replay store.
- `Not Before`/`Not After` của **chứng thư TLS**: sai đồng hồ có thể làm chứng thư tưởng như chưa hiệu lực hoặc đã hết hạn.

**Ví dụ tính thời gian (UTC) độc lập với timezone:**

```text
Issuer tạo token:
  nbf = 2026-11-07T03:00:00Z
  exp = 2026-11-07T03:05:00Z

Thời gian thật ở thời điểm request: 2026-11-07T03:01:00Z
Clock của Spring Boot bị chạy nhanh +6 phút:
  Spring thấy 2026-11-07T03:07:00Z
=> Spring có thể từ chối token vì đã quá exp,
   dù token mới được cấp khoảng 1 phút theo thời gian thật.

Clock của Spring Boot chạy chậm -3 phút:
  Spring thấy 2026-11-07T02:58:00Z
=> Spring có thể từ chối token vì trước nbf.
```

Ví dụ mô tả nguyên lý; quyết định thực tế còn phụ thuộc mức `clock skew`/leeway mà validator áp dụng. **Không dùng việc thay timezone hay bỏ kiểm tra `exp`** để chữa một đồng hồ sai.

### 8.2. Xem trạng thái NTP/NTS và đồng hồ

Trên Linux có systemd, kiểm tra:

```bash
date -u +"%Y-%m-%dT%H:%M:%SZ"
timedatectl status
timedatectl show -p NTPSynchronized
```

Nếu hệ thống dùng chrony, có thể kiểm tra offset và nguồn bằng:

```bash
chronyc tracking
chronyc sources -v
```

Trên Windows (PowerShell hoặc Command Prompt):

```powershell
Get-Date -Format o
w32tm /query /status
w32tm /query /source
```

Trên macOS có thể xem UTC bằng `date -u` và kiểm tra cấu hình “Set time and date automatically” cùng nguồn đồng bộ của hệ điều hành. Lệnh có thể cần quyền thích hợp; nếu môi trường không dùng `systemd` hoặc `chrony`, kiểm tra bằng dịch vụ thời gian thực sự đang được vận hành trên máy đó.

**Cần kiểm tra những máy nào?** Host chạy Spring Boot, host/container/VM chạy IdP, gateway/proxy có xử lý token, máy API Resource Server, và hệ thống cấp/lưu chứng thư. Trong Docker, container Linux thường chia sẻ kernel clock của host/VM; trên Docker Desktop còn có lớp VM. Khi phát hiện drift, kiểm tra đồng hồ **host và VM**, không cố sửa thời gian trong một container không có quyền và không xem đó là biện pháp lâu dài.

### 8.3. Cấu hình clock skew có kiểm soát

Spring Security Resource Server khi xác minh JWT dùng `JwtTimestampValidator` để đánh giá `nbf` và `exp`; tài liệu Spring Security mô tả mặc định mức clock skew khoảng **60 giây** cho Resource Server và cho phép cấu hình khi cần. Đây là **khoảng dung sai nhỏ**, không phải lý do bỏ đồng bộ NTP. Các bộ kiểm tra ID Token/OIDC, SAML assertion và CAS ticket có cơ chế/giới hạn riêng; **không suy ra cùng mặc định 60 giây cho mọi giao thức**.

Nếu cần can thiệp ở Resource Server, hãy:

1. Đo lệch đồng hồ trước, xác nhận NTP thực sự chạy, sửa nguyên nhân ở hạ tầng.
2. Chọn leeway tối thiểu phù hợp với sai số đo và chính sách bảo mật, thay vì kéo dài hàng phút để che lỗi.
3. Không tự xóa kiểm tra `exp`/`nbf`, chữ ký, issuer hoặc audience; các validator vẫn phải phối hợp đúng.
4. Cảnh báo khi offset vượt ngưỡng do nhóm vận hành thống nhất; định kỳ thử nghiệm token gần thời điểm hết hạn.

**Khác nhau giữa một số lỗi:** `invalid_grant` tại token endpoint có thể liên quan code bị dùng lại, hết hạn, PKCE/redirect URI không khớp hoặc điều kiện server khác; **không kết luận cứ `invalid_grant` là lệch thời gian**. Nếu token vừa cấp nhưng luôn “expired” hoặc SAML assertion “not yet valid”, lúc đó kiểm tra UTC giữa các hệ thống là bước chẩn đoán ưu tiên.

## 9. Mở rộng lab sang SAML, CAS và OAuth Resource Server

Khi phần OIDC cơ bản đã chạy, **giữ hạ tầng HTTPS + đồng bộ thời gian** rồi bổ sung mỗi giao thức ở một cấu hình riêng.

| Muốn thử | Ứng dụng Spring đóng vai trò | Cần chuẩn bị ở IdP hoặc server trung tâm | Giá trị thời gian/định danh đặc biệt |
| --- | --- | --- | --- |
| **SAML 2.0 Web SSO** | SAML Service Provider/Relying Party | SAML metadata, `entityID`, certificate ký assertion, SSO endpoint, ACS URL | `NotBefore`/`NotOnOrAfter`, `Destination`, `AudienceRestriction`, `InResponseTo` khi áp dụng |
| **OIDC login** | OIDC RP | OIDC discovery, issuer, client, redirect URI, secret/PKCE, JWK Set | `iss`, `aud`, `exp`, `nonce`, `auth_time` theo luồng |
| **CAS login** | CAS service | CAS login và `/serviceValidate`, service URL đã đăng ký, kênh TLS | Service Ticket ngắn hạn/dùng một lần, phiên CAS, đúng `service` |
| **OAuth2 API** | Resource Server | Authorization Server phát Access Token có audience/scope dành cho API; JWKS hoặc introspection | `iss`, `aud`, `exp`/`nbf`, scope/role và quyền nghiệp vụ |

**Không trộn bằng chứng:** SAML Assertion, OIDC ID Token, CAS Service Ticket và OAuth Access Token **không hoán đổi trực tiếp**. Một Keycloak realm có thể hỗ trợ OIDC/SAML, nhưng cấu hình Spring Security phải chọn `oauth2Login` hay `saml2Login` tương ứng; CAS đòi luồng ticket validation riêng. Resource Server xác minh Access Token cho API, còn bài `/me` hiện tại dựa trên session web sau OIDC login.

Bài mở rộng có thể triển khai thêm một ứng dụng API với `spring-boot-starter-oauth2-resource-server` và cấu hình `issuer-uri`/`audiences`, sau đó kiểm tra bearer token đúng/sai issuer, audience và scope. Việc dùng chung IdP **không biến ID Token của RP thành Access Token dành cho API**.

## 10. Chuyển từ lab sang staging/production đúng cách

**Mục tiêu vận hành:** Cả trình duyệt → RP và RP → OP, cũng như các cuộc gọi tới token endpoint/JWKS/metadata phải dùng kết nối TLS xác thực; hostname, issuer và redirect URI phải phù hợp với hạ tầng thật.

1. **IdP production:** Dùng tên miền thật như `login.company.example`; cấu hình Keycloak chế độ production, database phù hợp, HA/backup, TLS và host/proxy theo hướng dẫn triển khai. Không tiếp tục `start-dev`, tài khoản admin mặc định, HTTP public hoặc cấu hình test user trên môi trường thật.
2. **Ứng dụng và callback:** Đặt `https://app.company.example/login/oauth2/code/keycloak` làm redirect URI chính xác; cập nhật `issuer-uri` thành issuer công bố qua HTTPS. `http://` và `https://`, `localhost` và FQDN là các origin/issuer khác nhau.
3. **Chứng thư và trust:** Cấp chứng thư từ CA được tin; tự động gia hạn và quản lý private key; cấu hình trust store Java khi hệ thống dùng CA nội bộ. Không tắt xác thực TLS trong Java client.
4. **Reverse proxy:** Nếu TLS kết thúc ở ingress/proxy, backend có thể chạy trên mạng riêng nhưng phải được bảo vệ theo topology; cấu hình forwarded headers **chỉ tin từ proxy đã biết**, bảo đảm Spring tạo `{baseUrl}` và `redirect_uri` đúng scheme HTTPS và host public. Không nhận mù quáng `X-Forwarded-Proto`/`Host` từ mọi client.
5. **Secret:** Chuyển client secret, keystore password và signing key sang secret manager; phân quyền và xoay vòng có kế hoạch. Tách `dev/staging/prod` bằng client/realm/issuer/key khác nhau khi phù hợp.
6. **Clock:** Mọi host, node, VM và proxy dùng nguồn đồng bộ thời gian đáng tin, có metric về offset và cảnh báo drift. Đánh giá độ chính xác của NTP/NTS theo chính sách hệ thống.
7. **Session/cookie:** Bật `Secure` và `HttpOnly` cho session cookie, cấu hình SameSite phù hợp với các redirect/cross-site request cần thiết, chống CSRF/session fixation; dùng cookie domain và timeout chặt.
8. **Giới hạn quyền:** Liệt kê redirect URI chính xác, scope tối thiểu, client authentication/PKCE phù hợp, role mapping có phê duyệt, logout và revocation khi được hỗ trợ.
9. **Kiểm thử trước mở truy cập:** Discovery, HTTPS chain, callback, token validation, user mapping, người dùng bị khóa, clock skew, expired cert, key rotation, IdP downtime và fail-closed.
10. **Giám sát:** Giữ log correlation, lỗi xác thực theo nhóm, hiệu lực chứng thư, drift, sức khỏe IdP, nhưng không ghi raw ID Token, Access Token, SAML Assertion, CAS ticket, client secret hoặc session cookie.

**Chú ý về chứng thư:** Khi HTTPS ở IdP dùng CA riêng, Java client phải tin CA đó; browser tin cert chưa đồng nghĩa JVM cũng tin. `PKIX path building failed` thường là vấn đề trust chain/hostname, không giải quyết bằng việc đổi `client-id` hay tắt SSL verification.

## 11. Khắc phục lỗi theo dấu hiệu

| Dấu hiệu | Nguyên nhân thường gặp | Cách kiểm tra/sửa |
| --- | --- | --- |
| `Connection refused` ở cổng 8081 | Docker chưa chạy, container chưa ready, bind sai cổng | `docker ps`/`docker logs`, kiểm tra `http://localhost:8081/admin/` |
| Spring không khởi động vì thiếu issuer metadata | Keycloak/realm chưa sẵn sàng, issuer-uri sai, network từ JVM không tới OP | Gọi `/.well-known/openid-configuration` trực tiếp; so sánh issuer, DNS và cổng |
| `invalid_redirect_uri` hoặc callback bị từ chối | Scheme, host, port hoặc path khác cấu hình client | So sánh chính xác redirect URI thực tế và Valid redirect URIs; không dùng wildcard |
| OAuth2 login trả `invalid_client` | Sai client secret, client auth mode, client ID hoặc registration | Kiểm tra client authentication và secret ở Keycloak; cấp lại secret khi cần |
| Trình duyệt cảnh báo `ERR_CERT_AUTHORITY_INVALID` | Chứng thư app tự ký/CA lab chưa được tin | Dùng CA phát triển tin cậy, kiểm tra SAN/chain; tránh bypass |
| `SSLHandshakeException`, `PKIX path building failed` từ JVM | JVM không tin chứng thư IdP hoặc endpoint HTTPS | Kiểm tra CA/truststore, chứng thư đúng DNS, chain đầy đủ |
| `Issuer mismatch` | `iss` do OP phát khác issuer cấu hình | So sánh nguyên chuỗi `issuer` trong discovery và cấu hình; tránh đổi localhost/127.0.0.1 tùy tiện |
| `Token expired` hoặc `not yet valid` ngay sau login | Đồng hồ lệch, token quá hạn hoặc cấu hình thời hạn không phù hợp | So sánh UTC/NTP trên các máy; kiểm tra `exp`, `nbf`, skew hợp lệ |
| OAuth code bị từ chối hoặc `invalid_grant` | Code hết hạn/dùng lại, redirect URI/PKCE sai, time drift hoặc chính sách IdP | Lấy request mới, kiểm tra đúng dòng thời gian và correlation; không replay code |
| 302 liên tục hoặc app chuyển về HTTP | Proxy forwarded headers, `{baseUrl}`, cookie Secure, reverse-proxy scheme không chuẩn | Kiểm tra HTTPS public URL, trusted proxies, cookie, redirect URI |
| Trang `/me` không có `OidcUser` | Client không dùng OIDC, thiếu scope `openid` hoặc chưa đăng nhập | Kiểm tra registration scope, OIDC response, `oauth2Login` và session |
| Bất chợt thất bại sau xoay cert/key | Browser/JVM truststore/JWKS cache hoặc metadata chưa cập nhật | Kiểm tra chuỗi tin cậy và quy trình rollover; không tắt validation |

**Quy trình phân loại lỗi nhanh:**

```text
Java/Docker lỗi?             -> sửa môi trường chạy
TLS GET "/" thất bại?        -> sửa cert/port/keystore
GET "/" được, IdP không lên? -> sửa container/realm/network
Discovery không khớp?        -> sửa issuer/host/port
IdP từ chối authorize?       -> kiểm tra client, redirect URI, user
Callback/token exchange lỗi? -> kiểm tra secret, code, issuer, thời gian
Login xong nhưng /me 401?    -> kiểm tra session và filter chain
Sai exp/nbf?                 -> đo clock offset trước khi chỉnh leeway
```

## 12. Checklist nghiệm thu một môi trường federation nền tảng

- [ ] `java -version`/`./mvnw -version`/Docker hoạt động, dự án Spring Boot có Web + Security + OAuth2 Client.
- [ ] Keycloak chỉ bind loopback ở phòng lab, realm `lab` và OIDC client `spring-lab` hoạt động.
- [ ] Endpoint discovery trả issuer đúng với `issuer-uri` ứng dụng đã khai báo.
- [ ] Redirect URI đã đăng ký khớp tuyệt đối `https://localhost:8443/login/oauth2/code/keycloak`.
- [ ] App mở HTTPS 8443, chứng thư có SAN `localhost`, còn hạn và được client kiểm tra; test `curl --cacert` thành công.
- [ ] Private key, key store password và client secret không commit/không ghi log.
- [ ] `/` công khai 200; `/me` chưa đăng nhập chuyển tới login; đăng nhập Keycloak thành công trả ID của user test.
- [ ] Các tình huống redirect sai, issuer sai và TLS không tin cậy bị **từ chối** đúng cơ chế.
- [ ] Đồng hồ UTC và dịch vụ đồng bộ thời gian của host/VM/IdP được kiểm tra; không dùng clock skew quá lớn để che lỗi NTP.
- [ ] Biết rõ khi nào lab HTTP IdP phải được thay bằng **HTTPS IdP** và cấu hình hạ tầng thật.
- [ ] Có quy trình đổi secret, xoay cert/key, tắt tích hợp và xem log an toàn để làm các bài federation tiếp theo.

**Kết quả mong đợi:** Một môi trường học có thể khởi chạy lại, truy cập app bằng HTTPS, đăng nhập qua IdP test bằng OIDC, quan sát issuer/subject và kiểm chứng đồng hồ chính xác. Khi những nền tảng này ổn định, các bài SAML/CAS/OAuth2 sau đó sẽ tập trung vào **giao thức và ranh giới tin cậy**, thay vì bị nhiễu bởi lỗi cổng, chứng thư hoặc thời gian.

## 13. Tài liệu đối chiếu

- [Spring Initializr](https://start.spring.io/) — tạo ứng dụng mẫu phù hợp bản Spring Boot được hỗ trợ.
- [Spring Security — OAuth2 Login Core](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html) — `ClientRegistration`, OIDC discovery, redirect URI và filter.
- [Spring Security — OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/) — flow và sự khác nhau giữa OAuth2 client và Resource Server.
- [Spring Boot — Embedded Web Server SSL](https://docs.spring.io/spring-boot/how-to/webserver.html) — `server.ssl`, keystore, HTTPS connector.
- [Spring Boot — SSL Bundles](https://docs.spring.io/spring-boot/reference/features/ssl.html) — cấu hình key/trust material dùng lại.
- [Keycloak — Getting Started on Docker](https://www.keycloak.org/getting-started/getting-started-docker) — chạy Keycloak dev, tạo realm và OIDC client.
- [Keycloak — Running in a Container](https://www.keycloak.org/server/containers) — container options, startup mode và lưu ý production.
- [Spring Security — Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html) — `exp`/`nbf`, issuer, clock skew của JWT validator.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html) — issuer, ID Token và validation.
- [SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html) — luồng SP/IdP, ACS và điều kiện assertion.

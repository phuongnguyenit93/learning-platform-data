# Cấu hình VaultEndpoint theo môi trường

Trong module **SPRING_VAULT**, ứng dụng Java kết nối với HashiCorp Vault qua `VaultTemplate` để đọc KV secrets, thực hiện Transit encryption, thao tác PKI và các API liên quan đến token/lease. Trước mọi thao tác đó, ứng dụng cần biết **gửi request đến Vault nào**. Trong chương **Cấu hình Java**, đối tượng `VaultEndpoint` thể hiện lựa chọn này.

Bài học hướng dẫn cấu hình một ứng dụng Spring Boot chạy qua ba môi trường **local, staging và production** mà không phải sửa mã nguồn khi đổi địa chỉ Vault. Trọng tâm là cấu hình bên ngoài ứng dụng, kiểm tra URI, TLS và mô hình kết nối đúng khi triển khai với container hoặc Vault HA. Cuối bài có ví dụ dùng `VaultTemplate` để đọc một secret KV v2 và bảng chẩn đoán lỗi thường gặp.

## 1. VaultEndpoint là gì và không phải là gì?

`VaultEndpoint` thuộc `org.springframework.vault.client`, chứa những phần cơ bản của địa chỉ server: **scheme**, **host** và **port**.

~~~text
https://vault.staging.example.internal:8200
  │                 │                 │
scheme            host               port
~~~

Ví dụ Java tạo endpoint:

~~~java
VaultEndpoint endpoint =
        VaultEndpoint.create("vault.staging.example.internal", 8200);
endpoint.setScheme("https");
~~~

Đối với Vault dev server chạy ngay trên máy phát triển:

~~~java
VaultEndpoint endpoint = VaultEndpoint.create("127.0.0.1", 8200);
endpoint.setScheme("http");
~~~

**Endpoint không chứa token, policy, mount KV hoặc tên secret.** Những thông tin đó do các thành phần khác chịu trách nhiệm.

~~~mermaid
flowchart LR
    A["VAULT_ADDR<br/>cấu hình môi trường"] --> B["VaultEndpoint"]
    C["ClientAuthentication<br/>danh tính ứng dụng"] --> D["VaultTemplate"]
    B --> D
    D --> E["Vault HTTP API"]
    E --> F["KV / Transit / PKI"]
~~~

Đặc biệt cần phân biệt:

| Khái niệm | Ví dụ | Vai trò |
| --- | --- | --- |
| Base URL của Vault | `https://vault.example.internal:8200` | Địa chỉ của `VaultEndpoint` |
| API prefix | `/v1` | Phần HTTP API mà client xử lý |
| Secrets engine mount | `secret` | Tên mount KV |
| Đường dẫn secret | `demo/app` | Secret bên trong mount |
| Đường dẫn HTTP của KV v2 | `/v1/secret/data/demo/app` | Request đọc KV v2 thực tế |

Không đưa `/v1` hay `/secret/data/demo/app` vào `VAULT_ADDR`. `VaultEndpoint` cần trỏ tới **base URL**, còn đường dẫn API do Spring Vault xây dựng khi gọi thao tác thích hợp.

## 2. Vì sao endpoint phải khác nhau theo môi trường?

Trong thực tế, cùng một bản build thường chạy ở các nơi có DNS, chính sách mạng và cụm Vault khác nhau:

| Môi trường | `VAULT_ADDR` minh họa | Yêu cầu chính |
| --- | --- | --- |
| Local | `http://127.0.0.1:8200` | Dev server hoặc Vault test; HTTP chỉ cho thực hành cục bộ |
| Staging | `https://vault.staging.example.internal:8200` | Có TLS, cấu hình mạng và danh tính dành cho staging |
| Production | `https://vault.prod.example.internal:8200` | TLS đáng tin cậy, endpoint ổn định, policy ít quyền nhất |

Tên máy dưới `example.internal` chỉ là **ví dụ**, không phải địa chỉ Vault có thể dùng ngay.

Không nên hardcode URL trong Java rồi sửa lại mỗi lần deploy. Cấu hình bên ngoài cho phép:
- Dùng cùng artifact Java trên các môi trường.
- Không tạo mặc định `localhost` nguy hiểm cho production.
- Chỉ định một địa chỉ Vault độc lập với token, workload identity và policy.
- Dễ chuyển sang DNS Service hoặc load balancer khi vận hành Vault HA.

**Đổi endpoint không đồng nghĩa đã đổi identity hay policy.** Ứng dụng vẫn cần phương thức xác thực, quyền đọc và secret tồn tại ở đúng Vault của môi trường đó.

## 3. Cấu hình Spring Boot theo profile và biến môi trường

Ví dụ dùng Spring Boot, Java 17 trở lên, cùng dependency `spring-vault-core`:

~~~xml
<dependency>
    <groupId>org.springframework.vault</groupId>
    <artifactId>spring-vault-core</artifactId>
</dependency>
~~~

Đoạn `pom.xml` giả định dự án đã quản lý phiên bản Spring Vault tương thích bằng dependency management/BOM. Nếu chưa có, hãy khai báo một phiên bản tương thích với Spring Framework của dự án.

### 3.1. Cấu hình chung: bắt buộc cung cấp VAULT_ADDR

Trong `src/main/resources/application.yml`:

~~~yaml
app:
  vault:
    uri: ${VAULT_ADDR}
~~~

`app.vault.uri` là **thuộc tính do bài thực hành tự định nghĩa**. Biểu thức `${VAULT_ADDR}` đọc biến môi trường đã cấp cho tiến trình Java; Spring Vault không mặc nhiên yêu cầu thuộc tính `app.vault.uri`.

Ở staging/production, nếu không có `VAULT_ADDR`, việc lấy `app.vault.uri` sẽ thất bại. Cách này giúp phát hiện lỗi cấu hình ngay trong quá trình khởi động.

### 3.2. Profile local: một fallback có giới hạn

Trong `src/main/resources/application-local.yml`:

~~~yaml
app:
  vault:
    uri: ${VAULT_ADDR:http://127.0.0.1:8200}
~~~

Khi bật profile `local`, ứng dụng có thể dùng dev server ở `http://127.0.0.1:8200` nếu `VAULT_ADDR` không được đặt. Khi biến môi trường có mặt, nó vẫn được ưu tiên trong placeholder.

Ví dụ Bash:

~~~bash
export SPRING_PROFILES_ACTIVE=local
export VAULT_ADDR=http://127.0.0.1:8200
export VAULT_TOKEN=dev-only-token
~~~

Ví dụ PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "local"
$env:VAULT_ADDR = "http://127.0.0.1:8200"
$env:VAULT_TOKEN = "dev-only-token"
~~~

`VAULT_TOKEN` chỉ phục vụ code xác thực bằng token tĩnh ở mục sau. Token demo này **không dùng cho production**.

### 3.3. Staging và production: cấu hình bắt buộc

Các giá trị deployment mẫu cho staging:

~~~text
SPRING_PROFILES_ACTIVE=staging
VAULT_ADDR=https://vault.staging.example.internal:8200
~~~

Và cho production:

~~~text
SPRING_PROFILES_ACTIVE=prod
VAULT_ADDR=https://vault.prod.example.internal:8200
~~~

Cần cấp `VAULT_ADDR` từ Kubernetes Deployment, container runtime, hệ thống triển khai hoặc nguồn cấu hình được quản lý. Không viết token, AppRole SecretID hoặc thông tin xác thực bí mật vào các file YAML trong Git.

Khi có cả `application.yml` và `application-local.yml`, file của profile local có thể ghi đè thuộc tính chung. Các nguồn cấu hình Spring Boot khác có độ ưu tiên cao hơn, ví dụ một số command-line properties, cũng có thể ghi đè giá trị hiệu lực. Vì vậy khi chẩn đoán sự cố, hãy xác định **giá trị thực mà process Java nhận**, không chỉ đọc một file YAML trong repository.

## 4. Tạo VaultEndpoint từ URI một cách rõ ràng

Một cách cấu hình Spring Vault là kế thừa `AbstractVaultConfiguration`. Lớp cơ sở cung cấp hạ tầng, bao gồm `VaultTemplate`; ứng dụng phải triển khai `vaultEndpoint()` và `clientAuthentication()`.

Tạo `AppVaultConfiguration.java`:

~~~java
package com.example.vault;

import java.net.URI;
import java.util.Arrays;
import java.util.Locale;

import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.vault.authentication.ClientAuthentication;
import org.springframework.vault.authentication.TokenAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.config.AbstractVaultConfiguration;

@Configuration
public class AppVaultConfiguration extends AbstractVaultConfiguration {

    private final Environment environment;

    public AppVaultConfiguration(Environment environment) {
        this.environment = environment;
    }

    @Override
    public VaultEndpoint vaultEndpoint() {
        String raw = environment.getRequiredProperty("app.vault.uri");
        URI uri = URI.create(raw.trim());

        String scheme = uri.getScheme();
        String host = uri.getHost();

        if (host == null || scheme == null
                || (!"http".equalsIgnoreCase(scheme)
                    && !"https".equalsIgnoreCase(scheme))) {
            throw new IllegalArgumentException(
                    "app.vault.uri phải có dạng http(s)://host[:port]");
        }

        String path = uri.getRawPath();
        if (uri.getRawUserInfo() != null
                || (path != null && !path.isEmpty() && !"/".equals(path))
                || uri.getRawQuery() != null
                || uri.getRawFragment() != null) {
            throw new IllegalArgumentException(
                    "app.vault.uri chỉ được chứa scheme, host và port");
        }

        boolean local = Arrays.asList(
                environment.getActiveProfiles()).contains("local");

        // Giới hạn HTTP ở profile local cho bài thực hành.
        if (!local && !"https".equalsIgnoreCase(scheme)) {
            throw new IllegalArgumentException(
                    "Vault endpoint ngoài local phải dùng HTTPS");
        }

        int port = uri.getPort();
        if (port == -1) {
            port = "https".equalsIgnoreCase(scheme) ? 443 : 80;
        }
        if (port < 1 || port > 65535) {
            throw new IllegalArgumentException(
                    "Port Vault phải nằm trong khoảng 1..65535");
        }

        VaultEndpoint endpoint = VaultEndpoint.create(host, port);
        endpoint.setScheme(scheme.toLowerCase(Locale.ROOT));
        return endpoint;
    }

    @Override
    public ClientAuthentication clientAuthentication() {
        // Chỉ là phương án học tập, cần thay theo workload ở production.
        String token = environment.getRequiredProperty("VAULT_TOKEN");
        if (token.isBlank()) {
            throw new IllegalArgumentException(
                    "VAULT_TOKEN không được để trống");
        }
        return new TokenAuthentication(token);
    }
}
~~~

**Những điểm cần chú ý:**

1. `getRequiredProperty("app.vault.uri")` buộc cấu hình phải có giá trị; thiếu biến môi trường trên staging/prod sẽ báo lỗi.
2. `URI.create(...)` phân tách URL và làm lộ lỗi cấu trúc. Chỉ chấp nhận scheme `http` hoặc `https`, host hợp lệ, không có userinfo, query, fragment hay đường dẫn API.
3. HTTP chỉ được chấp nhận khi profile chứa `local`. Đây là guard bổ sung của ví dụ; môi trường chạy vẫn phải được cấu hình profile đúng.
4. Nếu URL không có port, code dùng cổng chuẩn `80` cho HTTP hoặc `443` cho HTTPS. Vault server thường dùng `8200`, vì vậy **nên chỉ định `:8200`** nếu đây là cổng thực tế; `443` phù hợp khi có reverse proxy/ingress phục vụ cổng đó.
5. `clientAuthentication()` trả về `TokenAuthentication` để dễ học; token tĩnh không tự gia hạn khi hết TTL. Khi dùng Kubernetes auth, AppRole hay hình thức identity theo workload, cần thay chiến lược xác thực và quản lý token/session phù hợp.
6. Vì `AbstractVaultConfiguration` đã cung cấp cấu hình hạ tầng, không cần tự đăng ký thêm một bean `VaultTemplate` trong ví dụ.

Nếu ứng dụng đồng thời bật Spring Cloud Vault hoặc cấu hình Vault thủ công khác, cần kiểm tra việc trùng bean/hạ tầng trước khi dùng lớp này.

**Phân biệt phạm vi:** kiểm tra URI chỉ xác nhận cấu trúc địa chỉ; nó không bảo đảm DNS phân giải được, TLS được tin cậy, Vault đang hoạt động hay token có đủ quyền. Các bước đó cần xác minh bằng kết nối thực tế.

## 5. Thực hành đọc một secret KV v2 để xác minh endpoint

Một endpoint hợp lệ về cú pháp vẫn có thể trỏ sai Vault. Hãy dùng một phép đọc secret có kiểm soát để xác minh đường đi từ ứng dụng tới Vault.

### 5.1. Chuẩn bị Vault dev

Terminal thứ nhất:

~~~bash
vault server -dev -dev-root-token-id=dev-only-token
~~~

Terminal thứ hai (đã đặt biến môi trường như mục 3):

~~~bash
vault kv put secret/demo/app username=demo_user
vault kv get secret/demo/app
~~~

Giả định dev server có mount `secret` thuộc KV v2. Có thể kiểm tra bằng `vault secrets list -detailed`. Dev server và root token trong ví dụ **chỉ dùng cục bộ**, không triển khai thật.

### 5.2. Inject VaultTemplate để đọc

Tạo `VaultConnectionCheck.java`:

~~~java
package com.example.vault;

import java.util.Map;

import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.core.VaultTemplate;
import org.springframework.vault.support.VaultResponse;

@Service
public class VaultConnectionCheck {

    private final VaultTemplate vaultTemplate;

    public VaultConnectionCheck(VaultTemplate vaultTemplate) {
        this.vaultTemplate = vaultTemplate;
    }

    public boolean canReadSampleSecret() {
        VaultResponse response = vaultTemplate
                .opsForKeyValue("secret", KeyValueBackend.KV_2)
                .get("demo/app");

        Map<String, Object> data =
                response == null ? null : response.getData();

        return data != null
                && data.get("username") instanceof String name
                && !name.isBlank();
    }
}
~~~

Phần config tạo hạ tầng kết nối, còn service inject `VaultTemplate` để làm nghiệp vụ. Trong đoạn trên, `"secret"` là KV mount, `"demo/app"` là secret path **tương đối**. Spring Vault tự xử lý đường dẫn HTTP đặc thù KV v2, tương đương request `GET /v1/secret/data/demo/app`. Không chèn `data/` vào `get(...)`.

Nếu muốn kiểm tra khi khởi động, có thể thêm phương thức bean sau **bên trong lớp `@SpringBootApplication`**:

~~~java
@Bean
CommandLineRunner verifyVault(VaultConnectionCheck check) {
    return args -> {
        if (!check.canReadSampleSecret()) {
            throw new IllegalStateException(
                    "Không đọc được secret mẫu từ Vault");
        }
        System.out.println("Kết nối Vault và đọc KV v2 thành công");
    };
}
~~~

Đoạn trên cần import `org.springframework.boot.CommandLineRunner` và `org.springframework.context.annotation.Bean`. Không log token, `VaultResponse` hoặc nội dung secret. Việc để một phép đọc thất bại làm dừng startup là lựa chọn trong demo, không phải quy tắc bắt buộc cho mọi service production.

## 6. Đổi môi trường: endpoint, danh tính và policy là ba việc khác nhau

Ví dụ một service ở production gọi KV v2 mount `secret`, path `demo/app`. Token của service phải có policy thích hợp, chẳng hạn:

~~~hcl
path "secret/data/demo/app" {
  capabilities = ["read"]
}
~~~

Một phép đọc trên KV v1 lại có dạng path khác. Vì vậy HTTP 403 có thể xảy ra ngay cả khi `VAULT_ADDR` đúng, DNS hoạt động và token chưa hết hạn.

| Thành phần | Ví dụ | Điều cần cấu hình |
| --- | --- | --- |
| Endpoint | `https://vault.prod.example.internal:8200` | `VAULT_ADDR`, DNS, mạng, TLS |
| Authentication | Token hoặc cơ chế đăng nhập workload | `ClientAuthentication`, Vault auth role, session |
| Authorization | `read` tại `secret/data/demo/app` | Policy gắn với đúng identity/token |
| Data | KV v2 ở mount `secret` | Secrets engine, đường dẫn, dữ liệu có tồn tại |
| Token/lease lifecycle | TTL, renew, revoke | Cơ chế quản lý token và secret động nếu có |

Một token từ staging thường **không thể mặc nhiên sử dụng** cho Vault production. Dù cùng tên KV mount, secret của mỗi môi trường cũng có thể khác nội dung hoặc không tồn tại. Các API Transit encryption và PKI sau này có những path/policy riêng nhưng vẫn sử dụng endpoint và cơ chế kết nối đã thiết lập.

## 7. TLS, container và Vault HA

### 7.1. HTTPS cần chứng chỉ hợp lệ

Ở staging và production, dùng HTTPS và kiểm tra đầy đủ chứng chỉ của Vault hoặc load balancer đứng trước Vault. Cần xem:
- Certificate chain/CA có được JVM hoặc HTTP client tin cậy không.
- Hostname trong `VAULT_ADDR` có khớp Subject Alternative Name (SAN) trên chứng chỉ không.
- Chứng chỉ còn hiệu lực và mạng có cho phép kết nối tới cổng đã chọn không.
- Timeout, proxy hoặc mTLS có được cấu hình đúng trên HTTP client không.

`VaultEndpoint` không tự cấu hình CA trust store, client certificate hoặc private key. Với CA nội bộ, cần cấu hình trust store/JVM hoặc HTTP client tương ứng với thư viện đang dùng. Không tắt hostname verification hoặc chuyển sang HTTP chỉ để vượt lỗi PKIX.

### 7.2. localhost trong Docker/Kubernetes

`127.0.0.1` bên trong container thường chỉ **chính container**. Nếu Vault nằm ở một service khác, `http://127.0.0.1:8200` sẽ không truy cập tới service đó.

Ví dụ địa chỉ theo từng cách chạy:

| Nơi chạy Java | Địa chỉ nên cân nhắc | Điều kiện |
| --- | --- | --- |
| Java và Vault cùng máy local | `http://127.0.0.1:8200` | Vault dev đang chạy trên máy |
| Docker Compose với service `vault` | `http://vault:8200` | Cùng Docker network; HTTP chỉ cho lab phù hợp |
| Kubernetes | `https://vault.vault.svc.cluster.local:8200` | Có Service tên `vault`, namespace `vault` và certificate hợp lệ |
| Production HA | `https://vault.prod.example.internal:8200` | DNS/load balancer được vận hành để truy cập cụm Vault |

Các địa chỉ trong bảng là minh họa, không bảo đảm tồn tại trong hạ tầng người học.

### 7.3. Endpoint ổn định cho Vault HA

Khi chạy Vault HA, thường nên trỏ `VAULT_ADDR` tới một DNS, Service, ingress hoặc load balancer **ổn định** thay vì IP cố định của node active. Vault có cơ chế xử lý request tùy trạng thái node và topology; load balancer, đường dẫn health check và HTTP client phải được thiết kế phù hợp với failover.

Đừng giả định thay `VAULT_ADDR` trên máy chủ sẽ làm `VaultTemplate` đang chạy cập nhật ngay: ví dụ này tạo cấu hình ở thời điểm khởi động. Muốn áp dụng endpoint mới thường cần restart/redeploy hoặc xây cơ chế refresh/discovery riêng.

Nếu dùng Vault Enterprise namespace, namespace cũng là thành phần cấu hình độc lập với URL gốc; không nên tự nhét tên namespace vào đường dẫn base URL.

## 8. Chẩn đoán lỗi từ endpoint đến secret

| Hiện tượng | Nơi cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Không resolve được `VAULT_ADDR` | Nguồn cấu hình Spring | Cấp biến cho đúng process, kiểm tra active profile |
| URI có path `/v1` hoặc thiếu scheme | `app.vault.uri` | Đổi thành base URL `http(s)://host[:port]` |
| HTTP bị từ chối ngoài local | Guard ở `vaultEndpoint()` | Cấp URL HTTPS có CA hợp lệ |
| `UnknownHostException` | DNS | Kiểm tra phân giải tên trong đúng container/pod |
| Connection refused hoặc timeout | Port, routing, firewall, Vault listener | Kiểm tra service và mạng giữa workload với Vault |
| `SSLHandshakeException` / PKIX | TLS/CA/hostname | Cấu hình trust đúng; không tắt xác minh TLS |
| HTTP 401 hoặc token không hợp lệ | Authentication/session | Kiểm tra thông tin đăng nhập, TTL, revoke |
| HTTP 403 | Policy | Kiểm tra quyền của identity thật, đặc biệt `secret/data/...` với KV v2 |
| HTTP 404 hoặc response rỗng | Mount/path/engine version | Kiểm tra mount, KV_1/KV_2, đường dẫn secret |
| Vault sealed hoặc unavailable | Trạng thái Vault | Kiểm tra health/readiness và vận hành cụm |
| Sau deploy mới bắt đầu lỗi | Profile/env/TLS/identity khác môi trường cũ | So sánh effective config của deployment mới |

Chạy `vault status` có thể giúp kiểm tra Vault đang hoạt động, nhưng không chứng minh danh tính ứng dụng được phép đọc secret. Tương tự, CLI dùng root token đọc thành công không thay thế được việc kiểm tra bằng token hoặc role thực của service.

Khi lỗi kết nối nhất thời, có thể thiết kế timeout và retry có backoff ở tầng client. Retry vô hạn không sửa được URI sai hoặc policy 403, và có thể khiến startup treo không cần thiết.

## 9. Kịch bản kiểm thử tích hợp và quan sát

Với lớp cấu hình trên, các tình huống nên xác minh gồm:

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Profile `local` không có `VAULT_ADDR` | Dùng fallback `http://127.0.0.1:8200` |
| Local có `VAULT_ADDR` khác | Dùng giá trị biến môi trường |
| Staging thiếu `VAULT_ADDR` | Báo lỗi cấu hình khi khởi tạo |
| Staging dùng HTTP | Guard từ chối trước khi gọi Vault |
| URI chứa `/v1/secret` hoặc query | Validation từ chối |
| HTTPS với CA không tin cậy | Lỗi TLS đúng nguyên nhân; không bỏ kiểm tra chứng chỉ |
| Endpoint đúng, policy KV v2 sai | Lỗi quyền 403, không trả secret giả |
| Endpoint, token, policy và secret đúng | `VaultTemplate` đọc được dữ liệu KV v2 |
| Deploy vào container với localhost sai | Lỗi mạng; sửa bằng Service/DNS đúng |
| Chuyển node HA/failover | Đánh giá kết nối lại theo thiết kế mạng/client |

Nên dùng một Vault test instance hoặc Testcontainers cho kiểm thử tích hợp; mock `VaultTemplate` chỉ kiểm tra logic service mà không chứng minh DNS, TLS, authentication hay policy vận hành đúng.

Giám sát nên có latency, lỗi mạng/TLS, phân nhóm HTTP 4xx/5xx, trạng thái client và lỗi xác thực. Không gắn token, private key PKI, giá trị KV hoặc thông tin bí mật vào log, trace hay nhãn metric.

## 10. Câu hỏi tự luyện

1. `VaultEndpoint` có chứa đường dẫn `secret/data/demo/app` không? Vì sao?
2. Khi dùng `application.yml` và `application-local.yml` như ví dụ, môi trường nào được dùng HTTP fallback?
3. Vì sao code cố dùng HTTPS nhưng vẫn có thể gặp lỗi TLS handshake?
4. Tại sao `127.0.0.1` chạy được trên laptop nhưng không nhất thiết chạy được trong Kubernetes?
5. Nếu `VAULT_ADDR` đúng mà KV v2 trả 403, nên kiểm tra gì tiếp theo?
6. Tại sao một Vault HA cluster thường nên được truy cập qua endpoint ổn định thay vì IP của một node?
7. Khi token hết TTL, việc đổi `VaultEndpoint` có giải quyết được lỗi xác thực không?

**Kết quả mong đợi:** cùng một bản build Java có thể nhận endpoint từ môi trường triển khai, sử dụng HTTP fallback chỉ trong lab local, kiểm tra URI và HTTPS ở staging/production, rồi đọc thành công secret KV v2 qua `VaultTemplate` với danh tính và policy phù hợp. Đó là nền tảng cấu hình để tiếp tục thực hành xác thực workload, vòng đời token/lease, Transit, PKI, xử lý lỗi và giám sát trong Spring Vault.


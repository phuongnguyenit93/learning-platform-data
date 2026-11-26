# AbstractVaultConfiguration và các phương thức cần cung cấp

Trong chương **Cấu hình Java** của **SPRING_VAULT**, sau khi hiểu các thành phần `VaultEndpoint`, `ClientAuthentication` và `VaultTemplate`, có thể dùng `AbstractVaultConfiguration` để gom việc khởi tạo hạ tầng Vault vào một lớp cấu hình Spring thống nhất. Đây là cách phù hợp khi muốn kiểm soát rõ kết nối, cách đăng nhập và policy của workload, đồng thời để Spring quản lý các đối tượng mà service cần sử dụng.

**Mục tiêu:** tự viết được một lớp kế thừa `AbstractVaultConfiguration`, triển khai đúng **hai phương thức bắt buộc** — `vaultEndpoint()` và `clientAuthentication()` — rồi inject `VaultTemplate` để đọc secret KV v2. Bài cũng phân biệt cấu hình tối thiểu dùng token tại máy phát triển với cấu hình xác thực theo workload, vòng đời token/lease, khả năng mở rộng sang Transit encryption và PKI.

## 1. `AbstractVaultConfiguration` giải quyết vấn đề gì?

`AbstractVaultConfiguration` thuộc package `org.springframework.vault.config` trong thư viện `spring-vault-core`. Đây là lớp cơ sở cho cấu hình Spring Vault bằng Java: ứng dụng **kế thừa lớp này**, cung cấp thông tin kết nối và cách xác thực; lớp cơ sở đăng ký hạ tầng Spring Vault, đặc biệt là `VaultTemplate`, để các service sử dụng qua dependency injection.

Khi cấu hình hoàn toàn thủ công, bạn thường tạo nhiều bean cho endpoint, authentication và template. Với `AbstractVaultConfiguration`, ứng dụng tập trung vào hai quyết định bắt buộc:

1. **Vault ở đâu?** Phương thức `vaultEndpoint()` trả về địa chỉ máy chủ Vault.
2. **Ứng dụng xác thực thế nào?** Phương thức `clientAuthentication()` trả về chiến lược đăng nhập hoặc cung cấp token.

Luồng phụ thuộc về mặt khái niệm:

~~~mermaid
flowchart TD
    A["AppVaultConfiguration<br/>extends AbstractVaultConfiguration"] --> B["vaultEndpoint(): VaultEndpoint"]
    A --> C["clientAuthentication(): ClientAuthentication"]
    A --> D["Hạ tầng được lớp cơ sở cấu hình"]
    B --> D
    C --> D
    D --> E["VaultTemplate"]
    E --> F["SecretReader / service khác"]
    F --> G["Vault KV / Transit / PKI API"]
~~~

**`VaultTemplate` là điểm sử dụng chính của ứng dụng.** Bạn thường inject bean này trong service; không tự gọi `new VaultTemplate(...)` ở từng service. Các thao tác KV, Transit hoặc PKI có API và quyền khác nhau, nhưng đều sử dụng cấu hình kết nối và xác thực Vault.

### So sánh hai cách cấu hình

| Tiêu chí | Tự khai báo bean thủ công | Kế thừa `AbstractVaultConfiguration` |
| --- | --- | --- |
| Chọn endpoint | Tạo bean `VaultEndpoint` | Override `vaultEndpoint()` |
| Chọn cách xác thực | Tạo bean `ClientAuthentication` | Override `clientAuthentication()` |
| Cấp `VaultTemplate` | Tự viết `@Bean VaultTemplate` | Dùng hạ tầng do lớp cơ sở cung cấp |
| Khi phù hợp | Cần tạo bean theo thiết kế riêng | Muốn cấu hình Spring Vault bằng mô hình chuẩn của thư viện |
| Trách nhiệm còn lại | Token, TLS, policy, vận hành | Vẫn cần bảo đảm token, TLS, policy, vận hành |

Hai cách đều có thể hoạt động. Bài này chỉ chọn **một cách** là `AbstractVaultConfiguration` để tránh đăng ký `VaultTemplate` trùng lặp.

## 2. Hai phương thức bắt buộc

Lớp kế thừa phải triển khai các phương thức sau:

| Phương thức | Kiểu trả về | Ý nghĩa | Ví dụ |
| --- | --- | --- | --- |
| `public VaultEndpoint vaultEndpoint()` | `VaultEndpoint` | Địa chỉ Vault (scheme, host, port) | `https://vault.internal:8200` |
| `public ClientAuthentication clientAuthentication()` | `ClientAuthentication` | Chiến lược cung cấp thông tin xác thực | `new TokenAuthentication(token)` |

Khi triển khai, giữ `@Override` trên cả hai phương thức. Nếu nhầm chữ ký hoặc dùng sai phiên bản API, trình biên dịch sẽ báo ngay, thay vì vô tình tạo một phương thức khác.

### `vaultEndpoint()`

Một `VaultEndpoint` trả lời câu hỏi request phải tới host, cổng và giao thức nào. Ví dụ một endpoint dành cho môi trường phát triển:

~~~java
@Override
public VaultEndpoint vaultEndpoint() {
    return VaultEndpoint.create("127.0.0.1", 8200);
}
~~~

Cấu hình này phù hợp với Vault dev server chạy ở máy cá nhân qua HTTP. Với triển khai thật, endpoint nên lấy từ cấu hình môi trường và dùng HTTPS. **Địa chỉ endpoint không phải đường dẫn secret**: mount `secret` và path `demo/app` sẽ được truyền riêng khi đọc KV.

### `clientAuthentication()`

`ClientAuthentication` mô tả cách ứng dụng có được token dùng gọi Vault. Trường hợp đơn giản nhất là một token đã có sẵn:

~~~java
@Override
public ClientAuthentication clientAuthentication() {
    return new TokenAuthentication("dev-only-token");
}
~~~

Đoạn trên chỉ minh họa chữ ký phương thức. **Không được chép token thật vào code hoặc commit lên Git.** Ở ví dụ hoàn chỉnh bên dưới, token được lấy từ biến môi trường.

`TokenAuthentication` sử dụng token được cung cấp, **không đăng nhập lại để tự tạo token mới**. Khi token hết hạn hoặc bị thu hồi, việc tiếp tục đọc secret có thể thất bại. Để xác thực theo workload, cần dùng một `ClientAuthentication` phù hợp như Kubernetes hoặc AppRole và thiết kế quản lý token/session tương ứng.

## 3. Dự án mẫu: kế thừa `AbstractVaultConfiguration`

Giả sử một Spring Boot service cần đọc API key từ mount KV v2 tên `secret`. Chúng ta sẽ cấu hình endpoint và token qua biến môi trường, tránh hardcode giá trị xác thực.

### 3.1. Thêm dependency

Trong dự án Spring Boot, bổ sung dependency cốt lõi Spring Vault trong `pom.xml`:

~~~xml
<dependency>
    <groupId>org.springframework.vault</groupId>
    <artifactId>spring-vault-core</artifactId>
</dependency>
~~~

Ví dụ giả định dự án đã quản lý phiên bản Spring Vault tương thích với Spring Framework thông qua BOM hoặc dependency management. Nếu chưa có, phải khai báo một phiên bản tương thích. `AbstractVaultConfiguration` không yêu cầu thêm Spring Cloud Vault chỉ để tạo `VaultTemplate`.

Ví dụ sử dụng Java 17 trở lên và các thành phần ứng dụng từ Spring Boot.

### 3.2. Cấu hình Java hoàn chỉnh

Tạo `AppVaultConfiguration.java`:

~~~java
package com.example.vault;

import java.net.URI;
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
        // Ví dụ: VAULT_ADDR=https://vault.internal:8200
        URI uri = URI.create(
                environment.getRequiredProperty("VAULT_ADDR"));

        String scheme = uri.getScheme();
        if (uri.getHost() == null
                || (!"http".equalsIgnoreCase(scheme)
                    && !"https".equalsIgnoreCase(scheme))) {
            throw new IllegalArgumentException(
                    "VAULT_ADDR phải là URL HTTP(S) hợp lệ");
        }

        // Ví dụ chỉ nhận base URL, không nhận path/API cụ thể.
        String path = uri.getPath();
        if (path != null && !path.isEmpty() && !"/".equals(path)) {
            throw new IllegalArgumentException(
                    "VAULT_ADDR phải trỏ tới gốc Vault, không kèm path");
        }

        int port = uri.getPort() >= 0
                ? uri.getPort()
                : ("https".equalsIgnoreCase(scheme) ? 443 : 80);

        VaultEndpoint endpoint =
                VaultEndpoint.create(uri.getHost(), port);
        endpoint.setScheme(scheme.toLowerCase(Locale.ROOT));
        return endpoint;
    }

    @Override
    public ClientAuthentication clientAuthentication() {
        String token = environment.getRequiredProperty("VAULT_TOKEN");

        if (token.isBlank()) {
            throw new IllegalArgumentException(
                    "VAULT_TOKEN không được rỗng");
        }

        return new TokenAuthentication(token);
    }
}
~~~

Các điểm cần đọc kỹ:

- `@Configuration` đánh dấu lớp cấu hình Spring; ứng dụng cần component scan tới package này hoặc import lớp một cách tường minh.
- `extends AbstractVaultConfiguration` cho phép sử dụng bean/hạ tầng do Spring Vault cấu hình. **Không cần tự thêm một phương thức `@Bean VaultTemplate` vào lớp này.**
- `Environment.getRequiredProperty(...)` yêu cầu có `VAULT_ADDR` và `VAULT_TOKEN`. Thiếu một trong hai, ứng dụng báo lỗi khi khởi tạo cấu hình thay vì âm thầm dùng token mặc định.
- `vaultEndpoint()` chỉ cấu hình địa chỉ. Việc map `secret/demo/app`, KV v1 hay KV v2 nằm ở thao tác đọc.
- `clientAuthentication()` trả về một đối tượng xác thực. Ví dụ này là token tĩnh phục vụ học tập, chưa có cơ chế đăng nhập workload hay làm mới token.
- `@Configuration` ở đây giữ chế độ proxy bean mặc định. Khi làm việc với các phương thức cấu hình kế thừa, chỉ tối ưu `proxyBeanMethods` nếu đã hiểu rõ cách phiên bản Spring Vault đang dùng tham chiếu các bean.

Với một secret đọc đơn giản, **hai phương thức override là phần ứng dụng bắt buộc cung cấp**. Các tùy chỉnh liên quan HTTP client, TLS, timeout, hoặc session có thể cần thêm cấu hình theo phiên bản Spring Vault và môi trường triển khai; chúng không làm thay đổi hai trách nhiệm cơ bản trên.

## 4. Xác minh bằng một secret KV v2

### 4.1. Tạo secret để thực hành

Khởi chạy Vault dev server tại máy phát triển:

~~~bash
vault server -dev -dev-root-token-id=dev-only-token
~~~

Trong terminal khác (Bash), đặt biến môi trường và lưu dữ liệu:

~~~bash
export VAULT_ADDR=http://127.0.0.1:8200
export VAULT_TOKEN=dev-only-token

vault kv put secret/demo/app apiKey=local-demo-key
vault kv get secret/demo/app
~~~

Tương đương phần biến môi trường ở PowerShell:

~~~powershell
$env:VAULT_ADDR = "http://127.0.0.1:8200"
$env:VAULT_TOKEN = "dev-only-token"
~~~

Vault dev server thường có KV v2 được gắn vào `secret/`. Nếu cấu hình Vault khác đi, hãy kiểm tra mount và phiên bản engine; tham số `KeyValueBackend.KV_2` bên dưới phải khớp với thực tế.

**Không sử dụng root token, HTTP plaintext hoặc secret demo trong production.** Dev server chỉ dành cho bài thực hành cục bộ.

### 4.2. Inject `VaultTemplate` vào service

Tạo `DemoSecretReader.java`:

~~~java
package com.example.vault;

import java.util.Map;

import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.core.VaultTemplate;
import org.springframework.vault.support.VaultResponse;

@Service
public class DemoSecretReader {

    private final VaultTemplate vaultTemplate;

    public DemoSecretReader(VaultTemplate vaultTemplate) {
        this.vaultTemplate = vaultTemplate;
    }

    public String readApiKey() {
        VaultResponse response = vaultTemplate
                .opsForKeyValue("secret", KeyValueBackend.KV_2)
                .get("demo/app");

        Map<String, Object> data =
                response == null ? null : response.getData();

        Object apiKey = data == null ? null : data.get("apiKey");
        if (!(apiKey instanceof String text) || text.isBlank()) {
            throw new IllegalStateException(
                    "Không tìm thấy apiKey hợp lệ tại secret/demo/app");
        }

        return text;
    }
}
~~~

Spring inject `VaultTemplate` được đăng ký từ cấu hình `AbstractVaultConfiguration`. Service chỉ khai báo dependency và tập trung vào nghiệp vụ đọc secret.

Có **ba loại đường dẫn khác nhau** dễ bị nhầm:

| Thành phần | Giá trị | Dùng ở đâu? |
| --- | --- | --- |
| Endpoint máy chủ | `http://127.0.0.1:8200` | `vaultEndpoint()` |
| Mount KV | `secret` | `opsForKeyValue("secret", KV_2)` |
| Secret tương đối | `demo/app` | `get("demo/app")` |

Với KV v2, thao tác đọc phía HTTP tương ứng là `GET /v1/secret/data/demo/app`. `VaultKeyValueOperations` tự xử lý phần `data` của đường dẫn API, nên **không viết** `get("data/demo/app")`.

### 4.3. Xác nhận từ ứng dụng

Một cách kiểm tra mà không làm lộ secret là gọi hàm khi ứng dụng khởi động và chỉ in trạng thái:

~~~java
package com.example.vault;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class VaultExampleApplication {

    public static void main(String[] args) {
        SpringApplication.run(VaultExampleApplication.class, args);
    }

    @Bean
    CommandLineRunner verifyVault(DemoSecretReader reader) {
        return args -> {
            reader.readApiKey();
            System.out.println("Đọc secret từ Vault thành công");
        };
    }
}
~~~

Giả sử lớp ứng dụng và các lớp cấu hình/service nằm trong package được component scan, terminal có `VAULT_ADDR` và `VAULT_TOKEN` đúng, kết quả mong đợi:

~~~text
Đọc secret từ Vault thành công
~~~

Trong hệ thống thật, không in kết quả `readApiKey()`, token, toàn bộ `VaultResponse` hoặc nội dung secret vào log hay HTTP response. Nếu đọc thất bại, `CommandLineRunner` trên sẽ làm quá trình khởi động báo lỗi; đó là lựa chọn có chủ đích cho ví dụ kiểm tra này, không phải chiến lược khởi động bắt buộc của mọi ứng dụng.

## 5. Bean nào do ai tạo? Những hiểu nhầm thường gặp

**Hiểu nhầm 1: Kế thừa `AbstractVaultConfiguration` là đủ, không cần override gì.**

Không đúng. Spring Vault vẫn cần biết đích kết nối và cơ chế xác thực. Hai override `vaultEndpoint()` và `clientAuthentication()` là điểm mở rộng bắt buộc trong cấu hình này.

**Hiểu nhầm 2: Cần viết thêm `@Bean VaultTemplate` ở lớp kế thừa.**

Không cần cho ví dụ tối thiểu. `AbstractVaultConfiguration` cung cấp cơ chế đăng ký hạ tầng và bean `VaultTemplate`. Định nghĩa thêm một bean cùng kiểu/tên có thể gây trùng bean, thay đổi cách autowire hoặc tạo hành vi khó đoán.

**Hiểu nhầm 3: `AbstractVaultConfiguration` tự đưa mọi secret vào `application.properties` hoặc Spring `Environment`.**

Không phải chức năng mặc định của ví dụ này. `VaultTemplate` cung cấp API truy cập Vault chủ động từ code. Việc đưa secret vào nguồn thuộc tính khi khởi động là một cơ chế cấu hình khác, ví dụ qua integration tương ứng của Spring Cloud Vault.

**Hiểu nhầm 4: `vaultEndpoint()` nên trả về đường dẫn `secret/data/demo/app`.**

Không đúng. Endpoint là URL máy chủ Vault. Mount và đường dẫn secret được chọn khi gọi operation; nhầm ba lớp đường dẫn sẽ dễ tạo lỗi 404 hoặc sai đường dẫn policy.

**Hiểu nhầm 5: Chỉ cần token đúng là đọc được tất cả secret.**

Vault còn áp dụng policy theo danh tính, mount và đường dẫn API. Token hợp lệ nhưng thiếu quyền `read` vẫn có thể bị từ chối với 403.

## 6. Phân quyền, token và session: cấu hình tối thiểu chưa phải production

Nếu service chỉ đọc secret KV v2 `secret/demo/app`, một policy HCL tối thiểu có thể là:

~~~hcl
path "secret/data/demo/app" {
  capabilities = ["read"]
}
~~~

Policy phải được gắn với danh tính/token **thực tế của ứng dụng**. Trong dev server, root token thường đọc được mọi thứ, nên kiểm tra thành công bằng root token **không chứng minh** policy production đã đúng.

### Phân biệt authentication, token và session

| Khái niệm | Chức năng | Điều cần lưu ý |
| --- | --- | --- |
| `ClientAuthentication` | Cách lấy hoặc cung cấp thông tin đăng nhập Vault | Có thể dùng token sẵn hoặc cơ chế login dựa trên workload |
| Token Vault | Credential được Vault chấp nhận cho request | Có policy, TTL, khả năng revoke và đặc điểm gia hạn tùy loại |
| Session/token management | Giữ và sử dụng token phù hợp khi gọi API | Chiến lược phụ thuộc implementation và cấu hình thực tế |
| Lease của secret động | Vòng đời quyền truy cập do secrets engine cấp | Khác với việc đọc giá trị KV tĩnh; có thể cần renew/revoke |

`TokenAuthentication` trong ví dụ chỉ sử dụng một token có sẵn. Nó không biến token tĩnh thành token có khả năng tự gia hạn. `AbstractVaultConfiguration` cũng không tự động làm cho mọi cơ chế xác thực có cùng hành vi refresh: phải chọn phương thức xác thực và cơ chế quản lý token theo workload cụ thể.

Khi triển khai trên Kubernetes, ví dụ, ứng dụng có thể dùng Kubernetes auth dựa trên ServiceAccount token và Vault auth role được cấu hình trước. Với ứng dụng chạy theo môi trường khác, AppRole hoặc cơ chế identity native của nền tảng có thể phù hợp hơn. Khi thay `clientAuthentication()`, cần xét cả dữ liệu đăng nhập, Vault auth mount path, HTTP client phục vụ login và policy gán vào role; **không chỉ đổi một tên class**.

### Có cần override thêm phương thức của lớp cơ sở?

Đối với mục tiêu **kết nối và đọc một secret**, hai phương thức trong bảng ở mục 2 là tối thiểu. Khi cần tùy chỉnh TLS, proxy, timeout, Vault namespace, quản lý session hoặc cơ chế auth phức tạp, có thể phải mở rộng cấu hình theo API của **đúng phiên bản** Spring Vault đang sử dụng. Không nên đoán rằng mọi phiên bản đều có cùng chữ ký hoặc cùng giá trị mặc định cho các extension point bổ sung.

Đặc biệt ở production, cần sử dụng HTTPS, xác minh chứng chỉ của Vault, không tắt hostname verification và không cho phép token nhạy cảm xuất hiện trong log.

## 7. Khi dùng Spring Boot hoặc Spring Cloud Vault

Trong Spring Boot, `@Configuration` phải được phát hiện qua component scan hoặc `@Import`. Một khi lớp cấu hình được nạp, các bean hạ tầng sẽ có thể được service inject.

Nếu ứng dụng đã thêm starter **Spring Cloud Vault Config** hoặc một cấu hình khác tự tạo `VaultTemplate`, cần kiểm tra các bean hiện diện trước khi đưa thêm `AbstractVaultConfiguration`. Hai cơ chế cùng khởi tạo Vault infrastructure có thể dẫn đến bean trùng tên, nhiều bean cùng kiểu hoặc việc inject nhầm bean. Chọn một nguồn cấu hình hạ tầng rõ ràng; nếu cố ý dùng nhiều kết nối Vault, hãy đặt tên bean và qualifier tường minh.

Không nên xem `AbstractVaultConfiguration` như thay thế hoàn toàn cho Spring Cloud Vault: lớp cơ sở là nền tảng cấu hình và truy cập Vault qua Java API; Spring Cloud Vault còn giải quyết các tình huống tích hợp cấu hình ứng dụng và property sources ở tầng khác.

## 8. Chẩn đoán lỗi theo từng lớp

| Triệu chứng | Lớp đang có vấn đề | Cách kiểm tra |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` cho `VaultTemplate` | Spring configuration | Kiểm tra `@Configuration` có được scan/import, dependency `spring-vault-core` và class kế thừa |
| Lỗi thiếu `VAULT_ADDR` / `VAULT_TOKEN` | Input cấu hình | Đặt biến môi trường trong **tiến trình chạy Java**, không chỉ ở terminal khác |
| `UnknownHostException`, connection refused, timeout | Endpoint/mạng | Kiểm tra host, port, route, DNS và Vault đang chạy |
| TLS handshake/PKIX error | TLS/trust | Dùng HTTPS đúng, CA/trust store phù hợp; không tắt kiểm tra TLS |
| 401/permission error do token | Authentication/session | Kiểm tra token có tồn tại, đã hết TTL hay bị thu hồi và phương thức đăng nhập |
| 403 permission denied | Policy | Xác nhận policy gắn với token của service có `read` tại `secret/data/demo/app` |
| 404/null khi gọi KV | Mount/path/engine | Xác nhận `secret` là KV v2, dữ liệu ở `demo/app`, không tự chèn `data/` vào `get(...)` |
| Lỗi do nhiều bean `VaultTemplate` | Cấu hình trùng | Tìm các nguồn cấu hình Spring Vault/Cloud Vault và xác định một bean được sử dụng |
| Ban đầu chạy được, sau đó thất bại | Vòng đời token | Kiểm tra TTL/revoke; triển khai auth/session management phù hợp |

Cũng cần phân biệt **401/403** do danh tính hoặc quyền với **404** do mount/secret và lỗi giao tiếp mạng. Đừng ghi token hoặc giá trị secret vào log để thử chẩn đoán. Dùng mã lỗi, loại request, đường dẫn logic đã kiểm soát và thông tin vận hành không nhạy cảm.

## 9. Gợi ý kiểm thử và giám sát

Các tình huống kiểm thử tích hợp hữu ích sau khi cấu hình xong:

1. **Đường đi thành công:** Một Vault test instance có mount KV v2 và secret `demo/app`; service inject được `VaultTemplate` và đọc được `apiKey`.
2. **Cấu hình thiếu:** Không có `VAULT_ADDR` hoặc `VAULT_TOKEN`; ứng dụng báo lỗi rõ ràng ở quá trình tạo bean.
3. **Sai quyền:** Token chỉ có policy ở path khác; thao tác đọc bị 403, ứng dụng không trả về secret mặc định giả.
4. **Secret thiếu:** `demo/app` không tồn tại; service nhận kết quả thiếu hoặc lỗi được chuyển thành thông báo nghiệp vụ an toàn.
5. **Mất Vault/token hết hạn:** Mô phỏng kết nối lỗi hoặc credential không còn hiệu lực để kiểm tra chính sách retry, timeout và khả năng phục hồi đã thiết kế.

Có thể dùng Vault thật trong môi trường tích hợp hoặc Testcontainers cung cấp Vault tạm thời cho bài kiểm thử; mock `VaultTemplate` chỉ kiểm tra logic riêng của service, **không chứng minh** endpoint, auth và policy tích hợp đúng. Không bắt buộc triển khai tất cả các kiểm thử này trong bài lý thuyết bước đầu, nhưng phải biết lớp nào đang được kiểm tra.

Giám sát nên tập trung vào tình trạng kết nối, độ trễ gọi Vault, số lần lỗi theo nhóm 4xx/5xx, lỗi authentication và các sự kiện vòng đời token cần thiết. Không xuất token, khóa Transit, private key PKI hoặc giá trị KV vào metric label, tracing hay log. Khi mở rộng sang Transit encryption và PKI, vẫn dùng hạ tầng kết nối/xác thực này nhưng request và policy của từng secrets engine phải được kiểm tra riêng.

## 10. Tự đánh giá sau bài học

Hãy thử trả lời các câu hỏi sau:

1. Hai phương thức `@Override` nào phải cung cấp khi kế thừa `AbstractVaultConfiguration`? Mỗi phương thức trả về gì?
2. Vì sao lớp `DemoSecretReader` chỉ inject `VaultTemplate` mà không tự tạo `VaultEndpoint` hay `TokenAuthentication`?
3. Nếu secret nằm ở KV v2 mount `secret`, path `demo/app`, đường dẫn policy `read` chính xác là gì? Giá trị nào truyền vào `get(...)`?
4. Nếu ứng dụng dùng token tĩnh và token hết TTL, `AbstractVaultConfiguration` có tự làm mới token đó không?
5. Ứng dụng đã có Spring Cloud Vault auto configuration. Cần kiểm tra điều gì trước khi thêm lớp kế thừa `AbstractVaultConfiguration`?

**Kết quả mong đợi:** có một lớp `@Configuration extends AbstractVaultConfiguration` triển khai `vaultEndpoint()` và `clientAuthentication()`; ứng dụng tạo được `VaultTemplate` để service đọc secret KV v2 và kiểm tra thành công mà không tiết lộ dữ liệu nhạy cảm. Từ nền tảng này có thể tiếp tục thiết kế authentication theo workload, policy ít quyền nhất, quản lý token/lease, xử lý lỗi, giám sát và kiểm thử tích hợp cho Spring Vault.


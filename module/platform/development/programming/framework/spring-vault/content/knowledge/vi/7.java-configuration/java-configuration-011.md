# Sử dụng thư viện trong hoặc ngoài ApplicationContext

Trong chương **Cấu hình Java** của module **SPRING_VAULT**, một ứng dụng Java có thể kết nối HashiCorp Vault qua `VaultTemplate` để đọc KV secrets, gọi Transit encryption, thao tác PKI hoặc các API token. Câu hỏi quan trọng khi thiết kế là: **có nhất thiết phải khởi động Spring `ApplicationContext` để sử dụng Spring Vault không?**

**Không.** `spring-vault-core` cung cấp các lớp Java có thể khởi tạo và sử dụng trực tiếp trong chương trình không có Spring container. Tuy nhiên, khi các đối tượng này nằm trong một `ApplicationContext`, Spring quản lý dependency injection và các callback khởi tạo/hủy, thuận tiện cho những ứng dụng chạy lâu có token, session và secret lease cần được theo dõi.

Bài học này so sánh hai mô hình, minh họa **cùng một nghiệp vụ đọc KV v2** trong ứng dụng Spring Boot và trong chương trình Java standalone, rồi phân tích cách quản lý tài nguyên, xác thực theo workload, TLS, kiểm thử và xử lý lỗi. Những nguyên tắc tương tự áp dụng cho Transit encryption, PKI và các operations khác.

**Kết quả cần đạt:**

- Giải thích được `ApplicationContext` mang lại điều gì và điều gì không bắt buộc phải có nó.
- Khởi tạo `VaultEndpoint`, `ClientAuthentication` và `VaultTemplate` ở cả hai môi trường.
- Tách logic sử dụng `VaultOperations` khỏi cách tạo và quản lý client.
- Hiểu trách nhiệm xử lý `InitializingBean`, `DisposableBean`, `SessionManager` và scheduler khi không có container.
- Biết khi nào một script/batch có thể dùng client đơn giản và khi nào nên dùng Spring context hoặc một lifecycle manager riêng.

## 1. Phân biệt thư viện Spring Vault và Spring ApplicationContext

`VaultTemplate` là lớp chính trong `org.springframework.vault.core` và triển khai interface `VaultOperations`. Nó cung cấp những operation như `read`, `write`, `opsForKeyValue`, `opsForTransit` và `opsForPki`.

`ApplicationContext`, ngược lại, là **container IoC của Spring**. Nó tạo bean, resolve dependency, thực thi các callback vòng đời và đóng các bean khi context shutdown. `VaultTemplate` có thể được quản lý bởi container, nhưng bản thân một lời gọi Vault API **không yêu cầu** `ApplicationContext` tồn tại.

~~~mermaid
flowchart TD
    A["Nghiệp vụ Java<br/>VaultOperations"] --> B{"Có Spring ApplicationContext?"}
    B -- "Có" --> C["Spring tạo bean<br/>VaultEndpoint/Auth/Session/Template"]
    B -- "Không" --> D["Code Java tự tạo và giữ<br/>VaultEndpoint/Auth/Template"]
    C --> E["VaultTemplate"]
    D --> E
    E --> F["Vault HTTP API"]
    F --> G["KV / Transit / PKI"]
~~~

| Khía cạnh | Trong `ApplicationContext` | Ngoài `ApplicationContext` |
| --- | --- | --- |
| Tạo đối tượng | `@Configuration`, `@Bean`, `AbstractVaultConfiguration` hoặc auto-configuration | `new VaultTemplate(...)` bằng code |
| Cấp cấu hình | Spring `Environment`, `@Value`, `@ConfigurationProperties` | Biến môi trường, CLI args, file config do chương trình đọc |
| Dependency injection | Spring inject `VaultOperations` vào service | Constructor Java thông thường |
| Vòng đời bean | Spring gọi các callback phù hợp khi tạo/hủy bean | **Ứng dụng tự chịu trách nhiệm** với các callback và tài nguyên liên quan |
| Session token | Có thể dùng `LifecycleAwareSessionManager` của cấu hình Spring | Phải chọn và quản lý manager nếu cần lifecycle nâng cao |
| Scheduler/lease | Dễ đăng ký và đóng cùng context | Phải tự tạo, điều phối, dọn dẹp |
| Kiểm thử | Test Spring context và integration test | Unit test POJO và integration test |
| Cài đặt | Phù hợp service chạy lâu, Spring Boot | Phù hợp CLI, batch, migration tool, ứng dụng Java không dùng Spring |

**Một điểm dễ nhầm:** chỉ thêm dependency `spring-vault-core` **không tự tạo** `ApplicationContext`; ngược lại, có Spring Boot trong classpath cũng **không tự thiết lập endpoint và token Vault** nếu bạn chưa dùng cấu hình được hỗ trợ.

## 2. Ba khái niệm độc lập: endpoint, authentication và operations

Dù dùng container hay không, ứng dụng cần hiểu ba trách nhiệm:

1. `VaultEndpoint` xác định **đích kết nối**: scheme, host, port của Vault.
2. `ClientAuthentication` cung cấp hoặc lấy **Vault token** đại diện cho workload.
3. `VaultTemplate` sử dụng endpoint và nguồn token để thực hiện **Vault operations**.

Ví dụ:

~~~java
VaultEndpoint endpoint =
        VaultEndpoint.from(URI.create("http://127.0.0.1:8200"));

ClientAuthentication authentication =
        new TokenAuthentication("dev-only-token");

VaultTemplate template =
        new VaultTemplate(endpoint, authentication);
~~~

Trong ví dụ Java này cần import `java.net.URI` và các class Spring Vault phù hợp. Nó chỉ minh họa đối tượng cốt lõi; **đừng hardcode token thật** trong source code.

Một số khái niệm khác cũng rất quan trọng:

| Khái niệm | Ý nghĩa |
| --- | --- |
| `SessionManager` | Quyết định cách lấy, dùng lại, renew hoặc revoke token theo implementation |
| `TaskScheduler` | Chạy tác vụ theo lịch như renew token hoặc lease khi được đăng ký |
| `SecretLeaseContainer` | Theo dõi những secret động có lease mà ứng dụng yêu cầu quản lý |
| Vault policy | Xác định quyền `read`, `create`, `update`, `delete`... của token trên các API path |
| TLS/trust store | Bảo vệ kết nối từ client tới Vault |
| KV mount/path | Chọn dữ liệu đích; độc lập với base URL |

**Không nên nhầm Spring bean lifecycle với Vault token TTL.** Callback `destroy()` của một object chỉ xử lý phần tài nguyên mà object đó sở hữu. Nó không bảo đảm mọi token hoặc secret động đã được thu hồi, nhất là khi token/lease được cấp và quản lý bên ngoài ứng dụng.

## 3. Khi nào nên dùng và không dùng ApplicationContext?

### Nên dùng ApplicationContext khi

- Ứng dụng Spring Boot phục vụ HTTP/gRPC hoặc xử lý message liên tục.
- Nhiều service cùng dùng một `VaultOperations` được cấu hình thống nhất.
- Cần `Environment`, profiles, bean scopes, test configuration và dependency injection.
- Token có TTL và muốn quản lý renewal/lifecycle qua hạ tầng Spring Vault.
- Có secret động hoặc lease cần đăng ký theo dõi và dọn dẹp theo vòng đời context.
- Cần nhiều Vault clients, chọn rõ từng bean bằng `@Qualifier`.

### Có thể dùng ngoài ApplicationContext khi

- Viết command-line tool đọc secret cho một lần chạy.
- Chạy migration, batch job hoặc integration utility không dùng Spring Boot.
- Có ứng dụng Java hiện hữu nhưng không muốn đưa một IoC container vào chỉ để gọi vài Vault API.
- Cần kiểm soát chính xác lúc tạo, lúc thực thi và lúc đóng client.

**Không phải cứ dùng Spring Vault bên ngoài container là thiếu an toàn.** Tính an toàn đến từ authentication theo workload, policy, HTTPS/TLS, thời gian sống credential và cách dọn dẹp tài nguyên. Tuy nhiên, trách nhiệm cấu hình đúng tất cả yếu tố này **thuộc về bạn nhiều hơn**.

Bảng lựa chọn nhanh:

| Trường hợp | Gợi ý | Lý do |
| --- | --- | --- |
| Công cụ CLI chạy trong vài giây | Standalone `VaultTemplate` | Ít hạ tầng |
| Spring Boot service chạy hàng ngày | `ApplicationContext` + bean quản lý | DI và lifecycle rõ ràng |
| Java service không dùng Spring | Standalone + lifecycle manager thiết kế riêng | Không cần thêm container chỉ để đọc secret |
| Nhiều secret động phải renew liên tục | Spring context hoặc bộ quản lý vòng đời tương đương | Scheduler và cleanup phức tạp |
| Dùng Vault Agent/proxy thay ứng dụng xác thực | Xem xét constructor không có auth, theo kiến trúc agent | Không nên tự gửi token nếu agent đảm nhận |
| Nhiều Vault server/danh tính | Có thể ở cả hai mô hình | Phải tách endpoint, identity, session cho từng client |

## 4. Chuẩn bị môi trường thực hành dùng chung

Bài này dùng Spring Vault và Java 17 trở lên, giả sử HashiCorp Vault CLI đã cài trên máy phát triển. Các ví dụ Java dùng dependency:

~~~xml
<dependency>
    <groupId>org.springframework.vault</groupId>
    <artifactId>spring-vault-core</artifactId>
</dependency>
~~~

Trong Maven project có dependency management/BOM tương thích, đoạn trên có thể để trống version. Nếu dự án không quản lý phiên bản, phải khai báo một version Spring Vault phù hợp Spring Framework và HTTP libraries. Với Spring Vault 4.1 có `VaultClient`; ở các nhánh 3.2/4.0 vẫn có constructor `VaultTemplate(VaultEndpoint, ClientAuthentication)` dùng trong bài.

### 4.1. Khởi động Vault dev

Terminal thứ nhất:

~~~bash
vault server -dev -dev-root-token-id=dev-only-token
~~~

Terminal thứ hai (Bash):

~~~bash
export VAULT_ADDR=http://127.0.0.1:8200
export VAULT_TOKEN=dev-only-token

vault kv put secret/demo/app username=demo-user
vault kv get secret/demo/app
~~~

Hoặc PowerShell:

~~~powershell
$env:VAULT_ADDR = "http://127.0.0.1:8200"
$env:VAULT_TOKEN = "dev-only-token"

vault kv put secret/demo/app username=demo-user
vault kv get secret/demo/app
~~~

Giả định dev server có KV v2 ở mount `secret`, như cấu hình dev phổ biến. Có thể kiểm tra bằng `vault secrets list -detailed`. **Dev root token và kết nối HTTP localhost chỉ dành cho lab**, không dùng cho staging hoặc production.

### 4.2. Khái niệm mount và secret path

| Thành phần | Giá trị ví dụ | Vai trò |
| --- | --- | --- |
| Vault base URL | `http://127.0.0.1:8200` | Tạo `VaultEndpoint` |
| KV mount | `secret` | Engine KV |
| Secret path | `demo/app` | Đường dẫn tương đối trong mount |
| API KV v2 | `/v1/secret/data/demo/app` | HTTP path do client xây từ KV v2 operation |
| Secret field | `username` | Trường đọc từ response KV |

Không đưa `/v1/secret/data/demo/app` vào `VAULT_ADDR`; đó không phải base URL Vault.

## 5. Tách nghiệp vụ Java khỏi cách quản lý client

Đây là bước làm cho **cùng một logic** chạy trong và ngoài `ApplicationContext`. Tạo class Java thuần `DemoSecretReader.java`:

~~~java
package com.example.vault;

import java.util.Map;
import java.util.Objects;

import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponse;

public final class DemoSecretReader {

    private final VaultOperations vault;

    public DemoSecretReader(VaultOperations vault) {
        this.vault = Objects.requireNonNull(vault, "vault");
    }

    public boolean sampleUsernameExists() {
        VaultResponse response = vault
                .opsForKeyValue("secret", KeyValueBackend.KV_2)
                .get("demo/app");

        Map<String, Object> data =
                response == null ? null : response.getData();

        return data != null
                && data.get("username") instanceof String username
                && !username.isBlank();
    }
}
~~~

**Class này không có `@Service` hay `@Component`.** Nó chỉ nhận một `VaultOperations` qua constructor Java. Do đó:

- Khi **có context**, ta tạo `@Bean DemoSecretReader` và để Spring inject `VaultOperations`.
- Khi **không có context**, ta gọi `new DemoSecretReader(template)`.
- Logic đọc `KV_2` giữ nguyên; không nhân đôi mã nghiệp vụ để phục vụ hai môi trường.

`VaultTemplate` triển khai `VaultOperations` và có thể được **dùng lại giữa nhiều luồng sau khi cấu hình đúng**. Tốt nhất không khởi tạo một template mới cho mỗi request hoặc mỗi lần đọc secret.

## 6. Mô hình A: dùng Spring Vault trong ApplicationContext

Trong ứng dụng Spring Boot, Spring container có thể quản lý các bean Vault như những thành phần hạ tầng khác.

### 6.1. Tạo bean bằng @Configuration

Tạo `VaultAppConfig.java`:

~~~java
package com.example.vault;

import java.net.URI;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.vault.authentication.ClientAuthentication;
import org.springframework.vault.authentication.TokenAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultTemplate;

@Configuration(proxyBeanMethods = false)
public class VaultAppConfig {

    @Bean
    public VaultTemplate vaultTemplate(Environment environment) {
        String address =
                environment.getRequiredProperty("app.vault.uri");
        String token =
                environment.getRequiredProperty("app.vault.token");

        if (token.isBlank()) {
            throw new IllegalArgumentException(
                    "app.vault.token không được rỗng");
        }

        VaultEndpoint endpoint =
                VaultEndpoint.from(URI.create(address));
        ClientAuthentication auth =
                new TokenAuthentication(token);

        return new VaultTemplate(endpoint, auth);
    }

    @Bean
    public DemoSecretReader demoSecretReader(
            VaultOperations vaultOperations) {
        return new DemoSecretReader(vaultOperations);
    }
}
~~~

Ứng dụng Spring Boot có thể khai báo properties:

~~~yaml
# src/main/resources/application.yml
app:
  vault:
    uri: ${VAULT_ADDR}
    token: ${VAULT_TOKEN}
~~~

Đối với local, có thể thêm `application-local.yml` với fallback URL (nhưng không fallback token):

~~~yaml
app:
  vault:
    uri: ${VAULT_ADDR:http://127.0.0.1:8200}
~~~

Khi khởi động bằng `SPRING_PROFILES_ACTIVE=local` và `VAULT_TOKEN=dev-only-token`, Spring Boot nạp `Environment`, tạo `VaultTemplate` và inject nó dưới kiểu `VaultOperations` cho `DemoSecretReader`.

**Lưu ý:** `app.vault.*` là tên property do ví dụ định nghĩa. Nếu dùng `EnvironmentVaultConfiguration` của Spring Vault, tên cấu hình lại là `vault.uri`/`vault.token`/`vault.authentication`. Nếu dùng Spring Cloud Vault, starter thường dùng `spring.cloud.vault.*`. Không trộn các nhóm property rồi chờ framework tự đoán cách dựng client.

### 6.2. Lớp khởi động và phép kiểm tra

Tạo `VaultSpringApplication.java`:

~~~java
package com.example.vault;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class VaultSpringApplication {

    public static void main(String[] args) {
        SpringApplication.run(VaultSpringApplication.class, args);
    }

    @Bean
    CommandLineRunner checkVault(DemoSecretReader reader) {
        return args -> {
            if (!reader.sampleUsernameExists()) {
                throw new IllegalStateException(
                        "KV v2 chưa có trường username hợp lệ");
            }
            System.out.println("Spring context: đọc KV v2 thành công");
        };
    }
}
~~~

Đây là ứng dụng Spring Boot hoàn chỉnh ở mức lớp chính, nhưng phụ thuộc việc đặt các lớp trong package được component scan và có dependency Spring Boot cần thiết của dự án.

**Vì sao `CommandLineRunner` phù hợp?** Nó chạy sau khi context đã tạo các bean singleton thông thường. Nhờ đó, phép đọc kiểm tra đúng `VaultTemplate` đã được inject. Trong service production, việc chặn startup vì một secret tạm thời không truy cập được là **quyết định vận hành**, không phải mặc định bắt buộc.

**Điều Spring làm thay bạn:** tạo bean, giải quyết dependency, gọi callback `InitializingBean` sau khi thuộc tính được thiết lập, và callback hủy tương ứng khi context đóng đúng quy trình. Nhưng Spring **không tự cấp policy, token production hay CA trust store** chỉ vì object là bean.

### 6.3. Tận dụng AbstractVaultConfiguration

Thay vì tự tạo bean `VaultTemplate` như mục 6.1, có thể chọn cách kế thừa `AbstractVaultConfiguration`:

~~~java
package com.example.vault;

import java.net.URI;

import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.vault.authentication.ClientAuthentication;
import org.springframework.vault.authentication.TokenAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.config.AbstractVaultConfiguration;

@Configuration
public class VaultInfrastructureConfig
        extends AbstractVaultConfiguration {

    private final Environment environment;

    public VaultInfrastructureConfig(Environment environment) {
        this.environment = environment;
    }

    @Override
    public VaultEndpoint vaultEndpoint() {
        String address =
                environment.getRequiredProperty("app.vault.uri");
        return VaultEndpoint.from(URI.create(address));
    }

    @Override
    public ClientAuthentication clientAuthentication() {
        String token =
                environment.getRequiredProperty("app.vault.token");
        if (token.isBlank()) {
            throw new IllegalArgumentException("Vault token rỗng");
        }
        return new TokenAuthentication(token);
    }
}
~~~

**Đây là cấu hình thay thế** cho `VaultAppConfig`, không phải lớp bổ sung tạo template thứ hai. Nếu áp dụng, để `AbstractVaultConfiguration` cung cấp `VaultTemplate`, `SessionManager` và scheduler; `DemoSecretReader` có thể được đăng ký bằng một bean trong lớp cấu hình khác hoặc bằng `@Service` nếu bạn quyết định sửa class POJO.

Đặc biệt, `AbstractVaultConfiguration` mặc định tạo `LifecycleAwareSessionManager` và hạ tầng scheduler phục vụ token/secret lease theo điều kiện. Cách này phù hợp với service chạy lâu cần vòng đời credential hơn constructor đơn giản có `TokenAuthentication`.

## 7. Mô hình B: dùng Spring Vault ngoài ApplicationContext

Chương trình standalone có thể tạo các đối tượng trực tiếp, **không gọi `SpringApplication.run(...)`**, không cần `@Bean` hoặc `@Configuration`.

Tạo `VaultStandaloneMain.java`:

~~~java
package com.example.vault;

import java.net.URI;

import org.springframework.vault.authentication.ClientAuthentication;
import org.springframework.vault.authentication.TokenAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultTemplate;

public final class VaultStandaloneMain {

    public static void main(String[] args) throws Exception {
        String address = requireEnv("VAULT_ADDR");
        String token = requireEnv("VAULT_TOKEN");

        URI uri = URI.create(address);
        validateBaseUrl(uri);

        VaultEndpoint endpoint = VaultEndpoint.from(uri);
        ClientAuthentication authentication =
                new TokenAuthentication(token);

        VaultTemplate template =
                new VaultTemplate(endpoint, authentication);

        // Không có container: gọi callback khởi tạo một cách tường minh.
        template.afterPropertiesSet();

        try {
            DemoSecretReader reader =
                    new DemoSecretReader(template);

            if (!reader.sampleUsernameExists()) {
                throw new IllegalStateException(
                        "KV v2 chưa có trường username hợp lệ");
            }
            System.out.println(
                    "Standalone Java: đọc KV v2 thành công");
        } finally {
            // Không có container gọi callback destroy giúp bạn.
            template.destroy();
        }
    }

    private static String requireEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    "Thiếu biến môi trường bắt buộc: " + name);
        }
        return value.trim();
    }

    private static void validateBaseUrl(URI uri) {
        String scheme = uri.getScheme();
        if (uri.getHost() == null
                || (!"http".equalsIgnoreCase(scheme)
                    && !"https".equalsIgnoreCase(scheme))
                || uri.getRawUserInfo() != null
                || uri.getRawQuery() != null
                || uri.getRawFragment() != null
                || (uri.getRawPath() != null
                    && !uri.getRawPath().isEmpty()
                    && !"/".equals(uri.getRawPath()))) {
            throw new IllegalArgumentException(
                    "VAULT_ADDR phải là base URL http(s)://host[:port]");
        }
    }
}
~~~

Đoạn này chạy khi classpath có dependency Spring Vault, Spring HTTP và các thư viện chuyển đổi dữ liệu tương thích theo dependency management, cùng class `DemoSecretReader` của mục 5. Nó **không khởi động Spring ApplicationContext**; việc dùng những class trong `org.springframework.*` không tự động tạo một container.

### Đọc kỹ phần vòng đời

- `new VaultTemplate(endpoint, authentication)` tạo một template dùng cơ chế session đơn giản. Nó thích hợp cho demo hoặc batch ngắn, không tự quản lý renewal/rotation lâu dài.
- `afterPropertiesSet()` và `destroy()` là các callback lifecycle mà Spring thường gọi cho bean được quản lý. Trong standalone, bạn có thể gọi chúng có chủ đích để giữ quy tắc khởi tạo/cleanup nhất quán.
- `template.destroy()` **không phải lệnh “thu hồi mọi token”**. Với `TokenAuthentication`, token có sẵn thường do bên ngoài quản lý; đừng hứa callback này sẽ revoke root token hoặc làm mất hiệu lực secret trong Vault.
- Nếu thêm `SessionManager` được tạo riêng, scheduler hoặc lease container, bạn còn phải xác định **ai sở hữu và đóng** từng đối tượng đó. Hủy template chưa chắc hủy một manager do caller truyền vào.
- `System.getenv(...)` trong ví dụ chỉ đọc biến môi trường; nó không có profile override như Spring Boot. Nếu cần file config hoặc command-line options, chương trình standalone phải tự định nghĩa cơ chế ưu tiên và validation.

Một điểm kỹ thuật: gọi `afterPropertiesSet()` trên `VaultTemplate` **không nên được hiểu là kiểm tra Vault server đang chạy**. Với các phiên bản gần đây, callback chủ yếu xác nhận trạng thái khởi tạo nội bộ; request `KV_2.get(...)` mới là phép kiểm tra thực tế cho network, token, policy và secret path.

### Thêm yêu cầu production

Code trên có kiểm tra cấu trúc URL nhưng **không giới hạn HTTP cho local**. Trong staging/production phải sử dụng HTTPS với certificate chain/trust store phù hợp, timeout và mạng được kiểm soát. Không dùng root token hoặc token dài hạn hardcode. Nếu script chạy trên Kubernetes/cloud, thay chiến lược authentication tĩnh bằng identity theo workload khi có cơ chế phù hợp.

## 8. Có thể dùng ApplicationContext rất nhẹ mà không cần Spring Boot?

Có. `ApplicationContext` là khái niệm của Spring Framework, **không đồng nghĩa với Spring Boot**. Một utility Java có thể dùng `AnnotationConfigApplicationContext` để hưởng bean management và DI mà không chạy server HTTP hay Spring Boot.

Ví dụ:

~~~java
package com.example.vault;

import java.net.URI;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.vault.authentication.TokenAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultTemplate;

public final class VaultPlainSpringMain {

    public static void main(String[] args) {
        String address = System.getenv("VAULT_ADDR");
        String token = System.getenv("VAULT_TOKEN");

        if (address == null || token == null
                || address.isBlank() || token.isBlank()) {
            throw new IllegalStateException(
                    "Thiếu VAULT_ADDR hoặc VAULT_TOKEN");
        }

        // Context Spring Framework được mở/đóng tường minh.
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext()) {

            context.registerBean(VaultTemplate.class, () ->
                    new VaultTemplate(
                            VaultEndpoint.from(URI.create(address)),
                            new TokenAuthentication(token)));

            context.refresh();

            DemoSecretReader reader = new DemoSecretReader(
                    context.getBean(VaultTemplate.class));

            System.out.println(reader.sampleUsernameExists());
        }
    }
}
~~~

Đây là lựa chọn **có Spring `ApplicationContext` nhưng không có Spring Boot**. `try-with-resources` đóng context, để Spring gọi callback hủy của bean `VaultTemplate`. Ví dụ chủ động đăng ký bean bằng supplier; bạn vẫn cần tự tạo connection parameters và validation cho URI/authentication.

Tuy nhiên, **đừng chỉ tạo `AnnotationConfigApplicationContext` rồi quên `refresh()` hoặc `close()`** nếu dùng constructor mặc định. Các phương thức này quyết định lúc bean được tạo và tài nguyên được giải phóng.

Cách này hữu ích để thấy hai khái niệm “có Spring IoC container” và “có Spring Boot” là độc lập.

## 9. SessionManager, token TTL và trách nhiệm shutdown

Đây là điểm tạo ra khác biệt vận hành lớn nhất giữa hai mô hình.

### 9.1. Hai cách quản lý token

`SessionManager` cung cấp token dùng cho request. Spring Vault có hai triển khai thường gặp:

| Implementation | Khả năng chính | Ghi chú |
| --- | --- | --- |
| `SimpleSessionManager` | Lấy token từ `ClientAuthentication` và dùng lại | Không tự lên lịch renew hoặc revoke |
| `LifecycleAwareSessionManager` | Quản lý vòng đời token login, renew nếu token renewable và điều kiện cho phép | Cần scheduler và HTTP client phù hợp |

`AbstractVaultConfiguration` mặc định sử dụng `LifecycleAwareSessionManager`. Còn constructor `VaultTemplate(VaultEndpoint, ClientAuthentication)` hoặc `VaultTemplate(VaultClient, ClientAuthentication)` thường xây manager đơn giản, nên **không được suy ra có auto-renew**.

### 9.2. Ngữ cảnh chạy lâu và token không renewable

Nếu `TokenAuthentication` nhận một token tĩnh có TTL ngắn, nó không có credential nguồn để đăng nhập lại sau khi token bị revoke. Dù có scheduler, token không renewable vẫn không tự được “kéo dài mãi mãi”. Các lựa chọn đúng tùy platform gồm:

- Kubernetes auth: workload dùng ServiceAccount JWT để login và nhận token có policy phù hợp.
- AppRole: workload dùng RoleID/SecretID được cấp an toàn để login.
- AWS/GCP/Azure identity: workload dùng danh tính cloud với Vault auth backend đã cấu hình.
- Một cơ chế Vault Agent hoặc broker credential được vận hành riêng, nếu kiến trúc yêu cầu.

Không phải auth method nào cũng có thể renew token giống nhau. Quy tắc TTL, max TTL, revocation và login lại phụ thuộc Vault role, loại token, policy và cơ chế quản lý phiên.

### 9.3. Khi không có container, phải có ownership rõ ràng

Giả sử một chương trình standalone dùng manager và scheduler riêng:

~~~text
StandaloneMain (chủ sở hữu)
   |
   +-- HTTP client / connection pool
   +-- ClientAuthentication / login client
   +-- SessionManager
   |      |
   |      +-- TaskScheduler (nếu có)
   +-- VaultTemplate
   +-- SecretLeaseContainer (nếu dùng secret động)
~~~

Ứng dụng phải định nghĩa thứ tự shutdown phù hợp: dừng các tác vụ mới, để các operation đang chạy kết thúc có giới hạn, dừng container theo dõi lease nếu có, dispose session manager do ứng dụng sở hữu, rồi đóng scheduler/HTTP resources. Không giả định `VaultTemplate.destroy()` sẽ tự đóng mọi dependency **được truyền từ bên ngoài**.

Nếu đối tượng triển khai `DisposableBean`, có thể gọi `destroy()` theo contract trong code quản lý lifecycle tương ứng. Nhưng **không tự gọi destroy nhiều lần** trên cùng một resource do các lớp cùng tham chiếu, và không hủy token được quản lý bởi một dịch vụ khác chỉ vì process này kết thúc.

Trong Spring context, việc đăng ký đúng những đối tượng này dưới dạng bean giúp Spring điều phối cleanup; tuy nhiên, cấu hình tự tạo bean có thể vẫn phải chỉ rõ destroy method hoặc ownership đối với thư viện/HTTP resources không được Spring biết.

## 10. Secret lease không phải lifecycle của VaultTemplate

Một token Vault dùng để đọc KV có TTL, nhưng việc đọc KV secret tĩnh **thường không cấp lease mới cho mỗi request**. Ngược lại, một database secrets engine có thể phát hành username/password động với `lease_id` và `lease_duration`, cần renew hoặc rotate/revoke.

| Khía cạnh | Token phiên làm việc | Lease của secret động | KV secret tĩnh |
| --- | --- | --- | --- |
| Được tạo bởi | Vault auth method hoặc token API | Dynamic secrets engine | KV put/write trước đó |
| Dùng để | Xác thực request Vault | Giới hạn hiệu lực credential/tài nguyên | Lưu cấu hình/secret ứng dụng |
| Quản lý bởi | `SessionManager` hoặc agent/broker | `SecretLeaseContainer`/logic ứng dụng | `VaultKeyValueOperations` để đọc/ghi |
| Cần renew? | Tùy token renewable/TTL | Tùy engine và lease | Không renew lease cho mỗi KV read |
| Cần xử lý khi dừng? | Theo ownership và chính sách revoke | Theo lease/rotation policy | Không xóa KV chỉ vì app shutdown |

Trong Spring context, `AbstractVaultConfiguration` có thể cung cấp `SecretLeaseContainer`. Nhưng **có bean không có nghĩa mọi secret đã được đăng ký theo dõi**. Ứng dụng/integration phải xác định những secret động cần lease tracking. Ngoài context, bạn phải xây và quản lý thêm thành phần theo dõi nếu use case yêu cầu.

Với Transit encryption hoặc PKI, `VaultTemplate` cung cấp API cấp cao tương ứng, nhưng policy và vòng đời tài nguyên không giống một KV read. Ví dụ certificate PKI có thời gian hiệu lực riêng; không nên coi mọi certificate là một lease có thể gia hạn theo cùng thuật toán token.

## 11. VaultTemplate và những API khác dùng lại ra sao?

Mẫu thiết kế nên dùng là **dependency inversion**: class nghiệp vụ nhận interface `VaultOperations` chứ không tạo `VaultTemplate` bằng `new` bên trong.

~~~java
public final class SecretStatusService {

    private final VaultOperations vault;

    public SecretStatusService(VaultOperations vault) {
        this.vault = vault;
    }

    public boolean hasSecret() {
        VaultResponse response = vault
                .opsForKeyValue("secret", KeyValueBackend.KV_2)
                .get("demo/app");
        return response != null && response.getData() != null;
    }
}
~~~

Đoạn trên minh họa phần thân class; cần các import tương tự `DemoSecretReader` ở mục 5.

Ưu điểm:
- Chạy được ở Spring Boot service, CLI và batch bằng cùng core logic.
- Unit test có thể mock/fake `VaultOperations` mà không phải khởi chạy Vault.
- Ở Spring, bean `VaultOperations` inject qua constructor; ngoài Spring, caller truyền `VaultTemplate`.
- Có thể thay phương thức xác thực hoặc constructor client mà không sửa logic KV.

**Không dùng trực tiếp `VaultTemplate.read("secret/data/demo/app")` thay cho `opsForKeyValue(..., KV_2)`** nếu bạn muốn Spring Vault xử lý cấu trúc response của KV v2. Direct HTTP/low-level read và KV-specific operations có envelope và cách giải mã khác nhau.

## 12. Dùng Vault Agent khi không muốn Java quản lý login

Spring Vault cũng có constructor:

~~~java
VaultTemplate template = new VaultTemplate(endpoint);
~~~

Constructor **chỉ có `VaultEndpoint`** không tự thêm cơ chế `ClientAuthentication`. Nó dành cho tình huống Vault Agent/proxy được cấu hình để cung cấp authentication ngoài ứng dụng.

Điều kiện để cách này hoạt động:

1. Ứng dụng gửi request tới đúng listener/đích do Vault Agent/proxy phục vụ.
2. Agent thực sự được cấu hình để xác thực và chèn/thực thi credential theo kiến trúc.
3. Kênh kết nối app tới agent được bảo vệ, đặc biệt khi khác container/host.
4. Vault policy của identity qua agent đủ quyền với path cần gọi.
5. Ứng dụng có phương án khi agent unavailable hoặc credential phía agent hết hạn.

**Không dùng `new VaultTemplate(endpoint)` trỏ thẳng tới một Vault server yêu cầu token** rồi cho rằng library sẽ tự đọc `VAULT_TOKEN` từ biến môi trường. Một constructor không có auth không được hiểu là cơ chế “auto-auth”.

Cả mô hình trong và ngoài `ApplicationContext` đều có thể dùng Vault Agent nếu hạ tầng đáp ứng các giả định trên.

## 13. TLS, cấu hình bên ngoài và an toàn thông tin

Dù Spring quản lý bean hay không, client vẫn cần được cấu hình an toàn:

| Vấn đề | Khi có Spring context | Khi standalone |
| --- | --- | --- |
| Vault URL | `Environment`/profiles/`@Value` | `System.getenv`, CLI args, config của chương trình |
| Token/AppRole/K8s JWT | Credential provider/bean từ runtime | Credential provider do chương trình tự tạo |
| TLS CA/trust store | HTTP client/SSL configuration beans | JVM trust store hoặc HTTP client tự cấu hình |
| Timeout và retry | Factory/client bean và framework chính sách | Programmatic HTTP client và logic retry |
| Vault HA | Endpoint provider/DNS/LB được cấu hình | Cũng cần endpoint ổn định và failover |
| Log/metric | Tích hợp Spring observability khi có | Tự tích hợp logging/metrics |
| Resource cleanup | Spring bean destroy/lifecycle | `try/finally`, `close()`/`destroy()` đúng ownership |

`VaultEndpoint` là base URL, không tự chứa CA, mTLS certificate, client private key hay timeout. Với Spring Vault 4.1+, có thể xây `VaultClient` để tùy chỉnh HTTP client và truyền vào `VaultTemplate`; ở phiên bản cũ có thể dùng constructor nhận `ClientHttpRequestFactory` và `SessionManager` thích hợp. **Đừng copy API 4.1 sang project Spring Vault 3.2/4.0**.

Staging/production nên sử dụng HTTPS, xác thực hostname và CA đúng. **Không tắt TLS validation** để xử lý lỗi PKIX. Nếu ứng dụng chạy trong container, `127.0.0.1` thường chỉ container/pod, không đại diện cho một Vault server khác.

### Không rò rỉ credential qua cấu hình/log

- Không commit Vault token, AppRole SecretID, Kubernetes JWT, private key hoặc database password.
- Không log `VaultResponse` đầy đủ, không in `apiKey` hoặc `username` thật khi test.
- Không truyền URL có userinfo/query chứa credential vào `VaultEndpoint`.
- Không trả thông điệp lỗi chứa token/secret ra API response.
- Dùng policy ít quyền nhất trên path cụ thể; không dùng root token ngoài lab.

Với KV v2 ở mount `secret` và path `demo/app`, policy chỉ đọc có thể là:

~~~hcl
path "secret/data/demo/app" {
  capabilities = ["read"]
}
~~~

Truy cập KV v2 đi qua `secret/data/...`, không phải `secret/demo/app` kiểu KV v1. Mã Java thành công khi sử dụng dev root token không chứng minh identity production sẽ đọc được secret.

## 14. Xử lý lỗi theo hai mô hình

| Triệu chứng | Khi có ApplicationContext | Khi standalone | Hướng xử lý |
| --- | --- | --- | --- |
| Không tạo được bean `VaultTemplate` | Lỗi property/bean scan/cấu hình trùng | Không áp dụng | Kiểm tra `@Configuration`, `Environment`, số bean |
| `NoSuchBeanDefinitionException` | `VaultOperations` chưa được đăng ký | Không áp dụng | Đăng ký bean hoặc import config đúng |
| `NoUniqueBeanDefinitionException` | Có nhiều Vault bean cùng kiểu | Không áp dụng | Dùng `@Qualifier` và chọn đúng target |
| Thiếu `VAULT_ADDR` | Placeholder/property chưa resolve | `requireEnv` ném lỗi | Cấp biến cho đúng process |
| URI sai định dạng | Bean endpoint khởi tạo lỗi | `validateBaseUrl` ném lỗi | Dùng base URL `http(s)://host[:port]` |
| `SSLHandshakeException`/PKIX | HTTP client hoặc trust store sai | JVM/HTTP client sai | Kiểm tra CA, hostname, mTLS |
| Timeout, connection refused | Địa chỉ/DNS/network/Vault listener sai | Tương tự | Kiểm tra từ đúng process/container |
| HTTP 401/403 | Token/role/policy không hợp lệ | Tương tự | Phân biệt authentication và quyền truy cập |
| HTTP 404 hoặc response null | Sai KV mount/path/engine version | Tương tự | Kiểm tra `secret`, `demo/app`, KV v2 |
| Lúc đầu thành công, sau TTL thì lỗi | Session/lifecycle chưa phù hợp | Token tĩnh hoặc manager không renew | Xem TTL, renewable, login lại |
| Thread nền không dừng | Scheduler bean/lifecycle cấu hình sai | Caller quên shutdown scheduler | Xác định ownership và dọn dẹp |
| Token không bị revoke khi đóng | Token do bên ngoài quản lý | Tương tự | Không hứa auto-revoke; thiết kế theo auth method |
| Một context shutdown làm mất client của job khác | Shared resource ownership sai | Không áp dụng | Không chia sẻ manager/HTTP resource mà thiếu ownership |

**Chẩn đoán theo tầng**: cấu hình khởi tạo → kết nối/TLS → authentication/token → policy → mount/path/dữ liệu. Đừng sửa SessionManager để giải quyết DNS, hoặc tăng timeout để sửa lỗi `403 permission denied`.

### Khi ứng dụng kết thúc bất ngờ

Callback dọn dẹp chỉ chạy nếu tiến trình kết thúc có kiểm soát. `SIGKILL`, crash, mất nguồn hoặc sự cố hệ điều hành có thể khiến shutdown hook không chạy. Vì vậy, security không thể phụ thuộc hoàn toàn vào `destroy()`; cần TTL giới hạn, policy ít quyền, khả năng revoke/rotation phía Vault và quy trình ứng phó sự cố.

## 15. Kiểm thử ứng dụng trong ApplicationContext

Khi dùng Spring Boot, có thể kiểm tra bean wiring mà không khởi động Vault thật bằng `ApplicationContextRunner`. Ví dụ nạp đúng `VaultAppConfig` và class nghiệp vụ `DemoSecretReader`:

~~~java
package com.example.vault;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultTemplate;

import static org.assertj.core.api.Assertions.assertThat;

class VaultAppConfigTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(VaultAppConfig.class);

    @Test
    void createsManagedVaultTemplateAndReader() {
        runner.withPropertyValues(
                "app.vault.uri=http://127.0.0.1:8200",
                "app.vault.token=test-token")
                .run(context -> {
                    assertThat(context)
                            .hasSingleBean(VaultTemplate.class);
                    assertThat(context)
                            .hasSingleBean(DemoSecretReader.class);

                    VaultOperations ops =
                            context.getBean(VaultOperations.class);

                    assertThat(ops)
                            .isSameAs(context.getBean(
                                    VaultTemplate.class));
                });
    }

    @Test
    void missingTokenFailsAtStartup() {
        runner.withPropertyValues(
                "app.vault.uri=http://127.0.0.1:8200")
                .run(context ->
                        assertThat(context).hasFailed());
    }
}
~~~

Dùng JUnit Jupiter, AssertJ và `spring-boot-test` phù hợp. Test này chứng minh Spring tạo/inject bean và báo lỗi property sớm, **không chứng minh kết nối Vault/TLS/policy thành công** vì chưa gửi HTTP request.

Với `AbstractVaultConfiguration`, test context có thể kiểm tra thêm `SessionManager` và scheduler do class cơ sở cung cấp. Đừng khai báo cả `VaultAppConfig` và `VaultInfrastructureConfig` trong cùng test nếu muốn chỉ có một `VaultTemplate`.

## 16. Kiểm thử standalone và tích hợp với Vault thật

### 16.1. Unit test không dùng Spring container

Vì `DemoSecretReader` là POJO nhận `VaultOperations` qua constructor, bạn có thể dùng mock/fake trong JUnit để kiểm tra cách service diễn giải response. Không cần `SpringApplication` hoặc `ApplicationContext` cho unit test này.

Bài test unit cần xác minh:
- Response `null` trả `false`, không gây `NullPointerException`.
- Trường `username` vắng hoặc rỗng trả `false`.
- Trường `username` hợp lệ trả `true`.
- Code dùng đúng `KV_2` và path `demo/app`.

Unit test trên không xác nhận endpoint, credential hoặc Vault HTTP API. Những yếu tố này thuộc **integration test**.

### 16.2. Integration test chung cho cả hai mô hình

Một thử nghiệm có giá trị nên chạy với Vault test instance, Vault dev server hoặc Testcontainers phù hợp:

| Kịch bản | Với Spring context | Với standalone |
| --- | --- | --- |
| Endpoint/token hợp lệ, policy `read` đúng | `DemoSecretReader` đọc KV v2 | Cùng class đọc KV v2 |
| Token bị revoke | Request bị từ chối | Request bị từ chối |
| Token thiếu `read` tại `secret/data/demo/app` | Không trả secret giả | Không trả secret giả |
| Sai KV mount/path | 404/null hoặc lỗi phù hợp | Tương tự |
| Vault chưa chạy | Startup/read có lỗi theo thiết kế | `main` báo lỗi và exit khác 0 |
| Vault HTTPS có CA riêng | HTTP client bean cần trust đúng | JVM/client được cấu hình trust đúng |
| TTL ngắn/renewable | Xác minh manager đã chọn | Chỉ xác minh renew nếu standalone có manager phù hợp |
| Resource shutdown | Đóng context và kiểm tra cleanup | `finally` được thực thi, tài nguyên được giải phóng |

Với test quyền, **không dùng root token** để thay thế token của workload. Nên tạo token có policy `read` giới hạn; đồng thời thử negative test với token thiếu quyền. Đối với Kubernetes auth hoặc AppRole, cần cấu hình backend và role thực, không chỉ mock `ClientAuthentication`.

### 16.3. Quan sát trong production

Những metric đáng theo dõi cho cả hai mô hình gồm:
- Thời gian gọi Vault KV/Transit/PKI.
- Lỗi kết nối/TLS/DNS và HTTP 4xx/5xx theo từng target.
- Tỷ lệ login thành công, lỗi token renew, token hết TTL và revoke.
- Event lease/rotation thất bại với secret động.
- Thời gian startup và khả năng phục hồi khi Vault unavailable.

Spring context có thể giúp tích hợp các công cụ observability đã có của ứng dụng, còn standalone có thể chủ động gắn logging/metric library. Dù cách nào, **không xuất token, SecretID, JWT, secret KV, private key PKI hoặc Transit key material** vào log, trace hay metric label.

## 17. Checklist thiết kế và câu hỏi tự luyện

Trước khi chọn mô hình, trả lời các câu hỏi sau:

| Câu hỏi | Nếu “có” |
| --- | --- |
| Ứng dụng đã dùng Spring Boot để quản lý dependency? | Đăng ký Vault bean trong context thường đơn giản nhất |
| Process chạy lâu và token có TTL? | Cần thiết kế session renewal/login lại và shutdown |
| Chạy batch một lần rồi thoát? | Standalone `VaultTemplate` có thể phù hợp |
| Nhiều dynamic secrets có lease? | Cần lease tracking/rotation theo từng engine |
| Nhiều Vault server hoặc danh tính? | Cần client/session/credential tách biệt |
| Yêu cầu TLS CA riêng, mTLS, proxy hoặc timeout? | Cần HTTP client phù hợp ở cả hai mô hình |
| Có Vault Agent quản lý auto-auth? | Có thể xem xét constructor không có auth, nhưng kiểm chứng agent |
| Có cần kiểm tra policy ít quyền? | Phải dùng identity thực tế và negative test, không chỉ root token |

Tự luyện:

1. Vì sao `VaultTemplate` có thể hoạt động không cần `ApplicationContext`?
2. Sự khác nhau giữa `new VaultTemplate(...)` và một bean `@Bean VaultTemplate` về lifecycle là gì?
3. Tại sao `DemoSecretReader` không có `@Service` vẫn sử dụng được cả hai mô hình?
4. Khi không có Spring context, ai chịu trách nhiệm gọi `afterPropertiesSet()`, `destroy()` và đóng scheduler nếu có?
5. Vì sao `template.destroy()` không bảo đảm một token tĩnh do bên ngoài cấp bị revoke?
6. Khi chạy Spring Boot với `AbstractVaultConfiguration`, bạn phải cung cấp hai phương thức nào?
7. Nếu `VaultTemplate(endpoint, authentication)` chạy được lúc đầu, điều đó có chứng minh nó sẽ tự renew mọi token không?
8. `VaultTemplate(endpoint)` khác `VaultTemplate(endpoint, authentication)` ra sao khi dùng Vault Agent?
9. Vì sao `ApplicationContextRunner` không thể thay thế phép thử đọc KV bằng policy thật?
10. Nếu đọc secret KV v2 tại `secret/demo/app`, đường dẫn policy `read` cần là gì?
11. Nếu một chương trình standalone bị `SIGKILL`, có thể dựa hoàn toàn vào `finally` để revoke token không?
12. Đối với ứng dụng Java không dùng Spring nhưng chạy liên tục với nhiều dynamic leases, bạn cần thiết kế những thành phần bổ sung nào?

**Tổng kết:** Spring Vault là **thư viện có thể dùng độc lập**, còn `ApplicationContext` là một cách quản lý dependency và vòng đời rất hữu ích. Ứng dụng ngắn hạn có thể khởi tạo `VaultTemplate` trực tiếp và chủ động cleanup; ứng dụng Spring Boot hoặc workload chạy lâu nên cân nhắc bean management, `SessionManager` và lease lifecycle. Cả hai cách phải giữ nguyên các nguyên tắc: endpoint/TLS đúng, xác thực theo workload, policy ít quyền nhất, không lộ secret và kiểm thử tích hợp bằng Vault thực.

### Tài liệu chính thức

- [Spring Vault Reference: Introduction to VaultTemplate](https://docs.spring.io/spring-vault/reference/vault/imperative-template.html)
- [Spring Vault Javadoc: VaultTemplate](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultTemplate.html)
- [Spring Vault Javadoc: SessionManager](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/SessionManager.html)
- [Spring Vault Javadoc: AbstractVaultConfiguration](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/config/AbstractVaultConfiguration.html)
- [Spring Framework Reference: Bean Lifecycle](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [HashiCorp Vault: KV Secrets Engine v2](https://developer.hashicorp.com/vault/docs/secrets/kv/kv-v2)


# Lấy cấu hình từ Environment đúng thời điểm khởi tạo

Trong chương **Cấu hình Java** của module **SPRING_VAULT**, ứng dụng cần đọc địa chỉ HashiCorp Vault, cơ chế xác thực và các lựa chọn kết nối trước khi tạo `VaultTemplate`. Một lỗi thường gặp là **đọc cấu hình quá sớm**, lúc Spring chưa chuẩn bị xong nguồn thuộc tính, hoặc **đọc quá muộn**, sau khi bean kết nối Vault đã được tạo bằng giá trị cũ.

Bài này giải thích cách sử dụng `org.springframework.core.env.Environment` **đúng thời điểm trong vòng đời khởi tạo Spring**. Chúng ta sẽ tạo các bean `VaultEndpoint`, `ClientAuthentication` và `VaultTemplate` dựa trên thuộc tính hiện hành, chuyển môi trường bằng Spring profiles và biến môi trường, kiểm tra lỗi cấu hình từ startup, sau đó xác minh kết nối bằng một secret KV v2. Các nguyên tắc tương tự cũng áp dụng khi ứng dụng tiến tới xác thực theo workload, token/lease lifecycle, Transit encryption và PKI.

**Mục tiêu sau bài học:**

- Giải thích khi nào Spring chuẩn bị `Environment` và khi nào các phương thức `@Bean` được thực thi.
- Phân biệt `getProperty(...)` và `getRequiredProperty(...)`, `@Value`, `@ConfigurationProperties` và biến môi trường hệ điều hành.
- Đưa cấu hình Vault vào bean **trong lúc Spring khởi tạo context**, thay vì dùng biến `static` hoặc đọc trễ trong `CommandLineRunner`.
- Hiểu thay đổi cấu hình sau startup có tác động gì tới các bean `VaultTemplate` đang chạy.
- Viết và kiểm tra một cấu hình Java tự chứa, có bảo vệ token và cơ chế báo lỗi rõ ràng.

## 1. Environment là gì trong ứng dụng Spring?

`Environment` là abstraction của Spring để đọc **properties** và **profiles** đang có hiệu lực. Nó hợp nhất nhiều `PropertySource` theo độ ưu tiên do Spring Framework/Spring Boot quy định, chẳng hạn:

- Biến môi trường của process (ví dụ `VAULT_ADDR`).
- Java system properties (`-Dapp.vault.uri=...`).
- `application.yml`, `application.properties` và các file dành cho profile.
- Thuộc tính truyền từ command line hoặc công cụ triển khai.
- Nguồn cấu hình được đăng ký sớm qua cơ chế thích hợp của Spring Boot/Spring Framework.

`Environment` **không phải** chính HashiCorp Vault. Nó chỉ là nơi Spring tra cứu những giá trị cần thiết để **kết nối tới Vault**.

Ví dụ trong ứng dụng tự cấu hình:

~~~yaml
app:
  vault:
    uri: ${VAULT_ADDR}
    token: ${VAULT_TOKEN}
~~~

Hai khóa `app.vault.uri`, `app.vault.token` là **quy ước do ứng dụng tự đặt**. Spring Boot giải quyết các placeholder `${VAULT_ADDR}` và `${VAULT_TOKEN}` khi truy xuất thuộc tính; còn `Environment.getRequiredProperty("app.vault.uri")` trả về giá trị URL sau khi placeholder được xử lý.

Nếu dùng `EnvironmentVaultConfiguration` có sẵn của Spring Vault, nhóm khóa được mong đợi lại là **`vault.uri`, `vault.authentication` và `vault.token`**. Không nên nhầm `app.vault.*` trong ví dụ tự tạo bean với `vault.*` của lớp cấu hình có sẵn hoặc `spring.cloud.vault.*` của Spring Cloud Vault.

## 2. Vòng đời khởi động: lúc nào cấu hình đã sẵn sàng?

Với Spring Boot, trình tự khái niệm như sau:

~~~mermaid
sequenceDiagram
    participant Runtime as OS / Deployment
    participant Boot as Spring Boot
    participant Env as Spring Environment
    participant Ctx as ApplicationContext
    participant Vault as Bean VaultTemplate
    participant Runner as CommandLineRunner

    Runtime->>Boot: Cấp env vars, system properties, args
    Boot->>Env: Chuẩn bị property sources và profiles
    Note over Env: Nạp application.yml và cấu hình profile
    Boot->>Ctx: Tạo/refresh ApplicationContext
    Ctx->>Env: Resolve properties cần cho bean
    Ctx->>Vault: Gọi @Bean để dựng endpoint/auth/template
    Vault-->>Ctx: Bean sẵn sàng để inject
    Ctx->>Runner: Chạy sau khi context đã khởi tạo
    Runner->>Vault: Thực hiện kiểm tra đọc secret nếu cần
~~~

Các giai đoạn cần nhớ:

| Giai đoạn | Điều đã xảy ra | Việc nên làm |
| --- | --- | --- |
| **Trước khi tạo Spring context** | Hệ điều hành/nền tảng cấp biến môi trường | Cấp đúng `VAULT_ADDR`, auth credentials, TLS settings |
| **Spring Boot chuẩn bị Environment** | Nguồn cấu hình và active profiles được tổng hợp | Đăng ký nguồn cấu hình cần có **trước lúc tạo bean** |
| **Spring khởi tạo bean** | `@Bean` methods/constructor injection được thực hiện | Đọc `Environment` và tạo `VaultEndpoint`, `ClientAuthentication`, `VaultTemplate` |
| **Context sẵn sàng** | Bean đã được tạo, các service có thể inject | Gọi KV/Transit/PKI theo thiết kế; kiểm tra quyền |
| **Ứng dụng đang chạy** | Bean thường giữ trạng thái cấu hình lúc tạo | Không mong đợi thay đổi một property sẽ tự tạo lại bean |
| **Shutdown/restart** | Spring quản lý destroy/lifecycle của bean | Giải phóng scheduler/session và khởi tạo lại nếu endpoint thay đổi |

**Điểm quan trọng:** việc Spring chuẩn bị `Environment` trước khi tạo bean không có nghĩa mọi nguồn cấu hình trên thế giới đều đã có sẵn. Nếu ứng dụng tự thêm một `PropertySource` **trong `CommandLineRunner`**, bean `VaultTemplate` đã được tạo trước đó và không tự thay endpoint hoặc token theo giá trị mới.

### “Đọc lúc tạo bean” không giống “đọc mỗi request”

Ví dụ:

~~~java
@Bean
VaultEndpoint vaultEndpoint(Environment environment) {
    String address =
            environment.getRequiredProperty("app.vault.uri");
    return VaultEndpoint.from(URI.create(address));
}
~~~

Spring gọi phương thức bean khi cần khởi tạo `VaultEndpoint` (thường là trong refresh context đối với singleton không lazy). Giá trị được đọc ở **thời điểm khởi tạo bean**, không phải mỗi lần `VaultTemplate` gửi một HTTP request.

Dù `Environment` có thể được hỏi lại lúc chạy, một `VaultEndpoint` đã được tạo từ URL cũ **không tự nhận URL mới**.

## 3. Đọc thuộc tính bằng Environment: chọn API phù hợp

`Environment` có các phương thức thường dùng sau:

| Cách đọc | Khi phù hợp | Nếu thiếu |
| --- | --- | --- |
| `getProperty("app.vault.uri")` | Thuộc tính thật sự optional | Trả `null` |
| `getProperty("app.vault.timeout", Integer.class, 3000)` | Optional có giá trị mặc định hợp lý | Trả `3000` nếu property không tồn tại |
| `getRequiredProperty("app.vault.uri")` | Endpoint phải có để khởi động | Ném lỗi khi thiếu |
| `getRequiredProperty("app.vault.token")` | Ví dụ token lab bắt buộc | Ném lỗi khi thiếu |
| `getActiveProfiles()` | Biết profile nào đang hoạt động | Mảng rỗng nếu không bật profile |
| `@Value("${app.vault.uri}")` | Inject một giá trị vào parameter/field do Spring quản lý | Có thể lỗi placeholder nếu không có fallback |
| `@ConfigurationProperties` | Gom nhiều thuộc tính cùng prefix và validation | Cần đăng ký/binding theo Spring Boot |

Với endpoint Vault, **`getRequiredProperty(...)` là mặc định an toàn hơn `getProperty(...)`**: nếu thiếu URI ở production, ứng dụng báo lỗi rõ thay vì truyền `null` cho HTTP client hoặc âm thầm kết nối tới Vault không mong đợi.

Dùng `getProperty(..., defaultValue)` chỉ khi fallback thật sự hợp lệ, chẳng hạn timeout có đơn vị và giới hạn phù hợp. **Không tạo mặc định root token hoặc endpoint HTTP cho production**.

Ví dụ:

~~~java
String endpoint = environment.getRequiredProperty("app.vault.uri");
int timeoutMillis = environment.getProperty(
        "app.vault.connect-timeout-ms", Integer.class, 3000);

if (timeoutMillis <= 0) {
    throw new IllegalArgumentException(
            "app.vault.connect-timeout-ms phải > 0");
}
~~~

`getRequiredProperty` chỉ kiểm tra **có giá trị property**; bạn vẫn phải tự kiểm tra chuỗi rỗng, cấu trúc URI, scheme và các ràng buộc khác theo nghiệp vụ.

## 4. Ví dụ hoàn chỉnh: tạo bean từ Environment đúng thời điểm

Ví dụ này dùng **Spring Boot, Java 17+ và `spring-vault-core`**, đồng thời tự khai báo bean. Cách tạo `VaultTemplate(VaultEndpoint, ClientAuthentication)` dùng được ở các nhánh Spring Vault thông dụng như 3.2, 4.0 và 4.1. Để đơn giản và có thể chạy ở local, authentication dùng token demo. Production nên dùng phương thức auth theo workload và session management phù hợp.

### 4.1. Thêm dependency

Trong dự án Maven có dependency management phù hợp:

~~~xml
<dependency>
    <groupId>org.springframework.vault</groupId>
    <artifactId>spring-vault-core</artifactId>
</dependency>
~~~

Nếu dự án chưa quản lý phiên bản của Spring Vault bằng BOM hoặc `dependencyManagement`, phải khai báo một version tương thích với Spring Framework/Spring Boot đang sử dụng.

### 4.2. Khai báo properties

`src/main/resources/application.yml`:

~~~yaml
app:
  vault:
    uri: ${VAULT_ADDR}
    token: ${VAULT_TOKEN}
~~~

`src/main/resources/application-local.yml`:

~~~yaml
app:
  vault:
    uri: ${VAULT_ADDR:http://127.0.0.1:8200}
~~~

Profile `local` cho phép URL mặc định chỉ trong lab. Nếu chạy với profile staging/prod, ứng dụng phải được cấp `VAULT_ADDR`. Ví dụ `app.vault.token` vẫn được yêu cầu vì đây là bài lab với token tĩnh; không coi mẫu này là hướng xác thực production.

### 4.3. Cấu hình Java: inject Environment vào phương thức bean

Tạo `VaultBeansConfiguration.java`:

~~~java
package com.example.vault;

import java.net.URI;
import java.util.Locale;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.vault.authentication.ClientAuthentication;
import org.springframework.vault.authentication.TokenAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultTemplate;

@Configuration(proxyBeanMethods = false)
public class VaultBeansConfiguration {

    @Bean
    VaultEndpoint vaultEndpoint(Environment environment) {
        String address = environment.getRequiredProperty(
                "app.vault.uri").trim();

        URI uri = URI.create(address);
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
                    "app.vault.uri phải là base URL http(s)://host[:port]");
        }

        int port = uri.getPort();
        if (port < 0) {
            port = "https".equalsIgnoreCase(scheme) ? 443 : 80;
        }
        if (port < 1 || port > 65535) {
            throw new IllegalArgumentException(
                    "Vault port phải nằm trong khoảng 1..65535");
        }

        VaultEndpoint endpoint =
                VaultEndpoint.create(uri.getHost(), port);
        endpoint.setScheme(scheme.toLowerCase(Locale.ROOT));
        return endpoint;
    }

    @Bean
    ClientAuthentication clientAuthentication(
            Environment environment) {

        String token = environment.getRequiredProperty(
                "app.vault.token");

        if (token.isBlank()) {
            throw new IllegalArgumentException(
                    "app.vault.token không được rỗng");
        }

        // Chỉ phục vụ lab: không tự renew hoặc login lại khi token hết hạn.
        return new TokenAuthentication(token);
    }

    @Bean
    VaultTemplate vaultTemplate(
            VaultEndpoint endpoint,
            ClientAuthentication authentication) {

        return new VaultTemplate(endpoint, authentication);
    }
}
~~~

**Vì sao đây là cách đọc đúng thời điểm?**

1. `Environment` được Spring **inject trực tiếp vào phương thức `@Bean`**; không cần gọi `System.getenv(...)` hoặc tự khởi tạo `Environment`.
2. Spring có thể resolve `app.vault.uri` từ các nguồn đã chuẩn bị và tạo `VaultEndpoint` lúc tạo bean.
3. Nếu thiếu URI/token, phương thức bean báo lỗi **ngay tại startup** thay vì tiếp tục với một endpoint hoặc credential sai.
4. `VaultTemplate` nhận đúng instance `VaultEndpoint` và `ClientAuthentication` do Spring quản lý, không đọc lại cấu hình trong mỗi service.
5. `@Configuration(proxyBeanMethods = false)` phù hợp vì các phương thức bean nhận dependency qua tham số, **không tự gọi chéo** phương thức `@Bean`; tránh nhầm với cách tự gọi bean method trong chế độ non-proxy.

**Lưu ý về xác thực:** `TokenAuthentication` dùng một token đã có. Nó không biến token tĩnh thành một cơ chế xác thực workload có thể đăng nhập lại; nếu token hết TTL hoặc bị revoke, cần cấp lại token hoặc chuyển sang auth method phù hợp. Khi cần quản lý token lifecycle, dùng `SessionManager` và cơ chế login/renew tương ứng thay vì dựa vào một `VaultTemplate(endpoint, authentication)` đơn giản.

### 4.4. Cách chạy local

Terminal thứ nhất:

~~~bash
vault server -dev -dev-root-token-id=dev-only-token
~~~

Terminal thứ hai (Bash):

~~~bash
export SPRING_PROFILES_ACTIVE=local
export VAULT_ADDR=http://127.0.0.1:8200
export VAULT_TOKEN=dev-only-token

vault kv put secret/demo/app username=demo-user
~~~

Với PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "local"
$env:VAULT_ADDR = "http://127.0.0.1:8200"
$env:VAULT_TOKEN = "dev-only-token"

vault kv put secret/demo/app username=demo-user
~~~

Ví dụ giả định Vault dev server có KV v2 tại mount `secret`. Có thể kiểm tra bằng `vault secrets list -detailed`. **HTTP và root token của dev server chỉ dùng trong lab**, không đưa vào staging/production.

## 5. Xác minh với VaultTemplate sau khi Spring khởi tạo bean

Tạo `DemoSecretReader.java`:

~~~java
package com.example.vault;

import java.util.Map;

import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponse;

@Service
public class DemoSecretReader {

    private final VaultOperations vault;

    public DemoSecretReader(VaultOperations vault) {
        this.vault = vault;
    }

    public boolean sampleSecretExists() {
        VaultResponse response = vault
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

`VaultTemplate` triển khai `VaultOperations` nên Spring có thể inject vào service. Trong lớp chính `@SpringBootApplication`:

~~~java
@Bean
CommandLineRunner verifyVault(DemoSecretReader reader) {
    return args -> {
        if (!reader.sampleSecretExists()) {
            throw new IllegalStateException(
                    "Chưa đọc được secret mẫu tại secret/demo/app");
        }
        System.out.println("Spring Environment -> VaultTemplate -> KV v2: OK");
    };
}
~~~

Nhớ import `org.springframework.boot.CommandLineRunner` và `org.springframework.context.annotation.Bean`. Phương thức nằm **bên trong** lớp application/configuration, không phải một class độc lập.

Khi `CommandLineRunner` chạy, Spring context đã khởi tạo bean `VaultTemplate`. Bởi vậy đoạn này thích hợp để **kiểm tra kết nối sau khi cấu hình đã được đọc**, nhưng **không phải nơi nên đặt `VAULT_ADDR` hoặc `app.vault.uri` lần đầu**.

Với mount `secret`, path `demo/app` và backend KV v2, request HTTP tương ứng là `GET /v1/secret/data/demo/app`. Policy đọc tối thiểu:

~~~hcl
path "secret/data/demo/app" {
  capabilities = ["read"]
}
~~~

Policy phải gắn với danh tính/token thật của Java workload. Chạy CLI bằng dev root token đọc được secret chưa chứng minh role production có quyền tương tự. Chỉ in trạng thái thành công, không in giá trị secret, token hoặc toàn bộ `VaultResponse`.

## 6. Cách khác: đọc Environment trong AbstractVaultConfiguration

Nếu dự án chọn kế thừa `AbstractVaultConfiguration`, **không đồng thời tạo bộ bean `VaultTemplate` như ở mục 4**. Lớp cơ sở đã cung cấp hạ tầng Vault và cho phép ứng dụng override hai phương thức bắt buộc.

Một mẫu cấu hình riêng có thể là:

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
public class VaultAbstractConfiguration
        extends AbstractVaultConfiguration {

    private final Environment environment;

    public VaultAbstractConfiguration(Environment environment) {
        this.environment = environment;
    }

    @Override
    public VaultEndpoint vaultEndpoint() {
        // Được gọi trong quá trình Spring tạo hạ tầng Vault.
        String address = environment.getRequiredProperty("app.vault.uri");
        return VaultEndpoint.from(URI.create(address));
    }

    @Override
    public ClientAuthentication clientAuthentication() {
        String token = environment.getRequiredProperty("app.vault.token");
        if (token.isBlank()) {
            throw new IllegalArgumentException("app.vault.token rỗng");
        }
        return new TokenAuthentication(token);
    }
}
~~~

Ví dụ ngắn này giả định `app.vault.uri` là **base URL hợp lệ**. Trong production, cần bổ sung kiểm tra URI/path/HTTPS/TLS tương tự mục 4. Hai override là các **điểm Spring Vault gọi khi dựng hạ tầng**, không phải các callback được gọi để refresh mọi lần đọc secret.

**Constructor injection** của `Environment` giúp bạn sử dụng trường `environment` sau khi constructor đã chạy. Không viết field initializer truy cập một trường môi trường chưa được inject, ví dụ:

~~~java
// KHÔNG NÊN: environment chưa được gán trong field initializer.
private final Environment environment;
private final String vaultUri =
        environment.getRequiredProperty("app.vault.uri");
~~~

Ngoài lỗi thứ tự khởi tạo Java, cách rải việc đọc thuộc tính ra các field initializer/static initializer khiến code khó phân biệt giai đoạn chuẩn bị cấu hình với giai đoạn tạo bean.

Nếu chỉ cần cấu hình dựa trên nhóm khóa `vault.*` đã được Spring Vault hỗ trợ, có thể cân nhắc `@Import(EnvironmentVaultConfiguration.class)` thay cho tự override. Khi đó lớp có sẵn đọc `vault.uri`, `vault.authentication` và các tùy chọn auth từ `Environment`. **`vault.*` không phải `app.vault.*`**: chọn đúng nhóm khóa theo hướng cấu hình đang dùng.

## 7. So sánh Environment, @Value và @ConfigurationProperties

Ba cách đều đọc giá trị từ cơ chế externalized configuration của Spring, nhưng mức độ kiểm soát khác nhau:

| Cách | Đọc giá trị khi nào? | Ưu điểm | Cần lưu ý |
| --- | --- | --- | --- |
| `Environment` trong `@Bean` | Khi method được Spring gọi để tạo bean | Rõ thời điểm, xử lý optional/required, validation có chủ đích | Phải tự chuyển kiểu và validate đủ |
| `@Value("${app.vault.uri}")` ở tham số `@Bean` | Khi Spring resolve tham số cho lần tạo bean | Rất ngắn với một vài khóa | Rải nhiều `@Value` khó quản lý |
| `@ConfigurationProperties(prefix = "app.vault")` | Khi Boot bind và đăng ký bean properties | Hợp nhiều khóa, validation và metadata | Phải kích hoạt binding đúng, chọn cách xử lý credential an toàn |
| `System.getenv("VAULT_ADDR")` trực tiếp | Khi code gọi hệ điều hành | Không cần Spring | Bỏ qua profile/property precedence/placeholder; khó test và có thể đọc sai thời điểm |

Ví dụ `@Value` nhận endpoint tại thời điểm tạo bean:

~~~java
@Bean
VaultEndpoint vaultEndpoint(
        @Value("${app.vault.uri}") String uri) {
    return VaultEndpoint.from(URI.create(uri));
}
~~~

Đây là **phương án thay thế** cho method `vaultEndpoint(Environment)` ở mục 4, không phải một bean thứ hai. Nếu dùng nhiều properties (URI, auth method, namespace, timeout, TLS), `@ConfigurationProperties` giúp gom nhóm và validate rõ hơn. Tuy nhiên, quá trình bind vẫn diễn ra theo vòng đời Spring — không tự động đọc lại mọi giá trị ở mỗi request.

### @PropertySource và application.yml

`@PropertySource("classpath:vault.properties")` có thể thêm một nguồn dạng properties vào `Environment` trong quá trình xử lý cấu hình Spring, trước khi những bean thông thường cần giá trị đó được khởi tạo. Nhưng:

- `@PropertySource` chuẩn **không tự đọc YAML** nếu không cấu hình factory.
- Với Spring Boot, `application.yml`/`application.properties` được hệ thống config data tải sớm; thường **không cần** dùng `@PropertySource` chỉ để tải hai file đó.
- Một số cấu hình Boot **rất sớm**, chẳng hạn logging hoặc lựa chọn khởi động, có thể được quyết định trước khi `@PropertySource` trong context được xử lý. Không dùng `@PropertySource` cho những giá trị phải có trước giai đoạn đó.
- Spring `Environment` là một abstraction chứa property sources, chứ không bảo đảm mọi nguồn được thêm quá muộn sẽ làm bean cũ cập nhật.

## 8. Thêm PropertySource trước hay sau context refresh?

Đây là trọng tâm của “**đúng thời điểm khởi tạo**”.

### 8.1. Nguồn cấu hình phải có trước khi tạo bean

Thông thường nên dùng `application.yml`, profile-specific YAML, biến môi trường hoặc system properties do công cụ triển khai cung cấp **trước lúc process Java khởi động**. Nếu phải thêm nguồn cấu hình bằng code, dùng một hook **được gọi trước khi context tạo các bean phụ thuộc**, chẳng hạn `ApplicationContextInitializer` hoặc `EnvironmentPostProcessor` trong phạm vi và trình tự lifecycle phù hợp của Spring Boot.

Ví dụ khái niệm với `ApplicationContextInitializer`, chỉ thêm endpoint **không nhạy cảm** trước khi khởi tạo context:

~~~java
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.core.env.MapPropertySource;

SpringApplication app =
        new SpringApplication(VaultLearningApplication.class);

app.addInitializers(context -> {
    context.getEnvironment().getPropertySources()
            .addFirst(new MapPropertySource(
                    "runtimeVaultEndpoint",
                    Map.of("app.vault.uri",
                           "http://127.0.0.1:8200")));
});

app.run(args);
~~~

Đoạn trên minh họa **trình tự**: thêm property source khi initializer chạy **trước khi refresh bean**. Nó không phải file `main` hoàn chỉnh nếu chưa đặt vào một class Java có các import/chữ ký phù hợp và không thay cho việc cấu hình HTTPS ở production. Trong ứng dụng thật, nên ưu tiên cấu hình ngoài và chỉ dùng initializer khi có lý do rõ ràng.

**Không thêm token/SecretID/JWT thật bằng literal trong `Map.of(...)`.** Chúng phải được cấp an toàn theo workload và không xuất hiện trong Git.

### 8.2. Thêm thuộc tính trong CommandLineRunner là quá muộn để thay bean

Ví dụ phản tác dụng:

~~~java
@Bean
CommandLineRunner tooLate(
        ConfigurableEnvironment environment) {
    return args -> environment.getPropertySources()
            .addFirst(new MapPropertySource(
                    "lateSource",
                    Map.of("app.vault.uri",
                           "https://other-vault.example.internal:8200")));
}
~~~

Đoạn này giả định import `ConfigurableEnvironment`, `MapPropertySource` và `Map` đã có. Nó minh họa **điều không nên làm**: `CommandLineRunner` chạy sau khi Spring đã khởi tạo nhiều singleton bean, bao gồm `VaultEndpoint` và `VaultTemplate` trong cấu hình bài này. Gọi `environment.getProperty("app.vault.uri")` sau đó có thể thấy giá trị mới, nhưng **template đã được khởi tạo không tự động chuyển địa chỉ**.

Thậm chí việc thay một property source trong lúc runtime còn có thể gây tình trạng không nhất quán: phần code hỏi `Environment` trực tiếp nhận giá trị mới, phần code sử dụng bean đã tạo vẫn dùng giá trị cũ.

## 9. Active profiles và độ ưu tiên của PropertySource

Spring Boot cho phép cấu hình theo profile, ví dụ:

~~~yaml
# application.yml
app:
  vault:
    uri: ${VAULT_ADDR}
    token: ${VAULT_TOKEN}
~~~

~~~yaml
# application-local.yml
app:
  vault:
    uri: ${VAULT_ADDR:http://127.0.0.1:8200}
~~~

Ví dụ kết quả hiệu lực:

| Profile | Có VAULT_ADDR? | Giá trị app.vault.uri dự kiến |
| --- | --- | --- |
| `local` | Không | `http://127.0.0.1:8200` |
| `local` | Có | Giá trị `VAULT_ADDR` |
| `staging` | Không | Thiếu placeholder/không thể resolve; ứng dụng nên thất bại |
| `staging` | Có | Giá trị `VAULT_ADDR` |
| `prod` | Có | Giá trị `VAULT_ADDR` của production |

Phần này giả định không có một PropertySource ưu tiên cao khác ghi đè `app.vault.uri`. Thứ tự ưu tiên thật của Spring Boot có nhiều lớp: command-line properties, Java system properties, environment variables, config data, profile-specific files và những nguồn được thêm thủ công. **Đừng suy ra một quy tắc duy nhất “YAML luôn thắng biến môi trường”**; hãy kiểm tra `Environment` hiệu lực trong test hoặc tại runtime bằng phương thức an toàn.

Không log giá trị token. Đối với URI, nếu cần chẩn đoán thì chỉ ghi dạng đã được làm sạch, ví dụ scheme và hostname đã được kiểm soát, không để URL chứa userinfo hoặc query mang credential.

### Tách config và danh tính theo môi trường

Ở local, `app.vault.token` làm bài thực hành dễ chạy. Khi chuyển sang Kubernetes, AppRole hoặc cloud identity, bạn cần đổi implementation `ClientAuthentication` theo workload, không chỉ thay URL.

Ví dụ, một môi trường production có thể có:

~~~yaml
app:
  vault:
    uri: ${VAULT_ADDR}
    auth-method: kubernetes
    auth-role: ${VAULT_K8S_ROLE}
~~~

Các khóa `app.vault.auth-method` và `app.vault.auth-role` ở đây **chỉ là quy ước đề xuất** nếu bạn tự viết cấu hình Java cho Kubernetes auth; chúng **không tự kích hoạt provider** khi ứng dụng vẫn đang dùng `TokenAuthentication` của mục 4. Muốn dùng chúng, phải tạo `ClientAuthentication` tương ứng hoặc chuyển sang `EnvironmentVaultConfiguration` với khóa `vault.authentication=KUBERNETES` và `vault.kubernetes.*` được hỗ trợ.

## 10. Thay đổi cấu hình sau startup có tự cập nhật VaultTemplate không?

**Không theo mặc định.** Với singleton `VaultEndpoint`/`ClientAuthentication`/`VaultTemplate` do Spring tạo khi khởi động:

- Sửa `application.yml` trên ổ đĩa thường **không làm Spring Boot nạp lại bean ngay**.
- Thay `VAULT_ADDR` bên ngoài process đang chạy **không có nghĩa process Java tự nhận giá trị mới**.
- Dù một PropertySource được thêm hoặc thay đổi động, bean đã đọc chuỗi URI/token trước đó **không tự tạo lại**.
- `@Value`, `@ConfigurationProperties` và constructor injection thông thường không mặc nhiên biến bean thành “live configuration” theo mỗi request.
- Với các cơ chế refresh chuyên dụng, cần bảo đảm refresh **đồng bộ toàn bộ** endpoint, auth/session, HTTP client, connection và phụ thuộc; không chỉ refresh một trường rồi để những bean khác giữ cấu hình cũ.

Nếu đơn giản là đổi endpoint khi triển khai, **restart/redeploy có kiểm soát** thường rõ ràng và dễ kiểm thử hơn. Nếu yêu cầu runtime refresh, phải thiết kế riêng: an toàn concurrency, dọn dẹp kết nối cũ, quản lý token/lease và khôi phục khi reload thất bại.

### Token rotation khác với đổi property

`TokenAuthentication` giữ một token đã cung cấp; nó không tự login lại để lấy token mới khi token bị revoke. Trong hệ thống thật, có thể dùng Kubernetes/AppRole/cloud auth với session manager có cơ chế renew/login lại tùy loại token và điều kiện Vault, thay vì yêu cầu đổi `Environment` liên tục.

Đọc **KV secret tĩnh** không tạo một lease riêng cho mỗi lần đọc. Với **secret động** như database credentials, cần thêm cơ chế theo dõi lease/renew/revoke (ví dụ `SecretLeaseContainer` hoặc một integration tương ứng). Thời điểm khởi tạo hạ tầng Vault và vòng đời token/lease có liên hệ với nhau, nhưng không phải cùng một bài toán.

## 11. Lỗi thường gặp do đọc Environment sai thời điểm

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| `Could not resolve placeholder VAULT_ADDR` | Chưa cấp env var hoặc profile không nạp fallback | Xem active profile và biến môi trường của process Java |
| `IllegalStateException: required property ... not found` | `getRequiredProperty(...)` thiếu khóa | Cấp thuộc tính trước khi Spring tạo bean |
| `NullPointerException` khi tạo endpoint | Gọi `getProperty(...)` rồi dùng giá trị null | Dùng `getRequiredProperty(...)` và validate rõ |
| URI có path API hoặc scheme không hợp lệ | Giá trị `app.vault.uri` không phải Vault base URL | Kiểm tra format `http(s)://host[:port]` |
| Field initializer không dùng được Environment | Trường chưa inject khi initializer chạy | Đọc trong constructor sau injection hoặc phương thức `@Bean` |
| Runtime thấy property mới nhưng Vault vẫn gọi server cũ | Bean singleton đã được tạo trước khi đổi property | Restart/redeploy hoặc thiết kế refresh toàn bộ hạ tầng |
| Code dùng `System.getenv` mà YAML profile không có tác dụng | Bỏ qua abstraction của Spring | Đọc từ `Environment`/`@Value` |
| Lỗi `NoSuchBeanDefinitionException` | `@Configuration` không được scan/import | Kiểm tra cấu hình Spring context |
| Lỗi nhiều bean `VaultTemplate` | Cấu hình thủ công trùng `AbstractVaultConfiguration` hoặc Spring Cloud Vault | Chọn một nguồn bean hoặc qualifier tường minh |
| Kết nối từ container tới localhost bị từ chối | `127.0.0.1` chỉ container/pod hiện tại | Dùng Vault Service/DNS phù hợp |
| HTTP 401/403 | Token sai, hết hạn hoặc policy thiếu quyền | Kiểm tra auth/session, policy KV v2 path |
| HTTP 404/null | Sai mount KV, path hoặc engine version | Kiểm tra `secret`/`demo/app` và `KeyValueBackend.KV_2` |
| `SSLHandshakeException`/PKIX | HTTPS/TLS CA hoặc hostname sai | Cấu hình trust store/HTTP client, không tắt TLS verification |
| KV đọc được lúc khởi động nhưng sau đó lỗi | Token hết TTL, bị revoke, Vault unavailable | Thiết kế quản lý session/token và retry/timeout |

**Một lỗi cấu hình xuất hiện ở startup không phải thất bại của Vault server.** Cần phân biệt lỗi resolve property, khởi tạo bean, kết nối mạng, authentication, authorization và dữ liệu để xử lý đúng tầng.

## 12. Kiểm thử khởi tạo bằng ApplicationContextRunner

Có thể kiểm tra **cấu hình khi startup** mà chưa cần chạy Vault thật bằng `ApplicationContextRunner` từ `spring-boot-test`. Ví dụ dưới đây chỉ xác minh bean khởi tạo với property được cung cấp, không gọi HTTP API.

~~~java
package com.example.vault;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultTemplate;

import static org.assertj.core.api.Assertions.assertThat;

class VaultBeansConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(
                            VaultBeansConfiguration.class);

    @Test
    void createsVaultBeansWhenPropertiesExist() {
        runner.withPropertyValues(
                "app.vault.uri=http://127.0.0.1:8200",
                "app.vault.token=test-token-not-for-production")
                .run(context -> {
                    assertThat(context)
                            .hasSingleBean(VaultEndpoint.class);
                    assertThat(context)
                            .hasSingleBean(VaultTemplate.class);
                    assertThat(context.getBean(VaultEndpoint.class)
                            .getHost())
                            .isEqualTo("127.0.0.1");
                });
    }

    @Test
    void failsFastWhenEndpointIsMissing() {
        runner.withPropertyValues(
                "app.vault.token=test-token-not-for-production")
                .run(context ->
                        assertThat(context).hasFailed());
    }
}
~~~

Đoạn test này dùng `JUnit Jupiter`, `AssertJ` và `spring-boot-test`. Trong test không có mạng, `VaultTemplate` được tạo bằng token giả nhưng chưa gọi Vault; không kết luận policy hoặc TLS đã đúng.

### Kiểm tra thêm các nhánh cấu hình

| Tình huống | Kỳ vọng |
| --- | --- |
| Có URI và token | Có `VaultEndpoint`, `ClientAuthentication`, `VaultTemplate` |
| Thiếu `app.vault.uri` | Context khởi tạo lỗi rõ |
| Thiếu `app.vault.token` | Context khởi tạo lỗi rõ |
| Token rỗng | Bean authentication từ chối |
| URI có `/v1/secret` | Bean endpoint từ chối |
| URI không có scheme | Bean endpoint từ chối |
| URI HTTPS và port 8200 | Endpoint giữ đúng scheme/cổng |
| Tạo bean xong rồi sửa PropertySource | Bean đã tạo vẫn giữ endpoint cũ |
| Hai nguồn cấu hình có thứ tự ưu tiên khác nhau | Xác nhận bean dùng **giá trị hiệu lực** tại thời điểm tạo |

Kiểm thử với `ApplicationContextRunner` phù hợp để kiểm tra **lifecycle và externalized configuration**. Test tích hợp thật cần chạy Vault instance có auth, policy và secret thực tế.

## 13. Kiểm thử tích hợp, giám sát và an toàn

Sau khi test startup qua, nên có ít nhất một phép thử tích hợp sử dụng Vault dev/test instance hoặc Testcontainers phù hợp với module:

1. Nạp profile local và các biến môi trường cần thiết **trước khi** tạo Spring context.
2. Khởi chạy Vault test instance, mount KV v2 ở `secret` và ghi dữ liệu `demo/app`.
3. Tạo một token **không phải root** với policy `read` tại `secret/data/demo/app` nếu cần kiểm tra least privilege.
4. Tạo Spring context, xác nhận `VaultTemplate` được inject.
5. Gọi `DemoSecretReader.sampleSecretExists()`, kiểm tra giá trị boolean thay vì in secret.
6. Thử token thiếu quyền: request bị từ chối; không chuyển 403 thành dữ liệu giả.
7. Thử sai URL, TLS, mount/path và lỗi mạng để khoanh vùng chính xác.
8. Nếu chuyển sang workload auth, kiểm tra TTL/token lifecycle và quyền của identity thực tế.

Các thao tác KV, Transit và PKI có endpoint/policy khác nhau; nhưng **chúng đều cần hạ tầng được tạo sau khi Environment có cấu hình phù hợp**. Sự đúng đắn của phần bean không thay thế kiểm tra policy engine-specific.

**Giám sát:** theo dõi startup failures (thiếu property), latency của Vault API, tỷ lệ 401/403/404, lỗi DNS/TLS, timeout, và tình trạng renew token khi dùng manager có lifecycle. Không đưa `VAULT_TOKEN`, AppRole SecretID, Kubernetes JWT, khóa Transit, private key PKI hay giá trị KV vào logs, trace, metric labels, exception messages gửi cho người dùng.

Với `/actuator/env` hoặc `/actuator/configprops` (nếu có Spring Boot Actuator), phải quản lý truy cập và cơ chế che giấu dữ liệu nhạy cảm; không dùng các endpoint quản trị đó để công khai credential chỉ nhằm kiểm tra precedence của property.

## 14. Tổng kết và câu hỏi tự luyện

**Mô hình nên nhớ:** nguồn cấu hình đến trước → Spring chuẩn bị `Environment` → Spring tạo bean bằng giá trị đã resolve → `VaultTemplate` bắt đầu thực hiện nghiệp vụ. Sau khi bean được tạo, thay property source không có nghĩa nó được tạo lại.

Tự luyện:

1. `Environment` trong Spring khác với `System.getenv(...)` ở khả năng nào?
2. Tại sao `getRequiredProperty("app.vault.uri")` thích hợp hơn `getProperty(...)` cho endpoint production?
3. Trong thứ tự khởi động, `CommandLineRunner` chạy trước hay sau khi `VaultTemplate` được tạo?
4. Nếu bạn thay `app.vault.uri` bằng cách thêm `MapPropertySource` ở runtime, `VaultEndpoint` singleton có tự cập nhật không?
5. Khi viết `@Configuration(proxyBeanMethods = false)`, vì sao ví dụ nên inject các dependency `@Bean` qua tham số?
6. Những phương thức nào phải override nếu dùng `AbstractVaultConfiguration` thay cho ba bean thủ công?
7. `EnvironmentVaultConfiguration` kỳ vọng `vault.uri` hay `app.vault.uri`? Spring Cloud Vault thường dùng nhóm khóa nào?
8. Cấu hình theo profile local nên đặt fallback HTTP ở đâu để không vô tình áp dụng cho production?
9. Test `ApplicationContextRunner` chứng minh được điều gì, và điều gì chỉ một bài kiểm thử tích hợp Vault mới chứng minh được?
10. Khi token tĩnh hết hạn sau một giờ, đổi `VAULT_ADDR` có giúp lấy token mới không?
11. Vì sao việc đọc KV secret tĩnh không đồng nghĩa có một secret lease mới cho mỗi lần đọc?
12. Tại sao không được in token/SecretID hoặc toàn bộ `VaultResponse` chỉ để debug cấu hình?

**Kết quả mong đợi:** bạn có thể đọc thuộc tính Vault từ `Environment` **đúng lúc tạo bean**, nhận lỗi cấu hình sớm, dùng profiles và externalized configuration phù hợp, và chứng minh `VaultTemplate` đọc được KV v2 bằng danh tính có quyền. Kiến thức này giúp mở rộng SPRING_VAULT sang xác thực workload, token và lease lifecycle, Transit encryption, PKI, xử lý lỗi, giám sát và kiểm thử tích hợp mà không tạo ra sự khác biệt ngầm giữa cấu hình ở startup và trạng thái đang chạy.

### Tài liệu tham khảo

- [Spring Framework Reference: Environment Abstraction](https://docs.spring.io/spring-framework/reference/core/beans/environment.html)
- [Spring Boot Reference: Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Vault Reference: VaultTemplate](https://docs.spring.io/spring-vault/reference/vault/imperative-template.html)
- [Spring Vault Reference: Authentication](https://docs.spring.io/spring-vault/reference/vault/authentication.html)
- [HashiCorp Vault: KV Secrets Engine v2](https://developer.hashicorp.com/vault/docs/secrets/kv/kv-v2)


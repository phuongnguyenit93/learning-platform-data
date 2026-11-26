# VaultPropertySource và Spring Environment

Trong một ứng dụng Java dùng **Spring Vault** để truy cập **HashiCorp Vault**, cấu hình thường được lấy từ nhiều nơi: tệp `application.yml`, biến môi trường, system properties, dòng lệnh và các bí mật lưu ở Vault. **Spring `Environment`** thống nhất các nguồn này thành một chuỗi `PropertySource` có thứ tự ưu tiên. **`VaultPropertySource`** là cầu nối giúp Spring đọc các khóa/giá trị lưu trong Vault thông qua `VaultTemplate` rồi đưa chúng vào chuỗi tìm kiếm cấu hình đó.

Bài thuộc chương **Nguồn cấu hình**, giải thích cách dữ liệu KV trở thành Spring properties, cách chọn thứ tự ưu tiên, sử dụng `@VaultPropertySource` và API đăng ký thủ công, phân biệt Spring Vault với Spring Cloud Vault Config Data, xử lý bootstrap, rotation, policy tối thiểu và kiểm thử tích hợp. Các quy tắc này quan trọng khi ứng dụng đồng thời sử dụng KV secrets, token/lease, Transit encryption và PKI.

## 1. Vì sao cần VaultPropertySource?

Giả sử `orders-api` cần các giá trị:

~~~properties
app.mode=staging
http.timeout=3000
database.password=<secret-do-vault-cap>
~~~

Đưa mật khẩu vào repository hoặc container image tạo ra nhiều bản sao khó kiểm soát. Ngược lại, mỗi thành phần trong ứng dụng tự gọi `VaultTemplate.read(...)` rồi tự parse key/value làm mã nghiệp vụ phụ thuộc vào định dạng Vault, khó áp dụng precedence và khó cấu hình những bean Spring vốn nhận property từ `Environment`.

`VaultPropertySource` đưa các giá trị về đúng abstraction của Spring:

~~~mermaid
flowchart LR
    A["Vault KV<br/>secret/orders-api"] --> B["VaultTemplate / VaultOperations"]
    B --> C["VaultPropertySource"]
    C --> D["MutablePropertySources<br/>trong Spring Environment"]
    E["application.yml / env / system properties"] --> D
    D --> F["getProperty / @Value / Bean binding"]
    F --> G["HTTP client / DataSource / feature config"]
~~~

Lợi ích chính là component sử dụng **tên property**, không phải tên endpoint Vault. Tuy nhiên, việc nhập dữ liệu vào `Environment` **không tự bảo đảm tất cả consumer nhận cấu hình mới khi Vault thay đổi**. Cách bean được tạo và giữ giá trị quyết định dữ liệu có được áp dụng lại hay không.

### Các khái niệm nền tảng

| Khái niệm | Vai trò | Điểm dễ nhầm |
| --- | --- | --- |
| `Environment` | API truy vấn properties và profile của ứng dụng Spring. | Không phải nơi phát hành token hoặc quản lý lease. |
| `PropertySource<?>` | Một nguồn giá trị theo key, có tên và thứ tự trong chuỗi tìm kiếm. | Nhiều source có thể cùng chứa một key. |
| `ConfigurableEnvironment` | Cho phép thao tác chuỗi `PropertySource`. | Thứ tự thay đổi ảnh hưởng giá trị được chọn. |
| `MutablePropertySources` | API `addFirst`, `addLast`, `addBefore`, `addAfter`, `replace`, `remove`. | `addFirst` ưu tiên cao trong tập đang xét. |
| `VaultTemplate` / `VaultOperations` | Client được xác thực gọi Vault qua HTTP/TLS. | Không tự tạo ra bean `VaultPropertySource` trong mọi cấu hình. |
| `VaultPropertySource` (class) | Đọc một đường bí mật ở Vault và trình bày thành Spring properties. | Đọc/cấp dữ liệu khác với `SessionManager` renew token. |
| `@VaultPropertySource` (annotation) | Đăng ký source khai báo trên `@Configuration`. | Đặt precedence giữa nhiều annotation có thể khó dự đoán. |
| `LeaseAwareVaultPropertySource` | Property source nhận cập nhật từ `SecretLeaseContainer`. | Property source thay đổi chưa chắc bean consumer được cập nhật. |

Tên trùng nhau nhưng thuộc **hai package Java khác nhau**:

- Class: `org.springframework.vault.core.env.VaultPropertySource`.
- Annotation: `org.springframework.vault.annotation.VaultPropertySource`.

Đối với `@VaultPropertySource`, Spring Vault còn dùng các thành phần đăng ký annotation để thêm sources vào `Environment` lúc cấu hình context.

## 2. Spring Environment tìm một property như thế nào?

Khi gọi:

~~~java
String mode = environment.getProperty("app.mode");
~~~

Spring duyệt các `PropertySource` trong `Environment` theo **thứ tự ưu tiên hiện hành**. Source đầu tiên cung cấp key phù hợp sẽ quyết định giá trị đọc được. Nếu không có key, `getProperty` có thể trả `null`; `getRequiredProperty` sẽ ném exception khi key bắt buộc không tồn tại.

Ví dụ minh họa, giả sử thứ tự sources đã được sắp đặt chủ động như sau:

| Thứ tự tìm | PropertySource | `app.mode` | `http.timeout` |
| --- | --- | --- | --- |
| 1 – cao nhất | `vaultOrders` | `production` | Không có |
| 2 | `operatorOverrides` | `staging` | `2000` |
| 3 | `applicationConfig` | `local` | `3000` |

Kết quả:

~~~text
environment.getProperty("app.mode")      -> "production"
environment.getProperty("http.timeout")  -> "2000"
~~~

Source đầu tiên chỉ thắng **với key mà nó thực sự chứa**; các key còn lại tiếp tục được tìm ở source phía sau. Đây là ví dụ về thứ tự được tổ chức thủ công, **không phải tuyên bố Spring Boot mặc định luôn ưu tiên Vault hơn command-line hay biến môi trường**. Với Spring Boot, Config Data, profile, command-line, environment variables và nhiều cơ chế khác cùng tham gia vào thứ tự cuối cùng.

### Quy tắc xử lý khi có key trùng

Không nên quyết định precedence theo cảm tính. Trước khi chọn `addFirst` hay cấu hình import, hãy xác định:

1. Có cho phép biến môi trường hoặc command-line **override** secret từ Vault không?
2. Có key nào bắt buộc **chỉ nhận từ Vault**, tránh fallback sang giá trị thử nghiệm cũ?
3. Key nào chỉ là cấu hình thông thường, không nhạy cảm và có thể đặt trong `application.yml`?
4. Cơ chế khẩn cấp khi Vault tạm ngừng: fail-fast hay dùng giá trị có hạn? Nếu fallback, ai quản trị vòng đời và cảnh báo?
5. Có nhiều source từ cùng Vault mount/profile dẫn đến cùng property name không?

Với mật khẩu hoặc signing material nhạy cảm, việc cho một nguồn không kiểm soát ghi đè Vault có thể gây lộ bí mật hoặc kết nối sai môi trường. Với feature flag/timeout không nhạy cảm, override bởi môi trường có thể là một yêu cầu vận hành hợp lý.

## 3. Chuẩn bị secret trong Vault KV

Ví dụ dùng KV version 2 được mount tại `secret/`. Để tách demo cấu hình khỏi thông tin nhạy cảm, có thể ghi các key không phải mật khẩu:

~~~bash
# Trong một Vault thử nghiệm có auth/policy phù hợp:
vault kv put -mount=secret orders-api \
  app.mode=staging \
  http.timeout=3000 \
  feature.checkout=true

# Kiểm tra theo tên logic của KV:
vault kv get -mount=secret orders-api
~~~

Lệnh `vault kv get` sẽ hiện dữ liệu; chỉ dùng trên môi trường test hoặc với dữ liệu không nhạy cảm. Nếu secret thật chứa password, không in toàn bộ response vào log, terminal chia sẻ, CI artifact hoặc screenshot.

Dữ liệu logic mà Vault lưu có thể trông như sau:

~~~json
{
  "app.mode": "staging",
  "http.timeout": "3000",
  "feature.checkout": "true"
}
~~~

Đường secret logic là `secret/orders-api`. Với KV v2, HTTP API thật có thể đi qua `/v1/secret/data/orders-api`, nhưng tài liệu Spring Vault chỉ rõ rằng khi sử dụng `@VaultPropertySource` với versioned KV, **đừng thêm phân đoạn `data/` vào path của annotation**. Spring Vault xác định mount/phiên bản engine khi xử lý property source. Để tự gọi `VaultTemplate.opsForKeyValue(..., KV_2)`, client cũng có abstraction riêng cho KV v2.

### Tài liệu lồng nhau và tên property

Nếu một bản đồ secret chứa:

~~~json
{
  "database": {
    "pool": {
      "max-size": 8
    }
  },
  "app.mode": "staging"
}
~~~

`VaultPropertySource` có khả năng flatten cấu trúc thành khóa dạng đường dẫn như `database.pool.max-size` bên cạnh `app.mode`. Khả năng map type, dấu chấm, dấu gạch nối và chuyển đổi kiểu của consumer cần được kiểm thử với dữ liệu cụ thể; không giả định mọi YAML/JSON nested object hay list sẽ khớp tự động mọi cấu hình Spring Boot.

## 4. Đăng ký VaultPropertySource bằng code Java

Cách lập trình cho phép kiểm soát trực tiếp tên source và thứ tự precedence. Ví dụ dưới đây giả định ứng dụng **đã có `VaultOperations` hợp lệ**, được xác thực bằng workload identity và xác minh TLS của Vault:

~~~java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MutablePropertySources;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.env.VaultPropertySource;

public final class VaultSourceRegistration {

    private VaultSourceRegistration() {}

    public static void register(
            ConfigurableEnvironment environment,
            VaultOperations vaultOperations) {

        VaultPropertySource vaultSource =
                new VaultPropertySource(
                        "vaultOrders",
                        vaultOperations,
                        "secret/orders-api"
                );

        MutablePropertySources sources = environment.getPropertySources();

        // Cố ý ưu tiên Vault cho những key có trong source này.
        sources.addFirst(vaultSource);
    }
}
~~~

Sau khi đăng ký và trước lúc consumer đọc property:

~~~java
String mode = environment.getRequiredProperty("app.mode");

Integer timeoutMillis =
        environment.getRequiredProperty("http.timeout", Integer.class);
~~~

Với dữ liệu ví dụ, `mode` là `staging` và `timeoutMillis` bằng `3000` nếu không có source ưu tiên cao hơn. `getRequiredProperty(key, type)` dùng cơ chế chuyển kiểu của `Environment`; nếu giá trị không chuyển thành số nguyên được, consumer phải xử lý lỗi cấu hình thay vì âm thầm dùng một timeout sai.

**Quan trọng về thời điểm:** constructor `VaultPropertySource` sẽ đọc dữ liệu từ Vault khi được khởi tạo. Vì vậy phương thức `register(...)` phải được gọi ở bước bootstrap **trước khi các bean cần property được xây dựng**. Nếu gọi sau khi bean đã tạo và lấy `@Value`, việc thêm source không tự hồi tố thay đổi field đã inject. Ví dụ trên là **hàm registration**, không phải một Spring Boot initializer hoàn chỉnh: để dùng thực tế, cần thiết kế nơi có thể tạo Vault client trước khi context cần secret.

### addFirst, addLast và vị trí tương đối

~~~java
MutablePropertySources sources = environment.getPropertySources();

sources.addFirst(vaultSource);     // source này ưu tiên cao nhất lúc gọi
// Hoặc:
// sources.addLast(vaultSource);   // fallback sau các source có sẵn
// sources.addBefore("knownSourceName", vaultSource);
// sources.addAfter("knownSourceName", vaultSource);
~~~

Các lựa chọn trên loại trừ nhau trong một lượt thêm, không thực thi đồng thời. Khi dùng `addBefore`/`addAfter`, tên source đích phải **tồn tại trong Environment thực tế**. Nên kiểm tra danh sách tên source trước khi áp dụng và viết test cho thứ tự đã chọn.

Khi thay thế source:

~~~java
sources.replace("vaultOrders", refreshedSource);
~~~

`refreshedSource` là một `PropertySource` đã được xây dựng hợp lệ. `replace` thay entry trong chuỗi tìm kiếm, nhưng **không tự khởi tạo lại các bean** đã dùng giá trị cũ. Không nên dùng việc rebuild source liên tục như cơ chế rotation dynamic credential khi đã có `SecretLeaseContainer`/`ManagedSecret` phù hợp.

## 5. Khai báo @VaultPropertySource trên @Configuration

Với ứng dụng cấu hình Spring bằng annotation, cách gọn hơn là:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.vault.annotation.VaultPropertySource;

@Configuration(proxyBeanMethods = false)
@VaultPropertySource(
        value = "secret/orders-api",
        propertyNamePrefix = "orders.",
        ignoreSecretNotFound = false
)
public class OrdersVaultPropertiesConfig {

    @Bean
    OrdersSettings ordersSettings(Environment environment) {
        String mode = environment.getRequiredProperty("orders.app.mode");
        int timeout = environment.getRequiredProperty(
                "orders.http.timeout", Integer.class);
        return new OrdersSettings(mode, timeout);
    }

    public record OrdersSettings(String mode, int timeoutMillis) {}
}
~~~

Các property `app.mode` và `http.timeout` được đưa vào `Environment` với prefix `orders.`, nên code đọc `orders.app.mode` và `orders.http.timeout`. Prefix có ích khi nhiều nhóm secret trùng tên key như `username`, `password`, `url`.

**Điều kiện chạy:** Spring phải có bean `VaultTemplate` hợp lệ (mặc định annotation tìm bean tên `vaultTemplate`) và các nguồn dùng để tạo Vault client đã được cung cấp trước thời điểm xử lý annotation. Java `record` yêu cầu phiên bản Java phù hợp. Đoạn code giả định Spring Vault/Context đã được cấu hình; chỉ thêm annotation mà không có Vault connectivity sẽ không đủ để chạy.

### Các thuộc tính đáng chú ý của annotation

| Thuộc tính | Mục đích | Mặc định/ghi chú |
| --- | --- | --- |
| `value` | Một hoặc nhiều đường secret Vault. | Bắt buộc; mỗi path trở thành một source. |
| `propertyNamePrefix` | Tiền tố cho tất cả key lấy từ source. | Chuỗi rỗng nếu không khai báo. |
| `vaultTemplateRef` | Tên bean `VaultTemplate` được sử dụng. | `vaultTemplate`. |
| `ignoreSecretNotFound` | Cho phép bỏ qua secret không tồn tại. | `true` theo Javadoc; cân nhắc đặt `false` cho config bắt buộc. |
| `renewal` | Chế độ quản lý lease của secret được đọc. | `VaultPropertySource.Renewal.OFF`. |

Vì `ignoreSecretNotFound=true` có thể khiến source trống khi thiếu path, **không sử dụng sự im lặng đó để bỏ qua secret bắt buộc của production**. Đặt `ignoreSecretNotFound=false` khi hệ thống phải fail-fast nếu nguồn không tồn tại; lưu ý lỗi network, authentication và policy cũng cần được phân loại riêng.

### Chọn VaultTemplate khác

~~~java
@Configuration
@VaultPropertySource(
        value = "secret/orders-api",
        vaultTemplateRef = "ordersVaultTemplate",
        ignoreSecretNotFound = false
)
class CustomVaultTemplateConfig {
    // ordersVaultTemplate phải là một bean VaultTemplate đã cấu hình hợp lệ.
}
~~~

Cấu hình này dùng khi ứng dụng có nhiều Vault client, khác mount/namespace hoặc endpoint. Việc dùng nhiều client đòi hỏi quản trị role/policy, TLS và session riêng; không dùng một Vault token rộng quyền cho mọi source chỉ vì dễ cấu hình.

## 6. Placeholder trong đường secret và phụ thuộc bootstrap

`@VaultPropertySource` hỗ trợ placeholder trong path, được giải từ **property sources đã có trước đó**:

~~~java
@Configuration
@VaultPropertySource(
        value = "secret/${spring.application.name:orders-api}",
        propertyNamePrefix = "appVault."
)
class VaultPathByApplicationName {
}
~~~

Nếu `spring.application.name=payments-api` tồn tại trong `Environment` ở thời điểm xử lý annotation, path có thể được giải thành `secret/payments-api`. Nếu thiếu, giá trị fallback trong ví dụ là `orders-api`. Placeholder không có giá trị mặc định và không giải được sẽ gây lỗi.

Không dùng path placeholder phụ thuộc vào một key **chỉ có thể được lấy từ chính Vault property source đang được tạo**. Đây là vòng phụ thuộc bootstrap:

~~~mermaid
flowchart TD
    A["Cần URI/auth và secret path để tạo VaultTemplate"] --> B["Cần đọc VaultPropertySource"]
    B --> C{"URI/auth/path có lấy từ nguồn có sẵn?"}
    C -- "Có" --> D["Tạo VaultTemplate, đọc secret, đăng ký source"]
    C -- "Không: chỉ nằm trong Vault source cần đọc" --> E["Vòng phụ thuộc bootstrap / startup failure"]
~~~

Các thông tin bootstrap tối thiểu cần tồn tại từ nguồn độc lập và đã bảo vệ: Vault URI, CA/truststore, cách xác thực workload, auth mount/role, path để đọc và một số timeout căn bản. Nếu runtime trên Kubernetes, JWT service account có thể đến từ volume được mount; với GCE, identity từ metadata server. Không phải đặt sẵn Vault root token hay password trong repository để giải quyết bootstrap.

### Tương tác với @Value và @ConfigurationProperties

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class CheckoutSettings {
    private final boolean enabled;

    public CheckoutSettings(@Value("${orders.feature.checkout:false}") boolean enabled) {
        this.enabled = enabled;
    }

    public boolean enabled() {
        return enabled;
    }
}
~~~

Ví dụ này chỉ đọc value **khi bean được tạo**. Khi Vault secret thay đổi sau đó, `enabled` là field `final` nên sẽ không tự thay đổi. Tương tự, `@ConfigurationProperties` được bind vào bean theo lifecycle của binder; không nên giả định mọi bản cập nhật `Environment` tự phát lại việc bind.

Nếu cần quan sát giá trị hiện hành, có thể gọi `environment.getProperty(...)` ở thời điểm sử dụng. Nhưng đọc property mới **vẫn chưa chắc** làm JDBC pool, TLS `SSLContext` hay HTTP client thay credential đã được nạp lúc khởi tạo; phải có cơ chế reload/reconfiguration thích hợp.

## 7. Thứ tự precedence của @VaultPropertySource

Khi có nhiều annotation `@VaultPropertySource` hoặc nhiều lớp `@Configuration` được quét qua component scanning, thứ tự thêm sources có thể không đủ rõ để dựa vào cho chính sách override. Chính tài liệu Spring Vault khuyến nghị dùng API `PropertySource` lập trình nếu cần kiểm soát ordering chặt.

Ví dụ hai nguồn:

~~~java
@Configuration
@VaultPropertySource(
        value = {
                "secret/orders-api",
                "secret/orders-api/region-apac"
        },
        propertyNamePrefix = "orders."
)
class RegionalProperties {
}
~~~

Mỗi path sẽ được thêm như một source và thứ tự path trong cùng annotation được khai báo theo thứ tự nêu ra. Nhưng khi phối hợp nhiều `@Configuration`, các loại Config Data và Spring Boot overrides, cần kiểm tra `Environment` tại runtime để biết **nguồn thực tế thắng cho từng key**. Không gắn ưu tiên tuyệt đối chỉ dựa vào tên thư mục hoặc thứ tự source trong code.

### Cách điều tra không làm lộ giá trị

Có thể ghi tên PropertySource theo thứ tự để hỗ trợ vận hành:

~~~java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

public final class PropertySourceDiagnostics {

    public static void printSourceNames(ConfigurableEnvironment environment) {
        for (PropertySource<?> source : environment.getPropertySources()) {
            System.out.println(source.getName());
        }
    }
}
~~~

Đoạn code chỉ in **tên source**, không in keys/values. Trong hệ thống thật, tên path cũng có thể chứa thông tin nội bộ; cần lọc trước khi xuất log công khai. Đừng gọi `environment.getProperty("database.password")` rồi log giá trị để xác định source thắng. Với key nhạy cảm, dùng test value giả hoặc công cụ nội bộ hiển thị chỉ “present/absent/source” theo quyền được duyệt.

## 8. Spring Vault khác Spring Cloud Vault Config Data thế nào?

Hai cách tiếp cận cùng đưa dữ liệu Vault vào `Environment` nhưng mức tự động hóa khác nhau.

| Tiêu chí | Spring Vault `VaultPropertySource` | Spring Cloud Vault Config Data |
| --- | --- | --- |
| Thư viện/vai trò | `spring-vault-core` cùng Spring context; tự khai báo class hoặc annotation. | Spring Cloud Vault tích hợp Spring Boot Config Data API. |
| Khai báo điển hình | `@VaultPropertySource("secret/orders-api")`. | `spring.config.import: "vault://"`. |
| Chọn path | Chủ động nêu từng path, có placeholder và prefix. | Context paths được cấu hình theo application/profile/backends hoặc contextual import. |
| Thứ tự | Theo `MutablePropertySources` và annotation registration. | Theo Config Data/import/order và Spring Boot configuration rules. |
| Bootstrap | Cần VaultTemplate/auth sẵn tại thời điểm source khởi tạo. | Spring Cloud Vault cung cấp integration bootstrapping, vẫn cần URI/auth/CA từ nguồn ban đầu. |
| Token/lease | Dùng cấu hình session và chế độ renewal của property source. | Spring Cloud Vault có lifecycle/session/secret management tích hợp theo cấu hình/phiên bản. |
| Phù hợp | Ứng dụng muốn quản lý nguồn cấu hình có chủ đích, dùng Spring Vault trực tiếp. | Ứng dụng Boot cần lấy cấu hình Vault ngay trong quá trình startup. |

Ví dụ `application.yml` cho ứng dụng **Spring Boot + Spring Cloud Vault** (không cần đồng thời khai báo `@VaultPropertySource` cho cùng path):

~~~yaml
spring:
  application:
    name: orders-api
  config:
    import: "vault://"
  cloud:
    vault:
      uri: "https://vault.internal.example:8200"
      authentication: KUBERNETES
      kubernetes:
        role: orders-api
      kv:
        enabled: true
        backend: secret
        application-name: orders-api
~~~

Với các dòng Spring Cloud Vault hỗ trợ Spring Boot Config Data, `vault://` nhập các nguồn đã enable; context mặc định thường gồm tên ứng dụng và profile (phụ thuộc cấu hình). Nếu muốn nhập một đường riêng, Spring Cloud Vault hỗ trợ contextual location theo cấu hình tài liệu phiên bản tương ứng.

**Không hiểu `spring.config.import` là thuộc tính riêng của `spring-vault-core`.** Nó được xử lý bởi Spring Boot cùng integration Spring Cloud Vault. Nếu dự án không có dependency Spring Cloud Vault phù hợp, chỉ viết `vault://` không tự tạo `VaultPropertySource`.

## 9. Gia hạn, thay đổi KV và cập nhật giá trị trong Environment

### 9.1. VaultPropertySource thông thường

Class `VaultPropertySource` tải dữ liệu khi khởi tạo và cung cấp các key qua `getProperty(...)`. Không nên suy rằng mỗi lần gọi `getProperty` sẽ mở HTTP request mới để đọc Vault. Đối với cấu hình ít thay đổi, mô hình nạp ở startup có thể phù hợp.

Nếu người quản trị ghi một version mới của KV, **bean đã nhận value cũ** bằng `@Value` hoặc binding không tự xoay vòng. Cần xác định có cơ chế refresh nguồn config và áp dụng lại bean hay không. Với KV v2, `@VaultPropertySource` dùng path logic không chứa `data/` để lấy version hiện hành tại thời điểm đọc.

### 9.2. LeaseAwareVaultPropertySource

`LeaseAwareVaultPropertySource` tích hợp với `SecretLeaseContainer` và `RequestedSecret`. Giá trị của source có thể được cập nhật ở background thread khi secret lease được renew/rotate và xóa khi hết hạn hoặc bị revoke. Đây là sự thay đổi **ở mức property source**, không phải cam kết thay mọi connection pool đang mở.

Annotation hỗ trợ ba giá trị cho thuộc tính `renewal`:

| Giá trị | Ý nghĩa |
| --- | --- |
| `VaultPropertySource.Renewal.OFF` | Không tự renew lease; mặc định. |
| `VaultPropertySource.Renewal.RENEW` | Thử renew lease định kỳ theo điều kiện máy chủ. |
| `VaultPropertySource.Renewal.ROTATE` | Renew nếu phù hợp và yêu cầu secret mới khi lease cũ hết hạn. |

Ví dụ lấy dynamic database credential bằng Spring Vault:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.vault.annotation.VaultPropertySource;
import org.springframework.vault.annotation.VaultPropertySource.Renewal;

@Configuration
@VaultPropertySource(
        value = "database/creds/orders-reader",
        propertyNamePrefix = "ordersDb.",
        renewal = Renewal.ROTATE,
        ignoreSecretNotFound = false
)
class RotatingDatabaseCredentialSource {
}
~~~

Giả sử engine trả `username` và `password`, property names là `ordersDb.username` và `ordersDb.password`. Khi có rotation, property source có thể đổi dữ liệu, **nhưng** `@Value` đã gán vào field của singleton hoặc DataSource đang giữ password cũ sẽ không tự chuyển sang tài khoản mới. Với ứng dụng cần rotation credential trong runtime, nên thiết kế consumer sử dụng event/callback như `ManagedSecret` (Spring Vault 4.1+) hoặc cơ chế update pool chuyên biệt.

### 9.3. Đừng nhầm lease của dynamic secret với KV version

| Nguồn | Cách thay đổi | Lưu ý |
| --- | --- | --- |
| KV v2 static secret | Ghi version mới ở path. | Không mặc định phát dynamic lease; cần chiến lược refresh/config reload. |
| Database dynamic credentials | Có `lease_id`/`lease_duration`, có thể renew hoặc rotate. | Pool cần thay user/password và connection khi account cũ hết hạn. |
| Vault client token | Renew/login lại qua `SessionManager`. | Gia hạn token không đồng nghĩa tự cập nhật nguồn configuration. |
| Transit key | Xoay khóa trong engine Transit theo policy. | Không tải material khóa Transit về `Environment` để mã hóa. |
| PKI certificate/private key | Phát hành/rotate và reload TLS consumer. | `Environment` chứa chuỗi property không thay thế keystore, CSR hay SSLContext. |

## 10. Policy, quyền và bảo mật dữ liệu cấu hình

Ví dụ policy tối thiểu khi application chỉ đọc `orders-api` từ KV v2:

~~~hcl
path "secret/data/orders-api" {
  capabilities = ["read"]
}
~~~

Với Vault KV v2, đường **policy/API** có `data` nhưng đường **logical secret** được truyền vào `@VaultPropertySource` là `secret/orders-api`. Phân biệt hai đường để tránh lỗi `403`.

Ngoài quyền đọc secret, Spring Vault có thể yêu cầu xác định mount/version qua `sys/internal/ui/mounts/...`. Nếu ứng dụng bị từ chối ở khâu kiểm tra mount, hãy đọc audit log/response được lọc và cấu hình chính sách theo đường API thực sự cần thiết; không cấp `sys/*` hoặc `secret/*` tùy tiện chỉ để bỏ qua lỗi.

### Các điểm có nguy cơ rò rỉ

- `Environment` có thể được truy vấn từ các bean, diagnostics và test helper. Không in toàn bộ properties hoặc `@ConfigurationProperties` chứa secret.
- Spring Boot Actuator `/env`, `/configprops`, debug endpoints và thông tin lỗi cần cấu hình quyền truy cập/chính sách masking cẩn thận. Không xem masking tự động là biện pháp duy nhất.
- Không để token Vault, JWT của workload hoặc private key trong property source nếu có cơ chế cấp/giữ credential chuyên dụng an toàn hơn.
- Giới hạn role/policy theo service và môi trường. Không dùng root token cho ứng dụng hoặc trong pipeline.
- Khi secret bị rotate, kiểm tra bản sao cũ trong JVM heap, log, cache, pool và file temp; xóa một version KV không tự thu hồi mọi credential đã sao chép.
- Bảo vệ Vault HTTPS bằng CA/truststore hợp lệ; không tắt kiểm tra certificate/hostname để đọc properties thành công.

**Nguyên tắc dữ liệu:** một secret đi vào `Environment` có thể được phân phối đến nhiều consumer trong tiến trình. Chỉ nhập những giá trị cần thiết và giới hạn thành phần có quyền xem, sử dụng hoặc log chúng.

## 11. Các tình huống lỗi thường gặp

| Triệu chứng | Nguồn có thể gây lỗi | Cách kiểm tra có mục tiêu |
| --- | --- | --- |
| `getProperty("orders.app.mode")` trả null | Sai prefix, sai path, source chưa đăng ký hoặc không có key. | Kiểm tên source, `propertyNamePrefix`, key KV và thứ tự khởi tạo. |
| Application startup thất bại vì thiếu bean `vaultTemplate` | `@VaultPropertySource` tìm template mặc định nhưng chưa có. | Kiểm bean name, cấu hình VaultTemplate, `vaultTemplateRef`. |
| Vault trả `403` khi nạp source | Token chưa đủ quyền, path KV v2 sai, mount discovery bị từ chối. | Kiểm auth role, policy `secret/data/...`, API path và audit logs. |
| Vault trả `404` | Secret path không tồn tại, mount sai hoặc engine chưa enable. | Kiểm KV logical path, KV v1/v2, `ignoreSecretNotFound`. |
| Vault bị timeout/TLS handshake thất bại | DNS, mạng, cert CA/SAN, HTTP client. | Kiểm `VaultTemplate` URI/truststore và root cause Java. |
| Property từ `application.yml` lấn át Vault | Precedence/import order khác mong đợi. | Kiểm thứ tự `MutablePropertySources`, tạo test key trùng có giá trị giả. |
| Annotation path chứa `data/` cho KV v2 | Nhầm path API với logical path. | Bỏ `data/` trong `@VaultPropertySource` theo tài liệu Spring Vault. |
| Thay đổi KV nhưng `@Value` vẫn cũ | Bean đã inject value từ lúc tạo. | Thiết kế refresh/rebind hoặc đọc `Environment` khi dùng. |
| Dynamic password mới có trong source nhưng JDBC 403/auth failed | Connection pool chưa thay credential. | Kiểm lifecycle pool và kết nối mới bằng credential đã rotate. |
| Context vẫn còn tác vụ lease sau shutdown | Container/registry không được quản lý lifecycle đúng. | Kiểm bean ownership, scheduler/`SecretLeaseContainer` stop/destroy. |

Khi điều tra, phân biệt **lỗi trước khi có HTTP response** (DNS/TCP/TLS), **lỗi Vault auth**, **lỗi policy đọc secret** và **lỗi Spring Environment mapping/precedence**. Cùng một biểu hiện “property null” có thể bắt nguồn từ cấu hình mặc định `ignoreSecretNotFound=true` hoặc lỗi consumer dùng sai key, nên cần dấu hiệu ở từng tầng.

## 12. Kiểm thử unit: chứng minh precedence mà không gọi Vault

Có thể kiểm tra thuật toán Spring `Environment` trước khi cấu hình Vault thật bằng `MockEnvironment` và `MapPropertySource`. Ví dụ JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.core.env.MapPropertySource;
import org.springframework.mock.env.MockEnvironment;

class PropertySourcePriorityTest {

    @Test
    void earlierPropertySourceWinsForMatchingKey() {
        MockEnvironment environment = new MockEnvironment();

        environment.getPropertySources().addLast(
                new MapPropertySource("local-fallback",
                        Map.of("app.mode", "local",
                               "http.timeout", "5000")));

        environment.getPropertySources().addFirst(
                new MapPropertySource("vault-test",
                        Map.of("app.mode", "staging")));

        assertEquals("staging", environment.getProperty("app.mode"));
        assertEquals("5000", environment.getProperty("http.timeout"));
    }
}
~~~

Test này cần `spring-test` và JUnit 5 trong scope test. Nó chứng minh thứ tự `PropertySource` và fallback khi thiếu key, **chưa chứng minh VaultTemplate đọc KV thật hoặc template bootstrap thành công**. Không thêm test chỉ xác nhận lại một hàm do chính test tự mô phỏng mà quên kiểm end-to-end.

## 13. Kiểm thử integration: từ Vault đến bean Spring

Dùng một Vault test instance cô lập và KV v2 mount `secret/` (có thể chạy Vault dev/Testcontainers với phiên bản image được dự án kiểm soát). Kịch bản integration nên thực hiện:

1. **Arrange:** tạo auth role/token dành riêng cho test với quyền `read` trên `secret/data/orders-api`; ghi `app.mode=staging` và `http.timeout=3000` bằng dữ liệu giả.
2. **Bootstrap:** cấu hình `VaultTemplate` kết nối Vault test, đăng ký `@VaultPropertySource` hoặc source thủ công **trước khi bean consumer được tạo**.
3. **Readback:** lấy `Environment.getRequiredProperty("app.mode")` hoặc `orders.app.mode` tùy prefix, so sánh giá trị đã ghi.
4. **Precedence:** thêm `MapPropertySource` chứa cùng key ở vị trí cao/thấp bằng dữ liệu giả và kiểm kết quả đọc đúng thứ tự mong muốn.
5. **Missing required secret:** dùng `ignoreSecretNotFound=false`, xóa một path test và xác nhận startup thất bại rõ ràng, không âm thầm dùng password fallback production.
6. **Policy denial:** dùng token thiếu `read` rồi xác nhận lỗi `403` được phân loại, không bị coi như secret không tồn tại.
7. **KV v2 semantics:** xác minh logical path trong annotation là `secret/orders-api`, còn policy là `secret/data/orders-api`.
8. **Rotation:** ghi version mới; xác định source nào refresh, bean nào giữ value cũ và yêu cầu reload nào phải triển khai. Nếu dùng dynamic secret, kiểm tra consumer thực sự đổi credential.
9. **Shutdown:** đóng `ApplicationContext` có trật tự, kiểm tra container/scheduler và client resources thuộc context được dừng.
10. **Cleanup:** revoke token/lease test và xóa tài nguyên thử nghiệm theo ownership, không sửa Vault production.

### Một negative test quan trọng

Giả sử `app.mode` có trong Vault nhưng application.yml cũng có `app.mode=local`. Nếu quy tắc vận hành yêu cầu Vault thắng, test **không chỉ assert mode=staging**. Phải assert nguồn Vault có precedence cao hơn và có thể xác minh tên `PropertySource` thắng cho key đó; nhờ vậy test bắt được trường hợp thứ tự import vô tình bị đảo khi nâng cấp Spring.

Nếu có credential dynamic với TTL ngắn, hãy dùng polling có deadline thay vì ngủ cố định; xác minh lease renewal và consumer reload riêng. Khi KV v2 ghi version mới, đừng suy diễn rằng source thông thường tự cập nhật hoặc tất cả bean tự refresh.

## 14. Checklist triển khai và bài tập

Trước khi dùng `VaultPropertySource` trong một Java service, nhóm phát triển cần trả lời:

1. **Nguồn:** key nào nằm ở Vault, key nào ở `application.yml` hoặc biến môi trường? Có secret trong repo/image không?
2. **Bootstrap:** Vault URI, truststore, workload identity và secret path đã có trước khi property source được tạo chưa?
3. **Đăng ký:** sử dụng class `VaultPropertySource`, annotation `@VaultPropertySource` hay Spring Cloud Vault `vault://`? Có đăng ký trùng không?
4. **Đường KV:** path logic là `secret/orders-api` hay API path `secret/data/orders-api`? Policy có đúng version không?
5. **Thứ tự:** khi hai source có cùng key, source nào phải thắng và test nào chứng minh điều đó?
6. **Prefix và placeholder:** tên property và path placeholder có được giải theo `Environment` đã tồn tại chưa?
7. **Thiếu secret:** config bắt buộc có fail-fast, hay `ignoreSecretNotFound` đang cho phép bỏ qua không báo lỗi?
8. **Động/tĩnh:** có cần lease renewal/rotation hay chỉ tải KV version ở startup? Bean consumer có reload được không?
9. **Quyền:** Vault token có policy chỉ đọc đúng path, và log/Actuator có được lọc secrets không?
10. **Kiểm thử:** đã chạy unit precedence, integration với Vault thật, negative test policy, sai path và shutdown chưa?

### Câu hỏi tự đánh giá

- Vì sao `Environment.getProperty("app.mode")` có thể trả giá trị khác với `@Value` đã inject khi property source thay đổi sau startup?
- Nếu thêm một `VaultPropertySource` bằng `addFirst` nhưng sau đó Spring Boot nạp thêm một source khác, có thể mặc định Vault vẫn ưu tiên cao nhất không?
- Vì sao `@VaultPropertySource("secret/data/orders-api")` dễ gây sai khi đọc KV v2?
- Nếu secret đang dùng không được phép thiếu, nên kiểm soát `ignoreSecretNotFound` và startup test thế nào?
- `LeaseAwareVaultPropertySource` có thể nhận secret mới, nhưng vì sao connection pool vẫn cần rotation logic?
- Khi ứng dụng dùng Spring Cloud Vault `spring.config.import: "vault://"`, điều gì khác với việc tự tạo `VaultTemplate` và thêm source bằng tay?

**Ghi nhớ:** `VaultPropertySource` đưa dữ liệu Vault vào **chuỗi nguồn cấu hình của Spring Environment**, còn thứ tự `PropertySource` quyết định giá trị của mỗi key. Việc nạp secret đúng thời điểm, dùng logical path KV phù hợp, xác thực theo workload, giữ policy tối thiểu và thiết kế refresh đến tận consumer sẽ giúp ứng dụng dùng Spring Vault an toàn mà không cần lưu credential cố định trong mã nguồn.

## Tài liệu chính thức tham khảo

- [Spring Vault – Property Sources](https://docs.spring.io/spring-vault/reference/vault/propertysource.html).
- [Spring Vault – VaultPropertySource annotation API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/annotation/VaultPropertySource.html).
- [Spring Vault – VaultPropertySource class API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/env/VaultPropertySource.html).
- [Spring Vault – LeaseAwareVaultPropertySource API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/env/LeaseAwareVaultPropertySource.html).
- [Spring Cloud Vault – ConfigData API](https://docs.spring.io/spring-cloud-vault/docs/current/reference/html/config-data.html).

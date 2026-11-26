# Tiền tố tên thuộc tính và tránh xung đột khóa trong Spring Vault

## 1. Bài toán: nhiều nguồn cấu hình cùng có một tên khóa

Trong module **Spring Vault**, ứng dụng Java dùng `VaultTemplate` để truy cập HashiCorp Vault theo danh tính workload và chính sách ACL. Bên cạnh đọc secret trực tiếp, ứng dụng có thể đưa các giá trị Vault vào **Spring `Environment`** dưới dạng `PropertySource` để dùng với `@Value`, `@ConfigurationProperties` hoặc các bean cần cấu hình.

Giả sử dịch vụ `orders-api` cần hai kết nối database:

- Database **primary** cho giao dịch ghi.
- Database **reporting** cho truy vấn báo cáo.

Cả hai nhóm secret đều có khóa `db.username` và `db.password`. Nếu nạp hai đường dẫn Vault vào Spring `Environment` mà giữ nguyên tên khóa, chỉ một giá trị `db.username` được trả về khi ứng dụng gọi `environment.getProperty("db.username")`. Giá trị từ một nguồn sẽ **che khuất (shadow)** giá trị cùng tên của nguồn khác.

Chủ đề của chương **Nguồn cấu hình** là giải quyết vấn đề này bằng cách **đặt tiền tố tên thuộc tính** cho từng nguồn, đồng thời hiểu cách thứ tự ưu tiên ảnh hưởng đến kết quả cấu hình.

Sau bài học, bạn có thể:

1. Phân biệt **đường dẫn secret trong Vault**, **tên khóa lưu trong secret**, **tên thuộc tính Spring sau khi nạp** và **prefix**.
2. Dùng `?prefix=...` với **Spring Cloud Vault ConfigData** hoặc `propertyNamePrefix` với **Spring Vault `@VaultPropertySource`**.
3. Biết khi nào `PropertySource` ghi đè/che khuất khóa, khi nào cần chủ động quản lý precedence.
4. Kết hợp tiền tố với `@Value` và `@ConfigurationProperties` để bind cấu hình chính xác.
5. Kiểm tra ACL cho KV v2, xử lý lỗi khởi tạo, tránh lộ bí mật qua log/Actuator và kiểm thử tích hợp.

## 2. PropertySource, trùng khóa và shadowing

Spring `Environment` tìm một thuộc tính qua **danh sách `PropertySource` có thứ tự**. Nguồn xuất hiện trước trong thứ tự tra cứu sẽ cung cấp giá trị khi nhiều nguồn cùng định nghĩa tên thuộc tính giống nhau.

Ví dụ:

| PropertySource | Đường dẫn Vault | Khóa được lưu | Tên thuộc tính khi nạp không prefix |
|---|---|---|---|
| `vault-orders-primary` | `kv-demo/orders/primary` | `db.username=primary_user` | `db.username` |
| `vault-orders-reporting` | `kv-demo/orders/reporting` | `db.username=report_user` | `db.username` |

Khi gọi:

```java
String username = environment.getProperty("db.username");
```

kết quả **phụ thuộc nguồn nào có precedence cao hơn**. Không có cơ chế tự đổi tên để trả về cả hai giá trị, cũng không có phép hợp nhất hai scalar `db.username` thành một đối tượng có hai thuộc tính. Nếu thứ tự nạp thay đổi do cấu hình hoặc profile, ứng dụng có thể lấy nhầm credential.

Với tiền tố riêng:

| Nguồn | Prefix | Tên khóa gốc | Tên thuộc tính Spring |
|---|---|---|---|
| Primary | `orders.primary.` | `db.username` | `orders.primary.db.username` |
| Reporting | `orders.reporting.` | `db.username` | `orders.reporting.db.username` |
| Primary | `orders.primary.` | `db.password` | `orders.primary.db.password` |
| Reporting | `orders.reporting.` | `db.password` | `orders.reporting.db.password` |

Hai nhóm cấu hình có **namespace riêng**, nên không còn tranh chấp cùng tên. Điều này đặc biệt hữu ích khi ứng dụng cần đồng thời nhiều datasource, nhiều AWS account, nhiều context Vault hoặc nhiều loại credential.

> **Ghi nhớ:** tiền tố chỉ thay đổi **tên thuộc tính được công bố vào Spring `Environment`**. Nó không đổi đường dẫn dữ liệu trong Vault, không đổi tên khóa lưu ở Vault và không tạo thêm quyền ACL.

## 3. Phân biệt ba loại “prefix” thường bị nhầm

| Khái niệm | Ví dụ | Tác động thực tế |
|---|---|---|
| **Vault mount/backend path** | `kv-demo` | Chọn secret engine KV được mount tại `kv-demo/` |
| **Context path trong Vault** | `orders/primary` | Chọn key nằm bên trong mount; kết hợp thành `kv-demo/orders/primary` |
| **Property-name prefix** | `orders.primary.` | Khi nạp khóa `db.username`, Spring thấy `orders.primary.db.username` |

Các thuộc tính `spring.cloud.vault.kv.backend`, `spring.cloud.vault.kv.default-context` và `spring.cloud.vault.kv.application-name` thuộc nhóm **chọn secret path/context**. Chúng **không phải** cấu hình tự thêm tiền tố vào mọi tên khóa mà Vault trả về.

Ví dụ, nếu Spring Cloud Vault tự chọn context theo `spring.application.name=orders-api`, một khóa `db.username` lấy từ context đó thông thường vẫn được công bố với tên `db.username`, chứ không tự biến thành `orders-api.db.username`.

Đối với KV v2, cần phân biệt hai kiểu path:

- **Đường dẫn logic trong Spring Cloud Vault hoặc `@VaultPropertySource`:** `kv-demo/orders/primary`.
- **Đường dẫn REST API / ACL của KV v2:** `kv-demo/data/orders/primary`.

Đoạn `data/` là thành phần của HTTP API KV v2. **Không chèn thủ công `data/` vào `@VaultPropertySource` hay contextual ConfigData import** chỉ vì backend là KV v2; thư viện nhận diện version và xử lý đường dẫn API tương ứng.

## 4. Chuẩn bị hai KV v2 context để thực hành

Ví dụ dùng Vault **dev/test độc lập**, KV v2 mount `kv-demo/` và dữ liệu giả. Chỉ chạy lệnh enable nếu mount chưa tồn tại; không ghi đè mount đang vận hành.

```bash
# Một lần trên Vault thử nghiệm chưa có mount kv-demo.
vault secrets enable -path=kv-demo -version=2 kv

# Mỗi context chứa khóa tên giống nhau.
# Các mật khẩu là placeholder của lab, không phải bí mật thật.
vault kv put -mount=kv-demo orders/primary \
  db.username=primary_user \
  db.password=LAB_PRIMARY_ONLY

vault kv put -mount=kv-demo orders/reporting \
  db.username=report_user \
  db.password=LAB_REPORT_ONLY

# Kiểm tra riêng từng key trong Vault.
vault kv get -mount=kv-demo orders/primary
vault kv get -mount=kv-demo orders/reporting
```

Các tên `db.username` và `db.password` là **khóa literal** được đưa vào KV; dấu chấm ở đây là một phần của tên khóa. Trong production, tránh đưa password thật trực tiếp trên command line vì có thể xuất hiện trong lịch sử shell hoặc thông tin process. Sử dụng kênh cấp phát và công cụ nhập bí mật của tổ chức.

Tài khoản workload không cần quyền tạo KV mount hay quyền ghi secret để sử dụng hai context. Policy đọc mẫu:

```hcl
path "kv-demo/data/orders/primary" {
  capabilities = ["read"]
}

path "kv-demo/data/orders/reporting" {
  capabilities = ["read"]
}
```

Workload đăng nhập qua Kubernetes Auth, AppRole hoặc certificate auth, nhận Vault token gắn với policy này. Khóa trong Vault có thể được đọc từ `VaultTemplate` chỉ khi token hợp lệ, TLS được kiểm tra và quyền `read` đúng path. Nếu Spring Vault cần truy vấn mount metadata để phát hiện KV v2, cũng phải bảo đảm cơ chế phát hiện mount hoạt động theo Vault/policy đang sử dụng.

## 5. Đặt prefix qua Spring Cloud Vault ConfigData

Với **Spring Boot 2.4+ và Spring Cloud Vault 3.0+** theo phiên bản tương thích, cơ chế **ConfigData API** cho phép nạp các context Vault bằng `spring.config.import`. Spring Cloud Vault hỗ trợ query parameter `prefix` cho **từng contextual location**.

Ví dụ `application.yml`:

```yaml
spring:
  application:
    name: orders-api
  config:
    import:
      - "vault://kv-demo/orders/primary?prefix=orders.primary."
      - "vault://kv-demo/orders/reporting?prefix=orders.reporting."
```

Ví dụ giả định đã có dependency Spring Cloud Vault Config và đã cấu hình Vault endpoint, TLS, auth method cùng token policy phù hợp bằng các tham số bootstrap/runtime khác. Không ghi `VAULT_TOKEN`, SecretID hoặc mật khẩu thực vào `application.yml`.

Khi ứng dụng khởi động, Spring Cloud Vault nạp **mỗi contextual location thành một `PropertySource`** và thêm prefix tương ứng vào tên các khóa trả về:

```text
Vault key: kv-demo/orders/primary
  db.username = primary_user
  db.password = [redacted]
       |
       | prefix=orders.primary.
       v
Spring Environment:
  orders.primary.db.username
  orders.primary.db.password

Vault key: kv-demo/orders/reporting
  db.username = report_user
  db.password = [redacted]
       |
       | prefix=orders.reporting.
       v
Spring Environment:
  orders.reporting.db.username
  orders.reporting.db.password
```

### 5.1. Dấu chấm cuối prefix có ý nghĩa gì?

**Prefix được nối nguyên văn với tên thuộc tính.** Spring Cloud Vault **không tự thêm dấu chấm**.

| Prefix trong import | Khóa nguồn | Tên kết quả |
|---|---|---|
| `orders.primary.` | `db.username` | `orders.primary.db.username` |
| `orders.primary` | `db.username` | `orders.primarydb.username` |
| `orders.primary-` | `db.username` | `orders.primary-db.username` |
| Rỗng | `db.username` | `db.username` |

Vì vậy, khi chọn namespace theo dạng dot-delimited, hãy ghi `?prefix=orders.primary.` có **dấu chấm cuối**. Nếu hai context cùng dùng một prefix thì khóa vẫn trùng nhau; chỉ “có prefix” thôi chưa đủ, **prefix phải khác nhau** cho những nguồn cần cùng tồn tại.

### 5.2. Explicit import khác `vault://` mặc định

- `vault://` là location mặc định: Spring Cloud Vault nạp các context từ các secret backend đã bật, với cơ chế xác định application name/profile.
- `vault://kv-demo/orders/primary?prefix=orders.primary.` là **contextual location chỉ định rõ một path**, có prefix cho các tên thuộc tính từ path đó.
- Kết hợp thêm `vault://` vào danh sách import có thể làm xuất hiện **những property source khác không có prefix**, nên cần rà soát khóa trùng.

Nếu hệ thống cần kiểm soát namespace của hai nguồn, ưu tiên liệt kê **các contextual locations** một cách rõ ràng và tránh vô tình nạp lại cùng key theo cơ chế default. Với phiên bản Spring Cloud Vault cũ dùng bootstrap context, không áp dụng nguyên xi cú pháp `spring.config.import`: phải xem cơ chế property source tương ứng phiên bản đó.

## 6. Đặt prefix bằng `@VaultPropertySource` của Spring Vault Core

Nếu dự án tích hợp **Spring Vault Core** trực tiếp mà không sử dụng Spring Cloud Vault ConfigData, annotation `@VaultPropertySource` đưa secret vào `Environment`. Thuộc tính `propertyNamePrefix` thêm tiền tố vào **mọi khóa** của property source.

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.vault.annotation.VaultPropertySource;

@Configuration
@VaultPropertySource(
        value = "kv-demo/orders/primary",
        propertyNamePrefix = "orders.primary.")
@VaultPropertySource(
        value = "kv-demo/orders/reporting",
        propertyNamePrefix = "orders.reporting.")
public class VaultPropertySourcesConfiguration {
    // VaultTemplate / VaultOperations đã được cấu hình tại ứng dụng.
}
```

`@VaultPropertySource` là annotation có thể sử dụng nhiều lần trên một lớp cấu hình. Trong ví dụ:

- `orders.primary.db.username` đến từ `kv-demo/orders/primary`.
- `orders.reporting.db.username` đến từ `kv-demo/orders/reporting`.
- `propertyNamePrefix` không thay đổi secret trong Vault.
- `@VaultPropertySource` với KV v2 sử dụng **đường dẫn logic không có `data/`**.

Để đọc thử trong mã nghiệp vụ:

```java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class DatabaseUsernames {

    private final Environment environment;

    public DatabaseUsernames(Environment environment) {
        this.environment = environment;
    }

    public String primaryUsername() {
        return environment.getRequiredProperty(
                "orders.primary.db.username");
    }

    public String reportingUsername() {
        return environment.getRequiredProperty(
                "orders.reporting.db.username");
    }
}
```

Đây là ví dụ lấy **username giả**. Không log `db.password` hoặc dump mọi property trong `Environment`. Với dữ liệu production, một bean chuyên dụng nhận password và tạo datasource thích hợp, không công bố password ra HTTP response.

### 6.1. Thời điểm khởi tạo property source

`@VaultPropertySource` cần có `VaultTemplate` được cấu hình trước để có thể đọc secret trong giai đoạn khởi tạo bean/configuration. Việc thêm property source quá muộn có thể khiến các bean đã được bind bằng `@ConfigurationProperties` hoặc `@Value` không nhận cấu hình như mong muốn.

**Spring Cloud Vault ConfigData** được thiết kế để tham gia bước nạp cấu hình sớm của Spring Boot; **Spring Vault Core `@VaultPropertySource`** cần được lắp vào đúng giai đoạn khởi tạo context. Hai phương pháp cùng mang dữ liệu vào `Environment` nhưng đường tích hợp và thời điểm nạp khác nhau.

## 7. Đặt prefix bằng Java API và kiểm soát thứ tự

Khi cần điều khiển thứ tự `PropertySource` một cách tường minh, Spring Vault Core hỗ trợ `VaultPropertySource` cùng `PropertyTransformers.propertyNamePrefix(...)`. Ví dụ sau giả định đã có đối tượng `ConfigurableEnvironment environment` và `VaultOperations vaultOperations` trong giai đoạn dựng cấu hình:

```java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MutablePropertySources;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.env.VaultPropertySource;
import org.springframework.vault.core.util.PropertyTransformers;

public final class VaultSourceInstaller {

    private VaultSourceInstaller() {
    }

    public static void install(
            ConfigurableEnvironment environment,
            VaultOperations vault) {

        VaultPropertySource primary = new VaultPropertySource(
                "vault-orders-primary",
                vault,
                "kv-demo/orders/primary",
                PropertyTransformers.propertyNamePrefix(
                        "orders.primary."));

        VaultPropertySource reporting = new VaultPropertySource(
                "vault-orders-reporting",
                vault,
                "kv-demo/orders/reporting",
                PropertyTransformers.propertyNamePrefix(
                        "orders.reporting."));

        MutablePropertySources sources = environment.getPropertySources();
        sources.addFirst(primary);
        sources.addAfter("vault-orders-primary", reporting);
    }
}
```

**Ý nghĩa:** `addFirst(primary)` đặt primary ở đầu chuỗi tra cứu hiện tại; `addAfter(..., reporting)` đặt reporting ngay sau primary. Trong ví dụ có namespace riêng, thứ tự không làm hai username đè lên nhau. Việc quản lý precedence vẫn quan trọng nếu các nguồn chứa các tên khóa **cố ý trùng nhau** hoặc có các override từ nguồn khác.

Không gọi `install` tùy tiện sau khi toàn bộ ứng dụng đã bind xong cấu hình; cần đăng ký trước thời điểm khởi tạo bean phụ thuộc. Nếu chỉ muốn rõ namespace mà không cần tự kiểm soát precedence, annotation/ConfigData ở các mục trước thường dễ duy trì hơn.

### 7.1. Minh họa precedence bằng Spring thuần

```java
import java.util.Map;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.StandardEnvironment;

StandardEnvironment env = new StandardEnvironment();

env.getPropertySources().addFirst(
        new MapPropertySource("primary",
                Map.of("db.username", "primary_user")));

env.getPropertySources().addFirst(
        new MapPropertySource("reporting",
                Map.of("db.username", "report_user")));

// reporting đứng trước primary sau hai lần addFirst:
String effective = env.getProperty("db.username");
// effective = "report_user"
```

Đây là hành vi của **Spring `Environment`**, không phải một quy tắc đặc biệt của Vault. Thay `db.username` bằng hai tên `orders.primary.db.username` và `orders.reporting.db.username` loại bỏ sự phụ thuộc vào thứ tự tra cứu cho hai giá trị này.

## 8. Bind cấu hình đã được prefix vào ứng dụng

### 8.1. Dùng placeholder

```yaml
# application.yml: minh họa tham chiếu, không đặt giá trị secret thật.
orders:
  connection-labels:
    primary-user: "${orders.primary.db.username}"
    reporting-user: "${orders.reporting.db.username}"
```

Để lấy giá trị trực tiếp từ Environment:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class AccountNames {

    public AccountNames(
            @Value("${orders.primary.db.username}") String primary,
            @Value("${orders.reporting.db.username}") String reporting) {
        // Dùng hai username trong cấu hình datasource phù hợp.
    }
}
```

Đường dẫn trong placeholder phải khớp **tên thuộc tính sau prefix**. Nếu ứng dụng vẫn tham chiếu `${db.username}`, giá trị có thể thiếu hoặc đến từ một `PropertySource` không liên quan.

### 8.2. Dùng `@ConfigurationProperties`

Với Spring Boot, nên gom các trường cùng namespace bằng cấu hình có kiểu:

```java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "orders.primary.db")
public record PrimaryDbSettings(
        String username,
        String password) {
}
```

Để binder tạo bean, cần đăng ký bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties(PrimaryDbSettings.class)` theo cấu hình Spring Boot của dự án. Có thể tạo type khác cho `orders.reporting.db` hoặc dùng hai cấu hình riêng với validation phù hợp.

Không xuất `record.toString()` khi đối tượng chứa password, vì Java record mặc định có thể đưa giá trị field ra log. Trong production, lưu password trong phạm vi bean cần thiết, tránh thông báo lỗi/bộ quan sát có thể tiết lộ credential.

**Prefix không phải cơ chế bảo mật:** chỉ tách không gian tên ở tầng Spring. Vault token vẫn cần policy `read` cho đúng secret, và không nên để các giá trị nhạy cảm lộ qua `/actuator/env`, lỗi binding, debug dump hoặc CI artifact.

## 9. Tránh xung đột ở nhiều secret backend

Không phải mọi secret engine được nạp vào Spring đều dùng cơ chế prefix giống KV. Với **Spring Cloud Vault Database**, người dùng có thể cấu hình tên property đích của credential động bằng `username-property` và `password-property`. Khi có hai database backend, cần chọn các **tên thuộc tính đích khác nhau**.

Ví dụ khái niệm:

```yaml
spring:
  cloud:
    vault:
      databases:
        primary:
          enabled: true
          backend: database
          role: primary-readonly
          username-property: orders.primary.db.username
          password-property: orders.primary.db.password
        reporting:
          enabled: true
          backend: reporting-db
          role: report-readonly
          username-property: orders.reporting.db.username
          password-property: orders.reporting.db.password
```

Cấu hình phụ thuộc phiên bản Spring Cloud Vault và các mount/role được cấp trong môi trường. Các tên `orders.primary.db.username` và `orders.reporting.db.username` là **địa chỉ thuộc tính trong Spring**, còn `database`/`reporting-db` là mount và `primary-readonly`/`report-readonly` là tên role của backend database.

Với backend AWS hoặc các nguồn tạo credentials khác, có thể tồn tại các tùy chọn riêng để chọn tên property đích. Không giả định mọi backend đều tự hiểu `?prefix=` trên cấu hình mặc định; đó là cú pháp được tài liệu **ConfigData contextual location** hỗ trợ. Kiểm tra đúng extension/phiên bản Spring Cloud Vault trước khi áp dụng.

## 10. Các lỗi và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| `db.username` chỉ hiện một trong hai giá trị Vault | Hai property source có khóa trùng; một nguồn che khuất nguồn kia | Dùng namespace riêng hoặc chủ động thiết kế precedence |
| Nhận `orders.primarydb.username` | Prefix thiếu dấu chấm cuối | Đổi `prefix=orders.primary.` hoặc `propertyNamePrefix="orders.primary."` |
| Placeholder `${orders.reporting.db.username}` không resolve | Sai path, sai prefix, secret không có khóa đó hoặc chưa nạp property source | Kiểm tra đường dẫn logic, tên khóa thực và thứ tự nạp |
| KV v2 trả 404 khi dùng `kv-demo/data/orders/primary` làm contextual path | Đã thêm `data/` vào đường dẫn logic của integration | Dùng `kv-demo/orders/primary`; thư viện xử lý KV v2 HTTP API |
| Vault trả 403 khi ứng dụng startup | Token thiếu `read` trên path KV hoặc truy vấn mount cần quyền phù hợp | Kiểm tra auth, ACL, KV mount discovery và đúng namespace |
| Đã thêm prefix nhưng bean vẫn có giá trị cũ | Bean đã bind trước khi property source xuất hiện hoặc đang cache cấu hình | Nạp property source ở giai đoạn bootstrap phù hợp; kiểm tra lifecycle |
| Prefix khác nhau nhưng vẫn thấy tên trùng | Dùng đồng thời default `vault://` không prefix, hoặc có nhiều nguồn công bố cùng namespace | Kiểm kê toàn bộ property sources và import locations |
| Môi trường test khác production | Active profiles, env vars, command-line hoặc import order khác | Test với chính profile/import/priority của môi trường đích |
| Username đúng nhưng password bị lộ | Log cả `Environment`/config bean hoặc bật endpoint quan sát không kiểm soát | Ẩn/giới hạn logs và Actuator, phân quyền truy cập |
| Thay secret Vault nhưng app vẫn đọc giá trị cũ | ConfigData thường được nạp lúc khởi động; thiếu cơ chế refresh/rotation | Kiểm tra cơ chế cập nhật được hỗ trợ, tạo lại hoặc refresh phù hợp |

Lưu ý: **thứ tự ưu tiên không tự bảo đảm bảo mật**. Environment variables hay command-line args có thể ghi đè một tên thuộc tính Vault tùy quy tắc Spring Boot và cấu hình thực tế. Nếu một property cần có nguồn gốc bắt buộc, hãy xác minh provenance và chính sách override, không chỉ tin rằng “có Vault là luôn thắng”.

## 11. Kiểm thử hợp lệ mà không in secret

Kiểm thử cần tách hai mục tiêu: **hành vi Spring Environment với tên khóa** và **khả năng nạp dữ liệu thật từ Vault**.

### 11.1. Unit test cho shadowing

Ví dụ JUnit 5 kiểm tra hai nguồn trùng khóa:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.StandardEnvironment;

class PropertySourceCollisionTest {

    @Test
    void firstPropertySourceShadowsSameNamedKey() {
        StandardEnvironment env = new StandardEnvironment();
        env.getPropertySources().addFirst(
                new MapPropertySource("primary",
                        Map.of("db.username", "primary_user")));
        env.getPropertySources().addFirst(
                new MapPropertySource("reporting",
                        Map.of("db.username", "report_user")));

        assertEquals("report_user", env.getProperty("db.username"));
    }

    @Test
    void uniquePrefixesKeepBothValues() {
        StandardEnvironment env = new StandardEnvironment();
        env.getPropertySources().addFirst(
                new MapPropertySource("primary",
                        Map.of("orders.primary.db.username", "primary_user")));
        env.getPropertySources().addFirst(
                new MapPropertySource("reporting",
                        Map.of("orders.reporting.db.username", "report_user")));

        assertEquals("primary_user",
                env.getProperty("orders.primary.db.username"));
        assertEquals("report_user",
                env.getProperty("orders.reporting.db.username"));
    }
}
```

Hai test chỉ chứng minh **ngữ nghĩa ưu tiên tên khóa** của Spring; chúng chưa chứng minh ConfigData đã lấy secret từ Vault.

### 11.2. Integration test với Vault thử nghiệm

Dùng Vault dev/test riêng, KV v2 mount `kv-demo`, key và policy của mục 4. Với test context Spring Boot có import của mục 5, test có thể kiểm tra:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;

@SpringBootTest
class VaultPrefixIntegrationTest {

    @Autowired
    Environment environment;

    @Test
    void loadsTwoDistinctVaultContexts() {
        assertEquals("primary_user",
                environment.getProperty("orders.primary.db.username"));
        assertEquals("report_user",
                environment.getProperty("orders.reporting.db.username"));
    }
}
```

Test trên yêu cầu Spring context đã được cấu hình Vault endpoint/TLS/workload auth phù hợp và hai key lab tồn tại. Tránh test giá trị password thật bằng cách in giá trị trong assertion; nếu cần kiểm tra sự có mặt, chỉ xác minh property được bind và không rỗng trong kênh test an toàn.

Ma trận nghiệm thu hữu ích:

| Case | Thao tác | Kết quả mong đợi |
|---|---|---|
| P1 | Hai context cùng có `db.username`, không prefix | Một giá trị che khuất giá trị kia theo precedence |
| P2 | Hai prefix khác nhau và đều có dấu chấm | Hai thuộc tính tồn tại độc lập |
| P3 | Bỏ dấu chấm cuối prefix | Tên thuộc tính bị nối liền bất ngờ; test phát hiện |
| P4 | Hai context cùng prefix và cùng khóa | Shadowing vẫn xảy ra |
| P5 | KV v2 path được nạp đúng | Đọc hai context thành công qua tên logic không chứa `data/` |
| P6 | Token thiếu quyền `read` với reporting | Nguồn đó không nạp được; không bỏ qua lỗi quyền |
| P7 | Thêm `vault://` mặc định bên cạnh contextual imports | Kiểm tra có xuất hiện khóa gốc chưa prefix/đụng tên không |
| P8 | Bind `@ConfigurationProperties` cho cả hai prefix | Giá trị của từng datasource đúng, không trộn credential |
| P9 | Thay đổi active profile/precedence | Không có trộn username/password giữa hai nguồn |
| P10 | Bật logs/Actuator trong test | Không lộ password, token, SecretID hoặc response Vault |

Với ứng dụng nhiều môi trường, nên chạy test riêng cho các profile `dev`/`test`/`prod` hoặc ít nhất kiểm chứng danh sách `PropertySource` của từng kiểu triển khai bằng **tên nguồn**. Không cần in giá trị bí mật để kiểm tra thứ tự nguồn.

## 12. Quy tắc thiết kế namespace lâu dài

Một quy ước dễ bảo trì nên có các đặc tính:

- **Nhất quán:** dùng cấu trúc như `<ứng-dụng>.<mục-đích>.<loại-thuộc-tính>.`, ví dụ `orders.primary.db.` và `orders.reporting.db.`.
- **Ổn định:** không thay prefix tùy từng lần deploy, vì code bind và cấu hình người dùng phụ thuộc tên này.
- **Phân quyền rõ:** mỗi context có path KV v2 và policy read riêng. Prefix tên khóa trong Spring không thay thế ACL.
- **Không trùng giữa các nguồn cần độc lập:** nếu hai datasource phải sống đồng thời, không công bố cả hai vào `spring.datasource.username`.
- **Có kiểm thử:** xác minh kết quả sau khi nạp với profile thực tế, nhất là trong thời điểm migration từ `vault://` mặc định sang explicit imports.
- **Kiểm soát override:** dùng precedence rõ ràng cho những cấu hình muốn ghi đè, thay vì dựa vào trùng khóa ngẫu nhiên.
- **Bảo vệ giá trị:** credential có thể xuất hiện trong `Environment` và property binding; hạn chế endpoint vận hành và log hiển thị cấu hình.

Một trường hợp đặc biệt là **cố ý override**: chẳng hạn shared defaults có `feature.timeout` còn environment-specific context cũng có `feature.timeout`. Khi đó có thể dùng cùng tên khóa **nếu precedence được thiết kế và kiểm thử rõ ràng**. Prefix giải quyết nhu cầu **giữ đồng thời nhiều giá trị**, không bắt buộc trong mọi trường hợp override có chủ đích.

## 13. Tài liệu đối chiếu và câu hỏi tự kiểm tra

Tài liệu kỹ thuật chính thức:

- [Spring Cloud Vault – ConfigData API](https://docs.spring.io/spring-cloud-vault/reference/config-data.html)
- [Spring Cloud Vault – Secret Backends (KV, Database)](https://docs.spring.io/spring-cloud-vault/reference/secret-backends.html)
- [Spring Vault – Property Sources](https://docs.spring.io/spring-vault/reference/vault/propertysource.html)
- [Spring Vault – `@VaultPropertySource` API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/annotation/VaultPropertySource.html)
- [Spring Vault – `PropertyTransformers` API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/util/PropertyTransformers.html)

**Câu hỏi 1:** Hai key Vault đều có tên `db.username`. Nếu nạp cùng lúc mà không thêm prefix, Spring có trả cả hai qua `getProperty("db.username")` không?

**Trả lời:** Không. Spring trả giá trị theo `PropertySource` có precedence cao nhất chứa tên đó; nguồn còn lại bị che khuất đối với lần tra cứu tên ấy.

**Câu hỏi 2:** Khi import `vault://kv-demo/orders/primary?prefix=orders.primary`, khóa `db.password` được công bố với tên nào?

**Trả lời:** `orders.primarydb.password`, vì prefix được nối **nguyên văn**. Để có `orders.primary.db.password` phải dùng `prefix=orders.primary.`.

**Câu hỏi 3:** Thay `spring.cloud.vault.kv.backend=kv-demo` có tự chuyển mọi khóa thành `kv-demo.db.username` không?

**Trả lời:** Không. `backend` chọn KV mount/path, không tự thêm namespace cho tên thuộc tính.

**Câu hỏi 4:** Vì sao integration `@VaultPropertySource("kv-demo/data/orders/primary")` dễ gây lỗi với KV v2?

**Trả lời:** Annotation cần đường dẫn logic `kv-demo/orders/primary`; thành phần REST `data/` do Spring Vault xử lý khi truy cập engine KV v2.

**Câu hỏi 5:** Có nên in `Environment` để kiểm tra hai password đã được bind không?

**Trả lời:** Không. Chỉ kiểm tra tên nguồn/khóa, sự tồn tại hoặc các thuộc tính kiểm thử không nhạy cảm trong môi trường cô lập.

**Điểm cốt lõi:** trong Spring Vault, **prefix là một công cụ đặt tên khi dữ liệu được đưa vào Spring `Environment`**. Dùng `?prefix=...` cho Spring Cloud Vault ConfigData hoặc `propertyNamePrefix` cho Spring Vault Core, thêm dấu chấm cuối khi cần cấu trúc dot-delimited, kiểm tra thứ tự `PropertySource` và tiếp tục áp dụng ACL/TLS bảo vệ dữ liệu như bình thường.

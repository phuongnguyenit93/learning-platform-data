# @ConditionalOnProperty và tác động của matchIfMissing

Trong Spring Boot và Spring Cloud, nhiều bean chỉ nên được tạo khi một tính năng được bật bằng cấu hình. Ví dụ, ứng dụng chỉ tạo cache khi `catalog.cache.enabled=true`, chỉ khởi tạo client tích hợp hệ thống ngoài khi có endpoint phù hợp, hoặc chỉ bật adapter theo môi trường triển khai. Annotation **`@ConditionalOnProperty`** cho phép điều kiện hóa configuration và bean dựa trên giá trị trong `Environment`.

Thuộc tính **`matchIfMissing`** quyết định điều gì xảy ra khi key được kiểm tra không tồn tại. Mặc định, key bị thiếu làm điều kiện không khớp. Đặt `matchIfMissing=true` khiến điều kiện có thể khớp ngay cả khi không có key, nhưng kết quả còn phụ thuộc `havingValue` và các property name khác trong annotation. Chọn sai giá trị này có thể vô tình bật tính năng, tắt bean hoặc thay đổi hành vi mặc định khi nâng cấp ứng dụng.

Bài học thuộc chương **Tùy biến tự động cấu hình** của module `SPRING_CLOUD_CORE`. Nội dung giải thích cách `@ConditionalOnProperty` kiểm tra key và value, vai trò của `havingValue`, tác động riêng của `matchIfMissing`, cách dùng ở cấp configuration/bean, tương tác với property source và cách kiểm thử trường hợp thiếu cấu hình.

## 1. Vì sao cần điều kiện hóa cấu hình?

Giả sử ứng dụng có tính năng cache catalog. Trong môi trường local, nhóm phát triển muốn tắt cache để dễ quan sát dữ liệu; production có thể bật cache để giảm tải database.

Nếu chỉ kiểm tra cờ trong từng method, bean cache vẫn phải tồn tại và được khởi tạo:

```java
@Service
public class CatalogService {
    private final CatalogCache cache;
    private final Environment environment;

    public CatalogService(
            CatalogCache cache,
            Environment environment) {
        this.cache = cache;
        this.environment = environment;
    }

    public CatalogItem find(String id) {
        if (environment.getProperty(
                "catalog.cache.enabled", Boolean.class, false)) {
            return cache.get(id);
        }
        return loadFromDatabase(id);
    }
}
```

Nếu cache cần kết nối Redis, tạo thread pool hoặc khởi tạo resource tốn kém, ứng dụng vẫn chịu chi phí đó dù tính năng tắt. Một configuration có điều kiện cho phép Spring chỉ đăng ký bean khi điều kiện phù hợp:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "catalog.cache",
        name = "enabled",
        havingValue = "true"
)
public class CatalogCacheConfiguration {

    @Bean
    CatalogCache catalogCache() {
        return new CatalogCache();
    }
}
```

Với cấu hình này, bean `CatalogCache` chỉ được tạo khi property `catalog.cache.enabled` có giá trị phù hợp. Vì `matchIfMissing` mặc định là `false`, nếu key không có trong `Environment`, configuration không khớp và bean không được đăng ký.

## 2. @ConditionalOnProperty kiểm tra điều gì?

`@ConditionalOnProperty` là annotation điều kiện của Spring Boot, nằm trong package `org.springframework.boot.autoconfigure.condition`. Nó có thể được đặt trên class cấu hình hoặc method `@Bean`.

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `prefix` | Tiền tố chung của các property được kiểm tra |
| `name` | Một hoặc nhiều tên property cần kiểm tra sau prefix |
| `havingValue` | Giá trị mà property phải có để điều kiện khớp |
| `matchIfMissing` | Có coi property bị thiếu là khớp hay không |
| `value` | Alias của `name`; thường dùng `name` để rõ nghĩa |

Ví dụ:

```java
@ConditionalOnProperty(
        prefix = "catalog.cache",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
```

Annotation kiểm tra property có tên đầy đủ là `catalog.cache.enabled`. Dùng `prefix` giúp nhóm các key cùng namespace và tránh lặp chuỗi.

Nên khai báo tên property theo dạng kebab-case:

```java
@ConditionalOnProperty(
        prefix = "catalog.cache",
        name = "refresh-after-write",
        havingValue = "true"
)
```

Property tương ứng:

```yaml
catalog:
  cache:
    refresh-after-write: true
```

Dùng tên canonical nhất quán giúp tránh khác biệt giữa YAML, properties, environment variable và relaxed binding.

### 2.1. Condition đọc giá trị hiệu lực trong Environment

Giá trị có thể đến từ `application.yml`, profile-specific config, biến môi trường, system property, command line, Config Server hoặc nguồn khác. Nếu nhiều nguồn khai báo cùng key, thứ tự ưu tiên của Spring Boot quyết định giá trị mà condition nhìn thấy.

Ví dụ Config Server đặt `true` nhưng biến môi trường của container đặt `false`, condition có thể thấy `false` theo precedence đang áp dụng. Khi condition không khớp như mong đợi, hãy kiểm tra giá trị hiệu lực trong `Environment`, không chỉ xem một file YAML.

## 3. Vai trò của havingValue

`havingValue` xác định giá trị mà property phải có để điều kiện khớp. Đây là cách rõ ràng nhất khi property biểu diễn boolean hoặc một mode cụ thể.

### 3.1. Không khai báo havingValue

Nếu không khai báo `havingValue`, Spring Boot áp dụng quy tắc mặc định: property phải tồn tại và giá trị của nó không được bằng chuỗi `"false"` (so sánh không phân biệt chữ hoa/chữ thường).

Ví dụ:

```java
@ConditionalOnProperty(
        prefix = "catalog.cache",
        name = "enabled"
)
```

| Giá trị `catalog.cache.enabled` | Điều kiện khớp? |
| --- | --- |
| Không tồn tại | Không, trừ khi `matchIfMissing=true` |
| `true` | Có |
| `false` | Không |
| `TRUE` | Có |
| `yes` | Có theo quy tắc mặc định vì khác `"false"` |
| Chuỗi rỗng | Có vì property tồn tại và không bằng `"false"` |

Đây là điểm dễ gây bất ngờ: nếu ý định là chỉ bật khi giá trị boolean thực sự là `true`, không nên bỏ `havingValue`. Giá trị sai chính tả như `treu` hoặc `enabled` cũng có thể được xem là khớp theo quy tắc mặc định.

### 3.2. Khai báo havingValue = "true"

```java
@ConditionalOnProperty(
        prefix = "catalog.cache",
        name = "enabled",
        havingValue = "true"
)
```

Điều kiện chỉ khớp khi property có giá trị `true` theo phép so sánh của condition. Các giá trị `false`, `yes`, `on`, chuỗi rỗng hoặc giá trị không hợp lệ không khớp.

Đây thường là lựa chọn dễ hiểu nhất cho feature flag dạng boolean:

```yaml
catalog:
  cache:
    enabled: true
```

### 3.3. Khai báo havingValue = "false"

Có thể tạo configuration chỉ hoạt động khi tính năng bị tắt rõ ràng:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "catalog.cache",
        name = "enabled",
        havingValue = "false"
)
public class CatalogCacheDisabledConfiguration {
    // Các bean dành riêng cho chế độ cache bị tắt.
}
```

Nếu key bị thiếu, condition này không khớp khi `matchIfMissing` giữ mặc định `false`. Muốn coi thiếu key tương đương với false, phải chủ động đặt `matchIfMissing=true`.

### 3.4. havingValue không phải parser cho mọi kiểu dữ liệu

`@ConditionalOnProperty` so khớp giá trị property theo tên và chuỗi được yêu cầu; nó không thay thế validation cho toàn bộ cấu hình. Với mode có nhiều lựa chọn như `simple`, `redis`, `caffeine`, hãy đặt `havingValue` tương ứng hoặc viết condition riêng nếu logic phức tạp.

Ví dụ chọn Redis:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "catalog.cache",
        name = "type",
        havingValue = "redis"
)
public class RedisCatalogCacheConfiguration {
    // Redis-backed cache beans.
}
```

Nếu `catalog.cache.type=redsi` do lỗi chính tả, configuration không khớp. Ứng dụng nên có validation hoặc cấu hình fallback rõ ràng để lỗi được phát hiện sớm.

## 4. matchIfMissing quyết định hành vi mặc định

`matchIfMissing` có kiểu boolean và mặc định là `false`.

- `matchIfMissing=false`: property không tồn tại thì condition không khớp.
- `matchIfMissing=true`: property không tồn tại thì condition được coi là khớp, với điều kiện các property khác trong annotation cũng thỏa mãn.

Đây là chính sách cho trường hợp **không có key**, không phải chính sách ghi đè một giá trị đã được khai báo.

### 4.1. matchIfMissing=false: mặc định không bật

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "catalog.cache",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
public class CatalogCacheConfiguration {

    @Bean
    CatalogCache catalogCache() {
        return new CatalogCache();
    }
}
```

| Property | Kết quả |
| --- | --- |
| Không có key | Không tạo `CatalogCache` |
| `enabled=false` | Không tạo `CatalogCache` |
| `enabled=true` | Tạo `CatalogCache` |

Đây là kiểu **opt-in**: tính năng chỉ bật khi cấu hình ghi rõ `true`. Nó phù hợp với tính năng mới, tích hợp ngoài hoặc resource tốn kém mà ứng dụng không nên tự bật khi thiếu cấu hình.

### 4.2. matchIfMissing=true: mặc định khớp khi thiếu key

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "catalog.cache",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
public class CatalogCacheConfiguration {

    @Bean
    CatalogCache catalogCache() {
        return new CatalogCache();
    }
}
```

| Property | Kết quả |
| --- | --- |
| Không có key | Tạo `CatalogCache` |
| `enabled=false` | Không tạo `CatalogCache` |
| `enabled=true` | Tạo `CatalogCache` |

Đây là kiểu **default-on, opt-out**: khi không có cấu hình, tính năng được bật; người vận hành phải đặt `false` để tắt. Nó phù hợp khi hành vi mặc định cần được duy trì cho ứng dụng cũ hoặc tính năng được coi là mặc định của module.

Tuy nhiên, default-on có thể tạo resource ngoài ý muốn khi module được thêm vào một ứng dụng chưa từng khai báo property. Chỉ dùng khi đây là quyết định tương thích có chủ đích.

### 4.3. matchIfMissing=true không có nghĩa luôn khớp

Với `havingValue="true"`:

- Thiếu key: khớp vì `matchIfMissing=true`.
- Key bằng `true`: khớp.
- Key bằng `false`: không khớp.
- Key có giá trị khác: không khớp.

`matchIfMissing` chỉ xử lý nhánh không tìm thấy property. Khi property tồn tại, `havingValue` vẫn được áp dụng.

### 4.4. Nếu bỏ havingValue, tác động sẽ khác

Ví dụ:

```java
@ConditionalOnProperty(
        prefix = "catalog.cache",
        name = "enabled",
        matchIfMissing = true
)
```

| Property | Kết quả |
| --- | --- |
| Không có key | Khớp |
| `enabled=false` | Không khớp |
| `enabled=true` | Khớp |
| `enabled=yes` | Khớp |
| Chuỗi rỗng | Khớp |

Nếu property là boolean, cách viết này thường kém rõ ràng hơn `havingValue="true"`. Hãy nêu rõ giá trị cần có để tránh vô tình bật tính năng do một giá trị không hợp lệ.

## 5. Ma trận kết hợp havingValue và matchIfMissing

Giả sử chỉ kiểm tra một property `catalog.cache.enabled`:

| `havingValue` | `matchIfMissing` | Key thiếu | Giá trị `true` | Giá trị `false` | Giá trị `other` |
| --- | --- | --- | --- | --- | --- |
| Không khai báo | `false` | Không khớp | Khớp | Không khớp | Khớp |
| Không khai báo | `true` | Khớp | Khớp | Không khớp | Khớp |
| `"true"` | `false` | Không khớp | Khớp | Không khớp | Không khớp |
| `"true"` | `true` | Khớp | Khớp | Không khớp | Không khớp |
| `"false"` | `false` | Không khớp | Không khớp | Khớp | Không khớp |
| `"false"` | `true` | Khớp | Không khớp | Khớp | Không khớp |

Hãy xác định trước trạng thái mong muốn khi key thiếu, khi key là true/false và khi người vận hành nhập giá trị không hợp lệ.

## 6. Nhiều property trong cùng một annotation

`name` có thể chứa nhiều property. Khi khai báo nhiều tên, **tất cả** các property phải đáp ứng điều kiện để annotation khớp.

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "catalog",
        name = {"cache.enabled", "cache.remote"},
        havingValue = "true"
)
public class RemoteCatalogCacheConfiguration {
    // Chỉ bật khi cả hai property đều là true.
}
```

Cấu hình tương ứng:

```yaml
catalog:
  cache:
    enabled: true
    remote: true
```

Nếu `catalog.cache.enabled=true` nhưng `catalog.cache.remote=false`, configuration không khớp. Nếu một trong hai key bị thiếu, kết quả phụ thuộc `matchIfMissing`. Với `matchIfMissing=true`, từng key bị thiếu được xử lý theo chính sách đó; các key có mặt vẫn phải thỏa `havingValue`.

Không nên hiểu danh sách `name` là điều kiện OR. Nếu logic là “A và B, hoặc C và không D”, hãy tách configuration hoặc viết một `Condition` tùy biến có tên rõ ràng.

## 7. Dùng ở cấp class và cấp bean

### 7.1. Đặt trên class cấu hình

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "catalog.search",
        name = "enabled",
        havingValue = "true"
)
public class CatalogSearchConfiguration {

    @Bean
    CatalogSearchClient catalogSearchClient() {
        return new CatalogSearchClient();
    }

    @Bean
    CatalogSearchHealthIndicator catalogSearchHealthIndicator(
            CatalogSearchClient client) {
        return new CatalogSearchHealthIndicator(client);
    }
}
```

Khi điều kiện ở class không khớp, cấu hình đó không được áp dụng; các bean method trong class không được đăng ký từ configuration này. Đây là lựa chọn phù hợp khi nhiều bean tạo thành một tính năng cần bật/tắt cùng nhau.

### 7.2. Đặt trên method @Bean

```java
@Configuration(proxyBeanMethods = false)
public class CatalogConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "catalog.cache",
            name = "enabled",
            havingValue = "true"
    )
    CatalogCache catalogCache() {
        return new CatalogCache();
    }
}
```

Điều kiện chỉ áp dụng cho bean được khai báo bởi method đó. Các bean khác trong class vẫn có thể được đăng ký.

Dùng method-level condition khi chỉ một implementation hoặc adapter tùy chọn phụ thuộc property. Nếu nhiều bean phải cùng xuất hiện, đặt điều kiện ở class thường dễ đọc và tránh lặp annotation.

### 7.3. Kết hợp với các condition khác

Có thể kết hợp `@ConditionalOnProperty` với điều kiện classpath hoặc bean:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "com.example.redis.RedisClient")
@ConditionalOnProperty(
        prefix = "catalog.cache",
        name = "type",
        havingValue = "redis"
)
public class RedisCatalogCacheConfiguration {
    // Chỉ bật khi thư viện Redis có mặt và type=redis.
}
```

Điều này tránh tạo cấu hình Redis khi thư viện không có trong classpath. Với auto-configuration, cần xem xét thứ tự và điều kiện của các cấu hình liên quan để không tạo hai bean cạnh tranh cùng lúc.

## 8. Property default trong @ConfigurationProperties

Default value trong object `@ConfigurationProperties` không nhất thiết tương đương với một property có mặt trong `Environment`.

Ví dụ:

```java
@ConfigurationProperties(prefix = "catalog.cache")
public class CatalogCacheProperties {

    private boolean enabled = true;

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }
}
```

Nếu không có `catalog.cache.enabled` trong property sources, object được bind có thể giữ `enabled=true` do giá trị khởi tạo của field. Nhưng `@ConditionalOnProperty` kiểm tra property trong `Environment`; nó không đọc field default của object để quyết định condition.

Do đó, có thể xảy ra:

- `CatalogCacheProperties.isEnabled()` trả về `true`.
- `@ConditionalOnProperty(prefix="catalog.cache", name="enabled", havingValue="true")` không khớp vì key không tồn tại và `matchIfMissing=false`.

Để tránh hai nguồn định nghĩa default mâu thuẫn, hãy chọn một chiến lược:

1. Khai báo default ở property source mà condition nhìn thấy, nếu muốn condition dựa vào default đó.
2. Dùng `matchIfMissing=true` nếu ý định là key thiếu phải bật configuration.
3. Thiết kế một condition/custom auto-configuration dựa trên cùng một nguồn quyết định nếu logic phức tạp.
4. Viết test xác nhận đồng thời bean condition và giá trị `@ConfigurationProperties`.

Không giả định giá trị khởi tạo Java tự động được ghi ngược vào `Environment`.

## 9. Property source và Spring Cloud Config

Trong ứng dụng Spring Cloud, property có thể đến từ Config Server hoặc các nguồn cấu hình ngoài. `@ConditionalOnProperty` vẫn kiểm tra giá trị hiệu lực trong `Environment`; nó không quan tâm property đến từ YAML local, biến môi trường hay remote Config Server.

Ví dụ remote config:

```yaml
catalog:
  cache:
    enabled: true
```

Nếu Config Client nạp property này trước khi auto-configuration được đánh giá, condition có thể khớp và bean được đăng ký lúc startup.

### 9.1. Property precedence có thể thay đổi kết quả

Giả sử Config Server đặt `true` nhưng môi trường container đặt `CATALOG_CACHE_ENABLED=false`. Giá trị hiệu lực phụ thuộc precedence của các property source trong ứng dụng. Condition sẽ dùng giá trị hiệu lực, nên bean có thể không được tạo dù file remote chứa `true`.

Khi debug, kiểm tra property source nào đang thắng và tránh ghi log toàn bộ cấu hình nếu có secret.

### 9.2. Refresh property không tự đăng ký hoặc gỡ bean

`@ConditionalOnProperty` là điều kiện cấu hình được đánh giá trong quá trình tạo application context. Nó không phải listener theo dõi property liên tục.

Ví dụ ứng dụng khởi động với:

```yaml
catalog:
  cache:
    enabled: false
```

Sau đó Config Server đổi thành `true` và ứng dụng gọi `/actuator/refresh`. Giá trị property có thể được cập nhật trong Environment, nhưng Spring không tự chạy lại toàn bộ quá trình đánh giá configuration class để thêm bean `CatalogCache`.

Tương tự, nếu bean đã được tạo khi property là `true`, refresh property sang `false` không tự xóa bean và hủy resource của nó.

Nếu cần bật/tắt hành vi runtime, hãy thiết kế bean tồn tại ổn định và đọc cấu hình có thể refresh, dùng một state/strategy bean có lifecycle rõ ràng hoặc điều phối việc tạo/hủy resource riêng. Nếu cần thay đổi tập bean trong context, thường phải khởi động lại/rollout instance theo quy trình an toàn.

`@RefreshScope` có thể tạo lại target của bean nằm trong scope đó, nhưng không biến `@ConditionalOnProperty` thành condition động để đăng ký hoặc loại bỏ bean definition.

## 10. Giới hạn khi kiểm tra collection property

`@ConditionalOnProperty` phù hợp với property đơn như boolean, string hoặc mode. Nó không phải lựa chọn đáng tin cậy để kiểm tra sự tồn tại của collection dựa trên indexed key.

Ví dụ:

```yaml
catalog:
  nodes:
    - http://catalog-a:8080
    - http://catalog-b:8080
```

Các key được bind có thể ở dạng:

```text
catalog.nodes[0]
catalog.nodes[1]
```

Một condition kiểm tra `catalog.nodes` không nhất thiết khớp chỉ vì các indexed property tồn tại. Tài liệu Spring Boot cảnh báo `@ConditionalOnProperty` không thể dự đoán đáng tin cậy sự hiện diện của property collection theo cách này.

Nếu cần kiểm tra collection, hãy dùng `@Conditional` với `Condition` tùy biến hoặc bind collection vào một cấu hình rồi xác thực bằng cơ chế phù hợp. Không dựa vào việc một indexed key tình cờ làm `containsProperty` trả kết quả như mong muốn ở một property source cụ thể.

## 11. Thiết kế default-on và default-off an toàn

Chọn `matchIfMissing` theo tác động của tính năng:

| Tính năng | Default thường phù hợp | Lý do |
| --- | --- | --- |
| Adapter tích hợp dịch vụ ngoài có phí | Off (`false`) | Tránh kết nối ngoài khi chưa cấu hình |
| Cache tùy chọn mới | Off hoặc quyết định theo tương thích | Tránh tạo resource ngoài dự kiến |
| Hành vi mặc định đã tồn tại từ phiên bản cũ | Có thể on (`true`) | Giữ tương thích khi người dùng chưa khai báo property mới |
| Telemetry bổ sung tốn tài nguyên | Off (`false`) | Chỉ bật khi có chủ đích |
| Cấu hình an toàn bắt buộc | Không nên chỉ dựa vào `matchIfMissing` | Cần fail-fast/validation rõ ràng |

### 11.1. Opt-in

```java
@ConditionalOnProperty(
        prefix = "catalog.experimental",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
```

Tính năng chỉ bật khi operator khai báo rõ `true`. Đây là lựa chọn tốt cho tính năng thử nghiệm, tích hợp có side effect hoặc resource ngoài.

### 11.2. Opt-out

```java
@ConditionalOnProperty(
        prefix = "catalog.compatibility",
        name = "legacy-mode",
        havingValue = "true",
        matchIfMissing = true
)
```

Chế độ tương thích được bật khi property không có; operator có thể đặt `false` để tắt. Cách này hữu ích khi thêm property mới nhưng muốn giữ hành vi cũ cho ứng dụng chưa cập nhật cấu hình.

Nếu đây chỉ là default chuyển tiếp, cần có kế hoạch loại bỏ nó trong release tương lai. Ghi rõ default trong tài liệu cấu hình để người vận hành biết tính năng đang bật dù không khai báo key.

## 12. Kiểm thử bằng ApplicationContextRunner

Spring Boot cung cấp `ApplicationContextRunner` để kiểm thử auto-configuration và condition trong một context nhỏ, không cần khởi động toàn bộ ứng dụng.

Ví dụ cấu hình:

```java
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "catalog.cache",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
class CatalogCacheAutoConfiguration {

    @Bean
    CatalogCache catalogCache() {
        return new CatalogCache();
    }
}
```

Test:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class CatalogCacheAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withUserConfiguration(
                            CatalogCacheAutoConfiguration.class);

    @Test
    void missingPropertyDoesNotCreateCache() {
        contextRunner.run(context ->
                assertThat(context).doesNotHaveBean(CatalogCache.class));
    }

    @Test
    void trueCreatesCache() {
        contextRunner
                .withPropertyValues("catalog.cache.enabled=true")
                .run(context ->
                        assertThat(context).hasSingleBean(CatalogCache.class));
    }

    @Test
    void falseDoesNotCreateCache() {
        contextRunner
                .withPropertyValues("catalog.cache.enabled=false")
                .run(context ->
                        assertThat(context).doesNotHaveBean(CatalogCache.class));
    }
}
```

`CatalogCache` là class ví dụ của ứng dụng. Test cho thấy ba trạng thái quan trọng: key thiếu, key `true`, key `false`. Nếu đổi `matchIfMissing=true`, test đầu tiên phải đổi expectation để xác nhận bean được tạo khi key thiếu.

### 12.1. Ma trận test cần có

| Trường hợp | Property test | `havingValue` | `matchIfMissing` | Kỳ vọng |
| --- | --- | --- | --- | --- |
| Không khai báo | Không có | `true` | `false` | Không có bean |
| Bật rõ ràng | `true` | `true` | `false` | Có bean |
| Tắt rõ ràng | `false` | `true` | `false` | Không có bean |
| Mặc định bật | Không có | `true` | `true` | Có bean |
| Bật sai giá trị | `yes` | `true` | `false` | Không có bean |
| Mặc định bật nhưng operator tắt | `false` | `true` | `true` | Không có bean |

Nên bổ sung test cho property precedence nếu ứng dụng dùng Config Server, biến môi trường hoặc command line để override cùng một key.

## 13. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Bean không được tạo khi không khai báo property | `matchIfMissing` mặc định là `false` | Kiểm tra key có tồn tại và chọn default có chủ đích |
| Bean được tạo dù value không phải `true` | Không khai báo `havingValue` | Đặt `havingValue="true"` cho boolean flag |
| Bean không được tạo dù YAML có `true` | Property source ưu tiên cao hơn đang đặt `false`, sai prefix/name hoặc profile chưa nạp | Kiểm tra giá trị hiệu lực trong Environment |
| Bean được tạo khi key thiếu ngoài dự kiến | `matchIfMissing=true` | Xem lại default-on/opt-out decision |
| Nhiều property nhưng condition không khớp | Một key trong danh sách thiếu hoặc không thỏa giá trị | Nhớ rằng mọi `name` phải khớp |
| Collection condition không hoạt động | Đang kiểm tra base key trong khi chỉ có indexed properties | Dùng custom `Condition` hoặc validation sau binding |
| `@ConfigurationProperties` có `enabled=true` nhưng bean condition không khớp | Default trong Java object không phải property trong Environment | Đồng bộ default và condition strategy |
| Refresh Config Server nhưng bean không xuất hiện | Condition không được đánh giá lại sau startup | Restart/rollout hoặc thiết kế runtime toggle riêng |
| Tắt property sau refresh nhưng bean vẫn còn | Condition không tự gỡ bean definition runtime | Quản lý lifecycle hoặc restart instance |
| Hai configuration cùng tạo một bean | Condition chồng lấn hoặc thiếu điều kiện loại trừ | Thiết kế các nhánh mutually exclusive và test context |

Trình tự điều tra:

1. Xác nhận property key đầy đủ sau khi ghép `prefix` và `name`.
2. Kiểm tra profile và property source nào cung cấp giá trị.
3. Xác nhận giá trị hiệu lực trong `Environment`.
4. Đọc `havingValue` và `matchIfMissing` thực tế của annotation.
5. Kiểm tra tất cả property names nếu có nhiều key.
6. Kiểm tra điều kiện class-level hay method-level.
7. Xem condition evaluation report khi cần chẩn đoán auto-configuration.
8. Xác nhận ứng dụng đang kiểm tra startup condition hay mong đợi một thay đổi runtime.
9. Viết `ApplicationContextRunner` test tái hiện đúng property values.

Spring Boot Actuator có endpoint `conditions` trong các cấu hình phù hợp để xem điều kiện auto-configuration đã match hay không. Chỉ expose endpoint quản trị này theo chính sách bảo mật của ứng dụng; không mở toàn bộ Actuator chỉ để debug.

## 14. Thực hành: bật cache theo cấu hình

Giả sử module catalog cung cấp cache tùy chọn. Yêu cầu:

- Mặc định cache tắt.
- Chỉ bật khi `catalog.cache.enabled=true`.
- Nếu property thiếu, không tạo bean Redis client.
- Nếu property sai giá trị, không âm thầm bật cache.

Cấu hình:

```yaml
catalog:
  cache:
    enabled: false
    type: redis
    ttl: 5m
```

Auto-configuration:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "catalog.cache",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
public class CatalogCacheAutoConfiguration {

    @Bean
    CatalogCache catalogCache() {
        return new CatalogCache();
    }
}
```

Nếu cache cần Redis library, có thể bổ sung `@ConditionalOnClass` và condition cho `catalog.cache.type=redis`. Khi đó chỉ tạo Redis-specific bean nếu cả thư viện và property phù hợp đều có mặt.

Các bước kiểm tra:

1. Bỏ hẳn `catalog.cache.enabled`: bean không được tạo.
2. Đặt `false`: bean không được tạo.
3. Đặt `true`: bean được tạo.
4. Đặt `yes`: bean không được tạo vì `havingValue="true"`.
5. Đặt một property source ưu tiên cao hơn thành `false`: bean không được tạo dù file khác đặt `true`.
6. Thay đổi property sau startup: xác nhận condition không tự đăng ký/gỡ bean; dùng restart hoặc thiết kế runtime toggle nếu yêu cầu nghiệp vụ cần thay đổi ngay.

### Câu hỏi tự kiểm tra

1. `@ConditionalOnProperty` kiểm tra dữ liệu từ đâu?
2. `matchIfMissing` có giá trị mặc định là gì?
3. Khi không khai báo `havingValue`, giá trị `yes` có thể làm condition khớp không?
4. Vì sao nên đặt `havingValue="true"` cho feature flag boolean?
5. `matchIfMissing=true` có làm condition khớp khi property hiện diện với giá trị `false` không?
6. Nếu khai báo nhiều property trong `name`, cần bao nhiêu property khớp?
7. Condition ở cấp class khác condition trên method `@Bean` thế nào?
8. Vì sao default field trong `@ConfigurationProperties` không tự làm `@ConditionalOnProperty` khớp?
9. Vì sao `@ConditionalOnProperty` không phù hợp để kiểm tra collection indexed property?
10. Khi Config Server refresh một property, Spring có tự đăng ký hoặc gỡ bean theo condition không?
11. Khi nào nên dùng `matchIfMissing=true`?
12. Dùng công cụ nào để kiểm thử các trường hợp property thiếu/true/false?

**Gợi ý đáp án:** (1) Từ `Environment` và property sources hiệu lực; (2) `false`; (3) Có, vì khác chuỗi `false` theo quy tắc mặc định; (4) Để chỉ bật với giá trị rõ ràng là true; (5) Không, `havingValue` vẫn được áp dụng; (6) Tất cả; (7) Class condition áp dụng cho toàn configuration, method condition chỉ áp dụng bean method đó; (8) Field default không phải property trong Environment; (9) Indexed key không bảo đảm base collection key tồn tại; (10) Không, condition được đánh giá khi tạo context; (11) Khi thiếu key phải tương đương bật theo chính sách tương thích đã định; (12) `ApplicationContextRunner`.

## 15. Những nguyên tắc cần nhớ

- `@ConditionalOnProperty` điều kiện hóa configuration hoặc bean theo property trong `Environment`.
- `havingValue` xác định giá trị cần khớp; với boolean flag nên khai báo rõ `havingValue="true"` hoặc `havingValue="false"`.
- Nếu bỏ `havingValue`, property tồn tại và khác chuỗi `false` có thể làm condition khớp, kể cả giá trị không phải boolean hợp lệ.
- `matchIfMissing` mặc định là `false`; key thiếu sẽ không làm condition khớp.
- `matchIfMissing=true` chỉ thay đổi cách xử lý key bị thiếu; nó không bỏ qua `havingValue` khi key có mặt.
- Nhiều property trong `name` là điều kiện AND: tất cả phải đáp ứng.
- Condition ở cấp class áp dụng cho toàn configuration; condition trên `@Bean` chỉ áp dụng bean tương ứng.
- Default trong `@ConfigurationProperties` không tự trở thành property trong `Environment`.
- Không dùng `@ConditionalOnProperty` để kiểm tra collection indexed property; cân nhắc custom `Condition`.
- Property refresh không tự đánh giá lại condition hoặc tự thêm/gỡ bean definition; runtime toggle cần thiết kế lifecycle riêng.
- Kiểm thử key thiếu, true, false, giá trị sai, property precedence và condition report bằng `ApplicationContextRunner`.

Chọn đúng `havingValue` và `matchIfMissing` giúp auto-configuration có hành vi mặc định dễ dự đoán, giữ tương thích khi thêm property mới và tránh vô tình khởi tạo tính năng ngoài ý muốn. Hãy xem trường hợp property bị thiếu là một quyết định thiết kế rõ ràng, sau đó kiểm thử cả giá trị có mặt lẫn không có mặt trước khi phát hành.

## Tài liệu tham khảo

- [Spring Boot Reference — ConditionalOnProperty](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html)
- [Spring Boot API — ConditionalOnProperty](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html)
- [Spring Boot API — ApplicationContextRunner](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html)
- [Spring Cloud Commons Reference](https://docs.spring.io/spring-cloud-commons/reference/)

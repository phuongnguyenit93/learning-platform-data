# Đối chiếu Environment, configprops và giá trị bean đang sử dụng

Khi một thuộc tính cấu hình có giá trị không như mong đợi, chỉ nhìn file YAML hoặc response từ Config Server là chưa đủ. Ứng dụng Spring Boot xử lý cấu hình qua nhiều lớp: `Environment` hợp nhất các `PropertySource`, Binder đưa giá trị vào bean `@ConfigurationProperties`, rồi code nghiệp vụ có thể đọc trực tiếp, sao chép, cache hoặc biến đổi giá trị đó. Ba lớp này có thể lệch nhau sau khi refresh hoặc khi ứng dụng có nhiều nguồn cấu hình.

Spring Boot Actuator cung cấp hai endpoint quan trọng để điều tra: `/actuator/env` cho biết giá trị trong `Environment` và nguồn cung cấp; `/actuator/configprops` cho biết các bean `@ConfigurationProperties` cùng giá trị đã bind và thông tin đầu vào. Giá trị mà bean nghiệp vụ đang sử dụng phải được kiểm tra tại chính bean hoặc qua một phép đo an toàn do ứng dụng cung cấp. Bài này xây dựng quy trình đối chiếu ba lớp đó để tìm ra điểm mà giá trị bị thay đổi hoặc bị giữ cũ.

## 1. Ba lớp cấu hình cần phân biệt

```text
Config Server / file / environment / system property / command line
                         |
                         v
                 Spring Environment
              (PropertySource precedence)
                         |
              Binder / @Value injection
                         |
                         v
             @ConfigurationProperties bean
                         |
             constructor / cache / copy
                         |
                         v
             Bean nghiệp vụ đang chạy
```

| Lớp | Câu hỏi cần trả lời | Công cụ kiểm tra |
|---|---|---|
| `Environment` | Spring phân giải khóa thành giá trị nào và nguồn nào thắng? | `Environment.getProperty(...)`, Actuator `/env` |
| `@ConfigurationProperties` | Giá trị nào đã được bind vào bean cấu hình, với prefix và origin nào? | Actuator `/configprops`, getter của bean cấu hình |
| Bean runtime | Thành phần nghiệp vụ thực sự đang dùng giá trị nào ở thời điểm này? | Getter/phương thức chẩn đoán an toàn, log/metric có kiểm soát, debugger hoặc test |

Ví dụ: Config Server trả `orders.timeout=5s`, nhưng biến môi trường `ORDERS_TIMEOUT=2s` có độ ưu tiên cao hơn. Khi đó `Environment` phân giải `2s`, bean cấu hình được bind thành `Duration.ofSeconds(2)`, và bean nghiệp vụ có thể tiếp tục dùng `5s` nếu nó đã sao chép giá trị trước refresh. Ba con số này trả lời ba câu hỏi khác nhau.

## 2. `Environment` là nơi Spring phân giải thuộc tính

Spring `Environment` chứa danh sách `PropertySource`. Mỗi nguồn có thể cung cấp cùng một khóa, ví dụ:

- Config Data từ `application.yml` và profile-specific file.
- Property source từ Spring Cloud Config Server.
- Biến môi trường của tiến trình.
- Java system properties.
- Tham số dòng lệnh.
- Nguồn cấu hình tùy chỉnh do ứng dụng hoặc thư viện thêm vào.

Khi gọi `environment.getProperty("orders.timeout")`, Spring tìm giá trị theo thứ tự ưu tiên của các property source. Nguồn có ưu tiên cao hơn quyết định giá trị được trả về. `/actuator/env` cho phép xem danh sách nguồn theo thứ tự ưu tiên và nguồn nào cung cấp khóa được truy vấn.

Ví dụ đọc trong Java:

```java
import java.time.Duration;

import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class EnvironmentProbe {

    private final Environment environment;

    public EnvironmentProbe(Environment environment) {
        this.environment = environment;
    }

    public Duration currentTimeout() {
        return environment.getProperty(
                "orders.timeout", Duration.class, Duration.ofSeconds(3));
    }
}
```

`Environment.getProperty` có thể chuyển đổi giá trị sang kiểu yêu cầu qua conversion service. Nếu không tìm thấy khóa, overload có default trả về giá trị dự phòng; overload không có default có thể trả `null`. Vì vậy, khi so sánh với `configprops`, hãy xác định cả kiểu dữ liệu và default đang được áp dụng.

### Thứ tự `PropertySource` và nguồn thắng

Một response `/actuator/env` có dạng khái quát:

```json
{
  "activeProfiles": ["prod"],
  "defaultProfiles": ["default"],
  "propertySources": [
    {
      "name": "commandLineArgs",
      "properties": {
        "orders.timeout": { "value": "750ms" }
      }
    },
    {
      "name": "systemEnvironment",
      "properties": {
        "ORDERS_TIMEOUT": { "value": "2s" }
      }
    },
    {
      "name": "configserver:.../order-service-prod.yml",
      "properties": {
        "orders.timeout": { "value": "5s" }
      }
    }
  ]
}
```

Đây là ví dụ rút gọn để minh họa cấu trúc, không phải response cố định của mọi phiên bản. Tên property source và cách hiển thị biến môi trường có thể khác. Hãy đọc thứ tự thực tế trong response của đúng instance.

Với danh sách được sắp từ ưu tiên cao xuống thấp, phần tử đầu tiên có khóa tương ứng là nguồn thắng. Các nguồn phía sau vẫn có thể xuất hiện và chứa giá trị khác; sự hiện diện của chúng không có nghĩa chúng đang được dùng.

### Lưu ý khi dùng Spring Cloud Config Data và legacy bootstrap

Không áp dụng một thứ tự rút gọn cho mọi kiểu Config Client. Với `spring.config.import=configserver:...`, cấu hình từ xa được nạp như Config Data và các nguồn Spring Boot có ưu tiên cao hơn như biến môi trường, system properties và command-line options có thể ghi đè theo thứ tự hiện hành. Với legacy Config First Bootstrap, remote property source mặc định có ưu tiên cao hơn local property sources và không cho phép local override. Muốn cho phép ghi đè, remote source phải cấp `spring.cloud.config.allow-override=true`; `override-system-properties` và `override-none` tiếp tục quyết định phạm vi override. Vì vậy, hãy dựa vào thứ tự thực tế trong `/actuator/env` thay vì giả định biến môi trường luôn thắng cấu hình từ xa.

## 3. Dùng Actuator `/env` để tìm giá trị và origin

`env` endpoint hiển thị các property source của `ConfigurableEnvironment`. Có thể đọc toàn bộ môi trường:

```bash
curl -sS http://localhost:8080/actuator/env
```

Trong sự cố, nên truy vấn một khóa cụ thể để giảm lượng dữ liệu và tránh vô tình thu thập thông tin không liên quan:

```bash
curl -sS \
  http://localhost:8080/actuator/env/orders.timeout
```

Response của một thuộc tính thường có các phần:

| Trường | Ý nghĩa |
|---|---|
| `activeProfiles` | Các profile đang active trên instance |
| `defaultProfiles` | Các profile mặc định |
| `property.source` | Tên property source đang cung cấp giá trị hiệu lực |
| `property.value` | Giá trị đã phân giải, nếu được phép hiển thị |
| `propertySources` | Các nguồn theo thứ tự ưu tiên có khai báo khóa |
| `propertySources[].name` | Tên của từng nguồn |
| `propertySources[].property.origin` | Vị trí nguồn gốc nếu nguồn cung cấp metadata, ví dụ file và dòng/cột |

`origin` rất hữu ích khi cần tìm file hoặc vị trí khai báo. Với Config Data từ xa, tên nguồn có thể chứa thông tin repository/file; với biến môi trường, origin có thể chỉ tên biến. Property source tùy chỉnh có thể không cung cấp origin. Khi không có origin, vẫn có thể xác định tên nguồn thắng nhưng không nên tự suy đoán file hoặc dòng.

### Phân biệt response Config Server và Environment của client

Config Server có endpoint Environment dạng:

```text
GET /{application}/{profile}/{label}
```

Ví dụ:

```bash
curl -sS https://config.example.com/order-service/prod/main
```

Response này cho biết cấu hình từ xa mà server tổng hợp. Trong khi đó, `/actuator/env/orders.timeout` trên Config Client cho biết giá trị sau khi tất cả nguồn cấu hình phía client cùng tham gia. Nếu Config Server trả `5s` nhưng client phân giải `2s`, hãy tìm property source phía client có độ ưu tiên cao hơn hoặc kiểm tra quy tắc override của cơ chế Config Data/legacy bootstrap mà ứng dụng đang dùng.

Không dùng response Config Server để kết luận trực tiếp giá trị runtime trên client. Hãy truy vấn đúng instance client đang gặp sự cố, đúng profile và đúng thời điểm.

## 4. `configprops` cho biết bean cấu hình đã bind

`/actuator/configprops` cung cấp thông tin về các bean được đăng ký bằng `@ConfigurationProperties`. Nó không phải danh sách tất cả bean Spring và không thay thế `/env`.

Truy vấn tất cả bean cấu hình:

```bash
curl -sS http://localhost:8080/actuator/configprops
```

Có thể lọc theo prefix:

```bash
curl -sS \
  http://localhost:8080/actuator/configprops/orders
```

Response có cấu trúc khái quát:

```json
{
  "contexts": {
    "application": {
      "beans": {
        "orders-com.example.OrderProperties": {
          "prefix": "orders",
          "properties": {
            "timeout": "PT2S",
            "maxAttempts": 4
          },
          "inputs": {
            "timeout": {
              "value": "2s",
              "origin": "System Environment Property \"ORDERS_TIMEOUT\""
            },
            "maxAttempts": {
              "value": "4",
              "origin": "class path resource [application-prod.yml]"
            }
          }
        }
      }
    }
  }
}
```

Tên bean, cách biểu diễn kiểu và origin trong ví dụ chỉ mang tính minh họa. Các trường quan trọng:

- `prefix`: prefix của bean cấu hình.
- `properties`: giá trị hiện có trên bean sau khi bind, đã chuyển sang kiểu Java tương ứng.
- `inputs`: nguồn và giá trị đầu vào đã dùng để bind từng thuộc tính, gồm origin nếu có.
- `contexts`: các application context mà bean được đăng ký.

`inputs` và `properties` có mục đích khác nhau. `inputs` giúp truy ra nguồn cấu hình; `properties` cho biết bean cấu hình đang giữ giá trị nào. Nếu property không có trong `Environment` mà bean dùng default trong code, `inputs` có thể không có origin tương ứng trong khi `properties` vẫn hiển thị giá trị default.

### Vì sao một bean không xuất hiện trong `configprops`?

Kiểm tra các khả năng:

- Lớp không có `@ConfigurationProperties`.
- Lớp có annotation nhưng không được đăng ký qua `@ConfigurationPropertiesScan`, `@EnableConfigurationProperties` hoặc cơ chế tương đương.
- Prefix đang tìm không khớp.
- Bean thuộc application context khác trong context hierarchy.
- Ứng dụng chưa có Actuator hoặc endpoint chưa được expose.

Các field được inject bằng `@Value` vào một `@Component` thông thường không tự xuất hiện như một bean `@ConfigurationProperties`. Muốn quan sát chúng, cần kiểm tra bean trực tiếp hoặc chuyển cấu hình có cấu trúc sang `@ConfigurationProperties` khi phù hợp.

## 5. Ví dụ `@ConfigurationProperties` và bean nghiệp vụ

Giả sử ứng dụng quản lý timeout và số lần retry của đơn hàng. Tạo lớp cấu hình:

```java
package com.example.orders;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "orders")
public class OrderProperties {

    private Duration timeout = Duration.ofSeconds(3);
    private int maxAttempts = 3;

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }

    public int getMaxAttempts() {
        return maxAttempts;
    }

    public void setMaxAttempts(int maxAttempts) {
        this.maxAttempts = maxAttempts;
    }
}
```

Đăng ký bằng scanning:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderServiceApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderServiceApplication.class, args);
    }
}
```

Hoặc đăng ký cụ thể:

```java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(OrderProperties.class)
public class OrderConfiguration {
}
```

Giả sử cấu hình có các nguồn:

```yaml
# application-prod.yml
orders:
  timeout: 5s
  max-attempts: 4
```

```text
ORDERS_TIMEOUT=2s
```

Nếu biến môi trường có ưu tiên cao hơn Config Data trong cấu hình hiện tại, `Environment` trả timeout `2s`; Binder chuyển nó thành `Duration` và bean `OrderProperties` giữ `Duration.ofSeconds(2)`. `maxAttempts` vẫn lấy `4` từ file nếu không có nguồn cao hơn khai báo khóa đó.

## 6. Giá trị bean nghiệp vụ có thể khác bean cấu hình

Một lỗi phổ biến xảy ra khi bean nghiệp vụ sao chép cấu hình trong constructor:

```java
import java.time.Duration;

import org.springframework.stereotype.Service;

@Service
public class OrderExecutor {

    private final Duration timeoutAtCreation;
    private final OrderProperties properties;

    public OrderExecutor(OrderProperties properties) {
        this.properties = properties;
        this.timeoutAtCreation = properties.getTimeout();
    }

    public Duration timeoutFromPropertiesBean() {
        return properties.getTimeout();
    }

    public Duration timeoutActuallyUsed() {
        return timeoutAtCreation;
    }
}
```

`OrderExecutor` là singleton thông thường. `timeoutAtCreation` chỉ được gán một lần khi constructor chạy. Nếu Spring Cloud rebind `OrderProperties` sau một `EnvironmentChangeEvent`, getter `properties.getTimeout()` có thể trả giá trị mới, nhưng `timeoutAtCreation` vẫn là snapshot cũ.

Đây là lý do `/configprops` có thể hiển thị giá trị mới trong khi request nghiệp vụ vẫn dùng timeout cũ. Cần xác định bean nào đang giữ giá trị thực tế, có copy cấu hình vào field, cache, client hoặc pool nào không.

Các kiểu giữ giá trị cũ thường gặp:

- Gán giá trị từ `Environment` hoặc `@Value` vào `final` field trong constructor.
- Copy các field từ `@ConfigurationProperties` sang một object khác khi khởi tạo.
- Tạo HTTP client, executor, connection pool hoặc SDK client từ cấu hình ban đầu.
- Cache kết quả cấu hình trong singleton, static field hoặc cache bên ngoài.
- Tạo object con không được Spring quản lý rồi giữ tham chiếu lâu dài.
- Consumer giữ trực tiếp target của refresh-scoped bean thay vì giữ proxy.

## 7. Đọc giá trị runtime một cách có chủ đích

Actuator `/configprops` chỉ báo cáo các bean `@ConfigurationProperties`. Nó không thể tự suy ra một bean nghiệp vụ đang sử dụng biến local, snapshot hoặc trạng thái nội bộ nào. Để chẩn đoán, hãy cung cấp phép quan sát nhỏ và có kiểm soát trong chính ứng dụng.

Ví dụ một phương thức chẩn đoán chỉ trả về các giá trị không nhạy cảm:

```java
import java.time.Duration;

public record OrderRuntimeSnapshot(
        Duration configuredTimeout,
        Duration timeoutActuallyUsed,
        int configuredMaxAttempts) {
}
```

```java
import org.springframework.stereotype.Service;

@Service
public class OrderDiagnostics {

    private final OrderProperties properties;
    private final OrderExecutor executor;

    public OrderDiagnostics(
            OrderProperties properties,
            OrderExecutor executor) {
        this.properties = properties;
        this.executor = executor;
    }

    public OrderRuntimeSnapshot snapshot() {
        return new OrderRuntimeSnapshot(
                properties.getTimeout(),
                executor.timeoutActuallyUsed(),
                properties.getMaxAttempts());
    }
}
```

Chỉ expose snapshot qua một kênh nội bộ có xác thực và phân quyền, hoặc ghi log có cấu trúc trong lúc điều tra. Không trả password, token, private key, URL có credential hoặc toàn bộ object cấu hình ra endpoint công khai. Nếu không muốn thêm endpoint tùy chỉnh, có thể đặt breakpoint, ghi metric/log tạm thời hoặc kiểm thử bean bằng integration test.

### Không dùng `System.getenv()` để đại diện giá trị Spring đang dùng

`System.getenv("ORDERS_TIMEOUT")` chỉ đọc biến môi trường của tiến trình. Nó không hợp nhất Config Server, file cấu hình, system properties, command line và default. Tương tự, `System.getProperty("orders.timeout")` chỉ đọc Java system property. Để biết giá trị Spring đã phân giải, dùng `Environment`; để biết bean đã bind, dùng getter của `@ConfigurationProperties`; để biết giá trị nghiệp vụ thực dùng, kiểm tra bean nghiệp vụ.

## 8. Đối chiếu ba lớp trong một tình huống thực tế

Giả sử Config Server trả:

```yaml
orders:
  timeout: 5s
  max-attempts: 4
```

Container được khởi chạy với:

```text
ORDERS_TIMEOUT=2s
```

Kết quả quan sát có thể là:

| Nơi kiểm tra | `orders.timeout` | Ý nghĩa |
|---|---:|---|
| Config Server Environment API | `5s` | Giá trị từ xa server trả về |
| Client `/actuator/env/orders.timeout` | `2s` | Biến môi trường thắng trong Environment của client |
| Client `/actuator/configprops` | `PT2S` | `OrderProperties.timeout` đã bind thành Duration |
| `OrderExecutor.timeoutFromPropertiesBean()` | `PT2S` | Đọc trực tiếp bean cấu hình hiện tại |
| `OrderExecutor.timeoutActuallyUsed()` | `PT5S` | Snapshot được sao chép khi constructor chạy trước đó |

Đừng so sánh chuỗi `5s` với `PT5S` rồi kết luận sai khác. Một giá trị là dạng biểu diễn cấu hình; dạng kia là biểu diễn chuẩn ISO-8601 của `Duration`. Hãy so sánh theo kiểu dữ liệu và ý nghĩa tương đương.

## 9. Đối chiếu sau khi refresh

Spring Cloud không mặc định polling Config Server liên tục để phát hiện thay đổi. Ứng dụng cần một cơ chế tạo thay đổi trong `Environment`, ví dụ thao tác refresh được bảo vệ, webhook/Bus hoặc quy trình triển khai.

Khi `EnvironmentChangeEvent` được phát, Spring Cloud xử lý một số thay đổi phổ biến:

- Rebind các bean `@ConfigurationProperties` đủ điều kiện.
- Cập nhật logger level khi các khóa `logging.level.*` thay đổi.
- Các listener tùy chỉnh có thể phản ứng với danh sách khóa thay đổi.

Quy trình đối chiếu sau refresh:

1. Xác nhận nguồn cấu hình mới đã được Config Server nhận và đúng application/profile/label.
2. Kích hoạt refresh theo cơ chế của hệ thống.
3. Truy vấn `/actuator/env/{property}` trên đúng client instance để xác nhận Environment đã đổi.
4. Truy vấn `/actuator/configprops/{prefix}` để xác nhận bean cấu hình đã bind lại.
5. Kiểm tra getter hoặc snapshot của bean nghiệp vụ để xác nhận code đang dùng giá trị mới.
6. Nếu các instance chạy nhiều replica, lặp lại kiểm tra trên từng instance hoặc dùng metric tổng hợp theo instance.

`/actuator/refresh` và Spring Cloud Bus có thể tham gia quy trình này tùy cách ứng dụng nạp cấu hình và phiên bản đang dùng. Một HTTP response thành công từ endpoint refresh không tự chứng minh mọi object trong context đã thay đổi. Cần xác minh từng lớp.

### Mutable `@ConfigurationProperties` và `@RefreshScope`

Mutable JavaBean có getter/setter có thể được rebinder cập nhật tại chỗ. Bean nghiệp vụ đọc getter mỗi lần sử dụng có thể thấy giá trị mới; bean đã sao chép giá trị sang field riêng vẫn có thể giữ snapshot cũ.

Với bean cần tạo lại từ cấu hình mới, `@RefreshScope` đặt bean sau scoped proxy. Khi scope được làm mới, target cũ bị loại khỏi cache và target mới được tạo khi proxy được gọi lần tiếp theo. Consumer cần giữ proxy do Spring inject, không giữ target hoặc snapshot cũ.

Constructor-bound `@ConfigurationProperties` và Java record không được rebinder cập nhật trực tiếp theo cơ chế thông thường. Nếu dùng cấu hình bất biến, có thể tạo lại value object qua provider có vòng đời refresh được kiểm soát hoặc dùng restart khi cần. Với thành phần giữ tài nguyên như connection pool, hãy kiểm tra khả năng tái tạo và đóng tài nguyên trước khi chọn refresh.

## 10. Ma trận chẩn đoán khi ba lớp không khớp

| Quan sát | Nguyên nhân có thể | Bước kiểm tra tiếp theo |
|---|---|---|
| Config Server cũ, client Environment cũ | Commit chưa được fetch, sai label/profile, webhook/refresh chưa chạy | Kiểm tra server response, Git revision và refresh trigger |
| Config Server mới, client Environment cũ | Client chưa refresh, đang gọi nhầm Config Server/label, local import không cập nhật | Kiểm tra log client, request Config Server và property source của client |
| Environment mới, configprops cũ | Bean không được rebind, constructor-bound object, bean chưa đăng ký đúng hoặc refresh event không đến | Kiểm tra bean registration, kiểu binding và log `EnvironmentChangeEvent` |
| Environment mới, configprops mới, bean nghiệp vụ cũ | Bean sao chép giá trị, cache, tạo client/resource lúc startup hoặc giữ target cũ | Kiểm tra constructor, field, cache, dependency lifecycle và proxy |
| configprops không có bean mong muốn | Thiếu `@ConfigurationProperties`, không scan/enable hoặc sai context/prefix | Kiểm tra annotation và registration |
| `inputs` không có origin | Giá trị default trong code, nguồn tùy chỉnh không cung cấp metadata hoặc không có input | Kiểm tra default và implementation của PropertySource |
| Giá trị bị `******` | Actuator sanitization đang hoạt động | Xác minh source/metadata; không tắt sanitization chỉ để xem secret |
| Mỗi replica trả giá trị khác nhau | Config Server replica khác revision, env var khác nhau hoặc Bus chưa tới mọi instance | So sánh instance ID, source, revision và refresh timestamp |
| Environment và bean đúng nhưng hành vi vẫn sai | Code biến đổi giá trị, đơn vị khác nhau, cache hoặc dependency bên ngoài chưa cập nhật | Kiểm tra giá trị sau conversion và thành phần thực thi cuối cùng |

## 11. Cấu hình Actuator để chẩn đoán có kiểm soát

Thêm `spring-boot-starter-actuator` vào ứng dụng nếu chưa có, sau đó chỉ expose các endpoint cần thiết. Ví dụ cho một môi trường chẩn đoán nội bộ:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,env,configprops
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
```

Theo mặc định, Actuator chỉ expose `health` qua HTTP. `env` và `configprops` phải được expose tường minh. Các giá trị nhạy cảm trong hai endpoint được sanitization mặc định thành `******`.

Nếu Spring Security có trên classpath và ứng dụng chưa khai báo `SecurityFilterChain` riêng, Spring Boot tự bảo vệ các actuator endpoint khác `health`. Khi tự khai báo `SecurityFilterChain`, cấu hình tự động này có thể back off; hãy thêm rule riêng cho `/actuator/env/**` và `/actuator/configprops/**`, đồng thời bảo vệ các route Actuator còn lại. Không mở toàn bộ Actuator chỉ để điều tra một thuộc tính.

Nếu có nhu cầu xem giá trị không nhạy cảm cho nhóm vận hành được ủy quyền, có thể dùng `when-authorized` và đặt role rõ ràng:

```yaml
management:
  endpoint:
    env:
      show-values: when-authorized
      roles: CONFIG_DIAGNOSTICS
    configprops:
      show-values: when-authorized
      roles: CONFIG_DIAGNOSTICS
```

Đối với HTTP endpoint, người dùng được coi là authorized khi đã xác thực và có role được khai báo. Nếu không khai báo roles, mặc định bất kỳ người dùng đã xác thực nào cũng có thể được coi là authorized cho chế độ `when-authorized`. Vì vậy, hãy cấu hình role cụ thể và Spring Security policy tương ứng. Custom `SanitizingFunction` vẫn có thể tiếp tục che giá trị.

Các nguyên tắc bảo vệ:

- Chỉ mở endpoint trên management network hoặc cổng quản trị riêng.
- Dùng xác thực, phân quyền và audit log; không dựa vào URL khó đoán.
- Giữ `show-values: never` cho production nếu không có nhu cầu rõ ràng.
- Không đặt `show-values: always` cho `env` hoặc `configprops` trong môi trường dùng secret.
- Không ghi response đầy đủ vào ticket, chat hoặc log công khai.
- Không log Authorization header, password, token, private key hoặc giá trị bí mật.
- Chỉ expose prefix/endpoint cần điều tra nếu phiên bản và cấu hình cho phép giới hạn phạm vi.
- Nếu định nghĩa custom `SecurityFilterChain`, tự bảo vệ toàn bộ endpoint cần thiết vì cấu hình bảo mật Actuator tự động có thể back off.

## 12. Quy trình điều tra chuẩn cho một property

Khi nhận báo cáo “ứng dụng đang dùng cấu hình sai”, thực hiện theo thứ tự:

### Bước 1: Chốt đúng instance và đúng khóa

Ghi lại service name, instance ID/pod, profile, label, thời điểm xảy ra, property key và hành vi thực tế. Đừng so sánh hai replica hoặc hai môi trường khác nhau.

### Bước 2: Xác minh Config Server

Gọi `/{application}/{profile}/{label}` để kiểm tra server có trả đúng property source và revision không. Nếu server đã sai, điều tra repository, profile, label hoặc composite precedence trước.

### Bước 3: Xác minh Environment của client

Gọi `/actuator/env/{property}`. Ghi lại source thắng, origin nếu có, active profile và các nguồn khác cùng khai báo khóa. So sánh với giá trị server trả về để phát hiện local override.

### Bước 4: Xác minh bean cấu hình

Gọi `/actuator/configprops/{prefix}`. Tìm bean đúng tên/prefix, so sánh `properties` với `inputs`, kiểm tra kiểu dữ liệu, default và validation. Nếu bean không xuất hiện, kiểm tra registration.

### Bước 5: Xác minh giá trị nghiệp vụ đang dùng

Kiểm tra getter hoặc snapshot của bean tiêu thụ. Tìm field `final`, constructor copy, `@Value`, cache, static state, SDK client, connection pool và các object không do Spring quản lý.

### Bước 6: Xác minh refresh và hội tụ

Kiểm tra event/refresh log, thời điểm refresh và từng replica. Sau khi giá trị đã đúng, xác nhận hành vi nghiệp vụ bằng request thử hoặc metric an toàn. Nếu dependency không thể refresh, lập kế hoạch restart/rolling deployment.

### Bước 7: Ghi lại kết quả

Một bản ghi điều tra ngắn có thể gồm:

| Trường | Ví dụ |
|---|---|
| Instance | `order-service-7d8c9f6b9-x2k4p` |
| Property | `orders.timeout` |
| Config Server | `5s`, label `main`, commit `abc123` |
| Environment | `2s`, source `systemEnvironment`, origin `ORDERS_TIMEOUT` |
| configprops | `PT2S` trong bean `OrderProperties` |
| Runtime bean | `PT5S` trong `OrderExecutor.timeoutAtCreation` |
| Root cause | Bean nghiệp vụ copy timeout trong constructor trước lần refresh |
| Corrective action | Đọc getter hiện tại hoặc refresh/recreate bean tiêu thụ |

Không đưa giá trị bí mật vào bản ghi. Tên source, origin, hash/ID phiên bản và kết luận đủ để tái lập phần lớn sự cố.

## 13. Các lỗi dễ nhầm khi đọc Actuator

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| `/env` cho biết giá trị bean đang dùng | `/env` chỉ cho biết giá trị trong Environment và nguồn của nó |
| `/configprops` liệt kê mọi bean Spring | Endpoint chỉ báo cáo bean `@ConfigurationProperties` |
| `inputs` và `properties` là cùng một thứ | `inputs` mô tả nguồn/giá trị dùng để bind; `properties` là giá trị trên bean |
| Config Server trả đúng thì client chắc chắn đúng | Client còn có property source và override riêng |
| `configprops` đúng thì mọi bean nghiệp vụ đều đúng | Bean nghiệp vụ có thể đã copy/cache giá trị khác |
| Refresh trả HTTP 200 nghĩa là toàn bộ ứng dụng đã đổi | Cần xác minh Environment, bean cấu hình, target refresh scope và consumer |
| `******` nghĩa là property không có giá trị | Có thể giá trị tồn tại nhưng đã được sanitization |
| Không có origin nghĩa là không có nguồn | PropertySource tùy chỉnh hoặc default có thể không cung cấp origin metadata |
| Đổi `Environment` tự thay `@Value` field | `@Value` đã inject vào singleton không tự được re-inject; cần cơ chế tạo lại phù hợp |
| Mọi replica đều nhận cùng refresh event | Phải kiểm tra Bus delivery và giá trị trên từng instance |

## 14. Checklist vận hành

| Kiểm tra | Điều kiện đạt |
|---|---|
| Instance identity | Đã xác định đúng pod/instance và profile |
| Config Server | Application/profile/label và revision đúng |
| Environment | Khóa có giá trị hiệu lực đúng; biết property source thắng và origin nếu có |
| Local override | Biến môi trường, system property, command line và Config Data đã được đối chiếu |
| configprops | Bean đúng prefix xuất hiện; giá trị typed đã bind đúng |
| Binding defaults | Default, conversion và validation được hiểu rõ |
| Runtime bean | Consumer không giữ snapshot/cached value cũ ngoài ý muốn |
| Refresh mechanism | Event/endpoint thực sự cập nhật Environment trên instance |
| Refresh scope | Consumer giữ proxy và target được tạo lại khi cần |
| Multi-instance | Các replica có cùng revision và refresh timestamp phù hợp |
| Actuator security | Endpoint chỉ expose trong mạng quản trị và có authorization |
| Sanitization | Secret tiếp tục bị che; không bật hiển thị toàn bộ giá trị |
| Evidence | Ghi source/origin/version và root cause mà không ghi secret |

## 15. Nguyên tắc cần ghi nhớ

- `/actuator/env` trả lời Spring đang phân giải khóa thành giá trị nào và property source nào thắng.
- `/actuator/configprops` trả lời bean `@ConfigurationProperties` đang giữ giá trị nào và input/origin nào đã được dùng để bind.
- Giá trị bean nghiệp vụ phải được kiểm tra tại chính thành phần sử dụng; Actuator không tự phát hiện mọi snapshot, cache hoặc giá trị được copy.
- Config Server Environment API và client `/actuator/env` là hai góc nhìn khác nhau; local property source có thể ghi đè cấu hình từ xa.
- So sánh theo kiểu dữ liệu và ý nghĩa, không chỉ theo chuỗi biểu diễn như `5s` và `PT5S`.
- `EnvironmentChangeEvent` có thể rebind `@ConfigurationProperties` và cập nhật logging level; bean giữ snapshot riêng vẫn có thể cũ.
- `@RefreshScope` dùng proxy và tạo lại target khi cần; consumer phải đi qua proxy.
- Actuator chỉ expose `health` qua HTTP theo mặc định; `env` và `configprops` cần được expose rõ ràng.
- Giá trị trong `env` và `configprops` được sanitization mặc định; giữ role, network boundary và audit cho endpoint chẩn đoán.
- Sau refresh, xác minh từng instance và giá trị nghiệp vụ thực tế trước khi kết luận hệ thống đã hội tụ.

Đối chiếu Environment, configprops và giá trị bean đang sử dụng là cách lần theo một thuộc tính từ nguồn cấu hình đến hành vi cuối cùng. `Environment` chỉ ra giá trị thắng, `configprops` cho thấy kết quả binding, còn bean nghiệp vụ cho biết ứng dụng thực sự làm gì với giá trị đó. Khi kiểm tra lần lượt ba lớp trên đúng instance và bảo vệ endpoint Actuator, nhóm có thể tìm ra chính xác nơi cấu hình bị ghi đè, không được bind hoặc bị giữ trong snapshot cũ.

## Tài liệu tham khảo

- [Spring Boot Actuator — Endpoints và sanitization](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot Actuator API — Environment (`env`)](https://docs.spring.io/spring-boot/api/rest/actuator/env.html)
- [Spring Boot Actuator API — Configuration Properties (`configprops`)](https://docs.spring.io/spring-boot/api/rest/actuator/configprops.html)
- [Spring Cloud Commons — Environment Changes và refresh](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
- [Spring Cloud Config — Config Client](https://docs.spring.io/spring-cloud-config/reference/client.html)

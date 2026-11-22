# Sử dụng Environment đầu vào để chọn ứng dụng và profile

Spring Cloud Config Server có thể lấy cấu hình từ Git, hệ thống file, JDBC, Vault hoặc một nguồn do đội phát triển tự xây dựng. Với nguồn tùy biến, máy chủ cần biết **đang được yêu cầu cấu hình cho ứng dụng nào, profile nào và phiên bản cấu hình nào** trước khi truy vấn kho dữ liệu. Hợp đồng `EnvironmentRepository` cung cấp chính ba thông tin này cho phương thức `findOne`.

Bài học thuộc chương **Nguồn cấu hình tùy biến** của module **SPRING_CLOUD_CORE**. Ta sẽ theo dõi một request từ Config Client đến Config Server, dùng `application`, `profile` và `label` để chọn dữ liệu, xây dựng đối tượng `Environment` trả về, rồi kiểm tra cách nhiều profile kết hợp với nhau.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vai trò của `EnvironmentRepository` trong Spring Cloud Config Server.
- Phân biệt `org.springframework.core.env.Environment` với `org.springframework.cloud.config.environment.Environment`.
- Xác định `application`, `profile` và `label` đến từ đâu trong một request cấu hình.
- Viết một repository tùy biến triển khai `findOne(application, profile, label)`.
- Chọn đúng cấu hình theo ứng dụng và nhiều profile, đồng thời giữ thứ tự ưu tiên profile nhất quán.
- Trả về `Environment` có tên, profile, label và `PropertySource` phù hợp.
- Đăng ký repository bằng Spring bean, điều khiển thứ tự khi dùng composite và kiểm tra kết quả qua HTTP.
- Bảo vệ việc tra cứu cấu hình khỏi ứng dụng/profile/label không hợp lệ và tránh truy vấn dữ liệu tùy tiện.

## 2. Environment trong Spring Cloud Config có hai ý nghĩa

Tên `Environment` xuất hiện ở hai package khác nhau. Cần phân biệt rõ để không nhầm đối tượng request với đối tượng kết quả.

| Kiểu | Package | Vai trò |
| --- | --- | --- |
| `Environment` của Spring Framework | `org.springframework.core.env.Environment` | Abstraction của ứng dụng Spring đang chạy, cung cấp active/default profiles và khả năng đọc property từ các `PropertySource`. |
| `Environment` của Spring Cloud Config | `org.springframework.cloud.config.environment.Environment` | Mô hình dữ liệu được Config Server trả về, gồm tên ứng dụng, danh sách profile, label và các property source. |

Trong hợp đồng `EnvironmentRepository`, **đầu vào trực tiếp không phải một object `Environment`**. Đầu vào là ba chuỗi:

~~~java
Environment findOne(String application, String profile, String label);
~~~

Repository dùng các tham số đó để chọn dữ liệu, rồi tạo và trả về `org.springframework.cloud.config.environment.Environment`. Đối tượng `org.springframework.core.env.Environment` của chính Config Server là một khái niệm khác, thường được inject để đọc cấu hình runtime của máy chủ.

## 3. Ba tham số đầu vào chọn cấu hình

Config Server phục vụ cấu hình qua endpoint dạng:

~~~text
/{application}/{profile}/{label}
~~~

Ba thành phần có ý nghĩa riêng:

| Tham số | Ý nghĩa | Giá trị phía client thường dùng |
| --- | --- | --- |
| `application` | Tên ứng dụng cần lấy cấu hình | `spring.application.name` |
| `profile` | Một hoặc nhiều profile được kích hoạt | `spring.profiles.active`, thường là danh sách phân tách bằng dấu phẩy |
| `label` | Nhãn phiên bản của bộ cấu hình trên server | Nhánh, tag, commit Git hoặc version tương ứng của backend |

Ví dụ client:

~~~yaml
spring:
  application:
    name: order-service
  profiles:
    active: dev,mysql
  cloud:
    config:
      label: release-2026.11
~~~

Config Client mặc định dùng `spring.application.name` làm application, các profile đang active làm profile và một label mặc định do cấu hình client/server quyết định. Có thể ghi đè các giá trị này bằng `spring.cloud.config.name`, `spring.cloud.config.profile` và `spring.cloud.config.label`.

Với ví dụ trên, repository nhận được yêu cầu tương đương:

~~~text
application = order-service
profile     = dev,mysql
label       = release-2026.11
~~~

### 3.1. Application chọn phạm vi cấu hình

`application` thường tương ứng với tên dịch vụ. Repository dùng nó để chọn namespace, tenant, thư mục, bảng hoặc kho dữ liệu riêng cho ứng dụng.

Ví dụ:

| Application | Không gian cấu hình |
| --- | --- |
| `order-service` | Timeout xử lý đơn hàng, kết nối database đơn hàng, cờ tính năng checkout |
| `catalog-service` | Cache danh mục, giới hạn tìm kiếm, kết nối search index |
| `payment-service` | Timeout cổng thanh toán, chính sách retry và thông số đối soát |

Không nên coi application do request gửi lên là danh tính đã được xác thực. Config Server cần kiểm tra caller có quyền đọc cấu hình của ứng dụng đó hay không. Nếu không, người gọi có thể thử đổi tên application để đọc nhầm cấu hình của dịch vụ khác.

### 3.2. Profile chọn biến thể môi trường

Profile là tên môi trường hoặc nhóm cấu hình như `dev`, `test`, `staging`, `prod`, `mysql`, `redis`. Một request có thể chứa nhiều profile:

~~~text
/order-service/dev,mysql/release-2026.11
~~~

Spring Cloud Config áp dụng quy tắc profile tương tự Spring Boot: profile active được ưu tiên hơn cấu hình mặc định; khi có nhiều profile, **profile đứng sau có thể ghi đè giá trị của profile đứng trước**. Ví dụ, nếu cả `dev` và `mysql` đều khai báo `spring.datasource.url`, giá trị từ `mysql` có thể thắng trong quy tắc hợp nhất tương ứng.

Repository tùy biến cần giữ đúng thứ tự profile mà request cung cấp khi hợp nhất dữ liệu. Nếu tự sắp xếp profile theo alphabet hoặc dùng một cấu trúc không bảo toàn thứ tự, kết quả có thể khác hành vi mà Config Client mong đợi.

### 3.3. Label chọn phiên bản cấu hình

`label` là nhãn phiên bản ở phía Config Server. Với Git backend, label thường là branch, tag hoặc commit ID. Với nguồn dữ liệu khác, label có thể là mã version, revision hoặc snapshot đã phát hành.

Không nhầm label với profile:

- `prod` trả lời câu hỏi **cấu hình cho môi trường nào**.
- `release-2026.11` trả lời câu hỏi **dùng bộ cấu hình phiên bản nào**.

Nếu label không được truyền, repository cần áp dụng default label đã được quy định. Không nên ngầm dùng một giá trị khác nhau giữa các instance Config Server.

## 4. Luồng request từ Config Client đến EnvironmentRepository

~~~mermaid
sequenceDiagram
    participant C as Config Client
    participant H as Config Server HTTP endpoint
    participant R as EnvironmentRepository
    participant S as Custom configuration store
    C->>H: GET /order-service/dev,mysql/release-2026.11
    H->>R: findOne(application, profile, label)
    R->>R: Validate application/profile/label
    R->>S: Load data for app + label + profiles
    S-->>R: Default and profile-specific properties
    R->>R: Merge profiles in requested order
    R-->>H: Config Environment + PropertySources
    H-->>C: JSON Environment response
~~~

Các bước có thể được mở rộng bằng xác thực, phân quyền, cache, giải mã secret, ghi audit hoặc kết hợp nhiều repository. Nhưng hợp đồng chính vẫn là: **nhận bộ chọn cấu hình, đọc nguồn dữ liệu, trả về một Environment có các PropertySource**.

Config Server không yêu cầu repository phải dùng database cụ thể. Một repository có thể đọc từ bảng SQL, REST API nội bộ, object storage, secret manager hoặc một kho cấu hình tự xây dựng.

## 5. Cấu trúc Environment được trả về

`org.springframework.cloud.config.environment.Environment` là mô hình kết quả. Nó chứa:

- `name`: application được yêu cầu.
- `profiles`: danh sách profile đã xử lý.
- `label`: nhãn phiên bản cấu hình.
- `propertySources`: danh sách nguồn property, mỗi nguồn có tên và map key/value.
- `version` và `state`: metadata tùy chọn do repository/backend cung cấp.

Ví dụ JSON rút gọn:

~~~json
{
  "name": "order-service",
  "profiles": ["dev", "mysql"],
  "label": "release-2026.11",
  "propertySources": [
    {
      "name": "custom:order-service:dev,mysql:release-2026.11",
      "source": {
        "order.timeout": "5s",
        "order.checkout.enabled": "true",
        "spring.datasource.url": "jdbc:postgresql://db-dev/orders"
      }
    }
  ]
}
~~~

Trong ví dụ này, repository đã hợp nhất các giá trị vào một `PropertySource`. Một triển khai khác có thể trả nhiều `PropertySource` riêng để giữ nguồn gốc và thứ tự ưu tiên. Khi trả nhiều nguồn, cần đặt nguồn ưu tiên cao hơn ở vị trí phù hợp theo hợp đồng của Spring Cloud Config.

## 6. Viết custom EnvironmentRepository

Giả sử tổ chức lưu cấu hình trong một catalog nội bộ với cấu trúc logic:

~~~text
application
  └── label
      ├── default
      ├── dev
      ├── mysql
      └── prod
~~~

Mỗi profile chứa một map property. Repository sẽ:

1. Xác thực application và label.
2. Tách chuỗi profile thành danh sách theo đúng thứ tự request.
3. Nạp cấu hình `default` trước.
4. Nạp từng profile active theo thứ tự từ trái sang phải; profile sau ghi đè key trùng của profile trước.
5. Tạo Config `Environment` và thêm `PropertySource`.

### 6.1. Interface truy cập catalog

Để tách phần chọn ứng dụng/profile khỏi công nghệ lưu trữ, định nghĩa một abstraction nhỏ:

~~~java
package com.example.configserver.repository;

import java.util.Map;

public interface ConfigurationCatalog {

    boolean supportsApplication(String application);

    boolean supportsLabel(String label);

    boolean supportsProfile(String application, String label, String profile);

    Map<String, Object> find(
            String application,
            String label,
            String profile);
}
~~~

Trong production, `ConfigurationCatalog` có thể được triển khai bằng JDBC, JPA, Redis hoặc REST client. Các câu truy vấn phải dùng parameter binding và giới hạn quyền truy cập theo caller.

Trong ví dụ, quy ước của `find` là luôn trả về một map không null; nếu profile không có property thì trả map rỗng. Cách này giúp repository không gặp `NullPointerException` khi gọi `putAll`.

### 6.2. Repository triển khai hợp đồng

~~~java
package com.example.configserver.repository;

import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.cloud.config.environment.Environment;
import org.springframework.cloud.config.environment.PropertySource;
import org.springframework.cloud.config.server.environment.EnvironmentRepository;
import org.springframework.core.Ordered;
import org.springframework.util.StringUtils;

public class CatalogEnvironmentRepository
        implements EnvironmentRepository, Ordered {

    private static final String DEFAULT_LABEL = "main";
    private static final String DEFAULT_PROFILE = "default";

    private final ConfigurationCatalog catalog;

    public CatalogEnvironmentRepository(ConfigurationCatalog catalog) {
        this.catalog = catalog;
    }

    @Override
    public Environment findOne(
            String application,
            String profile,
            String label) {

        String selectedLabel =
                StringUtils.hasText(label) ? label : DEFAULT_LABEL;

        String[] profiles = parseProfiles(profile);
        Environment result = new Environment(application, profiles);
        result.setLabel(selectedLabel);

        if (!StringUtils.hasText(application)
                || !catalog.supportsApplication(application)
                || !catalog.supportsLabel(selectedLabel)) {
            return result;
        }

        Map<String, Object> merged = new LinkedHashMap<>();
        merged.putAll(catalog.find(
                application, selectedLabel, DEFAULT_PROFILE));

        for (String activeProfile : profiles) {
            if (DEFAULT_PROFILE.equals(activeProfile)) {
                continue;
            }

            if (!catalog.supportsProfile(
                    application, selectedLabel, activeProfile)) {
                return result;
            }

            merged.putAll(catalog.find(
                    application, selectedLabel, activeProfile));
        }

        if (!merged.isEmpty()) {
            String sourceName = "custom:"
                    + application + ":"
                    + String.join(",", profiles) + ":"
                    + selectedLabel;

            result.add(new PropertySource(sourceName, merged));
        }

        return result;
    }

    private String[] parseProfiles(String profile) {
        if (!StringUtils.hasText(profile)) {
            return new String[] { DEFAULT_PROFILE };
        }

        String[] parsed = Arrays.stream(
                    StringUtils.commaDelimitedListToStringArray(profile))
                .map(String::trim)
                .filter(StringUtils::hasText)
                .distinct()
                .toArray(String[]::new);

        return parsed.length == 0
                ? new String[] { DEFAULT_PROFILE }
                : parsed;
    }

    @Override
    public int getOrder() {
        return 0;
    }
}
~~~

Đây là ví dụ minh họa cách điều phối. `ConfigurationCatalog` phải có implementation và bean thực tế thì repository mới khởi động được. Ví dụ chọn `main` làm default label cho catalog này; nếu backend dùng Git, hãy lấy default label từ cấu hình Git của Config Server thay vì mặc định mọi repository đều có nhánh `main`.

Config Client có thể gửi label mặc định như `master` tùy phiên bản và cấu hình. Khi triển khai, hãy thống nhất default label giữa client, Config Server và catalog. Cách dễ dự đoán nhất là đặt `spring.cloud.config.label` tường minh trong môi trường triển khai hoặc đọc default label từ cấu hình backend thay vì để mỗi lớp tự chọn một giá trị.

Một số điểm trong code:

- `new Environment(application, profiles)` tạo mô hình kết quả với tên ứng dụng và danh sách profile đã parse.
- `setLabel` ghi lại label đã chọn vào response.
- `LinkedHashMap` giữ thứ tự thêm key; `putAll` của profile sau thay giá trị key trùng từ profile trước.
- `PropertySource` chứa map kết quả để Config Client đọc được.
- `getOrder()` điều khiển độ ưu tiên khi repository được đưa vào composite; giá trị cụ thể phải phù hợp với thứ tự repository còn lại.
- Profile không hợp lệ trả về Environment rỗng trong ví dụ. Khi cấu hình `accept-empty=false`, Config Server có thể trả HTTP 404 nếu ứng dụng không có property source. Một hệ thống thực tế có thể dùng exception/response policy riêng để phân biệt app không tồn tại với profile không hợp lệ.

## 7. Đăng ký repository vào Config Server

Config Server cần dependency `spring-cloud-config-server`, được quản lý bởi Spring Cloud BOM tương thích với Spring Boot:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-config-server</artifactId>
</dependency>
~~~

Ứng dụng server bật `@EnableConfigServer`:

~~~java
package com.example.configserver;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.config.server.EnableConfigServer;

@SpringBootApplication
@EnableConfigServer
public class ConfigServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigServerApplication.class, args);
    }
}
~~~

Đăng ký repository bằng bean. Có thể giới hạn bean ở profile runtime `custom` của **Config Server**:

~~~java
package com.example.configserver;

import com.example.configserver.repository.CatalogEnvironmentRepository;
import com.example.configserver.repository.ConfigurationCatalog;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
@Profile("custom")
public class CustomRepositoryConfiguration {

    @Bean
    CatalogEnvironmentRepository catalogEnvironmentRepository(
            ConfigurationCatalog catalog) {
        return new CatalogEnvironmentRepository(catalog);
    }
}
~~~

Kích hoạt profile `custom` trên Config Server:

~~~yaml
spring:
  application:
    name: config-server
  profiles:
    active: custom
  cloud:
    config:
      server:
        accept-empty: false
server:
  port: 8888
~~~

`custom` ở đây là profile để kích hoạt bean repository trong tiến trình Config Server. Nó **không phải** profile `dev`, `prod` hay `mysql` mà Config Client gửi trong request. Hai nhóm profile có phạm vi và mục đích khác nhau.

Trong ví dụ, `accept-empty: false` giúp server trả 404 nếu repository không tìm thấy ứng dụng hoặc trả về Environment không có property source. Nếu muốn kết hợp custom repository với Git/Vault hoặc nguồn khác, hãy cấu hình composite rõ ràng thay vì vô tình kích hoạt nhiều backend không có thứ tự xác định.

## 8. Gọi endpoint để kiểm tra lựa chọn application/profile

Sau khi chạy Config Server tại `localhost:8888`, thử gọi:

~~~bash
curl -i "http://localhost:8888/order-service/dev/release-2026.11"
~~~

Yêu cầu nhiều profile:

~~~bash
curl -i "http://localhost:8888/order-service/dev,mysql/release-2026.11"
~~~

Yêu cầu cùng profile nhưng application khác:

~~~bash
curl -i "http://localhost:8888/catalog-service/dev/release-2026.11"
~~~

Nếu catalog có dữ liệu cho ba bộ chọn này, mỗi response sẽ có `name`, `profiles`, `label` và property sources tương ứng. Nếu `order-service` có `order.timeout=5s` ở profile `dev`, còn profile `mysql` ghi `order.timeout=8s`, response sau cùng phải dùng `8s` theo quy tắc last-profile-wins mà repository đã triển khai.

### 8.1. Ví dụ response

~~~json
{
  "name": "order-service",
  "profiles": ["dev", "mysql"],
  "label": "release-2026.11",
  "propertySources": [
    {
      "name": "custom:order-service:dev,mysql:release-2026.11",
      "source": {
        "order.timeout": "8s",
        "order.checkout.enabled": "true",
        "spring.datasource.url": "jdbc:mysql://db-dev/orders"
      }
    }
  ]
}
~~~

Nếu gọi `catalog-service`, repository phải trả dữ liệu thuộc namespace `catalog-service`; không được dùng lại cấu hình của `order-service` chỉ vì profile giống nhau.

## 9. Kết hợp nhiều profile đúng thứ tự

Giả sử catalog chứa:

| Profile | `order.timeout` | `order.checkout.enabled` | `spring.datasource.url` |
| --- | --- | --- | --- |
| `default` | `3s` | `false` | `jdbc:postgresql://db/orders` |
| `dev` | `5s` | `true` | `jdbc:postgresql://db-dev/orders` |
| `mysql` | `8s` | — | `jdbc:mysql://db-dev/orders` |
| `prod` | `2s` | `false` | `jdbc:postgresql://db-prod/orders` |

Với request `dev,mysql`, quá trình hợp nhất:

1. Nạp `default`: timeout `3s`, checkout `false`, URL PostgreSQL mặc định.
2. Nạp `dev`: timeout `5s`, checkout `true`, URL PostgreSQL dev.
3. Nạp `mysql`: timeout `8s`, URL MySQL dev; giá trị checkout không được khai báo nên giữ `true` từ `dev`.

Kết quả:

~~~yaml
order:
  timeout: 8s
  checkout:
    enabled: true
spring:
  datasource:
    url: jdbc:mysql://db-dev/orders
~~~

Nếu request đảo thành `mysql,dev`, profile `dev` được xử lý cuối và có thể ghi đè `order.timeout` về `5s`, đồng thời URL datasource trở lại PostgreSQL dev. Vì vậy, không sắp xếp lại profile đầu vào nếu thứ tự đó có ý nghĩa với client.

Trong trường hợp muốn giữ riêng từng nguồn để audit, có thể trả nhiều `PropertySource` thay vì gộp vào một map. Khi đó, phải bảo đảm property source ưu tiên cao hơn nằm trước trong danh sách `Environment`, theo quy ước của Config Server.

## 10. Client chọn application, profile và label như thế nào?

Config Client hiện đại dùng Config Data import. Ví dụ `application.yml` của `order-service`:

~~~yaml
spring:
  application:
    name: order-service
  profiles:
    active: dev,mysql
  config:
    import: "configserver:http://localhost:8888"
  cloud:
    config:
      label: release-2026.11
~~~

Dependency client:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-config</artifactId>
</dependency>
~~~

Spring Cloud Config Client dùng:

- `spring.application.name` để chọn application mặc định.
- `Environment.getActiveProfiles()` để lấy profile đang active.
- `spring.cloud.config.label` để chọn label.

Có thể ghi đè riêng tên application, profile hoặc label bằng:

~~~yaml
spring:
  cloud:
    config:
      name: order-service,shared-database
      profile: dev,mysql
      label: release-2026.11
~~~

Khi `spring.cloud.config.name` có nhiều tên phân tách bằng dấu phẩy, Config Server có thể trả cấu hình chung từ tên `application`, cấu hình riêng của service và các nguồn dùng chung được liệt kê thêm. Tên xuất hiện sau trong danh sách có thể ghi đè key trùng từ tên trước.

### 10.1. Vì sao Config Server có thể nhận nhiều request khi startup?

Với `spring.config.import`, Spring Boot nạp cấu hình theo hai bước:

1. Yêu cầu cấu hình với profile `default` để tìm các property có thể kích hoạt profile khác.
2. Sau khi xác định active profiles, yêu cầu thêm cấu hình theo các profile đó.

Vì vậy, một Config Client có thể gọi `EnvironmentRepository.findOne` nhiều lần trong cùng quá trình khởi động. Đây là hành vi bình thường. Repository nên **idempotent**, trả kết quả nhất quán cho cùng bộ `application/profile/label`, không ghi thay đổi trạng thái khi chỉ đọc và không giả định mỗi startup chỉ có một lần gọi.

Nếu cần dùng legacy bootstrap, phải chủ động bật cơ chế bootstrap theo tài liệu Spring Cloud Config. `bootstrap.yml` không bắt buộc khi dùng Config Data import hiện đại.

## 11. Chọn repository trong composite

Một Config Server có thể kết hợp Git với repository tùy biến, Vault hoặc nguồn khác. Khi nhiều repository cùng cung cấp một key, thứ tự của chúng quyết định giá trị nào thắng.

Ví dụ composite:

~~~yaml
spring:
  profiles:
    active: composite
  cloud:
    config:
      server:
        composite:
          - type: git
            uri: file:./config-repository
          - type: vault
            host: 127.0.0.1
            port: 8200
~~~

Với composite, thứ tự khai báo repository có ảnh hưởng đến precedence. Tài liệu Spring Cloud Config cũng cho phép cấu hình `order` khi kích hoạt các backend theo profile tương ứng; giá trị số nhỏ hơn có ưu tiên cao hơn.

Ví dụ trên chỉ minh họa thứ tự. Nếu dùng Vault thật, phải cấu hình token/credentials theo hướng dẫn của Vault backend và bảo đảm token có quyền đọc đúng secret path.

Nếu custom repository được đưa vào composite, triển khai `Ordered` và `getOrder()` để xác định rõ vị trí của nó. Nếu không triển khai `Ordered`, custom repository được xem là có độ ưu tiên thấp nhất theo hướng dẫn custom repository.

Một điểm vận hành quan trọng: mặc định lỗi khi đọc một repository có thể làm toàn bộ composite request thất bại. Chỉ bật `spring.cloud.config.server.fail-on-composite-error=false` khi chấp nhận rõ ràng hành vi tiếp tục phục vụ từ các nguồn còn lại và hiểu tác động đến tính đầy đủ của cấu hình.

## 12. Kiểm thử repository

Có thể unit test trực tiếp phương thức `findOne` mà không cần khởi động HTTP server. Với catalog giả lập, kiểm tra ít nhất các trường hợp:

~~~java
@Test
void selectsApplicationAndMergesProfilesInRequestOrder() {
    Environment environment = repository.findOne(
            "order-service",
            "dev,mysql",
            "release-2026.11");

    assertThat(environment.getName()).isEqualTo("order-service");
    assertThat(environment.getProfiles())
            .containsExactly("dev", "mysql");
    assertThat(environment.getLabel())
            .isEqualTo("release-2026.11");

    Map<?, ?> source = (Map<?, ?>) environment
            .getPropertySources().get(0).getSource();

    assertThat(source).containsEntry("order.timeout", "8s");
}
~~~

Đoạn test giả định catalog có dữ liệu mẫu ở phần trước và dùng AssertJ. Cần bổ sung test cho application khác để chắc chắn namespace không bị lẫn.

### 12.1. Ma trận test nên có

| Trường hợp | Đầu vào | Kết quả mong đợi |
| --- | --- | --- |
| Một application, một profile | `order-service`, `dev`, `release-2026.11` | Chọn cấu hình của đúng service/profile/label |
| Nhiều profile | `dev,mysql` | Profile cuối ghi đè key trùng |
| Đảo thứ tự profile | `mysql,dev` | Giá trị có thể đổi theo thứ tự mới |
| Application khác | `catalog-service`, `dev` | Không có property của order-service |
| Label khác | `release-2026.10` | Trả đúng snapshot cũ hoặc không có dữ liệu |
| Application không tồn tại | `unknown-service` | Không trả cấu hình của service khác; xử lý 404 theo policy |
| Profile không hợp lệ | `dev,unknown` | Báo lỗi/không có kết quả theo policy đã định, không âm thầm dùng nhầm profile |
| Profile rỗng/default | `default` hoặc không có profile | Dùng dữ liệu mặc định theo quy tắc đã chọn |

Ngoài unit test, nên có integration test gọi endpoint thật để kiểm tra serialization của `Environment`, HTTP status khi không tìm thấy dữ liệu và việc Config Server chọn đúng repository bean theo profile runtime.

## 13. Bảo vệ đầu vào và dữ liệu cấu hình

`application`, `profile` và `label` được truyền qua URL. Chúng là selector từ request, vì vậy cần xác thực và kiểm tra trước khi dùng.

- **Allowlist application:** chỉ cho phép caller đọc application mà danh tính của họ được cấp quyền.
- **Validate profile:** giới hạn profile hợp lệ theo từng ứng dụng; không cho phép chuỗi rỗng, ký tự điều khiển hoặc profile không được hỗ trợ.
- **Validate label:** chỉ chấp nhận branch/tag/commit hoặc version có trong policy; không nối chuỗi label trực tiếp vào lệnh shell hoặc SQL.
- **Truy vấn an toàn:** dùng parameterized SQL/ORM binding, không ghép `application` hay `profile` vào câu SQL.
- **Đường dẫn file:** nếu tự tạo file backend, chuẩn hóa path và xác nhận kết quả vẫn nằm trong root cấu hình được phép để tránh path traversal.
- **Không rò rỉ secret:** bảo vệ endpoint Config Server bằng authentication/authorization và TLS; chỉ trả secret cho client được phép.
- **Audit:** ghi nhận application, profile, label, caller, kết quả và version cấu hình; tránh ghi nội dung secret vào log.

Ký hiệu `(_)` có thể được Spring Cloud Config dùng để biểu diễn dấu `/` trong một số path application/label vì dấu `/` vốn là dấu phân cách URL. Cơ chế này chỉ giải quyết biểu diễn đường dẫn, **không thay thế kiểm tra quyền truy cập**.

## 14. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Request trả cấu hình của application khác | Repository bỏ qua tham số `application` hoặc catalog dùng key không đầy đủ | Dùng application làm khóa namespace trong mọi lần truy vấn và thêm test chéo ứng dụng |
| Profile thứ hai không ghi đè | Repository sắp xếp profile hoặc merge ngược thứ tự | Giữ thứ tự profile đầu vào và áp dụng profile sau sau cùng |
| Profile `default` bị thiếu | Chỉ đọc profile active, không nạp cấu hình dùng chung | Nạp default trước rồi áp dụng các profile active |
| Label không đổi dữ liệu | Backend luôn dùng nhánh/version mặc định | Đưa label vào truy vấn catalog hoặc Git reference |
| Client gọi Config Server nhiều lần | Config Data nạp default trước rồi active profiles | Thiết kế `findOne` idempotent và kiểm tra log request theo từng profile |
| Custom repository không được gọi | Bean không được tạo do profile/conditional config hoặc backend khác đang được chọn | Kiểm tra profile runtime của Config Server và cấu hình composite |
| Composite trả giá trị không mong đợi | Thứ tự repository/`Ordered` chưa rõ | Khai báo thứ tự tường minh và test key trùng |
| Ứng dụng nhận Environment rỗng | Sai application/profile/label hoặc catalog không có dữ liệu | Kiểm tra tham số request và bật `accept-empty=false` nếu muốn 404 |

## 15. Tổng kết

Trong Spring Cloud Config Server, `EnvironmentRepository.findOne(application, profile, label)` là điểm mở rộng để chọn và đọc cấu hình theo từng ứng dụng, profile và phiên bản. Các tham số đầu vào xác định phạm vi dữ liệu; đối tượng `org.springframework.cloud.config.environment.Environment` được tạo ra sau đó để trả metadata cùng các `PropertySource` về cho client.

Một repository tốt giữ nguyên application và label, xử lý danh sách profile theo đúng thứ tự, nạp cấu hình mặc định trước, kiểm soát dữ liệu không tồn tại và trả kết quả ổn định. Khi tích hợp vào Config Server, cần đăng ký bean đúng profile runtime, xác định precedence nếu dùng composite, bảo vệ endpoint và kiểm thử cả request hợp lệ lẫn request sai.

## Tài liệu tham khảo

- [Spring Cloud Config — Custom Environment Repositories](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/custom-enviroment-repository.html): triển khai `EnvironmentRepository`, đăng ký custom bean và `Ordered`.
- [Spring Cloud Config — Environment Repository](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository.html): ý nghĩa application/profile/label và precedence của profile.
- [Spring Cloud Config — Config Client](https://docs.spring.io/spring-cloud-config/reference/client.html): cách client chọn application/profile/label, Config Data import và request khi active profiles thay đổi.
- [Spring Cloud Config — Composite Environment Repositories](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/composite-repositories.html): thứ tự repository, `order` và xử lý lỗi composite.
- [Spring Cloud Config — Git Backend](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/git-backend.html): label Git, pattern repository theo application/profile và search paths.
- [Spring Framework — Environment Abstraction](https://docs.spring.io/spring-framework/reference/core/beans/environment.html): `Environment`, profile và `PropertySource` của Spring Framework.

Luôn đối chiếu tài liệu theo release train Spring Cloud đang sử dụng. Hợp đồng `EnvironmentRepository` có thể có overload bổ sung theo phiên bản; phương thức ba tham số trong bài là điểm bắt đầu cơ bản cho một custom repository.

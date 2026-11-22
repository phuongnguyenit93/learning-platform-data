# `Environment`, `ConfigurableEnvironment` và `PropertySource`

Trong Spring, cấu hình của ứng dụng không chỉ nằm trong một file YAML hoặc Properties. Khi ứng dụng khởi động, nhiều nguồn khác nhau có thể cung cấp cùng một thuộc tính: file đóng gói trong JAR, file bên ngoài, profile, biến môi trường, JVM system properties, tham số dòng lệnh, cấu hình kiểm thử và cấu hình từ xa. Spring cần một cơ chế thống nhất để truy vấn các giá trị đó và quyết định nguồn nào được ưu tiên.

Cơ chế này được thể hiện qua ba abstraction:

- **`Environment`**: giao diện đọc thuộc tính và truy vấn profile đang hoạt động.
- **`ConfigurableEnvironment`**: phiên bản có khả năng cấu hình Environment, quản lý profile và danh sách nguồn thuộc tính.
- **`PropertySource`**: đại diện cho một nguồn cung cấp giá trị thuộc tính.

Trong module **SPRING_CLOUD_CORE**, các abstraction này là nền tảng để hiểu cấu hình bên ngoài, Spring Cloud Config, discovery, service registry và refresh. Chúng giúp các thư viện tích hợp cung cấp cấu hình vào ứng dụng Spring Boot theo cách thống nhất, trong khi mã nghiệp vụ có thể đọc giá trị mà không cần biết giá trị đến từ file, biến môi trường hay máy chủ cấu hình.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích vai trò của `Environment`, `ConfigurableEnvironment` và `PropertySource`.
2. Đọc thuộc tính qua `Environment` và xử lý trường hợp key không tồn tại.
3. Phân biệt active profiles với default profiles và sử dụng điều kiện profile.
4. Giải thích thứ tự ưu tiên của `PropertySource` và cách nguồn đầu tiên chứa key quyết định giá trị.
5. Thêm hoặc thay thế một nguồn thuộc tính có kiểm soát qua `MutablePropertySources`.
6. Hiểu cách Spring Boot đưa Config Data, biến môi trường và tham số dòng lệnh vào Environment.
7. Phân biệt việc thay đổi Environment với việc rebind hoặc refresh các bean đang chạy.
8. Kiểm thử cấu hình và chẩn đoán nguồn giá trị trong ứng dụng Spring Cloud.

## 2. `Environment`: giao diện đọc cấu hình và profile

`Environment` là một abstraction của Spring Core, mở rộng `PropertyResolver` và cung cấp thêm khả năng làm việc với profile. Các thành phần ứng dụng có thể dùng nó để đọc giá trị mà không cần phụ thuộc trực tiếp vào một file cấu hình cụ thể.

### 2.1. Đọc thuộc tính

Các phương thức thường dùng:

| Phương thức | Ý nghĩa |
| --- | --- |
| `getProperty(key)` | Lấy giá trị dạng `String`; trả về `null` nếu không có |
| `getProperty(key, defaultValue)` | Lấy giá trị hoặc dùng giá trị mặc định |
| `getProperty(key, targetType)` | Lấy và chuyển đổi sang kiểu đích |
| `getProperty(key, targetType, defaultValue)` | Chuyển đổi kiểu hoặc dùng giá trị mặc định |
| `getRequiredProperty(key)` | Đọc thuộc tính bắt buộc; ném lỗi nếu không tồn tại |
| `containsProperty(key)` | Kiểm tra có nguồn nào cung cấp key hay không |
| `resolvePlaceholders(text)` | Thay placeholder; placeholder không giải quyết được có thể giữ nguyên |
| `resolveRequiredPlaceholders(text)` | Thay placeholder và báo lỗi nếu không giải quyết được |

Ví dụ, giả sử ứng dụng có cấu hình:

~~~yaml
clients:
  inventory:
    base-url: https://inventory.internal.example
    read-timeout: 700ms
    enabled: true
~~~

Có thể đọc các giá trị qua `Environment`:

~~~java
import java.net.URI;
import java.time.Duration;

import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class InventoryEnvironmentProbe {
    private final Environment environment;

    public InventoryEnvironmentProbe(Environment environment) {
        this.environment = environment;
    }

    public void inspect() {
        URI baseUrl = environment.getProperty(
                "clients.inventory.base-url",
                URI.class
        );

        Duration timeout = environment.getProperty(
                "clients.inventory.read-timeout",
                Duration.class,
                Duration.ofMillis(500)
        );

        boolean enabled = environment.getProperty(
                "clients.inventory.enabled",
                Boolean.class,
                false
        );

        System.out.println("baseUrl = " + baseUrl);
        System.out.println("timeout = " + timeout);
        System.out.println("enabled = " + enabled);
    }
}
~~~

Spring sử dụng cơ chế chuyển đổi kiểu của `PropertyResolver`/conversion service được cấu hình. Những kiểu như `Duration`, `URI`, số và boolean có thể được chuyển đổi khi có converter phù hợp. Nếu key bắt buộc, nên dùng `getRequiredProperty` hoặc binding có validation để phát hiện lỗi ngay lúc khởi tạo.

### 2.2. Phân biệt giá trị mặc định và giá trị bắt buộc

Dùng default value khi ứng dụng có hành vi hợp lệ nếu không cấu hình key:

~~~java
Duration timeout = environment.getProperty(
        "clients.inventory.read-timeout",
        Duration.class,
        Duration.ofMillis(700)
);
~~~

Dùng required property khi thiếu cấu hình phải làm ứng dụng thất bại sớm:

~~~java
String registryEndpoint = environment.getRequiredProperty(
        "spring.cloud.discovery.client.simple.instances.inventory-service[0].uri"
);
~~~

Không nên biến mọi thuộc tính thành bắt buộc. Hãy phân loại:

- **Bắt buộc:** thiếu sẽ khiến ứng dụng không thể phục vụ nghiệp vụ an toàn.
- **Có mặc định hợp lệ:** có thể chạy với giá trị được chọn rõ ràng.
- **Tùy chọn:** tính năng có thể tắt nếu không cấu hình.
- **Nhạy cảm:** cần lấy từ secret store hoặc nguồn bảo mật, tránh log.

Việc chọn default value phải dựa trên nghiệp vụ. Ví dụ timeout quá lớn có thể giữ tài nguyên lâu, còn timeout quá nhỏ có thể làm request thất bại không cần thiết.

### 2.3. Placeholder và giải quyết giá trị

`PropertyResolver` cũng hỗ trợ thay placeholder:

~~~java
String endpoint = environment.resolveRequiredPlaceholders(
        "${clients.inventory.base-url}"
);
~~~

Nếu placeholder không tồn tại, phương thức `resolveRequiredPlaceholders` báo lỗi. Điều này phù hợp với cấu hình bắt buộc. Với placeholder tùy chọn, có thể cung cấp default ngay trong biểu thức ở nơi cấu hình hỗ trợ:

~~~yaml
clients:
  inventory:
    base-url: "${INVENTORY_URL:http://localhost:8081}"
~~~

`Environment` là nơi đọc giá trị sau khi các nguồn đã được kết hợp. Nó không phải là một template engine tổng quát và cũng không tự gọi Config Server chỉ vì một chuỗi chứa placeholder.

## 3. Profile trong Environment

Profile biểu diễn một nhóm cấu hình hoặc bean chỉ áp dụng trong một bối cảnh nhất định, chẳng hạn `dev`, `test`, `staging` hoặc `prod`.

### 3.1. Active profiles và default profiles

`Environment` cung cấp:

- `getActiveProfiles()`: danh sách profile đang hoạt động.
- `getDefaultProfiles()`: danh sách profile mặc định khi không có active profile phù hợp.
- `acceptsProfiles(...)`: kiểm tra một profile expression có được chấp nhận hay không.

Ví dụ:

~~~java
import java.util.Arrays;

import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
class ProfileProbe {
    ProfileProbe(Environment environment) {
        System.out.println("active profiles: "
                + Arrays.toString(environment.getActiveProfiles()));
        System.out.println("default profiles: "
                + Arrays.toString(environment.getDefaultProfiles()));
    }
}
~~~

Nếu không có active profile, Spring thường sử dụng profile mặc định tên `default`, trừ khi ứng dụng đã cấu hình default profiles khác.

### 3.2. Điều kiện profile

Có thể kiểm tra profile bằng `Profiles.of`:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;

boolean isProduction = environment.acceptsProfiles(
        Profiles.of("prod")
);

boolean isProductionOrStaging = environment.acceptsProfiles(
        Profiles.of("prod", "staging")
);

boolean isProductionOnCloud = environment.acceptsProfiles(
        Profiles.of("prod & cloud")
);
~~~

Trong biểu thức:

- Dấu `&` biểu thị điều kiện AND.
- Dấu `|` biểu thị điều kiện OR.
- Dấu `!` biểu thị phủ định.
- Có thể dùng ngoặc để nhóm biểu thức.

Spring cũng cho phép dùng annotation:

~~~java
@Configuration
@Profile("prod")
class ProductionConfiguration {
    // Các bean chỉ được đăng ký khi profile prod phù hợp.
}
~~~

Profile không phải một nguồn giá trị riêng. Nó là điều kiện ảnh hưởng đến cấu hình nào được kích hoạt, file nào được nạp và bean nào được đăng ký.

### 3.3. Đặt profile qua ConfigurableEnvironment

`ConfigurableEnvironment` cho phép đặt active hoặc default profiles trước khi context refresh:

~~~java
ConfigurableEnvironment environment = ...;

environment.setActiveProfiles("prod", "cloud");
environment.addActiveProfile("metrics");
environment.setDefaultProfiles("local");
~~~

Cần phân biệt:

- `setActiveProfiles(...)` thay danh sách active profiles được thiết lập qua API.
- `addActiveProfile(...)` bổ sung một profile.
- `setDefaultProfiles(...)` thay danh sách default profiles.

Thay đổi active profiles sau khi context đã refresh không tự động đăng ký lại hoặc loại bỏ những bean đã được tạo theo `@Profile`. Điều kiện profile chủ yếu được xét trong quá trình đăng ký cấu hình/bean. Không dùng thay đổi profile runtime như một cơ chế bật tắt bean động.

## 4. `ConfigurableEnvironment`: quản lý Environment

`ConfigurableEnvironment` mở rộng `Environment` và `ConfigurablePropertyResolver`. Nó bổ sung khả năng quản lý property sources, profile và một số thuộc tính nền tảng của môi trường.

Các khả năng quan trọng:

| API | Vai trò |
| --- | --- |
| `getPropertySources()` | Lấy danh sách nguồn thuộc tính có thể thay đổi |
| `getSystemProperties()` | Truy cập system properties |
| `getSystemEnvironment()` | Truy cập environment variables |
| `setActiveProfiles(...)` | Đặt danh sách active profiles |
| `addActiveProfile(...)` | Thêm một active profile |
| `setDefaultProfiles(...)` | Đặt default profiles |
| `merge(parent)` | Hợp nhất property sources và profiles từ Environment cha |
| `setPlaceholderPrefix(...)`, `setPlaceholderSuffix(...)` | Tùy chỉnh cú pháp placeholder khi cần |
| `setConversionService(...)` | Cấu hình conversion service cho việc chuyển kiểu |

Thông thường, mã nghiệp vụ chỉ cần `Environment` để đọc cấu hình. Chỉ dùng `ConfigurableEnvironment` khi cần cấu hình môi trường trong giai đoạn bootstrap, viết integration hoặc kiểm thử.

### 4.1. Lấy ConfigurableEnvironment từ ApplicationContext

Một `ConfigurableApplicationContext` cung cấp `getEnvironment()`:

~~~java
ConfigurableApplicationContext context = ...;
ConfigurableEnvironment environment =
        (ConfigurableEnvironment) context.getEnvironment();
~~~

Trong ứng dụng Spring Boot, `ConfigurableApplicationContext` là kiểu context thường dùng khi cần truy cập cấu hình có thể thay đổi. Không nên cast tùy tiện nếu không kiểm soát loại context; hãy nhận kiểu phù hợp từ lifecycle hoặc API đang sử dụng.

### 4.2. Cấu hình Environment trước khi refresh

Một cách phổ biến là dùng `ApplicationContextInitializer` để thêm property source trước khi context được refresh:

~~~java
import java.util.Map;

import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;

public class RuntimeOverridesInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        ConfigurableEnvironment environment = context.getEnvironment();

        Map<String, Object> values = Map.of(
                "clients.inventory.read-timeout", "900ms",
                "clients.inventory.enabled", true
        );

        environment.getPropertySources().addFirst(
                new MapPropertySource("runtimeOverrides", values)
        );
    }
}
~~~

Đăng ký initializer với `SpringApplication`:

~~~java
SpringApplication application =
        new SpringApplication(OrdersApplication.class);

application.addInitializers(new RuntimeOverridesInitializer());
application.run(args);
~~~

Nguồn `runtimeOverrides` được thêm vào đầu danh sách nên có độ ưu tiên cao hơn những nguồn nằm sau nó khi cùng chứa một key. Ví dụ này minh họa kỹ thuật; trong production, cần quyết định rõ nguồn override nào được phép thắng cấu hình triển khai và tránh ghi cứng giá trị nhạy cảm trong mã nguồn.

### 4.3. `Environment.merge(parent)`

Một số ứng dụng có context cha và context con. `merge(parent)` hỗ trợ đưa property sources và profiles từ Environment cha vào Environment hiện tại. Các property source của parent được thêm sau các nguồn hiện có của child; do đó, nguồn đã có trong child giữ ưu tiên cao hơn.

Không nên nhầm việc merge Environment với việc hợp nhất toàn bộ bean giữa hai context. Bean lookup theo context hierarchy là cơ chế của `ApplicationContext`; `Environment.merge` chỉ nói về property sources và profiles.

## 5. `PropertySource`: một nguồn cung cấp thuộc tính

`PropertySource<T>` là abstraction đại diện cho một nguồn dữ liệu có thể tra cứu bằng tên key. `T` là kiểu dữ liệu nguồn bên dưới, ví dụ `Map<String, Object>`, `Properties` hoặc một đối tượng tùy chỉnh.

Một `PropertySource` thường có:

- **name:** tên định danh nguồn.
- **source:** đối tượng dữ liệu nền.
- **getProperty(name):** trả về giá trị của key hoặc `null` nếu nguồn không có key.

### 5.1. Các loại PropertySource thường gặp

| Loại | Mục đích |
| --- | --- |
| `MapPropertySource` | Đọc thuộc tính từ `Map<String, Object>` |
| `PropertiesPropertySource` | Đọc từ đối tượng `Properties` |
| `SystemEnvironmentPropertySource` | Đọc biến môi trường của tiến trình, có hỗ trợ quy tắc tên phù hợp |
| `StubPropertySource` | Placeholder source dùng trong một số giai đoạn/lifecycle |
| `CompositePropertySource` | Gom nhiều `PropertySource` thành một nguồn tổng hợp |
| `EnumerablePropertySource` | Nguồn có thể liệt kê các tên thuộc tính |

Spring Boot còn tạo các property source cho Config Data, command-line arguments, random values và những nguồn cấu hình khác. Những nguồn đó được đưa vào cùng cơ chế phân giải thuộc tính.

### 5.2. PropertySource không nhất thiết là file

Một property source có thể được xây dựng từ:

- File `.properties` hoặc YAML đã được nạp.
- JVM system properties (`-Dname=value`).
- Environment variables của tiến trình.
- Command-line arguments.
- Map được tạo trong mã.
- Nguồn từ xa đã được integration nạp vào Environment.
- Nguồn tùy chỉnh do ứng dụng hoặc thư viện cung cấp.

Vì vậy, khi gọi `environment.getProperty("clients.inventory.read-timeout")`, mã ứng dụng không cần biết giá trị được đọc từ YAML, biến môi trường hay Config Server. Nó chỉ yêu cầu giá trị theo key.

## 6. Thứ tự ưu tiên giữa các PropertySource

`MutablePropertySources` giữ một danh sách có thứ tự. Khi Spring phân giải một key, nguồn có ưu tiên cao hơn được kiểm tra trước; giá trị đầu tiên khác `null` được sử dụng.

### 6.1. Quy tắc first match wins

Giả sử có ba nguồn:

| Thứ tự | PropertySource | `clients.inventory.read-timeout` |
| ---: | --- | --- |
| 1 | `commandLineArgs` | `1200ms` |
| 2 | `systemEnvironment` | `1000ms` |
| 3 | `applicationConfig` | `700ms` |

Kết quả từ `Environment` là `1200ms` vì nguồn đầu tiên chứa key này được chọn.

~~~mermaid
flowchart TD
    A[environment.getProperty(key)] --> B{Source 1 có key?}
    B -- Có --> C[Trả về giá trị Source 1]
    B -- Không --> D{Source 2 có key?}
    D -- Có --> E[Trả về giá trị Source 2]
    D -- Không --> F{Source tiếp theo có key?}
    F -- Có --> G[Trả về giá trị đầu tiên tìm thấy]
    F -- Không --> H[Trả về null hoặc default]
~~~

Sơ đồ mô tả nguyên tắc tổng quát. Thứ tự nguồn cụ thể trong Spring Boot phụ thuộc phiên bản và cách ứng dụng được khởi động. Hãy xem `Environment` thực tế thay vì giả định danh sách luôn giống nhau ở mọi dự án.

### 6.2. StandardEnvironment và Spring Boot

`StandardEnvironment` của Spring Framework mặc định có các nguồn phổ biến như:

- `systemProperties`: JVM system properties.
- `systemEnvironment`: environment variables.

Trong cấu hình mặc định của `StandardEnvironment`, system properties có ưu tiên cao hơn system environment. Spring Boot bổ sung nhiều nguồn khác, ví dụ command-line arguments, Config Data, test properties, devtools và nguồn cấu hình tích hợp. Vì thế, thứ tự đầy đủ của một ứng dụng Boot không thể suy ra chỉ từ hai nguồn của `StandardEnvironment`.

Ví dụ, tham số:

~~~bash
java -jar orders-service.jar --server.port=9090
~~~

được Spring Boot đưa vào một property source riêng cho command line. Nguồn này thường có ưu tiên cao, cho phép override giá trị trong file cấu hình.

### 6.3. Cùng key xuất hiện ở nhiều nguồn

Giả sử cấu hình mặc định:

~~~yaml
clients:
  inventory:
    read-timeout: 700ms
~~~

Môi trường triển khai đặt:

~~~bash
CLIENTS_INVENTORY_READTIMEOUT=1000ms
~~~

Và lần chạy có tham số:

~~~bash
java -jar orders-service.jar --clients.inventory.read-timeout=1200ms
~~~

Nếu không có nguồn ưu tiên cao hơn khác ghi đè, giá trị cuối cùng là `1200ms`. Đây là lý do khi điều tra một giá trị “không giống file”, cần kiểm tra toàn bộ PropertySource và không chỉ mở `application.yml`.

## 7. MutablePropertySources: thêm, thay thế và xóa nguồn

`ConfigurableEnvironment.getPropertySources()` trả về `MutablePropertySources`. API này cho phép điều chỉnh danh sách nguồn cấu hình.

| Phương thức | Ý nghĩa |
| --- | --- |
| `addFirst(source)` | Thêm nguồn vào đầu danh sách, ưu tiên cao |
| `addLast(source)` | Thêm nguồn vào cuối danh sách, ưu tiên thấp |
| `addBefore(name, source)` | Thêm trước nguồn có tên đã biết |
| `addAfter(name, source)` | Thêm sau nguồn có tên đã biết |
| `replace(name, source)` | Thay nguồn có tên tương ứng |
| `remove(name)` | Loại nguồn theo tên |
| `contains(name)` | Kiểm tra nguồn có tên đó hay không |
| `precedenceOf(source)` | Trả về vị trí ưu tiên của nguồn trong danh sách |

### 7.1. Thêm MapPropertySource

~~~java
Map<String, Object> values = Map.of(
        "clients.inventory.read-timeout", "850ms",
        "clients.inventory.enabled", true
);

MapPropertySource overrides =
        new MapPropertySource("inventoryOverrides", values);

environment.getPropertySources().addFirst(overrides);
~~~

Sau khi thêm, có thể đọc:

~~~java
Duration timeout = environment.getProperty(
        "clients.inventory.read-timeout",
        Duration.class
);
~~~

Vì `inventoryOverrides` được thêm vào đầu, nó có thể ghi đè cùng key ở những nguồn phía sau. Nguồn này chỉ tồn tại trong bộ nhớ của tiến trình và không tự ghi ngược vào file cấu hình.

### 7.2. Thêm nguồn với mức ưu tiên thấp

Nếu chỉ muốn cung cấp giá trị fallback, dùng `addLast`:

~~~java
MapPropertySource defaults = new MapPropertySource(
        "libraryDefaults",
        Map.of(
                "clients.inventory.read-timeout", "500ms",
                "clients.inventory.enabled", false
        )
);

environment.getPropertySources().addLast(defaults);
~~~

Nguồn này chỉ được dùng nếu không có nguồn đứng trước cung cấp key tương ứng. Đây là một cách để thư viện cung cấp default mà vẫn cho phép ứng dụng ghi đè.

### 7.3. Thêm trước hoặc sau một nguồn cụ thể

Khi cần kiểm soát vị trí chính xác:

~~~java
environment.getPropertySources().addBefore(
        "systemEnvironment",
        new MapPropertySource("deploymentPolicy", values)
);
~~~

Tên property source phải tồn tại trong danh sách. Nếu tên không có, thao tác `addBefore`/`addAfter` không thể thực hiện và sẽ báo lỗi. Không hardcode tên nguồn Boot nếu không kiểm tra phiên bản và cách khởi động của ứng dụng.

### 7.4. Cẩn trọng khi replace hoặc remove

`replace` và `remove` tác động đến toàn bộ việc phân giải thuộc tính của context. Nếu vô tình loại `systemEnvironment` hoặc Config Data source, nhiều key có thể chuyển sang giá trị mặc định mà không có lỗi cú pháp rõ ràng.

Chỉ thay thế/xóa nguồn khi có yêu cầu cụ thể và có kiểm thử. Đối với ứng dụng thông thường, thêm một nguồn có tên riêng và mức ưu tiên được xác định rõ thường dễ hiểu hơn việc thay nguồn framework đã tạo.

## 8. Config Data và Spring Cloud Config đi vào Environment như thế nào?

### 8.1. Spring Boot Config Data

Spring Boot nạp `application.properties`, `application.yml`, file theo profile và các nguồn được import trong giai đoạn chuẩn bị Environment. Kết quả được biểu diễn bằng các property sources để phần còn lại của ứng dụng đọc qua `Environment`.

Ví dụ:

~~~yaml
spring:
  application:
    name: orders-service
  config:
    import: optional:file:./deploy-config/overrides.yml

clients:
  inventory:
    read-timeout: 700ms
~~~

File import có thể bổ sung hoặc ghi đè giá trị tùy vị trí và quy tắc Config Data. `spring.config.import` không phải API của `PropertySource`; nó là cơ chế Spring Boot để đưa nguồn Config Data bổ sung vào quá trình nạp cấu hình.

### 8.2. Spring Cloud Config Client

Khi sử dụng Spring Cloud Config Client, starter tương ứng kết nối Config Server theo cấu hình đã khai báo. Những giá trị từ server được đưa vào Environment thông qua các property source mà integration tạo ra.

Ví dụ theo cơ chế Config Data:

~~~yaml
spring:
  application:
    name: orders-service
  config:
    import: optional:configserver:http://localhost:8888
~~~

Cần có dependency Config Client phù hợp với release train. Config Server trả cấu hình theo application name, profile và label. Việc property source từ xa đứng ở vị trí nào và có thể bị ghi đè ra sao phụ thuộc cơ chế Config Client, release train và các tùy chọn override. Không nên áp dụng thứ tự của một dự án cũ cho một dự án dùng Config Data hiện đại mà chưa kiểm chứng.

**Điểm quan trọng:** `Environment` không tự thực hiện HTTP request đến Config Server. Config Client chịu trách nhiệm lấy cấu hình và đưa nó vào Environment; `Environment` cung cấp giao diện đọc giá trị sau khi quá trình tích hợp hoàn tất.

### 8.3. Discovery và service registry cũng là chuyện khác

Spring Cloud Commons có abstraction `DiscoveryClient`, `ServiceRegistry` và `ServiceInstance`. Chúng mô tả khả năng tra cứu/đăng ký service, còn `Environment` cung cấp các giá trị cấu hình như endpoint registry, tên ứng dụng hoặc tùy chọn discovery.

Ví dụ:

~~~yaml
spring:
  application:
    name: orders-service
  cloud:
    discovery:
      enabled: true
~~~

Đọc được `spring.cloud.discovery.enabled=true` từ Environment không chứng minh registry đã kết nối thành công, cũng không chứng minh `DiscoveryClient` provider đã được tạo. Cần kiểm tra riêng dependency, auto-configuration, bean và hành vi tra cứu instance.

## 9. Environment thay đổi không đồng nghĩa bean tự refresh

Một nhầm lẫn quan trọng là cho rằng chỉ cần thay giá trị trong `PropertySource` thì mọi bean đang chạy sẽ tự cập nhật.

### 9.1. Bean đọc cấu hình một lần

Ví dụ:

~~~java
@Component
class InventoryEndpoint {
    private final URI baseUrl;

    InventoryEndpoint(
            @Value("${clients.inventory.base-url}") URI baseUrl
    ) {
        this.baseUrl = baseUrl;
    }

    URI baseUrl() {
        return baseUrl;
    }
}
~~~

Giá trị được resolve khi bean được tạo và lưu trong field. Nếu sau đó một property source được thêm hoặc thay đổi, field `baseUrl` không tự gán lại.

### 9.2. `@ConfigurationProperties` cũng có vòng đời

Một bean được bind từ `@ConfigurationProperties` cũng là một đối tượng có vòng đời trong context. Việc thay đổi Environment không tự đảm bảo object đang được sử dụng đã được bind lại, đặc biệt nếu consumer giữ tham chiếu tới một client hoặc object được tạo từ giá trị cũ.

### 9.3. Vai trò của Spring Cloud Context

Spring Cloud Context bổ sung cơ chế refresh, trong đó có `@RefreshScope` và các dịch vụ liên quan đến Environment. Khi ứng dụng kích hoạt refresh đúng cách:

- Property source hoặc Environment có thể được cập nhật theo cơ chế tích hợp.
- Một số bean có thể được rebind hoặc tạo lại theo scope.
- Bean ngoài refresh scope có thể tiếp tục giữ trạng thái cũ.
- Client đang xử lý request có thể vẫn dùng instance hoặc cấu hình cũ cho đến khi vòng đời được xử lý.

`@RefreshScope` không tự theo dõi mọi file thay đổi trên đĩa, không tự polling Config Server và không tự broadcast thay đổi đến toàn bộ replica. Cần cơ chế phát tín hiệu refresh, cấu hình endpoint/messaging phù hợp và kiểm tra từng instance sau khi cập nhật.

### 9.4. Khi nào nên thay đổi PropertySource runtime?

Các trường hợp hợp lý có thể gồm:

- Kiểm thử để mô phỏng cấu hình.
- Bootstrap một nguồn override được kiểm soát.
- Tích hợp một nguồn cấu hình động có lifecycle rõ ràng.
- Cung cấp giá trị tạm thời cho một context cụ thể.

Không nên dùng việc liên tục mutate `MutablePropertySources` như một kho lưu trạng thái ứng dụng. Nếu cấu hình thay đổi thường xuyên, hãy dùng cơ chế quản lý cấu hình/refresh có chủ đích và xác định cách đồng bộ với bean phụ thuộc.

## 10. Kiểm tra nguồn thuộc tính và giá trị cuối cùng

### 10.1. Liệt kê property source

Có thể in tên các nguồn cấu hình:

~~~java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

void listSources(ConfigurableEnvironment environment) {
    for (PropertySource<?> source : environment.getPropertySources()) {
        System.out.println(source.getName());
    }
}
~~~

Thứ tự in ra phản ánh thứ tự ưu tiên trong `MutablePropertySources`. Không in toàn bộ source object hoặc toàn bộ key/value trong production vì có thể chứa thông tin nhạy cảm.

### 10.2. Kiểm tra một key trong từng nguồn

~~~java
void inspectOneKey(
        ConfigurableEnvironment environment,
        String key
) {
    System.out.println("resolved value = "
            + environment.getProperty(key));

    for (PropertySource<?> source : environment.getPropertySources()) {
        Object value = source.getProperty(key);
        if (value != null) {
            System.out.printf(
                    "source=%s, contains key=%s%n",
                    source.getName(),
                    key
            );
        }
    }
}
~~~

Ví dụ này chỉ ghi tên nguồn có key, không ghi giá trị. Trong môi trường thử nghiệm có thể hiển thị giá trị để so sánh; với production, phải cẩn thận vì key có thể là secret.

Lưu ý: `getProperty` trên từng source không thực hiện toàn bộ quá trình placeholder resolution/conversion giống như `Environment.getProperty`. Nó giúp tìm nguồn trực tiếp chứa key, nhưng không phải lúc nào cũng xác định được origin cuối cùng nếu source là composite hoặc giá trị được tham chiếu gián tiếp.

### 10.3. Actuator `env` và origin tracking

Spring Boot Actuator có endpoint `env` để quan sát Environment và property source, nếu endpoint được bật và expose. Endpoint này có thể giúp xác định:

- Key có tồn tại hay không.
- Property source nào cung cấp giá trị.
- Giá trị nào đang được dùng sau khi áp dụng thứ tự ưu tiên.
- Origin/location của thuộc tính nếu nguồn hỗ trợ origin tracking.

Không expose endpoint này công khai. Giá trị nhạy cảm có thể được che theo cấu hình sanitization, nhưng cần xác thực, phân quyền và giới hạn mạng. Không dựa vào việc che mặc định để bảo vệ mọi loại secret tùy chỉnh.

## 11. Kiểm thử Environment và PropertySource

Kiểm thử giúp chứng minh nguồn ưu tiên, profile và binding hoạt động như mong đợi mà không cần kết nối Config Server hoặc registry thật trong mọi test.

### 11.1. Dùng MockEnvironment

Spring Test cung cấp `MockEnvironment` để tạo Environment có thể cấu hình trong test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.mock.env.MockEnvironment;

import static org.assertj.core.api.Assertions.assertThat;

class EnvironmentTest {

    @Test
    void resolvesPropertyFromMockEnvironment() {
        MockEnvironment environment = new MockEnvironment()
                .withProperty(
                        "clients.inventory.read-timeout",
                        "700ms"
                );

        assertThat(environment.getProperty(
                "clients.inventory.read-timeout"
        )).isEqualTo("700ms");
    }
}
~~~

`MockEnvironment` phù hợp cho unit test của component nhận `Environment`. Nếu test cần kiểm tra nhiều property sources và precedence, có thể thêm `MockPropertySource`.

### 11.2. Kiểm tra precedence

~~~java
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.core.env.MapPropertySource;
import org.springframework.mock.env.MockEnvironment;

import static org.assertj.core.api.Assertions.assertThat;

class PropertySourcePrecedenceTest {

    @Test
    void firstSourceWins() {
        MockEnvironment environment = new MockEnvironment();

        environment.getPropertySources().addFirst(
                new MapPropertySource(
                        "highPriority",
                        Map.of("app.mode", "production")
                )
        );

        environment.getPropertySources().addLast(
                new MapPropertySource(
                        "lowPriority",
                        Map.of("app.mode", "development")
                )
        );

        assertThat(environment.getProperty("app.mode"))
                .isEqualTo("production");
    }
}
~~~

Test này kiểm tra quy tắc first match wins của danh sách PropertySource. Nó không kiểm tra toàn bộ thứ tự property source mặc định của Spring Boot.

### 11.3. Kiểm tra profile

~~~java
@Test
void acceptsProductionProfile() {
    MockEnvironment environment = new MockEnvironment();
    environment.setActiveProfiles("prod", "cloud");

    assertThat(environment.acceptsProfiles(
            org.springframework.core.env.Profiles.of("prod & cloud")
    )).isTrue();
}
~~~

Test có thể bổ sung các trường hợp profile không hoạt động, biểu thức OR và phủ định. Với `@Profile` trên cấu hình, cần thêm test context để xác nhận bean được đăng ký/không được đăng ký theo profile.

### 11.4. Kiểm tra ứng dụng Spring Boot

Để kiểm thử cách Boot nạp Config Data, bind `@ConfigurationProperties` hoặc áp dụng auto-configuration, nên dùng `ApplicationContextRunner`, `@SpringBootTest` hoặc context test phù hợp. `MockEnvironment` đơn lẻ không tái hiện toàn bộ quá trình tìm file, xử lý profile và Config Data import của `SpringApplication`.

## 12. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách điều tra |
| --- | --- | --- |
| `getProperty` trả về `null` | Không có nguồn chứa key hoặc sai tên key | Liệt kê PropertySource, kiểm tra canonical name và Config Data |
| Giá trị khác với file YAML | Nguồn ưu tiên cao hơn ghi đè | Xem thứ tự nguồn và Actuator `env` |
| Profile không đúng | Active profile chưa được đặt hoặc bị override | Kiểm tra `getActiveProfiles()` và command line/environment |
| Thêm MapPropertySource nhưng giá trị không đổi | Nguồn được thêm bằng `addLast` hoặc key sai | Kiểm tra vị trí nguồn và tên key |
| Bean vẫn giữ giá trị cũ | Giá trị đã được đọc khi bean khởi tạo | Xem lifecycle, rebind và `@RefreshScope` |
| Config Server có dữ liệu nhưng client không thấy | Config Client không import, sai app/profile/label hoặc kết nối lỗi | Kiểm tra startup log, dependency, `spring.config.import` và Environment |
| Bean discovery không tồn tại | Thiếu provider/auto-configuration hoặc property điều kiện không đúng | Kiểm tra classpath, condition report và bean inventory |
| Test pass nhưng production sai | Test dùng MockEnvironment đơn giản, không tái hiện Config Data thực | Thêm integration test gần môi trường triển khai |

### 12.1. Phân biệt key không tồn tại và key có giá trị rỗng

`containsProperty(key)` kiểm tra có nguồn nào cung cấp key. Một key được khai báo với chuỗi rỗng có thể khác với key hoàn toàn không tồn tại. Khi dùng `getProperty`, cả hai trường hợp có thể cần được phân biệt theo yêu cầu nghiệp vụ.

Ví dụ, nếu một URL bắt buộc phải có giá trị không rỗng, chỉ dùng `containsProperty` chưa đủ. Cần validate chuỗi sau khi đọc hoặc dùng `@NotBlank` trong cấu hình có kiểu.

### 12.2. Placeholder có thể tham chiếu một nguồn khác

Giả sử:

~~~properties
app.region=ap-southeast-1
app.display-name=${spring.application.name}-${app.region}
~~~

Giá trị `app.display-name` có thể phụ thuộc vào một key từ property source khác. Khi điều tra, không chỉ xem source chứa key placeholder mà cần xem các key được tham chiếu và quá trình resolution.

### 12.3. Thứ tự PropertySource không phải thứ tự tạo bean

Property source precedence quyết định giá trị cấu hình được đọc. Thứ tự khởi tạo bean là một vấn đề khác, chịu ảnh hưởng bởi dependency graph, `@DependsOn`, configuration processing và lifecycle. Không dùng `addFirst` để giải quyết lỗi thứ tự tạo bean; hai khái niệm này không liên quan trực tiếp.

## 13. Quy ước thiết kế trong Spring Cloud Core

Khi xây dựng ứng dụng dùng các abstraction Spring Cloud, nên áp dụng các nguyên tắc:

1. Inject `Environment` khi cần đọc một số key động hoặc cần truy vấn profile.
2. Dùng `@ConfigurationProperties` cho nhóm cấu hình có cấu trúc, có validation và có nhiều consumer.
3. Chỉ dùng `ConfigurableEnvironment` trong bootstrap, integration hoặc test khi cần thay đổi danh sách nguồn/profile.
4. Đặt tên PropertySource rõ ràng và duy nhất để việc điều tra dễ dàng.
5. Chỉ dùng `addFirst` khi thật sự muốn override nguồn khác; default của thư viện thường nên có ưu tiên thấp.
6. Không xóa hoặc thay thế nguồn do Spring Boot/Spring Cloud tạo nếu không có lý do và test phù hợp.
7. Phân biệt cấu hình được nạp với bean đã được tạo, provider đã kết nối và hành vi runtime đã hoạt động.
8. Khi dùng Config Server, kiểm tra application name, profile, label, import và precedence theo đúng release train.
9. Khi thay đổi cấu hình runtime, xác định bean nào cần rebind/tạo lại và cơ chế refresh nào phát tín hiệu.
10. Không log toàn bộ giá trị cấu hình hoặc expose endpoint quản trị ra mạng không tin cậy.

## 14. Bài tập vận dụng

**Bài tập 1 — Tìm nguồn thắng.** Tạo ba `MapPropertySource` cùng chứa key `app.region`, lần lượt thêm bằng `addFirst`, `addLast` và `addBefore`. Ghi lại kết quả `Environment.getProperty` sau mỗi thao tác và giải thích thứ tự ưu tiên.

**Bài tập 2 — Profile expression.** Đặt active profiles là `prod` và `cloud`. Kiểm tra các biểu thức `prod`, `dev`, `prod & cloud`, `prod | staging` và `!test`. Nêu biểu thức nào được chấp nhận.

**Bài tập 3 — ConfigurableEnvironment.** Viết `ApplicationContextInitializer` thêm một `MapPropertySource` có key `clients.inventory.read-timeout`. Chứng minh giá trị này được ưu tiên hơn file `application.yml`, sau đó thử đổi `addFirst` thành `addLast`.

**Bài tập 4 — Thay đổi runtime.** Một bean giữ `URI baseUrl` trong constructor. Sau khi thêm property source mới vào Environment, hãy quan sát vì sao giá trị field không đổi. Đề xuất thiết kế phù hợp nếu yêu cầu nghiệp vụ cần cập nhật endpoint runtime.

**Bài tập 5 — Spring Cloud Config.** Dùng Config Client để lấy `clients.inventory.read-timeout` từ Config Server. Kiểm tra PropertySource từ xa, profile và giá trị cuối cùng. Thử tạo thêm một override từ biến môi trường và xác định nguồn nào thắng theo cấu hình đang dùng.

**Bài tập 6 — Chẩn đoán discovery.** Một ứng dụng đọc được `spring.cloud.discovery.enabled=true` nhưng không tra cứu được instance. Hãy tách các lớp bằng chứng: Environment có key, provider bean tồn tại, registry kết nối thành công và instance được trả về.

## 15. Ghi nhớ và nguồn tra cứu

- **`Environment`** là giao diện đọc thuộc tính và profile.
- **`ConfigurableEnvironment`** cho phép cấu hình profile và danh sách PropertySource.
- **`PropertySource`** đại diện cho một nguồn giá trị; nó không nhất thiết là file.
- **`MutablePropertySources`** sắp xếp nguồn theo ưu tiên; nguồn đầu tiên chứa key thường quyết định giá trị cuối cùng.
- Spring Boot đưa Config Data và các nguồn ngoài vào Environment; Spring Cloud Config Client tích hợp cấu hình từ xa vào cùng cơ chế.
- Thay đổi Environment không tự động cập nhật mọi object đã được tạo. Cần xem lifecycle, binding và refresh scope.
- Khi debug, hãy kiểm tra cả giá trị cuối cùng lẫn nguồn cung cấp nó.

Nguồn chính thức để đối chiếu theo phiên bản Spring Framework, Spring Boot và Spring Cloud của dự án:

1. [Spring Framework Reference – Environment Abstraction](https://docs.spring.io/spring-framework/reference/core/beans/environment.html)
2. [Spring Framework Javadoc – `Environment`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/env/Environment.html)
3. [Spring Framework Javadoc – `ConfigurableEnvironment`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/env/ConfigurableEnvironment.html)
4. [Spring Framework Javadoc – `PropertySource`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/env/PropertySource.html)
5. [Spring Framework Javadoc – `MutablePropertySources`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/env/MutablePropertySources.html)
6. [Spring Boot Reference – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
7. [Spring Cloud Config – Client Side Usage](https://docs.spring.io/spring-cloud-config/reference/client.html)
8. [Spring Cloud Context – Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)

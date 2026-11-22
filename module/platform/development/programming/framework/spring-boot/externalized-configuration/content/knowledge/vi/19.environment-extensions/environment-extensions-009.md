# Mở rộng Config Data qua ConfigDataLocationResolver và ConfigDataLoader

Spring Boot cho phép khai báo cấu hình qua file, biến môi trường, system properties, tham số dòng lệnh và các nguồn ngoài. Hệ thống **Config Data** được dùng khi Spring Boot nạp `application.yml`, `application.properties` và các tài nguyên nhập bằng `spring.config.import`. Nếu ứng dụng muốn hiểu một địa chỉ mới như `demo:orders` hoặc `acme-config:team/orders`, có thể mở rộng cơ chế này thông qua hai SPI:

- `ConfigDataLocationResolver<R>`: nhận dạng một địa chỉ và phân giải nó thành một hay nhiều `ConfigDataResource`.
- `ConfigDataLoader<R>`: nạp những resource đó, trả `ConfigData` chứa các Spring `PropertySource`.

Hai interface thuộc `org.springframework.boot.context.config`. Chúng chạy trong **giai đoạn bootstrap của Environment**, trước khi phần lớn bean Spring thông thường được tạo. Bài học dùng **Spring Boot 3.3.x và Java 21**, minh họa một extension hoàn chỉnh hỗ trợ `demo:orders`, resource theo profile, `optional:`, thứ tự ưu tiên, đăng ký bằng `spring.factories` và kiểm thử.

## 1. Bài toán: import dữ liệu từ một scheme mới

Ta muốn viết trong `application.yml`:

~~~yaml
spring:
  config:
    import: "demo:orders"
~~~

Nguồn cấu hình `demo:orders` giả sử cung cấp:

~~~properties
demo.feature.origin=orders
demo.feature.limit=25
~~~

Sau khi Spring Boot khởi động, ứng dụng có thể đọc:

~~~java
environment.getProperty("demo.feature.origin");
environment.getProperty("demo.feature.limit", Integer.class);
~~~

Hoặc bind vào một record:

~~~java
@ConfigurationProperties(prefix = "demo.feature")
public record DemoFeatureProperties(String origin, int limit) {
}
~~~

Spring Boot không biết scheme `demo:` nếu chúng ta chưa đăng ký resolver và loader. Cặp SPI tạo luồng:

~~~text
spring.config.import = demo:orders
            |
            v
   DemoConfigDataLocationResolver
            |
            v
    DemoConfigDataResource
            |
            v
       DemoConfigDataLoader
            |
            v
 ConfigData(MapPropertySource)
            |
            v
       Spring Environment
            |
            v
      @ConfigurationProperties
            |
            v
        Service / Component
~~~

Trong ví dụ, loader lấy dữ liệu từ Map có sẵn để tập trung vào API. Khi kết nối một kho từ xa, chỉ cần thay phần lấy dữ liệu trong loader bằng adapter thực tế, đồng thời bổ sung timeout, credential và xử lý lỗi.

## 2. Khi nào dùng hai SPI này?

Các trường hợp phù hợp:

- Import một cấu hình nằm trong remote configuration store.
- Hỗ trợ một prefix riêng như `myconfig:namespace/key`.
- Đọc nhiều lớp cấu hình theo tenant, nhóm ứng dụng hoặc profile.
- Biến response từ một API thành các property cho Environment.
- Đóng gói cơ chế import dùng chung trong một thư viện/starter.

Không cần custom resolver nếu chỉ muốn:

- Nhập YAML có sẵn qua `spring.config.import=optional:file:./extra.yml`.
- Đọc các file trong Kubernetes volume qua `configtree:`.
- Chuyển giá trị String thành enum hoặc kiểu nghiệp vụ bằng Converter.
- Bind nhóm thuộc tính bằng `@ConfigurationProperties`.
- Kiểm tra số worker lớn hơn 0 bằng Bean Validation.
- Quan sát callback của Binder bằng `BindHandler`.

Bảng trách nhiệm:

| Thành phần | Mục đích |
| --- | --- |
| `ConfigDataLocation` | Địa chỉ người dùng khai báo, ví dụ `demo:orders` |
| `ConfigDataLocationResolver` | Kiểm tra scheme và tạo resource |
| `ConfigDataResource` | Đại diện nguồn cụ thể cần tải |
| `ConfigDataLoader` | Đọc resource rồi tạo ConfigData |
| `ConfigData` | Chứa những PropertySource được nạp |
| `@ConfigurationProperties` | Sử dụng property đã có trong Environment |
| `PropertySourceLoader` | Hỗ trợ đọc định dạng file chuẩn theo cơ chế tương ứng |

Điểm quan trọng: **resolver không nhất thiết phải tải dữ liệu**. Nó chủ yếu chuyển một địa chỉ thành resource. Loader mới thực hiện việc lấy và xây dựng PropertySource.

## 3. ConfigDataLocation: địa chỉ và optional

`ConfigDataLocation` là object bọc địa chỉ import:

~~~text
demo:orders
optional:demo:orders
file:./extra.yml
classpath:/default.properties
configtree:/etc/secrets/
~~~

Các method hữu ích:

~~~java
location.hasPrefix("demo:");
location.getNonPrefixedValue("demo:");
location.getValue();
location.isOptional();
~~~

`hasPrefix` nhận diện scheme, `getNonPrefixedValue` lấy phần còn lại sau prefix, còn `isOptional` cho biết người dùng khai báo location có thể không tồn tại.

Ví dụ:

~~~text
Location: optional:demo:orders
Prefix:   demo:
Name:     orders
Optional: true
~~~

Spring Boot tách prefix `optional:` trước khi xét `getValue()`. Tuy nhiên, **optional không có nghĩa bỏ qua tất cả exception**; đó là một chính sách cho lỗi Config Data không tìm thấy.

## 4. ConfigDataResource: định danh ổn định

Một resource là dữ liệu trung gian giữa resolver và loader. Nó có thể chứa ID tài liệu, namespace, profile hoặc location đã chuẩn hóa.

Subclass của `ConfigDataResource` cần triển khai `equals`, `hashCode`, `toString` hợp lệ. Điều này hỗ trợ phát hiện hai resource cùng đại diện một nguồn, tránh xử lý lặp và tạo thông tin chẩn đoán rõ ràng.

Không nên lưu secret trong `toString()` vì exception hoặc log bootstrap có thể hiển thị chuỗi đó.

Trong ví dụ, resource chỉ cần tên và trạng thái optional.

## 5. Cấu trúc dự án

~~~text
config-data-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/configdemo/
    │   ├── ConfigDataDemoApplication.java
    │   ├── config/DemoFeatureProperties.java
    │   └── configdata/
    │       ├── DemoConfigDataResource.java
    │       ├── DemoConfigDataLocationResolver.java
    │       └── DemoConfigDataLoader.java
    └── resources/
        ├── application.yml
        └── META-INF/spring.factories
~~~

Với ứng dụng Spring Boot thông thường, các SPI đã nằm trong dependency Spring Boot cơ bản:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter</artifactId>
</dependency>
~~~

Giả định dự án đang sử dụng Maven parent/BOM quản lý Spring Boot 3.3.x, Java 21 và plugin build thích hợp.

## 6. Bước 1: tạo DemoConfigDataResource

Tạo `DemoConfigDataResource.java`:

~~~java
package com.example.configdemo.configdata;

import java.util.Objects;

import org.springframework.boot.context.config.ConfigDataResource;

public final class DemoConfigDataResource extends ConfigDataResource {

    private final String name;
    private final boolean optional;

    public DemoConfigDataResource(String name, boolean optional) {
        super(optional);
        this.name = Objects.requireNonNull(name, "name");
        this.optional = optional;
    }

    public String name() {
        return name;
    }

    public boolean optional() {
        return optional;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof DemoConfigDataResource that)) {
            return false;
        }
        return optional == that.optional
                && name.equals(that.name);
    }

    @Override
    public int hashCode() {
        return Objects.hash(name, optional);
    }

    @Override
    public String toString() {
        return (optional ? "optional:" : "") + "demo:" + name;
    }
}
~~~

`super(optional)` truyền trạng thái optional cho lớp nền Spring Boot. Thuộc tính `name` có thể là `orders` hoặc `orders@dev`, còn `optional` phục vụ xử lý nguồn vắng mặt.

`optional()` trong ví dụ là getter của class demo, không phải giả định rằng lớp nền bắt buộc có getter public như vậy. Trong hệ thống thật, nên dùng ID tài nguyên không chứa password hoặc token.

## 7. Bước 2: viết ConfigDataLocationResolver

Tạo `DemoConfigDataLocationResolver.java`:

~~~java
package com.example.configdemo.configdata;

import java.util.List;

import org.springframework.boot.context.config.ConfigDataLocation;
import org.springframework.boot.context.config.ConfigDataLocationResolver;
import org.springframework.boot.context.config.ConfigDataLocationResolverContext;
import org.springframework.boot.context.config.Profiles;

public final class DemoConfigDataLocationResolver
        implements ConfigDataLocationResolver<DemoConfigDataResource> {

    private static final String PREFIX = "demo:";

    @Override
    public boolean isResolvable(
            ConfigDataLocationResolverContext context,
            ConfigDataLocation location) {

        return location.hasPrefix(PREFIX);
    }

    @Override
    public List<DemoConfigDataResource> resolve(
            ConfigDataLocationResolverContext context,
            ConfigDataLocation location) {

        String name = readName(location);
        return List.of(
                new DemoConfigDataResource(name, location.isOptional()));
    }

    @Override
    public List<DemoConfigDataResource> resolveProfileSpecific(
            ConfigDataLocationResolverContext context,
            ConfigDataLocation location,
            Profiles profiles) {

        String name = readName(location);

        // Các biến thể profile là tùy chọn trong demo.
        return profiles.getAccepted().stream()
                .map(profile -> new DemoConfigDataResource(
                        name + "@" + profile, true))
                .toList();
    }

    private static String readName(ConfigDataLocation location) {
        String name = location.getNonPrefixedValue(PREFIX);

        if (!name.matches("[a-z][a-z0-9-]*")) {
            throw new IllegalArgumentException(
                    "Invalid demo config name: " + name);
        }
        return name;
    }
}
~~~

### isResolvable nhận diện scheme

Với `demo:orders`, method trả true. Với `optional:demo:orders`, `ConfigDataLocation` đã nhận diện optional nên `hasPrefix("demo:")` cũng nhận đúng scheme.

Với `file:./extra.yml` hoặc `classpath:/default.properties`, resolver trả false. Một resolver không nên claim tất cả location rồi tự cố gắng phân giải; khi có nhiều resolver, Spring Boot chọn implementation đầu tiên hỗ trợ location theo thứ tự resolver.

### resolve tạo một resource cơ bản

`resolve(...)` chuyển `demo:orders` thành `DemoConfigDataResource("orders", false)`.

Nó **chưa tạo PropertySource**. Dữ liệu sẽ được load sau. Nếu một location tạo nhiều resource, thứ tự danh sách phải theo **ưu tiên tăng dần** để những lớp cấu hình cao hơn có thể ghi đè nguồn thấp hơn.

### resolveProfileSpecific tạo các biến thể

Trong ví dụ, `orders@dev` hoặc `orders@prod` là hai tên do ứng dụng tự quy ước. Spring Boot không tự phát minh quy ước đó cho mọi custom scheme.

`Profiles.getAccepted()` cung cấp danh sách profile được chấp nhận trong quá trình Config Data, bao gồm thông tin active/default phù hợp. Không nên đọc `System.getenv("SPRING_PROFILES_ACTIVE")` rồi tự kết luận nó là toàn bộ thông tin profile.

Nếu không override `resolveProfileSpecific`, implementation mặc định của interface trả danh sách rỗng: extension sẽ không tự tạo resource theo profile.

### Vì sao profile resource optional?

Ví dụ coi `orders` là dữ liệu gốc bắt buộc, còn `orders@dev` và `orders@prod` có thể vắng mặt. Vì vậy resolver đặt cờ optional=true cho biến thể.

Với một hệ thống thật, nếu mỗi môi trường bắt buộc phải có dữ liệu riêng, cần thiết kế chính sách khác. Không mặc định biến mọi tài nguyên theo profile thành optional mà không có yêu cầu nghiệp vụ.

## 8. Bước 3: viết ConfigDataLoader

Tạo `DemoConfigDataLoader.java`:

~~~java
package com.example.configdemo.configdata;

import java.io.IOException;
import java.util.List;
import java.util.Map;

import org.springframework.boot.context.config.ConfigData;
import org.springframework.boot.context.config.ConfigDataLoader;
import org.springframework.boot.context.config.ConfigDataLoaderContext;
import org.springframework.boot.context.config.ConfigDataResourceNotFoundException;
import org.springframework.core.env.MapPropertySource;

public final class DemoConfigDataLoader
        implements ConfigDataLoader<DemoConfigDataResource> {

    @Override
    public ConfigData load(
            ConfigDataLoaderContext context,
            DemoConfigDataResource resource) throws IOException {

        Map<String, Object> values = switch (resource.name()) {
            case "orders" -> Map.of(
                    "demo.feature.origin", "orders",
                    "demo.feature.limit", "25");
            case "orders@dev" -> Map.of(
                    "demo.feature.limit", "5");
            case "orders@prod" -> Map.of(
                    "demo.feature.limit", "100");
            case "billing" -> Map.of(
                    "demo.feature.origin", "billing",
                    "demo.feature.limit", "40");
            default -> null;
        };

        if (values == null) {
            throw new ConfigDataResourceNotFoundException(resource);
        }

        MapPropertySource source = new MapPropertySource(
                "demoConfigData[" + resource.name() + "]",
                values);

        return new ConfigData(List.of(source));
    }
}
~~~

Với `orders`, loader trả các property:

~~~text
demo.feature.origin = orders
demo.feature.limit  = 25
~~~

Với `orders@dev`, nó chỉ trả:

~~~text
demo.feature.limit  = 5
~~~

Khi bản dev được xử lý như profile-specific Config Data, nó có thể ghi đè `limit` của bản cơ bản, trong khi `origin` vẫn đến từ `orders`.

### isLoadable

`ConfigDataLoader` có method default `isLoadable(ConfigDataLoaderContext, R)`. Với resource riêng `DemoConfigDataResource` và một loader duy nhất, không cần override. Nếu nhiều loader claim cùng resource, sẽ xung đột; Javadoc yêu cầu không có nhiều loader đồng thời nhận một resource.

### MapPropertySource và ConfigData

`MapPropertySource` là một implementation `PropertySource` để biểu diễn key-value. Loader có thể trả một hoặc nhiều PropertySource thông qua `ConfigData`.

Danh sách property sources trong một `ConfigData` được tài liệu yêu cầu theo **thứ tự ưu tiên tăng dần**: source xuất hiện sau có thể thắng nếu có key trùng với source trước.

### Khi tài nguyên không tồn tại

Loader ném:

~~~java
throw new ConfigDataResourceNotFoundException(resource);
~~~

Đây là cách cho biết một resource đã được phân giải nhưng không tìm thấy. `optional:` chỉ có ý nghĩa rõ ràng khi lỗi được phân loại theo nhóm Config Data not-found.

Không biến mọi exception từ HTTP, database hay parse JSON thành not-found: nếu backend trả 401/403 hoặc dữ liệu sai cú pháp, ứng dụng cần thông báo lỗi phù hợp.

## 9. Bước 4: đăng ký SPI bằng spring.factories

Tạo file:

~~~text
src/main/resources/META-INF/spring.factories
~~~

Nội dung:

~~~properties
org.springframework.boot.context.config.ConfigDataLocationResolver=com.example.configdemo.configdata.DemoConfigDataLocationResolver
org.springframework.boot.context.config.ConfigDataLoader=com.example.configdemo.configdata.DemoConfigDataLoader
~~~

Các implementation trong ví dụ có constructor không tham số để Spring Boot tạo qua factory mechanism.

**Lưu ý Spring Boot 3.x:** các auto-configuration classes thường được khai báo trong `AutoConfiguration.imports`, nhưng hai SPI Config Data vẫn được đăng ký bằng **`META-INF/spring.factories`**. Không di chuyển hai entry sang `AutoConfiguration.imports`.

Chỉ gắn `@Component` không phải cách đủ để đăng ký resolver/loader: chúng cần chạy trước khi application context thông thường hoàn tất component scan và tạo bean.

## 10. Bước 5: dùng import và bind dữ liệu

File `application.yml`:

~~~yaml
spring:
  config:
    import: "demo:orders"

demo:
  feature:
    limit: 10
~~~

Spring Boot đọc location, gọi resolver, gọi loader rồi đóng góp PropertySource. Theo quy tắc Config Data, **document được import có thể ghi đè document khai báo import**, nên `limit=25` từ `demo:orders` sẽ được ưu tiên so với `limit=10` trong chính document trên, giả định không có nguồn khác ưu tiên cao hơn.

Tạo `DemoFeatureProperties.java`:

~~~java
package com.example.configdemo.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo.feature")
public record DemoFeatureProperties(String origin, int limit) {
}
~~~

Tạo application class:

~~~java
package com.example.configdemo;

import com.example.configdemo.config.DemoFeatureProperties;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ConfigDataDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigDataDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner showConfig(DemoFeatureProperties properties) {
        return args -> System.out.println(
                "origin=" + properties.origin()
                        + ", limit=" + properties.limit());
    }
}
~~~

Chạy:

~~~bash
./mvnw spring-boot:run
~~~

Kết quả dự kiến:

~~~text
origin=orders, limit=25
~~~

`@ConfigurationProperties` bind giá trị sau khi Config Data đã đóng góp property vào Environment; nó không phải cơ chế tìm resolver.

## 11. Kết quả khi dùng profile

Thử:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.arguments="--spring.profiles.active=dev"
~~~

Resolver có thể tạo thêm resource `orders@dev`, loader trả `limit=5`:

~~~text
origin=orders, limit=5
~~~

Tương tự:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.arguments="--spring.profiles.active=prod"
~~~

Resource `orders@prod` trả `limit=100`:

~~~text
origin=orders, limit=100
~~~

Kết quả dự kiến giả định những resource được nạp theo quy tắc priority của Config Data, không có CLI, environment variable hoặc nguồn ưu tiên cao hơn thay `demo.feature.limit`.

Với profile `staging` mà kho demo không có `orders@staging`, resource profile-specific được đánh dấu optional, nên lỗi resource đó không tồn tại có thể được bỏ qua, để lại giá trị gốc `limit=25`.

### Nhiều active profiles

Khi có profile `prod,live`, thứ tự và danh sách resource theo profile có thể ảnh hưởng giá trị cuối. Nếu extension phân giải nhiều resource, hãy tuân thủ quy tắc **ưu tiên tăng dần** của API và kiểm thử thứ tự với các profile được hỗ trợ.

Đừng dựa vào thứ tự iteration ngẫu nhiên của Map hoặc tự đổi active profile khi loader đang nạp dữ liệu theo profile.

## 12. Optional và missing resource

So sánh:

~~~properties
spring.config.import=demo:missing
~~~

với:

~~~properties
spring.config.import=optional:demo:missing
~~~

Trong ví dụ, `missing` không tồn tại:

- Import bắt buộc thường khiến ứng dụng dừng với lỗi Config Data resource không tìm thấy.
- Import optional có thể bỏ qua missing resource và tiếp tục startup nếu những điều kiện còn lại cho phép.

Bảng phân biệt:

| Lỗi | Có nên xử lý như missing resource? |
| --- | --- |
| Tài liệu/tập cấu hình không tồn tại | Có |
| HTTP 404 có nghĩa namespace không tồn tại | Có, theo hợp đồng API |
| HTTP 401/403 | Không, đây là lỗi xác thực/quyền |
| HTTP 500/503 | Không, đây là lỗi hạ tầng |
| Timeout | Không tự biến thành not-found |
| JSON/YAML sai cú pháp | Không, đây là lỗi dữ liệu |
| Location sai format | Không nên bỏ qua như một missing hợp lệ |

`optional:` không tự bảo đảm các property mà bean cần sẽ tồn tại. Nếu bean đánh dấu `@NotNull` hoặc `@NotBlank`, việc thiếu import optional vẫn có thể làm validation thất bại.

## 13. Thứ tự ưu tiên của nhiều import

Ví dụ:

~~~yaml
spring:
  config:
    import:
      - "demo:orders"
      - "demo:billing"
~~~

Trong loader:

~~~text
orders  → origin=orders,  limit=25
billing → origin=billing, limit=40
~~~

Theo cách xử lý import, location sau có thể có ưu tiên cao hơn đối với key trùng. Kết quả có thể là `origin=billing, limit=40` nếu không có nguồn cao hơn khác.

Với nhiều PropertySource trong một `ConfigData`:

~~~java
new ConfigData(List.of(
        new MapPropertySource("defaults", defaults),
        new MapPropertySource("overrides", overrides)));
~~~

Đặt nguồn thấp trước và nguồn cao sau; đây là quy tắc được nêu trong API `ConfigData`.

### Tương tác với environment và CLI

Config Data là một nhóm trong thứ tự `PropertySource` của Spring Boot. Các nguồn như biến môi trường, system property và tham số dòng lệnh thường có thể ghi đè giá trị Config Data.

Ví dụ:

~~~bash
java -jar app.jar --demo.feature.limit=200
~~~

Với CLI ghi đè, giá trị cuối có thể là 200 dù loader cung cấp 25.

## 14. ResolverContext trong bootstrap

`ConfigDataLocationResolverContext` có các method:

~~~java
context.getBinder();
context.getBootstrapContext();
context.getParent();
~~~

- `getBinder()` cung cấp Binder để đọc những giá trị **đã được đóng góp trước đó** trong quá trình nạp Config Data. Không được giả định mọi property của ứng dụng đã sẵn sàng.
- `getBootstrapContext()` cung cấp bootstrap context chia sẻ, hữu ích khi client kết nối nguồn ngoài tốn chi phí tạo.
- `getParent()` cung cấp resource cha đã kích hoạt một resolve, hoặc null nếu không có. Nó có thể giúp xử lý import tương đối theo resource cha.

Tránh vòng phụ thuộc:

~~~text
Muốn nạp remote:orders cần app.remote.token
Nhưng app.remote.token chỉ có trong remote:orders
=> bootstrap chưa có token để đọc resource
~~~

Nên cung cấp credential từ nguồn đã sẵn có trước, như environment/secret bootstrap thích hợp.

## 15. LoaderContext và đối tượng khởi động

`ConfigDataLoader.load(...)` nhận `ConfigDataLoaderContext`. Ví dụ in-memory không dùng context vì không có tài nguyên dùng chung.

Javadoc cho phép một số constructor parameters được hỗ trợ trong resolver/loader như `DeferredLogFactory` và `ConfigurableBootstrapContext`; resolver còn có thể dùng `Binder` hoặc `ResourceLoader` trong phạm vi hỗ trợ của API.

Không inject một `@Service` hoặc JPA repository thông thường vào loader và kỳ vọng nó đã tồn tại. Quá trình Config Data chạy trước khi phần lớn runtime bean được tạo, trong khi datasource hoặc service đó có thể lại cần chính những property do loader cung cấp.

Một remote client ở bootstrap nên là đối tượng nhẹ, có timeout và lifecycle được kiểm soát.

## 16. Xây loader thực tế cho remote configuration

Khi dùng HTTP/API, quy trình gợi ý:

~~~text
1. Nhận resource với namespace và profile.
2. Lấy endpoint/credential từ cấu hình bootstrap có sẵn.
3. Gửi request với timeout hữu hạn.
4. Phân loại 404, 401, 403, 429, 5xx.
5. Retry có giới hạn cho lỗi phù hợp.
6. Parse payload và validate schema.
7. Chuyển payload sang Map<String, Object>.
8. Tạo MapPropertySource với tên nguồn rõ ràng.
9. Trả ConfigData để Spring Boot đưa vào Environment.
~~~

Pseudo-code minh họa (các class RemoteDocument, remoteClient, validateAndFlatten là class tự thiết kế, **không phải Spring Boot API có sẵn**):

~~~java
public ConfigData load(
        ConfigDataLoaderContext context,
        RemoteConfigDataResource resource) throws IOException {

    RemoteDocument doc =
            remoteClient.fetch(resource.identifier());

    if (doc == null) {
        throw new ConfigDataResourceNotFoundException(resource);
    }

    Map<String, Object> values =
            validateAndFlatten(doc);

    return new ConfigData(List.of(
            new MapPropertySource(
                    "remote[" + resource.identifier() + "]",
                    values)));
}
~~~

Những yêu cầu thiết kế cần có:

- Không log token, password hoặc toàn bộ nội dung nhạy cảm.
- Đặt timeout và retry hữu hạn để không treo startup.
- Không đổi mọi lỗi remote thành not-found.
- Có giới hạn kích thước payload và số lượng key.
- Kiểm tra schema trước khi cung cấp property.
- Ghi origin hoặc version không nhạy cảm để truy vết.
- Quy định thứ tự ưu tiên khi nhiều lớp remote config cùng có một key.
- Đảm bảo key không bị trùng hoặc bị flatten sai.
- Xem xét cache/bootstrap sharing với `ConfigurableBootstrapContext`.
- Không tự động reload bean chỉ vì remote store thay đổi.

### Nguồn bí mật

Nếu backend cung cấp secret, không nên in toàn bộ PropertySource khi debug. Resource `toString` cũng phải chỉ chứa ID không nhạy cảm. Những endpoint quan sát như Actuator cần được bảo vệ quyền truy cập.

## 17. Config Data không phải hot reload

Một ứng dụng thông thường:

~~~text
Khởi động
  → chuẩn bị Environment
  → xử lý Config Data imports
  → tạo ApplicationContext
  → bind @ConfigurationProperties
  → tạo bean và chạy nghiệp vụ
~~~

Resolver/loader chạy trong giai đoạn nạp dữ liệu. Khi dữ liệu remote thay đổi sau startup, Spring Boot không mặc định nạp lại mọi Config Data resource rồi xây lại các bean `@ConfigurationProperties`.

Nếu cần refresh runtime, phải thiết kế cơ chế riêng với tính nhất quán, đồng bộ, xử lý lỗi và quyền truy cập phù hợp. Đừng dùng loader như một vòng polling chạy nền.

## 18. Lỗi thường gặp

### Sai spring.factories

File sai tên, nằm sai thư mục hoặc dùng sai tên class khiến Spring Boot không phát hiện implementation. Cần đúng `META-INF/spring.factories` và hai key interface đầy đủ.

### isResolvable quá rộng

Nếu resolver nhận mọi địa chỉ, nó có thể tranh chấp với `file:`, `classpath:` hoặc `configtree:`. Hãy chỉ nhận prefix riêng mà extension thực sự hỗ trợ.

### Resource không có equals/hashCode

Resource không có equality ổn định có thể gây xử lý trùng không mong muốn khi cùng một import xuất hiện nhiều lần.

### Không giữ trạng thái optional

Nếu `location.isOptional()` không được đưa vào resource cơ bản, một missing location có thể không được xử lý theo kỳ vọng.

### Không triển khai resolveProfileSpecific

Phương thức mặc định trả danh sách rỗng; Spring Boot không tự tạo profile variants cho scheme mới.

### Dùng exception sai

Resource không tồn tại dùng not-found exception thích hợp; lỗi HTTP 403 hay dữ liệu sai format phải có ngữ nghĩa khác. Không nuốt lỗi chỉ để app khởi động.

### Sai thứ tự nguồn

Nhiều resource/property sources phải theo ưu tiên tăng dần. Nếu đảo thứ tự, giá trị cuối có thể trái hợp đồng.

### Đọc bean runtime ở bootstrap

Đừng phụ thuộc vào JPA repository hoặc service chưa được tạo trong constructor loader.

### Lộ secret qua log

Không in result map hay resource có credential. Chỉ log tên nguồn và loại lỗi phù hợp.

### Nhầm kết quả import với giá trị cuối

CLI hoặc environment có thể có ưu tiên cao hơn Config Data. Quan sát property hiệu lực thay vì chỉ kiểm tra loader trả gì.

## 19. Kiểm tra khi chạy

Sau khi tạo các class và `spring.factories`:

~~~bash
./mvnw clean package
java -jar target/config-data-demo.jar
~~~

Tên JAR chỉ là ví dụ. Dùng artifact thực tế sau build.

Thử profile:

~~~bash
java -jar target/config-data-demo.jar --spring.profiles.active=dev
java -jar target/config-data-demo.jar --spring.profiles.active=prod
~~~

Thử import `demo:missing` và `optional:demo:missing` bằng cách sửa file hoặc tham số config phù hợp. Đối chiếu lỗi startup và giá trị của `DemoFeatureProperties`.

Để quan sát chi tiết trong môi trường phát triển:

~~~bash
java -jar target/config-data-demo.jar --logging.level.org.springframework.boot.context.config=TRACE
~~~

Không bật TRACE tràn lan trong production khi log có thể gây quá tải hoặc lộ thông tin cấu hình.

Kiểm tra file đăng ký nằm trong JAR:

~~~bash
jar tf target/config-data-demo.jar
~~~

Với Spring Boot executable JAR, `spring.factories` của ứng dụng thường nằm ở `BOOT-INF/classes/META-INF/spring.factories`; với library JAR thường ở `META-INF/spring.factories`.

## 20. Unit test resolver/loader

Dùng JUnit, AssertJ, Mockito qua `spring-boot-starter-test`:

~~~java
package com.example.configdemo.configdata;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;

import java.util.List;
import org.junit.jupiter.api.Test;

import org.springframework.boot.context.config.ConfigData;
import org.springframework.boot.context.config.ConfigDataLoaderContext;
import org.springframework.boot.context.config.ConfigDataLocation;
import org.springframework.boot.context.config.ConfigDataLocationResolverContext;

class DemoConfigDataSpiTest {

    @Test
    void recognizesDemoPrefix() {
        var resolver = new DemoConfigDataLocationResolver();
        var context = mock(ConfigDataLocationResolverContext.class);

        assertThat(resolver.isResolvable(
                context,
                ConfigDataLocation.of("demo:orders"))).isTrue();

        assertThat(resolver.isResolvable(
                context,
                ConfigDataLocation.of("file:./extra.yml"))).isFalse();
    }

    @Test
    void resolvesResource() {
        var resolver = new DemoConfigDataLocationResolver();
        var context = mock(ConfigDataLocationResolverContext.class);

        List<DemoConfigDataResource> resources =
                resolver.resolve(
                        context, ConfigDataLocation.of("demo:orders"));

        assertThat(resources).hasSize(1);
        assertThat(resources.get(0).name()).isEqualTo("orders");
        assertThat(resources.get(0).optional()).isFalse();
    }

    @Test
    void loadsProperties() throws Exception {
        var loader = new DemoConfigDataLoader();
        var context = mock(ConfigDataLoaderContext.class);

        ConfigData data = loader.load(
                context,
                new DemoConfigDataResource("orders", false));

        assertThat(data.getPropertySources()).hasSize(1);
        assertThat(data.getPropertySources().get(0)
                .getProperty("demo.feature.limit"))
                .isEqualTo("25");
    }
}
~~~

Unit test kiểm tra đúng các method mà implementation cung cấp, nhưng không tự chứng minh Spring Boot đã discover `spring.factories`.

Cần thêm integration test khởi động ứng dụng thật với `spring.config.import=demo:orders`, kiểm tra profile/optional/priority và xử lý lỗi startup theo đúng thời điểm Config Data.

## 21. Các tình huống integration test nên có

| Tình huống | Kỳ vọng |
| --- | --- |
| `spring.config.import=demo:orders` | `origin=orders`, `limit=25` |
| YAML cùng document đặt `limit=10` | Import có thể ghi đè thành 25 |
| Active profile dev | `limit=5` từ `orders@dev` |
| Active profile prod | `limit=100` từ `orders@prod` |
| Import bắt buộc bị thiếu | Startup lỗi not-found |
| Import optional bị thiếu | Có thể bỏ qua missing resource |
| CLI `--demo.feature.limit=200` | CLI có thể ghi đè import |
| Không có resolver trong `spring.factories` | Scheme không được nhận |
| Property sai kiểu ở nguồn | Lỗi khi Binder tiêu thụ property |
| 403 từ remote API | Không nên bị xem là not-found |
| Hai import cùng key | Giá trị cuối theo thứ tự ưu tiên |

Đừng chỉ kiểm tra object Map do loader tạo. Kiểm tra cả **giá trị hiệu lực trong Environment** và bean đã bind.

## 22. Câu hỏi thực hành

### Bài 1 — Chia trách nhiệm

Một nhóm muốn hỗ trợ `vaultlike:team-a/orders`. Thành phần nào nhận scheme, thành phần nào thực hiện HTTP request, thành phần nào giữ ID resource?

**Đáp án:** resolver, loader và resource tương ứng.

### Bài 2 — Optional

Tại sao `optional:demo:missing` có thể được bỏ qua trong khi `demo:missing` gây lỗi?

**Đáp án:** cờ optional được truyền vào resource và Spring Boot xử lý exception not-found theo chính sách tương ứng.

### Bài 3 — Profile

Thêm case `orders@staging` trả `limit=50` vào loader và chạy với `staging`; giải thích kết quả ưu tiên so với base.

### Bài 4 — Thứ tự nguồn

Nhập `demo:orders` rồi `demo:billing`, cả hai cung cấp `demo.feature.limit`. Dự đoán giá trị khi không có nguồn khác ghi đè.

### Bài 5 — Sai loại lỗi

Remote API trả 403. Có nên đổi thành `ConfigDataResourceNotFoundException` chỉ để `optional:` cho phép khởi động?

**Đáp án:** không; lỗi quyền truy cập không đồng nghĩa tài nguyên không tồn tại.

### Bài 6 — Bootstrap

Resolver cần token chỉ được cung cấp bởi chính resource chưa tải. Hãy giải thích vòng phụ thuộc và tìm một nguồn credential được bootstrap sớm hơn.

### Bài 7 — Resource equality

Tại sao hai instance `DemoConfigDataResource("orders", false)` nên so sánh bằng nhau? Trả lời dựa trên vai trò nhận diện tài nguyên và khử trùng lặp.

### Bài 8 — Chọn cơ chế

Chỉ cần chuyển String `"apac"` sang `RegionCode("APAC")`. Có cần Config Data SPI không?

**Đáp án:** không; chỉ cần converter phù hợp cho configuration binding.

## 23. Tổng kết

`ConfigDataLocationResolver` và `ConfigDataLoader` là hai điểm mở rộng cho **nguồn Config Data mới** trong Spring Boot. Resolver chuyển một location thành resource; loader nạp resource và trả ConfigData với PropertySource. Spring Boot xử lý các property đó trong Environment, còn bean ứng dụng đọc qua `@Value` hoặc `@ConfigurationProperties`.

Các nguyên tắc cốt lõi:

- Đăng ký hai implementation qua `META-INF/spring.factories` trong Spring Boot 3.3.
- Giữ resource identity ổn định và không lộ secret.
- Giữ thứ tự ưu tiên rõ ràng khi có nhiều resource hoặc PropertySource.
- Tự định nghĩa cơ chế profile-specific nếu custom scheme cần nó.
- Sử dụng `optional:` đúng cho missing resource, không che lỗi bảo mật hoặc parse.
- Hạn chế dependency ở bootstrap, đặt timeout và xử lý lỗi cho remote config.
- Kiểm thử unit riêng cho resolver/loader và integration test cho discovery, import, profile, priority.

## Tài liệu tham khảo

- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [ConfigDataLocationResolver API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/config/ConfigDataLocationResolver.html)
- [ConfigDataLoader API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/config/ConfigDataLoader.html)
- [ConfigDataResource API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/config/ConfigDataResource.html)
- [ConfigData API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/config/ConfigData.html)
- [ConfigDataLocation API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/config/ConfigDataLocation.html)
- [Profiles API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/config/Profiles.html)

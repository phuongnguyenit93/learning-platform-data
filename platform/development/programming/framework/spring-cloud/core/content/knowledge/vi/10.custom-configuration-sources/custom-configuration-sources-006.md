# Gộp nhiều nguồn bằng `CompositePropertySource`

Trong ứng dụng Spring, một thuộc tính có thể được cung cấp từ nhiều nơi: file cấu hình, biến môi trường, tham số khởi chạy, cấu hình theo tenant, kho cấu hình trung tâm hoặc dịch vụ quản lý secret. Khi một integration cần gom một số nguồn thành một nhóm và kiểm soát thứ tự ưu tiên giữa chúng, Spring Framework cung cấp **`CompositePropertySource`**.

`CompositePropertySource` là một `PropertySource` tổng hợp. Nó giữ nhiều `PropertySource` con và tra cứu lần lượt theo thứ tự đã sắp xếp. Với một key, **nguồn con đầu tiên trả về giá trị khác `null` sẽ quyết định kết quả**. Nhờ đó, ứng dụng có thể biểu diễn một nhóm nguồn cấu hình như một nguồn duy nhất khi đưa vào `Environment`.

Bài học thuộc chương **Nguồn cấu hình tùy biến** của module **SPRING_CLOUD_CORE**. Người học sẽ thực hành cách gộp nguồn cấu hình bằng API Spring Framework, điều khiển ưu tiên nội bộ và ưu tiên toàn cục, tích hợp vào `ConfigurableEnvironment`, kiểm thử và hiểu giới hạn khi dùng cùng Spring Cloud Config hoặc cơ chế refresh.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích vai trò của `CompositePropertySource` và mối quan hệ với `PropertySource`.
2. Tạo một composite chứa nhiều nguồn cấu hình và xác định nguồn thắng khi trùng key.
3. Phân biệt thứ tự ưu tiên **bên trong composite** với thứ tự của composite trong `MutablePropertySources`.
4. Kết hợp nguồn mặc định, nguồn theo tenant và nguồn override có kiểm soát.
5. Phân tích việc liệt kê property names khi một nguồn con không hỗ trợ enumeration.
6. Đưa composite vào `Environment` ở đúng giai đoạn khởi tạo.
7. Kiểm thử precedence, trường hợp key thiếu và hành vi khi có nhiều nguồn trùng tên.
8. Phân biệt việc gom nguồn với việc tải dữ liệu từ xa, cache, refresh và đồng bộ cấu hình.

## 2. `CompositePropertySource` là gì?

`PropertySource<T>` là abstraction đại diện cho một nguồn cung cấp thuộc tính. Một nguồn thường có tên và đối tượng dữ liệu nền. Ví dụ:

- `MapPropertySource`: đọc từ `Map<String, Object>`.
- `PropertiesPropertySource`: đọc từ `Properties`.
- `SystemEnvironmentPropertySource`: đọc từ biến môi trường.
- `ResourcePropertySource`: đọc từ resource.
- Một `PropertySource` tùy biến: đọc từ API hoặc kho dữ liệu do ứng dụng tích hợp.

`CompositePropertySource` kế thừa `EnumerablePropertySource<Object>` và chứa một tập hợp các `PropertySource` con. Nó cung cấp một tên cho toàn bộ nhóm, đồng thời thực hiện tra cứu trên từng nguồn con.

~~~mermaid
flowchart TD
    E[Environment] --> M[CompositePropertySource: applicationSources]
    M --> A[tenantOverrides]
    M --> B[centralConfig]
    M --> C[platformDefaults]
    A --> V1[Key có trong tenant?]
    B --> V2[Key có trong central config?]
    C --> V3[Key có trong platform defaults?]
~~~

Trong sơ đồ, các nguồn được xét từ trên xuống. Nếu `tenantOverrides` có key, giá trị của nó được trả về; nếu không, composite tiếp tục kiểm tra `centralConfig`, rồi `platformDefaults`.

### 2.1. Composite không sao chép dữ liệu

Khi thêm một `PropertySource` vào composite, composite giữ tham chiếu đến nguồn đó. Nó không tự đọc hết key, sao chép toàn bộ map hay tạo một snapshot bất biến của các giá trị.

Hệ quả:

- Nguồn con vẫn chịu trách nhiệm cung cấp dữ liệu.
- Giá trị được tra cứu khi gọi `getProperty`.
- Nếu nguồn con dựa trên dữ liệu thay đổi, kết quả có thể thay đổi theo cách triển khai của nguồn đó.
- Composite không tự tải lại file hoặc gọi remote service.

Vì vậy, `CompositePropertySource` là cơ chế **kết hợp tra cứu**, không phải một config server, cache hoặc hệ thống đồng bộ.

### 2.2. Tên composite và tên nguồn con

Composite có tên riêng, ví dụ `tenantAndPlatformConfig`. Mỗi nguồn con cũng nên có tên duy nhất, có ý nghĩa:

~~~text
tenantAndPlatformConfig
  ├── tenantOverrides
  ├── centralConfig
  └── platformDefaults
~~~

Tên rõ ràng giúp debug, đọc log và kiểm tra nguồn cấu hình. `PropertySource` so sánh bằng tên; vì vậy khi thêm nguồn con vào tập hợp, tên trùng có thể khiến nguồn mới không được thêm như mong muốn. Hãy đặt tên phân biệt cho từng nguồn, kể cả khi hai nguồn đọc từ cùng một loại backend.

## 3. Cách tra cứu và quy tắc ưu tiên nội bộ

### 3.1. First non-null wins

Giả sử composite chứa ba nguồn:

| Nguồn con | `service.timeout` | `service.region` |
| --- | ---: | --- |
| `tenantOverrides` | `900ms` | Không có |
| `platformDefaults` | `500ms` | `global` |
| `centralConfig` | `700ms` | `ap-southeast-1` |

Kết quả:

| Key | Giá trị composite trả về | Nguồn thắng |
| --- | --- | --- |
| `service.timeout` | `900ms` | `tenantOverrides` |
| `service.region` | `global` | `platformDefaults` |
| `service.name` | `null` nếu không nguồn nào có key | Không có |

Composite kiểm tra từng nguồn theo thứ tự. Nguồn đầu tiên trả về giá trị khác `null` sẽ dừng quá trình tra cứu cho key đó.

**Giá trị rỗng `""` khác `null`.** Nếu nguồn đầu tiên trả về chuỗi rỗng, đó vẫn là một giá trị và có thể chặn giá trị ở nguồn phía sau. Nếu ứng dụng muốn xem chuỗi rỗng là “chưa cấu hình”, cần chuẩn hóa hoặc validate giá trị ở tầng phù hợp; không giả định composite tự bỏ qua chuỗi rỗng.

### 3.2. Thứ tự thêm nguồn ảnh hưởng kết quả

API thường dùng:

- `addPropertySource(source)`: thêm nguồn vào cuối thứ tự nội bộ.
- `addFirstPropertySource(source)`: đặt nguồn vào đầu, có ưu tiên cao nhất bên trong composite.
- `getPropertySources()`: xem các nguồn con đang có.
- `containsPropertySource(name)`: kiểm tra nguồn con theo tên.

Ví dụ:

~~~java
CompositePropertySource composite =
        new CompositePropertySource("serviceConfig");

composite.addPropertySource(platformDefaults);
composite.addPropertySource(centralConfig);
composite.addFirstPropertySource(tenantOverrides);
~~~

Thứ tự tra cứu sau khi thêm:

~~~text
1. tenantOverrides
2. platformDefaults
3. centralConfig
~~~

Nếu muốn `centralConfig` đứng trên `platformDefaults`, hãy thêm theo đúng thứ tự hoặc dùng `addFirstPropertySource` có chủ đích:

~~~java
composite.addFirstPropertySource(centralConfig);
~~~

Sau thao tác này, thứ tự trở thành:

~~~text
1. centralConfig
2. tenantOverrides
3. platformDefaults
~~~

Lưu ý: `addFirstPropertySource` chuyển nguồn được chỉ định lên đầu tập hợp. Nó không thay đổi thứ tự của các `PropertySource` bên ngoài composite trong `Environment`.

### 3.3. Nguồn không có key và nguồn trả về null

Nếu nguồn con không chứa key, `getProperty` trả `null` và composite tiếp tục xét nguồn sau. Một nguồn tùy biến có thể trả `null` khi backend không có dữ liệu, key không được phép truy cập hoặc backend không sẵn sàng; các trường hợp đó có ý nghĩa vận hành khác nhau.

Không nên âm thầm biến lỗi kết nối backend thành `null` nếu ứng dụng cần phân biệt:

- Key không tồn tại.
- Key tồn tại nhưng bị từ chối truy cập.
- Backend tạm thời không khả dụng.
- Backend trả dữ liệu không hợp lệ.

Với cấu hình bắt buộc, lỗi backend nên được xử lý rõ ràng ở tầng tải nguồn hoặc bootstrap thay vì giả vờ rằng key đơn giản là không có.

## 4. Tạo CompositePropertySource từ nhiều MapPropertySource

Một ví dụ nhỏ giúp nhìn thấy thứ tự ưu tiên mà không cần backend bên ngoài.

### 4.1. Khai báo các nguồn con

~~~java
import java.util.Map;

import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.PropertySource;

PropertySource<?> tenantOverrides = new MapPropertySource(
        "tenantOverrides",
        Map.of(
                "service.timeout", "900ms",
                "service.display-name", "Tenant A"
        )
);

PropertySource<?> centralConfig = new MapPropertySource(
        "centralConfig",
        Map.of(
                "service.timeout", "700ms",
                "service.region", "ap-southeast-1"
        )
);

PropertySource<?> platformDefaults = new MapPropertySource(
        "platformDefaults",
        Map.of(
                "service.timeout", "500ms",
                "service.region", "global",
                "service.retry-enabled", true
        )
);
~~~

Các nguồn có một số key trùng nhau. Điều này được cố ý tạo ra để kiểm tra precedence.

### 4.2. Gộp nguồn

~~~java
import org.springframework.core.env.CompositePropertySource;

CompositePropertySource composite =
        new CompositePropertySource("serviceConfig");

composite.addPropertySource(platformDefaults);
composite.addPropertySource(centralConfig);
composite.addFirstPropertySource(tenantOverrides);
~~~

Thứ tự nội bộ là:

1. `tenantOverrides`.
2. `platformDefaults`.
3. `centralConfig`.

Với `service.timeout`, tenant thắng và kết quả là `900ms`. Với `service.region`, tenant không có key nên platform defaults được xét trước central config; kết quả là `global`.

Nếu muốn central config có ưu tiên cao hơn platform defaults, thay thứ tự thêm nguồn:

~~~java
CompositePropertySource composite =
        new CompositePropertySource("serviceConfig");

composite.addPropertySource(platformDefaults);
composite.addFirstPropertySource(centralConfig);
composite.addFirstPropertySource(tenantOverrides);
~~~

Kết quả nội bộ là tenant, central, platform.

### 4.3. Đọc giá trị từ composite

~~~java
Object timeout = composite.getProperty("service.timeout");
Object region = composite.getProperty("service.region");
Object retryEnabled = composite.getProperty("service.retry-enabled");

System.out.println(timeout);       // 900ms
System.out.println(region);        // ap-southeast-1 nếu central đứng trên platform
System.out.println(retryEnabled);  // true
~~~

Đoạn mã trên giả định thứ tự đã được thiết lập theo ví dụ thứ hai. Trong ứng dụng thật, nên ghi rõ thứ tự nguồn bằng một bảng hoặc test để người bảo trì không phải suy luận từ các lệnh `addPropertySource`.

## 5. Đưa composite vào Environment

Một `CompositePropertySource` chỉ tham gia phân giải cấu hình của ứng dụng khi được gắn vào `Environment` hoặc được một integration đưa vào đó.

### 5.1. Dùng MutablePropertySources

`ConfigurableEnvironment` cung cấp `getPropertySources()`, trả về `MutablePropertySources`. Có thể thêm composite như một nguồn cấp cao nhất:

~~~java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.CompositePropertySource;

void registerComposite(
        ConfigurableEnvironment environment,
        CompositePropertySource composite
) {
    environment.getPropertySources().addFirst(composite);
}
~~~

Sau khi thêm, có thể đọc bằng `Environment`:

~~~java
String timeout = environment.getProperty("service.timeout");
~~~

Ở đây có **hai tầng precedence**:

1. **Bên trong composite:** thứ tự các nguồn con quyết định nguồn nào thắng trong nhóm.
2. **Giữa các PropertySource của Environment:** vị trí của composite trong `MutablePropertySources` quyết định composite đứng trước hay sau các nguồn bên ngoài nhóm.

Ví dụ, nếu `commandLineArgs` nằm trước composite và chứa `service.timeout`, command line thắng. Nếu composite được `addFirst`, nó đứng trước các nguồn hiện có và có thể ghi đè cả command-line value. Đây là quyết định có ảnh hưởng lớn; không nên dùng `addFirst` một cách máy móc trong production.

### 5.2. Chọn vị trí có chủ đích

| Cách thêm | Kết quả |
| --- | --- |
| `addFirst(composite)` | Composite có ưu tiên cao nhất trong danh sách hiện tại |
| `addLast(composite)` | Composite có ưu tiên thấp nhất |
| `addBefore(name, composite)` | Đặt composite trước nguồn có tên đã biết |
| `addAfter(name, composite)` | Đặt composite sau nguồn có tên đã biết |
| `replace(name, composite)` | Thay nguồn đã có cùng tên trong danh sách Environment |

Nếu dùng `addBefore` hoặc `addAfter`, phải chắc chắn tên nguồn đích tồn tại. Tên nguồn mặc định có thể thay đổi theo loại Environment, phiên bản hoặc cách khởi động. Hãy kiểm tra `environment.getPropertySources()` trước khi sắp xếp tương đối.

### 5.3. Thêm composite trong ApplicationContextInitializer

Một cách đăng ký trước khi bean thông thường được tạo là `ApplicationContextInitializer`:

~~~java
import java.util.Map;

import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.CompositePropertySource;
import org.springframework.core.env.MapPropertySource;

public class ServiceSourcesInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        CompositePropertySource composite =
                new CompositePropertySource("serviceConfig");

        composite.addFirstPropertySource(
                new MapPropertySource(
                        "tenantOverrides",
                        Map.of("service.timeout", "900ms")
                )
        );

        composite.addPropertySource(
                new MapPropertySource(
                        "platformDefaults",
                        Map.of(
                                "service.timeout", "500ms",
                                "service.retry-enabled", true
                        )
                )
        );

        context.getEnvironment()
                .getPropertySources()
                .addLast(composite);
    }
}
~~~

Đăng ký initializer với `SpringApplication`:

~~~java
SpringApplication application =
        new SpringApplication(OrdersApplication.class);

application.addInitializers(new ServiceSourcesInitializer());
application.run(args);
~~~

Ví dụ dùng `addLast` để composite đóng vai trò nguồn fallback có ưu tiên thấp. Nếu yêu cầu tenant override các nguồn hiện có, phải chọn vị trí khác và kiểm thử rõ thứ tự.

`ApplicationContextInitializer` chạy trong quá trình chuẩn bị context. Đây là thời điểm phù hợp để bổ sung nguồn cấu hình cần có trước khi bean được tạo. Không nên chờ tới `ApplicationRunner` rồi mới thêm source nếu bean đã bind giá trị từ trước.

## 6. CompositePropertySource với nguồn cấu hình từ xa

Trong hệ thống phân tán, các nguồn con có thể đến từ nhiều backend:

- Cấu hình mặc định của nền tảng.
- Cấu hình riêng cho ứng dụng.
- Cấu hình theo môi trường.
- Cấu hình theo tenant.
- Nguồn secret hoặc credential.
- Nguồn override do vận hành quản lý.

Một composite có thể biểu diễn thứ tự ưu tiên giữa các nguồn đó.

### 6.1. Mô hình nhiều lớp cấu hình

Ví dụ một dịch vụ `orders-service` nhận ba lớp:

| Lớp | Ví dụ | Mục đích |
| --- | --- | --- |
| Platform defaults | Timeout mặc định `500ms` | Giá trị nền cho mọi service |
| Central application config | Timeout `700ms`, region `ap-southeast-1` | Cấu hình theo ứng dụng/môi trường |
| Tenant overrides | Timeout `900ms`, tên hiển thị riêng | Điều chỉnh theo tenant được phép |

Nếu tenant override có ưu tiên cao nhất, composite sẽ chọn timeout `900ms`. Nếu tenant không khai báo region, giá trị sẽ rơi xuống nguồn kế tiếp có key đó.

Đây là mô hình **fallback theo key**. Nó không phải merge sâu object JSON/YAML tự động. Composite chỉ tìm giá trị theo từng key đã được chuẩn hóa thành dạng property. Cách merge danh sách hoặc object phức tạp phải được định nghĩa ở tầng binding hoặc tầng xử lý cấu hình riêng.

### 6.2. Nguồn từ xa phải được nạp trước khi đăng ký

Nếu nguồn con đọc từ HTTP, Vault hoặc database, cần có thành phần tải dữ liệu và biến nó thành `PropertySource`. Composite không tự biết URL, credential, retry, timeout hay giao thức backend.

Một luồng có thể là:

~~~mermaid
flowchart TD
    A[Bootstrap / Config Data integration] --> B[Fetch platform config]
    A --> C[Fetch application config]
    A --> D[Fetch tenant overrides]
    B --> E[Build PropertySource objects]
    C --> E
    D --> E
    E --> F[Build CompositePropertySource]
    F --> G[Register into Environment]
    G --> H[Create and bind application beans]
~~~

Luồng này cần chính sách lỗi rõ ràng:

- Platform defaults có thể là bắt buộc hoặc có fallback đóng gói.
- Config Server có thể bắt buộc hoặc optional tùy nghiệp vụ.
- Tenant override có thể là tùy chọn nếu tenant không có cấu hình riêng.
- Secret source thường không nên fallback sang một giá trị rỗng hoặc mặc định không an toàn.
- Nếu một backend lỗi, cần phân biệt lỗi đó với trường hợp backend trả về “không có key”.

### 6.3. Tách trách nhiệm tải dữ liệu và kết hợp dữ liệu

Thiết kế dễ bảo trì thường tách hai việc:

1. **Loader/adapter:** kết nối backend, xác thực, xử lý timeout, retry, cache và chuyển dữ liệu thành `PropertySource`.
2. **Composer:** nhận các `PropertySource` đã sẵn sàng, đặt tên, sắp xếp và tạo `CompositePropertySource`.

Như vậy, logic precedence không bị trộn với HTTP client hoặc SDK của secret store. Có thể test composer bằng `MapPropertySource` mà không cần dựng backend thật.

## 7. Tích hợp với Spring Cloud

### 7.1. Quan hệ với PropertySourceLocator trong bootstrap legacy

Trong các tích hợp Spring Cloud sử dụng bootstrap context legacy, `PropertySourceLocator` là một extension point để tìm hoặc tạo property source dựa trên Environment. Một implementation có thể lấy cấu hình từ backend và trả về một `CompositePropertySource` khi cần gom nhiều nguồn con.

Ý tưởng ở mức khái niệm:

~~~java
// Pseudocode: tên package/API cần đối chiếu release train đang dùng.
PropertySource<?> locate(Environment environment) {
    PropertySource<?> platform = loadPlatformProperties(environment);
    PropertySource<?> application = loadApplicationProperties(environment);
    PropertySource<?> tenant = loadTenantProperties(environment);

    CompositePropertySource composite =
            new CompositePropertySource("remoteConfiguration");

    if (tenant != null) {
        composite.addFirstPropertySource(tenant);
    }
    if (application != null) {
        composite.addPropertySource(application);
    }
    if (platform != null) {
        composite.addPropertySource(platform);
    }

    return composite;
}
~~~

Đây là pseudocode minh họa ý tưởng, không phải một lớp có thể copy nguyên xi: package, cách đăng ký và lifecycle của `PropertySourceLocator` phụ thuộc phiên bản Spring Cloud và bootstrap mode. Không nên mặc định extension point legacy này được gọi trong mọi dự án Config Data hiện đại.

### 7.2. Config Data import hiện đại

Với Spring Cloud Config Client hiện đại, ứng dụng thường khai báo:

~~~yaml
spring:
  application:
    name: orders-service
  config:
    import: optional:configserver:http://localhost:8888
~~~

Config Client chịu trách nhiệm tải remote configuration và đưa property source vào quá trình Config Data. Người dùng không cần tự tạo `CompositePropertySource` chỉ để gọi Config Server một lần.

Nếu có nhiều nguồn ngoài Config Server, có thể cần một integration tùy biến khác. Với Spring Boot Config Data, extension point cho nguồn tùy chỉnh có thể là `ConfigDataLocationResolver` và `ConfigDataLoader`, tùy nhu cầu và phiên bản. Chọn extension point phù hợp với cơ chế nạp cấu hình đang dùng; không đưa mã bootstrap legacy vào Config Data chỉ vì nó từng hoạt động ở phiên bản cũ.

### 7.3. Composite không thay thế Config Server

| Thành phần | Trách nhiệm |
| --- | --- |
| `CompositePropertySource` | Gom các nguồn thuộc tính đã có và quyết định thứ tự tra cứu |
| Config Client | Kết nối Config Server và nạp cấu hình từ xa |
| Config Server | Cung cấp cấu hình tập trung |
| `Environment` | Cho ứng dụng đọc giá trị sau khi nguồn đã được đăng ký |
| Spring Cloud Context refresh | Hỗ trợ cập nhật/rebind hoặc tạo lại bean theo cơ chế refresh phù hợp |

Composite không tự lưu lịch sử phiên bản cấu hình, phân phối thay đổi tới các instance hoặc xác thực người dùng. Những nhiệm vụ đó thuộc các hệ thống tích hợp tương ứng.

## 8. Enumeration: liệt kê tên key trong composite

`CompositePropertySource` là một `EnumerablePropertySource`. Khi gọi `getPropertyNames()`, nó thu thập tên key từ các nguồn con hỗ trợ liệt kê.

### 8.1. EnumerablePropertySource và nguồn không enumerable

Một nguồn như `MapPropertySource` có thể liệt kê tên key. Nhưng một nguồn tùy biến chỉ có khả năng trả lời `getProperty(key)` có thể không biết toàn bộ key hoặc không hỗ trợ liệt kê.

Hệ quả:

- `composite.getProperty("secret.token")` vẫn có thể lấy được giá trị từ nguồn con không enumerable.
- `composite.getPropertyNames()` chỉ có thể tổng hợp những tên key mà các nguồn con có thể liệt kê.
- Một key có thể đọc được nhưng không xuất hiện trong danh sách tên key.

Đừng dùng danh sách `getPropertyNames()` làm bằng chứng tuyệt đối rằng mọi key có thể truy vấn đều đã được liệt kê.

### 8.2. containsProperty và key rỗng

`containsProperty(key)` kiểm tra các nguồn con theo khả năng của từng nguồn. Một key tồn tại nhưng có giá trị `null` có thể không được xem như một giá trị có thể phân giải; một chuỗi rỗng vẫn là giá trị khác `null`.

Nếu backend phân biệt rõ “không có key”, “key có giá trị rỗng” và “không được phép đọc”, adapter nên thể hiện sự khác biệt đó bằng chính sách lỗi/validation rõ ràng. Không dùng `null` cho nhiều trạng thái nếu ứng dụng cần phân biệt.

## 9. Kiểm thử CompositePropertySource

Kiểm thử composer nên xác nhận thứ tự nội bộ, tương tác với Environment và các trường hợp thiếu key. Các test sau dùng `MapPropertySource`, không cần Config Server hoặc registry.

### 9.1. Kiểm tra first source wins

~~~java
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.core.env.CompositePropertySource;
import org.springframework.core.env.MapPropertySource;

import static org.assertj.core.api.Assertions.assertThat;

class CompositePropertySourceTest {

    @Test
    void firstSourceWinsForDuplicateKey() {
        var defaults = new MapPropertySource(
                "defaults",
                Map.of("service.timeout", "500ms")
        );

        var tenant = new MapPropertySource(
                "tenant",
                Map.of("service.timeout", "900ms")
        );

        var composite = new CompositePropertySource("serviceConfig");
        composite.addPropertySource(defaults);
        composite.addFirstPropertySource(tenant);

        assertThat(composite.getProperty("service.timeout"))
                .isEqualTo("900ms");
    }
}
~~~

Test chứng minh nguồn tenant được đưa lên đầu và thắng nguồn mặc định cho key trùng nhau.

### 9.2. Kiểm tra fallback khi nguồn đầu không có key

~~~java
@Test
void fallsBackToNextSourceWhenKeyIsAbsent() {
    var tenant = new MapPropertySource(
            "tenant",
            Map.of("service.display-name", "Tenant A")
    );

    var defaults = new MapPropertySource(
            "defaults",
            Map.of("service.timeout", "500ms")
    );

    var composite = new CompositePropertySource("serviceConfig");
    composite.addPropertySource(tenant);
    composite.addPropertySource(defaults);

    assertThat(composite.getProperty("service.timeout"))
            .isEqualTo("500ms");
}
~~~

Nếu tenant không khai báo `service.timeout`, composite tiếp tục tìm ở `defaults`.

### 9.3. Kiểm tra precedence giữa Environment và composite

~~~java
import org.springframework.mock.env.MockEnvironment;
import org.springframework.core.env.MapPropertySource;

@Test
void environmentSourceCanOverrideComposite() {
    var environment = new MockEnvironment();

    var composite = new CompositePropertySource("serviceConfig");
    composite.addPropertySource(
            new MapPropertySource(
                    "compositeDefaults",
                    Map.of("service.timeout", "700ms")
            )
    );

    environment.getPropertySources().addLast(composite);
    environment.getPropertySources().addFirst(
            new MapPropertySource(
                    "commandLineLike",
                    Map.of("service.timeout", "1200ms")
            )
    );

    assertThat(environment.getProperty("service.timeout"))
            .isEqualTo("1200ms");
}
~~~

Test này chứng minh có hai tầng thứ tự: dù composite có nguồn con, property source bên ngoài đứng trước composite vẫn có thể thắng.

### 9.4. Kiểm tra tên nguồn và enumeration

Nên có thêm test cho:

- Nguồn con có tên duy nhất.
- Thêm nguồn con cùng tên.
- Composite chứa một nguồn enumerable và một nguồn không enumerable.
- Key có chuỗi rỗng.
- Key không tồn tại ở tất cả nguồn.
- Nguồn con bị lỗi khi truy vấn.

Không nhất thiết mọi ứng dụng phải viết tất cả test trên. Hãy chọn những trường hợp phản ánh chính sách precedence và lỗi backend thực tế của hệ thống.

## 10. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Giá trị lấy từ nguồn không mong muốn | Thứ tự nguồn con sai | Kiểm tra thứ tự `getPropertySources()` và dùng `addFirstPropertySource` có chủ đích |
| Composite có giá trị nhưng Environment không lấy được | Composite chưa được thêm vào Environment hoặc bị nguồn đứng trước ghi đè | Kiểm tra `MutablePropertySources` và vị trí composite |
| Key không xuất hiện trong `getPropertyNames()` | Nguồn con không hỗ trợ enumeration | Kiểm tra trực tiếp `getProperty(key)` hoặc cung cấp nguồn enumerable |
| Thêm nguồn nhưng không có tác dụng | Tên `PropertySource` trùng với nguồn đã có trong tập hợp | Đặt tên nguồn con duy nhất và kiểm tra `containsPropertySource` |
| Chuỗi rỗng chặn giá trị mặc định | `""` khác `null`, nên nguồn đầu vẫn được xem là có giá trị | Validate/chuẩn hóa giá trị ở loader hoặc binder |
| Config Server lỗi nhưng composite trả fallback | Adapter đã biến lỗi backend thành `null` | Phân biệt lỗi kết nối với key không tồn tại |
| Thay đổi map nhưng bean vẫn dùng giá trị cũ | Bean đã bind/giữ giá trị từ trước | Xem lifecycle, rebind và refresh scope |
| Thứ tự nguồn thay đổi giữa môi trường | Nguồn được thêm ở giai đoạn khác hoặc integration khác | Kiểm tra startup order và property source thực tế |
| Sibling/context khác không nhận cùng cấu hình | Composite được đăng ký trong một Environment/context riêng | Xác định context ownership và cách chia sẻ Environment |

### 10.1. Trùng tên nguồn con

`PropertySource` dùng tên làm định danh trong các thao tác so sánh. Nếu thêm hai nguồn có cùng tên vào tập hợp nội bộ, nguồn thứ hai có thể không được thêm như một phần tử mới. Đừng dùng cùng tên `remoteConfig` cho hai nguồn khác nhau rồi kỳ vọng cả hai đều có mặt.

Đặt tên theo backend và phạm vi, ví dụ:

~~~text
tenantConfig:tenant-42
centralConfig:orders-service:prod
platformDefaults:region-ap-southeast-1
~~~

Không đưa secret hoặc dữ liệu nhạy cảm vào tên nguồn.

### 10.2. Mutate composite sau khi ứng dụng đã chạy

`CompositePropertySource` và tập hợp nguồn con không phải một kho cấu hình có cơ chế đồng bộ thread-safe cho mọi thao tác thay đổi runtime. Việc thêm/xóa nguồn trong lúc nhiều thread đang đọc có thể tạo hành vi khó dự đoán.

Khuyến nghị:

- Xây dựng composite hoàn chỉnh trước khi đăng ký vào Environment.
- Tránh sửa tập hợp nguồn con trong đường xử lý request.
- Nếu cần cập nhật cấu hình, dùng cơ chế refresh/replacement có kiểm soát.
- Xác định bean nào cần rebind hoặc tạo lại sau khi cập nhật.
- Kiểm thử đồng thời nếu integration bắt buộc hỗ trợ cập nhật runtime.

### 10.3. Gộp nguồn không có nghĩa là merge sâu object

Composite giải quyết câu hỏi: “Key này lấy từ nguồn nào?”. Nó không tự hợp nhất hai JSON object, YAML list hay cấu trúc map theo quy tắc domain.

Ví dụ hai nguồn cùng có `clients.inventory.zones` với hai danh sách khác nhau: composite sẽ chọn giá trị của nguồn thắng cho key tương ứng; nó không tự nối phần tử của hai list. Nếu cần merge sâu, phải triển khai logic merge riêng trước khi tạo PropertySource hoặc dùng mô hình cấu hình phù hợp.

## 11. Bảo mật và vận hành

Khi composite chứa nguồn secret hoặc cấu hình tenant, cần thiết kế phạm vi truy cập rõ ràng.

- **Phân tách tenant:** chỉ đưa override của tenant đang được xác định vào đúng phạm vi context/request. Không đặt một map tenant dùng chung toàn JVM nếu các request có thể đọc nhầm cấu hình của nhau.
- **Quyền truy cập:** adapter cần xác thực và kiểm tra quyền trước khi tải dữ liệu; không xem tên PropertySource là ranh giới bảo mật.
- **Secret:** không log giá trị, không đưa token/password vào tên nguồn và không expose Actuator `env` công khai.
- **Timeout và retry:** loader từ xa cần giới hạn thời gian, retry có kiểm soát và phân biệt backend lỗi với key vắng mặt.
- **Fallback:** chỉ fallback khi nghiệp vụ cho phép; secret bắt buộc không nên tự rơi về giá trị giả.
- **Quan sát:** ghi nhận backend nào được tải, thời gian tải, số key hoặc trạng thái nguồn ở mức an toàn; không ghi nội dung nhạy cảm.
- **Refresh:** khi nguồn thay đổi, cập nhật composite theo cơ chế có kiểm soát và xác minh bean đã nhận cấu hình mới.
- **Versioning:** API Spring Framework và extension point Spring Cloud cần tương thích với release train/Boot version của dự án.

Với cấu hình theo tenant, đặc biệt tránh đưa mọi tenant override vào một `CompositePropertySource` toàn cục rồi đổi “tenant hiện tại” theo request. `Environment` thường thuộc phạm vi ứng dụng/context, không phải request context. Nếu cấu hình thay đổi theo tenant trên mỗi request, cần một resolver có phạm vi phù hợp, cache phân tách tenant và kiểm soát truy cập riêng.

## 12. Bài tập vận dụng

**Bài tập 1 — Thứ tự nội bộ.** Tạo ba `MapPropertySource`: `platformDefaults`, `centralConfig`, `tenantOverrides`. Cùng khai báo key `service.timeout` với giá trị khác nhau. Dùng `addPropertySource` và `addFirstPropertySource` để tenant thắng; chứng minh kết quả bằng test.

**Bài tập 2 — Fallback theo key.** Tenant chỉ khai báo `service.display-name`, central khai báo `service.region`, platform khai báo `service.timeout`. Gọi `getProperty` cho cả ba key và giải thích nguồn nào được chọn.

**Bài tập 3 — Hai tầng precedence.** Đưa composite vào `MockEnvironment` bằng `addLast`, rồi thêm một `MapPropertySource` bằng `addFirst`. Chứng minh nguồn ngoài composite có thể ghi đè nguồn con dù composite có thứ tự nội bộ riêng.

**Bài tập 4 — Enumeration.** Tạo một nguồn tùy biến có thể đọc key nhưng không liệt kê được tên key. So sánh `getProperty("secret.token")` với `getPropertyNames()` của composite và giải thích sự khác nhau.

**Bài tập 5 — Trùng tên.** Thêm hai `MapPropertySource` cùng tên vào composite. Quan sát tập hợp nguồn và kết quả tra cứu; sau đó đổi tên để bảo đảm cả hai nguồn được quản lý rõ ràng.

**Bài tập 6 — Nguồn từ xa.** Thiết kế adapter đọc platform config và tenant config từ hai backend giả lập. Tách loader khỏi composer; viết test cho timeout, backend lỗi, key thiếu và precedence.

**Bài tập 7 — Refresh.** Cập nhật dữ liệu của một nguồn con sau khi ứng dụng khởi động. Xác định giá trị mới có được Environment đọc hay không và bean đã bind giá trị cũ có cần refresh/recreate hay không.

## 13. Ghi nhớ và nguồn tra cứu

- `CompositePropertySource` là một `PropertySource` tổng hợp, chứa nhiều nguồn con.
- Composite tra cứu theo thứ tự nội bộ; **nguồn đầu tiên trả về giá trị khác `null` thắng**.
- `addFirstPropertySource` đưa nguồn lên đầu; `addPropertySource` thêm nguồn vào cuối.
- Tên nguồn con nên duy nhất vì `PropertySource` sử dụng tên trong phép so sánh.
- `getPropertyNames()` chỉ liệt kê những key mà các nguồn con hỗ trợ enumeration; một nguồn không enumerable vẫn có thể trả lời `getProperty(key)`.
- Khi thêm composite vào Environment, phải xét cả thứ tự nội bộ lẫn vị trí composite trong `MutablePropertySources`.
- Composite chỉ gộp việc tra cứu; nó không tự tải remote config, cache, merge sâu object hoặc refresh bean.
- Với Spring Cloud, cần chọn extension point phù hợp: bootstrap legacy và Config Data hiện đại có lifecycle khác nhau.
- Cấu hình tenant và secret cần phạm vi truy cập, fallback và logging được kiểm soát.

Nguồn chính thức để đối chiếu API theo phiên bản Spring Framework/Spring Cloud của dự án:

1. [Spring Framework Javadoc – `CompositePropertySource`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/env/CompositePropertySource.html)
2. [Spring Framework Javadoc – `PropertySource`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/env/PropertySource.html)
3. [Spring Framework Javadoc – `MutablePropertySources`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/env/MutablePropertySources.html)
4. [Spring Framework Reference – Environment Abstraction](https://docs.spring.io/spring-framework/reference/core/beans/environment.html)
5. [Spring Cloud Config – Client Side Usage](https://docs.spring.io/spring-cloud-config/reference/client.html)
6. [Spring Cloud Context – Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)

# PropertySource và MutablePropertySources trong ConfigurableEnvironment

## 1. Vì sao cần hiểu nguồn thuộc tính thay vì chỉ đọc application.yml?

Một ứng dụng Spring Boot có thể nhận cùng một khóa cấu hình từ rất nhiều nơi: cấu hình đóng gói trong JAR, file bên ngoài, biến môi trường, Java system properties, đối số dòng lệnh, nguồn do thư viện thêm vào hoặc một nguồn được ứng dụng tự xây dựng.

Ví dụ, khóa `warehouse.api-url` có thể được khai báo:

```yaml
# src/main/resources/application.yml
warehouse:
  api-url: https://warehouse-default.example.invalid
```

Trong khi tiến trình được khởi động với:

```bash
java -jar app.jar \
  --warehouse.api-url=https://warehouse-prod.example.invalid
```

Vì sao `Environment.getProperty("warehouse.api-url")` trả về giá trị từ dòng lệnh thay vì YAML? Nếu muốn bổ sung một nguồn “giá trị mặc định theo vùng”, nên thêm nó ở đâu để không ghi đè cấu hình của người triển khai? Có thể thay thứ tự ưu tiên ở runtime không? Có nên sửa trực tiếp nguồn mặc định của Spring Boot không?

Để trả lời, cần hiểu ba kiểu trung tâm của Spring Framework:

- **`PropertySource<T>`**: đại diện cho **một nguồn** có thể tra cứu giá trị theo tên thuộc tính.
- **`MutablePropertySources`**: tập hợp **có thứ tự và có thể thay đổi** của các `PropertySource`.
- **`ConfigurableEnvironment`**: một biến thể của `Environment` cho phép truy cập/chỉnh tập nguồn thuộc tính và một số thông số cấu hình môi trường.

Đây là nền tảng của chủ đề **Mở rộng Environment**: thay vì chỉ tiêu thụ cấu hình, ta có thể đăng ký và sắp xếp một nguồn mới một cách có chủ đích.

Kết quả cuối cùng phụ thuộc vào **khóa**, **giá trị**, **thứ tự ưu tiên**, **thời điểm thêm nguồn** và **cách bean đã được khởi tạo**.

## 2. Mô hình tổng thể

Sơ đồ đơn giản:

```text
             ConfigurableEnvironment
                      |
                      v
             MutablePropertySources
                      |
         +------------+-------------+
         |            |             |
      vị trí 0      vị trí 1       vị trí 2 ...
         |            |             |
         v            v             v
   PropertySource  PropertySource  PropertySource
     ưu tiên cao       tiếp theo      ưu tiên thấp
         |            |             |
         +------------+-------------+
                      |
                      v
            PropertyResolver
             getProperty(key)
                      |
                      v
         Tìm nguồn đầu tiên có giá trị
                      |
                      v
              @Value / Binder /
          @ConfigurationProperties
```

Khi giải quyết một khóa đơn giản, quy tắc tư duy là:

1. Bắt đầu tại `PropertySource` có ưu tiên cao nhất trong danh sách.
2. Hỏi nguồn đó có giá trị phù hợp cho tên thuộc tính cần tìm không.
3. Nếu không có, chuyển sang nguồn có ưu tiên thấp hơn.
4. Khi tìm thấy một giá trị khác `null`, sử dụng nó theo cơ chế property resolution.
5. Sau đó mới xử lý những việc phù hợp như placeholder, chuyển kiểu và đưa giá trị vào bean.

Một lưu ý quan trọng: giá trị chuỗi **rỗng** `""` vẫn khác `null`. Một nguồn có thể chủ động cung cấp chuỗi rỗng, khiến những nguồn thấp hơn không được chọn cho khóa đó.

Spring Boot xây dựng và bổ sung nhiều nguồn mặc định theo các quy tắc riêng. Danh sách trong sơ đồ là mô hình khái quát, **không phải một thứ tự cố định của mọi phiên bản Boot**. Để quan sát thứ tự thực tế, hãy in tên các source của chính tiến trình đang chạy, không đoán từ tên file.

## 3. Interface PropertySource<T>: hợp đồng của một nguồn

`PropertySource<T>` nằm trong:

```java
org.springframework.core.env.PropertySource
```

Một nguồn có **tên** và một đối tượng nguồn dữ liệu nền. Phương thức quan trọng nhất:

```java
Object getProperty(String name)
```

Kết quả có thể là một giá trị, hoặc `null` nếu nguồn này không cung cấp tên được hỏi.

Ta có thể hình dung:

```text
PropertySource("tenantDefaults")
    |
    +-- getProperty("tenant.region") -> "ap-southeast"
    |
    +-- getProperty("tenant.limit")  -> 100
    |
    +-- getProperty("tenant.unknown")-> null
```

Những thành phần thường gặp trên API gồm:

| API | Ý nghĩa |
| --- | --- |
| `getName()` | Tên định danh của PropertySource |
| `getSource()` | Object dữ liệu nền mà source bao lại |
| `getProperty(String)` | Tìm giá trị của một tên thuộc tính |
| `containsProperty(String)` | Kiểm tra sự tồn tại theo hành vi của nguồn |
| `toString()` | Biểu diễn phục vụ chẩn đoán; không nên log cả giá trị bí mật |

Không phải mọi `PropertySource` đều là một `Map`. Đối tượng nguồn có thể là bản đồ, Java `Properties`, environment variables, servlet context, cấu trúc config data hay thậm chí một bộ tra cứu động do thư viện cung cấp.

**Không nên sửa dữ liệu bên dưới chỉ vì `getSource()` có trả về một Map.** Quyền thay đổi, tính bất biến, khả năng an toàn luồng và cách nguồn cập nhật phụ thuộc implementation. Với mục đích thêm giá trị cấu hình, hãy chọn implementation thích hợp hoặc tạo một PropertySource mới.

### 3.1. PropertySource chỉ đại diện cho một nguồn

Giả sử nguồn tên `baseDefaults` có:

```text
shop.currency = VND
shop.max-items = 20
```

Nó không biết rằng một nguồn dòng lệnh phía trên có thể đưa ra `shop.max-items=50`. Thứ tự ưu tiên do **tập PropertySources bên ngoài** quyết định, không phải bản thân `MapPropertySource`.

Vì vậy:

```java
propertySource.getProperty("shop.max-items")
```

và:

```java
environment.getProperty("shop.max-items")
```

có thể cho kết quả khác nhau. Lệnh đầu truy vấn **đúng một nguồn**; lệnh sau đi qua **chuỗi các nguồn có thứ tự**.

## 4. Những kiểu PropertySource thường gặp

Trong Spring Framework và Spring Boot, có một số implementation hoặc nhóm implementation cần nhận diện.

| Kiểu/nhóm | Vai trò |
| --- | --- |
| `MapPropertySource` | Đưa dữ liệu từ `Map<String, Object>` vào một PropertySource |
| `PropertiesPropertySource` | Bao một đối tượng `java.util.Properties` |
| `SystemEnvironmentPropertySource` | Thích nghi cách tra cứu thuộc tính với các biến môi trường |
| `CompositePropertySource` | Gom nhiều nguồn con thành một nguồn tổng hợp trong một số tình huống |
| Các nguồn Config Data của Spring Boot | Đại diện dữ liệu được nạp từ `application.yml`, `application.properties`, imports và vị trí cấu hình tương ứng |
| PropertySource tự định nghĩa | Thực hiện logic tra cứu riêng khi những implementation sẵn có không đủ |

Tên lớp implementation và tên nguồn xuất hiện trong ứng dụng có thể thay đổi tùy phiên bản Spring Boot, giai đoạn khởi động và loại nguồn. Khi cần tạo một nguồn tĩnh trong ví dụ học tập, **`MapPropertySource`** thường là lựa chọn dễ dùng nhất.

### 4.1. Ví dụ MapPropertySource

```java
import java.util.Map;
import org.springframework.core.env.MapPropertySource;

MapPropertySource defaults = new MapPropertySource(
    "shopDefaults",
    Map.of(
        "shop.currency", "VND",
        "shop.max-items", 20,
        "shop.enabled", true
    )
);
```

Ở đây:

- `"shopDefaults"` là **tên của nguồn**, không phải tên thuộc tính.
- `"shop.currency"` là **tên thuộc tính** bên trong nguồn.
- Value có kiểu `Object`, vì Map có thể chứa cả chuỗi, số và boolean.
- `defaults.getProperty("shop.max-items")` trả về object số `20` theo cách lưu dữ liệu.
- `defaults.getProperty("missing")` trả về `null`.

Nếu dùng `Environment.getProperty("shop.max-items")`, giao diện `getProperty(String)` thường trả về dạng `String` được giải quyết/chuyển đổi phù hợp. Đừng dựa vào việc kết quả raw của `MapPropertySource` và kết quả của resolver luôn có cùng kiểu runtime.

## 5. ConfigurableEnvironment mở rộng Environment như thế nào?

`Environment` cung cấp khả năng **đọc** trạng thái môi trường, chẳng hạn:

```java
String value = environment.getProperty("shop.currency");
String[] profiles = environment.getActiveProfiles();
```

`ConfigurableEnvironment` cung cấp thêm API **cấu hình** môi trường, đặc biệt:

```java
MutablePropertySources sources = environment.getPropertySources();
```

Các import:

```java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MutablePropertySources;
```

Có thể lấy `ConfigurableEnvironment` khi đang ở một điểm mở rộng hợp lệ của Spring Boot, hoặc từ `ConfigurableApplicationContext`.

Ví dụ trong một `ApplicationRunner`:

```java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@Bean
ApplicationRunner inspectSources(
        ConfigurableApplicationContext context) {
    return args -> {
        ConfigurableEnvironment env = context.getEnvironment();

        for (PropertySource<?> source : env.getPropertySources()) {
            System.out.println(source.getName());
        }
    };
}
```

Imports bổ sung:

```java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;
```

Ví dụ in **tên** PropertySource, không in toàn bộ nội dung. Cách đó có ích để xem thứ tự ưu tiên mà không vô tình log mật khẩu, token hoặc thông tin nhạy cảm trong `Environment`.

### 5.1. Vì sao gọi là configurable?

Vì nó cung cấp các thao tác cấu hình như quản lý nguồn, chọn profile hoặc những khả năng cấu hình môi trường khác. Nhưng khả năng thay đổi object **không có nghĩa mọi bean đang chạy đều tự cập nhật tức thời** khi danh sách nguồn bị thay đổi.

Trong nhiều ứng dụng, `@Value` và `@ConfigurationProperties` được đánh giá lúc tạo bean. Nếu một source mới được thêm **sau** khi bean đã tạo xong, lệnh `Environment.getProperty(...)` sau đó có thể thấy giá trị mới, còn các field đã được injection hoặc binding vẫn giữ giá trị cũ.

Đó là lý do thời điểm mở rộng môi trường quan trọng ngang với thứ tự ưu tiên.

## 6. MutablePropertySources là một danh sách có thứ tự

`MutablePropertySources` thuộc:

```java
org.springframework.core.env.MutablePropertySources
```

Nó quản lý các `PropertySource<?>` theo **tên nguồn** và theo **thứ tự**.

Các thao tác chính:

| Phương thức | Tác dụng |
| --- | --- |
| `addFirst(source)` | Đặt nguồn lên vị trí ưu tiên cao nhất |
| `addLast(source)` | Đặt nguồn ở vị trí ưu tiên thấp nhất |
| `addBefore(existingName, source)` | Chèn nguồn trước nguồn có tên đã biết |
| `addAfter(existingName, source)` | Chèn nguồn sau nguồn có tên đã biết |
| `replace(name, source)` | Thay source mang tên đó bằng source mới |
| `remove(name)` | Gỡ source theo tên |
| `get(name)` | Lấy source theo tên |
| `contains(name)` | Kiểm tra tập có source mang tên đó không |
| `iterator()` | Duyệt nguồn theo thứ tự ưu tiên |

Từ **“trước”** nghĩa là **ưu tiên cao hơn** trong trình tự tra cứu; **“sau”** nghĩa là **ưu tiên thấp hơn**.

```text
MutablePropertySources
  index 0: commandLineArgs  (ví dụ nguồn ưu tiên cao)
  index 1: configDataA
  index 2: configDataB
  index 3: customDefaults
  index 4: systemEnvironment
  ...
```

Đây chỉ là danh sách minh họa cách đánh số, **không phải cam kết thứ tự mặc định thật**. Trong ứng dụng, mỗi lần thêm nguồn nên xuất phát từ mục tiêu rõ ràng và thứ tự nguồn đang có, không dựa vào hình vẽ như một quy tắc bất biến.

### 6.1. Tên của PropertySource phải có ý nghĩa và được quản lý

Tên `"regionDefaults"`, `"tenantOverrides"` hay `"externalServiceDefaults"` giúp chẩn đoán. Tránh những tên chung như `"properties"` hoặc `"custom"` nếu có nhiều thư viện cùng thêm nguồn.

Khi muốn `addBefore` hoặc `addAfter`, bạn phải biết **tên nguồn neo có tồn tại**. Nếu tên đó không có trong danh sách, thao tác có thể ném `IllegalArgumentException`. Vì vậy, mã mở rộng nên kiểm tra và có phương án phù hợp, thay vì giả định mọi phiên bản Boot đều đặt cùng tên nguồn.

Không nên tùy tiện `replace("systemEnvironment", ...)` hoặc `remove("commandLineArgs")` chỉ để đạt một kết quả tạm thời; những nguồn tích hợp có thể được framework và thư viện khác sử dụng.

## 7. Thực nghiệm đầu tiên: addFirst và addLast

Để làm rõ thứ tự mà không phụ thuộc một máy thật đang có biến môi trường gì, ta có thể tạo `ConfigurableEnvironment` thử nghiệm bằng `MockEnvironment` từ `spring-test`.

Ví dụ unit test hoặc một chương trình thí nghiệm trong test source:

```java
import java.util.Map;

import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.MutablePropertySources;
import org.springframework.mock.env.MockEnvironment;

public class PriorityDemo {

    public static void main(String[] args) {
        ConfigurableEnvironment env = new MockEnvironment()
                .withProperty("shop.currency", "VND");

        MutablePropertySources sources = env.getPropertySources();

        sources.addLast(new MapPropertySource(
                "fallbackRegion",
                Map.of("shop.currency", "USD",
                       "shop.region", "global")
        ));

        System.out.println(env.getProperty("shop.currency"));
        System.out.println(env.getProperty("shop.region"));

        sources.addFirst(new MapPropertySource(
                "emergencyOverride",
                Map.of("shop.currency", "EUR")
        ));

        System.out.println(env.getProperty("shop.currency"));
    }
}
```

Vì `MockEnvironment` có nguồn `mockProperties` chứa `shop.currency=VND`, source `fallbackRegion` đặt ở cuối không ghi đè nó.

Dự đoán:

```text
VND
global
EUR
```

Giải thích:

1. `addLast(fallbackRegion)` cung cấp `shop.region` vì nguồn ban đầu không có khóa đó.
2. `shop.currency` vẫn là `VND` vì `mockProperties` có ưu tiên cao hơn.
3. `addFirst(emergencyOverride)` đặt `EUR` lên trước cả hai nguồn, nên resolver chọn `EUR`.

Ví dụ này cũng cho thấy **một source không cần chứa mọi khóa**. Nó có thể đóng góp một khóa mới mà không làm thay đổi những khóa đã được nguồn ưu tiên cao hơn cung cấp.

### 7.1. Cách đọc kết quả theo bảng

| Thứ tự nguồn cho `shop.currency` | Giá trị cung cấp | Kết quả |
| --- | --- | --- |
| Chỉ `mockProperties` | VND | VND |
| `mockProperties` → `fallbackRegion` | VND → USD | VND |
| `emergencyOverride` → `mockProperties` → `fallbackRegion` | EUR → VND → USD | EUR |

Không phải source cuối cùng được đăng ký thì luôn thắng. **Vị trí trong `MutablePropertySources`**, không phải thời gian được thêm vào, quyết định precedence.

## 8. addBefore và addAfter: kiểm soát vị trí tương đối

Khi không muốn đưa một source lên đầu hoặc cuối, có thể đặt nó tương đối với một nguồn đã tồn tại.

Giả sử ta có một môi trường thử nghiệm:

```java
import java.util.Map;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.MutablePropertySources;
import org.springframework.mock.env.MockEnvironment;

MockEnvironment env = new MockEnvironment();
MutablePropertySources sources = env.getPropertySources();

sources.addFirst(new MapPropertySource(
        "applicationOverrides",
        Map.of("feature.limit", 50)
));

sources.addAfter("applicationOverrides", new MapPropertySource(
        "regionalSettings",
        Map.of("feature.limit", 40,
               "feature.region", "SEA")
));

sources.addAfter("regionalSettings", new MapPropertySource(
        "globalDefaults",
        Map.of("feature.limit", 30)
));
```

Thứ tự lúc này:

```text
applicationOverrides
        |
        v
regionalSettings
        |
        v
globalDefaults
        |
        v
mockProperties
```

Kết quả:

```java
env.getProperty("feature.limit")   // "50"
env.getProperty("feature.region")  // "SEA"
```

Nếu đặt `regionalSettings` **trước** `applicationOverrides`:

```java
sources.addBefore("applicationOverrides", new MapPropertySource(
        "urgentRegionalRules",
        Map.of("feature.limit", 70)
));
```

thì `feature.limit` trở thành `"70"`. Lý do là `urgentRegionalRules` được đặt trước source trước đây có giá trị `50`.

### 8.1. Chèn nguồn an toàn khi không chắc tên neo tồn tại

Ví dụ:

```java
String anchor = "applicationOverrides";

if (sources.contains(anchor)) {
    sources.addAfter(anchor, new MapPropertySource(
            "regionalDefaults",
            Map.of("feature.currency", "VND")
    ));
} else {
    sources.addLast(new MapPropertySource(
            "regionalDefaults",
            Map.of("feature.currency", "VND")
    ));
}
```

Ý nghĩa fallback `addLast` ở đây là **ưu tiên thấp**. Nhưng trong dự án thật, không phải mọi missing anchor đều nên được xử lý im lặng. Nếu thiết kế yêu cầu source phải nằm ngay sau một nguồn quan trọng, thiếu anchor có thể là lỗi cấu hình nên dừng khởi động.

Cần quyết định chính sách rõ ràng: *thiếu anchor thì thêm thấp, bỏ qua hay fail fast?*

## 9. replace và remove: thay nguồn, không chỉ thêm giá trị

`MutablePropertySources` cũng hỗ trợ thay hoặc gỡ nguồn.

Ví dụ:

```java
import java.util.Map;
import org.springframework.core.env.MapPropertySource;
import org.springframework.mock.env.MockEnvironment;

MockEnvironment env = new MockEnvironment();

env.getPropertySources().addFirst(new MapPropertySource(
    "currentRules",
    Map.of("rules.max-items", 10,
           "rules.enabled", true)
));

System.out.println(env.getProperty("rules.max-items")); // 10

env.getPropertySources().replace(
    "currentRules",
    new MapPropertySource(
        "currentRules",
        Map.of("rules.max-items", 25,
               "rules.enabled", false)
    )
);

System.out.println(env.getProperty("rules.max-items")); // 25

env.getPropertySources().remove("currentRules");

System.out.println(env.getProperty("rules.max-items")); // null
```

Trong đoạn này:

- `replace` thay **source đã được đăng ký** theo tên.
- `remove` gỡ toàn bộ source mang tên tương ứng.
- Sau khi gỡ, nếu không có nguồn nào khác cung cấp `rules.max-items`, `getProperty(...)` trả về `null`.
- Nếu có nguồn thấp hơn cung cấp cùng khóa, resolver có thể tiếp tục thấy giá trị từ nguồn thấp hơn thay vì `null`.

Đây là thay đổi **cấu trúc danh sách nguồn**, không phải thay đổi trực tiếp một dòng trong YAML.

### 9.1. Vì sao không nên dùng replace để sửa nguồn tích hợp?

Những nguồn như system properties, environment variables và Config Data có thể được thành phần khác kỳ vọng tồn tại. Thay thế một nguồn tích hợp bằng Map tùy ý có thể:

- Làm mất những khóa mà thư viện đang sử dụng.
- Bỏ qua cơ chế tra cứu đặc biệt của source cũ.
- Tạo khác biệt giữa môi trường test và production.
- Khiến chẩn đoán về thứ tự ưu tiên khó hơn.
- Gây tác động tới cấu hình runtime ở những chỗ không liên quan.

Thông thường, nếu muốn override một vài khóa, **thêm một PropertySource mới với các khóa đó** là lựa chọn rõ ràng và ít rủi ro hơn thay toàn bộ nguồn cũ.

## 10. PropertySource không phải Map trộn tất cả nguồn

Hãy phân biệt hai cấu trúc:

```text
A. PropertySource A
   { "shop.currency": "VND", "shop.limit": 10 }

B. PropertySource B
   { "shop.currency": "USD", "shop.region": "global" }

MutablePropertySources:
   [ A, B ]
```

Kết quả của `Environment`:

```text
shop.currency -> VND
shop.limit    -> 10
shop.region   -> global
```

Tuy nhiên, đó **không đồng nghĩa** với việc Spring Boot tạo một Map vật lý duy nhất rồi ghi đè bản đồ ban đầu. `Environment` thường thực hiện việc giải quyết giá trị qua một tập các `PropertySource` theo thứ tự.

Việc giữ các nguồn riêng có những lợi ích:

1. Giải thích được giá trị đến từ nguồn nào khi có công cụ chẩn đoán phù hợp.
2. Cho phép thêm hoặc gỡ một nhóm thuộc tính như một đơn vị.
3. Hỗ trợ các implementation có cách tra cứu riêng, không nhất thiết enumerable.
4. Bảo toàn quyền quản lý nguồn theo module, thư viện hoặc giai đoạn khởi động.
5. Hỗ trợ một số cơ chế thứ tự ưu tiên và chuyển đổi giá trị chuyên biệt.

Nếu một PropertySource được xây từ Map có thể thay đổi, việc thay đổi Map bên dưới có thể tác động đến kết quả tra cứu tùy implementation. Nhưng cách đó thường khó kiểm soát hơn một chiến lược cập nhật có chủ đích và không tự bảo đảm các bean đã bind sẽ cập nhật.

## 11. Viết một PropertySource tùy biến

`MapPropertySource` phù hợp với dữ liệu đã có sẵn trong một Map. Nếu cần quyết định giá trị bằng logic riêng khi một khóa được hỏi, có thể kế thừa `PropertySource<T>`.

Ví dụ một source chỉ cung cấp hai khóa tính toán cố định, không truy cập mạng:

```java
package com.example.config;

import org.springframework.core.env.PropertySource;

public final class CalculatedPropertySource
        extends PropertySource<String> {

    public CalculatedPropertySource(String deploymentId) {
        super("calculatedDeployment", deploymentId);
    }

    @Override
    public Object getProperty(String name) {
        if ("deployment.instance-name".equals(name)) {
            return "worker-" + getSource();
        }

        if ("deployment.features.audit".equals(name)) {
            return "true";
        }

        return null;
    }
}
```

Cách đăng ký:

```java
sources.addLast(new CalculatedPropertySource("blue"));
```

Khi không có nguồn ưu tiên cao hơn cung cấp những khóa đó:

```text
deployment.instance-name  -> worker-blue
deployment.features.audit -> true
```

Vì `getProperty` trả `null` cho khóa không hỗ trợ, resolver sẽ tiếp tục tìm ở nguồn bên dưới.

### 11.1. Đặc điểm của một source tùy biến tốt

Một `PropertySource` tùy biến nên:

- Có tên **duy nhất, ổn định và có ý nghĩa**.
- Trả `null` khi không quản lý khóa.
- Có kết quả xác định cho cùng đầu vào trong một lần khởi tạo ứng dụng, nếu không có nhu cầu động thật sự.
- Tránh thực hiện IO nặng hoặc truy vấn mạng trong mỗi lần `getProperty`.
- Không log secret khi có ai đó tra cứu khóa nhạy cảm.
- Có cơ chế đồng bộ/đảm bảo thread safety nếu dữ liệu nền thay đổi đồng thời.
- Phân biệt giá trị thực sự vắng mặt với chuỗi rỗng.
- Có test độc lập cho những khóa hỗ trợ và không hỗ trợ.

Nếu một source phải gọi secret store hoặc API từ xa mỗi lần property được đọc, hãy cân nhắc vòng đời, cache, timeout và cơ chế failover. Việc gọi mạng trong `getProperty` có thể xảy ra trong **giai đoạn khởi động ứng dụng**, khiến lỗi từ bên ngoài cản trở tạo context.

Thông thường, nên thu thập dữ liệu cần thiết một lần ở giai đoạn phù hợp, sau đó đưa chúng vào một `MapPropertySource` có thể kiểm soát.

## 12. Kết hợp nguồn cấu hình với @ConfigurationProperties

Một khóa được `Environment` tìm thấy vẫn cần được bind vào đối tượng Java đúng cách.

Ví dụ:

```java
package com.example.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "shop")
public record ShopProperties(
        String currency,
        int maxItems,
        boolean enabled
) {}
```

Trong ứng dụng:

```java
@SpringBootApplication
@EnableConfigurationProperties(ShopProperties.class)
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

Những import cần có:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
```

Ta có thể cấp những khóa:

```text
shop.currency
shop.max-items
shop.enabled
```

bằng một source mới, ví dụ:

```java
new MapPropertySource(
    "shopRegionalDefaults",
    Map.of(
        "shop.currency", "VND",
        "shop.max-items", "30",
        "shop.enabled", "true"
    )
)
```

Nếu source được đăng ký **đủ sớm** và không bị nguồn ưu tiên cao hơn ghi đè, Binder có thể liên kết ba giá trị đó vào `ShopProperties`, chuyển ``"30"`` thành `int 30` và ``"true"`` thành `boolean true`.

### 12.1. Đọc Environment trực tiếp khác với binder

`Environment.getProperty("shop.max-items")` thực hiện tra cứu một tên property. `@ConfigurationProperties` của Spring Boot có thêm cơ chế relaxed binding và conversion cho tên thuộc tính và kiểu Java.

Ví dụ Java field `maxItems` có thể bind từ tên canonical `shop.max-items`. Nhưng đừng giả định mọi custom PropertySource đều tự được Spring hiểu như một nguồn Config Data với toàn bộ metadata, nguồn gốc và quy tắc chuẩn hóa giống nhau.

Khi bạn tự tạo tên property, nên dùng **canonical lowercase kebab-case** như `shop.max-items`, `shop.delivery-timeout` để phù hợp với cấu trúc chuẩn của Boot.

### 12.2. Đăng ký source sau khi bean đã tạo không làm tự rebind

Giả sử `ShopProperties` đã được tạo với `maxItems=20`. Một `ApplicationRunner` thêm:

```java
environment.getPropertySources().addFirst(
    new MapPropertySource(
        "lateOverride",
        Map.of("shop.max-items", "99")
    )
);
```

Lệnh `environment.getProperty("shop.max-items")` sau đó có thể thấy `99`, nhưng `shopProperties.maxItems()` có thể vẫn là `20` vì record đã được tạo ở trước đó. **Không dùng ApplicationRunner làm cách chính thức cấp những giá trị mà chính các bean khởi động cần nhận.**

Để bổ sung nguồn trước khi các bean cấu hình được khởi tạo, hãy dùng điểm mở rộng phù hợp như `EnvironmentPostProcessor`.

## 13. Thời điểm mở rộng Environment trong vòng đời Spring Boot

Một mô hình khởi động đơn giản hóa:

```text
SpringApplication.run(...)
          |
          v
Tạo và chuẩn bị Environment
          |
          v
EnvironmentPostProcessor / Config Data processing
          |
          v
Chuẩn bị ApplicationContext
          |
          v
Bean definitions + binding @ConfigurationProperties
          |
          v
Khởi tạo bean và dependency injection
          |
          v
ApplicationRunner / CommandLineRunner
          |
          v
Ứng dụng phục vụ yêu cầu
```

Sơ đồ lược giản này nêu mục đích chọn điểm mở rộng; thứ tự sự kiện chi tiết phụ thuộc phiên bản Spring Boot.

Về ý tưởng:

- **`EnvironmentPostProcessor`** thích hợp để thêm `PropertySource` trong giai đoạn chuẩn bị môi trường, **trước khi context tạo các bean thông thường**.
- **`ApplicationContextInitializer`** cũng có thể tùy chỉnh context/environment trước refresh, nhưng cần cân nhắc rằng một số quyết định như logging hoặc xử lý Config Data có thể đã xảy ra.
- **`@PropertySource`** trên một `@Configuration` được xử lý trong giai đoạn đăng ký cấu hình của context; nó thường **quá muộn** cho một số thuộc tính mà Spring Boot cần đọc từ rất sớm.
- **`ApplicationRunner`** diễn ra sau khi context khởi tạo. Nó phù hợp để **quan sát** hoặc minh họa, không phải nơi lý tưởng để thay những giá trị đã được bean tiêu thụ.

Nếu một thuộc tính ảnh hưởng tới `spring.main.*`, logging hoặc lựa chọn vị trí nạp cấu hình, thời điểm cấp nó đặc biệt quan trọng. Nguồn được thêm quá muộn có thể không ảnh hưởng tới quyết định đã được thực hiện.

## 14. Dùng EnvironmentPostProcessor để thêm defaults

Ví dụ thực hành: ứng dụng muốn cung cấp một số mặc định dành cho khu vực hoạt động, nhưng không ghi đè dữ liệu do người triển khai cung cấp.

Ta tạo một `EnvironmentPostProcessor` thêm source **vào cuối danh sách**.

### 14.1. Class RegionDefaultsEnvironmentPostProcessor

```java
package com.example.config;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.MutablePropertySources;

public final class RegionDefaultsEnvironmentPostProcessor
        implements EnvironmentPostProcessor {

    public static final String SOURCE_NAME =
            "regionDefaultPropertySource";

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application) {

        MutablePropertySources sources =
                environment.getPropertySources();

        if (sources.contains(SOURCE_NAME)) {
            return;
        }

        MapPropertySource defaults = new MapPropertySource(
                SOURCE_NAME,
                Map.of(
                    "shop.currency", "VND",
                    "shop.max-items", "30",
                    "shop.enabled", "true"
                )
        );

        sources.addLast(defaults);
    }
}
```

Quan sát:

- Processor nhận `ConfigurableEnvironment` và `SpringApplication`.
- Source được đặt tên riêng `regionDefaultPropertySource`.
- `contains` hạn chế việc đăng ký trùng tên nếu processor bị gọi lại trong một hoàn cảnh đặc biệt.
- `addLast` diễn đạt chính sách: **đây là fallback có ưu tiên thấp**, không phải override bắt buộc.
- Dữ liệu cố định trong `Map.of` có tính minh họa. Ứng dụng thật có thể nạp từ nguồn được kiểm soát và xử lý lỗi đầu vào.

### 14.2. Đăng ký EnvironmentPostProcessor

Trong nhiều phiên bản Spring Boot 3.x, `EnvironmentPostProcessor` được đăng ký qua:

```text
src/main/resources/META-INF/spring.factories
```

Nội dung:

```properties
org.springframework.boot.env.EnvironmentPostProcessor=\
com.example.config.RegionDefaultsEnvironmentPostProcessor
```

Dấu `\` ở cuối dòng thứ nhất dùng để nối dòng trong file Java properties. Cũng có thể viết nguyên một dòng nếu muốn.

Đây là **cơ chế đăng ký processor khi khởi động**, không phải khai báo bean qua `@Component` hoặc `@Bean`. Một processor dùng để chuẩn bị môi trường trước khi context dựng bean; không nên dựa vào việc component scanning tạo nó sau đó.

Với các thế hệ Spring Boot khác, phải đối chiếu cơ chế đăng ký extension point đang được phiên bản dự án hỗ trợ. Ví dụ trên mô tả quy trình thường gặp ở Spring Boot 3.

### 14.3. Thử với file YAML

```yaml
# application.yml
shop:
  currency: USD
  enabled: false
```

Source mặc định cung cấp:

```text
shop.currency = VND
shop.max-items = 30
shop.enabled = true
```

Nếu các nguồn Config Data có ưu tiên cao hơn `regionDefaultPropertySource`:

```text
shop.currency  -> USD    (từ YAML)
shop.enabled   -> false  (từ YAML)
shop.max-items -> 30     (từ nguồn fallback)
```

Đây là hành vi mong đợi của một nguồn mặc định. Người triển khai chỉ cần khai báo những giá trị muốn thay đổi; các khóa chưa được cấp nhận mặc định từ source bổ sung.

### 14.4. Dùng addFirst khi nào?

Nếu một yêu cầu thật sự cần khóa từ source mới **thắng những nguồn hiện tại**, có thể dùng `addFirst`. Tuy nhiên, nên cân nhắc kỹ:

```java
sources.addFirst(new MapPropertySource(
    "forcedPolicy",
    Map.of("shop.enabled", "false")
));
```

Cách này có thể làm `--shop.enabled=true` trên dòng lệnh không còn thắng được source `forcedPolicy`, tùy danh sách nguồn tại thời điểm áp dụng. Trong sản phẩm thật, việc bất ngờ ghi đè lựa chọn của người triển khai có thể gây khó chẩn đoán.

Với **mặc định**, dùng `addLast` hoặc một vị trí thấp được thiết kế rõ ràng. Với **chính sách bắt buộc**, giải thích rõ vì sao nguồn mới phải được ưu tiên và kiểm tra ảnh hưởng tới những nguồn còn lại.

## 15. Thứ tự giữa các EnvironmentPostProcessor

Một ứng dụng có thể có nhiều processor:

```text
Config Data processor
Library defaults processor
Deployment-specific processor
Organization policy processor
...
```

Thứ tự thực thi processor và thứ tự cuối cùng của các `PropertySource` là **hai điều cần phân biệt**:

1. Thứ tự processor quyết định **ai có cơ hội chỉnh sửa môi trường lúc nào**.
2. Thứ tự source trong `MutablePropertySources` quyết định **khóa nào thắng khi tra cứu**.

Một processor chạy sau **không đồng nghĩa** source do nó thêm phải có ưu tiên cao hơn. Nó vẫn có thể gọi `addLast` để đặt nguồn cuối danh sách.

Với class implements `Ordered`, có thể nêu thứ tự mong muốn:

```java
import org.springframework.core.Ordered;

public final class RegionDefaultsEnvironmentPostProcessor
        implements EnvironmentPostProcessor, Ordered {

    @Override
    public int getOrder() {
        return Ordered.LOWEST_PRECEDENCE - 100;
    }

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application) {
        // Thêm PropertySource tại đây
    }
}
```

Đây là minh họa API; nếu ghép với ví dụ hoàn chỉnh ở phần trước, cần giữ lại phần import, constructor và logic cần thiết. **Không coi con số `-100` so với `LOWEST_PRECEDENCE` là một quy tắc chuẩn cho mọi extension point.** Khi project cần can thiệp trước/sau Config Data, phải kiểm tra thứ tự processor thực tế và các constant của phiên bản Boot đang dùng.

Tránh thực thi logic phụ thuộc vào config được nạp **sau** processor của mình. Ví dụ một processor chạy trước Config Data có thể chưa nhìn thấy một property nằm trong `application.yml`.

Nếu yêu cầu là tạo một nguồn cấu hình tích hợp vào chính cơ chế Config Data, cần nghiên cứu các extension point chuyên dụng hơn; không phải mọi nhu cầu import config đều nên xử lý bằng `EnvironmentPostProcessor` đơn giản.

## 16. @PropertySource và PropertySource trong Environment khác nhau ra sao?

`@PropertySource` là annotation Spring Framework để thêm một nguồn từ tài nguyên khi một class `@Configuration` được xử lý.

Ví dụ:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.PropertySource;

@Configuration
@PropertySource("classpath:shipping-defaults.properties")
public class ShippingDefaultsConfiguration {
}
```

Trong `shipping-defaults.properties`:

```properties
shipping.connect-timeout=3s
shipping.max-attempts=4
```

Annotation giúp thêm các thuộc tính từ file `.properties` vào `Environment` ở một giai đoạn xử lý context. Cần phân biệt:

| Cơ chế | Thời điểm/mục đích |
| --- | --- |
| `@PropertySource` | Đăng ký nguồn theo cấu hình của Spring context |
| `EnvironmentPostProcessor` | Thay đổi environment trong quá trình chuẩn bị ứng dụng |
| `application.yml` / `spring.config.import` | Nguồn Config Data do Spring Boot xử lý |
| `MutablePropertySources.addFirst/addLast` | Thao tác trực tiếp trên tập nguồn, tại điểm mã được gọi |

Một lưu ý: `@PropertySource` thông dụng không tự xử lý YAML theo cùng cơ chế như Config Data của Spring Boot. Nếu muốn dùng YAML trong `@PropertySource`, có thể cần `PropertySourceFactory` phù hợp. Với cấu hình ứng dụng Spring Boot thông thường, **`application.yml` và Config Data** là cách tích hợp tự nhiên hơn.

Đặc biệt, `@PropertySource` thường được xử lý quá muộn đối với một số thuộc tính khởi động rất sớm, chẳng hạn những thiết lập cần trước khi context được refresh. Vì vậy, không chọn annotation này cho mọi mục tiêu “mở rộng Environment”.

## 17. Không sửa Environment tùy tiện trong @Bean hoặc service

Đoạn dưới đây có thể làm thay đổi cách tra cứu property về sau:

```java
@Service
public class ShippingService {

    public ShippingService(ConfigurableEnvironment environment) {
        environment.getPropertySources().addFirst(
            new MapPropertySource(
                "shippingRuntimeOverride",
                Map.of("shipping.max-attempts", "99")
            )
        );
    }
}
```

Nhưng đây là thiết kế đáng tránh vì:

- Thứ tự tạo bean ảnh hưởng kết quả cấu hình.
- Một bean nghiệp vụ can thiệp vào phần hạ tầng cấu hình chung.
- Những bean đã được tạo trước đó có thể có giá trị cũ.
- Một số bean khác có thể được tạo sau và nhận giá trị mới, dẫn tới trạng thái không đồng nhất.
- Kiểm thử service trở nên phụ thuộc nhiều vào container.
- Hành vi khác nhau giữa các lần khởi động nếu thứ tự dependency thay đổi.

Service nên nhận dữ liệu qua `@ConfigurationProperties` hoặc những dependency có kiểu. Nếu cần thay nguồn cấu hình toàn ứng dụng, hãy thực hiện tại **lớp cấu hình/extension point được chọn có chủ đích**.

Cách tách trách nhiệm:

```text
EnvironmentPostProcessor
        |
        v
MapPropertySource
        |
        v
ConfigurableEnvironment
        |
        v
Spring Boot Binder
        |
        v
ShippingProperties
        |
        v
ShippingService
```

Lớp nghiệp vụ chỉ dùng giá trị đã được cung cấp, không sở hữu cơ chế quyết định thứ tự nguồn.

## 18. Điểm khác nhau giữa “thay nguồn” và “refresh bean”

Giả sử một lần khởi động tạo bean:

```java
@ConfigurationProperties(prefix = "service")
public record ServiceProperties(int retryLimit) {}
```

với `service.retry-limit=3`.

Sau khi context chạy, một đoạn mã thay nguồn bằng:

```java
environment.getPropertySources().addFirst(
    new MapPropertySource(
        "newRuntimeSettings",
        Map.of("service.retry-limit", "8")
    )
);
```

Hai quan sát có thể khác nhau:

```java
environment.getProperty("service.retry-limit"); // "8"
serviceProperties.retryLimit();                  // 3
```

Đây không phải bug của Binder. Bean `ServiceProperties` đã được dựng và ràng buộc ở trạng thái trước; record không tự được tạo lại.

Trong ứng dụng có thể có thêm:

- Bean dùng `@Value` đã được injection.
- Client được dựng từ timeout lúc khởi động.
- Bean hạ tầng đọc cấu hình trong constructor.
- Code gọi `Environment` trực tiếp ở mỗi lần sử dụng.

Các thành phần có **thời điểm quan sát cấu hình** khác nhau. Vì vậy, thay nguồn động mà không có cơ chế refresh đồng bộ có thể dẫn đến các cấu hình không nhất quán.

Nếu hệ thống cần thay cấu hình trong lúc chạy, phải thiết kế rõ ràng: snapshot, quản lý vòng đời, tái tạo client, đồng bộ giữa thread, refresh scope hoặc nền tảng quản lý cấu hình chuyên dụng. `MutablePropertySources` đơn thuần **không cung cấp** một giao thức refresh toàn ứng dụng.

## 19. Thứ tự PropertySource ảnh hưởng tới placeholder thế nào?

Giả sử có hai nguồn:

```text
highPriority:
  api.host = prod.internal

lowPriority:
  api.host = localhost
  api.url  = http://${api.host}:8080
```

Khi `Environment` giải quyết `api.url`, nó lấy công thức từ nguồn thấp vì nguồn cao không khai `api.url`; bên trong công thức, `${api.host}` thường được giải quyết từ toàn bộ `Environment`. Vì thế host có thể là `prod.internal`.

Kết quả mong đợi:

```text
http://prod.internal:8080
```

Điều này có ý nghĩa:

- Source chứa công thức không nhất thiết phải chứa giá trị cuối cùng của mọi placeholder.
- Placeholder có thể tham chiếu những khóa đã bị nguồn khác ghi đè.
- Khi muốn hiểu một URL cuối cùng, cần kiểm tra **khóa URL** và **các khóa thành phần** theo thứ tự ưu tiên.
- Nếu nguồn cao ghi đè trực tiếp `api.url`, công thức ở nguồn thấp không còn là giá trị đích được lựa chọn.

Một ví dụ test:

```java
MockEnvironment env = new MockEnvironment();
MutablePropertySources sources = env.getPropertySources();

sources.addLast(new MapPropertySource(
    "urlTemplate",
    Map.of(
        "api.host", "localhost",
        "api.url", "http://${api.host}:8080"
    )
));

sources.addFirst(new MapPropertySource(
    "hostOverride",
    Map.of("api.host", "prod.internal")
));

System.out.println(env.getProperty("api.url"));
```

Với cơ chế placeholder resolution được cấu hình trong Spring `Environment`, kết quả là `http://prod.internal:8080`.

## 20. Chẩn đoán: in thứ tự nguồn mà không làm lộ giá trị

Một công cụ chẩn đoán an toàn nên tập trung vào **tên nguồn, vị trí và tên khóa đã cho trước**, không in toàn bộ giá trị.

Ví dụ:

```java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

public final class PropertySourceInspector {

    private PropertySourceInspector() {}

    public static void printNames(ConfigurableEnvironment env) {
        int index = 0;

        for (PropertySource<?> source : env.getPropertySources()) {
            System.out.println(
                index + " : " + source.getName()
            );
            index++;
        }
    }

    public static void printPresence(
            ConfigurableEnvironment env,
            String key) {

        for (PropertySource<?> source : env.getPropertySources()) {
            if (source.containsProperty(key)) {
                System.out.println(
                    "found in " + source.getName()
                );
                return;
            }
        }

        System.out.println("key not found in listed sources");
    }
}
```

`printPresence` chỉ mang tính quan sát. Nó không in giá trị. Ngoài ra, vì một số nguồn có quy tắc lookup riêng hoặc converter liên quan, việc tự duyệt và gọi `containsProperty` không luôn phản ánh đầy đủ mọi ngữ nghĩa đặc biệt của Binder.

**Không dùng công cụ này như một bằng chứng tuyệt đối cho mọi nguồn và mọi kiểu relaxed binding.** Nó phù hợp để tìm hiểu cấu trúc source và những tên khóa cụ thể trong môi trường đã biết.

Trong Spring Boot, Actuator có endpoint `env` để chẩn đoán cấu hình nếu được bật đúng cách. Endpoint này có thể chứa thông tin nhạy cảm và có quy tắc ẩn giá trị. Không mở rộng endpoint chẩn đoán ra mạng công cộng chỉ để xem source order.

## 21. Đừng nhầm index và tên source trong từng phiên bản Spring Boot

Một số bài hướng dẫn đưa ra danh sách cố định:

```text
commandLineArgs
systemProperties
systemEnvironment
applicationConfig: [...]
...
```

Danh sách này có thể chỉ đúng với **một phiên bản Spring Boot hoặc một điều kiện chạy cụ thể**. Spring Boot có cơ chế Config Data, cấu hình import, testing và nhiều nguồn do auto-configuration/thư viện thêm vào.

Một số khác biệt giữa các lần chạy:

- Có hay không có tham số dòng lệnh.
- Có hay không có file cấu hình ngoài JAR.
- Profile nào hoạt động.
- Có `spring.config.import` hay không.
- Có test properties hoặc `@DynamicPropertySource` hay không.
- Có `EnvironmentPostProcessor` của thư viện hay không.
- Chạy web servlet, reactive, test hay ứng dụng console.

Khi chèn source bằng `addBefore` hoặc `addAfter`, hãy dựa trên **tên source thực tế đã được xác định ở đúng thời điểm mở rộng**. Không gắn cứng một tên source Config Data có chi tiết đường dẫn và kỳ vọng nó tồn tại mọi nơi.

Nếu mục tiêu chỉ là fallback, `addLast` thường ít phụ thuộc vào tên source nội bộ hơn.

## 22. Source có cùng khóa nhưng value là chuỗi rỗng

Một trường hợp dễ bị hiểu sai:

```text
highPriority:
  app.display-name = ""

lowPriority:
  app.display-name = "Default App"
```

Khi `Environment` tra cứu `app.display-name`, nguồn ưu tiên cao có thể trả **chuỗi rỗng**; chuỗi rỗng vẫn là giá trị khác `null`. Kết quả thường là `""`, không phải `"Default App"`.

Để minh họa:

```java
MockEnvironment env = new MockEnvironment();
MutablePropertySources sources = env.getPropertySources();

sources.addLast(new MapPropertySource(
    "fallback",
    Map.of("app.display-name", "Default App")
));

sources.addFirst(new MapPropertySource(
    "explicitEmpty",
    Map.of("app.display-name", "")
));

System.out.println(
    "[" + env.getProperty("app.display-name") + "]"
);
```

Kết quả:

```text
[]
```

Điểm cần nhớ: **PropertySource trả `null` thường khiến resolver tiếp tục tìm**, trong khi chuỗi rỗng có thể ngăn fallback. Nếu một giá trị phải khác rỗng, hãy kiểm tra bằng validation hoặc quy tắc nghiệp vụ, không chỉ tin vào việc đặt một nguồn có mặc định ở cuối.

## 23. Một số giá trị không thể trực tiếp dùng Map.of

`Map.of(...)` trong Java không cho phép key hoặc value `null`. Khi nguồn dữ liệu động có giá trị thiếu, cố tạo Map qua `Map.of("key", null)` sẽ gây lỗi lập tức, trước cả lúc Spring bind.

Nếu bạn cần cấu trúc có thể chứa `null` trong quá trình chuẩn bị dữ liệu:

```java
Map<String, Object> values = new HashMap<>();
values.put("shop.currency", "VND");
// Không nên thêm key với null chỉ để đánh dấu thiếu.
```

Một `MapPropertySource` có thể nhận dữ liệu từ Map thay đổi được, nhưng **giá trị `null` thường mang ý nghĩa không có property** trong quá trình resolution. Nếu muốn cấu hình mặc định, tốt hơn là không đưa những khóa chưa có giá trị vào nguồn, hoặc quyết định default tại chỗ phù hợp.

Trong ứng dụng đa luồng, không nên chia sẻ một `HashMap` thay đổi liên tục rồi để nhiều thread tra cứu trực tiếp mà không có biện pháp đồng bộ. Với cấu hình gần như bất biến, tạo snapshot và đăng ký nguồn một lần sẽ đơn giản hơn.

## 24. Khi nào dùng ConfigurableEnvironment thay vì Environment?

Một quy tắc thiết kế hữu ích:

- Bean nghiệp vụ cần đọc một vài giá trị: ưu tiên **`@ConfigurationProperties`** hoặc các dependency có kiểu.
- Một đoạn mã chỉ cần tra cứu tên property: dùng **`Environment`** nếu phù hợp.
- Một extension point cần **thêm hoặc sắp xếp PropertySource**: dùng **`ConfigurableEnvironment`**.
- Một component cần xây một nguồn đặc biệt: viết **`PropertySource`** hoặc dùng **`MapPropertySource`**, sau đó đăng ký ở thời điểm thích hợp.
- Test cần thay thế cấu hình có kiểm soát: dùng **`MockEnvironment`**, `ApplicationContextRunner` hoặc cơ chế test properties của Spring Boot.

Không nên inject `ConfigurableEnvironment` vào mọi service chỉ vì interface này cung cấp nhiều chức năng. Quyền thay đổi nguồn cấu hình toàn ứng dụng là trách nhiệm hạ tầng; trao nó cho nhiều bean nghiệp vụ khiến code khó dự đoán.

## 25. Unit test thứ tự ưu tiên bằng MockEnvironment

Một bài test dùng JUnit 5 và AssertJ:

```java
package com.example.config;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.MutablePropertySources;
import org.springframework.mock.env.MockEnvironment;

class PropertySourcesPriorityTest {

    @Test
    void firstPropertySourceWins() {
        MockEnvironment env = new MockEnvironment()
                .withProperty("feature.limit", "20");

        MutablePropertySources sources = env.getPropertySources();

        sources.addLast(new MapPropertySource(
            "defaults",
            Map.of("feature.limit", "10",
                   "feature.name", "catalog")
        ));

        assertThat(env.getProperty("feature.limit"))
                .isEqualTo("20");
        assertThat(env.getProperty("feature.name"))
                .isEqualTo("catalog");

        sources.addFirst(new MapPropertySource(
            "overrides",
            Map.of("feature.limit", "50")
        ));

        assertThat(env.getProperty("feature.limit"))
                .isEqualTo("50");
    }

    @Test
    void removingOverrideRevealsLowerPriorityValue() {
        MockEnvironment env = new MockEnvironment()
                .withProperty("feature.limit", "20");

        MutablePropertySources sources = env.getPropertySources();

        sources.addFirst(new MapPropertySource(
            "overrides",
            Map.of("feature.limit", "50")
        ));

        assertThat(env.getProperty("feature.limit"))
                .isEqualTo("50");

        sources.remove("overrides");

        assertThat(env.getProperty("feature.limit"))
                .isEqualTo("20");
    }
}
```

Test này chỉ cần `spring-test` cùng JUnit/AssertJ trong test classpath (thường có trong `spring-boot-starter-test`). Nó không khởi động một Spring Boot application context, không cần file `application.yml` và không làm thay đổi biến môi trường thật.

Một lợi ích của test không dùng Spring context là **không phụ thuộc thứ tự các nguồn mà một phiên bản Boot cụ thể thiết lập**. Ta chủ động xây thứ tự và kiểm tra kết quả của từng thao tác.

## 26. Test addBefore, addAfter và replace

Ví dụ:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.MutablePropertySources;
import org.springframework.mock.env.MockEnvironment;

class MutablePropertySourcesOperationsTest {

    @Test
    void orderAndReplacementAreObservable() {
        MockEnvironment env = new MockEnvironment();
        MutablePropertySources sources = env.getPropertySources();

        sources.addFirst(new MapPropertySource(
            "defaults",
            Map.of("sample.mode", "basic")
        ));

        sources.addBefore("defaults", new MapPropertySource(
            "regional",
            Map.of("sample.mode", "regional")
        ));

        assertThat(env.getProperty("sample.mode"))
                .isEqualTo("regional");

        sources.replace("regional", new MapPropertySource(
            "regional",
            Map.of("sample.mode", "enterprise")
        ));

        assertThat(env.getProperty("sample.mode"))
                .isEqualTo("enterprise");

        sources.remove("regional");

        assertThat(env.getProperty("sample.mode"))
                .isEqualTo("basic");
    }
}
```

Đây là phép thử **cấu trúc danh sách nguồn**. Nó xác nhận rằng nguồn đặt trước được tra cứu trước, thay source theo tên làm đổi kết quả và gỡ nguồn làm lộ giá trị thấp hơn.

Trong ứng dụng thật, không nên gọi `replace` hoặc `remove` theo chu kỳ chỉ vì thao tác này có API. Nếu cần cấu hình động, có thêm vấn đề thread safety và lifecycle của bean.

## 27. Kiểm thử EnvironmentPostProcessor riêng

Không nhất thiết phải chạy JAR để kiểm tra processor thêm nguồn đúng.

Với `RegionDefaultsEnvironmentPostProcessor` ở phần 14, có thể test logic cơ bản:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.SpringApplication;
import org.springframework.mock.env.MockEnvironment;

class RegionDefaultsEnvironmentPostProcessorTest {

    @Test
    void addsOnlyLowPriorityFallbackValues() {
        MockEnvironment env = new MockEnvironment()
                .withProperty("shop.currency", "USD");

        RegionDefaultsEnvironmentPostProcessor processor =
                new RegionDefaultsEnvironmentPostProcessor();

        processor.postProcessEnvironment(
                env, new SpringApplication(Object.class)
        );

        assertThat(env.getProperty("shop.currency"))
                .isEqualTo("USD");
        assertThat(env.getProperty("shop.max-items"))
                .isEqualTo("30");

        assertThat(env.getPropertySources()
                .contains("regionDefaultPropertySource")).isTrue();
    }
}
```

Kiểm thử này chứng minh logic source được đặt thấp hơn `mockProperties`. Tuy nhiên, **nó không thay thế integration test bootstrapping** để kiểm tra file `META-INF/spring.factories` đã được phát hiện, hoặc processor chạy đúng thời điểm so với Config Data trong dự án thật.

Khi cần kiểm tra dây chuyền đầy đủ, hãy chạy một Spring Boot test/application nhỏ và quan sát giá trị đã bind vào `@ConfigurationProperties`. Giữ test đơn vị và test khởi động tách biệt sẽ dễ phân tích lỗi hơn.

## 28. Một chiến lược mở rộng Environment an toàn

Giả sử công ty cần thêm một nguồn mặc định cho nhiều ứng dụng, ví dụ `organizationDefaults`. Nên thiết kế như sau:

1. **Xác định trách nhiệm nguồn**: chỉ cấp những khóa được phép, ví dụ `org.region` và `org.timeout`.
2. **Chọn precedence**: nếu chỉ là mặc định, thêm ở cuối; nếu là chính sách bắt buộc, mô tả rõ tại sao phải có ưu tiên cao.
3. **Tạo source có tên ổn định** và không đụng tên của nguồn framework hoặc thư viện.
4. **Đăng ký tại điểm mở rộng sớm** nếu những bean cần nhận giá trị lúc khởi động.
5. **Không thay toàn bộ source tích hợp** để override một vài khóa.
6. **Không tải dữ liệu nhạy cảm rồi log** Map đã tạo.
7. **Trả null cho khóa không thuộc quyền quản lý** khi viết custom PropertySource.
8. **Kiểm tra những nguồn đã có** trước khi chèn tương đối bằng `addBefore/addAfter`.
9. **Viết unit test precedence** và integration test binding.
10. **Ghi rõ cách gỡ nguồn** hoặc phục hồi cấu hình nếu một extension bị tắt.

Điểm quan trọng là giữ khả năng quan sát và dự đoán được. Một nguồn custom “thắng tất cả” nhưng không được tài liệu hóa có thể khiến những tham số mà người vận hành truyền qua command line bỗng nhiên vô tác dụng.

## 29. Khi nào không nên tạo PropertySource tùy biến?

Không phải yêu cầu cấu hình nào cũng cần mở rộng `ConfigurableEnvironment`.

Nếu mục tiêu là đọc một tệp YAML khác, Spring Boot đã có cơ chế Config Data, đường dẫn cấu hình và `spring.config.import`. Nếu mục tiêu là gom nhiều thuộc tính thành một class, `@ConfigurationProperties` có thể giải quyết mà không cần custom source.

Nếu muốn giá trị mặc định cho vài khóa, đôi khi chỉ cần:

```yaml
# application.yml
shop:
  currency: VND
  max-items: 30
```

Nếu muốn thay theo profile:

```yaml
# application-prod.yml
shop:
  max-items: 50
```

Nếu muốn giá trị theo môi trường triển khai, dùng biến môi trường hoặc tham số dòng lệnh phù hợp. Tất cả các cách này thường đơn giản hơn việc tạo một source mới bằng code.

Chỉ nên cân nhắc `EnvironmentPostProcessor` hoặc PropertySource custom khi thật sự có nhu cầu như:

- Một thư viện muốn cung cấp giá trị mặc định cho nhiều ứng dụng.
- Một hệ thống tích hợp với nguồn cấu hình không thuộc các cơ chế nạp tiêu chuẩn.
- Cần cung cấp một nhóm khóa có cấu trúc riêng vào giai đoạn chuẩn bị môi trường.
- Cần kiểm soát precedence có chủ đích giữa một nguồn tùy biến và những nguồn có sẵn.
- Một sản phẩm cần đóng gói các quy tắc cấu hình hạ tầng thành module có test.

Tránh chọn cơ chế phức tạp hơn chỉ vì nó cho phép can thiệp sâu.

## 30. Một số lỗi thường gặp

### 30.1. Nghĩ addLast luôn thắng

`addLast` đặt nguồn ở cuối danh sách; thông thường nguồn này chỉ cung cấp giá trị khi những nguồn phía trên **không có giá trị** cho khóa tương ứng.

### 30.2. Nghĩ nguồn thêm sau thì ưu tiên cao hơn

Thứ tự đăng ký theo thời gian không quyết định precedence. `addFirst`, `addLast` và các thao tác chèn tương đối mới quyết định vị trí.

### 30.3. Quên tên source là định danh

`addBefore("missingName", custom)` có thể thất bại khi tên neo không tồn tại. Dùng `contains` hoặc thiết kế fail fast rõ ràng.

### 30.4. Dùng @PropertySource cho thuộc tính cần rất sớm

Một số thuộc tính khởi động được xử lý trước khi `@Configuration` được đọc. `@PropertySource` có thể quá muộn để ảnh hưởng đến chúng.

### 30.5. Đăng ký custom source trong service

Điều này khiến business logic phụ thuộc thứ tự khởi tạo bean và trạng thái mutable toàn cục. Hãy sử dụng extension point hạ tầng thích hợp.

### 30.6. Nghĩ sửa PropertySources sẽ refresh @ConfigurationProperties

Việc cập nhật resolver có thể thấy giá trị mới; bean đã bind thường không tự tạo lại. Cần cơ chế refresh riêng nếu muốn cập nhật runtime.

### 30.7. Gọi getProperty trên một source rồi tưởng đó là giá trị cuối cùng

`source.getProperty(key)` chỉ đọc đúng source đó. `environment.getProperty(key)` mới xét thứ tự nhiều nguồn.

### 30.8. In toàn bộ Map nguồn trong log

Một nguồn có thể chứa mật khẩu hoặc token. Hãy in tên nguồn hoặc những khóa vô hại có kiểm soát, không log toàn bộ giá trị.

### 30.9. Dựa vào index nguồn cố định

Ứng dụng có thể thêm Config Data, profile, test sources, command line hoặc library processors. Thứ tự thực tế thay đổi theo môi trường và phiên bản.

### 30.10. Nhầm chuỗi rỗng với không có giá trị

Một source cung cấp `""` có thể ngăn nguồn thấp hơn được chọn. Mặc định ở source cuối không tự sửa chuỗi rỗng.

### 30.11. Cố dùng source custom cho mọi YAML import

Nếu bài toán chỉ là thêm một tệp cấu hình, hãy cân nhắc cơ chế Config Data của Spring Boot trước. Không nên tự viết lại logic nạp tệp, profile và precedence nếu không có yêu cầu đặc biệt.

### 30.12. Bỏ qua sự khác nhau giữa String property và Binder

`Environment.getProperty` và `@ConfigurationProperties` liên quan nhưng không hoàn toàn đồng nghĩa về relaxed binding, conversion và cấu trúc object. Với key custom, cần test cả trường hợp tra cứu trực tiếp và binding.

## 31. Bài tập thực hành

### Bài tập 1: dự đoán thứ tự

Có ba nguồn theo thứ tự:

```text
A: app.mode=alpha, app.region=north
B: app.mode=beta,  app.timeout=2s
C: app.mode=gamma, app.feature=true
```

Hãy dự đoán:

- `app.mode` nhận `alpha`.
- `app.region` nhận `north`.
- `app.timeout` nhận `2s`.
- `app.feature` nhận `true`.

Sau đó thêm nguồn D bằng `addFirst` với `app.mode=delta`. Kết quả mode sẽ thành `delta`.

### Bài tập 2: chọn thao tác đúng

Yêu cầu:

1. Thêm source mặc định thấp nhất.
2. Thêm source ưu tiên cao nhất.
3. Thêm source ngay sau một source đã biết.
4. Thay source cũ theo tên.
5. Gỡ source khi không cần nữa.

Đáp án tương ứng:

```java
sources.addLast(defaults);
sources.addFirst(overrides);
sources.addAfter("knownSource", regional);
sources.replace("oldSource", replacement);
sources.remove("oldSource");
```

Trong trường hợp 3 và 4, cần bảo đảm tên nguồn tồn tại. Trong trường hợp 5, phải xem gỡ source có làm lộ một giá trị khác từ nguồn thấp hơn không.

### Bài tập 3: nguồn chứa chuỗi rỗng

Nguồn cao khai `app.label=""`, nguồn thấp khai `app.label="Default"`. Hãy giải thích tại sao kết quả thường là chuỗi rỗng, không phải `Default`, và cơ chế validation nào có thể phù hợp nếu label bắt buộc có nội dung.

### Bài tập 4: custom PropertySource

Viết một `PropertySource<String>` trả `"acme-" + getSource()` cho khóa `app.instance-id`, trả `null` cho mọi khóa khác. Đăng ký bằng `addLast` và kiểm tra có thể tra cứu từ `Environment` khi không có nguồn cao hơn.

### Bài tập 5: EnvironmentPostProcessor

Tạo `RegionDefaultsEnvironmentPostProcessor` với:

```text
shop.currency = VND
shop.max-items = 30
```

Dùng `addLast`. Đăng ký qua `META-INF/spring.factories` theo phiên bản dự án, rồi chạy với YAML chỉ khai `shop.currency=USD`. Dự đoán đối tượng properties nhận currency USD, maxItems 30.

### Bài tập 6: đổi nguồn sau khi context đã chạy

Một bean `@ConfigurationProperties` đã bind `shop.max-items=20`. Sau đó thêm source đầu danh sách cung cấp `99`. Hãy so sánh `Environment.getProperty("shop.max-items")` với `ShopProperties.maxItems()`. Vì sao cần tách runtime lookup với snapshot đã bind?

### Bài tập 7: thay nguồn

Tạo nguồn `rulesDefaults` cung cấp `rules.limit=10`, rồi gọi `replace("rulesDefaults", ...)` để cung cấp `25`. Sau đó gọi `remove("rulesDefaults")`. Giải thích giá trị cuối cùng khi có và khi không có một nguồn khác cung cấp `rules.limit`.

### Bài tập 8: phát hiện thiết kế nguy hiểm

Một service có constructor thêm source ưu tiên cao với khóa `spring.main.banner-mode`. Hãy giải thích:

- Tại sao thời điểm tạo service là quá muộn để chắc chắn thay đổi thiết lập khởi động?
- Tại sao service không nên thay môi trường toàn ứng dụng?
- Extension point nào phù hợp hơn nếu thật sự cần cấp một thuộc tính rất sớm?
- Vì sao cần kiểm thử precedence và không ghi đè tùy tiện nguồn mặc định?

### Bài tập 9: tìm nguồn gây override

Có YAML đặt `service.timeout=2s` nhưng chương trình nhận `5s`. Hãy nêu trình tự chẩn đoán:

1. Đọc tên các source theo thứ tự.
2. Kiểm tra có tham số dòng lệnh, system property, biến môi trường hoặc nguồn custom nào cung cấp khóa không.
3. Kiểm tra source đứng trước YAML.
4. Kiểm tra khóa đích và các placeholder phụ thuộc.
5. Kiểm tra bean đã được binding ở thời điểm nào.
6. Tránh in secret khi dò nguồn.

### Bài tập 10: phân biệt hai điểm mở rộng

Tạo hai giải pháp:

- Thêm `defaults.properties` qua `@PropertySource`.
- Thêm `MapPropertySource` qua `EnvironmentPostProcessor`.

Giải thích vì sao hai cách có thể khác nhau về **thời điểm** dữ liệu có mặt trong môi trường, và tại sao một số thuộc tính cần sớm không nên được xử lý qua `@PropertySource`.

## 32. Tổng kết

`PropertySource`, `MutablePropertySources` và `ConfigurableEnvironment` tạo thành một mô hình mở rộng cấu hình mạnh mẽ của Spring.

```text
PropertySource<T>
  -> một nguồn tra cứu theo khóa

MutablePropertySources
  -> tập nguồn có thứ tự, thêm/thay/gỡ được

ConfigurableEnvironment
  -> Environment có khả năng cấu hình nguồn
     và các thuộc tính môi trường khác
```

Những quy tắc cốt lõi:

1. **Nguồn đứng trước có ưu tiên cao hơn** trong trình tự tra cứu thông thường.
2. **`addFirst` ưu tiên cao; `addLast` ưu tiên thấp.** Không nhầm thời điểm đăng ký với precedence.
3. **`getProperty` trên một source khác với `Environment.getProperty`.** Một bên chỉ tra cứu một nơi; bên kia xét các nguồn theo thứ tự.
4. **Tên PropertySource là định danh để quản lý.** `addBefore`, `addAfter` và `replace` phụ thuộc vào tên đúng.
5. **Nguồn mặc định nên được đặt thấp** để người triển khai còn có thể ghi đè giá trị.
6. **Thêm nguồn đủ sớm** nếu giá trị phải có trước khi `@ConfigurationProperties` hoặc bean hạ tầng được tạo.
7. **Thay nguồn không có nghĩa refresh bean.** Những field đã injection/binding thường vẫn giữ giá trị trước đó.
8. **Mở rộng cấu hình thuộc tầng hạ tầng**, không phải trách nhiệm của service nghiệp vụ.
9. **Chẩn đoán thận trọng**: đọc thứ tự nguồn nhưng không log bí mật.
10. **Ưu tiên cơ chế Config Data sẵn có** nếu yêu cầu chỉ là nạp tệp cấu hình thông thường.

Cách hình dung tốt nhất:

```text
          [Nguồn thuộc tính]
         /        |         \
       CLI      YAML      Custom
         \        |         /
          v       v        v
         MutablePropertySources
                  |
                  v
         ConfigurableEnvironment
                  |
                  v
         Binder / @Value / Bean
```

Khi hiểu rõ chuỗi này, bạn có thể trả lời vì sao một giá trị ghi đè giá trị khác, nơi nên đưa một mặc định mới vào, và tại sao một thao tác sửa `Environment` lúc runtime không tự làm mọi bean thay đổi.

Tài liệu chính thức để học tiếp:

- [Spring Framework — PropertySource API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/env/PropertySource.html)
- [Spring Framework — MutablePropertySources API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/env/MutablePropertySources.html)
- [Spring Framework — ConfigurableEnvironment API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/env/ConfigurableEnvironment.html)
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot — EnvironmentPostProcessor API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/env/EnvironmentPostProcessor.html)
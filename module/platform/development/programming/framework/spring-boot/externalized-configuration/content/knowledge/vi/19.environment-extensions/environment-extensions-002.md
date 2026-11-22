# Thêm nguồn bằng addFirst, addLast, addBefore và addAfter

## 1. Bối cảnh: Vì sao cần mở rộng Spring Environment?

Spring Boot cho phép đưa cấu hình ra bên ngoài mã nguồn bằng nhiều nguồn như:

- `application.yml` và `application.properties`;
- các tệp cấu hình dành cho từng profile;
- biến môi trường của tiến trình;
- Java system properties;
- đối số dòng lệnh;
- nguồn được nạp qua cơ chế Config Data;
- các nguồn do ứng dụng hoặc thư viện tích hợp tự bổ sung.

Khi triển khai hệ thống thực tế, đôi khi một ứng dụng còn cần đọc cấu hình từ **một nơi riêng**: bảng thiết lập của tenant, cơ sở dữ liệu cấu hình, một tệp do công ty quản lý, một nguồn giá trị trong bộ nhớ hoặc một thư viện tích hợp.

Spring Framework có cấu trúc `Environment` và `PropertySource` để đại diện cho những nguồn đó. Một `PropertySource` chứa một tập thuộc tính có tên, còn `Environment` cung cấp cách tìm giá trị từ nhiều nguồn theo thứ tự ưu tiên.

Ví dụ:

```yaml
# application.yml
demo:
  message: "Giá trị từ YAML"
  retries: 3
```

Ứng dụng có thể muốn thêm một nguồn với:

```text
demo.message = "Giá trị từ tenant"
```

Kết quả cuối cùng phụ thuộc vào **vị trí của nguồn mới** so với những nguồn đã có. Đó là nhiệm vụ của `MutablePropertySources` và bốn thao tác được học trong bài:

- `addFirst(...)`;
- `addLast(...)`;
- `addBefore(...)`;
- `addAfter(...)`.

**Mục tiêu:** biết chính xác bốn phương thức đặt nguồn mới ở đâu, cách chúng ảnh hưởng tới giá trị có hiệu lực, cách tích hợp vào Spring Boot vào đúng thời điểm, và cách tránh vô tình ghi đè cấu hình vận hành.

## 2. Ba khái niệm nền tảng

### 2.1. Environment

`org.springframework.core.env.Environment` là giao diện dùng để truy cập thuộc tính và thông tin profile.

Ví dụ:

```java
import org.springframework.core.env.Environment;

String message = environment.getProperty("demo.message");
String active = String.join(",", environment.getActiveProfiles());
```

`Environment#getProperty("demo.message")` không buộc phải đọc trực tiếp từ tệp YAML. Nó trả về giá trị được giải quyết từ hệ thống các nguồn thuộc tính hiện tại.

### 2.2. PropertySource

`org.springframework.core.env.PropertySource<T>` đại diện cho một nguồn thuộc tính có **tên nhận diện** và đối tượng chứa dữ liệu.

Một triển khai phổ biến là:

```java
org.springframework.core.env.MapPropertySource
```

Nó cho phép một `Map<String,Object>` đóng vai trò là nguồn cấu hình:

```java
Map<String, Object> values = new HashMap<>();
values.put("demo.message", "Hello from custom source");
values.put("demo.retries", 5);

MapPropertySource source =
        new MapPropertySource("tenantOverrides", values);
```

Tên `tenantOverrides` là **tên của nguồn**, không phải tên của khóa cấu hình. Tên nguồn giúp bạn xác định nơi nguồn ấy được đặt trong danh sách thứ tự ưu tiên.

### 2.3. MutablePropertySources

`org.springframework.core.env.MutablePropertySources` là một tập hợp **có thứ tự và có thể thay đổi** các `PropertySource<?>`.

Nó có các thao tác thêm, xóa, thay thế, kiểm tra sự tồn tại và di chuyển nguồn bằng cách thêm lại nguồn có tên đã tồn tại.

Để truy cập tập nguồn có thể chỉnh sửa trong ứng dụng, thường dùng:

```java
ConfigurableEnvironment configurableEnvironment = ...;

MutablePropertySources propertySources =
        configurableEnvironment.getPropertySources();
```

`Environment` thông thường chỉ cung cấp khả năng đọc. Giao diện `ConfigurableEnvironment` mở rộng nó với những thao tác cấu hình hệ thống nguồn.

## 3. Quy tắc quan trọng nhất: Nguồn đứng trước có ưu tiên cao hơn

Hãy hình dung một danh sách nguồn:

```text
Vị trí 1 — commandLineArgs             (ưu tiên cao)
Vị trí 2 — systemProperties
Vị trí 3 — systemEnvironment
Vị trí 4 — customDefaults
Vị trí 5 — application.yml             (ưu tiên thấp hơn)
```

Đây là **sơ đồ minh họa**, không phải cam kết vị trí đầy đủ hoặc tên nội bộ của tất cả PropertySource trong mọi phiên bản Spring Boot.

Khi ứng dụng hỏi:

```java
environment.getProperty("demo.message");
```

hệ thống tìm kiếm các nguồn theo độ ưu tiên. Trong cách giải quyết thuộc tính thông thường, **nguồn có ưu tiên cao nhất chứa một giá trị không null cho khóa đó** sẽ cung cấp kết quả.

Ví dụ:

| Nguồn | `demo.message` |
| --- | --- |
| Nguồn A, ưu tiên cao | `"A"` |
| Nguồn B, ưu tiên thấp | `"B"` |
| Nguồn C, ưu tiên thấp hơn | `"C"` |

Kết quả là `"A"`.

Nếu A không có khóa `demo.message`, Spring tiếp tục tìm ở B. Một PropertySource không phải khai báo mọi khóa; nó chỉ đóng góp những khóa thực sự có mặt trong nó.

**Không nhầm “thêm một nguồn” với “ghi lại giá trị trong application.yml”.** Khi thêm một `MapPropertySource`, bạn đang thay đổi tập nguồn trong bộ nhớ của `Environment`, không sửa tệp YAML trên đĩa.

## 4. Cách lấy MutablePropertySources

Trong một đối tượng Spring `ApplicationContext` có hỗ trợ cấu hình môi trường:

```java
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MutablePropertySources;

ConfigurableEnvironment environment =
        context.getEnvironment();

MutablePropertySources sources =
        environment.getPropertySources();
```

Ở đây `context` là `ConfigurableApplicationContext`.

Nếu bạn chỉ được cấp giao diện `Environment`, không nên giả định mọi implementation đều hỗ trợ chỉnh sửa:

```java
if (environment instanceof ConfigurableEnvironment configurable) {
    MutablePropertySources sources = configurable.getPropertySources();
    // Thao tác với sources khi thực sự cần.
}
```

Trong ứng dụng Spring Boot tiêu chuẩn, môi trường ứng dụng thường là một implementation của `ConfigurableEnvironment`. Nhưng một API dùng chung nhận `Environment` nên tôn trọng sự khác biệt giao diện đọc và giao diện cấu hình.

Các phương thức sẽ dùng trong bài đều nằm trên `MutablePropertySources`, không phải được gọi trực tiếp trên `Environment`.

## 5. addFirst: đặt nguồn vào đầu danh sách

### 5.1. Cú pháp

```java
propertySources.addFirst(propertySource);
```

Ý nghĩa: chèn nguồn được chỉ định vào **đầu danh sách**. Đối với thứ tự ưu tiên `PropertySources`, đầu danh sách thường là vị trí ưu tiên cao nhất.

Ví dụ:

```java
import java.util.Map;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.MutablePropertySources;

MapPropertySource override = new MapPropertySource(
        "emergencyOverrides",
        Map.of("demo.message", "Ưu tiên từ nguồn mới")
);

MutablePropertySources sources = environment.getPropertySources();
sources.addFirst(override);
```

Trong tình huống nguồn mới thực sự đứng đầu quá trình tra cứu, `demo.message` từ `emergencyOverrides` có thể ghi đè giá trị cùng tên do các nguồn thấp hơn cung cấp.

### 5.2. Sơ đồ

Trước:

```text
1. sourceA    demo.message=A
2. sourceB    demo.message=B
```

Thực hiện:

```java
sources.addFirst(
    new MapPropertySource(
        "prioritySource",
        Map.of("demo.message", "P")
    )
);
```

Sau:

```text
1. prioritySource    demo.message=P
2. sourceA           demo.message=A
3. sourceB           demo.message=B
```

Kết quả tìm `demo.message` là `P`.

### 5.3. Khi nào dùng?

`addFirst` phù hợp khi **nguồn mới được phép thắng các nguồn có sẵn** cho những khóa mà nó khai báo, ví dụ một lớp cấu hình override do hệ thống quản lý với quy tắc ưu tiên được thiết kế rõ ràng.

Tuy nhiên, đây cũng là thao tác có rủi ro cao nhất nếu dùng tùy tiện.

Nếu đặt một MapPropertySource ở đầu và nó chứa:

```properties
server.port=9090
spring.profiles.active=prod
logging.level.root=DEBUG
```

bạn có thể thay đổi cách các thành phần nhìn thấy giá trị tương ứng, nhưng **không thể suy ra mọi quyết định khởi động đã hoàn tất sẽ được tính lại**. Đặc biệt, các lựa chọn về Config Data, profile hoặc logging có thể đã được xử lý trước thời điểm bạn thêm nguồn.

Chỉ dùng `addFirst` với những khóa và thời điểm mà bạn hiểu rõ vòng đời xử lý của chúng.

## 6. addLast: đặt nguồn ở cuối làm lớp dự phòng

### 6.1. Cú pháp

```java
propertySources.addLast(propertySource);
```

Ý nghĩa: thêm nguồn ở **cuối danh sách**, cho nó mức ưu tiên thấp hơn những nguồn đang có.

Ví dụ:

```java
import java.util.Map;
import org.springframework.core.env.MapPropertySource;

propertySources.addLast(new MapPropertySource(
        "companyDefaults",
        Map.of(
                "demo.message", "Giá trị dự phòng",
                "demo.retries", 2
        )
));
```

Nếu nguồn có ưu tiên cao hơn đã khai báo `demo.message`, giá trị đó được dùng. Nếu không nguồn nào phía trên cung cấp khóa ấy, `companyDefaults` có thể đóng góp giá trị dự phòng.

### 6.2. Sơ đồ

Trước:

```text
1. sourceA     demo.message=A
2. sourceB     demo.message=B
```

Sau khi:

```java
sources.addLast(
    new MapPropertySource(
        "fallback",
        Map.of("demo.message", "F")
    )
);
```

Danh sách:

```text
1. sourceA     demo.message=A
2. sourceB     demo.message=B
3. fallback    demo.message=F
```

Kết quả vẫn là `A`, không phải `F`.

Nếu cả sourceA lẫn sourceB không có `demo.message`, kết quả mới có thể là `F`.

### 6.3. Khi nào dùng?

`addLast` hữu ích cho:

- bộ mặc định của một thư viện;
- các giá trị dự phòng khi người triển khai chưa đặt cấu hình;
- một tập giá trị thử nghiệm có mức ưu tiên thấp;
- hệ thống dùng “cấu hình từ ứng dụng thắng mặc định từ thư viện”.

Với default cấu hình, cũng có thể dùng `@DefaultValue` hoặc giá trị mặc định trong tệp config. Lựa chọn nguồn dự phòng riêng phù hợp khi có nhiều giá trị được cung cấp bởi một mô-đun và cần quản lý chúng như một lớp nguồn rõ ràng.

## 7. addBefore: chèn trước một nguồn được chỉ định

### 7.1. Cú pháp

```java
propertySources.addBefore(
        "sourceName",
        newPropertySource
);
```

Tham số thứ nhất là **tên nguồn đã tồn tại**. Nguồn mới sẽ được đặt **ngay trước nguồn đó**.

Vì nguồn đứng trước có độ ưu tiên cao hơn, `addBefore("sourceName", ...)` thường khiến nguồn mới thắng nguồn đích khi cùng khai báo một khóa, nhưng **không nhất thiết thắng mọi nguồn khác phía trước**.

### 7.2. Ví dụ

Danh sách ban đầu:

```text
1. commandLine
2. deploymentOverrides
3. libraryDefaults
```

Chạy:

```java
sources.addBefore(
        "libraryDefaults",
        new MapPropertySource(
                "teamDefaults",
                Map.of("demo.message", "Team")
        )
);
```

Kết quả:

```text
1. commandLine
2. deploymentOverrides
3. teamDefaults
4. libraryDefaults
```

`teamDefaults` thắng `libraryDefaults` với các khóa trùng nhau, nhưng vẫn đứng sau `commandLine` và `deploymentOverrides`.

### 7.3. Trường hợp cần ưu tiên có kiểm soát

Giả sử một thư viện phát hành nguồn `libraryDefaults` để cung cấp các giá trị mặc định. Ứng dụng muốn thêm mặc định nội bộ **mạnh hơn** của thư viện nhưng vẫn **yếu hơn** giá trị do người dùng vận hành cung cấp.

`addBefore("libraryDefaults", companyDefaults)` có thể mô tả đúng chính sách ấy mà không phải dùng `addFirst` để ghi đè toàn bộ các nguồn còn lại.

Cách này đặc biệt hữu ích khi bạn kiểm soát tên nguồn đích và bảo đảm nó thực sự tồn tại.

## 8. addAfter: chèn sau một nguồn được chỉ định

### 8.1. Cú pháp

```java
propertySources.addAfter(
        "sourceName",
        newPropertySource
);
```

Nguồn mới được chèn **ngay sau** nguồn mang tên `sourceName`, nên nó có mức ưu tiên thấp hơn nguồn đích nhưng cao hơn những nguồn nằm sau.

### 8.2. Ví dụ

Ban đầu:

```text
1. commandLine
2. deploymentOverrides
3. libraryDefaults
```

Thực hiện:

```java
sources.addAfter(
        "deploymentOverrides",
        new MapPropertySource(
                "tenantFallback",
                Map.of("demo.message", "Tenant")
        )
);
```

Kết quả:

```text
1. commandLine
2. deploymentOverrides
3. tenantFallback
4. libraryDefaults
```

`tenantFallback` không thắng `deploymentOverrides` với khóa trùng, nhưng nó có thể thắng `libraryDefaults`.

### 8.3. Khi nào dùng?

`addAfter` thích hợp khi:

- một nguồn gốc có quyền ưu tiên cao hơn giá trị tùy chỉnh;
- bạn muốn thêm cấu hình bổ sung ngay sau một nguồn do mình quản lý;
- cần bảo đảm một nguồn mới có vị trí tương đối cụ thể mà không đặt nó ở đầu hoặc cuối.

Ví dụ hệ thống muốn ưu tiên **cấu hình do người vận hành** hơn cấu hình tenant, nhưng vẫn cho cấu hình tenant thắng các giá trị mặc định của thư viện.

## 9. So sánh nhanh bốn phương thức

Giả sử danh sách nguồn ban đầu:

```text
[ A, B, C ]
```

Các thao tác với nguồn mới `X`:

| Thao tác | Kết quả |
| --- | --- |
| `addFirst(X)` | `[X, A, B, C]` |
| `addLast(X)` | `[A, B, C, X]` |
| `addBefore("B", X)` | `[A, X, B, C]` |
| `addAfter("B", X)` | `[A, B, X, C]` |

Nhìn từ góc độ ưu tiên:

```text
Đầu danh sách                            Cuối danh sách
ưu tiên cao                               ưu tiên thấp
      |                                           |
      v                                           v
      A  ->  B  ->  C  ->  D  ->  E
```

Nếu hai nguồn cùng chứa `demo.message`, nguồn gần đầu danh sách hơn thường thắng khi giải quyết khóa đó.

**Điều quan trọng:** bốn phương thức này không thay đổi **giá trị dữ liệu** của một `PropertySource` đã tồn tại, mà thay đổi **vị trí/quan hệ ưu tiên** của nguồn. Nếu nguồn mới là một Map có các khóa khác hoàn toàn, việc di chuyển nguồn có thể không làm thay đổi các giá trị đang được hỏi.

## 10. Ví dụ Java độc lập: quan sát thứ tự và kết quả

Để học chính xác cách bốn thao tác hoạt động, có thể dùng một ví dụ Java **không cần khởi động Spring Boot**.

```java
import java.util.Map;

import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.MutablePropertySources;
import org.springframework.core.env.PropertySourcesPropertyResolver;

public class PropertySourcesOrderingDemo {

    public static void main(String[] args) {
        MutablePropertySources sources =
                new MutablePropertySources();

        sources.addLast(new MapPropertySource(
                "base",
                Map.of("demo.message", "BASE")
        ));

        sources.addFirst(new MapPropertySource(
                "operator",
                Map.of("demo.message", "OPERATOR")
        ));

        sources.addAfter("operator", new MapPropertySource(
                "tenant",
                Map.of("demo.message", "TENANT")
        ));

        sources.addBefore("base", new MapPropertySource(
                "team",
                Map.of("demo.message", "TEAM")
        ));

        sources.addLast(new MapPropertySource(
                "finalFallback",
                Map.of("demo.message", "FALLBACK")
        ));

        for (var source : sources) {
            System.out.println(source.getName());
        }

        var resolver = new PropertySourcesPropertyResolver(sources);

        System.out.println("demo.message = "
                + resolver.getProperty("demo.message"));
    }
}
```

Kết quả thứ tự tên nguồn:

```text
operator
tenant
team
base
finalFallback
demo.message = OPERATOR
```

**Vì sao?**

1. `base` được thêm vào cuối một tập trống.
2. `operator` được thêm vào đầu, nên đứng trước `base`.
3. `tenant` được đặt sau `operator`, trước `base`.
4. `team` được đặt trước `base`, tức sau `tenant`.
5. `finalFallback` được thêm sau cùng.

`PropertySourcesPropertyResolver` cho phép giải quyết thuộc tính từ một `MutablePropertySources` độc lập. Đây là cách quan sát quy tắc thứ tự mà không bị các nguồn mặc định của một ứng dụng Boot thực tế làm nhiễu.

## 11. Nguồn mới không có khóa thì Spring tìm tiếp

Xét:

```java
MutablePropertySources sources = new MutablePropertySources();

sources.addFirst(new MapPropertySource(
        "highPriority",
        Map.of("demo.message", "HIGH")
));

sources.addLast(new MapPropertySource(
        "lowPriority",
        Map.of(
                "demo.message", "LOW",
                "demo.retries", 7
        )
));
```

Khi hỏi:

```java
var resolver = new PropertySourcesPropertyResolver(sources);

resolver.getProperty("demo.message"); // "HIGH"
resolver.getProperty("demo.retries"); // "7" dạng chuỗi khi đọc String
```

Nguồn `highPriority` chỉ có `demo.message`, nên Spring tiếp tục tra cứu `demo.retries` ở nguồn thấp hơn.

Không phải cứ có một PropertySource ở đầu thì mọi thuộc tính đều bị chặn bởi nguồn ấy.

### 11.1. Giá trị null và chuỗi rỗng

Trong cách giải quyết PropertySource thông thường, một nguồn trả về `null` cho khóa được hiểu là không có giá trị phù hợp, nên quá trình tìm kiếm có thể tiếp tục.

Nhưng **chuỗi rỗng** `""` là một giá trị đã được cung cấp. Ví dụ:

```java
sources.addFirst(new MapPropertySource(
        "override",
        Map.of("demo.message", "")
));
```

Giá trị rỗng có thể thắng một chuỗi không rỗng từ nguồn thấp hơn.

Đây là nguyên nhân thường gặp của lỗi “tôi đã đặt mặc định ở dưới nhưng ứng dụng vẫn nhận chuỗi rỗng”. Hãy phân biệt **không có khóa** với **khóa có giá trị rỗng**.

## 12. addBefore/addAfter cần tên nguồn đã tồn tại

Hai phương thức dùng vị trí tương đối phải tìm được nguồn làm mốc.

Ví dụ:

```java
sources.addBefore(
        "sourceThatDoesNotExist",
        new MapPropertySource(
                "mySource",
                Map.of("demo.message", "Hello")
        )
);
```

Nếu tên nguồn làm mốc không tồn tại, thao tác không thể xác định vị trí chèn và có thể ném `IllegalArgumentException`.

Trong mã thực tế, nên kiểm tra trước khi dùng:

```java
String anchor = "companyDefaults";

MapPropertySource custom = new MapPropertySource(
        "tenantSettings",
        Map.of("demo.message", "tenant")
);

if (sources.contains(anchor)) {
    sources.addBefore(anchor, custom);
} else {
    sources.addLast(custom);
}
```

Đây chỉ là **một chính sách dự phòng minh họa**. Nếu hệ thống yêu cầu bắt buộc nguồn `companyDefaults` phải có mặt, việc tự chuyển sang `addLast` có thể che giấu lỗi cấu hình. Khi đó nên từ chối với thông báo rõ ràng:

```java
if (!sources.contains(anchor)) {
    throw new IllegalStateException(
            "Thiếu nguồn làm mốc: " + anchor);
}
sources.addBefore(anchor, custom);
```

Hãy chọn cách xử lý theo hợp đồng của hệ thống, không mặc định im lặng dùng một vị trí bất kỳ khi tên mốc sai.

## 13. Tên PropertySource là định danh quản lý nguồn

Mỗi PropertySource có một tên để `MutablePropertySources` nhận diện khi tìm, thay thế và chèn nguồn tương đối.

Ví dụ:

```java
new MapPropertySource(
        "customTenantSource",
        Map.of("demo.message", "Tenant")
);
```

Trong ví dụ, `customTenantSource` là **tên nguồn**, còn `demo.message` là **tên khóa**.

Hai nguồn với các tên khác nhau có thể chứa cùng một khóa:

```text
customTenantSource: demo.message=Tenant
companyDefaults:   demo.message=Company
```

Đó là bình thường; thứ tự ưu tiên quyết định giá trị có hiệu lực.

Tuy nhiên, nên **chọn tên nguồn riêng biệt và ổn định**. Nếu cố thêm nguồn mới trùng tên nguồn đã có, `MutablePropertySources` có hành vi quản lý theo tên chứ không duy trì hai phần tử cùng tên độc lập như một danh sách thông thường.

Khi dùng `addFirst` hoặc `addLast` với một PropertySource có tên đã tồn tại, implementation có thể loại bỏ vị trí cũ và đưa nguồn vào vị trí mới. Điều này làm thay đổi thứ tự một nguồn đã có thay vì tạo hai bản sao.

Để tránh khó theo dõi, nên dùng các tên có namespace riêng, chẳng hạn:

```text
acmeTenantOverrides
acmeRemoteDefaults
acmeFeatureFlags
```

và ghi rõ trong thiết kế rằng những nguồn này được quản lý bởi thành phần nào.

## 14. Quan sát tên và thứ tự của PropertySources

Để biết nguồn nào đang tồn tại, có thể liệt kê **tên nguồn**:

```java
import org.springframework.core.env.ConfigurableEnvironment;

public static void printPropertySourceNames(
        ConfigurableEnvironment environment) {

    int index = 0;

    for (var source : environment.getPropertySources()) {
        System.out.printf("%d. %s%n",
                ++index, source.getName());
    }
}
```

Một môi trường có thể chứa nguồn về:

- đối số dòng lệnh;
- system properties;
- system environment;
- Config Data;
- property sources tạm thời từ test;
- nguồn tùy chỉnh;
- nguồn tổng hợp hoặc nguồn nội bộ của Spring Boot.

**Không viết mã phụ thuộc vào một danh sách tên nội bộ cố định** nếu các tên ấy không phải hợp đồng công khai của thành phần bạn kiểm soát. Tên của nguồn Config Data có thể chứa thông tin đường dẫn hoặc thay đổi theo phiên bản/cách nạp.

### 14.1. Tránh in toàn bộ giá trị

Có thể in tên nguồn để chẩn đoán, nhưng không nên duyệt mọi khóa rồi in mọi giá trị trong production: PropertySource có thể chứa token, mật khẩu, API key hoặc thông tin cấu hình nhạy cảm.

Để kiểm tra một khóa không nhạy cảm:

```java
System.out.println(
        "demo.message = "
        + environment.getProperty("demo.message")
);
```

Với secret, chỉ kiểm tra sự hiện diện hoặc dùng công cụ quan sát có che giá trị nhạy cảm.

## 15. Đưa một nguồn cấu hình tùy chỉnh vào Spring Boot

Từ ví dụ độc lập, bây giờ tích hợp vào ứng dụng thực tế.

Giả sử muốn cấp giá trị:

```text
demo.message = "Xin chào từ tenant"
demo.retries = 5
```

vào `Environment` trước khi Spring tạo các bean nghiệp vụ.

Một cách dễ hiểu là dùng `ApplicationContextInitializer`.

### 15.1. Tạo initializer

```java
package com.example.configdemo;

import java.util.Map;

import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.MutablePropertySources;

public final class TenantPropertySourceInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        MutablePropertySources sources =
                context.getEnvironment().getPropertySources();

        MapPropertySource tenantSource = new MapPropertySource(
                "acmeTenantOverrides",
                Map.of(
                        "demo.message", "Xin chào từ tenant",
                        "demo.retries", 5
                )
        );

        sources.addFirst(tenantSource);
    }
}
```

Ở đây:

- `MapPropertySource` tạo một nguồn từ Map.
- `acmeTenantOverrides` là tên riêng của nguồn.
- `addFirst` yêu cầu đưa nguồn lên đầu danh sách tại thời điểm initializer chạy.
- Các property có thể được Spring đọc qua `Environment` và binder sau đó.

### 15.2. Đăng ký initializer khi khởi động

```java
package com.example.configdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ConfigDemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ConfigDemoApplication.class);

        application.addInitializers(
                new TenantPropertySourceInitializer()
        );

        application.run(args);
    }
}
```

Initializer được gọi trong giai đoạn chuẩn bị ApplicationContext, trước lần refresh tạo các singleton bean thông thường. Với các khóa cấu hình mà bean đọc trong quá trình tạo sau đó, đây là một thời điểm hữu ích để thêm PropertySource.

**Giới hạn quan trọng:** initializer **không phải điểm mở rộng sớm nhất** của Spring Boot. Config Data, lựa chọn profile, một phần thiết lập logging và các quyết định chuẩn bị Environment có thể đã được xử lý trước khi initializer chạy. Thêm `spring.config.import` hoặc `spring.profiles.active` tại đây không đồng nghĩa toàn bộ quá trình nạp cấu hình sẽ được tính lại.

Nếu mục đích chỉ là cung cấp giá trị nghiệp vụ như `demo.message` hoặc `demo.retries` cho bean tạo sau initializer, ví dụ trên rõ ràng và phù hợp.

## 16. Đọc nguồn mới bằng @ConfigurationProperties

Tiếp tục ví dụ, tạo record:

```java
package com.example.configdemo;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public record DemoProperties(
        String message,
        int retries) {
}
```

Đăng ký bằng:

```java
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ConfigDemoApplication {
    // Đoạn main đăng ký initializer như phần trước.
}
```

Tệp `application.yml`:

```yaml
demo:
  message: "Giá trị từ YAML"
  retries: 3
```

Vì initializer thêm:

```text
demo.message = Xin chào từ tenant
demo.retries = 5
```

vào nguồn ưu tiên cao trong ví dụ, bean `DemoProperties` được bind sau đó có thể nhận hai giá trị từ nguồn tùy chỉnh.

Dùng một runner để quan sát:

```java
package com.example.configdemo;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class DemoPrinter implements ApplicationRunner {

    private final DemoProperties properties;

    public DemoPrinter(DemoProperties properties) {
        this.properties = properties;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("message=" + properties.message());
        System.out.println("retries=" + properties.retries());
    }
}
```

Kết quả dự kiến:

```text
message=Xin chào từ tenant
retries=5
```

Lưu ý: kết quả này xét ở ví dụ các nguồn không có cơ chế đặc biệt khác can thiệp. Thực tế, nên kiểm tra danh sách PropertySource và kết quả `Environment#getProperty(...)` sau initializer nếu ứng dụng có nhiều extension riêng.

## 17. Có nên để nguồn tùy chỉnh thắng đối số dòng lệnh?

Giả sử ứng dụng được chạy với:

```bash
java -jar app.jar --demo.message="Giá trị từ CLI"
```

Và initializer của bạn gọi:

```java
sources.addFirst(tenantSource);
```

Khi nguồn `tenantSource` ở đầu danh sách tại thời điểm đọc, nó có thể **thắng cả giá trị được đưa từ đối số dòng lệnh** đối với khóa `demo.message`.

Điều này khác với quy tắc thứ tự ưu tiên mặc định của Spring Boot, trong đó đối số ứng dụng thường có mức ưu tiên cao hơn các nguồn Config Data thông thường.

**Một quyết định thiết kế quan trọng:** bạn có thực sự muốn mã ứng dụng tự thêm nguồn dữ liệu ở vị trí có quyền ghi đè cấu hình do người vận hành cung cấp không?

Nếu câu trả lời là không, tránh gọi `addFirst` chỉ vì nó dễ sử dụng. Có thể:

- đặt nguồn tùy chỉnh ở cuối bằng `addLast` nếu đó là default;
- dùng `addAfter` đối với một nguồn do bạn quản lý và có mốc chắc chắn;
- thiết kế nguồn Config Data theo cơ chế được Spring Boot hỗ trợ nếu cần hòa vào chính sách ưu tiên của hệ thống;
- quy định rõ trong tài liệu triển khai nguồn nào được phép thắng nguồn nào.

Việc chọn đúng **vị trí** quan trọng không kém việc chọn đúng **giá trị**.

## 18. So sánh addFirst với addLast trong cùng ứng dụng

Tệp `application.yml`:

```yaml
demo:
  message: "YAML"
  retries: 3
```

Nguồn tùy chỉnh:

```java
MapPropertySource source = new MapPropertySource(
        "companySettings",
        Map.of(
                "demo.message", "COMPANY",
                "demo.retries", 6
        )
);
```

Nếu dùng:

```java
sources.addFirst(source);
```

thì nguồn mới được đặt ở đầu và có thể cho:

```text
demo.message = COMPANY
demo.retries = 6
```

Nếu dùng:

```java
sources.addLast(source);
```

thì cấu hình từ YAML có thể vẫn thắng:

```text
demo.message = YAML
demo.retries = 3
```

Nguồn ở cuối vẫn có tác dụng với một khóa mà các nguồn phía trên **không khai báo**.

Ví dụ nếu chỉ `companySettings` có `demo.region=vn` thì ứng dụng vẫn có thể đọc `demo.region=vn`, mặc dù `companySettings` đứng cuối.

Đây là lý do `addLast` thường hợp với nguồn **mặc định bổ sung**, trong khi `addFirst` là nguồn **ghi đè có chủ ý**.

## 19. Chèn tương đối với một nguồn do ứng dụng tự tạo

Khi dùng `addBefore` và `addAfter`, tốt nhất nên có một **nguồn mốc do bạn kiểm soát** thay vì phụ thuộc tên nội bộ của Config Data.

Ví dụ:

```java
import java.util.Map;

import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.MutablePropertySources;

public final class PropertySourceLayers {

    public static void install(MutablePropertySources sources) {
        sources.addLast(new MapPropertySource(
                "acmeLibraryDefaults",
                Map.of(
                        "demo.message", "Library",
                        "demo.retries", 1
                )
        ));

        sources.addBefore(
                "acmeLibraryDefaults",
                new MapPropertySource(
                        "acmeTenantDefaults",
                        Map.of("demo.message", "Tenant")
                )
        );

        sources.addAfter(
                "acmeTenantDefaults",
                new MapPropertySource(
                        "acmeRegionalDefaults",
                        Map.of("demo.region", "vn")
                )
        );
    }
}
```

Giữa ba nguồn do ta quản lý, thứ tự là:

```text
acmeTenantDefaults
acmeRegionalDefaults
acmeLibraryDefaults
```

Nhưng vì cả ba nguồn được xây trên danh sách hiện có qua `addLast` rồi chèn tương đối, chúng có thể vẫn đứng **sau các nguồn đã có của ứng dụng**.

Điều này cho phép người vận hành dùng `application.yml` hoặc nguồn khác đã được đặt ở phía trên để ghi đè default của thư viện, đồng thời các lớp default của thư viện vẫn có một thứ tự nội bộ rõ ràng.

## 20. Không dựa mù vào tên nội bộ của PropertySource trong Boot

Trong ứng dụng thật, bạn có thể thấy các tên nguồn mô tả Config Data như đường dẫn tới tệp `application.yml`, vị trí import hoặc tên do Boot tạo.

Một đoạn mã như:

```java
sources.addBefore(
        "Config resource 'class path resource [application.yml]' ...",
        customSource
);
```

rất dễ bị hỏng nếu:

- cấu hình được chuyển từ YAML sang Properties;
- ứng dụng dùng thêm profile;
- đường dẫn thay đổi;
- phiên bản Spring Boot thay đổi cách đặt tên nguồn;
- tệp được nạp từ vị trí ngoài JAR;
- cấu hình được import thay vì là tệp chuẩn.

Không nên sao chép một tên PropertySource nhìn thấy trong log ở một máy rồi coi đó là API ổn định cho mọi môi trường.

Thay vào đó, có thể:

1. Đặt tên duy nhất cho các nguồn do mình tạo.
2. Dùng `addBefore`/`addAfter` với tên nguồn do mình kiểm soát.
3. Đặt fallback rõ nếu mốc tùy chọn không có.
4. Với yêu cầu ưu tiên theo kiểu Config Data, cân nhắc cơ chế Config Data thay vì tự chèn vào một tên nội bộ.

## 21. Mở rộng Environment nên thực hiện lúc nào?

**Thời điểm thay đổi nguồn** quyết định thành phần nào có thể quan sát được giá trị mới.

Có một số giai đoạn thường gặp:

```text
SpringApplication.run()
       |
       v
Chuẩn bị Environment
       |
       +-- Nạp Config Data / xử lý profile liên quan
       |
       v
Chuẩn bị ApplicationContext
       |
       +-- ApplicationContextInitializer
       |
       v
Refresh ApplicationContext
       |
       +-- tạo bean
       +-- resolve @Value
       +-- bind @ConfigurationProperties
       |
       v
ApplicationRunner / CommandLineRunner
       |
       v
Ứng dụng phục vụ yêu cầu
```

Đây là **sơ đồ đơn giản hóa**. Từng subsystem của Boot có thể xử lý cấu hình vào thời điểm khác nhau; không nên suy ra toàn bộ quyết định của quá trình khởi động diễn ra trong một bước duy nhất.

### 21.1. Initializer

Hữu ích khi cần bổ sung PropertySource **trước khi Spring tạo bean ứng dụng thông thường**. Đây là lựa chọn dễ tiếp cận cho ví dụ học tập.

### 21.2. EnvironmentPostProcessor

Phù hợp khi cần can thiệp vào giai đoạn chuẩn bị Environment sớm hơn và tích hợp với quá trình khởi động của Spring Boot.

Tuy nhiên, thứ tự các processor có ý nghĩa. Một EnvironmentPostProcessor chạy quá sớm có thể không nhìn thấy Config Data; một processor chạy sau cũng không khiến mọi quyết định đã hoàn tất được thực hiện lại.

### 21.3. @PostConstruct hoặc ApplicationRunner

Nếu thêm PropertySource tại những thời điểm này, nhiều bean có thể đã được tạo và bind với giá trị cũ. Việc đọc `Environment` trực tiếp sau đó có thể thấy giá trị mới, nhưng các field `@Value` đã tiêm hoặc các bean `@ConfigurationProperties` đã tạo **không tự nhận lại giá trị**.

Vì vậy, không nên sử dụng các thời điểm quá muộn chỉ để mong toàn bộ ứng dụng “tự động cập nhật cấu hình”.

## 22. EnvironmentPostProcessor cho trường hợp tích hợp sớm

Spring Boot cung cấp SPI:

```java
org.springframework.boot.env.EnvironmentPostProcessor
```

Nó cho phép thay đổi `ConfigurableEnvironment` trong quá trình chuẩn bị môi trường ứng dụng.

Ví dụ:

```java
package com.example.configdemo;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.Ordered;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;

public class CompanyDefaultsEnvironmentPostProcessor
        implements EnvironmentPostProcessor, Ordered {

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application) {

        environment.getPropertySources().addLast(
                new MapPropertySource(
                        "acmeCompanyDefaults",
                        Map.of(
                                "demo.retries", 2,
                                "demo.region", "vn"
                        )
                )
        );
    }

    @Override
    public int getOrder() {
        return Ordered.LOWEST_PRECEDENCE;
    }
}
```

Ví dụ dùng `addLast` vì chỉ muốn cung cấp giá trị dự phòng. `Ordered.LOWEST_PRECEDENCE` thể hiện ý định chạy muộn trong nhóm các processor dùng cơ chế sắp xếp theo thứ tự, **không phải lời bảo đảm cho mọi subsystem khởi động hoặc mọi extension khác**.

### 22.1. Đăng ký processor

Trong Spring Boot 3.x, một cách đăng ký phổ biến là đặt:

```text
src/main/resources/META-INF/spring.factories
```

với nội dung:

```properties
org.springframework.boot.env.EnvironmentPostProcessor=\
com.example.configdemo.CompanyDefaultsEnvironmentPostProcessor
```

Khi khởi động qua cơ chế Boot hỗ trợ, Spring Boot có thể phát hiện implementation được khai báo tại đây.

**Không nhầm** cơ chế khai báo `EnvironmentPostProcessor` qua `spring.factories` với danh sách `AutoConfiguration.imports` dành cho auto-configuration. Hai loại extension có nhiệm vụ khác nhau.

Tùy phiên bản Spring Boot hoặc framework build của ứng dụng, hãy theo hướng dẫn SPI tương ứng. Nếu cần một processor chạy trước/sau quá trình xử lý Config Data, cần xét thứ tự cụ thể của các processor thay vì chỉ chọn một số tùy tiện.

## 23. Khi nào EnvironmentPostProcessor vẫn chưa phải giải pháp đúng?

Giả sử bạn muốn một file từ xa quyết định:

```properties
spring.profiles.active=prod
spring.config.import=...
```

Việc tự thêm một nguồn qua `addFirst` ở thời điểm tùy ý không bảo đảm Spring Boot sẽ tính lại việc chọn profile hoặc thứ tự nạp Config Data đã diễn ra.

Một phần cấu hình được Boot dùng **rất sớm** để quyết định cách chuẩn bị môi trường. Khi yêu cầu của bạn là tích hợp **một loại Config Data mới** với cơ chế nạp tệp, profile và import, hãy cân nhắc các điểm mở rộng chính thức như:

- `ConfigDataLocationResolver`;
- `ConfigDataLoader`;
- cơ chế `spring.config.import` và vị trí cấu hình được Boot hỗ trợ.

Một `MapPropertySource` được thêm bằng initializer có thể phù hợp cho **giá trị nghiệp vụ** nhưng không thay thế hoàn toàn cơ chế nạp Config Data.

**Nguyên tắc:** nếu nguồn mới chỉ cung cấp `demo.*` cho bean, thao tác PropertySources có thể đủ; nếu nguồn mới định nghĩa quá trình khởi động/phân giải config, hãy đánh giá điểm mở rộng sớm và chuyên biệt hơn.

## 24. Thêm PropertySource bằng @PropertySource khác gì?

Trong Spring Framework, có annotation:

```java
@PropertySource("classpath:company.properties")
```

để khai báo một nguồn Properties cho context.

Ví dụ:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.PropertySource;

@Configuration
@PropertySource("classpath:company.properties")
public class CompanyPropertyConfiguration {
}
```

Cơ chế này khác với việc tự gọi:

```java
sources.addFirst(...);
sources.addLast(...);
sources.addBefore(...);
sources.addAfter(...);
```

Với `@PropertySource`, Spring xử lý annotation trong quá trình xây dựng ApplicationContext; bạn không trực tiếp chỉ định vị trí bằng bốn thao tác trên.

Đặc biệt, tài liệu Spring Boot lưu ý rằng `@PropertySource` được thêm trong giai đoạn refresh context, **có thể quá muộn** để ảnh hưởng một số thuộc tính được đọc rất sớm, chẳng hạn những cấu hình khởi động và logging.

Nếu cần thứ tự ưu tiên chính xác hoặc thời điểm thêm nguồn cụ thể, thao tác với `ConfigurableEnvironment` ở một điểm vòng đời phù hợp cho phép kiểm soát rõ ràng hơn.

Nhưng “có kiểm soát hơn” không có nghĩa “nên làm mọi thứ bằng addFirst”. Với cấu hình tệp thông thường, cơ chế Config Data mặc định của Boot thường là lựa chọn ít phức tạp hơn.

## 25. Nguồn tùy chỉnh có thể đọc được bằng Environment

Giả sử initializer thêm:

```java
MapPropertySource source = new MapPropertySource(
        "myRuntimeSettings",
        Map.of(
                "demo.message", "Hello",
                "demo.retries", 4
        )
);

environment.getPropertySources().addFirst(source);
```

Sau đó:

```java
String message = environment.getProperty("demo.message");
Integer retries = environment.getProperty(
        "demo.retries",
        Integer.class
);
```

Giá trị kỳ vọng trong bối cảnh đơn giản:

```text
message = Hello
retries = 4
```

Spring `Environment` có cơ chế chuyển kiểu cho những trường hợp thông dụng. Tuy nhiên, không nên giả định mọi converter tùy chỉnh dành riêng cho `@ConfigurationProperties` tự động được sử dụng hệt như vậy cho `Environment#getProperty(..., TargetType.class)`.

### 25.1. Tương tác với @Value

Một bean được tạo sau initializer có thể dùng:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class GreetingService {

    private final String message;

    public GreetingService(
            @Value("${demo.message:Default}") String message) {
        this.message = message;
    }

    public String greeting() {
        return message;
    }
}
```

Khi Spring tạo bean và giải quyết placeholder, nguồn tùy chỉnh đã có thể đóng góp giá trị cho `demo.message`.

Nếu bạn thêm PropertySource **sau khi bean đã được tạo**, trường `message` trong ví dụ này không tự động thay đổi.

## 26. @ConfigurationProperties và thứ tự nguồn

Một record:

```java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public record DemoProperties(
        String message,
        int retries) {
}
```

không cần biết cấu hình đến từ YAML, CLI hay nguồn Map. Binder của Spring Boot sử dụng những nguồn cấu hình trong Environment và các cơ chế binding tương ứng.

Khi các nguồn đã được thiết lập trước lúc bind, record nhận giá trị có hiệu lực theo thứ tự ưu tiên.

Điều đó có nghĩa:

```text
PropertySources ordered
      |
      v
Value resolution
      |
      v
ConfigurationProperties Binder
      |
      v
DemoProperties(message, retries)
```

**Việc thay đổi danh sách nguồn sau khi record đã tạo không khiến constructor của record tự chạy lại.** Cấu hình bất biến được dùng như một ảnh chụp tại thời điểm binding thông thường.

Nếu cần cập nhật cấu hình động lúc chạy, phải thiết kế một cơ chế refresh/rebind hoặc tạo lại những đối tượng phụ thuộc, không nên chỉ thêm PropertySource rồi kỳ vọng mọi bean thay đổi.

## 27. Không nên chỉnh Environment từ service nghiệp vụ tùy tiện

Một service xử lý đơn hàng không nên thường xuyên thực hiện:

```java
environment.getPropertySources().addFirst(...);
```

mỗi khi một request đến, bởi điều này:

1. Thay đổi nguồn cấu hình toàn ứng dụng.
2. Có thể tạo thứ tự ưu tiên khó dự đoán.
3. Không tự làm mới những bean đã nhận giá trị cũ.
4. Khi nhiều request cùng xử lý, việc thay đổi nguồn global khiến hành vi phụ thuộc vào thời điểm.
5. Khó truy vết nguồn nào tạo ra giá trị hiện tại.
6. Có nguy cơ ghi đè chính sách triển khai hoặc những khóa hệ thống khác.

Để quản lý cấu hình động hoặc theo tenant, một chiến lược có thể là cung cấp một **dịch vụ đọc cấu hình tại thời điểm sử dụng**, có cache và cơ chế đồng bộ rõ ràng, thay vì biến `Environment` thành kho trạng thái mutable cho mỗi request.

Thao tác với `MutablePropertySources` thích hợp nhất trong giai đoạn **thiết lập cấu hình có chủ đích**, không phải là kỹ thuật thay thế mọi hệ thống feature flag hoặc tenant configuration runtime.

## 28. MapPropertySource và tính thay đổi của Map

`MapPropertySource` giữ một Map chứa các giá trị. Nếu bạn đưa vào một `HashMap` có thể thay đổi rồi tiếp tục sửa Map ấy, những lần đọc về sau có thể nhìn thấy thay đổi.

Ví dụ:

```java
Map<String, Object> values = new HashMap<>();
values.put("demo.message", "A");

MapPropertySource source =
        new MapPropertySource("custom", values);
```

Nếu sau đó mã thực hiện:

```java
values.put("demo.message", "B");
```

thì nguồn Map đã bị thay đổi.

Trong một ứng dụng nhiều luồng, đây là hành vi cần thiết kế đồng bộ cẩn thận. Bốn phương thức `addFirst`, `addLast`, `addBefore`, `addAfter` quản lý **vị trí nguồn**; chúng không biến Map gốc thành một kho cấu hình động có cơ chế nhất quán, validation, audit hoặc refresh tự động.

Với giá trị ổn định:

```java
MapPropertySource source = new MapPropertySource(
        "custom",
        Map.of("demo.message", "A")
);
```

dễ kiểm soát hơn vì Map không cho phép gán lại nội dung bằng những phương thức cập nhật thông thường.

**Lưu ý:** bản thân `Map.of` không cho phép khóa hoặc giá trị null. Nếu dữ liệu có thể null, cần xử lý trước khi tạo Map.

## 29. Dùng nguồn riêng cho mỗi mục đích

Một cách tổ chức dễ quản lý là chia nguồn thành các lớp ý nghĩa:

```text
operatorOverrides
tenantConfiguration
regionalDefaults
libraryDefaults
```

Cách chia này tạo cơ hội định nghĩa quy tắc ưu tiên rõ ràng:

1. Giá trị vận hành có được ghi đè giá trị tenant không?
2. Giá trị tenant có được ghi đè mặc định theo vùng không?
3. Mặc định vùng có được ghi đè mặc định thư viện không?
4. Nguồn nào được phép chứa các khóa hệ thống của Spring Boot?
5. Có cần đưa ra audit khi thay đổi những nguồn đó không?

Nếu mọi thứ bị gộp vào một nguồn `custom` đứng đầu, rất khó biết vì sao một giá trị cuối cùng được chọn.

**Thiết kế thứ tự trước khi viết mã.** Sau đó chọn `addFirst`, `addLast`, `addBefore` và `addAfter` theo chính sách đã xác định.

## 30. Giữ an toàn khi thêm cấu hình từ nguồn bên ngoài

Một nguồn cấu hình từ xa hoặc kho dữ liệu tenant không nhất thiết đáng tin cậy để cung cấp **mọi khóa của Spring Boot**.

Ví dụ, một nguồn chỉ dành cho tenant business settings nên có whitelist:

```text
tenant.display-name
tenant.max-items
tenant.feature-enabled
```

Thay vì chấp nhận tùy ý:

```text
spring.*
server.*
management.*
logging.*
```

rồi đưa toàn bộ lên đầu danh sách.

Cách thiết kế an toàn hơn có thể gồm:

- Chỉ nạp những khóa được cho phép.
- Kiểm tra kiểu và giới hạn của dữ liệu trước khi xây PropertySource.
- Không log secret trong toàn bộ Map.
- Có chính sách độ ưu tiên cụ thể.
- Thêm nguồn đúng thời điểm, hạn chế cập nhật sau khi các bean đã tạo.
- Kiểm thử ứng dụng với nguồn có cấu hình trùng nhau.
- Từ chối dữ liệu gây thay đổi hành vi hệ thống vượt quá phạm vi tin cậy.

Một `MapPropertySource` rất đơn giản về API nhưng quyền ảnh hưởng của nó có thể rộng khi được đưa vào Environment toàn ứng dụng.

## 31. Kiểm thử trực tiếp thứ tự ưu tiên với JUnit

Có thể viết unit test không cần Spring Boot context để kiểm tra bốn thao tác.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.MutablePropertySources;
import org.springframework.core.env.PropertySourcesPropertyResolver;

class MutablePropertySourcesTest {

    private static MapPropertySource source(
            String name, String value) {
        return new MapPropertySource(
                name,
                Map.of("demo.message", value)
        );
    }

    @Test
    void addFirstHasHighestPriority() {
        MutablePropertySources sources =
                new MutablePropertySources();

        sources.addLast(source("base", "BASE"));
        sources.addFirst(source("override", "OVERRIDE"));

        var resolver = new PropertySourcesPropertyResolver(sources);

        assertEquals("OVERRIDE",
                resolver.getProperty("demo.message"));
    }

    @Test
    void addLastActsAsFallback() {
        MutablePropertySources sources =
                new MutablePropertySources();

        sources.addFirst(source("primary", "PRIMARY"));
        sources.addLast(source("fallback", "FALLBACK"));

        var resolver = new PropertySourcesPropertyResolver(sources);

        assertEquals("PRIMARY",
                resolver.getProperty("demo.message"));
    }

    @Test
    void addBeforePositionsSourceAheadOfAnchor() {
        MutablePropertySources sources =
                new MutablePropertySources();

        sources.addLast(source("base", "BASE"));
        sources.addBefore("base", source("team", "TEAM"));

        var resolver = new PropertySourcesPropertyResolver(sources);

        assertEquals("TEAM",
                resolver.getProperty("demo.message"));
    }

    @Test
    void addAfterPositionsSourceBehindAnchor() {
        MutablePropertySources sources =
                new MutablePropertySources();

        sources.addLast(source("base", "BASE"));
        sources.addAfter("base", source("fallback", "FALLBACK"));

        var resolver = new PropertySourcesPropertyResolver(sources);

        assertEquals("BASE",
                resolver.getProperty("demo.message"));
    }
}
```

Bốn test kiểm tra đúng một điều: **thứ tự của PropertySources dẫn đến kết quả ưu tiên nào**. Chúng không cần khởi động servlet container hay Spring Boot application.

Nếu test chỉ kiểm tra danh sách tên nguồn mà không hỏi `resolver.getProperty(...)`, ta có thể bỏ lỡ việc các nguồn chứa những khóa khác nhau. Vì vậy việc có ít nhất một khóa trùng để kiểm chứng thứ tự là cách học rất trực quan.

## 32. Kiểm thử việc thêm nguồn trước khi bean được bind

Khi cần xác nhận nguồn thêm bằng initializer được binder nhìn thấy, dùng một test context nhỏ.

Giả sử:

```java
package com.example.configdemo;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public record DemoProperties(String message) {
}
```

Test:

```java
package com.example.configdemo;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.MapPropertySource;

class CustomSourceBindingTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withInitializer(context ->
                            context.getEnvironment()
                                    .getPropertySources()
                                    .addFirst(new MapPropertySource(
                                            "acmeTestOverrides",
                                            Map.of("demo.message", "CUSTOM")
                                    )))
                    .withUserConfiguration(TestConfiguration.class);

    @Test
    void constructorBindingSeesCustomSource() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();

            DemoProperties properties =
                    context.getBean(DemoProperties.class);

            assertThat(properties.message()).isEqualTo("CUSTOM");
        });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(DemoProperties.class)
    static class TestConfiguration {
    }
}
```

Test này kiểm tra một điều khác với unit test thuần PropertySources: **Spring Boot binder thực sự tạo bean với dữ liệu được bổ sung vào Environment**.

Nó không kiểm tra mọi tình huống Config Data hoặc logging ở giai đoạn rất sớm. Đối với những trường hợp đó, cần integration test với cách khởi động thật và các điểm mở rộng tương ứng.

## 33. Test thiếu nguồn làm mốc

Khi ứng dụng phụ thuộc vào một nguồn mốc cụ thể, hãy kiểm tra trường hợp tên mốc không tồn tại.

Ví dụ:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.MutablePropertySources;

class MissingAnchorTest {

    @Test
    void addBeforeNeedsExistingAnchor() {
        MutablePropertySources sources =
                new MutablePropertySources();

        assertThrows(IllegalArgumentException.class, () ->
                sources.addBefore(
                        "unknownAnchor",
                        new MapPropertySource(
                                "custom",
                                Map.of("demo.message", "A")
                        )
                )
        );
    }
}
```

Nếu chính sách yêu cầu fallback khi mốc tùy chọn không có, viết test riêng cho fallback thay vì chỉ bắt lỗi rồi bỏ qua.

Bài học: **addBefore và addAfter phụ thuộc vào định danh nguồn hiện hữu**, nên tên nguồn là một phần của hợp đồng khi nhiều thành phần cùng quản lý danh sách nguồn.

## 34. Mối quan hệ với SPRING_APPLICATION_JSON

Spring Boot có khả năng nhận một đối tượng JSON được cấp qua `SPRING_APPLICATION_JSON` hoặc cơ chế tương ứng, rồi biến nó thành dữ liệu cấu hình.

Đây là một nguồn cấu hình do Boot hỗ trợ, không phải điều bạn phải tự viết bằng:

```java
sources.addFirst(new MapPropertySource(...))
```

Nếu bài toán chỉ là cung cấp một số thuộc tính cho lần chạy, trước tiên hãy cân nhắc các cơ chế có sẵn như biến môi trường, đối số CLI hoặc Config Data, thay vì tạo một initializer mới.

Tùy chỉnh PropertySources thường đáng làm khi ứng dụng cần một **nguồn dữ liệu mới có ý nghĩa riêng**, ví dụ một adapter chuyển từ registry cấu hình nội bộ sang những thuộc tính mà Spring hiểu được.

## 35. Mối quan hệ với spring.config.import

`spring.config.import` cho phép Spring Boot nạp những tài nguyên cấu hình bổ sung trong giai đoạn Config Data. Đây là một phần của cơ chế nạp cấu hình tích hợp với lựa chọn profile và thứ tự ưu tiên.

Trong khi đó:

```java
environment.getPropertySources().addFirst(custom);
```

là thao tác trực tiếp trên danh sách PropertySource trong một thời điểm cụ thể.

Hai phương pháp không có cùng hợp đồng về:

- thời điểm nạp;
- xử lý profile;
- vị trí cấu hình;
- quy tắc import;
- lỗi thiếu nguồn;
- xử lý format và thứ tự ưu tiên giữa các tài liệu Config Data.

Nếu một file hoặc location cần trở thành một nguồn cấu hình theo đúng cơ chế Config Data, nên dùng khả năng được Spring Boot hỗ trợ thay vì tự cố mô phỏng toàn bộ quy tắc bằng bốn thao tác trên danh sách.

## 36. Mối quan hệ với @PropertySource

`@PropertySource` là một cơ chế của Spring Framework để khai báo Properties resource trong cấu hình context.

`@PropertySource` có thể phù hợp với các tệp Properties truyền thống, nhưng nó không thay thế hoàn toàn Config Data của Spring Boot, đặc biệt khi cần profile-specific documents, imports hoặc những quyết định khởi động sớm.

Bốn phương thức của `MutablePropertySources` cho bạn **quyền điều khiển vị trí trực tiếp**, nhưng cũng tăng trách nhiệm phải hiểu thứ tự và vòng đời.

Chọn đúng công cụ:

| Nhu cầu | Cơ chế thường phù hợp |
| --- | --- |
| Cấu hình ứng dụng qua file chuẩn | `application.yml` / `application.properties` |
| Tài liệu theo profile, import | Config Data |
| Nguồn thuộc tính từ Map trong bộ nhớ | `MapPropertySource` |
| Kiểm soát vị trí nguồn tùy chỉnh | `MutablePropertySources` |
| Mở rộng chuẩn bị Environment | `EnvironmentPostProcessor` |
| Thêm nguồn trước tạo bean thông thường | `ApplicationContextInitializer` |
| File Properties kiểu Spring Framework | `@PropertySource`, khi phù hợp |

Không có lý do phải thay tất cả cách cấu hình chuẩn bằng một phương thức `addFirst`.

## 37. Những sai lầm thường gặp

### 37.1. Cho rằng addLast luôn ghi đè YAML

Không. `addLast` đưa nguồn về cuối, nên các nguồn đã tồn tại ở phía trên có thể thắng khi cùng khóa.

### 37.2. Cho rằng addBefore thắng toàn bộ nguồn

Không. `addBefore("B", X)` chỉ đặt X trước B. Nếu A đang đứng trước B, A vẫn có thể thắng X.

### 37.3. Cho rằng addAfter thua toàn bộ nguồn

Không. `addAfter("B", X)` đặt X sau B, nhưng X có thể đứng trước các nguồn C, D phía sau và thắng chúng.

### 37.4. Dùng tên nguồn làm mốc chưa tồn tại

`addBefore`/`addAfter` cần tìm được tên nguồn làm mốc. Nếu không, có thể ném `IllegalArgumentException`.

### 37.5. Trộn tên nguồn với khóa cấu hình

`MapPropertySource("mySource", Map.of("demo.message", "A"))` có tên nguồn là `mySource`. `demo.message` không phải tên nguồn để đưa vào `addBefore`.

### 37.6. Dùng addFirst không xét quyền của người vận hành

Một nguồn đưa lên đầu có thể thắng CLI hoặc biến môi trường cho cùng khóa, làm ứng dụng khó điều chỉnh khi triển khai.

### 37.7. Thêm nguồn sau khi các bean đã bind

Đọc trực tiếp `Environment` có thể thấy giá trị mới, nhưng `@Value` và `@ConfigurationProperties` đã được xử lý thông thường không tự cập nhật.

### 37.8. Dùng initializer để kỳ vọng Config Data chạy lại

Quá trình nạp Config Data và xử lý một số cấu hình khởi động có thể diễn ra trước initializer. Muốn bổ sung loại nguồn Config Data, cân nhắc extension đúng thời điểm.

### 37.9. Dựa vào tên nguồn Config Data nội bộ

Tên các nguồn Config Data có thể thay đổi theo file/profile/version. Nếu cần mốc ổn định, ưu tiên nguồn do bạn đặt tên và kiểm soát.

### 37.10. In toàn bộ Map cấu hình

PropertySource có thể chứa secret. Chỉ log tên nguồn hoặc những giá trị đã được xác định là không nhạy cảm.

### 37.11. Dùng nguồn mutable cho mọi request

Thay đổi Environment toàn ứng dụng trong luồng xử lý request tạo rủi ro về trạng thái và không tự làm mới các bean hiện có.

### 37.12. Không kiểm thử thứ tự khi có khóa trùng

Nếu test chỉ có những khóa khác nhau, bạn chưa thật sự xác nhận nguồn nào thắng. Hãy tạo ít nhất một khóa trùng trong các nguồn để thử ưu tiên.

## 38. Quy trình chẩn đoán khi giá trị không đúng

Khi giá trị `demo.message` không đúng dự kiến sau khi thêm PropertySource, làm theo thứ tự:

1. **Xác nhận Environment có đúng là môi trường ứng dụng đang chạy không.** Một test context khác có thể dùng một danh sách nguồn khác.
2. **Liệt kê tên các nguồn theo thứ tự.** Không cần in giá trị nhạy cảm.
3. **Xác nhận tên nguồn tùy chỉnh có xuất hiện không.** Nếu không, initializer/processor chưa được đăng ký hoặc chưa chạy.
4. **Kiểm tra vị trí của nguồn mới.** `addFirst`, `addLast`, `addBefore`, `addAfter` có đúng chính sách không?
5. **Kiểm tra nguồn thực sự chứa khóa.** Ví dụ `demo.message` khác `demo.mesage`.
6. **Xác nhận có nguồn cao hơn cung cấp cùng khóa không.**
7. **Xem thời điểm thêm nguồn.** Bean đã được tạo và bind trước đó chưa?
8. **Xem giá trị có bị conversion hoặc validation từ chối không.**
9. **Kiểm tra profile và Config Data.** Có nguồn nào không được nạp hoặc được nạp theo profile khác không?
10. **Viết test cô lập với `MutablePropertySources` và `PropertySourcesPropertyResolver`.** Sau đó mới kiểm thử Spring Boot context.

Cách chẩn đoán này tách nguyên nhân “thứ tự nguồn sai” khỏi “khóa sai”, “nguồn không được đăng ký” và “thời điểm thêm quá muộn”.

## 39. Bài tập A: Dự đoán thứ tự

Ban đầu:

```text
[A, B, C]
```

Thực hiện:

```java
sources.addFirst(X);
sources.addAfter("B", Y);
sources.addBefore("C", Z);
sources.addLast(W);
```

Giả sử các tên nguồn tồn tại, riêng `X, Y, Z, W` là nguồn mới và không trùng tên.

**Câu hỏi:** thứ tự cuối cùng là gì?

**Đáp án:**

```text
[X, A, B, Y, Z, C, W]
```

Giải thích:

- `X` đứng đầu.
- `Y` đứng sau B.
- `Z` đứng trước C (sau Y).
- `W` đứng cuối.

## 40. Bài tập B: Nguồn nào thắng?

Có các nguồn theo thứ tự:

```text
1. commandLine       demo.mode=cli
2. tenantSettings    demo.mode=tenant
3. libraryDefaults   demo.mode=default
```

**Câu hỏi 1:** `Environment#getProperty("demo.mode")` trả về gì?

**Đáp án:** `cli`.

**Câu hỏi 2:** nếu chuyển `tenantSettings` lên đầu bằng `addFirst`, kết quả có thể là gì?

**Đáp án:** `tenant`.

**Câu hỏi 3:** nếu đặt một nguồn `regionalSettings` với `demo.mode=region` bằng `addAfter("tenantSettings", ...)` khi thứ tự ban đầu chưa đổi, nguồn nào thắng?

**Đáp án:** `commandLine` vẫn đứng trước `tenantSettings`, nên `cli` thắng.

## 41. Bài tập C: Thêm default mà không ghi đè người dùng

Ứng dụng đã nhận cấu hình người dùng qua YAML và CLI. Bạn muốn cung cấp:

```properties
demo.retries=2
demo.region=vn
```

chỉ khi các nguồn khác không có khóa.

**Câu hỏi:** nên dùng phương thức nào trong bốn phương thức?

**Đáp án gợi ý:** `addLast`, vì nguồn được đặt ở cuối làm fallback.

Ví dụ:

```java
sources.addLast(new MapPropertySource(
        "acmeDefaults",
        Map.of(
                "demo.retries", 2,
                "demo.region", "vn"
        )
));
```

Nếu hệ thống đã có nhiều default có thứ tự nội bộ, `addBefore` hoặc `addAfter` quanh một nguồn mốc do bạn quản lý cũng có thể phù hợp.

## 42. Bài tập D: Chọn addBefore hay addAfter

Danh sách:

```text
operatorSettings
tenantSettings
libraryDefaults
```

Yêu cầu: nguồn `regionalSettings` phải **thua tenantSettings** nhưng **thắng libraryDefaults**.

Một cách làm:

```java
sources.addAfter(
        "tenantSettings",
        regionalSettings
);
```

Kết quả:

```text
operatorSettings
tenantSettings
regionalSettings
libraryDefaults
```

Một cách khác là `addBefore("libraryDefaults", regionalSettings)` trong danh sách ban đầu. Cả hai đều thỏa quan hệ ưu tiên được yêu cầu trong tình huống này.

## 43. Bài tập E: Tại sao addBefore không chạy?

Mã:

```java
sources.addBefore(
        "applicationConfig",
        new MapPropertySource(
                "tenantSettings",
                Map.of("demo.message", "Tenant")
        )
);
```

Nhưng danh sách nguồn thực tế không có tên `applicationConfig`.

**Kết luận:** thao tác có thể thất bại vì tên mốc không tồn tại. Không nên suy đoán tên nguồn Config Data nội bộ từ một phiên bản Spring Boot cũ.

**Cách sửa:** lấy tên thực tế hoặc, tốt hơn, sử dụng một nguồn mốc do ứng dụng tự định nghĩa với tên ổn định.

## 44. Bài tập F: Thêm nguồn sau ApplicationRunner

Trong `ApplicationRunner`, bạn thêm:

```java
environment.getPropertySources().addFirst(
        new MapPropertySource(
                "lateOverride",
                Map.of("demo.message", "LATE")
        )
);
```

Trước đó một singleton bean đã được tạo với:

```java
public GreetingService(
        @Value("${demo.message}") String message) {
    this.message = message;
}
```

**Câu hỏi:** field `message` trong bean có tự đổi thành `LATE` không?

**Đáp án:** không. `@Value` đã được giải quyết khi bean được tạo. Việc chỉnh nguồn sau đó có thể ảnh hưởng các lần đọc `Environment` trực tiếp, nhưng không tự tiêm lại trường hoặc chạy lại constructor.

## 45. Ghi nhớ

- `Environment` cung cấp API đọc cấu hình; `ConfigurableEnvironment` cho phép truy cập danh sách nguồn có thể chỉnh sửa.
- `PropertySource` đại diện cho một nguồn thuộc tính có tên; `MapPropertySource` là một triển khai tiện dụng cho dữ liệu dạng Map.
- `MutablePropertySources` quản lý thứ tự các nguồn. **Nguồn đứng trước thường có ưu tiên cao hơn khi giải quyết một khóa trùng.**
- `addFirst(X)` đặt X ở đầu; `addLast(X)` đặt X ở cuối; `addBefore("B",X)` đặt X trước B; `addAfter("B",X)` đặt X sau B.
- `addBefore` và `addAfter` cần tên nguồn mốc thực sự tồn tại. Chọn tên nguồn tùy chỉnh duy nhất và ổn định.
- Dùng `addLast` cho default dự phòng; dùng `addFirst` khi thực sự cần override mạnh; dùng các thao tác tương đối cho chính sách ưu tiên nhiều lớp.
- Mở rộng Environment **đúng thời điểm**: `ApplicationContextInitializer` phù hợp trước tạo bean thông thường; `EnvironmentPostProcessor` phục vụ giai đoạn chuẩn bị môi trường sớm hơn.
- Một thay đổi PropertySources **không tự làm mới** những bean `@Value` hoặc `@ConfigurationProperties` đã nhận giá trị.
- Thêm PropertySource không thay thế toàn bộ Config Data, profile, `spring.config.import` hoặc các điểm mở rộng chuyên biệt cho nguồn cấu hình mới.
- Tránh dùng nguồn tùy chỉnh để ghi đè không kiểm soát các khóa hệ thống, tránh lộ secret và không cập nhật danh sách nguồn toàn ứng dụng cho từng request.
- Kiểm thử ưu tiên bằng `MutablePropertySources` + `PropertySourcesPropertyResolver`, rồi kiểm thử việc binder nhận nguồn tùy chỉnh ở thời điểm khởi tạo.

# Gợi ý giá trị, đánh dấu ngừng khuyến nghị và khai báo khóa thay thế

Spring Boot hỗ trợ **configuration metadata** để công cụ phát triển (đặc biệt là IDE) hiểu cấu trúc các property cấu hình ứng dụng. Ngoài việc mô tả tên, kiểu dữ liệu, giá trị mặc định và ý nghĩa của một property, metadata có thể cung cấp **gợi ý những giá trị hợp lý**, đánh dấu **property đã bị deprecated** và chỉ rõ **property mới được khuyến nghị thay thế**.

Các thông tin này rất hữu ích khi dự án có nhiều cấu hình riêng, khi đóng gói một Spring Boot starter cho đội khác sử dụng, hoặc khi muốn đổi tên một khóa cấu hình mà không khiến người dùng thư viện bị bất ngờ.

Tuy nhiên, cần hiểu đúng ranh giới:

> **Metadata giúp công cụ hiểu và hướng dẫn người viết cấu hình. Nó không tự tạo luật validation, không tự đổi key cũ sang key mới, không tự di chuyển giá trị và không bảo đảm Spring Boot in cảnh báo khi chạy.**

Bài này đi từ cách sinh metadata cho `@ConfigurationProperties` đến cách bổ sung `hints`, khai báo `deprecation` với `reason` và `replacement`, sử dụng `@DeprecatedConfigurationProperty`, hỗ trợ giai đoạn chuyển đổi giữa các phiên bản và kiểm tra tệp JSON đóng gói.

## 1. Configuration metadata phục vụ vấn đề gì?

Giả sử một thư viện nội bộ cho phép cấu hình:

~~~yaml
warehouse:
  client:
    mode: "http"
    endpoint: "https://warehouse.example.invalid"
    timeout: 3s
~~~

Người sử dụng thư viện cần biết:

- Có những key nào dưới `warehouse.client`?
- `mode` nhận những giá trị nào, chẳng hạn `http` hoặc `queue`?
- `timeout` dùng kiểu gì và mặc định có hay không?
- Nếu tên `base-url` cũ đã được đổi thành `endpoint`, người dùng có được IDE nhắc không?
- Key cũ còn được phần mềm hỗ trợ ở runtime hay đã thực sự bị loại bỏ?

Những câu hỏi trên có hai loại trả lời.

**Loại thứ nhất: hợp đồng chạy thật.** Class `@ConfigurationProperties`, Binder, validation và logic ứng dụng quyết định key được đọc ra sao và giá trị nào hợp lệ.

**Loại thứ hai: thông tin cho công cụ.** Metadata mô tả type, description, hints và deprecation, để IDE có thể autocomplete, hiển thị giải thích hoặc cảnh báo người dùng.

Tệp thường được các công cụ nhận diện có tên:

~~~text
META-INF/spring-configuration-metadata.json
~~~

Đây là tài nguyên được đóng gói trên classpath. Nó có thể được sinh tự động bởi annotation processor, rồi được bổ sung từ tệp metadata viết tay khi cần.

## 2. Bốn khái niệm cần phân biệt

| Khái niệm | Mục đích | Có tự thay đổi runtime binding không? |
| --- | --- | --- |
| `properties` trong metadata | Mô tả tên, type, default, description | Không |
| `hints` | Đề xuất giá trị hoặc nhà cung cấp gợi ý cho IDE | Không |
| `deprecation` | Báo rằng khóa không còn được khuyến nghị hoặc đã loại bỏ | Không |
| `replacement` | Chỉ khóa nên dùng thay khóa cũ | Không tự chuyển giá trị |

Ví dụ khi metadata khai báo:

~~~json
{
  "name": "warehouse.client.mode",
  "values": [
    { "value": "http" },
    { "value": "queue" }
  ]
}
~~~

IDE có thể gợi ý hai giá trị này. Nhưng nếu bean Java vẫn nhận `String mode` và ứng dụng không kiểm tra giá trị, người dùng vẫn có thể cấu hình `mode: "typo"`; metadata không tự bảo đảm ứng dụng từ chối.

Ngược lại, nếu Java dùng một `enum`:

~~~java
public enum ClientMode {
    HTTP,
    QUEUE
}
~~~

thì Binder có cơ chế chuyển đổi enum và có thể từ chối giá trị không chuyển được theo quy tắc conversion. Đây là **ràng buộc của type/runtime**, không phải vì metadata values đã được khai báo.

## 3. Bắt đầu từ một class @ConfigurationProperties

Ví dụ typed configuration:

~~~java
package example.warehouse;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "warehouse.client")
public record WarehouseClientProperties(
        String mode,
        URI endpoint,
        Duration timeout
) {}
~~~

Đăng ký:

~~~java
package example.warehouse;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(WarehouseClientProperties.class)
class WarehouseClientConfiguration {
}
~~~

File cấu hình:

~~~yaml
warehouse:
  client:
    mode: "http"
    endpoint: "https://warehouse.example.invalid"
    timeout: 3s
~~~

Như vậy, cấu hình runtime đã có một hợp đồng typed object. Nếu bật annotation processor tương ứng, Spring Boot có thể sinh metadata với các property bên dưới prefix `warehouse.client`.

Điều cần nhớ:

- `@ConfigurationProperties` gắn tên prefix với một Java type.
- `@EnableConfigurationProperties` hoặc `@ConfigurationPropertiesScan` đăng ký type đó làm configuration-properties bean.
- Binder đọc các PropertySource, chuyển kiểu và tạo object.
- Configuration metadata giúp công cụ hiểu các key đó.

Annotation processor **không phải** cơ chế đăng ký bean. Có metadata JSON cũng không làm bean tự xuất hiện trong ApplicationContext.

## 4. Bật spring-boot-configuration-processor

Thành phần thường dùng để tạo metadata là `spring-boot-configuration-processor`.

### 4.1. Maven

Ví dụ dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
~~~

Trong project Maven thông thường dùng Spring Boot dependency management, phiên bản processor được quản lý theo phiên bản Boot của project. `optional=true` giúp tránh vô tình lan dependency processor sang người tiêu thụ qua quan hệ dependency thông thường; nó **không** thay thế việc cấu hình annotation processing.

Nếu project quản lý annotation processors qua `maven-compiler-plugin` hoặc cơ chế của JDK mới, hãy bảo đảm processor **thực sự được javac chạy** ở module chứa `@ConfigurationProperties`. Đặc biệt với những cấu hình Java/Maven có explicit processor list hoặc JDK không tự bật annotation processing, chỉ thêm dependency chưa chắc đủ.

Ví dụ cấu hình processor path ở một dự án có plugin/compiler setup phù hợp:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <annotationProcessorPaths>
                    <path>
                        <groupId>org.springframework.boot</groupId>
                        <artifactId>spring-boot-configuration-processor</artifactId>
                        <version><!-- phiên bản đồng bộ Spring Boot --></version>
                    </path>
                </annotationProcessorPaths>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Đoạn XML minh họa cách khai báo processor trong build plugin; trong POM thực tế, thẻ `version` cần **giá trị phiên bản hợp lệ** hoặc cơ chế quản lý plugin/processor tương ứng, không được để comment như một phiên bản chạy được.

### 4.2. Gradle Groovy DSL

~~~groovy
dependencies {
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
~~~

### 4.3. Gradle Kotlin DSL

~~~kotlin
dependencies {
    annotationProcessor(
        "org.springframework.boot:spring-boot-configuration-processor"
    )
}
~~~

Gradle có configuration riêng cho annotation processors. Một thư viện chỉ chứa `@ConfigurationProperties` có thể cần processor trong **chính module đó**, không phải chỉ trong module ứng dụng tiêu thụ.

Trong project Kotlin thuần, annotation processing và metadata có những hướng dẫn riêng cho Kotlin compiler; ví dụ ở đây tập trung vào Java.

## 5. Metadata được sinh ra nằm ở đâu?

Tên file đích trên classpath là:

~~~text
META-INF/spring-configuration-metadata.json
~~~

Vị trí ở thư mục build phụ thuộc Maven, Gradle, annotation processor và packaging. Thông thường có thể tìm ở:

~~~text
target/classes/META-INF/spring-configuration-metadata.json

build/classes/java/main/META-INF/spring-configuration-metadata.json
~~~

Những đường dẫn này chỉ là ví dụ. File trong **JAR được phát hành** mới là tài nguyên cuối cùng mà IDE hoặc công cụ tiêu thụ có thể sử dụng.

Có thể kiểm tra:

~~~bash
jar tf build/libs/warehouse-client.jar
~~~

hoặc:

~~~bash
jar tf target/warehouse-client.jar
~~~

Rồi tìm:

~~~text
META-INF/spring-configuration-metadata.json
~~~

Nếu không thấy file, đừng lập tức kết luận `@ConfigurationProperties` bị lỗi runtime. Có thể đơn giản là annotation processor chưa chạy, task compilation không được cấu hình hoặc module artifact không đóng gói tệp metadata.

## 6. Cấu trúc JSON metadata

Một file metadata thường dùng ba nhóm cấp cao:

~~~json
{
  "groups": [
    {
      "name": "warehouse.client",
      "type": "example.warehouse.WarehouseClientProperties",
      "sourceType": "example.warehouse.WarehouseClientProperties"
    }
  ],
  "properties": [
    {
      "name": "warehouse.client.mode",
      "type": "java.lang.String",
      "description": "Protocol used to reach the warehouse service."
    },
    {
      "name": "warehouse.client.endpoint",
      "type": "java.net.URI",
      "description": "Base URI of the warehouse service."
    },
    {
      "name": "warehouse.client.timeout",
      "type": "java.time.Duration",
      "description": "Maximum wait time for one request."
    }
  ],
  "hints": [
    {
      "name": "warehouse.client.mode",
      "values": [
        {
          "value": "http",
          "description": "Direct HTTP integration."
        },
        {
          "value": "queue",
          "description": "Asynchronous message-based integration."
        }
      ]
    }
  ]
}
~~~

Đây là **minh họa cấu trúc metadata**, không phải lời khuyên tự viết toàn bộ groups/properties khi processor đã sinh được chúng.

- `groups` mô tả một nhóm property, thường gắn với một prefix.
- `properties` mô tả các key cụ thể cùng Java type và thông tin bổ trợ.
- `hints` cung cấp gợi ý giá trị hoặc provider cho một key được hỗ trợ.

Tập trường thực tế còn có `defaultValue`, `sourceMethod`, deprecation metadata và các trường khác theo schema Spring Boot. Không nên tự thêm những trường tùy ý rồi kỳ vọng IDE hiểu.

JSON metadata phải đúng cú pháp JSON: không được có comment trong file, không được có dấu phẩy dư và phải dùng dấu nháy kép cho key/value chuỗi.

## 7. Tệp bổ sung: additional-spring-configuration-metadata.json

Annotation processor sinh được nhiều thông tin từ Java type, nhưng không thể tự đoán hết tất cả giá trị mode mà dự án muốn gợi ý.

Spring Boot hỗ trợ tệp bổ sung ở đường dẫn:

~~~text
src/main/resources/
  META-INF/
    additional-spring-configuration-metadata.json
~~~

Nội dung mẫu:

~~~json
{
  "hints": [
    {
      "name": "warehouse.client.mode",
      "values": [
        {
          "value": "http",
          "description": "Use an HTTP client."
        },
        {
          "value": "queue",
          "description": "Publish messages to a queue."
        }
      ]
    }
  ]
}
~~~

Khi annotation processor được cấu hình đúng và nhận ra tài nguyên bổ sung, thông tin có thể được kết hợp vào tệp `spring-configuration-metadata.json` được sinh/đóng gói.

**Lưu ý về thứ tự build:** Trong một số Maven/Gradle cấu hình đặc biệt, processor cần nhìn thấy additional metadata trong compilation classpath/resource pipeline. Hãy kiểm tra artifact sau `clean build` thay vì chỉ kết luận từ việc file nguồn đã tồn tại.

Không tạo một tệp `spring-configuration-metadata.json` viết tay để ghi đè vô tình output processor, nếu mục tiêu chỉ là bổ sung hints hoặc mô tả. Hãy dùng đường dẫn `additional-spring-configuration-metadata.json` đúng quy ước.

## 8. Cách khai báo gợi ý giá trị với hints.values

Ví dụ property:

~~~yaml
warehouse:
  client:
    mode: "http"
~~~

Bạn muốn IDE hiện hai lựa chọn quen thuộc:

~~~json
{
  "hints": [
    {
      "name": "warehouse.client.mode",
      "values": [
        {
          "value": "http",
          "description": "Use the HTTP integration."
        },
        {
          "value": "queue",
          "description": "Use the queue integration."
        }
      ]
    }
  ]
}
~~~

Phần tử `values` chứa:

- `value`: giá trị mà công cụ có thể đề xuất.
- `description`: thông tin giúp người dùng lựa chọn, thường là trường tùy chọn.

Đây là **danh sách gợi ý**, không phải một danh sách quyền truy cập hay bộ lọc giá trị bắt buộc.

Một số IDE có thể dùng metadata này để autocomplete giá trị sau dấu `:` trong YAML hoặc `=` trong properties. Nhưng hành vi IDE phụ thuộc plugin, phiên bản và khả năng hỗ trợ metadata.

Nếu ứng dụng không được phép nhận bất kỳ chuỗi nào ngoài `http` và `queue`, cần kiểm tra điều đó **ở runtime** bằng enum, Bean Validation hoặc logic validation phù hợp.

## 9. Gợi ý giá trị không có nghĩa là enum runtime

So sánh hai kiểu Java.

**Kiểu String:**

~~~java
@ConfigurationProperties(prefix = "warehouse.client")
public record WarehouseClientProperties(String mode) {}
~~~

Thêm metadata values có thể giúp IDE gợi ý `http` hoặc `queue`. Nhưng `String mode` vẫn có thể nhận `"ftp"` nếu không có validation.

**Kiểu enum:**

~~~java
public enum ClientMode {
    HTTP,
    QUEUE
}
~~~

~~~java
@ConfigurationProperties(prefix = "warehouse.client")
public record WarehouseClientProperties(ClientMode mode) {}
~~~

Ở đây Binder áp dụng conversion cho enum. Trên nhiều trường hợp, annotation processor/IDE còn có thể suy ra các lựa chọn từ enum. Hints viết tay có thể không cần thiết nếu type đã biểu diễn đầy đủ tập giá trị.

Chọn:

- `String` + hints: khi bộ giá trị gợi ý phổ biến nhưng ứng dụng cho phép giá trị mở rộng hoặc có quy tắc riêng.
- `enum`: khi tập giá trị đóng và được Java model kiểm soát.
- `String` + `@Pattern`/custom validator: khi chuỗi có định dạng hoặc miền hợp lệ nhưng không muốn/không thể dùng enum.

Metadata không thay thế thiết kế type Java.

## 10. Gợi ý cho property số hoặc boolean

Giả sử:

~~~yaml
report:
  level: 2
  enabled: true
~~~

Có thể mô tả các mức level thông dụng:

~~~json
{
  "hints": [
    {
      "name": "report.level",
      "values": [
        { "value": 1, "description": "Light reporting." },
        { "value": 2, "description": "Standard reporting." },
        { "value": 3, "description": "Detailed reporting." }
      ]
    }
  ]
}
~~~

Nhưng nếu Java dùng `Integer level`, giá trị `100` vẫn có thể bind được. Muốn ràng buộc 1..3:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;

@ConfigurationProperties(prefix = "report")
@Validated
public record ReportProperties(
        @Min(1) @Max(3) int level
) {}
~~~

Tương tự, với boolean, kiểu Java đã diễn đạt tập true/false. Việc thêm hints không tự động bổ sung logic bật/tắt feature.

Một quy tắc: **đừng lạm dụng hints để diễn tả điều mà type system/validation đã làm tốt hơn**.

## 11. Hints providers và sự khác biệt với values

Ngoài `values` tĩnh, metadata cho phép mô tả **provider** để IDE hoặc công cụ lấy gợi ý từ ngữ cảnh.

Ví dụ dạng tổng quát:

~~~json
{
  "hints": [
    {
      "name": "warehouse.client.profile",
      "providers": [
        {
          "name": "spring-profile-name"
        }
      ]
    }
  ]
}
~~~

Provider `spring-profile-name` là một trong các tên provider có quy ước trong Spring Boot metadata. Công cụ hỗ trợ có thể dùng ngữ cảnh project để đề xuất tên profile, thay vì bạn phải hard-code tất cả profile vào mảng values.

Một số provider khác mà Spring Boot metadata có quy ước như `class-reference`, `spring-bean-reference`, `logger-name` và `any`. Khả năng hỗ trợ của từng provider phụ thuộc IDE và tình huống.

Không nên đặt một tên provider tưởng tượng như `"my-custom-provider"` rồi kỳ vọng mọi IDE tự biết tìm dữ liệu. Provider metadata là **hợp đồng với công cụ**, không phải Java SPI tự chạy của Spring Boot ở runtime.

Nếu bộ giá trị là hai hoặc ba chuỗi tĩnh, `values` thường đủ. Nếu danh sách phụ thuộc bean, class hoặc profile hiện có trong project, provider được công cụ hỗ trợ có thể phù hợp hơn.

## 12. Kết hợp values và provider

Một property có thể có vài giá trị phổ biến, nhưng vẫn cho phép tên do người dùng tự đặt.

Ví dụ:

~~~json
{
  "hints": [
    {
      "name": "routing.strategy",
      "values": [
        {
          "value": "round-robin",
          "description": "Distribute requests in sequence."
        },
        {
          "value": "least-connections",
          "description": "Prefer the backend with fewer connections."
        }
      ],
      "providers": [
        {
          "name": "any"
        }
      ]
    }
  ]
}
~~~

Thông điệp cho công cụ là: có một số đề xuất hữu ích, nhưng các giá trị khác cũng có thể tồn tại theo hợp đồng cấu hình.

**Cảnh báo:** thông điệp “có thể nhập giá trị khác” trong metadata không được coi là giấy phép runtime. Nếu ứng dụng chỉ nhận hai strategy, logic Java phải giới hạn hai strategy và có thể không cần provider `any`.

Metadata tạo trải nghiệm soạn cấu hình, không thay thế cấu trúc domain.

## 13. Gợi ý key của Map và giá trị của Map

Khi property là một Map, nhu cầu gợi ý có thể nằm ở **key** hoặc **value**.

Ví dụ:

~~~yaml
warehouse:
  channels:
    email: "enabled"
    webhook: "disabled"
~~~

Java:

~~~java
@ConfigurationProperties(prefix = "warehouse")
public record WarehouseProperties(
        java.util.Map<String, String> channels
) {}
~~~

Trong metadata bổ sung, quy ước `.keys` hoặc `.values` có thể được dùng trong tên hint cho map entry.

Ví dụ:

~~~json
{
  "hints": [
    {
      "name": "warehouse.channels.keys",
      "values": [
        { "value": "email", "description": "Email channel." },
        { "value": "webhook", "description": "Webhook channel." }
      ]
    },
    {
      "name": "warehouse.channels.values",
      "values": [
        { "value": "enabled", "description": "Channel is active." },
        { "value": "disabled", "description": "Channel is inactive." }
      ]
    }
  ]
}
~~~

Hình thức này hữu ích khi keys/values cần gợi ý theo tập phổ biến. Nhưng bạn phải nhớ:

- Map key có thể bị normalize hoặc bind theo quy tắc riêng (đặc biệt với ký tự đặc biệt).
- Hints không giới hạn toàn bộ Map vào hai key trên.
- Nếu value là một object phức tạp, thường nên khai báo properties type có cấu trúc và validation, không cố nhét mọi rules vào hint.
- Nếu Map entry key cần có tập hợp đóng, phải thiết kế validation hoặc type tương ứng.

## 14. Khai báo description và defaultValue: giúp gợi ý có ngữ cảnh

Một danh sách values thiếu lời giải thích dễ gây hiểu nhầm. Khi thiết kế metadata, hãy mô tả rõ:

~~~json
{
  "properties": [
    {
      "name": "warehouse.client.timeout",
      "type": "java.time.Duration",
      "description": "Request timeout; use a duration such as 3s.",
      "defaultValue": "3s"
    }
  ]
}
~~~

Trường `description` giúp IDE hiển thị ý nghĩa của key. `defaultValue` mô tả **mặc định được công bố**.

Nhưng cần cẩn thận: **thêm `defaultValue` vào metadata không tự gán mặc định cho Binder**. Nếu ứng dụng thật không có default thì metadata có thể trở thành thông tin sai.

Default runtime phải đến từ một nơi thực sự có tác dụng, chẳng hạn giá trị khởi tạo của JavaBean, constructor-binding `@DefaultValue`, hoặc property source mặc định được ứng dụng cung cấp.

Nếu processor đã sinh metadata của class, thường nên sửa type/Javadoc đúng nguồn hoặc bổ sung metadata một cách có chủ đích, tránh tạo hai phần mô tả mâu thuẫn.

## 15. Deprecated property nghĩa là gì?

Khi một khóa không còn được khuyến nghị, có thể đánh dấu nó là **deprecated** để người dùng biết nên chuyển sang khóa mới.

Ví dụ phiên bản cũ:

~~~yaml
warehouse:
  client:
    base-url: "https://warehouse.example.invalid"
~~~

Phiên bản mới dùng:

~~~yaml
warehouse:
  client:
    endpoint: "https://warehouse.example.invalid"
~~~

Trong giai đoạn chuyển đổi, nhà phát triển muốn thông báo:

> `warehouse.client.base-url` là key cũ. Hãy sử dụng `warehouse.client.endpoint`.

Configuration metadata cho phép mô tả thông điệp đó. Tuy nhiên, “deprecated” có thể mang nhiều mức ý nghĩa:

- **Deprecated nhưng vẫn được runtime hỗ trợ** để người dùng có thời gian cập nhật.
- **Đã bị loại bỏ khỏi runtime**, IDE không nên gợi ý dùng nữa.
- **Thay bằng một key khác** có cấu trúc hoặc ý nghĩa mới.
- **Không có khóa thay thế trực tiếp**, vì tính năng cũ đã bị loại bỏ.

Không nên gắn deprecation chỉ vì một key có tên không đẹp. Cần có kế hoạch tương thích và lý do rõ ràng.

## 16. Cấu trúc deprecation trong metadata

Trong JSON metadata, một property có thể chứa trường `deprecation`:

~~~json
{
  "properties": [
    {
      "name": "warehouse.client.base-url",
      "type": "java.net.URI",
      "description": "Legacy base URL for the warehouse client.",
      "deprecation": {
        "level": "warning",
        "reason": "Renamed for consistency with client endpoint settings.",
        "replacement": "warehouse.client.endpoint"
      }
    }
  ]
}
~~~

Ý nghĩa các trường:

| Field | Ý nghĩa |
| --- | --- |
| `deprecation.level` | Mức độ: `warning` hoặc `error` theo metadata schema |
| `deprecation.reason` | Giải thích vì sao key không còn được khuyến nghị |
| `deprecation.replacement` | Tên property mới được đề xuất, nếu có |

`replacement` nên dùng **tên property đầy đủ theo prefix**, ví dụ `warehouse.client.endpoint`. Đừng chỉ viết `endpoint` nếu IDE cần biết chính xác khóa mới.

Các thông tin này phục vụ trải nghiệm công cụ, không tự thực hiện thay đổi logic.

## 17. Mức warning và error khác nhau thế nào?

Trong configuration metadata của Spring Boot, deprecation có hai mức thường gặp:

**`warning`**: property không còn là lựa chọn khuyến nghị; thông thường có thể vẫn tồn tại để giữ tương thích. IDE có thể cảnh báo và gợi ý migrate.

**`error`**: property đã không còn được hỗ trợ theo metadata, nên công cụ có thể hiển thị cảnh báo nghiêm trọng hơn và không đề xuất tiếp tục dùng.

Ví dụ:

~~~json
{
  "properties": [
    {
      "name": "warehouse.client.legacy-mode",
      "type": "java.lang.String",
      "deprecation": {
        "level": "warning",
        "reason": "Use a typed mode setting.",
        "replacement": "warehouse.client.mode"
      }
    },
    {
      "name": "warehouse.client.old-debug",
      "type": "java.lang.Boolean",
      "deprecation": {
        "level": "error",
        "reason": "This configuration option was removed."
      }
    }
  ]
}
~~~

**Điều rất dễ nhầm:** `level:"error"` trong metadata **không có nghĩa Spring Boot tự ném exception khi thấy property đó**. Nó là mức đánh dấu cho công cụ hỗ trợ metadata. Nếu ứng dụng cần từ chối key đã loại bỏ, phải có cơ chế kiểm tra riêng ở runtime, hoặc đơn giản key không còn được bind/sử dụng theo thiết kế và có chính sách unknown-property phù hợp.

Không được mô tả các mức metadata như một cơ chế security enforcement.

## 18. @DeprecatedConfigurationProperty trên getter

Spring Boot có annotation `@DeprecatedConfigurationProperty` thuộc package:

~~~java
org.springframework.boot.context.properties.DeprecatedConfigurationProperty
~~~

Annotation này hỗ trợ processor nhận biết rằng một configuration property đã deprecated, với `reason` và `replacement`.

Ví dụ JavaBean-style:

~~~java
package example.warehouse;

import java.net.URI;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.DeprecatedConfigurationProperty;

@ConfigurationProperties(prefix = "warehouse.client")
public class WarehouseClientProperties {

    private URI baseUrl;
    private URI endpoint;

    @Deprecated
    @DeprecatedConfigurationProperty(
        reason = "The base-url property was renamed to endpoint.",
        replacement = "warehouse.client.endpoint"
    )
    public URI getBaseUrl() {
        return baseUrl;
    }

    @Deprecated
    public void setBaseUrl(URI baseUrl) {
        this.baseUrl = baseUrl;
    }

    public URI getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(URI endpoint) {
        this.endpoint = endpoint;
    }

    public URI effectiveEndpoint() {
        return endpoint != null ? endpoint : baseUrl;
    }
}
~~~

Đoạn code minh họa hai trách nhiệm:

1. Getter `getBaseUrl()` được đánh dấu là property cũ để processor sinh deprecation metadata.
2. Phương thức `effectiveEndpoint()` **chủ động thực hiện fallback ở runtime** từ endpoint mới sang baseUrl cũ.

`@DeprecatedConfigurationProperty` **không tự tạo fallback**. Nếu xóa `effectiveEndpoint()` hoặc không dùng logic tương đương, metadata vẫn có thể gợi ý migrate nhưng runtime không tự ưu tiên key mới.

Trong ví dụ, khi cả hai key cùng được khai báo, code chọn `endpoint` trước. Đây là **quyết định tương thích của ứng dụng**, không phải độ ưu tiên giữa hai tên property khác nhau của Spring Boot.

## 19. Vì sao annotation nằm ở getter?

Với JavaBean-style `@ConfigurationProperties`, metadata processor có thể tìm property thông qua accessor. Để gắn deprecation cho một property theo cách quen thuộc, Spring Boot khuyến nghị đặt `@DeprecatedConfigurationProperty` trên getter tương ứng.

Ví dụ:

~~~java
@Deprecated
@DeprecatedConfigurationProperty(
    reason = "Use client.request-timeout instead.",
    replacement = "client.request-timeout"
)
public Duration getTimeout() {
    return timeout;
}
~~~

Các điểm cần phân biệt:

- `@Deprecated` là annotation chuẩn Java báo một API member không còn được khuyến nghị.
- `@DeprecatedConfigurationProperty` truyền **thông tin deprecation dành riêng cho configuration metadata**.
- Annotation này không đổi tên field, không chuyển đổi binding và không tạo alias trong Environment.
- `@DeprecatedConfigurationProperty` có target thích hợp với method; không nên giả định có thể đặt trực tiếp lên mọi record component hoặc constructor parameter rồi processor chắc chắn nhận đúng.

Với immutable record không có JavaBean getter truyền thống, hoặc với property đã bị xóa khỏi source, **tệp additional metadata** thường là lựa chọn rõ ràng để mô tả deprecation và replacement.

## 20. Khai báo deprecated property thủ công cho record

Giả sử type mới đã đổi thành:

~~~java
import java.net.URI;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "warehouse.client")
public record WarehouseClientProperties(
        URI endpoint
) {}
~~~

Nhưng dự án muốn công cụ vẫn hiển thị thông tin rằng `warehouse.client.base-url` là key cũ.

Có thể khai báo deprecation thủ công trong:

~~~text
src/main/resources/META-INF/
  additional-spring-configuration-metadata.json
~~~

Nội dung:

~~~json
{
  "properties": [
    {
      "name": "warehouse.client.base-url",
      "type": "java.net.URI",
      "description": "Legacy configuration key.",
      "deprecation": {
        "level": "warning",
        "reason": "The key was renamed.",
        "replacement": "warehouse.client.endpoint"
      }
    }
  ]
}
~~~

Nhưng phải thống nhất với **hành vi thực tế của phiên bản ứng dụng**.

Nếu code mới chỉ bind `endpoint`, cấu hình dùng `base-url` **không nhất thiết còn tác dụng**. Khai báo warning với lý do “key chỉ mới renamed nhưng vẫn hoạt động” sẽ gây hiểu nhầm nếu runtime đã ngừng hỗ trợ nó. Khi key thật sự bị loại bỏ, hãy xem xét mức `error` và ghi rõ kế hoạch migration.

Nếu cần giữ tương thích, phải có code xử lý legacy key, chẳng hạn hỗ trợ cả hai property trong một JavaBean hoặc một adapter configuration phù hợp.

## 21. Replacement không phải alias

Đây là điều quan trọng nhất khi khai báo khóa thay thế.

Metadata:

~~~json
{
  "deprecation": {
    "level": "warning",
    "reason": "Renamed to endpoint.",
    "replacement": "warehouse.client.endpoint"
  }
}
~~~

không có nghĩa Spring Boot tự thực hiện:

~~~text
warehouse.client.base-url
        |
        v
warehouse.client.endpoint
~~~

trong Environment.

Nếu file người dùng chỉ có:

~~~yaml
warehouse:
  client:
    base-url: "https://legacy.example.invalid"
~~~

và Java record mới chỉ nhận `URI endpoint`, giá trị `endpoint` có thể bị thiếu. IDE có thể gợi ý sửa YAML, nhưng Binder không tự mang giá trị của base-url sang endpoint chỉ dựa trên metadata.

Cần **chọn một trong các chiến lược tương thích**:

1. Giữ cả field cũ và mới trong properties type rồi chọn giá trị hiệu lực trong code.
2. Dùng một migration mechanism rõ ràng do ứng dụng/thư viện cung cấp.
3. Chấp nhận breaking change, thông báo deprecation/removal và yêu cầu người dùng đổi key.
4. Khi hợp đồng phức tạp, thêm validation để phát hiện cấu hình cũ/không hợp lệ ở startup.

Không nên dựa vào metadata làm cơ chế migration runtime.

## 22. Chính sách ưu tiên khi cả key cũ và mới được khai báo

Một ứng dụng có thể gặp:

~~~yaml
warehouse:
  client:
    base-url: "https://legacy.example.invalid"
    endpoint: "https://new.example.invalid"
~~~

Hai key có tên khác nhau. **Thứ tự ưu tiên PropertySource không tự quyết định key nào được ưu tiên**, vì đây không phải một key được khai báo ở hai nguồn khác nhau.

Phải đặt ra một policy:

- Ưu tiên key mới nếu cả hai cùng tồn tại.
- Báo lỗi khi cả hai cùng xuất hiện để tránh mơ hồ.
- Cho phép key cũ như fallback trong một thời gian nhất định.
- Ghi thông báo migration một lần, không lộ secret.

Ví dụ code tường minh:

~~~java
public URI effectiveEndpoint() {
    if (endpoint != null) {
        return endpoint;
    }
    return baseUrl;
}
~~~

Nếu endpoint mới là required ở một phiên bản sau, remove fallback và cập nhật migration guide/metadata. Nếu muốn tránh trạng thái hai key cùng tồn tại, hãy viết validator cross-field.

Quan trọng là người đọc code có thể chỉ ra **chính xác giá trị nào có hiệu lực**.

## 23. Chiến lược migration có hai phiên bản

Một lộ trình phù hợp cho cấu hình của thư viện:

| Giai đoạn | Runtime | Metadata | Hướng dẫn người dùng |
| --- | --- | --- | --- |
| Phiên bản A | Chỉ dùng `base-url` | Key bình thường | Chưa có migration |
| Phiên bản B | Hỗ trợ `base-url` và `endpoint` | Đánh dấu `base-url` warning, replacement=endpoint | Khuyến nghị đổi sang endpoint |
| Phiên bản C | Ngừng hỗ trợ `base-url` | Đánh dấu removed/error khi thích hợp | Yêu cầu dùng endpoint |

Đây là ví dụ chính sách, không có nghĩa mọi project phải dùng đúng ba phiên bản.

Điều quan trọng trong phiên bản B:

- Không làm mất cấu hình đang chạy của người dùng.
- Có đủ thông tin để IDE hoặc tài liệu hướng dẫn chuyển đổi.
- Có chính sách rõ khi đồng thời khai báo cũ và mới.
- Có test bao phủ cả key cũ và key mới.
- Có thông báo deprecation đủ cụ thể, không chỉ “deprecated”.

Khi chuyển sang phiên bản C, phải kiểm tra cách ứng dụng phản ứng với key cũ. Spring Boot có thể bỏ qua unknown property tùy binding configuration; không phải cứ xóa field khỏi properties class là startup chắc chắn thất bại. Nếu cần từ chối key cũ, hãy thiết kế kiểm tra riêng.

## 24. Reason nên viết như thế nào?

Một `reason` tốt trả lời **vì sao** key bị deprecate và **điều gì thay đổi**.

Ví dụ chưa đủ:

~~~json
"reason": "Deprecated."
~~~

Ví dụ hữu ích hơn:

~~~json
"reason": "Renamed to client.endpoint to distinguish the full endpoint from the service root URL."
~~~

Hoặc:

~~~json
"reason": "This option is no longer used because retry behavior is controlled by client.retry-policy."
~~~

Quy ước nên áp dụng:

- Ngắn, rõ, diễn đạt nguyên nhân kỹ thuật hoặc ý nghĩa thay đổi.
- Không nói “key cũ vẫn hoạt động” nếu điều đó không đúng.
- Nêu khóa thay thế trong trường `replacement` khi có đường chuyển tương đương.
- Nếu không có replacement, nói thẳng rằng tính năng đã bị bỏ hoặc phải thay đổi cách cấu hình.
- Tránh đưa URL nội bộ, credential, token hoặc dữ liệu bí mật vào description/reason.

Gợi ý của IDE có thể hiển thị trực tiếp các chuỗi này nên chúng nên được viết dễ hiểu cho người sử dụng thư viện.

## 25. Metadata không tự tạo cảnh báo startup

Một câu dễ gây nhầm: “Đánh dấu deprecated thì Spring Boot sẽ cảnh báo trong log mỗi khi ai dùng key cũ.”

**Không thể mặc định điều đó.** Configuration metadata chủ yếu được các công cụ như IDE sử dụng; Spring Boot Binder không tự đọc `deprecation.replacement` để phát sinh migration log hoặc remap key.

Nếu muốn có cảnh báo runtime cho một key cũ, có thể làm chủ đích trong code, ví dụ một thành phần startup đọc nguồn cấu hình và phát hiện legacy key đang được khai báo. Nhưng cần cẩn thận:

- `Environment.containsProperty("warehouse.client.base-url")` chỉ cho biết Environment có thể phân giải key ấy; không tự chỉ ra nguồn hay mục đích.
- Không log giá trị bí mật của property.
- Không spam cảnh báo theo mỗi request.
- Đừng dùng cảnh báo runtime để thay thế tài liệu migration chính thức.
- Nếu runtime vẫn hỗ trợ cả hai key, test phải chứng minh ưu tiên và fallback đúng.

Không tự thêm một “runtime migration mechanism” chỉ để giải một bài toán gợi ý IDE, trừ khi có yêu cầu thật sự.

## 26. Hints cũng không tự bảo đảm YAML hợp lệ

Ví dụ:

~~~json
{
  "hints": [
    {
      "name": "warehouse.client.mode",
      "values": [
        { "value": "http" },
        { "value": "queue" }
      ]
    }
  ]
}
~~~

Những nội dung sau là hai việc khác:

1. **Autocomplete** có thể gợi ý `http`/`queue` khi viết YAML.
2. **Validation** quyết định `mode: "ftp"` có được dùng khi ứng dụng chạy không.

Nếu cần rule cứng, dùng enum:

~~~java
public enum Mode {
    HTTP,
    QUEUE
}
~~~

Hoặc validation:

~~~java
import jakarta.validation.constraints.Pattern;

@Pattern(regexp = "http|queue")
String mode
~~~

Cần có Bean Validation provider phù hợp và `@Validated`/registration trên root nếu dùng Bean Validation cho configuration properties.

Tương tự, `hints.values` không kiểm tra `URI` truy cập được, không kiểm tra timeout dương và không giới hạn số phần tử List.

## 27. Mô tả giá trị chỉ nên phản ánh hợp đồng thật

Nếu `mode=http` làm việc đồng bộ và `mode=queue` cần cấu hình message broker, hint description nên phản ánh điều đó:

~~~json
{
  "hints": [
    {
      "name": "warehouse.client.mode",
      "values": [
        {
          "value": "http",
          "description": "Send requests directly to the HTTP endpoint."
        },
        {
          "value": "queue",
          "description": "Publish messages; requires queue configuration."
        }
      ]
    }
  ]
}
~~~

Tuy nhiên, description không phải thay thế cho điều kiện bắt buộc ở runtime. Ví dụ khi mode queue, ứng dụng có thể cần `warehouse.client.queue-name`; cần validation có điều kiện để phát hiện thiếu giá trị khi tạo bean hoặc lúc startup.

Nếu nhiều khóa có quan hệ phụ thuộc, một tài liệu cấu hình hoàn chỉnh hoặc custom validator thường rõ hơn việc dồn tất cả logic vào vài câu description.

## 28. Gợi ý cho nested configuration và collection

Một object có thể có:

~~~yaml
warehouse:
  client:
    retries:
      attempts: 3
      backoff: 250ms
    modes:
      - "http"
      - "queue"
~~~

Metadata property names theo dạng flatten:

~~~text
warehouse.client.retries.attempts
warehouse.client.retries.backoff
warehouse.client.modes
~~~

Nếu muốn gợi ý các phần tử của collection, có thể cần cấu trúc hint theo quy ước metadata và khả năng hỗ trợ của IDE. Ví dụ Spring Boot metadata cho phép chỉ dẫn gợi ý value của collection bằng suffix `.values` trong các trường hợp phù hợp:

~~~json
{
  "hints": [
    {
      "name": "warehouse.client.modes.values",
      "values": [
        { "value": "http" },
        { "value": "queue" }
      ]
    }
  ]
}
~~~

Không nhầm tên gợi ý trong metadata với một property runtime tên `warehouse.client.modes.values`: suffix `.values` ở đây là **ngữ nghĩa dành cho công cụ để gợi ý element**; ứng dụng vẫn bind `warehouse.client.modes` vào List.

Với collection object phức tạp, ưu tiên mô tả cấu trúc typed configuration, default/validation và ví dụ YAML, thay vì cố mô tả toàn bộ schema bằng gợi ý giá trị tĩnh.

## 29. Thêm metadata cho property không được sinh tự động

Có trường hợp property được đọc thủ công qua `Environment#getProperty` hoặc một thư viện không có class `@ConfigurationProperties` tương ứng. Processor có thể không sinh metadata cho key ấy.

Ví dụ:

~~~java
String region =
    environment.getProperty("warehouse.client.region", "apac");
~~~

Nếu muốn IDE gợi ý key và values, có thể khai báo thủ công:

~~~json
{
  "properties": [
    {
      "name": "warehouse.client.region",
      "type": "java.lang.String",
      "description": "Deployment region for the warehouse integration.",
      "defaultValue": "apac"
    }
  ],
  "hints": [
    {
      "name": "warehouse.client.region",
      "values": [
        { "value": "apac" },
        { "value": "eu" },
        { "value": "us" }
      ]
    }
  ]
}
~~~

Đây là lý do `additional-spring-configuration-metadata.json` không chỉ dành cho deprecation: nó còn có thể bổ sung key mà processor không phân tích được.

Nhưng lưu ý: thêm mô tả metadata **không làm runtime tự đọc key mới**. Nếu code không có đường xử lý `warehouse.client.region`, IDE có thể gợi ý một property vô dụng. Hãy luôn giữ metadata đồng bộ với source và tài liệu triển khai.

## 30. Dự án multi-module: metadata phải đi cùng artifact thích hợp

Giả sử dự án:

~~~text
root/
  warehouse-client-config/
    src/main/java/.../WarehouseClientProperties.java
  warehouse-client-starter/
    src/main/java/.../WarehouseClientAutoConfiguration.java
  order-service/
    src/main/java/.../OrderApplication.java
~~~

Nếu `WarehouseClientProperties` nằm trong module `warehouse-client-config`, processor cần chạy ở module đó (hoặc quy trình đóng gói metadata có chủ đích). Không nên chỉ thêm processor vào `order-service` rồi kỳ vọng nó phân tích lại Java source đã đóng gói thành dependency JAR.

Quy trình tốt:

1. Module sở hữu properties class định nghĩa và sinh metadata.
2. Module thích hợp cung cấp additional metadata nếu cần gợi ý/deprecation.
3. Build đóng gói metadata vào artifact tiêu thụ được.
4. IDE của ứng dụng downstream có thể đọc metadata từ dependency.
5. Test CI kiểm tra artifact có tệp JSON và những entry quan trọng.

Với starter gồm nhiều JAR, có thể tồn tại metadata trong nhiều artifacts khác nhau trên classpath. Không nên tự gộp hoặc thay thế thủ công các file có cùng đường dẫn mà không kiểm soát packaging.

## 31. Cẩn thận với duplicate metadata entry

Một lỗi bảo trì thường gặp là processor đã sinh property:

~~~json
{
  "name": "warehouse.client.endpoint",
  "type": "java.net.URI"
}
~~~

và developer lại khai báo thủ công đầy đủ một entry cùng tên trong additional metadata nhưng type khác:

~~~json
{
  "name": "warehouse.client.endpoint",
  "type": "java.lang.String",
  "description": "Endpoint..."
}
~~~

Các trường thông tin bổ sung có thể được xử lý khi merge metadata, nhưng đừng tạo **hợp đồng trái ngược** giữa mã nguồn và tệp JSON. Nếu Java type là `URI`, metadata không nên nói `String` chỉ vì cấu hình YAML được viết bằng chuỗi.

Nên:

- Ưu tiên để processor sinh tên và type.
- Viết additional metadata cho hints, description/deprecation hoặc property không thể sinh tự động.
- Chỉ bổ sung những trường thực sự cần.
- Kiểm tra output JSON cuối cùng sau build.
- Có review khi đổi tên property hoặc kiểu Java để tránh deprecation stale.

Gợi ý tốt đến đâu cũng vô nghĩa nếu property không tồn tại trong runtime hoặc mô tả sai type.

## 32. Cách kiểm tra metadata sau build

Một quy trình thủ công:

**Maven:**

~~~bash
./mvnw clean compile
~~~

**Gradle:**

~~~bash
./gradlew clean classes
~~~

Sau đó xác định tệp metadata đầu ra của module đang build. Nếu có công cụ đọc JSON, kiểm tra:

- Có `properties` entry cho `warehouse.client.mode` không?
- Có `hints` cho đúng key đó không?
- Các values có `http` và `queue` không?
- Property cũ `warehouse.client.base-url` có `deprecation` không?
- `deprecation.replacement` có đúng `warehouse.client.endpoint` không?
- Level warning/error có phản ánh tình trạng hỗ trợ runtime thực tế không?
- Metadata đã được đóng gói vào JAR chưa?

Ví dụ với Python khi kiểm tra file đã sinh (nếu máy có Python):

~~~python
import json
from pathlib import Path

path = Path(
    "target/classes/META-INF/"
    "spring-configuration-metadata.json"
)
data = json.loads(path.read_text(encoding="utf-8"))

hints = {
    item["name"]: item
    for item in data.get("hints", [])
}
assert "warehouse.client.mode" in hints

properties = {
    item["name"]: item
    for item in data.get("properties", [])
}
assert (
    properties["warehouse.client.base-url"]
    ["deprecation"]["replacement"]
    == "warehouse.client.endpoint"
)
~~~

Đây là kiểm tra kỹ thuật của **metadata artifact**, không phải thay thế integration test của Binder. Nếu source build bằng Gradle hoặc file nằm trong module khác, chỉnh đường dẫn cho đúng.

Không nên dựa duy nhất vào việc IDE có hiển thị autocomplete hay không, vì trải nghiệm đó còn phụ thuộc IDE đã index JAR và plugin có hỗ trợ schema metadata hay chưa.

## 33. Unit test chỉ đọc object không chứng minh hints hoạt động

Ví dụ:

~~~java
@Test
void readsMode() {
    var props = new WarehouseClientProperties(
        "http",
        URI.create("https://warehouse.example.invalid"),
        Duration.ofSeconds(3)
    );
    assertEquals("http", props.mode());
}
~~~

Test này xác nhận record hoạt động như Java object, **không kiểm tra**:

- Annotation processor có chạy không.
- Additional metadata đã được merge chưa.
- Metadata có hints values không.
- IDE có thể đọc JSON không.
- Deprecation/replacement có xuất hiện trong artifact không.

Một bài test cho metadata có thể đọc `META-INF/spring-configuration-metadata.json` từ classpath rồi parse JSON để kiểm tra entry bắt buộc. Bài test cho runtime binding lại cần Spring Boot context/Binder.

Cần hai nhóm test khác nhau vì chúng kiểm tra **hai hợp đồng khác nhau**.

## 34. Kiểm thử runtime cho key cũ và key mới

Nếu bạn chủ động hỗ trợ legacy key, có thể dùng `ApplicationContextRunner` hoặc `@SpringBootTest(properties=...)` để xác minh.

Ví dụ logic với hai key:

~~~java
@ConfigurationProperties(prefix = "warehouse.client")
public class WarehouseClientProperties {

    private URI baseUrl;
    private URI endpoint;

    @Deprecated
    @DeprecatedConfigurationProperty(
        reason = "Use endpoint instead.",
        replacement = "warehouse.client.endpoint"
    )
    public URI getBaseUrl() {
        return baseUrl;
    }

    @Deprecated
    public void setBaseUrl(URI baseUrl) {
        this.baseUrl = baseUrl;
    }

    public URI getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(URI endpoint) {
        this.endpoint = endpoint;
    }

    public URI effectiveEndpoint() {
        return endpoint != null ? endpoint : baseUrl;
    }
}
~~~

Các tình huống test cần có:

| Input | Giá trị hiệu lực dự kiến nếu chọn key mới trước |
| --- | --- |
| Chỉ `base-url=old` | old |
| Chỉ `endpoint=new` | new |
| Cả hai cùng có | new |
| Không có key nào | Thiếu endpoint; cần policy/validation rõ |

Đừng để cả hai property được khai báo mà không có quy tắc ưu tiên rõ ràng. Nếu không hỗ trợ key cũ nữa, test nên xác nhận trạng thái removed và cách báo lỗi/migration mà ứng dụng đã chọn.

## 35. Khi nào nên dùng deprecation.level=error?

Một giai đoạn migration thường bắt đầu với warning rồi mới chuyển sang removed/error khi runtime đã ngừng hỗ trợ. Tuy nhiên:

- Không nên gắn `error` chỉ vì muốn người dùng đổi key nhanh hơn trong khi runtime còn hỗ trợ và policy chính thức chỉ là warning.
- Không dùng `error` thay thế một lỗi runtime thực sự.
- Nếu key cũ đã loại bỏ, thông báo reason và hướng dẫn nâng cấp phải rõ ràng.
- Nếu key mới có đơn vị/kiểu khác, replacement có thể cần hướng dẫn chuyển đổi dữ liệu thay vì chỉ đổi tên.

Ví dụ key cũ `client.timeout-ms=3000` và key mới `client.timeout=3s` có thể khác cách biểu diễn. Chỉ khai báo:

~~~json
"replacement": "client.timeout"
~~~

chưa đủ để bảo đảm người dùng đổi tên mà giữ nguyên giá trị `3000` sẽ đúng đơn vị. Description/reason và migration guide cần chỉ rõ đơn vị hoặc quy tắc conversion của phiên bản mới.

**Replacement là đường dẫn khuyến nghị, không phải lời đảm bảo hai property có semantics hoàn toàn tương đương.**

## 36. Không nên gợi ý secrets như những giá trị cụ thể

Ví dụ property:

~~~yaml
payment:
  api-token: "..."
~~~

Không tạo hints:

~~~json
{
  "name": "payment.api-token",
  "values": [
    { "value": "actual-production-token" }
  ]
}
~~~

Điều đó có thể làm lộ secret trong JAR, repository, IDE index hoặc log build.

Với secret, metadata có thể mô tả nguồn cung cấp (environment/secret manager) và kiểu String nếu cần, nhưng **không** đưa token/password thật vào values/defaultValue/description.

Tương tự, đừng đưa URL nội bộ chứa credential, thông tin khách hàng hoặc tham số bí mật vào deprecation.reason hay replacement.

Metadata là tài nguyên phát hành cùng artifact, cần được xem như nội dung có thể được nhiều công cụ đọc.

## 37. Những ngộ nhận thường gặp

### 37.1. “Có hints.values thì Spring chỉ cho phép các giá trị đó”

Sai. Hints là gợi ý IDE. Phải dùng enum/validation hoặc logic nghiệp vụ nếu cần giới hạn thật.

### 37.2. “Chỉ thêm spring-boot-configuration-processor là bean đã được đăng ký”

Sai. Processor sinh metadata lúc compile; bean registration vẫn cần `@EnableConfigurationProperties`, `@ConfigurationPropertiesScan` hoặc một cách đăng ký phù hợp.

### 37.3. “Thêm replacement sẽ tự đọc key cũ vào field mới”

Sai. Replacement chỉ là thông tin migration. Hỗ trợ alias/fallback cần code hoặc cơ chế migration runtime khác.

### 37.4. “DeprecatedConfigurationProperty tự làm startup fail”

Sai. Annotation chủ yếu phục vụ metadata; fail-fast phải đến từ logic/runtime constraints thực sự.

### 37.5. “Dùng @Deprecated trên mọi thứ là đủ”

Không hẳn. `@Deprecated` là Java annotation. Nếu muốn deprecation.reason và replacement rõ trong Spring Boot metadata, dùng `@DeprecatedConfigurationProperty` trên getter phù hợp hoặc additional metadata.

### 37.6. “Đánh dấu error nghĩa là Spring Runtime ném lỗi”

Sai. Error là mức trong metadata, không phải luật validation tự động.

### 37.7. “Đặt file additional metadata là xong”

Không chắc. Processor phải thấy tài nguyên bổ sung và kết hợp vào output; build phải đóng gói JSON. Hãy kiểm tra file `spring-configuration-metadata.json` cuối cùng.

### 37.8. “IDE không autocomplete tức là runtime không đọc được property”

Không chắc. IDE có thể chưa index, plugin không hỗ trợ provider hoặc metadata không được publish. Runtime Binder và IDE metadata là hai đường riêng.

### 37.9. “Properties type đã đổi nhưng JSON metadata cũ vẫn vô hại”

Metadata stale có thể gợi ý key sai, cảnh báo nhầm và làm người dùng cấu hình không có tác dụng. Khi đổi API config, cập nhật metadata và migration cùng lúc.

### 37.10. “Reason và description cứ ghi mọi thứ càng chi tiết càng tốt”

Không nên đưa bí mật hoặc nội dung nội bộ không cần thiết. Mô tả ngắn, đúng nghĩa, có hành động rõ là hữu ích hơn.

## 38. Checklist trước khi phát hành một khóa cấu hình mới

1. Key mới đã được Java code thực sự sử dụng chưa?
2. Prefix và kebab-case có nhất quán không?
3. Có typed `@ConfigurationProperties` hoặc đường tra cứu khác rõ ràng không?
4. Bean đã được đăng ký đúng chưa?
5. Annotation processor đã chạy trong module sở hữu class chưa?
6. Artifact có `META-INF/spring-configuration-metadata.json` chưa?
7. Property type/defaultValue/description trong metadata có khớp runtime không?
8. Nếu cần choices, `hints.values` có phản ánh lựa chọn thật không?
9. Nếu key là enum, có thực sự cần hints viết tay nữa không?
10. Nếu dùng hints.providers, IDE mục tiêu có hỗ trợ provider đó không?
11. Nếu property cũ bị deprecated, `reason` có giải thích đủ không?
12. `replacement` có chứa tên property đầy đủ và đúng ngữ nghĩa không?
13. Nếu runtime vẫn nhận key cũ, có test fallback/priority không?
14. Nếu key cũ bị loại bỏ, có migration guide và policy báo lỗi phù hợp không?
15. Có bỏ secret ra khỏi metadata JSON không?
16. CI có kiểm tra metadata artifact và binding runtime độc lập không?

## 39. Bài tập thực hành

**Bài toán:** cấu hình của một HTTP/queue client có `warehouse.client.transport` nhận `http` hoặc `queue`. Key cũ `warehouse.client.base-url` đã được thay bằng `warehouse.client.endpoint`. Muốn IDE gợi ý transport, cảnh báo key cũ và nêu replacement.

### Bước 1 — Định nghĩa Java type

~~~java
package example.warehouse;

import java.net.URI;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "warehouse.client")
public record WarehouseClientProperties(
        String transport,
        URI endpoint
) {}
~~~

Và đăng ký:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(WarehouseClientProperties.class)
class WarehouseClientConfiguration {}
~~~

### Bước 2 — Bật configuration processor

Gradle:

~~~groovy
dependencies {
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
~~~

Hoặc cấu hình Maven compiler/processor phù hợp.

### Bước 3 — Thêm additional metadata

Tạo `src/main/resources/META-INF/additional-spring-configuration-metadata.json`:

~~~json
{
  "hints": [
    {
      "name": "warehouse.client.transport",
      "values": [
        {
          "value": "http",
          "description": "Direct HTTP transport."
        },
        {
          "value": "queue",
          "description": "Queue-based transport."
        }
      ]
    }
  ],
  "properties": [
    {
      "name": "warehouse.client.base-url",
      "type": "java.net.URI",
      "description": "Legacy property name.",
      "deprecation": {
        "level": "warning",
        "reason": "Use endpoint instead of base-url.",
        "replacement": "warehouse.client.endpoint"
      }
    }
  ]
}
~~~

### Bước 4 — Quyết định runtime compatibility

Nếu Java record chỉ có `endpoint`, thì **khóa cũ chưa được hỗ trợ tự động**. Bạn phải chọn:

- Nâng hợp đồng thành breaking change, sửa metadata level/reason cho đúng; hoặc
- Giữ logic legacy binding/fallback trong một cấu trúc tương thích.

Đừng tuyên bố migration hoàn thành chỉ vì JSON metadata đã có replacement.

### Bước 5 — Clean build và kiểm tra

~~~bash
./gradlew clean classes
~~~

Hoặc:

~~~bash
./mvnw clean compile
~~~

Kiểm tra JSON đầu ra và JAR của module. Xác nhận hints và deprecation hiển thị đúng. Sau đó thử runtime binding riêng với cấu hình key mới, key cũ và cả hai.

### Bước 6 — Dự đoán các kết quả

| Tình huống | Điều mong đợi |
| --- | --- |
| IDE hỗ trợ metadata, người dùng gõ transport | Có thể gợi ý http/queue |
| Người dùng nhập transport=unknown | Metadata không tự từ chối |
| IDE gặp key base-url | Có thể hiển thị cảnh báo và replacement |
| Runtime chỉ có record endpoint, YAML chỉ có base-url | Không tự bind vào endpoint |
| Runtime có cả old/new fallback code | Hành vi do code quyết định |
| Metadata đánh dấu deprecation error | Không đồng nghĩa startup exception |
| Không có JSON trong JAR | IDE downstream có thể không có hints |

## 40. Tổng kết

Spring Boot configuration metadata có ba năng lực rất hữu ích để phát triển một API cấu hình bền vững:

1. **Gợi ý giá trị** với `hints.values` và, khi thích hợp, `hints.providers`, giúp người viết YAML/properties khám phá các lựa chọn.
2. **Đánh dấu khóa ngừng khuyến nghị** bằng deprecation metadata hoặc `@DeprecatedConfigurationProperty` trên getter của JavaBean-style properties type.
3. **Chỉ ra khóa thay thế** bằng `deprecation.replacement`, kèm `reason` giải thích lộ trình chuyển đổi.

Metadata thường được sinh bởi `spring-boot-configuration-processor` và bổ sung qua `META-INF/additional-spring-configuration-metadata.json`. Sau build, kiểm tra tệp `META-INF/spring-configuration-metadata.json` trong artifact để bảo đảm người tiêu thụ nhận được hướng dẫn đúng.

**Điều cần nhớ nhất:** metadata là **thông tin dành cho IDE/công cụ**, không phải bộ máy migration hay validation runtime. Nếu muốn cấm giá trị sai, hãy dùng kiểu/validation; nếu muốn hỗ trợ key cũ, hãy viết đường bind/fallback tương thích; nếu muốn loại bỏ key cũ, hãy công bố breaking change và kiểm tra hành vi runtime rõ ràng.

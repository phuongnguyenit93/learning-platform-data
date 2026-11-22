# Bổ sung thông tin bằng additional-spring-configuration-metadata.json trong Spring Boot 3.3

## 1. Tổng quan

Spring Boot sử dụng **configuration metadata** để mô tả những property có thể khai báo trong `application.properties`, `application.yaml` và những nguồn cấu hình khác. Metadata giúp IDE hiển thị gợi ý tên key, kiểu dữ liệu, mô tả, giá trị đề xuất, giá trị mặc định và cảnh báo property đã deprecated.

Trong dự án có `@ConfigurationProperties`, phần lớn metadata có thể được **sinh tự động khi biên dịch** bằng `spring-boot-configuration-processor`. Tuy nhiên, processor không thể suy ra tất cả ý nghĩa nghiệp vụ chỉ từ tên field và kiểu Java. Có những property được đọc thủ công qua `Environment` hoặc `@Value`, những giá trị kiểu `String` chỉ cho phép một tập lựa chọn rõ ràng, hoặc những metadata cần ghi chú deprecated và lộ trình thay thế.

Để giải quyết các trường hợp này, Spring Boot 3.3 hỗ trợ một file nguồn tùy chọn:

```text
src/main/resources/META-INF/additional-spring-configuration-metadata.json
```

Khi được annotation processor đọc trong quá trình build, nội dung của file này được **hợp nhất** với metadata sinh tự động để tạo kết quả:

```text
META-INF/spring-configuration-metadata.json
```

**Đây là metadata phục vụ công cụ phát triển, không phải một file cấu hình runtime.** Tạo file bổ sung không tự đăng ký bean, không định nghĩa property trong `Environment`, không ép kiểu, không thêm validation, không thay thế `application.yaml` và không quyết định precedence giữa các nguồn cấu hình.

Bài này đi từ cách tổ chức file và JSON schema, đến các ví dụ thực tế: bổ sung mô tả cho property đã có, khai báo property không được processor phát hiện, gợi ý values/providers, gợi ý Map key và Map value, đánh dấu deprecated, kiểm tra build Maven/Gradle và xử lý các lỗi phổ biến.

## 2. Phân biệt ba file dễ nhầm

Trong một ứng dụng Spring Boot có thể thấy các file sau:

| File | Ai tạo hoặc chỉnh? | Vai trò |
| --- | --- | --- |
| `src/main/resources/application.properties` hoặc `application.yaml` | Người phát triển/vận hành | **Cung cấp giá trị cấu hình runtime** |
| `src/main/resources/META-INF/additional-spring-configuration-metadata.json` | Người phát triển | **Cung cấp metadata bổ sung ở build time** |
| `META-INF/spring-configuration-metadata.json` trong output build hoặc JAR | `spring-boot-configuration-processor` | **Metadata hợp nhất cho IDE và công cụ** |

Ví dụ một key cùng xuất hiện trong các tầng:

**Java model:**

```java
@ConfigurationProperties(prefix = "acme")
public class AcmeProperties {
    private String mode = "safe";

    public String getMode() {
        return mode;
    }

    public void setMode(String mode) {
        this.mode = mode;
    }
}
```

**Giá trị runtime:**

```properties
# application.properties
acme.mode=fast
```

**Thông tin hỗ trợ IDE:**

```json
{
  "hints": [
    {
      "name": "acme.mode",
      "values": [
        {"value": "safe", "description": "Prioritize safer behavior."},
        {"value": "fast", "description": "Prioritize throughput."}
      ]
    }
  ]
}
```

Metadata ở block JSON cho phép IDE *có thể* gợi ý `safe` và `fast`. Nó **không làm `acme.mode` tự chuyển sang `safe`** khi người vận hành không khai báo, không làm `fast` trở thành giá trị bắt buộc và không kiểm tra sự hợp lệ của một chuỗi khác tại runtime. Giá trị mặc định runtime trong ví dụ đến từ field initializer `"safe"` của Java model, còn giá trị thực `"fast"` đến từ Config Data.

## 3. Mối quan hệ với spring-boot-configuration-processor

Spring Boot annotation processor đọc các kiểu được đánh dấu `@ConfigurationProperties` và sinh file metadata chuẩn. Thông tin có thể được suy ra tự động gồm:

- Prefix và những property được khai báo ở class cấu hình.
- Tên canonical của property.
- Java type và những nested properties mà processor nhận diện được.
- Một số default values và mô tả từ source.
- Thông tin deprecated có thể suy ra từ API phù hợp.
- Các nhóm metadata cho namespace cấu hình.

Nhưng các khả năng suy ra tự động vẫn có giới hạn:

1. Một `String mode` không tự tiết lộ rằng nghiệp vụ mong `safe` và `fast`.
2. Một property được truy cập trực tiếp bằng `Environment#getProperty("acme.legacy-token")` có thể không được phát hiện, vì không nằm trong bean `@ConfigurationProperties`.
3. Một default được tính động không nhất thiết suy ra được chính xác tại compile time.
4. Một field có thể cần mô tả rõ đơn vị, giới hạn hoặc rủi ro mà code type không nói lên.
5. Một alias tương thích ngược cần metadata deprecation/replacement, dù runtime vẫn tự xử lý bằng code khác.

File `additional-spring-configuration-metadata.json` giúp **bù đắp** những trường hợp trên mà không phải chỉnh sửa file metadata được sinh tự động.

### 3.1. File bổ sung có bắt buộc không?

Không. Nếu metadata từ processor đã đủ cho IDE, không cần tạo file bổ sung. Nếu dự án không cấu hình annotation processor, chỉ đặt một file có tên `additional-...json` vào resources **chưa đủ để bảo đảm kết quả merged metadata được tạo**; cần kiểm tra build pipeline đã thực sự chạy processor và nạp file bổ sung.

### 3.2. Không sửa trực tiếp file sinh ra

Ví dụ output Maven:

```text
target/classes/META-INF/spring-configuration-metadata.json
```

Ví dụ output Gradle:

```text
build/classes/java/main/META-INF/spring-configuration-metadata.json
```

Các file output có thể bị ghi đè mỗi lần compile/clean. Không chỉnh trực tiếp để thêm mô tả: thay đổi sẽ không tồn tại bền vững. Đặt dữ liệu thủ công trong file `additional-spring-configuration-metadata.json` thuộc mã nguồn, commit cùng dự án, rồi build lại.

## 4. Vị trí file và cấu trúc thư mục

Một dự án Java thông thường:

```text
my-app/
├── pom.xml                       # hoặc build.gradle
└── src/
    └── main/
        ├── java/
        │   └── com/example/demo/config/
        │       └── AcmeProperties.java
        └── resources/
            ├── application.yaml
            └── META-INF/
                └── additional-spring-configuration-metadata.json
```

Tên chính xác cần lưu ý:

```text
META-INF/additional-spring-configuration-metadata.json
```

Không đặt nhầm thành:

```text
META-INF/spring-configuration-metadata-additional.json
META-INF/additional-spring-configuration-metadata.yaml
META-INF/additional-configuration-metadata.json
additional-spring-configuration-metadata.json     (ở root resources)
```

Các tên sai không được processor nhận theo hợp đồng dành cho file bổ sung.

**Nguyên tắc đường dẫn:** `src/main/resources` là phần gốc resources; đường dẫn mà processor cần tìm là `META-INF/additional-spring-configuration-metadata.json`. Với project cấu trúc khác, phải bảo đảm nó có mặt tại đường dẫn resource tương ứng trong quá trình compile.

## 5. JSON metadata: groups, properties và hints

File bổ sung dùng cùng định dạng JSON như metadata chuẩn, với ba mảng:

```json
{
  "groups": [],
  "properties": [],
  "hints": []
}
```

Không phải lúc nào cũng cần khai báo đủ ba mảng. Chỉ có hints cũng hợp lệ:

```json
{
  "hints": [
    {
      "name": "acme.mode",
      "values": [
        {"value": "safe"},
        {"value": "fast"}
      ]
    }
  ]
}
```

Vai trò:

| Mảng | Đối tượng | Khi nên dùng |
| --- | --- | --- |
| `groups` | Nhóm namespace chứa các property | Muốn mô tả thêm một nhóm thủ công hoặc một namespace không phát hiện tự động |
| `properties` | Property với tên, kiểu, mô tả, default, deprecation | Bổ sung khóa ngoài `@ConfigurationProperties` hoặc cải thiện mô tả property đã được processor sinh |
| `hints` | Những giá trị đề xuất và provider hỗ trợ IDE | Muốn gợi ý value, Map key/value, bean name, profile name, class, Resource... |

Một JSON có thể chỉ chứa `properties`; cũng có thể chứa `properties` và `hints` cùng lúc. Đây là **một document JSON chuẩn**, không phải JSON Lines, không có dấu comment `//` hoặc `#`, không có dấu phẩy thừa ở cuối mảng/object.

### 5.1. Mẫu tổng hợp

```json
{
  "groups": [
    {
      "name": "acme.feature",
      "type": "com.example.demo.config.FeatureProperties",
      "description": "Settings for the Acme feature."
    }
  ],
  "properties": [
    {
      "name": "acme.feature.mode",
      "type": "java.lang.String",
      "description": "Execution mode for the feature.",
      "defaultValue": "safe"
    },
    {
      "name": "acme.feature.max-retries",
      "type": "java.lang.Integer",
      "description": "Maximum number of retries.",
      "defaultValue": 3
    }
  ],
  "hints": [
    {
      "name": "acme.feature.mode",
      "values": [
        {"value": "safe", "description": "Prefer safety."},
        {"value": "fast", "description": "Prefer speed."}
      ]
    }
  ]
}
```

Các tên như `com.example.demo.config.FeatureProperties` là **class minh họa**; hãy thay bằng class thật nếu có. Có thể bỏ `groups` và `type` không cần thiết khi đã có nhóm/phần tử được sinh tự động. Mẫu này giải thích schema, không có nghĩa mọi dự án cần tạo group thủ công.

## 6. Thuộc tính trong phần properties

Mỗi phần tử của mảng `properties` phải chỉ định `name`; một số thuộc tính khác giúp công cụ mô tả key chính xác hơn.

| JSON field | Kiểu thường dùng | Ý nghĩa |
| --- | --- | --- |
| `name` | String | Tên đầy đủ, ví dụ `acme.http.connect-timeout`; **bắt buộc** |
| `type` | String | Tên Java type (thường là tên đầy đủ), ví dụ `java.lang.String` hoặc `java.time.Duration` |
| `description` | String | Thuyết minh chức năng, đơn vị và lưu ý về property |
| `sourceType` | String | Fully qualified class name đóng góp khai báo nếu biết |
| `defaultValue` | JSON primitive, String hoặc dạng tương thích | Giá trị mặc định được **mô tả** cho tooling |
| `deprecation` | Object | Thông tin property đã deprecated, lý do và khóa thay thế |

Ví dụ:

```json
{
  "properties": [
    {
      "name": "acme.http.connect-timeout",
      "type": "java.time.Duration",
      "description": "Connection timeout. Configure an explicit unit, such as 500ms or 5s.",
      "defaultValue": "3s",
      "sourceType": "com.example.demo.config.AcmeHttpProperties"
    }
  ]
}
```

**Tên property phải viết thống nhất**, ưu tiên lowercase kebab-case với dấu chấm phân cấp. `acme.http.connect-timeout` và `acme.http.connectTimeout` là các cách biểu diễn có thể cùng bind về Java `connectTimeout`, nhưng metadata nên dùng tên canonical.

### 6.1. defaultValue không phải runtime default

`"defaultValue": "3s"` chỉ **mô tả** default cho IDE. Nếu code không khởi tạo `connectTimeout` và file cấu hình cũng không khai báo giá trị, ghi metadata trên **không khiến Binder tạo Duration 3 giây**.

Runtime default phải tồn tại ở nơi thực thi, ví dụ:

```java
private Duration connectTimeout = Duration.ofSeconds(3);
```

hoặc:

```java
public record AcmeHttpProperties(
    @DefaultValue("3s") Duration connectTimeout) {
}
```

với constructor binding phù hợp; hay bằng nguồn `application.properties` có giá trị tương ứng. Nếu metadata nói 3s nhưng code thực tế dùng 5s, IDE sẽ đưa thông tin sai. Hãy giữ metadata đồng bộ với cơ chế default runtime.

### 6.2. description nên mô tả hành vi, không lặp tên key

Mô tả yếu:

```json
{
  "name": "acme.http.connect-timeout",
  "description": "Connect timeout."
}
```

Mô tả có ích:

```json
{
  "name": "acme.http.connect-timeout",
  "description": "Maximum time to establish a connection. Use an explicit Duration unit such as 500ms or 3s."
}
```

Nếu có giá trị 0 hoặc âm mang ý nghĩa đặc biệt, cần nói rõ. Nếu property chứa thông tin nhạy cảm, phần metadata chỉ ghi **mô tả**, không ghi secret thật trong `defaultValue` hoặc `description`.

### 6.3. type đầy đủ và generic type

Một property có thể dùng kiểu Java thông thường:

```json
{
  "name": "acme.targets",
  "type": "java.util.List<java.lang.String>",
  "description": "Target identifiers."
}
```

Hoặc:

```json
{
  "name": "acme.retry-limits",
  "type": "java.util.Map<java.lang.String,java.lang.Integer>",
  "description": "Per-client retry limits."
}
```

Nếu processor đã suy ra type chính xác từ `@ConfigurationProperties`, thường **không cần** lặp lại type trong additional metadata chỉ để bổ sung description/hints. Tài liệu Spring Boot 3.3 mô tả cụ thể việc metadata thủ công có thể ghi đè `description`, `defaultValue` và `deprecation` của item đã sinh.

## 7. Ghi đè thông tin của một property đã được sinh tự động

Giả sử `spring-boot-configuration-processor` đọc class:

```java
package com.example.demo.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme")
public class AcmeProperties {

    private String mode = "safe";

    public String getMode() {
        return mode;
    }

    public void setMode(String mode) {
        this.mode = mode;
    }
}
```

Dự án bật `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties(AcmeProperties.class)` để runtime thực sự bind bean. Processor có thể phát hiện `acme.mode`, nhưng chưa có mô tả nghiệp vụ đầy đủ.

Trong `additional-spring-configuration-metadata.json`:

```json
{
  "properties": [
    {
      "name": "acme.mode",
      "description": "Controls how the Acme feature executes. The safe mode prioritizes predictable behavior.",
      "defaultValue": "safe"
    }
  ],
  "hints": [
    {
      "name": "acme.mode",
      "values": [
        {"value": "safe", "description": "Prefer predictable behavior."},
        {"value": "fast", "description": "Prefer throughput."}
      ]
    }
  ]
}
```

Khi processor hợp nhất thành công, metadata tạo ra cho key `acme.mode` chứa phần mô tả/default được cung cấp thủ công cùng với những thông tin khác được sinh từ class, chẳng hạn type.

**Quy tắc merge được Spring Boot 3.3 nêu rõ:** đối với property đã được tự động phát hiện **trong module hiện tại**, các trường `description`, `defaultValue` và `deprecation` được metadata bổ sung **ghi đè nếu chúng được chỉ định**. Nếu một manual property không trùng item do processor tìm thấy trong module, nó sẽ được thêm như một property mới.

Không suy rộng rằng mọi trường về `type`, `sourceType`, name hay group đều có thể bị ghi đè theo cùng quy tắc. Với property đã phát hiện, ưu tiên để processor xác định type/source và dùng additional file cho mô tả, giá trị mặc định, deprecated và hints.

### Nếu chỉ muốn thêm gợi ý giá trị

Không cần khai báo lại property:

```json
{
  "hints": [
    {
      "name": "acme.mode",
      "values": [
        {"value": "safe"},
        {"value": "fast"}
      ]
    }
  ]
}
```

Đây là trường hợp rất phù hợp với additional metadata: model Java vẫn là `String`, nhưng IDE có danh sách gợi ý giúp tránh gõ sai.

## 8. Khai báo property không được phát hiện qua @ConfigurationProperties

Một số ứng dụng đọc một key thủ công:

```java
package com.example.demo.service;

import org.springframework.core.env.Environment;
import org.springframework.stereotype.Service;

@Service
public class RuntimeOptions {

    private final Environment environment;

    public RuntimeOptions(Environment environment) {
        this.environment = environment;
    }

    public String getFeatureTokenMode() {
        return environment.getProperty(
                "acme.feature-token-mode", "standard");
    }
}
```

Ở đây property `acme.feature-token-mode` không nhất thiết thuộc một bean `@ConfigurationProperties`, nên annotation processor có thể không tạo metadata cho key này.

Bổ sung:

```json
{
  "properties": [
    {
      "name": "acme.feature-token-mode",
      "type": "java.lang.String",
      "description": "Selects how feature tokens are interpreted.",
      "defaultValue": "standard"
    }
  ],
  "hints": [
    {
      "name": "acme.feature-token-mode",
      "values": [
        {"value": "standard"},
        {"value": "strict"}
      ]
    }
  ]
}
```

Sau build thành công, metadata gộp có thể chứa key mới và IDE có thể gợi ý khi chỉnh:

```properties
acme.feature-token-mode=strict
```

Nhưng lưu ý: **metadata không khiến `RuntimeOptions` tự có method khác hoặc tự validate giá trị `strict`**. Code runtime vẫn quyết định phương pháp đọc, default, parse và kiểm tra tập giá trị. Nếu code chấp nhận mọi chuỗi, hints cũng không tự giới hạn những chuỗi đó.

### Một property không có bean vẫn cần tồn tại trong code

Nếu thêm:

```json
{
  "properties": [
    {
      "name": "acme.feature-enabled",
      "type": "java.lang.Boolean",
      "description": "Enables the Acme feature.",
      "defaultValue": false
    }
  ]
}
```

mà **không có code hoặc framework nào đọc `acme.feature-enabled`**, ứng dụng không tự thay đổi hành vi chỉ vì key xuất hiện trong metadata. Đừng dùng additional file để “khai báo cấu hình runtime” theo nghĩa của một bean configuration mới.

Nếu tập key thủ công ngày càng nhiều, nên cân nhắc chuyển sang class `@ConfigurationProperties` để có binding type-safe, validation, metadata tự động và quản lý prefix rõ ràng.

## 9. Hints: gợi ý giá trị cho IDE

Phần `hints` cung cấp thêm dữ liệu hỗ trợ biên tập configuration files. Một hint thường có:

- `name`: tên property mà hint áp dụng.
- `values`: các giá trị được đề xuất, mỗi phần tử có `value` và có thể có `description`.
- `providers`: các nguồn gợi ý thông minh, chẳng hạn enum, class, bean name, logger name hoặc profile name.

Ví dụ:

```json
{
  "hints": [
    {
      "name": "acme.storage-mode",
      "values": [
        {
          "value": "memory",
          "description": "Keep data in memory for a lightweight setup."
        },
        {
          "value": "disk",
          "description": "Persist data on local storage."
        },
        {
          "value": "remote",
          "description": "Use an external storage service."
        }
      ]
    }
  ]
}
```

IDE hỗ trợ metadata có thể dùng `values` để auto-complete hoặc hiển thị mô tả khi người dùng gõ:

```properties
acme.storage-mode=
```

### 9.1. Danh sách hint không mặc nhiên là validation

Nếu Java target là:

```java
private String storageMode;
```

thì metadata hints không tự biến nó thành enum hoặc từ chối giá trị `"unknown"` ở runtime. Để giới hạn runtime, có thể:

- Dùng một enum Java có các giá trị được phép.
- Thực hiện kiểm tra riêng trong service/constructor.
- Thêm Bean Validation hoặc custom converter/validator phù hợp.

Metadata chỉ là **thông tin cho công cụ**, còn validation là **quy tắc thực thi**.

### 9.2. Giá trị hint có kiểu JSON

Với property kiểu boolean:

```json
{
  "hints": [
    {
      "name": "acme.verbose",
      "values": [
        {"value": true, "description": "Enable verbose output."},
        {"value": false, "description": "Disable verbose output."}
      ]
    }
  ]
}
```

Với property số:

```json
{
  "hints": [
    {
      "name": "acme.batch-size",
      "values": [
        {"value": 16},
        {"value": 32},
        {"value": 64}
      ]
    }
  ]
}
```

Dùng đúng JSON type khi hợp lý thay vì luôn ép số/boolean thành chuỗi. Dẫu vậy, các hint này không phải nguồn authoritative cho ràng buộc miền giá trị runtime.

## 10. Gợi ý key và value của Map

Một property kiểu Map có thể chứa những key động và value động:

```java
@ConfigurationProperties(prefix = "acme")
public class AcmeProperties {

    private Map<String, String> channels = new LinkedHashMap<>();

    public Map<String, String> getChannels() {
        return channels;
    }

    public void setChannels(Map<String, String> channels) {
        this.channels = channels;
    }
}
```

Cấu hình:

```properties
acme.channels.billing=primary
acme.channels.inventory=secondary
```

Với Map, Spring Boot metadata cho phép gợi ý **key và value riêng biệt** qua hậu tố:

- `acme.channels.keys`: gợi ý tên Map key.
- `acme.channels.values`: gợi ý value của các entry.
- **Không dùng hint `acme.channels` để mong nó trực tiếp gợi ý cả Map theo cách đặc biệt.**

Ví dụ:

```json
{
  "hints": [
    {
      "name": "acme.channels.keys",
      "values": [
        {
          "value": "billing",
          "description": "Billing workflow."
        },
        {
          "value": "inventory",
          "description": "Inventory workflow."
        }
      ]
    },
    {
      "name": "acme.channels.values",
      "values": [
        {
          "value": "primary",
          "description": "Primary processing channel."
        },
        {
          "value": "secondary",
          "description": "Secondary processing channel."
        }
      ]
    }
  ]
}
```

Khi biên tập:

```properties
acme.channels.billing=primary
```

IDE có thể đề xuất key `billing` hoặc `inventory` và value `primary`/`secondary`. Tính năng thực tế phụ thuộc mức hỗ trợ của IDE.

**Hậu tố `.keys`, `.values` trong metadata là giao thức hint cho Map**, không phải hai property runtime phải khai báo trong `application.properties`. Không đặt:

```properties
acme.channels.keys=billing
```

rồi cho rằng Spring Boot tự hiểu đây là danh sách key cần tạo.

## 11. Value providers: gợi ý thông minh theo ngữ cảnh

Ngoài `values` cố định, metadata có thể sử dụng `providers`. Provider khai báo cách IDE tìm gợi ý dựa trên classpath, bean, profile hoặc kiểu dữ liệu.

Các provider phổ biến trong tài liệu Spring Boot 3.3:

| Provider | Chức năng | Tình huống |
| --- | --- | --- |
| `any` | Cho phép chọn giá trị khác ngoài danh sách đã gợi ý | Value hints chỉ là đề xuất |
| `class-reference` | Gợi ý class từ project/classpath | Config chứa tên class |
| `handle-as` | Xử lý như một kiểu dữ liệu khác để IDE hỗ trợ | String mang ý nghĩa Resource/Charset/Locale/enum |
| `logger-name` | Gợi ý tên logger/group | Map key của mức log |
| `spring-bean-reference` | Gợi ý tên Spring bean | String chứa bean name |
| `spring-profile-name` | Gợi ý profile names | Property dùng tên profile |

Một provider có thể có object `parameters`, tùy loại provider. IDE không bắt buộc hỗ trợ mọi provider, nên không nên xem việc không có dropdown là lỗi runtime.

### 11.1. Provider any

```json
{
  "hints": [
    {
      "name": "acme.storage-mode",
      "values": [
        {"value": "memory"},
        {"value": "disk"}
      ],
      "providers": [
        {
          "name": "any"
        }
      ]
    }
  ]
}
```

Ý nghĩa: IDE có thể gợi ý `memory` và `disk` nhưng vẫn cho phép những value khác ở mức metadata. Provider `any` không phải một cách làm Java Binder “chấp nhận tất cả giá trị bất kể target type”: runtime conversion/validation vẫn giữ nguyên.

### 11.2. Provider class-reference

Khi property lưu tên class:

```json
{
  "hints": [
    {
      "name": "acme.plugin-class",
      "providers": [
        {
          "name": "class-reference",
          "parameters": {
            "target": "com.example.demo.spi.Plugin"
          }
        }
      ]
    }
  ]
}
```

IDE có thể gợi ý những class phù hợp với base type `com.example.demo.spi.Plugin` trong classpath. `Plugin` là interface minh họa do dự án định nghĩa. Tham số `target` giúp lọc kết quả; provider còn hỗ trợ `concrete` khi cần quyết định có chỉ gợi ý class cụ thể hay không.

### 11.3. Provider handle-as

Khi property Java là `String` nhưng nội dung đại diện một Resource path:

```json
{
  "hints": [
    {
      "name": "acme.template-location",
      "providers": [
        {
          "name": "handle-as",
          "parameters": {
            "target": "org.springframework.core.io.Resource"
          }
        }
      ]
    }
  ]
}
```

IDE có thể cung cấp gợi ý phù hợp với ý nghĩa Resource như `classpath:/templates/main.txt`. Nhưng Java target vẫn là `String`; metadata không biến nó thành một đối tượng `Resource` hoặc mở file tự động ở runtime.

Provider `handle-as` cũng có thể dùng với những kiểu có semantics như Charset, Locale, MimeType hoặc enum khi phù hợp với target.

### 11.4. Provider logger-name

```json
{
  "hints": [
    {
      "name": "acme.logging.levels.keys",
      "providers": [
        {
          "name": "logger-name"
        }
      ]
    }
  ]
}
```

Ví dụ áp dụng khi `acme.logging.levels` là một Map với key là tên logger. Provider có thể hỗ trợ tìm class/package/logger group. Hãy viết đúng suffix `.keys` khi muốn gợi ý **Map key**.

### 11.5. Provider spring-bean-reference

```json
{
  "hints": [
    {
      "name": "acme.handler-bean",
      "providers": [
        {
          "name": "spring-bean-reference",
          "parameters": {
            "target": "com.example.demo.spi.Handler"
          }
        }
      ]
    }
  ]
}
```

IDE có thể gợi ý tên bean kiểu Handler. **Binder không tự biến chuỗi `"myHandler"` thành đối tượng bean** chỉ vì có provider metadata; nếu runtime cần tham chiếu bean, code ứng dụng phải giải quyết tên bean qua `ApplicationContext` hoặc cách injection thích hợp.

### 11.6. Provider spring-profile-name

```json
{
  "hints": [
    {
      "name": "acme.target-profile",
      "providers": [
        {
          "name": "spring-profile-name"
        }
      ]
    }
  ]
}
```

IDE hỗ trợ provider này có thể gợi ý tên những profile tồn tại trong project. Runtime của property `acme.target-profile` vẫn phụ thuộc code ứng dụng; metadata không kích hoạt profile tương ứng.

### 11.7. Thứ tự providers

Có thể khai báo nhiều provider cho cùng một hint. IDE sẽ sử dụng provider đầu tiên **mà nó hỗ trợ** trong danh sách được khai báo. Đặt provider giàu ngữ nghĩa nhất lên trước, provider dự phòng phía sau khi phù hợp.

```json
{
  "hints": [
    {
      "name": "acme.handler-bean",
      "providers": [
        {"name": "spring-bean-reference"},
        {"name": "any"}
      ]
    }
  ]
}
```

Không kỳ vọng mọi IDE triển khai logic provider hoặc hiển thị giao diện giống nhau.

## 12. Deprecation metadata: thông báo khóa cũ và hướng thay thế

Khi đổi tên một property công khai, bạn có thể muốn giữ alias cũ trong một giai đoạn chuyển tiếp nhưng cảnh báo người chỉnh cấu hình.

Ví dụ:

- Property cũ: `acme.old-timeout`.
- Property mới: `acme.client.connect-timeout`.

Metadata bổ sung có thể chứa:

```json
{
  "properties": [
    {
      "name": "acme.old-timeout",
      "type": "java.time.Duration",
      "description": "Legacy connection timeout setting.",
      "deprecation": {
        "reason": "Use the client-specific timeout property.",
        "replacement": "acme.client.connect-timeout"
      }
    }
  ]
}
```

Các IDE hỗ trợ metadata có thể đánh dấu `acme.old-timeout` là deprecated và gợi ý `acme.client.connect-timeout`.

**Giới hạn rất quan trọng:** deprecation metadata không tự loại bỏ key cũ, không tự chuyển giá trị từ key cũ sang key mới, không buộc ứng dụng ưu tiên key mới và không thực hiện migration. Logic runtime tương thích ngược (nếu cần) phải được cài đặt riêng.

Ví dụ, nếu runtime tiếp tục chấp nhận key cũ, code cần tự xác định:

- Nếu key mới và cũ cùng xuất hiện thì key nào thắng?
- Nếu key cũ vắng mặt thì có fallback không?
- Có log cảnh báo khi người vận hành đang dùng key cũ không?
- Khi nào alias cũ bị loại bỏ hẳn?

### 12.1. Các thông tin trong deprecation

Những trường thường dùng:

```json
{
  "deprecation": {
    "reason": "The old setting is no longer recommended.",
    "replacement": "acme.client.connect-timeout"
  }
}
```

Spring Boot 3.3 metadata cũng mô tả mức deprecation (như `warning`/`error`) ở nơi hỗ trợ; cần chọn theo hợp đồng phiên bản cụ thể và chính sách phát hành. Không dùng mức cảnh báo của IDE để thay cho một cơ chế fail-fast runtime.

### 12.2. Không đánh dấu deprecated khi property mới chưa được hỗ trợ

Nếu thay thế chưa được implement runtime, metadata có thể dẫn người dùng chuyển sang một key không hoạt động. Hãy bảo đảm key thay thế tồn tại ở version phát hành tương ứng; nếu chưa, mô tả lộ trình chuyển đổi mà không đưa ra hướng dẫn gây lỗi.

## 13. Ví dụ thực tế end-to-end

Giả sử một microservice tên Acme Gateway cần:

- `acme.gateway.mode`: String, default `safe`, gợi ý `safe`/`fast`.
- `acme.gateway.connect-timeout`: Duration, default 3 giây.
- `acme.gateway.client-tags`: Map có key và value cần gợi ý.
- `acme.gateway.custom-handler`: String trỏ đến bean name.
- `acme.legacy-gateway-mode`: khóa cũ đang được bỏ dần.

### 13.1. JavaBean configuration

```java
package com.example.demo.config;

import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme.gateway")
public class GatewayProperties {

    private String mode = "safe";
    private Duration connectTimeout = Duration.ofSeconds(3);
    private Map<String, String> clientTags = new LinkedHashMap<>();
    private String customHandler;

    public String getMode() { return mode; }
    public void setMode(String mode) { this.mode = mode; }

    public Duration getConnectTimeout() { return connectTimeout; }
    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }

    public Map<String, String> getClientTags() {
        return clientTags;
    }

    public void setClientTags(Map<String, String> clientTags) {
        this.clientTags = clientTags;
    }

    public String getCustomHandler() { return customHandler; }
    public void setCustomHandler(String customHandler) {
        this.customHandler = customHandler;
    }
}
```

Đăng ký:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Chú ý `@ConfigurationPropertiesScan` hoạt động ở runtime để đăng ký bean; còn metadata processor hoạt động ở compile time. Hai cơ chế có liên quan nhưng không phải một.

### 13.2. Additional metadata file

Đặt nguyên JSON sau vào:

```text
src/main/resources/META-INF/additional-spring-configuration-metadata.json
```

Nội dung:

```json
{
  "properties": [
    {
      "name": "acme.gateway.mode",
      "description": "Gateway execution mode. Safe favors predictable behavior.",
      "defaultValue": "safe"
    },
    {
      "name": "acme.gateway.connect-timeout",
      "description": "Connection timeout. Specify a Duration unit such as 500ms or 3s.",
      "defaultValue": "3s"
    },
    {
      "name": "acme.legacy-gateway-mode",
      "type": "java.lang.String",
      "description": "Legacy gateway mode for older deployments.",
      "deprecation": {
        "reason": "The gateway settings are now grouped under acme.gateway.",
        "replacement": "acme.gateway.mode"
      }
    }
  ],
  "hints": [
    {
      "name": "acme.gateway.mode",
      "values": [
        {
          "value": "safe",
          "description": "Use the safe execution policy."
        },
        {
          "value": "fast",
          "description": "Prioritize throughput."
        }
      ]
    },
    {
      "name": "acme.gateway.client-tags.keys",
      "values": [
        {
          "value": "billing",
          "description": "Billing client tag."
        },
        {
          "value": "inventory",
          "description": "Inventory client tag."
        }
      ],
      "providers": [{"name": "any"}]
    },
    {
      "name": "acme.gateway.client-tags.values",
      "values": [
        {"value": "primary"},
        {"value": "secondary"}
      ],
      "providers": [{"name": "any"}]
    },
    {
      "name": "acme.gateway.custom-handler",
      "providers": [
        {
          "name": "spring-bean-reference",
          "parameters": {
            "target": "com.example.demo.spi.GatewayHandler"
          }
        }
      ]
    }
  ]
}
```

Với `@ConfigurationProperties` class trong ví dụ, processor có thể tự nhận dạng các key mới `acme.gateway.*`, và additional file bổ sung description/default/hints. `acme.legacy-gateway-mode` có thể được thêm vào metadata vì không được class hiện tại khai báo.

**Lưu ý cho người triển khai:** `com.example.demo.spi.GatewayHandler` là interface giả định, không phải thành phần có sẵn của Spring Boot. Đổi thành interface thực tế của dự án nếu dùng provider. Ngoài ra, muốn giữ hỗ trợ runtime cho `acme.legacy-gateway-mode`, cần có code đọc hoặc ánh xạ alias; metadata không làm việc đó.

### 13.3. Runtime Config Data

```properties
# src/main/resources/application.properties
acme.gateway.mode=fast
acme.gateway.connect-timeout=750ms
acme.gateway.client-tags.billing=primary
acme.gateway.client-tags.inventory=secondary
acme.gateway.custom-handler=defaultGatewayHandler
```

Cấu hình này được runtime đọc theo cách Spring Boot thông thường. Additional metadata có thể giúp IDE đề xuất key và value khi chỉnh file, nhưng **không làm thay đổi thứ tự ưu tiên** của Config Data, OS env hoặc CLI.

### 13.4. Kết quả mong đợi

Nếu processor chạy và merge thành công, output metadata chứa:

- Property `acme.gateway.mode` với description/default bổ sung.
- Property `acme.gateway.connect-timeout` với mô tả và default 3s.
- Property `acme.legacy-gateway-mode` với deprecation/replacement.
- Hints `acme.gateway.mode`, `acme.gateway.client-tags.keys`, `acme.gateway.client-tags.values` và `acme.gateway.custom-handler`.

Không cần kỳ vọng output JSON **giống byte-for-byte** file đầu vào: annotation processor có thể bổ sung những trường như type/sourceType, nhóm hoặc sắp xếp lại metadata; điều quan trọng là các item metadata cần thiết có mặt và không sai tên.

## 14. Cấu hình annotation processor với Maven

Nếu dự án dùng Maven và có quản lý version Spring Boot 3.3 (ví dụ Spring Boot parent POM hoặc BOM phù hợp), có thể khai báo:

```xml
<dependencies>
    <!-- Các dependencies Spring Boot khác... -->

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-configuration-processor</artifactId>
        <optional>true</optional>
    </dependency>
</dependencies>
```

`<optional>true</optional>` tránh truyền dependency processor như một dependency bắt buộc cho project phụ thuộc thư viện của bạn. Trong nhiều cấu hình Maven với Spring Boot build setup, annotation processor được phát hiện và chạy khi compile.

Nếu project tùy biến mạnh `maven-compiler-plugin`, có thể phải cấu hình **annotation processor path** rõ ràng để bảo đảm processor thực sự được chạy. Cách cấu hình cụ thể phụ thuộc JDK/Maven Compiler Plugin đang dùng; đừng chỉ dựa vào việc dependency xuất hiện trong pom.xml rồi kết luận metadata chắc chắn đã được sinh.

Ví dụ lệnh build:

```bash
./mvnw clean compile
```

Hoặc trên Windows:

```powershell
.\mvnw.cmd clean compile
```

Kiểm tra file sinh:

```text
target/classes/META-INF/spring-configuration-metadata.json
```

Nếu file additional đã đúng nhưng output không có hints/property mới, hãy kiểm tra processor có được kích hoạt hay không, vị trí resource ở compile time và cấu hình của plugin compiler.

### 14.1. Ví dụ annotationProcessorPaths khi cần

Với cấu hình Maven Compiler Plugin tùy chỉnh, một hướng là:

```xml
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
                        <version>${spring-boot.version}</version>
                    </path>
                </annotationProcessorPaths>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Trong ví dụ trên, project phải có property `spring-boot.version` hoặc version management tương ứng; không copy như một cấu hình độc lập nếu chưa xác định hệ thống version của dự án. Khi chỉ định annotation processors thủ công, cần bảo đảm các processors khác đang dùng (Lombok, MapStruct...) không vô tình bị bỏ khỏi danh sách processor path. Không đổi cấu hình build nếu workflow hiện tại đã tạo metadata đầy đủ.

## 15. Cấu hình với Gradle

Ví dụ build.gradle (Groovy DSL):

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
```

Phiên bản plugin ở đây chỉ là **minh họa cho dòng 3.3**, không phải yêu cầu phải dùng đúng bản patch này. Với dự án thực tế, đồng bộ plugin và dependency versions theo build quản lý chung.

Lệnh kiểm tra:

```bash
./gradlew clean compileJava
```

Hoặc trên Windows:

```powershell
.\gradlew.bat clean compileJava
```

Output thường nằm ở:

```text
build/classes/java/main/META-INF/spring-configuration-metadata.json
```

### Lưu ý về task order khi dùng additional file

Với một số cấu hình Gradle hoặc custom resource processing, cần bảo đảm file `META-INF/additional-spring-configuration-metadata.json` có mặt ở vị trí mà annotation processor có thể đọc **trong lúc `compileJava` chạy**. Nếu processor không nhận được file additional, output chỉ có metadata tự sinh.

Các task `processResources`, `compileJava` và cấu hình source sets có thể ảnh hưởng tới việc resource xuất hiện trên compilation path. Khi cần xử lý, kiểm tra thứ tự và input của các task trong project, rồi điều chỉnh dependency giữa các task sao cho có nguồn tài nguyên đầy đủ. **Không thêm một task dependency có thể gây vòng lặp một cách mù quáng**; dùng lệnh `--info` hoặc Gradle task graph để kiểm tra pipeline thực tế.

### Kotlin project

Với Kotlin, cách sinh configuration metadata có thể cần cơ chế annotation processing tương ứng như KAPT, tùy build setup và phiên bản Spring Boot. Ví dụ Java `annotationProcessor` không tự động bảo đảm processor chạy trên toàn bộ Kotlin source. Trong dự án Kotlin, cấu hình processor theo tài liệu Kotlin/Gradle phù hợp thay vì bê nguyên đoạn Java Gradle.

## 16. Kiểm tra metadata sau build

### 16.1. Xem file output

Sau khi Maven compile:

```text
target/classes/META-INF/spring-configuration-metadata.json
```

Sau khi Gradle compileJava:

```text
build/classes/java/main/META-INF/spring-configuration-metadata.json
```

Mở file và tìm tên key:

```text
acme.gateway.mode
acme.gateway.connect-timeout
acme.legacy-gateway-mode
acme.gateway.client-tags.keys
```

Các item có thể ở các mảng khác nhau. `hints` chứa `.keys`/`.values`; `properties` chứa định nghĩa property thực.

### 16.2. Xem bằng jq nếu công cụ có sẵn

Ví dụ kiểm tra property:

```bash
jq '.properties[] | select(.name == "acme.gateway.mode")' \
  target/classes/META-INF/spring-configuration-metadata.json
```

Kiểm tra hints:

```bash
jq '.hints[] | select(.name == "acme.gateway.mode")' \
  target/classes/META-INF/spring-configuration-metadata.json
```

Kiểm tra deprecated:

```bash
jq '.properties[] | select(.name == "acme.legacy-gateway-mode")' \
  target/classes/META-INF/spring-configuration-metadata.json
```

Nếu không cài `jq`, có thể mở bằng IDE hoặc dùng trình xử lý JSON khác. Đừng dựa duy nhất vào tìm chuỗi text vì một key có thể nằm ở `hints` nhưng không nằm ở `properties`, hoặc ở module khác.

### 16.3. Kiểm tra tính hợp lệ của JSON đầu vào

Đây là một file JSON, không phải YAML:

```json
{
  "properties": [
    {
      "name": "acme.mode",
      "description": "Execution mode."
    }
  ]
}
```

Các lỗi thường gây parse failure:

- Quên dấu nháy kép quanh key.
- Dùng comment `//` hoặc `#`.
- Có trailing comma sau item cuối.
- Escape dấu `\` sai trong String.
- Chứa hai root JSON objects rời nhau thay vì một object.
- Gõ sai `properties` thành `property` hoặc `hints` thành `hint`.
- Dùng giá trị `defaultValue` có kiểu JSON không phù hợp với điều muốn mô tả.

Một trình kiểm tra JSON chuẩn có thể phát hiện lỗi cú pháp. Bước tiếp theo vẫn cần kiểm tra output merged metadata vì **JSON hợp lệ chưa chắc đúng schema/tên key**.

### 16.4. Kiểm tra metadata trong JAR

Với JAR thông thường, `META-INF/spring-configuration-metadata.json` có thể nằm ở root JAR. Với Spring Boot executable JAR, file resources của ứng dụng có thể nằm dưới:

```text
BOOT-INF/classes/META-INF/spring-configuration-metadata.json
```

Với các thư viện phụ thuộc, metadata ở trong dependency JAR của chúng. Ví dụ liệt kê nội dung:

```bash
jar tf build/libs/my-app.jar | grep spring-configuration-metadata.json
```

Tùy artifact name và vị trí output, chỉnh path cho phù hợp. Một bản build thành công chưa tự chứng minh metadata đã được đóng gói ở đúng nơi tiêu thụ; kiểm tra artifact phát hành nếu dự án tạo thư viện để IDE của module khác sử dụng.

## 17. Vì sao IDE không thấy gợi ý dù JSON đã đúng?

Có nhiều nguyên nhân không liên quan trực tiếp tới syntax:

1. **Chưa chạy annotation processor:** không có `spring-configuration-metadata.json` được sinh.
2. **File additional sai vị trí:** processor không tìm thấy `META-INF/additional-spring-configuration-metadata.json`.
3. **File JSON không hợp lệ:** parse failure hoặc processor bỏ qua nội dung không đúng.
4. **Tên property sai canonical:** hint `acme.gateway.clientTags` không trùng property chuẩn `acme.gateway.client-tags`.
5. **Đang xem output cũ:** chưa clean compile hoặc IDE dùng cache/index cũ.
6. **Đang mở module khác:** IDE có thể phải có dependency tới module chứa metadata.
7. **IDE/plugin không hỗ trợ provider:** `spring-bean-reference` hoặc `handle-as` có thể được hỗ trợ khác nhau.
8. **Property không tồn tại runtime:** metadata có key nhưng Java code không đọc, nên không có tác động khi chạy.
9. **Metadata chỉ ở source, chưa merge:** file additional hiện diện nhưng output generated thiếu hint/property.
10. **Build system không copy/đóng gói metadata:** generated file tồn tại tạm thời nhưng artifact không chứa nó.

Quy trình tìm lỗi nên đi từ **file source → processor thực thi → file generated → packaged artifact → IDE index**, thay vì lập tức chỉnh lại JSON hay cập nhật Spring Boot version.

### 17.1. Phân biệt lỗi gợi ý và lỗi binding

Nếu IDE không đề xuất `acme.gateway.mode` nhưng ứng dụng vẫn bind được giá trị từ `application.yaml`, đó là vấn đề **metadata/tooling**, không nhất thiết là vấn đề runtime.

Ngược lại, nếu IDE gợi ý key nhưng runtime luôn bỏ qua, hãy kiểm tra `@ConfigurationPropertiesScan`/`@EnableConfigurationProperties`, tên prefix, getter/setter hoặc constructor binding và việc code có dùng property hay không.

### 17.2. Tên đúng nhưng default mô tả sai

Nếu additional metadata ghi:

```json
{
  "properties": [
    {
      "name": "acme.gateway.connect-timeout",
      "defaultValue": "10s"
    }
  ]
}
```

nhưng class có:

```java
private Duration connectTimeout = Duration.ofSeconds(3);
```

thì IDE có thể báo default là 10s trong khi runtime giữ 3s khi key thiếu. Đây là **sai khác tài liệu**, không phải phép đổi default do annotation processor. Cần đồng bộ metadata với code hoặc thay default runtime thật sự.

## 18. Những lỗi thường gặp khi thêm property thủ công

### Lỗi 1 — Tưởng additional file là application configuration

```json
{
  "properties": [
    {"name": "server.port", "defaultValue": 9090}
  ]
}
```

Nó **không tự đổi port server thành 9090**. Nếu muốn runtime đổi port, hãy dùng:

```properties
server.port=9090
```

hoặc cấu hình programmatic có hiệu lực. Metadata chỉ mô tả giá trị cho tooling.

### Lỗi 2 — Thêm thuộc tính mới rồi tưởng Java tự có field

```json
{
  "properties": [
    {"name": "acme.experimental-flag", "type": "java.lang.Boolean"}
  ]
}
```

Không có getter `isExperimentalFlag()` hay field Java nào tự xuất hiện. Phải tự cài đặt property trong code runtime hoặc dùng `@ConfigurationProperties`.

### Lỗi 3 — Khai báo hint sai tên

```json
{
  "hints": [
    {"name": "acme.gateway.connectTimeout", "values": [{"value": "5s"}]}
  ]
}
```

Trong metadata nên dùng tên canonical:

```text
acme.gateway.connect-timeout
```

Tên viết camelCase có thể không được IDE ghép đúng với property mục tiêu.

### Lỗi 4 — Nhầm Map keys với Map values

Nếu target là `Map<String,String> clientTags`, dùng:

```json
{"name": "acme.gateway.client-tags.keys"}
```

để gợi ý key, và:

```json
{"name": "acme.gateway.client-tags.values"}
```

để gợi ý value. Việc thêm một hint lên `acme.gateway.client-tags` không thay thế hai hậu tố đặc thù này.

### Lỗi 5 — Chỉ có enum values ở metadata nhưng code vẫn chấp nhận mọi String

Khi Java property là `String`, hints không phải validation. Muốn runtime chỉ nhận một tập giá trị, dùng enum hoặc kiểm tra rõ. Tránh để IDE gợi ý một tập có vẻ “bắt buộc” trong khi code chấp nhận giá trị không hợp lệ.

### Lỗi 6 — Dùng giá trị deprecated replacement chưa được hỗ trợ

Nếu metadata báo chuyển sang `acme.new-key` nhưng bản phát hành hiện tại chưa đọc key mới, người vận hành có thể tạo cấu hình vô hiệu. Chỉ gợi ý replacement thật sự được runtime hỗ trợ.

### Lỗi 7 — Bỏ qua annotation processor

Chỉ commit `additional-spring-configuration-metadata.json` chưa đủ khi build không chạy processor. Đọc output generated để xác minh.

### Lỗi 8 — Sửa trực tiếp file output

Chỉnh `target/classes/META-INF/spring-configuration-metadata.json` có thể tạo kết quả nhìn đúng tạm thời nhưng mất sau clean build. File bền vững là source `additional-...json`.

### Lỗi 9 — Thừa group thủ công không cần thiết

Một property không bắt buộc phải có một group do người dùng khai báo. Nếu processor đã sinh group từ `@ConfigurationProperties`, thường không cần lặp lại trong additional file. Giữ JSON càng tập trung càng dễ bảo trì.

### Lỗi 10 — Chứa dữ liệu nhạy cảm trong metadata

```json
{
  "properties": [
    {
      "name": "acme.auth.token",
      "defaultValue": "real-secret-token-here"
    }
  ]
}
```

Đây là cách làm nguy hiểm vì metadata có thể được đóng gói và phát hành cùng artifact hoặc hiển thị trong công cụ. Metadata không phải secret store; chỉ mô tả cách cấp secret thông qua nguồn an toàn, không ghi credential thật.

### Lỗi 11 — Dùng provider như một runtime resolver

`spring-bean-reference` giúp IDE gợi ý tên bean; code vẫn cần chuyển tên String thành bean reference. `handle-as` giúp IDE hiểu kiểu semantic; code runtime không tự đổi String thành Resource nếu không có logic thích hợp.

### Lỗi 12 — Không kiểm tra metadata sau refactor

Đổi Java field `connectTimeout` thành `requestTimeout` sẽ khiến key chuẩn đổi từ `acme.gateway.connect-timeout` sang `acme.gateway.request-timeout` nếu không còn alias. Additional metadata có thể tiếp tục mô tả key cũ như một property mới, dù runtime đã bỏ nó. Khi refactor, cập nhật source JSON và migration strategy đồng bộ.

## 19. Gợi ý quy trình làm việc khi phát triển một property mới

### Bước 1 — Khai báo runtime contract

Quyết định:

- Prefix và canonical property name.
- Java target type: String, enum, Duration, DataSize, List, Map, object...
- Default thực thi, nếu có.
- Các giá trị hợp lệ và đơn vị.
- Profile/environment override có được hỗ trợ không.
- Nếu đổi tên từ key cũ: quy tắc migration và precedence.

### Bước 2 — Dùng @ConfigurationProperties khi phù hợp

Khai báo Java model type-safe và đăng ký bean để runtime binding hoạt động. Đừng bỏ qua cách tự động này chỉ vì biết viết JSON metadata thủ công.

### Bước 3 — Tạo hoặc sửa additional metadata

Chỉ thêm thông tin mà processor không suy ra được hoặc cần tinh chỉnh: `description`, `defaultValue` được ghi chính xác, `deprecation`, `hints` và các key runtime đặc biệt không thuộc model.

### Bước 4 — Chạy build

Kích hoạt annotation processor, bảo đảm resource được nhìn thấy ở compile time, kiểm tra lỗi JSON/processor. Không dùng output cũ làm bằng chứng.

### Bước 5 — Kiểm tra generated metadata

Tìm đúng item `name` ở `properties` và đúng item trong `hints`. Phân biệt property có thật với hint chỉ gợi ý.

### Bước 6 — Kiểm tra trải nghiệm IDE

Mở `application.properties` hoặc `application.yaml`, thử autocomplete và hover description. Khả năng hiển thị có thể phụ thuộc IDE/plugin và version.

### Bước 7 — Kiểm tra hành vi runtime riêng

Chạy test/app với giá trị từ Config Data/OS env/CLI; xác nhận bean hoặc service **thực sự nhận giá trị đúng**, default đúng và validation đúng. **Không dùng metadata được sinh làm bằng chứng duy nhất cho runtime**.

## 20. Bảng quyết định: khi nào cần additional metadata?

| Nhu cầu | Cách phù hợp |
| --- | --- |
| Một bean `@ConfigurationProperties` có field chuẩn | Để processor tự sinh phần lớn metadata |
| Field đã được processor sinh nhưng mô tả chưa rõ | Thêm `properties` với `name` và `description` |
| Default runtime đã có nhưng metadata chưa mô tả | Thêm `defaultValue` trùng default runtime |
| Một property được đọc trực tiếp từ `Environment` | Thêm manual property với `name`, `type`, `description` |
| Một String chỉ có vài lựa chọn phổ biến | Thêm `hints.values`; validate runtime bằng cơ chế khác khi cần |
| Một Map có tên key/vocabulary gợi ý | Dùng hint `.keys` và `.values` |
| Một String chứa tên class | Provider `class-reference` |
| Một String chứa bean name | Provider `spring-bean-reference` |
| Một String chứa đường dẫn Resource | Provider `handle-as` với target Resource |
| Một key cũ có key mới thay thế | Thêm `deprecation.reason`/`replacement` và triển khai tương thích runtime |
| Muốn đổi giá trị mặc định runtime | Sửa Java default/Config Data, **không chỉ metadata** |
| Muốn chặn giá trị không hợp lệ khi khởi động | Enum, Bean Validation, custom validation/conversion |
| Muốn property được bind thành field mới | Sửa/đăng ký Java configuration properties, không chỉ file JSON |
| IDE không gợi ý key | Kiểm tra processor, merged metadata, classpath và IDE trước khi sửa runtime code |

## 21. Tài liệu tham khảo chính thức

- **Spring Boot 3.3 — Configuration Metadata**, bao gồm Metadata Format, Providing Manual Hints và Generating Your Own Metadata by Using the Annotation Processor: https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/index.html
- **Spring Boot 3.3 — Metadata Format**, mô tả mảng `groups`, `properties`, `hints` và các thuộc tính của item: https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/format.html
- **Spring Boot 3.3 — Providing Manual Hints**, bao gồm Map `.keys`/`.values` và những value providers chuẩn: https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/manual-hints.html
- **Spring Boot 3.3 — Annotation Processor**, phần Adding Additional Metadata: https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/annotation-processor.html
- **Spring Boot 3.3.0-M2 — Configuration Metadata Reference** (tài liệu thuộc dòng phát triển 3.3 có mục bổ sung metadata): https://docs.spring.io/spring-boot/docs/3.3.0-M2/reference/html/configuration-metadata.html
- **Spring Boot 3.3 — Externalized Configuration**, phần @ConfigurationProperties binding và PropertySource precedence: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html

## 22. Tóm tắt

1. `additional-spring-configuration-metadata.json` đặt tại `src/main/resources/META-INF/` và được **annotation processor hợp nhất ở build time**, không phải một property source runtime.
2. File dùng schema metadata với các mảng `groups`, `properties` và `hints`; chỉ cần khai báo phần thực sự sử dụng.
3. Với property được processor phát hiện trong module, additional metadata có thể ghi đè `description`, `defaultValue` và `deprecation` **khi được chỉ định**; property chưa phát hiện có thể được thêm mới.
4. Dùng `hints.values` và `hints.providers` để bổ sung gợi ý IDE, nhưng **không coi chúng là validation hoặc runtime conversion**.
5. Với Map, thêm `.keys` và `.values` cho hai kiểu gợi ý khác nhau.
6. `deprecation.replacement` giúp thông báo hướng chuyển key, nhưng không tự sửa cấu hình hoặc tạo alias runtime.
7. Kết quả cần kiểm tra là `META-INF/spring-configuration-metadata.json` được tạo sau compile, và khi phát hành thì kiểm tra metadata có mặt trong artifact thích hợp.
8. Mọi thông tin default/type/deprecation phải phản ánh đúng contract runtime; giữ metadata đồng bộ với class, cấu hình và test.

**Nguyên tắc cuối:** Additional metadata giúp **công cụ hiểu cấu hình tốt hơn**, không làm **ứng dụng tự hoạt động khác đi**. Hãy sử dụng nó như tài liệu máy đọc được cho IDE và người phát triển, còn hành vi runtime vẫn được quyết định bởi Config Data, Java code, Binder và validation.

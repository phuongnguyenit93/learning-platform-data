# additional-spring-configuration-metadata.json cho mô tả bổ sung và gợi ý

## 1. Mục đích: giúp IDE hiểu cấu hình của thư viện

Spring Boot có thể tự sinh metadata cho các thuộc tính được khai báo bằng `@ConfigurationProperties`. Metadata này giúp IDE hiển thị mô tả, kiểu dữ liệu, giá trị mặc định và gợi ý autocomplete khi người dùng sửa `application.properties` hoặc `application.yaml`.

Metadata tự sinh không phải lúc nào cũng đủ. Một property có thể được đọc bằng `@Value`, custom binder hoặc trực tiếp từ `Environment`; default của enum/collection có thể không được processor suy ra; hoặc một property cần mô tả rõ hơn, có giá trị gợi ý, hay cần chỉ ra key thay thế sau khi deprecated.

Spring Boot cung cấp file:

```text
src/main/resources/META-INF/additional-spring-configuration-metadata.json
```

Annotation processor đọc file này và merge vào metadata chuẩn:

```text
META-INF/spring-configuration-metadata.json
```

**File additional là metadata dành cho IDE và tooling.** Nó không đăng ký bean, không tạo property trong `Environment`, không tự làm một chuỗi trở thành giá trị hợp lệ khi bind và không thay thế validation runtime. Nếu khai báo property mà không có code nào đọc, metadata chỉ giúp IDE gợi ý; thư viện vẫn cần logic để tiêu thụ giá trị đó.

Bài này dùng Spring Boot 3.3.x và Java 17+, đi qua cấu trúc JSON, `groups`/`properties`/`hints`, value providers, deprecation, cấu hình annotation processor và một bài test xác minh metadata đã được merge vào artifact.

## 2. Metadata chuẩn và metadata bổ sung

Hai file có cùng định dạng JSON nhưng vai trò khác nhau:

| File | Ai tạo/duy trì? | Vai trò |
| --- | --- | --- |
| `META-INF/spring-configuration-metadata.json` | Annotation processor tạo khi compile | Metadata cuối cùng để IDE và tooling đọc |
| `META-INF/additional-spring-configuration-metadata.json` | Developer viết thủ công | Dữ liệu bổ sung hoặc override được processor merge vào file chuẩn |

Không tự sửa file generated trong thư mục build. Lần compile tiếp theo có thể ghi đè thay đổi. Hãy sửa file additional hoặc Java source có annotation/Javadoc tương ứng.

File additional là optional. Nếu tất cả property đã được mô tả đầy đủ bằng `@ConfigurationProperties` và annotation processor, không cần tạo file rỗng.

### 2.1. Khi nào nên thêm metadata thủ công?

| Nhu cầu | Nơi nên khai báo |
| --- | --- |
| Property thuộc `@ConfigurationProperties`, tên và kiểu đã rõ | Để processor sinh tự động |
| Description tự sinh còn thiếu hoặc chưa rõ | Thêm `description` |
| Default tĩnh của enum/collection không được suy ra | Thêm `defaultValue` chính xác |
| Property do custom code đọc, không xuất hiện trong properties bean | Thêm entry trong `properties` |
| Muốn gợi ý một số giá trị thường dùng | Thêm `hints.values` |
| Muốn IDE gợi ý class, bean, profile hoặc resource | Thêm `hints.providers` |
| Muốn đánh dấu key cũ và key thay thế | Thêm `deprecation` hoặc dùng `@DeprecatedConfigurationProperty` khi code vẫn xử lý key cũ |

Nếu một nhóm property có thể được biểu diễn rõ bằng một `@ConfigurationProperties` class, nên làm điều đó trước. Metadata bổ sung dành cho những thông tin không thể suy ra hoặc cần biên tập lại.

## 3. Cấu trúc JSON cấp cao

File metadata có ba phần chính:

```json
{
  "groups": [],
  "properties": [],
  "hints": []
}
```

- `groups` mô tả namespace/nhóm property, ví dụ `acme.storage`. Group không tự mang giá trị cấu hình.
- `properties` mô tả từng key người dùng có thể đặt, như `acme.storage.mode`.
- `hints` bổ sung lựa chọn giá trị hoặc ngữ nghĩa để IDE hỗ trợ autocomplete.

Không phải property nào cũng bắt buộc có group. Một property độc lập vẫn có thể nằm trong `properties` mà không cần tạo group.

### 3.1. Group

Một group object có các thuộc tính thường dùng:

| Thuộc tính | Bắt buộc? | Ý nghĩa |
| --- | :---: | --- |
| `name` | Có | Tên đầy đủ của group, lowercase và phân tách bằng dấu chấm |
| `type` | Không | Tên class biểu diễn kiểu dữ liệu của group |
| `description` | Không | Mô tả ngắn để IDE hiển thị |
| `sourceType` | Không | Class nguồn đóng góp group |
| `sourceMethod` | Không | Method nguồn đóng góp group, nếu group đến từ method được annotate |

Ví dụ:

```json
{
  "groups": [
    {
      "name": "acme.storage",
      "type": "com.example.storage.StorageProperties",
      "description": "Settings for the Acme storage integration.",
      "sourceType": "com.example.storage.StorageProperties"
    }
  ]
}
```

`type` và `sourceType` có thể giống nhau khi group dựa trên một `@ConfigurationProperties` class. Với group được đóng góp bởi một method `@Bean`, `sourceType` có thể là class configuration chứa method đó, còn `type` là kiểu trả về. Nếu không biết type/source, có thể bỏ thuộc tính tương ứng thay vì đoán.

Group giúp IDE hiển thị namespace có cấu trúc. Nó không tạo nested Java object và không tự làm binder chấp nhận property.

### 3.2. Property

Một property object thường dùng các thuộc tính:

| Thuộc tính | Bắt buộc? | Ý nghĩa |
| --- | :---: | --- |
| `name` | Có | Tên key đầy đủ, lowercase, phân tách bằng dấu chấm |
| `type` | Không | Tên class hoặc generic signature của giá trị |
| `description` | Không | Giải thích tác dụng và ngữ cảnh sử dụng |
| `sourceType` | Không | Class nguồn đóng góp property |
| `defaultValue` | Không | Giá trị mặc định thực tế khi người dùng không cấu hình |
| `deprecation` | Không | Trạng thái deprecated và hướng thay thế |

Ví dụ:

```json
{
  "name": "acme.storage.region",
  "type": "java.lang.String",
  "description": "Logical region selected by the storage integration.",
  "sourceType": "com.example.storage.StorageProperties",
  "defaultValue": "local"
}
```

Với primitive, metadata dùng kiểu wrapper để nhất quán: `boolean` là `java.lang.Boolean`, `int` là `java.lang.Integer`. Với generic, có thể dùng đầy đủ kiểu như `java.util.Map<java.lang.String,com.example.Mode>`.

**Default value là thông tin mô tả, không phải lệnh gán default ở runtime.** Nếu code thực tế mặc định `local`, metadata có thể ghi `"defaultValue": "local"`. Nếu metadata ghi `cloud` nhưng constructor/binder thực tế dùng `local`, IDE sẽ hướng dẫn sai. Chỉ ghi giá trị mà code thật sự sử dụng.

Nếu default được tính từ environment, gọi method, đọc file hoặc phụ thuộc runtime state, đừng đoán. Có thể bỏ `defaultValue` nếu không thể đưa ra một giá trị tĩnh đúng.

### 3.3. Property tự sinh và property chỉ có metadata thủ công

Khi property đã được annotation processor nhận diện, file additional có thể bổ sung mô tả, default hoặc deprecation cho cùng `name`. Processor hợp nhất thông tin theo tên property; những thuộc tính manual được hỗ trợ sẽ override thông tin tương ứng nếu được khai báo.

Nếu property chưa được nhận diện trong module, entry manual có thể thêm nó vào metadata. Trường hợp đó nên khai báo `type` và `description` để IDE có đủ thông tin.

Điều này hữu ích cho property được đọc bằng code tùy chỉnh:

```java
String mode = environment.getProperty("acme.storage.mode");
```

Đây chỉ là đoạn minh họa cách đọc từ `Environment`. Thêm metadata giúp IDE hiểu key, nhưng **không thay đổi** cách code đọc nó và không tạo validation. Nếu muốn type-safe binding, cân nhắc `@ConfigurationProperties`.

## 4. File mẫu: mô tả, default, deprecation và hints

Ví dụ dưới đây kết hợp các trường hợp phổ biến:

- Bổ sung description và default cho property enum đã được processor sinh.
- Bổ sung property metadata cho các chuỗi đại diện class name, bean name và resource path.
- Đưa ra gợi ý mode/region.
- Hướng dẫn IDE gợi ý class, bean, resource và profile.
- Đánh dấu một property cũ đã bị loại bỏ.

Đặt file tại `src/main/resources/META-INF/additional-spring-configuration-metadata.json`:

```json
{
  "groups": [
    {
      "name": "acme.storage",
      "type": "com.example.storage.StorageProperties",
      "description": "Settings for the Acme storage integration.",
      "sourceType": "com.example.storage.StorageProperties"
    }
  ],
  "properties": [
    {
      "name": "acme.storage.mode",
      "description": "Controls the execution strategy used by the storage client.",
      "defaultValue": "safe"
    },
    {
      "name": "acme.storage.region",
      "type": "java.lang.String",
      "description": "Logical region selected by the storage integration.",
      "sourceType": "com.example.storage.StorageProperties"
    },
    {
      "name": "acme.storage.client-class",
      "type": "java.lang.String",
      "description": "Fully qualified class name of the client implementation.",
      "sourceType": "com.example.storage.StorageProperties"
    },
    {
      "name": "acme.storage.client-bean",
      "type": "java.lang.String",
      "description": "Name of an application bean that supplies the storage client.",
      "sourceType": "com.example.storage.StorageProperties"
    },
    {
      "name": "acme.storage.change-log",
      "type": "java.lang.String",
      "description": "Location of the storage migration changelog.",
      "sourceType": "com.example.storage.StorageProperties"
    },
    {
      "name": "acme.storage.old-mode",
      "type": "java.lang.String",
      "description": "Legacy mode property that is no longer supported.",
      "deprecation": {
        "level": "error",
        "reason": "The old mode setting has been removed.",
        "replacement": "acme.storage.mode"
      }
    }
  ],
  "hints": [
    {
      "name": "acme.storage.mode",
      "values": [
        {
          "value": "safe",
          "description": "Use conservative defaults for compatibility."
        },
        {
          "value": "fast",
          "description": "Prefer throughput when the backend supports it."
        }
      ]
    },
    {
      "name": "acme.storage.region",
      "values": [
        {
          "value": "local",
          "description": "Use the local development endpoint."
        },
        {
          "value": "cloud",
          "description": "Use the configured cloud endpoint."
        }
      ],
      "providers": [
        {
          "name": "any"
        }
      ]
    },
    {
      "name": "acme.storage.client-class",
      "providers": [
        {
          "name": "class-reference",
          "parameters": {
            "target": "com.example.storage.StorageClient",
            "concrete": true
          }
        }
      ]
    },
    {
      "name": "acme.storage.client-bean",
      "providers": [
        {
          "name": "spring-bean-reference",
          "parameters": {
            "target": "com.example.storage.StorageClient"
          }
        }
      ]
    },
    {
      "name": "acme.storage.change-log",
      "providers": [
        {
          "name": "handle-as",
          "parameters": {
            "target": "org.springframework.core.io.Resource"
          }
        }
      ]
    },
    {
      "name": "spring.profiles.active",
      "providers": [
        {
          "name": "spring-profile-name"
        }
      ]
    }
  ]
}
```

Đây là JSON mẫu hoàn chỉnh. Các tên package `com.example.storage` và class `StorageClient` là ví dụ cho project tương ứng; khi áp dụng vào thư viện thật, hãy thay bằng FQCN tồn tại.

### 4.1. Vì sao property mode chỉ khai báo description/default?

Giả sử `StorageProperties` đã khai báo:

```java
@ConfigurationProperties("acme.storage")
public class StorageProperties {

    private Mode mode = Mode.SAFE;

    public Mode getMode() {
        return this.mode;
    }

    public void setMode(Mode mode) {
        this.mode = mode;
    }

    public enum Mode {
        SAFE, FAST
    }
}
```

Annotation processor đã biết `acme.storage.mode` và kiểu enum của nó. File additional chỉ cần cung cấp description/default bị thiếu. Không cần lặp lại `type` nếu type đã được sinh đúng.

Processor có thể không tự phát hiện default enum. Vì code khởi tạo `Mode.SAFE`, metadata bổ sung ghi `"defaultValue": "safe"` để IDE phản ánh đúng giá trị mặc định. Nếu đổi code thành `Mode.FAST`, hãy cập nhật metadata tương ứng.

### 4.2. Metadata-only property không tự được bind

Ví dụ `acme.storage.client-class` có thể được một resolver tùy chỉnh đọc bằng `Environment`. Metadata cung cấp type/description và class-reference hint. Nhưng nếu không có code nào đọc key này, người dùng nhập nó cũng không làm Spring tự tạo client.

Tương tự, `acme.storage.client-bean` gợi ý bean name phù hợp trong IDE. Binder vẫn chỉ bind chuỗi bean name; ứng dụng phải tự tra bean từ `ApplicationContext` hoặc dùng cơ chế injection phù hợp. Provider không tự chuyển chuỗi thành object bean.

## 5. Hints: gợi ý giá trị tĩnh và autocomplete theo ngữ nghĩa

Mỗi hint object có:

| Thuộc tính | Bắt buộc? | Ý nghĩa |
| --- | :---: | --- |
| `name` | Có | Tên property hoặc tên map key/value mà hint áp dụng |
| `values` | Không | Danh sách giá trị gợi ý và mô tả |
| `providers` | Không | Danh sách provider có thể đưa ra gợi ý theo project context |

Một value hint có `value` bắt buộc và `description` tùy chọn:

```json
{
  "name": "acme.storage.mode",
  "values": [
    {
      "value": "safe",
      "description": "Use conservative defaults for compatibility."
    },
    {
      "value": "fast",
      "description": "Prefer throughput when the backend supports it."
    }
  ]
}
```

IDE có thể hiển thị hai lựa chọn khi người dùng nhập property mode. Description giúp giải thích sự khác nhau.

**Hint không phải validation rule.** Nếu property là `String`, gợi ý `local` và `cloud` không tự cấm người dùng nhập `staging`. Nếu muốn giới hạn giá trị runtime, hãy dùng enum, Bean Validation, custom validator hoặc logic binding tương ứng. Nếu property là enum, binder/runtime mới là nơi xác nhận giá trị thuộc enum.

### 5.1. Hint cho Map keys và values

Với property kiểu Map, hint áp dụng cho key hoặc value bằng hậu tố:

- `acme.storage.contexts.keys`
- `acme.storage.contexts.values`

Không đặt hint trực tiếp cho toàn bộ map. Ví dụ:

```json
{
  "hints": [
    {
      "name": "acme.storage.contexts.keys",
      "values": [
        { "value": "primary" },
        { "value": "archive" }
      ]
    },
    {
      "name": "acme.storage.contexts.values",
      "values": [
        { "value": "fast" },
        { "value": "safe" }
      ]
    }
  ]
}
```

Nếu tập key thực sự cố định, một enum có thể là thiết kế tốt hơn String key tùy ý; IDE có thể tự hiểu enum mà không cần manual hints.

### 5.2. Provider any

Provider `any` cho phép IDE gợi ý một số giá trị đã biết nhưng vẫn chấp nhận giá trị khác. Nó phù hợp với property dạng String có tập giá trị thường gặp nhưng không đóng.

Ví dụ `acme.storage.region` gợi ý `local` và `cloud`, đồng thời cho phép region do tổ chức tự đặt. Không gắn `any` vào enum chỉ nhận `SAFE`/`FAST` nếu muốn IDE thể hiện đúng tập giá trị giới hạn; runtime enum vẫn từ chối giá trị lạ.

### 5.3. Provider class-reference

`class-reference` gợi ý các class có trong project. Tham số quan trọng:

- `target`: FQCN của kiểu mà class được chọn phải assignable.
- `concrete`: chỉ gợi ý class cụ thể hay cho phép cả abstract class; mặc định là true.

Ví dụ:

```json
{
  "name": "acme.storage.client-class",
  "providers": [
    {
      "name": "class-reference",
      "parameters": {
        "target": "com.example.storage.StorageClient",
        "concrete": true
      }
    }
  ]
}
```

Điều này phù hợp khi property có kiểu String để tránh dependency trực tiếp vào implementation class tùy chọn. Provider hỗ trợ IDE gợi ý tên class; code ứng dụng vẫn phải load/instantiate/validate class theo chính sách của thư viện.

### 5.4. Provider handle-as

`handle-as` yêu cầu IDE xử lý property như một type có ngữ nghĩa cao hơn. Nó hữu ích khi code giữ property dưới dạng String nhưng người dùng thực chất nhập một giá trị có thể chuyển đổi sang abstraction cụ thể.

Các target phổ biến gồm:

- Enum.
- `java.nio.charset.Charset`.
- `java.util.Locale`.
- `org.springframework.util.MimeType`.
- `org.springframework.core.io.Resource`.

Ví dụ property `acme.storage.change-log` được lưu dưới dạng String nhưng chứa resource location:

```json
{
  "name": "acme.storage.change-log",
  "providers": [
    {
      "name": "handle-as",
      "parameters": {
        "target": "org.springframework.core.io.Resource"
      }
    }
  ]
}
```

IDE có thể hỗ trợ gợi ý resource location như `classpath:/db/changelog.xml`. Điều đó không tự biến field String thành Resource hoặc thực hiện file access; code vẫn cần chuyển đổi khi sử dụng.

### 5.5. Provider spring-bean-reference

Provider này gợi ý bean name đang có trong project, có thể lọc theo type:

```json
{
  "name": "acme.storage.client-bean",
  "providers": [
    {
      "name": "spring-bean-reference",
      "parameters": {
        "target": "com.example.storage.StorageClient"
      }
    }
  ]
}
```

IDE có thể đề xuất tên bean assignable tới `StorageClient`. Đây vẫn là giá trị chuỗi trong cấu hình. Nếu ứng dụng cần dùng bean đó, code phải tra cứu bean bằng context hoặc thiết kế injection phù hợp; metadata không làm Binder tự resolve bean.

### 5.6. Provider spring-profile-name

Provider `spring-profile-name` hỗ trợ gợi ý profile đang được định nghĩa trong project:

```json
{
  "name": "spring.profiles.active",
  "providers": [
    {
      "name": "spring-profile-name"
    }
  ]
}
```

Có thể dùng provider này cho property profile của Spring hoặc property custom mang ý nghĩa tương tự. Đây là gợi ý theo IDE/project context, không phải danh sách profile mà Spring runtime bắt buộc phải dùng.

### 5.7. Provider logger-name

`logger-name` gợi ý tên logger và logger group đã biết. Tham số `group` có thể điều khiển việc đưa các logger group vào gợi ý; mặc định là true theo provider specification.

Provider này phù hợp cho property nhận logger category. Vì logger name có thể là bất kỳ package/class name nào, gợi ý không nên được xem là danh sách đóng.

### 5.8. Nhiều provider và khả năng hỗ trợ của IDE

IDE không bắt buộc hỗ trợ mọi provider. Nếu IDE không hiểu provider, nó có thể bỏ qua gợi ý đó mà không làm ứng dụng runtime lỗi.

Có thể khai báo nhiều provider cho cùng property nếu các provider đều có ích. IDE dùng provider đầu tiên mà nó hỗ trợ; do đó hãy đặt provider có ngữ nghĩa mạnh nhất lên trước. Không dựa vào provider để bảo đảm trải nghiệm giống hệt giữa mọi IDE.

## 6. Deprecation metadata: hướng người dùng sang key mới

Một property deprecated có thể có object `deprecation`:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `level` | `warning` hoặc `error`; mặc định là warning |
| `reason` | Lý do key cũ bị deprecated |
| `replacement` | Tên đầy đủ của property thay thế |

Hai mức có ý nghĩa khác nhau:

- `warning`: property vẫn được quản lý/bind; ứng dụng có thể duy trì tương thích trong giai đoạn chuyển đổi.
- `error`: property không còn được quản lý và không được bind như property được hỗ trợ.

Nếu key cũ vẫn được hỗ trợ trong code, phải giữ logic đọc/ánh xạ nó sang key mới. Metadata warning chỉ mô tả trạng thái; nó không tự viết adapter hoặc chuyển giá trị. Nếu key đã bị loại bỏ, metadata error có thể tiếp tục giúp IDE báo cho người dùng biết key cũ không còn hợp lệ và chỉ ra replacement.

### 6.1. Dùng @DeprecatedConfigurationProperty khi code vẫn hỗ trợ key cũ

Nếu class `@ConfigurationProperties` còn getter/setter tương thích cho key cũ, có thể dùng `@Deprecated` và `@DeprecatedConfigurationProperty` trên getter:

```java
@ConfigurationProperties("acme.storage")
public class StorageProperties {

    private String mode;

    public String getMode() {
        return this.mode;
    }

    public void setMode(String mode) {
        this.mode = mode;
    }

    @Deprecated
    @DeprecatedConfigurationProperty(
            replacement = "acme.storage.mode")
    public String getLegacyMode() {
        return this.mode;
    }

    @Deprecated
    public void setLegacyMode(String legacyMode) {
        this.mode = legacyMode;
    }
}
```

Đây là ví dụ minh họa bean giữ property cũ như alias cho property mới; code thực tế cần bảo đảm hai key ánh xạ tới cùng state theo contract đã công bố.

Annotation này tạo deprecation ở mức warning vì code vẫn tiếp tục xử lý key cũ. Nó không cung cấp cách đặt mức error. Khi getter/setter đã bị xóa khỏi public API nhưng vẫn muốn giữ lời nhắc cho người dùng, manual metadata có thể khai báo deprecation error và replacement.

### 6.2. Không nhầm metadata deprecation với @Deprecated của Java

`@Deprecated` trên method/class Java và deprecation metadata của configuration property có liên quan nhưng không thay thế nhau. Một Java getter có thể deprecated nhưng key vẫn bind. Một property bị đánh dấu error trong metadata có thể không còn được Boot quản lý ngay cả khi người dùng vẫn gõ key trong YAML.

Hãy xác định rõ contract:

- Còn hỗ trợ key cũ: giữ code tương thích và dùng warning.
- Đã ngừng hỗ trợ: loại bỏ binding/logic cũ và dùng error-level metadata.
- Có replacement: ghi đúng full property name, không ghi tên field Java hoặc tên getter.

## 7. Annotation processor: nguồn của metadata được merge

Spring Boot cung cấp artifact `spring-boot-configuration-processor`. Annotation processor quét class/method `@ConfigurationProperties` trong lúc compile và sinh `META-INF/spring-configuration-metadata.json`.

### 7.1. Maven

Khai báo processor là dependency optional trong module chứa configuration properties:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
```

`optional` giúp dependency processor không trở thành runtime dependency bắt buộc của consumer. Nếu project cấu hình Maven Compiler Plugin với annotation processor path riêng, hãy thêm processor vào cấu hình đó.

Maven lifecycle chuẩn xử lý resource trước compile. Nếu build tùy biến thay đổi thứ tự này, cần bảo đảm file additional đã có mặt khi processor chạy.

### 7.2. Gradle

Với Gradle, khai báo processor trong configuration riêng:

```groovy
dependencies {
    annotationProcessor(
        "org.springframework.boot:spring-boot-configuration-processor:3.3.13"
    )
}
```

Khi dùng file additional trong `src/main/resources`, bảo đảm `compileJava` nhận resource output làm input để processor nhìn thấy file trước lúc compile:

```groovy
tasks.named('compileJava') {
    inputs.files(tasks.named('processResources'))
}
```

Đây là bước dễ bị bỏ quên. Nếu processor chạy trước khi resource được xử lý, metadata tự sinh có thể vẫn xuất hiện nhưng description/hints thủ công không được merge như mong đợi.

### 7.3. Annotation processor sinh được những gì?

Processor đọc `@ConfigurationProperties` trên class và method. Nó có thể phát hiện group/property names, type, description từ Javadoc trong trường hợp được hỗ trợ, một số default tĩnh và cấu trúc nested/collection/map.

Không phải mọi default đều tự phát hiện được. Default enum/collection và giá trị được tính động có thể cần manual metadata. Nếu source Javadoc được chép thẳng vào JSON, hãy dùng plain text đơn giản; đừng kỳ vọng Markdown hoặc HTML được render như tài liệu rich text.

## 8. Project thực hành: merge additional metadata và kiểm tra JSON đầu ra

Bài thực hành tạo project Gradle nhỏ để xác minh:

1. `StorageProperties` sinh metadata tự động.
2. File additional bổ sung description/default cho property đã sinh.
3. Manual property và deprecation được merge.
4. Hints xuất hiện trong metadata chuẩn.
5. File đầu ra parse được như JSON.

### 8.1. Cấu trúc thư mục

```text
configuration-metadata-lab/
├── settings.gradle
├── build.gradle
├── src/main/java/com/example/storage/StorageProperties.java
├── src/main/resources/META-INF/additional-spring-configuration-metadata.json
└── src/test/java/com/example/storage/AdditionalMetadataTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'configuration-metadata-lab'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    annotationProcessor platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.13'
    )
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'

    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.13'
    )
    implementation 'org.springframework.boot:spring-boot'

    testImplementation 'org.junit.jupiter:junit-jupiter'
    testImplementation 'com.fasterxml.jackson.core:jackson-databind'
    testImplementation 'org.assertj:assertj-core'
}

tasks.named('compileJava') {
    inputs.files(tasks.named('processResources'))
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`StorageProperties.java`:

```java
package com.example.storage;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties("acme.storage")
public class StorageProperties {

    private Mode mode = Mode.SAFE;
    private String region;
    private String clientClass;
    private String clientBean;
    private String changeLog;

    public Mode getMode() {
        return this.mode;
    }

    public void setMode(Mode mode) {
        this.mode = mode;
    }

    public String getRegion() {
        return this.region;
    }

    public void setRegion(String region) {
        this.region = region;
    }

    public String getClientClass() {
        return this.clientClass;
    }

    public void setClientClass(String clientClass) {
        this.clientClass = clientClass;
    }

    public String getClientBean() {
        return this.clientBean;
    }

    public void setClientBean(String clientBean) {
        this.clientBean = clientBean;
    }

    public String getChangeLog() {
        return this.changeLog;
    }

    public void setChangeLog(String changeLog) {
        this.changeLog = changeLog;
    }

    public enum Mode {
        SAFE, FAST
    }
}
```

Đặt JSON mẫu ở mục 4 vào resource `src/main/resources/META-INF/additional-spring-configuration-metadata.json`. Tên file và đường dẫn phải chính xác; không đặt nhầm thành `spring-configuration-metadata.json` vì đó là file đầu ra chuẩn.

### 8.2. Test đọc file metadata đã sinh

`src/test/java/com/example/storage/AdditionalMetadataTest.java`:

```java
package com.example.storage;

import java.io.IOException;
import java.io.InputStream;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class AdditionalMetadataTest {

    private final ObjectMapper objectMapper = new ObjectMapper();

    @Test
    void generatedMetadataContainsManualDescriptionDefaultAndHints()
            throws IOException {

        InputStream stream = getClass().getResourceAsStream(
                "/META-INF/spring-configuration-metadata.json");

        assertThat(stream)
                .as("Generated Spring configuration metadata must exist")
                .isNotNull();

        try (stream) {
            JsonNode root = objectMapper.readTree(stream);

            JsonNode mode = findByName(
                    root.path("properties"), "acme.storage.mode");

            assertThat(mode).isNotNull();
            assertThat(mode.path("description").asText())
                    .contains("execution strategy");
            assertThat(mode.path("defaultValue").asText())
                    .isEqualTo("safe");

            JsonNode oldMode = findByName(
                    root.path("properties"), "acme.storage.old-mode");

            assertThat(oldMode).isNotNull();
            assertThat(oldMode.path("deprecation")
                    .path("level").asText()).isEqualTo("error");
            assertThat(oldMode.path("deprecation")
                    .path("replacement").asText())
                    .isEqualTo("acme.storage.mode");

            JsonNode modeHint = findByName(
                    root.path("hints"), "acme.storage.mode");

            assertThat(modeHint).isNotNull();
            assertThat(modeHint.path("values")).hasSize(2);
            assertThat(modeHint.path("values").get(0)
                    .path("value").asText()).isEqualTo("safe");

            JsonNode classHint = findByName(
                    root.path("hints"), "acme.storage.client-class");

            assertThat(classHint).isNotNull();
            assertThat(classHint.path("providers").get(0)
                    .path("name").asText()).isEqualTo("class-reference");
        }
    }

    private static JsonNode findByName(JsonNode entries, String name) {
        for (JsonNode entry : entries) {
            if (name.equals(entry.path("name").asText())) {
                return entry;
            }
        }
        return null;
    }
}
```

Test này kiểm tra **metadata đầu ra**, không kiểm tra binding runtime của `StorageProperties`. Mục tiêu là chứng minh processor đã merge file additional vào resource chuẩn và JSON có cấu trúc đọc được.

### 8.3. Chạy test

Từ thư mục project:

```bash
gradle clean test
```

Nếu dùng Gradle Wrapper trên Linux/macOS:

```bash
./gradlew clean test
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat clean test
```

Kết quả mong đợi là task test thành công với một test passed, miễn là JDK 17+ và dependency tương thích được tải đầy đủ. Không có stdout ứng dụng cố định; Gradle chỉ báo trạng thái task/test theo phiên bản và cấu hình logging.

### 8.4. Kiểm tra resource trong JAR

Sau khi build artifact:

```bash
jar tf build/libs/configuration-metadata-lab-1.0.0.jar
```

Trên Windows có thể lọc kết quả:

```powershell
jar tf build/libs/configuration-metadata-lab-1.0.0.jar |
    Select-String "spring-configuration-metadata"
```

Hãy xác nhận JAR có resource chuẩn `META-INF/spring-configuration-metadata.json`. IDE/tooling thường đọc metadata chuẩn này. File additional là nguồn đầu vào cho processor; điều quan trọng là nội dung bổ sung đã xuất hiện trong file chuẩn được đóng gói.

## 9. Cách kiểm tra trong IDE

Sau khi project compile, IDE có thể dùng metadata để:

- Gợi ý property name khi nhập `acme.storage.`.
- Hiển thị description khi hover hoặc mở documentation popup.
- Gợi ý `safe` và `fast` cho `acme.storage.mode`.
- Đưa ra class candidate cho `acme.storage.client-class`.
- Đưa ra bean candidate cho `acme.storage.client-bean`.
- Hỗ trợ resource location cho `acme.storage.change-log`.
- Cảnh báo property deprecated và đưa ra replacement.

Nếu metadata trong JAR đúng nhưng IDE không hiển thị:

1. Re-import/reload Maven hoặc Gradle project.
2. Chạy lại compile để annotation processor sinh file mới.
3. Kiểm tra output `META-INF/spring-configuration-metadata.json` trong build/classes hoặc JAR.
4. Kiểm tra IDE có hỗ trợ provider tương ứng hay không.
5. Đảm bảo IDE đang dùng module chứa artifact có metadata.
6. Nếu có nhiều module, xác định metadata thuộc module nào và module đó có nằm trong project model hiện tại không.

Không phải IDE nào cũng triển khai mọi provider. Autocomplete class/bean/profile/resource có thể khác nhau; điều đó không làm thay đổi runtime behavior của Spring Boot.

## 10. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Description thủ công không xuất hiện | File sai path hoặc processor chạy trước khi resource được xử lý | Kiểm tra path additional và task ordering |
| Metadata generated biến mất | Developer sửa trực tiếp file đầu ra chuẩn | Sửa file additional hoặc Java source, rồi build lại |
| JSON bị bỏ qua | Sai dấu phẩy, dấu ngoặc, kiểu dữ liệu hoặc comment không hợp lệ | Validate JSON trước khi compile |
| IDE gợi ý property nhưng ứng dụng không dùng giá trị | Metadata chỉ mô tả key; code không bind/read key đó | Thêm `@ConfigurationProperties` hoặc logic đọc property |
| IDE gợi ý giá trị lạ nhưng runtime từ chối | Hint không phải validator | Dùng enum/Bean Validation/custom validator |
| Default trong IDE khác runtime | Manual `defaultValue` không khớp constructor/field initializer | Đồng bộ metadata với default thực tế hoặc bỏ default nếu không chắc |
| Provider không gợi ý gì | IDE không hỗ trợ provider hoặc target class sai | Kiểm tra support và FQCN/parameters |
| Bean-reference hint nhưng bean không được inject | Provider chỉ gợi ý tên bean | Dùng ApplicationContext lookup hoặc dependency injection |
| Map hint không hoạt động | Hint gắn vào map thay vì keys/values | Dùng hậu tố `.keys` hoặc `.values` |
| Deprecated key vẫn được chấp nhận dù metadata warning | Warning giữ khả năng bind | Giữ alias có chủ đích hoặc chuyển sang error khi đã ngừng hỗ trợ |
| File additional đúng nhưng JAR thiếu metadata chuẩn | Processor không chạy hoặc resource merge chưa đúng | Kiểm tra annotationProcessor/Maven compile và JAR output |

### 10.1. Đừng dùng additional để thay thế runtime validation

Ví dụ, file metadata có thể ghi `acme.storage.mode` chỉ nhận `safe` hoặc `fast`. Nhưng nếu code property là `String`, người dùng vẫn có thể nhập `turbo` trừ khi runtime code kiểm tra nó.

Nếu tập giá trị thật sự đóng, khai báo Java enum:

```java
public enum Mode {
    SAFE, FAST
}
```

Nếu tập giá trị mở rộng, giữ String và dùng validator theo domain. Hints chỉ hỗ trợ khám phá giá trị, không thực thi hợp đồng.

### 10.2. Đừng khai báo default không có trong code

Metadata có thể ghi default để IDE hiển thị, nhưng binder không đọc file metadata để đặt giá trị cho object. Nếu field khởi tạo là `SAFE`, hãy mô tả `safe`. Nếu default phụ thuộc profile/environment, không ghi một giá trị cố định sai.

### 10.3. Đừng nhầm deprecation warning với removal

`warning` cho biết key cũ còn được quản lý. `error` cho biết key không còn được quản lý/bind như property được hỗ trợ. Nếu muốn chuyển dần API, giữ alias và logic tương thích trong thời gian warning; chỉ dùng error sau khi contract đã bỏ key cũ.

## 11. Giới hạn phiên bản: không dùng metadata của Boot 3.5 trong project Boot 3.3

Định dạng `groups`, `properties`, `hints`, value hints, providers và deprecation là nền tảng của configuration metadata trong Boot 3.x.

Tuy nhiên, không phải mọi trường metadata ở phiên bản sau đều có trong Boot 3.3. Cụ thể, khả năng `ignored.properties` để loại property khỏi metadata generated được giới thiệu trong Spring Boot 3.5. Nếu module target Boot 3.3, không sao chép cấu trúc `ignored` từ tài liệu/metadata Boot 3.5+ rồi kỳ vọng processor 3.3 xử lý giống nhau.

Với Boot 3.3, tập trung vào `groups`, `properties`, `hints` và `deprecation`. Nếu cần ẩn/loại một property generated, xử lý ở source model hoặc nâng version processor có chủ đích sau khi đánh giá compatibility.

## 12. Checklist trước khi merge metadata

- [ ] File nằm đúng tại `src/main/resources/META-INF/additional-spring-configuration-metadata.json`.
- [ ] Root JSON dùng đúng `groups`, `properties` và `hints`.
- [ ] Mọi group/property/hint có `name` đầy đủ và đúng canonical property name.
- [ ] Type là FQCN hoặc generic signature chính xác.
- [ ] Description ngắn, rõ, plain text và kết thúc bằng dấu chấm.
- [ ] Default value khớp với default thật trong code.
- [ ] Property manual không bị hiểu nhầm là tự động được bind.
- [ ] Value hints phản ánh giá trị gợi ý đúng, không giả vờ là runtime validation.
- [ ] Provider target là FQCN đúng và IDE được hỗ trợ.
- [ ] Map hints dùng hậu tố `.keys`/`.values`.
- [ ] Bean reference hint không bị hiểu nhầm là tự resolve bean.
- [ ] Deprecation level/reason/replacement phù hợp chính sách tương thích.
- [ ] Annotation processor được cấu hình trong Maven/Gradle.
- [ ] Gradle compile task phụ thuộc processResources khi dùng file additional.
- [ ] Test đọc được `META-INF/spring-configuration-metadata.json` đã merge.
- [ ] JAR publish có metadata chuẩn.
- [ ] Không dùng `ignored.properties` của Boot 3.5 trong module target Boot 3.3.
- [ ] IDE thực tế của nhóm hiển thị được các gợi ý quan trọng.

**Ghi nhớ:** `additional-spring-configuration-metadata.json` là cách bổ sung tài liệu và gợi ý cho configuration metadata được sinh tự động. Dùng `properties` để mô tả key, `groups` để tổ chức namespace, `hints.values` cho giá trị gợi ý và `hints.providers` cho autocomplete theo ngữ nghĩa. Dùng deprecation để hướng người dùng sang key mới. Sau cùng, xác minh processor đã merge file vào `META-INF/spring-configuration-metadata.json` trong artifact. Metadata giúp IDE hiểu cấu hình; code và validation vẫn chịu trách nhiệm cho hành vi runtime.

## Tài liệu chính thức

- Spring Boot 3.2 — Configuration Metadata (schema, properties, groups, hints, providers, deprecation): https://docs.spring.io/spring-boot/docs/3.2.5/reference/html/configuration-metadata.html
- Spring Boot 3.0 — Configuration Metadata and Adding Additional Metadata: https://docs.spring.io/spring-boot/docs/3.0.11/reference/html/configuration-metadata.html
- Spring Boot — Configuration Metadata Format: https://docs.spring.io/spring-boot/specification/configuration-metadata/format.html
- Spring Boot — Generating Metadata with the Annotation Processor: https://docs.spring.io/spring-boot/specification/configuration-metadata/annotation-processor.html
- Spring Boot 3.5 Release Notes — ignored properties support added to the annotation processor: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.5-Release-Notes

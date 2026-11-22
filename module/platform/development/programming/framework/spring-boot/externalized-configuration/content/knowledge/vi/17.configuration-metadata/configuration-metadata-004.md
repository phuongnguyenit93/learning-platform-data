# Cấu trúc groups, properties và hints của metadata JSON

> **Chủ đề:** Spring Boot Externalized Configuration  
> **Nhóm:** Metadata cấu hình

## 1. Vì sao Spring Boot có metadata cấu hình?

Khi sử dụng Spring Boot, người lập trình thường chỉnh những khóa như `server.port`, `spring.datasource.url` hoặc các thuộc tính riêng như `catalog.client.timeout`. Một IDE có hỗ trợ Spring Boot có thể gợi ý tên khóa, cho biết kiểu, hiển thị mô tả và đề xuất các giá trị phù hợp. Những thông tin này thường được cung cấp bởi **configuration metadata**.

Tệp JSON metadata được đóng gói tại đường dẫn:

~~~text
META-INF/spring-configuration-metadata.json
~~~

Đây là dữ liệu **dành cho công cụ phát triển**, không phải file cấu hình runtime. Spring Boot có thể sinh metadata nhờ `spring-boot-configuration-processor`, dựa trên các lớp `@ConfigurationProperties` và thông tin mã nguồn tương ứng. Lập trình viên cũng có thể bổ sung metadata thủ công.

Một tệp metadata điển hình gồm ba mảng cấp cao nhất:

~~~json
{
  "groups": [],
  "properties": [],
  "hints": []
}
~~~

Ý nghĩa:

- **`groups`**: những nhóm thuộc tính có cùng namespace/prefix, ví dụ `catalog.client`.
- **`properties`**: các tên property đầy đủ, kiểu Java, mô tả, default metadata và thông tin nguồn.
- **`hints`**: gợi ý bổ sung cho value, chẳng hạn danh sách lựa chọn hoặc một provider để IDE gợi ý theo ngữ cảnh.

Điều cực kỳ quan trọng: **metadata không tự tạo bean, không tự cấp giá trị mặc định cho ứng dụng, không sửa thứ tự ưu tiên của PropertySource và không tự kiểm tra hợp lệ dữ liệu khi chạy**.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Đọc được `groups`, `properties` và `hints` trong JSON.
2. Phân biệt group prefix và property scalar thực sự.
3. Giải thích `name`, `type`, `sourceType`, `sourceMethod`, `description`, `defaultValue` và `deprecation`.
4. Dùng `hints.values` và `hints.providers` đúng mục đích.
5. Khai báo hints cho `Map` bằng hậu tố `.keys`, `.values`.
6. Sinh metadata qua annotation processor và bổ sung thông tin bằng `additional-spring-configuration-metadata.json`.
7. Chẩn đoán việc IDE không hiện gợi ý trong khi runtime binding vẫn hoạt động.
8. Hiểu sự khác biệt giữa metadata, validation và nguồn cấu hình tại thời điểm khởi động.

## 2. Quan hệ giữa @ConfigurationProperties và metadata

Giả sử ta có record:

~~~java
package com.example.catalog.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "catalog.client")
public record CatalogClientProperties(
        URI endpoint,
        Duration timeout,
        int maxConnections,
        String mode
) {}
~~~

Cấu hình tương ứng trong `application.yml`:

~~~yaml
catalog:
  client:
    endpoint: "https://catalog.example.test"
    timeout: 3s
    max-connections: 20
    mode: safe
~~~

Ở build time, annotation processor có thể phân tích kiểu cấu hình và sinh metadata. Khi developer gõ YAML, IDE có thể sử dụng metadata để hiển thị gợi ý. Ở runtime, Binder nhận property từ `Environment` để tạo record.

~~~text
Java @ConfigurationProperties
             |
             v
Annotation processor (build)
             |
             v
spring-configuration-metadata.json
    |             |             |
 groups       properties       hints
    \             |             /
             IDE / tooling

application.yml / env / CLI / imports
             |
             v
     Spring Environment
             |
             v
      Spring Boot Binder
             |
             v
   CatalogClientProperties bean
~~~

Hai nhánh có mục đích riêng: metadata phục vụ tooling; Binder phục vụ ứng dụng.

Ví dụ metadata minh họa:

~~~json
{
  "groups": [
    {
      "name": "catalog.client",
      "type": "com.example.catalog.config.CatalogClientProperties",
      "sourceType": "com.example.catalog.config.CatalogClientProperties"
    }
  ],
  "properties": [
    {
      "name": "catalog.client.endpoint",
      "type": "java.net.URI",
      "description": "Địa chỉ API Catalog."
    },
    {
      "name": "catalog.client.timeout",
      "type": "java.time.Duration",
      "description": "Giới hạn thời gian chờ."
    },
    {
      "name": "catalog.client.max-connections",
      "type": "java.lang.Integer",
      "defaultValue": 20
    },
    {
      "name": "catalog.client.mode",
      "type": "java.lang.String"
    }
  ],
  "hints": [
    {
      "name": "catalog.client.mode",
      "values": [
        {"value": "safe", "description": "Chế độ an toàn."},
        {"value": "fast", "description": "Chế độ nhanh."}
      ]
    }
  ]
}
~~~

Đây là **JSON minh họa cấu trúc**, không phải khẳng định processor luôn tự sinh mọi description, hint hay default hệt như trên. Với một `String mode`, processor không tự biết hai lựa chọn nghiệp vụ `safe` và `fast` nếu chúng chưa được diễn tả trong nguồn hoặc metadata bổ sung.

## 3. Phần groups: mô tả nhóm cấu hình

Một phần tử `groups` mô tả một namespace:

~~~json
{
  "groups": [
    {
      "name": "catalog.client",
      "type": "com.example.catalog.config.CatalogClientProperties",
      "sourceType": "com.example.catalog.config.CatalogClientProperties",
      "description": "Thiết lập kết nối Catalog."
    }
  ]
}
~~~

### 3.1. Trường name

`groups[].name` là tên prefix, thường dùng ký tự chữ thường, dấu chấm phân cấp và kebab-case. Ví dụ:

~~~text
catalog.client
mail.sender
batch.import-job
payment.gateway.retry
~~~

`catalog.client` là **group prefix**. Tự nó thường không phải scalar property cần gán một chuỗi hoặc số. Các property cụ thể nằm dưới prefix, ví dụ `catalog.client.timeout`.

### 3.2. Trường type

`groups[].type` mô tả kiểu Java đại diện cho group. Nếu class được bind là `CatalogClientProperties`, metadata có thể chứa tên fully qualified class đó.

Không nhầm `type` của metadata với JSON Schema type như `object`. Spring Boot metadata thường dùng tên Java type.

### 3.3. sourceType và sourceMethod

`sourceType` cho biết kiểu Java nguồn được dùng để xác định group/property. Khi nhóm hoặc property liên quan tới một phương thức Java, ví dụ phương thức `@Bean` được đánh dấu để bind configuration properties, metadata có thể chứa `sourceMethod`.

Bảng:

| Trường | Ý nghĩa |
| --- | --- |
| `name` | Tên group/prefix |
| `type` | Java type đại diện group |
| `sourceType` | Java type khai báo/công bố nguồn metadata |
| `sourceMethod` | Tên Java method nguồn nếu có |
| `description` | Mô tả ý nghĩa namespace |

Không phải mọi entry đều có đủ các trường tùy chọn. Metadata được sinh có thể khác tùy cách khai báo code, phiên bản processor và mức thông tin sẵn có.

### 3.4. Group lồng nhau

Ví dụ Java:

~~~java
@ConfigurationProperties(prefix = "catalog.client")
public record CatalogClientProperties(
        URI endpoint,
        Retry retry
) {
    public record Retry(int maxAttempts, Duration backoff) {}
}
~~~

YAML:

~~~yaml
catalog:
  client:
    endpoint: "https://catalog.example.test"
    retry:
      max-attempts: 3
      backoff: 250ms
~~~

Metadata có thể mô tả cả `catalog.client` và `catalog.client.retry` dưới dạng groups. Các property scalar là `catalog.client.endpoint`, `catalog.client.retry.max-attempts` và `catalog.client.retry.backoff`.

Nested group không đồng nghĩa với một property scalar `catalog.client.retry` có thể đọc trực tiếp để nhận toàn bộ object.

## 4. Phần properties: mô tả từng key

`properties` thường là phần hữu ích nhất khi developer gõ file YAML hoặc properties.

~~~json
{
  "properties": [
    {
      "name": "catalog.client.timeout",
      "type": "java.time.Duration",
      "description": "Thời gian chờ tối đa một lần gọi.",
      "sourceType": "com.example.catalog.config.CatalogClientProperties"
    }
  ]
}
~~~

### 4.1. name là tên property đầy đủ

`name` thường bao gồm đầy đủ prefix:

~~~text
catalog.client.timeout
catalog.client.max-connections
catalog.client.retry.max-attempts
~~~

Nó không phải chỉ `timeout`. Điều này giúp IDE nhận biết thuộc tính dưới đúng namespace và hạn chế xung đột giữa các class có field cùng tên.

### 4.2. type mô tả Java type

Ví dụ:

| Property | Java type điển hình |
| --- | --- |
| `catalog.client.endpoint` | `java.net.URI` |
| `catalog.client.timeout` | `java.time.Duration` |
| `catalog.client.enabled` | Kiểu Boolean/boolean được biểu diễn theo schema |
| `catalog.client.max-connections` | Integer/int được biểu diễn trong metadata |
| `catalog.client.regions` | List String |
| `catalog.client.labels` | Map String sang String |

Một metadata `"type":"java.time.Duration"` giúp tooling hiểu loại giá trị được mong đợi, nhưng **không phải lệnh runtime tạo field Duration**. Kiểu Java trong code cấu hình mới quyết định Binder phải chuyển dữ liệu sang kiểu gì.

Với collection/generic type, chuỗi `type` có biểu diễn Java phù hợp và có thể phản ánh kiểu generic. Không xây dựng logic ứng dụng dựa vào việc hardcode chính xác một chuỗi type từ ví dụ nếu processor phiên bản khác có biểu diễn khác.

### 4.3. description

`description` nên giải thích ý nghĩa thuộc tính:

~~~json
{
  "name": "catalog.client.timeout",
  "type": "java.time.Duration",
  "description": "Thời gian chờ cho mỗi lần yêu cầu Catalog."
}
~~~

Một mô tả tốt có thể nêu đơn vị, tác động khi giá trị thiếu, mức độ bắt buộc và mối quan hệ với property khác. Không nên chỉ viết `"description":"Timeout"` nếu người dùng chưa hiểu timeout áp dụng cho kết nối hay toàn bộ request.

### 4.4. defaultValue

~~~json
{
  "name": "catalog.client.max-connections",
  "type": "java.lang.Integer",
  "defaultValue": 20
}
~~~

`defaultValue` là **một phần mô tả** mặc định của property để tooling hiển thị. Tự chỉnh `defaultValue` trong metadata không làm Binder tự gán 20 vào Java bean khi runtime thiếu giá trị.

Muốn có default thật, có thể dùng `@DefaultValue` trong constructor binding:

~~~java
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "catalog.client")
public record CatalogClientProperties(
        @DefaultValue("20") int maxConnections
) {}
~~~

Hoặc đặt trong file config:

~~~yaml
catalog:
  client:
    max-connections: 20
~~~

Hoặc với JavaBean dùng initializer:

~~~java
private int maxConnections = 20;
~~~

Các cách này có semantics và thứ tự override khác nhau. Metadata nên **mô tả đúng hành vi default thực sự**. Khi processor không suy ra được một default, cần cập nhật tài liệu/metadata bổ sung cho chính xác, chứ không tạo ra một default chỉ tồn tại trên giấy.

### 4.5. sourceType và sourceMethod

Một property có thể có `sourceType` để trỏ tới class khai báo. `sourceMethod` là thông tin tùy chọn khi có nguồn là method. Nếu một entry không có `sourceMethod`, không được kết luận nó không hợp lệ.

### 4.6. deprecation

Khi một property không còn được khuyến nghị:

~~~json
{
  "name": "catalog.client.legacy-timeout",
  "type": "java.time.Duration",
  "description": "Tên timeout đời cũ.",
  "deprecation": {
    "level": "warning",
    "reason": "Đổi tên để phân biệt request timeout và connect timeout.",
    "replacement": "catalog.client.timeout"
  }
}
~~~

Các trường thường gặp trong đối tượng deprecation:

- `level`: mức như `warning` hoặc `error`.
- `reason`: lý do không nên tiếp tục dùng.
- `replacement`: tên property đề xuất thay thế.
- `since`: thông tin phiên bản nếu được cung cấp.

Một cảnh báo deprecation **không tự alias property cũ sang property mới**. Nếu ứng dụng phải giữ tương thích tạm thời, cần có cơ chế runtime nhận tên cũ hoặc migration riêng.

### 4.7. Metadata không mô tả mọi field Java một cách mù quáng

Processor nhận diện các kiểu và phần tử theo quy tắc `@ConfigurationProperties`. Một Java class có method tính toán, field nội bộ hoặc nested class không có nghĩa tất cả đều nên xuất hiện thành property công khai.

Với kiểu khai báo mà processor chưa suy luận được hết, tệp metadata bổ sung có thể cung cấp thông tin còn thiếu.

## 5. Phần hints: giúp IDE gợi ý value

`hints` khác `properties` ở chỗ nó tập trung vào **giá trị có thể nhập** thay vì tên property và Java type.

Ví dụ `catalog.client.mode` có type String, nhưng ứng dụng khuyến khích hai chế độ:

~~~json
{
  "hints": [
    {
      "name": "catalog.client.mode",
      "values": [
        {
          "value": "safe",
          "description": "Chính sách ưu tiên an toàn."
        },
        {
          "value": "fast",
          "description": "Chính sách ưu tiên thời gian đáp ứng."
        }
      ]
    }
  ]
}
~~~

### 5.1. name liên kết hint với property

`hints[].name` thường là tên đầy đủ của property nhận hint, ví dụ `catalog.client.mode`.

Đừng dùng tên field ngắn `mode` nếu property thực sự nằm dưới prefix `catalog.client`; IDE cần liên hệ đúng key.

### 5.2. values: lựa chọn tĩnh

Mỗi phần tử `values` thường có:

- `value`: giá trị được đề xuất, có thể là string, số hoặc kiểu JSON tương ứng.
- `description`: giải thích cho lựa chọn đó.

Ví dụ:

~~~json
{
  "name": "catalog.client.retry-limit",
  "values": [
    {
      "value": 2,
      "description": "Ít lần thử lại."
    },
    {
      "value": 5,
      "description": "Chính sách thử lại rộng hơn."
    }
  ]
}
~~~

**Hint không phải constraint.** IDE có thể gợi ý 2 hoặc 5, nhưng Binder không mặc định từ chối 3 chỉ vì 3 không có trong danh sách `values`.

Muốn bắt buộc retry phải thuộc một tập cụ thể, dùng enum, Bean Validation hoặc custom validator phù hợp.

### 5.3. providers: gợi ý động

Một hint có thể khai báo `providers` để IDE gợi ý dựa trên ngữ cảnh thay vì chỉ một danh sách cố định.

~~~json
{
  "hints": [
    {
      "name": "app.handler-class",
      "providers": [
        {
          "name": "class-reference",
          "parameters": {
            "target": "com.example.spi.Handler"
          }
        }
      ]
    }
  ]
}
~~~

Ý tưởng: một IDE hỗ trợ `class-reference` có thể gợi ý tên class Java phù hợp. `parameters` là object cung cấp tham số cho provider, khi loại provider đó cần.

Những provider name thường được Spring Boot tài liệu hóa gồm:

| Provider | Mục tiêu gợi ý |
| --- | --- |
| `any` | Cho phép giá trị không giới hạn |
| `class-reference` | Tham chiếu tới class Java |
| `handle-as` | Diễn giải/gợi ý theo kiểu mong muốn |
| `logger-name` | Tên logger |
| `spring-bean-reference` | Tên bean trong Spring context |
| `spring-profile-name` | Tên Spring profile |
| `spring-property-name` | Tên Spring property |

Các IDE có thể hỗ trợ không đồng đều. Hint provider không tự tạo class instance, bean hoặc profile runtime.

### 5.4. Có cần cả values và providers?

Một hint có thể có values tĩnh, provider theo ngữ cảnh hoặc cả hai nếu schema và công cụ hỗ trợ. Nhưng đừng thêm nhiều provider gây nhiễu chỉ để JSON đầy đủ ba mảng. Cần có **mục đích gợi ý thật sự** và kiểm tra IDE dùng nó thế nào.

Một property kiểu enum có thể đã đủ thông tin để tooling đề xuất các enum constants; trong một số tình huống không cần thêm `values` thủ công.

## 6. Hints cho Map: hậu tố .keys và .values

Khi một Java properties class có `Map<String,String>`:

~~~java
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "routing")
public record RoutingProperties(
        Map<String, String> channels
) {}
~~~

YAML có thể là:

~~~yaml
routing:
  channels:
    email: enabled
    sms: disabled
~~~

IDE có thể cần gợi ý **key** và **value** khác nhau. Spring Boot metadata hỗ trợ hai hậu tố hint:

- `routing.channels.keys`: danh sách đề xuất cho **map keys**.
- `routing.channels.values`: danh sách đề xuất cho **map values**.

Ví dụ:

~~~json
{
  "hints": [
    {
      "name": "routing.channels.keys",
      "values": [
        {"value": "email", "description": "Kênh email."},
        {"value": "sms", "description": "Kênh SMS."},
        {"value": "push", "description": "Kênh push."}
      ]
    },
    {
      "name": "routing.channels.values",
      "values": [
        {"value": "enabled", "description": "Bật kênh."},
        {"value": "disabled", "description": "Tắt kênh."}
      ]
    }
  ]
}
~~~

Trong `hints` của Map, hậu tố `.keys` và `.values` là **quy ước metadata đặc biệt**, không bắt buộc là property runtime có tên `routing.channels.keys` hoặc `routing.channels.values`.

### 6.1. Hint không tạo entry

Chỉ vì JSON hints gợi ý `email`, `sms`, `push` không có nghĩa Binder tạo ba map entries. Khi runtime, Map vẫn đến từ những giá trị cấu hình có hiệu lực.

### 6.2. Bracket notation và key đặc biệt

Nếu key chứa `/` hoặc một số ký tự đặc biệt, Binder có quy tắc để giữ nguyên key. Ví dụ trong YAML:

~~~yaml
routing:
  channels:
    "[/api]": enabled
~~~

Hint gợi ý `/api` không tự sửa cú pháp YAML hoặc bảo đảm một key nhập sai được bind đúng. Metadata và quy tắc map binding là hai cơ chế khác nhau.

## 7. Ví dụ metadata hoàn chỉnh: groups + properties + hints

Giả sử ứng dụng có hợp đồng cấu hình:

~~~text
shipping.gateway.endpoint
shipping.gateway.timeout
shipping.gateway.mode
shipping.gateway.retry.max-attempts
shipping.gateway.retry.backoff
shipping.gateway.extra-headers
~~~

Một JSON minh họa đủ ba mảng:

~~~json
{
  "groups": [
    {
      "name": "shipping.gateway",
      "type": "com.example.shipping.GatewayProperties",
      "sourceType": "com.example.shipping.GatewayProperties",
      "description": "Cấu hình kết nối Shipping Gateway."
    },
    {
      "name": "shipping.gateway.retry",
      "type": "com.example.shipping.GatewayProperties$Retry",
      "description": "Chính sách retry."
    }
  ],
  "properties": [
    {
      "name": "shipping.gateway.endpoint",
      "type": "java.net.URI",
      "description": "Địa chỉ Shipping Gateway."
    },
    {
      "name": "shipping.gateway.timeout",
      "type": "java.time.Duration",
      "description": "Thời gian chờ lời gọi.",
      "defaultValue": "5s"
    },
    {
      "name": "shipping.gateway.mode",
      "type": "java.lang.String",
      "description": "Chế độ gửi yêu cầu."
    },
    {
      "name": "shipping.gateway.retry.max-attempts",
      "type": "java.lang.Integer",
      "defaultValue": 3
    },
    {
      "name": "shipping.gateway.retry.backoff",
      "type": "java.time.Duration",
      "defaultValue": "250ms"
    },
    {
      "name": "shipping.gateway.extra-headers",
      "type": "java.util.Map<java.lang.String,java.lang.String>",
      "description": "Các header bổ sung."
    }
  ],
  "hints": [
    {
      "name": "shipping.gateway.mode",
      "values": [
        {"value": "standard", "description": "Chế độ thường."},
        {"value": "priority", "description": "Chế độ ưu tiên."}
      ]
    },
    {
      "name": "shipping.gateway.extra-headers.keys",
      "values": [
        {"value": "x-trace-tag", "description": "Tag truy vết."},
        {"value": "x-client-name", "description": "Tên client."}
      ]
    }
  ]
}
~~~

Đọc theo thứ tự:

1. `groups` cho biết namespace `shipping.gateway` và `shipping.gateway.retry`.
2. `properties` cho biết các key cụ thể và Java types.
3. `hints` gợi ý chế độ `standard`/`priority` và hai map keys cho `extra-headers`.

### 7.1. YAML tương ứng

~~~yaml
shipping:
  gateway:
    endpoint: "https://shipping.example.test"
    timeout: 5s
    mode: standard
    retry:
      max-attempts: 3
      backoff: 250ms
    extra-headers:
      x-trace-tag: batch-a
      x-client-name: catalog
~~~

IDE có thể dựa trên metadata để gợi ý property names và values. Spring Boot runtime vẫn nạp YAML này bằng config-data loader và bind vào typed object theo precedence thực tế.

### 7.2. Record tương ứng

~~~java
package com.example.shipping;

import java.net.URI;
import java.time.Duration;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "shipping.gateway")
public record GatewayProperties(
        URI endpoint,
        @DefaultValue("5s") Duration timeout,
        @DefaultValue("standard") String mode,
        Retry retry,
        Map<String, String> extraHeaders
) {
    public record Retry(
            @DefaultValue("3") int maxAttempts,
            @DefaultValue("250ms") Duration backoff
    ) {}
}
~~~

Nếu muốn nested `retry` luôn được tạo khi toàn bộ `shipping.gateway.retry.*` vắng, xem xét empty `@DefaultValue` tại component `Retry retry`. Nếu không, constructor-bound nested field có thể null khi không có property nào cho nhóm.

Ví dụ tập trung vào metadata; một HTTP client production còn cần validation, xử lý network errors và bảo mật thích hợp.

## 8. Cách sinh metadata với annotation processor

Spring Boot cung cấp `spring-boot-configuration-processor` để sinh metadata lúc build.

### 8.1. Maven

Với dự án dùng Spring Boot dependency management, có thể thêm dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
~~~

Tùy phiên bản Maven Compiler Plugin/JDK và cấu hình project, có thể cần khai báo annotation processor path hoặc bật annotation processing tường minh. Nên dùng phiên bản processor tương thích với Spring Boot của project.

### 8.2. Gradle

Gradle Groovy DSL:

~~~groovy
dependencies {
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
~~~

Processor chạy trong build/compile. Với Kotlin, cách cấu hình xử lý annotation khác tùy plugin và phiên bản, cần tham khảo hướng dẫn Kotlin tương ứng thay vì áp dụng máy móc cấu hình Java.

### 8.3. Output

Sau khi compile, có thể thấy:

~~~text
target/classes/META-INF/spring-configuration-metadata.json
~~~

hoặc:

~~~text
build/classes/java/main/META-INF/spring-configuration-metadata.json
~~~

Tùy cấu hình build. Khi đóng gói, metadata có thể có ở `META-INF/spring-configuration-metadata.json` bên trong JAR.

### 8.4. Không cần processor để bind runtime

Một lớp `@ConfigurationProperties` vẫn có thể được bind khi chưa có metadata generated, miễn Spring Boot đã đăng ký bean và nạp dữ liệu cấu hình thích hợp. Processor giúp IDE hiểu property; **nó không phải thư viện Binder bắt buộc để runtime hoạt động**.

Nếu IDE không gợi ý nhưng bean vẫn nhận giá trị, cần điều tra metadata/build/IDE riêng.

## 9. additional-spring-configuration-metadata.json

Annotation processor có thể không suy ra đầy đủ descriptions, default metadata hoặc hints nghiệp vụ. Spring Boot hỗ trợ tệp bổ sung trong source tree:

~~~text
src/main/resources/META-INF/additional-spring-configuration-metadata.json
~~~

Ví dụ:

~~~json
{
  "properties": [
    {
      "name": "catalog.client.mode",
      "type": "java.lang.String",
      "description": "Chế độ vận hành Catalog client."
    }
  ],
  "hints": [
    {
      "name": "catalog.client.mode",
      "values": [
        {"value": "safe", "description": "Ưu tiên an toàn."},
        {"value": "fast", "description": "Ưu tiên tốc độ."}
      ]
    }
  ]
}
~~~

Processor có thể kết hợp dữ liệu bổ sung này với metadata được sinh, theo cơ chế và toolchain được Spring Boot hỗ trợ.

So sánh:

| Tệp | Nguồn | Vai trò |
| --- | --- | --- |
| `spring-configuration-metadata.json` | Thường được processor sinh ở build output | Bản metadata để IDE/tooling đọc |
| `additional-spring-configuration-metadata.json` | Do lập trình viên viết trong source resources | Bổ sung/chỉnh thông tin metadata |

Không sửa trực tiếp bản metadata **trong thư mục build output** rồi coi đó là thay đổi bền vững. Build tiếp theo có thể sinh lại và ghi đè. Hãy sửa source JavaDoc hoặc additional metadata.

### 9.1. Metadata bổ sung không tạo property runtime

Nếu thêm:

~~~json
{
  "properties": [
    {
      "name": "custom.feature.enabled",
      "type": "java.lang.Boolean",
      "description": "Bật tính năng tùy chỉnh."
    }
  ]
}
~~~

IDE có thể gợi ý tên property. Nhưng nếu ứng dụng không có code đọc/bind `custom.feature.enabled`, việc thêm metadata không tự làm tính năng đó hoạt động.

### 9.2. Nhiều module

Một thư viện hoặc starter nên đóng gói metadata cho **những configuration properties do chính module đó cung cấp**. IDE có thể thu thập metadata từ nhiều JAR trên classpath.

Nếu một module được phát hành với metadata cũ, IDE của ứng dụng dùng module đó có thể gợi ý sai key so với code runtime. Hãy duy trì metadata và phiên bản thư viện cùng nhau.

## 10. Mô tả từ JavaDoc

Processor có thể sử dụng JavaDoc và source declarations để tạo mô tả. Ví dụ:

~~~java
package com.example.demo.config;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

/**
 * Cấu hình cho công việc import dữ liệu.
 *
 * @param enabled có bật công việc import không
 * @param batchSize số bản ghi mỗi lô
 * @param timeout thời gian chờ tối đa
 */
@ConfigurationProperties(prefix = "demo.import-job")
public record ImportJobProperties(
        @DefaultValue("false") boolean enabled,
        @DefaultValue("100") int batchSize,
        @DefaultValue("10s") Duration timeout
) {}
~~~

Khi annotation processing được cấu hình phù hợp, tooling có thể nhận metadata cho các key:

~~~text
demo.import-job.enabled
demo.import-job.batch-size
demo.import-job.timeout
~~~

Không mặc định mọi phiên bản processor thu thập JavaDoc trên record theo một cách duy nhất. Cần bảo đảm IDE/build tool và processor thực tế hỗ trợ mô hình source đang dùng.

## 11. Metadata, default, validation và precedence: bốn việc khác nhau

### 11.1. Default metadata không quyết định default runtime

Metadata:

~~~json
{
  "properties": [
    {
      "name": "app.retry.attempts",
      "type": "java.lang.Integer",
      "defaultValue": 3
    }
  ]
}
~~~

Nếu Java class không có default, và các nguồn cấu hình đều không cung cấp `app.retry.attempts`, ứng dụng **không tự nhận giá trị 3 vì metadata**. Thứ tự nguồn và Binder quyết định kết quả, với kiểu primitive có thể rơi về 0 khi object được tạo.

Muốn default thực, dùng `@DefaultValue("3")` hoặc nguồn runtime phù hợp.

### 11.2. Hints không cưỡng chế validation

Metadata:

~~~json
{
  "hints": [
    {
      "name": "app.mode",
      "values": [
        {"value": "safe"},
        {"value": "fast"}
      ]
    }
  ]
}
~~~

Nếu code bind `String mode`, giá trị `experimental` có thể vẫn được chấp nhận dù không được liệt kê. Muốn chỉ cho phép hai chế độ, nên dùng enum hoặc validation.

### 11.3. Metadata không tạo bean

Cần đăng ký `@ConfigurationProperties` bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties` phù hợp. JSON metadata không thay thế bước đó.

### 11.4. Metadata không làm thay đổi nguồn ưu tiên cao hơn

Giả sử YAML có `app.client.timeout=5s`, biến môi trường có `APP_CLIENT_TIMEOUT=2s`, metadata mô tả default `3s`. Kết quả runtime thông thường lấy `2s` từ OS environment nếu không có nguồn cao hơn; metadata không tham gia tra cứu `Environment`.

### 11.5. Metadata không thay thế JSON Schema

Mặc dù là JSON, cấu trúc `groups`/`properties`/`hints` **khác JSON Schema**. Nó không tự áp dụng những ràng buộc kiểu `required` hoặc `minimum` cho file YAML.

Bean Validation, Binder conversion và kiểm tra nghiệp vụ vẫn là trách nhiệm riêng.

## 12. Deprecation và migration property

Khi đổi tên key, ví dụ:

~~~text
Trước: catalog.client.retry-count
Sau:   catalog.client.retry.max-attempts
~~~

có thể mô tả deprecation:

~~~json
{
  "properties": [
    {
      "name": "catalog.client.retry-count",
      "type": "java.lang.Integer",
      "deprecation": {
        "level": "warning",
        "reason": "Chuyển sang nhóm retry có cấu trúc.",
        "replacement": "catalog.client.retry.max-attempts"
      }
    }
  ]
}
~~~

IDE có thể giúp người cấu hình nhận ra key cũ và đề xuất key mới. Nhưng metadata **không tự biến key cũ thành alias**.

Nếu có deployment cũ cần tiếp tục dùng key cũ, ứng dụng phải cung cấp chính sách tương thích thực sự, ví dụ code đọc cả hai dạng với mức ưu tiên rõ hoặc cơ chế mapping được thiết kế.

Khi loại bỏ hỗ trợ runtime cho key cũ, cần cập nhật tài liệu và metadata để người dùng không bị gợi ý cấu hình không còn hoạt động.

## 13. Cách đọc những field tùy chọn

Không phải mọi group hoặc property đều chứa tất cả field. Một số trường hợp:

~~~json
{
  "properties": [
    {
      "name": "app.enabled",
      "type": "java.lang.Boolean"
    }
  ]
}
~~~

Entry này vẫn có ý nghĩa: nó mô tả tên và kiểu. Thiếu `description` không có nghĩa property hỏng. Thiếu `defaultValue` không có nghĩa giá trị runtime bắt buộc null. Thiếu `sourceMethod` không có nghĩa processor đã thất bại.

Khi đọc metadata, phân biệt:

- **Thông tin metadata đã biết.**
- **Thông tin không được mô tả.**
- **Hành vi Binder runtime.**

Đừng tự suy từ một trường thiếu rằng framework sẽ có hành vi bắt buộc nào đó.

## 14. Các lỗi thường gặp

| Triệu chứng | Khả năng nguyên nhân | Cách xử lý |
| --- | --- | --- |
| IDE không tự hoàn thành `catalog.client.*` | Chưa có processor hoặc annotation processing tắt | Bật processor và build lại |
| Metadata file không thấy ở output | Chưa compile, toolchain khác, processor chưa chạy | Kiểm tra build output đúng module |
| Runtime bind được nhưng IDE không gợi ý | Thiếu metadata hoặc IDE hỗ trợ hạn chế | Kiểm tra processor, classpath, plugin |
| IDE gợi ý property không còn dùng | Additional metadata hoặc JAR dependency cũ | Đồng bộ metadata với code |
| `defaultValue` hiển thị 20 nhưng runtime nhận 0 | Metadata không tạo default runtime | Thêm default thực trong code/config |
| Hint `safe`/`fast` nhưng ứng dụng chấp nhận `other` | Hint không phải validation | Dùng enum hoặc Bean Validation |
| Hints không hiện | Sai `name` hoặc IDE không hỗ trợ provider | Đối chiếu tên canonical, schema và IDE |
| Provider không tìm bean/class | Context/tooling chưa có thông tin hoặc provider không hỗ trợ | Kiểm tra provider name và parameters |
| Group tồn tại nhưng không có property | Class không có bindable members hoặc metadata bổ sung chưa đủ | Xem định nghĩa properties |
| Map key hint không hoạt động | Thiếu hậu tố `.keys`/`.values` | Dùng đúng naming dành cho Map |
| JSON bổ sung không đọc được | Sai cú pháp JSON, vị trí tài nguyên | Sửa JSON và đặt đúng thư mục |
| Source method thiếu | Không có method liên quan hoặc processor không ghi | Không coi là lỗi nếu không bắt buộc |
| Metadata bị mất sau clean build | Đã chỉnh file generated thay vì source | Dùng additional metadata hoặc JavaDoc |
| IDE gợi ý kiểu cũ | Metadata và Java type lệch nhau | Đồng bộ metadata và build lại |

### 14.1. Kiểm tra JSON hợp lệ

Tệp do lập trình viên viết phải là JSON chuẩn: tên key và string có nháy kép, không có comment, không có dấu phẩy cuối, object/array đóng đủ.

Ví dụ sai:

~~~text
{
  'hints': [
    {name: "app.mode"}
  ]
}
~~~

Ví dụ đúng:

~~~json
{
  "hints": [
    {
      "name": "app.mode"
    }
  ]
}
~~~

Cú pháp đúng là điều kiện cơ bản; tên key schema đúng, mô tả trung thực và sự tương thích với IDE vẫn cần được thiết kế riêng.

## 15. Thực hành: tạo và xem metadata

### Bước 1: Tạo record cấu hình

~~~java
package com.example.demo;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "lesson.cleanup")
public record CleanupProperties(
        @DefaultValue("false") boolean enabled,
        @DefaultValue("10s") Duration timeout,
        @DefaultValue("100") int batchSize
) {}
~~~

Bật scanning:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {}
~~~

### Bước 2: Bật processor

Gradle Groovy DSL:

~~~groovy
dependencies {
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
~~~

Hoặc cấu hình Maven tương ứng đã nêu.

### Bước 3: Compile và xem output

Sau khi build, tìm `META-INF/spring-configuration-metadata.json` và kiểm tra có group `lesson.cleanup`, các property `lesson.cleanup.enabled`, `lesson.cleanup.timeout`, `lesson.cleanup.batch-size`.

Không coi thứ tự phần tử trong mảng JSON là thứ tự ưu tiên runtime của các property. Metadata là một danh sách mô tả.

### Bước 4: Thêm hint

Tạo `src/main/resources/META-INF/additional-spring-configuration-metadata.json`:

~~~json
{
  "hints": [
    {
      "name": "lesson.cleanup.batch-size",
      "values": [
        {
          "value": 100,
          "description": "Lô nhỏ."
        },
        {
          "value": 500,
          "description": "Lô lớn."
        }
      ]
    }
  ]
}
~~~

### Bước 5: Viết file YAML

~~~yaml
lesson:
  cleanup:
    enabled: true
    timeout: 30s
    batch-size: 500
~~~

Quan sát IDE có completion/hints không, sau đó khởi chạy ứng dụng để xem typed values thực tế. Phân biệt IDE dùng metadata và Binder dùng YAML.

## 16. Bài tập tự kiểm tra

### Bài tập A: nhóm và thuộc tính

JSON:

~~~json
{
  "groups": [
    {"name": "billing.client", "type": "com.example.BillingProperties"}
  ],
  "properties": [
    {"name": "billing.client.endpoint", "type": "java.net.URI"},
    {"name": "billing.client.timeout", "type": "java.time.Duration"}
  ]
}
~~~

Hỏi: group name là gì, có mấy property, và có suy ra timeout thực tại runtime không?

Đáp án: `billing.client`, hai property, không thể suy ra timeout runtime chỉ từ metadata.

### Bài tập B: hint có bắt buộc không?

Hint đề xuất `mode=safe` và `mode=fast`. Nếu app bind `String mode` và file có `mode=experimental`, metadata có tự làm startup thất bại không?

Đáp án: không. Cần một rule runtime riêng nếu muốn hạn chế tập giá trị.

### Bài tập C: Map hint name

Với property `app.channels` kiểu `Map<String,String>`, tên hint nào đề xuất key `email`?

Đáp án: `app.channels.keys`. Với gợi ý value dùng `app.channels.values`.

### Bài tập D: Metadata default

Tệp metadata khai báo `"defaultValue":5` cho `app.retries` nhưng code chỉ có `int retries` không initializer. Thiếu runtime property thì có chắc giá trị 5 không?

Đáp án: không; metadata không cấp default runtime.

### Bài tập E: Provider

Hint sử dụng `"name":"spring-profile-name"`. Nó giúp gì?

Đáp án: IDE có thể đề xuất tên profile theo hỗ trợ tooling; nó không tự kích hoạt profile.

### Bài tập F: Migration

Một property cũ được đánh dấu `replacement` trong metadata. Có chắc runtime đọc tên cũ và tự chuyển sang tên mới không?

Đáp án: không; cần hỗ trợ tương thích riêng trong code hoặc cơ chế cấu hình.

## 17. Checklist khi phát triển metadata cho thư viện

- [ ] Các classes `@ConfigurationProperties` có prefix canonical và ổn định.
- [ ] Processor nằm đúng configuration và annotation processing được bật.
- [ ] Mô tả nói rõ ý nghĩa property thay vì lặp tên field.
- [ ] Tên `properties[].name` có prefix đầy đủ.
- [ ] `type` tương ứng Java type đang bind.
- [ ] `defaultValue` trong metadata khớp default runtime nếu có.
- [ ] Nested groups được mô tả theo cấu trúc code cần thiết.
- [ ] Hint `values` có tập lựa chọn thực sự hữu ích.
- [ ] Hint `providers` dùng tên hợp lệ và parameters đúng schema.
- [ ] Map hints dùng hậu tố `.keys` hoặc `.values`.
- [ ] Deprecated keys có reason/replacement rõ và chiến lược runtime riêng.
- [ ] Additional metadata nằm trong `src/main/resources/META-INF/`.
- [ ] Không sửa output generated như nguồn sự thật duy nhất.
- [ ] JAR/module được phát hành chứa metadata tương thích code.
- [ ] Có thử nghiệm IDE completion với ứng dụng tiêu thụ module.
- [ ] Binding và Bean Validation được kiểm tra độc lập metadata.
- [ ] Không đưa secret values thật vào description, hints hay examples.

## 18. Ghi nhớ

1. **`spring-configuration-metadata.json` là metadata cho tooling**, không phải file config data điều khiển ứng dụng lúc chạy.
2. **`groups`** mô tả prefix, type và nguồn của các nhóm cấu hình.
3. **`properties`** mô tả key cụ thể, kiểu Java, description, default metadata, source và deprecation.
4. **`hints`** mô tả gợi ý value bằng `values` và `providers`, có thể thêm gợi ý Map key/value bằng `.keys` và `.values`.
5. **`spring-boot-configuration-processor`** sinh metadata khi build; dùng `additional-spring-configuration-metadata.json` để bổ sung thủ công.
6. Default trong metadata **không tự tạo default runtime**; hint trong metadata **không tự cưỡng chế validation**.
7. Khi IDE không gợi ý, kiểm tra processor, build output, classpath và IDE; đừng kết luận Binder hỏng.
8. Metadata tốt được duy trì cùng API cấu hình thật, có mô tả đúng hành vi và không làm lộ thông tin nhạy cảm.

## Tài liệu tham khảo

- [Spring Boot — Configuration Metadata](https://docs.spring.io/spring-boot/specification/configuration-metadata/index.html): mục đích và khái quát.
- [Spring Boot — Metadata Format](https://docs.spring.io/spring-boot/specification/configuration-metadata/format.html): cấu trúc `groups`, `properties`, `hints`.
- [Spring Boot — Providing Manual Hints](https://docs.spring.io/spring-boot/specification/configuration-metadata/manual-hints.html): `values`, `providers` và Map hints.
- [Spring Boot — Annotation Processor](https://docs.spring.io/spring-boot/specification/configuration-metadata/annotation-processor.html): tạo metadata và additional metadata.
- [Spring Boot — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties): Bean registration, Binder và typed configuration.
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): nguồn giá trị thực và precedence.

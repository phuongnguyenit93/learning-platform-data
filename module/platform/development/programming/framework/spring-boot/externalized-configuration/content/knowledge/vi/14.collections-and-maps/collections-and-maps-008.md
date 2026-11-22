# Bảo toàn khóa Map đặc biệt bằng ký pháp dấu ngoặc vuông

## 1. Vấn đề: tên thuộc tính không phải lúc nào cũng là khóa Map cần giữ nguyên

Spring Boot cho phép liên kết cấu hình ngoài vào đối tượng Java thông qua `@ConfigurationProperties`. Với những trường kiểu `Map<K, V>`, mỗi mục trong file YAML hoặc `.properties` có thể trở thành một entry trong Map.

Điều này đơn giản khi khóa chỉ gồm chữ và số:

```yaml
routing:
  handlers:
    orders: orders-handler
    payments: payments-handler
```

Java:

```java
@ConfigurationProperties(prefix = "routing")
public record RoutingProperties(Map<String, String> handlers) {}
```

Khi được đăng ký và bind, `handlers` chứa hai khóa `orders` và `payments`.

Tuy nhiên, nhiều hệ thống cần dùng **khóa Map có ký tự đặc biệt**: tuyến HTTP `/api/v1`, tên đối tác `tenant@east`, đường dẫn `/public/**`, mã môi trường `us.east` hoặc tên chính sách `rate:premium`. Đây là dữ liệu có ý nghĩa; bỏ một ký tự có thể làm lookup sai hoàn toàn.

Ví dụ:

```yaml
routing:
  handlers:
    /api/v1: orders-handler
```

Người viết YAML có thể kỳ vọng Map giữ khóa `/api/v1`. Nhưng Spring Boot binder áp dụng các quy tắc về **tên thuộc tính**. Khi một Map key **không** được đặt trong ký pháp dấu ngoặc vuông `[ ]`, những ký tự không phải chữ, số, dấu `-` hoặc dấu `.` có thể bị loại bỏ khi binding.

Vì vậy, khóa như `/api/v1` có thể trở thành `apiv1`, làm câu lệnh Java sau trả về `null`:

```java
properties.handlers().get("/api/v1");
```

Để bảo toàn khóa gốc, cần viết:

```yaml
routing:
  handlers:
    "[/api/v1]": orders-handler
```

Sau binding, Map giữ đúng khóa `/api/v1`.

**Ý chính:** ký pháp `[key]` của Spring Boot dùng để nói với binder rằng *phần trong ngoặc là một khóa Map cần được bảo toàn*, thay vì để ký tự đặc biệt bị chuẩn hóa như thành phần của đường dẫn thuộc tính.

## 2. Ba lớp cú pháp phải phân biệt

Khi đọc một file YAML có Map, thực tế có ba tầng xử lý:

1. **Cú pháp YAML:** dấu hai chấm, mức thụt lề và dấu nháy biểu diễn dữ liệu trong tài liệu.
2. **Tên thuộc tính được Spring Boot tạo từ YAML:** cấu trúc lồng nhau được chuyển thành những tên thuộc tính để binder truy cập.
3. **Quy tắc Map binding:** binder diễn giải đường dẫn thuộc tính để xác định tên field và Map key.

Ví dụ:

```yaml
routing:
  handlers:
    "[/api/v1]": orders-handler
```

Phần `"[/api/v1]"` vừa là **YAML key có dấu nháy**, vừa chứa **ký pháp bảo toàn Map key cho Spring Boot**. Dấu nháy là để parser YAML hiểu phần này là một chuỗi; dấu ngoặc vuông là tín hiệu dành cho Spring Boot binder.

Sơ đồ:

```text
YAML:
  "[/api/v1]": orders-handler
            |
            v
YAML parser đọc chuỗi key: [/api/v1]
            |
            v
Spring Boot binder nhận dạng [ ... ]
            |
            v
Map key gốc: /api/v1
Map value:   orders-handler
```

Không nên nhầm rằng *chỉ cần đặt dấu nháy* là đủ. Nếu khai báo:

```yaml
routing:
  handlers:
    "/api/v1": orders-handler
```

dấu nháy bảo đảm YAML đọc đúng chuỗi `/api/v1`, nhưng **không** bật ký pháp `[ ]` của binder. Khóa vẫn có thể bị chuẩn hóa khi bind.

Ngược lại, nếu viết `[/api/v1]` mà không đặt trong dấu nháy ở vị trí key của YAML, parser có thể hiểu `[ ]` theo cú pháp collection của chính YAML. Tài liệu Spring Boot yêu cầu **bao cặp dấu ngoặc vuông bằng dấu nháy khi khai báo Map key trong YAML**.

## 3. Quy tắc chuẩn hóa khóa Map của binder

Spring Boot có cơ chế *relaxed binding*, giúp những tên thuộc tính như `max-attempts`, `maxAttempts` hoặc `max_attempts` được liên kết vào thành phần Java phù hợp. Cơ chế này có ích cho tên field, nhưng khi áp dụng với Map, có những trường hợp cần bảo toàn nguyên văn khóa.

Quy tắc quan trọng đối với Map key:

> Nếu một khóa Map không được bao bằng `[ ]`, các ký tự nằm ngoài nhóm chữ cái, chữ số, dấu gạch ngang `-` và dấu chấm `.` có thể bị loại bỏ trong quá trình diễn giải tên thuộc tính.

Bảng minh họa với Map giá trị scalar như `Map<String, String>`:

| Khóa muốn có trong Map | YAML key | Kết quả cần quan sát |
| --- | --- | --- |
| `orders` | `orders` | `orders` |
| `shipping-fast` | `shipping-fast` | `shipping-fast` |
| `/api/v1` | `"[/api/v1]"` | `/api/v1` |
| `tenant@east` | `"[tenant@east]"` | `tenant@east` |
| `/public/**` | `"[/public/**]"` | `/public/**` |
| `feature.beta` | `"[feature.beta]"` | `feature.beta` |
| `a_b` | `"[a_b]"` | `a_b` |

Với các ký tự thuộc nhóm đặc biệt như `/`, `@`, `*`, `_`, dùng ngoặc vuông để tránh làm thay đổi tên. Dấu chấm `.` có một ngoại lệ quan trọng khi value là scalar; phần riêng về dấu chấm sẽ giải thích vì sao vẫn nên dùng ngoặc vuông nếu cần một cấu hình ổn định khi kiểu Map thay đổi.

Không phải mọi vấn đề về tên thuộc tính đều là lỗi. Ví dụ `max-attempts` ánh xạ tới thành phần Java `maxAttempts` là điều **mong muốn** của relaxed binding. Ngược lại, nếu Map key thực sự là một biểu thức route `/api/v1` thì biến nó thành `apiv1` là điều **không mong muốn**.

## 4. Cú pháp trong application.properties

Ở file `.properties`, ký pháp bảo toàn khóa được viết trực tiếp trong tên thuộc tính:

```properties
routing.handlers[/api/v1]=orders-handler
routing.handlers[tenant@east]=tenant-handler
routing.handlers[/public/**]=static-handler
routing.handlers[feature.beta]=beta-handler
routing.handlers[shipping-fast]=fast-handler
```

Ở ví dụ này:

- `routing` là tiền tố của lớp `@ConfigurationProperties`.
- `handlers` là tên trường `Map<String, String>` trong Java.
- `[... ]` xác định phần nằm trong ngoặc là một khóa Map cần giữ nguyên.
- Dấu `=` phân tách tên thuộc tính và giá trị theo cú pháp file properties.

Đặc biệt, đây **không phải** cú pháp chỉ số list. Hai trường hợp có thể cùng sử dụng ngoặc vuông nhưng mang ý nghĩa khác nhau tùy kiểu Java đích:

```properties
workers[0].name=first
routing.handlers[/api/v1]=orders-handler
```

- Với `List<Worker> workers`, `[0]` biểu diễn phần tử chỉ số 0.
- Với `Map<String, String> handlers`, `[/api/v1]` biểu diễn khóa chuỗi `/api/v1`.

Binder dựa vào kiểu dữ liệu mà lớp Java khai báo để xử lý thích hợp.

### Không có dấu ngoặc sẽ xảy ra chuyện gì?

So sánh:

```properties
# Không bảo toàn:
routing.handlers./api/v1=orders-handler

# Bảo toàn:
routing.handlers[/api/v1]=orders-handler
```

Ở dòng đầu, ký tự slash có thể bị loại bỏ trong tên Map key; với ví dụ này, khóa scalar sẽ trở thành `apiv1`. Ở dòng sau, khóa được giữ là `/api/v1`.

Vì vậy, khi sau binding bạn gọi:

```java
properties.handlers().containsKey("/api/v1")
```

dòng có ngoặc vuông mới biểu diễn đúng ý định bảo toàn tên đường dẫn.

Trong file properties, đừng tùy tiện thêm escape hoặc dấu nháy quanh toàn bộ `[key]` theo thói quen YAML. File `.properties` và YAML có cú pháp phân tích khác nhau.

## 5. Cú pháp trong application.yml

YAML có cấu trúc phân cấp theo thụt lề:

```yaml
routing:
  handlers:
    "[/api/v1]": orders-handler
    "[tenant@east]": tenant-handler
    "[/public/**]": static-handler
    "[feature.beta]": beta-handler
    "[shipping-fast]": fast-handler
```

Các key trong ví dụ được bao bởi dấu nháy kép; có thể dùng dấu nháy đơn phù hợp với cú pháp YAML. Với cặp ngoặc vuông, dấu nháy giúp parser YAML coi toàn bộ key là một chuỗi.

Điểm cần nhớ là **dấu nháy bao ngoài cặp ngoặc**, chứ không đặt ngoặc vuông ngoài một chuỗi đã được trích dẫn theo cách tự nghĩ:

```yaml
# Cách viết rõ ràng:
"[/api/v1]": orders-handler
```

Khi đặt trong YAML đầy đủ, các key này phải nằm đúng dưới field Map, ví dụ `routing.handlers`.

### Vì sao không thể chỉ trích dẫn khóa gốc?

Hai dòng trông gần giống nhưng ý nghĩa khác nhau:

```yaml
routing:
  handlers:
    "/api/v1": might-change
    "[/api/v2]": preserved
```

Ở dòng đầu, dấu nháy chỉ xử lý cú pháp YAML. Binder không thấy dạng `[... ]`. Ở dòng thứ hai, binder nhận dạng ký pháp bảo toàn và có thể giữ nguyên `/api/v2`.

Không nên dùng cả hai cách cho cùng một key thực tế trong cùng file vì khóa sau chuẩn hóa có thể đè lên khóa trước hoặc tạo kết quả khó dự đoán. Hãy chọn một quy ước nhất quán: **mọi Map key chứa ký tự đặc biệt đều dùng dạng `"[...]"`**.

## 6. Ví dụ Spring Boot hoàn chỉnh với Map<String, String>

Tạo một dự án Spring Boot 3.x, Java 17 trở lên và dependency cơ bản `spring-boot-starter`. Ta không cần mở HTTP server; chương trình chỉ in các Map key đã được bind.

### 6.1. Cấu trúc thư mục

```text
map-key-lab/
└── src/main/
    ├── java/com/example/mapkey/
    │   ├── MapKeyApplication.java
    │   └── RoutingProperties.java
    └── resources/
        └── application.yml
```

### 6.2. File application.yml

```yaml
routing:
  handlers:
    "[/api/v1]": orders-handler
    "[tenant@east]": east-handler
    "[feature.beta]": beta-handler
    normal: default-handler
```

### 6.3. Lớp @ConfigurationProperties

`RoutingProperties.java`:

```java
package com.example.mapkey;

import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "routing")
public record RoutingProperties(Map<String, String> handlers) {
}
```

`RoutingProperties` là một record để Spring Boot bind từ các thuộc tính bắt đầu bằng `routing`. Trường `handlers` là một Map có khóa `String` và giá trị `String`.

Với record dùng constructor binding của Spring Boot 3, không cần tạo setter cho từng entry. Cũng không cần thêm `@Component` nếu ta đăng ký record qua cơ chế cấu hình properties chuyên dụng.

### 6.4. Lớp khởi động và quan sát

`MapKeyApplication.java`:

```java
package com.example.mapkey;

import java.util.Map;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableConfigurationProperties(RoutingProperties.class)
public class MapKeyApplication {

    public static void main(String[] args) {
        SpringApplication.run(MapKeyApplication.class, args);
    }

    @Bean
    ApplicationRunner showMap(RoutingProperties properties) {
        return args -> {
            System.out.println("=== MAP KEY LAB ===");

            for (Map.Entry<String, String> entry
                    : properties.handlers().entrySet()) {
                System.out.println(
                    "[" + entry.getKey() + "] => " + entry.getValue()
                );
            }

            System.out.println(
                "lookup /api/v1 = "
                + properties.handlers().get("/api/v1")
            );

            System.out.println(
                "lookup tenant@east = "
                + properties.handlers().get("tenant@east")
            );
        };
    }
}
```

`@EnableConfigurationProperties(RoutingProperties.class)` đăng ký bean cấu hình để binder tạo Map. `ApplicationRunner` chỉ đọc bean đã được dựng xong; không có network call hoặc side effect vận hành.

Sau khi đóng gói bằng Maven/Gradle phù hợp, chạy JAR thực thi. Trong lệnh dưới đây, `app.jar` là tên minh họa:

```bash
java -jar app.jar
```

Các Map entry được duyệt **không nên phụ thuộc vào thứ tự hiển thị cụ thể**, nhưng hai phép lookup có kết quả mong đợi:

```text
lookup /api/v1 = orders-handler
lookup tenant@east = east-handler
```

Ngoài ra, Map có khóa `feature.beta` và `normal`. Mục đích của ví dụ là xác nhận **chuỗi khóa gốc** sau binding, chứ không xác nhận thứ tự in hoặc cấu hình HTTP routing thật.

## 7. Thực nghiệm A: bỏ ngoặc vuông rồi so sánh

Đổi YAML thành:

```yaml
routing:
  handlers:
    "/api/v1": orders-handler
    "tenant@east": east-handler
    "feature.beta": beta-handler
    normal: default-handler
```

Không sửa Java. Đóng gói và chạy lại ứng dụng.

Với `Map<String, String>`, các ký tự `/` và `@` nằm ngoài tập ký tự được bảo toàn khi không có `[ ]`, nên các tên khóa tương ứng có thể trở thành:

```text
/api/v1     -> apiv1
tenant@east -> tenanteast
```

Kết quả của:

```java
properties.handlers().get("/api/v1");
properties.handlers().get("tenant@east");
```

có thể là `null` dù Map vẫn có các entry dưới tên **đã chuẩn hóa**. Lỗi này rất dễ khiến người đọc nghĩ “Spring không nạp YAML”, trong khi sự thật là YAML đã được nạp nhưng **tên khóa Map không còn như mong muốn**.

Khóa `feature.beta` lại khác: dấu chấm là một ký tự được xử lý đặc biệt tùy kiểu value. Với Map scalar ở thí nghiệm này, khóa có dấu chấm vẫn có thể được bảo toàn ngay khi không có ngoặc. Đây là ngoại lệ sẽ được giải thích ở phần kế tiếp.

### Thực nghiệm B: giữ ngoặc vuông

Đổi lại:

```yaml
routing:
  handlers:
    "[/api/v1]": orders-handler
    "[tenant@east]": east-handler
    "[feature.beta]": beta-handler
    normal: default-handler
```

Kỳ vọng:

```text
handlers.containsKey("/api/v1")     == true
handlers.containsKey("tenant@east") == true
handlers.containsKey("feature.beta")== true
handlers.containsKey("normal")      == true
```

Cả bốn key đều được sử dụng đúng như yêu cầu. Ngoặc vuông không được giữ lại như một phần key trong Java; nó được binder hiểu là cú pháp bảo toàn.

## 8. Ngoại lệ quan trọng: dấu chấm trong Map có giá trị scalar

Không phải mọi dấu `.` đều đòi hỏi ngoặc vuông. Trong Spring Boot, hành vi của dấu chấm trong Map key phụ thuộc **kiểu giá trị của Map**.

Với Map có giá trị scalar như `Map<String, String>`:

```properties
labels.names.a.b=hello
```

Nếu Java khai báo:

```java
@ConfigurationProperties(prefix = "labels")
public record LabelProperties(Map<String, String> names) {}
```

thì binder có thể giữ `a.b` làm **một key** và liên kết thành:

```text
names = { "a.b" : "hello" }
```

Nguyên nhân: với đích là một giá trị đơn giản `String`, binder có thể hiểu phần còn lại của tên thuộc tính là key của Map, bao gồm dấu chấm.

Các kiểu value scalar được tài liệu Spring Boot nêu bao gồm enum và những kiểu trong package `java.lang` (ngoại trừ `Object`). Nhưng ngay khi value là đối tượng phức tạp hoặc `Object`, cách hiểu dấu chấm có thể thay đổi.

Do đó, đối với `Map<String,String>`, đôi khi cả hai cách dưới đây cùng giữ được key `a.b`:

```properties
labels.names.a.b=hello
labels.names[a.b]=hello
```

Không nên đồng thời khai báo cả hai dòng cho cùng khóa trong ứng dụng thật. Đây là hai cách minh họa cùng mục tiêu. Nếu muốn bảo toàn chính xác khóa xuyên suốt quá trình thay đổi kiểu Map, viết `[a.b]` là lựa chọn tường minh hơn.

## 9. Map<String, Object>: dấu chấm có thể biến thành cấu trúc lồng nhau

Xét thuộc tính:

```properties
feature.flags.a.b=enabled
```

Nếu Java khai báo:

```java
@ConfigurationProperties(prefix = "feature")
public record FeatureProperties(
        Map<String, Object> flags
) {}
```

thì đường dẫn `a.b` có thể được hiểu thành **hai cấp**: khóa `a` chứa một object/map có khóa `b`. Ta có kết quả tương đương:

```text
flags = {
    "a": {
        "b": "enabled"
    }
}
```

Trong trường hợp đó:

```java
properties.flags().get("a.b")
```

không phải phép tra cứu thích hợp vì trong Map ở cấp đầu, key là `a` thay vì `a.b`.

Để giữ `a.b` thành **một khóa duy nhất**, dùng bracket notation:

```properties
feature.flags[a.b]=enabled
```

Hoặc YAML:

```yaml
feature:
  flags:
    "[a.b]": enabled
```

Kết quả mong đợi khi bind vào `Map<String, Object>`:

```text
flags = { "a.b" : "enabled" }
```

Giờ:

```java
properties.flags().get("a.b")
```

có thể trả về giá trị `enabled`.

Sự phân biệt cần nhớ:

| Khai báo | Kiểu đích | Kết quả của dấu chấm |
| --- | --- | --- |
| `feature.flags.a.b=enabled` | `Map<String, String>` | Key `a.b` được giữ do value scalar |
| `feature.flags.a.b=enabled` | `Map<String, Object>` | Thường là cấu trúc `a → b` |
| `feature.flags[a.b]=enabled` | `Map<String, Object>` | Key literal `a.b` được bảo toàn |
| YAML `"[a.b]": enabled` | `Map<String, Object>` | Key literal `a.b` được bảo toàn |

Nếu value là một lớp Java lồng nhau như `RuleProperties`, đường dẫn sau Map key có thể tiếp tục chỉ tới field của đối tượng đó. Vì vậy, cần phân biệt **dấu chấm nằm trong tên key** và **dấu chấm dùng để đi vào thuộc tính lồng nhau**.

## 10. Map<String, Rule>: phân biệt tên key với đường dẫn tới field

Giả sử mỗi tenant có quy tắc riêng:

```java
public record Rule(
        boolean enabled,
        int limit
) {}

@ConfigurationProperties(prefix = "tenants")
public record TenantProperties(
        Map<String, Rule> rules
) {}
```

Ta muốn giữ một tên tenant literal `team.east`. YAML:

```yaml
tenants:
  rules:
    "[team.east]":
      enabled: true
      limit: 20
    "[team@west]":
      enabled: false
      limit: 10
```

Binder có thể tạo hai entry:

```text
rules["team.east"] = Rule(true, 20)
rules["team@west"] = Rule(false, 10)
```

Cú pháp file `.properties` tương đương về cấu trúc:

```properties
tenants.rules[team.east].enabled=true
tenants.rules[team.east].limit=20
tenants.rules[team@west].enabled=false
tenants.rules[team@west].limit=10
```

Ở đây:

- `[team.east]` bảo toàn nguyên văn tên key của Map.
- `.enabled` và `.limit` **nằm ngoài cặp ngoặc**, nên là đường dẫn tới các field của `Rule`.

Nếu viết:

```properties
tenants.rules.team.east.enabled=true
```

mà không dùng ngoặc, binder có thể diễn giải `team` là key hoặc một thành phần của đường dẫn khác thay vì key literal `team.east`. Trường hợp Map value là đối tượng phức tạp càng cần diễn đạt ranh giới key rõ ràng.

### Vì sao không đặt toàn bộ đường dẫn trong ngoặc?

So sánh:

```properties
tenants.rules[team.east].enabled=true
tenants.rules[team.east.enabled]=true
```

Dòng thứ nhất có key `team.east`, rồi truy cập field `enabled` của `Rule`. Dòng thứ hai đặt cả chuỗi `team.east.enabled` vào key, không cung cấp phần đường dẫn tới field như dòng thứ nhất. Với `Map<String, Rule>`, đây không phải cấu trúc tương đương.

Hãy đặt ngoặc đúng **quanh phần muốn làm một Map key**, không quanh tất cả tên thuộc tính.

## 11. Khi ký tự đặc biệt xuất hiện trong tên route

Một trường hợp dễ hiểu là bảng cấu hình route:

```yaml
gateway:
  route-to-service:
    "[/api/v1/orders]": orders-service
    "[/api/v1/payments]": payments-service
    "[/assets/**]": static-service
    "[/users/{id}]": user-service
```

Nếu Java dùng:

```java
@ConfigurationProperties(prefix = "gateway")
public record GatewayProperties(
        Map<String, String> routeToService
) {}
```

thì các key có thể giữ nguyên như:

```text
/api/v1/orders
/api/v1/payments
/assets/**
/users/{id}
```

Các dấu `/`, `*`, `{`, `}` đều là một phần có ý nghĩa của key chuỗi và cần được bảo toàn.

**Quan trọng:** việc bind những chuỗi này **không tự đăng ký HTTP routes**. Đây chỉ là dữ liệu trong một Map. Ứng dụng cần một thành phần đọc Map, kiểm tra quy tắc và thiết lập router/gateway phù hợp. Spring Boot binder không biết các chuỗi đang biểu diễn URL pattern, regex, mã đối tác hay tên feature.

Tương tự, một key dạng `/assets/**` có thể cần được kiểm tra riêng để chắc chắn pattern hợp lệ với router đang dùng. Ngoặc vuông chỉ giữ ký tự, không kiểm tra cú pháp của pattern.

### Một lỗi dễ khó phát hiện: hai key đụng nhau sau chuẩn hóa

Giả sử bạn vô tình khai báo:

```yaml
gateway:
  route-to-service:
    "/api/v1": old-service
    "apiv1": new-service
```

Khi ký tự `/` bị loại bỏ ở key đầu tiên, cả hai có thể trở thành cùng tên `apiv1` trong quá trình bind. Trong một nguồn cấu hình như vậy, có thể xuất hiện hành vi ghi đè hoặc kết quả khó thấy ngay từ YAML. Đây là lỗi cấu hình nguy hiểm vì bảng ánh xạ không còn phân biệt hai tuyến.

Nếu ý định là hai key khác nhau, dùng:

```yaml
gateway:
  route-to-service:
    "[/api/v1]": old-service
    "apiv1": new-service
```

Khi đó các key literal khác nhau và có thể cùng tồn tại.

## 12. Tương tác với relaxed binding

**Relaxed binding** giúp đối chiếu những biến thể tên thuộc tính với tên field Java. Ví dụ `route-to-service` trong YAML có thể bind vào field `routeToService`.

Nhưng không nên cho rằng mọi sự thay đổi tên Map key cũng được mong muốn:

```text
gateway.route-to-service
            |
            +-- field Java: routeToService
            |   (relaxed binding có ích)
            |
            +-- key trong Map: /api/v1
                (cần bảo toàn nguyên văn)
```

Hai vai trò khác nhau:

- Tên field `route-to-service` có thể được binder chuẩn hóa để khớp `routeToService`.
- Dữ liệu key `/api/v1` không nên bị biến thành tên khác vì code nghiệp vụ dùng key đó để tra cứu.

Một quy ước tốt là **sử dụng tên field cấu hình canonical, nhưng bảo toàn các key dữ liệu đặc biệt**.

Ví dụ:

```yaml
tenant-routing:
  destination-map:
    "[tenant@north]": https://north.example.invalid
    "[tenant@west]": https://west.example.invalid
```

Lớp:

```java
@ConfigurationProperties(prefix = "tenant-routing")
public record TenantRoutingProperties(
        Map<String, String> destinationMap
) {}
```

- Prefix `tenant-routing` là tên nhóm cấu hình.
- Field `destination-map` khớp `destinationMap`.
- Key `tenant@north` và `tenant@west` được giữ nguyên vì được bao bởi ngoặc.

Đừng áp dụng cùng một thao tác chuẩn hóa cho mọi tầng rồi tự suy đoán kết quả.

## 13. Một lỗi YAML phổ biến: nhầm key có ngoặc với danh sách

Trong YAML, dấu `[ ]` có cú pháp riêng cho flow sequence. Điều này khiến key không trích dẫn có thể bị phân tích khác mong muốn.

Không viết:

```yaml
routing:
  handlers:
    [/api/v1]: orders-handler
```

và kỳ vọng parser luôn coi `[/api/v1]` là chuỗi literal. Theo hướng dẫn của Spring Boot, khi dùng bracket notation trong YAML, **trích dẫn cả chuỗi có dấu ngoặc**:

```yaml
routing:
  handlers:
    "[/api/v1]": orders-handler
```

Ngoài ra, dấu `:`, `#`, `*`, `?` và những ký tự đặc biệt khác có ý nghĩa trong YAML ở các ngữ cảnh nhất định. Ký pháp bảo toàn Map key và dấu nháy giúp mục đích cấu hình rõ hơn, nhưng bạn vẫn cần viết YAML hợp lệ, đúng mức thụt lề và đúng cấu trúc của field.

Ví dụ key có ký tự `#`:

```yaml
routing:
  handlers:
    "[policy#blue]": blue-handler
```

`#` ở đây là một phần tên Map key, không phải bắt đầu comment YAML vì nó nằm trong chuỗi có dấu nháy.

### Dấu nháy đơn và dấu nháy kép

Hai cách thường được YAML hiểu như chuỗi:

```yaml
"[/v1/orders]": orders-handler
'[/v1/orders]': orders-handler
```

Chọn một phong cách thống nhất. Với các key có ký tự escape phức tạp như dấu gạch chéo ngược, cần lưu ý quy tắc escape khác nhau giữa hai loại nháy của YAML; tránh thay đổi cách trích dẫn khi chưa hiểu đúng chuỗi kết quả.

## 14. Ký pháp Map không thay đổi kiểu value

Dấu ngoặc vuông chỉ xử lý **key**. Nó không làm mọi value trở thành `String` hoặc làm hỏng quá trình chuyển kiểu.

Ví dụ:

```yaml
limits:
  per-path:
    "[/api/v1/orders]": 50
    "[/api/v1/payments]": 20
```

Lớp:

```java
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "limits")
public record LimitProperties(
        Map<String, Integer> perPath
) {}
```

Sau binding, chương trình có thể đọc:

```java
Integer maxOrders = properties.perPath().get("/api/v1/orders");
```

và nhận `50` dưới dạng `Integer`.

Tương tự, với `Map<String, Duration>`, các giá trị `2s`, `500ms` có thể được chuyển đổi thành thời lượng bởi cơ chế binding Spring Boot tương ứng. Nhưng nếu value không thể chuyển sang kiểu đích, đó là **lỗi binding/conversion value**, không phải lỗi ngoặc vuông của key.

Vì vậy, khi Map nhận sai dữ liệu, kiểm tra hai câu hỏi độc lập:

1. **Key có giữ nguyên không?** Xem `Map.keySet()` và bracket notation.
2. **Value có chuyển đúng kiểu không?** Xem kiểu `V`, converter và nội dung thuộc tính.

Một khóa được bảo toàn đúng vẫn có thể đi cùng một value không hợp lệ.

## 15. Environment và Map binding không phải một phép tra cứu giống nhau

Một cách kiểm tra cấu hình là:

```java
String value = environment.getProperty(
        "routing.handlers[/api/v1]");
```

Cách khác là:

```java
String value = routingProperties.handlers().get("/api/v1");
```

Hai cơ chế này có liên hệ nhưng không nên coi chúng là luôn tương đương về cách tìm và chuẩn hóa khóa:

- `Environment.getProperty(...)` tra cứu một tên thuộc tính từ các `PropertySource`.
- `@ConfigurationProperties` Binder duyệt và diễn giải các tên thuộc tính để xây object/Map theo kiểu đích.

Điều ta cần kiểm chứng trong bài này là **key sau khi bind vào Map**, không chỉ sự tồn tại của một chuỗi tên trong một nguồn cấu hình.

Khi chẩn đoán, nên in những key không nhạy cảm:

```java
System.out.println(properties.handlers().keySet());
```

và kiểm tra lookup cụ thể:

```java
System.out.println(
    properties.handlers().containsKey("/api/v1")
);
```

Đừng chỉ in value rồi suy ra key đã đúng. Có thể hai tên khóa khác nhau dẫn tới cùng một value.

## 16. Tác động của file theo profile và thứ tự ưu tiên

Ký pháp `[key]` không tạo một mức ưu tiên cấu hình mới. Nó chỉ yêu cầu giữ nguyên Map key. Nếu cùng một key xuất hiện ở nhiều nguồn cấu hình, Spring Boot vẫn áp dụng quy tắc nguồn và binding của mình.

Ví dụ file chung:

```yaml
# application.yml
routing:
  handlers:
    "[/api/v1]": local-handler
    "[/health]": health-handler
```

File theo profile:

```yaml
# application-prod.yml
routing:
  handlers:
    "[/api/v1]": prod-handler
```

Khi chạy:

```bash
java -jar app.jar --spring.profiles.active=prod
```

và không có nguồn ưu tiên cao hơn, Map có thể nhận:

```text
/api/v1 -> prod-handler
/health -> health-handler
```

Giá trị của entry `/api/v1` được ghi đè từ file profile, còn entry `/health` vẫn được giữ từ nguồn chung. Đối với Map binding, các entry từ nhiều nguồn có thể được kết hợp theo quy tắc tương ứng, khác với cơ chế thay nguyên list ở một số tình huống.

Điều này hữu ích khi chỉ một tuyến khác giữa môi trường phát triển và production. Nhưng phải dùng nhất quán key `"[/api/v1]"` ở cả hai file. Nếu một file vô tình viết `"/api/v1"` không ngoặc, binder có thể tạo **hai key khác nhau** (`/api/v1` và `apiv1`) thay vì ghi đè cùng một entry.

Đây là một lỗi khiến người triển khai nghĩ “file prod không override”, trong khi nguyên nhân thực tế là **key đã biến dạng**.

## 17. Ghi đè bằng tham số dòng lệnh

Đối với một key đặc biệt, có thể cung cấp thuộc tính tương ứng qua đối số dòng lệnh của Spring Boot:

```bash
java -jar app.jar '--routing.handlers[/api/v1]=runtime-handler'
```

Dùng dấu nháy đơn trong Bash/PowerShell để shell không diễn giải các ký tự đặc biệt như dấu ngoặc vuông, dấu `*` hoặc những ký hiệu khác trước khi Java nhận chuỗi.

Trên Windows `cmd.exe` có thể dùng dấu nháy kép quanh đối số:

```bat
java -jar app.jar "--routing.handlers[/api/v1]=runtime-handler"
```

Ví dụ này minh họa cách cấp property có key đặc biệt qua command-line arguments. Nếu dùng nền tảng chạy JAR với wrapper, Docker, Kubernetes hoặc hệ thống CI/CD, cần đảm bảo chuỗi đến ứng dụng vẫn chứa đúng cặp dấu ngoặc.

Dù dùng file hay command-line, sau khi bind hãy quan sát `properties.handlers().get("/api/v1")` để xác nhận giá trị có hiệu lực.

### Vì sao không luôn dùng biến môi trường?

Các hệ điều hành và shell thường giới hạn ký tự có thể xuất hiện trong **tên biến môi trường**. Tên biến kiểu:

```text
ROUTING_HANDLERS[/api/v1]
```

không phải tên hợp lệ trong nhiều shell và không tuân theo quy ước biến môi trường thông dụng. Spring Boot còn áp dụng quy tắc riêng khi bind các biến môi trường vào Map, bao gồm việc tên Map key có thể bị chuyển thành chữ thường.

Vì vậy, đối với key chứa dấu `/`, `@`, `*` hoặc muốn giữ chính xác chữ hoa/thường, **file cấu hình có ngoặc vuông** hoặc một nguồn cấu hình hỗ trợ tên thuộc tính tương ứng thường dễ kiểm soát hơn. Không nên cố truyền một tên biến môi trường có ký tự bất hợp lệ rồi kết luận binder không hỗ trợ Map key đặc biệt.

Nếu yêu cầu triển khai buộc phải dùng biến môi trường, cân nhắc cấp một JSON blob hoặc một cấu trúc cấu hình được framework/nền tảng hỗ trợ và kiểm tra cách nó được đưa vào Spring Boot. Không có quy tắc rằng mọi Map key tùy ý đều có thể biểu diễn trực tiếp thành tên biến môi trường thông thường.

## 18. Phân biệt Map key và tên thuộc tính lồng nhau trong YAML

Một ứng dụng có thể trộn Map và object lồng nhau:

```yaml
integrations:
  vendors:
    "[vendor@north]":
      endpoint: https://north.example.invalid
      timeout: 2s
    "[vendor@west]":
      endpoint: https://west.example.invalid
      timeout: 5s
```

Lớp Java:

```java
import java.net.URI;
import java.time.Duration;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "integrations")
public record IntegrationProperties(
        Map<String, Vendor> vendors
) {
    public record Vendor(
            URI endpoint,
            Duration timeout
    ) {}
}
```

Các phần tử có vai trò khác nhau:

```text
integrations             prefix
  |
  +-- vendors            field Map<String, Vendor>
          |
          +-- vendor@north   Map key (phải bảo toàn)
                 |
                 +-- endpoint   field trong Vendor
                 +-- timeout    field trong Vendor
```

Spring binder chuyển value `https://north.example.invalid` sang `URI`, `2s` sang `Duration`, rồi đặt object `Vendor` ở key `vendor@north`. Các field `endpoint`, `timeout` không cần ngoặc vì chúng là tên thuộc tính Java bình thường.

Khi muốn xem thông số:

```java
IntegrationProperties.Vendor vendor =
    properties.vendors().get("vendor@north");

System.out.println(vendor.timeout());
```

Nếu code truyền một tên key khác, ví dụ `"vendornorth"`, Map không tự biết đó là cùng một vendor. Bracket notation giúp làm rõ hợp đồng key giữa dữ liệu cấu hình và code lookup.

## 19. Test binding riêng cho khóa đặc biệt

Có thể kiểm chứng Map key mà không cần chạy cả ứng dụng bằng cách sử dụng `ApplicationContextRunner` của Spring Boot Test.

Giả sử record:

```java
package com.example.mapkey;

import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "routing")
public record RoutingProperties(Map<String, String> handlers) {}
```

Một test đơn giản dùng JUnit 5:

```java
package com.example.mapkey;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class RoutingPropertiesTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withUserConfiguration(TestConfig.class);

    @Test
    void preservesSpecialMapKeys() {
        runner.withPropertyValues(
                "routing.handlers[/api/v1]=orders-handler",
                "routing.handlers[tenant@east]=east-handler",
                "routing.handlers[feature.beta]=beta-handler"
        ).run(context -> {
            RoutingProperties props =
                context.getBean(RoutingProperties.class);

            assertThat(props.handlers())
                .containsEntry("/api/v1", "orders-handler")
                .containsEntry("tenant@east", "east-handler")
                .containsEntry("feature.beta", "beta-handler");
        });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(RoutingProperties.class)
    static class TestConfig {
    }
}
```

Test này kiểm tra **hợp đồng binding**:

1. Binder có tạo bean đúng kiểu không?
2. Map có chứa key nguyên văn hay không?
3. Value có tương ứng với key mong đợi không?

Đây không phải test router, HTTP request hay service nghiệp vụ. Nếu test thất bại, ta có thể tập trung vào cú pháp property và cơ chế bind thay vì debugging cả ứng dụng.

Với YAML, có thể sử dụng `@SpringBootTest` nạp tệp `application.yml` thực tế hoặc một context test phù hợp, sau đó assert `containsKey("/api/v1")`. Dùng test cấu hình riêng sẽ giúp nhận ra lỗi Map key ngay trong pipeline build.

## 20. Kiểm thử ngoại lệ dấu chấm theo kiểu Map

Để quan sát sự khác biệt giữa Map scalar và Map object, dùng hai cấu hình tách biệt.

### Trường hợp 1: Map<String, String>

```properties
demo.labels.a.b=value-one
```

Java:

```java
@ConfigurationProperties(prefix = "demo")
public record DemoProperties(
        Map<String, String> labels
) {}
```

Trong trường hợp này có thể nhận:

```text
labels["a.b"] = "value-one"
```

### Trường hợp 2: Map<String, Object>

```properties
demo.options.a.b=value-two
```

Java:

```java
@ConfigurationProperties(prefix = "demo")
public record DemoProperties(
        Map<String, Object> options
) {}
```

Ở đây binder có thể diễn giải thành:

```text
options["a"] = { "b": "value-two" }
```

Nếu muốn:

```text
options["a.b"] = "value-two"
```

thì khai báo:

```properties
demo.options[a.b]=value-two
```

Đây là lý do **không thể chỉ nhớ “dấu chấm luôn được giữ”**. Quy tắc phụ thuộc kiểu value. Khi các tên key đến từ bên ngoài và cần giữ chính xác, ngoặc vuông là cách trình bày ranh giới key tường minh.

## 21. Các lỗi thường gặp

### 21.1. Chỉ đặt dấu nháy mà không đặt ngoặc

```yaml
routes:
  names:
    "/v1/orders": orders
```

YAML có thể đọc đúng key string, nhưng Spring Boot binder vẫn có thể bỏ ký tự `/`. Sửa:

```yaml
routes:
  names:
    "[/v1/orders]": orders
```

### 21.2. Đặt ngoặc nhưng quên dấu nháy trong YAML

```yaml
routes:
  names:
    [/v1/orders]: orders
```

Không tuân thủ cách khai báo Map key có ngoặc được Spring Boot hướng dẫn cho YAML. Sửa thành `"[/v1/orders]"` hoặc `'[/v1/orders]'`.

### 21.3. Bao sai phần của đường dẫn

```properties
tenants.rules[team.east.enabled]=true
```

Nếu Java cần `Map<String, Rule>` với key `team.east` và field `enabled`, phải viết:

```properties
tenants.rules[team.east].enabled=true
```

### 21.4. Thấy Map khác dự đoán rồi đổ lỗi cho YAML không được nạp

Hãy kiểm tra `keySet()`. Một value vẫn có thể hiện diện nhưng được gắn với key đã chuẩn hóa như `apiv1` thay vì `/api/v1`.

### 21.5. Coi key có dấu chấm là một quy tắc duy nhất

Với `Map<String, String>`, `a.b` có thể được giữ mà không cần `[ ]`. Với `Map<String, Object>` hoặc kiểu value phức tạp, `a.b` có thể trở thành đường dẫn lồng nhau. Đọc kiểu Java trước khi giải thích kết quả.

### 21.6. Nhầm Map với List

`values[0]` với `List` là truy cập vị trí; `values[0]` với `Map<String,String>` có thể là key chuỗi `"0"` theo cách binder diễn giải kiểu đích. Không quyết định cú pháp chỉ bằng nhìn dấu ngoặc; hãy nhìn class properties.

### 21.7. Nghĩ ký pháp [key] bảo vệ dữ liệu nhạy cảm

Ký pháp này không mã hóa key/value, không giới hạn quyền truy cập và không bảo đảm an toàn cho route pattern. Với key hoặc value nhạy cảm, cần cơ chế bảo vệ phù hợp và không in chúng ra log chẩn đoán.

### 21.8. Nhầm việc override entry với đổi tên key

Nếu file chung dùng `"[/api/v1]"` còn file prod dùng `"/api/v1"` không ngoặc, hai định danh có thể khác nhau sau binding. Dùng cùng ký pháp cho mọi nguồn nếu ý định là override một entry.

### 21.9. Dùng tên biến môi trường chứa dấu đặc biệt như một property key

Không phải shell nào cũng cho phép ký tự `/`, `[`, `]` hoặc `@` trong tên biến. Nếu cần giữ key chính xác, lựa chọn một nguồn cấu hình hỗ trợ cú pháp đó thay vì suy đoán mapping môi trường sẽ bảo toàn mọi ký tự.

### 21.10. Lạm dụng Map<String,Object> cho mọi giá trị

`Map<String,Object>` rất linh hoạt nhưng có thể khiến việc phân biệt key có dấu chấm với cấu trúc nested trở nên khó đọc. Nếu dữ liệu có schema ổn định, cân nhắc `Map<String, Rule>` hoặc một lớp cấu hình lồng nhau có kiểu. Nếu chỉ cần ánh xạ chuỗi sang chuỗi, `Map<String,String>` là hợp đồng đơn giản hơn.

## 22. Khi nào nên dùng Map và khi nào nên dùng class cố định?

Dùng `Map` khi tập khóa thực sự là dữ liệu động:

- Tên tenant được bổ sung qua deployment.
- Các route path là tập có thể mở rộng.
- Mã vùng địa lý hoặc nhóm đối tác không cố định trong lớp Java.
- Bảng ánh xạ tên alias sang endpoint hoặc policy.

Dùng class hoặc record có field tường minh khi tập trường đã có cấu trúc cố định:

```java
public record RetryPolicy(
        int maxAttempts,
        Duration backoff
) {}
```

Đừng thay mọi field của `RetryPolicy` bằng `Map<String,Object>` chỉ để tránh khai báo kiểu; như vậy mất đi một phần lợi thế của type-safe binding và dễ gây lỗi runtime.

Với cấu trúc “tên tenant động, nhưng mỗi tenant có chính sách cố định”, lựa chọn thường hợp lý là:

```java
Map<String, RetryPolicy> tenantPolicies
```

Khi đó bracket notation giữ chính xác key tenant, còn Spring Boot binder liên kết các field của `RetryPolicy` theo schema có kiểu.

## 23. Cách chẩn đoán theo từng bước

Giả sử code:

```java
String handler = props.handlers().get("/api/v1");
```

trả về `null`.

**Bước 1 — Xem kiểu Map.** Có thật là `Map<String, String>` hay một Map value phức tạp? Kiểu value quyết định cách binder xử lý dấu chấm.

**Bước 2 — In các key vô hại.** Xem `props.handlers().keySet()`. Nếu thấy `apiv1`, vấn đề nằm ở khâu bảo toàn key.

**Bước 3 — Kiểm tra chính tả của key.** `"/api/v1"` trong YAML đã được viết thành `"[/api/v1]"` chưa? Có thiếu dấu ngoặc hoặc dấu nháy không?

**Bước 4 — Kiểm tra prefix và tên field.** Nếu Java dùng `@ConfigurationProperties(prefix="routing")` và field `handlers` thì YAML cần nằm dưới `routing.handlers`. Trường hợp key không xuất hiện trong Map có thể do sai prefix chứ không phải do dấu ngoặc.

**Bước 5 — Kiểm tra môi trường đang hoạt động.** Có `application-prod.yml`, file cấu hình bên ngoài hoặc đối số dòng lệnh ghi đè entry đó không? Những file khác nhau có khai báo key bằng cùng ký pháp không?

**Bước 6 — Kiểm tra lỗi chuyển value.** Nếu Map value là `Integer`, `Duration` hay một record, liệu các giá trị được cấp có đúng kiểu và cấu trúc không?

**Bước 7 — Tạo test binding tối thiểu.** Dùng `ApplicationContextRunner` với một property string có `[key]`. Nếu test nhỏ đúng còn ứng dụng lớn sai, tiếp tục tìm nguồn ghi đè và cấu trúc cấu hình khác.

**Bước 8 — Kiểm tra hành vi dùng Map.** Nếu binding đúng nhưng route không hoạt động, lỗi có thể ở logic router, thứ tự route, rule matching hoặc quyền truy cập, không phải binder.

Chia vấn đề theo các bước giúp tránh sửa cả ứng dụng chỉ vì một dấu `/` bị loại khỏi Map key.

## 24. Bài tập tự kiểm tra

### Bài 1. Giữ nguyên key chứa slash

Hãy chuyển:

```yaml
api:
  handlers:
    /public/v1: open-handler
```

sang dạng bảo toàn key. Đáp án:

```yaml
api:
  handlers:
    "[/public/v1]": open-handler
```

Trong Java, `Map<String,String> handlers` có thể lookup bằng `get("/public/v1")`.

### Bài 2. Giữ key có @ và dấu chấm

Giả sử cần key `account@east` và `tenant.blue`, hãy viết file `.properties`:

```properties
accounts.handlers[account@east]=east-handler
accounts.handlers[tenant.blue]=blue-handler
```

Giải thích: `@` cần bảo toàn bằng bracket notation; dấu chấm cũng được đặt trong bracket để ý định key literal rõ ràng, kể cả nếu kiểu value thay đổi trong tương lai.

### Bài 3. Dự đoán Map scalar

Cho:

```properties
demo.map.a.b=sample
```

Và:

```java
@ConfigurationProperties(prefix = "demo")
public record DemoProperties(Map<String, String> map) {}
```

Dự đoán key của Map. Với kiểu scalar `String`, key có thể là `a.b`.

### Bài 4. Dự đoán Map object

Giữ property `demo.map.a.b=sample` nhưng đổi kiểu Java thành `Map<String,Object>`. Hãy giải thích vì sao tên `a.b` có thể trở thành cấu trúc nested. Sửa property để giữ key literal:

```properties
demo.map[a.b]=sample
```

### Bài 5. Tạo Map có value là record

Cho:

```java
public record AccessPolicy(boolean enabled, int limit) {}

@ConfigurationProperties(prefix = "access")
public record AccessProperties(Map<String, AccessPolicy> policies) {}
```

Hãy viết YAML cho hai key `/admin/**` và `tenant@east`, với `enabled`/`limit` khác nhau. Đáp án mẫu:

```yaml
access:
  policies:
    "[/admin/**]":
      enabled: true
      limit: 10
    "[tenant@east]":
      enabled: false
      limit: 5
```

### Bài 6. Ghi đè theo profile

File chung khai báo `"[/api/v1]": dev-handler`, file `application-prod.yml` khai báo `"[/api/v1]": prod-handler`. Hãy dự đoán Map sau khi bật `prod` trong một trường hợp không có nguồn ưu tiên cao hơn. Giải thích vì sao cùng một key literal có thể được override, còn khác cú pháp giữa các nguồn có thể tạo key khác.

### Bài 7. Tìm lỗi lookup

Java gọi:

```java
props.handlers().get("tenant@east");
```

YAML:

```yaml
routing:
  handlers:
    "tenant@east": east-handler
```

Vì sao code có thể nhận `null`? Hãy nêu nguyên nhân ở tầng binder, sửa YAML và đề xuất một assertion trong integration test để tránh lỗi tái diễn.

## 25. Tổng kết

Ký pháp dấu ngoặc vuông là một cơ chế quan trọng khi bind cấu hình Spring Boot vào `Map` có key chứa ký tự đặc biệt.

```text
Muốn key Map là: /api/v1

Trong .properties:
  routing.handlers[/api/v1]=orders-handler

Trong YAML:
  routing:
    handlers:
      "[/api/v1]": orders-handler

Trong Java:
  properties.handlers().get("/api/v1")
```

Các quy tắc cốt lõi:

1. **Dùng `[key]` để giữ nguyên tên Map key** khi chứa ký tự như `/`, `@`, `*` hoặc những ký tự ngoài tập tên thông thường.
2. **Trong YAML, đặt dấu nháy quanh cả `[key]`** để parser đọc đúng key.
3. **Dấu nháy đơn thuần không thay thế ngoặc vuông.** `"/api/v1"` và `"[/api/v1]"` không có cùng ý nghĩa với binder.
4. **Dấu chấm là ngoại lệ cần chú ý.** Với Map scalar như `Map<String,String>`, `a.b` có thể được giữ mà không cần ngoặc; với `Map<String,Object>` hoặc value phức tạp, nó có thể trở thành đường dẫn lồng nhau.
5. **Chỉ bao phần Map key trong ngoặc.** Với `Map<String, Rule>`, viết `rules[team.east].enabled` để truy cập field của value.
6. **Ngoặc vuông không thay đổi quy tắc ưu tiên nguồn hoặc kiểm tra value.** Nó bảo toàn tên key, không thay cho conversion, validation hay bảo mật.
7. **Kiểm tra Map sau binding.** Các phép `containsKey(...)` và `keySet()` trong test giúp phát hiện sớm key bị biến dạng.

Điểm mấu chốt: một Map có thể chứa đúng giá trị nhưng sai key. Khi khóa biểu diễn route, tenant, mã đối tác hoặc tên chính sách, **giữ nguyên từng ký tự của key chính là giữ đúng hợp đồng cấu hình**.

Đọc thêm tài liệu chính thức: [Spring Boot — Externalized Configuration, Binding Maps](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.relaxed-binding.maps) và [Spring Boot — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties).
# Phân biệt khóa vắng mặt, chuỗi rỗng, giá trị 0 và false trong Spring Boot 3.3

## 1. Vì sao bốn trạng thái này quan trọng?

Khi xử lý externalized configuration trong Spring Boot 3.3, ứng dụng thường phải phân biệt bốn trường hợp:

1. **Khóa không được khai báo** ở bất kỳ nguồn cấu hình hiệu lực nào.
2. **Khóa tồn tại nhưng giá trị là chuỗi rỗng** `""`.
3. **Khóa tồn tại với giá trị số không** `0`.
4. **Khóa tồn tại với giá trị boolean false** `false`.

Chúng có thể trông giống nhau khi lập trình viên kiểm tra bằng biểu thức “có vẻ không có giá trị”, nhưng Spring `Environment`, cơ chế placeholder `${...}`, `@Value` và `@ConfigurationProperties` xử lý chúng khác nhau. Đặc biệt, **`0` và `false` là giá trị hợp lệ**, không phải dấu hiệu “chưa cấu hình”.

Ví dụ trong `application.properties`:

```properties
# app.name không xuất hiện: khóa vắng mặt
app.alias=
app.max-retries=0
app.feature-enabled=false
```

Các ý nghĩa nghiệp vụ có thể là:

- `app.name`: chưa có quyết định tên, được phép dùng default hoặc từ chối startup.
- `app.alias`: đã chỉ định một chuỗi rỗng; có thể có nghĩa “không hiển thị bí danh”.
- `app.max-retries=0`: chủ động **không retry** khi thao tác thất bại.
- `app.feature-enabled=false`: chủ động **tắt** một tính năng.

Nếu mã nguồn dùng kiểu `if (!value)` của một ngôn ngữ khác làm mô hình, hoặc trong Java tự quy tất cả về “không có”, ứng dụng dễ ghi đè những quyết định cấu hình hợp lệ.

**Tóm tắt nguyên tắc:** xem **sự tồn tại của property**, **chuỗi đầu vào** và **giá trị sau chuyển kiểu** là ba lớp thông tin riêng.

## 2. Bảng so sánh nhanh

Giả sử một khóa được cung cấp từ file `application.properties`, và chưa có nguồn ưu tiên cao hơn ghi đè:

| Trạng thái | Ví dụ file | `Environment#getProperty("app.key")` | `getProperty("app.key", "fallback")` | Cách hiểu |
| --- | --- | --- | --- | --- |
| Khóa vắng mặt | Không có dòng `app.key` | `null` | `"fallback"` | Không tìm thấy giá trị có thể giải quyết |
| Chuỗi rỗng | `app.key=` | `""` | `""` | Có property, giá trị String dài 0 |
| Chuỗi `0` | `app.key=0` | `"0"` | `"0"` | Có property, giá trị biểu diễn số không |
| Chuỗi `false` | `app.key=false` | `"false"` | `"false"` | Có property, giá trị biểu diễn boolean false |

Bảng trên dành cho **đọc ở dạng String qua `Environment`**. Khi đọc bằng `getProperty(key, Integer.class)`, `getProperty(key, Boolean.class)` hoặc bind vào kiểu Java tương ứng, Spring dùng cơ chế **chuyển đổi kiểu**. Khi giá trị là chuỗi rỗng mà kiểu đích không nhận được chuỗi rỗng, kết quả có thể là `null` hoặc lỗi chuyển đổi/binding tùy API và kiểu đích. Không nên giả định chuỗi rỗng tự chuyển thành `0` hoặc `false`.

Phép kiểm tra `environment.containsProperty("app.key")` cho biết property **có một giá trị có thể giải quyết (khác null)** trong các PropertySource hiện tại hay không, chứ không phải phép tìm xem một dòng text có xuất hiện trong một file nào đó không. Bởi vậy thông thường:

```text
missing -> containsProperty=false
""      -> containsProperty=true
"0"     -> containsProperty=true
"false" -> containsProperty=true
```

Nếu một nguồn có key nhưng giá trị `null`, khái niệm “có key trong nguồn vật lý” và “có giá trị giải quyết được trong Environment” có thể khác nhau. Phần về JSON null ở dưới giải thích trường hợp tiêu biểu.

## 3. Khai báo trong .properties và YAML

### 3.1. File .properties

```properties
# Không khai báo app.missing

app.empty=
app.zero=0
app.off=false
app.label=0
app.flag-as-text=false
```

Trong file .properties, phần bên phải dấu `=` được đọc như nội dung property và sau đó được chuyển sang kiểu Java khi cần. Vì thế:

- `app.empty=` là **chuỗi rỗng**, không phải một giá trị số không.
- `app.zero=0` có chuỗi đầu vào `"0"`; Binder có thể chuyển thành `int`/`Integer`.
- `app.off=false` có chuỗi đầu vào `"false"`; Binder có thể chuyển thành `boolean`/`Boolean`.
- `app.label=0` vẫn là **String `"0"`** nếu khai báo kiểu Java là `String`.
- `app.flag-as-text=false` vẫn là **String `"false"`** nếu kiểu đích là `String`.

Nghĩa của một giá trị không thể suy ra chỉ từ hình thức khi **chưa biết kiểu Java và mục đích nghiệp vụ**.

### 3.2. File YAML tương đương

```yaml
# application.yaml
app:
  empty: ""
  zero: 0
  off: false
  label: "0"
  flag-as-text: "false"
```

Cú pháp YAML dùng dấu nháy `""` để biểu diễn rõ **chuỗi rỗng**. Khi cần giữ `0` hoặc `false` như dữ liệu text theo định dạng YAML, nên đặt trong dấu nháy để tránh nhầm ý định với scalar số/boolean của YAML.

Đừng xem những cách viết sau là tương đương tuyệt đối:

```yaml
app:
  empty-string: ""
  no-explicit-value:
  explicit-null: null
  false-flag: false
  zero-count: 0
```

`empty-string: ""` diễn đạt String rỗng. Trong YAML, một node không có nội dung sau dấu `:` và scalar `null` có **ngữ nghĩa YAML null**; chúng không phải cách ghi rõ ràng cho String rỗng. Cách flatten và chuyển đổi null còn phụ thuộc đường nạp cụ thể. Nếu cần một chuỗi rỗng có chủ ý, dùng `""`; nếu cần phân biệt “không cung cấp property”, tốt nhất **không khai báo key**. Đừng dùng YAML `null` như một cơ chế phổ quát để xóa giá trị đến từ nguồn ưu tiên thấp hơn.

### 3.3. Chuỗi chỉ có khoảng trắng không phải chuỗi rỗng

`" "` có một dấu cách, khác `""`. Ví dụ:

```yaml
app:
  title: " "
```

Khi dùng String, hãy xác định ứng dụng cần chấp nhận, giữ nguyên hay coi chuỗi chỉ gồm khoảng trắng là không hợp lệ. Các phép kiểm tra trong Java cũng khác nhau:

```java
String value = " ";
value.isEmpty(); // false
value.isBlank(); // true
```

Cơ chế nạp file và conversion có thể xử lý/trim một số ký tự theo định dạng hoặc converter, vì vậy nếu ý nghĩa phụ thuộc chính xác khoảng trắng, hãy quy định và kiểm tra rõ. `@NotBlank` hữu ích khi chuỗi phải có ký tự không phải khoảng trắng.

## 4. Quan sát bằng `Environment`: nhận biết “thiếu” và “đã đặt”

`Environment` của Spring Framework cung cấp nhiều cách truy cập property. Một ví dụ trong Spring Boot:

```java
package com.example.demo;

import java.util.Arrays;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration
class ConfigDiagnostics {

    @Bean
    ApplicationRunner inspectProperties(Environment env) {
        return args -> {
            for (String key : Arrays.asList(
                    "app.missing", "app.empty", "app.zero", "app.off")) {

                String value = env.getProperty(key);
                System.out.printf(
                        "%s present=%s value=%s length=%s%n",
                        key,
                        env.containsProperty(key),
                        value == null ? "<null>" : "[" + value + "]",
                        value == null ? "<null>" : value.length()
                );
            }
        };
    }
}
```

Với YAML hoặc .properties tương đương ở trên, khi không có nguồn nào khác ghi đè:

```text
app.missing present=false value=<null> length=<null>
app.empty   present=true  value=[]     length=0
app.zero    present=true  value=[0]    length=1
app.off     present=true  value=[false] length=5
```

**Tại sao in dấu `[ ]` quanh giá trị?** Nếu chỉ `println(value)`, chuỗi rỗng nhìn giống một dòng trắng, khó phân biệt với dữ liệu bị mất. Với property có thể chứa bí mật, không in giá trị ra log; chỉ chẩn đoán các key không nhạy cảm hoặc log trạng thái đã được che.

### `getProperty(key, defaultValue)` không thay thế mọi giá trị “falsy”

Ví dụ:

```java
String a = env.getProperty("app.missing", "fallback"); // fallback
String b = env.getProperty("app.empty", "fallback");   // ""
String c = env.getProperty("app.zero", "fallback");    // "0"
String d = env.getProperty("app.off", "fallback");     // "false"
```

Tham số `defaultValue` được sử dụng khi **không thể giải quyết giá trị property**, không phải khi giá trị là rỗng, số không hay false.

Tương tự, nếu muốn đọc kiểu:

```java
Integer maxRetries = env.getProperty("app.zero", Integer.class);
Boolean enabled = env.getProperty("app.off", Boolean.class);
```

Thường có kết quả `maxRetries=0` và `enabled=false`. Hai giá trị này hợp lệ. Với key thiếu, đối tượng kiểu wrapper có thể là `null`; nếu cần fallback rõ ràng, sử dụng overload có default:

```java
Integer retryCount = env.getProperty("app.max-retries",
        Integer.class, 3);
Boolean featureEnabled = env.getProperty("app.feature-enabled",
        Boolean.class, false);
```

Overload typed vẫn chịu yêu cầu chuyển đổi kiểu. Nếu chuỗi rỗng được khai báo cho một property số/boolean, không nên xem nó là “thiếu” rồi mặc định 0/false mà không có quy tắc ứng dụng rõ ràng.

### `getRequiredProperty` là một khái niệm khác

`env.getRequiredProperty("app.name")` được dùng khi property **phải tồn tại và có giá trị giải quyết được**. Điều này không đồng nghĩa “String phải chứa ký tự”.

Một chuỗi rỗng có thể vẫn là **giá trị đã được giải quyết** với kiểu String. Nếu yêu cầu nghiệp vụ là “không được rỗng”, cần kiểm tra `isBlank()` hoặc dùng Bean Validation ở tầng `@ConfigurationProperties`, thay vì chỉ dựa vào `getRequiredProperty`.

## 5. Placeholder `${key:default}`: khi nào default được dùng?

Spring Boot cho phép dùng cú pháp placeholder trong các giá trị ở `application.properties`/YAML và `@Value`:

```properties
app.display-name=${app.name:Guest}
app.retry-limit=${app.max-retries:3}
app.enabled-by-default=${app.feature-enabled:true}
```

Dấu `:` phân tách tên property với giá trị mặc định.

Giả sử ta kiểm tra bốn tình huống cho riêng `app.name`:

| `app.name` hiệu lực | Giá trị của `${app.name:Guest}` | Diễn giải |
| --- | --- | --- |
| Vắng mặt | `Guest` | Có fallback |
| `app.name=` | `""` | Chuỗi rỗng được coi là giá trị đã có |
| `app.name=0` | `0` | Không dùng fallback |
| `app.name=false` | `false` | Không dùng fallback |

**Kết luận:** placeholder default không phải toán tử “nếu giá trị không có ý nghĩa thì dùng thay thế”. Nó là fallback theo cơ chế **không tìm thấy property**.

Ví dụ sử dụng:

```java
@Component
class DisplayService {

    private final String displayName;

    DisplayService(@Value("${app.name:Guest}") String displayName) {
        this.displayName = displayName;
    }

    String displayName() {
        return displayName;
    }
}
```

Nếu file ghi `app.name=`, `displayName` nhận chuỗi rỗng; nó không tự chuyển thành `Guest`.

### Phân biệt default và default rỗng

Hai biểu thức sau khác nhau:

```properties
app.title=${app.name:Guest}
app.subtitle=${app.name:}
```

Khi `app.name` **vắng mặt**:

- `app.title` dùng `Guest`.
- `app.subtitle` dùng chuỗi rỗng.

Khi `app.name` **đã tồn tại và bằng chuỗi rỗng**, cả hai sẽ lấy chuỗi rỗng. Điều kiện kích hoạt default vẫn là **không tìm thấy property**, không phải nội dung của default.

### Placeholder lồng nhau

```properties
app.endpoint=${app.remote-url:${app.local-url:http://localhost:8080}}
```

Spring có thể dùng `app.remote-url` nếu được giải quyết; nếu không, xét `app.local-url`; nếu cả hai thiếu thì dùng URL cố định. Nếu `app.remote-url=` (rỗng), tầng default bên ngoài thông thường không được dùng vì property tồn tại với giá trị String rỗng. Trường hợp này đòi hỏi chính sách của ứng dụng: chuỗi rỗng có được phép biểu thị “tắt endpoint” không, hay phải từ chối cấu hình?

**Cách viết tên key:** ưu tiên dạng chuẩn lowercase kebab-case trong placeholder, ví dụ `${app.max-retries:3}`, để phù hợp cơ chế relaxed binding của Spring Boot.

## 6. `@Value` với kiểu Java: đừng nhập nhằng null, rỗng và boolean

Trong code:

```java
@Component
class FeaturePolicy {

    FeaturePolicy(
            @Value("${app.feature-enabled:false}") boolean enabled,
            @Value("${app.max-retries:0}") int maxRetries,
            @Value("${app.label:}") String label) {

        System.out.println(enabled);
        System.out.println(maxRetries);
        System.out.println("[" + label + "]");
    }
}
```

Nếu các property **vắng mặt**, annotation cung cấp default đã chỉ định: `false`, `0` và `""` trước khi chuyển sang các kiểu Java.

Nếu property đã có:

```properties
app.feature-enabled=false
app.max-retries=0
app.label=
```

thì ba giá trị vẫn lần lượt là `false`, `0` và `""`, nhưng **chúng đến từ cấu hình đã khai báo**, không phải nhờ fallback.

Điểm nguy hiểm là hai bộ dữ liệu có thể cho **cùng giá trị Java** mà vẫn khác ý nghĩa:

- Không khai báo `app.max-retries`, trong Java nhận `0` do default annotation.
- Khai báo rõ `app.max-retries=0`, trong Java cũng nhận `0`.
- Không khai báo `app.feature-enabled`, Java nhận `false` do default annotation.
- Khai báo `app.feature-enabled=false`, Java cũng nhận `false`.

Nếu cần biết người vận hành **đã cố ý ghi đè** hay chưa, không thể chỉ dựa vào trường `int`/`boolean` sau binding; cần kiểm tra khả năng giải quyết property ở `Environment` hoặc dùng mô hình trạng thái riêng.

### Tránh dùng chuỗi rỗng làm boolean/int

Ví dụ dễ gây lỗi:

```properties
app.max-retries=
app.feature-enabled=
```

Nếu inject vào `int` hoặc `boolean` bằng `@Value`, chuỗi rỗng có thể không chuyển thành giá trị primitive hợp lệ. Kết quả có thể là conversion/binding exception hoặc null ở một tầng trung gian; không được tự kết luận “rỗng chắc chắn bằng 0/false”.

Nếu cần mặc định, **bỏ hẳn key** để fallback có hiệu lực, hoặc cung cấp giá trị đúng kiểu. Nếu cần một trạng thái ba giá trị, dùng wrapper `Integer`/`Boolean` cùng chính sách cho giá trị rỗng.

## 7. `@ConfigurationProperties` và giá trị mặc định

Đối với nhiều property, Spring Boot khuyến nghị binding theo kiểu bằng `@ConfigurationProperties`. Cơ chế này khác `@Value` ở khả năng relaxed binding, nested structures, metadata và hỗ trợ constructor/record binding.

### 7.1. Record với `@DefaultValue`

Spring Boot 3.3 hỗ trợ `org.springframework.boot.context.properties.bind.DefaultValue` cho tham số constructor/record component của cấu hình bất biến.

Ví dụ:

```java
package com.example.demo.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @DefaultValue("Guest") String name,
        @DefaultValue("3") int maxRetries,
        @DefaultValue("false") boolean featureEnabled,
        String alias) {
}
```

Bật quét lớp cấu hình:

```java
@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

**Khi thiếu các key tương ứng**, Binder có thể dùng:

```text
name           = "Guest"
maxRetries     = 3
featureEnabled = false
alias          = null
```

**Khi file chứa:**

```properties
app.name=
app.max-retries=0
app.feature-enabled=false
app.alias=
```

thì `@DefaultValue("Guest")` **không thay chuỗi rỗng bằng Guest**, vì property `app.name` đã được tìm thấy. `maxRetries=0` và `featureEnabled=false` giữ đúng ý định khai báo, không dùng các default tương ứng; `alias` là String rỗng.

Đây là điểm Spring Boot 3.3 nói rõ trong Javadoc `@DefaultValue`: **default chỉ dùng khi Binder không tìm thấy property; ngay cả khi property tồn tại với giá trị rỗng, annotation default không được áp dụng**.

**Giới hạn:** `@DefaultValue` không hỗ trợ placeholder resolution cho giá trị được khai báo trong annotation; giá trị của annotation phải là hằng và sẽ được conversion service chuyển sang kiểu đích.

### 7.2. JavaBean với giá trị khởi tạo ban đầu

Một cách khác là định nghĩa default ở trường JavaBean:

```java
package com.example.demo.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public class AppSettings {

    private String name = "Guest";
    private int maxRetries = 3;
    private boolean featureEnabled = true;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public int getMaxRetries() {
        return maxRetries;
    }

    public void setMaxRetries(int maxRetries) {
        this.maxRetries = maxRetries;
    }

    public boolean isFeatureEnabled() {
        return featureEnabled;
    }

    public void setFeatureEnabled(boolean featureEnabled) {
        this.featureEnabled = featureEnabled;
    }
}
```

Trong kiểu bean có setter này:

- Nếu không có `app.name`, trường có thể giữ giá trị khởi tạo `Guest`.
- Nếu `app.name=`, Binder có thể set thành `""`, thay thế `Guest`.
- Nếu `app.max-retries=0`, trường đổi từ `3` sang `0`.
- Nếu `app.feature-enabled=false`, trường đổi từ `true` sang `false`.

Một giá trị explicit `0`/`false` luôn có thể ghi đè default khởi tạo trong JavaBean. Với property rỗng nhưng kiểu đích không cho phép, cần xử lý/validate rõ ràng, không giả định nó tự trở về default cũ.

### 7.3. Primitive và wrapper

Giả sử hai khai báo:

```java
private int retryCount;
private Integer retryLimit;

private boolean enabled;
private Boolean overrideEnabled;
```

Đối với một JavaBean mới tạo, `int` có giá trị khởi tạo Java `0` và `boolean` là `false`, còn `Integer`/`Boolean` mặc định là `null` khi chưa gán. Vì vậy:

- `retryCount==0` **không chứng minh** key `app.retry-count` đã được cấu hình.
- `enabled==false` **không chứng minh** key `app.enabled` đã được cấu hình.
- Wrapper có thể biểu thị **chưa được gán** bằng `null`, nhưng cần thiết kế rõ ý nghĩa và tác động của binding/validation, thay vì suy đoán từ wrapper một cách tuyệt đối.
- Khi property bắt buộc, sử dụng validation để buộc giá trị hợp lệ; nếu một flag là hai trạng thái thuần túy, primitive boolean cùng default explicit có thể là thiết kế đơn giản.

Đối với cấu hình tri-state thật sự:

```text
null  → không chỉ định, dùng chính sách kế thừa
false → chỉ định tắt
true  → chỉ định bật
```

có thể dùng `Boolean`, **không tự map chuỗi rỗng thành null** nếu chưa định nghĩa chính sách đó. Nếu cần phân biệt thêm trạng thái “đã khai báo rỗng”, mô hình cần một trạng thái riêng hoặc kiểm tra nguồn property.

## 8. Cần kiểm tra “presence” hay “value”?

Hãy bắt đầu từ câu hỏi nghiệp vụ:

| Yêu cầu | Nên kiểm tra |
| --- | --- |
| Cần biết khóa có giá trị có thể giải quyết được không | `Environment.containsProperty(key)` |
| Cần đọc chuỗi, có fallback khi thiếu | `Environment.getProperty(key, defaultValue)` |
| Cần biết có chuỗi rỗng hay không | `value != null && value.isEmpty()` |
| Cần biết có chuỗi trắng toàn bộ hay không | `value != null && value.isBlank()` |
| Cần boolean thật | `getProperty(key, Boolean.class)` hoặc `@ConfigurationProperties` |
| Cần phân biệt không cấu hình / false / true | `Boolean` và quy tắc binding rõ ràng |
| Cần số không là giá trị hợp lệ | `int`/`Integer` cùng validation phù hợp |
| Cần String không rỗng, không toàn khoảng trắng | `@NotBlank` hoặc kiểm tra `isBlank()` |
| Cần số lớn hơn 0 | `@Positive` hoặc `@Min(1)` |
| Cần đảm bảo key được cung cấp trong tập cấu hình phù hợp | Validation, kiểm tra property source/origin, quy tắc startup |

Ví dụ một hàm mô tả trạng thái từ `Environment`:

```java
static String describe(Environment env, String key) {
    String raw = env.getProperty(key);

    if (raw == null) {
        return "MISSING";
    }
    if (raw.isEmpty()) {
        return "EMPTY";
    }
    if (raw.equalsIgnoreCase("false")) {
        return "BOOLEAN_FALSE_TEXT";
    }
    if (raw.equals("0")) {
        return "ZERO_TEXT";
    }
    return "PRESENT_VALUE";
}
```

Hàm này chỉ phân loại **chuỗi hiệu lực sau khi Environment giải quyết**, không phải một parser hoàn chỉnh. Ví dụ `"00"` vẫn có thể chuyển thành số 0 tùy conversion, nhưng không khớp nhánh `raw.equals("0")`. Nếu cần semantics số, hãy dùng conversion service và xử lý giá trị không hợp lệ. Nếu cần phân biệt nguồn ưu tiên nào đóng góp giá trị, phải xem `PropertySource`/origin.

## 9. Thứ tự ưu tiên PropertySource: chuỗi rỗng, 0, false có ghi đè được không?

**Có.** Spring Boot 3.3 sử dụng nhiều nguồn cấu hình với thứ tự ưu tiên rõ ràng. Với cùng một khóa, giá trị từ nguồn có ưu tiên cao hơn được dùng. Giá trị `""`, `"0"` hoặc `"false"` vẫn là giá trị có thể giải quyết và **có thể ghi đè** một giá trị bình thường ở nguồn thấp hơn.

Ví dụ file đóng gói:

```properties
# classpath:/application.properties
app.name=Catalog
app.max-retries=5
app.feature-enabled=true
```

Khởi chạy:

```bash
java -jar myapp.jar \
  --app.name= \
  --app.max-retries=0 \
  --app.feature-enabled=false
```

Theo thứ tự ưu tiên mặc định, command-line properties ở mức cao hơn file ứng dụng. Giá trị String có hiệu lực:

```text
app.name           = ""
app.max-retries    = "0"
app.feature-enabled = "false"
```

Nghĩa là:

- `--app.name=` **ghi đè bằng chuỗi rỗng**; không tự dùng lại tên `Catalog`.
- `--app.max-retries=0` **ghi đè bằng 0**; không tự dùng lại `5`.
- `--app.feature-enabled=false` **ghi đè bằng false**; không tự dùng lại `true`.

Tương tự có thể cung cấp bằng JVM system properties:

```bash
java -Dapp.name= -Dapp.max-retries=0 \
  -Dapp.feature-enabled=false -jar myapp.jar
```

Và biến môi trường tương ứng:

```bash
APP_NAME='' APP_MAXRETRIES=0 APP_FEATUREENABLED=false \
  java -jar myapp.jar
```

Ví dụ trên phù hợp cách ánh xạ tên canonical property vào environment variable của Boot: dấu chấm thành `_`, bỏ dấu `-`, viết hoa. Nếu không truyền khóa ở nguồn cao hơn, Spring tiếp tục tìm giá trị ở nguồn thấp hơn theo thứ tự PropertySource.

### Higher priority = empty khác “không có higher priority”

Đừng suy luận: “Nếu nguồn cấp cao có giá trị rỗng thì Spring sẽ bỏ qua và đọc nguồn cấp thấp”. Với String property rỗng, Spring thường xem đó là giá trị có mặt, nên nó **che** giá trị có nghĩa của nguồn thấp hơn.

Nếu yêu cầu ứng dụng là “coi rỗng như không khai báo”, cần thực hiện rõ trong mô hình binding hoặc tầng business:

```java
String configured = env.getProperty("app.name");
String effective = (configured == null || configured.isBlank())
        ? "Catalog"
        : configured;
```

Đây là **quy tắc nghiệp vụ tự xây dựng**, không phải hành vi tự động của `${app.name:Catalog}`.

## 10. JSON null có thể dùng để xóa giá trị nguồn thấp hơn không?

Spring Boot cho phép nạp JSON cấu hình từ `SPRING_APPLICATION_JSON`, JVM `spring.application.json` hoặc command-line argument tương ứng:

```bash
SPRING_APPLICATION_JSON='{"app":{"name":null,"maxRetries":0,"enabled":false}}' \
  java -jar myapp.jar
```

Đặc tính quan trọng được tài liệu Spring Boot 3.3 xác nhận: **JSON null không thể dùng để ghi đè một giá trị đến từ PropertySource có ưu tiên thấp hơn**, vì `PropertySourcesPropertyResolver` xem giá trị `null` là không có.

Giả sử file đóng gói:

```properties
app.name=Catalog
```

Và JSON cao hơn chứa:

```json
{"app":{"name":null}}
```

Kết quả có thể vẫn là `app.name=Catalog` từ nguồn thấp hơn. Nó **khác** với:

```json
{"app":{"name":""}}
```

Trong trường hợp này, chuỗi rỗng là **giá trị String thực** và có thể che `Catalog`.

Các phần tử JSON `0` và `false` cũng là giá trị thật, sau khi được giải quyết/chuyển kiểu sẽ mang nghĩa số không và boolean false, không phải lệnh bỏ qua nguồn.

Không suy rộng cơ chế JSON null thành một quy tắc thống nhất cho mọi nguồn dữ liệu, mọi converter hoặc mọi API ở Java. Khi nguồn là YAML, config tree hay PropertySource tùy biến, cần xét cách nguồn đó biểu diễn và công bố giá trị của key cho Spring.

## 11. `@ConditionalOnProperty`: kiểm tra thuộc tính là false hay chỉ không có?

Một bẫy rất thường gặp trong Spring Boot auto-configuration là nghĩ rằng `@ConditionalOnProperty` mặc định kiểm tra boolean true. **Không hoàn toàn đúng.** Theo semantics của Spring Boot, khi không đặt `havingValue`, điều kiện thường khớp nếu property **tồn tại và không bằng chuỗi `"false"`**.

Ví dụ:

```java
@Configuration
@ConditionalOnProperty(
    prefix = "app",
    name = "feature-enabled"
)
class FeatureConfiguration {
}
```

Với `matchIfMissing=false` mặc định:

| Giá trị hiệu lực `app.feature-enabled` | Điều kiện mặc định có thể khớp? | Lý do |
| --- | --- | --- |
| Vắng mặt | Không | `matchIfMissing` mặc định false |
| `false` | Không | Giá trị bằng `"false"` |
| `true` | Có | Giá trị có mặt và khác `"false"` |
| `0` | **Có** | Chuỗi `"0"` không phải `"false"` |
| Chuỗi rỗng `""` | **Có** | Giá trị có mặt và khác `"false"` |
| `custom` | Có | Giá trị có mặt và khác `"false"` |

Do đó, muốn một **feature flag true rõ ràng**, hãy khai báo:

```java
@Configuration
@ConditionalOnProperty(
    prefix = "app",
    name = "feature-enabled",
    havingValue = "true",
    matchIfMissing = false
)
class FeatureConfiguration {
}
```

Với `havingValue="true"`, điều kiện chỉ khớp giá trị được nhận là `"true"` theo cách đối chiếu của annotation. `false`, `0` và `""` không khớp; key thiếu cũng không khớp.

Nếu muốn một tính năng **mặc định bật khi thiếu key**, có thể định nghĩa chính sách rõ:

```java
@Configuration
@ConditionalOnProperty(
    prefix = "app",
    name = "feature-enabled",
    havingValue = "true",
    matchIfMissing = true
)
class DefaultOnFeatureConfiguration {
}
```

Lúc này **vắng mặt** sẽ khớp do `matchIfMissing=true`, còn **explicit false** vẫn không khớp. `matchIfMissing` không có nghĩa “coi rỗng hoặc 0 như thiếu”.

Cần đặc biệt thận trọng với `@ConditionalOnProperty` cho collection; annotation này không bảo đảm khớp chính xác các key có chỉ số `[0]` nếu chỉ xét prefix của collection.

## 12. Validation để phân biệt giá trị hợp lệ và không hợp lệ

Đặt default giúp ứng dụng khởi động khi thiếu cấu hình, nhưng default **không thay thế validation**. Nếu một property không được phép rỗng hoặc không được phép bằng 0, hãy thể hiện điều đó rõ trong model.

Ví dụ với Spring Boot 3.3, Jakarta Bean Validation:

```java
package com.example.demo.config;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public record StrictSettings(
        @NotBlank String name,
        @Min(0) int maxRetries,
        @NotNull Boolean enabled) {
}
```

Giải thích:

- `@NotBlank`: `name` phải khác null, khác chuỗi rỗng và không chỉ gồm khoảng trắng.
- `@Min(0)`: `maxRetries=0` **hợp lệ**, các số âm không hợp lệ. Nếu muốn phải dương, dùng `@Min(1)` hoặc `@Positive`.
- `@NotNull Boolean enabled`: khi không có giá trị và Binder tạo trường null, validation thất bại; nhưng `false` là **khác null và hợp lệ**.

Nếu kiểu đích phải thật sự bắt buộc được cung cấp, primitive `boolean` không giúp phân biệt missing/false vì cả hai có thể cho cùng giá trị false; `Boolean` cùng `@NotNull` thích hợp hơn khi cần biểu thị tình trạng chưa khai báo.

Để validation cho `@ConfigurationProperties` hoạt động, dự án cần có implementation Bean Validation tương thích (thông thường thêm `spring-boot-starter-validation` nếu classpath chưa có) và đăng ký cấu hình properties đúng cách bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`.

### Không dùng `@NotNull` khi muốn cấm chuỗi rỗng

`@NotNull String name` chỉ yêu cầu không phải null. Giá trị `""` không phải null, vì thế dùng `@NotBlank` (hoặc `@NotEmpty` nếu vẫn cho phép chuỗi toàn khoảng trắng) khi business yêu cầu có tên hiển thị.

### Không dùng `@Positive` khi 0 là quyết định có ý nghĩa

Với retry count, `0` thường có nghĩa “không retry”, hoàn toàn hợp lệ. Dùng `@Min(0)` thay vì `@Positive` nếu muốn cho phép tắt retry bằng cách đặt 0.

Đừng chọn annotation theo cảm giác “giá trị 0 là chưa cấu hình”; chọn theo nghĩa của trường.

## 13. Mô hình trạng thái ba hoặc bốn giá trị

Một API cấu hình đôi khi cần phân biệt:

```text
MISSING  = chưa cấu hình
EMPTY    = chủ ý cung cấp chuỗi rỗng
ZERO     = chủ ý đặt 0 (đối với số)
FALSE    = chủ ý tắt (đối với boolean)
VALUE    = giá trị khác
```

Nếu các trạng thái này đều có nghĩa khác nhau, có thể biểu diễn riêng thay vì vội ép chúng về một primitive.

Ví dụ API đọc String hiệu lực:

```java
public enum InputKind {
    MISSING, EMPTY, VALUE
}

public record RawSetting(InputKind kind, String value) {
}

public static RawSetting readStringSetting(Environment env, String key) {
    String value = env.getProperty(key);
    if (value == null) {
        return new RawSetting(InputKind.MISSING, null);
    }
    if (value.isEmpty()) {
        return new RawSetting(InputKind.EMPTY, "");
    }
    return new RawSetting(InputKind.VALUE, value);
}
```

Ứng dụng có thể quyết định:

- `MISSING`: kế thừa hệ thống hoặc dùng default.
- `EMPTY`: xóa phần hiển thị của một nhãn, hoặc báo lỗi nếu không được phép.
- `VALUE`: parse theo kiểu String, số, boolean hoặc enum phù hợp.

Đối với boolean:

```java
Boolean override = env.getProperty("app.feature-enabled",
        Boolean.class);

if (override == null) {
    // chính sách dự phòng khi không có giá trị typed
} else if (override) {
    // chủ động bật
} else {
    // chủ động tắt
}
```

Ví dụ này tiện cho các trường hợp tri-state, nhưng **không tự phân biệt missing với raw empty** trong mọi conversion path. Nếu bắt buộc nhận ra empty, hãy kiểm tra giá trị String (hoặc nguồn nguyên thủy) trước khi convert.

Không lạm dụng `Optional` làm field của `@ConfigurationProperties`: tài liệu Spring Boot nêu rõ `Optional` không phải lựa chọn được khuyến nghị cho property binding; với property không có giá trị, Binder có thể bind `null` thay vì một `Optional.empty()` như mong đợi.

## 14. Các lỗi cấu hình điển hình

### Lỗi 1 — Dùng placeholder default nhưng vẫn nhận chuỗi rỗng

```properties
app.name=
app.display-name=${app.name:Guest}
```

**Nguyên nhân:** `app.name` tồn tại với chuỗi rỗng, nên placeholder không lấy `Guest`.

**Giải pháp theo yêu cầu:** bỏ `app.name` nếu muốn default có hiệu lực, hoặc chấp nhận rằng empty là dữ liệu thực và xử lý empty theo nghiệp vụ.

### Lỗi 2 — Đặt retry count bằng 0 nhưng code tự thay thành 3

```java
// SAI nếu 0 nghĩa là cố ý không retry
int retries = configuredRetries == 0 ? 3 : configuredRetries;
```

Cách này không phân biệt **không khai báo** với **đã đặt 0**. Nếu 0 là hợp lệ, dùng default khi missing ở giai đoạn binding, không dùng 0 làm sentinel.

### Lỗi 3 — Feature false nhưng condition vẫn khớp vì truyền `0`

```properties
app.feature-enabled=0
```

`@ConditionalOnProperty(name="app.feature-enabled")` không đảm bảo rằng `0` được coi như boolean false; mặc định nó kiểm tra “property có mặt và khác `false`”. Nên ghi cấu hình boolean rõ `true`/`false` và dùng `havingValue="true"` nếu tính năng chỉ bật với true.

### Lỗi 4 — Đọc typed Boolean nhưng nghĩ null nghĩa là false

```java
Boolean enabled = env.getProperty("app.feature-enabled",
        Boolean.class);
```

Key thiếu có thể tạo `null`. Không dùng `enabled.booleanValue()` khi chưa kiểm tra null. Nếu tính năng mặc định tắt, dùng overload typed có default hoặc thiết kế binding explicit.

### Lỗi 5 — YAML null được kỳ vọng “xóa” giá trị file gốc

```yaml
app:
  name: null
```

Đừng suy luận giá trị null sẽ ghi đè chuỗi từ nguồn khác theo cùng cách empty string. JSON null được Spring Boot mô tả là **không thể override** một property thấp hơn. Với YAML hoặc custom loader, cần xem cơ chế giải quyết null cụ thể; dùng `""` nếu chủ ý muốn chuỗi rỗng.

### Lỗi 6 — Dùng `@NotNull` cho String và để lọt tên rỗng

```java
@NotNull
private String displayName;
```

Chuỗi rỗng vẫn khác null. Nếu tên phải có nội dung, dùng `@NotBlank`.

### Lỗi 7 — Đọc cấu hình qua API không cùng semantics

Một nơi dùng `env.getProperty(key)`; nơi khác dùng `@Value` với placeholder default; nơi khác lại dùng Binder `@DefaultValue`. Chúng có thể cùng trả về một giá trị trong tình huống thường nhưng khác nhau ở missing/empty/typed conversion. Chọn một mô hình chuẩn cho cấu hình của một component, đặc biệt khi cần khả năng kiểm thử và validation.

### Lỗi 8 — Xóa key ở file cao hơn và tưởng đã xóa khỏi ứng dụng

Nếu property vẫn tồn tại trong file hoặc nguồn ưu tiên thấp hơn, bỏ một dòng ở nguồn cao hơn có thể **làm lộ lại** giá trị cũ. Khóa không hiện diện ở một file không chứng minh nó vắng mặt trong `Environment`.

### Lỗi 9 — Mặc định primitive khiến hệ thống không nhận ra cấu hình thiếu

Trường `boolean enabled` mặc định false, `int timeout` mặc định 0. Nếu zero timeout là không hợp lệ hoặc bắt buộc cung cấp flag, dùng wrapper và validation; không dựa vào Java primitive để chứng minh giá trị được khai báo.

### Lỗi 10 — In toàn bộ cấu hình để debug missing/empty

Dump tất cả `Environment` hoặc endpoint `/actuator/env` không được bảo vệ có thể để lộ bí mật. Chỉ kiểm tra các key cần thiết; nếu dùng Actuator, cấu hình exposure và bảo vệ endpoint, tôn trọng các cơ chế masking/sanitization.

## 15. Kiểm thử hành vi một cách có chủ đích

Khi một feature phải có hành vi xác định cho cả bốn trạng thái, có thể viết test theo **đầu vào và kết quả mong đợi**, thay vì chỉ test “happy path”.

Ví dụ hàm thuần Java:

```java
public static String chooseDisplayName(String configured) {
    if (configured == null) {
        return "Guest";
    }
    return configured;  // rỗng được giữ nguyên nếu nghiệp vụ cho phép
}
```

Các trường hợp đầu vào:

| Đầu vào | Kết quả | Ý nghĩa |
| --- | --- | --- |
| `null` | `"Guest"` | Không có giá trị |
| `""` | `""` | Rỗng được cung cấp |
| `"0"` | `"0"` | Text số không vẫn là giá trị |
| `"false"` | `"false"` | Text boolean vẫn là giá trị |

Nếu nghiệp vụ lại yêu cầu “empty cũng dùng default”, implementation có chủ đích sẽ là:

```java
public static String chooseDisplayName(String configured) {
    return configured == null || configured.isBlank()
            ? "Guest"
            : configured;
}
```

Hai hàm đều hợp lệ nhưng **có hợp đồng khác nhau**. Quan trọng là mô tả rõ trường hợp empty, thay vì để hành vi xuất hiện ngẫu nhiên từ conversion hoặc một phép so sánh không đủ thông tin.

Trong test Spring Boot, có thể truyền property cố định:

```java
@SpringBootTest(properties = {
    "app.max-retries=0",
    "app.feature-enabled=false",
    "app.name="
})
class EmptyZeroFalseConfigTest {
    // Kiểm tra các bean đã bind trong cùng test context
}
```

Để kiểm tra tình huống **key thật sự vắng mặt**, test cần bảo đảm không có giá trị của key trong các PropertySource khác của context. Chỉ bỏ một dòng khỏi `@SpringBootTest(properties = ...)` không chứng minh rằng toàn bộ `Environment` thiếu key, vì file cấu hình ứng dụng hoặc môi trường hệ thống vẫn có thể cung cấp nó.

## 16. Quy trình xử lý khi giá trị không như mong đợi

1. **Xác định key chuẩn** (ví dụ `app.max-retries`) và kiểu dữ liệu mong muốn: `String`, `int`, `boolean`, `Integer` hoặc `Boolean`.
2. **Tìm giá trị String hiệu lực** bằng `env.getProperty(key)`. Phân biệt `null`, `""`, `"0"` và `"false"`; dùng dấu bao hoặc in độ dài cho các key không nhạy cảm.
3. **Kiểm tra khả năng giải quyết** bằng `containsProperty(key)`. Nhớ rằng đây là trạng thái của toàn bộ `Environment`, không phải chỉ một file.
4. **Kiểm tra PropertySource precedence**: nguồn cao có empty/0/false có thể che nguồn thấp; nếu nguồn cao không có key, nguồn thấp có thể được dùng.
5. **Xác định API tiêu thụ**: `${key:default}`, `@Value`, `getProperty(key, type)`, `@ConfigurationProperties` hoặc `@ConditionalOnProperty`.
6. **Kiểm tra phép chuyển kiểu và default**: default placeholder/`@DefaultValue` chỉ áp dụng theo cơ chế missing; không xem `0`/`false` như thiếu.
7. **Áp dụng validation nghiệp vụ** cho giá trị rỗng, không hợp lệ hoặc bắt buộc; dùng `@NotBlank`, `@Min`, `@NotNull` theo nghĩa.
8. **Ghi rõ chính sách cho null/empty** trong tài liệu config để người vận hành biết có thể tắt tính năng hay bỏ qua giá trị bằng cách nào.

## 17. Bảng quy tắc nhớ

| Câu hỏi | Đáp án trong trường hợp thông thường |
| --- | --- |
| Vắng mặt và `""` có giống nhau không? | **Không.** Missing thường được giải quyết thành `null`; empty là String có độ dài 0. |
| Placeholder `${key:default}` có dùng default khi `key=` không? | **Không**, vì String rỗng vẫn là giá trị được cung cấp. |
| `0` có được phép ghi đè giá trị số 5 không? | **Có**, nếu nguồn chứa `0` có ưu tiên cao hơn. |
| `false` có được phép ghi đè `true` không? | **Có**, khi nguồn có ưu tiên cao hơn. |
| `@DefaultValue("3")` có thắng `key=0` không? | **Không.** Key đã có giá trị 0. |
| `@DefaultValue("Guest")` có thắng `key=` không? | **Không**, khi Binder nhìn thấy property rỗng. |
| Java `boolean` mặc định false có chứng minh property đã được đặt false không? | **Không.** Primitive có giá trị mặc định của ngôn ngữ Java. |
| `@NotNull String` có chặn `""` không? | **Không.** Dùng `@NotBlank` nếu cần nội dung thật. |
| `@ConditionalOnProperty` mặc định có xem `0` như false không? | **Không.** Mặc định điều kiện so chuỗi với `false`. |
| JSON `null` có che được property từ nguồn thấp hơn không? | **Không**, theo cách `PropertySourcesPropertyResolver` xử lý JSON null trong Spring Boot. |
| Muốn phân biệt missing/false/true thì làm gì? | Dùng wrapper `Boolean` và chính sách conversion/validation rõ ràng, hoặc kiểm tra nguồn. |
| Muốn chấp nhận zero như một quyết định cấu hình? | Giữ `0`, không dùng zero làm sentinel cho missing; chọn validation phù hợp. |

## 18. Tài liệu tham khảo

- **Spring Boot 3.3 Reference – Externalized Configuration:** PropertySource order, JSON Application Properties, Property Placeholders, Type-safe Configuration Properties, Binding, `@ConfigurationProperties` vs. `@Value`. https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- **Spring Boot 3.3 API – `@DefaultValue`:** default chỉ dùng khi property không được tìm thấy; property tồn tại với chuỗi rỗng không làm annotation default có hiệu lực. https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/DefaultValue.html
- **Spring Boot 3.3 API – `@ConditionalOnProperty`:** ngữ nghĩa `havingValue` và `matchIfMissing`. https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html
- **Spring Framework – Environment Abstraction / PropertyResolver:** `containsProperty`, `getProperty`, default values và nguồn property. https://docs.spring.io/spring-framework/reference/core/beans/environment.html
- **Spring Framework – Using `@Value`:** default trong placeholder và conversion của giá trị inject. https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/value-annotations.html
- **Jakarta Bean Validation:** `@NotNull`, `@NotBlank`, `@Min` và các constraint tương ứng; dùng cùng `@Validated` để kiểm tra cấu hình ứng dụng.

**Ghi nhớ:** **MISSING** là “không giải quyết được giá trị”; **EMPTY** là một String rỗng có mặt; **0** và **false** là những giá trị explicit. Chúng khác nhau khi chọn default, ghi đè nguồn cấu hình, chuyển kiểu, quyết định bật/tắt feature và xác thực cấu hình. Trong Spring Boot 3.3, muốn phân biệt đúng phải xét **presence, raw value, target type, default policy và PropertySource precedence**.

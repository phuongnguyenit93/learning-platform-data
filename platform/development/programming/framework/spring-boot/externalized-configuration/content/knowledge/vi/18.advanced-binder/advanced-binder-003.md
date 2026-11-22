# Giữ thông tin kiểu tổng quát bằng `Bindable` trong Spring Boot

## 1. Bối cảnh: bind một giá trị không khó, bind kiểu generic mới khó

Spring Boot hỗ trợ **externalized configuration**: cấu hình từ `application.yml`, `application.properties`, biến môi trường, Java system properties và nhiều nguồn khác được tổng hợp vào `Environment`. Với một giá trị đơn, mã Java có thể dùng:

~~~java
String region = environment.getProperty("app.region");
Integer port = environment.getProperty("server.port", Integer.class);
~~~

Nhưng khi ứng dụng cần đọc một cấu trúc như `List<Endpoint>`, `Map<String, Duration>` hoặc `List<Map<String, RetryPolicy>>`, việc chỉ truyền `List.class` hay `Map.class` **không thể biểu diễn đầy đủ kiểu của các phần tử**. Các class này không mang theo `Endpoint`, `Duration` hoặc `RetryPolicy` như một `Class` riêng.

Spring Boot cung cấp hai thành phần trong package `org.springframework.boot.context.properties.bind`:

- **`Binder`**: đọc các nguồn cấu hình và thực hiện quá trình binding vào type Java.
- **`Bindable<T>`**: mô tả **đích để bind**: kiểu đích (cả thông tin generic), annotation liên quan và trong một số trường hợp giá trị đã có.

Ví dụ ngắn:

~~~java
List<String> servers = Binder.get(environment)
    .bind("app.servers", Bindable.listOf(String.class))
    .orElseGet(List::of);
~~~

Trong đó `Bindable.listOf(String.class)` nói rõ đích là **`List<String>`**, chứ không phải một `List` thô với kiểu phần tử không xác định.

> Ý chính: `Bindable` không phải danh sách chứa dữ liệu cấu hình. Nó là **mô tả kiểu và ngữ cảnh binding** để `Binder` biết nên tạo ra kiểu Java nào.

## 2. Ôn lại Java generics và type erasure

Khi khai báo:

~~~java
List<String> names;
List<Integer> ports;
List<Endpoint> endpoints;
~~~

Java compiler có thông tin generic để kiểm tra chương trình. Tuy nhiên, ở runtime, cách sử dụng `List.class` không lưu ba kiểu khác nhau:

~~~java
Class<?> raw = List.class;
~~~

Không tồn tại cú pháp Java hợp lệ:

~~~java
// Không hợp lệ: không có List<String>.class
// Class<List<String>> type = List<String>.class;
~~~

Đây là hệ quả của **type erasure**: runtime `Class` cho kiểu raw `List` không đủ để mô tả phần tử cụ thể.

Nếu chỉ gọi:

~~~java
binder.bind("app.servers", List.class);
~~~

đích binding là một danh sách kiểu raw. Kết quả có thể không mang thông tin để binder chuyển từng phần tử sang `String`, `Duration` hoặc một object lồng nhau theo ý định. Một cast như sau không tự khôi phục metadata generic:

~~~java
// Không nên: cast chỉ khiến compiler bớt phàn nàn;
// nó không cho Binder biết kiểu phần tử cần tạo.
@SuppressWarnings("unchecked")
List<Endpoint> endpoints =
    (List<Endpoint>) (List<?>) binder.bind("app.endpoints", List.class).get();
~~~

Với list các object, mã trên có nguy cơ nhận phần tử không thuộc kiểu mong muốn rồi lỗi khi sử dụng.

**Giải pháp:** truyền một `Bindable<List<Endpoint>>` có chứa type information đến `Binder`.

## 3. Các API liên quan và cách phối hợp

Các import thông dụng:

~~~java
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.BindResult;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.core.env.Environment;
import org.springframework.core.ResolvableType;

import java.util.List;
import java.util.Map;
import java.util.Set;
~~~

Trong Spring Boot 3.x:

~~~java
Binder binder = Binder.get(environment);
~~~

Tạo binder từ `Environment` hiện tại. Một số phương thức:

~~~java
BindResult<String> a =
    binder.bind("app.region", String.class);

BindResult<List<String>> b =
    binder.bind("app.servers", Bindable.listOf(String.class));

BindResult<Map<String, Integer>> c =
    binder.bind("app.limits", Bindable.mapOf(String.class, Integer.class));
~~~

Bảng vai trò:

| Thành phần | Vai trò |
| --- | --- |
| `Environment` | Tập hợp các nguồn cấu hình và quy tắc ưu tiên |
| `Binder` | Điều phối đọc cấu hình, conversion và bind sang object |
| `Bindable<T>` | Cung cấp mô tả chính xác kiểu đích và ngữ cảnh binding |
| `ResolvableType` | Biểu diễn kiểu có generic arguments, gồm cấu trúc lồng nhiều tầng |
| `BindResult<T>` | Kết quả binding có/không có giá trị, hỗ trợ lấy giá trị hoặc fallback |
| `@ConfigurationProperties` | Cơ chế declarative được Spring Boot tích hợp tự động vào lifecycle |

Các API này không loại trừ nhau. `@ConfigurationProperties` dùng cơ chế binding của Spring Boot; mã dùng `Binder` trực tiếp là cách truy cập **thủ công, lập trình được** khi cần bind một prefix tùy thời điểm hoặc cấu trúc generic động.

## 4. Ví dụ đầu tiên: `List<String>`

File `application.yml`:

~~~yaml
app:
  servers:
    - alpha.example.test
    - beta.example.test
    - gamma.example.test
~~~

Nếu cần lấy trực tiếp một danh sách trong component:

~~~java
package com.example.service;

import java.util.List;

import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Service;

@Service
public class ServerDirectory {
    private final List<String> servers;

    public ServerDirectory(Environment environment) {
        this.servers = Binder.get(environment)
            .bind("app.servers", Bindable.listOf(String.class))
            .orElseGet(List::of);
    }

    public List<String> servers() {
        return servers;
    }
}
~~~

Khi list được khai báo như YAML trên:

~~~text
servers[0] = alpha.example.test
servers[1] = beta.example.test
servers[2] = gamma.example.test
~~~

Nếu không có `app.servers`, `BindResult.orElseGet(List::of)` cung cấp danh sách trống **theo lựa chọn của mã**. Điều này khác với việc binder tự mặc định mọi list đều trống.

### 4.1. Cùng dữ liệu dưới dạng Properties

~~~properties
app.servers[0]=alpha.example.test
app.servers[1]=beta.example.test
app.servers[2]=gamma.example.test
~~~

`Bindable.listOf(String.class)` vẫn là đích phù hợp. Mã Java không cần biết lúc đó giá trị đến từ YAML hay Properties; binder đọc thông qua các configuration property sources.

### 4.2. Tại sao không gọi `getProperty("app.servers")`?

`Environment.getProperty(...)` hữu ích cho một property riêng lẻ, nhưng YAML list thường được làm phẳng thành các key như `app.servers[0]` và `app.servers[1]`. Không thể giả định có một string đơn `app.servers` chứa toàn bộ danh sách theo đúng dạng muốn parse.

`Binder` hiểu cấu trúc index và conversion của collection. Khi cấu hình đại diện cho một List, nó là lựa chọn thích hợp hơn việc tự phân tích các key bằng chuỗi.

## 5. `List<Endpoint>`: nơi `Bindable` thực sự phát huy tác dụng

Giả sử ứng dụng có danh sách endpoint gồm tên, URL và timeout.

`application.yml`:

~~~yaml
app:
  endpoints:
    - name: catalog
      url: https://catalog.example.test
      timeout: 3s
    - name: inventory
      url: https://inventory.example.test
      timeout: 5s
~~~

Dùng Java record trong Java 17+:

~~~java
package com.example.config;

import java.time.Duration;

public record Endpoint(
        String name,
        String url,
        Duration timeout) {
}
~~~

Đọc trực tiếp bằng Binder:

~~~java
package com.example.service;

import java.util.List;

import com.example.config.Endpoint;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.core.env.Environment;

public class EndpointLoader {

    public static List<Endpoint> load(Environment environment) {
        Binder binder = Binder.get(environment);

        return binder
            .bind("app.endpoints", Bindable.listOf(Endpoint.class))
            .orElseGet(List::of);
    }
}
~~~

`Bindable.listOf(Endpoint.class)` không chỉ mô tả `List`, mà còn bảo đảm binder nhận biết **kiểu phần tử là `Endpoint`**. Với Spring Boot 3.x hỗ trợ record constructor binding, nó có thể chuyển `3s` thành `Duration` và tạo record tương ứng.

Kết quả logic:

~~~text
[
  Endpoint("catalog", "https://catalog.example.test", PT3S),
  Endpoint("inventory", "https://inventory.example.test", PT5S)
]
~~~

Không cần tự đọc:

~~~java
environment.getProperty("app.endpoints[0].name");
environment.getProperty("app.endpoints[0].url");
environment.getProperty("app.endpoints[0].timeout");
~~~

rồi lặp qua các index và tự chuyển đổi kiểu. Khi danh sách dài hay có nested fields, tự xử lý thủ công như vậy rất dễ sai.

### 5.1. Yêu cầu về model

Kiểu phần tử phải có cách tạo/bind phù hợp, ví dụ:

- JavaBean có constructor không tham số và getter/setter.
- Immutable class có constructor binding thích hợp.
- Record có canonical constructor như ví dụ.

`Bindable.listOf(Endpoint.class)` **không tự thêm constructor/setter** cho một class không hỗ trợ binding. Nếu type là object của thư viện bên ngoài và không thể bind trực tiếp, dùng class cấu hình trung gian của ứng dụng rồi tạo vendor object từ dữ liệu đó.

## 6. `Set<T>`: lưu kiểu phần tử của một tập hợp

`Bindable` cũng có factory cho Set:

~~~java
Set<String> roles = Binder.get(environment)
    .bind("app.allowed-roles", Bindable.setOf(String.class))
    .orElseGet(Set::of);
~~~

Ví dụ cấu hình:

~~~yaml
app:
  allowed-roles:
    - viewer
    - editor
    - auditor
~~~

`Set<String>` biểu diễn tập các giá trị, phù hợp khi ứng dụng quan tâm tới **tính duy nhất** hơn thứ tự index. Nếu bạn cần thứ tự chính xác để thử failover hay chạy từng bước, `List` diễn đạt ý định rõ hơn.

Dù dùng `Set` hay `List`, phần tử trong cấu hình vẫn cần convert được sang kiểu `T`. Ví dụ `Bindable.setOf(Integer.class)` cho phép binder biết mỗi phần tử phải là `Integer`, không phải một string giữ nguyên.

## 7. `Map<K,V>`: lưu cả kiểu key và value

Giả sử ứng dụng cần ngưỡng retry cho từng service:

~~~yaml
app:
  retry-limits:
    catalog: 2
    inventory: 4
    billing: 1
~~~

Đích Java:

~~~java
Map<String, Integer> retryLimits = Binder.get(environment)
    .bind(
        "app.retry-limits",
        Bindable.mapOf(String.class, Integer.class))
    .orElseGet(Map::of);
~~~

Thông tin được giữ là:

~~~text
Map
 ├─ K = String
 └─ V = Integer
~~~

Binder biết cần chuyển `2`, `4`, `1` sang `Integer`. Nếu giá trị là văn bản `"many"`, việc bind sang `Integer` có thể thất bại; `Bindable` không thể biến input sai kiểu thành một số hợp lệ.

### 7.1. Map với value là object

Dùng cùng record `Endpoint` nhưng định danh endpoint bằng tên map:

~~~yaml
app:
  endpoints-by-name:
    catalog:
      name: catalog
      url: https://catalog.example.test
      timeout: 3s
    inventory:
      name: inventory
      url: https://inventory.example.test
      timeout: 5s
~~~

Bind:

~~~java
Map<String, Endpoint> endpoints = Binder.get(environment)
    .bind(
        "app.endpoints-by-name",
        Bindable.mapOf(String.class, Endpoint.class))
    .orElseGet(Map::of);
~~~

Khi đó `endpoints.get("catalog")` trả một `Endpoint` đã chuyển đổi các field.

Điểm khác với List: `catalog` và `inventory` là các **key có ý nghĩa**, còn List nhận dạng phần tử bằng index. Điều này ảnh hưởng cách Spring Boot bind cấu hình từ **nhiều nguồn**: Map có thể kết hợp các key, trong khi List được thay thế nguyên danh sách ở nguồn ưu tiên cao hơn.

### 7.2. Khi key là kiểu khác `String`

`Bindable.mapOf(Integer.class, String.class)` cũng diễn đạt kiểu key/value cụ thể:

~~~java
Map<Integer, String> labels = Binder.get(environment)
    .bind(
        "app.port-labels",
        Bindable.mapOf(Integer.class, String.class))
    .orElseGet(Map::of);
~~~

Tuy nhiên, không nên giả định **mọi** dạng key YAML hoặc ký tự đặc biệt sẽ được chuyển theo cùng cách cho mọi map key type. Các key có dấu chấm, dấu gạch chéo hoặc dấu ngoặc có thể cần bracket notation theo quy tắc Spring Boot. Với cấu hình quan trọng, dùng các key đơn giản, kiểm tra binding bằng test và chỉ định rõ yêu cầu map key.

## 8. Các factory method của `Bindable`

Những cách tạo `Bindable` thông dụng:

| Factory method | Kiểu thông tin nhận được | Khi dùng |
| --- | --- | --- |
| `Bindable.of(String.class)` | `String` | Giá trị đơn |
| `Bindable.of(Endpoint.class)` | `Endpoint` | Object riêng |
| `Bindable.listOf(String.class)` | `List<String>` | Danh sách chuỗi |
| `Bindable.listOf(Endpoint.class)` | `List<Endpoint>` | Danh sách object |
| `Bindable.setOf(Integer.class)` | `Set<Integer>` | Tập số |
| `Bindable.mapOf(String.class, Integer.class)` | `Map<String,Integer>` | Map key/value đơn |
| `Bindable.mapOf(String.class, Endpoint.class)` | `Map<String,Endpoint>` | Map có value object |
| `Bindable.of(ResolvableType)` | Kiểu generic phức tạp do `ResolvableType` diễn đạt | Cấu trúc lồng nhau |
| `Bindable.ofInstance(object)` | Kiểu và giá trị instance có sẵn | Binding với object đã tồn tại |

Một ví dụ đồng thời:

~~~java
Binder binder = Binder.get(environment);

String region = binder
    .bind("app.region", Bindable.of(String.class))
    .orElse("vn");

List<String> servers = binder
    .bind("app.servers", Bindable.listOf(String.class))
    .orElseGet(List::of);

Map<String, Integer> limits = binder
    .bind("app.retry-limits",
          Bindable.mapOf(String.class, Integer.class))
    .orElseGet(Map::of);
~~~

`Binder.bind("app.region", String.class)` còn là một overload tiện lợi cho trường hợp không cần tạo `Bindable` thủ công. Nhưng với collections có generic arguments, `Bindable.listOf/mapOf` biểu đạt đích rõ hơn và có kiểu tĩnh tốt hơn.

## 9. Cấu trúc generic lồng nhau: `List<Map<String, RetryPolicy>>`

`listOf(Class<E>)` chỉ nhận `Class` của phần tử trực tiếp. Nhưng phần tử của một danh sách có thể **lại là một kiểu generic**:

~~~java
List<Map<String, RetryPolicy>>
~~~

Ở đây không có `Class<Map<String, RetryPolicy>>`. `Map.class` không biểu diễn được `String` và `RetryPolicy`, nên không thể bảo toàn toàn bộ type graph chỉ bằng `listOf(Map.class)`.

Spring Framework có `org.springframework.core.ResolvableType` để biểu diễn các generic arguments ở nhiều tầng.

### 9.1. Tạo `ResolvableType` lồng nhau

Một model ví dụ:

~~~java
package com.example.config;

import java.time.Duration;

public record RetryPolicy(
        int attempts,
        Duration backoff) {
}
~~~

YAML:

~~~yaml
app:
  retry-groups:
    - catalog:
        attempts: 3
        backoff: 250ms
      inventory:
        attempts: 2
        backoff: 500ms
    - billing:
        attempts: 1
        backoff: 1s
~~~

Khai báo kiểu:

~~~java
import java.util.List;
import java.util.Map;

import com.example.config.RetryPolicy;
import org.springframework.core.ResolvableType;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;

ResolvableType mapType =
    ResolvableType.forClassWithGenerics(
        Map.class,
        ResolvableType.forClass(String.class),
        ResolvableType.forClass(RetryPolicy.class));

ResolvableType listType =
    ResolvableType.forClassWithGenerics(List.class, mapType);

Bindable<List<Map<String, RetryPolicy>>> target =
    Bindable.of(listType);

List<Map<String, RetryPolicy>> groups = binder
    .bind("app.retry-groups", target)
    .orElseGet(List::of);
~~~

Cấu trúc type được giữ:

~~~text
List
 └─ Map
     ├─ K = String
     └─ V = RetryPolicy
          ├─ attempts: int
          └─ backoff: Duration
~~~

Khi binding, Spring Boot có đủ thông tin để tạo `RetryPolicy` và chuyển `250ms`, `500ms`, `1s` thành `Duration` trong từng map value.

### 9.2. Khi nào cần nested generics?

Không phải ứng dụng nào cũng nên cấu hình List chứa Map chứa object. Cấu trúc này hữu ích khi dữ liệu thực sự có nhiều tầng, nhưng cũng tăng độ phức tạp của YAML, validation và test.

Nếu dữ liệu có danh tính rõ ràng, một type chuyên dụng như:

~~~java
public record RetryGroup(Map<String, RetryPolicy> policies) {
}
~~~

có thể giúp model dễ hiểu hơn. Không phải cứ `ResolvableType` diễn đạt được một loại generic là mô hình đó tối ưu cho domain.

## 10. Giữ kiểu qua một `Field` được khai báo sẵn

Trong mã Java có thể có một field chứa generic type đầy đủ. `ResolvableType.forField(...)` đọc thông tin generic từ khai báo field mà không cần lắp ráp từng tầng bằng tay.

Ví dụ:

~~~java
package com.example.config;

import java.util.List;
import java.util.Map;

public final class RetryTypeHolder {
    // Field dùng như điểm giữ type metadata để tham chiếu.
    private List<Map<String, RetryPolicy>> retryGroups;
}
~~~

Đọc metadata và bind:

~~~java
import java.lang.reflect.Field;
import java.util.List;
import java.util.Map;

import org.springframework.core.ResolvableType;
import org.springframework.boot.context.properties.bind.Bindable;

Field field = RetryTypeHolder.class
    .getDeclaredField("retryGroups");

ResolvableType type = ResolvableType.forField(field);

Bindable<List<Map<String, RetryPolicy>>> target =
    Bindable.of(type);

List<Map<String, RetryPolicy>> groups = binder
    .bind("app.retry-groups", target)
    .orElseGet(List::of);
~~~

Đoạn trên cần xử lý `NoSuchFieldException` hoặc khai báo `throws` trong phương thức chứa mã. Đây là ví dụ về **lấy metadata**, không phải lời khuyên tạo một field không dùng trong mọi project.

`ResolvableType.forField` đọc khai báo generic đầy đủ của field khi thông tin còn tồn tại trong metadata phản chiếu. Cách này phù hợp với framework, library hoặc code generic có type declaration sẵn.

**Điểm cần nhớ:** type erasure không có nghĩa mọi generic declaration đều biến mất khỏi metadata. Khai báo field, parameter, generic supertype có thể cung cấp đủ thông tin cho `ResolvableType`; `Class<List>` đơn thuần thì không.

## 11. Vì sao `Bindable.of(List.class)` không tương đương `Bindable.listOf(Endpoint.class)`?

Xét hai cách:

~~~java
Bindable<List> rawTarget = Bindable.of(List.class);

Bindable<List<Endpoint>> typedTarget =
    Bindable.listOf(Endpoint.class);
~~~

Cách đầu chỉ biết collection type là `List`. Cách sau biết **`List<Endpoint>`**. Khi cấu hình là một chuỗi đơn giản, binding raw list đôi khi tạo ra dữ liệu có vẻ đúng; nhưng khi phần tử là object có constructor, enum, `Duration` hay type converter riêng, việc thiếu generic type có thể trở thành lỗi.

Lỗi phổ biến:

~~~java
List raw = binder.bind("app.endpoints", List.class)
    .orElseGet(List::of);

// Tưởng rằng mọi phần tử đã là Endpoint:
Endpoint first = (Endpoint) raw.get(0);
~~~

Nếu phần tử không thực sự là `Endpoint`, cast có thể thất bại. Một lời ép kiểu ở tầng code **không thể chỉ đạo lại binder** sau khi binding xong.

Cách đúng:

~~~java
List<Endpoint> endpoints = binder
    .bind("app.endpoints", Bindable.listOf(Endpoint.class))
    .orElseGet(List::of);
~~~

Bây giờ cả compiler lẫn Binder đều có thông tin type phù hợp. Tuy nhiên, type đúng **không tự xác thực** URL, thời gian chờ dương hay các giới hạn nghiệp vụ; phần validation vẫn cần được thiết kế riêng.

## 12. `BindResult<T>`: lấy giá trị, kiểm tra thiếu và fallback

`Binder.bind(...)` trả `BindResult<T>`, không trực tiếp luôn trả một `T`.

Ví dụ:

~~~java
BindResult<List<String>> result =
    binder.bind("app.servers", Bindable.listOf(String.class));
~~~

Cách dùng:

~~~java
if (result.isBound()) {
    List<String> servers = result.get();
    // Sử dụng servers.
}
else {
    // Không có cấu hình được bind tại prefix này.
}
~~~

Các lựa chọn khác:

~~~java
List<String> servers =
    result.orElseGet(List::of);
~~~

hoặc:

~~~java
List<String> defaultServers = List.of("localhost");
List<String> servers = result.orElse(defaultServers);
~~~

Cần tách ba tình huống:

1. **Không có property để bind:** `isBound()` có thể là `false`, `orElse` cung cấp fallback.
2. **Có property và convert thành công:** `isBound()` là `true`, `get()` cho giá trị.
3. **Có property nhưng không thể chuyển đổi/bind:** Binder có thể ném `BindException` hoặc lỗi liên quan; `orElse` **không tự biến một cấu hình sai kiểu thành fallback**.

Ví dụ:

~~~properties
app.retry-limits.catalog=three
~~~

Bind `Map<String, Integer>` có thể thất bại khi converter gặp `three`. Đừng viết `orElse(Map.of())` và cho rằng nó sẽ tự che mọi lỗi cấu hình. Fallback dành cho **thiếu cấu hình hợp lệ**, không phải cơ chế bỏ qua những override sai.

### 12.1. Nên dùng `get()` khi nào?

`BindResult.get()` thích hợp khi kết quả chắc chắn phải tồn tại; nếu không được bind, nó báo trạng thái không có kết quả. Với cấu hình tùy chọn, dùng `orElse` hoặc `orElseGet` dễ diễn đạt hơn.

Nếu property **bắt buộc theo nghiệp vụ**, nên báo lỗi rõ ràng:

~~~java
List<Endpoint> endpoints = binder
    .bind("app.endpoints", Bindable.listOf(Endpoint.class))
    .orElseThrow(() -> new IllegalStateException(
        "app.endpoints is required"));
~~~

Dòng trên minh họa ý tưởng fail-fast. Khi code dùng API `BindResult` của phiên bản cụ thể, hãy dùng phương thức fallback được hỗ trợ; một cách luôn khả thi là kiểm tra `isBound()` rồi ném exception của ứng dụng nếu cần.

## 13. `Bindable.ofInstance`: target object có sẵn

`Bindable` không chỉ mô tả một type để binder tạo object mới. Nó còn có thể gắn **giá trị đã tồn tại**:

~~~java
NodeSettings settings = new NodeSettings();

Bindable<NodeSettings> target =
    Bindable.ofInstance(settings);

NodeSettings bound = binder
    .bind("app.node", target)
    .orElse(settings);
~~~

Với JavaBean:

~~~java
package com.example.config;

public class NodeSettings {
    private String host;
    private int port = 8080;

    public String getHost() {
        return host;
    }

    public void setHost(String host) {
        this.host = host;
    }

    public int getPort() {
        return port;
    }

    public void setPort(int port) {
        this.port = port;
    }
}
~~~

YAML:

~~~yaml
app:
  node:
    host: node.example.test
    port: 9090
~~~

Target mô tả một instance đã có để binder **có thể sử dụng làm đối tượng hiện tại**. Điều này đặc biệt hữu ích với JavaBean được khởi tạo bởi thư viện khác, hoặc khi cần giữ field initializer/default của object.

Tuy nhiên, đừng mặc định rằng binder **luôn mutate đúng cùng một reference trong mọi trường hợp**. Cách bind object, collections, immutable types và constructor-bound values có thể khác nhau; hãy sử dụng object trả về từ `BindResult` và kiểm tra behavior của type đang dùng.

### 13.1. Với collection generic, cẩn thận metadata từ instance

~~~java
List<Endpoint> existing = new ArrayList<>();

// Không nên giả định chỉ nhìn runtime Class của ArrayList
// là biết generic element type Endpoint.
Bindable<List<Endpoint>> typed =
    Bindable.listOf(Endpoint.class).withExistingValue(existing);
~~~

`List<Endpoint>` bị xóa generic type khỏi runtime class của `ArrayList` thông thường. Vì vậy `Bindable.ofInstance(existing)` có thể không biết chính xác element type từ một instance collection thuần nếu type argument không được lưu trong type metadata riêng.

Khi cần một existing value **và** thông tin element type, cách ghép một `Bindable` đã khai báo generic với `withExistingValue(...)` là rõ ràng hơn.

### 13.2. `withSuppliedValue`

Một số phiên bản Spring Boot hỗ trợ:

~~~java
Bindable<NodeSettings> target =
    Bindable.of(NodeSettings.class)
        .withSuppliedValue(NodeSettings::new);
~~~

Dạng này cung cấp một `Supplier` để lấy object hiện tại/khởi tạo khi binder cần, thay vì phải luôn truyền trước một instance. Chi tiết cách sử dụng và thời điểm supplier được gọi phụ thuộc cơ chế binding; không nên dựa vào supplier để thực hiện IO hoặc tác dụng phụ.

Nếu chỉ cần tạo một đối tượng immutable từ config, thường không cần cung cấp existing instance hay supplier; `Bindable.of(Type.class)` hoặc `Bindable.listOf(...)` là đủ.

## 14. `Bindable.withAnnotations` và metadata ảnh hưởng conversion

Một số annotation của Spring Boot có thể thay đổi cách diễn giải một giá trị cấu hình, ví dụ `@DurationUnit` và `@DataSizeUnit` cho số không có hậu tố. `Bindable` có khả năng mang theo annotations gắn với target.

Ví dụ tưởng tượng một cấu hình timeout không có suffix, nhưng muốn mặc định là giây:

~~~java
import java.time.Duration;
import java.time.temporal.ChronoUnit;

import org.springframework.boot.convert.DurationUnit;

public class TimeoutHolder {
    @DurationUnit(ChronoUnit.SECONDS)
    private Duration timeout;
}
~~~

Khi một framework hoặc đoạn mã reflection có annotation metadata từ field, nó có thể tạo `Bindable` với metadata đó:

~~~java
import java.lang.reflect.Field;
import java.time.Duration;

import org.springframework.boot.context.properties.bind.Bindable;

Field field = TimeoutHolder.class.getDeclaredField("timeout");

Bindable<Duration> target = Bindable
    .of(Duration.class)
    .withAnnotations(field.getAnnotations());

Duration timeout = binder
    .bind("app.timeout", target)
    .orElse(Duration.ofSeconds(5));
~~~

Ví dụ cần xử lý `NoSuchFieldException`; phần liên quan là `withAnnotations(...)`.

Dữ liệu:

~~~yaml
app:
  timeout: 10
~~~

Với conversion của Spring Boot tôn trọng `@DurationUnit(SECONDS)`, số `10` được diễn giải là 10 giây thay vì mặc định 10 mili giây. Đây là lý do `Bindable` không chỉ cần **Class target**, mà đôi khi còn cần **annotation metadata** của nơi khai báo.

Nếu không thực sự cần động hóa binding, cách đơn giản hơn là khai báo property field trực tiếp trong một `@ConfigurationProperties` class; Spring Boot sẽ đọc annotations tương ứng mà không cần viết mã reflection.

### 14.1. Annotation không tạo property source

`withAnnotations(...)` không thêm giá trị cấu hình vào `Environment`, không bật profile và không thay đổi thứ tự ưu tiên nguồn. Nó cung cấp ngữ cảnh cho binder/converter xử lý **target đã xác định**.

Một annotation unit cũng **không** tạo ra fallback khi key bị thiếu. Đơn vị mặc định của một giá trị được cung cấp và giá trị mặc định cho một key không tồn tại là hai vấn đề khác nhau.

## 15. Chọn `Bindable.of(Class)` hay `Bindable.of(ResolvableType)`?

Quy tắc ngắn:

- **Đích đơn giản:** dùng `Bindable.of(MyType.class)`, hoặc truyền `MyType.class` vào `Binder.bind`.
- **List/Set với phần tử là class cụ thể:** dùng `Bindable.listOf(Endpoint.class)` / `Bindable.setOf(String.class)`.
- **Map với key/value là class cụ thể:** dùng `Bindable.mapOf(String.class, Endpoint.class)`.
- **Generic lồng nhiều tầng:** dùng `ResolvableType` rồi `Bindable.of(type)`.
- **Có existing object hoặc annotation metadata:** bắt đầu từ một Bindable có type đầy đủ, sau đó thêm `withExistingValue` / `withAnnotations` khi phù hợp.

Ví dụ về generic type phức tạp khác:

~~~java
// Map<String, List<Integer>>
ResolvableType valueType =
    ResolvableType.forClassWithGenerics(
        List.class, ResolvableType.forClass(Integer.class));

ResolvableType mapType =
    ResolvableType.forClassWithGenerics(
        Map.class,
        ResolvableType.forClass(String.class),
        valueType);

Bindable<Map<String, List<Integer>>> target =
    Bindable.of(mapType);
~~~

Với YAML:

~~~yaml
app:
  scores:
    alpha: [1, 2, 3]
    beta: [4, 5]
~~~

Binder có đủ thông tin để bind một `Map<String, List<Integer>>`. Việc có một phần tử YAML không chuyển được sang số, ví dụ `"abc"`, vẫn là lỗi dữ liệu nguồn chứ không phải lý do để bỏ metadata kiểu.

## 16. Khác biệt giữa manual `Binder` và `@ConfigurationProperties`

Trong nhiều dự án, dùng `@ConfigurationProperties` là lựa chọn chuẩn để ánh xạ nhóm cấu hình lâu dài vào một bean:

~~~java
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppProperties(
        List<Endpoint> endpoints,
        Map<String, Integer> retryLimits) {
}
~~~

Khi đã đăng ký type qua `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties(AppProperties.class)`, Spring Boot tự bind các field theo generic declarations:

~~~java
private final AppProperties appProperties;

public SomeService(AppProperties appProperties) {
    this.appProperties = appProperties;
}
~~~

Bạn **không cần** tự gọi `Bindable.listOf` chỉ để binding một field `List<Endpoint>` đã được khai báo trong class properties.

Mã `Binder` trực tiếp phù hợp khi:

1. Prefix cấu hình được chọn lúc chạy và không cố định tại annotation.
2. Một thư viện muốn nhận tên prefix làm tham số và tạo một cấu trúc Java tại đó.
3. Cần load một nhóm thuộc tính nhỏ độc lập với việc đăng ký một Spring bean properties.
4. Cần tạo một tool quan sát cấu hình hoặc test binding ở mức thấp.
5. Cần truyền một `ResolvableType` được xác định động từ field, method hoặc generic signature.

**Không nên** chuyển mọi configuration properties của dự án thành những lệnh Binder thủ công; như vậy dễ phải tự giải quyết lifecycle, validation, defaults và lỗi cấu hình vốn đã có cơ chế tích hợp trong Spring Boot.

### 16.1. Manual Binder không mặc nhiên giống toàn bộ pipeline auto-configuration

`Binder.get(environment)` tạo một binder từ environment. Nhưng các tình huống đặc biệt như custom conversion service, bind handler, validation tích hợp hoặc metadata chuyên biệt có thể phụ thuộc cách Binder được khởi tạo và cấu hình.

Vì vậy, một lời gọi Binder thủ công **không tự bảo đảm** có mọi behavior validation của một `@ConfigurationProperties` bean được Spring Boot tạo qua toàn bộ infrastructure.

Nếu cần bean được validate nhất quán theo policy, ưu tiên `@Validated` + `@ConfigurationProperties` hoặc chủ động cung cấp handler/validation tương ứng cho manual binding. Đừng coi `Bindable` là một cách tắt validation và vẫn đạt mức an toàn tương đương.

## 17. Source precedence với List và Map: Bindable không sửa quy tắc

Giả sử file mặc định:

~~~yaml
# application.yml
app:
  servers:
    - alpha.example.test
    - beta.example.test
  retry-limits:
    catalog: 2
    inventory: 3
~~~

File theo profile:

~~~yaml
# application-prod.yml
app:
  servers:
    - prod.example.test
  retry-limits:
    catalog: 5
    billing: 1
~~~

Chạy `prod`:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

Khi file profile có ưu tiên cao hơn và không có nguồn khác ghi đè:

~~~text
Bindable.listOf(String.class):
  servers = ["prod.example.test"]

Bindable.mapOf(String.class, Integer.class):
  retry-limits = {
      "catalog": 5,
      "inventory": 3,
      "billing": 1
  }
~~~

Tại sao?

- Với **List**, Spring Boot dùng danh sách từ nguồn ưu tiên cao đã cung cấp danh sách, chứ không nối các phần tử.
- Với **Map**, các key có thể được kết hợp từ nhiều nguồn, trong đó key trùng dùng giá trị từ nguồn ưu tiên cao hơn.

`Bindable.listOf(...)` và `Bindable.mapOf(...)` chỉ nêu đích kiểu dữ liệu, **không tạo quy tắc merge mới**. Nếu muốn thêm `alpha.example.test` vào danh sách production, hãy khai báo danh sách production đầy đủ hoặc thiết kế nguồn dữ liệu khác.

### 17.1. Tra cứu leaf property khác với bind collection

Một lời gọi:

~~~java
environment.getProperty("app.servers[1]");
~~~

có thể trả giá trị từ nguồn thấp nếu nguồn cao không có leaf property cùng tên. Nhưng khi bind toàn bộ `List` từ nhiều property sources, binder áp dụng **quy tắc thay thế List**. Không nên suy ra List sẽ merge theo index chỉ vì `Environment` tra cứu từng key đơn lẻ theo ưu tiên.

## 18. Binding theo prefix động trong thư viện tích hợp

Giả sử hệ thống có nhiều tenant được cấu hình theo các prefix riêng:

~~~yaml
tenants:
  alpha:
    endpoints:
      - name: api
        url: https://alpha.example.test
        timeout: 3s
  beta:
    endpoints:
      - name: api
        url: https://beta.example.test
        timeout: 5s
~~~

Một service nội bộ cần load List endpoint cho một tenant được chọn, mà không muốn khai báo một properties bean riêng cho mọi tenant.

~~~java
import java.util.List;
import java.util.Set;

import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.core.env.Environment;

public final class TenantEndpointLoader {

    private static final Set<String> ALLOWED_TENANTS =
        Set.of("alpha", "beta");

    private final Binder binder;

    public TenantEndpointLoader(Environment environment) {
        this.binder = Binder.get(environment);
    }

    public List<Endpoint> load(String tenant) {
        if (!ALLOWED_TENANTS.contains(tenant)) {
            throw new IllegalArgumentException("Unknown tenant");
        }

        String prefix = "tenants." + tenant + ".endpoints";

        return binder
            .bind(prefix, Bindable.listOf(Endpoint.class))
            .orElseGet(List::of);
    }
}
~~~

`Bindable.listOf(Endpoint.class)` bảo toàn kiểu phần tử cho cả hai prefix. Đây là một trường hợp hợp lý để sử dụng Binder trực tiếp thay vì một bean `@ConfigurationProperties` cho từng tenant.

**Lưu ý an toàn:** prefix động phải được tạo từ một tập tên được kiểm soát hoặc validate cẩn thận. Không lấy nguyên dữ liệu không tin cậy rồi nối thành tên property để có thể truy cập cấu hình nhạy cảm ở namespace khác.

Việc gọi Binder ở thời điểm runtime **không đảm bảo config data tự refresh** khi file trên đĩa thay đổi. `Environment` thường được tạo từ cấu hình nạp khi startup; khả năng thay đổi động phụ thuộc nguồn cấu hình và cơ chế refresh riêng.

## 19. Thêm validation sau khi dùng `Bindable`

`Bindable` giữ generic type, nhưng không xác minh các quy tắc nghiệp vụ. Ví dụ `Endpoint` có:

~~~java
public record Endpoint(String name, String url, Duration timeout) {
}
~~~

Binder có thể chuyển `timeout: -3s` thành một `Duration` âm, nếu conversion hợp lệ. Điều đó không có nghĩa endpoint có cấu hình hợp lệ.

Với manual Binder, có thể validate sau khi bind:

~~~java
List<Endpoint> endpoints = binder
    .bind("app.endpoints", Bindable.listOf(Endpoint.class))
    .orElseGet(List::of);

if (endpoints.isEmpty()) {
    throw new IllegalStateException(
        "app.endpoints must contain at least one endpoint");
}

for (Endpoint endpoint : endpoints) {
    if (endpoint.name() == null || endpoint.name().isBlank()) {
        throw new IllegalStateException(
            "app.endpoints contains an endpoint without name");
    }

    if (endpoint.timeout() == null
            || endpoint.timeout().isNegative()
            || endpoint.timeout().isZero()) {
        throw new IllegalStateException(
            "app.endpoints timeout must be positive");
    }
}
~~~

Trong ứng dụng thật, còn nên kiểm tra URL, scheme HTTPS, độ dài, giới hạn số lượng endpoint và các yêu cầu riêng. Chỉ hiển thị tên property và loại lỗi, không log credential hay token nếu endpoint chứa thông tin nhạy cảm.

Với `@ConfigurationProperties`, có thể dùng:

~~~java
import java.util.List;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
    @NotEmpty @Valid List<EndpointEntry> endpoints) {

    public record EndpointEntry(
        @NotBlank String name,
        @NotBlank String url,
        @NotNull Duration timeout) {
    }
}
~~~

Ví dụ này dùng Spring Boot 3.x với Jakarta Bean Validation; để chạy cần một implementation thích hợp, thường là `spring-boot-starter-validation`. `@NotNull` không kiểm tra timeout dương; thêm constraint hoặc custom validation theo yêu cầu.

### 19.1. Vì sao không chỉ thêm annotation rồi gọi manual Binder?

Một `Bindable` có thể mang annotation metadata, nhưng việc **chạy validator** còn phụ thuộc bind handler/infrastructure. Manual `Binder.get(environment).bind(...)` không nên được coi là tự kích hoạt đầy đủ mọi Jakarta validation giống một bean `@ConfigurationProperties` do Boot quản lý.

Nếu project yêu cầu validation tự động cùng startup lifecycle, dùng annotation-driven properties bean thường ít sai sót hơn. Nếu manual binding là bắt buộc, bổ sung kiểm tra rõ ràng hoặc tạo handler phù hợp.

## 20. Xử lý lỗi kiểu và tên property

### 20.1. Tên key hợp lệ

Trong ví dụ:

~~~java
binder.bind("app.retry-limits",
            Bindable.mapOf(String.class, Integer.class));
~~~

Tên prefix phải tương ứng với cấu hình. Spring Boot ưu tiên canonical property names dạng kebab-case như `retry-limits`. Việc viết nhầm `retry-limit` (khác số nhiều) không tự ánh xạ sang `retry-limits`.

### 20.2. Generic type không phù hợp

YAML:

~~~yaml
app:
  retry-limits:
    catalog: many
~~~

Java:

~~~java
Map<String, Integer> limits = binder
    .bind("app.retry-limits",
          Bindable.mapOf(String.class, Integer.class))
    .get();
~~~

Binder có thể thất bại khi chuyển `"many"` sang `Integer`. Đây không phải lỗi do `mapOf` thiếu metadata; ngược lại, **vì type được giữ là Integer nên binder phát hiện dữ liệu sai kiểu**.

### 20.3. Missing property không đồng nghĩa conversion failure

Nếu toàn bộ `app.retry-limits` không được khai báo, `BindResult` có thể ở trạng thái unbound. Khi đó có thể dùng fallback. Nếu có giá trị nhưng sai kiểu, kết quả là lỗi cần sửa, không nên che bằng một map mặc định.

### 20.4. Đừng dùng raw types trong các helper

Không nên thiết kế helper:

~~~java
public List loadList(Binder binder, String prefix) {
    return binder.bind(prefix, List.class).orElseGet(List::of);
}
~~~

Vì caller không có đảm bảo type.

Một helper generic có thể nhận loại phần tử:

~~~java
public static <E> List<E> loadList(
        Binder binder,
        String prefix,
        Class<E> elementType) {

    return binder.bind(prefix, Bindable.listOf(elementType))
        .orElseGet(List::of);
}
~~~

Lúc gọi:

~~~java
List<Endpoint> endpoints =
    loadList(binder, "app.endpoints", Endpoint.class);
~~~

Thông tin element type được truyền rõ ràng và Java compiler có thể kiểm tra kiểu của kết quả.

## 21. Unit test `Bindable.listOf` và `mapOf`

Một test nhỏ giúp xác minh hai yếu tố: các phần tử được tạo **đúng kiểu**, và dữ liệu sai kiểu sẽ không bị âm thầm chấp nhận.

Ví dụ dùng `MockEnvironment` của `spring-test` và Spring Boot Binder:

~~~java
package com.example.config;

import java.time.Duration;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.mock.env.MockEnvironment;

import static org.assertj.core.api.Assertions.assertThat;

class BindableExampleTest {

    record Endpoint(String name, String url, Duration timeout) {
    }

    @Test
    void bindsListWithTypedElements() {
        MockEnvironment env = new MockEnvironment()
            .withProperty("app.endpoints[0].name", "catalog")
            .withProperty("app.endpoints[0].url",
                    "https://catalog.example.test")
            .withProperty("app.endpoints[0].timeout", "3s");

        List<Endpoint> list = Binder.get(env)
            .bind("app.endpoints", Bindable.listOf(Endpoint.class))
            .get();

        assertThat(list).hasSize(1);
        assertThat(list.get(0)).isInstanceOf(Endpoint.class);
        assertThat(list.get(0).timeout())
            .isEqualTo(Duration.ofSeconds(3));
    }

    @Test
    void bindsMapWithIntegerValues() {
        MockEnvironment env = new MockEnvironment()
            .withProperty("app.retry-limits.catalog", "2")
            .withProperty("app.retry-limits.inventory", "4");

        Map<String, Integer> result = Binder.get(env)
            .bind("app.retry-limits",
                  Bindable.mapOf(String.class, Integer.class))
            .get();

        assertThat(result).containsEntry("catalog", 2);
        assertThat(result).containsEntry("inventory", 4);
    }
}
~~~

Để chạy test trong project Spring Boot, thường dùng `spring-boot-starter-test`, chứa JUnit/AssertJ và Spring Test.

Trong các dự án khác nhau, khi bind record bằng constructor, compiler cần metadata tên tham số và phiên bản Spring Boot hỗ trợ record binding. Nếu bạn viết class bất biến thông thường thay vì record, hãy đảm bảo constructor binding đúng cơ chế.

### 21.1. Test nested generic bằng `ResolvableType`

Giữ record `RetryPolicy`:

~~~java
record RetryPolicy(int attempts, Duration backoff) {
}
~~~

Tạo target:

~~~java
ResolvableType mapType =
    ResolvableType.forClassWithGenerics(
        Map.class,
        ResolvableType.forClass(String.class),
        ResolvableType.forClass(RetryPolicy.class));

ResolvableType listType =
    ResolvableType.forClassWithGenerics(List.class, mapType);

Bindable<List<Map<String, RetryPolicy>>> target =
    Bindable.of(listType);
~~~

Với một `MockEnvironment` cung cấp:

~~~properties
app.retry-groups[0].catalog.attempts=3
app.retry-groups[0].catalog.backoff=250ms
~~~

Test có thể khẳng định:

~~~java
List<Map<String, RetryPolicy>> groups = Binder.get(env)
    .bind("app.retry-groups", target)
    .get();

assertThat(groups).hasSize(1);
assertThat(groups.get(0).get("catalog").backoff())
    .isEqualTo(Duration.ofMillis(250));
~~~

Kết quả này minh họa generic metadata được bảo toàn qua **hai tầng**: phần tử của list là map và value của map là `RetryPolicy`.

## 22. Các nhầm lẫn thường gặp

| Nhầm lẫn | Hiểu đúng |
| --- | --- |
| “`List.class` đã là `List<Endpoint>`.” | `Class<List>` không chứa generic argument `Endpoint`. |
| “Ép kiểu `(List<Endpoint>)` sau bind là đủ.” | Cast không cung cấp element type cho Binder; có thể lỗi khi dùng phần tử. |
| “`Bindable` chứa giá trị lấy từ YAML.” | Nó mô tả **đích**; `Binder` mới đọc property sources và tạo kết quả. |
| “`Bindable.listOf` tự hợp nhất danh sách giữa các profile.” | Không. List binding vẫn tuân theo quy tắc replacement theo nguồn ưu tiên cao. |
| “`mapOf` và `listOf` giống nhau.” | Map có key/value type, List có element type; merge semantics cũng khác. |
| “`mapOf(String.class, Map.class)` giữ mọi tầng generic bên trong.” | `Map.class` là raw type của value; dùng `ResolvableType` nếu cần generic lồng nhau. |
| “`ofInstance(new ArrayList<Endpoint>())` chắc chắn suy ra Endpoint.” | Java type erasure có thể làm mất element type ở runtime; nên dùng typed `Bindable` và existing value nếu cần. |
| “`BindResult.orElse` bỏ qua mọi conversion error.” | Không; fallback chủ yếu xử lý trường hợp không bind được vì thiếu key. |
| “`Bindable.withAnnotations` làm key xuất hiện trong Environment.” | Không; annotations cung cấp metadata cho binding. |
| “`Binder.get(environment)` luôn thực thi mọi validation của `@ConfigurationProperties`.” | Không nên giả định; manual binding có thể cần handler/validation riêng. |
| “Generic type đúng thì URL/timeout chắc chắn hợp lệ.” | Binder xử lý kiểu, validation nghiệp vụ là trách nhiệm khác. |
| “Mỗi lần gọi Binder là Spring Boot tự reload file config.” | Không; điều đó phụ thuộc nguồn và cơ chế refresh. |
| “Một prefix động nối từ user input luôn an toàn.” | Cần giới hạn/validate prefix để tránh đọc nhầm namespace. |
| “Một map key chứa dấu đặc biệt luôn bind như chữ và dấu chấm bình thường.” | Có quy tắc key notation, cần bracket notation khi phù hợp. |

## 23. Bài tập áp dụng

### 23.1. Bài 1 — List số nguyên

Cho:

~~~yaml
app:
  allowed-ports:
    - 8080
    - 8081
    - 9090
~~~

**Yêu cầu:** dùng Binder lấy `List<Integer>`, không dùng raw list.

**Đáp án:**

~~~java
List<Integer> ports = Binder.get(environment)
    .bind("app.allowed-ports", Bindable.listOf(Integer.class))
    .orElseGet(List::of);
~~~

Kết quả gồm ba phần tử `8080`, `8081`, `9090` kiểu `Integer`.

### 23.2. Bài 2 — Map thời gian chờ

Cho:

~~~yaml
app:
  service-timeouts:
    catalog: 2s
    inventory: 5s
~~~

**Yêu cầu:** lấy `Map<String, Duration>`.

**Đáp án:**

~~~java
Map<String, Duration> timeouts = Binder.get(environment)
    .bind("app.service-timeouts",
          Bindable.mapOf(String.class, Duration.class))
    .orElseGet(Map::of);
~~~

Giá trị `catalog` là `Duration.ofSeconds(2)`, `inventory` là `Duration.ofSeconds(5)`.

### 23.3. Bài 3 — Nested generic

Cho:

~~~yaml
app:
  matrix:
    - east: [1, 2]
      west: [3, 4]
    - central: [5]
~~~

**Yêu cầu:** lấy `List<Map<String, List<Integer>>>`. Vì phần tử List là Map có value là List, `Bindable.listOf(Map.class)` không đủ.

**Hướng giải:**

~~~java
ResolvableType integers =
    ResolvableType.forClassWithGenerics(
        List.class, ResolvableType.forClass(Integer.class));

ResolvableType map =
    ResolvableType.forClassWithGenerics(
        Map.class, ResolvableType.forClass(String.class), integers);

ResolvableType outerList =
    ResolvableType.forClassWithGenerics(List.class, map);

Bindable<List<Map<String, List<Integer>>>> target =
    Bindable.of(outerList);

List<Map<String, List<Integer>>> matrix =
    Binder.get(environment)
        .bind("app.matrix", target)
        .orElseGet(List::of);
~~~

Nếu binder tạo kết quả đúng, `matrix.get(0).get("east")` là list số nguyên `[1, 2]`.

### 23.4. Bài 4 — Khi nào cần fallback?

**Câu hỏi:** `app.servers` không có trong bất kỳ nguồn nào; nên xử lý bằng `get()` hay `orElseGet(List::of)`?

**Đáp án:** nếu danh sách server là tùy chọn, dùng `orElseGet(List::of)`; nếu bắt buộc để ứng dụng hoạt động, báo lỗi rõ ràng khi `!result.isBound()`, tránh âm thầm chạy với danh sách rỗng.

### 23.5. Bài 5 — Khi generic type không đúng

**Câu hỏi:** `app.service-timeouts.catalog=abc` nhưng target là `Map<String, Duration>`. Có nên mong Binder trả về map trống vì `orElse(Map.of())` không?

**Đáp án:** không. `abc` không convert được thành `Duration` là lỗi cấu hình; fallback không phải cơ chế nuốt conversion failure.

## 24. Checklist khi dùng `Bindable` trong dự án

1. **Xác định type đích đầy đủ:** `List<Endpoint>`, `Map<String,Integer>` hay một nested generic.
2. **Không dùng raw `List.class`/`Map.class`** khi cần phần tử/value kiểu cụ thể.
3. **Chọn factory phù hợp:** `listOf`, `setOf`, `mapOf`; nếu generic lồng nhau dùng `ResolvableType`.
4. **Sử dụng đúng nguồn:** `Binder.get(environment)` lấy cấu hình từ môi trường hiện tại; thứ tự ưu tiên vẫn theo property sources.
5. **Xử lý thiếu property tường minh:** `BindResult.isBound/get/orElse/orElseGet` theo contract nghiệp vụ.
6. **Không che lỗi conversion bằng default:** dữ liệu sai kiểu nên được sửa hoặc báo lỗi rõ.
7. **Kiểm tra model:** record/constructor/JavaBean có cách tạo được và conversion cho các field.
8. **Phân biệt List và Map:** List thường replacement giữa nguồn ưu tiên; Map có thể kết hợp key.
9. **Cân nhắc existing instance:** `ofInstance`/`withExistingValue` hữu ích nhưng không tự chữa type erasure của một collection raw.
10. **Nếu có annotation ảnh hưởng conversion:** dùng metadata phù hợp hoặc khai báo `@ConfigurationProperties` để Boot xử lý tự động.
11. **Không bỏ qua validation:** type conversion thành công không bảo đảm chính sách nghiệp vụ đúng.
12. **Test đúng cấp:** unit test cho List/Map/nested generic, lỗi sai kiểu và trường hợp thiếu prefix.
13. **Giữ tiền tố động an toàn:** chỉ chấp nhận namespace từ allowlist hoặc validate chặt.
14. **Không giả định reload:** việc tạo Binder không thay thế cơ chế refresh configuration.
15. **Chọn công cụ đơn giản nhất:** với một nhóm cấu hình cố định, `@ConfigurationProperties` thường rõ và dễ bảo trì hơn manual Binder.

## 25. Tóm tắt

**`Bindable` là cầu nối giữa generic type information của Java và cơ chế `Binder` của Spring Boot.**

Khi một ứng dụng cần bind:

~~~java
List<Endpoint>
Map<String, Duration>
List<Map<String, RetryPolicy>>
~~~

hãy cung cấp đầy đủ thông tin type:

~~~java
Bindable.listOf(Endpoint.class)
Bindable.mapOf(String.class, Duration.class)
Bindable.of(resolvableType)
~~~

Thay vì:

~~~java
List.class
Map.class
~~~

và hy vọng ép kiểu sau binding sẽ khôi phục dữ liệu đúng.

- **`Binder`** đọc và bind cấu hình.
- **`Bindable<T>`** mô tả đích, bao gồm generics, annotation metadata và có thể là existing value.
- **`ResolvableType`** dùng khi cấu trúc generic lồng nhau không biểu diễn được bằng một `Class` đơn giản.
- **`BindResult<T>`** biểu diễn kết quả có/không bind được, không tự nuốt lỗi chuyển đổi kiểu.
- **`@ConfigurationProperties`** là đường đi thông thường khi muốn bind một nhóm cấu hình cố định trong application context; manual Binder/Bindable dành cho các nhu cầu nâng cao có chủ đích.

### Tài liệu tham khảo

- Spring Boot 3.4 Javadoc — Bindable: https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/context/properties/bind/Bindable.html
- Spring Boot 3.4 Javadoc — Binder: https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/context/properties/bind/Binder.html
- Spring Boot Reference — Type-safe Configuration Properties: https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties
- Spring Framework Javadoc — ResolvableType: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/ResolvableType.html
- Spring Boot Configuration Binding (wiki, thông tin nền): https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-Configuration-Binding

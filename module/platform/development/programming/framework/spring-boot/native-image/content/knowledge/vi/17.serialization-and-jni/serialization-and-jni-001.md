# Phân biệt Java serialization với chuyển đổi JSON

## 1. Vì sao cần phân biệt hai cơ chế này?

Trong ứng dụng Spring Boot, dữ liệu thường phải được chuyển đổi để lưu trữ, truyền qua mạng hoặc trao đổi với hệ thống khác. Hai cách thường gặp là **Java Object Serialization** và **JSON serialization/deserialization**. Cả hai đều có thể được gọi chung là "serialization", nhưng chúng tạo ra định dạng dữ liệu khác nhau, có mục tiêu khác nhau và cần metadata khác nhau khi biên dịch thành GraalVM Native Image.

Ví dụ dịch vụ `order-service` có một đối tượng `OrderSnapshot` cần lưu tạm trạng thái, đồng thời có `OrderRequest` và `OrderResponse` dùng làm payload REST API.

- Java serialization chuyển một object graph Java thành luồng byte theo giao thức serialization của Java, thường qua `ObjectOutputStream` và `ObjectInputStream`.
- JSON chuyển dữ liệu thành văn bản theo cấu trúc object/array/value của JSON, thường dùng Jackson trong Spring Boot.

Khi chạy trên JVM, hai cơ chế đều có thể hoạt động nếu được cấu hình đúng. Với **GraalVM Native Image**, Java serialization cần metadata serialization cho các kiểu trong object graph; JSON binding thường cần reflection/binding metadata cho các DTO mà thư viện JSON truy cập động. Đăng ký nhầm loại hint sẽ không giải quyết được lỗi.

Sau bài này, bạn có thể:

- Giải thích sự khác nhau về định dạng, tính di động, versioning và object graph.
- Chọn Java serialization hay JSON theo mục đích của ứng dụng.
- Viết ví dụ chuyển đổi dữ liệu bằng `ObjectOutputStream` và Jackson `ObjectMapper`.
- Hiểu rủi ro khi deserialize dữ liệu không đáng tin cậy.
- Cấu hình metadata phù hợp cho từng cơ chế khi build Spring Boot Native Image.

## 2. Java Object Serialization là gì?

Java Object Serialization là cơ chế của Java để ghi object graph thành chuỗi byte và dựng lại object graph từ chuỗi byte đó. Các API cơ bản nằm trong package `java.io`:

- `Serializable`: marker interface cho class có thể được serialize theo cơ chế mặc định.
- `ObjectOutputStream`: ghi object vào một `OutputStream`.
- `ObjectInputStream`: đọc và tái tạo object từ một `InputStream`.
- `serialVersionUID`: mã định danh phiên bản của class trong serialization protocol.

### 2.1. Khai báo một class có thể serialize

```java
package com.example.orders.snapshot;

import java.io.Serial;
import java.io.Serializable;

public final class OrderSnapshot implements Serializable {

    @Serial
    private static final long serialVersionUID = 1L;

    private final String orderId;
    private final long totalAmount;
    private transient String temporaryAccessToken;

    public OrderSnapshot(String orderId, long totalAmount) {
        this.orderId = orderId;
        this.totalAmount = totalAmount;
    }

    public String getOrderId() {
        return orderId;
    }

    public long getTotalAmount() {
        return totalAmount;
    }
}
```

`Serializable` không yêu cầu class phải có getter/setter hoặc constructor không tham số. Java serialization mặc định lưu trạng thái các field không `static` và không `transient`, theo quy tắc của serialization protocol.

Một số điểm cần nhớ:

- `static` thuộc về class nên không được lưu như trạng thái riêng của từng object.
- `transient` đánh dấu field không được ghi theo cơ chế mặc định. Khi deserialize, field đó nhận giá trị mặc định nếu custom serialization không khôi phục nó.
- `serialVersionUID` giúp kiểm tra tính tương thích giữa class ghi và class đọc. Nếu UID không khớp, có thể phát sinh `InvalidClassException`.
- Nếu một object tham chiếu tới object khác trong graph, các kiểu liên quan cũng phải đáp ứng quy tắc serialization; nếu không, quá trình ghi có thể ném `NotSerializableException`.

### 2.2. Ghi và đọc object

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;

OrderSnapshot snapshot = new OrderSnapshot("ORD-100", 250_000L);

byte[] bytes;
try (ByteArrayOutputStream buffer = new ByteArrayOutputStream();
     ObjectOutputStream output = new ObjectOutputStream(buffer)) {
    output.writeObject(snapshot);
    output.flush();
    bytes = buffer.toByteArray();
}

OrderSnapshot restored;
try (ByteArrayInputStream buffer = new ByteArrayInputStream(bytes);
     ObjectInputStream input = new ObjectInputStream(buffer)) {
    restored = (OrderSnapshot) input.readObject();
}

System.out.println(restored.getOrderId());
```

Kết quả là một luồng byte chứa thông tin class và trạng thái object theo Java serialization protocol. Nó không phải JSON và không có mục tiêu trở thành định dạng trao đổi độc lập ngôn ngữ.

### 2.3. Java serialization bảo toàn object graph

Java serialization có thể lưu mối quan hệ tham chiếu, object được dùng chung và chu trình tham chiếu trong graph. Ví dụ hai field cùng trỏ tới một object thì khi đọc lại, chúng có thể tiếp tục trỏ tới cùng một instance trong graph được khôi phục.

Đây là điểm khác với JSON thông thường: JSON biểu diễn cấu trúc dữ liệu dạng cây gồm object, array và primitive values. JSON không tự biểu diễn identity hoặc chu trình tham chiếu của object Java. Nếu object graph có vòng lặp, thư viện JSON thường cần cấu hình đặc biệt, identity reference hoặc DTO chuyển đổi để tránh lỗi đệ quy.

## 3. JSON là gì và Spring Boot chuyển đổi JSON như thế nào?

JSON (*JavaScript Object Notation*) là định dạng văn bản độc lập ngôn ngữ, biểu diễn dữ liệu bằng object, array, string, number, boolean và `null`. Trong Spring Boot, Jackson thường được dùng làm JSON mapper thông qua HTTP message converters.

JSON mô tả **dữ liệu**, không mô tả một object Java hoàn chỉnh. Khi chuyển JSON về Java, mapper cần biết kiểu đích và cách ánh xạ field/property, constructor hoặc creator.

DTO dùng cho JSON không cần triển khai `Serializable`. Jackson ánh xạ property theo cấu hình và metadata của mapper; nó không ghi object theo Java serialization protocol.

### 3.1. DTO dùng cho REST API

```java
package com.example.orders.api;

public record OrderRequest(String productCode, int quantity) {
}
```

```java
package com.example.orders.api;

public record OrderResponse(String orderId, long totalAmount) {
}
```

Controller Spring MVC có thể nhận và trả DTO:

```java
package com.example.orders.api;

import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    @PostMapping
    OrderResponse create(@RequestBody OrderRequest request) {
        return new OrderResponse("ORD-100", request.quantity() * 125_000L);
    }
}
```

Với cấu hình Spring Boot tiêu chuẩn, Jackson được tích hợp qua HTTP message converter. Controller không cần tự gọi `ObjectOutputStream` hoặc tự chuyển DTO thành byte.

### 3.2. Chuyển đổi trực tiếp bằng Jackson `ObjectMapper`

Khi cần chuyển đổi JSON bên ngoài HTTP controller, có thể dùng `ObjectMapper`:

```java
package com.example.orders.api;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

public class OrderJsonCodec {

    private final ObjectMapper objectMapper;

    public OrderJsonCodec(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public String write(OrderResponse response) throws JsonProcessingException {
        return objectMapper.writeValueAsString(response);
    }

    public OrderResponse read(String json) throws JsonProcessingException {
        return objectMapper.readValue(json, OrderResponse.class);
    }
}
```

Trong Spring Boot, nên inject `ObjectMapper` do ứng dụng cấu hình thay vì tạo `new ObjectMapper()` tùy tiện ở mỗi nơi. Mapper được auto-configure có thể đã chứa module, naming strategy, date/time support và các custom serializer/deserializer mà ứng dụng đang dùng.

JSON kết quả có dạng văn bản, ví dụ:

```json
{
  "orderId": "ORD-100",
  "totalAmount": 250000
}
```

Một hệ thống viết bằng Java, JavaScript, Go hoặc Python đều có thể đọc dữ liệu này nếu tuân theo cùng cấu trúc JSON và quy ước schema.

## 4. So sánh Java serialization và JSON

| Tiêu chí | Java Object Serialization | JSON serialization/deserialization |
|---|---|---|
| Định dạng | Binary stream theo giao thức Java | Văn bản JSON |
| Mục tiêu | Ghi/khôi phục object graph Java | Trao đổi dữ liệu giữa hệ thống và ngôn ngữ khác nhau |
| Phụ thuộc class Java | Cao; dữ liệu gắn với class và serialization contract | Thấp hơn; gắn với cấu trúc dữ liệu/schema |
| Object graph và identity | Hỗ trợ tham chiếu dùng chung và chu trình | JSON thông thường là cây; identity/cycle cần quy ước riêng |
| Versioning | Dùng `serialVersionUID` và quy tắc tương thích serialization | Thường quản lý qua schema, field tùy chọn, version API và quy tắc unknown field |
| Field | Ghi trạng thái field theo quy tắc serialization, trừ `static`/`transient` và custom behavior | Ánh xạ property theo cấu hình mapper, annotation và creator |
| Đa ngôn ngữ | Không phải định dạng trao đổi phù hợp cho client không phải Java | Phổ biến và độc lập ngôn ngữ |
| Đọc bằng mắt | Khó, vì là binary stream | Dễ quan sát và debug hơn |
| Rủi ro nổi bật | Deserialize dữ liệu không tin cậy có thể kích hoạt gadget chain hoặc hành vi nguy hiểm | Cấu hình polymorphic typing không an toàn, payload quá lớn, parser/resource exhaustion và validation thiếu |
| Native Image hints | Serialization metadata cho các kiểu trong object graph | Reflection/binding metadata cho các kiểu Jackson cần truy cập; resource hints nếu đọc file JSON từ classpath |

Không có quy tắc rằng Java serialization luôn nhanh hơn hoặc JSON luôn nhỏ hơn. Kết quả phụ thuộc kích thước object graph, cấu trúc dữ liệu, serializer, cấu hình nén, cách lưu trữ và workload. Hãy benchmark nếu hiệu năng là tiêu chí quyết định.

## 5. Versioning và khả năng tương thích dữ liệu

### 5.1. `serialVersionUID` trong Java serialization

Khi class triển khai `Serializable`, Java dùng `serialVersionUID` để xác định phiên bản serialization. Nếu stream được ghi bởi một phiên bản class có UID khác với class đang đọc, `ObjectInputStream` có thể ném `InvalidClassException`.

Khai báo UID tường minh giúp tránh việc compiler tự tính UID thay đổi bất ngờ do một số thay đổi class. Tuy nhiên, **giữ nguyên UID không tự bảo đảm tương thích về ngữ nghĩa**. Nếu đổi ý nghĩa field, thay đổi kiểu dữ liệu hoặc thay đổi cách diễn giải trạng thái, ứng dụng vẫn cần chiến lược chuyển đổi dữ liệu cũ.

Với dữ liệu cần lưu lâu dài hoặc chia sẻ giữa nhiều phiên bản dịch vụ, cần kiểm thử các trường hợp:

- Class mới đọc stream cũ.
- Class cũ đọc stream mới (nếu hệ thống cần hỗ trợ chiều này).
- Field được thêm, bỏ hoặc đổi tên.
- Kiểu trong object graph thay đổi.
- Custom `readObject`, `writeObject`, `readResolve` hoặc `writeReplace` thay đổi.

Nếu dữ liệu có tuổi thọ dài, hãy cân nhắc một định dạng có schema/versioning rõ ràng thay vì phụ thuộc hoàn toàn vào cấu trúc class Java.

### 5.2. Versioning JSON

JSON không tự cung cấp schema hoặc versioning. Ứng dụng cần thiết kế contract, ví dụ:

```json
{
  "schemaVersion": 2,
  "orderId": "ORD-100",
  "totalAmount": 250000,
  "currency": "VND"
}
```

Khi thêm field tùy chọn, client cũ có thể bỏ qua nếu mapper và contract cho phép. Khi đổi kiểu field, đổi ý nghĩa hoặc xóa field đang được sử dụng, cần kế hoạch tương thích API và migration.

Một số quy tắc thực tế:

- Dùng DTO riêng cho API thay vì serialize trực tiếp entity nội bộ.
- Xác định field bắt buộc/tùy chọn và giá trị mặc định.
- Quy định cách xử lý field chưa biết để tránh vô tình làm mất dữ liệu hoặc che giấu lỗi contract.
- Dùng OpenAPI/JSON Schema hoặc tài liệu contract tương đương khi nhiều client cùng tích hợp.
- Kiểm thử payload từ phiên bản client cũ và payload được tạo bởi phiên bản server mới.

## 6. Bảo mật: đặc biệt cẩn trọng với Java deserialization

### 6.1. Không deserialize dữ liệu không đáng tin cậy

`ObjectInputStream.readObject()` có thể khởi tạo object và kích hoạt logic trong quá trình deserialize. Một số thư viện có gadget chain khiến dữ liệu serialized được tạo có chủ ý có thể dẫn tới hành vi nguy hiểm trong ứng dụng.

Không nên nhận byte Java serialization trực tiếp từ client không tin cậy, không mở endpoint công khai để gọi `readObject()` với dữ liệu tùy ý và không coi `Serializable` là một ranh giới bảo mật.

Nếu buộc phải đọc dữ liệu serialized từ nguồn được kiểm soát, dùng `ObjectInputFilter` để giới hạn class, kích thước graph, độ sâu và số tham chiếu phù hợp với use case. Ví dụ tối giản cho object graph chỉ gồm `OrderSnapshot` và `String`:

```java
package com.example.orders.snapshot;

import java.io.IOException;
import java.io.InputStream;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;

public final class OrderSnapshotReader {

    public OrderSnapshot read(InputStream source)
            throws IOException, ClassNotFoundException {
        try (ObjectInputStream input = new ObjectInputStream(source)) {
            input.setObjectInputFilter(info -> {
                if (info.depth() > 10 || info.references() > 100) {
                    return ObjectInputFilter.Status.REJECTED;
                }

                Class<?> type = info.serialClass();
                if (type == null) {
                    return ObjectInputFilter.Status.UNDECIDED;
                }

                if (type == OrderSnapshot.class || type == String.class) {
                    return ObjectInputFilter.Status.ALLOWED;
                }

                return ObjectInputFilter.Status.REJECTED;
            });

            return (OrderSnapshot) input.readObject();
        }
    }
}
```

Đây là allowlist minh họa cho graph rất nhỏ. Khi graph có collection, enum hoặc kiểu con hợp lệ, phải thêm đúng kiểu vào allowlist và giới hạn kích thước phù hợp. `UNDECIDED` không có nghĩa là cho phép mọi class; filter khác hoặc cơ chế mặc định vẫn có thể quyết định. Với dữ liệu không đáng tin cậy, lựa chọn an toàn hơn thường là không dùng Java native deserialization.

### 6.2. JSON cũng cần kiểm soát đầu vào

JSON thường phù hợp hơn cho API công khai vì contract dữ liệu minh bạch và không trực tiếp khôi phục object graph Java tùy ý. Tuy vậy, JSON không tự an toàn:

- Giới hạn kích thước request, độ sâu lồng nhau và số phần tử.
- Validate dữ liệu đầu vào bằng Bean Validation hoặc quy tắc nghiệp vụ.
- Không bật polymorphic default typing rộng cho dữ liệu không tin cậy.
- Nếu cần polymorphic JSON, dùng danh sách subtype được cho phép và contract rõ ràng.
- Tránh để JSON parser tiêu thụ CPU/bộ nhớ không giới hạn qua payload lớn hoặc cấu trúc lồng sâu.

## 7. Java serialization trong GraalVM Native Image

### 7.1. Vì sao cần serialization hints?

GraalVM Native Image phân tích mã reachable và cần biết các kiểu có thể được tái tạo qua Java serialization. Việc `readObject()` nhận object từ stream có thể khiến kiểu được sử dụng theo đường động mà reachability analysis không suy ra đầy đủ từ code thông thường.

Spring cung cấp `RuntimeHints.serialization()` để khai báo các kiểu được dùng trong Java serialization. Hints này thuộc **serialization metadata**, không phải reflection hints thông thường.

### 7.2. Đăng ký kiểu serialized bằng `RuntimeHintsRegistrar`

```java
package com.example.orders.snapshot;

import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public class OrderSerializationRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.serialization().registerType(OrderSnapshot.class);
    }
}
```

Nếu object graph chứa thêm kiểu serializable như `OrderLineSnapshot`, hãy đăng ký các kiểu đó khi chúng không được framework hoặc cơ chế metadata khác suy ra:

```java
hints.serialization().registerType(OrderSnapshot.class);
hints.serialization().registerType(OrderLineSnapshot.class);
```

Đăng ký type root nhưng bỏ sót kiểu trong graph có thể khiến một đường deserialize cụ thể thất bại. Hãy kiểm thử bằng object graph thực tế, gồm cả nested objects và custom serialization khi có.

### 7.3. Gắn hints vào module sở hữu

```java
package com.example.orders.snapshot;

import java.io.IOException;
import java.io.ObjectOutputStream;
import java.io.OutputStream;

import org.springframework.context.annotation.ImportRuntimeHints;
import org.springframework.stereotype.Component;

@Component
@ImportRuntimeHints(OrderSerializationRuntimeHints.class)
public class OrderSnapshotStore {

    public void save(OrderSnapshot snapshot, OutputStream destination)
            throws IOException {
        try (ObjectOutputStream output = new ObjectOutputStream(destination)) {
            output.writeObject(snapshot);
        }
    }
}
```

`@ImportRuntimeHints` giúp registrar gắn với component sử dụng Java serialization. Nếu module snapshot không được import hoặc bean bị điều kiện cấu hình loại bỏ trong AOT, hints tương ứng không nhất thiết được đóng góp qua component đó.

### 7.4. Kiểm thử serialization hints

```java
package com.example.orders.snapshot;

import org.junit.jupiter.api.Test;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.predicate.RuntimeHintsPredicates;

import static org.assertj.core.api.Assertions.assertThat;

class OrderSerializationRuntimeHintsTests {

    @Test
    void registersOrderSnapshotSerialization() {
        RuntimeHints hints = new RuntimeHints();
        new OrderSerializationRuntimeHints().registerHints(
                hints, getClass().getClassLoader());

        assertThat(RuntimeHintsPredicates.serialization()
                .onType(OrderSnapshot.class))
                .accepts(hints);
    }
}
```

Predicate xác nhận metadata đã được đăng ký. Nó không chứng minh stream tương thích giữa mọi phiên bản class hoặc mọi object graph đều có thể đọc lại. Cần có test round-trip và integration test chạy trên native executable.

## 8. JSON binding trong GraalVM Native Image

### 8.1. JSON không dùng serialization hints

Khi Jackson ánh xạ JSON vào `OrderRequest` hoặc chuyển `OrderResponse` thành JSON, đó là quá trình **data binding**. Nó có thể cần truy cập constructor, accessor, field hoặc annotation metadata thông qua reflection.

Vì vậy, không dùng:

```java
hints.serialization().registerType(OrderResponse.class);
```

để giải quyết một lỗi Jackson không tìm thấy constructor/property trong native image. API trên mô tả Java Object Serialization. Với JSON binding, cần reflection/binding hints.

### 8.2. Spring AOT tự suy ra nhiều kiểu DTO

Với controller Spring MVC/WebFlux khai báo kiểu request/response rõ ràng, Spring AOT và các tích hợp JSON có thể phân tích signature để tạo metadata cần thiết. Không nên đăng ký thủ công mọi DTO ngay từ đầu.

Tuy nhiên, nếu ứng dụng gọi `ObjectMapper` trực tiếp với kiểu chỉ được xác định động, hoặc sử dụng custom serializer/deserializer mà AOT không nhìn thấy, cần khai báo reflection hints phù hợp.

### 8.3. Dùng `@RegisterReflectionForBinding`

Spring cung cấp `@RegisterReflectionForBinding` để đăng ký reflection hints phục vụ data binding cho các kiểu được chỉ định:

```java
package com.example.orders.api;

import org.springframework.aot.hint.annotation.RegisterReflectionForBinding;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@RegisterReflectionForBinding({OrderRequest.class, OrderResponse.class})
class OrderJsonRuntimeConfiguration {
}
```

Đây là lựa chọn phù hợp khi kiểu JSON được dùng qua mapper tùy chỉnh hoặc đường code mà Spring AOT không thể tự suy ra. Chỉ thêm các DTO thực sự cần binding metadata.

### 8.4. Dùng `RuntimeHintsRegistrar` khi cần kiểm soát chi tiết

Nếu cần đăng ký reflection cho một kiểu cụ thể, có thể dùng `RuntimeHintsRegistrar`:

```java
package com.example.orders.api;

import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public class OrderJsonRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.reflection().registerType(
                OrderResponse.class,
                MemberCategory.INVOKE_PUBLIC_CONSTRUCTORS,
                MemberCategory.INVOKE_PUBLIC_METHODS);
    }
}
```

Gắn registrar bằng `@ImportRuntimeHints` vào module sở hữu mapper. Mức metadata cần thiết phụ thuộc cách Jackson tạo instance và đọc/ghi property; ví dụ trên là minh họa cho một kiểu DTO có public constructor và accessor. Với record, private field, custom creator hoặc serializer đặc biệt, hãy kiểm tra nhu cầu thực tế và dùng `@RegisterReflectionForBinding` khi phù hợp.

### 8.5. JSON resource là một loại hint khác nữa

Nếu ứng dụng đọc một file JSON tĩnh từ classpath, ví dụ `schemas/order-v2.json`, vấn đề có thể là **resource hint**, không phải serialization hay reflection hint:

```java
hints.resources().registerPattern("schemas/order-v2.json");
```

Ba nhu cầu cần phân biệt:

| Tình huống | Loại metadata |
|---|---|
| `ObjectInputStream.readObject()` dựng lại `OrderSnapshot` | Serialization hints |
| Jackson bind JSON vào `OrderRequest` bằng reflection | Reflection/binding hints |
| Đọc `schemas/order-v2.json` từ classpath | Resource hints |

### 8.6. JNI không phải là một định dạng serialization

JNI (*Java Native Interface*) là cơ chế để Java gọi mã native hoặc để mã native tương tác với Java. JNI không quy định payload phải dùng Java serialization hay JSON. Một thư viện native có thể nhận `byte[]`, chuỗi UTF-8 hoặc cấu trúc dữ liệu theo hợp đồng riêng; định dạng payload vẫn phải được xác định độc lập.

Trong Native Image, JNI hints mô tả các class/member Java mà mã native cần truy cập. Chúng không thay thế serialization hints cho `ObjectInputStream`, reflection/binding hints cho Jackson hoặc resource hints cho file JSON. Thư viện native đi kèm cũng phải tương thích với hệ điều hành, kiến trúc CPU và ABI của image đích.

## 9. Kiểm thử hai cơ chế độc lập

### 9.1. Java serialization round-trip

```java
package com.example.orders.snapshot;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class OrderSnapshotSerializationTests {

    @Test
    void writesAndReadsOrderSnapshot() throws Exception {
        OrderSnapshot original = new OrderSnapshot("ORD-100", 250_000L);
        byte[] bytes;

        try (ByteArrayOutputStream buffer = new ByteArrayOutputStream();
             ObjectOutputStream output = new ObjectOutputStream(buffer)) {
            output.writeObject(original);
            bytes = buffer.toByteArray();
        }

        try (ObjectInputStream input = new ObjectInputStream(
                new ByteArrayInputStream(bytes))) {
            OrderSnapshot restored = (OrderSnapshot) input.readObject();
            assertThat(restored.getOrderId()).isEqualTo("ORD-100");
            assertThat(restored.getTotalAmount()).isEqualTo(250_000L);
        }
    }
}
```

Test này xác nhận Java serialization contract và các field cần khôi phục. Nếu class có custom `writeObject/readObject`, `readResolve`, `Externalizable` hoặc nested graph, bổ sung trường hợp tương ứng.

### 9.2. JSON round-trip

```java
package com.example.orders.api;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class OrderJsonCodecTests {

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void writesAndReadsOrderResponse() throws Exception {
        OrderResponse original = new OrderResponse("ORD-100", 250_000L);

        String json = objectMapper.writeValueAsString(original);
        OrderResponse restored = objectMapper.readValue(json, OrderResponse.class);

        assertThat(restored).isEqualTo(original);
    }
}
```

Test dùng mapper do Spring Boot cấu hình, giúp kiểm tra đúng module Jackson và custom configuration của ứng dụng. Nếu dùng Jackson module hoặc serializer tùy chỉnh, test phải chạy với cùng cấu hình runtime.

### 9.3. Chạy cả hai test trên native executable

JVM round-trip thành công không bảo đảm native round-trip thành công. Cần chạy các luồng thực tế trên native image:

- Ghi và đọc `OrderSnapshot` qua Java serialization.
- Xử lý payload JSON qua controller hoặc `ObjectMapper`.
- Kiểm tra custom serializer/deserializer, polymorphic types và nested DTO nếu có.
- Kiểm tra resource JSON/schema nếu ứng dụng tải từ classpath.
- Kiểm tra tương thích dữ liệu đã lưu từ phiên bản ứng dụng trước nếu cần hỗ trợ nâng cấp.

## 10. Chọn định dạng theo use case

| Use case | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| REST API công khai | JSON | Client đa ngôn ngữ, dễ kiểm tra và quản lý contract |
| Message giữa nhiều loại service | JSON hoặc định dạng schema-based khác | Không buộc consumer dùng Java serialization |
| Cache nội bộ ngắn hạn giữa các tiến trình cùng phiên bản Java | Có thể cân nhắc Java serialization hoặc codec khác | Cần đánh giá versioning, bảo mật và hiệu năng |
| Lưu object graph Java có identity/cycle | Java serialization có thể biểu diễn graph, nhưng phải cân nhắc an toàn và khả năng nâng cấp | Bảo toàn reference graph; class coupling cao |
| Lưu trữ lâu dài hoặc tích hợp nhiều phiên bản | JSON có schema/versioning hoặc định dạng dữ liệu có schema rõ ràng | Dễ migration và tương tác giữa phiên bản/ngôn ngữ |
| Dữ liệu đến từ người dùng hoặc hệ thống bên ngoài không tin cậy | JSON với validation và giới hạn parser | Tránh Java native deserialization không tin cậy |

Đây là hướng lựa chọn tổng quát, không phải luật tuyệt đối. Với dữ liệu lớn hoặc yêu cầu hiệu năng cao, có thể cần benchmark thêm Avro, Protobuf hoặc codec khác có schema rõ ràng.

## 11. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `NotSerializableException` | Một kiểu trong object graph không triển khai `Serializable` hoặc không được custom serialization xử lý | Kiểm tra toàn bộ graph, loại field không cần bằng `transient` hoặc dùng DTO phù hợp |
| `InvalidClassException` | `serialVersionUID` không khớp hoặc class serialization contract thay đổi | Kiểm tra UID, field và chiến lược migration dữ liệu |
| Field trở về `null`/giá trị mặc định sau deserialize | Field `transient`, không được ghi hoặc custom read logic không khôi phục | Kiểm tra serialization contract và `readObject` |
| Java serialization lỗi trên native image | Thiếu serialization metadata cho một hoặc nhiều kiểu trong graph | Dùng `hints.serialization().registerType(...)` và test native round-trip |
| Jackson báo không tìm thấy constructor/property trên native | Thiếu reflection/binding metadata hoặc custom mapper không được AOT phân tích | Kiểm tra `@RegisterReflectionForBinding` hoặc reflection hints |
| JSON file không tìm thấy trên native | Resource không được giữ lại trong executable | Đăng ký `hints.resources()` cho đường dẫn classpath cần dùng |
| JSON round-trip khác kết quả JVM | Custom module/serializer hoặc cấu hình ObjectMapper không được dùng giống nhau | Inject mapper Spring, kiểm tra cấu hình và native integration test |
| JSON deserialize thất bại với subtype | Polymorphic metadata/subtype chưa được khai báo hoặc không được cho phép | Dùng subtype allowlist và hints phù hợp; không bật default typing rộng |
| Deserialize dữ liệu không tin cậy gây rủi ro | Java serialization không có filter/allowlist hoặc JSON polymorphic typing quá rộng | Không nhận Java serialized data không tin cậy; dùng filter và giới hạn parser |

## 12. Bài thực hành: cùng một dữ liệu, hai cách biểu diễn

**Bối cảnh:** dịch vụ `order-service` lưu một snapshot nội bộ và cung cấp REST API trả `OrderResponse`.

### Bước 1 — Tạo model

Tạo `OrderSnapshot implements Serializable` có `serialVersionUID` tường minh. Tạo `OrderRequest` và `OrderResponse` làm DTO JSON riêng. Không dùng cùng một class cho cả persistence nội bộ và API nếu hai contract có vòng đời khác nhau.

### Bước 2 — Thử Java serialization

Ghi snapshot bằng `ObjectOutputStream`, đọc lại bằng `ObjectInputStream`, kiểm tra các field. Bổ sung test cho nested object và `transient` field nếu có.

### Bước 3 — Thử JSON

Inject `ObjectMapper` từ Spring Boot, chuyển `OrderResponse` thành JSON và đọc lại. Kiểm tra tên field, null handling, date/time format và unknown property theo contract ứng dụng.

### Bước 4 — Cấu hình native metadata

- Java serialization: đăng ký `OrderSnapshot` và các kiểu trong graph bằng `RuntimeHints.serialization()` nếu Spring AOT chưa suy ra nhu cầu.
- JSON: ưu tiên metadata tự suy ra từ controller; với mapper động, dùng `@RegisterReflectionForBinding` hoặc reflection hints.
- JSON resource: đăng ký resource pattern riêng nếu đọc file schema/template từ classpath.

### Bước 5 — Build và kiểm thử native

Build native executable/container image. Chạy cả Java serialization round-trip và JSON round-trip trên native. Nếu một cơ chế lỗi, xác định loại metadata tương ứng trước khi bổ sung hints.

### Phiếu kết quả

| Hạng mục | Java serialization | JSON/Jackson |
|---|---|---|
| Model | `OrderSnapshot` | `OrderRequest`, `OrderResponse` |
| Định dạng | Binary object stream | JSON text |
| API | `ObjectOutputStream` / `ObjectInputStream` | `ObjectMapper` / HTTP message converter |
| Versioning | `serialVersionUID` và serialization contract | Schema/API version và field rules |
| Native metadata | Serialization hints | Reflection/binding hints; resource hints nếu cần |
| JVM round-trip | _(PASS/FAIL)_ | _(PASS/FAIL)_ |
| Native round-trip | _(PASS/FAIL)_ | _(PASS/FAIL)_ |
| Security review | Input source, `ObjectInputFilter` | Validation, subtype allowlist, payload limits |

## 13. Ghi nhớ

Java Object Serialization lưu và khôi phục object graph Java thành binary stream; JSON biểu diễn dữ liệu dưới dạng văn bản có thể trao đổi giữa nhiều ngôn ngữ và hệ thống. Java serialization gắn chặt với class và serialization contract, trong khi JSON cần schema/API contract do ứng dụng quản lý. Hai cơ chế có cách versioning, bảo mật và metadata Native Image khác nhau.

Với GraalVM Native Image, dùng **serialization hints** cho `ObjectInputStream`/`ObjectOutputStream`; dùng **reflection/binding hints** cho Jackson khi AOT không tự suy ra được kiểu; dùng **resource hints** nếu ứng dụng đọc file JSON từ classpath. Không dùng `RuntimeHints.serialization()` để sửa lỗi JSON binding. Luôn kiểm thử cả hai đường chuyển đổi trên native executable và không deserialize Java object stream từ nguồn không đáng tin cậy.

### Tài liệu tham khảo chính thức

- [Java SE — Object Serialization Specification](https://docs.oracle.com/en/java/javase/25/docs/specs/serialization/)
- [Java SE — `ObjectInputFilter`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/ObjectInputFilter.html)
- [Spring Framework — Runtime Hints and AOT](https://docs.spring.io/spring-framework/reference/core/aot.html)
- [Spring Framework — `SerializationHints` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aot/hint/SerializationHints.html)
- [Spring Framework — `RegisterReflectionForBinding` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aot/hint/annotation/RegisterReflectionForBinding.html)
- [Spring Boot — JSON Support](https://docs.spring.io/spring-boot/reference/features/json.html)
- [GraalVM Native Image — Serialization Metadata](https://www.graalvm.org/latest/reference-manual/native-image/metadata/)

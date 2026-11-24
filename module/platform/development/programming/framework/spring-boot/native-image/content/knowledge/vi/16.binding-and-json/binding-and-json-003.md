# Jackson với DTO, record, enum và các thành viên truy cập động

Trong ứng dụng Spring Boot, Jackson thường chuyển JSON thành DTO khi nhận request và chuyển object thành JSON khi trả response hoặc gọi dịch vụ bên ngoài. Để làm việc đó, Jackson phải khám phá cấu trúc kiểu dữ liệu: constructor, tham số constructor, field, getter, setter, record component, enum constant và các phương thức được đánh dấu bằng annotation. Một số đường truy cập chỉ được thực hiện **động qua reflection**.

Trên JVM, những truy cập này thường hoạt động nhờ metadata class có sẵn. Với **GraalVM Native Image**, reachability analysis diễn ra ở build time; các constructor, field hoặc method chỉ được Jackson gọi qua reflection cần được nhận diện và đăng ký phù hợp. Vì thế, một DTO có thể deserialize tốt bằng JAR nhưng lỗi khi chạy native executable.

Bài học thuộc chương **Binding và JSON** của module **`SPRING_BOOT_NATIVE_IMAGE`**. Nội dung tập trung vào cách Jackson làm việc với POJO, record, enum, nested DTO, polymorphism và các thành viên truy cập động; cách Spring AOT suy luận reflection hints; và cách kiểm thử JSON thực tế trong native application. Đây là phần thực hành quan trọng của mục tiêu module: biên dịch Spring Boot bằng Spring AOT, xử lý reflection/resource, kiểm tra tương thích, đóng gói container và đánh giá startup/memory.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao Jackson cần những thành viên nào khi serialize và deserialize DTO.
- Thiết kế DTO dạng POJO hoặc Java record với constructor/property rõ ràng.
- Ánh xạ enum sang giá trị JSON ổn định bằng annotation.
- Hiểu các cơ chế `@JsonAnyGetter`, `@JsonAnySetter`, `@JsonCreator`, `@JsonValue` và polymorphic type metadata.
- Nhận biết các truy cập reflection không hiển nhiên trong custom serializer, mixin và thư viện client.
- Phân biệt những hints Spring AOT tự suy ra với các hints cần đăng ký tường minh.
- Kiểm thử cả chiều JSON → object và object → JSON trên native executable.

## 2. Jackson nhìn một DTO như thế nào?

Jackson xây dựng mô hình property từ những thành phần mà nó nhận diện trên class:

| Thành phần | Vai trò thường gặp |
|---|---|
| Constructor hoặc factory method | Tạo object khi deserialize |
| Tham số constructor | Nhận giá trị JSON để tạo object bất biến |
| Getter | Đọc giá trị khi serialize |
| Setter | Gán giá trị khi deserialize vào object mutable |
| Field | Có thể được dùng trực tiếp nếu visibility/configuration cho phép |
| Record component | Đại diện property và tham số canonical constructor |
| Enum constant / method được chú thích | Ánh xạ enum sang tên hoặc giá trị JSON |
| Method có `@JsonAnyGetter` / `@JsonAnySetter` | Đọc/ghi các property động không được khai báo thành field cố định |

Jackson có thể nhận diện thành viên bằng quy ước đặt tên, annotation hoặc cấu hình visibility. Ví dụ, `getCustomerId()` thường được xem là getter của property `customerId`; `setCustomerId(String)` là setter tương ứng. Nếu một class chỉ có private field và không có constructor/property phù hợp, cách Jackson truy cập nó sẽ phụ thuộc annotation và mapper configuration.

**Serialize** và **deserialize** đi theo hai hướng khác nhau:

- Serialize: Jackson đọc giá trị từ getter/field/record component rồi ghi thành JSON.
- Deserialize: Jackson đọc token JSON, chọn constructor/factory method hoặc tạo object, sau đó gán giá trị qua constructor/setter/field.

Một class có thể serialize thành công nhưng deserialize thất bại, hoặc ngược lại. Khi kiểm thử Native Image, cần kiểm tra cả hai chiều nếu ứng dụng dùng cả hai.

## 3. POJO DTO: constructor, getter, setter và field

Các import `com.fasterxml.jackson.*` trong những ví dụ POJO/record/enum bên dưới minh họa **Jackson 2** (thường gặp với Spring Boot 3.x). Với Jackson 3, các annotation tương ứng nằm trong package `tools.jackson.annotation`; hãy dùng đồng bộ annotation, mapper và module cùng major version.

Một POJO đơn giản có thể được Jackson nhận diện theo JavaBean conventions:

~~~java
package com.example.orders.api;

public class OrderRequest {

    private String customerId;
    private int quantity;

    public OrderRequest() {
    }

    public String getCustomerId() {
        return customerId;
    }

    public void setCustomerId(String customerId) {
        this.customerId = customerId;
    }

    public int getQuantity() {
        return quantity;
    }

    public void setQuantity(int quantity) {
        this.quantity = quantity;
    }
}
~~~

Với cấu trúc này, Jackson thường dùng constructor không tham số rồi gọi setter để gán dữ liệu. Khi serialize, Jackson đọc getter để lấy giá trị.

JSON đầu vào:

~~~json
{
  "customerId": "C-100",
  "quantity": 3
}
~~~

Đối tượng kết quả có `customerId = "C-100"` và `quantity = 3`.

### Đổi tên property JSON

Nếu API bên ngoài dùng tên khác với tên Java, dùng `@JsonProperty`:

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;

public class OrderRequest {

    @JsonProperty("customer_id")
    private String customerId;

    @JsonProperty("item_count")
    private int quantity;

    public OrderRequest() {
    }

    public String getCustomerId() {
        return customerId;
    }

    public void setCustomerId(String customerId) {
        this.customerId = customerId;
    }

    public int getQuantity() {
        return quantity;
    }

    public void setQuantity(int quantity) {
        this.quantity = quantity;
    }
}
~~~

`@JsonProperty` có thể đặt trên field, getter, setter hoặc tham số creator. Hãy đặt annotation ở một vị trí rõ ràng để tránh định nghĩa property trùng hoặc xung đột giữa field và accessor.

### Chấp nhận tên cũ bằng alias

Khi API đang chuyển từ tên `customerId` sang `customer_id`, có thể chấp nhận cả hai trong giai đoạn migration:

~~~java
import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonProperty;

public class OrderRequest {
    @JsonProperty("customer_id")
    @JsonAlias("customerId")
    private String customerId;

    // Constructor, getter và setter...
}
~~~

`@JsonAlias` chủ yếu giúp **đọc** các tên đầu vào thay thế; tên được ghi ra khi serialize vẫn theo property name chính. Điều này hữu ích khi tương thích ngược với payload cũ.

### Chỉ định constructor rõ ràng

Với DTO bất biến không có setter, dùng `@JsonCreator` và `@JsonProperty` để chỉ rõ cách tạo object:

~~~java
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;

public class ImmutableOrder {

    private final String orderId;
    private final int quantity;

    @JsonCreator
    public ImmutableOrder(
            @JsonProperty("order_id") String orderId,
            @JsonProperty("quantity") int quantity) {
        this.orderId = orderId;
        this.quantity = quantity;
    }

    public String getOrderId() {
        return orderId;
    }

    public int getQuantity() {
        return quantity;
    }
}
~~~

Jackson phải nhận diện constructor và tham số tương ứng. Trong native executable, nếu đường tạo object dựa trên reflection mà không được hints bao phủ, deserialize có thể lỗi ngay khi request đi vào.

**Đừng dựa vào tên tham số constructor một cách ngầm định** nếu build không giữ parameter names hoặc mapper không bật tính năng tương ứng. Annotation `@JsonProperty` làm contract JSON rõ ràng và ít phụ thuộc cấu hình compiler hơn.

## 4. Java record: DTO bất biến gọn hơn

Java record khai báo dữ liệu qua record components:

~~~java
public record OrderRequest(
        String customerId,
        int quantity) {
}
~~~

Jackson hỗ trợ record trong các phiên bản hiện đại. Khi deserialize, Jackson dùng canonical constructor và các record components; khi serialize, nó đọc giá trị của các component.

JSON:

~~~json
{
  "customerId": "C-100",
  "quantity": 3
}
~~~

Record không cần getter/setter theo kiểu JavaBean. Accessor được sinh tự động theo tên component, ví dụ `customerId()` và `quantity()`.

### Đổi tên record component trong JSON

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;

public record OrderRequest(
        @JsonProperty("customer_id") String customerId,
        @JsonProperty("item_count") int quantity) {
}
~~~

Annotation đặt trực tiếp trên component giúp Jackson ánh xạ tên JSON với tham số canonical constructor.

### Record có nested DTO

~~~java
public record AddressDto(String city, String country) {
}

public record CustomerDto(
        String customerId,
        AddressDto address) {
}

public record OrderLineDto(String sku, int quantity) {
}

public record OrderResponse(
        String orderId,
        CustomerDto customer,
        List<OrderLineDto> lines) {
}
~~~

Khi đăng ký reflection hints cho kiểu ngoài cùng, Spring binding hints có thể xử lý các kiểu được dùng bắc cầu trong property và record components. Tuy nhiên, subtype được chọn bằng discriminator, kiểu được nạp động hoặc member truy cập theo quy tắc riêng của thư viện cần được kiểm tra độc lập.

### Record không tự giải quyết mọi vấn đề JSON

Record phù hợp cho DTO bất biến, nhưng cần chú ý:

- Mỗi component là một phần của canonical constructor; payload thiếu field có thể tạo giá trị mặc định hoặc lỗi tùy kiểu/configuration.
- Record lồng nhau cần được Jackson nhận diện đúng type.
- Nếu dùng polymorphism, concrete subtype vẫn cần được cấu hình và kiểm tra.
- Custom serializer/deserializer có thể truy cập các member theo cách riêng.
- Một record component có generic type phức tạp không làm mất nhu cầu kiểm thử type information.

## 5. Enum: tên Java và giá trị JSON

Mặc định, Jackson thường ánh xạ enum theo tên constant. Ví dụ:

~~~java
public enum OrderStatus {
    NEW,
    PROCESSING,
    COMPLETED,
    CANCELLED
}
~~~

JSON có thể chứa `"PROCESSING"`.

### Dùng `@JsonProperty` cho từng enum constant

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;

public enum OrderStatus {
    @JsonProperty("new")
    NEW,

    @JsonProperty("in-progress")
    PROCESSING,

    @JsonProperty("done")
    COMPLETED,

    @JsonProperty("cancelled")
    CANCELLED
}
~~~

Đây là cách dễ đọc khi mỗi constant có một chuỗi JSON cố định.

### Dùng `@JsonValue` khi enum có mã riêng

~~~java
import com.fasterxml.jackson.annotation.JsonValue;

public enum PaymentState {
    PENDING("P"),
    APPROVED("A"),
    DECLINED("D");

    private final String code;

    PaymentState(String code) {
        this.code = code;
    }

    @JsonValue
    public String code() {
        return code;
    }
}
~~~

Khi serialize, `PaymentState.APPROVED` được ghi thành `"A"` thay vì `"APPROVED"`. Để deserialize chuỗi code thành enum, có thể định nghĩa factory method:

~~~java
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;

public enum PaymentState {
    PENDING("P"),
    APPROVED("A"),
    DECLINED("D");

    private final String code;

    PaymentState(String code) {
        this.code = code;
    }

    @JsonValue
    public String code() {
        return code;
    }

    @JsonCreator
    public static PaymentState fromCode(String code) {
        for (PaymentState state : values()) {
            if (state.code.equals(code)) {
                return state;
            }
        }
        throw new IllegalArgumentException("Unknown payment state: " + code);
    }
}
~~~

Ở đây, `@JsonValue` xác định giá trị ghi ra, còn `@JsonCreator` chỉ ra cách đọc giá trị đầu vào. Hãy xác định rõ cách xử lý code lạ, `null`, chữ hoa/chữ thường và dữ liệu cũ theo contract API.

### Enum và Native Image

Enum thường dễ xử lý hơn kiểu object có nhiều member, nhưng không nên giả định mọi đường truy cập đều là truy cập tĩnh. Nếu serializer dùng reflection để gọi factory method, custom enum converter hoặc nạp subtype theo tên, cần kiểm tra các member đó trong native build. Đừng đăng ký reflection rộng chỉ vì một enum được dùng trong JSON; bắt đầu bằng native test và diagnostic thực tế.

## 6. Các thành viên truy cập động: `@JsonAnyGetter` và `@JsonAnySetter`

Một số API cho phép object mang thêm thuộc tính không biết trước tại thời điểm compile. Jackson cung cấp `@JsonAnyGetter` và `@JsonAnySetter` để xử lý các thuộc tính mở rộng này.

~~~java
import com.fasterxml.jackson.annotation.JsonAnyGetter;
import com.fasterxml.jackson.annotation.JsonAnySetter;
import java.util.LinkedHashMap;
import java.util.Map;

public class PartnerPayload {

    private String partnerId;
    private final Map<String, Object> attributes = new LinkedHashMap<>();

    public String getPartnerId() {
        return partnerId;
    }

    public void setPartnerId(String partnerId) {
        this.partnerId = partnerId;
    }

    @JsonAnySetter
    public void addAttribute(String name, Object value) {
        attributes.put(name, value);
    }

    @JsonAnyGetter
    public Map<String, Object> attributes() {
        return attributes;
    }

    public String calculateSignature() {
        return partnerId + ":" + attributes.size();
    }
}
~~~

Với payload:

~~~json
{
  "partnerId": "P-42",
  "region": "apac",
  "priority": 2,
  "enabled": true
}
~~~

`partnerId` đi vào property cố định; các key `region`, `priority`, `enabled` được chuyển vào map `attributes`. Khi serialize, `@JsonAnyGetter` trải các entry của map ra cùng cấp với `partnerId`.

### Vì sao đây là truy cập động?

Jackson gọi phương thức được đánh dấu để xử lý property mà class không khai báo getter/setter riêng cho từng key. Tên key và kiểu value được quyết định từ JSON runtime. Trong Native Image, cần xác nhận các method này và kiểu dữ liệu chứa map được truy cập đúng.

Nếu `@RegisterReflectionForBinding(PartnerPayload.class)` chưa đủ cho một method đặc thù theo cấu hình serializer, hãy đọc diagnostic để xác định method bị thiếu. Có thể đăng ký invocation hint cho đúng method bằng `RuntimeHintsRegistrar`; tránh mở toàn bộ private methods của package nếu chỉ cần hai method được đánh dấu.

### Không nên dùng `Map<String, Object>` mà bỏ qua kiểm soát dữ liệu

`Object` có thể đại diện cho string, number, boolean, map hoặc list lồng nhau. Nếu nghiệp vụ yêu cầu kiểu cụ thể, nên kiểm tra và chuyển đổi giá trị sau khi parse, hoặc định nghĩa DTO rõ ràng cho phần dữ liệu đã biết. Reflection hints không xác thực schema và không thay thế validation.

## 7. Nested DTO, collection và generic type

JSON thường chứa object lồng nhau hoặc danh sách:

~~~java
public record OrderLine(
        String sku,
        int quantity,
        BigDecimal unitPrice) {
}

public record OrderRequest(
        String orderId,
        List<OrderLine> lines,
        Map<String, String> labels) {
}
~~~

Jackson có thể suy ra các phần tử của `List<OrderLine>` và value type của `Map<String, String>` từ generic signature khi compile giữ metadata cần thiết. Tuy nhiên, nếu code chỉ truyền `Object.class`, dùng raw `List.class`, hoặc tạo type bằng tên class runtime, thông tin generic có thể bị mất.

Ví dụ đọc list trực tiếp:

~~~java
List<OrderLine> lines = objectMapper.readValue(
        json,
        new TypeReference<List<OrderLine>>() {});
~~~

`TypeReference` giữ generic type để Jackson biết phần tử là `OrderLine`. Trong native executable, hãy kiểm tra cả kiểu wrapper và phần tử khi generic type được xây dựng động hoặc dùng API thư viện trong thân method.

Với Jackson 3, API type-reference vẫn có vai trò tương tự, nhưng package/API cụ thể phụ thuộc module đã dùng. Tránh trộn `com.fasterxml.jackson.*` của Jackson 2 với `tools.jackson.*` của Jackson 3 trong cùng một mapper.

## 8. Polymorphic DTO: interface và nhiều subtype

Một DTO có thể khai báo property theo interface nhưng JSON chứa nhiều implementation:

~~~java
public interface PaymentMethod {
}

public record CardPayment(String lastFourDigits) implements PaymentMethod {
}

public record BankTransfer(String bankCode) implements PaymentMethod {
}

public record PaymentRequest(String paymentId, PaymentMethod method) {
}
~~~

Để Jackson biết subtype nào tương ứng với discriminator, có thể dùng `@JsonTypeInfo` và `@JsonSubTypes`:

~~~java
import com.fasterxml.jackson.annotation.JsonSubTypes;
import com.fasterxml.jackson.annotation.JsonTypeInfo;

@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "kind")
@JsonSubTypes({
        @JsonSubTypes.Type(value = CardPayment.class, name = "card"),
        @JsonSubTypes.Type(value = BankTransfer.class, name = "bank")
})
public interface PaymentMethod {
}
~~~

JSON:

~~~json
{
  "paymentId": "PAY-900",
  "method": {
    "kind": "card",
    "lastFourDigits": "4242"
  }
}
~~~

Native Image phải giữ các concrete subtype và những constructor/property cần cho Jackson. Nếu AOT không suy ra subtype từ cấu hình serializer, đăng ký chúng tường minh, ví dụ:

~~~java
@Configuration(proxyBeanMethods = false)
@RegisterReflectionForBinding({
        PaymentRequest.class,
        CardPayment.class,
        BankTransfer.class
})
class PaymentJsonHints {
}
~~~

`@RegisterReflectionForBinding` cung cấp reflection hints cho kiểu binding; nó **không tự cấu hình discriminator**, không xác thực subtype được phép và không thay thế `@JsonTypeInfo`/`@JsonSubTypes`. Với dữ liệu đến từ bên ngoài, chỉ cho phép các subtype đã kiểm soát; không bật cơ chế nạp class tùy ý từ tên do người dùng gửi.

## 9. Custom serializer, deserializer và mixin

Jackson có thể gọi custom serializer/deserializer thay vì tự introspect DTO. Đây là nơi thường xuất hiện truy cập động tới member khác.

### Jackson 2 với Spring Boot 3.x

Spring Boot 3.x tích hợp Jackson 2 qua `ObjectMapper`, `JsonSerializer` và `JsonDeserializer`. Có thể đăng ký component bằng `@JsonComponent`:

~~~java
import java.io.IOException;
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.JsonSerializer;
import com.fasterxml.jackson.databind.SerializerProvider;
import org.springframework.boot.jackson.JsonComponent;

@JsonComponent
public class MoneyJsonComponent {

    public static class Serializer extends JsonSerializer<Money> {
        @Override
        public void serialize(
                Money value,
                JsonGenerator generator,
                SerializerProvider serializers) throws IOException {
            generator.writeString(value.currency() + " " + value.amount());
        }
    }
}
~~~

`@JsonComponent` giúp Spring Boot phát hiện và đăng ký serializer/deserializer theo cơ chế auto-configuration. Nếu custom component dùng reflection để gọi field/method hoặc truy cập class theo tên, cần đánh giá hints riêng.

### Jackson 3 với Spring Boot 4.x

Spring Boot 4.x ưu tiên Jackson 3; API dùng package `tools.jackson.*`, bean mapper mặc định là `JsonMapper`, và Spring Boot cung cấp `@JacksonComponent` cùng `ValueSerializer`/`ValueDeserializer`:

~~~java
import tools.jackson.core.JsonGenerator;
import tools.jackson.databind.SerializationContext;
import tools.jackson.databind.ValueSerializer;
import org.springframework.boot.jackson.JacksonComponent;

@JacksonComponent
public class MoneyJsonComponent {

    public static class Serializer extends ValueSerializer<Money> {
        @Override
        public void serialize(
                Money value,
                JsonGenerator generator,
                SerializationContext context) {
            generator.writeString(value.currency() + " " + value.amount());
        }
    }
}
~~~

Spring Boot tự đăng ký các `@JacksonComponent` bean trong ApplicationContext. Cú pháp custom serializer của Jackson 3 khác Jackson 2; không sao chép nguyên lớp `JsonSerializer` của Jackson 2 vào dự án Jackson 3.

### Mixin

Mixin cho phép thêm annotation Jackson vào class mà nhóm không thể sửa, ví dụ class từ dependency hoặc model bên thứ ba. Spring Boot hỗ trợ phát hiện mixin qua annotation riêng:

- Spring Boot 3.x/Jackson 2: `@JsonMixin`.
- Spring Boot 4.x/Jackson 3: `@JacksonMixin`.

Mixin giúp thay đổi cách Jackson nhìn property, nhưng không tự bảo đảm mọi member đã được Native Image giữ lại. Nếu mixin làm Jackson truy cập field/constructor không được suy ra, hãy đăng ký hints cho target type và kiểm thử.

## 10. Jackson 2 và Jackson 3: tránh trộn package

Phiên bản Jackson phụ thuộc Spring Boot và dependency thực tế:

| Nền tảng | Mapper chính | Package thường gặp | Component annotation của Spring Boot |
|---|---|---|---|
| Spring Boot 3.x / Jackson 2 | `com.fasterxml.jackson.databind.ObjectMapper` | `com.fasterxml.jackson.*` | `@JsonComponent` |
| Spring Boot 4.x / Jackson 3 | `tools.jackson.databind.json.JsonMapper` | `tools.jackson.*` | `@JacksonComponent` |

Spring Boot 4.x hiện ưu tiên Jackson 3. Tài liệu Spring Boot hiện hành mô tả hỗ trợ Jackson 2 là hướng tương thích migration và sẽ bị loại bỏ trong một bản Spring Boot 4.x tương lai. Do đó:

- Dự án Boot 3.x thường dùng `ObjectMapper` của Jackson 2.
- Dự án Boot 4.x nên dùng `JsonMapper`/Jackson 3 theo cấu hình mặc định.
- Không trộn annotation, serializer, module hoặc mapper của hai major version.
- Kiểm tra dependency tree để biết mapper thực tế; đừng suy ra từ tên import trong một file cũ.

Các ví dụ `@JsonProperty`, `@JsonCreator`, `@JsonValue`, `@JsonAnyGetter` và `@JsonAnySetter` trong bài minh họa mô hình binding chung. Khi chuyển sang Jackson 3, dùng annotation cùng bộ Jackson 3 của dự án và kiểm tra API cụ thể của phiên bản.

## 11. Spring AOT tự suy ra hints cho Jackson khi nào?

Spring AOT phân tích ApplicationContext và các contract đã biết. Một số kiểu JSON được framework suy ra tự động:

- Kiểu tham số và kiểu trả về của `@RestController` method thường được Spring kiểm tra; nếu nhận diện được nhu cầu serialization/binding, Spring có thể đóng góp reflection hints.
- `@ConfigurationProperties` có cơ chế hỗ trợ AOT riêng cho configuration binding.
- Các thư viện phổ biến có thể cung cấp reachability metadata tương thích Native Image.

Tuy nhiên, khi gọi `WebClient`, `RestClient` hoặc `RestTemplate` trực tiếp bên trong thân method, kiểu DTO có thể không xuất hiện trong signature của controller. Trong trường hợp đó, Spring Boot khuyến nghị dùng `@RegisterReflectionForBinding` trên bean cần kiểu dữ liệu:

~~~java
import org.springframework.aot.hint.annotation.RegisterReflectionForBinding;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Component
public class PartnerClient {

    private final WebClient webClient;

    public PartnerClient(WebClient webClient) {
        this.webClient = webClient;
    }

    @RegisterReflectionForBinding(PartnerOrder.class)
    public Mono<PartnerOrder> getOrder(String id) {
        return webClient.get()
                .uri("/orders/{id}", id)
                .retrieve()
                .bodyToMono(PartnerOrder.class);
    }
}
~~~

Annotation cho Spring biết cần reflection hints cho `PartnerOrder` và các kiểu liên quan tới binding. Nó không tự đăng ký resource, JDK proxy hoặc logic custom serializer không liên quan tới binding.

### DTO của `@ConfigurationProperties` là một trường hợp riêng

Spring Boot AOT tự tạo reflection hints cho configuration properties đã nhận diện. Với nested configuration property là class ngoài (không phải inner class), Spring Boot cần `@NestedConfigurationProperty` để nhận biết cấu trúc nested. Cách đặt annotation tùy kiểu binding:

- Với JavaBean mutable, đặt trên field nested hoặc getter tương ứng.
- Với constructor binding, đặt trên field tương ứng.
- Với Java record, đặt trên tham số record component.

Đây là annotation của Spring Boot configuration binding, **không phải annotation Jackson**.

Không dùng `@RegisterReflectionForBinding` như một cách thay thế mặc định cho `@NestedConfigurationProperty` trong cấu hình `@ConfigurationProperties`. Hãy dùng đúng cơ chế của từng loại binding.

## 12. Reflection hints cho thành viên truy cập động

Khi Jackson gọi getter/setter/constructor thông qua introspection, binding hints cho DTO thường là điểm bắt đầu. Nhưng một custom module có thể gọi thêm method khác, ví dụ:

~~~java
Method method = target.getClass().getDeclaredMethod("calculateSignature");
method.invoke(target);
~~~

Đây là lời gọi reflection tổng quát, không đơn thuần là binding property. Nếu Spring AOT hoặc thư viện chưa đóng góp hints, hãy đăng ký member cần thiết bằng `RuntimeHintsRegistrar`:

~~~java
import java.lang.reflect.Method;

import org.springframework.aot.hint.ExecutableMode;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.util.ReflectionUtils;

public class PartnerRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        Method method = ReflectionUtils.findMethod(
                PartnerPayload.class, "calculateSignature");
        if (method != null) {
            hints.reflection().registerMethod(method, ExecutableMode.INVOKE);
        }
    }
}
~~~

Đăng ký registrar bằng `@ImportRuntimeHints(PartnerRuntimeHints.class)` trên bean hoặc configuration được Spring AOT xử lý.

Ví dụ trên chỉ đăng ký invocation cho method được tìm thấy. Nếu thư viện cần truy cập constructor, field, method để introspect hoặc resource, phải chọn loại hint đúng với thao tác đó. **Không đăng ký mọi declared member chỉ để làm build pass** nếu chưa hiểu vì sao thư viện cần chúng.

### Private field và visibility

Jackson có thể được cấu hình để nhìn private field, nhưng đây là thay đổi phạm vi truy cập. Trước khi mở visibility rộng:

1. Ưu tiên public constructor, getter/setter hoặc record component.
2. Nếu API bắt buộc dùng private field, xác định chính xác field cần đọc/ghi.
3. Kiểm tra `@JsonAutoDetect`, `@JsonProperty(access = ...)` và cấu hình mapper.
4. Đảm bảo reflection hints cho field/accessor phù hợp.
5. Chạy deserialize/serialize trong native executable.

Hạn chế cấu hình visibility toàn cục để Jackson truy cập mọi field private của mọi DTO; điều đó có thể làm contract JSON khó kiểm soát và tăng metadata không cần thiết.

## 13. Kiểm thử JSON và Runtime Hints

### 13.1. Kiểm thử trên JVM

Một test cơ bản nên kiểm tra cả deserialize và serialize:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import tools.jackson.annotation.JsonProperty;
import tools.jackson.databind.json.JsonMapper;

record OrderDto(
        @JsonProperty("order_id") String orderId,
        String status) {
}

@SpringBootTest
class OrderJsonTests {

    @Autowired
    JsonMapper jsonMapper; // Jackson 3

    @Test
    void shouldReadAndWriteOrder() throws Exception {
        String json = """
                {
                  "order_id": "O-100",
                  "status": "processing"
                }
                """;

        OrderDto order = jsonMapper.readValue(json, OrderDto.class);
        assertThat(order.orderId()).isEqualTo("O-100");
        assertThat(order.status()).isEqualTo("processing");

        String written = jsonMapper.writeValueAsString(order);
        assertThat(written).contains("\"order_id\":\"O-100\"");
        assertThat(written).contains("\"status\":\"processing\"");
    }
}
~~~

Với Jackson 2, inject `ObjectMapper` thay cho `JsonMapper` và dùng annotation/package Jackson 2. Test này xác nhận contract JSON ở JVM; nó **chưa chứng minh** Native Image có đủ metadata.

### 13.2. Native test hoặc integration test trên executable

Chạy test theo profile native đã cấu hình trong dự án, hoặc build executable rồi gọi đúng endpoint:

~~~bash
# Ví dụ Maven profile native đã được khai báo
./mvnw -Pnative native:compile

# Ví dụ Gradle task native đã được cấu hình
./gradlew nativeCompile
~~~

Sau đó chạy binary và gửi payload chứa:

- POJO có constructor/setter.
- Record có nested record/list.
- Enum có giá trị JSON tùy chỉnh.
- Property động qua `@JsonAnySetter`.
- Polymorphic subtype nếu API có discriminator.

Test nên xác nhận response JSON và trạng thái dữ liệu đã parse. Chỉ thấy native build thành công chưa đủ; nhiều lỗi reflection chỉ xuất hiện khi đường code cụ thể được thực thi.

### 13.3. Kiểm tra Runtime Hints bằng unit test

Nếu ứng dụng có `RuntimeHintsRegistrar` tùy chỉnh, dùng `RuntimeHintsPredicates` để xác nhận hint đã được đăng ký:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.predicate.RuntimeHintsPredicates;

@Test
void shouldRegisterSignatureMethodHint() {
    RuntimeHints hints = new RuntimeHints();
    new PartnerRuntimeHints().registerHints(hints, getClass().getClassLoader());

    assertThat(RuntimeHintsPredicates.reflection()
            .onMethod(PartnerPayload.class, "calculateSignature")
            .invoke())
            .accepts(hints);
}
~~~

Đoạn test dùng API predicate của Spring Framework 6.x. Với phiên bản Spring Framework mới hơn, API có thể cung cấp phương thức chuyên biệt như `onMethodInvocation`; hãy kiểm tra Javadoc dependency thực tế. Kiểu test này xác minh registrar đóng góp hint, còn native integration test xác minh toàn bộ pipeline và hành vi cuối.

### 13.4. Dùng GraalVM tracing agent khi cần

Khi một thư viện bên thứ ba thực hiện reflection/resource/proxy mà không được AOT suy ra, tracing agent có thể ghi nhận những thao tác đã xảy ra khi chạy trên JVM. Cần chạy test hoặc thao tác thực tế để đi qua đầy đủ nhánh code liên quan.

Các file JSON agent tạo ra chỉ là **bằng chứng quan sát trong lần chạy đó**, không phải cấu hình hoàn chỉnh tự động cho mọi môi trường. Review và loại bỏ entry chỉ phục vụ test infrastructure trước khi đưa metadata vào source.

## 14. Chẩn đoán lỗi Jackson trên Native Image

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Deserialize báo không tìm thấy constructor phù hợp | Constructor/creator không được Jackson nhận diện hoặc thiếu reflection hint | Dùng constructor rõ ràng, `@JsonCreator`/`@JsonProperty`, kiểm tra hints |
| Record chạy trên JVM nhưng lỗi native | Canonical constructor/record component cần metadata chưa được giữ | Kiểm tra binding hints cho record và nested types |
| Enum không đọc được giá trị API | JSON value khác enum name hoặc `@JsonCreator` không xử lý code đó | Dùng `@JsonProperty`, `@JsonValue` hoặc factory method rõ ràng |
| Getter/setter hoặc private field không được truy cập | Visibility/field hints chưa đúng | Ưu tiên accessor công khai; đăng ký đúng member nếu cần |
| `@JsonAnyGetter`/`@JsonAnySetter` không hoạt động | Method đặc thù hoặc custom serializer cần invocation hints | Kiểm tra method được gọi và đăng ký hint hẹp |
| Polymorphic subtype không được tạo | Concrete subtype chưa được nhận diện/đăng ký hoặc discriminator sai | Khai báo subtype, reflection hints và cấu hình type metadata |
| DTO dùng trong WebClient/RestClient lỗi native | AOT không suy ra kiểu từ thân method | Dùng `@RegisterReflectionForBinding` trên bean/method phù hợp |
| Không tìm thấy schema/template | Resource không được đóng gói | Đăng ký resource hints; binding hints không bao gồm file |
| Jackson module/serializer không được gọi | Module/component chưa được đăng ký trong mapper | Kiểm tra Spring component scan, `@JsonComponent`/`@JacksonComponent` hoặc module |

### Quy trình điều tra

1. Tái hiện lỗi với payload nhỏ nhất trên native executable.
2. Xác định lỗi ở deserialize hay serialize.
3. Xác định DTO, constructor, field, property, enum hoặc method cụ thể bị truy cập.
4. Kiểm tra kiểu có xuất hiện trong controller signature hay chỉ trong thân method/client.
5. Kiểm tra Spring AOT hints và metadata từ dependency.
6. Bổ sung binding hint hoặc reflection/resource hint đúng loại.
7. Build lại native và chạy lại đúng payload đã gây lỗi.

Không nên thêm một file reflection config lớn cho toàn bộ model package trước khi xác định member bị thiếu. Hints quá rộng có thể làm tăng surface reflection, che khuất lỗi thiết kế và khiến metadata khó duy trì.

## 15. Ví dụ tổng hợp: gọi đối tác bằng WebClient

Giả sử đối tác trả JSON:

~~~json
{
  "order_id": "O-901",
  "status": "in-progress",
  "customer": {
    "customer_id": "C-77"
  },
  "attributes": {
    "channel": "mobile",
    "campaign": "winter"
  }
}
~~~

Các DTO:

~~~java
public record CustomerDto(
        @JsonProperty("customer_id") String customerId) {
}

public enum OrderStatus {
    @JsonProperty("new")
    NEW,
    @JsonProperty("in-progress")
    PROCESSING,
    @JsonProperty("done")
    COMPLETED
}

public record PartnerOrder(
        @JsonProperty("order_id") String orderId,
        OrderStatus status,
        CustomerDto customer,
        Map<String, Object> attributes) {
}
~~~

Client:

~~~java
@Component
public class PartnerOrderClient {

    private final WebClient webClient;

    public PartnerOrderClient(WebClient webClient) {
        this.webClient = webClient;
    }

    @RegisterReflectionForBinding(PartnerOrder.class)
    public Mono<PartnerOrder> getOrder(String id) {
        return webClient.get()
                .uri("/orders/{id}", id)
                .retrieve()
                .bodyToMono(PartnerOrder.class);
    }
}
~~~

Spring AOT có thể xử lý các kiểu nested được sử dụng trên property/record component của `PartnerOrder`. Nếu serializer hoặc generic runtime access cần thêm subtype, hãy đăng ký các kiểu cụ thể và kiểm thử. `attributes` là map động; nếu dùng object values có kiểu riêng hoặc custom deserializer, cần xác minh cách Jackson tạo các giá trị đó.

Quy trình xác minh:

1. Chạy JVM test với payload trên.
2. Build AOT/native theo Maven hoặc Gradle của dự án.
3. Gọi endpoint/service bằng native executable.
4. Kiểm tra `orderId`, `status`, `customer.customerId` và map `attributes`.
5. Serialize object trả về và so sánh tên property với contract JSON.
6. Nếu chỉ native bị lỗi, đọc diagnostic để xác định constructor/property/subtype/method nào thiếu hints.

## 16. Bài tập tự kiểm tra

**Câu 1.** Jackson thường dùng thành phần nào để serialize POJO?

**Gợi ý:** getter, field hoặc property accessor được nhận diện theo quy ước và cấu hình mapper.

**Câu 2.** Jackson thường dùng thành phần nào để deserialize POJO mutable?

**Gợi ý:** constructor để tạo object, sau đó setter hoặc field access để gán dữ liệu.

**Câu 3.** Vì sao record phù hợp với DTO bất biến?

**Gợi ý:** record khai báo component và canonical constructor rõ ràng; Jackson có thể dùng chúng cho serialization/deserialization.

**Câu 4.** `@JsonValue` và `@JsonCreator` giải quyết hai chiều nào?

**Gợi ý:** `@JsonValue` xác định giá trị ghi ra; `@JsonCreator` chỉ ra cách tạo enum/object từ giá trị đầu vào.

**Câu 5.** `@JsonAnySetter` dùng khi nào?

**Gợi ý:** khi JSON có các key động không được khai báo thành property cố định; method nhận tên và value để lưu vào cấu trúc mở rộng.

**Câu 6.** Vì sao WebClient có thể cần `@RegisterReflectionForBinding` dù controller đã chạy native?

**Gợi ý:** kiểu DTO dùng trong thân method client có thể không xuất hiện trong controller signature để Spring AOT tự suy luận.

**Câu 7.** Nếu một file JSON schema bị thiếu trong native executable, có nên thêm `@RegisterReflectionForBinding` cho DTO không?

**Gợi ý:** không. DTO cần binding hints; file schema cần resource hints.

**Câu 8.** `@JsonTypeInfo` có tự đăng ký reflection hints cho mọi subtype không?

**Gợi ý:** annotation cấu hình polymorphic type handling của Jackson; vẫn phải kiểm tra concrete subtype và metadata Native Image.

## 17. Checklist trước khi phát hành

- [ ] Xác định Jackson major version và package đang dùng; không trộn Jackson 2 với Jackson 3.
- [ ] DTO POJO có constructor/getter/setter rõ ràng.
- [ ] Record component và canonical constructor được kiểm tra với payload thật.
- [ ] Enum JSON values ổn định và có quy tắc xử lý giá trị không hợp lệ.
- [ ] `@JsonAnyGetter`/`@JsonAnySetter` và các method truy cập động đã được kiểm thử.
- [ ] Nested DTO, generic collection/map và polymorphic subtype đã được xác minh.
- [ ] Custom serializer/deserializer/mixin/module được đăng ký đúng với Spring Boot/Jackson version.
- [ ] DTO dùng trong WebClient/RestClient/RestTemplate có binding hints khi AOT không tự suy ra.
- [ ] Reflection hints và resource hints được phân biệt, đăng ký đúng mục đích.
- [ ] Có JVM tests và native tests/integration tests cho cả serialize lẫn deserialize.
- [ ] Đã kiểm tra payload biên: thiếu field, null, enum lạ, nested object rỗng và key động.
- [ ] Native executable/container được chạy thử trong môi trường tương đương deployment.

## 18. Tài liệu tham khảo

- [Spring Boot Reference — JSON](https://docs.spring.io/spring-boot/reference/features/json.html): Jackson 3, Jackson 2, custom serializers/deserializers, `@JacksonComponent` và mixins.
- [Spring Boot Reference — Advanced Native Images Topics](https://docs.spring.io/spring-boot/reference/packaging/native-image/advanced-topics.html): binding hints, `@RegisterReflectionForBinding`, RuntimeHints và kiểm thử hints.
- [Spring Boot 3.5 — Advanced Native Images Topics](https://docs.spring.io/spring-boot/3.5/reference/packaging/native-image/advanced-topics.html): nested configuration properties và lưu ý AOT/native cho Spring Boot 3.x.
- [Jackson 2 Javadoc — JsonProperty](https://www.javadoc.io/static/com.fasterxml.jackson.core/jackson-annotations/2.21/com/fasterxml/jackson/annotation/JsonProperty.html): ánh xạ logical property và enum.
- [Jackson 3 Javadoc — MapperFeature](https://javadoc.io/doc/tools.jackson.core/jackson-databind/latest/tools/jackson/databind/MapperFeature.html): nhận diện constructor/factory method parameter names và record properties.

**Ghi nhớ:** Jackson không chỉ đọc tên field; nó có thể gọi constructor, getter, setter, record accessor, enum factory và method động để ánh xạ JSON. Spring AOT suy luận được nhiều kiểu từ controller và cấu hình đã biết, nhưng DTO dùng trong client hoặc custom serializer có thể cần hints tường minh. Hãy chọn đúng DTO/member, phân biệt binding với resource và reflection tổng quát, rồi xác minh cả serialize lẫn deserialize trên native executable.

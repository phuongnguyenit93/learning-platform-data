# Ánh xạ record tại ranh giới JSON và kiểm tra hỗ trợ của thư viện

> **Học phần:** `JAVA_VERSION_JAVA16` · **Chương:** Ứng dụng record. Record là kiểu dữ liệu theo giá trị được chuẩn hóa từ Java 16. Khi nhận hoặc gửi JSON, ứng dụng có thể dùng record làm DTO để mô tả hợp đồng dữ liệu gọn, có kiểu và không cần setter. Tuy nhiên, thư viện JSON phải hiểu record và có khả năng gọi canonical constructor. Bài học này hướng dẫn kiểm tra khả năng tương thích, ánh xạ tên property, xác thực dữ liệu và giữ ranh giới rõ ràng giữa JSON với mô hình miền.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích cách thư viện JSON tạo record thông qua component và canonical constructor.
- Kiểm tra phiên bản Jackson hoặc Gson có hỗ trợ record hay không.
- Ánh xạ tên property JSON khác tên component Java.
- Xử lý trường bị thiếu, giá trị null, property lạ và dữ liệu lồng nhau.
- Giữ invariant trong constructor khi dữ liệu đến từ JSON.
- Dùng record làm DTO ở ranh giới API và chuyển đổi sang kiểu miền khi cần.
- Viết kiểm tra serialization/deserialization để phát hiện lỗi tương thích sau khi nâng cấp dependency.

## 1. Record khác JavaBean ở điểm nào tại ranh giới JSON?

Một record:

```java
public record CustomerDto(
        String customerId,
        String displayName,
        boolean active
) {}
```

có các accessor `customerId()`, `displayName()` và `active()`. Record không tự sinh các phương thức `getCustomerId()`, `getDisplayName()` hoặc setter. Các component được lưu trong trường final và giá trị được thiết lập qua canonical constructor.

Một số thư viện cũ hoặc framework chỉ dựa vào quy ước JavaBean có thể mong đợi:

- Constructor không tham số.
- Setter công khai để gán từng property.
- Getter có tiền tố `get` hoặc `is`.

Mô hình đó không phù hợp trực tiếp với record. Thư viện JSON có hỗ trợ record sẽ đọc thông tin component, ghép property với tham số canonical constructor, rồi tạo instance bằng constructor. Không cần setter để điền dữ liệu.

### 1.1. Canonical constructor là điểm tạo record

Với record:

```java
public record CustomerDto(String customerId, String displayName) {}
```

canonical constructor có chữ ký tương ứng với thứ tự và kiểu component:

```java
public CustomerDto(String customerId, String displayName) {
    this.customerId = customerId;
    this.displayName = displayName;
}
```

Đây là dạng constructor do Java ngầm sinh khi ta không khai báo constructor tường minh. Thư viện JSON hỗ trợ record có thể sử dụng constructor này để tạo instance từ property JSON.

Nếu record có compact constructor để chuẩn hóa hoặc kiểm tra dữ liệu, constructor đó vẫn được thực thi khi thư viện tạo record. Vì vậy, invariant không bị bỏ qua chỉ vì dữ liệu đến từ JSON.

### 1.2. Không thêm no-args constructor hoặc setter chỉ để chiều thư viện

Record được thiết kế quanh dữ liệu bất biến và constructor. Không nên cố biến nó thành JavaBean mutable bằng cách thêm setter hoặc dùng công cụ sinh mã để thay đổi component sau khi tạo.

Nếu thư viện JSON đang dùng không hỗ trợ record, hãy kiểm tra khả năng nâng cấp hoặc dùng một DTO class riêng tại ranh giới tích hợp. Không dùng reflection để sửa trường final hoặc dựa vào hành vi nội bộ không được thư viện cam kết.

## 2. Kiểm tra thư viện JSON có hỗ trợ record

Khả năng hỗ trợ phụ thuộc vào phiên bản thư viện thực sự được chạy, không chỉ phiên bản ghi trong một file build. Dependency gián tiếp hoặc dependency management của framework có thể thay đổi phiên bản cuối cùng.

Hai thư viện Java phổ biến có hỗ trợ record trong các dòng phiên bản sau:

| Thư viện | Mốc hỗ trợ record | Cách sử dụng |
|---|---|---|
| Jackson Databind | Jackson 2.12 trở lên có hỗ trợ record | Dùng ObjectMapper/JsonMapper và canonical constructor |
| Gson | Gson 2.10 trở lên có hỗ trợ record | Dùng Gson/GsonBuilder và record component |

Đây là mốc bắt đầu hỗ trợ record, không phải gợi ý dùng một phiên bản cũ làm dependency mới. Với ứng dụng hiện tại, chọn bản phát hành còn được duy trì, tương thích với Java runtime và framework đang dùng; giữ các module Jackson cùng dòng phiên bản và ưu tiên BOM/dependency management của framework.

### 2.1. Kiểm tra phiên bản thực tế

Khi mapping không hoạt động, hãy kiểm tra dependency graph để biết bản thư viện nào thực sự được resolve. Với Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Với Maven:

```bash
mvn dependency:tree
```

Tìm các artifact liên quan như `jackson-databind`, `jackson-annotations`, `jackson-core` hoặc `gson`. Nếu framework quản lý phiên bản, tránh tự nâng riêng một artifact Jackson làm lệch các module cùng bộ.

Một project có thể compile thành công nhưng khi chạy lại nạp một phiên bản khác do dependency bắc cầu hoặc cấu hình đóng gói. Kiểm tra runtime dependency là bước cần thiết khi xác nhận hỗ trợ.

### 2.2. Đừng chỉ dựa vào việc serialize thành công

Một thư viện có thể ghi JSON từ accessor nhưng không đọc JSON thành record được, hoặc có thể đọc được record đơn giản nhưng lỗi với constructor validation, generic collection hay kiểu ngày giờ.

Hãy kiểm tra cả hai chiều:

1. Tạo record và serialize thành JSON.
2. Đọc JSON thành record mới.
3. So sánh giá trị component sau khi đọc.
4. Kiểm tra trường hợp thiếu property, null, property lạ và dữ liệu lồng nhau theo hợp đồng ứng dụng.

## 3. Ánh xạ record với Jackson

Jackson 2.12 trở lên hỗ trợ record trực tiếp. Với DTO đơn giản, có thể dùng `ObjectMapper` hoặc `JsonMapper` mà không cần setter và constructor không tham số.

Ví dụ record:

```java
import com.fasterxml.jackson.annotation.JsonProperty;

public record CustomerJson(
        @JsonProperty("customer_id") String customerId,
        @JsonProperty("display_name") String displayName,
        boolean active
) {}
```

Dùng `JsonMapper`:

```java
import com.fasterxml.jackson.databind.json.JsonMapper;

JsonMapper mapper = JsonMapper.builder().build();

String json = """
        {
          "customer_id": "C-100",
          "display_name": "Nguyen An",
          "active": true
        }
        """;

CustomerJson customer = mapper.readValue(json, CustomerJson.class);

System.out.println(customer.customerId());  // C-100
System.out.println(customer.displayName()); // Nguyen An
```

Serialize:

```java
String output = mapper.writeValueAsString(customer);
System.out.println(output);
```

`@JsonProperty` ánh xạ tên property bên ngoài với component Java. Tên trong JSON có thể là snake_case trong khi Java dùng camelCase. Cách khai báo tường minh giúp hợp đồng JSON ổn định ngay cả khi tên component nội bộ thay đổi.

### 3.1. Ánh xạ tên bằng naming strategy

Nếu toàn bộ API dùng một quy tắc đặt tên thống nhất, có thể cấu hình naming strategy thay vì gắn annotation trên mọi component:

```java
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.json.JsonMapper;

JsonMapper mapper = JsonMapper.builder()
        .propertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
        .build();
```

Với strategy này, component `customerId` được ánh xạ thành property `customer_id` theo quy tắc snake_case. Hãy chọn một cách quản lý tên nhất quán: annotation cho các tên đặc biệt hoặc naming strategy cho toàn bộ DTO. Khi một property là hợp đồng công khai quan trọng, annotation tường minh có thể giúp người đọc nhận ra ngay tên JSON.

### 3.2. Property không biết trước

Khi client gửi thêm property mà DTO chưa khai báo, hành vi phụ thuộc cấu hình ObjectMapper và annotation. Nếu API cần bỏ qua property lạ để hỗ trợ client mở rộng độc lập, có thể khai báo:

```java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record CustomerJson(
        String customerId,
        String displayName
) {}
```

Chỉ bỏ qua property lạ khi hợp đồng API cho phép. Trong hệ thống cần phát hiện client gửi sai tên field hoặc gửi nhầm schema, giữ chế độ kiểm tra nghiêm ngặt sẽ giúp lỗi lộ ra sớm hơn. Cấu hình toàn cục của framework có thể thay đổi mặc định, nên hãy kiểm tra hành vi của mapper thực tế.

### 3.3. Kiểu ngày giờ trong JSON

Các kiểu `java.time` như `LocalDate`, `Instant` và `OffsetDateTime` là lựa chọn phù hợp cho component record. Với Jackson, dùng module Java Time tương ứng:

```java
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

JsonMapper mapper = JsonMapper.builder()
        .addModule(new JavaTimeModule())
        .build();
```

Ứng dụng cần dependency `jackson-datatype-jsr310` cùng dòng phiên bản Jackson đang dùng. Không dựa vào việc serialize trực tiếp các trường nội bộ của kiểu ngày giờ bằng reflection. Hãy để module chuyên biệt quy định biểu diễn JSON.

Ví dụ:

```java
import com.fasterxml.jackson.annotation.JsonProperty;
import java.time.LocalDate;

public record BookingJson(
        @JsonProperty("booking_id") String bookingId,
        @JsonProperty("start_date") LocalDate startDate
) {}
```

JSON có thể dùng chuỗi ISO-8601 như `"2026-11-27"` cho LocalDate. Định dạng cụ thể cần là một phần hợp đồng API và nên có kiểm tra tương ứng.

## 4. Ánh xạ record với Gson

Gson 2.10 trở lên có hỗ trợ Java record. Dùng `Gson` hoặc `GsonBuilder` như với các kiểu dữ liệu khác:

```java
import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.annotations.SerializedName;

public record CustomerJson(
        @SerializedName("customer_id") String customerId,
        @SerializedName("display_name") String displayName,
        boolean active
) {}
```

Sau khi khai báo record, tạo Gson và ánh xạ JSON:

```java
Gson gson = new GsonBuilder().create();

String json = """
        {
          "customer_id": "C-100",
          "display_name": "Nguyen An",
          "active": true
        }
        """;

CustomerJson customer = gson.fromJson(json, CustomerJson.class);
String output = gson.toJson(customer);
```

`@SerializedName` ánh xạ tên JSON với component. Record vẫn không cần setter. Khi đọc JSON, Gson sử dụng cơ chế hỗ trợ record của phiên bản tương ứng để tạo instance.

### 4.1. Kiểm tra kiểu ngày giờ với Gson

Không giả định mọi kiểu trong `java.time` đều tự động được Gson xử lý theo định dạng API mong muốn. Với ngày giờ, khai báo `TypeAdapter` hoặc `JsonSerializer`/`JsonDeserializer` phù hợp và đăng ký trong `GsonBuilder`.

Ví dụ adapter cho LocalDate:

```java
import com.google.gson.TypeAdapter;
import com.google.gson.stream.JsonReader;
import com.google.gson.stream.JsonWriter;
import java.io.IOException;
import java.time.LocalDate;

public final class LocalDateAdapter extends TypeAdapter<LocalDate> {
    @Override
    public void write(JsonWriter out, LocalDate value) throws IOException {
        if (value == null) {
            out.nullValue();
        } else {
            out.value(value.toString());
        }
    }

    @Override
    public LocalDate read(JsonReader in) throws IOException {
        if (in.peek() == com.google.gson.stream.JsonToken.NULL) {
            in.nextNull();
            return null;
        }
        return LocalDate.parse(in.nextString());
    }
}
```

Đăng ký:

```java
Gson gson = new GsonBuilder()
        .registerTypeAdapter(LocalDate.class, new LocalDateAdapter())
        .create();
```

Adapter này dùng định dạng ISO-8601 mặc định của `LocalDate.toString()` và `LocalDate.parse()`. Nếu API dùng định dạng khác, hãy định nghĩa formatter tường minh và kiểm thử cả dữ liệu hợp lệ lẫn không hợp lệ. Nếu component bắt buộc khác null, canonical constructor của record vẫn phải kiểm tra null.

## 5. Giữ invariant khi tạo record từ JSON

Dữ liệu JSON đến từ bên ngoài cần được xem là dữ liệu đầu vào chưa đáng tin cậy. Annotation mapping chỉ giúp chuyển property sang component; nó không tự động bảo đảm mọi quy tắc nghiệp vụ đều được đáp ứng.

Compact constructor là nơi phù hợp để kiểm tra invariant cơ bản:

```java
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.Objects;

public record CreateCustomerRequest(
        @JsonProperty("display_name") String displayName,
        @JsonProperty("email") String email
) {
    public CreateCustomerRequest {
        Objects.requireNonNull(displayName, "displayName");
        Objects.requireNonNull(email, "email");

        displayName = displayName.strip();
        email = email.strip();

        if (displayName.isEmpty()) {
            throw new IllegalArgumentException("displayName must not be blank");
        }
        if (email.isEmpty() || !email.contains("@")) {
            throw new IllegalArgumentException("email is invalid");
        }
    }
}
```

Khi Jackson tạo `CreateCustomerRequest` từ JSON, constructor kiểm tra dữ liệu như khi ứng dụng gọi `new CreateCustomerRequest(...)` trực tiếp. Điều này ngăn dữ liệu không hợp lệ đi vào các bước xử lý sau.

Kiểm tra cú pháp email ở ví dụ chỉ mang tính minh họa; ứng dụng thực tế nên dùng validator theo quy tắc nghiệp vụ và tiêu chuẩn phù hợp. Không nên coi một phép kiểm tra chuỗi đơn giản là xác thực email đầy đủ.

### 5.1. Trường bị thiếu và trường có giá trị null

Đối với component kiểu tham chiếu, thư viện có thể truyền `null` khi property bị thiếu hoặc khi JSON ghi rõ `null`, tùy cấu hình và adapter. Canonical constructor nhìn thấy giá trị được truyền vào; nó không tự biết giá trị đó đến từ property bị thiếu hay property hiện diện với null.

Nếu cả hai trạng thái đều không hợp lệ, `Objects.requireNonNull` đủ để từ chối. Nếu nghiệp vụ cần phân biệt:

- Không có property: dùng giá trị mặc định hoặc trạng thái “không được cung cấp”.
- Property có giá trị null: biểu diễn rõ “xóa giá trị” hoặc “đã cung cấp nhưng rỗng”.
- Property có giá trị cụ thể: cập nhật bằng giá trị đó.

Hãy dùng request DTO có biểu diễn trạng thái phù hợp, custom deserializer hoặc cấu trúc JSON có trường trạng thái riêng. Không ép mọi trường hợp thành một nullable component nếu API cần phân biệt ba trạng thái.

Với component primitive như `int` và `boolean`, giá trị mặc định của kiểu có thể làm mất thông tin giữa property bị thiếu và giá trị 0/false. Nếu cần phát hiện thiếu field, dùng kiểu wrapper như `Integer`/`Boolean` ở DTO đầu vào rồi xác thực trước khi chuyển sang mô hình miền.

### 5.2. Validation annotation không tự chạy chỉ vì có JSON

Có thể đặt annotation Bean Validation trên record component, ví dụ `@NotBlank` hoặc `@NotNull`, nếu ứng dụng có Jakarta Bean Validation provider. Nhưng việc deserialize bằng ObjectMapper không tự động có nghĩa validator đã được gọi.

Trong ứng dụng dùng Spring hoặc framework tương tự, kiểm tra cấu hình validation tại ranh giới controller/service. Trong code thuần, gọi `Validator` một cách tường minh hoặc kiểm tra invariant trong constructor. Chọn một đường kiểm tra rõ ràng để tránh nghĩ annotation đã được thực thi trong khi thực tế chưa có provider.

## 6. Record lồng nhau và collection trong JSON

Record có thể chứa record khác hoặc collection record. Ví dụ request tạo đơn hàng:

```java
import com.fasterxml.jackson.annotation.JsonProperty;
import java.math.BigDecimal;
import java.util.List;
import java.util.Objects;

public record OrderRequest(
        @JsonProperty("order_id") String orderId,
        @JsonProperty("lines") List<OrderLineRequest> lines
) {
    public OrderRequest {
        Objects.requireNonNull(orderId, "orderId");
        orderId = orderId.strip();
        if (orderId.isEmpty()) {
            throw new IllegalArgumentException("orderId must not be blank");
        }

        lines = List.copyOf(Objects.requireNonNull(lines, "lines"));
        if (lines.isEmpty()) {
            throw new IllegalArgumentException("Order must contain at least one line");
        }
    }

    public record OrderLineRequest(
            @JsonProperty("sku") String sku,
            @JsonProperty("quantity") int quantity,
            @JsonProperty("unit_price") BigDecimal unitPrice
    ) {
        public OrderLineRequest {
            Objects.requireNonNull(sku, "sku");
            Objects.requireNonNull(unitPrice, "unitPrice");
            sku = sku.strip();

            if (sku.isEmpty() || quantity <= 0 || unitPrice.signum() < 0) {
                throw new IllegalArgumentException("Invalid order line");
            }
        }
    }
}
```

JSON tương ứng:

```json
{
  "order_id": "ORD-100",
  "lines": [
    {
      "sku": "KB-01",
      "quantity": 2,
      "unit_price": 750000
    },
    {
      "sku": "MS-02",
      "quantity": 1,
      "unit_price": 250000
    }
  ]
}
```

`List.copyOf` tạo snapshot danh sách và từ chối phần tử null. Mỗi `OrderLineRequest` cũng tự xác thực component của nó. Việc lồng record giữ cấu trúc request rõ ràng mà không cần tạo class mutable chỉ để mapping JSON.

### 6.1. Generic collection cần giữ thông tin kiểu

Khi đọc một record đơn, truyền trực tiếp `CustomerJson.class`. Khi đọc collection generic như `List<CustomerJson>`, kiểu runtime `List.class` không giữ được tham số generic. Dùng cơ chế giữ generic type của thư viện.

Với Jackson:

```java
import com.fasterxml.jackson.core.type.TypeReference;
import java.util.List;

List<CustomerJson> customers = mapper.readValue(
        json,
        new TypeReference<List<CustomerJson>>() {}
);
```

Với Gson:

```java
import com.google.gson.reflect.TypeToken;
import java.lang.reflect.Type;
import java.util.List;

Type type = new TypeToken<List<CustomerJson>>() {}.getType();
List<CustomerJson> customers = gson.fromJson(json, type);
```

Không ép kết quả thành raw `List` rồi cast từng phần tử. Giữ generic type giúp thư viện biết kiểu record cần tạo và giúp code kiểm tra kiểu tốt hơn.

## 7. DTO JSON và mô hình miền không nhất thiết là một kiểu

Một record dùng trực tiếp làm DTO rất tiện khi cấu trúc JSON gần như trùng với dữ liệu ứng dụng. Nhưng hợp đồng JSON và mô hình miền thường thay đổi theo nhịp khác nhau.

Ví dụ JSON nhận số tiền dưới dạng số thập phân và tên property theo API:

```java
import java.math.BigDecimal;

public record PaymentRequest(
        String accountId,
        BigDecimal amount,
        String currency
) {}
```

Mô hình miền có thể dùng value object riêng:

```java
import java.math.BigDecimal;
import java.util.Currency;
import java.util.Objects;

public record Money(BigDecimal amount, Currency currency) {
    public Money {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currency, "currency");
        if (amount.signum() <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
    }
}
```

Chuyển đổi tại ranh giới:

```java
import java.util.Currency;

public final class PaymentMapper {
    private PaymentMapper() {}

    public static Money toMoney(PaymentRequest request) {
        return new Money(
                request.amount(),
                Currency.getInstance(request.currency())
        );
    }
}
```

DTO chịu trách nhiệm phản ánh JSON; value object chịu trách nhiệm bảo vệ quy tắc miền. Việc tách hai kiểu giúp thay đổi tên property, cấu trúc API hoặc annotation JSON mà không làm lan thay đổi vào domain.

Không cần tách DTO và domain cho mọi record nhỏ. Hãy tách khi API công khai, validation, versioning hoặc quy tắc nghiệp vụ có vòng đời khác nhau.

## 8. Các điểm cần kiểm tra khi nâng cấp thư viện

Khi nâng Jackson, Gson hoặc framework chứa chúng, kiểm tra các hành vi mà ứng dụng thực sự phụ thuộc:

| Nội dung | Điều cần xác minh |
|---|---|
| Record đơn giản | Serialize và deserialize thành công |
| Property naming | Tên JSON khớp annotation hoặc naming strategy |
| Constructor validation | Compact constructor được gọi và exception được xử lý đúng |
| Property bị thiếu/null | Có đúng với chính sách bắt buộc, mặc định và nullable |
| Property lạ | Bị từ chối hay bỏ qua đúng hợp đồng |
| Nested record | Record con được tạo đúng |
| Collection component | Null, phần tử null và quyền sửa được kiểm soát |
| Generic collection | Phần tử được tạo đúng kiểu record |
| Ngày giờ | Module/adapter tạo định dạng JSON dự kiến |
| Dependency runtime | Không có phiên bản thư viện xung đột hoặc bị framework ghi đè |

Một kiểm tra round-trip có thể bắt đầu đơn giản:

```java
CustomerJson original = new CustomerJson(
        "C-100",
        "Nguyen An",
        true
);

String json = mapper.writeValueAsString(original);
CustomerJson restored = mapper.readValue(json, CustomerJson.class);

if (!original.equals(restored)) {
    throw new AssertionError("Record round-trip failed");
}
```

Record sinh `equals()` theo component nên phép so sánh trên phù hợp với DTO có component equality theo giá trị. Với component như mảng hoặc object có equality theo identity, hãy viết assertion theo semantics mong muốn thay vì giả định round-trip luôn cho kết quả equals.

### 8.1. Kiểm tra schema và dữ liệu không hợp lệ

Ngoài round-trip, nên có kiểm tra cho:

- JSON thiếu component bắt buộc.
- JSON gửi null cho component không nullable.
- Chuỗi rỗng hoặc giá trị ngoài miền cho phép.
- Số âm hoặc giá trị vượt giới hạn.
- Collection chứa phần tử null.
- Property không biết trước.
- Ngày giờ sai định dạng.
- JSON có cấu trúc lồng nhau không hợp lệ.

Các trường hợp này xác minh rằng constructor và cấu hình mapper cùng bảo vệ hợp đồng dữ liệu.

## 9. Lưu ý bảo mật tại ranh giới JSON

JSON đầu vào có thể do client không đáng tin cậy tạo ra. Việc record là immutable không thay thế kiểm tra kích thước, giới hạn nesting, xác thực và kiểm soát kiểu dữ liệu.

- Giới hạn kích thước request và độ sâu cấu trúc theo khả năng framework/parser.
- Chỉ ánh xạ sang các kiểu DTO được ứng dụng chủ động cho phép.
- Tránh bật cơ chế polymorphic typing không giới hạn cho dữ liệu không tin cậy; nếu cần polymorphism, dùng allow-list subtype rõ ràng.
- Kiểm tra dữ liệu trước khi thực hiện side effect như ghi database, chuyển tiền hoặc gọi dịch vụ khác.
- Không đưa trực tiếp thông báo lỗi nội bộ, stack trace hoặc dữ liệu nhạy cảm vào response JSON.

Annotation hoặc constructor validation là một phần của kiểm soát đầu vào, không phải ranh giới bảo mật duy nhất.

## 10. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng thư viện chỉ hỗ trợ JavaBean | Không tạo được record hoặc thiếu property | Dùng phiên bản có record support hoặc DTO chuyển tiếp |
| Chỉ kiểm tra compile dependency | Runtime nạp bản thư viện khác | Kiểm tra dependency runtime và framework BOM |
| Mong record có getter `getX()` | Method reference hoặc introspection không tìm thấy | Dùng accessor `x()` và thư viện hiểu record |
| Nghĩ annotation JSON tự xác thực dữ liệu | Dữ liệu sai vẫn đi vào ứng dụng | Constructor invariant hoặc gọi Bean Validation rõ ràng |
| Không phân biệt missing và null | Mất thông tin trạng thái đầu vào | Thiết kế DTO/decoder biểu diễn trạng thái riêng |
| Đọc `List.class` cho `List<Record>` | Mất generic element type | Jackson `TypeReference` hoặc Gson `TypeToken` |
| Dùng `LocalDate` mà không cấu hình module/adapter | Mapping lỗi hoặc định dạng không như hợp đồng | Jackson JavaTimeModule hoặc Gson TypeAdapter |
| Bỏ qua property lạ trong mọi API | Lỗi sai tên field bị che khuất | Chỉ bật ignore unknown khi hợp đồng cho phép |
| Dùng domain record làm JSON contract trong mọi trường hợp | Thay đổi API lan vào mô hình miền | Tạo request/response DTO và mapper ở ranh giới |

## 11. Checklist tích hợp record với JSON

Trước khi đưa record vào API, hãy kiểm tra:

1. Phiên bản thư viện JSON thực tế có hỗ trợ Java record không?
2. Runtime dependency có đồng bộ với dependency management của framework không?
3. Tên property JSON có khớp component hoặc annotation không?
4. Canonical constructor có kiểm tra invariant cần thiết không?
5. Chính sách missing, null, default và unknown property đã rõ chưa?
6. Collection component có defensive copy và chính sách null phù hợp không?
7. Generic collection có giữ đúng kiểu phần tử không?
8. Kiểu ngày giờ có module/adapter và định dạng rõ ràng không?
9. Có cần tách DTO JSON khỏi value object/domain model không?
10. Có round-trip test và test dữ liệu không hợp lệ không?

## 12. Bài tập vận dụng

**Bài 1 — DTO khách hàng:** Tạo `CustomerJson(customerId, displayName, active)`. Ánh xạ property snake_case bằng Jackson `@JsonProperty` hoặc Gson `@SerializedName`. Serialize và deserialize rồi so sánh component.

**Bài 2 — Kiểm tra constructor:** Tạo record request có component bắt buộc. Thử JSON thiếu field, null và chuỗi rỗng. Xác định lỗi được phát hiện tại parser hay canonical constructor.

**Bài 3 — Đơn hàng lồng nhau:** Tạo `OrderRequest` chứa `List<OrderLineRequest>`. Sao chép danh sách trong constructor, xác thực từng dòng và kiểm tra JSON lồng nhau.

**Bài 4 — Generic collection:** Đọc `List<CustomerJson>` bằng Jackson `TypeReference` và Gson `TypeToken`. Giải thích vì sao chỉ dùng `List.class` không đủ thông tin generic.

**Bài 5 — Ranh giới miền:** Tạo `PaymentRequest` làm DTO JSON và `Money` làm value object. Viết mapper chuyển DTO thành domain, bảo đảm currency và amount hợp lệ trước khi xử lý nghiệp vụ.

---

**Ghi nhớ:** Record có thể làm DTO JSON khi thư viện hiểu record và tạo instance qua canonical constructor. Kiểm tra phiên bản runtime, tên property, module cho kiểu đặc biệt và hành vi với missing/null. Hãy giữ invariant trong constructor, kiểm thử cả hai chiều ánh xạ và tách DTO khỏi domain khi hợp đồng API có vòng đời riêng.

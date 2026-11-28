# Kiểm thử round-trip dữ liệu qua mapper mà vẫn chạy validation constructor

> **Học phần:** `JAVA_VERSION_JAVA16` · **Chương:** Ứng dụng record. Record phù hợp để biểu diễn DTO, command và value object vì component được thiết lập qua constructor, có accessor rõ ràng và equality theo giá trị. Trong ứng dụng thực tế, dữ liệu thường đi qua nhiều bước: JSON được ánh xạ thành DTO, mapper chuyển DTO thành mô hình miền, rồi mapper khác tạo response hoặc dữ liệu lưu trữ. Bài học này hướng dẫn kiểm thử round-trip qua các bước đó, đồng thời chứng minh validation trong canonical hoặc compact constructor vẫn được thực thi khi mapper và thư viện tạo record.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt round-trip qua mapper với round-trip qua JSON.
- Thiết kế record có invariant và defensive copy trong constructor.
- Viết mapper chuyển đổi DTO sang domain record và chiều ngược lại.
- Kiểm tra round-trip bằng `equals()` của record khi semantics phù hợp.
- Kiểm tra JSON bằng cấu trúc dữ liệu thay vì so sánh chuỗi JSON thô.
- Xác minh constructor validation chạy trong quá trình deserialize và mapping.
- Kiểm thử dữ liệu thiếu, null, sai kiểu, giá trị ngoài miền và collection lồng nhau.
- Tránh các test chỉ chứng minh serialize thành công nhưng bỏ sót lỗi deserialize hoặc mapping.

## 1. Round-trip đang kiểm tra điều gì?

Round-trip nghĩa là đưa dữ liệu đi qua một chuỗi chuyển đổi rồi kiểm tra dữ liệu thu được có giữ đúng thông tin mà hợp đồng yêu cầu hay không. Trong ứng dụng Java dùng record, có ít nhất ba đường đi thường gặp:

1. **Mapper round-trip:** domain record → DTO record → domain record.
2. **JSON round-trip:** record → JSON → record.
3. **Boundary round-trip:** JSON → request DTO → domain command/value object → response DTO → JSON.

Ba đường đi này kiểm tra các hợp đồng khác nhau. Một mapper có thể chuyển đổi đúng nhưng JSON annotation sai; JSON có thể đọc được nhưng mapper làm mất một component; serialization có thể thành công trong khi deserialization không gọi được constructor hoặc constructor từ chối dữ liệu.

Không nên gom tất cả vào một test duy nhất. Tách test theo từng ranh giới giúp xác định chính xác lớp nào làm sai dữ liệu.

### 1.1. Record hỗ trợ kiểm tra equality theo giá trị

Record tự sinh `equals()` và `hashCode()` dựa trên component. Điều này hữu ích khi kiểm tra một giá trị được tạo lại có tương đương với giá trị ban đầu hay không:

```java
record Coordinate(int x, int y) {}

Coordinate original = new Coordinate(10, 20);
Coordinate restored = new Coordinate(10, 20);

System.out.println(original.equals(restored)); // true
```

Với record có component là List, Set hoặc Map, equality của record sử dụng equality của collection. Với component là object khác, kết quả phụ thuộc semantics `equals()` của object đó.

Equality không có nghĩa mọi object graph đều được so sánh sâu theo nội dung mong muốn. Ví dụ, mảng Java dùng equality theo identity nếu không tự bọc hoặc so sánh riêng. Với `BigDecimal`, `equals()` phân biệt scale: `new BigDecimal("2.0")` không bằng `new BigDecimal("2.00")`, dù `compareTo()` trả về 0. Test phải theo đúng hợp đồng của kiểu dữ liệu.

### 1.2. Không phải mọi mapper đều có phép nghịch đảo hoàn hảo

Một mapper có thể bỏ một field nội bộ, chuẩn hóa chuỗi, chuyển tiền tệ hoặc làm tròn số. Trong trường hợp đó:

- Domain → DTO → domain có thể giữ nguyên các component công khai.
- DTO → domain → DTO có thể giữ nguyên hợp đồng API.
- Hai object không nhất thiết `equals()` nếu một chiều chuyển đổi cố ý bỏ dữ liệu.

Trước khi viết assertion, xác định thông tin nào phải được bảo toàn và thông tin nào được phép thay đổi. Không viết `assertEquals(original, restored)` một cách máy móc khi mapper có chủ đích chuẩn hóa hoặc loại bỏ dữ liệu.

## 2. Thiết kế record với invariant rõ ràng

Ta dùng ví dụ đặt hàng để kiểm thử nhiều tầng. Một dòng hàng có mã SKU, số lượng và đơn giá. Record miền `OrderLine` bảo vệ invariant: SKU không rỗng, số lượng dương và đơn giá lớn hơn 0.

```java
import java.math.BigDecimal;
import java.util.Objects;

public record OrderLine(
        String sku,
        int quantity,
        BigDecimal unitPrice
) {
    public OrderLine {
        Objects.requireNonNull(sku, "sku");
        Objects.requireNonNull(unitPrice, "unitPrice");

        sku = sku.strip();

        if (sku.isEmpty()) {
            throw new IllegalArgumentException("sku must not be blank");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        if (unitPrice.signum() <= 0) {
            throw new IllegalArgumentException("unitPrice must be positive");
        }
    }
}
```

Compact constructor được gọi khi code ứng dụng tạo `new OrderLine(...)`. Nó cũng được gọi khi một thư viện record-aware tạo record qua canonical constructor. Vì vậy, đây là một điểm bảo vệ invariant ổn định cho dữ liệu miền.

Command chứa nhiều dòng hàng:

```java
import java.util.List;
import java.util.Objects;

public record PlaceOrderCommand(
        String customerId,
        List<OrderLine> lines
) {
    public PlaceOrderCommand {
        Objects.requireNonNull(customerId, "customerId");
        Objects.requireNonNull(lines, "lines");

        customerId = customerId.strip();
        lines = List.copyOf(lines);

        if (customerId.isEmpty()) {
            throw new IllegalArgumentException("customerId must not be blank");
        }
        if (lines.isEmpty()) {
            throw new IllegalArgumentException("order must contain at least one line");
        }
    }
}
```

`List.copyOf()` tạo collection không sửa được và từ chối phần tử null. Constructor kiểm tra cả collection reference, phần tử và điều kiện nghiệp vụ của command. Nếu collection nguồn bị thay đổi sau khi tạo command, cấu trúc list bên trong command không bị thay đổi theo.

## 3. DTO và mapper ở ranh giới

DTO phản ánh dữ liệu được nhận từ API. DTO có thể kiểm tra cấu trúc đầu vào, trong khi record miền kiểm tra invariant nghiệp vụ mạnh hơn.

Ví dụ request DTO:

```java
import com.fasterxml.jackson.annotation.JsonProperty;
import java.math.BigDecimal;
import java.util.Objects;

public record CreateOrderLineRequest(
        @JsonProperty("sku") String sku,
        @JsonProperty("quantity") int quantity,
        @JsonProperty("unit_price") BigDecimal unitPrice
) {
    public CreateOrderLineRequest {
        Objects.requireNonNull(sku, "sku");
        Objects.requireNonNull(unitPrice, "unitPrice");

        sku = sku.strip();

        if (sku.isEmpty()) {
            throw new IllegalArgumentException("sku must not be blank");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
    }
}
```

Trong ví dụ này DTO kiểm tra các điều kiện cơ bản. Điều kiện đơn giá phải dương được bảo vệ ở `OrderLine`, để minh họa rằng mapper phải tạo record miền bằng constructor và không được bỏ qua invariant miền.

Request cấp đơn hàng:

```java
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;
import java.util.Objects;

public record CreateOrderRequest(
        @JsonProperty("customer_id") String customerId,
        @JsonProperty("lines") List<CreateOrderLineRequest> lines
) {
    public CreateOrderRequest {
        Objects.requireNonNull(customerId, "customerId");
        Objects.requireNonNull(lines, "lines");

        customerId = customerId.strip();
        lines = List.copyOf(lines);

        if (customerId.isEmpty()) {
            throw new IllegalArgumentException("customerId must not be blank");
        }
        if (lines.isEmpty()) {
            throw new IllegalArgumentException("lines must not be empty");
        }
    }
}
```

Mapper chuyển request DTO sang domain command và ngược lại:

```java
import java.util.Objects;

public final class OrderMapper {
    private OrderMapper() {}

    public static PlaceOrderCommand toCommand(CreateOrderRequest request) {
        Objects.requireNonNull(request, "request");

        var lines = request.lines().stream()
                .map(line -> new OrderLine(
                        line.sku(),
                        line.quantity(),
                        line.unitPrice()
                ))
                .toList();

        return new PlaceOrderCommand(request.customerId(), lines);
    }

    public static CreateOrderRequest toRequest(PlaceOrderCommand command) {
        Objects.requireNonNull(command, "command");

        var lines = command.lines().stream()
                .map(line -> new CreateOrderLineRequest(
                        line.sku(),
                        line.quantity(),
                        line.unitPrice()
                ))
                .toList();

        return new CreateOrderRequest(command.customerId(), lines);
    }
}
```

Điểm cần quan sát: `toCommand()` gọi `new OrderLine(...)` cho từng dòng. Mapper không gán trực tiếp vào field và không dùng reflection để bỏ qua constructor. Nếu một giá trị không hợp lệ lọt qua DTO, constructor `OrderLine` vẫn có cơ hội từ chối nó.

`Stream.toList()` có từ Java 16 và trả danh sách không sửa được. Constructor `PlaceOrderCommand` tiếp tục tạo defensive copy bằng `List.copyOf()`, nhờ đó hợp đồng của command không phụ thuộc vào implementation collection của mapper.

## 4. Kiểm thử round-trip mapper với JUnit 5

Test mapper cần chứng minh:

- Từng component được chuyển đúng.
- Các dòng lồng nhau không bị bỏ sót.
- Chiều chuyển đổi ngược giữ dữ liệu theo hợp đồng.
- Mapper tạo object thông qua constructor có validation.

Ví dụ test:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.math.BigDecimal;
import java.util.List;
import org.junit.jupiter.api.Test;

class OrderMapperTest {
    @Test
    void mapsRequestToCommandAndBackWithoutLosingData() {
        CreateOrderRequest request = new CreateOrderRequest(
                "C-100",
                List.of(
                        new CreateOrderLineRequest(
                                "KB-01", 2, new BigDecimal("750000.00")),
                        new CreateOrderLineRequest(
                                "MS-02", 1, new BigDecimal("250000.00"))
                )
        );

        PlaceOrderCommand command = OrderMapper.toCommand(request);
        CreateOrderRequest restored = OrderMapper.toRequest(command);

        assertNotNull(command);
        assertEquals(request, restored);
        assertEquals(2, command.lines().size());
        assertEquals("C-100", command.customerId());
    }
}
```

Test này dùng `equals()` của record để kiểm tra cả component cấp ngoài và collection lồng nhau. Các `BigDecimal` được tạo với cùng scale để phép so sánh theo `equals()` phù hợp.

Nếu nghiệp vụ chỉ quan tâm giá trị số mà không quan tâm scale, có thể kiểm tra bằng `compareTo()` hoặc chuẩn hóa scale tại constructor. Không thay đổi semantics chỉ để làm test dễ pass.

### 4.1. Kiểm tra chiều domain → DTO → domain

Nếu mục tiêu là bảo toàn command, có thể kiểm tra chiều ngược:

Đây là method bổ sung trong `OrderMapperTest` ở phần trên; dùng lại các import và fixture của class đó.

```java
@Test
void roundTripsDomainCommandThroughRequestDto() {
    PlaceOrderCommand original = new PlaceOrderCommand(
            "C-200",
            List.of(
                    new OrderLine("BOOK-01", 3, new BigDecimal("19.90")),
                    new OrderLine("PEN-02", 5, new BigDecimal("2.50"))
            )
    );

    CreateOrderRequest dto = OrderMapper.toRequest(original);
    PlaceOrderCommand restored = OrderMapper.toCommand(dto);

    assertEquals(original, restored);
}
```

Test này chứng minh hai chiều mapper bảo toàn dữ liệu mà command và request DTO cùng biểu diễn. Nếu DTO không chứa một component của domain, hãy kiểm tra các component được phép bảo toàn thay vì đòi `equals()` toàn object.

### 4.2. Kiểm tra defensive copy của collection

Một mapper có thể tạo đúng dữ liệu lúc đầu nhưng vô tình để collection mutable bị chia sẻ. Hãy kiểm tra cả nguồn và kết quả:

```java
@Test
void commandKeepsItsOwnUnmodifiableList() {
    OrderLine line = new OrderLine(
            "BOOK-01", 1, new BigDecimal("19.90"));

    var source = new java.util.ArrayList<>(List.of(line));
    PlaceOrderCommand command = new PlaceOrderCommand("C-300", source);

    source.clear();

    assertEquals(1, command.lines().size());
    assertEquals(line, command.lines().get(0));
}
```

Có thể kiểm tra accessor không cho sửa:

Đây cũng là method bổ sung trong `OrderMapperTest`.

```java
import static org.junit.jupiter.api.Assertions.assertThrows;

@Test
void commandDoesNotExposeMutableList() {
    PlaceOrderCommand command = new PlaceOrderCommand(
            "C-300",
            List.of(new OrderLine("BOOK-01", 1, new BigDecimal("19.90")))
    );

    assertThrows(
            UnsupportedOperationException.class,
            () -> command.lines().add(
                    new OrderLine("PEN-02", 1, new BigDecimal("2.50")))
    );
}
```

Hai test này kiểm tra cấu trúc collection. `List.copyOf()` không tự làm các phần tử mutable trở thành bất biến sâu; nếu component chứa object mutable, cần quyết định có chuyển chúng thành snapshot riêng hay không.

## 5. Kiểm thử JSON round-trip với Jackson

Mapper round-trip chưa kiểm tra annotation JSON, naming strategy hoặc thư viện có gọi đúng constructor khi deserialize hay không. Cần một test riêng cho đường JSON.

Jackson Databind từ phiên bản 2.12 hỗ trợ record. Ví dụ cấu hình mapper rõ ràng:

```java
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.json.JsonMapper;

JsonMapper mapper = JsonMapper.builder()
        .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
        .build();
```

Test serialize rồi deserialize:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.json.JsonMapper;
import java.math.BigDecimal;
import java.util.List;
import org.junit.jupiter.api.Test;

class OrderJsonRoundTripTest {
    private final JsonMapper mapper = JsonMapper.builder()
            .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
            .build();

    @Test
    void serializesAndDeserializesNestedRecordComponents() throws Exception {
        CreateOrderRequest original = new CreateOrderRequest(
                "C-100",
                List.of(new CreateOrderLineRequest(
                        "KB-01", 2, new BigDecimal("750000.00")))
        );

        String json = mapper.writeValueAsString(original);
        CreateOrderRequest restored =
                mapper.readValue(json, CreateOrderRequest.class);

        assertEquals(original, restored);
    }
}
```

Khi deserialize, Jackson tạo `CreateOrderRequest` và các record con qua constructor tương ứng. Compact constructor của từng record được thực thi, nên validation và defensive copy vẫn có hiệu lực.

### 5.1. Không so sánh JSON thô nếu thứ tự property không phải hợp đồng

Một test như `assertEquals(expectedJson, actualJson)` có thể thất bại do khác khoảng trắng hoặc thứ tự property, dù hai JSON có cùng cấu trúc và giá trị.

Nếu hợp đồng không yêu cầu thứ tự property, thêm assertion JSON tree vào cùng test method sau khi đã tạo biến `json` và `mapper`:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import com.fasterxml.jackson.databind.JsonNode;

JsonNode expected = mapper.readTree("""
        {
          "customer_id": "C-100",
          "lines": [
            {
              "sku": "KB-01",
              "quantity": 2,
              "unit_price": 750000.00
            }
          ]
        }
        """);

JsonNode actual = mapper.readTree(json);

assertEquals(expected, actual);
```

Cách này kiểm tra cấu trúc JSON, tên property, số lượng phần tử và giá trị. Nếu định dạng số hoặc chuỗi là hợp đồng cần kiểm tra chính xác, hãy viết assertion riêng cho trường đó.

## 6. Chứng minh constructor validation không bị bỏ qua

Một round-trip chỉ dùng dữ liệu hợp lệ chưa chứng minh constructor validation đang bảo vệ dữ liệu. Cần tạo trường hợp không hợp lệ và xác minh nó bị từ chối.

### 6.1. Kiểm tra constructor trực tiếp

```java
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class OrderLineValidationTest {
    @Test
    void rejectsNonPositiveUnitPrice() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new OrderLine("KB-01", 1, BigDecimal.ZERO)
        );
    }
}
```

Test này xác nhận invariant ở domain record. Nhưng nó chưa chứng minh mapper hoặc thư viện JSON thực sự đi qua constructor đó.

### 6.2. Kiểm tra validation qua mapper

DTO ở ví dụ trên kiểm tra SKU và quantity, nhưng để minh họa mapper không bỏ qua invariant miền, nó chưa từ chối đơn giá bằng 0. Khi mapper tạo `OrderLine`, constructor miền phải ném lỗi:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import java.util.List;
import org.junit.jupiter.api.Test;

class OrderMapperValidationTest {
    @Test
    void domainConstructorRejectsInvalidValueDuringMapping() {
        CreateOrderRequest request = new CreateOrderRequest(
                "C-100",
                List.of(new CreateOrderLineRequest(
                        "KB-01", 1, BigDecimal.ZERO))
        );

        assertThrows(
                IllegalArgumentException.class,
                () -> OrderMapper.toCommand(request)
        );
    }
}
```

Test này có ý nghĩa quan trọng: mapper không chỉ chuyển field mà còn phải tạo domain object hợp lệ. Nếu sau này ai đó thay mapper bằng cách dùng reflection hoặc cơ chế khởi tạo bỏ qua constructor, test này sẽ phát hiện hành vi thay đổi.

### 6.3. Kiểm tra validation khi deserialize JSON trực tiếp thành domain record

Nếu ứng dụng deserialize trực tiếp record miền, hãy kiểm tra constructor validation trên đường đó:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.databind.JsonMappingException;
import com.fasterxml.jackson.databind.json.JsonMapper;
import org.junit.jupiter.api.Test;

class OrderLineJsonValidationTest {
    private final JsonMapper mapper = JsonMapper.builder().build();

    @Test
    void rejectsInvalidDomainValueDuringDeserialization() {
        String json = """
                {
                  "sku": "KB-01",
                  "quantity": 1,
                  "unitPrice": 0
                }
                """;

        JsonMappingException exception = assertThrows(
                JsonMappingException.class,
                () -> mapper.readValue(json, OrderLine.class)
        );

        assertTrue(hasCause(exception, IllegalArgumentException.class));
    }

    private static boolean hasCause(
            Throwable error,
            Class<? extends Throwable> expectedType
    ) {
        for (Throwable current = error; current != null; current = current.getCause()) {
            if (expectedType.isInstance(current)) {
                return true;
            }
        }
        return false;
    }
}
```

Jackson thường bọc exception từ constructor trong exception mapping. Vì vậy, test kiểm tra loại exception mapping bên ngoài và kiểm tra cause chain chứa `IllegalArgumentException`. Cách này tránh phụ thuộc vào toàn bộ nội dung thông báo lỗi của thư viện.

Trong code test hoàn chỉnh, khai báo `mapper` giống test JSON round-trip ở phần trước. Nếu framework của ứng dụng chuẩn hóa lỗi thành exception riêng, hãy kiểm tra loại exception ở đúng ranh giới ứng dụng thay vì buộc test phụ thuộc exception nội bộ của Jackson.

## 7. Kiểm thử field thiếu, null và collection lồng nhau

Dữ liệu JSON có thể thiếu property hoặc ghi rõ null. Với component tham chiếu, cả hai trường hợp có thể dẫn đến null được truyền vào constructor, tùy cấu hình mapper. Với primitive, field thiếu có thể thành giá trị mặc định như 0 hoặc false.

Các method test dưới đây được thêm vào một test class có field mapper. Ví dụ phần khai báo tối thiểu:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.fasterxml.jackson.databind.JsonMappingException;
import com.fasterxml.jackson.databind.json.JsonMapper;
import org.junit.jupiter.api.Test;

class CreateOrderRequestBindingTest {
    private final JsonMapper mapper = JsonMapper.builder().build();
    // Đặt các method test tiếp theo trước dấu đóng class.
}
```

Ví dụ `CreateOrderRequest` yêu cầu `customerId` và `lines` khác null. Hãy kiểm tra cả hai dạng đầu vào:

```java
@Test
void rejectsNullRequiredComponent() {
    String json = """
            {
              "customer_id": null,
              "lines": []
            }
            """;

    assertThrows(
            JsonMappingException.class,
            () -> mapper.readValue(json, CreateOrderRequest.class)
    );
}
```

Property bị thiếu:

```java
@Test
void rejectsMissingRequiredCollection() {
    String json = """
            {
              "customer_id": "C-100"
            }
            """;

    assertThrows(
            JsonMappingException.class,
            () -> mapper.readValue(json, CreateOrderRequest.class)
    );
}
```

Collection hiện diện nhưng có giá trị null:

```java
@Test
void rejectsNullRequiredCollection() {
    String json = """
            {
              "customer_id": "C-100",
              "lines": null
            }
            """;

    assertThrows(
            JsonMappingException.class,
            () -> mapper.readValue(json, CreateOrderRequest.class)
    );
}
```

Các test trên dựa vào constructor dùng `Objects.requireNonNull`. Nếu API muốn chuẩn hóa missing thành collection rỗng, hãy thay hợp đồng constructor và test theo chính sách đó. Không để hành vi mặc định của thư viện quyết định ngữ nghĩa nghiệp vụ một cách vô tình.

### 7.1. Kiểm tra primitive thiếu field

Với `quantity` kiểu `int`, JSON thiếu property có thể đưa giá trị 0 vào constructor. Constructor `CreateOrderLineRequest` từ chối quantity không dương, do đó test có thể xác minh field thiếu bị phát hiện:

```java
@Test
void rejectsMissingPrimitiveQuantity() {
    String json = """
            {
              "sku": "KB-01",
              "unit_price": 750000
            }
            """;

    assertThrows(
            JsonMappingException.class,
            () -> mapper.readValue(json, CreateOrderLineRequest.class)
    );
}
```

Nếu cần phân biệt rõ “không có quantity” với quantity bằng 0, dùng `Integer` trong DTO đầu vào rồi kiểm tra null tường minh. Primitive chỉ giữ giá trị số, không giữ trạng thái property đã xuất hiện hay chưa.

### 7.2. Kiểm tra collection con và phần tử null

`List.copyOf()` từ chối phần tử null. Khi request có phần tử null trong `lines`, constructor phải từ chối:

```java
@Test
void rejectsNullElementInsideLines() {
    String json = """
            {
              "customer_id": "C-100",
              "lines": [null]
            }
            """;

    assertThrows(
            JsonMappingException.class,
            () -> mapper.readValue(json, CreateOrderRequest.class)
    );
}
```

Test này khác với test collection reference null. Một list có thể tồn tại nhưng chứa phần tử null; hợp đồng của record cần quyết định riêng cả hai trường hợp.

## 8. Tổ chức test để dễ bảo trì

Một bộ test tốt thường chia theo ranh giới:

| Nhóm test | Đối tượng | Điều cần chứng minh |
|---|---|---|
| Constructor test | Domain record | Invariant và defensive copy |
| Mapper test | DTO ↔ domain | Component được chuyển đúng, không mất dữ liệu |
| JSON round-trip | Jackson/Gson và DTO | Tên property, serialization, deserialization |
| JSON validation test | JSON → record | Constructor từ chối dữ liệu không hợp lệ |
| Boundary test | Toàn bộ luồng | Lỗi được chuyển thành response phù hợp |

Không nhất thiết mỗi test phải khởi động toàn bộ Spring context hoặc database. Dùng unit test cho constructor và mapper; chỉ dùng integration test khi cần xác minh cấu hình framework thực tế, custom module, dependency injection hoặc exception translation.

### 8.1. Tránh test quá phụ thuộc chi tiết triển khai

Không nên:

- So sánh chuỗi JSON thô nếu khoảng trắng và thứ tự property không phải hợp đồng.
- Khẳng định constructor được gọi bằng cách kiểm tra reflection nội bộ của thư viện.
- So sánh stack trace hoặc thông báo exception đầy đủ.
- Dùng `assertEquals()` cho object có semantics equality không phù hợp.
- Kiểm tra một mapper bằng cách gọi lại chính mapper để tạo expected value.
- Chỉ kiểm tra serialize mà không deserialize.
- Chỉ kiểm tra dữ liệu hợp lệ mà không kiểm tra invariant bị vi phạm.

Nên tạo expected object độc lập, kiểm tra từng component quan trọng và xác minh lỗi tại ranh giới được ứng dụng công bố.

### 8.2. Kiểm tra phiên bản thư viện trong môi trường test

Jackson cần phiên bản có record support và các module liên quan phải đồng bộ. Test chạy trong IDE có thể dùng classpath khác với runtime của ứng dụng nếu dependency management bị lệch.

Khi nâng cấp dependency, chạy lại test round-trip trên classpath test và runtime phù hợp. Với Jackson, giữ `jackson-databind`, `jackson-core`, `jackson-annotations` và module Java Time cùng dòng phiên bản do BOM/framework quản lý.

Nếu ứng dụng dùng Gson, viết test tương tự với `Gson.fromJson()` và `Gson.toJson()`. Đối với `java.time`, đăng ký adapter có định dạng rõ ràng; không giả định thư viện tự chọn đúng biểu diễn JSON nghiệp vụ.

## 9. Checklist cho round-trip và constructor validation

Trước khi xem một mapper hoặc record DTO đã được kiểm thử, hãy xác nhận:

1. Đã xác định dữ liệu nào phải được bảo toàn qua round-trip chưa?
2. Có test riêng cho mapper và JSON serialization/deserialization chưa?
3. Có kiểm tra tất cả component lồng nhau và collection chưa?
4. Record constructor có kiểm tra null, rỗng, miền giá trị và defensive copy chưa?
5. Có test chứng minh mapper tạo domain record qua constructor hợp lệ không?
6. Có test dữ liệu không hợp lệ qua JSON và kiểm tra cause của exception không?
7. Field thiếu, null và primitive default đã được kiểm tra riêng chưa?
8. Test có tránh phụ thuộc thứ tự property hoặc thông báo lỗi không ổn định không?
9. Có xác minh equality phù hợp với kiểu component như BigDecimal, array và collection không?
10. Test chạy với đúng phiên bản thư viện và cấu hình runtime của ứng dụng không?

## 10. Bài tập vận dụng

**Bài 1 — Round-trip mapper:** Hoàn thiện `OrderMapper.toCommand()` và `toRequest()`. Tạo dữ liệu gồm nhiều dòng hàng, kiểm tra domain → DTO → domain bằng `assertEquals()`.

**Bài 2 — Invariant constructor:** Thêm quy tắc đơn giá phải lớn hơn 0 vào `OrderLine`. Viết test constructor trực tiếp và test mapper nhận DTO có đơn giá bằng 0.

**Bài 3 — JSON round-trip:** Dùng Jackson để serialize và deserialize `CreateOrderRequest`. So sánh record sau khi đọc và JSON tree để kiểm tra tên property.

**Bài 4 — Missing và null:** Viết test cho `customer_id` bị thiếu, `customer_id` null, `lines` null, phần tử null và `quantity` bị thiếu. Giải thích test nào thất bại ở constructor DTO và test nào thất bại ở constructor domain.

**Bài 5 — Giá trị có scale:** Thay đơn giá bằng `BigDecimal("2.0")` và `BigDecimal("2.00")`. So sánh `equals()` với `compareTo()` và quyết định scale có phải một phần hợp đồng của ứng dụng không.

---

**Ghi nhớ:** Round-trip chỉ có ý nghĩa khi xác định rõ dữ liệu nào phải được bảo toàn. Hãy kiểm tra riêng mapper, JSON và luồng qua ranh giới ứng dụng. Dữ liệu hợp lệ phải tạo ra record đúng giá trị; dữ liệu vi phạm invariant phải bị constructor từ chối cả khi code gọi trực tiếp, mapper chuyển đổi hay thư viện deserialize record.

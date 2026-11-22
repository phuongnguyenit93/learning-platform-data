# Tạo ObjectWriter theo kiểu dữ liệu và cách trình bày

`ObjectMapper` là thành phần trung tâm để cấu hình và thực hiện chuyển đổi giữa object Java với JSON. Trong một ứng dụng, mapper thường được cấu hình một lần rồi tái sử dụng. Tuy nhiên, mỗi nơi ghi JSON có thể cần một kiểu dữ liệu gốc, định dạng hoặc tùy chọn serialize khác nhau.

`ObjectWriter` giải quyết nhu cầu đó. Nó là đối tượng ghi JSON được tạo từ `ObjectMapper`, mang theo cấu hình serialize cho một lần sử dụng hoặc một nhóm lần sử dụng. Có thể tạo writer cho một kiểu Java cụ thể, cho một kiểu generic, cho JSON gọn, JSON dễ đọc hoặc cho một bộ tùy chọn riêng.

Điểm quan trọng là `ObjectWriter` bất biến và có thể tái sử dụng an toàn giữa nhiều luồng. Khi thay đổi cấu hình writer, Jackson trả về một writer mới; cấu hình của mapper và writer cũ không bị sửa theo.

## 1. Phân biệt ObjectMapper và ObjectWriter

Hai kiểu này có trách nhiệm liên quan nhưng khác nhau:

| Thành phần | Trách nhiệm |
|---|---|
| `ObjectMapper` | Cấu hình chung, đăng ký module, quy tắc ánh xạ, serializer/deserializer và thực hiện cả serialize lẫn deserialize. |
| `ObjectWriter` | Ghi object thành JSON với kiểu gốc và cấu hình serialize đã chọn. |
| `ObjectReader` | Đọc JSON theo kiểu đích và cấu hình deserialize đã chọn. |

Một mapper có thể tạo nhiều writer cho các mục đích khác nhau:

~~~text
                         ObjectMapper
                              |
             +----------------+----------------+
             |                |                |
             v                v                v
       ObjectWriter      ObjectWriter      ObjectWriter
       OrderResponse     List<Order>       OrderResponse
       JSON compact      JSON pretty       JSON compact
~~~

Ví dụ, API có thể trả JSON gọn để giảm dung lượng truyền tải, trong khi chức năng export tạo JSON có thụt lề để người dùng dễ đọc. Cả hai cùng dùng một mapper đã đăng ký module và quy tắc ánh xạ chung, nhưng dùng hai writer riêng.

Không cần tạo một `ObjectMapper` mới cho mỗi request chỉ để đổi cách trình bày. Cách đó làm phân tán cấu hình, tăng chi phí khởi tạo và dễ khiến các đường serialize trong cùng ứng dụng có hành vi khác nhau.

## 2. Tạo ObjectWriter cho một kiểu Java cụ thể

Cách cơ bản nhất là gọi `writerFor(Class)`:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.ObjectWriter;
import com.fasterxml.jackson.databind.json.JsonMapper;

public record OrderResponse(
    String orderId,
    String customerName,
    int itemCount
) {}

ObjectMapper mapper = JsonMapper.builder().build();

ObjectWriter orderWriter =
    mapper.writerFor(OrderResponse.class);

OrderResponse order =
    new OrderResponse("ORD-100", "Linh", 3);

String json = orderWriter.writeValueAsString(order);
~~~

`writerFor(OrderResponse.class)` cung cấp kiểu gốc mà writer sẽ sử dụng khi tìm serializer. Điều này làm cho mục đích của writer rõ ràng và giúp Jackson chuẩn bị serializer cho kiểu đó khi có thể.

Có thể đặt tên writer theo nhiệm vụ để code thể hiện rõ ý định:

~~~java
ObjectWriter orderResponseWriter =
    mapper.writerFor(OrderResponse.class);

ObjectWriter customerResponseWriter =
    mapper.writerFor(CustomerResponse.class);
~~~

Khi một service ghi nhiều loại response, các writer có kiểu gốc riêng giúp tránh việc mọi nơi đều gọi `mapper.writeValueAsString(Object)` mà không thể hiện kiểu dữ liệu dự kiến.

Kiểu gốc của writer là thông tin cho quá trình serialize. Nó không thay thế validation nghiệp vụ và cũng không tự bảo đảm object có dữ liệu hợp lệ theo API contract.

## 3. Tạo writer cho kiểu generic

Java có type erasure: thông tin tham số kiểu generic thường không còn đầy đủ ở runtime nếu chỉ truyền `List.class`. Vì vậy, khi ghi một collection mà kiểu phần tử có ý nghĩa, hãy cung cấp đầy đủ kiểu generic.

Dùng `TypeReference`:

~~~java
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectWriter;
import java.util.List;

ObjectWriter ordersWriter = mapper.writerFor(
    new TypeReference<List<OrderResponse>>() {}
);

List<OrderResponse> orders = List.of(
    new OrderResponse("ORD-100", "Linh", 3),
    new OrderResponse("ORD-101", "Minh", 1)
);

String json = ordersWriter.writeValueAsString(orders);
~~~

Nếu chỉ dùng:

~~~java
ObjectWriter writer = mapper.writerFor(List.class);
~~~

Jackson chỉ nhận được kiểu gốc là `List`, không có thông tin khai báo rằng các phần tử là `OrderResponse`. Khi cần serializer theo kiểu phần tử, generic type hoặc kiểu đa hình, thông tin kiểu đầy đủ có thể ảnh hưởng đến kết quả serialize.

Một cách khác là tạo `JavaType` bằng `TypeFactory`:

~~~java
import com.fasterxml.jackson.databind.JavaType;

JavaType orderListType = mapper.getTypeFactory()
    .constructCollectionType(List.class, OrderResponse.class);

ObjectWriter ordersWriter = mapper.writerFor(orderListType);
~~~

`JavaType` hữu ích khi kiểu đích được xây dựng động, ví dụ kiểu collection hoặc map có tham số kiểu được xác định từ metadata lúc chạy. Với kiểu generic cố định trong code, `TypeReference` thường dễ đọc hơn.

## 4. Ghi JSON gọn và JSON có thụt lề

Mặc định, Jackson thường ghi JSON ở dạng compact: không thêm khoảng trắng và xuống dòng chỉ để trình bày.

Ví dụ:

~~~json
{"orderId":"ORD-100","customerName":"Linh","itemCount":3}
~~~

Để tạo JSON dễ đọc, có thể bật `SerializationFeature.INDENT_OUTPUT` riêng cho writer:

~~~java
import com.fasterxml.jackson.databind.SerializationFeature;

ObjectWriter compactWriter =
    mapper.writerFor(OrderResponse.class);

ObjectWriter prettyWriter =
    compactWriter.with(SerializationFeature.INDENT_OUTPUT);

String compactJson = compactWriter.writeValueAsString(order);
String prettyJson = prettyWriter.writeValueAsString(order);
~~~

Kết quả pretty JSON có dạng:

~~~json
{
  "orderId" : "ORD-100",
  "customerName" : "Linh",
  "itemCount" : 3
}
~~~

Hai chuỗi JSON biểu diễn cùng một object. Khác biệt là khoảng trắng, xuống dòng và thụt lề. Pretty JSON hữu ích cho file export, log dành cho người đọc hoặc dữ liệu mẫu; JSON compact thường phù hợp hơn cho lưu lượng API lớn.

Có thể tạo writer pretty ngay từ mapper:

~~~java
ObjectWriter prettyOrderWriter = mapper
    .writerFor(OrderResponse.class)
    .with(SerializationFeature.INDENT_OUTPUT);
~~~

Tùy chọn này chỉ áp dụng cho writer vừa tạo. Mapper không bị chuyển sang chế độ pretty cho các lần serialize khác.

Không nên bật `INDENT_OUTPUT` toàn cục chỉ vì một chức năng export cần JSON dễ đọc. Nếu các endpoint API và export dùng cùng mapper, việc bật toàn cục có thể làm thay đổi dung lượng và hình thức response của mọi nơi ghi JSON.

## 5. Tùy chỉnh cách thụt lề bằng PrettyPrinter

Nếu cần kiểm soát cách xuống dòng và thụt lề, có thể cung cấp một `PrettyPrinter` riêng. Jackson cung cấp `DefaultPrettyPrinter` và `DefaultIndenter` để xây dựng định dạng phổ biến.

Ví dụ dùng hai dấu cách cho object và array:

~~~java
import com.fasterxml.jackson.core.util.DefaultIndenter;
import com.fasterxml.jackson.core.util.DefaultPrettyPrinter;

DefaultIndenter indenter =
    new DefaultIndenter("  ", "\n");

DefaultPrettyPrinter prettyPrinter =
    new DefaultPrettyPrinter()
        .withObjectIndenter(indenter)
        .withArrayIndenter(indenter);

ObjectWriter customPrettyWriter = mapper
    .writerFor(OrderResponse.class)
    .with(prettyPrinter);

String json = customPrettyWriter.writeValueAsString(order);
~~~

Ở đây:

- `DefaultIndenter("  ", "\n")` quy định chuỗi thụt lề và ký tự xuống dòng.
- `withObjectIndenter(...)` áp dụng indenter cho thuộc tính object.
- `withArrayIndenter(...)` áp dụng indenter cho phần tử array.
- `with(prettyPrinter)` gắn bộ trình bày vào writer.

Có thể chọn indenter khác cho array nếu muốn mảng ngắn nằm trên một dòng hoặc có cách trình bày riêng. Tuy nhiên, hãy cân nhắc khả năng đọc và tính nhất quán trước khi tạo định dạng quá đặc biệt.

PrettyPrinter kiểm soát cách ghi dấu phân cách và khoảng trắng. Nó không thay đổi ý nghĩa dữ liệu, không lọc trường và không thay thế các annotation điều khiển tên hoặc thứ tự thuộc tính.

## 6. Đặt tùy chọn serialize riêng cho từng writer

Ngoài kiểu gốc và pretty printing, `ObjectWriter` có thể nhận các tùy chọn serialize khác. Điều này hữu ích khi cùng một kiểu Java được xuất theo các mục đích khác nhau.

Ví dụ, một writer ghi thời gian thành chuỗi ISO-8601 và một writer khác dùng timestamp. Giả sử mapper đã đăng ký `JavaTimeModule`:

~~~java
ObjectWriter isoTimeWriter = mapper
    .writerFor(EventResponse.class)
    .without(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);

ObjectWriter timestampWriter = mapper
    .writerFor(EventResponse.class)
    .with(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
~~~

Hai writer có cùng kiểu gốc nhưng cách biểu diễn thời gian khác nhau. Chỉ nên cung cấp nhiều dạng biểu diễn như vậy khi hợp đồng trao đổi thực sự quy định hoặc cho phép chúng.

Một tùy chọn khác là sắp xếp khóa của Map:

~~~java
ObjectWriter orderedMapWriter = mapper
    .writerFor(Map.class)
    .with(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS);
~~~

Tùy chọn này áp dụng cho các entry của Map. Nó không tự quy định thứ tự thuộc tính của mọi Java bean. Nếu thứ tự field của một DTO cần ổn định, có thể khai báo `@JsonPropertyOrder` trên kiểu đó hoặc dùng cấu hình mapper phù hợp.

Có thể kết hợp các tùy chọn trên cùng một writer:

~~~java
ObjectWriter exportWriter = mapper
    .writerFor(OrderResponse.class)
    .with(SerializationFeature.INDENT_OUTPUT)
    .without(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
~~~

Mỗi lời gọi `with(...)` hoặc `without(...)` tạo cấu hình writer mới. Có thể gán kết quả vào biến mới hoặc nối lời gọi như ví dụ. Hãy đọc chuỗi cấu hình từ trái sang phải để biết writer cuối cùng đang có những tùy chọn nào.

## 7. ObjectWriter là bất biến và có thể tái sử dụng

`ObjectWriter` được thiết kế để tái sử dụng và an toàn giữa nhiều luồng. Các phương thức cấu hình như `with`, `without` hoặc `forType` trả về một writer đã cấu hình, không sửa writer ban đầu.

Ví dụ:

~~~java
ObjectWriter baseWriter =
    mapper.writerFor(OrderResponse.class);

ObjectWriter prettyWriter =
    baseWriter.with(SerializationFeature.INDENT_OUTPUT);

ObjectWriter compactWriter =
    baseWriter.without(SerializationFeature.INDENT_OUTPUT);
~~~

Ba biến tham chiếu đến ba cấu hình writer có thể sử dụng độc lập. Việc tạo `prettyWriter` không làm `baseWriter` chuyển sang pretty output.

Đặc tính bất biến cho phép giữ writer trong service hoặc component để dùng lại:

~~~java
public final class OrderJsonExporter {
    private final ObjectWriter compactWriter;
    private final ObjectWriter prettyWriter;

    public OrderJsonExporter(ObjectMapper mapper) {
        this.compactWriter = mapper.writerFor(OrderResponse.class);
        this.prettyWriter = compactWriter.with(
            SerializationFeature.INDENT_OUTPUT
        );
    }

    public String exportCompact(OrderResponse order) throws JsonProcessingException {
        return compactWriter.writeValueAsString(order);
    }

    public String exportReadable(OrderResponse order) throws JsonProcessingException {
        return prettyWriter.writeValueAsString(order);
    }
}
~~~

Đoạn code cần import `JsonProcessingException` và `SerializationFeature`. Trong ứng dụng Spring, mapper có thể được inject từ cấu hình chung; exporter chỉ giữ các writer dành cho hai cách xuất dữ liệu.

Nên hoàn tất cấu hình `ObjectMapper` trước khi tạo và chia sẻ writer. Mapper cũng được thiết kế để dùng chung sau khi cấu hình hoàn tất, nhưng không nên liên tục thay đổi module, serializer hoặc feature trên mapper đang được nhiều thành phần sử dụng.

## 8. Ghi ra String, OutputStream hoặc Writer

`ObjectWriter` có nhiều cách ghi kết quả tùy đích đầu ra.

Ghi ra String khi cần trả response, so sánh JSON trong test hoặc đưa dữ liệu sang một bước xử lý tiếp theo:

~~~java
String json = orderWriter.writeValueAsString(order);
~~~

Ghi trực tiếp ra OutputStream khi xuất file hoặc gửi dữ liệu đến một luồng byte:

~~~java
try (OutputStream output = Files.newOutputStream(outputPath)) {
    prettyOrderWriter.writeValue(output, order);
}
~~~

Ghi ra `Writer` khi đích là một luồng ký tự:

~~~java
try (Writer output = Files.newBufferedWriter(outputPath, StandardCharsets.UTF_8)) {
    prettyOrderWriter.writeValue(output, order);
}
~~~

Các ví dụ ghi file cần import những kiểu tương ứng trong `java.io` và `java.nio.file`. Việc đóng stream thuộc trách nhiệm của nơi tạo stream; try-with-resources bảo đảm tài nguyên được đóng sau khi ghi.

Ghi trực tiếp vào stream có thể tránh tạo thêm một chuỗi JSON lớn trong bộ nhớ. Tuy nhiên, hãy xử lý IOException và vòng đời stream đúng cách. Không chia sẻ cùng một OutputStream giữa các request đồng thời nếu không có cơ chế đồng bộ và quản lý quyền sở hữu rõ ràng.

## 9. Chọn writer theo kiểu dữ liệu và mục đích xuất

Một service có thể tạo writer theo từng kiểu response và định dạng:

~~~java
public final class JsonWriters {
    private final ObjectWriter orderCompact;
    private final ObjectWriter orderPretty;
    private final ObjectWriter orderListCompact;

    public JsonWriters(ObjectMapper mapper) {
        this.orderCompact = mapper.writerFor(OrderResponse.class);

        this.orderPretty = orderCompact.with(
            SerializationFeature.INDENT_OUTPUT
        );

        this.orderListCompact = mapper.writerFor(
            new TypeReference<List<OrderResponse>>() {}
        );
    }

    public String writeOrder(OrderResponse order)
            throws JsonProcessingException {
        return orderCompact.writeValueAsString(order);
    }

    public String writeOrderForDownload(OrderResponse order)
            throws JsonProcessingException {
        return orderPretty.writeValueAsString(order);
    }

    public String writeOrders(List<OrderResponse> orders)
            throws JsonProcessingException {
        return orderListCompact.writeValueAsString(orders);
    }
}
~~~

Các import cần có:

~~~java
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.ObjectWriter;
import com.fasterxml.jackson.databind.SerializationFeature;
import java.util.List;
~~~

Ví dụ này tạo ba writer có mục đích rõ ràng:

- `orderCompact` ghi một order theo kiểu gốc `OrderResponse`.
- `orderPretty` ghi cùng kiểu order nhưng có thụt lề.
- `orderListCompact` ghi collection và giữ thông tin generic về phần tử.

Trong code thực tế, không nhất thiết phải tạo một lớp registry cho mọi writer. Nếu chỉ có một hoặc hai trường hợp đơn giản, tạo writer tại component sử dụng cũng đủ. Khi nhiều nơi dùng chung một kiểu và một định dạng, tập trung writer giúp giảm cấu hình lặp.

## 10. Những nhầm lẫn thường gặp

### Thay đổi ObjectMapper để xử lý một lần xuất dữ liệu

Nếu bật `INDENT_OUTPUT` trên mapper dùng chung, mọi nơi dùng mapper có thể nhận JSON có thụt lề. Hãy tạo writer với tùy chọn riêng để phạm vi thay đổi rõ ràng.

### Dùng ObjectWriter mà không cung cấp kiểu generic

`writerFor(List.class)` không lưu được kiểu phần tử như `List<OrderResponse>`. Khi kiểu phần tử quan trọng, dùng `TypeReference` hoặc `JavaType`.

### Cho rằng pretty printing thay đổi cấu trúc JSON

PrettyPrinter thay đổi khoảng trắng và cách xuống dòng. Nó không đổi array thành object, không loại bỏ null, không đổi tên field và không kiểm tra dữ liệu nghiệp vụ.

### Dùng thứ tự thuộc tính như một cách ký JSON

Thứ tự field của object JSON thường không mang ý nghĩa trong hợp đồng trao đổi. Nếu hệ thống cần JSON canonical để ký hoặc hash, phải dùng quy tắc canonicalization được xác định rõ. Chỉ bật pretty printing hoặc sắp xếp Map không đủ để tạo một định dạng canonical hoàn chỉnh.

### Tạo ObjectMapper mới cho mỗi lần ghi

Việc này có thể khiến module và cấu hình khác nhau giữa các request, đồng thời lặp chi phí khởi tạo. Hãy cấu hình mapper một lần, sau đó tạo writer bất biến cho từng kiểu và cách trình bày.

### Nhầm ObjectWriter với ObjectReader

`ObjectWriter` chỉ phục vụ serialize. Khi cần cấu hình đọc JSON theo kiểu đích, dùng `ObjectReader` được tạo từ mapper, ví dụ `mapper.readerFor(OrderResponse.class)`.

## 11. Kiểm tra writer trong unit test

Một kiểm tra tốt nên xác nhận cả nội dung JSON và sự độc lập của các writer.

Ví dụ với JUnit:

~~~java
@Test
void shouldCreateCompactAndPrettyWritersForOrder() throws Exception {
    ObjectMapper mapper = JsonMapper.builder().build();

    ObjectWriter compactWriter =
        mapper.writerFor(OrderResponse.class);

    ObjectWriter prettyWriter =
        compactWriter.with(SerializationFeature.INDENT_OUTPUT);

    OrderResponse order =
        new OrderResponse("ORD-100", "Linh", 3);

    String compact = compactWriter.writeValueAsString(order);
    String pretty = prettyWriter.writeValueAsString(order);

    assertFalse(compact.contains("\n"));
    assertTrue(pretty.contains("\n"));

    JsonNode compactTree = mapper.readTree(compact);
    JsonNode prettyTree = mapper.readTree(pretty);

    assertEquals(compactTree, prettyTree);
}
~~~

Đoạn test giả định đã import `org.junit.jupiter.api.Test`, các assertion của JUnit, `JsonMapper`, `ObjectMapper`, `ObjectWriter`, `SerializationFeature` và `JsonNode`. Kiểu `OrderResponse` là record đã định nghĩa ở ví dụ trước.

Test này xác nhận:

- Writer compact không thêm xuống dòng trình bày.
- Writer pretty có xuống dòng.
- Hai output vẫn biểu diễn cùng một cây JSON.
- Việc tạo writer pretty không làm thay đổi nội dung của writer compact.

Với writer generic, nên thêm test cho collection có nhiều phần tử để xác nhận cấu trúc array và kiểu dữ liệu từng phần tử. Với writer có module ngày giờ hoặc custom serializer, cần có fixture kiểm tra chính xác wire format mà consumer mong đợi.

## Kết luận

`ObjectWriter` cho phép tạo cấu hình serialize riêng theo kiểu Java và cách trình bày mà không phải thay đổi mapper dùng chung. Hãy dùng `writerFor` cho kiểu cụ thể, `TypeReference` hoặc `JavaType` cho kiểu generic, và cấu hình pretty printing hoặc serialization feature trực tiếp trên writer.

Vì writer bất biến và có thể tái sử dụng, ứng dụng có thể chuẩn bị sẵn các writer cho response, export hoặc collection. Kiểm tra JSON đầu ra bằng cách parse lại và so sánh cấu trúc giúp xác nhận rằng thay đổi cách trình bày không vô tình làm thay đổi dữ liệu theo hợp đồng.


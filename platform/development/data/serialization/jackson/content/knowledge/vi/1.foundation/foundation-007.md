# Quan hệ giữa cấu trúc dữ liệu, kiểu Java và hợp đồng trao đổi

Khi một ứng dụng Java gửi hoặc nhận JSON, có ba lớp cần được phân biệt:

1. **Cấu trúc dữ liệu** mô tả cách thông tin được tổ chức trong thông điệp: đối tượng, mảng, giá trị đơn, giá trị rỗng và các cấp lồng nhau.
2. **Kiểu Java** mô tả cách chương trình biểu diễn và thao tác với thông tin đó: class, record, enum, List, Map, BigDecimal, Instant, v.v.
3. **Hợp đồng trao đổi** quy định hai phía thống nhất điều gì về dữ liệu: tên trường, ý nghĩa, kiểu trên wire, trường bắt buộc hay tùy chọn, định dạng, giới hạn giá trị và cách xử lý khi cấu trúc thay đổi.

Jackson đứng giữa kiểu Java và biểu diễn JSON. Nó chuyển đổi dữ liệu theo cấu hình và metadata mà ứng dụng cung cấp. Jackson không tự quyết định đầy đủ ý nghĩa nghiệp vụ của thông điệp; hợp đồng vẫn cần được thiết kế và thực thi rõ ràng.

## 1. Ba lớp trả lời ba câu hỏi khác nhau

Hãy xét một thông điệp mô tả đơn hàng:

~~~json
{
  "orderId": "ORD-2026-001",
  "customer": {
    "id": "C-17",
    "displayName": "Linh"
  },
  "items": [
    {
      "sku": "BOOK-01",
      "quantity": 2,
      "unitPrice": 125000.00
    }
  ],
  "status": "paid",
  "createdAt": "2026-11-12T08:15:30Z",
  "note": null
}
~~~

Cấu trúc JSON cho biết thông điệp có một object ở ngoài cùng. Object đó chứa các trường đơn như orderId và status, một object customer, một array items, một chuỗi thời gian createdAt và một giá trị null ở note.

Kiểu Java cho biết chương trình sẽ thao tác với các giá trị này như thế nào. Chẳng hạn, orderId có thể được lưu bằng String, items bằng List<OrderItemResponse>, unitPrice bằng BigDecimal, status bằng enum và createdAt bằng Instant.

Hợp đồng trao đổi bổ sung ý nghĩa mà cấu trúc JSON và kiểu Java không thể hiện đầy đủ. Ví dụ:

- orderId là mã đơn hàng ổn định, không phải số thứ tự để đem đi tính toán.
- quantity phải là số nguyên dương.
- unitPrice là đơn giá theo một loại tiền tệ đã được quy ước.
- status chỉ nhận các mã trạng thái mà hai phía cùng hiểu.
- createdAt là thời điểm tuyệt đối theo UTC, được truyền theo định dạng ISO-8601.
- note có thể không có nội dung; hai phía cần thống nhất việc không có note được biểu diễn bằng cách bỏ trường hay gửi null.

Một JSON hợp lệ về cú pháp chưa chắc là thông điệp hợp lệ theo hợp đồng. Ví dụ, quantity bằng -5 vẫn là một JSON number hợp lệ, nhưng có thể vi phạm quy tắc của đơn hàng.

## 2. Cấu trúc JSON và kiểu Java thường ánh xạ với nhau ra sao?

JSON có một tập kiểu dữ liệu nhỏ. Java có hệ thống kiểu phong phú hơn, vì vậy một cấu trúc JSON có thể được ánh xạ vào nhiều kiểu Java tùy mục đích.

| Cấu trúc JSON | Kiểu Java thường dùng | Điểm cần chú ý |
|---|---|---|
| Object | class, record, Map<String, T>, JsonNode | DTO có kiểu rõ ràng phù hợp với hợp đồng ổn định; Map linh hoạt hơn nhưng ít ràng buộc lúc biên dịch. |
| Array | List<T>, Set<T>, T[] | List giữ thứ tự và phần tử lặp; Set loại bỏ phần tử trùng theo quy tắc equals/hashCode. |
| String | String, enum, UUID, kiểu ngày giờ | Muốn chuyển chuỗi thành kiểu chuyên biệt cần quy tắc định dạng hoặc bộ chuyển đổi phù hợp. |
| Number | int, long, Integer, Long, BigInteger, BigDecimal, double | JSON không tự ghi rõ đây là số nguyên Java hay số thực Java; kiểu đích quyết định cách chuyển đổi. |
| Boolean | boolean, Boolean | boolean không biểu diễn được trạng thái null; Boolean có thể biểu diễn true, false và null. |
| null | null trong kiểu tham chiếu | Kiểu nguyên thủy như int và boolean không thể chứa null. |

Có một số khác biệt quan trọng:

- JSON object dùng tên trường dạng chuỗi. Vì vậy Map có khóa không phải String cần quy tắc chuyển đổi khóa khi serialize và deserialize.
- JSON array có thể chứa phần tử trùng nhau. Khi chuyển thành Set, các phần tử trùng có thể bị gộp.
- JSON number không mang thông tin về độ chính xác mà ứng dụng nghiệp vụ mong muốn. Dùng double cho tiền có thể tạo sai số biểu diễn; BigDecimal thường phù hợp hơn.
- JSON string không tự cho biết đó là ngày, thời điểm, mã định danh hay văn bản tự do. Hợp đồng phải định nghĩa định dạng và ý nghĩa.
- JSON không có kiểu riêng cho byte, char, Optional, LocalDate hay enum. Jackson cần quy tắc ánh xạ các kiểu Java đó thành những kiểu JSON có sẵn.

Vì thế, không nên chọn kiểu Java chỉ dựa trên việc JSON có thể chứa giá trị đó. Cần chọn kiểu phản ánh đúng miền dữ liệu và giữ được các quy tắc của hợp đồng.

## 3. Biểu diễn một hợp đồng bằng DTO Java

Trong ứng dụng có API, DTO thường là kiểu Java dành riêng cho dữ liệu vào hoặc ra. DTO giúp hợp đồng bên ngoài ổn định ngay cả khi mô hình nội bộ thay đổi.

Ví dụ:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

import com.fasterxml.jackson.annotation.JsonProperty;

public record OrderResponse(
    @JsonProperty("orderId")
    String id,
    CustomerResponse customer,
    List<OrderItemResponse> items,
    OrderStatus status,
    Instant createdAt,
    String note
) {}

public record CustomerResponse(
    String id,
    String displayName
) {}

public record OrderItemResponse(
    String sku,
    int quantity,
    BigDecimal unitPrice
) {}
~~~

Ở đây, tên thành phần Java là id nhưng tên trường JSON được công bố là orderId nhờ @JsonProperty. Điều đó cho thấy tên thuộc tính Java và tên trường trong hợp đồng không bắt buộc phải giống nhau.

Record phù hợp với nhiều DTO vì các thành phần của record được khai báo rõ ràng và dữ liệu thường được tạo một lần rồi sử dụng. Class thông thường vẫn phù hợp khi cần constructor, setter, trạng thái có thể thay đổi hoặc logic tạo đối tượng phức tạp hơn.

Enum cũng cần được xem là một phần của hợp đồng. Không nên để thứ tự khai báo enum trở thành mã trao đổi, vì việc chèn một giá trị mới có thể làm thay đổi ordinal. Hãy dùng giá trị chuỗi ổn định:

~~~java
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;

public enum OrderStatus {
    PENDING("pending"),
    PAID("paid"),
    CANCELLED("cancelled");

    private final String wireValue;

    OrderStatus(String wireValue) {
        this.wireValue = wireValue;
    }

    @JsonValue
    public String wireValue() {
        return wireValue;
    }

    @JsonCreator
    public static OrderStatus fromWireValue(String value) {
        for (OrderStatus status : values()) {
            if (status.wireValue.equals(value)) {
                return status;
            }
        }
        throw new IllegalArgumentException("Unsupported order status: " + value);
    }
}
~~~

@JsonValue xác định giá trị được ghi ra JSON. @JsonCreator xác định cách Jackson tạo enum từ giá trị nhận vào. Cách này tách tên hằng số trong code khỏi mã ổn định mà hệ thống bên ngoài nhìn thấy.

## 4. Jackson chuyển đổi giữa kiểu Java và JSON

Trong Jackson Databind, ObjectMapper là điểm vào phổ biến cho hai chiều chuyển đổi:

- **Serialize**: nhận object Java và tạo JSON.
- **Deserialize**: đọc JSON và tạo object Java.

Với dữ liệu ngày giờ, cần đăng ký module hỗ trợ kiểu thời gian Java và thống nhất định dạng. Ví dụ cấu hình:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

ObjectMapper mapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
    .build();
~~~

Khi đó có thể chuyển đổi một DTO:

~~~java
String json = mapper.writeValueAsString(orderResponse);

OrderResponse restored =
    mapper.readValue(json, OrderResponse.class);
~~~

Trong ví dụ trên, createdAt có kiểu Instant. Cấu hình tắt WRITE_DATES_AS_TIMESTAMPS hướng Jackson đến cách ghi thời gian dưới dạng chuỗi thay vì timestamp dạng số. Hợp đồng vẫn cần xác định rõ chuỗi đó phải có múi giờ hoặc offset ra sao.

Với kiểu generic, chỉ truyền List.class là chưa đủ để giữ thông tin kiểu phần tử do Java type erasure. Hãy cung cấp đầy đủ kiểu đích bằng TypeReference:

~~~java
import com.fasterxml.jackson.core.type.TypeReference;

List<OrderResponse> orders = mapper.readValue(
    jsonArray,
    new TypeReference<List<OrderResponse>>() {}
);
~~~

Nếu cấu trúc JSON chưa biết trước hoặc cần kiểm tra từng trường trước khi ánh xạ sang DTO, có thể đọc thành cây JsonNode:

~~~java
import com.fasterxml.jackson.databind.JsonNode;

JsonNode root = mapper.readTree(json);
String orderId = root.path("orderId").asText();
JsonNode items = root.path("items");
~~~

JsonNode hữu ích khi xử lý dữ liệu linh hoạt, cấu trúc thay đổi hoặc cần kiểm tra thông điệp theo từng bước. Với hợp đồng ổn định, DTO có kiểu rõ ràng thường giúp phát hiện lỗi sớm hơn và làm code dễ hiểu hơn.

ObjectMapper nên được cấu hình tập trung trước khi dùng. Không nên tạo nhiều mapper với các quy tắc ngày giờ, enum, tên trường hoặc xử lý null khác nhau trong cùng một ứng dụng nếu chúng đang phục vụ cùng một hợp đồng.

## 5. Kiểu Java nội bộ không nhất thiết là kiểu trao đổi

Một entity trong tầng persistence có thể chứa:

- Khóa chính của cơ sở dữ liệu.
- Quan hệ hai chiều với entity khác.
- Trường phục vụ audit hoặc trạng thái nội bộ.
- Lazy proxy do ORM quản lý.
- Dữ liệu chỉ có ý nghĩa bên trong ứng dụng.

Nếu serialize entity trực tiếp, cấu trúc JSON có thể vô tình phụ thuộc vào cách lưu trữ. Quan hệ hai chiều còn có thể tạo vòng tham chiếu, dữ liệu thừa hoặc lỗi serialize.

DTO giúp tạo ranh giới rõ ràng:

~~~text
Entity / Domain Model
        |
        | ánh xạ có chủ đích
        v
Request DTO / Response DTO
        |
        | Jackson
        v
JSON theo hợp đồng
~~~

Ví dụ entity có trường internalNote và quan hệ customer đầy đủ, nhưng response chỉ công bố customerId và displayName. DTO quyết định chính xác dữ liệu nào được đưa ra ngoài.

Các annotation Jackson như @JsonProperty, @JsonIgnore, @JsonInclude và @JsonFormat có thể điều chỉnh cách một kiểu Java được biểu diễn. Tuy nhiên, annotation chỉ là cơ chế ánh xạ. Chúng không thay thế tài liệu hợp đồng, quy tắc nghiệp vụ hay kiểm tra dữ liệu.

## 6. Phân biệt trường bị thiếu, null và giá trị rỗng

Ba trạng thái sau không đồng nghĩa:

~~~json
{}
~~~

~~~json
{ "note": null }
~~~

~~~json
{ "note": "" }
~~~

- **Bị thiếu**: bên gửi không đưa trường note vào thông điệp.
- **null**: bên gửi đưa trường vào nhưng tuyên bố không có giá trị.
- **Chuỗi rỗng**: bên gửi đưa vào một giá trị chuỗi có độ dài bằng không.

Tương tự, các giá trị 0, false, mảng rỗng [] và object rỗng {} đều khác với việc không có trường.

Sự khác biệt này có ảnh hưởng trực tiếp đến cập nhật dữ liệu. Trong một API cập nhật từng phần, trường bị thiếu có thể mang nghĩa “giữ nguyên giá trị hiện tại”, trong khi null có thể mang nghĩa “xóa giá trị”. Nếu không quy định rõ, hai phía dễ hiểu khác nhau.

Khi deserialize, trường bị thiếu có thể nhận giá trị mặc định tùy kiểu Java, constructor và cấu hình Jackson. Kiểu tham chiếu thường có thể nhận null; kiểu nguyên thủy có giá trị mặc định như 0 hoặc false. Cấu hình như FAIL_ON_MISSING_CREATOR_PROPERTIES và FAIL_ON_NULL_FOR_PRIMITIVES có thể làm quá trình đọc thất bại trong các trường hợp tương ứng.

Khi serialize, @JsonInclude(NON_NULL) có thể yêu cầu bỏ qua trường có giá trị null. Cấu hình này chỉ ảnh hưởng cách ghi JSON; nó không tự chứng minh rằng trường đó là tùy chọn trong hợp đồng.

Có thể dùng @JsonSetter với Nulls.FAIL để từ chối null ở một thuộc tính cụ thể. Dù dùng annotation hay cấu hình mapper, cần phân biệt rõ ba việc:

1. Jackson có đọc và tạo được object hay không.
2. Dữ liệu có thỏa điều kiện của hợp đồng hay không.
3. Dữ liệu có thỏa quy tắc nghiệp vụ hay không.

Ví dụ @NotNull, @NotBlank hoặc @Positive là các ràng buộc validation. Jackson không tự động thực thi toàn bộ các annotation validation chỉ vì đã tạo được DTO. Ứng dụng cần gọi cơ chế validation phù hợp, chẳng hạn Bean Validation thông qua @Valid trong một endpoint Spring.

## 7. Chọn kiểu Java theo ngữ nghĩa của dữ liệu

Một số lựa chọn kiểu có ảnh hưởng trực tiếp đến độ chính xác và khả năng tương thích:

### Số lượng và tiền

- Dùng int hoặc long cho số lượng có giới hạn phù hợp.
- Dùng Integer hoặc Long khi cần biểu diễn thêm trạng thái null.
- Dùng BigInteger cho số nguyên lớn vượt phạm vi long.
- Dùng BigDecimal cho tiền hoặc số thập phân cần kiểm soát độ chính xác.
- Chỉ dùng double khi sai số dấu phẩy động được chấp nhận trong miền nghiệp vụ.

Đừng dùng String cho mọi con số chỉ để tránh lỗi parse. Làm vậy khiến phía nhận phải tự chuyển đổi, tự kiểm tra phạm vi và tự thống nhất cách tính.

Nếu đơn giá được truyền dưới dạng JSON number, hợp đồng cần xác định đơn vị tiền tệ, số chữ số thập phân và quy tắc làm tròn. Nếu có nhiều loại tiền, chỉ có amount là chưa đủ; cần thêm currency hoặc một cấu trúc tiền tệ có ý nghĩa rõ ràng.

### Ngày và thời gian

Các kiểu thời gian biểu diễn những khái niệm khác nhau:

- LocalDate: một ngày lịch, không có thời điểm trong ngày và múi giờ.
- LocalTime: giờ trong ngày, không có ngày và múi giờ.
- LocalDateTime: ngày và giờ địa phương, không tự xác định được một thời điểm tuyệt đối.
- OffsetDateTime: ngày giờ kèm offset UTC.
- Instant: một thời điểm trên dòng thời gian UTC.

Nếu trường createdAt biểu diễn thời điểm một sự kiện đã xảy ra, Instant thường phù hợp. Nếu trường birthday biểu diễn ngày sinh, LocalDate phù hợp hơn. Dùng LocalDateTime cho thời điểm toàn cầu mà không có quy ước múi giờ sẽ tạo ra sự mơ hồ.

### Collection và Map

List phù hợp khi thứ tự phần tử có ý nghĩa. Set phù hợp khi phần tử phải duy nhất theo quy tắc equality của Java. Map phù hợp khi dữ liệu được tra cứu theo khóa, nhưng JSON object chỉ có tên trường dạng chuỗi.

Nếu thứ tự của mảng là một phần hợp đồng, không nên ánh xạ tùy tiện sang một collection không bảo đảm thứ tự. Nếu cần giữ cả thứ tự và tính duy nhất, hãy định nghĩa rõ cách kiểm tra trùng lặp thay vì dựa vào hành vi ngầm của Set.

### Enum và giá trị phân loại

Giá trị enum trao đổi nên là mã ổn định, có ý nghĩa và được tài liệu hóa. Tránh dùng ordinal hoặc tên hằng số Java làm hợp đồng vô tình. Cần quyết định ứng dụng sẽ từ chối hay chấp nhận một giá trị enum mới mà phiên bản hiện tại chưa biết.

## 8. Hợp đồng trao đổi quyết định khả năng tương thích

Một hợp đồng thường bao gồm ít nhất các nội dung sau:

| Nội dung | Câu hỏi cần thống nhất |
|---|---|
| Tên trường | JSON dùng orderId hay id? Có phân biệt chữ hoa chữ thường không? |
| Kiểu và cấu trúc | Trường là string, number, object hay array? Object lồng nhau có hình dạng nào? |
| Bắt buộc | Trường có luôn phải xuất hiện không? |
| Nullability | Trường có được nhận null không? |
| Miền giá trị | Số lượng có phải dương? Chuỗi có giới hạn độ dài? |
| Định dạng | Thời gian dùng ISO-8601 hay định dạng khác? Mã tiền tệ theo quy ước nào? |
| Giá trị phân loại | Enum có những mã nào? Có thể xuất hiện mã mới không? |
| Lỗi | Trường sai kiểu, thiếu trường hoặc có giá trị không hợp lệ được phản hồi ra sao? |
| Phiên bản | Thay đổi nào tương thích ngược và thay đổi nào cần phiên bản hợp đồng mới? |

Khả năng tương thích phụ thuộc vào cả phía gửi và phía nhận:

- **Thêm trường tùy chọn** thường tương thích với consumer bỏ qua trường chưa biết. Điều này chỉ đúng nếu consumer được cấu hình để chấp nhận trường lạ.
- **Thêm trường bắt buộc** có thể làm hỏng producer cũ vì producer chưa gửi trường đó.
- **Đổi tên hoặc xóa trường** có thể làm hỏng consumer đang đọc tên cũ.
- **Đổi kiểu** từ number sang string hoặc từ object sang array thường là thay đổi không tương thích.
- **Thêm giá trị enum** có thể làm consumer cũ thất bại nếu consumer từ chối mọi giá trị chưa biết.
- **Đổi ý nghĩa của một trường mà vẫn giữ nguyên tên và kiểu** vẫn là thay đổi hợp đồng, dù JSON trông không khác.

Jackson có thể được cấu hình để từ chối hoặc bỏ qua thuộc tính JSON chưa được ánh xạ. Tùy chọn FAIL_ON_UNKNOWN_PROPERTIES kiểm soát một phần hành vi đó. Cần chọn chính sách có chủ đích: consumer cần nghiêm ngặt để phát hiện sai hợp đồng có thể từ chối trường lạ; consumer cần khả năng tiến hóa độc lập có thể bỏ qua trường mới. Không có một lựa chọn đúng cho mọi hệ thống.

## 9. Deserialization không đồng nghĩa với validation

Giả sử JSON sau có thể được ánh xạ thành DTO vì các trường đều có kiểu phù hợp:

~~~json
{
  "orderId": "ORD-2026-001",
  "items": [
    {
      "sku": "BOOK-01",
      "quantity": -2,
      "unitPrice": -100.00
    }
  ]
}
~~~

Jackson có thể đọc quantity thành int và unitPrice thành BigDecimal. Điều đó chỉ chứng minh dữ liệu có thể được chuyển thành kiểu Java tương ứng. Nó không chứng minh đơn hàng hợp lệ.

Một luồng xử lý thường có các bước:

1. Đọc JSON và kiểm tra cú pháp.
2. Deserialize sang request DTO.
3. Kiểm tra ràng buộc cấu trúc và dữ liệu, ví dụ trường bắt buộc, độ dài, số lượng dương.
4. Thực hiện quy tắc nghiệp vụ, ví dụ SKU có được phép bán hay trạng thái đơn hàng có cho phép cập nhật không.
5. Chuyển DTO thành mô hình nghiệp vụ và thực hiện thao tác.
6. Chuyển kết quả thành response DTO rồi serialize theo hợp đồng đầu ra.

Mỗi bước có trách nhiệm riêng. Không nên xem việc ObjectMapper không ném exception là bằng chứng duy nhất cho tính hợp lệ của request.

## 10. Kiểm tra hợp đồng ở cả hai chiều

Kiểm tra serialize giúp bảo đảm Java object được phát ra với đúng tên trường, kiểu, định dạng và giá trị mà consumer mong đợi. Kiểm tra deserialize giúp bảo đảm JSON hợp lệ theo hợp đồng có thể được đọc thành kiểu Java dự kiến.

Một bộ kiểm tra hợp đồng có thể bao gồm:

- Kiểm tra tên trường JSON, đặc biệt khi Java property khác tên wire.
- Kiểm tra kiểu và cấu trúc của object lồng nhau, mảng và giá trị đơn.
- Kiểm tra enum được ghi ra bằng mã ổn định.
- Kiểm tra thời gian có đúng định dạng và offset đã thống nhất.
- Kiểm tra BigDecimal không bị chuyển qua kiểu dấu phẩy động gây sai số.
- Kiểm tra cách xử lý trường bị thiếu, null và trường chưa biết.
- Dùng các JSON mẫu đã được hai phía thống nhất làm fixture để phát hiện thay đổi ngoài ý muốn.

Không nhất thiết phải so sánh chuỗi JSON theo từng ký tự. Thứ tự thuộc tính trong JSON object thường không mang ý nghĩa hợp đồng; có thể parse JSON rồi so sánh cây dữ liệu hoặc kiểm tra riêng từng thuộc tính. Ngược lại, thứ tự phần tử trong JSON array thường có ý nghĩa và cần được kiểm tra nếu hợp đồng yêu cầu.

Round-trip test — serialize rồi deserialize lại — hữu ích để phát hiện một số lỗi ánh xạ, nhưng không đủ để chứng minh hợp đồng tương thích. Hai phiên bản code có thể round-trip tốt với nhau trong khi JSON phát ra vẫn sai tên trường hoặc sai ý nghĩa so với hệ thống bên ngoài. Vì vậy cần có fixture hoặc kiểm tra độc lập với chính DTO hiện tại.

## 11. Cách suy nghĩ khi thiết kế một trường trao đổi

Khi thêm một trường mới, hãy đi theo trình tự:

1. Xác định ý nghĩa nghiệp vụ của trường. Nó đại diện cho mã định danh, số lượng, tiền, ngày lịch hay thời điểm?
2. Xác định cách biểu diễn trên JSON. Dùng string, number, boolean, object, array hay null?
3. Xác định kiểu Java thể hiện đúng ý nghĩa đó. Cân nhắc precision, nullability, collection và khả năng mở rộng.
4. Xác định tên wire, tính bắt buộc, định dạng và miền giá trị trong hợp đồng.
5. Cấu hình Jackson khi kiểu Java cần quy tắc chuyển đổi riêng.
6. Bổ sung validation cho các ràng buộc không thể được bảo đảm chỉ bằng kiểu dữ liệu.
7. Kiểm tra JSON thực tế ở cả chiều serialize và deserialize, bao gồm trường hợp thiếu, null và giá trị chưa biết.

Ví dụ, nếu trường eventTime là thời điểm một sự kiện xảy ra, thiết kế tốt sẽ thống nhất đây là một thời điểm tuyệt đối, dùng Instant ở Java, dùng chuỗi ISO-8601 có UTC hoặc offset trên JSON, cấu hình JavaTimeModule và kiểm tra dữ liệu mẫu. Chỉ khai báo eventTime là String có thể giúp đọc JSON, nhưng không bảo đảm mọi producer gửi cùng một định dạng hoặc cùng ý nghĩa.

## Kết luận

Cấu trúc dữ liệu cho biết thông điệp được tổ chức như thế nào. Kiểu Java cho biết ứng dụng biểu diễn và thao tác với dữ liệu ra sao. Hợp đồng trao đổi xác định hai phía phải hiểu thống nhất điều gì về dữ liệu đó.

Jackson thực hiện việc ánh xạ giữa Java và JSON dựa trên kiểu, annotation và cấu hình. Thiết kế tốt bắt đầu từ ý nghĩa của dữ liệu và hợp đồng, sau đó mới chọn kiểu Java và cấu hình Jackson. Khi ba lớp này nhất quán, dữ liệu dễ đọc, dễ kiểm tra và có thể tiến hóa giữa các phiên bản ứng dụng mà ít gây lỗi tích hợp hơn.


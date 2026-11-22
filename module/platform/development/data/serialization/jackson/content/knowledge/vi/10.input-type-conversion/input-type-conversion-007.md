# Cấu hình chuyển kiểu theo nhóm kiểu và kiểu cụ thể

Khi đọc JSON, Jackson thường phải chuyển giá trị đầu vào sang kiểu Java mà thuộc tính yêu cầu. Một trường JSON có thể là số nhưng thuộc tính Java là String; một chuỗi có thể chứa chữ số nhưng thuộc tính đích là Integer; một mảng rỗng có thể được đưa vào thuộc tính collection hoặc một chuỗi rỗng có thể được dùng cho một kiểu đối tượng. Những trường hợp này được gọi chung là coercion (chuyển đổi hoặc ép kiểu dữ liệu đầu vào).

Jackson có các quy tắc mặc định để xử lý nhiều dạng đầu vào. Tuy nhiên, quy tắc mặc định không phải lúc nào cũng phù hợp với hợp đồng API hoặc yêu cầu nghiệp vụ. Có API chấp nhận chuỗi số, có API yêu cầu số phải được gửi dưới dạng JSON number; có trường hợp chuỗi rỗng được xem là null, nhưng ở trường khác chuỗi rỗng phải bị từ chối.

Từ Jackson Databind 2.12, cơ chế CoercionConfig cho phép đặt chính sách theo **nhóm kiểu logic** hoặc theo **lớp Java cụ thể**. Nhờ đó, ứng dụng có thể kiểm soát chính xác dạng đầu vào nào được chuyển đổi, bị từ chối, trở thành null hoặc trở thành giá trị rỗng.

## 1. Coercion là gì?

Coercion xảy ra khi hình dạng hoặc kiểu token JSON không trùng trực tiếp với kiểu Java đích, nhưng Jackson được phép chuyển đổi theo một quy tắc nào đó.

Ví dụ JSON:

~~~json
{
  "quantity": "12",
  "price": 19.5,
  "active": "true"
}
~~~

Mô hình Java:

~~~java
public class ProductRequest {
    private Integer quantity;
    private BigDecimal price;
    private Boolean active;

    // Getter và setter
}
~~~

Trong ví dụ này:

- quantity nhận một JSON string có nội dung số, trong khi kiểu Java là Integer.
- price nhận JSON number có phần thập phân, trong khi kiểu Java là BigDecimal.
- active nhận một JSON string có nội dung boolean, trong khi kiểu Java là Boolean.

Jackson có thể hỗ trợ một số chuyển đổi scalar như vậy. Nếu ứng dụng muốn API chỉ nhận đúng kiểu JSON tương ứng, có thể cấu hình để từ chối các dạng đầu vào không mong muốn.

Coercion cần được phân biệt với việc chuyển đổi giữa hai kiểu Java trong mã ứng dụng. Cấu hình coercion của Jackson điều khiển cách deserializer diễn giải token JSON khi tạo giá trị Java.

## 2. Hai cấp cấu hình: nhóm kiểu logic và lớp Java cụ thể

Jackson tổ chức các kiểu đích thành những nhóm logic. Ví dụ, các kiểu số nguyên thuộc nhóm Integer, các kiểu số thực thuộc nhóm Float, chuỗi thuộc nhóm Textual và các lớp bean thông thường thuộc nhóm POJO.

Có thể cấu hình theo hai phạm vi:

| Phạm vi | API | Tác dụng |
|---|---|---|
| Mặc định chung | coercionConfigDefaults() | Quy tắc fallback cho các kiểu khi không có cấu hình cụ thể hơn |
| Nhóm kiểu logic | coercionConfigFor(LogicalType.Integer) | Áp dụng cho các kiểu đích thuộc cùng nhóm logic |
| Lớp Java cụ thể | coercionConfigFor(BigDecimal.class) | Điều chỉnh riêng cho một kiểu Java xác định |

Nhóm kiểu logic giúp đặt chính sách chung. Cấu hình theo lớp cụ thể dùng để tạo ngoại lệ cho một kiểu trong nhóm.

Ví dụ, ứng dụng có thể cho phép các kiểu số thực nhận chuỗi số, nhưng riêng BigDecimal phải nhận JSON number để tránh dữ liệu tiền tệ được gửi nhầm dưới dạng chuỗi.

## 3. Các thành phần của CoercionConfig

API coercion sử dụng ba khái niệm chính:

- **LogicalType:** nhóm kiểu Java đích.
- **CoercionInputShape:** hình dạng token JSON đầu vào.
- **CoercionAction:** hành động Jackson thực hiện khi gặp hình dạng đầu vào đó.

Các lớp và enum thường dùng:

~~~java
import com.fasterxml.jackson.databind.cfg.CoercionAction;
import com.fasterxml.jackson.databind.cfg.CoercionInputShape;
import com.fasterxml.jackson.databind.type.LogicalType;
~~~

### LogicalType

Một số nhóm kiểu logic thường gặp:

| LogicalType | Kiểu Java hoặc nhóm dữ liệu tiêu biểu |
|---|---|
| Integer | byte, short, int, long, các wrapper số nguyên, BigInteger |
| Float | float, double, Float, Double, BigDecimal |
| Boolean | boolean và Boolean |
| Textual | String và các kiểu văn bản |
| Enum | Các kiểu enum |
| DateTime | Các kiểu ngày giờ có deserializer tương ứng |
| POJO | Các bean hoặc đối tượng Java thông thường |
| Array | Kiểu mảng Java |
| Collection | List, Set và các collection khác |
| Map | Map và các kiểu ánh xạ key/value |
| Binary | Dữ liệu nhị phân |
| OtherScalar | Một số kiểu scalar không thuộc các nhóm chuyên biệt phía trên |

LogicalType mô tả nhóm của kiểu đích, không phải loại token JSON đang đọc. Ví dụ, nếu thuộc tính Java là Integer nhưng JSON gửi chuỗi "12", kiểu đích vẫn thuộc LogicalType.Integer còn hình dạng đầu vào là CoercionInputShape.String.

### CoercionInputShape

CoercionInputShape mô tả hình dạng dữ liệu Jackson nhận được:

| Input shape | Ý nghĩa |
|---|---|
| Array | JSON array |
| Object | JSON object |
| Integer | JSON number không có phần thập phân |
| Float | JSON number có phần thập phân hoặc dạng số thực |
| Boolean | JSON true hoặc false |
| String | JSON string thông thường |
| Binary | Dữ liệu nhị phân |
| EmptyArray | JSON array rỗng |
| EmptyObject | JSON object rỗng |
| EmptyString | JSON string rỗng |

EmptyString, EmptyArray và EmptyObject là các trường hợp riêng. Không nên xem chúng luôn tương đương với String, Array hoặc Object thông thường.

### CoercionAction

CoercionAction quy định Jackson xử lý đầu vào như thế nào:

| Action | Hành vi |
|---|---|
| TryConvert | Thử chuyển đổi theo quy tắc deserializer thông thường |
| Fail | Từ chối đầu vào và phát sinh lỗi ánh xạ |
| AsNull | Xem giá trị đầu vào như null |
| AsEmpty | Yêu cầu deserializer cung cấp giá trị rỗng của kiểu đích |

AsEmpty không có nghĩa mọi kiểu đều nhận cùng một giá trị. Giá trị rỗng phụ thuộc kiểu đích và deserializer. Ví dụ, kiểu collection có thể trả về collection rỗng, kiểu văn bản có thể trả về chuỗi rỗng; kiểu khác có thể có hành vi riêng hoặc không có empty value phù hợp.

TryConvert cũng không bảo đảm mọi dữ liệu đều chuyển đổi thành công. Nó cho phép Jackson thử quy tắc chuyển đổi bình thường; nếu nội dung không hợp lệ hoặc kiểu đích không hỗ trợ chuyển đổi đó, thao tác đọc vẫn có thể thất bại.

## 4. Cấu hình theo nhóm kiểu logic

Để áp dụng một chính sách cho cả nhóm kiểu, dùng ObjectMapper.coercionConfigFor(LogicalType):

~~~java
ObjectMapper mapper = JsonMapper.builder().build();

mapper.coercionConfigFor(LogicalType.Integer)
    .setCoercion(
        CoercionInputShape.String,
        CoercionAction.Fail
    );
~~~

Thiết lập này yêu cầu Jackson từ chối JSON string khi đích là một kiểu thuộc nhóm Integer. Ví dụ, thuộc tính Integer không còn nhận chuỗi "12" theo coercion scalar thông thường.

~~~json
{
  "quantity": "12"
}
~~~

Nếu quantity có kiểu Integer, thao tác đọc sẽ báo lỗi thay vì chuyển chuỗi thành số. Đầu vào đúng kiểu vẫn được chấp nhận:

~~~json
{
  "quantity": 12
}
~~~

Vì chính sách được đặt theo LogicalType.Integer, nó có thể ảnh hưởng đến nhiều kiểu số nguyên như Integer, Long, Short, Byte hoặc BigInteger. Đây là cách hữu ích khi hợp đồng API quy định mọi giá trị nguyên phải được gửi dưới dạng JSON number.

### Ví dụ chính sách theo từng nhóm

Có thể cấu hình nhiều nhóm độc lập:

~~~java
ObjectMapper mapper = JsonMapper.builder().build();

// Không nhận chuỗi cho các kiểu số nguyên.
mapper.coercionConfigFor(LogicalType.Integer)
    .setCoercion(
        CoercionInputShape.String,
        CoercionAction.Fail
    );

// Không nhận số thực cho các kiểu số nguyên.
mapper.coercionConfigFor(LogicalType.Integer)
    .setCoercion(
        CoercionInputShape.Float,
        CoercionAction.Fail
    );

// Cho phép thử chuyển chuỗi sang kiểu số thực.
mapper.coercionConfigFor(LogicalType.Float)
    .setCoercion(
        CoercionInputShape.String,
        CoercionAction.TryConvert
    );

// Không chuyển chuỗi tùy ý thành Boolean.
mapper.coercionConfigFor(LogicalType.Boolean)
    .setCoercion(
        CoercionInputShape.String,
        CoercionAction.Fail
    );
~~~

Sau cấu hình:

| Kiểu đích | JSON đầu vào | Chính sách |
|---|---|---|
| Integer | 12 | Kiểu JSON phù hợp, đọc bình thường |
| Integer | "12" | Fail |
| Integer | 12.5 | Fail |
| Double | "12.5" | TryConvert |
| Boolean | "true" | Fail |
| Boolean | true | Kiểu JSON phù hợp, đọc bình thường |

Các quy tắc trên chỉ mô tả những coercion đã cấu hình. Những kiểu đầu vào vốn phù hợp với deserializer vẫn được xử lý theo quy tắc thông thường.

## 5. Cấu hình riêng cho một lớp Java cụ thể

Khi một kiểu cần chính sách khác với các kiểu cùng nhóm, dùng overload nhận Class:

~~~java
mapper.coercionConfigFor(BigDecimal.class)
    .setCoercion(
        CoercionInputShape.String,
        CoercionAction.Fail
    );
~~~

Giả sử mapper đã cho phép nhóm Float nhận chuỗi số:

~~~java
mapper.coercionConfigFor(LogicalType.Float)
    .setCoercion(
        CoercionInputShape.String,
        CoercionAction.TryConvert
    );

// Riêng BigDecimal không nhận chuỗi.
mapper.coercionConfigFor(BigDecimal.class)
    .setCoercion(
        CoercionInputShape.String,
        CoercionAction.Fail
    );
~~~

Khi đó, các kiểu số thực khác có thể tiếp tục dùng chính sách nhóm, còn BigDecimal có quy tắc riêng. Cách này hữu ích khi cùng một nhóm kiểu có những yêu cầu nghiệp vụ khác nhau.

Ví dụ DTO:

~~~java
public class Invoice {
    private Double exchangeRate;
    private BigDecimal totalAmount;

    public Double getExchangeRate() {
        return exchangeRate;
    }

    public void setExchangeRate(Double exchangeRate) {
        this.exchangeRate = exchangeRate;
    }

    public BigDecimal getTotalAmount() {
        return totalAmount;
    }

    public void setTotalAmount(BigDecimal totalAmount) {
        this.totalAmount = totalAmount;
    }
}
~~~

Với cấu hình minh họa phía trên, JSON sau có thể được đọc nếu exchangeRate nhận chuỗi số, nhưng totalAmount phải là JSON number:

~~~json
{
  "exchangeRate": "1.25",
  "totalAmount": 250000.00
}
~~~

Nếu totalAmount được gửi thành chuỗi "250000.00", cấu hình riêng cho BigDecimal yêu cầu Jackson từ chối.

## 6. Thứ tự áp dụng cấu hình

Jackson tìm chính sách coercion theo mức độ cụ thể. Về nguyên tắc, cấu hình cho lớp đích cụ thể được xét trước, sau đó đến nhóm LogicalType, rồi đến cấu hình mặc định chung.

~~~text
Kiểu Java đích
      │
      ▼
Cấu hình theo Class cụ thể
      │  nếu không có action phù hợp
      ▼
Cấu hình theo LogicalType
      │  nếu không có action phù hợp
      ▼
Cấu hình coercion mặc định
      │  nếu vẫn chưa có action
      ▼
Quy tắc mặc định/fallback của Jackson
~~~

Điểm quan trọng là một cấu hình cụ thể chỉ thay thế chính sách ở đúng input shape mà nó khai báo. Nếu lớp cụ thể không có action cho một input shape, Jackson có thể tiếp tục tìm chính sách ở nhóm logic hoặc mặc định.

Ví dụ:

~~~java
mapper.coercionConfigFor(LogicalType.Float)
    .setCoercion(
        CoercionInputShape.String,
        CoercionAction.TryConvert
    );

mapper.coercionConfigFor(BigDecimal.class)
    .setCoercion(
        CoercionInputShape.String,
        CoercionAction.Fail
    );
~~~

Với BigDecimal và JSON string, cấu hình theo lớp cụ thể được ưu tiên. Với Double và JSON string, không có override riêng nên chính sách của nhóm Float được dùng.

Khi thiết kế cấu hình, nên đặt chính sách phổ biến ở nhóm logic và chỉ thêm override ở lớp cụ thể khi có lý do nghiệp vụ rõ ràng. Điều này giúp tránh một danh sách cấu hình ngoại lệ khó theo dõi.

## 7. Cấu hình mặc định chung

ObjectMapper cung cấp coercionConfigDefaults() để đặt hành vi fallback cho những kiểu chưa có cấu hình cụ thể hơn:

~~~java
ObjectMapper mapper = JsonMapper.builder().build();

mapper.coercionConfigDefaults()
    .setCoercion(
        CoercionInputShape.EmptyString,
        CoercionAction.AsNull
    );
~~~

Ví dụ này yêu cầu xem chuỗi rỗng như null ở mức mặc định chung, nếu không có cấu hình theo nhóm hoặc lớp cụ thể ghi đè cho trường hợp đó.

Có thể dùng mặc định để thống nhất một chính sách rộng, sau đó giới hạn các nhóm:

~~~java
mapper.coercionConfigDefaults()
    .setCoercion(
        CoercionInputShape.EmptyString,
        CoercionAction.AsNull
    );

mapper.coercionConfigFor(LogicalType.Textual)
    .setCoercion(
        CoercionInputShape.EmptyString,
        CoercionAction.AsEmpty
    );

mapper.coercionConfigFor(LogicalType.Integer)
    .setCoercion(
        CoercionInputShape.EmptyString,
        CoercionAction.Fail
    );
~~~

Trong ví dụ, chuỗi rỗng có chính sách khác nhau tùy kiểu đích:

- Với nhóm Textual, có thể chuyển thành giá trị rỗng của kiểu văn bản.
- Với nhóm Integer, bị từ chối.
- Với kiểu không có cấu hình riêng, mặc định là AsNull.

Kết quả cụ thể của AsNull và AsEmpty vẫn phụ thuộc deserializer và kiểu đích. Đặc biệt, nếu kết quả null được gán vào thuộc tính kiểu nguyên thủy, các feature xử lý null cho primitive có thể tiếp tục ảnh hưởng đến kết quả.

## 8. Phân biệt String, EmptyString và chuỗi chỉ chứa khoảng trắng

CoercionInputShape.String và CoercionInputShape.EmptyString cho phép tách chuỗi thông thường khỏi chuỗi rỗng.

Ví dụ:

~~~json
{
  "quantity": "",
  "description": "Keyboard"
}
~~~

Có thể cấu hình riêng:

~~~java
mapper.coercionConfigFor(LogicalType.Integer)
    .setCoercion(
        CoercionInputShape.EmptyString,
        CoercionAction.AsNull
    );

mapper.coercionConfigFor(LogicalType.Integer)
    .setCoercion(
        CoercionInputShape.String,
        CoercionAction.Fail
    );
~~~

Với kiểu Integer, chuỗi rỗng có thể trở thành null, còn chuỗi không rỗng như "12" bị từ chối. Đây là hai quy tắc riêng.

Chuỗi chỉ chứa khoảng trắng như "   " không nhất thiết được xem giống hệt chuỗi rỗng trong mọi cấu hình và phiên bản. Jackson có cơ chế xử lý blank-as-empty trong cấu hình coercion. Khi hợp đồng cần phân biệt hoặc chuẩn hóa khoảng trắng, nên kiểm tra rõ hành vi của phiên bản đang dùng và cân nhắc chuẩn hóa đầu vào ở tầng riêng.

Không nên giả định mọi giá trị String đều được trim tự động trước khi coercion. Nếu nghiệp vụ yêu cầu bỏ khoảng trắng, hãy quy định rõ trong deserializer, setter, creator hoặc tầng validation.

## 9. Điều khiển chuỗi rỗng cho POJO và collection

Một tình huống thường gặp là API gửi chuỗi rỗng cho trường vốn là object:

~~~json
{
  "address": ""
}
~~~

Nếu address có kiểu Address, Jackson có thể từ chối vì một chuỗi không phải object JSON. Nếu hợp đồng muốn xem chuỗi rỗng như null, có thể cấu hình nhóm POJO:

~~~java
mapper.coercionConfigFor(LogicalType.POJO)
    .setCoercion(
        CoercionInputShape.EmptyString,
        CoercionAction.AsNull
    );
~~~

Tương tự, có thể đặt chính sách cho collection:

~~~java
mapper.coercionConfigFor(LogicalType.Collection)
    .setCoercion(
        CoercionInputShape.EmptyArray,
        CoercionAction.AsEmpty
    );
~~~

Tuy nhiên, JSON array rỗng vốn đã là hình dạng hợp lệ cho collection; việc cấu hình EmptyArray có ý nghĩa khi muốn xác định rõ hành vi coercion cho kiểu đích hoặc muốn ghi đè mặc định. Với chuỗi rỗng, cần quyết định riêng vì chuỗi không phải array.

Nếu API gửi:

~~~json
{
  "items": ""
}
~~~

và items có kiểu List<Item>, chính sách cho LogicalType.Collection và EmptyString có thể được cân nhắc. Chỉ nên cho phép chuyển thành null hoặc collection rỗng khi hợp đồng dữ liệu xác định ý nghĩa đó.

## 10. Chuyển đổi giữa số nguyên và số thực

Một trường hợp quan trọng là JSON number có phần thập phân được đọc vào kiểu số nguyên:

~~~json
{
  "quantity": 12.7
}
~~~

Nếu thuộc tính Java là Integer, Jackson có thể có quy tắc chuyển đổi số thực sang số nguyên. Để từ chối đầu vào này cho toàn bộ nhóm Integer:

~~~java
mapper.coercionConfigFor(LogicalType.Integer)
    .setCoercion(
        CoercionInputShape.Float,
        CoercionAction.Fail
    );
~~~

Chính sách này hữu ích khi dữ liệu số lượng, số lần hoặc mã định lượng phải là số nguyên đúng nghĩa. Nó ngăn ứng dụng âm thầm nhận một số thập phân cho thuộc tính nguyên.

Nếu chỉ một kiểu cần nghiêm ngặt hơn, có thể dùng cấu hình theo lớp:

~~~java
mapper.coercionConfigFor(Integer.class)
    .setCoercion(
        CoercionInputShape.Float,
        CoercionAction.Fail
    );
~~~

Khi cần áp dụng cho cả primitive int và wrapper Integer, hãy kiểm tra kiểu thuộc tính thực tế và cấu hình tương ứng theo class nếu cần. Cấu hình theo LogicalType.Integer thường thích hợp hơn khi chính sách phải áp dụng cho toàn nhóm số nguyên.

## 11. Boolean và Enum

Boolean có thể gặp các đầu vào dạng string như "true", "false", "yes", "no" hoặc dạng số 0/1 tùy cấu hình và quy tắc chuyển đổi. Nếu API yêu cầu JSON boolean thực sự, có thể từ chối các scalar khác:

~~~java
mapper.coercionConfigFor(LogicalType.Boolean)
    .setCoercion(
        CoercionInputShape.String,
        CoercionAction.Fail
    );

mapper.coercionConfigFor(LogicalType.Boolean)
    .setCoercion(
        CoercionInputShape.Integer,
        CoercionAction.Fail
    );
~~~

JSON phù hợp:

~~~json
{
  "enabled": true
}
~~~

JSON không phù hợp với chính sách:

~~~json
{
  "enabled": "true"
}
~~~

Enum cũng có thể cần chính sách riêng khi nhận số hoặc chuỗi. Ví dụ, ứng dụng muốn chỉ chấp nhận tên enum, không chấp nhận ordinal:

~~~java
mapper.coercionConfigFor(LogicalType.Enum)
    .setCoercion(
        CoercionInputShape.Integer,
        CoercionAction.Fail
    );
~~~

Đầu vào chuỗi:

~~~json
{
  "status": "ACTIVE"
}
~~~

Đầu vào số:

~~~json
{
  "status": 1
}
~~~

Nếu chính sách yêu cầu tên enum, hãy từ chối số để tránh phụ thuộc vào thứ tự khai báo enum. Việc ánh xạ chuỗi không hợp lệ sang enum vẫn chịu các quy tắc enum deserializer và feature liên quan.

## 12. Coercion theo lớp cụ thể với kiểu nghiệp vụ

Không phải mọi kiểu Java đều được nhóm thành Integer, Float hoặc Textual. Một lớp value object riêng có thể cần quy tắc coercion đặc biệt.

Ví dụ:

~~~java
public class OrderNumber {
    private final String value;

    @JsonCreator(mode = JsonCreator.Mode.DELEGATING)
    public OrderNumber(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Order number is required");
        }
        this.value = value;
    }

    @JsonValue
    public String getValue() {
        return value;
    }
}
~~~

Có thể đặt quy tắc riêng cho OrderNumber:

~~~java
mapper.coercionConfigFor(OrderNumber.class)
    .setCoercion(
        CoercionInputShape.Integer,
        CoercionAction.Fail
    );
~~~

Nếu hợp đồng yêu cầu mã đơn hàng luôn là JSON string, cấu hình trên từ chối số nguyên trước khi Jackson thử chuyển thành kiểu String cho creator. Kiểu OrderNumber khác có thể có quy tắc riêng mà không ảnh hưởng toàn bộ LogicalType.Textual.

Với custom deserializer hoặc creator phức tạp, coercion có thể tương tác với logic chuyển đổi riêng. Cần hiểu thứ tự Jackson gọi deserializer và creator của kiểu đó; không nên coi CoercionConfig là cơ chế validation thay thế cho constructor hoặc custom deserializer.

## 13. CoercionConfig và các feature chuyển đổi cũ

Trước khi có CoercionConfig, Jackson đã cung cấp một số feature điều khiển chuyển đổi. Chúng vẫn có thể xuất hiện trong codebase:

| Feature | Phạm vi hoặc mục đích thường gặp |
|---|---|
| MapperFeature.ALLOW_COERCION_OF_SCALARS | Điều khiển việc cho phép một số coercion giữa scalar |
| DeserializationFeature.ACCEPT_FLOAT_AS_INT | Điều khiển việc nhận số thực cho kiểu nguyên |
| DeserializationFeature.ACCEPT_EMPTY_STRING_AS_NULL_OBJECT | Điều khiển một số trường hợp chuỗi rỗng được xem là null cho object |
| DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES | Điều khiển lỗi khi null được gán vào kiểu nguyên thủy |

CoercionConfig cung cấp khả năng cấu hình chi tiết theo input shape và kiểu đích. Thay vì chỉ bật hoặc tắt một hành vi rộng, ứng dụng có thể đặt action khác nhau cho từng nhóm kiểu hoặc một class cụ thể.

Ví dụ, ACCEPT_FLOAT_AS_INT là feature quen thuộc để kiểm soát float sang integer. Khi dùng CoercionConfig, có thể diễn tả rõ hơn:

~~~java
mapper.coercionConfigFor(LogicalType.Integer)
    .setCoercion(
        CoercionInputShape.Float,
        CoercionAction.Fail
    );
~~~

Trong dự án có cả feature cũ và CoercionConfig, cần đọc tài liệu đúng phiên bản Jackson để hiểu quan hệ giữa các thiết lập và mặc định fallback. Tránh cấu hình hai cơ chế theo các hướng mâu thuẫn rồi dựa vào suy đoán về thứ tự ưu tiên. Nên chọn một chính sách rõ ràng, tập trung và có kiểm tra bằng dữ liệu đại diện.

## 14. Cấu hình coercion trong lúc tạo ObjectMapper

CoercionConfig là một phần cấu hình của mapper. Có thể tạo mapper trước, sau đó thiết lập coercion trước khi sử dụng:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .build();

mapper.coercionConfigFor(LogicalType.Integer)
    .setCoercion(
        CoercionInputShape.String,
        CoercionAction.Fail
    );

mapper.coercionConfigFor(BigDecimal.class)
    .setCoercion(
        CoercionInputShape.String,
        CoercionAction.Fail
    );

// Chỉ bắt đầu chia sẻ và đọc/ghi sau khi hoàn tất cấu hình.
~~~

Có thể gom cấu hình vào một phương thức:

~~~java
public final class JacksonConfiguration {

    private JacksonConfiguration() {
    }

    public static ObjectMapper createMapper() {
        ObjectMapper mapper = JsonMapper.builder().build();

        mapper.coercionConfigFor(LogicalType.Integer)
            .setCoercion(
                CoercionInputShape.String,
                CoercionAction.Fail
            );

        mapper.coercionConfigFor(LogicalType.Integer)
            .setCoercion(
                CoercionInputShape.Float,
                CoercionAction.Fail
            );

        mapper.coercionConfigFor(LogicalType.Boolean)
            .setCoercion(
                CoercionInputShape.String,
                CoercionAction.Fail
            );

        return mapper;
    }
}
~~~

Sau khi mapper đã được công bố và dùng đồng thời, không nên tiếp tục thay đổi coercion config. Hãy hoàn tất cấu hình ở giai đoạn khởi tạo và tái sử dụng mapper đã cấu hình.

## 15. Tách chính sách bằng ObjectReader

Nếu hai luồng nhập dữ liệu có chính sách khác nhau, có thể dùng mapper riêng hoặc tạo các reader phù hợp với cấu hình. ObjectReader cho phép gắn các cấu hình đọc theo thao tác mà không thay đổi mapper gốc.

Ví dụ:

~~~java
ObjectMapper mapper = new ObjectMapper();

ObjectReader strictReader = mapper.readerFor(ProductRequest.class)
    .with(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

ObjectReader tolerantReader = mapper.readerFor(ProductRequest.class)
    .without(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
~~~

Đối với coercion, API reader có các cách cấu hình theo thao tác tùy phiên bản Jackson. Nếu cần thay đổi CoercionConfig cho một loại đích, cách dễ kiểm soát nhất là tạo mapper đã cấu hình riêng cho chính sách đó hoặc dùng API reader/configuration được phiên bản dự án hỗ trợ. Không nên bật tắt trực tiếp coercion trên mapper dùng chung giữa các request.

Một thiết kế thực tế có thể dùng:

- Mapper strict cho API công khai yêu cầu JSON đúng kiểu.
- Mapper compatibility cho nguồn dữ liệu cũ còn gửi chuỗi số.
- Các reader/writer bất biến để điều chỉnh feature theo thao tác khi không cần thay đổi coercion nền tảng.

Hai mapper có thể chia sẻ cùng module hoặc naming strategy nhưng phải hoàn tất cấu hình riêng trước khi được dùng.

## 16. Kiểm tra hành vi coercion

Khi cấu hình chuyển kiểu, nên kiểm tra cả trường hợp được chấp nhận và trường hợp bị từ chối. Ví dụ:

~~~java
public class QuantityRequest {
    private Integer quantity;

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }
}
~~~

Cấu hình từ chối chuỗi cho nhóm Integer:

~~~java
ObjectMapper mapper = JsonMapper.builder().build();

mapper.coercionConfigFor(LogicalType.Integer)
    .setCoercion(
        CoercionInputShape.String,
        CoercionAction.Fail
    );
~~~

JSON đúng:

~~~json
{"quantity": 12}
~~~

JSON sai theo chính sách:

~~~json
{"quantity": "12"}
~~~

Kiểm tra bằng JUnit:

~~~java
class QuantityRequestTest {

    private final ObjectMapper mapper = createMapper();

    private static ObjectMapper createMapper() {
        ObjectMapper mapper = JsonMapper.builder().build();
        mapper.coercionConfigFor(LogicalType.Integer)
            .setCoercion(
                CoercionInputShape.String,
                CoercionAction.Fail
            );
        return mapper;
    }

    @Test
    void acceptsIntegerToken() throws Exception {
        QuantityRequest request = mapper.readValue(
            "{\"quantity\":12}",
            QuantityRequest.class
        );

        assertEquals(12, request.getQuantity());
    }

    @Test
    void rejectsNumericString() {
        assertThrows(
            JsonProcessingException.class,
            () -> mapper.readValue(
                "{\"quantity\":\"12\"}",
                QuantityRequest.class
            )
        );
    }
}
~~~

Ngoài hai trường hợp trên, nên kiểm tra:

- JSON null.
- Chuỗi rỗng và chuỗi chỉ có khoảng trắng.
- Số thực cho thuộc tính nguyên.
- Mảng rỗng hoặc object rỗng.
- Các kiểu primitive và wrapper.
- Kiểu cụ thể có override so với chính sách nhóm.
- Dữ liệu hợp lệ nhưng nằm ngoài miền giá trị của kiểu đích.

Mục tiêu là xác nhận chính sách coercion có đúng phạm vi, không vô tình làm thay đổi các kiểu khác.

## 17. Cách đọc lỗi coercion

Khi action là Fail hoặc thao tác TryConvert không thành công, Jackson thường phát sinh lỗi databinding. Loại exception và thông điệp cụ thể phụ thuộc kiểu đích, token JSON và phiên bản Jackson.

Ví dụ, nếu quantity là Integer nhưng JSON truyền "many", Jackson không thể chuyển nội dung thành số nguyên. Nếu cấu hình action là Fail cho String, ngay cả chuỗi số hợp lệ "12" cũng bị từ chối theo chính sách.

Hai lỗi này có ý nghĩa khác nhau:

| Đầu vào | Chính sách | Ý nghĩa lỗi |
|---|---|---|
| "12" | Fail cho String | Hình dạng JSON không được hợp đồng cho phép |
| "many" | TryConvert | Hình dạng có thể thử chuyển, nhưng nội dung không chuyển được thành số |
| 12.5 | Fail cho Float | Không chấp nhận token số thực cho kiểu nguyên |
| null | Fail hoặc feature null phù hợp | Giá trị null không được phép cho thuộc tính đó |

Ở tầng ứng dụng, có thể bắt JsonProcessingException hoặc các exception databind cụ thể để chuyển thành phản hồi lỗi đầu vào. Tránh chỉ dựa vào nội dung message vì thông điệp có thể thay đổi theo phiên bản.

## 18. Lưu ý khi chọn AsNull và AsEmpty

AsNull và AsEmpty có vẻ tương tự nhưng biểu thị hai ý nghĩa khác nhau:

- AsNull coi đầu vào như null. Điều này phù hợp khi chuỗi rỗng có nghĩa là không cung cấp giá trị.
- AsEmpty yêu cầu deserializer tạo giá trị rỗng của kiểu đích. Điều này phù hợp khi ứng dụng muốn giữ đối tượng hoặc collection ở trạng thái rỗng.

Ví dụ với một thuộc tính collection:

~~~java
public class SearchRequest {
    private List<String> tags;

    public List<String> getTags() {
        return tags;
    }

    public void setTags(List<String> tags) {
        this.tags = tags;
    }
}
~~~

Nếu đầu vào được xử lý thành AsEmpty, deserializer collection có thể trả về collection rỗng. Nếu là AsNull, thuộc tính nhận null, trừ khi có quy tắc xử lý null khác.

Với kiểu primitive, AsNull không thể tạo một giá trị null Java thực sự. Hành vi cuối cùng còn phụ thuộc các feature như FAIL_ON_NULL_FOR_PRIMITIVES. Vì vậy, nếu cần biểu diễn trạng thái không có giá trị, wrapper type thường rõ ràng hơn primitive.

## 19. Phạm vi tác động và thiết kế chính sách

Khi thêm coercion config, hãy xác định chính xác kiểu đích và hình dạng đầu vào cần kiểm soát:

1. Nếu quy tắc đúng cho mọi kiểu số nguyên, cấu hình LogicalType.Integer.
2. Nếu chỉ một kiểu cụ thể cần ngoại lệ, cấu hình Class tương ứng.
3. Nếu quy tắc là fallback chung, dùng coercionConfigDefaults().
4. Nếu chỉ quan tâm chuỗi rỗng, dùng EmptyString thay vì áp dụng chung cho mọi String.
5. Nếu muốn từ chối số thực cho số nguyên, cấu hình input shape Float cho nhóm Integer hoặc lớp cụ thể.
6. Nếu muốn đầu vào được chuyển thành null hoặc giá trị rỗng, chọn AsNull hoặc AsEmpty và xác định rõ ý nghĩa nghiệp vụ.
7. Hoàn tất cấu hình trước khi mapper được chia sẻ và sử dụng.

Không nên bật coercion rộng chỉ để một API cũ hoạt động nếu điều đó làm các API khác nhận dữ liệu sai định dạng. Tách mapper theo miền tích hợp hoặc dùng chính sách cụ thể cho kiểu đích sẽ dễ kiểm soát hơn.

## 20. Ví dụ tổng hợp nhiều cấp cấu hình

Ví dụ sau minh họa mặc định chung, nhóm logic và kiểu cụ thể:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.cfg.CoercionAction;
import com.fasterxml.jackson.databind.cfg.CoercionInputShape;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.databind.type.LogicalType;

import java.math.BigDecimal;

public final class ApiMapperFactory {

    private ApiMapperFactory() {
    }

    public static ObjectMapper create() {
        ObjectMapper mapper = JsonMapper.builder().build();

        // Fallback: chuỗi rỗng được xem như null.
        mapper.coercionConfigDefaults()
            .setCoercion(
                CoercionInputShape.EmptyString,
                CoercionAction.AsNull
            );

        // Nhóm số nguyên không nhận chuỗi số.
        mapper.coercionConfigFor(LogicalType.Integer)
            .setCoercion(
                CoercionInputShape.String,
                CoercionAction.Fail
            );

        // Nhóm số nguyên không nhận số thực.
        mapper.coercionConfigFor(LogicalType.Integer)
            .setCoercion(
                CoercionInputShape.Float,
                CoercionAction.Fail
            );

        // Nhóm Boolean chỉ nhận token boolean.
        mapper.coercionConfigFor(LogicalType.Boolean)
            .setCoercion(
                CoercionInputShape.String,
                CoercionAction.Fail
            );

        // Riêng BigDecimal không nhận chuỗi số,
        // kể cả khi nhóm Float có chính sách khác.
        mapper.coercionConfigFor(BigDecimal.class)
            .setCoercion(
                CoercionInputShape.String,
                CoercionAction.Fail
            );

        return mapper;
    }
}
~~~

Trong ví dụ:

- Mặc định chung xử lý EmptyString như null.
- Nhóm Integer từ chối chuỗi và số thực.
- Nhóm Boolean từ chối chuỗi.
- BigDecimal có chính sách riêng cho String.

Đây là cấu hình minh họa cho một API yêu cầu đầu vào có kiểu JSON chặt chẽ. Một hệ thống khác có thể chọn TryConvert cho chuỗi số hoặc AsEmpty cho một số trường collection. Điều quan trọng là mỗi hành vi phải được lựa chọn theo hợp đồng dữ liệu và phạm vi tác động mong muốn.

## 21. Chọn cấu hình theo nhu cầu

| Yêu cầu | Cấu hình nên xem |
|---|---|
| Tất cả số nguyên từ chối chuỗi | LogicalType.Integer + String + Fail |
| Tất cả số nguyên từ chối số thực | LogicalType.Integer + Float + Fail |
| Chỉ BigDecimal từ chối chuỗi | BigDecimal.class + String + Fail |
| Chuỗi rỗng thành null theo mặc định | coercionConfigDefaults + EmptyString + AsNull |
| Chuỗi rỗng thành giá trị rỗng cho nhóm văn bản | LogicalType.Textual + EmptyString + AsEmpty |
| Boolean không nhận chuỗi | LogicalType.Boolean + String + Fail |
| Enum không nhận ordinal dạng số | LogicalType.Enum + Integer + Fail |
| Một lớp nghiệp vụ có quy tắc riêng | coercionConfigFor(MyType.class) |

CoercionConfig giúp Jackson xử lý đầu vào có chủ đích thay vì dựa hoàn toàn vào các quy tắc chuyển đổi mặc định. Cấu hình theo nhóm logic giữ chính sách nhất quán cho nhiều kiểu liên quan; cấu hình theo lớp cụ thể cho phép tạo ngoại lệ mà không ảnh hưởng phần còn lại. Khi phối hợp hai cấp cùng cấu hình mặc định, ứng dụng có thể mô tả rõ dữ liệu nào được chuyển đổi, dữ liệu nào bị từ chối và dữ liệu nào được xem là null hoặc rỗng.

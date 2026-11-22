# Kiểm tra dữ liệu dư sau giá trị JSON mong đợi

Một thông điệp JSON thường được thiết kế như một document có đúng một giá trị gốc (root value): object, array, string, number, boolean hoặc null. Sau giá trị đó có thể có khoảng trắng hợp lệ, nhưng không nên có thêm một giá trị JSON độc lập nếu giao thức chỉ cho phép một document.

Jackson có thể đọc JSON thành object Java bằng ObjectMapper hoặc ObjectReader. Tuy nhiên, đọc thành công object đầu tiên chưa chắc đã chứng minh toàn bộ nội dung đầu vào đã được tiêu thụ. Một chuỗi có thể chứa một object hợp lệ rồi tiếp tục chứa một object khác:

~~~json
{"orderId":"ORD-100"} {"orderId":"ORD-101"}
~~~

Hai object đều hợp lệ khi xét riêng, nhưng toàn bộ chuỗi không phải một JSON document đơn. Nếu endpoint chỉ chấp nhận một đơn hàng, dữ liệu phía sau object đầu tiên phải bị từ chối.

Jackson cung cấp DeserializationFeature.FAIL_ON_TRAILING_TOKENS để kiểm tra điều đó. Khi bật feature, Jackson đọc thêm token sau khi bind root value; nếu còn token, quá trình deserialize sẽ thất bại.

## 1. Một JSON document chỉ có một root value

JSON cho phép các cấu trúc lồng nhau. Một object có thể chứa object khác, array có thể chứa nhiều object, và các giá trị có thể lồng nhiều cấp:

~~~json
{
  "orderId": "ORD-100",
  "items": [
    { "sku": "BOOK-01", "quantity": 2 },
    { "sku": "BOOK-02", "quantity": 1 }
  ]
}
~~~

Đây vẫn là một root value duy nhất: object ngoài cùng. Hai object trong items là các giá trị con thuộc cấu trúc đó, không phải dữ liệu dư sau root.

Ngược lại, ví dụ sau chứa hai root value nối tiếp nhau:

~~~json
{"orderId":"ORD-100"}
{"orderId":"ORD-101"}
~~~

Nếu giao thức yêu cầu một JSON document cho mỗi request, chuỗi trên phải bị từ chối. Muốn truyền nhiều đơn hàng trong cùng một document, hãy dùng một array:

~~~json
[
  { "orderId": "ORD-100" },
  { "orderId": "ORD-101" }
]
~~~

Array là một root value duy nhất, còn hai object bên trong là các phần tử của array.

Khoảng trắng sau root value không phải dữ liệu dư:

~~~json
{ "orderId": "ORD-100" }

~~~

Các ký tự xuống dòng, tab và dấu cách hợp lệ sau JSON value được parser bỏ qua. Điều cần phát hiện là token hoặc giá trị khác xuất hiện sau root, chứ không phải khoảng trắng định dạng.

## 2. Hành vi mặc định và FAIL_ON_TRAILING_TOKENS

DeserializationFeature.FAIL_ON_TRAILING_TOKENS điều khiển việc Jackson có kiểm tra token còn lại sau khi deserialize root value hay không.

Trong cấu hình Jackson thông thường, feature này mặc định tắt để duy trì khả năng tương thích với hành vi cũ. Khi tắt, một lời gọi đọc có thể bind root value đầu tiên rồi không kiểm tra chặt phần còn lại của input. Điều này đặc biệt đáng chú ý khi dữ liệu đến từ client hoặc hệ thống bên ngoài.

Bật feature:

~~~java
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.json.JsonMapper;

ObjectMapper mapper = JsonMapper.builder()
    .enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS)
    .build();
~~~

Khi dùng mapper này để đọc một object:

~~~java
OrderRequest request = mapper.readValue(
    json,
    OrderRequest.class
);
~~~

Jackson sẽ xác nhận không còn token nào sau root value. Nếu có một root value thứ hai, quá trình đọc sẽ ném exception thay vì âm thầm chấp nhận phần đầu.

Feature này có từ Jackson 2.9. Với ứng dụng dùng phiên bản cũ hơn, cần kiểm tra API có sẵn trong phiên bản thực tế và cân nhắc nâng cấp theo bộ dependency được hỗ trợ.

Không nên dựa vào giả định rằng framework luôn bật hoặc luôn tắt feature này. Spring Boot và các ứng dụng có thể tùy chỉnh ObjectMapper bằng builder, customizer hoặc cấu hình riêng. Hãy kiểm tra mapper thực sự được sử dụng tại ranh giới nhận dữ liệu.

## 3. Bật kiểm tra cho một ObjectReader

Không phải mọi luồng đọc đều có cùng chính sách. Một endpoint có thể chỉ nhận một JSON document, trong khi một tác vụ import lại đọc một chuỗi nhiều root value có chủ đích.

Có thể tạo ObjectReader nghiêm ngặt cho riêng kiểu request:

~~~java
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.ObjectReader;

ObjectReader strictOrderReader = mapper
    .readerFor(OrderRequest.class)
    .with(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);

OrderRequest order = strictOrderReader.readValue(json);
~~~

ObjectReader là cấu hình đọc bất biến. Lời gọi with(...) trả về reader mới, không thay đổi mapper hoặc reader ban đầu. Vì vậy, có thể giữ một reader nghiêm ngặt cho API đơn giá trị và một reader khác cho luồng dữ liệu nhiều giá trị khi giao thức yêu cầu.

Ví dụ tạo reader theo kiểu request:

~~~java
public final class OrderRequestReader {
    private final ObjectReader reader;

    public OrderRequestReader(ObjectMapper mapper) {
        this.reader = mapper.readerFor(OrderRequest.class)
            .with(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);
    }

    public OrderRequest read(String body) throws JsonProcessingException {
        return reader.readValue(body);
    }
}
~~~

Cách này giúp chính sách kiểm tra dữ liệu dư nằm cạnh nơi định nghĩa kiểu request. Trong ứng dụng Spring MVC, nếu request được deserialize tự động bởi HttpMessageConverter, cần cấu hình mapper mà converter sử dụng; tạo một reader riêng nhưng không dùng nó ở đường nhận request sẽ không thay đổi hành vi của endpoint.

## 4. Phân biệt dữ liệu dư sau root với thuộc tính lạ bên trong object

Hai tình huống sau khác nhau:

**Thuộc tính lạ nằm bên trong root object:**

~~~json
{
  "orderId": "ORD-100",
  "unexpectedField": true
}
~~~

**Một root value khác nằm sau object:**

~~~json
{
  "orderId": "ORD-100"
}
true
~~~

Trường hợp thứ nhất vẫn có một root object. unexpectedField là một thuộc tính của object đó. Hành vi này được điều khiển bởi DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES.

Trường hợp thứ hai có một root object, sau đó là root value boolean. Hành vi này được điều khiển bởi DeserializationFeature.FAIL_ON_TRAILING_TOKENS.

Hai feature có mục đích riêng:

| Feature | Kiểm tra |
|---|---|
| FAIL_ON_UNKNOWN_PROPERTIES | Thuộc tính trong object không ánh xạ được vào kiểu Java đích. |
| FAIL_ON_TRAILING_TOKENS | Token còn lại sau khi root value đã được deserialize. |

Nếu hợp đồng yêu cầu vừa từ chối field lạ vừa từ chối root value thứ hai, có thể bật cả hai:

~~~java
ObjectReader strictReader = mapper
    .readerFor(OrderRequest.class)
    .with(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
    .with(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);
~~~

Lưu ý framework có thể đã tắt FAIL_ON_UNKNOWN_PROPERTIES để consumer tương thích với field mới từ producer. Hãy quyết định chính sách dựa trên hợp đồng và khả năng tiến hóa của API. Không dùng FAIL_ON_TRAILING_TOKENS để thay thế kiểm tra field lạ, và cũng không dùng FAIL_ON_UNKNOWN_PROPERTIES để phát hiện một JSON document thứ hai.

Các trường hợp khác như hai thuộc tính trùng tên trong cùng object là một vấn đề riêng. Nếu hợp đồng cần từ chối duplicate key, hãy cấu hình cơ chế phát hiện duplicate field của parser; FAIL_ON_TRAILING_TOKENS không xử lý trường hợp đó.

## 5. Những dạng input cần được kiểm tra

Giả sử kiểu đích là:

~~~java
public record OrderRequest(String orderId) {}
~~~

Các input dưới đây có ý nghĩa khác nhau:

| Input | Kết quả mong đợi với reader kiểm tra trailing tokens |
|---|---|
| {"orderId":"ORD-100"} | Chấp nhận: một root object. |
| {"orderId":"ORD-100"} và theo sau là khoảng trắng | Chấp nhận: phần sau chỉ là khoảng trắng. |
| {"orderId":"ORD-100"} và theo sau là newline/tab | Chấp nhận: newline và tab là khoảng trắng. |
| {"orderId":"ORD-100"} {"orderId":"ORD-101"} | Từ chối: có root object thứ hai. |
| {"orderId":"ORD-100"} true | Từ chối: có root boolean thứ hai. |
| {"orderId":"ORD-100"} [] | Từ chối: có root array thứ hai. |
| [{"orderId":"ORD-100"},{"orderId":"ORD-101"}] | Chấp nhận nếu kiểu đích là collection phù hợp; đây là một root array. |

Ví dụ JSON hỏng như:

~~~text
{"orderId":"ORD-100"} garbage
~~~

cũng không phải input hợp lệ. Parser thường phát hiện lỗi cú pháp khi cố đọc phần tiếp theo. FAIL_ON_TRAILING_TOKENS bổ sung bảo đảm rằng một root value thứ hai có token hợp lệ cũng không bị bỏ qua.

Không nên nhầm việc parser chấp nhận khoảng trắng với việc parser bỏ qua tùy ý nội dung phía sau. Khoảng trắng là thành phần được JSON cho phép; một giá trị độc lập khác không phải khoảng trắng.

## 6. Kiểm tra hành vi bằng JUnit

Một test nên chứng minh cả hai phía: JSON có một root value được chấp nhận, còn JSON có root value thứ hai bị từ chối.

Ví dụ:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.ObjectReader;
import com.fasterxml.jackson.databind.json.JsonMapper;
import org.junit.jupiter.api.Test;

class TrailingTokensTest {

    record OrderRequest(String orderId) {}

    private final ObjectMapper mapper = JsonMapper.builder().build();

    private final ObjectReader strictReader = mapper
        .readerFor(OrderRequest.class)
        .with(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);

    @Test
    void acceptsOneRootValueAndTrailingWhitespace() throws Exception {
        OrderRequest order = strictReader.readValue(
            "{\"orderId\":\"ORD-100\"} \n\t"
        );

        assertEquals("ORD-100", order.orderId());
    }

    @Test
    void rejectsASecondRootValue() {
        String input =
            "{\"orderId\":\"ORD-100\"} {\"orderId\":\"ORD-101\"}";

        assertThrows(
            JsonProcessingException.class,
            () -> strictReader.readValue(input)
        );
    }
}
~~~

Test đầu tiên xác nhận whitespace không bị xem là dữ liệu dư. Test thứ hai xác nhận reader không chấp nhận hai object độc lập trong cùng input.

Có thể bổ sung test cho root boolean hoặc array thứ hai để bao phủ các kiểu JSON khác. Không cần kiểm tra mọi tổ hợp khoảng trắng; mục tiêu là xác nhận ranh giới giữa một root value và nhiều root value.

## 7. Khi ứng dụng thực sự cần đọc nhiều root value

Một số định dạng trao đổi cố ý truyền nhiều JSON value nối tiếp nhau, ví dụ stream gồm nhiều object độc lập. Trường hợp này khác với một API request chỉ chấp nhận một JSON document.

Nếu giao thức cho phép nhiều root value, có thể dùng ObjectReader.readValues(...) để nhận MappingIterator:

~~~java
import com.fasterxml.jackson.databind.MappingIterator;
import com.fasterxml.jackson.databind.ObjectReader;

String sequence = """
    {"orderId":"ORD-100"}
    {"orderId":"ORD-101"}
    """;

ObjectReader sequenceReader = mapper.readerFor(OrderRequest.class);

try (MappingIterator<OrderRequest> values =
         sequenceReader.readValues(sequence)) {
    while (values.hasNextValue()) {
        OrderRequest order = values.nextValue();
        process(order);
    }
}
~~~

Đây là một luồng nhiều giá trị ở cấp root. Reader đọc từng giá trị theo thứ tự. Không bật FAIL_ON_TRAILING_TOKENS trên reader này, vì token kế tiếp chính là phần tử tiếp theo của luồng.

Nếu producer có thể gửi nhiều bản ghi, cần định nghĩa framing rõ ràng:

- JSON array: một JSON document chứa danh sách.
- NDJSON/JSON Lines: mỗi dòng là một JSON document riêng.
- JSON root-value sequence: nhiều JSON value được đọc tuần tự theo giao thức đã thống nhất.

Không nên để endpoint đơn giá trị vô tình hoạt động như một parser chuỗi nhiều root value. Khi giao thức là một document, dùng reader strict; khi giao thức là sequence, dùng API đọc sequence và kiểm soát ranh giới bản ghi.

## 8. Kiểm tra ở ranh giới nhận dữ liệu

Việc bật feature ở một mapper không có tác dụng nếu endpoint đang dùng một mapper khác. Đây là điểm dễ bỏ sót trong ứng dụng Spring Boot hoặc hệ thống có nhiều adapter đọc JSON.

Với Spring MVC, body thường được deserialize thông qua HTTP message converter. Nếu cần từ chối dữ liệu dư cho mọi request đi qua converter, hãy cấu hình đúng mapper được converter sử dụng và kiểm tra hành vi bằng integration test HTTP. Nếu chỉ một luồng nhập dữ liệu cần chính sách nghiêm ngặt, dùng ObjectReader tại chính luồng đó có thể rõ ràng hơn.

Cần chú ý các đường đọc khác nhau:

- Controller dùng @RequestBody thường không gọi reader mà bạn tự tạo trong service.
- Consumer message queue có thể có một mapper riêng do framework hoặc serializer cấu hình.
- Batch import có thể đọc stream bằng MappingIterator và cần cho phép nhiều root value.
- Code gọi trực tiếp mapper.readValue(...) chịu cấu hình của mapper hoặc reader được dùng ở lời gọi đó.

Hãy kiểm tra tại đúng ranh giới nhận dữ liệu, nơi ứng dụng quyết định payload nào được chấp nhận trước khi thực hiện nghiệp vụ.

## 9. Vì sao kiểm tra dữ liệu dư quan trọng?

Nếu một tầng chỉ đọc root value đầu tiên rồi bỏ phần còn lại, trong khi tầng khác hiểu hoặc xử lý toàn bộ input, hai tầng có thể diễn giải cùng một chuỗi theo cách khác nhau. Sự khác biệt này làm hợp đồng khó dự đoán và có thể tạo lỗ hổng kiểm tra dữ liệu.

Ví dụ, gateway kiểm tra object đầu tiên là request hợp lệ, nhưng một thành phần phía sau lại đọc tiếp một root value khác. Nếu hai tầng không thống nhất cách parse, dữ liệu được xác thực và dữ liệu được xử lý có thể không còn là cùng một thông điệp.

Kiểm tra trailing tokens giúp ràng buộc payload vào đúng một root value ở nơi cần quy tắc đó. Tuy nhiên, đây không phải cơ chế thay thế xác thực chữ ký, phân quyền, validation nghiệp vụ hay giới hạn kích thước request. Mỗi kiểm soát giải quyết một loại rủi ro khác nhau.

Với dữ liệu không đáng tin cậy, nên kết hợp:

1. Giới hạn kích thước body ở tầng HTTP hoặc transport.
2. Parse JSON bằng cấu hình parser phù hợp.
3. Bật FAIL_ON_TRAILING_TOKENS khi hợp đồng chỉ cho phép một root value.
4. Áp dụng validation cho trường bắt buộc, miền giá trị và cấu trúc.
5. Thực hiện authorization và quy tắc nghiệp vụ trước khi thay đổi trạng thái.

## 10. Cách chọn chính sách phù hợp

| Nhu cầu | Cách thực hiện |
|---|---|
| API nhận đúng một JSON document | Tạo ObjectReader với FAIL_ON_TRAILING_TOKENS hoặc cấu hình mapper được HTTP converter sử dụng. |
| Toàn ứng dụng chỉ chấp nhận một root value | Bật feature trên mapper dùng chung sau khi đánh giá các luồng đọc hiện tại. |
| Một endpoint cần strict, luồng khác cần sequence | Tạo các ObjectReader riêng với chính sách khác nhau. |
| Đọc một danh sách trong một document | Deserialize root array thành List<T> bằng TypeReference hoặc JavaType. |
| Đọc nhiều root value nối tiếp | Dùng readValues(...) và MappingIterator, theo một giao thức sequence đã xác định. |
| Từ chối field không biết bên trong object | Xem xét FAIL_ON_UNKNOWN_PROPERTIES; đây là chính sách khác với trailing tokens. |

Trước khi bật feature toàn cục, hãy rà soát các luồng có chủ ý đọc nhiều root value. Nếu không có luồng như vậy, chính sách strict toàn cục có thể đơn giản hóa việc kiểm soát payload. Nếu có, tách reader theo mục đích sẽ giúp tránh vô tình phá vỡ luồng nhập dữ liệu.

## Kết luận

FAIL_ON_TRAILING_TOKENS giúp Jackson xác nhận rằng sau khi deserialize root value không còn token nào khác. Nó phân biệt một JSON document duy nhất với input chứa nhiều root value nối tiếp, đồng thời vẫn cho phép khoảng trắng hợp lệ sau document.

Hãy dùng ObjectReader strict tại ranh giới chỉ chấp nhận một JSON document, hoặc bật feature trên mapper được framework thực sự sử dụng nếu đó là chính sách chung. Với luồng nhiều giá trị có chủ đích, dùng readValues và MappingIterator. Cần phân biệt kiểm tra trailing tokens với kiểm tra thuộc tính lạ, duplicate key và validation nghiệp vụ để mỗi quy tắc được áp dụng đúng chỗ.


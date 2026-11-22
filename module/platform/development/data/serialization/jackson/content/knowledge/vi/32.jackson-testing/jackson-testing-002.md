# So sánh cấu trúc JSON thay vì chỉ so sánh chuỗi ký tự

Trong kiểm thử serialization, một cách làm dễ viết là serialize object thành JSON rồi so sánh chuỗi kết quả với một chuỗi mong đợi. Cách này có thể tạo test giòn: hai JSON có cùng dữ liệu vẫn khác nhau vì thứ tự property, khoảng trắng, xuống dòng hoặc cách escape ký tự. Ngược lại, chỉ chuẩn hóa chuỗi rồi so sánh cũng không giúp hiểu rõ khác biệt về kiểu dữ liệu, field bị thiếu, null hay thứ tự phần tử.

JSON là một cấu trúc dữ liệu. Object là tập hợp các member có tên; array là dãy phần tử có thứ tự; string, number, boolean và null là các giá trị scalar. Vì vậy, với phần lớn kiểm thử Jackson, nên **parse JSON mong đợi và JSON thực tế thành cây dữ liệu, sau đó so sánh cấu trúc**. Jackson Tree Model cung cấp JsonNode, ObjectNode và ArrayNode để thực hiện việc này.

So sánh cấu trúc giúp bỏ qua khác biệt trình bày không có ý nghĩa, đồng thời vẫn giữ những khác biệt có ý nghĩa như kiểu string so với number, null so với field không tồn tại và thứ tự array. Khi contract có quy tắc đặc biệt, ví dụ array được xem như tập hợp hoặc số 1 và 1.0 phải được coi là tương đương, hãy chuẩn hóa hoặc so sánh riêng theo quy tắc đó thay vì làm lỏng toàn bộ phép so sánh.

## 1. Vì sao so sánh JSON string dễ tạo test giòn?

Giả sử serializer tạo ra:

~~~json
{"id":42,"name":"An","active":true}
~~~

Chuỗi mong đợi trong test lại là:

~~~json
{
  "name": "An",
  "active": true,
  "id": 42
}
~~~

Hai văn bản khác nhau về khoảng trắng, xuống dòng và thứ tự property, nhưng biểu diễn cùng một JSON object. Nếu dùng phép so sánh chuỗi:

~~~java
assertEquals(expectedJson, actualJson);
~~~

test sẽ thất bại dù dữ liệu JSON có cùng ý nghĩa.

Một ví dụ khác là escape string:

~~~json
{"message":"A"}
~~~

và:

~~~json
{"message":"\u0041"}
~~~

Sau khi parse, cả hai đều chứa cùng một string. Cách viết trong văn bản khác nhau nhưng giá trị string giống nhau.

Các khác biệt trình bày thường không phải điều test muốn kiểm tra:

- Khoảng trắng giữa token.
- Xuống dòng và indentation.
- Thứ tự member của object.
- Cách viết escape cho cùng một ký tự.
- Một số khác biệt về cách formatter trình bày số.

Nếu mục tiêu là xác nhận hợp đồng JSON, hãy so sánh cây dữ liệu. Nếu mục tiêu thật sự là kiểm tra output phải có format cụ thể, ví dụ một file snapshot được ký hoặc một giao thức yêu cầu byte chính xác, lúc đó mới so sánh văn bản/byte theo yêu cầu đó.

## 2. Object, array và scalar có quy tắc so sánh khác nhau

Cần hiểu semantics của từng loại node trước khi viết assertion:

| JSON node | Quy tắc cấu trúc thường dùng |
|---|---|
| Object | So sánh tập member theo tên và giá trị; thứ tự member không có ý nghĩa |
| Array | So sánh phần tử theo vị trí; thứ tự có ý nghĩa |
| String | So sánh nội dung string sau khi parse |
| Number | So sánh theo node/value và chính sách số của ứng dụng |
| Boolean | true chỉ bằng true; false chỉ bằng false |
| Null | Phải phân biệt với field không tồn tại |

Ví dụ hai object sau có cấu trúc tương đương:

~~~json
{
  "user": {
    "id": 42,
    "name": "An"
  },
  "enabled": true
}
~~~

~~~json
{
  "enabled": true,
  "user": {
    "name": "An",
    "id": 42
  }
}
~~~

Nhưng hai array sau không tương đương nếu thứ tự là một phần của contract:

~~~json
["created", "validated", "published"]
~~~

~~~json
["published", "created", "validated"]
~~~

Không nên áp dụng một quy tắc bỏ qua thứ tự cho toàn bộ JSON. Object và array có semantics khác nhau.

## 3. Dùng JsonNode để so sánh cấu trúc

Jackson có thể parse cả JSON mong đợi lẫn JSON thực tế thành JsonNode:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper mapper = new ObjectMapper();

JsonNode expected = mapper.readTree("""
        {
          "id": 42,
          "name": "An",
          "active": true
        }
        """);

JsonNode actual = mapper.readTree("""
        {"active":true,"name":"An","id":42}
        """);

assertEquals(expected, actual);
~~~

JsonNode triển khai equals() theo cấu trúc node. Với object, các member được so sánh theo tên và value nên thứ tự ghi trong JSON không làm assertion thất bại. Với array, các phần tử được so sánh theo thứ tự và số lượng. Các node lồng nhau được so sánh đệ quy.

Đây là cách phù hợp cho phần lớn test kiểm tra serializer:

~~~java
String actualJson = mapper.writeValueAsString(response);

JsonNode expected = mapper.readTree("""
        {
          "orderId": "ORD-42",
          "status": "PAID",
          "total": 1250.50
        }
        """);

JsonNode actual = mapper.readTree(actualJson);

assertEquals(expected, actual);
~~~

Test xác nhận JSON output có đúng dữ liệu và cấu trúc. Nó không phụ thuộc vào pretty printing hoặc thứ tự property do reflection/annotation tạo ra.

### 3.1. Tạo helper để tái sử dụng

Nếu nhiều test cần so sánh JSON, có thể tạo helper nhỏ:

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import static org.junit.jupiter.api.Assertions.assertEquals;

public final class JsonAssertions {
    private static final ObjectMapper MAPPER = new ObjectMapper();

    private JsonAssertions() {
    }

    public static void assertJsonEquals(String expected, String actual)
            throws JsonProcessingException {
        JsonNode expectedTree = MAPPER.readTree(expected);
        JsonNode actualTree = MAPPER.readTree(actual);

        assertEquals(
                expectedTree,
                actualTree,
                () -> "JSON structures differ.\nExpected:\n"
                        + expectedTree.toPrettyString()
                        + "\nActual:\n"
                        + actualTree.toPrettyString()
        );
    }
}
~~~

Helper parse hai văn bản và so sánh tree. Pretty output chỉ được dùng trong thông báo lỗi để người đọc dễ tìm khác biệt; nó không tham gia phép so sánh.

Trong dự án thực tế, helper có thể nhận ObjectMapper được cấu hình của ứng dụng thay vì tạo mapper mới. Điều này quan trọng nếu test cần cùng module, coercion, custom node factory hoặc parser policy với code production.

## 4. So sánh JSON output của serializer

Một test serializer nên tạo object Java, serialize thành JSON, parse kết quả và so sánh với JSON contract mong đợi.

Ví dụ DTO:

~~~java
public record PaymentResponse(
        String paymentId,
        String status,
        BigDecimal amount,
        boolean successful
) {
}
~~~

Test:

~~~java
@Test
void serializesPaymentResponseWithExpectedStructure() throws Exception {
    PaymentResponse response = new PaymentResponse(
            "pay-100",
            "COMPLETED",
            new BigDecimal("1250.50"),
            true
    );

    String actualJson = mapper.writeValueAsString(response);

    JsonNode expected = mapper.readTree("""
            {
              "paymentId": "pay-100",
              "status": "COMPLETED",
              "amount": 1250.50,
              "successful": true
            }
            """);

    JsonNode actual = mapper.readTree(actualJson);

    assertEquals(expected, actual);
}
~~~

Test này kiểm tra tên property, giá trị, kiểu JSON, field bắt buộc và member dư/thiếu. Nếu serializer vô tình đổi amount thành string, tree comparison sẽ phát hiện khác biệt giữa TextNode và node số. Nếu thêm property ngoài contract, object equality cũng phát hiện member dư.

## 5. So sánh JSON input sau deserialization

Với deserializer, có thể đọc JSON thành object Java rồi serialize lại thành tree để so sánh representation chuẩn. Tuy nhiên, nên kiểm tra cả object Java và JSON output, vì chỉ round-trip có thể che giấu lỗi nếu serializer và deserializer cùng mắc một giả định sai.

Ví dụ:

~~~java
@Test
void deserializesRequestAndProducesExpectedDomainValues() throws Exception {
    String input = """
            {
              "customerId": "cus-7",
              "quantity": 3,
              "enabled": true
            }
            """;

    CreateOrderRequest request =
            mapper.readValue(input, CreateOrderRequest.class);

    assertEquals("cus-7", request.customerId());
    assertEquals(3, request.quantity());
    assertTrue(request.enabled());
}
~~~

Nếu cần xác nhận representation sau khi bind và ghi lại:

~~~java
JsonNode actualTree = mapper.valueToTree(request);
JsonNode expectedTree = mapper.readTree("""
        {
          "customerId": "cus-7",
          "quantity": 3,
          "enabled": true
        }
        """);

assertEquals(expectedTree, actualTree);
~~~

valueToTree() hữu ích để chuyển object thành cây JSON theo serializer đang cấu hình. Với test tích hợp serialization, vẫn có thể dùng writeValueAsString() rồi readTree() để đi qua toàn bộ đường ghi text.

## 6. Object member order không có ý nghĩa, array order có ý nghĩa

Theo mô hình JSON, object là tập member; không nên dựa vào thứ tự member để biểu đạt nghiệp vụ. Array là dãy có thứ tự nên vị trí phần tử có ý nghĩa.

Ví dụ object:

~~~json
{"firstName":"An","lastName":"Nguyen"}
~~~

và:

~~~json
{"lastName":"Nguyen","firstName":"An"}
~~~

có thể so sánh bằng tree equality và vẫn bằng nhau.

Ngược lại:

~~~json
{"steps":["validate","charge","notify"]}
~~~

khác:

~~~json
{"steps":["charge","validate","notify"]}
~~~

nếu quy trình yêu cầu validate trước charge.

Khi một test tree comparison thất bại ở array, đừng vội bỏ qua thứ tự. Hãy hỏi xem thứ tự có phải một phần của contract không. Nếu có, assertion hiện tại đang làm đúng việc.

## 7. Khi array mang ý nghĩa tập hợp không thứ tự

Một số API dùng array để truyền tập hợp phần tử mà thứ tự không quan trọng, ví dụ danh sách role hoặc tập permission. JSON vẫn định nghĩa array có thứ tự; ý nghĩa không thứ tự là quy ước của contract ứng dụng.

Có hai cách kiểm thử phù hợp:

1. Chuẩn hóa array theo một khóa ổn định trước khi so sánh.
2. Chuyển các phần tử thành map/set theo khóa nghiệp vụ rồi so sánh tập giá trị.

Không nên xóa thứ tự array toàn cục vì sẽ làm mất khả năng phát hiện lỗi ở những array thực sự có thứ tự.

Ví dụ chuẩn hóa array object theo id:

~~~java
private ArrayNode sortById(ArrayNode source) {
    List<JsonNode> items = new ArrayList<>();
    source.forEach(items::add);

    items.sort(Comparator.comparing(
            node -> node.path("id").asText()
    ));

    ArrayNode normalized = JsonNodeFactory.instance.arrayNode();
    items.forEach(normalized::add);
    return normalized;
}
~~~

Test:

~~~java
JsonNode expectedTree = mapper.readTree("""
        [
          {"id":"a-1","name":"An"},
          {"id":"b-2","name":"Binh"}
        ]
        """);

JsonNode actualTree = mapper.readTree("""
        [
          {"id":"b-2","name":"Binh"},
          {"id":"a-1","name":"An"}
        ]
        """);

assertEquals(
        sortById((ArrayNode) expectedTree),
        sortById((ArrayNode) actualTree)
);
~~~

Cách này chỉ phù hợp khi id là khóa duy nhất và thứ tự không có ý nghĩa. Nếu có phần tử trùng id, helper nên phát hiện và báo lỗi thay vì âm thầm tạo một kết quả so sánh mơ hồ.

Một lựa chọn khác là dùng Set sau khi chuyển từng phần tử thành key/value domain phù hợp. Hãy bảo đảm phép chuyển đổi không làm mất duplicate nếu duplicate là điều cần kiểm tra.

## 8. Phân biệt field bị thiếu với field có giá trị null

JSON A:

~~~json
{"userId": "u-1"}
~~~

JSON B:

~~~json
{"userId": "u-1", "middleName": null}
~~~

Hai object không có cùng cấu trúc: JSON B có member middleName với giá trị null; JSON A không có member đó.

Với JsonNode:

~~~java
JsonNode node = mapper.readTree(json);

assertFalse(node.has("middleName"));
~~~

Với field hiện diện và null:

~~~java
assertTrue(node.has("middleName"));
assertTrue(node.get("middleName").isNull());
assertFalse(node.hasNonNull("middleName"));
~~~

Một số API Jackson hữu ích:

| API | Ý nghĩa |
|---|---|
| get("field") | Trả node hoặc Java null nếu field không tồn tại |
| path("field") | Trả MissingNode nếu field không tồn tại |
| has("field") | Kiểm tra member có hiện diện, kể cả giá trị JSON null |
| hasNonNull("field") | Chỉ true khi member hiện diện và không phải JSON null |
| isNull() | Kiểm tra node là JSON null |
| isMissingNode() | Kiểm tra node là MissingNode |

Đừng dùng asText() hoặc asInt() một cách tùy tiện để kiểm tra presence. Các phương thức chuyển đổi có thể trả giá trị mặc định cho node thiếu hoặc sai kiểu, làm test bỏ sót lỗi.

## 9. Kiểm tra kiểu JSON, không chỉ giá trị hiển thị

Các giá trị sau không giống nhau về kiểu:

~~~json
{"id": 42}
~~~

~~~json
{"id": "42"}
~~~

Tương tự:

~~~json
{"enabled": true}
~~~

~~~json
{"enabled": "true"}
~~~

Nếu parse thành tree, có thể kiểm tra kiểu rõ ràng:

~~~java
JsonNode root = mapper.readTree(actualJson);

assertTrue(root.path("id").isNumber());
assertTrue(root.path("enabled").isBoolean());
assertTrue(root.path("name").isTextual());
~~~

Với property có thể null:

~~~java
JsonNode nickname = root.get("nickname");

assertNotNull(nickname);
assertTrue(nickname.isNull());
~~~

Điều này hữu ích khi kiểm tra custom serializer, coercion hoặc DTO có kiểu dữ liệu không rõ. Một test chỉ gọi asText() có thể khiến số 42 và string "42" đều cho kết quả nhìn giống nhau; kiểm tra node type giúp giữ đúng contract.

## 10. So sánh số: chú ý representation và precision

JSON có một loại cú pháp number, nhưng parser Jackson có thể tạo các loại node số khác nhau như IntNode, LongNode, BigIntegerNode, FloatNode, DoubleNode hoặc DecimalNode tùy giá trị và cấu hình.

Vì vậy, không nên giả định mọi cách viết số tương đương về mặt toán học sẽ luôn bằng nhau theo JsonNode.equals(). Ví dụ 1 và 1.0 có thể được parse thành các concrete numeric node khác nhau; precision và scale của BigDecimal cũng có thể ảnh hưởng tùy node factory/cấu hình.

Nếu contract yêu cầu so sánh đúng representation số mà Jackson tạo ra, tree equality là phù hợp. Nếu contract yêu cầu so sánh giá trị thập phân theo toán học, hãy kiểm tra rõ bằng BigDecimal:

~~~java
JsonNode actual = mapper.readTree("""
        {"amount": 1.0}
        """);

assertTrue(actual.path("amount").isNumber());

BigDecimal expectedAmount = new BigDecimal("1.00");
BigDecimal actualAmount = actual.path("amount").decimalValue();

assertEquals(0, expectedAmount.compareTo(actualAmount));
~~~

BigDecimal.compareTo() so sánh giá trị số và bỏ qua khác biệt scale; BigDecimal.equals() thì xét cả scale. Vì vậy 1.0 và 1.00 có thể không bằng nhau theo equals() dù cùng giá trị số.

### 10.1. Khi nào representation số quan trọng?

Một số contract cần giữ kiểu số nguyên hay thập phân, hoặc cần giữ scale cho mục đích hiển thị/định dạng. Ví dụ tiền tệ có thể cần hai chữ số thập phân khi ghi ra JSON. Trong trường hợp đó, test nên xác nhận đúng node type/scale/format đã thỏa thuận.

Một contract khác chỉ quan tâm giá trị số. Khi đó, dùng decimalValue() và compareTo() ở các field số cần so sánh, trong khi vẫn so sánh phần object còn lại bằng tree equality.

Không chuyển số qua double nếu cần độ chính xác thập phân. Với tiền và phép so sánh chính xác, BigDecimal thường phù hợp hơn.

## 11. Escape string và Unicode

Khi parse JSON, escape sequence được giải mã thành nội dung string. Do đó:

~~~json
{"letter":"A"}
~~~

và:

~~~json
{"letter":"\u0041"}
~~~

có thể cho cùng TextNode.

Nhưng không nên tự động coi mọi chuỗi trông giống nhau là tương đương. Ví dụ một ký tự có thể được mã hóa bằng một code point dựng sẵn hoặc bằng chuỗi code point kết hợp dấu. Hai chuỗi Unicode này có thể hiển thị giống nhau nhưng có dãy code point khác nhau.

Nếu hợp đồng yêu cầu chuẩn hóa Unicode, hãy thực hiện normalization rõ ràng, ví dụ NFC, ở đúng tầng dữ liệu và kiểm thử chính sách đó. Không âm thầm normalize trong helper JSON chung vì điều đó có thể làm thay đổi giá trị string có ý nghĩa chính xác.

Whitespace bên ngoài string không có ý nghĩa với cấu trúc JSON; whitespace bên trong string là dữ liệu và phải được giữ:

~~~json
{"message":"hello world"}
~~~

khác:

~~~json
{"message":"helloworld"}
~~~

## 12. So sánh một phần cây JSON bằng JSON Pointer

Không phải lúc nào test cũng cần so sánh toàn bộ payload. Có thể lấy một subtree bằng JSON Pointer:

~~~java
JsonNode metadata = actual.at("/metadata");
JsonNode customer = actual.at("/order/customer");
JsonNode firstLine = actual.at("/order/lines/0");
~~~

Sau đó so sánh subtree:

~~~java
assertEquals(
        expectedCustomer,
        actual.at("/customer")
);
~~~

JSON Pointer dùng dấu slash để đi qua object property và array index. Nếu property name chứa ký tự đặc biệt như slash hoặc tilde, cần escape theo quy tắc JSON Pointer.

Nếu chỉ quan tâm một số field, assertion trực tiếp cũng được:

~~~java
assertEquals("PAID", actual.at("/payment/status").textValue());
assertEquals("ORD-42", actual.at("/order/id").textValue());
assertTrue(actual.at("/payment/confirmed").asBoolean());
~~~

Tuy nhiên, assertion dùng asText()/asBoolean() nên đi kèm kiểm tra node type nếu kiểu JSON là một phần của contract:

~~~java
JsonNode status = actual.at("/payment/status");
assertTrue(status.isTextual());
assertEquals("PAID", status.textValue());
~~~

## 13. So sánh JSON nhưng bỏ qua field biến động

Một số response có field thay đổi theo mỗi lần chạy, ví dụ generatedAt, requestId hoặc traceId. Nếu test không nhằm kiểm tra những field đó, có thể tạo bản sao tree và loại field trước khi so sánh.

~~~java
ObjectNode expectedComparable = expected.deepCopy();
ObjectNode actualComparable = actual.deepCopy();

expectedComparable.remove("generatedAt");
actualComparable.remove("generatedAt");

expectedComparable.remove("traceId");
actualComparable.remove("traceId");

assertEquals(expectedComparable, actualComparable);
~~~

Dùng deepCopy() để không làm thay đổi tree gốc. Không xóa field khỏi actual rồi bỏ qua việc kiểm tra field có tồn tại hay có format hợp lệ; hãy viết assertion riêng cho field biến động nếu contract vẫn yêu cầu nó.

Với field lồng nhau, lấy ObjectNode con rồi remove field tại đúng vị trí. Với array, cần xác định phần tử nào chứa field và dùng index hoặc khóa nghiệp vụ phù hợp.

Không nên tạo helper ignore-all-unknown dùng cho mọi test. Việc bỏ qua field dư có thể che giấu việc serializer vô tình công bố dữ liệu nội bộ hoặc thay đổi contract.

## 14. So sánh toàn bộ object và kiểm tra subset là hai mục tiêu khác nhau

So sánh toàn bộ tree yêu cầu không có member dư hoặc thiếu. Đây là lựa chọn tốt khi test JSON contract của một response DTO.

Nếu chỉ muốn kiểm tra một phần payload, hãy viết test thể hiện rõ đó là subset assertion:

~~~java
assertEquals("PAID", actual.path("status").textValue());
assertEquals("ORD-42", actual.path("orderId").textValue());
~~~

Hoặc so sánh subtree có ý nghĩa:

~~~java
assertEquals(expectedCustomer, actual.path("customer"));
~~~

Không dùng một JSON expected nhỏ rồi so sánh với toàn bộ actual nếu actual có nhiều field hợp lệ hơn. Ngược lại, không dùng subset assertion cho test contract cần phát hiện field ngoài dự kiến.

Có thể tổ chức hai lớp test:

- Test contract đầy đủ: so sánh toàn bộ JSON tree để phát hiện mọi field thiếu/dư.
- Test hành vi tập trung: kiểm tra các field/subtree liên quan đến một quy tắc cụ thể.

## 15. So sánh object lồng nhau và collection

Tree equality xử lý đệ quy nên không cần viết assertion cho từng cấp nếu muốn kiểm tra toàn bộ cấu trúc:

~~~json
{
  "order": {
    "id": "ORD-42",
    "customer": {
      "id": "CUS-7",
      "name": "An"
    },
    "lines": [
      {
        "productCode": "P-1",
        "quantity": 2
      },
      {
        "productCode": "P-2",
        "quantity": 1
      }
    ]
  }
}
~~~

Chỉ cần parse expected và actual rồi assertEquals. Nếu test thất bại, in hai tree đã pretty-print để thấy vị trí khác biệt.

Nếu muốn kiểm tra chi tiết một phần tử, có thể dùng pointer:

~~~java
assertEquals(
        "P-1",
        actual.at("/order/lines/0/productCode").textValue()
);

assertEquals(
        2,
        actual.at("/order/lines/0/quantity").intValue()
);
~~~

Cần nhớ array index phụ thuộc thứ tự. Nếu phần tử là tập hợp không thứ tự, hãy chuẩn hóa theo khóa như phần trước.

## 16. Duplicate object keys cần được phát hiện trước khi so sánh tree

JSON object nên có tên member duy nhất. Một văn bản như sau có duplicate key:

~~~json
{
  "role": "USER",
  "role": "ADMIN"
}
~~~

Nếu parser chấp nhận input và tree model chỉ giữ một giá trị cho key, phép so sánh tree sau đó không còn thấy đầy đủ văn bản ban đầu. Hành vi xử lý duplicate key có thể khác nhau giữa parser và cấu hình.

Nếu duplicate key không được phép, hãy bật strict duplicate detection ở parser:

~~~java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.StreamReadFeature;
import com.fasterxml.jackson.databind.ObjectMapper;

JsonFactory factory = JsonFactory.builder()
        .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
        .build();

ObjectMapper strictMapper = new ObjectMapper(factory);
~~~

Test:

~~~java
assertThrows(JsonProcessingException.class, () ->
        strictMapper.readTree("""
                {
                  "role": "USER",
                  "role": "ADMIN"
                }
                """)
);
~~~

Strict duplicate detection là một chính sách parse, không phải tính năng so sánh tree. Bật nó ở mapper dùng cho input cần schema chặt và kiểm tra tương thích với phiên bản Jackson đang dùng.

## 17. Test serializer và deserializer riêng, rồi mới test round-trip

Round-trip test thường có dạng:

~~~java
String json = mapper.writeValueAsString(value);
MyType restored = mapper.readValue(json, MyType.class);

assertEquals(value, restored);
~~~

Test này hữu ích để xác nhận một object có thể đi qua cả hai chiều. Tuy nhiên, nó không chứng minh JSON contract đúng. Serializer có thể ghi sai tên field và deserializer cũng đọc theo đúng tên sai đó; round-trip vẫn pass.

Nên tách test:

1. Serializer: object Java tạo ra JSON tree đúng với contract mong đợi.
2. Deserializer: JSON input chuẩn tạo ra object Java có field/semantics đúng.
3. Round-trip: nếu ứng dụng cần, kiểm tra thêm khả năng ghi rồi đọc lại mà không mất dữ liệu.

Ví dụ serializer test:

~~~java
JsonNode actual = mapper.readTree(mapper.writeValueAsString(value));
assertEquals(expectedJsonTree, actual);
~~~

Deserializer test:

~~~java
MyType restored = mapper.readValue(inputJson, MyType.class);
assertEquals(expectedId, restored.id());
assertEquals(expectedStatus, restored.status());
~~~

Cách chia này giúp biết lỗi nằm ở chiều ghi, chiều đọc hay ở semantics của domain model.

## 18. Kiểm tra property order khi nó thật sự là yêu cầu

Về semantics JSON, thứ tự object member không nên được xem là dữ liệu. Vì vậy, không nên dùng chuỗi JSON để kiểm tra thứ tự field chỉ vì output hiện tại đang có thứ tự ổn định.

Có một số trường hợp thứ tự byte có thể quan trọng với hệ thống bên ngoài, ví dụ:

- Một giao thức legacy yêu cầu thứ tự văn bản cụ thể.
- Snapshot text được quản lý như artifact có format chính xác.
- JSON được ký hoặc hash dưới dạng byte.
- Một tool downstream có lỗi và phụ thuộc thứ tự property.

Trong các trường hợp đó, cần nêu rõ yêu cầu và test ở tầng output text/byte. Có thể cấu hình JsonPropertyOrder hoặc SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS khi phù hợp, nhưng thứ tự field của POJO và thứ tự key của Map là hai vấn đề khác nhau.

Nếu cần ký JSON, không nên chỉ sort key rồi tự cho rằng đã có canonical JSON. Cần dùng implementation của một quy tắc canonicalization được chuẩn hóa, chẳng hạn JSON Canonicalization Scheme (RFC 8785), bao gồm cả quy tắc number và string escaping. Tree equality không tạo ra canonical byte representation.

## 19. Dùng JSON assertion library khi cần quy tắc so sánh nâng cao

JsonNode equality đáp ứng nhiều trường hợp mà không cần dependency thêm. Khi test cần DSL dễ đọc hoặc quy tắc linh hoạt, có thể cân nhắc thư viện chuyên so sánh JSON như JsonUnit hoặc JSONassert.

Các tính năng có thể hữu ích:

- So sánh theo JSON path.
- Bỏ qua field được chỉ định.
- Bỏ qua thứ tự array ở một số path.
- So sánh số theo tolerance hoặc quy tắc numeric cụ thể.
- Thông báo diff chi tiết hơn.

Cần đọc rõ semantics của chế độ so sánh. Một chế độ lenient có thể cho phép field dư hoặc bỏ qua thứ tự array; điều đó có thể làm test yếu đi nếu contract cần chặt. Không bật chế độ bỏ qua toàn cục chỉ để một test pass.

Nếu chỉ cần bỏ qua whitespace và object member order, Jackson tree comparison thường đơn giản và đủ rõ.

## 20. Những lỗi thường gặp khi so sánh JSON

### 20.1. So sánh raw string cho mọi test

Test thất bại vì indentation, newline hoặc property order dù dữ liệu giống nhau. Parse thành JsonNode và so sánh cấu trúc.

### 20.2. Bỏ qua thứ tự array không có chọn lọc

Array có thể biểu diễn workflow, thứ tự ưu tiên hoặc lịch sử. Chỉ chuẩn hóa array khi contract nói thứ tự không quan trọng.

### 20.3. Không phân biệt null với missing

Field có null và field không tồn tại có thể mang nghĩa khác nhau. Dùng has(), hasNonNull(), isNull() và isMissingNode().

### 20.4. So sánh số bằng asText()

Cách này có thể làm number và string trông giống nhau. Kiểm tra isNumber()/isTextual() rồi dùng decimalValue() hoặc kiểu số phù hợp.

### 20.5. Dùng equals() của BigDecimal mà quên scale

BigDecimal.equals() xét scale. Nếu chỉ quan tâm giá trị số, dùng compareTo().

### 20.6. Bỏ qua field dư trong test contract

Nếu expected tree chỉ là subset hoặc test dùng chế độ lenient, serializer có thể vô tình thêm field nhạy cảm mà test không phát hiện. Dùng full-tree equality cho contract test.

### 20.7. Chỉ test round-trip

Serializer và deserializer có thể cùng hiểu sai contract theo một cách nhất quán. Kiểm tra từng chiều độc lập bằng expected JSON và expected domain values.

### 20.8. Không kiểm tra duplicate keys

Sau khi parse thành tree, duplicate key có thể đã bị xử lý. Bật strict duplicate detection nếu input không cho phép key trùng.

### 20.9. Dùng helper normalize quá rộng

Helper tự động xóa null, sort mọi array hoặc bỏ field không biết có thể che giấu lỗi thật. Mỗi quy tắc normalization phải gắn với một contract cụ thể.

### 20.10. Dùng structural equality cho bài toán canonical bytes

Hai tree bằng nhau không đồng nghĩa chuỗi/byte giống nhau. Nếu chữ ký số hoặc hash phụ thuộc byte, dùng canonicalization chuẩn và byte comparison riêng.

## 21. Một bộ test mẫu cho contract JSON

Ví dụ một response có field biến động requestId, array lines có thứ tự theo contract và amount cần so sánh theo giá trị decimal:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;

import static org.junit.jupiter.api.Assertions.*;

class OrderResponseJsonTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void writesStableOrderContract() throws Exception {
        OrderResponse response = createResponse();

        String json = mapper.writeValueAsString(response);
        JsonNode actual = mapper.readTree(json);
        JsonNode expected = mapper.readTree("""
                {
                  "orderId": "ORD-42",
                  "status": "PAID",
                  "amount": 1250.50,
                  "lines": [
                    {"code": "P-1", "quantity": 2},
                    {"code": "P-2", "quantity": 1}
                  ],
                  "requestId": "ignored-in-this-assertion"
                }
                """);

        ObjectNode expectedComparable = expected.deepCopy();
        ObjectNode actualComparable = actual.deepCopy();

        expectedComparable.remove("requestId");
        actualComparable.remove("requestId");

        assertEquals(expectedComparable, actualComparable);

        JsonNode amount = actual.path("amount");
        assertTrue(amount.isNumber());
        assertEquals(
                0,
                new BigDecimal("1250.50").compareTo(amount.decimalValue())
        );

        assertTrue(actual.path("lines").isArray());
        assertEquals("P-1", actual.at("/lines/0/code").textValue());
        assertEquals("P-2", actual.at("/lines/1/code").textValue());
    }
}
~~~

Đây là minh họa cho cách kết hợp full-tree equality sau khi loại field biến động có chủ đích với assertion riêng cho numeric semantics và thứ tự array. Trong code thực tế, helper có thể nhận field ignore theo danh sách cố định và kiểm tra root node đúng loại trước khi cast sang ObjectNode.

Không nên copy nguyên helper bỏ field cho mọi endpoint. Một response có thể cần kiểm tra requestId có mặt và đúng format, dù giá trị không cố định. Hãy assertion riêng cho field đó trước hoặc sau phép so sánh normalized.

## 22. Chuẩn hóa JSON trước khi so sánh: làm có chủ đích

Normalization là bước biến hai representation về cùng một quy ước trước khi so sánh. Một số phép chuẩn hóa hợp lý khi contract cho phép:

- Bỏ field thời gian sinh tự động khỏi phép so sánh chính và kiểm tra riêng format.
- Sort một array được định nghĩa là tập hợp theo khóa ổn định.
- So sánh số bằng BigDecimal.compareTo() cho một field tiền.
- Chuẩn hóa Unicode theo NFC nếu contract quy định.
- Chuyển timezone về UTC nếu contract quy định thời điểm tuyệt đối theo UTC.

Những phép chuẩn hóa không nên áp dụng tùy tiện:

- Xóa tất cả field null.
- Xóa mọi field không có trong expected.
- Sort tất cả array.
- Chuyển tất cả number thành string.
- Trim mọi string.
- Chuyển mọi missing field thành null.

Các thao tác đó có thể làm mất khác biệt mà consumer thực sự quan sát được. Normalization nên được đặt tên theo contract, ví dụ normalizeUnorderedPermissions(), chứ không phải một hàm normalizeJson() tổng quát không có chính sách rõ ràng.

## 23. Cây JSON không phải văn bản JSON canonical

Sau khi parse, JsonNode giữ cấu trúc dữ liệu để so sánh. Nó không bảo toàn chính xác cách viết ban đầu:

- Khoảng trắng và xuống dòng bị loại bỏ.
- Object member order không phải mục tiêu so sánh.
- Escape sequence được giải mã.
- Cách viết số có thể được parse thành numeric node.
- Comment không thuộc JSON chuẩn và không nằm trong tree.
- Duplicate key có thể bị xử lý ở parser trước khi tree được tạo.

Vì vậy, tree equality phù hợp với kiểm thử semantics. Nó không phù hợp để chứng minh hai file giống hệt từng byte, bảo toàn format nguồn hoặc tạo chữ ký trên văn bản gốc.

Nếu cần giữ raw input để audit, lưu byte/string gốc riêng cùng với kết quả parse. Nếu cần canonical output, dùng một quy trình canonicalization riêng và test theo chuẩn đã chọn.

## 24. Quy trình viết test so sánh JSON

Khi kiểm tra output hoặc input của Jackson, có thể đi theo các bước:

1. **Xác định mục tiêu:** test semantics của JSON hay byte/text format?
2. **Viết expected JSON rõ ràng:** dùng text block để dễ đọc.
3. **Parse expected và actual:** dùng cùng parser policy phù hợp.
4. **So sánh toàn tree:** dùng JUnit assertEquals với JsonNode khi contract cần chính xác toàn bộ.
5. **Kiểm tra khác biệt có chủ đích:** array order, numeric precision, null/missing và field biến động.
6. **Dùng JSON Pointer cho subtree:** tránh lặp code truy cập nested path.
7. **Chỉ normalize theo contract:** không bỏ qua field hoặc sort array toàn cục.
8. **Kiểm tra duplicate key:** bật strict detection cho input nếu key trùng bị cấm.
9. **Tách serializer/deserializer test:** tránh chỉ dựa vào round-trip.
10. **Dùng text/byte comparison riêng:** chỉ khi thứ tự, whitespace hoặc canonical bytes thật sự là yêu cầu.

## 25. Chọn phương pháp theo mục tiêu

| Mục tiêu kiểm thử | Phương pháp phù hợp |
|---|---|
| Bỏ qua whitespace và thứ tự object member | Parse thành JsonNode rồi assertEquals |
| Kiểm tra toàn bộ response contract, gồm field dư/thiếu | Full-tree equality |
| Kiểm tra một field/subtree | JSON Pointer hoặc assertion trực tiếp |
| Kiểm tra null khác missing | has(), hasNonNull(), isNull(), isMissingNode() |
| Kiểm tra kiểu JSON | isTextual(), isNumber(), isBoolean(), isArray(), isObject() |
| Array có thứ tự nghiệp vụ | Tree equality theo index |
| Array được contract định nghĩa là tập hợp | Normalize theo khóa hoặc so sánh Set/Map có kiểm tra duplicate |
| Số thập phân theo giá trị toán học | decimalValue() và BigDecimal.compareTo() |
| Bỏ qua field biến động | deepCopy() rồi remove đúng field; assertion riêng nếu cần |
| Phát hiện duplicate object key | StreamReadFeature.STRICT_DUPLICATE_DETECTION |
| Kiểm tra format byte/canonical signature | Canonicalization chuẩn hoặc byte comparison riêng |
| Test cả chiều ghi và chiều đọc | Serializer contract test, deserializer behavior test và round-trip bổ sung |

## 26. Kết luận

JSON là cấu trúc dữ liệu, vì vậy phần lớn kiểm thử Jackson nên so sánh cấu trúc thay vì so sánh raw string. Parse expected và actual bằng Jackson thành JsonNode rồi dùng equality để bỏ qua whitespace, escape presentation và thứ tự object member trong khi vẫn kiểm tra đệ quy các giá trị, kiểu node và array order. Với array được định nghĩa là tập hợp, hãy chuẩn hóa theo khóa nghiệp vụ tại đúng path; với số cần so sánh theo giá trị toán học, dùng BigDecimal.compareTo(); với field biến động, loại khỏi bản sao tree và kiểm tra riêng nếu contract yêu cầu.

Hãy luôn phân biệt null với missing, string với number, object với array và thứ tự array có ý nghĩa với thứ tự không có ý nghĩa. Full-tree equality phù hợp cho contract test chặt; JSON Pointer và assertion theo field phù hợp cho test tập trung. Bật strict duplicate detection nếu key trùng không được phép, tách test serializer khỏi deserializer và chỉ so sánh chuỗi/byte khi format văn bản hoặc canonical bytes thật sự là một phần của hợp đồng.

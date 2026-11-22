# Thiết kế chính sách xử lý tên thuộc tính trùng

## 1. Tên thuộc tính trùng trong JSON là gì?

Một JSON object là tập các cặp tên và giá trị. Ví dụ:

~~~json
{
  "id": "U-10",
  "name": "Lan"
}
~~~

Tên thuộc tính (member name) nên duy nhất trong cùng một object. RFC 8259 khuyến nghị tên trong object là duy nhất; nếu một object chứa cùng tên nhiều lần, hành vi của các parser khác nhau có thể không thống nhất. Có parser giữ giá trị đầu, parser giữ giá trị cuối, parser báo lỗi hoặc xử lý theo cách riêng.

Ví dụ:

~~~json
{
  "role": "reader",
  "role": "administrator"
}
~~~

Payload này có hai giá trị cho cùng tên role. Nếu một lớp Java chỉ có một property role, ứng dụng không thể biểu diễn đồng thời cả hai giá trị theo cách binding thông thường. Kết quả có thể phụ thuộc parser và thứ tự xử lý.

Đây không chỉ là vấn đề định dạng. Nếu một lớp bảo vệ kiểm tra giá trị đầu tiên nhưng backend dùng giá trị cuối cùng, hai thành phần có thể hiểu cùng một request theo hai cách khác nhau. Với field điều khiển quyền, giá tiền, trạng thái hoặc chữ ký, sự khác biệt này có thể trở thành lỗ hổng bảo mật.

**Chính sách an toàn thường là từ chối object có tên thuộc tính trùng ngay tại ranh giới tiếp nhận dữ liệu.**

## 2. Jackson có bật phát hiện tên trùng mặc định không?

Jackson Core có tính năng phát hiện tên field trùng ở tầng parser:

~~~java
StreamReadFeature.STRICT_DUPLICATE_DETECTION
~~~

Tính năng này không được bật mặc định trong cấu hình thông thường vì nó cần lưu các tên đã gặp trong từng object để so sánh. Khi bật, parser ném lỗi ngay khi gặp tên thứ hai trùng với một tên đã xuất hiện trong cùng object.

Có thể bật khi tạo JsonFactory:

~~~java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.StreamReadFeature;
import com.fasterxml.jackson.databind.ObjectMapper;

JsonFactory factory = JsonFactory.builder()
        .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
        .build();

ObjectMapper mapper = new ObjectMapper(factory);
~~~

ObjectMapper sử dụng factory này cho các thao tác đọc JSON. Vì phát hiện diễn ra ở tầng parser, chính sách áp dụng trước khi dữ liệu được ánh xạ thành POJO, Map hoặc JsonNode.

Ví dụ:

~~~java
String json = """
        {
          "role": "reader",
          "role": "administrator"
        }
        """;

JsonNode result = mapper.readTree(json);
~~~

Lần đọc sẽ thất bại khi parser gặp lần xuất hiện thứ hai của role. Jackson không tiếp tục để một giá trị âm thầm ghi đè giá trị còn lại.

## 3. Bật strict duplicate detection cho toàn bộ mapper

Nếu ứng dụng dùng nhiều kiểu đích, hãy cấu hình JsonFactory trước khi tạo ObjectMapper dùng chung:

~~~java
public final class JsonConfiguration {
    private JsonConfiguration() {
    }

    public static ObjectMapper createStrictMapper() {
        JsonFactory factory = JsonFactory.builder()
                .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
                .build();

        return new ObjectMapper(factory);
    }
}
~~~

Mapper này áp dụng phát hiện trùng cho:

- Đọc trực tiếp vào POJO bằng readValue().
- Đọc thành cây JSON bằng readTree().
- Đọc thành Map hoặc collection.
- Đọc các object lồng nhau.
- Đọc dữ liệu qua JsonParser được tạo từ cùng JsonFactory.

Tính năng nằm ở parser nên không phụ thuộc việc property có được khai báo trong lớp Java hay không. Một tên lặp lại vẫn bị phát hiện dù đó là unknown property.

Hãy cấu hình factory trước khi mapper được sử dụng và chia sẻ mapper đã cấu hình xong. Không nên bật/tắt parser feature tùy tiện trong lúc xử lý request đồng thời.

## 4. Phân biệt parser-level detection và tree-only detection

Jackson Databind còn có feature:

~~~java
DeserializationFeature.FAIL_ON_READING_DUP_TREE_KEY
~~~

Feature này yêu cầu JsonNode deserializer báo lỗi khi đọc duplicate key vào Tree Model. Ví dụ:

~~~java
ObjectMapper treeStrictMapper = JsonMapper.builder()
        .enable(DeserializationFeature.FAIL_ON_READING_DUP_TREE_KEY)
        .build();
~~~

Hai cơ chế khác nhau về phạm vi:

| Cơ chế | Phạm vi |
|---|---|
| StreamReadFeature.STRICT_DUPLICATE_DETECTION | Phát hiện ở tầng parser, áp dụng cho các kiểu dữ liệu được đọc qua parser đó |
| FAIL_ON_READING_DUP_TREE_KEY | Kiểm tra duplicate key khi Jackson tạo JsonNode |

Nếu ứng dụng chỉ đọc JSON thành JsonNode, feature tree-specific có thể hữu ích. Nếu cùng một đầu vào có thể được đọc thành POJO, Map hoặc Tree Model ở nhiều nơi, parser-level strict detection tạo chính sách nhất quán hơn.

Có thể bật cả hai nếu muốn phòng vệ rõ ràng cho cả parser và Tree Model, nhưng không cần bật tree-only feature để thay thế parser-level detection trong một mapper đã dùng strict parser.

## 5. Duplicate detection áp dụng trong từng object

Tên giống nhau ở hai object khác nhau không phải duplicate:

~~~json
{
  "primary": {
    "id": 1,
    "name": "Lan"
  },
  "secondary": {
    "id": 2,
    "name": "Minh"
  }
}
~~~

Các object primary và secondary đều có field id và name. Đây là cấu trúc hợp lệ vì tên chỉ cần duy nhất trong từng object.

Tương tự, các phần tử của array có thể dùng cùng tên field:

~~~json
[
  {"id": 1, "name": "Lan"},
  {"id": 2, "name": "Minh"}
]
~~~

Parser duy trì trạng thái duplicate detection riêng cho mỗi object đang mở. Khi object kết thúc, phạm vi tên của object đó kết thúc. Vì vậy, strict mode không cấm các DTO trong cùng một danh sách dùng chung tên property.

## 6. Object lồng nhau cũng cần được kiểm tra

Duplicate có thể nằm sâu trong cấu trúc:

~~~json
{
  "user": {
    "id": "U-10",
    "permissions": {
      "read": true,
      "read": false
    }
  }
}
~~~

Tên read bị lặp trong object permissions. Nếu chỉ kiểm tra các field cấp cao bằng code ứng dụng, lỗi ở object con có thể bị bỏ sót. Strict duplicate detection ở tầng parser theo dõi mọi object trong luồng, nên có thể phát hiện duplicate ở bất kỳ độ sâu nào.

Hãy kiểm thử cả duplicate ở root và duplicate trong object lồng nhau. Một chính sách bảo mật nên áp dụng nhất quán cho toàn bộ tài liệu.

## 7. Tên escape trong JSON

JSON cho phép biểu diễn ký tự trong tên property bằng escape sequence Unicode. Hai cách viết văn bản khác nhau có thể tạo ra cùng một tên sau khi parser giải mã:

~~~json
{
  "role": "reader",
  "ro\u006ce": "administrator"
}
~~~

Trong JSON trên, chuỗi escape \u006c biểu diễn chữ l. Sau khi giải mã, cả hai tên đều là role.

Jackson parser xử lý escape trong tên field trước khi ứng dụng binding property. Strict duplicate detection có thể nhận ra hai tên sau giải mã là trùng nhau. Nên có test trên đúng phiên bản Jackson đang dùng để khóa hành vi này trong hợp đồng bảo mật.

Không nên chỉ tìm chuỗi tên lặp trong raw text bằng regex. Cách viết escape, khoảng trắng, string và nesting khiến việc so khớp văn bản thô không đủ để hiểu cấu trúc JSON.

## 8. Tree Model có thể che giấu duplicate nếu không kiểm tra trước

Nếu duplicate detection không được bật, Tree Model lưu object trong một cấu trúc key-value. Một key không thể giữ hai value độc lập theo cách ObjectNode thông thường. Khi parse JSON có duplicate key, giá trị sau có thể ghi đè giá trị trước trong cây.

Ví dụ:

~~~java
ObjectMapper mapper = new ObjectMapper();

JsonNode root = mapper.readTree("""
        {
          "role": "reader",
          "role": "administrator"
        }
        """);

System.out.println(root.path("role").asText());
~~~

Sau khi cây đã được tạo, ứng dụng có thể chỉ còn nhìn thấy một giá trị role. Thông tin rằng tên này từng xuất hiện hai lần không còn được biểu diễn trong JsonNode thông thường.

Vì vậy, không nên parse bằng mapper permissive rồi mới tìm duplicate trong JsonNode. Lúc đó dữ liệu cần phát hiện có thể đã bị mất. Hãy bật strict detection trên parser trước khi tạo cây hoặc bind POJO.

## 9. POJO và Map cũng không phải nơi phù hợp để quyết định duplicate

Khi duplicate detection tắt, Jackson có thể gán cùng một property nhiều lần theo thứ tự token. Với bean mutable, setter có thể được gọi nhiều lần; với Map, một key có thể bị ghi đè. Kết quả thường mang semantics “giá trị sau thắng”, nhưng không nên dựa vào hành vi này như một hợp đồng an toàn.

Ví dụ:

~~~json
{
  "limit": 10,
  "limit": 1000000
}
~~~

Một lớp Java có field limit có thể kết thúc với giá trị 1000000 nếu lần gán sau ghi đè. Một gateway, validator hoặc thư viện khác có thể chọn giá trị đầu. Nếu các tầng không thống nhất, request có thể vượt qua kiểm tra ở tầng này nhưng được thực thi với giá trị khác ở tầng sau.

Chính sách duplicate nên được áp dụng trước khi dữ liệu đi vào các object có side effect hoặc logic phân quyền.

## 10. Strict parser detection không phát hiện mọi xung đột property

Có một trường hợp tinh vi: hai tên JSON khác nhau có thể ánh xạ vào cùng một property Java.

Ví dụ:

~~~java
public class AccessRequest {
    @JsonProperty("accessRole")
    @JsonAlias("role")
    private String accessRole;

    public String getAccessRole() {
        return accessRole;
    }

    public void setAccessRole(String accessRole) {
        this.accessRole = accessRole;
    }
}
~~~

Payload:

~~~json
{
  "accessRole": "reader",
  "role": "administrator"
}
~~~

Tên accessRole và role khác nhau ở cấp JSON. Vì vậy, parser-level duplicate detection không xem đây là duplicate key. Tuy nhiên, cả hai đều ánh xạ vào một property Java.

Đây là **xung đột property sau chuẩn hóa (semantic property collision)**. Nó có thể xảy ra do:

- @JsonAlias.
- MapperFeature.ACCEPT_CASE_INSENSITIVE_PROPERTIES.
- PropertyNamingStrategy hoặc PropertyNamingStrategies.
- Custom deserializer tự chuẩn hóa tên.
- Quy tắc chuyển đổi Unicode hoặc tên field của một tầng trung gian.

Nếu hai tên có thể cùng ánh xạ vào một giá trị nghiệp vụ nhạy cảm, cần kiểm tra xung đột ở tầng binding/schema chứ không chỉ dựa vào strict duplicate detection.

## 11. Phát hiện xung đột giữa tên chính và alias

Với một số DTO đã biết, có thể kiểm tra cả hai key trước khi bind:

~~~java
JsonNode root = mapper.readTree(json);

if (root.has("accessRole") && root.has("role")) {
    throw new IllegalArgumentException(
            "Send either accessRole or role, not both"
    );
}

AccessRequest request =
        mapper.treeToValue(root, AccessRequest.class);
~~~

Cách này đơn giản khi số alias ít và schema rõ ràng. Nếu payload có nhiều alias hoặc object lồng nhau, hãy tạo một bước validation theo schema để ánh xạ từng tên JSON về tên property canonical rồi phát hiện nhiều nguồn cùng ghi vào một property.

Một quy tắc tốt:

- Chấp nhận một tên canonical hoặc một alias cho mỗi logical property.
- Từ chối nếu có nhiều tên cùng xuất hiện trong một object.
- Nếu cần hỗ trợ payload gửi cả hai tên, quy định rõ chúng phải có giá trị giống nhau và kiểm tra điều đó trước khi binding.

Không nên để thứ tự field quyết định alias nào thắng. Cũng không nên tự động chọn tên canonical mà không báo lỗi nếu alias còn lại mang giá trị mâu thuẫn.

## 12. Case-insensitive matching tạo thêm va chạm

Jackson có thể bật nhận diện tên property không phân biệt chữ hoa/chữ thường:

~~~java
ObjectMapper mapper = JsonMapper.builder()
        .enable(MapperFeature.ACCEPT_CASE_INSENSITIVE_PROPERTIES)
        .build();
~~~

Khi đó, các tên JSON như role, Role và ROLE có thể cùng ánh xạ đến property role của bean.

Strict duplicate detection ở tầng parser so sánh tên field trong object theo tên đã được parser giải mã; nó không đồng nghĩa với việc áp dụng toàn bộ quy tắc case-insensitive của Databind. Vì vậy, role và ROLE có thể không phải duplicate ở parser nhưng vẫn là hai input cùng nhắm đến một property Java.

Nếu bật case-insensitive matching:

- Cân nhắc có thật sự cần thiết cho hợp đồng hay không.
- Kiểm tra các tên khác nhau chỉ khác chữ hoa/chữ thường.
- Không dùng nó như cách sửa lỗi client gửi sai casing mà không có kế hoạch.
- Bổ sung semantic collision detection cho các property nhạy cảm.

## 13. Chọn chính sách: reject, first-wins hay last-wins?

Có ba cách xử lý phổ biến:

| Chính sách | Hành vi | Đánh giá |
|---|---|---|
| Reject | Từ chối object khi phát hiện tên trùng | Khuyến nghị cho API và dữ liệu không đáng tin cậy |
| First-wins | Giữ giá trị xuất hiện đầu tiên | Có thể gây khác biệt với parser khác |
| Last-wins | Giữ giá trị xuất hiện cuối cùng | Dễ xảy ra ghi đè ngoài ý muốn và parser differential |

### Reject

Reject làm hợp đồng rõ ràng: một property chỉ được xuất hiện một lần trong cùng object. Client gửi payload mơ hồ nhận lỗi ngay tại ranh giới đầu vào.

Đây thường là lựa chọn phù hợp cho:

- Field phân quyền hoặc danh tính.
- Giá trị tiền, số lượng, trạng thái giao dịch.
- Request có chữ ký hoặc được xác thực qua nhiều tầng.
- Message đi qua gateway, proxy và backend khác nhau.
- Dữ liệu lưu trữ cần replay nhất quán.

### First-wins và last-wins

Hai chính sách này chỉ nên dùng khi một giao thức legacy đã quy định rõ và tất cả thành phần tham gia đều thực hiện cùng một quy tắc. Jackson strict duplicate detection không cung cấp lựa chọn first-wins hoặc last-wins; nó là cơ chế reject.

Nếu buộc phải hỗ trợ semantics cũ, hãy triển khai một parser/adapter có chủ đích, ghi lại hành vi bằng test và không để các thành phần khác tự chọn cách diễn giải. Không nên dùng Tree Model mặc định rồi giả định đó là một hợp đồng portable.

## 14. Vì sao duplicate names là vấn đề bảo mật?

Duplicate property names có thể tạo ra cách hiểu khác nhau giữa các tầng:

~~~text
Client gửi JSON có hai field role
             |
             v
Gateway / WAF đọc theo quy tắc A
             |
             v
Backend Jackson đọc theo quy tắc B
             |
             v
Logic phân quyền dùng một giá trị khác
~~~

Một số tình huống cần chú ý:

- **Authorization:** một tầng thấy role = reader, tầng khác thấy role = administrator.
- **Giá trị giới hạn:** validator kiểm tra limit nhỏ nhưng service thực thi limit lớn.
- **Định tuyến:** proxy chọn tenant hoặc endpoint theo một field, backend chọn theo field còn lại.
- **Chữ ký số:** bước canonicalization và bước xử lý nghiệp vụ có thể hiểu payload khác nhau nếu duplicate không được quy định.
- **Audit:** log lưu một giá trị nhưng logic thực thi dùng giá trị khác.

Đây là nhóm rủi ro parser differential hoặc request interpretation mismatch. Không cần một parser cụ thể bị lỗi; chỉ cần các thành phần hợp lệ nhưng có quy tắc duplicate khác nhau.

Với request được ký, bên xác minh chữ ký và bên thực thi phải dùng cùng một quy tắc canonicalization. Cách đơn giản và an toàn là từ chối duplicate trước khi chuyển payload sang các tầng diễn giải khác nhau, đồng thời xác định rõ thứ tự xác minh chữ ký theo giao thức.

## 15. Chính sách cho dữ liệu đầu vào không đáng tin cậy

Một chính sách đầu vào nghiêm ngặt thường gồm:

1. Giới hạn kích thước body và độ sâu JSON.
2. Bật strict duplicate detection ở JsonFactory.
3. Kiểm tra schema, kiểu dữ liệu và property bắt buộc.
4. Phát hiện semantic collision do alias, case-insensitive matching hoặc naming strategy.
5. Chỉ sau đó mới chuyển thành domain object và thực hiện side effect.
6. Ghi nhận lỗi bằng error code và vị trí, không ghi raw payload nhạy cảm vào log.

Không nên để dữ liệu có tên trùng đi sâu vào hệ thống rồi mới kiểm tra ở tầng nghiệp vụ. Lúc đó một số thành phần có thể đã đọc và sử dụng giá trị khác nhau.

## 16. Chi phí của strict duplicate detection

Strict duplicate detection cần lưu tên field đã gặp trong mỗi object đang mở. Điều này tạo thêm chi phí bộ nhớ và CPU so với parser không kiểm tra duplicate.

Chi phí phụ thuộc:

- Số lượng field trong mỗi object.
- Độ sâu lồng nhau.
- Số object được parse.
- Độ dài và số lượng tên property khác nhau.
- Kích thước tài liệu và tốc độ xử lý.

Với object rất lớn có hàng chục nghìn field, tập tên đã gặp có thể chiếm bộ nhớ đáng kể. Tuy nhiên, với request JSON thông thường, chi phí thường là một đánh đổi hợp lý để có semantics rõ ràng.

Không nên tắt strict detection trên toàn hệ thống chỉ vì một benchmark nhỏ cho thấy overhead. Hãy đo trên payload thực tế, đặt giới hạn kích thước/độ sâu và chỉ dùng chính sách permissive ở ranh giới đã có hợp đồng legacy cụ thể.

## 17. Kiểm thử duplicate detection

Một bộ test nên bao gồm duplicate ở nhiều cấp, tên escape và trường hợp hợp lệ có cùng tên ở các object khác nhau.

Ví dụ JUnit:

~~~java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.StreamReadFeature;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonMapper;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class DuplicatePropertyTest {
    private final ObjectMapper strictMapper = new ObjectMapper(
            JsonFactory.builder()
                    .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
                    .build()
    );

    @Test
    void rejectsDuplicateTopLevelName() {
        String json = """
                {
                  "role": "reader",
                  "role": "administrator"
                }
                """;

        assertThrows(
                JsonProcessingException.class,
                () -> strictMapper.readTree(json)
        );
    }

    @Test
    void rejectsDuplicateNameInsideNestedObject() {
        String json = """
                {
                  "user": {
                    "id": 1,
                    "id": 2
                  }
                }
                """;

        assertThrows(
                JsonProcessingException.class,
                () -> strictMapper.readTree(json)
        );
    }

    @Test
    void allowsSameNameInDifferentObjects() throws Exception {
        String json = """
                [
                  {"id": 1},
                  {"id": 2}
                ]
                """;

        assertEquals(2, strictMapper.readTree(json).size());
    }

    @Test
    void rejectsDuplicateAfterJsonEscapeIsDecoded() {
        String json = """
                {
                  "role": "reader",
                  "ro\\u006ce": "administrator"
                }
                """;

        assertThrows(
                JsonProcessingException.class,
                () -> strictMapper.readTree(json)
        );
    }
}
~~~

Test cuối dùng escape trong JSON text block. Khi parser giải mã tên field, hai tên trở thành cùng một chuỗi. Chạy test với đúng phiên bản Jackson của ứng dụng để bảo đảm cấu hình và hành vi parser được khóa bằng kiểm thử.

### Kiểm thử semantic collision do alias

Strict parser không phát hiện hai tên khác nhau cùng ánh xạ vào một property:

~~~java
String json = """
        {
          "accessRole": "reader",
          "role": "administrator"
        }
        """;

JsonNode root = strictMapper.readTree(json);

assertTrue(root.has("accessRole"));
assertTrue(root.has("role"));

if (root.has("accessRole") && root.has("role")) {
    throw new IllegalArgumentException(
            "Conflicting names for accessRole"
    );
}
~~~

Đây là test cho bước schema validation bổ sung. Nó minh họa rằng parser-level duplicate detection và logical-property collision detection giải quyết hai lớp vấn đề khác nhau.

## 18. Xử lý lỗi và trả phản hồi cho client

Duplicate property là lỗi cú pháp/hợp đồng đầu vào. API nên trả lỗi 4xx phù hợp, thường là 400 Bad Request, thay vì tiếp tục xử lý với một giá trị tùy ý.

Thông tin lỗi có thể gồm:

- Error code ổn định, ví dụ DUPLICATE_JSON_PROPERTY.
- Tên property nếu an toàn để hiển thị.
- Vị trí dòng/cột hoặc byte offset nếu parser cung cấp.
- Correlation ID để tra cứu log.

Không nên phản hồi toàn bộ payload trong error message. Request có thể chứa mật khẩu, token, thông tin cá nhân hoặc dữ liệu bí mật. Log cũng cần tránh ghi raw payload nếu không có chính sách bảo vệ.

Ở tầng ứng dụng, có thể bắt JsonProcessingException hoặc JsonParseException tại boundary và chuyển thành lỗi request không hợp lệ. Không nên catch rồi bỏ qua lỗi duplicate để tiếp tục gọi service.

## 19. Chính sách khi phải hỗ trợ hệ thống legacy

Nếu một producer cũ thực sự gửi duplicate property và không thể nâng cấp ngay, hãy xử lý như một migration có thời hạn:

1. Xác định producer nào phát duplicate và field nào bị lặp.
2. Kiểm tra hai giá trị có luôn giống nhau hay có trường hợp mâu thuẫn.
3. Chọn quy tắc tạm thời theo hợp đồng legacy và thực hiện tại một adapter cô lập.
4. Ghi metric số payload duplicate, không ghi giá trị nhạy cảm.
5. Yêu cầu producer sửa payload.
6. Sau thời hạn chuyển tiếp, bật strict rejection ở ranh giới chính.
7. Xóa adapter permissive khi không còn nguồn gửi cũ.

Nếu buộc phải dùng first-wins hoặc last-wins, mọi tầng trung gian, validator, signature verifier và backend phải tuân theo đúng một quy tắc. Đây vẫn là giải pháp tạm thời có rủi ro; không nên mở rộng nó thành chuẩn chung cho API mới.

## 20. Checklist thiết kế chính sách

Trước khi đưa một endpoint hoặc consumer vào production, hãy xác nhận:

- [ ] JsonFactory bật STRICT_DUPLICATE_DETECTION ở ranh giới nhận dữ liệu.
- [ ] Các test xác nhận duplicate ở root và object lồng nhau bị từ chối.
- [ ] Tên field có escape được kiểm thử.
- [ ] Cùng tên ở hai object khác nhau vẫn được chấp nhận.
- [ ] Alias và tên canonical không thể cùng ghi một logical property mà không bị phát hiện.
- [ ] Case-insensitive matching và naming strategy đã được xem xét.
- [ ] Parser, gateway, signature verifier và backend dùng semantics tương thích.
- [ ] Duplicate tạo lỗi request rõ ràng và không thực hiện side effect.
- [ ] Log không làm lộ raw payload nhạy cảm.
- [ ] Kích thước body và độ sâu JSON có giới hạn.
- [ ] Ngoại lệ legacy, nếu có, có chủ sở hữu và thời điểm loại bỏ.

## 21. Kết luận

Tên thuộc tính trùng khiến một JSON object có nhiều cách diễn giải và có thể tạo khác biệt giữa gateway, validator, signature verifier và backend. Jackson cung cấp StreamReadFeature.STRICT_DUPLICATE_DETECTION để từ chối tên lặp ở tầng parser; đây là chính sách phù hợp cho phần lớn dữ liệu đầu vào không đáng tin cậy. FAIL_ON_READING_DUP_TREE_KEY chỉ bổ sung kiểm tra cho Tree Model. Cần nhớ parser-level detection không phát hiện hai tên khác nhau cùng ánh xạ vào một property do @JsonAlias, case-insensitive matching hoặc naming strategy; những va chạm này cần validation theo schema. Không nên dựa vào first-wins hoặc last-wins ngầm định. Hãy từ chối payload mơ hồ, kiểm thử các trường hợp escape và lồng nhau, giới hạn tài nguyên và áp dụng cùng một quy tắc ở mọi tầng xử lý dữ liệu.

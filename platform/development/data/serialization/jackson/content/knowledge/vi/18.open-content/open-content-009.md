# Kiểm thử nhập lại dữ liệu có thuộc tính chưa được phiên bản hiện tại biết

## 1. Bài toán tương thích khi cấu trúc JSON phát triển

Một hệ thống thường có nhiều phiên bản chạy đồng thời. Dịch vụ mới có thể bổ sung thuộc tính vào JSON response, trong khi một consumer cũ vẫn đang dùng lớp Java chưa khai báo thuộc tính đó. Khi consumer cũ đọc lại dữ liệu mới, Jackson phải quyết định cách xử lý property chưa biết.

Ví dụ, phiên bản đầu của ứng dụng có mô hình:

    public class Customer {
        private String id;
        private String name;
        // getters/setters
    }

Payload của phiên bản sau bổ sung thuộc tính loyaltyLevel:

    {
      "id": "C-100",
      "name": "Lan",
      "loyaltyLevel": "GOLD"
    }

Lớp Customer cũ không có property loyaltyLevel. Tình huống này thường được gọi là **unknown property** hoặc thuộc tính chưa được phiên bản hiện tại biết.

Đây là một vấn đề về khả năng tương thích tiến (forward compatibility): consumer cũ có thể tiếp tục đọc payload do producer mới tạo hay không? Ngoài câu hỏi đọc thành công, cần xác định thêm dữ liệu mới có bị mất khi ứng dụng đọc rồi ghi JSON trở lại hay không.

Có ba chính sách phổ biến:

1. **Từ chối thuộc tính chưa biết:** phát hiện payload không khớp mô hình hiện tại và báo lỗi.
2. **Bỏ qua thuộc tính chưa biết:** đọc phần dữ liệu đã biết, loại bỏ phần mới.
3. **Giữ lại thuộc tính chưa biết:** đọc các field đã biết vào mô hình Java và lưu những field còn lại để có thể ghi lại sau này.

Chọn chính sách nào phụ thuộc vào hợp đồng dữ liệu, mục tiêu tương thích và yêu cầu bảo toàn thông tin.

## 2. Hành vi mặc định của Jackson

Jackson Databind cung cấp feature DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES. Trong cấu hình mặc định của ObjectMapper, feature này được bật. Vì vậy, nếu JSON có một property không ánh xạ được vào kiểu đích và không có cơ chế xử lý property đó, Jackson thường ném UnrecognizedPropertyException.

Ví dụ:

    import com.fasterxml.jackson.databind.ObjectMapper;

    public class StrictReadExample {
        public static class Customer {
            public String id;
            public String name;
        }

        public static void main(String[] args) throws Exception {
            ObjectMapper mapper = new ObjectMapper();
            String json = """
                    {
                      "id": "C-100",
                      "name": "Lan",
                      "loyaltyLevel": "GOLD"
                    }
                    """;

            Customer customer = mapper.readValue(json, Customer.class);
        }
    }

Với cấu hình mặc định thông thường, lần đọc này thất bại vì Customer không có property loyaltyLevel. Jackson không tự đoán rằng thuộc tính mới nên được bỏ qua.

Hành vi nghiêm ngặt có ích trong các hệ thống mà schema phải khớp chính xác. Nó giúp phát hiện lỗi chính tả trong tên field, sai phiên bản payload hoặc producer gửi dữ liệu ngoài hợp đồng. Tuy nhiên, nó cũng khiến consumer cũ dễ bị ảnh hưởng khi producer chỉ bổ sung một field tùy chọn.

## 3. Kiểm tra và phân loại unknown property

Khi gặp lỗi, cần phân biệt property chưa được biết với property đã được nhận diện nhưng bị cấu hình bỏ qua:

| Trường hợp | Ý nghĩa | Cơ chế liên quan |
|---|---|---|
| Unknown property | Kiểu Java đích không khai báo hoặc không nhận diện tên field trong JSON | FAIL_ON_UNKNOWN_PROPERTIES |
| Ignored property | Jackson nhận diện property nhưng annotation hoặc cấu hình yêu cầu bỏ qua nó | FAIL_ON_IGNORED_PROPERTIES và các quy tắc ignore |
| Property được biết nhưng sai kiểu | Tên field hợp lệ nhưng giá trị JSON không thể ánh xạ sang kiểu Java | Lỗi deserialization/coercion tương ứng |
| Property bị thiếu | JSON không gửi một field mà mô hình có khai báo | Creator/validation/default value policy |

FAIL_ON_UNKNOWN_PROPERTIES và FAIL_ON_IGNORED_PROPERTIES không giải quyết cùng một tình huống. Tắt feature thứ nhất không đồng nghĩa mọi lỗi ánh xạ đều được bỏ qua; dữ liệu sai kiểu hoặc vi phạm quy tắc creator vẫn có thể làm quá trình đọc thất bại.

## 4. Bỏ qua thuộc tính mới bằng cấu hình mapper

Nếu ứng dụng chấp nhận payload có thêm field và không cần giữ các field đó, có thể tắt FAIL_ON_UNKNOWN_PROPERTIES:

    ObjectMapper tolerantMapper = new ObjectMapper()
            .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

Sau đó:

    Customer customer = tolerantMapper.readValue(json, Customer.class);

Jackson ánh xạ id và name; loyaltyLevel bị bỏ qua. Cách này phù hợp với consumer chỉ cần phần dữ liệu đã biết và không có yêu cầu ghi lại payload đầy đủ.

Ưu điểm:

- Thay đổi ít, có thể áp dụng nhanh cho một mapper.
- Consumer cũ tiếp tục đọc payload có thêm thuộc tính.
- Không cần sửa mọi lớp DTO khi schema bổ sung field tùy chọn.

Giới hạn:

- Field mới bị mất khỏi đối tượng Java.
- Nếu serialize Customer sau đó, loyaltyLevel sẽ không xuất hiện trong JSON.
- Lỗi chính tả của field trong payload cũng có thể bị bỏ qua, khiến dữ liệu không được ánh xạ mà không có cảnh báo.
- Nếu dùng mapper chung cho nhiều loại dữ liệu, chính sách lỏng có thể ảnh hưởng cả những payload cần được kiểm tra nghiêm ngặt.

Vì vậy, chỉ tắt feature toàn cục khi toàn bộ ứng dụng thực sự muốn áp dụng chính sách tolerant cho mọi kiểu đọc liên quan.

## 5. Bỏ qua unknown property ở cấp lớp

Nếu chỉ một DTO cần chấp nhận thuộc tính mới, có thể dùng annotation:

    import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

    @JsonIgnoreProperties(ignoreUnknown = true)
    public class Customer {
        private String id;
        private String name;

        public Customer() {
        }

        public String getId() {
            return id;
        }

        public void setId(String id) {
            this.id = id;
        }

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }
    }

Khi đọc JSON có loyaltyLevel, Jackson ánh xạ các property đã biết và bỏ qua property còn lại. Chính sách được đặt ngay trên kiểu Customer nên dễ nhìn thấy khi xem DTO.

So sánh hai cách:

| Cách cấu hình | Phạm vi ảnh hưởng | Khi phù hợp |
|---|---|---|
| Tắt FAIL_ON_UNKNOWN_PROPERTIES trên ObjectMapper | Mọi kiểu đọc dùng mapper đó, trừ trường hợp có cơ chế riêng | Ứng dụng có chính sách tolerant thống nhất |
| @JsonIgnoreProperties(ignoreUnknown = true) | Kiểu được annotation | Chỉ một số DTO được phép nhận field mới |

Annotation ignoreUnknown không lưu lại field bị bỏ qua. Nếu cần re-import rồi ghi lại payload mà vẫn bảo toàn field mới, cần một cơ chế lưu trữ khác.

## 6. Giữ lại thuộc tính chưa biết bằng @JsonAnySetter

Nếu consumer cũ cần đọc payload mới, chỉnh sửa phần dữ liệu đã biết rồi ghi lại mà không làm mất field mới, có thể thu thập các property chưa được nhận diện vào một Map.

Jackson cung cấp @JsonAnySetter để nhận những property còn lại. Có thể kết hợp @JsonAnyGetter để phát các property đó trở lại JSON khi serialization.

    import com.fasterxml.jackson.annotation.JsonAnyGetter;
    import com.fasterxml.jackson.annotation.JsonAnySetter;
    import com.fasterxml.jackson.annotation.JsonProperty;
    import com.fasterxml.jackson.databind.JsonNode;

    import java.util.LinkedHashMap;
    import java.util.Map;

    public class ExtensibleCustomer {
        private String id;
        private String name;

        private final Map<String, JsonNode> additionalProperties =
                new LinkedHashMap<>();

        public String getId() {
            return id;
        }

        public void setId(String id) {
            this.id = id;
        }

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }

        @JsonAnySetter
        public void captureUnknown(String propertyName, JsonNode value) {
            additionalProperties.put(propertyName, value);
        }

        @JsonAnyGetter
        public Map<String, JsonNode> additionalProperties() {
            return additionalProperties;
        }
    }

Trong ví dụ, các field đã biết id và name được ánh xạ vào thuộc tính thông thường. Các field chưa biết như loyaltyLevel, marketing hoặc preferences được giữ dưới dạng JsonNode trong additionalProperties.

Khi ghi lại:

    ObjectMapper mapper = new ObjectMapper();
    ExtensibleCustomer customer =
            mapper.readValue(json, ExtensibleCustomer.class);

    customer.setName("Lan Nguyen");

    String rewritten = mapper.writeValueAsString(customer);

JSON đầu ra chứa name đã cập nhật và các field chưa biết đã được giữ trong Map. Đây là lựa chọn phù hợp khi ứng dụng đóng vai trò trung gian: hiểu một phần schema nhưng cần chuyển tiếp phần còn lại.

### Vì sao dùng JsonNode cho giá trị mở rộng?

Nếu dùng Map<String, Object>, Jackson thường ánh xạ JSON value thành các kiểu Java tổng quát như String, Integer/Long/Double, Boolean, List hoặc Map. Cách này tiện nhưng có thể làm mất một số chi tiết kiểu hoặc khiến xử lý số phụ thuộc cấu hình.

Map<String, JsonNode> giữ cấu trúc JSON rõ ràng:

- Object lồng nhau vẫn là ObjectNode.
- Array vẫn là ArrayNode.
- String, number, boolean và null giữ loại node tương ứng.
- Có thể duyệt hoặc chỉnh sửa một field mở rộng bằng API Tree Model.

JsonNode giữ ý nghĩa cấu trúc và giá trị JSON, nhưng không giữ nguyên byte đầu vào, khoảng trắng, thứ tự văn bản ban đầu trong mọi tình huống hoặc cách escape gốc. Nếu cần bảo toàn nguyên văn tài liệu, phải lưu raw payload riêng.

## 7. Thao tác với field mở rộng sau khi nhập

Map bổ sung có thể được truy cập để đọc hoặc thay đổi một field mà phiên bản hiện tại chưa mô hình hóa thành property Java:

    JsonNode loyaltyLevel = customer.additionalProperties()
            .get("loyaltyLevel");

    if (loyaltyLevel != null && loyaltyLevel.isTextual()) {
        System.out.println(loyaltyLevel.asText());
    }

Có thể thay giá trị:

    customer.additionalProperties().put(
            "loyaltyLevel",
            mapper.getNodeFactory().textNode("PLATINUM")
    );

Hoặc xóa field:

    customer.additionalProperties().remove("marketing");

Nếu field mở rộng là object hoặc array, có thể kiểm tra kiểu node rồi dùng ObjectNode/ArrayNode để chỉnh sửa. Không nên ép kiểu trước khi xác nhận isObject() hoặc isArray().

### Tránh xung đột tên property

Không nên lưu một tên trong additionalProperties trùng với property đã biết như id hoặc name. Jackson xử lý các property đã khai báo theo cơ chế thông thường; any-setter dành cho những tên còn lại. Tuy nhiên, khi chương trình tự thêm dữ liệu vào Map, cần kiểm soát tên để không tạo JSON có field trùng hoặc gây hiểu nhầm cho consumer.

Có thể kiểm tra tên trước khi thêm:

    if ("id".equals(propertyName) || "name".equals(propertyName)) {
        throw new IllegalArgumentException(
                "Known property cannot be stored as an extension"
        );
    }

Đối với một schema mở lớn, nên định nghĩa quy tắc namespace hoặc prefix cho extension fields để giảm nguy cơ trùng tên khi các phiên bản tương lai bổ sung property mới.

## 8. Giữ dữ liệu mở bằng Tree Model

Nếu không cần ánh xạ vào POJO, có thể đọc toàn bộ payload thành JsonNode:

    JsonNode root = mapper.readTree(json);

Tree Model tự nhiên phù hợp với dữ liệu có cấu trúc thay đổi. Consumer có thể đọc các field mà nó hiểu, cập nhật chúng bằng ObjectNode, rồi ghi lại cây:

    ObjectNode customer = (ObjectNode) root;

    String id = customer.path("id").asText();
    customer.put("name", "Lan Nguyen");

    String rewritten = mapper.writeValueAsString(customer);

Các property khác như loyaltyLevel vẫn nằm trong cây vì ứng dụng không ánh xạ tài liệu vào một lớp chỉ chứa một tập field cố định. Đây là cách đơn giản để giữ những phần JSON mà phiên bản hiện tại chưa cần diễn giải.

Trước khi ép kiểu root sang ObjectNode, cần kiểm tra root không null và isObject(). JSON root cũng có thể là array, string, number, boolean hoặc null. Nếu hợp đồng yêu cầu object, hãy từ chối root không phù hợp thay vì ép kiểu mù quáng.

Tree Model giữ cấu trúc JSON trong bộ nhớ. Với payload lớn, cần cân nhắc chi phí dựng toàn bộ cây; có thể dùng Streaming API để xử lý từng phần tử và giữ lại riêng những nhánh cần thiết.

## 9. Kiểm thử đọc payload mới bằng mô hình cũ

Một phép thử tốt cần mô tả rõ phiên bản producer và consumer:

- Producer v1 tạo JSON chỉ có id và name.
- Producer v2 bổ sung loyaltyLevel và preferences.
- Consumer v1 chỉ biết id và name.
- Consumer v2 biết thêm các property mới.

Payload của producer v2:

    {
      "id": "C-100",
      "name": "Lan",
      "loyaltyLevel": "GOLD",
      "preferences": {
        "language": "vi",
        "notifications": true
      }
    }

Có thể tổ chức các ca thử:

| Ca | Cách đọc | Kết quả mong đợi |
|---|---|---|
| T01 | Consumer v1, mapper mặc định strict | Phát sinh lỗi unknown property |
| T02 | Consumer v1, tắt FAIL_ON_UNKNOWN_PROPERTIES | Đọc thành công; field mới bị bỏ |
| T03 | Consumer v1 có ignoreUnknown = true | Đọc thành công; field mới bị bỏ |
| T04 | Consumer extensible có @JsonAnySetter | Đọc thành công; field mới được lưu trong Map |
| T05 | Extensible model đọc rồi ghi lại | Field đã biết và field mở rộng đều có trong JSON |
| T06 | Tree Model đọc rồi ghi lại | Các field trong cây vẫn hiện diện về mặt cấu trúc |
| T07 | Payload có field đã biết nhưng sai kiểu | Vẫn phải xử lý lỗi kiểu theo chính sách; unknown-property tolerance không sửa lỗi này |

### Ví dụ kiểm thử bằng JUnit

    import com.fasterxml.jackson.databind.ObjectMapper;
    import com.fasterxml.jackson.databind.exc.UnrecognizedPropertyException;
    import org.junit.jupiter.api.Test;

    import static org.junit.jupiter.api.Assertions.*;

    class UnknownPropertyTest {
        private final ObjectMapper strictMapper = new ObjectMapper();

        private final ObjectMapper tolerantMapper = new ObjectMapper()
                .disable(
                        DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES
                );

        private static final String NEW_PAYLOAD = """
                {
                  "id": "C-100",
                  "name": "Lan",
                  "loyaltyLevel": "GOLD"
                }
                """;

        @Test
        void strictMapperRejectsUnknownProperty() {
            assertThrows(
                    UnrecognizedPropertyException.class,
                    () -> strictMapper.readValue(
                            NEW_PAYLOAD,
                            Customer.class
                    )
            );
        }

        @Test
        void tolerantMapperReadsKnownProperties() throws Exception {
            Customer customer = tolerantMapper.readValue(
                    NEW_PAYLOAD,
                    Customer.class
            );

            assertEquals("C-100", customer.getId());
            assertEquals("Lan", customer.getName());
        }

        @Test
        void extensibleModelPreservesUnknownProperty() throws Exception {
            ExtensibleCustomer customer = strictMapper.readValue(
                    NEW_PAYLOAD,
                    ExtensibleCustomer.class
            );

            assertEquals(
                    "GOLD",
                    customer.additionalProperties()
                            .get("loyaltyLevel")
                            .asText()
            );

            String output = strictMapper.writeValueAsString(customer);
            JsonNode result = strictMapper.readTree(output);

            assertEquals("GOLD", result.path("loyaltyLevel").asText());
        }
    }

Đoạn test là khung minh họa; lớp Customer, ExtensibleCustomer và các import Jackson/JUnit cần nằm trong project test tương ứng. Ca kiểm thử cuối quan trọng vì nó xác nhận không chỉ đọc được payload mới mà còn giữ lại field khi serialize trở lại.

## 10. Đọc thành công không có nghĩa là bảo toàn dữ liệu

Một lỗi thiết kế thường gặp là chỉ kiểm tra readValue không ném ngoại lệ rồi kết luận consumer đã tương thích.

Hãy xét chu trình:

    JSON v2
       |
       v
    Consumer v1 DTO (chỉ biết id, name)
       |
       v
    Chỉnh sửa name
       |
       v
    Serialize DTO v1
       |
       v
    JSON mới (không còn loyaltyLevel)

Nếu dùng ignoreUnknown hoặc tắt FAIL_ON_UNKNOWN_PROPERTIES, quá trình đọc có thể thành công nhưng field mới đã bị loại khỏi object. Khi ghi lại, field đó không thể tự xuất hiện trở lại.

Nếu ứng dụng chỉ đọc dữ liệu để hiển thị và không bao giờ ghi lại payload, việc bỏ field mới có thể hoàn toàn phù hợp. Nhưng nếu ứng dụng là gateway, proxy, đồng bộ dữ liệu, công cụ biên tập hoặc dịch vụ chuyển tiếp, mất field có thể làm hỏng dữ liệu của phiên bản mới.

Hãy phân biệt:

- **Tolerant read:** consumer chấp nhận payload có thêm field.
- **Lossless round-trip ở mức cấu trúc:** consumer đọc, thay đổi phần nó biết và ghi lại mà vẫn giữ field không biết.
- **Byte-for-byte preservation:** giữ nguyên toàn bộ văn bản gốc, gồm khoảng trắng, thứ tự key, cách escape và định dạng số.

Ignore unknown chỉ giải quyết tolerant read. Any-setter hoặc Tree Model có thể hỗ trợ giữ cấu trúc JSON khi round-trip. Muốn bảo toàn byte-for-byte, cần lưu raw payload hoặc dùng một cơ chế xử lý văn bản phù hợp; JsonNode không phải bản sao nguyên văn.

## 11. Chọn chính sách strict hay tolerant

Không nên bật chế độ tolerant cho mọi tình huống mà không cân nhắc:

| Bối cảnh | Chính sách thường phù hợp | Lý do |
|---|---|---|
| Internal command có schema nghiêm ngặt | Strict | Field sai tên có thể làm lệnh mất dữ liệu hoặc thực hiện sai |
| Event consumer cần tương thích additive changes | Tolerant có kiểm soát | Producer có thể bổ sung field tùy chọn |
| Gateway chuyển tiếp payload | Preserve unknown | Không làm mất dữ liệu mà gateway không hiểu |
| Công cụ biên tập JSON tổng quát | Tree Model hoặc preserve extensions | Cần giữ các nhánh ngoài phạm vi chỉnh sửa |
| Security-sensitive request | Strict hoặc allowlist rõ ràng | Không muốn field không được phép bị âm thầm chấp nhận |
| Analytics chỉ đọc một số field | Tolerant có logging/metrics | Có thể bỏ field mới nhưng vẫn muốn theo dõi schema drift |

Strictness giúp phát hiện sai lệch sớm. Tolerance giúp hệ thống triển khai theo từng giai đoạn mà không cần mọi consumer nâng cấp cùng lúc. Preserve unknown phù hợp khi dữ liệu phải đi qua các thành phần không hiểu toàn bộ schema.

## 12. Theo dõi schema drift khi bỏ qua unknown fields

Nếu bỏ qua field mới, ứng dụng có thể mất tín hiệu rằng producer đã thay đổi schema. Có thể dùng logging, metric hoặc DeserializationProblemHandler để ghi nhận unknown property trong khi vẫn tiếp tục xử lý.

DeserializationProblemHandler cho phép ứng dụng tùy biến cách xử lý một số tình huống deserialization, trong đó có unknown property. Handler có thể ghi metric về tên field, loại payload hoặc phiên bản producer, rồi quyết định đã xử lý hay để Jackson tiếp tục cơ chế mặc định.

Không nên ghi toàn bộ giá trị của unknown field vào log một cách tự động. Field mới có thể chứa dữ liệu cá nhân, token hoặc thông tin nhạy cảm. Thường chỉ cần ghi tên field, loại message, nguồn producer và số lần xuất hiện.

Một metric hữu ích có thể là:

- số unknown property theo loại event;
- số lần gặp field mới theo producer version;
- số payload bị strict mapper từ chối;
- số field mở rộng được lưu lại;
- kích thước Map extension trung bình và cực đại.

Các metric này giúp phát hiện producer đã thêm field nhưng consumer chưa được cập nhật hoặc chưa có quyết định tương thích.

## 13. Những rủi ro cần kiểm soát khi giữ unknown properties

Giữ mọi field chưa biết giúp tránh mất dữ liệu, nhưng cũng mở rộng bề mặt dữ liệu mà ứng dụng lưu và phát lại.

- **Dung lượng:** payload có thể chứa object hoặc array lồng nhau lớn; cần giới hạn kích thước và độ sâu JSON.
- **Dữ liệu nhạy cảm:** field mới có thể chứa thông tin không nên lưu hoặc phát lại. Cần có chính sách lọc theo tên/path hoặc phân loại dữ liệu.
- **Xung đột schema:** field hiện chưa biết hôm nay có thể trở thành field chính thức ở phiên bản sau. Cần tránh để extension map chiếm tên hoặc ghi đè property chuẩn.
- **Kiểu dữ liệu không mong muốn:** không ép unknown value sang kiểu Java tùy tiện; JsonNode giữ cấu trúc để xử lý sau.
- **Tính toàn vẹn:** nếu ứng dụng chỉnh sửa extension fields, cần xác thực quyền và quy tắc nghiệp vụ tương ứng.
- **Khả năng tương thích:** một field được giữ lại có thể không còn hợp lệ với phiên bản producer hiện tại; preserve không đồng nghĩa xác nhận field đó hợp lệ.

Với dữ liệu không đáng tin cậy, cần cấu hình giới hạn parser phù hợp và tránh đưa extension map không kiểm soát trực tiếp vào các hệ thống downstream.

## 14. Thiết kế payload theo hướng tương thích tiến

Để các phiên bản producer/consumer có thể triển khai lệch thời điểm, nên áp dụng một số nguyên tắc:

1. Ưu tiên bổ sung field tùy chọn thay vì thay đổi ý nghĩa hoặc kiểu của field cũ.
2. Không đổi tên field mà không có giai đoạn tương thích; có thể tạm nhận cả tên cũ và tên mới bằng alias khi phù hợp.
3. Không tái sử dụng một tên field cũ cho ý nghĩa hoàn toàn khác.
4. Xác định rõ unknown field sẽ bị từ chối, bỏ qua hay được giữ lại ở mỗi ranh giới dịch vụ.
5. Kiểm thử consumer cũ với payload của producer mới trước khi phát hành.
6. Nếu payload đi qua gateway hoặc được đọc rồi ghi lại, kiểm thử bảo toàn các field chưa biết.
7. Theo dõi schema drift để biết field mới đã xuất hiện trong thực tế.

Thêm field thường dễ tương thích hơn xóa field hoặc đổi kiểu. Tuy nhiên, điều đó chỉ đúng khi consumer cũ có chính sách xử lý unknown field phù hợp và producer không thay đổi semantics của field hiện hữu.

## 15. Kết luận

Khi một phiên bản Jackson đọc JSON có thuộc tính mà mô hình Java hiện tại chưa biết, hành vi mặc định của ObjectMapper là báo lỗi qua FAIL_ON_UNKNOWN_PROPERTIES. Có thể bỏ qua field mới bằng cách tắt feature hoặc dùng @JsonIgnoreProperties(ignoreUnknown = true), nhưng các field đó sẽ mất khi ghi lại DTO. Nếu cần giữ chúng, dùng @JsonAnySetter kết hợp @JsonAnyGetter để lưu extension fields, hoặc dùng JsonNode để giữ toàn bộ cấu trúc cây. Kiểm thử phải bao gồm cả bước đọc và bước serialize lại, vì đọc thành công chưa chứng minh dữ liệu được bảo toàn. Chính sách strict, tolerant hay preserve cần được chọn theo vai trò của consumer, yêu cầu bảo toàn dữ liệu và rủi ro của payload.

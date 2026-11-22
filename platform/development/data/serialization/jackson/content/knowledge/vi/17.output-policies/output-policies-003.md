# Điều chỉnh thứ tự thuộc tính và thứ tự khóa khi cần ổn định

JSON object được định nghĩa là tập hợp các cặp tên và giá trị. Theo ngữ nghĩa JSON, thứ tự các thuộc tính trong object không làm thay đổi ý nghĩa dữ liệu. Tuy nhiên, khi serialize bằng Jackson, thứ tự field vẫn có thể ảnh hưởng đến cách con người đọc file, kết quả diff trong Git, snapshot test, cache key hoặc byte sequence được gửi sang một hệ thống khác.

Cần phân biệt ba loại thứ tự:

- **Thứ tự thuộc tính của POJO/record**: thứ tự các property Java được ghi thành field của JSON object.
- **Thứ tự khóa của Map**: thứ tự các entry trong một Map được ghi thành các thuộc tính JSON.
- **Thứ tự thuộc tính của ObjectNode**: thứ tự field trong một object thuộc Jackson tree model.

Jackson có cấu hình riêng cho từng trường hợp. Có thể chỉ định thứ tự bằng annotation, bật sắp xếp toàn cục, dùng collection có thứ tự hoặc tạo tree theo một trình tự xác định. Nhưng việc làm output ổn định theo một cấu hình không đồng nghĩa với việc tạo ra JSON canonical để ký số hoặc hash.

## 1. Vì sao cần quan tâm đến thứ tự khi serialize?

Xét hai JSON object:

~~~json
{
  "id": "U-100",
  "name": "Linh",
  "active": true
}
~~~

~~~json
{
  "active": true,
  "name": "Linh",
  "id": "U-100"
}
~~~

Hai object có cùng tập thuộc tính và giá trị. Một consumer JSON đúng chuẩn phải hiểu chúng tương đương về mặt dữ liệu, dù chuỗi byte khác nhau.

Trong thực tế, thứ tự ổn định vẫn có ích:

- JSON dễ đọc hơn nếu các field quan trọng xuất hiện trước.
- Git diff ít nhiễu khi chỉ có dữ liệu thay đổi.
- Snapshot test ít thất bại do thứ tự không ổn định.
- Log và file export dễ đối chiếu giữa các lần chạy.
- Một số hệ thống cũ có thể dựa vào thứ tự dù hợp đồng JSON không nên yêu cầu điều đó.
- Cache hoặc hệ thống kiểm tra checksum dựa trên byte cần một quy tắc serialize nhất quán.

Trước khi sắp xếp, hãy xác định mục tiêu. Nếu chỉ muốn output dễ đọc, thứ tự khai báo DTO có thể đủ. Nếu muốn mọi Map có thứ tự khóa xác định, cần cấu hình Map riêng. Nếu cần byte sequence canonical cho chữ ký, các feature sắp xếp thông thường chưa đủ.

## 2. Phân biệt POJO property, Map key và ObjectNode property

Ba nguồn dữ liệu này có thể cùng xuất hiện trong một JSON object nhưng Jackson xử lý chúng bằng các cơ chế khác nhau.

| Nguồn Java | Cơ chế điều khiển thứ tự thường dùng |
|---|---|
| Class hoặc record | @JsonPropertyOrder hoặc MapperFeature.SORT_PROPERTIES_ALPHABETICALLY |
| Map | SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS hoặc Map implementation có thứ tự |
| ObjectNode | Thứ tự field được thêm vào; ở các phiên bản hỗ trợ có thể dùng JsonNodeFeature.WRITE_PROPERTIES_SORTED |
| Array/List | Thứ tự phần tử của collection; không phải thứ tự khóa object |

Ví dụ một DTO có cả property cố định và Map động:

~~~java
public record UserResponse(
    String id,
    String displayName,
    Map<String, Object> attributes
) {}
~~~

Thứ tự id, displayName là thứ tự property của record. Thứ tự các entry bên trong attributes là thứ tự Map. Sắp xếp POJO property không tự động sắp xếp Map lồng bên trong, và ngược lại.

Tương tự, nếu attributes được lưu dưới dạng ObjectNode, cần xem quy tắc của tree model. Không nên bật một feature cho Map rồi mặc định rằng nó cũng sắp xếp mọi ObjectNode.

## 3. Chỉ định thứ tự POJO bằng @JsonPropertyOrder

@JsonPropertyOrder cho phép định nghĩa thứ tự property trên một class cụ thể.

~~~java
import com.fasterxml.jackson.annotation.JsonPropertyOrder;

@JsonPropertyOrder({
    "id",
    "displayName",
    "createdAt",
    "active"
})
public record UserResponse(
    String id,
    String displayName,
    Instant createdAt,
    boolean active
) {}
~~~

Khi serialize, các property được liệt kê sẽ xuất hiện theo thứ tự đã chỉ định. Tên trong annotation là tên property Jackson nhìn thấy sau quá trình introspection và áp dụng tên JSON tương ứng.

Annotation này phù hợp khi:

- Một response type có thứ tự trình bày được quy định rõ.
- Các field nhận diện hoặc field quan trọng nên xuất hiện trước.
- Muốn thứ tự của một DTO không phụ thuộc vào thứ tự khai báo getter hoặc quy tắc khám phá property.
- Muốn tránh thay đổi thứ tự output khi refactor nội bộ class.

Nếu class có property bổ sung không được liệt kê trong danh sách, Jackson vẫn cần quyết định vị trí của chúng. Có thể kết hợp thuộc tính alphabetic:

~~~java
@JsonPropertyOrder(
    value = {"id", "displayName"},
    alphabetic = true
)
public record UserResponse(
    String id,
    String displayName,
    Instant createdAt,
    boolean active
) {}
~~~

Trong ví dụ này, id và displayName được đưa lên trước theo thứ tự đã nêu; các property còn lại có thể được sắp xếp alphabetically. Nếu muốn tất cả property theo alphabet, có thể dùng:

~~~java
@JsonPropertyOrder(alphabetic = true)
public record UserResponse(
    String id,
    String displayName,
    Instant createdAt,
    boolean active
) {}
~~~

@JsonPropertyOrder là cấu hình theo kiểu. Nó không thay đổi thứ tự của mọi DTO khác và không điều khiển thứ tự key của một Map nằm trong DTO.

## 4. Sắp xếp property của POJO trên toàn mapper

Nếu ứng dụng muốn mọi bean property được sắp xếp theo tên, có thể bật MapperFeature.SORT_PROPERTIES_ALPHABETICALLY.

~~~java
import com.fasterxml.jackson.databind.MapperFeature;
import com.fasterxml.jackson.databind.json.JsonMapper;

ObjectMapper mapper = JsonMapper.builder()
    .enable(MapperFeature.SORT_PROPERTIES_ALPHABETICALLY)
    .build();
~~~

Đây là cấu hình ở cấp mapper. Nó hữu ích khi muốn thứ tự nhất quán cho nhiều DTO mà không cần lặp annotation trên từng class.

Cần lưu ý:

- Feature này điều khiển thứ tự property của POJO/bean.
- Nó không thay thế ORDER_MAP_ENTRIES_BY_KEYS cho Map.
- Nó không làm array được sắp xếp.
- Một @JsonPropertyOrder cụ thể vẫn có thể quy định thứ tự riêng cho class.
- Việc sắp xếp property không thay đổi tên field hoặc giá trị được serialize.

Không nên bật sắp xếp toàn cục chỉ để giải quyết một response type nếu phần lớn API cần thứ tự trình bày riêng. Với một vài DTO công khai, @JsonPropertyOrder thường thể hiện ý định rõ hơn. Với chính sách đồng nhất trên toàn ứng dụng, MapperFeature có thể phù hợp hơn.

Cấu hình mapper nên được hoàn tất trước khi mapper được sử dụng đồng thời. Sau khi ứng dụng bắt đầu serialize, không nên thay đổi feature tùy tiện trong từng request.

## 5. Sắp xếp khóa của Map bằng ORDER_MAP_ENTRIES_BY_KEYS

Map thường được dùng cho dữ liệu động:

~~~java
Map<String, Object> attributes = new HashMap<>();
attributes.put("timezone", "Asia/Ho_Chi_Minh");
attributes.put("language", "vi");
attributes.put("theme", "dark");
~~~

HashMap không cam kết thứ tự iteration ổn định. Nếu serialize trực tiếp, thứ tự key không nên được xem là hợp đồng ổn định.

Jackson có SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS để sắp xếp entry của Map theo khóa khi serialize:

~~~java
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.json.JsonMapper;

ObjectMapper mapper = JsonMapper.builder()
    .enable(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS)
    .build();

String json = mapper.writeValueAsString(attributes);
~~~

Với Map có khóa String, các entry được ghi theo thứ tự khóa tự nhiên. Ví dụ kết quả sẽ có các key theo thứ tự alphabet:

~~~json
{
  "language": "vi",
  "theme": "dark",
  "timezone": "Asia/Ho_Chi_Minh"
}
~~~

Nếu chỉ cần áp dụng cho một lần ghi, có thể tạo ObjectWriter riêng:

~~~java
ObjectWriter sortedMapWriter = mapper.writer()
    .with(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS);

String json = sortedMapWriter.writeValueAsString(attributes);
~~~

Writer này mang cấu hình serialize riêng; mapper và các writer khác không bị đổi cấu hình.

Feature sắp xếp Map áp dụng cho các Map được serialize trong cấu trúc, kể cả Map lồng nhau. Nó không có nghĩa mọi object JSON trong output đều được sắp xếp theo key.

## 6. LinkedHashMap và TreeMap có vai trò gì?

Có thể chọn Map implementation dựa trên quy tắc thứ tự mong muốn.

### LinkedHashMap: giữ thứ tự chèn

~~~java
Map<String, Object> attributes = new LinkedHashMap<>();
attributes.put("timezone", "Asia/Ho_Chi_Minh");
attributes.put("language", "vi");
attributes.put("theme", "dark");
~~~

LinkedHashMap giữ thứ tự chèn. Khi serialize, thứ tự entry thường theo trình tự đã thêm vào.

Dùng LinkedHashMap khi thứ tự được xác định bởi logic tạo dữ liệu, chẳng hạn một file cấu hình hoặc báo cáo có thứ tự trình bày mong muốn.

Lưu ý: LinkedHashMap chỉ ổn định nếu thứ tự chèn đầu vào cũng ổn định. Nếu dữ liệu được nạp từ một HashMap khác, việc chuyển sang LinkedHashMap không thể khôi phục một thứ tự có ý nghĩa đã không được xác định trước.

### TreeMap: giữ thứ tự theo comparator

~~~java
Map<String, Object> attributes = new TreeMap<>();
attributes.put("timezone", "Asia/Ho_Chi_Minh");
attributes.put("language", "vi");
attributes.put("theme", "dark");
~~~

TreeMap sắp xếp key theo natural ordering hoặc Comparator được cung cấp. Vì vậy, thứ tự iteration được xác định bởi quy tắc đó.

Có thể dùng comparator riêng:

~~~java
Map<String, Object> attributes =
    new TreeMap<>(String.CASE_INSENSITIVE_ORDER);
~~~

Tuy nhiên, comparator không phân biệt chữ hoa/thường có thể xem hai key khác nhau theo equals() là tương đương về thứ tự. TreeMap có thể không lưu được cả hai key đó như hai entry riêng biệt. Chỉ dùng comparator như vậy khi quy tắc nghiệp vụ cho phép.

### Chọn implementation hay bật Jackson feature?

| Cách làm | Phù hợp khi |
|---|---|
| LinkedHashMap | Thứ tự chèn là thứ tự mong muốn. |
| TreeMap | Muốn Map luôn được lưu và duyệt theo một comparator. |
| ORDER_MAP_ENTRIES_BY_KEYS | Muốn giữ Map hiện tại nhưng yêu cầu Jackson sắp xếp khi serialize. |

Nếu chỉ cần thứ tự khi xuất JSON, ORDER_MAP_ENTRIES_BY_KEYS giúp tránh thay đổi cấu trúc Map nội bộ. Nếu toàn bộ logic ứng dụng cần duyệt Map theo thứ tự khóa, TreeMap có thể hợp lý hơn.

## 7. Những trường hợp Map cần chú ý

JSON object có tên thuộc tính dạng string. Trong Java, Map có thể dùng khóa không phải String, và Jackson có thể cần key serializer để chuyển chúng thành tên JSON.

Ví dụ:

~~~java
Map<Integer, String> codes = new HashMap<>();
codes.put(20, "twenty");
codes.put(3, "three");
~~~

Khi serialize, các key số được chuyển thành tên field JSON dạng chuỗi. Thứ tự sắp xếp Map dựa trên khóa Java và cơ chế so sánh của Jackson; không nên giả định thứ tự đó luôn giống thứ tự từ điển của chuỗi sau khi key serializer chuyển đổi.

Với Map dùng key tùy chỉnh:

- Xác định rõ cách key được serialize thành tên JSON.
- Xác định comparator có thể so sánh mọi key hay không.
- Kiểm tra khả năng hai key khác nhau trong Java trở thành cùng tên JSON.
- Viết test trên JSON thực tế, không chỉ test thứ tự iteration của Map.

Đối với hợp đồng JSON ổn định, Map<String, T> thường dễ dự đoán hơn Map có key là object hoặc kiểu tùy chỉnh.

## 8. Điều khiển thứ tự field của ObjectNode

ObjectNode là một object trong tree model. Khi tạo node và thêm field theo một trình tự xác định, cách sử dụng thông thường giữ thứ tự field được thêm vào:

~~~java
ObjectNode user = mapper.createObjectNode();

user.put("id", "U-100");
user.put("displayName", "Linh");
user.put("active", true);
~~~

Output sẽ giữ thứ tự thêm field theo cấu trúc ObjectNode mặc định. Nếu cần một thứ tự trình bày cụ thể, hãy thêm field theo thứ tự đó ngay từ lúc tạo cây.

Khi copy hoặc biến đổi ObjectNode, hãy chú ý các thao tác có thể giữ lại thứ tự hiện tại hoặc thêm field mới vào cuối. Nếu cần xây dựng một output có thứ tự khác, tạo ObjectNode mới và chép các field theo trình tự mong muốn:

~~~java
ObjectNode ordered = mapper.createObjectNode();

ordered.set("id", source.get("id"));
ordered.set("displayName", source.get("displayName"));
ordered.set("active", source.get("active"));
~~~

Nếu một field có thể bị thiếu, hãy kiểm tra trước khi set để tránh đưa Java null vào API node:

~~~java
ObjectNode ordered = mapper.createObjectNode();

for (String name : List.of("id", "displayName", "active")) {
    JsonNode value = source.get(name);

    if (value != null) {
        ordered.set(name, value.deepCopy());
    }
}
~~~

Trong các phiên bản Jackson Databind có hỗ trợ JsonNodeFeature.WRITE_PROPERTIES_SORTED, có thể bật feature này để yêu cầu ObjectNode được ghi theo thứ tự tên property:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .enable(JsonNodeFeature.WRITE_PROPERTIES_SORTED)
    .build();
~~~

Feature này thuộc nhóm cấu hình tree node và có từ các phiên bản Jackson mới; hãy kiểm tra API của đúng phiên bản dự án trước khi dùng. Nó dành cho ObjectNode, không thay thế cấu hình sắp xếp POJO property hoặc Map key.

Nếu phiên bản dự án chưa có feature này, tạo ObjectNode theo thứ tự cần xuất hoặc chuyển subtree thành một Map có thứ tự trước khi serialize.

## 9. Sắp xếp POJO và Map trong cùng một mapper

Một API có thể chứa cả DTO và Map. Có thể bật cả hai feature:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .enable(MapperFeature.SORT_PROPERTIES_ALPHABETICALLY)
    .enable(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS)
    .build();
~~~

Ví dụ:

~~~java
public record AuditResponse(
    String requestId,
    String event,
    Map<String, Object> metadata
) {}

Map<String, Object> metadata = new HashMap<>();
metadata.put("source", "api");
metadata.put("attempt", 2);
metadata.put("region", "ap-southeast-1");

AuditResponse response =
    new AuditResponse("REQ-100", "created", metadata);

String json = mapper.writeValueAsString(response);
~~~

Mapper sắp xếp property của AuditResponse theo tên và sắp xếp các entry của metadata theo key. Hai chính sách hoạt động độc lập nhưng có thể cùng được áp dụng trong một lần serialize.

Nếu một DTO cần thứ tự riêng, có thể dùng @JsonPropertyOrder trên DTO đó. Nếu một Map cần giữ thứ tự chèn thay vì sort alphabet, hãy cân nhắc không bật ORDER_MAP_ENTRIES_BY_KEYS toàn cục hoặc dùng writer riêng cho đường xuất cần sort.

## 10. Thứ tự array là một vấn đề khác

Không được nhầm thứ tự key của object với thứ tự phần tử của array.

JSON array là một dãy có thứ tự. Hai array sau không tương đương:

~~~json
["created", "updated", "deleted"]
~~~

~~~json
["deleted", "updated", "created"]
~~~

Nếu array đại diện cho lịch sử sự kiện, thứ tự thời gian có ý nghĩa. Nếu array đại diện cho một tập nhãn mà thứ tự không quan trọng, ứng dụng có thể chọn sort trước khi serialize, nhưng đó là quy tắc nghiệp vụ của dữ liệu.

Jackson không tự sắp xếp List hoặc ArrayNode chỉ vì bật ORDER_MAP_ENTRIES_BY_KEYS hay SORT_PROPERTIES_ALPHABETICALLY.

Ví dụ, muốn sắp xếp danh sách mã trước khi ghi:

~~~java
List<String> sortedTags = tags.stream()
    .sorted()
    .toList();
~~~

Chỉ làm vậy nếu hợp đồng cho phép thay đổi thứ tự. Với danh sách có ý nghĩa vị trí, hãy giữ nguyên thứ tự nguồn.

## 11. Thứ tự ổn định không đồng nghĩa JSON canonical

Đây là điểm đặc biệt quan trọng khi output dùng cho chữ ký số, hash, checksum hoặc định danh nội dung.

Bật các feature sau:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .enable(MapperFeature.SORT_PROPERTIES_ALPHABETICALLY)
    .enable(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS)
    .build();
~~~

có thể làm một số phần output ổn định hơn. Nhưng điều đó không tự tạo ra canonical JSON theo một chuẩn thống nhất.

Byte output còn có thể khác do:

- Cách biểu diễn số, đặc biệt BigDecimal, exponent và số 0 ở cuối.
- Cách escape ký tự trong string.
- Encoding và quy tắc Unicode.
- Null inclusion và property filter.
- Định dạng ngày giờ, timezone và locale.
- Custom serializer hoặc key serializer.
- Pretty printing và khoảng trắng.
- Thứ tự các phần tử array.
- ObjectNode được tạo từ nguồn có thứ tự khác nhau.
- Phiên bản Jackson hoặc cấu hình thay đổi.

Nếu dùng JSON làm đầu vào cho chữ ký số hoặc hash, hai hệ thống phải tạo ra chính xác cùng byte sequence. Chỉ sort key chưa đủ.

Có thể dùng một chuẩn canonicalization như JSON Canonicalization Scheme (JCS, RFC 8785). Chuẩn này quy định cách chuẩn hóa property name, number serialization và các chi tiết biểu diễn khác để các bên tạo cùng canonical bytes từ cùng dữ liệu JSON phù hợp.

Jackson là thư viện parse và serialize JSON; các feature sắp xếp thông thường không đồng nghĩa với việc Jackson tự thực hiện toàn bộ RFC 8785. Nếu chữ ký hoặc hash phụ thuộc canonical JSON, hãy dùng thư viện canonicalization tương thích với chuẩn đã chọn và kiểm tra bằng test vector của chuẩn đó.

Không nên tự viết một hàm sort key rồi gọi output là canonical. Các khác biệt về số, escape, Unicode và dữ liệu không hợp lệ có thể làm chữ ký giữa các hệ thống không khớp.

## 12. Pretty printing không quyết định thứ tự property

Pretty printing chỉ thêm khoảng trắng và xuống dòng để JSON dễ đọc:

~~~java
ObjectWriter prettyWriter = mapper.writerWithDefaultPrettyPrinter();
String json = prettyWriter.writeValueAsString(response);
~~~

Nó không tự sắp xếp field. Nếu cần vừa sort vừa pretty, cấu hình thứ tự trên mapper hoặc writer trước, sau đó dùng pretty printer:

~~~java
ObjectWriter readableWriter = mapper.writer()
    .with(SerializationFeature.INDENT_OUTPUT)
    .with(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS);
~~~

Đối với POJO, thứ tự alphabet toàn cục hoặc @JsonPropertyOrder vẫn cần được cấu hình riêng. Với ObjectNode, cần dùng thứ tự chèn hoặc feature dành cho JsonNode nếu phiên bản hỗ trợ.

Pretty output và compact output thường biểu diễn cùng cấu trúc JSON nhưng byte sequence khác nhau. Vì vậy, không nên ký hoặc hash chuỗi pretty output nếu hệ thống bên kia canonicalize theo một quy tắc khác.

## 13. Kiểm tra output ổn định bằng test

Một test nên xác nhận thứ tự thực tế trong chuỗi JSON, không chỉ kiểm tra hai cây JSON có cùng dữ liệu. Khi so sánh tree, thứ tự field của object thường không phải trọng tâm; khi kiểm tra chính sách output, cần kiểm tra chuỗi hoặc vị trí field.

Ví dụ kiểm tra POJO và Map:

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.databind.MapperFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.json.JsonMapper;
import org.junit.jupiter.api.Test;

class JsonPropertyOrderingTest {

    record UserResponse(
        String id,
        String displayName,
        Map<String, Object> attributes
    ) {}

    private final ObjectMapper mapper = JsonMapper.builder()
        .enable(MapperFeature.SORT_PROPERTIES_ALPHABETICALLY)
        .enable(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS)
        .build();

    @Test
    void sortsBeanPropertiesAndMapKeys() throws Exception {
        Map<String, Object> attributes = new HashMap<>();
        attributes.put("timezone", "UTC");
        attributes.put("language", "vi");

        UserResponse response =
            new UserResponse("U-100", "Linh", attributes);

        String json = mapper.writeValueAsString(response);

        assertTrue(json.indexOf("\"attributes\"") < json.indexOf("\"displayName\""));
        assertTrue(json.indexOf("\"displayName\"") < json.indexOf("\"id\""));
        assertTrue(json.indexOf("\"language\"") < json.indexOf("\"timezone\""));
    }
}
~~~

Ví dụ trên giả định các import Map và HashMap đã được thêm. Nó kiểm tra thứ tự property của bean và thứ tự key bên trong Map riêng biệt.

Nếu dùng @JsonPropertyOrder, hãy tạo test cho đúng class đó để tránh refactor làm thay đổi thứ tự output. Nếu dùng ObjectNode, hãy test thứ tự field trong JSON string hoặc feature tree-node tương ứng.

Không nên dùng snapshot test quá nhạy với khoảng trắng nếu mục tiêu chỉ là thứ tự key. Có thể parse output và kiểm tra thứ tự field bằng parser hoặc so sánh các vị trí chuỗi; đồng thời giữ một test riêng cho cấu trúc dữ liệu.

## 14. Các lỗi cấu hình thường gặp

| Nhầm lẫn | Hệ quả | Cách hiểu đúng |
|---|---|---|
| Bật SORT_PROPERTIES_ALPHABETICALLY rồi mong Map cũng sort | Map vẫn theo thứ tự của Map/serializer. | Bật ORDER_MAP_ENTRIES_BY_KEYS hoặc dùng Map có thứ tự. |
| Bật ORDER_MAP_ENTRIES_BY_KEYS rồi mong POJO đổi thứ tự | Property bean không bị điều khiển bởi feature Map. | Dùng @JsonPropertyOrder hoặc MapperFeature. |
| Cho rằng HashMap có thứ tự ổn định | Output có thể thay đổi theo cách tạo và runtime. | Dùng LinkedHashMap, TreeMap hoặc sort khi serialize. |
| Cho rằng ObjectNode tự alphabet | Thứ tự có thể theo thứ tự field được thêm vào. | Tạo node theo thứ tự xác định hoặc dùng JsonNodeFeature nếu có. |
| Sort mọi List để output đẹp | Có thể làm thay đổi ý nghĩa thứ tự nghiệp vụ. | Chỉ sort array khi hợp đồng coi nó là tập không thứ tự. |
| Dùng sort key để ký JSON | Byte output vẫn có thể khác vì number, escaping, Unicode hoặc whitespace. | Dùng chuẩn canonicalization như JCS. |
| Thay đổi mapper sau khi ứng dụng đã chạy | Các request có thể quan sát cấu hình không nhất quán. | Cấu hình trước khi dùng và tạo writer riêng cho nhu cầu cục bộ. |

## 15. Quy trình chọn chính sách thứ tự

Khi thiết kế response hoặc file export, hãy xác định:

1. Những field POJO nào cần thứ tự trình bày cố định?
2. Map có cần sort key hay giữ thứ tự chèn?
3. ObjectNode được tạo từ dữ liệu động có cần thứ tự cố định?
4. Array có mang ý nghĩa thứ tự không?
5. Output chỉ cần dễ đọc/dễ diff hay phải tạo byte sequence canonical?
6. Chính sách có áp dụng toàn ứng dụng hay chỉ một DTO/endpoint?
7. Có test chứng minh thứ tự thực tế của output không?

Một lựa chọn thực tế:

- Dùng @JsonPropertyOrder khi một DTO công khai có thứ tự field riêng.
- Dùng MapperFeature.SORT_PROPERTIES_ALPHABETICALLY khi muốn chính sách alphabet cho POJO trên mapper.
- Dùng SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS khi Map cần sort theo key lúc serialize.
- Dùng LinkedHashMap khi thứ tự chèn đã được xác định và cần được giữ.
- Dùng TreeMap khi toàn bộ logic cần Map luôn theo comparator.
- Tạo ObjectNode theo thứ tự mong muốn hoặc dùng JsonNodeFeature phù hợp với phiên bản.
- Dùng canonicalization chuẩn khi byte sequence là một phần của chữ ký hoặc hash.

## Kết luận

Jackson có nhiều cơ chế để kiểm soát thứ tự đầu ra, nhưng mỗi cơ chế áp dụng cho một loại dữ liệu. @JsonPropertyOrder và MapperFeature.SORT_PROPERTIES_ALPHABETICALLY điều khiển property của POJO; SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS điều khiển key của Map; ObjectNode thường theo thứ tự field được thêm hoặc feature tree-node tương ứng nếu phiên bản hỗ trợ.

Hãy chọn chính sách theo mục đích: thứ tự dễ đọc, output ổn định cho diff/test hay canonical bytes cho chữ ký/hash. Sắp xếp field và key giúp giảm khác biệt không cần thiết, nhưng không thay thế chuẩn canonical JSON. Kiểm tra riêng POJO, Map, ObjectNode và array để bảo đảm mỗi loại dữ liệu giữ đúng thứ tự mà hợp đồng yêu cầu.


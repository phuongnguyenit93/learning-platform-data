# Khi nào chọn Jackson và khi nào cần công cụ khác

Jackson là lựa chọn rất phù hợp khi một ứng dụng Java cần đọc và ghi JSON, đặc biệt trong API HTTP, tích hợp dịch vụ và xử lý dữ liệu trao đổi giữa các hệ thống. Tuy vậy, không nên chọn thư viện chỉ vì nó phổ biến hoặc đã có sẵn trong dự án. Hãy bắt đầu từ định dạng dữ liệu, cấu trúc hợp đồng, kích thước dữ liệu, ngôn ngữ đang dùng và mức độ kiểm soát cần thiết.

Quy tắc thực tế là: **chọn Jackson làm mặc định cho JSON trong ứng dụng Java nếu hệ sinh thái hiện tại đã hỗ trợ tốt; chuyển sang công cụ khác khi công cụ đó giải quyết một yêu cầu cụ thể tốt hơn.**

## 1. Bảng quyết định nhanh

| Nhu cầu | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| REST API Java nhận và trả JSON, ánh xạ JSON vào DTO | Jackson Databind | Tích hợp tốt với hệ sinh thái Java và Spring, hỗ trợ annotation, module và kiểu dữ liệu phong phú |
| JSON có cấu trúc thay đổi theo từng bản tin | Jackson Tree Model hoặc JSON-P | Có thể duyệt cây dữ liệu hoặc thao tác JSON mà không cần định nghĩa trước toàn bộ DTO |
| Đọc hoặc ghi JSON rất lớn theo từng phần | Jackson Streaming API hoặc JSON-P Streaming | Xử lý tuần tự từng token, tránh giữ cả cây dữ liệu lớn trong bộ nhớ |
| Ứng dụng Kotlin cần serialization theo kiểu Kotlin, đa nền tảng | kotlinx.serialization | Sinh serializer theo compiler plugin, hỗ trợ Kotlin multiplatform và mô hình Kotlin |
| Ứng dụng cần thư viện JSON gọn, API đơn giản | Gson hoặc Moshi | Có thể đáp ứng tốt các trường hợp JSON cơ bản; Moshi thường phù hợp với hệ sinh thái Kotlin/Android |
| Cần chuẩn Jakarta để giảm phụ thuộc vào một nhà cung cấp | JSON-B hoặc JSON-P | API chuẩn hóa trong hệ sinh thái Jakarta |
| Dữ liệu trao đổi cần schema rõ ràng, payload gọn và tương thích phiên bản nghiêm ngặt | Protocol Buffers hoặc Avro | Có schema, quy tắc tương thích và biểu diễn nhị phân hiệu quả |
| Cần XML có ràng buộc schema, namespace hoặc mapping nghiệp vụ phức tạp | JAXB hoặc StAX; đôi khi Jackson XML | Công cụ XML chuyên biệt có thể biểu đạt đầy đủ hơn các đặc điểm của XML |
| Cần đọc/ghi CSV | Apache Commons CSV hoặc OpenCSV | Xử lý delimiter, quote, escape và record theo đúng ngữ nghĩa CSV |
| Cần đọc/ghi YAML | Jackson YAML hoặc SnakeYAML | Chọn theo nhu cầu mapping đối tượng hay thao tác trực tiếp với cấu trúc YAML |
| Chuyển đổi giữa hai mô hình Java trong cùng ứng dụng | MapStruct hoặc mapping thủ công | Đây là bài toán object-to-object mapping, không phải serialization |
| Muốn lưu object Java tùy ý thành luồng byte để nhận lại sau này | Thiết kế định dạng lưu trữ rõ ràng; tránh Java native serialization | Serialization nhị phân gắn chặt với lớp Java và có rủi ro bảo mật khi đọc dữ liệu không tin cậy |

Bảng trên là điểm bắt đầu. Một dự án có thể dùng nhiều công cụ: Jackson cho REST API, Protocol Buffers cho giao tiếp nội bộ tốc độ cao và Apache Commons CSV cho chức năng import/export.

## 2. Khi nào Jackson là lựa chọn tốt?

### 2.1. Ứng dụng Java trao đổi JSON qua HTTP

Jackson đặc biệt phù hợp khi backend nhận JSON từ client và trả JSON cho client. Mô hình phổ biến là ánh xạ request vào DTO, kiểm tra dữ liệu, xử lý nghiệp vụ rồi ánh xạ response DTO thành JSON.

Trong Spring MVC và Spring WebFlux, Jackson thường được tích hợp thông qua HTTP message converter hoặc codec khi dependency phù hợp có mặt trên classpath. Điều này giúp controller tập trung vào request, response và nghiệp vụ thay vì tự gọi parser ở từng endpoint.

Ví dụ một request DTO:

~~~java
import java.time.Instant;
import java.util.List;

public record CreateOrderRequest(
    String customerId,
    Instant requestedAt,
    List<String> productCodes
) {}
~~~

Jackson có thể ánh xạ JSON thành record và ngược lại. Với các kiểu ngày giờ của Java, ứng dụng cần module hỗ trợ tương ứng, thường là jackson-datatype-jsr310 với JavaTimeModule trong Jackson 2. Khi dùng Spring Boot, nên ưu tiên dependency management và cấu hình ObjectMapper do Spring Boot cung cấp trước khi tự tạo một bộ cấu hình riêng.

### 2.2. Cần ánh xạ JSON vào DTO một cách linh hoạt

Jackson Databind phù hợp khi cấu trúc JSON đã được mô hình hóa thành class, record hoặc DTO. Annotation giúp điều chỉnh tên field, định dạng, thuộc tính bị bỏ qua và cách xử lý các trường hợp đặc biệt.

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;

public record CustomerResponse(
    @JsonProperty("customer_id") String customerId,
    String displayName
) {}
~~~

~~~json
{
  "customer_id": "CUS-1001",
  "displayName": "An"
}
~~~

Các khả năng như custom serializer, custom deserializer, mix-in annotation và module hữu ích khi hợp đồng JSON có quy tắc đặc thù hoặc cần tích hợp kiểu dữ liệu từ thư viện khác.

Tuy nhiên, annotation không thay thế thiết kế DTO. Không nên để mọi quy tắc nghiệp vụ, kiểm tra quyền truy cập hoặc chuyển đổi dữ liệu phức tạp nằm trong serializer. Serializer nên tập trung vào biểu diễn dữ liệu.

### 2.3. Cần cả ba cách tiếp cận: object, tree và streaming

Jackson không chỉ có một cách xử lý JSON. Có ba mô hình chính, phù hợp với ba dạng vấn đề khác nhau.

| Mô hình | Cách làm | Khi nên dùng |
|---|---|---|
| Databind | Ánh xạ JSON trực tiếp vào Java object và ngược lại | Cấu trúc dữ liệu ổn định, đã có DTO |
| Tree Model | Đọc JSON thành cây JsonNode rồi truy cập từng node | Cấu trúc không hoàn toàn cố định, chỉ cần một số trường hoặc cần biến đổi có điều kiện |
| Streaming API | Đọc/ghi token tuần tự bằng JsonParser và JsonGenerator | File lớn, dữ liệu liên tục hoặc cần kiểm soát bộ nhớ |

Ví dụ Tree Model:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper mapper = new ObjectMapper();

JsonNode root = mapper.readTree(json);
JsonNode statusNode = root.path("status");

if (!statusNode.isMissingNode()) {
    String status = statusNode.asText();
    System.out.println(status);
}
~~~

Tree Model tiện khi một webhook có nhiều phiên bản payload hoặc chỉ một vài thuộc tính cần được trích xuất. Dùng path giúp tránh lỗi null khi một node không tồn tại, nhưng vẫn cần kiểm tra kiểu và giá trị trước khi dùng dữ liệu cho nghiệp vụ.

Streaming API phù hợp hơn khi xử lý một file JSON lớn đến mức không muốn tạo toàn bộ object graph hoặc JsonNode tree. Parser đọc token theo thứ tự; ứng dụng chỉ giữ lại phần dữ liệu cần thiết. Cách này tiết kiệm bộ nhớ nhưng code thường dài và cần quản lý trạng thái đọc cẩn thận hơn.

### 2.4. Hệ sinh thái hiện tại đã dùng Jackson

Nếu dự án Java đã dùng Jackson thông qua Spring Boot, thư viện nội bộ hoặc các dependency khác, tiếp tục dùng Jackson thường giúp giảm số lượng thư viện và cấu hình phải duy trì. Một ObjectMapper được cấu hình thống nhất cũng giúp các endpoint có hành vi JSON nhất quán.

Đây là lợi thế về vận hành và bảo trì, nhưng không phải lý do để ép mọi định dạng dữ liệu vào Jackson. Ví dụ, việc dùng Jackson để đọc CSV chỉ hợp lý nếu module CSV đáp ứng đúng yêu cầu; nếu cần xử lý CSV chuyên sâu, thư viện chuyên biệt có thể dễ hiểu và ít lỗi hơn.

## 3. Khi nào nên chọn công cụ khác?

### 3.1. Gson: JSON đơn giản và nhu cầu mapping cơ bản

Gson là thư viện JSON của Google, có API tương đối đơn giản để chuyển đổi Java object và JSON. Nó có thể phù hợp với ứng dụng nhỏ, tiện ích độc lập hoặc hệ thống đã sử dụng Gson ổn định.

Nên cân nhắc Gson khi:

- Nhu cầu chủ yếu là đọc và ghi JSON cơ bản.
- Dự án đã chuẩn hóa Gson và không cần các khả năng đặc thù của Jackson.
- Đội ngũ quen với API của Gson và chi phí chuyển đổi không mang lại lợi ích rõ ràng.

Nên cân nhắc Jackson khi cần tích hợp sâu với Spring, nhiều module kiểu dữ liệu, streaming, tree model, annotation phong phú hoặc cấu hình chung cho nhiều thành phần.

Không nên chuyển thư viện chỉ vì một bài benchmark đơn lẻ. Hiệu năng phụ thuộc vào cấu trúc payload, cách cấu hình, kiểu dữ liệu, kích thước dữ liệu và phiên bản thư viện. Nếu hiệu năng là lý do chính, hãy benchmark bằng payload và luồng xử lý thực tế của ứng dụng.

### 3.2. Moshi: lựa chọn đáng cân nhắc trong Kotlin và Android

Moshi là thư viện JSON của Square, thường xuất hiện trong các ứng dụng Android và Kotlin. API của Moshi tập trung vào việc đọc/ghi JSON và có hỗ trợ adapter để tùy chỉnh cách chuyển đổi.

Có thể chọn Moshi khi dự án Android hoặc Kotlin đã dùng Moshi, cần adapter phù hợp với mô hình hiện tại và muốn giữ hệ sinh thái dependency gọn. Với backend Java/Spring đã dùng Jackson, việc thêm Moshi chỉ để xử lý một DTO thông thường thường không tạo ra lợi ích đủ lớn.

### 3.3. kotlinx.serialization: mô hình Kotlin và đa nền tảng

kotlinx.serialization phù hợp khi Kotlin là ngôn ngữ trung tâm, đặc biệt nếu ứng dụng cần chia sẻ mô hình dữ liệu giữa JVM, Android, JavaScript hoặc Native. Serializer được tạo dựa trên metadata của compiler plugin và annotation của Kotlin.

Nên cân nhắc thư viện này khi:

- Dự án cần Kotlin multiplatform.
- Muốn mô hình hóa serialization theo kiểu dữ liệu Kotlin.
- Cần kiểm soát serializer theo từng kiểu và muốn hạn chế reflection trong các trường hợp được hỗ trợ.

Jackson vẫn có thể dùng trong ứng dụng Kotlin chạy trên JVM, nhưng kotlinx.serialization thường tự nhiên hơn khi yêu cầu đa nền tảng là trọng tâm. Quyết định cần xét đến các dependency hiện có, kiểu dữ liệu đang dùng và khả năng tương thích với thư viện khác.

### 3.4. JSON-B và JSON-P: khi cần API chuẩn Jakarta

JSON-B (Jakarta JSON Binding) cung cấp cách binding giữa JSON và Java object theo chuẩn Jakarta. JSON-P (Jakarta JSON Processing) cung cấp API xử lý JSON ở mức thấp hơn, gồm object model và streaming.

Hai chuẩn này đáng cân nhắc khi:

- Ứng dụng Jakarta EE cần giảm phụ thuộc vào API riêng của một thư viện.
- Hạ tầng hoặc nền tảng triển khai yêu cầu chuẩn Jakarta.
- Tính di động giữa các runtime Jakarta quan trọng hơn các tính năng riêng của Jackson.

JSON-B và Jackson giải quyết nhiều nhu cầu giống nhau ở lớp binding, nhưng không có nghĩa là mọi tính năng hoặc annotation của hai bên có thể thay thế trực tiếp cho nhau. JSON-P thích hợp khi cần thao tác JSON theo API chuẩn mà không muốn gắn vào một object mapper cụ thể.

### 3.5. Protocol Buffers và Avro: khi JSON không còn phù hợp

Jackson là công cụ xử lý định dạng dữ liệu; nó không tự tạo ra một hợp đồng nhị phân có schema và quy tắc tương thích phiên bản như Protocol Buffers hoặc Avro.

Hãy cân nhắc Protocol Buffers khi:

- Các dịch vụ cần giao tiếp hiệu quả với payload nhị phân.
- Hợp đồng API cần được định nghĩa bằng schema.
- Muốn sinh code cho nhiều ngôn ngữ.
- Cần quản lý việc thêm, bỏ hoặc thay đổi field theo quy tắc tương thích.

Avro thường phù hợp trong hệ sinh thái dữ liệu lớn và event streaming, nơi schema có thể được quản lý tập trung và reader/writer schema có vai trò quan trọng.

Các định dạng này có chi phí về schema, code generation, tooling và khả năng debug. JSON thường dễ đọc trực tiếp hơn và thuận tiện cho API công khai, tích hợp thủ công hoặc hệ thống cần tính linh hoạt cao. Chọn binary format khi yêu cầu về kích thước, tốc độ, schema hoặc tương thích hợp đồng đủ rõ ràng.

### 3.6. XML: JAXB, StAX hoặc Jackson XML

XML có các đặc điểm mà JSON không có, chẳng hạn namespace, attribute, mixed content, schema và cấu trúc tài liệu. Vì vậy, chọn công cụ XML cần dựa vào dạng XML thực tế.

- **JAXB (Jakarta XML Binding):** phù hợp khi cần binding XML với Java class, đặc biệt trong hệ thống dùng XSD và các mô hình XML đã được định nghĩa.
- **StAX:** phù hợp khi cần đọc hoặc ghi XML theo luồng, kiểm soát từng event và xử lý tài liệu lớn.
- **Jackson XML:** thuận tiện khi dự án đã dùng Jackson và cấu trúc XML tương đối phù hợp với cách ánh xạ object của Jackson.

Không nên giả định rằng Jackson XML có thể biểu diễn mọi cấu trúc XML phức tạp giống như một công cụ XML chuyên biệt. Hãy thử với tài liệu đại diện có namespace, attribute, danh sách phần tử, phần tử tùy chọn và mixed content trước khi quyết định.

### 3.7. CSV: Apache Commons CSV hoặc OpenCSV

CSV trông đơn giản nhưng có nhiều quy tắc dễ xử lý sai: dấu phân cách, dấu nháy, ký tự escape, xuống dòng bên trong một ô, encoding và header. Jackson có module CSV, nhưng Apache Commons CSV hoặc OpenCSV thường là lựa chọn trực tiếp khi chức năng chính là import/export bảng dữ liệu.

Hãy chọn thư viện CSV chuyên biệt khi cần:

- Đọc file có nhiều biến thể delimiter hoặc quote.
- Xử lý header và mapping cột.
- Đọc file lớn theo từng record.
- Xuất dữ liệu có quy tắc escape và format rõ ràng.

Nếu hệ thống chỉ trao đổi một cấu trúc bảng đơn giản và đã có Jackson CSV, có thể tiếp tục dùng module đó để giảm số dependency.

### 3.8. YAML: Jackson YAML hoặc SnakeYAML

Jackson YAML phù hợp khi muốn ánh xạ YAML vào Java object bằng mô hình gần với Jackson Databind. SnakeYAML phù hợp khi cần thao tác trực tiếp với cấu trúc YAML hoặc sử dụng các khả năng đặc thù của hệ sinh thái SnakeYAML.

YAML thường được dùng cho cấu hình, vì vậy cần quan tâm đến việc nạp dữ liệu không tin cậy, kiểu dữ liệu được phép tạo và các tùy chọn an toàn của phiên bản thư viện. Không bật cơ chế tạo object tùy ý từ input không tin cậy. Hãy giới hạn kiểu dữ liệu và dùng cấu hình an toàn được thư viện khuyến nghị.

## 4. Phân biệt serialization với những bài toán gần giống

Không phải mọi thao tác chuyển đổi dữ liệu đều cần một JSON library.

### 4.1. Object-to-object mapping: dùng MapStruct khi phù hợp

Ví dụ ứng dụng có Entity và Response DTO:

~~~java
public class UserEntity {
    private Long id;
    private String email;
    private String passwordHash;
}

public record UserResponse(Long id, String email) {}
~~~

Đây là bài toán chuyển đổi giữa hai mô hình Java trong bộ nhớ. MapStruct có thể sinh code mapping ở compile time; mapping thủ công cũng có thể đủ tốt nếu chỉ có vài trường. Jackson không phải công cụ phù hợp nhất cho bài toán này vì nó được thiết kế chủ yếu để chuyển đổi giữa object và định dạng dữ liệu bên ngoài.

Không nên serialize Entity trực tiếp để tạo response API. Cách đó có thể làm lộ field nội bộ, kéo theo quan hệ lazy của ORM, gây vòng tham chiếu hoặc khiến hợp đồng API phụ thuộc vào cấu trúc database. Hãy định nghĩa DTO cho dữ liệu cần trao đổi.

### 4.2. Validation: dùng Bean Validation hoặc JSON Schema khi cần

Jackson có thể kiểm tra JSON có parse được và có thể ánh xạ vào kiểu Java hay không. Điều đó không đồng nghĩa dữ liệu đã hợp lệ theo nghiệp vụ.

Ví dụ, Jackson có thể đọc một chuỗi thành trường email, nhưng không tự kết luận email đó có đúng định dạng mong muốn hay người gửi có quyền sử dụng nó hay không.

Có thể kết hợp:

- Bean Validation với các annotation như @NotNull, @Size, @Email để kiểm tra DTO.
- JSON Schema khi hợp đồng JSON cần được mô tả và kiểm tra độc lập với Java class.
- Kiểm tra nghiệp vụ trong service/domain layer, chẳng hạn trạng thái đơn hàng có được phép chuyển đổi hay không.

Hãy phân biệt ba bước: parse dữ liệu, kiểm tra cấu trúc/giá trị và xác nhận quy tắc nghiệp vụ.

### 4.3. Java native serialization: tránh dùng cho dữ liệu không tin cậy

Java native serialization gắn dữ liệu nhị phân với cơ chế object serialization của JVM. Nó có thể xuất hiện trong hệ thống cũ hoặc một số tình huống nội bộ, nhưng không nên dùng làm định dạng trao đổi chung giữa các dịch vụ.

Các vấn đề chính gồm:

- Khó tương thích lâu dài khi class thay đổi.
- Dữ liệu khó quan sát và debug hơn JSON.
- Đọc object graph từ nguồn không tin cậy có thể mở ra rủi ro thực thi hành vi nguy hiểm thông qua gadget chain.
- Phụ thuộc vào hệ sinh thái Java và cách triển khai class.

Đối với dữ liệu lưu trữ hoặc trao đổi lâu dài, hãy chọn định dạng có hợp đồng rõ ràng như JSON, Protocol Buffers hoặc Avro tùy yêu cầu. Nếu buộc phải duy trì native serialization trong hệ thống cũ, cần giới hạn nguồn dữ liệu, áp dụng filter phù hợp và có kế hoạch thay thế.

## 5. Các tiêu chí cần đánh giá trước khi quyết định

### 5.1. Định dạng và hợp đồng dữ liệu

Trước tiên xác định dữ liệu là JSON, XML, CSV, YAML hay binary. Sau đó xác định schema có ổn định không, có cần versioning không, có cho phép field mới hay field không biết trước không.

Nếu hợp đồng JSON ổn định, DTO và Jackson Databind thường đơn giản. Nếu cấu trúc thay đổi nhiều, Tree Model hoặc streaming có thể hợp lý hơn. Nếu hợp đồng binary và tương thích schema là yêu cầu chính, hãy xem xét Protobuf hoặc Avro.

### 5.2. Kích thước dữ liệu và giới hạn bộ nhớ

Với request JSON nhỏ hoặc vừa, Databind thường dễ bảo trì. Với file rất lớn, hãy xem xét streaming thay vì đọc toàn bộ nội dung thành String rồi tạo object graph.

Cần đánh giá cả giới hạn kích thước request, độ sâu JSON, số phần tử trong mảng và thời gian xử lý. Một thư viện nhanh vẫn có thể gây sự cố nếu ứng dụng cho phép payload quá lớn hoặc lồng nhau quá sâu.

### 5.3. Ngôn ngữ và nền tảng

Java trên JVM, Kotlin đa nền tảng và Android có hệ sinh thái khác nhau. Jackson thường thuận lợi cho Java backend; kotlinx.serialization có lợi thế khi chia sẻ mô hình Kotlin đa nền tảng; Moshi là một lựa chọn phổ biến trong một số ứng dụng Android/Kotlin.

Hãy chọn thư viện phù hợp với nền tảng chính của dự án và khả năng hỗ trợ của các dependency đang sử dụng.

### 5.4. Khả năng tương thích và bảo trì

Kiểm tra:

- Phiên bản thư viện có được nền tảng quản lý dependency hỗ trợ không.
- Các module đi kèm có cùng dòng phiên bản tương thích không.
- Thư viện có được cập nhật và có tài liệu rõ ràng không.
- Có thể kiểm thử contract bằng payload thực tế không.
- Việc thay đổi serializer có làm thay đổi JSON đã phát hành hay không.

Với Jackson, nên quản lý phiên bản các artifact cùng dòng thông qua dependency management của nền tảng hoặc BOM thích hợp. Tránh tùy tiện trộn các phiên bản khác nhau của core, databind và module.

### 5.5. Bảo mật khi đọc dữ liệu bên ngoài

Dữ liệu JSON từ HTTP, file upload, message broker hoặc webhook đều có thể không đáng tin cậy. Cần:

- Giới hạn kích thước payload và độ sâu lồng nhau phù hợp.
- Chỉ bật polymorphic typing khi có yêu cầu rõ ràng; dùng allowlist kiểu cụ thể.
- Không bật default typing rộng cho dữ liệu không tin cậy.
- Kiểm tra giá trị sau khi parse trước khi đưa vào nghiệp vụ.
- Tránh để lỗi parse trả về stack trace hoặc thông tin nội bộ cho client.
- Cập nhật phiên bản thư viện để nhận các bản vá bảo mật.

Jackson xử lý chuyển đổi dữ liệu; nó không tự biến input bên ngoài thành dữ liệu an toàn.

## 6. Cấu hình Jackson nên được tổ chức như thế nào?

Trong một ứng dụng Java, nên có một cấu hình ObjectMapper thống nhất cho từng bộ quy tắc serialization. Cấu hình module, naming strategy, date format và feature trước khi dùng mapper. Sau khi cấu hình xong, có thể chia sẻ mapper đã cấu hình trong ứng dụng thay vì tạo mới cho từng request.

Ví dụ độc lập cho Jackson 2:

~~~java
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

public final class JsonConfiguration {

    private JsonConfiguration() {
    }

    public static JsonMapper createMapper() {
        return JsonMapper.builder()
            .addModule(new JavaTimeModule())
            .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
            .build();
    }
}
~~~

Đoạn code trên giả định dependency Jackson Databind và jackson-datatype-jsr310 tương thích đã có trong dự án. Trong Spring Boot, hãy kiểm tra auto-configuration và các customizer hiện có trước khi tự khai báo một ObjectMapper mới, vì tạo mapper riêng có thể làm mất các module hoặc quy tắc mà framework đã đăng ký.

Một số nguyên tắc cấu hình:

1. Tạo và cấu hình mapper ở nơi tập trung.
2. Không thay đổi cấu hình mapper sau khi đã đưa vào sử dụng đồng thời.
3. Đăng ký module cần thiết cho kiểu dữ liệu của ứng dụng.
4. Viết test cho JSON đầu ra và đầu vào quan trọng để phát hiện thay đổi hợp đồng.
5. Không bật tính năng permissive chỉ để làm cho một payload bất thường parse được.
6. Tách cấu hình cho các hợp đồng khác nhau khi chúng thực sự cần quy tắc khác nhau; tránh một mapper toàn cục chứa quá nhiều ngoại lệ khó hiểu.

## 7. Ví dụ chọn công cụ theo tình huống

### Tình huống A: REST API quản lý đơn hàng

Backend Java nhận request JSON có cấu trúc ổn định, kiểm tra dữ liệu rồi lưu đơn hàng. Response cũng là JSON.

**Chọn Jackson Databind.** Dùng request/response DTO, Bean Validation và cấu hình Jackson thống nhất. Không cần thêm Gson hoặc Moshi chỉ để ánh xạ một vài DTO.

### Tình huống B: Webhook từ nhiều nhà cung cấp

Mỗi nhà cung cấp gửi JSON có cấu trúc hơi khác nhau; ứng dụng chỉ cần đọc event type, event id và một số trường tùy loại.

**Cân nhắc Jackson Tree Model.** Đọc JsonNode, xác định loại event rồi ánh xạ phần payload tương ứng sang DTO. Nếu các biến thể đã được mô tả rõ và ổn định, có thể dùng Databind với các DTO riêng. Tránh bật polymorphic typing rộng cho dữ liệu webhook không tin cậy.

### Tình huống C: Import file JSON hàng gigabyte

Ứng dụng cần đọc từng record, xử lý và ghi vào database mà không giữ toàn bộ file trong RAM.

**Chọn Jackson Streaming API hoặc JSON-P Streaming.** Đọc token tuần tự, xử lý từng record và giải phóng dữ liệu đã dùng. Thiết kế thêm giới hạn record, xử lý lỗi từng phần và cơ chế resume nếu nghiệp vụ yêu cầu.

### Tình huống D: Hai microservice trao đổi event với schema được quản lý

Payload lớn, nhiều ngôn ngữ cùng tham gia và cần kiểm soát tương thích schema giữa producer và consumer.

**Cân nhắc Avro hoặc Protocol Buffers.** Định nghĩa schema, quy tắc tương thích và quy trình sinh code. JSON/Jackson vẫn có thể được giữ cho API công khai hoặc công cụ quan sát.

### Tình huống E: Ứng dụng Kotlin chia sẻ model giữa Android và iOS

Một phần model được dùng chung trên nhiều nền tảng, không chỉ JVM.

**Cân nhắc kotlinx.serialization.** Khả năng đa nền tảng là tiêu chí quyết định. Jackson có thể vẫn xuất hiện ở backend Java, nhưng không nhất thiết phải là serializer chung cho mọi nền tảng.

### Tình huống F: Xuất báo cáo CSV cho người dùng

Ứng dụng tạo file CSV có header, dấu phẩy trong nội dung, dấu nháy kép và ký tự xuống dòng trong ô.

**Chọn Apache Commons CSV hoặc OpenCSV.** Dùng API xử lý record và escaping theo chuẩn thư viện; không tự nối chuỗi bằng dấu phẩy vì dễ tạo file sai khi dữ liệu có ký tự đặc biệt.

## 8. Checklist lựa chọn

Trước khi thêm hoặc thay thư viện, hãy trả lời các câu hỏi sau:

- [ ] Định dạng dữ liệu thực tế là gì?
- [ ] Dữ liệu có cấu trúc ổn định hay thay đổi theo từng bản tin?
- [ ] Có cần ánh xạ sang DTO, thao tác cây dữ liệu hay xử lý theo luồng?
- [ ] Kích thước payload và giới hạn bộ nhớ là bao nhiêu?
- [ ] Có cần schema, code generation hoặc quy tắc tương thích phiên bản?
- [ ] Ngôn ngữ và nền tảng chính là Java, Kotlin/JVM hay đa nền tảng?
- [ ] Dự án đã có thư viện nào được quản lý và sử dụng thống nhất?
- [ ] Công cụ được chọn có xử lý đúng các trường hợp đặc biệt của định dạng không?
- [ ] Đã có test cho payload đầu vào, đầu ra và dữ liệu lỗi chưa?
- [ ] Đã đặt giới hạn và cấu hình an toàn cho dữ liệu không tin cậy chưa?

Nếu chưa có yêu cầu đặc biệt, Jackson thường là lựa chọn hợp lý cho JSON trong Java backend. Nếu yêu cầu tập trung vào đa nền tảng Kotlin, chuẩn Jakarta, schema nhị phân, XML/CSV chuyên sâu, streaming hoặc mapping giữa các object Java, hãy chọn công cụ được thiết kế cho bài toán đó.

Điều quan trọng là giữ ranh giới rõ ràng: **Jackson chuyển đổi giữa Java object và định dạng dữ liệu; validation kiểm tra dữ liệu; MapStruct chuyển đổi giữa các mô hình object; còn Protobuf/Avro giải quyết hợp đồng dữ liệu nhị phân có schema.** Chọn đúng lớp công cụ giúp code dễ đọc, hợp đồng ổn định và hệ thống dễ bảo trì.


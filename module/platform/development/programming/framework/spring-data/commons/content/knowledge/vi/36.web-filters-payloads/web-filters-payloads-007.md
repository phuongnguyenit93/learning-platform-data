# JSONPath, XPath và dependency tùy chọn cho binding

## 1. Mục tiêu và phạm vi

Trong chương **Bộ lọc và payload web** của module **Spring Data Commons**, payload projection cho phép mô tả dữ liệu cần đọc từ HTTP body bằng một interface. Các accessor có thể dùng JSONPath cho JSON hoặc XPath cho XML thay vì yêu cầu cấu trúc tài liệu trùng hoàn toàn với tên property Java.

Sau bài học, bạn cần:

- Phân biệt JSONPath, XPath và binding JSON thông thường.
- Khai báo interface payload với annotation đúng.
- Xác định dependency tùy chọn cần có cho từng định dạng.
- Hiểu vai trò của HTTP message converter và Spring Data Web support.
- Nhận diện lỗi do thiếu thư viện, sai đường dẫn, sai media type hoặc thiếu dữ liệu.
- Chuyển dữ liệu đã đọc thành command được kiểm tra trước khi gọi nghiệp vụ.

Bài dùng Spring MVC. Những ví dụ nhắc `ProjectingJackson2HttpMessageConverter` thuộc nhánh tích hợp **Jackson 2** có API tương ứng; cần chọn dependency theo phiên bản Spring Data và Spring Framework của dự án. Không trộn converter Jackson 2 với cấu hình Jackson của một nhánh API khác chỉ vì cùng xử lý JSON.

Đây là khả năng tích hợp web của Commons. Nó không phụ thuộc riêng vào JPA và không tự cung cấp implementation truy vấn cho các loại store.

## 2. JSONPath và XPath giải quyết việc gì?

Giả sử tài liệu JSON có cấu trúc:

~~~json
{
  "customer": {
    "name": {
      "first": "Phương"
    },
    "email": "phuong@example.test"
  }
}
~~~

Đường dẫn JSONPath:

~~~text
$.customer.name.first
$.customer.email
~~~

chỉ đến hai giá trị ứng dụng cần đọc.

Tài liệu XML tương ứng:

~~~xml
<customer>
    <name>
        <first>Phương</first>
    </name>
    <email>phuong@example.test</email>
</customer>
~~~

có thể dùng XPath:

~~~text
/customer/name/first
/customer/email
~~~

Hai loại biểu thức cùng phục vụ việc chọn dữ liệu, nhưng cú pháp và mô hình tài liệu khác nhau:

| Thành phần | JSONPath | XPath |
| --- | --- | --- |
| Tài liệu | JSON | XML |
| Root trong ví dụ | `$` | `/customer` |
| Chọn phần tử con | `$.customer.email` | `/customer/email` |
| Chọn thuộc tính XML | Không dùng cú pháp XML này | Ví dụ `/customer/@code` |
| Thư viện liên quan trong tích hợp của bài | Jayway JsonPath | XMLBeam |
| Annotation accessor | `@JsonPath` | `@XBRead` |

Không dùng JSONPath như một predicate Querydsl hoặc một biểu thức SQL. Nó chọn dữ liệu trong tài liệu payload; nó không truy vấn repository.

Tương tự, XPath trong bài được đánh giá trên XML đầu vào, không phải một ngôn ngữ để đọc tùy ý nội dung của database.

## 3. Các lớp và annotation cần nhận diện

~~~java
org.springframework.data.web.ProjectedPayload
org.springframework.data.web.JsonPath
org.xmlbeam.annotation.XBRead
~~~

Vai trò của từng annotation:

| Annotation | Vai trò |
| --- | --- |
| `@ProjectedPayload` | Đánh dấu interface dùng làm payload projection trong tích hợp web |
| `@JsonPath` | Gắn biểu thức JSONPath với accessor |
| `@XBRead` | Gắn biểu thức XPath của XMLBeam với accessor |

`@JsonPath` ở đây là annotation của Spring Data Web. Nó không phải class API `com.jayway.jsonpath.JsonPath` dùng để thao tác trực tiếp với thư viện Jayway.

Hạ tầng converter tạo đối tượng triển khai interface ở thời điểm chạy, thường qua cơ chế projection/proxy. Không cần tự viết một class setter/getter chỉ để đáp ứng interface này.

Tuy vậy, một interface có annotation không tự làm cho converter phù hợp xuất hiện trên classpath hoặc trong cấu hình MVC.

## 4. Dependency tùy chọn: tùy theo tính năng được sử dụng

Spring Data Commons không buộc mọi ứng dụng mang theo toàn bộ thư viện cho JSONPath và XMLBeam. Ứng dụng dùng khả năng tương ứng phải bảo đảm các thành phần cần thiết thực sự có mặt.

| Tính năng | Artifact cần quan tâm |
| --- | --- |
| API projection và tích hợp Spring Data Web | `org.springframework.data:spring-data-commons` |
| Hạ tầng HTTP MVC | Các dependency Spring MVC của ứng dụng |
| Projection JSONPath trong nhánh Jackson 2 | Jackson 2 cùng `com.jayway.jsonpath:json-path` |
| Projection XPath qua XMLBeam | `org.xmlbeam:xmlprojector` |
| Kiểm tra Bean Validation nếu ứng dụng chọn dùng | Validation API cùng implementation phù hợp |

“Optional” ở đây không có nghĩa thiếu thư viện thì mọi khả năng vẫn chạy được. Nó có nghĩa ứng dụng không sử dụng tính năng đó không bắt buộc nhận dependency của tính năng như một phần mặc định của Commons.

### 4.1. Ví dụ khai báo Maven

Nếu dự án đã có Spring Data Commons và Spring MVC qua starter, không cần khai báo lại chỉ để lặp dependency.

Phần bổ sung cho JSONPath có hình dạng:

~~~xml
<dependency>
    <groupId>com.jayway.jsonpath</groupId>
    <artifactId>json-path</artifactId>
</dependency>
~~~

Nếu dùng XMLBeam:

~~~xml
<dependency>
    <groupId>org.xmlbeam</groupId>
    <artifactId>xmlprojector</artifactId>
</dependency>
~~~

Các snippet không ghi version vì giả định dependency management tương ứng đã cung cấp version phù hợp. Nếu BOM hoặc parent không quản lý một artifact, ứng dụng phải khai báo version rõ ràng theo bộ dependency tương thích.

Không hiểu việc bỏ version trong ví dụ là Maven sẽ tự chọn một version bất kỳ.

### 4.2. Biên dịch, chạy và kiểm tra là ba phạm vi khác nhau

Nếu source import:

~~~java
import org.xmlbeam.annotation.XBRead;
~~~

XMLBeam cần khả dụng khi biên dịch source đó.

Nếu production runtime phải thực hiện JSONPath projection, Jayway JsonPath cần có trong runtime artifact. Chỉ thêm thư viện ở test scope không giải quyết đường production.

Một bộ test của Spring MVC có thể mang JsonPath để hỗ trợ assertion `jsonPath(...)`. Việc test assertion chạy được chưa chứng minh thư viện đó được đóng gói cho ứng dụng thật.

Phân biệt rõ:

| Phạm vi | Câu hỏi cần trả lời |
| --- | --- |
| Compile | Annotation và các class tham chiếu trong source có được tìm thấy không |
| Runtime | Converter và engine cần dùng có nằm trong ứng dụng đã đóng gói không |
| Test | Test đang mượn dependency nào mà production không có |

Đối với thư viện chia sẻ, dependency optional còn ảnh hưởng việc consumer có tự nhận dependency bắc cầu hay không. Consumer dùng tính năng nên khai báo yêu cầu của mình rõ ràng.

## 5. Payload JSON bằng JSONPath

~~~java
import org.springframework.data.web.JsonPath;
import org.springframework.data.web.ProjectedPayload;

@ProjectedPayload
public interface CustomerJsonPayload {

    @JsonPath("$.customer.name.first")
    String getFirstName();

    @JsonPath("$.customer.email")
    String getEmail();
}
~~~

Với JSON ở phần đầu:

~~~text
getFirstName() -> "Phương"
getEmail()     -> "phuong@example.test"
~~~

Tên method `getFirstName` không yêu cầu tài liệu có property phẳng tên `firstName`, vì annotation đã chỉ rõ nơi đọc.

Đây là khả năng trích xuất dữ liệu theo đường dẫn, không phải một phép biến đổi schema đầy đủ.

### 5.1. Nhiều đường dẫn thay thế

Có thể khai báo các vị trí thay thế:

~~~java
@JsonPath({
    "$.customer.email",
    "$.email"
})
String getEmail();
~~~

Cách này hữu ích khi cần hỗ trợ có chủ đích hai hình dạng payload. Nó không tự hợp nhất hai email thành một giá trị nghiệp vụ.

Cần xác định và kiểm tra trường hợp:

- Chỉ đường dẫn thứ nhất tồn tại.
- Chỉ đường dẫn thứ hai tồn tại.
- Cả hai cùng có dữ liệu.
- Một đường dẫn có null hoặc chuỗi rỗng.
- Cả hai đều không có dữ liệu.

Không dựa vào một phỏng đoán về fallback để giải quyết payload có hai giá trị mâu thuẫn. Nếu hợp đồng cần từ chối mâu thuẫn, phải có logic kiểm tra phù hợp.

### 5.2. Cardinality phải phù hợp với kiểu trả về

Một đường dẫn tới đúng một giá trị khác với đường dẫn dùng wildcard chọn nhiều giá trị.

~~~java
@JsonPath("$.customer.aliases[*]")
java.util.List<String> getAliases();
~~~

Accessor tập hợp phù hợp hơn một accessor String nếu hợp đồng trả về danh sách alias.

Không dùng `$..email` chỉ để “tìm email ở bất kỳ đâu” nếu payload có thể chứa email của nhiều người. Recursive descent có thể chọn dữ liệu ngoài vị trí nghiệp vụ cần đọc.

Với field quan trọng, ưu tiên đường dẫn đủ cụ thể và kiểm tra dữ liệu được chọn.

## 6. Payload XML bằng XPath và XMLBeam

~~~java
import org.springframework.data.web.ProjectedPayload;
import org.xmlbeam.annotation.XBRead;

@ProjectedPayload
public interface CustomerXmlPayload {

    @XBRead("/customer/name/first")
    String getFirstName();

    @XBRead("/customer/email")
    String getEmail();
}
~~~

Ở đây annotation XPath đến từ XMLBeam. Chỉ thêm một Jackson XML mapper không đồng nghĩa XMLBeam projection tự hoạt động.

Nếu tài liệu dùng XML namespace, đường dẫn không có namespace trong ví dụ không tự trở thành đúng cho mọi tài liệu. Cần cấu hình và kiểm tra XPath theo namespace của payload thực tế.

Tương tự, `//email` rộng hơn `/customer/email`; nó có thể khớp nhiều vị trí. Đừng dùng đường dẫn rộng để che một schema chưa được hiểu rõ.

### 6.1. Có thể gắn cả hai loại annotation không?

Một interface có thể mô tả accessor bằng cả JSONPath và XPath nếu ứng dụng chủ động hỗ trợ cả hai engine.

Ví dụ:

~~~java
@ProjectedPayload
public interface CustomerPayload {

    @JsonPath("$.customer.email")
    @XBRead("/customer/email")
    String getEmail();
}
~~~

Snippet cần các import tương ứng từ phần trước.

Hệ quả dependency rất cụ thể: source interface này tham chiếu cả annotation Spring Data lẫn XMLBeam. Dự án biên dịch nó cần class của các annotation đó, dù một endpoint cụ thể chỉ nhận JSON.

Nếu chỉ có nhu cầu JSON, tách interface JSON như ví dụ trước giúp hợp đồng và yêu cầu dependency rõ ràng hơn. Không thêm XMLBeam chỉ vì một đoạn code mẫu đã ghép hai annotation.

## 7. HTTP message converter là thành phần thực sự đọc body

Luồng xử lý khái niệm:

~~~text
HTTP request
    |
    +-- Content-Type xác định định dạng đầu vào
    |
    v
MVC chọn HttpMessageConverter có thể đọc kiểu tham số
    |
    +-- JSON: projection converter + Jackson + JsonPath
    |
    +-- XML: XMLBeam converter + XMLBeam
    |
    v
Payload projection interface
    |
    v
Đọc accessor -> kiểm tra -> command ứng dụng
    |
    v
Service nghiệp vụ -> repository/template nếu có
~~~

Trong nhánh API của ví dụ, hai converter cần nhận diện là:

~~~java
org.springframework.data.web.ProjectingJackson2HttpMessageConverter
org.springframework.data.web.XmlBeamHttpMessageConverter
~~~

Spring Data Web support có cơ chế đăng ký các converter phù hợp khi tích hợp tương ứng được bật và dependency cần thiết có trên classpath.

Không chỉ kiểm tra sự hiện diện của annotation. Cần xác nhận converter thích hợp có trong cấu hình MVC thực tế, đặc biệt khi ứng dụng đã tùy chỉnh danh sách converter.

### 7.1. Converter thông thường và converter projection

Một Jackson converter có thể đọc DTO hoặc record thông thường. Điều đó chưa chứng minh nó sẽ tạo payload projection interface với ý nghĩa JSONPath của Spring Data.

Nếu converter khác nhận xử lý trước nhưng không hỗ trợ interface projection đúng cách, request có thể thất bại dù engine JsonPath đã nằm trong dependency tree.

Thứ tự converter và điều kiện `canRead` đều có ý nghĩa. Không giải quyết lỗi bằng cách thêm lặp nhiều instance mà chưa biết converter nào đang được chọn.

### 7.2. Cấu hình MVC thủ công cần giữ các converter khác

Nếu dự án tự cấu hình message converters, cần thêm các converter projection vào cơ chế mở rộng phù hợp và giữ converter phục vụ các kiểu request/response còn lại.

Trong MVC, việc thay toàn bộ danh sách converter và việc mở rộng danh sách hiện có là hai hành động khác nhau. Chỉ phục vụ payload projection không có nghĩa response DTO của ứng dụng không còn cần một JSON converter thông thường.

Đối với Jackson, cũng cần bảo toàn những thiết lập của ObjectMapper như module ngày giờ, naming policy hoặc các cấu hình mà ứng dụng đã công bố. Một converter tạo với ObjectMapper mặc định riêng có thể không dùng cùng chính sách với converter hiện tại.

### 7.3. Client HTTP không tự kế thừa cấu hình MVC phía server

Nếu dùng RestTemplate theo nhánh API tương ứng, có thể cần đăng ký converter trên chính client:

~~~java
import org.springframework.data.web.ProjectingJackson2HttpMessageConverter;
import org.springframework.data.web.XmlBeamHttpMessageConverter;
import org.springframework.web.client.RestTemplate;

RestTemplate client = new RestTemplate();

client.getMessageConverters().add(
        0, new ProjectingJackson2HttpMessageConverter());

client.getMessageConverters().add(
        0, new XmlBeamHttpMessageConverter());
~~~

Snippet minh họa client chủ động hỗ trợ cả hai định dạng, giả định các dependency đều hiện diện. Nếu chỉ dùng JSON thì không khởi tạo converter XML.

Việc thêm phía đầu danh sách giúp các converter projection có cơ hội được xét trước các converter tổng quát; vẫn cần kiểm tra kiểu dữ liệu và media type của lời gọi cụ thể.

Nếu ứng dụng có ObjectMapper đã tùy chỉnh, hãy cấu hình converter JSON của client nhất quán với yêu cầu đó thay vì mặc định snippet tối giản này đã phản ánh đầy đủ cấu hình.

Không kết luận RestClient, WebClient hoặc một HTTP client khác dùng cùng cơ chế chỉ vì ví dụ RestTemplate chạy được. Mỗi client có điểm mở rộng riêng.

## 8. Controller nhận JSON hoặc XML và chuyển thành command

Ví dụ chọn một endpoint xem trước dữ liệu, không thực hiện lưu:

~~~java
public record CustomerCommand(String firstName, String email) {
}
~~~

~~~java
public record CustomerPreview(String firstName, String email) {
}
~~~

Controller:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class CustomerPreviewController {

    @PostMapping(
            value = "/customer-previews",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public CustomerPreview fromJson(
            @RequestBody CustomerJsonPayload payload) {

        CustomerCommand command = command(
                payload.getFirstName(),
                payload.getEmail());

        return new CustomerPreview(
                command.firstName(), command.email());
    }

    @PostMapping(
            value = "/customer-previews",
            consumes = MediaType.APPLICATION_XML_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public CustomerPreview fromXml(
            @RequestBody CustomerXmlPayload payload) {

        CustomerCommand command = command(
                payload.getFirstName(),
                payload.getEmail());

        return new CustomerPreview(
                command.firstName(), command.email());
    }

    private static CustomerCommand command(
            String firstName, String email) {

        return new CustomerCommand(
                requiredText("firstName", firstName),
                requiredText("email", email));
    }

    private static String requiredText(
            String field, String value) {

        if (value == null || value.isBlank()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "Thiếu giá trị bắt buộc: " + field);
        }

        return value.strip();
    }
}
~~~

Mỗi kiểu public đặt trong file Java riêng khi triển khai. Các snippet không tạo một bộ source Java hoàn chỉnh trong một file duy nhất.

Ví dụ chỉ kiểm tra giá trị bắt buộc và loại bỏ khoảng trắng đầu/cuối. Nó chưa kiểm tra đầy đủ cú pháp email, độ dài, tính duy nhất hay quy tắc nghiệp vụ.

Những kiểm tra bổ sung có thể được đặt trên command hoặc trong tầng ứng dụng. Nếu dùng Bean Validation, cần có API/provider và cần thực sự gọi validation theo đường phù hợp; không mặc định mọi getter trên projection sẽ được kiểm tra như một DTO đã được cấu hình validation.

### 8.1. Content-Type và Accept có vai trò khác nhau

Request JSON:

~~~http
POST /customer-previews
Content-Type: application/json
Accept: application/json
~~~

Request XML:

~~~http
POST /customer-previews
Content-Type: application/xml
Accept: application/json
~~~

Cả hai method đều trả JSON trong ví dụ. XML input không đòi response cũng phải là XML.

- `Content-Type` mô tả body mà server cần đọc.
- `Accept` mô tả định dạng phản hồi mà client chấp nhận.

Chỉ đặt `Accept: application/xml` không làm một body JSON được đọc bằng XPath.

### 8.2. Đọc accessor trong phạm vi xử lý rõ ràng

Payload projection có thể đánh giá một số thông tin khi accessor được gọi. Vì vậy, request đã tạo được proxy chưa đủ chứng minh mọi đường dẫn đã đọc thành công.

Ví dụ controller đọc các giá trị cần thiết rồi tạo command trước khi tiếp tục. Cách này làm ranh giới giữa projection và dữ liệu nghiệp vụ rõ ràng hơn.

Không truyền một proxy payload đi qua nhiều tầng hoặc lưu nó để xử lý bất đồng bộ rồi giả định mọi lỗi binding đã xuất hiện tại thời điểm MVC đọc body.

### 8.3. Binding không phải persist

Controller không gọi repository và không sửa entity.

Nếu sau này endpoint cần tạo khách hàng, tầng ứng dụng sẽ nhận command đã kiểm tra rồi thực hiện quy tắc nghiệp vụ và lưu bằng mô-đun thích hợp.

Không đưa payload projection trực tiếp vào lệnh lưu chỉ vì tên getter giống tên property entity. Những field như id, version, tenant hoặc thông tin auditing cần được xử lý theo chính sách của ứng dụng.

## 9. Missing, null, kiểu sai và payload thừa

Một annotation đường dẫn chỉ mô tả nơi đọc dữ liệu; nó không thay thế schema validation.

| Trường hợp | Quyết định ứng dụng cần có |
| --- | --- |
| Không có đường dẫn | Cho phép thiếu hay trả lỗi bắt buộc |
| Giá trị JSON null | Có đồng nghĩa không gửi hay không |
| Chuỗi rỗng hoặc chỉ có khoảng trắng | Chuẩn hóa hay từ chối |
| Path chọn nhiều giá trị | Dùng collection hay coi là vi phạm hợp đồng |
| Giá trị không phù hợp kiểu accessor | Xử lý lỗi chuyển đổi thế nào |
| Field ngoài projection | Bỏ qua hay từ chối theo schema |
| Hai path thay thế có giá trị mâu thuẫn | Ưu tiên hoặc từ chối ra sao |

Hành vi cụ thể khi path không tồn tại còn phụ thuộc engine, converter, cấu hình và loại accessor. Cần kiểm tra thay vì mặc định mọi trường hợp đều trả null hoặc mọi trường hợp đều ném cùng một exception.

Dùng kiểu primitive cho dữ liệu bắt buộc có thể che mờ câu hỏi “giá trị có được gửi không”. Nếu cần phân biệt thiếu với giá trị số 0 hoặc boolean false, hãy thiết kế kiểu và validation tương ứng.

Field không được projection đọc không tự biến thành một lỗi “unknown property”. Một projection chỉ lấy hai field không đồng nghĩa payload đã bị giới hạn đúng hai field ở cấp schema.

## 10. Chẩn đoán lỗi theo từng tầng

### 10.1. Thiếu thư viện hoặc không có converter

Các triệu chứng có thể gồm:

- Không tìm thấy class của engine khi chạy.
- Không có converter đọc được interface với media type đã gửi.
- Một converter tổng quát cố deserialize interface và thất bại.
- Test thành công nhưng runtime artifact thiếu dependency.

Cách kiểm tra nên đi theo thứ tự:

1. Source có tham chiếu annotation hoặc class nào?
2. Artifact chứa class đó có trong phạm vi compile/runtime cần thiết không?
3. Runtime có engine cho đường JSONPath hoặc XPath đang dùng không?
4. MVC có đăng ký converter phù hợp không?
5. Converter nào thực sự được chọn cho request?

Mã HTTP không đủ để kết luận thiếu dependency nào. Tùy vị trí lỗi, ứng dụng có thể gặp lỗi khởi động, lỗi đọc body hoặc lỗi không hỗ trợ media type.

### 10.2. Converter đúng nhưng đường dẫn sai

Nếu body được đọc nhưng giá trị cần thiết không đúng, hãy kiểm tra:

- Tên field và mức lồng của JSON.
- Root element và namespace của XML.
- Phân biệt chữ hoa/chữ thường trong tên.
- Cardinality của path.
- Kiểu trả về accessor.
- Cách engine xử lý missing và null.
- Dữ liệu thực sự đã được gửi, không chỉ một payload mẫu khác.

Không thêm recursive descent hoặc XPath `//` chỉ để làm một test tạm thời xanh. Đường dẫn rộng có thể chọn nhầm một giá trị hợp lệ ở vị trí khác.

### 10.3. Lỗi ứng dụng và lỗi input không nên bị gom chung

Một biểu thức sai nằm cố định trong annotation là lỗi cấu hình/source của server. Nó khác với một JSON body bị client viết sai cú pháp.

Không catch mọi lỗi projection rồi trả HTTP 400 một cách máy móc. Hãy ánh xạ lỗi input được nhận diện rõ, đồng thời giữ khả năng phát hiện lỗi triển khai.

Tương tự, lỗi thiếu engine không phải một payload “không có khách hàng”.

## 11. Giới hạn tài nguyên và cấu hình parser

Đường dẫn do ứng dụng khai báo trong annotation dễ kiểm soát hơn việc nhận nguyên một JSONPath/XPath tùy ý từ client.

Nếu sản phẩm thực sự cần cho client truyền biểu thức, đó là một hợp đồng khác, cần giới hạn cú pháp, phạm vi truy cập dữ liệu và chi phí đánh giá rõ ràng.

Đối với payload đầu vào, ứng dụng cũng cần giới hạn dung lượng và độ phức tạp phù hợp. JSONPath recursive hoặc XPath quá rộng không phải công cụ thay thế một schema cụ thể.

Với XML từ bên ngoài, cấu hình parser phải phù hợp chính sách ứng dụng về DTD, external entities và truy cập tài nguyên ngoài. Việc thêm XMLBeam vào dependency không tự chứng minh những thiết lập đó đã đúng.

Các quyết định này thuộc cấu hình hạ tầng và hợp đồng đầu vào, không thuộc khả năng lưu trữ của JPA, MongoDB hoặc một mô-đun Spring Data khác.

## 12. Kiểm tra cấu hình và hợp đồng binding

### 12.1. Kiểm tra JSON theo đường HTTP

Với MockMvc đã đăng ký converter tương ứng:

~~~java
mockMvc.perform(post("/customer-previews")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .content("""
            {
              "customer": {
                "name": {
                  "first": "Phương"
                },
                "email": "phuong@example.test"
              }
            }
            """))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.firstName").value("Phương"))
    .andExpect(jsonPath("$.email")
            .value("phuong@example.test"));
~~~

Snippet dùng Java text block, giả định MockMvc và các static import tương ứng đã có.

Assertion `jsonPath(...)` trong test đọc **response**. Annotation `@JsonPath` trong payload interface đọc **request body**. Hai hoạt động khác nhau dù đều có liên quan đến JSONPath.

### 12.2. Kiểm tra XML độc lập

~~~java
mockMvc.perform(post("/customer-previews")
        .contentType(MediaType.APPLICATION_XML)
        .accept(MediaType.APPLICATION_JSON)
        .content("""
            <customer>
                <name>
                    <first>Phương</first>
                </name>
                <email>phuong@example.test</email>
            </customer>
            """))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.firstName").value("Phương"));
~~~

Test JSON thành công không chứng minh XML converter và XMLBeam đã hoạt động.

Nếu ứng dụng chỉ hỗ trợ JSON, không cần tạo thêm contract XML chỉ để “đủ hai ví dụ”. Khi đó cần kiểm tra XML bị xử lý theo chính sách định dạng không được hỗ trợ của endpoint.

### 12.3. Ma trận kiểm tra tối thiểu

| Nhóm | Tình huống |
| --- | --- |
| JSON hợp lệ | Path đơn đọc đúng dữ liệu nested |
| JSON path thay thế | Từng shape, cả hai shape và giá trị mâu thuẫn |
| XML hợp lệ | Root/path đúng, trường hợp có namespace nếu được hỗ trợ |
| Giá trị bắt buộc | Missing, null, blank |
| Kiểu và cardinality | Scalar, collection, giá trị sai kiểu |
| Cú pháp tài liệu | JSON/XML không hợp lệ |
| Media type | Content-Type đúng, sai hoặc không được endpoint hỗ trợ |
| Dependency | Engine có trong runtime, không chỉ test |
| Cấu hình MVC | Test context thật có đăng ký converter |
| Chuẩn hóa và validation | Command nhận đúng giá trị và quy tắc nghiệp vụ cần thiết |

Một test tự tạo projection factory hoặc gọi thư viện Jayway trực tiếp chỉ chứng minh đường gọi đó. Nó chưa chứng minh Spring MVC chọn đúng HTTP message converter.

Nếu test standalone tự đăng ký converter còn ứng dụng thật không scan cấu hình cần thiết, kết quả test có thể che lỗi wiring. Cần một kiểm tra với context tương ứng của ứng dụng.

## 13. Khi nào nên dùng payload projection?

| Nhu cầu | Lựa chọn nên cân nhắc |
| --- | --- |
| Chỉ đọc vài giá trị từ tài liệu nested có cấu trúc đã biết | Payload projection với path cụ thể |
| DTO/record ánh xạ trực tiếp schema đơn giản | Binding JSON thông thường |
| Nhiều quy tắc validation và thông báo lỗi theo field | DTO/command có validation rõ ràng |
| Một ít shape đầu vào thay thế đã được công bố | Path thay thế cùng kiểm tra xung đột |
| Biến đổi schema lớn, chuẩn hóa phức tạp | Mapper hoặc quy trình xử lý tường minh |
| Chỉ dùng JSON | Chỉ thêm engine JSONPath nếu thực sự cần tính năng đó |
| Hỗ trợ XML/XPath | XMLBeam cùng converter và cấu hình XML phù hợp |

Payload projection hữu ích khi nó làm rõ dữ liệu cần đọc. Nếu accessor chứa quá nhiều path thay thế hoặc logic tương thích lịch sử, cần đánh giá lại hợp đồng thay vì tiếp tục mở rộng annotation không giới hạn.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| @JsonPath biên dịch nhưng request không bind | Thiếu engine hoặc converter | Kiểm tra runtime dependency và MVC |
| @XBRead không biên dịch | Source không có annotation XMLBeam | Thêm dependency cho tính năng XML hoặc bỏ tham chiếu không cần |
| Chỉ test chạy được JSONPath | Thư viện chỉ nằm trong test scope | Kiểm tra runtime artifact |
| Jackson thông thường không tạo được interface | Đường projection converter chưa được dùng | Xác nhận converter và thứ tự |
| Đổi XML mapper nhưng XPath vẫn không chạy | Nhầm XML serialization với XMLBeam projection | Cấu hình đúng engine/converter |
| Giá trị đọc nhầm từ một nhánh khác | Path quá rộng | Dùng path cụ thể |
| Field thừa không bị từ chối | Projection không phải schema validator | Thêm validation/schema policy nếu hợp đồng yêu cầu |
| Field bắt buộc vẫn thiếu | Chỉ khai báo path, chưa kiểm tra | Chuyển sang command và validate |
| XML request bị hiểu là cần XML response | Nhầm Content-Type với Accept | Khai báo consumes và produces rõ ràng |
| Service giữ proxy payload lâu dài | Ranh giới đọc dữ liệu không rõ | Trích xuất giá trị trong phạm vi xử lý và tạo command |

## 15. Bài thực hành

1. Tạo một payload JSON nested và interface dùng hai đường dẫn JSONPath cụ thể.
2. Xác định rõ dependency nào có sẵn qua starter, dependency nào phải bổ sung cho JsonPath.
3. Kiểm tra thư viện cần thiết có trong runtime, không chỉ test scope.
4. Nếu ứng dụng cần XML, tạo interface XPath riêng và đăng ký tích hợp XMLBeam phù hợp.
5. Đọc dữ liệu thành command và kiểm tra các trường bắt buộc trước khi gọi nghiệp vụ.
6. Kiểm tra missing, null, blank, sai kiểu và một đường dẫn chọn nhiều giá trị.
7. Nếu dùng path thay thế, mô tả cách xử lý payload có hai giá trị mâu thuẫn.
8. Kiểm tra request qua MVC với Content-Type và Accept rõ ràng.
9. Giải thích vì sao binding thành công không đồng nghĩa validation hoặc persist thành công.

Bài thực hành đạt yêu cầu khi bạn chỉ ra được **engine nào đọc định dạng nào**, **dependency nằm ở phạm vi nào**, **converter nào tạo projection**, và **dữ liệu được kiểm tra ở đâu trước khi đi vào nghiệp vụ**.

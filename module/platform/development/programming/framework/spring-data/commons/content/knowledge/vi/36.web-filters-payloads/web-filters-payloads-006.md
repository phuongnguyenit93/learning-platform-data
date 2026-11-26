# Projection đầu vào với @ProjectedPayload

Một request đăng ký khách hàng có thể chứa thông tin tên, liên hệ và nhiều trường khác. Controller thường chỉ cần đọc một tập dữ liệu cụ thể để tạo lệnh nghiệp vụ. `@ProjectedPayload` cho phép mô tả góc nhìn đầu vào bằng một interface projection, thay vì yêu cầu lớp nhận dữ liệu phải có cấu trúc Java trùng khít với toàn bộ tài liệu JSON hoặc XML.

Trong chương **Bộ lọc và payload web** của **Spring Data Commons**, cơ chế này thuộc phần tích hợp web và projection. Nó giúp đọc payload theo một hợp đồng khai báo; việc kiểm tra dữ liệu, xác định tenant, áp dụng quyền, tạo entity và gọi repository vẫn là trách nhiệm riêng. Projection đầu vào cũng không làm thay đổi khả năng truy vấn, mapping hoặc auditing của từng module lưu trữ.

## 1. Projection đầu vào khác projection kết quả truy vấn

Hai cơ chế cùng dùng ý tưởng một góc nhìn của dữ liệu, nhưng nguồn dữ liệu khác nhau:

| Cơ chế | Nguồn dữ liệu | Mục tiêu |
|---|---|---|
| Projection repository | Kết quả truy vấn/domain object | Chọn hình dạng dữ liệu đọc từ repository theo khả năng module |
| Projection đầu vào | Request body JSON/XML | Đọc dữ liệu HTTP qua các accessor được khai báo |
| DTO request thông thường | Request body được deserialize vào class/record | Tạo một object dữ liệu có cấu trúc do ứng dụng định nghĩa |

`@ProjectedPayload` đánh dấu interface dùng cho projection đầu vào. Các getter mô tả dữ liệu cần đọc; annotation đường dẫn có thể định vị dữ liệu ở một cấu trúc lồng nhau khác với tên getter.

Nó không có nghĩa database chỉ đọc một vài cột. Khi HTTP request đang được chuyển thành projection, có thể chưa có truy vấn repository nào xảy ra.

Một getter tên `getEmail()` không chứng minh dữ liệu đã là email hợp lệ, đã thuộc người dùng hiện tại hoặc được phép dùng để cập nhật một entity.

## 2. Đường đi từ request đến repository

Một thiết kế rõ ràng có thể là:

```text
Request body
    → message converter hỗ trợ projected payload
    → interface projection
    → đọc các giá trị cần thiết
    → command/DTO nghiệp vụ đã chuẩn hóa và kiểm tra
    → service áp dụng quyền và phạm vi dữ liệu
    → tạo hoặc thay đổi domain object
    → repository của module thực hiện persistence
    → response DTO
```

Projection là ranh giới đọc dữ liệu HTTP. Nó không tự gọi `save`, không tự tìm entity theo ID trong body và không tự mở một transaction nghiệp vụ.

Việc chuyển projection sang command hữu ích khi service cần một đối tượng dữ liệu độc lập với cơ chế đọc JSON/XML. Service không cần biết giá trị tên được đọc bằng JSONPath nào hoặc request ban đầu có cấu trúc lồng nhau ra sao.

Response DTO là một hợp đồng khác. Không cần trả lại chính proxy đầu vào chỉ vì nó đã có sẵn ở controller.

## 3. Điều kiện để projected payload hoạt động

Các ví dụ dùng Spring MVC và hạ tầng Spring Data Web tương ứng. Cần có:

1. Interface được đánh dấu `@ProjectedPayload`.
2. Message converter có khả năng tạo projection từ loại payload được nhận.
3. Các thư viện tùy chọn cần thiết cho cơ chế đường dẫn được dùng.
4. Cấu hình HTTP nhận đúng media type và chuyển đổi kiểu phù hợp.

Với cấu hình Spring MVC chủ động, có thể bật hỗ trợ Spring Data Web:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.web.config.EnableSpringDataWebSupport;

@Configuration
@EnableSpringDataWebSupport
class DataWebConfiguration {
}
```

Khi các dependency tương ứng có mặt và bộ phiên bản hỗ trợ tích hợp này, hạ tầng Spring Data Web có thể đăng ký converter dành cho projected payload. JSONPath thường gắn với thư viện JsonPath; đường XML dùng cơ chế XmlBeam và annotation của nó.

Một ứng dụng Spring Boot phù hợp có thể đã có một phần cấu hình tự động. Không thêm cấu hình chồng nhau mà chưa xác định converter đang xử lý request.

Chỉ thêm Jackson thông thường không đồng nghĩa mọi interface Java đều tự deserialize được như một projected payload. Nếu converter chuyên biệt chưa được đăng ký hoặc không được chọn, request có thể đi vào một đường deserialize khác và thất bại vì interface không có cách tạo instance thông thường.

Cần dùng bộ dependency tương thích với Spring Data, Spring MVC và phiên bản Jackson của ứng dụng. Không sao chép tên lớp converter của một phiên bản khác rồi coi đó là cấu hình chắc chắn phù hợp.

## 4. Interface projection JSON đầu vào

Giả sử API nhận JSON:

```json
{
  "customer": {
    "name": "Nguyễn Lan",
    "contact": {
      "email": "lan@example.com"
    }
  }
}
```

Interface có thể đọc hai giá trị cần dùng:

```java
import org.springframework.data.web.JsonPath;
import org.springframework.data.web.ProjectedPayload;

@ProjectedPayload
public interface RegisterCustomerPayload {

    @JsonPath("$.customer.name")
    String getName();

    @JsonPath("$.customer.contact.email")
    String getEmail();
}
```

`getName()` trả góc nhìn của đường `$.customer.name`. Getter không bắt buộc tên thuộc tính Java phải tái hiện toàn bộ cây object `customer.contact`.

Annotation `org.springframework.data.web.JsonPath` là metadata cho cơ chế đọc payload. Nó khác với việc ứng dụng tự gọi API của thư viện JsonPath ở mọi controller.

Đường dẫn được ứng dụng khai báo, không phải một biểu thức do client tùy ý truyền vào. Client cung cấp giá trị theo schema của request, còn ứng dụng quyết định vùng dữ liệu nào được đọc.

Nếu bỏ annotation đường dẫn, cơ chế truy cập thuộc tính mặc định của projection cần được hiểu theo hạ tầng đang dùng. Với một hợp đồng đầu vào lồng nhau quan trọng, đường dẫn tường minh giúp thể hiện rõ kỳ vọng của API.

## 5. Controller: đọc một lần rồi tạo command

Ví dụ command sử dụng Bean Validation theo namespace Jakarta:

```java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

record RegisterCustomerCommand(
        @NotBlank @Size(max = 100) String name,
        @NotBlank @Email @Size(max = 254) String email) {

    static RegisterCustomerCommand from(RegisterCustomerPayload payload) {
        String rawName = payload.getName();
        String rawEmail = payload.getEmail();

        return new RegisterCustomerCommand(
                normalize(rawName),
                normalize(rawEmail));
    }

    private static String normalize(String value) {
        return value == null ? null : value.strip();
    }
}
```

Ví dụ giả định phiên bản Java hỗ trợ record và `String.strip()`. Các giới hạn độ dài là chính sách minh họa của ứng dụng, không phải giá trị mặc định của Spring Data.

`@Email` không xác minh người dùng sở hữu hộp thư hoặc địa chỉ đó nhận được thư. Nó là ràng buộc hình thức theo provider validation; `@NotBlank` bổ sung yêu cầu có nội dung.

Controller kiểm tra command trước khi gọi service:

```java
import jakarta.validation.Validator;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/customers")
class CustomerRegistrationController {

    private final CustomerRegistrationService service;
    private final Validator validator;

    CustomerRegistrationController(
            CustomerRegistrationService service,
            Validator validator) {
        this.service = service;
        this.validator = validator;
    }

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<CustomerView> register(
            @RequestBody RegisterCustomerPayload payload) {

        RegisterCustomerCommand command = RegisterCustomerCommand.from(payload);

        if (!validator.validate(command).isEmpty()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "Dữ liệu đăng ký khách hàng không hợp lệ");
        }

        CustomerView created = service.register(command);
        return ResponseEntity.status(HttpStatus.CREATED).body(created);
    }
}
```

`CustomerRegistrationService` và `CustomerView` thuộc ứng dụng, giả định service có phương thức `register(RegisterCustomerCommand)`. Cần có Bean Validation provider và bean `Validator` phù hợp.

Cách kiểm tra ở đây là tường minh: dữ liệu được đọc từ projection, chuẩn hóa, tạo command rồi được kiểm tra. Nó không dựa vào giả định rằng mọi constraint trên mọi proxy đầu vào đều được phát hiện giống nhau trong mọi cấu hình.

Trong ứng dụng có chính sách lỗi chuẩn, có thể thay `ResponseStatusException` bằng exception và advice chung để trả mã lỗi/chi tiết trường theo hợp đồng. Không cần để service biết JSONPath hoặc loại message converter đã tạo projection.

## 6. Validation không tự được tạo bởi annotation projection

`@ProjectedPayload` không tự có nghĩa các trường đều bắt buộc, chuỗi không được rỗng hoặc email phải hợp lệ.

Các yêu cầu khác nhau cần được khai báo và thực thi riêng:

| Yêu cầu | Ví dụ cơ chế |
|---|---|
| Có request body | Hợp đồng `@RequestBody` và cấu hình MVC |
| JSON/XML đúng cú pháp | Parser/message converter |
| Getter đọc được giá trị phù hợp | Đường dẫn, kiểu trả về và conversion |
| Tên không rỗng, email đúng hình thức | Validation trên dữ liệu được đọc |
| Email chưa được đăng ký trong phạm vi cần thiết | Chính sách service và ràng buộc dữ liệu tương ứng |
| Người gọi được phép tạo khách hàng | Chính sách truy cập nghiệp vụ |

Có thể dùng validation khai báo trên interface/getter khi stack và provider hỗ trợ đúng cách. Tuy nhiên, chỉ thêm `@Valid` không tự tạo các constraint còn thiếu và không thay việc xác định cách xử lý thuộc tính không tồn tại.

Với một command trung gian, ứng dụng có nơi rõ ràng để kiểm tra dữ liệu không phụ thuộc hình dạng proxy. Nếu service còn được gọi từ batch, queue hoặc một endpoint khác, các yêu cầu nghiệp vụ chung cũng cần được duy trì tại ranh giới thích hợp; không coi validation trong một controller là bảo đảm cho mọi điểm gọi.

## 7. Nhiều JSONPath cho một accessor

Một giai đoạn chuyển đổi API có thể cần đọc cả dạng cũ:

```json
{
  "name": "Nguyễn Lan",
  "email": "lan@example.com"
}
```

và dạng mới có object `customer` lồng nhau. Một interface thay thế có thể khai báo các đường dẫn ứng viên:

```java
@ProjectedPayload
public interface CompatibleCustomerPayload {

    @JsonPath({"$.customer.name", "$.name"})
    String getName();

    @JsonPath({"$.customer.contact.email", "$.email"})
    String getEmail();
}
```

Đây là một lựa chọn hợp đồng thay thế cho interface ở phần 4. Annotation cho phép khai báo các cách định vị theo thứ tự mà hạ tầng hỗ trợ, thay vì coi chúng là yêu cầu gộp mọi giá trị lại.

Cần công bố chính sách khi request chứa cả hai dạng với giá trị khác nhau. Không mặc định cơ chế chọn đường dẫn tự kiểm tra xung đột hoặc tự từ chối payload mâu thuẫn.

Cũng không nên suy ra rằng đường đầu tiên có giá trị `null` luôn được xử lý giống đường không tồn tại rồi tự chuyển sang đường tiếp theo. Cần xác định hành vi của bộ thư viện và schema được chấp nhận.

Nếu hợp đồng yêu cầu nhận biết đồng thời cả hai giá trị, kiểm tra xung đột hoặc phân biệt trạng thái hiện diện, DTO/parser có kiểm soát cấu trúc có thể phù hợp hơn một getter hợp nhất.

Khả năng đọc nhiều cấu trúc không thay kế hoạch version API. Cần xác định thời gian hỗ trợ dạng cũ và bộ quy tắc chuẩn hóa chung để service không xử lý hai hợp đồng khác nhau một cách ngầm định.

## 8. Kiểu trả về phải khớp dữ liệu được chọn

Một đường dẫn chọn giá trị đơn và một đường dẫn quét nhiều giá trị có ngữ nghĩa khác nhau:

```text
$.customer.contact.email   → nhắm một vị trí cụ thể
$..email                   → tìm sâu các thuộc tính email
```

Nếu tài liệu có nhiều object chứa `email`, biểu thức quét sâu có thể chọn nhiều kết quả hoặc kết quả ngoài vùng ứng dụng dự định sử dụng. Không đặt kiểu `String` rồi mặc định parser luôn chọn đúng một phần tử như mong muốn.

Khi cần collection, phải chọn đường dẫn và kiểu collection tương thích với cơ chế projection đang dùng. Khi cần một trường đơn, nên định vị cụ thể và kiểm tra dữ liệu vi phạm kỳ vọng về cấu trúc.

Projection cũng có thể được kết hợp với góc nhìn lồng nhau hoặc ánh xạ kiểu phức tạp theo khả năng của projection factory/converter. Điều đó không đồng nghĩa mọi getter tùy ý, mọi generic hoặc mọi loại collection đều được xử lý giống nhau ở mọi phiên bản.

Nếu payload phức tạp, có nhiều nhánh lựa chọn hoặc cần ràng buộc liên trường, DTO rõ ràng thường giúp biểu diễn schema và validation dễ theo dõi hơn.

## 9. Đọc XML qua cùng ý tưởng projection

Khi XmlBeam và converter XML tương ứng được hỗ trợ, interface có thể khai báo đường XPath bên cạnh JSONPath:

```java
import org.springframework.data.web.JsonPath;
import org.springframework.data.web.ProjectedPayload;
import org.xmlbeam.annotation.XBRead;

@ProjectedPayload
public interface CustomerContactPayload {

    @JsonPath("$.customer.name")
    @XBRead("/customer/name")
    String getName();

    @JsonPath("$.customer.contact.email")
    @XBRead("/customer/contact/email")
    String getEmail();
}
```

Payload XML tương ứng:

```xml
<customer>
    <name>Nguyễn Lan</name>
    <contact>
        <email>lan@example.com</email>
    </contact>
</customer>
```

JSONPath và XPath là hai cơ chế định vị khác nhau. Không sao chép một biểu thức từ ngôn ngữ này sang ngôn ngữ kia rồi kỳ vọng cùng ý nghĩa.

Nếu XML dùng namespace, XPath và cấu hình namespace phải phù hợp. Các đường quét rộng như `//name` cũng cần được cân nhắc khi tài liệu có nhiều phần tử cùng tên ở các nhánh khác nhau.

Một endpoint muốn nhận cả JSON và XML có thể công bố hai media type trong `consumes`, nhưng chỉ khi cả hai đường chuyển đổi đã được cấu hình. Sau khi đọc dữ liệu, vẫn cần dùng cùng quy tắc tạo command và validation nghiệp vụ.

`Content-Type` mô tả định dạng request body và ảnh hưởng converter được chọn. `Accept` diễn đạt định dạng response client muốn nhận; nó không thay thế `Content-Type` của body gửi lên.

Không cần bật XML nếu API chỉ có hợp đồng JSON. Projection không bắt buộc một endpoint phải hỗ trợ mọi định dạng mà hạ tầng có thể cung cấp.

## 10. Trường thiếu, null và chuỗi rỗng

Ba payload sau không có cùng biểu diễn:

```json
{"customer": {}}
```

```json
{"customer": {"name": null}}
```

```json
{"customer": {"name": ""}}
```

Tuy nhiên, một getter `String getName()` không tự công bố đầy đủ thông tin về việc đường dẫn có hiện diện hay không. Hành vi có thể liên quan đến kết quả `null`, giá trị đọc được hoặc lỗi đọc/chuyển kiểu theo cấu hình.

Với thao tác tạo mới, ứng dụng có thể chọn coi cả ba là không đáp ứng ràng buộc tên bắt buộc. Command và validation ở phần 5 thể hiện chính sách đó cho các giá trị đọc được.

Với PATCH hoặc cập nhật từng phần, ý nghĩa thường khác:

| Trạng thái | Một hợp đồng cập nhật có thể chọn |
|---|---|
| Không có trường | Giữ nguyên dữ liệu hiện tại |
| Có trường với `null` | Xóa giá trị, nếu nghiệp vụ cho phép |
| Có chuỗi rỗng | Đặt chuỗi rỗng hoặc từ chối theo quy tắc |

Không dùng một getter nullable rồi mặc định đã giữ được mọi trạng thái hiện diện cần cho PATCH. Cần một thiết kế có theo dõi hiện diện, patch document hoặc DTO phù hợp với hợp đồng cập nhật.

Tương tự, dùng kiểu nguyên thủy như `boolean` cho một giá trị tùy chọn có thể làm việc phân biệt thiếu dữ liệu trở nên khó diễn đạt hoặc gây lỗi chuyển đổi. Chọn kiểu trả về và quy tắc validation theo yêu cầu thực tế; không xem giá trị mặc định Java là bằng chứng client đã gửi trường.

## 11. Trường ngoài projection không phải chính sách từ chối trường lạ

Một request có thể gửi thêm:

```json
{
  "customer": {
    "name": "Nguyễn Lan",
    "contact": {"email": "lan@example.com"},
    "tenantId": "tenant-khac",
    "role": "ADMIN"
  }
}
```

Nếu interface chỉ đọc tên và email, controller tạo command từ đúng hai giá trị đó thì các trường bổ sung không tự trở thành thuộc tính của command.

Tuy nhiên, chỉ không khai báo getter không đồng nghĩa framework chắc chắn từ chối request vì có trường lạ. Projection thường phục vụ một góc nhìn của dữ liệu, không phải toàn bộ chính sách kiểm tra schema nghiêm ngặt.

Nếu hợp đồng yêu cầu từ chối thuộc tính không được phép, cần cơ chế kiểm tra cấu trúc thích hợp và xác định phạm vi kiểm tra. Không mặc định cấu hình Jackson từ chối thuộc tính lạ cho DTO thông thường luôn áp dụng giống hệt cho mọi converter projected payload.

Tenant, vai trò, trạng thái tạo mới và metadata auditing nên lấy từ chính sách của ứng dụng khi nghiệp vụ quy định như vậy. Một ví dụ service có thể dùng:

```java
UUID tenantId = tenantContext.requireTenantId();

Customer customer = Customer.register(
        tenantId,
        command.name(),
        command.email());

Customer saved = repository.save(customer);
return CustomerView.from(saved);
```

Đoạn này giả định domain có factory `register`, repository CRUD phù hợp và transaction được thiết kế ở service. Factory có thể đặt trạng thái ban đầu theo nghiệp vụ; không lấy vai trò hay tenant tùy ý từ payload chỉ vì chúng xuất hiện trong JSON.

Auditing của Spring Data cần được cấu hình với module, annotation và nguồn auditor tương ứng. `@ProjectedPayload` không tự tạo auditor và không xác thực danh tính.

## 12. Đọc projection không phải xử lý streaming hoặc tối ưu truy vấn

Chỉ khai báo hai getter không chứng minh HTTP server chỉ đọc hai trường từ mạng hoặc không phải parse phần còn lại của tài liệu. Cách lưu và phân tích payload phụ thuộc converter cùng thư viện.

Projection cũng không tự giới hạn kích thước request body, độ sâu tài liệu hoặc số phần tử trong một mảng. Nếu endpoint có các giới hạn này, cần cấu hình và kiểm tra ở lớp thích hợp với hợp đồng API.

Giá trị của projection nằm ở cách khai báo góc nhìn đầu vào và cách tách cấu trúc tài liệu khỏi tên thuộc tính Java. Nó không thay thế các chiến lược đọc tài liệu lớn khi nghiệp vụ yêu cầu streaming thực sự.

Một số công việc đọc/chuyển giá trị có thể diễn ra khi accessor được gọi. Vì vậy, đừng giả định mọi lỗi liên quan đến field đều chắc chắn xảy ra ngay lúc object projection được tạo.

Đọc các giá trị cần thiết một lần rồi tạo command giúp xác định rõ thời điểm lỗi đầu vào được xử lý. Không nên truyền proxy HTTP đi xa vào tác vụ nền, transaction dài hoặc một lớp nghiệp vụ không cần biết cơ chế projection.

## 13. Phân loại lỗi tại ranh giới payload

| Tình huống | Bản chất | Hướng xử lý |
|---|---|---|
| Body bắt buộc nhưng không có | Thiếu đầu vào HTTP | Theo hợp đồng `@RequestBody`, thường là lỗi 400 |
| JSON/XML sai cú pháp | Không đọc được tài liệu | Lỗi parse/message conversion theo chính sách HTTP |
| Content-Type không được endpoint hỗ trợ | Không có đường nhận định dạng phù hợp | Phản hồi media type theo cấu hình MVC |
| Đường dẫn thiếu hoặc chọn sai kiểu | Không đọc được dữ liệu như hợp đồng | Xử lý lỗi đọc/chuyển kiểu và validation phù hợp |
| Tên/email không đáp ứng ràng buộc | Dữ liệu đầu vào không hợp lệ | Phản hồi validation có chủ đích |
| Email đã tồn tại trong phạm vi quy định | Xung đột nghiệp vụ/dữ liệu | Theo chính sách của service và ràng buộc persistence |
| Database không truy cập được | Lỗi hạ tầng | Không giả làm payload sai |

Không bắt mọi exception rồi trả “JSON không hợp lệ”. Một tài liệu có thể hoàn toàn đúng cú pháp nhưng không đáp ứng ràng buộc nghiệp vụ; ngược lại, lỗi repository không phải lỗi cấu trúc request.

Nếu getter phát sinh exception khi đọc, cần tích hợp kiểu exception thực tế của stack vào chính sách lỗi. Không đặt một handler toàn cục quá rộng rồi quy mọi lỗi lập trình hoặc lỗi driver thành HTTP 400.

Response lỗi nên dùng mã và thông báo công khai do ứng dụng kiểm soát. Đường dẫn nội bộ, chi tiết parser hoặc thông tin persistence không cần trở thành hợp đồng với client.

## 14. Khi nào chọn projection, khi nào chọn DTO?

| Nhu cầu | Lựa chọn có thể phù hợp |
|---|---|
| Đọc một góc nhìn nhỏ từ cấu trúc JSON/XML khác nhau | Projected payload với đường dẫn rõ ràng |
| Hỗ trợ tạm thời hai vị trí dữ liệu cho cùng một trường | Nhiều đường dẫn ứng viên, kèm chính sách xung đột |
| Schema request cố định, validation nhiều trường | DTO/class/record đầu vào rõ ràng |
| Cần phân biệt thiếu trường và null khi PATCH | Kiểu dữ liệu có theo dõi hiện diện hoặc patch model phù hợp |
| Cần từ chối toàn bộ thuộc tính lạ | Cơ chế kiểm tra schema/deserialization có chính sách tường minh |
| Xử lý tài liệu lớn theo luồng | API/parser streaming phù hợp, không suy ra từ projection |

Không cần thay mọi DTO bằng interface. Projection hữu ích khi cách định vị dữ liệu là một phần quan trọng của bài toán; DTO hữu ích khi cấu trúc và ràng buộc của command cần được biểu diễn trực tiếp.

Hai cách có thể kết hợp: projection ở ranh giới HTTP, command đã kiểm tra ở service, và DTO khác cho response. Sự kết hợp nên phục vụ một yêu cầu cụ thể, không thêm lớp chỉ để đổi tên object.

## 15. Tình huống kiểm chứng khi tích hợp

| Trường hợp | Điều cần quan sát |
|---|---|
| Payload JSON đúng cấu trúc | Getter đọc đúng tên và email |
| Body thiếu | Phản hồi theo hợp đồng request bắt buộc |
| Tên thiếu/null/rỗng | Chính sách validation nhất quán |
| Email sai hình thức | Không gọi persistence như một đăng ký hợp lệ |
| Giá trị có khoảng trắng đầu/cuối | Chuẩn hóa theo chính sách đã chọn |
| JSON sai kiểu tại đường email | Phân biệt lỗi đọc với chuỗi email không hợp lệ |
| Payload có thêm role/tenantId | Không tự thay quyền hoặc tenant của command |
| Hai đường dẫn cùng có giá trị khác nhau | Theo chính sách xung đột đã công bố |
| JSONPath quét nhiều kết quả | Không âm thầm chọn nhầm một giá trị |
| XML được hỗ trợ | XPath, namespace và Content-Type hoạt động đúng hợp đồng |
| XML không thuộc hợp đồng | Không tự nhận chỉ vì một dependency có mặt |
| Repository thất bại | Không trả lỗi giả rằng payload sai cú pháp |

Khi chẩn đoán, cần lần theo converter được chọn, interface projection, đường dẫn, dữ liệu đã đọc, command đã chuẩn hóa và kết quả validation. Chỉ sau đó mới kiểm tra service và persistence nếu yêu cầu đã đi tới lớp đó.

## 16. Bài tập tự kiểm tra

### Tình huống 1: Có @ProjectedPayload nhưng Jackson báo không tạo được interface

Ứng dụng chỉ có đường deserialize thông thường hoặc converter projected payload chưa được chọn.

**Phân tích:** marker annotation cần đi cùng hạ tầng chuyển đổi và dependency thích hợp. Không thể suy ra một interface bất kỳ tự trở thành request DTO chỉ vì nó có getter.

### Tình huống 2: Getter chỉ đọc email nên cho rằng email đã hợp lệ

Payload chứa chuỗi không đáp ứng quy tắc email của API.

**Phân tích:** extraction và validation là hai bước khác nhau. Cần chuẩn hóa/kiểm tra dữ liệu, chẳng hạn tạo command rồi áp dụng Bean Validation phù hợp.

### Tình huống 3: Payload có thêm role=ADMIN

Interface không có getter role và controller chỉ tạo command từ tên/email.

**Phân tích:** trường đó không tự đi vào command đã định nghĩa, nhưng request cũng chưa chắc bị từ chối vì trường lạ. Quyền và trạng thái vẫn phải do service xác định theo hợp đồng.

### Tình huống 4: Hai JSONPath cùng tồn tại với dữ liệu khác nhau

Nhóm phát triển cho rằng framework tự phát hiện request mâu thuẫn.

**Phân tích:** nhiều đường dẫn cung cấp cách định vị thay thế, không tự tạo chính sách kiểm tra xung đột. Cần quyết định ưu tiên hoặc từ chối theo thiết kế.

### Tình huống 5: Dùng cùng getter nullable cho PATCH

Ứng dụng muốn phân biệt không gửi email với gửi email bằng null.

**Phân tích:** một giá trị getter đơn lẻ có thể không giữ đủ thông tin hiện diện. Cần model cập nhật có ngữ nghĩa rõ ràng thay vì suy ra từ null.

### Tình huống 6: Chỉ có hai getter nên cho rằng request rất lớn được đọc theo luồng

Payload chứa một mảng lớn không dùng đến trong command.

**Phân tích:** projection giới hạn góc nhìn API Java, không tự bảo đảm parser bỏ qua phần còn lại theo streaming. Giới hạn body và chiến lược xử lý tài liệu lớn cần được thiết kế riêng.

`@ProjectedPayload` giúp khai báo cách đọc dữ liệu đầu vào mà không buộc cấu trúc Java trùng toàn bộ tài liệu. Để dùng đúng, hãy định vị trường rõ ràng, chuyển các giá trị cần thiết sang command đã kiểm tra và giữ quyền truy cập, tenant, auditing cùng thao tác repository trong ranh giới nghiệp vụ phù hợp.

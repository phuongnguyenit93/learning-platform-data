# Tính bắt buộc, giá trị rỗng và thuộc tính vắng mặt

Khi mô tả hợp đồng HTTP bằng springdoc-openapi, cần phân biệt ba trạng thái thường bị nhầm lẫn: một thuộc tính không xuất hiện trong request, một thuộc tính xuất hiện với giá trị <code>null</code>, và một thuộc tính xuất hiện với giá trị rỗng như chuỗi <code>""</code>. Ba trạng thái này có ý nghĩa khác nhau trong JSON và có thể dẫn đến hành vi nghiệp vụ khác nhau.

OpenAPI mô tả các trạng thái đó bằng những khái niệm riêng: <code>required</code> xác định một giá trị có bắt buộc phải xuất hiện hay không; kiểu dữ liệu và khả năng nhận <code>null</code> xác định giá trị nào hợp lệ khi nó xuất hiện; các ràng buộc như <code>minLength</code> xác định giá trị rỗng có được chấp nhận hay không. springdoc-openapi tạo tài liệu từ ứng dụng Spring Boot, nhưng hợp đồng chỉ chính xác khi schema thể hiện đúng các quy tắc mà API thực sự áp dụng.

## 1. Phân biệt thuộc tính vắng mặt, null và rỗng

Xét một request JSON có ba thuộc tính <code>name</code>, <code>nickname</code> và <code>description</code>:

~~~json
{
  "name": "Lan",
  "nickname": null,
  "description": ""
}
~~~

Trong object JSON này:

- <code>name</code> có mặt và chứa chuỗi có nội dung.
- <code>nickname</code> có mặt và giá trị của nó là <code>null</code>.
- <code>description</code> có mặt và chứa chuỗi rỗng, tức chuỗi có độ dài bằng 0.
- Nếu bỏ hẳn một thuộc tính khỏi object, thuộc tính đó ở trạng thái vắng mặt.

Các trường hợp này không thể thay thế cho nhau:

| Biểu diễn | Ý nghĩa trong JSON | Câu hỏi hợp đồng cần trả lời |
|---|---|---|
| Không có khóa <code>nickname</code> | Thuộc tính vắng mặt | Có được phép bỏ thuộc tính không? |
| <code>"nickname": null</code> | Có khóa, giá trị null | Có cho phép giá trị null không? |
| <code>"nickname": ""</code> | Có khóa, chuỗi rỗng | Có cho phép chuỗi độ dài 0 không? |
| <code>"nickname": "   "</code> | Có khóa, chuỗi chỉ có khoảng trắng | Có yêu cầu nội dung không phải khoảng trắng không? |
| <code>"nickname": "Lan"</code> | Có khóa, chuỗi có nội dung | Giá trị có thỏa các ràng buộc khác không? |

Đối với mảng và object, giá trị rỗng cũng có hình thức riêng:

~~~json
{
  "tags": [],
  "settings": {}
}
~~~

<code>[]</code> là mảng có 0 phần tử; <code>{}</code> là object không có thuộc tính. Chúng khác với <code>null</code> và khác với việc không gửi khóa <code>tags</code> hoặc <code>settings</code>.

## 2. <code>required</code> quy định sự hiện diện

Trong Schema Object của OpenAPI, <code>required</code> là một danh sách tên thuộc tính bắt buộc của object. Danh sách này được khai báo cùng cấp với <code>properties</code>.

~~~yaml
type: object
required:
  - name
properties:
  name:
    type: string
  nickname:
    type: string
~~~

Schema trên yêu cầu object phải có thuộc tính <code>name</code>. Thuộc tính <code>nickname</code> có thể vắng mặt. Cả hai thuộc tính đều có kiểu string, nên khi xuất hiện, giá trị phải là chuỗi theo schema này. <code>nickname</code> không được liệt kê trong <code>required</code> không có nghĩa là nó tự động nhận <code>null</code>.

Ví dụ:

~~~json
{ "name": "Lan" }
~~~

Đây là object hợp lệ theo schema trên. Object sau không hợp lệ vì thiếu <code>name</code>:

~~~json
{ "nickname": "L" }
~~~

<code>required</code> không đồng nghĩa với <code>minLength</code>, <code>minItems</code> hay một quy tắc kiểm tra nội dung. Một chuỗi bắt buộc vẫn có thể là chuỗi rỗng nếu schema không đặt giới hạn độ dài.

~~~yaml
type: object
required:
  - name
properties:
  name:
    type: string
~~~

Với schema này, <code>{ "name": "" }</code> vẫn thỏa kiểu string và sự hiện diện. Nếu nghiệp vụ yêu cầu ít nhất một ký tự, cần bổ sung <code>minLength: 1</code>. Nếu yêu cầu loại bỏ cả chuỗi chỉ chứa khoảng trắng, cần một quy tắc mạnh hơn, chẳng hạn <code>@NotBlank</code> ở tầng Bean Validation.

## 3. Bắt buộc và cho phép null là hai quyết định độc lập

Một thuộc tính có thể bắt buộc xuất hiện nhưng vẫn cho phép giá trị <code>null</code>. Ngược lại, một thuộc tính có thể được phép vắng mặt nhưng nếu xuất hiện thì phải có giá trị khác null.

Bảng sau mô tả bốn tổ hợp:

| Có trong <code>required</code>? | Schema có nhận null? | Ý nghĩa |
|---|---|---|
| Có | Không | Phải xuất hiện và không được null |
| Có | Có | Phải xuất hiện; giá trị có thể null |
| Không | Không | Có thể vắng mặt; nếu xuất hiện thì không được null |
| Không | Có | Có thể vắng mặt; nếu xuất hiện thì có thể null |

### 3.1. OpenAPI 3.0: dùng <code>nullable</code>

Trong OpenAPI 3.0, có thể dùng <code>nullable: true</code> để cho phép giá trị null cho một schema có khai báo <code>type</code>:

~~~yaml
type: object
required:
  - displayName
  - nickname
properties:
  displayName:
    type: string
    minLength: 1
  nickname:
    type: string
    nullable: true
  bio:
    type: string
~~~

Diễn giải:

- <code>displayName</code> bắt buộc, không null và phải có ít nhất một ký tự.
- <code>nickname</code> bắt buộc phải có khóa, nhưng giá trị có thể là chuỗi hoặc <code>null</code>.
- <code>bio</code> có thể vắng mặt; nếu có mặt thì phải là chuỗi khác null. Chuỗi rỗng vẫn hợp lệ vì chưa đặt <code>minLength</code>.

Ví dụ sau hợp lệ:

~~~json
{
  "displayName": "Lan",
  "nickname": null,
  "bio": ""
}
~~~

Ví dụ sau không hợp lệ vì thiếu thuộc tính bắt buộc <code>nickname</code>:

~~~json
{
  "displayName": "Lan"
}
~~~

Ví dụ sau không hợp lệ vì <code>displayName</code> có độ dài bằng 0:

~~~json
{
  "displayName": "",
  "nickname": null
}
~~~

Trong OpenAPI 3.0, <code>nullable</code> chỉ có tác dụng khi <code>type</code> được khai báo rõ trong cùng Schema Object. Không dùng <code>nullable: true</code> để thay thế <code>required</code>: hai thuộc tính này giải quyết hai vấn đề khác nhau.

### 3.2. OpenAPI 3.1: dùng kiểu hợp với null

OpenAPI 3.1 dựa trên JSON Schema hiện đại. Để một giá trị có thể là chuỗi hoặc null, biểu diễn kiểu bằng danh sách:

~~~yaml
openapi: 3.1.0
components:
  schemas:
    Profile:
      type: object
      required:
        - displayName
        - nickname
      properties:
        displayName:
          type: string
          minLength: 1
        nickname:
          type: [string, "null"]
        bio:
          type: string
~~~

<code>nickname</code> vẫn bắt buộc xuất hiện do nằm trong mảng <code>required</code>, còn <code>type: [string, "null"]</code> cho phép giá trị của nó là chuỗi hoặc null. <code>bio</code> vẫn là thuộc tính tùy chọn và không nhận null theo schema này.

Khi viết tài liệu OpenAPI 3.1, ưu tiên biểu diễn kiểu null theo JSON Schema như ví dụ trên. <code>nullable</code> là cách biểu diễn của OpenAPI 3.0 và không phải từ khóa JSON Schema thay thế cho kiểu hợp trong OpenAPI 3.1.

## 4. Phân biệt required ở các cấp của hợp đồng HTTP

OpenAPI có nhiều vị trí dùng từ <code>required</code>. Cần xác định đúng cấp vì mỗi vị trí điều khiển một điều khác nhau.

| Vị trí | Cách khai báo | Ý nghĩa |
|---|---|---|
| Parameter Object | <code>required: true</code> | Tham số path, query, header hoặc cookie phải được gửi |
| Request Body Object | <code>required: true</code> | Client phải gửi request body |
| Schema Object của object | <code>required: [fieldA, fieldB]</code> | Các thuộc tính được liệt kê phải xuất hiện trong object |

Với tham số đường dẫn, OpenAPI yêu cầu <code>required: true</code>. Tham số query thường không bắt buộc trừ khi khai báo rõ:

~~~yaml
parameters:
  - name: customerId
    in: path
    required: true
    schema:
      type: string
  - name: keyword
    in: query
    required: false
    schema:
      type: string
~~~

<code>required: false</code> của <code>keyword</code> cho phép client bỏ tham số. Nếu client gửi <code>?keyword=</code>, giá trị nhận được là một giá trị chuỗi rỗng theo cách phân tích query thông thường; đó không phải là tham số vắng mặt. Cách xử lý query không có dấu <code>=</code> có thể phụ thuộc framework và cần được quy định rõ nếu API sử dụng trường hợp này.

Request body có quy tắc riêng:

~~~yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        type: object
        required:
          - name
        properties:
          name:
            type: string
~~~

Ở đây, <code>requestBody.required: true</code> yêu cầu có body. Mảng <code>schema.required</code> yêu cầu thuộc tính <code>name</code> bên trong JSON body. Nếu body là object rỗng <code>{}</code>, request có body nhưng vẫn không thỏa schema vì thiếu <code>name</code>. Nếu client không gửi body, request vi phạm yêu cầu ở cấp Request Body.

Body không có byte dữ liệu, body chứa JSON <code>null</code>, và body chứa object rỗng <code>{}</code> cũng là ba trường hợp khác nhau. Muốn chấp nhận JSON <code>null</code>, schema của body phải cho phép kiểu null; <code>requestBody.required: true</code> tự nó không làm schema nhận null.

## 5. Ràng buộc chuỗi rỗng và nội dung chỉ có khoảng trắng

Một thuộc tính có mặt và có kiểu string chưa chắc chứa nội dung có ích. Dùng các ràng buộc schema để mô tả giới hạn:

~~~yaml
type: string
minLength: 1
maxLength: 80
~~~

<code>minLength: 1</code> loại chuỗi rỗng <code>""</code>, nhưng vẫn cho phép chuỗi chỉ có khoảng trắng như <code>"   "</code>. Nếu cần ít nhất một ký tự không phải khoảng trắng, hãy thể hiện quy tắc tương ứng bằng validation ở ứng dụng và mô tả rõ trong tài liệu.

Một số annotation Bean Validation thường dùng:

| Annotation | Quy tắc ở runtime |
|---|---|
| <code>@NotNull</code> | Giá trị không được null; chuỗi rỗng vẫn có thể hợp lệ |
| <code>@NotEmpty</code> | Giá trị không null và có kích thước lớn hơn 0; chuỗi chỉ có khoảng trắng vẫn có thể hợp lệ |
| <code>@NotBlank</code> | Chuỗi không null và phải chứa ít nhất một ký tự không phải khoảng trắng |
| <code>@Size(min = 1)</code> | Kích thước phải tối thiểu 1; constraint này chấp nhận null nếu không có constraint khác cấm null |

Ví dụ DTO:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateCustomerRequest(
    @NotBlank
    @Size(max = 80)
    String name,

    @Size(max = 40)
    String nickname
) {}
~~~

Controller cần kích hoạt validation cho request:

~~~java
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CustomerController {

    @PostMapping("/customers")
    ResponseEntity<Void> create(
            @Valid @RequestBody CreateCustomerRequest request) {
        // Xử lý request sau khi validation thành công
        return ResponseEntity.accepted().build();
    }
}
~~~

<code>@NotBlank</code> khiến <code>name</code> không được null, không được rỗng và không được chỉ chứa khoảng trắng khi Bean Validation thực thi. <code>@Size(max = 40)</code> giới hạn kích thước nickname nhưng tự nó không bắt buộc nickname phải có mặt và cũng chấp nhận null. Đây là quy tắc runtime của ứng dụng; cần kiểm tra schema do springdoc tạo ra để bảo đảm tài liệu phản ánh đúng các constraint.

## 6. Diễn đạt yêu cầu rõ ràng trong springdoc-openapi

springdoc-openapi đọc cấu trúc Spring MVC/WebFlux và các annotation liên quan để tạo đặc tả. Bean Validation giúp mô tả những giới hạn mà ứng dụng kiểm tra ở runtime. Annotation <code>@Schema</code> cho phép bổ sung metadata OpenAPI khi cần chỉ rõ ý định của hợp đồng.

Ví dụ, dùng <code>requiredMode</code> để khai báo tường minh sự hiện diện của một thuộc tính:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;

public record RegisterRequest(
    @Schema(
        description = "Tên hiển thị của người dùng",
        requiredMode = Schema.RequiredMode.REQUIRED
    )
    @NotBlank
    String displayName,

    @Schema(
        description = "Tên gọi khác; có thể bỏ qua khi đăng ký",
        requiredMode = Schema.RequiredMode.NOT_REQUIRED
    )
    String nickname
) {}
~~~

<code>requiredMode</code> điều khiển cách thuộc tính được mô tả trong OpenAPI. Nó không tự thực thi validation khi request đến server. Ngược lại, annotation Bean Validation chỉ có hiệu lực runtime khi ứng dụng kích hoạt validation và gọi kiểm tra phù hợp. Hai lớp này cần thống nhất để tài liệu không hứa một hành vi mà endpoint không thực hiện.

Đối với thuộc tính có thể nhận null, hãy chọn cách biểu diễn phù hợp với phiên bản OpenAPI mà ứng dụng xuất ra. Kiểm tra trường <code>openapi</code> ở đầu tài liệu <code>/v3/api-docs</code>, sau đó xác minh schema:

- OpenAPI 3.0: kiểm tra <code>nullable: true</code> cùng <code>type</code>.
- OpenAPI 3.1: kiểm tra kiểu JSON Schema có bao gồm <code>"null"</code> khi cần.
- Ở cả hai phiên bản: kiểm tra thuộc tính có nằm trong mảng <code>required</code> của object hay không.

Không suy luận rằng một thuộc tính nhận null chỉ vì Java DTO khai báo kiểu tham chiếu như <code>String</code>, <code>Integer</code> hoặc <code>LocalDate</code>. Kiểu Java, quy tắc Jackson, Bean Validation, metadata OpenAPI và logic nghiệp vụ là các lớp khác nhau. Đặc tả sinh ra cần được đọc lại để xác nhận kết quả cuối cùng.

## 7. Thuộc tính vắng mặt và null trong thao tác cập nhật

Sự khác biệt giữa vắng mặt và null đặc biệt quan trọng với API cập nhật một phần. Ví dụ client muốn đổi tên gọi khác của hồ sơ:

~~~json
{
  "nickname": "Lana"
}
~~~

Nếu client bỏ <code>nickname</code>, API có thể hiểu là không thay đổi thuộc tính này. Nếu client gửi <code>"nickname": null</code>, API có thể hiểu là xóa giá trị hiện tại. Nếu client gửi <code>"nickname": ""</code>, API có thể lưu chuỗi rỗng hoặc từ chối theo quy tắc nghiệp vụ.

Đây là quy ước của API cập nhật; không phải mọi endpoint PATCH đều tự động có hành vi như vậy. Hợp đồng phải mô tả rõ từng trạng thái. Nếu dùng JSON Merge Patch theo RFC 7396, thuộc tính bị bỏ qua giữ nguyên, còn thuộc tính có giá trị null biểu thị việc loại bỏ thành viên tương ứng khỏi target object. Nếu dùng một định dạng PATCH riêng, hãy công bố quy tắc của định dạng đó.

Trong Java, một DTO thông thường có thể không giữ được khác biệt giữa thuộc tính bị bỏ qua và thuộc tính được gửi với null: cả hai trường hợp có thể trở thành giá trị <code>null</code> sau khi Jackson bind vào field. Khi nghiệp vụ cần phân biệt, có thể đọc payload dạng <code>JsonNode</code> và kiểm tra sự hiện diện trước khi kiểm tra giá trị:

~~~java
if (!patch.has("nickname")) {
    // Không cập nhật nickname
} else if (patch.get("nickname").isNull()) {
    // Xóa nickname theo quy ước của API
} else {
    // Cập nhật bằng giá trị được gửi
    String nickname = patch.get("nickname").asText();
}
~~~

Đoạn mã trên giả định <code>patch</code> là một object JSON và endpoint đã xác thực kiểu dữ liệu phù hợp. Nếu dùng DTO, wrapper hoặc custom deserializer, hãy kiểm tra cách thư viện bind dữ liệu để chắc chắn ba trạng thái vẫn được phân biệt.

## 8. Kiểm tra hợp đồng được sinh ra

Sau khi thêm hoặc thay đổi annotation, hãy kiểm tra tài liệu thực tế tại <code>/v3/api-docs</code>. Có thể tải JSON bằng curl:

~~~bash
curl -s http://localhost:8080/v3/api-docs
~~~

Tập trung vào các điểm sau:

1. Đúng phiên bản OpenAPI 3.0 hay 3.1 được công bố ở trường <code>openapi</code>.
2. Request body có đúng mức bắt buộc theo yêu cầu endpoint không.
3. Schema object có mảng <code>required</code> gồm đúng những thuộc tính phải xuất hiện không.
4. Thuộc tính cho phép null có biểu diễn phù hợp với phiên bản OpenAPI không.
5. Chuỗi có giới hạn độ dài, mẫu hoặc định dạng đúng như validation runtime không.
6. Các ví dụ request có thể hiện được thuộc tính vắng mặt, null và chuỗi rỗng khi những trường hợp đó có ý nghĩa.

Nên kiểm tra cả hai phía của hợp đồng. Với request, xác minh server từ chối dữ liệu vi phạm quy tắc. Với response, xác minh dữ liệu thực tế mà controller trả về không vi phạm schema đã công bố. Việc đặc tả có <code>required</code> hoặc <code>minLength</code> không tự động bảo đảm mọi đường code đều tạo ra response hợp lệ.

## 9. Danh sách rà soát trước khi công bố API

- [ ] Mỗi thuộc tính đã được xác định rõ là bắt buộc hay tùy chọn.
- [ ] Với thuộc tính tùy chọn, đã quyết định có cho phép null khi xuất hiện hay không.
- [ ] Với kiểu chuỗi, đã quyết định có chấp nhận <code>""</code> hoặc chuỗi chỉ có khoảng trắng hay không.
- [ ] Với mảng và object, đã quyết định có chấp nhận <code>[]</code> và <code>{}</code> hay không.
- [ ] Đã phân biệt <code>requestBody.required</code>, <code>Parameter.required</code> và mảng <code>Schema.required</code>.
- [ ] Hợp đồng PATCH đã quy định rõ cách xử lý thuộc tính vắng mặt, null và rỗng.
- [ ] Validation runtime và schema OpenAPI được sinh ra nhất quán.
- [ ] Ví dụ request/response thể hiện những trạng thái quan trọng của dữ liệu.

## Tài liệu tham khảo

- [OpenAPI Specification 3.0 – Schema Object](https://spec.openapis.org/oas/v3.0.3.html#schema-object): <code>required</code>, <code>nullable</code> và các ràng buộc schema.
- [OpenAPI Specification 3.1 – Schema Object](https://spec.openapis.org/oas/v3.1.1.html#schema-object): Schema Object dựa trên JSON Schema và cách mô tả kiểu dữ liệu.
- [JSON Schema – Required Properties](https://json-schema.org/understanding-json-schema/reference/object#required-properties): sự khác nhau giữa thuộc tính bắt buộc và thuộc tính tùy chọn.
- [JSON Schema – Null](https://json-schema.org/understanding-json-schema/reference/null): mô tả giá trị null trong schema.
- [JSON Merge Patch – RFC 7396](https://www.rfc-editor.org/rfc/rfc7396): ý nghĩa của thuộc tính vắng mặt và null trong JSON Merge Patch.
- [springdoc-openapi](https://springdoc.org/): tích hợp OpenAPI với Spring Boot và các tùy chỉnh tài liệu.

# nullable trong 3.0 và biểu diễn kiểu null trong 3.1

Khi mô tả một thuộc tính JSON có thể nhận giá trị null, OpenAPI 3.0 và OpenAPI 3.1 dùng hai cách biểu diễn khác nhau. OpenAPI 3.0 bổ sung từ khóa **nullable: true** vào Schema Object. OpenAPI 3.1 dựa trên JSON Schema 2020-12 nên biểu diễn null như một kiểu dữ liệu trong union type, ví dụ **type: [string, "null"]**, hoặc như một nhánh **anyOf**.

Sự khác biệt này ảnh hưởng trực tiếp đến schema springdoc sinh ra, Swagger UI, validator, code generator và các client đọc OpenAPI. Khi nâng tài liệu từ 3.0 lên 3.1, cần chuyển đổi schema nullable thay vì chỉ thay số phiên bản ở đầu file.

## 1. Phân biệt null, thuộc tính vắng mặt và giá trị rỗng

Trong JSON, ba trạng thái sau không giống nhau:

~~~json
{
  "nickname": null
}
~~~

~~~json
{}
~~~

~~~json
{
  "nickname": ""
}
~~~

- **null:** thuộc tính có mặt và giá trị của nó là null.
- **Vắng mặt:** đối tượng không chứa thuộc tính đó.
- **Chuỗi rỗng:** thuộc tính có mặt, giá trị là chuỗi có độ dài bằng 0.

API có thể gán ý nghĩa nghiệp vụ khác nhau cho từng trạng thái. Ví dụ trong request cập nhật hồ sơ:

| Dữ liệu gửi lên | Ý nghĩa có thể có |
| --- | --- |
| Không có nickname | Giữ nguyên biệt danh hiện tại |
| nickname: null | Xóa biệt danh |
| nickname: "" | Đặt biệt danh thành chuỗi rỗng, hoặc từ chối theo validation |
| nickname: "An" | Đổi biệt danh thành An |

Schema phải phản ánh đúng hợp đồng API. Nếu server phân biệt thuộc tính bị bỏ qua với thuộc tính được gửi rõ ràng là null, tài liệu cũng phải giữ được sự khác biệt đó.

## 2. nullable và required giải quyết hai câu hỏi khác nhau

Một Schema Object có thể trả lời hai câu hỏi độc lập:

1. Giá trị của thuộc tính có được phép là null không?
2. Thuộc tính có bắt buộc phải xuất hiện trong object không?

**nullable** trong OpenAPI 3.0 hoặc union với kiểu null trong OpenAPI 3.1 trả lời câu hỏi thứ nhất. Mảng **required** của object trả lời câu hỏi thứ hai.

| Required | Cho phép null | Ý nghĩa |
| --- | --- | --- |
| Không | Không | Có thể bỏ thuộc tính; nếu xuất hiện phải có giá trị đúng kiểu |
| Không | Có | Có thể bỏ thuộc tính hoặc gửi null |
| Có | Không | Phải có thuộc tính và giá trị không được null |
| Có | Có | Phải có thuộc tính, nhưng giá trị có thể là null |

Ví dụ, nickname bắt buộc phải có mặt nhưng được phép null:

~~~json
{
  "nickname": null
}
~~~

Nếu schema không đưa nickname vào required, client có thể bỏ thuộc tính đó. Đừng dùng **nullable: true** để thay thế cho việc bỏ thuộc tính khỏi danh sách required; hai khái niệm này không tương đương.

## 3. Biểu diễn nullable trong OpenAPI 3.0

OpenAPI 3.0 không hỗ trợ null như một giá trị hợp lệ của từ khóa type. Thay vào đó, Schema Object có trường riêng nullable.

Ví dụ thuộc tính nickname là chuỗi hoặc null:

~~~yaml
openapi: 3.0.3
components:
  schemas:
    Customer:
      type: object
      properties:
        nickname:
          type: string
          nullable: true
          maxLength: 80
~~~

Schema trên cho phép:

~~~json
{"nickname": "An"}
~~~

và:

~~~json
{"nickname": null}
~~~

Nhưng không cho phép số, boolean hoặc object ở thuộc tính nickname.

Theo OpenAPI 3.0.3, **nullable: true** chỉ có tác dụng khi **type** được khai báo rõ ràng trong cùng Schema Object. Nó thêm null vào tập giá trị của kiểu đó. Các ràng buộc khác vẫn được áp dụng và có thể tiếp tục loại một giá trị null trong một số cấu trúc schema.

Ví dụ sau không thể hiện nullable theo cách đáng tin cậy vì Schema Object không khai báo type tại cùng vị trí:

~~~yaml
nickname:
  nullable: true
  maxLength: 80
~~~

Hãy khai báo rõ type:

~~~yaml
nickname:
  type: string
  nullable: true
  maxLength: 80
~~~

Giá trị mặc định của nullable là false. Nếu thuộc tính không được phép null, không cần ghi nullable: false ở mọi nơi.

## 4. Giới hạn của nullable trong OpenAPI 3.0

OpenAPI 3.0 dùng một tập con Schema Object riêng dựa trên JSON Schema cũ. Không thể đặt type: null hoặc type: [string, "null"] như trong JSON Schema hiện đại.

Các ví dụ sau không hợp lệ theo cách biểu diễn kiểu của OpenAPI 3.0:

~~~yaml
# Không dùng trong OpenAPI 3.0
nickname:
  type: null
~~~

~~~yaml
# Mảng type không được hỗ trợ trong Schema Object của OpenAPI 3.0
nickname:
  type:
    - string
    - "null"
~~~

Hãy dùng type: string cùng nullable: true.

Một giới hạn khác liên quan đến $ref. Trong OpenAPI 3.0, Reference Object không được mở rộng bằng các thuộc tính tùy ý. Vì vậy, không nên viết nullable: true như một sibling của $ref rồi kỳ vọng mọi công cụ hiểu đó là schema nullable:

~~~yaml
# Không dựa vào cách viết này trong OpenAPI 3.0
nickname:
  $ref: '#/components/schemas/Nickname'
  nullable: true
~~~

nullable cũng không thể dùng như một cách nới lỏng ràng buộc kiểu đã được áp đặt bên trong schema được tham chiếu qua allOf. Một schema con không thể dùng allOf để bỏ ràng buộc kiểu của schema cha.

Nếu định nghĩa được tham chiếu phải nullable ở mọi nơi, có thể khai báo nullable ngay trong component đó:

~~~yaml
components:
  schemas:
    Nickname:
      type: string
      nullable: true
~~~

Nếu chỉ một vị trí sử dụng cần nullable, hãy cân nhắc khai báo schema inline với kiểu cụ thể và nullable: true, hoặc thiết kế lại các component để phạm vi nullable được thể hiện rõ. Tránh sửa component dùng chung nếu điều đó vô tình làm tất cả các vị trí tham chiếu cho phép null.

## 5. Biểu diễn null trong OpenAPI 3.1 bằng union type

OpenAPI 3.1 căn chỉnh Schema Object với JSON Schema Draft 2020-12. Từ khóa type có thể nhận một mảng kiểu, vì vậy có thể liệt kê kiểu dữ liệu thông thường cùng null.

Ví dụ:

~~~yaml
openapi: 3.1.0
components:
  schemas:
    Customer:
      type: object
      properties:
        nickname:
          type:
            - string
            - "null"
          maxLength: 80
~~~

Thuộc tính nickname chấp nhận chuỗi hoặc null. Đây là cách chuyển trực tiếp và dễ đọc từ ví dụ OpenAPI 3.0:

~~~yaml
# OpenAPI 3.0
type: string
nullable: true
~~~

~~~yaml
# OpenAPI 3.1
type:
  - string
  - "null"
~~~

Trong mảng type, "null" là tên kiểu dữ liệu JSON Schema, không phải chuỗi có giá trị "null" trong payload. Payload hợp lệ vẫn dùng JSON literal null:

~~~json
{"nickname": null}
~~~

Nếu schema chỉ cho phép null mà không cho phép kiểu nào khác, OpenAPI 3.1 có thể dùng:

~~~yaml
type: "null"
~~~

Trường hợp này khác với một thuộc tính nullable, vốn cho phép cả kiểu dữ liệu thông thường lẫn null.

## 6. Biểu diễn null bằng anyOf

OpenAPI 3.1 cũng có thể biểu diễn một giá trị là kiểu được tham chiếu hoặc null bằng anyOf:

~~~yaml
components:
  schemas:
    Nickname:
      type: string
      maxLength: 80

    Customer:
      type: object
      properties:
        nickname:
          anyOf:
            - $ref: '#/components/schemas/Nickname'
            - type: "null"
~~~

anyOf cho phép instance hợp lệ với ít nhất một schema con. Ở đây, giá trị phải thỏa schema Nickname hoặc phải là null.

Mẫu này hữu ích khi kiểu chính được tái sử dụng qua $ref. Nó giữ nguyên component Nickname không nullable trong những vị trí khác, nhưng cho phép một thuộc tính cụ thể nhận null.

Có thể dùng oneOf trong một số mô hình union khi các nhánh được thiết kế loại trừ lẫn nhau. Với nhánh null và một kiểu object/string thông thường, anyOf thường dễ hiểu và phù hợp cho mục tiêu biểu diễn nullable.

## 7. Enum nullable trong OpenAPI 3.1

Khi dùng union type cùng enum, cần nhớ enum vẫn là một ràng buộc độc lập. Nếu muốn cho phép null, giá trị null phải nằm trong danh sách enum.

Ví dụ:

~~~yaml
status:
  type:
    - string
    - "null"
  enum:
    - active
    - disabled
    - null
~~~

Nếu bỏ null khỏi enum, schema vẫn không chấp nhận null dù type có chứa "null", vì giá trị đó không nằm trong tập enum.

Một cách khác là đặt enum trong nhánh string và dùng nhánh null riêng:

~~~yaml
status:
  anyOf:
    - type: string
      enum:
        - active
        - disabled
    - type: "null"
~~~

Hai cách đều có thể mô tả union. Khi schema có nhiều ràng buộc hoặc dùng $ref, cách anyOf thường giúp nhìn rõ nhánh nào cho phép null.

## 8. Phân biệt nullable object và nullable array item

Một mảng có thể tự nó nullable, hoặc từng phần tử trong mảng có thể nullable. Đây là hai cấu trúc khác nhau.

### Mảng có thể null, phần tử luôn là chuỗi

~~~yaml
tags:
  type:
    - array
    - "null"
  items:
    type: string
~~~

Payload hợp lệ:

~~~json
{"tags": null}
~~~

hoặc:

~~~json
{"tags": ["java", "spring"]}
~~~

### Mảng luôn phải là mảng, nhưng phần tử có thể null

~~~yaml
tags:
  type: array
  items:
    type:
      - string
      - "null"
~~~

Payload hợp lệ:

~~~json
{"tags": ["java", null, "spring"]}
~~~

### Cả mảng và phần tử đều có thể null

~~~yaml
tags:
  type:
    - array
    - "null"
  items:
    type:
      - string
      - "null"
~~~

Hãy đặt union ở đúng cấp schema. Nếu đặt "null" vào items, điều đó chỉ cho phép một phần tử null; nó không làm cho toàn bộ mảng trở thành nullable.

## 9. Bảng so sánh OpenAPI 3.0 và 3.1

| Nội dung | OpenAPI 3.0 | OpenAPI 3.1 |
| --- | --- | --- |
| Cơ sở Schema Object | Tập con JSON Schema Draft 05 được điều chỉnh | JSON Schema Draft 2020-12 |
| Kiểu null trong type | Không hỗ trợ | Hỗ trợ |
| Biểu diễn string hoặc null | type: string, nullable: true | type: [string, "null"] |
| Biểu diễn ref hoặc null | Hạn chế; cần thiết kế schema riêng | anyOf với $ref và nhánh type: "null" |
| Kiểu union qua mảng type | Không hỗ trợ | Hỗ trợ |
| Từ khóa nullable | Từ khóa OpenAPI có ý nghĩa | Không còn là cách chuẩn; dùng JSON Schema null type |
| Validator/code generator | Cần hỗ trợ OAS 3.0 | Cần hỗ trợ OAS 3.1 và JSON Schema mới |

OpenAPI 3.1 không chỉ đổi cách viết nullable. Schema Object có nhiều thay đổi khác do căn chỉnh với JSON Schema 2020-12. Khi nâng cấp, hãy kiểm tra toàn bộ công cụ xử lý schema, không chỉ Swagger UI.

## 10. Chọn phiên bản OpenAPI khi dùng springdoc

Springdoc có thuộc tính springdoc.api-docs.version để chọn OpenAPI 3.0 hoặc 3.1. Ví dụ:

~~~yaml
springdoc:
  api-docs:
    version: OPENAPI_3_1
~~~

Để sinh tài liệu theo OpenAPI 3.0:

~~~yaml
springdoc:
  api-docs:
    version: OPENAPI_3_0
~~~

Tài liệu cấu hình springdoc hiện liệt kê giá trị mặc định openapi_3_1; enum cấu hình dùng các giá trị OPENAPI_3_0 và OPENAPI_3_1. Hãy kiểm tra phiên bản springdoc thực tế vì default và khả năng hỗ trợ có thể khác giữa các dòng phát hành.

Thuộc tính này chọn dialect OpenAPI mà springdoc sinh ra. Nó không thay đổi kiểu Java, Jackson serialization hoặc validation logic của controller. Cũng không nên tự sửa duy nhất trường openapi trong JSON đầu ra từ 3.0.x thành 3.1.x; schema bên trong cần được chuyển đổi theo đúng quy tắc.

## 11. Kiểm tra phiên bản và schema được sinh ra

Sau khi cấu hình springdoc, tải tài liệu JSON:

~~~bash
curl -sS http://localhost:8080/v3/api-docs -o openapi.json
~~~

Kiểm tra phiên bản ở cấp document:

~~~bash
jq -r '.openapi' openapi.json
~~~

Nếu cấu hình OpenAPI 3.1, trường openapi cần bắt đầu bằng 3.1. Nếu cấu hình 3.0, trường đó cần bắt đầu bằng 3.0.

Kiểm tra schema của model:

~~~bash
jq '.components.schemas.Customer' openapi.json
~~~

Với OpenAPI 3.0, tìm nullable: true ở property tương ứng. Với OpenAPI 3.1, tìm type có "null" hoặc nhánh anyOf/oneOf chứa schema type: "null".

Đừng chỉ kiểm tra Swagger UI có hiển thị được trang. Giao diện có thể render tài liệu trong khi validator hoặc code generator của downstream không hiểu một số cấu trúc schema.

## 12. Ánh xạ null từ Java model

Trong Java, kiểu tham chiếu như String, Integer, BigDecimal hoặc DTO có thể mang giá trị null. Kiểu primitive như int, long, boolean không thể chứa null.

Ví dụ:

~~~java
public record CustomerResponse(
    String id,
    String nickname,
    Integer age
) {}
~~~

Ở tầng Java, nickname và age có thể null nếu không có validation hoặc logic khác ngăn điều đó. Tuy nhiên, việc springdoc sinh schema nullable còn phụ thuộc phiên bản, annotation, model converter và cấu hình đang dùng.

Nếu hợp đồng cần nullable rõ ràng, hãy kiểm tra OpenAPI JSON sau khi sinh. Không suy ra schema chỉ từ việc field Java là kiểu tham chiếu.

Với kiểu primitive:

~~~java
public record CounterResponse(int count) {}
~~~

count không thể là null ở runtime. Nếu API cần biểu diễn count có thể null, dùng kiểu wrapper Integer hoặc một kiểu tham chiếu phù hợp và xác định rõ validation.

## 13. Bean Validation không thay thế mô tả nullable

Bean Validation kiểm tra dữ liệu tại runtime. Ví dụ:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record UpdateCustomerRequest(
    @NotNull
    String customerId,

    String nickname
) {}
~~~

@NotNull yêu cầu giá trị không null khi validation được thực thi. @NotBlank cũng từ chối null và chuỗi rỗng hoặc chỉ có khoảng trắng. Nếu một thuộc tính thực sự cho phép null, đừng gắn constraint cấm null vào chính thuộc tính đó.

Tuy nhiên, required trong OpenAPI nói về việc thuộc tính phải xuất hiện trong object, còn @NotNull kiểm tra giá trị sau khi Jackson bind request vào Java object. Với một số DTO, field bị bỏ qua và field được gửi rõ ràng là null có thể cùng trở thành giá trị Java null. Muốn phân biệt hai trường hợp trong PATCH, cần thiết kế request model và quá trình deserialization phù hợp.

Springdoc có thể đọc một số annotation Bean Validation để bổ sung ràng buộc vào schema. Hãy kiểm tra document được sinh ra và kiểm thử validation thật, thay vì giả định mọi annotation đều tự động tạo đúng required, nullable hoặc semantics của PATCH.

## 14. Jackson có thể làm thay đổi cách null xuất hiện trong JSON

Schema mô tả giá trị được phép, còn Jackson quyết định object Java được serialize thành JSON như thế nào.

Ví dụ:

~~~java
import com.fasterxml.jackson.annotation.JsonInclude;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record CustomerResponse(
    String id,
    String nickname
) {}
~~~

Nếu nickname là null, Jackson có thể bỏ hẳn thuộc tính khỏi response thay vì ghi "nickname": null. Đây là khác biệt giữa property vắng mặt và property có giá trị null.

Nếu hợp đồng yêu cầu response luôn chứa property với giá trị null, cần cấu hình serialization phù hợp, chẳng hạn không loại null khỏi JSON cho model hoặc property đó. Ngược lại, nếu hợp đồng cho phép server bỏ thuộc tính null, schema và mô tả response cần thể hiện rõ cách xử lý.

Đối với request, các cấu hình Jackson như xử lý null khi deserialize hoặc setter tùy chỉnh cũng có thể ảnh hưởng ý nghĩa của giá trị gửi lên. Vì vậy, kiểm thử cả JSON đầu vào, Java object sau binding và JSON response thực tế.

## 15. Tạo nullable schema bằng annotation hoặc customizer

Annotation của swagger-core có thể bổ sung metadata cho schema, nhưng khả năng sinh nullable phụ thuộc OpenAPI version và phiên bản swagger-core/springdoc đi kèm. Một annotation được viết cho OpenAPI 3.0 không nhất thiết tạo đúng union type cho OpenAPI 3.1.

Khi cần kiểm soát chính xác:

1. Chọn OpenAPI version bằng springdoc.api-docs.version.
2. Khai báo DTO và validation theo semantics nghiệp vụ.
3. Dùng annotation hoặc model converter/customizer phù hợp phiên bản.
4. Tải OpenAPI JSON và xác minh schema đầu ra.
5. Chạy validator và thử code generator của consumer thực tế.

Không tự chèn nullable: true vào mọi schema khi document đã khai báo OpenAPI 3.1. Trong 3.1, hãy ưu tiên union với kiểu null hoặc anyOf.

Nếu có nhiều component cùng tham chiếu một schema, hãy xác định nullable thuộc bản thân component hay chỉ thuộc property đang tham chiếu. Chọn cách khai báo tương ứng để không làm thay đổi hợp đồng của các endpoint khác.

## 16. Chiến lược chuyển đổi từ 3.0 sang 3.1

Khi nâng cấp một tài liệu hoặc hệ thống springdoc:

1. Kiểm kê các schema đang dùng nullable: true.
2. Chuyển type: string cùng nullable thành type: [string, "null"].
3. Với schema tham chiếu, dùng anyOf gồm $ref và nhánh type: "null" nếu chỉ một vị trí cần nullable.
4. Kiểm tra enum và bổ sung giá trị null khi cần.
5. Kiểm tra riêng nullable array và nullable array item.
6. Kiểm tra danh sách required để đảm bảo không nhầm bắt buộc với không-null.
7. Chạy validator OpenAPI 3.1 và JSON Schema tương thích.
8. Kiểm tra Swagger UI, API client generator, mock server và contract test.
9. So sánh request/response thực tế trước và sau chuyển đổi.

Một ví dụ chuyển đổi:

~~~yaml
# Trước: OpenAPI 3.0
components:
  schemas:
    Customer:
      type: object
      required:
        - nickname
      properties:
        nickname:
          type: string
          nullable: true
~~~

~~~yaml
# Sau: OpenAPI 3.1
components:
  schemas:
    Customer:
      type: object
      required:
        - nickname
      properties:
        nickname:
          type:
            - string
            - "null"
~~~

Hai schema trên giữ nguyên ý nghĩa: nickname phải có mặt, nhưng giá trị có thể là chuỗi hoặc null.

## 17. Lỗi thường gặp

**Dùng type: null trong OpenAPI 3.0.** OAS 3.0 không hỗ trợ null như một type. Dùng type cụ thể và nullable: true.

**Đưa nullable: true vào schema không có type.** Trong OAS 3.0, nullable chỉ có tác dụng khi type được khai báo trong cùng Schema Object.

**Cho rằng nullable đồng nghĩa optional.** Nullable cho phép giá trị null; optional nghĩa là thuộc tính có thể vắng mặt. Kiểm tra danh sách required.

**Dùng chuỗi "null" thay cho JSON null.** Giá trị JSON null không có dấu nháy. Chuỗi "null" là một string bình thường.

**Dùng type: [string, "null"] nhưng quên chuyển document lên OAS 3.1.** Mảng type không hợp lệ trong Schema Object OAS 3.0.

**Đặt nullable bên cạnh $ref trong OAS 3.0.** Reference Object không được mở rộng tùy ý. Đặt nullable trong component nếu mọi nơi tham chiếu đều cho phép null, hoặc thiết kế schema inline riêng.

**Dùng allOf để nới lỏng kiểu của schema được tham chiếu.** allOf kết hợp ràng buộc; schema con không thể bỏ ràng buộc không-null của schema cha.

**Union type cho phép null nhưng enum không chứa null.** Enum là một ràng buộc riêng. Bổ sung null vào enum hoặc tách nhánh null bằng anyOf.

**Nullable array bị nhầm với nullable item.** Đặt union ở cấp array hoặc cấp items đúng với payload mong muốn.

**Swagger UI hiển thị được nhưng code generator lỗi.** Kiểm tra toolchain có hỗ trợ OpenAPI 3.1 và JSON Schema 2020-12 không; nếu không, cân nhắc tiếp tục xuất OAS 3.0.

**Schema cho phép null nhưng response không có thuộc tính.** Kiểm tra Jackson JsonInclude và cấu hình serialization.

**Dùng @NotNull cho thuộc tính muốn nhận null.** Constraint sẽ từ chối null khi validation chạy. Đồng bộ validation với hợp đồng OpenAPI.

**Chỉ sửa trường openapi trong JSON.** Chuyển từ 3.0 sang 3.1 cần chuyển đổi Schema Object và kiểm tra toàn bộ document, không chỉ sửa version string.

## 18. Checklist thiết kế nullable

- [ ] Xác định API cần phân biệt null, thuộc tính vắng mặt và chuỗi rỗng hay không.
- [ ] Xác định property có bắt buộc xuất hiện trong object không.
- [ ] Với OAS 3.0, dùng type rõ ràng cùng nullable: true.
- [ ] Với OAS 3.1, dùng type array có "null" hoặc anyOf.
- [ ] Không dùng type array trong document OAS 3.0.
- [ ] Kiểm tra enum có cần chứa null.
- [ ] Phân biệt nullable array với nullable array item.
- [ ] Xử lý $ref theo đúng giới hạn của OAS 3.0 hoặc union của OAS 3.1.
- [ ] Chọn springdoc.api-docs.version theo khả năng của consumer.
- [ ] Đồng bộ Java type, Bean Validation và Jackson serialization.
- [ ] Kiểm tra OpenAPI JSON được sinh ra, không chỉ kiểm tra annotation.
- [ ] Chạy validator và contract test cho cả request lẫn response.

## 19. Kết luận

OpenAPI 3.0 biểu diễn giá trị null bằng nullable: true trên Schema Object có khai báo type rõ ràng. OpenAPI 3.1 dùng khả năng của JSON Schema 2020-12 để biểu diễn null như một kiểu trong union hoặc một nhánh anyOf. Trong cả hai phiên bản, nullable vẫn độc lập với required: một property có thể bắt buộc xuất hiện nhưng được phép mang giá trị null. Khi dùng springdoc, hãy chọn đúng phiên bản document, kiểm tra schema đầu ra và bảo đảm Java model, Bean Validation, Jackson cùng các công cụ consumer cùng hiểu một hợp đồng.

## 20. Nguồn tham khảo

- [OpenAPI Specification 3.0.3 — Data Types and Schema Object](https://spec.openapis.org/oas/v3.0.3.html): null không phải type và ý nghĩa của nullable.
- [OpenAPI Specification 3.1.2 — Schema Object](https://spec.openapis.org/oas/v3.1.2.html): Schema Object tương thích JSON Schema 2020-12 và cách biểu diễn type.
- [OpenAPI Initiative — Upgrading from OpenAPI 3.0 to 3.1](https://learn.openapis.org/upgrading/v3.0-to-v3.1.html): thay nullable bằng type array có null và các thay đổi schema khác.
- [springdoc-openapi — Configuration Properties](https://springdoc.org/properties.html): thuộc tính springdoc.api-docs.version để chọn OpenAPI 3.0 hoặc 3.1.
- [Swagger — OpenAPI 3.0 Data Types](https://swagger.io/docs/specification/v3_0/data-models/data-types/): null, nullable và sự khác nhau giữa nullable với optional.

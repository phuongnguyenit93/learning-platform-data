# Prompt và type

## Mục tiêu

HAL-FORMS mô tả các thao tác mà client có thể thực hiện và các trường dữ liệu cần gửi khi thực hiện thao tác. Mỗi property trong một template có tên máy đọc được, nhưng giao diện người dùng thường cần thêm nhãn dễ hiểu và gợi ý loại điều khiển phù hợp.

Hai thuộc tính quan trọng là:

- **prompt**: nhãn dành cho người dùng khi hiển thị trường nhập liệu, ví dụ “Họ và tên”.
- **type**: loại input mà client có thể dùng để trình bày trường, ví dụ text, email, date hoặc tel.

Spring HATEOAS có thể suy ra type từ kiểu Java hoặc validation annotation, cho phép ghi đè bằng @InputType, và tra cứu prompt từ resource bundle rest-messages. Nhờ vậy, server có thể mô tả form có nhãn dễ hiểu và phù hợp với dữ liệu mà endpoint mong đợi.

Sau bài học, bạn có thể:

- Phân biệt name, prompt, placeholder và type trong HAL-FORMS.
- Hiểu cách Spring HATEOAS tạo type từ kiểu Java và validation annotations.
- Ghi đè input type bằng @InputType.
- Định nghĩa prompt và placeholder qua rest-messages.properties.
- Bản địa hóa prompt theo locale của request.
- Kiểm thử prompt và type trong _templates.

## Prompt và type trong một property

Trong HAL-FORMS, template nằm trong _templates. Mỗi phần tử của properties mô tả một giá trị client có thể gửi khi thực hiện thao tác:

~~~json
{
  "_templates": {
    "default": {
      "title": "Tạo khách hàng",
      "method": "post",
      "contentType": "application/json",
      "properties": [
        {
          "name": "firstName",
          "prompt": "Họ và tên",
          "type": "text",
          "required": true
        },
        {
          "name": "birthdate",
          "prompt": "Ngày sinh",
          "type": "date",
          "required": true
        },
        {
          "name": "email",
          "prompt": "Địa chỉ email",
          "type": "email",
          "required": true
        },
        {
          "name": "phone",
          "prompt": "Số điện thoại",
          "placeholder": "+84 912 345 678",
          "type": "tel"
        }
      ]
    }
  }
}
~~~

Các thuộc tính có vai trò khác nhau:

| Thuộc tính | Vai trò | Ví dụ |
|---|---|---|
| name | Tên property để client gửi dữ liệu đúng trường mà server mong đợi. | firstName |
| prompt | Nhãn dễ đọc để hiển thị cạnh trường nhập liệu. | Họ và tên |
| placeholder | Gợi ý ngắn bên trong trường, thường là ví dụ về định dạng. | +84 912 345 678 |
| type | Gợi ý loại input hoặc điều khiển mà client nên dùng. | text, email, date, tel |
| required | Cho biết property có bắt buộc trong template hay không. | true |

name phục vụ hợp đồng dữ liệu giữa client và server; prompt phục vụ người dùng. Không nên đổi tên property chỉ để có nhãn hiển thị đẹp hơn. Hãy giữ name ổn định và dùng prompt để diễn đạt theo ngôn ngữ giao diện.

prompt là tùy chọn theo HAL-FORMS. Nếu không có prompt, client có thể dùng giá trị name làm nhãn mặc định. Spring HATEOAS chỉ đưa prompt vào response khi có metadata tương ứng, chẳng hạn giá trị được cấu hình trong resource bundle.

placeholder không thay thế prompt. Placeholder chỉ là gợi ý định dạng hoặc ví dụ; nó không nên là nhãn duy nhất của trường vì một số giao diện có thể ẩn placeholder khi người dùng bắt đầu nhập.

## Spring HATEOAS tạo type như thế nào?

Thuộc tính type mô tả loại input theo ngữ nghĩa HTML. Spring HATEOAS có thể suy ra giá trị này từ:

1. Annotation @InputType được khai báo trực tiếp trên property.
2. Validation annotation như @Email.
3. Kiểu Java của property, ví dụ String, LocalDate hoặc kiểu số.

Ví dụ các kết quả thường gặp:

| Khai báo property | Type có thể được tạo |
|---|---|
| String firstName | text |
| LocalDate birthdate | date |
| Integer quantity | number |
| @Email String email | email |
| @InputType("tel") String phone | tel |

Spring HATEOAS hỗ trợ các input type như text, email, date, number, tel, url, password, checkbox, radio, textarea, time và file. Đây là gợi ý cho client khi dựng giao diện; client có thể chọn cách hiển thị khác nếu nền tảng không hỗ trợ một loại input cụ thể.

### Dùng kiểu Java và validation annotations

Nên định nghĩa một input representation riêng cho request thay vì dùng trực tiếp entity persistence. Ví dụ:

~~~java
import java.time.LocalDate;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;

public class CustomerInput {

    @NotNull
    private String firstName;

    private LocalDate birthdate;

    @Email
    private String email;

    @Pattern(regexp = "^[0-9+ -]{8,20}$")
    private String phone;

    // Constructors, getters và setters.
}
~~~

Từ model này, Spring HATEOAS có thể suy ra:

- firstName là input text; @NotNull có thể làm property được mô tả là bắt buộc.
- birthdate là input date vì kiểu Java là LocalDate.
- email là input email nhờ @Email.
- phone là input text theo kiểu String; @Pattern được biểu diễn bằng metadata regex.

Các validation annotation cung cấp thông tin về dữ liệu hợp lệ, không chỉ để tạo giao diện. Ví dụ @Email vừa giúp suy ra input type email, vừa là ràng buộc validation khi server kiểm tra request. Tuy nhiên, client có thể bỏ qua metadata; server vẫn phải thực thi validation khi nhận dữ liệu.

### Ghi đè type bằng @InputType

Khi kiểu Java không đủ để suy ra input phù hợp, dùng @InputType để khai báo rõ loại input:

~~~java
import org.springframework.hateoas.InputType;

public class CustomerInput {

    private String firstName;

    @InputType("tel")
    private String phone;

    // Getters và setters.
}
~~~

phone vẫn là String trong Java, nhưng HAL-FORMS có thể công bố type: tel để client chọn input dành cho số điện thoại. @InputType có thể đặt trên field hoặc getter. Annotation này ghi đè type được suy ra từ kiểu property hoặc validation annotations.

Chỉ dùng giá trị type có ngữ nghĩa phù hợp với client. Ví dụ, không gán number cho số điện thoại chỉ vì dữ liệu chứa chữ số; số điện thoại có thể có dấu cộng, khoảng trắng hoặc số 0 ở đầu và không phải đại lượng dùng để tính toán.

## Định nghĩa prompt bằng rest-messages

Spring HATEOAS sử dụng resource bundle rest-messages để tra cứu các chuỗi hiển thị trong HAL-FORMS. Để định nghĩa prompt, thêm hậu tố ._prompt vào tên property.

Ví dụ file rest-messages.properties:

~~~properties
CustomerInput.firstName._prompt=First name
CustomerInput.birthdate._prompt=Date of birth
CustomerInput.email._prompt=Email address
CustomerInput.phone._prompt=Phone number
~~~

Các khóa có thể được khai báo ở phạm vi khác nhau:

~~~properties
# Áp dụng cho các property có tên firstName trên mọi kiểu.
firstName._prompt=First name

# Áp dụng cho property firstName trong các kiểu có tên CustomerInput.
CustomerInput.firstName._prompt=Customer first name

# Áp dụng cho đúng kiểu có tên đầy đủ com.example.api.CustomerInput.
com.example.api.CustomerInput.firstName._prompt=Customer's legal name
~~~

Phạm vi toàn cục hữu ích khi một property có cùng nhãn ở nhiều model. Khóa theo tên class hoặc tên đầy đủ giúp dùng nhãn riêng khi cùng một tên property có ý nghĩa khác nhau ở các model khác nhau.

Không cần thêm thuộc tính prompt vào DTO chỉ để phục vụ giao diện. Prompt được lấy từ resource bundle và đưa vào metadata HAL-FORMS khi representation được serialize.

## Placeholder cũng được cấu hình qua resource bundle

Placeholder dùng hậu tố ._placeholder:

~~~properties
CustomerInput.phone._prompt=Phone number
CustomerInput.phone._placeholder=+84 912 345 678
CustomerInput.email._prompt=Email address
CustomerInput.email._placeholder=name@example.com
~~~

Ví dụ property được serialize:

~~~json
{
  "name": "phone",
  "prompt": "Phone number",
  "placeholder": "+84 912 345 678",
  "type": "tel"
}
~~~

Prompt nên ngắn gọn và mô tả dữ liệu cần nhập. Placeholder nên minh họa định dạng hoặc một giá trị mẫu. Không đưa dữ liệu cá nhân thật vào placeholder.

## Bản địa hóa prompt theo locale

Prompt và placeholder là văn bản hướng tới người dùng, nên có thể bản địa hóa bằng các resource bundle theo locale. Ví dụ:

rest-messages.properties:

~~~properties
CustomerInput.firstName._prompt=First name
CustomerInput.birthdate._prompt=Date of birth
CustomerInput.email._prompt=Email address
CustomerInput.phone._prompt=Phone number
CustomerInput.phone._placeholder=+1 555 010 2000
~~~

rest-messages_vi.properties:

~~~properties
CustomerInput.firstName._prompt=Họ và tên
CustomerInput.birthdate._prompt=Ngày sinh
CustomerInput.email._prompt=Địa chỉ email
CustomerInput.phone._prompt=Số điện thoại
CustomerInput.phone._placeholder=+84 912 345 678
~~~

Client gửi Accept-Language để yêu cầu locale:

~~~http
GET /api/customers
Accept: application/prs.hal-forms+json
Accept-Language: vi
~~~

Spring HATEOAS sử dụng cơ chế resource bundle của Spring để phân giải chuỗi theo locale hiện tại. Khi có bản dịch tương ứng, prompt và placeholder trong response sẽ dùng ngôn ngữ được chọn. Nếu không có bản dịch phù hợp, resource bundle có thể quay về giá trị mặc định trong rest-messages.properties.

Prompt cho property khác với title của template:

- _templates.default.title đặt tiêu đề cho cả form, ví dụ “Tạo khách hàng”.
- CustomerInput.firstName._prompt đặt nhãn cho một trường, ví dụ “Họ và tên”.
- CustomerInput.firstName._placeholder đặt gợi ý bên trong trường.

Khi template là affordance duy nhất, tên template trong HAL-FORMS là default. Khi có nhiều affordances, tên template thường được suy ra từ tên method hoặc tên affordance đã cấu hình. Hãy dùng đúng tên template khi cấu hình title; prompt của property vẫn được phân giải theo input type.

## Kết hợp prompt và type với affordance

Để Spring HATEOAS tạo metadata cho property, input model phải được khai báo là kiểu request body của controller method được gắn affordance. Ví dụ:

~~~java
import jakarta.validation.Valid;

import org.springframework.http.MediaType;
import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@RestController
class CustomerController {

    @GetMapping("/api/customers")
    CollectionModel<EntityModel<CustomerSummary>> findAll() {
        CollectionModel<EntityModel<CustomerSummary>> model =
                loadCustomers();

        model.add(linkTo(methodOn(CustomerController.class)
                .findAll())
                .withSelfRel()
                .andAffordance(afford(methodOn(CustomerController.class)
                        .create(null))));

        return model;
    }

    @PostMapping(
            path = "/api/customers",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    EntityModel<CustomerSummary> create(
            @Valid @RequestBody CustomerInput input) {
        // Validate input, tạo khách hàng và trả representation.
        return null;
    }
}
~~~

Controller công bố affordance POST trên link self của collection. Spring HATEOAS đọc kiểu CustomerInput, các annotation validation và metadata @InputType để tạo properties trong template. Vì mapping có consumes = application/json, template có thể công bố contentType tương ứng.

Bật HAL-FORMS bằng cấu hình:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.config.EnableHypermediaSupport;
import org.springframework.hateoas.config.EnableHypermediaSupport.HypermediaType;

@Configuration
@EnableHypermediaSupport(type = HypermediaType.HAL_FORMS)
class HypermediaConfiguration {
}
~~~

Client yêu cầu media type application/prs.hal-forms+json để nhận _templates. HAL JSON và HAL-FORMS là hai media type riêng; không nên giả định client chỉ hỗ trợ HAL JSON sẽ hiển thị prompt hoặc type.

## Kiểm thử prompt và type

MockMvc có thể xác minh metadata mà server công bố. Giả sử thứ tự property trong input model là firstName, birthdate, email, phone:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;

mockMvc.perform(get("/api/customers")
                .header("Accept-Language", "vi")
                .accept(MediaTypes.HAL_FORMS_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$._templates.default.properties[0].name")
                .value("firstName"))
        .andExpect(jsonPath("$._templates.default.properties[0].prompt")
                .value("Họ và tên"))
        .andExpect(jsonPath("$._templates.default.properties[1].type")
                .value("date"))
        .andExpect(jsonPath("$._templates.default.properties[2].type")
                .value("email"))
        .andExpect(jsonPath("$._templates.default.properties[3].type")
                .value("tel"))
        .andExpect(jsonPath("$._templates.default.properties[3].placeholder")
                .value("+84 912 345 678"));
~~~

Ví dụ dùng chỉ số mảng để minh họa; trong test của ứng dụng, có thể tìm property theo name để tránh phụ thuộc thứ tự khai báo. Nếu có nhiều templates, thay default bằng tên template thực tế.

Nên kiểm thử các trường hợp:

- Prompt xuất hiện đúng ngôn ngữ khi gửi Accept-Language.
- Placeholder không bị dùng nhầm làm prompt.
- String, LocalDate và kiểu số tạo ra type mong đợi.
- @Email tạo type email và @InputType ghi đè type theo yêu cầu.
- @NotNull và validation annotations tạo metadata ràng buộc phù hợp.
- Template PATCH không đánh dấu tất cả property là bắt buộc.
- Khi thiếu bản dịch, resource bundle mặc định được dùng.

## Những lỗi thường gặp

- **Dùng prompt thay cho name:** prompt dành cho người dùng; name là khóa property trong payload. Giữ name ổn định và bản địa hóa prompt.
- **Dùng placeholder làm nhãn duy nhất:** placeholder có thể biến mất khi nhập liệu; hãy cung cấp prompt riêng.
- **Cho rằng type là validation:** type: email gợi ý input email nhưng không thay thế @Email và validation phía server.
- **Dùng kiểu Java để quyết định mọi input:** String mặc định thường là text; dùng @InputType khi cần tel, search hoặc loại phù hợp hơn.
- **Dùng entity persistence làm input model:** entity có thể chứa trường không nên cho client gửi. Tạo request representation riêng.
- **Cấu hình sai resource bundle key:** hậu tố phải là ._prompt hoặc ._placeholder, và tên class/property phải khớp input model.
- **Nhầm template title với property prompt:** title đặt tên form; prompt đặt nhãn cho một trường.
- **Giả định mọi client hiểu type giống nhau:** type là metadata cho client; giao diện thực tế phụ thuộc khả năng của client.
- **Chỉ dựa vào metadata để bảo vệ dữ liệu:** server vẫn phải validate và kiểm tra quyền khi nhận request.

## Quy trình thiết kế prompt và type

1. Tạo input representation riêng mô tả chính xác dữ liệu client được phép gửi.
2. Đặt tên property ổn định để server bind payload đúng trường.
3. Dùng kiểu Java và validation annotations để cung cấp type và ràng buộc cơ bản.
4. Dùng @InputType khi muốn ghi đè loại input được suy ra.
5. Định nghĩa prompt và placeholder trong rest-messages.properties bằng hậu tố tương ứng.
6. Bổ sung resource bundle theo locale và kiểm tra Accept-Language.
7. Gắn input model vào controller method được tham chiếu bởi affordance.
8. Kiểm thử _templates để bảo vệ prompt, type, placeholder và validation metadata.

prompt giúp người dùng hiểu cần nhập dữ liệu gì; type giúp client chọn cách nhập phù hợp. Khi Spring HATEOAS suy ra type từ model và validation, còn prompt được quản lý qua resource bundle, HAL-FORMS có thể mô tả form vừa có cấu trúc máy đọc được vừa có nhãn phù hợp với ngôn ngữ người dùng.

## Tài liệu tham khảo

- Spring HATEOAS Reference Documentation, HAL-FORMS metadata: https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.hal-forms
- Spring HATEOAS Reference Documentation, internationalization of form attributes: https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.hal-forms.i18n
- Spring HATEOAS API, @InputType: https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/InputType.html
- HAL-FORMS media type specification: https://rwcbook.com/hal-forms/
# Prompt và type

Trong HAL-FORMS, mỗi phần tử trong mảng `properties` mô tả một trường dữ liệu mà client có thể hiển thị hoặc gửi khi thực hiện một affordance. Hai metadata quan trọng là **prompt** và **type**. `prompt` cung cấp nhãn dễ hiểu cho người dùng; `type` gợi ý loại điều khiển nhập liệu mà client nên dùng, chẳng hạn text, email, date hoặc number.

Spring HATEOAS tạo metadata HAL-FORMS từ input model của controller và cho phép tùy biến nó bằng annotation cùng resource bundle. Nhờ đó, tên thuộc tính trong hợp đồng dữ liệu có thể giữ ổn định trong khi nhãn hiển thị được dịch theo ngôn ngữ người dùng và kiểu điều khiển được suy ra từ kiểu Java, validation annotation hoặc khai báo tường minh.

Trong module SPRING_HATEOAS, prompt và type là một phần của cách mô tả hành động khả dụng trong REST API hypermedia. Bài học này tập trung vào ý nghĩa của từng thuộc tính, cách Spring HATEOAS tạo chúng, cách cấu hình nhãn đa ngôn ngữ bằng `rest-messages` và cách dùng `@InputType` để điều chỉnh input control.

Sau bài học, bạn có thể:

- Phân biệt `name`, `prompt`, `placeholder` và `type` trong HAL-FORMS.
- Hiểu cách client sử dụng prompt làm nhãn trường.
- Tùy biến prompt bằng resource bundle `rest-messages`.
- Cung cấp prompt theo locale và `Accept-Language`.
- Hiểu cách Spring HATEOAS suy ra type từ kiểu Java và validation annotation.
- Override type bằng `@InputType`.
- Phân biệt type với media type của request và với danh sách lựa chọn `options`.
- Kiểm thử prompt, type và hành vi tương thích của HAL-FORMS response.

## Prompt và type nằm ở đâu trong HAL-FORMS?

HAL-FORMS mở rộng HAL bằng thuộc tính `_templates`. Mỗi template mô tả một thao tác có thể thực hiện, bao gồm HTTP method, target và danh sách các trường đầu vào. Một property có thể chứa `name`, `prompt`, `type`, `required`, `readOnly`, `placeholder` và các metadata validation khác.

Ví dụ:

~~~json
{
  "_links": {
    "self": {
      "href": "/customers"
    }
  },
  "_templates": {
    "default": {
      "title": "Create customer",
      "method": "POST",
      "contentType": "application/json",
      "properties": [
        {
          "name": "fullName",
          "prompt": "Customer name",
          "type": "text",
          "required": true
        },
        {
          "name": "email",
          "prompt": "Email address",
          "type": "email",
          "required": true,
          "placeholder": "name@example.com"
        },
        {
          "name": "birthDate",
          "prompt": "Date of birth",
          "type": "date"
        }
      ]
    }
  }
}
~~~

Client đọc template để dựng form. Với property `email`, client có thể dùng `name` làm tên trường gửi lên server, `prompt` làm nhãn hiển thị, `type` để chọn input email và `placeholder` làm gợi ý định dạng.

`prompt` và `type` không đứng độc lập. Chúng chỉ có ý nghĩa khi gắn với một property trong template được tạo từ affordance. Nếu controller không công bố affordance phù hợp hoặc client yêu cầu media type khác, response có thể không chứa `_templates`.

## Phân biệt name, prompt, placeholder và type

Bốn thuộc tính này phục vụ các mục đích khác nhau:

| Thuộc tính | Vai trò | Ví dụ |
| --- | --- | --- |
| `name` | Tên thuộc tính trong payload hoặc tham số | `email` |
| `prompt` | Nhãn dễ đọc để hiển thị cho người dùng | `Địa chỉ email` |
| `placeholder` | Gợi ý ngắn về định dạng hoặc giá trị mẫu | `ten@example.com` |
| `type` | Gợi ý loại input control và kiểu dữ liệu | `email` |

Ví dụ, một form có thể gửi thuộc tính `email` nhưng hiển thị nhãn `Địa chỉ email liên hệ`. Đổi prompt không làm thay đổi tên trường trong JSON request. Đổi type cũng không đổi tên thuộc tính hoặc tự thay đổi hợp đồng JSON.

### name là tên dữ liệu

`name` liên kết property trong template với thuộc tính đầu vào. Client cần giữ tên này khi serialize dữ liệu gửi lên server.

Ví dụ:

~~~json
{
  "name": "phoneNumber",
  "prompt": "Số điện thoại liên hệ",
  "type": "tel"
}
~~~

Request vẫn dùng key `phoneNumber`:

~~~json
{
  "phoneNumber": "+84901234567"
}
~~~

Client không được thay key thành `Số điện thoại liên hệ` chỉ vì đó là prompt. Prompt là metadata dành cho giao diện, không phải tên trường dữ liệu.

### prompt là nhãn hiển thị

`prompt` là chuỗi dành cho con người, thường được hiển thị bên cạnh hoặc phía trên input control. Theo HAL-FORMS, thuộc tính này là tùy chọn. Nếu không có prompt, client có thể dùng giá trị `name` làm nhãn mặc định.

Vì prompt hướng đến người dùng cuối, nên:

- Dùng từ ngữ rõ nghĩa, ngắn gọn và nhất quán.
- Tránh đưa tên kỹ thuật như `cust_eml_addr` lên giao diện.
- Dùng cùng thuật ngữ cho các trường có cùng ý nghĩa.
- Cung cấp bản dịch theo locale khi API phục vụ nhiều ngôn ngữ.

Prompt không thay thế mô tả nghiệp vụ dài, thông báo lỗi hoặc hướng dẫn validation. Nếu người dùng cần ví dụ định dạng, hãy dùng placeholder; nếu cần giới hạn dữ liệu, công bố metadata validation và vẫn xác thực ở server.

### placeholder là gợi ý, không phải nhãn

`placeholder` đưa ra một ví dụ hoặc gợi ý ngắn bên trong input. Nó không thay thế prompt vì placeholder có thể biến mất khi người dùng nhập dữ liệu và có thể không đủ rõ với công nghệ hỗ trợ.

Ví dụ:

~~~json
{
  "name": "email",
  "prompt": "Địa chỉ email",
  "placeholder": "ten@example.com",
  "type": "email"
}
~~~

Prompt nói trường này là gì; placeholder minh họa một giá trị có định dạng phù hợp. Hai thuộc tính có thể được bản địa hóa độc lập.

### type là gợi ý loại input

`type` cho biết loại điều khiển nhập liệu hoặc kiểu dữ liệu mà client có thể dùng để hiển thị property. Giá trị này thường tương ứng với HTML input type, ví dụ `text`, `email`, `date` hoặc `number`.

Type không phải media type của toàn bộ request. `contentType` ở cấp template mới mô tả media type server mong đợi, ví dụ `application/json`. Một template có thể có `contentType: application/json` và từng property có `type: email` hoặc `type: date`.

## Prompt trong Spring HATEOAS

Spring HATEOAS cho phép định nghĩa prompt thông qua resource bundle tên `rest-messages`. Bundle này được cấu hình để Spring HATEOAS tra cứu các chuỗi hiển thị khi tạo HAL-FORMS metadata.

Quy tắc đặt key cho prompt là:

~~~properties
<property>._prompt=<nhãn hiển thị>
~~~

Có thể khai báo key ở ba phạm vi:

~~~properties
# Áp dụng cho mọi property có tên email
email._prompt=Email address

# Áp dụng cho property email trong kiểu CustomerInput
CustomerInput.email._prompt=Customer email

# Áp dụng cho property email trong kiểu com.example.api.CustomerInput
com.example.api.CustomerInput.email._prompt=Customer email address
~~~

Phạm vi toàn cục phù hợp khi cùng một property name luôn có cùng ý nghĩa. Phạm vi theo kiểu giúp dùng nhãn riêng cho DTO cụ thể. Phạm vi tên đầy đủ phù hợp khi nhiều package có các kiểu trùng tên.

### Cấu hình nhãn tiếng Việt

Đặt resource bundle trong classpath, thường dưới `src/main/resources`:

`rest-messages.properties` có thể chứa nhãn mặc định:

~~~properties
CustomerInput.fullName._prompt=Customer name
CustomerInput.email._prompt=Email address
CustomerInput.phoneNumber._prompt=Phone number
CustomerInput.birthDate._prompt=Date of birth
~~~

`rest-messages_vi.properties` chứa bản dịch tiếng Việt:

~~~properties
CustomerInput.fullName._prompt=Họ và tên
CustomerInput.email._prompt=Địa chỉ email
CustomerInput.phoneNumber._prompt=Số điện thoại
CustomerInput.birthDate._prompt=Ngày sinh
~~~

Khi client gửi `Accept-Language: vi`, Spring HATEOAS có thể chọn message tiếng Việt nếu bundle tương ứng có sẵn. Nếu không có bản dịch phù hợp, cơ chế MessageSource của Spring sẽ áp dụng fallback theo cấu hình locale và bundle mặc định.

Ví dụ request:

~~~http
GET /customers HTTP/1.1
Accept: application/prs.hal-forms+json
Accept-Language: vi
~~~

Response có thể chứa:

~~~json
{
  "_templates": {
    "default": {
      "method": "POST",
      "properties": [
        {
          "name": "fullName",
          "prompt": "Họ và tên",
          "type": "text"
        },
        {
          "name": "email",
          "prompt": "Địa chỉ email",
          "type": "email"
        }
      ]
    }
  }
}
~~~

### Định nghĩa placeholder bằng resource bundle

Placeholder dùng cùng cơ chế tra cứu, với hậu tố `._placeholder`:

~~~properties
CustomerInput.email._prompt=Địa chỉ email
CustomerInput.email._placeholder=ten@example.com
CustomerInput.phoneNumber._prompt=Số điện thoại
CustomerInput.phoneNumber._placeholder=+84 90 123 4567
~~~

Prompt và placeholder có thể được dịch riêng. Không đưa thông tin nhạy cảm hoặc dữ liệu thật của người dùng vào placeholder.

### Template title khác property prompt

Template có thể có `title` riêng để mô tả toàn bộ thao tác, ví dụ `Tạo khách hàng`. Property prompt mô tả từng trường bên trong form.

Trong resource bundle, template title sử dụng key theo affordance name:

~~~properties
_templates.createCustomer.title=Tạo khách hàng
CustomerInput._template.createCustomer.title=Tạo khách hàng mới
~~~

Tên template có thể là `default` khi chỉ có một template. Khi có nhiều affordance, tên template thường được suy ra từ tên method hoặc được cấu hình rõ. Không dùng key template title thay cho key property prompt.

## Type trong Spring HATEOAS

Spring HATEOAS xây dựng type metadata dựa trên input model mà affordance trỏ tới. Thứ tự nguồn thông tin có thể gồm:

1. Annotation `@InputType` khai báo type tường minh trên field hoặc accessor.
2. Validation annotation có ngữ nghĩa phù hợp, ví dụ `@Email`.
3. Kiểu Java của property, ví dụ `String` hoặc `LocalDate`.

Nếu không có type phù hợp hoặc client không hiểu type được công bố, HAL-FORMS cho phép client quay về cách nhập văn bản đơn giản theo quy tắc của đặc tả. Vì vậy, type nên là gợi ý tương thích, không phải điều kiện duy nhất để server chấp nhận dữ liệu.

### Type suy ra từ kiểu Java

Spring HATEOAS có thể suy ra một số input type từ kiểu property. Ví dụ:

| Kiểu hoặc metadata | Type thường được tạo |
| --- | --- |
| `String` | `text` |
| `LocalDate` | `date` |
| Kiểu số như `Integer`, `Long` hoặc `BigDecimal` | `number` |
| `@Email` | `email` |

Đây là các ví dụ thường gặp; kết quả cụ thể phụ thuộc kiểu dữ liệu, validation metadata và phiên bản Spring HATEOAS. Hãy kiểm tra response thực tế khi thêm kiểu domain riêng hoặc kiểu wrapper.

Ví dụ input model:

~~~java
import java.math.BigDecimal;
import java.time.LocalDate;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class CustomerInput {

    @NotBlank
    private String fullName;

    @NotBlank
    @Email
    private String email;

    private LocalDate birthDate;

    @NotNull
    private BigDecimal monthlyBudget;

    // Getters and setters
}
~~~

Spring HATEOAS có thể tạo các property có type tương ứng như `text`, `email`, `date` và `number`. Validation annotation còn có thể đóng góp metadata khác như `required`, `min`, `max` hoặc `regex` tùy annotation được hỗ trợ.

Lưu ý: `@Pattern` thường cung cấp metadata regex. Nó không có nghĩa mọi chuỗi có pattern đều tự chuyển thành một input type đặc biệt.

### Override type bằng @InputType

Khi kiểu Java không diễn tả đúng loại input mong muốn, dùng `@InputType`:

~~~java
import org.springframework.hateoas.InputType;

public class CustomerInput {

    private String fullName;

    @InputType("tel")
    private String phoneNumber;

    @InputType("textarea")
    private String note;

    @InputType("password")
    private String temporaryPassword;

    // Getters and setters
}
~~~

`@InputType` thuộc package `org.springframework.hateoas` và có thể đặt trên field hoặc method. Annotation nhận một chuỗi type. Nó dùng để override type được suy ra từ kiểu Java hoặc validation metadata.

Trong ví dụ, cả `phoneNumber` và `note` đều có kiểu Java `String`. Nếu chỉ dựa trên kiểu Java, chúng có thể được suy ra là `text`. Annotation giúp công bố `tel` cho số điện thoại và `textarea` cho nội dung nhiều dòng. Field mật khẩu có thể dùng `password` để client hiển thị điều khiển nhập mật khẩu.

### Các type thường gặp

Spring HATEOAS cung cấp các giá trị input type theo nhóm HTML phổ biến:

| Type | Mục đích thường gặp |
| --- | --- |
| `text` | Văn bản một dòng |
| `textarea` | Văn bản nhiều dòng |
| `email` | Địa chỉ email |
| `tel` | Số điện thoại |
| `url` | URL |
| `password` | Mật khẩu |
| `number` | Giá trị số |
| `range` | Giá trị trong một khoảng |
| `date` | Ngày |
| `datetime-local` | Ngày và giờ địa phương |
| `month`, `week`, `time` | Tháng, tuần hoặc thời gian |
| `checkbox`, `radio` | Điều khiển chọn |
| `color`, `search`, `hidden` | Các loại input chuyên biệt |

Spring HATEOAS có các hằng số trong `HtmlInputType` cho những type được hỗ trợ. Đặc tả HAL-FORMS và client cụ thể có thể hỗ trợ tập con khác nhau. Client không hiểu type có thể dùng input text mặc định hoặc cách xử lý dự phòng.

Với các lựa chọn có tập giá trị xác định, `type` không thay thế metadata `options`. Ví dụ danh sách phương thức vận chuyển nên công bố các giá trị có thể chọn bằng `options`; type chỉ gợi ý cách hiển thị điều khiển, như radio hoặc checkbox khi phù hợp.

## Kết hợp prompt và type với affordance

Prompt và type chỉ được tạo khi Spring HATEOAS có thông tin về input model của affordance. Một cách phổ biến là gắn affordance POST vào link collection hoặc self link:

~~~java
import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@RestController
@RequestMapping("/customers")
class CustomerController {

    @GetMapping
    CollectionModel<EntityModel<CustomerResponse>> all() {
        var collection = CollectionModel.of(customerService.findAll().stream()
            .map(customerAssembler::toModel)
            .toList());

        collection.add(linkTo(methodOn(CustomerController.class).all())
            .withSelfRel()
            .andAffordance(afford(methodOn(CustomerController.class)
                .create(null))));

        return collection;
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    EntityModel<CustomerResponse> create(@RequestBody CustomerInput input) {
        Customer customer = customerService.create(input);
        return customerAssembler.toModel(customer);
    }
}
~~~

Ví dụ giả định các dependency service và assembler được inject bằng constructor, cùng các kiểu Customer, CustomerInput và CustomerResponse đã được định nghĩa. Khi Spring HATEOAS phân tích affordance trỏ đến method `create`, nó đọc input model `CustomerInput` để tạo property metadata.

Nếu client gửi:

~~~http
GET /customers HTTP/1.1
Accept: application/prs.hal-forms+json
Accept-Language: vi
~~~

response HAL-FORMS có thể chứa template tương tự:

~~~json
{
  "_templates": {
    "default": {
      "method": "POST",
      "contentType": "application/json",
      "properties": [
        {
          "name": "fullName",
          "prompt": "Họ và tên",
          "type": "text",
          "required": true
        },
        {
          "name": "email",
          "prompt": "Địa chỉ email",
          "type": "email",
          "required": true
        },
        {
          "name": "phoneNumber",
          "prompt": "Số điện thoại",
          "type": "tel"
        },
        {
          "name": "birthDate",
          "prompt": "Ngày sinh",
          "type": "date"
        }
      ]
    }
  }
}
~~~

Response là ví dụ minh họa. Property order, giá trị required và các metadata khác phụ thuộc input model, annotation, affordance và phiên bản thư viện. Spring HATEOAS có thể bỏ qua các thuộc tính metadata khi chúng bằng giá trị mặc định theo đặc tả; không nên yêu cầu mọi property luôn phải có tường minh `required: false` hoặc `readOnly: false`.

## Type không thay thế validation phía server

Type giúp client chọn input control và có thể hỗ trợ trình duyệt kiểm tra định dạng cơ bản. Nó không đảm bảo dữ liệu gửi lên hợp lệ.

Ví dụ, `type: email` có thể khiến trình duyệt hiển thị input email, nhưng server vẫn phải kiểm tra:

- Email có đúng định dạng theo quy tắc ứng dụng không?
- Email đã được sử dụng chưa?
- Người gửi có quyền đăng ký email đó không?
- Giá trị có vượt giới hạn độ dài không?

Tương tự, `type: number` không tự xác định giá trị nhỏ nhất hoặc lớn nhất. Nếu có giới hạn, hãy công bố metadata như `min` và `max` khi có thể, đồng thời validate bằng annotation hoặc logic nghiệp vụ ở server.

`prompt` cũng không phải thông báo lỗi. Prompt mô tả trường; lỗi validation cần được trả bằng response lỗi phù hợp, chẳng hạn Problem Details hoặc cấu trúc lỗi API mà ứng dụng quy định.

## Tách input model khỏi domain model

HAL-FORMS mô tả các trường mà client được phép gửi. Không nên mặc định dùng entity persistence làm input model, vì entity có thể chứa ID, trạng thái nội bộ, khóa ngoại hoặc thuộc tính mà client không được sửa.

Hãy tạo DTO đầu vào riêng:

~~~java
public class CustomerInput {

    @NotBlank
    private String fullName;

    @Email
    @NotBlank
    private String email;

    @InputType("tel")
    private String phoneNumber;

    // Getters and setters
}
~~~

DTO này chỉ công bố các trường được phép nhập. Service nhận DTO, xác thực và chuyển thành domain object. Cách tách biệt này giúp metadata HAL-FORMS phản ánh đúng hợp đồng request và tránh vô tình công bố trường nội bộ.

Nếu cùng một domain type được dùng cho nhiều thao tác, mỗi affordance có thể trỏ đến input model riêng. Ví dụ thao tác tạo khách hàng cần tên và email, còn thao tác cập nhật địa chỉ chỉ cần địa chỉ. Prompt và type được tạo theo input model của từng affordance.

## Kiểm thử prompt và type

Kiểm thử nên xác minh response HAL-FORMS có đúng prompt, type và media type. Không chỉ kiểm tra template tồn tại.

Ví dụ với MockMvc:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class CustomerHalFormsMetadataTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void exposesVietnamesePromptAndInputType() throws Exception {
        mockMvc.perform(get("/customers")
                .header("Accept", "application/prs.hal-forms+json")
                .header("Accept-Language", "vi"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                "application/prs.hal-forms+json"))
            .andExpect(jsonPath("$._templates.default.properties").isArray())
            .andExpect(jsonPath(
                "$._templates.default.properties[?(@.name == 'email')].prompt")
                .exists())
            .andExpect(jsonPath(
                "$._templates.default.properties[?(@.name == 'phoneNumber')].type")
                .exists());
    }
}
~~~

Test giả định endpoint công bố affordance tạo khách hàng, bundle tiếng Việt được nạp và template duy nhất có tên `default`. Nếu response có nhiều template hoặc tên template khác, cập nhật JSONPath theo hợp đồng thực tế.

Trong test tích hợp đầy đủ, nên kiểm tra giá trị cụ thể thay vì chỉ kiểm tra field tồn tại. Có thể dùng JsonPath predicate hoặc parse JSON để tìm property theo `name`, sau đó so sánh prompt và type mong đợi. Cách tìm theo tên property bền vững hơn việc phụ thuộc vào thứ tự phần tử trong mảng.

Các trường hợp nên kiểm thử:

1. Property có prompt tùy biến được render đúng.
2. Property không có prompt vẫn có thể dùng name làm nhãn dự phòng ở client.
3. Prompt được dịch theo `Accept-Language`.
4. Placeholder dùng key `._placeholder` và được dịch độc lập.
5. Kiểu Java tạo type mong đợi.
6. `@Email` tạo type email khi phù hợp.
7. `@InputType` override type suy ra từ kiểu Java.
8. Metadata type không làm thay đổi tên property trong request body.
9. Validation phía server vẫn từ chối dữ liệu không hợp lệ.
10. Client yêu cầu media type HAL-FORMS nhận đúng Content-Type.

## Những sai lầm thường gặp

**Dùng prompt làm tên thuộc tính JSON.** Prompt là nhãn hiển thị. `name` mới là key client gửi lên server.

**Dùng placeholder thay prompt.** Placeholder chỉ là gợi ý trong input và có thể biến mất khi người dùng nhập. Hãy cung cấp nhãn prompt riêng.

**Nghĩ type là media type của request.** Type thuộc từng property; `contentType` thuộc template và mô tả media type của payload.

**Nghĩ type tự xác thực dữ liệu.** Type chỉ là metadata để client hiển thị điều khiển. Server vẫn phải validate request.

**Cố dùng kiểu Java để mô tả mọi input control.** Một trường String có thể là số điện thoại, mật khẩu hoặc văn bản nhiều dòng. Dùng `@InputType` khi suy luận mặc định không phù hợp.

**Dùng @Pattern để mong có type đặc biệt.** Pattern thường tạo metadata regex. Dùng `@InputType` để override input type.

**Đưa nhãn giao diện vào DTO hoặc domain object.** Prompt và placeholder nên nằm trong resource bundle để có thể bản địa hóa mà không đổi hợp đồng dữ liệu.

**Chỉ kiểm thử một locale.** Nếu API hỗ trợ nhiều ngôn ngữ, kiểm thử cả locale mặc định, locale được hỗ trợ và fallback.

**Coi metadata HAL-FORMS là bắt buộc với mọi client.** Client có thể bỏ qua type hoặc prompt không hiểu. Server cần giữ validation và semantics request độc lập với giao diện.

## Kết luận

Trong HAL-FORMS, `prompt` là nhãn dành cho người dùng, còn `type` gợi ý loại input control phù hợp với một property. `name` vẫn là tên dữ liệu trong request; `placeholder` chỉ là gợi ý định dạng; `contentType` mới xác định media type của payload. Spring HATEOAS tạo prompt và type từ input model, validation metadata, kiểu Java và annotation tùy chỉnh.

Hãy dùng `rest-messages` để quản lý prompt và placeholder theo locale, dùng `@InputType` khi type suy ra không đúng ý nghĩa trường, và thiết kế DTO đầu vào riêng cho từng thao tác. Kiểm thử response HAL-FORMS với các locale và type khác nhau, đồng thời luôn xác thực dữ liệu ở server vì metadata giao diện không thay thế quy tắc nghiệp vụ.

Tài liệu tham khảo:

- [Spring HATEOAS Reference — Defining HAL-FORMS metadata and property prompts](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.hal-forms).
- [Spring HATEOAS 3.1.2 Javadoc — InputType](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/InputType.html).
- [Spring HATEOAS 3.1.2 Javadoc — HtmlInputType](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/mediatype/html/HtmlInputType.html).

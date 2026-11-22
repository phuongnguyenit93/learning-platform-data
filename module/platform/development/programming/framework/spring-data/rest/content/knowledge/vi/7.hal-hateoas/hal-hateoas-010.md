# HAL-FORMS và biểu mẫu thao tác khi phiên bản, media type hỗ trợ

## 1. HAL-FORMS giải quyết vấn đề gì?

Spring Data REST dùng hypermedia để giúp client khám phá API. Ở định dạng HAL, một resource thường chứa dữ liệu và các link trong thuộc tính _links. Ví dụ, collection people có thể cung cấp link self, profile và search.

HAL cho client biết có thể đi đến đâu, nhưng bản thân HAL không mô tả đầy đủ cách thực hiện một state transition. Chỉ nhìn một link, client thường chưa biết:

- Có những thao tác HTTP nào được hỗ trợ trên resource?
- Thao tác đó dùng GET, POST, PUT, PATCH hay DELETE?
- Gửi payload đến URI nào?
- Payload cần những trường nào, trường nào bắt buộc?
- Trường có kiểu dữ liệu, giới hạn hoặc danh sách lựa chọn ra sao?

HAL-FORMS bổ sung mô tả biểu mẫu ở thời điểm chạy. Nó vẫn giữ cách biểu diễn resource và link gần với HAL, đồng thời thêm thuộc tính _templates để mô tả các thao tác mà server muốn quảng bá.

HAL-FORMS là một media type riêng, không phải tên khác của HAL. Hai định dạng không thể thay thế cho nhau chỉ vì chúng có cấu trúc gần giống.

## 2. HAL, HAL-FORMS và ALPS khác nhau thế nào?

| Định dạng | Media type | Vai trò |
|---|---|---|
| HAL | application/hal+json | Biểu diễn resource, embedded resource và các link để điều hướng |
| HAL-FORMS | application/prs.hal-forms+json | Biểu diễn resource, link và template mô tả cách gửi các thao tác |
| ALPS | application/alps+json | Mô tả profile ngữ nghĩa của resource và các state transition ở mức khái niệm |

Ví dụ HAL tối giản:

~~~~json
{
  "firstName": "Frodo",
  "_links": {
    "self": {
      "href": "https://api.example.com/people/1"
    },
    "collection": {
      "href": "https://api.example.com/people"
    }
  }
}
~~~~

Client biết URI của item và collection, nhưng không có biểu mẫu mô tả cách cập nhật item.

Cùng resource đó ở HAL-FORMS có thể chứa thêm các template:

~~~~json
{
  "firstName": "Frodo",
  "_links": {
    "self": {
      "href": "https://api.example.com/people/1"
    }
  },
  "_templates": {
    "default": {
      "title": "Update person",
      "method": "put",
      "contentType": "application/json",
      "properties": [
        {
          "name": "firstName",
          "prompt": "First name",
          "required": true,
          "type": "text"
        }
      ]
    },
    "partiallyUpdatePerson": {
      "title": "Partially update person",
      "method": "patch",
      "contentType": "application/merge-patch+json",
      "properties": [
        {
          "name": "firstName",
          "required": false,
          "type": "text"
        }
      ]
    }
  }
}
~~~~

Client HAL-FORMS có thể đọc template, tạo form phù hợp, thu thập giá trị và gửi request theo method, target và content type đã mô tả. HAL-FORMS không tự tạo giao diện HTML; client cần hiểu định dạng này và quyết định cách hiển thị form.

## 3. Content negotiation: client phải yêu cầu đúng media type

Media type của HAL-FORMS là:

~~~~http
application/prs.hal-forms+json
~~~~

Client yêu cầu representation bằng header Accept:

~~~~http
GET /people/1 HTTP/1.1
Host: api.example.com
Accept: application/prs.hal-forms+json
~~~~

Nếu server và message converter hỗ trợ HAL-FORMS, response có thể có:

~~~~http
HTTP/1.1 200 OK
Content-Type: application/prs.hal-forms+json
~~~~

Khi client yêu cầu HAL:

~~~~http
GET /people/1 HTTP/1.1
Host: api.example.com
Accept: application/hal+json
~~~~

server trả về representation HAL thông thường. Client không nên yêu cầu HAL-FORMS rồi tự giả định mọi response đều chứa _templates; server chỉ có thể quảng bá những affordance đã được đăng ký và được phép hiển thị.

Cần phân biệt hai header khi submit form:

- **Accept** mô tả định dạng response mà client muốn nhận.
- **Content-Type** mô tả định dạng payload client gửi lên.

Ví dụ client gửi JSON để tạo resource và muốn nhận response HAL-FORMS:

~~~~http
POST /people
Accept: application/prs.hal-forms+json
Content-Type: application/json

{
  "firstName": "Frodo"
}
~~~~

Nếu không có converter hoặc cấu hình tương thích cho media type được yêu cầu, server có thể từ chối content negotiation (thường gặp 406 Not Acceptable). Nếu body gửi lên có Content-Type không được endpoint chấp nhận, request có thể gặp 415 Unsupported Media Type. Cần xem response thực tế và cấu hình endpoint thay vì suy ra chỉ từ việc dependency HAL-FORMS có mặt trong classpath.

## 4. Bật hỗ trợ HAL-FORMS trong Spring HATEOAS

Spring HATEOAS cung cấp hỗ trợ render các representation model thành HAL-FORMS. Ví dụ cấu hình được tài liệu Spring HATEOAS sử dụng:

~~~~java
@Configuration
@EnableHypermediaSupport(type = HypermediaType.HAL_FORMS)
public class HypermediaConfiguration {
}
~~~~

Các import tương ứng nằm trong Spring HATEOAS, gồm EnableHypermediaSupport và HypermediaType. Trong Spring Boot hoặc Spring Data REST application, cần xem cấu hình auto-configuration và message converter mà phiên bản đang dùng đã đăng ký trước khi thêm cấu hình thủ công. Tránh đăng ký converter hoặc hypermedia configuration trùng lặp mà không kiểm tra.

Một vài điểm cần xác nhận trong dependency tree:

- Phiên bản Spring Boot quản lý phiên bản Spring Data release train nào.
- Phiên bản Spring Data REST và Spring HATEOAS có tương thích với nhau không.
- Spring HATEOAS có HAL-FORMS module/converter tương ứng hay không.
- MVC message converters có nhận application/prs.hal-forms+json hay không.
- Endpoint thực sự trả Content-Type HAL-FORMS khi client gửi Accept tương ứng hay không.

Không nên nâng riêng Spring HATEOAS lên một phiên bản tùy ý bên cạnh Spring Boot BOM. Dùng dependency management của Spring Boot hoặc Spring Data BOM để giữ các module cùng release train, trừ khi dự án có lý do rõ ràng và đã kiểm thử tương thích.

## 5. Affordance là nguồn thông tin tạo biểu mẫu

HAL-FORMS template được tạo từ affordance. Affordance mô tả một thao tác có thể thực hiện liên quan đến resource hoặc link, thường được suy ra từ method của Spring MVC/WebFlux controller.

Thông tin của method đích có thể cung cấp:

- URI và HTTP method.
- Kiểu payload đầu vào.
- Media type mà method chấp nhận.
- Các thuộc tính của payload.
- Ràng buộc validation và thông tin hiển thị của từng thuộc tính.

Ví dụ một controller có thao tác cập nhật đầy đủ và cập nhật một phần:

~~~~java
@RestController
class PersonController {

    @PutMapping(path = "/people/{id}", consumes = "application/json")
    Person update(
            @PathVariable Long id,
            @Valid @RequestBody PersonInput input) {
        // cập nhật resource
        return ...;
    }

    @PatchMapping(
            path = "/people/{id}",
            consumes = "application/merge-patch+json")
    Person partiallyUpdate(
            @PathVariable Long id,
            @RequestBody PersonPatch input) {
        // cập nhật một phần
        return ...;
    }
}
~~~~

Một representation model có thể gắn các affordance của hai method vào link self của person. Khi được render ở HAL-FORMS, các affordance trở thành hai template, chẳng hạn default cho PUT và partiallyUpdate cho PATCH.

Ví dụ cấu trúc kết quả:

~~~~json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/people/1"
    }
  },
  "_templates": {
    "default": {
      "method": "put",
      "contentType": "application/json",
      "properties": [
        { "name": "firstName", "required": true },
        { "name": "lastName", "required": true }
      ]
    },
    "partiallyUpdate": {
      "method": "patch",
      "contentType": "application/merge-patch+json",
      "properties": [
        { "name": "firstName", "required": false },
        { "name": "lastName", "required": false }
      ]
    }
  }
}
~~~~

Nếu chỉ có một template, tên template thường là default. Khi có nhiều thao tác, template có thể mang tên affordance để client phân biệt.

## 6. Gắn affordance vào resource Spring Data REST

Spring Data REST xuất bản repository resource, nhưng việc có collection/item endpoint không đồng nghĩa tất cả thao tác đều tự động có HAL-FORMS template.

Tài liệu tích hợp Spring Data REST và Spring HATEOAS từ Spring Data Pascal mô tả khả năng render affordance dưới dạng HAL-FORMS. Tuy vậy, ví dụ tích hợp cũng chỉ ra rằng form không tự động xuất hiện cho mọi thao tác repository. Ứng dụng phải chủ động gắn affordance vào link muốn quảng bá.

Một cách làm là dùng RepresentationModelProcessor để bổ sung affordance cho link của root resource. Ví dụ dưới đây gắn thao tác tạo order vào link orders:

~~~~java
@Component
class RootResourceModelProcessor
        implements RepresentationModelProcessor<RepositoryLinksResource> {

    @Override
    public RepositoryLinksResource process(RepositoryLinksResource model) {

        var affordance = afford(
            methodOn(OrderController.class)
                .placeOrder(null, null, null)
        );

        return model.mapLink(
            LinkRelation.of("orders"),
            link -> link.andAffordance(affordance)
        );
    }
}
~~~~

Controller nhận payload cho thao tác tạo:

~~~~java
@BasePathAwareController
class OrderController {

    @PostMapping(path = "/orders", consumes = "application/json")
    ResponseEntity<?> placeOrder(
            @Valid @RequestBody OrderInput input,
            Errors errors) {
        // validate và thực hiện nghiệp vụ tạo order
        return ...;
    }
}
~~~~

Trong ví dụ, affordance tham chiếu đến method placeOrder. Spring HATEOAS dùng mapping và kiểu payload để tạo mô tả thao tác. Khi client yêu cầu HAL-FORMS tại root resource, template có thể được gắn vào link orders, với target là endpoint tạo order.

Điểm cần lưu ý:

- RepresentationModelProcessor chỉ làm giàu representation; nó không tạo endpoint mới.
- Method được tham chiếu phải thực sự tồn tại và được Spring MVC/Spring Data REST route đến.
- DTO đầu vào quyết định các field được mô tả trong form.
- Nếu link chỉ xuất hiện ở một trạng thái nhất định, hãy thêm affordance có điều kiện theo trạng thái đó.
- Cần kiểm tra import và kiểu RepositoryLinksResource theo phiên bản Spring Data REST của dự án.

Nếu nghiệp vụ không phù hợp với CRUD thuần, custom controller và DTO thường là cách tốt để mô tả chính xác payload của thao tác. Ví dụ, tạo order có thể cần danh sách URI của sản phẩm và địa điểm giao hàng, chứ không nên cho client gửi toàn bộ entity nội bộ.

## 7. Metadata của template và field

HAL-FORMS mô tả metadata ở hai cấp.

### Template attributes

| Thuộc tính | Ý nghĩa |
|---|---|
| title | Tiêu đề thân thiện với người dùng của thao tác |
| method | HTTP method dùng khi submit, ví dụ post, put, patch hoặc delete |
| target | URI nhận request; chỉ cần render khi khác link mà affordance gắn vào |
| contentType | Media type của request body mà server chấp nhận |
| properties | Danh sách field mà client gửi trong payload |

### Property attributes

| Thuộc tính | Ý nghĩa |
|---|---|
| name | Tên thuộc tính trong payload |
| prompt | Nhãn gợi ý cho người dùng |
| placeholder | Ví dụ hoặc gợi ý định dạng của giá trị |
| type | Kiểu input gợi ý, ví dụ text, number, date, email |
| required | Field có bắt buộc không |
| readOnly | Field chỉ đọc, không được chỉnh sửa trong form |
| regex | Pattern kiểm tra giá trị |
| min / max | Giới hạn giá trị số hoặc phạm vi |
| minLength / maxLength | Giới hạn độ dài chuỗi |
| options | Các lựa chọn hợp lệ, có thể inline hoặc lấy từ resource khác |

Spring HATEOAS có thể suy ra một phần metadata từ kiểu payload, accessor và validation annotation. Ví dụ:

~~~~java
public class PersonInput {

    @NotBlank
    @Size(max = 80)
    private String firstName;

    @Email
    private String email;

    @Pattern(regexp = "[0-9]{10}")
    private String phoneNumber;

    @NotNull
    private LocalDate birthDate;
}
~~~~

Các annotation như NotNull, Pattern, Size, Min và Max có thể góp phần mô tả required, regex, min/max hoặc maxLength trong template. Kiểu Java và cấu hình input type cũng có thể được chuyển thành type phù hợp cho client.

Đây là metadata hỗ trợ tạo UI và kiểm tra đầu vào phía client. Server vẫn phải validate payload khi nhận request. Không được coi field required hoặc regex trong HAL-FORMS là ranh giới bảo mật.

## 8. Cấu hình options cho field

Một field có thể cần giới hạn giá trị được chọn, chẳng hạn shippingMethod hoặc location. HAL-FORMS hỗ trợ hai cách mô tả options.

**Inline options** phù hợp với tập giá trị nhỏ và ít thay đổi:

~~~~java
@Configuration
class HalFormsOptionsConfiguration {

    @Bean
    HalFormsConfiguration halFormsConfiguration() {
        return new HalFormsConfiguration()
            .withOptions(
                OrderInput.class,
                "shippingMethod",
                metadata -> HalFormsOptions.inline("Standard", "Express")
            );
    }
}
~~~~

Client có thể hiển thị dropdown hoặc select với các lựa chọn đã khai báo.

**Remote options** phù hợp với danh sách động, dài hoặc phụ thuộc dữ liệu:

~~~~java
HalFormsOptions.remote(
    Link.of("/shipping-methods{?q}").withRel("options")
)
~~~~

Template có thể cung cấp URI template để client lấy danh sách lựa chọn khi cần. Resource options thường trả về các giá trị scalar hoặc các cặp value/prompt để tách giá trị gửi lên khỏi nhãn hiển thị.

Khi dùng remote options, cần kiểm tra:

- URI options có được client truy cập qua authentication hiện tại không.
- Có phân trang hoặc lọc khi danh sách lớn không.
- Giá trị value có đúng định dạng endpoint nhận không.
- Server có kiểm tra lại lựa chọn khi submit không.

## 9. Đặt title, prompt và placeholder theo ngôn ngữ

Các giá trị hiển thị như title, prompt và placeholder có thể được quốc tế hóa bằng resource bundle mà Spring HATEOAS dùng (mặc định có thể cấu hình qua bundle rest-messages).

Ví dụ:

~~~~properties
_templates.default.title=Create person
_templates.updatePerson.title=Update person
firstName._prompt=First name
firstName._placeholder=Enter your first name
email._prompt=Email address
~~~~

Có thể dùng key tổng quát, key theo tên class hoặc tên đầy đủ của class để tránh trùng thuộc tính giữa các payload type. Khi nhiều template tồn tại, tên affordance cụ thể giúp xác định title tương ứng.

Nên đặt prompt dễ hiểu cho người dùng API, còn tên field vẫn giữ theo payload mà endpoint nhận. Client có thể hiển thị prompt thay vì phơi bày tên thuộc tính kỹ thuật.

## 10. Phân biệt biểu mẫu HAL-FORMS với HAL Explorer

HAL-FORMS là định dạng biểu diễn hypermedia. HAL Explorer là một ứng dụng client có thể đọc các representation đó và tạo giao diện khám phá API.

HAL Explorer có thể:

- Theo các link HAL và URI template.
- Hiển thị các thao tác HTTP có thể thực hiện.
- Dùng metadata của Spring Data REST/JSON Schema để tạo trường nhập cho một số response HAL.
- Đọc _templates của HAL-FORMS để hiển thị các form và ràng buộc được mô tả.
- Hiển thị options và validation metadata mà template cung cấp.

Không nên nhầm việc HAL Explorer dựng được form từ Spring profile/JSON Schema với việc server đã trả HAL-FORMS. Đó là hai nguồn metadata khác nhau:

- HAL + Spring Data REST profile/JSON Schema: client có thể suy ra cấu trúc payload từ metadata.
- HAL-FORMS: server gửi trực tiếp template thao tác qua _templates.

HAL Explorer hữu ích khi phát triển và kiểm tra API. Với ứng dụng thực tế, client có thể là web frontend, mobile app hoặc một service khác, miễn là client hiểu HAL-FORMS.

## 11. Kiểm tra HAL-FORMS trong ứng dụng

Nên kiểm tra theo từng bước để xác định lỗi nằm ở dependency, content negotiation hay affordance.

### Bước 1 — Kiểm tra HAL mặc định

~~~~bash
curl -i \
  -H "Accept: application/hal+json" \
  http://localhost:8080/
~~~~

Xác nhận response có Content-Type application/hal+json và các link trong _links.

### Bước 2 — Yêu cầu HAL-FORMS

~~~~bash
curl -i \
  -H "Accept: application/prs.hal-forms+json" \
  http://localhost:8080/
~~~~

Kiểm tra:

- Status code có phải 2xx không.
- Content-Type có đúng application/prs.hal-forms+json không.
- Body có _links và _templates không.
- Template có method, target hoặc link đích, contentType và properties như mong muốn không.

### Bước 3 — Kiểm tra từng thao tác

Với mỗi template, gửi request bằng method, target và contentType được mô tả. Kiểm tra server thực sự route đến method tương ứng và áp dụng validation.

### Bước 4 — Kiểm tra fallback

Gửi lại Accept: application/hal+json. Client không hỗ trợ HAL-FORMS vẫn phải có thể tiếp tục điều hướng bằng link HAL nếu API cung cấp representation đó.

### Bước 5 — Kiểm tra trạng thái và quyền

Affordance chỉ nên xuất hiện khi thao tác thực sự khả dụng. Ví dụ, chỉ quảng bá thao tác thanh toán khi order đang ở trạng thái chờ thanh toán và user hiện tại có quyền thanh toán. Server vẫn phải kiểm tra quyền và trạng thái khi request được gửi; ẩn template không thay thế authorization.

Có thể viết MockMvc integration test để kiểm tra response media type và JSONPath của _templates:

~~~~java
mockMvc.perform(get("/people/1")
        .accept("application/prs.hal-forms+json"))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
        MediaType.parseMediaType("application/prs.hal-forms+json")))
    .andExpect(jsonPath("$._templates").exists());
~~~~

Nếu test không thấy _templates, kiểm tra xem link có affordance hay chưa, controller method có mapping đúng không, converter có được đăng ký không và phiên bản HATEOAS có hỗ trợ định dạng này không.

## 12. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Response luôn là HAL | Client gửi Accept HAL, hoặc HAL-FORMS chưa được cấu hình | Xem request Accept và response Content-Type |
| 406 Not Acceptable | Không có converter/handler đáp ứng media type yêu cầu | Kiểm tra Spring HATEOAS version và message converters |
| Response HAL-FORMS nhưng không có _templates | Resource chưa được gắn affordance hoặc không có thao tác phù hợp | Kiểm tra RepresentationModelProcessor và affordance |
| Có template nhưng thiếu field | Input DTO hoặc payload metadata không được suy ra như mong muốn | Kiểm tra @RequestBody type, accessors và validation annotations |
| Field required không đúng | Validation annotation hoặc loại template chưa phản ánh hợp đồng | Kiểm tra @NotNull, @NotBlank và PUT/PATCH semantics |
| Form submit bị 415 | Content-Type gửi lên không khớp consumes của endpoint | Đọc contentType trong template và mapping controller |
| Form submit bị 400 | Payload không đúng cấu trúc hoặc validation thất bại | Đọc lỗi binding/validation từ response |
| Client không hiển thị form | Client không hỗ trợ HAL-FORMS hoặc không đọc _templates | Thử HAL Explorer hoặc client có parser HAL-FORMS |

Một lỗi quan trọng khác là chỉ thêm dependency rồi kỳ vọng mọi CRUD operation tự động có form. Dependency chỉ cung cấp khả năng kỹ thuật; server vẫn phải có affordance được gắn vào resource và converter phải render được affordance đó.

## 13. Giới hạn và lưu ý thiết kế

- HAL-FORMS mô tả thao tác, không thực thi thao tác thay client.
- Template không phải HTML form; client cần tự render và gửi HTTP request.
- Không phải mọi resource đều cần form. Chỉ quảng bá transition phù hợp với trạng thái nghiệp vụ.
- Một form mô tả payload đầu vào, nhưng không thay thế tài liệu nghiệp vụ, authorization hoặc server validation.
- HAL-FORMS không phải mọi thao tác CRUD tự động được biểu diễn. Đặc biệt với Spring Data REST, hãy chủ động bổ sung affordance khi cần form cho custom operation.
- Đừng gắn affordance vào link không liên quan hoặc trỏ đến method không được route công khai.
- Giữ HAL representation cho client đơn giản; chỉ dùng HAL-FORMS khi client cần metadata của thao tác và có khả năng tiêu thụ định dạng.
- Kiểm tra tương thích theo release train đang sử dụng. Tài liệu Spring HATEOAS và Spring Data REST có thể mô tả các phiên bản khác nhau; không lấy một ví dụ cũ rồi áp dụng nguyên xi cho mọi bản Spring Boot.

## 14. Kết luận

HAL cung cấp link để client khám phá resource. HAL-FORMS mở rộng representation bằng _templates để mô tả method, target, content type và field của thao tác. Spring HATEOAS tạo các template đó từ affordance và metadata của input payload; Spring Data REST có thể tích hợp cơ chế này khi phiên bản và cấu hình hỗ trợ.

Để tạo form thao tác trong API, cần bảo đảm đủ ba điều kiện: server hỗ trợ media type application/prs.hal-forms+json, resource được gắn affordance cho method đích, và client biết cách đọc _templates. Sau đó, client vẫn gửi request bình thường và server vẫn chịu trách nhiệm kiểm tra dữ liệu, trạng thái nghiệp vụ và quyền truy cập.

## Tài liệu tham khảo

- [Spring HATEOAS Reference — HAL-FORMS](https://docs.spring.io/spring-hateoas/docs/2.5.1/reference/html/#mediatypes.hal-forms)
- [Spring HATEOAS Reference — Affordances](https://docs.spring.io/spring-hateoas/docs/2.5.1/reference/html/#server.affordances)
- [Spring Data REST Reference — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST Reference — HAL Explorer](https://docs.spring.io/spring-data/rest/reference/tools.html)
- [Spring RESTBucks in 2021 — Advertising the order creation using HAL-FORMS](https://odrotbohm.github.io/2021/04/Spring-RESTBucks-in-2021/)
- [HAL-FORMS Media Type Specification](https://rwcbook.github.io/hal-forms/)

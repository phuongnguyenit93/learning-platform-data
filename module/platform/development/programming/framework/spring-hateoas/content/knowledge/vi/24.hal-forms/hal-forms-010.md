# Khi nào dùng HAL-FORMS trong Spring HATEOAS?

HAL-FORMS phù hợp khi API cần cho client khám phá cả tài nguyên lẫn cách thực hiện các thao tác có request input. Định dạng này đặc biệt hữu ích với client có thể dựng giao diện hoặc tạo request từ metadata nhận được lúc chạy, thay vì phải biết trước mọi trường payload và endpoint hành động.

Tuy nhiên, không phải API nào dùng Spring HATEOAS cũng cần HAL-FORMS. Nếu client chỉ cần theo các liên kết tới tài nguyên, HAL thông thường có thể đã đủ. Nếu mọi client đều là ứng dụng cố định với hợp đồng request được triển khai sẵn, việc thêm form template có thể làm tăng chi phí mà ít đem lại lợi ích. Quyết định nên dựa trên cách client tương tác, mức độ thay đổi của quy trình và khả năng mô tả payload bằng metadata HAL-FORMS.

## 1. Mục tiêu của HAL-FORMS

HAL cung cấp `_links` để client khám phá tài nguyên và `_embedded` để nhận dữ liệu được nhúng. Một link HAL cơ bản thường có `rel` và `href`; nó chưa mô tả đầy đủ các trường mà client cần gửi khi thực hiện thao tác tạo hoặc cập nhật.

HAL-FORMS mở rộng representation bằng `_templates`. Một template có thể mô tả:

- HTTP method của thao tác.
- URI target mà request được gửi tới.
- Content type của request body.
- Các property đầu vào, loại input và một số ràng buộc.
- Tên hiển thị, prompt, placeholder hoặc options khi được cấu hình.

Client đọc metadata này để tạo form hoặc payload. Vì vậy, HAL-FORMS hữu ích khi server muốn công bố khả năng tương tác cùng dữ liệu, thay vì chỉ công bố đích điều hướng.

## 2. Dùng HAL-FORMS khi client cần khám phá request tại runtime

Tình huống điển hình là một client tổng quát không được viết riêng cho từng loại tài nguyên. Client nhận response, đọc template và dựng giao diện dựa trên metadata.

Ví dụ API quản lý nhân viên công bố thao tác tạo mới:

```json
{
  "_links": {
    "self": { "href": "/employees" }
  },
  "_templates": {
    "createEmployee": {
      "method": "POST",
      "target": "/employees",
      "contentType": "application/json",
      "properties": [
        { "name": "name", "type": "text", "required": true },
        { "name": "email", "type": "email", "required": true },
        { "name": "department", "type": "text" }
      ]
    }
  }
}
```

Client có thể đọc `createEmployee`, hiển thị các trường phù hợp, kiểm tra những ràng buộc được công bố và gửi POST tới target. Khi server thay đổi một số trường đầu vào, client có thể nhận metadata mới mà không cần suy ra payload từ tên class hoặc đường dẫn nội bộ của server.

Điều này có giá trị với các ứng dụng quản trị tổng quát, portal nội bộ, công cụ tích hợp hoặc client cần thích nghi với nhiều loại tài nguyên. Client vẫn cần biết cách hiểu HAL-FORMS và các quy tắc nghiệp vụ cốt lõi; định dạng không biến một client bất kỳ thành ứng dụng tự động hiểu mọi quy trình.

## 3. Dùng khi các thao tác khả dụng thay đổi theo trạng thái tài nguyên

Một tài nguyên có thể cho phép các hành động khác nhau tùy trạng thái. Ví dụ, đơn hàng đang chờ có thể được hủy; đơn đã giao không còn khả năng hủy. Server có thể công bố affordance phù hợp với trạng thái hiện tại.

| Trạng thái đơn hàng | Thao tác có thể công bố |
| --- | --- |
| `PENDING` | `cancel`, `update` |
| `PROCESSING` | Có thể chỉ còn `cancel`, tùy chính sách |
| `SHIPPED` | `track`, `view-invoice` |
| `CANCELLED` | `view-details` |

Ví dụ assembler tạo self link và chỉ gắn affordance hủy khi nghiệp vụ cho phép:

```java
EntityModel<OrderView> toModel(Order order) {
    Link self = linkTo(methodOn(OrderController.class)
            .one(order.getId())).withSelfRel();

    if (order.canBeCancelled()) {
        self = self.andAffordance(afford(
                methodOn(OrderController.class).cancel(order.getId())
        ));
    }

    return EntityModel.of(toView(order), self);
}
```

Khi client yêu cầu HAL-FORMS, affordance có thể được biểu diễn thành template tương ứng. Client có thể hiển thị hành động dựa trên trạng thái mà server công bố.

Việc không công bố affordance không thay thế phân quyền. Endpoint `cancel` vẫn phải kiểm tra quyền và trạng thái khi nhận request, vì client có thể giữ response cũ hoặc gọi URI trực tiếp.

## 4. Dùng khi thao tác cần payload mà client có thể tạo từ metadata

HAL-FORMS có ích khi request body có các trường tương đối rõ ràng và metadata có thể giúp client dựng form. Ví dụ:

- Tạo nhân viên với tên, email và phòng ban.
- Cập nhật địa chỉ giao hàng với đường phố, thành phố và mã bưu chính.
- Gửi yêu cầu hỗ trợ với tiêu đề, nội dung và mức độ ưu tiên.
- Cập nhật một phần tài nguyên bằng PATCH.
- Gửi yêu cầu phê duyệt với ghi chú và lựa chọn trạng thái.

Spring HATEOAS có thể suy ra input metadata từ kiểu tham số `@RequestBody`, annotation validation và mapping controller được tham chiếu bởi affordance. Client có thể dùng `required`, `readOnly`, `type`, `regex`, giới hạn min/max hoặc options để hỗ trợ nhập liệu.

HAL-FORMS phù hợp nhất khi metadata mô tả được phần lớn cấu trúc đầu vào mà client cần. Nếu quy tắc payload phụ thuộc nhiều điều kiện lồng nhau, nhiều loại dữ liệu phức tạp hoặc thuật toán nghiệp vụ khó biểu diễn, template có thể không đủ để client tạo request đúng nếu không có tài liệu bổ sung.

## 5. Dùng khi muốn giảm sự phụ thuộc của client vào URL và payload cố định

Client hypermedia nên lấy URI từ relation hoặc template do server công bố. Khi kết hợp với HAL-FORMS, client còn có thể lấy method, target và content type từ template thay vì tự ghép endpoint và request.

Ví dụ một client có thể:

1. Gọi entry point API.
2. Theo relation `orders` để tới collection.
3. Đọc template `createOrder`.
4. Lấy `target`, `method` và `contentType` từ template.
5. Dựng payload theo danh sách property.
6. Gửi request và đọc representation trả về.

Nếu server thay đổi mapping hoặc bổ sung trường payload mà vẫn giữ relation và semantics phù hợp, client có thể tiếp tục khám phá thao tác qua response mới. Khả năng thích nghi này chỉ có được khi client thực sự đọc và sử dụng hypermedia; client ghi cứng URL hoặc bỏ qua template vẫn phụ thuộc vào hợp đồng cũ.

## 6. Ví dụ tích hợp affordance trong Spring HATEOAS

Giả sử controller có endpoint GET collection và POST tạo đơn hàng:

```java
@RestController
@RequestMapping("/orders")
class OrderController {

    @GetMapping
    CollectionModel<EntityModel<OrderView>> all() {
        CollectionModel<EntityModel<OrderView>> model =
                assembler.toCollectionModel(orderService.findAll());

        Link collection = linkTo(methodOn(OrderController.class).all())
                .withSelfRel()
                .andAffordance(afford(
                        methodOn(OrderController.class).create(null)
                ));

        model.add(collection);
        return model;
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    EntityModel<OrderView> create(@Valid @RequestBody CreateOrderInput input) {
        return assembler.toModel(orderService.create(input));
    }
}
```

Affordance tham chiếu method `create(...)`, nên Spring HATEOAS có thể suy ra POST, request body `CreateOrderInput` và content type từ mapping `consumes`. Cấu hình HAL-FORMS cho phép serializer công bố template trong `_templates` khi client yêu cầu media type tương ứng.

Đây là ví dụ minh họa. Ứng dụng cần khai báo đầy đủ assembler, service, DTO và cấu hình hypermedia phù hợp. `null` trong lời gọi `methodOn(...).create(null)` chỉ là placeholder để phân tích chữ ký method, không phải request body được gửi.

## 7. Khi nào HAL thông thường đã đủ?

HAL thông thường thường là lựa chọn đủ dùng khi client chỉ cần điều hướng giữa các tài nguyên và không cần server mô tả cấu trúc form.

Ví dụ:

- API chỉ cung cấp các thao tác đọc và link `self`, `next`, `prev`.
- Client đã biết trước payload và quy trình cập nhật, chỉ cần URI từ server.
- Các thao tác không nhận body và link relation đã đủ để client lựa chọn bước tiếp theo theo hợp đồng đã biết.
- API có một client cố định, được phát hành cùng chu kỳ và dùng schema request được quản lý riêng.

Trong các trường hợp này, HAL-FORMS có thể thêm `_templates` mà client không sử dụng. Hãy ưu tiên media type đơn giản đáp ứng nhu cầu thực tế, đồng thời vẫn giữ relation và URI rõ ràng.

## 8. Khi nào OpenAPI hoặc JSON Schema phù hợp hơn?

HAL-FORMS mô tả thao tác trong ngữ cảnh hypermedia và một tập metadata đầu vào hữu ích. Nó không phải ngôn ngữ schema tổng quát để diễn đạt mọi cấu trúc dữ liệu và mọi ràng buộc nghiệp vụ.

OpenAPI hoặc JSON Schema có thể phù hợp hơn khi nhóm cần:

- Mô tả đầy đủ hợp đồng API cho nhiều nhóm client.
- Sinh SDK, tài liệu endpoint hoặc contract test.
- Khai báo schema lồng nhau, union/discriminator, cấu trúc phức tạp và ràng buộc nâng cao.
- Quản lý phiên bản API và quy trình review hợp đồng tập trung.
- Mô tả bảo mật, response lỗi, tham số và các mã trạng thái một cách chi tiết.

Hai hướng không nhất thiết loại trừ nhau. OpenAPI có thể mô tả hợp đồng tổng thể; HAL-FORMS có thể cung cấp affordance động trong response để client hypermedia biết thao tác nào hiện có và cách gửi payload cơ bản.

## 9. Khi nào HAL-FORMS không phải lựa chọn phù hợp?

Hãy cân nhắc định dạng khác hoặc một cơ chế bổ sung khi:

- Payload có cấu trúc lồng nhau sâu, nhiều nhánh điều kiện hoặc kiểu dữ liệu không được metadata HAL-FORMS mô tả đầy đủ.
- Quy trình cần nhiều bước tương tác phức tạp, state machine lớn hoặc tương tác thời gian thực.
- Client cần schema chi tiết để sinh mã hoặc validate toàn bộ payload trước khi gửi.
- API chủ yếu truyền file lớn, stream hoặc dữ liệu nhị phân mà form property thông thường không mô tả được đầy đủ.
- Không có client nào sử dụng template và việc duy trì metadata làm tăng công sức triển khai, kiểm thử.
- Các client cần hỗ trợ media type không hiểu HAL-FORMS và không có cơ chế fallback.

Đây không phải danh sách cấm tuyệt đối. Một API có thể dùng HAL-FORMS cho các thao tác CRUD đơn giản và dùng endpoint hoặc hợp đồng riêng cho upload, workflow phức tạp hoặc schema chuyên biệt.

## 10. Bảng quyết định nhanh

| Nhu cầu | Lựa chọn nên xem xét | Lý do |
| --- | --- | --- |
| Chỉ cần link điều hướng tài nguyên | HAL | `_links` và `_embedded` đáp ứng nhu cầu. |
| Client cần khám phá thao tác và dựng form lúc chạy | HAL-FORMS | `_templates` mô tả method, target và input properties. |
| Hành động xuất hiện theo trạng thái tài nguyên | HAL-FORMS affordance hoặc link HAL có điều kiện | Server công bố khả năng hiện tại. |
| Client cố định, payload đã biết và không dùng template | HAL hoặc hợp đồng hiện có | Tránh metadata không được tiêu thụ. |
| Cần schema phức tạp, SDK và tài liệu hợp đồng đầy đủ | OpenAPI/JSON Schema, có thể kết hợp HAL-FORMS | Phạm vi mô tả schema rộng hơn. |
| Quy trình nhiều bước hoặc tương tác chuyên biệt | HAL-FORMS kết hợp API workflow hoặc media type riêng | Không ép mọi logic vào một form template. |

## 11. Chi phí khi đưa HAL-FORMS vào API

HAL-FORMS có lợi ích nhưng cũng tạo thêm trách nhiệm cho server và client.

**Phía server:** cần tạo affordance đúng, thiết kế input DTO, giữ metadata đồng bộ với validation, cấu hình media type và kiểm thử template sau serialization. Nếu hành động phụ thuộc trạng thái hoặc quyền, logic công bố affordance cần nhất quán với quy tắc nghiệp vụ.

**Phía client:** cần parse `_templates`, hiểu method, target, content type và property metadata; cần xử lý template thiếu field, field không biết hoặc metadata mới. Client cũng phải xử lý lỗi server vì metadata không thể thay thế validation thực tế.

**Vận hành:** nếu cùng URI trả representation khác nhau theo `Accept`, cache và proxy phải xử lý content negotiation đúng. Khi response có biến thể theo media type, cần bảo đảm header cache phù hợp, thường là `Vary: Accept` theo cấu hình HTTP của ứng dụng.

Chi phí này hợp lý khi client thực sự tận dụng khả năng khám phá thao tác. Nếu không có client tiêu thụ template, lợi ích thực tế có thể thấp.

## 12. Triển khai từng bước thay vì chuyển đổi toàn bộ API

Có thể áp dụng HAL-FORMS cho một nhóm thao tác trước:

1. Chọn một collection có thao tác tạo mới đơn giản.
2. Tách input DTO khỏi entity và output representation.
3. Gắn affordance tới controller method nhận `@RequestBody`.
4. Bật HAL-FORMS và kiểm tra response `_templates`.
5. Xây một client thử nghiệm đọc template và gửi request.
6. Đo xem client có giảm được cấu hình endpoint/payload cố định hay không.
7. Mở rộng sang thao tác cập nhật hoặc hành động phụ thuộc trạng thái nếu có giá trị.

Giữ HAL hoặc các media type hiện có cho client không hỗ trợ HAL-FORMS. Việc bổ sung media type cần được kiểm tra content negotiation và không làm thay đổi ngoài ý muốn response mà client cũ đang tiêu thụ.

## 13. Kiểm thử xem HAL-FORMS có mang lại giá trị thực tế

Không chỉ kiểm tra `_templates` có xuất hiện. Hãy kiểm tra cả việc client có thể sử dụng template để tạo request đúng.

Với MockMvc, xác nhận response theo media type:

```java
mockMvc.perform(get("/orders")
        .accept(MediaTypes.HAL_FORMS_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_FORMS_JSON))
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._templates").exists());
```

Sau đó, kiểm thử client traversal:

1. Parse response HAL-FORMS.
2. Chọn template `createOrder` theo tên đã công bố.
3. Lấy target, method, content type và property.
4. Tạo payload hợp lệ từ property.
5. Gửi request tới target.
6. Xác nhận response thành công và representation mới có link phù hợp.

Thêm các trường hợp template không được công bố khi thao tác không khả dụng, payload sai validation, người dùng thiếu quyền và client yêu cầu HAL JSON thay vì HAL-FORMS. Những test này xác nhận cả hành vi hypermedia lẫn fallback cho client khác nhau.

## 14. Những lỗi thường gặp khi quyết định dùng HAL-FORMS

**Dùng HAL-FORMS chỉ vì dự án đã có Spring HATEOAS.** Hãy xác định client cần metadata thao tác hay chỉ cần link.

**Công bố template nhưng client không sử dụng.** Nếu client vẫn hard-code URL và payload, chi phí metadata không tạo ra lợi ích khám phá.

**Kỳ vọng HAL-FORMS thay thế schema đầy đủ.** Template chỉ mô tả tập thông tin được media type hỗ trợ; schema phức tạp có thể cần OpenAPI hoặc JSON Schema.

**Xem metadata là bảo mật hoặc validation.** Server vẫn phải xác thực, phân quyền và kiểm tra payload khi request đến.

**Không hỗ trợ fallback media type.** Client không hiểu HAL-FORMS cần có representation phù hợp khác hoặc hợp đồng được thống nhất.

**Không tính tới cache.** Cùng URI có thể trả HAL hoặc HAL-FORMS tùy `Accept`; cache cần phân biệt biến thể response.

**Đưa mọi thao tác vào một template.** Mỗi affordance nên mô tả một thao tác rõ ràng, với input và semantics phù hợp.

## 15. Bài tập thực hành và tiêu chí hoàn thành

Hãy đánh giá và triển khai HAL-FORMS cho API quản lý đơn hàng:

1. Xác định client nào cần dựng form từ metadata và client nào đã biết sẵn payload.
2. Chọn thao tác tạo đơn hàng có input DTO đơn giản.
3. Gắn affordance POST vào link collection và công bố template HAL-FORMS.
4. Tạo một client thử nghiệm đọc template thay vì ghép URL và payload cố định.
5. Thêm affordance `cancel` chỉ khi trạng thái đơn hàng cho phép.
6. Kiểm tra endpoint vẫn xác thực, phân quyền và kiểm tra trạng thái khi request thực tế đến.
7. So sánh response HAL JSON với HAL-FORMS cho cùng tài nguyên.
8. Đánh giá một thao tác có payload phức tạp và quyết định có cần OpenAPI/JSON Schema hoặc endpoint riêng hay không.
9. Kiểm thử `Accept`, `Content-Type`, cache variation và fallback cho client không hỗ trợ HAL-FORMS.
10. Ghi lại lý do chọn HAL-FORMS cho từng nhóm thao tác, dựa trên nhu cầu client và chi phí duy trì.

Bạn đã biết khi nào dùng HAL-FORMS khi có thể xác định nhu cầu khám phá thao tác của client, nhận diện payload có thể mô tả bằng template, công bố affordance theo trạng thái, phân biệt trường hợp HAL thông thường đã đủ và biết lúc nào cần schema hoặc media type bổ sung. Mục tiêu là chọn HAL-FORMS ở nơi metadata tương tác giúp client thực sự thích nghi, đồng thời giữ hợp đồng API rõ ràng và có thể tiến hóa.
# Khi nào dùng HAL-FORMS

HAL-FORMS phù hợp khi API cần mô tả các thao tác mà client có thể thực hiện ngay trong representation, đặc biệt là thao tác có dữ liệu đầu vào như tạo, cập nhật hoặc tìm kiếm tài nguyên. Thay vì để client tự biết endpoint nào nhận POST, endpoint nào nhận PUT và body cần những trường nào, server công bố các mẫu thao tác (form templates) cùng metadata của từng trường.

Spring HATEOAS xây dựng template từ affordance gắn với link và metadata của kiểu input. Client hiểu HAL-FORMS có thể đọc template, tạo giao diện nhập liệu hoặc chuẩn bị request theo thông tin server công bố. Lợi ích này rõ nhất khi xây dựng client tổng quát, giao diện thay đổi theo trạng thái nghiệp vụ hoặc nhiều client cần khám phá khả năng của cùng một API.

HAL-FORMS cũng tạo thêm chi phí: client phải hiểu media type, server cần duy trì metadata và kiểm thử hợp đồng template. Nếu API chỉ đọc hoặc client đã có biểu mẫu cố định theo một hợp đồng riêng, HAL với link thông thường có thể đủ. Bài học này giúp quyết định khi nào nên dùng HAL-FORMS, cách bật nó trong Spring HATEOAS, cách tạo affordance và cách kiểm thử template.

Sau bài học, bạn có thể:

- Giải thích HAL-FORMS và mối quan hệ của nó với HAL.
- Nhận diện trường hợp cần mô tả thao tác và form field tại runtime.
- So sánh HAL, HAL-FORMS và tài liệu hợp đồng như OpenAPI.
- Kích hoạt HAL-FORMS bằng `@EnableHypermediaSupport`.
- Gắn affordance vào link của controller để tạo template.
- Thiết kế input model với validation metadata phù hợp.
- Dùng `Accept` để yêu cầu representation HAL-FORMS.
- Nhận diện giới hạn về client, bảo mật, caching và độ phức tạp giao diện.
- Kiểm thử `_templates`, HTTP method, target và properties bằng MockMvc.

## 1. HAL-FORMS giải quyết vấn đề nào?

HAL cung cấp cách thống nhất để biểu diễn tài nguyên, link và embedded resource. Ví dụ một khách hàng có thể được trả về như sau:

~~~json
{
  "id": "42",
  "name": "Nguyễn An",
  "_links": {
    "self": {
      "href": "/customers/42"
    },
    "customers": {
      "href": "/customers"
    }
  }
}
~~~

Client có thể theo link `self` để đọc khách hàng hoặc theo link `customers` để quay về collection. Tuy nhiên, chỉ từ các link này client chưa biết tài nguyên có hỗ trợ PUT hay không, collection có hỗ trợ POST hay không, request cần những trường nào, trường nào bắt buộc và giá trị nhập cần theo định dạng nào.

Client viết theo kiểu cố định thường giải quyết bằng cách hard-code endpoint, HTTP method và cấu trúc request. Khi hợp đồng thay đổi, client phải được cập nhật tương ứng.

HAL-FORMS bổ sung phần mô tả form vào representation HAL thông qua thuộc tính `_templates`. Template cho biết thao tác có thể gửi, target, HTTP method, content type và các properties mà client cần gửi.

Ví dụ rút gọn:

~~~json
{
  "_links": {
    "self": {
      "href": "/customers"
    }
  },
  "_templates": {
    "default": {
      "method": "post",
      "contentType": "application/json",
      "properties": [
        {
          "name": "name",
          "required": true,
          "type": "text"
        },
        {
          "name": "email",
          "required": true,
          "type": "email"
        }
      ]
    }
  }
}
~~~

Client hiểu HAL-FORMS có thể đọc template để tạo biểu mẫu nhập tên và email, sau đó gửi request bằng POST đến URI của collection.

HAL-FORMS không phải HTML form được server dựng sẵn. Đây là media type hypermedia mô tả template thao tác để client diễn giải.

## 2. HAL và HAL-FORMS khác nhau như thế nào?

HAL và HAL-FORMS có liên quan nhưng không phải hai định dạng có thể thay thế lẫn nhau một cách tùy ý.

| Khía cạnh | HAL (application/hal+json) | HAL-FORMS (application/prs.hal-forms+json) |
|---|---|---|
| Dữ liệu tài nguyên | Có | Có |
| Link và relation | Có | Có |
| Embedded resource | Có | Có |
| Mô tả thao tác | Chủ yếu qua link | Qua affordance và `_templates` |
| HTTP method của form | Không có template chuẩn | Có |
| Request properties | Không mô tả thành form template | Có |
| Required, type, prompt, options | Không có cấu trúc form chuẩn | Có metadata cho property |
| Client cần hỗ trợ | Client HAL | Client HAL-FORMS |

HAL phù hợp khi client chỉ cần điều hướng giữa các tài nguyên. HAL-FORMS hữu ích khi client cần khám phá thao tác và chuẩn bị request dựa trên metadata server công bố.

HAL-FORMS được thiết kế để bổ sung hỗ trợ form runtime cho HAL. Dù có cấu trúc gần HAL, hai media type vẫn có định dạng và hợp đồng riêng. Client yêu cầu HAL không nên giả định response luôn chứa `_templates`; client yêu cầu HAL-FORMS phải biết cách diễn giải template.

## 3. Khi nào nên dùng HAL-FORMS?

### 3.1. Client cần khám phá thao tác tại runtime

Một API có thể cho phép tạo khách hàng, cập nhật thông tin hoặc thay đổi trạng thái tùy thuộc trạng thái hiện tại của tài nguyên. Client cần biết thao tác nào đang khả dụng và gửi request đến đâu.

Ví dụ:

- Đơn hàng ở trạng thái `DRAFT` có thể cho phép cập nhật.
- Đơn hàng ở trạng thái `SUBMITTED` có thể cho phép xác nhận hoặc hủy.
- Hồ sơ chưa hoàn tất có thể cung cấp template bổ sung thông tin.
- Collection cho phép tạo tài nguyên mới bằng POST.

Server có thể công bố affordance tương ứng với thao tác khả dụng. Client không cần suy ra tất cả hành động chỉ từ tên trạng thái nghiệp vụ. Điều này hữu ích cho giao diện quản trị, client tổng quát hoặc ứng dụng có workflow thay đổi theo dữ liệu.

### 3.2. Nhiều client cần dùng chung mô tả form

Giả sử cùng một API được sử dụng bởi giao diện web nội bộ, ứng dụng desktop, công cụ quản trị tổng quát và một client tự động tích hợp với API.

Nếu mỗi client tự duy trì danh sách endpoint, method và request field, thông tin dễ bị lệch nhau. HAL-FORMS cho phép server công bố metadata form ngay trong representation. Các client tương thích có thể dùng cùng một nguồn mô tả.

Điều này không loại bỏ hoàn toàn việc phát triển client. Mỗi client vẫn cần biết cách hiển thị field, xử lý lỗi, xác thực người dùng và gửi HTTP request.

### 3.3. Form có metadata thay đổi theo model

Một số form cần mô tả trường bắt buộc, độ dài tối thiểu hoặc tối đa, giá trị nhỏ nhất hoặc lớn nhất, biểu thức chính quy, kiểu input, placeholder và danh sách lựa chọn.

Spring HATEOAS có thể lấy một phần metadata từ kiểu input và annotation validation. Khi mô hình input thay đổi, server có thể cập nhật template theo metadata mới. Ví dụ form đăng ký khách hàng có thể yêu cầu email hợp lệ, tên không để trống và ngày sinh theo kiểu date.

### 3.4. Lựa chọn của form phụ thuộc dữ liệu khác

Một trường như phương thức giao hàng có thể có danh sách lựa chọn thay đổi theo khu vực hoặc loại đơn hàng. HAL-FORMS hỗ trợ metadata `options`, có thể mô tả lựa chọn inline hoặc tham chiếu đến nguồn lựa chọn từ xa.

Cách này hữu ích khi client cần hiển thị lựa chọn mà không tự duy trì danh sách cố định. Logic quyết định lựa chọn hợp lệ vẫn phải được kiểm tra ở server khi request được gửi.

### 3.5. API có thể tiến hóa mà client ít phụ thuộc vào cấu trúc cố định

Nếu client đọc template và dùng link do server cung cấp, server có thể thay đổi URI, thêm thao tác hoặc điều chỉnh một số metadata mà không buộc client hard-code lại từng endpoint.

Tuy vậy, đây không phải bảo đảm rằng mọi thay đổi đều tương thích ngược. Đổi tên property, thay đổi ý nghĩa field, kiểu dữ liệu hoặc relation mà client đang dùng vẫn có thể phá hợp đồng. Cần quản lý version và kiểm thử tương thích như với mọi API công khai khác.

## 4. Khi nào HAL-FORMS không cần thiết?

### 4.1. API chỉ phục vụ đọc dữ liệu

Nếu API chỉ cung cấp GET, tìm kiếm và điều hướng đến tài nguyên, link HAL thường đã đáp ứng nhu cầu. Không có thao tác gửi form thì `_templates` có thể không đem lại lợi ích đáng kể.

Ví dụ API công khai chỉ cung cấp danh sách địa điểm, chi tiết địa điểm và liên kết đến bản đồ. HAL là lựa chọn nhẹ hơn nếu client chỉ cần khám phá tài nguyên.

### 4.2. Client có giao diện cố định và hợp đồng được quản lý riêng

Một ứng dụng nội bộ có thể đã được phát triển cùng server, sử dụng DTO request/response và tài liệu OpenAPI được quản lý trong cùng quy trình phát hành. Nếu form và workflow cố định, client không có nhu cầu đọc metadata runtime, HAL-FORMS có thể làm tăng độ phức tạp mà không tạo lợi ích tương xứng.

Trong trường hợp đó, OpenAPI hoặc JSON Schema có thể là nguồn mô tả hợp đồng phù hợp hơn. Có thể tiếp tục dùng HAL để điều hướng tài nguyên nếu cần.

### 4.3. Client không hỗ trợ HAL-FORMS

Một client chỉ hiểu JSON thông thường hoặc HAL sẽ không tự động hiểu `_templates`. Nếu client không thể diễn giải template và gửi HTTP method tương ứng, việc bật HAL-FORMS không giúp client sử dụng form.

Trước khi chọn media type, hãy xác nhận các client quan trọng có khả năng đọc template, xử lý properties và gửi request theo method mà template mô tả.

### 4.4. Form quá phức tạp hoặc phụ thuộc mạnh vào giao diện

HAL-FORMS mô tả thao tác và metadata của field, nhưng không phải hệ thống thiết kế giao diện đầy đủ. Nó không thay thế framework frontend cho bố cục nhiều cột hoặc nhiều tab, wizard nhiều bước, logic hiển thị phụ thuộc nhiều field, tương tác kéo thả, upload nhiều tệp hoặc trình soạn thảo đặc biệt.

Nếu ứng dụng cần trải nghiệm giao diện giàu tương tác, có thể dùng HAL-FORMS cho thao tác cơ bản và dùng client riêng để triển khai phần giao diện nâng cao.

### 4.5. API không cần mô tả thao tác dưới dạng form

Một số thao tác dùng binary upload, stream, event hoặc giao thức riêng. Không nên cố biểu diễn chúng như form JSON chỉ để thống nhất định dạng. Hãy chọn giao thức và media type phù hợp với bản chất thao tác.

## 5. Bảng quyết định nhanh

| Tình huống | Lựa chọn phù hợp | Lý do |
|---|---|---|
| Chỉ đọc và điều hướng tài nguyên | HAL | Link và embedded resource là đủ |
| Client cần khám phá POST/PUT/PATCH và field runtime | HAL-FORMS | Template mô tả method và input properties |
| Nhiều client tổng quát dùng chung metadata form | HAL-FORMS | Server công bố mô tả thao tác trong response |
| Giao diện cố định, schema được quản lý cùng client | HAL và OpenAPI/JSON Schema | Ít cần form metadata runtime |
| Form có nhiều tương tác giao diện riêng | Client UI riêng, có thể kết hợp HAL-FORMS | Template không mô tả đầy đủ bố cục và hành vi UI |
| Client không hỗ trợ HAL-FORMS | HAL hoặc media type client hỗ trợ | Tránh gửi representation mà client không hiểu |
| API có nhiều thao tác phụ thuộc trạng thái tài nguyên | HAL-FORMS nếu client dùng affordance | Server có thể công bố thao tác khả dụng |

Có thể dùng HAL và HAL-FORMS song song. Client chọn representation bằng header `Accept` phù hợp với khả năng của nó.

## 6. Bật HAL-FORMS trong Spring HATEOAS

Với Spring MVC, bật hỗ trợ HAL-FORMS bằng `@EnableHypermediaSupport`:

~~~java
@Configuration
@EnableHypermediaSupport(
    type = EnableHypermediaSupport.HypermediaType.HAL_FORMS
)
public class HypermediaConfiguration {
}
~~~

Các import:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.config.EnableHypermediaSupport;
~~~

Ứng dụng Spring Boot có thể đã có cấu hình hypermedia riêng. Hãy kiểm tra cách ứng dụng đăng ký media type để tránh cấu hình lặp.

Khi client gửi:

~~~http
Accept: application/prs.hal-forms+json
~~~

Spring HATEOAS có thể serialize representation cùng affordance thành HAL-FORMS, bao gồm `_templates` nếu có template được đăng ký.

Nếu client gửi:

~~~http
Accept: application/hal+json
~~~

server trả representation HAL thông thường theo cấu hình content negotiation. Hai media type có thể chia sẻ dữ liệu tài nguyên và link, nhưng HAL-FORMS có thêm phần template.

## 7. Tạo affordance để server công bố form

HAL-FORMS không tự suy ra form chỉ từ một DTO. Spring HATEOAS cần biết thao tác nào có thể được thực hiện. Cách phổ biến là gắn affordance vào link được trả về từ endpoint đọc tài nguyên.

Ví dụ collection khách hàng:

~~~java
@RestController
@RequestMapping("/customers")
public class CustomerController {

    private final CustomerService service;
    private final CustomerModelAssembler assembler;

    public CustomerController(
            CustomerService service,
            CustomerModelAssembler assembler) {
        this.service = service;
        this.assembler = assembler;
    }

    @GetMapping
    public CollectionModel<EntityModel<CustomerRepresentation>> all() {

        var customers = service.findAll().stream()
            .map(assembler::toModel)
            .toList();

        Link self = linkTo(methodOn(CustomerController.class).all())
            .withSelfRel()
            .andAffordance(
                afford(methodOn(CustomerController.class).create(null))
            );

        return CollectionModel.of(customers, self);
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public EntityModel<CustomerRepresentation> create(
            @Valid @RequestBody CreateCustomerRequest request) {

        return assembler.toModel(service.create(request));
    }
}
~~~

Ở đây:

- `GET /customers` trả về collection và link self.
- `andAffordance(...)` gắn thao tác tạo khách hàng vào link collection.
- `create(...)` được ánh xạ bằng POST.
- `@RequestBody CreateCustomerRequest` cung cấp kiểu input để Spring HATEOAS đọc metadata.
- `consumes` cho biết media type của request body.
- `@Valid` kích hoạt kiểm tra validation khi server nhận request.

Lời gọi `methodOn(...).create(null)` dùng proxy để tham chiếu mapping của controller. Nó không gọi logic tạo khách hàng.

Các import chính:

~~~java
import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import jakarta.validation.Valid;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;
~~~

`CustomerModelAssembler`, `CustomerService` và các kiểu domain/representation là thành phần của ứng dụng. Ví dụ tập trung vào việc công bố thao tác tạo khách hàng từ collection resource.

### 7.1. Dùng input model riêng cho form

Request model nên thể hiện các trường client được phép gửi:

~~~java
public record CreateCustomerRequest(
    @NotBlank
    @Size(min = 2, max = 80)
    String name,

    @NotBlank
    @Email
    String email,

    @NotNull
    LocalDate birthdate
) {}
~~~

Các import:

~~~java
import java.time.LocalDate;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
~~~

Spring HATEOAS có thể dùng kiểu input và metadata thuộc tính để xây dựng template. Ví dụ:

- `@NotBlank` và `@NotNull` giúp mô tả trường bắt buộc.
- `@Size` có thể cung cấp giới hạn độ dài.
- `@Email` giúp xác định kiểu field email.
- `LocalDate` có thể được chuyển thành kiểu date phù hợp.

Metadata form giúp client trình bày và chuẩn bị dữ liệu. Server vẫn phải thực hiện validation và kiểm tra nghiệp vụ khi nhận request.

### 7.2. Response HAL-FORMS minh họa

Khi client yêu cầu HAL-FORMS, response collection có thể chứa template như sau:

~~~json
{
  "_links": {
    "self": {
      "href": "/customers"
    }
  },
  "_embedded": {
    "customers": [
      {
        "id": "42",
        "name": "Nguyễn An",
        "_links": {
          "self": {
            "href": "/customers/42"
          }
        }
      }
    ]
  },
  "_templates": {
    "default": {
      "method": "post",
      "contentType": "application/json",
      "properties": [
        {
          "name": "name",
          "required": true,
          "type": "text",
          "minLength": 2,
          "maxLength": 80
        },
        {
          "name": "email",
          "required": true,
          "type": "email"
        },
        {
          "name": "birthdate",
          "required": true,
          "type": "date"
        }
      ]
    }
  }
}
~~~

Đây là ví dụ minh họa cấu trúc. Các trường và giá trị metadata thực tế phụ thuộc input model, annotation, cấu hình và phiên bản thư viện.

Nếu chỉ có một template, tên template thường là `default`. Khi có nhiều affordance, template có thể được đặt tên theo thao tác hoặc tên affordance đã khai báo.

## 8. Metadata nào làm HAL-FORMS hữu ích?

Template mô tả thao tác có các thuộc tính như:

| Thuộc tính | Ý nghĩa |
|---|---|
| `method` | HTTP method để gửi form |
| `target` | URI nhận request nếu khác target link đang mang affordance |
| `contentType` | Media type của request body |
| `title` | Tên hiển thị của template |
| `properties` | Các trường client cần gửi |

Mỗi property có thể chứa metadata như:

| Metadata | Ý nghĩa |
|---|---|
| `name` | Tên trường trong request |
| `required` | Trường bắt buộc |
| `readOnly` | Trường chỉ đọc |
| `type` | Kiểu input như text, email hoặc date |
| `min`, `max` | Giới hạn giá trị |
| `minLength`, `maxLength` | Giới hạn độ dài |
| `regex` | Mẫu kiểm tra định dạng |
| `prompt` | Nhãn hoặc hướng dẫn cho người dùng |
| `placeholder` | Ví dụ định dạng đầu vào |
| `options` | Danh sách lựa chọn |

Không phải mọi metadata đều xuất hiện trong mọi template. Spring HATEOAS lấy một phần từ kiểu Java, annotation và cấu hình HAL-FORMS. Các giá trị mặc định theo đặc tả có thể được lược bỏ.

### 8.1. Options cho trường lựa chọn

Với trường có tập giá trị hợp lệ, HAL-FORMS hỗ trợ `options`. Spring HATEOAS cho phép cấu hình lựa chọn thông qua `HalFormsConfiguration`.

Ví dụ:

~~~java
@Configuration
public class HalFormsOptionsConfiguration {

    @Bean
    HalFormsConfiguration halFormsConfiguration() {

        HalFormsConfiguration configuration =
            new HalFormsConfiguration();

        configuration.withOptions(
            OrderRequest.class,
            "shippingMethod",
            metadata -> HalFormsOptions.inline("STANDARD", "EXPRESS")
        );

        return configuration;
    }
}
~~~

Các import:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.mediatype.hal.forms.HalFormsConfiguration;
import org.springframework.hateoas.mediatype.hal.forms.HalFormsOptions;
~~~

Ví dụ dùng lựa chọn inline. Với tập lựa chọn thay đổi theo dữ liệu, HAL-FORMS cũng hỗ trợ options tham chiếu đến nguồn từ xa. Hãy chọn nguồn dữ liệu và chính sách cache phù hợp với nghiệp vụ.

### 8.2. Prompt, placeholder và ngôn ngữ

HAL-FORMS có các thuộc tính hướng đến người dùng như title, prompt và placeholder. Spring HATEOAS hỗ trợ resource bundle `rest-messages` để định nghĩa và quốc tế hóa chúng.

Ví dụ các key cho prompt và placeholder:

~~~properties
CustomerRepresentation.email._prompt=Email address
CustomerRepresentation.email._placeholder=name@example.com
~~~

Có thể định nghĩa title của template theo tên affordance. Nếu client gửi `Accept-Language`, server có thể chọn thông điệp phù hợp với locale đã cấu hình.

Prompt và placeholder giúp client tạo giao diện dễ hiểu hơn, nhưng không thay thế tài liệu hướng dẫn nghiệp vụ hoặc thông báo validation chi tiết.

## 9. HAL-FORMS hoạt động qua content negotiation

Client lựa chọn representation bằng header `Accept`.

Ví dụ:

~~~http
GET /customers
Accept: application/prs.hal-forms+json
~~~

Server có thể trả representation HAL-FORMS có `_templates`.

Nếu client yêu cầu:

~~~http
GET /customers
Accept: application/hal+json
~~~

server trả HAL theo media type được yêu cầu.

Có thể kiểm tra bằng curl:

~~~bash
curl -H "Accept: application/prs.hal-forms+json" http://localhost:8080/customers
~~~

Và yêu cầu HAL:

~~~bash
curl -H "Accept: application/hal+json" http://localhost:8080/customers
~~~

Cần kiểm tra cấu hình message converter và hypermedia support của ứng dụng. Trong Spring HATEOAS, converter HAL-FORMS có thể chuyển về HAL JSON nếu representation không có template để công bố. Vì vậy, việc gửi `Accept` HAL-FORMS không đồng nghĩa mọi response luôn phải có `_templates`.

### 9.1. Client phải thực hiện được HTTP method trong template

HAL-FORMS mô tả HTTP method như POST, PUT, PATCH hoặc DELETE. HTML form thuần chỉ hỗ trợ GET và POST theo cơ chế native. Một client trình duyệt muốn gửi PUT hoặc PATCH thường cần JavaScript hoặc một lớp HTTP client thực hiện request.

Client HAL-FORMS cần:

1. Đọc template.
2. Chọn thao tác mà người dùng muốn thực hiện.
3. Tạo control phù hợp với từng property.
4. Thu thập và kiểm tra dữ liệu đầu vào.
5. Gửi request đến target với HTTP method và content type được mô tả.
6. Xử lý response và các link tiếp theo.

Server công bố mô tả thao tác; client chịu trách nhiệm triển khai trải nghiệm và gửi request.

## 10. HAL-FORMS so với OpenAPI và JSON Schema

HAL-FORMS và OpenAPI giải quyết các nhu cầu liên quan nhưng khác nhau.

| Tiêu chí | HAL-FORMS | OpenAPI / JSON Schema |
|---|---|---|
| Vị trí metadata | Trong representation runtime | Trong tài liệu hợp đồng |
| Khám phá thao tác | Gắn với link và affordance | Qua tài liệu API hoặc tooling |
| Form template | Có | Có thể sinh form bằng công cụ dựa trên schema, nhưng không phải mục tiêu hypermedia chính |
| URI và relation runtime | Có qua HAL | Không phải cơ chế điều hướng runtime chính |
| Tùy trạng thái tài nguyên | Có thể công bố affordance theo trạng thái | Tài liệu thường mô tả API tổng thể |
| Client cần hỗ trợ | HAL-FORMS | OpenAPI/JSON Schema tooling |

Hai cách tiếp cận có thể bổ sung nhau:

- OpenAPI mô tả hợp đồng API để phát triển, kiểm tra và tích hợp.
- HAL-FORMS mô tả các thao tác khả dụng trong ngữ cảnh representation runtime.
- HAL cung cấp link và embedded resource cho client điều hướng.

Không cần loại bỏ OpenAPI chỉ vì đã dùng HAL-FORMS. Tài liệu API tĩnh vẫn hữu ích cho nhà phát triển, trong khi template runtime giúp client khám phá thao tác theo tài nguyên hiện tại.

## 11. Những giới hạn cần cân nhắc

### 11.1. Metadata không thay thế validation phía server

Client có thể dùng `required`, `regex`, `minLength` hoặc `max` để kiểm tra sơ bộ. Nhưng request vẫn có thể bị sửa thủ công hoặc gửi từ client không tuân thủ template.

Server phải xác thực dữ liệu, kiểm tra quyền và áp dụng quy tắc nghiệp vụ độc lập.

### 11.2. Affordance không phải cơ chế phân quyền

Server có thể chỉ công bố affordance cập nhật khi người dùng có quyền phù hợp. Điều đó giúp giao diện tránh hiển thị thao tác không khả dụng.

Tuy nhiên, ẩn link hoặc template không ngăn được client gọi trực tiếp endpoint. Controller hoặc service vẫn phải xác thực quyền trên mỗi request.

### 11.3. Template không mô tả toàn bộ trải nghiệm UI

HAL-FORMS không quy định bố cục, màu sắc, thứ tự field theo nhóm, tương tác phức tạp hoặc mọi hành vi giao diện. Client có thể bổ sung quy tắc hiển thị riêng dựa trên metadata.

### 11.4. Cần quản lý khả năng tương thích client

Khi đổi tên property hoặc relation, client có thể không còn tìm được field. Khi thay đổi HTTP method hoặc target, client có thể gửi request sai.

Hãy coi template là một phần hợp đồng API công khai. Kiểm thử các template quan trọng và quản lý thay đổi tương thích như với response body.

### 11.5. Cache phải tính đến media type và locale

Cùng một URI có thể trả HAL hoặc HAL-FORMS tùy header `Accept`. Nếu title và prompt được quốc tế hóa, response còn phụ thuộc `Accept-Language`.

Vì vậy, khi dùng cache dùng chung, cần bảo đảm cache key hoặc chính sách `Vary` phân biệt các biến thể representation tương ứng. Nếu không, client có thể nhận nhầm HAL thay vì HAL-FORMS hoặc nhận prompt của ngôn ngữ khác.

## 12. Kiểm thử HAL-FORMS bằng MockMvc

Một kiểm thử nên xác nhận response thực sự chứa template và metadata cần thiết.

~~~java
@WebMvcTest(CustomerController.class)
@Import({
    CustomerModelAssembler.class,
    HypermediaConfiguration.class
})
class CustomerControllerTest {

    @Autowired
    MockMvc mvc;

    @MockBean
    CustomerService service;

    @Test
    void exposesCreateCustomerTemplate() throws Exception {

        given(service.findAll()).willReturn(List.of());

        mvc.perform(get("/customers")
                .accept(MediaTypes.HAL_FORMS_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaTypes.HAL_FORMS_JSON
            ))
            .andExpect(jsonPath("$._links.self.href")
                .value(endsWith("/customers")))
            .andExpect(jsonPath("$._templates.default.method")
                .value("post"))
            .andExpect(jsonPath("$._templates.default.contentType")
                .value("application/json"));
    }
}
~~~

Ví dụ giả định controller và assembler đã được cấu hình như phần 7. Tùy phiên bản Spring Boot, cách mock bean có thể dùng `@MockitoBean` thay cho `@MockBean`.

Các import thường dùng:

~~~java
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.endsWith;
import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
~~~

Nếu cần kiểm tra metadata của từng property, có thể đọc response JSON và tìm phần tử theo trường `name` thay vì phụ thuộc thứ tự phần tử trong mảng.

### 12.1. Kiểm thử representation HAL

Cũng nên xác nhận client yêu cầu HAL nhận response không có template HAL-FORMS:

~~~java
mvc.perform(get("/customers")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._templates").doesNotExist());
~~~

Kiểm thử này bảo vệ content negotiation và giúp phát hiện việc vô tình trả sai media type.

### 12.2. Kiểm thử request thật

Template mô tả request; nó không chứng minh endpoint xử lý request đúng. Cần có test riêng cho thao tác POST:

~~~java
mvc.perform(post("/customers")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaTypes.HAL_JSON)
        .content("""
            {
              "name": "Nguyễn An",
              "email": "an@example.com",
              "birthdate": "1995-04-12"
            }
            """))
    .andExpect(status().isCreated());
~~~

Kiểm thử request xác nhận endpoint thực thi đúng validation và nghiệp vụ. Kiểm thử template xác nhận metadata mô tả đúng thao tác. Hai loại kiểm thử bảo vệ hai phần khác nhau của hợp đồng.

## 13. Các lỗi thường gặp khi chọn HAL-FORMS

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng HAL-FORMS cho API chỉ đọc | Metadata template không tạo thêm giá trị | Dùng HAL nếu chỉ cần link |
| Giả định mọi client đều hiểu `_templates` | Client không biết cách gửi form | Kiểm tra khả năng hỗ trợ media type |
| Nghĩ HAL-FORMS tự dựng HTML | Không có giao diện thực tế | Xây client có khả năng diễn giải template |
| Dùng response DTO làm input model | Form có thể chứa trường không cho phép sửa | Dùng request DTO riêng |
| Coi required và regex là bảo mật | Request không hợp lệ vẫn có thể được gửi | Validate và kiểm tra quyền ở server |
| Công bố affordance cho mọi người dùng | Hiển thị thao tác không khả dụng | Tạo affordance theo trạng thái và quyền |
| Cho rằng template mô tả toàn bộ UI | Thiếu bố cục và hành vi đặc thù | Dùng logic giao diện phía client |
| Không kiểm thử Accept | Trả nhầm representation | Kiểm thử HAL và HAL-FORMS riêng |
| Đổi tên property không kiểm tra client | Client không còn điền đúng field | Quản lý template như hợp đồng công khai |
| Không phân biệt cache theo locale | Prompt hoặc title sai ngôn ngữ | Cấu hình cache theo header phù hợp |

## 14. Quy trình quyết định và triển khai

Khi đánh giá một API có nên dùng HAL-FORMS hay không, hãy đi theo trình tự:

1. Xác định client có cần khám phá thao tác tại runtime hay chỉ cần đọc link.
2. Xác nhận có thao tác nhận input payload như POST, PUT hoặc PATCH.
3. Kiểm tra client có khả năng hiểu `application/prs.hal-forms+json` và gửi method tương ứng.
4. Nếu cần form runtime, thiết kế request DTO riêng cho từng thao tác.
5. Thêm validation annotation và metadata cần thiết vào input model.
6. Gắn affordance vào link thích hợp trong representation.
7. Bật HAL-FORMS và kiểm tra content negotiation.
8. Bổ sung prompt, placeholder, options và bản dịch nếu có ích.
9. Kiểm tra quyền và validation tại server độc lập với metadata.
10. Kiểm thử template, request thực tế, HAL fallback và các client quan trọng.
11. Xem xét caching theo `Accept` và `Accept-Language`.
12. Theo dõi thay đổi template như thay đổi hợp đồng API.

## 15. Kết luận

HAL-FORMS phù hợp khi API cần công bố các thao tác có input và metadata của form tại runtime. Nó đặc biệt hữu ích cho client tổng quát, giao diện phụ thuộc trạng thái tài nguyên và hệ thống có nhiều client cần dùng chung mô tả thao tác. Spring HATEOAS kết hợp affordance của controller với metadata input để tạo `_templates`, bao gồm HTTP method, target, content type và properties.

Với API chỉ đọc, client có giao diện cố định hoặc client không hỗ trợ HAL-FORMS, HAL và tài liệu hợp đồng riêng có thể đáp ứng tốt hơn. HAL-FORMS cũng không thay thế frontend, validation hoặc phân quyền. Hãy chọn nó khi lợi ích khám phá thao tác và tạo form runtime đủ lớn, sau đó kiểm thử template cùng request thực tế để giữ hợp đồng API nhất quán.

## Tài liệu tham khảo

- [Spring HATEOAS Reference — HAL-FORMS](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.hal-forms): đặc điểm HAL-FORMS, cấu hình và template.
- [Spring HATEOAS Reference — Defining HAL-FORMS metadata](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.hal-forms.metadata): thuộc tính template, property metadata và options.
- [Spring HATEOAS Reference — Affordances](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.affordances): gắn affordance với link từ controller method.
- [HAL-FORMS specification](https://rwcbook.github.io/hal-forms/): cấu trúc media type và `_templates`.


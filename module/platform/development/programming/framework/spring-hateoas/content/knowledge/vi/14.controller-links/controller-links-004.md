# Link cho POST

Trong REST API, `POST` thường được dùng để tạo một tài nguyên mới trong collection hoặc gửi một lệnh làm thay đổi trạng thái nghiệp vụ. Khi client cần thực hiện thao tác đó, server có thể công bố một hypermedia link trỏ tới endpoint POST. Link giúp client khám phá điểm vào; **affordance** gắn với link có thể mô tả thêm phương thức HTTP và dữ liệu request mà thao tác yêu cầu.

Spring HATEOAS hỗ trợ tạo link từ mapping controller bằng `linkTo(...)` và `methodOn(...)`, sau đó gắn affordance bằng `andAffordance(...)`. Cách này giúp representation công bố khả năng tạo tài nguyên hoặc thực hiện một lệnh ngay tại thời điểm hành động khả dụng.

## Vì sao cần link cho POST?

Một client có thể biết URI `/orders` dùng để đọc collection, nhưng không nên phải tự đoán rằng gửi `POST` tới URI đó sẽ tạo đơn hàng. Server có thể công bố một link với relation mang ý nghĩa tạo đơn hàng, ví dụ `https://api.example.com/rels/create-order`.

Link thường chứa hai thông tin cơ bản:

- **Relation (`rel`):** ý nghĩa của link, chẳng hạn tạo đơn hàng hoặc gửi yêu cầu phê duyệt.
- **Href:** URI đích mà client sẽ gửi request.

Tuy nhiên, link thông thường chỉ chỉ ra đích và quan hệ. Nó không tự mô tả đầy đủ rằng client phải dùng `POST`, request body có trường nào, trường nào bắt buộc hoặc media type nào được chấp nhận. Khi client cần thông tin này, hãy gắn affordance với link và chọn định dạng hypermedia có thể biểu diễn affordance, ví dụ HAL-FORMS.

`POST` có thể dùng trong hai tình huống thường gặp:

| Tình huống | Ví dụ | Link có thể công bố |
| --- | --- | --- |
| Tạo phần tử mới trong collection | Tạo đơn hàng mới từ `/orders` | Relation tạo đơn hàng trên collection representation |
| Gửi lệnh hoặc tạo tài nguyên con | Yêu cầu hủy hoặc phê duyệt đơn hàng | Relation nghiệp vụ trên representation của đơn hàng |

Relation cho thao tác nghiệp vụ nên có ý nghĩa ổn định. Với API công khai, có thể dùng extension relation URI do tổ chức kiểm soát, chẳng hạn `https://api.example.com/rels/create-order`. Không nên buộc client suy ra hành động chỉ từ đường dẫn hoặc tên method trong controller.

## Tạo link POST bằng Spring HATEOAS

Giả sử controller có endpoint GET để liệt kê đơn hàng và endpoint POST để tạo đơn hàng. Có thể tạo link tới phương thức POST bằng `methodOn(...)`:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;

class OrderLinks {

    static final LinkRelation CREATE_ORDER =
        LinkRelation.of("https://api.example.com/rels/create-order");

    Link createOrder() {
        return linkTo(methodOn(OrderController.class).create(null))
            .withRel(CREATE_ORDER)
            .andAffordance(afford(
                methodOn(OrderController.class).create(null)));
    }
}
```

`create(null)` là lời gọi mô phỏng để Spring HATEOAS đọc mapping của phương thức. Nó không gọi nghiệp vụ tạo đơn hàng và không gửi request body. Tham số `null` được dùng ở đây vì URI của endpoint POST không phụ thuộc nội dung body; kiểu request body vẫn được khai báo trên chữ ký phương thức controller để framework có thể đọc metadata phù hợp.

`withRel(CREATE_ORDER)` gắn ý nghĩa tạo đơn hàng cho link. `andAffordance(afford(...))` gắn mô tả tương tác dựa trên mapping của phương thức POST. Nếu chỉ cần công bố điểm vào và client đã biết hợp đồng request từ một tài liệu khác, link thường có thể đủ; affordance hữu ích khi muốn client khám phá tương tác từ representation.

## Công bố link trên collection representation

Link tạo mới thường nằm trên representation của collection vì thao tác tạo một phần tử mới thuộc về collection đó. Ví dụ assembler có thể tạo `CollectionModel` như sau:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import java.util.List;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.stereotype.Component;

@Component
class OrderCollectionAssembler {

    CollectionModel<EntityModel<OrderRepresentation>> toModel(
            List<EntityModel<OrderRepresentation>> orders) {

        Link self = linkTo(methodOn(OrderController.class).all())
            .withSelfRel();

        Link create = linkTo(methodOn(OrderController.class).create(null))
            .withRel(OrderLinks.CREATE_ORDER)
            .andAffordance(afford(
                methodOn(OrderController.class).create(null)));

        return CollectionModel.of(orders, self, create);
    }
}
```

`OrderRepresentation` và `OrderController` là kiểu thuộc ứng dụng minh họa. Collection có link `self` để client truy cập lại danh sách và link `create-order` để khám phá thao tác tạo mới. Nếu người gọi không có quyền tạo đơn hàng hoặc hệ thống tạm thời không nhận đơn, server có thể không công bố affordance tạo mới trong representation hiện tại.

Không nên thêm link POST tạo đơn hàng vào từng `EntityModel<OrderRepresentation>` nếu thao tác thực chất tạo một phần tử mới trong collection. Nếu POST là thao tác trên một đơn hàng cụ thể, ví dụ gửi lệnh phê duyệt, relation đó phù hợp hơn khi đặt trên representation của chính đơn hàng.

## Controller xử lý POST và trả về tài nguyên mới

Endpoint POST nhận dữ liệu, gọi service để tạo tài nguyên rồi trả `201 Created`. Response nên có `Location` trỏ tới tài nguyên mới và representation có link `self`:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import java.net.URI;

import jakarta.validation.Valid;
import org.springframework.hateoas.EntityModel;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;

@PostMapping(consumes = "application/json", produces = "application/hal+json")
ResponseEntity<EntityModel<OrderRepresentation>> create(
        @Valid @RequestBody CreateOrderRequest request) {

    Order created = orderService.create(request);
    EntityModel<OrderRepresentation> body = assembler.toModel(created);

    URI location = linkTo(methodOn(OrderController.class)
        .one(created.getId())).toUri();

    return ResponseEntity.created(location).body(body);
}
```

Đoạn code giả định controller có `orderService`, `assembler` và endpoint `one(id)`; `CreateOrderRequest` là DTO đầu vào. `ResponseEntity.created(location)` tạo response `201 Created` và đặt header `Location`. Assembler gắn self link vào representation của tài nguyên mới. Với Spring Boot 3, validation API dùng namespace `jakarta.validation`; dự án Spring Boot 2 dùng namespace `javax.validation` tương ứng.

POST tạo tài nguyên thường trả `201 Created`. Nếu thao tác chỉ được tiếp nhận để xử lý bất đồng bộ và chưa có kết quả cuối cùng, `202 Accepted` có thể phù hợp hơn; response nên công bố link trạng thái công việc nếu client cần theo dõi tiến trình.

## Affordance mô tả method và request body

Affordance gắn metadata tương tác với một link. Với link tạo đơn hàng, affordance có thể cho biết thao tác dùng `POST` và cần một representation đầu vào có cấu trúc như:

```java
import java.util.List;

public record CreateOrderRequest(
    Long customerId,
    List<CreateOrderItem> items,
    String note
) {}

public record CreateOrderItem(
    Long productId,
    int quantity
) {}
```

Kiểu request body là một phần quan trọng của chữ ký controller. Khi Spring HATEOAS xây affordance, framework có thể sử dụng thông tin từ mapping, tham số, kiểu dữ liệu và metadata có sẵn để mô tả tương tác. Những chi tiết như trường bắt buộc, giới hạn hoặc mô tả nghiệp vụ có thể cần validation annotation, metadata bổ sung hoặc cấu hình riêng tùy media type.

Affordance không thay thế validation phía server. Dù client đọc được form và gửi đúng cấu trúc, server vẫn phải kiểm tra dữ liệu, quyền và các quy tắc nghiệp vụ khi nhận POST.

## HAL JSON và HAL-FORMS

HAL JSON là định dạng phổ biến để biểu diễn dữ liệu và link. Một link POST thông thường có thể xuất hiện dưới `_links`:

```json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/orders"
    },
    "https://api.example.com/rels/create-order": {
      "href": "https://api.example.com/orders"
    }
  }
}
```

Representation trên công bố điểm vào tạo đơn hàng. Tuy nhiên, chỉ từ `href` và relation, client không thể biết đầy đủ request body hoặc method nếu không có hợp đồng bổ sung.

HAL-FORMS mở rộng cách biểu diễn để mô tả form/template tương tác. Một response minh họa có thể có dạng:

```json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/orders"
    },
    "https://api.example.com/rels/create-order": {
      "href": "https://api.example.com/orders"
    }
  },
  "_templates": {
    "default": {
      "method": "POST",
      "contentType": "application/json",
      "properties": [
        {
          "name": "customerId",
          "type": "number",
          "required": true
        },
        {
          "name": "items",
          "type": "text",
          "required": true
        },
        {
          "name": "note",
          "type": "text",
          "required": false
        }
      ]
    }
  }
}
```

Đây là ví dụ minh họa rút gọn về cấu trúc HAL-FORMS; template name và các thuộc tính thực tế phụ thuộc affordance, cấu hình serializer và metadata mà ứng dụng cung cấp. Client đọc template để biết method, content type và các property được công bố, rồi gửi request tới `href` tương ứng. Khi cần kiểm tra hợp đồng thực tế, hãy xem response được Spring HATEOAS serialize thay vì giả định mọi DTO sẽ tự động sinh đầy đủ mọi ràng buộc giao diện.

Trong Spring HATEOAS, có thể yêu cầu HAL-FORMS bằng media type `application/prs.hal-forms+json` khi ứng dụng đã bật hỗ trợ hypermedia tương ứng. Với Spring Boot, kiểm tra dependency và auto-configuration của phiên bản đang dùng; với cấu hình thủ công, bật loại hypermedia HAL-FORMS phù hợp.

## Luồng client sử dụng POST link

Một client hypermedia có thể thực hiện quy trình sau:

1. Gửi GET tới entry point hoặc collection resource với `Accept` phù hợp, ví dụ `application/prs.hal-forms+json`.
2. Đọc `_links` và tìm relation tạo đơn hàng đã được API công bố.
3. Nếu representation có affordance/template, đọc method, content type và các trường đầu vào được mô tả.
4. Thu thập dữ liệu từ người dùng hoặc từ quy trình ứng dụng, kiểm tra các trường theo metadata đã nhận.
5. Gửi POST tới `href` với content type và body tương ứng.
6. Xử lý response, thường là `201 Created`, đọc `Location` và representation mới cùng self link.

Client không nên tự ghép `/orders` chỉ vì biết đây là collection. Nếu relation không xuất hiện, client có thể hiểu thao tác không được công bố trong trạng thái hoặc ngữ cảnh hiện tại. Khi link có mặt nhưng affordance không được hỗ trợ, client cần dùng hợp đồng tương thích đã biết hoặc bỏ qua thao tác đó.

## Bảo mật và tính lặp lại của POST

Sự xuất hiện của link POST chỉ là thông tin điều hướng, không phải quyền được cấp. Endpoint phải xác thực người gọi, kiểm tra quyền tạo tài nguyên, xác thực body và thực thi quy tắc nghiệp vụ. Người dùng vẫn có thể gửi request trực tiếp dù representation không công bố link.

Theo ngữ nghĩa HTTP, POST thường không idempotent: gửi lại cùng request có thể tạo nhiều tài nguyên hoặc thực hiện hành động nhiều lần. Client không nên tự động retry POST sau lỗi mạng mà không có chiến lược rõ ràng. Với thao tác cần chống tạo trùng, API có thể hỗ trợ idempotency key hoặc một mã yêu cầu duy nhất theo hợp đồng riêng.

Ngoài ra, cần giới hạn kích thước body, validate các ID tham chiếu, tránh tin cậy giá trị do client gửi để xác định chủ sở hữu và bảo đảm response không làm lộ dữ liệu mà người gọi không được phép xem.

## Kiểm thử link và affordance POST

Nên kiểm thử cả link trong representation và hành vi endpoint POST. Ví dụ với MockMvc, xác nhận collection có link tạo mới:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;

mockMvc.perform(get("/orders").accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath(
        "$._links['https://api.example.com/rels/create-order'].href").exists());
```

Với HAL-FORMS, kiểm tra template và method theo cấu trúc thực tế mà ứng dụng trả về. Với endpoint POST, kiểm tra status `201`, header `Location`, self link của tài nguyên mới và response body. Bổ sung trường hợp người dùng không có quyền tạo để xác nhận link không được công bố, đồng thời xác nhận endpoint vẫn từ chối request trực tiếp khi thiếu quyền.

Các lỗi thường gặp:

- **Chỉ công bố href:** client không biết method hoặc body nếu hợp đồng không mô tả affordance hay tài liệu tương ứng.
- **Đặt link sai cấp:** link tạo phần tử mới bị gắn vào từng phần tử thay vì collection.
- **Dùng relation mơ hồ:** client không hiểu link là tạo mới hay thực hiện một hành động khác.
- **Không trả Location:** client khó nhận biết URI của tài nguyên vừa được tạo theo quy ước HTTP.
- **Dựa vào link để phân quyền:** endpoint vẫn phải kiểm tra quyền độc lập.
- **Retry POST không kiểm soát:** có thể tạo tài nguyên trùng hoặc lặp tác động nghiệp vụ.

Link cho POST giúp client khám phá điểm vào tạo tài nguyên hoặc gửi lệnh. Kết hợp relation có ý nghĩa, affordance phù hợp, HAL-FORMS khi cần mô tả request body, response `201 Created` với `Location` và kiểm thử qua HTTP, Spring HATEOAS giúp hợp đồng API thể hiện rõ những tương tác mà server đang cung cấp.

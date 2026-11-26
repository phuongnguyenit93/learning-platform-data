# Ràng buộc Hypermedia (HATEOAS)

Ràng buộc hypermedia là phần của giao diện thống nhất trong REST, thường được diễn đạt bằng nguyên tắc **Hypermedia as the Engine of Application State (HATEOAS)**. Theo nguyên tắc này, client khám phá những bước tiếp theo của một tương tác bằng cách đọc các điều khiển hypermedia trong response, chẳng hạn liên kết và biểu mẫu. Server cung cấp các điều khiển phù hợp với tài nguyên và trạng thái nghiệp vụ hiện tại.

Điều này làm thay đổi cách client điều hướng API. Thay vì tự ghép URL theo cấu trúc đường dẫn mà đội server từng công bố, client bắt đầu từ một điểm vào đã biết, đọc các quan hệ liên kết, rồi đi theo liên kết phù hợp với mục tiêu của mình. Response vì vậy vừa mang dữ liệu vừa chỉ dẫn những chuyển tiếp có ý nghĩa.

Trong Spring HATEOAS, `RepresentationModel`, `EntityModel`, `CollectionModel`, `Link` và affordance là những thành phần giúp xây dựng các điều khiển đó. Bài học tập trung vào ý nghĩa của ràng buộc hypermedia, cách client sử dụng liên kết, cách server công bố hành động theo trạng thái và cách kiểm thử hợp đồng này.

Sau bài học, bạn có thể:

- Giải thích HATEOAS và vai trò của nó trong giao diện thống nhất của REST.
- Phân biệt tài nguyên, biểu diễn tài nguyên, link relation và affordance.
- Mô tả một luồng tương tác mà client khám phá bằng các liên kết do server cung cấp.
- Thiết kế liên kết phản ánh trạng thái nghiệp vụ bằng Spring HATEOAS.
- Chọn HAL hoặc HAL-FORMS tùy mức độ thông tin tương tác mà client cần.
- Kiểm thử khả năng điều hướng và tính ổn định của hợp đồng hypermedia.

## Vì sao cần ràng buộc hypermedia?

Một API có thể trả về JSON hợp lệ và dùng HTTP đúng cách nhưng vẫn buộc client biết trước mọi URL. Ví dụ, client luôn gọi `/orders/42`, sau đó tự đoán rằng muốn thanh toán thì phải gửi `POST` đến `/orders/42/pay`, còn muốn hủy thì gửi `DELETE` đến `/orders/42`. Các đường dẫn và quy tắc này trở thành kiến thức được sao chép trong từng ứng dụng web, ứng dụng di động hoặc dịch vụ tích hợp.

Khi server đổi đường dẫn, chuyển thanh toán sang một tài nguyên riêng hoặc thay đổi quy trình nghiệp vụ, mọi client chứa quy tắc cũ có thể phải sửa và phát hành lại. Server cũng khó thể hiện rằng một hành động chỉ khả dụng trong một số trạng thái nhất định.

HATEOAS giải quyết vấn đề khám phá bằng cách để response công bố các liên kết và điều khiển liên quan đến ngữ cảnh hiện tại. Client vẫn cần hiểu ý nghĩa của các quan hệ liên kết và mục tiêu nghiệp vụ của mình, nhưng không cần tự biết trước URL cụ thể của từng bước.

Ví dụ, một client muốn xử lý đơn hàng có thể:

1. Gọi URI điểm vào của API mà ứng dụng đã cấu hình.
2. Đọc liên kết có quan hệ `orders` để lấy danh sách đơn hàng.
3. Chọn một đơn hàng và theo liên kết `self` của đơn hàng đó.
4. Đọc các điều khiển được trả về. Nếu đơn hàng đang chờ thanh toán, response có thể cung cấp điều khiển `pay`; nếu đã thanh toán, điều khiển này không còn xuất hiện.
5. Theo điều khiển phù hợp, gửi request theo phương thức và dữ liệu mà media type mô tả.
6. Đọc response mới để khám phá trạng thái và các bước tiếp theo.

Server là nơi quyết định trạng thái nghiệp vụ và các hành động được công bố tại thời điểm tạo response. Client dùng thông tin đó để điều hướng. Đây là cơ chế khám phá và điều khiển luồng tương tác, không phải cơ chế cấp quyền: server vẫn phải xác thực, phân quyền và kiểm tra lại điều kiện nghiệp vụ ở mỗi request.

## Hypermedia trong giao diện thống nhất

Giao diện thống nhất của REST có bốn khía cạnh liên quan với nhau:

| Khía cạnh | Câu hỏi được trả lời | Ví dụ |
| --- | --- | --- |
| Nhận diện tài nguyên | Đang nói đến tài nguyên nào? | URI `/orders/42` |
| Thao tác qua biểu diễn | Client trao đổi biểu diễn nào để đọc hoặc thay đổi tài nguyên? | JSON đơn hàng và HTTP method |
| Thông điệp tự mô tả | Bên nhận hiểu thông điệp bằng thông tin nào? | Status code, header, media type và body |
| Hypermedia điều khiển trạng thái ứng dụng | Có thể đi đâu hoặc thực hiện bước nào tiếp theo? | Link relation, link template hoặc form/action |

Các khía cạnh này bổ sung cho nhau. URI nhận diện tài nguyên, biểu diễn mô tả dữ liệu, metadata giúp giải thích thông điệp, còn hypermedia cho biết các chuyển tiếp khả dụng. Chỉ thêm một trường `url` tùy ý vào JSON chưa đủ để tạo một giao diện hypermedia tốt: client cần biết liên kết đó có quan hệ gì với tài nguyên hiện tại và cách sử dụng nó.

### Tài nguyên, biểu diễn và trạng thái ứng dụng

Ba khái niệm này không nên bị đánh đồng:

- **Tài nguyên (resource):** khái niệm mà API cung cấp, ví dụ một đơn hàng hoặc tập hợp đơn hàng.
- **Biểu diễn (representation):** dữ liệu được trao đổi để mô tả tài nguyên tại một thời điểm, ví dụ JSON chứa mã, mô tả và trạng thái đơn hàng.
- **Trạng thái ứng dụng phía client:** vị trí hiện tại của client trong một luồng tương tác, ví dụ đang ở danh sách đơn hàng, đang xem chi tiết hoặc đang thực hiện thanh toán.

HATEOAS giúp client chuyển từ trạng thái tương tác này sang trạng thái khác thông qua các điều khiển trong biểu diễn. Một response của đơn hàng có thể vừa mô tả trạng thái nghiệp vụ `PENDING_PAYMENT`, vừa cung cấp liên kết đến thông tin đơn hàng và điều khiển để bắt đầu thanh toán.

Không nên hiểu rằng server phải lưu toàn bộ trạng thái màn hình hoặc phiên thao tác của client. Client vẫn có thể giữ trạng thái giao diện của riêng mình. Điều quan trọng là các chuyển tiếp tài nguyên và hành động trên API được khám phá qua hypermedia thay vì bị đóng cứng trong mã client.

## Link và link relation

Một liên kết hypermedia mô tả mối quan hệ giữa tài nguyên hiện tại (context) và một đích đến (target). Trong HTTP, định dạng liên kết thường mang một URI cùng kiểu quan hệ liên kết (link relation). Quan hệ cho biết liên kết có ý nghĩa gì, còn URI cho biết client có thể đi đến đâu.

Một số quan hệ thường gặp:

| Relation | Ý nghĩa thường dùng |
| --- | --- |
| `self` | Chính tài nguyên hiện tại |
| `collection` | Tập hợp chứa tài nguyên |
| `item` | Một phần tử trong tập hợp |
| `next` | Trang hoặc phần tiếp theo |
| `prev` | Trang hoặc phần trước |
| `first` / `last` | Trang đầu hoặc cuối |
| `related` | Tài nguyên có liên quan |
| `edit` | Đích dùng để chỉnh sửa theo hợp đồng của API |

Các relation đã đăng ký có thể dùng tên ngắn theo registry của IANA. API cũng có thể định nghĩa relation mở rộng bằng URI do tổ chức kiểm soát, ví dụ `https://api.example.com/rels/pay`. Dùng URI giúp giảm nguy cơ hai API gán ý nghĩa khác nhau cho cùng một tên tùy chỉnh. Tài liệu API cần giải thích semantics của relation mở rộng để client hiểu đúng.

Relation mô tả mối quan hệ giữa context và target; bản thân tên relation không tự định nghĩa đầy đủ HTTP method, schema request hay quy tắc phân quyền. Ví dụ, một liên kết có relation `payment` có thể trỏ đến tài nguyên thanh toán để đọc thông tin. Nếu muốn mô tả thao tác bắt đầu thanh toán, API cần một hợp đồng điều khiển rõ ràng, chẳng hạn affordance hoặc form có method và các trường đầu vào.

Client nên chọn liên kết theo relation và mục tiêu nghiệp vụ, sau đó sử dụng URI được cung cấp. Client không nên phụ thuộc vào vị trí của liên kết trong JSON, thứ tự các phần tử trong `_links` hay cách server đặt tên biến đường dẫn.

### Liên kết chuẩn và liên kết mở rộng

Relation chuẩn có semantics được công bố rộng rãi, giúp nhiều client và công cụ có thể hiểu cùng một ý nghĩa. Với hành động riêng của miền nghiệp vụ, relation mở rộng bằng URI là lựa chọn phù hợp. Ví dụ, API quản lý đơn hàng có thể định nghĩa:

```text
https://api.example.com/rels/pay
https://api.example.com/rels/cancel
https://api.example.com/rels/invoice
```

Tài liệu tại các URI relation nên mô tả mục đích, điều kiện khả dụng, media type liên quan và cách client sử dụng điều khiển. URI relation dùng để định danh semantics; nó không nhất thiết là endpoint để thực hiện request.

Không nên tái sử dụng một relation cho ý nghĩa mới chỉ vì tên cũ có vẻ gần giống. Khi semantics thay đổi không tương thích, hãy định nghĩa relation mới và cho phép client hỗ trợ dần. Điều này giúp duy trì hợp đồng giữa các phiên bản client và server.

## Hypermedia controls: link, template và affordance

Hypermedia control là thành phần trong biểu diễn cho phép client khám phá hoặc thực hiện một chuyển tiếp. Các dạng phổ biến gồm:

- **Link:** chỉ ra đích đến và quan hệ với tài nguyên hiện tại.
- **Templated link:** cung cấp mẫu URI với biến để client điền, thường dùng cho tìm kiếm hoặc lọc.
- **Form hoặc affordance:** mô tả một thao tác, bao gồm phương thức và dữ liệu đầu vào mà client có thể gửi.
- **Embedded resource:** nhúng biểu diễn của tài nguyên liên quan trong response để client có thể đọc ngay mà không phải gọi riêng một URI; tài nguyên nhúng vẫn có thể có link relation riêng.

Link và affordance có mục đích khác nhau. Link thường trả lời “tài nguyên liên quan ở đâu?”. Affordance trả lời thêm “có thể tương tác với đích theo cách nào và cần dữ liệu gì?”. Một định dạng hypermedia chỉ hỗ trợ link cơ bản có thể đủ cho điều hướng, trong khi luồng nghiệp vụ cần nhập dữ liệu thường cần biểu diễn form/action.

### Link không đồng nghĩa với lệnh HTTP

Một liên kết HAL cơ bản thường cung cấp `href` và relation. Nó không tự nói rằng client phải dùng `POST`, gửi JSON có những trường nào hoặc phải tuân theo validation gì. Client không nên suy đoán method chỉ từ tên relation.

Nếu API công bố một link `edit`, client vẫn cần hợp đồng rõ ràng về cách chỉnh sửa. Thông tin đó có thể đến từ tài liệu media type, affordance, form hoặc mô tả API đi kèm. Khi server cần công bố một hành động khả dụng ngay trong response, affordance giúp gắn mô tả thao tác vào link liên quan.

### Affordance và hành động khả dụng

Affordance mô tả khả năng tương tác có thể thực hiện đối với một tài nguyên. Nó có thể bao gồm HTTP method, kiểu nội dung, tiêu đề thao tác và các thuộc tính đầu vào. Ví dụ, đơn hàng đang chờ thanh toán có thể cung cấp affordance `pay` với `POST` và trường `paymentMethod` bắt buộc. Đơn hàng đã thanh toán sẽ không còn công bố thao tác đó.

Affordance phản ánh điều server cho biết là khả dụng khi response được tạo. Giữa lúc client đọc response và gửi request, dữ liệu có thể thay đổi. Server luôn phải kiểm tra lại điều kiện và trả status code phù hợp nếu thao tác không còn hợp lệ.

## Biểu diễn hypermedia với HAL và HAL-FORMS

Định dạng biểu diễn quyết định cách link và điều khiển được mã hóa trong body. Spring HATEOAS hỗ trợ HAL và HAL-FORMS, bên cạnh các kiểu biểu diễn hypermedia khác.

### HAL: liên kết và tài nguyên nhúng

HAL JSON dùng `_links` để biểu diễn liên kết và `_embedded` để chứa tài nguyên liên quan được nhúng. Ví dụ:

```json
{
  "id": 42,
  "description": "Bàn phím cơ",
  "status": "PENDING_PAYMENT",
  "_links": {
    "self": { "href": "/orders/42" },
    "collection": { "href": "/orders" },
    "https://api.example.com/rels/pay": {
      "href": "/orders/42/payment"
    }
  }
}
```

Trong ví dụ, `self` trỏ đến đơn hàng hiện tại, `collection` trỏ đến tập hợp, còn relation mở rộng `pay` công bố một đích liên quan đến thanh toán. Đây là ví dụ về link; chỉ từ cấu trúc HAL này, client chưa biết method và schema request của thao tác thanh toán.

HAL có thể biểu diễn nhiều liên kết cho cùng một relation, thông tin tiêu đề hoặc kiểu dữ liệu liên kết, link template và tài nguyên nhúng. Khi sử dụng HAL, response thường được gửi với media type `application/hal+json`. Client nên thương lượng và kiểm tra media type thay vì chỉ đoán định dạng từ phần mở rộng URL.

### HAL-FORMS: mô tả thao tác và dữ liệu đầu vào

HAL-FORMS mở rộng cách biểu diễn HAL để mô tả các template thao tác. Một template có thể nêu tên, HTTP method, content type và các thuộc tính mà client cần cung cấp. Ví dụ minh họa:

```json
{
  "_links": {
    "self": { "href": "/orders/42" }
  },
  "_templates": {
    "pay": {
      "title": "Thanh toán đơn hàng",
      "method": "POST",
      "contentType": "application/json",
      "properties": [
        {
          "name": "paymentMethod",
          "prompt": "Phương thức thanh toán",
          "required": true
        }
      ]
    }
  }
}
```

Đây là ví dụ rút gọn để minh họa ý nghĩa của template. Response HAL-FORMS thực tế phải tuân theo schema của media type và cấu hình của ứng dụng. Media type HAL-FORMS thường dùng là `application/prs.hal-forms+json`.

HAL phù hợp khi client chủ yếu cần khám phá tài nguyên và đi theo link. HAL-FORMS hữu ích khi client cần biết một thao tác có thể thực hiện bằng method nào và cần gửi những thuộc tính gì. Việc chọn định dạng nên dựa vào nhu cầu tương tác của client và khả năng hỗ trợ của hệ sinh thái tiêu thụ API.

## Áp dụng ràng buộc hypermedia trong Spring HATEOAS

Spring HATEOAS cung cấp mô hình Java để gắn link vào biểu diễn tài nguyên. `RepresentationModel<T>` là lớp cơ sở có khả năng chứa link; `EntityModel<T>` bọc một đối tượng; `CollectionModel<T>` biểu diễn tập hợp. `Link` chứa URI và relation. `RepresentationModelAssembler` tập trung việc chuyển đối tượng miền thành biểu diễn hypermedia.

Điểm quan trọng khi áp dụng HATEOAS là xây dựng link theo trạng thái nghiệp vụ. Ví dụ, một đơn hàng chỉ được phép thanh toán khi trạng thái là `PENDING_PAYMENT`. Assembler có thể công bố link thanh toán khi điều kiện này đúng:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<Order>> {

    @Override
    public EntityModel<Order> toModel(Order order) {
        EntityModel<Order> model = EntityModel.of(order,
            linkTo(methodOn(OrderController.class).one(order.id())).withSelfRel(),
            linkTo(methodOn(OrderController.class).all()).withRel("collection"));

        if (order.status() == OrderStatus.PENDING_PAYMENT) {
            model.add(linkTo(methodOn(PaymentController.class)
                .pay(order.id())).withRel("https://api.example.com/rels/pay"));
        }

        if (order.status() == OrderStatus.DRAFT) {
            model.add(linkTo(methodOn(OrderController.class)
                .cancel(order.id())).withRel("https://api.example.com/rels/cancel"));
        }

        return model;
    }
}
```

Đoạn mã giả định ứng dụng đã có `Order`, `OrderStatus`, `OrderController`, `PaymentController` và các phương thức tương ứng. Nó minh họa cách điều kiện nghiệp vụ quyết định link nào xuất hiện. `linkTo(methodOn(...))` xây URI dựa trên mapping controller, còn `withRel(...)` gắn semantics cho liên kết.

Các link ở ví dụ này vẫn là link HAL cơ bản. Nếu client cần biết rằng `pay` dùng `POST` với trường `paymentMethod`, hãy bổ sung affordance và chọn media type có khả năng biểu diễn thao tác, chẳng hạn HAL-FORMS. Không nên giả định relation URI tự mô tả toàn bộ request.

Controller có thể dùng assembler để trả representation model:

```java
@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService orderService;
    private final OrderModelAssembler assembler;

    OrderController(OrderService orderService, OrderModelAssembler assembler) {
        this.orderService = orderService;
        this.assembler = assembler;
    }

    @GetMapping("/{id}")
    EntityModel<Order> one(@PathVariable Long id) {
        Order order = orderService.findById(id)
            .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
        return assembler.toModel(order);
    }
}
```

Nhờ vậy, quy tắc tạo link nằm ở một nơi và có thể dùng lại trong nhiều endpoint. Với danh sách, assembler cũng có thể chuyển từng phần tử thành `EntityModel` rồi bọc trong `CollectionModel`, đồng thời thêm link phân trang như `next` và `prev` khi có trang tương ứng.

### Công bố điều khiển theo trạng thái, không theo suy đoán của client

Giả sử vòng đời đơn hàng có các trạng thái:

| Trạng thái | Điều khiển có thể công bố | Điều khiển không nên công bố |
| --- | --- | --- |
| `DRAFT` | `submit`, `cancel` | `ship`, `refund` |
| `PENDING_PAYMENT` | `pay`, `cancel` nếu chính sách cho phép | `refund`, `ship` |
| `PAID` | `ship`, `request-invoice` | `pay` |
| `SHIPPED` | `track` | `pay`, `ship` |
| `CANCELLED` | `self`, `collection` | `pay`, `ship`, `cancel` |

Bảng chỉ là một mô hình nghiệp vụ minh họa. Ứng dụng thực tế phải xác định điều khiển dựa trên trạng thái, quyền của người dùng, tồn kho, thời hạn và các điều kiện khác. Có thể cùng một trạng thái nhưng hai người dùng có quyền khác nhau sẽ nhận các affordance khác nhau.

Không công bố một điều khiển khi hành động không khả dụng giúp client tránh đưa ra lựa chọn vô ích. Tuy nhiên, không nên coi việc link vắng mặt là cơ chế bảo mật. Một client có thể giữ lại URL từ response cũ hoặc tự gửi request. Server phải từ chối thao tác không hợp lệ ngay cả khi client biết endpoint.

## Client tiêu thụ hypermedia như thế nào?

Một client HATEOAS cần biết điểm vào, media type được hỗ trợ và semantics của các relation mà nó quan tâm. Khi nhận response, client thực hiện quy trình tổng quát:

1. Kiểm tra status code và media type để biết response có thể được xử lý như thế nào.
2. Phân tích biểu diễn theo định dạng đã thương lượng, ví dụ HAL.
3. Tìm relation phù hợp với mục tiêu nghiệp vụ, ví dụ `orders`, `self` hoặc relation mở rộng `pay`.
4. Lấy URI từ link thay vì tự nối chuỗi URL.
5. Nếu có affordance/form, đọc method, content type và thuộc tính đầu vào trước khi gửi request.
6. Gửi request và đọc response tiếp theo để tiếp tục điều hướng.

Client không cần xử lý mọi relation mà server có thể gửi. Nó có thể bỏ qua relation chưa biết, miễn là vẫn xử lý đúng các relation bắt buộc trong hợp đồng mà nó hỗ trợ. Khi gặp relation mở rộng chưa biết, client có thể bỏ qua điều khiển đó hoặc hiển thị hành vi dự phòng phù hợp.

HATEOAS cũng không có nghĩa client hoàn toàn không cần kiến thức về nghiệp vụ. Client vẫn cần biết mục tiêu như “thanh toán đơn hàng” và hiểu relation nào biểu thị mục tiêu đó. Điều được giảm đi là sự phụ thuộc vào địa chỉ cụ thể và trình tự URL cố định.

## HATEOAS hỗ trợ khả năng tiến hóa API

Khi client dựa vào relation và điều khiển thay vì cấu trúc URL, server có thêm không gian thay đổi cách tổ chức endpoint. Ví dụ, ban đầu thanh toán có thể nằm tại `/orders/42/pay`; sau này server chuyển sang `/payments/9`. Nếu response vẫn công bố relation `pay` với URI mới và client theo link, client không cần biết thay đổi đường dẫn.

Hypermedia hỗ trợ tiến hóa hợp đồng theo một số cách:

- **Thay đổi URI:** server có thể đổi cấu trúc đường dẫn mà vẫn cung cấp relation tương ứng.
- **Thay đổi luồng:** server có thể thêm một bước xác nhận hoặc chuyển đến dịch vụ mới bằng cách cập nhật các điều khiển trong response.
- **Điều khiển theo trạng thái:** client nhận đúng hành động khả dụng tại thời điểm tương tác thay vì tự suy ra từ mã trạng thái hoặc URL.
- **Mở rộng tùy chọn:** server có thể thêm relation mới; client cũ có thể bỏ qua relation chưa biết nếu hợp đồng cho phép.
- **Phân trang và điều hướng:** link `next`, `prev`, `first` và `last` cho phép server thay đổi cách phân trang mà client không phải tự tính URL.

HATEOAS không tự làm mọi thay đổi trở nên tương thích ngược. Thay đổi semantics của relation, xóa một relation mà client phụ thuộc hoặc đổi schema của media type vẫn có thể phá vỡ client. API cần công bố relation ổn định, mô tả rõ điều khiển bắt buộc/tùy chọn và có chiến lược chuyển đổi khi thay đổi không tương thích.

Một số nguyên tắc thiết kế:

- Giữ semantics của relation ổn định qua các phiên bản.
- Dùng URI relation riêng cho semantics mở rộng và công bố tài liệu mô tả.
- Không yêu cầu client phụ thuộc vào thứ tự hoặc vị trí của link trong body.
- Thêm relation mới theo hướng tương thích; client nên bỏ qua relation mà nó không hiểu.
- Chỉ bỏ relation cũ sau khi có kế hoạch chuyển đổi cho client đang sử dụng.
- Dùng affordance/form khi client cần mô tả thao tác và schema đầu vào, thay vì yêu cầu client đoán method.
- Duy trì kiểm tra quyền và quy tắc nghiệp vụ ở server cho mọi request.

## Kiểm thử ràng buộc hypermedia

Kiểm thử hypermedia cần xác minh khả năng khám phá và điều hướng, không chỉ kiểm tra rằng JSON có trường `_links`. Một response có thể chứa link nhưng relation sai, URI sai hoặc link không phản ánh trạng thái nghiệp vụ.

Với Spring MVC Test, có thể kiểm tra media type, relation và URI được công bố:

```java
@Test
void pendingOrderExposesPayControl() throws Exception {
    mockMvc.perform(get("/orders/{id}", 42)
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
        .andExpect(jsonPath("$._links.self.href").exists())
        .andExpect(jsonPath("$._links['https://api.example.com/rels/pay'].href")
            .exists());
}
```

Test trên giả định đơn hàng 42 đang ở trạng thái `PENDING_PAYMENT` và dữ liệu test đã được chuẩn bị. Cần thêm test cho trạng thái đã thanh toán để xác minh điều khiển `pay` không còn được công bố:

```java
@Test
void paidOrderDoesNotExposePayControl() throws Exception {
    mockMvc.perform(get("/orders/{id}", 43)
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$._links['https://api.example.com/rels/pay']")
            .doesNotExist());
}
```

Ngoài kiểm tra từng response, nên có kiểm thử luồng điều hướng. Bắt đầu từ URI điểm vào, lấy relation `orders`, chọn một phần tử, theo `self`, đọc relation `pay` và thực hiện thao tác theo affordance nếu có. Kiểm thử như vậy xác minh rằng client có thể khám phá quy trình qua response thay vì phụ thuộc vào URL được viết sẵn trong test.

Danh sách kiểm tra hợp đồng:

1. Response dùng đúng media type đã công bố và client có thể phân tích.
2. Các tài nguyên có relation `self` hợp lệ.
3. Relation trỏ đến đúng đích và giữ nguyên semantics qua các phiên bản.
4. Link hành động xuất hiện đúng trạng thái và đúng quyền.
5. Link hoặc affordance mô tả đủ thông tin mà client cần để thực hiện thao tác.
6. Relation tùy chỉnh có tài liệu mô tả và định danh ổn định.
7. Client có thể đi theo link qua luồng nghiệp vụ mà không phải tự tạo URI.
8. Client bỏ qua được relation mới mà nó chưa hỗ trợ.
9. Server vẫn từ chối request trái quyền hoặc không hợp lệ dù client gửi trực tiếp đến endpoint.

## Những hiểu lầm thường gặp

**HATEOAS có nghĩa là client không cần biết gì về API.** Client vẫn cần biết media type, mục tiêu nghiệp vụ và semantics của relation mà nó sử dụng. HATEOAS giảm phụ thuộc vào URL và trình tự điều hướng được mã hóa cứng.

**Chỉ cần trả về một danh sách URL là đã có hypermedia.** Client cần biết mỗi URL có quan hệ gì với tài nguyên hiện tại. Relation và media type cung cấp ngữ nghĩa để client hiểu điều khiển.

**Relation chính là HTTP method.** Relation mô tả quan hệ giữa context và target. Method và dữ liệu đầu vào cần được mô tả bằng hợp đồng tương ứng, chẳng hạn affordance hoặc form.

**Link xuất hiện đồng nghĩa người dùng chắc chắn được phép thực hiện.** Link là thông tin điều hướng được công bố tại thời điểm response được tạo. Server vẫn phải xác thực và phân quyền ở thời điểm nhận request.

**Không có link nghĩa là endpoint không tồn tại.** Link vắng mặt thường có nghĩa điều khiển đó không được công bố trong ngữ cảnh hiện tại. Endpoint có thể vẫn tồn tại cho trạng thái khác, người dùng khác hoặc client có quyền khác.

**HATEOAS tự động bảo đảm tương thích ngược.** Khả năng tiến hóa phụ thuộc vào semantics relation ổn định, media type rõ ràng và quy tắc tương thích của hợp đồng. Đổi semantics hoặc xóa điều khiển mà client cần vẫn có thể phá vỡ tích hợp.

**HAL mô tả đầy đủ mọi hành động.** HAL cơ bản mô tả link và tài nguyên nhúng. Khi cần mô tả method và các trường đầu vào, hãy dùng affordance cùng định dạng phù hợp như HAL-FORMS.

## Kết luận

Ràng buộc hypermedia yêu cầu response REST cung cấp các điều khiển giúp client khám phá tài nguyên và chuyển tiếp giữa các trạng thái tương tác. Link relation mô tả ý nghĩa của đích đến; affordance và form mô tả thêm cách thực hiện hành động. Server công bố điều khiển theo trạng thái và ngữ cảnh, còn client chọn relation phù hợp rồi theo URI được cung cấp.

Spring HATEOAS hỗ trợ xây dựng hợp đồng này bằng `RepresentationModel`, `EntityModel`, `CollectionModel`, `Link`, assembler và affordance. Khi thiết kế, hãy giữ semantics relation ổn định, công bố đúng điều khiển theo nghiệp vụ, chọn media type phù hợp và kiểm thử luồng điều hướng như một phần của hợp đồng API. Nhờ đó, client có thể thích ứng tốt hơn khi server thay đổi URI hoặc quy trình nội bộ.

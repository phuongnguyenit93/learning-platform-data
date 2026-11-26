# Mục tiêu của thư viện

Spring HATEOAS là thư viện thuộc hệ sinh thái Spring, giúp xây dựng REST API theo hướng **hypermedia**. Thư viện cung cấp mô hình representation có thể mang liên kết, công cụ tạo URI dựa trên mapping của ứng dụng, cách lắp ghép tài nguyên thành representation và hỗ trợ các định dạng hypermedia như HAL. Mục tiêu là để client khám phá tài nguyên và hành động tiếp theo thông qua nội dung server trả về.

Tên HATEOAS là viết tắt của *Hypermedia As The Engine Of Application State*. Ý tưởng cốt lõi là trạng thái điều hướng của client được dẫn dắt bởi các hypermedia control trong representation. Khi client nhận một tài nguyên, server cung cấp những liên kết có ý nghĩa cho phép client đi đến tài nguyên liên quan hoặc thực hiện bước tiếp theo. Client dựa vào quan hệ liên kết và hợp đồng media type để hiểu ý nghĩa của các đường dẫn.

## 1. Vấn đề Spring HATEOAS giải quyết

Một REST API có thể trả về JSON chứa dữ liệu nghiệp vụ mà không có liên kết:

```json
{
  "id": 42,
  "status": "PENDING",
  "total": 1250000
}
```

Representation này cho client biết đơn hàng có mã `42`, đang chờ xử lý và có tổng tiền `1250000`. Nhưng nếu client muốn xem chi tiết, hủy đơn hoặc kiểm tra thanh toán, nó cần biết URI của các endpoint tiếp theo. Nếu những URI này chỉ được cấu hình sẵn trong mã client, client sẽ phụ thuộc vào cấu trúc URL của server. Khi server thay đổi đường dẫn, nhiều client có thể phải cập nhật theo.

Server có thể trả về representation có hypermedia:

```json
{
  "id": 42,
  "status": "PENDING",
  "total": 1250000,
  "_links": {
    "self": {
      "href": "https://api.example.test/orders/42"
    },
    "orders": {
      "href": "https://api.example.test/orders"
    },
    "cancel": {
      "href": "https://api.example.test/orders/42/cancellation"
    }
  }
}
```

Client có thể tìm quan hệ `self` để mở chính đơn hàng, `orders` để quay lại danh sách và `cancel` để bắt đầu thao tác hủy. Client không cần tự ghép đường dẫn từ mã đơn hàng theo một quy ước URL riêng nếu nó tuân theo các quan hệ mà API cung cấp.

Spring HATEOAS giúp ứng dụng Spring tạo và quản lý các representation như vậy một cách nhất quán. Nếu tự xây dựng mọi liên kết bằng chuỗi, ứng dụng dễ lặp mã, ghép sai URI khi mapping thay đổi hoặc tạo representation khác nhau giữa các controller. Các abstraction của thư viện giúp tách dữ liệu miền nghiệp vụ khỏi phần cấu trúc hypermedia.

## 2. Các mục tiêu chính

### 2.1. Đưa liên kết thành một phần của representation

Thay vì trả về một đối tượng dữ liệu đơn thuần, ứng dụng có thể trả về mô hình chứa dữ liệu và các liên kết. Liên kết được gắn với quan hệ (*link relation*), chẳng hạn `self`, `next`, `prev`, `orders` hoặc một quan hệ nghiệp vụ do API định nghĩa.

Quan hệ liên kết mô tả **ý nghĩa** của liên kết. Client nên dựa vào quan hệ như `next` để biết đây là trang tiếp theo, thay vì suy luận từ chuỗi URI. Với quan hệ tùy chỉnh, đội phát triển cần định nghĩa ý nghĩa ổn định và tài liệu hóa để client có thể hiểu.

### 2.2. Tạo URI từ mapping của ứng dụng

Spring HATEOAS cung cấp `WebMvcLinkBuilder` cho Spring MVC. Các hàm `linkTo(...)` và `methodOn(...)` cho phép tạo liên kết dựa trên controller và phương thức handler. Nhờ đó, mã tạo link bám theo mapping của ứng dụng thay vì nối chuỗi đường dẫn bằng tay.

### 2.3. Cung cấp abstraction cho tài nguyên đơn và tập hợp

Thư viện có các kiểu mô hình để biểu diễn nhiều hình dạng tài nguyên: `RepresentationModel`, `EntityModel`, `CollectionModel` và `PagedModel`. Chúng giúp ứng dụng gắn liên kết ở cấp tài nguyên, danh sách hoặc trang dữ liệu.

### 2.4. Hỗ trợ định dạng hypermedia

Spring HATEOAS cung cấp hỗ trợ cho các media type hypermedia. HAL (*Hypertext Application Language*) là một lựa chọn phổ biến, sử dụng `_links` cho liên kết và `_embedded` cho tài nguyên được nhúng. Việc dùng một định dạng nhất quán giúp client và server thống nhất cách trao đổi liên kết.

### 2.5. Hỗ trợ client khám phá hành động và API tiến hóa

Server có thể đưa một liên kết hành động vào representation khi hành động đó khả dụng với trạng thái tài nguyên hiện tại. Ví dụ, đơn hàng đang `PENDING` có thể có liên kết `cancel`; đơn hàng đã `SHIPPED` có thể không còn liên kết này. Client khám phá khả năng hiện tại từ response.

Khi server thay đổi cấu trúc URI nhưng vẫn giữ nguyên quan hệ liên kết và ý nghĩa của nó, client dựa trên hypermedia có thể tiếp tục hoạt động mà không phải biết trước đường dẫn mới. Đây là một cách giảm liên kết chặt giữa client và cấu trúc URL của server, góp phần giúp hợp đồng API tiến hóa ổn định hơn.

## 3. Các abstraction quan trọng

| Kiểu | Vai trò | Khi sử dụng |
| --- | --- | --- |
| `RepresentationModel<T>` | Lớp cơ sở để xây dựng representation tùy chỉnh có thể mang liên kết | Khi cần một kiểu response riêng, có cấu trúc rõ ràng |
| `EntityModel<T>` | Bọc một đối tượng nội dung cùng các liên kết | Khi muốn bổ sung hypermedia cho DTO hoặc đối tượng response hiện có |
| `CollectionModel<T>` | Biểu diễn một tập hợp các representation | Khi trả danh sách tài nguyên |
| `PagedModel<T>` | Biểu diễn tập hợp có thông tin phân trang | Khi API trả dữ liệu theo trang |
| `Link` | Mô tả một liên kết và quan hệ của nó | Khi thêm `self`, `next` hoặc quan hệ nghiệp vụ |
| `RepresentationModelAssembler` | Chuyển đổi đối tượng miền hoặc DTO thành representation có liên kết | Khi muốn gom logic dựng representation và tái sử dụng giữa các endpoint |

Khi cần định nghĩa kiểu response riêng, có thể kế thừa `RepresentationModel`:

```java
import org.springframework.hateoas.RepresentationModel;

class OrderModel extends RepresentationModel<OrderModel> {

    private final Long id;
    private final String status;

    OrderModel(Long id, String status) {
        this.id = id;
        this.status = status;
    }

    public Long getId() {
        return id;
    }

    public String getStatus() {
        return status;
    }
}
```

`OrderModel` vừa mang dữ liệu đơn hàng, vừa kế thừa khả năng thêm liên kết từ `RepresentationModel`. Controller hoặc assembler có thể tạo đối tượng này, rồi gọi `add(...)` để gắn liên kết `self` và các hành động phù hợp.

Ví dụ, `EntityModel<OrderView>` thể hiện một đơn hàng dưới dạng response có liên kết. `CollectionModel<EntityModel<OrderView>>` có thể biểu diễn danh sách các đơn hàng, trong đó từng phần tử có liên kết riêng và tập hợp có thể có thêm liên kết điều hướng.

## 4. Ví dụ tích hợp trong controller Spring MVC

Giả sử ứng dụng có `OrderService` để truy vấn đơn hàng và một DTO `OrderView` để xuất dữ liệu. Controller có thể tạo representation bằng `EntityModel`:

```java
import java.util.List;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/{id}")
    EntityModel<OrderView> one(@PathVariable Long id) {
        OrderView order = orderService.findViewById(id);

        return EntityModel.of(order,
                linkTo(methodOn(OrderController.class).one(id)).withSelfRel(),
                linkTo(methodOn(OrderController.class).all()).withRel("orders"));
    }

    @PostMapping("/{id}/cancellation")
    EntityModel<OrderView> cancel(@PathVariable Long id) {
        OrderView order = orderService.cancelAndFindView(id);
        return EntityModel.of(order,
                linkTo(methodOn(OrderController.class).one(id)).withSelfRel());
    }

    @GetMapping
    CollectionModel<EntityModel<OrderView>> all() {
        List<EntityModel<OrderView>> orders = orderService.findAllViews().stream()
                .map(order -> EntityModel.of(order,
                        linkTo(methodOn(OrderController.class)
                                .one(order.id())).withSelfRel()))
                .toList();

        return CollectionModel.of(orders,
                linkTo(methodOn(OrderController.class).all()).withSelfRel());
    }
}
```

Trong ví dụ:

- `EntityModel.of(...)` bọc DTO cùng các liên kết.
- `linkTo(methodOn(OrderController.class).one(id))` tham chiếu đến handler `one` để tạo URI chi tiết.
- `withSelfRel()` gắn quan hệ chuẩn `self`.
- `withRel("orders")` gắn quan hệ nghiệp vụ `orders`.
- `CollectionModel.of(...)` biểu diễn danh sách và liên kết của tập hợp.

`methodOn(...)` tạo một proxy dùng để mô tả lời gọi controller; nó không thực thi logic nghiệp vụ của phương thức handler trong lúc dựng liên kết. Các kiểu trả về `OrderView`, `OrderService` và phương thức truy vấn trong ví dụ là thành phần của ứng dụng giả định, cần được định nghĩa trong dự án thực tế. Với dự án dùng Java phiên bản chưa hỗ trợ `Stream.toList()`, có thể thay bằng cách thu thập danh sách tương ứng của phiên bản Java đó.

Khi cấu hình ứng dụng để xuất HAL, client có thể yêu cầu representation bằng header `Accept: application/hal+json`. JSON trả về sẽ có phần `_links` chứa các quan hệ đã thêm. Cách cấu hình cụ thể phụ thuộc phiên bản Spring Boot, Spring HATEOAS và cơ chế content negotiation của ứng dụng.

## 5. Từ dữ liệu miền đến hypermedia representation

Một ứng dụng nên phân biệt ba lớp khái niệm:

1. **Mô hình miền** mô tả nghiệp vụ, chẳng hạn `Order`, trạng thái thanh toán và quy tắc có được hủy hay không.
2. **DTO hoặc view model** xác định dữ liệu nghiệp vụ nào được đưa ra ngoài API.
3. **Hypermedia representation** bổ sung các liên kết và metadata điều hướng cho DTO đó.

Sự phân biệt này giúp tránh đưa chi tiết liên kết HTTP vào entity lưu trong cơ sở dữ liệu. Ví dụ, `Order` có thể cung cấp `canBeCancelled()` để phản ánh quy tắc nghiệp vụ; lớp assembler hoặc phương thức dựng representation dùng kết quả đó để quyết định có thêm liên kết `cancel` hay không.

Một assembler có thể tập trung việc chuyển đổi này:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

class OrderModelAssembler
        implements RepresentationModelAssembler<OrderView, EntityModel<OrderView>> {

    @Override
    public EntityModel<OrderView> toModel(OrderView order) {
        EntityModel<OrderView> model = EntityModel.of(order,
                linkTo(methodOn(OrderController.class).one(order.id())).withSelfRel());

        if (order.canBeCancelled()) {
            model.add(linkTo(methodOn(OrderController.class)
                    .cancel(order.id())).withRel("cancel"));
        }

        return model;
    }
}
```

Controller có thể dùng assembler ở nhiều endpoint để representation của cùng loại tài nguyên nhất quán. Trong ứng dụng thực tế, cần bảo đảm `canBeCancelled()` phản ánh đúng chính sách nghiệp vụ và endpoint hủy vẫn kiểm tra lại điều kiện khi nhận request. Việc có liên kết trong response không phải là cơ chế cấp quyền.

## 6. Affordance: mô tả hành động sâu hơn một liên kết

Một `Link` cơ bản cho client biết có thể đi theo một URI với quan hệ nhất định. Trong một số API, client còn cần metadata mô tả cách thực hiện hành động, chẳng hạn phương thức HTTP hoặc các trường đầu vào. Spring HATEOAS có khái niệm **affordance** để gắn mô tả khả năng thao tác với liên kết.

Affordance có thể hỗ trợ tạo representation giàu thông tin hơn, ví dụ một hành động cập nhật có dữ liệu đầu vào được mô tả. Tuy nhiên, client chỉ khai thác được metadata nếu media type và cách triển khai phía client hỗ trợ nó. Không phải mọi định dạng hypermedia đều biểu diễn affordance giống nhau; một liên kết HAL cơ bản không tự động mô tả đầy đủ schema của request body.

## 7. Spring HATEOAS không tự giải quyết mọi vấn đề API

Thư viện cung cấp công cụ để tạo hypermedia representation. Nó không thay thế thiết kế nghiệp vụ, bảo mật, lưu trữ hay kiểm thử API.

- **Không tự cấp quyền:** liên kết `cancel` chỉ quảng bá một khả năng. Server vẫn phải xác thực người dùng, kiểm tra phân quyền và trạng thái tài nguyên khi xử lý request.
- **Không tự tạo hợp đồng nghiệp vụ hoàn chỉnh:** đội phát triển vẫn cần định nghĩa ý nghĩa của relation, cấu trúc dữ liệu, mã lỗi và quy tắc chuyển trạng thái.
- **Không làm mọi client tự động tương thích:** client phải hiểu media type, relation và các quy tắc nghiệp vụ mà API công bố.
- **Không bảo đảm tương thích ngược chỉ nhờ có link:** thay đổi ý nghĩa của relation hoặc cấu trúc dữ liệu vẫn có thể phá vỡ client.
- **Không bắt buộc mọi response đều có nhiều liên kết:** chỉ cung cấp các liên kết có ích cho việc khám phá và điều hướng trong ngữ cảnh của tài nguyên.

Do đó, Spring HATEOAS là công cụ hỗ trợ thực hiện một thiết kế hypermedia có chủ đích. Chất lượng API vẫn phụ thuộc vào cách đội phát triển đặt tên quan hệ, lựa chọn media type, mô hình hóa hành động và giữ ổn định ngữ nghĩa của hợp đồng.

## 8. Kiểm tra mục tiêu thư viện đã được áp dụng

Khi đánh giá một endpoint Spring HATEOAS, có thể kiểm tra các điểm sau:

- Response có mô hình tài nguyên rõ ràng và chứa dữ liệu cần thiết cho client.
- Liên kết `self` trỏ đến đúng tài nguyên.
- Các relation có tên và ý nghĩa nhất quán; client không phải suy luận hành động từ chuỗi URL.
- Các liên kết điều hướng hoặc hành động phản ánh trạng thái tài nguyên tại thời điểm response được tạo.
- URI được tạo từ mapping của ứng dụng và không phụ thuộc vào việc ghép chuỗi thủ công ở nhiều nơi.
- Media type được công bố rõ ràng và response có cấu trúc phù hợp với định dạng đó, chẳng hạn HAL.
- Client có thể theo liên kết nhận được để tiếp tục tương tác; server vẫn kiểm tra quyền và điều kiện nghiệp vụ ở request tiếp theo.

Với kiểm thử tích hợp Spring MVC, có thể dùng `MockMvc` để gọi endpoint, xác nhận `Content-Type` và kiểm tra các đường dẫn trong `_links`, chẳng hạn `$._links.self.href` hoặc `$._links.cancel.href` theo cấu trúc JSON thực tế. Nên kiểm tra cả trường hợp hành động khả dụng và không khả dụng để bảo đảm tập liên kết thay đổi đúng theo trạng thái tài nguyên.

Khi áp dụng đúng mục tiêu, Spring HATEOAS giúp REST API công bố cách khám phá tài nguyên và các bước tương tác ngay trong representation. Nhờ đó, client có thể điều hướng theo hợp đồng hypermedia, còn server có không gian thay đổi cấu trúc URI và cách tổ chức endpoint mà vẫn giữ ổn định ngữ nghĩa liên kết đã công bố.

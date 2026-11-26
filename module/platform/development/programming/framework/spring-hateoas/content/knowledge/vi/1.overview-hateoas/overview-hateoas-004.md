# Tài nguyên và biểu diễn trong Spring HATEOAS

Trong một API REST, tài nguyên là khái niệm nghiệp vụ mà client có thể tham chiếu qua URI; biểu diễn là dữ liệu mô tả trạng thái hiện tại của tài nguyên được gửi qua HTTP. Spring HATEOAS giúp ghép dữ liệu biểu diễn với các liên kết hypermedia, để client có thể khám phá tài nguyên liên quan và những thao tác mà API đang công bố.

Bài học này đặt nền tảng cho việc thiết kế tài nguyên và cấu trúc response bằng Spring HATEOAS. Ví dụ xuyên suốt sử dụng tài nguyên đơn hàng, nhưng cách tổ chức có thể áp dụng cho khách hàng, sản phẩm, hồ sơ hoặc quy trình nghiệp vụ khác.

## 1. Phân biệt tài nguyên, biểu diễn và mô hình miền

Ba khái niệm này liên quan chặt chẽ nhưng không đồng nghĩa:

- **Tài nguyên (resource)** là đối tượng hoặc khái niệm có ý nghĩa trong miền nghiệp vụ, được nhận diện qua một URI. Ví dụ: đơn hàng có URI **/orders/ORD-42**.
- **Biểu diễn (representation)** là cách API truyền trạng thái của tài nguyên tại một thời điểm và theo một định dạng cụ thể. Một đơn hàng có thể được biểu diễn bằng JSON chứa mã đơn, trạng thái và tổng tiền.
- **Mô hình miền (domain model)** là cấu trúc mà ứng dụng dùng để thực thi quy tắc nghiệp vụ. Nó có thể gồm trạng thái nội bộ, quan hệ ORM, phương thức và dữ liệu mà client không cần biết.

Một tài nguyên có thể có nhiều biểu diễn. Chẳng hạn, cùng một đơn hàng có thể được trả về dưới dạng HAL JSON cho ứng dụng web hoặc một định dạng khác cho hệ thống tích hợp. Ngược lại, một biểu diễn cũng có thể tổng hợp thông tin từ nhiều đối tượng miền. Vì vậy, không nên mặc định mỗi entity trong cơ sở dữ liệu tương ứng với đúng một tài nguyên công khai.

Ví dụ, đơn hàng trong hệ thống có thể chứa thông tin thanh toán, địa chỉ giao hàng, lịch sử thay đổi và các tham chiếu nội bộ. API danh sách đơn hàng có thể chỉ cần trả về mã đơn, trạng thái và tổng tiền. Khi client mở một đơn hàng, API mới cung cấp thêm các liên kết đến khách hàng, chi tiết giao hàng hoặc thao tác hủy nếu thao tác đó còn hợp lệ.

URI nhận diện tài nguyên; nội dung response mô tả trạng thái; các liên kết chỉ ra những quan hệ hoặc đường đi tiếp theo mà client có thể khám phá.

## 2. Thiết kế ranh giới tài nguyên

Khi thiết kế API, hãy bắt đầu từ các khái niệm và quan hệ nghiệp vụ mà client cần thao tác, sau đó mới quyết định cách ánh xạ chúng thành endpoint.

Với miền đơn hàng, một thiết kế cơ bản có thể gồm:

| Tài nguyên | URI ví dụ | Ý nghĩa |
|---|---|---|
| Tập hợp đơn hàng | **/orders** | Tìm và duyệt các đơn hàng |
| Một đơn hàng | **/orders/ORD-42** | Xem trạng thái của một đơn hàng |
| Khách hàng | **/customers/CUS-7** | Xem thông tin khách hàng |
| Các mục hàng của đơn | **/orders/ORD-42/items** | Xem các dòng hàng thuộc đơn hàng |

Tên tài nguyên thường là danh từ và phản ánh ngôn ngữ nghiệp vụ. URI nên ổn định trong suốt vòng đời API; client không nên phải suy ra URI tiếp theo bằng cách nối chuỗi từ URI hiện tại.

Một số nguyên tắc thực tế:

1. **Chọn ranh giới theo nghiệp vụ.** Một tài nguyên nên có danh tính và ý nghĩa rõ ràng đối với client. Không đưa mọi bảng dữ liệu nội bộ thành endpoint công khai.
2. **Phân biệt tài nguyên đơn và tập hợp.** **/orders** đại diện tập hợp; **/orders/ORD-42** đại diện một đơn hàng. Hai response có thể dùng các mô hình Spring HATEOAS khác nhau.
3. **Biểu diễn quan hệ bằng liên kết.** Một đơn hàng có thể cung cấp liên kết đến khách hàng hoặc các mục hàng thay vì buộc client biết trước cấu trúc URL.
4. **Giữ dữ liệu công khai có chủ đích.** Chỉ trả về trường cần cho use case. Tránh để cấu trúc entity, tên cột hoặc quan hệ ORM quyết định hợp đồng API.
5. **Tách thao tác khỏi trạng thái.** Trạng thái của đơn hàng là dữ liệu; khả năng hủy đơn là một hành động có thể thay đổi theo trạng thái và quyền của người gọi.

Không phải mọi quan hệ đều cần nhúng toàn bộ dữ liệu vào response. Nếu dữ liệu liên quan lớn, thay đổi độc lập hoặc được nhiều tài nguyên dùng chung, một liên kết đến tài nguyên riêng thường giúp response gọn và giảm phụ thuộc giữa các phần của API.

## 3. Các kiểu mô hình trong Spring HATEOAS

Spring HATEOAS cung cấp các lớp mô hình để ghép nội dung với liên kết. Chúng là lớp biểu diễn cho API, không phải entity lưu trữ của JPA.

| Kiểu | Dùng khi nào | Nội dung chính |
|---|---|---|
| **RepresentationModel<T>** | Cần định nghĩa một kiểu biểu diễn riêng có liên kết | Lớp cơ sở để thêm và quản lý các **Link** |
| **EntityModel<T>** | Trả về một tài nguyên cùng nội dung DTO | Một đối tượng nội dung được bọc trong mô hình có liên kết |
| **CollectionModel<T>** | Trả về tập hợp tài nguyên | Nhiều mô hình phần tử, có thể kèm liên kết cho tập hợp |
| **PagedModel<T>** | Trả về kết quả phân trang | Tập hợp phần tử cùng metadata và liên kết điều hướng trang |

### 3.1. RepresentationModel

Khi cần một kiểu biểu diễn chuyên biệt, có thể kế thừa **RepresentationModel**:

~~~java
public class OrderView extends RepresentationModel<OrderView> {

    private UUID id;
    private String status;
    private BigDecimal total;

    // Constructor, getter và setter
}
~~~

Lớp này có thể chứa các trường mà API muốn công bố và nhận thêm liên kết bằng phương thức **add**. Kiểu generic tự tham chiếu giúp các phương thức thao tác liên kết trả về đúng kiểu mô hình.

Tuy nhiên, không cần tạo lớp con cho mọi response. Nếu chỉ cần bọc một DTO có sẵn và gắn liên kết, **EntityModel<T>** thường ngắn gọn hơn.

### 3.2. EntityModel

**EntityModel<T>** biểu diễn một tài nguyên đơn. Ví dụ, nội dung đơn hàng được giữ trong DTO **OrderRepresentation**, còn các liên kết được gắn ở lớp bao:

~~~java
OrderRepresentation body =
    new OrderRepresentation(order.getId(), order.getStatus().name(), order.getTotal());

EntityModel<OrderRepresentation> model = EntityModel.of(body);
~~~

Sau đó có thể thêm liên kết:

~~~java
model.add(linkTo(methodOn(OrderController.class)
        .one(order.getId()))
        .withSelfRel());
~~~

**self** là quan hệ chuẩn để chỉ liên kết đến chính tài nguyên đang được biểu diễn. Việc đặt liên kết bên cạnh nội dung giúp client nhận biết cả dữ liệu lẫn vị trí của tài nguyên trong API.

### 3.3. CollectionModel và PagedModel

**CollectionModel<T>** phù hợp khi endpoint trả về một tập hợp. Ngoài các phần tử, mô hình tập hợp có thể có liên kết **self**, liên kết đến tài nguyên liên quan hoặc liên kết điều hướng.

~~~java
CollectionModel<EntityModel<OrderRepresentation>> result =
    assembler.toCollectionModel(orders);
~~~

Với danh sách lớn, phân trang giúp giới hạn lượng dữ liệu mỗi response và cho client biết cách đi đến trang trước, trang tiếp theo hoặc trang đầu/cuối. **PagedModel<T>** bổ sung metadata phân trang cho một tập hợp. Các liên kết điều hướng nên được tạo từ thông tin phân trang thực tế, thay vì yêu cầu client tự tính URL.

Hãy chọn kiểu mô hình theo hình dạng response: một tài nguyên, một tập hợp hay một tập hợp có phân trang. Không nên trả về một mảng DTO thuần nếu mục tiêu của endpoint là cung cấp tài nguyên có khả năng điều hướng hypermedia.

## 4. Tách DTO khỏi entity và tạo mô hình biểu diễn

Một API bền vững thường có ba lớp trách nhiệm:

- **Entity hoặc domain object** giữ trạng thái và quy tắc nghiệp vụ.
- **DTO/representation** xác định dữ liệu công khai mà client được nhận.
- **Assembler** chuyển domain object thành representation và gắn các liên kết phù hợp.

Ví dụ DTO có thể dùng Java record:

~~~java
import org.springframework.hateoas.server.core.Relation;

import java.math.BigDecimal;
import java.util.UUID;

@Relation(itemRelation = "order", collectionRelation = "orders")
public record OrderRepresentation(
    UUID id,
    String status,
    BigDecimal total
) {}
~~~

**@Relation** cung cấp tên quan hệ cho phần tử và tập hợp khi Spring HATEOAS tạo biểu diễn HAL. Nhờ đó, tên quan hệ trong **_embedded** có thể được định nghĩa rõ ràng theo ngôn ngữ API.

Assembler chịu trách nhiệm chuyển đổi và gắn liên kết:

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
public class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderRepresentation>> {

    @Override
    public EntityModel<OrderRepresentation> toModel(Order order) {
        var body = new OrderRepresentation(
            order.getId(),
            order.getStatus().name(),
            order.getTotal()
        );

        var model = EntityModel.of(
            body,
            linkTo(methodOn(OrderController.class).one(order.getId()))
                .withSelfRel()
        );

        model.add(
            linkTo(methodOn(OrderController.class).all())
                .withRel("orders")
        );

        if (order.canCancel()) {
            model.add(
                linkTo(methodOn(OrderController.class).cancel(order.getId()))
                    .withRel("cancel")
            );
        }

        return model;
    }
}
~~~

Trong ví dụ, **Order** là mô hình miền; **OrderRepresentation** là hợp đồng dữ liệu công khai; **OrderModelAssembler** là nơi kết hợp nội dung và liên kết. Phương thức **toModel** chỉ trả về liên kết **cancel** khi quy tắc nghiệp vụ cho phép hủy.

**RepresentationModelAssembler<T, D>** chuẩn hóa cách chuyển một đối tượng nguồn thành mô hình biểu diễn. Ngoài **toModel**, assembler còn cung cấp **toCollectionModel** để chuyển một tập hợp đối tượng nguồn thành **CollectionModel<D>**. Cách này tránh lặp logic tạo DTO và liên kết ở nhiều controller.

Các import và tên kiểu trong ví dụ giả định ứng dụng đã thêm Spring HATEOAS. Với Spring Boot, có thể dùng dependency do Spring Boot quản lý phiên bản:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-hateoas</artifactId>
</dependency>
~~~

Không nên trả trực tiếp JPA entity chỉ để tiết kiệm một lớp chuyển đổi. Entity có thể chứa trường nội bộ, quan hệ lazy, vòng tham chiếu hoặc chi tiết persistence không thuộc hợp đồng API. DTO giúp kiểm soát dữ liệu công khai và cho phép thay đổi mô hình lưu trữ mà không bắt client thay đổi theo.

## 5. Xây dựng liên kết bằng ánh xạ controller

Spring HATEOAS tích hợp với Spring MVC qua **WebMvcLinkBuilder**. Hai hàm thường dùng là:

- **linkTo(...)** tạo link builder từ thông tin ánh xạ controller hoặc một URI.
- **methodOn(...)** tạo lời gọi controller giả lập để Spring HATEOAS đọc metadata ánh xạ, từ đó xây dựng URI tương ứng. Lời gọi này không thực thi logic nghiệp vụ của controller.

Controller có thể trả về các mô hình đã được assembler chuẩn bị:

~~~java
import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.UUID;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@RestController
@RequestMapping("/orders")
public class OrderController {

    private final OrderService service;
    private final OrderModelAssembler assembler;

    public OrderController(OrderService service, OrderModelAssembler assembler) {
        this.service = service;
        this.assembler = assembler;
    }

    @GetMapping("/{id}")
    public EntityModel<OrderRepresentation> one(@PathVariable UUID id) {
        return assembler.toModel(service.findById(id));
    }

    @GetMapping
    public CollectionModel<EntityModel<OrderRepresentation>> all() {
        return assembler.toCollectionModel(service.findAll())
            .add(linkTo(methodOn(OrderController.class).all()).withSelfRel());
    }

    @PostMapping("/{id}/cancellation")
    public ResponseEntity<Void> cancel(@PathVariable UUID id) {
        service.cancel(id);
        return ResponseEntity.noContent().build();
    }
}
~~~

Đây là ví dụ cấu trúc; **Order**, **OrderService** và quy tắc xử lý lỗi thuộc phần nghiệp vụ của ứng dụng. Điểm quan trọng là controller trả về kiểu mô hình HATEOAS và assembler tập trung logic tạo biểu diễn.

Việc tạo link dựa trên phương thức controller giúp tránh lặp chuỗi URI trong nhiều nơi. Nếu mapping thay đổi, link được tạo từ metadata mapping sẽ đi theo cấu hình mới. Dù vậy, quan hệ link như **orders** hoặc **cancel** vẫn là một phần hợp đồng công khai; cần đặt tên có ý nghĩa và giữ ổn định để client có thể dựa vào chúng.

## 6. Biểu diễn HAL trong JSON

HAL (Hypertext Application Language) là định dạng hypermedia mà Spring HATEOAS hỗ trợ. Trong HAL JSON, các liên kết được đặt dưới **_links**; các tài nguyên được nhúng nằm dưới **_embedded**.

Một biểu diễn đơn hàng minh họa có thể như sau:

~~~json
{
  "id": "ORD-42",
  "status": "PROCESSING",
  "total": 125000,
  "_links": {
    "self": {
      "href": "/orders/ORD-42"
    },
    "orders": {
      "href": "/orders"
    },
    "cancel": {
      "href": "/orders/ORD-42/cancellation"
    }
  }
}
~~~

**self** cho biết URI của đơn hàng hiện tại. **orders** dẫn đến tập hợp đơn hàng. **cancel** công bố một đường dẫn hành động đang khả dụng theo trạng thái và chính sách truy cập tại thời điểm response được tạo.

Response tập hợp có thể chứa các phần tử được nhúng:

~~~json
{
  "_embedded": {
    "orders": [
      {
        "id": "ORD-42",
        "status": "PROCESSING",
        "total": 125000,
        "_links": {
          "self": {
            "href": "/orders/ORD-42"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "/orders"
    }
  }
}
~~~

Tên quan hệ trong **_embedded** phụ thuộc cấu hình relation provider hoặc metadata như **@Relation**. Vì vậy, nếu client cần dựa vào tên quan hệ, hãy công bố tên đó có chủ đích và kiểm thử nó như một phần hợp đồng API.

Trong ứng dụng Spring Boot có **spring-boot-starter-hateoas**, Spring HATEOAS cung cấp tích hợp chuyển đổi mô hình sang HAL. Client có thể yêu cầu media type **application/hal+json** qua content negotiation. Nếu API cần công bố rõ định dạng, controller có thể khai báo **produces = "application/hal+json"** cho endpoint tương ứng.

HAL giúp client tìm liên kết theo quan hệ thay vì phải biết cấu trúc URL của mọi endpoint. Tuy nhiên, HAL cơ bản chủ yếu mô tả liên kết và đích của liên kết; một đối tượng link thông thường không tự mô tả đầy đủ HTTP method, schema của request body hay các trường nhập liệu. Nếu client cần khám phá biểu mẫu hoặc chi tiết thao tác, hãy tìm hiểu affordance của Spring HATEOAS và định dạng hỗ trợ affordance như HAL-FORMS.

## 7. Liên kết phản ánh hành động khả dụng

Một đặc điểm quan trọng của hypermedia là tập liên kết có thể thay đổi theo trạng thái tài nguyên và quyền của người gọi.

Ví dụ, một đơn hàng đang xử lý có thể được hủy; đơn hàng đã giao thì không. Assembler nên áp dụng quy tắc nghiệp vụ để quyết định có đưa liên kết **cancel** vào biểu diễn hay không. Client quan sát liên kết để biết API đang công bố hành động đó.

Cách làm này có một số lợi ích:

- Client không phải tự tái hiện toàn bộ quy tắc chuyển trạng thái của máy chủ.
- Khi một hành động không khả dụng, API có thể không công bố liên kết tương ứng.
- Khi quy tắc thay đổi, máy chủ có thể điều chỉnh các liên kết mà không yêu cầu client ghép URL theo cấu trúc endpoint cũ.

Dù vậy, liên kết không thay thế kiểm tra quyền và kiểm tra trạng thái ở phía máy chủ. Client có thể giữ response cũ, tự tạo request hoặc gửi request sau khi trạng thái đã thay đổi. Endpoint thực thi hành động vẫn phải xác thực, phân quyền và kiểm tra điều kiện nghiệp vụ trước khi thay đổi dữ liệu.

Cũng cần phân biệt ý nghĩa của relation với HTTP method. Relation **cancel** mô tả quan hệ hoặc khả năng nghiệp vụ được công bố; nó không tự khẳng định request phải dùng **POST**, **PATCH** hay **DELETE**. Với HAL cơ bản, client cần biết semantics của thao tác từ hợp đồng API hoặc tài liệu đi kèm. Muốn mô tả thao tác có cấu trúc hơn, hãy dùng affordance phù hợp thay vì suy luận method từ tên relation.

## 8. Giữ hợp đồng biểu diễn có khả năng tiến hóa

HATEOAS hỗ trợ client khám phá API, nhưng không tự động làm cho mọi thay đổi đều tương thích ngược. Cần quản lý cả dữ liệu lẫn relation như hợp đồng công khai.

- **Giữ relation ổn định.** Tên **self**, **orders**, **customer** hoặc **cancel** nên phản ánh ý nghĩa nghiệp vụ, không phải tên method Java hay tên route nội bộ.
- **Không bắt client ghép URI.** Hãy cung cấp link cho quan hệ mà client cần đi tiếp. Client nên theo link từ response thay vì nối **/orders/** với mã đơn.
- **Thêm thông tin theo hướng tương thích.** Thêm trường hoặc link mới thường dễ tương thích hơn đổi tên hoặc xóa trường/link đang được client sử dụng.
- **Xử lý link tùy chọn.** Client cần hiểu rằng một link có thể không xuất hiện do trạng thái, quyền truy cập hoặc chính sách tại thời điểm truy vấn.
- **Không coi link là quyền thực thi.** Máy chủ phải kiểm tra lại mọi điều kiện khi nhận request.
- **Kiểm soát dữ liệu nhúng.** Chỉ nhúng phần dữ liệu cần thiết; nếu một tài nguyên có vòng đời hoặc quyền truy cập riêng, cân nhắc cung cấp link đến tài nguyên đó.

Ví dụ, nếu API đổi đường dẫn chi tiết từ **/orders/{id}** sang một cấu trúc khác, client tuân theo relation **self** có thể tiếp tục khám phá URI mới từ response. Client phụ thuộc vào chuỗi URL cũ sẽ phải cập nhật. Đó là giá trị thực tế của việc để server công bố các đường đi qua hypermedia.

## 9. Kiểm thử nội dung và liên kết

Kiểm thử endpoint HATEOAS nên xác nhận cả dữ liệu lẫn cấu trúc liên kết. Chỉ kiểm tra status HTTP hoặc một vài trường DTO là chưa đủ để bảo vệ hợp đồng hypermedia.

Ví dụ với MockMvc:

~~~java
mockMvc.perform(get("/orders/{id}", orderId)
        .accept("application/hal+json"))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith("application/hal+json"))
    .andExpect(jsonPath("$.id").value(orderId.toString()))
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.orders.href").exists())
    .andExpect(jsonPath("$._links.cancel.href").exists());
~~~

Với đơn hàng không thể hủy, kiểm tra rằng liên kết **cancel** không được công bố:

~~~java
mockMvc.perform(get("/orders/{id}", deliveredOrderId)
        .accept("application/hal+json"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.cancel").doesNotExist());
~~~

Với endpoint tập hợp, kiểm tra liên kết **self**, cấu trúc **_embedded** và relation đã chọn cho phần tử. Nếu dùng phân trang, kiểm tra metadata và các liên kết điều hướng trong những trường hợp có trang trước hoặc trang tiếp theo.

Nên ưu tiên kiểm tra sự tồn tại và ý nghĩa của relation thay vì cố định toàn bộ URL tuyệt đối trong mọi test. Host, context path hoặc cấu hình proxy có thể làm thay đổi phần đầu của URL. Khi cần xác minh URI cụ thể, hãy kiểm tra phần đường dẫn theo cấu hình test phù hợp.

## 10. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Trả thẳng JPA entity | Lộ dữ liệu nội bộ, dễ gặp vấn đề lazy loading và vòng tham chiếu | Tạo DTO/representation riêng |
| Tự nối chuỗi URL | Client và server phụ thuộc vào cấu trúc route | Tạo link từ controller mapping hoặc URI builder |
| Chỉ gắn link cho tài nguyên đơn | Client khó quay lại tập hợp hoặc khám phá quan hệ | Cân nhắc link **self** cho cả tài nguyên và tập hợp, cùng các link liên quan |
| Công bố mọi hành động ở mọi trạng thái | Client thấy hành động không còn hợp lệ | Chỉ đưa link khi quy tắc nghiệp vụ và quyền cho phép |
| Dùng tên method làm relation | Hợp đồng API phụ thuộc cách đặt tên mã nguồn | Dùng relation ổn định theo ngôn ngữ nghiệp vụ |
| Nghĩ link HAL đã mô tả HTTP method và request body | Client có thể gọi thao tác sai cách | Dùng hợp đồng hoặc affordance phù hợp để mô tả thao tác |

## 11. Quy trình áp dụng

Khi thêm một tài nguyên mới vào API Spring HATEOAS, có thể đi theo trình tự sau:

1. Xác định khái niệm nghiệp vụ, danh tính và URI của tài nguyên.
2. Chọn dữ liệu công khai cần có trong representation; không lấy toàn bộ entity làm response mặc định.
3. Chọn **EntityModel**, **CollectionModel** hoặc **PagedModel** theo hình dạng response.
4. Viết assembler để chuyển đổi dữ liệu và tạo các liên kết bằng controller mapping.
5. Quyết định relation nào luôn có và relation nào phụ thuộc trạng thái hoặc quyền.
6. Xác định media type mà API công bố, chẳng hạn HAL JSON.
7. Kiểm thử trường dữ liệu, relation, cấu trúc **_embedded** và trường hợp hành động không khả dụng.

Khi thực hiện nhất quán, mỗi response trở thành một điểm khám phá của API: client đọc biểu diễn để hiểu trạng thái tài nguyên, theo các liên kết để tìm tài nguyên liên quan và nhận biết những hành động mà máy chủ đang công bố. Đây là nền tảng để các bài tiếp theo đi sâu vào xây dựng link, tích hợp controller, HAL và kiểm thử khả năng tiến hóa của hợp đồng REST.


# Khai báo controller class

Trong Spring HATEOAS, `RepresentationModelAssemblerSupport<T, D>` là lớp hỗ trợ xây dựng representation model cho ứng dụng Spring MVC. Khi kế thừa lớp này, assembler khai báo controller class và kiểu model tài nguyên trong constructor. Hai thông tin đó giúp Spring HATEOAS tạo model và xây dựng self link dựa trên mapping của controller.

Tham số controller class thường là lớp controller có mapping cơ sở của tài nguyên, ví dụ `OrderController.class`. Tham số resource type là lớp representation cần được khởi tạo, ví dụ `OrderModel.class`. Việc khai báo đúng controller class giúp link do assembler tạo ra bám theo cấu trúc URI của API, đồng thời giữ phần ánh xạ dữ liệu ở một nơi tập trung.

Bài học này tập trung vào ý nghĩa của controller class trong `RepresentationModelAssemblerSupport`, cách khai báo constructor, cách `createModelWithId` sử dụng mapping, cách xử lý controller có path variable ở cấp lớp, các giới hạn của cách tạo self link mặc định và cách kiểm thử link được tạo ra.

## 1. Vì sao assembler cần controller class?

Một representation model thường chứa dữ liệu công khai và link đến tài nguyên. Với tài nguyên đơn, link `self` cần trỏ đến URI của chính tài nguyên đó.

Ví dụ, controller quản lý đơn hàng có mapping:

~~~java
@RestController
@RequestMapping("/orders")
public class OrderController {

    @GetMapping("/{id}")
    public EntityModel<OrderRepresentation> one(@PathVariable UUID id) {
        // Trả về một đơn hàng
    }

    @GetMapping
    public CollectionModel<EntityModel<OrderRepresentation>> all() {
        // Trả về tập hợp đơn hàng
    }
}
~~~

Đường dẫn cơ sở của tài nguyên là `/orders`; một đơn hàng cụ thể có URI dạng `/orders/{id}`. Khi assembler biết `OrderController.class`, Spring HATEOAS có thể đọc mapping cấp lớp để xây dựng link gắn với tài nguyên này.

Nếu tự viết chuỗi URI trong assembler:

~~~java
Link self = Link.of("/orders/" + order.getId(), "self");
~~~

assembler bị gắn chặt với route hiện tại. Khi prefix thay đổi thành `/api/orders`, các chuỗi URL phải được tìm và cập nhật. Việc tạo link từ controller class giúp tái sử dụng metadata mapping của Spring MVC.

## 2. Khai báo RepresentationModelAssemblerSupport

Lớp `RepresentationModelAssemblerSupport<T, D>` nằm trong package `org.springframework.hateoas.server.mvc`. Hai tham số generic:

- `T`: kiểu đối tượng nguồn, thường là entity hoặc domain object.
- `D`: kiểu representation đầu ra, phải kế thừa `RepresentationModel<?>`.

Constructor nhận controller class và resource type:

~~~java
protected RepresentationModelAssemblerSupport(
    Class<?> controllerClass,
    Class<D> resourceType
)
~~~

Ví dụ khai báo assembler cho đơn hàng:

~~~java
import org.springframework.hateoas.server.mvc.RepresentationModelAssemblerSupport;
import org.springframework.stereotype.Component;

@Component
public class OrderModelAssembler
        extends RepresentationModelAssemblerSupport<Order, OrderModel> {

    public OrderModelAssembler() {
        super(OrderController.class, OrderModel.class);
    }

    @Override
    public OrderModel toModel(Order order) {
        OrderModel model = createModelWithId(order.getId(), order);

        model.setId(order.getId());
        model.setStatus(order.getStatus());
        model.setTotal(order.getTotal());

        return model;
    }
}
~~~

Trong lời gọi:

~~~java
super(OrderController.class, OrderModel.class);
~~~

- `OrderController.class` cho assembler biết controller chứa mapping của tài nguyên.
- `OrderModel.class` cho assembler biết kiểu representation cần tạo.

Đây là hai metadata class được truyền vào constructor. Assembler không tạo một controller mới, không gọi constructor của controller và không chạy handler method khi khởi tạo. Controller class được dùng để tra cứu mapping; resource type được dùng để khởi tạo model.

## 3. Controller class và resource type đảm nhiệm hai vai trò khác nhau

Hai tham số constructor thường được khai báo cạnh nhau nên dễ bị nhầm:

| Tham số | Ví dụ | Vai trò |
|---|---|---|
| Controller class | `OrderController.class` | Cung cấp mapping để tạo URI |
| Resource type | `OrderModel.class` | Cung cấp kiểu model mà assembler trả về |

Controller class thường là lớp có `@RestController` hoặc `@Controller` và mapping Spring MVC. Resource type là một lớp biểu diễn kế thừa `RepresentationModel`.

Ví dụ model:

~~~java
import org.springframework.hateoas.RepresentationModel;

import java.math.BigDecimal;
import java.util.UUID;

public class OrderModel extends RepresentationModel<OrderModel> {

    private UUID id;
    private String status;
    private BigDecimal total;

    public OrderModel() {
    }

    public UUID getId() {
        return id;
    }

    public void setId(UUID id) {
        this.id = id;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public BigDecimal getTotal() {
        return total;
    }

    public void setTotal(BigDecimal total) {
        this.total = total;
    }
}
~~~

`OrderModel` là resource type; nó không phải controller. Ngược lại, `OrderController` không phải kiểu nội dung response mà assembler khởi tạo.

Nếu truyền nhầm hai class hoặc dùng một class không có mapping phù hợp, link được tạo có thể không đúng URI mong muốn hoặc model không thể được khởi tạo.

## 4. Mapping cấp lớp quyết định đường dẫn cơ sở

`RepresentationModelAssemblerSupport` dùng controller class để xây dựng link đến tài nguyên. Vì vậy, hãy truyền đúng controller sở hữu mapping cơ sở của resource.

Ví dụ:

~~~java
@RestController
@RequestMapping("/api/v1/orders")
public class OrderController {

    @GetMapping("/{id}")
    public EntityModel<OrderRepresentation> one(@PathVariable UUID id) {
        // ...
    }
}
~~~

Khai báo assembler:

~~~java
public OrderModelAssembler() {
    super(OrderController.class, OrderModel.class);
}
~~~

Khi tạo model với ID `ORD-42`, self link được xây dựng dựa trên mapping controller và ID đó, tương ứng đường dẫn tài nguyên `/api/v1/orders/ORD-42` trong cấu hình này.

Nếu thay mapping cấp lớp từ `/api/v1/orders` thành `/api/orders`, link được tạo dựa trên controller class sẽ phản ánh mapping mới. Điều này giảm việc lặp chuỗi URL trong assembler.

Không nên truyền một controller khác chỉ vì nó có endpoint trùng đường dẫn ở thời điểm hiện tại. Chọn controller thực sự sở hữu tài nguyên để mapping và ngữ nghĩa của link không bị lệch khi hệ thống phát triển.

## 5. createModelWithId() dùng controller class như thế nào?

Phương thức `createModelWithId(...)` là helper quan trọng của `RepresentationModelAssemblerSupport`. Nó tạo một instance của resource type và thêm self link dựa trên controller class đã khai báo.

Cách dùng phổ biến:

~~~java
@Override
public OrderModel toModel(Order order) {
    OrderModel model = createModelWithId(order.getId(), order);

    model.setId(order.getId());
    model.setStatus(order.getStatus());
    model.setTotal(order.getTotal());

    return model;
}
~~~

Tham số đầu tiên là ID dùng để tạo đường dẫn đến tài nguyên. Tham số thứ hai là entity nguồn được chuyển cho quá trình khởi tạo model. Helper xây URI cơ sở từ mapping của controller class rồi thêm ID vào đường dẫn item; overload có tham số bổ sung dùng để giải quyết các path variable của mapping cấp lớp. Helper trả về một `OrderModel` đã có self link.

Điều này giúp tránh phải tự viết:

~~~java
model.add(
    linkTo(methodOn(OrderController.class).one(order.getId()))
        .withSelfRel()
);
~~~

Nếu chỉ cần self link theo cấu trúc resource chuẩn của controller, `createModelWithId` là cách ngắn gọn và nhất quán.

Lưu ý: helper không tự ánh xạ các trường nghiệp vụ từ entity sang model. Assembler vẫn cần gán ID, trạng thái, tổng tiền hoặc các trường công khai khác. Nó cũng không tự thêm link `orders`, `customer` hay `cancel`; các link quan hệ này cần được bổ sung riêng.

## 6. Controller có path variable ở cấp lớp

Một số API tổ chức tài nguyên lồng nhau. Ví dụ, đơn hàng thuộc về một khách hàng:

~~~java
@RestController
@RequestMapping("/customers/{customerId}/orders")
public class CustomerOrderController {

    @GetMapping("/{orderId}")
    public EntityModel<OrderRepresentation> one(
            @PathVariable UUID customerId,
            @PathVariable UUID orderId) {
        // ...
    }
}
~~~

Trong trường hợp này, mapping cơ sở của controller có path variable `customerId`; ID đơn hàng được nối sau phần đường dẫn collection. Khi tạo link, assembler phải cung cấp giá trị cần thiết để giải quyết mapping cấp lớp.

`RepresentationModelAssemblerSupport` có overload nhận các tham số bổ sung:

~~~java
createModelWithId(Object id, T entity, Object... parameters)
~~~

Ví dụ:

~~~java
@Override
public OrderModel toModel(Order order) {
    OrderModel model = createModelWithId(
        order.getId(),
        order,
        order.getCustomerId()
    );

    model.setId(order.getId());
    model.setStatus(order.getStatus());
    model.setTotal(order.getTotal());

    return model;
}
~~~

Trong ví dụ, `order.getId()` là ID tài nguyên được thêm vào đường dẫn; `order.getCustomerId()` là giá trị bổ sung để giải quyết path variable trong mapping controller. Thứ tự các giá trị bổ sung phải khớp với thứ tự placeholder của mapping cấp lớp theo quy tắc xây dựng URI.

Nếu controller có nhiều path variable ở cấp lớp, truyền đủ giá trị theo đúng thứ tự. Không để một placeholder chưa có giá trị, và không truyền ID đơn hàng vào vị trí customerId.

### 6.1. Phân biệt path variable cấp lớp và cấp phương thức

Hãy xác định rõ mapping nào thuộc controller và mapping nào thuộc handler:

~~~java
@RequestMapping("/customers/{customerId}/orders")
public class CustomerOrderController {

    @GetMapping("/{orderId}")
    public EntityModel<OrderRepresentation> one(
            @PathVariable UUID customerId,
            @PathVariable UUID orderId) {
        // ...
    }
}
~~~

- `customerId` nằm trong mapping cấp lớp.
- `orderId` là phần ID tài nguyên được thêm bởi `createModelWithId(orderId, ...)`.

Cấu trúc này phù hợp với helper mặc định: controller class cung cấp đường dẫn collection và ID được thêm để tạo đường dẫn item. Nếu URI item có cấu trúc khác, chẳng hạn có một segment bổ sung sau ID, hãy tự tạo self link từ handler method hoặc điều chỉnh cách xây dựng link thay vì giả định helper luôn ghép đúng.

## 7. Tài nguyên có URI không theo dạng collection/id

`createModelWithId` phù hợp nhất khi URI của item được hình thành từ mapping cơ sở của controller cộng với ID. Không phải API nào cũng dùng cấu trúc này.

Ví dụ một endpoint có mapping:

~~~java
@GetMapping("/by-number/{number}")
public EntityModel<OrderRepresentation> byNumber(
        @PathVariable String number) {
    // ...
}
~~~

Nếu mapping cơ sở của controller là `/orders`, URI thực tế là `/orders/by-number/{number}`, không phải `/orders/{id}`. Khi đó, không nên dùng `createModelWithId` với giả định nó sẽ tự tìm mọi handler method và suy luận segment `by-number`.

Có thể tạo self link trực tiếp từ handler mapping:

~~~java
Link self = linkTo(
    methodOn(OrderController.class).byNumber(order.getNumber())
).withSelfRel();

OrderModel model = instantiateModel(order);
model.add(self);
~~~

Cách này cho phép URI phản ánh chính xác handler method. Nếu ứng dụng thường xuyên có cấu trúc URI tùy biến, hãy cân nhắc dùng `RepresentationModelAssembler` thông thường để kiểm soát link rõ ràng hoặc tùy chỉnh cơ chế tạo link của assembler support.

Nguyên tắc là chọn helper theo hình dạng URI thực tế. Đừng ép cấu trúc endpoint khác biệt vào quy ước collection/id chỉ để dùng được một phương thức tiện ích.

## 8. Khởi tạo resource type

Constructor `RepresentationModelAssemblerSupport` nhận `Class<D> resourceType` để tạo representation model. Cơ chế mặc định khởi tạo resource type bằng reflection; vì vậy model thường cần constructor không tham số có thể truy cập được.

Ví dụ:

~~~java
public class OrderModel extends RepresentationModel<OrderModel> {

    public OrderModel() {
    }

    // getters và setters
}
~~~

Nếu model không có constructor không tham số hoặc cần nhận tham số bắt buộc, có thể override `instantiateModel(T entity)` trong assembler:

~~~java
@Override
protected OrderModel instantiateModel(Order order) {
    return new OrderModel(
        order.getId(),
        order.getStatus(),
        order.getTotal()
    );
}
~~~

Ví dụ này giả định `OrderModel` có constructor tương ứng. Khi đã tự khởi tạo model, không cần tạo instance thứ hai trong `toModel`; hãy dùng model được tạo trong quá trình triển khai.

Cần phân biệt `instantiateModel` với `createModelWithId`:

- `instantiateModel(entity)` tạo model từ đối tượng nguồn.
- `createModelWithId(id, entity, ...)` tạo model và gắn self link theo controller mapping.

Nếu override `instantiateModel`, helper `createModelWithId` có thể sử dụng cách khởi tạo tùy chỉnh đó.

## 9. Thêm link khác ngoài self

Controller class trong constructor chỉ phục vụ cơ chế tạo link tài nguyên của assembler support. Nó không tự xác định mọi quan hệ hypermedia mà API cần.

Ví dụ assembler hoàn chỉnh:

~~~java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.server.mvc.RepresentationModelAssemblerSupport;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
public class OrderModelAssembler
        extends RepresentationModelAssemblerSupport<Order, OrderModel> {

    public OrderModelAssembler() {
        super(OrderController.class, OrderModel.class);
    }

    @Override
    public OrderModel toModel(Order order) {
        OrderModel model = createModelWithId(order.getId(), order);

        model.setId(order.getId());
        model.setStatus(order.getStatus());
        model.setTotal(order.getTotal());

        Link collection = linkTo(
            methodOn(OrderController.class).all()
        ).withRel("orders");

        model.add(collection);

        if (order.canCancel()) {
            model.add(
                linkTo(methodOn(OrderController.class)
                    .cancel(order.getId()))
                    .withRel("cancel")
            );
        }

        return model;
    }
}
~~~

Self link được tạo bởi `createModelWithId`; link `orders` và `cancel` được tạo riêng. Cách tách này làm rõ phần link nào thuộc cơ chế mặc định của assembler support và phần nào là quy tắc nghiệp vụ của ứng dụng.

Nếu relation `cancel` chỉ khả dụng ở một số trạng thái, assembler kiểm tra điều kiện trước khi thêm. Endpoint cancel vẫn phải kiểm tra lại quyền và trạng thái khi nhận request; sự hiện diện của link không thay thế xác thực hoặc phân quyền.

## 10. Khai báo controller class khi dùng nhiều controller

Một resource type thường có một controller sở hữu URI item chính. Nếu nhiều controller cùng thao tác trên một loại entity, hãy chọn controller phù hợp với canonical URI của representation.

Ví dụ:

- `OrderController` cung cấp URI chuẩn cho một đơn hàng.
- `OrderAdminController` cung cấp endpoint quản trị.
- `OrderReportController` cung cấp endpoint báo cáo hoặc thống kê.

Nếu representation của đơn hàng được dùng trong cả API khách hàng và API quản trị, cần quyết định link self nên trỏ đến URI canonical nào trong từng ngữ cảnh. Không nên dùng một assembler chung với controller class tùy tiện rồi mong self link phù hợp cho mọi use case.

Có thể tạo các assembler riêng nếu mỗi API có hợp đồng hoặc base URI khác nhau. Hoặc dùng assembler thông thường và tạo self link theo handler method phù hợp với ngữ cảnh. Điều quan trọng là self link phải nhận diện đúng tài nguyên mà representation đang mô tả.

## 11. Link collection không tự động được tạo từ controller class

`RepresentationModelAssemblerSupport` hỗ trợ tạo self link cho từng model được tạo từ `createModelWithId`. Điều đó không có nghĩa link cấp collection cũng tự động xuất hiện.

Khi controller trả tập hợp:

~~~java
@GetMapping
public CollectionModel<OrderModel> all() {
    List<Order> orders = service.findAll();

    return assembler.toCollectionModel(orders)
        .add(linkTo(methodOn(OrderController.class).all())
            .withSelfRel());
}
~~~

Mỗi `OrderModel` được tạo qua `toModel` và có self link riêng. `CollectionModel` vẫn cần link self ở cấp tập hợp nếu hợp đồng yêu cầu.

Với phân trang, link `next`, `prev`, `first` và `last` cần được tạo từ trạng thái phân trang thực tế. Việc khai báo controller class trong assembler support không tự suy ra metadata trang hoặc link điều hướng.

## 12. Kiểm thử controller class và self link

Nên kiểm thử cả cách assembler tạo model và response HTTP cuối cùng. Với unit test dùng `WebMvcLinkBuilder`, cần có request context để tạo URI phù hợp.

Ví dụ thiết lập request context:

~~~java
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

MockHttpServletRequest request =
    new MockHttpServletRequest("GET", "/orders");

request.setScheme("https");
request.setServerName("api.example.test");
request.setServerPort(443);

RequestContextHolder.setRequestAttributes(
    new ServletRequestAttributes(request)
);

try {
    OrderModel model = assembler.toModel(order);

    assertThat(model.hasLink(IanaLinkRelations.SELF)).isTrue();
    assertThat(model.getRequiredLink(IanaLinkRelations.SELF).getHref())
        .endsWith("/orders/" + order.getId());
} finally {
    RequestContextHolder.resetRequestAttributes();
}
~~~

Test xác nhận controller class được khai báo đúng và helper tạo self link với ID tài nguyên. Luôn reset request attributes trong `finally` để tránh rò rỉ context sang test khác.

Có thể thêm integration test với MockMvc:

~~~java
mockMvc.perform(get("/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$._links.self.href")
        .value(org.hamcrest.Matchers.endsWith("/orders/" + orderId)));
~~~

Integration test xác nhận controller mapping, assembler, serializer và content negotiation phối hợp. Không nên khóa cứng host hoặc port trong test thông thường nếu chúng phụ thuộc môi trường; kiểm tra path và tạo test riêng cho base URI khi cần.

Với controller có mapping lồng nhau, cần có test truyền đúng các tham số bổ sung vào `createModelWithId` và xác nhận self link chứa đủ path variable.

## 13. Những lỗi thường gặp khi khai báo controller class

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Truyền resource model thay cho controller class | Không có mapping controller phù hợp để tạo link | Truyền class controller sở hữu tài nguyên |
| Truyền nhầm controller quản trị hoặc báo cáo | Self link trỏ đến sai ngữ cảnh API | Chọn controller canonical cho representation |
| Không có mapping cơ sở phù hợp | URI do helper tạo không khớp endpoint item | Kiểm tra `@RequestMapping` ở cấp lớp |
| Giả định helper hiểu mọi cấu trúc route | Self link sai khi item URI có segment tùy chỉnh | Dùng link từ handler method hoặc tùy chỉnh cách tạo |
| Quên tham số path ở cấp lớp | URI template không được giải quyết đầy đủ | Dùng overload có tham số bổ sung |
| Resource type không thể khởi tạo | Assembler không tạo được model | Thêm constructor phù hợp hoặc override `instantiateModel` |
| Nghĩ createModelWithId tự ánh xạ field | Model có self link nhưng thiếu dữ liệu | Gán các trường trong `toModel` |
| Nghĩ controller class tự thêm mọi relation | Response thiếu link collection hoặc hành động | Thêm relation nghiệp vụ riêng |
| Không kiểm thử request context | URI tuyệt đối có thể khác dự kiến | Dùng MockMvc hoặc thiết lập request context |

## 14. Quy trình khai báo assembler support

Khi tạo assembler dựa trên `RepresentationModelAssemblerSupport`, hãy thực hiện theo trình tự:

1. Xác định controller sở hữu mapping canonical của tài nguyên.
2. Xác định resource type cần trả về và bảo đảm nó kế thừa `RepresentationModel`.
3. Kế thừa `RepresentationModelAssemblerSupport<T, D>` với đúng kiểu nguồn và kiểu model.
4. Gọi `super(Controller.class, ResourceModel.class)` trong constructor.
5. Triển khai `toModel(T)` và gọi `createModelWithId(id, entity)` để tạo model có self link.
6. Ánh xạ các trường dữ liệu công khai vào model.
7. Thêm link collection, link quan hệ và link hành động theo hợp đồng API.
8. Với mapping lồng nhau, truyền các giá trị path bổ sung bằng overload phù hợp.
9. Nếu URI item không theo dạng mapping cơ sở cộng ID, tạo self link từ handler method hoặc điều chỉnh cơ chế tạo link.
10. Kiểm thử self link, relation, path variable và response HAL.

Controller class là metadata quan trọng để assembler support xây dựng link theo mapping của Spring MVC. Khi truyền đúng controller và resource type, `createModelWithId` giúp khởi tạo representation cùng self link nhất quán. Assembler vẫn chịu trách nhiệm ánh xạ dữ liệu và công bố các quan hệ nghiệp vụ còn lại, nhờ đó API có thể giữ hợp đồng hypermedia rõ ràng khi route và cấu trúc nội bộ thay đổi.

## Tài liệu tham khảo

- [Spring HATEOAS Reference Documentation – Representation model assembler](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [RepresentationModelAssemblerSupport API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/mvc/RepresentationModelAssemblerSupport.html)
- [RepresentationModelAssembler API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/RepresentationModelAssembler.html)
- [WebMvcLinkBuilder API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/mvc/WebMvcLinkBuilder.html)


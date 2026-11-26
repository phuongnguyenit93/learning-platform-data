# Path variable

Trong REST API, URI của một tài nguyên đơn lẻ thường chứa định danh ở phần path. Ví dụ, /api/orders/42 tham chiếu đến đơn hàng có mã 42; /api/orders/42/items/3 tham chiếu đến dòng hàng số 3 thuộc đơn hàng 42. Spring MVC nhận các đoạn định danh này bằng annotation PathVariable.

Khi dùng Spring HATEOAS, server cần tạo các liên kết đến tài nguyên dựa trên cùng mapping của controller. WebMvcLinkBuilder cung cấp linkTo(...) và methodOn(...) để xây URI từ phương thức controller. Cách này giúp link được tạo theo mapping thực tế, bao gồm đường dẫn cấp lớp, đường dẫn cấp phương thức và giá trị path variable.

Bài học này tập trung vào cách tạo link cho một hoặc nhiều path variable, cách kết hợp RequestMapping với GetMapping, cách dùng link builder trong assembler và cách kiểm thử URI được sinh ra.

## 1. Path variable trong REST và Spring MVC

Path variable là một phần của path trong URI, thường dùng để nhận diện tài nguyên. Ví dụ:

~~~http
GET /api/orders/42
~~~

Trong controller, đoạn 42 được ánh xạ vào tham số:

~~~java
@GetMapping("/{orderId}")
public OrderDto one(@PathVariable("orderId") Long orderId) {
    return orderService.getRequired(orderId);
}
~~~

@PathVariable("orderId") yêu cầu Spring MVC lấy giá trị từ biến orderId trong mapping và chuyển đổi sang kiểu Long. Tên trong annotation phải khớp với placeholder của đường dẫn. Có thể bỏ tên trong annotation nếu tên tham số Java được giữ và có thể khám phá tại runtime, nhưng khai báo tường minh thường giúp mapping dễ đọc và ít phụ thuộc cấu hình biên dịch.

Một controller thường kết hợp mapping ở cấp lớp và cấp phương thức:

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @GetMapping("/{orderId}")
    public OrderDto one(
            @PathVariable("orderId") Long orderId
    ) {
        return orderService.getRequired(orderId);
    }
}
~~~

Spring kết hợp hai mapping thành đường dẫn /api/orders/{orderId}. Khi client gọi /api/orders/42, tham số orderId nhận giá trị 42.

## 2. Vì sao link nên được tạo từ mapping của controller?

Nếu assembler tự nối chuỗi:

~~~java
String href = "/api/orders/" + orderId;
~~~

thì đường dẫn bị lặp lại ở nhiều nơi. Khi endpoint đổi từ /api/orders/{orderId} thành /api/purchases/{orderId}, các chuỗi cũ trong assembler có thể không được cập nhật. Tương tự, nếu controller có context path hoặc mapping cấp lớp khác nhau theo cấu hình, chuỗi tự ghép có thể không còn chính xác.

Spring HATEOAS cho phép tham chiếu trực tiếp phương thức controller để lấy mapping. Khi mapping thay đổi, link builder sử dụng mapping mới mà không cần sao chép lại đường dẫn trong assembler.

Hai phương thức thường dùng:

| Phương thức | Vai trò |
| --- | --- |
| linkTo(...) | Tạo builder từ controller, phương thức controller hoặc URI đã xác định |
| methodOn(...) | Tạo proxy để tham chiếu lời gọi phương thức controller và các tham số của nó |

Với path variable, mẫu phổ biến là:

~~~java
linkTo(methodOn(OrderController.class)
        .one(orderId))
        .withSelfRel();
~~~

methodOn(OrderController.class) tạo proxy tham chiếu đến controller. Lời gọi .one(orderId) cung cấp phương thức và giá trị tham số để Spring HATEOAS xác định mapping. linkTo(...) tạo link builder từ thông tin đó; withSelfRel() gắn quan hệ self cho link.

Lời gọi phương thức trên proxy không thực thi logic nghiệp vụ của controller. Nó được dùng để xác định mapping và tham số đường dẫn.

## 3. Tạo link cho một path variable

Giả sử controller có endpoint chi tiết:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @GetMapping("/{orderId}")
    public EntityModel<OrderDto> one(
            @PathVariable("orderId") Long orderId
    ) {
        Order order = orderService.getRequired(orderId);
        return orderAssembler.toModel(order);
    }
}
~~~

Assembler tạo link self:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.stereotype.Component;

@Component
public class OrderModelAssembler {

    public EntityModel<OrderDto> toModel(Order order) {
        OrderDto dto = new OrderDto(
                order.id(),
                order.status(),
                order.total()
        );

        return EntityModel.of(
                dto,
                linkTo(methodOn(OrderController.class)
                        .one(order.id())).withSelfRel()
        );
    }
}
~~~

Nếu order.id() bằng 42, link được tạo sẽ trỏ đến /api/orders/42 trên origin của request hiện tại. Khi HAL được cấu hình, response có thể chứa:

~~~json
{
  "id": 42,
  "status": "PENDING",
  "total": 1250000,
  "_links": {
    "self": {
      "href": "https://api.example.com/api/orders/42"
    }
  }
}
~~~

Địa chỉ tuyệt đối trong ví dụ phụ thuộc vào request, cấu hình ứng dụng và proxy phía trước. Không nên hard-code hostname vào assembler.

## 4. Kết hợp nhiều path variable

Một endpoint có thể chứa nhiều biến đường dẫn. Ví dụ:

~~~java
@GetMapping("/{orderId}/items/{itemId}")
public EntityModel<OrderItemDto> item(
        @PathVariable("orderId") Long orderId,
        @PathVariable("itemId") Long itemId
) {
    OrderItem item = orderService.getItem(orderId, itemId);
    return itemAssembler.toModel(item);
}
~~~

Mapping đầy đủ là /api/orders/{orderId}/items/{itemId}. Để tạo link đến dòng hàng cụ thể, truyền cả hai giá trị cho phương thức controller:

~~~java
Link itemLink = linkTo(methodOn(OrderController.class)
        .item(order.id(), item.id()))
        .withSelfRel();
~~~

Nếu order.id() bằng 42 và item.id() bằng 3, URI kết quả tương ứng là:

~~~text
/api/orders/42/items/3
~~~

Thứ tự đối số truyền vào methodOn(...).item(...) phải khớp với thứ tự tham số của phương thức Java. Tên biến trong @PathVariable xác định placeholder mà Spring MVC ánh xạ; vị trí đối số xác định giá trị truyền cho từng tham số khi link builder dựng URI.

Khi phương thức có nhiều path variable, nên dùng tên annotation tường minh:

~~~java
@GetMapping("/{customerId}/orders/{orderId}")
public EntityModel<OrderDto> customerOrder(
        @PathVariable("customerId") Long customerId,
        @PathVariable("orderId") Long orderId
) {
    // Xử lý yêu cầu.
}
~~~

Điều này giúp tránh nhầm lẫn giữa các placeholder có kiểu dữ liệu giống nhau.

## 5. Tổ chức controller và assembler hoàn chỉnh

Ví dụ dưới đây kết hợp endpoint đơn hàng, collection dòng hàng và endpoint chi tiết dòng hàng:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService orderService;
    private final OrderModelAssembler orderAssembler;
    private final OrderItemModelAssembler itemAssembler;

    public OrderController(
            OrderService orderService,
            OrderModelAssembler orderAssembler,
            OrderItemModelAssembler itemAssembler
    ) {
        this.orderService = orderService;
        this.orderAssembler = orderAssembler;
        this.itemAssembler = itemAssembler;
    }

    @GetMapping(value = "/{orderId}", produces = MediaTypes.HAL_JSON_VALUE)
    public EntityModel<OrderDto> one(
            @PathVariable("orderId") Long orderId
    ) {
        return orderAssembler.toModel(
                orderService.getRequired(orderId)
        );
    }

    @GetMapping(
            value = "/{orderId}/items",
            produces = MediaTypes.HAL_JSON_VALUE
    )
    public CollectionModel<EntityModel<OrderItemDto>> items(
            @PathVariable("orderId") Long orderId
    ) {
        return itemAssembler.toCollectionModel(
                orderService.findItems(orderId)
        ).add(
                linkTo(methodOn(OrderController.class)
                        .items(orderId)).withSelfRel(),
                linkTo(methodOn(OrderController.class)
                        .one(orderId)).withRel("order")
        );
    }

    @GetMapping(
            value = "/{orderId}/items/{itemId}",
            produces = MediaTypes.HAL_JSON_VALUE
    )
    public EntityModel<OrderItemDto> item(
            @PathVariable("orderId") Long orderId,
            @PathVariable("itemId") Long itemId
    ) {
        return itemAssembler.toModel(
                orderService.getItem(orderId, itemId)
        );
    }
}
~~~

Assembler của dòng hàng có thể tạo các liên kết:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.stereotype.Component;

@Component
public class OrderItemModelAssembler {

    public EntityModel<OrderItemDto> toModel(OrderItem item) {
        OrderItemDto dto = new OrderItemDto(
                item.id(),
                item.productName(),
                item.quantity()
        );

        return EntityModel.of(
                dto,
                linkTo(methodOn(OrderController.class)
                        .item(item.orderId(), item.id())).withSelfRel(),
                linkTo(methodOn(OrderController.class)
                        .one(item.orderId())).withRel("order")
        );
    }
}
~~~

Các kiểu Order, OrderItem, DTO, service và assembler được giả định đã được khai báo trong ứng dụng. Trong dự án Java, mỗi kiểu public được đặt trong file nguồn riêng. Ví dụ tập trung vào cách tạo link theo mapping và path variable.

Trong assembler, item.orderId() được truyền vào biến orderId, còn item.id() được truyền vào itemId. Link self trỏ đến dòng hàng; link order trỏ về đơn hàng cha. Client có thể điều hướng theo relation mà không cần tự ghép URI.

## 6. Tạo link với linkTo(Class).slash(...)

Với đường dẫn đơn giản, Spring HATEOAS cũng cho phép tạo builder từ controller class rồi nối thêm một path segment:

~~~java
Link orderLink = linkTo(OrderController.class)
        .slash(order.id())
        .withSelfRel();
~~~

Nếu controller có @RequestMapping("/api/orders"), link trên tạo URI dựa trên mapping cấp lớp rồi thêm mã đơn hàng. Cách này ngắn gọn khi chỉ cần thêm một đoạn path vào mapping gốc.

So sánh hai cách:

| Cách tạo | Điểm mạnh | Khi nên dùng |
| --- | --- | --- |
| linkTo(methodOn(...).one(id)) | Theo mapping cụ thể của phương thức, gồm cả path variable | Endpoint có mapping rõ ràng hoặc nhiều biến |
| linkTo(Controller.class).slash(id) | Ngắn gọn, thêm segment vào mapping cấp lớp | Đường dẫn đơn giản được xây từ base mapping |

Với endpoint có nhiều biến, mapping lồng nhau hoặc cần bám sát chữ ký phương thức, methodOn thường rõ ràng hơn. Cách slash không tự biết tham số nào thuộc endpoint nào; người viết chịu trách nhiệm bảo đảm thứ tự segment đúng với hợp đồng.

## 7. Path variable và query parameter là hai phần khác nhau

Path variable là thành phần của đường dẫn:

~~~text
/api/orders/42
~~~

Query parameter là dữ liệu sau dấu ?:

~~~text
/api/orders?status=PENDING&page=0
~~~

Trong Spring MVC, path variable dùng @PathVariable; query parameter dùng @RequestParam. Khi tạo link, methodOn có thể tham chiếu đến cả hai loại tham số theo mapping, nhưng cần xác định đúng tham số nào nằm trong path và tham số nào nằm trong query.

Ví dụ:

~~~java
import org.springframework.web.bind.annotation.RequestParam;

@GetMapping("/{orderId}/items")
public CollectionModel<EntityModel<OrderItemDto>> items(
        @PathVariable("orderId") Long orderId,
        @RequestParam(required = false) Integer page,
        @RequestParam(required = false) Integer size
) {
    // Trả collection dòng hàng theo trang.
}
~~~

Khi tạo link đến collection:

~~~java
Link itemsLink = linkTo(methodOn(OrderController.class)
        .items(orderId, null, null))
        .withRel("items");
~~~

Các giá trị null cho query parameter tùy chọn có thể được dùng để tạo link template trong các trường hợp phù hợp với cơ chế mapping và phiên bản Spring HATEOAS. Cần kiểm tra href và cờ templated trong response thực tế. Nếu chỉ muốn tạo link đến một trang cụ thể, truyền các giá trị page và size cụ thể.

## 8. Mã hóa giá trị path variable

Giá trị path variable có thể chứa ký tự cần mã hóa. Không nên nối chuỗi URI thủ công vì ký tự như /, ?, # hoặc % có thể làm thay đổi cấu trúc URI.

Khi dùng linkTo(methodOn(...)), Spring HATEOAS kết hợp mapping và giá trị tham số để dựng URI. Hãy truyền giá trị thô đúng kiểu dữ liệu và để cơ chế URI builder xử lý việc mở rộng, thay vì tự percent-encode trước rồi có nguy cơ mã hóa hai lần.

Với định danh số như Long, việc tạo link khá đơn giản. Nếu định danh là chuỗi có dấu cách hoặc ký tự Unicode, cần có kiểm thử cho giá trị thực tế và xác nhận URI được tạo có thể được phân tích đúng khi client theo liên kết.

Path variable cũng cần có quy tắc nghiệp vụ rõ ràng. Việc URI được tạo thành công không đảm bảo tài nguyên tồn tại. Service vẫn phải kiểm tra mã định danh và trả lỗi thích hợp nếu không tìm thấy tài nguyên.

## 9. Xử lý base path, context path và reverse proxy

Ứng dụng có thể chạy với context path, chẳng hạn /store, hoặc đứng sau reverse proxy với một host và scheme công khai khác với địa chỉ nội bộ. Link được tạo cần phản ánh địa chỉ mà client có thể truy cập.

Một số điểm cần cấu hình đúng:

- Mapping cấp lớp và cấp phương thức phải phản ánh endpoint thực tế.
- Context path của ứng dụng cần được tính vào URI khi framework tạo link.
- Nếu proxy thay đổi scheme, host hoặc prefix, ứng dụng cần xử lý forwarded headers theo cấu hình triển khai.
- Không cố định hostname và port trong assembler.

Ví dụ, ứng dụng nội bộ có thể lắng nghe HTTP trên một cổng riêng, trong khi client truy cập qua HTTPS tại api.example.com. Nếu forwarded headers không được xử lý đúng, link tuyệt đối có thể mang scheme hoặc host nội bộ. Cần kiểm thử link trong môi trường proxy tương ứng.

## 10. Kiểm thử link có path variable bằng MockMvc

Kiểm thử nên xác nhận endpoint nhận đúng path variable và link được tạo trỏ về đúng mapping.

Ví dụ:

~~~java
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(OrderController.class)
@Import(OrderModelAssembler.class)
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderService orderService;

    @Test
    void returnsSelfLinkUsingOrderPathVariable() throws Exception {
        Order order = new Order(42L, "PENDING", 1250000);
        when(orderService.getRequired(42L)).thenReturn(order);

        mockMvc.perform(get("/api/orders/42")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$.id").value(42))
                .andExpect(jsonPath("$._links.self.href")
                        .value(org.hamcrest.Matchers.endsWith(
                                "/api/orders/42"
                        )));
    }
}
~~~

Đây là ví dụ test slice. Các kiểu Order, OrderDto, OrderService, controller và assembler cần khớp với package của ứng dụng. @Import đăng ký assembler trong @WebMvcTest; service được mock để kiểm soát kết quả.

Với endpoint có hai path variable, nên kiểm tra cả hai giá trị trong link:

~~~java
mockMvc.perform(get("/api/orders/42/items/3")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href")
            .value(org.hamcrest.Matchers.endsWith(
                    "/api/orders/42/items/3"
            )));
~~~

Nên bổ sung các trường hợp:

- Path variable hợp lệ được chuyển đổi đúng kiểu dữ liệu.
- Giá trị không hợp lệ trả về lỗi chuyển đổi theo hợp đồng HTTP.
- Resource không tồn tại trả về 404 Not Found.
- Link self chứa đúng định danh của resource.
- Link quan hệ đến resource cha giữ đúng path variable của cha.
- Context path và forwarded headers tạo URI công khai đúng trong môi trường triển khai.

Ưu tiên kiểm tra phần path hoặc quan hệ link thay vì khóa toàn bộ hostname và cổng trong test. Host có thể khác giữa môi trường phát triển, kiểm thử và production.

## 11. Những lỗi thường gặp

**Tên placeholder không khớp @PathVariable.** Mapping dùng {orderId} nhưng annotation lại trỏ đến id có thể khiến Spring không ánh xạ được tham số. Hãy đặt tên tường minh và nhất quán.

**Truyền nhầm thứ tự biến cho methodOn.** Khi phương thức có nhiều path variable cùng kiểu, compiler không phát hiện việc đảo hai đối số. Hãy đối chiếu chữ ký phương thức và dùng tên tham số rõ nghĩa.

**Tự ghép chuỗi URL trong assembler.** Đường dẫn bị lặp lại và dễ lỗi khi mapping thay đổi. Dùng linkTo(methodOn(...)) để tạo link theo mapping.

**Dùng slash cho endpoint phức tạp mà không kiểm tra kết quả.** slash chỉ nối thêm segment vào builder. Với nhiều biến hoặc mapping lồng nhau, dùng methodOn để tham chiếu chính xác phương thức.

**Hard-code host hoặc context path.** Link có thể sai khi ứng dụng chạy sau proxy hoặc thay đổi môi trường. Dùng cơ chế tạo link theo request và cấu hình forwarded headers.

**Mã hóa giá trị trước khi đưa vào link builder.** Việc mã hóa hai lần có thể khiến định danh thay đổi. Truyền giá trị thô và để URI builder xử lý theo ngữ cảnh.

**Cho rằng link chứng minh tài nguyên tồn tại hoặc người dùng có quyền truy cập.** Link chỉ mô tả đích điều hướng. Service vẫn phải kiểm tra tồn tại, quyền và quy tắc nghiệp vụ khi nhận request.

## 12. Ghi nhớ

@PathVariable ánh xạ placeholder trong path của Spring MVC vào tham số phương thức. Spring HATEOAS dùng WebMvcLinkBuilder.linkTo(methodOn(Controller.class).method(pathValue)) để tạo liên kết dựa trên mapping controller và giá trị path variable. Với nhiều biến, truyền đủ giá trị theo đúng thứ tự tham số của phương thức.

linkTo(Controller.class).slash(id) là cách ngắn gọn để nối một segment vào mapping cấp lớp; với endpoint phức tạp, methodOn thường rõ ràng hơn vì tham chiếu trực tiếp đến phương thức và chữ ký của nó. Query parameter được xử lý bằng @RequestParam, khác với path variable, dù cả hai có thể tham gia tạo link.

Hãy giữ tên placeholder và annotation nhất quán, tránh tự ghép URI, kiểm soát encoding và cấu hình forwarded headers khi chạy sau proxy. Kiểm thử link self và các link quan hệ để xác nhận mọi path variable được đưa vào đúng vị trí và client có thể điều hướng theo URI mà server công bố.

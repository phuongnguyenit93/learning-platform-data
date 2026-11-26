# Tích hợp Spring MVC

Spring MVC xử lý yêu cầu HTTP thông qua controller, gọi tầng nghiệp vụ và chuyển kết quả thành phản hồi. Khi tích hợp Spring HATEOAS, controller có thể trả về các mô hình biểu diễn như EntityModel hoặc CollectionModel; các mô hình này chứa dữ liệu tài nguyên cùng liên kết hypermedia. Bộ chuyển đổi thông điệp của Spring MVC tuần tự hóa mô hình thành HAL hoặc media type hypermedia đã cấu hình.

Tích hợp đúng cách giúp controller tập trung vào giao thức HTTP, assembler chịu trách nhiệm xây dựng biểu diễn và service giữ quy tắc nghiệp vụ. Bài học này trình bày cách tổ chức các thành phần đó trong một API quản lý đơn hàng, cách xử lý tài nguyên đơn lẻ và tập hợp, cách tạo phản hồi khi thêm tài nguyên, cũng như cách kiểm thử các liên kết được công bố.

## 1. Spring MVC và Spring HATEOAS phối hợp

Trong một ứng dụng Spring Boot, dependency thường dùng là:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-hateoas</artifactId>
</dependency>
~~~

Starter tích hợp Spring HATEOAS với hệ sinh thái Spring. Với cấu hình Spring Boot thông thường, phần hỗ trợ hypermedia và HAL được tự động cấu hình. Nếu ứng dụng dùng Spring MVC thuần và tự quản lý cấu hình, cần đăng ký hỗ trợ hypermedia tương ứng, chẳng hạn HAL, bằng cấu hình Spring HATEOAS. Không nên thêm cấu hình thủ công trùng với cấu hình tự động đang hoạt động.

Luồng xử lý điển hình:

~~~mermaid
flowchart LR
    A["HTTP request"] --> B["DispatcherServlet"]
    B --> C["Spring MVC controller"]
    C --> D["Application service"]
    D --> C
    C --> E["Representation assembler"]
    E --> F["EntityModel / CollectionModel"]
    F --> G["HTTP message converter"]
    G --> H["HAL response"]
~~~

Controller nhận tham số từ URL, query string hoặc request body theo cơ chế Spring MVC. Controller gọi service để lấy hoặc thay đổi dữ liệu. Sau đó, assembler chuyển đối tượng nghiệp vụ thành mô hình biểu diễn có liên kết. Cuối cùng, message converter tuần tự hóa mô hình theo media type mà client yêu cầu và endpoint hỗ trợ.

Các vai trò nên được phân định rõ:

| Thành phần | Trách nhiệm |
| --- | --- |
| Controller | Ánh xạ endpoint, đọc đầu vào HTTP, chọn status code và trả mô hình biểu diễn |
| Service | Thực hiện nghiệp vụ, kiểm tra trạng thái và quyền theo ngữ cảnh ứng dụng |
| Representation assembler | Chuyển đối tượng nghiệp vụ hoặc DTO thành mô hình hypermedia |
| DTO | Xác định dữ liệu công khai của API, tránh phơi bày trực tiếp cấu trúc persistence |
| HTTP message converter | Tuần tự hóa mô hình thành HAL hoặc định dạng được cấu hình |

## 2. Chuẩn bị mô hình dữ liệu và DTO

Ví dụ sử dụng đơn hàng để minh họa. Đối tượng nghiệp vụ chứa dữ liệu mà service quản lý:

~~~java
import java.math.BigDecimal;

public record Order(
        Long id,
        String customerName,
        BigDecimal total,
        OrderStatus status
) {
}
~~~

Trạng thái đơn hàng:

~~~java
public enum OrderStatus {
    PENDING,
    PAID,
    CANCELLED
}
~~~

API có thể dùng một DTO riêng để quyết định trường nào được gửi cho client:

~~~java
import java.math.BigDecimal;

public record OrderDto(
        Long id,
        String customerName,
        BigDecimal total,
        OrderStatus status
) {
}
~~~

Đối với dữ liệu tạo mới, request DTO mô tả đầu vào và có thể dùng Jakarta Bean Validation:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;

import java.math.BigDecimal;

public record CreateOrderRequest(
        @NotBlank String customerName,
        @NotNull @Positive BigDecimal total
) {
}
~~~

Các kiểu trên là mô hình minh họa; ứng dụng thực tế có thể dùng class thay cho record và bổ sung trường theo nghiệp vụ. Điều quan trọng là lớp biểu diễn hypermedia được xây dựng từ dữ liệu đã chọn cho API. Không nên để việc tuần tự hóa entity persistence vô tình làm lộ quan hệ nội bộ, trường nhạy cảm hoặc cấu trúc cơ sở dữ liệu.

Giả sử OrderService cung cấp các thao tác nghiệp vụ sau:

~~~java
import java.util.List;

public interface OrderService {
    Order getRequired(Long id);
    List<Order> findAll();
    Order create(CreateOrderRequest request);
    void cancel(Long id);
}
~~~

Service cần chịu trách nhiệm xác nhận đơn hàng tồn tại, kiểm tra điều kiện hủy và áp dụng thay đổi. Việc có hay không có một liên kết trong phản hồi chỉ hỗ trợ client khám phá khả năng hiện tại; endpoint vẫn phải kiểm tra lại nghiệp vụ khi nhận yêu cầu.

## 3. Dùng RepresentationModelAssembler

Nếu controller tự chuyển từng đối tượng thành DTO và gắn liên kết, logic tạo biểu diễn sẽ lặp lại giữa endpoint chi tiết, danh sách và những nơi khác. Spring HATEOAS cung cấp RepresentationModelAssembler để gom quy tắc chuyển đổi vào một thành phần riêng.

Assembler cho đơn hàng:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

@Component
public class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderDto>> {

    @Override
    public EntityModel<OrderDto> toModel(Order order) {
        OrderDto dto = new OrderDto(
                order.id(),
                order.customerName(),
                order.total(),
                order.status()
        );

        EntityModel<OrderDto> model = EntityModel.of(
                dto,
                linkTo(methodOn(OrderController.class)
                        .one(order.id())).withSelfRel(),
                linkTo(methodOn(OrderController.class)
                        .all()).withRel("orders")
        );

        if (order.status() == OrderStatus.PENDING) {
            model.add(linkTo(methodOn(OrderController.class)
                    .cancel(order.id())).withRel("cancel"));
        }

        return model;
    }
}
~~~

RepresentationModelAssembler<Order, EntityModel<OrderDto>> cho biết assembler nhận Order và tạo ra EntityModel<OrderDto>. Phương thức toModel thực hiện hai việc: chuyển dữ liệu nghiệp vụ thành DTO và gắn các liên kết cần thiết.

linkTo(methodOn(OrderController.class).one(order.id())) tham chiếu đến phương thức controller để Spring HATEOAS tạo URI theo mapping đang khai báo. withSelfRel() gắn quan hệ self; withRel("orders") gắn quan hệ dẫn đến tập hợp. Cách tạo link theo phương thức giúp tránh lặp chuỗi URL trong assembler, đồng thời để mapping của controller là nguồn xác định đường dẫn.

Liên kết cancel chỉ được thêm khi trạng thái là PENDING. Quan hệ "orders" và "cancel" trong ví dụ là quan hệ do API quy ước; cần mô tả ý nghĩa và giữ ổn định trong hợp đồng. Với API công khai cần khả năng tái sử dụng rộng, có thể định danh quan hệ mở rộng bằng URI hoặc CURIE theo quy ước hypermedia của hệ thống.

Assembler không nên gọi repository hoặc tự thực hiện nghiệp vụ. Nó nhận dữ liệu đã được service chuẩn bị rồi chuyển dữ liệu đó thành biểu diễn. Nhờ vậy, quy tắc nghiệp vụ vẫn nằm trong service, còn quy tắc trình bày và điều hướng nằm ở assembler.

## 4. Tích hợp assembler vào controller

Controller nhận assembler qua dependency injection và trả về mô hình hypermedia. Ví dụ:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import java.net.URI;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import jakarta.validation.Valid;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService orderService;
    private final OrderModelAssembler assembler;

    public OrderController(
            OrderService orderService,
            OrderModelAssembler assembler
    ) {
        this.orderService = orderService;
        this.assembler = assembler;
    }

    @GetMapping(value = "/{id}", produces = MediaTypes.HAL_JSON_VALUE)
    public EntityModel<OrderDto> one(@PathVariable Long id) {
        Order order = orderService.getRequired(id);
        return assembler.toModel(order);
    }

    @GetMapping(produces = MediaTypes.HAL_JSON_VALUE)
    public CollectionModel<EntityModel<OrderDto>> all() {
        return assembler.toCollectionModel(orderService.findAll())
                .add(linkTo(methodOn(OrderController.class)
                        .all()).withSelfRel());
    }

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaTypes.HAL_JSON_VALUE
    )
    public ResponseEntity<EntityModel<OrderDto>> create(
            @Valid @RequestBody CreateOrderRequest request
    ) {
        Order created = orderService.create(request);
        EntityModel<OrderDto> body = assembler.toModel(created);

        URI location = linkTo(methodOn(OrderController.class)
                .one(created.id())).toUri();

        return ResponseEntity.created(location).body(body);
    }

    @DeleteMapping("/{id}/cancellation")
    public ResponseEntity<Void> cancel(@PathVariable Long id) {
        orderService.cancel(id);
        return ResponseEntity.noContent().build();
    }
}
~~~

@RestController kết hợp @RequestMapping định nghĩa controller và đường dẫn cơ sở. Các phương thức one và all công bố biểu diễn HAL; phương thức create nhận JSON và trả về biểu diễn của tài nguyên vừa tạo. Phương thức cancel thực hiện thao tác hủy và trả về HTTP 204 No Content.

### Tài nguyên đơn lẻ

one lấy đơn hàng từ service rồi chuyển nó qua assembler. Controller không cần tự dựng href hoặc lặp lại điều kiện tạo link. Kết quả là một EntityModel<OrderDto> có dữ liệu đơn hàng và các liên kết theo trạng thái.

Khi client gửi:

~~~http
GET /api/orders/42
Accept: application/hal+json
~~~

Spring MVC chọn handler phù hợp, gọi service và nhận EntityModel từ controller. Với hỗ trợ HAL đã được cấu hình, message converter chuyển mô hình thành phản hồi có _links cùng các trường DTO. Một phản hồi minh họa:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
~~~

~~~json
{
  "id": 42,
  "customerName": "Nguyen An",
  "total": 1250000,
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "https://api.example.com/api/orders/42"
    },
    "orders": {
      "href": "https://api.example.com/api/orders"
    },
    "cancel": {
      "href": "https://api.example.com/api/orders/42/cancellation"
    }
  }
}
~~~

Địa chỉ host trong phản hồi thực tế được tạo theo cấu hình request, proxy và môi trường triển khai. Ví dụ trên chỉ minh họa cấu trúc; không nên cố định hostname trong assembler.

### Tập hợp tài nguyên

all dùng toCollectionModel để chuyển danh sách đối tượng thành CollectionModel chứa các mô hình con. Mỗi phần tử được xử lý bởi cùng assembler nên có liên kết self và những liên kết nghiệp vụ phù hợp. Liên kết self được thêm ở cấp tập hợp để client có thể nhận diện URI của danh sách.

Không nên chỉ gắn link ở cấp collection rồi bỏ link ở từng phần tử nếu client cần mở chi tiết hoặc thực hiện thao tác với một tài nguyên cụ thể. Ngược lại, cũng không nên thêm mọi link nghiệp vụ vào mọi phần tử bất kể trạng thái; assembler nên phản ánh khả năng thực tế của từng tài nguyên.

### Tạo tài nguyên và phản hồi Location

Khi tạo đơn hàng, controller trả về 201 Created, header Location trỏ đến tài nguyên vừa tạo và body chứa biểu diễn hypermedia. linkTo(methodOn(...).one(created.id())).toUri() tạo URI theo mapping của endpoint chi tiết. Client có thể dùng header Location để mở tài nguyên và dùng các liên kết trong body để tiếp tục điều hướng.

Việc gắn liên kết vào body không thay thế các quy ước HTTP. Với thao tác tạo mới, status code và header Location vẫn cần phản ánh đúng kết quả xử lý. Với thao tác xóa hoặc hủy không trả nội dung, 204 No Content là một lựa chọn phù hợp khi nghiệp vụ hoàn tất thành công.

## 5. Phân trang khi dùng Spring Data

Với danh sách lớn, API thường nhận Pageable để xử lý page, size và sort. Khi tích hợp Spring Data Web, PagedResourcesAssembler có thể chuyển Page<T> thành PagedModel và tạo liên kết điều hướng trang.

Ví dụ thay cho endpoint danh sách không phân trang:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.hateoas.PagedModel;
import org.springframework.web.bind.annotation.GetMapping;

@GetMapping(produces = MediaTypes.HAL_JSON_VALUE)
public PagedModel<EntityModel<OrderDto>> all(
        Pageable pageable,
        PagedResourcesAssembler<Order> pagedAssembler
) {
    Page<Order> page = orderService.findAll(pageable);
    return pagedAssembler.toModel(page, assembler);
}
~~~

PagedResourcesAssembler dùng thông tin trang để tạo metadata và các liên kết như self, first, prev, next, last khi phù hợp. RepresentationModelAssembler vẫn chịu trách nhiệm chuyển từng Order thành EntityModel<OrderDto>. Cách phối hợp này giữ cùng quy tắc biểu diễn giữa endpoint danh sách và endpoint chi tiết.

Đoạn mã phân trang giả định OrderService có phương thức findAll(Pageable) trả về Page<Order> và ứng dụng đã tích hợp Spring Data Web. Nếu không dùng Spring Data, có thể tự xây dựng mô hình phân trang và liên kết điều hướng dựa trên hợp đồng API.

## 6. Thương lượng media type và cấu hình HAL

Hypermedia model chỉ là đối tượng Java trong controller. Để gửi phản hồi HAL, ứng dụng cần message converter và cấu hình hỗ trợ HAL. Trong ứng dụng Spring Boot dùng starter Spring HATEOAS, cấu hình tự động thường đã cung cấp phần tích hợp cần thiết.

Client nên gửi header Accept để nêu định dạng mong muốn:

~~~http
GET /api/orders/42
Accept: application/hal+json
~~~

Server trả Content-Type: application/hal+json khi endpoint hỗ trợ và thương lượng nội dung thành công. Thuộc tính produces = MediaTypes.HAL_JSON_VALUE trên mapping giúp công bố định dạng phản hồi của endpoint. Nếu client yêu cầu media type không được endpoint hỗ trợ, Spring MVC có thể trả 406 Not Acceptable.

Đối với request body, consumes xác định định dạng đầu vào mà endpoint chấp nhận. Ví dụ create nhận application/json, trong khi body phản hồi là HAL. Hai hướng thương lượng này độc lập: định dạng client gửi lên không bắt buộc phải giống định dạng server trả về.

Trong ứng dụng Spring MVC không dùng cấu hình tự động của Spring Boot, cần khai báo hỗ trợ hypermedia tương ứng bằng cơ chế cấu hình Spring HATEOAS, ví dụ @EnableHypermediaSupport với loại HAL. Cần kiểm tra phiên bản Spring HATEOAS đang dùng và cấu hình message converter hiện hữu trước khi thêm cấu hình mới.

## 7. Affordance và thao tác HTTP

Một link trong HAL cơ bản thường cho client biết quan hệ và URI đích. Chỉ từ href, client không thể suy ra chắc chắn endpoint yêu cầu GET, POST, PATCH hay DELETE, cũng không biết đầy đủ cấu trúc request body. Vì vậy, rel cancel trong ví dụ phải được hiểu theo hợp đồng API đã công bố.

Nếu client cần khám phá cách thực hiện thao tác, có thể dùng affordance của Spring HATEOAS và định dạng hỗ trợ mô tả phương thức, đầu vào, chẳng hạn HAL-FORMS. Khi thiết kế, cần xác định rõ:

- Quan hệ liên kết biểu thị hành động hoặc tài nguyên nào.
- Phương thức HTTP nào được hỗ trợ.
- Những trường đầu vào nào bắt buộc hoặc tùy chọn.
- Điều kiện nghiệp vụ nào làm thao tác khả dụng.
- Phản hồi thành công và lỗi có ý nghĩa gì.

Không nên xem sự xuất hiện của link như một cơ chế phân quyền. Client có thể giữ lại URI cũ hoặc gửi yêu cầu trực tiếp. Controller và service vẫn phải kiểm tra danh tính, quyền truy cập, trạng thái hiện tại và tính hợp lệ của dữ liệu trước khi thực hiện thao tác.

## 8. Xử lý lỗi trong ứng dụng Spring MVC

Việc controller trả EntityModel không làm thay đổi cơ chế xử lý lỗi chung của Spring MVC. Có thể tiếp tục dùng exception nghiệp vụ, ResponseStatusException hoặc @RestControllerAdvice để chuyển lỗi thành HTTP status và body phù hợp.

Ví dụ, khi không tìm thấy đơn hàng, service có thể phát sinh exception được ánh xạ thành 404 Not Found. Khi đơn hàng đã thanh toán và không thể hủy, ứng dụng có thể trả 409 Conflict. Khi đầu vào không hợp lệ, @Valid kết hợp Bean Validation giúp Spring MVC từ chối request không hợp lệ theo quy tắc đã cấu hình.

Nếu API cần body lỗi theo một định dạng cụ thể, hãy định nghĩa và kiểm thử hợp đồng lỗi riêng. Không nên giả định rằng body lỗi tự động có cấu trúc HAL giống biểu diễn tài nguyên thành công. Các liên kết trong phản hồi lỗi chỉ nên được thêm khi chúng có ý nghĩa điều hướng rõ ràng, chẳng hạn liên kết đến tài liệu hỗ trợ hoặc tài nguyên liên quan.

## 9. Kiểm thử tích hợp bằng MockMvc

Kiểm thử controller cần xác nhận status code, media type, dữ liệu DTO và các quan hệ hypermedia. Ví dụ kiểm tra endpoint chi tiết:

~~~java
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.math.BigDecimal;

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
    void returnsOrderWithHypermediaLinks() throws Exception {
        Order order = new Order(
                42L,
                "Nguyen An",
                BigDecimal.valueOf(1250000),
                OrderStatus.PENDING
        );
        when(orderService.getRequired(42L)).thenReturn(order);

        mockMvc.perform(get("/api/orders/42")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$.id").value(42))
                .andExpect(jsonPath("$._links.self.href").exists())
                .andExpect(jsonPath("$._links.orders.href").exists())
                .andExpect(jsonPath("$._links.cancel.href").exists());
    }
}
~~~

Đoạn kiểm thử giả định các kiểu miền và controller nằm trong package mà test có thể truy cập. @Import đưa assembler vào test slice; OrderService được mock để kiểm soát dữ liệu trả về. Tùy phiên bản Spring Boot, có thể dùng annotation mock bean tương ứng của Spring Test.

Nên bổ sung các trường hợp sau:

| Trường hợp | Điều cần xác nhận |
| --- | --- |
| Đơn hàng tồn tại và đang PENDING | Có self, orders và cancel |
| Đơn hàng đã PAID | Không công bố link cancel |
| Không tìm thấy đơn hàng | Trả status lỗi đã quy định, thường là 404 |
| Tạo đơn hàng hợp lệ | Trả 201, có Location và biểu diễn mới |
| Request tạo không hợp lệ | Trả lỗi validation theo hợp đồng |
| Yêu cầu media type không hỗ trợ | Trả 406 nếu không có representation phù hợp |

Ngoài @WebMvcTest, kiểm thử tích hợp với toàn bộ application context hữu ích để xác nhận cấu hình HAL, message converter, mapping và service hoạt động cùng nhau. Với endpoint phân trang, hãy kiểm tra metadata trang và các link điều hướng, đặc biệt ở trang đầu, trang giữa và trang cuối.

Khi viết assertion, nên kiểm tra rel và hành vi mà client dựa vào. Hạn chế so sánh toàn bộ URL tuyệt đối vì hostname, cổng hoặc context path có thể thay đổi theo môi trường. Nếu cần kiểm tra URI, hãy xác nhận cấu trúc và đích đến theo mapping của ứng dụng.

## 10. Những lỗi tích hợp thường gặp

**Controller trả DTO thuần và không có liên kết.** Nếu endpoint cần công bố hypermedia, hãy trả EntityModel, CollectionModel, PagedModel hoặc một kiểu RepresentationModel phù hợp.

**Tự ghép URI bằng chuỗi trong nhiều controller.** Dùng WebMvcLinkBuilder với linkTo(methodOn(...)) để liên kết theo mapping của controller và giảm lỗi khi đường dẫn thay đổi.

**Lặp logic tạo link ở nhiều endpoint.** Đưa logic chuyển đổi vào RepresentationModelAssembler để biểu diễn của cùng một loại tài nguyên nhất quán.

**Đưa entity persistence trực tiếp ra phản hồi.** Dùng DTO hoặc representation model phù hợp để kiểm soát trường dữ liệu công khai và tránh phụ thuộc vào cấu trúc lưu trữ.

**Cho rằng link đã cấp quyền thực hiện thao tác.** Link chỉ mô tả khả năng điều hướng được công bố; endpoint vẫn phải kiểm tra quyền và trạng thái khi nhận request.

**Không kiểm tra media type.** Xác nhận client gửi Accept phù hợp và ứng dụng có message converter cho định dạng đã chọn. Khi cần HAL, kiểm thử cả Content-Type của phản hồi.

**Assembler chứa nghiệp vụ hoặc truy cập dữ liệu.** Giữ service chịu trách nhiệm nghiệp vụ và truy xuất; assembler chỉ chuyển đổi dữ liệu có sẵn thành DTO cùng liên kết.

## 11. Ghi nhớ

Spring MVC tích hợp Spring HATEOAS bằng cách cho controller trả các mô hình biểu diễn hypermedia. EntityModel phù hợp với một tài nguyên, CollectionModel phù hợp với tập hợp và PagedModel phù hợp với danh sách có phân trang. RepresentationModelAssembler gom logic chuyển đối tượng nghiệp vụ thành DTO và link; WebMvcLinkBuilder tạo URI dựa trên mapping controller.

Trong ứng dụng Spring Boot, starter Spring HATEOAS thường cung cấp cấu hình HAL tự động. Client dùng Accept: application/hal+json để yêu cầu định dạng, còn controller có thể khai báo produces để công bố định dạng phản hồi. Với thao tác tạo mới, hãy trả status code và Location đúng quy ước HTTP. Với mọi thao tác, service và endpoint vẫn phải thực thi kiểm tra nghiệp vụ, xác thực và phân quyền.

Một tích hợp dễ bảo trì giữ controller mỏng, service tập trung vào nghiệp vụ, assembler tập trung vào biểu diễn và kiểm thử xác nhận cả dữ liệu lẫn liên kết. Nhờ đó, client có thể khám phá tài nguyên và chuyển tiếp thông qua hợp đồng hypermedia mà API công bố.

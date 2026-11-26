# Uniform interface

Uniform interface (giao diện đồng nhất) là một trong bốn ràng buộc cốt lõi của kiến trúc REST. Nó quy định cách client nhận diện tài nguyên, trao đổi biểu diễn, hiểu thông điệp HTTP và khám phá các bước tiếp theo của ứng dụng. Nhờ đó, client có thể làm việc với API qua một bộ quy tắc ổn định mà không cần biết cách server tổ chức controller, service hay cơ sở dữ liệu.

Spring HATEOAS cung cấp các kiểu dữ liệu và công cụ để đưa hypermedia vào biểu diễn tài nguyên Spring MVC. Thư viện giúp tạo liên kết từ mapping của controller, gắn liên kết vào tài nguyên và xuất biểu diễn theo các định dạng như HAL. Tuy nhiên, chỉ thêm thư viện hoặc thêm trường liên kết vào JSON chưa đủ để một API tuân thủ REST: các ràng buộc còn lại của giao diện đồng nhất vẫn phải được thiết kế đúng.

Sau bài học, bạn có thể:

- Giải thích bốn thành phần của ràng buộc uniform interface trong REST.
- Phân biệt tài nguyên, biểu diễn tài nguyên và thao tác HTTP.
- Dùng RepresentationModel, EntityModel, CollectionModel và RepresentationModelAssembler để xây dựng biểu diễn hypermedia.
- Tạo link theo mapping của controller và hiểu cấu trúc HAL.
- Thiết kế quan hệ link ổn định để client có thể thích nghi khi API thay đổi.
- Kiểm thử link và trạng thái khả dụng của hành động bằng MockMvc.

## 1. Vì sao REST cần giao diện đồng nhất?

Hãy hình dung một ứng dụng quản lý đơn hàng. Client cần xem đơn hàng, hủy đơn hoặc mở danh sách đơn hàng. Nếu API chỉ cung cấp các đường dẫn do client tự ghi nhớ, client có thể phải viết logic như sau:

~~~java
if (order.getStatus().equals("PENDING")) {
    httpClient.post("/api/orders/" + order.getId() + "/cancel");
}
~~~

Đoạn mã trên phụ thuộc vào hai chi tiết nội bộ của API: cấu trúc URI và quy tắc suy ra hành động từ trạng thái. Nếu server đổi đường dẫn hủy đơn, client cũ phải được sửa và phát hành lại. Nếu điều kiện được phép hủy thay đổi, logic phía client có thể không còn đúng.

Một API có giao diện đồng nhất mô tả tài nguyên và các khả năng hiện có bằng một giao thức nhất quán. Client bắt đầu từ một URI đã biết, đọc biểu diễn nhận được, rồi sử dụng các liên kết có quan hệ ngữ nghĩa phù hợp để đi tiếp. Server có thể thay đổi cách định tuyến nội bộ mà không buộc client phải biết cấu trúc đó, miễn là hợp đồng bên ngoài vẫn được giữ.

Uniform interface không có nghĩa mọi endpoint phải có cùng hình dạng JSON hoặc mọi thao tác đều dùng một URI. Nó có nghĩa các tương tác tuân theo cùng quy tắc HTTP và biểu diễn tài nguyên có ngữ nghĩa rõ ràng.

## 2. Bốn thành phần của uniform interface

Theo mô hình REST, ràng buộc này gồm bốn thành phần liên quan với nhau.

### 2.1. Nhận diện tài nguyên bằng URI

Mỗi tài nguyên được nhận diện bằng một định danh, thường là URI. Ví dụ:

- /orders/42 nhận diện một đơn hàng.
- /orders nhận diện tập hợp đơn hàng.
- /customers/17 nhận diện một khách hàng.

URI nhận diện tài nguyên; nó không nhất thiết mô tả cách server lưu trữ tài nguyên hoặc tên của một phương thức Java. Cùng một tài nguyên có thể được biểu diễn theo nhiều định dạng tùy theo khả năng thương lượng nội dung.

HTTP method thể hiện ý định tương tác với tài nguyên:

| Method | Ý nghĩa thường dùng |
|---|---|
| GET | Đọc biểu diễn hiện tại; không yêu cầu thay đổi trạng thái |
| POST | Gửi dữ liệu để xử lý hoặc tạo tài nguyên phụ thuộc vào tài nguyên đích |
| PUT | Thay thế biểu diễn của tài nguyên tại URI đích |
| PATCH | Áp dụng một phần thay đổi lên tài nguyên |
| DELETE | Yêu cầu xóa tài nguyên |

Không nên mã hóa hành động vào tên URI theo kiểu tạo ra một endpoint riêng cho mọi thao tác đọc. Ví dụ, GET /orders/42 phù hợp để đọc đơn hàng; POST /orders/42/cancellation có thể biểu diễn yêu cầu tạo một sự kiện hoặc tài nguyên hủy đơn. Việc chọn URI và method phải phản ánh đúng ngữ nghĩa nghiệp vụ và HTTP.

### 2.2. Thao tác tài nguyên thông qua biểu diễn

Client trao đổi các biểu diễn (representation) của tài nguyên thay vì truy cập trực tiếp đối tượng nội bộ của server. Một biểu diễn có thể chứa dữ liệu JSON, XML hoặc một định dạng hypermedia.

Ví dụ, đơn hàng có thể được biểu diễn như sau:

~~~json
{
  "id": "42",
  "status": "PENDING",
  "total": 125000
}
~~~

Client gửi một biểu diễn hoặc một phần biểu diễn lên server khi thực hiện thao tác cập nhật. Server xác thực dữ liệu, áp dụng quy tắc nghiệp vụ và trả về status code cùng biểu diễn hoặc header phù hợp.

Biểu diễn không đồng nghĩa với entity trong cơ sở dữ liệu. API nên có DTO hoặc mô hình biểu diễn riêng để kiểm soát dữ liệu công khai, tránh vô tình công bố trường nội bộ và tránh để cấu trúc persistence trở thành hợp đồng của client.

Với các thao tác có nguy cơ ghi đè dữ liệu đồng thời, HTTP còn cung cấp cơ chế điều kiện như ETag kết hợp If-Match. Client gửi phiên bản mà nó đã đọc; server chỉ chấp nhận cập nhật nếu tài nguyên vẫn ở phiên bản tương ứng. Cơ chế này bổ sung cho biểu diễn, giúp tránh cập nhật dựa trên dữ liệu cũ.

### 2.3. Thông điệp phải tự mô tả

Một thông điệp HTTP cần mang đủ thông tin để bên nhận hiểu cách xử lý nó mà không phải dựa vào ngữ cảnh ngoài băng. Các thành phần quan trọng gồm:

- Request method cho biết ý định của client.
- URI xác định tài nguyên đích.
- Content-Type mô tả định dạng phần thân được gửi.
- Accept cho biết định dạng phản hồi client có thể xử lý.
- Status code mô tả kết quả ở mức giao thức.
- Header như Location, ETag, Cache-Control và các header xác thực cung cấp ngữ nghĩa bổ sung.

Ví dụ, server trả về 201 Created khi tạo thành công tài nguyên mới và có thể gửi Location trỏ đến tài nguyên vừa tạo. Với một yêu cầu hợp lệ nhưng không có nội dung phản hồi, 204 No Content có thể phù hợp. Client nên dựa vào status code và header theo hợp đồng HTTP, thay vì chỉ kiểm tra một trường tự đặt trong JSON.

### 2.4. Hypermedia điều khiển trạng thái ứng dụng (HATEOAS)

HATEOAS là thành phần kết nối trực tiếp uniform interface với Spring HATEOAS. Server đưa các liên kết có quan hệ ngữ nghĩa vào biểu diễn. Client dùng những liên kết đó để khám phá các tài nguyên hoặc chuyển trạng thái tiếp theo.

Ví dụ, khi đơn hàng đang ở trạng thái PENDING, biểu diễn có thể cung cấp liên kết self và cancel. Sau khi đơn hàng được giao, liên kết cancel có thể biến mất và liên kết receipt có thể xuất hiện. Client không cần tự suy ra URI của từng hành động từ ID hoặc trạng thái.

Một liên kết thường có hai phần quan trọng:

- href: URI mà client có thể truy cập.
- rel: quan hệ mô tả ý nghĩa của liên kết đối với tài nguyên hiện tại, ví dụ self, next, collection hoặc cancel.

Quan hệ link là một phần của hợp đồng. Client nên dựa vào rel để hiểu vai trò của link, sau đó truy cập href. Client không nên tách chuỗi href để suy ra ID hoặc tự nối thêm đường dẫn.

Cần phân biệt hai ý: link giúp client khám phá khả năng hiện có; server vẫn phải kiểm tra quyền truy cập và điều kiện nghiệp vụ khi nhận yêu cầu. Việc một client biết href không đồng nghĩa client được cấp quyền thực hiện hành động.

## 3. Spring HATEOAS biểu diễn uniform interface như thế nào?

Spring HATEOAS bổ sung mô hình hypermedia cho ứng dụng Spring. Trong ứng dụng Spring Boot, có thể thêm dependency spring-boot-starter-hateoas và để Spring Boot quản lý phiên bản tương thích thông qua dependency management của dự án.

Các kiểu dữ liệu thường dùng:

| Kiểu | Vai trò |
|---|---|
| RepresentationModel | Lớp cơ sở để một biểu diễn mang các link |
| EntityModel<T> | Bao một đối tượng biểu diễn đơn lẻ cùng các link |
| CollectionModel<T> | Bao một tập hợp biểu diễn cùng các link của tập hợp |
| PagedModel<T> | Biểu diễn tập hợp có phân trang và metadata phân trang |
| Link | Mô tả một URI cùng quan hệ của nó |
| RepresentationModelAssembler<T, D> | Chuyển đối tượng miền hoặc DTO thành biểu diễn hypermedia |

EntityModel không bắt buộc phải chứa JPA entity. Trong thiết kế thực tế, nên truyền DTO hoặc kiểu biểu diễn đã được chọn lọc để API kiểm soát được dữ liệu công khai.

### 3.1. Tạo link theo mapping của controller

Spring HATEOAS cung cấp WebMvcLinkBuilder với hai hàm thường gặp:

- linkTo(...) xác định đường dẫn dựa trên mapping Spring MVC.
- methodOn(...) tạo lời gọi mô phỏng đến phương thức controller để Spring HATEOAS phân tích mapping và tham số.

Ví dụ, thay vì ghép chuỗi URI thủ công, có thể tạo link self như sau:

~~~java
linkTo(methodOn(OrderController.class).one(id)).withSelfRel()
~~~

Cách này giúp đường dẫn được tạo theo mapping của controller. Khi mapping thay đổi, link được sinh từ metadata của mapping mới, giảm nguy cơ đường dẫn trong biểu diễn bị lệch với endpoint thực tế.

Lời gọi methodOn không thực thi logic nghiệp vụ của controller. Nó được dùng để mô tả phương thức và tham số nhằm dựng URI.

### 3.2. Ví dụ xây dựng biểu diễn đơn hàng

Giả sử ứng dụng có kiểu miền Order và OrderService. Các phương thức truy vấn, kiểm tra trạng thái và cập nhật bên dưới là các phương thức của ứng dụng minh họa; bạn thay bằng mô hình miền thực tế của mình.

Trước hết, xác định DTO được công bố qua API:

~~~java
public record OrderRepresentation(
    UUID id,
    String status,
    BigDecimal total
) {}
~~~

Assembler chịu trách nhiệm chuyển một Order thành EntityModel. Các link được tạo tập trung ở đây để mọi nơi trả về đơn hàng đều có cùng quy tắc:

~~~java
@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderRepresentation>> {

    @Override
    public EntityModel<OrderRepresentation> toModel(Order order) {
        UUID id = order.getId();

        EntityModel<OrderRepresentation> model = EntityModel.of(
            new OrderRepresentation(
                id,
                order.getStatus().name(),
                order.getTotal()
            ),
            linkTo(methodOn(OrderController.class).one(id)).withSelfRel()
        );

        if (order.canBeCancelled()) {
            model.add(
                linkTo(methodOn(OrderController.class).cancel(id))
                    .withRel("cancel")
            );
        }

        model.add(
            linkTo(methodOn(OrderController.class).all())
                .withRel("orders")
        );

        return model;
    }
}
~~~

Điểm quan trọng nằm ở điều kiện tạo link cancel. Assembler chỉ công bố hành động khi trạng thái hiện tại cho phép hành động đó theo quy tắc của miền. Nếu đơn hàng đã được giao hoặc đã bị hủy, link này sẽ không xuất hiện.

Controller có thể trả trực tiếp các mô hình hypermedia:

~~~java
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
        return assembler.toModel(service.getRequired(id));
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

Các import chính của ví dụ:

~~~java
import java.math.BigDecimal;
import java.util.UUID;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;
~~~

Một số điểm cần lưu ý:

1. Phương thức one trả về EntityModel thay vì trả DTO thuần. Lớp bao này giữ dữ liệu đơn hàng và các link trong cùng một biểu diễn.
2. Phương thức all trả về CollectionModel để tập hợp có thể có link self, phân trang hoặc các link điều hướng khác.
3. Assembler giữ logic chuyển đổi và tạo link ở một nơi, giúp controller tập trung vào điều phối request.
4. Phương thức cancel vẫn kiểm tra điều kiện nghiệp vụ trong service. Việc assembler đã phát link cancel không thay thế kiểm tra này.
5. Với hệ thống lớn, nên dùng assembler riêng cho từng loại tài nguyên hoặc nhóm biểu diễn có cùng quy tắc.

### 3.3. Tổ chức link relation

Tên quan hệ cần ổn định và có ý nghĩa với client. Một số quan hệ phổ biến đã được chuẩn hóa, chẳng hạn self, next, prev, first, last và collection. Khi một quan hệ chuẩn diễn đạt đúng ý nghĩa, hãy ưu tiên dùng nó.

Các quan hệ theo miền như cancel, approve hoặc submit có thể được dùng làm custom relation. Với API được công bố rộng hoặc có nhiều nhóm client, nên định nghĩa tài liệu ngữ nghĩa rõ ràng cho các quan hệ này. Có thể dùng URI quan hệ hoặc CURIE để tránh xung đột tên và cung cấp cách tra cứu định nghĩa.

Không nên dùng một rel cho nhiều ý nghĩa khác nhau tùy theo endpoint. Nếu rel cancel được dùng để hủy đơn hàng ở một nơi, client phải có thể dựa vào cùng ngữ nghĩa đó ở mọi biểu diễn liên quan.

## 4. HAL: định dạng biểu diễn hypermedia phổ biến

HAL (Hypertext Application Language) là một định dạng JSON dành cho tài nguyên có liên kết. HAL quy ước một số trường:

- _links chứa các liên kết của tài nguyên.
- _embedded chứa các tài nguyên được nhúng.
- self thường là liên kết đến tài nguyên hiện tại.

Một biểu diễn đơn hàng có thể được serialize theo hình thức sau:

~~~json
{
  "id": "42",
  "status": "PENDING",
  "total": 125000,
  "_links": {
    "self": {
      "href": "https://api.example.com/orders/42"
    },
    "cancel": {
      "href": "https://api.example.com/orders/42/cancellation"
    },
    "orders": {
      "href": "https://api.example.com/orders"
    }
  }
}
~~~

Khi đơn hàng không còn hủy được, server có thể trả về cùng tài nguyên nhưng bỏ link cancel. Một client HAL có thể tìm quan hệ cancel trong _links để quyết định có hiển thị thao tác hủy hay không.

Với collection, HAL có thể đặt các phần tử trong _embedded và các link điều hướng ở _links. Tên quan hệ dùng làm khóa trong _embedded phụ thuộc cấu hình quan hệ của ứng dụng, vì vậy client nên dựa vào hợp đồng relation đã công bố thay vì tự suy đoán tên khóa từ tên lớp Java.

Client có thể yêu cầu HAL bằng header:

~~~http
GET /orders/42 HTTP/1.1
Accept: application/hal+json
~~~

Server phản hồi với Content-Type phù hợp, thường là application/hal+json. Trong Spring Boot, starter HATEOAS cung cấp cấu hình hỗ trợ hypermedia và HAL. Hãy kiểm tra cấu hình content negotiation của ứng dụng nếu API đang trả JSON thuần hoặc không khớp với Accept header.

HAL mô tả href và rel rất tốt, nhưng một link đơn giản chưa mô tả đầy đủ mọi chi tiết của một thao tác. Chẳng hạn, chỉ nhìn vào link cancel, client chưa chắc biết thao tác đó cần POST, cần gửi body hay cần trường dữ liệu nào.

## 5. Affordances: mô tả thêm cách thực hiện hành động

Affordance mở rộng thông tin gắn với link để mô tả các thao tác mà tài nguyên hỗ trợ. Tùy định dạng hypermedia, metadata này có thể mô tả HTTP method, kiểu nội dung, tên thao tác hoặc cấu trúc dữ liệu đầu vào.

Ví dụ, ngoài việc công bố một liên kết đến thao tác cập nhật địa chỉ giao hàng, server có thể mô tả rằng thao tác đó dùng PATCH và yêu cầu một biểu diễn đầu vào với các trường địa chỉ. Client có thể dùng metadata này để xây dựng giao diện hoặc gửi request phù hợp mà không phải mã hóa toàn bộ chi tiết thao tác trong ứng dụng.

Spring HATEOAS hỗ trợ xây dựng affordance thông qua API Affordances và biểu diễn các mô tả này trong những định dạng có hỗ trợ, chẳng hạn HAL-FORMS. Khi chọn dùng affordance, cần xác định rõ client mục tiêu có hiểu định dạng đó hay không. Nếu client chỉ hỗ trợ HAL cơ bản, hãy công bố tài liệu API hoặc hợp đồng bổ sung cho method và dữ liệu đầu vào.

Affordance không thay thế tài liệu về quy tắc nghiệp vụ. Nó mô tả cách tương tác ở mức giao thức và dữ liệu; server vẫn phải xác thực, phân quyền và kiểm tra trạng thái khi xử lý request.

## 6. Thiết kế API có thể tiến hóa

Uniform interface và hypermedia giúp giảm sự phụ thuộc của client vào cấu trúc URI, nhưng chỉ có tác dụng khi quan hệ và ngữ nghĩa được duy trì ổn định.

### 6.1. Client đi theo link thay vì tự dựng URI

Client nên bắt đầu từ entry point đã được công bố, đọc rel và href trong phản hồi, rồi theo link cần thiết. Client không nên ghép /orders/ với ID, tự tạo /cancellation hoặc dựa vào vị trí của một trường trong JSON để đoán endpoint.

Khi server đổi mapping từ /orders/{id}/cancellation sang một URI khác, server có thể cập nhật href trong biểu diễn. Client vẫn hoạt động nếu nó tìm đúng relation cancel và không phụ thuộc vào chuỗi URI cũ.

### 6.2. Giữ ý nghĩa của relation

Có thể bổ sung relation mới để cung cấp khả năng mới. Client cũ nên bỏ qua relation mà nó không hiểu. Ngược lại, không nên âm thầm đổi ý nghĩa của relation đang tồn tại. Nếu cancel trước đây có nghĩa là yêu cầu hủy đơn nhưng sau này lại mang nghĩa xóa đơn, client có thể thực hiện hành động sai dù URI vẫn hợp lệ.

Khi cần thay đổi không tương thích, hãy công bố hợp đồng mới theo chiến lược versioning hoặc media type phù hợp và có lộ trình chuyển đổi rõ ràng.

### 6.3. Link phản ánh trạng thái hiện tại

Tập hợp link có thể thay đổi theo trạng thái tài nguyên, quyền của người dùng hoặc điều kiện nghiệp vụ. Một đơn hàng PENDING có thể có cancel; đơn hàng SHIPPED có thể không có cancel. Client nên xử lý cả trường hợp link có mặt lẫn vắng mặt.

Không nên xem sự vắng mặt của link là cơ chế bảo mật duy nhất. Người dùng có thể gửi request trực tiếp, dùng client cũ hoặc dùng một URL đã lưu. Server phải kiểm tra quyền và trạng thái ở mỗi request, rồi trả status code phù hợp nếu thao tác không được phép.

### 6.4. Đừng công bố link gây hiểu nhầm

Mỗi link nên giúp client trả lời một câu hỏi cụ thể: đây là tài nguyên nào, có thể đi đến đâu, hoặc có thể thực hiện hành động gì? Tránh đưa quá nhiều link không liên quan vào mọi biểu diễn. Một tập hợp link có chủ đích giúp client dễ khám phá và giảm sự nhập nhằng trong hợp đồng.

Nếu API chạy sau reverse proxy hoặc gateway, cần cấu hình để Spring tạo URI bên ngoài chính xác. Link được sinh với host, scheme hoặc context path nội bộ sai có thể khiến client không truy cập được dù mapping trong ứng dụng hoạt động.

## 7. Kiểm thử hypermedia với MockMvc

Kiểm thử controller không nên chỉ xác nhận status code hoặc một vài trường dữ liệu. Với API hypermedia, cần xác nhận cả quan hệ link, href, media type và việc link xuất hiện đúng theo trạng thái tài nguyên.

Ví dụ dưới đây giả định service đã được mock để trả về một đơn hàng đang chờ xử lý. Phần fixture pendingOrder(id) là hàm dựng dữ liệu kiểm thử của ứng dụng:

~~~java
@WebMvcTest(OrderController.class)
@Import(OrderModelAssembler.class)
class OrderControllerTest {

    @Autowired
    MockMvc mvc;

    @MockBean
    OrderService service;

    @Test
    void includesCancelLinkForPendingOrder() throws Exception {
        UUID id = UUID.fromString("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa");
        given(service.getRequired(id)).willReturn(pendingOrder(id));

        mvc.perform(get("/orders/{id}", id)
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$._links.self.href")
                .value(endsWith("/orders/" + id)))
            .andExpect(jsonPath("$._links.cancel.href").exists());
    }
}
~~~

Các import thường dùng trong bài kiểm thử:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
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

Với một đơn hàng đã hoàn tất, hãy kiểm tra link cancel không được xuất hiện:

~~~java
.andExpect(jsonPath("$._links.cancel").doesNotExist());
~~~

Ngoài các assertion trên, nên có những kiểm thử sau:

- Collection trả về link self và các link điều hướng cần thiết.
- Link được tạo đúng khi controller có context path hoặc mapping lồng nhau.
- Content negotiation trả đúng media type mà client yêu cầu.
- Một request thực hiện hành động không hợp lệ nhận status code phù hợp, kể cả khi client tự gửi URI mà không có link.
- Các relation được giữ ổn định qua những thay đổi mapping nội bộ.
- Phản hồi tạo tài nguyên mới có status code và Location phù hợp.

MockMvc kiểm tra tích hợp giữa Spring MVC, assembler và quá trình serialize phản hồi trong ngữ cảnh test. Với cấu hình gateway, proxy hoặc triển khai nhiều instance, cần bổ sung kiểm thử ở môi trường tích hợp để xác nhận link công khai được tạo chính xác.

## 8. Lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Ghép URI bằng chuỗi trong assembler | Link có thể lệch khi mapping thay đổi | Dùng linkTo và methodOn |
| Trả entity persistence trực tiếp | API vô tình phụ thuộc cấu trúc cơ sở dữ liệu | Dùng DTO hoặc kiểu biểu diễn riêng |
| Luôn phát mọi link bất kể trạng thái | Client nhìn thấy hành động không khả dụng | Tạo link theo trạng thái và quyền phù hợp |
| Cho rằng có link đồng nghĩa được phép thao tác | Request trực tiếp có thể vượt qua giả định của client | Luôn kiểm tra quyền và nghiệp vụ ở server |
| Dùng rel không ổn định hoặc mơ hồ | Client khó hiểu ý nghĩa link | Định nghĩa relation và giữ ngữ nghĩa lâu dài |
| Chỉ kiểm tra status code trong test | Lỗi thiếu link hoặc sai href không được phát hiện | Kiểm tra cả _links, href và media type |
| Coi HAL là toàn bộ hợp đồng API | Method hoặc dữ liệu đầu vào của thao tác có thể chưa rõ | Dùng affordance khi phù hợp và công bố tài liệu hợp đồng |

## 9. Quy trình áp dụng trong một endpoint

Khi thêm hypermedia cho một tài nguyên, có thể thực hiện theo trình tự:

1. Xác định tài nguyên và URI công khai của nó.
2. Chọn DTO biểu diễn dữ liệu mà client được phép nhìn thấy.
3. Xác định các thao tác HTTP hợp lệ và điều kiện nghiệp vụ tương ứng.
4. Chọn relation cho link, ưu tiên relation chuẩn khi phù hợp và định nghĩa rõ custom relation.
5. Dùng assembler để tạo EntityModel hoặc CollectionModel cùng các link.
6. Trả biểu diễn từ controller và xác nhận content negotiation cho HAL.
7. Kiểm thử link có mặt, link vắng mặt, href, media type và kết quả của request thực hiện hành động.
8. Đánh giá tác động tương thích trước khi đổi URI, relation hoặc cấu trúc biểu diễn.

## 10. Kết luận

Uniform interface tạo ra một hợp đồng tương tác nhất quán giữa client và server thông qua URI, HTTP method, biểu diễn, thông điệp tự mô tả và hypermedia. Spring HATEOAS hỗ trợ phần hypermedia bằng các mô hình như EntityModel, CollectionModel, Link và RepresentationModelAssembler, đồng thời giúp tạo link dựa trên mapping thực tế của controller.

Khi thiết kế đúng, client có thể khám phá tài nguyên và hành động thông qua relation thay vì phụ thuộc vào cấu trúc URI nội bộ. Điều đó giúp API dễ tiến hóa hơn, miễn là server giữ ổn định ngữ nghĩa của hợp đồng, trả biểu diễn chính xác và luôn thực thi kiểm tra quyền cùng quy tắc nghiệp vụ ở phía server.


# Relation self

Trong một representation có hypermedia, relation **self** công bố URI nhận diện chính tài nguyên đang được biểu diễn. Client dùng link này để xác định địa chỉ của tài nguyên hiện tại, lưu tham chiếu, tải representation mới hoặc tiếp tục điều hướng từ đúng tài nguyên đó. Với REST API, self link là điểm neo quan trọng giúp client không phải tự ghép URL từ ID hay phụ thuộc vào cấu trúc route nội bộ của server.

IANA đăng ký relation **self** với ngữ nghĩa “conveys an identifier for the link's context”: link target cung cấp một định danh cho ngữ cảnh của link. Trong cách sử dụng phổ biến của API hypermedia, link self trỏ đến URI của resource mà representation mô tả. Spring HATEOAS cung cấp hằng số IanaLinkRelations.SELF và phương thức withSelfRel() để tạo relation chuẩn này.

Bài học tập trung vào ngữ nghĩa của self, cách tạo self link bằng Spring HATEOAS, phân biệt self của tài nguyên đơn với self của collection và trang kết quả, cách xử lý URI, cách kết hợp self với affordance và cách kiểm thử hợp đồng link trong HAL JSON.

## 1. Relation self biểu thị điều gì?

Một link có hai thành phần cơ bản: URI tham chiếu đến đích và relation mô tả mối quan hệ giữa đích đó với tài nguyên đang chứa link. Với relation self, đích link đóng vai trò định danh cho chính ngữ cảnh của link.

Ví dụ response một đơn hàng:

~~~json
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
~~~

Representation mô tả đơn hàng ORD-42. Link self công bố URI /orders/ORD-42 để client nhận diện và truy cập chính tài nguyên này.

Một client có thể nhận representation từ một collection, một thông báo hoặc một API entry point mà không biết route chi tiết. Khi representation có self link, client có thể dùng href được server cung cấp thay vì suy ra URI từ trường id.

Relation self có ngữ nghĩa nhận diện tài nguyên. Nó không nói rằng tài nguyên có thể được cập nhật, xóa hay thực hiện bất kỳ thao tác nào khác. Những khả năng đó cần được công bố bằng link relation phù hợp hoặc affordance và vẫn phải được server kiểm tra khi nhận request.

## 2. Self là một IANA link relation

IANA Link Relation Registry là danh mục các relation đã đăng ký để nhiều ứng dụng có thể dùng chung ngữ nghĩa. Relation self được đăng ký với mô tả nhận diện ngữ cảnh của link và có tham chiếu đến RFC 4287.

Spring HATEOAS cung cấp lớp IanaLinkRelations để sử dụng các relation chuẩn dưới dạng LinkRelation. Với self, có hai cách thường gặp:

~~~java
IanaLinkRelations.SELF
~~~

và:

~~~java
.withSelfRel()
~~~

Cả hai cách đều biểu thị relation chuẩn có giá trị self. Nên ưu tiên hằng số hoặc phương thức chuyên biệt thay vì gõ chuỗi "self" rải rác trong ứng dụng. Điều này giúp tránh lỗi chính tả và làm rõ rằng relation đang dùng thuộc bộ IANA.

Ví dụ tạo Link trực tiếp:

~~~java
Link self = Link.of(
    "/orders/ORD-42",
    IanaLinkRelations.SELF
);
~~~

Hoặc dùng factory method rút gọn. Overload chỉ nhận href mặc định tạo relation self:

~~~java
Link self = Link.of("/orders/ORD-42");
~~~

Trong ứng dụng Spring MVC, cách tạo link từ controller mapping thường phù hợp hơn vì URI được suy ra từ mapping đang khai báo.

## 3. Phân biệt self với canonical và related

Các relation này có thể cùng xuất hiện trong một representation nhưng mang ý nghĩa khác nhau.

| Relation | Ý nghĩa | Ví dụ |
|---|---|---|
| self | Định danh cho ngữ cảnh của link, thường là URI của tài nguyên hiện tại | /orders/ORD-42 |
| canonical | Chỉ ra phiên bản hoặc URI được xem là ưu tiên của tài nguyên | /orders/ORD-42 |
| alternate | Chỉ ra representation hoặc tài nguyên thay thế | /orders/ORD-42?format=pdf |
| related | Chỉ ra một tài nguyên có liên quan | /customers/CUS-7 |
| collection | Chỉ ra collection resource chứa hoặc đại diện cho ngữ cảnh hiện tại | /orders |

Self và canonical có thể trùng href trong một API đơn giản, nhưng không nên xem chúng là từ đồng nghĩa. Self trả lời câu hỏi “địa chỉ nhận diện tài nguyên trong ngữ cảnh representation này là gì?”. Canonical trả lời câu hỏi “phiên bản hoặc URI nào được ưu tiên làm bản chuẩn?”.

Ví dụ một bài viết có thể có self link đến representation hiện tại và canonical link đến URL chuẩn được công bố cho nội dung:

~~~json
{
  "id": "POST-19",
  "title": "Spring HATEOAS",
  "_links": {
    "self": {
      "href": "/api/posts/POST-19"
    },
    "canonical": {
      "href": "https://example.com/articles/spring-hateoas"
    }
  }
}
~~~

Nếu API không có nhiều URI hoặc representation thay thế, self link thường là đủ. Chỉ thêm canonical khi ứng dụng thực sự có khái niệm URI ưu tiên.

## 4. Tạo self link bằng WebMvcLinkBuilder

Trong Spring MVC, WebMvcLinkBuilder tạo link dựa trên mapping của controller. Hai helper thường dùng là linkTo(...) và methodOn(...):

- methodOn(...) tạo lời gọi giả lập để Spring HATEOAS đọc metadata của handler method.
- linkTo(...) xây URI từ mapping được tham chiếu.
- withSelfRel() gắn relation self cho link được tạo.

Ví dụ controller:

~~~java
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
public class OrderController {

    @GetMapping("/{id}")
    public EntityModel<OrderRepresentation> one(
            @PathVariable UUID id) {
        // Tìm đơn hàng và tạo representation
    }
}
~~~

Tạo self link:

~~~java
Link self = linkTo(
    methodOn(OrderController.class).one(order.getId())
).withSelfRel();
~~~

Nếu mapping thay đổi từ /orders/{id} sang /api/orders/{id}, link được xây dựng từ metadata controller có thể phản ánh mapping mới mà assembler không cần sửa chuỗi URL thủ công.

Lời gọi one(order.getId()) trong methodOn không thực thi logic của controller. Nó ghi nhận thông tin phương thức và tham số để xây dựng URI. Không dùng methodOn như một cách gọi service hoặc thực hiện nghiệp vụ.

Các import:

~~~java
import org.springframework.hateoas.Link;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;
~~~

## 5. Tạo self link trong RepresentationModelAssembler

Assembler là nơi thích hợp để tạo self link cho một loại tài nguyên vì nó tập trung cách chuyển đối tượng miền thành representation.

Ví dụ DTO:

~~~java
public record OrderRepresentation(
    UUID id,
    String status,
    BigDecimal total
) {}
~~~

Assembler:

~~~java
import java.math.BigDecimal;
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
public class OrderModelAssembler implements
        RepresentationModelAssembler<
            Order, EntityModel<OrderRepresentation>> {

    @Override
    public EntityModel<OrderRepresentation> toModel(Order order) {
        var body = new OrderRepresentation(
            order.getId(),
            order.getStatus(),
            order.getTotal()
        );

        Link self = linkTo(
            methodOn(OrderController.class).one(order.getId())
        ).withSelfRel();

        return EntityModel.of(body, self);
    }
}
~~~

EntityModel bọc nội dung OrderRepresentation và danh sách link. Khi serializer tạo HAL JSON, self link xuất hiện trong thuộc tính _links.

Nếu representation cần thêm link đến collection hoặc quan hệ khác, có thể bổ sung chúng:

~~~java
return EntityModel.of(
    body,
    self,
    linkTo(methodOn(OrderController.class).all())
        .withRel("orders"),
    linkTo(methodOn(CustomerController.class).one(order.getCustomerId()))
        .withRel("customer")
);
~~~

Self vẫn nhận diện chính đơn hàng. Relation orders và customer biểu thị các tài nguyên khác. Không dùng self cho link đến khách hàng hoặc collection chỉ vì chúng có liên quan đến đơn hàng.

## 6. Self link của tài nguyên đơn và collection

Self của tài nguyên đơn và self của collection có ngữ cảnh khác nhau.

Representation của một đơn hàng:

~~~json
{
  "id": "ORD-42",
  "_links": {
    "self": {
      "href": "/orders/ORD-42"
    },
    "orders": {
      "href": "/orders"
    }
  }
}
~~~

Ở đây, self trỏ đến đơn hàng ORD-42. Relation orders trỏ đến collection đơn hàng.

Representation collection:

~~~json
{
  "_links": {
    "self": {
      "href": "/orders"
    }
  },
  "_embedded": {
    "orders": [
      {
        "id": "ORD-42",
        "_links": {
          "self": {
            "href": "/orders/ORD-42"
          }
        }
      },
      {
        "id": "ORD-43",
        "_links": {
          "self": {
            "href": "/orders/ORD-43"
          }
        }
      }
    ]
  }
}
~~~

Self ở cấp ngoài nhận diện collection resource. Mỗi phần tử được nhúng có self riêng nhận diện tài nguyên đơn hàng tương ứng.

Không dùng self của collection làm self cho từng phần tử. Nếu client theo self của phần tử ORD-43, nó phải nhận được tài nguyên ORD-43 chứ không phải toàn bộ collection.

## 7. Self link trong CollectionModel và PagedModel

Spring HATEOAS cung cấp CollectionModel để biểu diễn một tập hợp tài nguyên. Link self của CollectionModel nhận diện collection resource hoặc collection view đang được trả về.

Ví dụ:

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.CollectionModel;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@GetMapping("/orders")
public CollectionModel<EntityModel<OrderRepresentation>> all() {
    var orders = service.findAll();

    return assembler.toCollectionModel(orders)
        .add(
            linkTo(methodOn(OrderController.class).all())
                .withSelfRel()
        );
}
~~~

Nếu collection có phân trang hoặc lọc, self link nên phản ánh chính view hiện tại, bao gồm các query parameter có ý nghĩa với kết quả đang hiển thị.

Ví dụ:

~~~text
/orders?status=PROCESSING&page=1&size=20
~~~

Đây là self link của trang collection đã lọc, không phải self link của từng đơn hàng.

Với PagedModel, Spring HATEOAS và Spring Data có thể tạo link self cùng các link điều hướng first, prev, next và last. Link self xác định trang hiện tại; các relation còn lại xác định các trang khác trong cùng chuỗi kết quả.

Khi tự xây pagination links hoặc dùng base link tùy chỉnh, hãy giữ lại filter và sort hiện tại trong self và các link điều hướng. Nếu bỏ filter khỏi self, URI không còn tái hiện đúng collection view mà response đang mô tả.

## 8. Self link của tài nguyên nhúng

Một tài nguyên xuất hiện trong _embedded vẫn là một representation riêng. Nếu client cần truy cập trực tiếp tài nguyên đó, nên cung cấp self link bên trong phần tử nhúng.

Ví dụ:

~~~json
{
  "_links": {
    "self": {
      "href": "/customers/CUS-7/orders"
    }
  },
  "_embedded": {
    "orders": [
      {
        "id": "ORD-42",
        "status": "PROCESSING",
        "_links": {
          "self": {
            "href": "/orders/ORD-42"
          }
        }
      }
    ]
  }
}
~~~

Self của collection khách hàng là /customers/CUS-7/orders. Self của đơn hàng nhúng là /orders/ORD-42.

Trong Spring HATEOAS, assembler cho phần tử collection nên tạo self link như khi tài nguyên được trả về độc lập. Việc representation nằm trong _embedded không làm thay đổi ngữ nghĩa relation self.

Nếu một embedded resource chỉ là summary không có endpoint độc lập, không nên tự tạo self link giả. Khi đó, summary là dữ liệu lồng bên trong tài nguyên cha; có thể dùng một relation hoặc cấu trúc DTO phù hợp thay vì công bố URI không tồn tại.

## 9. Tạo self link bằng RepresentationModelAssemblerSupport

Nếu assembler kế thừa RepresentationModelAssemblerSupport, có thể dùng createModelWithId(...) để tạo model và thêm self link dựa trên controller class đã khai báo trong constructor.

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

Constructor truyền OrderController.class để cung cấp mapping controller và OrderModel.class để xác định kiểu representation. createModelWithId(...) khởi tạo model rồi thêm self link từ mapping và ID.

Khi đã dùng createModelWithId(...), không nên thêm một self link giống hệt lần nữa trong cùng assembler. Hãy kiểm tra model đã có self link trước khi bổ sung link khác.

Helper phù hợp với cấu trúc URI item được hình thành từ mapping tài nguyên và ID. Nếu endpoint có URI tùy chỉnh, path variable bổ sung hoặc không theo dạng collection/id, hãy kiểm tra link thực tế hoặc tạo self link trực tiếp từ handler method tương ứng.

## 10. Self link có thể mang affordance

Self link xác định tài nguyên hiện tại. Spring HATEOAS còn cho phép gắn affordance vào link để mô tả những thao tác có thể thực hiện trên tài nguyên.

Ví dụ:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;

Link self = linkTo(
        methodOn(OrderController.class).one(order.getId())
    )
    .withSelfRel()
    .andAffordance(afford(
        methodOn(OrderController.class).update(null, order.getId())
    ));
~~~

Self link vẫn có relation self. Affordance bổ sung metadata về handler update, chẳng hạn HTTP method, kiểu request body và các ràng buộc có thể suy ra từ mapping hoặc kiểu input.

Điểm cần phân biệt:

- Relation self nhận diện tài nguyên.
- Affordance mô tả một thao tác liên quan đến tài nguyên.
- Endpoint vẫn phải xác thực, phân quyền và kiểm tra trạng thái khi request thực sự được gửi.

Một client không nên suy luận rằng có self link thì tài nguyên có thể được cập nhật. Chỉ công bố affordance khi thao tác thực sự được hỗ trợ trong ngữ cảnh representation đó.

## 11. Self link và URI tuyệt đối hoặc tương đối

Href trong link có thể là URI tuyệt đối hoặc URI tham chiếu tương đối. Ví dụ:

~~~json
{
  "_links": {
    "self": {
      "href": "/orders/ORD-42"
    }
  }
}
~~~

hoặc:

~~~json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/orders/ORD-42"
    }
  }
}
~~~

URI tương đối được client phân giải dựa trên URI cơ sở của representation theo quy tắc URI. URI tuyệt đối chứa scheme và authority, thuận tiện khi client lưu hoặc chia sẻ link ở ngoài ngữ cảnh response.

Khi dùng WebMvcLinkBuilder, Spring HATEOAS xây dựng URI dựa trên request hiện tại và cấu hình web. Nếu ứng dụng chạy sau reverse proxy hoặc API gateway, cần cấu hình forwarded headers đúng để scheme, host và prefix công khai được nhận diện chính xác.

Không nên hard-code domain, port hoặc context path trong assembler. Điều đó dễ làm self link trỏ về hostname nội bộ hoặc môi trường khác khi ứng dụng chạy sau proxy.

Nếu API cố ý công bố URI tương đối, hãy bảo đảm client có thể phân giải chúng từ response URL. Nếu API công bố URI tuyệt đối, hãy kiểm thử cấu hình proxy trong môi trường triển khai.

## 12. Self link và query parameter

Với tài nguyên đơn, self thường nhận diện URI tài nguyên, ví dụ /orders/ORD-42. Với collection hoặc kết quả tìm kiếm, query parameter có thể là một phần quan trọng của URI view.

Ví dụ:

- /orders: collection mặc định.
- /orders?status=PROCESSING: collection được lọc theo trạng thái.
- /orders?status=PROCESSING&page=1&size=20: trang thứ hai của collection đã lọc.

Self link của trang tìm kiếm nên phản ánh các tham số làm thay đổi nội dung hoặc cách hiển thị của trang. Các tham số tracking hoặc tham số không ảnh hưởng đến representation thường không cần đưa vào self link.

Client có thể lưu self link để tải lại cùng view. Nếu server bỏ query parameter quan trọng, link self không còn mô tả chính xác response hiện tại.

Không nhầm URI template với self URI đã mở rộng. Link search có thể là template như /orders{?status,page,size}; self của kết quả hiện tại nên là URI cụ thể chứa giá trị filter và page đang áp dụng.

## 13. Không dùng self thay cho định danh nghiệp vụ

Trường id trong JSON và self link có thể cùng xuất hiện nhưng phục vụ các nhu cầu khác nhau.

~~~json
{
  "id": "ORD-42",
  "status": "PROCESSING",
  "_links": {
    "self": {
      "href": "/orders/ORD-42"
    }
  }
}
~~~

id là dữ liệu của representation theo hợp đồng ứng dụng. Self link là một quan hệ hypermedia công bố URI để truy cập tài nguyên.

Client có thể hiển thị id cho người dùng hoặc dùng nó trong nghiệp vụ. Nhưng khi điều hướng, client nên theo href trong self thay vì tự nối id vào chuỗi /orders/{id}.

Nếu API đổi cấu trúc URI nhưng giữ relation self và cung cấp href mới, client hypermedia có thể tiếp tục hoạt động mà không cần biết route mới. Điều này giảm coupling giữa client và cấu trúc URL của server.

Không bắt buộc URI phải chứa ID nội bộ của database. API có thể dùng mã công khai, slug hoặc định danh opaque miễn là URI ổn định theo hợp đồng và server có thể phân giải nó.

## 14. Xử lý tài nguyên không tồn tại

Self link chỉ nên được tạo khi server có một tài nguyên hợp lệ để biểu diễn. Nếu request tìm kiếm ID không tồn tại, service hoặc controller cần trả lỗi phù hợp, thường là 404 Not Found, thay vì tạo EntityModel rỗng với self link trỏ đến tài nguyên không có.

Ví dụ:

~~~java
@GetMapping("/{id}")
public EntityModel<OrderRepresentation> one(
        @PathVariable UUID id) {

    Order order = service.findById(id)
        .orElseThrow(() -> new OrderNotFoundException(id));

    return assembler.toModel(order);
}
~~~

Assembler nhận Order hợp lệ và tạo self link. Trách nhiệm tìm kiếm và quyết định 404 nằm ở service/controller.

Nếu tài nguyên đã bị xóa nhưng API vẫn hỗ trợ URI tombstone hoặc lịch sử, hãy biểu diễn semantics đó theo hợp đồng riêng. Không dùng một representation rỗng để che giấu việc tài nguyên không còn tồn tại.

## 15. Kiểm thử self link bằng unit test

Có thể kiểm thử trực tiếp assembler để xác nhận relation và href được tạo đúng. Với WebMvcLinkBuilder, unit test cần request context nếu muốn tạo URI đầy đủ.

Đoạn test dưới đây giả định fixture đã khởi tạo Order hợp lệ và assembler đã được inject hoặc tạo trong test.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

import static org.assertj.core.api.Assertions.assertThat;

@Test
void createsSelfLinkForOrder() {
    MockHttpServletRequest request =
        new MockHttpServletRequest("GET", "/orders");

    request.setScheme("https");
    request.setServerName("api.example.test");
    request.setServerPort(443);

    RequestContextHolder.setRequestAttributes(
        new ServletRequestAttributes(request)
    );

    try {
        EntityModel<OrderRepresentation> model =
            assembler.toModel(order);

        assertThat(model.hasLink(IanaLinkRelations.SELF)).isTrue();

        assertThat(
            model.getRequiredLink(IanaLinkRelations.SELF).getHref()
        ).endsWith("/orders/" + order.getId());
    } finally {
        RequestContextHolder.resetRequestAttributes();
    }
}
~~~

Test xác nhận hai điều riêng biệt:

1. Model có relation self.
2. Href nhận diện đúng tài nguyên có ID của order.

Luôn reset RequestContextHolder trong finally để tránh rò rỉ request context sang test khác. Nếu dùng MockMvc, có thể ưu tiên kiểm thử qua HTTP vì Spring MVC tự thiết lập request context.

## 16. Kiểm thử self link trong HAL JSON

Integration test xác nhận serializer đưa self link vào đúng vị trí của HAL response:

Đoạn test giả định MockMvc được inject và dữ liệu orderId tồn tại trong fixture.

~~~java
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

mockMvc.perform(get("/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.self.href")
        .value(org.hamcrest.Matchers.endsWith("/orders/" + orderId)));
~~~

Với collection, kiểm tra self ở cấp ngoài và self của từng phần tử:

~~~java
mockMvc.perform(get("/orders")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._embedded.orders[0]._links.self.href").exists());
~~~

Tên relation orders trong _embedded phụ thuộc cấu hình relation của ứng dụng. Nếu dùng @Relation, hãy xác nhận itemRelation và collectionRelation phù hợp với hợp đồng JSON đang kiểm thử.

Nếu API công bố URI tuyệt đối, kiểm tra scheme và host theo cấu hình test. Nếu URI thay đổi theo môi trường, kiểm tra phần path hoặc dùng matcher phù hợp thay vì khóa cứng toàn bộ host.

## 17. Những lỗi thường gặp với relation self

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Bỏ self link khỏi tài nguyên có thể truy cập độc lập | Client khó lấy URI của chính tài nguyên từ representation | Thêm self bằng withSelfRel() |
| Dùng self cho tài nguyên liên quan | Client hiểu sai đích là tài nguyên hiện tại | Dùng relation customer, orders hoặc relation phù hợp |
| Dùng self của collection cho từng item | Client theo link item nhưng nhận collection | Tạo self riêng cho mỗi item |
| Tự ghép URL từ ID | Client phụ thuộc cấu trúc route | Dùng href do server công bố |
| Hard-code host và port | Link sai sau proxy hoặc khi đổi môi trường | Dùng WebMvcLinkBuilder và forwarded headers |
| Thêm self hai lần | HAL có thể xuất nhiều link cùng relation ngoài ý muốn | Kiểm tra link đã tồn tại, đặc biệt khi dùng AssemblerSupport |
| Nghĩ self link cho phép PUT hoặc DELETE | Client suy luận sai khả năng thao tác | Công bố affordance hoặc relation hành động riêng |
| Nhầm self với canonical | Gán sai ngữ nghĩa URI ưu tiên | Chỉ dùng canonical khi có phiên bản chuẩn |
| Tạo self cho tài nguyên không tồn tại | Response mâu thuẫn với trạng thái HTTP | Xử lý 404 trước khi assemble |
| Dùng URI template chưa mở rộng làm self của item | Client không có địa chỉ cụ thể của tài nguyên | Dùng URI cụ thể; dành template cho search hoặc collection action |

## 18. Quy trình tạo self link nhất quán

Khi xây dựng representation cho một tài nguyên bằng Spring HATEOAS, hãy thực hiện theo thứ tự:

1. Xác định tài nguyên mà representation đang mô tả.
2. Xác định controller handler trả về chính tài nguyên đó.
3. Tạo URI từ mapping bằng linkTo(methodOn(...)).
4. Gắn relation chuẩn bằng withSelfRel() hoặc IanaLinkRelations.SELF.
5. Đặt self link vào EntityModel hoặc RepresentationModel.
6. Với collection, tạo self cho collection view và self riêng cho từng item có thể truy cập độc lập.
7. Với PagedModel, giữ filter, sort và page hiện tại trong self link.
8. Nếu cần mô tả thao tác, gắn affordance vào link nhưng không nhầm affordance với relation self.
9. Kiểm tra URI sau reverse proxy hoặc gateway.
10. Kiểm thử relation, href và cấu trúc HAL JSON bằng unit test hoặc MockMvc.

Relation self là một thành phần nhỏ nhưng quan trọng của hợp đồng hypermedia. Nó cho client biết URI nhận diện tài nguyên đang được biểu diễn, giúp client điều hướng mà không phải tự xây URL. Khi tạo self từ controller mapping, phân biệt self của item và collection, giữ đúng ngữ cảnh query và kiểm thử href, API Spring HATEOAS có thể công bố địa chỉ tài nguyên nhất quán ngay cả khi cấu trúc route nội bộ thay đổi.

## Tài liệu tham khảo

- [IANA Link Relation Registry – self](https://www.iana.org/assignments/link-relations/)
- [RFC 4287 – The Atom Syndication Format, Link Relation self](https://www.rfc-editor.org/rfc/rfc4287)
- [RFC 8288 – Web Linking](https://www.rfc-editor.org/rfc/rfc8288)
- [Spring HATEOAS Reference Documentation – Link relations](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [IanaLinkRelations API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/IanaLinkRelations.html)
- [LinkBuilderSupport API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/core/LinkBuilderSupport.html)
- [EntityModel API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/EntityModel.html)


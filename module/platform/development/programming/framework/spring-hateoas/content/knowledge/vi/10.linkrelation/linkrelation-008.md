# Relation của collection

Khi một REST API trả về tập hợp tài nguyên, client cần biết các phần tử trong tập hợp đó đại diện cho loại tài nguyên nào. Trong HAL, các phần tử được nhúng nằm trong thuộc tính _embedded và được nhóm dưới một tên quan hệ (relation). Tên quan hệ này được gọi là collection relation.

Spring HATEOAS cho phép định nghĩa tên collection relation bằng annotation @Relation. Nhờ đó, API có thể công bố một tập hợp đơn hàng dưới tên orders, tập hợp khách hàng dưới tên customers hoặc tập hợp dòng hàng dưới tên items. Tên này trở thành một phần của cấu trúc representation mà client dùng để đọc dữ liệu.

Bài học này tập trung vào ý nghĩa của collection relation, cách Spring HATEOAS chọn tên quan hệ, cách tùy chỉnh bằng @Relation, cách phân biệt tên trong _embedded với link relation trong _links và cách kiểm thử hợp đồng HAL.

## 1. Collection relation là gì?

Một collection resource đại diện cho tập hợp các tài nguyên cùng loại. Ví dụ, /api/orders đại diện cho tập hợp đơn hàng, còn /api/orders/42/items đại diện cho các dòng hàng của đơn hàng số 42.

Khi server trả collection theo HAL, các phần tử thường được biểu diễn trong _embedded. Tên thuộc tính chứa danh sách là collection relation:

~~~json
{
  "_embedded": {
    "orders": [
      {
        "id": 42,
        "status": "PENDING"
      },
      {
        "id": 43,
        "status": "PAID"
      }
    ]
  }
}
~~~

Trong ví dụ, orders là collection relation. Nó cho client biết những phần tử được nhúng là các đơn hàng. Tên này có ý nghĩa trong hợp đồng representation, vì client có thể truy cập danh sách bằng khóa _embedded.orders.

Collection relation có ba vai trò quan trọng:

- Phân biệt loại phần tử được nhúng trong một representation.
- Giúp client tìm tập hợp theo ý nghĩa nghiệp vụ thay vì theo tên lớp Java.
- Giữ cấu trúc phản hồi ổn định khi implementation nội bộ thay đổi.

Tên relation nên phản ánh ý nghĩa tài nguyên mà API công bố. Không nên đặt tên theo tên bảng, repository hoặc package của ứng dụng.

## 2. Phân biệt collection relation và link relation

HAL có hai khu vực thường chứa tên relation:

- _embedded chứa các tài nguyên được nhúng; tên khóa bên dưới là collection relation.
- _links chứa các liên kết điều hướng; tên khóa bên dưới là link relation.

Ví dụ một representation khách hàng có thể công bố liên kết đến collection đơn hàng:

~~~json
{
  "id": 7,
  "name": "Nguyen An",
  "_links": {
    "self": {
      "href": "https://api.example.com/api/customers/7"
    },
    "orders": {
      "href": "https://api.example.com/api/customers/7/orders"
    }
  }
}
~~~

Ở đây, orders là link relation. Nó cho client biết liên kết dẫn đến tập hợp đơn hàng của khách hàng.

Khi client theo liên kết đó, server có thể trả về:

~~~json
{
  "_embedded": {
    "orders": [
      {
        "id": 42,
        "status": "PENDING",
        "_links": {
          "self": {
            "href": "https://api.example.com/api/orders/42"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "https://api.example.com/api/customers/7/orders"
    },
    "customer": {
      "href": "https://api.example.com/api/customers/7"
    }
  }
}
~~~

Trong phản hồi thứ hai, orders là collection relation nằm trong _embedded. Từ orders ở phản hồi đầu và orders ở phản hồi sau có cùng tên, nhưng vị trí và vai trò khác nhau: một tên mô tả liên kết đến collection, tên còn lại mô tả loại phần tử trong collection được nhúng.

Hai tên có thể giống nhau để giữ ngữ nghĩa nhất quán, nhưng không phải cùng một trường hay cùng một thao tác. @Relation(collectionRelation = "orders") điều khiển tên collection relation; nó không tự thêm link orders vào _links. Muốn công bố link, controller hoặc assembler vẫn phải tạo link riêng.

## 3. Tùy chỉnh collection relation bằng @Relation

Spring HATEOAS cung cấp annotation @Relation trong package org.springframework.hateoas.server.core. Annotation này cho phép chỉ định quan hệ của một tài nguyên đơn lẻ và quan hệ của collection chứa loại tài nguyên đó.

Ví dụ DTO của đơn hàng:

~~~java
import org.springframework.hateoas.server.core.Relation;

@Relation(
        value = "order",
        collectionRelation = "orders"
)
public record OrderRepresentation(
        Long id,
        String status,
        long total
) {
}
~~~

Trong annotation:

- value đặt tên relation cho một phần tử đơn lẻ khi relation provider cần biểu diễn loại tài nguyên đó.
- collectionRelation đặt tên relation dùng cho collection chứa các phần tử cùng kiểu.

Khi collection được tuần tự hóa theo HAL, collection relation orders giúp tạo khóa _embedded.orders. Cách khai báo này làm rõ tên quan hệ ngay tại kiểu representation và tránh phụ thuộc vào cách suy ra tên từ class.

Nếu chỉ cần tùy chỉnh tên collection, có thể khai báo:

~~~java
@Relation(collectionRelation = "orders")
public record OrderRepresentation(
        Long id,
        String status
) {
}
~~~

Trong dự án Java, mỗi kiểu public ở ví dụ được đặt trong file nguồn riêng. Annotation áp dụng trên kiểu representation được dùng để tuần tự hóa các phần tử collection, không phải trên entity persistence chỉ vì entity đó được lưu trong cơ sở dữ liệu.

## 4. Spring HATEOAS chọn tên relation như thế nào?

Spring HATEOAS sử dụng LinkRelationProvider để xác định tên relation cho kiểu representation. Provider có thể đọc metadata từ @Relation hoặc suy ra relation theo quy tắc đang cấu hình.

Khi một kiểu có @Relation, các giá trị đã khai báo cung cấp tên relation rõ ràng. Nếu không có annotation, tên có thể được suy ra từ kiểu nội dung và provider hiện hành. Kết quả phụ thuộc cấu hình và phiên bản Spring HATEOAS, vì vậy không nên dựa vào suy đoán rằng mọi tên class đều tự động được chuyển thành dạng số nhiều theo một quy tắc cố định.

Ví dụ, nếu class có tên OrderRepresentation, một provider có thể suy ra relation từ tên kiểu. Nếu API yêu cầu đúng tên orders, khai báo collectionRelation tường minh giúp hợp đồng rõ ràng và ít phụ thuộc vào provider.

Với ứng dụng có quy ước relation toàn cục, Spring HATEOAS cho phép cấu hình LinkRelationProvider phù hợp. Cách này hữu ích khi muốn áp dụng một chính sách đặt tên chung cho nhiều resource. Tuy nhiên, với một collection cụ thể có tên nghiệp vụ cần được bảo đảm, @Relation thường dễ đọc và dễ kiểm thử hơn.

## 5. Kết hợp @Relation với RepresentationModelAssembler

Assembler chuyển domain object thành representation. Collection relation được khai báo trên kiểu representation; assembler đảm nhiệm dữ liệu và liên kết cho từng phần tử.

Domain object minh họa:

~~~java
import java.time.Instant;

public record Order(
        Long id,
        String status,
        long total,
        Instant createdAt
) {
}
~~~

Representation:

~~~java
import org.springframework.hateoas.server.core.Relation;
import java.time.Instant;

@Relation(value = "order", collectionRelation = "orders")
public record OrderRepresentation(
        Long id,
        String status,
        long total,
        Instant createdAt
) {
}
~~~

Assembler:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

@Component
public class OrderModelAssembler
        implements RepresentationModelAssembler<
                Order,
                EntityModel<OrderRepresentation>
        > {

    @Override
    public EntityModel<OrderRepresentation> toModel(Order order) {
        OrderRepresentation representation = new OrderRepresentation(
                order.id(),
                order.status(),
                order.total(),
                order.createdAt()
        );

        return EntityModel.of(
                representation,
                linkTo(methodOn(OrderController.class)
                        .one(order.id())).withSelfRel()
        );
    }
}
~~~

Assembler trả EntityModel<OrderRepresentation>. Mỗi phần tử có dữ liệu được chọn cho API và link self. Khi các EntityModel được đặt trong collection, relation provider có thể sử dụng collectionRelation đã khai báo trên OrderRepresentation để đặt tên cho vùng embedded.

Assembler không cần tự tạo tên _embedded.orders. Việc xác định tên collection thuộc về relation metadata và quá trình tuần tự hóa hypermedia. Nhờ đó, cùng assembler có thể được dùng cho nhiều collection mà vẫn giữ quy tắc relation của kiểu representation.

## 6. Tạo collection và công bố link

Giả sử service trả về danh sách đơn hàng:

~~~java
import java.util.List;

public interface OrderService {
    List<Order> findAll();
    Order getRequired(Long id);
}
~~~

Controller dùng assembler để tạo collection:

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
    private final OrderModelAssembler assembler;

    public OrderController(
            OrderService orderService,
            OrderModelAssembler assembler
    ) {
        this.orderService = orderService;
        this.assembler = assembler;
    }

    @GetMapping(value = "/{id}", produces = MediaTypes.HAL_JSON_VALUE)
    public EntityModel<OrderRepresentation> one(@PathVariable Long id) {
        return assembler.toModel(orderService.getRequired(id));
    }

    @GetMapping(produces = MediaTypes.HAL_JSON_VALUE)
    public CollectionModel<EntityModel<OrderRepresentation>> all() {
        return assembler.toCollectionModel(orderService.findAll())
                .add(linkTo(methodOn(OrderController.class)
                        .all()).withSelfRel());
    }
}
~~~

toCollectionModel chuyển từng Order thành EntityModel<OrderRepresentation> thông qua toModel. CollectionModel bao các phần tử và mang link self ở cấp collection. Khi Spring HATEOAS tuần tự hóa phản hồi HAL, tên collection relation được lấy từ metadata của kiểu representation.

Phản hồi minh họa:

~~~json
{
  "_embedded": {
    "orders": [
      {
        "id": 42,
        "status": "PENDING",
        "total": 1250000,
        "createdAt": "2026-11-20T08:30:00Z",
        "_links": {
          "self": {
            "href": "https://api.example.com/api/orders/42"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "https://api.example.com/api/orders"
    }
  }
}
~~~

Ở đây, @Relation tạo tên embedded orders; link self được thêm riêng trong controller. Nếu cần một link đến collection từ một resource khác, assembler của resource đó có thể thêm quan hệ orders trỏ đến endpoint all.

## 7. Quan hệ collection lồng nhau

Một resource cha có thể liên kết đến collection con. Ví dụ khách hàng có tập hợp đơn hàng:

~~~java
@RestController
@RequestMapping("/api/customers")
public class CustomerController {

    @GetMapping(value = "/{customerId}", produces = MediaTypes.HAL_JSON_VALUE)
    public EntityModel<CustomerRepresentation> one(
            @PathVariable Long customerId
    ) {
        Customer customer = customerService.getRequired(customerId);

        return EntityModel.of(
                customerAssembler.toRepresentation(customer),
                linkTo(methodOn(CustomerController.class)
                        .orders(customerId)).withRel("orders")
        );
    }

    @GetMapping(
            value = "/{customerId}/orders",
            produces = MediaTypes.HAL_JSON_VALUE
    )
    public CollectionModel<EntityModel<OrderRepresentation>> orders(
            @PathVariable Long customerId
    ) {
        customerService.getRequired(customerId);
        return orderAssembler.toCollectionModel(
                orderService.findByCustomer(customerId)
        ).add(
                linkTo(methodOn(CustomerController.class)
                        .orders(customerId)).withSelfRel()
        );
    }
}
~~~

Đây là đoạn minh họa tích hợp; các service và assembler tương ứng được giả định đã được khai báo. Resource khách hàng công bố link relation orders. Khi client theo link, collection trả về dùng collection relation orders trong _embedded nhờ metadata của OrderRepresentation.

Tách endpoint collection con có lợi khi tập hợp lớn, cần lọc hoặc phân trang, hoặc client cần truy cập collection độc lập. Nếu tập hợp nhỏ và luôn cần cùng resource cha, API có thể chọn nhúng DTO đơn giản trong representation cha. Khi đó, dữ liệu nhúng không nhất thiết có link riêng cho từng phần tử.

## 8. Chọn tên collection relation

Tên collection relation là một phần của hợp đồng API. Hãy chọn tên có ý nghĩa với client và duy trì ổn định.

| Kiểu tài nguyên | Collection relation gợi ý |
| --- | --- |
| Đơn hàng | orders |
| Khách hàng | customers |
| Dòng hàng | items |
| Bình luận | comments |
| Giao dịch | transactions |

Một số nguyên tắc:

1. Dùng danh từ hoặc tên quan hệ mô tả loại phần tử trong collection.
2. Dùng cùng một tên cho cùng một khái niệm trên các endpoint tương ứng.
3. Tránh dùng tên lớp Java, tên repository hoặc tên bảng làm hợp đồng.
4. Tránh đổi tên relation đã được client sử dụng; nếu cần đổi, hãy xem đó là thay đổi API contract.
5. Kiểm thử tên relation thực tế trong HAL output.

Đối với quan hệ chuẩn, có thể dùng các tên đã đăng ký trong IANA Link Relation Registry khi ngữ nghĩa phù hợp. Với quan hệ mở rộng, chọn tên rõ ràng và tránh xung đột. Trong HAL, các quan hệ mở rộng có thể được định danh bằng URI; CURIE có thể giúp biểu diễn URI relation dưới dạng rút gọn khi API cấu hình cơ chế này.

Không nên dùng quan hệ chuẩn chỉ vì tên có vẻ phù hợp. Ví dụ, self có ý nghĩa là liên kết đến chính tài nguyên hiện tại; không nên dùng self làm tên collection relation cho danh sách đơn hàng. Tên relation cần tuân theo ngữ nghĩa đã công bố.

## 9. Collection relation và tiến hóa API

Client có thể phụ thuộc vào tên _embedded.orders để lấy danh sách. Nếu server đổi tên thành _embedded.orderList mà không có chiến lược tương thích, client có thể không đọc được collection dù URI và dữ liệu không thay đổi.

Vì vậy, collection relation cần được xem là một phần của hợp đồng representation:

- Giữ tên relation ổn định khi chỉ thay đổi implementation nội bộ.
- Bổ sung relation mới cần được cân nhắc với khả năng client cũ bỏ qua thuộc tính chưa biết.
- Đổi hoặc xóa relation đang được client sử dụng cần được quản lý như một thay đổi tương thích.
- Nếu một API cần nhiều representation khác nhau, hãy xác định rõ media type hoặc versioning strategy và kiểm thử từng hợp đồng.

Hypermedia giảm phụ thuộc vào cấu trúc URI bằng cách cung cấp link relation và href, nhưng không có nghĩa tên relation có thể thay đổi tùy ý. Client vẫn cần một từ vựng chung để hiểu dữ liệu và điều hướng.

## 10. Kiểm thử collection relation

Kiểm thử cần xác nhận cả dữ liệu phần tử, tên relation trong _embedded và các link ở cấp collection.

Ví dụ với MockMvc:

~~~java
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.time.Instant;
import java.util.List;

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
    void usesOrdersAsCollectionRelation() throws Exception {
        when(orderService.findAll()).thenReturn(List.of(
                new Order(
                        42L,
                        "PENDING",
                        1250000,
                        Instant.parse("2026-11-20T08:30:00Z")
                )
        ));

        mockMvc.perform(get("/api/orders")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$._embedded.orders.length()").value(1))
                .andExpect(jsonPath("$._embedded.orders[0].id").value(42))
                .andExpect(jsonPath(
                        "$._embedded.orders[0]._links.self.href").exists())
                .andExpect(jsonPath("$._links.self.href").exists());
    }
}
~~~

Đây là ví dụ minh họa. Các kiểu Order, OrderService, OrderController và assembler cần được định nghĩa trong package của ứng dụng. @Import đăng ký assembler trong test slice; service được mock để kiểm soát dữ liệu.

Nên kiểm thử thêm:

- Collection rỗng vẫn có cấu trúc HAL hợp lệ và link self.
- Tên _embedded.orders giữ nguyên theo annotation.
- Mỗi phần tử có link self riêng.
- Link orders ở resource cha trỏ đến endpoint collection nếu API công bố quan hệ đó.
- Collection phân trang vẫn dùng đúng collection relation.
- Media type trả về là application/hal+json khi client yêu cầu.

Không nên chỉ kiểm tra link relation bằng một URL tuyệt đối cố định. Hostname, cổng và context path có thể thay đổi theo môi trường. Hãy kiểm tra tên relation và hành vi của endpoint mà relation dẫn đến.

## 11. Những lỗi thường gặp

**Nhầm collection relation với link relation.** _embedded.orders đặt tên tập hợp phần tử được nhúng; _links.orders mô tả liên kết đến một đích. Hai tên có thể giống nhau nhưng có vai trò khác nhau.

**Chỉ thêm @Relation và nghĩ rằng link collection đã được tạo.** Annotation đặt tên relation khi tuần tự hóa collection. Controller hoặc assembler vẫn phải thêm link nếu client cần điều hướng đến endpoint collection.

**Dùng tên class làm hợp đồng.** Tên lớp có thể thay đổi trong refactor. Dùng collectionRelation tường minh cho các collection quan trọng đối với client.

**Không kiểm tra relation provider.** Nếu không có annotation, tên relation phụ thuộc provider đang cấu hình. Kiểm thử HAL output để biết chính xác tên được phát ra.

**Đổi tên collection relation mà không đánh giá client.** Tên _embedded là một phần của representation contract. Hãy quản lý việc đổi tên như một thay đổi API.

**Dùng một relation không đúng ngữ nghĩa.** Relation phải mô tả ý nghĩa của liên kết hoặc loại collection. Không dùng tên chuẩn chỉ vì thuận tiện.

## 12. Ghi nhớ

Collection relation là tên quan hệ dùng để nhận diện các phần tử của một collection được nhúng trong HAL. Nó xuất hiện dưới _embedded, ví dụ _embedded.orders. Spring HATEOAS dùng LinkRelationProvider để xác định tên; annotation @Relation(value = "order", collectionRelation = "orders") cho phép khai báo tên item relation và collection relation một cách tường minh.

Collection relation khác với link relation trong _links. @Relation(collectionRelation = "orders") đặt tên collection trong representation, còn withRel("orders") tạo link relation trỏ đến một URI. Một API có thể dùng cùng tên cho hai vai trò để giữ ngữ nghĩa nhất quán, nhưng cần hiểu rõ vị trí và chức năng của từng tên.

Hãy chọn tên relation theo ý nghĩa nghiệp vụ, giữ ổn định như một phần của hợp đồng API và kiểm thử HAL output. Khi kết hợp CollectionModel, EntityModel và RepresentationModelAssembler, Spring HATEOAS có thể tạo collection representation rõ ràng, giúp client nhận diện tập hợp và điều hướng theo các liên kết mà server công bố.

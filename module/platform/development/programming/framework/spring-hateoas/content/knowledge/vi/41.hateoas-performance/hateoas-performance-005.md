# Giảm payload

Một representation HATEOAS thường chứa dữ liệu resource, các resource được nhúng trong phần _embedded và những link trong phần _links. Khi API trả một object nhỏ, phần hypermedia thường không đáng kể. Nhưng một collection lớn có thể nhân bản nhiều field, nhúng cả object liên quan và tạo hàng loạt link cho từng item. Kết quả là response nặng, thời gian serialize tăng và client phải tải nhiều dữ liệu mà màn hình hiện tại không dùng.

Giảm payload trong Spring HATEOAS là chọn đúng lượng dữ liệu và metadata cần thiết cho một thao tác. Hãy bắt đầu bằng DTO hoặc projection gọn, chỉ embed phần tóm tắt có ích, giới hạn số item trả về, giữ những link cần cho việc điều hướng và bật HTTP compression khi phù hợp. Mỗi thay đổi cần được đo bằng số byte thực tế cùng thời gian truy vấn, serialize và truyền response.

Bài học này tập trung vào việc giảm kích thước representation HAL mà vẫn giữ được khả năng khám phá API. Các ví dụ dùng đơn hàng, khách hàng và collection đơn hàng để minh họa cách giảm field, embedded resource, link metadata và kích thước response.

## 1. Payload HATEOAS gồm những gì?

Một HAL representation thường có ba phần chính:

- **Resource data**: các field mô tả đối tượng hiện tại, chẳng hạn id, status, total.
- **_links**: các link giúp client điều hướng tới resource hoặc action khác.
- **_embedded**: các representation liên quan được server đưa vào response hiện tại.

Ví dụ một đơn hàng có thể chứa toàn bộ thông tin khách hàng, danh sách dòng hàng và các link:

~~~json
{
  "id": 42,
  "number": "SO-0042",
  "status": "PENDING",
  "total": 1250000,
  "_embedded": {
    "customer": {
      "id": 7,
      "name": "Nguyen An",
      "email": "an@example.com",
      "phone": "0900000000",
      "billingAddress": {
        "street": "12 Nguyen Hue",
        "city": "Ho Chi Minh City"
      }
    },
    "orderLine": [
      {
        "productId": 101,
        "productName": "Keyboard",
        "quantity": 2,
        "unitPrice": 450000,
        "warehouse": "WH-A",
        "stockDetails": {
          "reserved": 2,
          "available": 18
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "https://api.example.com/api/orders/42"
    },
    "customer": {
      "href": "https://api.example.com/api/customers/7"
    },
    "cancel": {
      "href": "https://api.example.com/api/orders/42/cancellation"
    }
  }
}
~~~

Nếu client chỉ cần hiển thị mã đơn, trạng thái, tổng tiền và tên khách hàng, phần địa chỉ, tồn kho và thông tin thanh toán là dư thừa. Những field đó làm response lớn hơn và có thể khiến server phải tải thêm dữ liệu từ database.

Kích thước payload không chỉ là số field. Nó còn phụ thuộc số item, độ dài chuỗi, số link, độ sâu của object nhúng và metadata của từng link. Vì vậy, cần đo response thực tế thay vì chỉ đếm số property trong DTO.

## 2. Bắt đầu bằng DTO tóm tắt

Không nên serialize trực tiếp entity persistence thành representation API. Entity thường có quan hệ hai chiều, field nội bộ, collection lớn hoặc dữ liệu chỉ một số màn hình cần. Hãy định nghĩa DTO riêng cho từng nhu cầu đọc:

~~~java
import java.math.BigDecimal;

public record OrderSummary(
        Long id,
        String number,
        OrderStatus status,
        BigDecimal total,
        String customerName
) {
}
~~~

OrderSummary chỉ mang dữ liệu cần cho danh sách đơn hàng. Trang chi tiết có thể dùng một DTO khác với các field phong phú hơn. Việc tách representation theo use case giúp API không phải gửi mọi field trong mọi response.

Một assembler có thể chuyển domain object sang DTO rồi thêm link:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.stereotype.Component;

@Component
public class OrderSummaryAssembler {

    public EntityModel<OrderSummary> toModel(Order order) {
        OrderSummary summary = new OrderSummary(
                order.getId(),
                order.getNumber(),
                order.getStatus(),
                order.getTotal(),
                order.getCustomer().getName()
        );

        return EntityModel.of(
                summary,
                linkTo(methodOn(OrderController.class)
                        .one(order.getId()))
                        .withSelfRel()
        );
    }
}
~~~

Ở đây mỗi item chỉ mang một link self. Nếu client cần mở chi tiết khách hàng, representation có thể cung cấp thêm relation customer; không cần nhúng toàn bộ customer entity vào danh sách đơn hàng.

DTO không chỉ giúp giảm byte truyền đi. Nó còn xác định rõ dữ liệu công khai, giảm nguy cơ vô tình serialize field nhạy cảm và tránh phụ thuộc vào cấu trúc entity.

## 3. Dùng DTO projection để chỉ tải field cần thiết

Nếu repository tải cả entity rồi assembler mới bỏ field, payload giảm nhưng database và bộ nhớ vẫn có thể phải xử lý object lớn. Spring Data JPA hỗ trợ projection để truy vấn một tập thuộc tính cụ thể.

Ví dụ repository trả DTO projection cho danh sách đơn hàng:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

public interface OrderRepository extends JpaRepository<Order, Long> {

    @Query("""
            select new com.example.api.OrderSummary(
                    o.id, o.number, o.status, o.total, c.name
            )
            from Order o join o.customer c
            """)
    Page<OrderSummary> findSummaries(Pageable pageable);
}
~~~

Trong query này, thay `com.example.api.OrderSummary` bằng package thực tế của record. Constructor expression phải khớp thứ tự và kiểu tham số của constructor DTO. Với interface projection có nested property, cần kiểm tra SQL được sinh ra vì nested property có thể khiến join và materialize nhiều dữ liệu hơn dự kiến; DTO projection với query chọn rõ cột giúp kiểm soát tốt hơn.

Assembler có thể nhận DTO projection trực tiếp thay cho entity. Đây là một overload của phương thức toModel trong ví dụ assembler ở mục trước:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;

public EntityModel<OrderSummary> toModel(OrderSummary summary) {
    return EntityModel.of(
            summary,
            linkTo(methodOn(OrderController.class).one(summary.id()))
                    .withSelfRel()
    );
}
~~~

Như vậy, dữ liệu được giới hạn từ query, DTO và cuối cùng là JSON. Đo cả SQL/query count và payload vì một response nhỏ vẫn có thể được tạo ra từ một truy vấn quá tốn kém.

## 4. Embed bản tóm tắt và giữ link tới resource đầy đủ

HAL cho phép embed representation liên quan. Embed rất hữu ích khi client cần hiển thị nhanh một phần dữ liệu, nhưng nhúng cả resource đầy đủ có thể làm response phình lớn. Một lựa chọn cân bằng là embed summary và cung cấp link tới resource chi tiết.

Spring HATEOAS có HalModelBuilder để tạo HAL representation với preview:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.RepresentationModel;
import org.springframework.hateoas.mediatype.hal.HalModelBuilder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

public record CustomerSummary(Long id, String displayName) {
}

@RestController
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping(value = "/api/orders/{id}", produces = MediaTypes.HAL_JSON_VALUE)
    public RepresentationModel<?> one(@PathVariable Long id) {
        Order order = orderService.getOrder(id);

        OrderSummary summary = new OrderSummary(
                order.getId(),
                order.getNumber(),
                order.getStatus(),
                order.getTotal(),
                order.getCustomer().getName()
        );

        CustomerSummary customer = new CustomerSummary(
                order.getCustomer().getId(),
                order.getCustomer().getName()
        );

        var customerLink = linkTo(methodOn(CustomerController.class)
                .one(order.getCustomer().getId()))
                .withRel("customer");

        var selfLink = linkTo(methodOn(OrderController.class)
                .one(id))
                .withSelfRel();

        return HalModelBuilder.halModelOf(summary)
                .preview(customer)
                .forLink(customerLink)
                .link(selfLink)
                .build();
    }
}
~~~

preview(customer).forLink(customerLink) đưa CustomerSummary vào _embedded.customer và công bố link customer trong _links. Client có thể hiển thị tên khách hàng ngay, đồng thời theo link khi cần chi tiết đầy đủ.

Representation nhận được có dạng:

~~~json
{
  "id": 42,
  "number": "SO-0042",
  "status": "PENDING",
  "total": 1250000,
  "customerName": "Nguyen An",
  "_links": {
    "self": {
      "href": "https://api.example.com/api/orders/42"
    },
    "customer": {
      "href": "https://api.example.com/api/customers/7"
    }
  },
  "_embedded": {
    "customer": {
      "id": 7,
      "displayName": "Nguyen An"
    }
  }
}
~~~

Trong ví dụ này customerName và customer.displayName đang lặp lại cùng thông tin. Nếu client chỉ cần tên qua embedded relation, hãy bỏ customerName khỏi OrderSummary; nếu client cần field phẳng để render danh sách, có thể giữ field đó nhưng cân nhắc bỏ preview. Tránh gửi cùng một dữ liệu ở nhiều vị trí mà không có lý do rõ ràng.

## 5. Chỉ embed những quan hệ client thật sự cần

Không phải quan hệ domain nào cũng cần xuất hiện trong _embedded. Trước khi embed, hãy trả lời:

- Client có cần dữ liệu này ngay trong màn hình hiện tại không?
- Có cần toàn bộ resource hay chỉ vài field tóm tắt?
- Quan hệ này có được dùng ở hầu hết request hay chỉ một số luồng?
- Việc embed có làm nhân số lượng object theo từng item không?
- Client có thể theo link khi cần mà không làm trải nghiệm bị chậm đáng kể không?

Ví dụ danh sách đơn hàng có thể embed customer summary nhưng không embed toàn bộ payments, shipments, auditEvents và inventoryMovements. Các quan hệ ít dùng có thể chỉ công bố link:

~~~json
{
  "_links": {
    "self": {
      "href": "/api/orders/42"
    },
    "customer": {
      "href": "/api/orders/42/customer"
    },
    "payments": {
      "href": "/api/orders/42/payments"
    },
    "shipments": {
      "href": "/api/orders/42/shipments"
    }
  }
}
~~~

Client có thể gọi resource liên quan khi người dùng mở tab thanh toán hoặc giao hàng. Server tránh phải tải và serialize các collection lớn cho mọi request.

Đừng biến quy tắc này thành “không embed gì cả”. Nếu client luôn cần một số field để render và dữ liệu đó nhỏ, embed summary có thể giảm số request và tổng thời gian tải. Hãy so sánh tổng bytes của một response lớn với nhiều response nhỏ, bao gồm cả header và round-trip.

## 6. Tránh nhúng collection không giới hạn

Một lỗi phổ biến là trả tất cả item của một quan hệ:

~~~java
// Không nên trả toàn bộ lịch sử giao dịch trong mọi representation.
List<Payment> payments = paymentRepository.findByOrderId(orderId);
~~~

Nếu một đơn hàng có hàng nghìn payment events, response chi tiết có thể rất lớn. Hãy phân trang collection và chỉ embed một tập nhỏ khi use case cần:

~~~java
Page<PaymentSummary> payments =
        paymentRepository.findSummaryByOrderId(
                orderId,
                PageRequest.of(0, 10)
        );
~~~

Client có thể theo link payments để mở collection đầy đủ, sau đó theo các link next/prev. Giới hạn phải được áp dụng ở query/database, không chỉ cắt list sau khi đã tải toàn bộ dữ liệu vào bộ nhớ.

Với collection lớn, cần giới hạn cả page size tối đa. Nếu client gửi size=100000, server không nên chấp nhận vô điều kiện. Một giới hạn phù hợp giúp giữ response trong ngân sách byte và giảm áp lực lên database.

## 7. Dùng PagedModel để trả collection có giới hạn

PagedModel biểu diễn collection cùng metadata phân trang và các link điều hướng. Spring Data cung cấp PagedResourcesAssembler để chuyển Page thành PagedModel và tạo các link trang theo cấu hình Pageable resolver. Ví dụ sau minh họa cách giới hạn page size tối đa:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.PagedModel;
import org.springframework.web.bind.annotation.GetMapping;

@GetMapping("/api/orders")
public PagedModel<EntityModel<OrderSummary>> list(
        Pageable pageable,
        PagedResourcesAssembler<OrderSummary> pagedAssembler
) {
    int safeSize = Math.min(Math.max(pageable.getPageSize(), 1), 50);
    Pageable boundedPageable = PageRequest.of(
            Math.max(pageable.getPageNumber(), 0),
            safeSize,
            pageable.getSort()
    );

    Page<OrderSummary> result = orderRepository.findSummaries(
            boundedPageable
    );

    return pagedAssembler.toModel(result, orderSummaryAssembler::toModel);
}
~~~

Đây là phần thân của controller minh họa; orderRepository, orderSummaryAssembler và query findSummaries(...) cần được khai báo trong ứng dụng. Với Spring Boot, Spring Data web support thường được auto-configure; ứng dụng Spring không dùng Boot có thể bật hỗ trợ bằng cấu hình Spring Data web phù hợp. PagedResourcesAssembler chuyển Page thành PagedModel, tạo PageMetadata và bổ sung các link phân trang theo Pageable resolver hiện tại. Trong API thực tế, hãy giữ lại filter và sort hiện tại khi tạo link trang tiếp theo để client không mất ngữ cảnh tìm kiếm.

Với ứng dụng Spring không dùng Spring Boot, có thể bật các resolver và assembler cho tham số web bằng cấu hình:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.web.config.EnableSpringDataWebSupport;

@Configuration
@EnableSpringDataWebSupport
class SpringDataWebConfiguration {
}
~~~

PagedModel giúp client khám phá các trang thay vì buộc server gửi toàn bộ collection. Metadata như totalElements và totalPages cũng chiếm byte; chỉ cung cấp loại metadata mà client thực sự dùng. Nếu use case không cần tổng số bản ghi, cân nhắc Slice kết hợp SlicedResourcesAssembler hoặc cursor-based pagination để tránh truy vấn count và metadata không cần thiết.

## 8. Giữ link cần thiết, tránh metadata lặp

Link thường nhỏ hơn dữ liệu embedded, nhưng số lượng link lớn vẫn làm response tăng đáng kể. Một collection 50 item, mỗi item có 8 link, có thể tạo ra hàng trăm link object.

Hãy giữ những link có giá trị cho client:

- self để xác định resource hiện tại.
- Link collection hoặc pagination cần để tiếp tục điều hướng.
- Action link mà client có thể thực hiện ở trạng thái hiện tại.
- Link quan hệ mà client cần truy cập trong use case hiện tại.

Tránh tạo nhiều link khác relation nhưng cùng một target và cùng ý nghĩa chỉ vì mỗi layer tự thêm link riêng. Đặt quy tắc link trong assembler hoặc một component nhất quán để không bị trùng giữa controller, service và RepresentationModelProcessor.

Không xóa link chỉ vì nó chiếm vài chục byte nếu link đó là cách client khám phá action hoặc resource. Hypermedia có giá trị chính ở khả năng điều hướng; tối ưu cần giữ nguyên vocabulary và semantics mà client phụ thuộc.

## 9. Tận dụng cách serialize link gọn của HAL

HAL cho phép một relation chứa một link object hoặc một mảng link object. Khi một relation chỉ có một link, Spring HATEOAS mặc định dùng dạng object đơn:

~~~json
{
  "_links": {
    "self": {
      "href": "/api/orders/42"
    }
  }
}
~~~

Dạng này ngắn hơn mảng một phần tử:

~~~json
{
  "_links": {
    "self": [
      {
        "href": "/api/orders/42"
      }
    ]
  }
}
~~~

Nếu ứng dụng cấu hình HalConfiguration để mọi relation đơn đều serialize thành array, hãy kiểm tra xem client có thực sự cần chính sách đó không. Cấu hình array có thể giúp client parser có một shape cố định, nhưng tăng payload và thay đổi hợp đồng JSON. Chỉ thay đổi sau khi cân nhắc tương thích client.

Ví dụ cấu hình ép một relation đơn thành array:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.mediatype.hal.HalConfiguration;
import org.springframework.hateoas.mediatype.hal.HalConfiguration.RenderSingleLinks;

@Configuration
class HalRenderingConfiguration {

    @Bean
    HalConfiguration halConfiguration() {
        return new HalConfiguration()
                .withRenderSingleLinksFor(
                        IanaLinkRelations.ITEM,
                        RenderSingleLinks.AS_ARRAY
                );
    }
}
~~~

Ví dụ trên cho thấy một cấu hình làm tăng kích thước link relation item. Nếu mục tiêu là response nhỏ, giữ hành vi mặc định dạng object cho relation chỉ có một link, trừ khi hợp đồng client yêu cầu khác.

## 10. CURIE có thể rút gọn extension relation

Extension relation thường được biểu diễn bằng URI tuyệt đối. Với nhiều custom relation, các URI dài lặp lại có thể làm _links lớn. HAL CURIE cho phép serialize relation dưới dạng compact URI:

~~~json
{
  "_links": {
    "curies": {
      "name": "acme",
      "href": "https://api.example.com/rels/{rel}",
      "templated": true
    },
    "acme:approve": {
      "href": "/api/orders/42/approval"
    },
    "acme:cancel": {
      "href": "/api/orders/42/cancellation"
    }
  }
}
~~~

Spring HATEOAS có CurieProvider để cấu hình prefix và URI template. CURIE có thể tiết kiệm byte khi nhiều extension relation cùng dùng một base URI, nhưng nó cũng thêm một link curies và yêu cầu client hiểu cách resolve prefix. Với response chỉ có một custom relation, phần tiết kiệm có thể không đáng kể.

Chỉ dùng CURIE khi nó phù hợp với vocabulary của API và đã được client hỗ trợ. Không thay relation URI bằng tên ngắn tùy ý mà không cung cấp mapping.

## 11. Chỉ serialize field có giá trị khi hợp đồng cho phép

Một số field optional có thể là null. Jackson cho phép bỏ qua chúng khi serialize:

~~~java
import com.fasterxml.jackson.annotation.JsonInclude;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record OrderSummary(
        Long id,
        String number,
        OrderStatus status,
        String note
) {
}
~~~

Khi note là null, field đó không xuất hiện trong JSON. Cách này hữu ích nếu field thực sự optional và client đã được thiết kế để xử lý trường hợp field vắng mặt.

NON_EMPTY còn bỏ qua collection rỗng và chuỗi rỗng. Hãy dùng cẩn thận: một mảng rỗng có thể mang ý nghĩa “đã tải collection và hiện không có phần tử”, trong khi field vắng mặt có thể mang ý nghĩa “không cung cấp dữ liệu này”. Không xóa khác biệt đó chỉ để giảm vài byte.

Không cấu hình bỏ qua null toàn cục trước khi xem xét hợp đồng API. Một thay đổi serialization toàn cục có thể ảnh hưởng đến mọi representation và làm client cũ hiểu sai field.

## 12. Tránh field lớn và lặp trong embedded model

Khi embed nhiều resource, hãy tạo summary model riêng thay vì dùng lại DTO chi tiết. Ví dụ ProductSummary có thể chỉ chứa id, name và thumbnailUrl; representation chi tiết mới chứa mô tả dài, thông số kỹ thuật và danh sách ảnh.

~~~java
public record ProductSummary(
        Long id,
        String name,
        String thumbnailUrl
) {
}
~~~

Một order line có thể embed ProductSummary cùng link tới sản phẩm:

~~~java
public record OrderLineSummary(
        Long id,
        int quantity,
        ProductSummary product
) {
}
~~~

Không lặp lại toàn bộ product description cho từng order line nếu nhiều dòng tham chiếu cùng sản phẩm. Khi một collection có nhiều item trỏ tới cùng resource, cân nhắc chỉ trả product ID/name tóm tắt và link duy nhất phù hợp ở cấp representation, hoặc để client truy cập chi tiết qua resource sản phẩm.

Nếu cần hiển thị ảnh thumbnail, dùng URL thumbnail đã được tối ưu kích thước. Không nhúng binary/base64 image vào JSON HAL; hãy công bố URL tới tài nguyên media.

## 13. Cân nhắc affordance và metadata link

Affordance, HAL-FORMS template, link title, type, hreflang và các thuộc tính link khác có thể giúp client hiểu cách tương tác. Chúng cũng làm response dài hơn.

Hãy đưa metadata vào khi nó giải quyết một nhu cầu thực:

- Client cần biết method và payload shape để thực hiện action động: dùng affordance hoặc HAL-FORMS.
- Client cần hiển thị label trực tiếp từ server: cung cấp title.
- Link trả về media type khác: cung cấp type.
- Link phụ thuộc ngôn ngữ: cân nhắc hreflang.

Nếu client đã có UI và schema ổn định, không cần lặp lại mô tả dài trong từng link. Có thể giữ relation và target cần thiết, còn tài liệu hoặc profile mô tả vocabulary dùng chung.

Không bỏ affordance quan trọng chỉ để giảm byte nếu client dựa vào metadata đó để gửi request đúng. Hãy đo phần tăng thêm và cân nhắc chỉ công bố affordance cho những action khả dụng ở resource hiện tại.

## 14. Nén HTTP response sau khi đã tối ưu representation

Payload JSON/HAL thường có nhiều key lặp lại, vì vậy gzip có thể giảm đáng kể số byte truyền qua mạng. Spring Boot hỗ trợ response compression cho embedded Tomcat, Jetty và Reactor Netty:

~~~properties
server.compression.enabled=true
server.compression.min-response-size=2KB
server.compression.additional-mime-types=application/hal+json
~~~

Mặc định, response phải đạt tối thiểu 2048 byte mới được nén. Danh sách MIME type mặc định có application/json, nhưng không liệt kê application/hal+json; dùng additional-mime-types để bổ sung HAL mà vẫn giữ các loại mặc định. Nếu dùng mime-types, danh sách mặc định sẽ bị thay thế, vì vậy cần khai báo lại các MIME type muốn nén.

Client phải gửi header:

~~~http
Accept-Encoding: gzip
~~~

Server có thể trả:

~~~http
Content-Encoding: gzip
Vary: Accept-Encoding
~~~

Compression giảm bytes truyền qua mạng, nhưng không làm JSON representation logic nhỏ đi. Nó tiêu thụ CPU để nén/giải nén và không có lợi đáng kể với response rất nhỏ. Đo tỷ lệ nén và latency trước khi điều chỉnh ngưỡng.

Không nén response đã được proxy hoặc gateway nén lần nữa. Kiểm tra cấu hình toàn tuyến để tránh double compression hoặc header Content-Encoding không khớp body.

## 15. Đo payload trước và sau khi tối ưu

Đừng dựa vào cảm giác rằng response nhẹ hơn. Hãy đo cùng một resource, cùng dữ liệu fixture, cùng Accept và cùng page size trước và sau thay đổi.

Với MockMvc, có thể lấy số byte của body chưa nén:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@WebMvcTest(OrderController.class)
class OrderPayloadSizeTest {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    OrderService orderService;

    @BeforeEach
    void setUp() {
        when(orderService.getOrder(42L)).thenReturn(TestOrders.order42());
    }

    @Test
    void orderSummaryResponseStaysWithinPayloadBudget() throws Exception {
        MvcResult result = mockMvc.perform(get("/api/orders/42")
                .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$._links.self.href").exists())
                .andReturn();

        int bodyBytes = result.getResponse().getContentAsByteArray().length;

        assertThat(bodyBytes).isLessThan(8 * 1024);
    }
}
~~~

Ngưỡng 8 * 1024 chỉ là ví dụ cho một representation nhỏ. Hãy đặt budget dựa trên dữ liệu thật, yêu cầu sản phẩm và kích thước p95/p99. Test slice cần mock service và fixture để response ổn định; TestOrders.order42() là factory minh họa, hãy thay bằng fixture builder của ứng dụng.

MockMvc đo body JSON trước HTTP compression; nó không thay thế kiểm thử server thực với gzip. Để đo bytes truyền đi, chạy ứng dụng trên embedded server hoặc qua môi trường staging và so sánh response khi có/không có Accept-Encoding: gzip. Với cache dùng chung, bảo đảm response được phân biệt theo Accept-Encoding bằng Vary: Accept-Encoding.

Một lần đo tốt nên ghi:

| Chỉ số | Điều cần biết |
| --- | --- |
| Body bytes chưa nén | Kích thước JSON/HAL sau serialization |
| Transfer bytes | Số byte thực truyền sau compression |
| Số item và số link | Thành phần nào làm payload tăng |
| Query count và thời gian DB | Giảm payload có làm query nặng hơn không |
| Serialization time | Chi phí tạo JSON/HAL |
| p50/p95/p99 response size | Kích thước ở tải thực tế, không chỉ một fixture |

Khi so sánh, dùng cùng dữ liệu và cùng điều kiện. Nếu response mới có ít item hơn, ghi rõ page size; nếu thay đổi cả gzip, tách riêng hiệu quả của payload shaping và compression.

## 16. Dùng cURL để kiểm tra compression

Sau khi bật compression, có thể kiểm tra response từ server:

~~~bash
curl -sS -D headers.txt \
  -H "Accept: application/hal+json" \
  -H "Accept-Encoding: gzip" \
  -o response.gz \
  https://localhost:8080/api/orders/42
~~~

Kiểm tra headers.txt để xác nhận server trả Content-Encoding: gzip và Content-Type phù hợp. Đo kích thước file nén:

~~~bash
wc -c response.gz
~~~

Để so sánh với body chưa nén, gửi request không có Accept-Encoding: gzip và lưu vào file khác. Khi đo trong môi trường có reverse proxy, cần xác định thành phần nào thực hiện compression vì embedded server có thể không phải nơi nén cuối cùng.

## 17. Những tối ưu dễ gây phản tác dụng

**Bỏ mọi link để response ngắn.** Client mất khả năng khám phá và phải hard-code URI. Chỉ bỏ link thật sự dư thừa, giữ relation cần thiết cho điều hướng.

**Embed toàn bộ resource để giảm số request.** Một request lớn có thể tốn nhiều byte và thời gian serialize hơn nhiều request nhỏ. Embed summary theo use case.

**Chỉ cắt collection sau khi đã tải tất cả entity.** Payload giảm nhưng database và bộ nhớ vẫn chịu chi phí. Giới hạn query trước khi materialize.

**Dùng NON_EMPTY toàn cục.** Field vắng mặt và collection rỗng có thể mang ý nghĩa khác nhau. Giữ semantics của hợp đồng.

**Ép tất cả single link thành array.** HAL mặc định dùng object cho một link, dạng này gọn hơn. Chỉ đổi khi client yêu cầu.

**Thêm CURIE cho mọi API.** CURIE hữu ích với nhiều custom relation, nhưng có overhead của link curies. Đo trước khi dùng vì mục đích giảm byte.

**Nén response nhỏ.** Chi phí CPU có thể lớn hơn lợi ích truyền tải. Dùng ngưỡng kích thước hợp lý.

**Tối ưu payload nhưng bỏ qua N+1 query.** Body nhỏ không bảo đảm request nhanh. Đo cả truy vấn, serialization và network.

## 18. Quy trình tối ưu payload

Có thể thực hiện theo thứ tự sau:

1. Chụp một response mẫu và đo body bytes, transfer bytes cùng số item/link.
2. Xác định field, embedded object và metadata chiếm nhiều byte nhất.
3. Tạo DTO/projection theo use case để chỉ tải field cần thiết.
4. Thay embedded entity lớn bằng summary và link tới resource đầy đủ.
5. Phân trang collection và áp dụng giới hạn ở tầng query.
6. Loại bỏ link/metadata thực sự trùng lặp, giữ các relation cần cho client.
7. Kiểm tra HAL rendering mặc định, CURIE và affordance theo nhu cầu.
8. Bật compression cho media type phù hợp và kiểm tra header thực tế.
9. Đo lại p95/p99, query count, serialization time và transfer bytes.
10. Thêm regression test cho payload budget và các relation client cần.

Tối ưu từng thay đổi riêng giúp biết được phần nào mang lại lợi ích và tránh làm mất khả năng tương thích. Khi bỏ field hoặc link khỏi representation công khai, xem đó là thay đổi hợp đồng và kiểm thử client trước khi phát hành.

## 19. Ghi nhớ

Payload HATEOAS tăng chủ yếu do field dư, embedded resource quá sâu, collection không giới hạn và link metadata lặp lại. Hãy định nghĩa DTO/projection gọn theo use case, embed summary khi client cần dữ liệu ngay và cung cấp link tới resource đầy đủ khi cần điều hướng sâu hơn.

PagedModel giúp client khám phá các trang thay vì buộc server gửi toàn bộ collection. HAL mặc định render một link đơn dưới dạng object gọn; CURIE, affordance và link metadata chỉ nên dùng khi có giá trị với client. Spring Boot có thể nén application/hal+json bằng response compression sau khi bổ sung MIME type phù hợp.

Đo body bytes chưa nén, transfer bytes sau nén, số query và thời gian serialize. Giảm payload tốt là giảm dữ liệu không cần thiết mà vẫn giữ nguyên semantics, relation và khả năng điều hướng mà client cần.

## Tài liệu tham khảo

- [Spring HATEOAS Reference – Building HAL representation models](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.hal)
- [Spring HATEOAS Reference – Configuring link rendering](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.hal.link-rendering)
- [Spring HATEOAS Reference – CurieProvider](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.hal.curie-provider)
- [Spring HATEOAS API – HalModelBuilder](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/mediatype/hal/HalModelBuilder.html)
- [Spring HATEOAS API – HalConfiguration](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/mediatype/hal/HalConfiguration.html)
- [Spring HATEOAS API – PagedModel.PageMetadata](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/PagedModel.PageMetadata.html)
- [Spring HATEOAS API – MediaTypes](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/MediaTypes.html)
- [Spring Data API – PagedResourcesAssembler](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/web/PagedResourcesAssembler.html)
- [Spring Boot Reference – Enable HTTP Response Compression](https://docs.spring.io/spring-boot/how-to/webserver.html#howto.webserver.enable-http-response-compression)
- [Spring Data JPA Reference – Projections](https://docs.spring.io/spring-data/jpa/reference/repositories/projections.html)

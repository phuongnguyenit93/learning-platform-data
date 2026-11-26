# Collection embedded

## Mục tiêu

Một representation HAL có thể chứa tài nguyên chính cùng những tài nguyên liên quan được nhúng trong _embedded. Khi tài nguyên liên quan là một danh sách, Spring HATEOAS cho phép nhúng cả collection vào representation gốc. Ví dụ, response của một đơn hàng có thể chứa thông tin đơn hàng, danh sách dòng hàng và danh sách thanh toán trong cùng một document.

Spring HATEOAS cung cấp HalModelBuilder để tạo những HAL document như vậy. Builder hỗ trợ nhúng object đơn, collection, stream và preview gắn với một link. Relation của collection quyết định tên thuộc tính trong _embedded, vì vậy cần thiết kế relation rõ ràng và ổn định.

Sau bài học, bạn có thể:

- Phân biệt collection resource cấp cao nhất với collection được nhúng trong một representation khác.
- Dùng HalModelBuilder để nhúng một hoặc nhiều collection.
- Kiểm soát tên relation bằng @Relation hoặc LinkRelation.
- Biểu diễn collection rỗng mà vẫn giữ relation trong HAL.
- Dùng preview để công bố cả link tới collection và dữ liệu preview được nhúng.
- Kiểm thử cấu trúc _embedded và các relation trong HAL JSON.

## Collection embedded trong HAL là gì?

HAL dùng _embedded để chứa representation của các tài nguyên liên quan ngay trong document hiện tại. Nếu tài nguyên được nhúng là một collection, giá trị của relation tương ứng là một mảng các representation.

Ví dụ, response của một đơn hàng có thể có cấu trúc:

~~~json
{
  "id": "order-42",
  "status": "PAID",
  "_links": {
    "self": {
      "href": "/api/orders/order-42"
    },
    "customer": {
      "href": "/api/customers/customer-7"
    }
  },
  "_embedded": {
    "orderLines": [
      {
        "sku": "BOOK-01",
        "quantity": 2
      },
      {
        "sku": "PEN-02",
        "quantity": 3
      }
    ]
  }
}
~~~

Ở đây:

- Phần dữ liệu gốc mô tả đơn hàng.
- _links.customer cho biết URI để truy cập tài nguyên khách hàng.
- _embedded.orderLines chứa các dòng hàng liên quan ngay trong response.

Nhúng collection giúp client có dữ liệu cần thiết cho một màn hình hoặc một bước xử lý mà không phải gửi thêm request để lấy từng collection liên quan. Mỗi item nhúng có thể chỉ là DTO dữ liệu, hoặc là một representation model có links riêng.

Một collection embedded vẫn là dữ liệu của tài nguyên liên quan. Nó không biến các item thành thuộc tính nghiệp vụ của entity gốc trong mô hình persistence, cũng không thay thế endpoint collection độc lập nếu client cần truy cập, lọc hoặc phân trang collection đó.

## Phân biệt CollectionModel và collection embedded

Hai cách biểu diễn đều có thể tạo ra _embedded trong HAL, nhưng mục đích khác nhau:

| CollectionModel<T> | HalModelBuilder.embed(...) |
|---|---|
| Biểu diễn một collection resource làm representation chính của endpoint. | Nhúng một collection vào một representation HAL có thể đã có tài nguyên chính. |
| Links cấp collection như self, next hoặc search thuộc collection root. | Links cấp document thuộc representation gốc; collection được đặt dưới relation trong _embedded. |
| Phù hợp với GET /api/orders trả danh sách đơn hàng. | Phù hợp với GET /api/orders/{id} trả đơn hàng cùng các dòng hàng liên quan. |
| Có thể dùng PagedModel khi cần metadata phân trang. | Không tự cung cấp page metadata hay links phân trang cho collection nhúng. |

Ví dụ collection resource:

~~~java
import org.springframework.hateoas.CollectionModel;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

CollectionModel<OrderLineModel> lines =
        CollectionModel.of(orderLineModels)
                .add(linkTo(methodOn(OrderController.class)
                        .findLines(orderId)).withSelfRel());
~~~

Đây là representation của collection dòng hàng. Nếu muốn document đơn hàng chứa thêm collection dòng hàng, dùng HalModelBuilder để nhúng danh sách vào representation của đơn hàng. Nếu collection có thể lớn hoặc cần filter, sort và phân trang độc lập, nên công bố link tới collection resource và để client tải theo nhu cầu.

## Dùng HalModelBuilder để nhúng collection

HalModelBuilder nằm trong package org.springframework.hateoas.mediatype.hal. Có thể bắt đầu bằng halModelOf(...) nếu representation có tài nguyên chính, hoặc emptyHalModel() nếu document chỉ chứa các tài nguyên nhúng và links.

Giả sử ứng dụng có model cho dòng hàng:

~~~java
import org.springframework.hateoas.server.core.Relation;

@Relation(itemRelation = "orderLine", collectionRelation = "orderLines")
public class OrderLineModel {

    private final String sku;
    private final int quantity;

    public OrderLineModel(String sku, int quantity) {
        this.sku = sku;
        this.quantity = quantity;
    }

    public String getSku() {
        return sku;
    }

    public int getQuantity() {
        return quantity;
    }
}
~~~

@Relation khai báo relation của một item và relation của collection. Với collection embedded, collectionRelation = "orderLines" sẽ được dùng làm tên key trong _embedded.

Tạo document đơn hàng cùng collection dòng hàng:

~~~java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.mediatype.hal.HalModelBuilder;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

OrderSummary summary = OrderSummary.from(order);

Link self = linkTo(methodOn(OrderController.class)
        .findById(order.getId())).withSelfRel();

var representation = HalModelBuilder.halModelOf(summary)
        .embed(orderLineModels, OrderLineModel.class)
        .link(self)
        .build();
~~~

embed(orderLineModels, OrderLineModel.class) đưa danh sách vào _embedded và dùng relation được suy ra từ kiểu OrderLineModel. link(self) thêm link ở cấp document. build() tạo representation model chứa tài nguyên gốc, collection embedded và các links.

Khi document có embedded entries, HalModelBuilder đánh dấu HAL JSON và HAL-FORMS JSON là các media type ưu tiên cho representation được tạo. Controller vẫn cần trả representation qua HTTP message converter có hỗ trợ hypermedia; client nên gửi Accept phù hợp, chẳng hạn application/hal+json, để nhận đúng cấu trúc HAL.

Khi cần nhúng nhiều collection, gọi embed(...) nhiều lần:

~~~java
var representation = HalModelBuilder.halModelOf(summary)
        .embed(orderLineModels, OrderLineModel.class)
        .embed(paymentSummaries, PaymentSummary.class)
        .embed(shipmentSummaries, ShipmentSummary.class)
        .link(self)
        .build();
~~~

Mỗi collection được đặt dưới relation riêng do kiểu phần tử cung cấp. Điều này giúp client tìm orderLines, paymentSummaries hoặc shipmentSummaries theo quan hệ thay vì dựa vào thứ tự xuất hiện trong JSON.

## Xác định relation cho collection

Tên relation là tên key trong _embedded. Spring HATEOAS sử dụng LinkRelationProvider để xác định relation từ kiểu phần tử. @Relation cho phép khai báo rõ itemRelation và collectionRelation; nếu không có annotation, relation provider áp dụng quy tắc mặc định hoặc pluralization tùy cấu hình classpath.

Có hai cách kiểm soát relation khi nhúng collection:

~~~java
// Suy ra collection relation từ kiểu OrderLineModel và @Relation.
builder.embed(orderLineModels, OrderLineModel.class);

// Chỉ định relation trực tiếp theo hợp đồng API.
builder.embed(orderLineModels, LinkRelation.of("orderLines"));
~~~

Ví dụ dùng relation tường minh:

~~~java
import org.springframework.hateoas.LinkRelation;
import org.springframework.hateoas.mediatype.hal.HalModelBuilder;

var representation = HalModelBuilder.halModelOf(summary)
        .embed(orderLineModels, LinkRelation.of("orderLines"))
        .build();
~~~

Dùng @Relation khi tên relation là đặc điểm ổn định của một kiểu representation được tái sử dụng ở nhiều nơi. Dùng LinkRelation khi document cần một relation riêng theo ngữ cảnh hoặc khi muốn kiểm soát trực tiếp hợp đồng của document đó.

Không dựa vào tên class một cách ngẫu nhiên. Nếu client đang đọc _embedded.orderLines, đổi relation thành _embedded.orderLineModelList có thể phá client dù endpoint và dữ liệu không thay đổi. Hãy kiểm thử relation như một phần của hợp đồng API.

## Xử lý collection rỗng

Khi gọi embed(collection) mà không cung cấp kiểu hoặc relation, builder cần một phần tử để suy ra relation. Nếu collection rỗng, không có kiểu phần tử để suy luận và không có trường tương ứng được thêm vào _embedded.

~~~java
var withoutTypedRelation = HalModelBuilder.emptyHalModel()
        .embed(Collections.emptyList())
        .build();
~~~

Đoạn code trên không thể tạo key collection cụ thể trong _embedded. Nếu client cần phân biệt collection rỗng với collection không được cung cấp, hãy truyền kiểu phần tử hoặc relation:

~~~java
import java.util.Collections;

import org.springframework.hateoas.LinkRelation;
import org.springframework.hateoas.mediatype.hal.HalModelBuilder;

var emptyWithType = HalModelBuilder.emptyHalModel()
        .embed(Collections.emptyList(), OrderLineModel.class)
        .build();

var emptyWithRelation = HalModelBuilder.emptyHalModel()
        .embed(Collections.emptyList(), LinkRelation.of("orderLines"))
        .build();
~~~

Representation sẽ có dạng:

~~~json
{
  "_embedded": {
    "orderLines": []
  }
}
~~~

Overload nhận Class<?> suy ra relation từ kiểu được cung cấp; overload nhận LinkRelation dùng đúng relation truyền vào. Đây là cách biểu diễn rõ ràng khi collection tồn tại nhưng hiện chưa có phần tử.

Với Stream, builder cũng có các overload embed(stream, type) và embed(stream, relation). Stream được tiêu thụ ngay khi gọi phương thức; builder thu thập kết quả để đưa vào representation. Các overload có type hoặc relation cũng giữ được key cho stream rỗng. Không truyền lại cùng một Stream sau khi đã embed vì Stream chỉ được tiêu thụ một lần.

## Kết hợp collection embedded với link bằng preview

Đôi khi client cần cả hai thông tin: một link để tải collection độc lập và một bản preview của collection ngay trong response hiện tại. preview(...).forLink(...) biểu diễn đúng mẫu này.

~~~java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.mediatype.hal.HalModelBuilder;

Link linesLink = linkTo(methodOn(OrderController.class)
        .findLines(order.getId())).withRel("orderLines");

var representation = HalModelBuilder.halModelOf(summary)
        .preview(orderLineModels, OrderLineModel.class)
        .forLink(linesLink)
        .link(self)
        .build();
~~~

preview(...) bắt đầu khai báo dữ liệu preview. forLink(linesLink) kết thúc cấu hình preview bằng link đích. Spring HATEOAS thêm link vào _links và đặt dữ liệu preview trong _embedded dưới cùng relation orderLines.

Kết quả minh họa:

~~~json
{
  "id": "order-42",
  "_links": {
    "self": {
      "href": "/api/orders/order-42"
    },
    "orderLines": {
      "href": "/api/orders/order-42/lines"
    }
  },
  "_embedded": {
    "orderLines": [
      {
        "sku": "BOOK-01",
        "quantity": 2
      }
    ]
  }
}
~~~

Khác biệt giữa hai cách:

- embed(collection, ...) chỉ thêm collection vào _embedded; nó không tự tạo link tới endpoint collection.
- preview(collection, ...).forLink(link) thêm cả link và dữ liệu preview dưới cùng relation.

Nếu preview có thể rỗng, dùng overload preview(collection, type) để builder có kiểu dự phòng xác định relation. Điều này giữ relation nhất quán ngay cả khi không có phần tử preview.

## Khi nào nên nhúng collection?

Nhúng collection hữu ích khi các phần tử liên quan nhỏ, thường được hiển thị cùng tài nguyên gốc và client cần chúng ngay trong một lần đọc. Ví dụ:

- Đơn hàng cùng các dòng hàng.
- Dự án cùng một số thành viên tham gia.
- Hồ sơ khách hàng cùng một vài địa chỉ giao hàng.
- Bài viết cùng danh sách nhãn hoặc tài liệu đính kèm nhẹ.

Nên cân nhắc chỉ cung cấp link tới collection khi:

- Collection có thể chứa rất nhiều phần tử.
- Client cần filter, sort hoặc phân trang độc lập.
- Dữ liệu thay đổi thường xuyên và không nên sao chép vào nhiều representation.
- Client chỉ cần collection trong một số luồng sử dụng.
- Kích thước response tăng đáng kể khi nhúng.

Có thể kết hợp cả link và preview: client nhận một phần dữ liệu phổ biến ngay trong response, sau đó theo link để lấy collection đầy đủ hoặc mới nhất khi cần.

Không nên nhúng toàn bộ entity persistence trực tiếp. Hãy chuyển các phần tử thành DTO hoặc representation model chỉ chứa trường được phép công khai. Nếu phần tử cần điều hướng riêng, dùng kiểu model có links; nếu chỉ cần dữ liệu tóm tắt, DTO thuần thường đủ.

## Kiểm thử collection embedded

MockMvc có thể xác minh relation, dữ liệu item và link ở cấp document:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;

mockMvc.perform(get("/api/orders/{id}", orderId)
                .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$._links.self.href").exists())
        .andExpect(jsonPath("$._embedded.orderLines").isArray())
        .andExpect(jsonPath("$._embedded.orderLines[0].sku")
                .value("BOOK-01"))
        .andExpect(jsonPath("$._embedded.orderLines[0].quantity")
                .value(2));
~~~

Với collection rỗng, xác minh relation vẫn tồn tại và mảng không có phần tử:

~~~java
mockMvc.perform(get("/api/orders/{id}", emptyOrderId)
                .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$._embedded.orderLines").isArray())
        .andExpect(jsonPath("$._embedded.orderLines").isEmpty());
~~~

Nếu dùng preview, kiểm tra cả $._links.orderLines.href và $._embedded.orderLines. Nếu dùng nhiều collection, xác minh mỗi relation chứa đúng loại phần tử. Những kiểm thử này phát hiện trường hợp đổi @Relation, đổi relation tường minh hoặc vô tình bỏ collection khỏi document.

## Những lỗi thường gặp

- **Nhầm collection embedded với collection resource:** collection embedded nằm trong representation khác; collection resource là representation chính của endpoint. Chọn CollectionModel hoặc HalModelBuilder theo mục đích.
- **Cho rằng embed tự tạo link:** embed(...) chỉ thêm dữ liệu vào _embedded. Dùng preview(...).forLink(...) nếu cần cả link và preview.
- **Không đặt relation ổn định:** tên key trong _embedded là một phần hợp đồng mà client có thể phụ thuộc.
- **Mất collection rỗng:** embed(collection) không thể suy ra relation khi collection không có phần tử. Truyền kiểu hoặc LinkRelation tường minh.
- **Nhúng collection quá lớn:** response nặng, khó cache và khó cập nhật. Cân nhắc link tới collection phân trang.
- **Đưa entity JPA trực tiếp vào document:** có thể lộ trường nội bộ hoặc kích hoạt lazy loading. Chuyển thành DTO/model công khai.
- **Mong item DTO tự có links:** DTO thuần chỉ chứa dữ liệu. Dùng RepresentationModel hoặc EntityModel nếu từng item cần links.
- **Không phân biệt link cấp document và link cấp item:** link thêm bằng HalModelBuilder.link(...) thuộc root document; links của item cần nằm trong representation của item đó.

## Quy trình xây dựng collection embedded

1. Xác định collection là tài nguyên chính hay dữ liệu liên quan được nhúng trong tài nguyên khác.
2. Chọn DTO hoặc representation model cho từng item và chỉ đưa trường cần công khai vào response.
3. Định nghĩa collection relation bằng @Relation hoặc chọn LinkRelation tường minh.
4. Dùng HalModelBuilder.halModelOf(...) để tạo document có tài nguyên gốc, hoặc emptyHalModel() nếu chỉ cần các phần nhúng.
5. Gọi embed(collection, type/relation) để nhúng collection; dùng preview(...).forLink(...) khi cần thêm link tới collection.
6. Truyền type hoặc relation cho collection rỗng để key trong _embedded vẫn được giữ.
7. Kiểm thử relation, item data, link preview, collection rỗng và kích thước response.

HalModelBuilder giúp ghép tài nguyên gốc với một hoặc nhiều collection embedded theo cách rõ ràng. Khi relation được kiểm soát ổn định và collection được chọn theo nhu cầu thực tế của client, HAL document có thể cung cấp đủ dữ liệu liên quan trong một response mà vẫn giữ khả năng điều hướng tới các tài nguyên độc lập.

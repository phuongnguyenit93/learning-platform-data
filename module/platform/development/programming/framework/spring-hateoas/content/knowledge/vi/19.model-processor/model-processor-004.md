# Processor cho collection

Trong Spring HATEOAS, `RepresentationModelProcessor<T>` cho phép hậu xử lý một representation model trước khi Spring serialize nó thành HTTP response. Khi cần bổ sung link ở cấp tập hợp, có thể khai báo processor nhận `CollectionModel` chứa các model phần tử. Processor này phù hợp để thêm những quan hệ dùng chung cho collection như `search`, `create` hoặc một link điều hướng theo chính sách của ứng dụng.

Điều quan trọng là phân biệt link cấp collection với link của từng phần tử. `CollectionModel` đại diện cho toàn bộ tập hợp; mỗi `EntityModel` bên trong đại diện cho một tài nguyên riêng. Processor cho collection thao tác trên model ngoài cùng, còn các link `self`, `customer`, `cancel` của từng phần tử thường được tạo trong assembler hoặc processor dành cho `EntityModel`.

## CollectionModel và RepresentationModelProcessor

`CollectionModel<T>` là representation model chứa một tập hợp các phần tử kiểu `T` và có thể mang các link ở cấp collection. Ví dụ:

```java
CollectionModel<EntityModel<OrderRepresentation>>
```

Kiểu trên có nghĩa collection chứa các `EntityModel<OrderRepresentation>`. Mỗi model con có thể chứa dữ liệu và link riêng; `CollectionModel` có thể chứa thêm link `self`, `search`, `create` hoặc các relation liên quan tới tập hợp.

Giao diện processor có dạng tổng quát:

```java
public interface RepresentationModelProcessor<T extends RepresentationModel<?>> {
    T process(T model);
}
```

`T` xác định chính xác kiểu representation mà processor nhận và trả về. Với collection đơn hàng, khai báo thường dùng là:

```java
RepresentationModelProcessor<CollectionModel<EntityModel<OrderRepresentation>>>
```

Phương thức `process` nhận model đã được tạo, bổ sung hoặc điều chỉnh metadata hypermedia, rồi trả lại model. Processor không thay thế repository, service hay assembler; nó không nên truy vấn từng phần tử hoặc thực hiện nghiệp vụ ghi dữ liệu.

## Vị trí của processor trong luồng tạo response

Một luồng xử lý collection thường gồm các bước:

1. Controller gọi service hoặc repository để lấy dữ liệu collection.
2. Assembler ánh xạ từng domain object thành `EntityModel` và gắn link riêng cho từng phần tử.
3. Controller hoặc assembler tạo `CollectionModel` và gắn các link cấp tập hợp đã biết.
4. Spring HATEOAS áp dụng các `RepresentationModelProcessor` phù hợp đã được đăng ký trong ứng dụng.
5. Message converter serialize representation thành media type đã thương lượng, ví dụ HAL JSON.

Processor được đăng ký như Spring bean, thường bằng `@Component`. Trong ứng dụng Spring MVC, Spring HATEOAS tích hợp bước áp dụng processor vào quá trình trả representation model. Việc khai báo kiểu generic phù hợp rất quan trọng: processor cho `CollectionModel<EntityModel<OrderRepresentation>>` được thiết kế để xử lý collection đơn hàng có đúng kiểu đó.

## Ví dụ: bổ sung search và create link cho collection

Giả sử endpoint `/orders` trả về danh sách đơn hàng. Collection cần công bố link tìm kiếm và chỉ công bố link tạo mới khi chính sách cho phép người dùng hiện tại tạo đơn hàng.

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;
import org.springframework.hateoas.server.RepresentationModelProcessor;
import org.springframework.stereotype.Component;

@Component
class OrderCollectionProcessor implements
        RepresentationModelProcessor<CollectionModel<EntityModel<OrderRepresentation>>> {

    private static final LinkRelation CREATE_ORDER =
        LinkRelation.of("https://api.example.com/rels/create-order");

    private final OrderPolicy orderPolicy;

    OrderCollectionProcessor(OrderPolicy orderPolicy) {
        this.orderPolicy = orderPolicy;
    }

    @Override
    public CollectionModel<EntityModel<OrderRepresentation>> process(
            CollectionModel<EntityModel<OrderRepresentation>> model) {

        if (model.getLink(IanaLinkRelations.SEARCH).isEmpty()) {
            model.add(Link.of("/orders{?status,page,size}",
                IanaLinkRelations.SEARCH));
        }

        if (orderPolicy.canCreateOrder()
                && model.getLink(CREATE_ORDER).isEmpty()) {
            model.add(linkTo(methodOn(OrderController.class).create(null))
                .withRel(CREATE_ORDER)
                .andAffordance(afford(
                    methodOn(OrderController.class).create(null))));
        }

        return model;
    }
}
```

`OrderRepresentation`, `OrderController` và `OrderPolicy` là các kiểu thuộc ứng dụng minh họa. `OrderPolicy.canCreateOrder()` cần đánh giá quyền của người gọi và điều kiện nghiệp vụ hiện tại. Relation `search` là relation chuẩn; `create-order` là extension relation URI do API sở hữu. `Link.of(...)` tạo link template cho truy vấn; link tạo mới được gắn affordance dựa trên mapping POST của controller.

Processor giữ nguyên nội dung collection và các link đã có. Nó chỉ bổ sung link khi relation tương ứng chưa tồn tại, tránh tạo link trùng nếu assembler hoặc controller đã chịu trách nhiệm cho relation đó. Trong ứng dụng thực tế, URI template tìm kiếm cần phản ánh base path, context path và route công khai; không hardcode đường dẫn tương đối nếu ứng dụng triển khai dưới một prefix khác.

## Link cấp collection và link của từng phần tử

Hai cấp link có mục đích khác nhau:

| Vị trí | Ví dụ relation | Ý nghĩa |
| --- | --- | --- |
| `CollectionModel` | `self` | Chính collection hoặc view collection hiện tại |
| `CollectionModel` | `search` | Cách tìm kiếm/lọc tập hợp |
| `CollectionModel` | `create-order` | Điểm vào tạo một phần tử mới |
| `EntityModel<OrderRepresentation>` | `self` | Một đơn hàng cụ thể |
| `EntityModel<OrderRepresentation>` | `customer` | Khách hàng liên quan tới đơn hàng |
| `EntityModel<OrderRepresentation>` | `cancel` | Thao tác trên chính đơn hàng đó |

Không thêm link `cancel` vào collection chỉ vì một vài phần tử có thể hủy. Nếu mỗi đơn hàng có trạng thái khác nhau, link hủy nên nằm trên representation của từng đơn hàng đủ điều kiện. Processor collection chỉ nên công bố những thao tác có ý nghĩa với toàn bộ tập hợp hoặc với collection như một resource.

Tương tự, link `self` của collection không thay thế self link của từng phần tử. Client dùng `_links.self` ở cấp ngoài để truy cập lại collection; self link nằm trong từng phần tử nhúng giúp truy cập tài nguyên cụ thể.

## Processor cho collection rỗng

Collection rỗng vẫn là một resource hợp lệ. Dù `_embedded` không có phần tử, representation vẫn có thể chứa link `self`, `search` và `create` nếu những tương tác đó khả dụng.

```java
CollectionModel<EntityModel<OrderRepresentation>> empty =
    CollectionModel.empty();
```

Processor vẫn có thể nhận collection rỗng và bổ sung các link cấp collection. Đây là lợi ích quan trọng: client vẫn khám phá được cách tìm kiếm hoặc tạo phần tử đầu tiên, ngay cả khi collection chưa có dữ liệu.

Không suy luận rằng collection rỗng đồng nghĩa người dùng được phép tạo mới. Quyền tạo phải được đánh giá riêng qua policy/service và endpoint POST vẫn kiểm tra quyền khi nhận request.

## Phân trang và PagedModel

`PagedModel<T>` biểu diễn collection có metadata phân trang và kế thừa cấu trúc collection model. Khi controller dùng `PagedResourcesAssembler`, Spring HATEOAS đã có thể tạo các link `first`, `prev`, `self`, `next` và `last` dựa trên `Page<T>`.

Nếu cần bổ sung link riêng cho representation phân trang, có thể khai báo processor chuyên biệt theo kiểu `PagedModel` mà endpoint trả về:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.PagedModel;
import org.springframework.hateoas.server.RepresentationModelProcessor;
import org.springframework.stereotype.Component;

@Component
class OrderPagedModelProcessor implements
        RepresentationModelProcessor<PagedModel<EntityModel<OrderRepresentation>>> {

    @Override
    public PagedModel<EntityModel<OrderRepresentation>> process(
            PagedModel<EntityModel<OrderRepresentation>> model) {

        if (model.getLink(IanaLinkRelations.SEARCH).isEmpty()) {
            model.add(Link.of("/orders{?status,page,size}",
                IanaLinkRelations.SEARCH));
        }

        return model;
    }
}
```

Ví dụ giả định controller trả `PagedModel<EntityModel<OrderRepresentation>>`. Processor chỉ thêm `search` và giữ nguyên metadata `page` cùng các link điều hướng do `PagedResourcesAssembler` tạo. Tránh tự thay `next` hoặc `prev` nếu không có yêu cầu rõ ràng, vì những link này phải phản ánh chính xác trang hiện tại và query đang áp dụng.

Khi xử lý `PagedModel`, nên khai báo processor theo đúng kiểu model endpoint công bố và kiểm thử qua HTTP. Cách này làm rõ mục tiêu xử lý, đồng thời giúp phát hiện khác biệt trong cơ chế chọn processor giữa các phiên bản Spring HATEOAS.

## Tạo collection bằng assembler trước khi processor chạy

Assembler nên tập trung ánh xạ phần tử và tạo collection model. Ví dụ:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import java.util.List;
import java.util.stream.Collectors;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.stereotype.Component;

@Component
class OrderCollectionAssembler {

    private final OrderModelAssembler orderModelAssembler;

    OrderCollectionAssembler(OrderModelAssembler orderModelAssembler) {
        this.orderModelAssembler = orderModelAssembler;
    }

    CollectionModel<EntityModel<OrderRepresentation>> toModel(List<Order> orders) {
        List<EntityModel<OrderRepresentation>> items = orders.stream()
            .map(orderModelAssembler::toModel)
            .collect(Collectors.toList());

        return CollectionModel.of(items,
            linkTo(methodOn(OrderController.class).all()).withSelfRel());
    }
}
```

Assembler ánh xạ từng `Order` và thêm self link của collection. Processor có thể bổ sung `search` hoặc `create-order` sau đó. Với Java trước phiên bản 16, thay `Stream.toList()` bằng `collect(Collectors.toList())`.

Không nên chuyển toàn bộ logic tạo representation sang processor. Assembler biết cách ánh xạ domain object thành model; processor áp dụng quy tắc hypermedia dùng chung hoặc có điều kiện cho model đã tạo. Ranh giới này giúp code dễ kiểm thử và dễ thay đổi.

## Điều kiện và ngữ cảnh request

Processor có thể dùng một policy/service để quyết định link có khả dụng hay không. Các điều kiện phổ biến gồm:

- Người dùng hiện tại có quyền tạo hoặc quản lý loại tài nguyên này.
- Hệ thống đang mở nhận đơn hoặc đang ở chế độ chỉ đọc.
- Collection thuộc tenant hoặc tổ chức mà người gọi được phép truy cập.
- Tính năng tìm kiếm nâng cao được bật cho nhóm người dùng hiện tại.

Nên đưa quy tắc vào một service/policy có tên rõ ràng thay vì nhúng logic phức tạp vào `process`. Nếu cần dữ liệu tenant hoặc user hiện tại, policy nên đọc từ cơ chế security/request context được ứng dụng quản lý. Tránh lưu thông tin request vào field của processor singleton vì có thể làm lẫn dữ liệu giữa các request đồng thời.

Processor nên tránh truy vấn database cho từng phần tử trong collection. Nếu cần đánh giá quyền theo từng item, hãy nạp dữ liệu cần thiết theo lô trong service/assembler hoặc dùng một policy có thể kiểm tra trên dữ liệu đã tải. Nếu mỗi item đều phát sinh một query, response collection lớn sẽ gặp vấn đề N+1 và tăng độ trễ.

## Collection processor không thay thế bảo mật

Việc không công bố link `create-order` hoặc `cancel` chỉ giúp client hiểu tương tác nào được API quảng bá trong representation hiện tại. Nó không phải cơ chế phân quyền. Client vẫn có thể tự gửi request tới URI đã biết hoặc đoán được.

Endpoint đích phải luôn xác thực người gọi, kiểm tra quyền, tenant, trạng thái nghiệp vụ và dữ liệu đầu vào. Policy trong processor và policy tại endpoint nên dùng chung quy tắc nghiệp vụ nếu có thể, nhưng endpoint vẫn là nơi quyết định cuối cùng vì trạng thái có thể thay đổi sau khi representation được trả về.

## HAL JSON sau khi processor áp dụng

Một collection representation sau khi processor bổ sung link có thể trông như sau:

```json
{
  "_embedded": {
    "orders": [
      {
        "id": "7a8b...",
        "status": "PENDING",
        "_links": {
          "self": {
            "href": "https://api.example.com/orders/7a8b..."
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "https://api.example.com/orders"
    },
    "search": {
      "href": "https://api.example.com/orders{?status,page,size}",
      "templated": true
    },
    "https://api.example.com/rels/create-order": {
      "href": "https://api.example.com/orders"
    }
  }
}
```

`_embedded.orders` chứa representation của từng đơn hàng; link `self` của từng phần tử trỏ tới item resource. `_links` ngoài cùng chứa quan hệ của collection. Nếu policy từ chối quyền tạo, relation `create-order` sẽ không xuất hiện. Tùy media type, affordance có thể được biểu diễn bổ sung; HAL JSON cơ bản chỉ cho biết link và relation.

## Kiểm thử processor cho collection

Nên kiểm tra processor trực tiếp ở unit test và kiểm tra response cuối qua MockMvc. Unit test xác nhận processor thêm link nhưng giữ nguyên phần tử:

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.when;

import java.util.List;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.LinkRelation;

CollectionModel<EntityModel<OrderRepresentation>> input =
    CollectionModel.of(List.of(orderModel));

when(orderPolicy.canCreateOrder()).thenReturn(true);

var result = processor.process(input);

assertThat(result.getContent()).containsExactly(orderModel);
assertThat(result.getLink(IanaLinkRelations.SEARCH)).isPresent();
assertThat(result.getLink(LinkRelation.of(
    "https://api.example.com/rels/create-order"))).isPresent();
```

Đoạn test giả định `processor` là instance của `OrderCollectionProcessor`, `orderPolicy` là mock Mockito và `orderModel` là model phần tử được tạo từ fixture. Phần khởi tạo fixture được lược bỏ để tập trung vào hành vi của processor.

Khi policy từ chối, cần xác nhận link tạo mới không được thêm:

```java
import static org.mockito.Mockito.when;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.LinkRelation;

when(orderPolicy.canCreateOrder()).thenReturn(false);

CollectionModel<EntityModel<OrderRepresentation>> result =
    processor.process(CollectionModel.empty());

assertThat(result.getLink(LinkRelation.of(
    "https://api.example.com/rels/create-order"))).isEmpty();
assertThat(result.getLink(IanaLinkRelations.SEARCH)).isPresent();
```

Integration test xác nhận processor đã được Spring phát hiện và áp dụng khi serialize response:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;

mockMvc.perform(get("/orders").accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.search.templated").value(true))
    .andExpect(jsonPath(
        "$._links['https://api.example.com/rels/create-order'].href").exists())
    .andExpect(jsonPath("$._embedded.orders").isArray());
```

Test HTTP ở trên giả định fixture tạo ít nhất một đơn hàng để `_embedded.orders` được serialize thành mảng. Với collection rỗng, hãy kiểm tra các link cấp collection và hành vi `_embedded` theo cấu hình HAL của ứng dụng.

Test bổ sung nên bao gồm collection rỗng, collection đã có sẵn link, người dùng có và không có quyền, tenant khác nhau, và response phân trang. Nếu assembler đã thêm `search` hoặc `create-order`, processor không nên tạo link trùng.

## Lỗi thường gặp

- **Khai báo sai generic type:** processor không khớp kiểu collection controller trả về. Dùng đúng `CollectionModel<EntityModel<...>>` hoặc kiểu model thực tế.
- **Nhầm cấp link:** thêm action link của từng đơn hàng lên collection, khiến client hiểu sai phạm vi thao tác.
- **Làm mất link có sẵn:** tạo model mới hoặc thay link thay vì bổ sung vào model nhận được.
- **Thêm link trùng:** không kiểm tra relation đã tồn tại trước khi bổ sung.
- **Gắn nghiệp vụ vào processor:** truy vấn hoặc cập nhật dữ liệu trong `process` làm thành phần trình bày khó kiểm thử.
- **Phát sinh N+1 query:** kiểm tra từng phần tử bằng truy vấn riêng.
- **Dùng link như quyền truy cập:** ẩn link nhưng không bảo vệ endpoint.
- **Can thiệp link phân trang tùy tiện:** làm sai `next`, `prev` hoặc query filter do assembler phân trang đã tạo.

`RepresentationModelProcessor` cho collection là nơi thích hợp để áp dụng quy tắc hypermedia chung lên `CollectionModel`. Giữ assembler chịu trách nhiệm ánh xạ phần tử, để processor bổ sung link cấp tập hợp, bảo toàn link phân trang và kiểm thử response HAL giúp API công bố khả năng tìm kiếm, tạo mới và điều hướng một cách nhất quán.

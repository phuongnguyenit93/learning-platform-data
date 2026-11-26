# Kết quả rỗng

## Mục tiêu

Một endpoint tìm kiếm có thể nhận filter hợp lệ nhưng không tìm thấy bản ghi nào phù hợp. Trong REST API dùng Spring HATEOAS, response rỗng vẫn cần mô tả collection, link quay lại truy vấn hiện tại và khả năng bắt đầu một truy vấn mới. Client nhờ đó tiếp tục khám phá API thay vì nhận một response không có thông tin điều hướng.

Spring HATEOAS cung cấp CollectionModel và PagedModel để biểu diễn collection, kể cả khi collection không có phần tử. Khi không có phần tử, Java type erasure khiến framework không thể suy ra kiểu phần tử từ nội dung collection. Cần khai báo fallback type để HAL có thể xác định embedded relation và để RepresentationModelProcessor tìm đúng processor.

Sau bài học, bạn có thể:

- Phân biệt tìm kiếm không có kết quả với trang được yêu cầu nằm ngoài phạm vi.
- Trả collection rỗng với HTTP 200 và hypermedia links.
- Giữ embedded relation ổn định bằng CollectionModel.empty(Class) hoặc withFallbackType(...).
- Dùng PagedResourcesAssembler.toEmptyModel(...) cho trang không có content.
- Duy trì self link và search link ngay cả khi không có kết quả.
- Hiểu vì sao processor không được áp dụng mặc định cho CollectionModel rỗng.
- Kiểm thử response HAL của truy vấn không có kết quả.

## Kết quả rỗng vẫn là một collection resource

Giả sử client tìm các đơn hàng đã lưu trữ:

~~~http
GET /api/orders?status=ARCHIVED
Accept: application/hal+json
~~~

Filter hợp lệ, endpoint hoạt động bình thường, nhưng không có đơn hàng nào có trạng thái ARCHIVED. Đây là một kết quả tìm kiếm rỗng, không phải lỗi định tuyến hay một item resource không tồn tại.

Với endpoint collection, nên trả HTTP 200 OK cùng representation của collection rỗng. Response có thể chứa:

- Một embedded collection rỗng để client biết tập kết quả có kiểu tài nguyên nào.
- Link self trỏ tới chính truy vấn đã thực hiện, bao gồm filter hiện tại.
- Link search để client bắt đầu một truy vấn khác.
- Metadata phân trang nếu endpoint hỗ trợ pagination.

Ví dụ HAL:

~~~json
{
  "_embedded": {
    "orders": []
  },
  "_links": {
    "self": {
      "href": "/api/orders?status=ARCHIVED"
    },
    "search": {
      "href": "/api/orders{?status,customerName,page,size,sort}",
      "templated": true
    }
  }
}
~~~

Client có thể đọc self để biết truy vấn nào vừa được thực hiện và dùng search để cung cấp filter khác. Việc không có item không làm mất khả năng điều hướng.

Không nên trả 404 Not Found chỉ vì collection tìm kiếm không có phần tử. 404 phù hợp khi client yêu cầu một tài nguyên cụ thể không tồn tại, ví dụ GET /api/orders/{id}. Không nên dùng 204 No Content nếu client cần nhận links hoặc metadata, vì status 204 không có response body.

## Phân biệt ba tình huống

Một response có content rỗng có thể xuất phát từ những nguyên nhân khác nhau:

| Tình huống | Content | Metadata | Cách xử lý |
|---|---:|---|---|
| Filter hợp lệ nhưng không có bản ghi phù hợp | Rỗng | totalElements = 0, totalPages = 0 | Trả collection rỗng, giữ search/self links. |
| Có kết quả nhưng client yêu cầu page vượt phạm vi | Rỗng | totalElements > 0, totalPages > 0 | Giữ metadata thật, cung cấp links để quay về trang hợp lệ. |
| Filter hoặc tham số không hợp lệ | Không thực hiện truy vấn hợp lệ | Không phải kết quả tìm kiếm | Trả lỗi 400 theo hợp đồng validation. |

Ví dụ, database có 42 đơn hàng phù hợp với filter và size là 20. API có 3 trang. Nếu client yêu cầu page=8, content trang hiện tại rỗng nhưng totalElements vẫn là 42 và totalPages vẫn là 3. Client cần quay về first hoặc last thay vì nghĩ rằng filter không tìm thấy dữ liệu.

Với một item resource, tình huống khác hẳn:

~~~http
GET /api/orders/does-not-exist
~~~

Nếu ID không tồn tại, controller có thể trả 404. Đừng trộn ngữ nghĩa “không tìm thấy item” với “tìm kiếm collection không có kết quả”.

## Khai báo relation cho collection rỗng

Khi collection có phần tử, Spring HATEOAS có thể xem kiểu của phần tử để xác định relation trong HAL. Khi collection rỗng, runtime chỉ nhìn thấy một CollectionModel không có item. Do Java type erasure, framework không thể tự biết CollectionModel đó chứa kiểu nào.

Hãy khai báo relation ổn định trên kiểu representation:

~~~java
import java.util.UUID;

import org.springframework.hateoas.server.core.Relation;

@Relation(itemRelation = "order", collectionRelation = "orders")
public record OrderSummary(UUID id, String status) {
}
~~~

Annotation @Relation xác định relation cho item là order và collection là orders. Tên orders sẽ được dùng làm key trong _embedded.

Tạo collection rỗng với fallback type:

~~~java
import org.springframework.hateoas.CollectionModel;

CollectionModel<OrderSummary> empty =
        CollectionModel.empty(OrderSummary.class);
~~~

Hoặc nếu model được tạo từ kết quả truy vấn:

~~~java
CollectionModel<OrderSummary> model =
        CollectionModel.of(results)
                .withFallbackType(OrderSummary.class);
~~~

Hai cách trên cung cấp kiểu dự phòng để serializer và hạ tầng hypermedia biết relation collection ngay cả khi results rỗng. Nếu không có @Relation, LinkRelationProvider dùng quy tắc mặc định hoặc pluralization được cấu hình; với hợp đồng công khai, nên khai báo relation rõ ràng để tên embedded không phụ thuộc tên class.

## Giữ self và search links khi không có kết quả

Link self mô tả truy vấn hiện tại. Link search mô tả nơi client có thể bắt đầu một truy vấn khác. Với search endpoint có query parameters, có thể dùng URI template để công bố các tham số mà client được phép truyền:

~~~java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

Link searchLink = Link.of(
        "/api/orders{?status,customerName}",
        IanaLinkRelations.SEARCH);
~~~

Link relation search là relation chuẩn IANA. URI template có các biến status và customerName; client có thể mở rộng template bằng những giá trị tìm kiếm mới mà không phải tự đoán cấu trúc endpoint.

Ví dụ controller trả CollectionModel:

~~~java
import java.util.List;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

@RestController
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/api/orders")
    CollectionModel<OrderSummary> search(
            @RequestParam(required = false) OrderStatus status,
            @RequestParam(required = false) String customerName) {

        List<OrderSummary> results =
                orderService.search(status, customerName);

        Link self = Link.of(
                ServletUriComponentsBuilder.fromCurrentRequest()
                        .build()
                        .toUriString(),
                IanaLinkRelations.SELF);

        Link search = Link.of(
                "/api/orders{?status,customerName}",
                IanaLinkRelations.SEARCH);

        return CollectionModel.of(results)
                .withFallbackType(OrderSummary.class)
                .add(self, search);
    }
}
~~~

ServletUriComponentsBuilder.fromCurrentRequest() lấy URI của request hiện tại, bao gồm query parameters đã gửi, để tạo self link. Search link là URI template cho một truy vấn mới. Nếu results rỗng, fallback type vẫn giữ relation orders trong HAL.

Không tạo search link chỉ khi results có phần tử. Search link là khả năng của collection endpoint, không phụ thuộc kết quả truy vấn hiện tại. Cũng không nên thay self bằng search: self trỏ tới truy vấn đã chạy, còn search mô tả cách khởi tạo truy vấn mới.

## CollectionModel.empty và RepresentationModelProcessor

Một processor có thể bổ sung links dùng chung cho collection:

~~~java
import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.server.RepresentationModelProcessor;
import org.springframework.stereotype.Component;

@Component
class OrderSearchProcessor
        implements RepresentationModelProcessor<CollectionModel<OrderSummary>> {

    @Override
    public CollectionModel<OrderSummary> process(
            CollectionModel<OrderSummary> model) {

        if (!model.hasLink(IanaLinkRelations.SEARCH)) {
            model.add(Link.of(
                    "/api/orders{?status,customerName}",
                    IanaLinkRelations.SEARCH));
        }

        return model;
    }
}
~~~

Có một chi tiết quan trọng: Spring HATEOAS không gọi RepresentationModelProcessor cho CollectionModel rỗng theo mặc định. Hạ tầng cần phân tích generic type để chọn processor, nhưng collection rỗng không có item để suy ra kiểu do Java type erasure.

Vì vậy, nếu muốn processor hoạt động với collection rỗng, hãy tạo model bằng CollectionModel.empty(OrderSummary.class) hoặc gọi withFallbackType(OrderSummary.class). Cách tạo fallback type ở ví dụ controller trước cũng bảo đảm processor có đủ thông tin kiểu.

Nếu chỉ cần thêm links tại endpoint này, có thể thêm trực tiếp vào model như ví dụ controller. Processor phù hợp khi cùng một chính sách link áp dụng cho nhiều endpoint trả cùng kiểu collection.

## Kết quả rỗng có phân trang

Khi endpoint hỗ trợ pagination, repository trả Page<T>. Page có thể rỗng vì filter không khớp hoặc vì page number vượt phạm vi. PagedResourcesAssembler chuyển Page thành PagedModel, nhưng khi content rỗng cần khai báo kiểu phần tử để tạo embedded collection relation.

Với một Page không có content, dùng toEmptyModel:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.PagedModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

@GetMapping("/api/orders")
PagedModel<?> search(
        @RequestParam(required = false) OrderStatus status,
        Pageable pageable,
        PagedResourcesAssembler<Order> pagedAssembler) {

    Page<Order> page = orderService.search(status, pageable);

    PagedModel<?> model;
    if (page.isEmpty()) {
        model = pagedAssembler.toEmptyModel(page, OrderSummary.class);
    } else {
        model = pagedAssembler.toModel(page, orderAssembler);
    }

    if (!model.hasLink(IanaLinkRelations.SELF)) {
        model.add(Link.of(
                ServletUriComponentsBuilder.fromCurrentRequest()
                        .build()
                        .toUriString(),
                IanaLinkRelations.SELF));
    }

    model.add(Link.of(
            "/api/orders{?status,page,size,sort}",
            IanaLinkRelations.SEARCH));

    return model;
}
~~~

toEmptyModel(Page, Class) tạo PagedModel với embedded wrapper rỗng cho kiểu phần tử được cung cấp. PagedResourcesAssembler vẫn sử dụng metadata của Page và cơ chế tạo pagination links. Ví dụ bổ sung self link nếu model chưa có relation đó, sau đó luôn bổ sung search link.

Với filter hợp lệ không có kết quả, metadata có thể có dạng:

~~~json
{
  "_embedded": {
    "orders": []
  },
  "_links": {
    "self": {
      "href": "/api/orders?status=ARCHIVED&page=0&size=20"
    },
    "search": {
      "href": "/api/orders{?status,page,size,sort}",
      "templated": true
    }
  },
  "page": {
    "size": 20,
    "totalElements": 0,
    "totalPages": 0,
    "number": 0
  }
}
~~~

Không giả định mọi relation phân trang đều xuất hiện khi kết quả rỗng. Links first, prev, next và last phụ thuộc metadata hiện tại cùng chính sách của PagedResourcesAssembler. Hãy kiểm tra những links thực sự có ý nghĩa cho trạng thái trang, đồng thời giữ search link để client có thể thay đổi filter.

## Collection embedded rỗng trong một HAL document

CollectionModel dùng khi collection là representation chính của endpoint. Nếu danh sách rỗng chỉ là một phần dữ liệu được nhúng trong một resource khác, dùng HalModelBuilder.

Ví dụ một đơn hàng có collection dòng hàng rỗng:

~~~java
import java.util.Collections;

import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;
import org.springframework.hateoas.mediatype.hal.HalModelBuilder;

Link selfLink = Link.of(
        "/api/orders/order-42",
        IanaLinkRelations.SELF);

var document = HalModelBuilder.halModelOf(orderSummary)
        .embed(Collections.emptyList(), OrderLineSummary.class)
        .link(selfLink)
        .build();
~~~

Truyền OrderLineSummary.class giúp Spring HATEOAS xác định relation collection dù danh sách không có phần tử. Nếu gọi embed(collection) mà không cung cấp kiểu hoặc relation, builder không thể suy ra relation từ một collection rỗng và có thể bỏ trường tương ứng khỏi _embedded.

Có thể truyền LinkRelation tường minh thay cho kiểu:

~~~java
import java.util.Collections;

import org.springframework.hateoas.LinkRelation;
import org.springframework.hateoas.mediatype.hal.HalModelBuilder;

var document = HalModelBuilder.emptyHalModel()
        .embed(Collections.emptyList(), LinkRelation.of("orderLines"))
        .build();
~~~

Kết quả có key orderLines với mảng rỗng. Cách này hữu ích khi relation được quyết định theo ngữ cảnh document thay vì kiểu Java.

## Kiểm thử kết quả tìm kiếm rỗng

MockMvc nên kiểm tra status, media type, embedded relation và links:

~~~java
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;

mockMvc.perform(get("/api/orders")
                .param("status", "ARCHIVED")
                .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
        .andExpect(jsonPath("$._embedded.orders").isArray())
        .andExpect(jsonPath("$._embedded.orders").isEmpty())
        .andExpect(jsonPath("$._links.self.href")
                .value(containsString("status=ARCHIVED")))
        .andExpect(jsonPath("$._links.search.href").exists())
        .andExpect(jsonPath("$._links.search.templated").value(true));
~~~

Với endpoint phân trang, kiểm tra metadata:

~~~java
mockMvc.perform(get("/api/orders")
                .param("status", "ARCHIVED")
                .param("page", "0")
                .param("size", "20")
                .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.page.size").value(20))
        .andExpect(jsonPath("$.page.totalElements").value(0))
        .andExpect(jsonPath("$.page.totalPages").value(0))
        .andExpect(jsonPath("$._embedded.orders").isEmpty())
        .andExpect(jsonPath("$._links.search.href").exists());
~~~

Nên có thêm test cho trang vượt phạm vi: content rỗng nhưng totalElements vẫn lớn hơn 0 và totalPages vẫn phản ánh tổng số kết quả. Test này bảo vệ khỏi việc nhầm một trang rỗng với một truy vấn không có kết quả.

Nếu dùng RepresentationModelProcessor, tạo cả test với CollectionModel rỗng có fallback type và xác minh link processor đã được thêm. Nếu bỏ fallback type, processor có thể không được gọi dù model có generic type ở khai báo biến.

## Những lỗi thường gặp

- **Trả 404 khi collection tìm kiếm rỗng:** 404 dành cho tài nguyên cụ thể không tồn tại; collection không có kết quả vẫn có thể trả 200.
- **Trả 204 và làm mất hypermedia:** client không nhận được self, search hoặc page metadata.
- **Dùng CollectionModel.empty() không có fallback type:** serializer hoặc processor không xác định được kiểu phần tử và embedded relation.
- **Không khai báo relation ổn định:** key trong _embedded có thể phụ thuộc tên class hoặc pluralization mặc định.
- **Chỉ thêm search link khi có kết quả:** client mất khả năng thay đổi filter đúng lúc cần tìm lại.
- **Nhầm self với search:** self đại diện truy vấn hiện tại; search là URI hoặc URI template để thực hiện truy vấn.
- **Coi trang ngoài phạm vi là không có kết quả:** kiểm tra totalElements và totalPages trước khi diễn giải content rỗng.
- **Mong processor chạy trên collection rỗng mà không fallback type:** cung cấp fallback type khi tạo CollectionModel.
- **Tự tạo embedded key bằng cách đoán tên:** dùng @Relation hoặc LinkRelationProvider để giữ relation đúng hợp đồng.
- **Kiểm thử chỉ status 200:** cần kiểm tra embedded array, relation, links và page metadata.

## Quy trình xử lý kết quả rỗng

1. Xác định đây là collection không có kết quả, trang ngoài phạm vi hay request filter không hợp lệ.
2. Với collection search hợp lệ, trả HTTP 200 cùng CollectionModel hoặc PagedModel.
3. Khai báo item/collection relation ổn định bằng @Relation hoặc LinkRelationProvider.
4. Cung cấp fallback type cho collection rỗng bằng CollectionModel.empty(Class) hoặc withFallbackType(...).
5. Với Page rỗng, dùng PagedResourcesAssembler.toEmptyModel(page, type).
6. Giữ self link cho truy vấn hiện tại và search link cho truy vấn mới.
7. Kiểm thử cả trường hợp không có kết quả, trang ngoài phạm vi và filter sai.

Kết quả rỗng vẫn là một trạng thái có ý nghĩa của collection resource. Khi Spring HATEOAS giữ được kiểu phần tử, relation, search link và page metadata, client có thể hiểu rằng truy vấn đã hợp lệ nhưng chưa tìm thấy item nào, đồng thời tiếp tục khám phá hoặc thay đổi điều kiện tìm kiếm.

## Tài liệu tham khảo

- Spring HATEOAS Reference Documentation, Collection resource representation model và empty collection models: https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals.representation-models.collection-resource
- Spring HATEOAS Reference Documentation, Processing empty collection models: https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.representation-model-processors.empty-collection-models
- Spring HATEOAS API, CollectionModel: https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/CollectionModel.html
- Spring Data API, PagedResourcesAssembler: https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/web/PagedResourcesAssembler.html
- Spring HATEOAS Reference Documentation, HAL embedded collections: https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.hal

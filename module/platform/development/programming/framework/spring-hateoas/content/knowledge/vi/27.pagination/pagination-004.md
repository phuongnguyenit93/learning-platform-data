# Thông tin phân trang PageMetadata

Khi một REST API trả về danh sách có nhiều phần tử, server thường chia kết quả thành các trang để giới hạn lượng dữ liệu truyền qua mạng. Client cần biết kích thước trang, vị trí trang hiện tại, tổng số phần tử và tổng số trang để hiển thị giao diện hoặc quyết định có thể tiếp tục điều hướng hay không.

Spring HATEOAS biểu diễn thông tin này bằng PagedModel, trong đó PageMetadata chứa metadata của trang. Metadata giúp client hiểu trạng thái phân trang tại thời điểm response được tạo. Các link như first, prev, self, next và last cung cấp đường điều hướng đến các trang liên quan.

Bài học này tập trung vào PagedModel.PageMetadata: ý nghĩa của từng trường, cách Spring Data chuyển Page thành PagedModel, cách tạo metadata thủ công, cách đọc response HAL và cách kiểm thử hợp đồng phân trang.

## 1. PageMetadata giải quyết vấn đề gì?

Giả sử endpoint /api/orders có 53 đơn hàng và client yêu cầu trang thứ hai với kích thước 20 phần tử:

~~~http
GET /api/orders?page=1&size=20
Accept: application/hal+json
~~~

Client cần biết:

- Mỗi trang có kích thước bao nhiêu?
- Trang hiện tại có chỉ số nào?
- Toàn bộ kết quả có bao nhiêu phần tử?
- Có tổng cộng bao nhiêu trang?
- Có trang trước hoặc trang tiếp theo không?

PageMetadata trả lời bốn câu hỏi đầu. Các link điều hướng trong PagedModel trả lời câu hỏi cuối và cho client URI để tiếp tục truy vấn.

Không nên bắt client tự suy luận URI trang kế tiếp chỉ từ số trang. Server có thể thay đổi cách biểu diễn tham số, thêm filter hoặc thay đổi cấu trúc endpoint. Client nên theo các link do server công bố.

## 2. Cấu trúc của PageMetadata

PageMetadata là kiểu lồng bên trong PagedModel:

~~~java
PagedModel.PageMetadata
~~~

Nó chứa bốn giá trị:

| Trường | Ý nghĩa |
| --- | --- |
| size | Kích thước trang được yêu cầu hoặc kích thước trang đang áp dụng |
| number | Chỉ số trang hiện tại, bắt đầu từ 0 |
| totalElements | Tổng số phần tử trong toàn bộ kết quả phù hợp với truy vấn |
| totalPages | Tổng số trang cần để chứa các phần tử đó |

Constructor nhận tham số theo thứ tự:

~~~java
new PagedModel.PageMetadata(
        size,
        number,
        totalElements,
        totalPages
);
~~~

Thứ tự tham số rất dễ nhầm vì JSON thường hiển thị totalElements và totalPages trước number. Khi tạo metadata thủ công, hãy nhớ thứ tự constructor là size, number, totalElements, totalPages.

## 3. Ví dụ tính metadata

Giả sử truy vấn có 53 đơn hàng và client yêu cầu mỗi trang 20 đơn hàng. Số trang cần thiết là:

\[
\text{totalPages} =
\left\lceil \frac{\text{totalElements}}{\text{size}} \right\rceil
= \left\lceil \frac{53}{20} \right\rceil = 3
\]

Các trang có chỉ số từ 0 đến 2:

| Chỉ số trang | Vị trí hiển thị cho người dùng | Số phần tử |
| ---: | ---: | ---: |
| 0 | Trang 1 | 20 |
| 1 | Trang 2 | 20 |
| 2 | Trang 3 | 13 |

Nếu client đang xem trang thứ hai, metadata là:

~~~java
PagedModel.PageMetadata metadata =
        new PagedModel.PageMetadata(
                20,  // size
                1,   // number: trang thứ hai, chỉ số bắt đầu từ 0
                53,  // totalElements
                3    // totalPages
        );
~~~

size vẫn là 20 ở trang cuối dù trang cuối chỉ chứa 13 phần tử. Đây là kích thước trang được áp dụng cho truy vấn, không phải số phần tử thực tế trong collection hiện tại.

## 4. Phân biệt Page, Pageable, PageMetadata và PagedModel

Các kiểu này có liên quan nhưng giữ những trách nhiệm khác nhau:

| Kiểu | Vai trò |
| --- | --- |
| Pageable | Mô tả yêu cầu phân trang và sắp xếp từ phía client |
| Page<T> | Kết quả truy vấn phân trang của Spring Data, gồm nội dung và thông tin trang |
| PageMetadata | Metadata phân trang được công bố trong representation |
| PagedModel<T> | Representation hypermedia chứa nội dung, link và metadata trang |

Luồng thường gặp:

~~~mermaid
flowchart TD
    A["HTTP request: page, size, sort"] --> B["Pageable"]
    B --> C["Repository / Service"]
    C --> D["Page<Order>"]
    D --> E["PagedResourcesAssembler"]
    E --> F["PagedModel<EntityModel<OrderDto>>"]
    F --> G["HAL response: _embedded, _links, page"]
~~~

Pageable là đầu vào truy vấn. Page là kết quả từ tầng dữ liệu. PagedResourcesAssembler chuyển kết quả đó thành representation hypermedia. PageMetadata được đưa vào PagedModel để mô tả trạng thái phân trang của response.

Không nên trả thẳng Page<Entity> từ controller nếu API cần hợp đồng hypermedia ổn định. Dùng DTO và assembler giúp tách cấu trúc persistence khỏi representation công khai.

## 5. PageMetadata xuất hiện trong response HAL

Một response cho trang thứ hai có thể có cấu trúc:

~~~json
{
  "_embedded": {
    "orders": [
      {
        "id": 21,
        "status": "PAID",
        "_links": {
          "self": {
            "href": "https://api.example.com/api/orders/21"
          }
        }
      }
    ]
  },
  "_links": {
    "first": {
      "href": "https://api.example.com/api/orders?page=0&size=20"
    },
    "prev": {
      "href": "https://api.example.com/api/orders?page=0&size=20"
    },
    "self": {
      "href": "https://api.example.com/api/orders?page=1&size=20"
    },
    "next": {
      "href": "https://api.example.com/api/orders?page=2&size=20"
    },
    "last": {
      "href": "https://api.example.com/api/orders?page=2&size=20"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 53,
    "totalPages": 3,
    "number": 1
  }
}
~~~

Ví dụ trên được rút gọn để làm rõ cấu trúc. Response thực tế có thể chứa nhiều đơn hàng hơn và thêm link khác. Tên relation trong _embedded phụ thuộc cấu hình relation provider của ứng dụng.

page là metadata, không phải một resource độc lập. _links chứa các URI điều hướng. Hai phần bổ trợ cho nhau:

- Metadata cho client biết trang hiện tại và quy mô toàn bộ kết quả.
- Link cho client biết nơi gửi request tiếp theo.

## 6. Tạo PagedModel từ Page bằng PagedResourcesAssembler

Trong ứng dụng Spring Data, cách phổ biến là dùng PagedResourcesAssembler để chuyển Page<T> thành PagedModel. Assembler tự xây dựng metadata và các link phân trang.

Controller ví dụ:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PageableDefault;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.hateoas.PagedModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService orderService;
    private final OrderModelAssembler orderModelAssembler;

    public OrderController(
            OrderService orderService,
            OrderModelAssembler orderModelAssembler
    ) {
        this.orderService = orderService;
        this.orderModelAssembler = orderModelAssembler;
    }

    @GetMapping(produces = MediaTypes.HAL_JSON_VALUE)
    public PagedModel<EntityModel<OrderDto>> all(
            @PageableDefault(size = 20) Pageable pageable,
            PagedResourcesAssembler<Order> pagedAssembler
    ) {
        Page<Order> orders = orderService.findAll(pageable);
        return pagedAssembler.toModel(orders, orderModelAssembler);
    }
}
~~~

OrderModelAssembler chuyển từng domain object Order thành EntityModel<OrderDto>. PagedResourcesAssembler đảm nhận phần collection, PageMetadata và các link điều hướng.

Với Spring Boot có Spring Data web support, Pageable và PagedResourcesAssembler thường được đăng ký để có thể inject vào controller. Trong cấu hình MVC độc lập, bật hỗ trợ Spring Data web bằng @EnableSpringDataWebSupport nếu chưa được cấu hình.

Service và repository có thể khai báo:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

public interface OrderService {
    Page<Order> findAll(Pageable pageable);
}
~~~

Trong dự án, `OrderModelAssembler` cần triển khai `RepresentationModelAssembler<Order, EntityModel<OrderDto>>`. Nó chuyển từng `Order` thành DTO và gắn link self của đơn hàng. Ví dụ này giả định domain type và assembler đã được khai báo trong package ứng dụng.

Để tránh truy vấn toàn bộ dữ liệu rồi mới cắt trang trong bộ nhớ, hãy truyền Pageable xuống repository hoặc tầng truy vấn hỗ trợ phân trang.

## 7. Tạo PagedModel và PageMetadata thủ công

Không phải nguồn dữ liệu nào cũng trả về Page<T>. Nếu dữ liệu đến từ API bên ngoài, truy vấn tùy chỉnh hoặc một dịch vụ tìm kiếm, có thể tạo PageMetadata và PagedModel trực tiếp.

~~~java
import java.util.List;

import org.springframework.hateoas.PagedModel;

List<OrderDto> content = List.of(
        new OrderDto(21L, "PAID"),
        new OrderDto(22L, "PENDING")
);

PagedModel.PageMetadata metadata =
        new PagedModel.PageMetadata(
                20,
                1,
                53,
                3
        );

PagedModel<OrderDto> model =
        PagedModel.of(content, metadata);
~~~

Khi tạo thủ công, ứng dụng chịu trách nhiệm cung cấp các giá trị chính xác. Nếu muốn client điều hướng giữa các trang, cần thêm link phù hợp.

Khi tự tạo link, hãy giữ các tham số lọc và sắp xếp hiện tại trong URI trang tiếp theo. Nếu bỏ mất filter, client có thể điều hướng sang một tập kết quả khác. Với controller có tham số Pageable và assembler, ưu tiên để PagedResourcesAssembler tạo link thay vì tự ghép URI.

## 8. Quy ước chỉ số trang bắt đầu từ 0

Spring Data mặc định dùng chỉ số trang bắt đầu từ 0:

- page=0 là trang đầu tiên.
- page=1 là trang thứ hai.
- page=2 là trang thứ ba.

PageMetadata.number cũng dùng cùng quy ước này. Giao diện người dùng thường hiển thị trang bắt đầu từ 1, vì vậy client có thể cộng 1 khi hiển thị:

~~~javascript
const pageLabel = page.number + 1;
~~~

Không gửi giá trị đã cộng 1 trở lại server nếu endpoint dùng quy ước Spring Data mặc định. Nếu ứng dụng tùy chỉnh PageableHandlerMethodArgumentResolver để dùng chỉ số một-based, hãy đồng bộ quy ước request và metadata; tránh để client phải đoán.

## 9. Trường hợp trang cuối và kết quả rỗng

Với 53 phần tử và size 20, trang cuối có number=2, totalPages=3, totalElements=53. Nội dung chỉ có 13 phần tử nhưng size vẫn là 20.

Khi không có kết quả, metadata thường thể hiện:

~~~json
{
  "size": 20,
  "totalElements": 0,
  "totalPages": 0,
  "number": 0
}
~~~

Giá trị cụ thể phụ thuộc Page được tạo và quy tắc truy vấn. Với collection rỗng, client không nên giả định luôn có link next hoặc last.

Nếu client yêu cầu một trang vượt quá phạm vi, repository có thể trả một Page rỗng với chỉ số trang được yêu cầu. API cần thống nhất hành vi này trong hợp đồng: trả trang rỗng với metadata tương ứng, hay từ chối request theo quy tắc riêng. Không nên tự ép number về trang cuối nếu link self vẫn trỏ đến tham số khác.

Kích thước trang cũng cần giới hạn. Client không nên được phép yêu cầu hàng trăm nghìn phần tử trong một trang chỉ bằng cách truyền size lớn. Có thể cấu hình kích thước mặc định và tối đa cho pageable resolver.

## 10. PageMetadata không chứa sort và filter

PageMetadata chỉ chứa bốn trường phân trang. Nó không mô tả:

- Trường đang sắp xếp.
- Hướng sắp xếp tăng hoặc giảm.
- Bộ lọc tìm kiếm.
- Tổng thời gian truy vấn.
- Quyền truy cập của người dùng.

Nếu API hỗ trợ sort hoặc filter, các tham số đó cần được giữ trong link điều hướng. Ví dụ:

~~~http
GET /api/orders?page=1&size=20&sort=createdAt,desc&status=PAID
~~~

Link next nên giữ size, sort và status trong khi thay đổi page. Nhờ đó, client đi đến trang tiếp theo trong cùng tập kết quả.

Không nên suy ra trạng thái sort hoặc filter từ PageMetadata. Nếu client cần hiển thị chúng, API có thể công bố query state riêng hoặc giữ các tham số trong self link.

## 11. PageMetadata và link điều hướng

Một response phân trang thường có một số relation:

| Relation | Vai trò |
| --- | --- |
| first | Trang đầu tiên |
| prev | Trang ngay trước trang hiện tại |
| self | Trang hiện tại |
| next | Trang ngay sau trang hiện tại |
| last | Trang cuối cùng |

Không phải trang nào cũng có đủ các link:

- Trang đầu không có prev.
- Trang cuối không có next.
- Kết quả rỗng có thể không có prev, next hoặc last.

PageMetadata giúp client hiển thị “trang 2 / 3” hoặc “53 kết quả”. Link giúp client gửi request tiếp theo. Nếu client chỉ dùng number + 1 để tự ghép URI, nó sẽ phụ thuộc vào quy ước URL và có thể làm mất filter hoặc sort.

## 12. Kiểm thử PageMetadata bằng unit test

Khi tạo metadata thủ công hoặc viết mapper, có thể kiểm tra các giá trị trực tiếp:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.hateoas.PagedModel;

class PageMetadataTest {

    @Test
    void storesPageValuesInExpectedFields() {
        PagedModel.PageMetadata metadata =
                new PagedModel.PageMetadata(
                        20,
                        1,
                        53,
                        3
                );

        assertThat(metadata.getSize()).isEqualTo(20);
        assertThat(metadata.getNumber()).isEqualTo(1);
        assertThat(metadata.getTotalElements()).isEqualTo(53);
        assertThat(metadata.getTotalPages()).isEqualTo(3);
    }
}
~~~

Test này đặc biệt hữu ích để phát hiện lỗi truyền nhầm thứ tự tham số trong constructor.

## 13. Kiểm thử metadata và link bằng MockMvc

Với endpoint dùng PagedResourcesAssembler, hãy kiểm tra metadata trong response HAL và các link cần thiết:

~~~java
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(OrderController.class)
@Import({OrderModelAssembler.class, PagingConfiguration.class})
class OrderPaginationTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderService orderService;

    @Test
    void exposesPageMetadataAndNavigationLinks() throws Exception {
        Pageable pageable = PageRequest.of(1, 20);
        Page<Order> page = new PageImpl<>(
                List.of(Order.example(21L), Order.example(22L)),
                pageable,
                53
        );
        when(orderService.findAll(any(Pageable.class))).thenReturn(page);

        mockMvc.perform(get("/api/orders")
                        .param("page", "1")
                        .param("size", "20")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.page.size").value(20))
                .andExpect(jsonPath("$.page.number").value(1))
                .andExpect(jsonPath("$.page.totalElements").value(53))
                .andExpect(jsonPath("$.page.totalPages").value(3))
                .andExpect(jsonPath("$._links.self.href").exists())
                .andExpect(jsonPath("$._links.prev.href").exists())
                .andExpect(jsonPath("$._links.next.href").exists());
    }
}
~~~

Đây là test slice minh họa. `Order.example`, `OrderModelAssembler` và `OrderService` đại diện cho các kiểu đã được định nghĩa trong ứng dụng. Nếu test context chưa tự cấu hình Spring Data web support, có thể import cấu hình:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.web.config.EnableSpringDataWebSupport;

@Configuration
@EnableSpringDataWebSupport
class PagingConfiguration {
}
~~~

Ví dụ dùng hai phần tử trong content để rút gọn dữ liệu test, trong khi totalElements là 53. Trong test thực tế, nên dùng số phần tử đúng với trang đang kiểm tra nếu cần xác nhận cả kích thước content.

Nên kiểm thử thêm:

- Trang đầu có first và next, không có prev.
- Trang giữa có prev và next.
- Trang cuối có prev và last, không có next.
- Trang cuối có ít phần tử hơn size nhưng metadata size không đổi.
- Kết quả rỗng có totalElements và totalPages đúng.
- Link next giữ các query parameter sort và filter.
- Số trang trong metadata dùng chỉ số bắt đầu từ 0.

## 14. Những lỗi thường gặp

**Nhầm thứ tự tham số PageMetadata.** Constructor nhận size, number, totalElements, totalPages. Ghi chú thứ tự này khi tạo thủ công.

**Coi number là số trang hiển thị.** number bắt đầu từ 0 theo mặc định Spring Data. Giao diện có thể cộng 1 để hiển thị cho người dùng.

**Dùng số phần tử của trang làm totalElements.** Content chỉ chứa phần tử của trang hiện tại. totalElements phải là tổng số phần tử của toàn bộ kết quả phù hợp với truy vấn.

**Dùng content.size() làm size.** Trang cuối có thể chứa ít phần tử hơn kích thước trang được yêu cầu. Metadata size vẫn phản ánh kích thước trang áp dụng.

**Cho rằng PageMetadata chứa link điều hướng.** Metadata chỉ mô tả con số. PagedModel chứa cả link relation để client điều hướng.

**Trả Page<Entity> trực tiếp từ controller.** Điều này làm API phụ thuộc cấu trúc Spring Data và entity. Dùng PagedResourcesAssembler cùng representation assembler để tạo PagedModel.

**Tự tạo link next nhưng bỏ query parameter.** Link trang kế tiếp phải giữ sort, filter và các tham số cần thiết khác.

**Không giới hạn size.** Client có thể yêu cầu page size quá lớn, làm tăng tải truy vấn và response. Đặt default và maximum page size phù hợp.

**Chỉ kiểm thử metadata, bỏ qua link.** Một response có con số đúng nhưng link sai vẫn khiến client không thể điều hướng. Kiểm thử cả page và _links.

## 15. Ghi nhớ

PagedModel.PageMetadata mô tả bốn giá trị: size, number, totalElements và totalPages. Constructor nhận tham số theo đúng thứ tự này; number mặc định bắt đầu từ 0. Metadata giúp client hiểu kích thước và vị trí trang hiện tại, còn các link trong PagedModel cung cấp đường điều hướng.

Với Spring Data, dùng Pageable để nhận yêu cầu phân trang, Page<T> để nhận kết quả truy vấn và PagedResourcesAssembler để chuyển thành PagedModel cùng metadata và link. Khi dữ liệu không đến từ Spring Data, có thể tạo PageMetadata và PagedModel thủ công nhưng phải bảo đảm các con số chính xác.

Không nhầm số phần tử của trang hiện tại với tổng số phần tử hoặc kích thước trang. Trang cuối có thể ít phần tử hơn size; totalElements vẫn tính toàn bộ kết quả. PageMetadata không chứa sort và filter, vì vậy link điều hướng cần giữ các query parameter đó.

Kiểm thử cả metadata và các relation first, prev, self, next, last ở trang đầu, giữa, cuối và trường hợp rỗng. Client nên theo link server công bố để điều hướng, thay vì tự ghép URI từ số trang.

## Tài liệu tham khảo

- [Spring HATEOAS Reference – Paged Resources](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.paged-resources)
- [PagedModel API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/PagedModel.html)
- [Spring Data Commons – Paging and Sorting](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html#core.web)
- [PagedResourcesAssembler API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/web/PagedResourcesAssembler.html)

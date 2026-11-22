# Kết hợp @ParameterObject với tham số phân trang

API danh sách thường cần nhận đồng thời bộ lọc nghiệp vụ và tham số phân trang, sắp xếp. Ví dụ, client muốn tìm các đơn hàng đã thanh toán, tạo trong một khoảng ngày, xem trang thứ hai với 20 kết quả và sắp xếp theo thời gian tạo mới nhất.

Spring Data cung cấp Pageable để gom thông tin page, size và sort; Spring Data Web bind các giá trị này từ request của Spring MVC. Với springdoc-openapi, **@ParameterObject** giúp các thuộc tính của Pageable được mô tả thành query parameter riêng trong OpenAPI. Có thể kết hợp Pageable với một query DTO khác để giữ chữ ký controller gọn và giúp Swagger UI hiển thị đầy đủ cách gọi API.

Bài này hướng dẫn cách kết hợp filter object với Pageable, đặt giá trị mặc định, cấu hình tên tham số và giới hạn kích thước trang, mô tả response phân trang và kiểm tra tài liệu được sinh ra.

## 1. Phân trang và sắp xếp trong API danh sách

Thay vì trả toàn bộ bản ghi trong một lần gọi, API phân trang chia kết quả thành các phần nhỏ. Client gửi thông tin trang và kích thước trang:

- **page:** chỉ số trang cần lấy.
- **size:** số phần tử tối đa trên một trang.
- **sort:** thuộc tính và chiều sắp xếp.

Với cấu hình mặc định phổ biến của Spring Data Web, chỉ số trang bắt đầu từ 0. Ví dụ:

~~~http
GET /api/orders?page=0&size=20
~~~

Request trên lấy trang đầu tiên với tối đa 20 phần tử. Để lấy trang tiếp theo:

~~~http
GET /api/orders?page=1&size=20
~~~

Tham số sort cho phép sắp xếp kết quả:

~~~http
GET /api/orders?page=0&size=20&sort=createdAt,desc
~~~

Có thể chỉ định nhiều tiêu chí bằng cách lặp lại tham số sort:

~~~http
GET /api/orders?page=0&size=20&sort=createdAt,desc&sort=id,asc
~~~

Ví dụ này sắp xếp theo createdAt giảm dần; nếu hai bản ghi có cùng thời gian tạo, id tăng dần được dùng làm tiêu chí tiếp theo.

Phân trang giúp giới hạn lượng dữ liệu truyền qua mạng và công việc xử lý cho mỗi request. Tuy nhiên, cần đặt giới hạn size và chọn cách phân trang phù hợp với quy mô dữ liệu.

## 2. Pageable gom page, size và sort

Spring Data định nghĩa interface Pageable để biểu diễn yêu cầu phân trang. Trong controller, Spring có thể tự tạo Pageable từ query parameter thông qua cơ chế Spring Data Web.

Ví dụ đơn giản:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PageableDefault;
import org.springframework.data.domain.Sort;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    @GetMapping("/api/orders")
    public Page<OrderResponse> listOrders(
        @PageableDefault(
            size = 20,
            sort = "createdAt",
            direction = Sort.Direction.DESC
        )
        Pageable pageable
    ) {
        return orderService.findAll(pageable);
    }
}
~~~

Spring Data phân tích query string và tạo Pageable chứa:

- page number.
- page size.
- Sort gồm một hoặc nhiều Order.

Controller truyền Pageable xuống service và repository để truy vấn dữ liệu theo trang. Không cần tự khai báo ba tham số page, size, sort nếu đã dùng Pageable.

Để springdoc biểu diễn Pageable thành query parameter trong OpenAPI, gắn @ParameterObject:

~~~java
import org.springdoc.core.annotations.ParameterObject;

@GetMapping("/api/orders")
public Page<OrderResponse> listOrders(
    @ParameterObject Pageable pageable
) {
    return orderService.findAll(pageable);
}
~~~

Trong springdoc-openapi v2, @ParameterObject nằm trong package org.springdoc.core.annotations. Với dòng major khác, hãy kiểm tra package và hướng dẫn migration của phiên bản đang sử dụng.

## 3. @ParameterObject có vai trò gì?

@ParameterObject hướng dẫn springdoc phân tích thuộc tính của object thành các parameter riêng. Khi đặt trên Pageable, tài liệu thường thể hiện các tham số:

| Query parameter | Ý nghĩa | Kiểu thường gặp |
|---|---|---|
| page | Chỉ số trang | integer |
| size | Số phần tử trên trang | integer |
| sort | Tiêu chí sắp xếp | string hoặc array string tùy cách mô hình hóa |

Với controller:

~~~java
@GetMapping("/api/orders")
public Page<OrderResponse> listOrders(
    @ParameterObject Pageable pageable
) {
    return orderService.findAll(pageable);
}
~~~

OpenAPI có thể mô tả operation tương tự:

~~~yaml
paths:
  /api/orders:
    get:
      parameters:
        - name: page
          in: query
          required: false
          schema:
            type: integer
            format: int32
            default: 0
        - name: size
          in: query
          required: false
          schema:
            type: integer
            format: int32
            default: 20
        - name: sort
          in: query
          required: false
          schema:
            type: array
            items:
              type: string
      responses:
        '200':
          description: Trang đơn hàng
~~~

Đây là hình dạng minh họa. Default, kiểu của sort và tên schema cụ thể có thể phụ thuộc annotation, Spring Data Web configuration và phiên bản springdoc. Luôn kiểm tra JSON thực tế tại /v3/api-docs.

@ParameterObject chỉ phục vụ việc tạo tài liệu. Spring Data Web mới bind query parameter vào Pageable khi chạy. Nếu Swagger UI hiển thị page nhưng resolver của ứng dụng dùng tên tham số khác, request vẫn có thể bind sai.

## 4. Kết hợp query DTO với Pageable

Trong API thực tế, client thường cần lọc theo trạng thái, từ khóa hoặc ngày tạo, đồng thời phân trang. Có thể dùng hai tham số object riêng:

~~~java
@GetMapping("/api/orders")
public Page<OrderResponse> searchOrders(
    @ParameterObject @ModelAttribute OrderSearchCriteria criteria,
    @ParameterObject Pageable pageable
) {
    return orderService.search(criteria, pageable);
}
~~~

Query DTO:

~~~java
public class OrderSearchCriteria {

    private String keyword;
    private OrderStatus status;
    private LocalDate createdFrom;
    private LocalDate createdTo;

    public OrderSearchCriteria() {
    }

    // Getters và setters.
}
~~~

Request mẫu:

~~~http
GET /api/orders?keyword=ORD&status=PAID&createdFrom=2026-01-01&createdTo=2026-01-31&page=0&size=20&sort=createdAt,desc
~~~

Spring MVC bind keyword, status, createdFrom và createdTo vào OrderSearchCriteria. Spring Data Web bind page, size và sort vào Pageable. springdoc dùng hai annotation @ParameterObject để công bố cả hai nhóm tham số.

Cách kết hợp này tách hai trách nhiệm:

- OrderSearchCriteria chứa điều kiện lọc theo nghiệp vụ.
- Pageable chứa cách chia trang và thứ tự sắp xếp.

Service có thể nhận cả hai:

~~~java
public Page<OrderResponse> search(
    OrderSearchCriteria criteria,
    Pageable pageable
) {
    return orderRepository.search(criteria, pageable)
        .map(orderMapper::toResponse);
}
~~~

Phần truy vấn repository là tùy implementation. Dù dùng JPQL, Criteria API, Specification hoặc query builder, hãy áp dụng Pageable vào truy vấn để database chỉ trả về phần dữ liệu cần thiết.

## 5. Đặt giá trị mặc định bằng @PageableDefault

@PageableDefault cho phép đặt page, size, sort và direction mặc định khi client không truyền các tham số tương ứng.

~~~java
@GetMapping("/api/orders")
public Page<OrderResponse> listOrders(
    @ParameterObject
    @PageableDefault(
        page = 0,
        size = 25,
        sort = "createdAt",
        direction = Sort.Direction.DESC
    )
    Pageable pageable
) {
    return orderService.findAll(pageable);
}
~~~

Ý nghĩa:

- page = 0: bắt đầu từ trang đầu theo cách đánh số mặc định.
- size = 25: mặc định lấy tối đa 25 phần tử.
- sort = "createdAt": sắp xếp theo thời gian tạo.
- direction = DESC: bản ghi mới hơn đứng trước.

Nếu client gửi page hoặc size, giá trị request thường được dùng thay cho giá trị mặc định tương ứng. Các giới hạn cấu hình ở resolver vẫn có thể áp dụng.

@PageableDefault có giá trị mặc định riêng của annotation. Vì vậy, khi muốn tài liệu và runtime cùng dùng một default cụ thể, hãy khai báo tường minh và kiểm tra JSON sinh ra. Đừng chỉ dựa vào giá trị mặc định ngầm của framework.

Có thể dùng @SortDefault khi muốn mô tả mặc định sắp xếp riêng:

~~~java
@GetMapping("/api/products")
public Page<ProductResponse> listProducts(
    @ParameterObject
    @PageableDefault(size = 20)
    @SortDefault(
        sort = "name",
        direction = Sort.Direction.ASC
    )
    Pageable pageable
) {
    return productService.findAll(pageable);
}
~~~

Khi dùng đồng thời các annotation mặc định, hãy kiểm tra kết quả Sort thực tế trong test và metadata OpenAPI. Nếu chỉ cần một tiêu chí mặc định đơn giản, khai báo sort và direction ngay trong @PageableDefault thường dễ đọc hơn.

## 6. Cấu hình tên tham số phân trang

Spring Data Web thường dùng các tên page, size và sort. Có thể đổi tên để phù hợp quy ước API.

Ví dụ cấu hình:

~~~yaml
spring:
  data:
    web:
      pageable:
        page-parameter: pageNumber
        size-parameter: pageSize
      sort:
        sort-parameter: orderBy
~~~

Khi áp dụng cấu hình này, URL có thể là:

~~~http
GET /api/orders?pageNumber=0&pageSize=20&orderBy=createdAt,desc
~~~

Các property thường dùng:

| Property | Mục đích |
|---|---|
| spring.data.web.pageable.page-parameter | Tên query parameter chứa số trang |
| spring.data.web.pageable.size-parameter | Tên query parameter chứa kích thước trang |
| spring.data.web.sort.sort-parameter | Tên query parameter chứa tiêu chí sort |
| spring.data.web.pageable.default-page-size | Kích thước trang mặc định của resolver |
| spring.data.web.pageable.max-page-size | Kích thước trang tối đa resolver chấp nhận |
| spring.data.web.pageable.one-indexed-parameters | Dùng cách đánh số trang bắt đầu từ 1 ở request |
| spring.data.web.pageable.prefix | Prefix cho tham số Pageable |
| spring.data.web.pageable.qualifier-delimiter | Ký tự phân cách qualifier và tên tham số |

Tên property và khả năng cấu hình phụ thuộc phiên bản Spring Boot/Spring Data. Hãy đối chiếu metadata cấu hình của dòng đang dùng. Sau khi đổi tên, cần kiểm tra cả Spring Data resolver và OpenAPI output; không để tài liệu tiếp tục hiển thị page trong khi runtime chỉ nhận pageNumber.

## 7. Đánh số trang từ 0 hay từ 1

Spring Data Pageable sử dụng page number bắt đầu từ 0 trong mô hình nội bộ. Ví dụ PageRequest.of(0, 20) biểu diễn trang đầu tiên.

Mặc định request cũng thường dùng page=0. Nếu API muốn client gửi trang đầu tiên bằng page=1, có thể bật:

~~~yaml
spring:
  data:
    web:
      pageable:
        one-indexed-parameters: true
~~~

Khi bật, resolver chuyển cách đánh số một-based ở query string sang chỉ số zero-based nội bộ. Ví dụ:

~~~http
GET /api/orders?page=1&size=20
~~~

Client yêu cầu trang đầu tiên; Pageable nội bộ vẫn biểu diễn trang với chỉ số 0.

Cần công bố rõ quy ước này trong description của parameter hoặc operation. Kiểm tra default trong OpenAPI, vì schema có thể cần được tùy chỉnh để phản ánh page=1 là giá trị đầu tiên ở giao diện public. Không nên giả định việc bật property tự động làm mọi generator và Swagger UI thể hiện đúng quy ước một-based.

Nếu không có yêu cầu tương thích đặc biệt, dùng zero-based thường phù hợp với mặc định của Spring Data và giảm chuyển đổi giữa API và backend.

## 8. Giới hạn kích thước trang

Client không nên được phép yêu cầu size tùy ý. Một request như size=100000 có thể làm truy vấn nặng, tốn bộ nhớ và tạo response quá lớn.

Có thể đặt giới hạn tối đa:

~~~yaml
spring:
  data:
    web:
      pageable:
        default-page-size: 20
        max-page-size: 100
~~~

Với resolver mặc định của Spring Data Web, size vượt giới hạn thường được chặn ở max-page-size thay vì cho phép truy vấn số lượng không giới hạn. Hành vi cụ thể nên được kiểm tra theo phiên bản và resolver tùy chỉnh của ứng dụng.

Ngoài cấu hình toàn cục, có thể đặt default cho từng endpoint bằng @PageableDefault. Cấu hình max page size vẫn cần được áp dụng ở resolver hoặc tầng kiểm tra tương ứng.

Nếu API muốn từ chối size quá lớn thay vì tự giới hạn, hãy triển khai validation rõ ràng và mô tả response lỗi. Đừng chỉ ghi maximum trong OpenAPI rồi kỳ vọng Spring Data tự trả 400 nếu cấu hình runtime không thực hiện điều đó.

## 9. Cách biểu diễn sort

Spring Data Web thường nhận sort dưới dạng tên thuộc tính và hướng sắp xếp:

~~~http
GET /api/orders?sort=createdAt,desc
~~~

Có thể gửi nhiều tiêu chí bằng cách lặp tham số:

~~~http
GET /api/orders?sort=status,asc&sort=createdAt,desc
~~~

Trong Pageable, các tiêu chí này được chuyển thành Sort. Ví dụ:

~~~java
Sort sort = Sort.by(
    Sort.Order.asc("status"),
    Sort.Order.desc("createdAt")
);

Pageable pageable = PageRequest.of(0, 20, sort);
~~~

Không nên cho phép client sắp xếp tùy ý theo mọi property của entity. Hãy xác định danh sách sort key public, kiểm tra đầu vào và ánh xạ sang property hoặc expression truy vấn được phép. Việc này tránh lỗi do tên property không tồn tại và giảm nguy cơ để client điều khiển truy vấn ngoài dự kiến.

Nếu API dùng tên sort khác với tên field persistence, có thể tạo mapping, ví dụ public key createdDate được ánh xạ sang createdAt. Hãy mô tả các giá trị được hỗ trợ trong OpenAPI hoặc description của parameter để client biết lựa chọn hợp lệ.

Sort không ổn định có thể khiến bản ghi xuất hiện lặp hoặc bị bỏ qua giữa các trang khi dữ liệu thay đổi. Nên bổ sung tiêu chí duy nhất làm tie-breaker, chẳng hạn id, khi tiêu chí chính có thể trùng nhau.

## 10. Kết hợp Pageable với @ParameterObject và filter có validation

Filter DTO có thể dùng Bean Validation để giới hạn dữ liệu:

~~~java
public class OrderSearchCriteria {

    @Size(max = 100)
    private String keyword;

    private OrderStatus status;

    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate createdFrom;

    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate createdTo;

    // Getters và setters.
}
~~~

Controller:

~~~java
@GetMapping("/api/orders")
public Page<OrderResponse> searchOrders(
    @Valid
    @ParameterObject
    @ModelAttribute
    OrderSearchCriteria criteria,

    @ParameterObject
    @PageableDefault(
        size = 20,
        sort = "createdAt",
        direction = Sort.Direction.DESC
    )
    Pageable pageable
) {
    return orderService.search(criteria, pageable);
}
~~~

Có thể kiểm tra quy tắc liên trường như createdFrom không được sau createdTo trong service hoặc custom validator. @ParameterObject không tự thực hiện validation; nó chỉ hướng dẫn springdoc tạo metadata. Spring MVC binding và Bean Validation vẫn xử lý dữ liệu runtime.

Với query parameter, cần kiểm tra kiểu dữ liệu và format trong OpenAPI. Ví dụ LocalDate thường được biểu diễn là string với format date. Gửi ngày không đúng định dạng có thể gây lỗi binding trước khi service được gọi.

## 11. Phân biệt Page, Slice và List

Spring Data cung cấp nhiều kiểu kết quả:

| Kiểu | Nội dung | Metadata phân trang | Chi phí thường gặp |
|---|---|---|---|
| Page<T> | Nội dung trang hiện tại | Có totalElements và totalPages | Thường cần truy vấn đếm tổng |
| Slice<T> | Nội dung lát dữ liệu | Có hasNext/hasPrevious, không yêu cầu tổng số trang | Có thể tránh count query |
| List<T> | Danh sách kết quả | Không có metadata phân trang | Phụ thuộc truy vấn và giới hạn dữ liệu |

Page<T> phù hợp khi giao diện cần tổng số bản ghi hoặc tổng số trang. Slice<T> phù hợp khi client chỉ cần biết còn dữ liệu tiếp theo hay không. List<T> phù hợp với tập dữ liệu nhỏ hoặc endpoint không công bố pagination metadata.

Việc chọn Page hay Slice ảnh hưởng cả hiệu năng lẫn response contract. Không dùng Page chỉ vì muốn có tham số page/size; nếu không cần tổng số phần tử, Slice có thể phù hợp hơn.

## 12. Mô tả response Page<T>

Một Page<T> chứa nội dung trang và metadata, thường gồm:

- content: danh sách phần tử của trang.
- number: chỉ số trang hiện tại.
- size: kích thước trang.
- numberOfElements: số phần tử thực tế trong trang.
- totalElements: tổng số phần tử phù hợp với điều kiện lọc.
- totalPages: tổng số trang.
- first và last: có phải trang đầu hoặc cuối không.
- empty: trang có rỗng không.
- sort/pageable: thông tin phân trang và sắp xếp, tùy cách serialize.

Ví dụ JSON minh họa:

~~~json
{
  "content": [
    {
      "id": "ORD-1001",
      "status": "PAID"
    }
  ],
  "number": 0,
  "size": 20,
  "numberOfElements": 1,
  "totalElements": 41,
  "totalPages": 3,
  "first": true,
  "last": false,
  "empty": false
}
~~~

Hình dạng JSON thực tế phụ thuộc kiểu trả về, cấu hình serialize của Spring Data và cách ứng dụng định nghĩa response. springdoc có thể dùng model converter để mô tả Page, nhưng không nên mặc định rằng schema được sinh luôn khớp chính xác với JSON của mọi phiên bản.

Kiểm tra response thực tế bằng request test và đối chiếu với components.schemas trong /v3/api-docs. Nếu cần hợp đồng public ổn định, cân nhắc DTO phân trang riêng thay vì phơi bày trực tiếp cấu trúc nội bộ của PageImpl.

## 13. Dùng DTO phân trang riêng cho public API

Một DTO riêng giúp kiểm soát tên field và tránh phụ thuộc vào cấu trúc serialize nội bộ của Spring Data:

~~~java
public record PageResponse<T>(
    List<T> content,
    int page,
    int size,
    long totalElements,
    int totalPages,
    boolean first,
    boolean last
) {}
~~~

Có thể chuyển đổi từ Page<T>:

~~~java
public final class PageResponses {

    private PageResponses() {
    }

    public static <T> PageResponse<T> from(Page<T> source) {
        return new PageResponse<>(
            source.getContent(),
            source.getNumber(),
            source.getSize(),
            source.getTotalElements(),
            source.getTotalPages(),
            source.isFirst(),
            source.isLast()
        );
    }
}
~~~

Controller trả DTO:

~~~java
@GetMapping("/api/orders")
public PageResponse<OrderResponse> listOrders(
    @ParameterObject Pageable pageable
) {
    Page<OrderResponse> result = orderService.findAll(pageable);
    return PageResponse.from(result);
}
~~~

Đây là ví dụ minh họa; trong code thực tế, đặt factory method trong mapper hoặc lớp phù hợp và xử lý generic schema theo yêu cầu. Nếu dùng record, cần phiên bản Java hỗ trợ record.

DTO phân trang giúp nhóm thay đổi cách truy vấn nội bộ mà không nhất thiết thay đổi public contract. Tuy nhiên, nếu đã công bố Page<T> trực tiếp, chuyển sang DTO mới có thể là thay đổi hợp đồng và cần đánh giá ảnh hưởng client.

## 14. Nhiều Pageable trong cùng operation

Một số endpoint có thể cần phân trang cho nhiều tập dữ liệu độc lập, nhưng chữ ký controller sẽ khó đọc nếu không phân biệt tham số. Spring Data hỗ trợ qualifier để đặt namespace cho từng Pageable.

Ví dụ:

~~~java
@GetMapping("/api/dashboard")
public DashboardResponse dashboard(
    @Qualifier("orders")
    @ParameterObject
    Pageable ordersPage,

    @Qualifier("payments")
    @ParameterObject
    Pageable paymentsPage
) {
    return dashboardService.load(ordersPage, paymentsPage);
}
~~~

Với qualifier và delimiter mặc định, tham số có thể có dạng:

~~~http
GET /api/dashboard?orders_page=0&orders_size=10&orders_sort=createdAt,desc&payments_page=0&payments_size=5
~~~

Tên prefix và ký tự phân cách phụ thuộc cấu hình Spring Data Web. Cần kiểm tra cả cách resolver bind và tên parameter mà springdoc công bố. Nhiều Pageable trong một operation làm API phức tạp hơn; chỉ dùng khi client thực sự cần phân trang độc lập cho nhiều tập dữ liệu.

## 15. Cursor pagination không phải Pageable

Pageable mô hình hóa phân trang theo số trang và kích thước trang (offset/page-number pagination). Với tập dữ liệu rất lớn hoặc dữ liệu thay đổi thường xuyên, cursor pagination có thể phù hợp hơn.

Ví dụ cursor API:

~~~http
GET /api/orders?limit=20&after=eyJpZCI6Ik9SRC0xMDAxIn0
~~~

Trong trường hợp này, after là cursor do server cấp, không phải page number. Client gửi cursor từ response trước để lấy phần tiếp theo.

Không nên dùng @ParameterObject Pageable rồi đổi tên page thành after nếu backend thực tế dùng cursor. Hãy định nghĩa query DTO riêng:

~~~java
public class OrderCursorQuery {
    @Min(1)
    @Max(100)
    private Integer limit = 20;

    private String after;

    // Getters và setters.
}
~~~

Cursor pagination có thể giúp tránh chi phí offset lớn và giảm vấn đề dịch chuyển vị trí khi dữ liệu được thêm mới, nhưng cần thiết kế cursor ổn định, opaque và có kiểm soát. Tài liệu OpenAPI cần mô tả limit, after, nextCursor và quy tắc kết thúc tập dữ liệu.

## 16. Kiểm tra query parameter trong OpenAPI JSON

Sau khi ứng dụng chạy, tải spec:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs -o openapi.json
~~~

Xem các parameter của operation:

~~~bash
jq '.paths["/api/orders"].get.parameters' openapi.json
~~~

Liệt kê tên, vị trí và schema:

~~~bash
jq -r '
  .paths["/api/orders"].get.parameters[]
  | [
      .name,
      .in,
      (.required // false | tostring),
      (.schema.type // ""),
      (.schema.default // "")
    ]
  | @tsv
' openapi.json
~~~

Đối chiếu các điểm:

- Có đủ filter parameter và page, size, sort không?
- Tên parameter có khớp Spring Data Web configuration không?
- Default page và size có đúng với @PageableDefault không?
- sort có biểu diễn được nhiều tiêu chí không?
- Mô tả có giải thích zero-based hay one-based không?
- Giới hạn size có được công bố nếu cần không?
- Query DTO có bị biểu diễn thành request body không mong muốn không?

Nếu OpenAPI chỉ hiển thị một object parameter chung, kiểm tra @ParameterObject và phiên bản springdoc. Nếu tài liệu hiển thị page/size mặc định sai, kiểm tra annotation, cấu hình global và resolver.

## 17. Kiểm tra binding và kết quả phân trang khi chạy

OpenAPI JSON xác minh metadata. Cần gửi request thực tế để xác minh Spring Data Web bind đúng và service trả đúng dữ liệu.

Ví dụ:

~~~bash
curl -i "http://localhost:8080/api/orders?status=PAID&page=0&size=20&sort=createdAt,desc"
~~~

Trong test MockMvc, có thể xác minh Pageable được truyền xuống service:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    OrderService orderService;

    @Test
    void bindsPageSizeAndSort() throws Exception {
        given(orderService.findAll(any(Pageable.class)))
            .willReturn(Page.empty());

        mockMvc.perform(get("/api/orders")
                .param("page", "1")
                .param("size", "10")
                .param("sort", "createdAt,desc"))
            .andExpect(status().isOk());

        ArgumentCaptor<Pageable> captor =
            ArgumentCaptor.forClass(Pageable.class);

        then(orderService).should().findAll(captor.capture());

        Pageable actual = captor.getValue();
        assertThat(actual.getPageNumber()).isEqualTo(1);
        assertThat(actual.getPageSize()).isEqualTo(10);
        assertThat(actual.getSort().getOrderFor("createdAt").getDirection())
            .isEqualTo(Sort.Direction.DESC);
    }
}
~~~

Test trên minh họa cách xác minh binding. Cần bổ sung import, cấu hình mock và assertion null-safe theo dự án. Nếu bật one-indexed-parameters, request page=1 sẽ được chuyển thành page number nội bộ 0; hãy điều chỉnh kỳ vọng cho phù hợp.

Nên có test cho:

- Không truyền page/size để xác minh default.
- Truyền page và size tường minh.
- Gửi nhiều sort.
- Gửi size vượt giới hạn.
- Gửi page âm hoặc size không hợp lệ.
- Kết hợp filter và Pageable.
- Kiểm tra response metadata và thứ tự phần tử.

## 18. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Swagger UI không hiển thị page/size/sort | Thiếu @ParameterObject hoặc springdoc không phân tích Pageable theo cấu hình hiện tại |
| Tài liệu hiển thị page nhưng request không bind | Tên parameter đã đổi trong Spring Data Web nhưng spec chưa phản ánh |
| Trang đầu tiên bị bỏ qua hoặc lệch một trang | Nhầm zero-based với one-based |
| Client yêu cầu size rất lớn | Chưa đặt max-page-size hoặc chưa kiểm tra giới hạn ở resolver |
| Sort trong Swagger UI không đúng định dạng backend nhận | Schema hoặc mô tả sort chưa phản ánh cú pháp lặp tham số |
| Bản ghi đổi vị trí giữa các trang | Sort không ổn định hoặc dữ liệu thay đổi trong lúc client duyệt |
| Page response chứa nhiều field nội bộ | Đang serialize trực tiếp PageImpl hoặc schema converter tạo cấu trúc không phù hợp public contract |
| API chạy chậm khi lấy Page | Count query tốn chi phí; cân nhắc Slice hoặc cursor pagination |
| Sort theo field không tồn tại gây lỗi | Chưa allowlist sort key public |
| Filter object và Pageable bị trùng parameter | Tên property filter xung đột với page, size hoặc sort |
| @PageableDefault không phản ánh trong Swagger UI | Kiểm tra annotation, converter và JSON output của phiên bản đang dùng |

## 19. Quy ước thiết kế API phân trang

Một API danh sách dễ tích hợp nên thống nhất:

- Tên parameter page, size và sort.
- Cách đánh số trang bắt đầu từ 0 hay 1.
- Kích thước trang mặc định và tối đa.
- Cú pháp truyền nhiều tiêu chí sort.
- Danh sách sort key được hỗ trợ.
- Cách xử lý page/size không hợp lệ.
- Cấu trúc metadata trong response.
- Điều kiện lọc được áp dụng trước khi phân trang.
- Sort có tính ổn định khi nhiều bản ghi cùng giá trị.
- Khi nào dùng Page, Slice hoặc cursor.

Không để mỗi endpoint tự chọn quy ước khác nhau nếu không có lý do nghiệp vụ. Sự nhất quán giúp client dùng chung component phân trang và giảm lỗi tích hợp.

## 20. Checklist kết hợp @ParameterObject và Pageable

- [ ] Controller nhận Pageable thay vì tự khai báo page, size, sort rời rạc.
- [ ] Đã gắn @ParameterObject lên Pageable để springdoc mô tả query parameter.
- [ ] Filter DTO được tách khỏi Pageable và gắn @ParameterObject phù hợp.
- [ ] @PageableDefault phản ánh đúng page, size và sort mặc định.
- [ ] Tên parameter trong OpenAPI khớp cấu hình Spring Data Web.
- [ ] Quy ước zero-based/one-based được ghi rõ.
- [ ] Có default-page-size và max-page-size phù hợp.
- [ ] Sort key được giới hạn theo danh sách cho phép.
- [ ] Nhiều tiêu chí sort có cú pháp rõ ràng.
- [ ] Response Page/Slice có schema và metadata đúng.
- [ ] Đã cân nhắc DTO phân trang riêng cho public API.
- [ ] Đã kiểm tra /v3/api-docs.
- [ ] Đã kiểm tra binding, giới hạn và kết quả truy vấn bằng test runtime.
- [ ] Đã cân nhắc cursor pagination khi offset không còn phù hợp.

## 21. Nguồn tra cứu

- [springdoc-openapi – tài liệu chính thức](https://springdoc.org/)
- [Spring Data – Web Support](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html)
- [Spring Data – Pageable API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Pageable.html)
- [Spring Data – PageableDefault API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/web/PageableDefault.html)
- [OpenAPI Specification – Parameter Object](https://spec.openapis.org/oas/latest.html#parameter-object)

@ParameterObject giúp springdoc công bố Pageable thành các query parameter, còn Spring Data Web chịu trách nhiệm bind page, size và sort khi request đến. Kết hợp Pageable với query DTO giúp API vừa có bộ lọc nghiệp vụ vừa có phân trang nhất quán. Sau mỗi thay đổi annotation hoặc cấu hình Spring Data, hãy kiểm tra cả OpenAPI JSON và request runtime để bảo đảm client gửi đúng tham số và nhận đúng trang dữ liệu.

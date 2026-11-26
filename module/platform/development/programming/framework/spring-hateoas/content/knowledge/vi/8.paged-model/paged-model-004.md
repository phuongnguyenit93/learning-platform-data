# Link first và last

Khi API trả về một tập dữ liệu phân trang, client thường cần đi sang trang liền trước hoặc liền sau. Tuy nhiên, giao diện cũng có thể cần quay thẳng về trang đầu hoặc nhảy tới trang cuối. Spring HATEOAS biểu diễn hai điểm điều hướng này bằng các quan hệ liên kết `first` và `last` trong `PagedModel`.

`first` trỏ tới trang đầu tiên của tập kết quả hiện tại; `last` trỏ tới trang cuối cùng. Client đọc `href` từ các quan hệ này để điều hướng, không cần tự tính URI hoặc tự ghép tham số `page`. Với Spring Data, `PagedResourcesAssembler` có thể tạo các liên kết phân trang dựa trên `Page<T>` và request hiện tại. Bài học này thuộc chương **PagedModel** của module **SPRING_HATEOAS**, tập trung vào ý nghĩa, cách sinh, cấu hình và kiểm thử `first` cùng `last`.

Sau bài học, bạn có thể:

- Phân biệt `first` và `last` với `prev`, `next` và `self`.
- Hiểu quan hệ giữa chỉ số trang, kích thước trang và trang cuối.
- Dùng `PagedResourcesAssembler` để tạo liên kết điều hướng.
- Điều chỉnh việc luôn xuất `first` và `last` bằng `setForceFirstAndLastRels`.
- Giữ lại tham số lọc, sắp xếp và kích thước trang trong các liên kết.
- Kiểm thử link biên trang và xử lý tập dữ liệu rỗng hoặc không biết tổng số trang.

## 1. Ý nghĩa của first và last

Một `PagedModel` biểu diễn nội dung của trang hiện tại, metadata phân trang và các liên kết điều hướng. Các quan hệ thường gặp có ý nghĩa như sau:

| Relation | Ý nghĩa | Hành vi client thường thực hiện |
|---|---|---|
| `self` | Trang hiện tại | Làm mới hoặc chia sẻ URL của trang đang xem. |
| `first` | Trang đầu tiên | Quay về điểm bắt đầu của tập kết quả. |
| `prev` | Trang liền trước | Lùi một trang. |
| `next` | Trang liền sau | Tiến một trang. |
| `last` | Trang cuối cùng | Nhảy tới điểm kết thúc của tập kết quả. |

Ví dụ, client đang ở trang thứ ba trong tập có năm trang. Phản hồi có thể cung cấp:

```json
{
  "_links": {
    "self":  { "href": "https://api.example.com/orders?page=2&size=10" },
    "first": { "href": "https://api.example.com/orders?page=0&size=10" },
    "prev":  { "href": "https://api.example.com/orders?page=1&size=10" },
    "next":  { "href": "https://api.example.com/orders?page=3&size=10" },
    "last":  { "href": "https://api.example.com/orders?page=4&size=10" }
  },
  "page": {
    "size": 10,
    "totalElements": 47,
    "totalPages": 5,
    "number": 2
  }
}
```

Trong ví dụ, `number` là `2`, vì Spring Data đánh số trang từ `0` theo mặc định. Client không cần tự suy ra rằng trang cuối là `4`; nó chỉ theo liên kết `last`.

`first` và `last` hữu ích khi client có điều khiển “Trang đầu” hoặc “Trang cuối”, khi cần bỏ qua nhiều trang trung gian, hoặc khi người dùng muốn trở lại một điểm ổn định của kết quả tìm kiếm. Hai relation này cũng giúp client không phụ thuộc vào cách server tổ chức URL.

## 2. Cách tính trang đầu và trang cuối

Với phân trang dựa trên số trang (`Page<T>`), các giá trị cơ bản là:

- `page`: chỉ số trang, bắt đầu từ `0` theo cấu hình mặc định.
- `size`: số phần tử tối đa trong một trang.
- `totalElements`: tổng số phần tử phù hợp với truy vấn.
- `totalPages`: tổng số trang cần để chứa các phần tử.

Khi `size` lớn hơn `0`, số trang thường được tính theo công thức:

\[
totalPages = \left\lceil \frac{totalElements}{size} \right\rceil
\]

Nếu có ít nhất một trang, chỉ số của trang cuối là:

\[
lastPage = totalPages - 1
\]

Ví dụ với `totalElements = 47` và `size = 10`, có năm trang mang chỉ số `0`, `1`, `2`, `3`, `4`. Trang đầu là `0`, trang cuối là `4`.

| Trang hiện tại | `first` | `prev` | `next` | `last` |
|---:|---:|---:|---:|---:|
| 0 | 0 | Không có | 1 | 4 |
| 1 | 0 | 0 | 2 | 4 |
| 2 | 0 | 1 | 3 | 4 |
| 3 | 0 | 2 | 4 | 4 |
| 4 | 0 | 3 | Không có | 4 |

Bảng mô tả đích đến của từng relation khi tập kết quả có năm trang. Một relation có thể được lược khỏi phản hồi tùy cấu hình của assembler; client nên kiểm tra sự hiện diện của relation trước khi dùng.

## 3. Để PagedResourcesAssembler tạo first và last

Khi dùng Spring Data, cách thông dụng là để repository trả `Page<T>` rồi chuyển thành `PagedModel` qua `PagedResourcesAssembler`. Assembler sử dụng request hiện tại và cấu hình `Pageable` để dựng các link phân trang.

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.PagedModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
public class OrderController {

    private final OrderRepository repository;
    private final OrderModelAssembler orderAssembler;

    public OrderController(
            OrderRepository repository,
            OrderModelAssembler orderAssembler) {
        this.repository = repository;
        this.orderAssembler = orderAssembler;
    }

    @GetMapping
    public PagedModel<EntityModel<OrderResponse>> all(
            Pageable pageable,
            PagedResourcesAssembler<Order> pagedAssembler) {

        Page<Order> page = repository.findAll(pageable);
        return pagedAssembler.toModel(page, orderAssembler);
    }
}
```

`OrderModelAssembler` là `RepresentationModelAssembler<Order, EntityModel<OrderResponse>>`, chịu trách nhiệm chuyển từng đơn hàng thành biểu diễn có link riêng. `PagedResourcesAssembler` chịu trách nhiệm tạo `PagedModel`, metadata trang và các liên kết điều hướng cấp collection. Hai assembler này giải quyết hai cấp khác nhau: một phần tử và toàn bộ trang.

Với cấu hình mặc định, `PagedResourcesAssembler` không nhất thiết luôn xuất `first` và `last`. Theo API của Spring Data, mặc định `setForceFirstAndLastRels` là `false`; các relation này chỉ được thêm cùng nhóm liên kết điều hướng `prev` và `next`. Điều này có nghĩa client không nên mặc định hai link luôn xuất hiện ở mọi trang.

## 4. Luôn xuất first và last

Nếu hợp đồng API yêu cầu `first` và `last` luôn có mặt, kể cả khi client đang ở trang đầu hoặc trang cuối, có thể bật cờ `forceFirstAndLastRels` trước khi gọi `toModel`:

```java
@GetMapping
public PagedModel<EntityModel<OrderResponse>> all(
        Pageable pageable,
        PagedResourcesAssembler<Order> pagedAssembler) {

    Page<Order> page = repository.findAll(pageable);

    pagedAssembler.setForceFirstAndLastRels(true);
    return pagedAssembler.toModel(page, orderAssembler);
}
```

`setForceFirstAndLastRels(true)` yêu cầu assembler luôn thêm relation `first` và `last` vào `PagedModel` được tạo. Phương thức này có từ Spring Data Commons 1.11. Khi bật tùy chọn, client có thể dựa vào hai relation này như một phần ổn định của hợp đồng, kể cả ở trang đầu hoặc trang cuối.

Chỉ bật tùy chọn khi giao diện hoặc client thực sự cần hai link luôn hiện diện. Nếu API muốn phản ánh các bước điều hướng khả dụng một cách tối giản, cấu hình mặc định có thể phù hợp hơn. Dù chọn cách nào, tài liệu API và kiểm thử cần thể hiện rõ quy tắc xuất link.

## 5. Giữ nguyên bộ lọc, sắp xếp và page size

Liên kết `first` và `last` cần dẫn tới cùng tập kết quả mà client đang duyệt. Ví dụ client lọc đơn hàng theo trạng thái và sắp xếp theo ngày tạo:

```http
GET /orders?status=PAID&page=2&size=10&sort=createdAt,desc
```

Liên kết đầu và cuối cần giữ các điều kiện lọc, sắp xếp và kích thước trang, chỉ thay đổi giá trị `page`:

```text
first -> /orders?status=PAID&page=0&size=10&sort=createdAt,desc
last  -> /orders?status=PAID&page=4&size=10&sort=createdAt,desc
```

Khi dùng `PagedResourcesAssembler` với request hiện tại, assembler phối hợp với `HateoasPageableHandlerMethodArgumentResolver` để xây dựng liên kết trang. Nếu endpoint dùng tham số tùy chỉnh hoặc URI gốc khác, hãy cấu hình resolver phù hợp và truyền self link rõ ràng cho overload `toModel`:

```java
import org.springframework.hateoas.Link;

Link collectionLink = Link.of("https://api.example.com/orders?status=PAID")
        .withSelfRel();

return pagedAssembler.toModel(page, orderAssembler, collectionLink);
```

Đây là ví dụ về overload nhận link gốc tùy chỉnh; trong ứng dụng thực tế, hãy tạo link theo route và cấu hình triển khai thay vì cố định host. Không truyền một URL đã mất bộ lọc hoặc tham số sắp xếp, vì các link được dựng dựa trên link gốc đó.

Trong thực tế, không nên tự ghép chuỗi query parameter bằng tay. Dùng resolver và link builder để tránh lỗi mã hóa giá trị, mất tham số lặp, sai tên tham số tùy chỉnh hoặc sai base path khi triển khai sau reverse proxy.

## 6. Khi tự tạo PagedModel

`PagedModel` là kiểu biểu diễn chứa các phần tử, `PageMetadata` và các link được ứng dụng cung cấp. Khi tự tạo `PagedModel` mà không dùng `PagedResourcesAssembler`, bạn phải tạo link `first` và `last` rồi thêm chúng vào mô hình. Metadata trang tự nó không tự sinh ra các URI điều hướng.

```java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.PagedModel;

PagedModel.PageMetadata metadata = new PagedModel.PageMetadata(
        page.getSize(),
        page.getNumber(),
        page.getTotalElements(),
        page.getTotalPages()
);

PagedModel<EntityModel<OrderResponse>> model = PagedModel.of(
        orderModels,
        metadata
);

if (page.getTotalPages() > 0) {
    Link firstLink = Link.of(firstUri).withRel(IanaLinkRelations.FIRST);
    Link lastLink = Link.of(lastUri).withRel(IanaLinkRelations.LAST);
    model.add(firstLink, lastLink);
}
```

Trong ví dụ, `firstUri` và `lastUri` là URI đã được tạo từ route của collection, giữ các bộ lọc và sort hiện tại, với chỉ số trang lần lượt là `0` và `page.getTotalPages() - 1`. Ví dụ không tự tạo các URI đó để tránh che khuất phần xử lý base path, query parameter và mã hóa. Trong ứng dụng Spring MVC, có thể dùng `WebMvcLinkBuilder` cùng cấu hình pageable resolver để xây các URI này.

Điều kiện `totalPages > 0` ngăn việc tính trang cuối thành `-1` khi kết quả rỗng. Với trang rỗng, hãy xác định rõ hợp đồng mong muốn: có xuất `first` trỏ tới trang truy vấn rỗng hay bỏ cả `first` và `last`. Nếu dùng `PagedResourcesAssembler`, kiểm thử hành vi thực tế theo phiên bản và cấu hình của ứng dụng.

## 7. Phân biệt Page và Slice khi cần last

`first` và `last` có mức độ phụ thuộc dữ liệu khác nhau:

- Trang đầu có thể được xác định bằng chỉ số `0` mà không cần biết tổng số bản ghi.
- Trang cuối cần biết tổng số trang hoặc một quy tắc khác để xác định điểm kết thúc.

`Page<T>` cung cấp tổng số phần tử và tổng số trang, vì vậy có thể xác định đích của `last`. Tùy loại repository, thông tin tổng số có thể yêu cầu một truy vấn đếm bổ sung.

`Slice<T>` chỉ cho biết lát dữ liệu hiện tại và có trang tiếp theo hay không. Nó không công bố tổng số phần tử hoặc tổng số trang. Vì thế, với `Slice<T>`, ứng dụng có thể cung cấp `next` hoặc `prev` dựa trên trạng thái đã biết, nhưng không thể tạo một `last` chính xác nếu không truy vấn thêm thông tin tổng hoặc tự xác định trang cuối bằng cách khác.

Nếu API chỉ cần cuộn từng đoạn dữ liệu và không cần nhảy tới cuối, `Slice` có thể hiệu quả hơn. Nếu giao diện cần nút “Trang cuối” hoặc số trang tổng cộng, `Page` thường phù hợp hơn.

## 8. Kiểm thử first và last

Kiểm thử nên dùng tập dữ liệu có nhiều hơn một trang để xác nhận cả hai relation và URI đích. Ví dụ dưới đây giả định có ít nhất năm đơn hàng và page size bằng hai; controller bật `setForceFirstAndLastRels(true)`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrderPaginationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void firstAndLastLinksPointToBoundaryPages() throws Exception {
        mockMvc.perform(get("/orders")
                        .param("page", "1")
                        .param("size", "2")
                        .param("sort", "createdAt,desc")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$._links.first.href", containsString("page=0")))
                .andExpect(jsonPath("$._links.last.href", containsString("page=2")))
                .andExpect(jsonPath("$._links.first.href", containsString("size=2")))
                .andExpect(jsonPath("$._links.last.href", containsString("sort=createdAt")));
    }
}
```

Với năm phần tử và page size hai, có ba trang đánh số `0`, `1`, `2`; vì vậy `last` phải trỏ tới `page=2`. Dữ liệu fixture cần bảo đảm thứ tự ổn định và không thay đổi trong lúc kiểm thử.

Nên bổ sung kiểm thử ở các biên:

| Trường hợp | Điều cần xác nhận |
|---|---|
| Trang đầu, nhiều trang | `first` trỏ trang `0`; `last` trỏ trang cuối theo metadata. |
| Trang giữa | `first` và `last` giữ nguyên filter, sort và size. |
| Trang cuối | `last` trỏ chính trang cuối; không có `next`. |
| Chỉ có một trang | Kiểm tra quy tắc cấu hình: có thể luôn xuất first/last khi bật force. |
| Không có kết quả | Không tạo chỉ số trang cuối âm; phản hồi theo hợp đồng trang rỗng. |
| Filter trả về số trang khác | `last` được tính theo tập đã lọc, không theo toàn bộ bảng. |

Ngoài JSONPath, có thể đọc URI của link trong test và phân tích query parameter để xác nhận tất cả điều kiện tìm kiếm được giữ nguyên. Tránh so sánh toàn bộ URL tuyệt đối nếu host hoặc context path thay đổi theo môi trường.

## 9. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Giả định `first` và `last` luôn xuất hiện | Client lỗi khi relation bị lược theo cấu hình mặc định. | Kiểm tra link tồn tại hoặc bật `setForceFirstAndLastRels(true)`. |
| Tự tính trang cuối từ số phần tử hiện tại | Trang cuối sai khi trang hiện tại không phải trang cuối hoặc trang cuối không đầy. | Dùng `totalPages - 1` từ `Page` hoặc theo link do assembler sinh. |
| Quên giữ bộ lọc và sort | Nhảy về tập kết quả khác với tập client đang duyệt. | Dùng assembler/resolver hoặc tạo URI từ đầy đủ query hiện tại. |
| Dùng `Slice` nhưng vẫn công bố `last` | Client nhận một đích đến không thể xác định chính xác. | Dùng `Page` hoặc bổ sung cơ chế xác định tổng số/trang cuối. |
| Tính `totalPages - 1` khi không có kết quả | Có thể tạo page index `-1`. | Kiểm tra `totalPages > 0` trước khi tạo link cuối. |
| Dựa vào trường `page.number` thay cho relation | Client phải tự dựng URL và phụ thuộc cách đánh số trang. | Theo `href` của `first` hoặc `last`. |
| Không kiểm thử cấu hình force | Thay đổi cấu hình assembler làm hợp đồng link đổi mà test không phát hiện. | Kiểm thử trang đầu, giữa, cuối và trang đơn theo cấu hình thực tế. |

## 10. Quy trình triển khai

Khi cần công bố link `first` và `last` cho một API phân trang, thực hiện theo trình tự:

1. Xác định API dùng `Page` hay `Slice`; chỉ công bố `last` khi có thể xác định đích đến.
2. Dùng `PagedResourcesAssembler` để chuyển `Page` thành `PagedModel` và tạo các link điều hướng.
3. Quyết định `first` và `last` có phải xuất hiện ở mọi trang hay chỉ theo hành vi mặc định của assembler.
4. Nếu cần luôn có hai relation, bật `setForceFirstAndLastRels(true)` trước khi gọi `toModel`.
5. Bảo đảm link giữ nguyên filter, sort, page size và các tham số định tuyến của endpoint.
6. Kiểm thử URI của trang đầu và trang cuối với tập dữ liệu nhiều trang, một trang và rỗng.
7. Hướng dẫn client đọc relation và theo `href`, không tự ghép tham số trang.

`first` và `last` biến hai điểm biên của tập dữ liệu thành các quan hệ hypermedia mà client có thể khám phá. Khi được tạo từ metadata phân trang đúng và giữ nguyên điều kiện truy vấn, chúng giúp client điều hướng tới đầu hoặc cuối tập kết quả mà không cần biết cách server xây dựng URI.

## Tài liệu tham khảo

- [Spring Data Commons – PagedResourcesAssembler API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/web/PagedResourcesAssembler.html)
- [Spring Data Commons – Pageable và Page API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Page.html)
- [Spring HATEOAS – PagedModel và representation models](https://docs.spring.io/spring-hateoas/reference/server/representation-models.html)
- [IANA – Link Relation Types](https://www.iana.org/assignments/link-relations/link-relations.xhtml)

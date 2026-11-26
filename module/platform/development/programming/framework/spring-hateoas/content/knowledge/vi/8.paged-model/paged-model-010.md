# Khi nào dùng PagedModel?

`PagedModel<T>` là kiểu biểu diễn trong Spring HATEOAS dành cho một tập hợp được phân trang. Nó kế thừa khả năng chứa phần tử và liên kết của `CollectionModel<T>`, đồng thời bổ sung metadata mô tả trang hiện tại như số trang, kích thước trang, tổng số phần tử và tổng số trang.

Hãy dùng `PagedModel` khi API cần công bố kết quả phân trang theo kiểu page-based và client cần biết vị trí hiện tại trong toàn bộ tập kết quả. Ví dụ, trang quản trị đơn hàng hiển thị 20 đơn hàng mỗi lần, cần biết tổng cộng có bao nhiêu đơn và có bao nhiêu trang để hiển thị bộ điều hướng.

Không phải collection nào cũng cần `PagedModel`. Danh sách nhỏ có thể dùng `CollectionModel`; luồng dữ liệu lớn chỉ cần biết còn phần tử tiếp theo có thể phù hợp với `Slice` hoặc cursor pagination và các link điều hướng riêng. Quyết định dựa trên nhu cầu của client, chi phí truy vấn và cách dữ liệu được truy cập.

Sau bài học, bạn có thể:

- Nhận biết khi nào API cần metadata phân trang của `PagedModel`.
- Phân biệt `PagedModel`, `CollectionModel`, `Page` và `Slice`.
- Hiểu metadata trang và các link `first`, `prev`, `self`, `next`, `last`.
- Tích hợp Spring Data `Page<T>` với `PagedResourcesAssembler`.
- Trả `PagedModel` từ controller và serialize sang HAL.
- Kiểm thử metadata, link phân trang và các trường hợp trang đầu, trang cuối, collection rỗng.

## Bài toán phân trang trong REST API

Một endpoint trả toàn bộ đơn hàng có thể trở nên chậm khi dữ liệu tăng lên. Nếu client tải hàng chục nghìn phần tử trong một response, server phải truy vấn và serialize nhiều dữ liệu, mạng truyền tải nhiều byte, còn client phải giữ và xử lý một tập dữ liệu lớn.

Phân trang chia kết quả thành các phần nhỏ. Với offset pagination, client thường chỉ định số trang và kích thước trang:

```text
GET /orders?page=0&size=20
GET /orders?page=1&size=20
GET /orders?page=2&size=20
```

API trả một phần tử của tập kết quả trong mỗi response. Client cần biết thêm thông tin để điều hướng: trang hiện tại là trang nào, có bao nhiêu phần tử, tổng cộng bao nhiêu trang và có trang trước hoặc sau hay không.

Một mảng JSON thuần chỉ chứa các item không thể hiện metadata và link ở cấp trang. `PagedModel` cung cấp một representation có cấu trúc cho nhu cầu đó.

## PagedModel là gì?

`PagedModel<T>` là một kiểu hypermedia cho một trang kết quả. Nó có hai nhóm thông tin:

- **Content:** các phần tử thuộc trang hiện tại, kiểu mỗi phần tử là `T`.
- **Page metadata:** thông tin về số trang, kích thước trang, tổng số phần tử và tổng số trang.
- **Links:** liên kết đến trang hiện tại và các trang điều hướng có liên quan.

Có thể hình dung cấu trúc như sau:

```text
PagedModel<EntityModel<OrderResponse>>
├── content
│   ├── order 42
│   └── order 43
├── page
│   ├── size: 20
│   ├── number: 0
│   ├── totalElements: 57
│   └── totalPages: 3
└── links
    ├── self  -> /orders?page=0&size=20
    ├── next  -> /orders?page=1&size=20
    └── last  -> /orders?page=2&size=20
```

`T` là kiểu phần tử của trang. Nếu cần link riêng cho từng đơn hàng, dùng `PagedModel<EntityModel<OrderResponse>>`. Nếu item chỉ là DTO và không cần link riêng, có thể dùng `PagedModel<OrderResponse>`.

`PagedModel<T>` kế thừa `CollectionModel<T>`, vì vậy vẫn có link ở cấp collection. Phần bổ sung quan trọng là metadata trang.

## Khi nào nên dùng PagedModel?

Dùng `PagedModel` khi các điều kiện sau phù hợp với API:

1. Kết quả là một tập hợp có thể chia thành các trang theo số trang và kích thước trang.
2. Client cần biết số trang hiện tại, tổng số phần tử hoặc tổng số trang.
3. Client cần điều hướng rõ ràng đến trang trước, trang sau, trang đầu hoặc trang cuối.
4. Server có thể cung cấp metadata tổng số phần tử với chi phí truy vấn chấp nhận được.
5. Hợp đồng API muốn biểu diễn metadata và link phân trang theo một cấu trúc hypermedia ổn định.

Ví dụ phù hợp:

- Màn hình quản trị cần hiển thị “Trang 2 trên 15” và tổng số đơn hàng.
- Trang tìm kiếm cần hiển thị tổng số kết quả và cho phép nhảy đến một trang cụ thể.
- API báo cáo cần trả số bản ghi trong trang cùng tổng số bản ghi phù hợp điều kiện lọc.
- Client cần xây dựng bộ điều hướng trang từ các link do server cung cấp.

Trong những trường hợp này, metadata của `PagedModel` giúp client không phải tự tính trang cuối hoặc tự đoán URI của trang tiếp theo.

## Khi nào CollectionModel phù hợp hơn?

`CollectionModel<T>` phù hợp khi API cần biểu diễn một collection và các link liên quan nhưng không cần metadata phân trang như tổng số phần tử hoặc tổng số trang.

Ví dụ:

- Danh sách nhỏ, số lượng phần tử giới hạn và được trả trong một response.
- Một tập hợp tài nguyên liên quan được nhúng trong response của tài nguyên cha.
- Collection có link `self` và một số link liên quan nhưng không có khái niệm page number.
- API dùng cursor hoặc `Slice` để điều hướng tiếp mà không công bố tổng số bản ghi.

Nếu chỉ cần một link `next` để client tiếp tục lấy dữ liệu, có thể trả `CollectionModel<T>` và tự thêm link đó theo cơ chế cursor hoặc trạng thái truy vấn. Không cần tạo metadata tổng số trang nếu server không có hoặc không muốn tính thông tin đó.

## Phân biệt Page, Slice, CollectionModel và PagedModel

Các kiểu này giải quyết những phần khác nhau của bài toán:

| Kiểu | Thuộc thành phần | Nội dung chính | Metadata phân trang | Hypermedia links |
| --- | --- | --- | --- | --- |
| `Page<T>` | Spring Data | Nội dung trang truy vấn | Có tổng phần tử, tổng trang, số trang | Không phải representation HATEOAS |
| `Slice<T>` | Spring Data | Một lát kết quả | Có thông tin có trang tiếp theo/trước đó; không cần tổng số phần tử | Không tự tạo link HATEOAS |
| `CollectionModel<T>` | Spring HATEOAS | Collection phần tử | Không có metadata page chuyên biệt | Có |
| `PagedModel<T>` | Spring HATEOAS | Nội dung trang | Có | Có |

### Page<T>

`Page<T>` là abstraction của Spring Data cho kết quả truy vấn phân trang. Nó cung cấp nội dung trang, `getNumber()`, `getSize()`, `getTotalElements()`, `getTotalPages()`, `hasNext()` và các thông tin liên quan.

`Page` phù hợp ở tầng service hoặc repository khi ứng dụng cần metadata tổng số. Tuy nhiên, `Page` là kiểu của Spring Data, không phải một representation hypermedia. `PagedModel` là kiểu biểu diễn API có metadata và links.

### Slice<T>

`Slice<T>` phù hợp khi ứng dụng chỉ cần biết có dữ liệu tiếp theo hay không. Nó không yêu cầu tính tổng số bản ghi hoặc tổng số trang. Điều này có thể giảm chi phí, nhất là với tập dữ liệu lớn hoặc truy vấn phức tạp.

Nếu client không cần “tổng cộng 10.000 kết quả” mà chỉ cần nút “Tải thêm”, `Slice<T>` hoặc cursor pagination thường là lựa chọn tốt hơn. Có thể biểu diễn kết quả bằng `CollectionModel<T>` và công bố link `next` khi `hasNext()` là true.

### CollectionModel<T>

`CollectionModel<T>` biểu diễn một tập hợp cùng links. Nó không khẳng định rằng tập hợp được phân trang và không cung cấp `totalElements` hay `totalPages`.

### PagedModel<T>

`PagedModel<T>` biểu diễn một trang có metadata và links. Nó thích hợp khi API cần mô tả rõ vị trí trang trong tập kết quả và hỗ trợ điều hướng page-based.

## Metadata của PagedModel

`PagedModel` cung cấp `PageMetadata` với bốn giá trị cơ bản:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `size` | Kích thước trang được dùng cho truy vấn hiện tại |
| `number` | Chỉ số trang hiện tại, thường bắt đầu từ 0 với Spring Data `Pageable` |
| `totalElements` | Tổng số phần tử phù hợp truy vấn |
| `totalPages` | Tổng số trang theo kích thước trang và tổng số phần tử |

Ví dụ, có 57 đơn hàng và mỗi trang có 20 phần tử:

```text
size          = 20
number        = 0
totalElements = 57
totalPages    = 3
```

Trang 0 chứa tối đa 20 phần tử; trang 1 chứa tối đa 20 phần tử; trang 2 chứa 17 phần tử. Chỉ số trang trong `Pageable` là zero-based, trong khi giao diện người dùng có thể hiển thị trang 1, 2, 3 bằng cách cộng thêm 1 khi trình bày.

Tổng số trang phụ thuộc vào tổng số phần tử và kích thước trang. Khi không có phần tử, tổng số trang thường là 0. Client không nên giả định rằng trang cuối luôn có đủ `size` phần tử.

## Các link phân trang

Một `PagedModel` thường công bố một số quan hệ link để client điều hướng:

| Relation | Ý nghĩa | Khi thường xuất hiện |
| --- | --- | --- |
| `self` | Trang hiện tại | Có ở response trang |
| `first` | Trang đầu tiên | Khi assembler công bố link đầu |
| `prev` | Trang trước | Khi trang hiện tại không phải trang đầu |
| `next` | Trang tiếp theo | Khi trang hiện tại chưa phải trang cuối |
| `last` | Trang cuối cùng | Khi assembler công bố link cuối |

Các link này giúp client đi theo URI do server tạo. Client không cần tự tăng `page` hoặc tự ghép `size` vào URL. Nếu có bộ lọc hoặc sắp xếp, cần kiểm tra các link được sinh có giữ đúng ngữ cảnh truy vấn theo hợp đồng hay không.

Ở trang đầu, `prev` không có ý nghĩa; ở trang cuối, `next` không có ý nghĩa. Với collection rỗng, response vẫn có thể có link `self` nhưng không có link điều hướng đến trang dữ liệu.

## Dùng PagedResourcesAssembler với Spring Data

Trong ứng dụng Spring Data, cách phổ biến để chuyển `Page<T>` thành `PagedModel<D>` là dùng `PagedResourcesAssembler<T>`. Assembler này nhận page từ service/repository, chuyển từng phần tử thành representation model và tạo metadata cùng các link phân trang.

Giả sử mô hình và service:

```java
import java.util.Optional;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

public record Order(Long id, String description, String status) {}

public record OrderResponse(Long id, String description, String status) {}

public interface OrderService {
    Page<Order> findAll(Pageable pageable);
    Optional<Order> findById(Long id);
}
```

Assembler chuyển một đơn hàng thành `EntityModel<OrderResponse>`:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderResponse>> {

    @Override
    public EntityModel<OrderResponse> toModel(Order order) {
        OrderResponse content = new OrderResponse(
            order.id(), order.description(), order.status());

        return EntityModel.of(content,
            linkTo(methodOn(OrderController.class).one(order.id())).withSelfRel());
    }
}
```

Controller nhận `Pageable`, lấy `Page<Order>` và dùng `PagedResourcesAssembler`:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.PagedModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService orderService;
    private final OrderModelAssembler orderModelAssembler;
    private final PagedResourcesAssembler<Order> pagedResourcesAssembler;

    OrderController(
            OrderService orderService,
            OrderModelAssembler orderModelAssembler,
            PagedResourcesAssembler<Order> pagedResourcesAssembler) {
        this.orderService = orderService;
        this.orderModelAssembler = orderModelAssembler;
        this.pagedResourcesAssembler = pagedResourcesAssembler;
    }

    @GetMapping
    PagedModel<EntityModel<OrderResponse>> all(Pageable pageable) {
        Page<Order> page = orderService.findAll(pageable);
        return pagedResourcesAssembler.toModel(page, orderModelAssembler);
    }

    @GetMapping("/{id}")
    EntityModel<OrderResponse> one(@PathVariable Long id) {
        Order order = orderService.findById(id)
            .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
        return orderModelAssembler.toModel(order);
    }
}
```

Ví dụ giả định các kiểu `Order`, `OrderResponse` và `OrderService` được đặt trong package ứng dụng. Spring Boot với Spring Data Web hỗ trợ phân giải `Pageable` từ query parameters; `PagedResourcesAssembler` được cung cấp trong tích hợp Spring Data Web/HATEOAS tương ứng.

Client có thể gọi:

```text
GET /orders?page=0&size=20&sort=id,asc
```

`PagedResourcesAssembler` dùng page metadata để tạo `PagedModel` và link điều hướng. Nó cũng dùng `OrderModelAssembler` để chuyển từng `Order` thành `EntityModel<OrderResponse>`. Nhờ đó mỗi item có link `self`, còn response trang có metadata và các link phân trang.

## Tạo PagedModel thủ công

Không phải mọi nguồn dữ liệu đều trả `Page<T>`. Nếu ứng dụng đã có content và metadata trang từ một dịch vụ khác, có thể tạo `PagedModel` trực tiếp bằng `PagedModel.of(...)`:

```java
List<OrderResponse> content = ...;

PagedModel.PageMetadata metadata = new PagedModel.PageMetadata(
    20, 0, 57, 3);

PagedModel<OrderResponse> model = PagedModel.of(
    content,
    metadata,
    selfLink,
    nextLink,
    lastLink);
```

Thứ tự tham số của `PageMetadata` là `size`, `number`, `totalElements`, `totalPages`. Các link phải được tính từ metadata và URI của endpoint thực tế. Không được tự đặt `totalElements` hoặc `totalPages` theo ước lượng vì client có thể dựa vào chúng để hiển thị hoặc điều hướng.

Tạo thủ công phù hợp khi metadata đến từ dịch vụ tìm kiếm, API upstream hoặc nguồn dữ liệu không phải Spring Data. Nếu nguồn đã trả `Page<T>`, ưu tiên assembler tích hợp để tránh tự viết lại logic tạo link và metadata.

## HAL JSON của PagedModel

Khi serialize thành HAL, `PagedModel` thường có ba nhóm dữ liệu: `_embedded` chứa các phần tử, `_links` chứa liên kết và `page` chứa metadata.

Ví dụ response:

```json
{
  "_embedded": {
    "orders": [
      {
        "id": 42,
        "description": "Bàn phím cơ",
        "status": "PAID",
        "_links": {
          "self": { "href": "https://api.example.com/orders/42" }
        }
      }
    ]
  },
  "_links": {
    "self": { "href": "https://api.example.com/orders?page=0&size=20" },
    "next": { "href": "https://api.example.com/orders?page=1&size=20" },
    "last": { "href": "https://api.example.com/orders?page=2&size=20" }
  },
  "page": {
    "size": 20,
    "totalElements": 57,
    "totalPages": 3,
    "number": 0
  }
}
```

Đây là response minh họa. Tên relation nhúng phụ thuộc relation provider; link thực tế phụ thuộc request, cấu hình resolver, base URI và trang hiện tại. Client nên đọc relation thay vì dựa vào vị trí hoặc thứ tự các link.

## Chú ý hiệu năng và giới hạn phân trang

`Page<T>` thường cần tổng số phần tử để tính tổng số trang. Với nhiều repository, điều đó có thể yêu cầu thêm count query. Truy vấn đếm có thể tốn kém khi tập dữ liệu lớn, điều kiện lọc phức tạp hoặc join nhiều bảng.

Trước khi chọn `PagedModel`, hãy cân nhắc:

- Client có thật sự cần tổng số kết quả và tổng số trang không?
- Count query có chi phí chấp nhận được không?
- Kích thước trang có giới hạn hợp lý không?
- Có chỉ mục hỗ trợ sắp xếp và lọc không?
- Dữ liệu có thay đổi thường xuyên trong lúc client duyệt các trang không?
- Offset sâu có làm truy vấn chậm không?

Nên đặt kích thước trang mặc định và giới hạn tối đa. Không để client yêu cầu hàng trăm nghìn phần tử trong một trang. Có thể dùng `@PageableDefault` cho giá trị mặc định và cấu hình resolver để giới hạn `maxPageSize` theo phiên bản Spring Boot/Spring Data đang dùng.

Offset pagination có thể gặp hiện tượng phần tử dịch chuyển giữa các trang nếu dữ liệu được thêm hoặc xóa trong lúc client đang duyệt. Sắp xếp theo trường ổn định và có tie-breaker duy nhất giúp giảm sự không nhất quán. Với luồng dữ liệu lớn hoặc cập nhật liên tục, cursor/keyset pagination có thể phù hợp hơn vì nó tiếp tục từ khóa cuối cùng đã đọc thay vì tính offset lớn.

Nếu không cần tổng số phần tử, cân nhắc `Slice<T>` và link `next`. Nếu cần điều hướng bằng cursor, hãy công bố cursor opaque trong link và để server giải mã/kiểm tra cursor; client không nên tự tính cursor từ dữ liệu hiển thị.

## Khi nào không nên dùng PagedModel?

Tránh dùng `PagedModel` trong các trường hợp sau:

- **Một tài nguyên đơn lẻ:** dùng `EntityModel<T>`.
- **Collection nhỏ và không phân trang:** dùng `CollectionModel<T>` hoặc `CollectionModel<EntityModel<T>>`.
- **Chỉ cần biết có dữ liệu tiếp theo:** cân nhắc `Slice<T>` và `CollectionModel` có link `next`.
- **Duyệt dữ liệu lớn bằng cursor/keyset:** mô hình hóa link cursor trong collection; không ép thành page number nếu không có ngữ nghĩa trang phù hợp.
- **Tổng số phần tử quá đắt để tính và client không cần:** tránh truy vấn count chỉ để tạo metadata page.

Chọn `PagedModel` vì hợp đồng cần metadata trang, không chỉ vì repository trả về một danh sách có nhiều phần tử.

## Kiểm thử PagedModel

Kiểm thử nên xác minh content, metadata và các link điều hướng. Với trang đầu, có thể kiểm tra `self`, `next`, `last` và metadata; với trang cuối, kiểm tra `prev` và xác minh không có `next`.

Ví dụ với Spring MVC Test:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrderPagingControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void firstPageContainsMetadataAndNextLink() throws Exception {
        mockMvc.perform(get("/orders?page=0&size=20")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$.page.number").value(0))
            .andExpect(jsonPath("$.page.size").value(20))
            .andExpect(jsonPath("$.page.totalElements").exists())
            .andExpect(jsonPath("$._links.self.href").exists())
            .andExpect(jsonPath("$._links.next.href").exists());
    }
}
```

Test giả định dữ liệu test có hơn 20 đơn hàng. Nếu dữ liệu chỉ có một trang, `next` không xuất hiện và test phải chuẩn bị dataset phù hợp. Nên có test riêng cho trang cuối và kết quả rỗng.

Các trường hợp nên kiểm thử:

1. Trang đầu có metadata chính xác và link `next` khi còn trang.
2. Trang giữa có cả link `prev` và `next`.
3. Trang cuối không có link `next`.
4. Trang rỗng trả metadata hợp lệ và link `self`.
5. Link phân trang giữ lại điều kiện lọc và sắp xếp theo hợp đồng.
6. `size` vượt giới hạn được xử lý theo cấu hình.
7. Thứ tự sắp xếp có tính ổn định khi nhiều bản ghi trùng giá trị sort.
8. Các trường content và link riêng của item vẫn đúng khi dùng `PagedModel<EntityModel<T>>`.

## Những sai lầm thường gặp

**Dùng PagedModel cho mọi danh sách.** PagedModel có ý nghĩa khi cần metadata page. Collection nhỏ hoặc cursor navigation có thể dùng CollectionModel.

**Nhầm Page với PagedModel.** `Page<T>` là kết quả phân trang của Spring Data; `PagedModel<T>` là representation hypermedia. `PagedResourcesAssembler` giúp chuyển từ Page sang PagedModel.

**Tự tính link bằng cách nối chuỗi page number.** Link có thể phụ thuộc base URI, prefix, sort, filter và cấu hình resolver. Dùng `PagedResourcesAssembler` hoặc URI builder phù hợp.

**Không giới hạn kích thước trang.** Request size quá lớn có thể gây tải nặng lên database, server và client. Hãy đặt mặc định và giới hạn tối đa.

**Không tính chi phí tổng số bản ghi.** `Page` thường cần count query. Nếu client không cần tổng số, cân nhắc `Slice` hoặc cursor pagination.

**Bỏ qua sắp xếp ổn định.** Nếu sort không xác định thứ tự duy nhất, phần tử có thể lặp hoặc bị bỏ qua giữa các trang. Hãy thêm trường tie-breaker ổn định như ID.

**Kiểm thử chỉ số lượng item.** Hợp đồng PagedModel gồm metadata, link trang và link item. Kiểm thử cần xác minh tất cả phần client sử dụng.

## Kết luận

`PagedModel<T>` phù hợp khi API cần biểu diễn một trang kết quả cùng metadata như số trang, kích thước, tổng số phần tử và tổng số trang, đồng thời cung cấp link điều hướng. Với Spring Data, `PagedResourcesAssembler<T>` là cầu nối thuận tiện từ `Page<T>` sang `PagedModel<D>` và có thể dùng `RepresentationModelAssembler` để tạo link cho từng item.

Hãy chọn `PagedModel` khi client cần page-based navigation và metadata tổng số có giá trị. Dùng `CollectionModel` cho collection không cần metadata trang, hoặc khi chỉ cần link `next` theo kiểu `Slice`/cursor. Trước khi quyết định, cân nhắc chi phí count query, giới hạn page size, sort ổn định và cách dữ liệu thay đổi trong lúc client duyệt trang. Kiểm thử cả metadata lẫn link để bảo đảm hợp đồng phân trang có thể được client sử dụng đáng tin cậy.

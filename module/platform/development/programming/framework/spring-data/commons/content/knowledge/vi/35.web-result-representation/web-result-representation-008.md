# Liên kết điều hướng, URI hiện tại và tham số phân trang

Một phản hồi phân trang hữu ích không chỉ cho biết có bao nhiêu phần tử. Nó còn có thể cung cấp liên kết để client lấy trang trước, trang sau hoặc quay về trang đầu. Liên kết chỉ đúng khi vẫn trỏ đến cùng tài nguyên, cùng bộ lọc và cùng thứ tự, đồng thời dùng đúng quy ước tham số mà server hiểu.

Bài học thuộc chương **Biểu diễn kết quả web** của module **SPRING_DATA_COMMONS**. Trọng tâm là cách hạ tầng web của Spring Data phối hợp với Spring HATEOAS để tạo liên kết từ kết quả repository và URI của request, đồng thời giữ ranh giới với khả năng thực thi của từng store.

## 1. Liên kết điều hướng là một phần của hợp đồng truy vấn

Giả sử client gọi:

```http
GET /api/orders?status=PAID&page=1&size=20&sort=id,asc
```

Theo quy ước đánh số từ 0, client đang đọc trang thứ hai của các đơn hàng đã thanh toán. Nếu có tổng 55 đơn hàng phù hợp, các đích điều hướng có thể là:

| Relation | Ý nghĩa | Chỉ số trang trong ví dụ |
| --- | --- | --- |
| `self` | Trang đang được biểu diễn | 1 |
| `prev` | Trang trước | 0 |
| `next` | Trang kế tiếp | 2 |
| `first` | Trang đầu | 0 |
| `last` | Trang cuối theo tổng hiện có | 2 |

Mỗi liên kết vẫn phải giữ `status=PAID`, `size=20` và thứ tự `id,asc`. Một link `next` bỏ mất status sẽ dẫn tới một tập kết quả khác, dù số trang có vẻ đúng.

Vì vậy có thể xem một liên kết trang là:

```text
URI của tập kết quả
    + điều kiện lọc
    + thứ tự sắp xếp
    + kích thước trang
    + vị trí trang đích
```

Không phải mọi relation đều xuất hiện trong mọi phản hồi. Ở trang đầu không có trang trước; ở trang cuối không có trang tiếp theo. Client nên quan sát relation được cung cấp thay vì mặc định bộ link luôn đủ năm phần tử.

## 2. Thành phần nào tạo liên kết?

Spring Data Commons có `PagedResourcesAssembler<T>` để chuyển `Page<T>` thành một mô hình phân trang của **Spring HATEOAS** và bổ sung liên kết điều hướng.

Cần phân biệt:

| Kiểu | Vai trò trong bài |
| --- | --- |
| `org.springframework.data.domain.Page` | Kết quả phân trang và thông tin về các trang |
| `org.springframework.data.web.PagedResourcesAssembler` | Dùng trang, resolver và URI để tạo mô hình có link |
| `org.springframework.hateoas.PagedModel` | Mô hình phản hồi có thể mang metadata và các link |
| `org.springframework.data.web.PagedModel` | Biểu diễn trang đơn giản của Commons, không tự tạo link điều hướng |

Tên assembler nằm trong package Spring Data, nhưng kiểu `PagedModel` dùng cho liên kết ở đây thuộc package HATEOAS. Không thay import bằng lớp Commons rồi kỳ vọng cùng API.

Các cách chuyển đổi và constructor của assembler được mô tả trong [PagedResourcesAssembler API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/web/PagedResourcesAssembler.html).

Luồng xử lý:

```text
Request HTTP
    -> Resolver tạo Pageable
    -> Service/repository tạo Page
    -> Assembler đọc trạng thái trang
    -> Assembler chọn URI nền và điền tham số trang đích
    -> Mô hình HATEOAS được serialize
```

Assembler không tạo dữ liệu truy vấn. Một store phải hỗ trợ kiểu truy vấn tương ứng, hoặc ứng dụng phải cung cấp một kết quả phân trang hợp lệ trước đó.

## 3. Ví dụ controller dùng URI của request hiện tại

Ví dụ giả định Java 17 trở lên, Spring MVC, Spring Data Web Support và Spring HATEOAS đã được cấu hình cho HAL. `OrderQueries` được ứng dụng cài đặt bằng cơ chế truy vấn của store phù hợp.

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PageableDefault;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.PagedModel;
import org.springframework.hateoas.server.core.Relation;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderQueries queries;

    OrderController(OrderQueries queries) {
        this.queries = queries;
    }

    @GetMapping(produces = MediaTypes.HAL_JSON_VALUE)
    PagedModel<EntityModel<OrderView>> list(
            @RequestParam(name = "status", defaultValue = "PAID")
            String status,
            @PageableDefault(size = 20, sort = "id")
            Pageable pageable,
            PagedResourcesAssembler<OrderView> assembler) {

        Page<OrderView> page =
                queries.findByStatus(status, pageable);

        return assembler.toModel(page);
    }
}

interface OrderQueries {
    Page<OrderView> findByStatus(
            String status,
            Pageable pageable);
}

@Relation(collectionRelation = "orders")
record OrderView(Long id, String status) {
}
```

`OrderQueries` là cổng truy vấn, không tự được Spring tạo implementation chỉ nhờ tên phương thức. Implementation phải áp dụng status, phạm vi dữ liệu và các chính sách truy vấn phù hợp. Controller minh họa này cũng chưa triển khai chính sách kiểm tra sort.

Với request:

```http
GET https://api.example.com/api/orders?status=PAID&page=1&size=20&sort=id,asc
Accept: application/hal+json
```

và tổng 55 phần tử, **trích phần link và metadata** có thể là:

```json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/api/orders?status=PAID&page=1&size=20&sort=id,asc"
    },
    "prev": {
      "href": "https://api.example.com/api/orders?status=PAID&page=0&size=20&sort=id,asc"
    },
    "next": {
      "href": "https://api.example.com/api/orders?status=PAID&page=2&size=20&sort=id,asc"
    },
    "first": {
      "href": "https://api.example.com/api/orders?status=PAID&page=0&size=20&sort=id,asc"
    },
    "last": {
      "href": "https://api.example.com/api/orders?status=PAID&page=2&size=20&sort=id,asc"
    }
  },
  "page": {
    "size": 20,
    "number": 1,
    "totalElements": 55,
    "totalPages": 3
  }
}
```

Phần nội dung các đơn hàng không được trình bày trong trích đoạn này. Thứ tự property hoặc cách encode những ký tự tương đương trong URL có thể khác; cần so sánh ý nghĩa URI thay vì so từng ký tự một cách máy móc.

Việc truyền assembler vào handler và phối hợp với resolver là một phần của [tích hợp hypermedia trong Spring Data Web Support](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions-web.html). Chỉ khai báo media type trên mapping chưa thay thế việc cấu hình hạ tầng HAL của ứng dụng.

## 4. URI hiện tại bao gồm những gì?

Một URI công khai có thể gồm:

```text
https://api.example.com/shop/api/orders?status=PAID&page=1&size=20
|----| |-------------| |-------------| |-----------------------------|
scheme      host             path                 query
```

Path có thể bao gồm context path, servlet mapping hoặc tiền tố do hệ thống triển khai quy định. Không nên giả định mọi ứng dụng đều chạy tại root `/`.

Khi không có URI nền được chỉ định riêng, assembler có thể sử dụng URI của request hiện tại. Ở mức Spring MVC, hai factory method dễ bị nhầm là:

| Factory method | Có query hiện tại? |
| --- | --- |
| `ServletUriComponentsBuilder.fromCurrentRequest()` | Có |
| `ServletUriComponentsBuilder.fromCurrentRequestUri()` | Không |

Sự khác nhau này được nêu trong [ServletUriComponentsBuilder API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/servlet/support/ServletUriComponentsBuilder.html).

Nếu tự dựng URI từ phương án không có query rồi chỉ thêm page và size, ứng dụng có thể vô tình bỏ mất `status`, từ khóa tìm kiếm hoặc một bộ lọc khác.

### 4.1. Cùng đường dẫn chưa chắc cùng tập dữ liệu

Hai URI sau cùng path nhưng khác truy vấn:

```http
/api/orders?status=PAID&page=0&size=20
/api/orders?status=CANCELLED&page=0&size=20
```

Link điều hướng phải tiếp tục truy vấn tập đang được biểu diễn. Không chỉ lấy path rồi tăng một con số.

### 4.2. Không phải mọi trạng thái tìm kiếm đều có sẵn trong URI

Điều kiện nằm trong request body hoặc trạng thái tạm trong frontend không tự xuất hiện trong URI hiện tại.

Nếu kết quả được tạo từ một payload tìm kiếm phức tạp, cần thiết kế cách tiếp tục truy vấn: đưa các điều kiện được hỗ trợ vào query, tạo một tài nguyên tìm kiếm có định danh, hoặc cung cấp cơ chế khác theo hợp đồng API. Một link GET không tự gửi lại body của request trước đó.

Giá trị mặc định hoặc bộ lọc đã chuẩn hóa ở server cũng cần được xét. Nếu URI không ghi status và controller luôn mặc định PAID, điều hướng tiếp tục có thể vẫn dùng cùng mặc định. Nếu muốn link mô tả tường minh trạng thái đã xử lý, ứng dụng phải đưa giá trị đó vào URI nền phù hợp.

## 5. Giữ bộ lọc, sort và encode đúng

### 5.1. Chỉ thay vị trí trang cần điều hướng

Với request:

```http
GET /api/orders?status=PAID&page=1&size=20&sort=createdAt,desc&sort=id,asc
```

Link next phải giữ cả hai khóa sort. Nếu chỉ còn `sort=id,asc`, thứ tự của tập kết quả đã thay đổi.

Với một tham số phân trang đơn trị, cần **thay** giá trị cũ thay vì nối thêm:

```text
Đúng về ý định:
?page=2&size=20

Dễ gây xử lý không nhất quán:
?page=1&page=2&size=20
```

Bộ dựng URI phân trang của Spring sử dụng resolver để điền vị trí và kích thước phù hợp. Khi tự tùy chỉnh link, vẫn phải giữ nguyên nguyên tắc tránh tham số page/size bị lặp ngoài ý muốn.

### 5.2. Tham số lặp có thể có ý nghĩa hợp lệ

`sort` có thể lặp để mô tả nhiều thứ tự ưu tiên. Các bộ lọc như `tag` cũng có thể được thiết kế là đa trị.

Không gom toàn bộ query vào một `Map<String, String>` rồi dựng lại nếu hợp đồng có tham số đa trị, vì một giá trị có thể ghi đè giá trị khác. Cấu trúc URI cần giữ đúng tập giá trị của từng tham số.

### 5.3. Không nối chuỗi tùy ý để encode giá trị

Giả sử từ khóa là `A+B & C`. Nếu ghép thẳng vào `?q=`, dấu cộng và dấu `&` có thể bị hiểu sai khi request tiếp theo được phân tích.

Ví dụ tạo URI từ một giá trị thô bằng template:

```java
import java.net.URI;

import org.springframework.web.util.UriComponentsBuilder;

URI uri = UriComponentsBuilder
        .fromUriString("https://api.example.com/api/orders")
        .queryParam("q", "{keyword}")
        .queryParam("page", 1)
        .queryParam("size", 20)
        .encode()
        .buildAndExpand("A+B & C")
        .toUri();
```

Đoạn này chỉ minh họa encode một URI dùng tên tham số mặc định; nó không thay thế resolver trong mọi cấu hình phân trang.

Spring giải thích việc encode template và biến URI trong [hướng dẫn dựng URI](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-uri-building.html). Khi thao tác trên URI đã encode, cần tránh encode lại toàn bộ chuỗi như thể đó vẫn là giá trị thô, khiến một dấu phần trăm bị biến đổi thêm.

## 6. Resolver đọc request và resolver tạo link phải đồng bộ

### 6.1. Tên tham số không phải lúc nào cũng là page, size, sort

Ứng dụng có thể chọn hợp đồng:

```http
GET /api/orders?p=1&limit=20&order=createdAt,desc&order=id,asc
```

Nếu server đọc `p` nhưng link lại sinh `page`, client đi theo next có thể quay lại trang mặc định. Link hợp lệ về cú pháp nhưng sai hành vi.

`HateoasPageableHandlerMethodArgumentResolver` vừa giải quyết thông tin trang vừa có khả năng bổ sung tham số vào URI. Xem [API của resolver hỗ trợ HATEOAS](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/web/HateoasPageableHandlerMethodArgumentResolver.html).

Tên tham số sort thuộc phần cấu hình resolver sort phối hợp. Đổi tên tham số page và size không phải một lệnh đổi đồng thời mọi quy ước của sort.

### 6.2. Quy ước bắt đầu từ 1 phải được chuyển đổi nhất quán

Khi HTTP được cấu hình bắt đầu từ 1:

```text
Request page=1  -> Page nội bộ có số trang 0
Request page=2  -> Page nội bộ có số trang 1
```

Khi tạo link, resolver cần thực hiện chuyển đổi ngược đúng một lần. Không tự cộng 1 trong controller rồi để resolver cộng thêm lần nữa.

Implementation assembler được dẫn trong bài cũng căn chỉnh number của metadata HATEOAS theo cấu hình one-indexed của resolver. Vì vậy không suy ra hành vi của mô hình HATEOAS từ lớp `org.springframework.data.web.PagedModel` đơn giản, vốn đọc number trực tiếp từ trang nguồn.

Cơ chế điền tham số trang và điều chỉnh chỉ số được thể hiện trong [mã nguồn HateoasPageableHandlerMethodArgumentResolver](https://raw.githubusercontent.com/spring-projects/spring-data-commons/main/src/main/java/org/springframework/data/web/HateoasPageableHandlerMethodArgumentResolver.java).

### 6.3. Link nên phản ánh kết quả phân trang thực sự được áp dụng

Client có thể yêu cầu size vượt mức và server chuẩn hóa về một kích thước nhỏ hơn. Với luồng assembler mặc định, thông tin `Pageable` của kết quả được dùng khi tạo link.

Không tự sao chép lại size thô chưa được áp dụng vào mọi link. Tương tự, nếu service đã điều chỉnh trang hoặc thứ tự theo một chính sách công bố rõ ràng, metadata và link cần mô tả đúng kết quả đó.

Assembler không xác định thay ứng dụng khi nào phải trả 400 cho request không hợp lệ. Binding, kiểm tra hợp đồng và biểu diễn kết quả vẫn là các trách nhiệm khác nhau.

## 7. Chỉ định URI nền hoặc self link riêng

### 7.1. URI nền cố định phải giữ đủ điều kiện truy vấn

Một trường hợp cần URI nền riêng là API công khai dùng đường dẫn khác URI mà backend nhận được. Constructor của assembler có thể nhận một `UriComponents` làm URI nền.

Ví dụ helper sau áp dụng cho **một tập phân trang không qualifier**, với URI collection công khai lấy từ cấu hình tin cậy:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.web.HateoasPageableHandlerMethodArgumentResolver;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.PagedModel;
import org.springframework.web.util.UriComponents;
import org.springframework.web.util.UriComponentsBuilder;

// Đặt phương thức trong một lớp tiện ích hoặc thành phần của ứng dụng.
static PagedModel<EntityModel<OrderView>> publicPage(
        Page<OrderView> page,
        String status,
        String publicCollectionUri,
        HateoasPageableHandlerMethodArgumentResolver configuredResolver) {

    UriComponents baseUri = UriComponentsBuilder
            .fromUriString(publicCollectionUri)
            .queryParam("status", "{status}")
            .encode()
            .buildAndExpand(status);

    PagedResourcesAssembler<OrderView> assembler =
            new PagedResourcesAssembler<>(
                    configuredResolver,
                    baseUri);

    return assembler.toModel(page);
}
```

Giả định `publicCollectionUri` là URI collection không kèm query và `status` đã được ứng dụng xử lý hợp lệ. Nếu truy vấn còn có từ khóa, khoảng thời gian hoặc những bộ lọc khác, helper cũng phải đưa chúng vào URI nền. Các tham số phân trang được resolver bổ sung từ trang kết quả.

Điểm quan trọng là truyền resolver có cấu hình phù hợp. Tự tạo assembler với resolver mặc định trong khi handler dùng quy ước khác sẽ làm mất tính nhất quán.

### 7.2. Overload nhận Link coi link đó là self được cung cấp

Một lựa chọn khác:

```java
import org.springframework.hateoas.Link;

Link selfLink = Link.of(publicSelfHref).withSelfRel();
return assembler.toModel(page, selfLink);
```

Đoạn này giả định `publicSelfHref` đã được ứng dụng dựng thành link self đúng cho kết quả hiện tại.

Cần phân biệt link self hoàn chỉnh với một URI collection chưa có vị trí trang. Trong implementation hiện tại được dẫn, overload này giữ self link do ứng dụng cung cấp và dùng href đó làm nền tạo các link điều hướng. Không dựa vào overload để tự sửa một self link đang mô tả sai trang hoặc thiếu bộ lọc.

Nếu muốn assembler tự điền cả self theo resolver, cách dùng URI nền với `toModel(page)` có ý nghĩa khác với truyền self link tường minh. Cách chọn URI và bổ sung từng relation được thể hiện trong [mã nguồn PagedResourcesAssembler](https://raw.githubusercontent.com/spring-projects/spring-data-commons/main/src/main/java/org/springframework/data/web/PagedResourcesAssembler.java).

## 8. Nhiều Pageable cần đúng ngữ cảnh qualifier

Một dashboard có thể có hai danh sách độc lập. Chữ ký minh họa:

```java
import org.springframework.beans.factory.annotation.Qualifier;

void dashboard(
        @Qualifier("orders") Pageable orders,
        @Qualifier("customers") Pageable customers,
        @Qualifier("orders")
        PagedResourcesAssembler<OrderView> ordersAssembler,
        @Qualifier("customers")
        PagedResourcesAssembler<CustomerView> customersAssembler) {

    // Tạo riêng mô hình từ Page của từng tập dữ liệu.
}
```

`CustomerView` ở đây biểu thị DTO của danh sách khách hàng. Đoạn mã minh họa tham số; một handler thực tế cần mapping, truy vấn và kiểu phản hồi phù hợp.

Với quy ước qualifier mặc định, URI có thể chứa:

```http
GET /api/dashboard?orders_page=1&orders_size=20&customers_page=0&customers_size=5
```

Khi điều hướng danh sách orders, link phải cập nhật `orders_page` và giữ ngữ cảnh của danh sách customers theo hợp đồng dashboard.

Assembler cần gắn với tham số `Pageable` tương ứng để biết tên tham số có qualifier. Cơ chế tìm tham số cùng qualifier được thể hiện trong [PageableMethodParameterUtils](https://raw.githubusercontent.com/spring-projects/spring-data-commons/main/src/main/java/org/springframework/data/web/PageableMethodParameterUtils.java).

Đây là lý do không nên thay một assembler do hạ tầng giải quyết tham số bằng một instance tự tạo thiếu ngữ cảnh rồi mặc định các tên `orders_page`, `orders_size` vẫn được giữ đúng.

## 9. URI hiện tại sau reverse proxy

Giả sử client gọi:

```text
https://api.example.com/shop/api/orders
```

nhưng backend nhận request qua địa chỉ nội bộ:

```text
http://order-service:8080/api/orders
```

Nếu tạo link từ thông tin nội bộ chưa được hiệu chỉnh, phản hồi có thể chứa sai scheme, hostname, port hoặc thiếu tiền tố `/shop`. Client đi theo link có thể không truy cập được API công khai.

Spring có cơ chế xử lý thông tin forwarded qua filter hoặc hạ tầng server tương ứng. Các thành phần dựng URI dựa trên request cần nhìn thấy đúng thông tin sau bước xử lý đó. `ServletUriComponentsBuilder` không tự đọc tùy ý mọi forwarded header để thay thế cấu hình triển khai.

Cần thiết lập ranh giới tin cậy ở proxy: proxy biên loại bỏ hoặc thay thế forwarded header từ nguồn không tin cậy, rồi ứng dụng xử lý thông tin đã được hệ thống cho phép. Cơ chế và lý do được trình bày trong [Forwarded Headers của Spring Framework](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html#filters-forwarded-headers).

Khi kiểm tra link ở môi trường triển khai, phải kiểm tra từ phía client công khai. Một kết quả đúng khi gọi trực tiếp localhost chưa xác nhận đường đi qua gateway cũng đúng.

## 10. Relation phụ thuộc loại kết quả và trạng thái trang

### 10.1. Không tự phát sinh trang trước hoặc trang sau

Assembler dựa vào trạng thái như `hasPrevious()`, `hasNext()` của trang. Độ dài content bằng size không tự chứng minh còn dữ liệu phía sau.

Với cấu hình mặc định của `PagedResourcesAssembler`, first và last xuất hiện khi có khả năng điều hướng trước hoặc sau. Có thể dùng `setForceFirstAndLastRels(true)` nếu hợp đồng muốn luôn bổ sung hai relation đó; lựa chọn này không tạo thêm dữ liệu hay làm một trang không tồn tại trở thành hợp lệ.

Ở một tập kết quả chỉ có một trang, không nên coi việc thiếu next hoặc prev là lỗi serialize.

### 10.2. Slice không có tổng như Page

Khi chỉ có `Slice`, ứng dụng có thể biết còn phần tiếp theo mà không biết tổng số trang. Khi đó không nên dựng một link last bằng một tổng giả định.

Spring Data có `SlicedResourcesAssembler` cho kiểu kết quả tương ứng; xem [SlicedResourcesAssembler API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/web/SlicedResourcesAssembler.html). Việc chọn Page hay Slice cần phù hợp nhu cầu API và khả năng của store.

### 10.3. Link không tạo snapshot dữ liệu

Để điều hướng nhất quán, truy vấn cần thứ tự đủ rõ ràng, chẳng hạn `createdAt,desc` rồi `id,asc` để phân định những bản ghi có cùng ngày tạo.

Tuy nhiên, một link đúng không ngăn dữ liệu thay đổi giữa hai request. Bản ghi được thêm, xóa hoặc thay đổi khóa sort có thể làm phân trang offset dịch chuyển. Nếu nghiệp vụ cần mức nhất quán khác, cần thiết kế chiến lược truy vấn phù hợp; không giải quyết bằng cách chỉ thay phần biểu diễn link.

## 11. Client đi theo relation và những tình huống cần xác nhận

Với hợp đồng hypermedia, client có thể tìm relation next trong phản hồi và sử dụng href được cung cấp. Nếu next không tồn tại, giao diện có thể vô hiệu hóa thao tác sang trang sau.

Không lấy href rồi tự nối thêm một `page` khác, làm xuất hiện tham số trùng. Nếu phản hồi cung cấp URI template, client phải xử lý theo hợp đồng template thay vì gửi nguyên dấu ngoặc như một URI đã hoàn chỉnh.

Một số tình huống có giá trị để xác nhận trong ứng dụng:

| Tình huống | Điều cần quan sát |
| --- | --- |
| Trang đầu, trang giữa, trang cuối | Relation xuất hiện đúng trạng thái |
| Thêm bộ lọc status | Mọi link tiếp tục cùng tập kết quả |
| Nhiều tham số sort | Giữ đủ khóa và thứ tự ưu tiên |
| Giá trị có dấu cộng, khoảng trắng hoặc `&` | Request tiếp theo nhận lại đúng giá trị |
| Size bị giới hạn ở server | Metadata và link phù hợp kích thước thực tế |
| Đổi tên page/size/sort | Link dùng đúng tên mà resolver đọc |
| HTTP đánh số từ 1 | Không chuyển đổi chỉ số hai lần |
| Hai tập phân trang | Chỉ cập nhật tập tương ứng, giữ đúng qualifier |
| Chạy dưới context path hoặc gateway | Scheme, host, port và path công khai đúng |
| Tập rỗng hoặc chỉ có một trang | Không yêu cầu những relation không có ý nghĩa |
| URI nền hoặc self link tùy chỉnh | Giữ đủ bộ lọc và mô tả đúng trang hiện tại |

Một liên kết điều hướng đúng phải đưa client đến bước tiếp theo của cùng truy vấn. Kết quả đó đòi hỏi phối hợp giữa URI công khai, bộ lọc, resolver tham số và trạng thái trang mà repository thực sự trả về.

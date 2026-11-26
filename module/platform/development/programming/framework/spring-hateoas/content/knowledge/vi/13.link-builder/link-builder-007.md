# Query parameter

Query parameter là phần dữ liệu nằm sau dấu `?` trong URI. Trong REST API, chúng thường mô tả cách client muốn lọc, tìm kiếm, sắp xếp hoặc phân trang một collection. Khi tạo hypermedia link bằng Spring HATEOAS, các query parameter giúp server công bố một URI có đủ ngữ cảnh để client tiếp tục truy cập đúng tập kết quả.

Ví dụ, một cửa hàng có endpoint tìm sản phẩm:

```text
GET /api/products/search?q=keyboard&status=ACTIVE&page=0&size=20
```

Các giá trị `q`, `status`, `page` và `size` không phải các tài nguyên riêng. Chúng mô tả cách truy vấn collection sản phẩm. Nếu response chứa link `self` với cùng các tham số, client có thể tải lại đúng tập kết quả hiện tại. Nếu response có link `next`, server có thể giữ nguyên bộ lọc và sắp xếp, đồng thời thay `page` để client đi đến trang kế tiếp.

## Query parameter trong hợp đồng REST

Một URI thường có các phần:

```text
https://shop.example/api/products/search?q=keyboard&status=ACTIVE&page=0
\___________/ \____________________/ \________________________________/
   origin             path                         query
```

Path thường xác định tài nguyên hoặc endpoint; query mô tả cách chọn representation hoặc collection từ endpoint đó. Các query parameter thường dùng gồm:

| Mục đích | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Tìm kiếm | `q=keyboard` | Từ khóa tìm sản phẩm. |
| Lọc | `status=ACTIVE` | Chỉ lấy sản phẩm đang hoạt động. |
| Sắp xếp | `sort=price,asc` | Sắp xếp theo giá tăng dần. |
| Phân trang | `page=1&size=20` | Lấy trang thứ hai, tối đa 20 phần tử. |
| Chọn trường | `fields=id,name,price` | Yêu cầu một tập trường nếu API hỗ trợ projection. |

Query parameter là một phần của URI và thường ảnh hưởng đến kết quả GET, cache key và liên kết mà client có thể chia sẻ. Hãy định nghĩa tên, kiểu, giá trị mặc định và cách kết hợp của chúng thành hợp đồng rõ ràng. Ví dụ `page` bắt đầu từ 0 hay 1, `size` tối đa bao nhiêu, `sort` chấp nhận tên trường nào và nhiều giá trị filter được truyền theo dạng lặp hay phân tách bằng dấu phẩy đều cần thống nhất.

## Tạo link từ method controller

`WebMvcLinkBuilder` có thể đọc mapping của controller và các tham số được chú thích bằng Spring MVC. Khi method có `@RequestParam`, giá trị truyền qua `methodOn(...)` được đưa vào query string của link.

Giả sử controller khai báo endpoint tìm kiếm:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import java.util.List;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.MediaTypes;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/products")
class ProductController {

    private final ProductService service;
    private final ProductModelAssembler assembler;

    ProductController(ProductService service, ProductModelAssembler assembler) {
        this.service = service;
        this.assembler = assembler;
    }

    @GetMapping(value = "/search", produces = MediaTypes.HAL_JSON_VALUE)
    CollectionModel<ProductModel> search(
            @RequestParam("q") String query,
            @RequestParam("status") ProductStatus status,
            @RequestParam(name = "page", defaultValue = "0") int page,
            @RequestParam(name = "size", defaultValue = "20") int size) {
        List<ProductModel> products = service.search(query, status, page, size)
                .stream()
                .map(assembler::toModel)
                .toList();

        Link self = linkTo(methodOn(ProductController.class)
                .search(query, status, page, size))
                .withSelfRel();

        return CollectionModel.of(products, self);
    }
}
```

Trong ví dụ, các tham số được khai báo rõ bằng `@RequestParam`. Spring MVC đọc chúng từ query string khi nhận request. Khi tạo link đến method này, Spring HATEOAS dùng cùng mapping và tham số để dựng URI.

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.Link;

String query = "keyboard";
ProductStatus status = ProductStatus.ACTIVE;
int page = 0;
int size = 20;

Link searchLink = linkTo(methodOn(ProductController.class)
        .search(query, status, page, size))
        .withRel("search");
```

Link được tạo theo mapping của `ProductController.search(...)`, đồng thời chứa các giá trị query. Client có thể theo relation `search` để mở đúng tập kết quả mà server công bố. Cách làm này tránh tự ghép chuỗi như `"/api/products/search?q=" + query`, vốn dễ sai khi route thay đổi hoặc giá trị cần URL encoding.

Đối với link tự trỏ đến truy vấn hiện tại, dùng `withSelfRel()`:

```java
Link self = linkTo(methodOn(ProductController.class)
        .search(query, status, page, size))
        .withSelfRel();
```

`self` biểu thị representation collection đang được trả về với bộ lọc và trang hiện tại. `search` có thể biểu thị quan hệ đến endpoint tìm kiếm. Chọn relation theo ý nghĩa của link trong hợp đồng API; query parameter không quyết định relation.

## Gắn self và next link vào collection

Ví dụ đầy đủ hơn dùng kết quả phân trang từ service, tạo self link và next link. Giả sử service trả về một đối tượng `ProductPage` có `content`, `page`, `size` và `hasNext()`:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import java.util.List;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.Link;

CollectionModel<ProductModel> toCollectionModel(
        ProductPage result,
        String query,
        ProductStatus status,
        int page,
        int size) {

    List<ProductModel> products = result.content().stream()
            .map(assembler::toModel)
            .toList();

    Link self = linkTo(methodOn(ProductController.class)
            .search(query, status, page, size))
            .withSelfRel();

    CollectionModel<ProductModel> model = CollectionModel.of(products, self);

    if (result.hasNext()) {
        Link next = linkTo(methodOn(ProductController.class)
                .search(query, status, page + 1, size))
                .withRel("next");
        model.add(next);
    }

    return model;
}
```

Đoạn này minh họa logic assembler; `ProductPage` là kiểu kết quả do ứng dụng định nghĩa. Khi tạo link `next`, các bộ lọc `query` và `status`, cùng `size`, được giữ nguyên; chỉ `page` tăng lên. Client không cần tự xây URI cho trang kế tiếp hoặc tự đoán tham số cần giữ.

Nếu dùng Spring Data, có thể lấy `Page<Product>` và `Pageable` thay cho `ProductPage`. Spring HATEOAS còn có `PagedResourcesAssembler` để chuyển `Page` thành `PagedModel` và tạo các link điều hướng trang. Dù dùng cách nào, nguyên tắc vẫn là giữ các query filter và sort hiện hành khi tạo link trang mới.

## Tham số tùy chọn và giá trị mặc định

Nhiều endpoint có tham số tùy chọn. Ví dụ, `category` có thể không được truyền; `page` và `size` có giá trị mặc định. Controller nên thể hiện rõ hợp đồng:

```java
@GetMapping("/search")
CollectionModel<ProductModel> search(
        @RequestParam(name = "q", required = false) String query,
        @RequestParam(name = "category", required = false) String category,
        @RequestParam(name = "page", defaultValue = "0") int page,
        @RequestParam(name = "size", defaultValue = "20") int size) {
    // Tìm kiếm theo các tham số đã được chuẩn hóa.
}
```

Khi tạo link từ method, hãy dùng các giá trị thực sự thuộc ngữ cảnh response. Tham số không có giá trị không nên được biến thành chuỗi `"null"` hoặc một filter rỗng không có ý nghĩa. Quy tắc xử lý tham số thiếu phải thống nhất với controller và service: bỏ qua filter, áp dụng default, hoặc trả lỗi validation nếu tham số bắt buộc.

Nếu muốn công bố một link tìm kiếm mà client tự điền các tham số sau, hãy dùng URI template. Ví dụ:

```java
import org.springframework.hateoas.Link;

Link searchTemplate = Link.of(
        "/api/products/search{?q,category,page,size}",
        "search");
```

Biểu thức `{?q,category,page,size}` là query expansion theo URI Template. Khi serialize HAL, link có thể được đánh dấu `templated: true`, báo cho client biết URI còn các biến cần điền. Đây là cách khác với link đã có giá trị cụ thể: link cụ thể dùng khi server đã biết truy vấn; template dùng khi client cần cung cấp giá trị.

Không nên tự dựng template bằng cách nối chuỗi tùy ý nếu có nhiều biến hoặc quy tắc encoding phức tạp. Hãy dùng cú pháp URI Template đúng chuẩn và kiểm thử URI template mà response thực tế công bố.

## Encoding query parameter

Giá trị query có thể chứa khoảng trắng, dấu `&`, `+`, dấu tiếng Việt hoặc ký tự dành riêng của URI. Các ký tự này cần được encode đúng để không bị hiểu nhầm là dấu phân tách hay cú pháp URI.

Ví dụ, từ khóa:

```text
mechanical keyboard & mouse
```

cần được URL encode trước khi đặt vào query string. Dùng Spring HATEOAS link builder giúp Spring xử lý việc mở rộng URI theo cơ chế URI components. Khi tự dùng `UriComponentsBuilder`, hãy gọi `encode()` trước khi tạo URI:

```java
import java.net.URI;

import org.springframework.web.util.UriComponentsBuilder;

URI uri = UriComponentsBuilder.fromPath("/api/products/search")
        .queryParam("q", "mechanical keyboard & mouse")
        .queryParam("page", 0)
        .build()
        .encode()
        .toUri();
```

Ví dụ này hữu ích khi URI được dựng từ một base path đã biết. Trong code controller, ưu tiên tạo link từ mapping bằng `linkTo(methodOn(...))` để route không bị lặp lại ở nhiều nơi.

Không encode giá trị hai lần. Nếu giá trị đã chứa `%20` do được encode trước, rồi builder tiếp tục encode, dấu `%` có thể thành `%25` và client nhận dữ liệu sai. Cũng không nên tự nối chuỗi query bằng dấu `&`; dùng builder hoặc link API để mã hóa và phân tách tham số.

## Query parameter nhiều giá trị

Một filter có thể nhận nhiều giá trị, ví dụ nhiều tag hoặc trạng thái. API cần xác định rõ cách biểu diễn:

```text
?tag=sale&tag=new
```

hoặc:

```text
?tag=sale,new
```

Hai dạng trên không phải lúc nào cũng tương đương. Spring MVC có thể bind nhiều giá trị lặp vào `List<String>` hoặc mảng. Nếu API chọn dạng phân tách bằng dấu phẩy, cần quy định cách escape khi một giá trị tự chứa dấu phẩy. Khi tạo link, bảo đảm cách serialize phù hợp với cách controller bind và client đọc.

Không nên để client phải đoán cách truyền nhiều giá trị. Hãy ghi rõ dạng lặp hay dạng phân tách trong hợp đồng và kiểm thử với ít nhất hai giá trị.

## Bảo toàn filter và sort khi điều hướng

Khi server tạo link `next`, `prev` hoặc `first`, các tham số ảnh hưởng đến kết quả cần được giữ nguyên. Ví dụ truy vấn:

```text
/api/products/search?q=keyboard&status=ACTIVE&sort=price,asc&page=0&size=20
```

Link `next` nên giữ `q`, `status`, `sort`, `size` và chỉ đổi `page=1`. Nếu bỏ mất `sort` hoặc filter, client có thể nhận một tập kết quả khác khi đi tiếp.

Hãy chuẩn hóa tham số trước khi tạo link. Ví dụ, nếu API chấp nhận nhiều alias cho thứ tự sắp xếp, server có thể chuyển về một biểu diễn chuẩn trong response. Giữ nguyên ngữ nghĩa truy vấn quan trọng hơn việc sao chép mọi chuỗi đầu vào của client.

## Bảo mật và thiết kế query

Query string có thể xuất hiện trong browser history, access log, proxy log, analytics và header `Referer` tùy chính sách trình duyệt. Không đặt mật khẩu, access token, session secret hoặc dữ liệu nhạy cảm vào query parameter. Dùng cơ chế xác thực phù hợp như Authorization header hoặc cookie an toàn.

Query parameter phù hợp để mô tả cách đọc tài nguyên: filter, search, sort, page, projection. Không dùng query để thực hiện thay đổi trạng thái như xóa, thanh toán hoặc cập nhật dữ liệu. Các thao tác thay đổi nên dùng HTTP method và request body phù hợp, đồng thời được bảo vệ bằng xác thực, phân quyền và kiểm tra nghiệp vụ.

Giới hạn `size`, độ dài từ khóa, số lượng filter và các giá trị sort được phép. Không nhận tên cột tùy ý rồi ghép thẳng vào SQL. Hãy ánh xạ các trường sort được phép sang thuộc tính đã định nghĩa trong ứng dụng.

## Kiểm thử query parameter trong link

MockMvc có thể xác minh link trong HAL chứa các query parameter phù hợp với request hiện tại. Ví dụ:

```java
import static org.hamcrest.Matchers.containsString;
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
class ProductSearchLinkTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void selfLinkPreservesSearchParameters() throws Exception {
        mockMvc.perform(get("/api/products/search")
                        .param("q", "keyboard")
                        .param("status", "ACTIVE")
                        .param("page", "0")
                        .param("size", "20")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$._links.self.href")
                        .value(containsString("q=keyboard")))
                .andExpect(jsonPath("$._links.self.href")
                        .value(containsString("status=ACTIVE")))
                .andExpect(jsonPath("$._links.self.href")
                        .value(containsString("page=0")))
                .andExpect(jsonPath("$._links.self.href")
                        .value(containsString("size=20")));
    }
}
```

Test giả định endpoint trả HAL collection có self link được tạo từ các giá trị request. Nếu API chuẩn hóa giá trị trước khi tạo link, hãy kiểm tra URI chuẩn hóa mà server công bố. Với từ khóa có khoảng trắng hoặc ký tự đặc biệt, nên parse URI và kiểm tra giá trị query sau khi decode thay vì khóa test vào một cách encode cụ thể.

Các trường hợp nên có thêm test:

- Tham số tùy chọn bị bỏ qua không tạo ra filter giả như `category=null`.
- Giá trị có dấu cách, dấu `&`, dấu `+` hoặc ký tự Unicode được encode và decode đúng.
- Nhiều giá trị được biểu diễn theo đúng quy ước của API.
- Link `next` giữ filter và sort, chỉ thay số trang.
- Giá trị `size` vượt giới hạn được chuẩn hóa hoặc từ chối theo hợp đồng.
- URI template công bố đúng tên biến và được đánh dấu `templated`.

## Lỗi thường gặp

| Vấn đề | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Tự nối chuỗi query | Sai encoding, thiếu dấu phân tách hoặc lỗi khi giá trị có ký tự đặc biệt. | Dùng `linkTo(methodOn(...))` hoặc `UriComponentsBuilder`. |
| Bỏ filter khi tạo link trang tiếp theo | Kết quả ở trang sau không còn cùng truy vấn. | Giữ filter, sort và size khi tạo `next`/`prev`. |
| Truyền `null` thành chuỗi | Client nhận filter không hợp lệ như `status=null`. | Chuẩn hóa và bỏ tham số không có giá trị. |
| Không thống nhất nhiều giá trị | Client và server diễn giải query khác nhau. | Chọn dạng lặp hoặc phân tách và kiểm thử. |
| Encode hai lần | Server nhận giá trị khác với đầu vào. | Chỉ encode tại ranh giới tạo URI. |
| Đưa token vào query | Thông tin có thể xuất hiện trong log hoặc lịch sử trình duyệt. | Dùng header/cơ chế xác thực thích hợp. |

## Nguyên tắc thiết kế

- Dùng query parameter cho filter, search, sort, paging và các tùy chọn đọc tài nguyên.
- Khai báo `@RequestParam` tường minh để mapping và link builder hiểu đúng tên tham số.
- Tạo link bằng `linkTo(methodOn(...))` để query được dựng theo method controller.
- Dùng URI template khi client cần tự cung cấp giá trị query sau đó.
- Encode giá trị đúng một lần và kiểm thử cả dữ liệu đơn giản lẫn ký tự đặc biệt.
- Giữ filter/sort khi tạo link điều hướng trang.
- Không đặt bí mật hoặc thao tác thay đổi trạng thái trong query string.

Khi query parameter được mô hình hóa rõ ràng trong controller và link, response HATEOAS có thể dẫn client đến đúng tập kết quả mà không buộc client phải tự ghép URI. Server kiểm soát cách truy vấn được công bố, còn client dựa vào link và relation để tiếp tục điều hướng.

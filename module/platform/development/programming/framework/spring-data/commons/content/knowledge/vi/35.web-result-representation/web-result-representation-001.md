# Thiết kế JSON phân trang ổn định cho client

## Mục tiêu và phạm vi

Một API danh sách không chỉ trả các bản ghi. Client còn cần biết đang xem trang nào, kích thước trang được áp dụng và có bao nhiêu kết quả phù hợp. Những thông tin đó tạo thành một hợp đồng web mà frontend, ứng dụng di động hoặc hệ thống tích hợp có thể phụ thuộc lâu dài.

Bài học thuộc chương **Biểu diễn kết quả web** của module **SPRING_DATA_COMMONS**. Nội dung sử dụng các abstraction chung như `Page`, `Pageable`, `Slice` và projection/DTO để thiết kế response. Việc thực thi truy vấn, mapping và xác định tổng số bản ghi vẫn phụ thuộc module kho dữ liệu đang dùng.

Mục tiêu là:

1. Tách cấu trúc JSON công khai khỏi implementation phân trang bên trong.
2. Định nghĩa rõ ý nghĩa của các trường metadata.
3. Ánh xạ nội dung trang sang DTO mà vẫn giữ thông tin phân trang.
4. Chọn giữa DTO riêng, Spring Data `PagedModel` và biểu diễn hypermedia.
5. Giữ hợp đồng nhất quán khi kết quả rỗng, đầu vào bị giới hạn hoặc dữ liệu thay đổi.

Các ví dụ Java dùng cú pháp record của Java 17 trở lên. Chúng giả định ứng dụng đã có Spring MVC, JSON message converter phù hợp và Spring Data Web Support. Không cần chọn một store cụ thể để hiểu thiết kế response; một repository thực tế chỉ dùng được những khả năng mà module store của nó hỗ trợ.

## 1. Ổn định ở đây nghĩa là gì?

Giả sử frontend đang đọc:

~~~javascript
const rows = response.content;
const currentPage = response.page.number;
const totalRows = response.page.totalElements;
~~~

Một thay đổi backend có thể không làm hỏng việc gọi repository nhưng vẫn làm frontend lỗi, chẳng hạn:

- Chuyển `content` thành `items`.
- Đưa `number` từ bên trong `page` ra ngoài.
- Đổi số trang đầu từ 0 thành 1.
- Trả `null` thay vì mảng rỗng.
- Đổi `totalElements` từ số thành chuỗi mà không có kế hoạch tương thích.
- Đổi ý nghĩa của `size` từ kích thước trang sang số phần tử thực nhận.

Vì vậy, ổn định bao gồm cả **cấu trúc**, **kiểu dữ liệu** và **ngữ nghĩa**. Chỉ giữ nguyên tên trường là chưa đủ.

Một schema ổn định cũng không bảo đảm mỗi lần đọc đều thấy cùng dữ liệu. Ví dụ, sản phẩm có thể được thêm vào giữa hai request. Hợp đồng JSON và tính nhất quán của dữ liệu là hai yêu cầu cần thiết kế riêng.

Luồng trách nhiệm nên rõ ràng:

~~~mermaid
flowchart LR
    A["Tham số HTTP"] --> B["Pageable và chính sách truy vấn"]
    B --> C["Repository theo module store"]
    C --> D["Page của domain hoặc projection"]
    D --> E["Ánh xạ phần tử và metadata"]
    E --> F["DTO JSON công khai"]
    F --> G["Client"]
~~~

Đối tượng truyền giữa repository và service có thể thay đổi khi refactor. DTO ở biên HTTP giữ vai trò bảo vệ hợp đồng mà client đã được công bố.

## 2. Vì sao không dựa vào JSON trực tiếp của PageImpl?

Một controller có thể trả `Page<Product>` và để JSON converter serialize đối tượng nhận được. Tuy nhiên, kiểu chạy thực tế thường là `PageImpl`, một implementation của abstraction truy cập dữ liệu.

Khi serialize trực tiếp, response có thể chứa những chi tiết như `pageable` hoặc biểu diễn nội bộ của `sort`. Tập trường và cấu trúc đó có thể chịu ảnh hưởng bởi API của implementation và cấu hình serializer.

Spring Data khuyến cáo không dựa vào việc serialize trực tiếp `PageImpl` như một hợp đồng JSON ổn định. Một thay đổi API Java phục vụ mục đích nội bộ có thể làm thay đổi JSON mà client nhìn thấy. Xem [Spring Data Commons — Creating JSON representations for Page](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions-web.html#core.web.page).

Ví dụ về điều không nên biến thành sự phụ thuộc của client là một đường dẫn sâu kiểu:

~~~javascript
const sorted = response.pageable.sort.sorted;
~~~

Vấn đề không nằm ở tên biến `sorted`. Vấn đề là client đang phụ thuộc một cấu trúc vốn không được API chủ động thiết kế cho nó.

Những cách sau không tự tạo ra hợp đồng ổn định:

- Khai báo kiểu trả về là interface `Page` nhưng vẫn serialize cùng implementation.
- Tắt warning trong log.
- Chỉ chụp lại một response và coi đó là schema lâu dài.
- Thêm vài annotation để ẩn một số getter mà không quản lý toàn bộ schema.

Cách rõ ràng hơn là chọn một representation có chủ đích: DTO do ứng dụng định nghĩa, DTO phân trang được Spring Data cung cấp hoặc một media type hypermedia đã được thống nhất.

## 3. Thiết kế một hợp đồng JSON cụ thể

Trong phần triển khai chính, ta chọn hợp đồng sau:

~~~http
GET /products?q=keyboard&page=1&size=2&sort=id,asc
Accept: application/json
~~~

~~~json
{
  "content": [
    {
      "id": "p-103",
      "name": "Mechanical Keyboard"
    },
    {
      "id": "p-104",
      "name": "Compact Keyboard"
    }
  ],
  "page": {
    "number": 1,
    "size": 2,
    "numberOfElements": 2,
    "totalElements": 5,
    "totalPages": 3
  }
}
~~~

Đây là hợp đồng minh họa do ứng dụng tự chọn, không phải khẳng định về JSON mặc định của `PageImpl`.

### Ý nghĩa chính xác của từng trường

| Trường | Ý nghĩa trong hợp đồng này |
|---|---|
| `content` | Mảng DTO của trang hiện tại, luôn hiện diện và không null |
| `page.number` | Chỉ số trang hiện tại, bắt đầu từ 0 |
| `page.size` | Kích thước trang có hiệu lực sau khi áp dụng chính sách |
| `page.numberOfElements` | Số phần tử thực tế trong `content` |
| `page.totalElements` | Tổng số bản ghi phù hợp toàn bộ điều kiện truy vấn và quyền truy cập |
| `page.totalPages` | Tổng số trang theo tổng kết quả và kích thước trang có hiệu lực |

Với 5 kết quả, kích thước trang 2, có 3 trang mang chỉ số 0, 1 và 2. Trang cuối có thể chỉ có một phần tử nhưng `size` vẫn là 2.

Khi tổng là chính xác và kích thước trang dương, quan hệ mong muốn là:

~~~text
numberOfElements = content.length
0 <= numberOfElements <= size
totalPages = ceil(totalElements / size)
~~~

Trong hợp đồng này, nếu tổng kết quả bằng 0 thì `totalPages` bằng 0. Điều này không yêu cầu đổi trang được yêu cầu thành `null`.

Các accessor nguồn có thể đối chiếu trong API [Page](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Page.html). Cách đặt tên và lồng trường ở JSON vẫn là quyết định của API.

### Phản ánh giá trị có hiệu lực

Nếu client gửi `size=1000` nhưng backend áp dụng trần 100, response phải phản ánh kích thước có hiệu lực là 100 theo hợp đồng này.

Không sao chép thẳng chuỗi query ban đầu vào metadata rồi trả `size=1000` trong khi dữ liệu được chia theo 100. Client có thể tính sai số trang, offset và nút điều hướng.

Nếu HTTP đầu vào dùng số trang bắt đầu từ 1, cần chuyển đổi có chủ đích. Đừng để request theo một quy ước và response theo quy ước khác mà không giải thích.

## 4. DTO phân trang do ứng dụng kiểm soát

Một DTO riêng giúp chỉ công khai các trường mà API đã quyết định hỗ trợ.

### 4.1. Phần tử công khai

~~~java
import java.util.Objects;

public record ProductSummary(
    String id,
    String name
) {
    public ProductSummary {
        Objects.requireNonNull(id, "id is required");
        Objects.requireNonNull(name, "name is required");
    }
}
~~~

Ví dụ cố ý chỉ có ID và tên sản phẩm. ID là chuỗi theo hợp đồng, dù tầng lưu trữ có thể dùng một kiểu khác.

Không nhất thiết phải đưa nguyên entity ra response. Một entity có thể chứa quan hệ lazy, trường nội bộ hoặc thông tin mà client không cần. Envelope phân trang ổn định chỉ giải quyết một phần; schema của từng phần tử cũng cần được quản lý.

### 4.2. Envelope và metadata

~~~java
import java.util.List;
import java.util.Objects;

import org.springframework.data.domain.Page;

public record PageJson<T>(
    List<T> content,
    Metadata page
) {
    public PageJson {
        content = List.copyOf(
            Objects.requireNonNull(content, "content is required")
        );
        Objects.requireNonNull(page, "page metadata is required");
    }

    public static <T> PageJson<T> from(Page<T> source) {
        Objects.requireNonNull(source, "source page is required");

        if (source.getPageable().isUnpaged()) {
            throw new IllegalArgumentException(
                "This representation requires a paged result"
            );
        }

        Metadata metadata = new Metadata(
            source.getNumber(),
            source.getSize(),
            source.getNumberOfElements(),
            source.getTotalElements(),
            source.getTotalPages()
        );

        return new PageJson<>(
            source.getContent(),
            metadata
        );
    }

    public record Metadata(
        int number,
        int size,
        int numberOfElements,
        long totalElements,
        int totalPages
    ) {
    }
}
~~~

Các kiểu Java trong bài được hiểu là những đơn vị mã nguồn riêng trong cùng package ứng dụng khi thực hành.

Factory `from` đọc kết quả đã có từ `Page`. Nó không chạy truy vấn count mới và không cố tự đoán tổng dựa vào số dòng của trang hiện tại.

`List.copyOf` tạo bản sao danh sách không sửa được qua tham chiếu đó và từ chối phần tử null. Đây không phải deep copy của mọi object bên trong. Trong ví dụ, phần tử là record gồm các chuỗi nên mô hình dữ liệu đơn giản và rõ ràng.

Factory từ chối kết quả unpaged vì hợp đồng này yêu cầu kích thước trang dương và metadata phân trang có nghĩa. Nếu API cũng cần chế độ lấy toàn bộ, hãy thiết kế rõ representation và giới hạn của chế độ đó.

### 4.3. Ánh xạ domain trước, đóng gói sau

Nếu repository trả `Page<Product>`, một bước chuyển đổi có thể là:

~~~java
Page<ProductSummary> summaries = products.map(product ->
    new ProductSummary(
        product.getId().toString(),
        product.getName()
    )
);

PageJson<ProductSummary> response = PageJson.from(summaries);
~~~

Đoạn này giả định `products` là trang domain đã được truy vấn và `Product` có các accessor tương ứng. Dùng `Page.map` để chuyển từng phần tử trong khi giữ metadata phân trang.

Không lọc quyền truy cập bằng cách xóa một số phần tử khỏi `content` sau khi phân trang rồi giữ nguyên tổng. Điều đó có thể làm số lượng và ý nghĩa của response sai. Điều kiện quyền truy cập, tenant và tìm kiếm cần được áp dụng đúng trong quá trình truy vấn/count.

Chuyển entity thành DTO là phép ánh xạ. Loại bỏ bản ghi là thay đổi tập kết quả và cần một thiết kế truy vấn tương ứng.

## 5. Controller và ranh giới với repository

Để ví dụ không gắn cứng vào JPA hay MongoDB, ta định nghĩa một cổng truy vấn:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

public interface ProductCatalog {

    Page<ProductSummary> find(
        String query,
        Pageable pageable
    );
}
~~~

Implementation của `ProductCatalog` sử dụng repository hoặc template của module store phù hợp. Nó chịu trách nhiệm áp dụng điều kiện truy vấn, chính sách được phép và trả metadata kết quả đúng.

Controller tập trung vào representation:

~~~java
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PageableDefault;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProductController {

    private final ProductCatalog catalog;

    public ProductController(ProductCatalog catalog) {
        this.catalog = catalog;
    }

    @GetMapping(
        value = "/products",
        produces = "application/json"
    )
    public PageJson<ProductSummary> list(
        @RequestParam(name = "q", defaultValue = "")
        String query,

        @PageableDefault(size = 20, sort = "id")
        Pageable pageable
    ) {
        return PageJson.from(
            catalog.find(query, pageable)
        );
    }
}
~~~

Ví dụ cần một bean implementation của `ProductCatalog` để chạy trong ứng dụng thật. Controller không tự cung cấp database, mapping hoặc repository.

Annotation `@PageableDefault` chỉ quy định mặc định. Một endpoint thực tế vẫn cần giới hạn size, xác định những khóa sort được phép và xử lý các truy vấn tốn tài nguyên theo yêu cầu của ứng dụng.

Không lấy toàn bộ kết quả rồi dùng `subList` chỉ để tạo một JSON trông giống phân trang. Representation đúng hình dạng không chứng minh truy vấn đã được thực thi hiệu quả.

### Tổng phải thuộc cùng tập kết quả

Với `q=keyboard`, `totalElements` là tổng sản phẩm phù hợp điều kiện đó trong phạm vi dữ liệu mà người gọi được phép thấy.

Nó không phải:

- Tổng toàn bộ sản phẩm trong hệ thống.
- Số phần tử ở trang hiện tại.
- Số dòng của một câu join chưa xử lý đúng ngữ nghĩa entity.
- Một con số ước đoán nhưng được trình bày như tổng chính xác.

Khả năng tạo query, count hoặc projection được quyết định bởi từng module. Tham khảo phần [Defining Query Methods](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html) để giữ rõ ranh giới giữa hợp đồng Commons và truy vấn theo store.

## 6. Dùng PagedModel của Spring Data

Khi schema đơn giản của Spring Data đã phù hợp, có thể dùng `org.springframework.data.web.PagedModel`. Kiểu này được cung cấp từ Spring Data 3.3 để tạo biểu diễn JSON ổn định cho `Page`.

Một controller thay thế có thể trả:

~~~java
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PagedModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class StandardProductController {

    private final ProductCatalog catalog;

    public StandardProductController(ProductCatalog catalog) {
        this.catalog = catalog;
    }

    @GetMapping(
        value = "/standard/products",
        produces = "application/json"
    )
    public PagedModel<ProductSummary> list(
        @RequestParam(name = "q", defaultValue = "")
        String query,

        Pageable pageable
    ) {
        return new PagedModel<>(
            catalog.find(query, pageable)
        );
    }
}
~~~

Biểu diễn cơ bản gồm `content` và metadata trong `page`:

~~~json
{
  "content": [
    {
      "id": "p-103",
      "name": "Mechanical Keyboard"
    },
    {
      "id": "p-104",
      "name": "Compact Keyboard"
    }
  ],
  "page": {
    "size": 2,
    "totalElements": 5,
    "totalPages": 3,
    "number": 1
  }
}
~~~

Đây là một lựa chọn khác với DTO `PageJson` của bài: phần metadata tiêu chuẩn không có trường `numberOfElements` do ta tự thêm.

Kiểu này không tự thêm link điều hướng và không yêu cầu đưa Spring HATEOAS vào chỉ để có envelope cơ bản. Xem [Spring Data PagedModel](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/web/PagedModel.html).

Việc chọn envelope có sẵn không thay thế lựa chọn kiểu phần tử. `PagedModel<ProductEntity>` vẫn có thể công khai schema entity; `PagedModel<ProductSummary>` giữ phần tử theo DTO đã thiết kế.

## 7. Chế độ VIA_DTO cho serialization

Khi muốn các `PageImpl` được render thông qua representation của Spring Data, có thể cấu hình:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.web.config.EnableSpringDataWebSupport;

import static org.springframework.data.web.config.EnableSpringDataWebSupport.PageSerializationMode.VIA_DTO;

@Configuration
@EnableSpringDataWebSupport(
    pageSerializationMode = VIA_DTO
)
public class PageRepresentationConfiguration {
}
~~~

Chế độ `VIA_DTO` khiến `PageImpl` được bọc thành `PagedModel` trước khi render JSON. Nó khác với `DIRECT`, là chế độ render implementation trực tiếp.

Điều cần phân biệt:

| Lựa chọn | Kiểu Java ở controller | Ai định nghĩa envelope? |
|---|---|---|
| DTO `PageJson` của ứng dụng | `PageJson<ProductSummary>` | Ứng dụng |
| Bọc tường minh bằng Spring Data `PagedModel` | `PagedModel<ProductSummary>` | Spring Data |
| Bật `VIA_DTO` | Có thể tiếp tục trả `Page<ProductSummary>` | Cơ chế render được cấu hình |
| Render trực tiếp `PageImpl` | `Page<ProductSummary>` hoặc implementation | Gắn với serialization của implementation |

Xem mô tả chính thức của [PageSerializationMode](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/web/config/EnableSpringDataWebSupport.PageSerializationMode.html).

Thay đổi cấu hình toàn cục có thể đổi JSON của nhiều endpoint cùng lúc. Với API đã có client đang sử dụng, phải xem đây là một thay đổi hợp đồng cần đánh giá và triển khai có kế hoạch.

Các snippet dùng annotation giả định cấu hình web tương ứng của Spring Data được áp dụng trong ứng dụng. Nếu ObjectMapper hoặc JSON converter được tự cấu hình riêng, cần kiểm tra response HTTP thực tế thay vì chỉ nhìn sự tồn tại của annotation.


## 8. Khi cần hypermedia và link điều hướng

Spring HATEOAS có một kiểu cũng tên `PagedModel`, nhưng ở package khác:

- `org.springframework.data.web.PagedModel`: representation cơ bản của Spring Data.
- `org.springframework.hateoas.PagedModel`: representation model phục vụ hypermedia.

Không hoán đổi hai import này chỉ vì tên lớp giống nhau.

Khi ứng dụng dùng Spring HATEOAS, `PagedResourcesAssembler` giúp chuyển `Page` thành model với metadata và link phân trang. Ví dụ phương thức đặt trong controller đã có dependency `catalog`:

~~~java
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.PagedModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

@GetMapping("/linked/products")
public PagedModel<EntityModel<ProductSummary>> linked(
    @RequestParam(name = "q", defaultValue = "")
    String query,

    Pageable pageable,
    PagedResourcesAssembler<ProductSummary> assembler
) {
    return assembler.toModel(
        catalog.find(query, pageable)
    );
}
~~~

Ví dụ cần hạ tầng tích hợp Spring HATEOAS. JSON cuối cùng còn phụ thuộc media type và cấu hình representation; với HAL, client làm việc với các khái niệm như `_embedded` và `_links`.

Không mô tả endpoint HAL bằng schema `content/page` của DTO riêng rồi kỳ vọng chúng giống nhau. Các tên relation, kiểu phần tử và trường hợp collection rỗng cũng cần được thống nhất.

Hợp đồng assembler nằm trong [PagedResourcesAssembler](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/web/PagedResourcesAssembler.html); media type được giải thích trong [Spring HATEOAS Reference](https://docs.spring.io/spring-hateoas/docs/current/reference/html/).

Nếu API tự thêm link thay vì dùng assembler, link phải giữ các điều kiện tìm kiếm, sort và kích thước trang có hiệu lực. Đừng tạo `next` bằng cách ghép chuỗi số trang rồi làm mất `q` hoặc các tham số sort lặp.

Khi chạy sau reverse proxy, địa chỉ công khai của link cũng cần được cấu hình đúng. Việc này thuộc triển khai hạ tầng HTTP, không được giải quyết chỉ bằng envelope JSON.

## 9. Quy ước cho trang rỗng và trang vượt phạm vi

### 9.1. Không có kết quả phù hợp

Với hợp đồng `PageJson` trong bài, request hợp lệ nhưng không tìm thấy sản phẩm trả `200 OK` cùng body:

~~~json
{
  "content": [],
  "page": {
    "number": 0,
    "size": 20,
    "numberOfElements": 0,
    "totalElements": 0,
    "totalPages": 0
  }
}
~~~

`content` vẫn là mảng. Metadata vẫn hiện diện. Client dùng cùng đường dẫn dữ liệu cho cả trạng thái có và không có kết quả.

Trong hợp đồng có body phân trang này, không chuyển tùy hứng sang `204 No Content` khi rỗng. Làm như vậy buộc client có thêm nhánh xử lý mất toàn bộ metadata.

### 9.2. Trang cuối chưa đủ kích thước

Với 5 kết quả và kích thước 2, trang cuối có thể là:

~~~json
{
  "content": [
    {
      "id": "p-105",
      "name": "Wireless Keyboard"
    }
  ],
  "page": {
    "number": 2,
    "size": 2,
    "numberOfElements": 1,
    "totalElements": 5,
    "totalPages": 3
  }
}
~~~

Không đặt `size=1` chỉ vì trang này có một phần tử. Nếu size thay đổi theo số phần tử nhận được, client không còn cùng cơ sở để tính toán các trang.

### 9.3. Chỉ số trang nằm ngoài phạm vi hiện tại

API cần chọn một chính sách rõ ràng. Trong ví dụ này, trang vượt phạm vi nhưng request hợp lệ trả `200 OK` với nội dung rỗng, giữ chỉ số được yêu cầu và tổng phù hợp:

~~~json
{
  "content": [],
  "page": {
    "number": 8,
    "size": 2,
    "numberOfElements": 0,
    "totalElements": 5,
    "totalPages": 3
  }
}
~~~

Trong trường hợp này, `number` có thể lớn hơn hoặc bằng `totalPages`. Vì vậy, không áp dụng bất biến “number luôn nhỏ hơn totalPages” cho mọi response.

Đây là chính sách của ví dụ, không phải yêu cầu bắt buộc cho mọi API. Một API khác có thể từ chối request vượt phạm vi nếu hợp đồng quy định vậy. Điều cần tránh là âm thầm chuyển đến trang cuối nhưng vẫn báo số trang cũ.

Chính sách vượt phạm vi cũng cần xét dữ liệu thay đổi giữa các request. Một trang từng tồn tại có thể trở thành rỗng sau khi các bản ghi bị xóa.

## 10. Khi không có tổng: dùng hợp đồng phù hợp

`Page` cung cấp tổng số phần tử và số trang. `Slice` tập trung vào nội dung phần hiện tại và thông tin còn phần tiếp theo hay không.

Nếu chỉ có `Slice`, không điền `totalElements=0` hoặc `totalPages=0` để lấp trường. Con số 0 nói rằng không có kết quả, khác với “chưa biết tổng”.

Một representation riêng cho slice có thể là:

~~~json
{
  "content": [
    {
      "id": "p-103",
      "name": "Mechanical Keyboard"
    },
    {
      "id": "p-104",
      "name": "Compact Keyboard"
    }
  ],
  "slice": {
    "number": 1,
    "size": 2,
    "numberOfElements": 2,
    "hasNext": true
  }
}
~~~

Đây là schema minh họa cho một API slice, không phải JSON mặc định của `SliceImpl`. Để tạo nó, cần DTO tương ứng và nguồn thông tin `hasNext` đúng.

Đặc biệt, một trang có đủ `size` phần tử chưa chứng minh còn phần tử kế tiếp. Nguồn truy vấn phải xác định được điều đó, chẳng hạn thông qua cơ chế lấy thêm một phần tử khi module hỗ trợ.

Xem [Slice](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Slice.html) để hiểu hợp đồng dữ liệu nguồn.

| Nhu cầu client | Hợp đồng nên cân nhắc |
|---|---|
| Hiển thị tổng và chuyển đến trang cụ thể | Page với tổng được xác định |
| Chỉ có nút “xem thêm” | Slice với `hasNext` |
| Duyệt theo vị trí tiếp nối | Cursor/window theo khả năng của store |
| Xuất dữ liệu lớn | API hoặc tác vụ xuất có vòng đời riêng |

Cursor là một hợp đồng khác với chỉ số trang offset. Nếu thay cách phân trang, phải đánh giá cách client điều hướng, lưu trạng thái và tiếp tục đọc; không chỉ đổi tên một trường trong response.

### Không tạo tổng từ danh sách của một trang

Mẫu sau dễ sai nếu `items` chỉ là nội dung của một trang:

~~~java
new PageImpl<>(items, pageable, items.size());
~~~

Độ dài trang hiện tại không phải tổng toàn bộ tập kết quả. Một constructor không thể suy ra các bản ghi chưa đọc.

`PageImpl` cũng có cơ chế thích nghi tổng trong một số tình huống của trang cuối. Không dùng cơ chế đó như cách sửa một tổng do ứng dụng bịa ra. Xem hợp đồng constructor trong [PageImpl](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/PageImpl.html).

## 11. JSON ổn định không tự tạo snapshot dữ liệu

Giả sử backend thực hiện một thao tác đọc nội dung và một thao tác xác định tổng. Nếu dữ liệu thay đổi giữa các thao tác, nội dung và tổng có thể phản ánh những thời điểm khác nhau tùy transaction, isolation và khả năng của store.

Không mặc định việc trả `Page` bảo đảm snapshot nhất quán hoặc luôn thực hiện đúng hai câu truy vấn. Implementation có thể tối ưu hoặc cần thêm công việc theo loại truy vấn.

Một thiết kế hợp lý cần trả lời:

- Tổng là chính xác tại thời điểm nào, hay là ước lượng?
- Việc đọc nội dung và đếm có cùng điều kiện lọc và phạm vi quyền truy cập?
- Có yêu cầu snapshot xuyên suốt nhiều lần chuyển trang không?
- Có thể chấp nhận một kết quả vừa bị xóa khi người dùng chuyển trang không?

Nếu tổng là ước lượng, hãy thể hiện điều đó bằng hợp đồng riêng, chẳng hạn một trường hoặc kiểu metadata được định nghĩa rõ. Đừng giữ cùng tên và lời hứa “tổng chính xác” rồi âm thầm thay nghĩa.

### Thứ tự xác định vẫn cần thiết

Với offset pagination, sắp xếp theo một thuộc tính có nhiều giá trị bằng nhau có thể chưa tạo thứ tự xác định. Có thể cần thêm khóa phân xử duy nhất, chẳng hạn `name ASC, id ASC`.

Tuy nhiên, khóa phân xử không ngăn dữ liệu dịch chuyển khi một bản ghi mới được thêm vào trước offset hiện tại. Đó là giới hạn cần đánh giá khi chọn offset, cursor hoặc cơ chế snapshot.

Việc lựa chọn query, count, chỉ mục và transaction thuộc module store và yêu cầu nghiệp vụ. DTO chỉ biểu diễn kết quả mà tầng đó đã cung cấp.

## 12. Quản lý kiểu dữ liệu và lỗi HTTP

### 12.1. Kiểu JSON là một phần của hợp đồng

Một số quyết định nên được công bố rõ:

| Vấn đề | Quyết định trong ví dụ |
|---|---|
| ID sản phẩm | Chuỗi |
| Số trang | Số nguyên bắt đầu từ 0 |
| Kích thước và số phần tử | Số nguyên không âm; size dương |
| Tổng số bản ghi | Số nguyên, được Java biểu diễn bằng `long` |
| Trang không có phần tử | `content: []` |
| Trường metadata | Hiện diện với ý nghĩa đã định nghĩa |

Java `long` không có nghĩa mọi client JavaScript có thể biểu diễn chính xác toàn bộ miền giá trị đó bằng `Number`. Nếu tổng hoặc ID có thể vượt giới hạn số nguyên chính xác của client, cần thống nhất phạm vi hoặc biểu diễn chuỗi ngay từ hợp đồng.

Trong ví dụ, ID đã được chọn là chuỗi. Với `totalElements`, hệ thống phải đánh giá miền giá trị thực tế và yêu cầu của client. Đổi một trường đã công bố từ số sang chuỗi về sau là thay đổi cần xử lý tương thích.

Không dùng thứ tự các thuộc tính trong object JSON làm hợp đồng. Thứ tự phần tử trong `content` lại có ý nghĩa vì đó là kết quả đã sắp xếp. Các nguyên tắc về object, array và khả năng tương tác số được nêu trong [RFC 8259](https://www.rfc-editor.org/rfc/rfc8259.html).

### 12.2. Không biểu diễn lỗi như trang rỗng thành công

Nếu database lỗi hoặc người gọi không được phép truy cập, không bắt mọi exception rồi trả:

~~~json
{
  "content": [],
  "page": {
    "number": 0,
    "size": 20,
    "numberOfElements": 0,
    "totalElements": 0,
    "totalPages": 0
  }
}
~~~

JSON đó tuy hợp lệ về cấu trúc nhưng truyền sai ý nghĩa: client sẽ tưởng truy vấn thành công và không có dữ liệu.

Đầu vào sai, thiếu quyền và lỗi hệ thống cần có status cùng representation lỗi phù hợp. Có thể dùng Problem Details để giữ hợp đồng lỗi riêng, chẳng hạn:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json
~~~

~~~json
{
  "type": "about:blank",
  "title": "Bad Request",
  "status": 400,
  "detail": "Unsupported sort property"
}
~~~

Đây là một ví dụ thiết kế lỗi; resolver mặc định có thể chuẩn hóa một số đầu vào phân trang thay vì tự động trả 400. Ứng dụng cần thực hiện chính sách validation mà API đã công bố.

Cấu trúc Problem Details được định nghĩa trong [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457.html).

## 13. Mô tả schema cho client

OpenAPI giúp công bố tên trường, kiểu và trường bắt buộc. Đoạn dưới là phần `components.schemas` minh họa cho DTO riêng của bài, không phải một tài liệu OpenAPI đầy đủ:

~~~yaml
components:
  schemas:
    ProductSummary:
      type: object
      required:
        - id
        - name
      properties:
        id:
          type: string
        name:
          type: string

    PageMetadata:
      type: object
      required:
        - number
        - size
        - numberOfElements
        - totalElements
        - totalPages
      properties:
        number:
          type: integer
          format: int32
          minimum: 0
          description: Chỉ số trang bắt đầu từ 0.
        size:
          type: integer
          format: int32
          minimum: 1
          description: Kích thước trang có hiệu lực.
        numberOfElements:
          type: integer
          format: int32
          minimum: 0
          description: Số phần tử của content trong response này.
        totalElements:
          type: integer
          format: int64
          minimum: 0
          description: Tổng kết quả phù hợp toàn bộ điều kiện truy vấn.
        totalPages:
          type: integer
          format: int32
          minimum: 0
          description: Bằng 0 khi không có kết quả phù hợp.

    ProductPage:
      type: object
      required:
        - content
        - page
      properties:
        content:
          type: array
          items:
            $ref: '#/components/schemas/ProductSummary'
        page:
          $ref: '#/components/schemas/PageMetadata'
~~~

Schema chưa thể tự diễn đạt hoặc tự kiểm tra mọi quan hệ nghiệp vụ chỉ bằng các ràng buộc đơn giản ở trên. Cần bổ sung ví dụ và kiểm thử cho các quan hệ như `numberOfElements = content.length`.

Hãy mô tả thêm chính sách trang vượt phạm vi, giới hạn size, các khóa sort và miền giá trị số mà client cần hỗ trợ. Chỉ có `format: int64` chưa giải quyết mọi khác biệt giữa các ngôn ngữ client.

Một tài liệu được sinh tự động từ kiểu Java cần được kiểm tra ở dạng JSON thực tế. Chẳng hạn, cấu hình `VIA_DTO` có thể ảnh hưởng cách serialize runtime; đừng mặc định mọi công cụ mô tả schema đã hiểu đúng cấu hình đó.

Quy tắc schema và response được trình bày trong [OpenAPI Specification 3.1.1](https://spec.openapis.org/oas/v3.1.1.html).

## 14. Kiểm thử hợp đồng ở biên HTTP

Một phép so sánh các record Java không chứng minh JSON đúng. Kiểm thử cần đi qua message converter và xác nhận những trường mà client thực sự nhận.

Ví dụ dưới dùng `ProductController`, `ProductCatalog` và các DTO ở phần trước. Catalog giả chỉ tạo fixture để kiểm tra representation; nó không mô phỏng đầy đủ repository hoặc thuật toán lọc dữ liệu.

~~~java
import java.util.List;

import org.junit.jupiter.api.Test;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.web.PageableHandlerMethodArgumentResolver;
import org.springframework.data.web.SortHandlerMethodArgumentResolver;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.aMapWithSize;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.setup.MockMvcBuilders.standaloneSetup;

class ProductPageJsonTest {

    private MockMvc web(ProductCatalog catalog) {
        SortHandlerMethodArgumentResolver sortResolver =
            new SortHandlerMethodArgumentResolver();

        PageableHandlerMethodArgumentResolver pageableResolver =
            new PageableHandlerMethodArgumentResolver(sortResolver);

        return standaloneSetup(new ProductController(catalog))
            .setCustomArgumentResolvers(pageableResolver, sortResolver)
            .build();
    }

    @Test
    void rendersThePublicEnvelope() throws Exception {
        MockMvc mvc = web((query, pageable) ->
            new PageImpl<>(
                List.of(
                    new ProductSummary("p-103", "Mechanical Keyboard"),
                    new ProductSummary("p-104", "Compact Keyboard")
                ),
                pageable,
                5
            )
        );

        mvc.perform(get("/products")
                .param("q", "keyboard")
                .param("page", "1")
                .param("size", "2"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", aMapWithSize(2)))
            .andExpect(jsonPath("$.content").isArray())
            .andExpect(jsonPath("$.content.length()").value(2))
            .andExpect(jsonPath("$.content[0].id").value("p-103"))
            .andExpect(jsonPath("$.page", aMapWithSize(5)))
            .andExpect(jsonPath("$.page.number").value(1))
            .andExpect(jsonPath("$.page.size").value(2))
            .andExpect(jsonPath("$.page.numberOfElements").value(2))
            .andExpect(jsonPath("$.page.totalElements").value(5))
            .andExpect(jsonPath("$.page.totalPages").value(3))
            .andExpect(jsonPath("$.pageable").doesNotExist())
            .andExpect(jsonPath("$.sort").doesNotExist());
    }

    @Test
    void keepsTheEnvelopeWhenEmpty() throws Exception {
        MockMvc mvc = web((query, pageable) ->
            Page.<ProductSummary>empty(pageable)
        );

        mvc.perform(get("/products")
                .param("page", "0")
                .param("size", "2"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.content").isArray())
            .andExpect(jsonPath("$.content.length()").value(0))
            .andExpect(jsonPath("$.page.number").value(0))
            .andExpect(jsonPath("$.page.size").value(2))
            .andExpect(jsonPath("$.page.numberOfElements").value(0))
            .andExpect(jsonPath("$.page.totalElements").value(0))
            .andExpect(jsonPath("$.page.totalPages").value(0));
    }

    @Test
    void preservesAnOutOfRangePageNumber() throws Exception {
        MockMvc mvc = web((query, pageable) ->
            new PageImpl<ProductSummary>(
                List.of(),
                pageable,
                5
            )
        );

        mvc.perform(get("/products")
                .param("page", "8")
                .param("size", "2"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.content.length()").value(0))
            .andExpect(jsonPath("$.page.number").value(8))
            .andExpect(jsonPath("$.page.totalElements").value(5))
            .andExpect(jsonPath("$.page.totalPages").value(3));
    }
}
~~~

Ví dụ cần JUnit, spring-test, thư viện JSONPath/Hamcrest tương ứng và JSON converter có khả năng serialize các record. Đây là mã thực hành để kiểm tra hợp đồng, không phải kết quả kiểm thử đã chạy trên ứng dụng của bạn.

Kiểm tra số trường ở object giúp phát hiện việc vô tình công khai thêm chi tiết. Khi chủ động thêm một trường công khai, cập nhật schema và kiểm thử cùng thay đổi đó.

Không so sánh chuỗi JSON theo thứ tự thuộc tính. Cần tập trung vào tên trường, kiểu, giá trị, sự hiện diện và các phần tử có thứ tự trong mảng.

Nếu dùng `VIA_DTO` hoặc Spring HATEOAS, bổ sung kiểm thử với application context và converter thực tế. Standalone setup của DTO riêng chưa xác minh cấu hình serialization toàn cục.

## 15. Thay đổi hợp đồng và nâng cấp thư viện

Một lớp representation rõ ràng giúp việc nâng cấp Spring Data ít ảnh hưởng đến client hơn, nhưng vẫn cần kiểm tra những gì đi qua biên HTTP.

| Thay đổi | Điều cần đánh giá |
|---|---|
| Đổi implementation repository | Schema và ý nghĩa tổng có được giữ không? |
| Đổi entity/projection | DTO phần tử có giữ đúng hợp đồng không? |
| Nâng cấp Spring Data hoặc JSON converter | Cấu trúc và kiểu JSON có đổi không? |
| Bật `VIA_DTO` | Các endpoint trả PageImpl cũ có đổi envelope không? |
| Chuyển từ Page sang Slice | Client đang cần tổng có được đáp ứng không? |
| Chuyển từ offset sang cursor | Luồng điều hướng và lưu trạng thái của client thay đổi thế nào? |
| Thay giới hạn size | Client có đọc kích thước có hiệu lực không? |
| Đổi chỉ số trang từ 0 sang 1 | Request, response và link đã thay nhất quán chưa? |

Thêm một trường tùy chọn có thể tương thích với client cho phép bỏ qua trường chưa biết. Tuy nhiên, không nên mặc định mọi client hoặc SDK đều có khả năng đó. Cần công bố chính sách tương thích và kiểm tra những client đang hỗ trợ.

Đổi tên trường, đổi kiểu hoặc đổi nghĩa thường cần một kế hoạch chuyển tiếp rõ hơn. Có thể dùng phiên bản endpoint, media type hoặc một giai đoạn hỗ trợ song song theo quy ước của hệ thống.

Nếu API cũ đã công khai JSON trực tiếp của `PageImpl`, việc chuyển sang DTO là cải thiện thiết kế nhưng vẫn có thể là breaking change với client đang đọc cấu trúc cũ. Một lộ trình khả thi là định nghĩa schema mới, kiểm tra consumer, cung cấp giai đoạn chuyển tiếp rồi mới loại bỏ dạng cũ.

Không coi sự biến mất của warning log là tiêu chí hoàn tất. Tiêu chí là client nhận được hợp đồng đã được thống nhất và các trường hợp biên vẫn đúng nghĩa.

## 16. Bài thực hành và câu hỏi tự kiểm tra

Thực hành với một endpoint danh sách của module store được hỗ trợ:

1. Chụp lại hợp đồng mà client cần: tên trường, kiểu và quy ước đánh số trang.
2. Tạo DTO cho phần tử và envelope phân trang, không trả trực tiếp entity theo thói quen.
3. Dùng `Page.map` để ánh xạ nội dung, sau đó đóng gói metadata.
4. Tạo fixture cho trang giữa, trang cuối thiếu phần tử và tập kết quả rỗng.
5. Quyết định chính sách trang vượt phạm vi và kiểm tra response đúng quyết định đó.
6. So sánh DTO riêng với `org.springframework.data.web.PagedModel`.
7. Kiểm thử response qua HTTP khi thay cấu hình serialization.
8. Xác minh query nội dung và tổng cùng áp dụng điều kiện lọc, tenant và quyền truy cập.
9. Đánh giá client có thật sự cần tổng hay chỉ cần khả năng đọc tiếp.
10. Mô tả schema và chính sách tương thích trước khi đổi envelope đã có người dùng.

Những câu hỏi cần trả lời được:

- Vì sao kích thước trang cuối khác số phần tử thực nhận?
- Vì sao `content: []` không đồng nghĩa tổng chưa biết?
- Vì sao `Page<ProductSummary>` chưa tự bảo đảm envelope JSON ổn định?
- Khi nào nên dùng DTO riêng và khi nào model có sẵn là đủ?
- Vì sao một count đúng tổng toàn hệ thống vẫn có thể sai với người gọi hiện tại?
- Vì sao JSON đúng schema vẫn có thể chứa dữ liệu phân trang thiếu nhất quán?
- Một thay đổi cấu hình toàn cục có thể tác động đến những endpoint nào?

Kết quả mong muốn là một hợp đồng mà client hiểu được mà không cần biết backend đang dùng `PageImpl`, repository implementation hay module store nào. **Schema công khai được thiết kế ở biên web; Commons cung cấp abstraction; tầng dữ liệu cung cấp kết quả và metadata đúng khả năng của store.**

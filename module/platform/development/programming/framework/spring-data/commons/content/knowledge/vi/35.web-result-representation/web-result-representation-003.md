# org.springframework.data.web.PagedModel

`org.springframework.data.web.PagedModel<T>` là kiểu biểu diễn một trang dữ liệu ở tầng web của Spring Data Commons. Nó bọc một `Page<T>` để tạo JSON có phần nội dung và metadata phân trang rõ ràng, thay vì để client phụ thuộc trực tiếp vào cách serialize implementation `PageImpl`.

Bài học thuộc chương **Biểu diễn kết quả web** của module **SPRING_DATA_COMMONS**. Trọng tâm là cách chuyển kết quả repository thành hợp đồng phản hồi HTTP, giữ đúng ý nghĩa của phân trang, projection và metadata mà không gán thêm khả năng truy vấn cho store.

## 1. Vì sao cần một kiểu biểu diễn riêng?

Một repository có thể trả:

```java
Page<ProductView> page = queries.findProducts(pageable);
```

`Page` là abstraction hữu ích trong Java: chứa dữ liệu trang hiện tại, thông tin vị trí và tổng số phần tử. Nhưng một HTTP response cần một cấu trúc mà client có thể dựa vào lâu dài.

Nếu trả một `PageImpl` trực tiếp để serializer khám phá các getter, JSON có thể gắn với API của lớp implementation. Những thay đổi phục vụ nội bộ thư viện có thể ảnh hưởng hình dạng phản hồi dù nghiệp vụ của endpoint không đổi.

`PagedModel` tạo một lớp biểu diễn riêng cho công việc này. Lớp có từ Spring Data Commons **3.3**, nhận một `Page` qua constructor và không bắt buộc phải thêm Spring HATEOAS chỉ để dùng kiểu bọc đơn giản này. Xem [PagedModel API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/web/PagedModel.html).

Luồng trách nhiệm có thể diễn tả như sau:

```text
Store thực thi truy vấn
        |
        v
Page<Entity> hoặc Page<Projection>
        |
        v
Page<DTO> dùng cho API
        |
        v
org.springframework.data.web.PagedModel<DTO>
        |
        v
JSON response
```

Không phải endpoint nào cũng cần bước entity sang DTO: repository có thể đã trả projection hoặc kiểu dữ liệu phù hợp. Điều quan trọng là chọn nội dung công khai trước khi tạo biểu diễn web.

## 2. Cấu trúc JSON: content và page

Với cấu hình JSON thông thường, phản hồi có dạng:

```json
{
  "content": [
    {"id": 103, "name": "Bàn làm việc"},
    {"id": 104, "name": "Đèn bàn"}
  ],
  "page": {
    "size": 2,
    "number": 1,
    "totalElements": 5,
    "totalPages": 3
  }
}
```

Ý nghĩa trong ví dụ:

| Trường | Diễn giải |
| --- | --- |
| `content` | Hai sản phẩm của trang đang được trả về |
| `page.size` | Kích thước trang là 2 |
| `page.number` | Chỉ số trang là 1, tức trang thứ hai nếu đánh số từ 0 |
| `page.totalElements` | Có tổng cộng 5 sản phẩm trong tập kết quả |
| `page.totalPages` | Có 3 trang với kích thước trang hiện tại |

Đây là tập kết quả sau điều kiện lọc của truy vấn, không nhất thiết là toàn bộ sản phẩm trong database.

Thứ tự các property trong một JSON object không phải ý nghĩa nghiệp vụ. Client nên đọc theo tên trường, không dựa vào việc `number` xuất hiện trước hay sau `totalPages`.

### 2.1. Tên getter Java khác tên trường JSON

Trong Java:

```java
List<ProductView> products = body.getContent();

PagedModel.PageMetadata metadata = body.getMetadata();
long number = metadata.number();
long total = metadata.totalElements();
```

Trong JSON, metadata nằm dưới key **`page`**, không phải `metadata`. Việc ánh xạ tên này được khai báo trên kiểu biểu diễn; xem [mã nguồn PagedModel](https://raw.githubusercontent.com/spring-projects/spring-data-commons/main/src/main/java/org/springframework/data/web/PagedModel.java).

`PageMetadata` là record có các thành phần `size`, `number`, `totalElements`, `totalPages`, đều có kiểu `long`. Vì là record, truy cập bằng `metadata.number()`, không phải tự suy ra một phương thức `metadata.getNumber()`. Xem [PageMetadata API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/web/PagedModel.PageMetadata.html).

### 2.2. Không mặc định có tất cả property của PageImpl

Biểu diễn đơn giản này không tự xuất toàn bộ các trường như:

```text
pageable
sort
first
last
numberOfElements
_links
```

Nếu client cũ đang đọc `pageable.pageNumber` hoặc `first`, chuyển sang `PagedModel` là thay đổi hợp đồng phản hồi cần được xử lý. Không chỉ đổi kiểu trả về Java rồi mặc định frontend vẫn đọc được cấu trúc cũ.

Độ dài `content` cho biết số phần tử thực tế trong phản hồi. Nó có thể nhỏ hơn `page.size`, chẳng hạn ở trang cuối.

## 3. Ví dụ nhỏ không cần repository

Ví dụ sau dùng Java 17 trở lên và Spring Data Commons có `PagedModel`. Dữ liệu được tạo trong bộ nhớ để nhìn rõ mối liên hệ giữa nội dung và metadata:

```java
import java.util.List;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.web.PagedModel;

record ProductView(Long id, String name) {
}

class PageRepresentationExample {

    static PagedModel<ProductView> example() {
        List<ProductView> content = List.of(
                new ProductView(103L, "Bàn làm việc"),
                new ProductView(104L, "Đèn bàn"));

        Page<ProductView> page = new PageImpl<>(
                content,
                PageRequest.of(1, 2),
                5);

        return new PagedModel<>(page);
    }
}
```

Khi kết quả được serialize bằng hạ tầng JSON phù hợp, nó tương ứng với cấu trúc ở phần 2.

Ba tham số của `PageImpl` ở đây là nội dung trang, thông tin yêu cầu trang và tổng số phần tử. Tổng 5 là giả định của dữ liệu minh họa. Trong ứng dụng thật, không được thay tổng số phần tử bằng một con số tùy ý chỉ để tạo đủ metadata.

Đặc biệt, `new PageImpl<>(content)` không tương đương với việc đưa vào nội dung của một trang bất kỳ trong tập lớn hơn. Constructor chỉ nhận danh sách xem danh sách đó như toàn bộ kết quả. Ý nghĩa các constructor được mô tả trong [PageImpl API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/PageImpl.html).

## 4. Trả PagedModel trực tiếp từ controller

Giả định ứng dụng đã có Spring MVC, hỗ trợ binding `Pageable`, hạ tầng JSON và một implementation của `ProductQueries`.

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PagedModel;
import org.springframework.data.web.PageableDefault;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/products")
class ProductController {

    private final ProductQueries queries;

    ProductController(ProductQueries queries) {
        this.queries = queries;
    }

    @GetMapping
    PagedModel<ProductView> list(
            @PageableDefault(size = 2, sort = "id")
            Pageable pageable) {

        Page<ProductView> page = queries.findProducts(pageable);
        return new PagedModel<>(page);
    }
}

interface ProductQueries {
    Page<ProductView> findProducts(Pageable pageable);
}
```

`ProductView` dùng lại record ở ví dụ trước. `ProductQueries` là cổng truy vấn do ứng dụng cài đặt; tên phương thức trên interface này không tự làm nó trở thành một Spring Data repository.

Implementation có thể gọi repository với store hỗ trợ phân trang và áp dụng điều kiện truy vấn cần thiết. Ví dụ request:

```http
GET /api/products?page=1&size=2&sort=id,asc
```

Trong luồng này:

- Resolver chuyển tham số HTTP thành `Pageable`.
- Service hoặc repository thực hiện truy vấn để có `Page`.
- Controller bọc trang thành `PagedModel`.
- HTTP message converter serialize mô hình thành JSON.

Constructor của `PagedModel` không tự truy vấn database, không tìm repository và không tạo endpoint. Mapping `/api/products` vẫn do controller khai báo.

## 5. Chuyển phần tử sang DTO trước khi bọc

### 5.1. Page.map giữ cấu trúc phân trang

Giả sử service đã có một `Page<Product>`, trong đó domain `Product` có các getter `getId()` và `getName()`. Có thể chuyển phần tử như sau:

```java
Page<ProductView> viewPage = productPage.map(
        product -> new ProductView(
                product.getId(),
                product.getName()));

PagedModel<ProductView> body = new PagedModel<>(viewPage);
```

`Page.map` là thao tác chuyển từng phần tử sang kiểu mới, được định nghĩa trong [Page API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Page.html). Với `PageImpl`, cách ánh xạ này giữ thông tin phân trang và tổng của trang nguồn.

Không cần lấy danh sách ra rồi tự lắp lại một `PageImpl` chỉ để đổi kiểu phần tử. Làm như vậy dễ bỏ mất số trang hoặc tổng số bản ghi.

### 5.2. Generic không tự biến entity thành DTO

Viết `PagedModel<ProductView>` không phải một lệnh ánh xạ các field của entity. Đối tượng được bọc phải có kiểu nội dung phù hợp.

Nếu bọc `Page<Product>`, nội dung vẫn là các đối tượng `Product`. `PagedModel` không tự loại bỏ field, không tự áp dụng projection và không thay thế chính sách serialize của từng phần tử.

Với store có hỗ trợ projection, có thể chọn projection ngay tại truy vấn. Tuy nhiên, dùng `Page.map` sau khi đã tải entity không tự làm database chỉ select những cột có trong DTO. Chi phí tải dữ liệu do truy vấn và mapping của store quyết định.

### 5.3. Lọc dữ liệu sau phân trang dễ làm metadata sai nghĩa

Một mẫu xử lý dễ gây nhầm:

```text
Lấy Page có tổng 100 phần tử
    -> Bỏ các phần tử không được phép xem khỏi content
    -> Vẫn trả metadata tổng 100
```

Khi đó danh sách và metadata không còn mô tả cùng một tập kết quả. Nếu cần giới hạn dữ liệu theo tenant, quyền đọc hoặc điều kiện nghiệp vụ, hãy áp dụng phạm vi phù hợp vào truy vấn và cách tính tổng.

DTO giúp kiểm soát biểu diễn của phần tử; nó không sửa một truy vấn có phạm vi dữ liệu sai.

## 6. Bật VIA_DTO để đơn giản hóa biểu diễn PageImpl

Không nhất thiết phải sửa từng handler từ `Page<T>` sang `PagedModel<T>`. Spring Data Web Support có chế độ serialize gián tiếp qua DTO:

```java
import static org.springframework.data.web.config
        .EnableSpringDataWebSupport.PageSerializationMode.VIA_DTO;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.web.config.EnableSpringDataWebSupport;

@Configuration
@EnableSpringDataWebSupport(pageSerializationMode = VIA_DTO)
class PageJsonConfiguration {
}
```

Ví dụ giả định cấu hình Spring MVC của ứng dụng đã tồn tại. Nếu ứng dụng đã có cấu hình web support tương ứng, cần tích hợp lựa chọn này vào cấu hình đó thay vì tạo các đăng ký cạnh tranh.

Handler có thể tiếp tục khai báo:

```java
@GetMapping("/api/products")
Page<ProductView> list(Pageable pageable) {
    return queries.findProducts(pageable);
}
```

Đây là phương án thay thế cho handler trả `PagedModel`, không phải mapping thứ hai để đặt đồng thời vào cùng controller.

Chế độ `VIA_DTO` làm các instance `PageImpl` đi qua kiểu bọc `PagedModel` khi render JSON. Chế độ `DIRECT` để chúng được render trực tiếp. Ý nghĩa hai lựa chọn được định nghĩa trong [PageSerializationMode API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/web/config/EnableSpringDataWebSupport.PageSerializationMode.html).

### 6.1. Chữ ký Java và hình dạng JSON là hai việc khác nhau

Khi dùng `VIA_DTO`:

```text
Kiểu trả về Java: Page<ProductView>
Implementation thực tế thường gặp: PageImpl<ProductView>
JSON: content + page
```

Đổi chế độ serialize không chuyển biến cục bộ trong service thành một `PagedModel`. Mã Java vẫn làm việc với `Page`; phép chuyển thuộc tầng biểu diễn JSON.

Tài liệu API hoặc schema mà client dùng cần mô tả JSON thực tế, kể cả khi công cụ tạo schema nhìn thấy chữ ký Java là `Page<T>`.

### 6.2. Không suy rộng sang mọi kiểu trả về

Cơ chế được công bố nhắm đến `PageImpl`. Không giả định một implementation `Page` tùy biến, một `Slice`, một `Window` hay một danh sách bất kỳ đều được tự đổi thành cùng biểu diễn.

Nếu muốn chủ động xác định kiểu phản hồi tại một endpoint, bọc trực tiếp `new PagedModel<>(page)` làm ý định dễ thấy hơn. Nếu muốn áp dụng thống nhất cho các handler đang trả `PageImpl`, `VIA_DTO` là một lựa chọn cấu hình dùng chung.

Cấu hình serialize còn phụ thuộc hạ tầng JSON thực tế của ứng dụng. Một ObjectMapper hoặc message converter do ứng dụng tự dựng cần có tích hợp phù hợp với bộ phiên bản đang sử dụng; annotation không bảo đảm mọi mapper độc lập tự nhận cùng hành vi.

## 7. Hiểu đúng metadata ở các trường hợp biên

### 7.1. Trang cuối có ít phần tử hơn size

Với tổng 5 phần tử và size 2, trang có number 2 có thể trả:

```json
{
  "content": [
    {"id": 105, "name": "Kệ sách"}
  ],
  "page": {
    "size": 2,
    "number": 2,
    "totalElements": 5,
    "totalPages": 3
  }
}
```

`size` vẫn là 2; số phần tử thực tế của trang này là 1.

### 7.2. Không có dữ liệu phù hợp

Có thể biểu diễn trang rỗng có thông tin yêu cầu cụ thể:

```java
Page<ProductView> emptyPage =
        Page.empty(PageRequest.of(0, 2));

PagedModel<ProductView> body = new PagedModel<>(emptyPage);
```

Với trang có phân trang này, phản hồi thông thường là:

```json
{
  "content": [],
  "page": {
    "size": 2,
    "number": 0,
    "totalElements": 0,
    "totalPages": 0
  }
}
```

Không thay trang rỗng bằng `null` hoặc biến mất trường `content` nếu hợp đồng API đã chọn một mảng nội dung. Constructor `PagedModel` yêu cầu `Page` không null.

Cũng không áp đặt rằng mọi kiểu trang rỗng, kể cả trường hợp không phân trang, phải có metadata giống hệt ví dụ này. Wrapper đọc thông tin từ trang nguồn.

### 7.3. Yêu cầu trang vượt quá tổng số trang

Nếu tập kết quả có 3 trang mà client yêu cầu chỉ số trang 8, `PagedModel` không tự đưa number về 2. Nó không phải bộ kiểm tra hợp lệ của request và không tự chọn mã lỗi HTTP.

Ứng dụng cần có chính sách về việc trả trang rỗng hay báo lỗi. Metadata phản hồi phải tương ứng với kết quả và chính sách đó; không sửa số trang để giả vờ đã thực hiện một request khác mà không có hợp đồng rõ ràng.

### 7.4. Request bắt đầu từ 1 không tự đổi metadata đầu ra

Resolver có thể được cấu hình nhận trang đầu là `page=1` từ HTTP, nhưng `Page` nội bộ vẫn thường đánh số từ 0. `PagedModel` lấy number từ trang nguồn.

Nếu API muốn cả request lẫn response đều bắt đầu từ 1, cần thiết kế biểu diễn đầu ra tương ứng, chẳng hạn DTO riêng. Chỉ bật one-indexed cho resolver chưa thực hiện chuyển đổi này.

## 8. Phân biệt hai lớp cùng tên PagedModel

| Đặc điểm | `org.springframework.data.web.PagedModel` | `org.springframework.hateoas.PagedModel` |
| --- | --- | --- |
| Thuộc mô-đun | Spring Data Commons | Spring HATEOAS |
| Mục đích ở đây | Biểu diễn trang đơn giản với nội dung và metadata | Mô hình collection phân trang có khả năng mang liên kết |
| Cách tạo phổ biến | `new PagedModel<>(page)` | Dùng API của HATEOAS hoặc assembler phù hợp |
| Liên kết chuyển trang | Không tự tạo | Có thể mang các link được xây dựng hoặc bổ sung |
| Nhu cầu thêm HATEOAS | Không bắt buộc cho kiểu bọc đơn giản | Cần Spring HATEOAS |

Khả năng mang metadata và liên kết của lớp HATEOAS được thể hiện trong [Spring HATEOAS PagedModel API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/PagedModel.html).

Một lỗi dễ gặp là IDE tự import lớp HATEOAS, sau đó `new PagedModel<>(page)` không còn khớp API đang học. Hãy kiểm tra toàn bộ package, không chỉ tên ngắn.

Các lời gọi như `PagedModel.of(...)` hoặc `PagedModel.empty(...)` thuộc API của lớp HATEOAS, không phải cách tạo của lớp Commons trong bài này. Với Commons, muốn trả trang rỗng thì tạo một `Page` rỗng rồi bọc nó.

Nếu yêu cầu có link `next`, `prev` và biểu diễn hypermedia phù hợp, cần chọn hạ tầng HATEOAS và assembler tương ứng. Chỉ đổi tên import không tự xây dựng chính sách link cho API.

## 9. PagedModel không thay đổi khả năng của repository

Đặt kết quả vào `PagedModel` không làm phát sinh những khả năng sau:

- Tự bổ sung phân trang cho một query hoặc store chưa hỗ trợ.
- Chuyển một `Slice` thành một `Page` có tổng số phần tử đúng.
- Tự chạy hoặc tối ưu truy vấn count.
- Chuyển đường truy cập blocking thành non-blocking.
- Tự sửa sort không hợp lệ hoặc thêm một khóa sort duy nhất.
- Tự bật auditing hoặc tự xuất repository thành REST API.

Một `Page` có tổng số phần tử cần có nguồn tổng hợp lệ. Store có thể thực hiện count, sử dụng thông tin có sẵn hoặc tối ưu theo tình huống. Wrapper không loại bỏ chi phí đó.

Khi endpoint chỉ cần dữ liệu và dấu hiệu còn trang kế tiếp, một hợp đồng dựa trên `Slice` có thể hợp lý hơn. Không dựng tổng bằng độ dài trang hiện tại chỉ để ép kết quả vào `PagedModel`.

Với dữ liệu thay đổi giữa các request, một biểu diễn JSON nhất quán cũng không tạo snapshot của toàn bộ tập dữ liệu. Tính ổn định của schema, thứ tự kết quả và độ nhất quán giữa các lần đọc là những vấn đề khác nhau.

Metadata của `page` là metadata phân trang. Nó không thay thế metadata domain như người tạo, thời điểm tạo hay phiên bản bản ghi.

## 10. Đưa kiểu biểu diễn này vào hợp đồng API

Trước khi dùng `PagedModel`, cần chọn nội dung phần tử và ý nghĩa metadata mà client sẽ nhận. Có thể diễn tả hợp đồng như sau:

```text
GET /api/products

Response:
- content: mảng ProductView
- page.size: kích thước trang
- page.number: chỉ số trang bắt đầu từ 0
- page.totalElements: tổng số phần tử của cùng tập lọc
- page.totalPages: tổng số trang

Không công bố trong biểu diễn này:
- cấu trúc nội bộ của Pageable
- liên kết điều hướng tự động
```

Khi thay một phản hồi đang serialize `PageImpl` trực tiếp, cần đối chiếu những trường frontend đang dùng. Thay đổi từ nhiều property nội bộ sang `content` và `page` có thể đòi hỏi cập nhật client hoặc quản lý phiên bản API.

Những tình huống có giá trị để xác nhận trong ứng dụng gồm:

| Tình huống | Điều cần xác nhận |
| --- | --- |
| Trang giữa | Số trang, size và tổng khớp truy vấn |
| Trang cuối chưa đủ size | `content.length` nhỏ hơn size mà metadata vẫn đúng |
| Không có kết quả | Mảng rỗng và metadata phù hợp với trang nguồn |
| Map entity sang DTO | Kiểu phần tử đổi, thông tin phân trang được giữ |
| Bật `VIA_DTO` | JSON thực tế chuyển sang biểu diễn dự kiến |
| Import nhầm lớp HATEOAS | Phát hiện sai package và sai API tạo đối tượng |
| Phân quyền hoặc lọc theo tenant | Nội dung và tổng mô tả cùng một phạm vi |
| Nâng phiên bản thư viện | Schema HTTP tiếp tục đáp ứng hợp đồng đã công bố |

Sử dụng lớp này ở biên web giúp giữ ranh giới rõ ràng: repository tạo kết quả dữ liệu, ứng dụng chọn DTO cho phần tử, còn `PagedModel` cung cấp biểu diễn trang để client sử dụng.

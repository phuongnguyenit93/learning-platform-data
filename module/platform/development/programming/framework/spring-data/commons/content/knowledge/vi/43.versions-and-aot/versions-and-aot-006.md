# Thay đổi Jackson, PagedModel và định dạng web

## 1. Vấn đề: nâng thư viện nhưng vô tình thay đổi API

Trong Spring Data Commons, `Page`, `Pageable`, `Sort` và các abstraction repository giúp thống nhất cách truy vấn dữ liệu. Khi một controller trả kết quả qua HTTP, còn có một hợp đồng khác cần giữ ổn định: JSON mà client nhận được.

Hai hợp đồng này liên quan nhưng không đồng nhất. `Page<ProductView>` là kiểu Java mô tả một trang dữ liệu; cấu trúc JSON của response phụ thuộc vào mô hình trả về, cấu hình web và Jackson đang được sử dụng. Một ứng dụng vẫn biên dịch, truy vấn đúng và trả HTTP 200 sau khi nâng phiên bản, nhưng client có thể hỏng vì tên trường hoặc vị trí metadata phân trang thay đổi.

Bài này thuộc phần **Phiên bản và AOT** của **SPRING_DATA_COMMONS**. Trọng tâm là cách thay đổi Jackson ảnh hưởng đến lớp web, vai trò của `org.springframework.data.web.PagedModel`, và cách xây dựng response phân trang có thể kiểm soát khi nâng phiên bản hoặc chạy native image. Các ví dụ dùng abstraction chung của Spring Data; chúng không phụ thuộc vào một cơ chế lưu trữ cụ thể như JPA hay MongoDB.

Sau bài học, bạn cần phân biệt được:

- Trang dữ liệu trong Java với định dạng JSON công khai.
- Serialize trực tiếp `PageImpl` với chuyển trang sang DTO.
- `PagedModel` của Spring Data với `PagedModel` của Spring HATEOAS.
- Thay đổi thư viện Jackson với quyết định thay đổi hợp đồng API.
- Kiểm thử JSON trên JVM với kiểm chứng đường chạy trong native image.

## 2. Ba lớp quyết định response cuối cùng

Giả sử repository trả về một trang sản phẩm. Đường đi của dữ liệu có thể mô tả như sau:

```text
Repository hoặc service
    |
    | Page<Product> hoặc Page<ProductView>
    v
Controller và mô hình response
    |
    | Page, PagedModel hoặc DTO tự định nghĩa
    v
HTTP message converter cùng Jackson
    |
    | JSON, tên trường, kiểu số, định dạng thời gian
    v
Client web, ứng dụng di động, API consumer
```

Spring Data Commons cung cấp các abstraction như `Page`, `PageImpl`, `PageRequest` và `Sort`. Jackson thực hiện ánh xạ đối tượng sang JSON thông qua cơ chế chuyển đổi thông điệp HTTP. Spring HATEOAS, nếu được dùng, bổ sung mô hình liên kết và biểu diễn tài nguyên.

Vì vậy, không thể suy luận rằng “repository không đổi thì JSON không đổi”. Cần xem cả kiểu response, module Jackson được đăng ký, cấu hình mapper và media type.

| Lớp | Ví dụ | Điều cần giữ rõ ràng |
| --- | --- | --- |
| Truy vấn | `findAll(Pageable)` | Dữ liệu, thứ tự, điều kiện và tổng số phần tử |
| Mô hình kết quả Java | `Page<ProductView>` | Nội dung và thông tin phân trang |
| Mô hình response | `PagedModel<ProductView>` | Cấu trúc công khai mà client sẽ sử dụng |
| Serialization | Jackson và HTTP converter | Cách biểu diễn trường, số, thời gian, `null` |
| Giao thức | `application/json`, HAL nếu có | Biểu diễn thực tế và cơ chế thương lượng nội dung |

## 3. Jackson thay đổi theo phiên bản như thế nào?

### 3.1. Phân biệt Spring Data, Spring Boot và Jackson

Spring Data Commons thuộc một hệ phiên bản của Spring Data. Spring Boot thường quản lý tổ hợp phiên bản tương thích của Spring Framework, Spring Data, Jackson và các thư viện liên quan qua dependency management.

Không nên xử lý một bản nâng cấp lớn bằng cách chỉ thay riêng `jackson-databind` rồi cho rằng toàn bộ lớp web đã được nâng tương ứng. Mã biên dịch có thể dùng một hệ Jackson, trong khi HTTP converter hoặc module mở rộng vẫn thuộc hệ khác.

Một số mốc giúp định hướng việc đọc mã và tài liệu của dự án:

| Dòng phiên bản | Điểm cần chú ý |
| --- | --- |
| Spring Data Commons trước 3.3 | Chưa có cơ chế `PagedModel` và `VIA_DTO` được giới thiệu ở 3.3; có thể dùng DTO do ứng dụng định nghĩa hoặc Spring HATEOAS |
| Spring Data Commons từ 3.3 | Có `org.springframework.data.web.PagedModel` và chế độ `PageSerializationMode.VIA_DTO` để biểu diễn trang qua DTO |
| Hệ Spring Data 3.x với Jackson 2 | Cần dùng các API và module tương thích Jackson 2 |
| Hệ Spring Data 4.x / Spring Framework 7 | Có bước chuyển sang hệ Jackson 3; cần kiểm tra converter, module và customization theo đúng phiên bản đang dùng |

Bảng này nêu các mốc thiết kế, không phải danh sách dependency để sao chép. Phiên bản cụ thể của dự án phải theo BOM và dependency management đã chọn. Cấu hình hỗ trợ Jackson 2 trong một hệ mới cũng cần được xem như một lựa chọn có chủ đích, không được suy ra chỉ từ việc class còn tồn tại trên classpath.

### 3.2. Đổi package không chỉ là đổi import

Một thay đổi dễ thấy khi chuyển từ Jackson 2 sang Jackson 3 là nhiều API lõi và databind đổi namespace:

```java
// Ví dụ kiểu mapper trong Jackson 2
com.fasterxml.jackson.databind.ObjectMapper

// Ví dụ kiểu mapper trong Jackson 3
tools.jackson.databind.ObjectMapper
```

Không áp dụng phép thay thế toàn cục `com.fasterxml.jackson` thành `tools.jackson`. Nhóm annotation là trường hợp quan trọng: Jackson 3 tiếp tục sử dụng các annotation thuộc namespace `com.fasterxml.jackson.annotation`. Cần xét từng dependency và API thực tế.

Hai class mapper có tên ngắn giống nhau nhưng thuộc hai kiểu Java khác nhau. Tương tự, module hoặc serializer viết cho Jackson 2 không trở thành module Jackson 3 chỉ vì đổi một vài import. Khi di chuyển, cần xem lại:

- Mapper nào thực sự được HTTP converter sử dụng.
- Module nào được đăng ký vào mapper đó.
- Extension point, builder hoặc customizer có còn đúng với phiên bản mới.
- Serializer/deserializer tùy chỉnh có được chuyển sang API tương thích.
- Cấu hình thời gian, enum, naming strategy và xử lý giá trị `null` có giữ nguyên ý nghĩa.

Một bean mapper tự tạo chưa chắc là mapper xử lý response của controller. Cần kiểm chứng đường HTTP thực tế thay vì chỉ gọi một mapper được dựng riêng trong unit test.

### 3.3. Đổi Jackson không bắt buộc đổi JSON công khai

Việc nâng Jackson là thay đổi hạ tầng. Chọn một cấu trúc response mới là thay đổi hợp đồng API. Hai việc có thể diễn ra cùng đợt triển khai, nhưng phải được đánh giá riêng.

Ví dụ, client có thể phụ thuộc vào:

```text
content[*].id
content[*].name
page.number
page.size
page.totalElements
page.totalPages
```

Nếu các đường dẫn, kiểu dữ liệu và ý nghĩa này được giữ nguyên, việc thay mapper bên dưới không nhất thiết buộc client thay mã. Ngược lại, chỉ cần chuyển `totalElements` từ cấp gốc vào `page.totalElements` cũng đã là thay đổi mà client cần biết, dù dữ liệu truy vấn vẫn giống hệt.

## 4. Vì sao không nên lấy JSON của PageImpl làm hợp đồng lâu dài?

`Page` là interface mô tả một trang. `PageImpl` là một implementation thường được dùng để chứa nội dung và metadata của trang đó.

Một controller dễ viết như sau:

```java
@GetMapping("/products")
public Page<ProductView> products(Pageable pageable) {
    return productService.search(pageable);
}
```

Tùy cấu hình, Jackson có thể serialize trực tiếp đối tượng `PageImpl`. Khi đó JSON có thể phơi bày các thuộc tính Java như `pageable`, `sort`, `first`, `last`, `numberOfElements` và các thông tin khác.

Vấn đề không nằm ở việc JSON có đọc được hay không. Vấn đề là hình dạng của implementation không phải hợp đồng web ổn định được cam kết cho client. Thay đổi implementation, accessor hoặc hỗ trợ serialization giữa các phiên bản có thể ảnh hưởng đến biểu diễn này.

Ở các phiên bản có cảnh báo serialize `PageImpl` trực tiếp, cần hiểu cảnh báo là dấu hiệu để kiểm soát mô hình response. Tắt log chỉ làm mất tín hiệu; nó không tạo ra hợp đồng JSON ổn định.

Một lỗi suy luận phổ biến là cho rằng khai báo kiểu trả về `Page<ProductView>` sẽ che implementation khỏi Jackson. Khai báo interface không tự biến đối tượng runtime thành một DTO công khai. Đường serialization vẫn cần được thiết kế rõ ràng.

## 5. PagedModel của Spring Data: vỏ JSON dành cho Page

### 5.1. Dùng đúng class

Class cần dùng trong phần này là:

```java
import org.springframework.data.web.PagedModel;
```

Đây là DTO dành cho biểu diễn phân trang của Spring Data, được giới thiệu từ Spring Data Commons 3.3. Nó bọc một `Page` để xuất nội dung cùng metadata phân trang theo một cấu trúc đơn giản.

Ví dụ dưới đây giả định `ProductService.search(Pageable)` đã tồn tại và trả về `Page<ProductView>`. Service chịu trách nhiệm truy vấn và ánh xạ dữ liệu; Spring Data Commons không tự cung cấp implementation của service này.

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.web.PageableDefault;
import org.springframework.data.web.PagedModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

record ProductView(Long id, String name) {}

@RestController
@RequestMapping("/products")
class ProductController {

    private final ProductService productService;

    ProductController(ProductService productService) {
        this.productService = productService;
    }

    @GetMapping
    PagedModel<ProductView> products(
            @PageableDefault(
                    size = 2,
                    sort = "name",
                    direction = Sort.Direction.ASC)
            Pageable pageable) {

        Page<ProductView> page = productService.search(pageable);
        return new PagedModel<>(page);
    }
}
```

Ví dụ request:

```http
GET /products?page=0&size=2&sort=name,asc
Accept: application/json
```

Nếu có tổng cộng 5 sản phẩm, trang đầu chứa 2 sản phẩm, response theo mô hình này có dạng:

```json
{
  "content": [
    { "id": 101, "name": "Bàn phím" },
    { "id": 102, "name": "Chuột" }
  ],
  "page": {
    "size": 2,
    "number": 0,
    "totalElements": 5,
    "totalPages": 3
  }
}
```

Thứ tự các thuộc tính trong JSON không phải ý nghĩa của hợp đồng. Điều cần giữ là tên trường, kiểu giá trị, cấu trúc và ngữ nghĩa.

### 5.2. Đọc đúng metadata

| Trường | Ý nghĩa |
| --- | --- |
| `content` | Danh sách phần tử trên trang hiện tại |
| `page.size` | Kích thước trang được mô hình phân trang báo cáo; không phải lúc nào cũng bằng số phần tử trong `content` |
| `page.number` | Chỉ số trang trong mô hình `Page`, thông thường bắt đầu từ 0 |
| `page.totalElements` | Tổng số phần tử của tập kết quả theo `Page` |
| `page.totalPages` | Tổng số trang theo metadata của `Page` |

Trang cuối trong ví dụ có thể có `content` chỉ gồm 1 phần tử nhưng `page.size` vẫn là 2. Client không được coi `page.size` là số phần tử thực tế của trang đang hiển thị.

Nếu ứng dụng bật cách nhận tham số trang bắt đầu từ 1 ở web resolver, điều đó không tự biến `Page.getNumber()` thành giá trị bắt đầu từ 1. Cần phân biệt quy ước đầu vào HTTP với quy ước của đối tượng `Page` và công bố rõ quy ước của response.

### 5.3. PagedModel không làm gì thay repository?

`new PagedModel<>(page)` chuyển mô hình biểu diễn; thao tác này không tự thực hiện truy vấn, không tự đếm dữ liệu và không tối ưu câu lệnh truy cập cơ sở dữ liệu.

Nếu truy vấn tạo `Page` cần thực hiện phép đếm để biết tổng số phần tử, chi phí đó thuộc lớp repository hoặc service. Đổi response từ `Page` sang `PagedModel` không xóa chi phí đếm.

Mô hình này cũng không tự:

- Thêm liên kết điều hướng HTTP.
- Xuất toàn bộ cấu hình `Sort` trong response.
- Xác thực thuộc tính được phép sắp xếp.
- Chuyển entity thành DTO hoặc che các trường nhạy cảm.
- Chuẩn hóa định dạng ngày giờ và số thập phân của từng phần tử.

Envelope phân trang được kiểm soát tốt hơn, còn hợp đồng của từng item vẫn do ứng dụng thiết kế. Nếu API cần trả lại tiêu chí sort, liên kết điều hướng hoặc mã theo dõi request, cần chọn mô hình response có các trường đó.

## 6. VIA_DTO: chuyển đổi tập trung tại lớp web

Từ Spring Data Commons 3.3, có thể bật chế độ chuyển đổi trang sang DTO qua cấu hình hỗ trợ web:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.web.config.EnableSpringDataWebSupport;

import static org.springframework.data.web.config.EnableSpringDataWebSupport
        .PageSerializationMode.VIA_DTO;

@Configuration
@EnableSpringDataWebSupport(pageSerializationMode = VIA_DTO)
class SpringDataWebConfiguration {
}
```

Trong cấu hình hỗ trợ tương ứng, trang `PageImpl` được xử lý qua biểu diễn DTO thay vì phơi bày trực tiếp hình dạng implementation. Controller có thể tiếp tục khai báo trả `Page<ProductView>` trong khi response dùng cấu trúc `content` và `page`.

Cần phân biệt hai lựa chọn:

| Lựa chọn | Phạm vi quyết định | Cách đọc mã |
| --- | --- | --- |
| Trả `new PagedModel<>(page)` | Từng endpoint hoặc lớp ánh xạ response | Kiểu trả về thể hiện rõ mô hình công khai |
| Bật `PageSerializationMode.VIA_DTO` | Tập trung trong cấu hình web | Endpoint trả `Page` có thể được đổi biểu diễn khi serialize |

Không cần bọc thủ công chỉ để lặp lại một cấu hình chuyển đổi đã được áp dụng đúng. Ngược lại, bọc trực tiếp là cách rõ ràng khi muốn áp dụng cho từng endpoint và giữ kiểu response có thể đọc được ngay trong controller.

Trong ứng dụng Spring Boot, cần xem auto-configuration và cấu hình web hiện hữu trước khi thêm `@EnableSpringDataWebSupport`. Bật cấu hình thủ công có thể ảnh hưởng đến việc Boot áp dụng cấu hình resolver và các thuộc tính liên quan. Không nên thêm nhiều cấu hình chồng nhau rồi giả định tất cả thiết lập `Pageable` vẫn được kết hợp như cũ.

Chế độ `DIRECT` gắn với việc serialize trực tiếp trang. Nó không phải giải pháp để bảo đảm hình dạng JSON của `PageImpl` ổn định qua các phiên bản.

Một điểm cần đánh giá khi nâng cấp hệ thống cũ: bật `VIA_DTO` có thể chuyển metadata đang ở cấp gốc vào đối tượng `page`. Đây là thay đổi response cần được kiểm thử và phối hợp với client. “Cấu hình được khuyến nghị” không có nghĩa là mọi consumer đang chạy sẽ tự tương thích.

## 7. Phân biệt hai class cùng tên PagedModel

Spring Data và Spring HATEOAS có các class cùng tên ngắn. IDE tự thêm import sai là một nguồn lỗi thường gặp.

| Đặc điểm | Spring Data Commons | Spring HATEOAS |
| --- | --- | --- |
| Tên đầy đủ | `org.springframework.data.web.PagedModel` | `org.springframework.hateoas.PagedModel` |
| Vai trò chính | DTO đơn giản bọc `Page` | Mô hình tài nguyên phân trang có khả năng chứa liên kết |
| Nội dung điển hình | `content` và `page` | Nội dung tài nguyên, metadata, liên kết; biểu diễn tùy cấu hình media type |
| Cách dùng thường gặp | `new PagedModel<>(page)` hoặc `VIA_DTO` | Dùng assembler như `PagedResourcesAssembler` để tạo mô hình |
| Có tự trở thành HAL không? | Không | Cần tích hợp và cấu hình biểu diễn HATEOAS phù hợp |

Nếu yêu cầu của API là client điều hướng theo liên kết `self`, `next`, `prev`, có thể dùng Spring HATEOAS và cơ chế assembler phù hợp. Với HAL, response thường có các cấu trúc như `_links` và `_embedded`; tên quan hệ tài nguyên và chi tiết biểu diễn phụ thuộc vào cấu hình.

Không được chuyển từ DTO Spring Data sang HAL mà coi đó là thay đổi nội bộ. Client đọc `content` không tự tìm được dữ liệu trong `_embedded`. Cần xem media type, mô hình response và tài liệu API như một bộ thống nhất.

## 8. Khi nào cần DTO phân trang do ứng dụng định nghĩa?

Nếu tổ chức đã có hợp đồng API riêng, chẳng hạn `items`, `meta` và thông tin version, có thể giữ hợp đồng bằng DTO thuộc ứng dụng.

```java
import java.util.List;

import org.springframework.data.domain.Page;

public record PageResponse<T>(
        List<T> items,
        PageInfo meta) {

    public static <T> PageResponse<T> from(Page<T> page) {
        return new PageResponse<>(
                List.copyOf(page.getContent()),
                new PageInfo(
                        page.getNumber(),
                        page.getSize(),
                        page.getTotalElements(),
                        page.getTotalPages()));
    }

    public record PageInfo(
            int number,
            int size,
            long totalElements,
            int totalPages) {
    }
}
```

DTO này chủ động tạo một hợp đồng khác với `PagedModel` của Spring Data. Nếu đang có consumer sử dụng `items` và `meta`, chuyển sang `content` và `page` vẫn là thay đổi hợp đồng, dù mô hình mới cũng hợp lý.

Lựa chọn có thể dựa vào nhu cầu thực tế:

- Dùng DTO `PagedModel` của Spring Data khi cần biểu diễn trang đơn giản, thống nhất với cơ chế hỗ trợ sẵn của Spring Data.
- Dùng Spring HATEOAS khi API cần mô hình tài nguyên và liên kết điều hướng.
- Dùng DTO riêng khi hợp đồng API đã được chuẩn hóa độc lập hoặc cần thêm metadata đặc thù.

Dù chọn cách nào, nên đưa DTO item vào trang thay vì trả entity trực tiếp. Projection của Spring Data có thể giúp chọn dữ liệu cần lấy, nhưng projection không tự quyết định toàn bộ chính sách public API. Đặc biệt, interface projection có thể dùng proxy; cần xem kỹ các trường được xuất và khả năng hỗ trợ trong môi trường native.

## 9. Những thay đổi web cần quan sát ngoài envelope

### 9.1. Thời gian, số, enum và null

Ổn định `content` và `page` mới giải quyết một phần hợp đồng. Khi nâng Jackson hoặc cấu hình mapper, cần quan sát cả dữ liệu bên trong `content`.

| Dữ liệu | Ví dụ thay đổi cần phát hiện |
| --- | --- |
| Ngày giờ | Chuỗi có offset trở thành chuỗi thiếu offset; timestamp thành chuỗi hoặc ngược lại |
| Giá trị tiền | JSON number thành string; thay đổi quy ước làm tròn ở tầng ứng dụng |
| Enum | Tên hằng Java khác với mã nghiệp vụ đã công bố |
| Giá trị `null` | Trường xuất hiện với `null` trở thành trường bị loại bỏ |
| Tên trường | `totalAmount` chuyển thành `total_amount` do naming strategy |
| Định danh | Client xử lý sai các số nguyên lớn vì giới hạn kiểu số của môi trường JavaScript |

Bảng này là các tình huống cần kiểm chứng, không phải khẳng định rằng mọi bản nâng Jackson đều tự gây ra các thay đổi đó. Không dùng phép đếm ký tự của JSON để kết luận hai response có tương thích hay không.

### 9.2. Tham số request vẫn là hợp đồng riêng

`PagedModel` mô tả output. Nó không quyết định trực tiếp cách bind `page`, `size`, `sort` của request thành `Pageable`.

Cần kiểm tra riêng:

- Tên tham số và prefix/qualifier nếu endpoint có nhiều `Pageable`.
- Chỉ số trang đầu vào bắt đầu từ 0 hay 1.
- Kích thước mặc định và kích thước tối đa.
- Cách xử lý request có kích thước hoặc số trang không hợp lệ.
- Thuộc tính sort được chấp nhận và cách bảo đảm thứ tự ổn định.

Ví dụ, sort chỉ theo `name` có thể chưa tạo thứ tự xác định khi nhiều sản phẩm trùng tên. Với dữ liệu thay đổi liên tục, cần thiết kế thứ tự phù hợp, thường có thêm khóa phân biệt như `id`. Đây là vấn đề truy vấn và phân trang, không được giải quyết chỉ bằng đổi serializer.

### 9.3. Không ép Slice hay cursor thành Page giả

`Page` mang thông tin tổng số phần tử và tổng số trang. `Slice` thường được dùng khi chỉ cần biết có phần tiếp theo, còn `Window` và vị trí cuộn phục vụ các cách duyệt dữ liệu khác.

`PagedModel` của Spring Data được xây quanh `Page`. Không nên bịa `totalElements` hoặc `totalPages` chỉ để ép một kết quả `Slice` vào envelope đó. API dùng slice hoặc cursor nên có mô hình response thể hiện đúng thông tin thực có, chẳng hạn `hasNext` hoặc token tiếp theo.

## 10. Kiểm thử hợp đồng JSON qua đường HTTP

Ví dụ sau minh họa kiểm thử response của controller ở mục 5. Giả định ứng dụng và test context đã có `ProductService`, Spring MVC, Jackson và thư viện kiểm thử phù hợp với dependency management của dự án.

```java
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ProductPageContractTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    ProductService productService;

    @Test
    void returnsProductPageContract() throws Exception {
        var pageable = PageRequest.of(0, 2, Sort.by("name"));
        var page = new PageImpl<>(
                List.of(
                        new ProductView(101L, "Bàn phím"),
                        new ProductView(102L, "Chuột")),
                pageable,
                5);

        when(productService.search(any())).thenReturn(page);

        mvc.perform(get("/products")
                        .param("page", "0")
                        .param("size", "2")
                        .param("sort", "name,asc")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.content.length()").value(2))
                .andExpect(jsonPath("$.content[0].id").value(101))
                .andExpect(jsonPath("$.content[0].name").value("Bàn phím"))
                .andExpect(jsonPath("$.page.number").value(0))
                .andExpect(jsonPath("$.page.size").value(2))
                .andExpect(jsonPath("$.page.totalElements").value(5))
                .andExpect(jsonPath("$.page.totalPages").value(3))
                .andExpect(jsonPath("$.pageable").doesNotExist());
    }
}
```

Ví dụ test dùng cách tổ chức package test của Spring Boot 3 cùng `@MockitoBean` có trong Spring Framework 6.2 trở lên; không phải mã dùng nguyên trạng cho mọi dòng phiên bản. Khi chuyển sang Spring Boot 4, cần cập nhật dependency test và import theo cấu trúc module test của dòng đó. Điều cần giữ khi di chuyển là các assertion về hợp đồng JSON và việc test đi qua cấu hình web thực tế.

Test này xác nhận envelope và item trong một trường hợp có dữ liệu. Nó không kiểm chứng truy vấn cơ sở dữ liệu vì service đã được thay bằng mock. Để kiểm chứng toàn bộ đường truy vấn, cần một test tích hợp riêng với dữ liệu kiểm soát được.

Các trường hợp bổ sung nên được chọn theo rủi ro của API:

| Trường hợp | Điều cần xác nhận |
| --- | --- |
| Không có kết quả | `content` là mảng rỗng, metadata đúng với `Page` do service trả về |
| Trang cuối thiếu phần tử | `content.length` có thể nhỏ hơn `page.size` |
| Trang nằm ngoài phạm vi dữ liệu | Response và metadata đúng chính sách của ứng dụng |
| DTO có thời gian, enum, `null` | Biểu diễn giữ đúng hợp đồng đã công bố |
| Bật `VIA_DTO` | Endpoint trả `Page` thực sự đi qua chuyển đổi mong muốn |
| Client yêu cầu media type khác | Không vô tình chuyển sang một biểu diễn không được hỗ trợ |
| Nâng Jackson hoặc Spring Data | Các đường dẫn JSON mà consumer sử dụng vẫn hợp lệ |

Không chỉ kiểm tra bằng một `ObjectMapper` dựng riêng: test đó có thể bỏ qua module Spring Data hoặc khác với mapper của HTTP converter. Cũng không chỉ kiểm tra HTTP 200: trạng thái thành công không chứng minh client đọc được payload.

## 11. Liên hệ với AOT và native image

AOT và native image làm cho những kiểu được phát hiện ở build time trở nên quan trọng hơn. Một serializer tự đăng ký lúc chạy, một DTO chỉ được tìm qua reflection hoặc một projection được tạo động có thể chạy trên JVM nhưng gặp lỗi khi đóng gói native nếu không có hỗ trợ tương ứng.

Đối với response phân trang, có ba nhóm kiểu cần quan sát:

1. Envelope như `PagedModel` hoặc `PageResponse`.
2. Item như `ProductView`, cùng các kiểu lồng bên trong.
3. Extension Jackson như serializer, deserializer và module tùy chỉnh.

Khai báo response cụ thể như `PagedModel<ProductView>` hoặc `PageResponse<ProductView>` giúp thể hiện kiểu dữ liệu rõ hơn so với `Object` hay raw type. Tuy nhiên, khai báo generic rõ ràng không phải bảo đảm rằng mọi đường đi động và mọi module tùy chỉnh đều được AOT xử lý tự động.

Khi một DTO ứng dụng không được cơ chế phân tích tự động phát hiện, Spring có annotation để đăng ký binding hint, ví dụ:

```java
import org.springframework.aot.hint.annotation.RegisterReflectionForBinding;
import org.springframework.context.annotation.Configuration;

@Configuration
@RegisterReflectionForBinding(ProductView.class)
class ProductBindingHints {
}
```

Đây là ví dụ cho tình huống có nhu cầu hint cụ thể. Không cần thêm hint cho mọi DTO theo thói quen, và hint cho `ProductView` không thay thế việc đăng ký đúng module Jackson hoặc bảo đảm envelope được hỗ trợ. Với kiểu lồng nhau, proxy hoặc serializer tùy chỉnh, cần phân tích đường sử dụng thực tế và cơ chế hint của phiên bản tương ứng.

Khi chuyển hệ Jackson, cần kiểm chứng native lại. Hint hoặc mã đăng ký dành cho một class Jackson 2 không tự chuyển sang class Jackson 3 có tên đầy đủ khác. Đồng thời, build native thành công chưa đủ chứng minh endpoint hoạt động: cần gọi endpoint và đọc payload JSON của binary native.

Phân biệt hai kết luận:

- Test JVM đi qua xác nhận hành vi trong runtime JVM và cấu hình test đó.
- Test trên native image xác nhận hành vi của binary đã biên dịch native trong các đường chạy được thực thi.

Một kết luận không tự bao hàm kết luận còn lại.

## 12. Quy trình nâng phiên bản có thể kiểm soát

### Bước 1: Chốt hợp đồng hiện tại

Lấy các response đại diện và ghi rõ consumer đang sử dụng những trường nào. Bao gồm metadata trang, cấu trúc item và media type. Nếu có OpenAPI hoặc client được sinh mã, đối chiếu schema với payload thực tế.

### Bước 2: Chọn mô hình response đích

Quyết định dùng Spring Data `PagedModel`, HATEOAS hay DTO riêng. Xác định endpoint nào còn trả trực tiếp `Page` và liệu có cần áp dụng `VIA_DTO` tập trung.

Nếu mô hình đích thay đổi đường dẫn JSON, lập kế hoạch thay đổi consumer hoặc phiên bản API. Không bật đồng loạt chỉ vì bản nâng cấp bắt đầu xuất hiện cảnh báo.

### Bước 3: Nâng một tổ hợp dependency tương thích

Dùng BOM hoặc dependency management của hệ đã chọn. Xem cả converter, mapper, module và extension tùy chỉnh. Nếu dự án có cả Jackson 2 và Jackson 3 vì nhu cầu tích hợp, phải xác định rõ từng hệ phục vụ đường nào.

### Bước 4: Kiểm tra request và response

Chạy test hợp đồng qua HTTP với trang đầu, trang cuối, dữ liệu rỗng và các kiểu item nhạy với serialization. Kiểm tra lại cấu hình `Pageable`, giới hạn kích thước trang và sort khi thay cấu hình web.

### Bước 5: Kiểm tra native nếu sản phẩm sử dụng

Build và gọi các endpoint đại diện trong môi trường native. Chỉ thêm hint khi đã xác định nhu cầu; đồng thời kiểm tra serializer tùy chỉnh và projection có được hỗ trợ đúng.

### Bước 6: Cập nhật mô tả API và consumer

Nếu JSON giữ nguyên, tài liệu nên tiếp tục phản ánh đúng hợp đồng. Nếu JSON đổi, cần cập nhật schema, client và hướng dẫn chuyển đổi cùng thời điểm phù hợp. Thay mapper thành công không tự cập nhật mã frontend hoặc SDK đang đọc cấu trúc cũ.

## 13. Chẩn đoán nhanh các lỗi thường gặp

| Hiện tượng | Khả năng cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Client không còn thấy `totalElements` ở cấp gốc | Đã đổi từ biểu diễn trực tiếp sang DTO | Đối chiếu đường dẫn mới `page.totalElements` và kế hoạch tương thích |
| JSON vẫn có cấu trúc nội bộ của `PageImpl` | Chuyển đổi chưa được áp dụng trên đường HTTP thực tế | Kiểm tra kiểu response, hỗ trợ web, module và converter đang dùng |
| Mapper tùy chỉnh không ảnh hưởng response | HTTP converter đang dùng mapper khác | Kiểm tra cấu hình converter và điểm customization của đúng phiên bản |
| Module không biên dịch sau khi nâng cấp | API Jackson 2 và 3 bị trộn lẫn | Xác định hệ Jackson rồi chuyển extension theo API tương thích |
| JSON xuất hiện `_embedded` thay cho `content` | Đã sử dụng biểu diễn HATEOAS/HAL | Kiểm tra import, assembler, media type và hợp đồng endpoint |
| `page.size` lớn hơn số item | Đang ở trang cuối hoặc trang thiếu phần tử | Dùng độ dài `content` để biết số phần tử thực nhận |
| UI lệch một trang | Quy ước đầu vào, `Page` và UI chưa thống nhất | Kiểm tra quy ước 0/1 ở từng ranh giới |
| JVM chạy được nhưng native lỗi serialization | Thiếu hỗ trợ kiểu động, hint hoặc module | Kiểm tra loại DTO, extension và đường chạy trong binary native |
| Tổng số trang sai dù JSON đúng cấu trúc | Metadata từ truy vấn hoặc cách dựng `Page` không đúng | Kiểm tra tổng số phần tử và logic repository/service |

## 14. Bài tập vận dụng

Một API hiện trả trực tiếp `Page<ProductView>`. Frontend đọc `response.content` và `response.totalElements`. Nhóm backend nâng Spring Data và bật `VIA_DTO`; JSON mới chứa `content` cùng `page.totalElements`.

Hãy thực hiện các bước phân tích sau:

1. Chỉ ra thay đổi khiến frontend hỏng dù backend vẫn trả HTTP 200.
2. Chọn giữa giữ hợp đồng cũ bằng DTO riêng hoặc chuyển consumer sang hợp đồng mới.
3. Viết assertion cho đường dẫn tổng số phần tử và quy ước số trang.
4. Thêm trường thời gian hoặc enum vào item rồi xác định điều cần kiểm chứng khi đổi hệ Jackson.
5. Nếu API chạy native, xác định những đường serialization nào cần được gọi sau khi build.

Điểm cốt lõi của bài tập là tách ba quyết định: nâng dependency, chọn mô hình response và thay đổi consumer. `PagedModel` giúp kiểm soát biểu diễn phân trang, còn sự ổn định của API phụ thuộc vào toàn bộ hợp đồng JSON mà ứng dụng chủ động duy trì.
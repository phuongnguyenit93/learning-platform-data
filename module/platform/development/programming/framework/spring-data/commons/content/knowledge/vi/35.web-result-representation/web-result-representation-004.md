# pageSerializationMode = VIA_DTO theo phiên bản hỗ trợ

## 1. Vấn đề khi trả Page trực tiếp qua HTTP

Trong chương **Biểu diễn kết quả web** của module **SPRING_DATA_COMMONS**, cần phân biệt kết quả phân trang ở lớp Java với hợp đồng JSON mà client sử dụng.

`Page<T>` mô tả nội dung một trang cùng thông tin như số trang, kích thước trang và tổng số phần tử. `PageImpl<T>` là một implementation phổ biến của hợp đồng đó. Khi controller trả một đối tượng `PageImpl`, serializer có thể nhìn thấy nhiều thuộc tính nội bộ của implementation và đưa chúng vào JSON.

Ví dụ một response cũ có thể có dạng rút gọn:

```json
{
  "content": [
    { "id": 101, "name": "Bàn phím" },
    { "id": 102, "name": "Chuột" }
  ],
  "number": 0,
  "size": 2,
  "totalElements": 5,
  "totalPages": 3,
  "first": true,
  "last": false
}
```

Đây chỉ là minh họa một hình dạng có thể gặp, không phải schema được bảo đảm cho mọi phiên bản. Nếu client phụ thuộc vào những thuộc tính xuất phát từ implementation, việc nâng cấp thư viện có thể làm thay đổi JSON dù nghiệp vụ truy vấn vẫn như cũ.

`pageSerializationMode = VIA_DTO` cho phép sử dụng một mô hình biểu diễn riêng khi ghi JSON. Mục tiêu là tách hợp đồng web khỏi API nội bộ của `PageImpl`, như [tài liệu biểu diễn Page của Commons](https://docs.spring.io/spring-data/commons/reference/3.5/repositories/core-extensions-web.html) giải thích.

Sau bài học, bạn có thể:

- Xác định phiên bản hỗ trợ `VIA_DTO` và phân biệt với phiên bản hỗ trợ property Spring Boot.
- Bật chế độ bằng annotation hoặc cấu hình Boot phù hợp.
- Đọc đúng cấu trúc `content` và `page` của response.
- Chọn bọc `PagedModel` tường minh hoặc DTO riêng khi cần.
- Lập kế hoạch chuyển đổi hợp đồng API mà client đang sử dụng.

## 2. DIRECT và VIA_DTO

Enum cấu hình nằm bên trong `EnableSpringDataWebSupport`:

```java
org.springframework.data.web.config.EnableSpringDataWebSupport.PageSerializationMode
```

Hai lựa chọn có ý nghĩa khác nhau:

| Chế độ | Cách xử lý biểu diễn | Hệ quả với hợp đồng web |
| --- | --- | --- |
| `DIRECT` | Ghi `PageImpl` theo dạng trực tiếp | JSON phụ thuộc các thuộc tính implementation mà serializer nhìn thấy |
| `VIA_DTO` | Chuyển biểu diễn `PageImpl` qua `PagedModel` của Commons | Response có một lớp mô hình phân trang dành cho JSON |

API của annotation giữ mặc định `DIRECT` vì tương thích ngược. Có thư viện hỗ trợ không đồng nghĩa ứng dụng đã chủ động chọn `VIA_DTO`. Mốc xuất hiện thuộc tính và mặc định được ghi tại [API của EnableSpringDataWebSupport](https://docs.spring.io/spring-data/relational/reference/data-commons/3.5/api/java/org/springframework/data/web/config/EnableSpringDataWebSupport.html); ý nghĩa hai chế độ nằm trong [API PageSerializationMode](https://docs.spring.io/spring-data/commons/docs/3.5.x/api/org/springframework/data/web/config/EnableSpringDataWebSupport.PageSerializationMode.html).

Luồng xử lý có thể hình dung:

```text
Repository hoặc service tạo Page<T>
                 |
                 v
Ứng dụng chọn kiểu dữ liệu của từng phần tử
                 |
                 v
Controller trả Page<DTO>, thực tế có thể là PageImpl<DTO>
                 |
                 v
HTTP message converter dùng mapper đã tích hợp Spring Data
                 |
                 v
VIA_DTO chuyển biểu diễn sang PagedModel<DTO>
                 |
                 v
JSON: content + page
```

Đây là bước biểu diễn khi serialize. Đối tượng repository trả về vẫn tuân theo hợp đồng Java của nó; cấu hình không đổi kiểu trả về của repository thành `PagedModel`.

“DTO” trong `VIA_DTO` chủ yếu nói đến mô hình bọc phân trang. Các phần tử `T` trong `content` vẫn cần được ứng dụng lựa chọn hoặc ánh xạ phù hợp.

## 3. Hai mốc phiên bản cần kiểm tra riêng

### 3.1. Mốc Spring Data Commons

`EnableSpringDataWebSupport.pageSerializationMode` và `org.springframework.data.web.PagedModel` có từ **Spring Data Commons 3.3**. Thông tin `Since: 3.3` được ghi trong API annotation và [mã nguồn PagedModel](https://raw.githubusercontent.com/spring-projects/spring-data-commons/3.5.x/src/main/java/org/springframework/data/web/PagedModel.java).

| Phiên bản Commons | Cách tiếp cận |
| --- | --- |
| Trước 3.3 | Không dùng thuộc tính annotation hoặc `PagedModel` của Commons chưa tồn tại; chọn DTO phân trang riêng hoặc giải pháp được phiên bản đó hỗ trợ |
| Từ 3.3, với API nêu trên | Có thể chọn `VIA_DTO` hoặc bọc `org.springframework.data.web.PagedModel` tường minh |
| Khi chuyển sang dòng lớn khác | Đối chiếu API và tích hợp serializer của dòng đó, nhất là khi thay đổi stack Jackson |

Các ví dụ bên dưới tập trung vào Spring MVC, Java 17 và cơ chế Jackson trong Commons 3.3–3.5. Không nên lấy mã tích hợp nội bộ của một dòng phiên bản rồi áp dụng nguyên trạng cho một dòng dùng serializer khác.

Cần kiểm tra phiên bản dependency thực tế được resolve. Tên phiên bản do dự án khai báo có thể chịu ảnh hưởng của BOM hoặc dependency management. Không nâng riêng Commons lên một phiên bản tùy ý trong hệ sinh thái đang quản lý đồng bộ chỉ để thêm một thuộc tính cấu hình.

### 3.2. Mốc property của Spring Boot

Property:

```properties
spring.data.web.pageable.serialization-mode=via-dto
```

có mốc hỗ trợ khác với API của Commons.

| Trường hợp Boot | Điểm cần biết |
| --- | --- |
| Boot 3.3.x | Commons tương ứng đã có API biểu diễn mới, nhưng không mặc định suy rằng Boot có property trên |
| Boot 3.4.x và 3.5.x | Có property `spring.data.web.pageable.serialization-mode`; cần auto-configuration tương ứng hoạt động |
| Dòng Boot khác hoặc dependency bị ghi đè | Đối chiếu tài liệu property và tích hợp serializer đúng phiên bản đang chạy |

Đối chiếu mã nguồn chính thức: `SpringDataWebProperties` ở [Boot 3.3.0](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-autoconfigure/src/main/java/org/springframework/boot/autoconfigure/data/web/SpringDataWebProperties.java) và [Boot 3.3.13](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-autoconfigure/src/main/java/org/springframework/boot/autoconfigure/data/web/SpringDataWebProperties.java) chưa có `serializationMode`; [Boot 3.4.0](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.4.0/spring-boot-project/spring-boot-autoconfigure/src/main/java/org/springframework/boot/autoconfigure/data/web/SpringDataWebProperties.java) có thuộc tính này.

Vì vậy, lỗi “cấu hình property nhưng JSON vẫn giữ dạng cũ” có thể xuất phát từ lớp tích hợp Boot, dù Commons đã đủ mới để biên dịch annotation `pageSerializationMode`.

## 4. Kích hoạt bằng annotation

Khi ứng dụng chủ động quản lý cấu hình Spring Data web support, có thể dùng:

```java
package example.catalog;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.web.config.EnableSpringDataWebSupport;
import org.springframework.data.web.config.EnableSpringDataWebSupport.PageSerializationMode;

@Configuration
@EnableSpringDataWebSupport(
        pageSerializationMode = PageSerializationMode.VIA_DTO)
public class DataWebRepresentationConfiguration {
}
```

Hoặc static import để viết ngắn hơn:

```java
import static org.springframework.data.web.config.EnableSpringDataWebSupport
        .PageSerializationMode.VIA_DTO;

@Configuration
@EnableSpringDataWebSupport(pageSerializationMode = VIA_DTO)
class DataWebRepresentationConfiguration {
}
```

Đây là hai cách viết thay thế cho cùng một cấu hình, không khai báo đồng thời hai class trùng tên. Đoạn thứ hai dùng lại import `Configuration` và `EnableSpringDataWebSupport` của đoạn đầu.

Class cấu hình phải được ứng dụng nạp vào context phục vụ web. Với MVC cấu hình thủ công, hạ tầng MVC và JSON message converter vẫn phải được thiết lập phù hợp. Annotation này không tự tạo repository, controller hay kết nối kho dữ liệu.

Trong Boot, thêm annotation là quyết định quản lý cấu hình Spring Data web tường minh. Cần xem xét ảnh hưởng đến auto-configuration thay vì thêm vào mọi ứng dụng như một bước bắt buộc.

## 5. Kích hoạt bằng property Boot khi phiên bản hỗ trợ

Với Boot 3.4/3.5 sử dụng auto-configuration phù hợp, cấu hình minh họa:

```yaml
spring:
  data:
    web:
      pageable:
        serialization-mode: via-dto
```

Property được liệt kê trong [danh mục cấu hình Boot 3.4](https://docs.spring.io/spring-boot/3.4/appendix/application-properties/index.html). Mặc định vẫn là `direct`.

Trong mã nguồn [SpringDataWebAutoConfiguration 3.4.0](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.4.0/spring-boot-project/spring-boot-autoconfigure/src/main/java/org/springframework/boot/autoconfigure/data/web/SpringDataWebAutoConfiguration.java), Boot tạo `SpringDataWebSettings` từ giá trị property. Auto-configuration có điều kiện liên quan đến MVC và sự hiện diện của `PageableHandlerMethodArgumentResolver`.

Nếu ứng dụng đã tự tạo resolver, cấu hình web riêng hoặc settings riêng, đường auto-configuration có thể nhường quyền. Khi đó, chỉ thêm property chưa đủ để kết luận mapper thực tế đã chọn `VIA_DTO`.

Nên chọn một nguồn cấu hình rõ ràng:

- Boot auto-configuration còn hoạt động và có property: dùng property.
- Cấu hình Spring Data web do ứng dụng chủ động quản lý: dùng annotation thích hợp.
- Chỉ một số endpoint cần đổi response: cân nhắc bọc DTO tường minh tại các endpoint đó.

Với Boot 3.3.x, có thể dùng annotation khi phù hợp với cấu hình ứng dụng hoặc chọn `new PagedModel<>(page)` tại endpoint. Không dựa vào một property chưa được phiên bản Boot đó cung cấp.

## 6. Ví dụ quan sát JSON

### 6.1. Controller trả Page nhưng implementation là PageImpl

Controller sau tạo dữ liệu cố định để tập trung quan sát serializer, chưa truy vấn kho dữ liệu:

```java
package example.catalog;

import java.util.List;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProductPageDemoController {

    @GetMapping("/products/demo-page")
    public Page<ProductView> demo() {
        List<ProductView> content = List.of(
                new ProductView(101L, "Bàn phím"),
                new ProductView(102L, "Chuột"));

        return new PageImpl<>(
                content,
                PageRequest.of(0, 2),
                5);
    }

    public record ProductView(Long id, String name) {
    }
}
```

Để quan sát qua HTTP, controller phải được nạp cùng một trong các phương án cấu hình ở phần trước. Tổng số `5` là dữ liệu minh họa do code cung cấp; `PageImpl` trong ví dụ không tự thực hiện truy vấn đếm.

Chữ ký Java vẫn là `Page<ProductView>`. Cấu hình serialization quyết định cách đối tượng runtime được ghi thành JSON.

### 6.2. Response khi VIA_DTO hoạt động

Request:

```http
GET /products/demo-page
Accept: application/json
```

Response mong đợi trong cấu hình Jackson thông thường:

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

Thứ tự các field JSON không phải điều client nên phụ thuộc. Hợp đồng cần quan tâm là tên field, cấu trúc, kiểu dữ liệu và ý nghĩa.

| Field | Ý nghĩa |
| --- | --- |
| `content` | Danh sách phần tử có trong trang hiện tại |
| `page.size` | Kích thước trang từ đối tượng `Page` |
| `page.number` | Chỉ số trang từ `Page.getNumber()`, thường bắt đầu từ 0 |
| `page.totalElements` | Tổng số phần tử mà kết quả `Page` cung cấp |
| `page.totalPages` | Tổng số trang mà kết quả `Page` cung cấp |

`content.length` có thể nhỏ hơn `page.size`, chẳng hạn ở trang cuối. Không dùng kích thước mảng hiện tại để thay thế tổng số phần tử.

Các metadata trên được mô hình `PagedModel` lấy từ `Page` nguồn; xem [mã nguồn PagedModel](https://raw.githubusercontent.com/spring-projects/spring-data-commons/3.5.x/src/main/java/org/springframework/data/web/PagedModel.java).

## 7. Bọc PagedModel tường minh tại endpoint

Khi chỉ muốn đổi một endpoint hoặc muốn kiểu response hiện rõ trong Java, có thể trả mô hình bọc trực tiếp:

```java
import org.springframework.data.web.PagedModel;
```

Phương thức thay thế cho `demo()` ở phần trước:

```java
@GetMapping("/products/demo-page")
public PagedModel<ProductView> demo() {
    Page<ProductView> page = new PageImpl<>(
            List.of(
                    new ProductView(101L, "Bàn phím"),
                    new ProductView(102L, "Chuột")),
            PageRequest.of(0, 2),
            5);

    return new PagedModel<>(page);
}
```

Đoạn này sử dụng lại các kiểu và import của controller mẫu; không đăng ký đồng thời hai phương thức có cùng mapping. Với cách bọc tường minh, endpoint đã chọn mô hình biểu diễn mà không cần bật chuyển đổi `PageImpl` toàn cục chỉ để phục vụ endpoint đó.

API `org.springframework.data.web.PagedModel` vẫn yêu cầu Commons từ 3.3. Đây không phải phương án để biên dịch trên một phiên bản cũ hơn chưa có class này.

Cần phân biệt đúng package:

| Kiểu | Vai trò |
| --- | --- |
| `org.springframework.data.web.PagedModel` | Mô hình phân trang đơn giản của Commons, có `content` và metadata `page` |
| `org.springframework.hateoas.PagedModel` | Mô hình hypermedia của Spring HATEOAS, có thể mang liên kết và các kiểu nội dung liên quan |

`VIA_DTO` dùng loại của Commons. Nó không tự thêm `_links`, không tự sinh URL trang kế tiếp và không đòi ứng dụng phải chọn một hợp đồng HAL. Nếu API cần liên kết điều hướng, hãy chọn model và assembler HATEOAS phù hợp; không chỉ thay import theo gợi ý tự động của IDE.

Tài liệu [web support của Commons](https://docs.spring.io/spring-data/commons/reference/3.5/repositories/core-extensions-web.html) trình bày riêng mô hình đơn giản và phần hỗ trợ hypermedia.

## 8. Phương án DTO riêng khi phiên bản hoặc hợp đồng yêu cầu

Nếu Commons chưa có API cần thiết, hoặc API muốn thêm `hasNext`, tên field riêng hay metadata khác, có thể định nghĩa response DTO của ứng dụng.

Ví dụ dưới đây dùng Java 17 và không phụ thuộc `org.springframework.data.web.PagedModel`:

```java
package example.catalog;

import java.util.List;

import org.springframework.data.domain.Page;

public record PageResponse<T>(
        List<T> content,
        PageMetadata page) {

    public static <T> PageResponse<T> from(Page<T> source) {
        PageMetadata metadata = new PageMetadata(
                source.getSize(),
                source.getNumber(),
                source.getTotalElements(),
                source.getTotalPages());

        return new PageResponse<>(source.getContent(), metadata);
    }

    public record PageMetadata(
            int size,
            int number,
            long totalElements,
            int totalPages) {
    }
}
```

Một phương thức controller có thể trả:

```java
PageResponse<ProductView> response = PageResponse.from(page);
return response;
```

`page` ở đây là `Page<ProductView>` đã được service cung cấp. Phương thức chứa đoạn này cần khai báo kiểu trả về tương ứng. Nếu dự án dùng Java cũ không hỗ trợ record, triển khai DTO bằng class và getter.

DTO riêng trao cho ứng dụng quyền kiểm soát schema, đồng thời ứng dụng chịu trách nhiệm duy trì và kiểm tra schema đó. Không cần nâng cấp cả hệ sinh thái chỉ để giữ một hình dạng response đã được DTO riêng biểu diễn rõ ràng.

So sánh ba lựa chọn:

| Lựa chọn | Phạm vi thay đổi | Điểm cần cân nhắc |
| --- | --- | --- |
| `VIA_DTO` qua cấu hình | Các `PageImpl` được serialize qua mapper tích hợp tương ứng | Cần đánh giá ảnh hưởng đến nhiều endpoint |
| `new PagedModel<>(page)` | Endpoint chủ động bọc model | Cần Commons có class này; kiểu response rõ tại controller |
| DTO phân trang của ứng dụng | Endpoint hoặc nhóm API do ứng dụng kiểm soát | Tự thiết kế field, metadata và quy ước tương thích |

Không cần dùng đồng thời cả ba cách cho cùng một response. Chọn cách thể hiện được hợp đồng mà API muốn công bố.

## 9. Phạm vi tác động thực tế

### 9.1. Chuyển biểu diễn PageImpl trong hạ tầng serializer phù hợp

Trong implementation Jackson 2 của Commons 3.5, `PageModule` áp dụng cơ chế bọc cho `PageImpl` khi settings chọn `VIA_DTO`. Xem [SpringDataJacksonConfiguration](https://raw.githubusercontent.com/spring-projects/spring-data-commons/3.5.x/src/main/java/org/springframework/data/web/config/SpringDataJacksonConfiguration.java).

Do đó cần xem kiểu runtime và mapper thực tế:

| Trường hợp | Cách suy luận |
| --- | --- |
| Controller khai báo `Page<T>`, đối tượng thực tế là `PageImpl<T>` | Chế độ có thể áp dụng qua module đã đăng ký |
| Trả `ResponseEntity<Page<T>>` | Phần body vẫn đi qua cơ chế ghi JSON tương ứng |
| Dùng implementation `Page` do ứng dụng tự viết | Không mặc định cho rằng cơ chế nhắm vào `PageImpl` xử lý mọi implementation |
| Trả `Slice<T>` hoặc `List<T>` | Không coi đó là `PageImpl` để tự có metadata tổng |
| Dùng serializer khác hoặc HTTP converter tự cấu hình | Phải kiểm tra tích hợp và output thực tế của đường ghi response đó |

Chỉ tạo `new ObjectMapper()` ở nơi khác rồi serialize một `PageImpl` không chứng minh cấu hình web đang sai: mapper mới có thể chưa nhận module và settings mà ứng dụng web sử dụng.

Ngược lại, test chỉ kiểm tra `Page.getTotalElements()` cũng chưa xác minh được JSON qua HTTP. Cần quan sát đúng mapper hoặc đường response đang phục vụ endpoint.

### 9.2. Không tự biến entity thành DTO của từng phần tử

Nếu repository trả `Page<Product>`, chuyển wrapper sang `PagedModel<Product>` vẫn giữ các phần tử `Product`. Những field được serialize ở từng phần tử còn phụ thuộc kiểu domain, cấu hình Jackson và mapping ứng dụng.

Một luồng ứng dụng thường có dạng:

```java
Page<Product> products = repository.findAll(pageable);

Page<ProductView> result = products.map(
        product -> new ProductView(
                product.getId(),
                product.getName()));

return result;
```

Đây là đoạn minh họa cho phương thức trả `Page<ProductView>`, giả định repository, domain `Product` và `pageable` đã được khai báo phù hợp. Khi `VIA_DTO` hoạt động, wrapper được chuyển khi ghi JSON; nội dung đã được ứng dụng ánh xạ trước đó.

`Page.map(...)` chuyển từng phần tử và giữ thông tin phân trang. Không dùng thao tác lọc bớt phần tử sau khi truy vấn rồi giả định metadata tổng vẫn mô tả đúng tập dữ liệu mới.

Projection ở repository cũng là một lựa chọn khi module lưu trữ và truy vấn hỗ trợ. Chế độ serialization không tự lựa chọn projection, dựng Query by Example hay thay đổi derived query.

### 9.3. Không đổi quy ước đánh số trang đầu vào

Cấu hình `one-indexed-parameters` điều khiển cách resolver đọc tham số HTTP. Metadata của mô hình bọc lấy chỉ số từ `Page`.

Ví dụ, khi đầu vào đánh số từ 1 được bật:

```text
Request page=1
    -> Pageable nội bộ có pageNumber=0
    -> Page nguồn có number=0
    -> JSON page.number=0
```

`VIA_DTO` không tự cộng thêm 1 cho response. Nếu hợp đồng API yêu cầu đầu vào và đầu ra đều bắt đầu từ 1, hãy thiết kế DTO hoặc mô hình biểu diễn đáp ứng quy ước đó một cách tường minh.

### 9.4. Không thay đổi khả năng truy vấn của kho dữ liệu

Serializer nhận kết quả đã có. Nó không tự thực hiện truy vấn đếm, tạo index hay làm repository có thêm phương thức phân trang.

`totalElements` và `totalPages` xuất phát từ `Page` mà ứng dụng cung cấp. Nếu cần trả tổng chính xác, tầng truy vấn phải có khả năng cung cấp tổng theo hợp đồng đã chọn. Khi việc đếm tốn kém hoặc không phù hợp với kho dữ liệu, nên xem xét hợp đồng `Slice`, cursor hoặc mô hình khác thay vì bịa metadata tổng để giống response `Page`.

Các abstraction Repository, CRUD, phân trang và sắp xếp của Commons vẫn phải được dùng theo khả năng thực tế của từng module. Auditing và metadata persistence cũng không được cấu hình lại bởi chế độ ghi JSON.

## 10. Chuyển API đang dùng DIRECT sang VIA_DTO

### 10.1. Đây có thể là thay đổi hợp đồng với client

Nếu client hiện đọc `response.totalElements`, sau khi đổi nó có thể cần đọc `response.page.totalElements`.

| Cách client có thể đang đọc ở response cũ | Hướng xử lý với mô hình mới |
| --- | --- |
| `content` | Vẫn lấy nội dung tại `content` |
| `totalElements` ở cấp gốc | Đọc `page.totalElements` |
| `totalPages` ở cấp gốc | Đọc `page.totalPages` |
| `number` hoặc `size` ở cấp gốc | Đọc trong object `page` |
| `first`, `last`, `numberOfElements` | Không giả định còn có sẵn; thiết kế cách dùng hoặc DTO bổ sung |
| Metadata `sort` hoặc `pageable` của implementation | Không coi là một phần mặc định của model đơn giản |

Các cột về response cũ mô tả những dạng thường gặp, không khẳng định `DIRECT` có một schema cố định.

Cấu hình toàn cục có thể tác động đến nhiều nơi sử dụng cùng mapper. Hãy xác định các endpoint và consumer liên quan trước khi bật trong một API đang được dùng.

### 10.2. Quy trình chuyển đổi có thể áp dụng

1. Xác định phiên bản Commons, Boot và serializer đang thực sự chạy.
2. Ghi nhận schema response mà các client đang sử dụng.
3. Chọn đổi toàn bộ API hoặc áp dụng tường minh cho endpoint/phiên bản API mới.
4. Cập nhật tài liệu schema và mã client theo hợp đồng mới.
5. Kiểm tra response qua HTTP, gồm trang có dữ liệu, trang rỗng và metadata.
6. Triển khai theo chiến lược tương thích đã thống nhất với các consumer.

Nếu cần giữ endpoint cũ, mô hình bọc tường minh ở endpoint mới thường giúp kiểm soát phạm vi chuyển đổi. Việc gán `VIA_DTO` toàn cục rồi kỳ vọng những endpoint cũ vẫn giữ các field implementation cần được xem xét lại.

### 10.3. Tài liệu API và phía nhận JSON

Khi controller vẫn khai báo `Page<ProductView>`, công cụ sinh schema có thể dựa vào kiểu Java thay vì toàn bộ chuyển đổi serializer runtime. Cần kiểm tra tài liệu OpenAPI có mô tả đúng `content` và `page` mà HTTP thực sự trả về hay không.

Trả `PagedModel<ProductView>` hoặc DTO riêng tường minh thường làm ý định ở lớp web dễ thấy hơn. Tuy vậy, schema sinh tự động vẫn nên được đối chiếu với response.

`VIA_DTO` là cấu hình biểu diễn đầu ra. Nó không tự tạo một cơ chế đối xứng để client đọc JSON thành interface `Page<T>` hoặc khởi tạo `PageImpl<T>`. Client nên có DTO nhận dữ liệu tương ứng hoặc cơ chế deserialize được thiết kế riêng.

## 11. Thực hành kiểm tra hợp đồng response

### 11.1. Kiểm tra ví dụ cố định

Với controller demo, gọi `GET /products/demo-page` và quan sát:

| Đường dẫn JSON | Giá trị mong đợi |
| --- | --- |
| `$.content.length` theo cách đọc mảng của công cụ đang dùng | `2` |
| `$.content[0].id` | `101` |
| `$.page.size` | `2` |
| `$.page.number` | `0` |
| `$.page.totalElements` | `5` |
| `$.page.totalPages` | `3` |

Cú pháp lấy độ dài mảng tùy công cụ JSONPath hoặc HTTP client. Điều cần kiểm tra là nội dung có hai phần tử và metadata nằm trong object `page`.

Đồng thời kiểm tra client không còn dựa vào tổng số phần tử ở cấp gốc. So sánh cấu trúc và giá trị thay vì so chuỗi JSON theo thứ tự field.

### 11.2. Trang rỗng và trang vượt phạm vi

Với một kết quả phân trang có `page=0`, `size=2`, tổng số phần tử bằng `0`, mô hình bọc lấy metadata từ `Page` nguồn. Với `PageImpl` có phân trang trong tình huống này, mong đợi `content` rỗng, `totalElements=0` và `totalPages=0`.

Phải phân biệt trường hợp trên với dữ liệu `unpaged`: metadata lấy từ đối tượng nguồn, nên không suy rằng mọi trang rỗng trong mọi chế độ đều giống hệt nhau.

Nếu ứng dụng cho phép yêu cầu một trang vượt phạm vi, serializer không tự chuyển yêu cầu về trang cuối. Chính sách trả trang rỗng, lỗi hoặc cách xử lý khác thuộc ứng dụng và tầng truy vấn.

### 11.3. Kiểm tra đúng context

Một phép kiểm tra hợp đồng hữu ích cần sử dụng cấu hình web và serializer tương ứng với ứng dụng thực tế. Context tối thiểu thiếu module có thể cho hình dạng khác dù code controller giống nhau.

Khi học, có thể lần lượt quan sát:

- `DIRECT` với response hiện tại.
- `VIA_DTO` bằng một nguồn cấu hình rõ ràng.
- `PagedModel` tường minh tại một endpoint.
- DTO riêng khi cần kiểm soát field bổ sung.

Các quan sát này nhằm làm rõ phần biểu diễn. Khả năng repository thực thi phân trang, sort hoặc truy vấn đếm vẫn cần được kiểm tra riêng trong luồng dữ liệu.

## 12. Lỗi thường gặp và cách xử lý

| Biểu hiện | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Không biên dịch được `pageSerializationMode` | Commons thực tế cũ hơn mốc hỗ trợ | Đối chiếu dependency được resolve; chọn DTO riêng hoặc nâng cả nền tảng phù hợp |
| Không tìm thấy `org.springframework.data.web.PagedModel` | Dùng phiên bản chưa có class hoặc import nhầm | Kiểm tra mốc 3.3 và package |
| Có property nhưng JSON không đổi | Boot chưa hỗ trợ property, auto-configuration đã nhường quyền hoặc mapper không có tích hợp | Kiểm tra lần lượt phiên bản, nguồn cấu hình và HTTP converter |
| DTO wrapper mới xuất hiện nhưng entity vẫn lộ field không mong muốn | Chỉ đổi lớp bọc, chưa chọn DTO cho từng phần tử | Dùng projection hoặc ánh xạ `Page.map(...)` |
| Client không đọc được tổng số phần tử | Client còn đọc field cấp gốc của response cũ | Cập nhật hợp đồng sang object `page` |
| Response không có `_links` | Đang dùng model đơn giản của Commons | Chọn HATEOAS khi hợp đồng cần hypermedia |
| Request bắt đầu từ trang 1 nhưng response là 0 | Cấu hình đầu vào và metadata đầu ra có vai trò riêng | Thiết kế DTO nếu API yêu cầu số trang đầu ra bắt đầu từ 1 |
| `Slice` không có metadata tổng giống Page | Đã chọn hợp đồng không cung cấp tổng | Giữ biểu diễn phù hợp thay vì tạo tổng giả |
| Test serialize khác với HTTP thực tế | Dùng mapper khác hoặc context thiếu module | Kiểm tra đường message conversion phục vụ endpoint |

Trước khi chọn `VIA_DTO`, hãy xác định ba điểm: phiên bản nào cung cấp API, lớp cấu hình nào đưa lựa chọn vào serializer, và client sẽ đọc schema nào. Từ đó có thể áp dụng biểu diễn phân trang ổn định mà vẫn giữ đúng hợp đồng truy vấn của từng kho dữ liệu.

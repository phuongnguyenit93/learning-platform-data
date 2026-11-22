# Phân trang, sắp xếp, bộ lọc và hợp đồng danh sách kết quả trong Spring MVC

## 1. Bài toán: một endpoint trả danh sách cần cam kết điều gì?

Giả sử client gọi API danh sách sách:

~~~http
GET /api/books?page=0&size=2&sort=createdAt,desc&category=spring&available=true HTTP/1.1
Accept: application/json
~~~

Một thiết kế hợp lý cần trả lời đồng thời:
- **Bộ lọc (filtering):** những bản ghi nào đủ điều kiện xuất hiện, cách so khớp, cách diễn giải tham số vắng mặt hoặc rỗng?
- **Sắp xếp (sorting):** bản ghi nào đứng trước, có thứ tự mặc định không, có một khóa phân xử cuối để thứ tự ổn định không?
- **Phân trang (pagination):** client xin trang số mấy, số phần tử tối đa, trang đầu tính từ 0 hay 1, còn trang tiếp không?
- **Hợp đồng kết quả (list response contract):** dữ liệu, metadata, tổng phần tử, hướng điều hướng và lỗi có dạng JSON nào, ổn định qua các phiên bản không?
- **Giới hạn tài nguyên:** size tối đa bao nhiêu; ai giới hạn offset lớn, danh sách rỗng và chi phí đếm tổng?
- **Tính nhất quán:** tổng số bản ghi và nội dung trang được quan sát tại thời điểm nào; dữ liệu thay đổi giữa các request làm trang dịch chuyển ra sao?

Trong Spring MVC, `@RestController` và `@RequestParam` giải quyết phần **nhận HTTP input và tạo HTTP response**; Spring Data (nếu có) hỗ trợ `Pageable`/`Sort`/`Page` và repository query. **Spring MVC thuần không tự truy vấn database hay tự quy định toàn bộ cấu trúc JSON danh sách.** Hợp đồng là quyết định của API, cần định nghĩa và kiểm thử.

Ví dụ bài học dùng Java 17+, Spring Boot 3.x / Spring Framework 6.x. Có một ứng dụng runnable **không phụ thuộc database** để phân biệt rõ contract HTTP; phần sau chỉ ra cách nối Spring Data JPA và những vấn đề khi dữ liệu rất lớn.

## 2. Thiết kế URL trước khi viết controller

### 2.1. Một hợp đồng query minh bạch

Chọn endpoint:

~~~text
GET /api/books
  ?page=0
  &size=20
  &sort=createdAt,desc
  &category=spring
  &available=true
  &q=security
~~~

Định nghĩa chính thức cho ví dụ:

| Tham số | Kiểu | Mặc định/ý nghĩa | Giới hạn hoặc quy tắc |
| --- | --- | --- | --- |
| `page` | số nguyên | `0`, **zero-based** | Không âm |
| `size` | số nguyên | `20` | Từ 1 đến 50 |
| `sort` | chuỗi `field,direction` | `createdAt,desc` | `field ∈ {id,title,createdAt}`, `direction ∈ {asc,desc}` |
| `category` | chuỗi tùy chọn | Không lọc | So sánh không phân biệt hoa/thường, khớp cả giá trị |
| `available` | boolean tùy chọn | Không lọc | `true` hoặc `false` theo converter |
| `q` | chuỗi tùy chọn | Không lọc | Chuỗi con trong `title`, không phân biệt hoa/thường |

Đây là **hợp đồng do ứng dụng tự định nghĩa**. Không mặc nhiên gắn “size mặc định 20” hay sort format trên với mọi ứng dụng Spring: cấu hình Spring Data web và annotation `@PageableDefault` có thể khác.

Trong URL, các tham số cùng cấp thường kết hợp theo logic **AND**: ví dụ `category=spring&available=true` chỉ lấy sách vừa thuộc spring vừa đang available. Với tìm kiếm `q`, ta ghi rõ thuộc tính nào được tìm; đừng để client tin rằng `q` tìm trong mọi trường nếu server chỉ tìm tên.

Các tham số đầu vào thuộc **query string**, không phải JSON request body. Phần danh sách không cần `POST` chỉ để có bộ lọc đơn giản; với filter rất phức tạp và payload lớn, có thể định nghĩa endpoint search riêng, nhưng cần hợp đồng HTTP/cache rõ ràng.

### 2.2. Tránh nhập nhằng: index bắt đầu từ 0 hay 1?

Với zero-based:
- `page=0` là trang đầu.
- `page=1` là trang thứ hai.
- `size=2` là tối đa hai phần tử mỗi trang.
- Trong thuật toán offset, vị trí bắt đầu là `page × size`, ví dụ `page=2&size=10` bắt đầu từ offset 20.

Có API dùng one-based (`page=1` là trang đầu). Cả hai được nếu **công bố rõ** và response trả lại index tương ứng; không đổi quy ước trong một API hiện hữu mà không version/migration. `PageRequest.of(page,size)` của Spring Data dùng **zero-based**, dù web resolver có thể được cấu hình nhận one-based ở biên HTTP.

### 2.3. Giới hạn size và không cho request tùy ý ngốn tài nguyên

Giá trị `size=1000000` không được phép chỉ vì client gửi được một số nguyên lớn. Áp dụng:
- Size tối thiểu 1; đừng chia cho 0.
- Size tối đa được công bố, trong ví dụ là 50.
- Page không âm; tính `page × size` bằng kiểu `long` để tránh overflow `int`.
- Giới hạn quyền và số lượng request bằng API gateway/rate limiting khi cần.
- Cân nhắc giới hạn độ dài query, số điều kiện lọc, số cột sort, độ sâu offset; tránh wildcard/filter vô hạn.

**Chính sách lỗi của bài:** tham số đã parse nhưng vi phạm hợp đồng (size=0, field sort không có trong allowlist) → HTTP `400 Bad Request` kèm mã lỗi rõ nghĩa. Lỗi chuyển chuỗi `page=abc` sang `int` cũng thường được Spring MVC trả 400 trước khi vào method.

## 3. Phân trang theo offset: thuật toán, metadata và giới hạn

### 3.1. Phân trang phải dựa trên kết quả đã lọc và sắp xếp

Thứ tự xử lý về mặt ngữ nghĩa:

~~~text
Data source
   │
   ▼
Lọc theo category, available, q
   │
   ▼
Sắp xếp theo khóa được cho phép
   │
   ▼
Thêm khóa phân xử ổn định (ví dụ id)
   │
   ▼
Tính totalElements / totalPages nếu contract cần
   │
   ▼
Lấy cửa sổ offset..offset+size
   │
   ▼
Map entity/domain → response DTO
   │
   ▼
Trả items + page metadata + sort + filters
~~~

Nếu phân trang **trước khi lọc**, một trang có thể nhận rất ít kết quả dù các trang khác vẫn chứa bản ghi phù hợp. Nếu không có thứ tự rõ ràng, database có thể trả hai trang chồng lấn hoặc bỏ sót bản ghi khi execution plan thay đổi.

Với truy vấn SQL, ý tưởng (không phải câu SQL có thể áp cho mọi dialect) là:

~~~sql
SELECT id, title, category, created_at, available
FROM books
WHERE (:category IS NULL OR category = :category)
  AND (:available IS NULL OR available = :available)
ORDER BY created_at DESC, id ASC
LIMIT :size OFFSET :offset;
~~~

Đoạn SQL chỉ minh họa phép lọc/sort/offset. Với production nên tạo SQL có điều kiện động hoặc query builder tương ứng để tối ưu index; nhiều điều kiện `OR :param IS NULL` có thể làm query planner khó tối ưu. **Không tự nối input của client vào `ORDER BY`**: phải map tên sort từ allowlist sang thuộc tính/cột hợp lệ.

### 3.2. Công thức trang

Nếu số bản ghi phù hợp là `totalElements` và `size > 0`:

~~~text
offset      = page * size
totalPages  = totalElements == 0 ? 0 : ceil(totalElements / size)
hasNext     = page + 1 < totalPages
hasPrevious = page > 0 (chính sách có thể xét thêm totalElements)
~~~

Để tránh số thực và overflow, Java có thể tính `totalPages = (totalElements == 0 ? 0 : 1 + (totalElements - 1) / size)` với `long` phù hợp. API phải nhất quán ý nghĩa `totalPages` khi danh sách trống: trong ví dụ này **bằng 0**, `items=[]` và `totalElements=0`.

Ví dụ có 21 kết quả, size 10: `totalPages=3`, page 0 có 10, page 1 có 10, page 2 có 1. Trang `page=3` nằm ngoài phạm vi. Có thể chọn **200 với `items=[]`** hoặc **404/400** tùy hợp đồng sản phẩm; ở ví dụ này chọn **200 và trang rỗng**, giữ tổng số bản ghi và index requested để client tự quyết định quay lại trang trước.

### 3.3. Phần tử được trả khác với kích thước yêu cầu

- `size`: số phần tử **tối đa** client yêu cầu trên một trang.
- `numberOfElements`: số phần tử **thực sự** trong response hiện tại; có thể 0 hoặc nhỏ hơn size.
- `totalElements`: tổng phần tử **đáp ứng filter** (không phải tổng dữ liệu trong bảng).
- `totalPages`: số trang của tập **đã lọc** với size được yêu cầu.

Không dùng `items.length` thay `totalElements` khi giao diện cần tổng số bản ghi. Ngược lại, nếu API chỉ cần nút Next và dữ liệu quá lớn, việc tính `totalElements` có thể không đáng chi phí.

## 4. Sắp xếp đúng: allowlist, nhiều khóa và thứ tự ổn định

### 4.1. Cột nào được phép sort?

Một API không nên để client chọn tùy ý mọi property của entity. Ví dụ public contract cho phép:
- `id`: định danh tăng theo hệ thống demo.
- `title`: tên hiển thị.
- `createdAt`: thời điểm tạo.

Các property nội bộ như `passwordHash`, `internalScore`, `tenantId`, hoặc những phép join tốn kém không được tự động trở thành lựa chọn sort. Trong Spring Data, `Sort.Order` mang tên property, nhưng **resolver không phải cơ chế bảo mật/allowlist cho ứng dụng**; cần xác nhận lựa chọn client có hợp lệ rồi chuyển tới repository.

Nếu cần giữ API field name độc lập entity field name, dùng mapping tường minh:

~~~text
API "createdAt" → entity property "createdAt"
API "title"     → entity property "title"
API "id"        → entity property "id"
Khác ba lựa chọn  → 400 BAD_QUERY
~~~

### 4.2. Vì sao phải có khóa phụ phân xử?

Giả sử `ORDER BY created_at DESC` và ba sách có cùng timestamp. Database được quyền trả ba bản ghi cùng khóa theo thứ tự bất kỳ. Khi dùng `LIMIT/OFFSET`, hai request liên tiếp có thể phân trang không ổn định. Dùng:

~~~sql
ORDER BY created_at DESC, id ASC
~~~

`id` unique giúp tạo **thứ tự toàn phần** cho cùng snapshot dữ liệu. Chú ý: khóa phụ ổn định giải quyết tie trong một tập dữ liệu; nó **không xóa** vấn đề thêm/xóa bản ghi giữa hai lần lấy trang offset.

Khi client sort `title,asc`, ví dụ giữ mặc định phụ `id ASC`. Khi muốn hỗ trợ nhiều sort field của client, hãy công bố rõ thứ tự ưu tiên: `sort=createdAt,desc&sort=id,asc` trong Spring Data web thường thể hiện khóa thứ nhất rồi khóa thứ hai. **Ví dụ runnable bên dưới chủ ý chỉ hỗ trợ một trường sort chính**, tự thêm id ASC để đơn giản hóa kiểm thử.

### 4.3. Chữ hoa, dấu tiếng Việt, NULL và time zone

Thứ tự xếp chuỗi phụ thuộc collation của database và đối chiếu chữ hoa/thường; `String.CASE_INSENSITIVE_ORDER` trong Java không tương đương mọi collation SQL. Nếu API yêu cầu quy tắc tiếng Việt, phải quyết định locale/collation ở tầng lưu trữ và kiểm thử với dữ liệu dấu. Không hứa thứ tự giống nhau giữa Java in-memory, PostgreSQL/MySQL và client JavaScript.

Với thời gian, lưu `Instant`/UTC ở tầng dữ liệu nếu đó là timestamp tuyệt đối, dùng ISO-8601 có offset/UTC ở HTTP contract, xác định cách so sánh. Với nullable sort keys, công bố NULLS FIRST/LAST nếu client cần ổn định; thêm unique tie-breaker và index tương ứng.

## 5. Bộ lọc: semantics, null, tìm kiếm và bảo mật

### 5.1. Cần phân biệt không gửi, gửi rỗng và gửi giá trị

Ba request:

~~~text
GET /api/books
GET /api/books?category=
GET /api/books?category=spring
~~~

Có thể mang ba ý nghĩa tùy contract. Trong ví dụ này, `category` null hoặc chỉ whitespace đều được chuẩn hóa thành “không lọc”; `category=spring` thì lọc chính xác chuỗi category, không phân biệt hoa/thường.

Với `available`: `null` = không lọc, `true` = chỉ có hàng available, `false` = chỉ có hàng unavailable. Không dùng primitive `boolean` với default `false` nếu cần phân biệt **vắng mặt** và **chỉ lấy false**.

Với `q`: sau trim, tìm chuỗi con trên `title`, không phân biệt hoa/thường. Đây là phép tìm đơn giản cho demo, **không tự động là full-text search**, fuzzy search, tokenizer hoặc bỏ dấu tiếng Việt.

### 5.2. Filter nào kết hợp AND, filter nào OR?

Nếu hỗ trợ `category=java&category=spring`, cần ghi rõ semantics: OR giữa hai giá trị category, nhưng AND với `available=true` chẳng hạn. Ví dụ runnable chỉ nhận **một category**, vì mặc định nhiều tham số trùng tên trong HTTP có thể được resolver tổng hợp theo cách không mong muốn khi binding sang `String`.

Quy tắc hiển thị trên UI phải khớp backend: tổng số bản ghi, số trang và sort đều tính **trong tập sau khi áp dụng toàn bộ filters**. Khi user thay filter, UI thường nên quay về page 0 để không đứng ở trang vượt phạm vi mới.

### 5.3. Chống query abuse và tránh mở dữ liệu không có quyền

Input do client gửi không đáng tin: cần kiểm tra giá trị hợp lệ, kích thước filter, số lượng điều kiện, allowlist sort, và cấu hình timeout/index. **Filter quyền truy cập/tenant** phải do server xác định từ principal/context và luôn được áp dụng trong repository query, không tin tham số client như `tenantId=...` để quyết định quyền.

Khi truy vấn database, dùng parameter binding của JPA/PreparedStatement/DSL thay vì nội suy các giá trị lọc thành SQL. Đừng ghép `ORDER BY ` + raw sort field từ client. SQL injection không phải rủi ro duy nhất: sort theo cột nội bộ hoặc join quá tốn kém cũng gây tổn hại hiệu năng và lộ cấu trúc.

## 6. Định nghĩa hợp đồng JSON danh sách kết quả

Một JSON envelope rõ nghĩa giúp frontend không phải đoán thông tin từ framework:

~~~json
{
  "items": [
    {"id": 106, "title": "Testing Spring", "category": "spring", "createdAt": "2025-02-15", "available": false},
    {"id": 105, "title": "Spring Security", "category": "spring", "createdAt": "2024-06-01", "available": true}
  ],
  "page": {
    "number": 0,
    "size": 2,
    "numberOfElements": 2,
    "totalElements": 4,
    "totalPages": 2,
    "first": true,
    "last": false,
    "hasNext": true,
    "hasPrevious": false
  },
  "sort": {"field": "createdAt", "direction": "desc"},
  "filters": {"q": null, "category": "spring", "available": null}
}
~~~

Đây là **hợp đồng do bài học tự định nghĩa**, không phải JSON mặc định của `Page<T>`. Chính vì thế controller nên map dữ liệu ra DTO/envelope riêng.

Các điểm cần thống nhất:
- `items` **luôn là mảng**, kể cả không có phần tử. Tránh `null` hoặc vắng field không có lý do.
- `page.number` dùng zero-based như query.
- `totalElements` là tổng trên tập đã lọc, không phải toàn catalog.
- `totalPages` bằng 0 khi `totalElements=0` trong hợp đồng này.
- `first` / `last` dựa trên quy ước của API. Có thể đặt cả hai `true` cho empty dataset ở page 0, nếu lựa chọn này được ghi rõ.
- `sort` trả lại sort **đã xác nhận và chuẩn hóa**; `filters` trả lại điều kiện thực tế.
- Với `available=false`, phải giữ boolean `false`, không nhầm với filter không có (`null`).

Một response trang ngoài phạm vi vẫn trả HTTP **200** và:

~~~json
{
  "items": [],
  "page": {
    "number": 10, "size": 2, "numberOfElements": 0,
    "totalElements": 4, "totalPages": 2,
    "first": false, "last": true,
    "hasNext": false, "hasPrevious": true
  },
  "sort": {"field": "createdAt", "direction": "desc"},
  "filters": {"q": null, "category": "spring", "available": null}
}
~~~

`last=true` trong trang out-of-range thể hiện “không còn trang kế tiếp”, **không có nghĩa page 10 là trang hợp lệ cuối cùng**. Vì vậy frontend nên dựa thêm `totalPages` khi render link. Có ứng dụng chọn 404 cho page out-of-range; nên xác định chính sách và test, không thay đổi ngầm khi refactor.

### 6.1. Có nên trả `Page<Entity>` trực tiếp?

Spring Data `Page<T>` hữu ích **trong Java application/service/repository**; nhưng việc serialize trực tiếp một `PageImpl` thành JSON có thể khiến frontend phụ thuộc vào chi tiết implementation của thư viện. Spring Data có cảnh báo về tính ổn định của format này; từ Spring Data 3.3 có `org.springframework.data.web.PagedModel` và `PageSerializationMode.VIA_DTO` làm một lựa chọn representation ổn định hơn.

Những phương án hợp lý:
1. **Tự thiết kế DTO envelope** như ví dụ, kiểm soát tuyệt đối tên field/compatibility.
2. Dùng `PagedModel` / `VIA_DTO` khi format chuẩn của Spring Data đáp ứng contract, kiểm tra version và field shape thực tế.
3. Dùng Spring HATEOAS khi muốn navigation links theo hypermedia, thay vì tự chế nhiều URL và đoán link.

Không assume `Page<T>` phải luôn xuất ra trường `content` hoặc `pageable` như nhau qua mọi Spring Data release. Hãy snapshot/test JSON API công khai trước khi nâng cấp dependency.

### 6.2. Đưa link điều hướng hay chỉ metadata?

Với REST list contract, có thể bổ sung:

~~~json
{
  "links": {
    "self": "/api/books?page=0&size=2&sort=createdAt%2Cdesc&category=spring",
    "next": "/api/books?page=1&size=2&sort=createdAt%2Cdesc&category=spring"
  }
}
~~~

Trên đây là **fragment minh họa thêm trường `links`**; không phải response runnable bên dưới. Khi tạo links, phải giữ đủ filters, sort và size; URL-encode đúng, không tin raw user-supplied Host nếu tạo absolute links sau reverse proxy. Nếu `hasNext=false`, có thể bỏ `next` thay vì đặt đường dẫn sai.

## 7. Ví dụ runnable: Spring Boot REST catalog dùng danh sách trong bộ nhớ

Để kiểm tra HTTP semantics độc lập với database, ví dụ sau dùng sáu bản ghi cố định và thực hiện filter → sort → page. Trong môi trường thật, chuyển bộ lọc/sort/page xuống database (tránh fetch toàn bộ rows rồi sort trong heap).

Cấu trúc:

~~~text
catalog-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/catalog/
    │   ├── CatalogApplication.java
    │   └── web/
    │       ├── BookController.java
    │       ├── BookCatalogService.java
    │       └── CatalogErrorHandler.java
    └── test/java/com/example/catalog/web/
        └── BookControllerTest.java
~~~

### 7.1. Gradle và Spring Boot

`settings.gradle`:

~~~groovy
rootProject.name = 'catalog-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Không cần `spring-boot-starter-data-jpa` trong ví dụ này; pagination là thuật toán của service trong bộ nhớ. Điều này giúp thấy `@RequestParam` và JSON DTO hoạt động hoàn toàn bằng Spring MVC. Project Gradle cần wrapper thích hợp, ví dụ Gradle 8.x chạy với Java 17.

`src/main/java/com/example/catalog/CatalogApplication.java`:

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

### 7.2. Controller: định nghĩa contract ở HTTP boundary

`src/main/java/com/example/catalog/web/BookController.java`:

~~~java
package com.example.catalog.web;

import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/books")
public class BookController {

    private final BookCatalogService service;

    public BookController(BookCatalogService service) {
        this.service = service;
    }

    @GetMapping
    public PageResponse<BookItem> list(
            @RequestParam(name = "page", defaultValue = "0") int page,
            @RequestParam(name = "size", defaultValue = "20") int size,
            @RequestParam(name = "sort", defaultValue = "createdAt,desc") String sort,
            @RequestParam(name = "category", required = false) String category,
            @RequestParam(name = "available", required = false) Boolean available,
            @RequestParam(name = "q", required = false) String q) {

        return service.find(page, size, sort, category, available, q);
    }

    public record BookItem(
            long id, String title, String category,
            String createdAt, boolean available) {
    }

    public record PageMeta(
            int number, int size, int numberOfElements,
            long totalElements, long totalPages,
            boolean first, boolean last, boolean hasNext, boolean hasPrevious) {
    }

    public record SortMeta(String field, String direction) {
    }

    public record FilterMeta(String q, String category, Boolean available) {
    }

    public record PageResponse<T>(
            List<T> items, PageMeta page,
            SortMeta sort, FilterMeta filters) {
    }
}
~~~

Ở đây:
- `@RestController` serialize `PageResponse` bằng Jackson thành JSON.
- `@RequestParam` nhận thông tin HTTP và chuyển `page`/`size` thành `int`, `available` thành `Boolean`.
- Controller chỉ điều phối. Service chịu trách nhiệm validate chính sách page/size/sort, normalize filter, chọn dữ liệu và đóng metadata.
- Các record định nghĩa **JSON response contract** cụ thể, không expose repository entity hoặc framework internals.
- `PageMeta.totalElements`/`totalPages` dùng `long` để phù hợp dataset lớn về mặt JSON; demo in-memory hiển nhiên nhỏ.

### 7.3. Service: lọc → sort → phân trang → DTO

`src/main/java/com/example/catalog/web/BookCatalogService.java`:

~~~java
package com.example.catalog.web;

import com.example.catalog.web.BookController.BookItem;
import com.example.catalog.web.BookController.FilterMeta;
import com.example.catalog.web.BookController.PageMeta;
import com.example.catalog.web.BookController.PageResponse;
import com.example.catalog.web.BookController.SortMeta;
import java.time.LocalDate;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import org.springframework.stereotype.Service;

@Service
public class BookCatalogService {

    private record Book(
            long id, String title, String category,
            LocalDate createdAt, boolean available) {
    }

    private static final List<Book> BOOKS = List.of(
            new Book(101, "Java Basics", "java",
                    LocalDate.parse("2023-05-01"), true),
            new Book(102, "Spring MVC", "spring",
                    LocalDate.parse("2024-01-10"), true),
            new Book(103, "Spring Data", "spring",
                    LocalDate.parse("2024-03-12"), false),
            new Book(104, "Java Concurrency", "java",
                    LocalDate.parse("2024-05-20"), true),
            new Book(105, "Spring Security", "spring",
                    LocalDate.parse("2024-06-01"), true),
            new Book(106, "Testing Spring", "spring",
                    LocalDate.parse("2025-02-15"), false)
    );

    private record SortSelection(String field, String direction) {
    }

    public PageResponse<BookItem> find(
            int page, int size, String rawSort,
            String category, Boolean available, String q) {

        if (page < 0) {
            throw new IllegalArgumentException("page must be >= 0");
        }
        if (size < 1 || size > 50) {
            throw new IllegalArgumentException("size must be between 1 and 50");
        }

        SortSelection sort = parseSort(rawSort);
        String categoryFilter = normalize(category);
        String qFilter = normalize(q);

        Comparator<Book> primary = switch (sort.field()) {
            case "id" -> Comparator.comparingLong(Book::id);
            case "title" ->
                    Comparator.comparing(Book::title, String.CASE_INSENSITIVE_ORDER);
            case "createdAt" -> Comparator.comparing(Book::createdAt);
            default -> throw new IllegalStateException("Unexpected sort field");
        };

        if ("desc".equals(sort.direction())) {
            primary = primary.reversed();
        }

        // ID duy nhất là tie-breaker để thứ tự xác định.
        Comparator<Book> order = primary.thenComparingLong(Book::id);

        List<Book> matched = BOOKS.stream()
                .filter(book -> categoryFilter == null
                        || book.category().equalsIgnoreCase(categoryFilter))
                .filter(book -> available == null
                        || book.available() == available)
                .filter(book -> qFilter == null
                        || book.title().toLowerCase(Locale.ROOT)
                                .contains(qFilter.toLowerCase(Locale.ROOT)))
                .sorted(order)
                .toList();

        long totalElements = matched.size();
        long totalPages = totalElements == 0
                ? 0 : 1 + (totalElements - 1) / size;
        long start = (long) page * size;

        List<BookItem> items;
        if (start >= totalElements) {
            items = List.of();
        } else {
            int from = (int) start;
            int to = (int) Math.min(totalElements, start + size);
            items = matched.subList(from, to).stream()
                    .map(book -> new BookItem(
                            book.id(), book.title(), book.category(),
                            book.createdAt().toString(), book.available()))
                    .toList();
        }

        boolean hasNext = (long) page + 1 < totalPages;
        boolean hasPrevious = page > 0 && totalElements > 0;
        PageMeta pageMeta = new PageMeta(
                page, size, items.size(),
                totalElements, totalPages,
                page == 0,
                !hasNext,
                hasNext,
                hasPrevious);

        return new PageResponse<>(
                items,
                pageMeta,
                new SortMeta(sort.field(), sort.direction()),
                new FilterMeta(qFilter, categoryFilter, available));
    }

    private static String normalize(String text) {
        if (text == null || text.isBlank()) {
            return null;
        }
        return text.trim();
    }

    private static SortSelection parseSort(String raw) {
        String[] parts = raw.split(",", -1);
        if (parts.length != 2) {
            throw new IllegalArgumentException(
                    "sort must have format field,direction");
        }

        String field = parts[0].trim();
        String direction = parts[1].trim().toLowerCase(Locale.ROOT);
        if (!Set.of("id", "title", "createdAt").contains(field)
                || !Set.of("asc", "desc").contains(direction)) {
            throw new IllegalArgumentException(
                    "sort field or direction is not supported");
        }
        return new SortSelection(field, direction);
    }
}
~~~

**Giải thích các lựa chọn có chủ đích:**
1. `BOOKS` là fixture bất biến: dễ tái hiện kết quả. Production phải filter/sort/page **trong database** thay vì kéo toàn bộ bảng vào JVM.
2. `Boolean available` phân biệt `null` (không lọc) với `false`.
3. `normalize` biến blank và whitespace thành không lọc, nhưng không tự chuẩn hóa nội dung của `category` trong metadata thành chữ thường; so khớp dữ liệu dùng `equalsIgnoreCase`.
4. `parseSort` kiểm tra field/direction theo allowlist. Có sort thứ hai tự động `id ASC` để kết quả xác định khi giá trị sort chính bằng nhau.
5. `start` dùng `long` để tránh overflow phép nhân `int`. Chỉ cast về `int` khi `start < matched.size()`, an toàn cho `List` trong JVM.
6. Khi không có dữ liệu, `totalPages=0`, `first=true` nếu page=0 và `last=true` vì không còn trang sau.
7. `hasPrevious` là metadata cho hành vi client trong ví dụ; ở page ngoài phạm vi mà dữ liệu vẫn tồn tại, vẫn có thể quay về page trước.

Hàm `String.CASE_INSENSITIVE_ORDER` phục vụ Java demo; database production phải có collation/sort key tương thích với API contract. Nếu có nhiều records đồng timestamp, tie-breaker ID duy nhất giải quyết trùng thứ tự.

### 7.4. Trả lỗi input rõ ràng

`src/main/java/com/example/catalog/web/CatalogErrorHandler.java`:

~~~java
package com.example.catalog.web;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class CatalogErrorHandler {

    public record ErrorBody(String code, String message) {
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<ErrorBody> badQuery(IllegalArgumentException ex) {
        return ResponseEntity.badRequest()
                .body(new ErrorBody("BAD_QUERY", ex.getMessage()));
    }
}
~~~

Đây là handler **cho các lỗi IllegalArgumentException do service ném**; ứng dụng production nên dùng exception domain cụ thể (ví dụ `InvalidListQueryException`), tránh biến mọi `IllegalArgumentException` từ bug logic thành 400.

Lỗi `page=xyz` trước khi vào service là lỗi chuyển kiểu của Spring MVC; nó thường trả **400** theo cơ chế exception mặc định, không phải JSON `ErrorBody` do method trên tạo. Muốn mọi lỗi cùng một schema, override các hook của `ResponseEntityExceptionHandler` hoặc dùng advice riêng cho conversion/binding và test.

**Lưu ý bảo mật:** không nên luôn trả raw exception message nếu exception có thể chứa SQL, internal identifier hay dữ liệu bí mật. Trong ví dụ, message do allowlist/validation tạo và không chứa payload nhạy cảm; production nên dùng message code an toàn và correlation ID.

## 8. Gọi thử API và hiểu kết quả

Chạy trong project có Gradle wrapper và Java 17:

~~~bash
./gradlew bootRun
~~~

Trên Windows có thể chạy `.\gradlew.bat bootRun`. Vì đây là ứng dụng Spring Boot, không chạy đơn lẻ bằng `javac BookController.java` mà thiếu classpath Spring.

### 8.1. Trang đầu cho category spring

~~~bash
curl -s 'http://localhost:8080/api/books?page=0&size=2&category=spring'
~~~

Sort mặc định `createdAt,desc`. Bốn sách spring theo thứ tự là:
1. ID `106` — Testing Spring (2025-02-15).
2. ID `105` — Spring Security (2024-06-01).
3. ID `103` — Spring Data (2024-03-12).
4. ID `102` — Spring MVC (2024-01-10).

Vì size=2, trang đầu có **106, 105**; `totalElements=4`, `totalPages=2`, `hasNext=true`, `numberOfElements=2`.

~~~json
{
  "items": [
    {"id":106,"title":"Testing Spring","category":"spring","createdAt":"2025-02-15","available":false},
    {"id":105,"title":"Spring Security","category":"spring","createdAt":"2024-06-01","available":true}
  ],
  "page": {
    "number":0,"size":2,"numberOfElements":2,
    "totalElements":4,"totalPages":2,
    "first":true,"last":false,"hasNext":true,"hasPrevious":false
  },
  "sort":{"field":"createdAt","direction":"desc"},
  "filters":{"q":null,"category":"spring","available":null}
}
~~~

### 8.2. Trang hai và lọc thêm available

~~~bash
curl -s 'http://localhost:8080/api/books?page=1&size=2&category=spring'
curl -s 'http://localhost:8080/api/books?page=0&size=2&category=spring&available=true'
~~~

Request đầu trả IDs `103`, `102`, `hasNext=false`, `hasPrevious=true`. Request thứ hai chỉ giữ IDs `105`, `102`; `totalElements=2` và `totalPages=1`. **Không giữ total=4 sau khi áp thêm filter available**.

### 8.3. Đổi sort không thay số phần tử khớp bộ lọc

~~~bash
curl -s 'http://localhost:8080/api/books?page=0&size=2&category=spring&sort=title,asc'
~~~

Thứ tự tiêu đề theo sort Java demo:
- `Spring Data` (103).
- `Spring MVC` (102).
- `Spring Security` (105).
- `Testing Spring` (106).

Page 0 nhận `103,102`. `totalElements` vẫn là 4: sort **đổi thứ tự**, không thêm/bớt bản ghi.

### 8.4. Trang vượt phạm vi và bộ lọc không có kết quả

~~~bash
curl -s 'http://localhost:8080/api/books?page=10&size=2&category=spring'
curl -s 'http://localhost:8080/api/books?q=NoSuchBook'
~~~

Đầu tiên trả HTTP **200**, `items=[]`, `number=10`, `totalElements=4`, `totalPages=2`. Thứ hai trả HTTP **200**, `items=[]`, `totalElements=0`, `totalPages=0`, vì không có sách tên chứa NoSuchBook.

Đây là trạng thái hợp lệ với một truy vấn danh sách. Trả 404 cho “không tìm thấy bản ghi đơn” (`GET /api/books/{id}`) là vấn đề khác với danh sách trống.

### 8.5. Giá trị sai contract

~~~bash
curl -i 'http://localhost:8080/api/books?page=-1'
curl -i 'http://localhost:8080/api/books?size=0'
curl -i 'http://localhost:8080/api/books?size=1000'
curl -i 'http://localhost:8080/api/books?sort=secret,asc'
curl -i 'http://localhost:8080/api/books?page=abc'
~~~

Bốn request đầu gây `IllegalArgumentException` từ service và được advice trả **400** với code `BAD_QUERY`. Request cuối sai chuyển kiểu `int`, Spring MVC cũng thường trả **400** nhưng body có thể khác vì đi qua exception handler mặc định.

**Không lẳng lặng clamp size=1000 thành 50 nếu hợp đồng yêu cầu báo 400.** Một sản phẩm khác có thể chủ động clamp; việc quan trọng là client biết chính sách và response báo lại size được thực thi.

## 9. Kiểm thử MockMvc cho toàn bộ hợp đồng danh sách

`src/test/java/com/example/catalog/web/BookControllerTest.java`:

~~~java
package com.example.catalog.web;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BookControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void filtersBeforePagingAndReturnsTotalForFilteredSet() throws Exception {
        mvc.perform(get("/api/books")
                        .param("page", "0")
                        .param("size", "2")
                        .param("category", "spring"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items.length()").value(2))
                .andExpect(jsonPath("$.items[0].id").value(106))
                .andExpect(jsonPath("$.items[1].id").value(105))
                .andExpect(jsonPath("$.page.totalElements").value(4))
                .andExpect(jsonPath("$.page.totalPages").value(2))
                .andExpect(jsonPath("$.page.hasNext").value(true))
                .andExpect(jsonPath("$.sort.field").value("createdAt"));
    }

    @Test
    void nextPageKeepsStableOrder() throws Exception {
        mvc.perform(get("/api/books")
                        .param("page", "1")
                        .param("size", "2")
                        .param("category", "spring"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items[0].id").value(103))
                .andExpect(jsonPath("$.items[1].id").value(102))
                .andExpect(jsonPath("$.page.hasNext").value(false))
                .andExpect(jsonPath("$.page.hasPrevious").value(true));
    }

    @Test
    void availableFalseIsARealFilter() throws Exception {
        mvc.perform(get("/api/books")
                        .param("category", "spring")
                        .param("available", "false"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.page.totalElements").value(2))
                .andExpect(jsonPath("$.items[0].id").value(106))
                .andExpect(jsonPath("$.items[1].id").value(103))
                .andExpect(jsonPath("$.filters.available").value(false));
    }

    @Test
    void sortingByTitleChangesOrderNotTotal() throws Exception {
        mvc.perform(get("/api/books")
                        .param("category", "spring")
                        .param("size", "2")
                        .param("sort", "title,asc"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items[0].id").value(103))
                .andExpect(jsonPath("$.items[1].id").value(102))
                .andExpect(jsonPath("$.page.totalElements").value(4))
                .andExpect(jsonPath("$.sort.direction").value("asc"));
    }

    @Test
    void outOfRangePageReturnsEmptyArrayAndOriginalTotal() throws Exception {
        mvc.perform(get("/api/books")
                        .param("page", "10")
                        .param("size", "2")
                        .param("category", "spring"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items.length()").value(0))
                .andExpect(jsonPath("$.page.totalElements").value(4))
                .andExpect(jsonPath("$.page.number").value(10))
                .andExpect(jsonPath("$.page.hasNext").value(false));
    }

    @Test
    void noMatchesReturnsZeroTotals() throws Exception {
        mvc.perform(get("/api/books").param("q", "NoSuchBook"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items.length()").value(0))
                .andExpect(jsonPath("$.page.totalElements").value(0))
                .andExpect(jsonPath("$.page.totalPages").value(0));
    }

    @Test
    void invalidPaginationAndSortReturn400() throws Exception {
        mvc.perform(get("/api/books").param("page", "-1"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("BAD_QUERY"));

        mvc.perform(get("/api/books").param("size", "0"))
                .andExpect(status().isBadRequest());

        mvc.perform(get("/api/books").param("size", "51"))
                .andExpect(status().isBadRequest());

        mvc.perform(get("/api/books").param("sort", "privateField,asc"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void parameterConversionFailureIs400() throws Exception {
        mvc.perform(get("/api/books").param("page", "abc"))
                .andExpect(status().isBadRequest());
    }
}
~~~

Chạy toàn bộ test:

~~~bash
./gradlew test
~~~

Các test này cố ý kiểm tra **thứ tự phần tử**, **tổng sau khi lọc**, **trang ngoài phạm vi**, **boolean false** và **error status**. Chỉ assert số lượng item mà không kiểm thứ tự không bắt được lỗi sort. Chỉ assert total trên request không filter không bắt được lỗi “count trước filter”.

Lưu ý về phạm vi xác minh: code test được trình bày cho app demo. Việc có filter bảo mật hoặc cấu hình MVC riêng trong project thật có thể yêu cầu thêm setup trong MockMvc. Test in-memory **không chứng minh tính đúng đắn của SQL, index hoặc tính nhất quán khi có giao dịch đồng thời**.

## 10. Khi có Spring Data: `Pageable`, `Sort`, `Page` và `Slice`

### 10.1. Spring MVC nhận `Pageable` thông qua Spring Data web support

Trong ứng dụng đã cấu hình Spring Data web (thường qua các starter Spring Data/Boot auto-configuration tương ứng), controller có thể nhận trực tiếp:

~~~java
@GetMapping("/api/books")
public Page<BookEntity> find(
        @PageableDefault(size = 20, sort = "createdAt",
                         direction = Sort.Direction.DESC)
        Pageable pageable) {
    return repository.findAll(pageable);
}
~~~

**Đây là fragment không độc lập:** cần imports `Page`, `Pageable`, `PageableDefault`, `Sort`, khai báo entity/repository và cấu hình Data/JPA; cũng **không phải lời khuyên trả `Page<Entity>` trực tiếp ra API công khai**. Hãy map `Page<BookEntity>` thành DTO và envelope như mục 6.

Spring Data web resolver thường hiểu:
- `page`: index zero-based, mặc định 0.
- `size`: page size, thường default 20 ở resolver (có thể tùy chỉnh).
- `sort=title,asc`: sort field/direction.
- `sort=createdAt,desc&sort=id,asc`: nhiều directive.

`@PageableDefault` thay default cho tham số controller; có thể dùng `@SortDefault` để cấu hình nhiều sort mặc định. Resolver còn hỗ trợ `setMaxPageSize` và `setOneIndexedParameters` khi cấu hình. Không suy luận rằng annotation `@PageableDefault(size=20)` tự tạo allowlist sort hoặc đã đáp ứng mọi chính sách bảo mật.

### 10.2. Repository query với `Pageable`

Một Spring Data JPA repository điển hình có thể khai báo:

~~~java
// Fragment, chỉ đúng khi đã có BookEntity và JPA repository setup.
interface BookRepository extends JpaRepository<BookEntity, Long> {
    Page<BookEntity> findByCategoryIgnoreCase(
            String category, Pageable pageable);
}
~~~

Dự án thật phải ghép bộ lọc optional `q`, `available` và phân quyền vào cùng query trước khi paging. Có thể dùng `Specification`, Criteria API, Querydsl hoặc repository method phù hợp. **Không** làm:
1. `repository.findAll()` tải hết bảng.
2. `stream().filter(...)` trong JVM.
3. `subList(...)` trả một trang.

Cách đó có thể chấp nhận với một fixture sáu bản ghi để dạy contract, nhưng sai về quy mô và chi phí đối với production database.

### 10.3. `Page` khác `Slice` thế nào?

| Trả về | Biết totalElements/totalPages? | Biết còn trang tiếp? | Chi phí thường gặp |
| --- | --- | --- | --- |
| `Page<T>` | Có, dựa query tổng khi cần | Có | Có thể cần `COUNT(...)` tốn chi phí |
| `Slice<T>` | Không cần | Có (`hasNext`) | Thường truy vấn size + 1 để xác định còn |
| `List<T>` với `Pageable` | Không có metadata page | Không trực tiếp | Chỉ lấy vùng dữ liệu theo limit/offset |
| `Window<T>` với scrolling | Không tập trung vào total count | Có | Hỗ trợ offset/keyset scrolling tùy store |

`Page` hữu ích cho UI muốn “Trang 2 trên 37” hoặc cần tổng số kết quả sau filter. `Slice` phù hợp với “Load more” khi chỉ cần biết còn dữ liệu. Không thêm COUNT query chỉ vì muốn trang HTML có nút Next; kiểm tra UX contract thực sự cần.

Tùy repository và query, Spring Data có thể tối ưu/suy ra total count ở một số trường hợp, vì vậy không khẳng định **mọi** `Page` luôn thực hiện đúng hai câu SQL.

### 10.4. Tạo JSON ổn định từ `Page`

Ví dụ ý tưởng trong service:

~~~java
// Fragment cần các kiểu DTO và repository của ứng dụng.
Page<BookEntity> entityPage = repository.findAll(validatedPageable);

List<BookDto> items = entityPage.getContent().stream()
        .map(BookDto::fromEntity)
        .toList();

// Tạo response DTO do ứng dụng quản lý:
// items, page number/size, numberOfElements,
// entityPage.getTotalElements(), entityPage.getTotalPages(),
// entityPage.hasNext(), applied sort, effective filters.
~~~

Nếu dùng `org.springframework.data.web.PagedModel` (Spring Data 3.3+) hoặc `@EnableSpringDataWebSupport(pageSerializationMode = VIA_DTO)`, hãy kiểm tra representation thực tế bằng integration test và versioned docs. Tên `PagedModel` cũng xuất hiện trong thư viện Spring HATEOAS; **đó không phải cùng một class**.

## 11. Offset pagination không bảo toàn snapshot khi dữ liệu thay đổi

### 11.1. Vấn đề khi có bản ghi mới

Giả sử sort mới nhất trước:

~~~text
Ở thời điểm T1:  [A, B, C, D, E, F]
page=0,size=2 -> [A, B]
~~~

Trước khi client gọi trang kế tiếp, một bản ghi `X` mới xuất hiện đầu danh sách:

~~~text
Ở thời điểm T2:  [X, A, B, C, D, E, F]
page=1,size=2 -> [B, C]
~~~

Client đã thấy `B` ở cả hai trang. Khi bản ghi bị xóa hoặc điều kiện lọc thay đổi, có thể xảy ra **bỏ sót**. Khóa phụ `id` làm thứ tự xác định tại mỗi thời điểm nhưng **không cố định snapshot giữa hai request**.

Các cách xử lý tùy nhu cầu:
- UI tra cứu thông thường: chấp nhận dữ liệu thay đổi và cung cấp nút Refresh.
- Export/report yêu cầu tập nhất quán: dùng snapshot/cursor token hoặc một transaction/snapshot strategy phù hợp, không giữ transaction HTTP quá dài vô hạn.
- Feed vô hạn, dữ liệu lớn, thứ tự thời gian: cân nhắc cursor/keyset pagination.

### 11.2. Keyset/cursor pagination

Thay vì `OFFSET 100000`, cursor ghi nhận khóa của phần tử cuối đã trả:

~~~text
GET /api/events?limit=20&after=opaqueCursor
~~~

Ví dụ data ordered `createdAt DESC, id DESC`, request tiếp theo chỉ lấy các bản ghi **đứng sau tuple cuối** theo thứ tự đó. Conceptual SQL:

~~~sql
SELECT id, created_at, payload
FROM events
WHERE (created_at < :last_created_at)
   OR (created_at = :last_created_at AND id < :last_id)
ORDER BY created_at DESC, id DESC
LIMIT :limit_plus_one;
~~~

Đây là SQL minh họa keyset cho hai khóa non-null và một database có phép so sánh phù hợp. Cần composite index theo filter/order và xử lý đúng NULL/collation. Không dùng raw query string của client thay cho token tin cậy.

Cursor public API nên:
- Opaque (có thể base64url encode token có phiên bản, keyset values, sort, filter fingerprint, hết hạn); nếu cursor ảnh hưởng quyền truy cập, cần bảo vệ khỏi giả mạo.
- Gắn với **đúng filters và sort**; cursor không được dùng cho một truy vấn khác.
- Có giới hạn `limit` và expiry/restart behavior rõ ràng.
- Trả `items`, `nextCursor`, `hasNext`; **không hứa `totalPages`** khi không đếm toàn bộ tập.

Cursor không tự tạo snapshot bất biến. Nó giúp duyệt theo vị trí ổn định hơn khi có insert đứng trước cursor, nhưng các update/delete làm thay đổi sort/filter vẫn có thể ảnh hưởng lần duyệt.

### 11.3. So sánh để chọn

| Yêu cầu sản phẩm | Offset (`page,size`) | Cursor/keyset |
| --- | --- | --- |
| Nhảy thẳng đến trang 19 | Thuận tiện | Thường không thuận tiện |
| Hiển thị “tổng 1.239 kết quả” | `Page`/COUNT phù hợp | Cần count riêng nếu muốn |
| Feed “Load more” liên tục | Dùng được nhưng dễ dịch trang khi có ghi dữ liệu | Thường tốt hơn với sort/keyset ổn định |
| Offset rất sâu trên bảng lớn | Có thể tốn chi phí | Có thể tốt hơn khi index phù hợp |
| Client cần lưu URL trang cố định | Dễ diễn đạt | Cần token và chính sách hạn |
| Dữ liệu đổi giữa hai request | Không đảm bảo snapshot | Cũng không đảm bảo snapshot tuyệt đối |

Không đổi sang cursor chỉ vì có API danh sách: chọn theo volume, nhu cầu UX, chi phí query và tính nhất quán thực tế.

## 12. Hiệu năng, index và độ tin cậy của total

### 12.1. Count query có thể nặng

Một request `Page<Book>` trong Spring Data thường truy vấn dữ liệu trang và có thể cần count cho `totalElements`. COUNT trên tập join/filter lớn có thể đắt, nhất là với nhiều joins, phân quyền, distinct hoặc truy vấn full-text. Dùng `Slice` nếu không cần tổng, hoặc thiết kế API cho biết tổng chỉ khi được yêu cầu (ví dụ `includeTotal=true`) nếu điều đó phù hợp.

Đừng trả metadata `totalElements=items.size()` để né count nhưng vẫn giữ tên field: đây là thay đổi ngữ nghĩa làm frontend tính trang sai. Nếu tổng không thể cung cấp chính xác, có thể bỏ field, dùng `totalApproximate` với tên và cam kết rõ, hoặc chuyển sang slice/cursor contract.

### 12.2. Index nên phục vụ bộ lọc và sắp xếp

Nếu thường lọc `category` rồi sort `createdAt DESC,id DESC`, cân nhắc index composite bắt đầu bằng điều kiện chọn lọc phù hợp và các khóa sort (tùy database/cardinality/query workload). Test bằng `EXPLAIN` và dữ liệu gần production. Tạo index cho mọi tổ hợp filter/sort có thể khiến ghi dữ liệu chậm và tăng storage; đo workload thay vì đoán.

Câu truy vấn không có `ORDER BY` không có thứ tự cam kết, kể cả khi hôm nay tình cờ theo primary key. Nếu dùng sort trên expression hoặc field join, cần kiểm chi phí và giới hạn cho phép.

### 12.3. Tính nhất quán của total và items

Khi data thay đổi giữa câu query lấy items và câu query count, hai kết quả có thể phản ánh hai thời điểm khác nhau. Isolation level, transaction snapshot và logic persistence quyết định độ nhất quán; `Page<T>` không tự hứa snapshot tuyệt đối giữa các HTTP requests.

Frontend nên có khả năng xử lý:
- `items=[]` nhưng `totalElements>0` nếu user đã đứng quá trang cuối.
- Giảm tổng khi filter đổi.
- Bản ghi bị xóa trước khi user bấm Next.
- Trang trước/tiếp thay đổi nếu có ghi đồng thời.

Tài liệu sản phẩm nên công bố **total là con số tại thời điểm truy vấn** và có thể thay đổi, trừ khi API cung cấp snapshot semantics rõ ràng.

## 13. Hợp đồng lỗi, HTTP cache và API evolution

### 13.1. Một bộ status nên nhất quán

| Request hoặc tình trạng | Status đề xuất cho ví dụ | Ý nghĩa |
| --- | --- | --- |
| Danh sách có dữ liệu | `200 OK` | `items` và metadata |
| Bộ lọc hợp lệ nhưng không khớp | `200 OK` | `items=[]`, `totalElements=0` |
| Page ngoài số trang nhưng input hợp lệ | `200 OK` | Trả `items=[]` theo policy đã công bố |
| `page=-1`, `size=0`, unknown sort | `400 Bad Request` | Sai contract query |
| `page=abc` | `400 Bad Request` | Lỗi chuyển kiểu/binding |
| Chưa xác thực/quyền không đủ | `401`/`403` | Theo cơ chế auth/authorization |
| Query/DB lỗi thật sự phía server | `5xx` phù hợp | Không ngụy trang thành danh sách trống |

Bảng này là **chính sách của ứng dụng ví dụ**, không phải lệnh bắt buộc mọi API. Quan trọng là các nhóm lỗi có mã máy đọc được và test, tránh frontend suy luận `[]` đồng nghĩa service thất bại.

### 13.2. Bộ lọc là một phần cache key

Nếu dùng HTTP/CDN caching cho GET, cache key cần phân biệt query params ảnh hưởng kết quả (`page`, `size`, `sort`, tất cả filters, tenant/visibility nếu có). Không cache response cá nhân trên shared cache mà không có chính sách authorization/cache headers phù hợp.

`ETag` hoặc `Last-Modified` có thể hỗ trợ conditional GET khi có version tài nguyên phù hợp. Tuy nhiên tính `ETag` bằng việc serialize toàn bộ dataset cho mỗi request có thể làm cache vô dụng; thiết kế theo lifecycle dữ liệu.

### 13.3. Backward compatibility

Những thay đổi có thể phá client:
- Đổi `page` zero-based thành one-based.
- Đổi default size/sort dẫn tới vị trí item thay đổi.
- Rename/remove fields hoặc đổi kiểu `totalElements` thành chuỗi.
- Thay field sort công khai bằng tên entity field mới.
- Đổi semantics của filter `q` từ contains sang exact match.
- Thay JSON envelope tự định nghĩa bằng Jackson serialization của `PageImpl`.

Những thay đổi thường an toàn hơn nếu có kiểm thử:
- Thêm field metadata tùy chọn khi client bỏ qua unknown properties.
- Thêm filter optional với default “không lọc”.
- Thêm lựa chọn sort có allowlist, giữ các lựa chọn cũ.

Đối với API nhiều consumer, công bố OpenAPI response schema, chuẩn hóa error schema và kiểm tra contract tests ở CI. Đừng để đổi library Spring Data ngầm kéo theo đổi shape public response.

## 14. Những lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Cách khắc phục |
| --- | --- | --- |
| Item lặp ở hai trang | Sort thiếu unique tie-breaker hoặc dữ liệu thay đổi | Thêm khóa sort phụ, cân nhắc cursor/snapshot |
| Trả 20 item trên request size=5 | Không truyền limit/`Pageable` xuống query | Assert size và kiểm query thực |
| Total sai khi lọc | COUNT tính trên toàn bảng hoặc điều kiện count khác data query | Dùng cùng filter/tenant scope cho count |
| Sort tùy ý truy cập property nội bộ | Không có allowlist | Map public field name sang property hợp lệ |
| `size=0` gây chia cho 0 | Không validate size | Kiểm 1..MAX trước tính metadata |
| `page × size` âm/sai | Overflow `int` | Validate page/size và nhân trên `long` |
| Trang cuối rỗng dù UI nghĩ còn | Dữ liệu thay đổi hoặc total cũ | Refresh, xử lý out-of-range và theo dõi version |
| API trả `PageImpl` JSON đổi shape sau nâng Spring Data | Expose representation framework nội bộ | Dùng stable envelope hoặc PagedModel có test |
| COUNT query quá lâu | Trả `Page` khi UI chỉ cần Next | Cân nhắc `Slice` hoặc cursor |
| `q` không tìm có dấu như mong đợi | So khớp chữ/collation không nhất quán | Xác định search/collation contract |
| Chạy in-memory ổn nhưng DB phân trang sai | Lọc/sort trong JVM sau khi limit hoặc thiếu ORDER BY | Chuyển filter/sort/page vào query, test integration |
| 200 với `items=[]` che lỗi server | Catch exception rồi trả list rỗng | Phân biệt empty dataset với lỗi hạ tầng |
| Client gửi `sort=title,desc` nhưng metadata nói asc | Dùng default khi build response | Trả effective sort đã normalize và test |

Khi gặp lỗi, lấy **một URL cụ thể** cùng filter, sort, index, size, quyền user và snapshot dữ liệu để tái hiện. Kiểm tra SQL thực thi (`WHERE`/`ORDER BY`/`LIMIT OFFSET`), Java mapping và JSON envelope, không chỉ nhìn response mảng.

## 15. Checklist thiết kế và tự đánh giá

Trước khi public danh sách API:
1. Ghi rõ query names, page base, default size, max size và behavior tham số lỗi.
2. Xác định điều kiện lọc, case sensitivity, blank/null semantics, AND/OR, timezone và quyền truy cập.
3. Chọn allowlist sort với thứ tự mặc định và **unique tie-breaker**.
4. Chỉ phân trang sau khi đã filter/sort ở **nguồn dữ liệu**, ưu tiên database cho dataset lớn.
5. Chọn giữa `Page` (có totals), `Slice` (hasNext) và cursor (load-more/large feed).
6. Định nghĩa JSON envelope tự sở hữu; `items=[]` khi rỗng, metadata theo **tập đã lọc**.
7. Thống nhất xử lý page vượt phạm vi và `totalPages=0`, 400 conversion/validation và status lỗi hệ thống.
8. Kiểm thử nhiều trang, sort tie, available=false, blank filter, out-of-range, dữ liệu rỗng, size biên và quyền/tenant.
9. Với DB, đo count/offset sâu, EXPLAIN index, kiểm tra query trên dữ liệu thay đổi.
10. Giữ backward compatibility của field names, metadata và default behavior; test JSON công khai khi nâng framework.

### Câu hỏi tự kiểm tra

**1.** Client gửi `page=2&size=10` trên API zero-based. Offset là bao nhiêu?

**Trả lời:** 20; đây là trang thứ ba nếu trang đầu là 0.

**2.** Vì sao `totalElements` không bằng `items.length`?

**Trả lời:** `items.length` chỉ đếm phần tử trang đang trả; `totalElements` đếm toàn bộ bản ghi khớp filter nếu API cung cấp tổng.

**3.** Sort `createdAt DESC` đã đủ ổn định khi nhiều record trùng thời điểm chưa?

**Trả lời:** Chưa. Thêm khóa unique, ví dụ `id ASC`, để tạo thứ tự toàn phần trong cùng snapshot.

**4.** Có nên dùng `Page<T>` hay `Slice<T>` cho feed chỉ có nút “Tải thêm”?

**Trả lời:** `Slice<T>` thường hợp lý hơn nếu không cần total count; cursor/keyset đáng cân nhắc nếu offset sâu hoặc dữ liệu đổi thường xuyên.

**5.** Trả thẳng `PageImpl<Entity>` cho frontend có rủi ro gì?

**Trả lời:** JSON dễ phụ thuộc vào cấu trúc serialization của Spring Data, có thể đổi qua version; entity cũng có thể lộ field. Nên dùng DTO/envelope ổn định hoặc cơ chế representation được hỗ trợ và kiểm thử.

**6.** Vì sao cần phân biệt `available=null` với `available=false`?

**Trả lời:** null là không lọc; false nghĩa là chỉ lấy bản ghi không available. Gộp hai trường hợp sẽ lọc sai và tính total sai.

## 16. Tài liệu chính thức

- [Spring Framework — `@RequestParam` trong Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html): query/form parameters và conversion.
- [Spring Framework — `@ResponseBody`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responsebody.html): serialize return value bằng HTTP message converters.
- [Spring Data Commons — Web support, Pageable và Sort](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html): `page`, `size`, `sort`, resolver, customizer và `@PageableDefault`.
- [Spring Data JPA — Paging/Sorting, `Page`, `Slice` và Scrolling](https://docs.spring.io/spring-data/jpa/reference/repositories/query-methods-details.html): query count, offset/keyset và trade-off.
- [Spring Data — `PageableDefault` Javadoc](https://docs.spring.io/spring-data/commons/docs/3.3.5/api/org/springframework/data/web/PageableDefault.html): default page/size/sort cho method parameters.
- [Spring Data — `PageSerializationMode` Javadoc](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/web/config/EnableSpringDataWebSupport.PageSerializationMode.html): `DIRECT` và `VIA_DTO`.
- [Spring Data — `PagedModel` Javadoc](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/web/PagedModel.html): stable DTO representation của `Page`.
- [Spring Data REST — Paging and Sorting](https://docs.spring.io/spring-data/rest/reference/paging-and-sorting.html): lưu ý đây là cơ chế REST repository exposure riêng, không tự áp cho mọi `@RestController` do bạn viết.

**Ghi nhớ:** một danh sách REST đáng tin cậy phải có **filter rõ nghĩa, thứ tự xác định, phân trang có giới hạn và response contract ổn định**. Spring MVC nhận tham số và ghi response; Spring Data hỗ trợ query/paging khi có repository, còn ý nghĩa public API, tính nhất quán và chính sách lỗi luôn phải được ứng dụng quyết định và kiểm thử.

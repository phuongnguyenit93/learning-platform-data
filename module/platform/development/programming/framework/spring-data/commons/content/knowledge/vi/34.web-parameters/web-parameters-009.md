# Điều kiện repository hỗ trợ và xử lý ID không tồn tại

Một endpoint nhận `/articles/42` có thể yêu cầu Spring MVC đưa thẳng một đối tượng `Article` vào phương thức controller. Cú pháp đó ngắn gọn, nhưng chỉ hoạt động khi hạ tầng chuyển đổi kiểu tìm được repository phù hợp, chuyển được chuỗi `42` thành kiểu ID và thực hiện được việc tìm đối tượng. Khi không có bản ghi, kết quả chuyển đổi cũng không tự mang theo đầy đủ chính sách lỗi HTTP của ứng dụng.

Trong chương **Tham số web** của **Spring Data Commons**, bài học này giải thích điều kiện dùng repository để phân giải domain object từ ID và cách xử lý trường hợp không tìm thấy. Commons cung cấp abstraction và cơ chế tích hợp; mapping, derived query, projection, quyền truy cập và khả năng truy vấn vẫn cần được đối chiếu với module lưu trữ đang dùng.

## 1. Hai cách nhận một ID ở ranh giới web

Với cùng URL, controller có thể nhận ID rõ ràng:

```java
@GetMapping("/articles/{id}")
ArticleView get(@PathVariable("id") Long id) {
    return articleService.requireView(id);
}
```

Hoặc nhận domain object thông qua cơ chế chuyển đổi của Spring Data Web:

```java
@GetMapping("/articles/{id}")
ArticleView get(@PathVariable("id") Article article) {
    return ArticleView.from(article);
}
```

Đây là hai phương án thay thế, không phải hai mapping cần đăng ký đồng thời. `ArticleService`, `ArticleView` và entity `Article` thuộc ứng dụng minh họa. Ví dụ giả định entity có ID kiểu `Long` cùng các thuộc tính thích hợp.

Ở cách đầu, controller/service chủ động quyết định lúc nào truy vấn và làm gì khi không có dữ liệu. Ở cách sau, việc tìm entity có thể xảy ra trong lúc Spring MVC phân giải đối số, trước khi vào thân phương thức controller.

Sự khác biệt này ảnh hưởng đến khả năng quan sát truy vấn, ranh giới transaction, kiểm tra quyền và cách biểu diễn lỗi.

## 2. DomainClassConverter thực hiện chuỗi chuyển đổi nào?

Trong hạ tầng Spring Data Web của Spring MVC, `DomainClassConverter` có thể dùng metadata repository và conversion service để chuyển một giá trị đầu vào sang domain object.

Đường đi khái niệm:

```text
Chuỗi trên URL: "42"
    ↓ chuyển sang kiểu ID của Article
Long: 42
    ↓ gọi thao tác tìm theo ID qua repository phù hợp
Optional<Article>
    ↓ lấy đối tượng hoặc không có giá trị
Article hoặc kết quả chuyển đổi null
    ↓ Spring MVC tiếp tục phân giải đối số
Đối số controller hoặc lỗi binding theo khai báo và cấu hình
```

Có hai câu hỏi độc lập:

1. Đầu vào có chuyển được sang kiểu ID không?
2. Repository có tìm thấy domain object mang ID đó không?

`abc` không phải một `Long` hợp lệ. Ngược lại, `999999` có thể là một `Long` hoàn toàn hợp lệ nhưng không tương ứng với bản ghi nào. Hai tình huống cần có hợp đồng xử lý riêng.

Converter không tự chạy mọi truy vấn nghiệp vụ mà ứng dụng đã định nghĩa. Ví dụ, việc có phương thức `findByIdAndPublishedTrue(...)` không khiến converter tự thay thao tác tìm theo ID thông thường bằng phương thức đó.

## 3. Điều kiện để repository tham gia phân giải domain object

### 3.1. Hạ tầng Spring Data Web phải được bật

Các ví dụ trong bài dùng Spring MVC và Spring Data Web. Với cấu hình chủ động, có thể bật hỗ trợ bằng:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.web.config.EnableSpringDataWebSupport;

@Configuration
@EnableSpringDataWebSupport
class DataWebConfiguration {
}
```

Một ứng dụng Spring Boot phù hợp có thể đã được auto-configure. Cần hiểu cấu hình đang sử dụng trước khi thêm cấu hình trùng lặp hoặc tự thay conversion service.

Việc chỉ thêm `@PathVariable` hoặc khai báo một interface repository không đủ để bảo đảm toàn bộ đường chuyển đổi đã được đăng ký trong Spring MVC.

### 3.2. Repository phải được tạo và có thể được phát hiện

Interface cần được module Spring Data phù hợp tạo thành repository bean trong application context. Một interface nằm ngoài phạm vi repository scanning, thiếu cấu hình module hoặc chỉ là base interface chưa có bean cụ thể sẽ không tự trở thành nguồn tìm entity.

Ví dụ hợp đồng cơ bản:

```java
import org.springframework.data.repository.CrudRepository;

interface ArticleRepository extends CrudRepository<Article, Long> {
}
```

Mapping của `Article` phải hợp lệ với module persistence của ứng dụng. Không dùng annotation mapping của một module rồi mặc định mọi module khác đều hiểu nó.

`CrudRepository<Article, Long>` cung cấp thông tin domain type, ID type và hợp đồng CRUD có thao tác `findById`. Đây là hợp đồng được tài liệu Spring Data Web dùng cho repository tham gia cơ chế chuyển đổi domain class.

### 3.3. Cần có khả năng tìm theo ID phù hợp

Một repository chỉ phục vụ sắp xếp hoặc phân trang không tự cung cấp đầy đủ hợp đồng CRUD. Trong các dòng Spring Data hiện đại, `PagingAndSortingRepository` không tự kế thừa `CrudRepository`.

Nếu ứng dụng cần cả hai khả năng, phải chọn hoặc kết hợp các interface thích hợp theo phiên bản đang dùng. Riêng với converter, không suy luận rằng có `findAll(Pageable)` là đã có đầy đủ khả năng tìm domain object theo ID.

Một interface tùy biến chỉ khai báo một phương thức trông giống `findById` cũng cần được kiểm tra theo cơ chế repository và invoker của phiên bản tương ứng. Không lấy sự giống nhau về tên làm bằng chứng rằng mọi cơ chế Spring Data Web sẽ phát hiện và sử dụng nó như một `CrudRepository` tiêu chuẩn.

### 3.4. Kiểu ID phải chuyển đổi được từ đầu vào

Nếu repository dùng ID kiểu `Long`, conversion service cần chuyển được chuỗi sang `Long`. Với `UUID`, chuỗi phải phù hợp định dạng UUID. Với value object hoặc ID tổng hợp, ứng dụng có thể cần converter hoặc một cách phân giải đối số riêng.

Một URL nhìn giống ID không chứng minh kiểu ID của repository là chuỗi. Metadata domain/ID của repository mới là cơ sở cho đường chuyển đổi.

## 4. Phân biệt các loại repository liên quan

| Loại hợp đồng hoặc thành phần | Điều cần xác nhận |
|---|---|
| `CrudRepository<T, ID>` đồng bộ | Có repository bean hợp lệ, metadata đúng và thao tác tìm theo ID hoạt động |
| Interface đồng bộ kế thừa CRUD của module | Kiểm tra quan hệ kế thừa và cấu hình thực tế của module |
| `PagingAndSortingRepository<T, ID>` đứng riêng | Không tự suy ra có CRUD hoặc đủ điều kiện cho đường chuyển đổi này |
| Base repository có `@NoRepositoryBean` | Cần repository cụ thể được tạo; base interface không phải bean truy cập dữ liệu độc lập |
| DAO/service do ứng dụng tự viết | Không tự được dùng chỉ vì có phương thức nhận ID |
| `ReactiveCrudRepository<T, ID>` | Không xem là thay thế đồng bộ tương đương cho cơ chế MVC đang minh họa |
| Coroutine repository | Không suy ra converter MVC sẽ tự gọi hàm suspend hoặc collect Flow |

Bài học không yêu cầu đổi ứng dụng reactive sang repository đồng bộ. Với WebFlux hoặc một đường truy cập coroutine/reactive, cần dùng cơ chế phân giải và cách hợp thành bất đồng bộ phù hợp. Không đưa `block()` vào chỉ để ép một luồng reactive giống ví dụ MVC.

Spring Data Commons tạo các abstraction dùng chung, nhưng không làm transaction, driver, truy vấn hay khả năng web của mọi module trở nên đồng nhất.

## 5. ID không tồn tại đi qua converter như thế nào?

Hợp đồng `CrudRepository.findById(id)` trả `Optional<T>`:

```java
Optional<Article> result = repository.findById(id);
```

Khi không có đối tượng, kết quả là `Optional.empty()`. Trong đường chuyển đổi domain class, việc không có entity có thể trở thành kết quả chuyển đổi `null`.

Từ đó, Spring MVC còn phải áp dụng hợp đồng đối số, bao gồm việc đối số có bắt buộc hay không. Với một `@PathVariable` bắt buộc, kết quả `null` sau chuyển đổi có thể được xử lý như tình huống thiếu giá trị sau chuyển đổi, chẳng hạn đi qua `MissingPathVariableException` trong các phiên bản Spring MVC có cơ chế này.

Vì vậy, không dùng sự hiện diện của `DomainClassConverter` làm bằng chứng rằng ID không tồn tại luôn nhận HTTP 404 theo đúng cấu trúc lỗi của ứng dụng. Cần xác định chính sách rõ ràng thay vì phụ thuộc ngầm vào lỗi binding.

Ba lớp cần tách biệt:

| Lớp | Câu hỏi |
|---|---|
| Chuyển đổi kiểu | Chuỗi đầu vào có biểu diễn được kiểu ID không? |
| Truy cập repository | Có đối tượng tương ứng hoặc đối tượng thuộc phạm vi truy vấn không? |
| Hợp đồng HTTP | Tình huống đó được trả với status và nội dung lỗi nào? |

Repository không trả HTTP status. Converter cũng không thể tự biết toàn bộ chính sách tồn tại, quyền truy cập và công bố tài nguyên của API.

## 6. Cách tường minh: nhận ID và tìm trong service

Với endpoint cần hợp đồng lỗi rõ ràng, nhận ID rồi truy vấn trong service là cách dễ theo dõi.

Controller:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/articles")
class ArticleController {

    private final ArticleQueryService service;

    ArticleController(ArticleQueryService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    ArticleView get(@PathVariable("id") Long id) {
        return service.requireView(id);
    }
}
```

Service:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class ArticleQueryService {

    private final ArticleRepository repository;

    ArticleQueryService(ArticleRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public ArticleView requireView(Long id) {
        Article article = repository.findById(id)
                .orElseThrow(() -> new ArticleNotFoundException(id));

        return ArticleView.from(article);
    }
}
```

Các kiểu phụ trợ minh họa:

```java
final class ArticleNotFoundException extends RuntimeException {

    ArticleNotFoundException(Long id) {
        super("Không tìm thấy bài viết có ID " + id);
    }
}

record ArticleView(Long id, String title) {

    static ArticleView from(Article article) {
        return new ArticleView(article.getId(), article.getTitle());
    }
}
```

Ví dụ giả định `Article` có `getId()` và `getTitle()`, và một transaction manager phù hợp đã được cấu hình. `readOnly = true` diễn tả chính sách/hint cho giao dịch theo hạ tầng đang dùng; không phải cơ chế kiểm tra quyền và không bảo đảm mọi kho dữ liệu có cùng cách tối ưu.

Chuyển sang DTO trong service giúp giới hạn dữ liệu trả về và xác định rõ nơi truy cập thuộc tính. Nếu entity có quan hệ lazy, cần chủ động chọn truy vấn, fetch hoặc projection thích hợp; DTO hai trường ở trên không tự giải quyết mọi vấn đề lazy loading.

## 7. Ánh xạ lỗi không tìm thấy sang HTTP 404

Một advice có thể ánh xạ exception nghiệp vụ sang response ổn định:

```java
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

@RestControllerAdvice
class ArticleErrorAdvice {

    @ExceptionHandler(ArticleNotFoundException.class)
    ResponseEntity<ApiError> notFound(ArticleNotFoundException exception) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(new ApiError(
                        "ARTICLE_NOT_FOUND",
                        "Không tìm thấy bài viết"));
    }

    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    ResponseEntity<ApiError> invalidParameter(
            MethodArgumentTypeMismatchException exception) {
        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
                .body(new ApiError(
                        "INVALID_PARAMETER",
                        "Tham số không đúng định dạng yêu cầu"));
    }
}

record ApiError(String code, String message) {
}
```

Handler thứ hai có phạm vi các lỗi mismatch mà advice nhận được, không chỉ riêng ID của bài viết. Trong ứng dụng lớn, cần đặt nó trong chính sách lỗi chung hoặc giới hạn phạm vi advice phù hợp.

Với mô hình này:

```http
GET /api/articles/abc
```

Không chuyển được `abc` sang `Long`, nên service chưa được gọi thành công với một ID hợp lệ. Hợp đồng lỗi của ví dụ là HTTP 400.

```http
GET /api/articles/999999
```

ID chuyển đổi hợp lệ nhưng repository trả rỗng, nên service phát sinh `ArticleNotFoundException`; advice trả HTTP 404.

Không cần trả nguyên văn thông báo exception chứa chi tiết nội bộ trong response. Mã lỗi và thông báo công khai nên là hợp đồng do ứng dụng kiểm soát.

## 8. Nếu vẫn muốn nhận domain object trong controller

Với phiên bản Spring MVC hỗ trợ giá trị `null` sau chuyển đổi cho đối số không bắt buộc, có thể cho phép `null` và tự ánh xạ lỗi:

```java
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.server.ResponseStatusException;

@GetMapping("/api/articles/{id}")
ArticleView getConverted(
        @PathVariable(name = "id", required = false) Article article) {

    if (article == null) {
        throw new ResponseStatusException(
                HttpStatus.NOT_FOUND,
                "Không tìm thấy bài viết");
    }

    return ArticleView.from(article);
}
```

Đây là phương án thay thế trong một controller đã có Spring Data Web và repository phù hợp. Không đăng ký trùng mapping với controller ở phần 6.

`required = false` ở đây cho phép xử lý giá trị đối số không có sau phân giải/chuyển đổi; nó không tự làm đoạn `/{id}` của route trở thành tùy chọn. Request `/api/articles` có khớp handler khác hay không vẫn do các mapping của ứng dụng quyết định.

Cách này còn các giới hạn:

- Nếu chuỗi ID sai định dạng, lỗi chuyển đổi có thể xảy ra trước khi vào thân controller; khối `if (article == null)` không xử lý mọi lỗi đầu vào.
- Việc tìm entity đã diễn ra khi phân giải đối số. Ranh giới transaction của một service được gọi sau đó không tự bao phủ ngược thao tác tìm này.
- Kiểm tra tenant, trạng thái công bố và quyền truy cập cần được thiết kế riêng.
- Việc nhận được entity không tự tạo snapshot tồn tại cho các thao tác ghi tiếp theo.

Nếu endpoint có nhiều chính sách nghiệp vụ, nhận ID rõ ràng rồi truy vấn theo phạm vi trong service thường dễ kiểm soát hơn.

Không viết handler toàn cục biến mọi `MissingPathVariableException` thành 404. Một exception cùng nhóm cũng có thể phản ánh lỗi khai báo mapping hoặc cách phân giải đối số. Cần phân biệt đúng nguyên nhân, kể cả cờ thiếu sau chuyển đổi nếu cơ chế của phiên bản đang dùng cung cấp nó.

## 9. Tenant và quyền truy cập làm thay đổi ý nghĩa của không tìm thấy

Một bản ghi có thể tồn tại trong cơ sở dữ liệu nhưng không thuộc tenant hiện tại. Nếu ứng dụng chỉ gọi `findById(id)` rồi trả entity, đường chuyển đổi ngắn gọn có thể làm mất điều kiện phạm vi quan trọng.

Một hợp đồng repository theo tenant có thể là:

```java
import java.util.Optional;
import java.util.UUID;

import org.springframework.data.repository.CrudRepository;

interface ArticleRepository extends CrudRepository<Article, Long> {

    Optional<Article> findByIdAndTenantId(Long id, UUID tenantId);
}
```

Ví dụ giả định domain có thuộc tính `tenantId` kiểu `UUID` và module hỗ trợ derived query tương ứng. Service cần lấy tenant từ ngữ cảnh danh tính đã được xác định, rồi thực hiện truy vấn có phạm vi:

```java
Article article = repository.findByIdAndTenantId(id, currentTenantId)
        .orElseThrow(() -> new ArticleNotFoundException(id));
```

`currentTenantId` phải đến từ cơ chế xác định tenant của ứng dụng. Không coi một tenant ID tùy ý trong request là bằng chứng quyền truy cập.

Tùy hợp đồng API, tài nguyên ngoài phạm vi có thể được trả như không tìm thấy để tránh công bố sự tồn tại, hoặc đi theo chính sách từ chối truy cập khác. Điều cần giữ là chính sách nhất quán và truy vấn đúng phạm vi.

Việc khai báo thêm `findByIdAndTenantId` không khiến `DomainClassConverter` tự chọn phương thức đó. Nếu muốn phân giải domain object theo tenant ngay ở tầng web, cần cơ chế tùy biến có chủ đích hoặc một thiết kế khác; không mặc định repository metadata đã chứa chính sách tenant.

Các bộ lọc bảo mật web có thể chạy trước bước phân giải đối số. Tuy vậy, một kiểm tra quyền chỉ viết trong thân controller chắc chắn xảy ra sau khi converter đã tìm entity cho đối số ấy. Cần xác định nơi chính sách được thực thi, thay vì nhìn annotation trên controller rồi suy ra chưa có truy vấn nào xảy ra trước đó.

## 10. Các lỗi không được gom thành 404

| Tình huống | Bản chất | Hướng xử lý |
|---|---|---|
| `abc` cho ID `Long` | Không chuyển đổi được kiểu ID | Lỗi đầu vào theo hợp đồng, thường là 400 |
| ID hợp lệ, không có bản ghi | Không có đối tượng trong phạm vi truy vấn | 404 nếu API chọn chính sách đó |
| Chuỗi UUID không hợp lệ | Sai biểu diễn ID | Lỗi đầu vào, chưa kết luận có hay không có entity |
| Repository bean chưa được tạo | Lỗi cấu hình/hạ tầng | Sửa cấu hình; không giả làm tài nguyên không tồn tại |
| Không có converter cho ID tùy biến | Thiếu đường chuyển đổi | Bổ sung chuyển đổi hoặc nhận ID theo hợp đồng rõ ràng |
| Database timeout hoặc mất kết nối | Không truy vấn được | Chính sách lỗi hạ tầng; không biến thành 404 |
| Có entity nhưng không được phép xem | Quyết định truy cập | Theo chính sách 403/404 của ứng dụng |
| Entity bị xóa trước thao tác ghi sau đó | Cạnh tranh dữ liệu | Xử lý theo kết quả thao tác và yêu cầu nhất quán |

Không dùng cách bắt mọi exception rồi trả không tìm thấy:

```java
// Mẫu cần tránh.
try {
    return repository.findById(id)
            .map(ArticleView::from)
            .orElseThrow(() -> new ArticleNotFoundException(id));
} catch (RuntimeException exception) {
    throw new ArticleNotFoundException(id);
}
```

Mẫu này biến lỗi kết nối, mapping hoặc lỗi lập trình thành thông báo sai rằng bài viết không tồn tại. Nó cũng làm mất tín hiệu cần thiết để giám sát và xử lý sự cố.

Chỉ ánh xạ trường hợp không có kết quả theo hợp đồng `Optional`; xử lý các nhóm lỗi khác bằng chính sách tương ứng.

## 11. Không kiểm tra existsById rồi mới findById một cách máy móc

Một cách triển khai thường gặp:

```java
if (!repository.existsById(id)) {
    throw new ArticleNotFoundException(id);
}

Article article = repository.findById(id)
        .orElseThrow(() -> new ArticleNotFoundException(id));
```

Nếu mục tiêu cuối cùng là đọc entity, bước kiểm tra tồn tại riêng có thể tạo thêm công việc truy vấn mà không loại bỏ khả năng kết quả thay đổi giữa hai bước.

Đối tượng có thể bị xóa sau `existsById` nhưng trước `findById`. Ngược lại, dữ liệu có thể xuất hiện sau lần kiểm tra đầu tiên. Cách thông thường cho đường đọc là thực hiện truy vấn cần thiết một lần rồi xử lý kết quả rỗng:

```java
Article article = repository.findById(id)
        .orElseThrow(() -> new ArticleNotFoundException(id));
```

`existsById` vẫn có vai trò khi nghiệp vụ thực sự chỉ cần kiểm tra tồn tại. Nó không phải một khóa bảo đảm entity tiếp tục tồn tại và không thay thế transaction, constraint hoặc cơ chế kiểm soát cạnh tranh của kho dữ liệu.

Khi cập nhật hoặc xóa, việc đã đọc thành công trước đó cũng không chứng minh thao tác sau chắc chắn thành công. Cần xử lý kết quả ghi, optimistic locking và chính sách lỗi theo module.

## 12. Metadata, nhiều repository và nhiều module

Đường chuyển đổi dựa vào mối liên hệ giữa domain type, ID type và repository được application context cung cấp. Vì vậy, các lỗi generic hoặc scanning không chỉ là vấn đề cú pháp.

Cần xác nhận:

| Thành phần | Điều phải khớp |
|---|---|
| Đối số controller | Domain type mà ứng dụng muốn phân giải |
| Repository metadata | Domain type và ID type đúng |
| Entity mapping | Quy tắc nhận diện ID và dữ liệu của module |
| Conversion service | Chuyển được giá trị web sang ID |
| Repository bean | Được tạo bởi đúng module và có thể được lựa chọn |

Nếu nhiều repository cùng quản lý một domain type, cần cấu hình lựa chọn phù hợp với cơ chế của phiên bản/module. Không dựa vào tên biến controller để quyết định repository.

`@Qualifier` dùng để phân biệt dependency injection hoặc các nhóm `Pageable`/`Sort` không tự tạo quy tắc chọn repository cho mọi đối số domain của `DomainClassConverter`. Những annotation cùng tên có thể được các thành phần framework đọc trong ngữ cảnh khác nhau; cần xác định thành phần nào đang thực hiện việc chọn.

Trong ứng dụng nhiều module Spring Data, cần giữ ranh giới repository và mapping rõ ràng. Không suy ra một domain type có thể được tự động tải từ bất kỳ kho nào chỉ vì Commons dùng chung interface `Repository`.

## 13. Domain object được tải không phải projection tùy ý

Một controller nhận `Article` qua converter đang yêu cầu phân giải domain object. Điều đó không tự biến lời gọi thành projection đã tối ưu hoặc một derived query trả đúng DTO cho màn hình.

Nếu màn hình chỉ cần một số trường và ứng dụng đã có truy vấn projection, nên cân nhắc nhận ID rồi gọi truy vấn đó rõ ràng trong service. Khả năng projection, truy vấn tùy biến và hành vi tải dữ liệu phụ thuộc module, kiểu truy vấn cùng cách mapping được cấu hình.

Cũng không nên trả thẳng entity chỉ vì nó đã có sẵn ở tham số controller. Response DTO giúp xác định dữ liệu công khai và giảm phụ thuộc vào cách entity được serialize.

Đối với endpoint sửa dữ liệu, entity được phân giải từ ID không thay thế request DTO. ID của tài nguyên, dữ liệu yêu cầu cập nhật, quyền thao tác và kết quả persistence là các thành phần cần được xử lý rõ ràng. Việc Spring MVC đã tạo đối số không tự gọi `save` hay hoàn tất nghiệp vụ cập nhật.

## 14. Tình huống kiểm chứng hợp đồng

Có thể dùng các tình huống sau khi tích hợp endpoint:

| Request hoặc điều kiện | Điều cần quan sát |
|---|---|
| ID đúng định dạng, entity tồn tại | Response thành công và DTO đúng |
| ID đúng định dạng, entity không tồn tại | 404 tường minh với mã lỗi đã công bố |
| ID sai định dạng | Lỗi đầu vào, không lẫn với không tìm thấy |
| ID không hợp lệ theo nghiệp vụ, ví dụ số âm nếu bị cấm | Kiểm tra ràng buộc theo hợp đồng, không chỉ kiểm tra chuyển kiểu |
| Thiếu đoạn ID trong URL | Kiểm tra route thực tế, không nhầm với repository trả rỗng |
| Entity thuộc tenant khác | Đúng chính sách truy cập và không trả dữ liệu ngoài phạm vi |
| Repository không được scan | Phát hiện lỗi cấu hình, không trả 404 giả |
| Kho dữ liệu không truy cập được | Phân biệt lỗi hạ tầng với dữ liệu không tồn tại |
| Có nhiều repository cho domain | Xác nhận lựa chọn repository đúng thiết kế |
| Entity bị xóa giữa đọc và ghi | Xử lý cạnh tranh theo kết quả persistence |

Đây là các tình huống học tập và kiểm chứng hợp đồng; chúng không thay thế việc lựa chọn cấu hình, transaction manager hay module lưu trữ phù hợp.

Khi chẩn đoán, nên lần theo chuỗi: route có khớp không, chuyển ID có thành công không, repository nào được chọn, kết quả có rỗng không, rồi exception nào được ánh xạ thành HTTP response. Cách lần theo từng ranh giới giúp tránh sửa nhầm query khi nguyên nhân thực sự là conversion hoặc advice.

## 15. Bài tập tự kiểm tra

### Tình huống 1: Repository chỉ kế thừa PagingAndSortingRepository

Controller muốn nhận `Article` từ path variable và cho rằng repository có phân trang nên tự có mọi thao tác CRUD.

**Phân tích:** không suy ra khả năng tìm theo ID từ khả năng phân trang. Cần kiểm tra quan hệ kế thừa của phiên bản, hợp đồng repository thích hợp, bean được tạo và metadata của domain/ID.

### Tình huống 2: ID hợp lệ nhưng không có entity

Endpoint nhận domain object và không có chính sách lỗi rõ ràng. Client nhận lỗi binding thay vì response 404 mong muốn.

**Phân tích:** converter tìm theo ID có thể trả kết quả chuyển đổi `null`; Spring MVC còn áp dụng quy tắc đối số bắt buộc. Nên nhận ID và xử lý `Optional.empty()` trong service, hoặc thiết kế rõ cách chấp nhận giá trị rỗng rồi trả 404.

### Tình huống 3: Có findByIdAndTenantId nhưng converter vẫn dùng tìm theo ID

Ứng dụng khai báo thêm derived query theo tenant và cho rằng mọi lần phân giải `Article` đã được giới hạn tenant.

**Phân tích:** converter không tự chọn phương thức nghiệp vụ theo tên. Cần gọi truy vấn theo tenant rõ ràng hoặc xây dựng cơ chế phân giải tùy biến có chính sách phù hợp.

### Tình huống 4: Bắt mọi lỗi repository và trả 404

Database đang mất kết nối nhưng API trả `ARTICLE_NOT_FOUND`.

**Phân tích:** ứng dụng đã đánh đồng không có kết quả với không thể thực hiện truy vấn. Chỉ trường hợp rỗng theo hợp đồng được ánh xạ thành không tìm thấy; lỗi hạ tầng phải giữ ý nghĩa riêng.

### Tình huống 5: Đặt transaction trên service được gọi từ controller nhận entity

Controller nhận `Article` qua converter rồi truyền entity sang một service có transaction.

**Phân tích:** transaction bắt đầu ở service không tự bao phủ ngược việc converter đã tải entity trước khi vào controller. Nếu thao tác đọc cần cùng transaction với nghiệp vụ, hãy đưa việc tìm theo ID vào ranh giới service thích hợp.

### Tình huống 6: Đã existsById nên cho rằng ghi chắc chắn thành công

Một bước kiểm tra tồn tại thành công, sau đó entity bị xóa bởi request khác.

**Phân tích:** kiểm tra tồn tại là quan sát tại một thời điểm. Cần xử lý kết quả thao tác tiếp theo và dùng cơ chế nhất quán/cạnh tranh phù hợp với module, không xem `existsById` là sự bảo đảm tồn tại lâu dài.

Khi dùng repository để phân giải tham số web, cần giữ rõ điều kiện kỹ thuật và chính sách nghiệp vụ: repository phải phù hợp, ID phải chuyển đổi được, truy vấn phải đúng phạm vi, và kết quả rỗng phải được ánh xạ thành hợp đồng HTTP có chủ đích. Nhận ID tường minh trong service là một lựa chọn hữu ích khi endpoint cần kiểm soát đồng thời quyền truy cập, transaction và lỗi không tìm thấy.

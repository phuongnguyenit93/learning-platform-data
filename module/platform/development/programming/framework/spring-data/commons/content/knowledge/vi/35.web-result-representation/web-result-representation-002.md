# Giới hạn tương thích khi tuần tự hóa trực tiếp PageImpl

Một repository trả `Page<Article>` và controller trả nguyên đối tượng đó cho client là cách viết thuận tiện. Kết quả JSON có thể chứa `content`, số trang, tổng số phần tử cùng thông tin `pageable` và `sort`. Tuy nhiên, cấu trúc xuất hiện hôm nay không đồng nghĩa Spring Data đã cam kết giữ nguyên nó như một hợp đồng REST công khai qua các lần nâng cấp.

Trong chương **Biểu diễn kết quả web** của **Spring Data Commons**, bài học này phân biệt abstraction phân trang ở tầng Java với biểu diễn JSON ở ranh giới HTTP. Mục tiêu là dùng Repository, phân trang, projection và các khả năng chung của Spring Data đúng vai trò, đồng thời giữ hợp đồng web độc lập với chi tiết triển khai và khả năng của từng module lưu trữ.

## 1. Page và PageImpl phục vụ tầng Java

`Page<T>` mô tả một trang kết quả gồm nội dung và metadata, chẳng hạn:

```java
page.getContent();
page.getNumber();
page.getSize();
page.getNumberOfElements();
page.getTotalElements();
page.getTotalPages();
page.hasNext();
```

`PageImpl<T>` là một lớp triển khai thông dụng của abstraction đó. Có thể tự tạo nó trong mã Java:

```java
import java.util.List;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;

Page<String> page = new PageImpl<>(
        List.of("Bài viết A", "Bài viết B"),
        PageRequest.of(0, 2),
        5);
```

Đối tượng trên mô tả trang đầu, kích thước yêu cầu 2, hai phần tử nội dung và tổng số phần tử 5. Tổng số trang tương ứng là 3.

Hợp đồng Java giúp service gọi các phương thức đó mà không cần tự xử lý offset hoặc đếm tổng trong mọi chỗ. Nó không tự quyết định rằng một API HTTP phải công khai toàn bộ getter của lớp triển khai.

Một thay đổi hợp lệ ở lớp Java, ví dụ bổ sung thuộc tính có getter hoặc điều chỉnh một kiểu lồng bên trong, có thể làm JSON thay đổi nếu serializer tự suy ra cấu trúc từ đối tượng runtime.

## 2. Điều gì xảy ra khi controller trả trực tiếp Page?

Ví dụ Spring MVC:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ArticleController {

    private final ArticleQueryService service;

    ArticleController(ArticleQueryService service) {
        this.service = service;
    }

    @GetMapping("/api/articles")
    Page<ArticleSummary> list(Pageable pageable) {
        return service.findAll(pageable);
    }
}
```

`ArticleQueryService` là service của ứng dụng và `ArticleSummary` là kiểu dữ liệu công khai cho mỗi phần tử. Ví dụ giả định hạ tầng Spring Data Web phân giải được `Pageable`, và module persistence đang dùng hỗ trợ truy vấn phân trang tương ứng.

Nếu kết quả runtime là `PageImpl` và ứng dụng đang dùng cách tuần tự hóa trực tiếp, JSON có thể được hình thành từ các thuộc tính mà Jackson nhìn thấy trên lớp triển khai và các object liên quan.

Luồng khái niệm:

```text
Repository của module
    → Page<Article> hoặc Page<ArticleSummary>
    → đối tượng triển khai, thường là PageImpl
    → HttpMessageConverter và ObjectMapper đang được cấu hình
    → JSON gửi cho client
```

Khai báo kiểu trả về là `Page` không loại bỏ đối tượng `PageImpl` ở runtime. Jackson vẫn chịu ảnh hưởng của cấu hình serialization, module, mixin và kiểu thực tế.

Nếu ứng dụng đã đăng ký một serializer hoặc cơ chế chuyển đổi có hợp đồng riêng, JSON có thể được kiểm soát theo cơ chế đó. Vấn đề trong bài là việc lấy biểu diễn trực tiếp mặc định của `PageImpl` làm hợp đồng mà không có lớp kiểm soát rõ ràng.

## 3. Một JSON quan sát được chưa phải schema được cam kết

Một response tuần tự hóa trực tiếp có thể chứa các nhóm thông tin như:

```json
{
  "content": [
    {"id": 101, "title": "Bài viết A"},
    {"id": 102, "title": "Bài viết B"}
  ],
  "number": 0,
  "size": 2,
  "totalElements": 5,
  "totalPages": 3,
  "first": true,
  "last": false,
  "numberOfElements": 2,
  "empty": false,
  "pageable": {
    "pageNumber": 0,
    "pageSize": 2
  },
  "sort": {
    "sorted": false,
    "unsorted": true,
    "empty": true
  }
}
```

Đây là **ảnh minh họa các trường có thể xuất hiện**, được rút gọn để giải thích. Nó không phải mẫu JSON bắt buộc của mọi phiên bản hoặc mọi cấu hình Jackson. Những object lồng nhau có thể có thêm trường, khác cấu trúc hoặc được xử lý bởi serializer đã đăng ký.

Nếu frontend đọc trực tiếp đường dẫn như `response.pageable.pageNumber` hoặc phụ thuộc vào toàn bộ cấu trúc `sort`, nó đang liên kết với cách triển khai hiện tại. Một nâng cấp thư viện có thể làm client hỏng dù truy vấn repository vẫn trả đúng dữ liệu.

Không nên sao chép nguyên response quan sát được vào tài liệu API rồi xem đó là bằng chứng về cam kết tương thích của Spring Data. Tài liệu API chỉ trở thành hợp đồng có thể kiểm soát khi phía ứng dụng cũng chủ động bảo vệ biểu diễn ấy.

## 4. Tương thích Java khác tương thích JSON

Có ít nhất ba lớp tương thích cần phân biệt:

| Lớp | Câu hỏi đánh giá |
|---|---|
| Hợp đồng repository và Page | Service còn gọi được API và hiểu đúng kết quả phân trang không? |
| Mã Java của ứng dụng | Mã nguồn hoặc bytecode còn dùng được với thư viện đã nâng cấp không? |
| Hợp đồng HTTP | Client còn nhận đúng schema và ý nghĩa trường đã công bố không? |

Ứng dụng có thể vượt qua hai lớp đầu nhưng vẫn làm hỏng lớp thứ ba. Ví dụ service tiếp tục gọi `getTotalElements()` như trước, trong khi cấu trúc metadata mà client đang đọc đã thay đổi do serialization.

Tương thích JSON cũng không chỉ là giữ nguyên tên trường. Nó còn bao gồm:

- Kiểu dữ liệu và khả năng nhận `null`.
- Ý nghĩa của số trang và kích thước trang.
- Cách biểu diễn danh sách rỗng.
- Việc trường có bắt buộc hay không.
- Cách biểu diễn tiêu chí sort, liên kết điều hướng và metadata khác.

Thứ tự các thuộc tính trong một JSON object thường không phải ý nghĩa của hợp đồng. Ngược lại, thứ tự phần tử trong `content` và thứ tự ưu tiên các tiêu chí sort có thể có ý nghĩa nghiệp vụ rõ ràng.

## 5. Cảnh báo của Spring Data nói điều gì?

Các phiên bản Spring Data có cơ chế cảnh báo về việc tuần tự hóa trực tiếp `PageImpl` muốn nhấn mạnh rằng cấu trúc JSON này không được bảo đảm ổn định như một biểu diễn web chuyên dụng.

Cảnh báo không có nghĩa truy vấn đã thất bại, `Page` không còn dùng được hoặc dữ liệu trong trang chắc chắn sai. Nó chỉ ra một ranh giới thiết kế: lớp triển khai phục vụ API Java đang bị đưa trực tiếp ra hợp đồng HTTP.

Không nên xử lý vấn đề chỉ bằng cách tắt logger rồi tiếp tục coi JSON đó là schema được thư viện cam kết. Tắt log không tạo một lớp chuyển đổi và không thay đổi mức phụ thuộc của client vào cấu trúc runtime.

Cũng không cần thay toàn bộ repository chỉ để giải quyết cảnh báo. Có thể giữ nguyên đường truy cập dữ liệu và thêm biểu diễn phù hợp ở ranh giới web.

## 6. Những thay đổi không tự giải quyết vấn đề

### 6.1. Đổi kiểu khai báo từ PageImpl sang Page

```java
Page<ArticleSummary> result = service.findAll(pageable);
return result;
```

Kiểu tĩnh trở nên trừu tượng hơn, nhưng đối tượng runtime và cách serializer xử lý nó có thể không thay đổi.

### 6.2. Bọc bằng ResponseEntity

```java
return ResponseEntity.ok(service.findAll(pageable));
```

`ResponseEntity` điều khiển status, header và body. Nếu body vẫn là `PageImpl` được serialize trực tiếp, cấu trúc JSON của body vẫn có cùng nguồn phụ thuộc.

### 6.3. Chỉ map entity sang DTO phần tử

```java
Page<ArticleSummary> summaries = articles.map(article ->
        new ArticleSummary(article.getId(), article.getTitle()));
```

`Page.map(...)` hữu ích để đổi kiểu nội dung và giữ thông tin phân trang. Nó không tự biến lớp bao kết quả thành một schema JSON do ứng dụng sở hữu.

Sau phép map, ứng dụng đã kiểm soát tốt hơn các trường của từng phần tử. Lớp metadata bao quanh vẫn cần được xem xét riêng.

### 6.4. Dựa vào cấu hình bỏ bớt một vài trường

Một mixin hoặc cấu hình ignore-property có thể làm JSON ngắn hơn. Tuy nhiên, chỉ bỏ các getter không muốn thấy chưa chắc đã xác định đầy đủ schema còn lại, cách biểu diễn các object lồng nhau và chính sách nâng cấp.

Nếu dùng custom serializer, hãy xem nó là thành phần duy trì hợp đồng thực sự: cần xác định schema, phạm vi đăng ký và cách kiểm chứng. Lúc đó sự ổn định đến từ serializer mà ứng dụng quản lý, không phải từ việc trả trực tiếp lớp triển khai.

## 7. Lựa chọn 1: DTO trang do ứng dụng sở hữu

Với API cần schema riêng, có thể định nghĩa lớp bao chỉ chứa các trường công khai:

```java
import java.util.List;

import org.springframework.data.domain.Page;

record PageEnvelope<T>(List<T> content, PageMetadata page) {

    static <T> PageEnvelope<T> from(Page<T> source) {
        return new PageEnvelope<>(
                List.copyOf(source.getContent()),
                new PageMetadata(
                        source.getNumber(),
                        source.getSize(),
                        source.getTotalElements(),
                        source.getTotalPages(),
                        source.hasNext()));
    }
}

record PageMetadata(
        int number,
        int size,
        long totalElements,
        int totalPages,
        boolean hasNext) {
}

record ArticleSummary(Long id, String title) {
}
```

Ví dụ dùng Java record trên phiên bản Java và cấu hình Jackson hỗ trợ record. `List.copyOf` giả định các phần tử nội dung không có `null`; nếu hợp đồng dữ liệu của ứng dụng cho phép phần tử `null`, cần chọn cách sao chép/kiểm tra phù hợp.

Controller chuyển đổi rõ ràng:

```java
@GetMapping("/api/articles")
PageEnvelope<ArticleSummary> list(Pageable pageable) {
    Page<ArticleSummary> page = service.findAll(pageable);
    return PageEnvelope.from(page);
}
```

Đây là phương án thay thế cho phương thức trả trực tiếp ở phần 2, không phải mapping bổ sung cùng đường dẫn.

Response do ứng dụng thiết kế có dạng:

```json
{
  "content": [
    {"id": 101, "title": "Bài viết A"},
    {"id": 102, "title": "Bài viết B"}
  ],
  "page": {
    "number": 0,
    "size": 2,
    "totalElements": 5,
    "totalPages": 3,
    "hasNext": true
  }
}
```

Schema này không công khai `Pageable`, các cờ nội bộ của `Sort` hoặc toàn bộ getter của `PageImpl`. Nhóm phát triển chịu trách nhiệm duy trì các record, cấu hình serializer liên quan và ý nghĩa trường đã công bố.

DTO riêng không tự bảo đảm tương thích mãi mãi. Nó tạo một nơi cụ thể để ứng dụng quyết định và kiểm soát các thay đổi hợp đồng.

## 8. Lựa chọn 2: PagedModel của Spring Data Web

Ở các phiên bản Spring Data cung cấp kiểu này, `org.springframework.data.web.PagedModel` là một biểu diễn trang được thiết kế để dùng ở ranh giới web, thay vì dựa vào JSON trực tiếp của `PageImpl`.

Có thể bọc rõ ràng:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PagedModel;
import org.springframework.web.bind.annotation.GetMapping;

@GetMapping("/api/articles")
PagedModel<ArticleSummary> list(Pageable pageable) {
    Page<ArticleSummary> page = service.findAll(pageable);
    return new PagedModel<>(page);
}
```

Đoạn này thuộc controller đã có service thích hợp. Cấu trúc khái niệm của biểu diễn Spring Data Web gồm nội dung và metadata trang:

```json
{
  "content": [
    {"id": 101, "title": "Bài viết A"},
    {"id": 102, "title": "Bài viết B"}
  ],
  "page": {
    "size": 2,
    "number": 0,
    "totalElements": 5,
    "totalPages": 3
  }
}
```

Ví dụ không yêu cầu thứ tự thuộc tính JSON cố định. Khác với DTO riêng ở phần 7, mẫu này không tự bổ sung `hasNext` vào schema minh họa.

Lớp bao giúp dùng một biểu diễn được thiết kế có chủ đích cho web. Dữ liệu trong từng phần tử vẫn do kiểu `ArticleSummary` và cấu hình serialization của ứng dụng quyết định.

Không mặc định biểu diễn đơn giản này có các liên kết `self`, `next`, `prev` hoặc là HAL. Nếu hợp đồng cần hypermedia, cần chọn thành phần phù hợp cho mục tiêu đó.

## 9. Lựa chọn 3: chế độ VIA_DTO

Với phiên bản hỗ trợ `PageSerializationMode`, có thể cấu hình Spring Data Web chuyển biểu diễn `PageImpl` thông qua DTO web:

```java
import static org.springframework.data.web.config.EnableSpringDataWebSupport.PageSerializationMode.VIA_DTO;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.web.config.EnableSpringDataWebSupport;

@Configuration
@EnableSpringDataWebSupport(pageSerializationMode = VIA_DTO)
class DataWebConfiguration {
}
```

Khi hạ tầng serialization liên quan được đăng ký và sử dụng, chế độ này cho phép biểu diễn `PageImpl` qua mô hình DTO của Spring Data Web. Controller có thể tiếp tục khai báo kiểu trả về `Page<ArticleSummary>` trong khi JSON không còn dựa trên việc xuất thẳng toàn bộ cấu trúc `PageImpl` như trước.

Cần phân biệt:

| Thành phần | Điều được thay đổi |
|---|---|
| Repository | Vẫn trả abstraction phân trang theo hợp đồng của nó |
| Service | Có thể tiếp tục xử lý `Page<T>` |
| Serialization ở ranh giới web | Dùng biểu diễn DTO thay cho dạng trực tiếp được cấu hình |
| Client | Phải hiểu schema JSON tương ứng |

Cấu hình không tự thêm DTO phần tử, không tự giới hạn dữ liệu nhạy cảm, không tự sửa truy vấn và không thay cách kho dữ liệu đếm tổng.

Phạm vi tác động có thể rộng hơn một endpoint. Trước khi dùng cho API đang có client, cần xác định các response `PageImpl` chịu ảnh hưởng. Không suy ra rằng mọi lớp tự triển khai `Page` hoặc mọi `ObjectMapper` riêng đều tự được xử lý giống nhau.

Trong ứng dụng Spring Boot, cũng cần hiểu quan hệ giữa auto-configuration và cấu hình Spring Data Web chủ động. Thêm `@EnableSpringDataWebSupport` chỉ để bật một thuộc tính có thể ảnh hưởng cách hạ tầng được cấu hình trong ứng dụng cụ thể; cần tổng hợp cấu hình có chủ đích, không đăng ký chồng nhiều cấu hình không rõ phạm vi.

## 10. PagedModel của Spring Data khác PagedModel của Spring HATEOAS

Hai kiểu có tên giống nhau nhưng thuộc hai package khác nhau:

| Kiểu | Mục tiêu |
|---|---|
| `org.springframework.data.web.PagedModel` | Biểu diễn trang đơn giản dành cho web |
| `org.springframework.hateoas.PagedModel` | Mô hình phân trang trong hệ sinh thái hypermedia của Spring HATEOAS |

Nếu dùng Spring HATEOAS, `PagedResourcesAssembler` của Spring Data có thể chuyển một `Page` thành mô hình có metadata và liên kết điều hướng thích hợp:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.PagedModel;
import org.springframework.web.bind.annotation.GetMapping;

@GetMapping("/api/articles")
PagedModel<EntityModel<ArticleSummary>> list(
        Pageable pageable,
        PagedResourcesAssembler<ArticleSummary> assembler) {

    Page<ArticleSummary> page = service.findAll(pageable);
    return assembler.toModel(page);
}
```

Ví dụ giả định dependency, hạ tầng web và assembler tương ứng đã được cấu hình. Đây lại là một phương án thay thế của endpoint, không phải đoạn mã cần ghép chung với tất cả lựa chọn trước.

Khi dùng HAL, biểu diễn có thể có các thành phần như `_embedded`, `_links` và metadata `page`, tùy cấu hình và quan hệ tài nguyên. Tên quan hệ, nội dung trang rỗng và loại liên kết không nên được suy ra từ một JSON ví dụ của một DTO khác.

Cần công bố media type và schema phù hợp với lựa chọn hypermedia. Việc import nhầm `PagedModel` giữa hai package có thể dẫn tới hiểu sai cả kiểu trả về lẫn cấu trúc client cần đọc.

## 11. Chọn một biểu diễn theo hợp đồng API

| Nhu cầu | Lựa chọn có thể phù hợp |
|---|---|
| API có schema riêng, tên trường riêng, metadata nghiệp vụ | DTO trang do ứng dụng sở hữu |
| Muốn biểu diễn trang đơn giản do Spring Data Web cung cấp | Bọc `org.springframework.data.web.PagedModel` |
| Muốn áp dụng biểu diễn DTO cho các `PageImpl` trong phạm vi cấu hình | `VIA_DTO`, nếu phiên bản và hạ tầng hỗ trợ |
| Client điều hướng bằng liên kết hypermedia | Spring HATEOAS và assembler phù hợp |
| API cũ đã có nhiều client phụ thuộc JSON trực tiếp | Lập kế hoạch chuyển đổi hợp đồng trước khi đổi biểu diễn |

Một API không nên đổi ngẫu nhiên giữa các schema chỉ vì từng controller được viết ở thời điểm khác nhau. Có thể có nhiều biểu diễn nếu chúng thuộc các hợp đồng hoặc media type được công bố rõ ràng.

Nếu dự án chưa hỗ trợ `VIA_DTO`, DTO riêng vẫn là một lựa chọn kiểm soát schema. Không cần cố dùng annotation hoặc lớp không có trong phiên bản đang chạy.

## 12. Metadata cũng cần có ý nghĩa ổn định

### 12.1. Chỉ số trang trên request và response

`Page.getNumber()` dùng chỉ số bắt đầu từ 0. Cấu hình web nhận tham số trang từ 1 không tự thay đổi bản chất này của đối tượng `Page`.

Nếu API muốn response bắt đầu từ 1, cần chuyển đổi rõ ràng trong DTO riêng và công bố quy ước. Không trả một con số ở dạng 0-based nhưng viết tài liệu như thể đó là số thứ tự trên giao diện bắt đầu từ 1.

### 12.2. Kích thước trang khác số phần tử thực có

Với trang cuối, `size` có thể là 20 nhưng `content` chỉ có 3 phần tử. `size` mô tả kích thước trang; số phần tử thực tế là độ dài nội dung hoặc `getNumberOfElements()` nếu hợp đồng muốn công khai trường đó.

Nếu server áp dụng giới hạn size, metadata cần phản ánh trang thực tế được tạo, thay vì sao chép nguyên một query parameter chưa qua chính sách giới hạn.

### 12.3. Tổng số phần tử thuộc phạm vi truy vấn

`totalElements` phải được hiểu theo tập dữ liệu mà truy vấn đang mô tả: điều kiện lọc, tenant, trạng thái và quyền truy cập tương ứng. Nó không mặc định là số bản ghi của toàn bộ bảng hoặc collection.

Việc đếm có thể có chi phí và có thể được module tối ưu trong một số trường hợp. Đổi serializer không loại bỏ nhu cầu tính tổng khi ứng dụng vẫn dùng hợp đồng `Page` có tổng số.

### 12.4. Trang rỗng và trang vượt phạm vi

Một endpoint có thể chọn trả HTTP 200 với `content: []` khi không có phần tử. Cần xác định metadata tương ứng cho truy vấn không có kết quả và cho trang yêu cầu vượt quá phạm vi.

Hai trường hợp không nhất thiết có cùng tổng số phần tử. Trang yêu cầu vượt phạm vi có thể rỗng trong khi toàn bộ tập kết quả vẫn có dữ liệu.

Không sửa total về 0 chỉ vì `content` của trang hiện tại rỗng. Ngược lại, khi tự dựng `PageImpl`, cần cung cấp thông tin nhất quán; lớp triển khai có thể điều chỉnh total trong một số tình huống để giảm bất nhất với nội dung trang cuối.

### 12.5. Sort và tính ổn định của nội dung

Một DTO ổn định không làm thứ tự dữ liệu tự ổn định. Nếu phân trang offset mà nhiều phần tử bằng nhau trên trường sort, cần khóa phá hòa phù hợp, chẳng hạn ID duy nhất.

Ngay cả khi có thứ tự xác định, dữ liệu vẫn có thể thay đổi giữa các request. JSON ổn định và snapshot dữ liệu là hai yêu cầu cần được xử lý ở những lớp khác nhau.

## 13. Ranh giới với repository, projection và module lưu trữ

Một cách phân chia trách nhiệm hữu ích:

```text
Repository/module
    Chọn truy vấn, lọc dữ liệu, áp dụng phân trang và trả kết quả.

Service
    Áp dụng nghiệp vụ, quyền truy cập, transaction và chuyển nội dung.

Biểu diễn web
    Quyết định schema, tên trường, metadata và liên kết công khai.

Serializer
    Mã hóa biểu diễn đã chọn theo cấu hình HTTP của ứng dụng.
```

Derived query hoặc repository fragment có thể trả `Page` theo khả năng module. Projection có thể giảm hoặc tổ chức dữ liệu phần tử theo cách module hỗ trợ. Các lựa chọn ấy không tự xác định schema của lớp bao HTTP.

Tương tự, một DTO web không làm module hỗ trợ thêm kiểu truy vấn, sort trên mọi thuộc tính hoặc phân trang giống nhau ở mọi kho dữ liệu.

Nếu ứng dụng thực tế chỉ cần biết còn trang tiếp theo hay không, có thể xem xét `Slice` và một hợp đồng response phù hợp. Không nên tạo `totalElements` giả để ép kết quả không có tổng số vào schema của `Page`.

Nếu chuyển sang scrolling/cursor, cần công bố hợp đồng cursor tương ứng. Việc thay `PageImpl` bằng một wrapper không biến offset pagination thành keyset pagination.

## 14. Chuyển đổi một API đã có client

Giả sử client cũ đọc:

```javascript
const pageNumber = response.number;
const rows = response.content;
```

Sau khi đổi sang DTO web, metadata có thể nằm dưới `response.page.number`. Dù server chỉ thay một annotation cấu hình, client vẫn phải thay đổi đường dẫn truy cập.

Một kế hoạch chuyển đổi cần xác định:

1. Schema đang được client sử dụng thực tế, gồm cả các trường lồng nhau.
2. Schema đích, quy ước số trang và cách xử lý trang rỗng.
3. Phạm vi endpoint bị ảnh hưởng bởi cấu hình serialization.
4. Cách phối hợp thay đổi client, phiên bản API hoặc media type khi cần.
5. Tiêu chí kiểm chứng response sau nâng cấp dependency và sau chuyển đổi.

Nếu phải giữ schema cũ trong một giai đoạn, có thể dùng DTO hoặc serializer tường minh để duy trì đúng phần hợp đồng cũ mà ứng dụng chọn hỗ trợ. Việc chủ động tái hiện schema là một quyết định duy trì API; nó khác với tiếp tục dựa vào một lớp triển khai chưa có cam kết JSON tương ứng.

Không xem việc cảnh báo biến mất là tiêu chí hoàn tất chuyển đổi. Tiêu chí cần là client nhận đúng schema và ý nghĩa dữ liệu đã được thống nhất.

## 15. Tình huống kiểm chứng biểu diễn

| Tình huống | Điều cần xác minh |
|---|---|
| Trang đầu có dữ liệu | Nội dung, số trang, size và tổng số đúng hợp đồng |
| Trang cuối chưa đủ size | Phân biệt kích thước trang với số phần tử thực tế |
| Truy vấn không có kết quả | Danh sách rỗng và metadata được biểu diễn nhất quán |
| Trang yêu cầu vượt phạm vi | Không suy ra toàn bộ tập dữ liệu có tổng số bằng 0 |
| Server giới hạn size | Metadata thể hiện giá trị có hiệu lực |
| Request dùng số trang từ 1 | Response vẫn đúng quy ước đã công bố |
| Nội dung dùng DTO/projection | Không lẫn schema phần tử với schema metadata |
| Bật `VIA_DTO` | Các endpoint trong phạm vi nhận đúng biểu diễn mới |
| Dùng HAL | Media type, quan hệ tài nguyên và liên kết phù hợp |
| Nâng cấp Spring Data/Jackson | Hợp đồng HTTP được giữ theo lựa chọn của ứng dụng |

Kiểm chứng nên bám schema và ý nghĩa trường mà API công bố. So sánh nguyên một chuỗi JSON có thể tạo nhiễu do thứ tự thuộc tính, trong khi bỏ qua toàn bộ metadata lại không phát hiện được thay đổi làm client hỏng.

Nếu client chỉ chấp nhận một tập trường cố định, cần công bố chính sách về trường bổ sung. Không tự cho rằng mọi client đều bỏ qua trường lạ hoặc mọi thay đổi thêm trường đều an toàn trong thực tế.

## 16. Bài tập tự kiểm tra

### Tình huống 1: Controller đã khai báo Page nên cho rằng JSON được trừu tượng hóa

Runtime vẫn trả `PageImpl` và Jackson đang dùng cách xuất trực tiếp.

**Phân tích:** abstraction ở kiểu khai báo Java không tự tạo DTO cho HTTP. Cần chọn biểu diễn web có chủ đích hoặc cấu hình cơ chế chuyển đổi phù hợp.

### Tình huống 2: Đã map entity sang ArticleSummary nhưng vẫn có cảnh báo

Service trả `Page<ArticleSummary>` sau `Page.map(...)`.

**Phân tích:** schema của từng phần tử đã được kiểm soát tốt hơn, nhưng lớp bao trang vẫn có thể là `PageImpl` tuần tự hóa trực tiếp. Cần giải quyết riêng biểu diễn metadata.

### Tình huống 3: Bật VIA_DTO và frontend không còn tìm thấy response.number

Frontend cũ đọc metadata ở cấp gốc, trong khi biểu diễn mới đặt metadata dưới `page`.

**Phân tích:** một cấu hình server có thể thay đổi hợp đồng HTTP trên nhiều endpoint. Cần phối hợp chuyển schema hoặc version hợp đồng với client.

### Tình huống 4: Import PagedModel của Spring HATEOAS nhưng mong JSON đơn giản

Nhóm phát triển nhầm hai lớp cùng tên.

**Phân tích:** kiểm tra package và mục tiêu biểu diễn. `org.springframework.data.web.PagedModel` và `org.springframework.hateoas.PagedModel` phục vụ các mô hình khác nhau; cấu hình media type cũng cần phù hợp.

### Tình huống 5: Trang có content rỗng nên DTO đặt totalElements bằng 0

Request đang yêu cầu một trang vượt phạm vi của tập kết quả có dữ liệu.

**Phân tích:** nội dung rỗng của trang hiện tại không chứng minh tổng tập kết quả bằng 0. Metadata cần được lấy và diễn giải theo kết quả truy vấn, không suy ra chỉ từ độ dài `content`.

### Tình huống 6: Tắt logger để chuẩn bị nâng cấp

Cảnh báo không còn xuất hiện nhưng client vẫn phụ thuộc cấu trúc `pageable` và `sort` trực tiếp.

**Phân tích:** thay đổi logging không bảo vệ schema. Cần chủ động chọn và duy trì biểu diễn HTTP, rồi kiểm chứng các đường truy cập dữ liệu mà client thực sự sử dụng.

`Page` và `PageImpl` hữu ích cho việc làm việc với kết quả phân trang trong Java. Để API web có hợp đồng kiểm soát được, hãy đặt một biểu diễn rõ ràng ở ranh giới serialization, công bố ý nghĩa metadata và duy trì sự tương thích của biểu diễn đó cùng với client.

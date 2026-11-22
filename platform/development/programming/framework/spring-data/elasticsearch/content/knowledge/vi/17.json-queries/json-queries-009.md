# `@SearchTemplateQuery` khi phiên bản Spring Data hỗ trợ

Spring Data Elasticsearch hỗ trợ Elasticsearch Search Templates để ứng dụng tái sử dụng một mẫu Query DSL được lưu trên cluster. Khi muốn một Repository method gọi trực tiếp stored search template, có thể dùng annotation `@SearchTemplateQuery` trên method đó.

Annotation này chỉ định ID của template. Các tham số của Repository method được Spring Data gửi vào template dưới dạng các cặp key/value, trong đó key là tên tham số method và value là giá trị thực tế tại thời điểm gọi. Vì vậy, tên biến trong method phải khớp với placeholder Mustache trong template.

Điểm quan trọng về phiên bản:

- `SearchTemplateQuery` (query object dùng trong custom repository) có từ Spring Data Elasticsearch **5.1**.
- Annotation `@SearchTemplateQuery` cho Repository method có từ **5.5**.
- Nếu dự án dùng Spring Data Elasticsearch thấp hơn 5.5, không thể dùng annotation này; có thể dùng `SearchTemplateQuery` qua custom repository nếu phiên bản từ 5.1 trở lên.
- Với phiên bản cũ hơn 5.1, cần dùng API truy vấn khác hoặc nâng cấp Spring Data Elasticsearch.

## 1. Search Template là gì?

Search Template là một mẫu truy vấn được lưu trong Elasticsearch dưới dạng stored script. Template thường dùng ngôn ngữ Mustache để nhận tham số lúc chạy. Thay vì gửi toàn bộ cấu trúc Query DSL từ ứng dụng trong mỗi request, ứng dụng chỉ gửi ID template cùng các giá trị tham số.

Ví dụ một template tìm sách theo tiêu đề có thể chứa placeholder `{{title}}`:

```json
{
  "query": {
    "match": {
      "title": "{{title}}"
    }
  }
}
```

Khi ứng dụng truyền `title = "Spring Data"`, Elasticsearch render template thành Query DSL có giá trị tìm kiếm tương ứng rồi thực hiện search.

Luồng hoạt động:

```text
Triển khai / quản trị cluster
          |
          | Đăng ký stored script Mustache
          v
Elasticsearch: script id = book-by-title

Spring Data Repository
          |
          | @SearchTemplateQuery(id = "book-by-title")
          | title = "Spring Data"
          v
Spring Data Elasticsearch
          |
          | Search template request
          v
Elasticsearch render Mustache template
          |
          v
Thực thi Query DSL và trả SearchHits
```

Template được lưu trên cluster, nên nó có thể được tái sử dụng bởi nhiều instance ứng dụng hoặc nhiều service có quyền gọi template đó. Nội dung template có vòng đời triển khai riêng với Java code; thay đổi template đã lưu có thể làm thay đổi kết quả tìm kiếm mà không cần thay đổi Repository interface.

## 2. Khác biệt giữa `@SearchTemplateQuery` và `SearchTemplateQuery`

Hai tên này gần giống nhau nhưng là hai API ở hai tầng khác nhau:

| Thành phần | Package | Có từ | Mục đích |
|---|---|---:|---|
| `@SearchTemplateQuery` | `org.springframework.data.elasticsearch.annotations` | 5.5 | Đánh dấu Repository method dùng một stored search template. |
| `SearchTemplateQuery` | `org.springframework.data.elasticsearch.core.query` | 5.1 | Query object để custom repository gọi template qua `ElasticsearchOperations`. |
| `SearchTemplateQueryBuilder` | `org.springframework.data.elasticsearch.core.query` | 5.1 | Builder để thiết lập template ID/source và parameter map cho query object. |

Annotation chỉ cần khai báo `id` của stored template. Query object linh hoạt hơn vì có thể truyền `Map<String, Object>` bằng `withParams(...)`, phù hợp khi ứng dụng cần tự xây dựng parameter map, tích hợp `Pageable` hoặc đang dùng Spring Data Elasticsearch 5.1–5.4.

Không nhầm `@SearchTemplateQuery` với `@Query`. `@Query` nhận Query DSL JSON gắn trong annotation; `@SearchTemplateQuery` tham chiếu template đã được đăng ký trong Elasticsearch.

## 3. Đăng ký stored search template

Trước khi gọi Repository method, template phải tồn tại trong Elasticsearch. Spring Data cung cấp `ScriptOperations`; interface `ElasticsearchOperations` mở rộng chức năng này và có thể dùng để đăng ký stored script.

Ví dụ đăng ký template tìm sách theo tiêu đề:

```java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.script.Script;
import org.springframework.stereotype.Component;

@Component
public class SearchTemplateProvisioner {

    private final ElasticsearchOperations operations;

    public SearchTemplateProvisioner(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void registerBookSearchTemplate() {
        Script script = Script.builder()
                .withId("book-by-title")
                .withLanguage("mustache")
                .withSource("""
                        {
                          "query": {
                            "match": {
                              "title": "{{title}}"
                            }
                          }
                        }
                        """)
                .build();

        operations.putScript(script);
    }
}
```

Các phần quan trọng:

- `withId("book-by-title")` đặt ID của stored script; Repository method sẽ tham chiếu chính xác ID này.
- `withLanguage("mustache")` khai báo ngôn ngữ template. Search template sử dụng Mustache.
- `withSource(...)` chứa nội dung Query DSL có placeholder.
- `putScript(...)` gửi stored script lên cluster.

Nên đăng ký hoặc cập nhật template trong bước provisioning/deployment phù hợp, không gọi `putScript` cho mỗi request tìm kiếm. Khi thay đổi template, hãy kiểm soát version và kiểm thử trước khi cập nhật ID đang được ứng dụng sử dụng.

Có thể đăng ký script bằng Elasticsearch Stored Scripts API trực tiếp:

```http
PUT /_scripts/book-by-title
Content-Type: application/json

{
  "script": {
    "lang": "mustache",
    "source": "{ \"query\": { \"match\": { \"title\": \"{{title}}\" } } }"
  }
}
```

Hai cách trên cùng tạo stored script. Nếu dùng REST API hoặc deployment tool để quản lý template, ứng dụng runtime chỉ cần quyền thực thi/search phù hợp; không nhất thiết phải có quyền quản trị stored scripts.

## 4. Dùng `@SearchTemplateQuery` trên Repository method

Khi dự án dùng Spring Data Elasticsearch **5.5 trở lên**, có thể import annotation và gắn nó lên method:

```java
import org.springframework.data.elasticsearch.annotations.SearchTemplateQuery;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;
import org.springframework.data.elasticsearch.core.SearchHits;

public interface BookRepository
        extends ElasticsearchRepository<Book, String> {

    @SearchTemplateQuery(id = "book-by-title")
    SearchHits<Book> findByTitle(String title);
}
```

Khi gọi:

```java
SearchHits<Book> hits = bookRepository.findByTitle("Spring Data");
```

Spring Data dùng template ID `book-by-title` và truyền tham số `title` với giá trị `Spring Data`. Placeholder `{{title}}` trong stored script được render bằng giá trị này.

Trong ví dụ, tên tham số Java là `title`, trùng với tên placeholder của Mustache. Nếu đổi method thành `findByTitle(String searchText)`, key được gửi sẽ là `searchText`; template vẫn chờ `title` nên không nhận được giá trị như mong muốn. Hãy giữ tên tham số đồng bộ với template và bảo đảm build giữ metadata tên tham số cho Spring Data (thường bật compiler option `-parameters` nếu cấu hình dự án chưa bật).

Annotation có thuộc tính bắt buộc `id`; nó không có thuộc tính `params` để khai báo map hoặc cú pháp placeholder vị trí `?0` như `@Query`. Giá trị được truyền theo tên tham số method.

### Return type của Repository method

Tài liệu Spring Data Elasticsearch minh họa `SearchHits<Book>` cho Repository method dùng `@SearchTemplateQuery`. Kiểu này giữ thông tin của từng hit, score và metadata tìm kiếm.

```java
SearchHits<Book> hits = bookRepository.findByTitle("Spring Data");

List<Book> books = hits.getSearchHits().stream()
        .map(SearchHit::getContent)
        .toList();
```

Các kiểu kết quả Repository được hỗ trợ còn phụ thuộc query execution và phiên bản Spring Data. Khi cần metadata tìm kiếm hoặc score, `SearchHits<T>` là lựa chọn rõ ràng. Khi thiết kế method trả `Page`, `SearchPage` hoặc `List`, hãy xác nhận return type được hỗ trợ cho loại query và cách template xử lý phân trang.

## 5. Template có nhiều tham số

Một template có thể nhận nhiều giá trị. Ví dụ tìm sách theo tiêu đề và lọc theo thể loại:

```json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "title": "{{title}}"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "category": "{{category}}"
          }
        }
      ]
    }
  }
}
```

Repository method:

```java
public interface BookRepository
        extends ElasticsearchRepository<Book, String> {

    @SearchTemplateQuery(id = "book-by-title-and-category")
    SearchHits<Book> findByTitleAndCategory(String title, String category);
}
```

Tên hai tham số phải khớp `{{title}}` và `{{category}}`. Khi gọi:

```java
SearchHits<Book> hits =
        bookRepository.findByTitleAndCategory("Spring Data", "TECHNICAL");
```

Spring Data truyền hai cặp key/value tương ứng vào template. Với tham số có cấu trúc như collection hoặc object, hãy kiểm tra kiểu dữ liệu mà Mustache nhận được và cách template render nó thành JSON hợp lệ.

### Điều kiện tùy chọn trong Mustache

Mustache hỗ trợ section để thêm một phần của template khi tham số có giá trị. Ví dụ:

```json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "title": "{{title}}"
          }
        }
      ]
      {{#category}},
      "filter": [
        {
          "term": {
            "category": "{{category}}"
          }
        }
      ]
      {{/category}}
    }
  }
}
```

Section `{{#category}} ... {{/category}}` chỉ render khi tham số `category` có giá trị phù hợp. Cần kiểm tra JSON sau khi render cho cả trường hợp có và không có tham số tùy chọn. Dấu phẩy và dấu ngoặc phải được đặt sao cho cả hai nhánh đều tạo JSON hợp lệ.

Với điều kiện phức tạp, nhiều collection hoặc cấu trúc lồng nhau, hãy viết test riêng cho template và các tổ hợp tham số. Không nên tạo một template quá nhiều nhánh đến mức khó đọc và khó xác minh.

## 6. Phân trang và sắp xếp trong Search Template

Search template gửi toàn bộ phần search body theo nội dung template đã lưu. Cần chú ý: dù `SearchTemplateQuery` là implementation của interface `Query`, không phải mọi thuộc tính query chung đều được áp dụng tự động. Tài liệu Spring Data nêu rõ `Pageable` và `Sort` được đặt trên `SearchTemplateQuery` có thể bị bỏ qua; các giá trị tương ứng cần được đưa vào stored template và truyền như tham số.

Ví dụ template có `from`, `size` và sort:

```json
{
  "query": {
    "match": {
      "title": "{{title}}"
    }
  },
  "from": {{from}},
  "size": {{size}},
  "sort": [
    {
      "published_at": {
        "order": "{{sortDirection}}"
      }
    }
  ]
}
```

Với Repository annotation, có thể khai báo các giá trị phân trang như tham số method để template nhận được chúng:

```java
public interface BookRepository
        extends ElasticsearchRepository<Book, String> {

    @SearchTemplateQuery(id = "book-by-title-page")
    SearchHits<Book> findByTitle(String title, int from, int size);
}
```

Khi gọi:

```java
int page = 0;
int pageSize = 20;
int from = page * pageSize;

SearchHits<Book> hits =
        bookRepository.findByTitle("Spring Data", from, pageSize);
```

Template nhận `title`, `from`, `size`. Cách này khiến hợp đồng method hiển thị rõ các tham số mà template cần.

Nếu muốn API service nhận `Pageable`, nên dùng custom repository implementation để chuyển `pageable.getOffset()` và `pageable.getPageSize()` thành template params. Ví dụ:

```java
interface BookSearchRepository {
    SearchPage<Book> searchByTitle(String title, Pageable pageable);
}
```

```java
class BookSearchRepositoryImpl implements BookSearchRepository {

    private final ElasticsearchOperations operations;

    BookSearchRepositoryImpl(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    @Override
    public SearchPage<Book> searchByTitle(String title, Pageable pageable) {
        SearchTemplateQuery query = SearchTemplateQuery.builder()
                .withId("book-by-title-page")
                .withParams(Map.of(
                        "title", title,
                        "from", pageable.getOffset(),
                        "size", pageable.getPageSize()
                ))
                .build();

        SearchHits<Book> searchHits = operations.search(query, Book.class);
        return SearchHitSupport.searchPageFor(searchHits, pageable);
    }
}
```

Trong ví dụ custom repository, template `book-by-title-page` phải chứa `from` và `size` placeholder. Nếu cần sort động, truyền một giá trị đã được whitelist và biểu diễn nó theo cấu trúc mà template hỗ trợ; không nối trực tiếp chuỗi sort tùy ý từ client vào JSON.

## 7. Dùng `SearchTemplateQuery` trong custom repository

Nếu dự án dùng Spring Data Elasticsearch 5.1–5.4 hoặc cần tự xây dựng parameter map, có thể dùng query object trực tiếp thay vì annotation.

Ví dụ:

```java
import java.util.Map;

import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.query.SearchTemplateQuery;

public class BookSearchRepositoryImpl implements BookSearchRepository {

    private final ElasticsearchOperations operations;

    public BookSearchRepositoryImpl(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    @Override
    public SearchHits<Book> searchByTitle(String title) {
        SearchTemplateQuery query = SearchTemplateQuery.builder()
                .withId("book-by-title")
                .withParams(Map.of("title", title))
                .build();

        return operations.search(query, Book.class);
    }
}
```

Ở đây:

- `withId(...)` chọn stored script.
- `withParams(...)` truyền map tham số tường minh.
- `operations.search(...)` thực thi template và ánh xạ kết quả thành `Book`.

Query builder còn có `withSource(...)` trong các phiên bản hỗ trợ nếu cần cung cấp source template thay vì chỉ ID. Tuy nhiên, với template được quản lý tập trung trên cluster, nên dùng ID và stored script để dễ kiểm soát phiên bản, quyền truy cập và triển khai.

## 8. So sánh `@SearchTemplateQuery` với các cách khai báo query khác

| Cách truy vấn | Nơi định nghĩa query | Truyền tham số | Khi phù hợp |
|---|---|---|---|
| Derived query method | Tên Repository method | Tham số method theo thứ tự/property | Điều kiện đơn giản, dễ diễn đạt bằng tên method. |
| `@Query` | JSON Query DSL trong annotation | Placeholder `?0`, `?1` hoặc SpEL | Query cố định, gọn và chỉ dùng trong một Repository. |
| `CriteriaQuery` | Java Criteria API | Java object và điều kiện được ghép trong code | Query động theo form tìm kiếm hoặc nhiều điều kiện tùy chọn. |
| `NativeQuery` | Elasticsearch Java API Client Query DSL | Typed Java builder | Query phức tạp, cần tính năng native của Elasticsearch. |
| `@SearchTemplateQuery` | Stored Mustache template trên cluster | Tên tham số method thành key/value | Query tái sử dụng, được quản lý độc lập với code. |
| `SearchTemplateQuery` | Stored template hoặc source qua query builder | `Map<String, Object>` | Custom repository, cần parameter map rõ ràng hoặc tương thích phiên bản trước 5.5. |

Không nên dùng Search Template chỉ vì nó là API mới. Nếu query đơn giản và chỉ có một nơi sử dụng, derived query hoặc `@Query` có thể dễ bảo trì hơn. Search Template hữu ích khi cùng một query cần dùng ở nhiều nơi, cần tách nội dung query khỏi code hoặc muốn quản lý template tập trung trên cluster.

## 9. Giới hạn và điều cần lưu ý

### Template phải tồn tại trước khi gọi Repository

Annotation chỉ tham chiếu ID; nó không tự đăng ký template. Nếu stored script chưa được tạo hoặc ID sai, request tìm kiếm sẽ thất bại. Cần triển khai template trước khi rollout ứng dụng sử dụng ID đó.

### Tên tham số phải khớp

Với annotation, key được tạo từ tên tham số method. Nếu method có `String searchText` nhưng template dùng `{{title}}`, tham số không tự đổi thành `title`. Hãy thống nhất tên hoặc dùng custom repository với map tường minh.

### Không có thuộc tính inline JSON trên annotation

`@SearchTemplateQuery` nhận `id`; nó không thay thế `@Query` với JSON inline. Nếu muốn định nghĩa query ngay trên Repository method, `@Query` là API khác.

### Phân trang và sort cần nằm trong template

Không giả định `Pageable` hoặc `Sort` được áp dụng tự động vào nội dung stored script. Đưa `from`, `size`, sort hoặc tham số tương ứng vào template và truyền giá trị phù hợp. Với custom repository, tự tạo map từ `Pageable` là cách rõ ràng.

### Template là cấu hình thực thi trên cluster

Người có quyền thay đổi stored script có thể thay đổi hành vi truy vấn của ứng dụng. Quản lý quyền ghi stored scripts riêng với quyền search runtime khi phù hợp. Nên version hóa template và có quy trình kiểm thử trước khi cập nhật.

### Mustache không thay thế validation

Template chỉ render request. Ứng dụng vẫn phải validate đầu vào, giới hạn page size, whitelist sort field và bảo đảm các tham số có kiểu phù hợp. Không để người dùng truyền trực tiếp một đoạn Query DSL hoặc tên field tùy ý qua API công khai.

## 10. Kiểm thử Search Template

Nên kiểm thử cả stored script và Repository method.

### Kiểm tra template được đăng ký

Trong integration test, tạo stored script bằng `putScript` hoặc provision template trước khi test. Có thể đọc lại template qua `getScript` để xác nhận ID và source tồn tại.

### Kiểm tra render với các giá trị đại diện

Thử các trường hợp:

- Chuỗi thông thường.
- Chuỗi có dấu câu, dấu nháy hoặc ký tự Unicode.
- Tham số tùy chọn có và không có giá trị.
- Collection rỗng và collection có phần tử nếu template hỗ trợ danh sách.
- Giá trị phân trang đầu tiên và các trang tiếp theo.
- Sort theo các lựa chọn đã được whitelist.

Đảm bảo template sau khi render tạo Query DSL hợp lệ và không làm thay đổi ý nghĩa truy vấn ngoài mong muốn.

### Kiểm tra Repository method

Ví dụ test ở mức ý tưởng:

```java
@Test
void searchTemplateShouldFindBooksByTitle() {
    // Arrange: đăng ký stored template và index các Book mẫu.
    // Act: gọi bookRepository.findByTitle("Spring Data").
    // Assert: kết quả chứa đúng các Book mong đợi.
}
```

Test phải chạy với đúng phiên bản Spring Data Elasticsearch đang dùng. Đặc biệt, kiểm tra việc bind tên tham số; nếu giá trị không được truyền đúng, xem lại metadata tên tham số và placeholder trong template.

### Kiểm tra khi cập nhật template

Nếu template có nhiều consumer, hãy chạy bộ regression test trên các truy vấn sử dụng ID đó trước khi cập nhật stored script dùng chung. Có thể dùng ID có version, ví dụ `book-by-title-v1` và `book-by-title-v2`, rồi chuyển Repository method sang ID mới theo một lần phát hành có kiểm soát.

## 11. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không import được `@SearchTemplateQuery` | Spring Data Elasticsearch đang dùng thấp hơn 5.5. | Nâng lên 5.5+ hoặc dùng `SearchTemplateQuery` trong custom repository từ 5.1+. |
| Template không tìm thấy | Stored script chưa được đăng ký hoặc sai ID. | Kiểm tra `putScript`, Stored Scripts API và ID trong annotation. |
| Placeholder không nhận giá trị | Tên tham số method khác tên placeholder Mustache. | Đồng bộ tên method parameter và template key; kiểm tra compiler parameter metadata. |
| Template render ra JSON không hợp lệ | Dấu ngoặc, dấu phẩy hoặc kiểu dữ liệu placeholder không phù hợp. | Test template với tất cả nhánh có/không có tham số. |
| Gọi method nhưng kết quả rỗng | Query DSL trong template sai, field mapping/analyzer không phù hợp hoặc tham số không đúng. | Kiểm tra stored script, dữ liệu mẫu và mapping. |
| `Pageable` không làm thay đổi kết quả trang | `from`/`size` không được đưa vào stored template. | Thêm placeholder và truyền offset/size rõ ràng. |
| Sort bị bỏ qua | Template không có sort hoặc chỉ set `Sort` trên query object. | Định nghĩa sort trong template và truyền tham số đã whitelist. |
| Build chạy nhưng runtime không bind được tên tham số | Metadata tên tham số không có hoặc khác với template key. | Bật `-parameters`, kiểm tra parameter discovery hoặc dùng custom repository map tường minh. |
| Dùng `@Query` nhưng mong stored script được gọi | Hai annotation có cơ chế khác nhau. | Dùng `@SearchTemplateQuery(id = ...)` cho stored template. |

## 12. Quy trình triển khai phù hợp

1. **Kiểm tra phiên bản:** xác nhận Spring Data Elasticsearch đang dùng có hỗ trợ annotation hay chỉ có query object.
2. **Thiết kế template:** viết Query DSL và các placeholder Mustache cần thiết.
3. **Đăng ký template:** dùng `ElasticsearchOperations.putScript` hoặc Stored Scripts API.
4. **Tạo Repository method:** dùng `@SearchTemplateQuery(id = "...")` nếu phiên bản từ 5.5; nếu không, tạo custom repository với `SearchTemplateQuery` khi phiên bản từ 5.1.
5. **Ánh xạ tham số:** bảo đảm tên method parameter khớp template key hoặc tạo `Map` tường minh trong custom repository.
6. **Thiết kế phân trang/sort:** đưa `from`, `size`, sort vào template và truyền các giá trị đã validate.
7. **Kiểm thử:** xác nhận template tồn tại, render hợp lệ, query trả kết quả đúng và tham số được bind đúng.
8. **Triển khai theo thứ tự:** đăng ký template trước, sau đó rollout ứng dụng gọi template đó.
9. **Theo dõi:** quan sát lỗi script/search, latency và thay đổi kết quả sau khi cập nhật template.

## 13. Những điểm cần nhớ

- `@SearchTemplateQuery` đánh dấu Repository method dùng stored search template theo ID.
- Annotation `@SearchTemplateQuery` có từ Spring Data Elasticsearch 5.5; query object `SearchTemplateQuery` có từ 5.1.
- Stored search template phải được đăng ký trong Elasticsearch và dùng ngôn ngữ Mustache.
- `@SearchTemplateQuery` chỉ định ID; tham số method được gửi thành key/value theo tên tham số.
- Tên placeholder như `{{title}}` phải khớp tên tham số `title` trong Repository method.
- Với phiên bản 5.1–5.4, có thể dùng `SearchTemplateQuery.builder()` trong custom repository và truyền map qua `withParams(...)`.
- Template phải chứa các giá trị `from`, `size` và sort nếu truy vấn cần phân trang hoặc sắp xếp; không mặc định `Pageable`/`Sort` trên query object sẽ tự thay đổi stored script.
- Search Template phù hợp với query tái sử dụng và được quản lý độc lập; query đơn giản có thể dùng derived method, `@Query` hoặc `CriteriaQuery`.
- Kiểm tra phiên bản, parameter name metadata, JSON sau render và quyền quản lý stored scripts trước khi triển khai.

`@SearchTemplateQuery` giúp Repository method gọi stored search template bằng một khai báo ngắn, trong khi query DSL được quản lý tập trung trên Elasticsearch. Hãy kiểm tra phiên bản Spring Data, đăng ký template trước khi sử dụng và giữ hợp đồng tham số rõ ràng để việc tìm kiếm có thể tái sử dụng, kiểm thử và triển khai an toàn.

## Tài liệu tham khảo

- [Spring Data Elasticsearch — Query methods](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories/elasticsearch-repository-queries.html)
- [Spring Data Elasticsearch — Search Template support](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/misc.html)
- [Javadoc — `@SearchTemplateQuery`](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/annotations/SearchTemplateQuery.html)
- [Javadoc — `SearchTemplateQuery`](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/query/SearchTemplateQuery.html)

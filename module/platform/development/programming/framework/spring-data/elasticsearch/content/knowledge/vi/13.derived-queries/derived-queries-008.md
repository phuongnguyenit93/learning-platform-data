# `OrderBy`, `Sort` và `Pageable` trong phương thức truy vấn

Khi truy vấn dữ liệu bằng Spring Data Elasticsearch, ứng dụng thường cần kiểm soát thứ tự kết quả và chỉ lấy một phần document trong mỗi lần gọi. Spring Data hỗ trợ ba cách diễn đạt nhu cầu này trong repository method:

- `OrderBy` khai báo thứ tự sắp xếp cố định ngay trong tên phương thức.
- `Sort` cho phép bên gọi truyền tiêu chí sắp xếp tại thời điểm chạy.
- `Pageable` mô tả trang cần lấy, kích thước trang và có thể bao gồm cả `Sort`.

Các cơ chế này giúp repository method ngắn gọn và dễ đọc. Tuy nhiên, Elasticsearch chỉ có thể sort hiệu quả trên những field có mapping phù hợp; phân trang theo offset cũng có giới hạn khi đi sâu vào tập kết quả lớn.

## 1. Chuẩn bị domain model và repository

Giả sử ứng dụng lưu document sản phẩm với các thuộc tính category, tên, giá và thời điểm tạo:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Long)
    private Long price;

    @Field(type = FieldType.Date)
    private Instant createdAt;

    // Constructor, getters và setters
}
~~~

Repository có thể kế thừa `ElasticsearchRepository` và khai báo các phương thức truy vấn theo tên:

~~~java
import java.util.List;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    List<ProductDocument> findByCategoryOrderByCreatedAtDesc(String category);

    List<ProductDocument> findByCategory(String category, Sort sort);

    Page<ProductDocument> findByCategory(String category, Pageable pageable);
}
~~~

Ba phương thức có cùng điều kiện lọc `category` nhưng cho phép caller kiểm soát thứ tự hoặc trang theo những cách khác nhau. Các method được phân tích từ tên và tham số; Spring Data tạo truy vấn Elasticsearch tương ứng.

## 2. Sắp xếp cố định bằng `OrderBy`

`OrderBy` là phần hậu tố trong tên derived query method. Nó mô tả field cần sắp xếp và chiều tăng/giảm.

Cú pháp khái quát:

~~~text
findBy<Điều kiện>OrderBy<TênField>Asc
findBy<Điều kiện>OrderBy<TênField>Desc
~~~

Ví dụ:

~~~java
List<ProductDocument> findByCategoryOrderByCreatedAtDesc(String category);

List<ProductDocument> findByActiveTrueOrderByPriceAsc();
~~~

Phương thức thứ nhất lọc theo category và sắp xếp thời điểm tạo mới nhất trước. Phương thức thứ hai lọc document có `active = true` và sắp xếp giá tăng dần.

### 2.1. Sắp xếp theo nhiều field

Có thể khai báo nhiều field trong phần `OrderBy`. Ví dụ, sắp xếp theo thời điểm tạo giảm dần, sau đó theo SKU tăng dần:

~~~java
List<ProductDocument> findByCategoryOrderByCreatedAtDescSkuAsc(String category);
~~~

Field xuất hiện trước có độ ưu tiên sắp xếp cao hơn. Elasticsearch so sánh `createdAt` trước; nếu hai document có cùng thời điểm, nó dùng `sku` để quyết định thứ tự.

Thứ tự phụ là điều hữu ích khi nhiều document có cùng giá trị của field sắp xếp chính. Nếu chỉ sort theo một field có nhiều giá trị trùng nhau, thứ tự tương đối của các document bằng nhau có thể không ổn định giữa những lần truy vấn.

### 2.2. Khi nào dùng `OrderBy`?

Dùng `OrderBy` khi thứ tự là quy tắc cố định của nghiệp vụ và caller không cần thay đổi. Ví dụ:

- Lịch sử đơn hàng luôn hiển thị mới nhất trước.
- Bảng xếp hạng mặc định luôn sắp xếp điểm từ cao xuống thấp.
- Danh sách sản phẩm luôn sắp xếp theo SKU tăng dần.

Ưu điểm là tên method thể hiện rõ thứ tự và caller không cần truyền thêm đối tượng `Sort`. Hạn chế là mỗi kiểu sắp xếp khác nhau có thể cần một method riêng; nếu giao diện cho phép người dùng đổi sort, tham số `Sort` thường linh hoạt hơn.

## 3. Sắp xếp động bằng `Sort`

`Sort` thuộc `org.springframework.data.domain.Sort`. Caller tạo đối tượng `Sort` rồi truyền vào repository method có tham số `Sort`.

Ví dụ method:

~~~java
List<ProductDocument> findByCategory(String category, Sort sort);
~~~

Gọi với một tiêu chí:

~~~java
Sort sort = Sort.by(Sort.Direction.DESC, "createdAt");
List<ProductDocument> products =
        productRepository.findByCategory("ACCESSORIES", sort);
~~~

Caller có thể thay đổi thứ tự mà không cần tạo method mới:

~~~java
Sort priceAscending = Sort.by(Sort.Direction.ASC, "price");
Sort priceDescending = Sort.by(Sort.Direction.DESC, "price");

List<ProductDocument> cheaperFirst =
        productRepository.findByCategory("ACCESSORIES", priceAscending);

List<ProductDocument> expensiveFirst =
        productRepository.findByCategory("ACCESSORIES", priceDescending);
~~~

### 3.1. Dùng `Sort.Order` để mô tả nhiều tiêu chí

`Sort.by` có thể nhận nhiều `Sort.Order`. Mỗi order xác định field và chiều sắp xếp:

~~~java
Sort sort = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("sku"));

List<ProductDocument> products =
        productRepository.findByCategory("ACCESSORIES", sort);
~~~

Trong ví dụ, kết quả được sắp xếp theo `createdAt` giảm dần; các document cùng thời điểm được sắp xếp theo `sku` tăng dần.

Có thể tạo `Sort` theo từng bước:

~~~java
Sort sort = Sort.unsorted()
        .and(Sort.by(Sort.Order.desc("createdAt")))
        .and(Sort.by(Sort.Order.asc("sku")));
~~~

Khi không cần sắp xếp, có thể truyền `Sort.unsorted()` nếu method yêu cầu tham số `Sort`.

### 3.2. Tên thuộc tính trong Sort

Trong repository method, hãy ưu tiên dùng tên thuộc tính Java của entity, ví dụ `createdAt` hoặc `price`. Spring Data Elasticsearch sử dụng mapping metadata để ánh xạ thuộc tính Java sang tên field Elasticsearch tương ứng khi có cấu hình tên field.

Ví dụ thuộc tính Java được lưu dưới tên snake case:

~~~java
@Field(name = "created_at", type = FieldType.Date)
private Instant createdAt;
~~~

Khi dùng repository `Sort`, dùng thuộc tính `createdAt` theo domain model để mapping metadata có thể phân giải field. Với subfield của multi-field, field lồng nhau hoặc một field Elasticsearch không có property Java tương ứng, cần xác nhận cú pháp field path mà phiên bản Spring Data đang dùng hỗ trợ và kiểm tra request được sinh ra.

Không truyền tên thuộc tính do người dùng gửi trực tiếp vào `Sort.by` mà không kiểm soát. Hãy ánh xạ lựa chọn sort trên giao diện vào một danh sách field được phép, tránh sort tùy ý trên field nhạy cảm hoặc không hỗ trợ sort.

## 4. Phân trang bằng `Pageable`

`Pageable` biểu diễn thông tin trang cần lấy. Nó chứa số trang, kích thước trang và có thể mang tiêu chí sort.

Ví dụ method repository:

~~~java
Page<ProductDocument> findByCategory(String category, Pageable pageable);
~~~

Tạo trang đầu tiên gồm 20 document:

~~~java
Pageable pageable = PageRequest.of(0, 20);
Page<ProductDocument> page =
        productRepository.findByCategory("ACCESSORIES", pageable);
~~~

`PageRequest.of(pageNumber, pageSize)` dùng chỉ số trang bắt đầu từ `0`. Vì vậy:

- `PageRequest.of(0, 20)` lấy trang đầu tiên, tối đa 20 document.
- `PageRequest.of(1, 20)` lấy trang thứ hai.
- `PageRequest.of(2, 20)` lấy trang thứ ba.

Với page size bằng 20, trang thứ hai bắt đầu sau 20 kết quả đầu tiên. Caller không phải tự tính offset khi dùng `PageRequest`.

### 4.1. Đọc thông tin từ `Page`

`Page<T>` chứa nội dung của trang cùng metadata phân trang:

~~~java
Page<ProductDocument> page =
        productRepository.findByCategory(
                "ACCESSORIES",
                PageRequest.of(0, 20));

List<ProductDocument> content = page.getContent();
long totalElements = page.getTotalElements();
int totalPages = page.getTotalPages();
boolean hasNext = page.hasNext();
boolean hasPrevious = page.hasPrevious();
~~~

Các thông tin thường dùng:

| Method | Ý nghĩa |
| --- | --- |
| `getContent()` | Danh sách document trong trang hiện tại. |
| `getNumber()` | Số trang hiện tại, bắt đầu từ 0. |
| `getSize()` | Kích thước trang được yêu cầu. |
| `getNumberOfElements()` | Số phần tử thực tế trong trang hiện tại. |
| `getTotalElements()` | Tổng số phần tử phù hợp với truy vấn theo metadata total hit mà backend trả về. |
| `getTotalPages()` | Tổng số trang được tính từ tổng phần tử và page size. |
| `hasNext()` | Có trang tiếp theo hay không. |
| `hasPrevious()` | Có trang trước hay không. |

`Page` phù hợp với giao diện cần hiển thị tổng số kết quả hoặc tổng số trang. Việc tính tổng chính xác trên tập dữ liệu lớn có thể tốn tài nguyên; Elasticsearch có cơ chế giới hạn/quan hệ total hits tùy cấu hình truy vấn và phiên bản. Nếu giao diện chỉ cần hiển thị nút “Xem thêm”, không nhất thiết phải yêu cầu tổng số trang.

### 4.2. Dùng `List` với `Pageable`

Nếu chỉ cần nội dung của một trang mà không cần metadata `Page`, repository method có thể trả về `List<T>` và nhận `Pageable`:

~~~java
List<ProductDocument> findByCategory(String category, Pageable pageable);
~~~

~~~java
List<ProductDocument> firstPage = productRepository.findByCategory(
        "ACCESSORIES",
        PageRequest.of(0, 20));
~~~

`List` chỉ trả về các document trong cửa sổ kết quả được yêu cầu. Caller không nhận được `getTotalElements()` hoặc `getTotalPages()` như với `Page`.

Chọn kiểu trả về dựa trên hợp đồng API:

- Dùng `Page<T>` nếu giao diện cần thông tin tổng số kết quả và trạng thái trang.
- Dùng `List<T>` với `Pageable` nếu chỉ cần một phần kết quả và không cần metadata của `Page`.
- Dùng `List<T>` không có `Pageable` khi tập kết quả được giới hạn rõ ràng ở nơi khác; tránh lấy một lượng document không giới hạn từ index lớn.

## 5. Đặt Sort bên trong Pageable

`Pageable` có thể chứa `Sort`, vì vậy một tham số đã mô tả cả phân trang lẫn thứ tự kết quả.

~~~java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.asc("sku")));

Page<ProductDocument> page =
        productRepository.findByCategory("ACCESSORIES", pageable);
~~~

Có thể tạo `Pageable` không có sort rồi truyền sort ở một lần gọi khác:

~~~java
Pageable firstPage = PageRequest.of(0, 20);
Pageable secondPage = PageRequest.of(
        1,
        20,
        Sort.by(Sort.Order.asc("price")));
~~~

Khi method đã nhận `Pageable`, thông thường không cần thêm tham số `Sort` riêng. Đặt sort trong `Pageable` giúp số tham số rõ ràng và giữ page number, page size, sort trong cùng một đối tượng.

## 6. Kết hợp điều kiện truy vấn và sắp xếp

Các điều kiện derived query có thể kết hợp với `OrderBy`, `Sort` hoặc `Pageable`.

Ví dụ lọc sản phẩm đang hoạt động theo category và sắp xếp giá tăng dần:

~~~java
List<ProductDocument> findByCategoryAndActiveTrueOrderByPriceAsc(
        String category);
~~~

Ví dụ cho phép caller chọn sort:

~~~java
Page<ProductDocument> findByCategoryAndActiveTrue(
        String category,
        Pageable pageable);
~~~

Gọi method với trang có sort:

~~~java
Pageable pageable = PageRequest.of(
        0,
        25,
        Sort.by(Sort.Order.desc("createdAt")));

Page<ProductDocument> page =
        productRepository.findByCategoryAndActiveTrue(
                "ACCESSORIES", pageable);
~~~

Điều kiện lọc được tạo từ tên method và tham số; phần sort/phân trang được lấy từ đối tượng runtime. Điều này giúp một repository method phục vụ nhiều màn hình với tiêu chí sắp xếp khác nhau.

## 7. Field nào có thể dùng để sort?

Không phải mọi field đều phù hợp cho sort. Elasticsearch cần cấu trúc dữ liệu hỗ trợ sort, thường là doc values đối với các kiểu scalar.

| Field type | Khả năng sort thường gặp |
| --- | --- |
| `keyword` | Có; thường dùng cho mã, trạng thái, tên chuẩn hóa và giá trị exact. |
| `long`, `integer`, `double`, `float` | Có; phù hợp sort theo số. |
| `date` | Có; phù hợp sort theo thời gian. |
| `boolean` | Có thể sort theo giá trị boolean. |
| `text` | Không có doc values mặc định; sort trực tiếp thường không khả dụng. |

### 7.1. Dùng multi-field cho văn bản

Nếu cần tìm kiếm toàn văn và sort theo chuỗi, hãy khai báo một subfield `keyword`:

~~~json
{
  "mappings": {
    "properties": {
      "name": {
        "type": "text",
        "fields": {
          "sort": {
            "type": "keyword"
          }
        }
      }
    }
  }
}
~~~

Field `name` dùng cho `match` query; subfield `name.sort` dùng cho sort theo chuỗi nguyên vẹn. Khi dùng repository sort trên subfield, kiểm tra cách Spring Data Elasticsearch của phiên bản dự án xử lý đường dẫn field multi-field; nếu cần kiểm soát trực tiếp, dùng query API cho phép khai báo field sort rõ ràng.

Không bật `fielddata` trên `text` chỉ để sort nếu chưa đánh giá chi phí heap. Với nhu cầu sort thông thường, multi-field `keyword` thường phù hợp hơn.

### 7.2. Sort trên nested field

Nếu field nằm trong một mảng `nested`, sort cần cấu hình nested path và có thể cần nested filter để xác định giá trị dùng cho việc sắp xếp. Một `Sort.by("lines.price")` đơn giản không nhất thiết thể hiện đủ ngữ nghĩa nested sort.

Với nested sort phức tạp, hãy dùng query API của Spring Data Elasticsearch hoặc native Elasticsearch query để khai báo `nested` sort options, thay vì cố biểu diễn mọi trường hợp bằng tên derived method.

## 8. Thứ tự ổn định khi phân trang

Phân trang theo offset giả định thứ tự kết quả ổn định. Nếu nhiều document có cùng giá trị sort, hoặc dữ liệu thay đổi giữa hai lần gọi trang, một document có thể xuất hiện lặp lại hoặc bị bỏ qua giữa các trang.

Ví dụ sort chỉ theo `createdAt`:

~~~java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Order.desc("createdAt")));
~~~

Nếu nhiều sản phẩm có cùng timestamp, Elasticsearch không có cam kết thứ tự nghiệp vụ ổn định giữa chúng. Có thể thêm field duy nhất có mapping hỗ trợ sort làm tiêu chí phụ, ví dụ `sku` nếu SKU thật sự duy nhất:

~~~java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.asc("sku")));
~~~

Không giả định metadata `_id` luôn là field sort phù hợp. Nếu cần tie-breaker ổn định, nên có field nghiệp vụ duy nhất được lập chỉ mục và có doc values phù hợp, hoặc sử dụng cơ chế sort/cursor chuyên biệt theo Elasticsearch.

Ngay cả khi có tie-breaker, offset pagination vẫn có thể bị ảnh hưởng khi document được thêm, xóa hoặc cập nhật trong lúc người dùng duyệt trang. Với dữ liệu thay đổi liên tục, cần chọn chiến lược phân trang phù hợp hơn.

## 9. Giới hạn phân trang sâu trong Elasticsearch

`Pageable` thường được chuyển thành truy vấn offset/size (`from`/`size`). Elasticsearch giới hạn cửa sổ kết quả mặc định bằng `index.max_result_window`, thường là 10.000 document cho một index.

Ví dụ, nếu page size là 100 và yêu cầu trang thứ 120, offset là 11.900. Truy vấn có thể vượt giới hạn mặc định và bị Elasticsearch từ chối.

Không nên tăng `index.max_result_window` thật lớn chỉ để cho phép người dùng đi tới những trang rất sâu. Elasticsearch phải giữ và xử lý nhiều kết quả từ đầu cửa sổ tới offset cần lấy; chi phí bộ nhớ và CPU tăng theo độ sâu.

### 9.1. Dùng `search_after` cho phân trang sâu

Với tập kết quả lớn, Elasticsearch khuyến nghị dùng `search_after` thay cho offset pagination sâu. Cơ chế này dùng giá trị sort của hit cuối cùng ở trang hiện tại làm cursor để lấy trang tiếp theo.

Luồng tổng quát:

1. Chạy truy vấn với sort xác định và lấy trang đầu.
2. Đọc mảng `sort` của hit cuối cùng.
3. Gửi truy vấn tiếp theo với cùng điều kiện và cùng sort, thêm `search_after` bằng giá trị sort đó.
4. Lặp lại cho đến khi không còn kết quả.

Ví dụ REST API minh họa:

~~~http
GET /products/_search
Content-Type: application/json

{
  "size": 100,
  "sort": [
    { "createdAt": "desc" },
    { "sku": "asc" }
  ],
  "query": {
    "term": {
      "category": "ACCESSORIES"
    }
  }
}
~~~

Lấy giá trị sort của hit cuối cùng, rồi dùng nó cho request kế tiếp:

~~~json
{
  "size": 100,
  "sort": [
    { "createdAt": "desc" },
    { "sku": "asc" }
  ],
  "search_after": [
    "2026-11-13T09:30:00Z",
    "KB-001"
  ],
  "query": {
    "term": {
      "category": "ACCESSORIES"
    }
  }
}
~~~

Các giá trị trong `search_after` phải đúng thứ tự và định dạng của sort trong request trước. Sort cần có thứ tự ổn định; trong các trường hợp phù hợp, kết hợp Point in Time (PIT) để duy trì một góc nhìn dữ liệu nhất quán trong suốt quá trình phân trang.

`Pageable` theo offset không tự động biến thành cursor `search_after`. Nếu use case cần phân trang sâu, hãy dùng API query/client của Spring Data Elasticsearch có hỗ trợ search-after/PIT theo phiên bản đang sử dụng, hoặc triển khai cursor endpoint riêng. Không cố biểu diễn cursor bằng page number lớn.

### 9.2. Scroll cho xử lý theo lô

Đối với export hoặc xử lý batch cần đọc tuần tự nhiều document, scroll API từng được dùng để duyệt kết quả theo từng batch. Với các phiên bản Elasticsearch hiện đại, PIT kết hợp `search_after` thường là lựa chọn được khuyến nghị cho phân trang sâu có thứ tự. Hãy chọn API theo mục đích: giao diện người dùng, export batch và xử lý nền có yêu cầu khác nhau.

## 10. `Page`, tổng số kết quả và chi phí đếm

`Page<T>` hữu ích vì cung cấp `totalElements` và `totalPages`. Tuy nhiên, tổng số kết quả chính xác có thể đắt với truy vấn phức tạp hoặc tập dữ liệu lớn.

Elasticsearch có cơ chế `track_total_hits` để điều khiển mức độ tính tổng hit. Tùy request và phiên bản, total hits có thể được trả về với quan hệ chính xác (`eq`) hoặc chỉ là cận dưới (`gte`). Khi xây dựng API công khai, không nên giả định mọi truy vấn đều có tổng số tuyệt đối chính xác nếu cấu hình tìm kiếm cho phép giới hạn việc đếm.

Nếu giao diện chỉ cần biết có trang tiếp theo, có thể thiết kế query lấy dư một phần tử để xác định `hasNext`, hoặc dùng cursor-based pagination. Cách này tránh phụ thuộc vào tổng số trang trên tập dữ liệu rất lớn.

## 11. Giới hạn đầu vào Pageable và Sort từ API

Không nên chuyển trực tiếp mọi tham số HTTP thành `PageRequest` hoặc `Sort` mà không kiểm soát. API nên giới hạn page size và các field được phép sort.

Ví dụ service nhận page number và size:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

public Page<ProductDocument> searchByCategory(
        String category, int page, int size, String sortBy, String direction) {

    int safePage = Math.max(page, 0);
    int safeSize = Math.min(Math.max(size, 1), 100);

    Sort sort = switch (sortBy) {
        case "price" -> Sort.by("price");
        case "createdAt" -> Sort.by("createdAt");
        case "name" -> Sort.by("name");
        default -> Sort.by("createdAt");
    };

    if ("desc".equalsIgnoreCase(direction)) {
        sort = sort.descending();
    } else {
        sort = sort.ascending();
    }

    Pageable pageable = PageRequest.of(safePage, safeSize, sort);
    return productRepository.findByCategory(category, pageable);
}
~~~

Đoạn code là ví dụ minh họa cách giới hạn page size và whitelist field sort. Trong ứng dụng thật, cần xác nhận `name` có mapping sortable; nếu `name` là `text`, hãy dùng subfield `keyword` thông qua query mapping phù hợp hoặc bỏ lựa chọn đó.

Không nhận trực tiếp tên field tùy ý từ client vì có thể dẫn tới lỗi runtime, truy vấn tốn kém hoặc cho phép sort theo dữ liệu không dự kiến.

## 12. Kết hợp `OrderBy`, `Sort` và `Pageable` thế nào?

Ba cơ chế có mục đích gần nhau nhưng khác mức độ linh hoạt:

| Cơ chế | Khai báo ở đâu? | Có thể thay đổi lúc chạy? | Dùng khi nào? |
| --- | --- | --- | --- |
| `OrderBy` | Trong tên repository method. | Không; thứ tự là cố định trong method. | Quy tắc sắp xếp mặc định của nghiệp vụ. |
| `Sort` | Tham số của repository method. | Có. | Caller cần chọn thứ tự nhưng không cần phân trang. |
| `Pageable` | Tham số của repository method. | Có; gồm page, size và có thể gồm Sort. | Giao diện cần phân trang và có thể thay đổi sort. |

Quy tắc chọn:

1. Nếu mọi caller luôn dùng cùng một thứ tự, chọn `OrderBy` để tên method tự mô tả hành vi.
2. Nếu caller cần chọn sort nhưng muốn lấy toàn bộ tập kết quả có giới hạn khác, dùng `Sort`.
3. Nếu caller cần lấy từng trang, dùng `Pageable`; đặt sort trong `Pageable` khi cần.
4. Nếu cần duyệt rất sâu qua tập kết quả lớn hoặc dữ liệu thay đổi liên tục, cân nhắc `search_after` và PIT thay cho page number lớn.

Không nên tạo quá nhiều method chỉ khác thứ tự sort nếu thứ tự đó là lựa chọn của giao diện. Ngược lại, không nên đẩy mọi thứ tự nghiệp vụ cố định thành tham số tùy ý nếu ứng dụng cần một hợp đồng truy vấn rõ ràng.

## 13. Ví dụ hoàn chỉnh

Repository:

~~~java
import java.util.List;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    List<ProductDocument> findByCategoryOrderByCreatedAtDesc(String category);

    List<ProductDocument> findByCategory(String category, Sort sort);

    Page<ProductDocument> findByCategory(String category, Pageable pageable);
}
~~~

Service:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;

@Service
public class ProductSearchService {

    private final ProductRepository repository;

    public ProductSearchService(ProductRepository repository) {
        this.repository = repository;
    }

    public List<ProductDocument> newestProducts(String category) {
        return repository.findByCategoryOrderByCreatedAtDesc(category);
    }

    public List<ProductDocument> sortedProducts(String category) {
        Sort sort = Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.asc("sku"));
        return repository.findByCategory(category, sort);
    }

    public Page<ProductDocument> productPage(
            String category, int pageNumber, int pageSize) {

        Pageable pageable = PageRequest.of(
                pageNumber,
                pageSize,
                Sort.by(Sort.Order.desc("createdAt"),
                        Sort.Order.asc("sku")));

        return repository.findByCategory(category, pageable);
    }
}
~~~

Trong ví dụ, method `newestProducts` có thứ tự cố định. `sortedProducts` nhận tiêu chí sort động. `productPage` nhận cả trang và sort, trả về `Page<ProductDocument>` để caller đọc nội dung cùng metadata.

## 14. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Method `OrderBy` không được phân tích đúng | Tên field hoặc cú pháp hậu tố không khớp property domain. | Kiểm tra chính tả, camel case và tên property trong entity. |
| Sort báo lỗi trên field text | Field `text` không có doc values mặc định. | Dùng subfield `keyword` hoặc một field sortable riêng. |
| Sort theo tên field không có kết quả mong muốn | Dùng tên field Elasticsearch không khớp mapping hoặc nhầm property Java với tên lưu trữ. | Kiểm tra `@Field(name = ...)` và query thực tế được tạo. |
| Trang sâu bị từ chối | Offset vượt `index.max_result_window`. | Dùng `search_after`/PIT hoặc thiết kế lại luồng duyệt dữ liệu. |
| Document lặp hoặc thiếu giữa các trang | Sort không có tie-breaker duy nhất hoặc dữ liệu thay đổi khi đang phân trang. | Dùng sort ổn định và cân nhắc PIT/cursor pagination. |
| Tổng số trang không như dự kiến | Total hits có thể bị giới hạn hoặc dữ liệu thay đổi giữa các request. | Kiểm tra `track_total_hits` và yêu cầu metadata của API. |
| API sort phát sinh lỗi runtime | Client truyền field không tồn tại hoặc không sortable. | Whitelist field sort và kiểm tra mapping. |

## 15. Quy trình chọn và kiểm tra phương thức truy vấn

Khi thiết kế repository method có sort hoặc phân trang, hãy xác định:

1. Điều kiện lọc nào cần xuất hiện trong tên method và tham số?
2. Thứ tự sort có cố định theo nghiệp vụ hay caller được chọn?
3. Field sort có mapping phù hợp và hỗ trợ doc values không?
4. Có cần sort phụ duy nhất để giữ thứ tự ổn định không?
5. Caller cần `Page` với tổng số phần tử hay chỉ cần `List` của trang hiện tại?
6. Page size tối đa là bao nhiêu và offset có thể chạm giới hạn result window không?
7. Dữ liệu có thay đổi liên tục trong lúc người dùng chuyển trang không?
8. Nếu cần phân trang sâu, API query/client của phiên bản Spring Data hiện tại có hỗ trợ cursor/PIT theo yêu cầu không?

`OrderBy` diễn đạt thứ tự cố định trong tên method, `Sort` cho phép caller chọn thứ tự lúc chạy, còn `Pageable` kết hợp số trang, kích thước trang và tùy chọn sort. Dùng đúng field có thể sort, giới hạn page size và chọn chiến lược cursor khi tập kết quả lớn sẽ giúp repository truy vấn rõ ràng và tránh các vấn đề về hiệu năng hoặc tính ổn định của phân trang.

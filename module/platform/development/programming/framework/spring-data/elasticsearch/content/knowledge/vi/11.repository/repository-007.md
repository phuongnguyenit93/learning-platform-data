# Kiểu trả về được hỗ trợ và hợp đồng dữ liệu không tồn tại

Spring Data Elasticsearch repository method có thể trả về nhiều kiểu dữ liệu khác nhau, tùy số lượng kết quả cần lấy và lượng metadata tìm kiếm cần sử dụng. Chọn kiểu trả về phù hợp giúp mã ứng dụng biểu đạt rõ hợp đồng của thao tác: tìm thấy một tài liệu, không tìm thấy tài liệu, có nhiều kết quả hay cần thông tin phân trang và điểm liên quan.

Với thao tác tìm một tài liệu theo ID, **Optional<T>** thường là lựa chọn rõ ràng vì tài liệu có thể không tồn tại. Với truy vấn trả về nhiều tài liệu, có thể dùng **List<T>**, **Iterable<T>**, **Page<T>** hoặc các kiểu kết quả tìm kiếm chuyên biệt. Spring Data Elasticsearch còn có repository reactive, trong đó **Mono<T>** và **Flux<T>** biểu diễn kết quả bất đồng bộ.

Bài này trình bày các kiểu trả về thường gặp, ý nghĩa của trường hợp không có dữ liệu, cách xử lý kết quả rỗng và các lỗi phát sinh khi hợp đồng trả về không phù hợp với số lượng tài liệu thực tế.

## 1. Chọn kiểu trả về theo số lượng kết quả

Trước khi khai báo repository method, cần xác định truy vấn có thể trả về bao nhiêu tài liệu:

- Không có hoặc tối đa một tài liệu.
- Không có hoặc nhiều tài liệu.
- Một trang trong tập kết quả lớn.
- Kết quả tìm kiếm kèm metadata như điểm liên quan, tổng số hit hoặc highlight.
- Một luồng dữ liệu được tiêu thụ dần.

Các nhóm kiểu trả về thường dùng:

| Nhu cầu | Kiểu trả về thường dùng | Khi không có kết quả |
|---|---|---|
| Tìm theo ID | **Optional<T>** | **Optional.empty()** |
| Tìm tối đa một tài liệu | **Optional<T>** hoặc **T** | Optional rỗng hoặc null theo kiểu khai báo |
| Lấy nhiều tài liệu | **List<T>**, **Iterable<T>** | Collection rỗng |
| Lấy một trang | **Page<T>** | Page rỗng |
| Lấy một phần kết quả và biết còn trang tiếp | **Slice<T>** | Slice rỗng |
| Lấy metadata của từng hit | **SearchHits<T>**, **SearchHit<T>** | SearchHits không có hit |
| Tìm kiếm reactive | **Mono<T>**, **Flux<T>** | Publisher hoàn tất mà không phát phần tử |
| Kiểm tra tồn tại | **boolean** hoặc **Mono<Boolean>** | false |
| Đếm kết quả | **long** hoặc **Mono<Long>** | 0 |

Không nên chọn kiểu trả về chỉ vì kiểu đó dễ viết. Hãy chọn kiểu thể hiện đúng số lượng kết quả hợp lệ và cách ứng dụng xử lý khi không có tài liệu.

## 2. Tìm một tài liệu: Optional<T>

**Optional<T>** biểu diễn một giá trị có thể có hoặc không. Đây là hợp đồng phù hợp khi truy vấn mong đợi tối đa một tài liệu.

Ví dụ repository:

~~~java
import java.util.Optional;

import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    Optional<Product> findBySku(String sku);
}
~~~

Gọi phương thức:

~~~java
Optional<Product> result = productRepository.findBySku("KB-1001");

if (result.isPresent()) {
    Product product = result.get();
    System.out.println(product.getName());
} else {
    System.out.println("Không tìm thấy sản phẩm");
}
~~~

Có thể xử lý gọn bằng các phương thức của Optional:

~~~java
Product product = productRepository.findBySku("KB-1001")
        .orElseThrow(() -> new ProductNotFoundException("KB-1001"));
~~~

Hoặc cung cấp giá trị mặc định:

~~~java
Product product = productRepository.findBySku("KB-1001")
        .orElseGet(Product::new);
~~~

Chỉ dùng giá trị mặc định khi nghiệp vụ thật sự định nghĩa được một đối tượng mặc định hợp lệ. Không nên tạo một Product rỗng chỉ để tránh xử lý trường hợp không tìm thấy, vì điều đó có thể làm mất ý nghĩa của việc không tồn tại tài liệu.

### findById và findAllById

Các phương thức CRUD kế thừa từ repository có hợp đồng quan trọng:

~~~java
Optional<Product> product = productRepository.findById("p-1001");

Iterable<Product> products =
        productRepository.findAllById(List.of("p-1001", "p-1002"));
~~~

- **findById(id)** trả về Optional. Nếu ID không tồn tại, kết quả là Optional rỗng.
- **findAllById(ids)** trả về những tài liệu tìm thấy trong danh sách ID. ID không tồn tại sẽ không tạo ra phần tử giả hoặc đối tượng null trong kết quả.
- Thứ tự tài liệu trả về từ **findAllById** không nhất thiết giống thứ tự ID đầu vào. Nếu nghiệp vụ cần giữ thứ tự, ứng dụng cần sắp xếp hoặc dựng lại thứ tự dựa trên ID sau khi nhận kết quả.

Ví dụ xử lý nhiều ID:

~~~java
List<String> ids = List.of("p-1001", "p-1002", "p-9999");

List<Product> found = new ArrayList<>();
productRepository.findAllById(ids).forEach(found::add);

Set<String> foundIds = found.stream()
        .map(Product::getId)
        .collect(Collectors.toSet());

List<String> missingIds = ids.stream()
        .filter(id -> !foundIds.contains(id))
        .toList();
~~~

Cách này giúp phân biệt các ID đã tìm thấy và các ID không có tài liệu tương ứng. Nếu ứng dụng cần báo lỗi khi thiếu bất kỳ ID nào, có thể so sánh số lượng hoặc tập ID sau truy vấn.

## 3. Truy vấn một tài liệu với kiểu T

Một repository query method có thể trả về trực tiếp kiểu entity:

~~~java
Product findBySku(String sku);
~~~

Hợp đồng của kiểu trả về đơn là truy vấn phải tìm được tối đa một tài liệu. Khi không tìm thấy, Spring Data có thể trả về **null**. Nếu có nhiều hơn một kết quả trong khi phương thức khai báo một giá trị đơn, framework phát sinh lỗi kích thước kết quả, thường là **IncorrectResultSizeDataAccessException**.

Vì vậy, nếu việc không tìm thấy là tình huống bình thường, **Optional<Product>** thường rõ ràng và an toàn hơn.

So sánh:

~~~java
// Có thể trả về null nếu không tìm thấy.
Product findBySku(String sku);

// Không có kết quả được biểu diễn tường minh.
Optional<Product> findBySku(String sku);
~~~

Không nên dùng kiểu trả về đơn nếu điều kiện truy vấn không bảo đảm tính duy nhất. Ví dụ, nếu nhiều sản phẩm có cùng danh mục thì phương thức sau không phù hợp:

~~~java
// Không phù hợp nếu một danh mục có nhiều sản phẩm.
Product findByCategory(String category);
~~~

Nên đổi sang collection hoặc kiểu trả về nhiều kết quả:

~~~java
List<Product> findByCategory(String category);
~~~

Nếu nghiệp vụ yêu cầu SKU duy nhất, cần bảo đảm tính duy nhất bằng quy tắc dữ liệu và cách ghi. Elasticsearch không tự động tạo ràng buộc unique cho một trường thông thường giống như unique constraint trong cơ sở dữ liệu quan hệ.

## 4. Trả về nhiều tài liệu: List và Iterable

Khi truy vấn có thể trả về nhiều tài liệu, dùng **List<T>** hoặc **Iterable<T>**:

~~~java
List<Product> findByCategory(String category);

Iterable<Product> findAll();
~~~

**List<T>** thuận tiện khi cần truy cập theo chỉ số, xử lý bằng Stream API hoặc trả về từ service/controller. Nếu truy vấn không có kết quả, collection trả về rỗng.

Ví dụ:

~~~java
List<Product> products =
        productRepository.findByCategory("accessories");

if (products.isEmpty()) {
    System.out.println("Danh mục chưa có sản phẩm");
} else {
    products.forEach(product ->
            System.out.println(product.getName()));
}
~~~

**Iterable<T>** phù hợp với các API CRUD tổng quát như **findAll()**. Nó cho phép duyệt kết quả mà không yêu cầu giao diện List.

Không nên giả định rằng **findAll()** luôn tải toàn bộ dữ liệu một cách an toàn đối với index lớn. Cần xem xét giới hạn kết quả mặc định, phân trang và tài nguyên bộ nhớ. Với dữ liệu lớn, hãy dùng **Pageable**, cơ chế cuộn kết quả hoặc API tìm kiếm phù hợp.

### Collection rỗng có ý nghĩa gì?

Một collection rỗng biểu thị truy vấn đã thực thi và không tìm thấy tài liệu nào. Đây là kết quả hợp lệ, không phải lỗi.

Ví dụ:

~~~java
List<Product> products = productRepository.findByCategory("unknown");

if (products.isEmpty()) {
    // Trả danh sách rỗng cho client.
}
~~~

Không nên trả **null** thay cho collection rỗng. Collection rỗng giúp caller luôn có thể duyệt hoặc kiểm tra **isEmpty()** mà không phải kiểm tra null trước.

## 5. Phân trang: Page<T> và Pageable

Khi dữ liệu có thể rất lớn, repository nên trả về từng trang thay vì tải toàn bộ kết quả.

Khai báo phương thức:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    Page<Product> findByCategory(String category, Pageable pageable);
}
~~~

Gọi truy vấn:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Direction.ASC, "name")
);

Page<Product> page =
        productRepository.findByCategory("accessories", pageable);

List<Product> content = page.getContent();
long totalElements = page.getTotalElements();
int totalPages = page.getTotalPages();
boolean hasNext = page.hasNext();
~~~

Trang đầu tiên có chỉ số **0**. Ví dụ trên yêu cầu tối đa 20 sản phẩm trong danh mục accessories, sắp xếp theo tên tăng dần.

**Page<T>** cung cấp:

- **getContent()**: danh sách tài liệu trong trang hiện tại.
- **getNumber()**: số thứ tự trang hiện tại.
- **getSize()**: kích thước trang yêu cầu.
- **getNumberOfElements()**: số phần tử thực tế trong trang.
- **getTotalElements()**: tổng số phần tử phù hợp với truy vấn.
- **getTotalPages()**: tổng số trang.
- **hasNext()** và **hasPrevious()**: kiểm tra có trang tiếp hoặc trang trước.

Nếu không có tài liệu, Page vẫn tồn tại nhưng nội dung rỗng:

~~~java
Page<Product> page =
        productRepository.findByCategory(
                "unknown",
                PageRequest.of(0, 20)
        );

if (page.isEmpty()) {
    System.out.println("Không có sản phẩm phù hợp");
}
~~~

Tổng số phần tử bằng 0 và tổng số trang bằng 0. Không cần kiểm tra null trước khi dùng Page.

### Page và chi phí đếm tổng số kết quả

**Page<T>** thường cần thông tin tổng số kết quả để tính **getTotalElements()** và **getTotalPages()**. Điều đó có thể làm phát sinh thao tác đếm hoặc truy vấn bổ sung, tùy cách triển khai và phiên bản.

Nếu giao diện chỉ cần biết còn kết quả tiếp theo hay không, **Slice<T>** có thể phù hợp hơn.

## 6. Slice<T> khi không cần tổng số kết quả

**Slice<T>** biểu diễn một lát kết quả. Nó cung cấp nội dung hiện tại và thông tin có trang tiếp theo hay không, nhưng không yêu cầu tổng số phần tử và tổng số trang như Page.

Khai báo:

~~~java
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;

Slice<Product> findByCategory(String category, Pageable pageable);
~~~

Gọi phương thức:

~~~java
Slice<Product> slice =
        productRepository.findByCategory(
                "accessories",
                PageRequest.of(0, 20)
        );

List<Product> products = slice.getContent();

if (slice.hasNext()) {
    Pageable nextPage = slice.nextPageable();
    // Tải phần kết quả tiếp theo.
}
~~~

Khi không có kết quả, Slice rỗng và **hasNext()** trả về false.

Dùng Slice khi giao diện cần nút “Xem thêm” hoặc tải từng phần, không cần hiển thị tổng số kết quả. Khả năng hỗ trợ cụ thể của Slice trong query method phụ thuộc phiên bản Spring Data Elasticsearch và loại truy vấn; hãy kiểm tra tài liệu API của dự án.

## 7. SearchHit và SearchHits: giữ lại metadata tìm kiếm

Khi chỉ cần đối tượng entity, **List<Product>** hoặc **Page<Product>** có thể đủ. Nhưng trong tìm kiếm toàn văn, Elasticsearch trả về metadata quan trọng như:

- ID tài liệu.
- Điểm liên quan (**score**).
- Nội dung highlight.
- Tên index nguồn.
- Thông tin sort values.
- Thông tin về kết quả và aggregations ở cấp truy vấn.

Spring Data Elasticsearch cung cấp **SearchHit<T>** và **SearchHits<T>** để giữ các metadata này.

**SearchHit<T>** đại diện cho một hit:

~~~java
import org.springframework.data.elasticsearch.core.SearchHit;

SearchHit<Product> hit = ...;

Product product = hit.getContent();
String id = hit.getId();
float score = hit.getScore();
Map<String, List<String>> highlights = hit.getHighlightFields();
~~~

**SearchHits<T>** chứa tập hit và metadata tổng thể:

~~~java
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.SearchHit;

SearchHits<Product> searchHits = ...;

long totalHits = searchHits.getTotalHits();

for (SearchHit<Product> hit : searchHits) {
    Product product = hit.getContent();
    System.out.println(product.getName() + " score=" + hit.getScore());
}
~~~

Khác với **List<Product>**, SearchHits giữ lại thông tin Elasticsearch cung cấp cho từng kết quả. Điều này hữu ích khi xây dựng trang kết quả tìm kiếm có highlight hoặc sắp xếp theo độ liên quan.

### Repository method trả về SearchHits

Một query method có thể khai báo kiểu SearchHits nếu phiên bản Spring Data Elasticsearch đang dùng hỗ trợ kiểu này:

~~~java
import org.springframework.data.elasticsearch.core.SearchHits;

SearchHits<Product> findByName(String name);
~~~

Khi sử dụng kiểu kết quả chuyên biệt, hãy kiểm tra khả năng hỗ trợ của loại truy vấn và phiên bản Spring Data Elasticsearch. Nếu repository query method không đáp ứng được cách xây dựng truy vấn cần thiết, có thể dùng **ElasticsearchOperations.search(...)** để tạo truy vấn tường minh và nhận SearchHits.

## 8. SearchPage và phân trang kết quả tìm kiếm

Khi cần cả phân trang lẫn metadata của từng hit, Spring Data Elasticsearch có kiểu **SearchPage<T>**. Kiểu này kết hợp thông tin phân trang với các SearchHit.

Ví dụ khai báo theo API hỗ trợ của phiên bản:

~~~java
import org.springframework.data.domain.Pageable;
import org.springframework.data.elasticsearch.core.SearchPage;

SearchPage<Product> searchByName(String name, Pageable pageable);
~~~

SearchPage cho phép lấy thông tin trang và nội dung hit. Mỗi hit vẫn giữ score và metadata tìm kiếm.

Trong một số phiên bản, generic của SearchPage và kiểu SearchHit được thể hiện khác nhau trong API. Hãy kiểm tra chữ ký repository method được hỗ trợ thay vì suy đoán generic từ ví dụ của phiên bản khác.

Khi chỉ cần entity, Page hoặc List thường đơn giản hơn. Khi cần score, highlight hoặc metadata, SearchHits/SearchPage là lựa chọn phù hợp.

## 9. Stream<T> và tiêu thụ kết quả lớn

Một số repository query method có thể trả về **Stream<T>** hoặc **Stream<SearchHit<T>>**, tùy loại truy vấn và phiên bản. Stream giúp xử lý phần tử theo luồng trong mã ứng dụng:

~~~java
try (Stream<Product> products =
             productRepository.streamByCategory("accessories")) {
    products.forEach(product ->
            process(product));
}
~~~

Khi stream gắn với tài nguyên hoặc scroll context phía Elasticsearch, cần đóng stream sau khi sử dụng. Cú pháp try-with-resources bảo đảm gọi close ngay cả khi xử lý phát sinh exception.

Không nên chuyển một stream lớn thành List nếu mục tiêu là tiết kiệm bộ nhớ. Cũng không nên giữ stream mở lâu hơn cần thiết vì nó có thể giữ tài nguyên phía client hoặc server.

Các phương thức Stream có thể phụ thuộc cách Spring Data Elasticsearch triển khai scroll và phiên bản đang dùng. Nếu cần duyệt lượng dữ liệu rất lớn, hãy cân nhắc **SearchHitsIterator<T>** hoặc API cuộn kết quả tương ứng, và luôn đóng tài nguyên theo hợp đồng của API.

## 10. Reactive repository: Mono và Flux

Spring Data Elasticsearch cung cấp repository reactive riêng, thường được khai báo bằng **ReactiveElasticsearchRepository**. Reactive repository dùng Reactor để biểu diễn kết quả bất đồng bộ.

Ví dụ:

~~~java
import org.springframework.data.elasticsearch.repository.ReactiveElasticsearchRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface ReactiveProductRepository
        extends ReactiveElasticsearchRepository<Product, String> {

    Mono<Product> findBySku(String sku);

    Flux<Product> findByCategory(String category);
}
~~~

Ý nghĩa:

- **Mono<Product>** phát tối đa một Product rồi hoàn tất.
- **Flux<Product>** phát 0 hoặc nhiều Product rồi hoàn tất.
- Nếu không tìm thấy một tài liệu, Mono hoàn tất mà không phát giá trị.
- Nếu truy vấn nhiều tài liệu không có kết quả, Flux hoàn tất mà không phát phần tử.

Ví dụ xử lý Mono rỗng:

~~~java
Mono<Product> result = reactiveProductRepository.findBySku("KB-1001");

return result.switchIfEmpty(
        Mono.error(new ProductNotFoundException("KB-1001"))
);
~~~

Ví dụ xử lý Flux rỗng:

~~~java
Flux<Product> products =
        reactiveProductRepository.findByCategory("unknown");

return products.switchIfEmpty(
        Flux.empty()
);
~~~

Trong trường hợp Flux, **switchIfEmpty(Flux.empty())** không làm thay đổi kết quả; ví dụ này chỉ minh họa rằng không có phần tử là một trạng thái hoàn tất hợp lệ. Nếu cần thông báo riêng khi collection không có dữ liệu, có thể dùng **collectList()** rồi kiểm tra danh sách, hoặc dùng các toán tử như **hasElements()** tùy nghiệp vụ.

Không gọi **block()** trong luồng xử lý reactive thông thường nếu không có lý do rõ ràng. **block()** chờ kết quả đồng bộ và có thể làm mất lợi ích của mô hình reactive, đặc biệt trên event-loop thread.

Reactive repository và imperative repository là hai API khác nhau. Không khai báo một repository imperative rồi mong nó trả về Mono/Flux như reactive repository.

## 11. Hợp đồng khi dữ liệu không tồn tại

Một phần quan trọng của thiết kế repository là định nghĩa rõ điều gì xảy ra khi tài liệu không tồn tại.

Các hợp đồng thường gặp:

| Kiểu trả về | Hợp đồng khi không có dữ liệu | Cách xử lý ở caller |
|---|---|---|
| **T** | Có thể trả null với query method đơn không có kết quả | Kiểm tra null hoặc đổi sang Optional |
| **Optional<T>** | Optional rỗng | Dùng isPresent, orElse hoặc orElseThrow |
| **List<T>** | Danh sách rỗng | Dùng isEmpty và trả collection rỗng |
| **Iterable<T>** | Không có phần tử | Duyệt collection, không giả định có phần tử |
| **Page<T>** | Page rỗng | Kiểm tra isEmpty, totalElements bằng 0 |
| **Slice<T>** | Slice rỗng, không có trang tiếp | Kiểm tra isEmpty và hasNext |
| **SearchHits<T>** | Không có hit | Kiểm tra getSearchHits().isEmpty() hoặc getTotalHits() |
| **Mono<T>** | Mono.empty() | Dùng switchIfEmpty, defaultIfEmpty hoặc xử lý trong subscriber |
| **Flux<T>** | Flux.empty() | Dùng toán tử reactive phù hợp |

Đừng nhầm lẫn giữa “không tìm thấy tài liệu” và “truy vấn thất bại”. Ví dụ:

- Không có tài liệu với ID đã cho là kết quả nghiệp vụ hợp lệ.
- Elasticsearch không kết nối được là lỗi hạ tầng.
- Truy vấn sai cú pháp là lỗi truy vấn.
- Mapping không tương thích có thể làm truy vấn thất bại.
- Tài khoản thiếu quyền có thể khiến Elasticsearch trả lỗi truy cập.

Không nên bắt mọi exception rồi trả Optional.empty hoặc danh sách rỗng. Cách đó biến lỗi hệ thống thành kết quả “không có dữ liệu”, khiến ứng dụng khó phát hiện sự cố.

## 12. Từ kết quả không tồn tại đến phản hồi API

Repository thường là tầng truy cập dữ liệu. Service quyết định ý nghĩa nghiệp vụ của trường hợp không có tài liệu, còn controller ánh xạ kết quả sang HTTP response.

Ví dụ service:

~~~java
import org.springframework.stereotype.Service;

@Service
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public Product getRequiredProduct(String id) {
        return repository.findById(id)
                .orElseThrow(() -> new ProductNotFoundException(id));
    }
}
~~~

Exception nghiệp vụ:

~~~java
public class ProductNotFoundException extends RuntimeException {

    public ProductNotFoundException(String id) {
        super("Không tìm thấy sản phẩm: " + id);
    }
}
~~~

Controller có thể ánh xạ exception sang HTTP 404:

~~~java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProductController {

    private final ProductService service;

    public ProductController(ProductService service) {
        this.service = service;
    }

    @GetMapping("/products/{id}")
    public ResponseEntity<Product> getById(@PathVariable String id) {
        return ResponseEntity.ok(service.getRequiredProduct(id));
    }
}
~~~

Dùng exception handler toàn cục để chuyển **ProductNotFoundException** thành phản hồi 404:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(ProductNotFoundException.class)
    public ResponseEntity<String> handleNotFound(
            ProductNotFoundException exception) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(exception.getMessage());
    }
}
~~~

Đối với endpoint trả về danh sách, thông thường trả HTTP 200 cùng mảng rỗng khi không có phần tử, nếu hợp đồng API quy định như vậy. Không nên trả 404 chỉ vì một truy vấn danh sách không có kết quả; 404 thường phù hợp hơn với tài nguyên đơn được định danh mà không tồn tại.

## 13. Truy vấn có nhiều hơn một kết quả khi phương thức chỉ nhận một

Một lỗi thường gặp là khai báo kiểu trả về đơn trong khi điều kiện truy vấn không duy nhất.

Ví dụ:

~~~java
Optional<Product> findByCategory(String category);
~~~

Nếu có nhiều sản phẩm cùng category, phương thức không thể biểu diễn tất cả kết quả bằng Optional. Spring Data có thể ném **IncorrectResultSizeDataAccessException** khi số lượng kết quả vượt quá một.

Cách sửa là đổi kiểu trả về:

~~~java
List<Product> findByCategory(String category);
~~~

Nếu nghiệp vụ chỉ cần một sản phẩm bất kỳ hoặc sản phẩm đầu tiên theo thứ tự xác định, hãy khai báo rõ quy tắc lấy kết quả, ví dụ phương thức giới hạn kết quả và có sort phù hợp. Không nên dựa vào thứ tự mặc định của Elasticsearch vì kết quả tìm kiếm có thể được xếp theo score hoặc quy tắc truy vấn.

Ví dụ:

~~~java
Optional<Product> findFirstByCategoryOrderByPriceAsc(String category);
~~~

Cách đặt tên và khả năng hỗ trợ các keyword như **First**, **Top** hoặc **OrderBy** phụ thuộc query derivation của phiên bản Spring Data Elasticsearch. Nếu cần kiểm soát chặt chẽ thứ tự, có thể dùng Pageable với kích thước 1 và Sort.

## 14. Kiểu trả về cho count, exists và delete

Repository còn có các phương thức thể hiện kết quả dạng số hoặc boolean:

~~~java
long countByCategory(String category);

boolean existsBySku(String sku);

long deleteByCategory(String category);
~~~

Ý nghĩa:

- **countBy...** trả về số tài liệu phù hợp. Nếu không có tài liệu, kết quả là 0.
- **existsBy...** trả về true nếu có tài liệu phù hợp, false nếu không có.
- Các query method xóa có thể trả về void hoặc số lượng tài liệu bị xóa tùy khai báo và khả năng hỗ trợ của phiên bản.

Ví dụ:

~~~java
long count = productRepository.countByCategory("accessories");

boolean exists = productRepository.existsBySku("KB-1001");

if (!exists) {
    System.out.println("SKU chưa tồn tại");
}
~~~

Không dùng **count()** chỉ để kiểm tra có dữ liệu hay không nếu repository đã có phương thức **existsBy...** phù hợp. Truy vấn exists có thể diễn đạt đúng ý định hơn và tránh yêu cầu đếm toàn bộ số kết quả.

Với thao tác xóa theo điều kiện, cần hiểu rõ phạm vi truy vấn và hợp đồng của phương thức trước khi gọi. Không dùng tên phương thức mơ hồ hoặc điều kiện có thể khớp toàn bộ index ngoài ý muốn.

## 15. Projection và kiểu dữ liệu trả về tùy chỉnh

Không phải lúc nào ứng dụng cũng cần tải toàn bộ entity. Projection cho phép chỉ lấy một phần dữ liệu phù hợp với màn hình hoặc tác vụ.

Ví dụ interface projection:

~~~java
public interface ProductSummary {
    String getId();
    String getName();
    Double getPrice();
}
~~~

Một repository method có thể khai báo kiểu projection nếu cách projection được hỗ trợ bởi phiên bản và loại truy vấn:

~~~java
List<ProductSummary> findByCategory(String category);
~~~

Projection giúp tầng service chỉ phụ thuộc vào các trường cần thiết. Tuy nhiên, cần phân biệt projection ở tầng Spring Data với việc Elasticsearch có thực sự chỉ trả về một phần source hay không. Tùy cách triển khai, mapping/conversion có thể vẫn cần xử lý source của tài liệu. Nếu muốn kiểm soát trường trả về ở Elasticsearch, có thể xây dựng query với source filtering bằng API phù hợp.

Khi dùng DTO hoặc projection, tên thuộc tính và cách chuyển đổi phải tương thích với mapping của tài liệu. Không nên giả định mọi kiểu interface projection hoặc DTO projection đều được hỗ trợ giống hệt giữa các phiên bản.

## 16. Chọn kiểu trả về trong một repository thực tế

Ví dụ repository kết hợp các kiểu trả về thường gặp:

~~~java
import java.util.List;
import java.util.Optional;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    Optional<Product> findBySku(String sku);

    List<Product> findByCategory(String category);

    Page<Product> findByCategoryAndPriceBetween(
            String category,
            Double minPrice,
            Double maxPrice,
            Pageable pageable);

    SearchHits<Product> findByName(String name);

    boolean existsBySku(String sku);

    long countByCategory(String category);
}
~~~

Cách dùng:

~~~java
Optional<Product> product = repository.findBySku("KB-1001");

List<Product> accessories =
        repository.findByCategory("accessories");

Page<Product> page = repository.findByCategoryAndPriceBetween(
        "accessories",
        20.0,
        100.0,
        PageRequest.of(0, 20)
);

SearchHits<Product> hits = repository.findByName("wireless keyboard");

boolean skuExists = repository.existsBySku("KB-1001");

long categoryCount = repository.countByCategory("accessories");
~~~

Mỗi kiểu trả về biểu đạt một hợp đồng riêng. Người đọc mã có thể nhận ra ngay liệu phương thức cần một tài liệu, nhiều tài liệu, một trang kết quả hay metadata tìm kiếm.

## 17. Lỗi thường gặp khi chọn kiểu trả về

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| NullPointerException khi đọc kết quả | Query method trả entity đơn và không tìm thấy tài liệu | Dùng Optional hoặc kiểm tra null theo hợp đồng |
| IncorrectResultSizeDataAccessException | Phương thức trả về một đối tượng nhưng truy vấn khớp nhiều tài liệu | Đổi sang List/Page hoặc giới hạn kết quả rõ ràng |
| Không biết còn trang tiếp hay không | Dùng List thay vì Page/Slice | Dùng Page hoặc Slice cùng Pageable |
| Không lấy được score hoặc highlight | Chỉ trả entity, metadata hit đã bị lược bỏ | Dùng SearchHit/SearchHits |
| Dữ liệu lớn làm tăng bộ nhớ | Tải tất cả kết quả vào List | Dùng phân trang, stream hoặc cơ chế cuộn phù hợp |
| Stream giữ tài nguyên quá lâu | Không đóng stream sau khi sử dụng | Dùng try-with-resources |
| Reactive pipeline không có giá trị | Mono hoàn tất rỗng nhưng caller giả định luôn có phần tử | Dùng switchIfEmpty hoặc xử lý Mono.empty |
| Nhầm không có dữ liệu với lỗi kết nối | Bắt exception và chuyển thành kết quả rỗng | Phân loại lỗi nghiệp vụ, truy vấn và hạ tầng |
| Repository method không hỗ trợ kiểu mong muốn | Kiểu trả về hoặc query derivation khác với phiên bản đang dùng | Kiểm tra tài liệu phiên bản và dùng ElasticsearchOperations khi cần |

## 18. Nguyên tắc thiết kế hợp đồng dữ liệu

Khi khai báo repository method, có thể dựa trên các nguyên tắc sau:

1. Dùng **Optional<T>** cho truy vấn mong đợi tối đa một tài liệu và trường hợp không tồn tại là hợp lệ.
2. Dùng **List<T>** hoặc **Iterable<T>** khi truy vấn trả về nhiều tài liệu và không cần metadata phân trang.
3. Dùng **Page<T>** khi giao diện cần tổng số kết quả và thông tin trang.
4. Dùng **Slice<T>** khi chỉ cần biết có trang tiếp theo.
5. Dùng **SearchHits<T>** hoặc kiểu SearchHit khi cần score, highlight và metadata Elasticsearch.
6. Dùng **Mono<T>** hoặc **Flux<T>** trong reactive repository, không trộn lẫn với API imperative.
7. Dùng kiểu boolean và số cho truy vấn tồn tại hoặc đếm.
8. Không trả null cho collection khi không có kết quả; trả collection rỗng.
9. Không biến exception hạ tầng thành kết quả rỗng.
10. Bảo đảm kiểu trả về phù hợp với số lượng kết quả mà truy vấn có thể tạo ra.

Các kiểu trả về được hỗ trợ cụ thể phụ thuộc phiên bản Spring Data Elasticsearch, loại repository và cách xây dựng truy vấn. Với các trường hợp cần SearchHits, SearchPage, Stream, projection hoặc reactive return types, hãy đối chiếu reference documentation của đúng phiên bản dự án. Khi repository query method không thể biểu đạt đầy đủ yêu cầu, **ElasticsearchOperations** cho phép xây dựng truy vấn tường minh và kiểm soát kiểu kết quả tốt hơn.

Thiết kế kiểu trả về là một phần của hợp đồng dữ liệu giữa repository và tầng nghiệp vụ. **Optional** thể hiện rõ khả năng không tồn tại của một tài liệu; collection rỗng biểu diễn truy vấn nhiều kết quả không tìm thấy phần tử; Page và Slice biểu diễn dữ liệu phân trang; SearchHits giữ lại metadata của Elasticsearch; Mono và Flux biểu diễn kết quả reactive. Khi các hợp đồng này được chọn đúng, ứng dụng dễ xử lý trường hợp bình thường, giảm lỗi null và phân biệt được dữ liệu không tồn tại với sự cố truy cập Elasticsearch.

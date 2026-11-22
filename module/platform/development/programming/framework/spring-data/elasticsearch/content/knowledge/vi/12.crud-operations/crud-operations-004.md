# findById, findAllById và Optional

Trong Spring Data Elasticsearch, `findById` và `findAllById` là hai thao tác đọc document dựa trên định danh `_id`. `findById` nhận một ID và trả về `Optional<T>` để biểu diễn trường hợp document có thể tồn tại hoặc không tồn tại. `findAllById` nhận một tập ID và trả về các entity tìm được dưới dạng `Iterable<T>`.

Hai phương thức này thuộc repository abstraction của Spring Data, vì vậy không cần tự viết Query DSL chỉ để lấy document theo ID. `Optional` giúp code thể hiện rõ kết quả có thể vắng mặt, còn `findAllById` phù hợp khi cần đọc nhiều document đã biết ID.

Điều quan trọng là phân biệt truy xuất theo ID với tìm kiếm theo thuộc tính. `findById("product-1001")` tìm document có `_id` tương ứng. Một phương thức như `findBySku("SKU-1001")` là truy vấn theo field nghiệp vụ và thường đi qua search. Hai thao tác có semantics, hiệu năng và thời điểm nhìn thấy dữ liệu khác nhau.

## 1. Repository và kiểu ID

Giả sử ứng dụng lưu sản phẩm trong index `products`. Entity sử dụng `String` làm định danh:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    protected Product() {
    }

    public Product(String id, String sku, String name) {
        this.id = id;
        this.sku = sku;
        this.name = name;
    }

    public String getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public String getName() {
        return name;
    }
}
```

Repository:

```java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
```

Tham số generic thứ nhất là entity type (`Product`); tham số thứ hai là kiểu của thuộc tính được đánh dấu `@Id` (`String`). Repository kế thừa các thao tác CRUD, trong đó có `findById` và `findAllById`.

Nếu entity dùng `Long` làm kiểu thuộc tính `@Id`, repository cần khai báo `ElasticsearchRepository<Product, Long>`. Hãy giữ hai kiểu này nhất quán thay vì chọn kiểu generic theo cảm tính.

## 2. `findById`: tìm một document theo `_id`

Chữ ký phổ biến được kế thừa từ Spring Data `CrudRepository`:

```java
Optional<Product> findById(String id);
```

Phương thức nhận một ID và trả về `Optional<Product>`:

- Nếu document tồn tại, Optional chứa entity đã được ánh xạ.
- Nếu document không tồn tại, kết quả là `Optional.empty()`.
- Nếu có lỗi kết nối, lỗi xác thực, lỗi mapping hoặc lỗi hệ thống khác, thao tác có thể ném exception. Những lỗi này không được chuyển thành `Optional.empty()` một cách mặc định.

Ví dụ:

```java
Optional<Product> result = productRepository.findById("product-1001");

if (result.isPresent()) {
    Product product = result.get();
    System.out.println(product.getName());
} else {
    System.out.println("Product does not exist");
}
```

Đoạn code trên hợp lệ vì đã kiểm tra `isPresent()` trước khi gọi `get()`. Tuy nhiên, trong code ứng dụng thường có những cách diễn đạt ngắn gọn và an toàn hơn bằng các method của `Optional`.

### 2.1 ID phải là ID của document

Giả sử document có metadata:

```json
{
  "_index": "products",
  "_id": "product-1001",
  "_source": {
    "sku": "SKU-1001",
    "name": "Bàn phím cơ"
  }
}
```

Lời gọi:

```java
productRepository.findById("product-1001");
```

tìm theo `_id`. Lời gọi:

```java
productRepository.findById("SKU-1001");
```

chỉ tìm thấy document nếu chính `_id` của document là `SKU-1001`. Spring Data không tự hiểu chuỗi đó là field `sku`.

Muốn tìm theo SKU, cần một query method theo field hoặc query tường minh:

```java
Optional<Product> findBySku(String sku);
```

Đây là truy vấn theo thuộc tính nghiệp vụ, khác với phương thức kế thừa `findById`.

### 2.2 `findById` và thời điểm nhìn thấy document

Elasticsearch cung cấp API GET document theo ID với semantics real-time theo mặc định. Điều này khác với `_search`, vốn sử dụng searcher và chỉ nhìn thấy thay đổi sau refresh.

Vì vậy, sau khi ghi một document, thao tác đọc theo ID có thể nhìn thấy document mới trước khi một query tìm kiếm theo `sku` hoặc `name` nhìn thấy nó. Đây là hành vi bình thường của Elasticsearch.

Nếu `findById` trả về empty, hãy kiểm tra ID, index/alias và document thực tế. Nếu query theo field trả về empty ngay sau write, hãy xem xét refresh visibility trước khi kết luận thao tác save bị lỗi.

## 3. `Optional<T>` biểu diễn kết quả có thể vắng mặt

`Optional<T>` là kiểu container của Java dùng để biểu diễn một giá trị có thể có hoặc không có. Với `findById`, Optional giúp API thể hiện rõ rằng một ID hợp lệ không đảm bảo document tương ứng vẫn tồn tại.

```java
Optional<Product> found = productRepository.findById(id);
```

Hai trạng thái chính:

```java
Optional<Product> present = Optional.of(product);
Optional<Product> absent = Optional.empty();
```

Một Optional đúng nghĩa không chứa `null`. Nếu không có kết quả, nó là `Optional.empty()`. Nếu có kết quả, nó chứa entity.

### 3.1 `orElse`

`orElse(defaultValue)` trả về entity bên trong nếu Optional có giá trị; nếu không, trả về giá trị mặc định:

```java
Product product = productRepository.findById(id)
    .orElse(defaultProduct);
```

Hãy dùng giá trị mặc định chỉ khi nghiệp vụ thực sự định nghĩa một fallback hợp lệ. Với dữ liệu sản phẩm, tự tạo một `Product` rỗng khi không tìm thấy thường che giấu lỗi ID hoặc trạng thái không tồn tại.

Một điểm cần chú ý: biểu thức truyền vào `orElse(...)` được đánh giá trước khi method được gọi. Ví dụ:

```java
Product product = productRepository.findById(id)
    .orElse(createDefaultProduct());
```

`createDefaultProduct()` vẫn được gọi ngay cả khi Optional đã chứa sản phẩm. Nếu việc tạo fallback tốn tài nguyên hoặc có side effect, đây có thể là hành vi không mong muốn.

### 3.2 `orElseGet`

`orElseGet(Supplier)` chỉ gọi supplier khi Optional rỗng:

```java
Product product = productRepository.findById(id)
    .orElseGet(() -> createDefaultProduct());
```

Khác biệt:

| Cách dùng | Khi nào giá trị thay thế được tạo? |
|---|---|
| `orElse(createDefaultProduct())` | Luôn được đánh giá trước khi gọi `orElse` |
| `orElseGet(() -> createDefaultProduct())` | Chỉ tạo khi Optional empty |

Không nên dùng fallback để biến một trường hợp “không tìm thấy” thành một entity giả nếu nghiệp vụ cần phân biệt rõ hai trạng thái.

### 3.3 `orElseThrow`

Nếu document bắt buộc phải tồn tại trong ngữ cảnh nghiệp vụ, có thể ném exception khi không tìm thấy:

```java
Product product = productRepository.findById(id)
    .orElseThrow(() -> new ProductNotFoundException(id));
```

Ví dụ exception riêng:

```java
public class ProductNotFoundException extends RuntimeException {

    public ProductNotFoundException(String id) {
        super("Product not found: " + id);
    }
}
```

`orElseThrow` giúp chuyển kết quả Optional thành một entity chắc chắn tồn tại hoặc kết thúc luồng bằng exception rõ ràng. Với Java hiện đại, `orElseThrow()` không tham số cũng có thể ném `NoSuchElementException`, nhưng exception domain riêng thường giúp tầng web ánh xạ sang HTTP 404 dễ hiểu hơn.

### 3.4 `ifPresent` và `ifPresentOrElse`

Khi chỉ cần thực hiện hành động nếu có kết quả:

```java
productRepository.findById(id)
    .ifPresent(product -> auditLog(product));
```

Java 9 trở lên có `ifPresentOrElse` để xử lý cả hai trường hợp:

```java
productRepository.findById(id)
    .ifPresentOrElse(
        product -> auditLog(product),
        () -> auditMissingProduct(id)
    );
```

Không nên dùng callback chỉ để làm code ngắn hơn nếu nhánh xử lý phức tạp. Khi cần trả về giá trị, `map`, `orElseThrow` hoặc một biến cục bộ thường dễ đọc hơn.

### 3.5 `map` và `filter`

`map` biến đổi giá trị bên trong Optional mà không cần tự kiểm tra empty:

```java
Optional<String> productName = productRepository.findById(id)
    .map(Product::getName);
```

Nếu không có Product, kết quả vẫn là `Optional.empty()`. Nếu có, kết quả chứa tên sản phẩm.

`filter` giữ lại giá trị nếu điều kiện đúng:

```java
Optional<Product> availableProduct = productRepository.findById(id)
    .filter(Product::isAvailable);
```

Nếu sản phẩm không tồn tại hoặc không thỏa điều kiện, Optional kết quả sẽ empty. Hãy dùng `filter` khi ý nghĩa nghiệp vụ thực sự là “không có kết quả phù hợp”; nếu cần phân biệt không tồn tại với không khả dụng, hãy xử lý hai trạng thái riêng.

## 4. Dùng `findById` trong service

Repository nên tập trung vào truy cập dữ liệu. Service diễn đạt quy tắc nghiệp vụ và quyết định trường hợp không tìm thấy là bình thường, cần fallback hay cần báo lỗi.

```java
import org.springframework.stereotype.Service;

@Service
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public Product getRequired(String id) {
        return repository.findById(id)
            .orElseThrow(() -> new ProductNotFoundException(id));
    }

    public boolean exists(String id) {
        return repository.existsById(id);
    }
}
```

Trong service, không cần tự kiểm tra `isPresent()` rồi gọi `get()` nếu có thể dùng `orElseThrow`. Cách viết này tránh trạng thái kiểm tra và sử dụng bị tách rời, đồng thời thể hiện rõ hành vi khi document vắng mặt.

### 4.1 Ánh xạ not found thành HTTP 404

Nếu service được gọi từ REST controller, exception domain có thể được ánh xạ sang 404:

```java
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
        return ResponseEntity.ok(service.getRequired(id));
    }
}
```

Một `@ControllerAdvice` có thể bắt `ProductNotFoundException` và trả về `404 Not Found`. Ví dụ:

```java
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(ProductNotFoundException.class)
    public ResponseEntity<String> handleProductNotFound(
            ProductNotFoundException exception) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .body(exception.getMessage());
    }
}
```

Đây là một lựa chọn thiết kế. Nếu API muốn trả `404` trực tiếp khi Optional empty, controller cũng có thể chuyển Optional thành `ResponseEntity` bằng API phù hợp. Điều quan trọng là giữ semantics HTTP nhất quán và không biến lỗi hạ tầng thành 404.

## 5. `findAllById`: đọc nhiều document theo ID

Khi đã có một tập ID và cần lấy các document tương ứng, dùng:

```java
Iterable<Product> findAllById(Iterable<String> ids);
```

Ví dụ:

```java
List<String> ids = List.of(
    "product-1001",
    "product-1002",
    "product-1003"
);

Iterable<Product> products = productRepository.findAllById(ids);
```

Phương thức trả về các entity tìm được. Kiểu trả về là `Iterable<Product>` theo contract repository; không phải `Optional<List<Product>>`.

### 5.1 Các quy tắc quan trọng của `findAllById`

Theo contract của Spring Data repository:

- ID đầu vào phải khác `null` và iterable không được `null`.
- Nếu một số ID không tồn tại, các entity tương ứng đơn giản không xuất hiện trong kết quả.
- Kết quả có thể chứa ít entity hơn số ID đầu vào.
- Thứ tự phần tử trong kết quả không được bảo đảm giống thứ tự ID đầu vào.
- Không nên dựa vào hành vi trả lại phần tử trùng lặp nếu input có ID lặp.

Ví dụ input:

```java
List<String> ids = List.of(
    "product-1003",
    "missing-id",
    "product-1001"
);
```

Nếu hai document đầu/cuối tồn tại, kết quả chỉ chứa hai Product tìm được. `missing-id` không tạo ra một phần tử `null` hay một Optional rỗng trong iterable. Vì thế, không thể suy luận trực tiếp rằng phần tử thứ nhất của kết quả ứng với ID thứ nhất của input.

### 5.2 Chuyển Iterable thành List

Nếu tầng service cần một `List`, có thể chuyển đổi rõ ràng:

```java
import java.util.ArrayList;
import java.util.List;

public List<Product> findProducts(List<String> ids) {
    List<Product> result = new ArrayList<>();
    productRepository.findAllById(ids).forEach(result::add);
    return result;
}
```

Hoặc dùng stream từ `Iterable`:

```java
import java.util.stream.StreamSupport;

List<Product> result = StreamSupport
    .stream(productRepository.findAllById(ids).spliterator(), false)
    .toList();
```

Không cần chuyển đổi nếu tầng gọi chỉ cần duyệt `Iterable` một lần. Giữ kiểu trả về tổng quát cũng giúp tránh tạo thêm collection không cần thiết.

### 5.3 Giữ thứ tự theo danh sách ID đầu vào

Contract `findAllById` không bảo đảm thứ tự kết quả. Nếu API cần trả sản phẩm theo đúng thứ tự client yêu cầu, hãy lập bản đồ kết quả theo ID rồi dựng lại danh sách.

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public List<Product> findInRequestedOrder(List<String> ids) {
    Map<String, Product> foundById = new HashMap<>();

    productRepository.findAllById(ids).forEach(product ->
        foundById.put(product.getId(), product)
    );

    List<Product> ordered = new ArrayList<>();
    for (String id : ids) {
        Product product = foundById.get(id);
        if (product != null) {
            ordered.add(product);
        }
    }

    return ordered;
}
```

Đoạn code giữ thứ tự của các ID được tìm thấy. Nếu input có cùng ID nhiều lần, danh sách kết quả cũng có thể lặp lại entity tương ứng vì vòng lặp duyệt input. Nếu API không muốn lặp, hãy loại ID trùng trước khi gọi repository hoặc khi dựng kết quả.

### 5.4 Phát hiện ID bị thiếu

Nếu nghiệp vụ cần biết ID nào không tồn tại, hãy so sánh danh sách yêu cầu với các entity tìm được:

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public Set<String> findMissingIds(List<String> ids) {
    Map<String, Product> foundById = new HashMap<>();

    productRepository.findAllById(ids).forEach(product ->
        foundById.put(product.getId(), product)
    );

    Set<String> missing = new HashSet<>(ids);
    missing.removeAll(foundById.keySet());
    return missing;
}
```

`Set` phù hợp khi chỉ cần tập ID thiếu và không cần giữ thứ tự. Nếu API cần thứ tự đầu vào, dùng `LinkedHashSet` hoặc dựng danh sách theo input. Cần validate null trước khi gọi repository; `List.of(...)` và `List.copyOf(...)` tự từ chối phần tử null.

## 6. `findAllById` không giống `findAll`

Hai phương thức có mục đích khác nhau:

| Phương thức | Ý nghĩa | Khi nên dùng |
|---|---|---|
| `findById(id)` | Lấy một document theo `_id` | Đã biết ID của document cần đọc |
| `findAllById(ids)` | Lấy các document theo danh sách `_id` | Đã có tập ID cần đọc |
| `findAll()` | Lấy các document trong phạm vi repository/index theo API phân trang tương ứng | Cần duyệt dữ liệu theo page hoặc sort |
| `findBySku(sku)` | Tìm theo field nghiệp vụ `sku` | Chỉ biết SKU, không biết `_id` |

Không dùng `findAll()` rồi lọc ở Java chỉ để lấy một vài ID đã biết. Cách đó có thể tải nhiều document không cần thiết và tiêu tốn bộ nhớ, network bandwidth cũng như tài nguyên search.

Tương tự, không dùng `findAllById` nếu yêu cầu thực tế là tìm theo điều kiện như category, trạng thái hoặc khoảng giá. Khi đó cần query theo field, derived query hoặc Query DSL.

## 7. Ví dụ service tổng hợp

Một service có thể cung cấp cả thao tác đọc đơn và đọc nhiều ID:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

import org.springframework.stereotype.Service;

@Service
public class ProductLookupService {

    private final ProductRepository repository;

    public ProductLookupService(ProductRepository repository) {
        this.repository = repository;
    }

    public Optional<Product> findOptional(String id) {
        return repository.findById(id);
    }

    public Product getRequired(String id) {
        return repository.findById(id)
            .orElseThrow(() -> new ProductNotFoundException(id));
    }

    public List<Product> findMany(Iterable<String> ids) {
        List<Product> products = new ArrayList<>();
        repository.findAllById(ids).forEach(products::add);
        return products;
    }
}
```

Service giữ rõ hai chính sách:

- `findOptional` để caller tự quyết định cách xử lý khi không có document.
- `getRequired` coi việc thiếu document là lỗi nghiệp vụ và ném exception rõ ràng.
- `findMany` trả về các document tìm được; caller cần biết contract rằng ID thiếu sẽ không có phần tử tương ứng.

Không nên tạo một method duy nhất luôn trả `null` cho trường hợp không tìm thấy. `Optional` hoặc exception thể hiện ý định rõ hơn.

## 8. Đọc nhiều ID với batch lớn

`findAllById` tiện lợi cho một tập ID có kích thước hợp lý. Nhưng nếu input chứa hàng chục nghìn hoặc hàng trăm nghìn ID, một lần gọi lớn có thể tạo request/response quá lớn, tăng memory pressure và làm tăng latency.

Với batch lớn, hãy chia thành các nhóm có kích thước phù hợp:

```java
import java.util.ArrayList;
import java.util.List;

public List<Product> findInBatches(List<String> ids, int batchSize) {
    if (batchSize <= 0) {
        throw new IllegalArgumentException("batchSize must be positive");
    }

    List<Product> all = new ArrayList<>();

    for (int start = 0; start < ids.size(); start += batchSize) {
        int end = Math.min(start + batchSize, ids.size());
        List<String> batch = ids.subList(start, end);
        productRepository.findAllById(batch).forEach(all::add);
    }

    return all;
}
```

`batchSize` không có giá trị tối ưu chung. Cần đo kích thước document, số ID, response bytes, latency và tải cluster. Khi chia batch, thứ tự kết quả từ mỗi batch vẫn không được đảm bảo theo thứ tự ID trong batch; nếu cần thứ tự toàn cục, hãy dựng lại theo input như phần trước.

Với các phiên bản Spring Data Elasticsearch phổ biến, thao tác tìm nhiều ID có thể được triển khai theo hướng multi-get thay vì chạy một search query. Tuy nhiên, hãy dựa vào contract repository và tài liệu phiên bản cụ thể; không phụ thuộc vào chi tiết nội bộ chưa được bảo đảm của implementation.

## 9. Những lỗi thường gặp

### 9.1 Gọi `get()` khi Optional có thể empty

```java
Product product = repository.findById(id).get();
```

Nếu không có document, code ném `NoSuchElementException`. Dùng `orElseThrow` với exception có ý nghĩa nghiệp vụ hoặc xử lý Optional một cách tường minh.

### 9.2 Dùng `orElse(null)` rồi tiếp tục truyền null

```java
Product product = repository.findById(id).orElse(null);
```

Cách này loại bỏ lợi ích của Optional và đẩy rủi ro null sang các dòng sau. Nếu caller thực sự chấp nhận không có kết quả, giữ kiểu `Optional<Product>` qua API service. Nếu bắt buộc có kết quả, dùng `orElseThrow`.

### 9.3 Nhầm SKU với `_id`

`findById("SKU-1001")` không có nghĩa là tìm field `sku`. Hãy dùng query method `findBySku` hoặc query theo field mapping.

### 9.4 Cho rằng `findAllById` trả đúng thứ tự input

Contract không bảo đảm thứ tự. Nếu cần thứ tự, ánh xạ kết quả theo ID rồi dựng lại danh sách theo input.

### 9.5 Cho rằng ID không tồn tại tạo ra null trong kết quả

ID thiếu bị bỏ qua; iterable có thể ngắn hơn input. Nếu cần biết ID nào thiếu, so sánh tập ID yêu cầu với ID entity tìm được.

### 9.6 Xem lỗi kết nối như không tìm thấy document

`Optional.empty()` biểu thị không có document tương ứng. Lỗi kết nối, xác thực, timeout hoặc mapping thường được biểu diễn bằng exception. Không bắt mọi exception rồi trả empty, vì điều đó khiến lỗi hạ tầng bị hiểu sai thành dữ liệu không tồn tại.

### 9.7 Gọi `findAllById` với input null

Không truyền iterable null hoặc phần tử ID null. Hãy validate đầu vào ở tầng service/API và trả lỗi đầu vào phù hợp trước khi gọi repository.

### 9.8 Dùng findAll để lấy một vài document

Nếu đã có ID, hãy dùng `findAllById`. Đọc toàn bộ index rồi lọc ở Java gây lãng phí và có thể bỏ qua giới hạn phân trang.

## 10. Kiểm tra khi không tìm thấy document

Khi `findById` trả về empty, hãy xác nhận:

1. ID truyền vào có đúng giá trị đã dùng khi ghi không.
2. Entity có `@Id` trên đúng thuộc tính không.
3. `ElasticsearchRepository<Product, ID>` khai báo đúng kiểu ID không.
4. `@Document(indexName = ...)` có trỏ tới đúng index hoặc alias không.
5. Alias đang trỏ tới index vật lý nào.
6. Document có tồn tại trong index bằng API GET trực tiếp không.
7. Ứng dụng có đang kết nối đúng cluster/môi trường không.

Ví dụ kiểm tra trực tiếp:

```http
GET /products/_doc/product-1001
GET /_alias/products
GET /_cat/indices/products*?v
```

Nếu API GET trực tiếp tìm thấy document nhưng repository không tìm thấy, tập trung kiểm tra index name, ID type, mapping metadata và cấu hình repository. Nếu API GET cũng không tìm thấy, kiểm tra thao tác ghi, ID thực tế và index đích.

Đối với `findAllById`, hãy ghi lại tập ID yêu cầu và so sánh với ID trong kết quả. Đừng giả định số lượng kết quả luôn bằng số phần tử đầu vào.

## 11. Nguyên tắc sử dụng

- Dùng `findById` khi đã biết `_id` và cần lấy một document.
- Giữ kết quả `Optional<T>` cho tới khi tầng nghiệp vụ quyết định cách xử lý trường hợp vắng mặt.
- Dùng `orElseThrow` khi document bắt buộc phải tồn tại; dùng `orElseGet` khi có fallback được định nghĩa rõ.
- Dùng `findAllById` khi đã có một tập ID cần đọc.
- Nhớ rằng `findAllById` trả về `Iterable`, có thể thiếu entity và không bảo đảm thứ tự input.
- Nếu cần thứ tự, dựng lại kết quả theo danh sách ID ban đầu.
- Nếu cần biết ID nào thiếu, so sánh tập ID đầu vào và ID tìm được.
- Với batch lớn, chia request theo kích thước đã đo và kiểm soát memory/latency.
- Dùng query theo field khi chỉ biết SKU, category hoặc thuộc tính nghiệp vụ khác.
- Phân biệt document không tồn tại với lỗi kết nối, timeout và lỗi mapping.

## 12. Tổng kết

`findById` đọc một document theo `_id` và trả về `Optional<T>`, giúp biểu diễn rõ trường hợp có hoặc không có entity. `Optional` cung cấp các thao tác như `orElse`, `orElseGet`, `orElseThrow`, `ifPresent`, `map` và `filter` để xử lý kết quả mà không cần dựa vào null. Khi document bắt buộc phải tồn tại, `orElseThrow` với exception domain thường là cách diễn đạt rõ ràng.

`findAllById` nhận một iterable ID và trả về các entity tìm được dưới dạng `Iterable<T>`. ID không tồn tại bị bỏ qua, kết quả có thể ít hơn input và thứ tự không được bảo đảm. Nếu cần giữ thứ tự hoặc báo ID thiếu, hãy đối chiếu kết quả theo ID thay vì dựa vào vị trí phần tử.

Cuối cùng, hãy nhớ rằng hai phương thức này truy xuất theo định danh document. Chúng khác với search theo field nghiệp vụ như SKU hoặc tên sản phẩm. Dùng đúng abstraction giúp code CRUD dễ hiểu, xử lý missing document rõ ràng và tránh tải dữ liệu không cần thiết.

# QuerydslBindings và điều kiện bind mặc định

## 1. Vai trò trong chương Bộ lọc và payload web

Một endpoint tìm sản phẩm có thể nhận request:

```http
GET /products?name=Keyboard&status=ACTIVE&status=ARCHIVED&page=0&size=20
```

Các giá trị trong query string cần được chuyển thành điều kiện truy vấn có kiểu. Với tích hợp Querydsl của **SPRING_DATA_COMMONS**, ứng dụng có thể để Spring MVC dựng `Predicate` từ request, rồi chuyển predicate đó xuống repository hỗ trợ Querydsl.

`QuerydslBindings` mô tả **thuộc tính nào được bind và giá trị của chúng trở thành điều kiện gì**. Nó không tự chạy truy vấn hoặc tự định nghĩa toàn bộ ngôn ngữ tìm kiếm của API.

Bài này tập trung vào bind query parameter. Payload JSON trong request body là một đường binding khác, không tự được chuyển thành predicate chỉ vì có cấu hình `QuerydslBindings`.

Sau bài học, bạn có thể:

- Phân biệt ba quy tắc bind mặc định: `eq`, `contains` trên collection và `in`.
- Hiểu cách ghép điều kiện giữa các thuộc tính.
- Tùy biến binding theo kiểu hoặc theo một path cụ thể.
- Chọn `first(...)` hoặc `all(...)` theo số lượng giá trị mà API chấp nhận.
- Giới hạn trường được phép lọc và giữ điều kiện nghiệp vụ bắt buộc ở phía server.

## 2. Những thành phần cùng tham gia

| Thành phần | Trách nhiệm |
| --- | --- |
| `@QuerydslPredicate` | Đánh dấu tham số controller cần dựng predicate từ request |
| `QuerydslBindings` | Lưu quy tắc path, kiểu dữ liệu, alias và khả năng được bind |
| `QuerydslBinderCustomizer<QProduct>` | Nơi ứng dụng cấu hình các quy tắc binding cho domain |
| `QuerydslPredicateExecutor<Product>` | Hợp đồng repository để thực thi các thao tác nhận Querydsl predicate |
| `QProduct` | Kiểu Querydsl được sinh cho domain `Product` |
| `ConversionService` | Tham gia chuyển chuỗi HTTP sang kiểu dữ liệu của thuộc tính |

Luồng chính:

```text
Query string
    |
    v
MVC nhận @QuerydslPredicate(root = Product.class)
    |
    v
Chọn QuerydslBindings cho Product
    |
    v
Kiểm tra path -> chuyển kiểu giá trị -> áp dụng binding
    |
    v
Ghép các điều kiện thành Predicate
    |
    v
Controller/service bổ sung phạm vi nghiệp vụ
    |
    v
Repository hỗ trợ Querydsl thực thi truy vấn
```

`QuerydslBindings` thuộc package `org.springframework.data.querydsl.binding`. `Predicate` dùng trong bài là `com.querydsl.core.types.Predicate`, không phải `java.util.function.Predicate`.

Các ví dụ sử dụng Java 17, API Commons 3.5 và module dữ liệu có hỗ trợ Querydsl tương ứng. Trước khi áp dụng, ứng dụng cần có dependency tương thích, domain mapping, repository và cấu hình sinh Q-type. Việc thêm annotation không tự sinh `QProduct`.

Với MVC cấu hình thủ công, `@EnableSpringDataWebSupport` có thể kích hoạt tích hợp Querydsl khi các thành phần cần thiết hiện diện trên classpath. Trong Boot, cần xác định cấu hình web tự động hoặc cấu hình chủ động đang thực sự hoạt động. Phần tích hợp và binding được mô tả trong [tài liệu web support của Commons](https://docs.spring.io/spring-data/commons/reference/3.5/repositories/core-extensions-web.html).

Khả năng thực thi predicate nằm ở module lưu trữ. Không suy rằng mọi repository của mọi store đều hỗ trợ `QuerydslPredicateExecutor` hoặc cùng một tập phép toán.

## 3. Mô hình ví dụ

Giả sử domain `Product` có các thuộc tính:

| Thuộc tính | Kiểu Java | Ý nghĩa |
| --- | --- | --- |
| `id` | `Long` | Định danh sản phẩm |
| `name` | `String` | Tên hiển thị |
| `sku` | `String` | Mã sản phẩm |
| `price` | `BigDecimal` | Giá |
| `status` | `ProductStatus` | Trạng thái |
| `tags` | `Set<String>` | Nhãn của sản phẩm |
| `tenantId` | `Long` | Phạm vi tenant |
| `internalNote` | `String` | Ghi chú nội bộ |

Enum minh họa:

```java
package example.catalog;

public enum ProductStatus {
    ACTIVE,
    ARCHIVED
}
```

Các đoạn mã tiếp theo giả định `Product` đã được ánh xạ cho kho dữ liệu được chọn, có các getter phù hợp và đã sinh Q-type `QProduct`. Đây là ngữ cảnh của ví dụ, không phải một yêu cầu rằng Commons tự cung cấp entity hoặc mapping cho mọi store.

Repository cơ bản, trước khi thêm customizer:

```java
package example.catalog;

import org.springframework.data.querydsl.QuerydslPredicateExecutor;
import org.springframework.data.repository.CrudRepository;

public interface ProductRepository
        extends CrudRepository<Product, Long>,
                QuerydslPredicateExecutor<Product> {
}
```

Lớp DTO dùng để đọc kết quả:

```java
package example.catalog;

import java.math.BigDecimal;

public record ProductView(
        Long id,
        String name,
        BigDecimal price,
        ProductStatus status) {

    public static ProductView from(Product product) {
        return new ProductView(
                product.getId(),
                product.getName(),
                product.getPrice(),
                product.getStatus());
    }
}
```

DTO phản hồi là lựa chọn của ứng dụng. Binding bộ lọc đầu vào không tự quyết định những field nào sẽ xuất hiện trong JSON kết quả.

## 4. Ba quy tắc bind mặc định

Các quy tắc dưới đây áp dụng khi path được phép bind và không có binding tùy biến được chọn cho nó.

| Thuộc tính đích | Giá trị đầu vào | Điều kiện mặc định |
| --- | --- | --- |
| Thuộc tính đơn, như `name` | Một giá trị | `eq` |
| Thuộc tính đơn, như `status` | Nhiều giá trị | `in` |
| Thuộc tính collection, như `tags` | Giá trị phần tử | `contains` trên collection |

Các quy tắc chính được liệt kê trong [tài liệu Querydsl web support](https://docs.spring.io/spring-data/commons/reference/3.5/repositories/core-extensions-web.html); chi tiết thực thi nằm ở [QuerydslDefaultBinding 3.5](https://raw.githubusercontent.com/spring-projects/spring-data-commons/3.5.x/src/main/java/org/springframework/data/querydsl/binding/QuerydslDefaultBinding.java).

### 4.1. Một giá trị trên thuộc tính đơn: eq

```http
GET /products?name=Keyboard
```

Ý tưởng điều kiện:

```java
product.name.eq("Keyboard")
```

Binding mặc định không tự chuyển thành tìm chuỗi con. Một tên chứa chữ `Keyboard` nhưng không bằng giá trị đã yêu cầu không được coi là khớp chỉ vì có đoạn chữ đó.

Tính phân biệt hoa/thường thực tế còn phụ thuộc phép toán, collation và store. Điều chắc chắn ở mức binding là API chọn `eq`, không tự chọn `containsIgnoreCase`.

Với giá:

```http
GET /products?price=100.00
```

Giá trị được chuyển sang kiểu thuộc tính phù hợp, rồi dùng điều kiện bằng. Đây không phải điều kiện giá tối thiểu.

### 4.2. Nhiều giá trị trên thuộc tính đơn: in

```http
GET /products?status=ACTIVE&status=ARCHIVED
```

Ý tưởng điều kiện:

```java
product.status.in(ProductStatus.ACTIVE, ProductStatus.ARCHIVED)
```

Sản phẩm chỉ cần có một trong hai trạng thái. Đối với cùng thuộc tính đơn, đây là lựa chọn nhiều giá trị hợp lệ, không phải yêu cầu một bản ghi đồng thời có cả hai giá trị.

Tương tự:

```http
GET /products?price=100.00&price=500.00
```

mặc định biểu thị giá bằng một trong hai giá trị. Nó không tự trở thành khoảng từ `100` đến `500`.

Bài dùng tham số lặp để thể hiện rõ nhiều giá trị. Nếu API muốn hỗ trợ chuỗi phân tách bằng dấu phẩy, cần xác định và kiểm tra quy tắc chuyển đổi của chính ứng dụng thay vì mặc định mọi kiểu đều xử lý giống nhau.

### 4.3. Thuộc tính collection: contains phần tử

```http
GET /products?tags=java
```

Ý tưởng điều kiện:

```java
product.tags.contains("java")
```

Ở đây `contains` có nghĩa collection chứa phần tử. Nó khác với `StringPath.contains(...)`, vốn tìm một chuỗi con trong một chuỗi.

Trong default binding Commons 3.5, nhiều giá trị của collection được ghép bằng các điều kiện chứa kết hợp `AND`. Ví dụ:

```http
GET /products?tags=java&tags=spring
```

tương ứng về ý tưởng:

```java
product.tags.contains("java")
        .and(product.tags.contains("spring"))
```

Nếu nghiệp vụ muốn collection chứa ít nhất một nhãn được yêu cầu, cần binding tùy biến hoặc truy vấn tường minh. Không lấy quy tắc `in` của thuộc tính đơn để suy ra hành vi collection.

### 4.4. Nhiều thuộc tính được kết hợp bằng AND

Request:

```http
GET /products?name=Keyboard&status=ACTIVE&status=ARCHIVED
```

có ý tưởng:

```text
name = "Keyboard"
AND status IN (ACTIVE, ARCHIVED)
```

Điều kiện của từng path được builder kết hợp bằng `AND`. Một binding tùy biến có thể trả biểu thức chứa `OR` bên trong, nhưng điều đó khác với việc đổi toàn bộ request thành phép `OR`. Xem [QuerydslPredicateBuilder](https://raw.githubusercontent.com/spring-projects/spring-data-commons/3.5.x/src/main/java/org/springframework/data/querydsl/binding/QuerydslPredicateBuilder.java).

## 5. Tùy biến theo kiểu và theo path

### 5.1. Customizer trên repository

Thay repository cơ bản bằng phiên bản có chính sách lọc:

```java
package example.catalog;

import org.springframework.data.querydsl.QuerydslPredicateExecutor;
import org.springframework.data.querydsl.binding.QuerydslBinderCustomizer;
import org.springframework.data.querydsl.binding.QuerydslBindings;
import org.springframework.data.repository.CrudRepository;

import com.querydsl.core.types.dsl.StringPath;

public interface ProductRepository
        extends CrudRepository<Product, Long>,
                QuerydslPredicateExecutor<Product>,
                QuerydslBinderCustomizer<QProduct> {

    @Override
    default void customize(
            QuerydslBindings bindings,
            QProduct product) {

        bindings.excludeUnlistedProperties(true);

        bindings.including(
                product.name,
                product.sku,
                product.status,
                product.price);

        bindings.bind(String.class).first(
                (StringPath path, String value) ->
                        path.containsIgnoreCase(value));

        bindings.bind(product.sku).first(
                (path, value) -> path.eq(value));
    }
}
```

Ứng dụng chỉ giữ một khai báo `ProductRepository`; hai đoạn repository là hai bước phát triển ví dụ.

Customizer trên repository được tích hợp web phát hiện khi chọn binding cho domain tương ứng. Nó cấu hình cách tạo predicate từ HTTP; việc gọi `repository.findAll(predicate)` với một predicate tự viết ở nơi khác không tự chạy lại các quy tắc HTTP này.

### 5.2. Thứ tự chọn binding

Có thể hiểu thứ tự cho một path được phép bind:

```text
Có binding riêng cho path?
    -> Có: dùng binding của path
    -> Không: tìm binding cho kiểu thuộc tính
        -> Có: dùng binding theo kiểu
        -> Không: dùng default binding
```

Với ví dụ trên:

| Request | Cách diễn giải |
| --- | --- |
| `name=key` | Tìm tên chứa `key`, không phân biệt hoa/thường theo phép toán đã chọn |
| `sku=KB-001` | So sánh bằng vì binding riêng của `sku` ưu tiên hơn binding `String` |
| `status=ACTIVE&status=ARCHIVED` | Vẫn dùng default `in` vì chưa có binding riêng cho trạng thái |
| `price=100&price=500` | Vẫn dùng default `in`, không phải khoảng giá |
| `tags=java` | Không được đưa vào predicate theo danh sách path cho phép của ví dụ |

Cơ chế ưu tiên binding theo path trước binding theo kiểu được thể hiện trong [QuerydslBindings](https://raw.githubusercontent.com/spring-projects/spring-data-commons/3.5.x/src/main/java/org/springframework/data/querydsl/binding/QuerydslBindings.java).

Binding theo `String.class` có phạm vi rộng trong các path phù hợp được mở cho bộ lọc. Với mã định danh, mã nghiệp vụ hoặc dữ liệu cần so sánh chính xác, nên cân nhắc binding riêng thay vì biến tất cả thành tìm chuỗi con.

## 6. first và all: số lượng giá trị là một phần hợp đồng

### 6.1. first chỉ dùng giá trị đầu tiên để dựng điều kiện

Binding:

```java
bindings.bind(product.name).first(
        (path, value) -> path.containsIgnoreCase(value));
```

với request:

```http
GET /products?name=key&name=mouse
```

chỉ đưa giá trị đầu tiên vào biểu thức của binding này. Nó không tự tạo `name contains key OR name contains mouse`.

Đặc điểm này cũng áp dụng khi dùng `bind(String.class).first(...)`. Vì thế, thêm một default tùy biến cho `String` có thể làm thay đổi cả hành vi của tham số lặp, không chỉ cách so sánh hoa/thường.

Các giá trị vẫn đi qua giai đoạn chuyển kiểu của builder trước khi binding được gọi. Không coi `first` là cơ chế cho phép bỏ qua mọi vấn đề định dạng của các giá trị còn lại.

### 6.2. all nhận tất cả giá trị của một path

Để tên khớp ít nhất một từ khóa, thay binding riêng của `name` bằng:

```java
bindings.bind(product.name).all((path, values) -> {
    BooleanBuilder alternatives = new BooleanBuilder();

    for (String value : values) {
        alternatives.or(path.containsIgnoreCase(value));
    }

    return Optional.ofNullable(alternatives.getValue());
});
```

Import bổ sung:

```java
import java.util.Optional;
import com.querydsl.core.BooleanBuilder;
```

Với hai tên ở request trên, binding trả biểu thức theo ý tưởng:

```text
name chứa "key"
OR name chứa "mouse"
```

Nếu request còn có `status=ACTIVE`, builder kết hợp:

```text
(name chứa "key" OR name chứa "mouse")
AND status = ACTIVE
```

Tên `all` nghĩa là callback nhận tập giá trị của path đang bind. Nó không có nghĩa framework luôn ghép `AND`, cũng không có nghĩa callback nhận mọi tham số của toàn request. Chính callback quyết định cách ghép các giá trị của path đó.

Khác biệt giữa single-value và multi-value binding được mô tả trong [API QuerydslBindings](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/querydsl/binding/QuerydslBindings.html).

### 6.3. Không suy ra toán tử từ tên tham số

Một request như:

```http
GET /products?priceMin=100&priceMax=500
```

không tự tạo khoảng giá khi domain chỉ có thuộc tính `price` và chưa có binding hoặc bộ đọc filter phù hợp.

Nếu dùng `all` để diễn đạt khoảng, API phải định nghĩa rõ một giá trị nghĩa gì, hai giá trị có thứ tự ra sao, cận có bao gồm hay không và xử lý giá trị dư thế nào. Với hợp đồng phức tạp, một DTO bộ lọc tường minh rồi dựng predicate trong service có thể dễ đọc hơn.

Tương tự, chuỗi `null` trong URL không tự trở thành yêu cầu `IS NULL`. Nếu API hỗ trợ lọc giá trị null, cần thiết kế cú pháp và conversion phù hợp.

## 7. Kiểm soát path được phép bind

### 7.1. Danh sách cho phép

Cấu hình rõ ràng:

```java
bindings.excludeUnlistedProperties(true);
bindings.including(product.name, product.status);
```

giúp API chỉ công bố những path đã lựa chọn. Trong ví dụ repository phần 5, danh sách còn có `sku` và `price`.

Khi dùng chính sách này, hãy khai báo tường minh các path muốn cung cấp, thay vì chỉ viết một binding rồi suy rằng mọi thuộc tính sẽ được mở theo ý định.

Nếu domain được bổ sung `internalScore` sau này, API không nên vô tình cung cấp một bộ lọc mới chỉ vì field đó vừa xuất hiện trong mô hình persistence.

### 7.2. Danh sách loại trừ

Một chính sách khác là:

```java
bindings.excluding(product.internalNote);
```

Đây là ví dụ thay thế cho cách tiếp cận theo danh sách loại trừ. Nếu không có chính sách giới hạn khác, các thuộc tính còn lại có thể tiếp tục được xem xét theo cơ chế mặc định.

Danh sách loại trừ cần được duy trì khi domain phát triển. Với API công khai, danh sách cho phép thường làm phạm vi hỗ trợ dễ kiểm soát hơn.

Không cố tình đưa một path vào cả danh sách cho phép và loại trừ rồi dựa vào suy đoán về thứ tự ưu tiên. Chọn một chính sách nhất quán và kiểm tra đúng các path mà endpoint công bố.

### 7.3. Bỏ qua khác với từ chối request

Trong builder Commons 3.5, path không khả dụng sẽ không đóng góp điều kiện vào predicate. Vì vậy, request có tham số sai tên hoặc không được mở cho binding không mặc định bị từ chối bằng `400`.

Ví dụ, với cấu hình phần 5:

```http
GET /products?tenantId=8
```

không tạo điều kiện `tenantId=8` từ binding, vì path đó không nằm trong danh sách cho phép. Tuy nhiên, điều này chưa tạo ra bất kỳ điều kiện tenant nào ở phía server.

Nếu API muốn từ chối mọi khóa lạ, cần kiểm tra danh sách khóa request riêng. Khi kiểm tra, phải tính cả những tham số hợp lệ khác như `page`, `size` và `sort`.

Cơ chế kiểm tra path và bỏ qua path không khả dụng có thể xem trong [QuerydslPredicateBuilder](https://raw.githubusercontent.com/spring-projects/spring-data-commons/3.5.x/src/main/java/org/springframework/data/querydsl/binding/QuerydslPredicateBuilder.java).

## 8. Alias và nơi đặt customizer

### 8.1. Một customizer riêng cho lớp web

Có thể tạo một class cấu hình binding thay vì đặt chính sách trong repository:

```java
package example.catalog;

import org.springframework.data.querydsl.binding.QuerydslBinderCustomizer;
import org.springframework.data.querydsl.binding.QuerydslBindings;

public class ProductWebBindings
        implements QuerydslBinderCustomizer<QProduct> {

    @Override
    public void customize(QuerydslBindings bindings, QProduct product) {
        bindings.excludeUnlistedProperties(true);
        bindings.including(product.status, product.price);

        bindings.bind(product.name)
                .as("q")
                .first((path, value) ->
                        path.containsIgnoreCase(value));
    }
}
```

Sau đó chỉ định trên tham số controller:

```java
@QuerydslPredicate(
        root = Product.class,
        bindings = ProductWebBindings.class)
Predicate filters
```

Đây là phần khai báo tham số để tích hợp vào một phương thức controller, không phải một phương thức độc lập hoàn chỉnh.

Request tương ứng:

```http
GET /products?q=key&status=ACTIVE
```

Trong cấu hình minh họa này, `q` là alias của path `name`. Nó vẫn chỉ tìm trên `name`, không tự trở thành tìm kiếm trên mọi thuộc tính.

Alias mặc định ẩn tên path gốc, trừ khi path gốc được đưa lại vào danh sách cho phép. Nếu dùng lại danh sách `including(product.name, ...)` của ví dụ trước, cần hiểu rằng tên gốc có thể tiếp tục được mở. Chi tiết alias được ghi trong [QuerydslBindings](https://raw.githubusercontent.com/spring-projects/spring-data-commons/3.5.x/src/main/java/org/springframework/data/querydsl/binding/QuerydslBindings.java).

### 8.2. Đừng giả định mọi customizer luôn được cộng dồn

Trong factory Commons 3.5, quá trình tạo bindings áp dụng default customizer chung trước, rồi chọn customizer cụ thể. Khi annotation chỉ định một class customizer cụ thể, factory chọn class đó; nếu không có chỉ định cụ thể, nó có thể phát hiện customizer trên repository.

Do vậy, khi thay sang `bindings = ProductWebBindings.class`, không giả định rằng toàn bộ chính sách repository phần 5 tự động được chạy thêm. Class riêng cần thể hiện đầy đủ những lựa chọn mà endpoint dựa vào.

Ứng dụng cũng có thể đăng ký bean `QuerydslBinderCustomizerDefaults` cho mặc định dùng chung. Phải phân biệt lớp mặc định chung này với việc chọn customizer cụ thể và với thứ tự chọn binding theo path/kiểu trong một đối tượng `QuerydslBindings`.

Cơ chế tạo và lựa chọn được thể hiện trong [QuerydslBindingsFactory 3.5](https://raw.githubusercontent.com/spring-projects/spring-data-commons/3.5.x/src/main/java/org/springframework/data/querydsl/binding/QuerydslBindingsFactory.java).

## 9. Controller nhận predicate và pageable

Controller sau sử dụng customizer trên repository ở phần 5. Nó khai báo rõ domain root vì kiểu response là DTO, không phải domain:

```java
package example.catalog;

import java.util.Set;

import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.querydsl.binding.QuerydslPredicate;
import org.springframework.data.web.PageableDefault;
import org.springframework.data.web.PagedModel;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import com.querydsl.core.types.Predicate;

@RestController
@RequestMapping("/products")
public class ProductController {

    private static final Set<String> SORT_FIELDS =
            Set.of("id", "name", "price");

    private final ProductSearchService service;
    private final CurrentTenant currentTenant;

    public ProductController(
            ProductSearchService service,
            CurrentTenant currentTenant) {
        this.service = service;
        this.currentTenant = currentTenant;
    }

    @GetMapping
    public PagedModel<ProductView> search(
            @QuerydslPredicate(root = Product.class) Predicate filters,
            @PageableDefault(size = 20, sort = "id") Pageable pageable) {

        for (Sort.Order order : pageable.getSort()) {
            if (!SORT_FIELDS.contains(order.getProperty())) {
                throw new ResponseStatusException(
                        HttpStatus.BAD_REQUEST,
                        "Thuộc tính sort không được hỗ trợ");
            }
        }

        return new PagedModel<>(
                service.search(
                        currentTenant.requiredId(),
                        filters,
                        pageable));
    }

    public interface CurrentTenant {
        Long requiredId();
    }
}
```

`CurrentTenant` là hợp đồng ứng dụng cần triển khai bằng một bean đọc tenant từ ngữ cảnh đã xác thực. Nó phải trả định danh tenant hợp lệ hoặc chấm dứt yêu cầu theo chính sách xác thực; không lấy một tham số tùy ý của client làm bằng chứng quyền truy cập.

`ProductSearchService` được trình bày ở phần tiếp theo. Các bean cần thiết vẫn phải được đăng ký trong context.

Ba phần cấu hình có trách nhiệm riêng:

- `@QuerydslPredicate` cùng bindings đọc bộ lọc.
- Resolver `Pageable` đọc phân trang và sort.
- `PagedModel` biểu diễn kết quả trả về.

Danh sách path được lọc của `QuerydslBindings` không tự giới hạn sort. Vì thế ví dụ kiểm tra sort riêng trước khi gọi service. Giới hạn page size cũng cần cấu hình riêng ở resolver hoặc chính sách ứng dụng.

Thuộc tính `root` được giải thích trong [API QuerydslPredicate](https://docs.spring.io/spring-data/commons/docs/3.5.x/api/org/springframework/data/querydsl/binding/QuerydslPredicate.html): nên chỉ định rõ khi kiểu domain không được thể hiện phù hợp trong kiểu trả về của phương thức.

## 10. Điều kiện bắt buộc phải do server kết hợp

Danh sách path cho phép chỉ kiểm soát điều kiện mà client được yêu cầu. Với ứng dụng nhiều tenant, vẫn cần một điều kiện server để giới hạn dữ liệu.

Ví dụ service đồng bộ:

```java
package example.catalog;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;

import com.querydsl.core.BooleanBuilder;
import com.querydsl.core.types.Predicate;

@Service
public class ProductSearchService {

    private final ProductRepository repository;

    public ProductSearchService(ProductRepository repository) {
        this.repository = repository;
    }

    public Page<ProductView> search(
            Long tenantId,
            Predicate clientFilters,
            Pageable pageable) {

        QProduct product = QProduct.product;

        BooleanBuilder effective = new BooleanBuilder(
                product.tenantId.eq(tenantId));

        effective.and(clientFilters);

        return repository.findAll(effective, pageable)
                .map(ProductView::from);
    }
}
```

Ví dụ giả định module lưu trữ hỗ trợ các path và phép toán này, đồng thời phạm vi transaction cần thiết đã được ứng dụng cấu hình theo module.

Điều kiện có dạng:

```text
tenantId = tenant đã xác thực
AND (predicate được dựng từ bộ lọc client)
```

Ngay cả khi client không gửi bộ lọc nào hoặc mọi path được gửi đều bị bỏ qua, điều kiện tenant vẫn tồn tại.

Nếu binding `name` tự trả biểu thức `OR`, kết hợp `AND` ở bên ngoài vẫn giữ phạm vi:

```text
tenantId = 7
AND (name chứa "key" OR name chứa "mouse")
```

Cách này cũng có thể mở rộng cho điều kiện xóa mềm, trạng thái được phép đọc hoặc quyền sở hữu. Không đặt những điều kiện bắt buộc chỉ vào giá trị mặc định của request, vì request có thể thiếu hoặc bị thay đổi.

Đặc biệt, không chỉ chặn client gửi `tenantId` rồi kết luận dữ liệu đã được giới hạn tenant. Việc chặn path và việc áp dụng phạm vi truy vấn là hai bước độc lập.

## 11. Giá trị rỗng, chuyển kiểu và hợp đồng API

### 11.1. Chuỗi HTTP cần được chuyển đúng kiểu

Các giá trị như `price=100.50` hoặc `status=ACTIVE` cần chuyển sang kiểu thuộc tính trước khi áp dụng binding.

Nếu một giá trị không chuyển được sang số, enum hoặc ngày tháng, đó là lỗi định dạng đầu vào, không phải một điều kiện hợp lệ chỉ tình cờ không có kết quả.

Định dạng enum, số và ngày phụ thuộc conversion service cùng các formatter hoặc converter đã cấu hình. API nên công bố định dạng được hỗ trợ và kiểm tra hành vi lỗi qua đường HTTP thực tế.

### 11.2. Giá trị trống có thể làm mất điều kiện

Trong builder Commons 3.5, một tham số chỉ có một giá trị rỗng có thể được bỏ qua. Do đó:

```http
GET /products?name=
```

không nên được hiểu mặc định là yêu cầu `name = ""`. Một request lặp có cả phần tử rỗng và phần tử có nội dung cũng không nên bị suy là hoàn toàn tương đương trường hợp một giá trị rỗng.

Ứng dụng cần quyết định:

- Có chuẩn hóa khoảng trắng không?
- Một trường có bắt buộc nhập ít nhất một ký tự không?
- Có cho phép nhiều giá trị với trường đang dùng `first` không?
- Số lượng giá trị tối đa là bao nhiêu?
- Bỏ qua điều kiện hay trả lỗi khi giá trị không phù hợp?

Với `all`, trả `Optional.empty()` có nghĩa không tạo predicate cho path đó. Không dùng cách này để âm thầm nuốt lỗi đầu vào nếu việc bỏ điều kiện làm kết quả rộng hơn điều người dùng dự định.

### 11.3. Bind được chưa có nghĩa truy vấn hiệu quả

Một bộ lọc `containsIgnoreCase` có thể có chi phí khác với so sánh bằng. Nhiều giá trị trong `in`, nhiều nhánh `OR` hoặc path qua quan hệ cũng có thể làm truy vấn tốn kém.

Cần giới hạn hợp lý độ dài chuỗi, số giá trị, page size và các path được công bố. Đồng thời kiểm tra khả năng module, index và kế hoạch truy vấn theo dữ liệu thực tế.

Querydsl cung cấp biểu thức có kiểu; nó không bảo đảm mọi biểu thức đều có chi phí phù hợp trên mọi store.

## 12. Thực hành đọc điều kiện từ request

Nên thực hành theo từng giai đoạn cấu hình để không trộn quy tắc mặc định với quy tắc tùy biến.

### 12.1. Chưa có custom binding

| Request | Điều kiện cần nhận diện |
| --- | --- |
| `name=Keyboard` | `name.eq("Keyboard")` |
| `status=ACTIVE&status=ARCHIVED` | `status.in(...)` |
| `price=100&price=500` | Chọn một trong hai mức giá |
| `tags=java` | Collection chứa nhãn `java` |
| `tags=java&tags=spring` | Trong default binding 3.5, collection cần chứa cả hai nhãn |
| `name=Keyboard&status=ACTIVE` | Điều kiện tên và trạng thái được ghép `AND` |

### 12.2. Với customizer repository phần 5

| Request | Điều cần quan sát |
| --- | --- |
| `name=key` | Binding chuỗi tìm chứa không phân biệt hoa/thường |
| `sku=KB-001` | Binding path riêng giữ phép so sánh bằng |
| `name=key&name=mouse` | Chỉ giá trị đầu tham gia binding `first` của tên |
| `tags=java` | Path không nằm trong danh sách cho phép của ví dụ |
| `tenantId=8` | Không tạo điều kiện client cho path tenant |
| Không có filter | Service vẫn áp dụng tenant đã xác thực |
| `sort=internalNote` | Controller ví dụ từ chối qua chính sách sort riêng |

### 12.3. Sau khi thay name sang all

Với binding `all` ở phần 6, gửi lại:

```http
GET /products?name=key&name=mouse&status=ACTIVE
```

Quan sát predicate có nhóm tên ghép `OR`, còn trạng thái và tenant được kết hợp bên ngoài bằng `AND`.

Có thể đặt breakpoint ở customizer, callback binding và service để thấy lần lượt cấu hình được chọn, giá trị đã chuyển kiểu và predicate cuối cùng. Khi kiểm tra kết quả, dùng dữ liệu có tên chỉ khớp từ khóa thứ nhất, chỉ khớp từ khóa thứ hai và không khớp từ nào.

Việc xem predicate giúp hiểu binding. Để xác nhận khả năng thực thi, cần quan sát kết quả và truy vấn của module dữ liệu thực tế.

## 13. Lỗi thường gặp

| Biểu hiện | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Không có `QProduct` | Chưa cấu hình hoặc chưa sinh Q-type đúng cho domain | Kiểm tra toolchain và dependency tương thích của module |
| Import được predicate nhưng controller không resolve được | Sai loại `Predicate` hoặc thiếu tích hợp Querydsl web | Dùng `com.querydsl.core.types.Predicate` và cấu hình MVC phù hợp |
| Framework suy domain sai khi trả DTO | Chưa chỉ định domain root phù hợp | Dùng `@QuerydslPredicate(root = Product.class)` |
| Tìm tên không ra vì chỉ nhập một phần | Đang dùng default `eq` | Chọn binding tìm chuỗi con nếu hợp đồng cần |
| Chỉ một giá trị được dùng dù gửi nhiều | Binding tùy biến dùng `first` | Thiết kế `all` hoặc từ chối tham số lặp |
| Hai mức giá không tạo khoảng | Default nhiều giá trị trên thuộc tính đơn là `in` | Định nghĩa binding hoặc DTO bộ lọc cho khoảng |
| Tham số sai tên không trả lỗi | Path không khả dụng bị bỏ qua | Thêm kiểm tra khóa request khi API cần chế độ nghiêm ngặt |
| Alias và tên gốc đều dùng được | Path gốc vẫn được cho phép tường minh | Kiểm tra lại danh sách path và hợp đồng alias |
| Customizer repository không chạy như kỳ vọng | Endpoint đang chỉ định customizer class riêng | Kiểm tra nguồn cấu hình thực sự được factory chọn |
| Chặn `tenantId` nhưng vẫn đọc dữ liệu nhiều tenant | Chưa bổ sung điều kiện server vào truy vấn | Kết hợp predicate tenant bắt buộc bằng `AND` |
| Whitelist filter không chặn được sort | Binding filter và resolver sort có vai trò riêng | Kiểm tra sort riêng |
| Bind thành công nhưng truy vấn lỗi hoặc chậm | Phép toán hoặc path không phù hợp với module và dữ liệu | Kiểm tra khả năng store, mapping và truy vấn thực tế |

Khi công bố một bộ lọc, hãy ghi rõ path nào được phép dùng, giá trị được chuyển sang kiểu nào, phép so sánh nào được áp dụng, tham số lặp có ý nghĩa gì và điều kiện server nào luôn được giữ. Đó là cơ sở để dùng `QuerydslBindings` nhất quán với hợp đồng repository và phạm vi dữ liệu của ứng dụng.

# DomainClassConverter để chuyển ID thành entity

## 1. Bài toán trong chương Tham số web

Giả sử ứng dụng có endpoint đọc sản phẩm:

```http
GET /products/42
```

Giá trị `42` trong URL là chuỗi. Controller cần một đối tượng sản phẩm được lưu trong kho dữ liệu. Cách viết quen thuộc là nhận ID rồi tra cứu:

```java
@GetMapping("/products/{id}")
public ProductView detail(@PathVariable("id") Long id) {
    return productService.findById(id);
}
```

`productService` và `ProductView` trong đoạn trên là thành phần của ứng dụng. Trong những trường hợp tra cứu đơn giản, Spring Data có thể thực hiện bước chuyển đổi ngay khi Spring MVC chuẩn bị tham số:

```java
@GetMapping("/products/{id}")
public ProductView detail(@PathVariable("id") Product product) {
    return ProductView.from(product);
}
```

Thành phần hỗ trợ cơ chế đó là `DomainClassConverter`, thuộc package:

```java
org.springframework.data.repository.support.DomainClassConverter
```

Converter nhận đầu vào có thể chuyển sang kiểu ID của một domain class, rồi sử dụng repository của domain class để tra cứu đối tượng. Đây là chức năng của **SPRING_DATA_COMMONS**, được mô tả trong [API của DomainClassConverter](https://docs.spring.io/spring-data/jpa/reference/data-commons/3.5/api/java/org/springframework/data/repository/support/DomainClassConverter.html).

Trong tên bài, “entity” là đối tượng domain được repository quản lý. Khái niệm này không chỉ dành cho JPA. Khả năng lưu trữ, ánh xạ định danh và thực thi truy vấn vẫn thuộc module dữ liệu cụ thể.

Sau bài học, bạn có thể:

- Giải thích hai bước chuyển chuỗi thành ID, rồi ID thành entity.
- Cấu hình tích hợp MVC và repository cần thiết.
- Dùng domain object trong `@PathVariable` hoặc `@RequestParam`.
- Phân biệt lỗi định dạng ID với tài nguyên không tồn tại.
- Chọn giữa converter và service nhận ID khi cần phân quyền, tenant hoặc transaction rõ ràng.

## 2. Cơ chế: chuyển kiểu và tra cứu là hai bước khác nhau

Với repository quản lý `Product` có ID kiểu `Long`, luồng chính có thể hình dung như sau:

```text
GET /products/42
        |
        v
Spring MVC lấy giá trị path variable: "42"
        |
        v
Hạ tầng conversion nhận kiểu đích: Product
        |
        v
Metadata repository xác định kiểu ID: Long
        |
        v
ConversionService chuyển "42" -> 42L
        |
        v
Repository thực hiện tra cứu theo ID
        |
        v
Product hoặc kết quả không tìm thấy
        |
        v
MVC kiểm tra yêu cầu của tham số
        |
        v
Gọi phương thức controller nếu binding thành công
```

`DomainClassConverter` tham gia hạ tầng conversion của Spring. Nó khác với resolver chuyên tạo `Pageable`: ở đây tham số vẫn là một path variable hoặc request parameter được MVC đọc, nhưng kiểu đích cần chuyển đổi là domain class.

Có thể dùng đoạn giả mã sau để ghi nhớ ý tưởng; đây không phải bản cài đặt framework:

```java
Long id = conversionService.convert(rawValue, Long.class);
Product product = productRepository.findById(id).orElse(null);
```

Implementation Commons 3.5 sử dụng metadata repository, `ConversionService` và lớp trung gian `RepositoryInvoker`; khi thao tác tìm theo ID không có kết quả, nhánh chuyển sang entity trả `null`. Xem [mã nguồn chính thức của DomainClassConverter](https://raw.githubusercontent.com/spring-projects/spring-data-commons/3.5.x/src/main/java/org/springframework/data/repository/support/DomainClassConverter.java).

Ba hệ quả thực tế:

1. **Chuyển đổi có thể phát sinh truy cập dữ liệu.** Đây không chỉ là thao tác parse chuỗi trong bộ nhớ.
2. **Kiểu ID được lấy từ metadata.** Controller không quyết định ID là `Long`, `UUID` hay kiểu khác chỉ bằng tên biến.
3. **Controller chạy sau bước resolve tham số.** Nếu chuyển đổi thất bại, breakpoint trong thân controller có thể chưa được chạm tới.

Kết quả truy vấn là domain object theo hợp đồng của repository. Với JPA, trạng thái managed hay detached phụ thuộc persistence context và transaction đang hoạt động; không phải thuộc tính do converter bảo đảm.

## 3. Điều kiện để sử dụng

### 3.1. Web support phải hoạt động

Với ứng dụng Spring MVC cấu hình thủ công, có thể kích hoạt bằng:

```java
package example.catalog;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.web.config.EnableSpringDataWebSupport;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;

@Configuration
@EnableWebMvc
@EnableSpringDataWebSupport
public class CatalogWebConfiguration {
}
```

Class cấu hình phải được nạp vào application context phục vụ MVC. Các controller và repository cũng phải được ứng dụng đăng ký.

Annotation web support đăng ký tích hợp giúp MVC chuyển request parameter hoặc path variable sang domain type. Cách kích hoạt cùng điều kiện repository được nêu trong [tài liệu web support của Commons](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions-web.html).

Nếu ứng dụng Spring Boot trên Servlet stack đã được auto-configuration thiết lập Spring Data web support, thường không cần thêm cấu hình kích hoạt thủ công. Không thêm `@EnableWebMvc` chỉ để dùng converter trong Boot; cần giữ cách quản lý MVC nhất quán với ứng dụng. Bài học này tập trung vào đường xử lý MVC, không giả định cấu hình đó áp dụng nguyên trạng cho WebFlux.

### 3.2. Phải có repository phù hợp

Ví dụ dùng hợp đồng chung:

```java
package example.catalog;

import java.util.Optional;

import org.springframework.data.repository.CrudRepository;

public interface ProductRepository extends CrudRepository<Product, Long> {

    Optional<Product> findByIdAndTenantId(Long id, Long tenantId);
}
```

Tài liệu web support hiện nêu repository cần triển khai `CrudRepository` để đủ điều kiện được converter phát hiện. Dùng hợp đồng này giúp thể hiện rõ thao tác tìm theo ID mà ví dụ dựa vào.

Không chỉ khai báo một class `Product` là đủ. Module lưu trữ phải tạo repository bean với metadata domain và ID đúng. Việc bật web support không tự cấu hình cơ sở dữ liệu hoặc sinh repository khi phần persistence còn thiếu.

Phương thức `findByIdAndTenantId` trong ví dụ là truy vấn riêng của ứng dụng. Converter không tự chọn nó chỉ vì nó tồn tại; phần sau dùng phương thức này để minh họa tra cứu có phạm vi qua service.

### 3.3. Ví dụ domain cụ thể với JPA

Để các đoạn mã có một mô hình xuyên suốt, ví dụ sau chọn JPA và ID được ứng dụng gán:

```java
package example.catalog;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "products")
public class Product {

    @Id
    private Long id;

    private Long tenantId;

    private String name;

    protected Product() {
    }

    public Product(Long id, Long tenantId, String name) {
        this.id = id;
        this.tenantId = tenantId;
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public Long getTenantId() {
        return tenantId;
    }

    public String getName() {
        return name;
    }
}
```

Ứng dụng thực hành vẫn cần dependency JPA tương thích, cấu hình persistence, quét entity và repository, cùng dữ liệu mẫu. Constructor trên nhận ID trực tiếp vì ví dụ không cấu hình cơ chế sinh ID.

Các annotation `jakarta.persistence` là lựa chọn của ví dụ JPA. Khi dùng MongoDB hoặc JDBC, phải thay bằng mô hình và mapping phù hợp. Hợp đồng chuyển định danh sang domain object của Commons vẫn cần được đánh giá cùng khả năng của module đó.

## 4. Dùng trong controller và trả DTO

### 4.1. DTO phản hồi

```java
package example.catalog;

public record ProductView(Long id, String name) {

    public static ProductView from(Product product) {
        return new ProductView(product.getId(), product.getName());
    }
}
```

Ví dụ dùng Java record để biểu diễn dữ liệu đọc. DTO chỉ công bố `id` và `name`; trường `tenantId` vẫn phục vụ phạm vi dữ liệu bên trong ứng dụng.

Converter giải quyết **đầu vào** của controller. Việc chuyển entity sang DTO response là quyết định riêng, giúp hợp đồng HTTP không phụ thuộc trực tiếp vào toàn bộ mô hình persistence.

### 4.2. Path variable và request parameter

```java
package example.catalog;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/products")
public class ProductController {

    @GetMapping("/{id}")
    public ProductView detail(@PathVariable("id") Product product) {
        return ProductView.from(product);
    }

    @GetMapping("/lookup")
    public ProductView lookup(@RequestParam("id") Product product) {
        return ProductView.from(product);
    }
}
```

Hai request minh họa:

```http
GET /products/42
GET /products/lookup?id=42
```

Chúng đều cung cấp một định danh để chuyển sang `Product`. Mapping tĩnh `/lookup` diễn đạt endpoint tra cứu bằng query parameter; mapping `/{id}` diễn đạt định danh trong đường dẫn.

Viết rõ tên trong `@PathVariable("id")` và `@RequestParam("id")` giúp quan hệ với request dễ đọc, đồng thời tránh phụ thuộc vào việc suy tên tham số Java từ cấu hình biên dịch.

Controller không inject repository, nhưng truy vấn vẫn tồn tại trong luồng xử lý. Khi đọc mã, phải nhìn cả chữ ký tham số để nhận diện truy cập dữ liệu này.

Hai phương thức trên là ví dụ cho trường hợp tìm thấy dữ liệu. Hành vi khi không tìm thấy cần được thiết kế như phần 6, đặc biệt vì các tham số hiện để `required` theo mặc định.

## 5. Converter luôn tra cứu theo định danh nào?

Tên path variable không quyết định thuộc tính dùng để tìm dữ liệu.

Ví dụ:

```java
@GetMapping("/products/by-code/{code}")
public ProductView byCode(@PathVariable("code") Product product) {
    return ProductView.from(product);
}
```

Đoạn này không tự gọi `findByCode`. Với `ProductRepository` quản lý `Product` và ID kiểu `Long` ở trên, chuỗi trong `code` vẫn phải chuyển được sang `Long` và được dùng làm ID.

Nếu muốn tra cứu mã nghiệp vụ như `SKU-001`, hãy nhận chuỗi rồi gọi service sử dụng truy vấn theo mã:

```java
@GetMapping("/products/by-code/{code}")
public ProductView byCode(@PathVariable("code") String code) {
    return productService.findByBusinessCode(code);
}
```

Đây là phương án thay thế, không đăng ký đồng thời hai phương thức cùng mapping. `productService` và `findByBusinessCode` là thành phần ứng dụng cần triển khai.

Cũng không cần trường định danh trong Java luôn mang tên `id`. Nếu domain có thuộc tính `pk` được đánh dấu là định danh và một thuộc tính thông thường tên `id`, thao tác CRUD `findById` nhắm vào định danh `pk`. Quy tắc phương thức dành riêng này được giải thích trong [tài liệu defining query methods](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html).

Phân biệt ba thứ:

| Thành phần | Vai trò |
| --- | --- |
| Tên biến HTTP, như `id` hoặc `code` | Xác định giá trị được lấy từ request |
| Kiểu ID trong metadata repository | Xác định cách chuyển kiểu và định danh dùng cho CRUD |
| Derived query, như `findByCode` | Diễn đạt truy vấn ứng dụng chọn gọi tường minh |

Thay tên tham số HTTP không làm converter tự chuyển từ CRUD sang derived query, Query by Example hoặc projection.

## 6. ID sai định dạng và entity không tồn tại

### 6.1. Các trường hợp không giống nhau

Giả sử repository có ID kiểu `Long`:

| Tình huống | Điều xảy ra | Quyết định cần có |
| --- | --- | --- |
| `/products/42`, có sản phẩm | Chuyển được ID và tra cứu có kết quả | Chuyển entity sang response phù hợp |
| `/products/abc` | Không chuyển được chuỗi sang `Long` | Trả lỗi đầu vào theo cơ chế xử lý exception |
| `/products/999`, không có sản phẩm | Chuyển ID thành công nhưng lookup không có kết quả | Xác định chính sách tài nguyên không tồn tại |
| Không gửi `id` cho `/products/lookup` | Thiếu request parameter bắt buộc | Xử lý lỗi thiếu tham số |
| Gọi `/products` nhưng chỉ khai báo `/{id}` | Không có segment để khớp mapping đó | Phụ thuộc các mapping khác của ứng dụng |

`CrudRepository.findById` trả `Optional.empty()` khi không tìm thấy đối tượng. Đó là kết quả lookup, không phải quyết định HTTP. Xem [hợp đồng findById](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/CrudRepository.html).

### 6.2. Vì sao không tự có 404?

Converter không tự ném một exception mang nghĩa nghiệp vụ “sản phẩm không tồn tại”. Với implementation đã mô tả, kết quả không tìm thấy có thể trở thành `null`.

MVC còn kiểm tra yêu cầu của tham số sau conversion. Tham số `@PathVariable` hoặc `@RequestParam` bắt buộc có thể bị từ chối trước khi controller được gọi nếu conversion tạo ra `null`. Tài liệu [type conversion của MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/typeconversion.html) mô tả việc kiểm tra giá trị thiếu sau chuyển đổi.

Cụ thể, ở Spring Framework 6.2, `MissingPathVariableException` có trạng thái `400` khi giá trị đã có nhưng trở thành `null` sau conversion. Exception do tên path variable không khớp template là tình huống khác. Xem [mã nguồn MissingPathVariableException 6.2](https://raw.githubusercontent.com/spring-projects/spring-framework/6.2.x/spring-web/src/main/java/org/springframework/web/bind/MissingPathVariableException.java).

Vì vậy, không viết hợp đồng API dựa trên giả định rằng “ID không tìm thấy qua converter luôn trả 404”. HTTP status thực tế còn chịu ảnh hưởng của phiên bản Framework, annotation và exception handler trong ứng dụng.

### 6.3. Xử lý null tường minh tại endpoint đơn giản

Khi chấp nhận lookup tự động nhưng muốn quyết định `404` ngay tại controller, có thể dùng một chữ ký thay thế:

```java
@GetMapping("/{id}")
public ResponseEntity<ProductView> detail(
        @PathVariable(value = "id", required = false) Product product) {

    if (product == null) {
        return ResponseEntity.notFound().build();
    }

    return ResponseEntity.ok(ProductView.from(product));
}
```

Import bổ sung:

```java
import org.springframework.http.ResponseEntity;
```

Chữ ký này thay cho phương thức `detail` ở phần 4. Với đường dẫn đã khớp mapping, controller chấp nhận kết quả chuyển đổi `null` và tự trả `404`.

Cần giữ các phân biệt sau:

- `required = false` không làm `/products` tự khớp với `/products/{id}`.
- ID sai định dạng vẫn có thể làm conversion thất bại; đây không phải trường hợp lookup trả `null`.
- Exception do mất kết nối hoặc truy vấn lỗi không nên được đổi hàng loạt thành `404`.
- Chính sách tenant và quyền đọc vẫn chưa được bổ sung chỉ bằng việc xử lý `null`.

Cũng có thể thiết kế xử lý tập trung, nhưng phải phân biệt đúng exception và ngữ cảnh. Ánh xạ mọi lỗi binding thành “không tìm thấy sản phẩm” sẽ che khuất lỗi request hoặc lỗi cấu hình.

## 7. Khi cần nhận ID và tra cứu qua service

### 7.1. Converter không tự áp dụng phạm vi nghiệp vụ

Trong hệ thống có nhiều tenant, ID hợp lệ không đủ để cho phép đọc tài nguyên. Cần giới hạn truy vấn theo tenant đã xác thực.

Repository ở phần 3 có cả `findById` kế thừa và `findByIdAndTenantId` do ứng dụng khai báo. Chữ ký `@PathVariable Product product` không làm converter tự chọn phương thức thứ hai.

Điều tương tự áp dụng cho:

- Điều kiện tài nguyên chưa bị xóa mềm.
- Điều kiện trạng thái nghiệp vụ cho phép xem.
- Quyền sở hữu của người dùng hiện tại.
- Quan hệ giữa tài nguyên con và tài nguyên cha trong URL.

Ví dụ:

```http
GET /shops/7/products/42
```

Nếu MVC chuyển `42` thành một `Product`, điều đó chưa chứng minh sản phẩm thuộc shop `7`. Ứng dụng phải kiểm tra quan hệ hoặc truy vấn với cả hai định danh.

Các bộ lọc persistence đã được cấu hình riêng có thể ảnh hưởng kết quả lookup, nhưng đó là hành vi của ứng dụng hoặc provider; converter không tự suy ra chúng từ cấu trúc URL.

### 7.2. Service truy vấn theo tenant

Một phương án tường minh dùng repository đã khai báo:

```java
package example.catalog;

import java.util.Optional;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductQueryService {

    private final ProductRepository repository;

    public ProductQueryService(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public Optional<ProductView> findForTenant(
            Long productId, Long tenantId) {

        return repository.findByIdAndTenantId(productId, tenantId)
                .map(ProductView::from);
    }
}
```

Ví dụ này tiếp tục sử dụng JPA, có transaction manager và hạ tầng transaction phù hợp. Service trả DTO sau khi đã áp dụng phạm vi dữ liệu.

Controller có thể nhận ID rồi gọi service:

```java
package example.catalog;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/products")
public class ScopedProductController {

    private final ProductQueryService queries;
    private final CurrentTenant currentTenant;

    public ScopedProductController(
            ProductQueryService queries,
            CurrentTenant currentTenant) {
        this.queries = queries;
        this.currentTenant = currentTenant;
    }

    @GetMapping("/{id}")
    public ResponseEntity<ProductView> detail(
            @PathVariable("id") Long id) {

        return ResponseEntity.of(
                queries.findForTenant(id, currentTenant.requiredId()));
    }

    public interface CurrentTenant {
        Long requiredId();
    }
}
```

Đây là **phương án thay thế controller trước**, không đăng ký đồng thời hai controller có cùng mapping. `CurrentTenant` là hợp đồng ứng dụng phải triển khai bằng một bean lấy tenant từ ngữ cảnh đã xác thực. Không dùng giá trị tenant tùy ý do client gửi làm bằng chứng quyền truy cập.

Trong phương án này:

1. MVC chuyển chuỗi sang `Long`, chưa tự tải `Product`.
2. Controller lấy tenant hợp lệ của request.
3. Service truy vấn theo cả ID và tenant.
4. Kết quả có dữ liệu thành `200`; `Optional.empty()` được controller biểu diễn thành `404`.

Việc dùng `404` cho tài nguyên ngoài phạm vi là chính sách minh họa. Nếu ứng dụng cần phân biệt `403` với `404`, hãy thiết kế điều kiện kiểm tra và hợp đồng lỗi riêng.

## 8. Transaction, lazy loading và ghi dữ liệu

### 8.1. Lookup có thể xảy ra trước transaction của service

Với chữ ký nhận entity qua converter, thứ tự thường là:

```text
MVC resolve tham số
    -> converter lookup entity
    -> gọi controller
    -> controller gọi service
    -> bắt đầu transaction của service nếu có
```

Một annotation `@Transactional` trên phương thức service được gọi sau đó không tự kéo lookup đã xảy ra trước đó vào cùng transaction.

Repository hoặc một transaction đang tồn tại có thể tạo phạm vi riêng cho lookup. Với JPA, cơ chế mở persistence context trong request cũng có thể làm thay đổi thời gian entity còn gắn với context. Không nên suy ra trạng thái này chỉ từ chữ ký controller.

Nếu cần tải quan hệ, kiểm tra quyền và chuyển DTO trong cùng ranh giới transaction, cách service nhận ID thường dễ kiểm soát hơn.

### 8.2. Entity được resolve chưa bảo đảm toàn bộ đồ thị đã tải

Ví dụ controller truy cập `product.getCategory().getName()` có thể:

- Phát sinh truy vấn bổ sung khi quan hệ được tải trễ.
- Thất bại nếu persistence context cần thiết không còn hoạt động.
- Làm chi phí endpoint phụ thuộc cách serialize domain object.

Các tình huống trên thuộc cơ chế persistence và thiết kế truy vấn, không được converter giải quyết. Chọn fetch plan hoặc projection phù hợp tại tầng dữ liệu, rồi chuyển thành response DTO trong phạm vi đã xác định.

Không dựa vào việc Jackson serialize entity để quyết định dữ liệu nào được tải hoặc được phép công bố.

### 8.3. Đọc được entity không đồng nghĩa đã cập nhật dữ liệu

Converter thực hiện tra cứu để tạo tham số. Nó không tự gọi `save`, không kiểm tra toàn bộ bất biến nghiệp vụ và không biến một đối tượng đầu vào thành lệnh cập nhật.

Với endpoint ghi, thường nên nhận ID và DTO yêu cầu, rồi để service:

1. Tải tài nguyên trong đúng phạm vi.
2. Kiểm tra quyền và trạng thái nghiệp vụ.
3. Áp dụng thay đổi trong transaction phù hợp.
4. Lưu theo hợp đồng module và xử lý kiểm soát đồng thời nếu cần.

Entity đã đọc trước đó không bảo đảm vẫn mới ở thời điểm ghi. Nếu hệ thống dùng optimistic locking hoặc cơ chế tương đương, cần giữ quy tắc version ở lớp nghiệp vụ và persistence.

Các trường auditing cũng không tự được điền chỉ vì converter vừa tải entity. Auditing thuộc cấu hình và vòng đời ghi dữ liệu của module tương ứng.

## 9. ID tùy chỉnh, DTO và các abstraction liên quan

### 9.1. Kiểu ID phải chuyển đổi được

Với `Long` hoặc `UUID`, cần request có định dạng mà conversion service của ứng dụng chấp nhận. Với một kiểu ID do ứng dụng định nghĩa, ví dụ `ProductKey`, phải có:

- Mapping ID tương thích với module lưu trữ.
- Repository khai báo đúng kiểu ID.
- Converter hoặc formatter đọc được biểu diễn HTTP sang kiểu ID đó.

Ví dụ sau chỉ minh họa phần chuyển kiểu ID cho một mô hình thay thế:

```java
public record ProductKey(java.util.UUID value) {
}
```

Đăng ký vào MVC thông qua cấu hình:

```java
import java.util.UUID;

import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
class ProductKeyWebConfiguration implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(
                String.class,
                ProductKey.class,
                text -> new ProductKey(UUID.fromString(text)));
    }
}
```

Đoạn này không biến mô hình JPA dùng `Long` ở phần trước thành mô hình dùng `ProductKey`. Để sử dụng thật, domain mapping và repository phải được thiết kế nhất quán với ID tùy chỉnh, và module được chọn phải hỗ trợ cách ánh xạ đó.

Chỉ đăng ký converter vào một conversion service không được MVC sử dụng sẽ không giải quyết đầu vào controller. Việc tùy biến conversion của MVC được mô tả trong [tài liệu type conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/typeconversion.html).

### 9.2. DomainClassConverter không phải bộ máy mapping tổng quát

| Nhu cầu | Cơ chế phù hợp |
| --- | --- |
| Đọc ID và tìm domain object bằng repository | `DomainClassConverter` trong tình huống phù hợp |
| Đọc JSON yêu cầu vào DTO | HTTP message conversion và binding body |
| Kiểm tra DTO đầu vào | Validation cùng quy tắc nghiệp vụ |
| Lấy một phần dữ liệu theo projection | Truy vấn repository hỗ trợ projection |
| Truy vấn theo ví dụ | Query by Example do ứng dụng chủ động dựng |
| Chuyển entity thành response | Mapper hoặc hàm chuyển DTO của ứng dụng |

Viết `@PathVariable("id") ProductView view` không làm converter tự biết phải tải `Product` rồi áp dụng hàm `ProductView.from`. Kiểu đích thông thường phải là domain class mà repository quản lý; DTO response không tự trở thành domain type.

Tương tự, converter không chọn derived query tùy ý và không làm mọi store có cùng khả năng truy vấn. Spring Data Commons cung cấp abstraction dùng chung, còn ứng dụng phải áp dụng đúng hợp đồng của repository và kho dữ liệu thực tế.

## 10. Chi phí tra cứu và khả năng quan sát

Một tham số entity có thể ẩn thao tác truy vấn trong giai đoạn binding. Với controller nhận nhiều domain object, cần tính cả các lookup trước khi vào thân phương thức.

Không cam kết rằng mỗi chuyển đổi luôn tương ứng đúng một câu SQL hoặc một request tới kho dữ liệu. Cache, persistence context và implementation repository có thể ảnh hưởng số lần truy cập vật lý. Điều cần nhớ là conversion có thể dẫn tới thao tác đọc repository và phải được tính vào chi phí endpoint.

Với yêu cầu xử lý nhiều ID, service nhận danh sách ID có thể tổ chức truy vấn theo lô, chẳng hạn dùng thao tác phù hợp với `findAllById`, thay vì phụ thuộc vào nhiều lần chuyển entity rời rạc.

Khi quan sát hành vi:

- Đặt breakpoint hoặc log ở tầng repository để thấy lookup trước controller.
- Phân biệt lỗi parse ID, kết quả lookup rỗng và exception truy cập dữ liệu.
- Xem các truy vấn phát sinh khi tạo DTO hoặc serialize response.
- Kiểm tra phạm vi tenant tại truy vấn thực tế, không chỉ ở URL.

Converter không thay thế việc đo chi phí truy vấn, thiết kế index hoặc chọn projection hiệu quả.

## 11. Thực hành và lựa chọn cách triển khai

### 11.1. Tập dữ liệu minh họa

Chuẩn bị dữ liệu trong môi trường học:

| ID | Tenant | Tên |
| --- | --- | --- |
| `42` | `7` | Bàn phím |
| `43` | `8` | Chuột |

Giả định không có sản phẩm ID `999`. Với từng phương án controller, quan sát riêng:

| Request | Điều cần xác minh |
| --- | --- |
| `GET /products/42` | Chuyển được ID; lookup xảy ra trước thân controller nhận entity |
| `GET /products/abc` | Lỗi chuyển sang `Long`; không coi là lookup không tìm thấy |
| `GET /products/999` | So sánh tham số bắt buộc với phương án chấp nhận `null` và trả `404` |
| `GET /products/lookup?id=42` | Request parameter cũng có thể dùng chuyển đổi domain |
| `GET /products/lookup` | Hành vi thiếu tham số bắt buộc |
| `GET /products/43`, tenant hiện tại là `7` | Phương án service có phạm vi không trả dữ liệu tenant `8` |

Chỉ đăng ký một phương án controller cho mỗi mapping khi thực hành. Có thể dùng HTTP client và quan sát log repository; không cần giả định controller được gọi ở mọi trường hợp lỗi.

Nếu dùng kiểm tra MVC với context tối thiểu, cần bảo đảm web support, metadata repository và các bean cần thiết thực sự có mặt. Chỉ dựng controller trực tiếp rồi gọi phương thức Java không kiểm tra được conversion của request.

### 11.2. Khi nào nên dùng converter?

| Tình huống | Lựa chọn thường dễ kiểm soát |
| --- | --- |
| Trang đọc đơn giản, lookup theo ID là đủ và quyền truy cập đã được xử lý phù hợp | Có thể dùng domain parameter |
| API cần tenant, quan hệ cha/con hoặc điều kiện xóa mềm | Nhận ID, truy vấn có phạm vi qua service |
| Cần kiểm soát rõ `404`, `403` và lỗi nghiệp vụ | Service nhận ID cùng chính sách lỗi tường minh |
| Endpoint cập nhật nhiều bước | Service quản lý transaction và kiểm tra trạng thái |
| Domain có quan hệ tải trễ hoặc response cần projection riêng | Truy vấn và chuyển DTO trong phạm vi được thiết kế |
| Xử lý nhiều ID hoặc cần tối ưu truy vấn theo lô | Service tổ chức truy vấn tập hợp |

Sử dụng converter là một lựa chọn giảm mã tra cứu cho trường hợp phù hợp. Quyết định nên dựa trên phạm vi dữ liệu, hợp đồng lỗi và ranh giới transaction của endpoint.

## 12. Lỗi thường gặp và cách suy luận

| Biểu hiện | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Không chuyển được chuỗi sang domain class | Web support chưa hoạt động, thiếu repository hoặc metadata không phù hợp | Kiểm tra cấu hình MVC và repository được đăng ký |
| ID tùy chỉnh luôn bị từ chối | Thiếu converter cho kiểu ID hoặc MVC không dùng conversion service đã tùy biến | Đăng ký chuyển kiểu ID đúng hạ tầng MVC |
| Controller không được gọi khi ID không tồn tại | Conversion tạo `null` nhưng tham số vẫn bắt buộc | Thiết kế xử lý `null` hoặc dùng service nhận ID |
| Kỳ vọng `404` nhưng nhận lỗi binding | Đang dựa vào mặc định của Framework thay vì hợp đồng tài nguyên | Xử lý lỗi tài nguyên tường minh |
| Đổi biến thành `code` nhưng không tìm theo mã nghiệp vụ | Converter vẫn dùng định danh repository | Gọi truy vấn theo mã qua service |
| Đọc được dữ liệu tenant khác | Lookup chỉ dựa vào ID, thiếu phạm vi đã xác thực | Truy vấn theo ID và tenant hoặc cơ chế kiểm soát tương đương |
| Truy cập quan hệ gây lỗi hoặc nhiều truy vấn | Entity chưa có đồ thị dữ liệu phù hợp với response | Chọn fetch plan hoặc projection, tạo DTO trong phạm vi phù hợp |
| Nhận entity rồi thay đổi nhưng dữ liệu không được lưu như kỳ vọng | Nhầm conversion với luồng cập nhật persistence | Tổ chức thao tác ghi qua service và transaction |

Khi đọc chữ ký `@PathVariable Product product`, hãy kiểm tra bốn câu hỏi: giá trị HTTP được chuyển sang kiểu ID nào, repository nào được gọi, phạm vi dữ liệu được áp dụng ở đâu và kết quả không tồn tại được biểu diễn ra sao? Trả lời được chúng giúp sử dụng `DomainClassConverter` đúng vai trò trong Spring Data Commons.

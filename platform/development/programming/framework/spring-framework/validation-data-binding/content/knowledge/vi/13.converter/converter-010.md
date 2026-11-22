# Phân biệt chuyển đổi dữ liệu với kiểm tra quyền hoặc truy vấn nghiệp vụ

Trong Spring Framework, `Converter<S, T>` có một trách nhiệm rõ ràng: chuyển một giá trị từ kiểu nguồn `S` sang kiểu đích `T`. Ví dụ, nó có thể biến chuỗi `"ab-012"` thành value object `ProductCode("AB-012")`. Nó không nên quyết định người dùng hiện tại có quyền sử dụng mã này không, mã có tồn tại trong database không, hay sản phẩm có đủ hàng để đặt không.

Ba nhóm công việc cần được tách bạch:

1. **Conversion (chuyển đổi):** biến một biểu diễn thành giá trị có kiểu theo quy tắc cú pháp và chuẩn hóa đã xác định.
2. **Authorization (kiểm tra quyền):** xác định principal hiện tại có được phép thực hiện hành động trên tài nguyên cụ thể hay không.
3. **Business lookup và rule (truy vấn, quy tắc nghiệp vụ):** lấy dữ liệu có thẩm quyền và quyết định hành động có hợp lệ theo trạng thái nghiệp vụ hay không.

Nếu đặt cả ba trong `Converter.convert(...)`, conversion sẽ phụ thuộc database, security context và transaction; khó test, khó tái sử dụng, có thể tạo truy vấn lặp ẩn trong binding và làm sai lệch loại lỗi. Bài này giải thích ranh giới đó bằng ví dụ Java 17+ và Spring Framework 6.2.x.

## 1. Ba câu hỏi khác nhau

Giả sử request gửi:

```text
productCode = "ab-012"
quantity    = "2"
```

Ứng dụng cần trả lời ba câu hỏi:

| Câu hỏi | Ví dụ | Thành phần phù hợp |
| --- | --- | --- |
| Giá trị có thể chuyển thành kiểu đích không? | `"ab-012"` có đúng cú pháp mã sản phẩm? | `Converter<String, ProductCode>` |
| Người gọi có quyền đặt hàng không? | User hiện tại có quyền tạo đơn trong tenant/kho này? | Spring Security / authorization service |
| Dữ liệu và trạng thái có thỏa nghiệp vụ không? | Mã có tồn tại? Còn bán? Kho đủ 2 đơn vị? | Application service / repository / domain rule |

Luồng thường gặp:

```text
HTTP request
  productCode = "ab-012"
  quantity    = "2"
        |
        v
Binding + Conversion
  String -> ProductCode
  String -> Integer
        |
        v
DTO có kiểu, cú pháp hợp lệ
        |
        v
Authentication / Authorization
  Ai đang gọi? Có quyền trên tài nguyên?
        |
        v
Business lookup + rules
  Tìm sản phẩm, kiểm tra trạng thái, tồn kho
        |
        v
Thực hiện nghiệp vụ / trả lỗi phù hợp
```

Các bước có thể được tổ chức khác nhau theo kiến trúc, nhưng conversion không thay authorization hoặc lookup. Converter có thể được gọi từ MVC form binding, BeanWrapper, code khác dùng ConversionService, batch hoặc test. Nó không nên cần biết toàn bộ request hay người dùng hiện tại.

## 2. Conversion: chuyển kiểu và chuẩn hóa biểu diễn

Conversion biến một giá trị đã có thành một giá trị có kiểu khác, ví dụ:

- `String -> Integer`: `"42"` thành số 42.
- `String -> UUID`: chuỗi UUID thành đối tượng UUID.
- `String -> ProductCode`: chuẩn hóa và kiểm tra cú pháp mã sản phẩm.
- `Long -> CustomerId`: tạo value object từ id số.
- `String -> LocalDate`: parse theo định dạng đã quy định.

Interface chính trong Spring Core có dạng:

```java
package org.springframework.core.convert.converter;

public interface Converter<S, T> {
    T convert(S source);
}
```

Đây là hình dạng rút gọn của interface. Method `convert` nhận một source value và trả về giá trị đích; nếu không chuyển đổi được, implementation có thể ném exception phù hợp. API cơ bản không nhận principal, request, repository hay transaction làm tham số.

Một converter nên trả lời: “giá trị này có thể biểu diễn bằng kiểu đích theo contract đã công bố không?”. Ví dụ mã sản phẩm bắt buộc theo mẫu `AA-999`. Nếu chuỗi không đúng mẫu, từ chối là conversion failure vì không thể tạo value object hợp lệ.

**Đúng cú pháp không đồng nghĩa tồn tại.** `AB-012` có thể trở thành `ProductCode("AB-012")` dù database không chứa sản phẩm đó. Converter không cần biết catalog để làm việc của nó.

### 2.1. Đặc điểm của converter tốt

- Kết quả phụ thuộc source và quy tắc chuyển đổi đã xác định.
- Không truy cập database hoặc network.
- Không gọi service có side effect.
- Không đọc principal hoặc security context.
- Không giữ trạng thái theo request giữa các lần gọi.
- Có hành vi xác định và dễ unit test.
- Input sai không bị âm thầm biến thành giá trị hợp lệ khác.

“Thuần” ở đây là ranh giới kiến trúc: converter không cần trạng thái bên ngoài thay đổi theo người dùng, tenant hoặc database. Nó có thể dùng cấu hình bất biến, nhưng nếu phải hỏi dữ liệu mới nhất tại thời điểm request thì đó thường là lookup, không còn là conversion đơn giản.

## 3. Authorization: người gọi có được phép không?

Authorization kiểm tra quyền của principal đã xác thực đối với hành động/tài nguyên. Nó thường cần biết:

- Ai là người gọi?
- Hành động nào đang được yêu cầu?
- Tài nguyên cụ thể nào bị ảnh hưởng?
- Tài nguyên thuộc tenant/owner/phạm vi nào?
- Authority, scope hoặc policy nào đang áp dụng?
- Quyền có phụ thuộc trạng thái resource hay quan hệ giữa các đối tượng không?

Ví dụ, `ProductCode("AB-012")` có cú pháp hợp lệ và sản phẩm tồn tại, nhưng user A không được đặt hàng thay tenant B. Quyết định từ chối thuộc authorization.

Spring Security hỗ trợ authorization ở request level và method level. Service có thể được bảo vệ bằng `@PreAuthorize` (khi đã bật method security), hoặc thực hiện policy trong application service khi quyền phụ thuộc dữ liệu domain. Kiểm tra phải được thực hiện ở server tại điểm thực hiện hành động; việc ẩn nút trên UI không bảo vệ endpoint.

```java
@Service
public class OrderApplicationService {
    @PreAuthorize("hasAuthority('order:create')")
    public OrderResult createOrder(CreateOrderCommand command) {
        // Có thể cần kiểm tra thêm quyền trên resource/tenant cụ thể.
        ...
    }
}
```

Đây là đoạn minh họa kiến trúc, không phải class hoàn chỉnh. Authority `order:create` là policy ví dụ; method-level annotation không tự chứng minh caller có thể truy cập mọi product hay tenant trong command.

**Không đưa `SecurityContextHolder` vào converter để kiểm tra quyền.** Cùng một chuỗi sẽ cho kết quả conversion khác nhau theo user, dù cú pháp không thay đổi. Converter cũng có thể chạy trong batch, background job, test hoặc bean configuration mà không có security context HTTP.

## 4. Business lookup: dữ liệu có tồn tại và trạng thái có đáp ứng không?

Business lookup là truy vấn nguồn dữ liệu có thẩm quyền, thường qua repository hoặc service. Ví dụ:

- Product code có record tương ứng không?
- Sản phẩm còn active hay đã ngừng bán?
- Người mua có được áp dụng contract/price list nào?
- Giá nào có hiệu lực tại thời điểm đặt hàng?
- Kho còn đủ số lượng không?
- Quantity có vượt hạn mức của khách không?

Một service điển hình:

```java
@Service
public class OrderApplicationService {
    private final ProductRepository products;
    private final AuthorizationService authorization;

    public OrderApplicationService(
            ProductRepository products,
            AuthorizationService authorization) {
        this.products = products;
        this.authorization = authorization;
    }

    public OrderResult create(
            CurrentUser user, CreateOrderCommand command) {
        Product product = products.findByCode(command.productCode())
                .orElseThrow(ProductNotFoundException::new);

        authorization.requireCanOrder(user, product);
        product.requireActive();
        product.requireAvailable(command.quantity());

        return placeOrder(user, product, command.quantity());
    }
}
```

Đây là pseudocode cần các class/interface nghiệp vụ. Thứ tự lookup và authorization tùy policy, ví dụ có ứng dụng query theo tenant ngay từ đầu để không tiết lộ resource ngoài phạm vi. Điểm cốt lõi là application service phối hợp lookup, policy và domain rule; converter chỉ tạo được `ProductCode`.

### 4.1. Lookup không phải validation cú pháp

`findByCode("AB-012")` là truy vấn. Nó có thể không tìm thấy record dù chuỗi hợp lệ. Ngược lại, nếu chuỗi sai cú pháp, không cần truy vấn database để nhận ra nó không phải mã hợp lệ.

Tách các giai đoạn giúp:

- Không gọi DB cho input hiển nhiên sai.
- Không gộp “không chuyển được kiểu” với “không tìm thấy”.
- Trả HTTP status và error code chính xác hơn.
- Dễ kiểm soát caching và hiệu năng lookup.
- Không khiến ConversionService phụ thuộc persistence.

## 5. Cây quyết định: logic thuộc tầng nào?

```text
Bạn đang muốn xác định điều gì?
        |
        +-- Chuyển biểu diễn/kiểu?
        |       -> Converter / Formatter / value object
        |
        +-- Người gọi có được phép?
        |       +-- Role/scope tổng quát -> Spring Security
        |       +-- Quyền trên resource/tenant -> authorization policy
        |
        +-- Dữ liệu/trạng thái có đáp ứng?
                +-- Cần persistent data -> repository qua service
                +-- Rule trên aggregate -> domain model/service
```

Một câu hỏi review hữu ích: **Nếu source value giống hệt nhưng đổi người dùng hoặc database thì kết quả có nên đổi không?**

- Kết quả chuyển đổi nên giữ nguyên: dấu hiệu logic thuộc converter.
- Kết quả phụ thuộc principal/permission: thuộc authorization.
- Kết quả phụ thuộc record, giá, tồn kho hoặc trạng thái: thuộc lookup/business rule.

Có trường hợp danh mục mã được cấu hình và nạp thành dữ liệu bất biến khi khởi động. Điều đó có thể là cấu hình chuyển đổi nếu chỉ là bảng alias tĩnh. Nhưng nếu câu hỏi là “giá trị này hiện có tồn tại hoặc được phép dùng không?”, hãy xử lý ở lookup/policy.

## 6. Ví dụ Java 17+ chạy được: converter thuần, service mới tra cứu

Ví dụ chạy độc lập bằng Maven với Spring Core. Nó minh họa:

1. Value object `ProductCode` tự bảo vệ invariant cú pháp.
2. Converter chuẩn hóa source, không cần database.
3. ConversionService gọi converter.
4. Repository và authorization được biểu diễn bằng interface riêng.
5. Application service phối hợp lookup, quyền và rule nghiệp vụ.

Để chương trình tự chạy không cần database hoặc Spring Security server, repository và authorization được triển khai bằng fake in-memory. Ứng dụng thật thay chúng bằng adapter persistence/security phù hợp.

### 6.1. Cấu trúc project

```text
conversion-boundary-demo/
├── pom.xml
└── src/main/java/ConversionBoundaryDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>conversion-boundary-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/ConversionBoundaryDemo.java`:

```java
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

import org.springframework.core.convert.converter.Converter;
import org.springframework.core.convert.support.DefaultConversionService;

public class ConversionBoundaryDemo {

    public record ProductCode(String value) {
        public ProductCode {
            if (value == null || !value.matches("[A-Z]{2}-[0-9]{3}")) {
                throw new IllegalArgumentException("Invalid product code");
            }
        }
    }

    // Chỉ parse và chuẩn hóa; không truy cập repository/security.
    public static final class ProductCodeConverter
            implements Converter<String, ProductCode> {
        @Override
        public ProductCode convert(String source) {
            if (source == null || source.isBlank()) {
                throw new IllegalArgumentException("Product code is required");
            }
            String normalized = source.trim().toUpperCase(Locale.ROOT);
            return new ProductCode(normalized);
        }
    }

    public record User(String username, Set<String> permissions) {}
    public record Product(ProductCode code, boolean active) {}
    public record CreateOrderCommand(ProductCode productCode, int quantity) {}
    public record OrderResult(String message) {}

    public interface ProductRepository {
        Optional<Product> findByCode(ProductCode code);
    }

    public interface ProductAuthorization {
        void requireCanOrder(User user, Product product);
    }

    public static final class InMemoryProductRepository
            implements ProductRepository {
        private final Map<ProductCode, Product> data;

        public InMemoryProductRepository(Map<ProductCode, Product> data) {
            this.data = Map.copyOf(data);
        }

        @Override
        public Optional<Product> findByCode(ProductCode code) {
            return Optional.ofNullable(data.get(code));
        }
    }

    public static final class PermissionCheck
            implements ProductAuthorization {
        @Override
        public void requireCanOrder(User user, Product product) {
            if (!user.permissions().contains("order:create")) {
                throw new SecurityException("Order permission required");
            }
        }
    }

    public static final class OrderApplicationService {
        private final ProductRepository repository;
        private final ProductAuthorization authorization;

        public OrderApplicationService(
                ProductRepository repository,
                ProductAuthorization authorization) {
            this.repository = repository;
            this.authorization = authorization;
        }

        public OrderResult create(User user, CreateOrderCommand command) {
            if (command.quantity() <= 0) {
                throw new IllegalArgumentException(
                        "Quantity must be positive");
            }

            Product product = repository.findByCode(command.productCode())
                    .orElseThrow(() ->
                            new IllegalStateException("Product not found"));

            authorization.requireCanOrder(user, product);

            if (!product.active()) {
                throw new IllegalStateException("Product is inactive");
            }

            return new OrderResult(
                    "Order accepted for " + product.code().value());
        }
    }

    public static void main(String[] args) {
        DefaultConversionService conversions =
                new DefaultConversionService();
        conversions.addConverter(new ProductCodeConverter());

        ProductCode existingCode = new ProductCode("AB-012");
        ProductRepository repository = new InMemoryProductRepository(
                Map.of(existingCode, new Product(existingCode, true))
        );

        ProductAuthorization authorization = new PermissionCheck();
        OrderApplicationService orders =
                new OrderApplicationService(repository, authorization);

        User buyer = new User("linh", Set.of("order:create"));
        User viewer = new User("minh", Set.of("catalog:read"));

        ProductCode validCode =
                conversions.convert(" ab-012 ", ProductCode.class);
        OrderResult accepted = orders.create(
                buyer, new CreateOrderCommand(validCode, 2));
        System.out.println("valid=" + accepted.message());

        // Cú pháp hợp lệ, nhưng repository không chứa mã này.
        ProductCode unknownCode =
                conversions.convert("ZZ-999", ProductCode.class);
        try {
            orders.create(buyer, new CreateOrderCommand(unknownCode, 1));
        } catch (IllegalStateException ex) {
            System.out.println("lookup=" + ex.getMessage());
        }

        // Cùng product/cùng code; principal khác và thiếu quyền.
        try {
            orders.create(viewer, new CreateOrderCommand(validCode, 1));
        } catch (SecurityException ex) {
            System.out.println("authorization=" + ex.getMessage());
        }

        // Sai cú pháp: thất bại trước lookup.
        try {
            conversions.convert("not-a-code", ProductCode.class);
        } catch (IllegalArgumentException ex) {
            System.out.println("conversion=Invalid product code");
        }
    }
}
```

Chạy trong thư mục `conversion-boundary-demo`:

```bash
mvn -q compile exec:java -Dexec.mainClass=ConversionBoundaryDemo
```

Đầu ra dự kiến từ các câu lệnh `System.out.println`:

```text
valid=Order accepted for AB-012
lookup=Product not found
authorization=Order permission required
conversion=Invalid product code
```

### 6.2. Phân tích từng trường hợp

**Conversion:** `conversions.convert(" ab-012 ", ProductCode.class)` chuẩn hóa input và tạo `ProductCode`. Converter không có dependency `ProductRepository` hoặc `ProductAuthorization`.

**Lookup:** `ZZ-999` đúng cú pháp nên convert thành công. Repository không có record tương ứng, nên service trả “Product not found”.

**Authorization:** cùng `ProductCode("AB-012")` và cùng record, user `linh` có quyền `order:create` nên được phép; user `minh` thiếu quyền nên bị từ chối. Kết quả quyền khác nhau theo principal, nhưng kết quả conversion không đổi.

**Business rule:** service còn kiểm tra quantity dương và product active. Những quy tắc này không thuộc converter.

**Giới hạn demo:** repository in-memory không mô phỏng transaction, concurrency, dữ liệu thật hoặc Spring Security context. Ví dụ chỉ minh họa vị trí mỗi trách nhiệm. Với database thật, repository là adapter được inject và thay đổi trạng thái cần transaction thích hợp.

## 7. Vì sao converter không nên truy vấn database?

Một implementation như sau là phản-pattern:

```java
public class ProductConverter
        implements Converter<String, Product> {

    private final ProductRepository repository;

    @Override
    public Product convert(String source) {
        return repository.findByCode(new ProductCode(source))
                .orElseThrow(ProductNotFoundException::new);
    }
}
```

Đây không phải cách khuyến nghị. Các vấn đề:

1. **Conversion phụ thuộc database:** cùng source string, kết quả đổi theo thời điểm record được thêm/xóa.
2. **Query ẩn trong binding:** binder có thể gọi converter nhiều lần; mỗi lần có thể tạo một query không rõ ràng.
3. **Sai loại lỗi:** “parse sai” và “không tìm thấy record” bị gộp trong lỗi conversion/type mismatch.
4. **Khó tái sử dụng:** batch, log, message handler hoặc test muốn parse code cũng phải có persistence.
5. **Khó tối ưu:** caller không thể dễ gom lookup, kiểm soát fetch plan hoặc phân trang.
6. **Transaction không rõ:** conversion có thể xảy ra ở nhiều context; I/O ẩn làm khó hiểu vòng đời transaction.
7. **Coupling tầng:** hạ tầng conversion phải biết persistence và exception domain.

Cách phù hợp là converter tạo `ProductCode`; application service nhận `ProductCode` để tìm product. Nếu form cần gợi ý thông tin sản phẩm, xây endpoint/query service có contract rõ thay vì biến parser thành service tra cứu.

### 7.1. Dữ liệu cấu hình có thể tham gia conversion không?

Có thể có bảng alias nhỏ, ổn định được nạp bất biến khi khởi động. Nếu nó chỉ mô tả quy tắc biểu diễn, không phụ thuộc principal/request và không thay đổi theo trạng thái nghiệp vụ, việc dùng cấu hình đó trong converter có thể hợp lý.

Nhưng nếu dữ liệu thay đổi và cần được truy vấn đúng thời điểm, hoặc câu hỏi là “giá trị này có tồn tại/được phép dùng ngay bây giờ không?”, hãy dùng lookup/policy. Cache không biến lookup nghiệp vụ thành conversion.

## 8. Vì sao converter không nên kiểm tra quyền?

Một converter có thể được gọi khi binding form, khi dùng BeanWrapper, trong test, batch job hoặc khi code khác gọi ConversionService. Không phải context nào cũng có user HTTP đã xác thực.

Nếu converter đọc `SecurityContextHolder.getContext()`:

- Cùng chuỗi có thể convert khác nhau theo user, dù cú pháp không đổi.
- Background job/async thread có thể không có security context.
- Conversion test phải dựng principal giả dù chỉ muốn test parsing.
- Reviewer khó nhận ra authorization đang ẩn phía sau property assignment.
- Một lời gọi conversion để kiểm tra/format dữ liệu có thể vô tình trigger policy.

Authorization cần chạy tại **điểm thực hiện hành động**. Ví dụ endpoint tạo đơn phải gọi service được bảo vệ; nếu quyền phụ thuộc resource, service tiếp tục kiểm tra đúng product/tenant.

### 8.1. Request authorization và method authorization

Spring Security có thể bảo vệ endpoint theo authority:

```java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.POST, "/orders")
        .hasAuthority("order:create")
        .anyRequest().authenticated());
```

Đây là đoạn cấu hình trong ứng dụng Spring Security; cần filter chain, imports và dependency tương ứng. Nó kiểm tra quyền tổng quát trên endpoint.

Với quyền phụ thuộc tài nguyên, service có thể dùng:

```java
@PreAuthorize("hasAuthority('order:create')")
public OrderResult createOrder(CreateOrderCommand command) {
    Product product = repository.findByCode(command.productCode())
            .orElseThrow(ProductNotFoundException::new);
    authorization.requireCanOrder(currentUser(), product);
    return createFor(product, command.quantity());
}
```

Đây là minh họa cần bật method security và có cách lấy principal phù hợp. Annotation không thay việc kiểm tra tenant/owner khi policy cần các thông tin đó.

### 8.2. Không vô tình tiết lộ sự tồn tại của resource

Có API muốn trả `404` cho cả hai tình huống: product không tồn tại hoặc caller không được phép biết product đó tồn tại. API khác trả `403` nếu resource có tồn tại nhưng user thiếu quyền. Đây là quyết định về **information disclosure**, không phải lựa chọn của converter.

Thứ tự lookup/authorization phụ thuộc policy. Ví dụ, query repository có thể ràng buộc tenant lấy từ principal ngay từ đầu, không tải resource ngoài tenant. Điều quan trọng là policy rõ ràng, thống nhất và chạy phía server.

## 9. Converter, Formatter, Validator và authorization không thay thế nhau

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| `Converter<S,T>` | Chuyển kiểu nguồn sang kiểu đích | `String -> ProductCode` |
| `Formatter<T>` | Parse/print theo `Locale` | `String <-> BigDecimal` |
| `Validator` / Bean Validation | Kiểm tra ràng buộc trên input/object | `quantity >= 1` |
| Authorization service | Kiểm tra quyền principal trên hành động/resource | Có quyền `order:create`? |
| Repository | Truy xuất dữ liệu persistent | Tìm product theo code/tenant |
| Application service | Phối hợp lookup, policy, domain rule, transaction | Tạo order |

Converter có thể từ chối chuỗi sai cú pháp. Đó vẫn là conversion failure. Nhưng rule “sản phẩm đang active” phụ thuộc database/trạng thái tại thời điểm xử lý, không phải format rule.

Validator cũng không phải authorization. `@NotNull` bảo đảm property có giá trị; nó không bảo đảm người gọi được quyền gán giá trị đó. `@Min(1)` kiểm tra số lượng dương; nó không chứng minh kho còn hàng.

Ví dụ DTO:

```java
public record CreateOrderRequest(
        @jakarta.validation.constraints.NotNull ProductCode productCode,
        @jakarta.validation.constraints.Min(1) int quantity
) {}
```

Đây là model minh họa cần Bean Validation provider và cơ chế kích hoạt validation. Constraint kiểm tra form value. Sau khi validation đạt, app service vẫn phải lookup product, kiểm tra quyền và tồn kho.

## 10. Sử dụng Converter với ConversionService và DataBinder

Đăng ký converter trong `ConversionService`:

```java
DefaultConversionService conversions =
        new DefaultConversionService();
conversions.addConverter(new ProductCodeConverter());

ProductCode code =
        conversions.convert("ab-012", ProductCode.class);
```

Đây là đoạn code dùng `ProductCodeConverter` trong ví dụ. Chuyển đổi được gọi tường minh, không cần security context.

Với `DataBinder`:

```java
PurchaseForm target = new PurchaseForm();
DataBinder binder = new DataBinder(target, "purchaseForm");

DefaultConversionService conversions =
        new DefaultConversionService();
conversions.addConverter(new ProductCodeConverter());
binder.setConversionService(conversions);

MutablePropertyValues values = new MutablePropertyValues();
values.add("productCode", "ab-012");
binder.bind(values);

BindingResult result = binder.getBindingResult();
```

Đây là đoạn tích hợp cần class `PurchaseForm` có setter nhận `ProductCode`. `DataBinder` chuyển kiểu để gán property và ghi lỗi binding nếu conversion thất bại. Nếu cần validation, đăng ký validator và gọi `binder.validate()` hoặc kích hoạt validation trong MVC; conversion không tự chạy mọi rule nghiệp vụ.

Với Spring MVC, converter cho form/web binding có thể đăng ký qua `WebMvcConfigurer.addFormatters(FormatterRegistry)`:

```java
@Configuration
class WebConversionConfig implements WebMvcConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new ProductCodeConverter());
    }
}
```

Đây là đoạn cấu hình MVC cần imports và class converter; đặt trong component scan. Nó chỉ bổ sung khả năng chuyển kiểu cho binder, không làm converter thành service nghiệp vụ.

**`@RequestBody` JSON là một luồng khác:** JSON thường được deserialize bằng HTTP message converter (ví dụ Jackson). Đăng ký Spring Core Converter không đồng nghĩa mọi JSON serializer/deserializer tự động dùng nó. Cấu hình JSON mapping riêng nếu API cần.

## 11. Phân loại lỗi theo giai đoạn

Ứng dụng nên phân biệt các failure:

| Giai đoạn | Ví dụ | Phản hồi thường dùng |
| --- | --- | --- |
| Conversion | `"not-a-code"` không đúng mẫu | 400 / `INVALID_PRODUCT_CODE` |
| Input validation | `quantity=0` | 400 / `QUANTITY_MUST_BE_POSITIVE` |
| Authentication | Chưa xác thực | 401 hoặc login flow |
| Authorization | Đã xác thực nhưng thiếu quyền | 403 hoặc 404 theo policy |
| Lookup | Mã hợp lệ nhưng không tồn tại | 404 hoặc lỗi domain theo contract |
| Business rule | Product inactive/hết hàng | 409 hoặc lỗi nghiệp vụ theo contract |

Mã HTTP cụ thể phụ thuộc API và chính sách information disclosure. Điểm cốt lõi là không biến “không tìm thấy product” thành `typeMismatch`: đó không phải lỗi chuyển kiểu.

### 11.1. Form binding

Khi converter ném exception do chuỗi sai cú pháp, Spring binder có thể ghi `FieldError`, thường với code chung `typeMismatch`. UI có thể hiển thị “Mã sản phẩm phải có dạng AB-123”.

Nếu converter chạy thành công nhưng repository không tìm thấy record, controller/service xử lý lookup failure riêng. Không giả vờ đó là `ConversionFailedException` chỉ để dùng cùng một message.

### 11.2. Không trả rejected value hoặc exception thô

`BindingResult` có thể lưu `rejectedValue` gốc. Với field nhạy cảm, không log hoặc serialize toàn bộ `FieldError`/`BindingResult` nếu chưa lọc. Tạo error DTO chỉ gồm field/code/message cần thiết và che dữ liệu nhạy cảm.

## 12. Anti-patterns và cách sửa

### A. Converter gọi repository

```java
@Override
public Product convert(String source) {
    return productRepository.findByCode(source)
            .orElseThrow(ProductNotFoundException::new);
}
```

**Vấn đề:** cú pháp và sự tồn tại bị trộn; conversion phụ thuộc DB; binder tạo query ẩn.  
**Sửa:** convert sang `ProductCode`, sau đó gọi repository trong application service.

### B. Converter đọc security context

```java
@Override
public ProductCode convert(String source) {
    User current = securityContextService.currentUser();
    authorizationService.checkCanUse(current, source);
    return new ProductCode(source);
}
```

**Vấn đề:** kết quả conversion phụ thuộc user và khó chạy ngoài HTTP.  
**Sửa:** conversion độc lập; authorization ở use case/service.

### C. Converter ghi dữ liệu

```java
@Override
public OrderId convert(String source) {
    Order order = repository.findByCode(source).orElseThrow();
    order.setViewedAt(Instant.now());
    repository.save(order);
    return order.getId();
}
```

**Vấn đề:** một thao tác binding/conversion bất ngờ có side effect; render/retry có thể lặp mutation.  
**Sửa:** converter chỉ tạo ID/value object; service command mới thực hiện hành động ghi.

### D. Converter làm mọi validation

Nếu `convert` vừa parse, query DB, kiểm tra stock, quyền, ghi audit, thì lỗi không có ranh giới và test khó cô lập. Tách parser, Bean Validation, authorization policy và domain/service rule.

### E. Coi “convert được” là “được sử dụng”

```java
ProductCode code = conversionService.convert(input, ProductCode.class);
// Chưa đủ điều kiện để tạo order.
orderRepository.create(code);
```

**Vấn đề:** bỏ qua tồn tại, quyền và business state.  
**Sửa:** use case/service phải kiểm tra tất cả điều kiện cần trước mutation.

## 13. Lookup, cache và reference data

Một số ứng dụng có danh mục code nhỏ, ổn định. Có thể nạp dictionary bất biến vào service/cache riêng. Cần phân biệt:

- **Conversion mapping:** alias tĩnh, quy tắc chuẩn hóa, bảng mã cố định. Đây có thể là cấu hình conversion nếu không phụ thuộc user/request và không mang trạng thái nghiệp vụ.
- **Reference data lookup:** mã cần đối chiếu danh mục có thẩm quyền. Đây vẫn là lookup dù có cache.
- **Authorization cache:** cache theo principal/resource/permission với expiry và invalidation đúng; không phải conversion cache.
- **Business availability:** tồn kho/giá/trạng thái thay đổi; cache cần freshness/consistency policy.

Cache chỉ là chiến lược hiệu năng. Nó không thay đổi loại trách nhiệm. Nếu cached lookup hết hạn hoặc phụ thuộc tenant/user, vẫn phải xử lý nó ở service/persistence boundary.

## 14. Test từng tầng độc lập

Một bộ test tốt không chỉ assert end-to-end “đặt hàng thành công”.

### 14.1. Unit test converter

| Input | Kỳ vọng |
| --- | --- |
| `"ab-012"` | `ProductCode("AB-012")` |
| `" AB-012 "` | `ProductCode("AB-012")` |
| `"ZZ-999"` | Conversion thành công dù repository không có code |
| `"ABC-12"` | Lỗi cú pháp |
| `""` | Lỗi required theo ví dụ |
| `null` | Lỗi required theo ví dụ |

Test quan trọng: `ZZ-999` phải parse thành công dù repository không chứa mã đó. Điều này chứng minh converter không tra database.

### 14.2. Unit test authorization

Dùng cùng product, rồi thay principal/quyền. User có permission được chấp thuận, user thiếu permission bị từ chối. Không cần tạo converter khác cho mỗi user.

### 14.3. Test repository/service

- Mã hợp lệ nhưng không tìm thấy product.
- Product tồn tại nhưng inactive.
- Product active nhưng quantity vượt tồn kho.
- Product thuộc tenant khác.
- Caller không có quyền.
- Tồn kho thay đổi giữa lookup và ghi order (cần transaction/locking phù hợp).

### 14.4. Test endpoint

Kiểm tra status và error body cho conversion failure, validation failure, authentication, authorization, not found và business conflict. Không assert tất cả đều là `typeMismatch`.

## 15. Checklist review code

Khi review class implements `Converter<S,T>`, hãy hỏi:

1. `convert` chỉ phụ thuộc source và cấu hình bất biến không?
2. Có repository, DAO, HTTP client hoặc network call không?
3. Có đọc `SecurityContextHolder` hoặc principal không?
4. Có ghi DB, cập nhật audit, gửi event hoặc side effect không?
5. Cùng source convert nhiều lần có kết quả ổn định không?
6. Chạy trong batch/job không có web request có hoạt động không?
7. Exception là lỗi biểu diễn/kiểu hay đang che lỗi lookup/permission?
8. Có test chứng minh code đúng cú pháp nhưng không tồn tại vẫn convert thành công?
9. Authorization được gọi tại use case/điểm hành động không?
10. Data access có ràng buộc tenant/owner và transaction thích hợp không?

Converter có dependency persistence/security chưa chắc là lỗi compile hay framework. Vấn đề là trách nhiệm: nếu method convert cần thông tin đó để quyết định có cho phép hành động hay không, logic có thể đang ở sai tầng.

## 16. Tự kiểm tra kiến thức

**1. `"AB-012"` đúng cú pháp nhưng không có record. Converter có nên ném “not found” không?**  
Không. Nó nên tạo `ProductCode`; repository/application service mới phát hiện record không tồn tại.

**2. User A có quyền, user B không quyền. Cùng chuỗi input có nên convert khác nhau?**  
Không. Conversion không phụ thuộc principal. Authorization đưa ra kết quả khác nhau.

**3. Có thể ném `IllegalArgumentException` khi chuỗi sai format trong converter không?**  
Có. Đây là conversion failure vì không thể tạo target value hợp lệ theo contract.

**4. `@Min(1)` có bảo đảm sản phẩm còn đủ hàng không?**  
Không. Nó kiểm tra số lượng đầu vào; availability cần dữ liệu và rule tồn kho.

**5. Converter gọi database để xác minh ID tồn tại gây vấn đề gì?**  
Conversion phụ thuộc persistent state, query ẩn trong binding, lỗi not-found bị trộn với type mismatch và khó tái sử dụng.

**6. Dùng Spring Security method authorization ở đâu?**  
Tại application service/entry point thực hiện use case; có thể kiểm tra thêm policy trên resource đã xác định.

**7. Cache lookup có biến lookup thành conversion không?**  
Không. Nó vẫn là lookup/reference data; cache chỉ là chiến lược hiệu năng.

**8. Khi nào dùng `Formatter<T>` thay `Converter<S,T>`?**  
Khi cần parse/print theo `Locale` cho UI. Formatter vẫn không kiểm tra quyền hay truy vấn business data.

**9. Product không tồn tại có nên trả `typeMismatch`?**  
Không. `typeMismatch` là lỗi binding/conversion; not-found cần error code/domain exception riêng.

**10. Có thể chỉ kiểm tra quyền ở frontend không?**  
Không. Frontend hỗ trợ UX; server phải thực hiện authorization theo principal và resource thực tế.

**Ghi nhớ:** converter trả lời **“giá trị này chuyển thành kiểu đích được không?”**; authorization trả lời **“người này được làm việc đó không?”**; repository/service trả lời **“dữ liệu có tồn tại và trạng thái có thỏa quy tắc nghiệp vụ không?”**. Giữ ba câu hỏi riêng giúp conversion dễ test, lỗi chính xác và quyền được kiểm tra tại nơi thực hiện hành động.

## Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — Core Conversion Service](https://docs.spring.io/spring-framework/reference/6.2/core/validation/convert.html)
- [Spring Framework 6.2 — Converter API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/convert/converter/Converter.html)
- [Spring Framework 6.2 — ConversionService API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/convert/ConversionService.html)
- [Spring Framework 6.2 — Data Binding](https://docs.spring.io/spring-framework/reference/6.2/core/validation/data-binding.html)
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html)

# Dữ liệu và hợp đồng giữa các tầng

## Quyết định khi nào cần kiểu dữ liệu riêng cho từng tầng và khi nào dùng chung

Trong module `SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED` — **Học tổ chức phần mềm theo kiến trúc phân tầng** — dữ liệu đi qua nhiều ranh giới: từ HTTP request vào ứng dụng, qua mô hình nghiệp vụ, tới cấu trúc lưu trữ; sau đó kết quả quay lại client. Mỗi tầng có mục đích và cách thay đổi riêng, vì vậy kiểu dữ liệu phù hợp ở tầng này chưa chắc phù hợp ở tầng khác.

Quyết định dùng kiểu riêng hay dùng chung là quyết định về **hợp đồng và mức độ phụ thuộc**. Tạo kiểu riêng giúp mỗi tầng bảo vệ cách biểu diễn và vòng đời của mình, nhưng cũng phát sinh mapping và mã chuyển đổi. Dùng chung giúp giảm chuyển đổi, nhưng có thể buộc nhiều tầng thay đổi cùng nhau và làm lộ chi tiết của một tầng sang tầng khác.

Bài học này dùng luồng tạo sản phẩm trong Java/Spring để đưa ra tiêu chí chọn lựa. Không có quy tắc rằng mọi tầng luôn phải có DTO riêng, cũng không có quy tắc rằng một class nên được dùng xuyên suốt toàn hệ thống. Hãy chọn dựa trên ý nghĩa của dữ liệu, ranh giới cần bảo vệ và chi phí thay đổi thực tế.

## 1. Một dữ liệu có thể có nhiều cách biểu diễn

Giả sử client gửi yêu cầu tạo sản phẩm. Ở các ranh giới khác nhau, hệ thống có thể cần những kiểu sau:

| Kiểu dữ liệu | Tầng thường sở hữu | Mục đích |
| --- | --- | --- |
| HTTP request/response DTO | Presentation | Biểu diễn hợp đồng giao tiếp với client, định dạng JSON và phiên bản API |
| Command/query/result model | Application | Biểu diễn yêu cầu và kết quả của một ca sử dụng |
| Entity, value object, domain service | Domain | Bảo vệ khái niệm và quy tắc nghiệp vụ |
| Persistence entity/row | Data access | Biểu diễn schema, quan hệ và cách ORM hoặc SQL lưu dữ liệu |

Các kiểu này có thể chứa một số trường giống nhau nhưng không có cùng ý nghĩa. Ví dụ, `price` trong request là dữ liệu client gửi lên; `Money` trong domain là giá trị tiền đã được kiểm tra và mang quy tắc về số tiền/đơn vị tiền; `price_amount` trong bảng là cột lưu trữ. Tên hoặc giá trị tương tự không làm chúng trở thành cùng một hợp đồng.

Một kiểu dữ liệu nên được xem là hợp đồng khi có bên khác dựa vào cấu trúc, ý nghĩa và quy tắc của nó. Khi dùng chung một class, các bên cùng phụ thuộc vào hợp đồng đó và có thể bị ảnh hưởng khi class thay đổi.

## 2. Khi nào nên dùng kiểu riêng cho từng tầng?

Tạo kiểu riêng khi các tầng có lý do thay đổi, ngữ nghĩa hoặc ràng buộc khác nhau. Một số dấu hiệu quan trọng:

### Hợp đồng bên ngoài cần ổn định độc lập

API công khai có thể cần giữ tên trường, cấu trúc lồng nhau và quy tắc tương thích trong khi mô hình miền hoặc schema cơ sở dữ liệu thay đổi. `CreateProductRequest` và `ProductJpaEntity` không nên trở thành một class chỉ vì cả hai đều có `name` và `price`.

### Mỗi tầng cần dữ liệu khác nhau

Client chỉ cần mã sản phẩm, tên và giá hiển thị; ca sử dụng có thể cần thêm người yêu cầu, nguồn thao tác hoặc thông tin kiểm soát; domain model có thể cần trạng thái, chính sách và các value object; persistence entity có thể cần khóa ngoại, cột audit và version để optimistic locking.

### Quy tắc xác thực khác nhau

Presentation kiểm tra cấu trúc và định dạng đầu vào, ví dụ trường tên không được bỏ trống hoặc chuỗi tiền có thể chuyển thành số. Domain kiểm tra bất biến nghiệp vụ, ví dụ giá không âm, đơn vị tiền hợp lệ hoặc sản phẩm không được kích hoạt khi thiếu thông tin bắt buộc. Persistence layer thực thi constraint của schema. Các kiểm tra có thể bổ trợ nhau, nhưng không nên coi validation của request là cách duy nhất bảo vệ domain.

### Cần tránh phụ thuộc framework hoặc công nghệ

Nếu domain model mang annotation Jackson, JPA hoặc cấu trúc của một thư viện web, thay đổi framework có thể lan vào phần nghiệp vụ. Một persistence entity thường cần constructor, quan hệ ORM, annotation và cách quản lý trạng thái riêng; domain model có thể cần API bất biến và phương thức bảo vệ invariant.

### Có yêu cầu bảo mật hoặc giới hạn dữ liệu

Không nên trả nguyên đối tượng nội bộ cho client nếu nó chứa dữ liệu riêng tư, trường quản trị hoặc thông tin kỹ thuật. Response DTO cho phép chỉ công khai các trường được phép và tránh vô tình lộ thuộc tính mới được thêm vào model nội bộ.

### Cần tiến hóa hoặc phiên bản hóa độc lập

API có thể duy trì `displayName` trong khi domain dùng `name`; schema có thể lưu `product_name`. Mỗi bên có lịch sử và nhịp thay đổi riêng. Kiểu riêng tạo nơi chuyển đổi rõ ràng để một thay đổi không buộc mọi tầng đổi theo cùng lúc.

## 3. Khi nào có thể dùng chung kiểu dữ liệu?

Dùng chung có thể hợp lý khi các bên thực sự chia sẻ cùng ngữ nghĩa, cùng vòng đời và cùng kỳ vọng thay đổi. Ví dụ:

- Một value object bất biến như `Money`, `EmailAddress` hoặc `ProductId` được dùng giữa application và domain trong cùng một ranh giới nội bộ.
- Một kiểu kết quả nhỏ, ổn định, không chứa chi tiết framework và có cùng ý nghĩa với mọi bên sử dụng.
- Một ứng dụng CRUD đơn giản có domain model và persistence entity gần như trùng nhau, không có nhu cầu thay đổi độc lập hoặc API phức tạp.
- Một hợp đồng sự kiện nội bộ được các bên cùng sở hữu và quản lý phiên bản theo thỏa thuận rõ ràng.

Trước khi dùng chung, hãy tự hỏi:

1. Các tầng có thật sự hiểu trường dữ liệu theo cùng một nghĩa không?
2. Các bên có thể chấp nhận cùng nhịp thay đổi và cùng quy tắc tương thích không?
3. Kiểu này có độc lập với framework, schema hoặc giao thức của một tầng không?
4. Chia sẻ kiểu có làm lộ trường nhạy cảm hoặc chi tiết nội bộ không?
5. Chi phí mapping nếu tách có lớn hơn lợi ích độc lập mà ta nhận được không?

Nếu các câu trả lời cho thấy hợp đồng ổn định và ngữ nghĩa đồng nhất, dùng chung có thể giảm mã lặp mà không tạo coupling đáng kể. Nếu chỉ giống tên trường hoặc cấu trúc hiện tại, đó chưa phải lý do đủ mạnh để dùng chung.

## 4. Ví dụ: luồng tạo sản phẩm với kiểu riêng ở các ranh giới

Một API tạo sản phẩm có thể nhận tên, giá và đơn vị tiền. Presentation dùng request DTO để mô tả giao thức HTTP:

```java
public record CreateProductRequest(
    @NotBlank String name,
    @NotNull @PositiveOrZero BigDecimal amount,
    @NotBlank String currency
) {}
```

Controller chuyển dữ liệu HTTP thành command của ứng dụng. Command phản ánh thông tin cần để thực hiện use case, không mang annotation hoặc cấu trúc JSON:

```java
public record CreateProductCommand(
    String name,
    BigDecimal amount,
    String currency
) {}
```

```java
@RestController
class ProductController {
    private final CreateProductService createProduct;

    ProductController(CreateProductService createProduct) {
        this.createProduct = createProduct;
    }

    @PostMapping("/products")
    ResponseEntity<CreateProductResponse> create(
            @Valid @RequestBody CreateProductRequest request) {
        var command = new CreateProductCommand(
            request.name(), request.amount(), request.currency());
        var result = createProduct.handle(command);
        var response = new CreateProductResponse(
            result.id().value().toString(), result.name(),
            result.amount(), result.currency());
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }
}
```

Application service điều phối use case và tạo mô hình miền; hợp đồng lưu trữ mà application sử dụng có thể được khai báo như sau:

```java
public interface ProductRepository {
    void save(Product product);
}
```

Service tạo mô hình miền và gọi hợp đồng đó:

```java
public record CreateProductResult(
    ProductId id,
    String name,
    BigDecimal amount,
    String currency
) {}

@Service
class CreateProductService {
    private final ProductRepository products;

    CreateProductService(ProductRepository products) {
        this.products = products;
    }

    @Transactional
    CreateProductResult handle(CreateProductCommand command) {
        var product = Product.create(
            command.name(),
            Money.of(command.amount(), command.currency()));
        products.save(product);
        return new CreateProductResult(
            product.id(), product.name(),
            product.price().amount(), product.price().currency());
    }
}
```

Adapter dữ liệu chuyển domain model sang persistence entity. `ProductRepository` là hợp đồng mà application sử dụng; `JpaProductRepository` triển khai hợp đồng và làm việc với Spring Data JPA:

```java
@Entity
@Table(name = "products")
class ProductJpaEntity {
    @Id
    private UUID id;
    private String name;
    private BigDecimal amount;
    private String currency;

    protected ProductJpaEntity() { }

    static ProductJpaEntity fromDomain(Product product) {
        var row = new ProductJpaEntity();
        row.id = product.id().value();
        row.name = product.name();
        row.amount = product.price().amount();
        row.currency = product.price().currency();
        return row;
    }
}
```

`CreateProductResponse` là kiểu response dành cho client:

```java
public record CreateProductResponse(
    String id,
    String name,
    BigDecimal amount,
    String currency
) {}
```

Các đoạn mã là ví dụ về cấu trúc và mapping, đã lược bỏ import, constructor, repository implementation và chi tiết domain model để tập trung vào hợp đồng. Trong ứng dụng thực tế, cần định nghĩa rõ cách tạo `ProductId`, quy tắc của `Money`, cách sinh định danh và xử lý lỗi. `@PositiveOrZero` ở request chỉ kiểm tra đầu vào HTTP; `Money.of` hoặc `Product.create` vẫn phải bảo vệ invariant để các caller khác không thể tạo dữ liệu sai.

Luồng chuyển đổi có thể tóm tắt:

```text
HTTP JSON
   |
   v
CreateProductRequest       (Presentation)
   | mapping
   v
CreateProductCommand       (Application)
   | use case / factory
   v
Product + Money            (Domain)
   | repository port
   v
ProductJpaEntity           (Data Access)
   |
   v
Database

Kết quả đi ngược qua CreateProductResult -> CreateProductResponse -> HTTP JSON
```

Mỗi kiểu có thể chỉ chứa một phần trường giống nhau, nhưng nó bảo vệ một hợp đồng riêng. Nếu tên trường HTTP đổi từ `amount` sang `price`, domain và schema không cần đổi theo; nếu schema đổi cách lưu tiền, response API vẫn có thể giữ nguyên.

## 5. Đặt mapping ở đâu?

Mapping nên nằm tại ranh giới nơi hai cách biểu diễn gặp nhau, và bên sở hữu ranh giới đó chịu trách nhiệm chuyển đổi:

| Chuyển đổi | Vị trí thường phù hợp | Lý do |
| --- | --- | --- |
| HTTP request DTO -> application command | Controller hoặc mapper thuộc presentation | Gắn với giao thức và cấu trúc API |
| Application command -> domain object | Application service hoặc factory/domain constructor | Application điều phối; domain bảo vệ invariant khi tạo object |
| Domain object <-> persistence entity | Repository/adapter dữ liệu | Che giấu schema, ORM và cách lưu trữ |
| Application result -> HTTP response DTO | Controller hoặc mapper thuộc presentation | Chọn dữ liệu và định dạng công khai cho client |

Không cần tạo một mapper class riêng cho mọi cặp kiểu. Mapping vài trường đơn giản có thể viết ngay tại ranh giới để dễ đọc. Khi mapping phức tạp, lặp lại hoặc có quy tắc riêng, một mapper chuyên biệt có thể làm trách nhiệm rõ hơn. Dù dùng MapStruct hay thư viện khác, cần giữ quyền sở hữu mapping rõ ràng và kiểm thử những chuyển đổi quan trọng.

## 6. Rủi ro khi dùng chung quá mức

### Một class trở thành hợp đồng của quá nhiều tầng

Nếu `Product` đồng thời là request DTO, domain model, JPA entity và response JSON, thay đổi một trường có thể tác động tới API, nghiệp vụ, schema và serialization. Annotation của Jackson hoặc JPA cũng có thể làm mô hình miền phụ thuộc framework.

### Rò rỉ dữ liệu và quyền truy cập

Khi trả trực tiếp domain object hoặc persistence entity, một trường nội bộ mới thêm vào có thể vô tình xuất hiện trong JSON. DTO phản hồi cho phép công khai có chủ đích các trường được phép.

### Thay đổi một tầng làm vỡ tầng khác

Schema có thể cần chuẩn hóa hoặc đổi quan hệ mà API không cần thay đổi. Nếu các tầng dùng cùng entity, refactor lưu trữ có thể buộc sửa controller hoặc client.

### Kiểu dữ liệu dùng chung trở thành nơi gom mọi thứ

Một module `common` chứa DTO, entity, request, response, helper và kiểu framework của mọi tầng dễ trở thành phụ thuộc chung rộng. Chỉ nên chia sẻ những kiểu có ý nghĩa ổn định và được sở hữu rõ ràng; không gom class vào một nơi chỉ vì muốn tránh mapping.

## 7. Rủi ro khi tách kiểu quá mức

Tạo nhiều kiểu giống hệt nhau cũng có chi phí:

- Mã mapping dài và dễ quên cập nhật khi thêm trường.
- Các kiểu trùng cấu trúc nhưng không có khác biệt ngữ nghĩa làm người đọc phải điều hướng nhiều file.
- Chuyển đổi qua nhiều lớp DTO có thể tăng cấp độ phức tạp mà không tạo ra ranh giới thực.
- Nếu mỗi tầng định nghĩa một kiểu cho cùng hợp đồng nhưng không có lý do tiến hóa độc lập, thay đổi có thể phải cập nhật nhiều nơi thủ công.

Vì vậy, đừng tạo kiểu mới chỉ để tên package trông đồng đều. Hãy tách khi kiểu mới biểu diễn hợp đồng, ngữ nghĩa, vòng đời hoặc lý do thay đổi khác. Nếu hai bên cùng sở hữu một khái niệm ổn định và không kéo theo phụ thuộc không mong muốn, dùng chung có thể là lựa chọn đơn giản hơn.

## 8. Cách ra quyết định trong dự án

Khi thêm một kiểu dữ liệu hoặc cân nhắc dùng lại class có sẵn, hãy thực hiện lần lượt:

1. Xác định bên gửi và bên nhận dữ liệu; ghi rõ ranh giới nào đang được nối.
2. Mô tả ý nghĩa của từng trường trong ngữ cảnh của mỗi bên, không chỉ so sánh tên và kiểu Java.
3. Kiểm tra khác biệt về validation, bảo mật, serialization, persistence và vòng đời.
4. Ước lượng khả năng các bên cần thay đổi độc lập trong tương lai gần.
5. Nếu tách, đặt mapping ở ranh giới và kiểm thử các chuyển đổi quan trọng.
6. Nếu dùng chung, xác định chủ sở hữu hợp đồng, phạm vi sử dụng và quy tắc tương thích.

| Tình huống | Lựa chọn thường hợp lý | Điều cần lưu ý |
| --- | --- | --- |
| API công khai và domain model có vòng đời khác nhau | Dùng request/response DTO riêng | Giữ API ổn định, không lộ trường nội bộ |
| Domain model và JPA entity có mapping, annotation hoặc schema thay đổi riêng | Tách persistence entity | Có chi phí mapping và kiểm thử mapping |
| Application và domain dùng chung một value object bất biến có cùng ngữ nghĩa | Có thể dùng chung | Không để value object kéo theo framework hoặc phụ thuộc ngược |
| Ứng dụng CRUD nhỏ, model đơn giản và ít khả năng tiến hóa độc lập | Có thể dùng chung model với persistence | Chấp nhận rõ sự gắn kết và kiểm soát dữ liệu API |
| Hai DTO chỉ trùng vài trường nhưng có mục đích và quy tắc khác nhau | Giữ kiểu riêng | Trùng cấu trúc không đồng nghĩa trùng hợp đồng |

## 9. Kiểm thử hợp đồng và mapping

Khi có kiểu riêng, kiểm thử cần tập trung vào những gì có thể sai ở ranh giới:

- Kiểm thử controller xác nhận request DTO nhận đúng định dạng, validation đầu vào và response chỉ chứa trường công khai.
- Kiểm thử application service xác nhận command tạo ra hành vi nghiệp vụ và result có dữ liệu cần thiết.
- Kiểm thử mapper xác nhận tiền, đơn vị tiền, định danh, trạng thái và giá trị null được chuyển đúng.
- Kiểm thử tích hợp repository xác nhận persistence entity được lưu và khôi phục đúng domain model.
- Kiểm thử tương thích API hoặc contract test xác nhận thay đổi DTO không phá vỡ client theo cam kết phiên bản.

Không cần kiểm thử mọi getter/setter hoặc mọi phép gán tầm thường. Ưu tiên những chuyển đổi có quy tắc, trường dễ nhầm, dữ liệu nhạy cảm và hợp đồng được nhiều bên sử dụng.

## Tự kiểm tra

1. Hai class có cùng trường `name` và `price` có đủ lý do để dùng chung không? Cần xem xét thêm điều gì?
2. Vì sao HTTP request DTO và persistence entity thường nên là hai kiểu riêng?
3. Một value object bất biến như `Money` có thể được dùng chung giữa application và domain trong điều kiện nào?
4. Mapping từ domain model sang JPA entity nên nằm ở đâu và vì sao?
5. Khi nào chi phí tạo DTO riêng và mapping lớn hơn lợi ích tách biệt mà nó đem lại?


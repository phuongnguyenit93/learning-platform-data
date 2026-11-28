# Thuộc tính chỉ đọc bằng @ReadOnlyProperty

Trong mô hình node của Spring Data Neo4j, có những thuộc tính ứng dụng cần đọc từ Neo4j nhưng không được ghi ngược lại khi lưu entity. Ví dụ, một mã đồng bộ từ hệ thống danh mục bên ngoài có thể được cập nhật bởi tiến trình tích hợp riêng. Service vẫn cần đọc mã đó để hiển thị hoặc xử lý nghiệp vụ, nhưng thao tác lưu tên sản phẩm không nên ghi đè giá trị do hệ thống khác quản lý.

Spring Data cung cấp annotation **`@ReadOnlyProperty`** cho trường hợp này. Annotation cho phép Spring Data Neo4j ánh xạ thuộc tính từ dữ liệu đọc, đồng thời bỏ qua thuộc tính đó trong các thao tác ghi entity do mapping thực hiện. Bài học này giải thích cách dùng annotation, phạm vi tác dụng và cách phân biệt nó với thuộc tính tạm hoặc dữ liệu tính toán.

## 1. @ReadOnlyProperty là gì?

`@ReadOnlyProperty` là annotation thuộc Spring Data Commons, có tên đầy đủ:

```java
import org.springframework.data.annotation.ReadOnlyProperty;
```

Khi đặt trên một thuộc tính được ánh xạ của entity, annotation biểu thị rằng thuộc tính đó **được đọc từ datastore nhưng không được ghi bởi cơ chế mapping của Spring Data**.

Trong Spring Data Neo4j, điều này có nghĩa:

- Khi đọc node và ánh xạ thành entity, giá trị property trong Neo4j có thể được nạp vào thuộc tính Java.
- Khi lưu entity bằng repository hoặc cơ chế mapping tương ứng, Spring Data Neo4j bỏ qua thuộc tính được đánh dấu `@ReadOnlyProperty` trong phần ghi dữ liệu.
- Các thuộc tính khác của entity vẫn được ánh xạ và ghi theo quy tắc thông thường.

Annotation này phù hợp khi một thuộc tính thuộc quyền quản lý của nguồn dữ liệu hoặc tiến trình khác, nhưng ứng dụng hiện tại vẫn cần đọc giá trị đó.

Điều cần nhớ là `@ReadOnlyProperty` điều khiển hành vi ánh xạ của Spring Data. Nó không tạo property trong Neo4j, không tự tính giá trị và cũng không thiết lập quyền chỉ đọc ở cấp database.

## 2. Ví dụ: mã danh mục do hệ thống bên ngoài quản lý

Giả sử ứng dụng quản lý node `Product` với các thuộc tính:

```text
(Product {
    sku: "SKU-100",
    name: "Bàn phím cơ",
    externalCatalogCode: "CAT-KEYBOARD"
})
```

Ứng dụng Spring Data Neo4j được phép cập nhật `name`, còn `externalCatalogCode` được một tiến trình đồng bộ danh mục cập nhật. Entity có thể khai báo như sau:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.ReadOnlyProperty;
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Product")
public class Product {

    @Id
    @GeneratedValue
    private Long id;

    private String sku;

    private String name;

    @ReadOnlyProperty
    private String externalCatalogCode;

    public Product() {
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public void setSku(String sku) {
        this.sku = sku;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getExternalCatalogCode() {
        return externalCatalogCode;
    }
}
```

Trong ví dụ, `externalCatalogCode` có getter để service hoặc API đọc giá trị. Ta không cung cấp setter công khai nhằm thể hiện ý định không cho luồng cập nhật thông thường thay đổi trường này. Việc bỏ setter là lựa chọn thiết kế Java; chính annotation mới là metadata yêu cầu Spring Data bỏ qua thuộc tính khi ghi.

Repository có thể khai báo theo cách thông thường:

```java
public interface ProductRepository extends Neo4jRepository<Product, Long> {
    Optional<Product> findBySku(String sku);
}
```

Khi gọi `findBySku`, Spring Data Neo4j đọc node `Product` và ánh xạ `externalCatalogCode` nếu property này tồn tại trong node.

## 3. Giá trị được đọc nhưng không được ghi qua entity mapping

Giả sử node đã có dữ liệu:

```cypher
CREATE (p:Product {
    sku: 'SKU-100',
    name: 'Bàn phím cơ',
    externalCatalogCode: 'CAT-KEYBOARD'
})
```

Sau đó repository đọc node:

```java
Product product = productRepository.findBySku("SKU-100")
    .orElseThrow();

System.out.println(product.getExternalCatalogCode());
// CAT-KEYBOARD
```

Giá trị `CAT-KEYBOARD` được nạp vào entity mặc dù trường được đánh dấu `@ReadOnlyProperty`.

Khi service chỉ đổi tên sản phẩm rồi lưu:

```java
@Service
public class ProductService {

    private final ProductRepository productRepository;

    public ProductService(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    @Transactional
    public Product rename(String sku, String newName) {
        Product product = productRepository.findBySku(sku)
            .orElseThrow();

        product.setName(newName);
        return productRepository.save(product);
    }
}
```

Spring Data Neo4j ghi thay đổi của `name` theo mapping thông thường và bỏ qua `externalCatalogCode`. Giá trị mã danh mục đang có trong Neo4j được giữ nguyên bởi thao tác lưu entity này.

Nếu tạo một entity mới và gán giá trị cho trường read-only bằng constructor hoặc cơ chế nội bộ, thao tác `save` qua mapping cũng không dùng giá trị đó để ghi property. Vì vậy, không nên dựa vào việc gán trường Java để cập nhật một thuộc tính đã được đánh dấu `@ReadOnlyProperty`.

## 4. Nguồn nào cập nhật thuộc tính read-only?

`@ReadOnlyProperty` không tự tạo ra cơ chế cập nhật. Property phải được ghi vào Neo4j bởi một nguồn khác, ví dụ:

- Một tiến trình đồng bộ danh mục sản phẩm.
- Một tác vụ nhập dữ liệu từ hệ thống cũ.
- Một luồng Cypher chuyên trách cập nhật các trường được quản lý tập trung.
- Một ứng dụng khác có trách nhiệm sở hữu thuộc tính đó.

Ví dụ, tiến trình đồng bộ có thể cập nhật mã danh mục bằng Cypher:

```cypher
MATCH (p:Product {sku: $sku})
SET p.externalCatalogCode = $externalCode
```

Nếu thao tác này được thực hiện từ Spring Data Neo4j, có thể dùng `Neo4jClient`:

```java
neo4jClient.query("""
    MATCH (p:Product {sku: $sku})
    SET p.externalCatalogCode = $externalCode
    """)
    .bind(sku).to("sku")
    .bind(externalCode).to("externalCode")
    .run();
```

Đây là truy vấn Cypher được viết tường minh, có lệnh `SET` trực tiếp. `@ReadOnlyProperty` không phải bộ lọc bảo mật và không chặn một truy vấn Cypher tùy chỉnh như vậy. Nếu ứng dụng gọi `Neo4jClient` hoặc Driver và chủ động ghi property, truy vấn vẫn có thể cập nhật nó.

Do đó, nên tổ chức quyền sở hữu thuộc tính ở tầng kiến trúc: xác định thành phần nào được phép cập nhật, giới hạn API ghi, và cấu hình quyền database phù hợp. Annotation giúp ngăn thao tác ghi vô tình qua entity mapping, nhưng không thay thế phân quyền Neo4j.

## 5. Phân biệt @ReadOnlyProperty, @Transient và thuộc tính thông thường

Ba cách khai báo dưới đây có mục đích khác nhau:

| Cách khai báo | Đọc từ Neo4j qua mapping | Ghi vào Neo4j qua mapping | Mục đích |
|---|---|---|---|
| Thuộc tính thông thường | Có | Có | Dữ liệu entity được ứng dụng đọc và cập nhật |
| `@ReadOnlyProperty` | Có | Không | Dữ liệu cần đọc nhưng được quản lý bởi nguồn khác |
| `@Transient` | Không | Không | Trường chỉ tồn tại trong đối tượng Java, không thuộc mô hình lưu trữ |

Ví dụ:

```java
import org.springframework.data.annotation.Transient;

@Node("Product")
public class Product {
    @Id
    @GeneratedValue
    private Long id;

    private String name;

    @ReadOnlyProperty
    private String externalCatalogCode;

    @Transient
    private String displayLabel;
}
```

`externalCatalogCode` có thể được nạp từ property cùng tên trên node nhưng không được ghi bởi mapping. `displayLabel` không được ánh xạ với property Neo4j; ứng dụng có thể tính giá trị này từ các trường Java khác.

Không dùng `@Transient` nếu vẫn cần đọc một property đã được lưu trong Neo4j. Ngược lại, không dùng `@ReadOnlyProperty` cho một giá trị chỉ tồn tại trong bộ nhớ và không có property tương ứng trong database.

## 6. Khi nào nên dùng @ReadOnlyProperty?

Annotation phù hợp khi thuộc tính có ý nghĩa trong entity nhưng ứng dụng hiện tại không phải chủ sở hữu dữ liệu đó.

Một số trường hợp điển hình:

- **Mã đồng bộ từ hệ thống ngoài:** mã phân loại hoặc mã đối tác được hệ thống chủ quản cập nhật; ứng dụng chỉ cần tra cứu.
- **Metadata do tiến trình nhập dữ liệu quản lý:** ví dụ thời điểm hoặc mã lô nhập được ghi bởi pipeline import riêng.
- **Thuộc tính được duy trì bằng quy trình chuyên trách:** một job định kỳ cập nhật trạng thái hoặc metadata trên node; service thông thường chỉ đọc.
- **Dữ liệu tương thích ngược:** node có property cũ mà ứng dụng vẫn cần đọc, nhưng không muốn ghi lại trong mỗi lần lưu entity.

Trước khi dùng annotation, hãy xác định rõ:

1. Property có thực sự tồn tại trên node trong Neo4j không?
2. Nguồn nào tạo và cập nhật property đó?
3. Ứng dụng cần đọc giá trị ở những luồng nào?
4. Có thao tác nào đang dùng Cypher trực tiếp để ghi property không?
5. Khi nguồn dữ liệu thay đổi, ứng dụng cần phản ánh giá trị mới vào entity trong lần đọc tiếp theo hay cần cơ chế cache/invalidation riêng?

Nếu không xác định được nguồn sở hữu, thuộc tính có nguy cơ trở thành dữ liệu không ai chịu trách nhiệm cập nhật.

## 7. Khi nào không nên dùng @ReadOnlyProperty?

Không phải mọi trường ít thay đổi đều nên đánh dấu read-only. Nếu ứng dụng là nguồn có thẩm quyền và service cần cập nhật property, hãy dùng thuộc tính thông thường cùng quy tắc nghiệp vụ phù hợp.

Đặc biệt, không nên dùng `@ReadOnlyProperty` như cách thay thế cho:

- **Giá trị tính toán chỉ phục vụ một truy vấn:** dùng DTO hoặc projection để trả kết quả truy vấn.
- **Trường không cần lưu:** dùng `@Transient` hoặc tính giá trị trong Java.
- **Phân quyền ghi:** dùng tài khoản và role Neo4j phù hợp, kiểm soát service/API và giới hạn truy vấn có thể thực thi.
- **Auditing:** các annotation như `@CreatedDate` hoặc `@LastModifiedDate` thuộc cơ chế auditing của Spring Data và có quy trình ghi riêng; không đồng nghĩa với `@ReadOnlyProperty`.
- **Giá trị tự động sinh:** cần cấu hình cơ chế tạo hoặc cập nhật giá trị ở database hay ứng dụng. `@ReadOnlyProperty` chỉ điều khiển việc mapping ghi, không sinh giá trị.

## 8. Dùng projection cho dữ liệu tính toán khi đọc

Một tình huống dễ nhầm là số lượng quan hệ, tổng tồn kho hoặc điểm đánh giá. Nếu giá trị chỉ được tính trong lúc truy vấn và không được lưu thành property của node, `@ReadOnlyProperty` không tự ánh xạ kết quả tính toán đó vào entity.

Ví dụ, cần tính tổng số lượng tồn kho liên kết với sản phẩm:

```java
public interface ProductAvailability {
    String getSku();
    Long getAvailableQuantity();
}
```

Repository có thể dùng Cypher để trả về projection:

```java
public interface ProductRepository extends Neo4jRepository<Product, Long> {

    @Query("""
        MATCH (p:Product {sku: $sku})
        OPTIONAL MATCH (s:Stock)-[:FOR_PRODUCT]->(p)
        RETURN p.sku AS sku,
               coalesce(sum(s.quantity), 0) AS availableQuantity
        """)
    Optional<ProductAvailability> findAvailability(
        @Param("sku") String sku
    );
}
```

Ở đây, `availableQuantity` là kết quả tổng hợp được trả về cho projection, không nhất thiết là property đã lưu trên node `Product`. Đây là cách phù hợp khi giá trị phụ thuộc vào nhiều node hoặc relationship và cần được tính theo trạng thái dữ liệu tại thời điểm truy vấn.

Nếu muốn lưu sẵn tổng tồn kho trên node `Product`, cần một quy trình cập nhật property đó. Khi ứng dụng chỉ đọc property đã lưu và không được phép ghi nó qua repository, khi đó `@ReadOnlyProperty` có thể phù hợp.

## 9. Kiểm thử hành vi read-only

Nên có integration test với Neo4j thật hoặc môi trường Neo4j cô lập để xác minh cả chiều đọc lẫn chiều ghi. Một bài kiểm thử có thể theo các bước:

1. Tạo node `Product` với `sku`, `name` và `externalCatalogCode` bằng Cypher.
2. Đọc node qua `ProductRepository` và xác nhận `getExternalCatalogCode()` trả về giá trị đã lưu.
3. Thay đổi `name` trong entity và gọi `save`.
4. Đọc lại node bằng Cypher hoặc repository.
5. Xác nhận `name` đã đổi còn `externalCatalogCode` giữ nguyên.
6. Tạo entity mới với trường read-only được gán giá trị trong fixture, lưu entity và xác nhận mapping không ghi trường đó.

Ví dụ truy vấn xác minh sau khi lưu:

```cypher
MATCH (p:Product {sku: $sku})
RETURN p.name AS name,
       p.externalCatalogCode AS externalCatalogCode
```

Kết quả cần thể hiện tên mới và mã danh mục ban đầu. Nếu giá trị read-only bị mất hoặc bị thay đổi, hãy kiểm tra cách mapping entity, phiên bản Spring Data Neo4j đang dùng và những thao tác ghi khác trong cùng transaction.

Integration test cũng nên kiểm tra luồng cập nhật chuyên trách: Cypher có chủ đích vẫn có thể thay đổi property read-only. Điều này xác nhận ranh giới giữa hành vi mapping entity và khả năng ghi trực tiếp ở database.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Giá trị Java luôn `null` | Node không có property, tên property không khớp hoặc truy vấn không trả node đầy đủ | Kiểm tra dữ liệu bằng Cypher và metadata ánh xạ. |
| Gán giá trị trong Java nhưng lưu không cập nhật Neo4j | Thuộc tính được đánh dấu `@ReadOnlyProperty` | Cập nhật qua nguồn sở hữu property hoặc Cypher chuyên trách. |
| Nghĩ rằng annotation ngăn mọi thao tác ghi | Nhầm metadata mapping với quyền database | Kiểm soát Cypher trực tiếp, service và quyền Neo4j. |
| Dùng annotation cho giá trị tổng hợp không được lưu | Nhầm property trên node với cột tính toán của truy vấn | Dùng DTO/interface projection hoặc `Neo4jClient`. |
| Dùng `@Transient` nhưng mong muốn đọc property đã tồn tại | `@Transient` loại trường khỏi mapping | Chuyển sang `@ReadOnlyProperty` nếu trường cần đọc nhưng không ghi. |

## 11. Ghi nhớ

`@ReadOnlyProperty` cho phép Spring Data Neo4j đọc một property từ node và bỏ qua property đó khi ghi entity qua cơ chế mapping. Nó phù hợp với dữ liệu do một nguồn hoặc quy trình khác quản lý, trong khi ứng dụng vẫn cần sử dụng giá trị để đọc.

Annotation không tạo dữ liệu, không tự tính property, không ngăn Cypher tùy chỉnh ghi vào database và không thay thế phân quyền. Hãy phân biệt nó với `@Transient` và projection: `@Transient` loại trường khỏi mapping, còn projection biểu diễn kết quả đọc được tính hoặc chọn riêng cho truy vấn. Khi xác định đúng nguồn sở hữu thuộc tính và kiểm thử cả hành vi đọc lẫn ghi, mô hình node sẽ rõ ràng hơn và tránh việc service vô tình ghi đè dữ liệu do thành phần khác quản lý.

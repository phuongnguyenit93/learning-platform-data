# Khớp tất cả hoặc bất kỳ trường được chọn

## 1. Bài toán: nhiều tiêu chí tìm kiếm nhưng không muốn viết hàng chục query method

Một ứng dụng quản lý sản phẩm sử dụng **Spring Data MongoDB**. Màn hình tìm kiếm cho phép nhân viên nhập một số tiêu chí: danh mục, thương hiệu, tên sản phẩm và trạng thái hoạt động. Người dùng có thể muốn một trong hai hành vi:

- **Khớp tất cả (AND):** chỉ trả sản phẩm vừa thuộc danh mục `keyboard` **và** có thương hiệu `ACME`.
- **Khớp bất kỳ (OR):** trả sản phẩm thuộc danh mục `keyboard` **hoặc** có thương hiệu `ACME`; một sản phẩm chỉ cần thỏa một trong hai.

Nếu viết các phương thức repository chuyên biệt như `findByCategoryAndBrand`, `findByCategoryOrBrand`, `findByCategoryAndActive`, `findByBrandOrActive`, số lượng tổ hợp sẽ tăng nhanh khi có thêm các ô tìm kiếm. Một hướng giải quyết là dùng **Query by Example (QBE)**:

1. Tạo **probe** — một object domain chứa các giá trị muốn tìm.
2. Tạo **ExampleMatcher** — mô tả cách so sánh, các property được xét và cách kết hợp điều kiện.
3. Tạo **Example** từ probe và matcher.
4. Đưa Example cho repository hoặc chuyển nó thành `Criteria` để dùng với `MongoTemplate`.

Bài thuộc chương **Query by Example** của module **SPRING_DATA_MONGODB**, nơi ta thực hành kết nối, ánh xạ document và truy vấn MongoDB qua repository/`MongoTemplate`; đồng thời đánh giá index, aggregation, transaction, reactive access, kiểm thử và hiệu năng.

**Kết luận cần nhớ ngay:** `ExampleMatcher.matchingAll()` yêu cầu **mọi predicate được chọn** cùng đúng; `ExampleMatcher.matchingAny()` yêu cầu **ít nhất một predicate được chọn** đúng. Cả hai chỉ tác động lên những property thực sự được đưa vào Example, không tự hiểu “trường được chọn” từ một form hay từ tên biến Java.

## 2. Bốn khái niệm tạo nên Query by Example

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| **Probe** | Đối tượng mẫu với các property đã điền | `category="keyboard", brand="ACME"` |
| **ExampleMatcher** | AND/OR, ignore paths, xử lý string/null | `matchingAny().withIgnorePaths("id")` |
| **Example<T>** | Ghép probe và matcher thành một mô tả truy vấn | `Example.of(probe, matcher)` |
| **QueryByExampleExecutor** | Thực thi Example qua repository | `repository.findAll(example)` |
| **Criteria.byExample** | Kết hợp Example với truy vấn `MongoTemplate` | `Criteria.byExample(example)` |

`ExampleMatcher.matching()` thường tương đương với **matching all** mặc định. Khi cần OR rõ ràng, chọn `matchingAny()` chứ không thay bằng một lần gọi `withMatcher(...)` trên từng field. `withMatcher(...)` dùng để đặt **cách so sánh của một property**, không phải để chọn phép nối OR hay AND giữa các property.

QBE thuận tiện với điều kiện đơn giản xuất phát từ object domain. Nó **không phải ngôn ngữ truy vấn đầy đủ** của MongoDB, không thay thế mọi biểu thức `$and`/`$or` lồng nhau, truy vấn khoảng, `$elemMatch`, aggregation hay transaction.

## 3. Mô hình dữ liệu và tập sản phẩm minh họa

Giả sử collection `products` chứa những document với ID chuỗi, thông tin tenant, tên, danh mục, mã thương hiệu và trạng thái. Ta dùng tên Java khác tên BSON ở vài field để làm rõ mapping.

### 3.1. Entity Java

```java
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "products")
public record ProductDocument(
    @MongoId(FieldType.STRING)
    String id,

    @Field("tenant_id")
    String tenantId,

    String name,
    String category,

    @Field("brand_code")
    String brand,

    Boolean active,

    @Field("price_cents")
    Long priceCents
) {}
```

Đây là record Java 17+ cho ví dụ đọc/ghi đơn giản:

- `id` lưu vào BSON `_id` dạng string theo `@MongoId(FieldType.STRING)`.
- `tenantId` trong Java được lưu vào `tenant_id` trong MongoDB.
- `brand` trong Java được lưu thành `brand_code`.
- `priceCents` lưu vào `price_cents`; sử dụng đơn vị nhỏ nhất giúp số tiền nguyên, nhưng phải thống nhất đơn vị và loại tiền trong ứng dụng thật.
- `active` là **`Boolean` wrapper**, không phải primitive `boolean`. Giá trị `null` có nghĩa **không đưa trạng thái vào probe**; `false` vẫn là một giá trị tìm kiếm hợp lệ.

Nếu dùng primitive `boolean active`, object mới khởi tạo có `false` và QBE có thể đưa điều kiện `active=false` vào truy vấn dù người dùng không hề chọn trạng thái. Quy tắc này sẽ được phân tích ở mục 8.

### 3.2. Dữ liệu kiểm thử

| ID | Tenant | Category | Brand | Active | Ghi chú |
| --- | --- | --- | --- | --- | --- |
| `p-01` | `t-A` | `keyboard` | `ACME` | true | Khớp cả hai |
| `p-02` | `t-A` | `keyboard` | `ZEN` | true | Chỉ khớp category |
| `p-03` | `t-A` | `mouse` | `ACME` | true | Chỉ khớp brand |
| `p-04` | `t-A` | `mouse` | `ZEN` | false | Không khớp |
| `p-05` | `t-A` | `keyboard` | `ACME` | false | Khớp cả hai |
| `p-06` | `t-B` | `keyboard` | `ACME` | true | Cùng tiêu chí nhưng **khác tenant** |

Các ví dụ repository QBE bên dưới giả định dữ liệu được **ghi bằng Spring Data MongoDB** với mapping mặc định, nên document có thể mang type hint `_class`. Nếu tự chèn dữ liệu bằng `mongosh` mà không có `_class`, một **typed Example** có thể không khớp do ràng buộc loại Java; xem mục 12.

Ví dụ BSON minh họa cho sản phẩm đầu:

```javascript
{
  _id: "p-01",
  tenant_id: "t-A",
  name: "Bàn phím cơ A",
  category: "keyboard",
  brand_code: "ACME",
  active: true,
  price_cents: NumberLong("1850000")
  // Khi Spring Data lưu với type hints mặc định, có thể có _class.
}
```

Truy vấn BSON tương đương về ý nghĩa của hai chế độ:

```javascript
// AND: chỉ sản phẩm thỏa cả category và brand.
db.products.find({
  category: "keyboard",
  brand_code: "ACME"
});

// OR: sản phẩm thỏa ít nhất một tiêu chí.
db.products.find({
  $or: [
    { category: "keyboard" },
    { brand_code: "ACME" }
  ]
});
```

Đây là ví dụ để hiểu logic. Câu query thực tế từ **typed QBE** có thể thêm ràng buộc `_class`; hình dạng BSON không nhất thiết chính xác từng byte như các lệnh shell minh họa.

## 4. `matchingAll()`: tất cả property được chọn phải khớp

Giả sử người dùng nhập:

```text
Danh mục   = keyboard
Thương hiệu = ACME
Chế độ      = Tất cả điều kiện
```

Ta tạo probe có đúng hai property không null:

```java
import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;

ProductDocument probe = new ProductDocument(
    null,       // id
    null,       // tenantId: không được đưa vào QBE tùy chọn
    null,       // name
    "keyboard", // category
    "ACME",     // brand
    null,       // active
    null        // priceCents
);

ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withIgnorePaths(
        "id", "tenantId", "name", "active", "priceCents"
    );

Example<ProductDocument> example = Example.of(
    probe, matcher
);
```

Về logic, ngoài ràng buộc type có thể có, các predicate là:

```javascript
{
  category: "keyboard",
  brand_code: "ACME"
}
```

Kết quả theo dataset ở mục 3: `p-01`, `p-05` và `p-06`. Ba document đều thỏa **cả** hai field. `p-06` thuộc tenant khác vẫn được đưa ra nếu truy vấn này không có điều kiện tenant bắt buộc; đây là lỗi bảo mật nếu dùng trực tiếp cho API khách hàng.

### 4.1. Mặc định cũng là matching all

```java
ExampleMatcher matcherA = ExampleMatcher.matching();
ExampleMatcher matcherB = ExampleMatcher.matchingAll();
```

Cả hai nhằm diễn đạt “tất cả giá trị được đưa vào probe phải khớp” theo mặc định. Viết `matchingAll()` tường minh hữu ích khi service cho phép chuyển qua lại hai chế độ AND/OR.

**Không** suy rằng matcher kiểm tra cả mọi property của entity. Những property `null` mặc định được bỏ qua; property được đánh dấu `withIgnorePaths(...)` cũng bị bỏ qua, kể cả có giá trị.

## 5. `matchingAny()`: ít nhất một property được chọn phải khớp

Dùng **cùng probe** nhưng thay matcher:

```java
import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;

ExampleMatcher anyMatcher = ExampleMatcher.matchingAny()
    .withIgnorePaths(
        "id", "tenantId", "name", "active", "priceCents"
    );

Example<ProductDocument> anyExample = Example.of(
    probe, anyMatcher
);
```

Ý nghĩa tương đương:

```javascript
{
  $or: [
    { category: "keyboard" },
    { brand_code: "ACME" }
  ]
}
```

Kết quả theo dataset:

- `p-01`: khớp cả hai → được trả.
- `p-02`: khớp category → được trả.
- `p-03`: khớp brand → được trả.
- `p-04`: không khớp tiêu chí nào → không được trả.
- `p-05`: khớp cả hai → được trả.
- `p-06`: khớp cả hai nhưng tenant khác → **vẫn được trả nếu không khóa tenant ở ngoài OR**.

### 5.1. So sánh trực tiếp

| Probe | Chế độ | Predicate logic | Sản phẩm trong t-A khớp |
| --- | --- | --- | --- |
| category=keyboard, brand=ACME | `matchingAll` | category **AND** brand | `p-01`, `p-05` |
| category=keyboard, brand=ACME | `matchingAny` | category **OR** brand | `p-01`, `p-02`, `p-03`, `p-05` |
| Chỉ category=keyboard | Cả hai | category | `p-01`, `p-02`, `p-05` |
| Chỉ brand=ACME | Cả hai | brand | `p-01`, `p-03`, `p-05` |

Bảng giới hạn kết quả trong tenant `t-A` **nếu có điều kiện tenant riêng**. QBE đơn thuần không tự áp dụng tenant filter.

### 5.2. Một predicate thì ALL và ANY cho kết quả như nhau

Nếu probe chỉ có `category="keyboard"` và tất cả property khác null/ignored, cả AND lẫn OR trên **một** predicate đều giống nhau. Đây là tình huống kiểm thử quan trọng: đừng kết luận switch chế độ không hoạt động chỉ vì thử một trường.

### 5.3. ANY không có nghĩa tìm gần đúng hay xếp hạng

`matchingAny()` chỉ kết hợp bằng OR. Nó không:

- Tính điểm sản phẩm khớp hai field cao hơn sản phẩm khớp một field.
- Tự sắp xếp kết quả theo số tiêu chí thỏa.
- Tự áp dụng fuzzy search, full-text search hoặc semantic similarity.
- Tự phân trang, giới hạn số document hay bảo vệ kết quả khỏi trùng/lộ dữ liệu.

Nếu cần scoring, relevance ranking hoặc thứ tự ưu tiên dựa trên số predicate khớp, cân nhắc aggregation `$addFields`/`$project` và `$sort` hoặc công cụ tìm kiếm phù hợp.

## 6. Thực thi QBE qua `MongoRepository`

### 6.1. Repository

```java
import org.springframework.data.mongodb.repository.MongoRepository;

public interface ProductRepository
        extends MongoRepository<ProductDocument, String> {}
```

Trong các dòng Spring Data MongoDB phổ biến, `MongoRepository` cung cấp khả năng **Query by Example**, vì vậy ta có thể gọi:

```java
Iterable<ProductDocument> allMatches =
    productRepository.findAll(
        Example.of(probe, ExampleMatcher.matchingAll())
    );

Iterable<ProductDocument> anyMatches =
    productRepository.findAll(
        Example.of(probe, ExampleMatcher.matchingAny())
    );
```

Hai lời gọi trên dùng cùng probe với các giá trị null khác. Trong code production, vẫn nên dùng matcher định nghĩa rõ `withIgnorePaths(...)` và kiểm tra tenant. `findAll(example)` **không** áp dụng phân quyền hay giới hạn số kết quả theo mặc định.

Tùy dòng Spring Data, return type của `findAll(Example<S>)` có thể có kiểu cụ thể hơn như `List<S>`; gán vào `Iterable<ProductDocument>` là cách dùng đơn giản. Với repository không kế thừa API QBE sẵn có, dùng `QueryByExampleExecutor<T>` theo hợp đồng Spring Data Commons.

### 6.2. Đếm và kiểm tra tồn tại

```java
long count = productRepository.count(example);
boolean exists = productRepository.exists(example);
```

`count` và `exists` xét cùng tập predicate của Example, nhưng không biến việc đọc rồi ghi thành một transaction. Nếu kết quả được dùng để quyết định tạo bản ghi duy nhất, vẫn cần unique index và logic ghi nguyên tử/transaction phù hợp; không dùng `exists(example)` như rào chắn concurrency duy nhất.

### 6.3. Phân trang và sắp xếp

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

Page<ProductDocument> page = productRepository.findAll(
    example,
    PageRequest.of(
        0,
        20,
        Sort.by(
            Sort.Order.asc("name"),
            Sort.Order.asc("id")
        )
    )
);
```

Với tập dữ liệu lớn, nên phân trang và sort có thứ tự ổn định (ID giúp phân biệt khi tên bằng nhau). `Page` có thể cần truy vấn đếm thêm; khi chỉ cần “Xem thêm”, `Slice`/scrolling hoặc một API riêng có thể phù hợp hơn tùy phiên bản.

### 6.4. Không sử dụng QBE như một endpoint công khai không giới hạn

Nếu web client được phép gửi một probe rỗng, `findAll(example)` có thể trở thành một query rất rộng (hoặc chỉ còn điều kiện type). Cần:

- Bắt buộc ít nhất một tiêu chí lọc hợp lệ.
- Luôn áp đặt điều kiện tenant/authorization ngoài nhóm OR tùy chọn.
- Giới hạn kích thước trang và chỉ trả những field được phép.
- Kiểm soát string matcher vì `CONTAINING` thường tạo regex có thể khó tận dụng index.
- Không cho client truyền một object entity có mọi property tùy ý làm probe.

## 7. Thực thi qua `MongoTemplate` để kết hợp điều kiện khác

Spring Data MongoDB hỗ trợ chuyển một `Example` thành `Criteria`:

```java
import java.util.List;

import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public List<ProductDocument> findByExample(
    MongoTemplate template,
    Example<ProductDocument> example
) {
    Query query = Query.query(
        Criteria.byExample(example)
    );
    query.limit(30);

    return template.find(
        query,
        ProductDocument.class
    );
}
```

Cách tương đương khác trong các phiên bản hỗ trợ là `new Criteria().alike(example)`. Nếu cần điều kiện bổ sung như `tenantId`, số tiền theo khoảng, hoặc trạng thái nghiệp vụ bắt buộc, `MongoTemplate` giúp xây cấu trúc `Criteria` rõ ràng hơn.

**Chú ý:** QBE do `Criteria.byExample(...)` tạo vẫn giữ lựa chọn `matchingAll`/`matchingAny` từ Example và có thể thêm ràng buộc type. `MongoTemplate` không tự động chuyển `matchingAny` thành `matchingAll`.

## 8. “Trường được chọn” được quyết định ra sao?

QBE không biết người dùng đã chọn checkbox nào trên giao diện. Nó suy ra predicate từ **giá trị của các property** và các quy tắc `ExampleMatcher`.

### 8.1. Mặc định: `null` bị bỏ qua

Giả sử:

```java
ProductDocument probe = new ProductDocument(
    null, null, null, "keyboard", null, null, null
);
```

Dù entity có bảy property, query chủ yếu chỉ dùng `category="keyboard"` vì những property khác null (cộng với khả năng có type restriction). QBE mặc định không hiểu `null` thành “tìm document có field null”.

### 8.2. Primitive được đưa vào probe dù người dùng không nhập

Nếu model dùng:

```java
public class ProductProbeWithPrimitive {
    public String category;
    public boolean active; // mặc định false
    public int stock;       // mặc định 0
}
```

và chỉ set `category="keyboard"`, QBE có thể vẫn thêm predicate `active=false` và `stock=0`. Với `matchingAll`, kết quả bị thu hẹp sai; với `matchingAny`, nó có thể mở rộng sai vì những document chỉ cần `active=false` hoặc `stock=0` cũng khớp.

Giải pháp:

- Dùng wrapper `Boolean`/`Integer`/`Long` trong probe nếu cần phân biệt “không chọn” và giá trị mặc định.
- Hoặc dùng `withIgnorePaths("active", "stock")` khi những property đó không được phép tham gia truy vấn.
- Không gắn thẳng một entity đầy đủ với tất cả primitive vào form QBE mà không kiểm soát.

### 8.3. `withIgnorePaths` loại field dù có giá trị

```java
ExampleMatcher matcher = ExampleMatcher.matchingAny()
    .withIgnorePaths("id", "tenantId", "priceCents");
```

Nếu probe chứa `id="p-01"` mà matcher ignore `id`, ID **không** trở thành predicate. `withIgnorePaths` không tự tạo một “danh sách chỉ cho phép” theo kiểu whitelist hoàn chỉnh: những property khác có giá trị vẫn có thể tham gia. Vì vậy nên dựng probe **có chủ đích** từ các trường đã xác thực, thay vì copy toàn bộ entity được gửi từ HTTP.

### 8.4. Chọn chế độ match và chọn property là hai quyết định khác nhau

| Quyết định | API | Kết quả |
| --- | --- | --- |
| Đưa property nào vào query | Probe non-null, `withIgnorePaths` | Tập predicate |
| Nối các predicate với nhau | `matchingAll` / `matchingAny` | AND hoặc OR |
| So khớp giá trị string ra sao | `withStringMatcher` / `withMatcher` | Exact, starts, contains... |
| So sánh hoa/thường | `withIgnoreCase` hoặc matcher theo field | Case-sensitive hoặc insensitive |
| Xử lý null tường minh | `withIncludeNullValues` | Thay đổi predicate, có caveat MongoDB |

Một thay đổi trên form có thể cần cập nhật **cả hai trục**: field nào được chọn và phép nối giữa chúng. Không chỉ chuyển sang `matchingAny` rồi kỳ vọng các field trống tự biến mất trong mọi kiểu model.

## 9. Ví dụ service hoàn chỉnh: ALL/ANY với bộ lọc tenant bắt buộc

Đây là mẫu nên dùng khi ứng dụng có dữ liệu nhiều tenant. Người dùng chọn AND hoặc OR cho **các trường tìm kiếm tùy chọn**, còn điều kiện tenant **luôn bắt buộc**.

### 9.1. Request DTO

```java
public record ProductSearchRequest(
    String name,
    String category,
    String brand,
    Boolean active,
    boolean matchAny
) {}
```

`matchAny` là tùy chọn của request/service, **không phải field của `ProductDocument`**. Không đưa property này vào probe. Giá trị `tenantId` phải lấy từ security context đáng tin cậy hoặc lời gọi nội bộ đã được xác thực, không tin trực tiếp ID tenant do client tự thay đổi.

### 9.2. Code áp dụng AND/OR tùy chọn nhưng AND tenant bắt buộc

```java
import java.util.List;

import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class ProductSearchService {

    private final MongoTemplate template;

    public ProductSearchService(MongoTemplate template) {
        this.template = template;
    }

    public List<ProductDocument> search(
        String trustedTenantId,
        ProductSearchRequest request
    ) {
        if (trustedTenantId == null || trustedTenantId.isBlank()) {
            throw new IllegalArgumentException("Thiếu tenant");
        }

        String name = normalize(request.name());
        String category = normalize(request.category());
        String brand = normalize(request.brand());
        Boolean active = request.active();

        int selected = (name != null ? 1 : 0)
            + (category != null ? 1 : 0)
            + (brand != null ? 1 : 0)
            + (active != null ? 1 : 0);

        if (selected == 0) {
            throw new IllegalArgumentException(
                "Phải nhập ít nhất một tiêu chí tìm kiếm"
            );
        }

        ProductDocument probe = new ProductDocument(
            null,   // id
            null,   // tenantId: không đưa vào nhóm OR
            name,
            category,
            brand,
            active,
            null    // priceCents: không dùng ở màn hình này
        );

        ExampleMatcher matcher = request.matchAny()
            ? ExampleMatcher.matchingAny()
            : ExampleMatcher.matchingAll();

        matcher = matcher.withIgnorePaths(
            "id", "tenantId", "priceCents"
        );

        Example<ProductDocument> example =
            Example.of(probe, matcher);

        Criteria requiredTenant =
            Criteria.where("tenantId").is(trustedTenantId);

        Criteria optionalSearch =
            Criteria.byExample(example);

        Query query = Query.query(
            new Criteria().andOperator(
                requiredTenant,
                optionalSearch
            )
        );

        query.with(
            Sort.by(
                Sort.Order.asc("name"),
                Sort.Order.asc("id")
            )
        );
        query.limit(30);

        return template.find(
            query,
            ProductDocument.class
        );
    }

    private static String normalize(String value) {
        if (value == null) {
            return null;
        }
        String trimmed = value.trim();
        return trimmed.isEmpty() ? null : trimmed;
    }
}
```

Logic của hai trường hợp:

```text
matchAny = false:
    tenantId = t-A
    AND name nếu có
    AND category nếu có
    AND brand nếu có
    AND active nếu có

matchAny = true:
    tenantId = t-A
    AND (
        name nếu có
        OR category nếu có
        OR brand nếu có
        OR active nếu có
    )
```

**Không** viết `ExampleMatcher.matchingAny()` với probe có `tenantId="t-A"` để mong MongoDB hiểu tenant là điều kiện bắt buộc. Khi đó tenant có nguy cơ trở thành **một nhánh OR**, và các document tenant khác có thể khớp qua category/brand. Ràng buộc quyền truy cập cần được giữ **ngoài nhóm OR tùy chọn**.

### 9.3. Query BSON minh họa

Với tenant `t-A`, category `keyboard` và brand `ACME`, lựa chọn ANY có ý nghĩa:

```javascript
db.products.find({
  tenant_id: "t-A",
  $or: [
    { category: "keyboard" },
    { brand_code: "ACME" }
  ]
})
.sort({ name: 1, _id: 1 })
.limit(30);
```

Trong đường Spring Data có typed Example, điều kiện `_class` có thể được thêm vào; cú pháp ở đây mô tả **logic nghiệp vụ**, không cam kết command thực tế chỉ có từng ấy field. Dù dùng QBE hay raw query, kết quả của tenant khác không được xuất hiện.

### 9.4. Vì sao phải kiểm tra số điều kiện đã chọn?

Nếu tất cả `name`, `category`, `brand`, `active` đều null, matcher có thể không tạo predicate nội dung và query chỉ còn điều kiện tenant/type. Với hàng triệu sản phẩm, điều này dẫn tới một lần quét quá rộng nếu không có limit hoặc index phù hợp.

Từ chối request không có tiêu chí là một chính sách an toàn cho endpoint tìm kiếm này. Ở use case khác, có thể cho phép duyệt tất cả sản phẩm trong tenant, nhưng phải là chức năng được định nghĩa riêng với phân trang, giới hạn và quyền phù hợp.

## 10. Phân biệt giá trị `false`, `null` và “không chọn”

Với ô chọn trạng thái ba giá trị:

```text
Tất cả trạng thái → active = null (bỏ qua predicate)
Chỉ đang hoạt động → active = true
Chỉ ngừng hoạt động → active = false
```

Ví dụ probe:

```java
ProductDocument inactiveProbe = new ProductDocument(
    null,
    null,
    null,
    null,
    null,
    Boolean.FALSE,
    null
);
```

`Boolean.FALSE` là một **giá trị cụ thể** và được QBE đưa vào query. Với `matchingAny()` có thêm `brand="ACME"`, điều kiện thành `active=false OR brand=ACME`, không phải “lọc ACME rồi chỉ lấy inactive”. Nếu cần **brand=ACME AND active=false** dù có nhiều trường tìm kiếm OR khác, hãy nhóm điều kiện một cách tường minh bằng `Criteria.andOperator(...)`.

**Không dùng `withIncludeNullValues()` để diễn đạt “người dùng chưa chọn trạng thái”.** API đó yêu cầu xét các field null theo semantics khác, và trong Spring Data MongoDB có những hệ quả quan trọng với subdocument.

## 11. Tùy chỉnh string matching cho từng trường

Khi tìm sản phẩm theo tên, người dùng thường muốn “chứa một cụm từ” thay vì bằng đúng từng ký tự. `ExampleMatcher` hỗ trợ `StringMatcher` và matcher theo property.

### 11.1. Chính xác, bắt đầu, kết thúc, chứa

| Chế độ | Ý nghĩa | Hình dung MongoDB |
| --- | --- | --- |
| `DEFAULT` | So sánh mặc định của store/framework | Thường là equality với string khi case-sensitive |
| `EXACT` | So khớp toàn chuỗi | Regex neo đầu/cuối tùy cách framework sinh |
| `STARTING` | Bắt đầu bằng chuỗi | Regex kiểu prefix |
| `ENDING` | Kết thúc bằng chuỗi | Regex kiểu suffix |
| `CONTAINING` | Có chuỗi nằm bên trong | Regex kiểu contains |
| `REGEX` | Pattern regex | Cần kiểm soát đặc biệt nếu input không tin cậy |

Ví dụ đặt mặc định chứa, nhưng riêng category/brand phải khớp chính xác:

```java
import static org.springframework.data.domain.ExampleMatcher
    .GenericPropertyMatchers.exact;
import static org.springframework.data.domain.ExampleMatcher
    .GenericPropertyMatchers.contains;

import org.springframework.data.domain.ExampleMatcher;

ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withIgnorePaths(
        "id", "tenantId", "priceCents"
    )
    .withMatcher("name", contains().ignoreCase())
    .withMatcher("category", exact())
    .withMatcher("brand", exact());
```

Để chọn ANY, thay `matchingAll()` bằng `matchingAny()`, giữ nguyên các property matcher tương ứng.

### 11.2. Cấu hình case sensitivity

```java
ExampleMatcher caseInsensitive = ExampleMatcher.matchingAny()
    .withIgnorePaths("id", "tenantId", "priceCents")
    .withIgnoreCase("name", "brand");
```

`withIgnoreCase(...)` thiết lập xử lý chữ hoa/thường cho những trường được chỉ định, nhưng **không mặc nhiên bỏ dấu tiếng Việt**, không phải fuzzy search và không giống một câu equality với MongoDB collation locale-specific.

Với MongoDB, case-insensitive string matching trong QBE thường được thể hiện qua `$regex` và option `i`. Regex này **không có cùng khả năng dùng index collation như equality được cấu hình collation tương thích**. Với tìm kiếm tên tiếng Việt có yêu cầu Unicode phức tạp, cần thiết kế canonical search key, collation hoặc công cụ search riêng theo mục tiêu nghiệp vụ.

### 11.3. QBE không phải full-text search

Nếu muốn tìm “bàn phím” theo từ vựng, dấu, từ gần nghĩa, loại bàn phím, relevance score, stemming hay fuzzy matching, `matchingAny` + `CONTAINING` không tự biến thành full-text engine.

Lựa chọn thay thế có thể là:

- `Criteria` với equality/range/regex được kiểm soát.
- Query lên trường canonical đã chuẩn hóa có index phù hợp.
- MongoDB text index khi tính năng đó phù hợp.
- Giải pháp search chuyên dụng nếu cần độ liên quan, gợi ý hay ngôn ngữ phức tạp.

Không cho client đưa trực tiếp regex tùy ý vào một endpoint production nếu chưa kiểm tra chi phí và an toàn truy vấn.

## 12. Typed Example, `_class` và `UntypedExampleMatcher`

Đây là đặc thù MongoDB dễ khiến người học hiểu nhầm kết quả QBE.

### 12.1. Typed Example mặc định có thể giới hạn loại entity

```java
Example<ProductDocument> example =
    Example.of(probe, ExampleMatcher.matchingAll());
```

Theo semantics MongoDB QBE, **typed Example** thông thường đưa ràng buộc loại domain vào query. Với cấu hình type hint mặc định, nó có thể kiểm tra `_class` (hoặc type aliases) để chỉ lấy những document thuộc loại được hỗ trợ.

Ví dụ nếu document được tạo qua `mongosh`:

```javascript
db.products.insertOne({
  _id: "manual-01",
  tenant_id: "t-A",
  category: "keyboard",
  brand_code: "ACME"
  // Không có _class.
});
```

thì một typed Example của `ProductDocument` có thể **không khớp** document này dù category/brand giống hoàn toàn. Khi thử QBE bằng shell data, phải kiểm tra type hints thực tế thay vì kết luận logic AND/OR bị lỗi.

### 12.2. Bỏ type restriction bằng `UntypedExampleMatcher`

Khi collection không lưu type hints hoặc chứa nhiều loại document có trường tương thích, có thể dùng:

```java
import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;
import org.springframework.data.mongodb.core.query.UntypedExampleMatcher;

ExampleMatcher matcher = UntypedExampleMatcher.matchingAny()
    .withIgnorePaths(
        "id", "tenantId", "name", "active", "priceCents"
    );

Example<ProductDocument> example = Example.of(
    probe, matcher
);
```

`UntypedExampleMatcher` cho phép không áp đặt type restriction mặc định khi xây MongoDB QBE. Tuy nhiên, **untyped không phải lựa chọn luôn tốt hơn**: nó có thể làm query khớp các document có field giống nhưng thuộc mô hình nghiệp vụ khác. Hãy kiểm tra schema, tenant, phân quyền, kiểu BSON và lý do tại sao collection không lưu `_class`.

Nếu cần typed QBE nhưng dữ liệu cũ không có type hints, có thể phải sửa cách nhập liệu, migration hoặc chọn một truy vấn `Criteria` trực tiếp có hợp đồng rõ ràng. Đừng thêm `_class` cho dữ liệu production mà không đánh giá khả năng đọc/ghi của toàn hệ thống.

### 12.3. Khi nào type restriction có ý nghĩa?

- Collection lưu nhiều subtype.
- Có polymorphic mapping hoặc `@TypeAlias`.
- Dữ liệu được ghi qua nhiều luồng, một số có `_class` và số khác không.
- QBE test thất bại nhưng `mongosh find(...)` khớp.

Cần đọc document BSON thật, kiểm tra mapping context và xem command MongoDB được gửi. `UntypedExampleMatcher` chỉ thay đổi cách giới hạn type, **không** thay đổi ý nghĩa AND/OR của `matchingAll`/`matchingAny`.

## 13. Null trong QBE và embedded document

### 13.1. Mặc định bỏ qua null

`ExampleMatcher.matchingAll()` thông thường bỏ qua các property null trong probe. Vì vậy `brand=null` không có nghĩa tìm document có `brand_code:null`; nó chỉ loại predicate về brand.

Nếu nghiệp vụ thực sự cần tìm document **thiếu field** hoặc **có field null**, dùng `Criteria.where("brand").is(null)`, `exists(false)` hoặc `$type` theo đúng semantics MongoDB thay vì tự suy ra từ một probe rỗng. Lưu ý MongoDB so sánh `field: null` theo cách có thể bao gồm cả field thiếu; phải làm rõ nhu cầu.

### 13.2. `withIncludeNullValues()` cần thận trọng

```java
ExampleMatcher includeNulls =
    ExampleMatcher.matchingAll()
        .withIncludeNullValues();
```

Tùy chọn này bảo framework **xem xét** các property null thay vì bỏ qua. Trên MongoDB, khi có **embedded document**, việc include null có thể khiến QBE xây **embedded document matching** thay vì các predicate dot notation riêng biệt. Phép đối chiếu có thể đòi hỏi subdocument khớp cấu trúc và thứ tự field theo semantics MongoDB.

Do đó:

- Không bật `withIncludeNullValues()` chỉ để giữ form trống.
- Cần kiểm thử với document thiếu field, field có null và object lồng nhau khác thứ tự/field.
- Nếu cần các điều kiện nested OR/AND phức tạp, viết `Criteria` rõ ràng thay vì dựa vào một matcher toàn cục.
- Phân biệt **null**, **missing** và **empty string** trong schema.

### 13.3. Property path lồng nhau

Nếu entity có `address.city`, có thể dùng:

```java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withMatcher(
        "address.city",
        ExampleMatcher.GenericPropertyMatchers
            .exact()
            .ignoreCase()
    );
```

Đây là cách cấu hình cách so sánh một property path. Nó **không** cho phép biểu diễn mọi nhóm điều kiện kiểu:

```text
(category = keyboard AND brand = ACME)
OR
(category = mouse AND active = true)
```

QBE chỉ có lựa chọn ALL/ANY ở mức các predicate được tạo từ probe, không có AST nhóm boolean tự do. Cần `Criteria.orOperator(...)`/`andOperator(...)` khi yêu cầu nhóm phức tạp.

## 14. ALL/ANY khác gì `$and`/`$or` viết tay?

Với hai field đơn giản, QBE rất dễ đọc:

```java
ExampleMatcher all = ExampleMatcher.matchingAll();
ExampleMatcher any = ExampleMatcher.matchingAny();
```

Nhưng khi logic tăng độ phức tạp, `Criteria` có khả năng nhóm điều kiện rõ hơn:

```javascript
{
  tenant_id: "t-A",
  $or: [
    {
      category: "keyboard",
      brand_code: "ACME"
    },
    {
      category: "mouse",
      active: true
    }
  ]
}
```

Ví dụ `MongoTemplate` với `Criteria`:

```java
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Criteria firstGroup = new Criteria().andOperator(
    Criteria.where("category").is("keyboard"),
    Criteria.where("brand").is("ACME")
);

Criteria secondGroup = new Criteria().andOperator(
    Criteria.where("category").is("mouse"),
    Criteria.where("active").is(true)
);

Criteria optional = new Criteria().orOperator(
    firstGroup, secondGroup
);

Query query = Query.query(
    new Criteria().andOperator(
        Criteria.where("tenantId").is("t-A"),
        optional
    )
);
```

Khi thực thi bằng `template.find(query, ProductDocument.class)`, tên Java như `tenantId`/`brand` được mapping thành field BSON `tenant_id`/`brand_code`. Mẫu trên không có `_class` restriction của typed QBE trừ khi được thêm bởi logic khác. Kiểm thử mapping và điều kiện trên MongoDB thật.

**Quy tắc chọn công cụ:** QBE phù hợp cho một nhóm predicate có cùng phép nối AND hoặc OR; `Criteria` phù hợp hơn khi cần **nhóm OR chứa AND**, so sánh khoảng, `$in`, `$elemMatch`, ngày tháng, điều kiện quyền phức tạp hoặc aggregation.

## 15. Vì sao QBE không thay được mọi truy vấn MongoDB?

QBE có giới hạn về loại phép so sánh và cấu trúc boolean. Những yêu cầu dưới đây thường cần `Criteria`/`Query` hoặc aggregation.

| Nhu cầu | QBE có phù hợp? | Công cụ thường nên dùng |
| --- | --- | --- |
| category bằng giá trị và brand bằng giá trị | Có | `matchingAll()` |
| category hoặc brand | Có | `matchingAny()` |
| Trường optional nếu user không nhập | Có, với null/ignore phù hợp | Probe + matcher |
| Tên bắt đầu/chứa một chuỗi | Có, trong phạm vi string matcher MongoDB hỗ trợ | `withMatcher(...)` |
| price từ 100.000 tới 500.000 | Không biểu diễn trực tiếp bằng QBE equality | `Criteria.gte/lte` |
| date nằm trong khoảng | Không biểu diễn trực tiếp | `Criteria.gte/lte` |
| category=A AND (brand=B OR active=true) | Không có grouped conditions tổng quát | `Criteria.andOperator/orOperator` |
| Match nhiều phần tử array theo điều kiện | Không phù hợp cho `$elemMatch` tổng quát | `Criteria.elemMatch` |
| Join collection customers và orders | Không | Aggregation `$lookup` |
| Đếm, nhóm, tính toán tổng | Không | Aggregation `$group` |
| Search relevance/scoring | Không | Search chuyên dụng/aggregation |
| Transaction cho nhiều document | Không | `MongoTransactionManager`/reactive manager |

QBE **không thể** thay điều kiện an ninh/tenant chỉ vì API có `matchingAll`. Trong ví dụ cho người dùng chọn `matchingAny`, điều kiện bất biến vẫn phải nằm ngoài nhóm predicate tùy chọn.

## 16. Index và hiệu năng của ALL so với ANY

### 16.1. AND có thể tận dụng index kết hợp

Với truy vấn lọc tenant, category, brand:

```javascript
db.products.createIndex({
  tenant_id: 1,
  category: 1,
  brand_code: 1
});
```

Index này có thể phù hợp cho:

```javascript
db.products.find({
  tenant_id: "t-A",
  category: "keyboard",
  brand_code: "ACME"
}).explain("executionStats");
```

Nếu query còn sort theo `name`, index có thể cần thiết kế khác để hỗ trợ filter+sort; không thêm index chỉ vì ví dụ có ba field. Theo dõi index size, write amplification và thống kê thực tế.

### 16.2. OR thường cần đường truy cập hiệu quả cho từng nhánh

Với:

```javascript
db.products.find({
  tenant_id: "t-A",
  $or: [
    { category: "keyboard" },
    { brand_code: "ACME" }
  ]
});
```

Một hướng nghiên cứu index:

```javascript
db.products.createIndex({
  tenant_id: 1,
  category: 1
});

db.products.createIndex({
  tenant_id: 1,
  brand_code: 1
});
```

MongoDB có thể dùng những index phù hợp cho các nhánh OR tùy query planner, selectivity và cấu trúc truy vấn. Nếu một nhánh không có index hữu ích, hiệu năng toàn query có thể bị ảnh hưởng. Không bảo đảm mọi `matchingAny()` luôn có index usage tối ưu.

### 16.3. Regex và kiểu tìm kiếm ảnh hưởng index

`CONTAINING` trên string thường dẫn tới regex cần dò chuỗi ở giữa, khó tận dụng B-tree index như equality hoặc prefix phù hợp. `ignoreCase` có thể sử dụng regex với option `i`; **không tự động sử dụng case-insensitive collation index như một equality có collation tương thích**.

Vì vậy, khi chuyển một search từ `matchingAll` exact sang `matchingAny` contains+ignoreCase, độ trễ có thể tăng đáng kể dù code chỉ đổi vài dòng. Cần đo trên dữ liệu thật.

### 16.4. Kiểm tra bằng `explain`

```javascript
db.products.find({
  tenant_id: "t-A",
  $or: [
    { category: "keyboard" },
    { brand_code: "ACME" }
  ]
})
.sort({ name: 1, _id: 1 })
.limit(30)
.explain("executionStats");
```

Quan sát:

| Chỉ số | Câu hỏi |
| --- | --- |
| `IXSCAN` hoặc `COLLSCAN` | Có dùng index hay quét collection? |
| `totalKeysExamined` | Đã duyệt bao nhiêu index entries? |
| `totalDocsExamined` | Có đọc nhiều document ngoài kết quả không? |
| Sort stage | Có cần sort ngoài index, chi phí bao nhiêu? |
| `nReturned` | Có thực sự giới hạn số kết quả không? |
| p95/p99 latency | Query có đáp ứng SLA trong tải lớn không? |
| Bytes trả về | Có đang tải cả entity khi endpoint chỉ cần DTO? |

`explain` trên một truy vấn `mongosh` được viết tay chỉ chứng minh query **tương đương** hoạt động ra sao. Để xác minh hình dạng QBE thực, có thể quan sát command MongoDB trong integration test hoặc qua MongoDB Java Driver command monitoring (không log dữ liệu riêng tư tùy tiện).

## 17. Trả DTO hoặc projection thay vì entity đầy đủ

Giả sử kết quả tìm kiếm chỉ cần ID, tên, danh mục và brand:

```java
public record ProductSearchResult(
    String id,
    String name,
    String category,
    String brand
) {}
```

Trong các phiên bản Spring Data hỗ trợ `FetchableFluentQuery` cho QBE, có thể dùng `findBy(example, queryFunction)` để tùy chỉnh sort/projection/result processing theo API tương ứng. Tuy nhiên, overload và khả năng tối ưu trường BSON phải đối chiếu Javadoc dependency thực tế.

Một phương án dễ hiểu khác khi cần Query kết hợp quyền là dùng `MongoTemplate`:

```java
Query query = Query.query(
    new Criteria().andOperator(
        Criteria.where("tenantId").is("t-A"),
        Criteria.byExample(example)
    )
);

query.fields()
    .include("id")
    .include("name")
    .include("category")
    .include("brand");

query.limit(30);

List<ProductDocument> partialResults =
    template.find(query, ProductDocument.class);
```

**Cảnh báo:** kết quả `ProductDocument` ở đây chỉ được tải một phần. Không gọi `template.save(partialResults.get(0))`; thao tác lưu có thể làm mất dữ liệu của các field bị projection bỏ đi.

Nếu cần DTO đúng nghĩa, có thể dùng fluent template với source entity và target DTO theo phiên bản Spring Data MongoDB phù hợp:

```java
List<ProductSearchResult> results = template
    .query(ProductDocument.class)
    .as(ProductSearchResult.class)
    .matching(query)
    .all();
```

Dù dùng class-based DTO hay closed interface, hãy xác minh kết quả BSON và alias khi có `@Field("brand_code")`. Projection/DTO **không** thay thế authorization; trường tenant và metadata nhạy cảm không được xuất ra chỉ vì entity có getter.

## 18. Reactive QBE

Trong ứng dụng WebFlux, `ReactiveMongoTemplate` nhận `Query`/`Criteria` tương tự nhưng trả `Flux<T>`:

```java
import org.springframework.data.domain.Example;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

import reactor.core.publisher.Flux;

public Flux<ProductDocument> findReactive(
    ReactiveMongoTemplate template,
    String trustedTenantId,
    Example<ProductDocument> example
) {
    Query q = Query.query(
        new Criteria().andOperator(
            Criteria.where("tenantId").is(trustedTenantId),
            Criteria.byExample(example)
        )
    );

    q.limit(30);
    return template.find(q, ProductDocument.class);
}
```

Ở các phiên bản hỗ trợ `ReactiveQueryByExampleExecutor`, reactive repository cũng có `findAll(example)` trả `Flux`, nhưng cần kiểm tra interface/phiên bản đang dùng.

Reactive QBE không tự mở transaction, không làm query regex trở nên rẻ hơn và không miễn phí RAM nếu downstream gọi `collectList()` trên một tập không giới hạn. Tránh gọi `block()` trong event loop WebFlux.

Nếu nhiều thao tác ghi liên quan cần transaction MongoDB, dùng `ReactiveMongoTransactionManager`/reactive transaction context phù hợp. Việc đọc bằng QBE chỉ là một **truy vấn**, không bảo đảm snapshot giữa nhiều lần đọc hoặc nhiều collection.

## 19. Kiểm thử tích hợp ALL/ANY và ràng buộc tenant

Một unit test chỉ mock `ProductRepository` không chứng minh Spring Data đã dịch `matchingAny()` sang đúng query MongoDB hay đã xử lý type hint của entity. Cần integration test trên MongoDB thật, ví dụ cấu hình qua Testcontainers.

### 19.1. Test dataset cố định, ghi bằng Spring Data

Ví dụ JUnit 5 và Spring Boot `@DataMongoTest`, giả định sử dụng MongoDB database riêng và chưa có những ID này:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.stream.StreamSupport;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;

@DataMongoTest
class ProductQbeIntegrationTest {

    @Autowired ProductRepository products;

    @Test
    void matchingAllAndMatchingAnyReturnDifferentSets() {
        products.saveAll(List.of(
            new ProductDocument(
                "qbe-01", "t-A", "Bàn phím A",
                "keyboard", "ACME", true, 100000L
            ),
            new ProductDocument(
                "qbe-02", "t-A", "Bàn phím B",
                "keyboard", "ZEN", true, 120000L
            ),
            new ProductDocument(
                "qbe-03", "t-A", "Chuột A",
                "mouse", "ACME", true, 90000L
            ),
            new ProductDocument(
                "qbe-04", "t-A", "Chuột B",
                "mouse", "ZEN", false, 80000L
            ),
            new ProductDocument(
                "qbe-05", "t-A", "Bàn phím C",
                "keyboard", "ACME", false, 110000L
            ),
            new ProductDocument(
                "qbe-06", "t-B", "Bàn phím khác tenant",
                "keyboard", "ACME", true, 130000L
            )
        ));

        ProductDocument probe = new ProductDocument(
            null, null, null, "keyboard", "ACME", null, null
        );

        ExampleMatcher allMatcher =
            ExampleMatcher.matchingAll()
                .withIgnorePaths(
                    "id", "tenantId", "name", "active", "priceCents"
                );

        ExampleMatcher anyMatcher =
            ExampleMatcher.matchingAny()
                .withIgnorePaths(
                    "id", "tenantId", "name", "active", "priceCents"
                );

        List<String> allIds = StreamSupport.stream(
                products.findAll(
                    Example.of(probe, allMatcher)
                ).spliterator(),
                false
            )
            .map(ProductDocument::id)
            .sorted()
            .toList();

        List<String> anyIds = StreamSupport.stream(
                products.findAll(
                    Example.of(probe, anyMatcher)
                ).spliterator(),
                false
            )
            .map(ProductDocument::id)
            .sorted()
            .toList();

        assertThat(allIds).containsExactly(
            "qbe-01", "qbe-05", "qbe-06"
        );

        assertThat(anyIds).containsExactly(
            "qbe-01", "qbe-02", "qbe-03",
            "qbe-05", "qbe-06"
        );
    }
}
```

Ở test này, `qbe-06` xuất hiện vì method repository không được bảo vệ bằng tenant filter. **Đó là tình huống chủ ý để minh họa rủi ro**, không phải hành vi cho phép trong endpoint người dùng thật. Một test khác phải xác minh `ProductSearchService` ở mục 9 **không bao giờ trả `qbe-06`** khi tenant đáng tin cậy là `t-A`.

Test dùng ID cố định nên phải chạy trên database/collection test được cô lập, hoặc dọn đúng dữ liệu test; không chạy lệnh xóa toàn collection dùng chung. Mẫu test **chưa được thực thi** trong bước soạn bài này.

### 19.2. Những case cần bảo vệ

| Case | Kỳ vọng |
| --- | --- |
| Hai field category + brand, ALL | Chỉ tài liệu khớp cả hai |
| Hai field category + brand, ANY | Tài liệu khớp một hoặc hai |
| Một field còn lại | ALL và ANY có cùng tập kết quả |
| `active=null` | Không tạo predicate về active |
| `active=false` | Có predicate về trạng thái false |
| Primitive `boolean` trong probe | Không vô tình lọc `false` nếu field không được chọn |
| Probe có ID nhưng matcher ignore ID | ID không thành predicate |
| Probe rỗng | Endpoint theo chính sách từ chối hoặc truy vấn được giới hạn chặt |
| ANY với tenant bắt buộc | Không có dữ liệu tenant khác |
| Category khác chữ hoa/thường | Xác minh string matcher/collation có chủ đích |
| Typed Example với `_class` | Chỉ đọc document phù hợp type |
| Untyped Example với raw shell document | Không bị type restriction ngoài ý muốn |
| Null/embedded document | Phân biệt missing, null, exact embedded matching |
| `@Field("brand_code")` | Truy vấn thật dùng đúng BSON field |
| Pagination/sort | Giới hạn kết quả và thứ tự ổn định |

### 19.3. Cách kiểm tra query BSON thật

Với `MongoTemplate`, có thể kiểm tra query được tạo cho từng Example và quan sát command thực tế trong môi trường test. Một ví dụ MongoDB tương đương:

```javascript
db.products.find({
  tenant_id: "t-A",
  $or: [
    { category: "keyboard" },
    { brand_code: "ACME" }
  ]
})
.sort({ name: 1, _id: 1 })
.limit(30);
```

Nếu document có type hint, hình dạng command từ Spring Data có thể khác. Truy vấn shell giúp chứng minh semantics MongoDB, nhưng để xác nhận Spring Data sinh đúng BSON cần integration test và quan sát driver command/profiler (tránh log dữ liệu cá nhân).

## 20. Các lỗi phổ biến khi dùng ALL/ANY

**“`matchingAny` nghĩa là tìm tất cả trường đều đúng nhưng không quan tâm thứ tự.”** Sai. ANY là **OR**, chỉ cần một predicate được chọn đúng.

**“Probe có 7 property nghĩa là QBE sẽ tìm theo cả 7.”** Không. Property null mặc định được bỏ qua, còn property ignored không tham gia.

**“Primitive false/0 cũng tự được bỏ qua vì người dùng chưa nhập.”** Sai. Primitive có giá trị mặc định không null và có thể tạo predicate không mong muốn.

**“Đặt tenantId trong probe với `matchingAny` vẫn giữ giới hạn tenant.”** Sai về mô hình logic. Tenant phải là điều kiện bắt buộc **bên ngoài** nhóm OR hoặc phải dùng một cấu trúc Criteria bảo đảm quyền.

**“`withIgnorePaths` tự động whitelist tất cả field còn lại.”** Nó chỉ loại những path chỉ định; property ngoài danh sách ignore mà có giá trị vẫn có thể tham gia.

**“`withIncludeNullValues` chỉ có nghĩa bỏ qua field null.”** Ngược lại, nó đưa null vào quy tắc so khớp và có thể thay đổi embedded document matching.

**“QBE hỗ trợ mọi tổ hợp AND/OR lồng nhau.”** Không. Dùng `Criteria` cho nhóm logic phức tạp.

**“`matchingAny` sắp xếp sản phẩm khớp nhiều tiêu chí lên đầu.”** Không. Muốn ranking phải thiết kế sort/scoring riêng.

**“Case-insensitive QBE dùng index collation đúng như equality.”** Không mặc định. Với MongoDB, ignoreCase thường dùng regex; cần đo `explain`.

**“Ghi document bằng `mongosh` không có `_class` thì typed QBE luôn tìm thấy.”** Không chắc; typed QBE có thể thêm type restriction. Kiểm tra BSON và dùng `UntypedExampleMatcher` nếu phù hợp schema.

**“QBE giúp sửa dữ liệu cũ hoặc chuẩn hóa Unicode.”** Không. QBE chỉ truy vấn; migration, validation và normalization là các quy trình khác.

**“Truy vấn QBE chỉ đọc thì kết quả luôn nhất quán qua nhiều request.”** Không. Dữ liệu có thể thay đổi giữa các lần đọc; transaction/read concern là phạm vi thiết kế riêng.

## 21. Bài thực hành tự kiểm tra

1. Tạo entity `ProductDocument` có category, brand, active dạng `Boolean` wrapper, và một số field ánh xạ bằng `@Field`.
2. Ghi sáu document mẫu bằng Spring Data để kiểm tra typed Example; không chỉ insert bằng shell.
3. Tạo probe `category="keyboard", brand="ACME"` với những property khác null.
4. Gọi `findAll(Example.of(probe, matchingAll()))`, dự đoán danh sách ID.
5. Đổi sang `matchingAny()`, giải thích vì sao `p-02`/`p-03` được bổ sung.
6. Chỉ giữ một property trong probe; xác minh ALL và ANY tương đương.
7. Thêm `active=false`, xem cách predicate thay đổi trong cả hai chế độ.
8. Thử một probe primitive `boolean` default false; giải thích kết quả bất ngờ.
9. Dùng `withIgnorePaths` loại một property dù có giá trị.
10. Viết `ProductSearchService` với tenant bắt buộc ngoài nhóm OR; test không rò rỉ `p-06`.
11. Thử `withMatcher("name", contains().ignoreCase())`, kiểm tra kết quả tiếng Việt và query plan.
12. Thử một document tạo bằng shell thiếu `_class`, đối chiếu typed và untyped QBE.
13. So sánh query QBE với `Criteria.orOperator`/`andOperator` tương đương.
14. Thử yêu cầu phức tạp `(category=A AND brand=B) OR (category=C AND active=true)` và viết bằng `Criteria`.
15. Tạo index cho các query AND/OR thực tế, dùng `explain("executionStats")` đo hiệu năng.
16. Viết integration test cho null, active=false, tenant, sort/pagination và trường BSON đổi tên.

## 22. Checklist trước khi triển khai production

| Câu hỏi | Điều cần xác minh |
| --- | --- |
| Đang dùng ALL hay ANY? | `matchingAll()` = AND; `matchingAny()` = OR |
| Có bao nhiêu predicate thực sự được chọn? | Null mặc định bị bỏ; primitive có giá trị mặc định |
| Có field nào cần luôn bỏ qua? | `withIgnorePaths(...)` rõ ràng |
| Probe có đến từ request chưa kiểm soát? | Dựng probe từ whitelist field đã được xác thực |
| Tenant/authorization đặt ở đâu? | **Ngoài** nhóm ANY, ràng buộc AND bắt buộc |
| Probe rỗng có được phép? | Quy định chính sách, limit và paging |
| Có Boolean/Integer tùy chọn? | Dùng wrapper để phân biệt “không chọn” |
| Có dùng `withIncludeNullValues()`? | Hiểu null/missing/embedded matching |
| Có cần so sánh gần đúng, range hoặc nested OR? | Dùng `Criteria`/aggregation thay QBE |
| Có typed `_class` không? | Kiểm tra mapping và type hints dữ liệu cũ |
| Có `@Field` rename? | Quan sát BSON query, test mapping |
| String matcher có tạo regex khó dùng index? | Kiểm tra `explain` và dữ liệu đại diện |
| Query có thể trả rất nhiều bản ghi? | Sort/limit/page và index |
| DTO/projection có thiếu field? | Không save entity partial |
| Reactive có block event loop? | Dùng `Flux`/`Mono` không chặn |
| Đã test AND/OR thật trên MongoDB? | Test cả loại được chọn, tenant và điều kiện edge |

## 23. Tài liệu tham khảo

Các API của QBE thuộc Spring Data Commons, còn cách chuyển Example thành truy vấn MongoDB, type restriction và string matching phụ thuộc Spring Data MongoDB. Khi tích hợp một dự án cụ thể, nên đối chiếu **phiên bản dependency** thay vì giả định mọi overload từ Javadoc mới nhất đều có.

- [Spring Data MongoDB — Repository Query by Example](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html)
- [Spring Data MongoDB — Template Query Operations và Query by Example](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html)
- [Spring Data Commons — Query by Example](https://docs.spring.io/spring-data/commons/reference/query-by-example.html)
- [Spring Data MongoDB — UntypedExampleMatcher API](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/core/query/UntypedExampleMatcher.html)
- [Spring Data MongoDB — Criteria API](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/core/query/Criteria.html)
- [MongoDB Manual — Query Documents](https://www.mongodb.com/docs/manual/tutorial/query-documents/)
- [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)

**Kết luận:** trong Spring Data MongoDB, **`ExampleMatcher.matchingAll()`** biểu diễn **AND** và **`ExampleMatcher.matchingAny()`** biểu diễn **OR** giữa các predicate được sinh từ những property thực sự được chọn. Chất lượng truy vấn phụ thuộc vào **probe được dựng có chủ đích**, xử lý `null`/primitive, `withIgnorePaths`, string matcher và typed `_class`; bảo mật phụ thuộc vào **điều kiện tenant/authorization bắt buộc đặt ngoài nhóm OR**. Khi logic cần nhóm phức tạp, range hoặc aggregation, chuyển sang `Criteria`/`MongoTemplate`; khi dữ liệu lớn, kết hợp index, paging, projection và kiểm thử trên BSON thực tế để có kết quả đúng, an toàn và đo đạc được.


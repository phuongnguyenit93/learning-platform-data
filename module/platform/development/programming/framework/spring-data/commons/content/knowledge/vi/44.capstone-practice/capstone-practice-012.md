# Đối chiếu một ca sử dụng tương đương trên store khác

## 1. Mục tiêu thực hành

Bài học thuộc chương **Thực hành tổng hợp** của module `SPRING_DATA_COMMONS`, với phạm vi tìm hiểu các abstraction dùng chung của Spring Data như Repository, CRUD, derived queries, phân trang, sắp xếp, projection và auditing.

Ta sẽ triển khai cùng một ca sử dụng đọc danh mục sản phẩm theo hai hướng:

- Spring Data JPA, lưu dữ liệu trong database quan hệ.
- Spring Data MongoDB, lưu dữ liệu trong collection document.

Mục tiêu là xác định phần hợp đồng có thể giữ chung và phần phải thiết kế theo store. Việc hai repository dùng cùng `Pageable` hoặc có cùng tên derived query chưa đủ chứng minh hai ứng dụng có hành vi tương đương.

Trong bài này, **tương đương** nghĩa là cùng đầu vào hợp lệ và cùng dữ liệu nghiệp vụ cố định cho ra cùng danh sách kết quả, thứ tự, thông tin phân trang và quy tắc cách ly tenant. Không yêu cầu SQL và truy vấn MongoDB có cùng hình thức, cùng số thao tác nội bộ hoặc cùng đặc điểm transaction.

Các đoạn mã minh họa giả định Java hỗ trợ `record`, một tổ hợp Spring Data tương thích và các module tương ứng đã được cấu hình. Ví dụ JPA dùng namespace `jakarta.persistence`. Không ghép tùy ý các phiên bản Commons, JPA, MongoDB và provider chỉ vì mã nguồn có cùng abstraction.

## 2. Chốt ca sử dụng trước khi chọn repository

### 2.1. Yêu cầu nghiệp vụ

API danh mục cần trả các sản phẩm:

1. Thuộc tenant hiện tại.
2. Có trạng thái `ACTIVE`.
3. Sắp xếp theo `createdAt` giảm dần; nếu thời gian bằng nhau, theo `id` giảm dần.
4. Phân trang với chỉ số bắt đầu từ `0`.
5. Trả ID, tên và thời điểm tạo; kèm tổng số sản phẩm phù hợp bộ lọc.

Giới hạn kích thước trang từ `1` đến `100`. Tenant rỗng, chỉ số trang âm hoặc kích thước không hợp lệ bị từ chối trước khi gọi repository.

Tenant trong ứng dụng thực tế phải đến từ ngữ cảnh đã được xác thực hoặc được đối chiếu quyền truy cập. Việc method có tham số `tenantId` không tự tạo ra cơ chế phân quyền.

### 2.2. Những giả định để phép đối chiếu có nghĩa

- Dataset không bị thay đổi trong khi kiểm chứng.
- ID là chuỗi do ứng dụng gán, duy nhất toàn bộ dataset và giống nhau ở hai store.
- ID trong ví dụ chỉ dùng ký tự ASCII và có cùng độ dài; collation được chọn phải cho thứ tự phù hợp.
- Trạng thái và tenant được lưu theo cùng quy ước, không có giá trị `null` ở các trường lọc và sort.
- Thời điểm mẫu là UTC, ở độ chính xác giây để tránh khác biệt độ chính xác lưu trữ.
- Không có converter tùy chỉnh thay đổi giá trị nghiệp vụ trong ví dụ cơ sở.

Đây là các điều kiện của bài thực hành. Nếu ứng dụng cần null, collation ngôn ngữ, ID khác kiểu hoặc dữ liệu cập nhật liên tục, phải mở rộng hợp đồng và kiểm chứng riêng.

## 3. Dữ liệu mẫu và đáp án kỳ vọng

Sử dụng cùng một tập dữ liệu nghiệp vụ cho hai store:

| ID | Tenant | Tên | Trạng thái | `createdAt` |
| --- | --- | --- | --- | --- |
| `p001` | `acme` | Chuột | `ACTIVE` | `2026-01-10T08:00:00Z` |
| `p002` | `beta` | Màn hình | `ACTIVE` | `2026-01-10T12:00:00Z` |
| `p003` | `acme` | Bàn phím | `ACTIVE` | `2026-01-10T09:00:00Z` |
| `p004` | `acme` | Tai nghe | `INACTIVE` | `2026-01-10T11:00:00Z` |
| `p005` | `acme` | Loa | `ACTIVE` | `2026-01-10T10:00:00Z` |
| `p006` | `acme` | Webcam | `ACTIVE` | `2026-01-10T10:00:00Z` |
| `p007` | `acme` | Micro | `ACTIVE` | `2026-01-10T09:00:00Z` |

Với tenant `acme`, danh sách đúng sau lọc và sort là:

```text
p006, p005, p007, p003, p001
```

Với kích thước trang bằng `2`:

| Trang | ID trong nội dung | Tổng phần tử | Tổng số trang |
| --- | --- | --- | --- |
| `0` | `p006`, `p005` | `5` | `3` |
| `1` | `p007`, `p003` | `5` | `3` |
| `2` | `p001` | `5` | `3` |
| `3` | Rỗng | `5` | `3` |

Hai cặp có cùng `createdAt` giúp phát hiện lỗi thiếu tiêu chí sort phụ. `p002` giúp phát hiện rò dữ liệu giữa tenant; `p004` giúp phát hiện thiếu điều kiện trạng thái.

Không chỉ kiểm tra hai store có cùng kết quả. Nếu cả hai cùng quên bộ lọc tenant, chúng vẫn có thể bằng nhau nhưng cùng sai. Cần so sánh từng implementation với đáp án nghiệp vụ độc lập ở trên.

## 4. Định nghĩa hợp đồng chung bằng Commons

Các kiểu sau được chia sẻ ở tầng ca sử dụng:

```java
public enum ProductStatus {
    ACTIVE,
    INACTIVE
}
```

```java
import java.time.Instant;

public record ProductView(
        String id,
        String name,
        Instant createdAt) {
}
```

```java
import org.springframework.data.domain.Page;

public interface CatalogSearch {

    Page<ProductView> findActive(String tenantId, int page, int size);
}
```

`CatalogSearch` là cổng của ca sử dụng, không phải interface repository mà Spring Data tự triển khai. Mỗi adapter sẽ sử dụng repository phù hợp với store.

Dùng chung quy tắc tạo yêu cầu phân trang:

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

public final class CatalogPages {

    private CatalogPages() {
    }

    public static PageRequest request(
            String tenantId, int page, int size) {

        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("tenantId không được rỗng");
        }
        if (page < 0) {
            throw new IllegalArgumentException("page phải từ 0 trở lên");
        }
        if (size < 1 || size > 100) {
            throw new IllegalArgumentException("size phải nằm trong [1, 100]");
        }

        return PageRequest.of(
                page,
                size,
                Sort.by(
                        Sort.Order.desc("createdAt"),
                        Sort.Order.desc("id")));
    }
}
```

Tên thuộc tính trong `Sort` là tên thuộc tính Java của mô hình repository. JPA có thể ánh xạ `createdAt` sang cột `created_at`; MongoDB có thể ánh xạ `id` sang `_id`. Không thay `Sort` của cả hai adapter bằng tên cột SQL.

Ca sử dụng cố định tập thuộc tính sort nên không nhận một tên thuộc tính bất kỳ từ request. Nếu mở rộng sort động, cần có danh sách cho phép và quy tắc tương đương giữa hai store.

## 5. Implementation A: Spring Data JPA

### 5.1. Mô hình persistence riêng của JPA

```java
import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "catalog_product")
public class ProductRow {

    @Id
    private String id;

    @Column(name = "tenant_id", nullable = false)
    private String tenantId;

    @Column(nullable = false)
    private String name;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private ProductStatus status;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected ProductRow() {
    }

    public ProductRow(
            String id,
            String tenantId,
            String name,
            ProductStatus status,
            Instant createdAt) {
        this.id = id;
        this.tenantId = tenantId;
        this.name = name;
        this.status = status;
        this.createdAt = createdAt;
    }

    public String getId() {
        return id;
    }

    public String getTenantId() {
        return tenantId;
    }

    public String getName() {
        return name;
    }

    public ProductStatus getStatus() {
        return status;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
```

Các annotation JPA nằm trên field nên ví dụ dùng field access. Constructor không tham số phục vụ yêu cầu khởi tạo entity của JPA; constructor đầy đủ phục vụ tạo dữ liệu minh họa.

ID được gán bởi ứng dụng, không dùng `@GeneratedValue`. Khi nạp fixture qua `save`, cần hiểu cơ chế xác định entity mới của module và provider; không mặc định `save` luôn tương đương một lệnh `INSERT`. Với ID đã gán, đường `merge` có thể được sử dụng tùy mapping và cơ chế phát hiện entity mới.

Điều quan trọng với phép đối chiếu đọc là dataset cuối cùng đúng, không phải hai store có cùng thuật toán ghi fixture.

### 5.2. Repository JPA

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface JpaProductRepository
        extends JpaRepository<ProductRow, String> {

    Page<ProductRow> findByTenantIdAndStatus(
            String tenantId,
            ProductStatus status,
            Pageable pageable);
}
```

Derived query dùng tên thuộc tính của entity, không dùng `tenant_id`. Ở mức ngữ nghĩa, điều kiện tương ứng là tenant và status cùng khớp; sort và phân trang đến từ `Pageable`.

Một biểu diễn JPQL tương đương về ý tưởng:

```sql
select p
from ProductRow p
where p.tenantId = :tenantId
  and p.status = :status
order by p.createdAt desc, p.id desc
```

Đây là mô tả ý nghĩa, không phải cam kết về SQL chính xác mà provider phát sinh. Cú pháp limit/offset, cách bind và kiểu timestamp của SQL thực tế phụ thuộc provider, dialect và database.

### 5.3. Adapter JPA

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;

public final class JpaCatalogSearch implements CatalogSearch {

    private final JpaProductRepository repository;

    public JpaCatalogSearch(JpaProductRepository repository) {
        this.repository = repository;
    }

    @Override
    public Page<ProductView> findActive(
            String tenantId, int page, int size) {

        PageRequest request = CatalogPages.request(tenantId, page, size);

        return repository.findByTenantIdAndStatus(
                        tenantId, ProductStatus.ACTIVE, request)
                .map(row -> new ProductView(
                        row.getId(),
                        row.getName(),
                        row.getCreatedAt()));
    }
}
```

Adapter chuyển mô hình persistence sang DTO. `Page.map` chuyển nội dung đồng thời giữ thông tin phân trang và tổng số phần tử của trang nguồn.

## 6. Implementation B: Spring Data MongoDB

### 6.1. Mô hình document riêng

```java
import java.time.Instant;

import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "catalog_products")
public record ProductDocument(
        @MongoId(FieldType.STRING) String id,
        String tenantId,
        String name,
        ProductStatus status,
        Instant createdAt) {
}
```

Ví dụ dùng record làm document immutable. Mapping của Spring Data MongoDB sử dụng constructor phù hợp của record; đây là một mô hình riêng, không yêu cầu entity JPA cũng trở thành record.

`@MongoId(FieldType.STRING)` biểu đạt chủ ý lưu ID dưới dạng chuỗi. Chi tiết này tránh việc suy diễn rằng mọi chuỗi ID đều có cùng biểu diễn với `ObjectId`. ID tại MongoDB được ánh xạ tới trường `_id`.

Không dùng constraint của JPA để giả định MongoDB đã có cùng ràng buộc. Ví dụ cơ sở bảo đảm dữ liệu hợp lệ khi tạo fixture; ứng dụng thật cần validation và, nếu phù hợp, quy tắc schema của MongoDB.

### 6.2. Repository MongoDB

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface MongoProductRepository
        extends MongoRepository<ProductDocument, String> {

    Page<ProductDocument> findByTenantIdAndStatus(
            String tenantId,
            ProductStatus status,
            Pageable pageable);
}
```

Phương thức có cùng tên và cùng hình dạng tham số như phía JPA, nhưng domain type và repository gốc khác nhau.

Với mapping thông thường của ví dụ, hình dung truy vấn MongoDB tương ứng là:

```javascript
db.catalog_products
  .find({ tenantId: "acme", status: "ACTIVE" })
  .sort({ createdAt: -1, _id: -1 })
  .skip(0)
  .limit(2)
```

Đây là truy vấn minh họa để giải thích bộ lọc và thứ tự. Khi kiểm chứng, cần quan sát biểu diễn thực tế của enum, timestamp và ID trong cấu hình đang dùng. Converter hoặc mapping tùy chỉnh có thể làm biểu diễn khác đi.

### 6.3. Adapter MongoDB

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;

public final class MongoCatalogSearch implements CatalogSearch {

    private final MongoProductRepository repository;

    public MongoCatalogSearch(MongoProductRepository repository) {
        this.repository = repository;
    }

    @Override
    public Page<ProductView> findActive(
            String tenantId, int page, int size) {

        PageRequest request = CatalogPages.request(tenantId, page, size);

        return repository.findByTenantIdAndStatus(
                        tenantId, ProductStatus.ACTIVE, request)
                .map(document -> new ProductView(
                        document.id(),
                        document.name(),
                        document.createdAt()));
    }
}
```

Hai adapter cung cấp cùng `CatalogSearch`. Ứng dụng có thể chọn một implementation qua cấu hình hoặc qualifier.

Các adapter trong ví dụ chưa được đánh dấu component. Nếu đăng ký cả hai làm bean, cần chỉ định bean nào được tiêm vào nơi sử dụng; không dựa vào Spring tự chọn ngẫu nhiên.

## 7. Cấu hình module và repository phải rõ ràng

Để thực hành, có thể dùng hai ứng dụng hoặc hai cấu hình kiểm chứng độc lập. Cách này giúp tách datasource/provider JPA khỏi kết nối MongoDB và quan sát kết quả dễ hơn.

Nếu đặt cả hai module trong cùng ứng dụng:

- Tách package repository và persistence model của hai store.
- Giới hạn phạm vi quét repository phù hợp với từng module.
- Dùng repository gốc đặc thù như `JpaRepository` và `MongoRepository` để nhận diện rõ store.
- Không gắn cả annotation JPA lẫn MongoDB lên một lớp chỉ nhằm tiết kiệm mô hình.
- Xác định rõ bean adapter được sử dụng ở từng luồng.

Khi có nhiều module repository, việc phân loại repository cần đủ thông tin. Một interface chung chỉ kế thừa `Repository` hoặc `CrudRepository` không tự cung cấp mọi căn cứ để định tuyến tới đúng store trong mọi cấu hình.

Cũng không có transaction nguyên tử liên store chỉ vì hai adapter dùng cùng một interface. Bài thực hành đối chiếu hai implementation độc lập, không triển khai ghi đồng thời để thay thế một hệ thống migration.

## 8. Kiểm chứng theo hợp đồng thay vì theo tên API

### 8.1. Dùng cùng tiêu chí cho từng implementation

Sau khi nạp đúng fixture, gọi riêng từng adapter và kiểm tra:

- Trang `0`, size `2` có ID `p006`, `p005`.
- Trang `1` có ID `p007`, `p003`.
- Trang `2` có `p001` và là trang cuối có nội dung.
- Trang `3` rỗng nhưng tổng phần tử vẫn là `5` trên dataset cố định.
- Không có `p002` hoặc `p004` trong bất kỳ trang kết quả nào của tenant `acme`.
- Nội dung DTO có tên và thời điểm đúng, không chỉ ID đúng.
- Tenant không có dữ liệu trả trang rỗng và tổng bằng `0`.
- Đầu vào không hợp lệ bị từ chối theo cùng quy tắc.

Một hàm assertion có thể được tái sử dụng trong các bộ kiểm chứng tích hợp riêng:

```java
import java.util.List;

import org.springframework.data.domain.Page;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

public final class CatalogContractAssertions {

    private CatalogContractAssertions() {
    }

    public static void verify(CatalogSearch search) {
        Page<ProductView> first = search.findActive("acme", 0, 2);
        Page<ProductView> second = search.findActive("acme", 1, 2);
        Page<ProductView> third = search.findActive("acme", 2, 2);
        Page<ProductView> beyond = search.findActive("acme", 3, 2);

        assertEquals(List.of("p006", "p005"), ids(first));
        assertEquals(List.of("p007", "p003"), ids(second));
        assertEquals(List.of("p001"), ids(third));
        assertTrue(beyond.isEmpty());

        for (Page<ProductView> result
                : List.of(first, second, third, beyond)) {
            assertEquals(5L, result.getTotalElements());
            assertEquals(3, result.getTotalPages());
        }

        assertTrue(first.hasNext());
        assertFalse(third.hasNext());

        Page<ProductView> missing = search.findActive("missing", 0, 2);
        assertTrue(missing.isEmpty());
        assertEquals(0L, missing.getTotalElements());

        assertThrows(IllegalArgumentException.class,
                () -> search.findActive(" ", 0, 2));
        assertThrows(IllegalArgumentException.class,
                () -> search.findActive("acme", -1, 2));
        assertThrows(IllegalArgumentException.class,
                () -> search.findActive("acme", 0, 101));
    }

    private static List<String> ids(Page<ProductView> page) {
        return page.getContent().stream()
                .map(ProductView::id)
                .toList();
    }
}
```

Hàm minh họa tập trung vào bộ lọc, thứ tự và metadata. Bộ kiểm chứng hoàn chỉnh còn cần đối chiếu tên, thời điểm và các biên đầu vào khác đã nêu. Nó phải được gọi với adapter kết nối store thật của môi trường thử nghiệm, không chỉ một mock trả sẵn đáp án.

### 8.2. Đối chiếu hai kết quả bổ sung

Sau khi cả hai implementation đã đúng với đáp án độc lập, có thể so sánh:

```text
nội dung DTO JPA == nội dung DTO MongoDB
page number JPA == page number MongoDB
page size JPA == page size MongoDB
total elements JPA == total elements MongoDB
```

Đây là bằng chứng cho phạm vi fixture và ca sử dụng đã xét. Nó không chứng minh mọi query tương lai hoặc mọi khả năng của hai store là tương đương.

Các đoạn kiểm chứng ở bài học là hướng dẫn thực hành, không phải báo cáo rằng chúng đã được chạy trên một dự án cụ thể.

## 9. Quan sát truy vấn và chi phí thực thi

Vì trả `Page`, ứng dụng có nhu cầu tổng số phần tử. Store có thể thực hiện thêm count query hoặc áp dụng tối ưu để suy ra tổng trong một số tình huống.

Không dùng quy tắc “mỗi lần gọi luôn đúng hai query” làm tiêu chí tương đương. Hãy kiểm tra kết quả hợp đồng và quan sát số thao tác thực tế để đánh giá chi phí.

Những điều cần xem:

| Khía cạnh | JPA | MongoDB |
| --- | --- | --- |
| Biểu diễn bộ lọc | Thuộc tính entity được provider chuyển thành SQL | Thuộc tính document được mapping thành bộ lọc |
| Phân trang | Provider/dialect áp dụng giới hạn và offset | Thường thể hiện qua skip/limit cho kiểu truy vấn này |
| Sort phụ | Cột ID được mapping | Trường `_id` với kiểu đã chọn |
| Tổng số phần tử | Count hoặc tối ưu phù hợp đường thực thi | Count hoặc tối ưu phù hợp đường thực thi |
| Tạo đối tượng | JPA provider materialize entity | Mapping converter tạo document object |
| Trả DTO | Adapter dùng `Page.map` | Adapter dùng `Page.map` |

Không đánh đồng “cùng kết quả” với “cùng hiệu năng”. Database, index, driver, network, kích thước document và khả năng cache đều có thể làm chi phí khác nhau.

## 10. Index phải được thiết kế theo biểu diễn của store

Bộ lọc cố định tenant và status, sau đó sort theo thời gian và ID. Một index ghép phù hợp là hướng cần xem xét ở cả hai store.

Ví dụ SQL minh họa theo PostgreSQL:

```sql
create index idx_catalog_filter_order
on catalog_product (
    tenant_id,
    status,
    created_at desc,
    id desc
);
```

Ví dụ MongoDB:

```javascript
db.catalog_products.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
})
```

Hai index thể hiện cùng ý định phục vụ truy vấn, nhưng không bảo đảm cùng execution plan hoặc cùng hiệu năng. Cần xem kế hoạch thực thi, độ chọn lọc, kích thước dữ liệu và chi phí duy trì index khi ghi.

Count query vẫn có thể đáng kể. Offset lớn cũng có thể tốn chi phí dù có index. Nếu chuyển sang scrolling hoặc keyset pagination, đó là thay đổi hợp đồng cần đối chiếu lại; không chỉ thay một kiểu repository rồi coi đã hoàn thành.

## 11. Projection: tách hình dạng đầu ra khỏi tối ưu truy vấn

Trong ví dụ cơ sở, repository tải entity/document rồi adapter dùng `Page.map` để tạo `ProductView`. Đây là chuyển đổi ở tầng ứng dụng, **không phải bằng chứng database chỉ trả ba trường**.

Lựa chọn này giúp tập trung vào hợp đồng nghiệp vụ trước. Sau khi có kết quả đúng, có thể tối ưu bằng projection của từng module.

Một interface projection có hình dạng:

```java
import java.time.Instant;

public interface ProductSummary {

    String getId();

    String getName();

    Instant getCreatedAt();
}
```

Có thể khảo sát phương thức như sau trong từng repository, nếu store và release hỗ trợ phạm vi này:

```java
Page<ProductSummary> findByTenantIdAndStatus(
        String tenantId,
        ProductStatus status,
        Pageable pageable);
```

Đây là phương án thay thế kiểu trả về của phương thức cơ sở, không thể khai báo đồng thời hai phương thức có cùng tên và cùng danh sách tham số chỉ khác kiểu trả về trong cùng interface Java.

Sau khi thay đổi, cần đối chiếu lại:

- Getter được mapping đúng và không thiếu ID.
- Sort vẫn áp dụng trên thuộc tính được yêu cầu.
- Count vẫn phản ánh đúng bộ lọc.
- Truy vấn thực tế có giảm trường dữ liệu như kỳ vọng không.
- Nếu dùng native, đường proxy hoặc khởi tạo projection có được đáp ứng không.

Hỗ trợ interface projection, DTO projection và dynamic projection phải được đánh giá riêng. Không dùng một lần projection thành công để kết luận mọi biến thể đều có tính tương đương giữa hai store.

## 12. Auditing và optimistic locking không tự được mang sang

### 12.1. Auditing

Nếu mở rộng ca sử dụng để ghi `createdBy`, `lastModifiedBy` hoặc thời điểm cập nhật, một số annotation auditing là abstraction dùng chung. Tuy nhiên, cơ chế kích hoạt và tích hợp với persistence vẫn khác nhau.

Phía JPA cần cấu hình auditing JPA và cơ chế listener phù hợp cho entity. Phía MongoDB cần cấu hình auditing MongoDB và callback/mapping tương ứng. Cả hai cần nguồn auditor nếu ghi người thực hiện.

Với fixture hiện tại, `createdAt` được gán cố định để so sánh. Khi thêm auditing, không để thời gian hiện tại vô tình ghi đè fixture làm hai store có dữ liệu khác nhau. Có thể dùng nguồn thời gian kiểm soát được trong kiểm chứng hoặc tách bài kiểm chứng auditing khỏi bài đối chiếu đọc.

### 12.2. Optimistic locking

Nếu bổ sung cập nhật đồng thời, cần chọn annotation version đúng cho từng mô hình:

- Entity JPA dùng `jakarta.persistence.Version`.
- Document MongoDB dùng `org.springframework.data.annotation.Version` theo cơ chế của module.

Không chỉ đổi import rồi mặc định mọi hành vi, giá trị version khởi tạo và lỗi đồng thời giống nhau. Cần định nghĩa kết quả nghiệp vụ khi hai người sửa cùng sản phẩm, sau đó kiểm chứng riêng từng store.

Ca sử dụng đọc trong bài chưa chứng minh tương đương về transaction, locking hoặc ghi nhiều đối tượng.

## 13. Những khác biệt dễ làm kết quả lệch

| Khác biệt | Dấu hiệu | Cách kiểm tra |
| --- | --- | --- |
| Thiếu sort phụ | Hai sản phẩm cùng thời gian đổi vị trí giữa trang | So thứ tự đầy đủ bằng ID trên dataset có giá trị trùng |
| Kiểu ID không đồng nhất | Chuỗi ở một store, `ObjectId` ở store còn lại | Quan sát biểu diễn lưu và mapping ID |
| Độ chính xác timestamp | DTO khác vài phần nhỏ của giây | Chốt độ chính xác chung và so giá trị sau khi đọc lại |
| Thiếu bộ lọc tenant | Xuất hiện `p002` | Đối chiếu đáp án độc lập, không chỉ so hai implementation |
| Enum được biểu diễn khác | Query không khớp dù đối tượng có cùng tên trạng thái | Kiểm tra converter và giá trị lưu thực tế |
| Null hoặc thiếu field | Sort và filter khác với dự kiến | Định nghĩa rõ semantics và thêm fixture cho trường hợp đó |
| Collation khác | Chuỗi có thứ tự hoặc so sánh khác nhau | Chốt collation và tập ký tự thuộc hợp đồng |
| Dữ liệu bị sửa giữa hai lượt đọc | Tổng và nội dung trang lệch | Cố định fixture hoặc thiết kế phép thử đồng thời riêng |
| Quét nhầm repository | Bean không tạo được hoặc gắn sai module | Kiểm tra package, repository gốc và cấu hình module |
| So sánh chỉ trên mock | Mọi assertion qua nhưng query thực tế sai | Dùng kiểm chứng tích hợp với store và mapping thật |

Dữ liệu `null` và field không tồn tại cũng không nên bị coi là đồng nhất mặc định giữa database quan hệ và document database. Ví dụ cơ sở tránh chúng có chủ ý; khi nghiệp vụ cần, phải mô tả riêng hành vi mong muốn.

## 14. Tính ổn định của trang không đồng nghĩa snapshot

Sort theo `createdAt`, `id` tạo một thứ tự xác định cho dataset cố định. Nó không tự tạo snapshot xuyên suốt nhiều request.

Giả sử người dùng đọc trang `0`, sau đó có sản phẩm mới được chèn ở đầu danh sách trước khi họ đọc trang `1`. Offset của các phần tử thay đổi; người dùng có thể thấy trùng hoặc bỏ sót phần tử dù mỗi query đều sort đúng.

Vì vậy cần tách hai yêu cầu:

1. **Thứ tự xác định:** cùng tập dữ liệu có cùng thứ tự.
2. **Duyệt nhất quán khi dữ liệu thay đổi:** cần một thiết kế phù hợp, có thể liên quan cursor, mốc dữ liệu hoặc khả năng transaction/snapshot của store.

Không mở rộng kết luận của bài này sang yêu cầu thứ hai. Nếu cần, bổ sung một ca sử dụng và tiêu chí mới cho cả hai implementation.

## 15. Ghi nhận kết quả đối chiếu

Sau khi thực hành trên dự án thật, báo cáo nên tách từng chiều:

| Hạng mục | Cần ghi |
| --- | --- |
| Hợp đồng | Filter, sort, kiểu kết quả và quy tắc lỗi |
| Môi trường JPA | Phiên bản module, provider, driver, database và cấu hình liên quan |
| Môi trường MongoDB | Phiên bản module, driver, server và mapping liên quan |
| Dataset | ID, enum, timestamp và điều kiện không có ghi đồng thời |
| Kết quả chức năng | Các trang, tổng số phần tử và trường DTO đã đối chiếu |
| Truy vấn | Quan sát SQL/truy vấn document và count nếu có |
| Hiệu năng | Chỉ số đã đo, dataset và giới hạn kết luận |
| Giới hạn | Projection khác loại, auditing, native hoặc ghi đồng thời chưa kiểm chứng |

Có thể dùng ba trạng thái đơn giản cho kết quả thực hành: đã đạt tiêu chí, không đạt tiêu chí hoặc chưa kiểm chứng. Không dùng chữ “tương đương” cho những phần chưa có bằng chứng.

Ví dụ cách kết luận sau một lần chạy giả định:

> Hai implementation cho kết quả đúng với hợp đồng tìm sản phẩm ACTIVE theo tenant trên fixture cố định, bao gồm thứ tự và metadata của Page. Chưa có kết luận về ghi đồng thời, transaction liên store, dynamic projection hoặc native image.

Đây chỉ là mẫu diễn đạt báo cáo, không phải kết quả thực thi của các đoạn mã trong tài liệu này.

## 16. Bài tập mở rộng

### Bài tập 1: Thêm sort do người dùng chọn

Cho phép `name` tăng dần hoặc `createdAt` giảm dần. Xây danh sách lựa chọn hữu hạn và luôn bổ sung ID làm tie-breaker. Chọn collation phù hợp trước khi khẳng định thứ tự tên tiếng Việt tương đương.

### Bài tập 2: Chuyển sang `Slice`

Giả sử giao diện chỉ cần biết còn trang sau, không cần tổng số sản phẩm. Xem module đang dùng hỗ trợ kiểu trả về và query này ra sao, sửa hợp đồng đầu ra rồi đối chiếu `hasNext` trên cùng dataset.

Không giữ assertion tổng số phần tử của `Page` sau khi đã đổi yêu cầu sang `Slice`.

### Bài tập 3: Tối ưu projection

Thay đường tải entity/document đầy đủ bằng projection mà mỗi store hỗ trợ. Giữ hợp đồng `ProductView`, quan sát trường được tải thực tế và chạy lại các tiêu chí chức năng.

### Bài tập 4: Thêm cập nhật có auditing

Định nghĩa thao tác đổi tên sản phẩm, nguồn auditor và kết quả khi hai cập nhật xung đột. Kiểm chứng từng store theo cùng yêu cầu nghiệp vụ, đồng thời ghi rõ những khác biệt về cơ chế persistence.

### Bài tập 5: Đánh giá artifact AOT/native

Cố định tổ hợp phiên bản và build artifact đích cho từng implementation. Kiểm chứng đường query, mapping và projection thực tế. Không chuyển trạng thái “đã chạy JVM” thành “đã chạy native” nếu chưa có lần thực thi tương ứng.

## 17. Câu hỏi tự kiểm tra

1. Vì sao tên derived query giống nhau chưa chứng minh hai repository tương đương?
2. Vì sao fixture cần có hai sản phẩm cùng `createdAt`?
3. Tại sao chọn ID chuỗi do ứng dụng gán cho bài đối chiếu cơ sở?
4. `Page.map` có bảo đảm database chỉ tải các trường của DTO không?
5. Vì sao phải kiểm tra từng implementation với đáp án độc lập trước khi so chúng với nhau?
6. Một thứ tự có tie-breaker có giải quyết việc dữ liệu thay đổi giữa hai request phân trang không?
7. Phần nào có thể dùng chung và phần nào cần riêng cho store?

### Gợi ý trả lời

1. Query translation, mapping, kiểu dữ liệu và khả năng của store có thể khác nhau; cần kiểm tra hành vi quan sát được.
2. Để phát hiện thiếu tiêu chí sort phụ và chứng minh thứ tự đúng trong trường hợp hòa.
3. Để loại bỏ khác biệt cơ chế sinh ID khỏi phép so sánh, giúp cùng dữ liệu có cùng định danh.
4. Không. Trong ví dụ cơ sở, nó chuyển nội dung trang ở ứng dụng sau khi repository trả entity/document.
5. Hai implementation có thể mắc cùng một lỗi; bằng nhau chưa có nghĩa đúng nghiệp vụ.
6. Không. Tie-breaker giải quyết thứ tự cho tập dữ liệu đã xét, không tự tạo snapshot xuyên request.
7. Có thể dùng chung hợp đồng ca sử dụng, DTO, quy tắc input, Pageable/Sort và tiêu chí kiểm chứng; mapping, repository gốc, cấu hình, query vật lý, index và cơ chế transaction cần xét theo store.

## 18. Kết quả học tập cần đạt

Sau bài này, bạn cần chỉ ra được một ranh giới cụ thể: **abstraction chung giúp giữ ổn định cách gọi và diễn đạt yêu cầu; tính tương đương phải được xác nhận bằng hợp đồng và dữ liệu trên từng store**.

Một bài đối chiếu đạt yêu cầu có hai implementation đúng cùng nghiệp vụ, giải thích được phần khác nhau trong persistence và nêu rõ phạm vi đã kiểm chứng. Nó không cần làm hai hệ lưu trữ trở nên giống nhau về mọi cơ chế bên trong.
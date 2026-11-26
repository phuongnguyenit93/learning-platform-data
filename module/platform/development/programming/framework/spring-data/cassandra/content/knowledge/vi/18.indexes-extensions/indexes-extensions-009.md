# Phạm vi annotation và API tìm kiếm nâng cao của Spring Data

Trong **Spring Data Cassandra**, các annotation như `@Table`, `@PrimaryKey`, `@Column` và `@Indexed` giúp mô tả cách ánh xạ object Java sang bảng và cột CQL. Repository, `@Query`, `CassandraTemplate`, `CqlTemplate` và Java Driver giúp gửi các câu truy vấn. Tuy nhiên, **có API để biểu diễn điều kiện tìm kiếm không có nghĩa Apache Cassandra có thể thực thi điều kiện đó một cách hiệu quả**.

Bài học thuộc chương **Chỉ mục và mở rộng** của module **SPRING_DATA_CASSANDRA**. Trọng tâm là **phạm vi của annotation và các API tìm kiếm nâng cao trong Spring Data Cassandra**, không đồng nhất chúng với những tính năng của Spring Data Elasticsearch, MongoDB hoặc cơ sở dữ liệu SQL. Chúng ta sẽ đối chiếu metadata Java với schema thật, phân biệt index và bảng truy cập theo truy vấn, áp dụng repository/template cho những câu CQL hợp lệ và xác định khi nào cần tìm kiếm chuyên dụng.

Kết thúc bài, bạn có thể:

1. Giải thích `@Indexed` hỗ trợ mô tả metadata gì và **không** tự bảo đảm những gì ở cluster.
2. Phân biệt **partition key**, **clustering columns**, **secondary index**, **Storage-Attached Index (SAI)** và **SASI** theo khả năng của phiên bản Cassandra cụ thể.
3. Chọn giữa `CassandraRepository`, `@Query`, `CassandraTemplate`, `CqlTemplate` và `CqlSession` cho một truy vấn cần kiểm soát.
4. Nhận diện bộ lọc trên cột thường, truy vấn collection, tìm kiếm văn bản và các điều kiện không phù hợp với mô hình khóa.
5. Kiểm tra schema/index vật lý, CQL thực tế và chi phí thực thi bằng integration test cùng dữ liệu đại diện.

> **Nguyên tắc:** Spring Data là **lớp truy cập dữ liệu**, còn Cassandra mới quyết định những đường truy cập nào được hỗ trợ. Annotation và method name không thay đổi thuật toán phân bố dữ liệu theo partition key.

## 1. Phân biệt năm lớp trách nhiệm

~~~text
Yêu cầu sản phẩm
    |
    v
Access pattern: đọc theo ID, category, status, tên, tag?
    |
    v
Thiết kế CQL: partition key, clustering key, index, read model
    |
    v
Spring Data: @Table/@Column/@Indexed, repository, @Query, template
    |
    v
Java Driver: CqlSession, bind markers, consistency, paging
    |
    v
Apache Cassandra: schema vật lý, replica, index, giới hạn CQL
~~~

| Lớp | Quyết định điều gì? | Không làm được |
|---|---|---|
| Access pattern | API cần tìm gì, giới hạn dữ liệu nào, sort/paging ra sao | Không tự tạo truy vấn CQL |
| Bảng và primary key CQL | Dữ liệu nằm ở partition nào, sắp xếp ra sao | Không tự tìm kiếm tự do mọi cột |
| Index/extension Cassandra | Hỗ trợ thêm các phép lọc theo khả năng index thực tế | Không bảo đảm mọi truy vấn đều nhanh hoặc phân trang rẻ |
| Annotation và Spring Data API | Ánh xạ entity, dựng/bind câu CQL, chuyển kết quả sang Java | Không tự sửa index production hay phá quy tắc Cassandra |
| Driver/vận hành | Timeout, retry, consistency, paging và kết nối | Không khắc phục sai lầm về mô hình dữ liệu |

Một câu hỏi kỹ thuật tốt là: **“CQL được tạo cuối cùng sẽ đọc những partition nào, bằng khóa hoặc index nào, và tốn bao nhiêu tài nguyên?”** Câu hỏi “có annotation nào để tìm theo field này?” chỉ là bước phụ.

## 2. Ví dụ nghiệp vụ: tra sản phẩm theo ID, danh mục và văn bản

Giả sử một ứng dụng thương mại điện tử cần:

~~~text
GET /tenants/{tenantId}/products/{productId}
GET /tenants/{tenantId}/categories/{category}/products?limit=20
GET /tenants/{tenantId}/products?status=ACTIVE
GET /tenants/{tenantId}/products/search?q=wireless+mouse
~~~

Đây là **bốn access patterns khác nhau**. Cần phân biệt:

- Tra một sản phẩm theo ID thường là **point read** với đầy đủ partition key.
- Liệt kê sản phẩm trong một danh mục có thể dùng **bảng đọc riêng** theo `(tenant_id, category)`, hỗ trợ clustering order và paging.
- Lọc sản phẩm theo trạng thái là truy vấn có thể làm bằng read model hoặc index **nếu** index phù hợp, hỗ trợ điều kiện và có chi phí chấp nhận được.
- Tìm kiếm tên tự do, sửa lỗi chính tả, xếp hạng theo relevance hoặc tìm gần đúng thường cần một **năng lực tìm kiếm chuyên dụng**, không thể suy ra chỉ từ `@Indexed`.

### 2.1. Bảng gốc để đọc theo ID

~~~sql
CREATE TABLE catalog_products_by_id (
    tenant_id uuid,
    product_id uuid,
    sku text,
    product_name text,
    category text,
    status text,
    tags set<text>,
    created_at timestamp,
    PRIMARY KEY ((tenant_id, product_id))
);
~~~

Ở bảng này:

| Cột | Loại | Ý nghĩa |
|---|---|---|
| `tenant_id` | Partition key, vị trí 0 | Định danh tenant |
| `product_id` | Partition key, vị trí 1 | Định danh sản phẩm trong tenant |
| `category` | Cột thường | Dữ liệu để hiển thị, **không phải khóa đọc** |
| `status` | Cột thường | Trạng thái kinh doanh |
| `product_name` | Cột thường | Tên có thể cần chức năng tìm kiếm riêng |
| `tags` | `set<text>` | Tập nhãn nhỏ, không có thứ tự chèn |
| `created_at` | Cột thường | Không được `ORDER BY` tùy ý với schema này |

Point read hợp lệ:

~~~sql
SELECT sku, product_name, category, status, tags, created_at
FROM catalog_products_by_id
WHERE tenant_id = ? AND product_id = ?;
~~~

Cassandra dùng **cả hai thành phần partition key**. Nếu chỉ có `tenant_id`, query không xác định một partition; nếu chỉ có `category`, bảng cũng không có đường đọc theo category. Đây là lý do cần thiết kế index hoặc bảng đọc khác **trước** khi viết `findByCategory`.

## 3. Phạm vi từng annotation thường gặp trong Spring Data Cassandra

| Annotation | Đặt trên | Công dụng chính | Có tự tạo tìm kiếm toàn văn/secondary index không? |
|---|---|---|---|
| `@Table` | Class entity | Ánh xạ bảng CQL | Không |
| `@PrimaryKey` | Field ID | Khai báo khóa đơn hoặc object chứa khóa | Không; khóa phải khớp schema |
| `@PrimaryKeyClass` | Class khóa ghép | Mô tả object primary key | Không |
| `@PrimaryKeyColumn` | Field của class khóa | `PARTITIONED`/`CLUSTERED`, thứ tự khóa | Không |
| `@Column` | Field thông thường | Ánh xạ tên cột CQL | Không |
| `@Indexed` | Field được mapping | Khai báo **metadata chỉ mục** cho đường tạo schema được hỗ trợ | **Không bảo đảm** index đã tồn tại hoặc được chọn khi chạy |
| `@CassandraType` | Field cần kiểu CQL rõ ràng | Mô tả kiểu CQL cụ thể | Không |
| `@Frozen` | Field collection/UDT thích hợp | Biểu diễn kiểu frozen theo schema | Không |
| `@Query` | Method repository | Chỉ định câu **CQL** tường minh | Không |

Trong một số phiên bản Spring Data Cassandra có annotation/khả năng khai báo **SASI** hoặc các tính năng mapping nâng cao. Chúng là **tính năng theo phiên bản và loại Cassandra**, không nên giả định sẽ hoạt động trên mọi cluster. **SAI, SASI và legacy secondary index không phải ba tên gọi đồng nghĩa**; chọn loại nào phải dựa trên server/driver/Spring Data đang triển khai.

Đặc biệt, `@Indexed` không phải `@Index` của một framework JPA tùy ý, cũng không phải `@TextIndexed` của Spring Data MongoDB hoặc annotation dùng cho Elasticsearch. Các module Spring Data chia sẻ một số khái niệm repository, nhưng **không chia sẻ toàn bộ API truy vấn và index backend**.

### 3.1. Metadata annotation và schema vật lý là hai thứ khác nhau

Giả sử Java có:

~~~java
@Indexed
@Column("category")
private String category;
~~~

Điều này biểu thị **ý định khai báo index trong mapping metadata**. Tùy phiên bản và chế độ schema management, framework có thể dùng metadata để sinh DDL; nhưng nó **không tự bảo đảm**:

- Cassandra production đã có index tương ứng.
- Index mới là **SAI** thay vì secondary index cổ điển.
- Một index trên `category` làm `WHERE tenant_id = ? AND category = ?` hiệu quả.
- Index hỗ trợ tìm kiếm prefix, substring, typo hoặc relevance ranking.
- Bảng đang có sẽ được **migrate tự động** khi thêm annotation.

Nếu bảng đã tồn tại và `spring.cassandra.schema-action: NONE`, thêm `@Indexed` trong code **không phải một migration**. Muốn tạo/sửa index ở production, sử dụng DDL được phê duyệt theo đúng engine/version; sau đó đọc lại `system_schema.indexes` và kiểm chứng truy vấn.

## 4. Mapping Java có @Indexed: hiểu đúng và không lạm dụng

Đối tượng khóa ghép của `catalog_products_by_id`:

~~~java
package example.catalog;

import java.io.Serializable;
import java.util.Objects;
import java.util.UUID;

import org.springframework.data.cassandra.core.cql.PrimaryKeyType;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;

@PrimaryKeyClass
public class ProductIdKey implements Serializable {

    private static final long serialVersionUID = 1L;

    @PrimaryKeyColumn(name = "tenant_id", ordinal = 0,
            type = PrimaryKeyType.PARTITIONED)
    private UUID tenantId;

    @PrimaryKeyColumn(name = "product_id", ordinal = 1,
            type = PrimaryKeyType.PARTITIONED)
    private UUID productId;

    public ProductIdKey() {}

    public ProductIdKey(UUID tenantId, UUID productId) {
        this.tenantId = tenantId;
        this.productId = productId;
    }

    public UUID getTenantId() { return tenantId; }
    public void setTenantId(UUID value) { tenantId = value; }
    public UUID getProductId() { return productId; }
    public void setProductId(UUID value) { productId = value; }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof ProductIdKey)) return false;
        ProductIdKey that = (ProductIdKey) other;
        return Objects.equals(tenantId, that.tenantId)
                && Objects.equals(productId, that.productId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(tenantId, productId);
    }
}
~~~

Entity có annotation:

~~~java
package example.catalog;

import java.time.Instant;
import java.util.Set;

import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.Indexed;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("catalog_products_by_id")
public class CatalogProduct {

    @PrimaryKey
    private ProductIdKey id;

    @Column("sku")
    private String sku;

    @Column("product_name")
    private String productName;

    @Indexed
    @Column("category")
    private String category;

    @Column("status")
    private String status;

    @Column("tags")
    private Set<String> tags;

    @Column("created_at")
    private Instant createdAt;

    public CatalogProduct() {}

    public ProductIdKey getId() { return id; }
    public void setId(ProductIdKey value) { id = value; }
    public String getSku() { return sku; }
    public void setSku(String value) { sku = value; }
    public String getProductName() { return productName; }
    public void setProductName(String value) { productName = value; }
    public String getCategory() { return category; }
    public void setCategory(String value) { category = value; }
    public String getStatus() { return status; }
    public void setStatus(String value) { status = value; }
    public Set<String> getTags() { return tags; }
    public void setTags(Set<String> value) { tags = value; }
    public Instant getCreatedAt() { return createdAt; }
    public void setCreatedAt(Instant value) { createdAt = value; }
}
~~~

`@Indexed` ở field `category` **không thay đổi** `ProductIdKey`. Repository `findById(new ProductIdKey(tenantId, productId))` vẫn là đường truy cập trực tiếp theo khóa. Một repository method `findByCategory(...)` có thể được Spring Data phân tích tên, nhưng việc Cassandra thực thi được và có phù hợp với yêu cầu tenant/paging hay không phải kiểm chứng riêng.

Lưu ý kiểu `Instant` ánh xạ CQL `timestamp` với độ chính xác mili giây; `Set<String>` ánh xạ `set<text>` và không giữ thứ tự thêm phần tử. Annotation index không sửa những quy tắc chuyển đổi dữ liệu đó.

## 5. Chỉ mục trong Cassandra: 2i, SAI, SASI và giới hạn

**Index là cấu trúc truy cập bổ sung do Cassandra quản lý**, khác với primary key. Các họ index có khả năng và lịch sử khác nhau. Việc một tài liệu đề cập `CREATE INDEX`, `CREATE CUSTOM INDEX` hoặc `USING 'sai'` **không có nghĩa mọi cú pháp đều chạy trên mọi server**.

### 5.1. Legacy secondary index (2i)

Secondary index truyền thống có thể hỗ trợ truy vấn theo một cột không thuộc primary key trong một số điều kiện. Ví dụ DDL minh họa:

~~~sql
-- DDL minh họa chỉ mục thứ cấp kiểu truyền thống.
-- Hãy đối chiếu cú pháp và loại index hiệu lực trên phiên bản server.
CREATE INDEX catalog_products_category_idx
ON catalog_products_by_id (category);
~~~

Nếu môi trường tạo được index hỗ trợ phép bằng trên `category`, truy vấn sau có thể được server chấp nhận:

~~~sql
SELECT product_id, product_name, category
FROM catalog_products_by_id
WHERE category = 'peripherals';
~~~

**Nhưng** category có thể là giá trị có độ chọn lọc thấp (“peripherals” xuất hiện ở hàng triệu sản phẩm); truy vấn có thể phải làm việc qua nhiều node/partition. Đặc biệt nếu API thật cần **lọc theo tenant, sort mới nhất và phân trang**, chỉ có một index `category` không bảo đảm toàn bộ hợp đồng ấy được hỗ trợ/hiệu quả.

Vì vậy, đừng đánh giá index chỉ bằng câu hỏi “CQL có chạy không?”. Cần đo số dữ liệu được đọc, phân bố giá trị, fan-out, độ trễ và chi phí ghi index.

### 5.2. Storage-Attached Index (SAI)

**SAI** là cơ chế index được hỗ trợ trong một số phiên bản/nền tảng Cassandra hiện đại. SAI có thiết kế và khả năng lọc khác với legacy 2i; một số môi trường hỗ trợ phép truy vấn linh hoạt hơn trên các trường được index.

Tuy nhiên, trước khi dùng:

1. Xác nhận phiên bản Apache Cassandra và bản phân phối/managed service thực tế **có hỗ trợ SAI**.
2. Xác nhận cú pháp DDL của **đúng môi trường** (một số ví dụ sử dụng `USING 'sai'`, môi trường khác có cú pháp/hạn chế khác).
3. Kiểm tra hỗ trợ của kiểu cột, toán tử `=`/`IN`/`CONTAINS`/`LIKE`, số index được kết hợp và các giới hạn phiên bản.
4. Đo chi phí tạo index, write amplification, compaction, selectivity và hiệu năng khi kết quả lớn.
5. Dùng migration và test thực tế; không suy ra SAI sẽ được tạo đúng chỉ vì field Java có `@Indexed`.

**SAI không phải search engine tổng quát**. Nếu nghiệp vụ yêu cầu ranking theo relevance, autocomplete, typo tolerance, stemming phức tạp hoặc phân tích ngôn ngữ đa dạng, cần xem khả năng thực tế của bản phân phối hoặc một hệ tìm kiếm chuyên biệt.

### 5.3. SASI và các extension tùy phiên bản

**SASI (SSTable-Attached Secondary Index)** là một cơ chế index tồn tại ở những hệ sinh thái/phiên bản Cassandra nhất định. Một số phiên bản Spring Data Cassandra có metadata/annotation liên quan SASI; nhưng **không nên coi SASI là lựa chọn mặc định cho thiết kế mới** hoặc giả định nó hiện diện trên mọi cluster.

Nếu gặp tài liệu/blog sử dụng annotation SASI hoặc CQL `CREATE CUSTOM INDEX`:

- Xác minh phiên bản Cassandra, tình trạng hỗ trợ và khả năng vận hành hiện tại.
- Kiểm tra cú pháp `LIKE`, tokenization và các chế độ index được backend thực sự hỗ trợ.
- Đọc cảnh báo về trạng thái tính năng (experimental/deprecated nếu áp dụng cho môi trường cụ thể).
- Ưu tiên index được nhà cung cấp hỗ trợ chính thức hoặc **bảng truy cập theo truy vấn** khi đáp ứng tốt hơn.

Không tự chuyển đoạn code có `@SASI` sang `@Indexed` rồi khẳng định kết quả tìm kiếm tương đương.

### 5.4. Bảng so sánh theo nhu cầu

| Nhu cầu | Primary key/read model | 2i truyền thống | SAI / extension | Search engine |
|---|---|---|---|---|
| Tra đúng một sản phẩm theo tenant + ID | **Phù hợp nhất** | Không cần | Không cần | Không cần |
| Liệt kê sản phẩm một danh mục, có sort và paging ổn định | **Rất phù hợp** | Cần benchmark; thường không thay thế sort theo clustering | Cần kiểm tra khả năng và tải | Có thể, tùy SLA |
| Lọc có chọn lọc theo cột ngoài khóa | Cần thêm bảng nếu query quan trọng | Có thể theo giới hạn | Có thể theo capability cụ thể | Có thể |
| Tìm giá trị bên trong `set/map` | Bảng đảo nếu query thường xuyên | Phụ thuộc index collection | Phụ thuộc loại index/operator | Có thể |
| Full-text, fuzzy, relevance, autocomplete | Không phải thế mạnh mặc định | Không | Phụ thuộc backend; không mặc nhiên đầy đủ | **Thường phù hợp hơn** |
| Truy vấn lớn cần phân tích nhiều tenant | Thiết kế ETL/read model | Không nên kỳ vọng thay data warehouse | Chỉ khi đã chứng minh | Hệ thống phân tích/search phù hợp |

Bảng trên là **khung lựa chọn**, không phải cam kết hỗ trợ toán tử. Quyết định cuối cùng dựa trên schema, version, lượng dữ liệu và benchmark.

## 6. Điều kiện WHERE hợp lệ không do tên repository quyết định

Với `catalog_products_by_id`, thử phân loại:

| CQL muốn thực thi | Đường truy cập | Đánh giá |
|---|---|---|
| `WHERE tenant_id=? AND product_id=?` | Đầy đủ partition key | Tốt cho point read |
| `WHERE product_id=?` | Thiếu thành phần tenant của partition key | Không phải point read chuẩn |
| `WHERE category=?` | Cột thường | Chỉ khi có index/access path phù hợp |
| `WHERE tenant_id=? AND category=?` | Thiếu một phần partition key, cộng filter cột thường | Không suy ra hợp lệ/chạy nhanh chỉ từ index đơn cột |
| `WHERE status=?` | Cột thường | Cần đường truy cập được thiết kế riêng |
| `ORDER BY created_at DESC` | `created_at` không phải clustering | Không phải sort CQL phù hợp với bảng này |
| `WHERE tags CONTAINS ?` | Phép lọc collection | Cần index hỗ trợ toán tử hoặc bảng đảo |
| Tìm tên gần đúng, xếp hạng | Ngoài semantics primary key thông thường | Chọn backend có chức năng tìm kiếm thích hợp |

**Không dùng `ALLOW FILTERING` như cách chữa mặc định**. Nó có thể cho phép Cassandra xử lý một số câu truy vấn bằng lọc dữ liệu nhiều hơn, nhưng không tạo đường truy cập hợp lý, có thể đọc nhiều node/partition và khiến latency khó dự đoán.

### 6.1. Có index vẫn phải hiểu giới hạn của index

Giả sử index hỗ trợ `WHERE category = 'peripherals'`. Nếu ứng dụng muốn:

~~~text
GET /tenants/{tenantId}/categories/peripherals/products
   ?sort=createdAt,desc&pageSize=20
~~~

thì điều kiện tenant, sort theo thời điểm và paging có ý nghĩa nghiệp vụ riêng. **Không thể mặc định** một index chỉ trên `category` đáp ứng toàn bộ. Nên cân nhắc **bảng truy cập theo tenant/category**, chứa dữ liệu cần hiển thị và clustering key phục vụ thứ tự mong muốn.

## 7. Repository và derived queries: API không tạo index

Repository cho bảng theo ID:

~~~java
package example.catalog;

import org.springframework.data.cassandra.repository.CassandraRepository;

public interface CatalogProductRepository
        extends CassandraRepository<CatalogProduct, ProductIdKey> {
}
~~~

Đường CRUD phù hợp:

~~~java
ProductIdKey key = new ProductIdKey(tenantId, productId);
Optional<CatalogProduct> product = repository.findById(key);
~~~

`findById` sử dụng metadata `@PrimaryKeyClass` và đủ hai thành phần khóa. Đây là lựa chọn mặc định cho API tra một sản phẩm.

Nếu bạn thêm:

~~~java
// Chỉ là tên phương thức có thể được parser nhận biết.
// KHÔNG đủ bằng chứng rằng Cassandra sẽ xử lý hiệu quả.
List<CatalogProduct> findByCategory(String category);
~~~

Spring Data có thể phân tích property `category` và tạo CQL tương ứng, nhưng:

- Bảng phải có index/access path cho `category`; `@Indexed` không phải bằng chứng index đã được deploy.
- Phương thức **không mang tenantId**, nên có nguy cơ không khớp hợp đồng phân quyền hoặc trả dữ liệu của nhiều tenant.
- Nếu kết quả rất lớn, `List` có thể materialize dữ liệu không giới hạn; cần phân trang đúng query.
- Nếu muốn sort `created_at`, schema/index thực tế phải hỗ trợ, không thể tùy tiện truyền `Sort`.

Khi method không thể phân tích property, có thể gặp `PropertyReferenceException` lúc tạo repository. Khi method parse được nhưng CQL sai đường khóa, có thể gặp `InvalidQueryException` từ driver/server khi thực thi. Đây là **hai tầng lỗi khác nhau**.

## 8. @Query: viết CQL rõ ràng nhưng không vượt giới hạn schema

`@Query` của **Spring Data Cassandra** là cách chỉ định **CQL** tường minh:

~~~java
import java.util.List;
import java.util.UUID;

import org.springframework.data.cassandra.repository.Query;

public interface CatalogProductRepository
        extends CassandraRepository<CatalogProduct, ProductIdKey> {

    @Query("SELECT * FROM catalog_products_by_id " +
           "WHERE tenant_id = ?0 AND product_id = ?1")
    CatalogProduct findExact(UUID tenantId, UUID productId);
}
~~~

Đoạn code minh họa cách bind hai giá trị; có thể dùng `Optional<CatalogProduct>` cho nghiệp vụ cho phép không tồn tại và xác minh kiểu trả về phù hợp phiên bản Spring Data đang dùng. Câu CQL hợp lệ vì đầy đủ partition key.

Ngược lại:

~~~java
// Câu lệnh này CHỈ có thể chạy khi Cassandra đã có
// index/access path phù hợp cho category trong schema thật.
@Query("SELECT * FROM catalog_products_by_id WHERE category = ?0")
List<CatalogProduct> findByCategoryWithIndex(String category);
~~~

`@Query` **không tự tạo index**, không bảo đảm chọn replica hiệu quả, không bỏ qua quyền truy cập tenant và không tự giới hạn một tập kết quả rất lớn. Để dùng code trên cho production phải đánh giá vấn đề multi-tenant, index và số lượng kết quả trước.

### 8.1. Khi nào @Query đáng dùng?

`@Query` phù hợp khi:

- Muốn kiểm soát rõ **các cột được SELECT**, bind markers và giới hạn kết quả.
- Muốn tránh nhập nhằng của tên method với khóa ghép/property nested.
- Muốn dùng câu CQL ổn định đã được kiểm thử với index/access table.
- Cần `CONTAINS`, `IN` hoặc điều kiện đặc biệt mà parser derived method không thể diễn đạt rõ ràng (sau khi **xác minh backend hỗ trợ**).

Nó **không** biến `LIKE '%mouse%'` thành truy vấn full-text có ranking. Việc có toán tử CQL trong một phiên bản không có nghĩa nó tương đương một API search engine.

## 9. CassandraTemplate và Query/Criteria: điều kiện động nhưng có kiểm soát

`CassandraTemplate` (thông qua `CassandraOperations`) giúp dựng CQL từ `Query` và `Criteria`, phù hợp khi các nhánh lọc được **whitelist** theo access pattern đã thiết kế.

Ví dụ point read hợp lệ:

~~~java
import java.util.UUID;

import org.springframework.data.cassandra.core.CassandraOperations;
import org.springframework.data.cassandra.core.query.Criteria;
import org.springframework.data.cassandra.core.query.Query;

public CatalogProduct findProduct(
        CassandraOperations operations,
        UUID tenantId, UUID productId) {

    Query query = Query.query(
            Criteria.where("tenant_id").is(tenantId))
            .and(Criteria.where("product_id").is(productId));

    return operations.selectOne(query, CatalogProduct.class);
}
~~~

Trong Spring Data Cassandra, `Query/Criteria` là **DSL biểu diễn CQL**, không phải một engine thực thi truy vấn client-side. Nếu thêm:

~~~java
// Không nên tự động thêm bộ lọc không có access path.
query.and(Criteria.where("category").is(requestedCategory));
~~~

thì câu CQL phải được Cassandra hỗ trợ trên schema thật. Các biến `query` và `requestedCategory` trong ví dụ là thuộc service; khi triển khai cần kiểm tra khả năng API với phiên bản thư viện. **Không chấp nhận mọi field/filter do client cung cấp rồi tự động thêm vào `Criteria`**.

### 9.1. Truy vấn từ bảng đọc chuyên dụng

Giả sử ứng dụng tạo bảng `products_by_tenant_category` (phần 11) để đọc theo category, khi đó Query/Criteria có thể biểu diễn đầy đủ partition key mới:

~~~java
Query query = Query.query(
        Criteria.where("tenant_id").is(tenantId))
        .and(Criteria.where("category").is(category))
        .limit(20);

List<ProductByCategory> products =
        operations.select(query, ProductByCategory.class);
~~~

`ProductByCategory` là entity **riêng** ánh xạ bảng đọc theo category; không sử dụng `CatalogProduct.class` để truy vấn sai bảng. Với phân trang dài, nên dùng `operations.slice(query.pageRequest(pageable), ProductByCategory.class)` thay vì tải mọi hàng vào `List`.

### 9.2. Không có "OR" tùy ý như một bộ tìm kiếm SQL tổng quát

Cassandra CQL chỉ hỗ trợ các tổ hợp toán tử phù hợp với version, index và khóa. Việc `Criteria` có thể diễn đạt một điều kiện nào đó trong Java **không bảo đảm** server hỗ trợ tổ hợp đó.

Ví dụ người dùng muốn `category = A OR status = ACTIVE`, sort theo `created_at` trên toàn bộ tenant: đây không phải truy vấn mặc định được giải quyết bằng `Query` hoặc secondary index một cột. Cần phân tích mức chọn lọc, thiết kế read model, index kết hợp (nếu backend hỗ trợ) hoặc dịch vụ search.

## 10. CqlTemplate và CqlSession khi cần CQL/driver tùy biến

`CqlTemplate` là tầng CQL thấp hơn `CassandraTemplate`, thích hợp khi muốn tự viết statement, bind tham số và ánh xạ `Row`.

~~~java
import java.util.UUID;
import org.springframework.data.cassandra.core.cql.CqlOperations;

public String findProductName(
        CqlOperations cql, UUID tenantId, UUID productId) {

    return cql.queryForObject(
            "SELECT product_name FROM catalog_products_by_id " +
            "WHERE tenant_id = ? AND product_id = ?",
            String.class,
            tenantId, productId);
}
~~~

Đoạn code minh họa phương thức trong DAO/service, cần xử lý tình huống không có hàng theo contract; một số overload `queryForObject` có thể ném ngoại lệ nếu không đúng một hàng. Nếu muốn tránh giả định số hàng, sử dụng `query(String, RowMapper<T>, Object...)` và chuyển kết quả thành `Optional` một cách rõ ràng.

Ví dụ Java Driver `CqlSession`:

~~~java
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public Row findRaw(CqlSession session,
        UUID tenantId, UUID productId) {

    PreparedStatement ps = session.prepare(
            "SELECT product_name, category, status " +
            "FROM catalog_products_by_id " +
            "WHERE tenant_id = ? AND product_id = ?");

    return session.execute(ps.bind(tenantId, productId)).one();
}
~~~

Với truy vấn gọi thường xuyên, nên giữ `PreparedStatement` theo vòng đời DAO/session thay vì prepare trong mỗi request. `Row` không được tự động chuyển thành entity như qua `CassandraTemplate`; code cần đọc cột và chuyển kiểu một cách tường minh.

**Giới hạn chung:** `CqlSession` có API mạnh hơn về timeout, consistency và paging state, nhưng không vượt các quy tắc về index, partition key và toán tử CQL.

## 11. Bảng truy cập theo category: giải pháp thay index cho một API quan trọng

Nếu API sản phẩm cần “20 sản phẩm mới nhất trong một danh mục của một tenant”, với paging theo thứ tự tạo, hãy thiết kế bảng:

~~~sql
CREATE TABLE products_by_tenant_category (
    tenant_id uuid,
    category text,
    created_at timestamp,
    product_id uuid,
    product_name text,
    status text,
    PRIMARY KEY (
        (tenant_id, category),
        created_at, product_id
    )
) WITH CLUSTERING ORDER BY (created_at DESC, product_id ASC);
~~~

Ở đây, **partition key** là `(tenant_id, category)`; `created_at` và `product_id` là **clustering columns**. Truy vấn:

~~~sql
SELECT tenant_id, category, created_at,
       product_id, product_name, status
FROM products_by_tenant_category
WHERE tenant_id = ? AND category = ?;
~~~

Ưu điểm:

- Cassandra định vị đúng **một partition** qua tenant/category.
- `created_at DESC` phục vụ thứ tự tự nhiên cho danh sách mới nhất.
- `product_id` phá hòa khi có các sản phẩm cùng timestamp.
- Driver và Spring Data có thể phân trang các **hàng** theo paging state.
- Không cần index trên cột thường chỉ để phục vụ đúng query contract này.

Đánh đổi:

- Khi tạo sản phẩm, phải ghi cả `catalog_products_by_id` và bảng đọc category.
- Nếu sản phẩm đổi category, phải xử lý xóa hàng ở category cũ và ghi sang category mới.
- Dữ liệu trong hai bảng **không tự** có transaction ACID xuyên bảng.
- Nếu một category trong một tenant quá lớn hoặc quá nóng, partition có thể cần time bucket/shard theo phân phối thật, với chi phí đọc nhiều partition.

### 11.1. Entity và repository riêng cho read model

`products_by_tenant_category` có khóa ghép riêng; không thể thay tên bảng rồi dùng lại `ProductIdKey` vì thành phần khóa khác nhau. Một entity thích hợp:

~~~java
package example.catalog;

import java.io.Serializable;
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

import org.springframework.data.cassandra.core.cql.Ordering;
import org.springframework.data.cassandra.core.cql.PrimaryKeyType;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.Table;

@PrimaryKeyClass
public class ProductByCategoryKey implements Serializable {
    private static final long serialVersionUID = 1L;

    @PrimaryKeyColumn(name = "tenant_id", ordinal = 0,
            type = PrimaryKeyType.PARTITIONED)
    private UUID tenantId;

    @PrimaryKeyColumn(name = "category", ordinal = 1,
            type = PrimaryKeyType.PARTITIONED)
    private String category;

    @PrimaryKeyColumn(name = "created_at", ordinal = 2,
            type = PrimaryKeyType.CLUSTERED,
            ordering = Ordering.DESCENDING)
    private Instant createdAt;

    @PrimaryKeyColumn(name = "product_id", ordinal = 3,
            type = PrimaryKeyType.CLUSTERED,
            ordering = Ordering.ASCENDING)
    private UUID productId;

    public ProductByCategoryKey() {}
    public ProductByCategoryKey(UUID tenantId, String category,
            Instant createdAt, UUID productId) {
        this.tenantId = tenantId;
        this.category = category;
        this.createdAt = createdAt;
        this.productId = productId;
    }

    public UUID getTenantId() { return tenantId; }
    public void setTenantId(UUID value) { tenantId = value; }
    public String getCategory() { return category; }
    public void setCategory(String value) { category = value; }
    public Instant getCreatedAt() { return createdAt; }
    public void setCreatedAt(Instant value) { createdAt = value; }
    public UUID getProductId() { return productId; }
    public void setProductId(UUID value) { productId = value; }

    @Override
    public boolean equals(Object value) {
        if (this == value) return true;
        if (!(value instanceof ProductByCategoryKey)) return false;
        ProductByCategoryKey other = (ProductByCategoryKey) value;
        return Objects.equals(tenantId, other.tenantId)
                && Objects.equals(category, other.category)
                && Objects.equals(createdAt, other.createdAt)
                && Objects.equals(productId, other.productId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(tenantId, category, createdAt, productId);
    }
}

@Table("products_by_tenant_category")
public class ProductByCategory {
    @PrimaryKey
    private ProductByCategoryKey id;

    @Column("product_name")
    private String productName;

    @Column("status")
    private String status;

    public ProductByCategory() {}
    public ProductByCategory(ProductByCategoryKey id,
            String productName, String status) {
        this.id = id;
        this.productName = productName;
        this.status = status;
    }

    public ProductByCategoryKey getId() { return id; }
    public void setId(ProductByCategoryKey value) { id = value; }
    public String getProductName() { return productName; }
    public void setProductName(String value) { productName = value; }
    public String getStatus() { return status; }
    public void setStatus(String value) { status = value; }
}
~~~

Hai class trên phải được **tách thành hai file Java public riêng** khi triển khai. `ordinal` trên toàn bộ khóa chạy từ 0 đến 3. Với CQL `timestamp`, giữ `created_at` ổn định và chuẩn hóa độ chính xác mili giây khi tạo khóa; không thay các thành phần primary key sau khi ghi.

Repository đọc theo partition mới:

~~~java
import java.util.UUID;

import org.springframework.data.cassandra.repository.CassandraRepository;
import org.springframework.data.cassandra.repository.Query;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;

public interface ProductByCategoryRepository
        extends CassandraRepository<
                ProductByCategory, ProductByCategoryKey> {

    @Query("SELECT * FROM products_by_tenant_category " +
           "WHERE tenant_id = ?0 AND category = ?1")
    Slice<ProductByCategory> findByTenantAndCategory(
            UUID tenantId, String category, Pageable pageable);
}
~~~

Lấy trang đầu, tiếp tục bằng cursor:

~~~java
import org.springframework.data.cassandra.core.query.CassandraPageRequest;
import org.springframework.data.domain.Slice;

Slice<ProductByCategory> first =
        repository.findByTenantAndCategory(
                tenantId, "peripherals",
                CassandraPageRequest.first(20));

if (first.hasNext()) {
    Slice<ProductByCategory> second =
            repository.findByTenantAndCategory(
                    tenantId, "peripherals",
                    first.nextPageable());
}
~~~

Đây là trang theo **một partition tenant/category**; không dùng paging state của category `peripherals` cho category `electronics`. Nếu cần lọc thêm `status` và kết quả đúng 20 hàng đã lọc, phải thiết kế đường truy vấn tương ứng hoặc dùng index đã được kiểm chứng; **lọc sau khi lấy 20 hàng trong JVM** có thể trả kết quả sai hợp đồng.

## 12. Tìm kiếm nâng cao: những gì Spring Data Cassandra không tự cung cấp

Cụm “tìm kiếm nâng cao” dễ gây hiểu nhầm vì các module Spring Data dùng tên repository gần giống nhau. Trong Cassandra, cần phân biệt **structured filtering** và **search theo nội dung**.

### 12.1. Structured filtering

Ví dụ:

~~~sql
-- Theo khóa:
SELECT * FROM products_by_tenant_category
WHERE tenant_id = ? AND category = ?;

-- Điều kiện trên clustering column đầu trong một partition:
SELECT * FROM products_by_tenant_category
WHERE tenant_id = ? AND category = ?
  AND created_at >= ? AND created_at < ?;
~~~

Hai câu trên đi theo primary-key path được thiết kế. Bộ lọc trên cột thường hoặc collection cần index hỗ trợ/đường đọc riêng và kiểm chứng từng toán tử.

### 12.2. Collection search

Với `tags set<text>`, một nhu cầu:

~~~sql
-- Chỉ áp dụng nếu backend/index hỗ trợ phép CONTAINS
-- trên cột tags theo schema thật.
SELECT * FROM catalog_products_by_id
WHERE tags CONTAINS 'sale';
~~~

`CONTAINS` là phép CQL, không phải một tính năng “quét tags miễn phí” do Spring Data tự thêm. Nếu sản phẩm cần “liệt kê mọi sản phẩm có tag `sale` trong tenant A, mới nhất trước”, thiết kế bảng đảo như `products_by_tenant_tag` có thể phù hợp hơn, với `(tenant_id, tag)` làm partition key và clustering theo thời gian/ID.

### 12.3. Tìm kiếm văn bản, ranking và autocomplete

Yêu cầu:

~~~text
q="wireles moues"
→ gợi ý "wireless mouse"
→ xếp hạng theo độ liên quan
→ đánh dấu từ khớp
→ filter tenant/category/availability
~~~

không thể được suy ra từ `@Indexed`, `findByProductNameContaining(...)` hay `@Query` một cách tổng quát. Một số bản Cassandra/index extension có thể hỗ trợ `LIKE`/prefix hoặc tính năng text nhất định, nhưng **khả năng phân tích ngôn ngữ, fuzzy matching và ranking là phụ thuộc backend**.

Nếu yêu cầu là tìm kiếm văn bản phong phú, hãy đánh giá một công cụ search như Elasticsearch/OpenSearch hoặc giải pháp mà nhà cung cấp dữ liệu hỗ trợ, cùng chiến lược đồng bộ dữ liệu, quyền tenant, độ trễ cập nhật và chi phí vận hành. Không viết repository method với cú pháp “giống Spring Data Elasticsearch” rồi mong Cassandra tự triển khai thuật toán tương đương.

### 12.4. Tìm kiếm vector, địa lý hoặc phân tích

Các nền tảng Cassandra hiện đại có thể mở rộng với kiểu vector hoặc khả năng truy vấn chuyên biệt, nhưng **không mặc định** có cùng API và toán tử trên mọi phiên bản. Các bài toán nearest-neighbor, geospatial hoặc OLAP cần kiểm tra **phiên bản server, driver, Spring Data và ngữ nghĩa index**. Nếu vượt phạm vi backend, dùng dịch vụ chuyên dụng hoặc pipeline phân tích.

**Quy tắc thực hành:** lấy **query contract** làm điểm bắt đầu; sau đó mới chọn primary key, index/extension hoặc engine khác, rồi quyết định dùng API Spring Data nào để gửi câu truy vấn.

## 13. Kiểm tra index vật lý và CQL thật

Trong production, thay annotation hoặc repository method **không chứng minh index đã tồn tại**. Hãy kiểm tra keyspace/schema bằng CQL với quyền phù hợp.

~~~sql
SELECT column_name, kind, position, type
FROM system_schema.columns
WHERE keyspace_name = 'app_data'
  AND table_name = 'catalog_products_by_id';

SELECT index_name, kind, options
FROM system_schema.indexes
WHERE keyspace_name = 'app_data'
  AND table_name = 'catalog_products_by_id';
~~~

Thay `app_data` bằng keyspace đang dùng. `kind` và `options` của index giúp xác định **kiểu cấu trúc vật lý** đã được tạo; không chỉ nhìn tên `catalog_products_category_idx` để kết luận nó là SAI.

Trong `cqlsh`, có thể dùng:

~~~text
-- Lệnh của cqlsh, không phải prepared CQL gửi từ Java Driver.
DESCRIBE TABLE catalog_products_by_id;
~~~

Khi ứng dụng phát truy vấn, quan sát bằng **Java Driver request tracker/logging** trong môi trường test/staging có kiểm soát, không bật log chứa bind values nhạy cảm trên production. Ghi lại:

- CQL thật, bảng, các cột `WHERE`, toán tử, `LIMIT`, `ORDER BY`.
- Thứ tự và kiểu bind markers; không log giá trị tenant/customer nếu không cần.
- Index đã được tạo, loại index, trạng thái hoạt động theo khả năng môi trường.
- Consistency/timeout, paging state/page size, số hàng và latency.
- Lỗi `InvalidQueryException` hoặc nguyên nhân server khác, thay vì chỉ xem exception wrapper của Spring.

**Không chạy thử truy vấn lọc toàn bảng trên cluster lớn** chỉ để xem “có trả kết quả không”. Hãy dùng test data, benchmark được giới hạn và kế hoạch đo tải phù hợp.

## 14. Testing: chứng minh annotation, index và API làm đúng việc

Unit test một phương thức repository mock được có thể kiểm tra service gọi đúng method, nhưng không chứng minh index tồn tại hay Cassandra chấp nhận CQL.

Một bộ **integration test** nên có Cassandra test instance, keyspace và schema migration riêng:

1. Tạo `catalog_products_by_id`, `products_by_tenant_category` trong test.
2. Nếu muốn kiểm tra index, tạo **đúng loại index** của hệ mục tiêu và xác minh trong `system_schema.indexes`.
3. Seed dữ liệu ở ít nhất hai tenant, nhiều category, nhiều status, có tên trùng và có tag.
4. Kiểm tra `repository.findById(new ProductIdKey(...))` chỉ trả đúng sản phẩm.
5. Kiểm tra repository/template đọc theo `products_by_tenant_category` trả đúng thứ tự và có paging state.
6. Với index, chạy chính câu CQL mà sản phẩm định dùng; test cả trường hợp không có đường truy cập.
7. Đo hành vi khi số hàng lớn, category phổ biến, nhiều truy vấn đồng thời và khi có cập nhật.
8. Kiểm tra authorization: không dùng tenant ID tùy ý từ client khi chưa xác thực.

### 14.1. Ví dụ kiểm tra schema bằng Java Driver

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import org.junit.jupiter.api.Test;

// Ví dụ phương thức nằm trong integration test có CqlSession session.
@Test
void categoryIndexExistsInTestSchema() {
    PreparedStatement ps = session.prepare(
            "SELECT index_name, kind, options " +
            "FROM system_schema.indexes " +
            "WHERE keyspace_name = ? AND table_name = ?");

    boolean found = false;
    for (Row row : session.execute(
            ps.bind("app_data", "catalog_products_by_id"))) {
        if ("catalog_products_category_idx".equals(
                row.getString("index_name"))) {
            found = true;
        }
    }

    assertTrue(found, "Expected index is missing from test schema");
}
~~~

**Đây là ví dụ cần bổ sung fixture và bean session**, không phải test đã chạy trong bước soạn bài. Test chỉ kiểm tra **có tên index**; cần thêm kiểm chứng `kind/options` phù hợp loại index mong đợi và chạy truy vấn thực để xác nhận capability.

### 14.2. Test âm tính và test hiệu năng không giống nhau

Ví dụ một test trên schema **không có index** có thể xác nhận câu `WHERE status = ?` không được hỗ trợ; nhưng khi triển khai phiên bản server/index khác, lỗi có thể thay đổi. Hãy kiểm tra khả năng thực thi theo **schema và version đã xác định**, không chỉ assert một message lỗi cố định.

Ngược lại, query có thể chạy thành công trên 10 hàng mà timeout trên 10 triệu hàng. Đây là vấn đề **hiệu năng/đường truy cập**, không phải lỗi Java parser. Để đánh giá index/read model, cần benchmark với phân bố thật: nhiều tenant, category phổ biến/hiếm, giá trị null, updates, tombstones và concurrency.

## 15. Consistency, paging và chi phí duy trì chỉ mục

### 15.1. Consistency không làm index thông minh hơn

`LOCAL_ONE`, `LOCAL_QUORUM` và các consistency levels phụ thuộc replication/keyspace. Chúng quyết định yêu cầu phản hồi replica của thao tác, **không** sửa một câu `WHERE` thiếu khóa hoặc index không phù hợp. Tăng consistency có thể ảnh hưởng latency và availability, nhưng không biến một `ORDER BY` trên cột thường thành sắp xếp hợp lệ.

Với dữ liệu denormalized ở hai bảng, ghi theo các câu CQL độc lập **không tự tạo giao dịch ACID xuyên bảng**. Phải thiết kế retry có idempotency key, theo dõi projection lag và thực hiện đối soát khi cần.

### 15.2. Paging của index query không đồng nghĩa paging của một partition

Khi truy vấn đi theo `products_by_tenant_category`, Cassandra đọc một partition có thứ tự clustering và dùng paging state tiến một chiều. Với truy vấn qua secondary index, cách server tìm và gom kết quả có thể khác; **đừng mặc định** index cho phép sort toàn cục giống SQL hoặc ổn định tương đương một partition theo khóa.

`Slice<T>`, `CassandraPageRequest.first(size)`, `nextPageable()` chỉ là cơ chế tiếp tục truy vấn được hỗ trợ. Page size không tự giới hạn tổng kết quả và **không sửa** tính chất fan-out của index search. Paging state không phải snapshot bất biến của dữ liệu qua nhiều HTTP requests.

### 15.3. Index có chi phí ghi

Khi thêm/chỉnh index, hệ thống phải duy trì dữ liệu phụ trợ tương ứng. Tùy loại index/server:

- Mỗi mutation có thể làm tăng I/O, CPU và độ trễ ghi.
- Backfill/build index từ dữ liệu hiện có có thể tiêu thụ tài nguyên.
- Compaction, TTL, delete và tombstones có thể ảnh hưởng chi phí đọc/ghi.
- Truy vấn ít chọn lọc có thể trả nhiều kết quả và tạo áp lực lên node/coordinator.
- Quá nhiều index làm phức tạp schema, nâng cấp, giám sát và kế hoạch phục hồi.

Không có giới hạn “tốt nhất” cho mọi dataset; phải đo p50/p95/p99 latency, timeout, throughput, partition/index size, disk, CPU, GC và retry trên tải đại diện.

## 16. Quy trình lựa chọn API và index cho một yêu cầu mới

~~~mermaid
flowchart TD
    A[Nhận yêu cầu tìm kiếm] --> B{Có đầy đủ partition key?}
    B -->|Có| C{Sort/range theo clustering hợp lệ?}
    C -->|Có| D[Repository hoặc CassandraTemplate]
    C -->|Không| E[Đánh giá bảng đọc riêng]
    B -->|Không| F{Lọc có chọn lọc trên cột đã index?}
    F -->|Có| G[Kiểm capability và benchmark index]
    F -->|Không| H{Full-text/fuzzy/ranking?}
    H -->|Có| I[Search backend/chức năng chuyên dụng]
    H -->|Không| E
    G --> J{Đạt SLA, sort và phân quyền?}
    J -->|Có| K[@Query/CqlTemplate với CQL đã kiểm chứng]
    J -->|Không| E
    D --> L[Integration test và quan sát]
    E --> L
    I --> L
    K --> L
~~~

Quy trình thực hành:

1. **Ghi query contract**: filter nào bắt buộc, sort gì, bao nhiêu kết quả, có trang tiếp không, giới hạn tenant ra sao?
2. **Đọc schema thực**: partition/clustering columns, index hiện có, loại index, version Cassandra.
3. **Ưu tiên đường primary-key path** nếu truy vấn quan trọng có thể được thiết kế thành một partition hợp lý.
4. **Đánh giá index** nếu là truy vấn theo cột khác và backend hỗ trợ, đặc biệt khi selectivity tốt.
5. **Chọn Spring Data API**: repository cho CRUD, `@Query` cho CQL cố định, template cho điều kiện hợp lệ, driver cho trường hợp cần kiểm soát sâu.
6. **Kiểm tra thực thi**: CQL thật, bind types, authorization, index usage theo công cụ phù hợp.
7. **Kiểm thử đúng/hiệu năng**: nhiều tenant, kết quả lớn, độ trễ, paging, cập nhật concurrent.
8. **Vận hành**: migration index/bảng, backfill, retry, consistency, metrics và quy trình rollback.

## 17. Bài tập thực hành

Một nền tảng đặt lịch có bảng:

~~~sql
CREATE TABLE bookings_by_id (
    tenant_id uuid,
    booking_id uuid,
    customer_id uuid,
    status text,
    service_type text,
    created_at timestamp,
    PRIMARY KEY ((tenant_id, booking_id))
);
~~~

API cần:

~~~text
GET /tenants/{tenantId}/bookings/{bookingId}
GET /tenants/{tenantId}/bookings?status=CONFIRMED&day=2026-11-25
GET /tenants/{tenantId}/bookings?serviceType=HAIRCUT
GET /tenants/{tenantId}/bookings/search?q=hair
~~~

**Bài tập A — chọn đường đọc.**

| Yêu cầu | Gợi ý đánh giá |
|---|---|
| Tra theo tenant + bookingId | Dùng `bookings_by_id` theo primary key |
| Danh sách CONFIRMED trong ngày | Cân nhắc `bookings_by_tenant_status_day` có time bucket, clustering theo `created_at` |
| Lọc theo serviceType | Index nếu phiên bản/tải phù hợp, hoặc `bookings_by_tenant_service_type` |
| Tìm “hair” dạng fuzzy/full text | Cần xác định chính xác semantics; có thể cần search backend |

**Bài tập B — thiết kế read model.**

~~~sql
CREATE TABLE bookings_by_tenant_status_day (
    tenant_id uuid,
    status text,
    booking_day date,
    created_at timestamp,
    booking_id uuid,
    customer_id uuid,
    service_type text,
    PRIMARY KEY (
        (tenant_id, status, booking_day),
        created_at, booking_id
    )
) WITH CLUSTERING ORDER BY (created_at DESC, booking_id ASC);
~~~

Hãy viết `@Query` lấy một slice trong `(tenant_id, status, booking_day)`, dùng `CassandraPageRequest.first(20)` rồi `slice.nextPageable()`. Giải thích vì sao thay `status` giữa hai trang không được dùng lại paging state.

**Bài tập C — phân biệt annotation và migration.**

Một developer thêm `@Indexed` vào `serviceType`, sau đó triển khai ứng dụng có `schema-action: NONE`. Hãy trả lời:

1. Index vật lý có chắc đã tồn tại không?
2. Kiểm tra `system_schema.indexes` như thế nào?
3. Nếu cluster hỗ trợ SAI, có thể khẳng định `@Indexed` tạo SAI không?
4. Nếu API cần sort mới nhất và chỉ trong một tenant, một index đơn cột đã đủ chưa?
5. Kế hoạch migration, build index, benchmark và rollback nên bao gồm gì?

**Bài tập D — quyết định API Java.**

Chọn một trong các phương án và lý giải:

- `findById` theo khóa đầy đủ.
- `@Query` cho CQL tường minh theo `tenant_id/status/booking_day`.
- `CassandraTemplate` khi cần một khoảng thời gian tùy chọn trên clustering column đã có.
- `CqlSession` khi cần statement options hoặc logic query chuyên biệt.
- Search backend khác cho yêu cầu ranking/fuzzy.

### Câu hỏi tự kiểm tra

1. `@Indexed` có bảo đảm index đã được tạo và chọn khi thực thi không?
2. `@Query` có làm `WHERE status=?` hợp lệ mà không có schema/index hỗ trợ không?
3. Vì sao `findByCategory` có thể parse được nhưng vẫn không phù hợp với Cassandra?
4. Điều kiện `WHERE tenant_id=? AND product_id=?` khác `WHERE category=?` ở đường truy cập nào?
5. SAI, SASI và 2i có thể coi là đồng nghĩa không?
6. Một index trên category có tự hỗ trợ `ORDER BY created_at DESC` không?
7. Vì sao index trên giá trị phổ biến có thể gây chi phí cao?
8. `CassandraTemplate` có tự xây index khi gọi `Query/Criteria` không?
9. Khi nào nên chọn bảng `products_by_tenant_category`?
10. Vì sao cần kiểm tra schema/index thực tế bằng CQL, không chỉ nhìn annotation?

**Gợi ý đáp án:** (1) không; (2) không; (3) parser không thay thế khả năng truy vấn backend; (4) một câu có đủ partition key, câu kia lọc trên cột thường; (5) không; (6) không tự động; (7) nhiều hàng/partition phải được xử lý, fan-out và chi phí index; (8) không; (9) khi đó là access pattern quan trọng cần sort/paging ổn định; (10) annotation không phải trạng thái vật lý đã được migrate.

## 18. Checklist trước khi release

- [ ] Đã xác định **query contract** trước khi tìm annotation hoặc viết repository method.
- [ ] Entity `@Table`, `@PrimaryKeyClass`, `@PrimaryKeyColumn`, `@Column` khớp với bảng vật lý.
- [ ] `@Indexed` được hiểu là metadata theo khả năng schema generation, **không phải bằng chứng index production**.
- [ ] Xác định rõ phiên bản/loại Cassandra và hỗ trợ 2i, SAI, SASI, toán tử liên quan.
- [ ] DDL index được quản lý bằng migration có kiểm soát, có kế hoạch build/backfill/rollback.
- [ ] Câu CQL thực tế được kiểm chứng với partition key, clustering order và index thực.
- [ ] Các derived methods không bị nhầm với một full-text search API.
- [ ] `@Query` và `Query/Criteria` chỉ biểu diễn truy vấn mà Cassandra có thể thực thi.
- [ ] Không dùng `ALLOW FILTERING` làm giải pháp mặc định cho truy vấn sai mô hình.
- [ ] Nếu cần sort/paging theo một access pattern quan trọng, đã đánh giá bảng đọc chuyên dụng.
- [ ] Nếu cần full-text/fuzzy/relevance, đã đánh giá backend có tính năng phù hợp.
- [ ] `Slice`, `LIMIT`, paging state được dùng đúng; không có OFFSET tùy ý hoặc cursor tái sử dụng giữa filter.
- [ ] API xác thực tenant và quyền truy cập ở mọi request, không dựa vào một index để cô lập dữ liệu.
- [ ] Có integration tests kiểm tra dữ liệu nhiều tenant/category, schema/index và kết quả truy vấn.
- [ ] Đã đo p95/p99, timeout, index selectivity, hot partition, tombstones và write amplification.
- [ ] Với nhiều bảng projection, có idempotency, đối soát và chính sách consistency phù hợp.

## Tài liệu tham khảo

- [Spring Data Cassandra — Object Mapping](https://docs.spring.io/spring-data/cassandra/reference/cassandra/object-mapping.html).
- [Spring Data Cassandra — Repository Query Methods](https://docs.spring.io/spring-data/cassandra/reference/cassandra/repositories/query-methods.html).
- [Spring Data Cassandra — CassandraTemplate](https://docs.spring.io/spring-data/cassandra/reference/cassandra/template.html).
- [Spring Data Cassandra — CQL Template](https://docs.spring.io/spring-data/cassandra/reference/cassandra/cql-template.html).
- [Apache Cassandra — Data Modeling](https://cassandra.apache.org/doc/latest/cassandra/developing/data-modeling/index.html).
- [Apache Cassandra — CQL Data Definition](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/ddl.html).
- [Apache Cassandra — CQL Data Manipulation](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/dml.html).

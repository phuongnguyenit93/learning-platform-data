# Kiểm thử tạo, đọc, cập nhật và xóa theo hợp đồng

Một repository Java có các phương thức create(), findById(), update() và delete(). Một test gọi từng phương thức, không nhận exception rồi kết luận CRUD đã đúng. Nhưng điều gì xảy ra khi tạo bản ghi trùng khóa, khi tenant khác đoán được ID, khi hai request sửa cùng bản ghi, hoặc khi xóa mềm rồi truy vấn danh sách?

**Kiểm thử CRUD theo hợp đồng** nghĩa là xác định đầu vào, trạng thái trước và sau, kết quả trả về, lỗi, bất biến dữ liệu và bảo đảm transaction của mỗi thao tác; sau đó chứng minh implementation tuân thủ cả khi gặp lỗi và truy cập đồng thời.

Bài thuộc chương **Kiểm thử lưu trữ** trong module **DATA_PERSISTENCE_FUNDAMENTALS**. Nội dung gắn Java persistence với mô hình dữ liệu, SQL, chỉ mục, giao dịch, cô lập, cạnh tranh, lỗi kết nối, bảo mật và hiệu năng. Ví dụ xuyên suốt sử dụng PostgreSQL, Spring JdbcTemplate và JUnit.

> **Nguyên tắc:** CRUD không chỉ là bốn động từ. Một implementation đạt hợp đồng khi dữ liệu được lưu, đọc, sửa và xóa theo đúng ngữ nghĩa đã công bố, không làm rò dữ liệu và không phá bất biến trong những lịch thực thi được hỗ trợ.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

- Viết hợp đồng Create, Read, Update, Delete gồm kết quả thành công, not found, duplicate, conflict và lỗi hạ tầng.
- Phân biệt unit test domain, unit test application với mock, repository integration test, API contract test và end-to-end test.
- Tạo fixture/cleanup cô lập, không phụ thuộc thứ tự test hoặc dữ liệu production.
- Kiểm tra mapping SQL–Java, PRIMARY KEY, UNIQUE, CHECK, NOT NULL, numeric, timestamp và schema migration.
- Kiểm tra tenant isolation, quyền truy cập, xóa mềm và chính sách tái sử dụng định danh.
- Xác minh rollback nguyên tử và ranh giới commit.
- Phát hiện lost update bằng optimistic locking và test song song có điều phối.
- Phân loại validation, duplicate, retryable, connection failure và ambiguous commit.
- Kiểm thử phân trang, sắp xếp, giới hạn kết quả và nguy cơ N+1.
- Dùng ma trận coverage và tiêu chí pass/fail cho lớp persistence.

## 2. Hợp đồng dữ liệu là gì?

Hợp đồng không chỉ là chữ ký method. Nó bao gồm:

1. **Precondition:** đầu vào hợp lệ thế nào, tenant nào được phép, trạng thái ban đầu?
2. **Effect:** hàng nào được tạo, sửa hoặc ẩn; có side effect nào khác?
3. **Return:** ID/object, Optional, boolean, số hàng hoặc loại kết quả?
4. **Failure:** duplicate, conflict, not found, timeout được biểu diễn ra sao?
5. **Atomicity:** phương thức tham gia transaction nào; ai commit?
6. **Concurrency:** hai request cạnh tranh có được cùng thành công không?
7. **Visibility:** đọc lại sau ghi phải thấy gì; có replica hoặc cache trễ không?
8. **Security:** truy vấn có bảo vệ tenant và giới hạn quyền không?
9. **Durability:** statement thành công khác với COMMIT được xác nhận.

### 2.1. Ma trận CRUD mẫu

Một sản phẩm thuộc tenant, có ID, SKU duy nhất trong tenant, giá không âm, version tăng sau thay đổi và xóa mềm:

| Operation | Thành công | Trường hợp không thành công | Trạng thái cần kiểm tra |
|---|---|---|---|
| Create | Một product, version=0 | ID/SKU trùng, constraint sai | Không có hàng phụ |
| Read active | Đúng object đang hoạt động | Không có, sai tenant, đã xóa | Không sửa dữ liệu |
| Update price | Một hàng khớp expectedVersion | Version sai, đã xóa, không có | Giá mới, version tăng một |
| Soft delete | Đánh dấu xóa, tăng version | Sai tenant/version hoặc đã xóa | Read active không thấy; row còn |
| Retry write | Theo idempotency contract nếu có | Commit outcome có thể chưa rõ | Không lặp nghiệp vụ do replay |

Đây là **một contract cụ thể**, không phải mặc định cho mọi hệ thống. Ứng dụng khác có thể hard delete hoặc trả Conflict/NotFound phân biệt. Test phải bám lựa chọn đã thống nhất, không suy đoán từ tên method.

### 2.2. Đừng chỉ kiểm tra có lời gọi JDBC

~~~java
verify(jdbcTemplate, times(1)).update(anyString(), any());
~~~

Test này không biết SQL đã lọc tenant chưa, hàng nào bị sửa, constraint nào hoạt động hay transaction có rollback không. Mock có ích cho orchestration nhưng không thay integration test trên PostgreSQL.

## 3. Mô hình dữ liệu ví dụ

~~~sql
CREATE TABLE products (
    tenant_id bigint NOT NULL,
    id uuid NOT NULL,
    sku text NOT NULL,
    name text NOT NULL,
    price numeric(12, 2) NOT NULL,
    version bigint NOT NULL DEFAULT 0,
    deleted_at timestamptz NULL,
    PRIMARY KEY (tenant_id, id),
    CONSTRAINT products_sku_tenant_unique UNIQUE (tenant_id, sku),
    CONSTRAINT products_name_nonblank CHECK (btrim(name) <> ''),
    CONSTRAINT products_price_nonnegative CHECK (price >= 0),
    CONSTRAINT products_version_nonnegative CHECK (version >= 0)
);

CREATE INDEX idx_products_active_tenant_sku
    ON products (tenant_id, sku)
    WHERE deleted_at IS NULL;
~~~

Đặc điểm contract:

- Cùng UUID có thể tồn tại ở hai tenant vì khóa chính gồm tenant_id và id.
- SKU không được trùng trong cùng tenant, **kể cả khi bản ghi cũ đã soft delete** do UNIQUE không có điều kiện deleted_at.
- Giá dùng numeric(12,2) và Java BigDecimal; cần quy định scale/rounding.
- version=0 khi tạo; update/delete thành công tăng version.
- Soft delete giữ bản ghi để audit; các đường đọc active lọc deleted_at IS NULL.

### 3.1. Bất biến cần kiểm tra

~~~text
(tenant_id, sku) là duy nhất.
price >= 0, biểu diễn được bằng numeric(12,2).
version >= 0.
Hàng deleted_at khác NULL không xuất hiện trong findActive.
Update/Delete chỉ thay đổi hàng có đúng tenant, id, version.
~~~

Quy tắc được DB CHECK/UNIQUE bảo vệ cần kiểm chứng bằng DB thật; những điều không có constraint (như tenant_id > 0 nếu là invariant) phải được kiểm tra tại application hoặc thêm CHECK tương ứng. DDL/migrations dùng trong test nên trùng với production, không dựng một schema khác rồi coi test đã chứng minh production.

### 3.2. Fixture nên gồm

- Tenant 101 và 202; cùng product UUID ở hai tenant với giá khác nhau.
- SKU hợp lệ và SKU trùng trong cùng tenant.
- Giá 0, 19.90 và một giá không hợp lệ.
- Tên Unicode, tên chỉ chứa khoảng trắng.
- Product active, product đã soft delete.
- Version 0, 1 và version cũ để tạo conflict.
- Các kịch bản cập nhật đồng thời hoặc transaction rollback.

Không để test phụ thuộc thứ tự chạy hoặc record còn sót từ suite trước.

## 4. Port và adapter tuân theo contract

~~~java
import java.math.BigDecimal;
import java.util.Optional;
import java.util.UUID;

public record CreateProduct(
    long tenantId, UUID id, String sku, String name, BigDecimal price
) {}

public record ProductView(
    long tenantId, UUID id, String sku, String name,
    BigDecimal price, long version
) {}

public interface ProductRepository {
    void create(CreateProduct product);

    Optional<ProductView> findActive(long tenantId, UUID productId);

    boolean updatePriceIfVersionMatches(
        long tenantId, UUID productId,
        long expectedVersion, BigDecimal newPrice
    );

    boolean softDeleteIfVersionMatches(
        long tenantId, UUID productId, long expectedVersion
    );
}
~~~

Contract của interface:

- create() hoàn thành bình thường sau khi INSERT thành công trong transaction đang tham gia; nếu còn outer transaction thì chưa tự chứng minh đã COMMIT.
- findActive() trả Optional.empty() nếu không có, sai tenant hoặc đã xóa. Có thể cố ý không phân biệt những trường hợp ấy để tránh tiết lộ record tenant khác.
- Update/Delete trả true khi một hàng khớp tenant/id/version được thay đổi; false nếu không có hàng khớp. Boolean không phân biệt not found, deleted và stale version.
- Caller/application service chọn HTTP status và domain error.
- Replay update với expectedVersion cũ sau một lần thành công sẽ trả false; đó không tự chứng minh lần đầu thất bại.

## 5. Adapter JDBC để thử nghiệm

Một implementation tối giản dùng JdbcTemplate và WHERE theo tenant, ID, version:

~~~java
import java.sql.ResultSet;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

@Repository
public class JdbcProductRepository implements ProductRepository {
    private final JdbcTemplate jdbc;

    public JdbcProductRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    private static final RowMapper<ProductView> PRODUCT_MAPPER =
        (ResultSet rs, int row) -> new ProductView(
            rs.getLong("tenant_id"),
            rs.getObject("id", UUID.class),
            rs.getString("sku"),
            rs.getString("name"),
            rs.getBigDecimal("price"),
            rs.getLong("version")
        );

    @Override
    public void create(CreateProduct p) {
        int rows = jdbc.update(
            """
            INSERT INTO products
                (tenant_id, id, sku, name, price, version)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            p.tenantId(), p.id(), p.sku(), p.name(), p.price()
        );
        if (rows != 1) {
            throw new IllegalStateException("Unexpected insert count");
        }
    }

    @Override
    public Optional<ProductView> findActive(
            long tenantId, UUID productId) {
        List<ProductView> rows = jdbc.query(
            """
            SELECT tenant_id, id, sku, name, price, version
            FROM products
            WHERE tenant_id = ? AND id = ?
              AND deleted_at IS NULL
            """,
            PRODUCT_MAPPER, tenantId, productId
        );
        return rows.stream().findFirst();
    }

    @Override
    public boolean updatePriceIfVersionMatches(
            long tenantId, UUID productId,
            long expectedVersion, BigDecimal newPrice) {
        return jdbc.update(
            """
            UPDATE products
            SET price = ?, version = version + 1
            WHERE tenant_id = ? AND id = ?
              AND deleted_at IS NULL AND version = ?
            """,
            newPrice, tenantId, productId, expectedVersion
        ) == 1;
    }

    @Override
    public boolean softDeleteIfVersionMatches(
            long tenantId, UUID productId, long expectedVersion) {
        return jdbc.update(
            """
            UPDATE products
            SET deleted_at = now(), version = version + 1
            WHERE tenant_id = ? AND id = ?
              AND deleted_at IS NULL AND version = ?
            """,
            tenantId, productId, expectedVersion
        ) == 1;
    }
}
~~~

Đây là adapter minh họa, chưa có validation, authorization hay idempotency ở application boundary. JdbcTemplate bind parameter thay vì nối input vào SQL; trong transaction của Spring, các thao tác dùng cùng DataSource có thể tham gia transaction hiện tại. Một lần update SQL thành công **không tự chứng minh** transaction bên ngoài đã commit.

## 6. Kiểm thử đúng ranh giới

| Loại test | Có thể chứng minh | Không chứng minh |
|---|---|---|
| Domain unit test | Validation/quy tắc thuần Java | SQL, locking, constraint |
| Service test với fake/mock | Điều phối, error mapping | DB isolation, schema |
| Repository integration trên PostgreSQL | Mapping, SQL, CHECK/UNIQUE, CAS, rollback | HTTP/auth của toàn hệ |
| API contract test | Status, body, lỗi, ETag, quyền endpoint | Failover nếu mock infra |
| End-to-end/fault injection | Tương tác nhiều dịch vụ và phục hồi | Không thay test nhỏ có invariant rõ |

Với SQLSTATE, UUID, numeric, transaction isolation hoặc locking đặc trưng PostgreSQL, một H2/SQLite test có thể cho kết quả khác. Dùng PostgreSQL thật cho những bảo đảm cần đúng ở production.

## 7. Setup PostgreSQL Testcontainers và fixture

Một lựa chọn với JUnit 5 + Spring Boot + Testcontainers, giả định migration thật tạo bảng products:

~~~java
import java.math.BigDecimal;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@SpringBootTest
@Testcontainers
class ProductRepositoryIT {
    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16");

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry p) {
        p.add("spring.datasource.url", postgres::getJdbcUrl);
        p.add("spring.datasource.username", postgres::getUsername);
        p.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired ProductRepository repository;
    @Autowired JdbcTemplate jdbc;

    @BeforeEach
    void clean() {
        // Chỉ dùng khi test sở hữu database riêng, không chạy song song.
        jdbc.execute("TRUNCATE TABLE products");
    }

    private static CreateProduct sample(
            long tenant, UUID id, String sku, String name, String price) {
        return new CreateProduct(
            tenant, id, sku, name, new BigDecimal(price)
        );
    }

    // Các test tiếp theo là method trong class này.
}
~~~

Cần các dependencies Spring Test, JUnit Jupiter, Testcontainers PostgreSQL/JUnit, driver PostgreSQL và Flyway/Liquibase hoặc cơ chế chạy schema giống production. Khi app có nhiều DataSource, cấu hình rõ bean nào trỏ vào container. Trong môi trường CI, cần Docker/container runtime hoặc giải pháp DB test được quản lý.

### 7.1. Cô lập test đúng cách

- Mỗi test tự chuẩn bị dữ liệu; không phụ thuộc vào test khác.
- TRUNCATE chỉ dùng trong container/schema riêng, không trên production hoặc staging chia sẻ.
- Khi schema có FK, lựa chọn cleanup phải xét bảng phụ thuộc, không lạm dụng CASCADE.
- @Transactional trên test method và rollback sau test hữu ích cho một số trường hợp nhưng **che commit thật**; nó không chứng minh constraint deferrable và visibility giữa connection.
- Trong concurrency test, các thread khác thường không tham gia transaction gắn với thread test; fixture phải commit trước khi chúng đọc.
- Test dữ liệu lớn nên dùng seed có kiểm soát, không tạo hàng triệu row trong mỗi unit test.

## 8. Create: giá trị, constraint, dữ liệu biên

### 8.1. Tạo rồi đọc lại toàn bộ field

~~~java
@Test
void createPersistsFieldsAndInitialVersion() {
    UUID id = UUID.randomUUID();
    repository.create(sample(
        101L, id, "SKU-1", "Cà phê rang", "19.90"
    ));

    ProductView actual = repository.findActive(101L, id).orElseThrow();

    assertEquals(101L, actual.tenantId());
    assertEquals(id, actual.id());
    assertEquals("SKU-1", actual.sku());
    assertEquals("Cà phê rang", actual.name());
    assertEquals(0, actual.price().compareTo(new BigDecimal("19.90")));
    assertEquals(0L, actual.version());
}
~~~

Khi dùng BigDecimal, compareTo so giá trị số học; equals còn xét scale. Nếu contract yêu cầu đúng scale 2, bổ sung assertEquals(2, actual.price().scale()). Với adapter chạy auto-commit và không có transaction ngoài, một query mới kiểm chứng dữ liệu đã commit; khi thử trong transaction ngoài, phải xét điểm commit.

### 8.2. Trùng khóa chính

~~~java
@Test
void duplicateIdIsRejectedWithoutOverwritingOriginal() {
    UUID id = UUID.randomUUID();
    repository.create(sample(101L, id, "A", "Bút", "9.90"));

    assertThrows(DuplicateKeyException.class, () ->
        repository.create(
            sample(101L, id, "B", "Bút mới", "11.00")
        )
    );

    ProductView persisted = repository.findActive(101L, id).orElseThrow();
    assertEquals("A", persisted.sku());
    assertEquals(0, persisted.price().compareTo(new BigDecimal("9.90")));
}
~~~

Exception class là ví dụ theo JdbcTemplate và Spring exception translation thông thường. Nếu adapter định nghĩa exception domain riêng, test cần assert contract của adapter. Quan trọng hơn exception name là bản ghi gốc **không bị ghi đè**.

### 8.3. Trùng SKU trong tenant và không trùng xuyên tenant

~~~java
@Test
void duplicateSkuWithinTenantIsRejected() {
    UUID one = UUID.randomUUID();
    UUID two = UUID.randomUUID();
    repository.create(sample(101L, one, "S-1", "Tập", "12.00"));

    assertThrows(DuplicateKeyException.class, () ->
        repository.create(sample(101L, two, "S-1", "Khác", "13.00"))
    );
    assertTrue(repository.findActive(101L, two).isEmpty());
}

@Test
void sameSkuCanExistInAnotherTenant() {
    repository.create(sample(
        101L, UUID.randomUUID(), "S-1", "Tập A", "12.00"
    ));
    repository.create(sample(
        202L, UUID.randomUUID(), "S-1", "Tập B", "21.00"
    ));
}
~~~

### 8.4. Ràng buộc giá và tên

~~~java
@Test
void negativePriceFailsAndDoesNotCreateProduct() {
    UUID id = UUID.randomUUID();
    assertThrows(DataIntegrityViolationException.class, () ->
        repository.create(sample(
            101L, id, "NEG", "Sai giá", "-1.00"
        ))
    );
    assertTrue(repository.findActive(101L, id).isEmpty());
}

@Test
void blankNameFails() {
    assertThrows(DataIntegrityViolationException.class, () ->
        repository.create(sample(
            101L, UUID.randomUUID(), "BLANK", "   ", "10.00"
        ))
    );
}
~~~

Lược đồ mẫu không có CHECK btrim(sku) <> '', nên nếu business cấm SKU rỗng, đó là **lỗ hổng contract cần bổ sung** ở validation hoặc schema. Một test không nên tuyên bố invariant đã được DB bảo vệ nếu DDL chưa biểu diễn nó.

### 8.5. Numeric và biên precision

Kiểm thử BigDecimal 0, giá lớn trong giới hạn và giá có quá nhiều chữ số thập phân. PostgreSQL numeric(12,2) có thể làm tròn khi đưa dữ liệu có scale lớn vào cột. Nếu nghiệp vụ **cấm làm tròn tự động**, Java phải dùng validation như setScale(2,RoundingMode.UNNECESSARY) và test rằng input không biểu diễn được bị từ chối **trước** khi INSERT.

## 9. Read: kiểm chứng đúng trường hợp vắng mặt, tenant và dữ liệu đã xóa

### 9.1. Không tìm thấy phải khác lỗi hạ tầng

~~~java
@Test
void findMissingProductReturnsEmpty() {
    assertTrue(repository.findActive(
        101L, UUID.randomUUID()
    ).isEmpty());
}
~~~

Không bắt timeout hoặc SQLException rồi chuyển tất cả thành Optional.empty(). Điều đó có thể khiến application coi một lỗi mạng là “không tồn tại”, tạo record trùng hoặc trả 404 sai.

### 9.2. Tenant khác không được đọc dữ liệu

~~~java
@Test
void findIsScopedByTenantEvenForSameId() {
    UUID id = UUID.randomUUID();
    repository.create(sample(101L, id, "A", "Tên A", "10.00"));
    repository.create(sample(202L, id, "B", "Tên B", "20.00"));

    ProductView a = repository.findActive(101L, id).orElseThrow();
    ProductView b = repository.findActive(202L, id).orElseThrow();

    assertEquals("Tên A", a.name());
    assertEquals("Tên B", b.name());
    assertEquals(101L, a.tenantId());
    assertEquals(202L, b.tenantId());
    assertTrue(repository.findActive(303L, id).isEmpty());
}
~~~

Cùng UUID ở hai tenant hợp lệ theo khóa (tenant_id,id), vì vậy bài test này phát hiện SQL WHERE chỉ dùng id mà quên tenant. Tuy nhiên **SQL tenant-scoping không thay API authorization**: tenantId phải đến từ security context đáng tin, không chỉ JSON do client tự gửi.

### 9.3. Read-after-write và replica

Nếu create() ghi primary nhưng findActive() đọc từ replica bất đồng bộ, GET ngay sau POST có thể trả not found vì replica chưa replay. Test phải chỉ ra hợp đồng:

- Có hứa read-your-writes không?
- Đường đọc dùng primary hay replica?
- Nếu replica, cần chờ version/LSN hay được trả dữ liệu cũ?
- Có cache trả stale dù database đã commit không?
- Đọc trong transaction REPEATABLE READ có giữ snapshot cũ không?

Đừng dùng vài lần sleep và retry tình cờ thành công làm chứng cứ bảo đảm consistency.

### 9.4. Field mapping và vòng đời connection

Phải xác minh UUID, BigDecimal, timestamp, nullable, enum và encoding Unicode đúng theo contract. Khi ResultSet chứa NULL, không tự biến thành 0 hoặc chuỗi trống nếu không được định nghĩa. Khi query thất bại, trả lỗi hạ tầng có nghĩa và giải phóng JDBC resources. Không đưa raw ResultSet/Stream lazy ra controller rồi tiêu thụ sau khi transaction đã đóng.

## 10. Update: thay đúng field, tăng version và phát hiện conflict

### 10.1. Happy path

~~~java
@Test
void updateChangesPriceAndVersionButPreservesOtherFields() {
    UUID id = UUID.randomUUID();
    repository.create(sample(101L, id, "U-1", "Bút", "11.00"));

    assertTrue(repository.updatePriceIfVersionMatches(
        101L, id, 0L, new BigDecimal("15.50")
    ));

    ProductView actual = repository.findActive(101L, id).orElseThrow();
    assertEquals(0, actual.price().compareTo(new BigDecimal("15.50")));
    assertEquals(1L, actual.version());
    assertEquals("U-1", actual.sku());
    assertEquals("Bút", actual.name());
}
~~~

Không chỉ kiểm tra giá mới; một SQL UPDATE sai có thể vô tình ghi đè name/sku hoặc reset version. Contract cần chỉ rõ trường nào **được phép thay đổi**.

### 10.2. Version cũ không được ghi đè dữ liệu mới

~~~java
@Test
void staleVersionIsRejectedWithoutLostUpdate() {
    UUID id = UUID.randomUUID();
    repository.create(sample(101L, id, "U-2", "Sổ", "20.00"));

    assertTrue(repository.updatePriceIfVersionMatches(
        101L, id, 0L, new BigDecimal("25.00")
    ));

    assertFalse(repository.updatePriceIfVersionMatches(
        101L, id, 0L, new BigDecimal("30.00")
    ));

    ProductView actual = repository.findActive(101L, id).orElseThrow();
    assertEquals(0, actual.price().compareTo(new BigDecimal("25.00")));
    assertEquals(1L, actual.version());
}
~~~

False có thể do missing, deleted hoặc stale version; nếu API cần phân biệt, nó phải đọc lại từ nguồn authoritative với chính sách quyền phù hợp. Không trả trạng thái “đã cập nhật” chỉ vì client gửi PATCH hợp lệ.

### 10.3. Sai tenant không được thay đổi hàng khác

~~~java
@Test
void updateOfOtherTenantDoesNotMutateProduct() {
    UUID id = UUID.randomUUID();
    repository.create(sample(101L, id, "U-3", "Sách", "10.00"));

    assertFalse(repository.updatePriceIfVersionMatches(
        202L, id, 0L, new BigDecimal("1.00")
    ));

    ProductView actual = repository.findActive(101L, id).orElseThrow();
    assertEquals(0, actual.price().compareTo(new BigDecimal("10.00")));
    assertEquals(0L, actual.version());
}
~~~

### 10.4. Constraint failure không được áp dụng cập nhật

~~~java
@Test
void invalidUpdateLeavesExistingStateIntact() {
    UUID id = UUID.randomUUID();
    repository.create(sample(101L, id, "U-4", "Giấy", "15.00"));

    assertThrows(DataIntegrityViolationException.class, () ->
        repository.updatePriceIfVersionMatches(
            101L, id, 0L, new BigDecimal("-10.00")
        )
    );

    ProductView actual = repository.findActive(101L, id).orElseThrow();
    assertEquals(0, actual.price().compareTo(new BigDecimal("15.00")));
    assertEquals(0L, actual.version());
}
~~~

Với autocommit, PostgreSQL từ chối statement vi phạm CHECK và không áp dụng thay đổi. Trong transaction nhiều câu, sau lỗi SQL cần xử lý trạng thái transaction bị abort theo DBMS rồi rollback ở scope sở hữu, không giả định có thể tiếp tục dùng transaction bình thường.

## 11. Delete: chọn rõ xóa mềm hay xóa cứng

Trong ví dụ, Delete nghĩa là đặt deleted_at và tăng version, không xóa vật lý.

### 11.1. Product biến mất khỏi đường đọc active nhưng row còn

~~~java
@Test
void softDeleteHidesActiveRecordButRetainsRow() {
    UUID id = UUID.randomUUID();
    repository.create(sample(101L, id, "D-1", "Tài liệu", "8.00"));

    assertTrue(repository.softDeleteIfVersionMatches(101L, id, 0L));
    assertTrue(repository.findActive(101L, id).isEmpty());

    Map<String, Object> stored = jdbc.queryForMap(
        """
        SELECT version, deleted_at
        FROM products WHERE tenant_id = ? AND id = ?
        """,
        101L, id
    );
    assertEquals(1L, ((Number) stored.get("version")).longValue());
    assertNotNull(stored.get("deleted_at"));
}
~~~

Test chỉ kiểm tra Optional.empty() có thể bỏ sót trường hợp implementation DELETE vật lý ngoài ý muốn. Vì thế truy vấn kiểm chứng trực tiếp **hàng vẫn tồn tại** và version/timestamp đúng.

### 11.2. Xóa lại và sửa row đã xóa

~~~java
@Test
void deletedProductCannotBeModifiedOrDeletedAgain() {
    UUID id = UUID.randomUUID();
    repository.create(sample(101L, id, "D-2", "Vở", "10.00"));
    assertTrue(repository.softDeleteIfVersionMatches(101L, id, 0L));

    assertFalse(repository.softDeleteIfVersionMatches(101L, id, 1L));
    assertFalse(repository.updatePriceIfVersionMatches(
        101L, id, 1L, new BigDecimal("20.00")
    ));
}
~~~

Ở tầng repository, lần xóa thứ hai trả false. Ở HTTP API, DELETE có thể được thiết kế idempotent về **tác động cuối** và trả 204 cả khi tài nguyên đã bị xóa; HTTP idempotency không đòi mọi lần gọi có cùng mã phản hồi. Tầng API phải công bố điều này rõ.

### 11.3. Soft delete vẫn chiếm UNIQUE key

Schema ví dụ dùng UNIQUE(tenant_id,sku) trên cả row đã xóa. Nếu business muốn tái sử dụng SKU sau soft delete, phải đổi schema/contract, ví dụ dùng partial unique index cho row active, rồi test hai INSERT đồng thời với cùng SKU. Không tự thay đổi tính duy nhất chỉ để một test pass.

### 11.4. Hard delete cần test riêng

Nếu nghiệp vụ dùng DELETE vật lý, cần xác minh row thật sự biến mất khỏi bảng, FK/ON DELETE policy đúng, audit/retention và side effect liên quan được xử lý. Một lệnh DELETE không tự xóa mọi bản sao trong WAL, replica, backup, cache hoặc search index. Không dùng CASCADE bừa bãi để cleanup test vì dễ che mất lỗi bảo vệ dữ liệu.

## 12. Transaction: chứng minh nguyên tử và rollback

Một use case có thể vừa tạo product vừa ghi audit/outbox. Kiểm tra từng INSERT riêng chưa chứng minh hai thay đổi commit nguyên tử.

### 12.1. Test rollback sau một bước đã ghi

Với TransactionTemplate tx được inject trong integration test và dùng transaction manager của cùng DataSource:

~~~java
@Test
void failedTransactionDoesNotPersistProduct() {
    UUID id = UUID.randomUUID();

    assertThrows(IllegalStateException.class, () ->
        tx.executeWithoutResult(status -> {
            repository.create(
                sample(101L, id, "TX-1", "Thử nghiệm", "5.00")
            );
            throw new IllegalStateException("Later operation failed");
        })
    );

    assertTrue(repository.findActive(101L, id).isEmpty());
}
~~~

Không bọc test trong outer @Transactional test rollback nếu mục tiêu là chứng minh commit/rollback thật. Với use case nhiều bảng, nên gây lỗi ở bước audit/outbox rồi assert **mọi** bảng được rollback.

### 12.2. Đọc qua hai connection và isolation

~~~text
Connection A: BEGIN
Connection A: INSERT P1 (chưa COMMIT)
Connection B: SELECT P1 ở READ COMMITTED -> không thấy
Connection A: COMMIT
Connection B: SELECT P1 bằng statement/snapshot mới -> thấy
~~~

Nếu B giữ snapshot REPEATABLE READ từ trước, kết quả có thể vẫn cũ dù A đã commit. Test phải mô tả isolation level, nguồn đọc (primary hay replica) và lúc tạo snapshot.

### 12.3. Side effect ngoài DB

Rollback PostgreSQL không thu hồi email đã gửi hoặc thao tác thanh toán API đã được hệ thống khác xác nhận. Với workflow vượt một DB, test application service và tích hợp outbox/idempotency riêng. Không suy local @Transactional bảo đảm atomicity xuyên HTTP/broker.

## 13. Concurrency: hai writer dùng cùng expectedVersion

### 13.1. Test hai cập nhật tranh chấp

Ví dụ dùng java.util.concurrent.* và helper sample của lớp ProductRepositoryIT:

~~~java
@Test
void sameVersionCannotBeUpdatedTwice() throws Exception {
    UUID id = UUID.randomUUID();
    repository.create(sample(101L, id, "RACE", "Giấy", "10.00"));

    ExecutorService pool = Executors.newFixedThreadPool(2);
    CountDownLatch start = new CountDownLatch(1);

    try {
        Future<Boolean> one = pool.submit(() -> {
            start.await();
            return repository.updatePriceIfVersionMatches(
                101L, id, 0L, new BigDecimal("11.00")
            );
        });
        Future<Boolean> two = pool.submit(() -> {
            start.await();
            return repository.updatePriceIfVersionMatches(
                101L, id, 0L, new BigDecimal("12.00")
            );
        });

        start.countDown();
        boolean a = one.get(10, TimeUnit.SECONDS);
        boolean b = two.get(10, TimeUnit.SECONDS);

        assertTrue(a ^ b, "Exactly one writer should succeed");
        ProductView actual = repository.findActive(101L, id).orElseThrow();
        assertEquals(1L, actual.version());

        BigDecimal expected = a
            ? new BigDecimal("11.00")
            : new BigDecimal("12.00");
        assertEquals(0, actual.price().compareTo(expected));
    } finally {
        pool.shutdownNow();
    }
}
~~~

Fixture phải commit trước khi các thread dùng những connection riêng. Pool đủ năng lực phục vụ hai task. Latch cho chúng khởi động gần nhau nhưng không đảm bảo lịch lock chính xác; property quan trọng vẫn là cả hai **không thể cùng thắng** với cùng version.

### 13.2. Update tranh chấp với soft delete

Một thread UPDATE giá version=0, thread kia soft DELETE version=0. Chỉ một mutation được phép thành công. Nếu UPDATE thắng, row active với version=1; nếu DELETE thắng, row bị ẩn và version=1. Test cần kiểm tra trạng thái cuối, không chỉ kết quả boolean.

### 13.3. Invariant nhiều hàng và deadlock

Optimistic version trên từng product chưa ngăn write skew của bất biến xuyên nhiều hàng. Có thể cần guard row, constraint hoặc PostgreSQL SERIALIZABLE. Với SQLSTATE 40001 hoặc 40P01 được xác nhận, retry **toàn bộ transaction** với budget/backoff; không retry một câu UPDATE trên snapshot cũ.

## 14. Phân loại lỗi theo hợp đồng

| Tín hiệu | Ý nghĩa thường gặp | Điều test phải chứng minh |
|---|---|---|
| 23505 unique_violation | ID/SKU trùng | Không ghi đè bản cũ |
| 23514 check_violation | Giá/tên sai CHECK | Không lưu giá trị sai |
| 23502 not_null_violation | Thiếu trường bắt buộc | Không có row dở dang |
| UPDATE count=0 | Không có row khớp điều kiện | False hoặc conflict theo contract |
| 40001 serialization_failure | Transaction bị abort | Retry toàn transaction khi an toàn |
| 40P01 deadlock_detected | DB hủy một transaction | Retry có giới hạn |
| 08xxx connection error | Kết nối bị lỗi | Có thể không rõ kết quả khi COMMIT |
| Query timeout/cancel | Không nhận kết quả đúng hạn | Không suy mọi tác động chưa xảy ra |
| HTTP 504 sau ghi | Không nhận upstream response | Không suy upstream rollback |

Spring có thể dịch SQLException thành DataAccessException; kiểm tra đúng abstraction công khai của repository/service. Không bắt tất cả lỗi rồi trả Optional.empty(), vì DB không sẵn sàng không đồng nghĩa record không tồn tại.

### 14.1. Timeout khi COMMIT: kết quả chưa rõ

~~~text
Client gửi CREATE cùng requestKey R
Database INSERT rồi COMMIT thành công
ACK bị mất
Client nhận socket timeout
~~~

Không được suy chắc chắn transaction chưa ghi. Nếu retry với ID mới, có thể tạo duplicate nghiệp vụ. Khi API cần replay an toàn, lưu requestKey bền vững cùng mutation trong một DB transaction, có UNIQUE, kiểm tra payload, đối soát trên nguồn authoritative và retry với giới hạn.

### 14.2. Test idempotency nếu hợp đồng có cam kết

~~~sql
CREATE TABLE create_product_requests (
    tenant_id bigint NOT NULL,
    request_key uuid NOT NULL,
    request_hash text NOT NULL,
    product_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, request_key)
);
~~~

Các test cần thêm:

- Hai request cùng key/payload chỉ một effect được commit.
- Hai request đồng thời cùng key vẫn bị UNIQUE bảo vệ.
- Cùng key khác payload bị từ chối.
- Mất ACK sau COMMIT rồi replay cùng key tìm lại kết quả cũ.
- Khi replica trễ không có key, không suy lần đầu rollback.

Repository mẫu không có idempotency key nên **không tự hứa** một POST lặp với ID mới sẽ an toàn. Đó là yêu cầu mở rộng cần contract riêng.

## 15. Hợp đồng HTTP khác hợp đồng repository

| HTTP operation | Thành công thường dùng | Những case khác |
|---|---|---|
| POST /products | 201, Location, product ID | 400 validation, 409 duplicate, idempotency |
| GET /products/{id} | 200, DTO | 404/403 theo policy tenant |
| PUT/PATCH price | 200/204 | 404, 409 hoặc 412 khi version/If-Match sai |
| DELETE /products/{id} | 204 hoặc kết quả quy định | Đã xóa, không có, sai tenant/version |

Repository trả Optional, boolean hoặc exception; application/controller mới quyết định HTTP status, JSON, authorization và ETag. Nếu dùng ETag/If-Match, test đọc ETag version 1 rồi thử cập nhật khi DB đã ở version 2; request cũ phải bị từ chối, không ghi đè.

### 15.1. Test quyền thực sự tại API

SQL có WHERE tenant_id vẫn có thể bị lạm dụng nếu client tự chọn tenantId. API test phải có hai principal từ security context:

- Tenant A tạo product, tenant B không thể GET/PUT/DELETE record của A.
- Database row thuộc A không thay đổi sau request trái phép.
- Error body không tiết lộ thông tin không được phép.
- Log không lộ tham số chứa dữ liệu nhạy cảm của tenant khác.

### 15.2. HTTP idempotency không nhất thiết cùng status

DELETE có thể idempotent về tác động tài nguyên và trả status khác giữa lần đầu và lần sau. Nếu API công bố trả 204 cho cả hai lần, test đúng chính sách ấy. Với POST có idempotency key, replay có thể trả lại kết quả cũ hoặc trạng thái đang xử lý theo contract; việc lặp request không mặc nhiên là một nghiệp vụ mới.

## 16. Kiểm thử danh sách: sắp xếp, phân trang và hiệu năng

Read không chỉ là findById(). Các API danh sách thường có lọc theo tenant, phân trang, sort và truy vấn JOIN. Contract cần bảo đảm **không trả dữ liệu ngoài phạm vi, không lặp/mất hàng trong điều kiện đã định** và không lấy một lượng dữ liệu không giới hạn.

### 16.1. Một truy vấn danh sách mẫu

~~~sql
SELECT id, sku, name, price, version
FROM products
WHERE tenant_id = :tenant_id
  AND deleted_at IS NULL
  AND (:after_sku IS NULL OR sku > :after_sku)
ORDER BY sku ASC
LIMIT :page_size;
~~~

Lược đồ ví dụ có UNIQUE(tenant_id,sku), vì vậy sku là khóa sắp xếp duy nhất trong từng tenant. Đối với schema có sort key không duy nhất, phải bổ sung tie-breaker ổn định như id để keyset pagination không bỏ/lặp hàng.

Điều cần test:

- Tenant A không nhận sản phẩm của tenant B.
- Product đã soft delete không có trong danh sách active.
- sort tăng/giảm đúng theo contract.
- pageSize bằng 1, giới hạn tối đa, đầu/cuối danh sách.
- Cursor đúng ở ranh giới giữa hai trang.
- NULL hoặc sort key đặc biệt được xử lý theo chính sách.
- Không cho client chèn tùy ý ORDER BY hoặc SQL fragments.
- Khi dữ liệu thay đổi giữa hai trang, contract có yêu cầu snapshot ổn định hay chấp nhận danh sách có thay đổi?

### 16.2. Pagination dưới ghi đồng thời

OFFSET có thể bỏ/lặp record khi hàng ở trang trước bị insert/delete giữa hai lần đọc. Keyset giảm một số vấn đề nhưng cũng **không tạo snapshot ổn định qua nhiều HTTP requests**. Nếu nghiệp vụ phải xuất đúng toàn bộ record của một mốc, cần snapshot/cursor/job theo chiến lược rõ hơn.

Một test phân trang tốt phải tạo dữ liệu với các SKU có thứ tự biết trước, thêm một bản ghi trong lúc chuyển trang và kiểm tra hành vi được công bố. Không tuyên bố “không bao giờ thiếu hàng” nếu API thiết kế eventual listing không có snapshot chung.

### 16.3. Đo truy vấn và phát hiện N+1

Một endpoint đọc 100 product rồi truy vấn categories cho từng product có thể phát sinh 101 câu SQL. Unit test mock repository không phát hiện được. Có thể quan sát số query qua datasource proxy/metrics/tracing ở integration test và assert trên ngưỡng phù hợp.

Với các truy vấn quan trọng, chạy EXPLAIN (ANALYZE, BUFFERS) trên môi trường test có dữ liệu đại diện:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, sku, price
FROM products
WHERE tenant_id = 101 AND deleted_at IS NULL
ORDER BY sku
LIMIT 50;
~~~

Không cố định từng dòng của execution plan làm assertion brittle: planner có thể thay đổi theo dữ liệu, thống kê và phiên bản PostgreSQL. Dùng threshold và mục tiêu đo được, đồng thời xác minh index phù hợp. EXPLAIN ANALYZE thực thi truy vấn, nên thận trọng nếu áp dụng lên DML trong môi trường không cô lập.

## 17. Kiểm thử migration và khả năng tương thích schema

Ứng dụng hiếm khi giữ nguyên schema mãi. Một phiên bản cũ có thể vẫn đang chạy khi phiên bản mới đã thêm cột, đổi constraint hoặc chuyển dữ liệu sang representation khác.

### 17.1. Expand → migrate → contract

~~~mermaid
flowchart LR
    A["Schema cũ"] --> B["Expand: thêm cột/index tương thích"]
    B --> C["Writer tương thích"]
    C --> D["Backfill dữ liệu"]
    D --> E["Đối soát và chuyển reader"]
    E --> F["Quan sát"]
    F --> G["Contract: bỏ field cũ"]
~~~

Kiểm thử:

- Code cũ còn chạy được sau bước expand.
- Code mới xử lý đúng record chưa backfill và record đã backfill trong giới hạn contract.
- Writer còn hoạt động không làm hai representation lệch.
- Backfill có thể retry/idempotent; không bỏ record mới phát sinh sau cursor.
- SQL CHECK, UNIQUE, FK được validate sau khi dữ liệu tương thích.
- Reader mới đọc đúng dữ liệu ở primary; không dùng replica trễ làm bằng chứng cutover.
- Rollback feature flag về reader cũ chỉ hợp lệ nếu representation cũ vẫn được cập nhật.
- Chưa DROP cột cũ trước khi mọi writer/reader đã chuyển và có khả năng phục hồi.

### 17.2. Test migration bằng dữ liệu legacy

Đừng chỉ kiểm thử record tạo bằng code mới. Hãy có fixture chứa:

- Row ở schema cũ, thiếu trường mới.
- NULL/giá trị bất thường do nhập dữ liệu lịch sử.
- Timestamp ở múi giờ/precision khác.
- Numeric có scale và giới hạn biên.
- Bản ghi soft deleted và orphan theo các rule cũ nếu có.
- Ghi đồng thời trong lúc backfill.

Mục tiêu là xác minh quy tắc chuyển đổi có thể **giải thích mọi giá trị hiện có**; không gán giá trị mặc định tùy tiện để migration hết lỗi.

## 18. Fault injection: kiểm tra lỗi thật thay vì mock mọi thứ

Một số lỗi chỉ xuất hiện ở thời điểm hiếm, nhất là xung quanh COMMIT, connection pool, replication và failover. Cần môi trường thử nghiệm được phép tạo lỗi, không thực hiện phá kết nối hoặc dừng database production tùy tiện.

### 18.1. Ma trận lỗi và bằng chứng

| Tình huống | Phương pháp kiểm thử có kiểm soát | Kỳ vọng |
|---|---|---|
| Pool acquisition timeout | Giới hạn connection pool test, giữ các connection bận | Lỗi phân loại đúng, không biến thành not found |
| Query timeout/cancel | Câu SQL chờ khóa có deadline | Transaction kết thúc/rollback đúng |
| Duplicate write | Hai request trùng ID/SKU đồng thời | UNIQUE bảo vệ chỉ một record |
| Mất kết nối trước statement | Ngắt kênh đúng giai đoạn test | Không tạo kết quả ảo, tài nguyên được giải phóng |
| Mất ACK sau COMMIT | Proxy chặn response sau khi xác nhận commit thực | Client thấy unknown, replay an toàn nếu có idempotency |
| Lỗi giữa hai bước DB | Gây exception sau INSERT trước COMMIT | Rollback cả hai thao tác trong cùng transaction |
| Primary/replica lag | Tạm dừng replay trong staging theo runbook | GET từ replica có thể stale; read-your-writes không bị đánh tráo |
| Failover | Chuyển leader trong cluster test | App điều hướng đúng và không suy RPO bằng 0 nếu chưa có bảo đảm |
| Redis/cache stale | Giữ bản giá cũ sau update primary | Luồng quyết định nghiệp vụ không dùng cache như nguồn chuẩn |
| Restart khi backfill | Chết sau commit batch trước checkpoint | Resume idempotent và đối soát đúng |

### 18.2. Phân biệt test timeout với test COMMIT thật sự unknown

Ngắt socket ngẫu nhiên rồi nhận SQLException **không chứng minh** bạn đã thử đúng cửa sổ “DB commit nhưng ACK mất”. Muốn kiểm tra contract này, cần fault injection có thể chặn phản hồi **sau khi** DB đã ghi nhận commit, rồi xác minh bằng một kết nối authoritative mới. Sau đó retry cùng request key để bảo đảm effect không lặp.

Nếu không có dụng cụ kiểm soát thời điểm chính xác, báo cáo test chỉ có thể khẳng định “đã thử connection interruption”, không khẳng định “đã mô phỏng lost ACK after commit”.

### 18.3. Kiểm tra resource leak

Sau khi tạo nhiều exception liên tiếp, đo:

- Active/pending connections của pool có trở về mức bình thường không?
- Transaction có giữ lock quá lâu hoặc idle in transaction không?
- PreparedStatement/ResultSet có được đóng bởi cơ chế quản lý đúng không?
- Timeout có gây retry storm đè lên primary không?
- Executor dùng trong test có shutdown để không treo suite không?

Không lấy “test vẫn chạy tiếp được” làm bằng chứng rằng tài nguyên không rò; cần metrics hoặc giới hạn pool đủ nhỏ để lỗi lộ ra.

## 19. Bài tập tình huống

### Bài A — Create thành công nhưng GET không thấy

POST /products trả 201 sau COMMIT trên primary. GET ngay sau đó đọc replica và trả 404.

**Câu hỏi:** Đây có phải lỗi INSERT chưa commit? Test nên thay đổi thế nào?

**Gợi ý:** Replica có thể lag; hợp đồng read-your-writes cần đọc primary hoặc chờ replica đạt watermark. Test phải ghi rõ nguồn đọc và snapshot, không coi 404 từ replica là bằng chứng rollback.

### Bài B — Trùng SKU và hai tenant

Cùng SKU xuất hiện ở tenant A và tenant B, nhưng không được trùng hai lần trong tenant A.

**Câu hỏi:** DDL và test nào chứng minh?

**Gợi ý:** UNIQUE(tenant_id,sku); tạo cùng SKU ở hai tenant phải thành công, tạo hai bản trong một tenant phải bị từ chối, record trước không đổi.

### Bài C — Hai update cùng version

T1 và T2 cùng đọc product version 0. Cả hai muốn đặt giá khác nhau.

**Câu hỏi:** Nếu cả hai update đều thành công có vi phạm contract không? Bảo vệ bằng gì?

**Gợi ý:** Có. UPDATE cần WHERE version=0 và tăng version; một lần update ảnh hưởng 1 row, lần khác 0 row hoặc xung đột transaction. Test dùng hai connection và assert trạng thái cuối.

### Bài D — Soft delete nhưng SKU vẫn bị chiếm

Đã soft delete product SKU=A; tạo product mới cùng tenant/SKU bị UNIQUE violation.

**Câu hỏi:** Đây là bug hay contract?

**Gợi ý:** Theo lược đồ ví dụ, đây là contract vì UNIQUE không có điều kiện deleted_at. Nếu muốn tái sử dụng SKU, phải thay schema, logic và test cùng nhau.

### Bài E — Rollback bị che bởi test transaction

Test có @Transactional, gọi service tạo product rồi kiểm tra findActive trong cùng transaction, sau test framework rollback.

**Câu hỏi:** Có chứng minh dữ liệu được commit và thấy từ connection khác không?

**Gợi ý:** Không. Cần test với transaction thực sự kết thúc và một connection/snapshot mới; khi rollback use case, kiểm tra mọi bảng liên quan.

### Bài F — Nguồn lỗi bị nuốt

DAO catch mọi DataAccessException rồi trả Optional.empty().

**Câu hỏi:** Điều gì có thể xảy ra khi database timeout?

**Gợi ý:** API báo 404 dù record tồn tại. Phải phân biệt not found (query chạy thành công nhưng không có hàng) với lỗi hạ tầng (query không thực hiện/không trả kết quả xác định).

### Bài G — Trùng nghiệp vụ sau timeout

COMMIT đã xảy ra nhưng ACK mất. Client tạo UUID mới và gửi lại Create.

**Câu hỏi:** Vì sao contract CRUD đơn thuần chưa chống được? Cần test bổ sung gì?

**Gợi ý:** UUID mới không vi phạm UNIQUE cũ. Cần stable idempotency key, lưu cùng effect DB, test lost ACK và replay cùng key/payload.

### Bài H — Xóa cứng và các bản sao

Ứng dụng DELETE một row, test SELECT trả không có và kết luận mọi dữ liệu đã bị xóa vĩnh viễn.

**Câu hỏi:** Kết luận có đúng không?

**Gợi ý:** Không. WAL, backup, replica, export, cache và retention là những phạm vi riêng. Test DB chỉ chứng minh row không còn trong bảng/snapshot quan sát; cần kiểm tra hệ thống xung quanh theo data deletion contract.

### Bài I — Query plan khác khi test và production

H2 test query trả đúng 50 record, nhưng PostgreSQL production chậm vì JOIN lớn và thiếu index.

**Câu hỏi:** Test đang thiếu gì?

**Gợi ý:** Integration/performance test trên PostgreSQL với dữ liệu đại diện, đo query count, EXPLAIN và latency; không so sánh kế hoạch thực thi như chuỗi cố định.

## 20. Checklist triển khai bộ test CRUD theo hợp đồng

### Hợp đồng và dữ liệu

- [ ] Mỗi method có precondition, effect, return, failure và transaction boundary rõ.
- [ ] Test thành công và thất bại cho cả Create, Read, Update, Delete.
- [ ] Có test mapping UUID, numeric/BigDecimal, timestamp, nullable, Unicode và default.
- [ ] Kiểm tra PRIMARY KEY, UNIQUE, CHECK, NOT NULL, FK trên DB thật.
- [ ] Không suy method không ném exception là đã COMMIT bền vững.
- [ ] Đã chọn rõ soft delete hay hard delete và chính sách reuse key.

### Nhất quán và an toàn

- [ ] Query có tenant scope và API dùng identity đáng tin cậy.
- [ ] Đã kiểm tra không lộ/thay đổi dữ liệu tenant khác.
- [ ] Update/Delete kiểm tra version và ngăn lost update.
- [ ] Có test hai connection cạnh tranh theo lịch được kiểm soát.
- [ ] Transaction nhiều bảng có rollback/commit atomically.
- [ ] Lỗi hạ tầng không bị ngụy trang thành not found.
- [ ] Timeout khi COMMIT được xem là kết quả có thể chưa rõ; idempotency được kiểm thử nếu hợp đồng có.
- [ ] Read-after-write có source routing và freshness contract rõ.
- [ ] Không giả định rollback DB thu hồi email, broker hay payment side effect.

### Hạ tầng test và vận hành

- [ ] Test schema được tạo từ migration phù hợp với production.
- [ ] PostgreSQL integration test có fixture riêng, cleanup an toàn.
- [ ] Test chạy độc lập, không phụ thuộc thứ tự hoặc account/DB dùng chung.
- [ ] Test commit không bị outer test transaction che kết quả.
- [ ] Có test pagination, stable sort, limit và N+1.
- [ ] Có kế hoạch kiểm thử rollback/compatibility khi schema tiến hóa.
- [ ] Fault injection chỉ diễn ra trong môi trường được phép; biết chính xác mốc lỗi đã thử.
- [ ] Resource leak, pool saturation, retry budget và query latency được quan sát.
- [ ] Không log secret/PII và không đưa test fixture nhạy cảm vào Git.

## 21. Kết luận

Kiểm thử CRUD theo hợp đồng không chỉ chứng minh bốn method chạy được. Nó chứng minh một bản ghi được **tạo đúng định danh và constraint, đọc đúng phạm vi và trạng thái, cập nhật không làm mất thay đổi đồng thời, xóa theo ngữ nghĩa đã chọn**, đồng thời bảo vệ transaction và báo lỗi chính xác khi hệ thống không thuận lợi.

Với Java persistence, cách tiếp cận đáng tin là kết hợp unit test domain, test application service, integration test trên database cùng loại với production và một số test concurrency/fault injection có mục tiêu. **Tên phương thức, số lần gọi mock hoặc trạng thái xanh của migration không thay thế được bằng chứng rằng dữ liệu trong database đang tuân thủ hợp đồng nghiệp vụ**.

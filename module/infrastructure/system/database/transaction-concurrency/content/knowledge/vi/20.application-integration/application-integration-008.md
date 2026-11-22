# Khóa lạc quan của ORM và các cập nhật SQL bỏ qua kiểm tra phiên bản

ORM (Object-Relational Mapping) giúp ứng dụng thao tác với hàng trong cơ sở dữ liệu thông qua đối tượng. Khi một đối tượng được đọc, chỉnh sửa rồi lưu, ORM có thể tự kiểm tra xem hàng đó có bị một transaction khác thay đổi trong lúc ứng dụng xử lý hay không. Cơ chế này thường được gọi là **khóa lạc quan (optimistic locking)** và thường dựa trên một cột phiên bản (`version`) hoặc concurrency token.

Vấn đề xuất hiện khi cùng ứng dụng dùng nhiều cách ghi dữ liệu. Cập nhật một entity được ORM quản lý có thể tự động thêm điều kiện phiên bản vào câu UPDATE. Nhưng câu lệnh bulk update, JPQL bulk DML, native SQL, JDBC hoặc thao tác SQL trực tiếp thường bỏ qua cơ chế theo dõi entity. Nếu người viết câu lệnh không tự đưa điều kiện phiên bản vào, dữ liệu cũ có thể ghi đè dữ liệu mới mà không phát sinh lỗi xung đột.

Bài này giải thích cách ORM bảo vệ cập nhật thông thường, vì sao các đường ghi hàng loạt hoặc SQL trực tiếp bỏ qua kiểm tra đó, và cách thiết kế cập nhật có điều kiện để mọi đường ghi cùng tuân thủ quy tắc phiên bản.

## 1. Vì sao cần kiểm tra phiên bản?

Giả sử bảng `Product` có một sản phẩm:

| id | name | price | version |
|---:|---|---:|---:|
| 10 | Keyboard | 500000 | 7 |

Hai người dùng A và B cùng đọc sản phẩm khi `version = 7`. A đổi giá thành 520.000 đồng; B đổi tên thành “Mechanical Keyboard”. Nếu cả hai lưu toàn bộ trạng thái đã đọc mà không kiểm tra phiên bản, transaction lưu sau có thể ghi đè thay đổi của transaction trước.

```text
Transaction A                     Transaction B
     |                                  |
     | đọc Product 10, version 7        |
     |                                  | đọc Product 10, version 7
     | đổi price = 520000               | đổi name = Mechanical Keyboard
     |                                  |
     | UPDATE ... WHERE id=10           |
     | lưu thành công                   |
     |                                  | UPDATE ... WHERE id=10
     |                                  | ghi đè dữ liệu đã đọc cũ
     |                                  | lưu thành công
```

Nếu B ghi cả `name` và `price` theo snapshot cũ, giá 520.000 của A có thể bị thay lại thành 500.000. Đây là **lost update**.

Khóa lạc quan thêm một điều kiện: chỉ cập nhật nếu phiên bản hiện tại trong DB vẫn bằng phiên bản mà transaction đã đọc. Khi A lưu thành công, version tăng từ 7 lên 8. Khi B lưu với điều kiện `version = 7`, không có hàng nào khớp và ORM báo xung đột.

## 2. Cột version hoạt động như thế nào?

Một cột version là dấu hiệu cho biết một hàng đã thay đổi kể từ lần đọc trước. Với version số nguyên, mỗi lần cập nhật thành công thường tăng giá trị lên một đơn vị.

Mẫu SQL khái niệm:

```sql
UPDATE Product
SET name = :newName,
    price = :newPrice,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion;
```

Kết quả:

- Nếu số hàng bị ảnh hưởng là `1`, phiên bản khớp và cập nhật thành công.
- Nếu số hàng bị ảnh hưởng là `0`, hàng không tồn tại hoặc version đã thay đổi; ứng dụng phải xử lý như một xung đột hoặc trường hợp không tìm thấy tùy nghiệp vụ.

Điều kiện version và phép tăng version phải nằm trong cùng một câu UPDATE nguyên tử. Nếu ứng dụng đọc version, rồi cập nhật không có điều kiện version, race condition vẫn tồn tại.

### Version không phải khóa bi quan

Optimistic locking không có nghĩa DBMS hoàn toàn không dùng khóa. Khi UPDATE chạy, DBMS vẫn cần điều phối việc ghi vật lý và có thể giữ write lock trong thời gian câu lệnh/transaction thực hiện. Điểm khác biệt là ứng dụng không giữ một khóa độc quyền dài hạn trong suốt thời gian người dùng đọc màn hình và suy nghĩ. Xung đột được phát hiện khi lưu, thay vì bắt người dùng khác chờ từ đầu.

### Chọn kiểu version

Các lựa chọn thường gặp:

| Kiểu | Đặc điểm | Lưu ý |
|---|---|---|
| Số nguyên (`long`, `BIGINT`) | Tăng đơn điệu mỗi lần cập nhật | Dễ so sánh, dễ dùng trong điều kiện SQL |
| Timestamp | Dùng thời điểm cập nhật làm dấu phiên bản | Độ chính xác và cách tạo thời gian phụ thuộc DBMS; hai cập nhật có thể trùng giá trị nếu độ phân giải thấp |
| Row version do DBMS sinh | DBMS tự tạo token mới khi hàng thay đổi | Ví dụ SQL Server `rowversion`; không phải timestamp ngày giờ |
| UUID/token mới | Mỗi lần cập nhật tạo giá trị khác | Không biểu diễn thứ tự lớn/nhỏ; phù hợp so sánh bằng, không thay thế fencing token |

Với ORM, nên dùng kiểu version được provider hỗ trợ chính thức. Không tự thay đổi version trong code nghiệp vụ khi ORM đang quản lý nó, trừ khi đang thực hiện một câu DML có điều kiện và hiểu rõ cơ chế của provider.

## 3. ORM-managed update: ORM tự thêm điều kiện version

Khi entity được ORM quản lý, ORM theo dõi trạng thái ban đầu và trạng thái sau chỉnh sửa. Khi flush hoặc save, ORM tạo UPDATE có điều kiện dựa trên version đã đọc.

### 3.1. JPA/Hibernate với `@Version`

Ví dụ entity:

```java
@Entity
public class Product {
    @Id
    private Long id;

    private String name;
    private BigDecimal price;

    @Version
    private long version;
}
```

`@Version` đánh dấu thuộc tính version mà provider JPA dùng để kiểm soát cập nhật đồng thời. Ứng dụng thường không tự tăng trường này khi chỉnh sửa entity được quản lý; provider chịu trách nhiệm tạo giá trị version mới.

Ví dụ sử dụng:

```java
Product product = entityManager.find(Product.class, 10L);
product.setPrice(new BigDecimal("520000"));

entityManager.flush();
```

SQL sinh ra có dạng khái niệm:

```sql
UPDATE product
SET price = ?, version = ?
WHERE id = ?
  AND version = ?;
```

Provider dùng version cũ trong `WHERE` và ghi version mới trong `SET`. Nếu UPDATE không tác động hàng nào, provider nhận biết optimistic lock failure. JPA thường biểu diễn bằng `OptimisticLockException`; Hibernate có thể bọc hoặc đưa ra exception đặc thù như `StaleObjectStateException` tùy vị trí và API.

Xung đột có thể được phát hiện tại `flush()` hoặc khi transaction commit, vì ORM có thể trì hoãn SQL đến cuối transaction. Do đó, không nên chỉ bắt exception quanh dòng `setPrice`; cần xử lý ở ranh giới flush/commit hoặc transaction service.

### 3.2. Entity phải được quản lý trong persistence context

Dirty checking và tự động thêm version condition áp dụng cho entity được provider quản lý. Nếu đối tượng chỉ là DTO hoặc một object Java thông thường, ORM không tự biết trạng thái ban đầu của nó.

Với entity detached, thao tác `merge()` sao chép trạng thái của object vào một instance managed. Version của entity vẫn có ý nghĩa trong quá trình kiểm tra, nhưng thời điểm phát hiện xung đột có thể là lúc merge, flush hoặc commit tùy provider. Không nên bỏ trường version khỏi dữ liệu cập nhật rồi giả định ORM có thể phát hiện mọi chỉnh sửa cũ.

Một mẫu service thường là:

```java
@Transactional
public void changePrice(Long id, long expectedVersion, BigDecimal newPrice) {
    Product product = entityManager.find(Product.class, id);
    if (product == null) {
        throw new ProductNotFoundException(id);
    }

    if (product.getVersion() != expectedVersion) {
        throw new StaleProductException(id);
    }

    product.setPrice(newPrice);
    // ORM tiếp tục kiểm tra version khi flush.
}
```

Kiểm tra `expectedVersion` trong service giúp trả lỗi sớm và diễn đạt điều kiện của client. Điều kiện version do ORM thêm vào UPDATE vẫn cần thiết vì một transaction khác có thể cập nhật sau lần kiểm tra trong service nhưng trước lúc flush.

### 3.3. EF Core với concurrency token

Trong Entity Framework Core, một thuộc tính có thể được cấu hình làm concurrency token:

```csharp
public class Product
{
    public int Id { get; set; }
    public string Name { get; set; } = "";
    public decimal Price { get; set; }

    [ConcurrencyCheck]
    public int Version { get; set; }
}
```

Hoặc cấu hình bằng Fluent API:

```csharp
modelBuilder.Entity<Product>()
    .Property(p => p.Version)
    .IsConcurrencyToken();
```

Với version do ứng dụng quản lý, code phải tăng token khi cập nhật, ví dụ dùng interceptor hoặc logic service nhất quán. EF Core giữ giá trị gốc đã đọc và dùng nó trong điều kiện UPDATE. Nếu không có hàng nào khớp, `SaveChanges()` ném `DbUpdateConcurrencyException`.

Với SQL Server, có thể dùng cột `rowversion` do DBMS sinh:

```csharp
public class Product
{
    public int Id { get; set; }
    public string Name { get; set; } = "";
    public decimal Price { get; set; }

    [Timestamp]
    public byte[] RowVersion { get; set; } = Array.Empty<byte>();
}
```

SQL Server tự thay đổi giá trị `rowversion` khi hàng được cập nhật. EF Core dùng giá trị ban đầu làm concurrency token trong WHERE. `rowversion` là token nhị phân tăng theo database, không phải ngày giờ tạo/cập nhật.

## 4. ORM kiểm tra phiên bản ở đâu trong câu SQL?

Một optimistic update cần có cả hai phần:

1. Điều kiện khớp phiên bản đã đọc trong `WHERE`.
2. Cập nhật version để các transaction đọc trước đó trở nên stale.

Ví dụ SQL minh họa:

```sql
UPDATE product
SET name = 'Keyboard Pro',
    version = 8
WHERE id = 10
  AND version = 7;
```

Nếu hàng đang có version 7, câu lệnh cập nhật và chuyển version thành 8. Nếu hàng đã có version 8, điều kiện không khớp; số hàng bị ảnh hưởng bằng 0.

Một câu UPDATE chỉ có `WHERE id = 10` không thực hiện optimistic version check, kể cả khi bảng có cột `version`. Cột version tự tồn tại không tự bảo vệ mọi câu lệnh SQL.

### Phân biệt optimistic conflict và not found

Affected rows bằng 0 có thể do:

- Hàng đã bị xóa.
- Version không còn khớp.
- Một điều kiện khác trong WHERE không còn đúng.

Nếu API cần phân biệt `404 Not Found` và `409 Conflict`, ứng dụng có thể đọc lại theo ID trong transaction phù hợp hoặc dùng chiến lược truy vấn riêng. Cần cân nhắc rằng lần đọc sau có thể thấy trạng thái mới hơn nữa; kết quả đó chỉ là thông tin chẩn đoán, không thay đổi việc câu UPDATE trước đã thất bại.

## 5. Vì sao bulk update bỏ qua optimistic locking?

Bulk update thường được thiết kế để thay đổi nhiều hàng trực tiếp trong database mà không tải từng entity vào bộ nhớ. Vì vậy, ORM không có trạng thái ban đầu của từng entity để so sánh version theo cách dirty checking thông thường.

Trong JPA, JPQL bulk UPDATE/DELETE được thực thi trực tiếp trên database và bỏ qua optimistic locking checks. Provider không tự động đồng bộ persistence context với kết quả bulk operation và không tự động tăng version như khi cập nhật entity được quản lý. Nếu muốn duy trì version semantics, ứng dụng phải chủ động đưa điều kiện hoặc thay đổi version vào câu lệnh.

Ví dụ JPQL bulk update:

```java
@Modifying
@Query("""
    update Product p
       set p.price = :price
     where p.category.id = :categoryId
""")
int updateCategoryPrice(Long categoryId, BigDecimal price);
```

Đoạn này có thể cập nhật hàng loạt sản phẩm nhưng không tự kiểm tra version cũ của từng entity và không tự tăng thuộc tính `@Version`. Một entity `Product` đang nằm trong persistence context cũng có thể tiếp tục chứa giá cũ và version cũ sau khi câu lệnh chạy.

### 5.1. Cập nhật bulk có điều kiện theo version

Nếu chỉ cập nhật một entity theo version kỳ vọng, có thể viết JPQL rõ ràng:

```java
@Modifying
@Query("""
    update Product p
       set p.price = :price,
           p.version = p.version + 1
     where p.id = :id
       and p.version = :expectedVersion
""")
int updatePriceIfVersionMatches(
    Long id,
    long expectedVersion,
    BigDecimal price
);
```

Ứng dụng kiểm tra kết quả:

```java
int updated = repository.updatePriceIfVersionMatches(
    id, expectedVersion, newPrice
);

if (updated == 0) {
    throw new OptimisticConflictException(id);
}
```

Điều kiện `p.version = :expectedVersion` phát hiện dữ liệu cũ; `p.version = p.version + 1` làm các entity khác đang giữ version trước đó trở nên stale. Ví dụ dùng version số nguyên. Nếu dùng timestamp, UUID hoặc DB-generated rowversion, cách tạo version mới phải phù hợp với DBMS và mapping.

Nếu câu lệnh cập nhật nhiều hàng theo category, một `expectedVersion` duy nhất không đủ để xác thực version riêng của từng hàng. Khi cần cập nhật theo tập, hãy xác định rõ chính sách: cập nhật tất cả hàng phù hợp và tăng version từng hàng, cập nhật một snapshot đã biết, hay yêu cầu tất cả version phải khớp. Những chính sách này cần SQL và kết quả đếm riêng; không thể suy ra từ một tham số version chung.

### 5.2. `@Modifying` và persistence context của Spring Data JPA

Spring Data JPA thường dùng `@Modifying` cho query DML. Bulk query không tự cập nhật các entity đã load trước đó trong persistence context.

Ví dụ:

```java
@Modifying(flushAutomatically = true, clearAutomatically = true)
@Query("""
    update Product p
       set p.price = :price,
           p.version = p.version + 1
     where p.id = :id
       and p.version = :expectedVersion
""")
int updatePriceIfVersionMatches(
    Long id,
    long expectedVersion,
    BigDecimal price
);
```

- `flushAutomatically = true` yêu cầu flush các thay đổi đang chờ trước khi chạy bulk query, giúp tránh việc thay đổi chưa flush bị sắp thứ tự sai với DML trực tiếp.
- `clearAutomatically = true` xóa các entity khỏi persistence context sau query, tránh tiếp tục dùng object managed có trạng thái cũ.
- `clear()` ảnh hưởng đến toàn bộ persistence context của EntityManager, không chỉ entity vừa cập nhật. Những thay đổi chưa flush sẽ bị detach; vì vậy cần hiểu rõ transaction và flush trước khi bật tùy chọn này.

Một lựa chọn khác là không clear toàn bộ context nhưng phải refresh hoặc reload các entity bị ảnh hưởng trước khi dùng tiếp. `refresh(entity)` ghi đè trạng thái trong bộ nhớ bằng trạng thái DB; nếu entity có thay đổi chưa flush, các thay đổi đó có thể bị mất. Hãy flush trước khi refresh khi cần giữ thay đổi đang chờ.

## 6. Native SQL, JDBC và DML bên ngoài ORM

Native SQL có thể cần thiết để dùng tính năng riêng của DBMS, CTE phức tạp, window function, bulk import hoặc tối ưu hiệu năng. Nhưng native SQL chạy trực tiếp trên database và không đi qua quy trình dirty checking của entity.

Ví dụ không an toàn nếu muốn bảo vệ version:

```sql
UPDATE product
SET price = :price
WHERE id = :id;
```

Câu lệnh này có thể ghi đè dữ liệu của một entity khác đã thay đổi. Việc entity Java có `@Version` không khiến database tự thêm `AND version = ...` vào câu SQL viết tay.

Mẫu có điều kiện:

```sql
UPDATE product
SET price = :price,
    version = version + 1
WHERE id = :id
  AND version = :expected_version;
```

Ứng dụng phải kiểm tra affected rows. Nếu driver trả về 0, xử lý như xung đột hoặc không tìm thấy theo hợp đồng API. Không được bỏ qua kết quả đếm và báo thành công.

### 6.1. Native query trong JPA

Ví dụ Spring Data:

```java
@Modifying(flushAutomatically = true, clearAutomatically = true)
@Query(value = """
    UPDATE product
       SET price = :price,
           version = version + 1
     WHERE id = :id
       AND version = :expectedVersion
    """, nativeQuery = true)
int updatePriceNative(
    @Param("id") Long id,
    @Param("expectedVersion") long expectedVersion,
    @Param("price") BigDecimal price
);
```

Đây là cú pháp SQL của ví dụ schema và có thể cần chỉnh tên bảng/cột theo naming strategy. Việc dùng `nativeQuery = true` không tự thêm optimistic locking. Chính câu SQL đã cung cấp điều kiện version và tăng version.

### 6.2. JDBC hoặc Dapper

Với JDBC, Dapper hoặc thư viện truy cập SQL trực tiếp, nguyên tắc giống nhau:

```java
int rows = jdbcTemplate.update("""
    UPDATE product
       SET price = ?, version = version + 1
     WHERE id = ? AND version = ?
    """,
    price, id, expectedVersion
);

if (rows != 1) {
    throw new OptimisticConflictException(id);
}
```

ORM không thể bảo vệ một câu lệnh mà nó không quản lý. Mọi đường ghi trực tiếp phải tuân thủ cùng hợp đồng version với đường ghi entity.

## 7. EF Core: SaveChanges và ExecuteUpdate

EF Core có thể phát hiện xung đột concurrency khi `SaveChanges()` lưu entity được theo dõi. Nó dùng giá trị concurrency token ban đầu trong WHERE và ném `DbUpdateConcurrencyException` nếu số hàng bị ảnh hưởng không như mong đợi.

Các API bulk như `ExecuteUpdate()` và `ExecuteDelete()` thực thi trực tiếp trên database, không đi qua change tracker như `SaveChanges()`. Chúng không tự áp dụng concurrency token check cho entity đã theo dõi. Nếu cần optimistic check, phải đưa token vào predicate và kiểm tra số hàng bị ảnh hưởng.

Ví dụ:

```csharp
var affected = await db.Products
    .Where(p => p.Id == id && p.Version == expectedVersion)
    .ExecuteUpdateAsync(setters => setters
        .SetProperty(p => p.Price, newPrice)
        .SetProperty(p => p.Version, p => p.Version + 1));

if (affected == 0)
{
    throw new OptimisticConflictException(id);
}
```

Đối với SQL Server `rowversion` do database sinh, không tự cộng token như số nguyên. Thay vào đó, thêm `RowVersion == expectedRowVersion` vào WHERE. Database sẽ tạo rowversion mới sau UPDATE; nếu cần giá trị mới, truy vấn lại hoặc dùng cơ chế trả về phù hợp với DBMS.

`ExecuteUpdate()` cũng không đồng bộ các entity đã được load vào change tracker. Nếu context đang giữ `Product` cũ, object đó không tự thay đổi sau bulk query. Hãy reload/clear/detach entity bị ảnh hưởng trước khi tiếp tục thao tác với nó. EF Core có `ChangeTracker.Clear()` để detach toàn bộ tracked entities; chỉ dùng khi phù hợp với các thay đổi chưa lưu khác.

## 8. Hậu quả khi bulk/native SQL không tăng version

Ngay cả khi bulk SQL không cần kiểm tra một version đầu vào cụ thể, nó thường vẫn phải tăng version của những hàng đã thay đổi để các client đang giữ snapshot cũ phát hiện xung đột khi lưu.

Ví dụ:

1. ORM session A đọc `Product 10`, version 7.
2. Một câu SQL trực tiếp cập nhật giá nhưng không tăng version.
3. ORM session A vẫn lưu entity với version 7.
4. WHERE version 7 vẫn khớp, nên ORM có thể ghi đè giá mà bulk SQL vừa cập nhật.

Đây là một lỗ hổng quan trọng: đường SQL trực tiếp đã thay đổi dữ liệu nhưng không làm token thay đổi, vì thế entity cũ không biết rằng nó đã stale.

Nếu bulk update là một thay đổi hợp lệ của dữ liệu và muốn các entity cũ bị phát hiện stale, hãy tăng version trong cùng câu UPDATE:

```sql
UPDATE product
SET price = :new_price,
    version = version + 1
WHERE category_id = :category_id;
```

Mỗi hàng được cập nhật sẽ có version mới. Khi ORM session cũ flush, điều kiện version cũ không còn khớp. Lưu ý đây là invalidation token; nó không kiểm tra một client cụ thể đã đọc version nào. Nếu nghiệp vụ cần compare-and-swap cho từng hàng, phải có predicate version kỳ vọng tương ứng.

## 9. Persistence context có thể giữ dữ liệu cũ sau bulk DML

Persistence context (JPA) hoặc change tracker (EF Core) là bộ nhớ đệm trạng thái entity trong một đơn vị làm việc. Bulk/native DML sửa database trực tiếp, nên object đã load có thể không phản ánh trạng thái mới.

Ví dụ:

```java
Product product = entityManager.find(Product.class, 10L);

// Native SQL hoặc JPQL bulk update thay đổi hàng Product 10.
repository.updatePriceNative(10L, product.getVersion(), newPrice);

// product trong bộ nhớ có thể vẫn chứa giá/version cũ.
```

Nếu tiếp tục sửa `product` rồi flush, ORM có thể gửi UPDATE với dữ liệu cũ. Khi bulk query đã tăng version, ORM sẽ phát hiện stale version và báo lỗi; nếu bulk query không tăng version, ORM có thể ghi đè thay đổi mà không phát hiện.

Các cách đồng bộ:

- Flush trước bulk DML để đẩy các thay đổi managed đang chờ xuống DB theo thứ tự mong muốn.
- Clear/detach persistence context sau bulk DML nếu không cần tiếp tục dùng entity đang quản lý.
- Refresh hoặc reload các entity cụ thể trước khi chỉnh sửa tiếp.
- Dùng transaction boundary riêng cho bulk operation nếu điều đó làm rõ vòng đời persistence context.

Không clear hoặc refresh một cách máy móc. `clear()` detach tất cả entity trong persistence context; `refresh()` có thể ghi đè thay đổi chưa flush. Cần biết entity nào đang dirty và transaction đang ở giai đoạn nào.

## 10. Cập nhật hàng loạt: chọn chính sách version rõ ràng

Không phải bulk update nào cũng cần một expected version chung. Cần phân biệt ba tình huống:

### A. Cập nhật một entity theo version từ client

Ví dụ người dùng chỉnh sửa một sản phẩm đã đọc từ trước. Dùng `WHERE id = ? AND version = ?`, tăng version khi thành công và kiểm tra affected rows. Nếu 0 hàng, trả conflict hoặc not found theo quy tắc API.

### B. Cập nhật một tập hàng theo điều kiện nghiệp vụ

Ví dụ quản trị viên tăng giá 5% cho mọi sản phẩm trong một category. Có thể chạy bulk update:

```sql
UPDATE product
SET price = price * 1.05,
    version = version + 1
WHERE category_id = :category_id;
```

Ở đây không có một version client duy nhất để so sánh cho mọi hàng. Chính sách có thể là cập nhật tất cả hàng đang thuộc category tại thời điểm câu lệnh chạy, đồng thời tăng version để invalidation các entity đã load trước đó. Nếu cần xác nhận một snapshot cụ thể hoặc bỏ qua những hàng đã đổi kể từ lúc xem trước, cần lưu danh sách ID/version và thiết kế câu lệnh kiểm tra từng cặp.

### C. Cập nhật theo snapshot gồm nhiều ID/version

Nếu client gửi một danh sách hàng kèm version đã đọc, ứng dụng phải kiểm tra từng version. Có thể đưa dữ liệu đầu vào vào bảng tạm/CTE hoặc dùng batch UPDATE có điều kiện. Kết quả cần xác định rõ hàng nào thành công, hàng nào stale và hàng nào không tồn tại. Không nên chỉ kiểm tra tổng affected rows nếu API cần báo kết quả riêng từng hàng.

## 11. Cập nhật SQL an toàn với nhiều đường ghi

Một ứng dụng thực tế có thể có nhiều con đường thay đổi cùng bảng:

| Đường ghi | Có tự kiểm tra version? | Trách nhiệm cần có |
|---|---|---|
| JPA/Hibernate managed entity có `@Version` | Có, provider thêm điều kiện khi flush | Xử lý optimistic lock exception |
| EF Core `SaveChanges()` với concurrency token | Có, change tracker dùng original value | Xử lý `DbUpdateConcurrencyException` |
| JPQL bulk UPDATE/DELETE | Không tự động | Thêm version predicate/tăng version khi cần; đồng bộ persistence context |
| JPA native SQL | Không tự động | Viết điều kiện version và kiểm tra affected rows |
| EF Core `ExecuteUpdate`/`ExecuteDelete` | Không tự động | Thêm predicate concurrency token, tăng token ứng dụng quản lý và kiểm tra affected rows |
| JDBC/Dapper/SQL trực tiếp | Không | Thực thi cùng hợp đồng version bằng SQL |
| Trigger hoặc job nền | Không qua ORM change tracking | Đảm bảo version được cập nhật hoặc có cơ chế concurrency khác |

Hợp đồng version cần được tài liệu hóa ở cấp bảng/aggregate. Nếu một đường ghi bỏ qua version, mọi đường ORM-managed khác có thể mất khả năng phát hiện dữ liệu stale.

### Quy ước cho bảng có version

Với mỗi bảng/entity có optimistic token, hãy quy định:

1. Token nào được dùng và ai tạo token mới: ORM, ứng dụng hay DBMS.
2. Mọi thay đổi có ý nghĩa nghiệp vụ có phải làm token thay đổi không?
3. Bulk/native SQL phải tăng token theo cách nào?
4. Những thao tác nào cần so sánh với expected token từ client?
5. Khi affected rows bằng 0, API phân biệt conflict và not found thế nào?
6. Persistence context/change tracker được clear hoặc reload ra sao sau bulk DML?

## 12. Xử lý optimistic conflict ở tầng ứng dụng/API

Optimistic conflict không nhất thiết là lỗi hệ thống. Nó cho biết dữ liệu đã thay đổi kể từ khi client đọc. Cách phản hồi phụ thuộc loại ứng dụng.

### Web form hoặc REST API

Client có thể gửi version cùng dữ liệu chỉnh sửa:

```json
{
  "id": 10,
  "name": "Keyboard Pro",
  "version": 7
}
```

Server cập nhật với điều kiện `id = 10 AND version = 7`. Nếu thành công, server trả dữ liệu mới với version 8. Nếu không, server có thể trả `409 Conflict` hoặc dùng HTTP conditional request với `ETag`/`If-Match` và `412 Precondition Failed` khi điều kiện không khớp.

Ví dụ:

```http
ETag: "product-10-v7"
If-Match: "product-10-v7"
```

ETag phải đại diện cho phiên bản tài nguyên đủ để phát hiện thay đổi có liên quan. Nếu response được tổng hợp từ nhiều hàng, một version của riêng hàng gốc có thể không đủ.

### Người dùng có thể chọn hợp nhất

Khi xung đột, ứng dụng có thể:

- Tải lại dữ liệu mới và yêu cầu người dùng áp dụng lại thay đổi.
- Hiển thị giá trị cũ và giá trị mới để người dùng chọn.
- Hợp nhất tự động nếu các trường được sửa độc lập và quy tắc nghiệp vụ cho phép.
- Từ chối thay đổi nếu thao tác không thể áp dụng an toàn vào trạng thái mới.

Không nên tự động ghi lại toàn bộ object cũ lên object mới chỉ để “retry”. Làm vậy có thể lặp lại lost update. Retry phải đọc lại trạng thái, tính toán lại và xác định thay đổi nào còn hợp lệ.

## 13. Retry và ranh giới transaction

Khi ORM báo optimistic locking failure, transaction hiện tại thường không còn phù hợp để tiếp tục commit. Ứng dụng cần rollback và bắt đầu transaction mới nếu muốn thử lại.

Một quy trình retry an toàn:

1. Nhận diện đúng optimistic conflict từ provider/driver.
2. Rollback transaction hiện tại.
3. Đọc lại entity và version mới trong transaction mới.
4. Áp dụng lại ý định nghiệp vụ, không nhất thiết áp dụng nguyên trạng toàn bộ snapshot cũ.
5. Kiểm tra lại các invariant và điều kiện nghiệp vụ.
6. Thử commit; giới hạn số lần retry.

Không retry vô hạn. Nếu người dùng liên tục chỉnh cùng một bản ghi nóng, retry có thể gây starvation và tăng tải. Trong trường hợp xung đột thường xuyên, cần cân nhắc khóa bi quan cho phạm vi hẹp, cập nhật nguyên tử hoặc thiết kế lại mô hình dữ liệu.

Nếu transaction có gửi email, gọi thanh toán hoặc phát message, retry không được lặp tác động bên ngoài. Hãy dùng idempotency key hoặc transactional outbox để tác động có thể được gửi lại an toàn.

## 14. Những trường hợp version check không đủ

Version trên một entity chỉ bảo vệ việc cập nhật entity đó. Nó không tự bảo vệ mọi bất biến liên quan đến nhiều entity.

Ví dụ, hai transaction cùng đọc hai hàng bác sĩ đang trực, rồi mỗi transaction tắt một hàng khác nhau. Nếu mỗi hàng có version riêng, cả hai update có thể khớp version của hàng mình sửa. Kết quả cuối có thể không còn bác sĩ trực nào. Đây là write skew.

Để bảo vệ invariant nhiều hàng, cần cơ chế rộng hơn như:

- Constraint trực tiếp nếu DBMS biểu diễn được.
- Guard row hoặc advisory lock theo phạm vi nghiệp vụ.
- Mức cô lập `SERIALIZABLE` và xử lý serialization failure.
- Mô hình dữ liệu tổng hợp có cập nhật nguyên tử.

Không nâng version của từng entity một cách máy móc rồi cho rằng toàn bộ aggregate đã được bảo vệ. Cần xác định aggregate boundary và tất cả dữ liệu mà quy tắc phụ thuộc.

## 15. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Có cột version nhưng không ánh xạ `@Version`/concurrency token | ORM không thêm điều kiện kiểm tra | Cấu hình mapping và kiểm thử SQL sinh ra |
| Native SQL chỉ lọc theo ID | Ghi đè dữ liệu mới mà không phát hiện stale state | Thêm expected version vào WHERE và tăng token |
| Bulk update không tăng version | Entity đã load trước đó vẫn có thể flush với version cũ | Tăng version cho mọi hàng bị thay đổi khi chính sách yêu cầu |
| Bulk update chạy khi persistence context còn entity cũ | Bộ nhớ và database không đồng bộ | Flush trước, clear hoặc reload sau bulk DML |
| Bỏ qua affected rows | Ứng dụng báo thành công dù update không khớp version | Kiểm tra số hàng bị ảnh hưởng |
| Dùng một expected version cho hàng loạt entity | Không kiểm tra được version riêng của từng hàng | Dùng danh sách ID/version hoặc chính sách bulk rõ ràng |
| Tự tăng DB-generated rowversion | SQL lỗi hoặc token không hợp lệ | Để DBMS sinh token và chỉ dùng token cũ trong predicate |
| Retry cùng snapshot cũ | Lặp lại lost update | Rollback, đọc lại và áp dụng lại ý định nghiệp vụ |
| Nghĩ entity version bảo vệ invariant nhiều hàng | Có thể vẫn gặp write skew | Dùng constraint, guard, serializable hoặc mô hình dữ liệu phù hợp |

## 16. Quy trình thiết kế khi ORM và SQL trực tiếp cùng tồn tại

Khi một bảng được cập nhật từ cả entity ORM lẫn bulk/native SQL, hãy thống nhất hợp đồng trước khi triển khai:

1. **Chọn token:** numeric version, timestamp hay token do DBMS sinh; xác định phạm vi token.
2. **Cấu hình ORM:** ánh xạ `@Version` hoặc concurrency token và xác nhận ORM tạo WHERE theo version gốc.
3. **Định nghĩa bulk semantics:** thao tác có compare với version từ client hay cập nhật mọi hàng thỏa predicate tại thời điểm chạy?
4. **Viết SQL có chủ đích:** thêm version predicate khi cần compare-and-swap; tăng version nếu thay đổi phải làm stale các entity đã đọc.
5. **Kiểm tra kết quả:** affected rows bằng 0 phải được xử lý, không được bỏ qua.
6. **Đồng bộ cache/persistence context:** flush trước và clear/reload/refresh sau bulk DML theo phạm vi phù hợp.
7. **Kiểm tra mọi đường ghi:** job nền, trigger, script, batch import và service khác có tuân thủ token không?
8. **Thiết kế conflict response:** trả lỗi, hợp nhất hay retry toàn bộ transaction.
9. **Kiểm thử cạnh tranh:** hai session cùng đọc một version, sau đó ORM update và SQL bulk/native update chạy xen kẽ.
10. **Theo dõi:** đo số conflict, affected rows bằng 0, retry, deadlock và thời gian transaction.

## 17. Kịch bản kiểm thử minh họa

Để chứng minh cả đường ORM và SQL trực tiếp tuân thủ cùng hợp đồng, hãy kiểm thử hai session trên cùng một hàng.

**Kịch bản A — ORM-managed update phát hiện stale entity**

1. Session A đọc Product 10, version 7.
2. Session B đọc Product 10, version 7.
3. A sửa giá và flush; DB chuyển version thành 8.
4. B sửa tên và flush với version 7.
5. B nhận optimistic lock exception; dữ liệu của A vẫn được giữ.

**Kịch bản B — Native SQL làm entity ORM cũ trở nên stale**

1. Session A đọc Product 10, version 7.
2. Session B chạy native UPDATE có điều kiện `version = 7` và tăng version lên 8.
3. A flush entity với version 7.
4. ORM UPDATE không khớp hàng nào và báo optimistic lock failure.

**Kịch bản C — Native SQL quên tăng version**

1. Session A đọc Product 10, version 7.
2. Session B cập nhật giá bằng SQL chỉ lọc theo ID, không đổi version.
3. A flush entity với version 7; WHERE vẫn khớp.
4. A có thể ghi đè thay đổi của B mà không phát hiện.

Kịch bản C cho thấy chỉ cấu hình `@Version` trong entity là chưa đủ. Cần quản lý tất cả đường ghi của bảng.

Khóa lạc quan của ORM bảo vệ cập nhật entity được theo dõi bằng cách so sánh version đã đọc với version hiện tại trong database. Bulk DML và native SQL bỏ qua cơ chế theo dõi đó vì chúng ghi trực tiếp trên database. Muốn giữ tính nhất quán, câu lệnh trực tiếp phải tự kiểm tra token khi cần, tăng version khi thay đổi cần làm stale các entity cũ, kiểm tra affected rows và đồng bộ persistence context/change tracker. Khi mọi đường ghi tuân thủ cùng một hợp đồng version, ứng dụng mới phát hiện được cập nhật lỗi thời thay vì âm thầm ghi đè dữ liệu mới.

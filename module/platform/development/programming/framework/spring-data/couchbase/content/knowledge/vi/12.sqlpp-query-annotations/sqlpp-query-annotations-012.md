# Truy vấn thay đổi dữ liệu và lựa chọn kết quả RETURNING trong Couchbase SQL++

> **Mục tiêu:** Viết và đọc được các lệnh SQL++ thay đổi document (`INSERT`, `UPSERT`, `UPDATE`, `DELETE` và biết khi nào xem xét `MERGE`); chọn `RETURNING` để nhận trường, document ID hoặc dữ liệu phục vụ ánh xạ; hiểu `#{#n1ql.delete}` và `#{#n1ql.returning}` trong Spring Data Couchbase; kiểm soát phạm vi dữ liệu bị sửa, quyền truy cập, CAS/TTL, chỉ mục, giao dịch và các rủi ro của thao tác hàng loạt.

Trong module **SPRING_DATA_COUCHBASE**, tầng dữ liệu thường dùng Spring Data Repository và `CouchbaseTemplate` để lưu/đọc document theo ID. Khi biết ID, đường **Key/Value (KV)** phù hợp cho thao tác trên một document và có các cơ chế như CAS. Tuy nhiên, ứng dụng cũng có thể phải **sửa hoặc xóa nhiều document khớp điều kiện JSON** — chẳng hạn vô hiệu hóa toàn bộ sản phẩm của một danh mục. Khi đó, Couchbase **SQL++** cung cấp các lệnh thay đổi dữ liệu (Data Manipulation Language — DML).

SQL++ trước đây gọi là **N1QL**; vì vậy các biểu thức Spring Expression Language (**SpEL**) phục vụ `@Query` của Spring Data Couchbase vẫn có tên `#n1ql`. SQL++ thực thi tại Query Service; còn `#{#n1ql.delete}` và `#{#n1ql.returning}` chỉ được **Spring Data phân giải** trước khi gửi câu lệnh.

**Điểm mấu chốt:** DML thay đổi dữ liệu, còn `RETURNING` **quyết định những gì câu lệnh trả về**, không phải điều kiện để thao tác trở nên an toàn. Một lệnh `DELETE` có `RETURNING` nhưng quên `WHERE` vẫn có thể xóa toàn bộ document trong keyspace.

| Lệnh | Tác dụng chính | Ví dụ tình huống | `RETURNING` dùng để làm gì? |
| --- | --- | --- | --- |
| `INSERT` | Tạo document với key mới, không ghi đè key đã tồn tại | Tạo SKU mới | Lấy ID và giá trị vừa tạo |
| `UPSERT` | Tạo mới hoặc thay thế document cùng key | Đồng bộ snapshot theo ID | Xác nhận dữ liệu sau khi upsert |
| `UPDATE` | Sửa field của document phù hợp điều kiện | Đổi giá, đánh dấu inactive | Lấy field/metadata sau sửa |
| `DELETE` | Xóa document phù hợp điều kiện | Dọn dữ liệu được phép xóa | Trả thông tin document bị xóa |
| `MERGE` | Kết hợp logic thêm/cập nhật/xóa theo matching source-target | Đồng bộ nhiều bản ghi | Trả kết quả theo phiên bản/cú pháp được hỗ trợ |

## 1. Mô hình dữ liệu, keyspace và phạm vi an toàn

Giả sử ứng dụng bán hàng quản lý:

| Thành phần | Giá trị minh họa |
| --- | --- |
| Bucket | `catalog` |
| Scope | `commerce` |
| Collection | `products` |
| Keyspace đầy đủ | `catalog.commerce.products` |
| Spring Data entity | `Product` |
| Repository | `ProductRepository` |

Tạo ba document mẫu bằng một cách ghi **tương thích converter** của Spring Data. Để các câu SQL++ minh họa về type filter dễ hiểu, body được biểu diễn với discriminator `_class` là `catalog-product`. Đây chỉ là ví dụ về một cấu hình type alias; trường type và giá trị thật phải được xác nhận theo project.

**Document ID: `product::KB-101`**

```json
{
  "_class": "catalog-product",
  "sku": "KB-101",
  "category": "keyboard",
  "name": "Bàn phím cơ TKL",
  "price": 1450000,
  "stock": 10,
  "active": true,
  "tenantId": "shop-a"
}
```

**Document ID: `product::KB-202`**

```json
{
  "_class": "catalog-product",
  "sku": "KB-202",
  "category": "keyboard",
  "name": "Bàn phím không dây",
  "price": 1950000,
  "stock": 3,
  "active": true,
  "tenantId": "shop-a"
}
```

**Document ID: `product::MS-301`**

```json
{
  "_class": "catalog-product",
  "sku": "MS-301",
  "category": "mouse",
  "name": "Chuột văn phòng",
  "price": 420000,
  "stock": 0,
  "active": false,
  "tenantId": "shop-b"
}
```

Ví dụ còn giả định collection có thể có các entity khác như `Promotion` hoặc document legacy thiếu discriminator. Vì vậy, mọi DML dưới đây cần giới hạn rõ **keyspace, loại document, tenant, điều kiện nghiệp vụ**, thay vì cho rằng mọi JSON trong collection đều là `Product`.

Entity Java:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.TypeAlias;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.repository.Collection;
import org.springframework.data.couchbase.repository.Scope;

@Document
@TypeAlias("catalog-product")
@Scope("commerce")
@Collection("products")
public class Product {
    @Id
    private String id;

    @Version
    private long version;

    private String sku;
    private String category;
    private String name;
    private Long price;
    private Integer stock;
    private Boolean active;
    private String tenantId;

    public Product() {}

    // Getters/setters hoặc constructor theo quy ước ứng dụng.
}
```

Bucket `catalog` được chọn trong cấu hình Spring Data. `@Id` đại diện **document key**, không bắt buộc là field `id` trong body; `@Version` có thể dùng CAS cho optimistic locking. Khi thao tác SQL++ trực tiếp, bạn **không tự động đi qua các callback, converter hay kiểm tra phiên bản của `repository.save`**.

### Hai nguyên tắc trước khi chạy mọi lệnh DML

1. **Xác định tập document:** đọc trước bằng `SELECT` có `FROM` và `WHERE` tương đương, kiểm tra ID, type discriminator, tenant và số hàng dự kiến.
2. **Xác định hợp đồng kết quả:** cần biết đã sửa bao nhiêu document, cần ID để audit, cần giá trị sau sửa hay cần trả lại entity trước khi xóa? Chọn `RETURNING` và kiểu Java phù hợp thay vì mặc định mọi DML luôn trả `Product`.

> Các truy vấn `INSERT/UPDATE/DELETE` trong bài là ví dụ **thay đổi dữ liệu thật nếu được chạy**. Hãy chỉ thực hành trên bucket/collection dành riêng cho lab hoặc môi trường thử nghiệm, không dán thẳng vào production.

## 2. `INSERT`: tạo document mới với ID duy nhất

Để thêm một sản phẩm có document key `product::HS-401`:

```sql
INSERT INTO `catalog`.`commerce`.`products` (KEY, VALUE)
VALUES (
  "product::HS-401",
  {
    "_class": "catalog-product",
    "sku": "HS-401",
    "category": "headset",
    "name": "Tai nghe có dây",
    "price": 850000,
    "stock": 6,
    "active": true,
    "tenantId": "shop-a"
  }
)
RETURNING META().id AS documentId, sku, category, price;
```

Với ID chưa tồn tại, câu lệnh tạo một document và trả về hàng có `documentId`, `sku`, `category`, `price`. `META().id` là **ID do Couchbase quản lý**, không phải field tùy ý trong JSON body.

**`INSERT` không ghi đè document đã có cùng key.** Nếu gọi lại với key `product::HS-401` mà document vẫn tồn tại, thao tác sẽ gặp lỗi key trùng thay vì cập nhật như `UPSERT`.

### Lấy thông tin trả về ít nhất đủ dùng

```sql
INSERT INTO `catalog`.`commerce`.`products` (KEY, VALUE)
VALUES (
  "product::HS-402",
  {
    "_class": "catalog-product",
    "sku": "HS-402",
    "category": "headset",
    "name": "Tai nghe không dây",
    "price": 1250000,
    "stock": 8,
    "active": true,
    "tenantId": "shop-a"
  }
)
RETURNING META().id AS documentId;
```

Khi API chỉ cần xác nhận document key, trả toàn bộ body sẽ làm tăng kích thước kết quả mà không thêm giá trị nghiệp vụ.

### Không nhầm `INSERT` SQL++ với `repository.save`

`repository.save(product)` sử dụng cơ chế mapping của Spring Data. `INSERT` viết tay phải chuẩn bị **đúng field JSON lưu thực tế**, bao gồm type discriminator nếu đọc lại qua Repository cần nó. Nếu có `@Field` đổi tên thuộc tính, `INSERT` SQL++ không tự biết tên Java tương ứng.

Khi chỉ thêm một document đã biết ID, API Key/Value hoặc Repository thường dễ kiểm soát hơn. SQL++ `INSERT` hữu ích cho những workflow dựng document từ câu truy vấn hay import hàng loạt theo điều kiện.

## 3. `UPSERT`: thêm mới hoặc thay thế document

`UPSERT` kết hợp hành vi insert và thay thế đối với cùng một document key:

```sql
UPSERT INTO `catalog`.`commerce`.`products` (KEY, VALUE)
VALUES (
  "product::KB-202",
  {
    "_class": "catalog-product",
    "sku": "KB-202",
    "category": "keyboard",
    "name": "Bàn phím không dây phiên bản mới",
    "price": 1890000,
    "stock": 5,
    "active": true,
    "tenantId": "shop-a"
  }
)
RETURNING META().id AS documentId, name, price, stock;
```

Nếu key đã tồn tại, `UPSERT` ghi **document value mới** chứ không chỉ cập nhật một field đã được nêu trong JSON. Vì vậy, nếu body mới thiếu `tenantId`, `category` hoặc discriminator thì các field ấy có thể biến mất khỏi document sau thao tác.

| Trường hợp | `INSERT` | `UPSERT` |
| --- | --- | --- |
| Key chưa tồn tại | Tạo mới | Tạo mới |
| Key đã tồn tại | Lỗi trùng key | Thay thế giá trị document |
| Cần giữ những field khác không truyền vào | Không áp dụng | **Không được giả định sẽ giữ** |
| Muốn thay đúng một field của document hiện hữu | Không phù hợp | Cẩn thận vì thay thế body; xem `UPDATE` hoặc KV sub-document |

**Phân biệt UPSERT với cập nhật có CAS:** UPSERT SQL++ không tự dùng `@Version` của Spring Data để bảo vệ cập nhật dựa trên bản đọc cũ. Nếu nghiệp vụ không cho phép ghi đè concurrent update, cần một cơ chế kiểm tra phiên bản/transaction phù hợp; đừng chỉ đổi `INSERT` thành `UPSERT` để xử lý lỗi trùng key.

## 4. `UPDATE`: sửa field theo điều kiện JSON

`UPDATE` thay đổi field của document đã tồn tại. Với ví dụ cần giảm giá 5% cho sản phẩm keyboard đang hoạt động của tenant `shop-a`:

```sql
UPDATE `catalog`.`commerce`.`products` AS p
SET p.price = ROUND(p.price * 0.95)
WHERE p._class = "catalog-product"
  AND p.tenantId = "shop-a"
  AND p.category = "keyboard"
  AND p.active = true
  AND ISNUMBER(p.price)
RETURNING META(p).id AS documentId,
          p.sku AS sku,
          p.price AS newPrice;
```

Nếu chạy câu này trên **bộ dữ liệu gốc** (trước khi thực hiện những DML ở phần khác), hai sản phẩm KB-101 và KB-202 được cập nhật. Giá sau giảm lần lượt là 1.377.500 và 1.852.500 đồng. Việc kiểm tra `ISNUMBER(p.price)` tránh tính toán trên những document có giá `NULL`, `MISSING` hoặc không phải kiểu số.

**Mỗi ví dụ DML trong bài nên chạy độc lập trên dữ liệu mẫu được khôi phục**, trừ khi phần thực hành yêu cầu thực thi nối tiếp. Nếu đã chạy `UPSERT` ở phần 3 trước, số liệu dùng trong phép tính trên sẽ khác.

### `SET`, `UNSET` và khác biệt `NULL/MISSING`

Giả sử document `KB-101` có field `promotionCode` cần xóa:

```sql
UPDATE `catalog`.`commerce`.`products` AS p
USE KEYS "product::KB-101"
UNSET p.promotionCode
RETURNING META(p).id AS documentId,
          p.promotionCode AS promotionCode;
```

`UNSET` xóa trường khỏi JSON body: `p.promotionCode` trở thành **MISSING**. Vì phép chiếu `MISSING` có thể bị lược khỏi hàng JSON, kết quả chỉ còn `documentId`. Nếu dùng `SET p.promotionCode = NULL`, field vẫn tồn tại nhưng chứa JSON null. Hai thao tác có ngữ nghĩa khác nhau.

Nếu cần lưu lại một giá trị:

```sql
UPDATE `catalog`.`commerce`.`products` AS p
USE KEYS "product::KB-101"
SET p.active = false
WHERE p._class = "catalog-product"
  AND p.tenantId = "shop-a"
RETURNING META(p).id AS documentId,
          p.active AS isActive;
```

Ở đây `USE KEYS` giới hạn ứng viên cập nhật vào một document ID đã biết; `WHERE` giữ thêm điều kiện type và tenant. **Không bỏ kiểm tra quyền/tenant chỉ vì câu lệnh có `USE KEYS`.**

### Cập nhật field nested

Giả sử product có:

```json
{
  "specs": {
    "connection": "wired",
    "layout": "TKL"
  }
}
```

Khi field cha `specs` tồn tại đúng kiểu object, SQL++ có thể cập nhật field con:

```sql
UPDATE `catalog`.`commerce`.`products` AS p
USE KEYS "product::KB-101"
SET p.specs.connection = "wireless"
WHERE p._class = "catalog-product"
  AND ISOBJECT(p.specs)
RETURNING p.sku AS sku,
          p.specs.connection AS connection;
```

Nếu `specs` có thể `NULL/MISSING` hoặc sai kiểu, cần có quy tắc khởi tạo object trước khi gán field con. Không mặc định mọi JSON document đều có cùng cấu trúc.

### Cập nhật tồn kho: điều kiện bảo vệ không phải transaction hoàn chỉnh

Một ví dụ nghiệp vụ:

```sql
UPDATE `catalog`.`commerce`.`products` AS p
USE KEYS "product::KB-101"
SET p.stock = p.stock - 2
WHERE p._class = "catalog-product"
  AND p.tenantId = "shop-a"
  AND ISNUMBER(p.stock)
  AND p.stock >= 2
RETURNING META(p).id AS documentId,
          p.stock AS remainingStock;
```

Với dữ liệu gốc, hàng trả về có `remainingStock = 8`. Nếu không có document nào đạt điều kiện, `RETURNING` không tạo hàng cho document đó. Nhưng **không xem điều kiện này là giải pháp hoàn chỉnh cho giao dịch bán hàng**, đặc biệt khi cập nhật tồn kho liên quan tới đơn hàng, thanh toán và cạnh tranh cao. Cần đánh giá cơ chế transaction hoặc thao tác KV với CAS, khả năng retry và idempotency theo toàn bộ quy trình.

### Vì sao thiếu `WHERE` rất nguy hiểm?

```sql
-- VÍ DỤ NGUY HIỂM, KHÔNG CHẠY:
UPDATE `catalog`.`commerce`.`products` AS p
SET p.active = false
RETURNING META(p).id;
```

Không có `WHERE` hoặc `USE KEYS`, lệnh có thể cập nhật **mọi document trong keyspace**. Một `LIMIT` nhỏ chỉ giới hạn số document bị tác động trong một lần thực thi, **không thay thế tập điều kiện**; không nên dựa vào `LIMIT` mà thiếu key/type/tenant filter để chọn đúng document.

## 5. `DELETE`: xóa có kiểm soát và nhận dữ liệu đã xóa

`DELETE` xóa document trong keyspace. Với yêu cầu xóa một document cụ thể được phép:

```sql
DELETE FROM `catalog`.`commerce`.`products` AS p
USE KEYS "product::MS-301"
WHERE p._class = "catalog-product"
  AND p.tenantId = "shop-b"
  AND p.active = false
RETURNING META(p).id AS documentId,
          p.sku AS sku,
          p.category AS category;
```

Khi chạy độc lập trên dữ liệu gốc, chỉ document `product::MS-301` khớp điều kiện. `RETURNING` có thể cung cấp ID, SKU và category của **document vừa bị xóa** để ứng dụng biết kết quả hoặc tạo bản ghi audit.

**Không nhầm `DELETE ... RETURNING` với lệnh “đọc lại document”.** Document đã bị xóa khỏi collection; hàng `RETURNING` chỉ là dữ liệu trả về của thao tác, không có nghĩa đối tượng vẫn còn tồn tại để cập nhật tiếp.

### Xóa theo bộ lọc: phải tách bước xem trước

Trước khi xóa hàng loạt những sản phẩm ngừng kinh doanh, khảo sát tập ứng viên:

```sql
SELECT META(p).id AS documentId,
       p.sku,
       p.tenantId
FROM `catalog`.`commerce`.`products` AS p
WHERE p._class = "catalog-product"
  AND p.tenantId = "shop-b"
  AND p.active = false;
```

Sau khi kiểm tra tập ID, quyền và kế hoạch rollback, mới thực hiện câu DML có cùng điều kiện:

```sql
DELETE FROM `catalog`.`commerce`.`products` AS p
WHERE p._class = "catalog-product"
  AND p.tenantId = "shop-b"
  AND p.active = false
RETURNING META(p).id AS documentId, p.sku AS sku;
```

**Xem trước bằng `SELECT` không khóa tập document.** Trong thời gian giữa `SELECT` và `DELETE`, document có thể được thêm/sửa/xóa. Nếu nghiệp vụ cần đảm bảo tập ứng viên không đổi, phải có chiến lược đồng bộ/transaction phù hợp hoặc kiểm tra lại điều kiện và version, không xem hai câu lệnh tách rời là một snapshot bất biến.

### Lỗi `AND/OR` có thể vượt qua bộ lọc tenant

Đoạn sau có thể xóa ngoài phạm vi mong muốn:

```sql
-- VÍ DỤ PHẢN DIỆN, KHÔNG CHẠY:
DELETE FROM `catalog`.`commerce`.`products` AS p
WHERE p.tenantId = "shop-a" AND p.active = false
   OR p.stock = 0;
```

Vì `AND` có ưu tiên cao hơn `OR`, nhánh `p.stock = 0` có thể được chọn **không cần tenant shop-a**. Đặt ngoặc đúng:

```sql
DELETE FROM `catalog`.`commerce`.`products` AS p
WHERE p._class = "catalog-product"
  AND p.tenantId = "shop-a"
  AND (p.active = false OR p.stock = 0)
RETURNING META(p).id AS documentId;
```

Ngay cả câu sau cũng **chỉ được chạy nếu yêu cầu nghiệp vụ thực sự cho phép xóa những sản phẩm đó**. Dùng `RETURNING` để kiểm tra hậu quả không thay thế việc review câu `WHERE` trước khi thực thi.

### Xóa theo ID hay theo điều kiện?

Nếu đã biết ID và cần xóa một document, `repository.deleteById(id)` hoặc KV remove thường là lựa chọn đơn giản, có thể kết hợp CAS nếu API/phiên bản hỗ trợ. `DELETE` SQL++ phù hợp hơn khi cần xóa **theo tập điều kiện** hoặc dùng kết quả `RETURNING` cho báo cáo/kiểm toán. Cả hai đường phải thực thi chính sách tenant và phân quyền nhất quán.

## 6. `RETURNING`: lựa chọn hình dạng kết quả

SQL++ cho phép đặt `RETURNING` **sau các mệnh đề thay đổi dữ liệu** để nhận kết quả của các document đã được thao tác. Ý nghĩa của nó gần với phép chiếu `SELECT`, nhưng **nguồn dữ liệu là thao tác DML vừa được thực thi**.

| Lựa chọn | Hình dạng kết quả | Khi nào phù hợp? |
| --- | --- | --- |
| Không có `RETURNING` | Không có hàng dữ liệu DML cần trả về | Chỉ quan tâm thành công/thất bại hoặc số mutation từ metrics |
| `RETURNING *` | Các field/document theo cách bộ máy chiếu kết quả, có thể bọc dưới tên keyspace | Debug trên lab hoặc cần toàn bộ body |
| `RETURNING META().id AS documentId` | Hàng object chỉ chứa ID | Audit danh sách document bị tác động |
| `RETURNING sku AS sku, price AS price` | Hàng object với field cụ thể | Trả response DTO nhẹ |
| `RETURNING RAW META().id` | Mỗi hàng là một giá trị ID đơn | Luồng chỉ cần danh sách ID |
| `#{#n1ql.returning}` trong Spring Data | Phép chiếu `RETURNING` phục vụ ánh xạ entity | `@Query` xóa và trả entity tương thích mapper |

### `RETURNING *` khác `RETURNING p.sku, p.price`

Ví dụ cập nhật một document:

```sql
UPDATE `catalog`.`commerce`.`products` AS p
USE KEYS "product::KB-101"
SET p.active = false
RETURNING *;
```

`RETURNING *` có thể trả một object chứa toàn bộ document được bọc theo keyspace/alias, tương tự đặc điểm của `SELECT *`. Không mặc định nó có cấu trúc Java DTO mong đợi hoặc sẽ phơi bày riêng document ID theo tên `id`.

Một phép chiếu xác định rõ tên field:

```sql
UPDATE `catalog`.`commerce`.`products` AS p
USE KEYS "product::KB-101"
SET p.active = false
RETURNING META(p).id AS documentId,
          p.sku AS sku,
          p.active AS active;
```

Kết quả nghiệp vụ từ dữ liệu gốc:

```json
[
  {
    "documentId": "product::KB-101",
    "sku": "KB-101",
    "active": false
  }
]
```

Đây là **hình dạng minh họa** của mảng kết quả, không bao gồm envelope metadata `requestId`, metrics của Query Service và không hàm ý đã chạy query thực tế.

### `RETURNING RAW` dành cho kết quả scalar

Nếu chỉ cần ID của những document đã được cập nhật:

```sql
UPDATE `catalog`.`commerce`.`products` AS p
USE KEYS "product::KB-101"
SET p.active = false
RETURNING RAW META(p).id;
```

Hàng trả về là **chuỗi ID**, không phải object có key `documentId`. Vì vậy, mã Java phải dùng bộ giải mã kết quả scalar phù hợp; không cố gắng dùng `rowsAsObject()` cho query `RETURNING RAW`.

### `RETURNING` trên `INSERT`, `UPDATE`, `DELETE` có giống nhau?

Không hoàn toàn:

| Lệnh | Dữ liệu `RETURNING` mô tả | Lưu ý |
| --- | --- | --- |
| `INSERT` | Document vừa thêm vào keyspace | Có thể lấy ID vừa tạo |
| `UPSERT` | Document được tạo/thay thế theo key | Có thể đã thay toàn bộ body cũ |
| `UPDATE` | Document sau khi áp dụng thay đổi | Không tự trả cả “before” và “after” |
| `DELETE` | Dữ liệu của document thuộc thao tác xóa | Document không còn trong keyspace sau xóa thành công |
| `MERGE` | Kết quả của những action DML theo câu lệnh | Phải xem loại action và query thực tế |

Một `UPDATE ... RETURNING p.price` trả giá sau cập nhật, **không có nghĩa nó trả giá cũ**. Nếu một hệ thống audit bắt buộc lưu cả giá trước và sau, cần cơ chế audit/changelog hoặc workflow transaction/CDC thích hợp. Không suy diễn từ `RETURNING` rằng Couchbase tự lưu lịch sử document.

### `RETURNING` không phải điều kiện thành công

Query Service xử lý DML và gửi metadata trạng thái. Với thao tác không khớp document nào, kết quả trả về có thể là mảng hàng rỗng. Một câu `DELETE` chạy hợp lệ nhưng xóa **0 document** vẫn có thể được xem là thành công về mặt thực thi.

Mặt khác, khi không dùng `RETURNING`, hàng dữ liệu trả về có thể rỗng **dù đã có document được thay đổi**. Muốn quan sát số lượng tác động, hãy sử dụng query metrics nếu được bật và được SDK hỗ trợ, hoặc thiết kế hợp đồng trả về phù hợp — không dùng độ dài `rowsAsObject()` của câu lệnh không có `RETURNING` làm số mutation.

### Giới hạn dữ liệu trả về

`RETURNING *` có thể làm kết quả rất lớn với hàng trăm nghìn document và dễ đưa dữ liệu nội bộ vào log/API. Chỉ trả những trường thực sự cần, chẳng hạn ID, SKU và trạng thái mới. Nếu cần xuất lịch sử xóa phục vụ kiểm toán, cân nhắc quy trình lưu audit riêng với chính sách truy cập và lưu trữ phù hợp thay vì dựa vào một response DML có thể mất khi client lỗi mạng.

## 7. `MERGE`: lựa chọn khi cần thay đổi theo nguồn dữ liệu khác

`MERGE` kết hợp dữ liệu **source** và **target** rồi thực hiện action dựa trên điều kiện match. Theo cú pháp SQL++ hiện đại, `MERGE` có thể áp dụng `WHEN MATCHED` và `WHEN NOT MATCHED` để cập nhật/chèn/xóa theo từng nhánh.

Ví dụ chỉ để minh họa nhánh **cập nhật** từ một tập nguồn nhỏ:

```sql
MERGE INTO `catalog`.`commerce`.`products` AS p
USING [
  { "documentId": "product::KB-101", "nextPrice": 1490000 },
  { "documentId": "product::KB-202", "nextPrice": 1790000 }
] AS src
ON META(p).id = src.documentId
   AND p._class = "catalog-product"
   AND p.tenantId = "shop-a"
WHEN MATCHED THEN
  UPDATE SET p.price = src.nextPrice
RETURNING META(p).id AS documentId, p.price AS newPrice;
```

Ví dụ này dựa trên dạng **ANSI MERGE**; việc chọn chiến lược join và index trên target có thể ảnh hưởng điều kiện thực thi và hiệu năng. Nếu không cần đọc từ nhiều nguồn hay áp dụng nhiều action, `UPDATE` thông thường thường dễ kiểm tra hơn.

**Không nhầm `MERGE` với `UPSERT`:** `UPSERT` thao tác theo document key và body mới; `MERGE` ghép một nguồn với target theo điều kiện và có thể chọn hành động khác nhau. Khi chuyển dữ liệu liên collection, cần xem khả năng tạo key mới, type discriminator, TTL và các trường không được truyền qua phép chiếu.

### Cần lưu ý với `MERGE ... RETURNING`

Kết quả `RETURNING` có thể gồm nhiều hàng từ các action khác nhau; nếu API cần phân biệt “đã chèn” và “đã cập nhật”, phải định nghĩa rõ cách suy ra hoặc lưu loại hành động. Không nên mặc nhiên cho rằng `RETURNING` có một field chuẩn tên `action` nếu SQL++ không tạo field ấy.

Với merge lớn, cần chuẩn bị index và quyền cho cả **source** lẫn **target**, kiểm tra `EXPLAIN` và xem điều kiện concurrency/transaction. Thử trước trên collection lab với số lượng document đã biết.

## 8. Spring Data Couchbase: `#{#n1ql.delete}` và `#{#n1ql.returning}`

Spring Data Couchbase cung cấp hai biến SpEL phục vụ trường hợp xóa bằng `@Query`:

| Biểu thức SpEL | Mục đích | Khác với |
| --- | --- | --- |
| `#{#n1ql.delete}` | Sinh phần `DELETE FROM ...` cho entity/keyspace của Repository | `#{#n1ql.selectEntity}` dành cho `SELECT/FROM` |
| `#{#n1ql.returning}` | Sinh mệnh đề `RETURNING` với các trường và metadata phục vụ mapping entity | `RETURNING sku, price` chỉ là phép chiếu tùy chọn |
| `#{#n1ql.filter}` | Lọc theo type discriminator của entity | `WHERE tenantId = ...` của nghiệp vụ/quyền |

Tài liệu Spring Data Couchbase có ví dụ kiểu:

```java
@Query("#{#n1ql.delete} WHERE #{#n1ql.filter} "
     + "AND username = $1 #{#n1ql.returning}")
UserInfo removeUser(String username);
```

Trên entity `Product` minh họa, có thể khai báo phương thức:

```java
import org.springframework.data.couchbase.repository.CouchbaseRepository;
import org.springframework.data.couchbase.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ProductRepository
        extends CouchbaseRepository<Product, String> {

    @Query("#{#n1ql.delete} WHERE #{#n1ql.filter} "
         + "AND META().id = $id "
         + "AND tenantId = $tenantId "
         + "#{#n1ql.returning}")
    Product deleteAndReturnForTenant(
        @Param("id") String documentId,
        @Param("tenantId") String trustedTenantId
    );
}
```

Ví dụ gọi trong service:

```java
Product deleted = productRepository.deleteAndReturnForTenant(
    "product::MS-301", "shop-b"
);
```

Với discriminator và tenant tương thích, mục tiêu là **xóa đúng một document** và lấy hàng kết quả có đủ dữ liệu để Spring Data dựng `Product`. Tuy nhiên, **kiểu trả về và hành vi khi không có kết quả phải được kiểm tra theo phiên bản Spring Data đang dùng**; ví dụ trên không thay thế kiểm thử tích hợp.

### Giải thích từng phần

```text
#{#n1ql.delete}    WHERE  #{#n1ql.filter}
      |                         |
  DELETE FROM                type discriminator
      |
      +-- AND META().id = $id AND tenantId = $tenantId
                                     |
                             điều kiện nghiệp vụ/quyền

#{#n1ql.returning}
      |
  RETURNING đủ phép chiếu phục vụ entity mapping
```

**Không đặt từ khóa `DELETE FROM` trước `#{#n1ql.delete}`**; biến này đã sinh phần đầu tương ứng. **Không đặt thêm `RETURNING` trước `#{#n1ql.returning}`**; nó đã là mệnh đề RETURNING. Một câu chỉ được có một mệnh đề `WHERE` chứa các điều kiện kết hợp.

### Vì sao cần `#n1ql.returning` thay vì `RETURNING *`?

Spring Data có hợp đồng mapping riêng cho ID/CAS. Một `RETURNING *` có thể tạo JSON bọc theo alias và thiếu phép chiếu metadata theo đúng tên mà converter cần. Biến `#n1ql.returning` được Spring Data định nghĩa để tạo **phép chiếu thích hợp khi muốn dựng entity trả về từ câu xóa**.

Đừng tự hardcode một danh sách alias lấy từ một phiên bản parser khác. Nếu mục tiêu chỉ là ID và SKU để audit, API SDK và phép chiếu `RETURNING META().id AS documentId, sku AS sku` có thể rõ hơn việc dựng lại toàn bộ entity vừa xóa.

### Xóa không có nghĩa entity vẫn dùng được để `save`

Object `deleted` ở ví dụ trên là **ảnh dữ liệu trả về sau thao tác xóa**, không phải entity còn tồn tại trong database. Đem nó gọi `repository.save(deleted)` sau đó có thể tạo/sửa dữ liệu theo semantics của repository và CAS, không phải “khôi phục an toàn” mặc định.

Nếu cần chức năng hoàn tác, phải thiết kế riêng: lưu audit/bản sao có kiểm soát, chính sách quyền, TTL và quy trình phục hồi idempotent. Không dựa vào object trả về ở bộ nhớ như một bản sao lưu bền vững.

### Có dùng `@Query UPDATE` với entity như `SELECT` không?

SQL++ hỗ trợ `UPDATE` và `RETURNING`, nhưng Spring Data Couchbase **không nên được giả định rằng mọi câu UPDATE tự viết trong `@Query` sẽ tự xử lý mapping, callbacks, optimistic locking và kiểu trả về như `repository.save`**. Cú pháp và khả năng hỗ trợ DML trong Repository có thể phụ thuộc phiên bản.

Đối với cập nhật có điều kiện phức tạp và cần DTO kết quả tùy biến, dùng `CouchbaseTemplate`/Couchbase Java SDK theo API được hỗ trợ hoặc một repository tùy biến có kiểm thử tích hợp. Nếu yêu cầu sửa một entity và giữ `@Version`, phương thức `findById`, sửa đối tượng rồi `save` theo optimistic locking thường dễ làm rõ hợp đồng hơn.

### Tránh nhầm với `@Modifying` của JPA

Ví dụ SQL++ của module sử dụng:

```java
import org.springframework.data.couchbase.repository.Query;
import org.springframework.data.repository.query.Param;
```

Không sao chép nguyên các annotation `@Modifying` hoặc cú pháp tham số `:name` từ Spring Data JPA mà giả định Couchbase hỗ trợ hệt như vậy. Với Spring Data Couchbase, mẫu có `#n1ql.delete` và `#n1ql.returning` đã được tài liệu Repository mô tả tường minh.

## 9. Couchbase Java SDK: thực thi DML và đọc hàng `RETURNING`

Khi cần kiểm soát SQL++ mutation và DTO kết quả, Couchbase Java SDK có `Cluster.query(...)`. Ví dụ dưới đây cập nhật giá cho một ID đã biết và nhận ID/giá mới:

```java
import java.util.ArrayList;
import java.util.List;
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryResult;
import static com.couchbase.client.java.query.QueryOptions.queryOptions;

public class ProductPriceMutationService {
    private final Cluster cluster;

    public ProductPriceMutationService(Cluster cluster) {
        this.cluster = cluster;
    }

    public record PriceUpdate(String documentId, Long price) {}

    public List<PriceUpdate> updatePrice(
            String documentId,
            String authorizedTenantId,
            long price) {

        if (price < 0) {
            throw new IllegalArgumentException("Price must be >= 0");
        }

        String sql = """
            UPDATE `catalog`.`commerce`.`products` AS p
            USE KEYS $documentId
            SET p.price = $price
            WHERE p._class = "catalog-product"
              AND p.tenantId = $tenantId
            RETURNING META(p).id AS documentId,
                      p.price AS price
            """;

        JsonObject parameters = JsonObject.create()
            .put("documentId", documentId)
            .put("tenantId", authorizedTenantId)
            .put("price", price);

        QueryResult result = cluster.query(
            sql,
            queryOptions().parameters(parameters)
        );

        List<PriceUpdate> updated = new ArrayList<>();
        for (JsonObject row : result.rowsAsObject()) {
            updated.add(new PriceUpdate(
                row.getString("documentId"),
                row.getLong("price")
            ));
        }
        return updated;
    }
}
```

Ví dụ dùng Java 17+ (`record`, text block). `Cluster` cần được cấu hình và tái sử dụng theo vòng đời ứng dụng. `authorizedTenantId` **phải đến từ security context đã được xác thực**, không được tin một giá trị tenant do HTTP caller tự gửi.

### Tại sao dùng binding thay vì nối chuỗi?

`$documentId`, `$tenantId` và `$price` là các placeholder **giá trị SQL++**, được SDK binding từ `JsonObject`. Chúng không thể tự thay tên collection hoặc trường. Không nối `documentId` hoặc `tenantId` vào chuỗi SQL++ với dấu nháy; điều đó có thể gây lỗi escaping và rủi ro injection.

Đường dẫn keyspace `catalog.commerce.products` là **cú pháp** đã được ứng dụng kiểm soát. Nếu cần thay collection theo cấu hình, phải lựa chọn từ tập định danh tin cậy và bảo đảm authorization, không dùng placeholder `$collection` để thay `FROM`.

### Hợp đồng kết quả của ví dụ

- Trả về **một phần tử `PriceUpdate`** khi có đúng một document khớp ID, type và tenant.
- Trả về **danh sách rỗng** nếu không có document khớp, ví dụ ID sai hoặc tenant không có quyền nhìn thấy; ứng dụng phải tự quyết định cách biến kết quả đó thành response.
- Nếu query có lỗi quyền, index, binding hoặc timeout, SDK báo lỗi; **không đánh đồng exception với kết quả rỗng**.
- Dù có `RETURNING`, SDK không tự ghi một bản sao audit bền vững.

### Trường hợp `RETURNING RAW`

```sql
DELETE FROM `catalog`.`commerce`.`products` AS p
USE KEYS "product::MS-301"
WHERE p.tenantId = "shop-b"
RETURNING RAW META(p).id;
```

Kết quả mỗi hàng là scalar, do đó không parse bằng `rowsAsObject()` như ví dụ `PriceUpdate` ở trên. Khi thiết kế API, nên chọn **object row với alias** nếu muốn dùng `JsonObject` và ánh xạ DTO nhiều field; dùng `RAW` khi client thực sự mong kết quả đơn giản.

### Khi không có `RETURNING`

`QueryResult` vẫn có metadata về query và có thể có metrics khi yêu cầu. Nếu chỉ cần số mutation, cân nhắc dựa vào metrics của query theo API SDK/phiên bản, không dùng `result.rowsAsObject().size()` cho câu DML không có `RETURNING` — khi đó số hàng có thể bằng 0 dù mutation thành công.

## 10. Type discriminator, tenant và quyền của câu lệnh DML

Một collection có thể chứa nhiều loại entity. Nếu `ProductRepository` dùng `#{#n1ql.filter}` để hạn chế `Product` trong câu `SELECT`, một lệnh `UPDATE`/`DELETE` SQL++ **viết tay qua SDK** không tự được thêm điều kiện ấy.

Ví dụ được kiểm soát đầy đủ:

```sql
UPDATE `catalog`.`commerce`.`products` AS p
SET p.active = false
WHERE p._class = "catalog-product"
  AND p.tenantId = "shop-a"
  AND p.category = "keyboard"
  AND p.active = true
RETURNING META(p).id AS documentId;
```

Trong lab, alias `catalog-product` là giả định của mapping đã mô tả. Trong ứng dụng thật, type key và alias phải được lấy từ **cách Spring Data converter đã lưu dữ liệu**, không được hardcode theo ví dụ nếu cấu hình khác.

### Phân quyền phải được thực thi trên cả đường đọc và ghi

Một câu query có `tenantId = $tenantId` chưa đủ an toàn nếu tham số tenant lấy trực tiếp từ client mà không được xác thực. Service cần lấy tenant từ token/session/security context đã được ủy quyền và kiểm tra vai trò có quyền **thay đổi** dữ liệu.

Không coi `#{#n1ql.filter}` là chính sách authorization: nó chỉ giải quyết **loại entity**. Ngay cả một câu `@Query` trả đúng `Product` vẫn có thể trả document thuộc tenant khác nếu thiếu điều kiện tenant.

### RBAC của Couchbase với DML

Couchbase Query Service kiểm tra quyền theo thao tác và keyspace:

| Tình huống | Nhóm quyền cần đánh giá |
| --- | --- |
| `INSERT` | Query Insert trên target |
| `UPSERT` | Query Insert và Query Update trên target |
| `UPDATE` | Query Update trên target |
| `DELETE` | Query Delete trên target |
| `MERGE` | Query Select nguồn, quyền Insert/Update/Delete phù hợp trên target |
| DML có `RETURNING` | Có thể cần thêm Query Select trên những keyspace được đọc trong `RETURNING` |

Đây là khái quát theo tài liệu Couchbase; quyền còn phụ thuộc nhánh, subquery và các tài nguyên được truy cập. Người có quyền cập nhật document **chưa chắc có quyền đọc nội dung qua RETURNING**. Đừng dùng tài khoản quản trị để bỏ qua lỗi quyền trong môi trường production; hãy cấp quyền tối thiểu theo nghiệp vụ.

### DELETE cứng hay đánh dấu xóa?

Nhiều hệ thống cần giữ lịch sử kinh doanh, vì thế nên cân nhắc **soft delete** bằng field `active` hoặc `deletedAt`:

```sql
UPDATE `catalog`.`commerce`.`products` AS p
USE KEYS "product::KB-202"
SET p.active = false
WHERE p._class = "catalog-product"
  AND p.tenantId = "shop-a"
RETURNING META(p).id AS documentId, p.active AS active;
```

Soft delete cần quy định mọi truy vấn đọc phải loại document đã đánh dấu, hoặc chỉ cho phép người có quyền xem lịch sử. Hard delete có thể cần cho chính sách lưu trữ dữ liệu/tuân thủ nhưng phải có cơ chế audit và phê duyệt vận hành tương ứng.

## 11. Chỉ mục, `EXPLAIN` và tác động của thay đổi hàng loạt

Với câu `UPDATE` hoặc `DELETE` lọc bằng thuộc tính JSON, Query Service cần xác định tập document đích. Một secondary index phù hợp giúp tránh quét quá rộng:

```sql
CREATE INDEX idx_products_tenant_type_category_active
ON `catalog`.`commerce`.`products`(
  tenantId, _class, category, active
);
```

Đây là **index ứng viên** theo bộ lọc ví dụ. Thứ tự khóa tối ưu phụ thuộc độ chọn lọc, range predicate, `ORDER BY` ở các query đọc và thống kê dữ liệu thực. Index thuộc đúng **collection**, không thuộc tất cả collection của bucket.

### Xem kế hoạch trước khi ghi

Có thể dùng:

```sql
EXPLAIN
UPDATE `catalog`.`commerce`.`products` AS p
SET p.active = false
WHERE p.tenantId = "shop-a"
  AND p._class = "catalog-product"
  AND p.category = "keyboard"
  AND p.active = true
RETURNING META(p).id AS documentId;
```

`EXPLAIN` được dùng để nghiên cứu kế hoạch, **không phải cách chạy mutation thật**. Nó có thể giúp phát hiện index không phù hợp, quét lớn và bước Fetch. Sau đó nên dùng một câu `SELECT` tương đương để kiểm tra tập ID dự kiến trước khi thực hiện DML.

### `USE KEYS` khác lọc qua index

`UPDATE/DELETE ... USE KEYS ...` chỉ định **document key** đích, hữu ích khi caller đã biết ID. Điều này không biến truy vấn SQL++ thành thao tác có cùng hợp đồng CAS của KV API; vẫn phải xét quyền, điều kiện `WHERE` và concurrency.

Nếu chỉ sửa một document theo ID, xem xét `repository.save` hoặc KV `mutateIn`/`replace` với CAS/expiry phù hợp để tránh Query Service khi không cần. Với hàng trăm nghìn document theo category, DML SQL++ có thể đúng công cụ nhưng cần **chia lô theo quy trình vận hành**, quan sát metrics, giảm kích thước RETURNING và kiểm soát tác động lên chỉ mục.

### `LIMIT` không phải cách chọn ngẫu nhiên “an toàn”

SQL++ hỗ trợ `LIMIT` trong một số lệnh DML, nhưng nếu không có cơ chế chọn tập ID theo thứ tự xác định, giới hạn số hàng có thể dẫn đến **tập document bị thay đổi không lặp lại được**. Đặc biệt không thay thế `WHERE` bằng một câu `UPDATE ... LIMIT 100` rồi kỳ vọng “chỉ sửa 100 document đúng đối tượng”.

Một quy trình batch có thể là: truy vấn chọn ID ứng viên theo điều kiện và thứ tự rõ ràng; xử lý từng lô với kiểm tra quyền/idempotency; ghi nhận tiến độ; xử lý retry theo hợp đồng. Với thay đổi có độ rủi ro cao, thêm điều kiện kiểm tra version hoặc transaction khi phù hợp.

## 12. CAS, TTL, scan consistency và giao dịch

Các cơ chế này **không được `RETURNING` tự giải quyết**. Chúng quyết định việc cập nhật có an toàn và đúng yêu cầu vận hành hay không.

### CAS và `@Version`

Couchbase CAS giúp phát hiện document đã bị thay đổi kể từ lần đọc trước. Trong Spring Data, `@Version` có thể gắn với CAS cho **optimistic locking** khi lưu entity.

Một luồng nghiệp vụ đơn document thường theo hướng:

```java
Product p = productRepository.findById("product::KB-101")
    .orElseThrow();

p.setPrice(1500000L);
productRepository.save(p);
```

Giả định entity có `setPrice`. Nếu một luồng khác đã thay đổi document, thao tác `save` với version cũ có thể gặp `OptimisticLockingFailureException`. Khi đó cần xử lý retry bằng cách đọc lại và áp dụng lại logic nghiệp vụ, chứ không tự gán CAS bất kỳ để ghi đè.

**DML SQL++ trực tiếp không tự áp dụng hợp đồng `@Version` của `repository.save`.** Nếu muốn thao tác theo CAS, phải thiết kế cơ chế cụ thể và kiểm tra semantics cạnh tranh/transaction. Một điều kiện SQL++ đơn giản `WHERE META(p).cas = $expectedCas` không nên được coi là bảo đảm tương đương một thao tác KV compare-and-swap trong mọi tình huống tranh chấp mà không có kiểm thử.

### TTL và chính sách giữ expiration

Couchbase có thể đặt thời hạn sống cho document. `INSERT/UPSERT` có thể cần metadata expiry khi tạo data ngắn hạn; `UPDATE` có thể ảnh hưởng cách giữ hoặc đặt lại expiration tùy thuộc tham số **preserve expiry**, cấu hình bucket/collection và phiên bản.

**Không mặc định rằng cập nhật SQL++ luôn giữ nguyên TTL.** Trước khi dùng lệnh `UPDATE` hàng loạt trên session, token, job tạm hoặc document có TTL, kiểm tra tài liệu của Query Service và tùy chọn preserve expiry. `RETURNING META(p).expiration` có thể hữu ích để quan sát trạng thái expiry nếu API và quyền cho phép, nhưng việc trả metadata không tự giữ TTL.

### Scan consistency không đồng nghĩa optimistic locking

Với query sử dụng index, `NOT_BOUNDED` có thể đọc trạng thái chỉ mục hiện có mà không đợi các ghi mới nhất. `REQUEST_PLUS` có thể yêu cầu đợi index cập nhật trước khi xác định tập dữ liệu, đổi lại tăng độ trễ.

Nếu bước 1 đọc `SELECT` trên index chậm, bước 2 thực hiện `UPDATE`, việc bật `REQUEST_PLUS` không tự biến hai bước thành **một transaction**. Document vẫn có thể bị thay đổi bởi tác nhân khác trong khoảng giữa hai bước. Consistency phục vụ độ mới của query, CAS phục vụ phát hiện xung đột ở document, còn transaction phục vụ tính nguyên tử/isolation của nhóm thao tác — ba mối quan tâm khác nhau.

### Transaction cho quy trình nhiều document

Nếu việc đặt hàng cần giảm tồn kho, tạo Order và cập nhật Payment/Reservation theo một invariant chung, hãy đánh giá cơ chế **Couchbase transactions** và phương án idempotent. Một lệnh `UPDATE ... RETURNING` đơn lẻ không chứng minh toàn bộ quy trình nhiều bước đã thành công.

Với transaction có retry, đừng phát sự kiện bên ngoài (gửi email, charge payment ngoài DB) mà không tính tới khả năng logic transaction chạy lại. Thiết kế outbox/idempotency hoặc cách phối hợp phù hợp với nền tảng.

### Reactive API

Spring Data Couchbase Reactive Repository, `ReactiveCouchbaseTemplate` hoặc reactive SDK thay đổi **cách lập trình kết quả**, không thay ngữ nghĩa `DELETE/UPDATE/RETURNING`. Khi cần mutation hiệu năng cao, vẫn phải xác định quyền, index, giới hạn tập document, CAS/TTL và consistency. Không sử dụng `block()` tùy tiện trong request processing của WebFlux.

## 13. Các lỗi thường gặp khi dùng DML và `RETURNING`

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `INSERT` báo trùng key | Document ID đã tồn tại | Kiểm tra yêu cầu tạo mới; chỉ dùng `UPSERT` nếu nghiệp vụ cho phép thay thế |
| `UPSERT` làm mất `tenantId` hoặc `_class` | Body upsert thay thế document cũ, không chỉ vá vài field | Truyền đủ body hoặc dùng `UPDATE`/KV mutate phù hợp |
| `UPDATE` sửa nhiều document hơn dự kiến | Thiếu `WHERE`, sai `AND/OR` hoặc thiếu tenant/type filter | Dùng `SELECT` xem trước, đặt ngoặc và ràng buộc đủ điều kiện |
| `DELETE` thành công nhưng trả 0 hàng | Không document nào khớp điều kiện hoặc không có `RETURNING` | Phân biệt 0 mutation với kết quả không được chiếu; xem query metrics |
| `RETURNING *` không map được `Product` | Hàng JSON thiếu alias/metadata theo hợp đồng Spring Data | Dùng `#{#n1ql.returning}` cho mẫu Repository delete hoặc DTO/SDK |
| `RETURNING RAW` làm `rowsAsObject()` lỗi | Kết quả là scalar, không phải JsonObject | Dùng cách đọc scalar của SDK tương thích phiên bản |
| `@Query` không nhận `#{#n1ql.delete}` | Sai import annotation hoặc API/version không phù hợp | Kiểm tra Spring Data Couchbase Repository `@Query` và tài liệu phiên bản |
| Lệnh có `RETURNING` bị từ chối quyền | Thiếu Query Select dù có Query Update/Delete | Cấp quyền Query Select tối thiểu trên keyspace được đọc |
| `DELETE` theo `category` xóa cả Promotion | Thiếu bộ lọc type discriminator trong collection dùng chung | Giữ điều kiện loại phù hợp, kiểm tra dữ liệu thật |
| Query ở Workbench sửa khác keyspace của app | Bucket/scope/collection hoặc query context khác nhau | Dùng đường dẫn ba cấp và so sánh SQL++ thực tế |
| DML chạy chậm | Thiếu index, lọc quá rộng, `RETURNING *` quá nặng | Dùng `EXPLAIN`, tối ưu index và thu hẹp phép chiếu |
| Sau UPDATE, TTL biến mất hoặc thay đổi | Không xác định rõ chính sách preserve expiry | Kiểm tra tùy chọn preserve expiry và expiration của document |
| Đọc lại entity cũ gặp CAS conflict | DML thay document mà object Java giữ `@Version` cũ | Nạp lại entity/giải quyết optimistic locking, không bỏ kiểm tra CAS |
| Thử `DELETE` hai lần chỉ thấy một lần có kết quả | Lần đầu đã xóa document; lần sau không còn đối tượng khớp | Thiết kế idempotency và trạng thái trả về cho thao tác xóa |
| `MERGE` không tìm được index trên target | Điều kiện ghép source-target chưa có đường truy cập tốt | Thiết kế index cho phép ghép và kiểm tra `EXPLAIN` |
| Tham số có dấu nháy gây lỗi SQL++ | Đã nối chuỗi đầu vào thay vì binding | Dùng `$1`/`$name` và `@Param` hoặc SDK parameters |
| Muốn “giá cũ và giá mới” nhưng chỉ thấy giá mới | `RETURNING` không mặc nhiên tạo bộ trước/sau | Thiết kế audit riêng hoặc workflow transaction có kiểm soát |

### Checklist trước khi chạy một câu SQL++ ghi dữ liệu

1. **Đúng keyspace chưa?** Xác nhận bucket, scope, collection; tránh query context rút gọn không rõ.
2. **Đúng người có quyền chưa?** Tenant phải lấy từ ngữ cảnh xác thực, không phải một field request tùy ý.
3. **Đúng loại entity chưa?** Kiểm tra discriminator lưu thực tế và các document legacy.
4. **Đúng tập ID chưa?** Chạy `SELECT` tương đương, đối chiếu mẫu và số lượng dự kiến, hiểu rằng tập này vẫn có thể thay đổi trước DML.
5. **Đúng lệnh chưa?** `INSERT` khác `UPSERT`; `SET` khác `UNSET`; `DELETE` cứng khác soft delete.
6. **Đúng kết quả chưa?** Chọn `RETURNING` theo kiểu scalar, DTO hoặc full entity; xác định xử lý zero rows.
7. **Đúng tính nhất quán chưa?** Xem CAS, retry, TTL, transaction và read-after-write index.
8. **Đúng hiệu năng chưa?** Kiểm tra index, `EXPLAIN`, giới hạn khối lượng DML và số field được trả về.
9. **Có kế hoạch audit/rollback chưa?** Với xóa hoặc cập nhật hàng loạt, xác định điểm khôi phục, log kiểm toán và người phê duyệt.

## 14. Bài thực hành có đáp án

Mỗi bài mặc định bắt đầu từ **ba document gốc** ở phần 1, chưa chịu ảnh hưởng của những DML trong các bài khác. Thực thi trên collection test riêng, không dùng dữ liệu production.

### Bài 1 — Xác định phép chiếu `RETURNING` cần cho API

**Yêu cầu:** Tạo sản phẩm mới và trả duy nhất document ID. Viết một câu `INSERT` mẫu.

```sql
INSERT INTO `catalog`.`commerce`.`products` (KEY, VALUE)
VALUES (
  "product::HS-501",
  {
    "_class": "catalog-product",
    "sku": "HS-501",
    "category": "headset",
    "name": "Tai nghe studio",
    "price": 1750000,
    "stock": 7,
    "active": true,
    "tenantId": "shop-a"
  }
)
RETURNING META().id AS documentId;
```

**Đáp án:** Khi key chưa tồn tại, một hàng trả về chứa `documentId = "product::HS-501"`. Nếu gọi lại với cùng ID, `INSERT` báo trùng key, không tự update.

### Bài 2 — Phân biệt `UPSERT` và `UPDATE`

**Tình huống:** KB-101 đang có đủ `sku`, `category`, `price`, `stock`, `active`, `tenantId`. Ứng dụng chỉ muốn sửa `price`.

**Đáp án:** Dùng `UPDATE` với `SET p.price = $newPrice` và điều kiện ID/type/tenant, hoặc dùng đường KV thích hợp khi đã biết ID. Không dùng `UPSERT` với body chỉ chứa `{"price": 1500000}`, vì các field khác của document có thể bị thay thế/mất.

### Bài 3 — Dự đoán kết quả của `UPDATE ... RETURNING`

```sql
UPDATE `catalog`.`commerce`.`products` AS p
USE KEYS "product::KB-101"
SET p.stock = p.stock - 3
WHERE p.tenantId = "shop-a"
  AND p._class = "catalog-product"
  AND p.stock >= 3
RETURNING META(p).id AS documentId,
          p.stock AS stock;
```

**Đáp án:** KB-101 có stock từ 10 xuống 7, hàng kết quả gồm `documentId = "product::KB-101"` và `stock = 7`. Không có lý do cập nhật KB-202 hay MS-301 vì `USE KEYS` chỉ một ID. Đây không phải toàn bộ giao dịch đặt hàng.

### Bài 4 — Sửa điều kiện xóa vượt qua tenant

**Đầu bài nguy hiểm:**

```sql
-- KHÔNG CHẠY:
DELETE FROM `catalog`.`commerce`.`products` AS p
WHERE p.tenantId = "shop-a" AND p.active = false
   OR p.stock = 0;
```

**Đáp án sửa:**

```sql
DELETE FROM `catalog`.`commerce`.`products` AS p
WHERE p._class = "catalog-product"
  AND p.tenantId = "shop-a"
  AND (p.active = false OR p.stock = 0)
RETURNING META(p).id AS documentId;
```

Trong dữ liệu gốc không có product của `shop-a` vừa inactive hoặc hết hàng, nên tập xóa là rỗng. MS-301 có `stock = 0` nhưng thuộc `shop-b`, không được xóa.

### Bài 5 — Xóa và trả entity bằng Spring Data

**Yêu cầu:** Khai báo một phương thức Repository có `#n1ql.delete`, `#n1ql.filter` và `#n1ql.returning` để xóa theo document ID của tenant đã được xác thực.

```java
@Query("#{#n1ql.delete} WHERE #{#n1ql.filter} "
     + "AND META().id = $id AND tenantId = $tenantId "
     + "#{#n1ql.returning}")
Product removeAndReturn(
    @Param("id") String id,
    @Param("tenantId") String trustedTenantId
);
```

**Đáp án:** `#n1ql.delete` tạo `DELETE FROM`, `#n1ql.filter` lọc kiểu entity, `$id` và `$tenantId` là giá trị được binding, `#n1ql.returning` tạo phép chiếu phục vụ mapping entity. Phải đối chiếu với version Spring Data khi chạy và bảo vệ tenant bằng security context.

### Bài 6 — `RETURNING RAW` hay `RETURNING ... AS ...`?

**Yêu cầu:** Service chỉ cần danh sách ID đã bị xóa, một API khác cần ID, SKU, category để hiển thị.

**Đáp án:** Service thứ nhất có thể dùng `RETURNING RAW META().id` và đọc kết quả dạng scalar. API thứ hai nên dùng `RETURNING META().id AS documentId, sku AS sku, category AS category` để nhận object row rõ field. Không dùng `rowsAsObject()` cho scalar rồi mong có key `documentId`.

### Bài 7 — Xác định ảnh hưởng của thiếu `RETURNING`

```sql
UPDATE `catalog`.`commerce`.`products` AS p
USE KEYS "product::KB-202"
SET p.active = false
WHERE p.tenantId = "shop-a";
```

**Đáp án:** Nếu query thành công, KB-202 được cập nhật nhưng tập hàng kết quả không phải một projection `RETURNING`. Không dùng độ dài danh sách row để kết luận đã sửa 0 document; kiểm tra query metadata/metrics phù hợp hoặc đọc lại document ở môi trường test.

### Bài 8 — Tính giá sau giảm

**Yêu cầu:** Trên dữ liệu gốc, giảm 5% sản phẩm keyboard đang active của shop-a bằng `ROUND(price * 0.95)`.

**Đáp án:** KB-101: 1.450.000 → 1.377.500; KB-202: 1.950.000 → 1.852.500. MS-301 không phù hợp tenant/category/active. Nếu chạy lại cùng lệnh trên giá đã giảm, **giảm tiếp 5% trên giá mới**; thao tác này không idempotent. Nên thiết kế điều kiện, chiến dịch hoặc version để chống áp dụng lặp ngoài ý muốn.

### Bài 9 — Cập nhật document có TTL

**Yêu cầu:** Một document sẽ hết hạn sau 24 giờ. Chạy `UPDATE` thay giá, có thể mặc định TTL giữ nguyên không?

**Đáp án:** Không nên giả định. Kiểm tra cơ chế preserve expiry của SQL++ và cấu hình bucket/collection theo phiên bản, rồi thử cả trước/sau mutation trên dữ liệu lab. `RETURNING META().expiration` có thể giúp quan sát expiry nhưng không tự bảo đảm giữ hạn cũ.

### Bài 10 — Chọn API cho từng bài toán

| Tình huống | Lựa chọn gợi ý |
| --- | --- |
| Đọc rồi sửa một Product theo ID, cần optimistic locking | Repository/KV với CAS và `@Version` |
| Tắt hàng loạt sản phẩm theo category/tenant | SQL++ `UPDATE ... WHERE ... RETURNING ...` có kiểm soát |
| Xóa một document và cần trả lại entity trong Repository | `@Query` với `#n1ql.delete` và `#n1ql.returning`, test mapping |
| Đồng bộ snapshot toàn bộ body theo document key | `UPSERT` hoặc KV upsert, chỉ khi ghi đè được phép |
| Đồng bộ dữ liệu theo một nguồn khác với nhiều nhánh hành động | `MERGE` sau khi thiết kế matching/index |
| Xóa hàng triệu document hết hạn | Xem TTL và quy trình lifecycle/batch phù hợp, không mặc định một `DELETE` lớn là tốt nhất |

### Bài 11 — Kịch bản kiểm thử tích hợp

Trên một collection test cách ly, thực hiện chuỗi kiểm chứng:

1. Chèn dữ liệu test bằng Spring Data để có discriminator thực sự.
2. Đọc ID/CAS/expiration và số lượng document trước thao tác.
3. Chạy `INSERT` với key mới, kiểm tra hàng `RETURNING` và xử lý key trùng.
4. Chạy `UPDATE USE KEYS` có `RETURNING` và so sánh field trước/sau.
5. Thử `UNSET` đối chiếu `IS MISSING` với `SET ... = NULL`.
6. Chạy `DELETE` có điều kiện type/tenant, xác nhận hàng `RETURNING` và không còn document theo ID.
7. So sánh câu DML không có `RETURNING` với metrics từ SDK.
8. Kiểm tra `#n1ql.delete`/`#n1ql.returning` qua Repository với phiên bản mapping thực tế.
9. Giả lập cập nhật cạnh tranh để kiểm tra CAS/transaction; thử document có TTL.
10. Chạy `EXPLAIN` trên DML và kiểm tra index đúng collection, cả trước và sau khi thêm điều kiện.

Các bước này là **kế hoạch thực hành**, không phải kết quả kiểm thử đã chạy trong quá trình viết bài.

## 15. Câu hỏi tự kiểm tra

1. **`INSERT` khác `UPSERT` thế nào?** INSERT không ghi đè key tồn tại; UPSERT tạo mới hoặc thay thế theo key.
2. **`UPDATE` có thể xóa một field không?** Có, thông qua `UNSET`; khác `SET field = NULL`.
3. **`DELETE ... RETURNING` có giữ document trong Couchbase không?** Không; nó chỉ trả dữ liệu liên quan tới document bị xóa.
4. **`RETURNING *` có luôn phù hợp để map thành Spring Data entity không?** Không; phải xét shape và metadata.
5. **`RETURNING RAW META().id` có trả JsonObject không?** Không; mỗi hàng là scalar ID.
6. **`#n1ql.delete` có sinh cả lệnh xóa không?** Nó tạo phần `DELETE FROM` của câu query cho entity; điều kiện `WHERE` phải được viết đúng.
7. **`#n1ql.returning` có tự làm lệnh xóa an toàn không?** Không; nó tạo phép chiếu trả về phục vụ entity mapping.
8. **DML không có RETURNING trả 0 hàng có nghĩa không sửa dữ liệu?** Không; cần xem metadata/metrics và hợp đồng câu lệnh.
9. **Vì sao phải kiểm tra tenant?** Vì type discriminator không phải authorization và collection có thể chứa nhiều tenant.
10. **`REQUEST_PLUS` có tự bảo vệ optimistic locking không?** Không; nó điều chỉnh độ mới index, không thay CAS/transaction.
11. **`MERGE` khác `UPSERT` ở đâu?** MERGE ghép source-target theo điều kiện và có thể chọn nhiều action; UPSERT thao tác theo key/value.
12. **Vì sao cập nhật giảm 5% không idempotent?** Chạy lặp sẽ giảm tiếp trên giá đã thay đổi.
13. **Có cần Query Select khi thêm `RETURNING` không?** Có thể cần; phải kiểm tra quyền đọc keyspace theo tài liệu Query Service.
14. **Vì sao `UPDATE` có thể làm thay đổi TTL?** Chính sách preserve expiry và expiration có thể không giữ mặc định; phải xác minh cụ thể.
15. **DML SQL++ trực tiếp có chạy Spring Data entity callbacks không?** Không nên mặc định có; query có thể đi vòng ngoài mapper/Repository lifecycle.

## Tài liệu tham khảo chính thức

- [Couchbase SQL++ — INSERT](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/insert.html): tạo document theo key, `VALUES` và `RETURNING`.
- [Couchbase SQL++ — UPSERT](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/upsert.html): thêm mới hoặc thay thế document.
- [Couchbase SQL++ — UPDATE](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/update.html): `SET`, `UNSET`, `USE KEYS` và `RETURNING`.
- [Couchbase SQL++ — DELETE](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/delete.html): điều kiện xóa, giới hạn và `RETURNING`.
- [Couchbase SQL++ — MERGE](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/merge.html): hợp nhất nguồn/đích với các hành động insert, update và delete.
- [Couchbase Server — Manipulate Data with Queries](https://docs.couchbase.com/server/current/guides/manipulate.html): hướng dẫn DML, quyền và kiểm soát thay đổi.
- [Spring Data Couchbase — Repositories](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): `@Query`, `#n1ql.delete`, `#n1ql.returning` và binding tham số.
- [Spring Data Couchbase — Query Parser API](https://docs.spring.io/spring-data/couchbase/reference/api/java/org/springframework/data/couchbase/repository/query/StringBasedN1qlQueryParser.html): các biểu thức SpEL phục vụ Delete/Returning.
- [Couchbase Java SDK — SQL++ Queries](https://docs.couchbase.com/java-sdk/current/howtos/sqlpp-queries-with-sdk.html): `Cluster.query`, query parameters, `QueryResult` và consistency.

**Ghi nhớ:** Với SQL++ DML, **document key xác định nơi tạo/thay thế khi dùng `INSERT/UPSERT`; `WHERE` hoặc `USE KEYS` giới hạn document bị sửa/xóa với `UPDATE/DELETE`; `RETURNING` quyết định dữ liệu nào được trả về**. `INSERT` không ghi đè, `UPSERT` có thể thay toàn bộ body, `UPDATE` sửa field, `DELETE` xóa document và `MERGE` áp dụng action theo nguồn so khớp. Trong Spring Data Couchbase, `#{#n1ql.delete}` và `#{#n1ql.returning}` có thể hỗ trợ xóa và dựng lại entity, nhưng không tự thay thế kiểm tra tenant, CAS, TTL, transaction, index hoặc audit. Với thao tác có rủi ro, luôn xác định rõ keyspace, xem trước tập ID, giới hạn quyền và kiểm chứng bằng môi trường test.

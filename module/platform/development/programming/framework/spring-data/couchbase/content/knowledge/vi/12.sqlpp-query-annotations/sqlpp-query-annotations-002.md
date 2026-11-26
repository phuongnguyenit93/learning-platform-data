# SELECT, FROM, WHERE và truy cập trường JSON trong Couchbase SQL++

> **Mục tiêu:** Hiểu ba mệnh đề nền tảng của SQL++ (`SELECT`, `FROM`, `WHERE`); truy cập object JSON, mảng và metadata document; áp dụng cú pháp đúng khi viết truy vấn trực tiếp hoặc qua Spring Data Couchbase `@Query`.

Trong module **SPRING_DATA_COUCHBASE**, Spring Data ánh xạ đối tượng Java thành document JSON trong Couchbase. Việc lấy document khi biết ID thường dùng Key/Value API. Khi cần tìm document theo thuộc tính hoặc chỉ lấy một số trường, ta dùng **SQL++** thông qua Query Service. Ngôn ngữ này từng có tên **N1QL**, vì vậy API và biểu thức của Spring Data đôi khi vẫn dùng chữ `n1ql`.

| Mệnh đề | Câu hỏi | Chức năng |
| --- | --- | --- |
| `SELECT` | Cần trả về dữ liệu gì? | Chọn trường, biểu thức và hình dạng mỗi hàng kết quả |
| `FROM` | Lấy document từ đâu? | Chọn bucket, scope, collection và khai báo alias |
| `WHERE` | Document nào đủ điều kiện? | Lọc theo trường JSON và biểu thức logic |

## 1. Dữ liệu mẫu: sản phẩm trong một collection

Giả sử hệ thống có bucket `catalog`, scope `commerce`, collection `products`. Ba document được lưu với những ID riêng:

**Document ID: `product::KB-100`**

```json
{
  "sku": "KB-100",
  "name": "Bàn phím cơ TKL",
  "category": "keyboard",
  "price": 1450000,
  "active": true,
  "specs": {
    "layout": "TKL",
    "connection": "wired"
  },
  "tags": ["mechanical", "office"],
  "variants": [
    { "color": "black", "stock": 12 },
    { "color": "white", "stock": 4 }
  ],
  "discount": null
}
```

**Document ID: `product::KB-200`**

```json
{
  "sku": "KB-200",
  "name": "Bàn phím không dây",
  "category": "keyboard",
  "price": 1890000,
  "active": true,
  "specs": {
    "layout": "75%",
    "connection": "wireless"
  },
  "tags": ["wireless", "office"],
  "variants": [
    { "color": "gray", "stock": 7 }
  ]
}
```

**Document ID: `product::MS-100`**

```json
{
  "sku": "MS-100",
  "name": "Chuột văn phòng",
  "category": "mouse",
  "price": 390000,
  "active": false,
  "specs": { "connection": "wireless" },
  "tags": ["wireless"]
}
```

Document có thể chứa **object** lồng nhau (`specs`), **mảng** (`tags`, `variants`) và trường không đồng nhất. Chẳng hạn, `discount` có giá trị `null` ở KB-100 nhưng hoàn toàn không có mặt ở hai document còn lại. SQL++ phải xử lý được cả những trường hợp này.

## 2. `SELECT`: lựa chọn dữ liệu trả về

`SELECT` quyết định trường hoặc biểu thức xuất hiện trong mỗi dòng kết quả. Ví dụ chỉ lấy mã, tên và giá:

```sql
SELECT p.sku, p.name, p.price
FROM `catalog`.`commerce`.`products` AS p;
```

Đối với KB-100, một dòng kết quả có dạng:

```json
{
  "sku": "KB-100",
  "name": "Bàn phím cơ TKL",
  "price": 1450000
}
```

`p` là alias (bí danh) của document. `p.price` là giá trị thuộc tính `price` trong document đó. Muốn đổi tên trường trong kết quả, sử dụng `AS`:

```sql
SELECT p.sku AS productCode, p.price AS salePrice
FROM `catalog`.`commerce`.`products` AS p;
```

Một hàng được chiếu có cấu trúc `{"productCode":"KB-100","salePrice":1450000}`. Alias sau `AS` không thay đổi tên trường trong document lưu trữ.

### Phân biệt `SELECT *`, `SELECT p.*` và `SELECT RAW`

```sql
-- Trả về các keyspace dưới khóa tương ứng với alias.
SELECT *
FROM `catalog`.`commerce`.`products` AS p
WHERE p.sku = "KB-100";
```

Với một nguồn `p`, kết quả `SELECT *` thường có dạng lồng `{"p": {"sku": "KB-100", ...}}`. Ngược lại:

```sql
SELECT p.*
FROM `catalog`.`commerce`.`products` AS p
WHERE p.sku = "KB-100";
```

`SELECT p.*` trải các trường của document `p` ra object kết quả cấp cao nhất. Nếu chỉ muốn nhận các **giá trị** thay vì một object chứa tên trường, sử dụng `SELECT RAW` (cũng gọi `SELECT VALUE`):

```sql
SELECT RAW p.sku
FROM `catalog`.`commerce`.`products` AS p
WHERE p.category = "keyboard"
ORDER BY p.sku;
```

Với dữ liệu mẫu, tập kết quả gồm hai giá trị chuỗi:

```json
["KB-100", "KB-200"]
```

Khác biệt này quan trọng khi ánh xạ kết quả về Java. `SELECT p.*` hay `SELECT *` không mặc nhiên cung cấp đầy đủ metadata mà Spring Data cần để dựng một entity; trong Repository trả về entity, nên cân nhắc mẫu `#{#n1ql.selectEntity}`.

### Đọc ID document bằng `META`

ID Couchbase không bắt buộc là trường trong JSON body. Để đưa ID vào hàng kết quả SQL++:

```sql
SELECT META(p).id AS documentId,
       p.sku, p.name
FROM `catalog`.`commerce`.`products` AS p
WHERE p.sku = "KB-100";
```

Kết quả tương ứng:

```json
{
  "documentId": "product::KB-100",
  "sku": "KB-100",
  "name": "Bàn phím cơ TKL"
}
```

`META(p).id` truy cập metadata do Couchbase quản lý, khác với `p.id` là trường JSON nếu document thực sự có trường ấy. Với Spring Data, thuộc tính gắn `@Id` thường được ánh xạ từ document ID.

## 3. `FROM`: nguồn dữ liệu, đường dẫn và alias

Trong ví dụ, nguồn đầy đủ có dạng:

```sql
FROM `catalog`.`commerce`.`products` AS p
```

| Thành phần | Giá trị | Vai trò |
| --- | --- | --- |
| Bucket | `catalog` | Đơn vị lưu trữ Couchbase cấp bucket |
| Scope | `commerce` | Không gian nhóm collection |
| Collection | `products` | Tập document để Query Service đọc |
| Alias | `p` | Tên dùng trong các biểu thức `SELECT` và `WHERE` |

Dấu **backtick** bao quanh `catalog`, `commerce` và `products` là dấu trích dẫn **định danh** của SQL++; dấu nháy đôi trong `"keyboard"` biểu thị **chuỗi dữ liệu**. Đường dẫn phải đúng với cấu hình của ứng dụng. Tên rút gọn chỉ được phân giải trong query context phù hợp; dùng đủ ba cấp khi cần tránh mơ hồ.

Alias giúp truy vấn dễ đọc và trở nên cần thiết khi có nhiều nguồn dữ liệu. Nếu đổi `AS p` thành `AS product`, các biểu thức `p.sku`, `p.category` phải đổi thành `product.sku`, `product.category` cho nhất quán.

## 4. `WHERE`: điều kiện lọc document

`WHERE` chỉ giữ các dòng có biểu thức đánh giá thành **TRUE**. Kết quả `FALSE`, `NULL` hoặc `MISSING` không được giữ lại.

```sql
SELECT p.sku, p.price
FROM `catalog`.`commerce`.`products` AS p
WHERE p.category = "keyboard";
```

Kết quả có KB-100 và KB-200. Thêm điều kiện giá:

```sql
SELECT p.sku, p.price
FROM `catalog`.`commerce`.`products` AS p
WHERE p.category = "keyboard"
  AND p.price < 1800000;
```

Chỉ KB-100 thỏa cả hai điều kiện.

| Cú pháp | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `=`, `!=` | `p.category = "keyboard"` | Bằng/khác |
| `<`, `<=`, `>`, `>=` | `p.price >= 1000000` | So sánh theo thứ tự |
| `BETWEEN ... AND ...` | `p.price BETWEEN 1000000 AND 2000000` | Trong đoạn, gồm hai đầu mút |
| `IN` | `p.category IN ["keyboard", "mouse"]` | Nằm trong tập giá trị |
| `LIKE` | `p.name LIKE "Bàn phím%"` | Mẫu chuỗi, `%` đại diện chuỗi ký tự |
| `AND`, `OR`, `NOT` | `p.active = true AND p.price < 2000000` | Ghép và phủ định điều kiện |

### Giữ đúng ưu tiên logic

`AND` có độ ưu tiên cao hơn `OR`. Chẳng hạn `A AND B OR C` được hiểu là `(A AND B) OR C`. Muốn lấy sản phẩm **đang hoạt động** và thuộc một trong hai nhóm, dùng ngoặc:

```sql
WHERE p.active = true
  AND (p.category = "keyboard" OR p.category = "mouse")
```

Đây là mẫu rõ nghĩa hơn khi thêm điều kiện vào truy vấn nghiệp vụ.

### Sắp xếp và giới hạn kết quả

`ORDER BY` và `LIMIT` thường đi sau `WHERE`:

```sql
SELECT p.sku, p.price
FROM `catalog`.`commerce`.`products` AS p
WHERE p.category = "keyboard"
ORDER BY p.price DESC, p.sku ASC
LIMIT 10;
```

Không có `ORDER BY` thì không nên giả định thứ tự trả về ổn định. Với phân trang, nên sắp xếp theo thứ tự xác định và có trường phân biệt khi nhiều bản ghi trùng giá, chẳng hạn `META(p).id`.

## 5. Truy cập object JSON và các trường lồng nhau

SQL++ có thể đi sâu vào object thông qua **dấu chấm**. Ví dụ document có `specs` là object và `layout`, `connection` là các thuộc tính bên trong:

```sql
SELECT p.sku,
       p.specs.layout AS keyboardLayout,
       p.specs.connection AS connection
FROM `catalog`.`commerce`.`products` AS p
WHERE p.specs.layout = "TKL";
```

`p.specs.layout` nghĩa là lấy `specs` từ document `p`, rồi lấy `layout`. Với dữ liệu mẫu, kết quả chỉ chứa KB-100. Nếu `specs` hoặc `layout` **không tồn tại**, đường dẫn trả về `MISSING`; điều kiện bằng `"TKL"` khi đó không TRUE nên document không được chọn.

### Tên trường chứa ký tự đặc biệt

Với document có trường JSON tên `width-mm` hoặc `screen.size`, phải phân biệt **một tên trường** với **đường dẫn nhiều cấp**. Ví dụ:

```json
{
  "dimensions": {
    "width-mm": 360
  },
  "screen.size": 24
}
```

SQL++ dùng backtick bao tên đặc biệt:

```sql
SELECT p.dimensions.`width-mm` AS widthMm,
       p.`screen.size` AS screenSize
FROM `catalog`.`commerce`.`products` AS p;
```

Đường dẫn có tên trường được trích dẫn trong khối SQL++ trên chỉ một trường có tên nguyên văn `screen.size`. Viết `p.screen.size` lại có nghĩa truy cập object `screen` rồi trường `size`. Các document mẫu ở trên chưa chứa những trường này, nên nếu chạy nguyên ví dụ trên chúng sẽ được trả về ở trạng thái `MISSING`.

### Truy cập phần tử mảng theo chỉ số

`variants` là mảng các object; SQL++ dùng chỉ số **bắt đầu từ 0**:

```sql
SELECT p.sku,
       p.variants[0].color AS firstColor,
       p.variants[0].stock AS firstStock
FROM `catalog`.`commerce`.`products` AS p
WHERE p.category = "keyboard";
```

Với KB-100, phần tử `p.variants[0]` có `color = "black"` và `stock = 12`. Phần tử `p.variants[1]` có `color = "white"`. Nếu mảng thiếu phần tử ở vị trí yêu cầu, biểu thức đường dẫn là `MISSING`.

**Đọc theo vị trí** khác với **kiểm tra tất cả phần tử**. Nếu cần tìm bất kỳ biến thể màu trắng nào, không nên chỉ kiểm tra `variants[0]`.

## 6. Lọc mảng JSON bằng `ANY` và mở rộng bằng `UNNEST`

Giả sử tìm mọi sản phẩm có nhãn `wireless` trong mảng `tags`. Không viết `p.tags = "wireless"` vì một bên là **mảng**, bên kia là **chuỗi**.

```sql
SELECT p.sku, p.tags
FROM `catalog`.`commerce`.`products` AS p
WHERE ANY tag IN p.tags
      SATISFIES tag = "wireless"
      END;
```

SQL++ duyệt các giá trị của `p.tags`, gán lần lượt cho biến `tag`. `ANY ... SATISFIES ... END` đúng nếu **ít nhất một phần tử** thỏa điều kiện. Trong dữ liệu mẫu, KB-200 và MS-100 được chọn.

Mảng cũng có thể chứa **object**. Ví dụ tìm sản phẩm có ít nhất một biến thể màu trắng và còn hàng:

```sql
SELECT p.sku
FROM `catalog`.`commerce`.`products` AS p
WHERE ANY v IN p.variants
      SATISFIES v.color = "white" AND v.stock > 0
      END;
```

KB-100 thỏa điều kiện. Hai phép kiểm tra `v.color` và `v.stock` ở đây áp dụng cho **cùng một object** trong mảng. Nếu muốn trả về từng biến thể thành một hàng, dùng `UNNEST`:

```sql
SELECT p.sku, v.color, v.stock
FROM `catalog`.`commerce`.`products` AS p
UNNEST p.variants AS v
WHERE v.stock > 0;
```

`UNNEST` có thể tạo **nhiều hàng cho cùng một document**. Chọn `ANY` cho yêu cầu lọc document theo điều kiện tồn tại; chọn `UNNEST` khi cần xử lý hoặc liệt kê từng phần tử của mảng.

## 7. `NULL` và `MISSING`: hai trạng thái không giống nhau

Document có trường `discount: null` khác với document không có trường `discount`. SQL++ phân biệt:

- **`NULL`:** trường có tồn tại và chứa giá trị JSON `null`, như KB-100.
- **`MISSING`:** trường không có mặt, như KB-200 và MS-100.

| Biểu thức | KB-100 có `discount: null` | KB-200 thiếu `discount` |
| --- | --- | --- |
| `p.discount IS NULL` | TRUE | FALSE |
| `p.discount IS MISSING` | FALSE | TRUE |
| `p.discount IS NOT MISSING` | TRUE | FALSE |
| `p.discount IS VALUED` | FALSE | FALSE |

Nếu yêu cầu “document **có trường discount**, kể cả giá trị `null`”:

```sql
SELECT p.sku
FROM `catalog`.`commerce`.`products` AS p
WHERE p.discount IS NOT MISSING;
```

Nếu yêu cầu “document có **giá trị discount thực sự** khác `NULL` và `MISSING`”:

```sql
SELECT p.sku, p.discount
FROM `catalog`.`commerce`.`products` AS p
WHERE p.discount IS VALUED;
```

Không nên dùng `p.discount = null` hoặc `p.discount != null` để kiểm tra tình trạng thiếu trường. Thay vào đó, hãy chọn các vị từ `IS NULL`, `IS NOT NULL`, `IS MISSING`, `IS NOT MISSING` hoặc `IS VALUED` theo đúng nghiệp vụ. Do `WHERE` chỉ giữ kết quả TRUE, những biểu thức trả về NULL/MISSING có thể khiến bản ghi bị bỏ qua một cách khó nhận thấy.

## 8. Từ SQL++ thuần đến `@Query` trong Spring Data Couchbase

Spring Data Couchbase hỗ trợ **derived query** (sinh truy vấn từ tên phương thức) và truy vấn tự khai báo bằng `@Query`. Điều kiện SQL++ trong `WHERE` vẫn sử dụng đường dẫn JSON như `category`, `price`, `specs.connection`.

Giả sử ứng dụng cấu hình kết nối bucket `catalog` và entity ánh xạ tới scope `commerce`, collection `products`:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.repository.Collection;
import org.springframework.data.couchbase.repository.Scope;

@Document
@Scope("commerce")
@Collection("products")
public class Product {
    @Id
    private String id;
    private String sku;
    private String category;
    private Long price;
    private Specs specs;

    public Product() {}

    // Trong ứng dụng thật, thêm constructor và getter/setter cần thiết.
    public static class Specs {
        private String layout;
        private String connection;
        public Specs() {}
    }
}
```

Một Repository có thể khai báo:

```java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;
import org.springframework.data.couchbase.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ProductRepository extends CouchbaseRepository<Product, String> {

    // Derived query: điều kiện được sinh từ tên phương thức.
    List<Product> findByCategory(String category);

    // String-based query: chủ động viết điều kiện SQL++.
    @Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} "
         + "AND category = $category "
         + "AND price <= $maxPrice "
         + "AND specs.connection = $connection")
    List<Product> findByCriteria(
        @Param("category") String category,
        @Param("maxPrice") long maxPrice,
        @Param("connection") String connection
    );
}
```

Khi gọi `findByCriteria("keyboard", 2000000, "wireless")`, các tham số được ràng buộc vào giá trị `$category`, `$maxPrice` và `$connection`. Không ghép trực tiếp dữ liệu người dùng vào chuỗi SQL++; tham số hóa giúp xử lý đúng ký tự đặc biệt và giảm rủi ro injection.

### Ba lớp cú pháp cần phân biệt

| Cú pháp | Được xử lý bởi | Tác dụng |
| --- | --- | --- |
| `@Query("...")` | Spring Data Couchbase | Gắn truy vấn SQL++ với phương thức Repository |
| `#{#n1ql.selectEntity}` | Biểu thức SpEL của Spring Data | Sinh `SELECT/FROM` cùng phép chiếu cần cho entity mapping |
| `#{#n1ql.filter}` | Biểu thức SpEL của Spring Data | Thêm điều kiện phân biệt kiểu document mà Spring Data quản lý |
| `$category` hoặc `$1` | Cơ chế tham số SQL++ do Spring Data truyền | Thay giá trị đầu vào, không thay tên trường hay cú pháp |
| `specs.connection` | Couchbase SQL++ | Truy cập trường JSON lồng nhau |

Tên `n1ql` trong `#{#n1ql...}` là **tên API lịch sử**, không phải một ngôn ngữ khác với SQL++ hiện tại. Các biểu thức `#{...}` chỉ được Spring Data xử lý; không dán trực tiếp chúng vào Couchbase Query Workbench.

### Vì sao phép chiếu phải phù hợp kiểu trả về?

Nếu chạy câu sau trong Query Workbench, ta có thể nhận được đầy đủ ba trường cần hiển thị:

```sql
SELECT p.sku, p.name, p.price
FROM `catalog`.`commerce`.`products` AS p
WHERE p.category = "keyboard";
```

Nhưng phép chiếu đó **không chứa đầy đủ trường và metadata** cần để Spring Data dựng entity `Product` với ID/CAS. Với `List<Product>`, nên dùng `#{#n1ql.selectEntity}`; nếu chỉ cần ba trường, thiết kế DTO/projection và kiểu trả về tương ứng. Việc SQL++ chạy thành công chưa đảm bảo Java mapping đúng.

**Lưu ý về dữ liệu mẫu:** ba document minh họa ở đầu bài chưa có trường phân biệt kiểu của Spring Data. Nếu tự chèn chúng bằng Query Workbench, `#{#n1ql.filter}` có thể loại bỏ chúng vì thiếu discriminator (thường được lưu ở `_class`). Trong ví dụ Repository thực tế, hãy sử dụng document được ghi bằng cùng cơ chế mapping Spring Data, hoặc bảo đảm cấu trúc discriminator phù hợp.

### Tham số theo vị trí

Ngoài tham số có tên, Spring Data có thể dùng vị trí:

```java
@Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} "
     + "AND category = $1 AND price <= $2")
List<Product> findByCategoryAndMaxPrice(String category, long maxPrice);
```

`$1` là giá trị tham số thứ nhất, `$2` là giá trị thứ hai. Nên nhất quán giữa tham số vị trí và tham số có tên trong một câu truy vấn. **Tên bucket, collection hoặc trường không phải là các giá trị để thay thế bằng `$1`**; khi xây dựng các phần cú pháp động, cần cơ chế kiểm soát định danh cho phép.

## 9. Chỉ mục, hiệu năng và độ mới của kết quả

SQL++ chạy qua **Query Service**, nên `WHERE` thường cần **secondary index** để lọc hiệu quả. Ví dụ với điều kiện danh mục và giá:

```sql
CREATE INDEX idx_products_category_price
ON `catalog`.`commerce`.`products`(category, price);
```

Sau khi tạo chỉ mục phù hợp, có thể xem kế hoạch thực thi:

```sql
EXPLAIN
SELECT p.sku, p.price
FROM `catalog`.`commerce`.`products` AS p
WHERE p.category = "keyboard"
  AND p.price < 1800000;
```

Đây chỉ là thiết kế chỉ mục minh họa. Khi triển khai, cần cân nhắc đường dẫn JSON đang lọc, thứ tự trường, phân bố giá trị, `ORDER BY` và lưu lượng dữ liệu. Truy vấn mảng với `ANY` có thể hưởng lợi từ **array index** chuyên biệt. Với `@Query` có `#{#n1ql.filter}`, cân nhắc cả trường type discriminator khi tối ưu.

Sau một lần ghi bằng Key/Value API, chỉ mục Query Service có thể chưa cập nhật ngay. Ở chế độ scan consistency `NOT_BOUNDED`, một truy vấn `WHERE` có thể tạm thời chưa thấy document mới; `REQUEST_PLUS` có thể đợi chỉ mục cập nhật, đổi lại tăng độ trễ. Nếu đã biết ID và chỉ cần một document, đường đọc Key/Value thường thích hợp hơn.

Trong kiến trúc Spring Data Couchbase rộng hơn, **TTL** quy định thời hạn sống document, **CAS** giúp kiểm soát cập nhật đồng thời, **transaction** quy định ranh giới thao tác nguyên tử, còn **CouchbaseTemplate** và Repository **reactive** là những lựa chọn API. Chúng không thay đổi nghĩa của `SELECT/FROM/WHERE`, nhưng ảnh hưởng cách triển khai tầng truy cập dữ liệu cho hiệu năng và nhất quán.

## 10. Các lỗi phổ biến và cách tự kiểm tra

| Hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| Truy vấn không tìm thấy collection | Sai bucket/scope/collection hoặc query context | Đối chiếu đường `FROM` và quyền truy cập |
| `SELECT *` trả về object có khóa `p` | Dấu `*` chọn keyspace theo alias | Chọn `p.*`, phép chiếu trường hoặc `RAW` tùy kiểu kết quả |
| Không lọc được trường lồng nhau | Trường không có trong document hoặc sai tên/kiểu | Xem cấu trúc JSON; kiểm tra `MISSING` |
| `WHERE discount = null` không đúng ý | `NULL` khác `MISSING` | Dùng vị từ `IS NULL`, `IS MISSING`, `IS VALUED` |
| `p.tags = "wireless"` không trả về kết quả | So sánh mảng với chuỗi | Sử dụng `ANY ... IN ... SATISFIES ... END` |
| `@Query` có kết quả thiếu ID/CAS hoặc mapping lỗi | Phép chiếu không phù hợp full entity | Dùng `#n1ql.selectEntity` hoặc định nghĩa projection |
| Workbench tìm thấy dữ liệu nhưng Repository không thấy | Khác collection hoặc discriminator được `#n1ql.filter` dùng | Kiểm tra entity mapping và kiểu document |
| Truy vấn chậm, thiếu index | Chưa có chỉ mục đúng điều kiện | Tạo secondary index, kiểm tra `EXPLAIN` |
| Vừa ghi nhưng query chưa thấy | Chỉ mục cập nhật bất đồng bộ | Cân nhắc `REQUEST_PLUS` hoặc đọc Key/Value |

## 11. Bài thực hành

**Yêu cầu:** Liệt kê mã, tên và giá của sản phẩm `keyboard` kết nối `wireless`, giá không quá 2 triệu, sắp xếp tăng dần theo giá.

Tự xác định:

1. `FROM` phải đến đúng collection `catalog.commerce.products` và cần alias `p`.
2. `SELECT` chỉ chiếu `sku`, `name` và `price`.
3. `WHERE` kết hợp ba điều kiện với `AND`; truy cập `specs.connection` bằng dấu chấm.
4. `ORDER BY` nên chỉ rõ thứ tự; khi phân trang nên bổ sung khóa phân biệt.

Câu SQL++ tham khảo:

```sql
SELECT p.sku, p.name, p.price
FROM `catalog`.`commerce`.`products` AS p
WHERE p.category = "keyboard"
  AND p.price <= 2000000
  AND p.specs.connection = "wireless"
ORDER BY p.price ASC;
```

Với dữ liệu mẫu, chỉ KB-200 thỏa điều kiện.

**Câu hỏi tự kiểm tra:**

1. `SELECT RAW p.sku` khác `SELECT *` thế nào? → `RAW` trả giá trị chuỗi; `*` trả object chứa nguồn document.
2. `p.variants[0].color` khác `ANY v IN p.variants ... END` ở đâu? → Dạng đầu lấy đúng vị trí 0; dạng sau xét các phần tử để tìm giá trị thỏa.
3. Vì sao `discount: null` khác document không có `discount`? → Trường đầu là `NULL`, trường sau là `MISSING`.
4. Vì sao `@Query` trả về `Product` nên dùng `#n1ql.selectEntity`? → Để Spring Data chọn được dữ liệu và metadata cần thiết cho full entity mapping.
5. Vì sao chỉ viết `WHERE` đúng chưa chắc đủ để có truy vấn tốt? → Còn phải chọn collection, phép chiếu, chỉ mục và mức nhất quán phù hợp.

## Tài liệu tham khảo chính thức

- [Couchbase SQL++ — SELECT](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/selectintro.html): cú pháp `SELECT` và dạng phép chiếu.
- [Couchbase SQL++ — FROM](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/from.html): chọn nguồn document và alias.
- [Couchbase SQL++ — WHERE](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/where.html): điều kiện lọc.
- [Couchbase SQL++ — Collection Operators](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/collectionops.html): `ANY` và biểu thức mảng.
- [Spring Data Couchbase — Repositories](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): `@Query`, tham số, entity mapping và các lựa chọn consistency.

**Ghi nhớ:** `FROM` chọn nguồn JSON document, `WHERE` lọc document theo điều kiện và `SELECT` quyết định hình dạng kết quả. Khi đưa truy vấn vào Spring Data Couchbase, cần gắn thêm cơ chế ánh xạ entity, tham số hóa, chỉ mục và yêu cầu nhất quán để tầng truy cập dữ liệu hoạt động đúng.

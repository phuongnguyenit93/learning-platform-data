# Khai báo truy vấn bằng @Query trong Spring Data Couchbase

> **Mục tiêu:** Biết khi nào cần khai báo `@Query` thay vì để Spring Data suy ra truy vấn từ tên phương thức; viết được SQL++ với `#{#n1ql.selectEntity}`, `#{#n1ql.filter}` và tham số `$1`/`$name`; hiểu cách ánh xạ entity, giới hạn kết quả, sử dụng chỉ mục và kiểm soát độ mới của dữ liệu.

Trong module **SPRING_DATA_COUCHBASE**, tầng truy cập dữ liệu kết nối các đối tượng Java với JSON document của Couchbase thông qua **document mapping**, **Repository** và **CouchbaseTemplate**. Bên cạnh thao tác theo ID bằng Key/Value API, ứng dụng thường tìm document theo giá, loại hàng, trạng thái hoặc thuộc tính JSON lồng nhau. Những điều kiện này được Couchbase Query Service xử lý bằng **SQL++** (tên trước đây là **N1QL**).

Spring Data Couchbase có thể tự tạo truy vấn từ phương thức như `findByCategory(String category)`. Khi điều kiện tìm kiếm phức tạp, cần kết hợp `ANY` trên mảng, biểu thức SQL++ đặc thù hoặc cần điều khiển chính xác câu lệnh, ta khai báo truy vấn trên phương thức Repository bằng annotation **`@Query`**.

Điểm mấu chốt: **`@Query` là annotation của Spring Data**, **SQL++ là ngôn ngữ Couchbase thực thi**, còn **`#{#n1ql...}` là biểu thức SpEL mà Spring Data thay thế trước khi gửi câu lệnh đi**.

## 1. Khi nào cần `@Query`?

| Nhu cầu | Cách tiếp cận phù hợp | Lý do |
| --- | --- | --- |
| Đọc một document đã biết ID | `findById(id)` của Repository hoặc Key/Value API | Không cần quét qua truy vấn tìm kiếm |
| Lọc đơn giản theo một vài thuộc tính | Derived query như `findByCategoryAndActive(...)` | Tên phương thức ngắn và dễ đọc |
| Lọc JSON lồng nhau, kiểm tra mảng hoặc biểu thức phức tạp | `@Query` | Chủ động viết điều kiện SQL++ |
| Nhiều điều kiện động theo biểu mẫu tìm kiếm | `CouchbaseTemplate` hoặc công cụ xây dựng truy vấn phù hợp | Dễ ghép các điều kiện đã được kiểm soát |
| Báo cáo tổng hợp `COUNT/SUM/GROUP BY` | SQL++ với DTO/projection hoặc SDK | Kết quả là hàng thống kê, không phải entity document đầy đủ |
| Luồng bất đồng bộ, không chặn | Repository/Template reactive | Thay cách nhận và xử lý dữ liệu, không đổi cú pháp SQL++ |

`@Query` đặc biệt phù hợp khi một phương thức có **ý nghĩa nghiệp vụ rõ ràng** nhưng việc diễn đạt hoàn toàn qua tên `findBy...` quá dài hoặc không hỗ trợ tính năng SQL++ cần thiết.

Trường hợp truy vấn tĩnh thường tốt hơn truy vấn động tự nối chuỗi: cùng một phương thức thể hiện rõ trường được lọc, các tham số truyền vào và kiểu kết quả, giúp kiểm tra chỉ mục cũng như truy vết lỗi dễ dàng hơn.

## 2. Chuẩn bị dữ liệu mẫu và entity Java

Giả sử ứng dụng bán hàng cấu hình Couchbase với:

| Thành phần | Tên minh họa |
| --- | --- |
| Bucket | `catalog` |
| Scope | `commerce` |
| Collection | `products` |
| Entity | `Product` |
| Repository | `ProductRepository` |

Một vài document mẫu được lưu với ID độc lập khỏi body JSON:

**Document ID: `product::KB-100`**

```json
{
  "sku": "KB-100",
  "category": "keyboard",
  "name": "Bàn phím cơ TKL",
  "price": 1500000,
  "active": true,
  "specs": { "connection": "wired", "layout": "TKL" },
  "tags": ["gaming", "mechanical"]
}
```

**Document ID: `product::KB-200`**

```json
{
  "sku": "KB-200",
  "category": "keyboard",
  "name": "Bàn phím không dây",
  "price": 1900000,
  "active": true,
  "specs": { "connection": "wireless", "layout": "75%" },
  "tags": ["office", "wireless"]
}
```

**Document ID: `product::MS-100`**

```json
{
  "sku": "MS-100",
  "category": "mouse",
  "name": "Chuột văn phòng",
  "price": 450000,
  "active": false,
  "specs": { "connection": "wireless" },
  "tags": ["office", "wireless"]
}
```

**Document ID: `product::HS-100`**

```json
{
  "sku": "HS-100",
  "category": "headset",
  "name": "Tai nghe cơ bản",
  "price": 800000,
  "active": true,
  "specs": {},
  "tags": []
}
```

Các JSON trên thể hiện **dữ liệu nghiệp vụ**. Khi lưu bằng Spring Data Couchbase, document có thể được ghi thêm một trường phân biệt kiểu entity (thường là `_class`). Điều này sẽ quan trọng khi sử dụng `#{#n1ql.filter}`.

Ví dụ entity dùng Spring Data Couchbase:

```java
import java.util.List;
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
    private String name;
    private Long price;
    private Boolean active;
    private Specs specs;
    private List<String> tags;

    public Product() {}

    public static class Specs {
        private String connection;
        private String layout;
        public Specs() {}
    }

    // Bổ sung getter/setter hoặc constructor theo quy ước của dự án.
}
```

Ở đây `@Document` đánh dấu kiểu tài liệu, `@Id` ánh xạ **document ID** do Couchbase quản lý, còn `@Scope` và `@Collection` xác định nơi lưu document theo mapping. Bucket `catalog` được chọn trong cấu hình kết nối của ứng dụng. Các trường Java ánh xạ tới các trường JSON cùng tên theo quy ước mặc định.

Trong ví dụ này, giá được lưu bằng số nguyên đồng Việt Nam. Ứng dụng cần số tiền có phần thập phân có thể dùng cách biểu diễn phù hợp với miền nghiệp vụ, chẳng hạn `BigDecimal`, đồng thời kiểm tra chính sách chuyển đổi của SDK/mapping.

## 3. Cú pháp tối thiểu của `@Query`

Một Repository có thể khai báo hai phương thức cùng thực hiện việc lọc theo danh mục:

```java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;
import org.springframework.data.couchbase.repository.Query;

public interface ProductRepository
        extends CouchbaseRepository<Product, String> {

    // Derived query: Spring Data tự tạo điều kiện từ tên phương thức.
    List<Product> findByCategory(String category);

    // SQL++ khai báo tường minh trong annotation.
    @Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} "
         + "AND category = $1")
    List<Product> findCategoryUsingSqlpp(String category);
}
```

Khi gọi:

```java
List<Product> keyboards =
    repository.findCategoryUsingSqlpp("keyboard");
```

Spring Data xử lý các biểu thức SpEL, ràng buộc giá trị `"keyboard"` vào tham số vị trí `$1`, gửi SQL++ qua Couchbase Java SDK tới Query Service và ánh xạ hàng JSON trả về thành `Product`.

### Ba lớp cú pháp trong một phương thức

| Thành phần | Do ai xử lý? | Công dụng |
| --- | --- | --- |
| `@Query("...")` | Spring Data Couchbase | Khai báo truy vấn chuỗi của phương thức Repository |
| `#{#n1ql.selectEntity}` | Spring Expression Language do Spring Data cung cấp | Tạo phần `SELECT/FROM` phù hợp với entity, gồm metadata cần cho mapping |
| `#{#n1ql.filter}` | Spring Data Couchbase | Tạo điều kiện phân biệt loại document theo type discriminator |
| `category = $1` | SQL++ và cơ chế binding tham số | So sánh trường JSON `category` với tham số đầu tiên |
| `List<Product>` | Repository result mapping | Ánh xạ các hàng kết quả thành entity Java |

**Đừng đổi `#n1ql` thành `#sqlpp`.** SQL++ là tên hiện dùng của ngôn ngữ truy vấn Couchbase nhưng `n1ql` vẫn là tên của đối tượng hỗ trợ SpEL trong các API Spring Data Couchbase tương ứng.

### `@Query` chứa câu truy vấn, không chỉ một mảnh `WHERE`

`@Query` ở ví dụ trên được Spring Data mở rộng thành một câu `SELECT ... FROM ... WHERE ...` hoàn chỉnh. Nếu muốn tự viết toàn bộ, cần cung cấp đủ các mệnh đề hợp lệ:

```sql
SELECT p.sku, p.name
FROM `catalog`.`commerce`.`products` AS p
WHERE p.category = "keyboard";
```

Đây là SQL++ **thuần** có thể dán vào Query Workbench. Trái lại, chuỗi `#{#n1ql.selectEntity}` là cú pháp SpEL, **không** được Couchbase Query Service hiểu nếu gửi trực tiếp.

### Lưu ý về `#{#n1ql.filter}`

Khi các entity Java khác nhau chia sẻ cùng một collection, Spring Data có thể dùng discriminator để phân biệt tài liệu của từng kiểu. Biểu thức `#{#n1ql.filter}` bổ sung điều kiện này, giúp query trả về đúng loại document mà Repository đang quản lý.

Do đó, khi chèn JSON bằng Workbench/SDK mà không có discriminator tương thích với mapping của Spring Data, **truy vấn SQL++ thuần có thể tìm thấy document trong khi Repository dùng `#{#n1ql.filter}` không tìm thấy**. Khi thử `@Query`, nên lưu dữ liệu qua cùng mapping hoặc chuẩn bị metadata kiểu phù hợp; đồng thời kiểm tra đúng bucket, scope và collection.

## 4. Ràng buộc tham số đúng cách

Nguyên tắc khi khai báo `@Query`: **giá trị do người dùng truyền phải được ràng buộc thành tham số của SQL++**, không được chèn trực tiếp vào chuỗi truy vấn. Có hai cách thường dùng: tham số **vị trí** và tham số **có tên**.

### Tham số vị trí `$1`, `$2`

```java
@Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} "
     + "AND category = $1 AND price <= $2")
List<Product> findByCategoryAndMaxPrice(
    String category, long maxPrice
);
```

Trong ví dụ:

- `$1` nhận giá trị tham số Java đầu tiên, `category`.
- `$2` nhận giá trị tham số Java thứ hai, `maxPrice`.
- `$1` và `$2` **không có dấu nháy** vì SDK/Query Service xử lý giá trị ràng buộc theo kiểu dữ liệu phù hợp.

Khi gọi `findByCategoryAndMaxPrice("keyboard", 1600000)`, kết quả nghiệp vụ trên dữ liệu mẫu là KB-100; KB-200 có `price = 1900000` nên không được chọn.

### Tham số có tên `$category`

Với nhiều điều kiện, tên tham số mô tả ý nghĩa rõ hơn:

```java
import java.util.List;
import org.springframework.data.couchbase.repository.Query;
import org.springframework.data.repository.query.Param;

@Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} "
     + "AND category = $category "
     + "AND active = $enabled "
     + "AND price BETWEEN $minPrice AND $maxPrice")
List<Product> findWithinPriceRange(
    @Param("category") String category,
    @Param("enabled") boolean enabled,
    @Param("minPrice") long minPrice,
    @Param("maxPrice") long maxPrice
);
```

Đây là **phần khai báo phương thức** đặt bên trong `ProductRepository`. Khi gọi:

```java
List<Product> products =
    repository.findWithinPriceRange("keyboard", true, 1000000, 2000000);
```

KB-100 và KB-200 đều thỏa: cùng danh mục keyboard, `active = true`, giá trong đoạn đã cho. `BETWEEN` bao gồm cả hai đầu mút.

**Khuyến nghị:** dùng nhất quán một kiểu tham số trong cùng một `@Query`. Nếu dùng tên, bảo đảm mọi placeholder `$name` có tham số `@Param("name")` tương ứng. Đừng nhầm biến Java `category` với trường JSON `category` hay biến cục bộ của SQL++.

### Tham số SQL++ không thay thế định danh

Tham số phù hợp với:

```sql
WHERE category = $category AND price <= $maxPrice
```

Nhưng không dùng `$fieldName` để thay tùy ý tên cột, `$collection` thay tên collection hay `$sortDirection` thay từ khóa `ASC/DESC`. Những thành phần đó là **cú pháp/định danh**, không phải **giá trị**.

Khi nghiệp vụ cần chọn một trường sắp xếp động, hãy kiểm tra lựa chọn theo danh sách cho phép (ví dụ chỉ `price`, `sku` hoặc `name`) rồi dùng cơ chế API được thư viện hỗ trợ. Không nối bất kỳ mảnh SQL++ nào từ chuỗi không tin cậy.

### Ví dụ tìm theo tiền tố

`LIKE` nhận một mẫu chuỗi, nên có thể truyền cả ký tự đại diện vào tham số:

```java
@Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} "
     + "AND sku LIKE $skuPattern")
List<Product> findBySkuPattern(
    @Param("skuPattern") String skuPattern
);
```

```java
List<Product> keyboardSkus =
    repository.findBySkuPattern("KB-%");
```

Kết quả là KB-100 và KB-200. Tuy nhiên, `%` và `_` có ý nghĩa đặc biệt trong mẫu `LIKE`; nếu cần tìm chính xác tiền tố **do người dùng nhập**, hãy xử lý việc escape ký tự đại diện theo quy tắc SQL++ của phiên bản đang dùng, hoặc dùng điều kiện/kiểu tìm kiếm phù hợp hơn. Tham số hóa giúp tránh lỗi injection nhưng **không tự chuyển `%` thành ký tự thường**.

### Vì sao ghép chuỗi trực tiếp nguy hiểm?

Ví dụ sau là một cách xây dựng truy vấn cần tránh:

```java
// Ví dụ phản diện: không làm như thế này với giá trị người dùng.
String unsafeSql = "SELECT p.* FROM `catalog`.`commerce`.`products` AS p "
                 + "WHERE p.category = '" + categoryFromRequest + "'";
```

Giá trị có dấu nháy, toán tử hoặc cú pháp SQL++ có thể làm thay đổi câu truy vấn. Bên trong `@Query`, hãy để Spring Data/SDK ràng buộc `$1` hoặc `$name`. Đối với nhu cầu thực sự động, chỉ tạo những đoạn cú pháp được kiểm soát từ mã ứng dụng.

## 5. Truy vấn trường JSON lồng nhau và mảng

`@Query` chấp nhận **điều kiện SQL++** chứ không chỉ so sánh một trường cấp gốc. Mẫu entity ở phần 2 có `specs.connection` và mảng `tags`.

### Object lồng nhau

```java
@Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} "
     + "AND category = $category "
     + "AND specs.connection = $connection")
List<Product> findByConnection(
    @Param("category") String category,
    @Param("connection") String connection
);
```

Gọi `findByConnection("keyboard", "wireless")` tìm KB-200. Đường dẫn `specs.connection` trong SQL++ đi qua thuộc tính JSON `specs` rồi lấy `connection`.

Nếu document thiếu trường `specs` hoặc `connection`, biểu thức trả về `MISSING`; so sánh bằng một giá trị chuỗi không đạt TRUE nên `WHERE` không chọn document đó. Khi cần tìm trường thiếu, dùng `IS MISSING`; khi cần trường có giá trị, dùng `IS VALUED`.

### Mảng chuỗi với `ANY`

Để tìm sản phẩm có một tag cụ thể:

```java
@Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} "
     + "AND active = true "
     + "AND ANY tag IN tags SATISFIES tag = $tag END")
List<Product> findActiveWithTag(@Param("tag") String tag);
```

Gọi `findActiveWithTag("wireless")` chỉ tìm KB-200 trong dữ liệu mẫu. MS-100 cũng có tag `wireless` nhưng `active = false`.

Biến `tag` trong SQL++ là biến cục bộ của `ANY`; `$tag` là **tham số do Java truyền**, hai tên trông giống nhau nhưng có vai trò khác nhau. Nếu muốn dễ đọc hơn, đổi biến cục bộ thành `item`:

```sql
ANY item IN tags SATISFIES item = $tag END
```

### Mảng object với nhiều điều kiện

Giả sử mỗi sản phẩm còn có trường JSON:

```json
{
  "variants": [
    { "color": "black", "stock": 5 },
    { "color": "white", "stock": 0 }
  ]
}
```

Để tìm một document có **ít nhất một biến thể vừa đúng màu, vừa còn hàng**, phải đặt hai điều kiện trong **cùng một** `SATISFIES`:

```java
@Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} "
     + "AND ANY v IN variants "
     + "    SATISFIES v.color = $color AND v.stock > 0 "
     + "    END")
List<Product> findInStockVariant(
    @Param("color") String color
);
```

Không tách thành hai `ANY` độc lập nếu yêu cầu cùng một biến thể: một `ANY` có thể tìm màu trắng ở biến thể hết hàng, trong khi `ANY` kia tìm tồn kho dương ở biến thể màu đen.

Khi mảng có thể không tồn tại hoặc sai kiểu, cần xác định trước chính sách dữ liệu và điều kiện cần thiết. Để xử lý phức tạp hơn, `EVERY` và `ANY AND EVERY` cũng có thể viết trong chuỗi `@Query` theo cú pháp SQL++ thông thường.

## 6. `NULL`, `MISSING` và điều kiện trên trường tùy chọn

Không phải document nào trong Couchbase cũng chứa tất cả thuộc tính. Nếu JSON có `discount: null`, biểu thức `discount` cho giá trị **NULL**; nếu không có khóa `discount`, kết quả là **MISSING**.

Trong `@Query`, dùng đúng toán tử:

```java
// Trường discount không tồn tại.
@Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} "
     + "AND discount IS MISSING")
List<Product> findWithoutDiscountField();

// Trường discount tồn tại nhưng mang giá trị JSON null.
@Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} "
     + "AND discount IS NULL")
List<Product> findExplicitNullDiscount();

// Trường discount hiện diện và không null.
@Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} "
     + "AND discount IS VALUED")
List<Product> findWithValuedDiscount();
```

Các ví dụ trên giả định entity và dữ liệu có thể chứa trường `discount`. Trường `discount` cần được ánh xạ vào entity khi muốn đọc/ghi qua Spring Data. Không viết `discount = null` rồi kỳ vọng nó hoạt động như `IS NULL`.

Nếu yêu cầu nghiệp vụ quy định NULL và MISSING đều tương đương 0, có thể dùng `COALESCE(discount, 0)` trong điều kiện. Tuy nhiên, đó là **quyết định nghiệp vụ**; hai trạng thái này có thể mang ý nghĩa khác nhau và việc thay mặc định cũng có thể ảnh hưởng khả năng dùng chỉ mục thông thường.

## 7. Kết hợp `ORDER BY`, `LIMIT` và phân trang

Một tính năng thường đi kèm `@Query` là giới hạn số bản ghi trả về. SQL++ hỗ trợ `ORDER BY`, `LIMIT` và `OFFSET`, nên có thể truyền số hàng và vị trí bắt đầu thành tham số:

```java
@Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} "
     + "AND category = $category "
     + "ORDER BY sku ASC "
     + "LIMIT $pageSize OFFSET $startAt")
List<Product> findCategoryPage(
    @Param("category") String category,
    @Param("pageSize") long pageSize,
    @Param("startAt") long startAt
);
```

Ví dụ:

```java
List<Product> firstPage =
    repository.findCategoryPage("keyboard", 10, 0);
List<Product> secondPage =
    repository.findCategoryPage("keyboard", 10, 10);
```

Mẫu này minh họa **phân trang tự quản lý** qua `LIMIT/OFFSET`, không ngầm cung cấp `Page<T>`, tổng số bản ghi hay truy vấn đếm. Với `Pageable` của Spring Data, đặc biệt khi kết hợp `@Query` tùy chỉnh, cần xem cách phiên bản thư viện hiện dùng bổ sung `LIMIT/OFFSET`, sắp xếp và câu `count`; tránh ghép hai cơ chế phân trang khi chưa kiểm tra.

Những điểm cần quyết định:

- **Sắp xếp ổn định:** `ORDER BY sku ASC` chỉ đủ ổn định nếu `sku` là duy nhất trong tập được tìm. Nếu không, thêm một khóa phân biệt phù hợp trước khi phân trang.
- **Giới hạn hợp lý:** giới hạn `pageSize` ở tầng dịch vụ/API để tránh yêu cầu tải hàng chục nghìn document.
- **Trang sâu:** `OFFSET` lớn có thể làm Query Service đọc/bỏ qua nhiều hàng. Với dữ liệu lớn hoặc thay đổi thường xuyên, cân nhắc phân trang theo khóa sắp xếp (*keyset pagination*).
- **Dữ liệu thay đổi:** giữa hai lần truy vấn, document có thể được thêm/xóa/cập nhật; phân trang dựa trên offset có thể lặp hoặc bỏ sót document.

Không dựa vào thứ tự “tự nhiên” của collection. `LIMIT 10` mà không có `ORDER BY` thường không đảm bảo hai lần gọi trả đúng cùng mười document.

### Biểu thức trong `ORDER BY`

SQL++ có thể sắp theo nhiều thuộc tính:

```sql
SELECT p.sku, p.price
FROM `catalog`.`commerce`.`products` AS p
WHERE p.category = "keyboard"
ORDER BY p.price DESC, p.sku ASC;
```

Nếu khai báo cùng yêu cầu trong `@Query` trả về entity, ta chỉ thay phần chọn và lọc kiểu document bằng SpEL:

```java
@Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} "
     + "AND category = $1 "
     + "ORDER BY price DESC, sku ASC")
List<Product> findExpensiveFirst(String category);
```

Trong dữ liệu mẫu, KB-200 đứng trước KB-100. Việc sắp xếp theo `price` có thể làm thay đổi khả năng dùng chỉ mục, nên cần xem `EXPLAIN` ở workload thật.

## 8. Kiểu trả về của `@Query`: entity, tập kết quả và phép chiếu

Kiểu trả về cho biết Repository muốn xử lý kết quả thế nào:

| Kiểu kết quả Java | Nhu cầu thường gặp | Điều cần chú ý |
| --- | --- | --- |
| `List<Product>` | Trả nhiều entity thỏa điều kiện | `SELECT` phải chứa các trường/metadata cần ánh xạ full entity |
| `Optional<Product>` | Kỳ vọng 0 hoặc 1 entity | Truy vấn thực sự có thể khớp nhiều document sẽ gây lỗi hoặc không đúng hợp đồng |
| `Product` | Kỳ vọng một entity | Cần quy định cách xử lý khi không có hoặc có nhiều kết quả |
| Interface/class projection | Chỉ lấy vài trường theo cấu trúc DTO | Phép chiếu SQL++ và converter phải phù hợp tên/kiểu thuộc tính |
| `Flux<Product>` trong repository reactive | Đọc nhiều entity dưới dạng reactive | Cần dùng reactive repository và tiêu thụ luồng đúng cách |

### Truy vấn đầy đủ entity

Với `List<Product>`, mẫu phổ biến là:

```java
@Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} "
     + "AND active = true AND price <= $1")
List<Product> findActiveBelowPrice(long maxPrice);
```

`#{#n1ql.selectEntity}` được tạo theo mapping entity và metadata Couchbase, bao gồm những giá trị cần cho document ID/CAS. Nếu tự chọn `SELECT sku, price` rồi trả về `List<Product>`, kết quả có thể thiếu ID và các trường khác; việc ánh xạ đầy đủ không còn được bảo đảm.

### Truy vấn chỉ lấy một phần trường

Khi API chỉ cần mã và giá, câu SQL++ thuần có thể là:

```sql
SELECT p.sku AS sku, p.price AS price
FROM `catalog`.`commerce`.`products` AS p
WHERE p.active = true;
```

Một projection Java:

```java
public interface ProductPriceView {
    String getSku();
    Long getPrice();
}
```

Tùy phiên bản Spring Data Couchbase, Repository có thể hỗ trợ projection tương ứng với kiểu trả về và query, nhưng **không nên mặc định rằng mọi câu `SELECT` tự viết sẽ ánh xạ được mọi DTO**. Hãy kiểm tra cơ chế projection của phiên bản dự án, alias SQL++ khớp thuộc tính và converter cho các kiểu dữ liệu.

Với phép chiếu đặc thù, báo cáo `GROUP BY`/`COUNT` hay kết quả cần điều khiển thủ công, có thể dùng Couchbase Java SDK để đọc JSON row rồi ánh xạ DTO rõ ràng. Một hàng tổng hợp không phải document entity, vì vậy không nên ghép `#{#n1ql.selectEntity}` vào truy vấn `SELECT COUNT(*) ...`.

### Lựa chọn `findById` cho truy vấn một document

Nếu đầu vào đã là **document ID** (ví dụ `product::KB-100`), `repository.findById(id)` là lựa chọn tự nhiên vì thường dùng đường **Key/Value** nhanh hơn. `@Query` phù hợp khi cần tìm theo thuộc tính trong JSON, ngay cả khi điều kiện cuối cùng chỉ khớp một document.

Đừng nhầm `@Id` của entity với trường JSON `id`: `@Id` thường ánh xạ metadata ID do Couchbase quản lý. Nếu cần truy vấn SQL++ trực tiếp theo ID, dùng `META(p).id` với alias của nguồn:

```sql
SELECT META(p).id AS documentId, p.sku
FROM `catalog`.`commerce`.`products` AS p
WHERE META(p).id = "product::KB-100";
```

Câu trên hợp lệ về ngữ nghĩa SQL++ nhưng nếu đã biết ID, truy cập KV thông qua Repository/Template hoặc SDK thường là cơ chế phù hợp hơn.

## 9. Chỉ mục cho các phương thức `@Query`

`@Query` không làm mất đi yêu cầu về chỉ mục của Couchbase. Khi truy vấn có `WHERE category = ...` và `price <= ...`, Query Service phải có đường truy cập phù hợp đến các document. Với khối lượng dữ liệu lớn, một **secondary index** trên collection có thể cải thiện việc lọc:

```sql
CREATE INDEX idx_products_category_price
ON `catalog`.`commerce`.`products`(category, price);
```

Đây là ví dụ khởi đầu; chỉ mục thực tế cần dựa trên điều kiện lọc, thứ tự khóa, độ chọn lọc và `ORDER BY` của truy vấn. Với điều kiện `active = true`, có thể cân nhắc chỉ mục nhiều trường hoặc index có predicate phù hợp, thay vì tạo chỉ mục theo mỗi thuộc tính một cách máy móc.

### Kiểm tra `EXPLAIN` bằng SQL++ thuần

Đối với phương thức:

```java
@Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} "
     + "AND category = $1 AND price <= $2")
List<Product> findByCategoryAndMaxPrice(String category, long maxPrice);
```

có thể bắt đầu nghiên cứu kế hoạch bằng câu SQL++ tương đương về điều kiện:

```sql
EXPLAIN
SELECT p.sku, p.category, p.price
FROM `catalog`.`commerce`.`products` AS p
WHERE p.category = "keyboard"
  AND p.price <= 1600000;
```

**Lưu ý:** truy vấn này chỉ nhằm hiểu chỉ mục của điều kiện nghiệp vụ. Câu SQL++ **thực tế** mà Spring Data gửi có thể thêm discriminator loại entity và phép chiếu metadata. Khi đánh giá performance cuối cùng, hãy kiểm tra câu lệnh được thực thi hoặc bảo đảm `EXPLAIN` mô phỏng đủ những điều kiện, keyspace và biểu thức mà Repository sinh ra.

Trong kế hoạch, cần chú ý:

| Dấu hiệu | Ý nghĩa vận hành |
| --- | --- |
| Chọn đúng index theo `category`/`price` | Có cơ hội giảm số document phải xét |
| Phải `Fetch` nhiều document | Chỉ mục có thể chưa covering hoặc điều kiện cần đọc body |
| Sắp xếp sau khi đọc dữ liệu | `ORDER BY` có thể tiêu tốn CPU/bộ nhớ thêm |
| Phải xử lý `ANY` trên mảng | Có thể cần **array index** cho thuộc tính bên trong mảng |
| Không tìm được index phù hợp | Cần rà soát index, trạng thái index, đúng collection và quyền |

Ví dụ một truy vấn `ANY tag IN tags ...` không mặc nhiên tối ưu bởi index chỉ chứa `category`. Nếu tìm trên phần tử mảng thường xuyên, có thể cần index dựa trên biểu thức `DISTINCT ARRAY ... FOR ... END` và kiểm tra `EXPLAIN`.

Không nên tạo primary index chỉ để mọi câu SQL++ tùy ý có thể chạy trên production: nó có thể quét quá rộng và che giấu nhu cầu thiết kế secondary index theo workload.

## 10. Scan consistency: vừa lưu xong nhưng `@Query` chưa thấy dữ liệu

Couchbase có đường **Key/Value** và **Query/Index** với cơ chế cập nhật chỉ mục riêng. Một document vừa ghi thành công qua `repository.save(product)` có thể đọc được theo ID, nhưng truy vấn theo thuộc tính trong `@Query` có thể chưa nhìn thấy ngay nếu index chưa bắt kịp.

Ví dụ:

```java
repository.save(product);

// Đọc theo ID thường đi qua đường KV.
repository.findById(productId);

// Truy vấn theo category qua Query Service có thể phụ thuộc độ mới của index.
repository.findCategoryUsingSqlpp("keyboard");
```

Tình huống thường gặp:

| Scan consistency | Kỳ vọng | Đánh đổi |
| --- | --- | --- |
| `NOT_BOUNDED` | Trả lời dựa trên index hiện có, có thể chưa nhìn thấy ghi mới | Thường có độ trễ thấp hơn |
| `REQUEST_PLUS` | Chờ index xử lý các thay đổi trước thời điểm query | Có thể tăng thời gian phản hồi |

Với những phương thức cần tăng độ mới của kết quả, Spring Data Couchbase có cơ chế điều chỉnh scan consistency theo phiên bản. Ví dụ một cách khai báo ở các phiên bản có hỗ trợ annotation `@ScanConsistency`:

```java
import com.couchbase.client.java.query.QueryScanConsistency;
import org.springframework.data.couchbase.repository.ScanConsistency;

@ScanConsistency(query = QueryScanConsistency.REQUEST_PLUS)
@Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} "
     + "AND category = $1")
List<Product> findByCategoryWithFreshIndex(String category);
```

Đoạn trên là **phương thức bên trong Repository**; cần đối chiếu API annotation và phiên bản Spring Data/SDK của dự án trước khi đưa vào production. `REQUEST_PLUS` không biến một truy vấn thành giao dịch có mức cô lập tuyệt đối; nó giải quyết vấn đề độ cập nhật của index tại thời điểm truy vấn.

Không áp dụng `REQUEST_PLUS` cho mọi phương thức chỉ vì “an toàn hơn”: bảng danh mục sản phẩm có thể chấp nhận độ trễ index nhỏ, trong khi chức năng vừa tạo sản phẩm rồi tìm ngay có yêu cầu khác. Nếu đã biết ID, đọc trực tiếp KV có thể phù hợp hơn.

### TTL, CAS và transaction liên quan thế nào?

Các cơ chế này bổ trợ cho tầng truy cập dữ liệu:

- **TTL:** thời gian sống của document. Một document hết TTL có thể biến mất theo chính sách của Couchbase, ảnh hưởng kết quả tìm kiếm khi index phản ánh thay đổi.
- **CAS:** mã phiên bản ở mức document dùng để phát hiện cập nhật đồng thời; không tự thay đổi semantics của câu `SELECT` trong `@Query`.
- **Transactions:** nhóm thao tác cần ràng buộc nguyên tử/nhất quán được thực hiện qua cơ chế giao dịch thích hợp; một `@Query` đọc thông thường không tự tạo ranh giới transaction cho nhiều thao tác nghiệp vụ.

Đừng dựa vào `@Query` như cơ chế thay thế cho optimistic locking, TTL hay transaction khi nghiệp vụ cần những đặc tính riêng của chúng.

## 11. Khai báo `@Query` với Repository reactive

Spring Data Couchbase còn cung cấp **reactive repository** cho ứng dụng sử dụng mô hình xử lý bất đồng bộ. Một ví dụ khai báo phương thức:

```java
import reactor.core.publisher.Flux;
import org.springframework.data.couchbase.repository.Query;
import org.springframework.data.couchbase.repository.ReactiveCouchbaseRepository;

public interface ReactiveProductRepository
        extends ReactiveCouchbaseRepository<Product, String> {

    @Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} "
         + "AND active = $1")
    Flux<Product> findByActiveFlag(boolean enabled);
}
```

`Flux<Product>` cho phép xử lý kết quả theo mô hình reactive của Reactor. Điều kiện SQL++ không đổi: Query Service vẫn lọc document theo `active`, index vẫn quan trọng và scan consistency vẫn có thể ảnh hưởng độ mới của kết quả.

Đừng gọi các thao tác chặn luồng như `block()` trong chuỗi xử lý reactive của HTTP request chỉ để biến luồng thành danh sách. Nếu toàn bộ ứng dụng dùng WebFlux, nên giữ chuỗi xử lý không chặn và chỉ dùng reactive API khi hạ tầng thực sự hỗ trợ.

### So sánh sử dụng Repository và `CouchbaseTemplate`

| Cơ chế | Điểm mạnh | Khi nên cân nhắc |
| --- | --- | --- |
| Repository + derived query | Cực ngắn gọn với điều kiện đơn giản | Tra cứu phổ biến, ít bộ lọc |
| Repository + `@Query` | Câu SQL++ tường minh, hợp đồng phương thức rõ | Truy vấn phức tạp nhưng ổn định |
| `CouchbaseTemplate` | API fluent, linh hoạt khi xây điều kiện và mapping | Tìm kiếm có bộ lọc động, cần kiểm soát cách truy vấn |
| SDK `Cluster.query` | Điều khiển SQL++ và JSON row trực tiếp | Tổng hợp, DTO đặc thù, tính năng API thấp hơn |
| Reactive Repository/Template | Tích hợp với Reactor và backpressure ở ứng dụng | Hệ thống dùng reactive end-to-end |

Việc chọn API không làm biến mất nhu cầu thiết kế **bucket/scope/collection**, chỉ mục, chính sách TTL/CAS, giao dịch và consistency. Lựa chọn phải phù hợp cả yêu cầu nghiệp vụ lẫn cách vận hành hệ thống.

## 12. Lỗi thường gặp khi viết `@Query`

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Đã khai báo `@Query` nhưng ứng dụng không nhận annotation | Import sai annotation, chẳng hạn dùng `org.springframework.data.jpa.repository.Query` | Dùng `org.springframework.data.couchbase.repository.Query` |
| Workbench báo lỗi với `#{#n1ql.selectEntity}` | Đã gửi nguyên biểu thức SpEL đến máy chủ | Chỉ dùng SpEL trong Spring Data; thử bằng SQL++ thuần ở Workbench |
| Spring Data báo lỗi tham số hoặc điều kiện không nhận giá trị | Placeholder `$1`, `$2`, `$name` không khớp phương thức | So khớp thứ tự hoặc `@Param`, kiểm tra kiểu dữ liệu |
| `@Query` chạy nhưng không tìm thấy document có trong Workbench | `#n1ql.filter` yêu cầu discriminator phù hợp hoặc mapping chọn sai collection | Kiểm tra dữ liệu được lưu qua Spring Data, scope/collection và type metadata |
| Truy vấn entity ánh xạ sai ID/CAS | Dùng `SELECT *` hoặc chỉ lấy vài trường thay vì phép chiếu cho full entity | Dùng `#n1ql.selectEntity` khi trả về entity; DTO cho phép chiếu từng trường |
| Trường JSON lồng nhau không khớp | Sai đường dẫn `specs.connection` hoặc tên field mapping khác JSON | Kiểm tra tên JSON thực tế, `@Field` và `MISSING` |
| Query trên mảng trả quá nhiều hoặc ít document | Dùng chỉ số `tags[0]` thay vì `ANY` hoặc tách các điều kiện trên các phần tử khác nhau | Viết đúng lượng từ và giữ điều kiện cùng phần tử trong một `SATISFIES` |
| Truy vấn `category = null` không trả về trạng thái mong muốn | SQL++ phân biệt `NULL` và `MISSING` | Dùng `IS NULL`, `IS MISSING`, `IS VALUED` |
| Tham số có ký tự đặc biệt gây lỗi hoặc thay đổi điều kiện | Đã nối chuỗi dữ liệu người dùng vào SQL++ | Ràng buộc tham số `$1`/`$name`, chỉ chấp nhận định danh từ danh sách cho phép |
| Không tìm được index hoặc query chậm | Collection thiếu index phù hợp với `WHERE`/`ORDER BY` | Kiểm tra index và chạy `EXPLAIN` |
| Vừa lưu nhưng `@Query` không thấy document | Index chưa đồng bộ theo scan consistency | Đọc KV theo ID hoặc cân nhắc `REQUEST_PLUS` |
| Phân trang trả bản ghi trùng hoặc bỏ sót | Không có `ORDER BY` ổn định hoặc dữ liệu đổi giữa các lần gọi | Chọn khóa sắp xếp xác định; cân nhắc phân trang theo khóa |
| Kết quả tổng hợp không ánh xạ thành entity | Hàng báo cáo không có metadata và cấu trúc của document `Product` | Dùng projection/DTO tương ứng, xác minh converter hoặc map qua SDK |

### Quy trình gỡ lỗi theo thứ tự

1. **Kiểm tra đúng kho dữ liệu:** bucket, scope, collection, dữ liệu JSON và discriminator của entity.
2. **Kiểm tra đúng hợp đồng phương thức:** import `@Query`, thứ tự `$1/$2` hoặc tên `@Param`, kiểu giá trị, kiểu trả về.
3. **Tách hai lớp cú pháp:** SpEL phải được Spring Data thay thế; SQL++ còn lại phải hợp lệ trong Query Service.
4. **Thử dữ liệu thật:** chạy câu SQL++ thuần tương đương trong Workbench với giá trị ví dụ đã biết.
5. **Xem chỉ mục:** dùng `EXPLAIN` trên truy vấn thực tế hoặc truy vấn tương đương với đầy đủ điều kiện.
6. **Kiểm tra độ mới dữ liệu:** quan sát sự khác nhau giữa truy vấn theo ID và truy vấn theo thuộc tính khi vừa ghi.

Khi theo dõi log truy vấn, tránh ghi toàn bộ giá trị nhạy cảm và thông tin kết nối vào log chỉ để debug. Các tùy chọn log SQL++ và tham số phải tuân thủ chính sách bảo mật của ứng dụng.

## 13. Bài thực hành có đáp án

Giả sử bốn document `KB-100`, `KB-200`, `MS-100`, `HS-100` ở phần 2 đã được lưu với đúng mapping `Product` và chỉ mục đã sẵn sàng.

### Bài 1 — Tìm bàn phím không vượt quá một mức giá

**Yêu cầu:** Định nghĩa Repository `findKeyboardCheaperThan(long maxPrice)`, trả về entity đầy đủ.

```java
@Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} "
     + "AND category = 'keyboard' AND price <= $1 "
     + "ORDER BY price ASC, sku ASC")
List<Product> findKeyboardCheaperThan(long maxPrice);
```

**Đáp án khi gọi `findKeyboardCheaperThan(1600000)`:** chỉ KB-100. KB-200 có giá 1.900.000 nên bị loại. Ở đây `'keyboard'` là hằng chuỗi SQL++, còn `$1` là giá trị được ràng buộc. Trong ứng dụng cần dùng lại cho nhiều danh mục, nên truyền `category` thành tham số thay vì cố định hằng này.

### Bài 2 — Tìm sản phẩm đang hoạt động theo tag

**Yêu cầu:** Tag do người dùng truyền, và chỉ trả về sản phẩm `active = true`.

```java
@Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} "
     + "AND active = true "
     + "AND ANY t IN tags SATISFIES t = $1 END")
List<Product> findEnabledByTag(String tag);
```

**Đáp án với tag `"wireless"`:** KB-200. MS-100 bị loại do không hoạt động. Điều kiện `ANY` kiểm tra mọi phần tử tag thay vì cố định `tags[0]`.

### Bài 3 — Truy vấn tên và giá theo nhóm, dùng tham số có tên

**Yêu cầu:** Truy vấn theo `category` và `maxPrice`, sắp xếp giá giảm dần.

```java
@Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} "
     + "AND category = $category AND price <= $maxPrice "
     + "ORDER BY price DESC, sku ASC")
List<Product> findCategoryPriceDesc(
    @Param("category") String category,
    @Param("maxPrice") long maxPrice
);
```

**Đáp án khi gọi `findCategoryPriceDesc("keyboard", 2000000)`:** KB-200 trước KB-100. Tên tham số trong `$category` và `$maxPrice` khớp chính xác với `@Param`.

### Bài 4 — Dự đoán hậu quả của `SELECT *`

Xét câu khai báo:

```java
@Query("SELECT * FROM `catalog`.`commerce`.`products` "
     + "WHERE category = $1")
List<Product> findRawProducts(String category);
```

**Đáp án:** SQL++ có thể thực thi được, nhưng `SELECT *` thường trả về hàng chứa object lồng theo keyspace/alias, thiếu phép chiếu metadata riêng mà Spring Data mong đợi khi khôi phục full entity. Không nên giả định `List<Product>` sẽ được dựng đúng; dùng `#{#n1ql.selectEntity} WHERE #{#n1ql.filter} AND ...` cho kiểu trả về full entity.

### Bài 5 — Chọn cơ chế truy cập phù hợp

Trong mỗi tình huống, chọn giữa `findById`, derived query, `@Query`, `CouchbaseTemplate` hoặc SDK:

| Tình huống | Lựa chọn tham khảo |
| --- | --- |
| Có document ID và cần đọc một sản phẩm | `findById` / Key/Value |
| Tìm một category đơn giản | Derived query |
| Tìm theo `ANY` trên tags, kết hợp nhiều điều kiện cố định | `@Query` |
| Form tìm kiếm có nhiều trường tùy chọn, điều kiện được xây động | `CouchbaseTemplate` hoặc API xây query phù hợp |
| Tạo bảng thống kê theo category với phép chiếu tùy chỉnh | Query/projection phù hợp hoặc SDK + DTO |

### Bài 6 — Kiểm tra đúng thứ tự trong một lần truy vấn thực tế

Thực hiện các bước trên một môi trường thử nghiệm:

1. Tạo index phù hợp cho `category` và `price` ở collection.
2. Lưu hai sản phẩm bàn phím bằng Repository để bảo đảm metadata mapping nhất quán.
3. Gọi một phương thức `@Query` dùng `$1` hoặc `@Param` và so sánh kết quả với dữ liệu mẫu.
4. Chạy câu SQL++ tương đương trong Workbench; phân biệt rõ phần SpEL của Spring Data và phần SQL++ server thực thi.
5. Dùng `EXPLAIN` để xem index; thử một điều kiện khác cần index bổ sung.
6. Thử ghi và đọc lại: so sánh `findById` với truy vấn `@Query` dưới scan consistency đang cấu hình.

Khi viết kiểm thử tích hợp, nên kiểm tra cả **số lượng kết quả, nội dung document, ID ánh xạ, các giá trị tham số đặc biệt, index và trường hợp không có kết quả**. Chỉ kiểm tra chuỗi Java chứa `@Query` bằng unit test không bảo đảm Query Service hiểu và ánh xạ câu lệnh đúng.

## 14. Câu hỏi tự kiểm tra

1. **`@Query` khác derived query như thế nào?** `@Query` để lập trình viên khai báo SQL++ trực tiếp; derived query được Spring Data dựng từ tên phương thức.
2. **Vì sao `#{#n1ql.selectEntity}` vẫn hợp lệ dù tên ngôn ngữ là SQL++?** `n1ql` là tên lịch sử của biến hỗ trợ SpEL trong Spring Data; kết quả gửi đến Couchbase vẫn là SQL++.
3. **`#{#n1ql.filter}` giải quyết vấn đề gì?** Giúp hạn chế kết quả theo kiểu entity/discriminator mà Spring Data quản lý.
4. **`$1` và `$category` khác nhau ở đâu?** Một bên là tham số theo vị trí, bên kia theo tên `@Param("category")`.
5. **Tại sao phải dùng binding thay vì nối chuỗi SQL++?** Giúp biểu diễn giá trị đúng kiểu, tránh lỗi dấu nháy và giảm rủi ro injection.
6. **Khi nào `SELECT *` không nên thay `#{#n1ql.selectEntity}`?** Khi phương thức trả về entity đầy đủ cần ID/CAS và phép chiếu phù hợp với mapping.
7. **Vì sao một `@Query` có thể chạy chậm dù SQL++ đúng cú pháp?** Có thể thiếu index, dùng sai thứ tự khóa, điều kiện không chọn lọc, `ORDER BY` tốn chi phí hoặc đang quét mảng.
8. **Vì sao vừa ghi document nhưng Repository `@Query` chưa tìm thấy?** Query index có thể cập nhật trễ so với đường Key/Value, phụ thuộc scan consistency.
9. **Reactive Repository có dùng ngôn ngữ khác SQL++ không?** Không. Nó thay mô hình thực thi và tiêu thụ kết quả, vẫn cần truy vấn/index phù hợp.
10. **Có nên dùng `@Query` cho mọi thao tác?** Không. Đọc theo ID, lọc đơn giản, bộ lọc động và báo cáo tổng hợp có thể phù hợp các API khác nhau.

## Tài liệu tham khảo chính thức

- [Spring Data Couchbase — Couchbase Repositories](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): `@Query`, phương thức suy diễn, tham số, SpEL và Repository mapping.
- [Spring Data Couchbase — Collections](https://docs.spring.io/spring-data/couchbase/reference/couchbase/collections.html): mapping bucket/scope/collection.
- [Spring Data Couchbase — Querying with Template](https://docs.spring.io/spring-data/couchbase/reference/couchbase/template-query-operations.html): các API truy vấn thông qua Template.
- [Couchbase Java SDK — SQL++ Queries](https://docs.couchbase.com/java-sdk/current/howtos/n1ql-queries-with-sdk.html): thực thi SQL++ và tham số truy vấn.
- [Couchbase Server — SQL++ Query Language](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/index.html): `SELECT`, `FROM`, `WHERE`, `ANY`, `ORDER BY` và `LIMIT`.
- [Couchbase Server — Indexes](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/indexing.html): chỉ mục cho Query Service và truy vấn tối ưu.

**Ghi nhớ:** `@Query` cho phép đặt một câu SQL++ trên phương thức Spring Data Couchbase Repository. Với kết quả là **entity đầy đủ**, mẫu `#{#n1ql.selectEntity} WHERE #{#n1ql.filter} AND ...` thường là điểm xuất phát tốt; truyền dữ liệu đầu vào bằng `$1` hoặc `$name`, thiết kế chỉ mục theo `WHERE/ORDER BY` và chọn scan consistency theo yêu cầu nghiệp vụ. Đối với projection, báo cáo hay truy vấn thay đổi linh hoạt, hãy chọn cơ chế ánh xạ và API phù hợp với hình dạng kết quả thực tế.

# Mảng, đối tượng lồng nhau và biểu thức ANY hoặc EVERY trong Couchbase SQL++

> **Mục tiêu bài học:** Truy cập đúng object và array trong JSON document, hiểu cách `ANY`, `EVERY` và `ANY AND EVERY` đánh giá điều kiện, viết truy vấn trên mảng object nhiều cấp và dùng chúng trong Spring Data Couchbase `@Query`.

Trong module **SPRING_DATA_COUCHBASE**, Spring Data lưu entity Java thành JSON document ở bucket/scope/collection của Couchbase. Dữ liệu thực tế thường có cấu trúc nhiều cấp: thuộc tính kỹ thuật là object, danh sách nhãn là mảng chuỗi, còn các biến thể sản phẩm là mảng object. **SQL++** (trước đây thường gọi **N1QL**) cho phép truy vấn trực tiếp các cấu trúc này mà không cần tách chúng thành nhiều bảng quan hệ.

Một quy tắc xuyên suốt: **đường dẫn JSON** lấy giá trị ở một vị trí; **`ANY`** hỏi có phần tử thỏa điều kiện hay không; **`EVERY`** hỏi tất cả phần tử có thỏa điều kiện hay không. Việc phân biệt ba cách đọc này quyết định tính đúng đắn của bộ lọc nghiệp vụ.

## 1. Dữ liệu mẫu và mục tiêu truy vấn

Giả sử hệ thống có bucket `catalog`, scope `commerce` và collection `products`. Mỗi sản phẩm là một document JSON. Bốn document sau minh họa các tình huống phổ biến.

**Document ID: `product::KB-100`**

```json
{
  "sku": "KB-100",
  "category": "keyboard",
  "name": "Bàn phím cơ TKL",
  "active": true,
  "specs": {
    "layout": "TKL",
    "connection": {
      "type": "wired",
      "ports": ["USB-C"]
    }
  },
  "tags": ["gaming", "rgb"],
  "variants": [
    {
      "color": "black",
      "stock": 12,
      "warehouses": [
        { "code": "HCM", "qty": 6 },
        { "code": "HAN", "qty": 6 }
      ]
    },
    {
      "color": "white",
      "stock": 0,
      "warehouses": [
        { "code": "HCM", "qty": 0 }
      ]
    }
  ]
}
```

**Document ID: `product::KB-200`**

```json
{
  "sku": "KB-200",
  "category": "keyboard",
  "name": "Bàn phím văn phòng",
  "active": true,
  "specs": {
    "layout": "75%",
    "connection": {
      "type": "wireless",
      "ports": []
    }
  },
  "tags": ["office", "wireless"],
  "variants": [
    {
      "color": "gray",
      "stock": 7,
      "warehouses": [
        { "code": "HCM", "qty": 5 },
        { "code": "HAN", "qty": 2 }
      ]
    },
    {
      "color": "white",
      "stock": 3,
      "warehouses": [
        { "code": "HCM", "qty": 3 }
      ]
    }
  ]
}
```

**Document ID: `product::MS-100`**

```json
{
  "sku": "MS-100",
  "category": "mouse",
  "name": "Chuột văn phòng",
  "active": false,
  "specs": {
    "connection": { "type": "wireless" }
  },
  "tags": [],
  "variants": []
}
```

**Document ID: `product::HS-100`**

```json
{
  "sku": "HS-100",
  "category": "headset",
  "name": "Tai nghe cơ bản",
  "active": true,
  "specs": {},
  "tags": ["audio"]
}
```

Những document này đặt ra các câu hỏi khác nhau:

- **Object lồng nhau:** sản phẩm có `specs.connection.type = "wireless"`?
- **Mảng chuỗi:** sản phẩm có nhãn `wireless` trong `tags`?
- **Mảng object:** có **ít nhất một** biến thể màu trắng **còn hàng**?
- **Điều kiện toàn bộ:** **mọi** biến thể có `stock > 0`?
- **Nhiều cấp mảng:** có biến thể nào có kho `HCM` với `qty > 0`?
- **Dữ liệu không đồng nhất:** `variants: []` khác gì với **không có** trường `variants`?

Các câu SQL++ bên dưới dùng đường dẫn đầy đủ:

```sql
FROM `catalog`.`commerce`.`products` AS p
```

`catalog` là bucket, `commerce` là scope, `products` là collection và `p` là bí danh document. Dấu backtick bao tên keyspace là dấu trích dẫn **định danh**; dấu nháy đôi `"white"` là **giá trị chuỗi**. Chỉ mục, quyền truy vấn và dữ liệu thật phải tồn tại để chạy ví dụ trên Couchbase.

## 2. Truy cập object lồng nhau bằng dấu chấm

Với object `specs` chứa object `connection`, đường dẫn dùng dấu chấm:

```sql
SELECT p.sku,
       p.specs.connection.type AS connectionType,
       p.specs.layout AS keyboardLayout
FROM `catalog`.`commerce`.`products` AS p
WHERE p.specs.connection.type = "wireless";
```

Trong dữ liệu mẫu, KB-200 và MS-100 có `connectionType = "wireless"`. KB-100 có `wired`; HS-100 thiếu `specs.connection` nên không thỏa điều kiện.

Mỗi dấu chấm có nghĩa là **đi sâu thêm một cấp object**. Chẳng hạn:

| Biểu thức | Giá trị ở KB-100 | Ý nghĩa |
| --- | --- | --- |
| `p.sku` | `"KB-100"` | Trường ở cấp gốc |
| `p.specs` | Một object | Toàn bộ object kỹ thuật |
| `p.specs.layout` | `"TKL"` | Một thuộc tính cấp hai |
| `p.specs.connection.type` | `"wired"` | Thuộc tính bên trong object cấp ba |
| `p.specs.connection.ports` | `["USB-C"]` | Một mảng nằm trong object lồng nhau |

### Tên thuộc tính đặc biệt

Nếu JSON có khóa chứa ký tự đặc biệt như `"screen.size"` hoặc `"width-mm"`, cần trích dẫn **toàn bộ tên thuộc tính** bằng backtick trong SQL++:

```sql
SELECT p.`screen.size` AS screenSize,
       p.dimensions.`width-mm` AS widthMm
FROM `catalog`.`commerce`.`products` AS p;
```

Đường dẫn dùng tên thuộc tính đã được trích dẫn trong khối SQL++ trên (một trường có dấu chấm) khác `p.screen.size` (đường dẫn hai cấp). Các trường này chưa xuất hiện trong bộ dữ liệu mẫu; đoạn trên minh họa cú pháp với JSON tương ứng, chẳng hạn `{"screen.size": 24, "dimensions": {"width-mm": 360}}`.

### Không có trường không giống trường bằng `null`

Ở HS-100, `specs` là object rỗng nên `p.specs.connection` trả về **MISSING**. Trong JSON khác, `"connection": null` biểu thị giá trị **NULL** có tồn tại. Phân biệt bằng các vị từ:

```sql
SELECT p.sku
FROM `catalog`.`commerce`.`products` AS p
WHERE p.specs.connection IS MISSING;
```

```sql
SELECT p.sku
FROM `catalog`.`commerce`.`products` AS p
WHERE p.specs.connection IS VALUED;
```

`IS MISSING` kiểm tra thiếu trường; `IS VALUED` chỉ đúng khi có giá trị khác `NULL` và `MISSING`. Trong `WHERE`, chỉ biểu thức đánh giá thành **TRUE** mới được chọn; phép so sánh với đường dẫn thiếu trường sẽ không làm document được giữ lại.

## 3. Mảng JSON: đọc một phần tử và hiểu giới hạn

Cú pháp `array[index]` đọc một phần tử theo vị trí, **đếm từ 0**:

```sql
SELECT p.sku,
       p.tags[0] AS firstTag,
       p.variants[0].color AS firstVariantColor,
       p.variants[0].warehouses[0].code AS firstWarehouseCode
FROM `catalog`.`commerce`.`products` AS p
WHERE p.sku = "KB-100";
```

Kết quả minh họa:

```json
{
  "sku": "KB-100",
  "firstTag": "gaming",
  "firstVariantColor": "black",
  "firstWarehouseCode": "HCM"
}
```

Đường dẫn `p.variants[0].warehouses[0].code` đi qua **mảng → object → mảng → object**. Nếu array rỗng, thiếu phần tử hoặc thiếu thuộc tính, giá trị có thể là `MISSING`. Một giá trị `MISSING` thường bị lược khỏi object chiếu trong kết quả.

Tuy nhiên, chỉ số `[0]` không diễn đạt được yêu cầu “**có một phần tử bất kỳ** thỏa điều kiện”. Ví dụ KB-200 có biến thể trắng ở vị trí thứ hai; `p.variants[0].color = "white"` sẽ bỏ sót KB-200. Đó là lý do cần các biểu thức định lượng trên mảng.

## 4. `ANY`: có ít nhất một phần tử thỏa điều kiện

`ANY` là biểu thức kiểm tra **tồn tại** phần tử thỏa biểu thức Boolean.

```sql
ANY variable IN arrayExpression
SATISFIES condition
END
```

Trong đó:

- `variable` là biến cục bộ, chỉ có ý nghĩa trong điều kiện của `ANY`.
- `arrayExpression` phải biểu diễn mảng muốn xét.
- `condition` là điều kiện được đánh giá cho mỗi phần tử.
- Biểu thức trả về TRUE nếu **có ít nhất một phần tử** thỏa.

### `ANY` với mảng chuỗi

Tìm sản phẩm có nhãn `wireless`:

```sql
SELECT p.sku, p.tags
FROM `catalog`.`commerce`.`products` AS p
WHERE ANY tag IN p.tags
      SATISFIES tag = "wireless"
      END;
```

Chỉ KB-200 có phần tử `"wireless"` trong `tags`. MS-100 kết nối không dây nhưng `tags` rỗng; hai trường này mang ý nghĩa khác nhau. Viết `p.tags = "wireless"` là so sánh **mảng** với **chuỗi**, không biểu thị kiểm tra thành viên.

### `ANY` với mảng object

Tìm sản phẩm có biến thể **màu trắng và tồn kho dương**:

```sql
SELECT p.sku, p.name
FROM `catalog`.`commerce`.`products` AS p
WHERE ANY v IN p.variants
      SATISFIES v.color = "white" AND v.stock > 0
      END;
```

Kết quả chỉ có **KB-200**. KB-100 có biến thể màu trắng nhưng `stock = 0`, nên không thỏa.

**Một bẫy logic quan trọng:** viết hai `ANY` tách nhau có thể làm sai điều kiện “cùng một biến thể”:

```sql
-- Sai nếu nghiệp vụ yêu cầu chính biến thể màu trắng phải còn hàng.
WHERE ANY v IN p.variants SATISFIES v.color = "white" END
  AND ANY w IN p.variants SATISFIES w.stock > 0 END
```

KB-100 có biến thể trắng hết hàng và biến thể đen còn hàng, vì vậy **cả hai `ANY` riêng biệt đều TRUE**. Để đảm bảo cả hai điều kiện áp dụng trên **cùng một phần tử**, đặt chúng chung trong một `SATISFIES` với cùng biến `v`.

### `ANY` khi kết hợp điều kiện ngoài mảng

```sql
SELECT p.sku
FROM `catalog`.`commerce`.`products` AS p
WHERE p.active = true
  AND p.category = "keyboard"
  AND ANY v IN p.variants
      SATISFIES v.stock >= 5
      END;
```

Truy vấn chọn những bàn phím đang hoạt động có **ít nhất một biến thể** còn từ 5 đơn vị trở lên. Với dữ liệu mẫu, KB-100 và KB-200 đều đáp ứng.

## 5. `EVERY`: tất cả phần tử đều thỏa

Trong khi `ANY` biểu diễn “tồn tại ít nhất một”, `EVERY` biểu diễn “với **mọi** phần tử”. Cú pháp:

```sql
EVERY variable IN arrayExpression
SATISFIES condition
END
```

Ví dụ: tìm sản phẩm mà **mọi biến thể** đều còn hàng:

```sql
SELECT p.sku
FROM `catalog`.`commerce`.`products` AS p
WHERE EVERY v IN p.variants
      SATISFIES v.stock > 0
      END;
```

Trong dữ liệu mẫu:

| Sản phẩm | `variants` | `ANY v ... stock > 0` | `EVERY v ... stock > 0` |
| --- | --- | --- | --- |
| KB-100 | Đen: 12; trắng: 0 | TRUE | FALSE |
| KB-200 | Xám: 7; trắng: 3 | TRUE | TRUE |
| MS-100 | Mảng rỗng `[]` | FALSE | **TRUE** |
| HS-100 | Không có trường `variants` | Không thỏa `WHERE` | Không thỏa `WHERE` |

Điểm dễ bỏ qua là **`EVERY` với mảng rỗng trả về TRUE**. Đây là quy tắc logic “mọi phần tử thỏa điều kiện” khi **không có phần tử nào phản ví dụ** (*vacuous truth*). Với MS-100, không có biến thể nào vi phạm `stock > 0`. Vì vậy, `EVERY` **không tự bảo đảm mảng có phần tử**.

Trong khi đó, HS-100 **thiếu hẳn trường `variants`**. Thiếu trường không đồng nghĩa với một mảng `[]`; khi đưa biểu thức lên `WHERE`, không nên xem document thiếu trường là đã thỏa điều kiện “mọi biến thể”. Có thể thêm kiểm tra kiểu dữ liệu và độ dài mảng để chính sách lọc rõ ràng.

### Khi nghiệp vụ yêu cầu ít nhất một biến thể

Thêm điều kiện mảng có phần tử:

```sql
SELECT p.sku
FROM `catalog`.`commerce`.`products` AS p
WHERE p.variants IS ARRAY
  AND ARRAY_LENGTH(p.variants) > 0
  AND EVERY v IN p.variants
      SATISFIES v.stock > 0
      END;
```

Truy vấn này trả về **KB-200**. Điều kiện `IS ARRAY` xác minh loại dữ liệu, còn `ARRAY_LENGTH(p.variants) > 0` loại mảng rỗng. Cách viết này phù hợp với yêu cầu “sản phẩm phải có biến thể và tất cả biến thể phải còn hàng”.

### `ANY AND EVERY`: ít nhất một phần tử và mọi phần tử

SQL++ còn hỗ trợ:

```sql
ANY AND EVERY v IN p.variants
SATISFIES v.stock > 0
END
```

Biểu thức này yêu cầu **mảng có ít nhất một phần tử thỏa và mọi phần tử đều thỏa**. Nó trả về FALSE đối với mảng rỗng, trong khi `EVERY` đơn thuần trả về TRUE với mảng rỗng.

Ví dụ:

```sql
SELECT p.sku
FROM `catalog`.`commerce`.`products` AS p
WHERE ANY AND EVERY v IN p.variants
      SATISFIES v.stock > 0
      END;
```

Trong dữ liệu mẫu, chỉ KB-200 được chọn. Cả hai cách viết `ANY AND EVERY` và `ARRAY_LENGTH(...) > 0 AND EVERY ...` đều diễn đạt mục tiêu với mảng hợp lệ. Biến thể có `stock` không tồn tại hoặc không phải số vẫn cần được xử lý theo quy tắc dữ liệu thực tế.

### So sánh ba biểu thức định lượng

| Biểu thức | Mảng `[]` | Mảng `[0, 3]` với điều kiện `x > 0` | Mảng `[1, 3]` với điều kiện `x > 0` |
| --- | --- | --- | --- |
| `ANY x IN a SATISFIES x > 0 END` | FALSE | TRUE | TRUE |
| `EVERY x IN a SATISFIES x > 0 END` | TRUE | FALSE | TRUE |
| `ANY AND EVERY x IN a SATISFIES x > 0 END` | FALSE | FALSE | TRUE |

Khi giải bài toán, hãy chuyển câu yêu cầu thành các lượng từ rõ ràng: **“có ít nhất một” → `ANY`**, **“tất cả” → `EVERY`**, **“tất cả và mảng không rỗng” → `ANY AND EVERY`**. Tránh suy luận từ tên cột hay giá trị trả về của một document riêng lẻ.

## 6. Mảng lồng trong mảng: kết hợp hai `ANY`

Các biến thể có mảng `warehouses` chứa những kho phân phối. Để trả lời “có biến thể nào còn hàng tại kho HCM?”, cần duyệt **hai cấp mảng**:

```sql
SELECT p.sku, p.name
FROM `catalog`.`commerce`.`products` AS p
WHERE ANY v IN p.variants
      SATISFIES ANY w IN v.warehouses
                SATISFIES w.code = "HCM" AND w.qty > 0
                END
      END;
```

Trong ví dụ, cả **KB-100** và **KB-200** có biến thể chứa kho HCM với số lượng dương. Biến `v` đại diện cho **một biến thể**, còn `w` đại diện cho **một kho của chính biến thể đó**.

Nếu yêu cầu là “biến thể **màu trắng** phải còn hàng **tại HCM**”, gắn toàn bộ điều kiện vào cùng một biến thể:

```sql
SELECT p.sku
FROM `catalog`.`commerce`.`products` AS p
WHERE ANY v IN p.variants
      SATISFIES v.color = "white"
        AND ANY w IN v.warehouses
            SATISFIES w.code = "HCM" AND w.qty > 0
            END
      END;
```

Chỉ **KB-200** thỏa. KB-100 có hàng tại HCM ở biến thể **đen**, nhưng biến thể **trắng** đã hết hàng ở HCM. Quan hệ cha-con ở đây rất quan trọng: `w` phải được chọn từ `v.warehouses`, không phải một mảng kho của biến thể khác.

Có thể kết hợp `ANY` ở cấp ngoài với `EVERY` ở cấp trong:

```sql
SELECT p.sku
FROM `catalog`.`commerce`.`products` AS p
WHERE ANY v IN p.variants
      SATISFIES ARRAY_LENGTH(v.warehouses) > 0
        AND EVERY w IN v.warehouses
            SATISFIES w.qty >= 0
            END
      END;
```

Truy vấn này hỏi “có ít nhất một biến thể có danh sách kho không rỗng, và **mọi kho của biến thể ấy** có số lượng không âm?”. Điều kiện độ dài mảng tránh trường hợp `EVERY` TRUE vì mảng kho rỗng. Với dữ liệu không tin cậy, có thể thêm `v.warehouses IS ARRAY` để lọc đúng kiểu dữ liệu.

## 7. Biến đổi mảng khi `SELECT`: `ARRAY ... FOR ... WHEN ... END`

`ANY` và `EVERY` chủ yếu phục vụ **điều kiện**. Nếu cần trả về danh sách các giá trị trong một mảng, dùng biểu thức `ARRAY`:

```sql
SELECT p.sku,
       ARRAY v.color
         FOR v IN p.variants
         WHEN v.stock > 0
       END AS availableColors
FROM `catalog`.`commerce`.`products` AS p
WHERE p.variants IS ARRAY
ORDER BY p.sku;
```

Kết quả minh họa:

```json
[
  { "sku": "KB-100", "availableColors": ["black"] },
  { "sku": "KB-200", "availableColors": ["gray", "white"] },
  { "sku": "MS-100", "availableColors": [] }
]
```

`FOR v IN p.variants` duyệt các biến thể; `WHEN v.stock > 0` chỉ giữ các biến thể còn hàng; `v.color` quyết định giá trị đưa vào mảng mới. Điều kiện `p.variants IS ARRAY` giúp loại document có cấu trúc thiếu hoặc sai kiểu khỏi ví dụ.

### Khi cần mỗi phần tử là một dòng: `UNNEST`

Nếu hệ thống cần xuất **một dòng cho từng biến thể**, thay vì một dòng cho mỗi sản phẩm, dùng `UNNEST`:

```sql
SELECT p.sku, v.color, v.stock
FROM `catalog`.`commerce`.`products` AS p
UNNEST p.variants AS v
WHERE v.stock > 0
ORDER BY p.sku, v.color;
```

Kết quả có một dòng biến thể đen của KB-100 và hai dòng biến thể xám, trắng của KB-200. `UNNEST` thay đổi số lượng dòng kết quả: một document có thể sinh nhiều dòng và document có mảng rỗng sẽ không có dòng theo phép `UNNEST` thông thường.

| Mục đích | Kỹ thuật phù hợp |
| --- | --- |
| Lấy phần tử ở vị trí cố định | `array[index]` |
| Lọc document nếu tồn tại phần tử phù hợp | `ANY` |
| Lọc document khi mọi phần tử phù hợp | `EVERY` |
| Mọi phần tử phù hợp và mảng không rỗng | `ANY AND EVERY` |
| Tạo mảng giá trị mới từ mảng đầu vào | `ARRAY ... FOR ... WHEN ... END` |
| Biến từng phần tử mảng thành hàng kết quả | `UNNEST` |

## 8. Áp dụng `ANY` và `EVERY` trong Spring Data Couchbase `@Query`

Trong Spring Data Couchbase, entity Java có thể chứa object lồng nhau và `List` ánh xạ về JSON object/array. Tầng Repository cho phép viết SQL++ trong `@Query`, trong đó `#{#n1ql.selectEntity}` và `#{#n1ql.filter}` là các biểu thức hỗ trợ của Spring Data. Chữ `n1ql` trong tên API được giữ vì lý do tương thích; câu truy vấn cuối cùng vẫn là SQL++.

Giả sử kết nối đã chọn bucket `catalog`, entity `Product` ánh xạ đến scope `commerce` và collection `products`:

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
    private Boolean active;
    private Specs specs;
    private List<String> tags;
    private List<Variant> variants;

    public Product() {}

    public static class Specs {
        private String layout;
        private Connection connection;
        public Specs() {}
    }

    public static class Connection {
        private String type;
        private List<String> ports;
        public Connection() {}
    }

    public static class Variant {
        private String color;
        private Integer stock;
        private List<Warehouse> warehouses;
        public Variant() {}
    }

    public static class Warehouse {
        private String code;
        private Integer qty;
        public Warehouse() {}
    }

    // Bổ sung getter/setter hoặc accessors theo convention của dự án.
}
```

Ở đây:

- `List<String> tags` đại diện cho mảng các chuỗi.
- `List<Variant> variants` đại diện cho mảng các object.
- `Variant.warehouses` là mảng object lồng thêm một cấp.
- `Specs.connection.type` tương ứng đường dẫn SQL++ `specs.connection.type`.
- `@Id` ánh xạ document ID từ metadata, không đòi hỏi JSON body có trường `id`.

Một repository truy vấn biến thể màu trắng còn hàng:

```java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;
import org.springframework.data.couchbase.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ProductRepository extends CouchbaseRepository<Product, String> {

    @Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} "
         + "AND category = $category "
         + "AND ANY v IN variants "
         + "    SATISFIES v.color = $color AND v.stock >= $minStock "
         + "    END")
    List<Product> findByVariant(
        @Param("category") String category,
        @Param("color") String color,
        @Param("minStock") int minStock
    );
}
```

Ví dụ gọi:

```java
List<Product> result =
    productRepository.findByVariant("keyboard", "white", 1);
```

Trên những document được ánh xạ đúng, kết quả nghiệp vụ là **KB-200**. Các thành phần có ý nghĩa:

| Thành phần | Vai trò |
| --- | --- |
| `#{#n1ql.selectEntity}` | Sinh phần `SELECT/FROM` cho phép ánh xạ full entity, gồm metadata cần thiết |
| `#{#n1ql.filter}` | Giới hạn document theo discriminator kiểu entity do Spring Data quản lý |
| `category = $category` | Điều kiện trên trường JSON cấp gốc với tham số có tên |
| `ANY v IN variants ... END` | Kiểm tra các object trong mảng `variants` |
| `$color` và `$minStock` | Giá trị được Spring Data ràng buộc từ các tham số `@Param` |

**Đặc biệt:** `$color` là giá trị do người gọi truyền; tuyệt đối tránh nối giá trị người dùng thành đoạn SQL++:

```java
// Không làm thế này với dữ liệu đầu vào người dùng:
// String query = "... v.color = \\"" + color + "\\" ...";
```

Sử dụng tham số có tên `$color` hoặc vị trí `$1` sẽ giúp tránh nhầm lẫn dấu nháy và giảm rủi ro SQL injection. Tham số nên dùng cho **giá trị**, không dùng để truyền nguyên tên field, tên collection hoặc một mảnh cú pháp động.

### `EVERY` trong Repository

Nếu nghiệp vụ yêu cầu **mọi biến thể còn hàng và tồn tại ít nhất một biến thể**:

```java
@Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} "
     + "AND category = $1 "
     + "AND ANY AND EVERY v IN variants "
     + "    SATISFIES v.stock > 0 END")
List<Product> findWithAllVariantsInStock(String category);
```

Với danh mục `keyboard`, truy vấn này chỉ trả KB-200 trong bộ dữ liệu mẫu. Khi sử dụng `EVERY` đơn thuần trong nghiệp vụ thực tế, hãy quyết định rõ liệu collection có được phép chứa mảng `[]` và kết quả TRUE với mảng rỗng có phù hợp hay không.

### Cẩn trọng với dữ liệu chèn bằng SQL++ hoặc SDK

Các JSON mẫu ở đầu bài không chứa trường phân biệt kiểu của Spring Data. Nếu tự thêm chúng bằng Query Workbench/SDK và không gắn metadata phân loại, `#{#n1ql.filter}` có thể loại các document đó. Để thử Repository, nên lưu dữ liệu bằng chính Spring Data mapping hoặc bảo đảm discriminator (thường là `_class`) phù hợp với entity và cấu hình ứng dụng.

Với phương thức trả về **full entity** (`List<Product>`), hãy giữ `#{#n1ql.selectEntity}` để Spring Data tạo phép chiếu chứa thông tin ánh xạ ID/CAS. Câu `SELECT sku, variants` có thể chạy ở Query Workbench nhưng không nhất thiết ánh xạ được một `Product` hoàn chỉnh. Khi chỉ cần vài trường, nên thiết kế projection/DTO có cấu trúc tương ứng.

### API reactive có thay đổi cú pháp không?

Không. Một repository reactive dùng `ReactiveCouchbaseRepository<Product, String>` và trả về `Flux<Product>` vẫn có thể sử dụng cùng dạng `@Query` với `ANY` hoặc `EVERY`. Tính reactive thay đổi mô hình thực thi và truyền kết quả, không làm thay đổi ngữ nghĩa SQL++ hay loại bỏ nhu cầu về chỉ mục phù hợp.

## 9. Chỉ mục cho điều kiện trên mảng và object lồng nhau

Truy vấn SQL++ qua **Query Service** cần được tối ưu bằng chỉ mục thích hợp. Trường lồng nhau có thể dùng secondary index trên đường dẫn:

```sql
CREATE INDEX idx_products_connection
ON `catalog`.`commerce`.`products`(specs.connection.type);
```

Nhưng truy vấn `ANY` trên **các phần tử mảng** thường cần **array index** để tăng hiệu quả. Ví dụ index màu của từng biến thể:

```sql
CREATE INDEX idx_products_variant_color
ON `catalog`.`commerce`.`products`(
    DISTINCT ARRAY v.color
    FOR v IN variants
    END
);
```

Biểu thức `DISTINCT ARRAY v.color FOR v IN variants END` tạo các khóa chỉ mục trên **giá trị màu bên trong mảng**, thay vì chỉ dựa vào document như một giá trị nguyên khối. Câu SQL++ tương ứng:

```sql
EXPLAIN
SELECT p.sku
FROM `catalog`.`commerce`.`products` AS p
WHERE ANY v IN p.variants
      SATISFIES v.color = "white"
      END;
```

Chạy `EXPLAIN` để kiểm tra optimizer có dùng đúng chỉ mục hay không. **Có chỉ mục không bảo đảm mọi biểu thức `ANY` hay `EVERY` đều được tối ưu**; truy vấn còn phụ thuộc biểu thức `SATISFIES`, điều kiện kết hợp, thứ tự khóa index, độ chọn lọc, khả năng covering và thống kê dữ liệu.

Ví dụ trên chỉ lập chỉ mục `v.color`. Nếu nghiệp vụ còn lọc đồng thời `v.stock > 0`, việc tìm được màu qua index không tự chứng minh luôn điều kiện tồn kho. Một array index tổ hợp và cách khai báo điều kiện tương ứng có thể cần thiết; nên thiết kế dựa trên `EXPLAIN` và dữ liệu thật, thay vì tự mặc định chỉ mục trên màu cũng tối ưu mọi điều kiện về tồn kho.

### Độ mới của dữ liệu sau khi ghi

Khi Spring Data ghi document, Key/Value Service có thể đã xác nhận thành công trong khi Query/Index Service chưa cập nhật chỉ mục mới. Với scan consistency `NOT_BOUNDED`, truy vấn tìm kiếm theo `ANY` hoặc `EVERY` có thể tạm thời chưa thấy thay đổi vừa ghi. Cấu hình `REQUEST_PLUS` cho phép chờ chỉ mục cập nhật trước yêu cầu truy vấn nhưng thường tăng độ trễ.

Khi đã biết document ID, đọc Key/Value theo ID thường phù hợp hơn việc dùng SQL++ chỉ để tìm lại một document vừa lưu. **TTL** quyết định tuổi thọ document, **CAS** hỗ trợ phát hiện cập nhật đồng thời, **transactions** xử lý nhóm thao tác cần tính nguyên tử; chúng là những cơ chế bổ trợ, không làm thay đổi ý nghĩa của `ANY` và `EVERY`. `CouchbaseTemplate` là một API khác để xây dựng tầng truy cập dữ liệu; lựa chọn Repository hay Template không loại bỏ nhu cầu hiểu cú pháp JSON lồng nhau và chỉ mục.

## 10. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| `p.variants[0].color` bỏ sót biến thể trắng | Chỉ kiểm tra phần tử đầu tiên | Dùng `ANY` cho yêu cầu “có bất kỳ phần tử” |
| So sánh `p.tags = "wireless"` không tìm được nhãn | So sánh cả mảng với chuỗi | Dùng `ANY tag IN p.tags SATISFIES ... END` |
| Lọc ra KB-100 dù biến thể trắng hết hàng | Hai `ANY` riêng có thể xét hai biến thể khác nhau | Ghép `color` và `stock` trong cùng một `SATISFIES` |
| `EVERY` chọn cả sản phẩm không có biến thể | `EVERY` đúng trên mảng rỗng | Dùng `ANY AND EVERY` hoặc kết hợp kiểm tra độ dài mảng |
| Nhầm `variants: []` với thiếu `variants` | JSON phân biệt mảng rỗng và `MISSING` | Dùng `IS ARRAY`, `IS MISSING`, `ARRAY_LENGTH` khi cần |
| Truy vấn kho HCM đúng nhưng sai biến thể | Điều kiện kho không được ràng buộc theo biến thể đang xét | Lồng `ANY w IN v.warehouses` bên trong `ANY v IN p.variants` |
| `WHERE p.specs.connection.type = ...` bỏ qua document | Thuộc tính lồng có thể thiếu | Kiểm tra đường dẫn và trạng thái `MISSING`/`NULL` |
| `@Query` không trả về document mà Workbench tìm thấy | Entity discriminator hoặc collection mapping không khớp | Kiểm tra `#n1ql.filter`, scope, collection và dữ liệu được Spring Data lưu |
| Truy vấn `ANY` chậm dù collection có chỉ mục | Index thường chưa chứa khóa của phần tử mảng | Cân nhắc array index và kiểm tra `EXPLAIN` |
| Vừa cập nhật tồn kho nhưng truy vấn chưa thấy | Chỉ mục cập nhật bất đồng bộ | Cân nhắc scan consistency hoặc đọc KV theo ID |

## 11. Bài tập áp dụng và đáp án tham khảo

### Bài 1 — Tìm sản phẩm có biến thể trắng còn ít nhất 2 đơn vị

Yêu cầu: trả về mã sản phẩm; điều kiện màu và số lượng phải thuộc **cùng biến thể**.

```sql
SELECT p.sku
FROM `catalog`.`commerce`.`products` AS p
WHERE ANY v IN p.variants
      SATISFIES v.color = "white" AND v.stock >= 2
      END;
```

**Đáp án với dữ liệu mẫu:** KB-200. KB-100 có màu trắng nhưng `stock = 0`.

### Bài 2 — Tìm sản phẩm có tất cả biến thể còn hàng, không chấp nhận mảng rỗng

```sql
SELECT p.sku
FROM `catalog`.`commerce`.`products` AS p
WHERE p.variants IS ARRAY
  AND ARRAY_LENGTH(p.variants) > 0
  AND EVERY v IN p.variants
      SATISFIES v.stock > 0
      END;
```

**Đáp án:** KB-200. Nếu bỏ `ARRAY_LENGTH > 0`, MS-100 cũng thỏa `EVERY` vì `variants = []`.

### Bài 3 — Tìm sản phẩm có ít nhất một biến thể còn hàng tại kho HCM

```sql
SELECT p.sku
FROM `catalog`.`commerce`.`products` AS p
WHERE ANY v IN p.variants
      SATISFIES ANY w IN v.warehouses
                SATISFIES w.code = "HCM" AND w.qty > 0
                END
      END;
```

**Đáp án:** KB-100 và KB-200. Câu truy vấn phải duyệt qua `variants` trước khi duyệt `warehouses` của biến thể đó.

### Bài 4 — Chọn API trả về

Ứng dụng chỉ cần trả về mảng tên màu còn hàng để hiển thị trên trang sản phẩm. Chọn một trong ba cách: `ANY`, `ARRAY ... FOR`, `UNNEST`.

**Đáp án:** `ARRAY ... FOR ... WHEN ... END` phù hợp nhất để tạo **một mảng màu trong mỗi hàng sản phẩm**. `ANY` chỉ trả lời câu hỏi điều kiện; `UNNEST` tạo nhiều hàng kết quả.

### Câu hỏi tự kiểm tra

1. Vì sao hai `ANY` độc lập không bảo đảm hai điều kiện xảy ra trong cùng một phần tử? Vì mỗi `ANY` có biến và lần duyệt mảng riêng; chúng có thể đúng ở hai phần tử khác nhau.
2. Khi nào `EVERY` TRUE dù không có phần tử nào đạt điều kiện? Khi đầu vào là **mảng rỗng**; không có phần tử nào phản ví dụ.
3. Khác biệt giữa `variants: []` và không có trường `variants` là gì? Trường hợp đầu là mảng tồn tại nhưng rỗng, trường hợp sau là giá trị `MISSING`.
4. Vì sao `#n1ql.selectEntity` hữu ích với `List<Product>`? Nó để Spring Data tạo phép chiếu và metadata cần cho ánh xạ entity đầy đủ.
5. Vì sao index trên `category` có thể chưa đủ cho truy vấn `ANY` trên `variants.color`? Vì đường truy cập cần giá trị bên trong mảng; nên cân nhắc array index phù hợp và xác minh qua `EXPLAIN`.

## Tài liệu tham khảo chính thức

- [Couchbase SQL++ for Query — Collection Operators](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/collectionops.html): `ANY`, `EVERY` và `ANY AND EVERY`.
- [Couchbase SQL++ for Query — Expressions](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/expressions.html): truy cập giá trị JSON, mảng và biểu thức.
- [Couchbase SQL++ for Query — Array Indexing](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/indexing-arrays.html): chỉ mục cho phần tử mảng.
- [Couchbase SQL++ for Query — UNNEST](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/unnest.html): đưa phần tử mảng thành dòng kết quả.
- [Spring Data Couchbase — Repositories](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): `@Query`, biểu thức `#n1ql`, tham số và ánh xạ entity.

**Ghi nhớ:** đối với JSON lồng nhau, hãy chọn đúng cấp dữ liệu trước khi xây dựng điều kiện. `ANY` kiểm tra sự **tồn tại**, `EVERY` kiểm tra **tất cả**, và `ANY AND EVERY` thêm ràng buộc **mảng không rỗng**. Khi đưa truy vấn vào Spring Data Couchbase, luôn cân nhắc tham số hóa, ánh xạ entity, điều kiện kiểu document, chỉ mục mảng và độ mới của dữ liệu.

# Chỉ mục trên mảng và truy vấn dữ liệu lồng nhau trong Spring Data Couchbase

Một document Couchbase thường chứa nhiều thông tin liên quan trong cùng một cấu trúc JSON. Ví dụ, đơn hàng có danh sách `items`, danh sách nhãn `tags`, địa chỉ giao hàng `shipping.address` và nhiều kiện hàng `packages`. Cách lưu này giúp đọc toàn bộ đơn hàng thuận tiện, nhưng phát sinh câu hỏi: **Làm sao tìm nhanh tất cả đơn hàng có một SKU nằm bên trong mảng, hoặc lọc theo thuộc tính của một phần tử trong mảng?**

**Array index** là một dạng secondary index của Couchbase được thiết kế để đánh chỉ mục trên phần tử mảng. Nó khác index trên đường dẫn JSON lồng nhau thông thường: điều kiện truy vấn cần thể hiện rõ phép tìm phần tử, và biểu thức của index cần tương thích với biểu thức truy vấn. Trong **Spring Data Couchbase**, các truy vấn như vậy thường được viết bằng SQL++ qua `@Query` hoặc API truy vấn phù hợp của `CouchbaseTemplate`.

Bài thuộc chương **Chỉ mục** của module **SPRING_DATA_COUCHBASE**. Bên cạnh array index, nội dung liên hệ với document mapping, repository, bucket/scope/collection, các lựa chọn API reactive, chi phí vận hành, TTL, CAS, giao dịch và tính nhất quán của SQL++.

## 1. Mục tiêu học tập

Sau khi hoàn thành, bạn có thể:

1. Phân biệt index trên **trường object lồng nhau** với index trên **phần tử của mảng**.
2. Viết SQL++ dùng `ANY ... IN ... SATISFIES ... END` và `UNNEST` để truy vấn dữ liệu mảng, hiểu sự khác biệt về số hàng trả về.
3. Tạo array index bằng `DISTINCT ARRAY` và `ALL ARRAY`, biết khi nào cần composite array index hoặc khóa bổ sung.
4. Hiểu điều kiện **cùng một phần tử thỏa nhiều predicate**, vấn đề mảng lồng nhiều cấp, và ảnh hưởng của `NULL`/`MISSING`/mảng rỗng.
5. Liên kết truy vấn mảng với `@Query`/`CouchbaseTemplate`, kiểm tra kế hoạch bằng `EXPLAIN` và chọn index theo workload.

## 2. Mô hình dữ liệu minh họa

Giả sử hệ thống thương mại điện tử lưu đơn hàng trong bucket `commerce`, scope `sales`, collection `orders`. Document ID `order::1001` có cấu trúc:

```json
{
  "_class": "salesOrder",
  "tenantId": "TENANT-A",
  "customerId": "C-42",
  "status": "PAID",
  "createdAt": "2026-11-20T08:00:00Z",
  "deleted": false,
  "tags": ["priority", "gift"],
  "shipping": {
    "address": {
      "city": "Ha Noi",
      "district": "Ba Dinh"
    },
    "method": "EXPRESS"
  },
  "items": [
    { "sku": "SKU-42", "quantity": 2, "price": 350000 },
    { "sku": "SKU-18", "quantity": 1, "price": 800000 }
  ],
  "packages": [
    {
      "packageId": "PKG-1",
      "lines": [
        { "sku": "SKU-42", "quantity": 1 },
        { "sku": "SKU-18", "quantity": 1 }
      ]
    }
  ]
}
```

Trong ví dụ này, `_class` minh họa một discriminator cho ánh xạ entity; giá trị thực có thể là tên lớp đầy đủ, `@TypeAlias` hoặc trường kiểu khác tùy cấu hình. `createdAt` là chuỗi thời gian ISO-8601 UTC thống nhất định dạng để có thể so sánh theo chuỗi; với `Instant` trong Java, luôn kiểm tra định dạng mà bộ chuyển đổi thực sự lưu.

Có ba dạng dữ liệu cần truy vấn:

| Kiểu JSON | Ví dụ | Cách truy vấn đặc trưng |
| --- | --- | --- |
| Thuộc tính object lồng nhau | `shipping.address.city` | Truy cập trực tiếp bằng đường dẫn trường |
| Mảng scalar | `tags: ["priority", "gift"]` | `ANY tag IN ... SATISFIES ... END` |
| Mảng object | `items: [{sku, quantity}, ...]` | `ANY item IN ... SATISFIES item.sku = ... END` |
| Mảng nhiều cấp | `packages[*].lines[*].sku` | Lồng `ANY` hoặc `UNNEST` nhiều tầng, thiết kế index thích hợp |

## 3. Object lồng nhau: có thể dùng secondary index thông thường

Điều kiện tìm đơn theo thành phố giao hàng không cần một array index nếu `shipping.address` là một **object**, không phải mảng:

```sql
SELECT META(o).id AS orderId, o.customerId, o.shipping.address.city AS city
FROM `commerce`.`sales`.`orders` AS o
WHERE o.shipping.address.city = "Ha Noi";
```

Chỉ mục thứ cấp tương ứng:

```sql
CREATE INDEX ix_orders_shipping_city
ON `commerce`.`sales`.`orders`(
    `shipping`.`address`.`city`
);
```

Đây là index trên **đường dẫn của một field JSON**, không phải index của các phần tử một mảng. Nếu yêu cầu luôn giới hạn theo tenant, có thể cân nhắc:

```sql
CREATE INDEX ix_orders_tenant_shipping_city
ON `commerce`.`sales`.`orders`(
    `tenantId`,
    `shipping`.`address`.`city`
);
```

Chọn thứ tự khóa theo mẫu truy vấn thực: `tenantId = ? AND shipping.address.city = ?` thường tận dụng hai khóa đầu. Với truy vấn chỉ lọc thành phố toàn hệ thống, index có `tenantId` dẫn đầu chưa chắc hiệu quả bằng index có thành phố đứng đầu.

**Điểm phân biệt:** Một đường dẫn như `items.sku` không tự động biểu thị “SKU của bất kỳ phần tử nào” khi `items` là array. Để diễn tả phép tìm trong các phần tử, cần cú pháp SQL++ dành cho mảng và cân nhắc array index.

## 4. Truy vấn mảng bằng `ANY ... SATISFIES`

### 4.1. Mảng scalar: tìm nhãn trong `tags`

Yêu cầu: tìm các đơn có tag `priority`.

```sql
SELECT META(o).id AS orderId, o.tags
FROM `commerce`.`sales`.`orders` AS o
WHERE ANY tag IN o.tags
      SATISFIES tag = "priority"
      END;
```

`ANY` diễn tả: **tồn tại ít nhất một phần tử** trong mảng làm điều kiện đúng. Với `tags = ["priority", "gift"]`, kết quả là đúng; với mảng `["gift"]`, không có phần tử thỏa.

### 4.2. Mảng object: tìm đơn chứa SKU

Yêu cầu: tìm các đơn có ít nhất một dòng hàng mang SKU `SKU-42`.

```sql
SELECT META(o).id AS orderId, o.tenantId, o.status
FROM `commerce`.`sales`.`orders` AS o
WHERE ANY item IN o.items
      SATISFIES item.sku = "SKU-42"
      END;
```

Đây là truy vấn theo thuộc tính của **từng phần tử mảng**, nên một array index trên `items[*].sku` là ứng viên tự nhiên. Query Service sẽ quyết định có sử dụng index hay không dựa trên biểu thức, predicate và kế hoạch.

### 4.3. Nhiều điều kiện phải đúng trên **cùng phần tử**

Yêu cầu: đơn hàng có **một dòng** vừa là SKU `SKU-42`, vừa có `quantity >= 2`. Hãy đặt cả hai điều kiện trong **cùng một `SATISFIES`**:

```sql
SELECT META(o).id AS orderId
FROM `commerce`.`sales`.`orders` AS o
WHERE ANY item IN o.items
      SATISFIES item.sku = "SKU-42"
            AND item.quantity >= 2
      END;
```

So sánh với điều kiện sau:

```sql
WHERE ANY item IN o.items SATISFIES item.sku = "SKU-42" END
  AND ANY item IN o.items SATISFIES item.quantity >= 2 END
```

Hai biểu thức `ANY` tách rời **có thể được thỏa bởi hai phần tử khác nhau**. Chẳng hạn, một item là `SKU-42` có `quantity = 1`, một item khác có `quantity = 5`: điều kiện tách rời vẫn đúng nhưng không đáp ứng yêu cầu “cùng một dòng hàng”. Đây là sai sót logic dễ xảy ra khi chuyển điều kiện Java sang SQL++.

### 4.4. `EVERY` và `ANY AND EVERY`

SQL++ cũng có những phép lượng từ khác:

- `EVERY item IN o.items SATISFIES item.quantity > 0 END`: mọi phần tử đều thỏa. Với mảng **rỗng**, `EVERY` là đúng theo logic “mọi phần tử của tập rỗng”.
- `ANY AND EVERY item IN o.items SATISFIES item.quantity > 0 END`: mảng phải có ít nhất một phần tử và mọi phần tử đều thỏa; với mảng rỗng, biểu thức không đúng.
- `ANY`: cần ít nhất một phần tử thỏa nên không thể đúng khi mảng rỗng.

Các trường hợp field `items` bị thiếu, có `NULL`, hoặc phần tử mang kiểu không mong đợi phải được xem xét riêng vì SQL++ phân biệt `MISSING`, `NULL` và Boolean. Đừng tự giả định mọi điều kiện trên một mảng không tồn tại đều trả `FALSE` trong mọi biểu thức và ngữ cảnh.

## 5. Tạo array index trên mảng scalar và mảng object

### 5.1. Cú pháp `DISTINCT ARRAY`

Index trên các nhãn đơn hàng:

```sql
CREATE INDEX ix_orders_tags
ON `commerce`.`sales`.`orders`(
    DISTINCT ARRAY tag FOR tag IN tags END
);
```

Index trên SKU của từng dòng hàng:

```sql
CREATE INDEX ix_orders_items_sku
ON `commerce`.`sales`.`orders`(
    DISTINCT ARRAY item.sku FOR item IN items END
);
```

Đối chiếu với các truy vấn:

```sql
-- Index tags
SELECT META(o).id AS orderId
FROM `commerce`.`sales`.`orders` AS o
WHERE ANY tag IN o.tags SATISFIES tag = "priority" END;

-- Index items.sku
SELECT META(o).id AS orderId
FROM `commerce`.`sales`.`orders` AS o
WHERE ANY item IN o.items SATISFIES item.sku = "SKU-42" END;
```

Phần `ARRAY ... FOR ... IN ... END` của định nghĩa index mô tả **biểu thức được trích từ các phần tử mảng**. Predicate của truy vấn cần có cấu trúc và biểu thức tương thích thì optimizer mới có cơ sở biến điều kiện `ANY` thành một index scan hiệu quả.

`DISTINCT` loại các giá trị trùng lặp được trích từ **cùng một document** khi xây dựng các entry của array key. Ví dụ một đơn có SKU `SKU-42` ở hai dòng thì index kiểu `DISTINCT ARRAY item.sku` không cần giữ hai entry cùng giá trị cho chính document đó. Điều này phù hợp truy vấn kiểu “đơn nào có SKU này?” khi kết quả mong muốn là một document đơn hàng.

> **Quan trọng:** `DISTINCT` trong array index khác với `SELECT DISTINCT`. Một cái quyết định cách lập chỉ mục các phần tử, cái kia quyết định loại hàng trùng trong kết quả truy vấn.

### 5.2. `ALL ARRAY` và việc giữ lại phần tử lặp

Một dạng khác:

```sql
CREATE INDEX ix_orders_items_sku_all
ON `commerce`.`sales`.`orders`(
    ALL ARRAY item.sku FOR item IN items END
);
```

`ALL` giữ thông tin về các lần xuất hiện của phần tử được lập chỉ mục, còn `DISTINCT` loại các giá trị lặp trong phạm vi document. `ALL` có thể phục vụ những truy vấn cần đi qua **từng phần tử**, đặc biệt những mẫu `UNNEST` tương thích; đổi lại index có thể nhiều entry hơn khi các mảng chứa giá trị lặp.

Không nên tạo cả hai index chỉ vì cú pháp có sẵn. Hãy xác định ứng dụng cần tìm document theo điều kiện tồn tại (`ANY`), hay cần kết quả ở cấp phần tử (`UNNEST`), rồi dùng `EXPLAIN` và metrics để chọn cấu trúc phù hợp.

### 5.3. Vì sao index thường theo SKU thay vì toàn bộ item JSON?

Một phần tử item có nhiều trường: `sku`, `quantity`, `price`, thậm chí metadata khác. Khi truy vấn chủ yếu hỏi theo `sku`, index trên `item.sku` giúp các entry nhỏ hơn và tập trung vào predicate. Việc lập chỉ mục nguyên object hoặc mọi trường có thể tăng dung lượng mà không mang lại lợi ích tương xứng.

Nếu cần lọc theo `quantity`, giá `price` hoặc một tổ hợp điều kiện, hãy xem phần composite array index tiếp theo, đồng thời đo độ chọn lọc của từng thuộc tính.

## 6. Composite array index: lọc theo tenant và phần tử mảng

Hệ thống đa tenant thường có mẫu truy vấn:

```sql
SELECT META(o).id AS orderId, o.tenantId
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = "TENANT-A"
  AND ANY item IN o.items
      SATISFIES item.sku = "SKU-42"
      END;
```

Thay vì chỉ lập chỉ mục `sku` trên toàn bộ đơn hàng, có thể kết hợp một **khóa scalar dẫn đầu** với array key:

```sql
CREATE INDEX ix_orders_tenant_item_sku
ON `commerce`.`sales`.`orders`(
    `tenantId`,
    DISTINCT ARRAY item.sku FOR item IN items END
);
```

Về ý tưởng, hệ thống có thể thu hẹp theo tenant, rồi theo các giá trị SKU bên trong mỗi document. Quy tắc thứ tự khóa vẫn quan trọng: nếu index đặt `tenantId` đầu tiên, truy vấn không lọc tenant có thể khó tận dụng hiệu quả toàn bộ cấu trúc này.

### 6.1. Điều kiện cùng phần tử có nhiều field

Nếu có hai điều kiện trên một item:

```sql
SELECT META(o).id AS orderId
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = "TENANT-A"
  AND ANY item IN o.items
      SATISFIES item.sku = "SKU-42"
            AND item.quantity >= 2
      END;
```

Index chỉ trích `item.sku` vẫn có thể giảm tập document ứng viên theo SKU; sau đó Query Service có thể phải đọc document và kiểm tra `quantity`. Nếu truy vấn theo cả hai thuộc tính rất thường xuyên, những phiên bản Couchbase hỗ trợ **flattened array index** có thể sử dụng `FLATTEN_KEYS` để lập chỉ mục nhiều trường của cùng phần tử:

```sql
CREATE INDEX ix_orders_tenant_sku_qty
ON `commerce`.`sales`.`orders`(
    `tenantId`,
    ALL ARRAY FLATTEN_KEYS(item.sku, item.quantity)
        FOR item IN items END
);
```

Với dạng này, các khóa được trích từ cùng item, giúp optimizer có thêm cơ hội áp dụng đồng thời điều kiện theo `sku` và `quantity`. Đây là kỹ thuật chuyên biệt: hãy xác nhận tính năng/cú pháp hỗ trợ trên **phiên bản Couchbase đang sử dụng**, kiểm tra `EXPLAIN` và quan sát chi phí index trước khi áp dụng.

Không được thay hai điều kiện cùng phần tử bằng hai index riêng rồi mặc định kết quả của phép nối điều kiện vẫn có ngữ nghĩa “cùng item”. Ngữ nghĩa của `ANY` phải đúng trước khi tối ưu bằng index.

### 6.2. Kết hợp điều kiện loại entity hoặc trạng thái

Nếu collection chứa nhiều entity hoặc có soft delete, partial array index có thể tập trung vào các đơn hàng hợp lệ:

```sql
CREATE INDEX ix_live_orders_tenant_item_sku
ON `commerce`.`sales`.`orders`(
    `tenantId`,
    DISTINCT ARRAY item.sku FOR item IN items END
)
WHERE `_class` = "salesOrder"
  AND `deleted` = FALSE;
```

Truy vấn muốn dùng index này phải có điều kiện **hàm ý** predicate:

```sql
SELECT META(o).id AS orderId
FROM `commerce`.`sales`.`orders` AS o
WHERE o._class = "salesOrder"
  AND o.deleted = FALSE
  AND o.tenantId = "TENANT-A"
  AND ANY item IN o.items
      SATISFIES item.sku = "SKU-42"
      END;
```

Nếu truy vấn bỏ `deleted = FALSE` vì cần cả đơn đã xóa mềm, index này **không chứa đủ dữ liệu**. Nếu Spring Data thêm điều kiện `_class` với giá trị khác `"salesOrder"` do cấu hình mapping, optimizer có thể không dùng index mong đợi. Phải đối chiếu document thật và truy vấn phát sinh.

## 7. `UNNEST`: một document có thể tạo nhiều hàng kết quả

`ANY` là phép kiểm tra “document có tồn tại phần tử thỏa điều kiện hay không”. Nếu ứng dụng cần **trả ra chính các dòng hàng**, `UNNEST` thường phù hợp hơn.

Ví dụ:

```sql
SELECT META(o).id AS orderId,
       i.sku AS sku,
       i.quantity AS quantity
FROM `commerce`.`sales`.`orders` AS o
UNNEST o.items AS i
WHERE o.tenantId = "TENANT-A"
  AND i.sku = "SKU-42";
```

Giả sử một đơn có **hai dòng cùng SKU**: kết quả `UNNEST` có thể có **hai hàng** mang cùng `orderId`, mỗi hàng ứng với một phần tử `items`. Trong khi đó, một truy vấn `WHERE ANY ... END` chọn document đơn hàng thì **không nhân bản document** chỉ vì có nhiều item thỏa.

| Đặc điểm | `ANY` | `UNNEST` |
| --- | --- | --- |
| Mục đích | Kiểm tra có phần tử thỏa điều kiện | Tạo một hàng ngữ cảnh truy vấn cho từng phần tử |
| Số hàng khi một document có hai item khớp | Thường một hàng document nếu `SELECT` trên parent | Có thể hai hàng |
| Khi thường dùng | Tìm đơn hàng có SKU | Liệt kê dòng hàng, báo cáo hoặc tổng hợp theo item |
| Độ phức tạp | Đơn giản nếu chỉ cần parent document | Cần xử lý khả năng nhân hàng, `DISTINCT`/`GROUP BY` khi cần |
| Khả năng dùng array index | Cần expression `ANY` tương thích với index | Cần index và kế hoạch thích hợp; thường cân nhắc `ALL ARRAY` |

Trong Couchbase, `UNNEST` có thể tận dụng array index ở những trường hợp đủ điều kiện, nhưng **không phải mọi index `DISTINCT ARRAY` đều tối ưu mọi truy vấn `UNNEST`**. Sử dụng `EXPLAIN` cho SQL++ thực tế, đặc biệt nếu truy vấn có nhiều `UNNEST`, tổng hợp hoặc phép nối.

### 7.1. `UNNEST` và array rỗng

Với phép `UNNEST` thông thường, document có `items = []` sẽ không sinh hàng kết quả từ mảng đó. Khi muốn giữ cả document không có item, SQL++ có biến thể outer unnest:

```sql
SELECT META(o).id AS orderId, i.sku AS sku
FROM `commerce`.`sales`.`orders` AS o
LEFT OUTER UNNEST o.items AS i
WHERE o.tenantId = "TENANT-A";
```

Điều kiện đặt sau `UNNEST` có thể làm thay đổi hiệu quả của phép outer join; nếu thêm `WHERE i.sku = ...`, các hàng không có item có thể bị loại. Cần viết đúng ngữ nghĩa mong muốn, không chỉ tối ưu index.

### 7.2. Phân trang trên dòng hàng khác phân trang trên đơn hàng

`LIMIT 20` sau `UNNEST` thường giới hạn **20 hàng đã unnested**, không mặc nhiên là 20 đơn hàng. Nếu sản phẩm yêu cầu “20 đơn mới nhất có chứa SKU”, nên tìm tập order phù hợp bằng `ANY` rồi phân trang theo order. Nếu sản phẩm yêu cầu “20 dòng hàng”, `UNNEST` và phân trang ở cấp item có thể hợp lý.

Đối với phân trang ổn định, cần `ORDER BY` xác định (thường thêm khóa phụ khi trùng thời gian) và chọn index tương thích; `OFFSET` lớn có thể tốn chi phí nên có thể cân nhắc keyset pagination khi workload phù hợp.

## 8. Mảng lồng nhiều cấp: `ANY` lồng và nhiều lần `UNNEST`

Trong document minh họa, `packages` là mảng các kiện hàng và mỗi kiện chứa mảng `lines`. Bài toán: tìm đơn có SKU `SKU-42` trong bất kỳ kiện nào.

### 8.1. Truy vấn tồn tại ở hai cấp

```sql
SELECT META(o).id AS orderId
FROM `commerce`.`sales`.`orders` AS o
WHERE ANY pkg IN o.packages
      SATISFIES ANY line IN pkg.lines
                SATISFIES line.sku = "SKU-42"
                END
      END;
```

Mỗi `ANY ... END` có **phạm vi biến** của chính nó. `pkg` là một phần tử của `packages`; `line` là một phần tử của `pkg.lines`. Việc viết thiếu tầng hoặc dùng nhầm biến có thể thay đổi hoàn toàn ý nghĩa truy vấn.

Nếu chỉ cần tìm theo `items[*].sku` ở cấp một, nên truy vấn `items` trực tiếp; không có lý do buộc phải đi qua `packages` nếu dữ liệu nghiệp vụ không yêu cầu.

### 8.2. Truy vấn trả các dòng ở hai cấp

```sql
SELECT META(o).id AS orderId,
       pkg.packageId AS packageId,
       line.sku AS sku,
       line.quantity AS quantity
FROM `commerce`.`sales`.`orders` AS o
UNNEST o.packages AS pkg
UNNEST pkg.lines AS line
WHERE o.tenantId = "TENANT-A"
  AND line.sku = "SKU-42";
```

Một đơn có nhiều kiện, mỗi kiện có nhiều dòng, nên số hàng có thể tăng nhanh. Đây là hiện tượng **mở rộng cardinality**; nếu không đặt predicate phù hợp, Query Service phải xử lý nhiều phần tử và tốn chi phí memory/CPU.

### 8.3. Thiết kế index nhiều cấp

Array index một cấp như `DISTINCT ARRAY item.sku FOR item IN items END` **không mặc nhiên áp dụng** cho cấu trúc `packages[*].lines[*].sku`. Đối với hai tầng mảng, Couchbase có các biểu thức array lồng nhau và những khả năng lập chỉ mục chuyên biệt; cú pháp và khả năng optimizer sử dụng phụ thuộc cấu trúc dữ liệu, phiên bản và dạng `ANY`/`UNNEST`.

Quy trình an toàn là:

1. Viết đúng truy vấn SQL++ trước; kiểm tra kết quả với cả document có mảng rỗng, thiếu mảng và nhiều phần tử khớp.
2. Xác định trường nào cần index và cấp mảng nào chứa trường đó.
3. Tạo index array lồng phù hợp với phiên bản Couchbase; **không** áp dụng máy móc index trên một đường dẫn object như `packages.lines.sku`.
4. Dùng `EXPLAIN` xác nhận phép quét có dùng index và những điều kiện có được đẩy xuống hay không.
5. Nếu truy vấn nhiều cấp là trường hợp cực nóng, cân nhắc thiết kế lại document, tạo trường tìm kiếm đã chuẩn hóa hoặc tách collection đọc riêng, nhưng phải bảo đảm đồng bộ dữ liệu đúng nghiệp vụ.

Một trường chuẩn hóa bổ trợ như `allSkus` chứa toàn bộ SKU được trích từ `packages[*].lines[*]` có thể giúp các truy vấn tìm tồn tại đơn giản hơn:

```json
{
  "packages": [
    {
      "lines": [
        { "sku": "SKU-42", "quantity": 1 },
        { "sku": "SKU-18", "quantity": 1 }
      ]
    }
  ],
  "allSkus": ["SKU-42", "SKU-18"]
}
```

Khi đó có thể dùng array index trên `allSkus` và `ANY` tương ứng. **Đổi lại**, ứng dụng phải cập nhật `allSkus` cùng lúc mỗi khi `packages` thay đổi để không xuất hiện dữ liệu tìm kiếm sai lệch; cần cân nhắc cơ chế ghi nguyên tử, CAS hoặc giao dịch theo phạm vi thay đổi.

## 9. Spring Data Couchbase: mapping và truy vấn mảng

### 9.1. Mapping document có mảng object

Entity minh họa, lược bỏ constructor, getter và setter:

```java
import java.time.Instant;
import java.util.List;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.TypeAlias;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;
import org.springframework.data.couchbase.core.mapping.Collection;

@Document
@TypeAlias("salesOrder")
@Scope("sales")
@Collection("orders")
public class SalesOrder {
    @Id
    private String id;
    private String tenantId;
    private String customerId;
    private String status;
    private Instant createdAt;
    private boolean deleted;
    private List<String> tags;
    private List<OrderItem> items;

    // Constructor, getter và setter được lược bỏ.
}

public class OrderItem {
    private String sku;
    private int quantity;
    private long price;

    // Constructor, getter và setter được lược bỏ.
}
```

Nếu đặt cả hai class trong cùng một file Java thực, phải điều chỉnh `public`/cấu trúc file theo quy tắc Java; các class trên chỉ là phần trích minh họa cho mapping. Bucket `commerce` được cấu hình trong ứng dụng; annotation xác định scope/collection theo mapping đang dùng.

Không cần khai báo một annotation “array index” trên `List<OrderItem>` để tự động có GSI mong muốn. Index phục vụ SQL++ cần được tạo và quản lý ở Couchbase theo chính sách môi trường.

### 9.2. Dùng `@Query` cho `ANY`

Ví dụ repository tìm đơn thuộc một tenant và có SKU trong mảng:

```java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;
import org.springframework.data.couchbase.repository.Query;

public interface SalesOrderRepository
        extends CouchbaseRepository<SalesOrder, String> {

    @Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} " +
           "AND tenantId = $1 " +
           "AND ANY item IN items SATISFIES item.sku = $2 END")
    List<SalesOrder> findContainingSku(String tenantId, String sku);
}
```

`#{#n1ql.selectEntity}` và `#{#n1ql.filter}` là các biểu thức hỗ trợ mapping entity của Spring Data Couchbase. Biểu thức filter có thể bổ sung điều kiện theo loại entity, ví dụ `_class`, và do đó ảnh hưởng đến việc partial index có tương thích hay không. Giá trị `$1`, `$2` là tham số; không nối trực tiếp SKU từ request vào SQL++.

Đối với truy vấn mảng có điều kiện phức tạp, `@Query` cho phép diễn tả chính xác `ANY` hoặc `UNNEST`. Không nên suy đoán rằng tên phương thức derived query như `findByItemsSku(...)` luôn tạo đúng cú pháp và ngữ nghĩa mong muốn trong mọi phiên bản Spring Data.

### 9.3. `CouchbaseTemplate`

`CouchbaseTemplate` hữu ích khi lớp truy cập dữ liệu cần xây dựng điều kiện linh hoạt, projection hoặc phân trang mà repository method cố định không đáp ứng. Nếu template chạy một truy vấn SQL++ có `ANY`, optimizer vẫn dựa trên cùng các array index của Query Service.

Một câu SQL++ có thể dùng làm tiêu chuẩn kiểm tra:

```sql
SELECT META(o).id AS orderId, o.tenantId, o.status
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = $tenantId
  AND ANY item IN o.items
      SATISFIES item.sku = $sku
      END;
```

Đây là mẫu query để xem hành vi của index. Cách gọi API `CouchbaseTemplate` và cách mapping projection phụ thuộc phiên bản Spring Data Couchbase; không được coi `SELECT` minh họa này là phương thức Java hoàn chỉnh.

### 9.4. Reactive API không thay đổi nhu cầu index

`ReactiveCouchbaseRepository` và các API reactive có thể trả `Flux`/`Mono`, giúp ứng dụng xử lý I/O không đồng bộ và backpressure. Tuy nhiên, nếu Query Service phải quét quá nhiều document hoặc mở rộng mảng bằng `UNNEST` rồi lọc sau, reactive **không loại bỏ** công việc đó.

Đầu tiên cần tối ưu predicate, array index, `SELECT`, `LIMIT` và chiến lược phân trang; sau đó mới đo hiệu quả của reactive trong các tình huống đồng thời cao.

## 10. Dùng `EXPLAIN` để xác nhận array index thực sự được chọn

Đối với truy vấn tìm đơn theo SKU và tenant:

```sql
EXPLAIN
SELECT META(o).id AS orderId, o.tenantId
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = "TENANT-A"
  AND ANY item IN o.items
      SATISFIES item.sku = "SKU-42"
      END;
```

Nếu đã tạo `ix_orders_tenant_item_sku`, hãy tìm trong kế hoạch:

| Dấu hiệu | Câu hỏi |
| --- | --- |
| `IndexScan` hoặc `IndexScan3` | Có chọn index `ix_orders_tenant_item_sku` không? |
| `spans`/điều kiện quét | Index có giới hạn theo `tenantId` và giá trị `item.sku` không? |
| `Filter` | Bao nhiêu predicate còn phải kiểm tra sau khi scan? |
| `Fetch` | Có cần đọc JSON gốc để xác minh điều kiện hay trả đủ dữ liệu không? |
| `Order` | Query có phải sắp xếp bổ sung không? |
| `Distinct`/`Group` | Với `UNNEST` hoặc tập item lặp, kết quả có cần khử trùng/tổng hợp không? |
| `Limit` | Phân trang áp dụng ở cấp document hay cấp dòng sau `UNNEST`? |

Tên operator phụ thuộc phiên bản Couchbase. Không kết luận “array index hoạt động tốt” chỉ vì thấy `IndexScan`; còn phải xem **phạm vi scan, số entry đọc và chi phí `Fetch`**.

Kiểm tra thông tin index:

```sql
SELECT name, state, index_key, condition
FROM system:indexes
WHERE bucket_id = "commerce"
  AND scope_id = "sales"
  AND keyspace_id = "orders";
```

Index phải được xây dựng và ở trạng thái dùng được (thường là `online`) trước khi có thể kỳ vọng optimizer sử dụng. Sau khi `CREATE INDEX`, hãy đợi việc build và cập nhật hoàn tất theo cơ chế triển khai.

### 10.1. Khi index không được chọn

Kiểm tra tuần tự:

1. Câu SQL++ thực từ ứng dụng có **đúng đường dẫn và biểu thức mảng** như index không? Ví dụ `items`, `item.sku` và cú pháp `ANY`.
2. Query đang tìm document bằng `ANY` hay phát sinh hàng bằng `UNNEST`? Index hiện tại là `DISTINCT ARRAY` hay `ALL ARRAY`?
3. Có bỏ qua khóa dẫn đầu của composite index như `tenantId` không?
4. Partial index có điều kiện `_class`, `deleted` hoặc `status` không? Query có hàm ý đầy đủ predicate đó không?
5. Kiểu dữ liệu thực tế có thống nhất? `item.sku` có phải string trong mọi document, hay tồn tại `NULL`/`MISSING`?
6. Index đã `online` chưa? Optimizer có lựa chọn index khác được đánh giá ít tốn kém hơn không?

Hãy đo Query Profile và metrics với dữ liệu đại diện: số entry index được quét, số document cần fetch, thời gian xử lý, tài nguyên Index Service và độ trễ khi trả kết quả. Một tập chỉ vài document có thể che giấu vấn đề mở rộng mảng trên collection lớn.

## 11. `NULL`, `MISSING`, mảng rỗng và dữ liệu không đồng nhất

Trong dữ liệu JSON thực tế có thể gặp:

```json
{ "items": [] }
```

```json
{ "items": null }
```

```json
{ "items": [{ "quantity": 2 }] }
```

```json
{ "items": [{ "sku": null, "quantity": 2 }] }
```

Và document hoàn toàn **không có field `items`**. Những trường hợp này khác nhau về mặt ngữ nghĩa; array index trên `item.sku` cũng không nên được coi là chỉ mục tổng quát để tìm mọi document thiếu `items`, thiếu `sku` hoặc có kiểu dữ liệu sai.

Một truy vấn chọn document có ít nhất một SKU cụ thể:

```sql
WHERE ANY item IN o.items SATISFIES item.sku = "SKU-42" END
```

không tương đương với truy vấn tìm document không có mảng, có mảng rỗng hoặc thiếu `sku`. Nếu sản phẩm cần báo cáo lỗi dữ liệu “đơn không có mặt hàng”, hãy thiết kế truy vấn và index phục vụ **nhóm báo cáo dữ liệu lỗi** riêng, thay vì kỳ vọng array index tìm SKU cũng tối ưu các trường hợp đó.

**Khuyến nghị mapping:** Chuẩn hóa danh sách `items` về một cấu trúc nhất quán (mảng object với `sku` và `quantity` có kiểu xác định); xác định rõ việc `items = []` có hợp lệ trong nghiệp vụ hay không. Validation ở tầng ứng dụng giúp tránh các truy vấn có quá nhiều nhánh xử lý dữ liệu bất thường.

## 12. Chi phí cập nhật, TTL, CAS, giao dịch và scan consistency

### 12.1. Mỗi phần tử có thể tạo thêm entry index

Với array index, một document có 50 dòng hàng có thể cần nhiều entry hơn document chỉ có một dòng. Khi số lượng phần tử trong mảng lớn, tổng số index entry và chi phí duy trì có thể tăng đáng kể. Chênh lệch giữa `DISTINCT` và `ALL` cũng thể hiện rõ khi nhiều phần tử trong cùng document có giá trị lặp.

Khi ứng dụng thêm, sửa hoặc xóa phần tử `items`, Couchbase phải cập nhật các entry index chịu ảnh hưởng. Không nên tạo hàng loạt index trên mọi thuộc tính phần tử chỉ vì các trường tồn tại trong JSON. Hãy ưu tiên mẫu truy vấn nóng và đo lợi ích/chi phí trên workload thật.

### 12.2. Ghi cập nhật mảng: nguy cơ ghi đè đồng thời

Giả sử hai request cùng đọc một đơn hàng rồi cùng sửa `items`. Nếu không kiểm soát cạnh tranh, một bản ghi mới có thể ghi đè thay đổi của request khác. **CAS** là một cơ chế kiểm tra phiên bản document để phát hiện xung đột và hỗ trợ retry có kiểm soát. Nếu thay đổi liên quan nhiều document/collection, đánh giá giao dịch phù hợp thay vì dựa vào array index.

Index giúp **đọc/tìm**, không giải quyết xung đột ghi vào mảng. Nếu ứng dụng duy trì thêm trường phụ như `allSkus`, cần cập nhật nó đồng bộ với mảng nguồn để bảo đảm dữ liệu tìm kiếm nhất quán về nội dung.

### 12.3. TTL và index

Document hết hạn theo TTL sẽ không còn là bản ghi hợp lệ cho các truy vấn; các index liên quan cần phản ánh việc loại bỏ đó. Tuy nhiên TTL không phải một array index và không giúp truy vấn `ANY` tự nhanh hơn. Nếu nghiệp vụ đòi hỏi giữ dữ liệu theo thời gian, hãy phối hợp TTL với chỉ mục theo điều kiện/trường thời gian phù hợp.

### 12.4. SQL++ có thể chưa thấy mutation mới ngay lập tức

Các GSI được duy trì bất đồng bộ so với thao tác KV. Sau khi `save(...)` hoàn tất, một truy vấn `ANY` qua array index ở mức consistency ưu tiên tốc độ có thể tạm chưa nhìn thấy thay đổi vừa ghi.

| Scan consistency | Điều cần hiểu |
| --- | --- |
| `NOT_BOUNDED` | Không đợi index bắt kịp các mutation trước khi thực thi; độ trễ thấp hơn trong nhiều trường hợp nhưng kết quả có thể tạm cũ |
| `REQUEST_PLUS` | Đợi index bắt kịp các mutation liên quan trước khi truy vấn; dữ liệu mới hơn nhưng có thể tăng thời gian chờ |

Nếu đã biết ID của đơn hàng vừa sửa và chỉ cần đọc lại chính đơn đó, KV `findById` là lựa chọn trực tiếp. Nếu cần tìm **tập các đơn** theo SKU sau mutation, hãy chọn scan consistency theo yêu cầu nghiệp vụ, cách gọi Spring Data/SDK của phiên bản thực tế và phép đo độ trễ. Một array index tối ưu không tự bảo đảm read-your-writes cho mọi câu SQL++.

## 13. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Truy vấn `ANY` rất chậm dù có primary index | Primary index không tổ chức entry theo SKU trong mảng | Tạo array secondary index tương thích biểu thức `ANY` |
| Đã tạo index trên `items.sku` nhưng không hiệu quả | `items` là mảng object; index đường dẫn field không biểu diễn đúng mẫu tìm phần tử | Xem lại định nghĩa `DISTINCT ARRAY item.sku FOR item IN items END` |
| Query theo SKU và quantity trả đơn không hợp lệ | Hai điều kiện được viết trong hai `ANY` khác nhau | Đặt cả hai predicate trong cùng một `SATISFIES` |
| `UNNEST` trả trùng orderId | Một đơn có nhiều phần tử phù hợp | Xác định cần đơn hay dòng hàng; cân nhắc `ANY` hoặc xử lý `DISTINCT` đúng nghĩa |
| `ORDER BY` và `LIMIT` cho kết quả phân trang lạ | Phân trang ở cấp item thay vì cấp order; thiếu thứ tự ổn định | Quy định rõ cấp phân trang, khóa sort và index tương ứng |
| Index chỉ trên SKU không được chọn khi thêm tenant | Thiếu index ghép hoặc optimizer chọn kế hoạch khác | Thử `(tenantId, DISTINCT ARRAY ... END)` và đo `EXPLAIN` |
| Partial array index không được dùng | Truy vấn thiếu predicate kiểu entity hoặc soft delete | Đối chiếu SQL++ thực, `_class`, `deleted` và điều kiện index |
| Dữ liệu vừa cập nhật chưa hiện trong kết quả tìm SKU | GSI cập nhật bất đồng bộ | Xem scan consistency; với một ID cụ thể có thể đọc KV |
| Index rất lớn và write throughput giảm | Mảng có nhiều phần tử, dùng `ALL` hoặc nhiều index dư thừa | Đo số entry, loại index ít dùng, cân nhắc `DISTINCT` khi ngữ nghĩa phù hợp |

## 14. Bài thực hành: thiết kế chỉ mục cho ba màn hình

Giả sử API bán hàng có ba màn hình:

1. **A — Tra cứu đơn theo SKU:** nhận `tenantId` và `sku`; trả danh sách đơn, mỗi đơn xuất hiện một lần.
2. **B — Báo cáo dòng hàng:** nhận `tenantId` và `sku`; trả từng dòng hàng với `quantity` để tính tổng.
3. **C — Thống kê giao hàng:** nhận `tenantId` và `city`; lọc theo `shipping.address.city`.

### Bước 1 — Viết truy vấn theo đúng ngữ nghĩa

Màn hình A:

```sql
SELECT META(o).id AS orderId, o.status
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = "TENANT-A"
  AND ANY i IN o.items SATISFIES i.sku = "SKU-42" END;
```

Màn hình B:

```sql
SELECT META(o).id AS orderId, i.sku, i.quantity
FROM `commerce`.`sales`.`orders` AS o
UNNEST o.items AS i
WHERE o.tenantId = "TENANT-A"
  AND i.sku = "SKU-42";
```

Màn hình C:

```sql
SELECT META(o).id AS orderId, o.shipping.address.city AS city
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = "TENANT-A"
  AND o.shipping.address.city = "Ha Noi";
```

### Bước 2 — Đề xuất index

Với A, thử:

```sql
CREATE INDEX ix_practice_tenant_sku
ON `commerce`.`sales`.`orders`(
    `tenantId`,
    DISTINCT ARRAY i.sku FOR i IN items END
);
```

Với B, thử một index `ALL ARRAY` phù hợp với `UNNEST` và so sánh chi phí scan/Fetch với index của A. Đừng mặc định B phải dùng chung index A chỉ vì cùng lọc SKU.

Với C, thử:

```sql
CREATE INDEX ix_practice_tenant_city
ON `commerce`.`sales`.`orders`(
    `tenantId`, `shipping`.`address`.`city`
);
```

Mẫu C không có mảng tại đường dẫn cần lọc, nên dùng secondary index thông thường là điểm khởi đầu hợp lý.

### Bước 3 — Kiểm tra `EXPLAIN` cho từng truy vấn

Chạy `EXPLAIN` của A, B, C với đúng SQL++ và tham số mà ứng dụng dùng. Ghi lại tên index được chọn, số entry ước tính/quét thực tế, operator `Fetch`, kết quả ở cấp document hay item, và độ trễ. Kiểm tra cả trường hợp một đơn có nhiều dòng `SKU-42`, một đơn không có `items` và một đơn có `items = []`.

### Bước 4 — Đánh giá ảnh hưởng tới ghi và đồng thời

Sinh dữ liệu với số item thay đổi, ví dụ 1, 5, 50 phần tử trong mỗi document. So sánh chi phí index của `DISTINCT` và `ALL` theo thực tế số SKU lặp. Thử tình huống cập nhật mảng rồi tìm lại theo SKU, quan sát khác biệt giữa tính nhất quán mặc định và mức yêu cầu index cập nhật mới hơn. Đảm bảo lớp ứng dụng xử lý xung đột cập nhật qua CAS/giao dịch nếu nghiệp vụ yêu cầu.

### Câu hỏi tự kiểm tra

1. Vì sao `shipping.address.city` thường dùng index trên đường dẫn field, còn `items[*].sku` thường cần array index?
2. `DISTINCT ARRAY` và `ALL ARRAY` khác nhau ra sao khi một document có ba dòng cùng SKU?
3. Viết SQL++ để tìm đơn có một item `sku = "SKU-42"` và `quantity >= 2` **trên cùng item**.
4. Tại sao `UNNEST` có thể trả nhiều dòng với cùng một `orderId` trong khi `ANY` không làm như vậy?
5. Vì sao array index một cấp trên `items` không mặc nhiên tối ưu truy vấn hai cấp trên `packages[*].lines[*]`?
6. Khi repository trả entity có `@TypeAlias` và index có predicate `_class`, cần kiểm tra những gì trước khi kết luận index dùng được?
7. Vì sao sau khi cập nhật một item bằng KV, truy vấn SQL++ qua array index có thể tạm trả kết quả cũ?

**Kết luận:** Với Couchbase, **đường dẫn object lồng nhau** và **phần tử mảng** cần chiến lược chỉ mục khác nhau. Hãy dùng `ANY` khi cần biết document có phần tử phù hợp, dùng `UNNEST` khi cần truy cập từng phần tử, và thiết kế `DISTINCT ARRAY`/`ALL ARRAY` theo ngữ nghĩa và workload. Trong **Spring Data Couchbase**, truy vấn mảng phải chính xác về logic, tương thích với mapping và array index; hãy xác nhận bằng `EXPLAIN`, đo chi phí đọc/ghi và chọn mức nhất quán đáp ứng nghiệp vụ trước khi triển khai.

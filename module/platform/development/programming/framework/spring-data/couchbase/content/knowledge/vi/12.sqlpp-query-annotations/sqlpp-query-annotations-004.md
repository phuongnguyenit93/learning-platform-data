# Giá trị NULL, MISSING và logic điều kiện trong Couchbase SQL++

> **Mục tiêu:** Phân biệt trường JSON có giá trị `null` với trường không tồn tại; hiểu logic bốn giá trị của SQL++ (`TRUE`, `FALSE`, `NULL`, `MISSING`); lựa chọn đúng `IS NULL`, `IS MISSING`, `IS VALUED`, các hàm xử lý giá trị thiếu và điều kiện `WHERE` trong Spring Data Couchbase.

Trong **SPRING_DATA_COUCHBASE**, document mapping giúp chuyển đối tượng Java thành JSON document. Trái với bảng quan hệ có cấu trúc cột cố định, các document trong cùng collection Couchbase có thể chứa những tập thuộc tính khác nhau. Hai document cùng đại diện cho sản phẩm, nhưng một document có `discount: null` trong khi document kia **không có** trường `discount`. Sự khác biệt này ảnh hưởng đến truy vấn SQL++, dữ liệu trả về cho Java và thiết kế chỉ mục.

SQL++ là tên hiện dùng của ngôn ngữ truy vấn Couchbase, trước đây thường được gọi là **N1QL**. Ngữ nghĩa của `NULL` và `MISSING` là đặc điểm quan trọng của SQL++ khi truy vấn dữ liệu JSON. Những biểu thức `#{#n1ql...}` trong Spring Data Couchbase vẫn giữ tên lịch sử nhưng tạo ra truy vấn SQL++.

## 1. Mô hình dữ liệu: `NULL` không phải `MISSING`

Giả sử hệ thống bán hàng sử dụng bucket `catalog`, scope `commerce` và collection `products`. Mỗi JSON sau là nội dung của một document riêng; các ID được Couchbase quản lý ngoài JSON body.

**ID: `product::KB-101` — có trường `discount` nhưng giá trị `null`**

```json
{
  "sku": "KB-101",
  "category": "keyboard",
  "price": 1500000,
  "discount": null,
  "active": true,
  "stock": 10,
  "shipping": {
    "method": "standard",
    "fee": null
  }
}
```

**ID: `product::KB-102` — thiếu trường `discount`**

```json
{
  "sku": "KB-102",
  "category": "keyboard",
  "price": 900000,
  "active": true,
  "stock": 0,
  "shipping": {
    "method": "express"
  }
}
```

**ID: `product::MS-201` — có `discount = 0`**

```json
{
  "sku": "MS-201",
  "category": "mouse",
  "price": 450000,
  "discount": 0,
  "active": false,
  "stock": 7,
  "shipping": null
}
```

**ID: `product::MS-202` — có số giảm giá thực sự, nhưng `stock = null`**

```json
{
  "sku": "MS-202",
  "category": "mouse",
  "price": 800000,
  "discount": 0.1,
  "active": true,
  "stock": null,
  "shipping": {
    "method": "express",
    "fee": 30000
  }
}
```

**ID: `product::HS-301` — thiếu `discount`, `active = null`**

```json
{
  "sku": "HS-301",
  "category": "headset",
  "price": 1250000,
  "active": null,
  "stock": 5,
  "shipping": {}
}
```

Ba trạng thái cần nhận diện:

| Tình huống | Trong document JSON | Khi truy cập `p.discount` |
| --- | --- | --- |
| Thuộc tính tồn tại, giá trị không xác định | `"discount": null` | `NULL` |
| Thuộc tính không tồn tại | Không có khóa `discount` | `MISSING` |
| Thuộc tính có giá trị bằng không | `"discount": 0` | Số `0`, không phải `NULL` hay `MISSING` |

**`MISSING` không phải một giá trị hợp lệ của JSON để lưu trực tiếp như `"discount": MISSING`.** Đây là trạng thái trong mô hình đánh giá biểu thức của SQL++ khi thiếu đường dẫn hoặc không tìm thấy giá trị. Trong khi đó, `null` là giá trị JSON hợp lệ và có thể được lưu.

Những chuỗi `""`, số `0`, Boolean `false`, mảng `[]` hay object `{}` đều là **giá trị hiện diện**. Chúng không trở thành `NULL` hoặc `MISSING` chỉ vì “rỗng”, “bằng không” hay “sai”.

## 2. Trường thiếu ảnh hưởng đến phép chiếu `SELECT` như thế nào?

Chạy SQL++ qua Couchbase Query Workbench:

```sql
SELECT p.sku, p.discount
FROM `catalog`.`commerce`.`products` AS p
WHERE p.sku IN ["KB-101", "KB-102"]
ORDER BY p.sku;
```

Kết quả được mô tả như sau:

```json
[
  {
    "sku": "KB-101",
    "discount": null
  },
  {
    "sku": "KB-102"
  }
]
```

`KB-101` có khóa `discount` với giá trị `null`. `KB-102` không có khóa này trong hàng kết quả vì phép chiếu của biểu thức `p.discount` trả về `MISSING`; trường có giá trị `MISSING` thường bị **bỏ qua khi dựng object kết quả**. Đây là sự khác nhau quan sát được ở JSON response, không chỉ là chi tiết nội bộ của SQL++.

Nếu muốn kết quả **luôn chứa** một khóa `discount` với giá trị mặc định, có thể dùng hàm `IFMISSINGORNULL` hoặc `COALESCE` sẽ học ở phần sau. Tuy nhiên, thay thế mặc định làm mất thông tin “vốn thiếu trường hay vốn có giá trị null”, nên cần xác định ý nghĩa nghiệp vụ trước.

### Trường lồng nhau cũng có thể `MISSING`

SQL++ truy cập object bằng dấu chấm:

```sql
SELECT p.sku, p.shipping.method AS shippingMethod,
       p.shipping.fee AS shippingFee
FROM `catalog`.`commerce`.`products` AS p;
```

- Ở `KB-101`, `p.shipping.fee` trả về `NULL` vì `fee` tồn tại và bằng `null`.
- Ở `KB-102`, `p.shipping.fee` là `MISSING` vì object `shipping` thiếu trường `fee`.
- Ở `HS-301`, `p.shipping.method` và `p.shipping.fee` đều `MISSING` vì `shipping` là object rỗng.
- Ở `MS-201`, `shipping` là `NULL`, nên không thể coi `p.shipping.method` là thuộc tính tồn tại. Cần bảo vệ truy vấn bằng kiểm tra object/đường dẫn trước khi dựa vào giá trị.

Truy cập `p.noSuchField` không sinh lỗi “cột không tồn tại” giống một số cơ sở dữ liệu quan hệ; SQL++ có thể trả về `MISSING`. Điều này giúp truy vấn JSON linh hoạt, nhưng dễ che giấu lỗi gõ sai tên field.

## 3. So sánh với `NULL` hoặc `MISSING`: vì sao `= null` không đủ?

Câu truy vấn sau **không phải cách đúng** để tìm mọi document có `discount` bằng null:

```sql
SELECT p.sku
FROM `catalog`.`commerce`.`products` AS p
WHERE p.discount = null;
```

Trong SQL++, với các toán tử so sánh thông thường như `=`, `!=`, `<`, `>`, nếu một toán hạng là `NULL` thì biểu thức có thể trả về `NULL`; nếu một toán hạng là `MISSING` thì có thể trả về `MISSING`. Điều kiện `WHERE` khi đó **không trở thành TRUE**, nên không chọn các document như người mới học thường kỳ vọng. Tương tự, viết `p.discount != null` không diễn đạt đáng tin cậy ý “giá trị tồn tại và không null”.

Để kiểm tra sự hiện diện, hãy dùng **họ toán tử `IS`**:

```sql
-- Chỉ các sản phẩm có discount là giá trị JSON null.
SELECT p.sku
FROM `catalog`.`commerce`.`products` AS p
WHERE p.discount IS NULL;
```

```sql
-- Các sản phẩm không có trường discount.
SELECT p.sku
FROM `catalog`.`commerce`.`products` AS p
WHERE p.discount IS MISSING;
```

```sql
-- Trường discount phải tồn tại VÀ có giá trị khác null.
SELECT p.sku
FROM `catalog`.`commerce`.`products` AS p
WHERE p.discount IS VALUED;
```

Kết quả với bộ dữ liệu mẫu:

| Điều kiện `WHERE` | Các mã sản phẩm được chọn | Giải thích |
| --- | --- | --- |
| `p.discount IS NULL` | KB-101 | Có trường, giá trị là `null` |
| `p.discount IS MISSING` | KB-102, HS-301 | Không có trường `discount` |
| `p.discount IS NOT MISSING` | KB-101, MS-201, MS-202 | Có trường `discount`, kể cả khi giá trị là `null` |
| `p.discount IS VALUED` | MS-201, MS-202 | Có trường với giá trị `0` hoặc `0.1` |
| `p.discount IS NOT VALUED` | KB-101, KB-102, HS-301 | Bằng `NULL` hoặc thiếu trường |

Hai cặp dễ nhầm:

- **`IS NOT MISSING`** chỉ đòi hỏi **trường có mặt**, nên vẫn chấp nhận giá trị `NULL`.
- **`IS VALUED`** đòi hỏi **trường có mặt và giá trị khác `NULL`**, nên loại cả `NULL` và `MISSING`.

Trong nghiệp vụ cần khẳng định **có giá trị thực sự**, hãy dùng `IS VALUED`; cần kiểm tra **có trường**, dùng `IS NOT MISSING`; cần tìm cả hai trạng thái chưa xác định, dùng `IS NOT VALUED`. Chỉ dùng `IS NOT NULL` khi đã xác định rõ nó cần xử lý trường `MISSING` như thế nào trong ngữ nghĩa của phiên bản Couchbase đang sử dụng.

### `IS VALUED` không có nghĩa là “khác 0”, “khác false”

`discount = 0` của MS-201 thỏa `IS VALUED`. Tương tự, `active = false` vẫn là giá trị Boolean hiện diện. Để kiểm tra “chiết khấu dương”, cần thêm điều kiện rõ ràng:

```sql
SELECT p.sku, p.discount
FROM `catalog`.`commerce`.`products` AS p
WHERE p.discount IS VALUED
  AND p.discount > 0;
```

Truy vấn trả về `MS-202`. Với dữ liệu bên ngoài có khả năng sai kiểu, có thể thêm `ISNUMBER(p.discount)` hoặc ràng buộc kiểu/schema để tránh so sánh kiểu không mong đợi.

## 4. Logic điều kiện bốn giá trị: `TRUE`, `FALSE`, `NULL` và `MISSING`

SQL thông thường sử dụng logic ba giá trị với `TRUE`, `FALSE` và `UNKNOWN/NULL`. SQL++ xử lý JSON nên phải phân biệt thêm `MISSING`. Vì vậy, một **biểu thức điều kiện** trong SQL++ có thể cho ra **bốn trạng thái**: `TRUE`, `FALSE`, `NULL` hoặc `MISSING`.

Trong `WHERE`, một document chỉ được giữ lại khi điều kiện đạt **TRUE**. `FALSE`, `NULL` và `MISSING` đều không khiến document đi qua bộ lọc, dù bản chất ba trạng thái đó khác nhau.

### `AND`, `OR` và `NOT` không chỉ trả về Boolean

Một số trường hợp tiêu biểu của bảng chân trị:

| Biểu thức | Kết quả | Giải thích |
| --- | --- | --- |
| `TRUE AND TRUE` | `TRUE` | Hai vế đều đúng |
| `TRUE AND NULL` | `NULL` | Chưa xác định vế thứ hai |
| `TRUE AND MISSING` | `MISSING` | Vế thứ hai thiếu |
| `FALSE AND NULL` | `FALSE` | Một vế sai là đủ kết luận cả biểu thức sai |
| `FALSE AND MISSING` | `FALSE` | Vế sai quyết định kết quả |
| `TRUE OR MISSING` | `TRUE` | Một vế đúng là đủ |
| `FALSE OR NULL` | `NULL` | Không có vế đúng; còn giá trị chưa xác định |
| `FALSE OR MISSING` | `MISSING` | Thiếu thông tin ở vế còn lại |
| `NULL AND MISSING` | `MISSING` | Thiếu thông tin thắng trong phép `AND` này |
| `NULL OR MISSING` | `NULL` | Quy tắc kết hợp riêng của `OR` |
| `NOT TRUE` | `FALSE` | Phủ định Boolean |
| `NOT NULL` | `NULL` | Phủ định không biến chưa xác định thành đúng |
| `NOT MISSING` | `MISSING` | Phủ định không biến thiếu trường thành đúng |

Có thể kiểm tra một số biểu thức độc lập trong Query Workbench mà không cần đọc collection:

```sql
SELECT TRUE AND MISSING AS andMissing,
       FALSE AND MISSING AS andFalse,
       TRUE OR MISSING AS orTrue,
       FALSE OR NULL AS orNull,
       NOT NULL AS notNull;
```

Trong kết quả JSON, cột `andMissing` có giá trị `MISSING` có thể **không xuất hiện**; điều đó không có nghĩa phép tính sai. Cột `andFalse` là `false`, `orTrue` là `true`, còn `orNull` và `notNull` là `null`.

### Tình huống nghiệp vụ: tìm sản phẩm đang hoạt động hoặc có giảm giá dương

```sql
SELECT p.sku
FROM `catalog`.`commerce`.`products` AS p
WHERE p.active = true OR p.discount > 0
ORDER BY p.sku;
```

Đánh giá từng document:

| Sản phẩm | `p.active = true` | `p.discount > 0` | Kết quả `OR` | Có được chọn? |
| --- | --- | --- | --- | --- |
| KB-101 | TRUE | NULL | TRUE | Có |
| KB-102 | TRUE | MISSING | TRUE | Có |
| MS-201 | FALSE | FALSE | FALSE | Không |
| MS-202 | TRUE | TRUE | TRUE | Có |
| HS-301 | NULL | MISSING | NULL | Không |

Truy vấn trả về KB-101, KB-102 và MS-202. Điểm quan trọng là **`TRUE OR MISSING` vẫn TRUE**, nhưng **`FALSE OR MISSING` không trở thành FALSE**. Cần hiểu biểu thức trước khi đọc kết quả từ `WHERE`.

### Vì sao `NOT (discount > 0)` không chọn được các trường thiếu?

```sql
SELECT p.sku
FROM `catalog`.`commerce`.`products` AS p
WHERE NOT (p.discount > 0);
```

Điều kiện trên chọn `MS-201` vì `discount = 0`, nên `0 > 0` là FALSE và `NOT FALSE` là TRUE. Nó **không** chọn KB-101, KB-102 hay HS-301: biểu thức so sánh của các document đó là `NULL` hoặc `MISSING`; phủ định vẫn giữ tính chưa xác định.

Nếu nghiệp vụ thật sự muốn “sản phẩm **không có giảm giá dương**, bao gồm cả chưa khai báo và null”, cần diễn đạt tường minh:

```sql
SELECT p.sku
FROM `catalog`.`commerce`.`products` AS p
WHERE p.discount IS NOT VALUED
   OR (ISNUMBER(p.discount) AND p.discount <= 0);
```

Với dữ liệu mẫu, truy vấn chọn KB-101, KB-102, MS-201 và HS-301. Nếu có document mà `discount` là chuỗi hoặc object, cần xác định chính sách riêng cho dữ liệu sai kiểu, thay vì mặc nhiên xem chúng là giá trị số.

### Thứ tự ưu tiên khi kết hợp `AND` và `OR`

`NOT` có độ ưu tiên cao hơn `AND`, và `AND` cao hơn `OR`. Vì vậy:

```sql
WHERE p.category = "keyboard"
  AND p.active = true
   OR p.discount > 0
```

được hiểu là `(category = "keyboard" AND active = true) OR (discount > 0)`. Nó có thể trả về sản phẩm không thuộc keyboard nếu có giảm giá dương. Nếu muốn chỉ chọn keyboard nhưng chấp nhận một trong hai điều kiện còn lại:

```sql
WHERE p.category = "keyboard"
  AND (p.active = true OR p.discount > 0)
```

Dùng ngoặc tường minh để tránh lỗi logic, nhất là khi một vài trường có thể `NULL` hoặc `MISSING`.

## 5. Hàm xử lý giá trị chưa xác định: `IFMISSING`, `IFNULL`, `IFMISSINGORNULL`

SQL++ hỗ trợ các hàm chọn giá trị dự phòng. Ba hàm có tên gần nhau nhưng **khác nhau ở trạng thái cần bỏ qua**.

| Hàm | Bỏ qua giá trị nào? | Khi nên dùng |
| --- | --- | --- |
| `IFMISSING(a, fallback)` | Chỉ `MISSING` | Thay giá trị khi **thiếu trường**, vẫn giữ `NULL` tường minh |
| `IFNULL(a, fallback)` | Chỉ `NULL` | Thay giá trị `NULL`, vẫn giữ khác biệt với `MISSING` |
| `IFMISSINGORNULL(a, fallback)` | Cả `NULL` và `MISSING` | Cần giá trị mặc định chung cho hai trạng thái |
| `COALESCE(a, fallback)` | Cả `NULL` và `MISSING` | Tên thay thế của `IFMISSINGORNULL` |

Ví dụ:

```sql
SELECT p.sku,
       IFMISSING(p.discount, 0) AS ifMissing,
       IFNULL(p.discount, 0) AS ifNull,
       IFMISSINGORNULL(p.discount, 0) AS effectiveDiscount
FROM `catalog`.`commerce`.`products` AS p
ORDER BY p.sku;
```

Kết quả logic tương ứng với hai trường hợp quan trọng:

| `p.discount` | `IFMISSING(p.discount, 0)` | `IFNULL(p.discount, 0)` | `IFMISSINGORNULL(p.discount, 0)` |
| --- | --- | --- | --- |
| `NULL` | `NULL` | `0` | `0` |
| `MISSING` | `0` | `MISSING` | `0` |
| `0` | `0` | `0` | `0` |
| `0.1` | `0.1` | `0.1` | `0.1` |

Nếu `ifNull` nhận `MISSING`, khóa này có thể vắng mặt trong object kết quả, dù truy vấn khai báo alias. Khi cần đầu ra JSON ổn định và chính sách mặc định rõ ràng, `IFMISSINGORNULL` hoặc `COALESCE` thường thuận tiện.

### Giá trị mặc định trong `SELECT` và điều kiện trong `WHERE`

Giả sử quy ước nghiệp vụ: **không khai báo hoặc null có nghĩa là giảm giá bằng 0**. Có thể chiếu trường tính toán:

```sql
SELECT p.sku,
       p.price,
       COALESCE(p.discount, 0) AS effectiveDiscount
FROM `catalog`.`commerce`.`products` AS p;
```

Hoặc lọc theo tỷ lệ giảm giá đã chuẩn hóa:

```sql
SELECT p.sku
FROM `catalog`.`commerce`.`products` AS p
WHERE COALESCE(p.discount, 0) >= 0.05;
```

Với bộ dữ liệu mẫu, chỉ MS-202 đáp ứng. **Giá trị mặc định là quyết định nghiệp vụ**, không phải quy tắc Couchbase tự suy đoán. Trong hệ thống kế toán hay vận hành, `NULL` có thể mang nghĩa “chưa duyệt” còn `MISSING` mang nghĩa “chưa áp dụng”; không nên tự động hợp nhất chúng nếu cần giữ vết trạng thái.

### `NULLIF`: biến một giá trị đặc biệt thành `NULL`

`NULLIF(a, b)` trả về `NULL` khi `a` bằng `b`; còn lại trả về `a` (với các quy tắc đặc biệt khi đầu vào là `NULL/MISSING`). Ví dụ:

```sql
SELECT p.sku,
       NULLIF(p.discount, 0) AS nonZeroDiscount
FROM `catalog`.`commerce`.`products` AS p;
```

`MS-201` có `discount = 0` nên `nonZeroDiscount` là `NULL`. Hàm này hữu ích khi giá trị `0` được định nghĩa là ký hiệu “không có chiết khấu”, nhưng cần thận trọng vì thay đổi ngữ nghĩa và phép chiếu dữ liệu.

## 6. `CASE WHEN`: phân loại rõ trạng thái trước khi áp dụng quy tắc

Khi `NULL` và `MISSING` mang hai nghĩa khác nhau, dùng dạng **searched CASE** sẽ dễ kiểm soát hơn:

```sql
SELECT p.sku,
       CASE
         WHEN p.discount IS MISSING THEN "not-provided"
         WHEN p.discount IS NULL THEN "explicit-null"
         WHEN p.discount = 0 THEN "no-discount"
         ELSE "positive-discount"
       END AS discountState
FROM `catalog`.`commerce`.`products` AS p
ORDER BY p.sku;
```

Kết quả dự kiến:

| `sku` | `discountState` |
| --- | --- |
| KB-101 | `explicit-null` |
| KB-102 | `not-provided` |
| MS-201 | `no-discount` |
| MS-202 | `positive-discount` |
| HS-301 | `not-provided` |

Thứ tự các nhánh giúp phân biệt thiếu trường, giá trị null và giá trị 0 trước khi đi vào `ELSE`. Với dữ liệu có nhiều kiểu khác nhau, có thể bổ sung `WHEN NOT ISNUMBER(p.discount) THEN "invalid-type"` trước `ELSE`.

**Không nên** thay bằng `CASE p.discount WHEN NULL THEN ...` và mong tìm được trạng thái NULL theo so sánh bằng thông thường. Hãy dùng `WHEN p.discount IS NULL` hay `WHEN p.discount IS MISSING` để biểu đạt rõ hai trường hợp.

Nếu dùng `CASE` không có `ELSE` và không nhánh `WHEN` nào đúng, kết quả mặc định là `NULL`. Do đó, một nhánh `ELSE` có ý nghĩa nên được khai báo khi API muốn mã trạng thái luôn hiện diện.

## 7. Thiết kế điều kiện an toàn với dữ liệu JSON không đồng nhất

Hãy chuyển yêu cầu nghiệp vụ thành điều kiện rõ ràng thay vì suy đoán `NULL` và `MISSING` đồng nghĩa. Bốn câu hỏi sau thường xuyên xuất hiện trong ứng dụng:

### Chỉ lấy sản phẩm có trường thông tin giao hàng

```sql
SELECT p.sku
FROM `catalog`.`commerce`.`products` AS p
WHERE p.shipping IS NOT MISSING;
```

Trong dữ liệu mẫu, cả năm document đều có trường `shipping`, kể cả `MS-201` có `shipping: null` và `HS-301` có `shipping: {}`. Truy vấn trả lời đúng câu hỏi “có trường”, **không khẳng định** trường chứa một object sử dụng được.

Nếu cần một object có giá trị và đủ thông tin:

```sql
SELECT p.sku
FROM `catalog`.`commerce`.`products` AS p
WHERE ISOBJECT(p.shipping)
  AND p.shipping.method IS VALUED;
```

Truy vấn chọn KB-101, KB-102 và MS-202. `ISOBJECT(...)` là hàm kiểm tra kiểu; `IS VALUED` yêu cầu `method` tồn tại và không null. Riêng `HS-301` có `shipping: {}` nhưng thiếu `method`, nên bị loại.

### Chỉ lấy sản phẩm đang hoạt động

```sql
SELECT p.sku
FROM `catalog`.`commerce`.`products` AS p
WHERE p.active = true;
```

Truy vấn chọn KB-101, KB-102, MS-202. `MS-201` có `active: false` nên không được chọn; `HS-301` có `active: null` cũng không được chọn. Khi cần phân biệt “đã tắt” với “chưa xác định”, hãy giữ `false` và `null` là hai trạng thái khác nhau trong schema, DTO và truy vấn.

### Đặt mặc định cho Boolean khi nghiệp vụ cho phép

Giả sử quy ước: sản phẩm thiếu trạng thái hoạt động hoặc trạng thái là null thì xem như **không hoạt động**:

```sql
SELECT p.sku,
       COALESCE(p.active, false) AS effectiveActive
FROM `catalog`.`commerce`.`products` AS p;
```

Giá trị `effectiveActive` của HS-301 trở thành `false`, trong khi không làm thay đổi JSON gốc. Nếu `NULL` nghĩa là “đang chờ duyệt” và khác `false` nghĩa là “đã vô hiệu hóa”, không nên gộp cả hai giá trị vào cùng trạng thái.

### Tìm sản phẩm chưa khai báo hoặc đã bỏ trống phí giao hàng

```sql
SELECT p.sku
FROM `catalog`.`commerce`.`products` AS p
WHERE p.shipping.fee IS NOT VALUED;
```

Kết quả là KB-101 (phí null), KB-102 (thiếu phí), MS-201 (shipping null) và HS-301 (shipping rỗng). MS-202 có `fee: 30000` nên không thỏa. Nếu nghiệp vụ chỉ muốn phí giao hàng **bằng null một cách tường minh**, không được gộp cả trường hợp thiếu phí và object cha thiếu dữ liệu: cần kiểm tra cụ thể từng tầng.

### Kiểu JSON và toán tử điều kiện

`0`, `false`, `""`, `[]` và `{}` không phải `NULL` hay `MISSING`. Một số biểu thức điều kiện trong SQL++ diễn giải các giá trị không phải Boolean theo quy tắc truthiness, nhưng trong mã nghiệp vụ nên **so sánh tường minh** để dễ bảo trì:

```sql
-- Rõ nghĩa: số lượng phải là số và lớn hơn 0.
WHERE ISNUMBER(p.stock) AND p.stock > 0

-- Rõ nghĩa: trạng thái phải là Boolean true.
WHERE p.active = true
```

Điều kiện `p.stock IS VALUED` chỉ chứng minh có giá trị; nếu `stock` là chuỗi `"10"` hoặc mảng `[]`, nó vẫn được coi là có giá trị. Muốn kiểm tra loại dữ liệu, dùng các hàm như `ISNUMBER(...)`, `ISSTRING(...)`, `ISBOOLEAN(...)`, `ISARRAY(...)` và `ISOBJECT(...)`.

## 8. Từ SQL++ sang Spring Data Couchbase Repository

Spring Data Couchbase cho phép truy vấn trực tiếp bằng `@Query` trên Repository. Khi phương thức trả về **full entity**, dùng `#{#n1ql.selectEntity}` để sinh phần `SELECT/FROM` phù hợp với metadata ánh xạ; thêm `#{#n1ql.filter}` để hạn chế document theo kiểu entity do Spring Data quản lý.

Giả sử Spring Boot đã được cấu hình kết nối đến bucket `catalog`; entity đặt trong scope `commerce`, collection `products`:

```java
import java.math.BigDecimal;

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
    private BigDecimal price;
    private BigDecimal discount;
    private Boolean active;
    private Integer stock;

    public Product() {}

    // Bổ sung getter/setter, constructor hoặc accessors phù hợp dự án.
}
```

Chọn `BigDecimal` cho giá trị tài chính; `Boolean`, `Integer` là wrapper cho phép biểu diễn `null` trong Java. Chọn primitive như `boolean` thường không thể biểu diễn trạng thái chưa xác định. Tuy nhiên, **wrapper `null` ở Java không tự phân biệt được** JSON có trường với giá trị `null` hay không có trường ấy.

Repository với các câu truy vấn thể hiện đúng nghiệp vụ:

```java
import java.math.BigDecimal;
import java.util.List;

import org.springframework.data.couchbase.repository.CouchbaseRepository;
import org.springframework.data.couchbase.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ProductRepository
        extends CouchbaseRepository<Product, String> {

    // Trường discount hoàn toàn không có trong JSON document.
    @Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} "
         + "AND discount IS MISSING")
    List<Product> findWithoutDiscountField();

    // Trường discount có giá trị JSON null.
    @Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} "
         + "AND discount IS NULL")
    List<Product> findWithExplicitNullDiscount();

    // Cả hai trường hợp NULL và MISSING đều được xem là chưa có giá trị.
    @Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} "
         + "AND discount IS NOT VALUED")
    List<Product> findWithoutEffectiveDiscount();

    // Quy ước nghiệp vụ: cả NULL và MISSING tương đương giá trị mặc định 0.
    @Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} "
         + "AND COALESCE(discount, 0) >= $minDiscount")
    List<Product> findWithEffectiveDiscountAtLeast(
            @Param("minDiscount") BigDecimal minDiscount);
}
```

Để tìm sản phẩm giảm giá từ `5%` trở lên, gọi:

```java
List<Product> discounted = repository.findWithEffectiveDiscountAtLeast(
    new BigDecimal("0.05")
);
```

Với bộ dữ liệu mẫu và kiểu mapping tương ứng, chỉ MS-202 có `discount = 0.1`. Giá trị `$minDiscount` được ràng buộc dưới dạng tham số SQL++: không ghép dữ liệu người dùng vào câu truy vấn bằng phép cộng chuỗi.

**Cần phân biệt ba lớp:**

| Thành phần | Trách nhiệm |
| --- | --- |
| `@Query("...")` | Khai báo truy vấn trên Repository |
| `#{#n1ql.selectEntity}` và `#{#n1ql.filter}` | Spring Data thay thế qua SpEL trước khi gửi câu SQL++ |
| `IS NULL`, `IS MISSING`, `IS VALUED`, `COALESCE` | Couchbase Query Service đánh giá trên JSON document |
| `$minDiscount` | Giá trị tham số truy vấn được ràng buộc từ Java `@Param` |

Các biến `#n1ql` là tên API lịch sử. Không dán nguyên `#{#n1ql.selectEntity}` vào Query Workbench và mong Couchbase hiểu biểu thức này.

### Lưu ý khi tự chèn document bằng Workbench hoặc SDK

JSON mẫu trong bài cố ý tập trung vào trường nghiệp vụ, nên chưa thêm trường phân biệt loại entity. Spring Data thường ghi thông tin phân loại (ví dụ `_class`) khi lưu entity. Do đó, khi tự chèn các JSON mẫu ngoài Spring Data, truy vấn Repository chứa `#{#n1ql.filter}` **có thể không thấy document**, dù SQL++ thuần trong Workbench vẫn thấy. Hãy dùng document lưu bằng cùng mapping hoặc đảm bảo thông tin phân loại nhất quán với cấu hình thực tế.

### Java mapping có làm mất phân biệt `NULL` và `MISSING` không?

Có thể. Khi đọc vào `Product.discount` kiểu `BigDecimal`, cả trường `"discount": null` và trường không tồn tại đều có thể được biểu diễn bằng giá trị `null` trong Java. Một entity đơn giản không tự lưu thêm dấu hiệu cho biết nguồn gốc nào đã tạo ra `null`. Nếu nghiệp vụ bắt buộc phân biệt:

- Truy vấn bằng `IS NULL` / `IS MISSING` ngay tại Couchbase khi chọn document.
- Nếu phải trả ra API, thêm trạng thái tường minh như `discountState` bằng `CASE WHEN` hoặc DTO chứa cờ `fieldPresent`.
- Khi cần giữ nguyên sự khác biệt để ghi lại document, làm việc với JSON thô hoặc mô hình domain có trạng thái hiện diện được thiết kế rõ ràng. Kiểm tra chính sách serializer/mapping của phiên bản đang dùng.

Không tự giả định rằng thao tác `save(entity)` sẽ giữ nguyên phân biệt missing/null của document đầu vào. Hành vi phụ thuộc cách serialization, mapping và các annotation cấu hình.

### `CouchbaseTemplate` và Repository reactive

Có thể xây dựng điều kiện qua `CouchbaseTemplate` thay vì `@Query` nếu ứng dụng cần truy vấn động, hoặc dùng API reactive để trả về `Flux<Product>`. Hai lựa chọn này không thay đổi ngữ nghĩa SQL++: `NULL`, `MISSING` và logic bốn giá trị vẫn được đánh giá tại Query Service. Lựa chọn API cần xét cấu trúc ứng dụng, hiệu năng, sự nhất quán và yêu cầu vận hành.

## 9. Chỉ mục và hiệu năng cho điều kiện có trường thiếu

Truy vấn SQL++ có `WHERE` thường cần secondary index để không phải quét dữ liệu tùy tiện. Ví dụ:

```sql
CREATE INDEX idx_products_discount
ON `catalog`.`commerce`.`products`(discount);
```

**Điểm cần chú ý:** secondary index thông thường có thể **không chứa document mà khóa chỉ mục đứng đầu là `MISSING`**. Vì vậy, không nên nghĩ rằng cứ tạo index trên `discount` là truy vấn `discount IS MISSING` có đường truy cập tối ưu. Kiểm tra truy vấn và kế hoạch thực thi thực tế, đặc biệt khi tìm nhiều document thiếu một trường tùy chọn.

Khi nghiệp vụ luôn lọc trên giá trị mặc định:

```sql
WHERE COALESCE(discount, 0) >= 0.05
```

một index thường trên `discount` chưa chắc tương thích trực tiếp với biểu thức đã biến đổi bằng `COALESCE`. Có thể xem xét **expression index** theo cùng biểu thức:

```sql
CREATE INDEX idx_products_effective_discount
ON `catalog`.`commerce`.`products`(
    COALESCE(discount, 0)
);
```

Sau đó dùng `EXPLAIN` để xác minh optimizer thực sự chọn chỉ mục:

```sql
EXPLAIN
SELECT p.sku, p.discount
FROM `catalog`.`commerce`.`products` AS p
WHERE COALESCE(p.discount, 0) >= 0.05;
```

Chỉ mục trên biểu thức có thêm chi phí lưu trữ và duy trì khi ghi; nó là phương án để **đánh giá** dựa trên dữ liệu và workload, không phải quy tắc luôn tạo cho mọi trường nullable. Trong hệ thống có nhiều điều kiện, cần cân nhắc thứ tự khóa, chỉ mục tổ hợp, tình trạng type discriminator và nhu cầu phân trang.

### Ảnh hưởng của scan consistency

Document vừa được ghi qua Key/Value API có thể chưa xuất hiện ngay trong kết quả SQL++ vì chỉ mục cập nhật bất đồng bộ. Ở scan consistency `NOT_BOUNDED`, truy vấn `WHERE discount IS MISSING` hay `WHERE discount IS VALUED` có thể chưa phản ánh ghi mới nhất. `REQUEST_PLUS` yêu cầu Query Service đợi chỉ mục cập nhật trước thời điểm truy vấn nhưng có thể tăng độ trễ.

Nếu biết document ID và muốn kiểm tra giá trị hiện tại của một document, đường đọc Key/Value có thể phù hợp hơn. **TTL** quyết định thời hạn sống document; **CAS** hỗ trợ kiểm soát ghi đồng thời; **transactions** quy định phạm vi thao tác nguyên tử. Các cơ chế này giải quyết những vấn đề khác nhau, không biến `MISSING` thành `NULL` hay thay đổi bảng chân trị SQL++.

## 10. Lỗi thường gặp khi xử lý `NULL` và `MISSING`

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `WHERE discount = null` không tìm được document mong muốn | So sánh thông thường không xác định trên `NULL`/`MISSING` | Dùng `IS NULL` hoặc `IS MISSING` theo nghiệp vụ |
| `WHERE discount != null` không lọc đúng “có chiết khấu” | Phủ định so sánh với `null` không tương đương kiểm tra giá trị | Dùng `IS VALUED` và điều kiện số học cần thiết |
| JSON response có hàng không chứa khóa `discount` | Phép chiếu nhận `MISSING` nên bỏ khóa | Nếu cần mặc định, dùng `IFMISSING`/`COALESCE` theo quy ước |
| `IS NOT MISSING` vẫn chọn `discount: null` | Kiểm tra sự tồn tại trường, không kiểm tra giá trị | Dùng `IS VALUED` nếu yêu cầu giá trị không null |
| `IS VALUED` vẫn chọn `discount = 0` | `0` là một giá trị hợp lệ | Thêm `discount > 0` khi muốn giá trị dương |
| `NOT (discount > 0)` bỏ qua document thiếu trường | `NOT MISSING` vẫn là `MISSING`, `NOT NULL` vẫn là `NULL` | Thêm điều kiện `IS NOT VALUED` khi muốn chọn cả hai trạng thái |
| `IFNULL(discount, 0)` không thay thế trường thiếu | `IFNULL` chỉ bỏ qua `NULL` | Dùng `IFMISSINGORNULL` hoặc `COALESCE` |
| Entity Java có `discount == null` nhưng không rõ JSON gốc | Mapping sang một field wrapper có thể mất trạng thái hiện diện | Truy vấn trạng thái hoặc thiết kế model có cờ hiện diện |
| Workbench có document, Repository không thấy | `#n1ql.filter` loại document thiếu discriminator hoặc sai collection | Kiểm tra type mapping, bucket/scope/collection và cách chèn dữ liệu |
| Truy vấn `IS MISSING` chậm | Index có thể không lập khóa cho giá trị `MISSING` | Kiểm tra `EXPLAIN` và thiết kế chỉ mục phù hợp với bộ lọc |

## 11. Bài thực hành và tự kiểm tra

### Bài 1 — Phân biệt ba trạng thái chiết khấu

Hãy viết SQL++ trả về `sku` và nhãn trạng thái `missing`, `null`, `zero`, `positive`.

```sql
SELECT p.sku,
       CASE
         WHEN p.discount IS MISSING THEN "missing"
         WHEN p.discount IS NULL THEN "null"
         WHEN p.discount = 0 THEN "zero"
         WHEN ISNUMBER(p.discount) AND p.discount > 0 THEN "positive"
         ELSE "unexpected-value"
       END AS discountStatus
FROM `catalog`.`commerce`.`products` AS p
ORDER BY p.sku;
```

**Đáp án dự kiến:** KB-101 → `null`, KB-102 → `missing`, MS-201 → `zero`, MS-202 → `positive`, HS-301 → `missing`.

### Bài 2 — Chỉ lấy sản phẩm có phí giao hàng hợp lệ

```sql
SELECT p.sku, p.shipping.fee AS shippingFee
FROM `catalog`.`commerce`.`products` AS p
WHERE ISOBJECT(p.shipping)
  AND ISNUMBER(p.shipping.fee)
  AND p.shipping.fee >= 0;
```

**Đáp án dự kiến:** MS-202 có `fee = 30000`. KB-101 có phí null; KB-102 và HS-301 thiếu phí; MS-201 có shipping null.

### Bài 3 — Trường hợp phủ định điều kiện

Cho `discount` là `NULL`, `MISSING`, `0` và `0.1`. Hỏi trường hợp nào được chọn bởi `NOT (discount > 0)`?

**Đáp án:** Chỉ `0`, vì `0 > 0` là FALSE nên phủ định thành TRUE. Các giá trị `NULL` và `MISSING` vẫn không xác định, còn `0.1 > 0` là TRUE nên phủ định thành FALSE.

### Bài 4 — Cách biểu đạt yêu cầu “có giá trị”

Giải thích khác nhau giữa `discount IS NOT MISSING`, `discount IS VALUED` và `discount IS NOT VALUED`.

**Đáp án:** `IS NOT MISSING` chấp nhận cả `NULL` nếu trường tồn tại; `IS VALUED` chỉ chấp nhận giá trị khác `NULL` và `MISSING`; `IS NOT VALUED` tìm hai trạng thái `NULL` hoặc `MISSING`.

### Bài 5 — Dự đoán kết quả `AND` và `OR`

| Biểu thức | Đáp án |
| --- | --- |
| `FALSE AND MISSING` | `FALSE` |
| `TRUE AND MISSING` | `MISSING` |
| `TRUE OR NULL` | `TRUE` |
| `FALSE OR NULL` | `NULL` |
| `NOT MISSING` | `MISSING` |

Hãy chạy `SELECT` các biểu thức này trong Query Workbench để quan sát rằng một cột có giá trị `MISSING` có thể không xuất hiện trong JSON object kết quả.

## Tài liệu tham khảo chính thức

- [Couchbase — Boolean Logic](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/booleanlogic.html): logic bốn giá trị và cách diễn giải điều kiện.
- [Couchbase — Logical Operators](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/logicalops.html): bảng chân trị `AND`, `OR` và `NOT`.
- [Couchbase — Comparison Operators](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/comparisonops.html): `IS NULL`, `IS MISSING`, `IS VALUED` và phép so sánh.
- [Couchbase — Conditional Functions for Unknowns](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/condfununknown.html): `IFMISSING`, `IFNULL`, `IFMISSINGORNULL`, `COALESCE`, `NULLIF`.
- [Couchbase — Type Functions](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/typefun.html): `ISNUMBER`, `ISOBJECT` và các hàm kiểm tra kiểu JSON.
- [Spring Data Couchbase — Couchbase Repositories](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): truy vấn `@Query`, biến SpEL `#n1ql` và ràng buộc tham số.

**Ghi nhớ:** `NULL` nghĩa là thuộc tính có giá trị JSON `null`; `MISSING` nghĩa là không có giá trị tại đường dẫn đang truy cập. `WHERE` chỉ chọn khi kết quả là **TRUE**, trong khi `AND`/`OR`/`NOT` có thể tạo ra `NULL` hoặc `MISSING`. Hãy dùng `IS MISSING`, `IS VALUED`, `IS NOT VALUED` và các hàm xử lý giá trị mặc định theo đúng ý nghĩa nghiệp vụ, đặc biệt khi kết hợp SQL++ với entity mapping và Repository `@Query` của Spring Data Couchbase.

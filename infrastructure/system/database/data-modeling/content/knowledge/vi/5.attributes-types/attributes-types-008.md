# Null, dữ liệu vắng mặt, giá trị rỗng và giá trị mặc định

## 1. Vì sao phải phân biệt bốn trạng thái này?

Khi thiết kế mô hình dữ liệu, một trường không có nội dung có thể mang nhiều ý nghĩa khác nhau. Giá trị chưa được biết, trường chưa được gửi lên, chuỗi rỗng, danh sách rỗng và giá trị mặc định đều có thể trông giống như “không có dữ liệu”, nhưng chúng diễn đạt những trạng thái khác nhau.

Ví dụ, một hồ sơ khách hàng có trường `middle_name`:

- `NULL`: hệ thống không có giá trị tên đệm hoặc hiện chưa biết tên đệm.
- Trường không xuất hiện trong tài liệu JSON: nguồn gửi dữ liệu không cung cấp trường này, hoặc trường không thuộc phiên bản dữ liệu đó.
- `""`: có một giá trị chuỗi và giá trị đó có độ dài bằng 0; nghiệp vụ có thể hiểu là người dùng chủ động để trống.
- Giá trị mặc định, ví dụ `"Chưa cung cấp"`: hệ thống tự điền một giá trị khi tạo hồ sơ theo quy tắc đã định.

Nếu gộp các trạng thái này thành một, hệ thống có thể xóa nhầm dữ liệu khi cập nhật, hiển thị thông tin sai, bỏ qua yêu cầu nhập liệu hoặc tạo báo cáo không chính xác.

Bài học này phân biệt bốn khái niệm:

1. **NULL:** dấu hiệu cho biết giá trị của thuộc tính không có hoặc không xác định theo semantics của hệ quản trị.
2. **Dữ liệu vắng mặt (missing/absent):** thuộc tính không được cung cấp hoặc không tồn tại trong cấu trúc bản ghi.
3. **Giá trị rỗng (empty):** giá trị tồn tại nhưng không chứa phần tử hoặc ký tự, chẳng hạn chuỗi `""`, mảng `[]` hoặc đối tượng `{}`.
4. **Giá trị mặc định (default):** giá trị được hệ thống chọn khi thao tác ghi không cung cấp giá trị theo quy tắc đã định.

Muốn mô hình đúng, trước hết phải xác định ý nghĩa nghiệp vụ của từng trạng thái; sau đó mới chọn kiểu dữ liệu, khả năng NULL, default, constraint và cách xử lý ở API.

## 2. NULL trong mô hình dữ liệu quan hệ

### 2.1. NULL biểu thị giá trị không có hoặc chưa xác định

Trong SQL, `NULL` là một marker đặc biệt biểu thị dữ liệu không có theo cách diễn giải của hệ quản trị. Nó không phải số 0, chuỗi rỗng, chuỗi ký tự "NULL" hay một giá trị thông thường có thể so sánh bằng toán tử bằng.

Ví dụ, bảng nhân viên có thể cho phép ngày nghỉ việc chưa xác định:

```sql
CREATE TABLE employee (
    employee_id BIGINT PRIMARY KEY,
    full_name VARCHAR(200) NOT NULL,
    terminated_at TIMESTAMP NULL
);
```

Nếu nhân viên vẫn đang làm việc hoặc chưa có ngày nghỉ việc, `terminated_at` có thể là `NULL` theo quy ước của mô hình.

Tuy nhiên, NULL không tự nói rõ lý do tại sao không có giá trị. Nó có thể được dùng cho nhiều tình huống khác nhau:

- Chưa biết giá trị.
- Chưa thu thập giá trị.
- Không áp dụng cho đối tượng này.
- Giá trị bị ẩn hoặc không được phép cung cấp.
- Giá trị chưa được xác định tại thời điểm ghi nhận.

Nếu các lý do này có ý nghĩa khác nhau với nghiệp vụ, chỉ một cột NULL là chưa đủ để diễn đạt. Cần thêm trạng thái hoặc thuộc tính giải thích.

### 2.2. NULL không bằng NULL

Trong SQL, phép so sánh thông thường với NULL thường cho kết quả UNKNOWN, kể cả khi so sánh NULL với NULL:

```sql
SELECT NULL = NULL;       -- UNKNOWN
SELECT NULL <> 10;        -- UNKNOWN
SELECT NULL = 10;         -- UNKNOWN
```

Vì vậy, không dùng `column = NULL` để tìm bản ghi thiếu giá trị. Hãy dùng:

```sql
SELECT *
FROM employee
WHERE terminated_at IS NULL;
```

Và để tìm giá trị đã có:

```sql
SELECT *
FROM employee
WHERE terminated_at IS NOT NULL;
```

Một số hệ quản trị cung cấp toán tử so sánh NULL an toàn như `IS DISTINCT FROM` hoặc `IS NOT DISTINCT FROM`. Cú pháp và hỗ trợ có thể khác nhau theo engine. Trong PostgreSQL, ví dụ:

```sql
SELECT NULL IS NOT DISTINCT FROM NULL; -- TRUE
SELECT 10 IS DISTINCT FROM NULL;       -- TRUE
```

Toán tử này hữu ích khi cần so sánh hai giá trị mà xem hai NULL là tương đương theo quy tắc đã chọn.

### 2.3. Logic ba giá trị: TRUE, FALSE và UNKNOWN

Điều kiện SQL có thể trả về ba trạng thái:

- **TRUE:** điều kiện được xác nhận đúng.
- **FALSE:** điều kiện được xác nhận sai.
- **UNKNOWN:** không đủ thông tin để kết luận do có NULL.

Ví dụ:

```sql
SELECT *
FROM employee
WHERE terminated_at > CURRENT_TIMESTAMP;
```

Nếu `terminated_at` là NULL, biểu thức so sánh không trả về TRUE hay FALSE mà là UNKNOWN. Mệnh đề WHERE chỉ giữ các hàng có điều kiện TRUE, vì vậy hàng đó không được trả về.

Một vài quy tắc thường gặp:

| Biểu thức | Kết quả khi có NULL |
|---|---|
| `NULL = 5` | UNKNOWN |
| `NULL <> 5` | UNKNOWN |
| `NOT UNKNOWN` | UNKNOWN |
| `TRUE AND UNKNOWN` | UNKNOWN |
| `FALSE AND UNKNOWN` | FALSE |
| `TRUE OR UNKNOWN` | TRUE |
| `FALSE OR UNKNOWN` | UNKNOWN |

Đây là lý do một điều kiện lọc có thể bỏ qua các hàng mà người viết truy vấn không dự đoán. Khi thiết kế truy vấn, cần xác định rõ cách xử lý giá trị chưa biết thay vì mặc định NULL sẽ hành xử như một giá trị bình thường.

### 2.4. Hàm tổng hợp và NULL

Nhiều hàm tổng hợp bỏ qua NULL:

```sql
SELECT
    COUNT(*) AS row_count,
    COUNT(discount_amount) AS known_discount_count,
    AVG(discount_amount) AS average_discount
FROM order_line;
```

- `COUNT(*)` đếm tất cả hàng.
- `COUNT(discount_amount)` chỉ đếm hàng có `discount_amount` khác NULL.
- `AVG(discount_amount)` tính trung bình trên các giá trị không NULL.

Điều này có thể tạo khác biệt đáng kể trong báo cáo. Nếu NULL có nghĩa “chưa được tính”, thì bỏ qua NULL có thể phù hợp. Nếu NULL có nghĩa “không giảm giá”, việc bỏ qua có thể làm trung bình bị sai so với nghiệp vụ; khi đó cần lưu số 0 hoặc chuyển đổi có chủ đích.

Không nên dùng `COALESCE(discount_amount, 0)` chỉ để tránh NULL mà chưa xác định ý nghĩa. Hàm `COALESCE` trả về giá trị đầu tiên không NULL, nhưng việc thay NULL bằng 0 có thể biến “chưa biết” thành “đã xác nhận không có”.

## 3. Dữ liệu vắng mặt (missing/absent)

### 3.1. Thuộc tính không xuất hiện trong bản ghi

Trong một số mô hình document hoặc dữ liệu JSON, một thuộc tính có thể không xuất hiện. Ví dụ:

```json
{
  "customerId": 1001,
  "fullName": "Mai Nguyen"
}
```

Ở đây, `middleName` không tồn tại trong document. Điều đó khác với:

```json
{
  "customerId": 1001,
  "fullName": "Mai Nguyen",
  "middleName": null
}
```

Trong document thứ hai, trường có mặt và mang giá trị null theo semantics JSON.

Sự khác biệt có thể quan trọng:

- Missing: nguồn không gửi trường, trường chưa được thu thập hoặc phiên bản schema không có thuộc tính này.
- Null: nguồn có chủ ý biểu thị giá trị không có hoặc chưa xác định.
- Có giá trị: nguồn cung cấp thông tin cụ thể.

Không phải mọi hệ quản trị document đều xử lý missing và null giống nhau trong truy vấn, chỉ mục hoặc constraint. Cần hiểu semantics của công nghệ được chọn.

### 3.2. Missing trong cập nhật một phần

Missing thường đặc biệt quan trọng trong API cập nhật. Giả sử hồ sơ hiện tại có:

```json
{
  "customerId": 1001,
  "email": "mai@example.test",
  "phone": "+84912345678"
}
```

Một yêu cầu cập nhật chỉ gửi:

```json
{
  "email": "mai.new@example.test"
}
```

Nếu API được định nghĩa là cập nhật một phần (PATCH), việc thiếu `phone` thường có nghĩa là giữ nguyên số điện thoại hiện tại.

Nếu yêu cầu gửi:

```json
{
  "email": "mai.new@example.test",
  "phone": null
}
```

thì `phone: null` có thể mang nghĩa xóa số điện thoại hoặc đặt giá trị thành chưa biết, tùy hợp đồng API.

Nếu yêu cầu gửi:

```json
{
  "email": "mai.new@example.test",
  "phone": ""
}
```

thì đây là một giá trị chuỗi rỗng; API cần quyết định nó có hợp lệ hay được chuyển thành NULL hoặc từ chối.

Không nên xử lý ba trường hợp này như nhau. Một hàm cập nhật cần kiểm tra cả việc thuộc tính có xuất hiện trong payload hay không và giá trị của nó là gì.

### 3.3. Missing không nhất thiết là lỗi

Một thuộc tính có thể vắng mặt hợp lệ nếu:

- Thuộc tính là tùy chọn.
- Dữ liệu chưa được thu thập.
- Thuộc tính không áp dụng cho loại thực thể đó.
- Bản ghi được tạo bởi phiên bản schema cũ.
- Người gửi không có quyền hoặc không có nguồn dữ liệu cho thuộc tính.

Ngược lại, missing là lỗi nếu trường bắt buộc theo nghiệp vụ hoặc hợp đồng giao tiếp. Vì vậy, phải phân biệt “không bắt buộc” với “bắt buộc nhưng chưa gửi”.

## 4. Giá trị rỗng (empty)

### 4.1. Chuỗi rỗng khác NULL

Chuỗi rỗng `''` là một chuỗi có độ dài bằng 0. Nó vẫn là một giá trị chuỗi:

```sql
SELECT
    LENGTH('') AS empty_length,
    LENGTH('abc') AS text_length;
```

Trong nhiều hệ quản trị, chuỗi rỗng khác NULL. Ví dụ, với PostgreSQL:

```sql
SELECT '' IS NULL;  -- FALSE
SELECT NULL IS NULL; -- TRUE
```

Điều đó có nghĩa một cột `VARCHAR NOT NULL` vẫn có thể chứa chuỗi rỗng, trừ khi có thêm constraint kiểm tra độ dài hoặc nội dung.

Ví dụ, nếu mã SKU không được rỗng:

```sql
CREATE TABLE product (
    product_id BIGINT PRIMARY KEY,
    sku VARCHAR(50) NOT NULL CHECK (LENGTH(TRIM(sku)) > 0)
);
```

`NOT NULL` chỉ ngăn NULL; nó không tự ngăn chuỗi rỗng hoặc chuỗi chỉ có khoảng trắng.

**Lưu ý theo hệ quản trị:** Oracle Database coi chuỗi ký tự có độ dài bằng 0 trong các kiểu ký tự như NULL trong nhiều ngữ cảnh SQL. Vì vậy, không nên giả định mọi engine phân biệt `''` và NULL giống nhau. Hãy kiểm tra semantics của hệ quản trị mục tiêu.

### 4.2. Mảng rỗng và NULL

Với trường lưu danh sách, mảng rỗng `[]` có nghĩa danh sách đã biết và hiện không có phần tử. NULL có thể có nghĩa chưa biết danh sách, chưa tải hoặc không áp dụng.

Ví dụ document:

```json
{
  "customerId": 1001,
  "tags": []
}
```

Khác với:

```json
{
  "customerId": 1001,
  "tags": null
}
```

Và khác với trường hợp không có `tags`:

```json
{
  "customerId": 1001
}
```

Ba trạng thái có thể được diễn giải như sau:

| Trạng thái | Ý nghĩa có thể có |
|---|---|
| `tags: []` | Đã biết danh sách và hiện không có tag |
| `tags: null` | Danh sách chưa biết hoặc không áp dụng |
| Không có `tags` | Chưa cung cấp hoặc trường không tồn tại trong phiên bản document |

Nếu nghiệp vụ không cần phân biệt các trường hợp, có thể chuẩn hóa chúng về một cách biểu diễn. Nhưng nếu cần biết “đã xác nhận không có tag” khác “chưa tải tag”, phải giữ thông tin đó.

### 4.3. Đối tượng rỗng và đối tượng vắng mặt

Một đối tượng JSON rỗng `{}` là một object đã tồn tại nhưng không có thuộc tính con:

```json
{
  "address": {}
}
```

Điều này khác với `"address": null` hoặc không có trường `address`. Object rỗng có thể có nghĩa hồ sơ địa chỉ đã được khởi tạo nhưng chưa có thành phần nào; null có thể có nghĩa không có địa chỉ; missing có thể có nghĩa chưa cung cấp thông tin.

Nếu mô hình document cho phép cấu trúc lồng nhau, cần quy định rõ ý nghĩa của object rỗng, object null và object bị bỏ qua.

## 5. Giá trị mặc định (default)

### 5.1. Default là quy tắc cấp giá trị khi ghi

Giá trị mặc định là giá trị hệ thống sử dụng khi thao tác ghi không cung cấp giá trị theo cách mà schema hoặc ứng dụng quy định.

Ví dụ trong SQL:

```sql
CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Nếu câu lệnh INSERT bỏ qua `status` và `created_at`, hệ quản trị áp dụng default:

```sql
INSERT INTO orders (order_id)
VALUES (7001);
```

Kết quả sẽ có `status = 'PENDING'` và `created_at` được gán thời điểm hiện tại theo semantics của engine.

### 5.2. Default không tự thay thế NULL được gửi tường minh

Một điểm thường bị hiểu nhầm: SQL DEFAULT thường được áp dụng khi cột bị bỏ qua trong INSERT hoặc khi dùng từ khóa `DEFAULT`, không phải khi gửi NULL tường minh.

Ví dụ:

```sql
INSERT INTO orders (order_id, status)
VALUES (7002, NULL);
```

Vì `status` được khai báo `NOT NULL`, câu lệnh trên sẽ vi phạm ràng buộc. Default `'PENDING'` không tự động thay thế NULL.

Nếu muốn yêu cầu hệ quản trị dùng default, có thể viết:

```sql
INSERT INTO orders (order_id, status)
VALUES (7003, DEFAULT);
```

Quy tắc chính xác có thể khác theo hệ quản trị, nhưng không nên giả định NULL và DEFAULT là một.

### 5.3. Default khác giá trị được người dùng chọn

Giả sử `status` mặc định là `'PENDING'`. Khi bản ghi được tạo mà người dùng không gửi trạng thái, hệ thống có thể dùng default. Nhưng nếu người dùng chủ động chọn `'CANCELLED'`, hệ thống phải lưu lựa chọn đó.

Nếu ứng dụng tự động thay mọi giá trị rỗng hoặc NULL thành `'PENDING'`, nó có thể ghi đè ý định của người dùng. Cần quy định rõ các trường hợp:

- Không gửi trường: dùng default hay báo thiếu?
- Gửi NULL: cho phép, từ chối hay chuyển thành default?
- Gửi chuỗi rỗng: lưu rỗng hay từ chối?
- Gửi một giá trị cụ thể: lưu giá trị đó nếu hợp lệ?

### 5.4. Default khi UPDATE

Default không tự chạy lại mỗi khi cập nhật một hàng. Ví dụ, nếu `status` đã là `'SHIPPED'`, một câu lệnh UPDATE không nhắc đến `status` sẽ giữ nguyên giá trị đó.

Muốn đặt lại default, có thể dùng cú pháp `SET status = DEFAULT` nếu hệ quản trị hỗ trợ:

```sql
UPDATE orders
SET status = DEFAULT
WHERE order_id = 7001;
```

Một số hệ thống ứng dụng có thể tự áp dụng default khi tạo object hoặc khi deserialize payload. Đó là hành vi ở tầng ứng dụng và cần được phân biệt với default do database thực thi.

### 5.5. Default không phải lúc nào cũng phù hợp

Default hữu ích khi có giá trị khởi tạo rõ ràng và an toàn, ví dụ:

- Trạng thái đơn hàng mới là `PENDING`.
- Thời điểm tạo là thời điểm ghi nhận.
- Số lần thử lại ban đầu bằng 0.
- Cờ bật/tắt có giá trị khởi tạo được nghiệp vụ thống nhất.

Không nên dùng default để che giấu dữ liệu bắt buộc bị thiếu. Ví dụ, tự điền `'Unknown'` vào tên khách hàng có thể tạo dữ liệu giả, làm sai báo cáo và khiến hệ thống tưởng rằng đã thu thập được tên.

## 6. So sánh bốn trạng thái

| Trạng thái | SQL quan hệ | JSON/document | Ý nghĩa điển hình |
|---|---|---|---|
| NULL | `NULL` | `"field": null` | Có marker biểu thị không có/không xác định |
| Missing | Không có khái niệm cột bị thiếu trong hàng quan hệ thông thường; cột vẫn tồn tại và có thể NULL | Không có thuộc tính | Không được cung cấp hoặc không tồn tại trong cấu trúc document |
| Empty | `''`, mảng rỗng nếu kiểu hỗ trợ | `""`, `[]`, `{}` | Giá trị có tồn tại nhưng không chứa ký tự/phần tử/thuộc tính |
| Default | `DEFAULT` hoặc bỏ cột khi INSERT | Do schema, ODM hoặc ứng dụng áp dụng | Giá trị khởi tạo theo quy tắc |

Cần chú ý: trong bảng quan hệ, mọi hàng có cùng tập cột theo schema. Vì vậy “missing column” không giống missing property của document. Một hàng quan hệ thường biểu diễn giá trị chưa có bằng NULL, còn việc một cột không tồn tại là thay đổi schema chứ không phải trạng thái riêng của từng hàng.

## 7. Thiết kế thuộc tính tùy chọn và bắt buộc

### 7.1. Xác định thuộc tính có bắt buộc không

Trước khi khai báo NULL hoặc NOT NULL, hãy hỏi:

- Giá trị có cần thiết để hoàn tất nghiệp vụ không?
- Có thể tạo thực thể trước khi biết giá trị này không?
- Giá trị có thể không áp dụng với một số loại thực thể không?
- Có thể bổ sung giá trị sau không?
- Việc thiếu giá trị có ảnh hưởng đến báo cáo, quyền truy cập hoặc quy trình khác không?

Ví dụ:

```sql
CREATE TABLE customer (
    customer_id BIGINT PRIMARY KEY,
    full_name VARCHAR(200) NOT NULL,
    email VARCHAR(320),
    middle_name VARCHAR(100),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

- `full_name` bắt buộc.
- `email` và `middle_name` có thể NULL theo mô hình minh họa.
- `created_at` bắt buộc và có default khi tạo.

Nếu email bắt buộc để đăng ký, cần đổi sang NOT NULL và có thể thêm xác minh ở tầng nghiệp vụ. Không nên để NULL chỉ vì một số dữ liệu nhập cũ đang thiếu mà không xác định chính sách chuyển đổi.

### 7.2. Phân biệt chưa biết, không áp dụng và chưa thu thập

Nếu nghiệp vụ cần phân biệt nhiều lý do không có giá trị, có thể thêm trường trạng thái:

```sql
CREATE TABLE customer_profile (
    customer_id BIGINT PRIMARY KEY,
    middle_name VARCHAR(100),
    middle_name_status VARCHAR(20) NOT NULL,
    CHECK (
        middle_name_status IN (
            'KNOWN',
            'NOT_PROVIDED',
            'NOT_APPLICABLE',
            'NOT_COLLECTED'
        )
    )
);
```

Mô hình này cho biết vì sao tên đệm không có. Tuy nhiên, cần bổ sung constraint hoặc quy tắc ứng dụng để bảo đảm trạng thái và giá trị nhất quán. Ví dụ, `KNOWN` phải đi cùng một giá trị hợp lệ; `NOT_APPLICABLE` có thể yêu cầu giá trị NULL.

Không nên tạo quá nhiều cột trạng thái nếu nghiệp vụ không sử dụng chúng. Chỉ mô hình hóa khác biệt có ý nghĩa đối với quyết định hoặc báo cáo.

### 7.3. Tránh sentinel values

Sentinel value là một giá trị đặc biệt được dùng thay cho trạng thái thiếu, ví dụ:

- `0` để biểu thị chưa biết số lượng.
- `-1` để biểu thị không có ID.
- `1900-01-01` để biểu thị ngày chưa biết.
- `'N/A'` hoặc `'UNKNOWN'` để biểu thị chuỗi thiếu.

Cách này có thể gây lỗi vì giá trị sentinel vẫn là dữ liệu bình thường theo kiểu dữ liệu. Nó có thể tham gia tính toán, sắp xếp, lọc hoặc báo cáo như một giá trị thật.

Hãy dùng NULL, trạng thái riêng hoặc cấu trúc phù hợp với semantics. Chỉ dùng sentinel khi đó thực sự là một giá trị nghiệp vụ hợp lệ và được định nghĩa rõ.

## 8. NULL, missing và default trong API

### 8.1. Phân biệt POST, PUT và PATCH

Các API cần quy định rõ ý nghĩa của việc thiếu trường và gửi NULL.

Một hợp đồng thường gặp:

| Payload | Ý nghĩa có thể được quy định |
|---|---|
| POST không gửi trường có default | Tạo mới và áp dụng default |
| POST không gửi trường bắt buộc | Từ chối vì thiếu dữ liệu |
| PATCH không gửi trường | Giữ nguyên giá trị hiện tại |
| PATCH gửi `null` | Xóa giá trị hoặc đặt thành chưa biết |
| PATCH gửi `""` | Đặt chuỗi rỗng nếu được phép |
| PUT thiếu trường | Có thể xem là thay thế toàn bộ representation; cần quy định rõ giá trị bị bỏ qua sẽ mất hay được default |

Không có một semantics duy nhất cho mọi API. Hợp đồng phải nói rõ hành vi, đặc biệt khi client cũ và mới cùng hoạt động.

### 8.2. Ví dụ xử lý PATCH

Giả sử hồ sơ có `displayName` và `phone`. Một yêu cầu PATCH chỉ gửi `displayName`:

```json
{
  "displayName": "Mai Nguyen"
}
```

Hệ thống giữ nguyên `phone`.

Nếu gửi:

```json
{
  "displayName": "Mai Nguyen",
  "phone": null
}
```

Hệ thống xóa hoặc đặt phone thành chưa biết theo hợp đồng.

Nếu gửi:

```json
{
  "displayName": "Mai Nguyen",
  "phone": ""
}
```

Hệ thống cần kiểm tra chuỗi rỗng có hợp lệ hay không.

Ở tầng code, cần kiểm tra sự hiện diện của thuộc tính trong payload trước khi đọc giá trị. Nếu chỉ deserialize mọi trường vắng mặt thành null, hệ thống sẽ không phân biệt được “không cập nhật trường” với “xóa giá trị”.

### 8.3. Default ở API và default ở database

Một ứng dụng có thể áp dụng default trước khi gửi INSERT, trong khi database cũng có default riêng. Nếu hai nơi khác nhau, kết quả có thể không nhất quán.

Ví dụ, database mặc định `status = 'PENDING'`, nhưng ứng dụng mặc định `status = 'NEW'`. Các đường ghi khác nhau có thể tạo ra trạng thái khác nhau tùy việc có gửi cột hay không.

Nên xác định một nguồn có thẩm quyền cho từng default. Có thể dùng database default để bảo vệ các đường ghi trực tiếp và ứng dụng dùng cùng một quy tắc để phản hồi nhất quán. Tài liệu schema và API cần được đồng bộ.

## 9. Ảnh hưởng đến truy vấn, constraint và chỉ mục

### 9.1. NOT NULL và CHECK

`NOT NULL` ngăn giá trị NULL nhưng không tự ngăn chuỗi rỗng:

```sql
CREATE TABLE category (
    category_id BIGINT PRIMARY KEY,
    category_name VARCHAR(100) NOT NULL
        CHECK (LENGTH(TRIM(category_name)) > 0)
);
```

Một lưu ý quan trọng: trong SQL, CHECK thường chỉ loại hàng khi biểu thức trả về FALSE; biểu thức UNKNOWN do NULL có thể không bị coi là vi phạm. Vì vậy, nếu trường bắt buộc phải có giá trị, cần kết hợp `NOT NULL` với CHECK phù hợp.

Ví dụ, `CHECK (quantity > 0)` không nhất thiết ngăn NULL nếu cột vẫn cho phép NULL. Hãy khai báo:

```sql
quantity INTEGER NOT NULL CHECK (quantity > 0)
```

### 9.2. UNIQUE và NULL

Cách unique constraint xử lý nhiều NULL phụ thuộc hệ quản trị và tùy chọn. Một số engine cho phép nhiều hàng NULL trong cột unique; engine hoặc cú pháp khác có thể hỗ trợ semantics NULLS NOT DISTINCT.

Nếu nghiệp vụ yêu cầu mỗi hàng phải có giá trị và không trùng, hãy dùng cả `NOT NULL` và `UNIQUE`. Nếu NULL được phép, cần xác định nhiều bản ghi thiếu giá trị có được chấp nhận hay không.

### 9.3. Truy vấn tìm dữ liệu thiếu

Có thể dùng `IS NULL` để tìm giá trị chưa có:

```sql
SELECT customer_id
FROM customer
WHERE email IS NULL;
```

Để tìm chuỗi rỗng hoặc chỉ chứa khoảng trắng:

```sql
SELECT customer_id
FROM customer
WHERE email = ''
   OR TRIM(email) = '';
```

Cú pháp hàm độ dài, trim và xử lý chuỗi có thể khác nhau theo engine. Trong các hệ thống có nhiều nguồn dữ liệu, nên thống kê riêng NULL, chuỗi rỗng, chuỗi chỉ có khoảng trắng và trường vắng mặt trong document để hiểu chất lượng dữ liệu.

## 10. Di chuyển schema và dữ liệu khi thay đổi semantics

Khi thay đổi một thuộc tính từ nullable sang NOT NULL hoặc bổ sung default, cần xem xét dữ liệu hiện có.

Quy trình an toàn thường gồm:

1. Thống kê số hàng NULL, chuỗi rỗng và giá trị sentinel hiện tại.
2. Xác nhận với nghiệp vụ giá trị thay thế nào là đúng.
3. Xác định default có thật sự đại diện cho dữ liệu lịch sử hay chỉ áp dụng cho bản ghi mới.
4. Backfill dữ liệu cũ theo quy tắc đã được duyệt.
5. Kiểm tra không còn bản ghi vi phạm.
6. Thêm constraint hoặc đổi nullability.
7. Cập nhật API, ứng dụng, ETL và tài liệu.
8. Theo dõi lỗi từ các client cũ vẫn gửi payload theo semantics trước đây.

Không nên tự động thay toàn bộ NULL thành chuỗi rỗng hoặc giá trị mặc định. Ví dụ, đổi mọi `email IS NULL` thành `'unknown@example.test'` sẽ tạo ra một giá trị giả có thể bị xem như email thật và có thể vi phạm unique constraint.

Default mới thường áp dụng cho các lần ghi mới sau khi schema thay đổi. Nó không có nghĩa dữ liệu cũ tự động được điền, trừ khi dùng thao tác backfill hoặc cú pháp migration cụ thể.

## 11. Ví dụ tổng hợp: hồ sơ sản phẩm

Giả sử một sản phẩm có các thuộc tính `description`, `tags`, `weight` và `status`.

| Trường | Trạng thái | Ý nghĩa |
|---|---|---|
| `description = NULL` | NULL | Mô tả chưa biết hoặc chưa có |
| Không có `description` trong document | Missing | Nguồn không gửi hoặc schema cũ chưa có trường |
| `description = ""` | Empty string | Mô tả đã được gửi nhưng rỗng |
| `tags = []` | Empty collection | Đã xác nhận sản phẩm chưa có tag |
| `tags = null` | NULL | Danh sách tag chưa biết hoặc không áp dụng |
| Không có `tags` | Missing | Trường tag chưa được cung cấp |
| `weight = 0` | Giá trị số | Khối lượng bằng 0 theo đơn vị đã chọn; chỉ hợp lệ nếu nghiệp vụ cho phép |
| Không gửi `status` khi tạo | Default | Áp dụng trạng thái mặc định, ví dụ `DRAFT` |
| `status = null` | NULL tường minh | Bị từ chối nếu status là NOT NULL |

Một document minh họa:

```json
{
  "productId": "P-100",
  "description": "",
  "tags": [],
  "weight": null,
  "status": "DRAFT"
}
```

Ở đây, mô tả được cung cấp nhưng rỗng; danh sách tag đã được xác nhận là rỗng; trọng lượng chưa có; trạng thái đã được đặt rõ. Nếu document bỏ trường `weight`, hệ thống có thể hiểu là chưa gửi trọng lượng. Việc hai trường hợp cuối có khác nhau hay không phải do hợp đồng dữ liệu quy định.

## 12. Quy trình xác định semantics cho từng thuộc tính

Với mỗi thuộc tính trong mô hình, hãy trả lời theo thứ tự:

1. **Có bắt buộc không?** Nếu bắt buộc, xác định điều kiện và thời điểm bắt buộc.
2. **Khi không có giá trị, lý do là gì?** Chưa biết, không áp dụng, chưa thu thập, bị ẩn hay người dùng chủ động xóa?
3. **Có trạng thái missing không?** Đặc biệt trong document, event và API cập nhật một phần.
4. **Giá trị rỗng có hợp lệ không?** Với chuỗi, mảng, object và tập hợp cần quy định riêng.
5. **Có default không?** Xác định default do database, ứng dụng hay nguồn dữ liệu cung cấp.
6. **NULL có được phép không?** Nếu có, mô tả ý nghĩa và cách truy vấn.
7. **Các constraint cần có là gì?** NOT NULL, CHECK, UNIQUE, độ dài, miền giá trị hoặc quy tắc liên quan.
8. **Khi cập nhật thì sao?** Missing giữ nguyên, NULL xóa, empty đặt rỗng hay có semantics khác?
9. **Khi đồng bộ và nhập dữ liệu thì sao?** Bảo toàn khác biệt giữa nguồn không gửi, nguồn gửi NULL và nguồn gửi giá trị rỗng.
10. **Khi báo cáo thì sao?** Xác định cách đếm, tính trung bình, lọc và thay thế NULL nếu cần.

Nên ghi các câu trả lời trong từ điển dữ liệu hoặc hợp đồng schema để người viết API, ETL, báo cáo và truy vấn dùng cùng một cách hiểu.

## 13. Những lỗi thường gặp

- Coi NULL, chuỗi rỗng, số 0 và trường missing là cùng một trạng thái.
- Dùng `= NULL` thay vì `IS NULL`.
- Nghĩ rằng `NOT NULL` sẽ tự ngăn chuỗi rỗng.
- Nghĩ rằng SQL DEFAULT sẽ thay thế mọi NULL được gửi tường minh.
- Chuyển mọi giá trị thiếu thành 0 hoặc "N/A" mà không xác nhận ý nghĩa.
- Không phân biệt missing với null trong payload PATCH.
- Ghi đè dữ liệu hiện có bằng NULL khi client chỉ bỏ qua trường.
- Để default ở ứng dụng và database khác nhau.
- Cho rằng mọi hệ quản trị xử lý chuỗi rỗng và NULL giống nhau.
- Không xem xét cách COUNT, AVG, SUM và CHECK xử lý NULL.
- Thêm NOT NULL vào schema mà chưa backfill và kiểm tra dữ liệu lịch sử.
- Không ghi rõ liệu mảng rỗng nghĩa là “đã xác nhận không có phần tử” hay “chưa tải dữ liệu”.

## 14. Checklist kiểm chứng

Trước khi hoàn tất mô hình thuộc tính, hãy xác nhận:

- [ ] Đã phân biệt NULL, missing, empty và default.
- [ ] Ý nghĩa nghiệp vụ của NULL được ghi rõ.
- [ ] Đã xác định thuộc tính bắt buộc hay tùy chọn.
- [ ] Chuỗi rỗng, khoảng trắng, mảng rỗng và object rỗng có semantics rõ ràng.
- [ ] Default được áp dụng ở đúng tầng và đúng thời điểm.
- [ ] Đã xác định hành vi khi INSERT bỏ cột, gửi NULL hoặc gửi DEFAULT.
- [ ] Đã xác định hành vi khi UPDATE/PATCH bỏ trường, gửi NULL hoặc gửi empty.
- [ ] Truy vấn dùng IS NULL/IS NOT NULL và hiểu logic ba giá trị.
- [ ] CHECK, NOT NULL và UNIQUE được kết hợp đúng.
- [ ] Khác biệt theo hệ quản trị, đặc biệt với chuỗi rỗng và NULL, đã được kiểm tra.
- [ ] Migration có kế hoạch backfill và xử lý dữ liệu lịch sử.
- [ ] API, ETL, báo cáo và database dùng chung một semantics.

Phân biệt rõ NULL, dữ liệu vắng mặt, giá trị rỗng và giá trị mặc định giúp mô hình dữ liệu bảo toàn ý nghĩa của thông tin qua các bước tạo, cập nhật, đồng bộ và phân tích. Khi mỗi trạng thái có định nghĩa nhất quán, hệ thống tránh được việc biến “chưa biết” thành “không có”, hoặc biến “không gửi” thành “xóa dữ liệu”.


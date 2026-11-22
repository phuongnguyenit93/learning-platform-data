# Chỉ mục duy nhất: ràng buộc dữ liệu và ảnh hưởng đến thực thi

Một hệ thống thường cần bảo đảm một số giá trị chỉ xuất hiện một lần: mã tài khoản, email đăng nhập, số hóa đơn hoặc mã giao dịch bên ngoài. Kiểm tra trùng lặp ở tầng ứng dụng có thể cải thiện trải nghiệm, nhưng không đủ để bảo vệ dữ liệu khi nhiều yêu cầu chạy đồng thời hoặc khi có nhiều ứng dụng cùng ghi vào cơ sở dữ liệu. Cơ sở dữ liệu cần thực thi quy tắc duy nhất ngay tại nơi lưu trữ dữ liệu.

**Chỉ mục duy nhất** (*unique index*) là cấu trúc chỉ mục đồng thời bảo đảm các khóa theo định nghĩa của chỉ mục không trùng nhau. **Ràng buộc duy nhất** (*unique constraint*) là quy tắc toàn vẹn dữ liệu do schema khai báo; nhiều hệ quản trị triển khai ràng buộc này bằng một chỉ mục duy nhất. Ngoài vai trò ngăn dữ liệu trùng, chỉ mục duy nhất còn giúp bộ tối ưu biết một điều kiện tìm kiếm có thể trả về tối đa một hàng, từ đó ảnh hưởng đến ước lượng số hàng, lựa chọn join và kế hoạch thực thi.

Trong module **DATABASE_PERFORMANCE**, cần hiểu cách thiết kế chỉ mục duy nhất phù hợp với quy tắc nghiệp vụ, cách cơ sở dữ liệu xử lý ghi đồng thời, và tác động của chỉ mục lên cả đọc lẫn ghi. Một chỉ mục duy nhất đúng giúp bảo vệ dữ liệu và hỗ trợ truy vấn; một chỉ mục đặt sai phạm vi hoặc thiếu hiểu biết về `NULL`, collation và khóa ghép có thể gây lỗi nghiệp vụ hoặc tăng chi phí vận hành.

## 1. Phân biệt unique constraint và unique index

Hai khái niệm liên quan chặt chẽ nhưng mục đích khai báo khác nhau:

| Thành phần | Mục đích chính | Ví dụ sử dụng |
|---|---|---|
| `UNIQUE` constraint | Khai báo quy tắc toàn vẹn: các giá trị hoặc tổ hợp cột không được trùng theo ngữ nghĩa hệ quản trị | Mỗi tài khoản có một email đăng nhập duy nhất |
| Unique index | Tạo cấu trúc truy cập và đồng thời từ chối khóa trùng | Tăng tốc tra cứu theo mã khách hàng và bảo đảm mã không lặp |

Khi dùng ràng buộc `UNIQUE`, hệ quản trị thường tạo hoặc sử dụng một chỉ mục duy nhất để thực thi. Trong một số nền tảng, unique index có thể được tạo trực tiếp mà không khai báo constraint; một số khả năng như chỉ mục lọc hoặc chỉ mục biểu thức cũng có thể không tương đương hoàn toàn với constraint thông thường.

Hãy chọn cách khai báo theo ý nghĩa dữ liệu. Nếu đây là quy tắc nghiệp vụ bắt buộc của bảng, constraint thường diễn đạt ý định rõ ràng trong schema. Nếu cần một chỉ mục duy nhất có điều kiện hoặc dựa trên biểu thức, có thể cần dùng unique index theo tính năng của hệ quản trị.

### Ví dụ ràng buộc email duy nhất

```sql
CREATE TABLE customer_account (
    account_id   BIGINT PRIMARY KEY,
    email        VARCHAR(320) NOT NULL,
    display_name VARCHAR(200),
    CONSTRAINT uq_customer_account_email UNIQUE (email)
);
```

Ràng buộc này bảo đảm không có hai hàng có cùng giá trị `email` theo quy tắc so sánh của kiểu dữ liệu, collation và hệ quản trị. `NOT NULL` thể hiện rằng email bắt buộc phải có; `UNIQUE` tự nó không phải lúc nào cũng đồng nghĩa với `NOT NULL`.

Nếu bảng đã tồn tại, có thể thêm constraint sau khi dữ liệu được làm sạch:

```sql
ALTER TABLE customer_account
ADD CONSTRAINT uq_customer_account_email UNIQUE (email);
```

Lệnh có thể thất bại nếu dữ liệu hiện tại có các giá trị trùng hoặc không đáp ứng quy tắc của hệ quản trị. Trước khi triển khai, cần kiểm tra dữ liệu, thời gian xây chỉ mục, khóa phát sinh và tác động lên workload.

## 2. Cơ sở dữ liệu thực thi tính duy nhất như thế nào?

Một B-tree index thường lưu khóa theo thứ tự và liên kết khóa với vị trí hàng. Với unique index, hệ quản trị kiểm tra rằng khóa mới không xung đột với khóa đã tồn tại theo ngữ nghĩa so sánh của chỉ mục.

Khi thêm hoặc cập nhật hàng, cơ sở dữ liệu phải kiểm tra tính duy nhất như một phần của thao tác ghi. Việc kiểm tra cần đúng ngay cả khi nhiều transaction đồng thời cố gắng ghi cùng một khóa. Chỉ thực hiện câu `SELECT` kiểm tra trước khi `INSERT` ở ứng dụng không thể bảo đảm điều này: hai transaction có thể cùng đọc thấy chưa tồn tại rồi cùng thử chèn.

Ví dụ tình huống cạnh tranh:

1. Transaction A kiểm tra email `a@example.test`, chưa thấy hàng nào.
2. Transaction B cũng kiểm tra email đó và chưa thấy hàng nào.
3. A chèn tài khoản với email này.
4. B cố chèn cùng email.
5. Cơ sở dữ liệu phải cho phép tối đa một thao tác thành công; thao tác còn lại chờ, nhận lỗi vi phạm duy nhất hoặc được xử lý theo cơ chế xung đột của hệ quản trị.

Do đó, kiểm tra ở ứng dụng chỉ phục vụ thông báo sớm. Constraint hoặc unique index ở cơ sở dữ liệu mới là lớp bảo vệ cuối cùng. Ứng dụng vẫn phải bắt và xử lý lỗi trùng có thể xảy ra giữa bước kiểm tra và bước ghi.

### Khóa và đồng thời

Để ngăn hai transaction cùng tạo một khóa, hệ quản trị có thể dùng khóa trên chỉ mục, cơ chế kiểm tra xung đột, đồng bộ nội bộ hoặc kết hợp các cơ chế này. Chi tiết phụ thuộc storage engine, isolation level, loại chỉ mục và nền tảng.

Khi nhiều transaction ghi cùng một giá trị hoặc vùng khóa gần nhau, chúng có thể chờ nhau. Vì vậy, unique index có thể tạo ra các điểm nóng nếu workload thường xuyên tranh cùng một khóa, chẳng hạn bộ đếm hoặc mã được sinh không hợp lý. Tuy nhiên, chi phí kiểm tra tính duy nhất là cần thiết để bảo đảm toàn vẹn dữ liệu; cần thiết kế cách phân phối khóa và xử lý retry phù hợp thay vì bỏ quy tắc duy nhất.

## 3. Chỉ mục duy nhất trên một cột và nhiều cột

### Unique index trên một cột

Chỉ mục duy nhất một cột phù hợp với thuộc tính phải duy nhất toàn bảng, ví dụ mã đăng nhập hoặc mã định danh do hệ thống cấp:

```sql
CREATE UNIQUE INDEX ux_customer_external_id
ON customer_account (external_id);
```

Nếu `external_id` phải luôn có giá trị, cần khai báo `NOT NULL` riêng. Nếu nghiệp vụ cho phép thiếu giá trị, hãy tìm hiểu chính xác cách hệ quản trị xử lý nhiều `NULL` trong unique index.

### Unique index ghép

Nhiều quy tắc duy nhất chỉ có ý nghĩa trong một phạm vi. Ví dụ, mã sản phẩm chỉ cần duy nhất trong từng cửa hàng:

```sql
CREATE TABLE store_product (
    store_id   BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    sku        VARCHAR(80) NOT NULL,
    name       VARCHAR(200),
    CONSTRAINT uq_store_product_sku UNIQUE (store_id, sku)
);
```

Khóa duy nhất là tổ hợp `(store_id, sku)`. Hai cửa hàng khác nhau có thể dùng cùng một SKU, nhưng cùng một cửa hàng không được có hai hàng có cùng SKU.

Thứ tự cột trong unique index ghép có ý nghĩa đối với khả năng truy cập. Chỉ mục `(store_id, sku)` thường hỗ trợ tìm theo `store_id` hoặc theo cả `store_id` và `sku`; nó thường không tối ưu cho điều kiện chỉ lọc `sku` mà thiếu `store_id`, tùy hệ quản trị và kế hoạch. Quy tắc duy nhất vẫn áp dụng trên toàn bộ tổ hợp khóa, không chỉ cột đầu tiên.

Hãy thiết kế thứ tự cột theo cả quy tắc nghiệp vụ và workload truy vấn. Nếu cần tìm SKU toàn cục, đó là một truy vấn hoặc quy tắc khác, có thể cần một chỉ mục khác hoặc một constraint riêng.

### Tính duy nhất theo biểu thức

Đôi khi nghiệp vụ yêu cầu so sánh sau khi chuẩn hóa. Ví dụ, email không phân biệt chữ hoa/chữ thường hoặc mã có khoảng trắng đầu cuối. Có thể dùng collation không phân biệt hoa thường, cột chuẩn hóa hoặc unique index trên biểu thức nếu hệ quản trị hỗ trợ.

Ví dụ khái niệm trên nền tảng hỗ trợ chỉ mục biểu thức:

```sql
CREATE UNIQUE INDEX ux_customer_email_normalized
ON customer_account (LOWER(TRIM(email)));
```

Đây là cú pháp được hỗ trợ ở một số hệ quản trị như PostgreSQL; không nên giả định mọi hệ quản trị chấp nhận cùng cú pháp. Trong nền tảng khác, có thể cần cột sinh (*generated column*), cột chuẩn hóa do ứng dụng quản lý hoặc collation phù hợp.

Điều quan trọng là định nghĩa chuẩn hóa phải nhất quán giữa lúc ghi, lúc tìm kiếm và lúc kiểm tra dữ liệu cũ. Nếu chỉ mục dùng `LOWER(email)` nhưng truy vấn dùng quy tắc chuẩn hóa khác, kết quả có thể không như mong đợi. Cũng cần xác định quy tắc Unicode, dấu, khoảng trắng và collation của ngôn ngữ.

## 4. `NULL`, collation và quy tắc so sánh

`NULL` biểu thị giá trị chưa biết hoặc không có; nó không giống một chuỗi rỗng. Cách xử lý `NULL` trong unique constraint/index có khác biệt giữa hệ quản trị, và một số nền tảng có tùy chọn thay đổi hành vi.

| Hệ quản trị | Hành vi phổ biến của unique constraint/index với `NULL` |
|---|---|
| PostgreSQL | Mặc định các `NULL` được xem là khác nhau cho mục đích unique, nên có thể có nhiều hàng `NULL`; phiên bản hỗ trợ `NULLS NOT DISTINCT` cho phép xem chúng như trùng |
| SQL Server | Unique index thông thường coi `NULL` như một giá trị khóa; với một cột thường chỉ cho phép một `NULL`. Có thể dùng filtered unique index để chỉ áp dụng cho hàng có giá trị |
| MySQL | Unique index cho phép nhiều `NULL`, vì các giá trị `NULL` không được xem là bằng nhau trong kiểm tra này |
| Oracle Database | Unique constraint thông thường cho phép nhiều `NULL` ở cột đơn; với khóa ghép, cách xử lý phụ thuộc tổ hợp giá trị null và quy tắc của Oracle |

Đây là hành vi phổ biến, cần xác nhận theo phiên bản và loại chỉ mục cụ thể. Không nên chuyển schema giữa các hệ quản trị mà không kiểm thử dữ liệu `NULL`.

Nếu nghiệp vụ yêu cầu chỉ một hàng được phép thiếu giá trị, có thể cần `NOT NULL`, một chỉ mục lọc/partial hoặc một cách biểu diễn khác. Ví dụ trên PostgreSQL, unique partial index có thể chỉ áp dụng cho hàng có email:

```sql
CREATE UNIQUE INDEX ux_customer_email_present
ON customer_account (email)
WHERE email IS NOT NULL;
```

Trong SQL Server, có thể dùng filtered unique index tương tự về mục đích:

```sql
CREATE UNIQUE INDEX ux_customer_email_present
ON dbo.CustomerAccount (email)
WHERE email IS NOT NULL;
```

Partial/filtered unique index hữu ích khi quy tắc chỉ áp dụng cho một tập con hàng, ví dụ chỉ một bản ghi đang hoạt động cho mỗi người dùng. Khả năng và cú pháp khác nhau theo hệ quản trị. MySQL không cung cấp partial index theo cú pháp `WHERE` giống PostgreSQL hoặc SQL Server; thường cần thiết kế cột sinh hoặc mô hình dữ liệu khác.

### Collation và tính duy nhất

Chỉ mục duy nhất so sánh khóa theo quy tắc của kiểu dữ liệu và collation. Với collation không phân biệt hoa thường, `User@example.test` và `user@example.test` có thể được coi là cùng một giá trị. Một số collation còn có quy tắc về dấu, ký tự Unicode hoặc khoảng trắng.

Trước khi tạo unique index, hãy xác định hai chuỗi nào được xem là giống nhau theo nghiệp vụ. Không nên dựa vào so sánh chuỗi mặc định của môi trường phát triển, vì production có thể dùng collation khác. Thay đổi collation hoặc quy tắc chuẩn hóa sau này cũng có thể làm phát sinh xung đột giữa những giá trị trước đó được chấp nhận.

## 5. Unique index ảnh hưởng đến kế hoạch thực thi

Unique index vừa là cấu trúc truy cập, vừa cung cấp thông tin về tính duy nhất cho bộ tối ưu. Khi truy vấn lọc bằng toàn bộ khóa duy nhất, bộ tối ưu có thể suy ra số hàng trả về tối đa là một. Điều này ảnh hưởng đến cardinality estimate và lựa chọn thuật toán.

Ví dụ:

```sql
SELECT account_id, display_name
FROM customer_account
WHERE email = ?;
```

Nếu `email` có unique index và kiểu dữ liệu/điều kiện phù hợp, hệ quản trị có thể dùng index seek hoặc index lookup để tìm tối đa một hàng. Chi phí truy cập thường thấp và dễ dự đoán hơn so với quét bảng lớn.

### Tác động đến join

Giả sử `customer_account.account_id` là khóa duy nhất và bảng `orders` lưu `customer_id` tham chiếu đến tài khoản:

```sql
SELECT o.order_id, c.display_name
FROM orders AS o
JOIN customer_account AS c
  ON c.account_id = o.customer_id
WHERE o.order_id = ?;
```

Tính duy nhất của `account_id` cho bộ tối ưu biết mỗi hàng đơn hàng có thể khớp tối đa một tài khoản. Thông tin này giúp ước lượng cardinality join và chọn thứ tự join hoặc thuật toán phù hợp. Nếu điều kiện join không dùng toàn bộ khóa ghép, tính duy nhất của toàn bộ khóa không nhất thiết bảo đảm mỗi hàng chỉ khớp một hàng.

Một số hệ quản trị có thể dùng thông tin constraint để đơn giản hóa hoặc loại bỏ một phần thao tác join trong những trường hợp đáp ứng đầy đủ điều kiện. Khả năng này phụ thuộc hệ quản trị, tính hợp lệ của constraint, nullability, loại join và các điều kiện truy vấn; không nên giả định mọi unique constraint đều làm join bị loại bỏ.

### Unique index không thay thế chỉ mục theo workload

Một unique index chỉ hỗ trợ tốt những truy vấn có điều kiện phù hợp với khóa và thứ tự cột. Nếu truy vấn lọc theo `created_at`, `status` hoặc một cột khác không thuộc chỉ mục, bộ tối ưu vẫn có thể phải quét dữ liệu hoặc dùng chỉ mục khác.

Ngoài ra, unique index có thể không được dùng nếu truy vấn áp dụng hàm hoặc chuyển kiểu lên cột, kiểu tham số không tương thích, collation khác hoặc điều kiện không khớp biểu thức chỉ mục. Hãy kiểm tra actual execution plan thay vì cho rằng có unique index thì mọi truy vấn liên quan đều nhanh.

## 6. Chi phí ghi và bảo trì chỉ mục duy nhất

Mỗi lần `INSERT`, `UPDATE` hoặc `DELETE` tác động đến khóa chỉ mục đều có thể cần cập nhật cấu trúc index và kiểm tra tính duy nhất. Vì vậy, unique index có chi phí:

- **CPU:** tính khóa, tìm vị trí trong cấu trúc chỉ mục và kiểm tra xung đột.
- **I/O:** đọc trang chỉ mục, ghi trang thay đổi và ghi log giao dịch.
- **Bộ nhớ:** trang chỉ mục chiếm buffer cache hoặc bộ nhớ của engine.
- **Đồng thời:** transaction có thể chờ khi tranh cùng khóa hoặc cùng vùng chỉ mục.
- **Dung lượng:** mỗi chỉ mục làm tăng dung lượng lưu trữ và backup.
- **Bảo trì:** rebuild, reorganize, cập nhật thống kê và xử lý phân mảnh tùy nền tảng.

Khi cập nhật cột tham gia unique index, hệ quản trị phải kiểm tra khóa mới và bảo đảm không tạo xung đột. Nếu khóa thay đổi thường xuyên, chi phí ghi có thể đáng kể. Với khóa ghép dài hoặc chứa chuỗi lớn, kích thước chỉ mục và số trang cũng tăng.

### Chọn khóa duy nhất phù hợp

Khóa duy nhất nên ổn định, có quy tắc nghiệp vụ rõ và kích thước hợp lý. Khóa tăng tuần tự có thể tạo điểm ghi tập trung ở một vùng cuối chỉ mục trong một số cấu trúc B-tree, trong khi khóa ngẫu nhiên có thể làm trang phân tán và tăng page split hoặc phân mảnh. Đây là đánh đổi thiết kế, không có một kiểu khóa tốt cho mọi workload.

Nếu cần một định danh nội bộ, có thể dùng surrogate key làm primary key và thêm unique constraint cho khóa nghiệp vụ như email hoặc mã bên ngoài. Cách này tách định danh nội bộ ổn định khỏi quy tắc nghiệp vụ có thể thay đổi, nhưng vẫn cần cân nhắc số lượng chỉ mục và chi phí ghi.

## 7. Xử lý dữ liệu trùng trước khi tạo unique index

Không thể thêm unique constraint thành công nếu dữ liệu hiện có vi phạm quy tắc. Trước khi triển khai, cần xác định chính xác phạm vi trùng, quy tắc chuẩn hóa và cách xử lý các hàng xung đột.

### Tìm nhóm giá trị trùng

Ví dụ tìm email trùng:

```sql
SELECT email, COUNT(*) AS duplicate_count
FROM customer_account
WHERE email IS NOT NULL
GROUP BY email
HAVING COUNT(*) > 1;
```

Nếu quy tắc nghiệp vụ không phân biệt hoa thường hoặc bỏ khoảng trắng, cần nhóm theo biểu thức chuẩn hóa tương ứng. Cú pháp và cách so sánh phải khớp với collation/biểu thức sẽ dùng cho chỉ mục.

### Xác định bản ghi cần giữ

Không nên tự động xóa mọi hàng trùng mà chưa xác định bản ghi chuẩn. Có thể cần:

1. Xác định khóa nghiệp vụ và quy tắc chuẩn hóa.
2. Nhóm các hàng xung đột và xem nguồn tạo dữ liệu.
3. Chọn bản ghi chuẩn theo quy tắc nghiệp vụ, chẳng hạn trạng thái hợp lệ hoặc thời điểm tạo.
4. Hợp nhất các tham chiếu và dữ liệu phụ thuộc sang bản ghi chuẩn.
5. Lưu dấu vết xử lý theo chính sách dữ liệu.
6. Chạy lại truy vấn phát hiện trùng và xác minh không còn vi phạm.

Việc dọn dữ liệu phải được thực hiện trong transaction hoặc quy trình migration có kiểm soát phù hợp với quy mô. Với bảng lớn, thao tác cập nhật/xóa hàng loạt có thể tạo nhiều log, khóa và ảnh hưởng replication.

### Tránh race condition trong quá trình migration

Nếu ứng dụng vẫn tiếp tục ghi trong lúc dọn trùng, một giá trị trùng mới có thể xuất hiện trước khi unique index được tạo. Cần phối hợp cửa sổ ghi, tạm thời áp dụng kiểm tra ở database hoặc dùng chiến lược migration phù hợp với nền tảng. Một lần kiểm tra dữ liệu sạch trước đó không bảo đảm dữ liệu vẫn sạch tại thời điểm tạo chỉ mục.

## 8. Thiết kế unique index có điều kiện

Một số quy tắc nghiệp vụ không yêu cầu duy nhất trên mọi hàng. Ví dụ, mỗi người dùng chỉ có một phiên đăng ký đang hoạt động; các bản ghi đã đóng được phép lặp lịch sử.

Trên nền tảng hỗ trợ partial hoặc filtered index, có thể mô tả quy tắc bằng điều kiện:

```sql
-- Ví dụ PostgreSQL
CREATE UNIQUE INDEX ux_active_subscription_per_user
ON subscription (user_id)
WHERE status = 'ACTIVE';
```

```sql
-- Ví dụ SQL Server
CREATE UNIQUE INDEX ux_active_subscription_per_user
ON dbo.Subscription (user_id)
WHERE status = 'ACTIVE';
```

Chỉ các hàng thỏa điều kiện mới tham gia chỉ mục và quy tắc duy nhất. Khi một hàng chuyển từ `ACTIVE` sang trạng thái khác, khóa của nó được loại khỏi tập chỉ mục; khi hàng khác chuyển sang `ACTIVE`, cơ sở dữ liệu kiểm tra xung đột.

Điều kiện lọc phải phản ánh đúng quy tắc nghiệp vụ và cần được kiểm thử khi cập nhật trạng thái. Nếu truy vấn cần dùng chỉ mục này, điều kiện truy vấn phải tương thích với predicate của chỉ mục theo khả năng nhận diện của bộ tối ưu. Không phải mọi hệ quản trị đều hỗ trợ filtered/partial unique index trực tiếp.

## 9. Triển khai và vận hành trên hệ quản trị khác nhau

Các hệ quản trị đều có cơ chế bảo đảm uniqueness nhưng khác cú pháp, hành vi `NULL`, khả năng tạo chỉ mục online và cách báo lỗi.

| Hệ quản trị | Khả năng thường dùng | Điểm cần xác minh |
|---|---|---|
| PostgreSQL | `UNIQUE` constraint, unique index, partial unique index, expression index; có tùy chọn `NULLS NOT DISTINCT` ở phiên bản hỗ trợ | Hành vi null, concurrent index build, constraint validation và giới hạn của predicate |
| SQL Server | `UNIQUE` constraint, unique index, filtered unique index | Quy tắc một `NULL` trong unique index thường, online index operation theo edition/phiên bản và giới hạn filtered index |
| MySQL/InnoDB | `UNIQUE` constraint/index, index trên generated column để mô hình hóa một số quy tắc | Nhiều `NULL`, giới hạn biểu thức/functional index theo phiên bản và thuật toán DDL |
| Oracle Database | Unique constraint/index, function-based unique index, các tùy chọn tạo/rebuild index | Ngữ nghĩa null, trạng thái constraint, online operation và hành vi khi có dữ liệu lỗi |

Ví dụ tạo unique index trực tiếp trong PostgreSQL:

```sql
CREATE UNIQUE INDEX CONCURRENTLY ux_customer_external_id
ON customer_account (external_id);
```

`CONCURRENTLY` cho phép tạo chỉ mục trong khi vẫn duy trì khả năng ghi thông thường theo cơ chế PostgreSQL, nhưng tốn thêm công việc và có thể để lại index invalid nếu thất bại. Lệnh này có các giới hạn, chẳng hạn không chạy bên trong transaction block thông thường. Cần kiểm tra trạng thái index sau khi thao tác.

Với SQL Server, có thể dùng tùy chọn online khi phiên bản, edition và loại thao tác hỗ trợ. Online không có nghĩa hoàn toàn không có khóa hoặc không phát sinh tác động; vẫn cần theo dõi transaction, tempdb, log và tải.

Với MySQL và Oracle, lựa chọn thuật toán DDL, online operation và mức khóa phụ thuộc phiên bản, engine, loại cột và điều kiện schema. Không nên sao chép cú pháp của hệ quản trị khác hoặc mặc định thao tác luôn không chặn ghi.

### Xử lý lỗi vi phạm duy nhất

Khi hai thao tác tạo cùng khóa, một thao tác có thể thất bại với lỗi duplicate/unique violation. Ứng dụng nên nhận diện loại lỗi theo driver và hệ quản trị, sau đó chuyển thành kết quả nghiệp vụ phù hợp, ví dụ “email đã được sử dụng”. Không nên bắt mọi lỗi SQL rồi coi là trùng, vì lỗi kết nối, deadlock, timeout hoặc lỗi schema cần xử lý khác.

Với thao tác có thể retry, cần phân biệt lỗi xung đột duy nhất với lỗi tạm thời. Retry một thao tác insert đã thất bại do khóa đã tồn tại thường không giải quyết được nguyên nhân; retry có thể phù hợp hơn với deadlock hoặc lỗi kết nối theo chính sách idempotency và transaction của ứng dụng.

## 10. Đo lường ảnh hưởng hiệu năng

Trước và sau khi thêm unique index, cần đo cả truy vấn đọc và workload ghi. Một chỉ mục mới có thể làm tra cứu nhanh hơn nhưng giảm throughput ghi hoặc tăng thời gian commit.

Các chỉ số nên theo dõi:

- **Đọc:** elapsed time, p95/p99, logical reads, physical reads, số hàng ước lượng/thực tế và kế hoạch thực thi.
- **Ghi:** thời gian insert/update/delete, commit latency, transaction throughput và tỷ lệ lỗi uniqueness.
- **Tài nguyên:** CPU, I/O, buffer/cache hit, dung lượng index, transaction log và replication lag.
- **Đồng thời:** lock wait, deadlock, thời gian chờ khóa chỉ mục và số transaction cùng tranh một khóa.
- **Bảo trì:** thời gian tạo/rebuild, lượng log phát sinh, dung lượng tạm và ảnh hưởng đến workload.

Hãy dùng dữ liệu và mức đồng thời gần với production. Kiểm thử cả khóa mới, khóa đã tồn tại, cập nhật khóa, xóa hàng và các giá trị biên. Với unique index ghép, kiểm tra các tổ hợp cột khác nhau và các truy vấn chỉ lọc một phần khóa.

Ví dụ bảng đánh giá trước/sau:

| Chỉ số | Trước unique index | Sau unique index | Cách diễn giải |
|---|---:|---:|---|
| Tra cứu theo email p95 | 45 ms | 4 ms | Có thể đã dùng unique seek |
| Insert mỗi giây | 8.000 | 7.500 | Cần đánh giá chi phí cập nhật chỉ mục |
| Logical reads khi tra cứu | 120 | 3 | Kiểm tra actual plan và cache |
| Lỗi trùng được phát hiện | Không được database bảo vệ | Bị từ chối tại database | Toàn vẹn dữ liệu được bảo đảm |

Các con số chỉ minh họa. Kết quả thực tế phụ thuộc kích thước bảng, cache, phần cứng, loại chỉ mục, phân bố khóa và workload.

## 11. Những sai lầm thường gặp

1. **Chỉ kiểm tra trùng ở ứng dụng:** hai transaction đồng thời vẫn có thể tạo cùng khóa.
2. **Cho rằng `UNIQUE` đồng nghĩa `NOT NULL`:** hành vi null khác nhau giữa hệ quản trị; cần khai báo rõ.
3. **Không kiểm tra collation:** hai chuỗi khác chữ hoa/thường hoặc dấu có thể được coi là giống nhau.
4. **Dùng unique index ghép nhưng hiểu sai phạm vi:** uniqueness áp dụng cho toàn bộ tổ hợp khóa.
5. **Cho rằng unique index ghép hỗ trợ mọi truy vấn trên các cột:** thứ tự khóa ảnh hưởng khả năng tìm kiếm.
6. **Tạo chỉ mục trước khi dọn dữ liệu:** thao tác có thể thất bại hoặc migration gây gián đoạn.
7. **Bỏ qua chi phí ghi:** mỗi thay đổi khóa có thể làm tăng CPU, I/O, log và tranh chấp.
8. **Tạo nhiều chỉ mục duy nhất trùng chức năng:** tăng dung lượng và chi phí bảo trì không cần thiết.
9. **Coi online index build là không có tác động:** vẫn có thể phát sinh khóa, log, I/O và tải bổ sung.
10. **Không xử lý lỗi duplicate riêng:** ứng dụng có thể che mất lỗi thật hoặc retry sai loại lỗi.

## 12. Danh sách kiểm tra trước khi triển khai

- [ ] Đã xác định rõ quy tắc nghiệp vụ và phạm vi dữ liệu cần duy nhất.
- [ ] Đã chọn constraint hay unique index theo mục đích và tính năng hệ quản trị.
- [ ] Đã xác định khóa đơn, khóa ghép, thứ tự cột và truy vấn cần hỗ trợ.
- [ ] Đã quy định cách xử lý `NULL`, chuỗi rỗng, collation và chuẩn hóa dữ liệu.
- [ ] Đã kiểm tra dữ liệu hiện tại và xử lý các nhóm trùng theo quy tắc nghiệp vụ.
- [ ] Đã ngăn phát sinh dữ liệu trùng trong khoảng thời gian migration.
- [ ] Đã đánh giá thời gian tạo chỉ mục, khóa, I/O, transaction log và replication.
- [ ] Đã kiểm thử hai transaction đồng thời tạo cùng khóa.
- [ ] Đã xác minh actual execution plan và cardinality estimate của truy vấn quan trọng.
- [ ] Đã đo tác động lên throughput đọc/ghi, độ trễ, dung lượng và bảo trì.
- [ ] Đã triển khai xử lý lỗi unique violation riêng trong ứng dụng.

Chỉ mục duy nhất là cơ chế quan trọng để thực thi quy tắc toàn vẹn dữ liệu và cung cấp thông tin về tính duy nhất cho bộ tối ưu truy vấn. Thiết kế đúng cần xác định phạm vi khóa, hành vi `NULL`, collation, điều kiện áp dụng và thứ tự cột; đồng thời phải tính đến kiểm tra đồng thời, chi phí ghi và quy trình migration. Hãy kiểm chứng bằng dữ liệu thực tế, execution plan và tải đọc/ghi trước khi triển khai để đạt được cả tính đúng đắn lẫn hiệu năng ổn định.

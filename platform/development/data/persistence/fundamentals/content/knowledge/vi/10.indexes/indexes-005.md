# Chỉ mục đơn và chỉ mục kết hợp

Khi một ứng dụng Java cần tìm một bản ghi theo mã định danh, lọc hàng theo trạng thái hoặc lấy 30 giao dịch mới nhất của một khách hàng, cơ sở dữ liệu phải chọn cách truy cập dữ liệu. **Chỉ mục đơn** giúp truy cập theo một cột khóa; **chỉ mục kết hợp** (hay **chỉ mục ghép**, *composite/multicolumn index*) sắp xếp nhiều khóa trong một cấu trúc để hỗ trợ các điều kiện và thứ tự truy vấn thường đi cùng nhau.

Trong mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**, thiết kế chỉ mục là một phần của thiết kế lưu trữ bền vững: người học cần liên kết mô hình dữ liệu, lược đồ, câu SQL và mã persistence của Java với hiệu năng đọc, chi phí ghi, tài nguyên và vận hành. Chủ đề này tập trung vào **cách lựa chọn giữa chỉ mục một cột, nhiều chỉ mục một cột và một chỉ mục ghép**. Các ví dụ dùng PostgreSQL và B-tree; khái niệm áp dụng rộng rãi, nhưng cú pháp, thuật toán tối ưu và giới hạn cụ thể có thể khác ở MySQL, SQL Server, Oracle hoặc hệ quản trị khác.

## Mục tiêu học tập

Hoàn thành bài học, bạn có thể:

1. Phân biệt chỉ mục đơn và chỉ mục kết hợp về khóa, thứ tự, điều kiện lọc, sắp xếp và chi phí.
2. Giải thích vì sao thứ tự cột trong chỉ mục ghép có thể quyết định hiệu quả truy vấn.
3. Nhận diện vai trò của điều kiện bằng, điều kiện khoảng và `ORDER BY ... LIMIT`.
4. So sánh một chỉ mục ghép với hai chỉ mục đơn và hiểu khi nào bộ tối ưu có thể kết hợp các chỉ mục độc lập.
5. Thiết kế chỉ mục dựa trên các mẫu truy vấn thực của repository Java rồi kiểm chứng bằng `EXPLAIN (ANALYZE, BUFFERS)`.
6. Nhận biết các đánh đổi về `INSERT`, `UPDATE`, `DELETE`, dung lượng, tính duy nhất và tiến hóa lược đồ.

## 1. Chỉ mục là gì trong đường truy cập dữ liệu?

Bảng dữ liệu lưu các hàng, còn chỉ mục duy trì một cấu trúc phụ để giúp tìm hàng theo một hay nhiều khóa. Với B-tree thông dụng, khóa được tổ chức theo thứ tự so sánh, cho phép tìm một giá trị, một khoảng giá trị và trong một số trường hợp trả hàng theo đúng thứ tự yêu cầu.

Ví dụ bảng giao dịch của một hệ thống nhiều đơn vị thuê (*multi-tenant*):

~~~sql
CREATE TABLE payments (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id    BIGINT NOT NULL,
    customer_id  BIGINT NOT NULL,
    status       TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL,
    amount       NUMERIC(14, 2) NOT NULL
);
~~~

Giả sử bảng có hàng triệu bản ghi và các API thường xuyên:

- Tra một giao dịch theo `id`.
- Lọc giao dịch thuộc một `tenant_id`.
- Tìm giao dịch của một khách hàng trong một đơn vị thuê.
- Lấy 30 giao dịch `PAID` mới nhất của một đơn vị thuê.
- Tổng hợp giao dịch trong một khoảng thời gian dài.

Không nên tạo chỉ mục dựa trên việc “cột này xuất hiện trong `WHERE`” một cách đơn lẻ. Các truy vấn trên có **mẫu lọc, thứ tự, số hàng trả về và độ chọn lọc** khác nhau. Chỉ mục tốt là chỉ mục tiết kiệm chi phí đủ nhiều cho những mẫu sử dụng thực tế.

> **Quy ước:** Bài này nói chủ yếu về chỉ mục B-tree trên các cột của bảng. Một số hệ quản trị có chỉ mục băm, full-text, GIN, GiST và nhiều cơ chế khác với đặc tính khác. Tên toán tử `Index Scan` trong kế hoạch thực thi cũng không đồng nghĩa mọi chỉ mục đều là B-tree.

## 2. Chỉ mục đơn: một khóa tìm kiếm

**Chỉ mục đơn** (*single-column index*) dùng một cột làm khóa tìm kiếm, chẳng hạn:

~~~sql
CREATE INDEX idx_payments_tenant
    ON payments (tenant_id);
~~~

Các mục của chỉ mục được tổ chức theo `tenant_id`; cơ sở dữ liệu có thể dò vùng khóa `tenant_id = 42` rồi lấy những hàng tương ứng.

~~~sql
SELECT id, customer_id, amount
FROM payments
WHERE tenant_id = 42;
~~~

Một chỉ mục đơn khác:

~~~sql
CREATE INDEX idx_payments_created_at
    ON payments (created_at);
~~~

có thể hỗ trợ truy vấn theo thời điểm:

~~~sql
SELECT id, created_at, amount
FROM payments
WHERE created_at >= TIMESTAMPTZ '2026-11-01 00:00:00+00'
  AND created_at <  TIMESTAMPTZ '2026-12-01 00:00:00+00';
~~~

**Ưu điểm:** dễ hiểu, phù hợp khi nhiều truy vấn độc lập thường lọc trên riêng từng cột. Ví dụ: hệ thống có truy vấn xem mọi giao dịch của một đơn vị thuê và cũng có truy vấn phân tích theo khoảng thời gian trên toàn bộ các đơn vị thuê.

**Giới hạn:** chỉ mục `(tenant_id)` không tự sắp xếp các giao dịch của cùng đơn vị thuê theo `created_at`. Tương tự, chỉ mục `(created_at)` không trực tiếp gom hàng theo `tenant_id`. Khi truy vấn đồng thời lọc đơn vị thuê và sắp xếp theo thời gian, optimizer có thể phải đọc nhiều mục, lọc thêm hoặc sắp xếp kết quả.

Nếu điều kiện khớp hầu hết hàng hoặc bảng quá nhỏ, quét toàn bảng vẫn có thể rẻ hơn tra chỉ mục. Việc chỉ mục tồn tại không ép bộ tối ưu phải sử dụng nó.

## 3. Chỉ mục kết hợp: một khóa gồm nhiều thành phần

Chỉ mục kết hợp định nghĩa **một thứ tự khóa chung** bằng nhiều cột:

~~~sql
CREATE INDEX idx_payments_tenant_customer_time
    ON payments (tenant_id, customer_id, created_at DESC);
~~~

Ở mức khái niệm, khóa được so sánh theo thứ tự:

1. `tenant_id` trước.
2. Trong cùng `tenant_id`, so sánh `customer_id`.
3. Trong cùng cặp `(tenant_id, customer_id)`, so sánh `created_at` từ mới đến cũ.

~~~text
Chỉ mục (tenant_id, customer_id, created_at DESC)

tenant=10, customer=101:   2026-11-22, 2026-11-19, 2026-11-10 ...
tenant=10, customer=102:   2026-11-21, 2026-11-14, 2026-11-02 ...
tenant=20, customer=101:   2026-11-20, 2026-11-16, 2026-11-03 ...
          |       |               |
          |       |               +-- khóa thứ ba
          |       +------------------ khóa thứ hai
          +-------------------------- khóa thứ nhất
~~~

Đây chỉ là minh họa thứ tự logic, không phải mô tả chính xác kích thước trang hoặc cách lưu hàng vật lý trong mọi hệ quản trị.

Một truy vấn rất phù hợp:

~~~sql
SELECT id, created_at, amount
FROM payments
WHERE tenant_id = 10
  AND customer_id = 101
ORDER BY created_at DESC
LIMIT 20;
~~~

Bộ tối ưu có thể đến thẳng dải khóa của `tenant_id = 10` và `customer_id = 101`, rồi đọc theo `created_at DESC` để trả 20 hàng đầu. Chỉ mục này vì vậy có thể hỗ trợ **lọc và sắp xếp cùng lúc**, giúp tránh quét/sắp xếp lượng lớn kết quả trung gian.

### 3.1. Thứ tự cột là một phần của thiết kế

Hai chỉ mục sau không tương đương:

~~~sql
CREATE INDEX idx_a
    ON payments (tenant_id, created_at DESC);

CREATE INDEX idx_b
    ON payments (created_at DESC, tenant_id);
~~~

Với truy vấn:

~~~sql
SELECT id, created_at
FROM payments
WHERE tenant_id = 10
ORDER BY created_at DESC
LIMIT 30;
~~~

`idx_a` thường là ứng viên tốt: khóa đầu giới hạn dữ liệu của một tenant; khóa thứ hai cung cấp thứ tự thời gian bên trong tenant đó.

`idx_b` tổ chức trước theo thời gian **trên tất cả tenant**. Nó có thể đọc từ giao dịch mới nhất, lọc ra tenant 10 rồi dừng khi đủ 30 hàng. Nếu tenant 10 chỉ chiếm tỷ lệ rất nhỏ, có thể phải xem qua nhiều mục chỉ mục của tenant khác.

Ngược lại, nếu cần **30 giao dịch mới nhất trên toàn hệ thống** không lọc tenant, thứ tự dẫn đầu bằng `created_at` của `idx_b` có thể hữu ích hơn.

Không có thứ tự cột “tốt nhất” độc lập với truy vấn.

### 3.2. Quy tắc tiền tố trái (*leftmost prefix*) và các giới hạn

Với B-tree trên `(tenant_id, customer_id, created_at DESC)`, các mẫu sau có mức độ phù hợp khác nhau:

| Mẫu điều kiện | Khả năng dùng chỉ mục ghép |
|---|---|
| `tenant_id = ?` | Có thể định vị dải khóa theo cột đầu |
| `tenant_id = ? AND customer_id = ?` | Có thể thu hẹp theo hai cột đầu |
| `tenant_id = ? AND customer_id = ? AND created_at >= ?` | Có thể giới hạn thêm khoảng trên cột thứ ba |
| `tenant_id = ? ORDER BY customer_id, created_at DESC` | Có thể tận dụng thứ tự chỉ mục trong một tenant |
| `customer_id = ?` | Thiếu điều kiện trên khóa đầu; thường kém hiệu quả hơn chỉ mục dẫn đầu bằng `customer_id` |
| `created_at >= ?` | Không có ràng buộc trên hai khóa đầu; thường không thuận lợi cho chỉ mục này |

Quy tắc tiền tố trái là **hướng dẫn thiết kế**, không phải luật cấm tuyệt đối. Một số phiên bản hệ quản trị có kỹ thuật như *skip scan* để tận dụng chỉ mục khi thiếu điều kiện ở cột đầu; một số kế hoạch vẫn dùng chỉ mục để lọc các mục sau khi quét một phần lớn cấu trúc. Muốn kết luận phải xem phiên bản và kế hoạch thực tế.

Trong PostgreSQL B-tree, thông thường các **điều kiện bằng ở các cột đầu** và điều kiện bất đẳng thức trên **cột đầu tiên chưa có điều kiện bằng** quyết định phần dải khóa có thể giới hạn. Điều kiện trên các cột ở phía sau vẫn có thể được kiểm tra ở chỉ mục nhưng không bảo đảm làm giảm toàn bộ dải cần duyệt.

Ví dụ:

~~~sql
-- Dải khóa thường được thu hẹp rõ theo tenant và khoảng thời gian.
CREATE INDEX idx_payments_tenant_time
    ON payments (tenant_id, created_at DESC);

SELECT id, created_at
FROM payments
WHERE tenant_id = 10
  AND created_at >= TIMESTAMPTZ '2026-11-01 00:00:00+00';
~~~

Nếu đặt điều kiện khoảng trên khóa đầu và điều kiện bằng trên khóa sau, khả năng thu hẹp vùng tìm kiếm thường khác:

~~~sql
-- Với chỉ mục (created_at, tenant_id), điều kiện khoảng trên
-- created_at thường định vị vùng cần duyệt trước; tenant_id được lọc tiếp.
SELECT id, created_at
FROM payments
WHERE created_at >= TIMESTAMPTZ '2026-11-01 00:00:00+00'
  AND tenant_id = 10;
~~~

Đặt điều kiện bằng ở đầu, rồi đến cột khoảng/sắp xếp thường là điểm xuất phát hợp lý; hãy kiểm chứng với phân bố dữ liệu và mẫu truy vấn thật.

### 3.3. Thứ tự tăng, giảm và ràng buộc sắp xếp

B-tree có thể hỗ trợ đọc theo thứ tự tiến hoặc lùi. Trong PostgreSQL, một chỉ mục `(tenant_id ASC, created_at ASC)` vẫn có thể hữu ích khi lọc bằng `tenant_id` rồi yêu cầu `created_at DESC` nhờ đọc lùi dải khóa tương ứng.

Tuy nhiên, với **thứ tự hỗn hợp giữa nhiều cột**, chiều `ASC`/`DESC` của khóa có thể rất quan trọng:

~~~sql
SELECT id, created_at
FROM payments
WHERE tenant_id = 10
ORDER BY customer_id ASC, created_at DESC
LIMIT 50;
~~~

Một chỉ mục dạng:

~~~sql
CREATE INDEX idx_payments_tenant_customer_time_mixed
    ON payments (tenant_id, customer_id ASC, created_at DESC);
~~~

có thể cung cấp đúng thứ tự trên trong cùng tenant. Chỉ mục `(tenant_id, customer_id ASC, created_at ASC)` không tương đương cho thứ tự hỗn hợp đó chỉ bằng cách đọc toàn bộ chỉ mục theo chiều ngược.

Sự phù hợp cũng phụ thuộc `NULLS FIRST/LAST`, kiểu dữ liệu, collation và cách hệ quản trị đối chiếu điều kiện sắp xếp.

## 4. Hai chỉ mục đơn có thay thế một chỉ mục kết hợp không?

Xét hai chỉ mục độc lập:

~~~sql
CREATE INDEX idx_payments_tenant_only
    ON payments (tenant_id);

CREATE INDEX idx_payments_customer_only
    ON payments (customer_id);
~~~

và truy vấn:

~~~sql
SELECT id, created_at, amount
FROM payments
WHERE tenant_id = 10
  AND customer_id = 101
ORDER BY created_at DESC
LIMIT 20;
~~~

Bộ tối ưu có nhiều khả năng lựa chọn:

- Dùng `idx_payments_tenant_only`, lấy các hàng của tenant rồi lọc `customer_id`.
- Dùng `idx_payments_customer_only`, lấy các hàng của khách hàng rồi lọc `tenant_id`.
- Kết hợp kết quả từ hai chỉ mục (nếu hệ quản trị hỗ trợ và ước tính có lợi).
- Quét bảng, nếu chi phí dự đoán rẻ hơn.

Trong PostgreSQL, phương án kết hợp có thể xuất hiện với các toán tử `Bitmap Index Scan`, `BitmapAnd` và `Bitmap Heap Scan`. Bitmap giúp thu thập vị trí hàng để đọc bảng theo trang; tuy nhiên **thứ tự khóa của từng chỉ mục không được giữ để đáp ứng `ORDER BY`**, vì vậy có thể cần bước `Sort`.

Một chỉ mục ghép:

~~~sql
CREATE INDEX idx_payments_tenant_customer_created
    ON payments (tenant_id, customer_id, created_at DESC);
~~~

có thể dùng cặp điều kiện bằng để thu hẹp vùng khóa, đọc tiếp theo thứ tự thời gian và dừng khi đủ 20 hàng. Đó là lợi thế mà việc tạo hai chỉ mục đơn **không tự động đem lại**.

Tuy nhiên, nếu hệ thống có nhiều truy vấn chỉ lọc riêng `tenant_id` và riêng `customer_id`, một chỉ mục ghép dẫn đầu bằng `tenant_id` sẽ không đương nhiên phục vụ hiệu quả tất cả truy vấn chỉ lọc `customer_id`. Khi ấy hai chỉ mục đơn, hoặc một tập chỉ mục kết hợp được lựa chọn theo tải thực tế, có thể phù hợp hơn.

### Bảng so sánh

| Tiêu chí | Hai chỉ mục đơn `(A)`, `(B)` | Một chỉ mục ghép `(A, B)` |
|---|---|---|
| Truy vấn chỉ lọc `A` | Có ứng viên trực tiếp `(A)` | Thường dùng tốt tiền tố `A` |
| Truy vấn chỉ lọc `B` | Có ứng viên trực tiếp `(B)` | Thường kém thuận lợi vì thiếu `A` |
| Truy vấn `A = ? AND B = ?` | Có thể dùng một hoặc kết hợp hai chỉ mục | Thường có thể định vị vùng khóa hẹp |
| `ORDER BY A, B` | Không mặc nhiên giữ được thứ tự khi kết hợp | Có thể tận dụng thứ tự khóa |
| Dung lượng | Có hai cấu trúc phụ | Một cấu trúc phụ, nhưng mục khóa có thể rộng hơn |
| Chi phí ghi | Cần cập nhật hai chỉ mục | Cần cập nhật một chỉ mục, nhưng khóa rộng hơn |
| Lựa chọn tối ưu | Phụ thuộc cả các truy vấn độc lập | Phụ thuộc các điều kiện hay đi cùng nhau và thứ tự |

Bảng này mô tả xu hướng, **không khẳng định** một chỉ mục ghép luôn nhỏ hơn hai chỉ mục đơn hay luôn rẻ hơn khi ghi. Dung lượng và chi phí phụ thuộc kiểu dữ liệu, phân bố, kích thước khóa và cách lưu của hệ quản trị.

## 5. Chọn thứ tự cột theo mẫu truy vấn

Một cách làm thực tế là ghi các truy vấn được dùng nhiều nhất, điều kiện, thứ tự, giới hạn và tần suất. Ví dụ:

| Mẫu truy vấn | Điều kiện | Thứ tự / giới hạn | Ứng viên cần đo |
|---|---|---|---|
| Danh sách giao dịch mới nhất của tenant | `tenant_id = ?` | `created_at DESC, id DESC LIMIT 30` | `(tenant_id, created_at DESC, id DESC)` |
| Danh sách giao dịch đã thanh toán của tenant | `tenant_id = ? AND status = 'PAID'` | `created_at DESC, id DESC LIMIT 30` | `(tenant_id, status, created_at DESC, id DESC)` |
| Lịch sử giao dịch của một khách hàng trong tenant | `tenant_id = ? AND customer_id = ?` | `created_at DESC LIMIT 50` | `(tenant_id, customer_id, created_at DESC)` |
| Báo cáo giao dịch theo ngày trên toàn hệ thống | `created_at` thuộc một khoảng | Không bắt buộc thứ tự | `(created_at)` hoặc quét bảng tùy tỷ lệ dữ liệu |
| Tra giao dịch theo `id` | `id = ?` | Một hàng | Chỉ mục duy nhất từ `PRIMARY KEY` |

Không nhất thiết tạo đủ tất cả ứng viên. Những chỉ mục có phần đầu trùng nhau có thể cạnh tranh về công dụng. Cần xem tổng tải đọc/ghi và loại bỏ cấu trúc không mang thêm lợi ích đáng kể.

### 5.1. Vì sao `(tenant_id, status, created_at)` chưa thay thế hoàn toàn `(tenant_id, created_at)`?

Với chỉ mục:

~~~sql
CREATE INDEX idx_payments_tenant_status_time
    ON payments (tenant_id, status, created_at DESC);
~~~

truy vấn `WHERE tenant_id = 10 AND status = 'PAID' ORDER BY created_at DESC` có thể được đáp ứng tốt.

Nhưng khi bỏ điều kiện `status`:

~~~sql
SELECT id, status, created_at
FROM payments
WHERE tenant_id = 10
ORDER BY created_at DESC
LIMIT 30;
~~~

các bản ghi trong chỉ mục được nhóm theo **status trước**, rồi mới sắp xếp theo thời gian **bên trong từng status**. Thứ tự đó không tương đương với `created_at DESC` của tất cả trạng thái gộp lại. Vì vậy planner có thể cần `Sort` hoặc chọn đường truy cập khác.

Đây là lý do cần quan sát trọn vẹn mẫu `WHERE + ORDER BY + LIMIT` khi chọn thứ tự cột.

### 5.2. Điều kiện khoảng và giá trị phân biệt

Thống kê phân bố quyết định hiệu quả thực tế. `status` chỉ có vài giá trị như `NEW`, `PAID`, `FAILED` nên thường ít phân biệt hơn `customer_id`, nhưng **không thể suy ra thứ tự cột chỉ từ số giá trị phân biệt**.

Với truy vấn cố định `tenant_id = ? AND status = ? ORDER BY created_at DESC`, đặt hai điều kiện bằng lên trước `created_at` thường có ích. Nếu còn nhiều truy vấn bỏ `status`, có thể cân nhắc thêm một chỉ mục khác dẫn đầu bằng `(tenant_id, created_at)`. Điều cần tối ưu là tổng chi phí của các truy vấn quan trọng, không phải một quy tắc “cột có nhiều giá trị khác nhau luôn đặt trước”.

## 6. Trường hợp nâng cao: duy nhất, bao phủ và lọc một phần

Các kỹ thuật sau làm rõ những việc chỉ mục có thể làm ngoài tăng tốc tìm kiếm, nhưng cần dùng khi có yêu cầu nghiệp vụ hoặc số liệu đo cụ thể.

### 6.1. Chỉ mục `UNIQUE` đơn và kết hợp

Bảng mẫu đã có `PRIMARY KEY (id)`; PostgreSQL tự tạo chỉ mục duy nhất trên cột `id` để thực thi ràng buộc này. Đó là ví dụ về chỉ mục duy nhất một cột: mỗi `id` chỉ xác định một hàng, và không cần tạo thêm chỉ mục tương đương.

Một chỉ mục duy nhất trên `external_reference` có thể bảo đảm giá trị tham chiếu không trùng trong phạm vi **toàn bảng**. Tuy nhiên, trong hệ thống multi-tenant, một mã bên ngoài có thể chỉ cần duy nhất *trong từng tenant*. Hai yêu cầu này khác nhau; phải chọn đúng phạm vi duy nhất mà nghiệp vụ cần.

~~~sql
-- Ví dụ lược đồ có thêm cột tham chiếu:
ALTER TABLE payments
    ADD COLUMN external_reference TEXT;

-- Nếu mã tham chiếu phải duy nhất trên toàn bảng, có thể dùng:
-- CREATE UNIQUE INDEX ux_payments_external_ref
--     ON payments (external_reference);

-- Ví dụ này chọn phạm vi duy nhất theo từng tenant:
-- Sau khi rà soát dữ liệu cũ và quy tắc NULL:
ALTER TABLE payments
    ADD CONSTRAINT uq_payments_tenant_external_ref
    UNIQUE (tenant_id, external_reference);
~~~

Ràng buộc này ngăn hai hàng có cùng cặp `(tenant_id, external_reference)` khi giá trị tham chiếu không null. Nó **không** bắt `external_reference` phải duy nhất trên toàn bảng, cũng không bắt từng `tenant_id` chỉ xuất hiện một lần.

Trong PostgreSQL, ràng buộc `UNIQUE` mặc định cho phép nhiều `NULL` theo quy tắc xem các giá trị NULL là phân biệt khi xét tính duy nhất. Nếu `external_reference` luôn bắt buộc có, nên dùng `NOT NULL` sau khi xử lý dữ liệu; còn nếu cần ngữ nghĩa khác thì thiết kế ràng buộc phù hợp. Bổ sung ràng buộc trên bảng đang có dữ liệu có thể thất bại nếu dữ liệu hiện tại vi phạm.

### 6.2. Chỉ mục bao phủ với `INCLUDE`

Chỉ mục ghép `(tenant_id, created_at DESC, id DESC)` cho phép lọc và sắp xếp, nhưng nếu truy vấn còn trả `amount`, hệ quản trị có thể phải truy cập bảng để lấy cột này.

PostgreSQL hỗ trợ thêm cột dữ liệu không thuộc khóa tìm kiếm bằng `INCLUDE`:

~~~sql
CREATE INDEX idx_payments_tenant_time_cover
    ON payments (tenant_id, created_at DESC, id DESC)
    INCLUDE (amount);
~~~

Trong một số trường hợp, chỉ mục đủ cột giúp giảm số lần đọc bảng. Tuy nhiên, `Index Only Scan` trên PostgreSQL còn phụ thuộc khả năng xác minh tính hiển thị hàng theo cơ chế MVCC; nó có thể xuất hiện `Heap Fetches`. Thêm `INCLUDE` cũng làm chỉ mục lớn hơn và có thể tăng chi phí ghi. Hãy xem đây là **một phương án thay thế** ứng viên ban đầu sau khi đo, không phải mặc định tạo cả hai.

### 6.3. Chỉ mục một phần (*partial index*)

Nếu API thường chỉ xử lý giao dịch đang chờ và trạng thái này hiếm:

~~~sql
CREATE INDEX idx_payments_pending_tenant_time
    ON payments (tenant_id, created_at DESC, id DESC)
    WHERE status = 'PENDING';
~~~

Truy vấn có điều kiện chứng minh được rằng `status = 'PENDING'` có thể hưởng lợi từ chỉ mục nhỏ hơn so với chỉ mục mọi trạng thái. Với prepared statement dùng tham số, khả năng planner chứng minh điều kiện trùng với predicate của chỉ mục phụ thuộc SQL, giá trị tham số và loại kế hoạch (chung hay riêng); không nên giả định chỉ mục một phần luôn được dùng với `status = ?`.

Dữ liệu thay đổi trạng thái thường xuyên còn gây chi phí đưa hàng vào/ra chỉ mục một phần. Cần đo cả phía ghi.

## 7. Đo và xác minh bằng PostgreSQL

Chỉ mục được đề xuất theo **mẫu truy vấn**, nhưng quyết định cuối cùng nên dựa trên số liệu. Dưới đây là một thí nghiệm có thể thực hiện trên cơ sở dữ liệu thử nghiệm với dữ liệu đủ lớn và phân bố đại diện.

### 7.1. Đo trước và sau khi tạo chỉ mục

Ví dụ API lấy 30 giao dịch mới nhất của một tenant, bất kể trạng thái:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, created_at, amount
FROM payments
WHERE tenant_id = 10
ORDER BY created_at DESC, id DESC
LIMIT 30;
~~~

Sau đó cân nhắc:

~~~sql
CREATE INDEX idx_payments_tenant_created_id
    ON payments (tenant_id, created_at DESC, id DESC);

ANALYZE payments;

EXPLAIN (ANALYZE, BUFFERS)
SELECT id, created_at, amount
FROM payments
WHERE tenant_id = 10
ORDER BY created_at DESC, id DESC
LIMIT 30;
~~~

Nếu chỉ mục hữu ích, kế hoạch có thể có hình dạng tương tự:

~~~text
Limit
  -> Index Scan using idx_payments_tenant_created_id on payments
       Index Cond: (tenant_id = 10)
~~~

Đây là **minh họa**, không phải kết quả chạy thử thực tế. Trong dữ liệu và điều kiện khác, PostgreSQL vẫn có thể chọn `Seq Scan`, `Bitmap Heap Scan` hoặc cấu trúc kế hoạch khác. Vì `amount` không nằm trong chỉ mục trên, `Index Scan` có thể phải truy cập hàng ở bảng.

Khi đọc `EXPLAIN`, đặc biệt chú ý:

| Trường / toán tử | Câu hỏi cần trả lời |
|---|---|
| `Seq Scan` | Truy vấn cần quá nhiều hàng hay không có chỉ mục phù hợp? |
| `Index Scan` | Chỉ mục đã giới hạn đúng vùng khóa chưa, có phải lấy nhiều trang bảng không? |
| `Bitmap Index Scan`, `BitmapAnd`, `Bitmap Heap Scan` | Có đang kết hợp chỉ mục đơn? Có phát sinh sắp xếp sau khi lấy hàng không? |
| `Index Cond` so với `Filter` | Điều kiện nào giới hạn đường chỉ mục, điều kiện nào chỉ được kiểm tra thêm? |
| `Sort` | Thứ tự của chỉ mục có khớp `ORDER BY` và điều kiện lọc không? |
| `cost=... rows=...` | Ước tính của planner có lệch đáng kể với thực tế không? `cost` không có đơn vị mili-giây |
| `actual time=... rows=... loops=...` | Thời gian, số hàng thực tế và số lần thực thi của từng toán tử |
| `Buffers: shared hit/read` | Có bao nhiêu trang được chạm tới trong bộ đệm dùng chung và bao nhiêu trang phải được nạp vào đó? |

`EXPLAIN (ANALYZE, BUFFERS)` thực sự chạy câu lệnh; chạy các phép đo ở nơi phù hợp và chú ý tải song song, bộ nhớ đệm, dữ liệu thử nghiệm. `shared read` không tương đương trực tiếp số lần đọc đĩa vật lý vì còn các lớp cache khác.

### 7.2. Đọc kế hoạch bằng câu hỏi, không bằng tên toán tử

Một `Index Scan` có thể vẫn tốn nhiều thời gian nếu hàng phù hợp rất nhiều và nằm rải rác. Một `Seq Scan` có thể là lựa chọn đúng khi cần phần lớn bảng. Điều cần so sánh:

1. Tổng thời gian và độ ổn định độ trễ qua nhiều lần đo có điều kiện tương đương.
2. Số trang bảng và chỉ mục thực tế bị chạm.
3. Số hàng được đọc, bị lọc và được trả về.
4. Có cần `Sort` và có dừng sớm với `LIMIT` không.
5. Ảnh hưởng của chỉ mục mới tới các truy vấn khác và thao tác ghi.

Khi kết quả không như dự đoán, kiểm tra thống kê (`ANALYZE`), phân bố `tenant_id` hoặc `status`, giá trị tham số, chiều sắp xếp, kiểu dữ liệu và số lượng bản ghi thật. Không nên ép optimizer theo một kế hoạch chỉ vì “đã có index”.

## 8. Từ SQL đến repository Java

Một tầng persistence Java nên diễn đạt rõ phạm vi lọc, thứ tự và giới hạn để hệ quản trị có cơ hội dùng chỉ mục phù hợp. Ví dụ API lấy tối đa 30 giao dịch mới nhất của tenant:

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import javax.sql.DataSource;

public final class PaymentRepository {
    private final DataSource dataSource;

    public record PaymentPreview(long id, Instant createdAt, BigDecimal amount) {}

    public PaymentRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public List<PaymentPreview> findRecent(long tenantId) throws SQLException {
        String sql = """
            SELECT id, created_at, amount
            FROM payments
            WHERE tenant_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 30
            """;

        List<PaymentPreview> result = new ArrayList<>();

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, tenantId);

            try (ResultSet rows = statement.executeQuery()) {
                while (rows.next()) {
                    result.add(new PaymentPreview(
                        rows.getLong("id"),
                        rows.getTimestamp("created_at").toInstant(),
                        rows.getBigDecimal("amount")
                    ));
                }
            }
        }

        return result;
    }
}
~~~

Câu SQL này phù hợp để cân nhắc chỉ mục `(tenant_id, created_at DESC, id DESC)`.

- `PreparedStatement` truyền tham số an toàn, nhưng **không tạo chỉ mục** và cũng không bảo đảm một kế hoạch cố định.
- `ORDER BY created_at DESC, id DESC` tạo thứ tự xác định cả khi hai giao dịch có cùng thời gian; chỉ mục nên xét đủ cả hai khóa sắp xếp.
- `LIMIT 30` giới hạn kết quả ở cơ sở dữ liệu, tránh tải hàng nghìn đối tượng Java chỉ để cắt danh sách ở bộ nhớ.
- `try-with-resources` đóng tài nguyên JDBC theo đúng vòng đời; quản lý tài nguyên không thay thế việc tối ưu số trang dữ liệu phải đọc.
- Nếu dùng JPA/Hibernate, hãy đo **SQL thực được sinh ra**, gồm join, điều kiện lọc, phân trang và các truy vấn bổ sung.

Một hệ thống multi-tenant còn phải **bắt buộc lọc tenant theo quy tắc phân quyền**. Chỉ mục `tenant_id` tăng hiệu năng nhưng không tự kiểm soát quyền truy cập dữ liệu. Xác thực và kiểm soát tenant vẫn thuộc trách nhiệm của thiết kế ứng dụng và/hoặc chính sách cơ sở dữ liệu.

## 9. Chi phí ghi, dung lượng và tiến hóa schema

Một chỉ mục được duy trì cùng với dữ liệu. Thêm càng nhiều chỉ mục có thể giúp một số truy vấn đọc nhưng kéo theo:

- **Ghi:** `INSERT` cần tạo mục tương ứng; `DELETE` và một số `UPDATE` tạo thêm công việc bảo trì. Việc cập nhật cột khóa của chỉ mục đặc biệt liên quan đến chi phí cập nhật cấu trúc chỉ mục.
- **Dung lượng:** thêm khóa hoặc cột `INCLUDE` làm tăng dữ liệu chỉ mục, ảnh hưởng bộ nhớ đệm và sao lưu.
- **Bảo trì:** chỉ mục có thể cần theo dõi mức sử dụng, độ phình, phân mảnh và chiến lược bảo trì phù hợp với hệ quản trị.
- **Thay đổi lược đồ:** tạo chỉ mục trên bảng lớn có thể tiêu tốn I/O/CPU và ảnh hưởng hoạt động. Trong PostgreSQL, `CREATE INDEX CONCURRENTLY` cho phép tạo chỉ mục với hạn chế khóa ghi so với cách tạo thông thường, nhưng có điều kiện sử dụng riêng (chẳng hạn không chạy trong transaction block) và có chi phí/khả năng thất bại cần quản lý. Không áp dụng cú pháp này nguyên xi cho hệ quản trị khác.
- **Khả năng quan sát:** chỉ mục phù hợp hôm nay có thể ít có ích khi lượng dữ liệu, tỷ lệ trạng thái và hình dạng truy vấn thay đổi.

Các chỉ mục trùng lặp gần như hoàn toàn dễ lãng phí tài nguyên. Ví dụ khi `(tenant_id, created_at DESC, id DESC)` đã đáp ứng tốt truy vấn chỉ lọc tenant, chỉ mục đơn `(tenant_id)` có thể không còn đóng góp đáng kể. Nhưng việc xóa nó vẫn phải dựa trên theo dõi truy vấn, số đo và ràng buộc hiện có; không xóa chỉ vì một chỉ mục khác có cùng cột đầu.

**Quy trình thiết kế thực tế:**

1. Thu thập các truy vấn quan trọng theo đường gọi API/job, thời gian chạy, tần suất và phân bố tham số.
2. Liệt kê điều kiện bằng, điều kiện khoảng, thứ tự, `LIMIT` và các cột cần trả.
3. Đề xuất thứ tự khóa dựa vào mẫu truy vấn. Cân nhắc nhu cầu độc lập trên cột thứ hai trước khi gộp chỉ mục.
4. Đo kế hoạch và thời gian trước/sau trên dữ liệu đại diện; tính cả tải ghi.
5. Chọn số lượng chỉ mục tối thiểu đủ phục vụ nhu cầu và theo dõi lại khi nghiệp vụ thay đổi.

## 10. Bài tập và tình huống quyết định

### Bài 1: Chọn chỉ mục cho truy vấn theo tenant

Bảng `payments` có 20 triệu hàng. Một tenant sở hữu 40.000 hàng, trong đó API cần 25 hàng mới nhất:

~~~sql
SELECT id, created_at
FROM payments
WHERE tenant_id = 77
ORDER BY created_at DESC, id DESC
LIMIT 25;
~~~

Hãy chọn ứng viên tốt hơn giữa:

- A: `(tenant_id)`.
- B: `(created_at DESC)`.
- C: `(tenant_id, created_at DESC, id DESC)`.

**Gợi ý:** C thường là ứng viên tốt nhất vì giới hạn dải tenant và cung cấp thứ tự với khả năng dừng sớm. Quyết định cuối cùng dựa trên kế hoạch và phép đo.

### Bài 2: Chỉ mục ghép có “bao hết” chỉ mục đơn không?

Hệ thống có hai API riêng:

~~~sql
-- API 1
SELECT id FROM payments WHERE tenant_id = 77;

-- API 2
SELECT id FROM payments WHERE customer_id = 9001;
~~~

Đã có chỉ mục `(tenant_id, customer_id)`. Có nên coi nó thay thế hoàn toàn `(customer_id)`?

**Gợi ý:** Không. Truy vấn thứ hai thiếu điều kiện trên `tenant_id` nên thường khó khoanh vùng hiệu quả theo chỉ mục ghép này. Nếu API 2 quan trọng và chọn lọc tốt, thử thêm một chỉ mục dẫn đầu bằng `customer_id` rồi đo.

### Bài 3: Vì sao vẫn có bước `Sort`?

Có chỉ mục `(tenant_id, status, created_at DESC)`. Truy vấn:

~~~sql
SELECT id, status, created_at
FROM payments
WHERE tenant_id = 77
ORDER BY created_at DESC
LIMIT 20;
~~~

Kế hoạch có `Sort`. Vì sao?

**Gợi ý:** Trong cùng tenant, chỉ mục sắp xếp theo `status` trước; các bản ghi của tất cả trạng thái không nằm chung một thứ tự giảm dần của `created_at`. Cân nhắc một chỉ mục `(tenant_id, created_at DESC)` nếu truy vấn này có giá trị và đủ thường xuyên.

### Bài 4: Hai chỉ mục đơn và `BitmapAnd`

Đã có `(tenant_id)` và `(status)`. Truy vấn lọc đồng thời hai cột, chỉ trả vài trăm hàng. Một kế hoạch dùng `BitmapAnd`, tiếp đó `Bitmap Heap Scan`.

**Gợi ý:** Hai chỉ mục có thể được kết hợp để tìm các hàng giao nhau. Đây có thể là lựa chọn tốt nếu lượng dữ liệu và chi phí phù hợp. Nếu truy vấn còn cần `ORDER BY created_at DESC LIMIT 20` và chạy rất thường xuyên, hãy thử so sánh với chỉ mục ghép `(tenant_id, status, created_at DESC)`.

### Bài 5: Hiểu ràng buộc duy nhất nhiều cột

Bảng có `UNIQUE (tenant_id, external_reference)`. Tenant 10 và tenant 20 cùng có tham chiếu `"INV-001"`. Trường hợp này có vi phạm unique không?

**Gợi ý:** Không, vì hai cặp khóa khác nhau. Hai giao dịch cùng tenant 10 và cùng tham chiếu không NULL `"INV-001"` sẽ vi phạm ràng buộc.

## 11. Ghi nhớ

- **Chỉ mục đơn** thích hợp cho đường truy cập theo một cột; **chỉ mục kết hợp** đặc biệt hữu ích khi nhiều điều kiện và thứ tự kết quả thường đi cùng nhau.
- **Thứ tự khóa quyết định thứ tự dữ liệu bên trong chỉ mục**. `(A, B)` thường hỗ trợ tốt truy vấn bắt đầu bằng `A`, nhưng không thể tự suy ra rằng nó phục vụ mọi truy vấn chỉ có `B`.
- **Điều kiện bằng, khoảng và `ORDER BY ... LIMIT` phải được xem cùng nhau.** Nhiều chỉ mục đơn không tự thay thế lợi thế về thứ tự của một chỉ mục ghép.
- **Chỉ mục không miễn phí.** Cần cân bằng cải thiện đọc với chi phí ghi, lưu trữ, bảo trì, ràng buộc nghiệp vụ và thay đổi schema.
- **Đo bằng SQL thực và kế hoạch thực thi** từ tầng persistence Java, trên dữ liệu đại diện, trước khi quyết định tạo, thay đổi hoặc bỏ chỉ mục.

Thiết kế chỉ mục tốt bắt đầu từ câu hỏi: *ứng dụng thường tìm, lọc và sắp xếp dữ liệu như thế nào?* Câu trả lời phải thể hiện qua truy vấn cụ thể và được xác minh bằng phép đo, để hệ thống persistence vừa đúng nghiệp vụ, vừa hiệu quả và bền vững khi dữ liệu tăng trưởng.

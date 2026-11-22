# Quyền thực thi view, security_invoker và security_barrier trong PostgreSQL

## 1. Một view trả dữ liệu dưới quyền của ai?

Giả sử hệ thống có bảng `finance.payments` chứa số tiền, khách hàng, người xử lý và thông tin nội bộ. Ứng dụng báo cáo cần xem **một số hàng và một số cột** chứ không nên được cấp quyền trực tiếp đọc toàn bộ bảng.

Đội phát triển tạo view:

~~~sql
CREATE VIEW reporting.v_paid_payments AS
SELECT payment_id, customer_id, amount
FROM finance.payments
WHERE status = 'paid';

GRANT SELECT ON reporting.v_paid_payments TO report_reader;
~~~

Câu hỏi bảo mật quan trọng không chỉ là “`GRANT SELECT` trên view hay chưa?”, mà còn:

- Người gọi có cần `SELECT` trên bảng `finance.payments` không?
- Khi bảng gốc có **Row-Level Security (RLS)**, policy của **người gọi** hay **chủ sở hữu view** được áp dụng?
- Nếu người gọi viết thêm một biểu thức có thể phát lộ dữ liệu ở điều kiện `WHERE` bên ngoài view, PostgreSQL có thể thực thi biểu thức đó trước bộ lọc của view không?
- Một view dùng `security_invoker=true` có giống view dùng `security_barrier=true` không?
- View có tự bảo vệ dữ liệu khi người dùng có quyền truy cập bảng gốc qua đường khác không?
- Việc sử dụng function, nested view, quyền của schema và role membership làm thay đổi câu trả lời ra sao?

Bài học này giải quyết những câu hỏi đó bằng một nguyên tắc: **phải phân biệt quyền truy cập (privileges), danh tính áp dụng RLS, và ranh giới tối ưu hóa biểu thức (security barrier)**. Ba vấn đề liên quan nhưng không thay thế nhau.

### 1.1. Mục tiêu học tập

Sau bài, bạn có thể:

1. Giải thích sự khác biệt giữa **quyền SELECT trên view**, **quyền SELECT trên bảng nền**, và **quyền USAGE trên schema**.
2. Hiểu cơ chế view mặc định kiểm tra quyền trên bảng nền bằng **quyền của view owner**.
3. Tạo và thay đổi view `WITH (security_invoker=true)` trong PostgreSQL 15+; nêu tác động đến quyền và RLS.
4. Dùng `WITH (security_barrier=true)` khi muốn bảo vệ điều kiện lọc khỏi việc một số biểu thức bên ngoài bị đẩy xuống chạy quá sớm.
5. Phân biệt `security_barrier` với `security_invoker` và với `SECURITY DEFINER` của function.
6. Kiểm thử bằng các roles độc lập, `SET ROLE`, `GRANT`/`REVOKE`, `EXPLAIN` và catalog.
7. Hiểu rủi ro **RLS owner bypass**, `BYPASSRLS`, policy thiếu, nested views và quyền thực thi function.
8. Biết giới hạn của view như một security boundary: side channels, leaky functions, quyền đường khác và các thao tác ghi.
9. Thiết kế quy trình migration, phân quyền, kiểm thử và review các view có tính nhạy cảm.
10. Thực hành bài tập SQL và xử lý tình huống quyền truy cập dữ liệu.

> **Cảnh báo vận hành:** các lệnh `CREATE ROLE`, `GRANT`, `REVOKE`, `ALTER VIEW` và `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` có thể ảnh hưởng truy cập dữ liệu nếu chạy nhầm môi trường. Hãy thực hành trong database/schema riêng, với role quản trị được phép. Không chạy nguyên một script có đoạn “lỗi mong đợi” qua migration tool đang bật stop-on-error.

---

## 2. View là gì, và security boundary nằm ở đâu?

Một **view thông thường** lưu định nghĩa truy vấn SELECT dưới một tên quan hệ logic. Khi truy vấn view, PostgreSQL sử dụng cơ chế rewrite/planning để mở rộng truy vấn phù hợp và thực thi trên các relations nền.

~~~text
Ứng dụng / User: report_reader
            |
            | SELECT payment_id, amount
            | FROM reporting.v_paid_payments;
            v
   reporting.v_paid_payments
   SELECT payment_id, amount
   FROM finance.payments
   WHERE status='paid'
            |
            v
      finance.payments
            |
            v
      Hàng dữ liệu trả về
~~~

Phía người gọi thấy một interface tên view, nhưng quyền đọc bảng nền được xử lý theo quy tắc của PostgreSQL đối với view.

### 2.1. View không nhất thiết tạo ra một bản sao dữ liệu

Một view thường không lưu các row riêng như một bảng. `SELECT` trên view chạy logic truy vấn nền; nếu bảng gốc thay đổi, kết quả view thay đổi theo.

**Materialized view** là đối tượng khác: lưu kết quả vật lý và phải REFRESH. Không lấy quy tắc caching/refresh của materialized view để suy luận trực tiếp quyền của view thường.

### 2.2. Security view không đồng nghĩa mọi lớp đều an toàn

Một view có thể:

- Chỉ expose một số cột.
- Chỉ expose những row đáp ứng predicate.
- Kiểm tra quyền bảng nền theo owner hoặc invoker.
- Áp dụng security barrier để hạn chế thứ tự đánh giá những biểu thức không leakproof.

Nhưng view **không tự**:

- Thu hồi những quyền đọc bảng gốc mà người gọi đã có.
- Ngăn thông tin bị rò qua mọi kênh phụ như thời gian, khóa, thống kê hoặc thông báo lỗi từ những đường hợp lệ.
- Thay thế RBAC/RLS chính xác.
- Ngăn mọi function nguy hiểm được gọi ở bên ngoài khi vai trò vẫn có `EXECUTE` trên function đó.
- Bảo đảm lọc row khi một view bị sửa định nghĩa hoặc một role có quyền thay đổi view.

Cần thiết kế **least privilege** xuyên suốt toàn bộ các đường truy cập dữ liệu.

---

## 3. Các lớp quyền phải kiểm tra khi truy vấn view

| Lớp | Ví dụ quyền / đối tượng | Mục đích |
|---|---|---|
| Database | `CONNECT ON DATABASE` | Kết nối được tới database |
| Schema chứa view | `USAGE ON SCHEMA reporting` | Phân giải và sử dụng đối tượng trong schema |
| View | `SELECT ON reporting.v_paid_payments` | Được phép đọc các cột của view |
| Bảng nền | `SELECT ON finance.payments` | Có cần quyền này ở caller hay không phụ thuộc view security mode |
| Schema chứa bảng nền | `USAGE ON SCHEMA finance` | Đối với quyền truy cập trực tiếp, schema USAGE là yêu cầu; qua view mặc định, người dùng thường không cần quyền này để gọi view |
| Functions | `EXECUTE ON FUNCTION ...` | Các function được gọi trong truy vấn có quyền thực thi riêng |
| Row-level security | `POLICY ... USING (...)` | Lọc/kiểm soát row sau khi xác định danh tính RLS được áp dụng |
| Role attributes | `BYPASSRLS`, owner status, membership | Có thể đổi hành vi RLS hoặc quyền hiệu lực |

### 3.1. Grant trên view và grant trên bảng nền không phải một lệnh

~~~sql
GRANT SELECT ON reporting.v_paid_payments TO report_reader;
~~~

Lệnh này cấp `SELECT` trên **view**, không đồng nghĩa tự cấp `SELECT` trên `finance.payments`. Ngược lại:

~~~sql
GRANT SELECT ON finance.payments TO report_reader;
~~~

sẽ cho người dùng một đường đọc bảng nền riêng, tùy schema privileges và RLS; nó không tự cấp `SELECT` trên reporting view.

### 3.2. Schema USAGE cho đối tượng được gọi

Một role có `SELECT` trên view nhưng không có `USAGE` trên schema chứa view vẫn có thể bị chặn khi truy cập view theo tên.

~~~sql
GRANT USAGE ON SCHEMA reporting TO report_reader;
GRANT SELECT ON reporting.v_paid_payments TO report_reader;
~~~

Đây là hai thao tác khác nhau.

### 3.3. Có cần USAGE trên schema chứa bảng nền?

Với **view thông thường kiểm tra quyền bảng nền theo chủ view**, người dùng chỉ cần quyền phù hợp để dùng view; không nhất thiết được cấp `USAGE` trên schema của bảng nền hoặc `SELECT` trên bảng nền.

Với **security_invoker view**, các quyền trên **base relations** được kiểm tra theo invoker, nhưng việc truy cập quan hệ nền **thông qua view** không có nghĩa caller cần được cấp `USAGE` trên mọi schema nền giống khi gọi trực tiếp tên bảng đó. Để caller gọi trực tiếp bảng nền bằng tên, `USAGE` schema vẫn cần thiết. Phân biệt **relation privilege checks** và **name lookup/access via view** khi review grant.

### 3.4. Column-level privileges

PostgreSQL có quyền cấp riêng từng cột:

~~~sql
GRANT SELECT (payment_id, customer_id, amount, status)
ON finance.payments TO report_reader;
~~~

Khi caller có quyền SELECT ở mức cột cần thiết, một security-invoker view có thể chạy mà không cần cấp `SELECT` trên những cột nhạy cảm khác, miễn là mọi tham chiếu trong định nghĩa view đều được bao phủ.

Nhưng nếu ứng dụng có quyền đọc `status` và các cột filter qua đường truy cập bảng nền, nó có thể thực hiện query khác. **Column privilege không thay row-level isolation**.

### 3.5. Privilege không thay cho dữ liệu được phép thấy

`GRANT SELECT` trả lời “có thể thực hiện thao tác SELECT hay không”; RLS trả lời “row nào có thể nhìn thấy hoặc thao tác theo policy?”; security barrier trả lời “tối ưu hóa có thể đẩy một số biểu thức ra trước điều kiện bảo vệ được không?”. Ba câu hỏi này phải được trả lời riêng.

---

## 4. View mặc định: quyền của view owner trên bảng nền

### 4.1. Hành vi mặc định

Trên PostgreSQL, một view không bật `security_invoker` thông thường truy cập bảng nền theo **quyền của chủ sở hữu view**. Cơ chế này đôi khi được gọi không chính thức là *security-definer-like view*, nhưng **không nhầm với `SECURITY DEFINER` của function**.

Ví dụ:

~~~sql
-- Chạy bằng role có quyền trên bảng nền:
CREATE VIEW reporting.v_paid_payments AS
SELECT payment_id, customer_id, amount
FROM finance.payments
WHERE status='paid';
~~~

Nếu:

- `report_owner` sở hữu view và có quyền SELECT trên bảng nền.
- `report_reader` có `USAGE` schema chứa view + `SELECT` view.
- `report_reader` không có SELECT trên bảng nền.

thì `report_reader` **vẫn có thể SELECT view**, bởi vì quyền truy cập bảng nền được xét theo owner của view.

### 4.2. Sơ đồ kiểm tra quyền

~~~text
SELECT FROM view do report_reader gửi
       |
       +--> report_reader có SELECT trên view? ---- không --> ERROR
       |
       +--> report_reader có USAGE schema view? --- không --> ERROR
       |
       v
View mặc định (security_invoker = false)
       |
       +--> Quyền bảng nền xét theo VIEW OWNER
       |
       v
Đọc bảng nền theo truy vấn/view definition
       |
       v
Trả các row/columns phù hợp định nghĩa
~~~

### 4.3. Hệ quả về bảo mật

Mặc định view hữu ích khi muốn cung cấp **một giao diện đọc có giới hạn** cho người dùng không có quyền trên dữ liệu gốc.

Nhưng nếu một view owner có quyền đọc **toàn bộ row**, kết quả view có thể phản ánh dữ liệu vượt khỏi RLS dành cho caller. Điều này phụ thuộc RLS identity và quyền owner ở bảng nền, được phân tích trong phần tiếp theo.

### 4.4. View owner khác người gọi

Một view có thể được tạo bởi role `report_owner`, nhưng user truy cập là `report_reader`.

Khi gọi view:

- **Invoker** là role thực thi câu truy vấn.
- **View owner** là role sở hữu relation view.
- **Table owner** có thể là role khác nữa.

Ba role đó **không tự là một**.

### 4.5. Không nên cấp quyền mạnh cho view owner vô lý

Nếu owner view là superuser hoặc role có `BYPASSRLS`, nó có khả năng đặc biệt khi áp RLS. Với reporting views nhạy cảm, dùng role owner **ít quyền nhất cần thiết**, không tạo bằng superuser chỉ vì nhanh thao tác.

Cũng cần xem khả năng role sở hữu view **thay đổi định nghĩa view**. View owner bị chiếm quyền có thể mở rộng các cột/row được expose trong giới hạn quyền của nó.

---

## 5. security_invoker: quyền bảng nền theo người thực thi

### 5.1. Có từ PostgreSQL 15

Tùy chọn `security_invoker` cho **view thông thường** được giới thiệu trong PostgreSQL 15. Trước khi dùng:

~~~sql
SHOW server_version;

SELECT current_setting('server_version_num')::integer >= 150000
       AS supports_security_invoker_views;
~~~

Nếu database cũ hơn PostgreSQL 15, không dựa vào cú pháp này; cần nâng cấp hoặc lựa chọn thiết kế quyền/RLS khác được kiểm chứng.

### 5.2. Tạo view với security_invoker

~~~sql
CREATE VIEW reporting.v_paid_payments_invoker
WITH (security_invoker = true)
AS
SELECT payment_id, customer_id, amount
FROM finance.payments
WHERE status = 'paid';
~~~

Khi caller SELECT view:

1. Caller cần `SELECT` trên view và quyền dùng schema view.
2. **Quyền truy cập các base relations** được kiểm tra theo caller như thể chúng được tham chiếu trực tiếp, thay vì theo view owner.
3. Nếu bảng nền có RLS, **các policies áp dụng cho caller** được sử dụng, theo quy tắc RLS/bypass tương ứng.
4. Caller có thể bị từ chối dù view owner có quyền SELECT toàn bộ bảng nền.

### 5.3. Thay đổi view hiện có

~~~sql
ALTER VIEW reporting.v_paid_payments
SET (security_invoker = true);
~~~

Và có thể chuyển về hành vi mặc định:

~~~sql
ALTER VIEW reporting.v_paid_payments
SET (security_invoker = false);
~~~

Thay đổi này có thể khiến **ứng dụng đang chạy mất quyền đọc** hoặc thay đổi tập row được thấy. Không đổi flag trên production mà chưa kiểm tra grant, RLS và tất cả caller roles.

### 5.4. security_invoker không có nghĩa caller được quyền bảng tự động

Một hiểu nhầm phổ biến:

> “Cứ bật security_invoker thì người gọi SELECT view và vẫn được xem dữ liệu dù không có quyền bảng.”

Điều ngược lại mới đúng: khi bật `security_invoker`, caller **phải có quyền cần thiết trên base relations** theo cơ chế kiểm tra invoker. Nếu không, truy vấn có thể báo `permission denied for table ...`.

### 5.5. security_invoker không tự thêm WHERE tenant_id

Nó chỉ thay đổi **người được dùng để kiểm tra quyền và RLS**. Nếu bảng không có RLS và caller đã có SELECT toàn bảng, thì security-invoker view **không tự hạn chế caller khỏi đọc bảng gốc** theo một predicate tenant-specific.

Muốn bảo vệ rows thật sự, cần thiết kế RLS/role grants/policies đúng.

### 5.6. Tùy chọn áp dụng theo view, không theo session

Không có chuyện một session bất kỳ `SET security_invoker=on` để biến tất cả views thành invoker views. Đây là một thuộc tính trên đối tượng view, được lưu trong catalog, quản trị bằng `CREATE VIEW WITH (...)` và `ALTER VIEW ... SET (...)`.

---

## 6. security_barrier: bảo vệ thứ tự thực thi điều kiện bảo mật

### 6.1. Vấn đề với biểu thức bên ngoài view

Giả sử view chỉ cho user xem các row thuộc tenant 10:

~~~sql
CREATE VIEW reporting.v_tenant10 AS
SELECT record_id, tenant_id, public_code
FROM finance.records
WHERE tenant_id = 10;
~~~

Người gọi có thể đặt thêm điều kiện:

~~~sql
SELECT *
FROM reporting.v_tenant10
WHERE suspicious_function(public_code);
~~~

SQL optimizer thường cố đẩy điều kiện lọc xuống sớm để giảm công việc. Nhưng một function do user kiểm soát có thể:

- Phát thông báo lỗi chứa một phần dữ liệu đầu vào.
- Ghi log/raise exception theo giá trị.
- Có side effect quan sát được.
- Dùng thời gian thực thi khác nhau theo input.

Nếu một biểu thức **không an toàn để đánh giá trước khi lọc** bị thực thi trên những row mà predicate view định bảo vệ, user có thể suy luận thông tin về những row đó dù chúng không xuất hiện trong kết quả cuối.

### 6.2. security_barrier được dùng cho điều gì?

Khi view được khai báo:

~~~sql
CREATE VIEW reporting.v_tenant10_safe
WITH (security_barrier = true)
AS
SELECT record_id, tenant_id, public_code
FROM finance.records
WHERE tenant_id = 10;
~~~

PostgreSQL xử lý security-barrier view theo quy tắc không đẩy các toán tử/function **không leakproof** do query bên ngoài đưa vào chạy trước các security qualifications của view theo cách có thể làm rò dữ liệu bị lọc.

### 6.3. Một security-barrier view vẫn có owner/invoker mode riêng

`security_barrier=true` **không đổi** quyền truy cập base table thành invoker. View ở trên **vẫn là default-owner mode** nếu không thêm `security_invoker=true`.

Đây là điểm nhầm lẫn quan trọng nhất giữa hai thuộc tính.

### 6.4. LEAKPROOF có ý nghĩa gì?

PostgreSQL có đặc tính `LEAKPROOF` dành cho function/operator mà optimizer được phép xem là **không phát lộ thông tin ngoài giá trị trả về**. Chỉ role đặc quyền rất cao (thực tế là superuser) mới được khai báo function là LEAKPROOF.

Optimizer có thể đẩy các biểu thức được biết là **leakproof** qua security barrier khi hợp lệ. Vì vậy security_barrier không đồng nghĩa “mọi WHERE phía caller luôn chạy sau tất cả WHERE của view theo đúng thứ tự chữ viết”.

**Không bao giờ** gắn nhãn LEAKPROOF cho function có thể báo lỗi theo dữ liệu, ghi log, có side effects hoặc rò dữ liệu chỉ để planner dùng index nhanh hơn.

### 6.5. Không phụ thuộc thứ tự biểu thức WHERE như một ranh giới bảo mật

~~~sql
WHERE tenant_id = 10
  AND suspicious_function(public_code)
~~~

Không có lời hứa SQL chung rằng điều kiện ở bên trái luôn được đánh giá trước điều kiện ở bên phải. PostgreSQL có thể thay đổi thứ tự cho mục đích tối ưu hóa, theo các ràng buộc an toàn.

Khi quyền truy cập phụ thuộc thứ tự đánh giá, thiết kế **security_barrier/RLS/permissions** phù hợp thay vì chỉ đổi thứ tự câu WHERE.

### 6.6. Một barrier không phải sự cô lập tuyệt đối

`security_barrier` hạn chế một loại rò rỉ qua **predicate pushdown/evaluation order**. Nó không tự ngăn mọi side channel về thời gian, kích thước kết quả, tính chọn lọc, logging, locking, statistics hay những quyền truy cập khác mà user đã có.

Nếu view expose `public_code` của row được phép, người dùng vẫn có thể đọc `public_code` trên những row đó. Barrier không biến cột view thành bí mật.

---

## 7. Bảng so sánh hai tùy chọn

| Nội dung | View mặc định | `security_invoker=true` | `security_barrier=true` |
|---|---|---|---|
| Quyền truy cập view | Caller cần quyền trên view | Caller cần quyền trên view | Caller cần quyền trên view |
| Quyền bảng nền | Theo **view owner** ở các quan hệ thuộc view mặc định | Theo **caller** ở quan hệ nền của invoker view | **Không thay đổi** cơ chế owner/invoker |
| RLS trên bảng nền | Thường xét chính sách theo view owner | Xét theo caller | **Không thay đổi** RLS identity |
| Ngăn đánh giá sớm biểu thức không leakproof của caller qua điều kiện view | Không có ranh giới đặc biệt | Không chỉ nhờ invoker | **Có**, theo security barrier rules |
| Có thay đổi SQL WHERE của view không? | Không | Không | Không |
| Có tự cấp quyền bảng nền cho caller không? | Không | Không | Không |
| Có thể kết hợp hai tùy chọn không? | Không áp dụng | **Có** | **Có** |
| Trường hợp thường dùng | Cấp interface đọc hạn chế trên bảng mà caller không được đọc trực tiếp | View cần tôn trọng base privileges/RLS của caller | View có predicate nhạy cảm, không muốn external leaky quals chạy trước |
| Rủi ro chính | Owner quá mạnh, RLS được áp theo owner | Caller thiếu quyền bảng; có thể thấy dữ liệu khác sau migration | Có thể làm giảm khả năng pushdown và hiệu năng |

### 7.1. Kết hợp cả hai

~~~sql
CREATE VIEW reporting.v_secure
WITH (
    security_invoker = true,
    security_barrier = true
)
AS
SELECT record_id, tenant_id, public_code
FROM finance.records
WHERE is_active = true;
~~~

Khi kết hợp:

- **Invoker mode:** dùng quyền/RLS identity của caller với base relations tương ứng.
- **Barrier mode:** bảo vệ thứ tự evaluation của một số qualifiers ngoài view.

Có lý do để dùng cả hai, nhưng cũng có trường hợp chỉ cần một. Không tự cho rằng bật mọi security option sẽ luôn là lựa chọn tốt nhất: **security model và cost plan phải được review**.

---

## 8. RLS trên bảng nền tương tác với view ra sao?

### 8.1. RLS là cơ chế của bảng, không phải một cột bảo mật trên view

Row-Level Security được bật trên **base table**:

~~~sql
ALTER TABLE finance.records ENABLE ROW LEVEL SECURITY;
~~~

Sau đó định nghĩa policy:

~~~sql
CREATE POLICY visible_records_for_readers
ON finance.records
FOR SELECT
TO report_reader
USING (tenant_id = 10);
~~~

Cú pháp này là minh họa. Phần lab bên dưới cung cấp schema và roles có thể chạy độc lập.

### 8.2. RLS policy phụ thuộc role thực hiện quyền truy cập

Với base table RLS enabled:

- Một user thường không được xem hàng không qua policy cho phép.
- Nếu chưa có policy nào áp dụng, hành vi mặc định thường là **deny** các rows đối với role chịu RLS.
- **Table owner** thường được miễn RLS theo mặc định, trừ khi bảng bật `FORCE ROW LEVEL SECURITY`.
- Superuser và role có `BYPASSRLS` có thể bỏ qua RLS theo đặc quyền.
- `FORCE ROW LEVEL SECURITY` khiến table owner chịu RLS, nhưng không biến superuser/BYPASSRLS thành role thường.

Do đó phải biết **RLS identity** và role attributes khi phân tích một view.

### 8.3. Default-owner view có thể vượt policy dành cho caller

Nếu view owner đồng thời là **table owner**, nó thường bỏ qua RLS. Một reader dù có policy chỉ thấy tenant 10 khi query bảng trực tiếp vẫn có thể thấy **nhiều tenant hơn qua default-owner view** nếu view không tự lọc tenant.

Đó không phải bug trong PostgreSQL. Đó là kết quả của **mô hình quyền theo chủ view**. Đừng sử dụng default-owner view để thay cho RLS per-user mà không hiểu tác động này.

### 8.4. security_invoker view áp RLS của caller

Với `security_invoker=true`, base relations tương ứng được truy cập với quyền/RLS identity của caller; row-level policies của caller có thể thu hẹp tập kết quả thêm so với predicate của view.

Nếu caller là superuser hoặc có `BYPASSRLS`, invoker mode không khiến nó bị RLS ràng buộc như user thường. Security invoker không tự hạ đặc quyền của caller.

### 8.5. Policy không thay cấp quyền SELECT

RLS cho phép role thấy row nào, nhưng role vẫn phải có **relation privilege** phù hợp. Bật policy SELECT không tự cấp quyền SELECT trên table; cần `GRANT` riêng nếu security-invoker view hoặc quyền đọc trực tiếp yêu cầu.

### 8.6. Đừng xây tenant isolation dựa trên GUC do user tùy chỉnh

Một ví dụ policy hay được viết:

~~~sql
USING (tenant_id = current_setting('app.tenant_id')::integer)
~~~

Nếu role truy vấn có thể tùy ý `SET app.tenant_id` thì nó có thể chọn tenant khác và vượt ý định bảo mật. Chỉ dùng session setting làm nguồn tenant identity khi **ứng dụng/hạ tầng ràng buộc nó với danh tính đã xác thực**, cách đặt giá trị không bị khách hàng thao túng và đã có threat model rõ.

Trong phần lab, dùng role-specific policy với tenant ID cố định để kiểm tra dễ hiểu, không dùng custom GUC thiếu kiểm soát.

---

## 9. Lab bảo mật có thể tái tạo: phân biệt owner, caller và RLS

### 9.1. Điều kiện môi trường

Phần lab giả định:

- PostgreSQL **15 trở lên** để dùng `security_invoker`.
- Tài khoản quản trị test có quyền tạo roles và schema, tạo tables, view, policies, thực hiện `SET ROLE` cho các lab roles.
- Database mới hoặc schema `view_lab` chưa tồn tại.
- Bạn không sử dụng tên role `view_lab_owner`, `view_lab_reader` ở môi trường khác.

Các lệnh tạo role là thay đổi **toàn cluster PostgreSQL**, không chỉ schema. Chỉ chạy trên instance thử nghiệm có quyền phù hợp. Không tạo LOGIN/password cho lab roles vì dùng `SET ROLE` trong phiên quản trị.

### 9.2. Tạo roles

Chạy bằng tài khoản quản trị **được phép**:

~~~sql
CREATE ROLE view_lab_owner NOLOGIN;
CREATE ROLE view_lab_reader NOLOGIN;

CREATE SCHEMA view_lab AUTHORIZATION view_lab_owner;
~~~

Role NOLOGIN không thể tự kết nối, nhưng vẫn được dùng để sở hữu đối tượng, nhận grants hoặc mô phỏng quyền bằng `SET ROLE` khi session có quyền chuyển role.

### 9.3. Tạo bảng dưới role owner

~~~sql
SET ROLE view_lab_owner;

CREATE TABLE view_lab.accounts (
    account_id BIGINT PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    region TEXT NOT NULL,
    balance NUMERIC(12,2) NOT NULL,
    internal_code TEXT NOT NULL
);

INSERT INTO view_lab.accounts
    (account_id, tenant_id, region, balance, internal_code)
VALUES
    (1, 10, 'north', 100.00, 'N10-A'),
    (2, 20, 'north', 200.00, 'N20-B'),
    (3, 10, 'south', 300.00, 'S10-C'),
    (4, 20, 'south', 400.00, 'S20-D'),
    (5, 10, 'north', 500.00, 'N10-E');
~~~

Bảng có năm hàng:

| account_id | tenant_id | region | balance | internal_code |
|---:|---:|---|---:|---|
| 1 | 10 | north | 100 | N10-A |
| 2 | 20 | north | 200 | N20-B |
| 3 | 10 | south | 300 | S10-C |
| 4 | 20 | south | 400 | S20-D |
| 5 | 10 | north | 500 | N10-E |

### 9.4. Tạo view owner-mode mặc định

Trong session vẫn ở `SET ROLE view_lab_owner`:

~~~sql
CREATE VIEW view_lab.v_north_default AS
SELECT account_id, tenant_id, region, balance
FROM view_lab.accounts
WHERE region = 'north';

RESET ROLE;
~~~

View expose bốn cột, **không expose internal_code**, và chỉ có predicate `region='north'`.

### 9.5. Grant chỉ trên view

Lệnh sau chạy bằng owner/admin phù hợp; có thể dùng `SET ROLE view_lab_owner` nếu account điều hành có quyền chuyển role:

~~~sql
GRANT USAGE ON SCHEMA view_lab TO view_lab_reader;
GRANT SELECT ON view_lab.v_north_default TO view_lab_reader;
~~~

**Chưa** cấp `SELECT ON view_lab.accounts` cho reader.

### 9.6. Thử đọc view dưới reader

~~~sql
SET ROLE view_lab_reader;

SELECT current_user, session_user;

SELECT account_id, tenant_id, region, balance
FROM view_lab.v_north_default
ORDER BY account_id;

RESET ROLE;
~~~

Kỳ vọng tập `account_id`: **1, 2, 5**.

Đọc được view dù reader **không có SELECT trên bảng nền** vì view dùng mặc định quyền của `view_lab_owner` đối với bảng nền.

### 9.7. Thử đọc bảng gốc: lỗi mong đợi

~~~sql
-- Chạy RIÊNG để quan sát lỗi quyền:
SET ROLE view_lab_reader;

SELECT account_id, tenant_id
FROM view_lab.accounts;

RESET ROLE;
~~~

Lệnh SELECT trực tiếp bảng gốc được kỳ vọng bị từ chối: `permission denied for table accounts`. Nếu công cụ SQL dừng khi gặp lỗi, phải chạy `RESET ROLE` ở một câu lệnh hoặc session khác phù hợp.

Điểm kiểm chứng: **GRANT SELECT view không cấp SELECT table**.

### 9.8. Tránh hiểu nhầm SET ROLE

`SET ROLE view_lab_reader` thay đổi `current_user` để mô phỏng quyền, nhưng `session_user` thường vẫn là role đăng nhập ban đầu. Nếu bạn thực thi từ một account không có quyền chuyển sang `view_lab_reader`, lệnh sẽ báo lỗi — đó là điều kiện quản trị lab, không phải lỗi `security_invoker`.

---

## 10. Bật RLS trên bảng nhưng view mặc định vẫn dùng owner identity

### 10.1. Tạo policy chỉ cho reader thấy tenant 10

Chạy bằng owner:

~~~sql
SET ROLE view_lab_owner;

ALTER TABLE view_lab.accounts ENABLE ROW LEVEL SECURITY;

CREATE POLICY accounts_reader_tenant10
ON view_lab.accounts
FOR SELECT
TO view_lab_reader
USING (tenant_id = 10);

RESET ROLE;
~~~

Policy này cho role reader xem hàng có `tenant_id=10` **khi role reader chịu RLS và có quyền SELECT bảng**. Nó không tự cấp relation privilege.

### 10.2. View mặc định hiện trả những hàng nào?

~~~sql
SET ROLE view_lab_reader;

SELECT account_id,tenant_id,region
FROM view_lab.v_north_default
ORDER BY account_id;

RESET ROLE;
~~~

Kỳ vọng vẫn là **1, 2, 5**.

Tại sao có hàng **2** với `tenant_id=20` dù policy dành cho reader chỉ cho tenant 10?

- View này là **owner-mode**.
- `view_lab_owner` đồng thời sở hữu `view_lab.accounts`.
- **Table owner thường bypass RLS** trừ khi bật FORCE RLS.
- Do đó RLS policy dành cho `view_lab_reader` không phải policy được áp dụng cho bảng nền qua owner-mode view.
- View vẫn lọc `region='north'` nên chỉ trả 1,2,5.

**Bài học bảo mật:** đặt RLS trên base table chưa đủ nếu người dùng cũng có đường truy cập qua một view được chạy dưới owner có quyền vượt RLS.

### 10.3. FORCED RLS thay đổi điều gì?

Khi owner bật:

~~~sql
ALTER TABLE view_lab.accounts FORCE ROW LEVEL SECURITY;
~~~

table owner bình thường sẽ phải chịu RLS. Vì lab chỉ có SELECT policy dành cho `view_lab_reader`, owner có thể không có policy cho phép và view mặc định có thể trả **không hàng** nếu owner không có quyền BYPASSRLS.

Đây là **thay đổi hành vi lớn**; không chạy trên bảng production chỉ để thử. `FORCE ROW LEVEL SECURITY` vẫn không làm superusers hoặc roles có `BYPASSRLS` trở thành subject to policy như role thường.

Nếu thử trong lab, cần có kế hoạch điều chỉnh policies và biết rằng việc thay đổi FORCE RLS sẽ ảnh hưởng các ứng dụng khác dùng table owner.

---

## 11. Tạo security-invoker view và thử quyền nền

### 11.1. Tạo view invoker trên cùng bảng

Chạy bằng owner:

~~~sql
SET ROLE view_lab_owner;

CREATE VIEW view_lab.v_north_invoker
WITH (security_invoker = true)
AS
SELECT account_id, tenant_id, region, balance
FROM view_lab.accounts
WHERE region = 'north';

RESET ROLE;
~~~

### 11.2. Grant view, chưa grant base table

~~~sql
GRANT SELECT ON view_lab.v_north_invoker TO view_lab_reader;
~~~

Thử:

~~~sql
-- Thử RIÊNG: kết quả mong đợi là permission denied.
SET ROLE view_lab_reader;

SELECT account_id,tenant_id,region
FROM view_lab.v_north_invoker
ORDER BY account_id;

RESET ROLE;
~~~

Reader được cấp SELECT view nhưng **chưa có SELECT trên bảng nền**, nên security-invoker view sẽ bị chặn ở base relation privilege check. Đây là khác biệt rõ với `v_north_default`.

### 11.3. Cấp SELECT những cột cần thiết trên bảng nền

~~~sql
GRANT SELECT (account_id, tenant_id, region, balance)
ON view_lab.accounts TO view_lab_reader;
~~~

Không grant `internal_code`.

Lệnh này cho quyền SELECT các cột được view dùng, bao gồm `region` trong predicate; quyền SELECT cột không đồng nghĩa reader được truy cập toàn bộ các cột của accounts.

### 11.4. Thử lại invoker view

~~~sql
SET ROLE view_lab_reader;

SELECT account_id,tenant_id,region,balance
FROM view_lab.v_north_invoker
ORDER BY account_id;

RESET ROLE;
~~~

Kỳ vọng là **1, 5**.

Vì:

- View WHERE chỉ giữ region north.
- RLS policy dành cho `view_lab_reader` chỉ giữ tenant 10.
- Hai điều kiện được kết hợp: **region north AND tenant 10**.
- Row 2 (tenant 20, north) bị loại bởi RLS.

### 11.5. Thử SELECT trực tiếp bảng sau khi đã grant

~~~sql
SET ROLE view_lab_reader;

SELECT account_id,tenant_id,region,balance
FROM view_lab.accounts
ORDER BY account_id;

RESET ROLE;
~~~

Kỳ vọng theo RLS: **1, 3, 5** (mọi region của tenant 10).

Trực tiếp bảng không có WHERE region north của view. Security invoker view không tạo row isolation mới nếu caller vốn đã được phép truy cập bảng; **RLS trên bảng** là ranh giới bảo vệ tenant.

### 11.6. Thử đọc cột không được cấp

~~~sql
-- Thử RIÊNG: bị từ chối theo column privileges.
SET ROLE view_lab_reader;

SELECT internal_code
FROM view_lab.accounts;

RESET ROLE;
~~~

Reader chưa được grant SELECT cột `internal_code`, nên không thể đọc nó trực tiếp.

### 11.7. Tập kết quả so sánh

| Cách truy cập dưới `view_lab_reader` | Kết quả dự kiến | Lý do |
|---|---|---|
| `SELECT v_north_default` | 1, 2, 5 | Owner-mode view; owner bypass RLS |
| `SELECT v_north_invoker` trước grant base | Lỗi quyền bảng nền | Invoker cần quyền trên base |
| `SELECT v_north_invoker` sau grant cột | 1, 5 | View WHERE + reader RLS |
| `SELECT accounts` sau grant cột | 1, 3, 5 | Reader RLS, không có view WHERE |
| `SELECT internal_code FROM accounts` | Lỗi quyền cột | Không được grant SELECT internal_code |

Kết quả dự kiến giả định bạn chạy trong schema lab mới, không thêm role memberships, policies hoặc GRANT khác.

---

## 12. Cùng một view có thể bật cả security_invoker và security_barrier

### 12.1. Tạo view hai thuộc tính

~~~sql
SET ROLE view_lab_owner;

CREATE VIEW view_lab.v_north_secure
WITH (
    security_invoker = true,
    security_barrier = true
)
AS
SELECT account_id,tenant_id,region,balance
FROM view_lab.accounts
WHERE region='north';

RESET ROLE;

GRANT SELECT ON view_lab.v_north_secure TO view_lab_reader;
~~~

### 12.2. Người gọi thấy gì?

~~~sql
SET ROLE view_lab_reader;

SELECT account_id,tenant_id
FROM view_lab.v_north_secure
ORDER BY account_id;

RESET ROLE;
~~~

Kỳ vọng: **1,5**.

Hai thuộc tính có nhiệm vụ khác nhau:

- `security_invoker=true`: quyền base và RLS theo reader.
- `security_barrier=true`: không cho một số external leaky quals được đẩy vượt bộ lọc nội bộ trước khi bảo đảm an toàn.

### 12.3. Chuyển thuộc tính của view đã tồn tại

~~~sql
SET ROLE view_lab_owner;

ALTER VIEW view_lab.v_north_default
SET (security_barrier = true);

RESET ROLE;
~~~

Lệnh này **không** làm `v_north_default` trở thành invoker view. Nó vẫn có thể trả 1,2,5 trong lab vì owner identity, chỉ thay đổi cách optimizer xử lý một số biểu thức bên ngoài.

Nếu muốn đổi cả quyền và barrier:

~~~sql
ALTER VIEW view_lab.v_north_default
SET (security_invoker = true, security_barrier = true);
~~~

Chạy lệnh cuối **chỉ sau khi review tác động quyền/RLS**. Để giữ các kết quả so sánh lab rõ ràng, nên giữ `v_north_default` owner-mode và dùng `v_north_secure` làm đối tượng có hai flag thay vì chạy mọi ALTER đồng thời.

---

## 13. Dùng security_barrier chống một leaky function từ phía caller

### 13.1. Mục tiêu của thí nghiệm

Giả sử view owner chỉ muốn expose `internal_code` của các account **region north**. Function do caller sử dụng trong WHERE có thể phát lỗi khi gặp code bắt đầu bằng chữ `S` (các row region south trong lab).

Ta muốn người dùng không thể dựa vào việc optimizer **đẩy function không leakproof xuống trước điều kiện region** để dò giá trị ở row mà view không cho thấy.

### 13.2. Tạo một hàm cố ý “leaky” trong lab

Chạy bằng owner trên schema lab:

~~~sql
SET ROLE view_lab_owner;

CREATE FUNCTION view_lab.raise_if_south_code(p_code text)
RETURNS boolean
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
AS $fn$
BEGIN
    IF left(p_code, 1) = 'S' THEN
        RAISE EXCEPTION 'A protected code reached the predicate';
    END IF;
    RETURN true;
END;
$fn$;

REVOKE ALL
ON FUNCTION view_lab.raise_if_south_code(text)
FROM PUBLIC;

GRANT EXECUTE
ON FUNCTION view_lab.raise_if_south_code(text)
TO view_lab_reader;

RESET ROLE;
~~~

Đây là một hàm **cố ý báo lỗi dựa trên dữ liệu** để giải thích threat model, không phải hàm nên dùng trong production. Chức năng thông thường chỉ nên trả boolean không rò dữ liệu hoặc được đặt sau security boundary phù hợp.

Function không được gắn `LEAKPROOF`, và việc cố ý báo lỗi khiến nó **không đủ điều kiện** để được coi là leakproof.

### 13.3. Tạo view bảo vệ predicate region

~~~sql
SET ROLE view_lab_owner;

CREATE VIEW view_lab.v_north_codes_barrier
WITH (security_barrier = true)
AS
SELECT account_id,region,internal_code
FROM view_lab.accounts
WHERE region='north';

RESET ROLE;

GRANT SELECT ON view_lab.v_north_codes_barrier
TO view_lab_reader;
~~~

Đây là owner-mode + barrier view. Reader không có quyền trực tiếp SELECT `internal_code` từ bảng nền nhưng được phép xem cột đó **qua view cho row north**. Dùng cấu trúc này chỉ khi exposure north codes là yêu cầu được phép.

### 13.4. Caller thêm leaky predicate

~~~sql
SET ROLE view_lab_reader;

SELECT account_id,internal_code
FROM view_lab.v_north_codes_barrier
WHERE view_lab.raise_if_south_code(internal_code)
ORDER BY account_id;

RESET ROLE;
~~~

Vì view có security barrier và function phía caller **không leakproof**, PostgreSQL không được thực thi function đó trên rows đã bị predicate bảo vệ `region='north'` loại theo cách làm rò code của row south.

Ở dữ liệu mẫu, hàm sẽ không báo lỗi chỉ vì code của row south có chữ S; kết quả dự kiến là các account IDs **1,2,5** nếu reader có quyền như đã grant.

### 13.5. Tại sao không thử bằng cách bỏ barrier trên dữ liệu nhạy cảm?

Một view không có barrier có thể cho optimizer nhiều tự do hơn trong việc reorder/pushdown qualifiers. **Không có bảo đảm** rằng chỉ cần bỏ barrier là query nhỏ sẽ báo lỗi hay lộ dữ liệu trong mọi PostgreSQL version và plan. Dùng `EXPLAIN` để quan sát kế hoạch và đọc quy tắc an toàn; đừng tạo thử nghiệm cố ý rò trên production.

Nếu dữ liệu gốc thực sự nhạy cảm, sự khác biệt về plan là đủ để đánh giá nhu cầu barrier; không cần khởi tạo một function ghi log bí mật.

### 13.6. Barrier không bảo vệ trước function được đặt bên trong định nghĩa view

View owner có thể tự viết logic function vào SELECT/WHERE của view; security_barrier không “sửa” một định nghĩa view vốn chứa function sai hoặc rò dữ liệu. Cần review cả **view definition, function semantics và quyền của owner**.

---

## 14. Query plans và chi phí của security_barrier

### 14.1. Vì sao barrier có thể làm chậm query?

Planner bình thường có thể đẩy một predicate của caller vào scan trên bảng nền để dùng index và lọc sớm. Security barrier giới hạn việc đẩy xuống những biểu thức không leakproof qua ranh giới bảo vệ.

Ví dụ:

~~~sql
SELECT account_id,balance
FROM view_lab.v_north_codes_barrier
WHERE view_lab.raise_if_south_code(internal_code);
~~~

Nếu leaky function rất đắt, nó chỉ nên chạy sau bộ lọc bảo vệ; điều này có thể làm thay đổi thứ tự thực thi và plan so với view không barrier.

### 14.2. So EXPLAIN trên SELECT an toàn

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT account_id
FROM view_lab.v_north_default
WHERE account_id=1;
~~~

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT account_id
FROM view_lab.v_north_secure
WHERE account_id=1;
~~~

Hai view có **security properties khác nhau**, nên không nên diễn giải khác biệt về thời gian chỉ do barrier: RLS identity, row counts và quyền cũng có thể khác. Để đo overhead riêng của barrier, giữ **cùng mode quyền, cùng định nghĩa SELECT** rồi thay chỉ barrier flag trên hai views so sánh.

### 14.3. Những plan có thể gặp

Một plan có thể có:

~~~text
Subquery Scan on v_secure
  Filter: (some_nonleakproof_condition(...))
  -> Seq Scan on accounts
       Filter: (region = 'north' ...)
~~~

hoặc cấu trúc khác tùy PostgreSQL version, statistics, indexes và qualifiers. Đừng coi sự xuất hiện hay vắng mặt của chữ “Subquery Scan” là kiểm thử bảo mật hoàn chỉnh; view rewrite và optimizer có nhiều biến thể.

### 14.4. Các predicates leakproof có thể push xuống

Một số operators built-in được đánh dấu leakproof và có thể được planner sử dụng phía trong barrier khi hợp lệ. Việc này cho phép một số **index conditions** vẫn hữu ích. Không diễn giải `security_barrier` là “PostgreSQL bắt buộc materialize toàn bộ view rồi mới làm mọi WHERE”.

### 14.5. Đo bằng dữ liệu lớn, nhưng không bỏ barrier chỉ để nhanh

Khi view là security boundary cần thiết, không được tắt barrier vì một phép đo đơn lẻ nhanh hơn. Các hướng cải thiện có thể là:

- Tạo index hỗ trợ **predicate nội bộ của view**.
- Giảm số cột và dữ liệu đi qua ranh giới.
- Đơn giản hóa điều kiện lọc bảo vệ nhưng giữ đúng semantics.
- Sử dụng built-in leakproof operators/hàm phù hợp thay cho function tự viết nếu đúng nghiệp vụ.
- Thay đổi mô hình quyền/RLS để giảm nhu cầu view-security boundary khi có cơ sở bảo mật rõ.
- Đo các query quan trọng với `EXPLAIN (ANALYZE, BUFFERS)` và workload đại diện.

**Không gắn LEAKPROOF bừa bãi** để “lấy lại hiệu năng” vì sai nhãn có thể làm mất ý nghĩa barrier.

### 14.6. Không so cost với thời gian một cách trực tiếp

`EXPLAIN` hiển thị estimated `cost` theo đơn vị tương đối; `EXPLAIN ANALYZE` đo actual time theo mili giây. Không lấy cost=500 để nói barrier “mất 500 ms”. Lưu cả Planning Time, Execution Time, buffers, rows và loops trong phép đo trước/sau.

---

## 15. Quyền function là cơ chế riêng với quyền view

### 15.1. Function trong view không được tự cấp quyền EXECUTE

Giả sử view định nghĩa:

~~~sql
CREATE VIEW view_lab.v_masked_accounts AS
SELECT
    account_id,
    view_lab.mask_code(internal_code) AS masked_code
FROM view_lab.accounts
WHERE region='north';
~~~

Đây chỉ là ví dụ về định nghĩa view, **chưa tạo hàm mask_code**.

Khi một function xuất hiện trong view, người gọi view vẫn có thể cần `EXECUTE` trên function đó theo quy tắc function privilege checks. `SELECT` trên view không được coi là quyền gọi mọi function nào đó mà owner muốn dùng.

### 15.2. SECURITY INVOKER function và security_invoker view là hai thuộc tính độc lập

Theo mặc định, function thực thi với quyền của **caller** (`SECURITY INVOKER` của function), không phải “tự động chạy bằng view owner” chỉ vì view default-owner mode.

- View default-owner quyết định quyền relation cho base relations tham chiếu trong view.
- Function `SECURITY INVOKER` dùng quyền caller để chạy function.
- Function `SECURITY DEFINER` dùng quyền function owner khi thực thi.
- Security-barrier view giới hạn việc pushdown external leaky quals.

Không trộn những khái niệm này thành một cờ “chạy bằng owner”.

### 15.3. SECURITY DEFINER function là một đường nâng đặc quyền tiềm ẩn

Một function `SECURITY DEFINER` truy cập dữ liệu bằng quyền function owner có thể vô tình trả về thông tin mà caller không có quyền đọc trực tiếp.

Nếu bắt buộc dùng, cần:

1. Tạo bằng role ít quyền, không bằng superuser nếu không cần.
2. Cố định `search_path` an toàn, dùng tên schema đầy đủ.
3. Không ghép dynamic SQL từ input thiếu kiểm soát.
4. Thu hồi quyền `EXECUTE` rộng (functions thường có default EXECUTE grant cho PUBLIC).
5. Chỉ GRANT EXECUTE cho roles cần thiết.
6. Review RLS/BYPASSRLS và mọi tables/functions mà function gọi.
7. Test SQL injection, search_path object shadowing và quyền trên schema.
8. Xác định kết quả function là gì nếu view owner, table owner và caller khác nhau.

### 15.4. Default EXECUTE cho functions cần được để ý

Không giả định một function mới tạo tự “chỉ owner gọi được”. PostgreSQL có default privileges cho EXECUTE của functions. Mẫu cần review:

~~~sql
REVOKE ALL
ON FUNCTION view_lab.raise_if_south_code(text)
FROM PUBLIC;

GRANT EXECUTE
ON FUNCTION view_lab.raise_if_south_code(text)
TO view_lab_reader;
~~~

Nếu môi trường dùng `ALTER DEFAULT PRIVILEGES`, kiểm tra **đúng role tạo function và schema**; thay đổi default privileges không tự hồi tố các functions đã tồn tại.

### 15.5. RLS policies gọi functions cũng có quyền và rủi ro riêng

Một policy có thể gọi function dựa trên session identity/claim. Function chạy trong ngữ cảnh quyền tương ứng; user truy vấn có thể cần quyền EXECUTE và những quyền nền liên quan nếu function SECURITY INVOKER. Cần tránh policy phụ thuộc function không an toàn hoặc tự tham chiếu bảng gây recursion.

### 15.6. Không phụ thuộc function error message để che dữ liệu

Dù view có barrier, function được phép gọi trên **rows đã expose** vẫn có thể phát lỗi chứa nội dung row đó. Nếu nội dung được expose là dữ liệu công khai theo policy, rò không nằm ở view barrier; nhưng vẫn phải hạn chế log lộ thông tin và các side effects của function.

---

## 16. Nested views: một view bên ngoài không quyết định toàn bộ quyền bên trong

### 16.1. View có thể tham chiếu view khác

~~~text
SELECT của reader
    |
    v
v_outer (security_invoker=true)
    |
    v
v_inner (security_invoker=false)
    |
    v
base_table (RLS enabled)
~~~

Nếu `v_inner` vẫn là default-owner mode, quyền/RLS identity khi truy cập base relation **thông qua v_inner** vẫn theo owner của `v_inner`, dù `v_outer` là invoker view.

Ngược lại, một inner security-invoker view có thể khiến quyền đối với base relations của nó được kiểm tra theo caller kể cả khi outer view không bật invoker. Quan trọng là **mỗi tầng view và đường đi tới base relation**, không phải chỉ một flag ở view ngoài cùng.

### 16.2. Mở rộng lab với outer invoker → inner default

Giữ nguyên `v_north_default` ở owner-mode (hoặc chỉ bật security_barrier, không bật invoker).

~~~sql
SET ROLE view_lab_owner;

CREATE VIEW view_lab.v_outer_invoker
WITH (security_invoker = true)
AS
SELECT account_id,tenant_id
FROM view_lab.v_north_default;

RESET ROLE;

GRANT SELECT ON view_lab.v_outer_invoker TO view_lab_reader;
~~~

Thử:

~~~sql
SET ROLE view_lab_reader;

SELECT account_id,tenant_id
FROM view_lab.v_outer_invoker
ORDER BY account_id;

RESET ROLE;
~~~

Trong lab, vì reader có `SELECT` trên cả `v_outer_invoker` và `v_north_default`, đường qua inner default có thể trả **1,2,5**, không tự thu hẹp còn 1,5 chỉ vì outer invoker.

**Nếu bạn đã ALTER v_north_default SET(security_invoker=true)** ở một thí nghiệm khác thì kết quả sẽ thay đổi. Cần kiểm tra thuộc tính thực tế trước khi diễn giải.

### 16.3. Outer default → inner invoker

Một cấu trúc ngược:

~~~sql
SET ROLE view_lab_owner;

CREATE VIEW view_lab.v_outer_default AS
SELECT account_id,tenant_id
FROM view_lab.v_north_invoker;

RESET ROLE;

GRANT SELECT ON view_lab.v_outer_default TO view_lab_reader;
~~~

`v_north_invoker` vẫn là security-invoker view, nên base relation truy cập qua nó dùng quyền/RLS identity của người thực thi theo quy tắc invoker, kể cả outer là default-owner view. Với reader đã được cấp SELECT các cột nền, kết quả được kỳ vọng là **1,5**.

Không cố suy diễn mọi nested-path đặc biệt chỉ bằng hai ví dụ; khi một view tham chiếu nhiều view/tables/functions với modes khác nhau, hãy **vẽ cây phụ thuộc và kiểm tra từng cạnh**.

### 16.4. Quyền SELECT view trung gian

Khi truy cập view qua view khác, privilege checks trên views trung gian cũng có cơ chế theo owner/invoker tương ứng. Trong ví dụ outer invoker, reader được cấp SELECT inner default. Nếu bỏ grant đó, truy vấn có thể bị từ chối; quyền SELECT outer không tự cấp mọi quyền qua các lớp invoker.

Một nguyên tắc tốt: **không dùng nested view để cố che giấu việc một role chưa có quyền thích hợp**, và phải kiểm thử bằng role thực dưới đúng cây views.

### 16.5. Bảng phân tích nested view

| Đường đi base relation | Identity quyền/RLS khi đọc base |
|---|---|
| Direct table access | Caller, theo quyền và RLS của caller |
| Default-owner view → table | Owner của default-owner view |
| Security-invoker view → table | Caller |
| Outer invoker → inner owner-mode → table | Owner của inner owner-mode view |
| Outer owner-mode → inner invoker → table | Caller theo inner invoker rule |

Bảng là mô hình về **base relation identity**, không có nghĩa quyền gọi tất cả intermediate views và functions đều tự động được cấp.

---

## 17. Kiểm tra security properties từ catalog

### 17.1. pg_class.reloptions

Các view options như `security_invoker=true` và `security_barrier=true` được lưu trong relation options.

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS view_name,
    pg_get_userbyid(c.relowner) AS view_owner,
    c.reloptions
FROM pg_class AS c
JOIN pg_namespace AS n
  ON n.oid=c.relnamespace
WHERE n.nspname='view_lab'
  AND c.relkind='v'
ORDER BY c.relname;
~~~

Ví dụ một view có thể có:

~~~text
{security_invoker=true,security_barrier=true}
~~~

Nếu `reloptions` là NULL, không tự suy ra view đã bật các security options: hành vi mặc định `security_invoker=false` và `security_barrier=false`.

### 17.2. Chuyển reloptions thành cặp key/value

~~~sql
SELECT
    n.nspname,
    c.relname,
    opt.option_name,
    opt.option_value
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid=c.relnamespace
CROSS JOIN LATERAL pg_options_to_table(c.reloptions) AS opt
WHERE n.nspname='view_lab'
  AND c.relkind='v'
ORDER BY c.relname,opt.option_name;
~~~

Query này chỉ hiện những options **được khai báo tường minh**, không có nghĩa những flag không xuất hiện bị vô hiệu hóa bởi policy ngoài.

### 17.3. Xem SQL view

~~~sql
SELECT pg_get_viewdef(
    'view_lab.v_north_secure'::regclass,
    true
) AS definition;
~~~

Cần đọc WHERE, JOIN, function calls, computed columns, LIMIT/aggregates và các base relations. Đừng chỉ xem flag mà bỏ qua chính dữ liệu view expose.

### 17.4. information_schema.views / pg_views

~~~sql
SELECT schemaname,viewname,viewowner,definition
FROM pg_views
WHERE schemaname='view_lab'
ORDER BY viewname;
~~~

Các view catalog cho thông tin định nghĩa; để kiểm tra security_invoker/security_barrier có thể cần `pg_class.reloptions` như ở trên. Không suy rằng SQL view definition chứa đầy đủ ownership/grants/RLS.

### 17.5. Kiểm tra grants bằng has_*_privilege

~~~sql
SELECT
    has_schema_privilege(
        'view_lab_reader','view_lab','USAGE'
    ) AS reader_has_schema_usage,
    has_table_privilege(
        'view_lab_reader','view_lab.v_north_default','SELECT'
    ) AS reader_can_select_default_view,
    has_table_privilege(
        'view_lab_reader','view_lab.v_north_invoker','SELECT'
    ) AS reader_can_select_invoker_view,
    has_column_privilege(
        'view_lab_reader','view_lab.accounts','balance','SELECT'
    ) AS reader_can_select_balance,
    has_column_privilege(
        'view_lab_reader','view_lab.accounts','internal_code','SELECT'
    ) AS reader_can_select_internal_code;
~~~

Những hàm trên kiểm tra **privileges**, không thay một phép thử đầy đủ của **RLS result set** hay security barrier.

### 17.6. Kiểm tra chính sách RLS

~~~sql
SELECT
    schemaname,
    tablename,
    policyname,
    permissive,
    roles,
    cmd,
    qual,
    with_check
FROM pg_policies
WHERE schemaname='view_lab'
ORDER BY tablename,policyname;
~~~

Tất cả policy expressions đều phải được review với role membership, owner, BYPASSRLS và lệnh SQL tương ứng.

### 17.7. Cờ RLS ở bảng

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    pg_get_userbyid(c.relowner) AS table_owner,
    c.relrowsecurity AS rls_enabled,
    c.relforcerowsecurity AS force_rls
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid=c.relnamespace
WHERE n.nspname='view_lab'
  AND c.relname='accounts';
~~~

RLS enabled không chứng minh mọi caller đều bị lọc: phải xét owner bypass và `rolbypassrls`.

### 17.8. Kiểm tra BYPASSRLS

~~~sql
SELECT rolname,rolsuper,rolbypassrls,rolcanlogin
FROM pg_roles
WHERE rolname IN ('view_lab_owner','view_lab_reader')
ORDER BY rolname;
~~~

Chỉ người có quyền cao mới được cấu hình role attributes đặc biệt. Không tự thay `BYPASSRLS` để thử một policy nếu không có quyền và môi trường an toàn.

---

## 18. Chẩn đoán lỗi "permission denied" theo thứ tự

Một ứng dụng báo lỗi:

~~~text
ERROR: permission denied for table accounts
~~~

trong khi DBA nói “đã GRANT SELECT trên view rồi”. Hãy xác định:

1. View có `security_invoker=true` không?
2. User truy cập view là role nào? `current_user`, connection pool role, `SET ROLE`, memberships?
3. Role có `USAGE` schema view và `SELECT` view chưa?
4. Nếu invoker, role có quyền SELECT những cột bảng nền cần thiết chưa?
5. View có tham chiếu các **nested invoker views** hoặc functions cần quyền EXECUTE không?
6. Table có RLS? Lỗi permission denied khác với truy vấn trả **0 rows** do RLS deny.
7. Có `FORCE ROW LEVEL SECURITY` và owner không có policy?
8. Có default privileges, grants từ role membership, `PUBLIC`, hoặc quyền bị REVOKE không?
9. App chạy đúng database/schema/search_path hay đang gọi một view tên giống nhưng owner khác?
10. Migration có ALTER VIEW hoặc đổi owner làm thay đổi identity không?

### 18.1. Quyền trên schema khác quyền bảng

Một lỗi:

~~~text
ERROR: permission denied for schema view_lab
~~~

có thể do thiếu `USAGE` schema chứa view. Không khắc phục bằng cách grant SELECT bảng gốc hoặc tắt security_invoker nếu thiếu schema grant.

### 18.2. View trả 0 rows không đồng nghĩa permission denied

Nếu reader đã có relation privilege nhưng policy không cho rows, SELECT có thể thành công và trả tập rỗng. Phân biệt:

- **Access denied:** PostgreSQL báo lỗi quyền.
- **RLS deny:** query thành công nhưng rows bị lọc (tùy lệnh/policy).
- **View WHERE:** row bị lọc bởi predicate định nghĩa view.
- **Empty table:** không có dữ liệu.
- **Join/filter logic:** query thực sự không còn row.

### 18.3. Cột bị thiếu quyền

Security-invoker view có thể SELECT nhiều cột và filter trên một cột không được GRANT. Có thể xảy ra lỗi ngay cả khi caller chỉ chọn một vài cột output từ view; quyền thực tế còn phụ thuộc các base-table columns và expression đã được dùng.

Đừng cấp `SELECT ON ALL TABLES IN SCHEMA ...` để giải quyết một lỗi cấp cột nếu nhu cầu chỉ là bốn cột của một bảng: grant ít nhất đủ dùng.

---

## 19. Quyền đọc không có nghĩa tự động được phép UPDATE view

### 19.1. Một số views có thể tự động updatable

Một **simple view** trên một bảng có thể cho phép `INSERT`, `UPDATE` và `DELETE` qua view khi PostgreSQL xác định nó là automatically updatable. Views có joins, DISTINCT, GROUP BY, aggregate hoặc một số cấu trúc phức tạp thường không tự động updatable theo cùng cách; có thể cần trigger/rule.

### 19.2. Các quyền ghi là riêng biệt

`GRANT SELECT ON view` không cấp `UPDATE` hoặc `INSERT`.

Với security-invoker view, quyền ghi lên base relations cần được cấp cho caller tương ứng khi DML được rewrite; RLS policies `FOR UPDATE`, `FOR INSERT`, `FOR DELETE` có thể kiểm soát rows/giá trị mới.

### 19.3. WITH CHECK OPTION khác security_barrier

Nếu view cho UPDATE nhưng chỉ muốn rows **sau khi INSERT/UPDATE vẫn đáp ứng WHERE của view**, dùng `WITH CHECK OPTION` khi view đủ điều kiện.

~~~sql
CREATE VIEW some_schema.v_tenant10
WITH (security_invoker = true)
AS
SELECT id,tenant_id,description
FROM some_schema.tasks
WHERE tenant_id=10
WITH LOCAL CHECK OPTION;
~~~

Đây là mẫu cú pháp giả định bảng `some_schema.tasks` tồn tại. `WITH CHECK OPTION` kiểm soát **hàng mới được ghi** có còn visible trong view theo điều kiện tương ứng; nó **không phải** security_barrier và không thay quyền hoặc RLS.

### 19.4. Một lab nhỏ với DML và RLS

Tạo bảng tasks riêng dưới owner:

~~~sql
SET ROLE view_lab_owner;

CREATE TABLE view_lab.tasks (
    task_id BIGINT PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'open'
);

INSERT INTO view_lab.tasks(task_id,tenant_id,title,state)
VALUES
    (1,10,'Chuẩn bị báo cáo','open'),
    (2,20,'Kiểm tra vận hành','open');

ALTER TABLE view_lab.tasks ENABLE ROW LEVEL SECURITY;

CREATE POLICY tasks_reader_select
ON view_lab.tasks
FOR SELECT
TO view_lab_reader
USING (tenant_id=10);

CREATE POLICY tasks_reader_update
ON view_lab.tasks
FOR UPDATE
TO view_lab_reader
USING (tenant_id=10)
WITH CHECK (tenant_id=10);

CREATE VIEW view_lab.v_tenant10_tasks
WITH (security_invoker=true)
AS
SELECT task_id,tenant_id,title,state
FROM view_lab.tasks
WHERE tenant_id=10
WITH LOCAL CHECK OPTION;

RESET ROLE;
~~~

Grant quyền **tối thiểu** cho reader:

~~~sql
GRANT SELECT(task_id,tenant_id,title,state)
ON view_lab.tasks TO view_lab_reader;

GRANT UPDATE(state)
ON view_lab.tasks TO view_lab_reader;

GRANT SELECT
ON view_lab.v_tenant10_tasks TO view_lab_reader;

GRANT UPDATE(state)
ON view_lab.v_tenant10_tasks TO view_lab_reader;
~~~

Thử UPDATE trong transaction lab:

~~~sql
SET ROLE view_lab_reader;

BEGIN;

UPDATE view_lab.v_tenant10_tasks
SET state='closed'
WHERE task_id=1
RETURNING task_id,tenant_id,title,state;

ROLLBACK;

RESET ROLE;
~~~

Trong lab, UPDATE này chỉ tác động task của tenant 10, rồi ROLLBACK giữ dữ liệu ban đầu. Để xác nhận có thể thay `tenant_id` hay không, phải xem **cả column UPDATE privilege**, `WITH CHECK OPTION` và **RLS WITH CHECK**; chỉ một flag view không đủ.

### 19.5. RLS US​ING và WITH CHECK

- `USING` kiểm soát rows được phép thấy/tác động trước thao tác, tùy loại policy.
- `WITH CHECK` kiểm soát giá trị row mới khi INSERT/UPDATE.

Một security-invoker view UPDATE phải đáp ứng privileges và policies tương ứng. `WITH CHECK OPTION` trên view kiểm tra điều kiện của view đối với row mới; cả hai có thể cùng tác động.

### 19.6. Triggers/rules có thể thay đổi bức tranh

Nếu view có `INSTEAD OF` trigger/rules, câu DML có thể được xử lý khác với automatically updatable view. Quyền của function trong trigger (`SECURITY INVOKER/DEFINER`), các bảng ghi thực và logic custom đều phải được audit. Đừng suy rằng `security_invoker` luôn đủ để kiểm soát mọi DML trigger tự viết.

---

## 20. Role membership, quyền kế thừa và PUBLIC

### 20.1. Quyền của một role có thể đến từ membership

User có thể không được grant trực tiếp, nhưng nhận quyền thông qua một role mà nó là thành viên, với cơ chế inheritance/SET role phù hợp phiên bản.

Vì vậy nếu:

~~~sql
SELECT has_table_privilege(
  'view_lab_reader',
  'view_lab.v_north_default',
  'SELECT'
);
~~~

trả true, không thể kết luận chắc chắn có một lệnh GRANT SELECT trực tiếp cho reader; quyền có thể đến từ membership hoặc PUBLIC. Cần kiểm tra ACL và cấu trúc role.

### 20.2. Grant cho PUBLIC có phạm vi rộng

~~~sql
GRANT SELECT ON view_lab.v_north_default TO PUBLIC;
~~~

Không dùng lệnh này trong lab nếu mục tiêu là chỉ cho `view_lab_reader` xem. `PUBLIC` đại diện mọi role hiện tại và tương lai, nên grant nhầm có thể mở rộng phạm vi đọc đáng kể.

### 20.3. ALTER DEFAULT PRIVILEGES

Default privileges có thể ảnh hưởng các view/tables/functions tạo mới. Đừng nhầm:

- `GRANT SELECT ON view_lab.v_north_default TO reader`: một view hiện có.
- `ALTER DEFAULT PRIVILEGES ... GRANT SELECT ON TABLES TO reader`: ảnh hưởng đối tượng tạo **về sau** bởi role tạo đối tượng tương ứng.

Default privileges không tự thay quyền đã cấp trên view cũ.

### 20.4. REVOKE không luôn đủ nếu có grant từ đường khác

Nếu role vẫn được quyền SELECT qua PUBLIC hoặc role membership, `REVOKE SELECT ON ... FROM reader` có thể không làm role mất toàn bộ effective permission. Cần xem ACL/membership và test thực bằng role.

### 20.5. Owner privilege là trường hợp đặc biệt

Chủ sở hữu đối tượng có quyền thay đổi/drop đối tượng theo quy tắc ownership; không thể coi GRANT/REVOKE đơn thuần làm mất mọi quyền quản trị của owner. Thiết kế owner role riêng và hạn chế ai được `SET ROLE` sang owner.

---

## 21. Đổi owner view hoặc table có thể đổi tập dữ liệu được thấy

### 21.1. Đổi owner của view mặc định

~~~sql
-- Dạng cú pháp; không tự chạy trên production:
ALTER VIEW view_lab.v_north_default OWNER TO another_role;
~~~

Nếu security_invoker=false, owner mới có quyền/RLS identity khác đối với bảng nền. Một thay đổi ownership có thể làm view:

- Không còn đọc được base table do thiếu quyền.
- Trả ít rows hơn do RLS.
- Trả nhiều rows hơn nếu owner mới có quyền BYPASSRLS.
- Gọi function với những hiệu ứng phụ thuộc owner/permission khác.

Không đánh giá ownership change như một thay đổi metadata vô hại.

### 21.2. Đổi owner bảng nền

Nếu table owner thay đổi, role nào được miễn RLS theo owner exception cũng thay đổi. Một view owner trước đó đồng thời là table owner có thể không còn bypass RLS theo cơ chế owner exemption.

### 21.3. FORCE ROW LEVEL SECURITY

Bật FORCE RLS có thể làm owner-mode views trở nên nghiêm ngặt hơn, nhưng cũng có thể làm app đọc **0 rows** nếu chưa có policies cho owner. Không coi FORCE là biện pháp “bật là an toàn cho mọi account” khi superuser/BYPASSRLS hoặc cấu trúc policy còn yếu.

### 21.4. Thay đổi search_path và object resolution

View definitions thường lưu references tới relation objects theo metadata của PostgreSQL, nhưng SQL functions, dynamic SQL, SECURITY DEFINER functions và việc tạo/replace views có thể chịu rủi ro liên quan `search_path` nếu dùng tên không được schema-qualified.

Dùng tên schema rõ ràng trong definitions nhạy cảm và đặt `search_path` an toàn ở SECURITY DEFINER functions.

---

## 22. Row isolation thật sự: view filter hay RLS policy?

### 22.1. Khi nào view WHERE đủ?

Nếu ứng dụng chỉ được dùng một reporting view và không thể truy cập bảng nền qua bất kỳ đường nào khác, một owner-mode view có filter cố định + security_barrier có thể tạo một interface giới hạn hữu ích.

Nhưng bạn phải kiểm tra:

- Caller không được cấp SELECT bảng nền qua role khác.
- View owner có quyền cần thiết nhưng không quá rộng.
- Predicate filter không bị bypass qua đường khác/nested view/function.
- Dữ liệu được expose trong SELECT list đúng contract.
- Có barrier nếu threat model có external leaky function qualifiers.

### 22.2. Khi nào RLS phù hợp hơn?

Khi nhiều bảng/views/queries có cùng chính sách tenant isolation per-user, **RLS trên bảng nền** có thể là cơ chế tập trung tốt hơn. Security-invoker views giúp các view tôn trọng RLS identity của caller mà không vô tình áp quyền/policy của owner.

Nhưng RLS cần review:

- Policies theo role và operation.
- `USING` vs `WITH CHECK`.
- Quyền SELECT/INSERT/UPDATE/DELETE.
- Owner/BYPASSRLS và FORCE.
- Role identity của connection pool.
- Cách identity/tenant được ánh xạ và bảo vệ trước spoofing.

### 22.3. Khi nào dùng cả view và RLS?

Ví dụ:

- RLS bảo đảm caller chỉ thấy tenant mà mình được phép.
- View chỉ expose những cột/report fields cần thiết.
- `security_invoker=true` để view không dùng owner vượt RLS của caller.
- `security_barrier=true` nếu view có thêm row restriction nhạy cảm và threat model yêu cầu.

Đây là mô hình **defense in depth**, nhưng không đồng nghĩa vô hiệu hóa mọi rủi ro.

### 22.4. Không dùng view filter tĩnh nếu mỗi caller cần chính sách khác

Một view `WHERE tenant_id=10` chỉ cho tenant 10, không phù hợp cho ứng dụng phục vụ 10.000 tenants nếu mỗi user có policy riêng. Lúc đó thường cần RLS gắn với danh tính xác thực và view invoker/role isolation phù hợp.

### 22.5. Cơ chế quyền của ứng dụng connection pool

Nếu mọi HTTP requests đều chạy dưới **cùng một database role** có SELECT rộng và policy `TO app_role` duy nhất, PostgreSQL không tự phân biệt hai end users của ứng dụng. Cần thiết kế identity propagation an toàn (role mapping, trusted session context hoặc một cơ chế khác) và quy trình reset session state khi connection được tái sử dụng.

**security_invoker chỉ nhìn thấy database role đang thực thi**, không tự biết JWT/user ID nếu không có cơ chế xác thực và ánh xạ đúng.

---

## 23. Kiểm thử quyền và dữ liệu: tập tình huống tối thiểu

Một bài test security view không nên chỉ chạy bằng owner hoặc superuser. Ít nhất cần những caller roles đại diện.

| Test | View / hành động | Kỳ vọng |
|---|---|---|
| 1 | Reader SELECT owner-mode view chưa có SELECT base | Thành công nếu có quyền view/schema |
| 2 | Reader SELECT base chưa được GRANT | Permission denied |
| 3 | Reader SELECT invoker view chưa có SELECT base | Permission denied |
| 4 | Reader SELECT invoker sau GRANT base | Thành công, RLS theo reader |
| 5 | Reader SELECT default view với owner bypass RLS | Có thể thấy row tenant 20 nếu WHERE view cho |
| 6 | Reader SELECT invoker với RLS tenant 10 | Chỉ tenant 10 |
| 7 | Reader SELECT internal_code trực tiếp không có grant cột | Permission denied |
| 8 | Reader SELECT barrier view + leaky function | Function không nhận row bị view loại theo barrier rules |
| 9 | Reader SELECT outer invoker → inner owner-mode | Phải xem identity của inner, không chỉ outer |
| 10 | Reader UPDATE view không có UPDATE grant | Permission denied |
| 11 | Reader UPDATE invoker view có grant nhưng RLS không cho | Không cập nhật row bị từ chối; có thể lỗi CHECK khi row mới trái policy |
| 12 | Quyền view bị REVOKE nhưng có grant PUBLIC/membership | Kiểm tra effective privilege, không suy từ một REVOKE |
| 13 | View owner đổi sang role ít quyền | Có thể mất quyền base hoặc thay tập row |
| 14 | FORCE RLS trên base | Owner thường không bypass theo owner exemption |
| 15 | View thiếu security_barrier, caller function non-leakproof | Có rủi ro evaluation order, không dùng một plan làm bảo chứng |
| 16 | Query qua connection pool chung database role | Chính sách phân theo database role, không tự phân biệt end users |

### 23.1. Đo bằng identity thật

Trong một session test:

~~~sql
SELECT current_user,session_user;
~~~

Nếu dùng `SET ROLE`, đọc cả hai kết quả. Trong app, cần biết role thực tế trên PostgreSQL lúc câu SQL chạy. Một user được gắn tên trong log HTTP không nhất thiết trùng với database role.

### 23.2. Thử cả negative cases

Security test tốt không chỉ chứng minh “user A đọc được dòng A”, mà còn phải chứng minh:

- User A **không** đọc được dữ liệu tenant B.
- User A **không** dùng quyền SELECT trên bảng nền trái chủ đích.
- External query không thể phát lộ row bị view lọc qua function evaluation khi barrier cần thiết.
- User A không thể UPDATE/INSERT vượt check/policy.
- Role B khác hoặc role có membership đặc biệt không vô tình kế thừa đường truy cập.

### 23.3. Phân biệt test quyền với test nội dung

Một truy vấn trả 0 rows có thể do bảng trống hoặc filter, không chứng minh người dùng bị chặn bởi quyền. Tạo dữ liệu sample có **hai tenants và nhiều regions** để có bằng chứng dương/âm rõ ràng, như lab accounts.

---

## 24. Migration từ view mặc định sang security_invoker

### 24.1. Vì sao việc đổi cờ có thể gây sự cố?

Giả sử API đã dùng view mặc định với SELECT grant nhưng không có SELECT base, sau đó DBA:

~~~sql
ALTER VIEW reporting.v_paid_payments
SET (security_invoker=true);
~~~

API có thể ngay lập tức báo `permission denied for table payments`. Nếu DBA phản ứng bằng cách GRANT SELECT toàn bảng để “sửa nhanh”, hệ thống có thể mở thêm một đường đọc dữ liệu nhạy cảm ngoài view.

### 24.2. Quy trình thay đổi có kiểm soát

1. Liệt kê mọi caller roles và các service phụ thuộc view.
2. Kiểm tra PostgreSQL major version hỗ trợ invoker.
3. Kiểm tra view definition, nested views, functions, owner và RLS on base tables.
4. Xác định quyền base columns/relations mà caller sẽ cần.
5. Xác định caller có thể query trực tiếp base table sau khi được grant hay không, và liệu RLS có ngăn vượt phạm vi không.
6. Tạo **view thử nghiệm mới** trong staging hoặc view song song có flag khác.
7. Chạy access tests với các roles đại diện: được phép, bị từ chối và corner cases.
8. So trước/sau cả **row set**, không chỉ số rows và execution time.
9. Đánh giá EXPLAIN/planner nếu có security_barrier hoặc thay đổi RLS.
10. Triển khai grants/policies và flag theo kế hoạch rollback rõ ràng.
11. Giám sát lỗi permission denied và những truy vấn trả 0 rows bất thường.
12. Chỉ dọn view cũ khi tất cả consumers đã chuyển và audit hoàn tất.

### 24.3. Không coi GRANT SELECT toàn bảng là bước mặc định

Nếu mục tiêu ban đầu là **giấu các rows không được phép**, security-invoker view yêu cầu quyền base có thể tạo mâu thuẫn nếu không có RLS thực thi phạm vi đó. Trong một số trường hợp, default-owner view + barrier + không grant base cho reader là thiết kế phù hợp hơn.

Không bật invoker chỉ vì tên chứa chữ “security”.

### 24.4. CREATE OR REPLACE VIEW cũng phải review

Một migration thay SELECT list, WHERE, JOIN, function calls hoặc view options có thể mở rộng kết quả dù object name không đổi. Cần review diff định nghĩa view và dependent permissions, không chỉ xác nhận DDL chạy thành công.

### 24.5. Đổi quyền phải đo cả hiệu năng

RLS policy có thể thêm predicates, làm thay đổi estimates, join order và index choices. Security barrier có thể ảnh hưởng pushdown. Vì vậy migration thành công cần cả:

- **Đúng quyền/dữ liệu.**
- **Không gây regression hiệu năng nghiêm trọng** theo workload, hoặc có plan giảm thiểu.

---

## 25. Theo dõi truy cập và thay đổi cấu hình

### 25.1. Metadata có thể được kiểm tra định kỳ

Một báo cáo định kỳ có thể liệt kê:

- View owner.
- `security_invoker` / `security_barrier` flags.
- Base relations/view dependencies.
- GRANT trên view.
- RLS status của tables nền.
- Policies và roles.
- Các SECURITY DEFINER functions trong đường truy cập nhạy cảm.

### 25.2. Audit các thay đổi quyền

Những thao tác đáng đưa vào change review:

~~~text
GRANT / REVOKE trên view và base table
ALTER VIEW ... SET (security_invoker / security_barrier)
ALTER VIEW ... OWNER TO
CREATE OR REPLACE VIEW
ALTER TABLE ... ENABLE/DISABLE/FORCE ROW LEVEL SECURITY
CREATE/ALTER/DROP POLICY
ALTER ROLE ... BYPASSRLS
CREATE/ALTER FUNCTION ... SECURITY DEFINER / LEAKPROOF
ALTER DEFAULT PRIVILEGES
~~~

Một thay đổi nhỏ trên một lớp có thể tác động tới quyền thực tế khi đi qua nhiều views.

### 25.3. PostgreSQL log và connection monitoring

Có thể dùng logging/audit extension/phương án vận hành được phê duyệt để theo dõi quyền và DDL. Khi ghi lại SQL, view definitions hoặc lỗi, cần bảo vệ dữ liệu nhạy cảm trong literals và query parameters. Không cung cấp quyền đọc toàn bộ system views hoặc query logs cho role không cần thiết.

### 25.4. View không thay backup và audit dữ liệu

Nếu một view được dùng để expose dữ liệu khách hàng, security barrier/invoker không giải quyết data retention, backups, encryption, masking ngoài phạm vi view hay quyền quản trị database. Cần phối hợp nhiều lớp kiểm soát.

---

## 26. Tình huống thiết kế 1: reporting view cho phòng ban khác

### 26.1. Bối cảnh

Bảng `finance.payments` thuộc phòng tài chính. Phòng phân tích cần đọc dữ liệu đã thanh toán gồm `payment_id`, `customer_id`, `amount`, nhưng không được xem số tài khoản ngân hàng hoặc mọi trạng thái thanh toán.

Mục tiêu: consumer **không có quyền SELECT trực tiếp** trên bảng finance.

### 26.2. Một thiết kế có thể phù hợp

~~~sql
-- Thực hiện bằng role owner có SELECT các cột cần thiết:
CREATE VIEW reporting.v_paid_payments
WITH (security_barrier = true)
AS
SELECT payment_id, customer_id, amount
FROM finance.payments
WHERE status='paid';

GRANT USAGE ON SCHEMA reporting TO analysis_reader;
GRANT SELECT ON reporting.v_paid_payments TO analysis_reader;
~~~

Trong trường hợp này view có thể dùng **default owner-mode** để caller không cần được grant SELECT vào bảng finance. `security_barrier` được cân nhắc nếu view WHERE là **bộ lọc an toàn mà user không được phép lách qua leaky quals**.

### 26.3. Những câu hỏi bắt buộc

- Owner của view có quyền đọc finance table nhưng **không phải superuser**?
- analysis_reader có SELECT bảng finance qua một role khác không?
- Có view khác expose dữ liệu chưa paid không?
- Các functions trong view có thể gây leakage/side effects không?
- `status='paid'` đủ chính xác về nghiệp vụ (refund/cancel/tax) không?
- Có ai có quyền ALTER/REPLACE view ngoài nhóm được phép không?

### 26.4. Vì sao security_invoker có thể không phù hợp ở đây?

Nếu bật invoker, analysis_reader cần quyền base relations. Nếu hệ thống không có RLS bảo vệ finance rows và bạn grant SELECT bảng nền, họ có thể truy vấn các rows ngoài điều kiện `status='paid'` bằng một đường khác. Khi mục tiêu là **không cấp bảng nền**, default-owner view được kiểm soát chặt có thể phù hợp hơn.

### 26.5. Barrier không che cột bị SELECT ra

Nếu view vô tình SELECT `bank_account_number`, barrier không giấu cột đó khỏi caller có SELECT view. **Đúng SELECT list và least privilege** vẫn là ưu tiên đầu tiên.

---

## 27. Tình huống thiết kế 2: multi-tenant SaaS với RLS

### 27.1. Bối cảnh

Một ứng dụng có nhiều tenants. PostgreSQL RLS ở bảng dữ liệu chịu trách nhiệm kiểm soát rows theo database identity (hoặc trusted authenticated tenant context).

Ứng dụng muốn tạo views để đơn giản hóa SELECT/reporting, nhưng không muốn owner view có quyền đọc vượt RLS của từng caller.

### 27.2. Thiết kế minh họa

~~~sql
CREATE VIEW api.v_active_orders
WITH (security_invoker=true)
AS
SELECT order_id, tenant_id, total_amount
FROM app.orders
WHERE status='active';
~~~

Trong hệ thống thực, `app.orders` cần chính sách RLS, table grants và identity propagation đúng; lệnh trên chỉ là phần định nghĩa view.

### 27.3. Khi nào nên thêm security_barrier?

Nếu view có một điều kiện bảo vệ nội bộ có thể làm lộ dữ liệu qua external leaky qualifications khi optimizer reorder, cân nhắc:

~~~sql
ALTER VIEW api.v_active_orders
SET (security_barrier=true);
~~~

Nhưng RLS nền vẫn là cơ chế chính giới hạn tenants. Barrier không thay việc xác thực tenant.

### 27.4. Rủi ro connection pool

Nếu mọi requests dùng cùng `app_runtime` database role và policy dựa trên một GUC mà caller có thể sửa, `security_invoker` không tự phân biệt user A/user B. Cần hạ tầng xác thực, quyền ứng dụng và bảo vệ session state hợp lệ.

### 27.5. Kiểm thử

- Tenant A truy vấn view chỉ thấy A.
- Tenant B chỉ thấy B.
- User không có SELECT base columns thì bị từ chối trước khi có quyền.
- Một role đặc quyền không vô tình được dùng cho request thường.
- Khi pool tái sử dụng session, tenant context không bị rò giữa requests.
- Test với nested views có owner-mode phía dưới để tránh đường bypass bất ngờ.

---

## 28. Tình huống thiết kế 3: view cho dữ liệu nhạy cảm có function lọc

### 28.1. Bối cảnh

Một view công khai chỉ trả sự kiện `is_public=true`. Người dùng có thể thêm predicates do họ tự tạo, kể cả functions có tác động phụ hoặc trả lỗi.

### 28.2. Thiết kế cần security barrier

~~~sql
CREATE VIEW public_api.v_public_events
WITH (security_barrier=true)
AS
SELECT event_id, code, created_at
FROM app.events
WHERE is_public=true;
~~~

Mục tiêu của barrier: tránh những qualifiers **không leakproof ở bên ngoài view** được tối ưu chạy trước điều kiện bảo vệ của view theo cách làm lộ thông tin về các row không công khai.

### 28.3. Những điều vẫn phải xử lý

- Caller không có SELECT trực tiếp trên app.events nếu không được phép.
- Cột `code` là dữ liệu được phép expose **trên public rows**.
- View owner có quyền cần thiết nhưng không quá rộng.
- Functions bên trong view được kiểm tra an toàn.
- Vai trò có thể CREATE FUNCTION không tự có quyền đánh dấu function LEAKPROOF.
- Có monitoring error logs và các trường hợp time-based inference khác theo threat model.

### 28.4. Tác động hiệu năng

Một predicate ngoài view sử dụng function không leakproof có thể bị thực thi sau filter bảo vệ, khiến một số index conditions không push xuống được. Cần benchmark và có thể thêm index phù hợp filter nội bộ; không tắt barrier để “ép index” nếu nó bảo vệ dữ liệu thật.

---

## 29. Sơ đồ chọn view-security mode

~~~mermaid
flowchart TD
    A["Thiết kế view cho ứng dụng"] --> B{"Caller có nên có quyền base table?"}
    B -- "Không" --> C["Default owner-mode view"]
    B -- "Có, theo grants/RLS" --> D["security_invoker=true; PostgreSQL 15+"]
    C --> E{"WHERE trong view là boundary cho row nhạy cảm?"}
    D --> F{"Cần chống external leaky quals vượt filter?"}
    E -- "Có" --> G["security_barrier=true"]
    E -- "Không" --> H["Review predicate, columns, owner grants"]
    F -- "Có" --> G
    F -- "Không" --> H
    G --> I["Review function EXECUTE và LEAKPROOF"]
    H --> I
    I --> J{"Base RLS/owner/BYPASSRLS đúng identity?"}
    J -- "Chưa" --> K["Sửa role/policy/grants; không triển khai"]
    J -- "Có" --> L["Test bằng roles thật và negative cases"]
    K --> L
    L --> M["EXPLAIN, benchmark, migration + monitoring"]
~~~

### 29.1. Bốn tổ hợp thường gặp

| `security_invoker` | `security_barrier` | Ý nghĩa chính |
|---|---|---|
| false | false | View thông thường: quyền/RLS base theo owner, optimizer có nhiều tự do hơn |
| false | true | View dùng owner quyền nền nhưng có hàng rào với leaky external quals |
| true | false | View dùng quyền/RLS caller, không thêm barrier cho external quals |
| true | true | View dùng quyền/RLS caller **và** có security barrier |

Không có tổ hợp nào tự giải quyết tất cả các yêu cầu: **role grants, RLS policies, SELECT list, function permissions và owner controls** vẫn là yếu tố bắt buộc.

---

## 30. Những ngộ nhận và lỗi cấu hình cần tránh

| Ngộ nhận / lỗi | Vì sao sai | Hướng xử lý |
|---|---|---|
| “View mặc định dùng quyền người gọi cho bảng nền” | Mặc định dùng quyền view owner | Xem security_invoker |
| “GRANT SELECT view cũng grant SELECT base table” | Hai ACL khác nhau | Kiểm tra từng relation |
| “Caller cần quyền vào mọi schema nền cho default view” | View có đường truy cập gián tiếp qua owner | Phân biệt schema view, base relation checks |
| “Có SELECT view là đủ ngay cả khi invoker=true” | Invoker cần base privileges | GRANT tối thiểu hoặc đổi mô hình |
| “security_invoker cấp quyền bảng cho caller” | Nó đổi identity kiểm tra, không tạo grants | Review RLS và base privileges |
| “security_invoker tự lọc tenant_id” | Nó không thêm WHERE/policy | Tạo RLS/tenant policy |
| “RLS luôn áp policy của caller qua mọi view” | Default owner-mode dùng owner identity | Test owner bypass và invoker |
| “Table owner luôn chịu RLS” | Owner thường bypass trừ FORCE RLS | Xem relforcerowsecurity |
| “FORCE RLS chặn superuser/BYPASSRLS” | Đặc quyền vượt RLS vẫn tồn tại | Giảm quyền và test roles |
| “Policy SELECT tự cấp SELECT privilege” | Policy và GRANT là hai lớp khác | Cấp đúng cả hai |
| “security_barrier thay cơ chế quyền owner” | Barrier không đổi owner/invoker | Bật đúng flag theo yêu cầu |
| “security_barrier nghĩa tuyệt đối không pushdown predicate” | Leakproof quals có ngoại lệ | Hiểu LEAKPROOF và EXPLAIN |
| “Viết WHERE A AND B thì A chắc chắn chạy trước” | SQL planner có thể reorder | Dùng security boundary đúng |
| “Bỏ barrier chắc chắn làm function leak trong mọi thử nghiệm” | Plan tùy optimizer/data | Kiểm thử threat model, không dựa một plan |
| “Barrier ngăn mọi side channel” | Nó chỉ xử lý lớp evaluation-order leakage | Defense in depth |
| “Caller bị chặn bảng nhưng vẫn có quyền function tự do” | Function EXECUTE có ACL riêng | Audit functions |
| “Function trong view chạy như view owner” | SECURITY INVOKER/DEFINER function độc lập | Review function definition |
| “SECURITY DEFINER mặc định an toàn” | Có rủi ro search_path/dynamic SQL/bypass | Least privilege, REVOKE PUBLIC |
| “LEAKPROOF chỉ là cách tối ưu hiệu năng” | Gắn sai có thể phá ranh giới bảo mật | Chỉ dùng cho function thật sự leakproof |
| “Outer view invoker làm mọi inner view invoker” | Inner owner-mode có semantics riêng | Vẽ đường phụ thuộc |
| “GRANT SELECT whole table là sửa lỗi invoker tốt nhất” | Có thể mở đường đọc ngoài view | Column grants + RLS hoặc owner-mode |
| “SELECT trả 0 row nghĩa không có quyền” | Có thể do RLS/view WHERE | Phân biệt lỗi và empty result |
| “VIEW SELECT grant cũng cho UPDATE view” | DML quyền riêng | GRANT UPDATE/INSERT phù hợp |
| “security_barrier là WITH CHECK OPTION” | Một cái là evaluation order, một cái là DML row check | Dùng đúng semantics |
| “UPDATE view không cần quyền/policy base khi invoker” | Invoker dùng base privileges/policies | Review UPDATE/USING/WITH CHECK |
| “REVOKE trực tiếp chắc chắn hết quyền” | PUBLIC/membership có thể vẫn cấp quyền | Kiểm tra effective ACL |
| “Đổi owner chỉ đổi metadata” | Base access/RLS identity có thể thay | Security review + regression tests |
| “Views luôn nhanh như direct SELECT” | Barrier/RLS/rewrite có thể đổi plan | EXPLAIN và benchmark |
| “View là security boundary dù caller có SELECT base” | Đường base vẫn tồn tại | Thu hẹp grants/RLS |
| “Một database role chung tự phân biệt HTTP users” | PostgreSQL chỉ biết database identity/trusted context | Identity propagation an toàn |
| “CREATE OR REPLACE không ảnh hưởng quyền” | Definition/functions/rows/columns có thể đổi | Review diff và test |
| “Chỉ kiểm tra bằng superuser là đủ” | Superuser bypass nhiều hạn chế | Test bằng caller role thật |

---

## 31. Checklist trước khi cấp quyền một view nhạy cảm

### 31.1. Định nghĩa và ownership

- [ ] View SELECT list chỉ expose những cột được phép.
- [ ] WHERE/JOIN thể hiện chính xác row-level business rules.
- [ ] View owner là role ít quyền cần thiết, không superuser khi không cần.
- [ ] Chỉ nhóm được phép có thể ALTER VIEW/OWNER/REPLACE.
- [ ] Đã xác định PostgreSQL major version.
- [ ] Đã xem `security_invoker`, `security_barrier` trên catalog.

### 31.2. Quyền truy cập

- [ ] Caller có `USAGE` schema chứa view.
- [ ] Caller có đúng `SELECT/INSERT/UPDATE/DELETE` trên view theo nhu cầu.
- [ ] Nếu invoker, caller có base-table/base-column privileges cần thiết.
- [ ] Không vô tình grant SELECT nhạy cảm trực tiếp qua membership hoặc PUBLIC.
- [ ] Đã kiểm tra quyền EXECUTE của functions.
- [ ] Đã audit SECURITY DEFINER functions và search_path.

### 31.3. RLS

- [ ] Bảng nền có ENABLE ROW LEVEL SECURITY khi cần.
- [ ] Policies đúng role và operation.
- [ ] RLS owner bypass được hiểu rõ.
- [ ] `FORCE ROW LEVEL SECURITY` có được dùng không?
- [ ] Owner/caller có `BYPASSRLS` hoặc superuser?
- [ ] Tenant identity được xác thực, không thể tự SET giả mạo.
- [ ] Connection pool reset/role switching được xử lý an toàn.

### 31.4. Barrier và performance

- [ ] View WHERE là security boundary hay chỉ filter nghiệp vụ thông thường?
- [ ] Có external user-defined/leaky expressions trong threat model?
- [ ] Nếu cần, đã bật `security_barrier=true`.
- [ ] Không gắn LEAKPROOF tùy tiện.
- [ ] Đã so plan với dữ liệu và caller roles đại diện.
- [ ] Đã đo Planning Time, Execution Time và BUFFERS.
- [ ] Không loại bỏ barrier chỉ vì regression hiệu năng khi chưa có phương án bảo vệ tương đương.

### 31.5. Triển khai và kiểm thử

- [ ] Có test đọc được **đúng rows** và **không đọc được rows bị cấm**.
- [ ] Có test lỗi quyền khi grant thiếu.
- [ ] Có test nested views và function calls.
- [ ] Có test UPDATE/INSERT/CHECK OPTION nếu view writable.
- [ ] Có rollback cho ALTER VIEW/GRANT/RLS policy changes.
- [ ] Có logging/audit phù hợp mà không lộ dữ liệu nhạy cảm.

---

## 32. Bài tập thực hành

Các bài dùng lab `view_lab` nếu không ghi khác. Mọi câu thử lỗi nên chạy **riêng**; PostgreSQL client có thể dừng chuỗi statement khi một câu lỗi. Các lệnh liên quan quyền nên thực hiện trong instance thử nghiệm, không chạy theo thói quen trên production.

### Bài 1 — Quyền trực tiếp và quyền qua view

Một reader có `USAGE` schema view và `SELECT` view, nhưng không có SELECT bảng nền. Reader có thể đọc default-owner view không? Có thể đọc base table trực tiếp không?

### Bài 2 — View owner là ai?

Viết SQL xem owner của `view_lab.v_north_default` từ `pg_class` và `pg_namespace`.

### Bài 3 — Tạo view mặc định

Viết SQL tạo `view_lab.v_north_2` chỉ trả `account_id`, `balance` của các rows `region='north'`, dưới quyền `view_lab_owner`. Cần grant gì để reader gọi được?

### Bài 4 — Chỉ GRANT view

Viết lệnh cấp `USAGE` schema `view_lab` và `SELECT` `v_north_default`, không grant bảng nền. Nếu role đã có các grants, lệnh GRANT lặp lại có ảnh hưởng gì?

### Bài 5 — Kiểm thử owner-mode

Với dữ liệu lab, `v_north_default` trả những account IDs nào cho reader **trước khi bật RLS**?

### Bài 6 — Bật RLS

Viết SQL bật RLS cho `view_lab.accounts` và policy SELECT cho `view_lab_reader` chỉ có `tenant_id=10`. Policy này có tự grant SELECT table không?

### Bài 7 — Owner bypass RLS

Tại sao sau bài 6, default-owner view vẫn có thể trả account 2 (tenant 20), dù reader policy chỉ cho tenant 10?

### Bài 8 — CREATE VIEW security_invoker

Viết SQL tạo view `view_lab.v_tenant10_invoker` với `security_invoker=true`, có filter `tenant_id=10` và các cột `account_id,tenant_id,balance`.

### Bài 9 — Caller chưa có quyền bảng

Nếu reader chỉ có SELECT view invoker nhưng không SELECT bảng nền, có thể SELECT view thành công không? Nếu lỗi, đây là vấn đề RLS hay base privileges?

### Bài 10 — Column privileges

Viết GRANT các cột `account_id,tenant_id,balance` của `accounts` cho reader để dùng `v_tenant10_invoker`, không grant `internal_code`.

### Bài 11 — Kết quả reader RLS

Với `v_north_invoker` sau khi grant những cột cần thiết, reader thấy account IDs nào? Vì sao row 3 tenant 10 không xuất hiện?

### Bài 12 — Kết quả direct table

Sau grant cột và policy tenant 10, reader SELECT trực tiếp `account_id,tenant_id,region,balance` từ accounts thấy những IDs nào? Tại sao khác view invoker north?

### Bài 13 — Cột bị cấm

Nếu reader SELECT `internal_code` trực tiếp, kết quả gì? Có thay đổi nếu người dùng có thể đọc internal_code của một số row qua owner-mode view được GRANT riêng?

### Bài 14 — Cờ version

Viết query kiểm tra PostgreSQL server có hỗ trợ `security_invoker` view (PG15+) không.

### Bài 15 — Thay flag của view

Viết lệnh bật `security_invoker` trên `v_north_default`. Nêu hai loại thay đổi có thể xảy ra với ứng dụng.

### Bài 16 — Tạo barrier view

Viết SQL tạo view `view_lab.v_north_balance_barrier` với `security_barrier=true`, lọc region north. Cờ này có làm quyền bảng nền chuyển sang caller không?

### Bài 17 — Kết hợp hai cờ

Viết `CREATE VIEW` có cả `security_invoker=true` và `security_barrier=true`.

### Bài 18 — Leaky function

Giải thích function báo lỗi theo giá trị input vì sao không leakproof. Security barrier liên quan điều gì tới function này khi function nằm trong WHERE bên ngoài view?

### Bài 19 — LEAKPROOF

Ai có thể khai báo một function là LEAKPROOF? Tại sao không nên khai báo một function tự viết có logging/RAISE EXCEPTION như vậy để tăng tốc index?

### Bài 20 — Không bảo đảm thứ tự WHERE

Vì sao `WHERE tenant_id=10 AND f(code)` không tự bảo đảm `f` luôn được chạy sau điều kiện tenant? Khi mục tiêu là bảo vệ row, nên dùng cơ chế gì?

### Bài 21 — catalog reloptions

Viết SQL xem `security_invoker` và `security_barrier` được lưu trong reloptions của các views thuộc schema view_lab.

### Bài 22 — Xem RLS policies

Viết SQL liệt kê policies của `view_lab.accounts` và cờ `relrowsecurity`/`relforcerowsecurity`.

### Bài 23 — Quyền theo user

Viết query dùng `has_table_privilege` và `has_column_privilege` kiểm tra quyền SELECT view và SELECT cột balance, internal_code của reader.

### Bài 24 — Nested views A

Outer view bật invoker tham chiếu inner default-owner, inner tham chiếu accounts. Quyền/RLS identity cho accounts theo ai? Reader chỉ có quyền outer view có đủ chưa?

### Bài 25 — Nested views B

Outer view default-owner tham chiếu inner security-invoker view. Base relation được kiểm tra theo ai khi reader gọi outer view?

### Bài 26 — Quyền function

Một view chứa function `view_lab.mask_code(internal_code)`. Vì sao `GRANT SELECT ON view` không đồng nghĩa caller được phép gọi function nếu thiếu `EXECUTE`? Vai trò của SECURITY DEFINER là gì?

### Bài 27 — SECURITY DEFINER

Nêu ít nhất năm biện pháp cần có khi function SECURITY DEFINER đọc bảng nhạy cảm rồi được gọi qua một view.

### Bài 28 — Permission denied vs empty result

Reader chạy SELECT view và nhận lỗi permission denied, còn một reader khác SELECT được nhưng không có rows. Hai trường hợp có chắc chung nguyên nhân không?

### Bài 29 — FORCED RLS

Bật `FORCE ROW LEVEL SECURITY` có tác động gì tới table owner? Nó có bắt superuser hoặc BYPASSRLS tuân thủ policy như role thường không?

### Bài 30 — Updatable view

Giải thích khác nhau giữa `GRANT UPDATE`, `WITH CHECK OPTION` và `security_barrier` khi người dùng UPDATE một view đơn giản.

### Bài 31 — RLS UPDATE

Trong `view_lab.tasks` có policies SELECT và UPDATE cho tenant 10. Nếu reader cố UPDATE row tenant 20, điều gì có thể xảy ra? Nếu muốn đổi tenant_id của row tenant 10 sang 20, cần xem hai loại kiểm tra nào?

### Bài 32 — Cảnh báo PUBLIC

Viết một grant không nên dùng nếu muốn chỉ một role đọc dữ liệu (`GRANT SELECT ... TO PUBLIC`) và giải thích phạm vi PUBLIC.

### Bài 33 — Đổi view owner

Vì sao `ALTER VIEW ... OWNER TO` có thể thay đổi kết quả SELECT/RLS dù SQL definition không đổi?

### Bài 34 — Connection pool

Mọi API calls dùng một database role, RLS policy dựa trên `current_setting('app.tenant_id')` do client tự SET được. Có an toàn không? security_invoker có sửa vấn đề không?

### Bài 35 — Performance barrier

Một query sau khi bật `security_barrier` chậm hơn vì nonleakproof predicate không được push xuống. Có nên tắt barrier? Nêu ít nhất bốn hướng cải thiện an toàn hơn.

### Bài 36 — Lập kế hoạch migration

Một default-owner reporting view đang được 12 services sử dụng, chỉ grant SELECT view cho service roles. Đề xuất quy trình chuyển sang security_invoker mà không vô tình grant đọc toàn bảng hoặc gây downtime.

### Bài 37 — Chọn thiết kế

Chọn owner-mode, invoker-mode, barrier hay kết hợp cho ba tình huống:

1. Báo cáo chỉ cho phòng kinh doanh xem đơn đã thanh toán, không cấp quyền bảng gốc.
2. SaaS nhiều tenants có RLS đúng theo database role, view chỉ giúp đơn giản hóa SQL.
3. Một public view giới hạn `is_public=true`, untrusted users có thể thêm function predicates.

### Bài 38 — Tự đánh giá một security view

Viết checklist tối thiểu cho `reporting.v_customer_stats`: SQL definition, owner, grants, RLS, function permissions, nested views, barrier, runtime tests và rollout/rollback. Phân biệt mục tiêu **đúng quyền** với **hiệu năng**.

---

## 33. Gợi ý lời giải

### Bài 1 — Quyền qua view

Nếu caller có `USAGE` schema chứa view và `SELECT` trên **default-owner view**, PostgreSQL kiểm tra quyền bảng nền qua **view owner**, nên caller có thể đọc view dù không có SELECT bảng nền. Caller truy cập trực tiếp base table vẫn cần quyền bảng phù hợp và schema access; nếu chưa có sẽ gặp lỗi quyền.

### Bài 2 — View owner

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS view_name,
    pg_get_userbyid(c.relowner) AS owner_name
FROM pg_class AS c
JOIN pg_namespace AS n
  ON n.oid=c.relnamespace
WHERE n.nspname='view_lab'
  AND c.relname='v_north_default'
  AND c.relkind='v';
~~~

Kỳ vọng owner là `view_lab_owner` nếu đã tạo view bằng `SET ROLE view_lab_owner` như lab.

### Bài 3 — Default view

~~~sql
SET ROLE view_lab_owner;

CREATE VIEW view_lab.v_north_2 AS
SELECT account_id,balance
FROM view_lab.accounts
WHERE region='north';

RESET ROLE;

GRANT USAGE ON SCHEMA view_lab TO view_lab_reader;
GRANT SELECT ON view_lab.v_north_2 TO view_lab_reader;
~~~

Không cần grant SELECT bảng nền cho reader trong **default owner-mode**. Nếu RLS enabled, owner bypass/policy vẫn phải được đánh giá.

### Bài 4 — Grant chỉ trên view

~~~sql
GRANT USAGE ON SCHEMA view_lab TO view_lab_reader;
GRANT SELECT ON view_lab.v_north_default TO view_lab_reader;
~~~

GRANT cùng quyền lặp lại thường không tạo thêm “hai bản quyền” độc lập và không cấp quyền bảng nền. Tuy nhiên phải xem người cấp grant hợp lệ, memberships và các ACL khác.

### Bài 5 — Default-owner trước RLS

~~~sql
SELECT account_id
FROM view_lab.v_north_default
ORDER BY account_id;
~~~

Với lab ban đầu và quyền view phù hợp, kết quả là **1,2,5** vì các row có `region='north'`.

### Bài 6 — Bật RLS

~~~sql
SET ROLE view_lab_owner;

ALTER TABLE view_lab.accounts ENABLE ROW LEVEL SECURITY;

CREATE POLICY accounts_reader_tenant10_answer
ON view_lab.accounts
FOR SELECT
TO view_lab_reader
USING (tenant_id=10);

RESET ROLE;
~~~

Nếu policy tương đương đã tồn tại, không cần tạo lặp ở lab. Policy không grant SELECT; nếu muốn reader truy cập bảng qua security-invoker view, cần relation/column GRANT riêng.

### Bài 7 — Table owner bypass

Default-owner view dùng **quyền và RLS identity của view_lab_owner** đối với bảng nền. Role này đồng thời là table owner, thường bỏ qua RLS nếu chưa FORCE RLS. Do view chỉ lọc region north, row 2 tenant 20 vẫn xuất hiện. Reader policy tenant10 không được áp như với invoker view.

### Bài 8 — Tạo invoker view

~~~sql
SET ROLE view_lab_owner;

CREATE VIEW view_lab.v_tenant10_invoker
WITH (security_invoker=true)
AS
SELECT account_id,tenant_id,balance
FROM view_lab.accounts
WHERE tenant_id=10;

RESET ROLE;

GRANT SELECT ON view_lab.v_tenant10_invoker TO view_lab_reader;
~~~

View dùng base relation privileges và RLS của caller, không tự cấp SELECT trên accounts.

### Bài 9 — Chưa được grant base

Không. Nếu reader chỉ có SELECT view invoker và thiếu SELECT các base columns cần thiết, query thường báo **permission denied for table accounts**. Đây trước hết là lỗi **base relation privileges**, không phải bằng chứng RLS đã lọc hết rows. RLS có thể cho 0 rows khi relation privilege đã hợp lệ.

### Bài 10 — Column privileges

~~~sql
GRANT SELECT (account_id,tenant_id,balance)
ON view_lab.accounts TO view_lab_reader;
~~~

Đủ các cột cho `v_tenant10_invoker` của bài 8, không bao gồm `internal_code`. Để dùng `v_north_invoker` ở lab, reader còn cần `region` do view SELECT/lọc bằng region; grant đầy đủ những cột thực sự được dùng.

### Bài 11 — Invoker north và RLS

Reader thấy **1,5**:

- RLS `tenant_id=10` cho các row 1,3,5.
- View `region='north'` cho các row 1,2,5.
- Giao của hai tập là 1,5.

Row 3 là tenant 10 nhưng **south**, nên bị điều kiện view loại.

### Bài 12 — Đọc bảng trực tiếp sau grant

~~~sql
SET ROLE view_lab_reader;

SELECT account_id,tenant_id,region,balance
FROM view_lab.accounts
ORDER BY account_id;

RESET ROLE;
~~~

Kỳ vọng **1,3,5** (tất cả rows tenant 10); view north chỉ trả 1,5 vì thêm điều kiện `region='north'`. Đây là ví dụ cho thấy view filter và RLS policy là hai điều kiện riêng.

### Bài 13 — Cột trực tiếp không được phép

~~~sql
SELECT internal_code FROM view_lab.accounts;
~~~

dưới reader thường báo lỗi quyền cột nếu không được GRANT. Tuy nhiên nếu owner-mode view **cố tình expose internal_code của một tập row**, và reader có SELECT view đó, reader có thể đọc **giá trị được view expose** dù không được SELECT cột đó trực tiếp trong bảng nền. Đây là thiết kế interface có kiểm soát, cần review đúng phạm vi.

### Bài 14 — Version check

~~~sql
SELECT
    current_setting('server_version') AS version_text,
    current_setting('server_version_num')::integer >= 150000
        AS has_security_invoker_view_option;
~~~

PostgreSQL 15+ hỗ trợ `security_invoker` của view thường. Đối với môi trường cũ, không cố dùng cú pháp.

### Bài 15 — Bật invoker cho view cũ

~~~sql
ALTER VIEW view_lab.v_north_default
SET (security_invoker=true);
~~~

Hai tác động có thể xảy ra:

1. **Permission denied** nếu caller chưa có quyền SELECT base relations/cột cần thiết.
2. **Tập row thay đổi** khi RLS được áp theo caller thay vì owner.

Trong lab nếu đã grant đủ cột và RLS tenant10, kết quả từ 1,2,5 có thể thành 1,5. Đây là thay đổi lớn cần migration có kiểm thử.

### Bài 16 — Barrier view

~~~sql
SET ROLE view_lab_owner;

CREATE VIEW view_lab.v_north_balance_barrier
WITH (security_barrier=true)
AS
SELECT account_id,region,balance
FROM view_lab.accounts
WHERE region='north';

RESET ROLE;

GRANT SELECT ON view_lab.v_north_balance_barrier
TO view_lab_reader;
~~~

Barrier không đổi cơ chế bảng nền theo owner: vì không bật `security_invoker`, view vẫn ở default-owner mode. Nó bổ sung quy tắc an toàn với các external non-leakproof qualifiers.

### Bài 17 — Cả hai flag

~~~sql
SET ROLE view_lab_owner;

CREATE VIEW view_lab.v_north_both_flags
WITH (
    security_invoker=true,
    security_barrier=true
)
AS
SELECT account_id,tenant_id,region,balance
FROM view_lab.accounts
WHERE region='north';

RESET ROLE;
~~~

Cần GRANT SELECT view và base-table columns tương ứng cho caller. Trong lab với reader RLS tenant10, sau grant phù hợp kết quả dự kiến 1,5.

### Bài 18 — Leaky function

Function có thể `RAISE EXCEPTION`, log dữ liệu, tạo tác động phụ hoặc mất thời gian khác nhau theo giá trị là **non-leakproof**. Nếu caller đưa function đó vào WHERE bên ngoài một view lọc rows nhạy cảm, planner không được đẩy nó qua **security barrier** để chạy trên rows chưa qua điều kiện bảo vệ theo cách rò dữ liệu. Barrier không cấm gọi function trên **những rows view cho phép**.

### Bài 19 — LEAKPROOF

Chỉ role đặc quyền **superuser** có thể khai báo một function là LEAKPROOF. Function thật sự leakproof không được tiết lộ dữ liệu ngoài kết quả trả về, kể cả qua errors hay side effects. Gắn LEAKPROOF sai để optimizer pushdown nhanh hơn có thể làm lộ rows bị view/RLS bảo vệ — vi phạm security model.

### Bài 20 — Thứ tự WHERE

SQL không bảo đảm phép AND đánh giá theo thứ tự viết từ trái sang phải; optimizer có thể reorder khi hợp lệ. Khi điều kiện A có ý nghĩa **bảo vệ thông tin**, phải dùng RLS/permissions và `security_barrier` khi threat model có external leaky quals, thay vì chỉ đặt A đứng trước B.

### Bài 21 — Xem reloptions

~~~sql
SELECT
    c.relname AS view_name,
    c.reloptions,
    pg_get_userbyid(c.relowner) AS owner_name
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid=c.relnamespace
WHERE n.nspname='view_lab'
  AND c.relkind='v'
ORDER BY c.relname;
~~~

`reloptions` hiển thị flags được set tường minh. Một view không có tùy chọn thường có `reloptions IS NULL`, tương ứng các defaults.

### Bài 22 — RLS metadata

~~~sql
SELECT
    schemaname,tablename,policyname,
    permissive,roles,cmd,qual,with_check
FROM pg_policies
WHERE schemaname='view_lab'
  AND tablename='accounts';
~~~

~~~sql
SELECT
    c.relname,c.relrowsecurity,c.relforcerowsecurity
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid=c.relnamespace
WHERE n.nspname='view_lab'
  AND c.relname='accounts';
~~~

Bên cạnh đó cần kiểm tra table owner và BYPASSRLS role attributes; chỉ thấy RLS enabled chưa đủ kết luận chính sách thực tế áp cho owner.

### Bài 23 — Kiểm tra quyền

~~~sql
SELECT
    has_table_privilege(
        'view_lab_reader',
        'view_lab.v_north_default',
        'SELECT'
    ) AS can_read_view,
    has_column_privilege(
        'view_lab_reader',
        'view_lab.accounts',
        'balance',
        'SELECT'
    ) AS can_read_balance,
    has_column_privilege(
        'view_lab_reader',
        'view_lab.accounts',
        'internal_code',
        'SELECT'
    ) AS can_read_internal_code;
~~~

Hàm `has_column_privilege` cho thông tin về quyền SELECT cột, **không** mô phỏng toàn bộ các RLS policy conditions. Test dữ liệu dưới đúng role vẫn cần thiết.

### Bài 24 — Outer invoker → inner owner-mode

Base table truy cập **thông qua inner default-owner view** theo quyền/RLS identity của **owner inner view**, không tự theo reader chỉ vì outer bật invoker. Caller có thể cần SELECT trên inner view vì outer invoker dùng quyền caller ở tầng view được tham chiếu, tùy cấu trúc quyền.

Không coi `GRANT SELECT outer` là bằng chứng caller có toàn bộ quyền cần qua mọi nested invoker path.

### Bài 25 — Outer default → inner invoker

Base table truy cập qua **inner security-invoker view** theo identity của **người thực thi truy vấn** theo quy tắc invoker, dù outer view default-owner. Nếu reader có base-table grants và RLS tenant10, output bên dưới chịu policy của reader.

### Bài 26 — Functions trong view

`GRANT SELECT` trên view kiểm soát khả năng truy cập view. Function được gọi trong view có quyền `EXECUTE` riêng, và SQL function invocation không tự được cấp EXECUTE chỉ nhờ quyền view.

Function `SECURITY INVOKER` (mặc định) thực thi với quyền caller. Function `SECURITY DEFINER` thực thi với quyền owner function, tạo một đường nâng quyền cần kiểm toán. Đây là flag **của function**, khác `security_invoker` của view.

### Bài 27 — SECURITY DEFINER hardening

Ít nhất:

1. Dùng function owner ít quyền cần thiết.
2. Cố định `search_path` an toàn và schema-qualify relation names.
3. Không build dynamic SQL từ input thiếu quote/validation.
4. `REVOKE EXECUTE ... FROM PUBLIC` khi function nhạy cảm.
5. GRANT EXECUTE chỉ roles cần thiết.
6. Kiểm tra RLS owner/BYPASSRLS và các bảng function có thể đọc.
7. Test injection, shadowing và concurrent permissions.
8. Audit định nghĩa function sau mỗi deployment.
9. Thiết kế output không expose secrets ngoài contract.

### Bài 28 — Lỗi quyền và tập rỗng

Không chắc chung nguyên nhân. Permission denied xảy ra khi role thiếu privileges cần thiết. Query thành công nhưng trả 0 rows có thể do view WHERE, RLS default-deny, tham số filter, join hoặc bảng rỗng. Phải kiểm tra **access**, **policy identity** và **dữ liệu** riêng.

### Bài 29 — FORCE RLS

`ALTER TABLE ... FORCE ROW LEVEL SECURITY` làm **table owner** thông thường chịu RLS thay vì tự bypass do sở hữu bảng. Nhưng superuser và roles có BYPASSRLS vẫn có đặc quyền bypass riêng. Không dùng FORCE để “sửa” một role superuser đang được ứng dụng dùng cho queries.

### Bài 30 — UPDATE, CHECK OPTION và barrier

- `GRANT UPDATE`: role có thể thực hiện UPDATE trên view/cột tương ứng khi view updatable và các quyền nền cần thiết đã có.
- `WITH CHECK OPTION`: kiểm tra row mới sau INSERT/UPDATE có còn đáp ứng điều kiện view theo quy tắc hỗ trợ.
- `security_barrier`: kiểm soát optimizer với non-leakproof external predicates để tránh evaluation-order leakage; **không thay quyền hay check row sau UPDATE**.

RLS còn có `USING` và `WITH CHECK` ở base table để kiểm soát DML.

### Bài 31 — RLS UPDATE trên tasks

Với policies tenant10, reader không được UPDATE rows tenant20 theo điều kiện `USING`; thường chúng không được xem là rows đủ điều kiện để cập nhật. Nếu muốn đổi tenant_id của một row 10 sang 20, phải xét:

1. **Column UPDATE privileges** (lab chỉ grant update state).
2. **View WITH CHECK OPTION** nếu row mới rời khỏi tenant10 view.
3. **RLS WITH CHECK** ngăn giá trị tenant20 với policy tenant10.

Vì vậy ngay cả khi grant UPDATE tenant_id, vẫn có thể bị view CHECK OPTION/RLS policy từ chối.

### Bài 32 — PUBLIC

~~~sql
-- Ví dụ KHÔNG NÊN dùng cho view nhạy cảm:
GRANT SELECT ON view_lab.v_north_default TO PUBLIC;
~~~

`PUBLIC` nghĩa là tất cả roles. Khi chỉ một nhóm nhỏ được phép đọc, grant trực tiếp cho role dành riêng và kiểm tra role memberships.

### Bài 33 — Đổi owner

Với owner-mode view, owner quyết định base relation privileges và RLS identity. Đổi owner có thể làm thiếu base grants hoặc làm RLS policies áp khác đi; nếu owner mới có BYPASSRLS/owner exemption, tập rows có thể mở rộng. Do đó phải review `ALTER VIEW ... OWNER TO` như một **thay đổi bảo mật**, không phải chỉ tên người quản lý.

### Bài 34 — GUC do client tự SET

Không an toàn nếu client có thể tự đặt `app.tenant_id` theo tenant bất kỳ. RLS policy dùng GUC đó sẽ tin dữ liệu không được xác thực; user có thể giả tenant. `security_invoker` chỉ đổi base permission/RLS identity theo database role, **không** xác thực nội dung GUC. Cần xác thực tenant context ở trusted layer, ràng buộc quyền và reset session state khi dùng pool.

### Bài 35 — Barrier làm chậm

Không tắt barrier khi nó bảo vệ một security boundary thật chỉ vì query nhanh hơn.

Các hướng cải thiện:

1. Tạo index phù hợp điều kiện **nội bộ** view.
2. Hạn chế số rows/columns và join ở bên trong view nếu có thể.
3. Thay user-defined predicate bằng built-in operators có semantics tương đương và tính leakproof phù hợp nếu có.
4. Xem query có thể dùng RLS/role grants thay một tầng view barrier không, nhưng chỉ sau security review.
5. Đo EXPLAIN với tập dữ liệu và quyền thật.
6. Kiểm tra statistics, filter selectivity, skew và planning overhead.
7. Cân nhắc API/query interface thay đổi để không cần caller đánh giá function nguy hiểm trên view.

Không tự gắn LEAKPROOF cho function không an toàn.

### Bài 36 — Migration 12 services

Một quy trình:

1. Liệt kê 12 services, database roles, quyền view hiện tại và nested dependencies.
2. Xác nhận version PostgreSQL 15+.
3. Audit view owner, base privileges, RLS policies và BYPASSRLS.
4. Xác định những cột bảng nền thật cần; tránh GRANT SELECT toàn bảng nếu không có RLS tương xứng.
5. Tạo view song song `..._invoker_candidate` trong staging.
6. Cấp grants tối thiểu và xây RLS policy kiểm soát row nếu caller có đường đọc base.
7. Chạy tests positive/negative với từng service role và parameter profiles.
8. So **tập rows/cột** trước/sau, audit dữ liệu không được phép đọc.
9. Benchmark plans và API latencies.
10. Triển khai canary/chuyển dần service, monitor permission errors và row mismatches.
11. Giữ đường rollback có thời hạn; không thu hồi quyền/đổi flag một lần trên mọi service nếu chưa test đầy đủ.
12. Dọn view/grants cũ sau khi xác nhận không còn consumers.

### Bài 37 — Chọn mode

**Trường hợp 1 — reporting có giới hạn, không cấp bảng nền:** owner-mode view + grants trên view; cân nhắc `security_barrier=true` nếu filter paid là security boundary trước external leaky quals. Owner ít quyền, không có đường base bypass cho caller.

**Trường hợp 2 — SaaS với RLS đã đúng theo database role:** `security_invoker=true` để views tôn trọng caller privileges/RLS. Thêm barrier khi có threat model về các non-leakproof predicates vượt điều kiện bảo vệ trong view.

**Trường hợp 3 — public view có untrusted caller functions:** `security_barrier=true` đặc biệt quan trọng cho predicate `is_public=true`. Chọn owner/invoker riêng dựa vào việc caller có nên có quyền base table và RLS identity nào được yêu cầu; đừng xem barrier tự cấp/thu hồi quyền.

### Bài 38 — Checklist tổng hợp

Với `reporting.v_customer_stats`, một review tối thiểu:

- **Definition:** SELECT list, WHERE, JOIN, functions, có expose thông tin khách hàng ngoài contract?
- **Owner:** role sở hữu view và bảng nền; có superuser/BYPASSRLS không?
- **Privileges:** USAGE schema view, SELECT view, grants base khi invoker, role membership/PUBLIC.
- **RLS:** enabled/forced, policies, tenant identity và owner bypass.
- **Options:** `security_invoker`/`security_barrier` qua `pg_class.reloptions`.
- **Functions:** EXECUTE grants, SECURITY DEFINER/INVOKER, LEAKPROOF, search_path.
- **Nested views:** mỗi tầng owner/invoker, direct base relation access.
- **Runtime tests:** role được xem đúng rows; role khác không xem được, column-level denials, DML/check nếu writable.
- **Performance:** EXPLAIN/ANALYZE trên SELECT an toàn, buffers, index pushdown, RLS/barrier overhead.
- **Rollout:** staged GRANTs/policies, canary, monitoring, rollback, audit changes.

**Đúng quyền** là điều kiện không thể hy sinh để đạt query nhanh hơn. **Hiệu năng** cần tối ưu trong phạm vi thiết kế đã giữ đúng quyền và dữ liệu.

---

## 34. Một số truy vấn quản trị gọn để dùng lại

### 34.1. Xem version và view flags

~~~sql
SELECT current_setting('server_version') AS postgres_version;

SELECT
    n.nspname,
    c.relname,
    pg_get_userbyid(c.relowner) AS owner_name,
    c.reloptions
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid=c.relnamespace
WHERE n.nspname='view_lab'
  AND c.relkind='v'
ORDER BY c.relname;
~~~

### 34.2. Xem view definition

~~~sql
SELECT
    'view_lab.v_north_secure' AS view_name,
    pg_get_viewdef('view_lab.v_north_secure'::regclass,true)
        AS sql_definition;
~~~

### 34.3. Quyền base và view của reader

~~~sql
SELECT
    has_schema_privilege('view_lab_reader','view_lab','USAGE')
        AS schema_usage,
    has_table_privilege(
        'view_lab_reader','view_lab.v_north_secure','SELECT'
    ) AS view_select,
    has_column_privilege(
        'view_lab_reader','view_lab.accounts','account_id','SELECT'
    ) AS account_id_select,
    has_column_privilege(
        'view_lab_reader','view_lab.accounts','internal_code','SELECT'
    ) AS internal_code_select;
~~~

### 34.4. RLS metadata

~~~sql
SELECT
    n.nspname,
    c.relname,
    c.relrowsecurity,
    c.relforcerowsecurity,
    pg_get_userbyid(c.relowner) AS owner_name
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid=c.relnamespace
WHERE n.nspname='view_lab'
  AND c.relname='accounts';
~~~

~~~sql
SELECT policyname,roles,cmd,qual,with_check
FROM pg_policies
WHERE schemaname='view_lab'
  AND tablename='accounts';
~~~

### 34.5. So kết quả các views trong lab

~~~sql
SET ROLE view_lab_reader;

SELECT
    'default' AS path,
    array_agg(account_id ORDER BY account_id) AS ids
FROM view_lab.v_north_default
UNION ALL
SELECT
    'invoker',
    array_agg(account_id ORDER BY account_id)
FROM view_lab.v_north_invoker
UNION ALL
SELECT
    'both_flags',
    array_agg(account_id ORDER BY account_id)
FROM view_lab.v_north_secure;

RESET ROLE;
~~~

Ở lab giữ nguyên owner-mode default, kỳ vọng:

~~~text
default     {1,2,5}
invoker     {1,5}
both_flags  {1,5}
~~~

Nếu đã thay owner/options hoặc FORCE RLS hay dữ liệu, kết quả có thể khác. Query này là một **test về các row thực sự expose**, không thay thế kiểm toán tất cả quyền.

### 34.6. Khi hoàn tất lab

Việc dọn schema/roles là thao tác **phá hủy dữ liệu lab** và thay đổi roles cluster-wide. Chỉ thực hiện khi chắc chắn các đối tượng thuộc lab này và không được ứng dụng khác sử dụng:

~~~sql
-- Chỉ chạy trên instance thực hành đã xác nhận ownership:
-- DROP SCHEMA view_lab CASCADE;
-- DROP ROLE view_lab_reader;
-- DROP ROLE view_lab_owner;
~~~

Trước khi dọn, bảo đảm session đã `RESET ROLE`, không còn quyền/grant/đối tượng phụ thuộc vào các roles ngoài schema lab và không có client sử dụng chúng.

---

## 35. Tài liệu chính thức và phạm vi phiên bản

Khi cần đối chiếu cú pháp và chi tiết quyền theo PostgreSQL major version đang vận hành, tham khảo:

- [PostgreSQL — CREATE VIEW](https://www.postgresql.org/docs/current/sql-createview.html): `security_invoker`, `security_barrier`, automatically updatable views và `CHECK OPTION`.
- [PostgreSQL — ALTER VIEW](https://www.postgresql.org/docs/current/sql-alterview.html): thay đổi view options và owner.
- [PostgreSQL — Privileges](https://www.postgresql.org/docs/current/ddl-priv.html): quyền trên các loại đối tượng, ownership, schema access.
- [PostgreSQL — GRANT](https://www.postgresql.org/docs/current/sql-grant.html): table/column/function/schema grants và role membership.
- [PostgreSQL — Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html): RLS, owner bypass, FORCE, policies.
- [PostgreSQL — CREATE POLICY](https://www.postgresql.org/docs/current/sql-createpolicy.html): `USING` và `WITH CHECK`.
- [PostgreSQL — CREATE FUNCTION](https://www.postgresql.org/docs/current/sql-createfunction.html): `SECURITY DEFINER`, `SECURITY INVOKER` và `LEAKPROOF`.
- [PostgreSQL — Function Security](https://www.postgresql.org/docs/current/perm-functions.html): quyền và rủi ro khi cấp quyền thực thi functions.
- [PostgreSQL — EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html): quan sát plans/actual execution.
- [PostgreSQL — System Catalog pg_class](https://www.postgresql.org/docs/current/catalog-pg-class.html): `reloptions`, owner, relrowsecurity/relforcerowsecurity.
- [PostgreSQL — pg_policies](https://www.postgresql.org/docs/current/view-pg-policies.html): view danh sách policy definitions.

Đường dẫn `/current/` có thể trỏ đến major version mới hơn PostgreSQL đang chạy. Với `security_invoker`, nhớ yêu cầu **PostgreSQL 15+**; các hành vi phụ trợ và tính năng catalog/view DDL có thể khác theo phiên bản, nên tra đúng major version trước khi triển khai.

---

## 36. Tổng kết

**View trong PostgreSQL là giao diện truy vấn có quy tắc quyền riêng.** Khi xử lý dữ liệu nhạy cảm, hai thuộc tính `security_invoker` và `security_barrier` giúp giải quyết **hai vấn đề khác nhau**:

1. **View mặc định** kiểm tra quyền truy cập bảng nền theo **view owner**. Nhờ đó có thể cấp SELECT trên một view hạn chế mà không cấp SELECT bảng nền. Nhưng RLS identity thường theo owner, và table owner có thể bypass RLS.
2. **`security_invoker=true`** (PostgreSQL 15+) dùng **quyền và RLS identity của caller** cho các base relations phù hợp. Caller cần quyền trên bảng/cột nền; chỉ GRANT SELECT view có thể chưa đủ. Tùy chọn này không tự thêm WHERE hay policy giới hạn tenant.
3. **`security_barrier=true`** bảo vệ một số **điều kiện lọc nhạy cảm trong view** khỏi việc optimizer đẩy external non-leakproof functions/operators xuống đánh giá sớm theo cách làm lộ dữ liệu của rows bị lọc. Nó **không** thay quyền bảng nền hoặc làm view thành invoker.
4. **RLS** và **GRANT** là hai lớp khác nhau: role cần privileges phù hợp và rows phải qua policies tương ứng. `BYPASSRLS`, table ownership và `FORCE ROW LEVEL SECURITY` có thể thay đổi kết quả.
5. **Functions** có quyền EXECUTE và `SECURITY INVOKER/DEFINER` riêng; không suy luận quyền function từ cờ của view. Đặc biệt, không dùng `LEAKPROOF` sai semantics để ép pushdown.
6. **Nested views** cần được audit theo từng tầng: outer invoker không tự biến inner owner-mode thành invoker; inner invoker có thể áp quyền caller ngay cả khi outer owner-mode.
7. **Security views không phải thay thế mọi lớp bảo mật.** Cần hạn chế quyền trực tiếp trên bảng, kiểm soát owner/role memberships, quyền function, chính sách RLS và application identity.
8. **UPDATE/INSERT qua view** còn liên quan quyền DML, RLS `USING/WITH CHECK`, `WITH CHECK OPTION` và tính updatable của view. Barrier không thay constraint DML.
9. **Thay đổi một flag trên view đang dùng có thể làm application lỗi hoặc lộ phạm vi dữ liệu khác trước.** Cần test bằng role thực, so tập rows, review grants/policies và có rollback.
10. **Hiệu năng vẫn quan trọng:** barrier/RLS có thể thay đổi predicate pushdown và query plan. Hãy đo EXPLAIN trên dữ liệu đại diện nhưng không đánh đổi security boundary chỉ để giảm vài milliseconds.

Quy trình nên ghi nhớ: **xác định caller và phạm vi dữ liệu được phép → kiểm tra view owner, schema/view/base grants → hiểu RLS identity và policies → chọn security_invoker theo nhu cầu quyền nền → chọn security_barrier theo threat model leaky predicates → audit functions/nested views → thử positive và negative cases dưới đúng role → đo kế hoạch thực thi → triển khai an toàn có giám sát và rollback**.

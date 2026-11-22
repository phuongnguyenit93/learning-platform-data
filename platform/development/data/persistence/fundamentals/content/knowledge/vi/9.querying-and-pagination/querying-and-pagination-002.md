# Lọc, sắp xếp và lựa chọn các trường cần đọc

## 1. Vì sao ba thao tác này thường đi cùng nhau?

Một nhân viên chăm sóc khách hàng mở màn hình “Đơn hàng đã thanh toán”. Họ chỉ muốn thấy đơn của đơn vị mình, trong khoảng thời gian đã chọn, được sắp từ mới đến cũ. Trên mỗi dòng, màn hình chỉ hiển thị mã đơn, trạng thái, tổng tiền và thời điểm tạo.

Yêu cầu tưởng như đơn giản này có ba quyết định khác nhau:

- **Lọc (filter):** hàng nào được phép xuất hiện? Ví dụ chỉ đơn của tenant hiện tại, trạng thái **PAID** và thời gian trong tháng.
- **Sắp xếp (sort):** những hàng đủ điều kiện xuất hiện theo thứ tự nào? Ví dụ **created_at giảm dần**, sau đó **order_id giảm dần** để xử lý các thời điểm trùng nhau.
- **Chọn trường đọc (projection):** mỗi hàng trả về gồm những cột nào? Ví dụ chỉ **order_id**, **status**, **total_amount**, **created_at**, thay vì toàn bộ dữ liệu đơn hàng.

Nếu chỉ đặt điều kiện lọc rồi đọc cả bảng vào Java để tự sắp xếp và bỏ bớt trường, ứng dụng có thể chuyển nhiều dữ liệu không cần thiết qua mạng, tiêu tốn bộ nhớ và vô tình tải cả thông tin nhạy cảm. Ngược lại, đẩy điều kiện và hình dạng kết quả xuống SQL giúp cơ sở dữ liệu có cơ hội sử dụng chỉ mục, lọc trước khi trả dữ liệu và giới hạn số hàng.

Bài học thuộc chương **Truy vấn và phân trang**, học phần **DATA_PERSISTENCE_FUNDAMENTALS**. Kiến thức ở đây nối liền lược đồ lưu trữ bền vững, SQL, chỉ mục và thiết kế ranh giới persistence cho Java. Người học cần biết viết truy vấn đúng về mặt nghiệp vụ, tránh SQL injection, giữ thứ tự ổn định cho phân trang và đo hiệu năng khi dữ liệu tăng.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt vai trò của **WHERE**, **ORDER BY**, **SELECT** và **LIMIT**.
2. Viết điều kiện lọc với so sánh, tập giá trị, khoảng thời gian, tìm kiếm chuỗi và **NULL**.
3. Giải thích vì sao thứ tự không được bảo đảm nếu thiếu **ORDER BY**, và chọn khóa phụ để sắp xếp xác định.
4. Chọn đúng cột phục vụ use case, ánh xạ kết quả vào DTO Java và tránh **SELECT \*** không cần thiết.
5. Xây dựng bộ lọc tùy chọn an toàn bằng **PreparedStatement**, kiểm soát cột sắp xếp bằng danh sách cho phép.
6. Hiểu tác động của **JOIN**, **DISTINCT**, phân trang và chỉ mục đến số hàng cũng như hiệu năng.
7. Nhận diện các lỗi thường gặp về lọc sai tenant, so sánh NULL, sai ranh giới thời gian và phân trang bị lặp/bỏ sót hàng.

## 2. Dữ liệu minh họa và hợp đồng truy vấn

Ví dụ xuyên suốt sử dụng PostgreSQL với hai bảng **customer** và **purchase_order**. Mỗi khách hàng và đơn hàng thuộc một **tenant** (đơn vị sử dụng hệ thống). Khóa ngoại ghép giúp ngăn đơn của tenant này tham chiếu khách thuộc tenant khác.

~~~sql
CREATE TABLE customer (
    tenant_id   BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    full_name   VARCHAR(160) NOT NULL,
    PRIMARY KEY (tenant_id, customer_id)
);

CREATE TABLE purchase_order (
    order_id     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id    BIGINT NOT NULL,
    customer_id  BIGINT NOT NULL,
    status       VARCHAR(20) NOT NULL
                 CHECK (status IN ('NEW', 'PAID', 'CANCELLED')),
    total_amount NUMERIC(14, 2) NOT NULL CHECK (total_amount >= 0),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    internal_note TEXT,
    FOREIGN KEY (tenant_id, customer_id)
        REFERENCES customer(tenant_id, customer_id)
);
~~~

**order_id** định danh duy nhất một đơn; **tenant_id** dùng để giới hạn phạm vi dữ liệu; **status**, **total_amount** và **created_at** là các điều kiện tìm kiếm/sắp xếp thường gặp; **internal_note** có thể chứa thông tin nội bộ và không cần xuất hiện trên màn hình danh sách.

Dữ liệu giả định (thời điểm trình bày theo UTC):

| order_id | tenant_id | customer_id | status | total_amount | created_at |
| ---: | ---: | ---: | --- | ---: | --- |
| 1001 | 10 | 201 | PAID | 520000.00 | 2026-11-20 10:30 |
| 1002 | 10 | 201 | NEW | 150000.00 | 2026-11-20 10:30 |
| 1003 | 10 | 202 | PAID | 90000.00 | 2026-11-19 15:30 |
| 1004 | 11 | 301 | PAID | 810000.00 | 2026-11-20 12:00 |
| 1005 | 10 | 201 | CANCELLED | 70000.00 | 2026-11-18 09:00 |

Cần lưu ý **1004 thuộc tenant 11**. Kể cả khi người dùng tenant 10 đoán được ID này, một endpoint chỉ được xem đơn của tenant 10 phải ngăn không cho đọc dữ liệu tenant 11.

Giả sử yêu cầu là: *“Trong tenant 10, lấy các đơn PAID, mới nhất trước, tối đa 20 hàng; chỉ trả mã đơn, trạng thái, tổng tiền và thời điểm tạo.”*

~~~sql
SELECT order_id, status, total_amount, created_at
FROM purchase_order
WHERE tenant_id = 10
  AND status = 'PAID'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Với dữ liệu ví dụ, kết quả là đơn **1001** và **1003** theo đúng thứ tự. Truy vấn thể hiện đồng thời ba quyết định: **WHERE chọn hàng**, **ORDER BY chọn thứ tự**, **SELECT chọn cột**. **LIMIT** giới hạn số hàng của kết quả cuối.

## 3. Hiểu đúng WHERE, SELECT và ORDER BY

Trong truy vấn SQL thông thường:

| Thành phần | Câu hỏi nghiệp vụ | Ví dụ |
| --- | --- | --- |
| **FROM / JOIN** | Dữ liệu đến từ bảng hay nguồn nào? | purchase_order |
| **WHERE** | Những hàng nào đủ điều kiện? | tenant_id = 10 AND status = 'PAID' |
| **GROUP BY / HAVING** | Có cần gom nhóm và lọc nhóm không? | Tổng tiền theo trạng thái |
| **SELECT** | Kết quả cần những cột/biểu thức nào? | order_id, total_amount |
| **DISTINCT** | Có cần loại bỏ hàng kết quả giống nhau không? | DISTINCT customer_id |
| **ORDER BY** | Kết quả theo thứ tự nào? | created_at DESC, order_id DESC |
| **LIMIT / OFFSET** | Trả bao nhiêu hàng và bỏ qua bao nhiêu hàng trước đó? | LIMIT 20 OFFSET 40 |

Có thể hình dung thứ tự **logic** của một truy vấn SELECT với các thành phần trên là: tạo nguồn dữ liệu và JOIN → WHERE → GROUP BY → HAVING → xác định biểu thức SELECT → DISTINCT → ORDER BY → LIMIT/OFFSET. Đây là mô hình để *hiểu ý nghĩa*, không phải thứ tự bắt buộc mà bộ máy thực thi vật lý tuân theo; bộ tối ưu có thể đẩy lọc xuống trước, dùng chỉ mục để sắp xếp hoặc chọn kế hoạch khác mà vẫn bảo toàn ngữ nghĩa SQL.

### 3.1. SELECT không làm thay đổi dữ liệu đang lưu

~~~sql
SELECT order_id, total_amount
FROM purchase_order
WHERE tenant_id = 10;
~~~

Lệnh này chỉ trả hai cột. Bảng gốc vẫn còn mọi cột như **customer_id**, **internal_note**, **created_at**. Việc **không chọn một cột** là quyết định về hình dạng kết quả, không phải thao tác xóa cột.

### 3.2. WHERE không sắp xếp và ORDER BY không lọc

~~~sql
-- Lọc đúng tenant nhưng chưa bảo đảm thứ tự kết quả.
SELECT order_id FROM purchase_order WHERE tenant_id = 10;

-- Sắp xếp toàn bộ các tenant, có thể vi phạm yêu cầu phân quyền.
SELECT order_id FROM purchase_order ORDER BY created_at DESC;
~~~

Hai câu SQL trên xử lý hai câu hỏi khác nhau. Cả hai đều thiếu một phần quan trọng của use case. Trong API đa tenant, điều kiện quyền truy cập cần được áp dụng vào truy vấn trước khi trả dữ liệu, không nên tải tất cả về Java rồi mới lọc.

## 4. Lọc chính xác bằng các toán tử so sánh

### 4.1. So sánh và kết hợp điều kiện

SQL thường dùng **=**, **<>**, **>**, **>=**, **<**, **<=**. Điều kiện có thể nối bằng **AND**, **OR** và phủ định bằng **NOT**.

~~~sql
SELECT order_id, status, total_amount
FROM purchase_order
WHERE tenant_id = 10
  AND status = 'PAID'
  AND total_amount >= 100000;
~~~

Truy vấn tìm các đơn đã thanh toán có tổng tiền từ 100000 trở lên trong tenant 10. Cột **total_amount** dùng **NUMERIC**, giúp so sánh số tiền theo giá trị thập phân cố định.

Hãy chú ý mức ưu tiên toán tử: **AND thường được đánh giá trước OR**. Dùng dấu ngoặc khi nghiệp vụ có nhiều nhánh điều kiện.

~~~sql
-- Chỉ nhận đơn tenant 10 thỏa một trong hai nhánh được đặt trong ngoặc.
SELECT order_id, status, total_amount
FROM purchase_order
WHERE tenant_id = 10
  AND (
       status = 'PAID'
       OR (status = 'NEW' AND total_amount >= 500000)
  );
~~~

Nếu vô ý viết **tenant_id = 10 AND status = 'PAID' OR status = 'NEW'** thì nhánh **status = 'NEW'** có thể khớp hàng của tenant khác. Đây vừa là lỗi logic vừa là rủi ro lộ dữ liệu.

### 4.2. IN cho một tập lựa chọn

~~~sql
SELECT order_id, status
FROM purchase_order
WHERE tenant_id = 10
  AND status IN ('NEW', 'PAID');
~~~

**IN** tương đương so sánh với một tập giá trị được liệt kê. Khi danh sách đến từ giao diện, cần dùng tham số hóa phù hợp với driver/framework, không nối trực tiếp các chuỗi người dùng vào SQL.

Danh sách rỗng có ngữ nghĩa cần xác định ở ứng dụng: “không lọc trạng thái” khác “không trạng thái nào được chọn, do đó kết quả rỗng”. Không tự biến danh sách rỗng thành một câu **IN ()** vì nhiều hệ quản trị không chấp nhận cú pháp đó.

### 4.3. Khoảng giá trị và BETWEEN

~~~sql
SELECT order_id, total_amount
FROM purchase_order
WHERE tenant_id = 10
  AND total_amount BETWEEN 100000 AND 600000;
~~~

**BETWEEN** bao gồm cả hai đầu mút (tương đương **>= 100000 AND <= 600000**). Điều này phù hợp với một số khoảng số tiền, nhưng có thể gây nhầm với thời gian.

### 4.4. Khoảng thời gian nên dùng đầu đóng, cuối mở

Nếu tìm các đơn trong ngày 20/11/2026 theo **UTC**, nên dùng:

~~~sql
SELECT order_id, created_at
FROM purchase_order
WHERE tenant_id = 10
  AND created_at >= TIMESTAMPTZ '2026-11-20 00:00:00+00'
  AND created_at <  TIMESTAMPTZ '2026-11-21 00:00:00+00'
ORDER BY created_at, order_id;
~~~

Cách này biểu diễn khoảng **[đầu ngày, đầu ngày kế tiếp)**, tránh phải đoán độ chính xác phần giây cuối ngày như **23:59:59.999999**. Hai khoảng ngày liền kề không chồng lấn và không bỏ sót thời điểm ở ranh giới.

Nếu người dùng chọn “ngày 20/11 tại Việt Nam”, ứng dụng phải xác định **múi giờ nghiệp vụ** (chẳng hạn **Asia/Ho_Chi_Minh**), tính hai mốc đầu ngày theo zone đó rồi chuyển sang thời điểm tuyệt đối trước khi gửi SQL. Không coi ngày cục bộ của người dùng là ngày UTC nếu nghiệp vụ không quy định như vậy. Với zone có daylight saving, một ngày địa phương có thể không dài đúng 24 giờ.

**Tránh bọc cột bằng hàm khi chưa cần**:

~~~sql
-- Có thể khó tận dụng trực tiếp chỉ mục B-tree thông thường trên created_at.
WHERE DATE(created_at) = DATE '2026-11-20'
~~~

Ngoài khả năng ảnh hưởng chỉ mục, biểu thức **DATE(created_at)** trong PostgreSQL còn phụ thuộc cách diễn giải múi giờ phiên khi created_at là TIMESTAMPTZ. Dùng hai mốc thời gian đã xác định rõ thường dễ kiểm soát hơn.

## 5. Lọc chuỗi và xử lý NULL

### 5.1. LIKE, ILIKE và ký tự đại diện

~~~sql
SELECT tenant_id, customer_id, full_name
FROM customer
WHERE tenant_id = 10
  AND full_name ILIKE '%an%';
~~~

Trong PostgreSQL, **ILIKE** tìm theo mẫu không phân biệt chữ hoa/chữ thường theo quy tắc so sánh/collation thích hợp. **LIKE** cũng hỗ trợ ký tự **%** cho chuỗi bất kỳ và **_** cho một ký tự. Cú pháp và tính năng ILIKE không phổ biến giống nhau ở mọi cơ sở dữ liệu; hệ khác có thể cần hàm hoặc collation tương ứng.

Nếu người dùng tìm chính ký tự **%** hoặc **_**, ứng dụng cần có quy tắc **escape wildcard** thay vì để các ký tự đó vô tình mở rộng kết quả. Dùng tham số hóa ngăn SQL injection nhưng **không tự biến wildcard thành ký tự thường**.

Về hiệu năng, mẫu bắt đầu bằng **%** như **'%an%'** thường không tận dụng tốt B-tree thông thường. Có thể cần cơ chế tìm kiếm phù hợp như PostgreSQL **pg_trgm**, full-text search hoặc một dịch vụ tìm kiếm chuyên dụng khi dữ liệu lớn; phải đo theo workload thực.

### 5.2. NULL không bằng giá trị 0 hay chuỗi rỗng

Trong lược đồ, **internal_note** cho phép NULL. Tìm đơn chưa có ghi chú bằng:

~~~sql
SELECT order_id
FROM purchase_order
WHERE tenant_id = 10
  AND internal_note IS NULL;
~~~

Không viết **internal_note = NULL**: biểu thức so sánh thông thường với NULL không trả **TRUE**, mà trả **UNKNOWN** theo logic ba giá trị của SQL. Chỉ những hàng có điều kiện WHERE đánh giá TRUE mới đi tiếp.

So sánh:

~~~sql
-- Không chọn các hàng internal_note là NULL.
WHERE internal_note <> 'Kiểm tra lại'

-- Chọn những hàng chưa có ghi chú hoặc có ghi chú khác chuỗi trên.
WHERE internal_note IS NULL
   OR internal_note <> 'Kiểm tra lại'
~~~

Nếu cần so sánh hai giá trị theo ngữ nghĩa coi NULL là một trường hợp có thể đối chiếu, PostgreSQL hỗ trợ **IS DISTINCT FROM** / **IS NOT DISTINCT FROM**. Ví dụ:

~~~sql
SELECT order_id
FROM purchase_order
WHERE tenant_id = 10
  AND internal_note IS DISTINCT FROM 'Kiểm tra lại';
~~~

Điều này gồm cả hàng có **internal_note IS NULL**. Khi chuyển sang DB khác, cần kiểm tra hỗ trợ cú pháp tương đương.

### 5.3. “Không có điều kiện lọc” khác “lọc cột có NULL”

Nếu API gửi **noteFilter = null**, cần làm rõ nó nghĩa là:

- Người dùng không yêu cầu lọc ghi chú; hoặc
- Người dùng muốn tìm các đơn **internal_note IS NULL**.

Cả hai không thể được biểu diễn không mơ hồ bằng một tham số nullable nếu hợp đồng API không xác định cách phân biệt **không cung cấp**, **NULL tường minh** và **giá trị cụ thể**. Có thể dùng một kiểu filter có các lựa chọn **ANY / IS_NULL / HAS_VALUE / EQUALS(value)** hoặc DTO theo dõi sự hiện diện trường.

## 6. Sắp xếp: luôn chủ động chỉ rõ thứ tự

### 6.1. Không có ORDER BY thì không có thứ tự bảo đảm

Cơ sở dữ liệu không có nghĩa vụ trả các hàng theo thứ tự chèn, thứ tự khóa chính, vị trí vật lý hay lần truy vấn trước. Thay đổi chỉ mục, dữ liệu, kế hoạch thực thi hoặc mức song song có thể làm thứ tự thay đổi.

~~~sql
-- Có thứ tự xác định nếu created_at và order_id đủ phân biệt.
SELECT order_id, status, created_at
FROM purchase_order
WHERE tenant_id = 10
ORDER BY created_at DESC, order_id DESC;
~~~

**DESC** là giảm dần, **ASC** là tăng dần. Có thể kết hợp nhiều cột với hướng khác nhau, ví dụ ưu tiên HIGH trước LOW theo biểu thức CASE, rồi ngày mới nhất. Khi dùng hàm/biểu thức để sắp xếp, cần cân nhắc chi phí và khả năng hỗ trợ chỉ mục.

### 6.2. Khóa phụ để xử lý giá trị trùng

Trong dữ liệu minh họa, đơn **1001** và **1002** cùng **created_at = 2026-11-20 10:30**. Chỉ dùng:

~~~sql
ORDER BY created_at DESC
~~~

thì hai đơn bằng thời gian có thể xuất hiện theo thứ tự bất kỳ. Thêm **order_id DESC** làm tiêu chí phụ:

~~~sql
ORDER BY created_at DESC, order_id DESC
~~~

sẽ đặt **1002 trước 1001** khi hai hàng cùng thời điểm. Vì **order_id** là PRIMARY KEY, bộ tiêu chí cuối cùng tạo ra thứ tự tổng xác định cho tập hàng ở thời điểm truy vấn.

Điều này đặc biệt quan trọng với **LIMIT/OFFSET** và **keyset pagination**. Thứ tự xác định trong một truy vấn không có nghĩa kết quả các trang vẫn giữ nguyên nếu dữ liệu được thêm, xóa hoặc sửa giữa hai request.

### 6.3. Quy tắc NULLS FIRST / NULLS LAST

Với một cột có thể NULL, cần xác định chỗ đặt hàng NULL:

~~~sql
SELECT order_id, internal_note
FROM purchase_order
WHERE tenant_id = 10
ORDER BY internal_note ASC NULLS LAST, order_id ASC;
~~~

Trong PostgreSQL, khi không ghi tường minh, **ASC mặc định NULLS LAST** và **DESC mặc định NULLS FIRST**. Hệ quản trị khác có thể có quy tắc khác. Để có kết quả phù hợp nghiệp vụ và giảm phụ thuộc ngầm vào database, có thể ghi rõ **NULLS FIRST/LAST** khi cần.

Lưu ý: sắp xếp theo **internal_note** có thể không phù hợp giao diện nếu giá trị dài hoặc collation khó đoán; ví dụ chỉ minh họa ngữ nghĩa NULL.

### 6.4. Sắp xếp chuỗi chịu ảnh hưởng collation

**ORDER BY full_name** phụ thuộc quy tắc đối chiếu chuỗi (collation) của cột/biểu thức và cấu hình database: chữ hoa/chữ thường, dấu tiếng Việt và ký tự đặc biệt có thể làm thứ tự khác kỳ vọng.

Nếu yêu cầu sắp xếp tên tiếng Việt nhất quán giữa môi trường, cần chọn collation và chính sách chuẩn hóa dữ liệu có chủ đích; kiểm thử với các tên có dấu. Không mặc định **ORDER BY LOWER(full_name)** là giải pháp chung cho mọi ngôn ngữ và cũng không giả định nó sẽ dùng ngay chỉ mục B-tree trên cột gốc.

### 6.5. Sắp xếp theo cột không có trong SELECT

Trong một truy vấn SELECT bình thường, PostgreSQL có thể sắp xếp theo cột không được trả về:

~~~sql
SELECT order_id, status
FROM purchase_order
WHERE tenant_id = 10
ORDER BY created_at DESC, order_id DESC;
~~~

Điều này cho phép giao diện chỉ nhận trường cần hiển thị. Tuy nhiên, có giới hạn khi kết hợp **DISTINCT**, truy vấn nhóm hoặc các quy tắc SQL đặc biệt: với **SELECT DISTINCT**, PostgreSQL yêu cầu biểu thức ORDER BY phải xuất hiện phù hợp trong danh sách SELECT. Khi xây truy vấn phức tạp, cần kiểm tra ngữ nghĩa và hỗ trợ của hệ quản trị.

## 7. Lựa chọn các trường cần đọc (projection)

### 7.1. SELECT \* tiện nhưng có nhiều hệ quả

~~~sql
SELECT *
FROM purchase_order
WHERE tenant_id = 10;
~~~

Lệnh này đọc toàn bộ cột được biểu diễn bởi **\***, gồm cả **internal_note** dù màn hình danh sách không cần. Khi schema thêm cột lớn như dữ liệu JSON hoặc thông tin nhạy cảm, truy vấn có thể vô tình nhận nhiều dữ liệu hơn trước.

Ở tầng API đọc danh sách, lựa chọn cột rõ ràng thường có lợi:

~~~sql
SELECT order_id, status, total_amount, created_at
FROM purchase_order
WHERE tenant_id = 10
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Lợi ích:

- Chỉ truyền dữ liệu thực sự cần qua driver/kết nối.
- Giảm chi phí ánh xạ sang Java và giảm áp lực bộ nhớ.
- Hợp đồng DTO ổn định hơn khi thêm cột ở bảng.
- Giảm nguy cơ vô tình đọc hoặc ghi log dữ liệu nhạy cảm.
- Có thể cho phép kế hoạch truy vấn sử dụng chỉ mục bao phủ trong một số trường hợp, tùy hệ quản trị và điều kiện truy xuất.

**Projection không phải cơ chế phân quyền.** Vẫn cần kiểm tra quyền đọc theo tenant và cột; một lập trình viên có thể vô tình thêm một cột nhạy cảm vào SELECT. Việc giới hạn cột ở tầng SQL là một lớp giảm thiểu dữ liệu, không thay cho chính sách bảo mật.

### 7.2. Dùng bí danh (alias) khi đầu ra cần tên khác

~~~sql
SELECT
    order_id AS id,
    status AS order_status,
    total_amount AS amount
FROM purchase_order
WHERE tenant_id = 10;
~~~

Bí danh giúp ánh xạ kết quả cho DTO hoặc báo cáo. Với JOIN, alias còn tránh hai cột trùng tên:

~~~sql
SELECT
    o.order_id AS order_id,
    o.status AS status,
    c.full_name AS customer_name
FROM purchase_order AS o
JOIN customer AS c
  ON c.tenant_id = o.tenant_id
 AND c.customer_id = o.customer_id
WHERE o.tenant_id = 10
ORDER BY o.created_at DESC, o.order_id DESC;
~~~

Điều kiện JOIN bao gồm cả tenant_id và customer_id để khớp đúng khóa ghép. Kết quả gồm tên khách nhưng không cần đưa mọi cột của hai bảng về Java.

### 7.3. Projection và dữ liệu dẫn xuất

Có thể chọn biểu thức thay vì cột lưu sẵn:

~~~sql
SELECT
    status,
    COUNT(*) AS order_count,
    SUM(total_amount) AS total_amount
FROM purchase_order
WHERE tenant_id = 10
GROUP BY status
ORDER BY status;
~~~

Mỗi hàng ở đây là **một nhóm trạng thái**, không phải một đơn hàng. Kiểu dữ liệu Java phù hợp có thể là **StatusSummary(status, count, totalAmount)**, thay vì cố ánh xạ kết quả vào entity **PurchaseOrder**.

Nếu phải lọc trên **kết quả gom nhóm**, dùng **HAVING**, chẳng hạn:

~~~sql
SELECT customer_id, COUNT(*) AS paid_order_count
FROM purchase_order
WHERE tenant_id = 10
  AND status = 'PAID'
GROUP BY customer_id
HAVING COUNT(*) >= 2
ORDER BY paid_order_count DESC, customer_id ASC;
~~~

**WHERE** lọc hàng trước khi nhóm; **HAVING** lọc nhóm theo kết quả tổng hợp.

### 7.4. DISTINCT giải quyết điều gì?

~~~sql
SELECT DISTINCT customer_id
FROM purchase_order
WHERE tenant_id = 10;
~~~

**DISTINCT** loại những hàng kết quả giống nhau theo toàn bộ danh sách biểu thức SELECT. Nó không tự “sửa” JOIN sai hay bảo đảm lấy bản ghi mới nhất mỗi khách. Nếu chọn thêm order_id, các hàng sẽ không còn trùng theo (customer_id, order_id) dù customer_id lặp nhiều lần.

Khi yêu cầu “mỗi khách lấy đơn mới nhất”, phải viết truy vấn thể hiện quy tắc **chọn một hàng theo thứ tự trong từng nhóm**, ví dụ dùng **ROW_NUMBER() OVER (PARTITION BY ... ORDER BY ...)** hoặc cú pháp đặc thù PostgreSQL như **DISTINCT ON**, thay vì chỉ dùng DISTINCT chung chung.

## 8. JOIN có thể thay đổi số hàng và ý nghĩa của bộ lọc

### 8.1. Một–nhiều có thể nhân số hàng

Giả sử bảng **order_item** có nhiều dòng sản phẩm cho một đơn. JOIN:

~~~sql
SELECT o.order_id, oi.product_id
FROM purchase_order AS o
JOIN order_item AS oi ON oi.order_id = o.order_id
WHERE o.tenant_id = 10;
~~~

có thể trả ba hàng cho cùng một **order_id** nếu đơn đó có ba sản phẩm. Đây là hành vi đúng của JOIN một–nhiều. Nếu ứng dụng chỉ muốn danh sách đơn và không cần dòng sản phẩm, JOIN đó có thể là công việc thừa.

Nếu cần lọc “đơn có ít nhất một sản phẩm mã 42”, có thể dùng **EXISTS** để tránh nhân hàng cha:

~~~sql
SELECT o.order_id, o.status
FROM purchase_order AS o
WHERE o.tenant_id = 10
  AND EXISTS (
      SELECT 1
      FROM order_item AS oi
      WHERE oi.order_id = o.order_id
        AND oi.product_id = 42
  )
ORDER BY o.order_id DESC;
~~~

Đoạn này giả định **order_item(order_id, product_id, ...)** đã được thiết kế với khóa ngoại phù hợp. **EXISTS** phản ánh đúng câu hỏi “có hay không” mà không yêu cầu trả nhiều dòng con.

### 8.2. Điều kiện ở ON khác điều kiện ở WHERE với LEFT JOIN

Muốn hiển thị mọi khách hàng, kể cả người chưa có đơn **PAID**:

~~~sql
SELECT
    c.customer_id,
    c.full_name,
    o.order_id
FROM customer AS c
LEFT JOIN purchase_order AS o
  ON o.tenant_id = c.tenant_id
 AND o.customer_id = c.customer_id
 AND o.status = 'PAID'
WHERE c.tenant_id = 10
ORDER BY c.customer_id, o.order_id;
~~~

Điều kiện **o.status = 'PAID'** nằm trong **ON**, nên khách hàng không có đơn PAID vẫn xuất hiện với **o.order_id = NULL**. Nếu chuyển điều kiện đó sang **WHERE o.status = 'PAID'** mà không xử lý NULL, những hàng không có đơn tương ứng bị loại và truy vấn có thể mất ý nghĩa của LEFT JOIN.

Nếu dùng LEFT JOIN để **đếm số đơn PAID** cho từng khách, nên dùng **COUNT(o.order_id)** thay vì **COUNT(*)**, vì LEFT JOIN vẫn tạo một hàng bên trái khi không có hàng khớp bên phải.

## 9. Tạo bộ lọc tùy chọn nhưng giữ SQL an toàn

Một màn hình thường cho phép nhiều điều kiện tùy chọn: trạng thái, số tiền tối thiểu, từ ngày, đến ngày. Cần giữ điều kiện bắt buộc (như tenant) trong mọi nhánh, và truyền **giá trị** dưới dạng tham số.

### 9.1. Điều kiện tùy chọn không nên làm mất điều kiện bắt buộc

Ví dụ một truy vấn có điều kiện **tenant_id = ?** và thêm các mệnh đề tùy theo tham số được cung cấp. Không ghép cả biểu thức người dùng nhập vào SQL. Các mảnh SQL cố định do lập trình viên kiểm soát có thể được nối một cách an toàn; dữ liệu như số tiền, thời điểm và trạng thái phải được bind.

Một kiểu SQL khác là **(? IS NULL OR status = ?)** để bật/tắt bộ lọc. Kiểu này có thể đơn giản hóa cấu trúc câu lệnh nhưng cần bind tham số đúng kiểu và có thể làm kế hoạch thực thi khó tối ưu trong một số workload. Không có một mẫu tốt nhất cho mọi cơ sở dữ liệu và phân bố dữ liệu.

### 9.2. JDBC: bộ lọc tùy chọn, projection gọn, thứ tự ổn định

Đoạn mã sau minh họa một repository Java 17+ dùng PostgreSQL/pgJDBC. Nó nhận các điều kiện lọc đã được tầng service chuẩn hóa, giới hạn số kết quả, chỉ chọn những cột cần thiết và dùng đúng thứ tự sắp xếp.

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;

public final class OrderSearchRepository {

    public enum Status { NEW, PAID, CANCELLED }

    public record OrderListItem(
            long orderId,
            String status,
            BigDecimal totalAmount,
            Instant createdAt
    ) {}

    public List<OrderListItem> search(
            Connection connection,
            long authorizedTenantId,
            Status status,
            BigDecimal minAmount,
            Instant fromInclusive,
            Instant toExclusive,
            int limit
    ) throws SQLException {

        if (limit < 1 || limit > 200) {
            throw new IllegalArgumentException("limit must be 1..200");
        }
        if (minAmount != null && minAmount.signum() < 0) {
            throw new IllegalArgumentException("minAmount must be non-negative");
        }
        if (fromInclusive != null && toExclusive != null
                && !fromInclusive.isBefore(toExclusive)) {
            throw new IllegalArgumentException("invalid time range");
        }

        StringBuilder sql = new StringBuilder("""
                SELECT order_id, status, total_amount, created_at
                FROM purchase_order
                WHERE tenant_id = ?
                """);

        if (status != null)        sql.append(" AND status = ?");
        if (minAmount != null)     sql.append(" AND total_amount >= ?");
        if (fromInclusive != null) sql.append(" AND created_at >= ?");
        if (toExclusive != null)   sql.append(" AND created_at < ?");

        sql.append("""
                 ORDER BY created_at DESC, order_id DESC
                 LIMIT ?
                """);

        List<OrderListItem> result = new ArrayList<>();

        try (PreparedStatement ps =
                     connection.prepareStatement(sql.toString())) {
            int index = 1;
            ps.setLong(index++, authorizedTenantId);

            if (status != null) {
                ps.setString(index++, status.name());
            }
            if (minAmount != null) {
                ps.setBigDecimal(index++, minAmount);
            }
            if (fromInclusive != null) {
                ps.setObject(index++,
                        OffsetDateTime.ofInstant(fromInclusive, ZoneOffset.UTC));
            }
            if (toExclusive != null) {
                ps.setObject(index++,
                        OffsetDateTime.ofInstant(toExclusive, ZoneOffset.UTC));
            }
            ps.setInt(index, limit);

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    OffsetDateTime timestamp =
                            rs.getObject("created_at", OffsetDateTime.class);

                    result.add(new OrderListItem(
                            rs.getLong("order_id"),
                            rs.getString("status"),
                            rs.getBigDecimal("total_amount"),
                            timestamp.toInstant()
                    ));
                }
            }
        }

        return result;
    }
}
~~~

**Những điểm cần kiểm tra khi dùng thực tế:**

- **authorizedTenantId** phải đến từ danh tính/quyền đã được xác thực, không tin một tenant_id tùy ý do người dùng nhập.
- **Status** là enum nên tên trạng thái đưa vào SQL thuộc tập cố định; ngay cả vậy, vẫn bind bằng tham số.
- Tham số **null** trong chữ ký repository có nghĩa **bỏ qua bộ lọc tương ứng**, không có nghĩa tìm những hàng có cột NULL. Nếu cần tìm NULL, phải có lựa chọn API riêng.
- Hai mốc **Instant** xác định khoảng đầu đóng/cuối mở; ví dụ chuyển thành **OffsetDateTime** theo UTC cho pgJDBC.
- **StringBuilder** chỉ nối các mảnh cú pháp SQL cố định trong mã. Tuyệt đối không nối nội dung nhập của người dùng thành SQL.
- Câu SELECT chỉ trả những cột DTO cần; **internal_note** không được đọc.
- **LIMIT** được bind như một tham số số nguyên và bị chặn ở mức 200.
- **try-with-resources** đóng statement/result set; connection do tầng gọi quản lý. Mẫu này chưa bao gồm timeout, logging, quản lý giao dịch và xử lý lỗi ở service.

Ví dụ yêu cầu **status = PAID**, **minAmount = 100000**, khoảng từ ngày 20 đến trước ngày 21/11 theo UTC sẽ có câu SQL gồm các điều kiện tương ứng. Nếu không có **minAmount**, mệnh đề **total_amount >= ?** hoàn toàn không được thêm, không còn dấu tham số “rỗng” cần bind.

### 9.3. Sắp xếp động: tên cột không thể bind như giá trị

Sai lầm thường gặp:

~~~sql
-- Không hoạt động như mong muốn để thay thế tên cột.
ORDER BY ?
~~~

Dấu **?** dùng cho **giá trị dữ liệu**, không thay cho cú pháp SQL như tên bảng, tên cột, hướng ASC/DESC. Nếu giao diện cho người dùng chọn “mới nhất”, “giá cao nhất” hoặc “ID tăng dần”, hãy ánh xạ lựa chọn đó sang **các biểu thức ORDER BY được định nghĩa sẵn**:

~~~java
enum OrderSort { NEWEST, AMOUNT_HIGH_TO_LOW, ID_ASC }

static String orderBy(OrderSort sort) {
    return switch (sort) {
        case NEWEST ->
            "created_at DESC, order_id DESC";
        case AMOUNT_HIGH_TO_LOW ->
            "total_amount DESC, order_id DESC";
        case ID_ASC ->
            "order_id ASC";
    };
}
~~~

Phần SQL được nối từ **giá trị trả về của switch** (do mã chương trình kiểm soát), không nối chuỗi người dùng nhập trực tiếp vào ORDER BY. Với mỗi kiểu sắp xếp, bổ sung khóa duy nhất cuối nếu cần thứ tự xác định.

## 10. Từ truy vấn SQL sang đối tượng Java và JPA

### 10.1. DTO là hợp đồng đọc, không phải toàn bộ entity

Giao diện danh sách chỉ cần:

~~~java
public record OrderListItem(
        long orderId,
        String status,
        java.math.BigDecimal totalAmount,
        java.time.Instant createdAt
) {}
~~~

Không cần tạo object chứa mọi cột của bảng rồi xóa những trường không dùng. DTO chuyên biệt làm rõ dữ liệu mà endpoint trả ra và giảm việc mang theo các trường nhạy cảm vào những lớp không cần biết chúng.

Khi ánh xạ kiểu:

| SQL | Java thường phù hợp | Lưu ý |
| --- | --- | --- |
| BIGINT NOT NULL | long / Long | Nếu SQL NULL, primitive không biểu diễn được |
| VARCHAR | String | Có thể null nếu cột/biểu thức cho phép |
| NUMERIC(14,2) | BigDecimal | Tránh double cho số tiền |
| TIMESTAMPTZ (PostgreSQL) | Instant / OffsetDateTime | Xác định rõ instant và múi giờ hiển thị |
| BOOLEAN | boolean / Boolean | Dùng boxed nếu có thể NULL |

### 10.2. JPQL: lọc, sắp xếp và projection

Giả sử ứng dụng có entity **PurchaseOrderEntity** với các thuộc tính **tenantId**, **status**, **totalAmount**, **createdAt**, **id**, và DTO **com.example.OrderListItemDto** có constructor tương ứng. JPQL có thể viết:

~~~java
List<OrderListItemDto> orders =
        entityManager.createQuery(
            "SELECT new com.example.OrderListItemDto(" +
            "o.id, o.status, o.totalAmount, o.createdAt) " +
            "FROM PurchaseOrderEntity o " +
            "WHERE o.tenantId = :tenantId " +
            "AND o.status = :status " +
            "ORDER BY o.createdAt DESC, o.id DESC",
            OrderListItemDto.class
        )
        .setParameter("tenantId", authorizedTenantId)
        .setParameter("status", "PAID")
        .setMaxResults(20)
        .getResultList();
~~~

Đây là minh họa cú pháp: tên lớp DTO, kiểu thuộc tính và tên package phải khớp mã nguồn thực tế. Trong JPQL, **tên thuộc tính entity** được dùng thay cho tên cột SQL.

**getResultList()** trả danh sách có thể rỗng. **setMaxResults(20)** giới hạn số kết quả trả theo ngữ nghĩa truy vấn JPA. Nếu muốn phân trang, có thể sử dụng **setFirstResult(offset)** nhưng cần tính đến nhược điểm OFFSET và JOIN với collection.

Nếu ứng dụng sử dụng JPA Criteria API hoặc công cụ query builder, mục tiêu vẫn là tạo biểu thức lọc có tham số, projection đúng nhu cầu, thứ tự xác định và bộ lọc quyền được áp dụng trong mọi nhánh truy vấn.

### 10.3. Cẩn thận với JOIN FETCH và N+1

Khi truy vấn entity rồi truy cập liên kết lười tải (lazy loading), ORM có thể sinh thêm một SELECT cho mỗi hàng, tạo vấn đề **N+1 queries**. Có thể xử lý bằng DTO projection có JOIN cần thiết, batch loading hoặc fetch plan thích hợp.

Tuy nhiên, **JOIN FETCH một collection nhiều hàng** cùng với pagination có thể tạo ra nhiều hàng trung gian hoặc buộc provider giới hạn kết quả trong bộ nhớ. Không mặc định “fetch hết mọi quan hệ một lần” là tối ưu. Hãy chọn dữ liệu thực sự phục vụ màn hình và quan sát SQL do ORM phát ra.

## 11. Lọc, sắp xếp và phân trang phải được thiết kế cùng nhau

### 11.1. OFFSET phụ thuộc thứ tự xác định

~~~sql
SELECT order_id, status, total_amount, created_at
FROM purchase_order
WHERE tenant_id = 10
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 40;
~~~

Truy vấn trên lấy tối đa 20 hàng sau 40 hàng đầu theo thứ tự đã định. Không có ORDER BY, “trang 3” có thể không ổn định và không có ý nghĩa rõ.

OFFSET sâu có thể làm tăng chi phí vì hệ thống phải bỏ qua nhiều hàng. Khi có các INSERT/DELETE hoặc cập nhật khóa sắp xếp giữa hai lần đọc, các vị trí hàng có thể dịch chuyển, tạo trùng lặp hoặc bỏ sót giữa các trang.

### 11.2. Keyset pagination gắn chặt với bộ lọc và thứ tự

Nếu sắp xếp theo:

~~~sql
ORDER BY created_at DESC, order_id DESC
~~~

thì trang tiếp theo phải dùng cursor gồm **created_at** và **order_id** của hàng cuối trang trước:

~~~sql
SELECT order_id, status, total_amount, created_at
FROM purchase_order
WHERE tenant_id = 10
  AND status = 'PAID'
  AND (created_at, order_id)
      < (TIMESTAMPTZ '2026-11-20 10:30:00+00', 1001)
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Đây là cú pháp **so sánh bộ giá trị của PostgreSQL**; hai trường sort được khai báo NOT NULL nên không phát sinh trường hợp NULL trong so sánh cursor. Trong Java thực tế phải **bind** cả timestamp và ID.

Cursor chỉ còn có ý nghĩa nếu **tenant, bộ lọc status và kiểu sắp xếp không đổi** giữa hai request. Nếu người dùng chuyển từ “đơn đã thanh toán” sang “mọi đơn” hoặc đổi sắp xếp sang tổng tiền, phải bắt đầu lại phân trang hoặc xây cursor mới phù hợp.

Ngay cả keyset cũng không bảo đảm snapshot cố định khi dữ liệu thay đổi giữa các request. Nếu cần xuất một tập bản ghi chính xác tại một thời điểm hoặc tránh bỏ sót do cập nhật khóa sắp xếp, phải thiết kế snapshot/isolation/đánh dấu mốc theo yêu cầu nghiệp vụ.

### 11.3. Đếm kết quả với cùng bộ lọc

Một API trả **totalCount** thường cần truy vấn COUNT dùng cùng phạm vi và điều kiện WHERE:

~~~sql
SELECT COUNT(*) AS total_count
FROM purchase_order
WHERE tenant_id = 10
  AND status = 'PAID';
~~~

Nếu truy vấn danh sách lọc thêm thời gian nhưng COUNT không lọc thời gian, số lượng tổng sẽ sai về mặt API. Nên tái sử dụng một định nghĩa filter có chủ đích ở tầng repository hoặc query builder để tránh sai lệch.

Khi COUNT và SELECT chạy riêng, chúng có thể quan sát hai trạng thái dữ liệu khác nhau dưới mức cô lập thông thường như READ COMMITTED. Nếu giao diện yêu cầu khớp tuyệt đối ở một snapshot, cần chọn chiến lược giao dịch phù hợp; nếu chỉ cần số lượng tham khảo, nên nói rõ khả năng thay đổi.

## 12. Chỉ mục và bộ tối ưu truy vấn

Một truy vấn đúng có thể chậm khi dữ liệu tăng. Ví dụ đường đọc phổ biến:

~~~sql
SELECT order_id, status, total_amount, created_at
FROM purchase_order
WHERE tenant_id = 10
  AND status = 'PAID'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Có thể cân nhắc chỉ mục PostgreSQL:

~~~sql
CREATE INDEX idx_po_tenant_status_created_id
ON purchase_order (
    tenant_id,
    status,
    created_at DESC,
    order_id DESC
);
~~~

Giải thích:

- **tenant_id** và **status** là điều kiện so sánh bằng, hữu ích ở đầu chỉ mục cho truy vấn tương ứng.
- **created_at DESC**, **order_id DESC** phù hợp với thứ tự danh sách cần đọc.
- Khi có chỉ mục và phân bố dữ liệu phù hợp, database có thể tìm vùng dữ liệu thỏa điều kiện rồi lấy hàng theo thứ tự mà không cần sắp xếp toàn bộ.

Tuy nhiên, một chỉ mục tối ưu cho truy vấn có **status = 'PAID'** chưa chắc tối ưu cho truy vấn chỉ lọc **tenant_id** mà không lọc status. Bởi thứ tự cột trong chỉ mục có ý nghĩa, khi lựa chọn bộ chỉ mục cần xem **tập truy vấn chủ lực**, không chỉ một câu lệnh.

### 12.1. Covering index và index-only scan

PostgreSQL có thể dùng **INCLUDE** để thêm cột không tham gia khóa sắp xếp/lọc vào chỉ mục:

~~~sql
CREATE INDEX idx_po_listing_cover
ON purchase_order (
    tenant_id, status, created_at DESC, order_id DESC
)
INCLUDE (total_amount);
~~~

Nếu các cột mà truy vấn cần đều có trong chỉ mục, cơ sở dữ liệu **có thể** thực hiện **index-only scan** trong một số điều kiện, nhưng vẫn phụ thuộc visibility map và trạng thái dữ liệu MVCC; không bảo đảm tránh mọi truy cập bảng chính.

Đổi lại, chỉ mục rộng hơn chiếm dung lượng lớn và tăng chi phí INSERT/UPDATE. Không tạo cả hai chỉ mục trong ví dụ một cách máy móc; chọn cấu hình có ích sau khi đo workload thực.

### 12.2. EXPLAIN và đo hiệu năng

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, status, total_amount, created_at
FROM purchase_order
WHERE tenant_id = 10
  AND status = 'PAID'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Trong PostgreSQL, **EXPLAIN ANALYZE thực sự chạy câu lệnh**, nên sử dụng ở môi trường và thời điểm phù hợp. Quan sát:

- Bộ tối ưu dùng **Index Scan**, **Index Only Scan** hay quét tuần tự?
- Có bước **Sort** hoặc nhiều hàng trung gian không?
- Số hàng dự kiến và thực tế chênh lệch bao nhiêu?
- Số block được đọc từ bộ nhớ/đĩa và thời gian thực thi thế nào?
- Điều kiện được dùng để xác định phạm vi index hay chỉ được kiểm tra sau khi đọc?

Đối với dữ liệu ít, quét tuần tự có thể nhanh hơn dùng chỉ mục. Một câu SQL không phải lúc nào cũng có kế hoạch tối ưu giống nhau khi tham số status, tenant hoặc độ lớn tập dữ liệu thay đổi.

### 12.3. Biểu thức lọc có thể ảnh hưởng chỉ mục

Ví dụ:

~~~sql
WHERE LOWER(status) = 'paid'
~~~

có thể khiến chỉ mục B-tree bình thường trên **status** không được dùng trực tiếp như điều kiện **status = 'PAID'**, trừ khi có chỉ mục biểu thức hoặc tối ưu tương ứng. Nếu trạng thái được chuẩn hóa thành enum/giá trị cố định, so sánh trực tiếp thường rõ ràng hơn.

Với các cột thời gian, ưu tiên lọc bằng mốc bắt đầu/kết thúc như phần 4 thay cho ép **DATE(created_at)** trong mỗi hàng khi không có lý do cụ thể.

## 13. Phân quyền dữ liệu và ranh giới persistence

Lọc và chọn cột không chỉ là vấn đề hiệu năng. Trong API đa tenant, **tenant_id = ?** là phần của chính sách truy cập dữ liệu. Nếu quên điều kiện này ở bất kỳ một nhánh truy vấn nào, người dùng có thể thấy số đơn, tên khách, tổng tiền hoặc ghi chú của tenant khác.

Những quy tắc cần áp dụng:

1. Lấy phạm vi tenant và quyền từ ngữ cảnh xác thực, không tin một tenant_id tự khai báo.
2. Áp dụng điều kiện quyền ở **truy vấn database**; không đọc dữ liệu không được phép về Java rồi mới lọc.
3. Với JOIN, chú ý các khóa liên kết có phạm vi tenant, tránh dùng customer_id không đủ định danh toàn cục.
4. Tránh log đầy đủ các kết quả truy vấn hoặc tham số nhạy cảm.
5. Chỉ chọn cột phù hợp vai trò và mục đích xử lý dữ liệu; DTO trả cho khách hàng khác DTO quản trị nội bộ.
6. Nếu hệ thống có row-level security ở database, vẫn phải cấu hình danh tính/kết nối và kiểm thử ranh giới phù hợp; nó là cơ chế bổ sung cho thiết kế quyền ở tầng ứng dụng.

**PreparedStatement** giúp truyền tham số an toàn và tránh phần lớn SQL injection ở vị trí giá trị khi được dùng đúng, nhưng không tự kiểm tra **authorization**. Cũng cần kiểm soát cú pháp động như tên cột và hướng sort; bind parameter không thay cho whitelist ở những chỗ đó.

## 14. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Thiếu ngoặc quanh OR | Một nhánh có thể bỏ qua tenant_id hoặc điều kiện bắt buộc | Nhóm điều kiện theo đúng logic nghiệp vụ |
| Dùng BETWEEN cho cuối ngày | Dễ xử lý sai mốc cuối, chồng lấn giữa hai ngày | Dùng khoảng **>= start AND < end** |
| So sánh **= NULL** | Không tìm được hàng NULL như dự định | Dùng **IS NULL / IS NOT NULL** |
| Nghĩ ILIKE '%abc%' luôn nhanh | Có thể quét nhiều dữ liệu | Đo workload; cân nhắc pg_trgm/full-text nếu phù hợp |
| Không có ORDER BY | Thứ tự kết quả không được bảo đảm | Sắp xếp rõ ràng |
| ORDER BY created_at không có khóa phụ | Các hàng cùng thời điểm có thứ tự bất định | Thêm **order_id** duy nhất cuối |
| Nối giá trị người dùng vào SQL | Nguy cơ SQL injection và lỗi escaping | Dùng PreparedStatement/typed parameter |
| Bind tên cột ORDER BY như **?** | Cú pháp không đại diện identifier | Ánh xạ lựa chọn sort sang whitelist |
| SELECT \* cho API danh sách | Đọc thừa dữ liệu, có thể lộ trường nhạy cảm | Projection theo DTO |
| JOIN 1:N để lọc tồn tại | Nhân hàng cha và làm sai đếm/paging | Dùng EXISTS nếu chỉ cần kiểm tra có liên kết |
| Dùng DISTINCT để “chọn hàng mới nhất” | DISTINCT không diễn đạt quy tắc chọn hàng theo nhóm | Dùng window function hoặc truy vấn rõ quy tắc |
| OFFSET lớn | Có thể phải bỏ qua nhiều hàng, trang chậm | Cân nhắc keyset theo khóa sắp xếp |
| Đổi filter nhưng dùng cursor cũ | Trả hàng trùng, bỏ sót hoặc sai phạm vi | Cursor gắn với filter/sort và tenant |
| COUNT không dùng cùng WHERE với SELECT | totalCount không khớp danh sách | Dùng chung định nghĩa filter |
| Tin index luôn cải thiện truy vấn | Tăng chi phí ghi/lưu trữ mà không hiệu quả | Kiểm chứng bằng EXPLAIN/benchmark |
| Lọc tenant sau khi lấy dữ liệu về Java | Có thể lộ dữ liệu ngoài phạm vi được phép | Lọc ngay trong SQL và kiểm tra quyền |

## 15. Thực hành theo tình huống

### Bài tập 1: lọc và sắp xếp theo yêu cầu

Yêu cầu: liệt kê đơn **PAID** của tenant **10**, có tổng tiền từ **100000** trở lên, mới nhất trước, tối đa **10** đơn. Chỉ trả **order_id**, **total_amount**, **created_at**.

**Lời giải gợi ý:**

~~~sql
SELECT order_id, total_amount, created_at
FROM purchase_order
WHERE tenant_id = 10
  AND status = 'PAID'
  AND total_amount >= 100000
ORDER BY created_at DESC, order_id DESC
LIMIT 10;
~~~

Dữ liệu ví dụ trả đơn **1001**; đơn **1003** không đủ số tiền, đơn **1004** thuộc tenant khác.

### Bài tập 2: tìm lỗi ưu tiên AND/OR

Xem câu truy vấn:

~~~sql
SELECT order_id
FROM purchase_order
WHERE tenant_id = 10
  AND status = 'PAID'
   OR status = 'NEW';
~~~

**Câu hỏi:** Vì sao không an toàn với hệ thống đa tenant?

**Gợi ý:** Do AND ưu tiên trước OR, phần **OR status = 'NEW'** có thể chọn đơn NEW của mọi tenant. Nếu yêu cầu các trạng thái PAID hoặc NEW chỉ trong tenant 10, viết:

~~~sql
WHERE tenant_id = 10
  AND status IN ('PAID', 'NEW')
~~~

hoặc đặt ngoặc tương đương.

### Bài tập 3: xử lý ngày địa phương

Người dùng ở Việt Nam chọn tất cả đơn tạo vào **20/11/2026** theo giờ Việt Nam. Có nên dùng **created_at >= '2026-11-20T00:00:00Z'** không?

**Gợi ý:** Không nếu yêu cầu là ngày theo múi giờ Việt Nam. Hãy xác định **đầu ngày 20/11** và **đầu ngày 21/11** ở zone **Asia/Ho_Chi_Minh**, chuyển sang hai **Instant** và lọc theo **>= start AND < end**. Thời điểm UTC tương ứng có thể nằm ở ngày lịch khác.

### Bài tập 4: cần một đơn mới nhất hay các ID phân biệt?

Yêu cầu: mỗi khách hàng lấy **một đơn mới nhất**, nếu hai đơn có cùng created_at thì lấy đơn có ID lớn hơn. Có đủ nếu viết:

~~~sql
SELECT DISTINCT customer_id, order_id, created_at
FROM purchase_order;
~~~

**Đáp án:** Không. Vì order_id khác nhau, các hàng không trùng theo ba cột trên. Cần dùng **ROW_NUMBER() OVER (PARTITION BY tenant_id, customer_id ORDER BY created_at DESC, order_id DESC)**, rồi lấy hàng có số thứ tự 1, hoặc giải pháp tương đương.

### Bài tập 5: filter và projection trong Java

Một endpoint danh sách cần **orderId**, **status**, **totalAmount** nhưng truy vấn trả cả **internal_note** và **customer_id**. Có thể tối ưu ở đâu?

**Gợi ý:** Đổi SELECT chỉ lấy các cột cần; xây DTO danh sách phù hợp; giữ điều kiện tenant/status trong SQL. Nếu controller không cần created_at để hiển thị nhưng repository dùng nó làm sort, có thể ORDER BY created_at mà không đưa vào projection trong truy vấn SELECT thông thường.

### Bài tập 6: chỉ mục cho hai loại màn hình

Màn hình A luôn lọc **tenant_id + status** và sắp theo created_at. Màn hình B chỉ lọc **tenant_id** và sắp theo created_at. Một index **(tenant_id, status, created_at DESC)** có chắc phù hợp cả hai như nhau không?

**Gợi ý:** Không. Khi B không lọc status, thứ tự theo created_at có thể không liên tục theo toàn tenant trong chỉ mục đó. Cần đo các đường đọc chủ lực và cân nhắc thêm/chọn chỉ mục tương ứng, không tạo index theo cảm tính.

### Bài tập 7: kiểm tra ranh giới dữ liệu

API chỉ cho nhân viên tenant 10 đọc đơn. Một lập trình viên dùng SQL:

~~~sql
SELECT order_id, status, total_amount
FROM purchase_order
WHERE status = ?
ORDER BY created_at DESC;
~~~

**Câu hỏi:** Thiếu điều gì dù đã dùng tham số hóa?

**Đáp án:** Truy vấn thiếu **tenant_id đã được xác thực/ủy quyền**. Tham số hóa chống SQL injection ở vị trí giá trị không thay cho kiểm soát quyền truy cập dữ liệu.

## 16. Kết luận

**WHERE** quyết định hàng nào có mặt trong kết quả, **ORDER BY** quyết định thứ tự và **SELECT** quyết định các trường được đọc. Kết hợp chúng với **LIMIT** giúp tầng persistence chỉ lấy những bản ghi thực sự cần cho màn hình hoặc tác vụ Java.

Một truy vấn đáng tin cậy phải lọc đúng phạm vi quyền, xử lý **NULL** và ranh giới thời gian chính xác, sắp xếp bằng thứ tự xác định và sử dụng projection có chủ đích. Khi API cho phép điều kiện hoặc kiểu sắp xếp động, chỉ thêm các mảnh SQL do mã kiểm soát và bind tất cả giá trị dữ liệu; với tên cột/hướng ORDER BY, dùng danh sách cho phép. **JOIN**, **DISTINCT** và phân trang có thể thay đổi số hàng hoặc cách lấy dữ liệu, nên phải được thiết kế theo đúng câu hỏi nghiệp vụ.

Hiệu năng đến từ truy vấn có mục tiêu, chỉ mục phù hợp và đo lường kế hoạch thực thi, không chỉ từ việc thêm LIMIT hoặc SELECT ít cột. Khi áp dụng vào Java, hãy để repository trả DTO rõ ràng, quản lý đúng vòng đời kết nối và giữ quy tắc nhất quán giữa các đường đọc.

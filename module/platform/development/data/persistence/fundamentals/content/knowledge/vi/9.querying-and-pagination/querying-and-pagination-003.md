# Thứ tự xác định và khóa phụ khi giá trị sắp xếp trùng nhau

## 1. Vì sao ORDER BY một cột đôi khi chưa đủ?

Giả sử một API Java hiển thị danh sách đơn hàng từ mới đến cũ. Câu truy vấn ban đầu là:

~~~sql
SELECT order_id, created_at, status
FROM purchase_order
WHERE tenant_id = 10
ORDER BY created_at DESC
LIMIT 20;
~~~

Câu lệnh có **ORDER BY**, nhưng chưa chắc tạo được **thứ tự xác định giữa mọi bản ghi**. Nếu hai đơn hàng có cùng **created_at**, SQL chỉ yêu cầu chúng đứng cùng một nhóm theo thời gian; nó không quy định đơn nào phải xuất hiện trước trong nhóm đó. Thứ tự thực tế có thể phụ thuộc kế hoạch thực thi, vị trí dữ liệu, chỉ mục hoặc thay đổi khi chạy lại.

Vấn đề đặc biệt rõ khi kết quả được **giới hạn**, **phân trang**, **xuất theo lô**, hoặc khi hệ thống cần giải thích tại sao một bản ghi đứng trước bản ghi khác. Hai lần gọi cùng bộ lọc có thể trả một tập hàng khác nhau tại ranh giới trang, ngay cả khi dữ liệu không đổi, nếu tiêu chí sắp xếp chưa phân biệt hết các hàng.

Cách giải quyết thông dụng là thêm một **khóa phụ dùng để phân định khi hòa (tie-breaker)**, thường là khóa chính:

~~~sql
ORDER BY created_at DESC, order_id DESC
~~~

Bài học thuộc chương **Truy vấn và phân trang** của học phần **DATA_PERSISTENCE_FUNDAMENTALS**. Kiến thức này giúp người học thiết kế tầng persistence cho Java với hợp đồng đọc ổn định, đồng thời hiểu tác động của chỉ mục, JOIN, giao dịch và thay đổi dữ liệu đồng thời.

Sau bài học, người học có thể:

1. Phân biệt **thứ tự xác định trong một tập dữ liệu** với **kết quả giữ nguyên khi dữ liệu thay đổi theo thời gian**.
2. Chọn khóa phụ thực sự bảo đảm duy nhất trong phạm vi truy vấn.
3. Xây dựng **ORDER BY** có nhiều tiêu chí ASC/DESC và kiểm soát cách sắp xếp NULL.
4. Giải thích vì sao LIMIT/OFFSET có thể gây mất hoặc lặp bản ghi khi các giá trị sort trùng nhau.
5. Viết điều kiện **keyset pagination** tương ứng chính xác với thứ tự đã chọn.
6. Triển khai một API phân trang Java/JDBC sử dụng cursor, giới hạn kích thước trang và truy vấn có tham số.
7. Nhận biết những giới hạn do cập nhật đồng thời, JOIN, collation và những truy vấn gom nhóm.

## 2. Ví dụ dữ liệu: nhiều đơn có cùng thời điểm

Bảng PostgreSQL tối giản:

~~~sql
CREATE TABLE purchase_order (
    tenant_id    BIGINT NOT NULL,
    order_id     BIGINT NOT NULL,
    status       VARCHAR(20) NOT NULL
                 CHECK (status IN ('NEW', 'PAID', 'CANCELLED')),
    created_at   TIMESTAMPTZ NOT NULL,
    total_amount NUMERIC(12, 2) NOT NULL CHECK (total_amount >= 0),
    PRIMARY KEY (tenant_id, order_id)
);
~~~

Ở đây, **order_id chỉ cần duy nhất trong một tenant**; cặp **(tenant_id, order_id)** mới là khóa chính trên toàn bảng. Mọi truy vấn danh sách theo tenant cần lọc đúng **tenant_id**. Đó là một phần của hợp đồng dữ liệu và chính sách truy cập, không chỉ là một tối ưu hiệu năng.

Giả sử các hàng đã được lưu:

| tenant_id | order_id | created_at (UTC) | status |
| ---: | ---: | --- | --- |
| 10 | 105 | 2026-11-20 09:30:00 | PAID |
| 10 | 104 | 2026-11-20 09:30:00 | NEW |
| 10 | 103 | 2026-11-20 09:30:00 | PAID |
| 10 | 102 | 2026-11-19 16:00:00 | PAID |
| 10 | 101 | 2026-11-18 08:00:00 | CANCELLED |
| 20 | 201 | 2026-11-20 09:30:00 | NEW |

Ba đơn **105**, **104**, **103** có cùng timestamp. Nếu chỉ sắp xếp theo **created_at DESC**, bất kỳ thứ tự nào giữa ba đơn này đều đáp ứng tiêu chí thời gian. Không thể yêu cầu SQL tự giữ thứ tự giống các lần chạy trước.

Khi dùng:

~~~sql
SELECT order_id, created_at, status
FROM purchase_order
WHERE tenant_id = 10
ORDER BY created_at DESC, order_id DESC;
~~~

ta xác định được thứ tự mong muốn:

~~~text
105 -> 104 -> 103 -> 102 -> 101
~~~

Đơn tenant 20 bị loại bởi WHERE. Các đơn có timestamp bằng nhau được sắp tiếp theo **order_id** lớn đến nhỏ, nên không còn cặp hàng nào trong tenant 10 hòa nhau ở toàn bộ khóa sắp xếp.

## 3. Thứ tự bộ phận và thứ tự toàn phần

Một phép sắp xếp theo **created_at** chỉ xác định được quan hệ trước/sau đối với những hàng có timestamp khác nhau. Các hàng cùng timestamp vẫn hòa nhau theo tiêu chí đang dùng.

Ta có thể hình dung:

~~~text
ORDER BY created_at DESC

Nhóm mới nhất: [105, 104, 103]  <- chưa rõ thứ tự bên trong
Nhóm tiếp:     [102]
Nhóm cũ nhất:  [101]
~~~

Khi thêm khóa phụ, mọi hàng có cặp **(created_at, order_id)** khác nhau:

~~~text
ORDER BY created_at DESC, order_id DESC

105 > 104 > 103 > 102 > 101
~~~

Ở đây, dấu **>** trong hình minh họa chỉ thứ tự hiển thị từ trước đến sau; không phải là phép so sánh trực tiếp toàn bộ ID bất kể timestamp. Hai tiêu chí được so sánh **theo thứ tự từ trái sang phải** (*lexicographic order*): ưu tiên created_at; chỉ khi bằng nhau mới xét order_id.

Điều kiện đủ để thứ tự xác định trên một kết quả là: **không có hai hàng kết quả khác nhau cùng hòa nhau theo tất cả biểu thức sắp xếp**, dưới quy tắc so sánh/collation đang dùng. Thêm một định danh duy nhất làm tiêu chí cuối thường đạt điều này.

### 3.1. Thứ tự xác định không đồng nghĩa dữ liệu bất biến

Phải tách hai nhận định:

- **Tại một thời điểm, với cùng tập hàng và cùng quy tắc so sánh**, ORDER BY kết thúc bằng khóa duy nhất xác định vị trí tương đối của mọi hàng.
- **Giữa hai request**, nếu có INSERT, DELETE hoặc UPDATE, tập hàng và giá trị sort có thể đổi. Câu ORDER BY vẫn xác định, nhưng kết quả có thể khác.

Khóa phụ giải quyết vấn đề **các giá trị sắp xếp bằng nhau**. Nó không đóng băng dữ liệu. Phân trang qua nhiều HTTP request còn phải xét **tính nhất quán giao dịch** và **sự thay đổi đồng thời**.

### 3.2. Đừng dựa vào thứ tự vật lý

Những điều sau **không được coi là cam kết thứ tự SQL**:

- Thứ tự INSERT.
- Thứ tự trả về đã thấy trong lần chạy trước.
- Thứ tự cột đầu tiên trong khóa chính nếu không khai báo ORDER BY.
- Vị trí hàng trên đĩa, số trang lưu trữ hoặc thứ tự quét index tình cờ được chọn.
- Thứ tự trong một subquery không được truy vấn ngoài bảo đảm dùng đúng ý đồ sắp xếp.

Chỉ **ORDER BY ở tầng truy vấn trả kết quả** mới diễn đạt hợp đồng thứ tự đầu ra; các tầng khác như danh sách Java không nên được kỳ vọng tự duy trì một thứ tự không được khai báo từ SQL.

## 4. Chọn khóa phụ đúng

Khóa phụ tốt có một số đặc tính:

| Tiêu chí | Vì sao cần? | Ví dụ |
| --- | --- | --- |
| **Duy nhất trong tập cần sắp** | Không còn hai hàng hòa nhau | order_id trong cùng tenant |
| **Ổn định** | Giảm việc bản ghi đổi vị trí khi phân trang | ID không sửa sau khi tạo |
| **Không NULL**, nếu có thể | Dễ so sánh trong cursor | PRIMARY KEY |
| **Có ý nghĩa kỹ thuật rõ ràng** | Tránh phụ thuộc vào tên hoặc giá trị hay thay đổi | Khóa định danh thay vì full_name |
| **Có thể kết hợp với chỉ mục** | Hỗ trợ truy vấn lọc và sắp xếp | (tenant_id, created_at DESC, order_id DESC) |

Một khóa phụ không nhất thiết phải tăng theo thời gian. **UUID** cũng có thể dùng để phá hòa nếu duy nhất và có thứ tự so sánh được quy định rõ; chỉ không nên diễn giải UUID như thứ tự tạo nếu hệ thống không có bảo đảm tương ứng.

### 4.1. Khóa chính ghép và phạm vi tính duy nhất

Với **PRIMARY KEY (tenant_id, order_id)**, câu:

~~~sql
WHERE tenant_id = 10
ORDER BY created_at DESC, order_id DESC
~~~

có thứ tự xác định vì **order_id** là duy nhất *trong tenant 10*. Ngược lại, nếu truy vấn xuyên tenant:

~~~sql
SELECT tenant_id, order_id, created_at
FROM purchase_order
ORDER BY created_at DESC, order_id DESC;
~~~

hai hàng thuộc hai tenant khác nhau có thể trùng **created_at** và **order_id**. Khi đó, thêm **tenant_id** làm tiêu chí cuối hoặc đưa toàn bộ khóa ghép vào cấu trúc sắp xếp:

~~~sql
ORDER BY created_at DESC, tenant_id ASC, order_id DESC;
~~~

Dãy khóa **(created_at, tenant_id, order_id)** là duy nhất vì cặp **(tenant_id, order_id)** duy nhất. Hướng ASC/DESC là lựa chọn hiển thị; tính duy nhất không phụ thuộc chiều.

### 4.2. Khi khóa phụ vẫn không duy nhất

Ví dụ:

~~~sql
ORDER BY created_at DESC, status ASC
~~~

vẫn không đủ: ba đơn có thể cùng **created_at** và cùng **status**. Muốn kết quả xác định, thêm định danh duy nhất cuối cùng:

~~~sql
ORDER BY created_at DESC, status ASC, order_id DESC
~~~

trong một tenant đã cố định.

Không nên chọn **customer_id** làm khóa phụ cuối cho danh sách đơn, vì một khách hàng có nhiều đơn. Khóa phụ phải phân biệt **các hàng đầu ra**, không chỉ có độ đa dạng cao trên dữ liệu mẫu.

## 5. Phân định khi hòa với nhiều tiêu chí sắp xếp

### 5.1. Nhiều cột được so sánh theo thứ tự ưu tiên

~~~sql
SELECT order_id, status, created_at, total_amount
FROM purchase_order
WHERE tenant_id = 10
ORDER BY status ASC, created_at DESC, order_id DESC;
~~~

Cơ sở dữ liệu ưu tiên **status**; bên trong từng status ưu tiên **created_at**; nếu timestamp còn bằng nhau thì ưu tiên **order_id**.

Có thể đổi thứ tự các cột để thay đổi hoàn toàn ý nghĩa:

~~~sql
ORDER BY created_at DESC, status ASC, order_id DESC;
~~~

Lúc này thời gian quan trọng hơn trạng thái. **Thứ tự khai báo các cột trong ORDER BY chính là thứ tự ưu tiên nghiệp vụ**, không phải một chi tiết tối ưu có thể đảo tùy ý.

### 5.2. Giá trị ưu tiên nghiệp vụ khác thứ tự chữ cái

Nếu yêu cầu **PAID trước NEW trước CANCELLED**, sắp xếp chữ cái thông thường không thể hiện đúng mức ưu tiên. Dùng biểu thức có quy tắc:

~~~sql
SELECT order_id, status, created_at
FROM purchase_order
WHERE tenant_id = 10
ORDER BY
    CASE status
        WHEN 'PAID' THEN 1
        WHEN 'NEW' THEN 2
        WHEN 'CANCELLED' THEN 3
        ELSE 4
    END ASC,
    created_at DESC,
    order_id DESC;
~~~

**CASE** tạo thứ bậc nghiệp vụ; created_at và order_id tiếp tục phân định khi các hàng cùng hạng. Nếu dịch vụ Java cung cấp một tùy chọn sắp xếp này, nên giữ quy tắc tương ứng ở một nơi có kiểm soát và viết kiểm thử cho kết quả.

Biểu thức CASE có thể ảnh hưởng khả năng dùng chỉ mục cho ORDER BY. Khi đây là đường đọc hiệu năng cao, cân nhắc cột hạng được quản lý nhất quán hoặc chỉ mục biểu thức phù hợp với hệ quản trị, sau khi đo thực tế.

### 5.3. ASC và DESC không buộc phải giống nhau

~~~sql
ORDER BY total_amount DESC, order_id ASC;
~~~

Truy vấn đặt tổng tiền cao nhất trước, nhưng khi tiền bằng nhau chọn **ID nhỏ hơn** trước. Dù hai chiều khác nhau, thứ tự vẫn có thể xác định hoàn toàn vì khóa cuối là duy nhất.

Điều này trở nên quan trọng khi triển khai **keyset pagination**: điều kiện “hàng đứng sau cursor” phải theo **đúng chiều của từng tiêu chí**, không dùng một dấu so sánh cho mọi cột.

## 6. NULL và collation: những nguồn hòa nhau dễ bị bỏ qua

### 6.1. NULL cần chính sách sắp xếp tường minh

Giả sử thêm cột **reviewed_at TIMESTAMPTZ NULL**. Những đơn chưa duyệt đều có reviewed_at = NULL. Nếu sắp xếp:

~~~sql
ORDER BY reviewed_at DESC
~~~

nhiều hàng sẽ cùng hòa ở NULL. PostgreSQL mặc định **NULLS FIRST** với DESC và **NULLS LAST** với ASC; các hệ quản trị có thể có mặc định khác.

Có thể viết rõ:

~~~sql
SELECT order_id, reviewed_at
FROM purchase_order
WHERE tenant_id = 10
ORDER BY reviewed_at DESC NULLS LAST, order_id DESC;
~~~

Điều này đặt các đơn đã duyệt gần nhất trước, các đơn chưa duyệt cuối; giữa những hàng có cùng reviewed_at (kể cả NULL), order_id quyết định thứ tự.

**Không nên dùng phép so sánh tuple đơn giản cho keyset khi một thành phần cursor có thể NULL** nếu chưa xử lý riêng. Trong SQL, so sánh với NULL có thể trả UNKNOWN; một điều kiện seek viết như **(reviewed_at, order_id) < (?, ?)** không tự bao quát đúng mọi trường hợp NULLS LAST. Cần thiết kế điều kiện theo từng vùng NULL/không NULL hoặc dùng khóa sắp xếp chuẩn hóa có ngữ nghĩa rõ ràng.

### 6.2. Collation có thể coi các chuỗi khác nhau là bằng nhau khi sắp xếp

Ví dụ danh sách khách hàng sắp theo **display_name**. Một số quy tắc collation có thể xem các chuỗi khác biệt chữ hoa/thường hoặc dấu là tương đương tại mức so sánh dùng cho ORDER BY. Nếu chỉ:

~~~sql
ORDER BY display_name ASC
~~~

các hàng cùng khóa sắp xếp theo collation vẫn có thể đổi vị trí.

Nên thêm ID duy nhất:

~~~sql
ORDER BY display_name ASC, customer_id ASC
~~~

với điều kiện đã lọc về một tenant mà **customer_id** duy nhất.

Nếu ứng dụng cần kết quả ổn định giữa các môi trường, cần đồng nhất **collation, locale và phiên bản quy tắc đối chiếu**. Khóa phụ giải quyết thứ tự giữa các hàng hòa nhau trong cùng cấu hình; nó không bảo đảm toàn bộ danh sách được sắp giống nhau khi collation hoặc giá trị chuẩn hóa thay đổi.

### 6.3. Sắp xếp theo biểu thức cũng cần khóa phụ

~~~sql
ORDER BY LOWER(full_name) ASC, customer_id ASC
~~~

Hai tên “AN” và “an” có thể cùng giá trị **LOWER(full_name)**; customer_id phân định. Tuy nhiên, biểu thức LOWER và collation cần phù hợp ngôn ngữ, và có thể cần chỉ mục biểu thức nếu đường đọc này thường xuyên dùng trên dữ liệu lớn.

## 7. LIMIT và OFFSET: chỗ lỗi thứ tự hòa nhau dễ lộ rõ

Giả sử ứng dụng phân trang mỗi lần **2 hàng** trên dữ liệu tenant 10. Chỉ dùng:

~~~sql
SELECT order_id, created_at
FROM purchase_order
WHERE tenant_id = 10
ORDER BY created_at DESC
LIMIT 2 OFFSET 0;
~~~

Ba đơn 105, 104, 103 đều hòa timestamp. Một kế hoạch thực thi có thể trả **105, 104** cho trang đầu; một truy vấn tiếp theo với **LIMIT 2 OFFSET 2** có thể xem nhóm hòa theo một thứ tự khác, dẫn tới bản ghi lặp hoặc bỏ sót giữa trang ngay cả khi không có ghi mới.

Thêm khóa phụ:

~~~sql
-- Trang 1
SELECT order_id, created_at
FROM purchase_order
WHERE tenant_id = 10
ORDER BY created_at DESC, order_id DESC
LIMIT 2 OFFSET 0;

-- Trang 2
SELECT order_id, created_at
FROM purchase_order
WHERE tenant_id = 10
ORDER BY created_at DESC, order_id DESC
LIMIT 2 OFFSET 2;
~~~

Nếu dữ liệu không đổi, trang 1 có **105, 104**; trang 2 có **103, 102**; trang 3 có **101**.

### 7.1. Khóa phụ vẫn không giải quyết INSERT/DELETE giữa hai request

Xét một danh sách có thứ tự xác định ban đầu:

~~~text
[104, 103, 102, 101]
~~~

API trả trang 1, kích thước 2:

~~~text
Trang 1: [104, 103]
~~~

Trước lúc lấy trang 2, đơn mới **105** được thêm lên đầu danh sách:

~~~text
[105, 104, 103, 102, 101]
~~~

Trang 2 dùng **OFFSET 2** sẽ trả:

~~~text
Trang 2: [103, 102]
~~~

Đơn **103** bị lặp. Đây là hậu quả **vị trí offset dịch chuyển**, không phải lỗi thiếu khóa phụ. Cần phân biệt hai vấn đề:

1. **Khóa phụ duy nhất** giải quyết việc các hàng cùng sort key không có thứ tự rõ.
2. **Kiểu phân trang và chính sách nhất quán** giải quyết rủi ro thay đổi tập dữ liệu giữa các lần đọc.

OFFSET vẫn có ích khi cần nhảy đến trang bất kỳ trên dữ liệu ít thay đổi hoặc khi giao diện chấp nhận tính biến động. Khi danh sách thay đổi liên tục và người dùng cuộn từ đầu đến cuối, **keyset pagination** thường là lựa chọn đáng cân nhắc.

## 8. Keyset pagination: cursor phải chứa toàn bộ khóa sắp xếp

### 8.1. Truy vấn trang đầu

Với thứ tự:

~~~sql
ORDER BY created_at DESC, order_id DESC
~~~

trang đầu của tenant 10 có thể lấy:

~~~sql
SELECT order_id, status, created_at
FROM purchase_order
WHERE tenant_id = 10
ORDER BY created_at DESC, order_id DESC
LIMIT 2;
~~~

Kết quả:

| order_id | created_at (UTC) |
| ---: | --- |
| 105 | 2026-11-20 09:30:00 |
| 104 | 2026-11-20 09:30:00 |

**Cursor** cho trang tiếp theo phải ghi lại cả hai trường của hàng cuối: **created_at = 2026-11-20 09:30:00+00**, **order_id = 104**.

Nếu cursor chỉ chứa timestamp, hệ thống không thể biết trong nhóm 09:30 đã đi đến ID nào. Một điều kiện **created_at < timestamp** sẽ bỏ qua ID 103 có cùng thời điểm; một điều kiện **created_at <= timestamp** có thể trả lại 105 và 104.

### 8.2. Truy vấn trang tiếp theo với thứ tự DESC/DESC

PostgreSQL hỗ trợ so sánh theo bộ giá trị (*row value comparison*):

~~~sql
SELECT order_id, status, created_at
FROM purchase_order
WHERE tenant_id = 10
  AND (created_at, order_id)
      < (TIMESTAMPTZ '2026-11-20 09:30:00+00', 104)
ORDER BY created_at DESC, order_id DESC
LIMIT 2;
~~~

Câu điều kiện **(created_at, order_id) < (cursorTime, cursorId)** tương đương trong trường hợp hai cột đều NOT NULL:

~~~sql
AND (
     created_at < TIMESTAMPTZ '2026-11-20 09:30:00+00'
     OR (
         created_at = TIMESTAMPTZ '2026-11-20 09:30:00+00'
         AND order_id < 104
     )
)
~~~

Với bộ dữ liệu minh họa, trang 2 trả **103, 102**. Trang 3 dùng cursor ở hàng 102 sẽ trả **101**.

**Quy tắc cơ bản:** khi sort theo các trường **đều DESC** thì dùng so sánh **<** cho tuple để đi tới hàng đứng sau. Khi tất cả trường **ASC**, dùng **>**. Điều kiện phải tương ứng chính xác với thứ tự và kiểu dữ liệu; không suy ra từ ID riêng lẻ nếu có tiêu chí đứng trước.

### 8.3. Không dùng một phép so sánh tuple cho chiều hỗn hợp

Nếu sắp xếp:

~~~sql
ORDER BY total_amount DESC, order_id ASC
~~~

thì hàng đứng sau cursor **(lastAmount, lastId)** thỏa:

~~~sql
WHERE tenant_id = ?
  AND (
      total_amount < ?
      OR (total_amount = ? AND order_id > ?)
  )
ORDER BY total_amount DESC, order_id ASC
LIMIT ?;
~~~

Tổng tiền **nhỏ hơn** đứng sau, nhưng trong nhóm tiền bằng nhau, ID **lớn hơn** đứng sau vì ID đang ASC.

Không viết **(total_amount, order_id) < (?, ?)** trong trường hợp này: phép so sánh tuple thông thường đều dùng một hướng cho từng thành phần theo thứ tự từ trái sang phải, nên không thể tự biểu diễn DESC/ASC hỗn hợp. Với nhiều cột hoặc NULL, điều kiện seek có thể phải được xây rõ hơn nữa.

### 8.4. Filter, sort và cursor là cùng một hợp đồng

Cursor tạo cho danh sách **tenant 10, status PAID, ORDER BY created_at DESC, order_id DESC** không thể tùy tiện tái sử dụng khi người dùng chuyển sang **tenant 20**, đổi status sang NEW hoặc đổi sort sang **total_amount DESC**. Cursor khi đó không còn cùng trật tự và phạm vi dữ liệu.

API nên:

- Gắn cursor với phiên bản quy tắc sort/filter, phạm vi tenant được ủy quyền và các giá trị khóa.
- Kiểm tra cấu trúc, kiểu dữ liệu, kích thước và tính toàn vẹn của cursor nếu token được đưa ra client.
- Tạo cursor từ **hàng cuối cùng thực sự trả về** của trang hiện tại.
- Không đưa ID chưa được phân quyền vào một truy vấn chỉ dựa trên dữ liệu cursor do client sửa tùy ý.
- Giới hạn số hàng mỗi trang; tránh một cursor hay limit bất thường tạo truy vấn tốn tài nguyên.

Nếu cursor được mã hóa dưới dạng token base64, **base64 không phải chữ ký hay mã hóa bảo mật**. Khi hợp đồng yêu cầu không cho client sửa token, cần ký/xác thực token hoặc dùng một định danh cursor do server quản lý.

## 9. Minh họa Java/JDBC: đọc trang và tạo cursor

Mẫu sau dùng **Java 17+**, PostgreSQL và **pgJDBC**. Phương thức nhận **authorizedTenantId** từ tầng đã xác thực quyền, một cursor tùy chọn và **pageSize**. Nó đọc **pageSize + 1** hàng để xác định có trang tiếp theo, rồi chỉ trả lại số hàng yêu cầu.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public final class OrderPageRepository {

    public record Cursor(Instant createdAt, long orderId) {
        public Cursor {
            Objects.requireNonNull(createdAt, "createdAt");
            if (orderId <= 0) {
                throw new IllegalArgumentException("invalid orderId");
            }
        }
    }

    public record OrderRow(long orderId, String status, Instant createdAt) {}

    // nextCursor == null nghĩa là không còn trang tiếp theo.
    public record Page(List<OrderRow> items, Cursor nextCursor) {}

    public Page readPage(
            Connection connection,
            long authorizedTenantId,
            Cursor cursor,
            int pageSize
    ) throws SQLException {

        if (authorizedTenantId <= 0) {
            throw new IllegalArgumentException("invalid tenant");
        }
        if (pageSize < 1 || pageSize > 100) {
            throw new IllegalArgumentException("pageSize must be 1..100");
        }

        String sql = cursor == null
                ? """
                  SELECT order_id, status, created_at
                  FROM purchase_order
                  WHERE tenant_id = ?
                  ORDER BY created_at DESC, order_id DESC
                  LIMIT ?
                  """
                : """
                  SELECT order_id, status, created_at
                  FROM purchase_order
                  WHERE tenant_id = ?
                    AND (created_at, order_id) < (?, ?)
                  ORDER BY created_at DESC, order_id DESC
                  LIMIT ?
                  """;

        List<OrderRow> fetched = new ArrayList<>();

        try (PreparedStatement ps = connection.prepareStatement(sql)) {
            int i = 1;
            ps.setLong(i++, authorizedTenantId);

            if (cursor != null) {
                OffsetDateTime time =
                        OffsetDateTime.ofInstant(cursor.createdAt(), ZoneOffset.UTC);
                ps.setObject(i++, time);
                ps.setLong(i++, cursor.orderId());
            }

            ps.setInt(i, pageSize + 1);

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    Instant createdAt =
                            rs.getObject("created_at", OffsetDateTime.class)
                              .toInstant();

                    fetched.add(new OrderRow(
                            rs.getLong("order_id"),
                            rs.getString("status"),
                            createdAt
                    ));
                }
            }
        }

        boolean hasNext = fetched.size() > pageSize;
        List<OrderRow> items = List.copyOf(
                fetched.subList(0, Math.min(pageSize, fetched.size()))
        );

        Cursor next = null;
        if (hasNext) {
            OrderRow lastVisible = items.get(items.size() - 1);
            next = new Cursor(lastVisible.createdAt(), lastVisible.orderId());
        }

        return new Page(items, next);
    }
}
~~~

Phân tích các quyết định quan trọng:

1. **Hai câu SQL cố định** bảo đảm trang đầu không cần điều kiện cursor, các trang sau có điều kiện seek đúng hướng.
2. **PreparedStatement** bind tenant, timestamp, ID và giới hạn; dữ liệu người dùng không được nối thành cú pháp SQL.
3. **authorizedTenantId** đến từ ngữ cảnh đã ủy quyền. Không dùng tenantId tự khai báo từ cursor làm nguồn phân quyền.
4. **TIMESTAMPTZ** được đọc từ pgJDBC dưới dạng **OffsetDateTime**, chuyển thành **Instant** để thể hiện thời điểm tuyệt đối.
5. **pageSize + 1** chỉ để phát hiện còn hàng tiếp theo. Hàng dư được bỏ khỏi danh sách hiển thị.
6. **Cursor** lấy từ hàng cuối **được trả về**, không từ hàng đọc dư.
7. **nextCursor = null** thể hiện không còn trang trong kết quả truy vấn hiện tại. Điều này không khẳng định dữ liệu sẽ không thay đổi trong tương lai.
8. **try-with-resources** đóng PreparedStatement và ResultSet. **Connection** do tầng gọi quản lý theo vòng đời transaction/pool.

Ví dụ này giả định cột **created_at NOT NULL** và **order_id** được cấp phát dương theo hợp đồng nghiệp vụ. Nó chưa bao gồm ký/xác thực cursor token, mã hóa token cho HTTP, timeout, logging, retry hoặc xử lý snapshot giữa nhiều request; các phần đó thuộc thiết kế dịch vụ hoàn chỉnh.

### 9.1. Nếu API cho phép nhiều kiểu ORDER BY?

Không truyền nguyên chuỗi **sort** từ client vào SQL. Phải ánh xạ lựa chọn từ danh sách cho phép tới **cặp ORDER BY + điều kiện seek tương ứng**. Ví dụ:

| Lựa chọn API | ORDER BY | Seek sau cursor |
| --- | --- | --- |
| NEWEST | created_at DESC, order_id DESC | (created_at, order_id) < (cursorTime, cursorId) |
| OLDEST | created_at ASC, order_id ASC | (created_at, order_id) > (cursorTime, cursorId) |
| AMOUNT_HIGH | total_amount DESC, order_id ASC | total_amount < cursorAmount OR (total_amount = cursorAmount AND order_id > cursorId) |

Mỗi lựa chọn là một **hợp đồng sắp xếp** hoàn chỉnh. Không thể thay ORDER BY mà quên cập nhật điều kiện cursor; sẽ xuất hiện trang thiếu/lặp hoặc thứ tự không đúng.

## 10. JOIN, DISTINCT và dữ liệu tổng hợp

### 10.1. Một hàng đầu ra phải có định danh phù hợp

Giả sử bảng **order_item** chứa nhiều dòng cho mỗi đơn. Truy vấn:

~~~sql
SELECT o.order_id, o.created_at, i.product_id
FROM purchase_order AS o
JOIN order_item AS i
  ON i.tenant_id = o.tenant_id
 AND i.order_id = o.order_id
WHERE o.tenant_id = 10
ORDER BY o.created_at DESC, o.order_id DESC;
~~~

có thể tạo nhiều hàng kết quả cùng **created_at** và **order_id**, vì một đơn có nhiều sản phẩm. Dù khóa chính của đơn là duy nhất, **cặp khóa sắp xếp không còn duy nhất trên tập hàng JOIN**.

Nếu cần danh sách **dòng đơn hàng**, phải thêm định danh của dòng vào thứ tự, chẳng hạn:

~~~sql
ORDER BY o.created_at DESC, o.order_id DESC, i.line_no ASC;
~~~

với giả định **(tenant_id, order_id, line_no)** là khóa duy nhất của order_item. Nếu cần danh sách **đơn hàng** thay vì dòng đơn, hãy tránh JOIN làm nhân hàng, hoặc dùng truy vấn EXISTS/aggregation đúng nghiệp vụ.

### 10.2. DISTINCT không tự xác định hàng đại diện cho một nhóm

~~~sql
SELECT DISTINCT o.customer_id, o.order_id, o.created_at
FROM purchase_order AS o
WHERE o.tenant_id = 10;
~~~

Vì order_id khác nhau, DISTINCT không chọn “một đơn mới nhất của mỗi khách”. Khi nghiệp vụ muốn mỗi khách một đơn mới nhất, hãy xác định thứ tự bên trong từng nhóm:

~~~sql
WITH ranked AS (
    SELECT
        customer_id,
        order_id,
        created_at,
        ROW_NUMBER() OVER (
            PARTITION BY tenant_id, customer_id
            ORDER BY created_at DESC, order_id DESC
        ) AS rn
    FROM purchase_order
    WHERE tenant_id = 10
)
SELECT customer_id, order_id, created_at
FROM ranked
WHERE rn = 1
ORDER BY created_at DESC, order_id DESC;
~~~

Ở đây, **ROW_NUMBER()** chọn đơn mới nhất trong từng nhóm khách hàng, đồng thời **order_id** phá hòa trong nhóm. **ORDER BY ngoài cùng** lại xác định thứ tự các hàng cuối của API. Không nên mặc định ORDER BY nằm bên trong window function tự bảo đảm thứ tự đầu ra của SELECT ngoài.

### 10.3. Kết quả GROUP BY cũng cần khóa phụ khi phân trang

Truy vấn tổng hợp theo khách:

~~~sql
SELECT customer_id, COUNT(*) AS order_count
FROM purchase_order
WHERE tenant_id = 10
GROUP BY customer_id
ORDER BY order_count DESC, customer_id ASC;
~~~

Nhiều khách có thể có cùng **order_count**. Thêm **customer_id ASC** giúp kết quả theo nhóm có thứ tự xác định trong tenant. Khi phân trang **các nhóm**, khóa phụ phải phân biệt **nhóm kết quả**, không đơn hàng chi tiết.

## 11. Chỉ mục hỗ trợ cả lọc, sắp xếp và khóa phụ

Với đường đọc chính:

~~~sql
SELECT order_id, status, created_at
FROM purchase_order
WHERE tenant_id = 10
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

có thể cân nhắc chỉ mục PostgreSQL:

~~~sql
CREATE INDEX idx_po_tenant_created_order
ON purchase_order (tenant_id, created_at DESC, order_id DESC);
~~~

Cách đọc:

- **tenant_id** đứng đầu vì truy vấn lọc bằng một giá trị cụ thể.
- **created_at DESC** phù hợp tiêu chí sắp xếp chính.
- **order_id DESC** phù hợp khóa phụ, tránh cần thêm bước sắp xếp giữa các hàng có cùng created_at trong một số kế hoạch thực thi.

Nếu API thường cần **status**, PostgreSQL hỗ trợ **INCLUDE(status)** cho chỉ mục bao phủ:

~~~sql
CREATE INDEX idx_po_listing_cover
ON purchase_order (tenant_id, created_at DESC, order_id DESC)
INCLUDE (status);
~~~

Khi các cột truy vấn cần đều nằm trong chỉ mục, PostgreSQL **có thể** chọn index-only scan nếu các điều kiện visibility/MVCC cho phép. Không phải lúc nào chỉ mục bao phủ cũng nhanh hơn; nó cũng tăng dung lượng lưu trữ và chi phí cập nhật.

**Không nên tạo cả hai chỉ mục giống nhau về mục đích chỉ vì chúng xuất hiện trong bài.** Hãy chọn thiết kế theo số lượng dữ liệu, các truy vấn phổ biến và kết quả đo. Nếu API còn lọc **status = 'PAID'** trước khi sort, một chỉ mục bắt đầu **(tenant_id, status, created_at DESC, order_id DESC)** cũng đáng cân nhắc, nhưng có thể kém phù hợp cho truy vấn không lọc status.

### 11.1. Khóa phụ không mặc nhiên khiến truy vấn nặng hơn nhiều

Thêm order_id vào ORDER BY có thể làm xuất hiện yêu cầu về chỉ mục/sort, nhưng không thể kết luận luôn chậm hơn hoặc luôn nhanh hơn. Nếu chỉ mục phù hợp và order_id có sẵn trong index, chi phí có thể nhỏ; ngược lại, một thứ tự nhiều biểu thức phức tạp có thể cần sort tốn tài nguyên.

Dùng **EXPLAIN (ANALYZE, BUFFERS)** khi đo trong môi trường phù hợp:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, status, created_at
FROM purchase_order
WHERE tenant_id = 10
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Cần quan sát index scan, sort, số hàng thực đọc, số block và độ trễ. **EXPLAIN ANALYZE** thực sự thực thi truy vấn; hãy chọn môi trường/tải thích hợp và không lấy một lần đo trên bảng vài hàng làm kết luận hiệu năng production.

## 12. Giao dịch và thay đổi đồng thời: giới hạn của thứ tự xác định

### 12.1. Mỗi truy vấn có thể đúng nhưng hai trang vẫn khác trạng thái

Trong PostgreSQL ở mức **READ COMMITTED**, các câu SELECT thực hiện trong những statement khác nhau thường có **snapshot dữ liệu riêng**. Trong HTTP API, hai request phân trang thường còn dùng các giao dịch riêng biệt. Vì vậy, kết quả trang sau có thể phản ánh thêm hoặc bớt đơn hàng.

Khóa phụ chỉ bảo đảm thứ tự của **những hàng mà truy vấn đang nhìn thấy**. Nó không giữ danh sách cố định giữa hai lần đọc.

### 12.2. Keyset giảm ảnh hưởng của hàng chèn ở đầu, nhưng không tạo snapshot

Giả sử trang đầu trả **[105, 104]**, cursor là **(09:30, 104)**. Nếu một đơn mới **106** được chèn lên đầu theo thời gian, truy vấn trang sau dùng điều kiện **(created_at, order_id) < cursor** vẫn đi tiếp tới **103, 102**, không lặp 104 chỉ vì có hàng mới ở phía trước.

Tuy nhiên, các trường hợp sau vẫn cần quyết định nghiệp vụ:

- **INSERT với created_at cũ hơn cursor** có thể xuất hiện ở trang sau dù chưa tồn tại lúc đọc trang đầu.
- **UPDATE created_at** của một bản ghi có thể chuyển nó từ trước cursor ra sau cursor hoặc ngược lại, dẫn tới lặp/bỏ sót trên cả hành trình phân trang.
- **DELETE** một hàng khiến kết quả ngắn lại hoặc thay đổi số trang dự tính.
- **Thay đổi điều kiện lọc** như status NEW → PAID có thể đưa hàng vào/ra tập kết quả giữa hai request.

Nếu use case cần một bộ dữ liệu cố định để kiểm toán hoặc xuất báo cáo, cần một chiến lược nhất quán như **giao dịch có snapshot phù hợp trong suốt công việc**, **xuất dữ liệu ra một bản chụp/staging có định danh**, hoặc **lọc theo một phiên bản/mốc dữ liệu bất biến** đã được thiết kế chính xác. Giữ một transaction database mở qua nhiều lượt cuộn HTTP thường không phải lựa chọn vận hành tốt vì có thể giữ tài nguyên lâu và khó phục hồi.

### 12.3. Cursor cũng không phải thước đo thời gian tuyệt đối

Không mặc định **order_id lớn hơn** nghĩa là đã commit sau, cũng không mặc định **created_at** được database sinh luôn phản ánh đúng thứ tự commit. Sequence/identity có thể có khoảng trống, các transaction có thể commit không theo thứ tự cấp ID, và timestamp có thể trùng nhau.

Trong ví dụ này, **created_at** thể hiện quy tắc hiển thị “mới nhất theo thời điểm đã lưu”, còn **order_id** chỉ là khóa phụ để tạo thứ tự xác định. Nếu nghiệp vụ thực sự cần **thứ tự commit** hoặc thứ tự event toàn cục, cần cơ chế tương ứng thay vì suy diễn từ khóa phụ.

## 13. Bảo mật và tính toàn vẹn của truy vấn phân trang

Một cursor chứa ID của hàng cuối không chứng minh người gọi có quyền xem hàng đó. Trong hệ thống đa tenant, mọi trang phải dùng **tenant_id được xác thực** và những điều kiện phân quyền phù hợp trong SQL.

Ví dụ an toàn về mặt phạm vi:

~~~sql
SELECT order_id, status, created_at
FROM purchase_order
WHERE tenant_id = :authorizedTenant
  AND (created_at, order_id) < (:cursorTime, :cursorId)
ORDER BY created_at DESC, order_id DESC
LIMIT :pageSize;
~~~

Đây là dạng SQL minh họa dùng **tham số đặt tên**; JDBC thuần dùng dấu **?** hoặc framework chuyển đổi tham số đặt tên. Không truyền tenantId từ một trường tự do rồi tin đó là quyền truy cập đã xác thực.

Một số yêu cầu cần bổ sung:

- **Authorization** áp dụng ở mỗi lần đọc; quyền có thể thay đổi giữa các request.
- Nếu cursor là token mang theo tenant, filter, sort, cần kiểm tra nó phù hợp với quyền và tham số hiện tại.
- Không chấp nhận **ORDER BY** dưới dạng chuỗi SQL tự do do client cung cấp; dùng enum/whitelist để chọn cặp sort và seek.
- Không trả toàn bộ cột nhạy cảm chỉ để lấy cursor; lấy đúng những khóa cần thiết và các trường DTO được phép đọc.
- Nếu có tham số **pageSize**, đặt giới hạn tối đa và kiểm tra kiểu/số.
- Cần giới hạn timeout và kiểm soát tài nguyên kết nối đối với đường truy vấn có độ trễ cao.

**PreparedStatement** bảo vệ vị trí giá trị được bind khỏi SQL injection khi dùng đúng; nó không thay cho xác thực, phân quyền, hạn chế dữ liệu hoặc kiểm soát cú pháp động.

## 14. Ma trận kiểm tra thứ tự và phân trang

Khi hoàn thành repository, nên kiểm thử tối thiểu những tình huống sau:

| Tình huống | Thiết lập | Kết quả cần xác minh |
| --- | --- | --- |
| Giá trị sort trùng nhau | 3 đơn có cùng created_at | order_id quyết định thứ tự |
| Giới hạn ngay giữa nhóm hòa | pageSize = 2 trong nhóm có 3 hàng trùng thời gian | Không bỏ sót hàng cùng timestamp ở trang tiếp |
| Không có dữ liệu | Tenant không có đơn | Trả danh sách rỗng, không sinh cursor tiếp |
| Đúng một trang | Số hàng đúng bằng pageSize | Không tạo nextCursor nếu không còn hàng |
| Có thêm một hàng | pageSize+1 hàng | nextCursor lấy từ hàng cuối hiển thị |
| ASC thay DESC | ORDER BY created_at ASC, order_id ASC | Điều kiện seek dùng >, kết quả đúng chiều |
| Chiều hỗn hợp | total_amount DESC, order_id ASC | Seek dùng OR với < cho tiền, > cho ID |
| Có NULL ở trường sort | reviewed_at nullable | Không để so sánh cursor UNKNOWN làm rơi hàng |
| JOIN một–nhiều | Một đơn có nhiều dòng | Khóa phụ phân biệt **hàng đầu ra**, không chỉ hàng cha |
| Sửa giá trị sort giữa các request | UPDATE created_at | Đánh giá hợp đồng nhất quán, không giả định snapshot |
| Thêm hàng ở đầu danh sách | INSERT created_at mới | Keyset tiếp tục sau cursor cũ |
| Nhiều tenant | Trùng order_id ở hai tenant | Filter quyền và khóa phụ phù hợp phạm vi |
| Collation | Tên có dấu/chữ hoa-thường | Kết quả khớp collation, có khóa ID phá hòa |
| Tham số cursor lỗi | Thiếu trường, sai kiểu hoặc sai phiên bản | API từ chối/đặt lại theo hợp đồng |
| Kế hoạch truy vấn | Dữ liệu đủ lớn, chỉ mục phù hợp | Đo EXPLAIN, số hàng và độ trễ thực |

Đối với bài toán thứ tự, nên dùng **dữ liệu cố tình có nhiều giá trị trùng nhau**. Một bộ test mà mọi created_at đều khác nhau không kiểm chứng được việc khóa phụ đang hoạt động đúng.

## 15. Những lỗi thiết kế hay gặp

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| ORDER BY created_at nhưng không có khóa phụ | Các hàng cùng timestamp có thứ tự không được bảo đảm | Thêm định danh duy nhất làm tiêu chí cuối |
| Dùng customer_id để phá hòa trên danh sách đơn | Nhiều đơn cùng khách vẫn hòa nhau | Dùng order_id hoặc khóa duy nhất của hàng |
| Tin LIMIT 1 tự chọn “mới nhất” | Chọn hàng không xác định nếu thiếu sort | ORDER BY thời gian + khóa phụ trước LIMIT |
| Cursor chỉ chứa timestamp | Bỏ sót/đọc lặp hàng trong nhóm cùng timestamp | Cursor lưu đủ mọi giá trị của bộ khóa sắp |
| ORDER BY DESC/ASC hỗn hợp nhưng seek dùng tuple < | Lọc sai những hàng đứng sau | Viết điều kiện OR theo chiều từng khóa |
| Có NULL nhưng dùng tuple seek như cột NOT NULL | Hàng có thể biến mất vì UNKNOWN | Tách logic NULL theo chính sách sắp xếp |
| Thêm khóa chính của hàng cha sau JOIN 1:N | Các dòng con vẫn hòa nhau | Thêm khóa duy nhất của hàng kết quả hoặc tránh JOIN |
| Tin ORDER BY ở subquery đủ sắp xếp ngoài cùng | Đầu ra cuối không được cam kết như mong muốn | ORDER BY ở truy vấn ngoài cùng |
| Cho rằng thứ tự xác định sẽ ổn định qua hai request có UPDATE | Có thể lặp hoặc mất hàng | Thiết kế snapshot/cursor theo nghiệp vụ |
| Dùng cursor của bộ lọc cũ với bộ lọc mới | Trang không đúng phạm vi/thứ tự | Gắn cursor với filter và sort |
| Nối chuỗi ORDER BY từ client | SQL injection hoặc truy vấn ngoài dự kiến | Enum/whitelist sort và seek |
| Không giới hạn pageSize | Tải đọc lớn, cạn tài nguyên | Hạn chế số hàng tối đa |
| Thêm quá nhiều index khi chưa đo | Tăng dung lượng và chi phí ghi | EXPLAIN và đánh giá workload |

## 16. Bài tập tự kiểm tra

### Bài tập 1: ba đơn cùng thời điểm

Ba đơn **105**, **104**, **103** có cùng created_at. Hãy viết ORDER BY để chúng xuất hiện theo thứ tự **103, 104, 105** trong nhóm này, còn những đơn mới hơn đứng trước nhóm.

**Đáp án gợi ý:**

~~~sql
ORDER BY created_at DESC, order_id ASC
~~~

**created_at** vẫn là tiêu chí chính giảm dần, còn **order_id** là khóa phụ tăng dần khi timestamp bằng nhau.

### Bài tập 2: khóa phụ theo tenant

Bảng có PRIMARY KEY **(tenant_id, order_id)**. Truy vấn xuyên tất cả tenant dùng:

~~~sql
ORDER BY created_at DESC, order_id DESC
~~~

Có bảo đảm thứ tự toàn phần không?

**Đáp án:** Chưa chắc, vì hai tenant có thể có cùng **order_id** và **created_at**. Có thể dùng:

~~~sql
ORDER BY created_at DESC, tenant_id ASC, order_id DESC
~~~

để bộ khóa cuối cùng phân biệt mọi hàng.

### Bài tập 3: chọn điều kiện keyset

Một API sắp theo **score DESC, id DESC** và hàng cuối trang trước có **score = 80, id = 50**. Điều kiện trang sau nào đúng khi cả hai cột NOT NULL?

**Đáp án gợi ý:**

~~~sql
WHERE score < 80
   OR (score = 80 AND id < 50)
~~~

Nếu truy vấn còn có tenant và quyền truy cập, các điều kiện đó vẫn phải được kết hợp bằng AND bên ngoài nhóm OR.

### Bài tập 4: hướng hỗn hợp

Với **ORDER BY score DESC, id ASC**, hàng nào đứng sau cursor **(80, 50)**?

**Đáp án:**

~~~sql
WHERE score < 80
   OR (score = 80 AND id > 50)
~~~

Khi score bằng nhau, **ID lớn hơn** đứng sau vì ID ASC.

### Bài tập 5: vì sao OFFSET vẫn lặp?

Một danh sách đã sắp xác định **[104, 103, 102, 101]**. Trang đầu lấy 2 hàng. Trước khi lấy trang hai, bản ghi 105 được thêm lên đầu. Tại sao OFFSET 2 trả [103, 102]?

**Đáp án:** OFFSET bỏ qua hai **vị trí của tập dữ liệu hiện tại**, không tiếp tục theo bản ghi cuối trước đó. Sau INSERT, 103 dịch sang vị trí thứ ba. Keyset dùng khóa của hàng 103 để tìm phần đứng sau sẽ giảm loại lặp này, dù nó cũng không tạo snapshot cố định.

### Bài tập 6: JOIN và định danh hàng đầu ra

Một đơn hàng có ba dòng sản phẩm, mỗi dòng có **line_no** riêng. Truy vấn chọn các dòng nhưng chỉ ORDER BY **o.created_at DESC, o.order_id DESC** có bảo đảm thứ tự ba dòng không?

**Đáp án:** Không. Có thể dùng thêm **i.line_no ASC** khi khóa dòng là duy nhất trong đơn:

~~~sql
ORDER BY o.created_at DESC, o.order_id DESC, i.line_no ASC
~~~

### Bài tập 7: phân biệt mục tiêu nhất quán

Ứng dụng xuất báo cáo tài chính nhiều triệu hàng theo trang. Trong khi xuất, các đơn có thể bị cập nhật. Chỉ thêm khóa phụ vào ORDER BY có đủ để tạo một bản báo cáo đúng tại cùng một thời điểm không?

**Đáp án:** Không. Khóa phụ chỉ xác định thứ tự các hàng mà mỗi truy vấn quan sát. Nếu báo cáo phải đúng với một mốc dữ liệu, cần thiết kế chiến lược **snapshot**, phạm vi giao dịch hoặc phiên bản dữ liệu phục vụ xuất báo cáo.

## 17. Ghi nhớ

**ORDER BY một trường không duy nhất chỉ tạo thứ tự giữa những giá trị khác nhau; các hàng trùng giá trị vẫn có thể đổi vị trí.** Để có thứ tự xác định trên tập kết quả, hãy thêm **khóa phụ thực sự duy nhất trong phạm vi các hàng đầu ra**, thường là khóa chính hoặc phần còn thiếu của khóa ghép. Với nhiều biểu thức sort, các tiêu chí được so sánh theo thứ tự trái sang phải và chiều ASC/DESC của từng tiêu chí phải được giữ nguyên.

Trong phân trang, **LIMIT/OFFSET** đòi hỏi thứ tự xác định nhưng vẫn có thể lặp/bỏ sót hàng khi dữ liệu thay đổi. **Keyset pagination** sử dụng toàn bộ bộ khóa sắp xếp làm cursor và điều kiện seek tương ứng để tiếp tục sau hàng cuối; nó cũng cần xử lý đúng NULL, các chiều sort hỗn hợp và quyền truy cập. Nếu nghiệp vụ cần một tập dữ liệu bất biến trong suốt nhiều lần đọc, phải bổ sung chiến lược nhất quán phù hợp.

Đối với tầng persistence Java, nguyên tắc thực dụng là **sắp xếp rõ, phá hòa bằng khóa duy nhất, bind mọi giá trị, kiểm soát phân trang và đo bằng truy vấn thực tế**.

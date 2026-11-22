# Phân trang theo khóa với điều kiện tiếp nối

## 1. Bài toán: lấy trang kế tiếp trong một danh sách có sắp xếp

Giả sử một ứng dụng hiển thị danh sách bài viết đã xuất bản, mới nhất đứng trước. Người dùng xem ba bài mỗi lần và nhấn **“Xem thêm”** để tải tiếp. Về mặt SQL, truy vấn phải trả lời được hai câu hỏi:

1. **Thứ tự nào xác định vị trí của mỗi hàng?**
2. **Trang tiếp theo bắt đầu ngay sau hàng nào?**

Cách quen thuộc là dùng `LIMIT` kết hợp `OFFSET`:

~~~sql
SELECT article_id, title, published_at
FROM articles
WHERE status = 'PUBLISHED'
  AND category = 'SQL'
ORDER BY published_at DESC, article_id DESC
LIMIT 3 OFFSET 3;
~~~

Câu lệnh trên yêu cầu bỏ qua ba hàng đầu rồi lấy ba hàng kế. Nhưng khi dữ liệu tăng lên hoặc bị chèn/xóa giữa các lần gọi API, `OFFSET` có thể phải duyệt/bỏ qua nhiều hàng và vị trí số của từng hàng dễ thay đổi.

**Phân trang theo khóa (keyset pagination)**, còn gọi là **seek pagination** hoặc **cursor-based pagination** trong một số API, sử dụng **giá trị khóa sắp xếp của hàng cuối trang trước** để tìm hàng tiếp theo:

~~~sql
SELECT article_id, title, published_at
FROM articles
WHERE status = 'PUBLISHED'
  AND category = 'SQL'
  AND (
      published_at < :last_published_at
      OR (
          published_at = :last_published_at
          AND article_id < :last_article_id
      )
  )
ORDER BY published_at DESC, article_id DESC
LIMIT :page_size;
~~~

Ở đây:

- `:last_published_at` và `:last_article_id` là **tham số truy vấn** đại diện cho khóa sắp xếp của hàng cuối đã trả về.
- `WHERE` chứa **điều kiện tiếp nối** (continuation predicate): chọn những hàng nằm *sau* vị trí đã xem theo thứ tự hiển thị.
- `ORDER BY` tiếp tục dùng **đúng bộ khóa và chiều sắp xếp** đã dùng ở trang trước.
- `LIMIT` kiểm soát số hàng cần trả cho lần gọi tiếp theo.

Trong PostgreSQL, MySQL và SQLite, `LIMIT` phổ biến; SQL Server thường dùng `OFFSET ... FETCH` hoặc `TOP`, còn cú pháp chuẩn hiện đại có `FETCH FIRST n ROWS ONLY`. **Nguyên lý điều kiện tiếp nối không đổi**, dù phần giới hạn hàng khác nhau giữa DBMS.

> Điểm quan trọng nhất: phân trang theo khóa dựa trên **vị trí trong thứ tự của dữ liệu**, thay vì một con số đếm những hàng đứng trước.

## 2. Dữ liệu mẫu: những hàng có cùng thời gian xuất bản

Các ví dụ chính dưới đây dùng cú pháp tương thích PostgreSQL. Để dễ so sánh, mọi timestamp trong dữ liệu đều thuộc cùng một cách biểu diễn thời gian; bài này chưa xét chuyển múi giờ.

~~~sql
CREATE TABLE articles (
    article_id   BIGINT PRIMARY KEY,
    title        VARCHAR(100) NOT NULL,
    category     VARCHAR(30) NOT NULL,
    status       VARCHAR(20) NOT NULL,
    published_at TIMESTAMP NOT NULL
);

INSERT INTO articles (
    article_id, title, category, status, published_at
)
VALUES
    (101, 'SQL A',     'SQL',  'PUBLISHED', TIMESTAMP '2026-11-14 09:30:00'),
    (102, 'SQL B',     'SQL',  'PUBLISHED', TIMESTAMP '2026-11-14 09:30:00'),
    (103, 'SQL C',     'SQL',  'PUBLISHED', TIMESTAMP '2026-11-14 09:25:00'),
    (104, 'SQL D',     'SQL',  'PUBLISHED', TIMESTAMP '2026-11-14 09:25:00'),
    (105, 'Java A',    'JAVA', 'PUBLISHED', TIMESTAMP '2026-11-14 09:20:00'),
    (106, 'SQL E',     'SQL',  'PUBLISHED', TIMESTAMP '2026-11-14 09:15:00'),
    (107, 'SQL nhap',  'SQL',  'DRAFT',     TIMESTAMP '2026-11-14 09:10:00'),
    (108, 'SQL F',     'SQL',  'PUBLISHED', TIMESTAMP '2026-11-14 09:05:00'),
    (109, 'SQL G',     'SQL',  'PUBLISHED', TIMESTAMP '2026-11-14 09:00:00'),
    (110, 'SQL H',     'SQL',  'PUBLISHED', TIMESTAMP '2026-11-14 08:55:00');
~~~

Yêu cầu nghiệp vụ:

- Chỉ lấy bài có `status = 'PUBLISHED'` và `category = 'SQL'`.
- Bài mới hơn trước; nếu hai bài cùng `published_at`, bài có `article_id` lớn hơn trước.
- Mỗi trang có **tối đa ba bài**.

Toàn bộ tám hàng phù hợp nếu sắp đúng sẽ là:

| Vị trí | article_id | title | published_at |
| ---: | ---: | --- | --- |
| 1 | 102 | SQL B | 09:30:00 |
| 2 | 101 | SQL A | 09:30:00 |
| 3 | 104 | SQL D | 09:25:00 |
| 4 | 103 | SQL C | 09:25:00 |
| 5 | 106 | SQL E | 09:15:00 |
| 6 | 108 | SQL F | 09:05:00 |
| 7 | 109 | SQL G | 09:00:00 |
| 8 | 110 | SQL H | 08:55:00 |

Tất cả thời gian ở bảng trên đều có ngày `2026-11-14`. Hai bài Java và bản nháp SQL không có trong danh sách vì không thỏa bộ lọc.

Điều đáng chú ý là có **hai cặp trùng thời gian**: ID 102/101 và ID 104/103. Chính điều này cho thấy vì sao **sắp xếp chỉ theo `published_at` là chưa đủ**.

## 3. Điều kiện tiên quyết: phải có thứ tự xác định hoàn toàn

### 3.1. ORDER BY không có khóa phá hòa dễ làm mất hoặc lặp hàng

Nếu chỉ sắp xếp:

~~~sql
ORDER BY published_at DESC
~~~

thì hai hàng cùng thời gian `09:25:00` không có thứ tự tương đối được bảo đảm. DBMS có thể trả ID 104 trước hoặc ID 103 trước tùy kế hoạch thực thi.

Nếu lấy trang đầu và lưu chỉ `last_published_at = '2026-11-14 09:25:00'`, rồi dùng:

~~~sql
WHERE published_at < TIMESTAMP '2026-11-14 09:25:00'
~~~

thì hàng có cùng thời gian `09:25:00` nhưng chưa xuất hiện ở trang trước **bị bỏ sót**.

Nếu thay `<` thành `<=` thì các hàng tại đúng thời điểm đã thấy có thể được trả lại ở trang sau, **gây lặp**.

Cách giải quyết là tạo **thứ tự toàn phần (total order)** bằng cách thêm một khóa duy nhất:

~~~sql
ORDER BY published_at DESC, article_id DESC
~~~

Vì `article_id` là khóa chính, hai hàng không thể cùng có cặp khóa `(published_at, article_id)` giống hệt nhau. Khi hai bài có cùng thời gian, ID quyết định vị trí ổn định.

**Quy tắc thiết kế:** mọi cột ảnh hưởng đến `ORDER BY` cần được phản ánh đúng trong continuation predicate; bộ khóa sắp xếp nên phân biệt được mọi hàng. Nếu khóa nghiệp vụ không duy nhất, thêm một định danh duy nhất làm tiêu chí cuối.

### 3.2. Một khóa duy nhất đôi khi là đủ

Nếu danh sách sắp theo ID tăng dần và ID là duy nhất:

~~~sql
-- Trang đầu:
SELECT article_id, title
FROM articles
ORDER BY article_id ASC
LIMIT 3;

-- Trang sau khi hàng cuối có article_id = 103:
SELECT article_id, title
FROM articles
WHERE article_id > 103
ORDER BY article_id ASC
LIMIT 3;
~~~

Ở đây `article_id` một mình vừa là khóa sắp xếp vừa là khóa tiếp nối. Nhưng không phải mọi sản phẩm có thể dùng ID để biểu thị “mới nhất”: ID không nhất thiết tăng theo thời gian sự kiện; backfill, nhập dữ liệu cũ hoặc ID được sinh phân tán có thể làm thứ tự ID khác với thời gian công bố. Chọn khóa phải theo **thứ tự người dùng yêu cầu**, không theo sự tiện lợi đơn thuần.

## 4. Lần lượt lấy ba trang theo khóa

### 4.1. Trang đầu: chưa có cursor

Truy vấn đầu tiên không có điều kiện tiếp nối, chỉ có bộ lọc và `ORDER BY`:

~~~sql
SELECT article_id, title, published_at
FROM articles
WHERE status = 'PUBLISHED'
  AND category = 'SQL'
ORDER BY published_at DESC, article_id DESC
LIMIT 3;
~~~

Kết quả:

| article_id | title | published_at |
| ---: | --- | --- |
| 102 | SQL B | 2026-11-14 09:30:00 |
| 101 | SQL A | 2026-11-14 09:30:00 |
| 104 | SQL D | 2026-11-14 09:25:00 |

**Hàng cuối trang:** `(published_at, article_id) = ('2026-11-14 09:25:00', 104)`. Đây là vị trí tiếp nối.

Mô hình:

~~~text
Thứ tự DESC của tất cả bài SQL đã xuất bản:

[102] [101] [104]  |  [103] [106] [108]  |  [109] [110]
      Trang 1       ^       Trang 2        ^    Trang 3
                    |                       |
               cursor sau 104         cursor sau 108
~~~

### 4.2. Trang hai: đi sau hàng 104

Sau hàng `(09:25, 104)` theo thứ tự giảm dần là:

1. Hàng có thời gian **nhỏ hơn 09:25**.
2. Hoặc hàng có thời gian **bằng 09:25**, nhưng ID **nhỏ hơn 104**.

Truy vấn:

~~~sql
SELECT article_id, title, published_at
FROM articles
WHERE status = 'PUBLISHED'
  AND category = 'SQL'
  AND (
      published_at < TIMESTAMP '2026-11-14 09:25:00'
      OR (
          published_at = TIMESTAMP '2026-11-14 09:25:00'
          AND article_id < 104
      )
  )
ORDER BY published_at DESC, article_id DESC
LIMIT 3;
~~~

Kết quả:

| article_id | title | published_at |
| ---: | --- | --- |
| 103 | SQL C | 2026-11-14 09:25:00 |
| 106 | SQL E | 2026-11-14 09:15:00 |
| 108 | SQL F | 2026-11-14 09:05:00 |

Hàng `103` có cùng thời gian với hàng cuối trang trước nhưng ID nhỏ hơn, nên vẫn được lấy. Hàng `104` không được trả lại do phép so sánh **nghiêm ngặt**.

**Cursor mới:** `('2026-11-14 09:05:00', 108)`.

### 4.3. Trang ba: tiếp nối sau hàng 108

~~~sql
SELECT article_id, title, published_at
FROM articles
WHERE status = 'PUBLISHED'
  AND category = 'SQL'
  AND (
      published_at < TIMESTAMP '2026-11-14 09:05:00'
      OR (
          published_at = TIMESTAMP '2026-11-14 09:05:00'
          AND article_id < 108
      )
  )
ORDER BY published_at DESC, article_id DESC
LIMIT 3;
~~~

Kết quả:

| article_id | title | published_at |
| ---: | --- | --- |
| 109 | SQL G | 2026-11-14 09:00:00 |
| 110 | SQL H | 2026-11-14 08:55:00 |

Trang này chỉ còn hai hàng, nên trong dữ liệu hiện tại đã hết danh sách.

### 4.4. Cú pháp so sánh tuple khi cả hai chiều giống nhau

PostgreSQL hỗ trợ so sánh theo hàng (row-value comparison), giúp viết gọn:

~~~sql
SELECT article_id, title, published_at
FROM articles
WHERE status = 'PUBLISHED'
  AND category = 'SQL'
  AND (published_at, article_id)
      < (TIMESTAMP '2026-11-14 09:25:00', 104)
ORDER BY published_at DESC, article_id DESC
LIMIT 3;
~~~

Với hai cột **đều sắp DESC**, toán tử `<` trên cặp khóa hoạt động như điều kiện `OR` ở trên: so sánh trường đầu tiên trước, khi bằng nhau thì so sánh trường thứ hai.

Cách này gọn nhưng cần chú ý khả năng hỗ trợ **so sánh tuple** và tối ưu hóa của từng DBMS/driver; không thể suy ra cú pháp tương tự luôn hợp lệ hoặc có cùng kế hoạch trong mọi hệ SQL. Mẫu điều kiện `OR` được mở rộng thường dễ chuyển hệ và dễ kiểm tra rõ từng chiều.

## 5. Vì sao đây được gọi là “điều kiện tiếp nối”?

Một cursor không nhất thiết là “con trỏ server” hoặc đối tượng cursor SQL có trạng thái trên database. Trong các API phân trang, cursor thường là **token do client nhận được và gửi lại**, chứa hoặc đại diện cho khóa sắp xếp đã thấy.

Ví dụ mô hình API:

~~~text
GET /articles?category=SQL&status=PUBLISHED&limit=3
          |
          v
   Trả ba bài: 102, 101, 104
   nextCursor = khóa của bài 104
          |
          v
GET /articles?category=SQL&status=PUBLISHED&limit=3&after=<cursor>
          |
          v
   Trả ba bài: 103, 106, 108
   nextCursor = khóa của bài 108
~~~

Bên trong cursor có thể mang:

~~~json
{
  "v": 1,
  "sort": "published_at_desc_article_id_desc",
  "publishedAt": "2026-11-14T09:25:00",
  "articleId": 104,
  "category": "SQL",
  "status": "PUBLISHED"
}
~~~

Đây là **nội dung logic để minh họa**, không phải yêu cầu phải công khai JSON nguyên bản. Một API có thể mã hóa token thành Base64URL và ký kiểm tra toàn vẹn, hoặc lưu trạng thái riêng ở server và cung cấp một mã định danh.

Cursor nên gắn với **bộ lọc và thứ tự sắp xếp** của truy vấn. Nếu người dùng đổi `category` từ `SQL` thành `JAVA` hoặc đổi cách sắp xếp trong khi vẫn tái sử dụng khóa của cursor cũ, kết quả có thể bị bỏ sót hoặc không có ý nghĩa. Cách rõ ràng là **bắt đầu lại từ trang đầu** hoặc từ chối cursor không khớp tham số.

### Phân biệt ba khái niệm

| Khái niệm | Ý nghĩa |
| --- | --- |
| `OFFSET` | Bỏ qua *N hàng* trước khi lấy kết quả |
| **Keyset/seek condition** | Chọn hàng có khóa sắp xếp nằm **sau một khóa đã biết** |
| **Cursor trong API** | Token chứa/tham chiếu đến thông tin để tiếp tục phân trang; có thể dùng keyset, nhưng từ “cursor” không tự bảo đảm implementation dùng keyset |

Một API tự gọi token của nó là cursor nhưng bên trong vẫn lưu `offset=100000` không tự động có tính chất hiệu năng của keyset.

## 6. Xây dựng điều kiện theo chiều sắp xếp

### 6.1. Một cột tăng dần

~~~sql
ORDER BY article_id ASC
~~~

Đi tiếp sau ID `104`:

~~~sql
WHERE article_id > 104
ORDER BY article_id ASC
~~~

Vì sắp **tăng dần**, “sau” nghĩa là giá trị **lớn hơn**.

### 6.2. Một cột giảm dần

~~~sql
ORDER BY article_id DESC
~~~

Đi tiếp sau ID `104`:

~~~sql
WHERE article_id < 104
ORDER BY article_id DESC
~~~

Vì sắp **giảm dần**, “sau” nghĩa là giá trị **nhỏ hơn**.

### 6.3. Hai cột cùng giảm dần

~~~sql
ORDER BY published_at DESC, article_id DESC
~~~

Đi sau `(:ts, :id)`:

~~~sql
WHERE published_at < :ts
   OR (published_at = :ts AND article_id < :id)
~~~

Mẫu tương đương theo row comparison, nơi được hỗ trợ:

~~~sql
WHERE (published_at, article_id) < (:ts, :id)
~~~

### 6.4. Hai cột cùng tăng dần

~~~sql
ORDER BY published_at ASC, article_id ASC
~~~

Đi sau `(:ts, :id)`:

~~~sql
WHERE published_at > :ts
   OR (published_at = :ts AND article_id > :id)
~~~

Mẫu so sánh tuple:

~~~sql
WHERE (published_at, article_id) > (:ts, :id)
~~~

### 6.5. Hai cột có chiều ngược nhau

Giả sử muốn **bài mới trước**, nhưng với cùng thời gian thì **ID nhỏ trước**:

~~~sql
ORDER BY published_at DESC, article_id ASC
~~~

Đi sau hàng `(:ts, :id)` phải viết:

~~~sql
WHERE published_at < :ts
   OR (published_at = :ts AND article_id > :id)
~~~

Chú ý: tại cột `article_id`, toán tử đổi thành `>` vì cột này sắp **ASC**.

**Không** áp dụng trực tiếp `(published_at, article_id) < (:ts, :id)` trong ví dụ mixed-direction trên: phép so sánh tuple dùng hướng so sánh theo giá trị của từng thành phần, không biết cột thứ hai trong `ORDER BY` đang ASC. Với nhiều khóa có chiều khác nhau, có thể tiếp tục mở rộng điều kiện từ trái sang phải:

~~~text
Sau khóa (k1, k2, k3) theo ORDER BY k1 DESC, k2 ASC, k3 DESC:

k1 < :v1
OR (k1 = :v1 AND k2 > :v2)
OR (k1 = :v1 AND k2 = :v2 AND k3 < :v3)
~~~

Cách viết này giả định các khóa **không NULL** và phép so sánh dùng cùng quy tắc thứ tự với `ORDER BY`. Nếu cần xử lý `NULL`, collation hoặc thứ tự đặc biệt, phải mở rộng quy tắc một cách chủ đích.

### 6.6. Dấu so sánh phải nghiêm ngặt

Điều kiện tiếp nối thường dùng `<` hoặc `>`, không dùng `<=` hay `>=` ở ranh giới hiện tại. Nếu dùng phép có bằng, hàng cuối của trang trước có thể xuất hiện lại ở trang sau.

Phần **bằng nhau** chỉ nằm ở các thành phần khóa đứng trước trong biểu thức ghép, ví dụ `published_at = :ts AND article_id < :id`. Mục đích là tiếp tục **trong nhóm có cùng thời gian**, chứ không lấy lại hàng có toàn bộ khóa giống cursor.

## 7. Trang trước, trang sau và đảo thứ tự

Phân trang về phía trước tương đối đơn giản: dùng **hàng cuối** trang hiện tại làm cursor “after”. Muốn đi về **trang trước**, có thể dùng **hàng đầu** trang hiện tại và đảo điều kiện, đồng thời đảo thứ tự để lấy các hàng gần ranh giới nhất.

Giả sử trang hiện tại là trang hai, gồm `103, 106, 108`. Hàng đầu là ID `103` tại `09:25`. Muốn lấy ba hàng **đứng trước** ID 103 trong thứ tự giảm dần:

~~~sql
SELECT article_id, title, published_at
FROM articles
WHERE status = 'PUBLISHED'
  AND category = 'SQL'
  AND (
      published_at > TIMESTAMP '2026-11-14 09:25:00'
      OR (
          published_at = TIMESTAMP '2026-11-14 09:25:00'
          AND article_id > 103
      )
  )
ORDER BY published_at ASC, article_id ASC
LIMIT 3;
~~~

Truy vấn chọn các hàng gần cursor nhất nhưng trả theo thứ tự đảo: `104, 101, 102`. Ứng dụng **đảo mảng** kết quả để hiển thị theo chiều chuẩn: `102, 101, 104`.

Với PostgreSQL, biểu thức rút gọn:

~~~sql
WHERE (published_at, article_id)
    > (TIMESTAMP '2026-11-14 09:25:00', 103)
ORDER BY published_at ASC, article_id ASC
LIMIT 3;
~~~

**Không chỉ đổi dấu điều kiện rồi giữ `ORDER BY published_at DESC`:** như vậy có thể lấy những hàng xa nhất ở đầu danh sách thay vì đúng trang liền trước.

Một API phân trang hai chiều có thể trả:

- `nextCursor` dựa trên **hàng cuối** theo chiều hiển thị.
- `previousCursor` dựa trên **hàng đầu** theo chiều hiển thị.
- Một token riêng cho hướng `before/after` hoặc một cờ direction được ký, để tránh dùng nhầm cursor.

Nếu người dùng cần nhảy thẳng đến “trang 27”, keyset không tự cung cấp cách đi tới vị trí đó mà không có một khóa bắt đầu tương ứng. Nó phù hợp nhất cho “tiếp tục”, “xem thêm”, infinite scroll hoặc luồng liên tục, còn số trang và tổng số trang cần một thiết kế khác.

## 8. Lấy thêm một hàng để biết có trang tiếp theo

Một cách phổ biến để báo `hasNextPage` là yêu cầu **`pageSize + 1` hàng**, sau đó chỉ trả tối đa `pageSize` hàng cho client.

Ví dụ trang đầu có `pageSize = 3`:

~~~sql
SELECT article_id, title, published_at
FROM articles
WHERE status = 'PUBLISHED'
  AND category = 'SQL'
ORDER BY published_at DESC, article_id DESC
LIMIT 4;
~~~

DBMS trả `102, 101, 104, 103`. API xử lý:

1. Nhận bốn hàng.
2. Chỉ gửi ba hàng đầu `102, 101, 104`.
3. Thấy còn hàng thứ tư nên đặt `hasNextPage = true`.
4. Tạo `nextCursor` từ **hàng cuối được gửi** là ID `104`, không phải hàng thứ tư ID `103`.

Nếu lấy 4 hàng nhưng dùng hàng 4 để sinh cursor, bài `103` sẽ bị bỏ qua ở lần gọi sau.

Ở trang ba, lấy `pageSize + 1 = 4` nhưng chỉ còn hai hàng `109, 110`, nên `hasNextPage = false` với dữ liệu hiện tại.

Một vài API có thể đơn giản hóa bằng cách trả `nextCursor = null` khi không có thêm hàng. Khi dữ liệu biến đổi đồng thời, đó là kết luận **tại thời điểm truy vấn**, không bảo đảm về sau không có bản ghi mới đủ điều kiện.

`COUNT(*)` có thể cung cấp số hàng tổng, nhưng đôi khi là truy vấn tốn chi phí và có thể không cùng thời điểm nhất quán với truy vấn trang. Với infinite scroll, thường không cần tính tổng số trang.

## 9. So sánh OFFSET và keyset trên dữ liệu biến động

### 9.1. Khi có hàng mới chèn vào đầu danh sách

Ban đầu trang 1 theo `LIMIT 3` là:

~~~text
102, 101, 104
~~~

Sau khi người dùng nhận trang đầu, hệ thống xuất bản bài mới:

~~~sql
INSERT INTO articles (
    article_id, title, category, status, published_at
)
VALUES (
    111, 'SQL Moi', 'SQL', 'PUBLISHED',
    TIMESTAMP '2026-11-14 09:45:00'
);
~~~

Toàn bộ thứ tự mới bắt đầu `111, 102, 101, 104, 103, 106, 108, ...`.

Nếu dùng `OFFSET 3` để lấy trang hai:

~~~sql
SELECT article_id, title
FROM articles
WHERE status = 'PUBLISHED'
  AND category = 'SQL'
ORDER BY published_at DESC, article_id DESC
LIMIT 3 OFFSET 3;
~~~

kết quả là `104, 103, 106`. **ID 104 bị lặp**: người dùng đã thấy nó ở cuối trang một.

Nếu dùng keyset dựa trên ID 104 / thời gian 09:25:

~~~sql
SELECT article_id, title
FROM articles
WHERE status = 'PUBLISHED'
  AND category = 'SQL'
  AND (published_at, article_id)
      < (TIMESTAMP '2026-11-14 09:25:00', 104)
ORDER BY published_at DESC, article_id DESC
LIMIT 3;
~~~

thì trang hai vẫn là `103, 106, 108`. Bài mới ID 111 ở **trước** ranh giới cursor nên không làm các bài đã đọc bị dồn vị trí. Người dùng sẽ cần làm mới từ đầu nếu muốn thấy ID 111.

Điều này minh họa ưu điểm của keyset khi có hàng **được chèn ở phía trước cursor**. Nó không tự động tạo một ảnh chụp dữ liệu bất biến cho mọi trang.

### 9.2. Khi có xóa và cập nhật

Với `OFFSET`, xóa một hàng nằm trước trang hiện tại có thể làm số vị trí dịch lên và khiến người dùng bỏ sót hàng kế.

Với keyset, vì điều kiện dựa trên **giá trị khóa**, việc xóa một hàng trước ranh giới thường không làm dịch điểm tiếp nối. Nhưng nếu hàng chưa xem bị xóa, đương nhiên nó không còn xuất hiện trong lần đọc sau.

Phức tạp hơn là **cập nhật cột tham gia sắp xếp**:

- Nếu một bài đã xem được đổi `published_at` sang thời gian cũ hơn, nó có thể xuất hiện lại **sau cursor**, gây lặp.
- Nếu một bài chưa xem được đổi sang thời gian mới hơn cursor, nó có thể chuyển lên **trước cursor** và bị bỏ qua trong luồng tiếp nối.
- Nếu `status` hoặc `category` đổi, một hàng có thể xuất hiện hoặc biến mất khỏi tập được lọc giữa hai request.

Vì vậy, keyset **giảm vấn đề dịch vị trí của OFFSET**, nhưng không tự bảo đảm exactly-once hoặc một tập dữ liệu snapshot cố định qua nhiều request.

### 9.3. Cần snapshot ổn định thì giải quyết riêng

Nếu nghiệp vụ bắt buộc duyệt **đúng cùng một tập hàng tại một thời điểm**, ví dụ xuất báo cáo để đối soát, cần thiết kế cách giữ ảnh chụp logic của tập dữ liệu:

- Một transaction có snapshot nhất quán đủ lâu, nếu hạ tầng và DBMS cho phép và chi phí chấp nhận được.
- Materialize danh sách khóa hoặc kết quả vào bảng/job snapshot tạm có định danh phiên.
- Đặt mốc giới hạn dữ liệu (watermark, ví dụ `published_at <= :cutoff`) **khi khóa sắp xếp phù hợp và không đổi**, kết hợp với quy tắc xử lý backfill/late arrivals; chỉ có cutoff không ngăn các hàng ghi muộn nhưng mang thời gian cũ xuất hiện.
- Dùng phiên bản dữ liệu hoặc watermark ghi nhận từ nguồn theo mô hình nghiệp vụ.

Trong API HTTP thường không nên giữ transaction database mở dài qua nhiều lần cuộn trang. Một cursor chứa khóa và cutoff có thể giúp tính nhất quán theo mục tiêu nhất định, nhưng phải nêu rõ **những loại thay đổi nào được phép và không được bảo vệ**.

## 10. Chỉ mục và hiệu năng

### 10.1. Vì sao keyset thường tốt hơn ở trang sâu?

`OFFSET 100000` yêu cầu DBMS tìm các hàng theo thứ tự rồi bỏ qua một lượng lớn kết quả trước khi lấy trang. Tùy kế hoạch, DBMS có thể phải đọc và sắp xếp khá nhiều hàng dù chỉ trả vài bản ghi.

Keyset cung cấp **điều kiện có thể tìm theo khóa sắp xếp**. Với chỉ mục thích hợp, DBMS có thể nhảy tới vùng dữ liệu sau cursor rồi đọc khoảng `LIMIT` hàng, thay vì đếm/bỏ qua phần trước.

Nhưng **keyset không cam kết thời gian O(1)**: chi phí còn tùy chọn chỉ mục, bộ lọc, phân phối dữ liệu, độ chọn lọc và kế hoạch thực thi. Một điều kiện tiếp nối có nhiều nhánh `OR` hoặc biểu thức đặc biệt có thể khiến bộ tối ưu chọn cách khác với kỳ vọng.

### 10.2. Chỉ mục khớp bộ lọc và thứ tự

Với bài toán:

~~~sql
WHERE status = 'PUBLISHED'
  AND category = 'SQL'
  AND (published_at, article_id) < (:ts, :id)
ORDER BY published_at DESC, article_id DESC
LIMIT 3
~~~

trong PostgreSQL có thể cân nhắc:

~~~sql
CREATE INDEX idx_articles_feed
ON articles (
    status,
    category,
    published_at DESC,
    article_id DESC
);
~~~

Ý nghĩa:

- Hai cột đầu `status` và `category` dùng làm điều kiện bằng.
- Hai cột tiếp theo đi theo `ORDER BY` của feed và điều kiện tiếp nối.
- Index có thể giúp hạn chế số hàng phải kiểm tra và tránh sắp xếp lại toàn bộ trong một số kế hoạch.

Một chỉ mục khác phù hợp cho hệ thống mà truy vấn feed luôn chỉ lấy bài SQL đã xuất bản là **partial index** (đặc thù PostgreSQL):

~~~sql
CREATE INDEX idx_articles_sql_published
ON articles (published_at DESC, article_id DESC)
WHERE status = 'PUBLISHED'
  AND category = 'SQL';
~~~

Chỉ mục lọc sẵn có thể nhỏ hơn, nhưng không hữu ích cho các bộ lọc khác. Với dữ liệu thật, cần cân nhắc chi phí ghi, kích thước index và các truy vấn đang chạy. Không nên tạo nhiều chỉ mục chỉ vì vài biến thể thử nghiệm mà chưa đo đạc.

### 10.3. Xem kế hoạch và đo

Dùng `EXPLAIN` trong PostgreSQL để quan sát kế hoạch dự kiến:

~~~sql
EXPLAIN
SELECT article_id, title, published_at
FROM articles
WHERE status = 'PUBLISHED'
  AND category = 'SQL'
  AND (published_at, article_id)
      < (TIMESTAMP '2026-11-14 09:25:00', 104)
ORDER BY published_at DESC, article_id DESC
LIMIT 3;
~~~

Dữ liệu mẫu chỉ vài hàng nên PostgreSQL có thể chọn sequential scan và sort thay vì index scan; điều đó không có nghĩa index vô dụng ở tập dữ liệu lớn.

`EXPLAIN (ANALYZE, BUFFERS)` có thể cho số đo thực tế, nhưng `ANALYZE` **thực thi câu lệnh**; với `SELECT` là đọc thật, còn với câu ghi cần quản lý tác động. Khi so sánh `OFFSET` và keyset, hãy dùng tập dữ liệu đại diện, bộ lọc thực, vị trí trang khác nhau và thống kê được cập nhật.

## 11. NULL, collation và kiểu khóa sắp xếp

### 11.1. Cột khóa cho keyset nên được xác định, không NULL

Ví dụ dùng:

~~~sql
published_at TIMESTAMP NOT NULL,
article_id BIGINT PRIMARY KEY
~~~

Nhờ vậy các phép `<`, `>` và `=` trên khóa hoạt động theo logic so sánh thông thường. Nếu `published_at` có thể `NULL`:

~~~sql
WHERE published_at < :ts
~~~

không chọn được các hàng `NULL`, vì kết quả so sánh là `UNKNOWN`. Trong khi `ORDER BY` vẫn có thể đặt các hàng `NULL` vào một vị trí nhất định, theo quy tắc `NULLS FIRST/LAST` hoặc mặc định DBMS.

Nếu cần hỗ trợ `NULL` trong khóa, phải xác định **thứ tự NULL** tường minh và xây continuation predicate phù hợp. Có thể chuẩn hóa khóa sắp xếp thành biểu thức có giá trị được định nghĩa rõ, ví dụ nhóm `NULL` sau những giá trị có dữ liệu, nhưng điều kiện và chỉ mục phải **dùng cùng biểu thức**. Tránh tùy tiện `COALESCE(timestamp, một ngày giả)` nếu giá trị giả có thể trùng dữ liệu thực hoặc làm sai ý nghĩa.

### 11.2. Collation và văn bản

Nếu sắp theo tên:

~~~sql
ORDER BY title ASC, article_id ASC
~~~

thứ tự các ký tự có dấu, chữ hoa/thường và các biến thể Unicode có thể phụ thuộc **collation** của DBMS. Cursor tạo dưới một collation nhưng so sánh dưới collation khác có thể tiếp nối không đúng.

Khi xây dựng API có sắp xếp theo văn bản, cần giữ nhất quán collation và quy tắc chuẩn hóa, hoặc chọn một khóa chuẩn hóa được tính/được lưu rõ ràng. Thêm `article_id` làm khóa phá hòa để các tiêu đề được coi là bằng nhau theo collation vẫn có thứ tự xác định.

### 11.3. Timestamp và độ chính xác

Ứng dụng có thể biểu diễn `published_at` với mili giây trong khi DB lưu microseconds hoặc độ chính xác khác. Nếu token làm tròn `published_at`, điều kiện tiếp nối có thể chuyển sang ranh giới khác và làm thiếu/lặp hàng.

Khi tạo cursor, phải **giữ nguyên độ chính xác và ngữ nghĩa thời gian của khóa so sánh**; nếu dùng instant có múi giờ, chọn định dạng chuẩn chứa đủ thông tin/offset và round-trip được về đúng kiểu DB. Không dùng chuỗi hiển thị người dùng như `"14/11/2026 09:25"` làm khóa tiếp nối nếu nó làm mất giây hoặc phần lẻ giây.

## 12. Thiết kế API phân trang dùng cursor

Một API có thể nhận:

~~~text
GET /articles?category=SQL&status=PUBLISHED&limit=3
GET /articles?category=SQL&status=PUBLISHED&limit=3&after=eyJ2IjoxLC4uLn0
~~~

và trả về:

~~~json
{
  "items": [
    {
      "articleId": 102,
      "title": "SQL B",
      "publishedAt": "2026-11-14T09:30:00"
    },
    {
      "articleId": 101,
      "title": "SQL A",
      "publishedAt": "2026-11-14T09:30:00"
    },
    {
      "articleId": 104,
      "title": "SQL D",
      "publishedAt": "2026-11-14T09:25:00"
    }
  ],
  "pageInfo": {
    "hasNextPage": true,
    "nextCursor": "<opaque-token-for-last-item-104>"
  }
}
~~~

`<opaque-token-for-last-item-104>` ở đây là placeholder mô tả, không phải một token hợp lệ sẵn dùng.

Các thành phần nên được thiết kế rõ:

- **Bộ lọc:** phân trang phải tiếp tục trong đúng phạm vi `status`, `category`, `tenant_id` và mọi điều kiện nghiệp vụ.
- **Thứ tự:** cursor gắn với cùng `ORDER BY`; nếu API cho phép nhiều sort modes, ghi mã của sort mode vào token.
- **Khóa:** lưu đủ toàn bộ các thành phần khóa sắp xếp và độ chính xác, không chỉ ID khi thứ tự chính là timestamp.
- **Phiên bản token:** thêm `v` để có thể thay định dạng token mà vẫn xử lý hoặc từ chối token cũ một cách có chủ đích.
- **Giới hạn page size:** xác thực `limit` dương, có mức tối đa, tránh client yêu cầu số hàng quá lớn.
- **Kiểm tra token:** Base64URL chỉ là mã hóa có thể giải được, **không chống sửa đổi**. Nếu token chứa quyền truy cập hoặc điều kiện bảo mật, cần kiểm tra chữ ký/HMAC, quyền hiện tại và filter/tenant từ server; không tin các trường do client sửa.
- **Định nghĩa lỗi:** cursor không hợp lệ, hết hạn, dùng sai filter hoặc phiên bản không còn được hỗ trợ cần có phản hồi rõ ràng. Thay đổi bộ lọc thường nên bắt đầu lại từ trang đầu.
- **Vị trí ranh giới:** `nextCursor` tạo từ **hàng cuối trong `items` trả về**, kể cả khi truy vấn đã lấy dư một hàng để tính `hasNextPage`.

Token nên là **opaque** đối với client để server có thể đổi cách mã hóa/triển khai, nhưng điều đó không thay thế việc tài liệu hóa ngữ nghĩa: cursor có hiệu lực trong bao lâu, dữ liệu mới xuất hiện như thế nào và có cho phép phân trang ngược không.

## 13. Ví dụ với truy vấn tham số hóa trong Java/JDBC

Với một API thực tế, tránh ghép trực tiếp `last_published_at` hay `article_id` từ đầu vào thành chuỗi SQL. Dùng prepared statement:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.Timestamp;
import java.time.LocalDateTime;

// cursor chứa khóa chính xác của hàng cuối trang trước.
LocalDateTime lastPublishedAt = cursor.publishedAt();
long lastArticleId = cursor.articleId();

int pageSize = 3;
// Ở tầng API cần giới hạn pageSize hợp lệ và tối đa.
int fetchSize = pageSize + 1;

String sql = """
    SELECT article_id, title, published_at
    FROM articles
    WHERE status = ?
      AND category = ?
      AND (
          published_at < ?
          OR (published_at = ? AND article_id < ?)
      )
    ORDER BY published_at DESC, article_id DESC
    LIMIT ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, "PUBLISHED");
    ps.setString(2, "SQL");
    ps.setTimestamp(3, Timestamp.valueOf(lastPublishedAt));
    ps.setTimestamp(4, Timestamp.valueOf(lastPublishedAt));
    ps.setLong(5, lastArticleId);
    ps.setInt(6, fetchSize);

    try (ResultSet rs = ps.executeQuery()) {
        // Đọc tối đa fetchSize hàng, chuyển sang DTO theo thứ tự SQL trả.
        // hasNextPage = rows.size() > pageSize.
        // items = tối đa pageSize hàng đầu.
        // nextCursor = khóa của items.get(items.size() - 1), khi còn trang.
    }
}
~~~

Ví dụ sử dụng `LocalDateTime` vì cột minh họa là `TIMESTAMP` **không có múi giờ**. Nếu hệ thống lưu instant như PostgreSQL `TIMESTAMPTZ`, phải chọn kiểu thời gian/driver phù hợp để giữ thông tin instant, không tự chuyển qua múi giờ máy chủ mà làm thay đổi cursor.

Ứng dụng vẫn cần xử lý trang đầu **không có cursor** bằng truy vấn tương ứng không có điều kiện tiếp nối, và xử lý kết quả rỗng. Không nên triển khai điều kiện tiếp nối kiểu:

~~~sql
WHERE (:cursor_is_null OR published_at < :ts OR ...)
~~~

một cách máy móc nếu nó khiến ràng buộc kiểu tham số phức tạp hoặc kế hoạch truy vấn khó tối ưu; thường có thể dùng hai SQL tường minh: một cho trang đầu, một cho trang sau.

## 14. Khi nào nên chọn keyset và khi nào vẫn cần OFFSET?

| Nhu cầu | Keyset/seek | OFFSET |
| --- | --- | --- |
| Infinite scroll / “Xem thêm” | Phù hợp: tiếp nối theo hàng cuối | Dễ dùng lúc đầu, nhưng có thể dịch trang |
| Feed có nhiều insert ở đầu | Thường giảm duplicate do dịch vị trí | Dễ lặp/bỏ sót khi dữ liệu đổi |
| Trang rất sâu | Có thể khai thác index và điểm bắt đầu | Thường tốn công bỏ qua nhiều hàng |
| Nhảy trực tiếp đến trang số 50 | Không tự hỗ trợ nếu không biết khóa ranh giới | Hỗ trợ tự nhiên bằng vị trí số |
| Hiển thị tổng số trang | Cần truy vấn/thiết kế thêm | Cũng cần đếm tổng số hàng |
| Sắp theo nhiều khóa | Cần continuation predicate đúng cho toàn bộ khóa | Chỉ cần ORDER BY nhất quán để xem trang tại một thời điểm |
| Dữ liệu thường xuyên đổi khóa sort | Có thể lặp/bỏ sót nếu khóa đổi | Cũng dễ bị dịch trang |
| Kết quả snapshot bất biến | Cần cơ chế snapshot riêng | Cũng cần cơ chế snapshot riêng |

**Keyset thường được ưu tiên** cho danh sách dài, yêu cầu tiếp nối tuần tự và có khóa sắp xếp phù hợp với chỉ mục. `OFFSET` vẫn hợp lý cho bảng nhỏ, công cụ quản trị cần nhảy trang số, dữ liệu ít đổi hoặc những màn hình mà chi phí OFFSET đã được đo là chấp nhận được.

Không nên thay `OFFSET` chỉ vì một quy tắc hình thức. Cần xác định đúng yêu cầu người dùng, mô hình dữ liệu, tính bất biến của khóa, bộ lọc và cách backend vận hành.

## 15. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách tránh |
| --- | --- | --- |
| Chỉ dùng `ORDER BY published_at` khi có thời gian trùng | Không có vị trí duy nhất, dễ bỏ sót/lặp | Thêm `article_id` duy nhất vào sort và cursor |
| Dùng `published_at < :ts` nhưng bỏ `article_id` | Bỏ sót các bài cùng timestamp còn lại | Dùng so sánh từ trái sang phải với tất cả khóa |
| Dùng `<=`/`>=` ở ranh giới cuối | Hàng cuối trang cũ có thể bị trả lại | Dùng điều kiện nghiêm ngặt |
| Dùng tuple `<` cho sort hỗn hợp DESC/ASC | Sai điều kiện tiếp nối | Mở rộng `OR` theo từng chiều |
| Đổi `WHERE category` giữa các trang | Cursor trỏ vào bộ dữ liệu khác | Bắt đầu lại/từ chối token sai filter |
| Lấy dư một hàng và lưu cursor của hàng dư | Bỏ sót hàng không trả về | Cursor của hàng cuối **thực sự gửi** |
| Coi Base64 là bằng chứng token nguyên vẹn | Client có thể thay dữ liệu token | Ký và xác thực token khi cần |
| Làm tròn timestamp trong cursor | Sai ranh giới, có thể lặp/bỏ sót | Giữ nguyên độ chính xác khóa |
| Không xác định quy tắc `NULL` | Điều kiện `<`/`>` không theo thứ tự hiển thị | Dùng khóa `NOT NULL` hoặc xử lý NULL rõ ràng |
| Giữ `ORDER BY DESC` khi truy vấn “trang trước” | Lấy các hàng xa nhất thay vì gần cursor | Đảo điều kiện và thứ tự rồi đảo kết quả |
| Khẳng định keyset tạo snapshot bất biến | Dữ liệu cập nhật/late insert vẫn thay đổi danh sách | Thiết kế snapshot/watermark riêng nếu cần |
| Không có index phù hợp | Hiệu năng không đạt kỳ vọng | Thiết kế index theo filter + sort, xem `EXPLAIN` |

## 16. Bài tập thực hành

Sử dụng dữ liệu ban đầu ở mục 2, **chưa chèn bài 111**, trừ khi bài tập nói khác.

### Bài 1 — Viết câu SQL cho trang thứ hai

Trang đầu trả `102, 101, 104`. Hãy viết truy vấn lấy tối đa ba bài tiếp theo, với điều kiện chỉ lấy bài SQL đã xuất bản.

**Đáp án:**

~~~sql
SELECT article_id, title, published_at
FROM articles
WHERE status = 'PUBLISHED'
  AND category = 'SQL'
  AND (
      published_at < TIMESTAMP '2026-11-14 09:25:00'
      OR (
          published_at = TIMESTAMP '2026-11-14 09:25:00'
          AND article_id < 104
      )
  )
ORDER BY published_at DESC, article_id DESC
LIMIT 3;
~~~

Kết quả: `103, 106, 108`.

### Bài 2 — Vì sao phải có ID làm khóa phụ?

Nếu trang đầu trả hết ở ID 104 tại `09:25:00`, tại sao `WHERE published_at < '2026-11-14 09:25:00'` chưa đúng?

**Đáp án:** vì ID 103 cũng xuất bản lúc `09:25:00` nhưng đứng sau ID 104 theo `article_id DESC`. Điều kiện chỉ kiểm tra `published_at` sẽ loại luôn ID 103. Cần nhánh thời gian bằng và ID nhỏ hơn để tiếp tục trong nhóm có thời gian trùng.

### Bài 3 — Đổi chiều sort của ID

Yêu cầu `ORDER BY published_at DESC, article_id ASC`. Hãy viết điều kiện lấy những hàng sau cursor `(:ts, :id)`.

**Đáp án:**

~~~sql
WHERE published_at < :ts
   OR (published_at = :ts AND article_id > :id)
~~~

Cột thời gian DESC nên đi tiếp bằng `<`, còn cột ID ASC nên đi tiếp bằng `>`.

### Bài 4 — Lấy trang trước

Trang hiện tại gồm `103, 106, 108`. Viết điều kiện và `ORDER BY` để lấy đúng ba hàng đứng trước nó, rồi nói rõ thứ tự cần hiển thị.

**Đáp án:** dùng cursor của **hàng đầu 103**, điều kiện `(published_at, article_id) > ('2026-11-14 09:25:00', 103)` với `ORDER BY published_at ASC, article_id ASC LIMIT 3`. SQL trả `104, 101, 102`, sau đó đảo mảng thành `102, 101, 104` để hiển thị theo thứ tự chuẩn.

### Bài 5 — Tìm lỗi khi xác định nextCursor

API đặt `pageSize = 3` và truy vấn `LIMIT 4`, nhận `102, 101, 104, 103`. API chỉ trả ba hàng đầu nhưng ghi cursor từ ID 103. Điều gì xảy ra?

**Đáp án:** lần tới sẽ lấy các hàng sau ID 103, làm mất ID 103 khỏi danh sách client dù nó chưa được hiển thị. Cursor phải được tạo từ ID **104**, là hàng cuối đã trả về.

### Bài 6 — Biến động dữ liệu

Sau khi người dùng đã xem `102, 101, 104`, hệ thống chèn bài mới ID 111 tại `09:45`. Hãy dự đoán trang hai của:

- `LIMIT 3 OFFSET 3`.
- Keyset sau cursor `(09:25, 104)`.

**Đáp án:** OFFSET trả `104, 103, 106` và lặp 104. Keyset trả `103, 106, 108`. Bài mới ID 111 không nằm ở những hàng sau cursor; người dùng phải làm mới từ đầu để thấy nó.

### Bài 7 — Thiết kế index

Cho truy vấn:

~~~sql
SELECT article_id, title, published_at
FROM articles
WHERE status = 'PUBLISHED'
  AND category = 'SQL'
  AND (published_at, article_id) < (:ts, :id)
ORDER BY published_at DESC, article_id DESC
LIMIT 10;
~~~

Hãy đề xuất một composite index cho PostgreSQL và giải thích thứ tự cột.

**Gợi ý đáp án:**

~~~sql
CREATE INDEX idx_articles_feed
ON articles (
    status,
    category,
    published_at DESC,
    article_id DESC
);
~~~

`status` và `category` phục vụ điều kiện bằng; `published_at` và `article_id` phục vụ bộ khóa seek và thứ tự giảm dần. Độ hữu ích thực tế cần xác nhận bằng execution plan trên dữ liệu đủ lớn.

### Bài 8 — Nêu giới hạn nhất quán

Đúng hay sai: “Dùng keyset với cursor bảo đảm người dùng luôn xem đúng một lần toàn bộ bài tồn tại ở thời điểm tải trang đầu, dù có cập nhật `published_at` trong lúc phân trang.”

**Đáp án:** **sai**. Keyset tránh một số lỗi dịch vị trí khi insert/delete trước cursor, nhưng nếu giá trị khóa sắp xếp đổi, bài đã xem có thể chuyển xuống sau cursor và xuất hiện lại hoặc bài chưa xem chuyển lên trước cursor rồi bị bỏ qua. Muốn snapshot cố định cần cơ chế bổ sung và quy tắc xử lý dữ liệu thay đổi.

## 17. Ghi nhớ

**Phân trang theo khóa** sử dụng **khóa sắp xếp của hàng cuối đã trả về** và điều kiện `WHERE` để lấy những hàng đứng sau khóa đó. Phương pháp hiệu quả và rõ nghĩa nhất khi:

1. Truy vấn có **thứ tự xác định hoàn toàn**, thường là khóa nghiệp vụ cộng một ID duy nhất.
2. **Điều kiện tiếp nối khớp tất cả thành phần và chiều sắp xếp** của `ORDER BY`.
3. Bộ lọc, collation, độ chính xác kiểu dữ liệu và quyền truy cập được giữ nhất quán giữa các trang.
4. Cursor được tạo từ **hàng cuối đã gửi** và chỉ dùng trong đúng ngữ cảnh.
5. Index được thiết kế phù hợp, còn yêu cầu snapshot và dữ liệu cập nhật được xử lý riêng.

Khi triển khai nút “Xem thêm”, hãy bắt đầu bằng câu hỏi: **“Hàng tiếp theo nằm sau khóa nào theo đúng thứ tự đang hiển thị?”**. Từ câu trả lời đó, xây `WHERE` bằng các phép so sánh nghiêm ngặt, rồi kiểm chứng các trường hợp trùng khóa, dữ liệu mới và trang cuối.

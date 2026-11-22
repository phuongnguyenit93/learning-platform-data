# Bổ sung khóa phân xử để kết quả có thứ tự xác định

Trong SQL, nhiều truy vấn có thể trả về **đúng tập dòng** nhưng **không bảo đảm thứ tự các dòng**. Kể cả khi đã dùng `ORDER BY`, nếu nhiều dòng có cùng giá trị ở tất cả các cột sắp xếp, hệ quản trị vẫn có quyền trả các dòng đồng hạng theo thứ tự bất kỳ. Điều này đặc biệt quan trọng khi hiển thị danh sách theo trang, chọn “bản ghi mới nhất”, xếp hạng hoặc xuất dữ liệu cho hệ thống khác.

Giải pháp thường là thêm một **khóa phân xử** (*tie-breaker*) vào cuối danh sách `ORDER BY`: một cột hoặc tổ hợp cột giúp phân biệt những dòng vốn đang bằng nhau theo tiêu chí nghiệp vụ. Khi các cột sắp xếp tạo ra **thứ tự toàn phần** đối với các dòng kết quả, việc chọn trang hoặc chọn một dòng trong nhóm trở nên có thể dự đoán hơn.

Bài học thuộc chủ đề **Sắp xếp và phân trang** trong Database SQL, sử dụng dữ liệu đơn hàng làm ví dụ xuyên suốt. Các truy vấn chủ yếu dùng PostgreSQL; cú pháp cơ bản `ORDER BY` và tư duy về khóa phân xử áp dụng rộng rãi cho các hệ quản trị quan hệ.

## 1. `ORDER BY` quyết định điều gì?

Một truy vấn `SELECT` không có `ORDER BY` ở **lớp truy vấn ngoài cùng** không hứa thứ tự hiển thị:

```sql
SELECT order_id, placed_at
FROM orders;
```

Dù hôm nay kết quả tình cờ được in theo `order_id`, ngày mai hệ quản trị có thể chọn một đường truy cập hoặc kế hoạch thực thi khác. Thứ tự chèn dữ liệu, khóa chính hay thứ tự vật lý của bảng **không thay thế** điều kiện `ORDER BY`.

Thêm điều kiện sắp xếp:

```sql
SELECT order_id, placed_at
FROM orders
ORDER BY placed_at DESC;
```

Ta đã yêu cầu các thời điểm mới đứng trước các thời điểm cũ. Nhưng nếu hai đơn hàng có **cùng `placed_at`**, điều kiện này vẫn chưa cho biết **đơn nào đứng trước trong cặp đồng hạng**.

Hãy phân biệt ba khái niệm:

| Khái niệm | Ý nghĩa | Câu hỏi |
|---|---|---|
| **Tập dòng kết quả** | Những dòng nào thỏa `FROM`, `JOIN`, `WHERE`, `GROUP BY`... | “Những đơn nào được trả về?” |
| **Thứ tự theo tiêu chí nghiệp vụ** | Ưu tiên thời gian, điểm số, doanh thu... | “Những đơn mới hơn đứng trước?” |
| **Khóa phân xử** | Cách chọn thứ tự giữa các dòng có cùng tiêu chí nghiệp vụ | “Nếu cùng giờ thì đơn nào đứng trước?” |

`ORDER BY` có thể chứa nhiều biểu thức:

```sql
ORDER BY placed_at DESC, order_id DESC
```

Cơ sở dữ liệu so sánh `placed_at` trước; **chỉ khi bằng nhau** mới dùng `order_id`. Vì vậy, khóa phân xử không làm thay đổi quy tắc “đơn mới trước đơn cũ”; nó chỉ làm rõ thứ tự **bên trong mỗi nhóm cùng thời gian**.

## 2. Dữ liệu mẫu: nhiều bản ghi có cùng khóa sắp xếp

Giả sử bảng `orders` có khóa chính `order_id` và các dòng sau:

| order_id | customer_id | placed_at | total_amount | status |
|---:|---:|---|---:|---|
| 101 | 1 | 2026-07-03 09:00:00 | 250000 | PAID |
| 102 | 2 | 2026-07-03 09:00:00 | 200000 | PAID |
| 103 | 1 | 2026-07-03 09:00:00 | 300000 | PAID |
| 104 | 3 | 2026-07-03 10:30:00 | 150000 | PAID |
| 105 | 2 | 2026-07-02 14:00:00 | 120000 | PAID |
| 106 | 4 | 2026-07-02 14:00:00 | 80000 | CANCELLED |
| 107 | 4 | 2026-07-01 12:00:00 | 200000 | PAID |
| 108 | 5 | 2026-07-01 12:00:00 | 180000 | PAID |
| 109 | 5 | 2026-06-30 08:00:00 | 90000 | PAID |
| 110 | 3 | 2026-07-03 10:30:00 | 160000 | PENDING |

Ta có các nhóm đồng hạng theo `placed_at`:

- 10:30 ngày 3/7: `104`, `110`.
- 09:00 ngày 3/7: `101`, `102`, `103`.
- 14:00 ngày 2/7: `105`, `106`.
- 12:00 ngày 1/7: `107`, `108`.
- 08:00 ngày 30/6: chỉ có `109`.

Nếu chạy:

```sql
SELECT order_id, placed_at
FROM orders
ORDER BY placed_at DESC;
```

thì các **nhóm thời gian** có thứ tự, nhưng thứ tự bên trong mỗi nhóm **chưa xác định**. Ví dụ `101`, `102`, `103` có thể xuất hiện theo nhiều hoán vị vì chúng cùng có `placed_at = '2026-07-03 09:00:00'`.

Trong một lần thực thi cụ thể, PostgreSQL vẫn phải in ra theo một thứ tự nào đó. Nhưng **thứ tự tình cờ quan sát được không phải cam kết SQL**. Khi dữ liệu lớn hơn, thay đổi chỉ mục, cập nhật thống kê, đổi kế hoạch hoặc chạy song song, ta có thể thấy thứ tự các dòng đồng hạng thay đổi.

## 3. Khóa phân xử là gì?

**Khóa phân xử** là biểu thức sắp xếp bổ sung để giải quyết các trường hợp bằng nhau ở những tiêu chí trước nó. Ví dụ:

```sql
SELECT order_id, placed_at
FROM orders
ORDER BY placed_at DESC, order_id DESC;
```

Ở đây:

1. `placed_at DESC`: đơn mới hơn đứng trước.
2. `order_id DESC`: nếu hai đơn cùng thời điểm, đơn có mã lớn hơn đứng trước.

Với dữ liệu mẫu, thứ tự mã đơn được xác định là:

```text
110, 104, 103, 102, 101, 106, 105, 108, 107, 109
```

Hình dung kết quả:

```text
placed_at DESC             order_id DESC trong nhóm bằng nhau
2026-07-03 10:30:00   ──>  110, 104
2026-07-03 09:00:00   ──>  103, 102, 101
2026-07-02 14:00:00   ──>  106, 105
2026-07-01 12:00:00   ──>  108, 107
2026-06-30 08:00:00   ──>  109
```

Vì `order_id` là **khóa chính** của bảng mẫu, không có hai đơn có cùng `order_id`. Do đó cặp `(placed_at, order_id)` cũng không thể trùng giữa hai đơn khác nhau. Danh sách `ORDER BY` tạo một **thứ tự toàn phần trên tập dòng đơn hàng** nếu mỗi dòng kết quả đúng là một đơn.

### 3.1. Chọn khóa phân xử theo quy tắc nghiệp vụ

Không có yêu cầu bắt buộc phải dùng `order_id DESC`. Cả hai truy vấn sau đều xác định được thứ tự:

```sql
-- Cùng thời điểm, mã lớn đứng trước.
ORDER BY placed_at DESC, order_id DESC

-- Cùng thời điểm, mã nhỏ đứng trước.
ORDER BY placed_at DESC, order_id ASC
```

Điều cần xác định là **quy tắc nào phù hợp với sản phẩm hoặc báo cáo**. Với dữ liệu sự kiện, hệ thống có thể chọn `(created_at DESC, event_id DESC)`; với bảng xếp hạng, có thể chọn `(score DESC, participant_id ASC)` nếu yêu cầu “bằng điểm thì mã người tham gia nhỏ hơn đứng trước”.

Không nên tự suy diễn rằng mã lớn hơn luôn có nghĩa sự kiện xảy ra muộn hơn. ID tăng dần không nhất thiết phản ánh thứ tự nghiệp vụ khi có nhập dữ liệu lại, giao dịch đồng thời, UUID hoặc sự kiện đến không đúng thứ tự. ID ở đây dùng để **phân xử đồng hạng**, còn tiêu chí chính vẫn là thời điểm.

### 3.2. Một khóa chính đơn lẻ là đủ khi nó phân biệt mọi dòng đầu ra

Nếu `order_id` là `PRIMARY KEY` của **mỗi dòng đơn**, thì:

```sql
ORDER BY total_amount DESC, placed_at DESC, order_id ASC
```

cũng xác định thứ tự toàn phần: so tiền trước, sau đó thời điểm, rồi dùng mã đơn phân xử nếu hai thuộc tính trước đều bằng nhau.

Nhưng:

```sql
ORDER BY placed_at DESC, customer_id ASC
```

**chưa chắc đủ**, vì một khách hàng có thể đặt nhiều đơn cùng lúc. `customer_id` không duy nhất trên bảng đơn, nên cặp `(placed_at, customer_id)` vẫn có thể trùng. Khóa phân xử phải giúp phân biệt **các dòng kết quả thực sự**, không chỉ “trông có vẻ giống một ID”.

### 3.3. Một khóa phân xử có thể là tổ hợp nhiều cột

Không phải bảng nào cũng có một cột ID duy nhất. Ví dụ `order_items` có khóa chính tổng hợp `(order_id, line_no)`:

```sql
SELECT order_id, line_no, quantity
FROM order_items
ORDER BY quantity DESC, order_id ASC, line_no ASC;
```

Ở đây `(order_id, line_no)` là tổ hợp duy nhất; nếu số lượng bằng nhau, hai cột khóa giúp xác định thứ tự.

Một tiêu chí bổ sung **chưa đủ duy nhất** thì vẫn cần tiếp tục thêm cột. Hãy hỏi: “Có thể tồn tại hai dòng khác nhau mà mọi biểu thức `ORDER BY` đều bằng nhau không?” Nếu có, thứ tự vẫn còn đồng hạng.

## 4. Thứ tự xác định và tính ổn định: cần phân biệt

Một bộ khóa sắp xếp phân biệt tất cả các dòng mang lại **thứ tự xác định đối với một trạng thái dữ liệu và quy tắc so sánh nhất định**. Nó không có nghĩa danh sách sẽ **không bao giờ thay đổi**.

Giả sử lúc 09:00 ta thấy:

```text
110, 104, 103, 102, 101, ...
```

Sau đó hệ thống ghi thêm một đơn mới có `placed_at` lớn hơn, đơn mới sẽ đứng đầu nếu truy vấn chạy lại. Câu SQL vẫn đúng và thứ tự vẫn xác định; **tập dữ liệu đã đổi** nên vị trí của các đơn cũ thay đổi.

Vì thế:

- **Deterministic order**: với cùng tập dòng, cùng giá trị khóa sắp xếp và cùng quy tắc so sánh, cách sắp xếp xác định một vị trí cho mỗi dòng.
- **Stable view/snapshot**: các lần đọc nhìn cùng một trạng thái dữ liệu; điều này phụ thuộc giao dịch, mức cách ly hoặc chiến lược phiên bản dữ liệu.
- **Pagination consistency**: người dùng chuyển trang không bị lặp/bỏ sót dòng do sự thay đổi dữ liệu giữa các lần gọi; cần thiết kế phân trang phù hợp ngoài việc thêm khóa phân xử.

Thêm `order_id` vào `ORDER BY` giải quyết **đồng hạng trong kết quả**, chứ không tự đóng băng dữ liệu khi người khác đang thêm, sửa hoặc xóa.

## 5. Vì sao thiếu khóa phân xử gây lỗi khi phân trang?

Giả sử giao diện hiển thị **3 đơn mỗi trang**, thứ tự “mới nhất trước”. Hai câu SQL:

```sql
-- Trang 1, PostgreSQL/MySQL:
SELECT order_id, placed_at
FROM orders
ORDER BY placed_at DESC
LIMIT 3 OFFSET 0;
```

```sql
-- Trang 2:
SELECT order_id, placed_at
FROM orders
ORDER BY placed_at DESC
LIMIT 3 OFFSET 3;
```

Khi chỉ sắp theo `placed_at`, nhóm `101`, `102`, `103` đồng hạng đúng tại vùng **ranh giới trang**. Cơ sở dữ liệu có thể xử lý hai câu `LIMIT/OFFSET` theo kế hoạch khác nhau, dẫn tới thứ tự khác nhau của những dòng đồng hạng. Vì vậy, một ID có thể xuất hiện ở hai trang và một ID khác bị bỏ qua, **ngay cả khi không có cập nhật dữ liệu**, vì SQL chưa quy định thứ tự giữa chúng.

### 5.1. Bổ sung khóa phân xử cho mọi truy vấn trang

```sql
-- Trang 1.
SELECT order_id, placed_at
FROM orders
ORDER BY placed_at DESC, order_id DESC
LIMIT 3 OFFSET 0;
```

Kết quả:

| Vị trí | order_id |
|---:|---:|
| 1 | 110 |
| 2 | 104 |
| 3 | 103 |

Trang 2:

```sql
SELECT order_id, placed_at
FROM orders
ORDER BY placed_at DESC, order_id DESC
LIMIT 3 OFFSET 3;
```

| Vị trí | order_id |
|---:|---:|
| 4 | 102 |
| 5 | 101 |
| 6 | 106 |

Trang 3 sẽ là `105`, `108`, `107`; trang 4 là `109`. Nếu **tập dữ liệu không đổi giữa các lần đọc**, không có hai dòng nào đổi chỗ do đồng hạng, vì hai biểu thức sắp xếp đã phân biệt mọi đơn.

### 5.2. Cú pháp giới hạn dòng tùy hệ quản trị

`LIMIT ... OFFSET ...` thông dụng trong PostgreSQL, MySQL và SQLite. SQL chuẩn có dạng `OFFSET ... ROWS FETCH NEXT ... ROWS ONLY`; SQL Server thường dùng `ORDER BY ... OFFSET ... ROWS FETCH NEXT ... ROWS ONLY`. Trong bài học này, nguyên lý không phụ thuộc cách viết giới hạn số dòng:

```sql
-- Ví dụ theo cú pháp chuẩn (nhiều hệ hỗ trợ):
SELECT order_id, placed_at
FROM orders
ORDER BY placed_at DESC, order_id DESC
OFFSET 3 ROWS FETCH NEXT 3 ROWS ONLY;
```

Điều cốt lõi là `ORDER BY` phải nêu đầy đủ tiêu chí **trước khi chọn một phần kết quả**.

### 5.3. `OFFSET` vẫn chịu ảnh hưởng khi dữ liệu thay đổi

Giả sử người dùng tải trang 1 ở thời điểm A. Trước khi tải trang 2, một đơn mới được thêm vào đầu danh sách. Mặc dù `ORDER BY placed_at DESC, order_id DESC` hoàn toàn xác định, `OFFSET 3` trên tập dữ liệu mới sẽ bỏ qua **ba dòng đầu mới**. Một dòng từng ở trang 1 có thể bị đẩy xuống trang 2 và xuất hiện lại; hoặc khi có xóa ở đầu danh sách, người dùng có thể bỏ qua một dòng.

Khóa phân xử xử lý **thứ tự của các dòng đang có**. Để phân trang khi dữ liệu liên tục thay đổi, có thể dùng **phân trang theo con trỏ/khóa** (*keyset/cursor pagination*) hoặc cách cố định phiên bản dữ liệu khi nghiệp vụ yêu cầu.

## 6. Phân trang theo khóa: dùng toàn bộ bộ khóa sắp xếp

Trong phân trang theo khóa, ta ghi nhớ **bộ giá trị sắp xếp của dòng cuối trang trước**, rồi yêu cầu trang sau chỉ chứa các dòng **đứng sau bộ giá trị đó**. Phương pháp này tránh phụ thuộc vào số lượng dòng nằm ở trước con trỏ.

Với thứ tự:

```sql
ORDER BY placed_at DESC, order_id DESC
```

trang đầu:

```sql
SELECT order_id, placed_at
FROM orders
ORDER BY placed_at DESC, order_id DESC
LIMIT 3;
```

Kết quả `110`, `104`, `103`. Dòng cuối là `103` với `placed_at = '2026-07-03 09:00:00'`.

Trang kế tiếp phải nhận cả **thời điểm** và **mã đơn**:

```sql
SELECT order_id, placed_at
FROM orders
WHERE placed_at < TIMESTAMP '2026-07-03 09:00:00'
   OR (
       placed_at = TIMESTAMP '2026-07-03 09:00:00'
       AND order_id < 103
   )
ORDER BY placed_at DESC, order_id DESC
LIMIT 3;
```

Kết quả là `102`, `101`, `106`. Nếu điều kiện chỉ là `placed_at < '2026-07-03 09:00:00'`, cả hai đơn `102` và `101` sẽ bị bỏ qua vì chúng cùng thời điểm với dòng cuối trang trước. Khóa phân xử vì thế **vừa tạo thứ tự xác định, vừa cần có mặt trong con trỏ**.

### 6.1. Giải thích điều kiện “đứng sau con trỏ”

Với `DESC, DESC`, một dòng nằm sau dòng cuối trang trước khi:

1. `placed_at` **nhỏ hơn** thời điểm cuối trang trước; hoặc
2. `placed_at` **bằng** thời điểm đó, nhưng `order_id` **nhỏ hơn** mã cuối trang trước.

```text
Trang 1                      Điểm cuối trang 1
110, 104, 103                (2026-07-03 09:00, 103)
           │
           ▼
Trang sau chỉ xét những khóa đứng sau:
102, 101, 106, 105, 108, 107, 109
```

Trong PostgreSQL, với các kiểu không `NULL` và thứ tự cả hai cột đều `DESC`, có thể viết ngắn gọn bằng phép so sánh hàng:

```sql
SELECT order_id, placed_at
FROM orders
WHERE (placed_at, order_id)
      < (TIMESTAMP '2026-07-03 09:00:00', 103)
ORDER BY placed_at DESC, order_id DESC
LIMIT 3;
```

Biểu thức hàng `(placed_at, order_id)` được so sánh theo thứ tự từ trái sang phải. Đây là cách ngắn, nhưng việc hỗ trợ và tối ưu phép so sánh hàng có thể khác giữa hệ quản trị. Cách dùng `OR` tường minh thường dễ áp dụng khi cần hiểu cơ chế hoặc viết SQL cho nhiều nền tảng.

### 6.2. Nếu hai chiều sắp xếp khác nhau thì điều kiện phải đổi

Giả sử bảng kết quả cuộc thi được sắp:

```sql
ORDER BY score DESC, participant_id ASC
```

Điểm cao đứng trước; nếu cùng điểm thì mã nhỏ đứng trước. Sau con trỏ `(last_score, last_participant_id)`, điều kiện phải là:

```sql
-- Placeholder minh họa trong ứng dụng, không phải literal SQL chuẩn:
WHERE score < :last_score
   OR (
       score = :last_score
       AND participant_id > :last_participant_id
   )
ORDER BY score DESC, participant_id ASC
```

Dấu so sánh của khóa phân xử đổi thành `>` vì `participant_id` đang sắp **tăng dần**. Không nên dùng máy móc toán tử `<` cho mọi thành phần chỉ vì cột chính là `DESC`.

### 6.3. Con trỏ thực tế nên chứa gì?

Trong ứng dụng thực, con trỏ cần đủ thông tin để tái dựng điều kiện sắp xếp:

- Giá trị của **mọi biểu thức `ORDER BY` cần thiết** để phân xử, ví dụ `placed_at` và `order_id`.
- Quy tắc sắp xếp đang dùng: `ASC`/`DESC`, quy tắc `NULL`, múi giờ/kiểu dữ liệu và filter nếu liên quan.
- Khi cần, một mã phiên bản dữ liệu hoặc điều kiện giới hạn snapshot để bảo đảm phạm vi đọc.

Con trỏ có thể được mã hóa thành một chuỗi do server tạo. Mã hóa không tự làm nó an toàn trước việc sửa tùy ý; API cần xác thực giá trị con trỏ, giới hạn hợp lệ và buộc con trỏ gắn với bộ lọc/sắp xếp tương ứng.

### 6.4. Keyset không tự giải quyết mọi thay đổi đồng thời

Keyset thường hạn chế lỗi dịch trang khi **thêm/xóa các dòng trước con trỏ**, nhưng có giới hạn:

- Nếu `placed_at` hoặc một khóa dùng để sắp xếp bị **cập nhật**, một dòng có thể chuyển từ phía sau con trỏ sang phía trước hoặc ngược lại, làm trải nghiệm đọc nhiều trang không còn nhất quán.
- Dòng mới có khóa **đứng trước con trỏ** thường không xuất hiện trong những trang tiếp theo của phiên duyệt đang diễn ra.
- Nếu cần đọc **chính xác một snapshot** dữ liệu xuyên nhiều yêu cầu, còn phải có chiến lược dữ liệu bất biến, phiên bản/snapshot phù hợp hoặc giao dịch và mức cách ly được thiết kế rõ.

Nói cách khác, bộ khóa phân xử **cần thiết** để phân trang đúng theo thứ tự, nhưng tính nhất quán khi cập nhật đồng thời là vấn đề bổ sung.

## 7. `NULL`: khóa sắp xếp có thể không có giá trị

Trong dữ liệu thực tế, một số cột như `published_at` hoặc `last_seen_at` có thể chứa `NULL`. Hai dòng có cùng giá trị `NULL` ở tiêu chí chính cũng cần khóa phân xử nếu muốn phân biệt thứ tự.

Ví dụ trong PostgreSQL:

```sql
SELECT article_id, published_at
FROM articles
ORDER BY published_at DESC NULLS LAST, article_id DESC;
```

Ở đây:

1. Những bài có thời điểm xuất bản được sắp mới đến cũ.
2. Các bài chưa xuất bản (`published_at IS NULL`) nằm **sau cùng**.
3. Trong một nhóm cùng thời điểm hoặc cùng `NULL`, `article_id DESC` phân xử vị trí.

`NULLS FIRST` và `NULLS LAST` có mặt trong PostgreSQL và một số hệ khác, nhưng không được hỗ trợ cùng cú pháp ở mọi nền tảng. Nếu môi trường không hỗ trợ, có thể biểu diễn vị trí `NULL` bằng một biểu thức `CASE`:

```sql
SELECT article_id, published_at
FROM articles
ORDER BY
    CASE WHEN published_at IS NULL THEN 1 ELSE 0 END ASC,
    published_at DESC,
    article_id DESC;
```

Ví dụ trên dùng `article_id` giả định là khóa duy nhất và không `NULL`. Nếu muốn phân trang keyset qua ranh giới giữa nhóm ngày giờ và nhóm `NULL`, điều kiện “sau con trỏ” phải **xử lý `NULL` riêng**; không thể chỉ lấy mẫu `(published_at, article_id) < (...)` vì phép so sánh thông thường với `NULL` trả về `UNKNOWN`.

Do đó, khi thiết kế keyset, bộ khóa sắp xếp không `NULL` thường giúp điều kiện đơn giản hơn. Với cột tùy chọn, hãy xác định quy tắc `NULL` và kiểm thử ranh giới giữa hai nhóm.

## 8. Thứ tự trên nhiều cột: tính duy nhất mới là điều quyết định

Số lượng cột trong `ORDER BY` không quyết định thứ tự đã xác định hay chưa. Ví dụ:

```sql
ORDER BY status ASC, total_amount DESC, placed_at DESC
```

có tới ba tiêu chí nhưng vẫn có thể có hai đơn cùng `status`, cùng `total_amount`, cùng `placed_at`. Khi cần một dòng trên mỗi đơn, thêm khóa duy nhất:

```sql
ORDER BY status ASC, total_amount DESC, placed_at DESC, order_id ASC
```

Khóa phân xử thường được đặt **cuối cùng** để không thay đổi ưu tiên của các tiêu chí nghiệp vụ. Một cách kiểm tra logic:

> Với hai dòng kết quả bất kỳ khác nhau, có ít nhất một biểu thức `ORDER BY` có thể phân biệt chúng hay không?

Nếu câu trả lời là “không”, vẫn còn đồng hạng. Nếu khóa cuối là khóa chính duy nhất cho mỗi dòng kết quả, câu trả lời thường là “có”.

### 8.1. Không nên mặc định cột thời gian có đủ độ phân giải

Hai sự kiện có thể có cùng `created_at` do:

- Ứng dụng gán một timestamp cho cả lô dữ liệu.
- Cột lưu giây trong khi nhiều giao dịch xảy ra cùng giây.
- Database làm tròn/giới hạn độ chính xác timestamp.
- Dữ liệu được nhập lại với thời gian gốc giống nhau.

Ngay cả timestamp có microsecond hoặc nanosecond cũng không phải **khóa duy nhất mặc định**. Khóa phân xử có tính duy nhất được khai báo và bảo vệ bởi ràng buộc schema là lựa chọn chắc chắn hơn.

### 8.2. Khóa phân xử khác với khóa phân nhóm

Một khóa có thể tốt để phân nhóm nhưng không đủ để phân biệt dòng. Ví dụ `customer_id` nhóm các đơn theo khách; nhưng một khách có nhiều đơn. `ORDER BY customer_id, placed_at` vẫn có thể đồng hạng với các đơn cùng khách và cùng thời điểm. Cần thêm `order_id` nếu đầu ra là **một dòng mỗi đơn**.

Ngược lại, sau khi `GROUP BY customer_id`, một dòng đầu ra đã đại diện cho **một khách hàng**, nên `customer_id` lúc này có thể đủ để phân biệt các nhóm. Điều quan trọng là xác định **độ hạt của kết quả** trước khi chọn khóa phân xử.

## 9. Khi truy vấn có `JOIN`, khóa duy nhất của một bảng có thể chưa đủ

Giả sử một đơn có nhiều dòng sản phẩm trong `order_items`. Kết quả:

```sql
SELECT o.order_id, i.item_id, i.quantity
FROM orders AS o
JOIN order_items AS i ON i.order_id = o.order_id
ORDER BY o.placed_at DESC, o.order_id DESC;
```

Sau phép `JOIN` một-nhiều, **mỗi đơn có thể xuất hiện nhiều dòng**. Hai dòng sản phẩm của cùng một đơn có cùng `o.placed_at` và `o.order_id`, nên thứ tự giữa chúng chưa được xác định. Nếu `item_id` là khóa duy nhất cho mỗi dòng sản phẩm, có thể bổ sung:

```sql
SELECT o.order_id, i.item_id, i.quantity
FROM orders AS o
JOIN order_items AS i ON i.order_id = o.order_id
ORDER BY o.placed_at DESC, o.order_id DESC, i.item_id ASC;
```

Đây là ví dụ cho một nguyên tắc tổng quát: **khóa phân xử phải duy nhất ở độ hạt cuối cùng của truy vấn**. Sau `JOIN`, một khóa từng là duy nhất ở bảng cha có thể được lặp lại trên nhiều dòng kết quả.

### 9.1. Muốn phân trang đơn hàng, đừng vô tình phân trang dòng sản phẩm

Nếu yêu cầu là “mỗi trang ba **đơn hàng**”, nên xác định ba đơn trong một truy vấn con hoặc CTE trước rồi mới lấy dòng sản phẩm:

```sql
WITH page_orders AS (
    SELECT order_id, placed_at
    FROM orders
    ORDER BY placed_at DESC, order_id DESC
    LIMIT 3
)
SELECT
    p.order_id,
    p.placed_at,
    i.item_id,
    i.quantity
FROM page_orders AS p
LEFT JOIN order_items AS i ON i.order_id = p.order_id
ORDER BY p.placed_at DESC, p.order_id DESC, i.item_id ASC;
```

Truy vấn trên có thể trả **hơn ba dòng** nếu mỗi đơn có nhiều sản phẩm; đó là kết quả đúng nếu yêu cầu là **ba đơn**, kèm toàn bộ dòng sản phẩm của chúng. Lệnh `ORDER BY` ở ngoài cùng vẫn cần có để thứ tự trình bày của kết quả sau `JOIN` được quy định.

Ví dụ này giả định `order_items(item_id, order_id, quantity)` tồn tại, trong đó `item_id` xác định một dòng sản phẩm. Tùy thiết kế thực tế, khóa dòng sản phẩm có thể là tổ hợp `(order_id, line_no)` thay vì `item_id`.

## 10. Khi `GROUP BY` hoặc `DISTINCT` làm thay đổi độ hạt

### 10.1. Xếp nhóm theo giá trị tổng hợp

Yêu cầu: “Sắp danh sách khách hàng theo thời gian đơn mới nhất, người có đơn mới nhất đứng trước. Nếu cùng thời điểm, mã khách nhỏ đứng trước.”

```sql
SELECT
    customer_id,
    MAX(placed_at) AS latest_order_at,
    COUNT(*) AS order_count
FROM orders
GROUP BY customer_id
ORDER BY latest_order_at DESC, customer_id ASC;
```

Vì mỗi nhóm trả về **một dòng trên mỗi `customer_id`**, `customer_id` ở đây có thể dùng làm khóa phân xử duy nhất. Không nên thêm `order_id` trực tiếp vào `ORDER BY` vì một nhóm có thể chứa nhiều `order_id`; khi dùng tổng hợp, ta phải xác định biểu thức nào có nghĩa **trên mỗi nhóm**.

### 10.2. `DISTINCT` và khóa phân xử

```sql
SELECT DISTINCT status
FROM orders
ORDER BY status ASC;
```

Mỗi dòng đầu ra là **một trạng thái khác nhau**, nên chỉ có một cột `status` là đủ để phân biệt các dòng ở kết quả này. Nếu yêu cầu là “mỗi khách hàng đúng một dòng”, hãy xác định muốn dòng nào đại diện cho khách: dòng mới nhất, có tiền lớn nhất hay tổng hợp theo khách. Không nên thêm `DISTINCT` để che việc `JOIN` sinh dòng lặp mà chưa xác định độ hạt.

Một số hệ quản trị đặt ràng buộc đối với biểu thức `ORDER BY` trong truy vấn có `DISTINCT`. Giải pháp là xác định rõ cột kết quả và khóa duy nhất ở **độ hạt đã loại trùng**, không mặc định đem khóa của bảng gốc ghép vào mọi câu `DISTINCT`.

## 11. Khóa phân xử trong `ROW_NUMBER()`, `RANK()` và chọn bản ghi đại diện

Khóa phân xử quan trọng không chỉ ở phân trang mà còn ở **hàm cửa sổ** (*window functions*) và chọn “một dòng tốt nhất”.

### 11.1. `ROW_NUMBER()` cần thứ tự đủ chi tiết

Giả sử muốn đánh số tất cả đơn từ mới đến cũ:

```sql
SELECT
    order_id,
    placed_at,
    ROW_NUMBER() OVER (
        ORDER BY placed_at DESC, order_id DESC
    ) AS row_no
FROM orders
ORDER BY placed_at DESC, order_id DESC;
```

`ROW_NUMBER()` gán số thứ tự 1, 2, 3... theo quy tắc trong `OVER`. Nếu `OVER (ORDER BY placed_at DESC)` chỉ có một cột thời gian, các đơn cùng thời điểm có thể nhận các số thứ tự khác nhau ở các lần thực thi vì không có tiêu chí phân xử.

Lưu ý: `ORDER BY` **bên trong `OVER`** dùng để tính giá trị của hàm cửa sổ; nó **không thay thế** `ORDER BY` ở cấp truy vấn ngoài cùng nếu muốn kết quả được hiển thị đúng thứ tự.

### 11.2. “Đơn mới nhất của mỗi khách hàng”

Yêu cầu này cần **một dòng trên mỗi khách**. Có thể dùng `ROW_NUMBER()` theo từng nhóm:

```sql
WITH ranked_orders AS (
    SELECT
        order_id,
        customer_id,
        placed_at,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY placed_at DESC, order_id DESC
        ) AS rn
    FROM orders
)
SELECT customer_id, order_id, placed_at
FROM ranked_orders
WHERE rn = 1
ORDER BY customer_id ASC;
```

Ở dữ liệu mẫu, các đơn được chọn lần lượt theo khách là:

| customer_id | order_id mới nhất |
|---:|---:|
| 1 | 103 |
| 2 | 102 |
| 3 | 110 |
| 4 | 106 |
| 5 | 108 |

Khách 1 có hai đơn `101` và `103` cùng thời điểm; nhờ `order_id DESC`, ta chọn **103** theo quy tắc đã công bố. Nếu không có khóa phân xử, truy vấn `WHERE rn = 1` vẫn chỉ trả một dòng nhưng **không bảo đảm dòng nào được chọn** khi đồng hạng.

### 11.3. Phân biệt đánh số xác định với giữ đồng hạng

Giả sử hai người có **cùng điểm số**:

- `ROW_NUMBER() OVER (ORDER BY score DESC, participant_id ASC)` tạo **thứ tự một-một**, có một người số 1 và người kia số 2.
- `RANK() OVER (ORDER BY score DESC)` cho phép hai người cùng **hạng 1** nếu bằng điểm.
- `DENSE_RANK() OVER (ORDER BY score DESC)` cũng cho cùng hạng 1, nhưng xử lý số hạng tiếp theo khác `RANK`.

Nếu **quy tắc nghiệp vụ phải công nhận đồng hạng**, việc thêm `participant_id` trực tiếp vào `ORDER BY` của `RANK()` sẽ khiến hai người có cùng điểm nhưng ID khác nhau **không còn đồng hạng theo định nghĩa hàm**. Đó là thay đổi **ngữ nghĩa xếp hạng**, không chỉ cải thiện hiển thị.

Vì vậy có thể:

```sql
SELECT
    participant_id,
    score,
    RANK() OVER (ORDER BY score DESC) AS competition_rank
FROM participants
ORDER BY score DESC, participant_id ASC;
```

Hàm `RANK()` dùng **điểm** để xác định đồng hạng, trong khi `ORDER BY` ở ngoài dùng thêm **ID** để hiển thị thứ tự ổn định giữa những người đồng điểm. Hãy phân biệt “cần có thứ tự xác định của từng dòng” với “có cần phá đồng hạng trong xếp hạng nghiệp vụ hay không”.

## 12. Thứ tự chuỗi, collation và biểu thức chuẩn hóa

Khóa phân xử duy nhất có thể là ID, nhưng thứ tự trước đó còn phụ thuộc cách so sánh dữ liệu:

```sql
SELECT customer_id, full_name
FROM customers
ORDER BY full_name ASC, customer_id ASC;
```

Trong truy vấn này, `customer_id` bảo đảm hai người trùng tên có thứ tự phân biệt. Tuy nhiên, thứ tự giữa các tên **khác nhau** phụ thuộc collation của database hoặc biểu thức: cách so chữ hoa/chữ thường, dấu tiếng Việt hoặc ký tự đặc biệt có thể khác ở hai hệ thống.

Vì thế, một thứ tự xác định **trong một môi trường** chưa chắc đồng nghĩa thứ tự hoàn toàn giống nhau giữa môi trường sử dụng collation khác. Nếu báo cáo yêu cầu thứ tự ngôn ngữ nhất định, hãy quy định collation phù hợp và kiểm tra cách nó so sánh các trường hợp đồng nhất theo quy tắc ngôn ngữ.

Ví dụ tiêu chí sắp xếp không phân biệt chữ hoa:

```sql
SELECT customer_id, full_name
FROM customers
ORDER BY LOWER(full_name) ASC, customer_id ASC;
```

Hàm `LOWER` có thể khiến những tên khác nhau chỉ về chữ hoa trở thành đồng hạng ở tiêu chí đầu. `customer_id` phân xử các dòng đó. Biểu thức `LOWER` trên cột cũng có thể tác động đến việc dùng chỉ mục thông thường, nên hãy xét phương án collation/chỉ mục biểu thức nếu yêu cầu thường xuyên lọc hoặc sắp xếp theo cách này.

### 12.1. `ORDER BY` không có nghĩa “luôn luôn dùng lại kết quả lần trước”

Nếu dữ liệu thay đổi, collation thay đổi, tham số truy vấn khác hoặc các khóa đang dùng bị cập nhật, thứ tự hiển thị có thể thay đổi hợp lệ. Điều cần đạt là **quy tắc rõ ràng và phân biệt được các dòng**, từ đó truy vấn với cùng đầu vào và ngữ nghĩa so sánh sẽ có cùng thứ tự logic.

### 12.2. Tránh `ORDER BY` chỉ theo số vị trí cột trong truy vấn quan trọng

Một số hệ hỗ trợ:

```sql
SELECT order_id, placed_at
FROM orders
ORDER BY 2 DESC, 1 DESC;
```

Điều này tương đương sắp theo cột thứ hai rồi cột thứ nhất trong danh sách `SELECT`, nhưng dễ vỡ khi đổi thứ tự cột đầu ra. Viết `ORDER BY placed_at DESC, order_id DESC` rõ nghĩa hơn và khó gây lỗi khi chỉnh sửa báo cáo.

`ORDER BY RANDOM()` trong PostgreSQL (hoặc hàm ngẫu nhiên tương đương) cố ý tạo thứ tự thay đổi; đó là một yêu cầu khác với kết quả có thứ tự xác định. Không nên dùng sắp xếp ngẫu nhiên cho một hệ thống phân trang cần duyệt qua mọi dòng mà không lặp hoặc bỏ sót.

## 13. Chọn khóa phân xử an toàn và thực tế

Một ứng viên khóa phân xử phù hợp thường có các đặc điểm:

1. **Duy nhất** trên mỗi dòng ở độ hạt kết quả; ưu tiên khóa chính hoặc khóa được ràng buộc `UNIQUE` cùng quy tắc `NOT NULL` thích hợp.
2. **Ổn định** trong suốt việc đọc nhiều trang. Tránh chọn cột thường xuyên bị cập nhật làm khóa cuối nếu có lựa chọn tốt hơn.
3. **Có kiểu so sánh rõ ràng**; không dựa vào cách ghép chuỗi mơ hồ hoặc chuyển kiểu ngầm.
4. **Không làm sai ưu tiên nghiệp vụ**; đặt khóa phân xử ở cuối `ORDER BY`.
5. **Có mặt trong truy vấn con trỏ** nếu dùng keyset pagination. Ứng dụng có thể giữ ID trong metadata nội bộ dù không hiển thị cột ID trên giao diện.

| Loại kết quả | Khóa sắp xếp nghiệp vụ | Khóa phân xử thường hợp lý |
|---|---|---|
| Một dòng trên mỗi đơn | `placed_at DESC` | `order_id DESC` |
| Một dòng trên mỗi sản phẩm | `price ASC, rating DESC` | `product_id ASC` |
| Một dòng trên mỗi sự kiện | `occurred_at DESC` | `event_id DESC` |
| Một dòng trên mỗi khách sau `GROUP BY customer_id` | `SUM(total_amount) DESC` | `customer_id ASC` |
| Một dòng trên mỗi dòng sản phẩm sau `JOIN` | `order_placed_at DESC, order_id DESC` | `item_id ASC` hoặc khóa dòng sản phẩm tổng hợp |
| Một dòng trên mỗi người tham gia bảng điểm | `score DESC` | `participant_id ASC` cho hiển thị; không tự thêm vào định nghĩa hạng nếu cần giữ đồng hạng |

### 13.1. Khóa `UNIQUE` cần xét `NULL`

Ở nhiều hệ quản trị, một ràng buộc `UNIQUE` có thể cho phép nhiều dòng mang giá trị `NULL` ở cột được ràng buộc, tùy quy tắc xử lý `NULL` và phiên bản. Vì vậy, để một cột thực sự phân xử mọi dòng, cần kiểm tra **độ duy nhất trên dữ liệu kết quả** và cách xử lý `NULL`. Một khóa chính không `NULL` thường đơn giản hơn.

### 13.2. Khóa phân xử không nhất thiết phải hiển thị

Giao diện có thể chỉ hiển thị tên người dùng và điểm:

```sql
SELECT display_name, score
FROM participants
ORDER BY score DESC, participant_id ASC;
```

Trong truy vấn thường không dùng `DISTINCT` hoặc tổng hợp, biểu thức sắp xếp không nhất thiết phải nằm trong `SELECT` ở nhiều hệ quản trị. Do đó ID có thể giúp định vị mà không cần hiển thị lên màn hình. Khi thiết kế API phân trang theo con trỏ, server vẫn cần giữ đủ bộ khóa để tạo và kiểm tra con trỏ trang sau.

## 14. Tối ưu `ORDER BY` có khóa phân xử

Việc thêm khóa phân xử cũng ảnh hưởng cách cơ sở dữ liệu xử lý sắp xếp và lấy giới hạn:

```sql
SELECT order_id, placed_at
FROM orders
ORDER BY placed_at DESC, order_id DESC
LIMIT 20;
```

Trên bảng lớn, một chỉ mục tương ứng với bộ khóa sắp xếp có thể giúp database lấy các dòng đầu mà không cần sắp xếp toàn bộ dữ liệu:

```sql
-- PostgreSQL, ví dụ cấu trúc:
CREATE INDEX idx_orders_page_order
ON orders (placed_at DESC, order_id DESC);
```

Chỉ mục B-tree hỗ trợ việc đọc theo thứ tự khóa, nhưng bộ tối ưu còn xét điều kiện `WHERE`, số dòng trả về, phương thức truy cập và thống kê. Không phải mọi truy vấn có `ORDER BY` đều nên tạo thêm một chỉ mục chuyên biệt.

Với keyset pagination, điều kiện:

```sql
WHERE placed_at < :last_placed_at
   OR (placed_at = :last_placed_at AND order_id < :last_order_id)
ORDER BY placed_at DESC, order_id DESC
```

có thể phù hợp với cùng bộ khóa chỉ mục. Trong PostgreSQL, phép so sánh hàng `(placed_at, order_id) < (...)` có thể được bộ tối ưu sử dụng thuận lợi trong một số trường hợp. Cần kiểm tra kế hoạch thực thi thực tế bằng `EXPLAIN`/`EXPLAIN ANALYZE` khi cần tối ưu.

**Khả năng xác định thứ tự là yêu cầu đúng đắn trước tiên; hiệu năng là vấn đề xem xét tiếp theo.** Không nên bỏ khóa phân xử chỉ vì một truy vấn thử chạy nhanh hơn khi thiếu nó, nếu hệ thống thật cần phân trang nhất quán.

## 15. Một ví dụ triển khai phân trang từ API

Giả sử endpoint `GET /orders` nhận `pageSize` và `cursor`. Ứng dụng quy định:

- Danh sách đơn xếp theo `(placed_at DESC, order_id DESC)`.
- `pageSize` được giới hạn ở giá trị hợp lệ do server quyết định.
- Trang đầu không có `cursor`.
- Trang sau lấy `last_placed_at` và `last_order_id` từ **dòng cuối trang trước**, sau khi đã xác thực con trỏ.

**Trang đầu**:

```sql
SELECT order_id, placed_at, total_amount
FROM orders
ORDER BY placed_at DESC, order_id DESC
LIMIT :page_size;
```

**Trang sau**:

```sql
SELECT order_id, placed_at, total_amount
FROM orders
WHERE placed_at < :last_placed_at
   OR (
       placed_at = :last_placed_at
       AND order_id < :last_order_id
   )
ORDER BY placed_at DESC, order_id DESC
LIMIT :page_size;
```

Các ký hiệu `:page_size`, `:last_placed_at`, `:last_order_id` là placeholder minh họa theo kiểu tham số có tên của một số công cụ hoặc framework; không phải literal SQL có thể gửi nguyên văn tới mọi database. Trong mã ứng dụng, phải bind chúng qua driver và chọn đúng kiểu `TIMESTAMP`/`INTEGER`.

Nếu API hỗ trợ `status=PAID` hoặc tìm kiếm theo khách hàng, bộ lọc đó phải áp dụng **nhất quán ở mọi trang**. Một con trỏ được tạo cho danh sách `status=PAID` không nên dùng lại cho danh sách `status=PENDING`, vì tập dữ liệu và thứ tự cần duyệt đã khác.

Để biết có trang tiếp theo, một chiến lược thường dùng là lấy tối đa `pageSize + 1` dòng rồi trả `pageSize` dòng đầu; dòng dư cho biết ở thời điểm truy vấn còn dữ liệu sau trang hiện tại. Cách này cần cẩn thận xây con trỏ từ **dòng cuối thực sự trả cho người dùng**, không phải từ dòng dư.

`OFFSET` vẫn phù hợp khi tập dữ liệu nhỏ, ít thay đổi hoặc giao diện cần nhảy tới trang số N. Keyset thường thuận lợi khi duyệt nhiều trang trong tập lớn hoặc dòng mới liên tục xuất hiện. Dù chọn phương thức nào, **khóa phân xử vẫn là nền tảng của thứ tự xác định**.

## 16. Bảng các sai lầm thường gặp

| Biểu hiện | Nguyên nhân | Cách xử lý |
|---|---|---|
| Cùng timestamp nhưng dòng đổi chỗ sau mỗi lần chạy | `ORDER BY placed_at` chưa phân xử nhóm bằng nhau | Thêm khóa duy nhất như `order_id` |
| Cùng một ID xuất hiện ở hai trang khi dữ liệu không đổi | Hai truy vấn `LIMIT/OFFSET` có thể chọn thứ tự khác nhau giữa các dòng đồng hạng | Dùng một bộ `ORDER BY` tạo thứ tự toàn phần cho mọi trang |
| Đã có `ORDER BY ... id` nhưng vẫn lặp/bỏ sót khi có thêm đơn mới | `OFFSET` bị dịch vị trí khi tập dữ liệu thay đổi | Xem xét keyset hoặc snapshot theo nghiệp vụ |
| Dùng keyset chỉ lưu timestamp | Bỏ toàn bộ dòng khác cùng timestamp với dòng cuối trang trước | Con trỏ chứa đầy đủ bộ khóa |
| Sắp `score DESC, id ASC` nhưng cursor dùng `id < last_id` | Sai chiều của khóa phân xử | Với `id ASC`, các dòng sau cùng điểm phải có `id > last_id` |
| Thêm ID vào `RANK() OVER` khiến người cùng điểm không còn đồng hạng | Đã thay đổi định nghĩa hạng nghiệp vụ | Xếp hạng theo điểm; dùng ID ở `ORDER BY` ngoài để hiển thị |
| `ORDER BY o.order_id` vẫn có dòng trùng sau `JOIN` | Một đơn có nhiều dòng sản phẩm | Dùng khóa duy nhất ở độ hạt dòng sau `JOIN` |
| `ORDER BY` trong CTE nhưng ngoài cùng không có | Kết quả ngoài cùng không được cam kết theo thứ tự đó | Viết `ORDER BY` ở truy vấn cuối |
| `NULL` nhảy lên đầu/cuối khác môi trường | Quy tắc sắp xếp `NULL` khác nhau | Chỉ rõ `NULLS FIRST/LAST` hoặc biểu thức `CASE` |
| Tên tiếng Việt đổi vị trí giữa môi trường | Collation khác nhau | Chọn/kiểm tra collation theo yêu cầu |
| Chọn `ROW_NUMBER() = 1` mà không phân xử | Đồng hạng không có quy tắc chọn đại diện | Thêm khóa phân xử trong cửa sổ |

## 17. Thực hành trên PostgreSQL

Để tự chạy các ví dụ, có thể tạo bảng **tạm** với dữ liệu mẫu. Đoạn script sau dùng tên `pagination_lab_orders` để tránh nhầm với bảng `orders` thật của một dự án.

```sql
CREATE TEMP TABLE pagination_lab_orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    placed_at TIMESTAMP NOT NULL,
    total_amount NUMERIC(12, 2) NOT NULL,
    status VARCHAR(20) NOT NULL
);

INSERT INTO pagination_lab_orders
    (order_id, customer_id, placed_at, total_amount, status)
VALUES
    (101, 1, TIMESTAMP '2026-07-03 09:00:00', 250000, 'PAID'),
    (102, 2, TIMESTAMP '2026-07-03 09:00:00', 200000, 'PAID'),
    (103, 1, TIMESTAMP '2026-07-03 09:00:00', 300000, 'PAID'),
    (104, 3, TIMESTAMP '2026-07-03 10:30:00', 150000, 'PAID'),
    (105, 2, TIMESTAMP '2026-07-02 14:00:00', 120000, 'PAID'),
    (106, 4, TIMESTAMP '2026-07-02 14:00:00',  80000, 'CANCELLED'),
    (107, 4, TIMESTAMP '2026-07-01 12:00:00', 200000, 'PAID'),
    (108, 5, TIMESTAMP '2026-07-01 12:00:00', 180000, 'PAID'),
    (109, 5, TIMESTAMP '2026-06-30 08:00:00',  90000, 'PAID'),
    (110, 3, TIMESTAMP '2026-07-03 10:30:00', 160000, 'PENDING');
```

Vì đây là bảng tạm, nó biến mất khi kết nối PostgreSQL kết thúc. Nếu chạy lại nguyên script trong cùng kết nối đã tạo bảng, cần mở một phiên mới hoặc chủ động chọn tên bảng khác. Những câu SQL khác trong bài sử dụng tên `orders` để minh họa cách viết chung; khi chạy trên bảng thực hành, thay tên `orders` bằng `pagination_lab_orders`.

### 17.1. Truy vấn toàn bộ kết quả với khóa phân xử

```sql
SELECT order_id, placed_at
FROM pagination_lab_orders
ORDER BY placed_at DESC, order_id DESC;
```

Kết quả mã đơn:

```text
110, 104, 103, 102, 101, 106, 105, 108, 107, 109
```

### 17.2. Hai trang liên tiếp bằng `OFFSET`

```sql
-- Trang 1: 110, 104, 103.
SELECT order_id, placed_at
FROM pagination_lab_orders
ORDER BY placed_at DESC, order_id DESC
LIMIT 3 OFFSET 0;

-- Trang 2: 102, 101, 106.
SELECT order_id, placed_at
FROM pagination_lab_orders
ORDER BY placed_at DESC, order_id DESC
LIMIT 3 OFFSET 3;
```

### 17.3. Trang thứ hai bằng keyset

```sql
-- Giả sử trang đầu kết thúc ở đơn 103.
SELECT order_id, placed_at
FROM pagination_lab_orders
WHERE placed_at < TIMESTAMP '2026-07-03 09:00:00'
   OR (
       placed_at = TIMESTAMP '2026-07-03 09:00:00'
       AND order_id < 103
   )
ORDER BY placed_at DESC, order_id DESC
LIMIT 3;
-- 102, 101, 106.
```

### 17.4. Chọn đơn mới nhất cho từng khách hàng

```sql
WITH ranked_orders AS (
    SELECT
        order_id,
        customer_id,
        placed_at,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY placed_at DESC, order_id DESC
        ) AS rn
    FROM pagination_lab_orders
)
SELECT customer_id, order_id, placed_at
FROM ranked_orders
WHERE rn = 1
ORDER BY customer_id;
-- Khách 1..5 lần lượt có đơn 103, 102, 110, 106, 108.
```

## 18. Bài tập tự luyện

Sử dụng dữ liệu trong bảng `pagination_lab_orders`. Trước khi viết truy vấn, hãy xác định: **một dòng kết quả đại diện cho gì; những cột nào tạo ra đồng hạng; cột/tổ hợp nào phân biệt được tất cả các dòng**.

### Bài 1 — Thứ tự đầy đủ

Lấy mọi đơn, sắp theo `total_amount` giảm dần. Nếu bằng tiền, ưu tiên `placed_at` mới hơn. Nếu vẫn bằng, `order_id` nhỏ hơn đứng trước. Viết `ORDER BY` và nêu vì sao bộ khóa đủ phân biệt mọi đơn.

### Bài 2 — Trang thứ ba

Với thứ tự `(placed_at DESC, order_id DESC)` và `LIMIT 3`, trang thứ ba (`OFFSET 6`) có những mã đơn nào? Nếu dùng keyset, cần bộ khóa của dòng nào để lấy trang thứ ba?

### Bài 3 — Sửa con trỏ thiếu khóa

Một người viết truy vấn trang sau:

```sql
SELECT order_id, placed_at
FROM pagination_lab_orders
WHERE placed_at < TIMESTAMP '2026-07-03 09:00:00'
ORDER BY placed_at DESC, order_id DESC
LIMIT 3;
```

Giả sử trang trước kết thúc ở đơn `103`. Truy vấn trên bỏ sót những đơn nào? Viết lại điều kiện để không bỏ các dòng cùng thời điểm.

### Bài 4 — Phân xử trên `JOIN`

Giả sử `order_items` có thể chứa nhiều sản phẩm trong một đơn và có khóa chính `(order_id, line_no)`. Nếu kết quả là **một dòng trên mỗi sản phẩm**, tại sao `ORDER BY o.placed_at DESC, o.order_id DESC` chưa đủ? Viết khóa sắp xếp bổ sung.

### Bài 5 — Xếp hạng và đồng hạng

Hai người có điểm 95 nhưng ID khác nhau. Nếu nghiệp vụ muốn **cùng hạng**, nên dùng `RANK() OVER (ORDER BY score DESC, participant_id ASC)` hay `RANK() OVER (ORDER BY score DESC)`? Làm thế nào hiển thị hai người theo thứ tự ID mà vẫn giữ cùng hạng?

### Bài 6 — Dữ liệu thay đổi giữa hai trang

Giải thích vì sao vẫn có thể gặp dòng lặp giữa hai lần tải trang `OFFSET` dù đã dùng `ORDER BY placed_at DESC, order_id DESC`. Nêu một trường hợp keyset giúp giảm vấn đề, và một trường hợp keyset vẫn cần chiến lược bổ sung.

### Bài 7 — `NULL` ở tiêu chí chính

Giả sử `articles(article_id PRIMARY KEY, published_at TIMESTAMPTZ NULL)`. Viết thứ tự “bài có ngày xuất bản trước, mới nhất trước; bài chưa xuất bản cuối danh sách; các bài trùng thời điểm sắp ID tăng dần” trong PostgreSQL.

<details>
<summary>Gợi ý lời giải</summary>

**Bài 1:**

```sql
SELECT order_id, total_amount, placed_at
FROM pagination_lab_orders
ORDER BY total_amount DESC, placed_at DESC, order_id ASC;
```

`order_id` là khóa chính và nằm cuối bộ sắp xếp, nên phân biệt những dòng bằng nhau về tiền và thời điểm.

**Bài 2:** Trang ba là `105`, `108`, `107`. Để lấy trang thứ ba bằng keyset, cần con trỏ từ **dòng cuối trang hai**, tức `(2026-07-02 14:00:00, 106)`:

```sql
SELECT order_id
FROM pagination_lab_orders
WHERE placed_at < TIMESTAMP '2026-07-02 14:00:00'
   OR (
       placed_at = TIMESTAMP '2026-07-02 14:00:00'
       AND order_id < 106
   )
ORDER BY placed_at DESC, order_id DESC
LIMIT 3;
```

**Bài 3:** Thiếu `102` và `101` vì chúng cùng thời điểm với `103`. Thêm:

```sql
WHERE placed_at < TIMESTAMP '2026-07-03 09:00:00'
   OR (
       placed_at = TIMESTAMP '2026-07-03 09:00:00'
       AND order_id < 103
   )
```

**Bài 4:** Sau `JOIN`, nhiều dòng có chung mã đơn; thêm `i.line_no` để phân xử:

```sql
ORDER BY o.placed_at DESC, o.order_id DESC, i.line_no ASC
```

Với một dòng trên mỗi `(order_id,line_no)`, tổ hợp này tạo thứ tự phân biệt.

**Bài 5:** Dùng `RANK() OVER (ORDER BY score DESC)` để đồng hạng theo điểm, và `ORDER BY score DESC, participant_id ASC` **ở truy vấn ngoài** để hiển thị ID tăng dần trong nhóm đồng điểm.

**Bài 6:** Ví dụ có đơn mới thêm ở đầu giữa lúc tải trang 1 và trang 2, khiến `OFFSET` của trang 2 chỉ sang vị trí mới và có thể lặp một dòng đã xem. Keyset tiếp tục **sau bộ khóa cuối trang trước**, nên không bị dịch đơn thuần bởi số dòng mới ở phía trước. Nhưng nếu khóa `placed_at` của một đơn bị cập nhật làm nó chuyển qua con trỏ, keyset vẫn không đảm bảo một snapshot cố định.

**Bài 7:**

```sql
SELECT article_id, published_at
FROM articles
ORDER BY published_at DESC NULLS LAST, article_id ASC;
```

</details>

## 19. Nguyên tắc cần nhớ

**`ORDER BY` chỉ xác định thứ tự đến mức các biểu thức của nó có thể phân biệt các dòng.** Nếu hai dòng bằng nhau trên mọi biểu thức đang dùng, SQL không cam kết dòng nào xuất hiện trước. Vì vậy, khi phân trang, lấy `LIMIT`, chọn một bản ghi theo `ROW_NUMBER()` hoặc xuất danh sách cần thứ tự rõ ràng, hãy bổ sung **khóa phân xử duy nhất ở độ hạt của kết quả**, thường là khóa chính hoặc tổ hợp khóa.

Với một dòng trên mỗi đơn:

```sql
ORDER BY placed_at DESC, order_id DESC
```

là mẫu dễ hiểu: thời gian quyết định ưu tiên, ID phân xử khi trùng thời gian. Nếu dùng **keyset pagination**, con trỏ phải chứa **đầy đủ bộ khóa**, và điều kiện trang sau phải đi đúng chiều của từng thành phần `ASC`/`DESC`. Nếu dùng **OFFSET**, khóa phân xử ngăn thứ tự đồng hạng tùy ý nhưng **không khóa dữ liệu giữa các lần tải trang**. Muốn kết quả thực sự ổn định khi hệ thống thay đổi liên tục, cần thêm chiến lược snapshot hoặc thiết kế phân trang phù hợp.

Chọn khóa phân xử dựa trên **độ hạt đầu ra, tính duy nhất và yêu cầu nghiệp vụ** sẽ khiến kết quả SQL dễ giải thích, thuận tiện để kiểm tra và ít gây hiện tượng lặp/bỏ sót khi người dùng duyệt qua nhiều trang.

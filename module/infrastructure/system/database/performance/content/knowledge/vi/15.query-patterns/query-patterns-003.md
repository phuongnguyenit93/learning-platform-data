# UNION và UNION ALL: loại trùng, thứ tự và chi phí

## 1. Khi nào cần kết hợp nhiều tập kết quả?

Trong ứng dụng cơ sở dữ liệu, một yêu cầu có thể cần lấy dữ liệu từ nhiều nhóm nguồn: đơn hàng đang hoạt động và đơn hàng đã lưu trữ, sự kiện từ nhiều loại bảng, bản ghi của nhiều tenant, hoặc kết quả của các truy vấn có điều kiện khác nhau. SQL cung cấp các phép toán tập hợp để kết hợp kết quả của nhiều câu `SELECT`. Hai phép được dùng phổ biến nhất là `UNION` và `UNION ALL`.

Khác biệt quan trọng nhất nằm ở cách xử lý dòng trùng. `UNION` loại bỏ các dòng trùng trong kết quả kết hợp; `UNION ALL` giữ lại mọi lần xuất hiện của dòng. Vì loại trùng có thể cần sort hoặc hash trên toàn bộ tập dữ liệu, hai cách viết có chi phí CPU, bộ nhớ, I/O tạm và thời gian khác nhau.

Trong tối ưu hiệu năng cơ sở dữ liệu, chọn đúng phép toán đòi hỏi hiểu rõ ý nghĩa của một dòng, khả năng các nhánh trả về cùng dữ liệu, quy tắc so sánh kiểu dữ liệu và NULL, thứ tự kết quả, cũng như cách bộ tối ưu thực thi từng nhánh. Chọn `UNION ALL` chỉ vì nó thường nhanh hơn có thể làm kết quả xuất hiện bản ghi lặp; dùng `UNION` khi không cần loại trùng lại tạo công việc không cần thiết.

Bài học này trình bày semantics của hai phép toán, cấu trúc thực thi thường gặp, tác động của kiểu dữ liệu và độ rộng dòng, cách đặt điều kiện và giới hạn trong từng nhánh, các tình huống thay thế `OR` bằng nhiều nhánh, thứ tự kết quả, recursive CTE và quy trình đo kiểm chứng. Tên toán tử trong execution plan và chiến lược vật lý khác nhau theo hệ quản trị; cần đọc plan thực tế của nền tảng đang vận hành.

## 2. Semantics: UNION loại trùng, UNION ALL giữ mọi dòng

### 2.1. SQL thường xử lý dữ liệu theo bag semantics

Trong lý thuyết tập hợp, một phần tử chỉ xuất hiện một lần. Tuy nhiên, kết quả truy vấn SQL thông thường có thể chứa nhiều dòng giống nhau. Mô hình này thường được gọi là bag hoặc multiset semantics: mỗi dòng có thể xuất hiện với một số lần (multiplicity) nhất định.

Ví dụ, bảng `online_orders` có hai dòng cùng giá trị được chiếu ra và bảng `store_orders` có một dòng giống hệt:

```sql
SELECT customer_id, status
FROM online_orders

UNION ALL

SELECT customer_id, status
FROM store_orders;
```

Nếu cả ba dòng đều là `(42, 'PAID')`, kết quả `UNION ALL` có ba lần xuất hiện của dòng đó. Nếu thay bằng `UNION`, kết quả chỉ còn một dòng `(42, 'PAID')`.

| Phép toán | Cách xử lý | Multiplicity của một dòng trong kết quả |
|---|---|---|
| `UNION ALL` | Ghép mọi dòng từ các nhánh | Tổng số lần xuất hiện ở tất cả nhánh |
| `UNION` | Ghép rồi loại các dòng trùng | Một lần nếu dòng xuất hiện ở ít nhất một nhánh |

Có thể mô tả ngắn gọn bằng công thức. Nếu một dòng `r` xuất hiện `m` lần ở nhánh A và `n` lần ở nhánh B thì:

\[
\operatorname{count}_{A\ UNION\ ALL\ B}(r)=m+n
\]

\[
\operatorname{count}_{A\ UNION\ B}(r)=
\begin{cases}
1 & \text{nếu } m+n > 0\\
0 & \text{nếu } m+n = 0
\end{cases}
\]

`UNION` không chỉ loại trùng giữa hai nhánh; nó cũng loại các dòng lặp nhiều lần ngay bên trong từng nhánh.

### 2.2. Ví dụ kết quả cụ thể

Giả sử hai nhánh trả về:

| Nhánh A | Nhánh B |
|---|---|
| (10, 'PAID') | (10, 'PAID') |
| (11, 'OPEN') | (12, 'PAID') |
| (11, 'OPEN') | (12, 'PAID') |

Kết quả `UNION ALL` có sáu dòng: hai lần `(10, 'PAID')`, hai lần `(11, 'OPEN')` và hai lần `(12, 'PAID')`. Kết quả `UNION` có ba dòng duy nhất: `(10, 'PAID')`, `(11, 'OPEN')` và `(12, 'PAID')`.

Điểm cần chú ý: `UNION` so sánh toàn bộ các cột được chọn theo quy tắc tương đương của phép toán tập hợp. Nó không tự hiểu khóa nghiệp vụ. Nếu hai bản ghi có cùng `customer_id` nhưng khác `status`, chúng không phải dòng trùng khi truy vấn chọn cả hai cột.

### 2.3. Loại trùng theo dòng hay theo khóa nghiệp vụ?

Giả sử yêu cầu là lấy mỗi khách hàng một lần, bất kể trạng thái đơn hàng. Truy vấn sau không bảo đảm mỗi khách hàng chỉ xuất hiện một lần:

```sql
SELECT customer_id, status
FROM online_orders
UNION
SELECT customer_id, status
FROM store_orders;
```

Nếu khách hàng 42 có cả trạng thái `PAID` và `OPEN`, hai dòng vẫn khác nhau. `UNION` chỉ loại dòng giống nhau trên cả `customer_id` và `status`.

Nếu cần một dòng cho mỗi khách hàng, phải xác định quy tắc chọn trạng thái hoặc tổng hợp, ví dụ ưu tiên trạng thái mới nhất bằng `ROW_NUMBER`, `MAX` theo quy tắc nghiệp vụ hoặc một phép aggregate khác. Không dùng `UNION` như một cách thay thế chung cho `GROUP BY` hay `DISTINCT ON`.

### 2.4. NULL trong loại trùng

Trong điều kiện so sánh thông thường, `NULL = NULL` không trả về TRUE mà cho kết quả UNKNOWN. Tuy nhiên, trong thao tác loại trùng của `UNION` (cũng như `DISTINCT`), các dòng có NULL ở cùng vị trí và các giá trị còn lại tương đương được xem là trùng theo quy tắc duplicate elimination của SQL.

Ví dụ:

```sql
SELECT CAST(NULL AS INTEGER) AS region_id, 'UNKNOWN' AS label
UNION
SELECT CAST(NULL AS INTEGER), 'UNKNOWN';
```

Kết quả chỉ có một dòng. Với `UNION ALL`, cả hai lần xuất hiện đều được giữ lại. Vì vậy, không suy luận semantics loại trùng từ phép so sánh `NULL = NULL` trong `WHERE`.

## 3. Điều kiện tương thích giữa các nhánh

### 3.1. Số cột và vị trí cột

Mỗi nhánh của `UNION` hoặc `UNION ALL` phải trả về cùng số lượng cột. Các cột được ghép theo vị trí, không theo tên alias. Vì vậy, thứ tự cột phải nhất quán.

```sql
-- Sai về ý nghĩa nếu hai nhánh đặt cột theo thứ tự khác nhau
SELECT order_id, customer_id
FROM online_orders
UNION ALL
SELECT customer_id, order_id
FROM store_orders;
```

Truy vấn có thể vẫn hợp lệ nếu kiểu tương thích, nhưng dữ liệu hai cột bị đảo nghĩa. Hãy liệt kê cột tường minh và giữ cùng thứ tự trong mọi nhánh. Tránh `SELECT *` vì thay đổi schema hoặc thứ tự cột có thể âm thầm làm thay đổi kết quả.

### 3.2. Kiểu dữ liệu chung và chuyển đổi ngầm định

Các cột tương ứng phải có kiểu tương thích. Hệ quản trị có thể xác định kiểu kết quả chung bằng quy tắc ưu tiên kiểu và chèn chuyển đổi ngầm định. Nếu một nhánh trả `INTEGER`, nhánh khác trả `BIGINT`, kiểu kết quả có thể được nâng lên kiểu rộng hơn. Với chuỗi, decimal, ngày giờ hoặc kiểu đặc thù, quy tắc có thể phức tạp hơn.

Ví dụ nên thể hiện kiểu rõ ràng khi cần:

```sql
SELECT order_id, CAST(created_at AS TIMESTAMP) AS event_time
FROM online_orders

UNION ALL

SELECT order_id, archived_at AS event_time
FROM archived_orders;
```

Việc ép kiểu cần giữ nguyên miền giá trị và độ chính xác. Không ép `DECIMAL` sang `FLOAT` nếu nghiệp vụ cần độ chính xác thập phân; không chuyển timestamp có múi giờ sang kiểu không múi giờ nếu điều đó làm thay đổi thời điểm; không chuyển khóa số sang chuỗi tùy tiện.

Chuyển đổi trên biểu thức đầu ra của nhánh thường không nhất thiết làm mất chỉ mục ở điều kiện truy cập bảng, nhưng nó có thể tăng CPU, ảnh hưởng độ rộng và kiểu so sánh khi loại trùng. Hãy kiểm tra plan từng nhánh và kiểu dữ liệu đầu ra.

### 3.3. Collation và so sánh chuỗi

Với cột chuỗi, các nhánh cần có collation tương thích theo quy tắc của hệ quản trị. Collation ảnh hưởng đến cách so sánh ký tự, hoa thường, dấu và thứ tự. Hai chuỗi có byte khác nhau vẫn có thể được xem là tương đương theo collation không phân biệt hoa thường hoặc dấu.

Ví dụ, nếu một nhánh trả `ABC` và nhánh khác trả `abc`, `UNION` có thể xem chúng là trùng trong một collation không phân biệt hoa thường, nhưng không nhất thiết trùng trong collation phân biệt hoa thường hoặc so sánh nhị phân. Khi cần chuẩn hóa, hãy chọn collation hoặc biểu thức chuyển đổi rõ ràng và bảo đảm nó phù hợp với nghiệp vụ.

### 3.4. Tên cột kết quả

Trong nhiều hệ quản trị, tên cột của tập kết quả hợp nhất được lấy từ danh sách chọn của nhánh đầu tiên. Alias ở nhánh sau không đổi tên cột kết quả chung. Khi dùng `ORDER BY` cuối cùng theo tên, hãy đặt alias rõ ràng ở nhánh đầu và kiểm tra cú pháp của engine.

## 4. Cách thực thi thường gặp

### 4.1. UNION ALL: ghép các nhánh

Về mặt logic, `UNION ALL` chỉ cần đưa các dòng từ từng nhánh vào cùng một luồng kết quả. Kế hoạch có thể dùng toán tử có tên `Append`, `Concatenate`, `Union All`, `Concatenation` hoặc toán tử tương đương. Các nhánh có thể chạy tuần tự, song song hoặc theo cách được bộ tối ưu chọn.

Vì không phải loại trùng, `UNION ALL` thường tránh được một bước sort/hash trên toàn bộ kết quả. Nếu các nhánh đã lọc tốt và chỉ trả những cột cần thiết, hệ thống có thể phát dòng theo luồng với chi phí bổ sung thấp.

Điều đó không có nghĩa `UNION ALL` luôn miễn phí hoặc luôn nhanh. Mỗi nhánh vẫn có thể cần scan lớn, join, sort, aggregate, chuyển kiểu hoặc truy cập storage. Nếu một nhánh rất chậm, thời gian hoàn tất tổng thể có thể bị chi phối bởi nhánh đó. Khi chạy song song, tranh chấp CPU, I/O và bộ nhớ có thể làm lợi ích giảm.

### 4.2. UNION: ghép và loại trùng

Để thực hiện `UNION`, engine phải xác định những dòng nào tương đương trên toàn bộ cột kết quả. Các chiến lược vật lý phổ biến gồm:

- **Sort và unique:** sắp xếp dòng theo các cột kết quả, sau đó loại các dòng liền kề giống nhau.
- **Hash-based duplicate elimination:** tính hash từ các cột kết quả, giữ một đại diện cho mỗi khóa hash và xử lý va chạm bằng phép so sánh đầy đủ.
- **Chiến lược khác hoặc biến đổi tương đương:** tùy engine, dữ liệu đã có thứ tự, partitioning và khả năng song song.

Minh họa một dạng kế hoạch:

```text
             Sort / Hash Aggregate / Unique
                         ^
                         |
                   UNION DISTINCT
                    /          \
             Scan nhánh A    Scan nhánh B
```

Tên toán tử thực tế có thể khác. Trong một số execution plan, `UNION` được thể hiện bằng `Concatenation` phía dưới và `Sort (Distinct Sort)` phía trên; trong hệ khác có thể là `HashAggregate`, `Unique` hoặc operator chuyên biệt.

### 4.3. Chi phí của sort hoặc hash

Loại trùng phải xử lý tập dòng kết hợp. Chi phí tăng theo số dòng và độ rộng dòng, vì engine cần so sánh hoặc băm các cột tham gia. Nếu dữ liệu không vừa bộ nhớ, sort có thể spill thành các run tạm; hash có thể chia batch hoặc dùng vùng lưu trữ tạm. Khi đó phát sinh thêm I/O, CPU và thời gian.

Nếu hai nhánh trả về tổng cộng hàng triệu dòng rộng, nhưng sau loại trùng chỉ còn một phần nhỏ, bước distinct vẫn phải xử lý dữ liệu đầu vào lớn. Giảm cột không cần thiết, lọc an toàn trong từng nhánh và giảm dữ liệu trước khi hợp nhất có thể làm bước loại trùng nhẹ hơn.

Không thể kết luận sort luôn chậm hơn hash hoặc ngược lại. Chiến lược được chọn phụ thuộc cardinality, độ rộng, thứ tự sẵn có, bộ nhớ, thống kê và engine. Hãy đọc actual plan và số liệu spill.

## 5. Độ rộng dòng ảnh hưởng đến UNION

Giả sử cần hợp nhất mã đơn hàng và trạng thái, nhưng truy vấn lại lấy thêm cột mô tả dài, JSON hoặc payload lớn. `UNION` phải so sánh toàn bộ danh sách cột, nên dòng rộng làm tăng bộ nhớ, băng thông và chi phí sort/hash.

```sql
-- Mang theo payload lớn dù không cần cho kết quả
SELECT order_id, status, raw_payload
FROM live_events
UNION
SELECT order_id, status, raw_payload
FROM archived_events;
```

Nếu nghiệp vụ chỉ cần mã và trạng thái:

```sql
SELECT order_id, status
FROM live_events
UNION
SELECT order_id, status
FROM archived_events;
```

Hai truy vấn có semantics khác nhau vì tiêu chí xác định dòng trùng khác nhau. Chỉ bỏ `raw_payload` nếu kết quả mong muốn thật sự chỉ phân biệt theo `order_id` và `status`. Nếu payload là một phần của định nghĩa bản ghi, loại bỏ nó sẽ làm những dòng khác payload bị gộp thành một.

Projection pushdown chỉ hợp lệ khi các cột bị bỏ không cần cho điều kiện lọc, join, định nghĩa duplicate hoặc kết quả đầu ra. Khi `UNION` loại trùng, danh sách cột chính là một phần của quy tắc so sánh.

## 6. Thứ tự kết quả: UNION không tự bảo đảm ORDER BY

### 6.1. Không có thứ tự mặc định

Không nên dựa vào thứ tự nhánh hoặc thứ tự vật lý để diễn giải kết quả của `UNION` hay `UNION ALL`. Ngay cả khi một lần chạy trả tất cả dòng nhánh A trước rồi đến nhánh B, kế hoạch khác, parallel execution, thay đổi chỉ mục hoặc phiên bản engine có thể trả thứ tự khác.

Nếu ứng dụng cần thứ tự xác định, đặt `ORDER BY` ở cuối toàn bộ biểu thức hợp nhất:

```sql
SELECT order_id, created_at
FROM live_orders

UNION ALL

SELECT order_id, created_at
FROM archived_orders
ORDER BY created_at DESC, order_id DESC;
```

`ORDER BY` cuối cùng sắp xếp tập kết quả đã hợp nhất. Khóa phụ `order_id` giúp thứ tự xác định hơn khi nhiều dòng có cùng `created_at`, giả sử khóa đó phân biệt được các dòng trong kết quả.

### 6.2. ORDER BY trong từng nhánh

Thông thường, `ORDER BY` đặt trong một nhánh của phép toán tập hợp không xác định thứ tự cuối cùng của toàn bộ kết quả. Nếu cần giới hạn hoặc sắp xếp nội bộ từng nhánh, hãy đặt nhánh trong subquery/CTE theo cú pháp của hệ quản trị, rồi đặt `ORDER BY` cuối cùng nếu cần thứ tự toàn cục.

Ví dụ lấy 100 sự kiện mới nhất từ mỗi nguồn rồi hợp nhất:

```sql
WITH recent_live AS (
    SELECT event_id, event_time, event_type
    FROM live_events
    ORDER BY event_time DESC, event_id DESC
    FETCH FIRST 100 ROWS ONLY
),
recent_archive AS (
    SELECT event_id, event_time, event_type
    FROM archived_events
    ORDER BY event_time DESC, event_id DESC
    FETCH FIRST 100 ROWS ONLY
)
SELECT event_id, event_time, event_type
FROM recent_live
UNION ALL
SELECT event_id, event_time, event_type
FROM recent_archive
ORDER BY event_time DESC, event_id DESC
FETCH FIRST 100 ROWS ONLY;
```

Hai giới hạn trong CTE chọn tối đa 100 dòng mỗi nguồn; giới hạn cuối chọn 100 dòng mới nhất trên cả hai nguồn. Nếu bỏ `ORDER BY` cuối, kết quả không được bảo đảm có thứ tự toàn cục. Cú pháp `FETCH FIRST` và việc dùng `ORDER BY` trong CTE có thể khác theo engine.

### 6.3. Thứ tự và chi phí sort

`ORDER BY` cuối cùng có thể cần sort toàn bộ kết quả hợp nhất, kể cả khi dùng `UNION ALL`. Nếu ứng dụng không cần thứ tự, không thêm sort chỉ để kết quả “trông ổn định”. Nếu cần thứ tự và chỉ lấy top-N, một số engine có thể dùng top-N sort hoặc tận dụng thứ tự chỉ mục; hãy kiểm tra kế hoạch.

Nếu nhánh đầu vào đã có thứ tự tương thích, engine có thể dùng chiến lược merge hoặc giảm công việc sort trong một số trường hợp. Nhưng không dựa vào thứ tự ngầm của nhánh; chỉ `ORDER BY` ở phạm vi kết quả cần bảo đảm mới tạo hợp đồng thứ tự cho ứng dụng.

## 7. Khi nào chọn UNION ALL?

### 7.1. Các nhánh chắc chắn rời nhau

Nếu điều kiện nghiệp vụ chứng minh hai nhánh không thể trả cùng một dòng theo định nghĩa kết quả, `UNION ALL` thường phù hợp. Ví dụ, dữ liệu được chia thành hai vùng thời gian không giao nhau:

```sql
SELECT event_id, event_time, event_type
FROM events_2025
WHERE event_time >= TIMESTAMP '2025-01-01 00:00:00'
  AND event_time <  TIMESTAMP '2026-01-01 00:00:00'

UNION ALL

SELECT event_id, event_time, event_type
FROM events_2026
WHERE event_time >= TIMESTAMP '2026-01-01 00:00:00'
  AND event_time <  TIMESTAMP '2027-01-01 00:00:00';
```

Nếu hai bảng thật sự chứa các khoảng dữ liệu không giao nhau và khóa/giá trị được chiếu ra không tạo bản sao ngoài ý muốn, không cần trả chi phí loại trùng. Điều kiện không giao nhau phải được bảo đảm bởi thiết kế lưu trữ hoặc ràng buộc dữ liệu, không chỉ là giả định của người viết truy vấn.

### 7.2. Các nguồn biểu diễn những lần xuất hiện độc lập

Một số trường hợp cần giữ mọi sự kiện, kể cả khi nội dung các cột được chọn giống nhau. Ví dụ, hai lần phát sinh giao dịch có cùng `account_id`, `event_type` và timestamp làm tròn nhưng vẫn là hai sự kiện riêng. `UNION ALL` giữ đúng multiplicity; `UNION` có thể gộp chúng nếu các cột đầu ra giống nhau.

Nếu cần phân biệt sự kiện, hãy đưa khóa sự kiện hoặc định danh nguồn vào kết quả. Dù dùng `UNION ALL`, việc chọn cột định danh rõ ràng vẫn giúp downstream xử lý đúng.

### 7.3. Dữ liệu đã duy nhất theo ràng buộc

Nếu mỗi nhánh có khóa duy nhất và miền khóa giữa các nhánh không giao nhau, `UNION ALL` có thể tránh distinct không cần thiết khi danh sách cột đầu ra chứa khóa đó hoặc có bảo đảm tương đương rằng không có hai dòng đầu ra giống nhau. Nếu bỏ khóa khỏi projection, hai bản ghi khác nhau vẫn có thể trở thành hai dòng giống nhau ở các cột còn lại. Hãy xác minh unique constraint, partition boundary, tenant id hoặc điều kiện thời gian thực sự bảo đảm không trùng theo đúng danh sách cột kết quả. Chỉ nhìn tên bảng như `current` và `archive` không đủ để chứng minh.

## 8. Khi nào cần UNION?

Dùng `UNION` khi yêu cầu nghiệp vụ là tập các dòng duy nhất trên đúng danh sách cột được chọn, hoặc khi các nhánh có thể giao nhau và duplicate phải được loại bỏ.

Ví dụ, danh sách mã vùng hoạt động được lấy từ nhiều nguồn, và yêu cầu chỉ trả mỗi cặp `(region_code, region_name)` một lần:

```sql
SELECT region_code, region_name
FROM active_customers

UNION

SELECT region_code, region_name
FROM active_suppliers;
```

Nếu một vùng xuất hiện ở cả hai nguồn, kết quả chỉ giữ một dòng giống nhau. Cần xác nhận việc loại trùng trên cả mã và tên đúng với quy tắc nghiệp vụ. Nếu tên có thể khác cách viết hoặc collation không phân biệt hoa thường, cần xác định quy tắc chuẩn hóa trước.

`UNION` cũng hữu ích khi nhiều nhánh có thể tạo cùng một dòng do dữ liệu lặp nội bộ. Tuy nhiên, nếu mục tiêu thực sự là chọn một bản ghi đại diện theo khóa và ưu tiên bản ghi mới nhất, `UNION` không đủ vì nó không chọn dòng theo timestamp hay độ ưu tiên. Hãy dùng window function hoặc aggregate theo quy tắc xác định.

## 9. Thay OR bằng nhiều nhánh UNION: lợi ích và rủi ro

### 9.1. Khi các điều kiện độc lập có access path khác nhau

Một điều kiện `OR` trên hai cột có thể khiến bộ tối ưu chọn scan hoặc chiến lược bitmap/index combination. Trong một số tình huống, tách thành hai nhánh giúp mỗi nhánh dùng chỉ mục riêng:

```sql
SELECT customer_id, email, phone
FROM customers
WHERE email = :email

UNION

SELECT customer_id, email, phone
FROM customers
WHERE phone = :phone;
```

Mỗi nhánh có thể dùng chỉ mục trên `email` hoặc `phone`. `UNION` bảo đảm một khách hàng thỏa cả hai điều kiện chỉ xuất hiện một lần nếu toàn bộ các cột kết quả giống nhau.

Tuy nhiên, đây không phải cách viết mặc định tốt hơn `OR`. Optimizer có thể đã xử lý `OR` hiệu quả bằng bitmap OR, index merge hoặc một access path khác. Tách nhánh có thể khiến bảng bị đọc hai lần, làm tăng I/O hoặc tạo bước distinct tốn kém.

### 9.2. UNION ALL có thể nhân bản kết quả

Nếu thay `UNION` bằng `UNION ALL`, khách hàng có cả email và phone khớp sẽ xuất hiện hai lần. Điều đó chỉ đúng nếu ứng dụng muốn giữ hai lần xuất hiện tương ứng với hai điều kiện. Nếu yêu cầu là mỗi khách hàng một lần, `UNION ALL` thay đổi kết quả.

Có thể viết các nhánh loại trừ nhau để dùng `UNION ALL`:

```sql
SELECT customer_id, email, phone
FROM customers
WHERE email = :email

UNION ALL

SELECT customer_id, email, phone
FROM customers
WHERE phone = :phone
  AND (email <> :email OR email IS NULL);
```

Ví dụ này giả định `:email` là giá trị không NULL. Điều kiện loại trừ ở nhánh hai cần được thiết kế cẩn thận theo semantics NULL và kiểu so sánh. Với cột nullable, `email <> :email` một mình không giữ các dòng NULL vì kết quả là UNKNOWN; thêm `OR email IS NULL` giúp giữ các hàng có email NULL khi tham số email không NULL. Nếu tham số có thể NULL, phải viết điều kiện theo quy tắc NULL của nghiệp vụ hoặc giữ truy vấn `OR` ban đầu. Nếu có collation, kiểu tham số hoặc quy tắc chuẩn hóa khác nhau, phải xác nhận hai nhánh thực sự rời nhau.

Trong nhiều trường hợp, giữ nguyên `OR` dễ đọc và ít rủi ro hơn. Chỉ tách nhánh sau khi execution plan cho thấy lợi ích và phép viết lại đã được chứng minh tương đương.

### 9.3. So sánh kết quả trước và sau

Khi thay `OR` bằng `UNION` hoặc `UNION ALL`, kiểm tra:

1. Một hàng có thể thỏa đồng thời nhiều điều kiện không?
2. Định nghĩa duplicate dựa trên toàn bộ cột đầu ra hay khóa nghiệp vụ?
3. Có NULL trong các cột tham gia điều kiện loại trừ không?
4. Các nhánh có cùng kiểu và collation không?
5. Mỗi nhánh có dùng chỉ mục hiệu quả hay đọc lại cùng dữ liệu không?
6. Bước distinct có làm tăng CPU, memory grant hoặc temp I/O không?

## 10. Đẩy điều kiện vào từng nhánh

### 10.1. Lọc trước khi hợp nhất

Nếu mỗi nguồn có điều kiện riêng, hãy đặt điều kiện trong nhánh tương ứng để giảm số dòng đầu vào:

```sql
SELECT event_id, event_time, event_type
FROM live_events
WHERE event_time >= :from_time
  AND event_time <  :to_time
  AND severity >= :minimum_severity

UNION ALL

SELECT event_id, event_time, event_type
FROM archived_events
WHERE event_time >= :from_time
  AND event_time <  :to_time
  AND severity >= :minimum_severity;
```

Mỗi nhánh có thể dùng chỉ mục hoặc partition pruning riêng. Nếu bộ tối ưu có thể đẩy điều kiện chung xuống cả hai nhánh, nó có thể tự thực hiện; viết điều kiện rõ ràng trong nhánh cũng giúp người đọc thấy phạm vi lọc.

### 10.2. Điều kiện chung và điều kiện riêng

Một truy vấn có thể kết hợp điều kiện chung ở lớp ngoài với điều kiện riêng trong từng nhánh. Tuy nhiên, nếu điều kiện ngoài chỉ tham chiếu cột đầu ra và có thể được đẩy xuống an toàn, engine có thể thực hiện pushdown. Hãy kiểm tra execution plan thay vì nhân bản điều kiện một cách máy móc.

Nếu điều kiện được viết lại khác nhau ở hai nhánh, phải bảo đảm chúng tương đương về kiểu, timezone, collation và NULL. Ví dụ, lọc ngày theo timezone của ứng dụng ở một nhánh nhưng theo timezone session ở nhánh khác có thể tạo kết quả không nhất quán.

### 10.3. Giới hạn từng nhánh và giới hạn toàn cục

Có hai yêu cầu khác nhau:

- Lấy tối đa N dòng từ mỗi nguồn rồi hợp nhất.
- Hợp nhất mọi nguồn rồi lấy N dòng tốt nhất trên toàn bộ kết quả.

Yêu cầu thứ nhất cần giới hạn ở từng nhánh; yêu cầu thứ hai cần giới hạn ở lớp ngoài sau khi có thứ tự toàn cục. Có thể dùng top-N ở mỗi nhánh như một bước giảm dữ liệu khi chứng minh được đủ dòng ứng viên, nhưng phải có `ORDER BY` xác định và vẫn cần bước chọn top-N toàn cục.

## 11. UNION ALL với partition, archive và nhiều nguồn

### 11.1. Bảng partition

Một số hệ thống biểu diễn dữ liệu phân vùng bằng các nhánh scan và append/concatenate. Khi truy vấn bao phủ nhiều partition, engine có thể đọc các partition phù hợp rồi ghép dòng. Partition pruning giúp bỏ qua vùng không liên quan dựa trên điều kiện phân vùng.

Nếu các partition được thiết kế rời nhau theo khóa phân vùng, `UNION ALL` thường phản ánh đúng việc ghép dữ liệu. Nếu truy vấn tự viết nhiều nhánh thay cho một bảng partition, cần đảm bảo điều kiện mỗi nhánh không giao nhau hoặc chủ động giữ duplicate theo nghiệp vụ.

### 11.2. Bảng hiện tại và bảng lưu trữ

Một mô hình phổ biến lưu dữ liệu gần đây trong bảng `events_current` và dữ liệu cũ trong `events_archive`. Truy vấn hợp nhất có thể dùng `UNION ALL`:

```sql
SELECT event_id, event_time, payload_type
FROM events_current
WHERE event_time >= :from_time
  AND event_time <  :to_time

UNION ALL

SELECT event_id, event_time, payload_type
FROM events_archive
WHERE event_time >= :from_time
  AND event_time <  :to_time;
```

Điều kiện quan trọng là quy trình chuyển archive phải tránh để cùng một sự kiện đồng thời tồn tại trong hai bảng nếu ứng dụng không muốn hai lần xuất hiện. Nếu việc chuyển dữ liệu không nguyên tử hoặc có thời gian overlap, cần có khóa định danh và quy tắc loại trùng rõ ràng.

### 11.3. Nhiều database hoặc nguồn liên kết

Trong hệ thống liên kết nhiều database, `UNION ALL` có thể ghép kết quả từ nhiều nguồn. Chi phí có thể bao gồm network transfer, remote execution, serialization và chênh lệch latency giữa các nguồn. Đẩy điều kiện và chỉ chọn cột cần thiết xuống nguồn từ xa giúp giảm dữ liệu truyền về coordinator.

Nếu cần `UNION`, bước loại trùng có thể phải diễn ra sau khi dữ liệu từ các nguồn được chuyển về cùng một nơi, tạo chi phí mạng và bộ nhớ đáng kể. Hãy xem khả năng pushdown distinct đến từng nguồn, nhưng lưu ý loại trùng cục bộ chưa đủ để loại trùng giữa các nguồn.

## 12. UNION trong recursive CTE

Recursive CTE thường dùng một nhánh anchor và một nhánh recursive. Tùy hệ quản trị và cú pháp, phép kết hợp có thể là `UNION` hoặc `UNION ALL`.

- `UNION ALL` giữ mọi dòng được sinh ra qua các vòng lặp. Nếu quan hệ có chu trình và không có điều kiện dừng hoặc cơ chế phát hiện chu trình, đệ quy có thể chạy quá lâu hoặc chạm giới hạn recursion.
- `UNION` loại các dòng trùng theo toàn bộ danh sách cột của CTE, có thể giúp tránh lặp lại một trạng thái đã xuất hiện nếu dòng lặp giống hoàn toàn.

Ví dụ khái niệm tìm các node có thể đi tới trong đồ thị:

```sql
WITH RECURSIVE reachable(node_id) AS (
    SELECT :start_node
    UNION
    SELECT e.to_node
    FROM edges AS e
    JOIN reachable AS r
      ON e.from_node = r.node_id
)
SELECT node_id
FROM reachable;
```

Vì CTE chỉ chứa `node_id`, `UNION` có thể loại một node đã được phát hiện, giúp quá trình dừng khi tập node đạt trạng thái cố định trong hệ quản trị hỗ trợ semantics này. Nếu thêm `depth` hoặc `path` vào danh sách cột, cùng một `node_id` ở độ sâu khác nhau sẽ không còn là dòng trùng. Khi đó `UNION` không tự bảo đảm chặn chu trình.

Đối với truy vấn đệ quy, hãy thiết kế rõ điều kiện dừng, giới hạn độ sâu, visited set hoặc cú pháp `CYCLE` nếu hệ quản trị hỗ trợ. Không dùng `UNION` như cơ chế chống chu trình chung cho mọi recursive CTE.

## 13. Các phép toán tập hợp liên quan

SQL còn có `INTERSECT` để lấy dòng xuất hiện trong cả hai kết quả và `EXCEPT`/`MINUS` để lấy dòng có ở nhánh trái nhưng không có ở nhánh phải. Các phép này thường có semantics loại trùng mặc định; một số hệ quản trị hỗ trợ biến thể `ALL` để giữ multiplicity theo quy tắc riêng.

| Phép toán | Ý nghĩa khái niệm | Câu hỏi nghiệp vụ |
|---|---|---|
| `UNION` | Hợp hai kết quả, loại dòng trùng | Cần tập dòng duy nhất không? |
| `UNION ALL` | Ghép mọi lần xuất hiện | Có cần giữ multiplicity của từng nguồn không? |
| `INTERSECT` | Lấy dòng chung giữa các kết quả | Cần phần giao của hai nhóm dữ liệu không? |
| `EXCEPT`/`MINUS` | Lấy dòng có ở trái nhưng không có ở phải | Cần tìm phần chênh lệch hoặc bản ghi thiếu không? |

Tên cú pháp và hỗ trợ `ALL` khác nhau theo hệ quản trị. Những phép toán này cũng có thể cần sort/hash hoặc chiến lược tương đương để so sánh dòng. Hãy chọn theo ý nghĩa dữ liệu trước, rồi đo chi phí.

## 14. Quy trình chọn UNION hay UNION ALL

1. **Xác định ý nghĩa một dòng.** Một dòng đại diện cho sự kiện, bản ghi vật lý, khách hàng, khóa nghiệp vụ hay một cặp giá trị?
2. **Xác định multiplicity mong muốn.** Nếu cùng giá trị xuất hiện từ nhiều nguồn, cần giữ tất cả hay chỉ một lần?
3. **Kiểm tra miền dữ liệu giữa các nhánh.** Partition, khoảng thời gian, tenant hoặc khóa có bảo đảm không giao nhau không?
4. **Kiểm tra danh sách cột.** Các nhánh có cùng số cột, cùng thứ tự và kiểu tương thích không? Danh sách cột có đúng là tiêu chí xác định duplicate không?
5. **Kiểm tra NULL và collation.** Dòng chứa NULL hoặc chuỗi có quy tắc so sánh nào? Việc loại trùng có phù hợp yêu cầu không?
6. **Chọn phép toán theo semantics.** Dùng `UNION ALL` khi phải giữ mọi lần xuất hiện; dùng `UNION` khi cần loại dòng trùng trên toàn bộ projection.
7. **Đặt điều kiện ở đúng nhánh.** Lọc sớm và chỉ giữ cột cần thiết khi phép biến đổi bảo toàn kết quả.
8. **Đặt thứ tự ở đúng phạm vi.** Nếu cần thứ tự toàn cục, dùng `ORDER BY` sau phép toán tập hợp và thêm tie-breaker để thứ tự xác định.
9. **Đọc execution plan.** Tìm Concatenate/Append, Sort Distinct, HashAggregate, Unique, remote scan, memory grant và spill.
10. **Đo và đối chiếu kết quả.** So sánh actual rows, CPU, elapsed time, logical/physical reads, temp I/O và multiplicity của các dòng.

## 15. Đo hiệu năng và đọc execution plan

### 15.1. Các chỉ số nên thu thập

| Chỉ số | Điều cần quan sát |
|---|---|
| Estimated rows và actual rows từng nhánh | Bộ tối ưu dự đoán quy mô mỗi nguồn có chính xác không? |
| Rows trước và sau distinct | Có bao nhiêu dòng bị loại và tỷ lệ duplicate là bao nhiêu? |
| Row width | Các cột kết quả có rộng hơn cần thiết không? |
| Sort/hash operator | `UNION` dùng sort, hash hay chiến lược khác? |
| Memory grant/peak memory | Bước loại trùng cần bao nhiêu bộ nhớ? |
| Temp read/write hoặc spill | Sort/hash có vượt bộ nhớ và dùng vùng tạm không? |
| Logical/physical reads | Các nhánh đọc bao nhiêu trang và có cache hit không? |
| CPU và elapsed time | Chi phí tính toán và thời gian hoàn tất thay đổi thế nào? |
| Network bytes | Có truyền quá nhiều dữ liệu từ remote source không? |

### 15.2. So sánh có kiểm soát

Khi đánh giá `UNION` và `UNION ALL`, hãy dùng cùng dữ liệu, tham số, mức tải, cache state và danh sách cột. Hai câu lệnh có thể trả kết quả khác nhau nên không được so sánh tốc độ nếu semantics không tương đương.

Nếu dữ liệu thực sự không trùng và hai truy vấn có cùng kết quả, có thể đo cả hai để thấy chi phí distinct. Nếu dữ liệu có trùng và yêu cầu là loại trùng, `UNION ALL` không phải baseline hợp lệ trừ khi có bước loại trùng tương đương khác. Kiểm tra multiplicity bằng cách nhóm theo toàn bộ cột đầu ra và đếm số lần xuất hiện, hoặc dùng phép đối chiếu kết quả phù hợp.

### 15.3. Đọc dấu hiệu trong plan

- `Append`, `Concatenate` hoặc `Union All` thường cho biết các nhánh được ghép mà không có distinct toàn cục.
- `Sort` kèm chế độ distinct/unique có thể cho biết engine sắp xếp để loại trùng.
- `HashAggregate`, `Hash Match (Aggregate)` hoặc `Unique` có thể là bước giữ một đại diện cho mỗi dòng duy nhất.
- `Sort spill`, hash batch tăng hoặc temp I/O cho thấy bộ nhớ không đủ hoặc ước lượng chưa phù hợp.
- Số hàng ở từng nhánh lớn bất thường có thể báo hiệu điều kiện lọc chưa được đẩy xuống hoặc thống kê sai.

Tên toán tử chỉ là dấu hiệu; hãy xem properties, actual rows, loops, memory và I/O theo đúng định nghĩa của engine.

## 16. Ví dụ thực hành: hợp nhất giao dịch hiện tại và lưu trữ

Giả sử ứng dụng hiển thị lịch sử giao dịch từ bảng hiện tại và bảng archive. Hai bảng có cùng cấu trúc và `transaction_id` được bảo đảm duy nhất toàn hệ thống. Quy trình archive chỉ xóa bản ghi khỏi bảng hiện tại sau khi bản ghi đã được ghi bền vững vào archive.

Truy vấn có thể dùng:

```sql
SELECT transaction_id, account_id, occurred_at, amount
FROM current_transactions
WHERE account_id = :account_id
  AND occurred_at >= :from_time
  AND occurred_at <  :to_time

UNION ALL

SELECT transaction_id, account_id, occurred_at, amount
FROM archived_transactions
WHERE account_id = :account_id
  AND occurred_at >= :from_time
  AND occurred_at <  :to_time

ORDER BY occurred_at DESC, transaction_id DESC;
```

`UNION ALL` phù hợp nếu quy trình lưu trữ thật sự bảo đảm một giao dịch chỉ nằm ở một nguồn trong phạm vi đọc. Hai nhánh cùng lọc tài khoản và thời gian để giảm dữ liệu; chỉ chọn các cột ứng dụng cần. `ORDER BY` cuối bảo đảm thứ tự toàn cục, với `transaction_id` làm tie-breaker.

Nếu trong quá trình archive có một khoảng thời gian bản ghi tồn tại ở cả hai bảng, `UNION ALL` có thể trả hai lần. Có ba hướng xử lý tùy yêu cầu:

1. Thiết kế quy trình chuyển dữ liệu nguyên tử hoặc có trạng thái ownership để truy vấn chỉ đọc một bản sao.
2. Dùng `UNION` nếu toàn bộ dòng giống nhau và yêu cầu là loại các dòng trùng theo toàn bộ projection.
3. Dùng khóa `transaction_id` và quy tắc ưu tiên nguồn/phiên bản để chọn một bản ghi đại diện, chẳng hạn `ROW_NUMBER` theo thời điểm cập nhật.

Không mặc định `UNION` là cách sửa archive overlap đúng. Nếu hai bản ghi cùng `transaction_id` nhưng `amount` hoặc `occurred_at` khác nhau, `UNION` sẽ giữ cả hai vì chúng không phải dòng giống nhau. Khi đó cần quy tắc giải quyết xung đột theo khóa nghiệp vụ.

## 17. Những lỗi thường gặp

- **Dùng `UNION` theo thói quen:** tạo sort/hash distinct dù các nhánh đã rời nhau và cần giữ mọi dòng.
- **Dùng `UNION ALL` chỉ vì nhanh:** có thể làm kết quả lặp khi các nhánh giao nhau hoặc có duplicate nội bộ.
- **Hiểu nhầm duplicate theo khóa:** `UNION` so sánh toàn bộ cột đầu ra, không tự chọn một dòng theo khóa nghiệp vụ.
- **Dùng `SELECT *`:** có thể lệch thứ tự cột, thay đổi kiểu kết quả và làm bước distinct xử lý dữ liệu rộng.
- **Bỏ qua chuyển đổi kiểu:** các nhánh có kiểu khác nhau có thể gây cast, mất precision hoặc lỗi so sánh.
- **Bỏ qua collation:** hai chuỗi khác byte có thể được xem là giống hoặc khác tùy quy tắc so sánh.
- **Giả định NULL = NULL:** phép loại trùng xử lý NULL theo quy tắc riêng, không giống predicate equality thông thường.
- **Dựa vào thứ tự nhánh:** không có `ORDER BY` cuối thì thứ tự kết quả không được bảo đảm.
- **Đặt LIMIT sai phạm vi:** top-N từng nhánh và top-N toàn cục là hai yêu cầu khác nhau.
- **Thay OR bằng UNION ALL mà không xét overlap:** một dòng thỏa hai điều kiện có thể xuất hiện hai lần.
- **Dùng UNION để giải quyết xung đột archive:** các dòng khác nhau ở bất kỳ cột nào vẫn được giữ lại.
- **Coi CTE đệ quy với UNION là luôn chống chu trình:** nếu cột depth/path thay đổi, dòng lặp có thể không bị loại.
- **Chỉ đo thời gian:** bỏ qua số dòng bị loại, memory grant, spill, CPU và I/O của bước distinct.

## 18. Bài tập tự kiểm tra

**Bài 1.** Nhánh A trả `(1, 'PAID')` hai lần; nhánh B trả `(1, 'PAID')` một lần và `(2, 'OPEN')` một lần. `UNION ALL` và `UNION` trả về bao nhiêu dòng?

*Gợi ý:* `UNION ALL` trả bốn dòng. `UNION` trả hai dòng duy nhất vì loại tất cả lần xuất hiện trùng trên cả hai cột.

**Bài 2.** Bạn cần hợp nhất sự kiện từ bảng hiện tại và archive. Vì sao phải xác minh quy trình archive trước khi chọn `UNION ALL`?

*Gợi ý:* Trong giai đoạn chuyển dữ liệu, cùng sự kiện có thể tồn tại ở cả hai bảng. Nếu yêu cầu mỗi sự kiện một lần, cần bảo đảm miền dữ liệu rời nhau hoặc có cơ chế chọn bản ghi theo khóa.

**Bài 3.** Hai nhánh trả cùng `customer_id` nhưng khác `status`. `UNION` có gộp thành một dòng không?

*Gợi ý:* Không. Toàn bộ dòng khác nhau vì `status` khác. Nếu cần một dòng mỗi khách hàng, phải định nghĩa quy tắc chọn hoặc tổng hợp theo khóa.

**Bài 4.** Một truy vấn dùng `UNION ALL` để thay cho `WHERE email = :email OR phone = :phone`. Người dùng có thể xuất hiện hai lần trong trường hợp nào?

*Gợi ý:* Khi cùng một hàng thỏa cả hai điều kiện. Dùng `UNION` hoặc thiết kế hai nhánh loại trừ nhau nếu semantics yêu cầu mỗi hàng một lần; sau đó đo chi phí.

**Bài 5.** Execution plan của `UNION` có sort distinct và ghi nhiều dữ liệu tạm. Bạn sẽ điều tra gì?

*Gợi ý:* Kiểm tra số hàng và độ rộng đầu vào, tỷ lệ duplicate, cột nào thực sự cần để xác định dòng trùng, khả năng lọc/chiếu sớm, memory grant, spill, thống kê và liệu nghiệp vụ có thật sự cần loại trùng hay không.

**Bài 6.** Vì sao `ORDER BY` ở nhánh đầu không đủ để bảo đảm kết quả hợp nhất được sắp xếp?

*Gợi ý:* Phép toán tập hợp không bảo đảm thứ tự đầu ra. Đặt `ORDER BY` ở cuối biểu thức hợp nhất và thêm tie-breaker để có thứ tự xác định.

## 19. Ghi nhớ khi tối ưu

`UNION ALL` ghép mọi lần xuất hiện và thường tránh được công việc loại trùng; `UNION` trả về các dòng duy nhất theo toàn bộ danh sách cột, có thể cần sort hoặc hash trên tập kết quả kết hợp. Quyết định đúng bắt đầu từ semantics: dòng trùng có cần giữ không, các nhánh có giao nhau không, và một dòng được định nghĩa theo toàn bộ projection hay theo khóa nghiệp vụ.

Hãy thống nhất số lượng, thứ tự và kiểu cột giữa các nhánh; chú ý NULL, collation và chuyển đổi ngầm định; lọc và chiếu sớm khi an toàn; đặt `ORDER BY` ở cuối nếu cần thứ tự toàn cục. Sau đó đọc execution plan và đo số hàng, độ rộng, CPU, bộ nhớ, spill, I/O và thời gian. Chỉ chọn phép toán nhanh hơn khi kết quả vẫn giữ đúng multiplicity và ý nghĩa mà ứng dụng yêu cầu.

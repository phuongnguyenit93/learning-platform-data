# ORDER BY/LIMIT trong truy vấn tập hợp và phạm vi áp dụng

Khi ghép kết quả từ nhiều câu `SELECT`, ta thường cần sắp xếp hoặc chỉ lấy một số dòng đầu. Trong MySQL, `ORDER BY` và `LIMIT` có thể áp dụng cho toàn bộ kết quả tập hợp, hoặc áp dụng riêng cho từng nhánh `SELECT` nếu nhánh đó được đặt trong ngoặc. Đặt hai mệnh đề sai vị trí có thể làm truy vấn trả về số dòng khác hẳn yêu cầu nghiệp vụ.

Ví dụ, báo cáo cần 10 sự kiện mới nhất từ hai nguồn dữ liệu. Có hai yêu cầu khác nhau: lấy 10 sự kiện mới nhất sau khi ghép cả hai nguồn, hoặc lấy 10 sự kiện mới nhất từ mỗi nguồn rồi ghép lại. Cả hai đều dùng `UNION ALL`, `ORDER BY` và `LIMIT`, nhưng phạm vi áp dụng khác nhau.

Trong module **DATABASE_MYSQL**, cần hiểu ranh giới query block, quy tắc ngoặc, thứ tự kết quả, alias của tập kết quả và tính xác định của top-N để viết các truy vấn tập hợp đúng nghĩa.

## 1. Truy vấn tập hợp là gì?

Truy vấn tập hợp (set operation) kết hợp kết quả của hai hoặc nhiều query block. MySQL hỗ trợ các toán tử:

| Toán tử | Ý nghĩa | Phiên bản MySQL |
|---|---|---|
| `UNION` hoặc `UNION DISTINCT` | Ghép các dòng và loại bỏ dòng trùng | Có từ các phiên bản MySQL trước 8.0 |
| `UNION ALL` | Ghép các dòng và giữ nguyên dòng trùng | Có từ các phiên bản MySQL trước 8.0 |
| `INTERSECT` | Chỉ giữ các dòng xuất hiện ở cả hai kết quả | MySQL 8.0.31 trở lên |
| `EXCEPT` | Giữ các dòng ở kết quả bên trái nhưng không có ở kết quả bên phải | MySQL 8.0.31 trở lên |

Các query block trong một phép tập hợp phải trả về cùng số cột và các cột tương ứng phải có kiểu dữ liệu tương thích. Tên cột của kết quả tập hợp được lấy từ danh sách `SELECT` đầu tiên.

Ví dụ ghép khách hàng từ hai nguồn:

```sql
SELECT customer_id, full_name
FROM online_customers
UNION ALL
SELECT customer_id, full_name
FROM store_customers;
```

`UNION ALL` giữ các dòng trùng, kể cả khi cùng một khách hàng xuất hiện ở cả hai nguồn. Nếu dùng `UNION` (mặc định tương đương `UNION DISTINCT`), MySQL loại các dòng trùng theo toàn bộ các cột của kết quả.

## 2. ORDER BY và LIMIT ở cuối phép tập hợp áp dụng cho toàn bộ kết quả

Nếu đặt `ORDER BY` và `LIMIT` sau query block cuối cùng, các mệnh đề này áp dụng cho kết quả đã ghép:

```sql
SELECT order_id AS event_id, created_at AS event_time
FROM online_events
UNION ALL
SELECT event_id, created_at
FROM archived_events
ORDER BY event_time DESC, event_id DESC
LIMIT 10;
```

Trình tự ý nghĩa là:

1. Lấy các dòng từ `online_events`.
2. Lấy các dòng từ `archived_events`.
3. Ghép hai tập kết quả bằng `UNION ALL`.
4. Sắp xếp toàn bộ kết quả theo `event_time` giảm dần, sau đó theo `event_id` giảm dần.
5. Chỉ trả về 10 dòng đầu.

Kết quả là tối đa 10 sự kiện mới nhất tính trên cả hai nguồn. Nó không phải 10 dòng từ mỗi nguồn.

Với `UNION DISTINCT`, việc loại bỏ dòng trùng là một phần của phép tập hợp trước khi giới hạn kết quả cuối. Ví dụ:

```sql
SELECT product_id FROM online_products
UNION
SELECT product_id FROM store_products
ORDER BY product_id
LIMIT 20;
```

MySQL loại các `product_id` trùng giữa hai kết quả, sắp xếp tập giá trị còn lại rồi lấy tối đa 20 dòng.

## 3. ORDER BY và LIMIT riêng cho từng nhánh SELECT

Nếu muốn giới hạn từng nguồn trước khi ghép, hãy đặt mỗi query block trong ngoặc:

```sql
(SELECT order_id AS event_id, created_at AS event_time
 FROM online_events
 ORDER BY created_at DESC, order_id DESC
 LIMIT 10)
UNION ALL
(SELECT event_id, created_at
 FROM archived_events
 ORDER BY created_at DESC, event_id DESC
 LIMIT 10);
```

Mỗi nhánh chọn tối đa 10 dòng mới nhất từ nguồn của nó. Kết quả tập hợp có thể chứa tối đa 20 dòng.

Lưu ý: `ORDER BY` trong từng nhánh quyết định những dòng nào được giữ lại bởi `LIMIT`. Nó không bảo đảm thứ tự hiển thị cuối cùng của toàn bộ kết quả. Nếu cần kết quả cuối được sắp xếp, phải có thêm `ORDER BY` ở cấp ngoài cùng:

```sql
(SELECT order_id AS event_id, created_at AS event_time, 'online' AS source_name
 FROM online_events
 ORDER BY created_at DESC, order_id DESC
 LIMIT 10)
UNION ALL
(SELECT event_id, created_at, 'archive'
 FROM archived_events
 ORDER BY created_at DESC, event_id DESC
 LIMIT 10)
ORDER BY event_time DESC, source_name ASC, event_id DESC
LIMIT 10;
```

Truy vấn này thực hiện hai lần giới hạn:

- Mỗi nguồn chọn tối đa 10 sự kiện.
- Sau khi ghép tối đa 20 dòng, truy vấn ngoài sắp xếp chung và lấy tối đa 10 sự kiện mới nhất.

Thứ tự cục bộ và thứ tự toàn cục có nhiệm vụ khác nhau. Không bỏ `ORDER BY` ngoài cùng nếu ứng dụng cần một thứ tự kết quả cụ thể.

## 4. Không có ngoặc thì LIMIT không tự áp dụng cho từng nhánh

Hãy so sánh hai truy vấn.

**Lấy tối đa 5 dòng từ toàn bộ kết quả:**

```sql
SELECT order_id, created_at
FROM online_events
UNION ALL
SELECT event_id, created_at
FROM archived_events
ORDER BY created_at DESC
LIMIT 5;
```

**Lấy tối đa 5 dòng từ mỗi nhánh:**

```sql
(SELECT order_id, created_at
 FROM online_events
 ORDER BY created_at DESC, order_id DESC
 LIMIT 5)
UNION ALL
(SELECT event_id, created_at
 FROM archived_events
 ORDER BY created_at DESC, event_id DESC
 LIMIT 5);
```

Ở truy vấn thứ nhất, `LIMIT 5` nằm ở cấp phép tập hợp nên tổng số dòng trả về không vượt quá 5. Ở truy vấn thứ hai, mỗi nhánh có `LIMIT 5`, nên kết quả có thể có tối đa 10 dòng.

Ngoặc xác định phạm vi query block. Đây không chỉ là cách trình bày cho dễ đọc; nó làm thay đổi ý nghĩa của câu SQL.

## 5. ORDER BY trong một nhánh cần đi cùng LIMIT để chọn top-N

Trong một nhánh của `UNION`, `ORDER BY` không có `LIMIT` không bảo đảm thứ tự của kết quả cuối. Khi một nhánh không giới hạn dòng, thứ tự nội bộ của nó không có ý nghĩa đối với phép tập hợp và optimizer có thể loại bỏ bước sắp xếp không cần thiết.

Nếu mục tiêu là chọn các dòng mới nhất từ mỗi nguồn, hãy dùng `ORDER BY` cùng `LIMIT` bên trong ngoặc:

```sql
(SELECT order_id, created_at
 FROM online_events
 ORDER BY created_at DESC, order_id DESC
 LIMIT 100)
UNION ALL
(SELECT event_id, created_at
 FROM archived_events
 ORDER BY created_at DESC, event_id DESC
 LIMIT 100);
```

Nếu chỉ muốn sắp xếp tất cả kết quả, đặt `ORDER BY` sau phép tập hợp:

```sql
SELECT order_id, created_at FROM online_events
UNION ALL
SELECT event_id, created_at FROM archived_events
ORDER BY created_at DESC, order_id DESC;
```

Ví dụ cuối giả định cột thứ nhất của kết quả được đặt tên `order_id` theo nhánh đầu. Nếu tên cột không phù hợp, hãy đặt alias tường minh trong `SELECT` đầu tiên.

## 6. ORDER BY ở cấp ngoài dùng tên cột kết quả của SELECT đầu tiên

Trong một phép tập hợp, tên các cột kết quả được xác định từ danh sách `SELECT` đầu tiên. Vì vậy, `ORDER BY` toàn cục nên dùng tên cột hoặc alias xuất hiện ở nhánh đầu tiên.

```sql
SELECT
    order_id AS event_id,
    created_at AS event_time
FROM online_events
UNION ALL
SELECT
    event_id,
    created_at
FROM archived_events
ORDER BY event_time DESC, event_id DESC;
```

Ở đây, tên kết quả là `event_id` và `event_time` vì chúng được khai báo trong `SELECT` đầu tiên. Alias ở nhánh sau không quyết định tên cột kết quả.

Không dùng tên bảng nguồn để định danh cột trong `ORDER BY` toàn cục:

```sql
-- Không dùng qualifier của bảng nguồn ở ORDER BY của set result
SELECT order_id, created_at FROM online_events
UNION ALL
SELECT event_id, created_at FROM archived_events
ORDER BY online_events.created_at DESC;
```

Thay vào đó, dùng tên cột kết quả:

```sql
SELECT order_id AS event_id, created_at AS event_time
FROM online_events
UNION ALL
SELECT event_id, created_at
FROM archived_events
ORDER BY event_time DESC;
```

Nếu cần sắp xếp theo một biểu thức, hãy đưa biểu thức đó thành cột kết quả ở tất cả các nhánh với kiểu tương thích, hoặc bọc phép tập hợp trong derived table rồi sắp xếp ở query ngoài.

## 7. ORDER BY và LIMIT phải có thứ tự xác định

`LIMIT` mà không có `ORDER BY` chọn một tập dòng không có thứ tự được bảo đảm. Hai lần chạy cùng câu SQL có thể trả các dòng khác nhau khi dữ liệu, index, kế hoạch thực thi hoặc trạng thái máy chủ thay đổi.

Không nên viết truy vấn top-N như sau nếu nghiệp vụ cần những bản ghi mới nhất:

```sql
SELECT order_id, created_at
FROM orders
LIMIT 10;
```

Hãy xác định tiêu chí sắp xếp:

```sql
SELECT order_id, created_at
FROM orders
ORDER BY created_at DESC, order_id DESC
LIMIT 10;
```

Nếu nhiều dòng có cùng `created_at`, thêm một khóa duy nhất như `order_id` để tạo thứ tự ổn định. Với tập hợp nhiều nguồn, có thể cần thêm `source_name` nếu ID chỉ duy nhất trong từng nguồn.

Ví dụ:

```sql
SELECT order_id AS event_id, created_at AS event_time, 'online' AS source_name
FROM online_events
UNION ALL
SELECT event_id, created_at, 'archive'
FROM archived_events
ORDER BY event_time DESC, source_name ASC, event_id DESC
LIMIT 50;
```

Nếu cặp `(source_name, event_id)` là duy nhất, thứ tự cuối cùng được xác định ngay cả khi nhiều sự kiện có cùng thời điểm.

## 8. LIMIT với OFFSET và phân trang

MySQL hỗ trợ hai dạng:

```sql
LIMIT row_count OFFSET offset
```

hoặc:

```sql
LIMIT offset, row_count
```

Ví dụ lấy trang thứ ba, mỗi trang 20 dòng:

```sql
SELECT event_id, event_time
FROM (
    SELECT order_id AS event_id, created_at AS event_time
    FROM online_events
    UNION ALL
    SELECT event_id, created_at
    FROM archived_events
) AS all_events
ORDER BY event_time DESC, event_id DESC
LIMIT 20 OFFSET 40;
```

Đây là phân trang trên kết quả đã ghép. `OFFSET 40` bỏ qua 40 dòng đầu của thứ tự toàn cục rồi lấy 20 dòng tiếp theo.

Với offset lớn, MySQL vẫn phải tìm và bỏ qua các dòng trước offset, nên truy vấn có thể chậm khi dữ liệu tăng. Nếu có lượng dữ liệu lớn và thứ tự ổn định, hãy cân nhắc keyset pagination: dùng giá trị của dòng cuối trang trước làm mốc cho trang kế tiếp.

Ví dụ minh họa keyset pagination cho thứ tự giảm dần theo `(event_time, event_id)`:

```sql
SELECT event_id, event_time
FROM (
    SELECT order_id AS event_id, created_at AS event_time
    FROM online_events
    UNION ALL
    SELECT event_id, created_at
    FROM archived_events
) AS all_events
WHERE (event_time, event_id) < (?, ?)
ORDER BY event_time DESC, event_id DESC
LIMIT 20;
```

Hai tham số là `event_time` và `event_id` của dòng cuối trang trước. Cách này phù hợp khi cặp sắp xếp tạo thứ tự duy nhất và dữ liệu không thay đổi theo cách phá vỡ quy tắc phân trang. Với set result lớn, cần kiểm tra kế hoạch thực thi vì derived table và phép tập hợp vẫn có thể cần materialization hoặc sort.

## 9. UNION DISTINCT và UNION ALL làm thay đổi ý nghĩa LIMIT

`UNION` mặc định loại bỏ các dòng trùng; `UNION ALL` giữ tất cả. Điều này ảnh hưởng đến số dòng còn lại trước khi áp dụng `LIMIT` toàn cục.

```sql
SELECT customer_id FROM online_customers
UNION
SELECT customer_id FROM store_customers
ORDER BY customer_id
LIMIT 100;
```

Truy vấn trên trả tối đa 100 `customer_id` duy nhất. Nếu dùng `UNION ALL`, một khách hàng xuất hiện ở cả hai nguồn có thể xuất hiện hai lần và chiếm hai vị trí trong 100 dòng.

Khi đặt `LIMIT` bên trong từng nhánh của `UNION DISTINCT`, mỗi nhánh bị cắt trước khi loại trùng ở kết quả tập hợp. Điều này có thể làm kết quả cuối có ít dòng hơn giới hạn toàn cục hoặc bỏ sót một giá trị lẽ ra nằm trong top-N của toàn bộ dữ liệu. Chỉ dùng local limit khi nghiệp vụ thật sự yêu cầu top-N riêng cho từng nguồn.

## 10. ORDER BY/LIMIT với INTERSECT và EXCEPT

MySQL hỗ trợ `INTERSECT` và `EXCEPT` từ MySQL 8.0.31. Phạm vi của `ORDER BY` và `LIMIT` vẫn theo nguyên tắc query expression:

- Mệnh đề ở cuối phép tập hợp áp dụng cho toàn bộ kết quả.
- Muốn giới hạn từng toán hạng trước khi thực hiện phép tập hợp, đặt query block tương ứng trong ngoặc.
- Muốn sắp xếp kết quả cuối, đặt `ORDER BY` ở ngoài cùng.

Ví dụ tìm 20 sản phẩm có trong cả hai danh sách và sắp xếp theo mã:

```sql
SELECT product_id FROM current_catalog
INTERSECT
SELECT product_id FROM promoted_products
ORDER BY product_id
LIMIT 20;
```

Ví dụ tìm sản phẩm hiện có nhưng không nằm trong danh sách ngừng kinh doanh:

```sql
SELECT product_id FROM current_catalog
EXCEPT
SELECT product_id FROM discontinued_products
ORDER BY product_id
LIMIT 50;
```

Nếu giới hạn từng toán hạng trước khi `INTERSECT` hoặc `EXCEPT`, tập đầu vào của phép toán đã thay đổi. Điều đó chỉ đúng khi yêu cầu nghiệp vụ muốn so sánh các tập con đã giới hạn.

Trong MySQL, `INTERSECT` có độ ưu tiên cao hơn `UNION` và `EXCEPT`. Khi kết hợp nhiều toán tử, hãy dùng ngoặc để thể hiện ý định thay vì dựa vào việc người đọc nhớ thứ tự ưu tiên. Cú pháp và các biến thể `ALL`/`DISTINCT` cần được kiểm tra theo phiên bản server.

## 11. Đưa cột sắp xếp phụ ra ngoài kết quả hiển thị

`ORDER BY` toàn cục của phép tập hợp sắp xếp theo các cột của kết quả set operation. Nếu cần sắp xếp theo một biểu thức không muốn trả về cho ứng dụng, có thể bọc phép tập hợp trong derived table:

```sql
SELECT event_id, event_time
FROM (
    SELECT
        order_id AS event_id,
        created_at AS event_time,
        priority
    FROM online_events
    UNION ALL
    SELECT
        event_id,
        created_at,
        priority
    FROM archived_events
) AS all_events
ORDER BY priority DESC, event_time DESC, event_id DESC
LIMIT 20;
```

Nếu không muốn trả `priority` trong kết quả, query ngoài chỉ chọn `event_id` và `event_time` nhưng vẫn có thể dùng cột của derived table để sắp xếp:

```sql
SELECT event_id, event_time
FROM (
    SELECT order_id AS event_id, created_at AS event_time, priority
    FROM online_events
    UNION ALL
    SELECT event_id, created_at, priority
    FROM archived_events
) AS all_events
ORDER BY priority DESC, event_time DESC, event_id DESC
LIMIT 20;
```

Cột `priority` phải có mặt trong kết quả bên trong để query ngoài nhìn thấy. Tên và thứ tự cột trong hai nhánh vẫn phải tương thích.

## 12. Hiệu năng và kế hoạch thực thi

Một phép tập hợp có thể phải đọc nhiều nguồn, loại trùng, materialize kết quả trung gian và sắp xếp toàn bộ tập. `LIMIT` toàn cục không đảm bảo MySQL chỉ đọc đúng số dòng cần trả về; để xác định chi phí, hãy kiểm tra kế hoạch.

Ví dụ:

```sql
EXPLAIN
SELECT order_id AS event_id, created_at AS event_time
FROM online_events
UNION ALL
SELECT event_id, created_at
FROM archived_events
ORDER BY event_time DESC, event_id DESC
LIMIT 20;
```

Trên MySQL 8.0.18 trở lên, có thể dùng `EXPLAIN ANALYZE` để quan sát thời gian và số dòng thực tế. Lệnh này thực thi truy vấn, vì vậy hãy chạy trên dữ liệu thử nghiệm hoặc trong điều kiện tải đã được kiểm soát.

Một số hướng tối ưu:

- Đánh index phù hợp cho điều kiện lọc và các cột sắp xếp ở từng nguồn.
- Dùng `UNION ALL` nếu không cần loại bỏ dòng trùng, tránh chi phí deduplication.
- Nếu chỉ cần top-N mỗi nguồn, đặt `ORDER BY` và `LIMIT` trong từng nhánh có ngoặc để giảm số dòng đưa vào phép tập hợp.
- Nếu cần top-N toàn cục, giữ `ORDER BY`/`LIMIT` ở ngoài cùng và kiểm tra kế hoạch sort/materialization.
- Tránh `SELECT *`; chỉ đưa vào set operation những cột cần thiết, cộng với các khóa sắp xếp cần dùng.
- Với phân trang sâu, cân nhắc keyset pagination thay cho `OFFSET` lớn.

Không giả định `LIMIT` sẽ tự làm truy vấn nhanh. Nếu server vẫn cần đọc, khử trùng hoặc sắp xếp một lượng dữ liệu lớn trước khi biết 20 dòng đầu, chi phí vẫn có thể cao.

## 13. Checklist xác định phạm vi ORDER BY/LIMIT

Trước khi hoàn thiện truy vấn tập hợp, hãy trả lời:

1. `ORDER BY` đang nằm trong một query block có ngoặc hay ở cuối toàn bộ set operation?
2. `LIMIT` cần áp dụng cho từng nguồn hay tổng số dòng sau khi ghép?
3. Nếu dùng top-N từng nguồn, thứ tự cục bộ có đủ tie-breaker duy nhất chưa?
4. Kết quả cuối có cần `ORDER BY` riêng để bảo đảm thứ tự hiển thị không?
5. `ORDER BY` toàn cục đang dùng tên cột/alias của kết quả từ `SELECT` đầu tiên chưa?
6. Có dùng qualifier của bảng nguồn ở cấp set result không?
7. Dùng `UNION` hay `UNION ALL` có đúng yêu cầu giữ/loại dòng trùng không?
8. Nếu có `INTERSECT`/`EXCEPT`, phiên bản MySQL có hỗ trợ không và ngoặc đã làm rõ thứ tự phép toán chưa?
9. `LIMIT` có `ORDER BY` ổn định để tránh chọn dòng tùy ý không?
10. `EXPLAIN` hoặc `EXPLAIN ANALYZE` cho thấy sort, materialization và số dòng phù hợp không?

## 14. Bài tập thực hành

Giả sử có hai bảng `online_events(order_id, created_at, event_type)` và `archived_events(event_id, created_at, event_type)`.

1. Dùng `UNION ALL` để ghép toàn bộ sự kiện từ hai bảng.
2. Thêm `ORDER BY` và `LIMIT 10` ở cuối để lấy 10 sự kiện mới nhất trên cả hai nguồn.
3. Bọc mỗi `SELECT` trong ngoặc và đặt `ORDER BY ... LIMIT 10` bên trong để lấy tối đa 10 dòng từ mỗi nguồn.
4. Thêm `ORDER BY` ngoài cùng và `LIMIT 10` để lấy 10 dòng mới nhất trong tập tối đa 20 dòng vừa ghép.
5. Thay `UNION ALL` bằng `UNION`; tạo dữ liệu trùng và so sánh kết quả.
6. Đổi alias ở `SELECT` đầu tiên rồi dùng alias đó trong `ORDER BY` toàn cục; thử dùng tên bảng nguồn và quan sát lỗi.
7. Bỏ `ORDER BY` khỏi truy vấn có `LIMIT`, chạy nhiều lần và giải thích vì sao tập dòng không được bảo đảm.
8. Nếu dùng MySQL 8.0.31+, thử `INTERSECT` và `EXCEPT` với `ORDER BY`/`LIMIT` ở cấp ngoài cùng.
9. Dùng `EXPLAIN` để so sánh truy vấn top-N toàn cục với truy vấn giới hạn top-N riêng từng nguồn.

Bạn hoàn thành bài khi có thể xác định chính xác `ORDER BY` và `LIMIT` đang tác động lên từng nhánh hay toàn bộ kết quả, chọn đúng `UNION`/`UNION ALL`, đặt ngoặc đúng vị trí và tạo thứ tự top-N ổn định. Hãy diễn đạt phạm vi bằng cấu trúc query block rõ ràng để kết quả SQL luôn khớp với yêu cầu báo cáo.

# MATCH_RECOGNIZE và nhận dạng mẫu theo chuỗi sự kiện trong Oracle Database

## 1. Khi câu hỏi SQL không chỉ là “lọc dòng nào?”

Nhiều bài toán dữ liệu cần nhận diện **một chuỗi sự kiện theo thứ tự**, thay vì chỉ tìm một row thỏa điều kiện độc lập. Ví dụ:

- Một tài khoản bắt đầu giao dịch, thực hiện nhiều lần thanh toán, rồi kết thúc.
- Giá cổ phiếu tăng liên tiếp trong một số phiên, sau đó giảm.
- Một cảm biến vượt ngưỡng ba lần trước khi trở về vùng bình thường.
- Một đơn hàng chuyển qua các trạng thái CREATED → PAID → SHIPPED.
- Phát hiện chuỗi đăng nhập thất bại rồi thành công.
- Tìm các phiên hoạt động gồm một sự kiện bắt đầu và một sự kiện kết thúc.

Có thể giải quyết một số trường hợp bằng self join, analytic functions, correlated subquery hoặc PL/SQL. Nhưng khi quy tắc được diễn đạt tự nhiên thành **mẫu trên một chuỗi row**, câu SQL có thể dài và khó đọc.

Oracle cung cấp mệnh đề **`MATCH_RECOGNIZE`** để nhận dạng mẫu dòng (row pattern matching). Ta khai báo:

1. Các dòng thuộc cùng một chuỗi bằng `PARTITION BY`.
2. Thứ tự sự kiện bằng `ORDER BY`.
3. Mẫu cần tìm bằng `PATTERN`.
4. Điều kiện để một dòng được gán vào biến mẫu bằng `DEFINE`.
5. Giá trị muốn xuất ra bằng `MEASURES`.
6. Cách tiếp tục tìm mẫu tiếp theo bằng `AFTER MATCH SKIP`.

`MATCH_RECOGNIZE` được giới thiệu trong Oracle Database 12c và có trong Oracle Database 19c. Bài này dùng cú pháp 19c.

## 2. Ý tưởng cốt lõi: xem dữ liệu như một chuỗi

Giả sử bảng giao dịch chứa:

| ACCOUNT_ID | EVENT_TIME | EVENT_TYPE | AMOUNT |
| ---: | --- | --- | ---: |
| 10 | 09:00 | START | NULL |
| 10 | 09:10 | PAYMENT | 100 |
| 10 | 09:20 | PAYMENT | 50 |
| 10 | 09:30 | CLOSE | NULL |
| 10 | 10:00 | START | NULL |
| 10 | 10:05 | PAYMENT | 30 |
| 10 | 10:15 | CLOSE | NULL |

Mục tiêu là tìm từng phiên có cấu trúc:

~~~text
START → PAYMENT (zero or more) → CLOSE
~~~

Ta có thể đặt tên các loại dòng trong mẫu:

- `S`: dòng bắt đầu phiên.
- `P`: dòng thanh toán.
- `C`: dòng kết thúc phiên.

Mẫu được viết:

~~~sql
PATTERN (S P* C)
~~~

Trong đó `P*` có nghĩa là **không hoặc nhiều** dòng `P`. Một phiên có thể có nhiều lần thanh toán, hoặc không có lần thanh toán nào.

Sơ đồ:

~~~text
Chuỗi row theo thời gian:

START  PAYMENT  PAYMENT  CLOSE  START  PAYMENT  CLOSE
  S       P        P       C      S       P       C
  └──────────── MATCH 1 ────────┘  └── MATCH 2 ───┘
~~~

Điểm khác biệt với `WHERE` thông thường là một dòng được xét trong **ngữ cảnh vị trí của nó trong mẫu**, và mẫu được khớp trên nhiều dòng theo thứ tự. Đây là công cụ phân tích chuỗi sự kiện, không chỉ là một phép lọc độc lập trên từng row.

## 3. Khung cú pháp MATCH_RECOGNIZE

Cấu trúc tổng quát:

~~~sql
SELECT ...
FROM source_table
MATCH_RECOGNIZE (
    [PARTITION BY partition_column [, ...]]
    [ORDER BY sort_column [ASC | DESC] [NULLS FIRST | NULLS LAST] [, ...]]
    [MEASURES measure_expression AS alias [, ...]]
    [ONE ROW PER MATCH | ALL ROWS PER MATCH]
    [AFTER MATCH SKIP ...]
    PATTERN (pattern_expression)
    [SUBSET ...]
    [DEFINE variable_condition [, ...]]
) pattern_result
~~~

Các phần có vai trò riêng:

| Phần | Câu hỏi được trả lời |
| --- | --- |
| `PARTITION BY` | Những dòng nào thuộc cùng một chuỗi độc lập? |
| `ORDER BY` | Thứ tự các sự kiện trong chuỗi là gì? |
| `PATTERN` | Cấu trúc chuỗi cần tìm là gì? |
| `DEFINE` | Điều kiện để dòng hiện tại khớp một pattern variable là gì? |
| `MEASURES` | Khi tìm được mẫu, cần tính và xuất thông tin nào? |
| `ONE ROW PER MATCH` / `ALL ROWS PER MATCH` | Mỗi match tạo một dòng tổng hợp hay trả lại từng dòng tham gia? |
| `AFTER MATCH SKIP` | Bắt đầu tìm match kế tiếp từ vị trí nào? |
| `SUBSET` | Gom nhiều pattern variable thành một nhóm logic để dùng trong measure/điều kiện? |

`PARTITION BY`, `ORDER BY`, `MEASURES`, `PATTERN` và `DEFINE` là những thành phần thường gặp. Đối với chuỗi sự kiện, hãy khai báo `ORDER BY` rõ ràng; thứ tự vật lý của table không phải thứ tự sự kiện.

## 4. Ví dụ đầu tiên: tìm phiên START, PAYMENT, CLOSE

### 4.1. Dữ liệu nguồn trong CTE

Ví dụ tự chứa dưới đây không cần tạo bảng:

~~~sql
WITH event_log AS (
    SELECT 10 AS account_id,
           101 AS event_id,
           TIMESTAMP '2026-11-14 09:00:00' AS event_time,
           'START' AS event_type,
           CAST(NULL AS NUMBER) AS amount
    FROM dual
    UNION ALL
    SELECT 10, 102, TIMESTAMP '2026-11-14 09:10:00',
           'PAYMENT', 100 FROM dual
    UNION ALL
    SELECT 10, 103, TIMESTAMP '2026-11-14 09:20:00',
           'PAYMENT', 50 FROM dual
    UNION ALL
    SELECT 10, 104, TIMESTAMP '2026-11-14 09:30:00',
           'CLOSE', CAST(NULL AS NUMBER) FROM dual
    UNION ALL
    SELECT 10, 105, TIMESTAMP '2026-11-14 10:00:00',
           'START', CAST(NULL AS NUMBER) FROM dual
    UNION ALL
    SELECT 10, 106, TIMESTAMP '2026-11-14 10:05:00',
           'PAYMENT', 30 FROM dual
    UNION ALL
    SELECT 10, 107, TIMESTAMP '2026-11-14 10:15:00',
           'CLOSE', CAST(NULL AS NUMBER) FROM dual
)
SELECT *
FROM event_log
ORDER BY account_id, event_time, event_id;
~~~

Trong dữ liệu này có hai phiên của tài khoản 10. `EVENT_ID` là khóa duy nhất giúp phân xử nếu hai sự kiện có cùng timestamp.

### 4.2. Câu MATCH_RECOGNIZE

~~~sql
WITH event_log AS (
    SELECT 10 account_id, 101 event_id,
           TIMESTAMP '2026-11-14 09:00:00' event_time,
           'START' event_type, CAST(NULL AS NUMBER) amount
    FROM dual
    UNION ALL
    SELECT 10, 102, TIMESTAMP '2026-11-14 09:10:00',
           'PAYMENT', 100 FROM dual
    UNION ALL
    SELECT 10, 103, TIMESTAMP '2026-11-14 09:20:00',
           'PAYMENT', 50 FROM dual
    UNION ALL
    SELECT 10, 104, TIMESTAMP '2026-11-14 09:30:00',
           'CLOSE', CAST(NULL AS NUMBER) FROM dual
    UNION ALL
    SELECT 10, 105, TIMESTAMP '2026-11-14 10:00:00',
           'START', CAST(NULL AS NUMBER) FROM dual
    UNION ALL
    SELECT 10, 106, TIMESTAMP '2026-11-14 10:05:00',
           'PAYMENT', 30 FROM dual
    UNION ALL
    SELECT 10, 107, TIMESTAMP '2026-11-14 10:15:00',
           'CLOSE', CAST(NULL AS NUMBER) FROM dual
)
SELECT account_id,
       match_no,
       started_at,
       closed_at,
       payment_count,
       total_paid
FROM event_log
MATCH_RECOGNIZE (
    PARTITION BY account_id
    ORDER BY event_time, event_id
    MEASURES
        MATCH_NUMBER() AS match_no,
        FIRST(S.event_time) AS started_at,
        LAST(C.event_time) AS closed_at,
        COUNT(P.event_id) AS payment_count,
        NVL(SUM(P.amount), 0) AS total_paid
    ONE ROW PER MATCH
    AFTER MATCH SKIP PAST LAST ROW
    PATTERN (S P* C)
    DEFINE
        S AS S.event_type = 'START',
        P AS P.event_type = 'PAYMENT',
        C AS C.event_type = 'CLOSE'
) mr
ORDER BY account_id, match_no;
~~~

Kết quả logic:

| ACCOUNT_ID | MATCH_NO | STARTED_AT | CLOSED_AT | PAYMENT_COUNT | TOTAL_PAID |
| ---: | ---: | --- | --- | ---: | ---: |
| 10 | 1 | 09:00 | 09:30 | 2 | 150 |
| 10 | 2 | 10:00 | 10:15 | 1 | 30 |

### 4.3. Đọc từng thành phần

- `PARTITION BY account_id`: mỗi tài khoản có một chuỗi độc lập. Mẫu không đi từ tài khoản này sang tài khoản khác.
- `ORDER BY event_time, event_id`: xử lý sự kiện theo thời gian; ID là tie-breaker nếu timestamp trùng.
- `PATTERN (S P* C)`: một dòng START, không hoặc nhiều PAYMENT, rồi một dòng CLOSE.
- `DEFINE`: chỉ định nghĩa loại row nào có thể khớp `S`, `P`, `C`.
- `MEASURES`: xuất số thứ tự match, thời điểm bắt đầu/kết thúc, số thanh toán và tổng tiền.
- `ONE ROW PER MATCH`: mỗi phiên được gom thành một dòng output.
- `AFTER MATCH SKIP PAST LAST ROW`: sau khi tìm xong một phiên, bắt đầu tìm tiếp sau dòng cuối của phiên vừa khớp.

`FIRST(S.event_time)` lấy thời điểm của dòng đầu tiên được gán cho biến `S` trong match. `LAST(C.event_time)` lấy thời điểm của dòng cuối được gán cho `C`. `COUNT(P.event_id)` đếm số dòng thanh toán; `SUM(P.amount)` tính tổng tiền từ các dòng `P`.

### 4.4. Vì sao P* cho phép phiên không có thanh toán?

`*` có nghĩa **zero or more**. Nếu dữ liệu có:

~~~text
START → CLOSE
~~~

thì vẫn khớp `S P* C` với `P*` nhận zero row. Trong trường hợp đó `COUNT(P.event_id)` là 0; `SUM(P.amount)` là NULL theo semantics aggregate, nên ví dụ dùng `NVL(..., 0)` để hiển thị tổng bằng 0.

Nếu nghiệp vụ bắt buộc phải có ít nhất một payment, đổi `P*` thành `P+`:

~~~sql
PATTERN (S P+ C)
~~~

`+` yêu cầu một hoặc nhiều dòng `P`.

## 5. PARTITION BY và ORDER BY xác định chuỗi sự kiện

### 5.1. PARTITION BY

`PARTITION BY` chia nguồn dữ liệu thành các nhóm độc lập. Mỗi partition được xử lý như một chuỗi riêng.

Ví dụ:

~~~sql
PARTITION BY account_id
ORDER BY event_time, event_id
~~~

nghĩa là:

- Sắp xếp sự kiện trong từng tài khoản.
- Một pattern không thể bắt đầu ở tài khoản 10 rồi kết thúc ở tài khoản 20.
- `MATCH_NUMBER()` được đánh số trong phạm vi partition.

Nếu muốn nhận dạng theo thiết bị và ngày, có thể phân vùng theo cả hai:

~~~sql
PARTITION BY device_id, TRUNC(event_time)
ORDER BY event_time, event_id
~~~

Hãy cân nhắc kiểu dữ liệu và timezone của `event_time` trước khi chia theo ngày. `TRUNC` trên timestamp và quy tắc ngày theo session có thể không phản ánh ngày nghiệp vụ mong muốn nếu dữ liệu có timezone. Với hệ thống đa múi giờ, xác định rõ ngày theo UTC hay theo múi giờ của khách hàng.

### 5.2. ORDER BY

Pattern matching cần một thứ tự có nghĩa. Nếu chỉ:

~~~sql
ORDER BY event_time
~~~

và hai row có cùng `EVENT_TIME`, thứ tự giữa chúng không được bảo đảm. Khi thứ tự trùng timestamp ảnh hưởng việc nhận dạng mẫu, thêm khóa duy nhất:

~~~sql
ORDER BY event_time, event_id
~~~

Nếu nghiệp vụ quy định thứ tự ưu tiên sự kiện cùng thời điểm, có thể dùng biểu thức phân xử riêng:

~~~sql
ORDER BY event_time,
         CASE event_type
           WHEN 'START' THEN 1
           WHEN 'PAYMENT' THEN 2
           WHEN 'CLOSE' THEN 3
           ELSE 9
         END,
         event_id
~~~

Chỉ dùng thứ tự này nếu nó phản ánh quy tắc nghiệp vụ. Không tự ý sắp START trước CLOSE chỉ để query khớp được mẫu.

### 5.3. Thứ tự bên trong MATCH_RECOGNIZE không thay thế ORDER BY ngoài cùng

`ORDER BY` trong `MATCH_RECOGNIZE` xác định thứ tự dùng để **nhận dạng mẫu**. Nếu ứng dụng cần thứ tự trình bày của kết quả, vẫn khai báo `ORDER BY` ở query ngoài:

~~~sql
SELECT account_id, match_no, started_at, closed_at
FROM event_log
MATCH_RECOGNIZE (...)
ORDER BY account_id, match_no;
~~~

Không suy rằng output tự có thứ tự chỉ vì đầu vào đã được sắp trong row pattern clause.

## 6. PATTERN: ngôn ngữ mô tả cấu trúc chuỗi

`PATTERN` dùng các pattern variable và toán tử để mô tả trình tự. Tên biến thường viết hoa để dễ đọc, ví dụ `A`, `B`, `START_EVT`, `PAYMENT_EVT`.

### 6.1. Nối tiếp (concatenation)

~~~sql
PATTERN (A B C)
~~~

Yêu cầu một dòng khớp `A`, ngay sau đó một dòng khớp `B`, rồi một dòng khớp `C`.

Ví dụ trạng thái đơn hàng:

~~~text
CREATED → PAID → SHIPPED
~~~

### 6.2. Quantifier: số lần xuất hiện

| Ký hiệu | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `?` | Zero hoặc một lần | `A?` |
| `*` | Zero hoặc nhiều lần | `A*` |
| `+` | Một hoặc nhiều lần | `A+` |
| `{m}` | Chính xác m lần | `A{3}` |
| `{m,}` | Ít nhất m lần | `A{2,}` |
| `{m,n}` | Từ m đến n lần | `A{2,5}` |

Ví dụ:

~~~sql
PATTERN (S P{2,4} C)
~~~

Một START, từ hai đến bốn PAYMENT, rồi CLOSE.

~~~sql
PATTERN (A B? C)
~~~

Một A, tùy chọn một B, rồi C.

### 6.3. Alternation: một trong nhiều nhánh

~~~sql
PATTERN (START (PAYMENT | REFUND)+ END)
~~~

Sau START có một hoặc nhiều dòng PAYMENT hoặc REFUND, rồi END.

Dấu `|` là phép lựa chọn nhánh. Dùng ngoặc để làm rõ phạm vi:

~~~sql
PATTERN ((A B) | (C D))
~~~

Mẫu trên chấp nhận chuỗi A rồi B, hoặc C rồi D.

### 6.4. Grouping

Ngoặc nhóm cho phép áp dụng quantifier lên cả chuỗi:

~~~sql
PATTERN (START (ITEM PAYMENT)+ CLOSE)
~~~

Sau START, có một hoặc nhiều cặp ITEM rồi PAYMENT, cuối cùng CLOSE.

### 6.5. Greedy quantifier

Các quantifier thông thường có tính **greedy**: cố gắng khớp nhiều lần nhất có thể mà vẫn cho phép phần còn lại của pattern hoàn thành.

Ví dụ:

~~~sql
PATTERN (A B* C)
~~~

`B*` cố gắng nhận nhiều dòng B liên tiếp nhất trước khi C được khớp. Nếu pattern phức tạp có nhiều nhánh/quantifier, tính greedy và việc backtrack có thể ảnh hưởng cách phân chia các dòng vào biến.

Khi quy tắc nghiệp vụ yêu cầu dừng tại sự kiện cụ thể, hãy viết điều kiện `DEFINE` cho rõ. Đừng dựa vào việc một quantifier tự “đoán” ranh giới phiên.

### 6.6. Anchor đầu và cuối partition

Hai anchor:

- `^`: vị trí đầu partition.
- `$`: vị trí cuối partition.

Ví dụ:

~~~sql
PATTERN (^ A+ $)
~~~

Mẫu yêu cầu toàn bộ partition gồm một hoặc nhiều dòng khớp A. Nó không chỉ tìm một đoạn con nằm giữa partition.

Anchor hữu ích khi yêu cầu là “chuỗi phải bắt đầu ở sự kiện đầu tiên” hoặc “chuỗi phải kết thúc ở sự kiện cuối cùng”. Không dùng anchor nếu chỉ cần tìm một đoạn phù hợp ở giữa chuỗi.

## 7. DEFINE: điều kiện để row khớp pattern variable

`DEFINE` gán predicate cho từng pattern variable:

~~~sql
PATTERN (A B+ C)
DEFINE
    A AS A.event_type = 'START',
    B AS B.event_type = 'PAYMENT',
    C AS C.event_type = 'CLOSE'
~~~

Một row được gán cho biến khi điều kiện của biến đó là TRUE. Điều kiện có thể kiểm tra:

- Giá trị cột của row hiện tại.
- Giá trị row trước/sau qua navigation functions.
- Quan hệ giữa giá trị hiện tại và những row đã được nhận vào match.
- Biểu thức số học, so sánh và điều kiện SQL được hỗ trợ.

Nếu một pattern variable không có trong `DEFINE`, điều kiện mặc định của biến đó là TRUE. Trong bài thực tế, nên định nghĩa rõ biến nào có ý nghĩa nghiệp vụ để người đọc hiểu pattern.

### 7.1. Điều kiện chỉ dựa trên row hiện tại

~~~sql
PATTERN (S P+ C)
DEFINE
    S AS S.event_type = 'START',
    P AS P.event_type = 'PAYMENT' AND P.amount > 0,
    C AS C.event_type = 'CLOSE'
~~~

Chỉ payment có amount dương được chấp nhận vào chuỗi. Nếu có payment amount 0 hoặc âm giữa START và CLOSE, pattern này không tự bỏ qua row đó; nó phải tìm cách khớp theo cấu trúc đã khai báo. Nếu muốn cho phép các sự kiện khác xen giữa, phải mô hình hóa chúng trong pattern.

### 7.2. So sánh với row trước bằng PREV

Ví dụ nhận diện các quan sát giá tăng liên tiếp:

~~~sql
PATTERN (A B+)
DEFINE
    B AS B.price > PREV(B.price)
~~~

`PREV` truy cập giá trị ở row trước trong chuỗi partition so với row đang được xét. Khi `B` đứng sau `A`, điều kiện của B có thể so giá hiện tại với giá của row trước. Khi `B+` lặp lại, mỗi B tiếp theo được so với row ngay trước đó.

Để dùng ví dụ trong một query đầy đủ:

~~~sql
SELECT symbol,
       match_no,
       first_price,
       last_price,
       rise_count,
       start_time,
       end_time
FROM stock_ticks
MATCH_RECOGNIZE (
    PARTITION BY symbol
    ORDER BY tick_time, tick_id
    MEASURES
        MATCH_NUMBER() AS match_no,
        FIRST(A.price) AS first_price,
        LAST(B.price) AS last_price,
        COUNT(B.tick_id) AS rise_count,
        FIRST(A.tick_time) AS start_time,
        LAST(B.tick_time) AS end_time
    ONE ROW PER MATCH
    AFTER MATCH SKIP PAST LAST ROW
    PATTERN (A B+)
    DEFINE
        B AS B.price > PREV(B.price)
) mr
ORDER BY symbol, start_time;
~~~

Pattern variable A không có điều kiện riêng nên có thể khớp một row làm điểm bắt đầu. Mỗi B phải có giá cao hơn row liền trước. `A B+` nhận một điểm neo và ít nhất một bước tăng.

Đây là mẫu minh họa; với dữ liệu giá thực, cần quyết định cách xử lý NULL, khoảng thời gian không có tick, giao dịch trùng thời điểm và việc có cho phép các row không tăng nằm giữa chuỗi hay không.

### 7.3. PREV và NEXT không giống FIRST và LAST

| Hàm | Vai trò |
| --- | --- |
| `PREV(expr [, offset])` | Lấy biểu thức ở row trước trong partition theo offset |
| `NEXT(expr [, offset])` | Lấy biểu thức ở row sau trong partition theo offset |
| `FIRST(expr [, offset])` | Truy cập giá trị ở vị trí đầu trong ngữ cảnh match/pattern variable |
| `LAST(expr [, offset])` | Truy cập giá trị ở vị trí cuối trong ngữ cảnh match/pattern variable |
| `CLASSIFIER()` | Tên pattern variable đã nhận diện row hiện tại trong match |
| `MATCH_NUMBER()` | Số thứ tự match trong partition |

`PREV`/`NEXT` là navigation theo row trong partition; `FIRST`/`LAST` dùng ngữ cảnh của match và pattern variable. Khi cần tính toán phức tạp, hãy đọc kỹ phạm vi của biểu thức và test trên chuỗi nhỏ có kết quả biết trước.

### 7.4. NULL trong DEFINE

Một predicate có kết quả UNKNOWN do NULL không được coi là TRUE để gán row cho pattern variable. Ví dụ:

~~~sql
DEFINE
    P AS P.amount > 0
~~~

Nếu `P.amount` là NULL, điều kiện không TRUE nên row không khớp biến P. Nếu nghiệp vụ muốn coi NULL như 0, hãy biểu diễn rõ:

~~~sql
DEFINE
    P AS NVL(P.amount, 0) > 0
~~~

Chỉ dùng `NVL` khi cách diễn giải đó đúng với ý nghĩa dữ liệu.

## 8. MEASURES: tạo kết quả từ một match

`MEASURES` định nghĩa các biểu thức được đưa vào output. Những hàm thường dùng:

- `MATCH_NUMBER()` — số thứ tự match trong partition.
- `CLASSIFIER()` — tên pattern variable gán cho row trong match.
- `FIRST(expr)` / `LAST(expr)` — giá trị đầu/cuối trong ngữ cảnh match.
- Aggregate như `COUNT`, `SUM`, `MIN`, `MAX`, `AVG` trên các pattern variable.

Ví dụ:

~~~sql
MEASURES
    MATCH_NUMBER() AS match_no,
    FIRST(S.event_time) AS session_start,
    LAST(C.event_time) AS session_end,
    COUNT(P.event_id) AS payment_count,
    SUM(P.amount) AS payment_total
~~~

Tên pattern variable được dùng để giới hạn row nào tham gia measure. `SUM(P.amount)` chỉ tính những dòng được gán cho P trong match.

### 8.1. ONE ROW PER MATCH

`ONE ROW PER MATCH` trả một dòng cho mỗi match. Đây là dạng phù hợp để tạo session summary, chuỗi cảnh báo, khoảng bắt đầu/kết thúc hoặc số liệu tổng hợp theo pattern.

~~~sql
SELECT account_id, match_no, session_start, session_end
FROM event_log
MATCH_RECOGNIZE (
    PARTITION BY account_id
    ORDER BY event_time, event_id
    MEASURES
        MATCH_NUMBER() AS match_no,
        FIRST(S.event_time) AS session_start,
        LAST(C.event_time) AS session_end
    ONE ROW PER MATCH
    PATTERN (S P* C)
    DEFINE
        S AS S.event_type = 'START',
        P AS P.event_type = 'PAYMENT',
        C AS C.event_type = 'CLOSE'
);
~~~

### 8.2. ALL ROWS PER MATCH

`ALL ROWS PER MATCH` trả về từng row thuộc match. Cách này hữu ích khi muốn biết dòng nào đã được nhận dạng là START, PAYMENT hay CLOSE.

~~~sql
SELECT account_id,
       event_id,
       event_type,
       event_time,
       classifier_name,
       match_no
FROM event_log
MATCH_RECOGNIZE (
    PARTITION BY account_id
    ORDER BY event_time, event_id
    MEASURES
        CLASSIFIER() AS classifier_name,
        MATCH_NUMBER() AS match_no
    ALL ROWS PER MATCH
    AFTER MATCH SKIP PAST LAST ROW
    PATTERN (S P* C)
    DEFINE
        S AS S.event_type = 'START',
        P AS P.event_type = 'PAYMENT',
        C AS C.event_type = 'CLOSE'
)
ORDER BY account_id, event_time, event_id;
~~~

Kết quả có thể có nhiều row cho một match:

| EVENT_ID | EVENT_TYPE | CLASSIFIER_NAME | MATCH_NO |
| ---: | --- | --- | ---: |
| 101 | START | S | 1 |
| 102 | PAYMENT | P | 1 |
| 103 | PAYMENT | P | 1 |
| 104 | CLOSE | C | 1 |
| 105 | START | S | 2 |
| 106 | PAYMENT | P | 2 |
| 107 | CLOSE | C | 2 |

`CLASSIFIER()` đặc biệt hữu ích khi cần giải thích vì sao một row thuộc match: cùng một nguồn event nhưng mỗi row có vai trò khác nhau.

### 8.3. RUNNING và FINAL trong measure

Trong `ALL ROWS PER MATCH`, kết quả measure có thể được hiểu theo trạng thái đang chạy hoặc sau khi match hoàn tất. Oracle hỗ trợ semantics `RUNNING` và `FINAL` cho measure trong những ngữ cảnh tương ứng:

- **RUNNING:** giá trị tại thời điểm row hiện tại trong quá trình nhận dạng.
- **FINAL:** giá trị sau khi match hoàn tất.

Điều này quan trọng khi muốn hiển thị running total hoặc tổng cuối cùng lặp lại trên các row của match. Với `ONE ROW PER MATCH`, thường chỉ cần giá trị cuối của match. Khi viết truy vấn `ALL ROWS PER MATCH`, hãy chỉ định semantics rõ nếu kết quả cần phụ thuộc tiến trình hay trạng thái cuối.

## 9. AFTER MATCH SKIP: vị trí bắt đầu tìm match kế tiếp

Sau khi một pattern được nhận diện, Oracle cần biết bắt đầu tìm pattern tiếp theo từ row nào. `AFTER MATCH SKIP` điều khiển hành vi này.

### 9.1. PAST LAST ROW

~~~sql
AFTER MATCH SKIP PAST LAST ROW
~~~

Sau khi match kết thúc, bỏ qua đến sau row cuối cùng của match. Đây là cách thường dùng khi các phiên không được chồng lấn.

~~~text
S P P C S P C
└─ match 1 ─┘ └ match 2 ┘
              bắt đầu sau C
~~~

### 9.2. TO NEXT ROW

~~~sql
AFTER MATCH SKIP TO NEXT ROW
~~~

Tiếp tục tìm từ row ngay sau row bắt đầu của match vừa rồi. Cách này cho phép các match chồng lấn, vì những row đã thuộc match trước vẫn có thể nằm trong match sau.

Ví dụ pattern tìm hai lần tăng liên tiếp có thể có nhiều cửa sổ cùng chia sẻ một số row. Nếu dùng `PAST LAST ROW`, các cửa sổ sau có thể bị bỏ qua; `TO NEXT ROW` cho phép xét lại từ vị trí sớm hơn.

### 9.3. TO FIRST variable và TO LAST variable

Oracle hỗ trợ skip tới lần xuất hiện đầu hoặc cuối của pattern variable trong match:

~~~sql
AFTER MATCH SKIP TO FIRST B
~~~

hoặc:

~~~sql
AFTER MATCH SKIP TO LAST B
~~~

Các dạng này hữu ích khi pattern có nhiều lần xuất hiện của một biến và muốn bắt đầu match tiếp theo từ một vị trí cụ thể trong match trước. Biến được dùng làm đích phải phù hợp với pattern và có mặt trong match; thiết kế sai có thể làm query không hợp lệ hoặc không đạt mục tiêu.

### 9.4. Skip policy thay đổi kết quả, không chỉ hiệu năng

Hai truy vấn có cùng `PATTERN` nhưng `AFTER MATCH SKIP` khác nhau có thể tạo **tập match khác nhau**. Hãy coi skip policy là một phần của định nghĩa nghiệp vụ:

| Mục tiêu | Skip policy thường cân nhắc |
| --- | --- |
| Các phiên tuần tự, không chồng lấn | `PAST LAST ROW` |
| Tìm các cửa sổ chồng lấn | `TO NEXT ROW` |
| Tiếp tục từ một sự kiện mốc trong match | `TO FIRST variable` / `TO LAST variable` |

Đừng chọn skip policy chỉ vì query trả nhiều hay ít dòng hơn mong đợi. Vẽ chuỗi input và đánh dấu điểm bắt đầu/kết thúc từng match để kiểm tra.

## 10. SUBSET: nhóm nhiều pattern variable

`SUBSET` cho phép định nghĩa một biến tổng hợp đại diện cho một nhóm pattern variable.

Ví dụ:

~~~sql
PATTERN (S (P | R)+ C)
SUBSET MONEY_EVENT = (P, R)
~~~

Trong đó P có thể là PAYMENT, R có thể là REFUND. `MONEY_EVENT` gom cả hai loại để sử dụng trong measure hoặc điều kiện phù hợp.

~~~sql
MEASURES
    COUNT(MONEY_EVENT.event_id) AS money_event_count
~~~

Điều này giúp biểu thức ngắn gọn khi nhiều pattern variable có cùng vai trò ở bước tính toán. `SUBSET` không làm thay đổi pattern; nó chỉ định nghĩa nhóm biến cho việc tham chiếu.

## 11. Ví dụ nhận dạng chuỗi tăng giá liên tiếp

Bài toán: với mỗi mã cổ phiếu, tìm đoạn có ít nhất hai lần tăng liên tiếp (tức có ít nhất ba quan sát giá, mỗi giá sau lớn hơn giá ngay trước).

Giả sử bảng `STOCK_TICKS` có:

| SYMBOL | TICK_ID | TICK_TIME | PRICE |
| --- | ---: | --- | ---: |
| ABC | 1 | 09:00 | 100 |
| ABC | 2 | 09:01 | 102 |
| ABC | 3 | 09:02 | 105 |
| ABC | 4 | 09:03 | 103 |
| ABC | 5 | 09:04 | 107 |
| ABC | 6 | 09:05 | 109 |

SQL:

~~~sql
SELECT symbol,
       match_no,
       first_price,
       last_price,
       observations,
       start_time,
       end_time
FROM stock_ticks
MATCH_RECOGNIZE (
    PARTITION BY symbol
    ORDER BY tick_time, tick_id
    MEASURES
        MATCH_NUMBER() AS match_no,
        FIRST(A.price) AS first_price,
        LAST(B.price) AS last_price,
        COUNT(B.tick_id) + 1 AS observations,
        FIRST(A.tick_time) AS start_time,
        LAST(B.tick_time) AS end_time
    ONE ROW PER MATCH
    AFTER MATCH SKIP TO NEXT ROW
    PATTERN (A B+)
    DEFINE
        B AS B.price > PREV(B.price)
) mr
ORDER BY symbol, start_time;
~~~

Diễn giải:

- A là giá neo đầu chuỗi.
- B là quan sát tăng so với row liền trước.
- `B+` yêu cầu ít nhất một bước tăng.
- `AFTER MATCH SKIP TO NEXT ROW` cho phép tiếp tục tìm các chuỗi có thể chồng lấn.
- `observations` đếm A cộng số dòng B.

Với dữ liệu ví dụ, chuỗi `100 → 102 → 105` là một đoạn tăng; `103 → 107 → 109` là đoạn tăng tiếp theo. Nếu muốn một chuỗi tăng tối đa không chồng lấn, xem xét `PAST LAST ROW`. Nếu muốn mọi cửa sổ tăng có thể chồng lấn, `TO NEXT ROW` thường phù hợp hơn.

Lưu ý: pattern và skip policy cần được thử trên dữ liệu thực, đặc biệt khi quantifier greedy có thể kéo dài match. `PREV` so sánh row liền trước trong partition; nếu dữ liệu có NULL hoặc khoảng trống, điều kiện tăng phải phản ánh rõ cách xử lý.

## 12. Ví dụ phát hiện chuỗi giao dịch bất thường

Một tài khoản có thể phát sinh nhiều giao dịch giá trị lớn liên tiếp. Giả sử quy tắc cảnh báo là:

- Có ít nhất ba giao dịch liên tiếp.
- Mỗi giao dịch có amount lớn hơn 1.000.
- Tất cả thuộc cùng tài khoản.
- Cửa sổ được phân tách khi có giao dịch nhỏ hơn hoặc bằng 1.000.

Pattern:

~~~sql
SELECT account_id,
       match_no,
       first_event,
       last_event,
       event_count,
       total_amount
FROM transactions
MATCH_RECOGNIZE (
    PARTITION BY account_id
    ORDER BY transaction_time, transaction_id
    MEASURES
        MATCH_NUMBER() AS match_no,
        FIRST(H.transaction_time) AS first_event,
        LAST(H.transaction_time) AS last_event,
        COUNT(H.transaction_id) AS event_count,
        SUM(H.amount) AS total_amount
    ONE ROW PER MATCH
    AFTER MATCH SKIP PAST LAST ROW
    PATTERN (H{3,})
    DEFINE
        H AS H.amount > 1000
) mr
ORDER BY account_id, first_event;
~~~

`H{3,}` yêu cầu ít nhất ba row liên tiếp thỏa điều kiện H. Một row không thỏa H kết thúc khả năng kéo dài chuỗi hiện tại; Oracle tiếp tục tìm match ở vị trí tiếp theo theo skip policy.

**Giới hạn nghiệp vụ:** ví dụ này nhận dạng chuỗi liên tiếp theo thứ tự row, không chứng minh các giao dịch có cùng người thực hiện, cùng thiết bị, không phải giao dịch hợp lệ hoặc có ý định gian lận. Fraud detection thực tế cần thêm đặc trưng, ngữ cảnh và quy trình xác minh.

## 13. Ví dụ trạng thái đơn hàng

Giả sử chuỗi trạng thái hợp lệ của một đơn là:

~~~text
CREATED → PAID → (PACKED) → SHIPPED
~~~

Trong đó `PACKED` có thể xuất hiện hoặc không:

~~~sql
SELECT order_id,
       created_at,
       paid_at,
       shipped_at
FROM order_status_history
MATCH_RECOGNIZE (
    PARTITION BY order_id
    ORDER BY status_time, status_event_id
    MEASURES
        FIRST(C.status_time) AS created_at,
        FIRST(P.status_time) AS paid_at,
        LAST(S.status_time) AS shipped_at
    ONE ROW PER MATCH
    AFTER MATCH SKIP PAST LAST ROW
    PATTERN (C P K? S)
    DEFINE
        C AS C.status = 'CREATED',
        P AS P.status = 'PAID',
        K AS K.status = 'PACKED',
        S AS S.status = 'SHIPPED'
) mr
ORDER BY order_id, created_at;
~~~

`K?` cho phép một row PACKED hoặc không có row PACKED. Pattern này chỉ tìm đúng thứ tự đã khai báo; nếu hệ thống có trạng thái `CANCELLED`, `RETURNED` hoặc `ON_HOLD`, cần quyết định chúng có được bỏ qua, kết thúc chuỗi hay tạo nhánh pattern khác.

Không tự thêm `.*` để “cho qua mọi trạng thái lạ” nếu chưa xác định các trạng thái đó có làm thay đổi ý nghĩa vòng đời đơn hàng hay không.

## 14. Row không khớp và khoảng trống trong chuỗi

Không phải mọi row trong partition đều phải thuộc một match. `MATCH_RECOGNIZE` tìm các đoạn thỏa pattern; những row không thuộc match có thể không xuất hiện trong output, tùy row-per-match option và cách truy vấn.

Nếu cần quan sát cả dòng khớp lẫn không khớp:

- Dùng `ALL ROWS PER MATCH` để xem từng dòng thuộc các match.
- Kiểm tra hỗ trợ và semantics của `WITH UNMATCHED ROWS` trong cú pháp Oracle release đang dùng nếu muốn đưa row không khớp vào output.
- Có thể so sánh nguồn với tập row đã match bằng khóa duy nhất và anti join/`NOT EXISTS`.

Ví dụ cách tư duy đối chiếu:

~~~sql
WITH matched_events AS (
    SELECT account_id, event_id
    FROM event_log
    MATCH_RECOGNIZE (
        PARTITION BY account_id
        ORDER BY event_time, event_id
        MEASURES
            CLASSIFIER() AS classifier_name
        ALL ROWS PER MATCH
        PATTERN (S P* C)
        DEFINE
            S AS S.event_type = 'START',
            P AS P.event_type = 'PAYMENT',
            C AS C.event_type = 'CLOSE'
    )
)
SELECT e.*
FROM   event_log e
WHERE  NOT EXISTS (
    SELECT 1
    FROM matched_events m
    WHERE m.account_id = e.account_id
      AND m.event_id = e.event_id
);
~~~

Đây là khung minh họa; khi áp dụng cần kiểm tra cột output của `MATCH_RECOGNIZE` theo row-per-match mode và giữ khóa đủ duy nhất. Cách anti join hữu ích để tìm sự kiện không thuộc match, nhưng không thay thế quy tắc phân loại unmatched rows của row pattern clause.

## 15. AFTER MATCH SKIP và các match chồng lấn

Xét chuỗi:

~~~text
Giá:  10 → 12 → 14 → 16
ID:    1    2    3    4
~~~

Pattern `A B+` với `B.price > PREV(B.price)` có thể nhận đoạn tăng bắt đầu tại ID 1. Nếu dùng `PAST LAST ROW`, sau khi match kết thúc ở ID 4, Oracle tiếp tục sau ID 4 nên không có các cửa sổ bắt đầu ở ID 2 hoặc 3.

Nếu dùng `TO NEXT ROW`, quá trình tìm tiếp tục từ row sau điểm bắt đầu của match trước; các row sau có thể được tái sử dụng trong match khác. Cách này tạo các match chồng lấn, tùy greedy quantifier và điều kiện DEFINE.

~~~text
Input:  10 → 12 → 14 → 16

Match có thể chồng lấn:
        [10 → 12 → 14]
              [12 → 14 → 16]

PAST LAST ROW:
        [10 → 12 → 14 → 16]
        tiếp tục sau ID cuối
~~~

Khi báo cáo số lượng match, phải nói rõ chúng có thể chồng lấn hay không. Nếu không, tổng số row tham gia match không nhất thiết bằng số row nguồn; nếu có overlap, một row có thể tham gia nhiều match.

## 16. Xử lý dữ liệu có timestamp trùng, NULL và khoảng thời gian

### 16.1. Timestamp trùng

Luôn thêm tie-breaker duy nhất khi thứ tự sự kiện cùng timestamp có ý nghĩa:

~~~sql
ORDER BY event_time, event_id
~~~

Nếu không có khóa phân xử, hai event cùng thời gian có thể được xử lý theo thứ tự không ổn định. Pattern như `A B C` có thể nhận dạng khác nhau nếu hai row đổi vị trí.

### 16.2. Giá trị NULL trong cột điều kiện

Điều kiện:

~~~sql
DEFINE
    H AS H.amount > 1000
~~~

không nhận row có amount NULL vào H vì phép so sánh trả UNKNOWN, không phải TRUE. Nếu NULL biểu thị “không rõ amount”, cần xác định:

- Row đó bị loại khỏi pattern?
- Row đó làm ngắt chuỗi?
- Row đó được xử lý như 0?
- Row đó cần tạo một pattern variable riêng?

Viết logic tương ứng thay vì để NULL semantics quyết định ngầm.

### 16.3. Khoảng thời gian giữa hai sự kiện

Có thể thêm điều kiện khoảng cách thời gian trong `DEFINE`, ví dụ sự kiện hiện tại phải xảy ra không quá 10 phút sau row trước. Với timestamp, phép trừ có thể tạo INTERVAL:

~~~sql
DEFINE
    B AS B.event_time - PREV(B.event_time)
         <= INTERVAL '10' MINUTE
~~~

Biểu thức thực tế cần phù hợp với datatype của cột và kiểu kết quả timestamp arithmetic. Nếu có nhiều row xen giữa hoặc cần đo khoảng cách từ mốc A thay vì row liền trước, dùng navigation function phù hợp và test trên chuỗi nhỏ.

## 17. Các lỗi thiết kế và lỗi truy vấn thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy match dù nhìn thấy START và CLOSE | Có row xen giữa không được pattern cho phép; DEFINE không TRUE | Xem toàn bộ chuỗi theo ORDER BY, định nghĩa biến cho sự kiện xen giữa nếu nghiệp vụ cho phép |
| Match đi qua sai thứ tự | ORDER BY thiếu tie-breaker hoặc sort key không phản ánh thứ tự nghiệp vụ | Thêm khóa duy nhất/quy tắc ưu tiên |
| Một phiên bị tách thành nhiều match | Skip policy hoặc pattern boundary không phù hợp | Vẽ chuỗi, kiểm tra quantifier và AFTER MATCH SKIP |
| Match bị chồng lấn ngoài ý muốn | Dùng TO NEXT ROW hoặc skip tới vị trí sớm | Chọn PAST LAST ROW nếu cần match tuần tự |
| Bỏ sót các match chồng lấn | Dùng PAST LAST ROW | Cân nhắc TO NEXT ROW hoặc skip phù hợp |
| Pattern khớp quá nhiều row | DEFINE quá rộng hoặc quantifier greedy | Thu hẹp điều kiện, xác định điểm kết thúc rõ ràng |
| Không có payment nhưng total là NULL | SUM trên tập rỗng trả NULL | Dùng NVL(SUM(...),0) nếu đúng nghiệp vụ |
| PREV trả NULL ở đầu partition | Không có row trước hoặc giá trị trước NULL | Xử lý boundary/NULL tường minh |
| Cùng dữ liệu nhưng match thay đổi giữa các lần chạy | Thứ tự row không xác định khi sort key trùng | Bổ sung unique tie-breaker |
| Output có nhiều dòng hơn dự kiến | Dùng ALL ROWS PER MATCH, hoặc match overlap | Kiểm tra row-per-match và skip policy |
| Chỉ có summary mà cần xem row gốc | Dùng ONE ROW PER MATCH | Chuyển sang ALL ROWS PER MATCH hoặc truy vấn chi tiết riêng |
| Cột measure không đúng phạm vi | Dùng sai pattern variable trong aggregate/FIRST/LAST | Qualify measure bằng đúng biến |
| Một row không thuộc match biến mất | Chỉ xuất matched rows | Đối chiếu unmatched rows bằng tùy chọn hỗ trợ hoặc anti join |

## 18. Hiệu năng và cách kiểm tra execution plan

`MATCH_RECOGNIZE` là phép phân tích chuỗi có thể cần sắp xếp và giữ trạng thái trong quá trình nhận dạng. Chi phí phụ thuộc:

- Số row trong mỗi partition.
- Số lượng partition và phân bố kích thước.
- Độ phức tạp của pattern.
- Quantifier lặp và số nhánh alternation.
- Biểu thức trong DEFINE/MEASURES.
- Khả năng tận dụng thứ tự/index và các phép lọc trước pattern matching.

### 18.1. Giảm dữ liệu đầu vào đúng cách

Nếu chỉ phân tích khoảng thời gian cần thiết, lọc nguồn trước:

~~~sql
SELECT ...
FROM (
    SELECT *
    FROM event_log
    WHERE event_time >= TIMESTAMP '2026-11-01 00:00:00'
      AND event_time <  TIMESTAMP '2026-12-01 00:00:00'
) src
MATCH_RECOGNIZE (...);
~~~

Điều kiện lọc cần giữ đủ dữ liệu để nhận diện pattern. Ví dụ nếu một phiên bắt đầu trước ngày 1/11 nhưng kết thúc trong tháng 11, lọc mất START sẽ làm pattern không còn hoàn chỉnh. Có thể cần mở rộng khoảng đọc, lấy trạng thái trước kỳ hoặc thiết kế boundary rule.

### 18.2. Partition key và thứ tự

Index theo `(account_id, event_time, event_id)` có thể hữu ích cho workload thường xuyên phân tích theo tài khoản và thời gian. Tuy nhiên, optimizer không nhất thiết dùng index đó; việc sort, join, filter và cardinality còn ảnh hưởng plan.

Không tạo index chỉ vì query có `PARTITION BY`/`ORDER BY`. Kiểm tra execution plan, chi phí ghi dữ liệu, dung lượng và workload tổng thể.

### 18.3. Pattern phức tạp

Pattern có nhiều quantifier lặp, alternation và điều kiện navigation có thể khó kiểm soát và tốn tài nguyên hơn. Hãy:

- Viết pattern tối giản theo quy tắc nghiệp vụ.
- Giới hạn partition nếu có thể mà không làm sai logic.
- Tránh DEFINE quá rộng khiến nhiều nhánh có thể khớp cùng một row.
- Kiểm tra kết quả với chuỗi nhỏ có expected matches.
- Đo trên phân bố dữ liệu gần thực tế, không chỉ bảng vài dòng.

### 18.4. Xem plan

~~~sql
EXPLAIN PLAN FOR
SELECT account_id, match_no
FROM event_log
MATCH_RECOGNIZE (
    PARTITION BY account_id
    ORDER BY event_time, event_id
    MEASURES MATCH_NUMBER() AS match_no
    ONE ROW PER MATCH
    PATTERN (S P* C)
    DEFINE
        S AS S.event_type = 'START',
        P AS P.event_type = 'PAYMENT',
        C AS C.event_type = 'CLOSE'
);

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

`EXPLAIN PLAN` là kế hoạch dự kiến. Nếu cần số liệu runtime, DBA có thể dùng `DBMS_XPLAN.DISPLAY_CURSOR` với cursor và statistics phù hợp. Không cấp quyền quản trị chỉ để chạy bài học; sử dụng quyền được cấp trong môi trường lab.

## 19. Giới hạn và lưu ý khi dùng MATCH_RECOGNIZE

1. **Cần có thứ tự sự kiện:** row pattern matching không thể suy ra thứ tự nghiệp vụ từ thứ tự lưu trữ.
2. **Không vượt partition:** một match không đi qua ranh giới partition.
3. **Một match có thể không bao gồm mọi row:** chỉ những row tham gia pattern mới được xem là matched.
4. **Skip policy quyết định overlap:** `AFTER MATCH SKIP` là một phần của semantics.
5. **Không phải mọi truy vấn tuần tự đều cần MATCH_RECOGNIZE:** nếu chỉ cần `LAG`, `LEAD`, `ROW_NUMBER` hoặc aggregate đơn giản, analytic function có thể rõ và nhẹ hơn.
6. **Đọc dữ liệu lịch sử cần đủ context:** cắt thời gian quá sớm có thể làm mất sự kiện mở đầu của pattern.
7. **Pattern không tự xác thực ý nghĩa nghiệp vụ:** query nhận dạng đúng chuỗi theo điều kiện, nhưng không chứng minh giao dịch gian lận, đơn hàng sai hay thiết bị hỏng.
8. **Cần kiểm tra datatype:** timestamp, interval, NULL, collation và biểu thức DEFINE/MEASURES phải phù hợp dữ liệu.
9. **Không giả định output order:** thêm ORDER BY ngoài cùng khi client cần thứ tự.
10. **Cú pháp phụ thuộc release:** đối chiếu SQL Language Reference đúng phiên bản Oracle đang chạy, nhất là tùy chọn row-per-match và navigation.

## 20. Khi nào dùng MATCH_RECOGNIZE, analytic function hay self join?

| Bài toán | Công cụ thường phù hợp | Lý do |
| --- | --- | --- |
| Lấy giá trị row trước/row sau | `LAG`, `LEAD` | Quan hệ một vị trí đơn giản |
| Đánh số và xếp hạng row | `ROW_NUMBER`, `RANK`, `DENSE_RANK` | Ranking theo thứ tự |
| Tính running total | Analytic aggregate | Tổng lũy kế không cần pattern |
| Kiểm tra một chuỗi sự kiện có cấu trúc | `MATCH_RECOGNIZE` | Mô tả biến, quantifier, thứ tự và skip |
| Liệt kê quan hệ cha-con hoặc mọi cặp row | JOIN/self join | Quan hệ giữa các row |
| Chỉ kiểm tra có row liên quan hay không | `EXISTS` | Không cần nhận dạng chuỗi |
| Logic điều khiển nhiều bước và side effect | PL/SQL/procedure/workflow | Cần thao tác hoặc trạng thái nghiệp vụ |

Ví dụ `LAG` có thể tìm một lần tăng đơn:

~~~sql
SELECT symbol,
       tick_time,
       price,
       LAG(price) OVER (
           PARTITION BY symbol
           ORDER BY tick_time, tick_id
       ) AS previous_price
FROM stock_ticks;
~~~

Sau đó `WHERE price > previous_price` có thể lọc row tăng. Nhưng nếu yêu cầu là tìm **một chuỗi có ít nhất ba lần tăng, sau đó giảm, cho phép một số nhánh và tính measure theo match**, `MATCH_RECOGNIZE` diễn đạt cấu trúc rõ hơn.

Không nên chọn công cụ chỉ dựa vào độ mới. Chọn theo hình dạng bài toán và khả năng kiểm soát kết quả.

## 21. Bài thực hành tự chứa

> Có thể chạy các truy vấn SELECT trong môi trường Oracle 19c. Các bảng `EVENT_LOG`, `STOCK_TICKS`, `TRANSACTIONS`, `ORDER_STATUS_HISTORY` ở một số ví dụ là tên minh họa; thay bằng bảng lab hoặc schema được cấp. Không chạy DML trên production.

### Bài A — Nhận dạng phiên không chồng lấn

Dùng CTE ở phần 4 và `PATTERN (S P* C)`.

Yêu cầu:

1. Trả một row cho mỗi phiên.
2. Đếm số payment.
3. Tính tổng payment.
4. Hiển thị thời gian bắt đầu và kết thúc.
5. Thử thêm một phiên `START → CLOSE` không có payment.

Kỳ vọng phiên không payment vẫn được nhận diện; count là 0 và total cần được xử lý NULL theo yêu cầu.

### Bài B — Bắt buộc có ít nhất hai payment

Đổi pattern:

~~~sql
PATTERN (S P{2,} C)
~~~

Tạo dữ liệu có một phiên một payment và một phiên hai payment. Giải thích vì sao chỉ phiên có từ hai payment mới khớp.

### Bài C — Trả về từng row trong match

Đổi `ONE ROW PER MATCH` thành:

~~~sql
ALL ROWS PER MATCH
~~~

Thêm measure:

~~~sql
CLASSIFIER() AS event_role,
MATCH_NUMBER() AS match_no
~~~

Đối chiếu từng `EVENT_ID` và giải thích vì sao cùng một partition có thể có nhiều match number.

### Bài D — So sánh skip policy

Tạo chuỗi tăng:

~~~text
100, 102, 105, 103, 107, 109
~~~

Chạy pattern:

~~~sql
PATTERN (A B+)
DEFINE
    B AS B.price > PREV(B.price)
~~~

So sánh `AFTER MATCH SKIP PAST LAST ROW` với `AFTER MATCH SKIP TO NEXT ROW`. Vẽ vị trí start/end từng match và ghi rõ row nào được tái sử dụng.

### Bài E — Timestamp trùng

Tạo hai event cùng `EVENT_TIME` nhưng `EVENT_ID` khác nhau. Chạy query trước và sau khi thêm `EVENT_ID` vào `ORDER BY`. Giải thích vì sao thứ tự tie có thể thay đổi cách pattern nhận dạng.

### Bài F — NULL trong DEFINE

Tạo một row có `AMOUNT = NULL`, rồi so sánh:

~~~sql
DEFINE
    P AS P.amount > 0
~~~

với:

~~~sql
DEFINE
    P AS NVL(P.amount, 0) > 0
~~~

Kết luận row NULL có được nhận vào biến P hay không và vì sao.

### Bài G — Khoảng thời gian tối đa

Với chuỗi sự kiện có `EVENT_TIME` kiểu TIMESTAMP, thêm điều kiện khoảng cách tối đa 10 phút giữa các row liên tiếp trong pattern. Thử khoảng cách 8 phút, 10 phút và 11 phút để xác nhận boundary.

### Bài H — Đối chiếu row không khớp

Dùng `ALL ROWS PER MATCH` lấy khóa của các row đã nhận dạng, rồi dùng `NOT EXISTS` để liệt kê event còn lại. Giải thích sự khác nhau giữa “không khớp pattern” và “dữ liệu sai”.

## 22. Câu hỏi ôn tập

**Câu 1.** `MATCH_RECOGNIZE` giải quyết loại bài toán nào?

**Câu 2.** Vì sao cần `PARTITION BY` khi nhận dạng chuỗi theo tài khoản?

**Câu 3.** `ORDER BY event_time` có đủ xác định thứ tự nếu hai event cùng timestamp không?

**Câu 4.** `PATTERN (S P* C)` khác `PATTERN (S P+ C)` ở điểm nào?

**Câu 5.** `DEFINE` làm nhiệm vụ gì?

**Câu 6.** Nếu một pattern variable không được định nghĩa trong DEFINE thì điều kiện mặc định là gì?

**Câu 7.** `ONE ROW PER MATCH` khác `ALL ROWS PER MATCH` như thế nào?

**Câu 8.** `CLASSIFIER()` và `MATCH_NUMBER()` cung cấp thông tin gì?

**Câu 9.** `AFTER MATCH SKIP PAST LAST ROW` và `TO NEXT ROW` khác nhau thế nào?

**Câu 10.** `PREV` khác `FIRST` ra sao?

**Câu 11.** Vì sao `SUM(P.amount)` có thể là NULL khi pattern cho phép zero payment?

**Câu 12.** Khi nào nên dùng LAG/LEAD thay cho MATCH_RECOGNIZE?

<details>
<summary>Gợi ý đáp án</summary>

1. Nhận dạng chuỗi row theo thứ tự và cấu trúc mẫu, ví dụ START, nhiều PAYMENT, CLOSE.
2. Để mỗi tài khoản là một chuỗi độc lập, tránh match vượt qua hai tài khoản.
3. Không. Cần thêm khóa phân xử duy nhất hoặc quy tắc ưu tiên nghiệp vụ.
4. `P*` cho phép zero hoặc nhiều P; `P+` yêu cầu ít nhất một P.
5. Định nghĩa predicate để row hiện tại được gán vào pattern variable.
6. TRUE, tức biến có thể khớp mọi row nếu pattern position cho phép.
7. ONE trả một row tổng hợp cho mỗi match; ALL trả từng row tham gia match.
8. CLASSIFIER cho biết tên biến mẫu của row; MATCH_NUMBER đánh số match trong partition.
9. PAST LAST ROW tiếp tục sau cuối match; TO NEXT ROW tiếp tục từ row sau điểm bắt đầu, cho phép overlap.
10. PREV truy cập row trước trong partition; FIRST truy cập giá trị đầu theo ngữ cảnh match/pattern variable.
11. SUM trên tập không có giá trị trả NULL; dùng NVL nếu nghiệp vụ muốn 0.
12. Khi chỉ cần quan hệ một row trước/sau hoặc một phép so sánh tuần tự đơn giản; analytic function dễ đọc hơn.

</details>

## 23. Tài liệu Oracle chính thức

1. [Oracle Database 19c SQL Language Reference — SELECT / MATCH_RECOGNIZE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html): cú pháp row pattern matching, partition, order, measures, pattern, define, row-per-match và skip.
2. [Oracle Database 19c Data Warehousing Guide — SQL Pattern Matching](https://docs.oracle.com/en/database/oracle/oracle-database/19/dwhsg/sql-pattern-matching-data-warehouses.html): khái niệm, cách mô hình hóa chuỗi, ví dụ pattern matching và ứng dụng phân tích.
3. [Oracle Database 19c SQL Language Reference — Pattern Matching Functions](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Pattern-matching-functions.html): navigation và các hàm dùng trong row pattern matching.
4. [Oracle Database 19c SQL Language Reference — Analytic Functions](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Analytic-Functions.html): thứ tự xử lý analytic function và so sánh với phân tích chuỗi.
5. [Oracle Database 19c SQL Tuning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/): execution plan, optimizer và đánh giá chi phí truy vấn.

**Nguyên tắc cần nhớ:** `MATCH_RECOGNIZE` biến một chuỗi row đã được phân vùng và sắp xếp thành một ngôn ngữ mô tả mẫu. `PATTERN` nêu cấu trúc, `DEFINE` nêu điều kiện của từng biến, `MEASURES` tạo kết quả, row-per-match quyết định độ chi tiết output và `AFTER MATCH SKIP` quyết định vị trí tìm tiếp. Khi thiết kế, phải xác định rõ thứ tự sự kiện, cách xử lý NULL, sự kiện xen giữa, quantifier và khả năng match chồng lấn.

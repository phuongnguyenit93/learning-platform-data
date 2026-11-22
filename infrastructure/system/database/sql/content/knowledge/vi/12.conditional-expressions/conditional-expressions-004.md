# Phân loại dữ liệu và ánh xạ mã thành nhãn trong SQL

Trong cơ sở dữ liệu, nhiều thông tin được lưu dưới dạng **mã ngắn** hoặc **giá trị số** để hệ thống dễ lưu trữ, kiểm tra và xử lý. Chẳng hạn, đơn hàng có thể có mã trạng thái \`P\`, \`D\`, \`S\`, \`C\`; tổng tiền có thể là 150.000, 650.000 hay 2.400.000 đồng. Người đọc báo cáo lại muốn thấy **“Chờ xử lý”**, **“Đã thanh toán”**, **“Đang giao”**, **“Hoàn tất”**, hoặc các nhóm **“Nhỏ”**, **“Vừa”**, **“Lớn”** thay vì những giá trị thô.

Đó là hai thao tác quen thuộc trong SQL:

- **Ánh xạ mã thành nhãn** (*code-to-label mapping*): chuyển một mã đã có ý nghĩa quy ước sang văn bản dễ hiểu, ví dụ \`'C'\` → \`'Hoàn tất'\`.
- **Phân loại dữ liệu** (*classification/bucketing*): dựa trên một hay nhiều điều kiện để gán một hàng vào nhóm, ví dụ tổng tiền từ 1.500.000 đồng trở lên → \`'Lớn'\`.

Công cụ rẽ nhánh cốt lõi là biểu thức **\`CASE\`**. Nó cho phép trả về **một giá trị khác nhau tùy điều kiện**, và vì là biểu thức SQL, nó có thể xuất hiện trong \`SELECT\`, \`ORDER BY\`, \`GROUP BY\`, phép tổng hợp có điều kiện và những chỗ phù hợp khác. Tuy nhiên, khi số lượng mã hoặc quy tắc tăng lên, **bảng tra cứu và \`JOIN\`** đôi khi phù hợp hơn một biểu thức CASE dài.

Bài học thuộc chương **Rẽ nhánh trong SQL** của module **Database SQL**. Các ví dụ chính chạy trên **PostgreSQL 15 trở lên**, dùng dữ liệu giả lập độc lập. Cú pháp cơ bản \`CASE\` có trong nhiều hệ quản trị khác; một số tiện ích như \`FILTER\`, cách ép kiểu hoặc cách nối chuỗi có thể khác theo phương ngữ.

## 1. Mục tiêu

Sau khi thực hành, bạn có thể:

1. Giải thích sự khác nhau giữa **mã gốc**, **nhãn hiển thị** và **nhóm phân loại**.
2. Viết cả hai dạng \`CASE\`: **simple CASE** và **searched CASE**.
3. Ánh xạ mã trạng thái thành nhãn tiếng Việt mà vẫn xử lý được **NULL** và **mã lạ**.
4. Chia khoảng số tiền thành những nhóm **không chồng lấn**, kiểm soát chính xác giá trị ở ranh giới.
5. Ưu tiên một số quy tắc nghiệp vụ khi nhiều điều kiện có thể cùng đúng.
6. Dùng nhãn/nhóm để lọc, sắp xếp, đếm và tổng hợp.
7. Chọn giữa \`CASE\`, bảng danh mục kết hợp \`JOIN\` và cách xử lý ở tầng ứng dụng.
8. Nhận ra các rủi ro như mất mã gốc, bỏ sót NULL, nhãn không được dịch, quy tắc phân loại thiếu điều kiện và thay đổi nghĩa khi sửa nhãn.

## 2. Mã, nhãn và phân loại không phải cùng một dữ liệu

Giả sử đơn hàng có trạng thái lưu trong cột \`status_code\`:

| Mã lưu trữ | Nhãn tiếng Việt | Ý nghĩa |
| --- | --- | --- |
| \`P\` | Chờ xử lý | Đơn mới, chưa hoàn thành bước xử lý ban đầu |
| \`D\` | Đã thanh toán | Đã ghi nhận thanh toán |
| \`S\` | Đang giao | Đơn đang được vận chuyển |
| \`C\` | Hoàn tất | Đơn đã hoàn thành |
| \`X\` | Đã hủy | Đơn bị hủy |
| \`R\` | Đã hoàn trả | Đơn đã được ghi nhận hoàn trả |

**Mã** là giá trị mà hệ thống sử dụng cho logic và quan hệ dữ liệu; **nhãn** diễn đạt mã đó cho người dùng. Chẳng hạn, có thể giữ nguyên mã \`C\` nhưng thay nhãn từ “Hoàn tất” thành “Đã hoàn thành”. Việc đổi cách gọi không nhất thiết là thay đổi trạng thái nghiệp vụ.

Ngược lại, khi nói đơn hàng thuộc nhóm **“Vừa”** hay **“Lớn”**, đây thường là **phân loại dẫn xuất** từ một quy tắc:

| Khoảng \`amount_vnd\` | Nhóm |
| --- | --- |
| Từ 0 đến dưới 500.000 | Nhỏ |
| Từ 500.000 đến dưới 1.500.000 | Vừa |
| Từ 1.500.000 trở lên | Lớn |

Ở đây, nhóm “Vừa” không phải mã gốc được nhập cùng đơn hàng: nó được **tính từ tổng tiền** theo các ngưỡng đã thống nhất. Nếu ngưỡng kinh doanh đổi, cách phân loại có thể đổi dù tổng tiền của đơn không đổi.

**Nguyên tắc thiết kế:** nên giữ lại **giá trị nguồn** (\`status_code\`, \`amount_vnd\`) và tạo thêm **nhãn/nhóm** khi cần trình bày hoặc phân tích. Điều này giúp kiểm tra lại kết quả, thay đổi ngôn ngữ hiển thị và tránh làm mất thông tin gốc.

## 3. Tạo bộ dữ liệu thực hành

Chạy đoạn SQL sau trong một phiên PostgreSQL. Hai bảng tạm sẽ chỉ tồn tại trong phiên kết nối hiện tại; chúng không đụng đến dữ liệu của các bài khác.

~~~sql
CREATE TEMP TABLE demo_case_orders (
    order_id       INTEGER PRIMARY KEY,
    customer_id    INTEGER NOT NULL,
    ordered_on     DATE NOT NULL,
    status_code    TEXT,
    amount_vnd     NUMERIC(12, 2) NOT NULL CHECK (amount_vnd >= 0),
    region_code    TEXT,
    is_priority    BOOLEAN
);

INSERT INTO demo_case_orders
    (order_id, customer_id, ordered_on, status_code,
     amount_vnd, region_code, is_priority)
VALUES
    (1,  10, '2026-04-01', 'P',  150000,  'HN',  FALSE),
    (2,  10, '2026-04-01', 'D',  650000,  'HN',  TRUE),
    (3,  11, '2026-04-02', 'S', 1250000,  'HCM', FALSE),
    (4,  12, '2026-04-02', 'C', 2400000,  'DN',  TRUE),
    (5,  13, '2026-04-03', 'X',   85000,  NULL,  FALSE),
    (6,  11, '2026-04-04', 'C',  480000,  'HCM', FALSE),
    (7,  14, '2026-04-05', 'R',  760000,  'HN',  TRUE),
    (8,  15, '2026-04-05', NULL, 320000, 'DN',  NULL),
    (9,  16, '2026-04-06', 'Z', 1200000,  'HCM', FALSE),
    (10, 16, '2026-04-06', 'D',       0,  'HCM', FALSE),
    (11, 10, '2026-04-07', 'C',  180000,  'HN',  FALSE),
    (12, 17, '2026-04-08', 'P', 1000000,  NULL,  TRUE),
    (13, 18, '2026-04-08', 'S',  500000,  'HN',  FALSE),
    (14, 19, '2026-04-09', 'C', 1500000,  'HCM', NULL);
~~~

Xem dữ liệu:

~~~sql
SELECT order_id, customer_id, ordered_on, status_code,
       amount_vnd, region_code, is_priority
FROM demo_case_orders
ORDER BY order_id;
~~~

Bộ dữ liệu có **14 đơn hàng**. Hai trường hợp được cố ý đưa vào để kiểm tra cách ánh xạ lỗi:

- **Đơn 8:** \`status_code IS NULL\`, nghĩa là chưa có mã trạng thái.
- **Đơn 9:** \`status_code = 'Z'\`, một mã không thuộc danh sách trạng thái đã mô tả.

Các giá trị \`amount_vnd\` bao gồm đúng các ngưỡng **500.000** và **1.500.000**, giúp quan sát điều kiện biên của phân loại. Giá trị **0** là hợp lệ trong bảng minh họa, nhưng ở hệ thống bán hàng thật cần quy định riêng khi nào đơn được phép có tổng tiền 0.

> Nếu chạy lại trong cùng phiên, bảng tạm đã tồn tại. Hãy mở phiên mới hoặc xóa **riêng bảng tạm \`demo_case_orders\`** rồi tạo lại. Không xóa các bảng nghiệp vụ đang dùng.

## 4. Dạng thứ nhất: simple CASE để ánh xạ mã

**Simple CASE** so sánh một biểu thức với từng giá trị được liệt kê:

~~~sql
CASE expression
    WHEN value_1 THEN result_1
    WHEN value_2 THEN result_2
    ELSE default_result
END
~~~

Ví dụ chuyển \`status_code\` thành nhãn:

~~~sql
SELECT
    order_id,
    status_code,
    CASE status_code
        WHEN 'P' THEN 'Chờ xử lý'
        WHEN 'D' THEN 'Đã thanh toán'
        WHEN 'S' THEN 'Đang giao'
        WHEN 'C' THEN 'Hoàn tất'
        WHEN 'X' THEN 'Đã hủy'
        WHEN 'R' THEN 'Đã hoàn trả'
        ELSE 'Không xác định'
    END AS status_label
FROM demo_case_orders
ORDER BY order_id;
~~~

**Cách đọc:** SQL lấy giá trị \`status_code\` của từng hàng, so sánh với các giá trị \`'P'\`, \`'D'\`, ... và trả về nhãn của nhánh phù hợp. Nếu không có nhánh nào khớp, biểu thức lấy giá trị ở \`ELSE\`.

| order_id | status_code | status_label |
| ---: | --- | --- |
| 1 | P | Chờ xử lý |
| 2 | D | Đã thanh toán |
| 3 | S | Đang giao |
| 4 | C | Hoàn tất |
| 5 | X | Đã hủy |
| 7 | R | Đã hoàn trả |
| 8 | NULL | Không xác định |
| 9 | Z | Không xác định |

**Ưu điểm:** ngắn gọn, dễ đọc nếu cần đổi **một mã** thành **một nhãn**, nhất là khi tập mã nhỏ và ổn định.

**Giới hạn:** đơn 8 **thiếu mã** và đơn 9 **có mã lạ** cùng nhận nhãn “Không xác định”. Nếu muốn phân biệt hai vấn đề này, nên dùng **searched CASE** ở phần tiếp theo.

### ELSE là gì? Nếu không có ELSE thì sao?

\`ELSE\` là kết quả mặc định khi không có nhánh \`WHEN\` nào khớp. Nếu **bỏ \`ELSE\`**, SQL trả về **NULL** cho hàng không khớp:

~~~sql
SELECT
    order_id,
    CASE status_code
        WHEN 'D' THEN 'Đã thanh toán'
        WHEN 'C' THEN 'Hoàn tất'
    END AS selected_label
FROM demo_case_orders
ORDER BY order_id;
~~~

Những đơn ngoài hai mã \`D\` và \`C\` nhận \`selected_label = NULL\`. Không phải SQL báo lỗi, nhưng việc để NULL có thể khiến nhãn biến mất trong báo cáo hoặc bị bỏ qua khi dùng \`COUNT(selected_label)\`.

### Vì sao \`WHEN NULL\` trong simple CASE không bắt NULL?

Ví dụ **không nên dùng**:

~~~sql
CASE status_code
    WHEN NULL THEN 'Thiếu trạng thái'
    ELSE 'Có mã'
END
~~~

Simple CASE dựa trên phép so sánh bằng. Trong SQL, **\`NULL = NULL\` cho UNKNOWN**, không phải TRUE, nên nhánh \`WHEN NULL\` sẽ không khớp với mã NULL. Muốn kiểm tra NULL, dùng **\`IS NULL\` trong searched CASE**.

## 5. Dạng thứ hai: searched CASE để kiểm tra điều kiện

**Searched CASE** cho phép mỗi nhánh \`WHEN\` có một điều kiện đầy đủ:

~~~sql
CASE
    WHEN condition_1 THEN result_1
    WHEN condition_2 THEN result_2
    ELSE default_result
END
~~~

Điều kiện có thể dùng \`=\`, \`<\`, \`>=\`, \`IN\`, \`IS NULL\`, \`AND\`, \`OR\`, \`EXISTS\` và những biểu thức logic SQL phù hợp.

### 5.1. Phân biệt mã NULL với mã chưa được hỗ trợ

~~~sql
SELECT
    order_id,
    status_code,
    CASE
        WHEN status_code IS NULL THEN 'Thiếu trạng thái'
        WHEN status_code = 'P' THEN 'Chờ xử lý'
        WHEN status_code = 'D' THEN 'Đã thanh toán'
        WHEN status_code = 'S' THEN 'Đang giao'
        WHEN status_code = 'C' THEN 'Hoàn tất'
        WHEN status_code = 'X' THEN 'Đã hủy'
        WHEN status_code = 'R' THEN 'Đã hoàn trả'
        ELSE 'Mã trạng thái chưa hỗ trợ'
    END AS status_label
FROM demo_case_orders
ORDER BY order_id;
~~~

Lúc này:

- **Đơn 8:** “Thiếu trạng thái”.
- **Đơn 9:** “Mã trạng thái chưa hỗ trợ”.
- Những đơn mang mã được nhận diện: nhãn tương ứng.

Việc phân biệt rõ **thiếu mã** với **mã ngoài danh mục** giúp sửa dữ liệu và bảo trì hệ thống hiệu quả hơn. Một nhãn chung “Khác” có thể phù hợp cho đồ thị tổng quan, nhưng không nên làm mất khả năng tìm ra dữ liệu bất thường.

### 5.2. Kết hợp nhiều điều kiện trong cùng một nhánh

Ví dụ, một đơn được gắn nhãn **“Cần chú ý”** nếu **ưu tiên** hoặc có **giá trị từ 1.500.000 đồng**:

~~~sql
SELECT
    order_id,
    is_priority,
    amount_vnd,
    CASE
        WHEN is_priority IS TRUE OR amount_vnd >= 1500000
            THEN 'Cần chú ý'
        ELSE 'Thông thường'
    END AS attention_label
FROM demo_case_orders
ORDER BY order_id;
~~~

Ở đây \`is_priority\` có thể NULL. Cách viết **\`IS TRUE\`** thể hiện rằng chỉ những hàng được xác nhận ưu tiên mới thỏa vế đầu. Nếu \`is_priority\` NULL nhưng \`amount_vnd >= 1500000\` TRUE, kết quả \`OR\` vẫn TRUE.

### CASE là biểu thức, không phải câu lệnh điều khiển luồng chương trình

Trong các ví dụ trên, \`CASE ... END\` **trả về một giá trị** cho từng hàng. Nó khác với cấu trúc \`IF/ELSE\` điều khiển các câu lệnh trong một ngôn ngữ lập trình thủ tục. Trong SQL truy vấn, có thể đặt \`CASE\` ngay trong danh sách cột:

~~~sql
SELECT
    order_id,
    CASE WHEN amount_vnd > 0 THEN 'Có tiền' ELSE 'Không có tiền' END
        AS amount_state
FROM demo_case_orders;
~~~

Mỗi hàng kết quả có thêm một giá trị dẫn xuất, nhưng bảng gốc **không tự thêm cột \`amount_state\`**.

## 6. Phân loại số tiền theo các khoảng không chồng lấn

Yêu cầu:

- **Nhỏ:** từ 0 đến dưới **500.000**.
- **Vừa:** từ **500.000** đến dưới **1.500.000**.
- **Lớn:** từ **1.500.000** trở lên.

Viết bằng searched CASE:

~~~sql
SELECT
    order_id,
    amount_vnd,
    CASE
        WHEN amount_vnd < 500000 THEN 'Nhỏ'
        WHEN amount_vnd < 1500000 THEN 'Vừa'
        ELSE 'Lớn'
    END AS amount_band
FROM demo_case_orders
ORDER BY amount_vnd, order_id;
~~~

**Tại sao nhánh thứ hai không cần viết lại \`amount_vnd >= 500000\`?** Vì các nhánh được xét **theo thứ tự**. Những hàng có số tiền dưới 500.000 đã khớp nhánh thứ nhất; tới nhánh thứ hai, các hàng còn lại đều có số tiền từ 500.000 trở lên, do cột \`amount_vnd\` đã được khai báo \`NOT NULL\`.

Nếu viết đầy đủ, ta có thể dùng:

~~~sql
CASE
    WHEN amount_vnd >= 0 AND amount_vnd < 500000 THEN 'Nhỏ'
    WHEN amount_vnd >= 500000 AND amount_vnd < 1500000 THEN 'Vừa'
    WHEN amount_vnd >= 1500000 THEN 'Lớn'
    ELSE 'Ngoài phạm vi'
END
~~~

Hai cách cho cùng phân loại trên dữ liệu mẫu, nhưng cách thứ hai giải thích rõ **cận dưới và cận trên** của từng khoảng, đặc biệt hữu ích khi cần xem xét dữ liệu không hợp lệ hoặc cột cho phép NULL.

### 6.1. Giá trị đúng tại ranh giới

| amount_vnd | So sánh đầu tiên đúng? | Nhóm |
| ---: | --- | --- |
| 0 | \`amount_vnd < 500000\` | Nhỏ |
| 499999 | \`amount_vnd < 500000\` | Nhỏ |
| **500000** | Nhánh \`< 1500000\` | **Vừa** |
| 1499999 | Nhánh \`< 1500000\` | Vừa |
| **1500000** | Nhánh \`ELSE\` | **Lớn** |
| 2400000 | Nhánh \`ELSE\` | Lớn |

Chọn \`<\` hay \`<=\` là quyết định xác định **ranh giới nhóm**. Nếu dùng sai dấu, một giá trị đúng tại ngưỡng có thể vào nhóm sai.

### 6.2. Quy tắc chồng lấn: nhánh đầu tiên đúng được chọn

Giả sử viết:

~~~sql
CASE
    WHEN amount_vnd >= 500000 THEN 'Từ 500 nghìn trở lên'
    WHEN amount_vnd >= 1500000 THEN 'Từ 1,5 triệu trở lên'
    ELSE 'Dưới 500 nghìn'
END
~~~

Nhánh thứ hai **không thể được chọn** với dữ liệu không NULL: số tiền từ 1.500.000 trở lên cũng thỏa nhánh thứ nhất. \`CASE\` chọn **kết quả của nhánh WHEN đầu tiên có điều kiện TRUE**.

Nếu các quy tắc cùng dựa trên **ngưỡng tối thiểu**, thường cần đặt **ngưỡng cao nhất trước**:

~~~sql
CASE
    WHEN amount_vnd >= 1500000 THEN 'Lớn'
    WHEN amount_vnd >= 500000 THEN 'Vừa'
    ELSE 'Nhỏ'
END
~~~

Hoặc giữ cách xếp **cận trên tăng dần** như ví dụ chính. Điều quan trọng là các nhánh cùng nhau tạo ra phân loại **đúng và đủ** cho mọi giá trị hợp lệ.

## 7. Phân loại khi cột nguồn có NULL

Bảng mẫu khai báo \`amount_vnd NOT NULL\`, nhưng nhiều bảng thật cho phép số tiền chưa xác định. Khi đó:

~~~sql
CASE
    WHEN amount_vnd < 500000 THEN 'Nhỏ'
    WHEN amount_vnd < 1500000 THEN 'Vừa'
    ELSE 'Lớn'
END
~~~

sẽ đưa **NULL vào nhóm “Lớn”**: cả hai phép so sánh với NULL trả **UNKNOWN**, không nhánh nào có điều kiện TRUE, nên chạy \`ELSE\`.

Đây là lỗi phân loại rất dễ bỏ sót. Nếu cột nullable, nên viết:

~~~sql
CASE
    WHEN amount_vnd IS NULL THEN 'Chưa có số tiền'
    WHEN amount_vnd < 500000 THEN 'Nhỏ'
    WHEN amount_vnd < 1500000 THEN 'Vừa'
    ELSE 'Lớn'
END
~~~

Trong searched CASE, điều kiện \`WHEN\` chỉ được chọn khi trả **TRUE**. **FALSE** và **UNKNOWN** đều chuyển sang kiểm tra nhánh tiếp theo. Vì vậy, xử lý NULL sớm giúp tránh việc dữ liệu thiếu rơi vào nhóm mặc định có ý nghĩa nghiệp vụ sai.

**Không tự động dùng \`COALESCE(amount_vnd, 0)\`** nếu NULL nghĩa là “chưa biết số tiền”: thay NULL bằng 0 sẽ ngầm gán dữ liệu thiếu vào nhóm “Nhỏ”. Chỉ làm như vậy khi nghiệp vụ đã xác định rằng NULL phải được hiểu là 0.

## 8. Kết hợp nhiều quy tắc và thứ tự ưu tiên

Một đơn có thể đồng thời thỏa nhiều tiêu chí. Ví dụ, đơn đã hủy có giá trị 2 triệu đồng; nếu chỉ xét số tiền, nó sẽ nhận nhãn “Lớn”, nhưng màn hình kiểm soát có thể muốn ưu tiên nhãn **“Không xử lý do đã hủy/hoàn trả”**.

~~~sql
SELECT
    order_id,
    status_code,
    amount_vnd,
    CASE
        WHEN status_code IN ('X', 'R')
            THEN 'Đã hủy hoặc hoàn trả'
        WHEN status_code IS NULL
            THEN 'Chưa rõ trạng thái'
        WHEN status_code NOT IN ('P', 'D', 'S', 'C', 'X', 'R')
            THEN 'Mã trạng thái bất thường'
        WHEN amount_vnd >= 1500000
            THEN 'Đơn giá trị lớn'
        WHEN amount_vnd >= 500000
            THEN 'Đơn giá trị vừa'
        ELSE 'Đơn giá trị nhỏ'
    END AS review_group
FROM demo_case_orders
ORDER BY order_id;
~~~

Trong ví dụ này:

- Đơn **5** (\`X\`) và **7** (\`R\`) được phân loại theo trạng thái **trước** khi xét giá trị.
- Đơn **8** có trạng thái NULL được chỉ ra là chưa rõ.
- Đơn **9** có mã \`Z\` được chỉ ra là mã bất thường.
- Những đơn có trạng thái được nhận diện và không thuộc nhóm hủy/hoàn trả mới được phân loại theo tiền.

Thứ tự nhánh chính là **thứ tự ưu tiên nghiệp vụ**. Khi thay đổi thứ tự, cùng một hàng có thể nhận nhóm khác. Hãy ghi rõ tại sao một quy tắc cần đứng trước quy tắc khác, nhất là khi CASE có nhiều điều kiện có thể đồng thời đúng.

### 8.1. Đừng dùng ELSE để che mã lạ

Ví dụ:

~~~sql
CASE
    WHEN status_code = 'C' THEN 'Hoàn tất'
    ELSE 'Chưa hoàn tất'
END
~~~

Ở đây mọi thứ không phải \`C\`, kể cả \`NULL\` và \`Z\`, đều thành “Chưa hoàn tất”. Đây có thể đúng nếu ta chỉ cần **phân nhóm nhị phân** “đã hoàn tất” so với “chưa được xác nhận là hoàn tất”. Nhưng nó sẽ **gây hiểu nhầm** nếu người đọc cần biết mã bất hợp lệ, dữ liệu thiếu, hoặc phân biệt “Đã hủy” với “Đang giao”.

Một nhãn báo cáo ngắn gọn không được coi là bằng chứng rằng dữ liệu nguồn đã hợp lệ. Có thể vừa hiển thị nhãn gộp vừa có cột riêng cho vấn đề dữ liệu.

## 9. Phân loại bằng CASE khác với lọc bằng WHERE

\`CASE\` **trả về một giá trị cho mỗi hàng**; \`WHERE\` **quyết định hàng nào được giữ lại**.

Ví dụ này gắn nhóm cho **mọi đơn**:

~~~sql
SELECT
    order_id,
    amount_vnd,
    CASE
        WHEN amount_vnd >= 1500000 THEN 'Lớn'
        WHEN amount_vnd >= 500000 THEN 'Vừa'
        ELSE 'Nhỏ'
    END AS amount_band
FROM demo_case_orders
ORDER BY order_id;
~~~

Ví dụ sau chỉ lấy **đơn từ 500.000 đồng trở lên**, đồng thời vẫn tạo nhãn:

~~~sql
SELECT
    order_id,
    amount_vnd,
    CASE
        WHEN amount_vnd >= 1500000 THEN 'Lớn'
        ELSE 'Vừa'
    END AS amount_band
FROM demo_case_orders
WHERE amount_vnd >= 500000
ORDER BY order_id;
~~~

Điều kiện \`WHERE\` đã loại các đơn nhỏ, nên trong danh sách còn lại nhánh ELSE chỉ còn ý nghĩa “Vừa”.

### 9.1. Lọc theo nhãn đã tính bằng CTE

Trong PostgreSQL và nhiều hệ SQL, **bí danh của biểu thức SELECT** như \`amount_band\` thường **không thể dùng trực tiếp trong WHERE của cùng cấp SELECT**, vì WHERE được xử lý về mặt logic trước khi danh sách SELECT tạo bí danh. Có thể viết biểu thức phân loại trong một **CTE**:

~~~sql
WITH classified AS (
    SELECT
        order_id,
        customer_id,
        amount_vnd,
        CASE
            WHEN amount_vnd < 500000 THEN 'Nhỏ'
            WHEN amount_vnd < 1500000 THEN 'Vừa'
            ELSE 'Lớn'
        END AS amount_band
    FROM demo_case_orders
)
SELECT order_id, customer_id, amount_vnd, amount_band
FROM classified
WHERE amount_band = 'Lớn'
ORDER BY amount_vnd DESC, order_id;
~~~

CTE giúp định nghĩa phân loại **một lần**, rồi dùng tên cột kết quả ở truy vấn bên ngoài. Nếu chỉ cần điều kiện ngưỡng, \`WHERE amount_vnd >= 1500000\` trực tiếp thường đơn giản và rõ ràng hơn.

## 10. Đếm và tổng hợp theo nhóm đã phân loại

Để biết có bao nhiêu đơn thuộc từng nhóm giá trị, tạo nhóm trong một CTE rồi dùng \`GROUP BY\`:

~~~sql
WITH classified AS (
    SELECT
        order_id,
        amount_vnd,
        CASE
            WHEN amount_vnd < 500000 THEN 'Nhỏ'
            WHEN amount_vnd < 1500000 THEN 'Vừa'
            ELSE 'Lớn'
        END AS amount_band
    FROM demo_case_orders
)
SELECT
    amount_band,
    COUNT(*) AS order_count,
    SUM(amount_vnd) AS total_amount_vnd
FROM classified
GROUP BY amount_band
ORDER BY CASE amount_band
    WHEN 'Nhỏ' THEN 1
    WHEN 'Vừa' THEN 2
    WHEN 'Lớn' THEN 3
    ELSE 99
END;
~~~

Mô hình gồm hai bước:

1. **Phân loại từng hàng** theo công thức \`CASE\`.
2. **Tổng hợp những hàng cùng nhóm** bằng \`COUNT(*)\` và \`SUM(amount_vnd)\`.

\`COUNT(*)\` đếm số hàng trong nhóm. \`SUM(amount_vnd)\` cộng tổng tiền trong nhóm. Hai chỉ tiêu có ý nghĩa khác nhau: có thể một nhóm ít đơn hơn nhưng tổng tiền lớn hơn.

### 10.1. Dùng CASE trong hàm tổng hợp có điều kiện

Không phải báo cáo nào cũng cần một hàng cho mỗi trạng thái. Đôi khi muốn **một hàng duy nhất chứa nhiều cột đếm**:

~~~sql
SELECT
    COUNT(*) AS all_orders,
    SUM(CASE WHEN status_code = 'C' THEN 1 ELSE 0 END)
        AS completed_orders,
    SUM(CASE WHEN status_code IN ('X', 'R') THEN 1 ELSE 0 END)
        AS cancelled_or_returned_orders,
    SUM(CASE WHEN status_code IS NULL THEN 1 ELSE 0 END)
        AS missing_status_orders,
    SUM(CASE WHEN status_code = 'Z' THEN 1 ELSE 0 END)
        AS unknown_code_orders
FROM demo_case_orders;
~~~

Với dữ liệu mẫu:

| all_orders | completed_orders | cancelled_or_returned_orders | missing_status_orders | unknown_code_orders |
| ---: | ---: | ---: | ---: | ---: |
| 14 | 4 | 2 | 1 | 1 |

**\`SUM(CASE WHEN ... THEN 1 ELSE 0 END)\`** biến điều kiện thành số 1 hoặc 0 cho từng hàng, rồi cộng lại.

Phân biệt với:

~~~sql
COUNT(CASE WHEN status_code = 'C' THEN 1 END)
~~~

Biểu thức này cũng đếm các hàng \`C\` vì nhánh không khớp trả NULL, và \`COUNT(expression)\` bỏ qua NULL. Nhưng cách viết sau **sai nếu mục tiêu là đếm số đơn hoàn tất**:

~~~sql
-- Sai ý định: COUNT đếm cả 0, vì 0 khác NULL.
COUNT(CASE WHEN status_code = 'C' THEN 1 ELSE 0 END)
~~~

\`COUNT(...)\` sẽ đếm mọi hàng nếu biểu thức luôn trả 1 hoặc 0.

### 10.2. FILTER là lựa chọn khác của PostgreSQL

PostgreSQL còn hỗ trợ:

~~~sql
SELECT
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (WHERE status_code = 'C')
        AS completed_orders,
    COUNT(*) FILTER (WHERE status_code IN ('X', 'R'))
        AS cancelled_or_returned_orders
FROM demo_case_orders;
~~~

Kết quả tương ứng với những phép đếm có điều kiện ở trên. \`FILTER\` thường rất dễ đọc với nhiều chỉ tiêu; nhưng hỗ trợ của nó khác nhau giữa các hệ quản trị. \`SUM(CASE ...)\` là mẫu biểu thức phổ biến khi cần viết SQL đa phương ngữ.

### 10.3. Lọc trạng thái trước khi tính một chỉ tiêu tiền

Nếu quy ước báo cáo chỉ tính các đơn \`D\`, \`S\`, \`C\` là nhóm **đủ điều kiện phân tích giá trị bán hàng**, hãy lọc theo mã gốc:

~~~sql
SELECT
    SUM(CASE
        WHEN status_code IN ('D', 'S', 'C') THEN amount_vnd
        ELSE 0
    END) AS eligible_amount_vnd
FROM demo_case_orders;
~~~

Kết quả với dữ liệu mẫu là **6.960.000 VND**. Đây là **quy ước phân tích minh họa**, không phải khẳng định cách ghi nhận doanh thu kế toán. Trạng thái \`R\` có thể liên quan đến hoàn tiền; hệ thống thật phải xét thêm thanh toán, hoàn trả, thuế và phí.

Việc tổng hợp dựa trên **status_code** giúp tránh rủi ro khi nhãn hiển thị được đổi ngôn ngữ hoặc biên tập lại.

## 11. Phân nhóm khách hàng từ dữ liệu đã tổng hợp

Đôi khi phân loại cần **thống kê trước**, chứ không chỉ đọc một hàng. Ví dụ:

- **VIP:** tổng giá trị đơn thuộc trạng thái \`D\`, \`S\`, \`C\` từ **2.000.000 VND**.
- **Thân thiết:** tổng giá trị từ **500.000 VND** đến dưới 2.000.000 VND.
- **Cơ bản:** có ít nhất một đơn thuộc các trạng thái đó nhưng tổng dưới 500.000 VND.
- **Chưa có đơn hợp lệ:** không có đơn thuộc các trạng thái được tính.

Không thể dùng trực tiếp \`SUM(amount_vnd)\` như một thuộc tính của từng hàng trước khi gom nhóm. Hãy tổng hợp theo \`customer_id\` trong một CTE, rồi \`CASE\` trên kết quả:

~~~sql
WITH customer_totals AS (
    SELECT
        customer_id,
        COUNT(*) FILTER (
            WHERE status_code IN ('D', 'S', 'C')
        ) AS eligible_order_count,
        SUM(CASE
            WHEN status_code IN ('D', 'S', 'C') THEN amount_vnd
            ELSE 0
        END) AS eligible_amount_vnd
    FROM demo_case_orders
    GROUP BY customer_id
)
SELECT
    customer_id,
    eligible_order_count,
    eligible_amount_vnd,
    CASE
        WHEN eligible_order_count = 0
            THEN 'Chưa có đơn hợp lệ'
        WHEN eligible_amount_vnd >= 2000000
            THEN 'VIP'
        WHEN eligible_amount_vnd >= 500000
            THEN 'Thân thiết'
        ELSE 'Cơ bản'
    END AS customer_segment
FROM customer_totals
ORDER BY customer_id;
~~~

Ví dụ:

- Khách **12** có đơn 4 hoàn tất trị giá **2.400.000**, nên thuộc **VIP**.
- Khách **10** có đơn 2 và 11 thuộc các trạng thái hợp lệ, tổng **830.000**, nên thuộc **Thân thiết**.
- Khách **13** chỉ có đơn bị hủy, nên thuộc **Chưa có đơn hợp lệ**.
- Khách **16** có một đơn mã \`D\` trị giá **0** và một đơn mã lạ \`Z\`; theo quy tắc minh họa, khách này thuộc **Cơ bản** vì có một đơn hợp lệ nhưng tổng bằng 0.

Điều này minh họa một nguyên tắc quan trọng: **phân loại là kết quả của quy tắc đã chọn**, không phải một sự thật độc lập tồn tại trong mọi báo cáo. Thay danh sách trạng thái hoặc ngưỡng giá trị sẽ thay nhóm khách hàng.

## 12. Sắp xếp theo thứ tự nghiệp vụ

Nếu sắp theo tên nhãn bằng \`ORDER BY status_label\`, hệ quản trị sắp chữ theo collation, thường không trùng thứ tự mong muốn trong quy trình xử lý đơn.

Ví dụ yêu cầu thứ tự:

1. Chờ xử lý (\`P\`).
2. Đã thanh toán (\`D\`).
3. Đang giao (\`S\`).
4. Hoàn tất (\`C\`).
5. Đã hủy (\`X\`).
6. Đã hoàn trả (\`R\`).
7. Thiếu mã hoặc mã lạ.

Ánh xạ mã thành **số thứ tự** riêng:

~~~sql
SELECT
    order_id,
    status_code,
    CASE status_code
        WHEN 'P' THEN 1
        WHEN 'D' THEN 2
        WHEN 'S' THEN 3
        WHEN 'C' THEN 4
        WHEN 'X' THEN 5
        WHEN 'R' THEN 6
        ELSE 99
    END AS status_sort_rank
FROM demo_case_orders
ORDER BY status_sort_rank, order_id;
~~~

Vì \`status_sort_rank\` là một biểu thức trong SELECT, PostgreSQL cho phép dùng **bí danh** của nó trong \`ORDER BY\` cùng cấp. Cột \`order_id\` phá hòa để thứ tự giữa các đơn cùng trạng thái ổn định.

**Không dùng nhãn ngôn ngữ tự nhiên làm khóa sắp xếp nghiệp vụ** nếu thứ tự cần được kiểm soát. Khi có bảng danh mục, số thứ tự nên được lưu như thuộc tính riêng \`sort_order\`.

## 13. Ánh xạ mã bằng bảng danh mục thay cho CASE dài

CASE thích hợp khi **ít mã, hiếm thay đổi và chỉ dùng trong vài truy vấn**. Khi có nhiều trạng thái, nhiều ngôn ngữ, thứ tự hiển thị, quy tắc hợp lệ hoặc nhiều báo cáo cùng dùng, một **bảng danh mục** (*lookup/reference table*) thường dễ quản lý hơn.

Tạo bảng tạm:

~~~sql
CREATE TEMP TABLE demo_status_catalog (
    status_code TEXT PRIMARY KEY,
    label_vi    TEXT NOT NULL,
    label_en    TEXT NOT NULL,
    sort_order  INTEGER NOT NULL UNIQUE,
    eligible_for_sales BOOLEAN NOT NULL
);

INSERT INTO demo_status_catalog
    (status_code, label_vi, label_en, sort_order, eligible_for_sales)
VALUES
    ('P', 'Chờ xử lý',      'Pending',   1, FALSE),
    ('D', 'Đã thanh toán',  'Paid',      2, TRUE),
    ('S', 'Đang giao',      'Shipping',  3, TRUE),
    ('C', 'Hoàn tất',       'Completed', 4, TRUE),
    ('X', 'Đã hủy',         'Cancelled', 5, FALSE),
    ('R', 'Đã hoàn trả',    'Returned',  6, FALSE);
~~~

Trong bảng danh mục, **mỗi mã chỉ xuất hiện một lần** nhờ PRIMARY KEY. Cột \`label_vi\` là nhãn tiếng Việt; \`label_en\` là nhãn tiếng Anh; \`sort_order\` quy định thứ tự nghiệp vụ; \`eligible_for_sales\` biểu diễn **quy ước phân tích của ví dụ**.

### 13.1. JOIN để lấy nhãn

~~~sql
SELECT
    o.order_id,
    o.status_code,
    s.label_vi,
    s.label_en,
    s.sort_order
FROM demo_case_orders AS o
LEFT JOIN demo_status_catalog AS s
    ON s.status_code = o.status_code
ORDER BY o.order_id;
~~~

\`LEFT JOIN\` giữ **tất cả đơn hàng**. Các đơn có trạng thái không khớp danh mục sẽ vẫn tồn tại trong kết quả:

- Đơn **8** (mã NULL) không khớp bản ghi danh mục nào.
- Đơn **9** (mã \`Z\`) cũng không khớp vì danh mục chưa định nghĩa mã \`Z\`.

Khi không khớp, các cột \`s.label_vi\`, \`s.label_en\`, \`s.sort_order\` đều NULL.

Nếu dùng \`INNER JOIN\`, hai đơn này **biến mất khỏi kết quả**, có thể khiến báo cáo đếm thiếu dữ liệu. Khi mục đích là **hiển thị và chẩn đoán mã lạ**, \`LEFT JOIN\` thường hữu ích hơn.

### 13.2. Dùng CASE để phân biệt lỗi sau JOIN

~~~sql
SELECT
    o.order_id,
    o.status_code,
    CASE
        WHEN o.status_code IS NULL THEN 'Thiếu trạng thái'
        WHEN s.status_code IS NULL THEN 'Mã chưa được cấu hình'
        ELSE s.label_vi
    END AS status_label
FROM demo_case_orders AS o
LEFT JOIN demo_status_catalog AS s
    ON s.status_code = o.status_code
ORDER BY o.order_id;
~~~

Ở đây \`CASE\` vẫn rất hữu ích, nhưng chỉ xử lý **ngoại lệ**. Các nhãn chính được duy trì trong **bảng danh mục**, không lặp lại ở mọi truy vấn.

### 13.3. Tìm mã không hợp lệ để làm sạch dữ liệu

~~~sql
SELECT o.order_id, o.status_code
FROM demo_case_orders AS o
LEFT JOIN demo_status_catalog AS s
    ON s.status_code = o.status_code
WHERE o.status_code IS NOT NULL
  AND s.status_code IS NULL
ORDER BY o.order_id;
~~~

Kết quả là **đơn 9 với mã \`Z\`**. Điều kiện đầu tiên cố ý loại trường hợp chưa có mã; nếu muốn tìm **cả mã thiếu và mã lạ**, có thể bỏ \`o.status_code IS NOT NULL\`.

### 13.4. Khi nào nên có FOREIGN KEY?

Trong một thiết kế thật, cột \`orders.status_code\` có thể tham chiếu \`status_catalog.status_code\` bằng **FOREIGN KEY**, nhờ đó các mã không có trong danh mục bị từ chối khi ghi dữ liệu.

~~~sql
-- Minh họa ý tưởng áp dụng cho bảng đã làm sạch dữ liệu:
ALTER TABLE orders
ADD CONSTRAINT fk_orders_status
FOREIGN KEY (status_code)
REFERENCES status_catalog(status_code);
~~~

Đoạn này **chỉ minh họa trên tên bảng nghiệp vụ giả định**, không chạy trực tiếp trên các bảng tạm của phần thực hành: dữ liệu tạm đang cố ý có mã \`Z\`, nên thêm FK sẽ thất bại nếu chưa sửa hoặc loại mã sai. Một FOREIGN KEY thông thường cũng **không cấm NULL**; nếu mã trạng thái là bắt buộc, cần thêm **NOT NULL**.

**Một bảng danh mục có FK kiểm soát miền mã**, còn CASE chỉ định nghĩa cách đọc giá trị. CASE trong SELECT không ngăn người dùng chèn \`'Z'\` vào bảng.

## 14. CASE và bảng danh mục: chọn cách nào?

| Tiêu chí | CASE trong truy vấn | Bảng danh mục + JOIN |
| --- | --- | --- |
| Số mã nhỏ, ít thay đổi | Gọn và trực tiếp | Có thể hơi nhiều cấu trúc |
| Nhiều màn hình/báo cáo dùng chung | Dễ lặp công thức | Duy trì một nguồn nhãn |
| Nhãn tiếng Việt/Anh hoặc nhiều ngôn ngữ | CASE dài và khó bảo trì | Có thể dùng các cột nhãn hoặc bảng bản dịch |
| Thứ tự hiển thị riêng | Thêm CASE tạo rank | Lưu \`sort_order\` |
| Kiểm soát mã hợp lệ khi INSERT/UPDATE | Không thực hiện được chỉ bằng SELECT CASE | Có thể dùng FOREIGN KEY |
| Ngưỡng số tiền thay đổi thường xuyên | Phải đổi SQL hoặc lớp ứng dụng | Có thể dùng bảng cấu hình khoảng với quy tắc không chồng lấn |
| Quy tắc phức hợp dựa trên nhiều thuộc tính | Searched CASE trực quan | Có thể cần bảng quy tắc hoặc logic bổ sung |
| Cần nhìn thấy mã lạ/NULL | ELSE và IS NULL | LEFT JOIN + điều kiện kiểm tra |

**Không có một lựa chọn phù hợp cho mọi trường hợp.** Một ứng dụng có thể dùng **bảng danh mục cho mã chuẩn**, đồng thời dùng **CASE cho phân loại động**. Với nhãn cần dịch theo nhiều ngôn ngữ, bảng bản dịch có khóa \`(status_code, language_code)\` thường mở rộng tốt hơn việc thêm một cột cho mỗi ngôn ngữ mãi mãi.

### Bảng phân loại khoảng giá trị

Nếu ngưỡng phân loại được người quản trị thay đổi thường xuyên, cũng có thể lưu các khoảng trong bảng:

~~~sql
CREATE TEMP TABLE demo_amount_bands (
    band_code  TEXT PRIMARY KEY,
    label_vi   TEXT NOT NULL,
    min_value  NUMERIC(12, 2) NOT NULL,
    max_value  NUMERIC(12, 2),
    sort_order INTEGER NOT NULL UNIQUE,
    CHECK (max_value IS NULL OR min_value < max_value)
);

INSERT INTO demo_amount_bands
    (band_code, label_vi, min_value, max_value, sort_order)
VALUES
    ('SMALL',  'Nhỏ', 0,       500000,  1),
    ('MEDIUM', 'Vừa', 500000,  1500000, 2),
    ('LARGE',  'Lớn', 1500000, NULL,    3);
~~~

Quy ước **cận dưới bao gồm, cận trên loại trừ**:

~~~sql
SELECT
    o.order_id,
    o.amount_vnd,
    b.band_code,
    b.label_vi
FROM demo_case_orders AS o
JOIN demo_amount_bands AS b
    ON o.amount_vnd >= b.min_value
   AND (b.max_value IS NULL OR o.amount_vnd < b.max_value)
ORDER BY o.order_id;
~~~

Bảng khoảng cần thêm cơ chế quản trị để **không tạo khoảng chồng lấn hoặc khoảng trống**. CHECK \`min_value < max_value\` trên từng hàng **chưa đủ** để đảm bảo hai hàng khác nhau không chồng lấn. Nếu hai khoảng chồng nhau, một đơn có thể JOIN ra **hai dòng**, làm sai số lượng hoặc tổng tiền. Vì vậy, dùng bảng quy tắc mang lại tính linh hoạt nhưng cũng đòi hỏi **quy trình kiểm soát quy tắc**.

## 15. Kiểu dữ liệu của kết quả CASE

Các nhánh \`THEN\` và \`ELSE\` của CASE cùng tạo nên **một cột kết quả**, vì vậy hệ quản trị phải xác định được **kiểu dữ liệu chung** cho các nhánh.

Ví dụ hợp lý:

~~~sql
SELECT
    order_id,
    CASE
        WHEN amount_vnd >= 1500000 THEN 'Lớn'
        ELSE 'Chưa lớn'
    END AS amount_label
FROM demo_case_orders;
~~~

Tất cả nhánh trả văn bản. Ví dụ tạo rank:

~~~sql
SELECT
    order_id,
    CASE
        WHEN status_code = 'P' THEN 1
        WHEN status_code = 'D' THEN 2
        ELSE 99
    END AS sort_rank
FROM demo_case_orders;
~~~

Tất cả nhánh trả số nguyên. Nếu cố ghép nhánh số nguyên và văn bản không chuyển đổi được, ví dụ \`THEN 1 ELSE 'Không rõ'\`, PostgreSQL có thể báo lỗi kiểu dữ liệu hoặc chuyển kiểu. Nên chọn **một loại kết quả rõ ràng**; nếu cần cả mã số và nhãn, trả thành **hai cột riêng**.

### CASE không nhất thiết trả TEXT

~~~sql
SELECT
    order_id,
    CASE
        WHEN status_code IN ('D', 'S', 'C') THEN amount_vnd
        ELSE 0::NUMERIC
    END AS eligible_amount_vnd
FROM demo_case_orders;
~~~

Biểu thức trên trả **giá trị số**, phục vụ SUM/AVG. Có thể trả BOOLEAN, DATE hoặc kiểu khác nếu các nhánh tương thích và phương ngữ hỗ trợ. Đừng ép kết quả sang chuỗi quá sớm khi vẫn cần tính toán.

### CASE không đảm bảo loại bỏ mọi lỗi đánh giá biểu thức

Trong PostgreSQL, \`CASE\` về ngữ nghĩa chọn kết quả của nhánh đầu tiên phù hợp. Nhưng **không nên dựa vào CASE như một cam kết tuyệt đối về thứ tự thực thi mọi biểu thức**: bộ tối ưu có thể đánh giá trước một số biểu thức hằng hoặc biến đổi biểu thức trong giai đoạn lập kế hoạch.

Khi cần tránh lỗi như chia cho 0 trong biểu thức, có thể dùng phép biến đổi dữ liệu an toàn:

~~~sql
SELECT
    order_id,
    amount_vnd / NULLIF(customer_id - 10, 0) AS ratio_demo
FROM demo_case_orders;
~~~

\`NULLIF(..., 0)\` biến mẫu số bằng 0 thành NULL, nên phép chia trả NULL thay vì phép chia cho 0. Đây chỉ là ví dụ về biểu thức an toàn; phép chia cho \`customer_id - 10\` không có ý nghĩa nghiệp vụ.

## 16. Hiệu năng và khả năng bảo trì

CASE là biểu thức phổ biến và thường phù hợp cho phân loại trực tiếp trong SELECT. Tuy nhiên, cách viết có thể ảnh hưởng đến khả năng dùng chỉ mục và cách bảo trì.

### 16.1. Lọc theo cột gốc khi điều kiện đơn giản

Nếu chỉ cần đơn từ 1.500.000 đồng trở lên:

~~~sql
SELECT order_id, amount_vnd
FROM demo_case_orders
WHERE amount_vnd >= 1500000;
~~~

thường rõ ràng hơn việc tạo nhãn rồi lọc:

~~~sql
WITH x AS (
    SELECT
        order_id,
        amount_vnd,
        CASE WHEN amount_vnd >= 1500000
             THEN 'Lớn' ELSE 'Khác' END AS band
    FROM demo_case_orders
)
SELECT order_id, amount_vnd
FROM x
WHERE band = 'Lớn';
~~~

Truy vấn trực tiếp theo \`amount_vnd\` cũng có thể phù hợp với chỉ mục B-tree thông thường trên cột số. Một biểu thức CASE phức tạp trong bộ lọc có thể khiến hệ quản trị khó khai thác chỉ mục trực tiếp hơn; kết quả thực tế tùy bộ tối ưu và dữ liệu.

### 16.2. Tránh sao chép một CASE dài ở nhiều nơi

Nếu cùng một bảng điều kiện được lặp lại trong SELECT, GROUP BY, ORDER BY và nhiều báo cáo, nguy cơ **một nơi đổi ngưỡng, nơi khác chưa đổi** tăng lên. Có thể:

- Định nghĩa phân loại trong **CTE hoặc VIEW** rồi dùng lại.
- Chuyển mã → nhãn sang **bảng danh mục** khi mã dùng chung.
- Tập trung ngưỡng vào **bảng quy tắc có kiểm soát** nếu thay đổi thường xuyên.
- Ghi rõ định nghĩa nghiệp vụ của mỗi nhóm, đặc biệt về NULL và khoảng biên.

Với phân loại dùng để báo cáo lịch sử, cần quyết định liệu báo cáo phải dùng **ngưỡng hiện tại** hay **ngưỡng tại thời điểm giao dịch**. Một CASE truy vấn theo ngưỡng mới có thể phân loại lại những hàng cũ, dù dữ liệu gốc không thay đổi. Nếu yêu cầu lịch sử phải bất biến, có thể cần lưu **phiên bản quy tắc** hoặc kết quả snapshot theo chính sách được phê duyệt.

### 16.3. Đừng kết luận hiệu năng chỉ từ độ ngắn của SQL

Một \`CASE\` ngắn hơn \`JOIN\` không có nghĩa chắc chắn nhanh hơn, và một \`JOIN\` dùng bảng danh mục không có nghĩa chắc chắn chậm. Hãy dựa vào quy mô dữ liệu, chỉ mục, mức độ dùng lại, loại truy vấn và kế hoạch thực thi (ví dụ \`EXPLAIN\` trên PostgreSQL) khi tối ưu hệ thống thật.

## 17. Những khác biệt theo phương ngữ

\`CASE\` dạng **simple** và **searched** là một phần quen thuộc của SQL và được hỗ trợ trong **PostgreSQL, MySQL, SQL Server, SQLite**. Tuy vậy, có những điểm cần chú ý:

| Chủ đề | Điểm cần xem khi đổi hệ quản trị |
| --- | --- |
| \`CASE ... WHEN ... THEN ... ELSE ... END\` | Cú pháp nền tảng tương đối di động |
| Kiểu kết quả | Quy tắc suy luận và ép kiểu giữa nhánh có thể khác |
| \`BOOLEAN\` trong ví dụ | SQL Server dùng \`BIT\`; MySQL/SQLite có biểu diễn khác; cú pháp \`IS TRUE\` không đồng nhất ở mọi hệ |
| \`FILTER (WHERE ...)\` | PostgreSQL hỗ trợ; một số hệ khác không có cú pháp tương ứng |
| Nối nhãn với mã bằng \`CONCAT\` | Hành vi NULL và cú pháp nối chuỗi khác theo hệ |
| So sánh văn bản | Collation và phân biệt hoa/thường có thể khác |
| \`LIMIT\` và \`TOP\` | Khác cú pháp giới hạn dòng |
| Bảng tạm | Cú pháp, thời gian tồn tại và phạm vi bảng tạm khác nhau |

Ví dụ thay phép đếm \`FILTER\` bằng CASE để dễ chuyển đổi:

~~~sql
SELECT
    SUM(CASE WHEN status_code = 'C' THEN 1 ELSE 0 END)
        AS completed_orders
FROM demo_case_orders;
~~~

Đây là biểu thức quen thuộc trong nhiều RDBMS. Khi viết SQL dùng cho nhiều nền tảng, hãy kiểm tra phiên bản và quy tắc kiểu dữ liệu cụ thể, nhất là các biểu thức \`CASE\` có nhánh trả dữ liệu không cùng kiểu.

## 18. Các lỗi thường gặp

| Hiểu nhầm hoặc cách viết | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng \`CASE status_code WHEN NULL\` | Không nhận diện mã NULL | Dùng searched CASE với \`status_code IS NULL\` |
| Bỏ \`ELSE\` mà mong có nhãn mặc định | Mã không khớp nhận NULL | Thêm ELSE có ý nghĩa, hoặc cố ý giữ NULL và giải thích |
| Gộp NULL và mã lạ chung nhãn “Khác” | Che mất vấn đề dữ liệu nguồn | Tách hai nhánh “Thiếu mã” và “Mã chưa hỗ trợ” |
| Đặt điều kiện ngưỡng thấp trước ngưỡng cao | Nhánh ngưỡng cao có thể không bao giờ tới | Sắp thứ tự hoặc tạo khoảng không chồng lấn |
| Dùng \`<=\` và \`<\` không nhất quán | Giá trị đúng ranh giới vào nhóm sai | Định nghĩa cận dưới/cận trên rõ ràng |
| Cột nullable rơi vào ELSE “Lớn” | NULL bị phân loại sai là số lớn | Viết nhánh \`IS NULL\` trước |
| Đếm bằng \`COUNT(CASE WHEN ... THEN 1 ELSE 0 END)\` | Đếm cả các hàng không khớp | Dùng \`SUM(CASE ... 1 ELSE 0 END)\` hoặc \`COUNT(CASE WHEN ... THEN 1 END)\` |
| Sắp nhãn tiếng Việt theo chữ cái | Không đúng thứ tự xử lý nghiệp vụ | CASE trả rank hoặc cột \`sort_order\` của danh mục |
| Dùng \`INNER JOIN\` với bảng danh mục để lấy nhãn | Mã lạ/NULL bị mất khỏi kết quả | Dùng LEFT JOIN khi cần giữ và chẩn đoán mọi hàng |
| Dùng CASE để “kiểm soát mã hợp lệ” | CASE không chặn mã sai khi INSERT | Dùng FOREIGN KEY/CHECK phù hợp |
| Bảng khoảng giá trị có vùng chồng lấn | JOIN có thể trả nhiều dòng cho một đơn | Kiểm soát không chồng lấn và không bỏ sót khoảng |
| Đổi nhãn nhưng dùng nhãn làm điều kiện nghiệp vụ | Thay cách gọi có thể làm báo cáo đổi nghĩa | Dùng mã gốc hoặc quy tắc nghiệp vụ ổn định |
| Các nhánh CASE trả số và chuỗi tùy ý | Lỗi hoặc ép kiểu ngoài dự định | Chọn kiểu kết quả rõ ràng, CAST khi cần |
| Lặp quy tắc ở nhiều báo cáo | Dễ lệch ngưỡng và nhãn | Tập trung biểu thức ở VIEW/CTE hoặc bảng quy tắc |

## 19. Bài tập thực hành

Sử dụng bảng \`demo_case_orders\` và bảng \`demo_status_catalog\` trong PostgreSQL.

1. Viết **simple CASE** đổi các mã \`P, D, S, C, X, R\` thành nhãn tiếng Việt. Xác định kết quả của đơn 8 và 9 khi ELSE = \`'Không xác định'\`.
2. Viết **searched CASE** để phân biệt riêng \`status_code IS NULL\` và mã \`Z\` chưa được hỗ trợ.
3. Phân loại \`amount_vnd\` theo ba nhóm **Nhỏ** (dưới 500.000), **Vừa** (500.000 đến dưới 1.500.000) và **Lớn** (từ 1.500.000). Kiểm tra riêng các đơn có amount_vnd đúng hai ngưỡng.
4. Đảo thứ tự các nhánh \`WHEN amount_vnd >= 500000\` và \`WHEN amount_vnd >= 1500000\`; giải thích vì sao nhãn “Lớn” có thể biến mất.
5. Tạo nhãn \`review_group\` ưu tiên đơn đã hủy/hoàn trả, sau đó mã thiếu, mã lạ, cuối cùng mới tới nhóm giá trị.
6. Dùng CTE phân loại từng đơn, sau đó **GROUP BY amount_band** để đếm số đơn và tính tổng tiền theo nhóm.
7. Dùng \`SUM(CASE ...)\` để đếm riêng đơn \`C\`, đơn \`X/R\`, đơn thiếu trạng thái, và đơn có mã \`Z\`.
8. Giải thích vì sao \`COUNT(CASE WHEN status_code='C' THEN 1 ELSE 0 END)\` không phải phép đếm số đơn hoàn tất đúng.
9. Dùng bảng \`demo_status_catalog\` và **LEFT JOIN** để hiển thị nhãn tiếng Việt, tiếng Anh và thứ tự sắp xếp; cho biết vì sao đơn 8, 9 vẫn hiện.
10. Dùng **INNER JOIN** thay LEFT JOIN và quan sát hàng nào biến mất. Giải thích tình huống nào có thể cho phép dùng INNER JOIN.
11. Viết truy vấn chỉ tìm các đơn có **mã chưa có trong danh mục nhưng không NULL**.
12. Sắp đơn theo thứ tự nghiệp vụ \`P → D → S → C → X → R → khác\`, sau đó theo \`order_id\`.
13. Dùng \`SUM(CASE WHEN status_code IN ('D','S','C') THEN amount_vnd ELSE 0 END)\` tính giá trị đơn theo quy ước minh họa. Không tính đơn \`X\`, \`R\`, \`P\`, NULL hoặc \`Z\`.
14. Tổng hợp theo từng khách hàng rồi phân nhóm **VIP/Thân thiết/Cơ bản/Chưa có đơn hợp lệ** như phần 11.
15. Tạo một trường hợp \`amount_vnd\` nullable trong một truy vấn CTE hoặc một bảng tạm mới. So sánh kết quả CASE **có** và **không có** nhánh \`WHEN amount_vnd IS NULL\`.
16. Tạo thêm hai khoảng giá trị **chồng lấn** trong một bảng thực hành riêng và giải thích vì sao phép JOIN bảng khoảng có thể tăng số dòng.
17. Viết lại phép đếm đơn hoàn tất bằng **FILTER** của PostgreSQL rồi bằng **SUM(CASE ...)\`** để so sánh khả năng chuyển sang hệ SQL khác.
18. Đề xuất thiết kế bảng mã trạng thái có **PRIMARY KEY**, nhãn tiếng Việt/Anh, thứ tự hiển thị và quy tắc FOREIGN KEY từ bảng đơn hàng sau khi dữ liệu cũ đã được làm sạch.

## 20. Câu hỏi tự kiểm tra

**Câu 1:** Simple CASE có bắt được \`status_code IS NULL\` bằng \`WHEN NULL\` không?

**Trả lời:** **Không.** Simple CASE dùng so sánh bằng, nên với NULL kết quả không phải TRUE. Dùng searched CASE với \`WHEN status_code IS NULL\`.

**Câu 2:** Một đơn 1.500.000 đồng nằm trong nhóm “Vừa” hay “Lớn” theo quy tắc đã nêu?

**Trả lời:** **Lớn**, vì nhóm Vừa kết thúc **trước** 1.500.000; nhóm Lớn bao gồm ngưỡng này.

**Câu 3:** Nếu không có ELSE và không có nhánh WHEN nào thỏa, CASE trả gì?

**Trả lời:** **NULL**.

**Câu 4:** Vì sao CASE phân loại theo ngưỡng phải để ý thứ tự WHEN?

**Trả lời:** SQL lấy kết quả của **nhánh đầu tiên có điều kiện TRUE**. Nếu một nhánh bao phủ luôn các nhánh phía sau, các nhánh sau không được chọn.

**Câu 5:** Khi dùng bảng danh mục, tại sao LEFT JOIN thường phù hợp để hiển thị và kiểm tra mã?

**Trả lời:** LEFT JOIN giữ mọi hàng nguồn, kể cả mã NULL hoặc mã chưa có trong danh mục. INNER JOIN sẽ loại những hàng không khớp.

**Câu 6:** CASE đổi mã \`C\` thành “Hoàn tất” có ngăn nhập mã \`Z\` không?

**Trả lời:** **Không.** CASE chỉ tạo giá trị đầu ra của truy vấn. Muốn kiểm soát mã hợp lệ khi ghi dữ liệu, sử dụng ràng buộc hoặc quy trình xác thực thích hợp.

**Câu 7:** Muốn đếm đơn hoàn tất, \`SUM(CASE WHEN status_code='C' THEN 1 ELSE 0 END)\` có đúng không?

**Trả lời:** **Có.** Mỗi đơn \`C\` góp 1, đơn khác góp 0.

**Câu 8:** Nhãn tiếng Việt nên dùng làm khóa liên kết giữa bảng đơn và bảng danh mục không?

**Trả lời:** **Không nên.** Nhãn là văn bản hiển thị và có thể đổi hoặc dịch. Nên liên kết bằng mã ổn định.

## 21. Ghi nhớ cốt lõi

**Phân loại dữ liệu** là áp dụng quy tắc để biến giá trị gốc thành nhóm; **ánh xạ mã thành nhãn** là biến mã đã được quy ước thành văn bản dễ hiểu. **\`CASE\` là biểu thức rẽ nhánh chính trong SQL**: simple CASE phù hợp với ánh xạ các mã cố định, còn searched CASE phù hợp với điều kiện, khoảng giá trị và ưu tiên nhiều quy tắc.

Luôn xác định rõ **ngưỡng biên**, **thứ tự WHEN**, **nhánh ELSE** và **cách xử lý NULL/mã lạ**. Với danh mục mã dùng chung, có nhiều ngôn ngữ hoặc thường thay đổi, hãy cân nhắc **bảng danh mục + LEFT JOIN**; với quy tắc dẫn xuất đơn giản, **CASE** thường là cách viết trực tiếp và dễ hiểu. **Nhãn hiển thị không thay thế mã gốc**, và việc tạo nhãn trong SELECT cũng không thay thế ràng buộc dữ liệu tại database.

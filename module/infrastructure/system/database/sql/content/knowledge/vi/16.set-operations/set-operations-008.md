# Độ ưu tiên phép toán và cách dùng dấu ngoặc

Khi kết hợp kết quả của nhiều câu `SELECT`, SQL cung cấp ba phép toán tập hợp quen thuộc: **`UNION`**, **`INTERSECT`** và **`EXCEPT`**. Mỗi phép trả lời một câu hỏi khác nhau: lấy các dòng thuộc một trong hai tập, lấy các dòng có ở cả hai tập, hoặc lấy những dòng của tập thứ nhất không thuộc tập thứ hai.

Nhưng khi một truy vấn chứa **từ ba nhánh `SELECT` trở lên**, câu hỏi không còn chỉ là “dùng phép toán nào?” mà còn là **“phép toán nào được thực hiện trước?”**. Ví dụ:

```sql
SELECT member_id FROM setlab_a
UNION
SELECT member_id FROM setlab_b
INTERSECT
SELECT member_id FROM setlab_c;
```

Truy vấn này có thể được đọc nhầm thành “gộp A và B trước, rồi lấy phần giao với C”. Trong **PostgreSQL**, cách hiểu đó **không đúng**: `INTERSECT` có độ ưu tiên cao hơn `UNION`, nên SQL tính **B giao C trước**, rồi mới hợp với A.

**Dấu ngoặc** giúp làm rõ và chủ động thay đổi cách nhóm các phép toán. Trong bài, dấu ngoặc vừa là công cụ **điều khiển ngữ nghĩa**, vừa là cách làm SQL dễ đọc, dễ kiểm thử và ít phụ thuộc quy tắc riêng của hệ quản trị.

Bài học thuộc chương **Phép toán tập hợp** của module Database SQL. Ví dụ chính sử dụng **PostgreSQL**; những lưu ý về khả chuyển giữa các hệ quản trị và phiên bản được trình bày ở phần sau.

## 1. Ôn nhanh ba phép toán tập hợp

Giả sử ta có ba tập ID:

```text
A = {1, 2, 3, 4}
B = {3, 4, 5}
C = {4, 5, 6}
```

Ở cách hiểu **tập hợp**, mỗi phần tử chỉ xuất hiện một lần.

| Phép toán | Ký hiệu toán học | Ý nghĩa | Kết quả với A và B |
|---|---|---|---|
| `UNION` | A ∪ B | Thuộc A **hoặc** B, có thể thuộc cả hai | `{1,2,3,4,5}` |
| `INTERSECT` | A ∩ B | Có trong **cả** A và B | `{3,4}` |
| `EXCEPT` | A \ B | Có trong A nhưng **không có trong** B | `{1,2}` |

Ví dụ SQL:

```sql
-- Hợp: mọi ID xuất hiện trong A hoặc B.
SELECT member_id FROM setlab_a
UNION
SELECT member_id FROM setlab_b;

-- Giao: ID có ở cả A và B.
SELECT member_id FROM setlab_a
INTERSECT
SELECT member_id FROM setlab_b;

-- Hiệu: ID chỉ lấy từ A mà không có trong B.
SELECT member_id FROM setlab_a
EXCEPT
SELECT member_id FROM setlab_b;
```

**Ba chú ý quan trọng:**

1. `UNION`, `INTERSECT`, `EXCEPT` mặc định mang hành vi **`DISTINCT`**: những dòng trùng nhau được loại bớt trong kết quả của phép toán tương ứng. Dạng `ALL` thay đổi cách xử lý số lần xuất hiện; xem mục 9.
2. `EXCEPT` **không có tính giao hoán**: `A EXCEPT B` thường khác `B EXCEPT A`.
3. Các phép toán trên tập dòng **không tự bảo đảm thứ tự hiển thị**. Muốn có thứ tự, viết `ORDER BY` ở đúng cấp truy vấn.

```text
A EXCEPT B = {1,2}
B EXCEPT A = {5}
```

Không nên đồng nhất `EXCEPT` với “lấy phần khác nhau của hai tập theo cả hai chiều”. Nếu cần hiệu đối xứng, phải diễn đạt một yêu cầu riêng, ví dụ `(A EXCEPT B) UNION (B EXCEPT A)`.

## 2. Dữ liệu thực hành và cách đọc kết quả

Để mọi ví dụ có thể chạy trong PostgreSQL, ta tạo ba **bảng tạm**, mỗi bảng có một cột `member_id INTEGER`. Dùng tên `setlab_` để tránh nhầm với bảng nghiệp vụ thật.

```sql
CREATE TEMP TABLE setlab_a (member_id INTEGER NOT NULL);
CREATE TEMP TABLE setlab_b (member_id INTEGER NOT NULL);
CREATE TEMP TABLE setlab_c (member_id INTEGER NOT NULL);

INSERT INTO setlab_a (member_id)
VALUES (1), (2), (3), (4);

INSERT INTO setlab_b (member_id)
VALUES (3), (4), (5);

INSERT INTO setlab_c (member_id)
VALUES (4), (5), (6);

SELECT 'A' AS source, member_id FROM setlab_a
UNION ALL
SELECT 'B', member_id FROM setlab_b
UNION ALL
SELECT 'C', member_id FROM setlab_c
ORDER BY source, member_id;
```

Các bảng tạm tồn tại trong **phiên kết nối PostgreSQL hiện tại** và tự biến mất khi phiên kết thúc. Nếu chạy lại nguyên đoạn `CREATE TEMP TABLE` trong cùng phiên, PostgreSQL có thể báo tên bảng đã tồn tại; hãy mở phiên mới hoặc chuẩn bị một tên khác. Không cần đụng đến dữ liệu thật để thực hành.

Ta sẽ dùng kết quả **`ORDER BY member_id`** để hiển thị theo thứ tự tăng dần, nhưng hãy nhớ: *thứ tự hiển thị là do `ORDER BY`, không phải do bản thân `UNION` hoặc `INTERSECT`*.

## 3. Quy tắc ưu tiên trong PostgreSQL

Với `UNION`, `INTERSECT` và `EXCEPT` thông thường, quy tắc cần nhớ trong **PostgreSQL** là:

1. **Dấu ngoặc** chỉ rõ nhóm cần thực hiện với nhau.
2. Nếu không có dấu ngoặc thay đổi nhóm, **`INTERSECT` được nhóm chặt hơn `UNION` và `EXCEPT`**.
3. **`UNION` và `EXCEPT` cùng mức ưu tiên**, được kết hợp **từ trái sang phải** khi xuất hiện liên tiếp ở cùng mức.

Có thể hình dung:

```text
Ưu tiên trong PostgreSQL cho các phép tập hợp

      ( ... )                 Nhóm theo dấu ngoặc
         ↓
      INTERSECT               Ưu tiên cao hơn
         ↓
      UNION / EXCEPT          Cùng mức; kết hợp trái → phải
```

Những quy tắc này nói về cách **phân tích cấu trúc biểu thức tập hợp**. Chúng không có nghĩa database nhất định phải chạy phép có ưu tiên cao hơn **trước về mặt thời gian vật lý**; bộ tối ưu được phép dùng kế hoạch thực thi khác miễn giữ ngữ nghĩa kết quả.

### 3.1. Cách hiểu đúng với ba nhánh

```sql
SELECT member_id FROM setlab_a
UNION
SELECT member_id FROM setlab_b
INTERSECT
SELECT member_id FROM setlab_c;
```

Với PostgreSQL, cách nhóm tương đương:

```text
A UNION (B INTERSECT C)
```

Chứ **không** phải:

```text
(A UNION B) INTERSECT C
```

Chỉ cần một cặp dấu ngoặc đặt khác vị trí là **tập kết quả có thể đổi**, như phần tiếp theo.

### 3.2. “Ưu tiên cao” khác “kết hợp trái sang phải”

Quy tắc kết hợp trái sang phải chỉ áp dụng khi các phép toán đang xét **ở cùng mức ưu tiên**. Không được đọc:

```text
A UNION B INTERSECT C
```

thành `(A UNION B) INTERSECT C` chỉ vì `UNION` xuất hiện trước trong dòng SQL. `INTERSECT` có mức ưu tiên cao hơn nên nó thuộc nhóm với B và C trước về mặt ngữ nghĩa.

Ngược lại, vì `UNION` và `EXCEPT` có cùng mức ưu tiên trong PostgreSQL, một chuỗi:

```text
A UNION B EXCEPT C
```

được nhóm từ trái sang phải thành `(A UNION B) EXCEPT C`.

## 4. Ví dụ quyết định: `UNION` đi cùng `INTERSECT`

Ta dùng lại:

```text
A = {1,2,3,4}
B = {3,4,5}
C = {4,5,6}
```

### 4.1. Không có dấu ngoặc: `INTERSECT` được nhóm trước

```sql
SELECT member_id FROM setlab_a
UNION
SELECT member_id FROM setlab_b
INTERSECT
SELECT member_id FROM setlab_c
ORDER BY member_id;
```

Phân tích theo hai bước:

```text
B INTERSECT C
    = {3,4,5} ∩ {4,5,6}
    = {4,5}

A UNION (B INTERSECT C)
    = {1,2,3,4} ∪ {4,5}
    = {1,2,3,4,5}
```

Kết quả:

| member_id |
|---:|
| 1 |
| 2 |
| 3 |
| 4 |
| 5 |

ID `1`, `2`, `3` xuất hiện dù không có trong C, vì chúng đã thuộc **A**, còn `INTERSECT C` chỉ áp dụng cho **nhánh B**.

### 4.2. Có dấu ngoặc: hợp A và B trước

Nếu nghiệp vụ yêu cầu “lấy những ID thuộc **A hoặc B**, nhưng đồng thời **phải thuộc C**”, cần nhóm A và B:

```sql
(SELECT member_id FROM setlab_a
 UNION
 SELECT member_id FROM setlab_b)
INTERSECT
SELECT member_id FROM setlab_c
ORDER BY member_id;
```

Diễn giải:

```text
(A UNION B) INTERSECT C
    = {1,2,3,4,5} ∩ {4,5,6}
    = {4,5}
```

Kết quả:

| member_id |
|---:|
| 4 |
| 5 |

### 4.3. Bảng đối chiếu

| Nhóm phép toán | Kết quả |
|---|---|
| `A UNION (B INTERSECT C)` | `{1,2,3,4,5}` |
| `(A UNION B) INTERSECT C` | `{4,5}` |

Hai câu có **cùng ba bảng và cùng hai phép toán**, chỉ khác cấu trúc nhóm. Đây là minh họa rõ nhất cho lý do phải quan tâm độ ưu tiên và dấu ngoặc.

```text
Không ghi dấu ngoặc                       Ghi dấu ngoặc chủ động

    UNION                                      INTERSECT
   /     \                                    /         \
  A    INTERSECT                            UNION        C
       /     \                              /    \
      B       C                            A      B

 A ∪ (B ∩ C)                              (A ∪ B) ∩ C
```

Hình trên là **cây ngữ nghĩa**, không phải sơ đồ trình tự thực thi bắt buộc của bộ máy database.

## 5. `EXCEPT` kết hợp với `INTERSECT`

`EXCEPT` là phép lấy hiệu; thứ tự áp dụng nó thường làm kết quả đổi đáng kể.

### 5.1. Không có dấu ngoặc: giao B và C trước

```sql
SELECT member_id FROM setlab_a
EXCEPT
SELECT member_id FROM setlab_b
INTERSECT
SELECT member_id FROM setlab_c
ORDER BY member_id;
```

PostgreSQL hiểu là:

```text
A EXCEPT (B INTERSECT C)
```

Tính:

```text
B ∩ C = {4,5}
A \ {4,5} = {1,2,3}
```

Kết quả là `{1,2,3}`.

### 5.2. Dùng dấu ngoặc để lấy hiệu trước rồi mới giao

```sql
(SELECT member_id FROM setlab_a
 EXCEPT
 SELECT member_id FROM setlab_b)
INTERSECT
SELECT member_id FROM setlab_c
ORDER BY member_id;
```

Diễn giải:

```text
(A EXCEPT B) INTERSECT C
    = {1,2} ∩ {4,5,6}
    = {}   -- tập rỗng
```

Truy vấn trả **0 dòng**.

### 5.3. Điều gì đã thay đổi?

| Cách viết | Ý nghĩa | Kết quả |
|---|---|---|
| `A EXCEPT (B INTERSECT C)` | Chỉ loại khỏi A những ID có trong **cả** B và C | `{1,2,3}` |
| `(A EXCEPT B) INTERSECT C` | Tìm ID có trong A nhưng không trong B, sau đó phải có trong C | `{}` |

Nếu không có dấu ngoặc, chỉ nhìn chữ `EXCEPT` đứng trước có thể khiến người đọc tự hình dung sai cấu trúc. Khi kết hợp `EXCEPT` với một phép khác, **nên ghi dấu ngoặc rõ ràng** ngay cả khi đã nhớ quy tắc của PostgreSQL.

## 6. `UNION` và `EXCEPT` cùng mức ưu tiên: kết hợp trái sang phải

Với PostgreSQL:

```text
A UNION B EXCEPT C
```

được nhóm thành:

```text
(A UNION B) EXCEPT C
```

Không phải `A UNION (B EXCEPT C)`.

### 6.1. Ví dụ hợp rồi trừ

```sql
SELECT member_id FROM setlab_a
UNION
SELECT member_id FROM setlab_b
EXCEPT
SELECT member_id FROM setlab_c
ORDER BY member_id;
```

Kết quả:

```text
A ∪ B = {1,2,3,4,5}
(A ∪ B) \ C = {1,2,3}
```

Nếu muốn “giữ nguyên A, chỉ lấy thêm những ID của B mà không thuộc C”, cần:

```sql
SELECT member_id FROM setlab_a
UNION
(SELECT member_id FROM setlab_b
 EXCEPT
 SELECT member_id FROM setlab_c)
ORDER BY member_id;
```

Lúc này:

```text
B \ C = {3}
A ∪ (B \ C) = {1,2,3,4}
```

ID `4` bị xóa trong phép `(A ∪ B) \ C`, nhưng **vẫn ở lại** trong `A ∪ (B \ C)` vì A được giữ nguyên. Dấu ngoặc phản ánh hai yêu cầu nghiệp vụ khác nhau.

### 6.2. Chiều `EXCEPT` cũng quan trọng

```sql
SELECT member_id FROM setlab_a
EXCEPT
SELECT member_id FROM setlab_b
UNION
SELECT member_id FROM setlab_c
ORDER BY member_id;
```

Theo kết hợp trái sang phải:

```text
(A \ B) ∪ C
    = {1,2} ∪ {4,5,6}
    = {1,2,4,5,6}
```

So với:

```sql
SELECT member_id FROM setlab_a
EXCEPT
(SELECT member_id FROM setlab_b
 UNION
 SELECT member_id FROM setlab_c)
ORDER BY member_id;
```

Kết quả:

```text
A \ (B ∪ C)
    = {1,2,3,4} \ {3,4,5,6}
    = {1,2}
```

**Nhớ:** `EXCEPT` không có tính giao hoán và nhìn chung cũng **không có tính kết hợp** như phép cộng:

```text
(A \ B) \ C   thường khác   A \ (B \ C)
```

Vì vậy, khi có hai phép `EXCEPT` trở lên, việc giữ nguyên hoặc đổi vị trí dấu ngoặc có thể thay đổi kết quả.

## 7. Gộp nhiều phép: đọc như cây biểu thức

Nếu một truy vấn có nhiều toán tử, đừng phân tích bằng cách đọc liên tục từ trái sang phải. Hãy **chia thành nhóm**.

Ví dụ:

```text
A UNION B INTERSECT C EXCEPT D
```

Theo quy tắc PostgreSQL, `B INTERSECT C` được nhóm trước. Sau đó `UNION` và `EXCEPT` cùng ưu tiên nên kết hợp trái sang phải:

```text
(A UNION (B INTERSECT C)) EXCEPT D
```

Trong SQL:

```sql
(SELECT member_id FROM setlab_a
 UNION
 (SELECT member_id FROM setlab_b
  INTERSECT
  SELECT member_id FROM setlab_c))
EXCEPT
SELECT member_id FROM another_table;
```

`another_table` là tên bảng minh họa chưa có trong dữ liệu thực hành; ví dụ chỉ diễn tả cấu trúc. Nếu cần chạy ngay, thay nó bằng một bảng có cột `member_id` tương thích.

### 7.1. Cách diễn giải nhanh

Một quy trình thực hành:

1. Khoanh các cặp dấu ngoặc đã có.
2. Trong từng phạm vi chưa bị dấu ngoặc chi phối, khoanh các phép `INTERSECT`.
3. Nhóm `UNION` và `EXCEPT` còn lại **từ trái sang phải** theo PostgreSQL.
4. Vẽ cây hoặc viết biểu thức bằng ký hiệu A, B, C.
5. Diễn đạt lại bằng lời để chắc chắn cây khớp yêu cầu nghiệp vụ.

Ví dụ yêu cầu “khách nằm trong A **hoặc** B, nhưng phải có trong C và **không có** trong D” thường được diễn đạt:

```text
((A UNION B) INTERSECT C) EXCEPT D
```

Lưu ý khác biệt với:

```text
A UNION (B INTERSECT (C EXCEPT D))
```

Ở biểu thức sau, các thành viên của A được giữ lại dù không có trong C hoặc có trong D. Dấu ngoặc phải theo **ý định lọc**, không theo thói quen viết ngắn.

## 8. Dấu ngoặc trong phép toán tập hợp khác ngoặc trong `WHERE`

Người học SQL đã quen dùng ngoặc khi phối hợp `AND` và `OR`:

```sql
SELECT customer_id
FROM customers
WHERE (is_active = TRUE OR is_vip = TRUE)
  AND country_code = 'VN';
```

Ngoặc ở đây nhóm **biểu thức điều kiện** bên trong **một** câu `SELECT`.

Trong phép toán tập hợp, dấu ngoặc nhóm **những câu `SELECT` hoàn chỉnh**:

```sql
(SELECT member_id FROM setlab_a
 UNION
 SELECT member_id FROM setlab_b)
INTERSECT
SELECT member_id FROM setlab_c;
```

Hai dạng ngoặc giải quyết **hai tầng logic khác nhau**.

### 8.1. Một cặp ngoặc `WHERE` không sửa được thứ tự tập hợp

```sql
SELECT member_id
FROM setlab_a
WHERE (member_id >= 2 AND member_id <= 4)
UNION
SELECT member_id
FROM setlab_b
INTERSECT
SELECT member_id
FROM setlab_c;
```

Ngoặc quanh `(member_id >= 2 AND member_id <= 4)` chỉ lọc nhánh A. Nó **không biến** cấu trúc `A UNION (B INTERSECT C)` thành `(A UNION B) INTERSECT C`.

Muốn thay thứ tự phép tập hợp, ngoặc phải **bao quanh nhánh `SELECT ... UNION ...`**, không chỉ bao quanh điều kiện `WHERE`.

### 8.2. Tránh nhầm với phép ngoặc biểu thức số học

```sql
SELECT (price * quantity) - discount AS amount
FROM order_lines;
```

Ngoặc ở đây chỉ định phép tính số học bên trong một `SELECT`, trong khi ngoặc ở phép tập hợp xác định cách kết hợp **tập dòng**. Cả hai đều là công cụ nhóm, nhưng vị trí và đối tượng được nhóm khác nhau.

## 9. `ALL` và `DISTINCT` tác động thế nào đến kết quả?

Trong SQL, bảng thường chứa **các dòng có thể trùng nhau** nếu không có ràng buộc duy nhất trên đúng bộ cột đang chọn. Vì vậy, các phép tập hợp SQL còn xử lý **số lần xuất hiện của mỗi dòng** (*bag/multiset semantics*).

### 9.1. Mặc định là loại trùng

```sql
SELECT member_id FROM setlab_a
UNION
SELECT member_id FROM setlab_b;
```

`UNION` mặc định tương ứng `UNION DISTINCT`: mỗi ID trong kết quả chỉ xuất hiện một lần. Tương tự, `INTERSECT` và `EXCEPT` mặc định loại các bản sao trùng trong kết quả phép toán.

```sql
SELECT member_id FROM setlab_a
UNION DISTINCT
SELECT member_id FROM setlab_b;
```

Là cách viết làm rõ `DISTINCT`; trong các ví dụ cơ bản, chỉ `UNION` đã đủ.

### 9.2. `UNION ALL` giữ các lần xuất hiện

```sql
SELECT member_id FROM setlab_a
UNION ALL
SELECT member_id FROM setlab_b
ORDER BY member_id;
```

Vì cả A và B đều có ID `3` và `4`, kết quả có:

```text
1, 2, 3, 3, 4, 4, 5
```

Trái lại, `UNION` cho:

```text
1, 2, 3, 4, 5
```

**`ALL` không làm thay đổi thứ tự ưu tiên của `UNION`, `INTERSECT`, `EXCEPT`**. Nó thay đổi cách phép toán cụ thể xử lý **số bản sao trùng**.

### 9.3. `INTERSECT ALL` và `EXCEPT ALL`

PostgreSQL hỗ trợ cả:

```sql
SELECT member_id FROM table_a
INTERSECT ALL
SELECT member_id FROM table_b;
```

```sql
SELECT member_id FROM table_a
EXCEPT ALL
SELECT member_id FROM table_b;
```

Nếu một giá trị xuất hiện `nA` lần trong nhánh A và `nB` lần trong nhánh B:

| Phép toán với `ALL` | Số lần giá trị xuất hiện ở kết quả |
|---|---|
| `A UNION ALL B` | `nA + nB` |
| `A INTERSECT ALL B` | `MIN(nA,nB)` |
| `A EXCEPT ALL B` | `MAX(nA-nB,0)` |

Với `UNION`, `INTERSECT`, `EXCEPT` **không `ALL`**, một giá trị tương ứng xuất hiện **0 hoặc 1 lần** trong kết quả.

### 9.4. Ví dụ có dữ liệu trùng

Ta tạo hai bảng tạm khác để tránh thay đổi tập A, B, C của bài:

```sql
CREATE TEMP TABLE setlab_bag_a (value INTEGER);
CREATE TEMP TABLE setlab_bag_b (value INTEGER);

INSERT INTO setlab_bag_a (value)
VALUES (1), (1), (2), (2), (3);

INSERT INTO setlab_bag_b (value)
VALUES (1), (2), (2), (2), (4);
```

Ở A: `1` xuất hiện 2 lần, `2` xuất hiện 2 lần, `3` xuất hiện 1 lần. Ở B: `1` xuất hiện 1 lần, `2` xuất hiện 3 lần, `4` xuất hiện 1 lần.

```sql
SELECT value FROM setlab_bag_a
INTERSECT ALL
SELECT value FROM setlab_bag_b
ORDER BY value;
-- 1, 2, 2
```

```sql
SELECT value FROM setlab_bag_a
EXCEPT ALL
SELECT value FROM setlab_bag_b
ORDER BY value;
-- 1, 3
```

Giải thích:

- `INTERSECT ALL` giữ `1` đúng `MIN(2,1)=1` lần, và `2` đúng `MIN(2,3)=2` lần.
- `EXCEPT ALL` giữ `1` đúng `MAX(2-1,0)=1` lần, không giữ `2` vì `MAX(2-3,0)=0`, và giữ `3` một lần vì B không có `3`.

Đây là một ví dụ quan trọng: khi dùng `ALL`, hai biểu thức có vẻ giống tập hợp toán học có thể khác nhau về **số dòng**.

## 10. Trộn `UNION ALL` với `UNION`: dấu ngoặc còn quan trọng hơn

Chỉ cần đổi cấu trúc nhóm là số bản sao trong kết quả có thể thay đổi.

Giả sử ba nguồn nhỏ:

```text
X = [1,1]      -- hai dòng có giá trị 1
Y = [1]        -- một dòng có giá trị 1
Z = [2]        -- một dòng có giá trị 2
```

### 10.1. Trường hợp không có ngoặc

Trong PostgreSQL, `UNION ALL` và `UNION` nằm cùng mức ưu tiên, kết hợp trái sang phải:

```text
X UNION ALL Y UNION Z
      ↓
(X UNION ALL Y) UNION Z
```

Phép `UNION` cuối **loại trùng khỏi kết quả kết hợp**, nên còn:

```text
1, 2
```

Ví dụ chạy được:

```sql
WITH
    x(v) AS (VALUES (1), (1)),
    y(v) AS (VALUES (1)),
    z(v) AS (VALUES (2)),
    combined AS (
        SELECT v FROM x
        UNION ALL
        SELECT v FROM y
        UNION
        SELECT v FROM z
    )
SELECT v, COUNT(*) AS times_seen
FROM combined
GROUP BY v
ORDER BY v;
-- v=1 có 1 lần; v=2 có 1 lần.
```

### 10.2. Thêm ngoặc: nhánh Y và Z hợp riêng trước

Nếu muốn giữ **toàn bộ hai dòng X**, rồi `UNION ALL` với tập đã khử trùng từ Y, Z:

```text
X UNION ALL (Y UNION Z)
```

```sql
WITH
    x(v) AS (VALUES (1), (1)),
    y(v) AS (VALUES (1)),
    z(v) AS (VALUES (2)),
    combined AS (
        SELECT v FROM x
        UNION ALL
        (SELECT v FROM y
         UNION
         SELECT v FROM z)
    )
SELECT v, COUNT(*) AS times_seen
FROM combined
GROUP BY v
ORDER BY v;
-- v=1 có 3 lần; v=2 có 1 lần.
```

Ở nhánh `(Y UNION Z)` có một `1` và một `2`; `UNION ALL` với X `[1,1]` giữ cả ba dòng giá trị `1`. Kết quả khác hoàn toàn phiên bản không ngoặc.

**Kết luận:** ưu tiên và dấu ngoặc không chỉ quyết định **giá trị nào được chọn**, mà với `ALL`, còn có thể quyết định **mỗi giá trị xuất hiện bao nhiêu lần**.

## 11. Khi nào dấu ngoặc thay đổi kết quả, khi nào không?

Không phải mọi lần thêm ngoặc đều đổi tập kết quả.

### 11.1. Các phép cùng loại có tính kết hợp ở mức tập

Với ngữ nghĩa tập hợp `DISTINCT`:

```text
(A UNION B) UNION C  =  A UNION (B UNION C)
(A INTERSECT B) INTERSECT C  =  A INTERSECT (B INTERSECT C)
```

Vì vậy, khi chỉ toàn `UNION` thông thường hoặc chỉ toàn `INTERSECT` thông thường, đổi nhóm thường **không đổi tập giá trị cuối**.

Nhưng dấu ngoặc vẫn có thể giúp **đọc cấu trúc**, và câu SQL còn có thể có `ALL`, `ORDER BY`, `LIMIT` hoặc biểu thức nhánh khác khiến kết quả/độ lớn tập được lấy thay đổi.

### 11.2. `EXCEPT` không kết hợp theo cách đó

```text
(A EXCEPT B) EXCEPT C
```

thường **khác**:

```text
A EXCEPT (B EXCEPT C)
```

Tập A, B, C trong bài:

```text
(A \ B) \ C = {1,2} \ {4,5,6} = {1,2}
A \ (B \ C) = {1,2,3,4} \ {3} = {1,2,4}
```

Đây là ví dụ đối lập ngay cả khi **không có bản sao trùng**.

### 11.3. Các phép khác loại thường không thể đổi nhóm tùy ý

```text
A UNION (B INTERSECT C)
```

thường khác:

```text
(A UNION B) INTERSECT C
```

Đã thấy ví dụ `{1,2,3,4,5}` so với `{4,5}`. Nếu thử với dữ liệu khác mà hai câu tình cờ cho cùng kết quả, **không có nghĩa chúng tương đương về logic trong mọi trường hợp**.

## 12. `ORDER BY` thuộc cấp nào?

Đây là một trong các bẫy thực hành lớn nhất của truy vấn tập hợp.

### 12.1. `ORDER BY` ở cuối sắp xếp kết quả chung

```sql
SELECT member_id FROM setlab_a
UNION
SELECT member_id FROM setlab_b
ORDER BY member_id DESC;
```

Trong PostgreSQL, `ORDER BY member_id DESC` ở **cuối câu truy vấn tập hợp** sắp xếp **toàn bộ kết quả `UNION`**. Kết quả là:

```text
5, 4, 3, 2, 1
```

Nó **không chỉ sắp xếp nhánh B**.

### 12.2. `LIMIT` ở cuối cũng áp dụng cho kết quả chung

```sql
SELECT member_id FROM setlab_a
UNION
SELECT member_id FROM setlab_b
ORDER BY member_id DESC
LIMIT 2;
```

Kết quả là:

```text
5, 4
```

Do `UNION` tạo `{1,2,3,4,5}`, rồi toàn bộ kết quả được sắp giảm dần và lấy 2 dòng đầu.

### 12.3. Muốn giới hạn từng nhánh thì phải dùng ngoặc

Giả sử yêu cầu: “Lấy **hai ID lớn nhất của A** và **hai ID lớn nhất của B**, sau đó hợp chúng lại.”

```sql
(SELECT member_id
 FROM setlab_a
 ORDER BY member_id DESC
 LIMIT 2)
UNION
(SELECT member_id
 FROM setlab_b
 ORDER BY member_id DESC
 LIMIT 2)
ORDER BY member_id;
```

Quy trình:

```text
A = {1,2,3,4} ── lấy top 2 ──> {4,3}
B = {3,4,5}   ── lấy top 2 ──> {5,4}
                                     │
                                     ▼
                         UNION → {3,4,5}
```

Kết quả cuối `3,4,5` khi sắp tăng dần.

So với truy vấn có `LIMIT 2` **chỉ ở cuối**, kết quả là `5,4`, hai yêu cầu khác nhau:

| Cách viết | Yêu cầu được thực hiện | Kết quả |
|---|---|---|
| `A UNION B ORDER BY id DESC LIMIT 2` | Hợp hết rồi lấy top 2 | `{5,4}` |
| `(top 2 A) UNION (top 2 B)` | Lấy top 2 mỗi nguồn rồi hợp | `{3,4,5}` |

### 12.4. `ORDER BY` trong một nhánh không hứa thứ tự của kết quả chung

Ngay cả khi các nhánh được sắp trước, phép `UNION` hoặc `INTERSECT` ở ngoài có thể dùng thuật toán khác và xuất các dòng theo thứ tự khác. Nếu kết quả cuối cần thứ tự, **thêm `ORDER BY` ở lớp ngoài cùng**.

Ví dụ:

```sql
(SELECT member_id FROM setlab_a ORDER BY member_id DESC)
UNION ALL
(SELECT member_id FROM setlab_b ORDER BY member_id DESC);
```

Các nhánh có `ORDER BY`, nhưng không nên coi thứ tự kết quả **của toàn phép `UNION ALL`** là cam kết hiển thị. Nếu cần thứ tự chung, ghi `ORDER BY` ở cuối câu compound.

### 12.5. `ORDER BY` trên biểu thức sau phép tập hợp

Trong PostgreSQL, `ORDER BY` gắn trực tiếp với kết quả `UNION`/`INTERSECT`/`EXCEPT` thường bị giới hạn ở **tên cột đầu ra hoặc vị trí cột**, thay vì một biểu thức mới tùy ý.

Ví dụ đơn giản:

```sql
SELECT member_id FROM setlab_a
UNION
SELECT member_id FROM setlab_b
ORDER BY member_id DESC;
```

Nếu cần `ORDER BY` theo biểu thức phức tạp, có thể **bọc kết quả tập hợp trong một truy vấn ngoài**:

```sql
SELECT result.member_id
FROM (
    SELECT member_id FROM setlab_a
    UNION
    SELECT member_id FROM setlab_b
) AS result
ORDER BY result.member_id % 2, result.member_id;
```

Ở đây `% 2` nhóm các số chẵn và lẻ theo phần dư; đó là biểu thức của **truy vấn ngoài**, không phải điều kiện sắp xếp trực tiếp ở cấp phép toán tập hợp.

## 13. Dùng CTE để đặt tên cho từng nhóm phép toán

Khi phép toán dài, thay vì lồng nhiều ngoặc và `SELECT` trên cùng một màn hình, có thể đặt tên cho các kết quả trung gian bằng `WITH` (*Common Table Expression*).

### 13.1. Nhóm A và B trước rồi mới giao với C

```sql
WITH members_in_a_or_b AS (
    SELECT member_id FROM setlab_a
    UNION
    SELECT member_id FROM setlab_b
)
SELECT member_id FROM members_in_a_or_b
INTERSECT
SELECT member_id FROM setlab_c
ORDER BY member_id;
```

Kết quả `{4,5}`, đúng ý nghĩa `(A UNION B) INTERSECT C`.

### 13.2. Giao B và C trước rồi hợp với A

```sql
WITH members_in_b_and_c AS (
    SELECT member_id FROM setlab_b
    INTERSECT
    SELECT member_id FROM setlab_c
)
SELECT member_id FROM setlab_a
UNION
SELECT member_id FROM members_in_b_and_c
ORDER BY member_id;
```

Kết quả `{1,2,3,4,5}`, đúng ý nghĩa `A UNION (B INTERSECT C)`.

### 13.3. Nhiều bước nghiệp vụ có thể đặt tên rõ nghĩa

Ví dụ mục tiêu:

> “Lấy khách thuộc **chiến dịch Email hoặc App**, đã **xác minh tài khoản**, nhưng **không nằm trong danh sách chặn**.”

Mô hình biểu thức:

```text
((Email UNION App) INTERSECT Verified) EXCEPT Blocked
```

Có thể chia thành hai CTE:

```sql
WITH
    reached AS (
        SELECT customer_id FROM campaign_email
        UNION
        SELECT customer_id FROM campaign_app
    ),
    reached_and_verified AS (
        SELECT customer_id FROM reached
        INTERSECT
        SELECT customer_id FROM verified_customers
    )
SELECT customer_id FROM reached_and_verified
EXCEPT
SELECT customer_id FROM blocked_customers
ORDER BY customer_id;
```

Các bảng `campaign_email`, `campaign_app`, `verified_customers`, `blocked_customers` là **schema minh họa**, chưa được tạo trong script `setlab_` ở đầu bài. Truy vấn cho thấy cách đặt tên trung gian dựa trên **ngữ nghĩa nghiệp vụ**, chứ không chỉ gọi `step1`, `step2`.

**CTE không phải lời hứa hiệu năng tốt hơn**. Tùy hệ quản trị và phiên bản, bộ tối ưu có thể đưa CTE vào kế hoạch chung hoặc xử lý theo cách khác. Lợi ích chắc chắn trong bài này là **cấu trúc phép tập hợp được nêu rõ và dễ kiểm tra**.

## 14. Quy tắc số cột, kiểu dữ liệu và tên cột

Các phép `UNION`, `INTERSECT` và `EXCEPT` kết hợp **những dòng cùng dạng**. Với SQL thông thường, các nhánh cần:

1. Có **cùng số lượng cột**.
2. Có **kiểu dữ liệu tương thích theo vị trí** để hệ quản trị xác định kiểu kết quả.
3. Các cột ở cùng vị trí phải mang **cùng ý nghĩa nghiệp vụ**.

### 14.1. Dữ liệu được so sánh theo vị trí cột

```sql
SELECT member_id, 'A' AS source
FROM setlab_a
UNION
SELECT member_id, 'B' AS source
FROM setlab_b
ORDER BY member_id, source;
```

Ở đây mỗi dòng có hai cột `(member_id, source)`. Dòng `(3,'A')` và `(3,'B')` **khác nhau**, nên `UNION` vẫn giữ cả hai, dù `member_id` trùng nhau. Phép loại trùng xét **toàn bộ các cột được chọn**, không riêng cột ID.

Nếu mục tiêu là “ID xuất hiện ít nhất một lần ở A hoặc B”, chỉ chọn `member_id`:

```sql
SELECT member_id FROM setlab_a
UNION
SELECT member_id FROM setlab_b;
```

### 14.2. Tên cột khác nhau không tự tạo lỗi, nhưng vị trí phải đúng

```sql
SELECT member_id AS id FROM setlab_a
UNION
SELECT member_id AS some_other_name FROM setlab_b;
```

Trong PostgreSQL, tên cột kết quả thường lấy từ **nhánh đầu tiên** (`id` trong ví dụ), nhưng phép so sánh giữa hai nhánh dựa vào **vị trí cột**, không dựa trên tên alias của nhánh sau.

Không được dựa vào việc hai cột cùng tên để mong SQL tự ghép đúng nếu chúng ở vị trí khác nhau. Ví dụ ghép `(customer_id, order_date)` với `(order_date, customer_id)` có thể gây lỗi kiểu dữ liệu hoặc tạo kết quả vô nghĩa nếu các kiểu ngẫu nhiên tương thích.

### 14.3. Mọi biểu thức phải mang kiểu tương thích

Nếu một nhánh chọn `INTEGER` còn nhánh kia chọn văn bản không thể chuyển thành kiểu chung, hệ quản trị có thể báo lỗi.

```sql
-- Hãy kiểm soát kiểu nguồn thay vì để SQL suy đoán tùy hệ.
SELECT CAST(member_id AS TEXT) AS identifier FROM setlab_a
UNION
SELECT CAST(member_id AS TEXT) FROM setlab_b;
```

Chỉ cast khi có ý nghĩa rõ ràng. Ví dụ ID dạng số 42 và mã định danh văn bản `'042'` có thể không tương đương về nghiệp vụ; ép về `INTEGER` sẽ mất số 0 đầu.

### 14.4. Khóa sắp xếp ở kết quả compound

Vì tên cột đầu ra lấy theo nhánh đầu, hãy đặt alias rõ ngay nhánh đầu nếu cần `ORDER BY`:

```sql
SELECT member_id AS result_id FROM setlab_a
UNION
SELECT member_id FROM setlab_b
ORDER BY result_id;
```

Đừng kỳ vọng alias chỉ có ở nhánh thứ hai trở thành tên cột chung.

## 15. `NULL`, dòng trùng và phép toán tập hợp

Một khác biệt quan trọng giữa **phép so sánh `=`** và **loại trùng trong phép tập hợp**:

```sql
SELECT NULL = NULL;
-- Giá trị logic UNKNOWN/NULL, không phải TRUE.
```

Tuy nhiên, trong `UNION`/`INTERSECT`/`EXCEPT` với mặc định loại trùng, các dòng có giá trị `NULL` ở những vị trí tương ứng được xử lý theo quy tắc **không phân biệt khi xét trùng**: những dòng toàn bộ cột cùng giá trị, kể cả `NULL` tương ứng, được xem là trùng để tính tập.

### 15.1. `UNION` giữ một bản sao của dòng `NULL`

```sql
SELECT v
FROM (VALUES (NULL::INTEGER), (NULL::INTEGER), (1)) AS a(v)
UNION
SELECT v
FROM (VALUES (NULL::INTEGER), (2)) AS b(v)
ORDER BY v NULLS FIRST;
```

Kết quả có **một dòng `NULL`**, rồi `1`, `2` (theo quy tắc sắp xếp đã ghi).

Với `UNION ALL`, ba dòng `NULL` từ hai nhánh **đều được giữ**.

### 15.2. `INTERSECT` có thể trả dòng `NULL`

```sql
SELECT v
FROM (VALUES (NULL::INTEGER), (1)) AS a(v)
INTERSECT
SELECT v
FROM (VALUES (NULL::INTEGER), (2)) AS b(v);
-- Một dòng NULL.
```

Đây không phải phép `WHERE a.v = b.v`, nơi `NULL = NULL` cho `UNKNOWN`. Phép `INTERSECT` áp dụng ngữ nghĩa **dòng trùng theo tập**.

### 15.3. `EXCEPT` có thể loại dòng `NULL`

```sql
SELECT v
FROM (VALUES (NULL::INTEGER), (1)) AS a(v)
EXCEPT
SELECT v
FROM (VALUES (NULL::INTEGER), (2)) AS b(v);
-- Chỉ còn 1; dòng NULL đã bị trừ.
```

Nếu thêm `ALL`, số lượng bản sao `NULL` cũng được tính theo công thức của `EXCEPT ALL`, ví dụ hai bản sao `NULL` phía trái trừ một bản sao `NULL` phía phải sẽ còn một bản sao.

### 15.4. Vì sao cần chú ý khi viết lại thành JOIN?

Một truy vấn `EXCEPT` có thể trừ các dòng chứa `NULL` theo ngữ nghĩa tập, nhưng phép `JOIN` dựa trên `a.value = b.value` thường **không nối `NULL` với `NULL`**. Vì vậy, viết lại `EXCEPT` thành `LEFT JOIN ... WHERE b.key IS NULL` mà không xét ràng buộc khóa và `NULL` có thể thay đổi kết quả.

Khi cần thay phép tập hợp bằng `JOIN`, `EXISTS` hoặc `NOT EXISTS` để tối ưu, phải kiểm tra:

- Dòng có thể trùng hay không.
- Có cột nullable nào trong khóa so sánh không.
- Bài toán muốn xử lý như **tập** (`DISTINCT`) hay **đa tập** (`ALL`).
- Dòng trùng được xác định trên **toàn bộ các cột** nào.

## 16. Sự khác biệt giữa `UNION`, `UNION ALL` và điều kiện `OR`

Một số truy vấn nhìn có vẻ giống nhau:

```sql
SELECT member_id FROM setlab_a
UNION
SELECT member_id FROM setlab_b;
```

Và một truy vấn khác dùng `WHERE ... OR ...` trên một bảng dữ liệu kết hợp. Nhưng chúng không đồng nhất về cấu trúc:

- `UNION` **hợp hai kết quả truy vấn**, có thể đến từ hai bảng hoặc hai phép lọc khác nhau, rồi loại trùng theo toàn bộ cột kết quả.
- `OR` là phép kết hợp **điều kiện boolean bên trong một `WHERE`** của một truy vấn.
- `UNION ALL` hợp các dòng mà **không loại trùng**.

Nếu dùng hai nhánh trên **cùng một bảng** với điều kiện khác nhau:

```sql
SELECT product_id FROM products WHERE is_active = TRUE
UNION
SELECT product_id FROM products WHERE is_featured = TRUE;
```

thì với `product_id` duy nhất và không `NULL`, kết quả ID có thể tương đương:

```sql
SELECT product_id
FROM products
WHERE is_active = TRUE OR is_featured = TRUE;
```

Tuy nhiên, `UNION ALL` sẽ trả ID **hai lần** nếu sản phẩm vừa hoạt động vừa được gắn nổi bật, trong khi một `SELECT ... WHERE ... OR ...` bình thường chỉ trả một dòng bảng cho sản phẩm đó. Đây là lý do không nên thay công thức tập hợp bằng `OR` chỉ vì cách đọc tiếng Việt đều có chữ “hoặc”.

## 17. Cấu trúc có `LIMIT`, `OFFSET` và phân trang

Khi kết quả `UNION`/`INTERSECT`/`EXCEPT` cần hiển thị theo trang, hãy phân biệt:

### 17.1. Phân trang **kết quả chung**

```sql
SELECT member_id FROM setlab_a
UNION
SELECT member_id FROM setlab_b
ORDER BY member_id ASC
LIMIT 2 OFFSET 2;
```

Kết quả hợp là `1,2,3,4,5`; sắp tăng dần rồi bỏ qua hai dòng đầu, lấy hai dòng tiếp theo → `3,4`.

Để phân trang ổn định, `ORDER BY` nên tạo thứ tự **xác định**, dùng một hoặc nhiều cột khóa phân xử khi các dòng đồng hạng. Ví dụ này chỉ có `member_id` duy nhất sau `UNION`, nên đủ để xác định thứ tự.

### 17.2. Giới hạn từng nhánh **trước khi hợp** không giống phân trang chung

```sql
(SELECT member_id
 FROM setlab_a
 ORDER BY member_id
 LIMIT 2 OFFSET 0)
UNION
(SELECT member_id
 FROM setlab_b
 ORDER BY member_id
 LIMIT 2 OFFSET 0)
ORDER BY member_id;
```

Nhánh A lấy `{1,2}`, nhánh B lấy `{3,4}`, hợp cuối cho `{1,2,3,4}`. Đây không phải “trang đầu 2 dòng của hợp A và B”; nó là **gộp trang đầu của từng nguồn**.

### 17.3. `ORDER BY` không thay thế quy tắc ưu tiên

```sql
SELECT member_id FROM setlab_a
UNION
SELECT member_id FROM setlab_b
INTERSECT
SELECT member_id FROM setlab_c
ORDER BY member_id DESC;
```

`ORDER BY` chỉ sắp **sau khi ngữ nghĩa `A UNION (B INTERSECT C)` đã được xác định**. Nó không khiến `UNION` được thực hiện trước và cũng không thay được ngoặc quanh `(A UNION B)`.

## 18. Khi nào nên dùng dấu ngoặc dù hệ quản trị đã có quy tắc ưu tiên?

Có nhiều lý do:

**Thứ nhất: mã SQL phải phản ánh đúng câu hỏi nghiệp vụ.** Nếu yêu cầu là “A hoặc B, rồi phải ở C”, câu lệnh:

```sql
(SELECT member_id FROM setlab_a
 UNION
 SELECT member_id FROM setlab_b)
INTERSECT
SELECT member_id FROM setlab_c;
```

cho thấy điều đó ngay cả khi người đọc không thuộc quy tắc ưu tiên.

**Thứ hai: khi kết hợp `EXCEPT`, rất dễ đọc sai chiều và phạm vi loại trừ.** `A EXCEPT (B UNION C)` và `(A EXCEPT B) UNION C` khác nhau nhiều; dấu ngoặc ngăn những cách hiểu chủ quan.

**Thứ ba: với `ALL`, dấu ngoặc ảnh hưởng việc loại hay giữ bản sao trùng.** `A UNION ALL (B UNION C)` và `(A UNION ALL B) UNION C` có thể khác số dòng.

**Thứ tư: `ORDER BY`/`LIMIT` trong nhánh phải được bao trong ngoặc khi muốn chọn top-N riêng.** Nếu để cuối toàn biểu thức, chúng áp dụng cho kết quả chung.

**Thứ năm: khả chuyển giữa hệ quản trị.** Một số hệ có quy tắc kết hợp phép toán khác hoặc hỗ trợ khác nhau cho `INTERSECT`, `EXCEPT`, `ALL`; viết dấu ngoặc theo ý nghĩa nghiệp vụ giúp giảm rủi ro khi chuyển SQL.

### 18.1. Đừng lồng ngoặc vô mục đích

Một câu chỉ có:

```sql
SELECT member_id FROM setlab_a
UNION
SELECT member_id FROM setlab_b;
```

không cần thêm năm tầng ngoặc để “an toàn”. Dùng ngoặc nơi có **nhiều phép**, **cách nhóm cần rõ**, hoặc **nhánh có `ORDER BY`/`LIMIT` riêng**. Với chuỗi rất dài, CTE đặt tên từng bước có thể dễ hiểu hơn ngoặc lồng sâu.

## 19. Khả chuyển giữa các hệ quản trị

Ngữ nghĩa nền tảng của ba phép toán tập hợp khá phổ biến, nhưng **cú pháp được hỗ trợ, mức ưu tiên và quy tắc ngoặc** có thể khác theo hệ hoặc phiên bản.

| Chủ đề | Lưu ý khi chuyển hệ |
|---|---|
| `UNION` | Được hỗ trợ rộng rãi; mặc định loại trùng |
| `UNION ALL` | Được hỗ trợ rộng rãi; giữ bản sao trùng |
| `INTERSECT` | Được nhiều hệ hỗ trợ, nhưng mức ưu tiên trong biểu thức dài có thể khác |
| `EXCEPT` | Được nhiều hệ hỗ trợ; một số hệ/phiên bản có tên hoặc khả năng hỗ trợ khác |
| `INTERSECT ALL` / `EXCEPT ALL` | Không có ở mọi hệ quản trị; phải xem phiên bản cụ thể |
| `ORDER BY` và `LIMIT` | Cú pháp phân trang và cách giới hạn từng nhánh có thể khác |
| `NULL` và loại trùng | Cần xác nhận quy tắc so sánh dòng khi viết lại bằng JOIN |
| Kiểu, collation | Có thể làm thay đổi việc hai dòng chuỗi được xem là tương đương |

### 19.1. Quy tắc quan trọng của PostgreSQL

Trong PostgreSQL:

```text
INTERSECT có ưu tiên cao hơn UNION và EXCEPT.
UNION và EXCEPT được kết hợp từ trái sang phải ở cùng mức.
```

`ALL` hoặc `DISTINCT` ảnh hưởng **bản sao trùng**, không đảo quy tắc ưu tiên đó.

### 19.2. Đừng giả định mọi database phân tích chuỗi phép toán giống PostgreSQL

Ví dụ một số hệ/phiên bản SQL xử lý các phép toán tập hợp ở cùng mức ưu tiên và kết hợp trái sang phải, trong khi PostgreSQL ưu tiên `INTERSECT`. Vì thế, nếu cần di chuyển một truy vấn có cả `UNION` và `INTERSECT`, cách an toàn là **đặt ngoặc theo đúng ý định trước khi chuyển**:

```sql
-- Ý định: lấy A hoặc B, rồi phải thuộc C.
(SELECT member_id FROM setlab_a
 UNION
 SELECT member_id FROM setlab_b)
INTERSECT
SELECT member_id FROM setlab_c;
```

Ngay cả khi hệ đích cũng ưu tiên `INTERSECT` giống PostgreSQL, dấu ngoặc trên vẫn giúp tránh nhầm. Khi đổi hệ, còn phải xác nhận liệu cú pháp đặt ngoặc quanh nhánh, alias, top-N và các phép `ALL` có được hỗ trợ hay không.

### 19.3. Vì sao phải kiểm thử với dữ liệu tạo ra kết quả khác nhau?

Nếu chọn dữ liệu:

```text
A = {1}
B = {1}
C = {1}
```

thì hai cách nhóm:

```text
A UNION (B INTERSECT C)
(A UNION B) INTERSECT C
```

đều trả `{1}`. Một bài kiểm tra như vậy **không phát hiện** lỗi ưu tiên.

Trong bài học này, A `{1,2,3,4}`, B `{3,4,5}`, C `{4,5,6}` được chọn để hai cách nhóm cho kết quả khác `{1,2,3,4,5}` và `{4,5}`. Khi viết kiểm thử SQL, nên có dữ liệu ở **phần chỉ thuộc A**, **phần chung B/C**, **phần chỉ thuộc C**, và những điểm chồng lấn cần thiết.

## 20. Hiệu năng và kế hoạch thực thi

Phép tập hợp có thể cần **sắp xếp**, **bảng băm** hoặc phương pháp khác để xác định dòng trùng, phần giao và phần hiệu. `UNION ALL` thường tránh được công việc loại trùng mà `UNION` phải thực hiện, nhưng không nên kết luận luôn nhanh hơn trong mọi truy vấn cụ thể khi còn có JOIN, lọc, giới hạn và kế hoạch tối ưu khác.

### 20.1. Dấu ngoặc là yêu cầu ngữ nghĩa trước tiên

Hai biểu thức:

```text
A UNION (B INTERSECT C)
(A UNION B) INTERSECT C
```

không thể đem so sánh tốc độ như hai cách tối ưu cùng một nhiệm vụ, vì **chúng trả hai tập khác nhau** trong dữ liệu mẫu. Trước khi dùng `EXPLAIN`, hãy bảo đảm chúng cùng một yêu cầu nghiệp vụ.

### 20.2. CTE và bảng tạm không mặc định nhanh hơn

CTE có thể làm SQL dễ đọc, giúp đặt tên các bước `(A UNION B)` hoặc `(B INTERSECT C)`. Nhưng nó không tự bảo đảm kết quả được **tính một lần rồi lưu vật lý**, cũng không cam kết thực thi nhanh hơn dấu ngoặc. Hệ quản trị có thể tối ưu khác nhau theo phiên bản.

### 20.3. Phép tập hợp so sánh toàn bộ hàng đã chọn

Nếu chỉ cần ID, nên chọn đúng cột ID:

```sql
SELECT member_id FROM setlab_a
INTERSECT
SELECT member_id FROM setlab_b;
```

Nếu chọn thêm nhiều cột mô tả thay đổi giữa các nguồn, hai dòng có cùng ID có thể **không còn trùng** để giao hoặc khử trùng. Ngoài ảnh hưởng **ngữ nghĩa**, độ rộng dòng cũng có thể ảnh hưởng tài nguyên xử lý.

### 20.4. Kiểm tra kế hoạch khi có nhu cầu thực

PostgreSQL hỗ trợ:

```sql
EXPLAIN
(SELECT member_id FROM setlab_a
 UNION
 SELECT member_id FROM setlab_b)
INTERSECT
SELECT member_id FROM setlab_c;
```

Có thể dùng `EXPLAIN ANALYZE` trong môi trường thực hành nếu cần số đo thời gian thật. Tuy nhiên, công việc quan trọng đầu tiên của bài này là **đọc đúng biểu thức**, không phải đo tốc độ của hai câu SQL có kết quả khác nhau.

## 21. Các lỗi thường gặp và cách sửa

| Cách nghĩ hoặc câu SQL | Vấn đề | Cách xử lý |
|---|---|---|
| Đọc `A UNION B INTERSECT C` từ trái sang phải | PostgreSQL ưu tiên `INTERSECT` | Ghi rõ `A UNION (B INTERSECT C)` hoặc `(A UNION B) INTERSECT C` |
| Nghĩ `UNION` đứng trước nên được tính trước | Vị trí văn bản không quyết định ưu tiên | Nhớ các mức ưu tiên, dùng ngoặc |
| Coi `EXCEPT` là phép hiệu hai chiều | `A EXCEPT B` khác `B EXCEPT A` | Xác định bên nào bị trừ |
| Viết `A UNION B EXCEPT C` khi chỉ muốn trừ C khỏi B | C đang bị trừ khỏi **hợp A và B** | Viết `A UNION (B EXCEPT C)` |
| Cho rằng `A EXCEPT B EXCEPT C` nhóm tùy ý | Phép hiệu không có tính kết hợp tổng quát | Viết ngoặc đúng yêu cầu |
| Nghĩ `ALL` đổi thứ tự ưu tiên | `ALL` chỉ điều khiển bản sao trùng | Phân tích ưu tiên và chế độ `ALL` riêng |
| Dùng `UNION ALL` rồi mong khử các ID trùng | `ALL` giữ bản sao | Dùng `UNION` nếu cần một dòng cho mỗi ID |
| Dùng `UNION` trên `(id, source)` rồi mong ID chỉ xuất hiện một lần | Dòng trùng được xét **trên cả hai cột** | Chọn đúng bộ cột cần coi là một phần tử |
| Đặt `LIMIT` cuối khi muốn top 2 của từng nguồn | `LIMIT` cuối giới hạn **kết quả chung** | Bọc mỗi nhánh với `ORDER BY ... LIMIT` |
| Nghĩ `ORDER BY` trong nhánh quyết định thứ tự kết quả chung | Phép tập hợp ở ngoài không hứa giữ thứ tự nhánh | Thêm `ORDER BY` ngoài cùng |
| Thêm ngoặc cho điều kiện `WHERE` rồi nghĩ đã nhóm phép tập hợp | Ngoặc `WHERE` và ngoặc `SELECT` ở hai cấp khác nhau | Bọc toàn nhánh `SELECT ... UNION ...` |
| Dùng `NULL = NULL` để giải thích `INTERSECT` | Logic `=` không giống cơ chế xét trùng của phép tập hợp | Phân biệt phép so sánh và tập dòng |
| Bỏ qua khác biệt hệ quản trị | Kết quả chuỗi phép có thể đổi theo phiên bản/hệ | Đặt ngoặc rõ và thử dữ liệu phân biệt |
| So tốc độ hai câu khác kết quả | Không cùng một nhiệm vụ | Xác nhận ngữ nghĩa rồi mới tối ưu |

## 22. Thực hành: viết từng truy vấn và dự đoán trước

Hãy dùng ba bảng tạm `setlab_a`, `setlab_b`, `setlab_c` đã tạo ở mục 2. Không cần thêm bảng nào cho các câu sau.

### 22.1. Truy vấn số 1: ưu tiên mặc định

```sql
SELECT member_id FROM setlab_a
UNION
SELECT member_id FROM setlab_b
INTERSECT
SELECT member_id FROM setlab_c
ORDER BY member_id;
```

Trước khi chạy, dự đoán có **5 dòng** `1,2,3,4,5`. Sau đó viết lại có ngoặc:

```sql
SELECT member_id FROM setlab_a
UNION
(SELECT member_id FROM setlab_b
 INTERSECT
 SELECT member_id FROM setlab_c)
ORDER BY member_id;
```

Kết quả giữ nguyên vì dấu ngoặc **làm rõ cách nhóm vốn đã được áp dụng**.

### 22.2. Truy vấn số 2: ép hợp trước

```sql
(SELECT member_id FROM setlab_a
 UNION
 SELECT member_id FROM setlab_b)
INTERSECT
SELECT member_id FROM setlab_c
ORDER BY member_id;
```

Truy vấn trả **2 dòng** `4,5`.

### 22.3. Truy vấn số 3: so sánh hai cách dùng `EXCEPT`

```sql
-- Cách A: A trừ phần chung của B và C.
SELECT member_id FROM setlab_a
EXCEPT
(SELECT member_id FROM setlab_b
 INTERSECT
 SELECT member_id FROM setlab_c)
ORDER BY member_id;
-- 1,2,3.
```

```sql
-- Cách B: phần A không có trong B, rồi mới giao C.
(SELECT member_id FROM setlab_a
 EXCEPT
 SELECT member_id FROM setlab_b)
INTERSECT
SELECT member_id FROM setlab_c
ORDER BY member_id;
-- 0 dòng.
```

### 22.4. Truy vấn số 4: hiệu của hợp khác hợp của hiệu

```sql
-- (A UNION B) EXCEPT C.
(SELECT member_id FROM setlab_a
 UNION
 SELECT member_id FROM setlab_b)
EXCEPT
SELECT member_id FROM setlab_c
ORDER BY member_id;
-- 1,2,3.
```

```sql
-- A UNION (B EXCEPT C).
SELECT member_id FROM setlab_a
UNION
(SELECT member_id FROM setlab_b
 EXCEPT
 SELECT member_id FROM setlab_c)
ORDER BY member_id;
-- 1,2,3,4.
```

### 22.5. Truy vấn số 5: tách phép bằng CTE

```sql
WITH
    candidates AS (
        SELECT member_id FROM setlab_a
        UNION
        SELECT member_id FROM setlab_b
    ),
    accepted AS (
        SELECT member_id FROM candidates
        INTERSECT
        SELECT member_id FROM setlab_c
    )
SELECT member_id
FROM accepted
ORDER BY member_id;
-- 4,5.
```

CTE thể hiện hai bước có tên: tạo ứng viên từ A/B, rồi chỉ lấy ứng viên có ở C.

## 23. Bài tập tự luyện

Các bài sau sử dụng A `{1,2,3,4}`, B `{3,4,5}`, C `{4,5,6}` trừ khi ghi khác. Với mỗi bài, nên **viết biểu thức tập hợp bằng ký hiệu A, B, C và dấu ngoặc trước**, rồi mới chuyển sang SQL.

### Bài 1 — Đọc ưu tiên

Trong PostgreSQL, biểu thức:

```sql
SELECT member_id FROM setlab_a
UNION
SELECT member_id FROM setlab_b
INTERSECT
SELECT member_id FROM setlab_c;
```

được nhóm như thế nào? Kết quả có những ID nào?

### Bài 2 — Đổi phạm vi của `INTERSECT`

Viết câu SQL có dấu ngoặc để lấy ID **thuộc A hoặc B**, và **đồng thời thuộc C**. Dự đoán số dòng.

### Bài 3 — `EXCEPT` trước hay `INTERSECT` trước?

Dự đoán kết quả:

```text
A EXCEPT B INTERSECT C
(A EXCEPT B) INTERSECT C
```

Giải thích vì sao một câu có thể rỗng còn câu kia không.

### Bài 4 — Hai cách dùng `EXCEPT`

Với:

```text
(A UNION B) EXCEPT C
A UNION (B EXCEPT C)
```

ID nào nằm trong câu thứ hai nhưng không nằm trong câu thứ nhất? Hãy dùng **một câu tiếng Việt** giải thích sự khác biệt.

### Bài 5 — Kết hợp trái sang phải

Không có dấu ngoặc, PostgreSQL hiểu `A EXCEPT B UNION C` như thế nào? Tính kết quả. Sau đó tính `A EXCEPT (B UNION C)`.

### Bài 6 — Chỉ `UNION`

So sánh `(A UNION B) UNION C` với `A UNION (B UNION C)` khi dùng mặc định loại trùng. Chúng có cho cùng tập giá trị không? Vì sao bài tập này không chứng minh mọi phép tập hợp đều kết hợp được?

### Bài 7 — `UNION ALL` và bản sao trùng

Trong A có ID `3`, trong B cũng có ID `3`. So sánh số lần `3` xuất hiện trong:

```sql
SELECT member_id FROM setlab_a
UNION
SELECT member_id FROM setlab_b;
```

và:

```sql
SELECT member_id FROM setlab_a
UNION ALL
SELECT member_id FROM setlab_b;
```

### Bài 8 — Trộn `ALL` với `DISTINCT`

Cho X `[1,1]`, Y `[1]`, Z `[2]`. Hai cách nhóm:

```text
(X UNION ALL Y) UNION Z
X UNION ALL (Y UNION Z)
```

có bao nhiêu dòng giá trị `1`? Giải thích.

### Bài 9 — Top-N từng nguồn

Viết câu SQL lấy **2 ID lớn nhất của A** và **2 ID lớn nhất của B**, sau đó `UNION` rồi sắp tăng dần. Vì sao `ORDER BY ... LIMIT 2` chỉ ở cuối truy vấn **không đáp ứng** yêu cầu?

### Bài 10 — Phân trang hợp chung

Viết truy vấn gộp A và B, loại trùng, rồi sắp ID tăng dần, lấy **2 dòng bắt đầu từ dòng thứ ba**. Dự đoán kết quả.

### Bài 11 — Hai cột làm thay đổi phép loại trùng

Nếu một nhánh trả `(3,'A')`, nhánh khác trả `(3,'B')`, liệu `UNION` có chỉ giữ một dòng ID 3 không? Vì sao?

### Bài 12 — `NULL` trong phép giao

Giả sử nguồn L có `{NULL,1}`, nguồn R có `{NULL,2}`. Dự đoán:

```text
L UNION R
L INTERSECT R
L EXCEPT R
```

Giải thích vì sao `INTERSECT` có thể trả dòng `NULL` dù `NULL = NULL` không trả `TRUE`.

### Bài 13 — Dịch câu nghiệp vụ thành ngoặc

Một hệ thống có bốn tập ID:

- `Email`: người nhận chiến dịch Email.
- `App`: người nhận chiến dịch App.
- `Verified`: người đã xác minh.
- `Blocked`: người bị chặn.

Viết biểu thức tập hợp và SQL theo yêu cầu:

> “Chọn người thuộc ít nhất một kênh Email/App, **phải được xác minh**, và **không bị chặn**.”

### Bài 14 — Tập rỗng và `EXCEPT`

Giả sử C là tập rỗng. Dự đoán kết quả `(A EXCEPT B) UNION C` và `A EXCEPT (B UNION C)`. Trường hợp này có đủ để chứng minh hai biểu thức luôn tương đương không?

### Bài 15 — Chọn câu có đúng ngữ nghĩa

Yêu cầu: “Giữ nguyên toàn bộ A, và chỉ bổ sung các ID trong B mà **không xuất hiện ở C**.” Chọn:

```text
1. (A UNION B) EXCEPT C
2. A UNION (B EXCEPT C)
3. (A EXCEPT C) UNION B
```

Giải thích bằng một ID xuất hiện trong cả A và C.

<details>
<summary>Gợi ý đáp án và cách diễn giải</summary>

**Bài 1:** PostgreSQL hiểu `A UNION (B INTERSECT C)`. Vì `B ∩ C={4,5}`, kết quả `{1,2,3,4,5}`.

**Bài 2:**

```sql
(SELECT member_id FROM setlab_a
 UNION
 SELECT member_id FROM setlab_b)
INTERSECT
SELECT member_id FROM setlab_c
ORDER BY member_id;
```

Kết quả `{4,5}`, **2 dòng**.

**Bài 3:** Không ngoặc: `A \ (B ∩ C)={1,2,3}`. Có ngoặc `(A \ B) ∩ C = {1,2} ∩ {4,5,6} = {}`, **0 dòng**.

**Bài 4:** ID **4** chỉ có trong `A UNION (B EXCEPT C)`, vì A được giữ nguyên; trong `(A UNION B) EXCEPT C`, ID 4 bị loại do thuộc C.

**Bài 5:** Không ngoặc: `(A EXCEPT B) UNION C = {1,2,4,5,6}`. Với `A EXCEPT (B UNION C)`, kết quả `{1,2}`.

**Bài 6:** Cùng kết quả `{1,2,3,4,5,6}`, bởi phép hợp tập hợp có tính kết hợp. Nhưng `EXCEPT` hoặc phối hợp `UNION`/`INTERSECT` không cho phép đổi nhóm tùy ý.

**Bài 7:** `UNION` có **một** dòng mang ID 3; `UNION ALL` có **hai** dòng mang ID 3. `ALL` giữ bản sao trùng.

**Bài 8:** `(X UNION ALL Y) UNION Z` loại trùng ở phép `UNION` ngoài cùng, nên `1` còn **một** lần. `X UNION ALL (Y UNION Z)` giữ hai bản sao `1` của X cộng một bản sao từ Y/Z, nên `1` xuất hiện **ba** lần.

**Bài 9:**

```sql
(SELECT member_id FROM setlab_a ORDER BY member_id DESC LIMIT 2)
UNION
(SELECT member_id FROM setlab_b ORDER BY member_id DESC LIMIT 2)
ORDER BY member_id;
```

Kết quả `{3,4,5}`. Nếu để `LIMIT 2` ở cuối, ta lấy **hai ID cao nhất của hợp** là `5,4`, chứ không lấy hai của từng nguồn.

**Bài 10:**

```sql
SELECT member_id FROM setlab_a
UNION
SELECT member_id FROM setlab_b
ORDER BY member_id
LIMIT 2 OFFSET 2;
```

Kết quả `3,4` (hai dòng sau khi bỏ qua ID 1 và 2).

**Bài 11:** Không; hai dòng `(3,'A')` và `(3,'B')` khác ở **cột thứ hai**, nên `UNION` giữ **cả hai**. Muốn khử trùng theo ID, chỉ chọn ID hoặc định nghĩa cách gom nhóm trước.

**Bài 12:** `L UNION R = {NULL,1,2}`, `L INTERSECT R = {NULL}`, `L EXCEPT R = {1}`. Phép tập hợp xác định dòng trùng theo ngữ nghĩa tập, không dựa đơn giản vào biểu thức `NULL = NULL` trong `WHERE`.

**Bài 13:** Biểu thức `((Email UNION App) INTERSECT Verified) EXCEPT Blocked`.

```sql
WITH reached AS (
    SELECT customer_id FROM campaign_email
    UNION
    SELECT customer_id FROM campaign_app
),
verified_reached AS (
    SELECT customer_id FROM reached
    INTERSECT
    SELECT customer_id FROM verified_customers
)
SELECT customer_id FROM verified_reached
EXCEPT
SELECT customer_id FROM blocked_customers
ORDER BY customer_id;
```

Các tên bảng là **schema minh họa**, không có trong script `setlab_`.

**Bài 14:** Khi C rỗng, `(A \ B) ∪ C = A \ B = {1,2}` và `A \ (B ∪ C)=A \ B={1,2}`. Hai biểu thức **tình cờ bằng nhau với C rỗng**, không chứng minh tương đương trong mọi tình huống.

**Bài 15:** Chọn **2. `A UNION (B EXCEPT C)`**. ID `4` thuộc cả A và C phải được giữ vì yêu cầu “giữ nguyên toàn bộ A”. Ở phương án 1, ID 4 bị trừ khỏi hợp A/B; phương án 3 vẫn thêm toàn bộ B kể cả những ID thuộc C.

</details>

## 24. Checklist trước khi dùng phép toán tập hợp trong truy vấn thật

Mỗi khi có từ **hai phép toán tập hợp trở lên** trong cùng câu SQL, tự hỏi:

1. **Mỗi nhánh `SELECT` đại diện cho tập gì?** Đặt tên A/B/C bằng ý nghĩa nghiệp vụ.
2. **Tập kết quả muốn lấy là hợp, giao hay hiệu?** Viết công thức bằng ngoặc trước khi viết SQL.
3. **Có `INTERSECT` không?** Trong PostgreSQL, nó có độ ưu tiên cao hơn `UNION` và `EXCEPT`.
4. **Có `UNION` đi cùng `EXCEPT` không?** Chúng cùng mức, được nhóm trái sang phải trong PostgreSQL; hiệu không giao hoán.
5. **Có cần giữ bản sao trùng không?** Chọn `UNION` hay `UNION ALL`, `INTERSECT` hay `INTERSECT ALL`, `EXCEPT` hay `EXCEPT ALL`.
6. **Những cột nào định nghĩa “dòng trùng”?** SQL so sánh toàn bộ cột đã chọn, không tự chọn khóa nghiệp vụ.
7. **Có `NULL` hoặc dữ liệu chuỗi với collation đặc thù không?** Đừng nhầm ngữ nghĩa tập với so sánh `=` trong `WHERE`.
8. **`ORDER BY`, `LIMIT`, `OFFSET` đang nằm ở cấp nào?** Nếu muốn top-N mỗi nhánh, nhóm nhánh đó bằng ngoặc; nếu muốn sắp/phân trang kết quả chung, đặt ở ngoài cùng.
9. **Kết quả có phải dùng trong nhiều hệ quản trị không?** Ghi ngoặc theo ngữ nghĩa thay vì lệ thuộc ưu tiên mặc định; kiểm tra hỗ trợ cú pháp và `ALL` trên hệ đích.
10. **Có thể viết CTE để trình bày các bước nghiệp vụ rõ hơn không?** CTE giúp đặt tên tập trung gian và dễ kiểm thử, nhưng không tự cam kết hiệu năng.

Một mẫu rất đáng nhớ:

```sql
-- Yêu cầu: (A hoặc B) và C, sau đó loại D.
WITH ab AS (
    SELECT member_id FROM source_a
    UNION
    SELECT member_id FROM source_b
),
abc AS (
    SELECT member_id FROM ab
    INTERSECT
    SELECT member_id FROM source_c
)
SELECT member_id FROM abc
EXCEPT
SELECT member_id FROM source_d
ORDER BY member_id;
```

`source_a`, `source_b`, `source_c`, `source_d` là tên minh họa cần thay bằng bảng hoặc CTE thực tế. Điểm quan trọng là **mỗi bước có một ý nghĩa riêng** và phạm vi loại trừ được quy định rõ.

**Nguyên tắc cuối cùng:** Với phép toán tập hợp, **dấu ngoặc là một phần của ý nghĩa truy vấn**. Hãy chọn thứ tự kết hợp dựa trên câu hỏi nghiệp vụ, hiểu quy tắc ưu tiên khi thiếu ngoặc, và đặt `ORDER BY`/`LIMIT` ở đúng cấp. Khi làm được điều đó, những truy vấn kết hợp nhiều tập không còn là chuỗi từ khóa khó đoán, mà trở thành một biểu thức logic rõ ràng, có thể giải thích và kiểm chứng bằng dữ liệu.

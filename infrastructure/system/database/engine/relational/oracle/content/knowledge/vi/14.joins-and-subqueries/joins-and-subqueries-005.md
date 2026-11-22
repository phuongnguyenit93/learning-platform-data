# ANSI JOIN và cú pháp Oracle (+) trong mã cũ

Trong Oracle Database, một truy vấn có thể kết hợp dữ liệu từ nhiều bảng bằng cú pháp JOIN. Mã SQL hiện đại thường dùng **ANSI JOIN** với các từ khóa `INNER JOIN`, `LEFT OUTER JOIN`, `RIGHT OUTER JOIN` và `FULL OUTER JOIN`. Trong nhiều hệ thống Oracle lâu năm, bạn vẫn sẽ gặp cú pháp riêng của Oracle dùng dấu `(+)` ở mệnh đề `WHERE` để biểu diễn outer join.

Hai cách viết có thể diễn đạt cùng một số phép nối, nhưng không nên đọc dấu `(+)` như một toán tử số học hay một ký hiệu tùy ý. Nó chỉ ra **bảng nào là phía tùy chọn** trong outer join kiểu cũ. Khi bảo trì hoặc chuyển đổi mã cũ, cần giữ đúng phía được bảo toàn, đặt điều kiện lọc đúng chỗ và kiểm tra số hàng sau JOIN.

Bài học đi từ cú pháp ANSI cơ bản đến cách đọc/chuyển đổi `(+)`, phân biệt `ON` với `WHERE`, xử lý nhiều điều kiện, self join, anti join, full outer join và các lỗi dễ làm mất hàng hoặc nhân bản dữ liệu.

## 1. JOIN giải quyết vấn đề gì?

Một cơ sở dữ liệu quan hệ thường chia thông tin thành nhiều bảng. Ví dụ:

- `DEPARTMENTS` lưu phòng ban.
- `EMPLOYEES` lưu nhân viên và mã phòng ban.
- `LOCATIONS` lưu địa điểm của phòng ban.

Muốn hiển thị tên phòng ban cùng tên nhân viên, cần ghép hàng từ hai bảng theo khóa liên quan:

~~~sql
SELECT d.department_name,
       e.employee_name
FROM departments d
JOIN employees e
  ON e.department_id = d.department_id;
~~~

`ON` xác định điều kiện ghép. Mỗi hàng kết quả đại diện cho một cặp hàng thỏa điều kiện. Nếu một phòng ban có nhiều nhân viên, tên phòng ban sẽ xuất hiện nhiều lần — đó là kết quả đúng của quan hệ một-nhiều.

~~~mermaid
erDiagram
    DEPARTMENTS ||--o{ EMPLOYEES : "department_id"
    DEPARTMENTS ||--o{ LOCATIONS : "location_id"
    DEPARTMENTS {
        number department_id PK
        varchar department_name
        number location_id FK
    }
    EMPLOYEES {
        number employee_id PK
        varchar employee_name
        number department_id FK
    }
    LOCATIONS {
        number location_id PK
        varchar city
    }
~~~

JOIN không tự biết hai bảng có quan hệ nghiệp vụ nào. Người viết phải chỉ định đúng khóa/điều kiện. Ghép nhầm cột hoặc thiếu điều kiện có thể tạo tích Descartes, làm số hàng tăng rất lớn hoặc làm tổng tiền bị nhân lên.

## 2. Các kiểu JOIN trong ANSI SQL

| Kiểu JOIN | Hàng được giữ lại | Khi không có hàng khớp ở phía còn lại |
|---|---|---|
| `INNER JOIN` | Chỉ các cặp hàng thỏa điều kiện | Hàng không khớp bị loại |
| `LEFT OUTER JOIN` | Tất cả hàng từ bảng bên trái, cộng các hàng phải khớp | Cột của bảng bên phải được điền `NULL` |
| `RIGHT OUTER JOIN` | Tất cả hàng từ bảng bên phải, cộng các hàng trái khớp | Cột của bảng bên trái được điền `NULL` |
| `FULL OUTER JOIN` | Tất cả hàng của cả hai phía | Phía không có đối tác được điền `NULL` |
| `CROSS JOIN` | Mọi tổ hợp hàng trái × hàng phải | Không cần điều kiện ghép |

Tên “trái” và “phải” dựa trên vị trí bảng trong câu `FROM ... JOIN ...`, không dựa vào tên schema hoặc bảng nào quan trọng hơn.

### 2.1 INNER JOIN

~~~sql
SELECT d.department_id,
       d.department_name,
       e.employee_id,
       e.employee_name
FROM departments d
INNER JOIN employees e
    ON e.department_id = d.department_id
ORDER BY d.department_id, e.employee_id;
~~~

`INNER` có thể viết ngắn thành `JOIN`. Chỉ phòng ban có nhân viên khớp mới xuất hiện; nhân viên có `DEPARTMENT_ID` NULL hoặc mã không khớp cũng không xuất hiện trong kết quả này.

### 2.2 LEFT OUTER JOIN

~~~sql
SELECT d.department_id,
       d.department_name,
       e.employee_id,
       e.employee_name
FROM departments d
LEFT OUTER JOIN employees e
    ON e.department_id = d.department_id
ORDER BY d.department_id, e.employee_id;
~~~

Kết quả giữ **mọi phòng ban**. Nếu phòng ban chưa có nhân viên, các cột `E.*` trả về `NULL`. Từ khóa `OUTER` là tùy chọn; `LEFT JOIN` có cùng ý nghĩa.

### 2.3 RIGHT OUTER JOIN

~~~sql
SELECT d.department_name,
       e.employee_id,
       e.employee_name
FROM departments d
RIGHT OUTER JOIN employees e
    ON e.department_id = d.department_id;
~~~

Truy vấn này giữ mọi nhân viên, kể cả người chưa được gán phòng ban hoặc có mã phòng ban không khớp. Có thể viết lại bằng `LEFT JOIN` bằng cách đảo vị trí hai bảng:

~~~sql
SELECT d.department_name,
       e.employee_id,
       e.employee_name
FROM employees e
LEFT JOIN departments d
    ON d.department_id = e.department_id;
~~~

Hai câu tương đương về tập hàng nếu điều kiện và các phép chiếu được giữ nguyên. Trong mã mới, nhiều nhóm chọn `LEFT JOIN` nhất quán vì dễ đọc bảng được bảo toàn ở bên trái.

### 2.4 FULL OUTER JOIN

~~~sql
SELECT d.department_id,
       d.department_name,
       e.employee_id,
       e.employee_name
FROM departments d
FULL OUTER JOIN employees e
    ON e.department_id = d.department_id;
~~~

Kết quả giữ:

- Phòng ban có nhân viên.
- Phòng ban không có nhân viên.
- Nhân viên có phòng ban khớp.
- Nhân viên không có phòng ban khớp.

Ở hàng chỉ có nhân viên, các cột phòng ban là `NULL`; ở hàng chỉ có phòng ban, các cột nhân viên là `NULL`. Nếu cần một mã phòng ban hiển thị chung từ hai phía, có thể dùng `COALESCE(d.department_id, e.department_id)`.

### 2.5 CROSS JOIN

~~~sql
SELECT c.color_name,
       s.size_name
FROM colors c
CROSS JOIN sizes s;
~~~

Nếu bảng `COLORS` có 4 hàng và `SIZES` có 3 hàng, kết quả có 12 tổ hợp. Đây là tích Descartes có chủ đích, thường dùng để tạo ma trận tổ hợp hoặc tập tham chiếu. Không thêm `CROSS JOIN` khi chỉ quên điều kiện `ON` của một phép nối thông thường.

## 3. ANSI JOIN: đặt điều kiện ghép ở ON

ANSI JOIN tách rõ ba phần:

~~~sql
SELECT danh_sach_cot
FROM bang_chinh a
JOIN bang_phu b
  ON dieu_kien_ghep
WHERE dieu_kien_loc;
~~~

- `FROM`/`JOIN` thể hiện bảng và loại quan hệ.
- `ON` mô tả cách ghép hai nguồn dữ liệu.
- `WHERE` lọc kết quả theo điều kiện truy vấn.

Ví dụ:

~~~sql
SELECT d.department_name,
       e.employee_name
FROM departments d
JOIN employees e
  ON e.department_id = d.department_id
WHERE d.active_flag = 'Y';
~~~

Ở đây điều kiện ghép là mã phòng ban; điều kiện chỉ lấy phòng ban đang hoạt động được đặt ở `WHERE`.

### 3.1 JOIN nhiều bảng

~~~sql
SELECT d.department_name,
       e.employee_name,
       l.city
FROM departments d
JOIN employees e
  ON e.department_id = d.department_id
LEFT JOIN locations l
  ON l.location_id = d.location_id;
~~~

Truy vấn yêu cầu:

1. Chỉ giữ nhân viên có phòng ban khớp.
2. Với phòng ban đã ghép, lấy địa điểm nếu có; nếu không có thì vẫn giữ nhân viên và trả `NULL` ở `CITY`.

Đọc từ trái sang phải giúp nhìn thấy từng bước kết hợp. Với truy vấn phức tạp, nên dùng alias nhất quán và xuống dòng điều kiện `ON` để người bảo trì xác định đúng bảng của từng cột.

### 3.2 Điều kiện ghép có nhiều cột

~~~sql
SELECT o.order_id,
       s.shipment_id
FROM orders o
JOIN shipments s
  ON s.order_id = o.order_id
 AND s.source_system = o.source_system;
~~~

Nếu khóa logic gồm hai cột, phải ghép bằng cả hai. Chỉ ghép `ORDER_ID` có thể nối nhầm dữ liệu từ hệ thống nguồn khác. Điều kiện `ON` có thể chứa nhiều biểu thức kết hợp bằng `AND`/`OR`; dùng ngoặc khi cần kiểm soát thứ tự logic.

### 3.3 JOIN theo cột cùng tên bằng USING

Nếu hai bảng có cột khóa cùng tên, ANSI hỗ trợ:

~~~sql
SELECT department_id,
       d.department_name,
       e.employee_name
FROM departments d
JOIN employees e
USING (department_id);
~~~

`USING` ngắn gọn khi tên cột ghép giống nhau. Cột được nêu trong `USING` được xem như một cột ghép duy nhất trong danh sách kết quả; trong một số ngữ cảnh, không được tham chiếu cột đó bằng tiền tố alias. Khi cần điều kiện nhiều biểu thức, tên cột khác nhau hoặc kiểm soát rõ ràng hơn, dùng `ON`.

Tránh `NATURAL JOIN` trong mã nghiệp vụ lâu dài: Oracle tự ghép theo **mọi cột cùng tên** ở hai bảng. Khi schema thêm một cột trùng tên, ý nghĩa truy vấn có thể thay đổi mà câu SQL không đổi. `ON` tường minh dễ review và ổn định hơn.

## 4. Cú pháp Oracle cũ: dấu (+) trong WHERE

Trước khi ANSI JOIN được dùng rộng rãi trong Oracle, outer join thường được viết bằng toán tử riêng `(+)` trong mệnh đề `WHERE`.

Ví dụ ANSI:

~~~sql
SELECT d.department_id,
       d.department_name,
       e.employee_id,
       e.employee_name
FROM departments d
LEFT OUTER JOIN employees e
    ON e.department_id = d.department_id;
~~~

Viết theo cú pháp Oracle cũ:

~~~sql
SELECT d.department_id,
       d.department_name,
       e.employee_id,
       e.employee_name
FROM departments d,
     employees e
WHERE e.department_id(+) = d.department_id;
~~~

Trong ví dụ này:

- `DEPARTMENTS d` là phía được giữ lại.
- `EMPLOYEES e` là phía tùy chọn, có thể không có hàng khớp.
- Dấu `(+)` đặt cạnh cột của bảng tùy chọn `e`.
- Nếu một phòng ban không có nhân viên, Oracle tạo hàng kết quả với các cột `e` bằng `NULL`.

**Quy tắc đọc nhanh:** trong điều kiện `A.col = B.col(+)`, bảng `A` được bảo toàn, còn hàng của `B` là tùy chọn. Đây tương ứng với `A LEFT OUTER JOIN B`.

### 4.1 Dấu (+) không phải dấu “cộng”

Không đọc:

~~~sql
e.department_id(+) = d.department_id
~~~

như một phép cộng hay một hàm. `(+)` là ký hiệu outer join kiểu cũ của Oracle, xuất hiện trong điều kiện so sánh ở `WHERE`. Nó đánh dấu phía có thể thiếu dữ liệu.

### 4.2 Muốn giữ bảng bên phải thì đặt (+) ở phía còn lại

ANSI:

~~~sql
SELECT d.department_name,
       e.employee_name
FROM departments d
RIGHT JOIN employees e
  ON e.department_id = d.department_id;
~~~

Oracle cũ:

~~~sql
SELECT d.department_name,
       e.employee_name
FROM departments d,
     employees e
WHERE d.department_id(+) = e.department_id;
~~~

Lần này `EMPLOYEES` được bảo toàn, còn `DEPARTMENTS` là phía tùy chọn. Dấu `(+)` được đặt ở cột phía `d`.

### 4.3 INNER JOIN cũ không cần (+)

ANSI:

~~~sql
SELECT d.department_name,
       e.employee_name
FROM departments d
JOIN employees e
  ON e.department_id = d.department_id;
~~~

Cú pháp comma join cũ:

~~~sql
SELECT d.department_name,
       e.employee_name
FROM departments d,
     employees e
WHERE e.department_id = d.department_id;
~~~

Không có `(+)` thì điều kiện bằng nhau là inner join. Cách viết cũ đặt điều kiện nối và điều kiện lọc chung trong `WHERE`; khi truy vấn có nhiều bảng, việc phân biệt chúng khó hơn ANSI.

## 5. Quy tắc quan trọng: điều kiện trên bảng tùy chọn phải ở đúng phía

Đây là nguồn gây lỗi lớn nhất khi đọc hoặc chuyển đổi cú pháp `(+)`.

Giả sử muốn giữ tất cả phòng ban nhưng chỉ ghép những nhân viên có trạng thái `ACTIVE`.

### 5.1 ANSI: điều kiện của bảng tùy chọn đặt trong ON

~~~sql
SELECT d.department_id,
       d.department_name,
       e.employee_name,
       e.status
FROM departments d
LEFT JOIN employees e
  ON e.department_id = d.department_id
 AND e.status = 'ACTIVE';
~~~

Ý nghĩa: với mỗi phòng ban, tìm nhân viên khớp mã **và** đang ACTIVE. Nếu không có nhân viên ACTIVE, phòng ban vẫn xuất hiện với cột `e.*` bằng NULL.

### 5.2 Oracle (+): đánh dấu cả điều kiện của phía tùy chọn

~~~sql
SELECT d.department_id,
       d.department_name,
       e.employee_name,
       e.status
FROM departments d,
     employees e
WHERE e.department_id(+) = d.department_id
  AND e.status(+) = 'ACTIVE';
~~~

Điều kiện `e.status(+) = 'ACTIVE'` thuộc logic outer join. Nó nói rằng chỉ những nhân viên ACTIVE mới được ghép, nhưng vẫn giữ phòng ban nếu không tìm được nhân viên như vậy.

### 5.3 Nếu bỏ (+) ở điều kiện trạng thái thì điều gì xảy ra?

~~~sql
SELECT d.department_id,
       d.department_name,
       e.employee_name,
       e.status
FROM departments d,
     employees e
WHERE e.department_id(+) = d.department_id
  AND e.status = 'ACTIVE';
~~~

Điều kiện `e.status = 'ACTIVE'` không có `(+)`. Với phòng ban không có nhân viên khớp, `e.status` là NULL; điều kiện so sánh không TRUE nên hàng phòng ban bị loại. Kết quả có thể giống inner join đối với điều kiện trạng thái và **làm mất mục tiêu giữ mọi phòng ban**.

ANSI có lỗi tương đương nếu đặt điều kiện ở `WHERE`:

~~~sql
SELECT d.department_id,
       d.department_name,
       e.employee_name
FROM departments d
LEFT JOIN employees e
  ON e.department_id = d.department_id
WHERE e.status = 'ACTIVE';
~~~

Đây là một trong những điểm quan trọng nhất:

| Điều kiện | Ý nghĩa |
|---|---|
| `LEFT JOIN ... ON key AND e.status = 'ACTIVE'` | Giữ tất cả phòng ban; chỉ ghép nhân viên ACTIVE |
| `LEFT JOIN ... ON key WHERE e.status = 'ACTIVE'` | Loại hàng không có nhân viên ACTIVE; thường cho kết quả như inner join đối với điều kiện đó |
| Cú pháp cũ `e.key(+) = d.key AND e.status(+) = 'ACTIVE'` | Giữ tất cả phòng ban; lọc nhân viên trong điều kiện outer join |
| Cú pháp cũ `e.key(+) = d.key AND e.status = 'ACTIVE'` | Điều kiện trạng thái null-rejecting làm mất phòng ban không có nhân viên khớp |

**Hãy xác định câu hỏi nghiệp vụ:** muốn lọc hàng nguồn trước khi ghép, hay muốn lọc kết quả sau khi đã ghép? Với outer join, hai cách này không tương đương.

## 6. Nhiều điều kiện nối giữa cùng hai bảng

Nếu outer join dựa trên nhiều điều kiện, cú pháp `(+)` phải được áp dụng nhất quán cho các điều kiện của phía tùy chọn.

ANSI:

~~~sql
SELECT o.order_id,
       s.shipment_id
FROM orders o
LEFT JOIN shipments s
  ON s.order_id = o.order_id
 AND s.source_system = o.source_system;
~~~

Oracle cũ:

~~~sql
SELECT o.order_id,
       s.shipment_id
FROM orders o,
     shipments s
WHERE s.order_id(+) = o.order_id
  AND s.source_system(+) = o.source_system;
~~~

Nếu chỉ đặt `(+)` trên một điều kiện và quên ở điều kiện còn lại, Oracle có thể không thực hiện outer join như dự định và trả về kết quả chỉ có các cặp khớp. Đây là lỗi khó phát hiện vì câu SQL vẫn có thể chạy mà không báo lỗi cú pháp.

Khi chuyển sang ANSI, đặt tất cả điều kiện ghép trong cùng `ON`:

~~~sql
LEFT JOIN shipments s
  ON s.order_id = o.order_id
 AND s.source_system = o.source_system
 AND s.is_current = 'Y'
~~~

Nếu `IS_CURRENT` là tiêu chí của hàng shipment được ghép, nó nằm trong `ON`; nếu là tiêu chí lọc kết quả cuối và chấp nhận loại đơn không có shipment hiện hành, mới đặt ở `WHERE`.

## 7. Self join: một bảng xuất hiện hai vai trò

Self join là phép nối một bảng với chính nó, thường dùng cho quan hệ nhân viên–quản lý, danh mục cha–con hoặc bản ghi thay thế.

ANSI:

~~~sql
SELECT e.employee_id,
       e.employee_name,
       m.employee_name AS manager_name
FROM employees e
LEFT JOIN employees m
  ON m.employee_id = e.manager_id;
~~~

Mỗi alias biểu diễn một vai trò:

- `e` là nhân viên.
- `m` là người quản lý.
- `LEFT JOIN` giữ cả nhân viên chưa có quản lý.

Cú pháp Oracle cũ cũng phải dùng alias riêng:

~~~sql
SELECT e.employee_id,
       e.employee_name,
       m.employee_name AS manager_name
FROM employees e,
     employees m
WHERE e.manager_id = m.employee_id(+);
~~~

Không thể bỏ alias rồi dùng cùng một tên bảng để phân biệt hai vai trò. Trong mã mới, ANSI giúp đọc rõ hơn vì mỗi alias được gắn ngay vào điều kiện `ON`.

## 8. FULL OUTER JOIN và giới hạn của dấu (+)

ANSI hỗ trợ trực tiếp:

~~~sql
SELECT COALESCE(a.business_key, b.business_key) AS business_key,
       a.value_a,
       b.value_b
FROM source_a a
FULL OUTER JOIN source_b b
  ON b.business_key = a.business_key;
~~~

Kết quả giữ:

- Khóa có ở cả hai nguồn.
- Khóa chỉ có ở `SOURCE_A`.
- Khóa chỉ có ở `SOURCE_B`.

Cú pháp Oracle cũ `(+)` **không có cách viết trực tiếp tương đương một FULL OUTER JOIN tổng quát**. Không thể đặt `(+)` ở cả hai phía của cùng điều kiện để tạo full outer join.

Nếu bảo trì mã cũ, cách rõ ràng nhất là dùng ANSI `FULL OUTER JOIN` trên phiên bản Oracle hỗ trợ. Với môi trường hoặc tình huống cần mô phỏng, có thể kết hợp hai hướng outer join bằng `UNION ALL` và loại phần trùng, nhưng phải thiết kế cẩn thận để không nhân bản hàng:

~~~sql
-- Minh họa full outer join bằng hai nhánh; ưu tiên cú pháp ANSI FULL OUTER JOIN.
SELECT a.business_key,
       a.value_a,
       b.value_b
FROM source_a a
LEFT JOIN source_b b
  ON b.business_key = a.business_key

UNION ALL

SELECT b.business_key,
       a.value_a,
       b.value_b
FROM source_b b
LEFT JOIN source_a a
  ON a.business_key = b.business_key
WHERE a.business_key IS NULL;
~~~

Điều kiện `a.business_key IS NULL` ở nhánh hai chỉ an toàn để nhận diện “không có hàng A” nếu `BUSINESS_KEY` ở bảng A **không NULL khi hàng tồn tại**, thường là khóa chính/unique not null. Nếu khóa ghép hoặc cột có thể NULL, dùng một cột định danh không null khác để kiểm tra sự vắng mặt. Ngoài ra, `UNION ALL` giữ nguyên các hàng trùng hợp lệ; nếu nghiệp vụ cần loại trùng thì phải định nghĩa khóa và quy tắc trùng cụ thể.

## 9. Anti join: tìm hàng không có đối tác

Một yêu cầu phổ biến là tìm phòng ban chưa có nhân viên. Có hai cách diễn đạt.

### 9.1 LEFT JOIN ... IS NULL

~~~sql
SELECT d.department_id,
       d.department_name
FROM departments d
LEFT JOIN employees e
  ON e.department_id = d.department_id
WHERE e.employee_id IS NULL;
~~~

`EMPLOYEE_ID` phải là cột định danh không NULL của hàng nhân viên (ví dụ primary key). Nếu không có nhân viên ghép, các cột phía `e` được null-extend và hàng phòng ban được chọn.

Không nên kiểm tra `e.some_nullable_column IS NULL` nếu cột đó có thể NULL ở một nhân viên thực sự khớp; khi ấy không phân biệt được “không có hàng ghép” với “có hàng nhưng cột dữ liệu NULL”.

### 9.2 NOT EXISTS

~~~sql
SELECT d.department_id,
       d.department_name
FROM departments d
WHERE NOT EXISTS (
    SELECT 1
    FROM employees e
    WHERE e.department_id = d.department_id
);
~~~

`NOT EXISTS` diễn đạt trực tiếp ý “không tồn tại nhân viên khớp”. Nó thường dễ đọc khi chỉ cần kiểm tra sự tồn tại, không cần lấy cột từ bảng phụ. Oracle optimizer có thể chuyển thành anti-join trong execution plan.

### 9.3 Dùng cú pháp (+) để tìm hàng không khớp

Mã Oracle cũ có thể viết:

~~~sql
SELECT d.department_id,
       d.department_name
FROM departments d,
     employees e
WHERE e.department_id(+) = d.department_id
  AND e.employee_id IS NULL;
~~~

Trong mẫu này, `EMPLOYEE_ID` là khóa không null của bảng nhân viên và điều kiện `IS NULL` được dùng để nhận diện hàng không ghép. Khi đọc mã legacy, cần xác nhận cột kiểm tra là cột bắt buộc/khóa không NULL. Với mã mới, `NOT EXISTS` thường thể hiện ý định rõ hơn.

## 10. NULL trong điều kiện JOIN

Điều kiện:

~~~sql
ON a.customer_id = b.customer_id
~~~

không coi `NULL` bằng `NULL`. Nếu cả hai cột đều NULL, điều kiện không TRUE nên hai hàng không khớp nhau. Đây là hành vi logic SQL, không phải lỗi outer join.

Nếu nghiệp vụ muốn ghép hai giá trị NULL như một nhóm “chưa xác định”, phải viết điều kiện riêng, ví dụ:

~~~sql
ON a.customer_id = b.customer_id
OR (a.customer_id IS NULL AND b.customer_id IS NULL)
~~~

Tuy nhiên điều kiện này có thể làm nhiều hàng NULL ghép chéo với nhau, tạo số hàng lớn và thường không mong muốn. Tốt hơn là dùng khóa định danh thực sự không NULL hoặc một mã thay thế có quy tắc rõ ràng.

### 10.1 NVL trong khóa JOIN cần cẩn trọng

Một số mã cũ viết:

~~~sql
ON NVL(a.customer_id, -1) = NVL(b.customer_id, -1)
~~~

Điều này coi mọi NULL như cùng một mã giả `-1`. Nếu `-1` có thể là giá trị hợp lệ hoặc nhiều hàng cùng NULL, kết quả có thể ghép nhiều-nhiều. Hàm trên cột cũng có thể ảnh hưởng khả năng dùng index thông thường. Chỉ áp dụng khi miền giá trị và quy tắc nghiệp vụ bảo đảm sentinel không va chạm; ưu tiên khóa không NULL.

## 11. WHERE, ON và thứ tự lọc trong outer join

Với inner join, điều kiện lọc liên quan bảng có thể thường được chuyển giữa `ON` và `WHERE` mà không thay đổi tập kết quả. Với outer join, vị trí điều kiện có thể thay đổi kết quả.

Giả sử cần mọi phòng ban và thông tin nhân viên đang làm việc:

~~~sql
-- Giữ mọi phòng ban; chỉ ghép nhân viên ACTIVE.
SELECT d.department_id,
       e.employee_id
FROM departments d
LEFT JOIN employees e
  ON e.department_id = d.department_id
 AND e.status = 'ACTIVE';
~~~

Nếu viết:

~~~sql
-- Chỉ trả phòng ban có nhân viên ACTIVE khớp.
SELECT d.department_id,
       e.employee_id
FROM departments d
LEFT JOIN employees e
  ON e.department_id = d.department_id
WHERE e.status = 'ACTIVE';
~~~

thì các hàng không có nhân viên sẽ có `e.status = NULL` và bị `WHERE` loại. Kết quả không còn bảo toàn mọi phòng ban.

Một quy tắc thực hành:

- `ON` mô tả **điều kiện để một hàng phía tùy chọn được ghép**.
- `WHERE` mô tả **điều kiện lọc kết quả sau khi ghép**, bao gồm cả việc có chủ ý loại hàng null-extended hay không.

Đừng máy móc chuyển mọi điều kiện trong `WHERE` của mã `(+)` sang `WHERE` ANSI; một số điều kiện thuộc logic ghép phải chuyển vào `ON`.

## 12. Các hạn chế quan trọng của cú pháp (+)

Toán tử `(+)` là cú pháp Oracle cũ và có nhiều hạn chế. Khi bảo trì, cần đối chiếu tài liệu Oracle đúng release; những hạn chế lịch sử có thể thay đổi theo phiên bản.

Các quy tắc phổ biến cần nhớ:

1. **Dùng trong điều kiện WHERE**, không đặt `(+)` trong mệnh đề `FROM ... JOIN ... ON`.
2. **Không trộn cú pháp `(+)` và ANSI JOIN trong cùng query block.** Oracle có thể báo `ORA-25156: old style outer join (+) cannot be used with ANSI joins`.
3. Nếu một cặp bảng có nhiều điều kiện outer join, phải đánh dấu phía tùy chọn nhất quán ở các điều kiện liên quan. Thiếu dấu `(+)` ở một điều kiện có thể làm mất hành vi outer join như mong đợi.
4. Có các hạn chế khi kết hợp `(+)` với `OR`, `IN`, subquery hoặc biểu thức phức tạp; nhiều trường hợp phải viết lại bằng ANSI JOIN/EXISTS.
5. Muốn self join phải dùng alias riêng cho hai vai trò của cùng bảng.
6. `(+)` không biểu diễn trực tiếp `FULL OUTER JOIN`.
7. Các giới hạn outer join nhiều bảng từng phụ thuộc phiên bản; không nên dựa vào một truy vấn cũ phức tạp mà không kiểm tra release.

Ví dụ một cách viết không hợp lệ/không được hỗ trợ theo quy tắc cũ:

~~~sql
-- Không dùng cú pháp trộn như thế này trong cùng query block:
SELECT *
FROM departments d
JOIN locations l
  ON l.location_id = d.location_id,
     employees e
WHERE e.department_id(+) = d.department_id;
~~~

Viết lại toàn bộ bằng ANSI:

~~~sql
SELECT d.department_name,
       l.city,
       e.employee_name
FROM departments d
JOIN locations l
  ON l.location_id = d.location_id
LEFT JOIN employees e
  ON e.department_id = d.department_id;
~~~

### 12.1 Không đặt dấu (+) tùy ý vào điều kiện OR

Các truy vấn dạng:

~~~sql
-- Mẫu legacy có vấn đề theo hạn chế của (+):
WHERE e.department_id(+) = d.department_id
  AND (e.status(+) = 'ACTIVE' OR d.include_all = 'Y')
~~~

có thể bị từ chối hoặc không diễn đạt được logic mong muốn. Hãy chuyển điều kiện sang ANSI, đặt phần ghép vào `ON` và phần lọc kết quả vào `WHERE` với ngoặc logic rõ ràng. Nếu điều kiện tồn tại phức tạp, cân nhắc `EXISTS` hoặc một CTE phân loại trước khi JOIN.

### 12.2 Không so sánh cột (+) với subquery tùy tiện

Một số dạng so sánh cột được đánh dấu `(+)` với subquery bị hạn chế. Khi gặp mã cũ có subquery trong điều kiện outer join, đừng cố thêm dấu `(+)` vào nhiều chỗ để làm cho nó chạy. Tách subquery thành inline view/CTE rồi dùng ANSI JOIN thường dễ hiểu và dễ kiểm soát hơn.

## 13. Chuyển đổi mã legacy từ (+) sang ANSI JOIN

Khi refactor, không chỉ thay dấu `(+)` bằng từ khóa `LEFT JOIN`. Phải xác định:

1. Bảng nào được bảo toàn?
2. Bảng nào là phía tùy chọn?
3. Những điều kiện nào thuộc quan hệ ghép?
4. Những điều kiện nào là bộ lọc kết quả?
5. Có điều kiện nào trên phía tùy chọn đang được dùng để giữ hay loại hàng NULL không?
6. JOIN có làm thay đổi grain/số hàng do quan hệ một-nhiều không?

### 13.1 Quy tắc chuyển đổi cơ bản

| Cú pháp cũ | ANSI tương ứng |
|---|---|
| `FROM A a, B b WHERE a.id = b.id` | `FROM A a JOIN B b ON a.id = b.id` |
| `WHERE b.a_id(+) = a.id` | `FROM A a LEFT JOIN B b ON b.a_id = a.id` |
| `WHERE a.b_id(+) = b.id` | `FROM B b LEFT JOIN A a ON a.b_id = b.id` |
| `WHERE b.a_id(+) = a.id AND b.flag(+) = 'Y'` | `FROM A a LEFT JOIN B b ON b.a_id = a.id AND b.flag = 'Y'` |
| `WHERE b.a_id(+) = a.id AND a.active = 'Y'` | `FROM A a LEFT JOIN B b ON b.a_id = a.id WHERE a.active = 'Y'` |

### 13.2 Ví dụ chuyển đổi đầy đủ

Mã cũ:

~~~sql
SELECT d.department_id,
       d.department_name,
       e.employee_id,
       e.employee_name
FROM departments d,
     employees e
WHERE e.department_id(+) = d.department_id
  AND e.status(+) = 'ACTIVE'
  AND d.region_id = 'NORTH';
~~~

Đọc ý nghĩa:

- Giữ các phòng ban vùng NORTH.
- Với mỗi phòng ban, ghép nhân viên ACTIVE nếu có.
- Phòng ban không có nhân viên ACTIVE vẫn xuất hiện.

ANSI:

~~~sql
SELECT d.department_id,
       d.department_name,
       e.employee_id,
       e.employee_name
FROM departments d
LEFT JOIN employees e
  ON e.department_id = d.department_id
 AND e.status = 'ACTIVE'
WHERE d.region_id = 'NORTH';
~~~

Điều kiện trạng thái của phía tùy chọn chuyển vào `ON`; điều kiện vùng của phía được bảo toàn nằm ở `WHERE`.

### 13.3 Tránh chuyển đổi làm thay đổi kết quả

Một truy vấn cũ:

~~~sql
SELECT d.department_id,
       e.employee_id
FROM departments d,
     employees e
WHERE e.department_id(+) = d.department_id
  AND e.status = 'ACTIVE';
~~~

Không tương đương với:

~~~sql
SELECT d.department_id,
       e.employee_id
FROM departments d
LEFT JOIN employees e
  ON e.department_id = d.department_id
 AND e.status = 'ACTIVE';
~~~

Vì truy vấn cũ có điều kiện `e.status = 'ACTIVE'` không có `(+)`, nên phòng ban không có nhân viên ACTIVE bị loại. Truy vấn ANSI thứ hai giữ các phòng ban đó. Muốn bảo toàn kết quả cũ, viết:

~~~sql
SELECT d.department_id,
       e.employee_id
FROM departments d
LEFT JOIN employees e
  ON e.department_id = d.department_id
WHERE e.status = 'ACTIVE';
~~~

Đây là lý do cần chuyển **ngữ nghĩa** chứ không chuyển ký tự. Nếu ý định của mã cũ vốn là giữ mọi phòng ban, có thể mã cũ đã có bug; việc sửa bug phải được xác nhận bằng yêu cầu nghiệp vụ và dữ liệu đối chiếu.

## 14. JOIN và aggregate: cẩn thận với số hàng sau ghép

JOIN có thể tạo nhiều hàng cho một thực thể. Ví dụ một phòng ban có 5 nhân viên; sau khi join, phòng ban xuất hiện 5 lần. Nếu cộng ngân sách phòng ban sau JOIN, tổng sẽ bị nhân lên.

~~~sql
SELECT d.department_id,
       SUM(d.annual_budget) AS budget_after_join,
       COUNT(e.employee_id) AS employee_count
FROM departments d
LEFT JOIN employees e
  ON e.department_id = d.department_id
GROUP BY d.department_id;
~~~

Nếu `ANNUAL_BUDGET` là giá trị cấp phòng ban, `SUM(d.annual_budget)` cộng lặp ngân sách theo số nhân viên. Đối với dữ liệu cấp phòng ban, có thể dùng `MAX(d.annual_budget)`/`MIN` khi bảo đảm một giá trị duy nhất cho mỗi phòng ban, hoặc tổng hợp bảng nhân viên riêng trước khi JOIN:

~~~sql
WITH employee_counts AS (
    SELECT department_id,
           COUNT(*) AS employee_count
    FROM employees
    GROUP BY department_id
)
SELECT d.department_id,
       d.annual_budget,
       NVL(ec.employee_count, 0) AS employee_count
FROM departments d
LEFT JOIN employee_counts ec
  ON ec.department_id = d.department_id;
~~~

### 14.1 COUNT(*) khác COUNT(cột phía tùy chọn)

~~~sql
SELECT d.department_id,
       COUNT(*) AS joined_row_count,
       COUNT(e.employee_id) AS matched_employee_count
FROM departments d
LEFT JOIN employees e
  ON e.department_id = d.department_id
GROUP BY d.department_id;
~~~

Với phòng ban không có nhân viên:

- `COUNT(*)` là 1 vì LEFT JOIN vẫn tạo một hàng null-extended cho phòng ban.
- `COUNT(e.employee_id)` là 0 vì khóa nhân viên là NULL ở hàng không khớp.

Nếu muốn đếm nhân viên, dùng cột định danh không NULL ở phía nhân viên hoặc `COUNT(CASE WHEN ... THEN 1 END)`.

## 15. Ví dụ kết hợp ba bảng với cả INNER và LEFT JOIN

Yêu cầu: liệt kê nhân viên có phòng ban; hiển thị địa điểm phòng ban nếu có; vẫn giữ nhân viên khi địa điểm chưa được khai báo.

~~~sql
SELECT e.employee_id,
       e.employee_name,
       d.department_name,
       l.city
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id
LEFT JOIN locations l
  ON l.location_id = d.location_id
ORDER BY d.department_id, e.employee_id;
~~~

Ý nghĩa theo từng bước:

1. `EMPLOYEES JOIN DEPARTMENTS`: chỉ giữ nhân viên có phòng ban hợp lệ.
2. `LEFT JOIN LOCATIONS`: tìm địa điểm của phòng ban nhưng không loại nhân viên nếu thiếu location.

Nếu đổi phép nối đầu thành `LEFT JOIN` từ `EMPLOYEES` sang `DEPARTMENTS`, kết quả sẽ giữ cả nhân viên chưa có phòng ban. Hãy chọn loại JOIN theo yêu cầu giữ hàng, không theo thói quen.

## 16. Kiểm tra kết quả khi chuyển đổi hoặc bảo trì

Khi chuyển mã legacy, cần so sánh **tập hàng và giá trị**, không chỉ kiểm tra câu SQL mới chạy không lỗi.

Một cách kiểm tra thực tế:

1. Chọn một khoảng dữ liệu đại diện có cả trường hợp khớp và không khớp.
2. Chạy câu cũ và câu ANSI trên cùng snapshot/transaction phù hợp.
3. So sánh số hàng tổng, số hàng không khớp và số hàng có giá trị NULL ở phía tùy chọn.
4. So sánh theo khóa định danh, không chỉ tổng số hàng.
5. Kiểm tra các chỉ số aggregate trước/sau JOIN để phát hiện nhân bản.
6. Đối chiếu các điều kiện `ON`/`WHERE` đặc biệt, nhất là predicate trên bảng tùy chọn.

Ví dụ số liệu đối chiếu:

~~~sql
-- Đếm tổng hàng và hàng không có nhân viên ghép.
SELECT COUNT(*) AS result_rows,
       COUNT(e.employee_id) AS matched_employees,
       COUNT(CASE WHEN e.employee_id IS NULL THEN 1 END)
           AS departments_without_employee
FROM departments d
LEFT JOIN employees e
  ON e.department_id = d.department_id;
~~~

Đây là phép đo nhanh; nếu một phòng ban có nhiều nhân viên, `RESULT_ROWS` sẽ lớn hơn số phòng ban. Để đếm số phòng ban duy nhất có/không có nhân viên, dùng `COUNT(DISTINCT d.department_id)` hoặc tổng hợp theo phòng ban trước.

## 17. Lỗi và hiểu nhầm thường gặp

| Lỗi/triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `ORA-25156: old style outer join (+) cannot be used with ANSI joins` | Trộn cú pháp `(+)` và ANSI trong cùng query block | Chuyển toàn bộ query block sang ANSI hoặc giữ toàn bộ cú pháp cũ trong lúc chưa refactor |
| Phòng ban không có nhân viên biến mất | Điều kiện trên `e.*` nằm trong `WHERE` làm null-rejecting | Đưa predicate thuộc logic ghép vào `ON` nếu muốn giữ phòng ban |
| Outer join trả ít hàng hơn dự kiến | Thiếu `(+)` ở một điều kiện hoặc đặt nhầm phía tùy chọn | Xác định bảng preserved/optional, đánh dấu nhất quán hoặc chuyển ANSI |
| Tổng doanh thu tăng sau JOIN | Quan hệ một-nhiều nhân bản hàng cấp cha | Xác định grain, tổng hợp detail trước hoặc dùng nguồn đúng cấp |
| `COUNT(*)` lớn hơn số nhân viên | LEFT JOIN giữ hàng cha không có con | Dùng `COUNT(e.primary_key)` để đếm hàng con |
| Dùng `(+)` cho FULL OUTER JOIN không được | Cú pháp cũ không biểu diễn full outer trực tiếp | Dùng `FULL OUTER JOIN` ANSI |
| Self join bị mơ hồ tên cột | Không đặt alias riêng cho từng vai trò | Dùng alias như `employee e` và `employee m` |
| Hai khóa NULL không ghép | `NULL = NULL` không phải TRUE | Xác định nghiệp vụ; dùng khóa không NULL hoặc điều kiện riêng có kiểm soát |
| `NOT IN`/`OR` kết hợp dấu (+) bị lỗi | Hạn chế của cú pháp Oracle cũ | Chuyển sang ANSI, `EXISTS` hoặc CTE |
| LEFT JOIN biến thành inner-like | Điều kiện trên bảng phải nằm trong WHERE | Phân biệt lọc kết quả với điều kiện ghép |
| Truy vấn chạy nhưng ghép sai hàng | Thiếu một phần khóa ghép hoặc join nhầm cột | Ghép đủ khóa, xác nhận cardinality và dữ liệu |

## 18. Bài thực hành tự kiểm tra

Giả sử có ba bảng:

~~~sql
-- Cấu trúc khái niệm:
-- DEPARTMENTS(department_id, department_name, location_id)
-- EMPLOYEES(employee_id, employee_name, department_id, status, manager_id)
-- LOCATIONS(location_id, city)
~~~

### Bài 1 — Chuyển INNER JOIN

Viết câu ANSI JOIN để liệt kê nhân viên và tên phòng ban. Viết lại cùng câu bằng comma join và điều kiện `WHERE` kiểu cũ. Vì sao hai câu chỉ trả các hàng có khóa phòng ban khớp?

### Bài 2 — Chuyển LEFT JOIN sang (+)

Viết ANSI `DEPARTMENTS LEFT JOIN EMPLOYEES`. Sau đó viết cú pháp cũ với `e.department_id(+) = d.department_id`. Nêu bảng nào được bảo toàn và cột nào thành NULL khi không có nhân viên.

### Bài 3 — Predicate trên bảng tùy chọn

Yêu cầu giữ mọi phòng ban nhưng chỉ ghép nhân viên ACTIVE. Viết cả hai dạng:

- ANSI: trạng thái ở `ON`.
- Oracle cũ: trạng thái ở điều kiện có `(+)`.

Sau đó chuyển trạng thái sang `WHERE` và giải thích phòng ban nào biến mất.

### Bài 4 — RIGHT JOIN

Viết truy vấn giữ mọi nhân viên kể cả không có phòng ban. Thực hiện một phiên bản `RIGHT JOIN` và một phiên bản `LEFT JOIN` đảo thứ tự bảng. So sánh tập hàng.

### Bài 5 — FULL OUTER JOIN

Một nguồn A và nguồn B chứa danh sách mã khách hàng từ hai hệ thống. Viết `FULL OUTER JOIN` để giữ mã có ở một hoặc cả hai nguồn. Dùng `COALESCE` hiển thị khóa chung. Giải thích tại sao `(+)` không thể thay thế trực tiếp.

### Bài 6 — Anti join

Tìm phòng ban không có nhân viên bằng `LEFT JOIN ... WHERE e.employee_id IS NULL` và `NOT EXISTS`. Vì sao phải chọn cột khóa không NULL để kiểm tra?

### Bài 7 — NULL và JOIN

Hai bảng có `CUSTOMER_ID` NULL. Dự đoán kết quả của `a.customer_id = b.customer_id`. Nếu ghép NULL với NULL theo quy tắc riêng, những rủi ro nhân bản hàng nào có thể xảy ra?

### Bài 8 — COUNT

Một phòng ban chưa có nhân viên. So sánh `COUNT(*)` và `COUNT(e.employee_id)` trong LEFT JOIN. Chỉ số nào phản ánh số nhân viên thật?

### Bài 9 — Grain và aggregate

Một phòng ban có ngân sách 1.000.000 và 4 nhân viên. JOIN rồi `SUM(d.annual_budget)` cho kết quả gì? Viết lại truy vấn để trả ngân sách một lần và số nhân viên là 4.

### Bài 10 — Refactor mã legacy

Chuyển truy vấn sau sang ANSI và giữ nguyên ý nghĩa:

~~~sql
SELECT d.department_id,
       e.employee_id
FROM departments d,
     employees e
WHERE e.department_id(+) = d.department_id
  AND e.status(+) = 'ACTIVE'
  AND d.region_id = 'NORTH';
~~~

Sau đó viết một biến thể có điều kiện `e.status = 'ACTIVE'` trong `WHERE`. Giải thích sự khác nhau và chọn câu phù hợp với yêu cầu giữ mọi phòng ban NORTH.

## 19. Quy trình đọc và chuyển đổi một truy vấn (+) cũ

Khi gặp truy vấn legacy, thực hiện theo trình tự:

~~~mermaid
flowchart TD
    A["Đọc FROM và alias"] --> B["Tìm từng điều kiện có (+)"]
    B --> C["Xác định bảng không có (+): phía được bảo toàn"]
    C --> D["Xác định tất cả predicate của phía tùy chọn"]
    D --> E["Tách predicate ghép và predicate lọc"]
    E --> F["Viết ANSI JOIN với ON/WHERE rõ ràng"]
    F --> G["Đối chiếu hàng khớp, hàng không khớp và aggregate"]
    G --> H["Kiểm tra plan và phát hành thay đổi"]
~~~

Checklist đọc cú pháp cũ:

- Cột nào có `(+)`? Bảng đó là phía tùy chọn trong điều kiện outer join.
- Bảng nào không có `(+)`? Bảng đó được bảo toàn.
- Có nhiều điều kiện ghép không? Đánh dấu phía tùy chọn nhất quán.
- Có predicate trên bảng tùy chọn không có `(+)`? Predicate đó có thể làm mất hàng null-extended.
- Có `OR`, `IN`, subquery, self join hoặc nhiều bảng? Xem hạn chế cú pháp cũ và cân nhắc viết lại bằng ANSI.
- Có đang cần FULL OUTER JOIN không? Dùng ANSI.
- Sau JOIN có nhân bản hàng cấp cha không? Kiểm tra grain trước khi aggregate.

## 20. Ghi nhớ

| Câu hỏi | Quy tắc |
|---|---|
| ANSI JOIN đặt điều kiện nối ở đâu? | `ON` |
| INNER JOIN giữ hàng nào? | Chỉ cặp hàng khớp |
| LEFT JOIN giữ bảng nào? | Giữ tất cả hàng bảng bên trái |
| RIGHT JOIN giữ bảng nào? | Giữ tất cả hàng bảng bên phải |
| FULL OUTER JOIN giữ gì? | Tất cả hàng cả hai phía, ghép được thì ghép |
| `A.id = B.id(+)` nghĩa gì? | A được bảo toàn, B là phía tùy chọn |
| Predicate phía tùy chọn để ở đâu trong ANSI? | `ON` nếu muốn giữ hàng trái không có hàng thỏa predicate |
| Predicate ở WHERE có thể làm gì? | Loại hàng null-extended và khiến outer join thành inner-like |
| Có thể trộn (+) và ANSI trong cùng query block? | Không; có thể gặp `ORA-25156` |
| Dấu (+) có biểu diễn FULL OUTER JOIN trực tiếp? | Không |
| Đếm hàng con sau LEFT JOIN? | `COUNT(child_primary_key)`, không phải luôn `COUNT(*)` |
| Chuyển mã cũ có chỉ thay ký hiệu không? | Không; phải bảo toàn phía được giữ, predicate và grain |

ANSI JOIN là cách viết nên ưu tiên cho mã mới vì loại JOIN và điều kiện ghép được thể hiện rõ ràng. Cú pháp `(+)` vẫn cần đọc được khi bảo trì hệ thống cũ: dấu này đánh dấu **phía tùy chọn**, và vị trí của các predicate quyết định hàng nào được giữ. Khi refactor, chuyển đúng ngữ nghĩa sang `ON`/`WHERE`, kiểm tra trường hợp không có hàng khớp, NULL, nhiều điều kiện và số hàng sau JOIN. Như vậy truy vấn mới vừa dễ đọc vừa giữ được kết quả nghiệp vụ mà mã cũ thực sự cần.

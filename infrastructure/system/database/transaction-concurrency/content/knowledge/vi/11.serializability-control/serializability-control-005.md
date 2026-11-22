# Theo dõi điều kiện đọc và tập hàng có thể thay đổi

Khi kiểm soát khả năng tuần tự hóa (*serializability*), cơ sở dữ liệu cần biết một giao dịch đã dựa vào dữ liệu nào để đưa ra quyết định. Việc theo dõi chỉ những hàng mà câu truy vấn trả về đôi khi chưa đủ: một giao dịch khác có thể chèn hàng mới hoặc cập nhật hàng cũ để hàng đó bắt đầu thỏa điều kiện truy vấn. Tập kết quả khi ấy thay đổi dù giao dịch đọc chưa thực hiện lại câu truy vấn.

Để phát hiện hoặc ngăn loại xung đột này, hệ thống cần theo dõi **điều kiện đọc** (*read predicate*) cùng với các hàng đã đọc. Điều kiện đọc mô tả tập hàng mà giao dịch quan tâm, chẳng hạn `status = 'PENDING' AND amount >= 100`. Hệ thống sau đó có thể xác định một thao tác ghi của giao dịch khác có làm thay đổi tập hàng hoặc giá trị mà giao dịch đọc dựa vào hay không.

Các hệ thống có thể bảo vệ điều kiện đọc bằng khóa phạm vi/khóa vị từ, hoặc theo dõi quan hệ đọc-ghi rồi kiểm tra khả năng tuần tự hóa trước khi cho các giao dịch cùng commit. Cơ chế cụ thể khác nhau, nhưng mục tiêu chung là phát hiện những phụ thuộc có thể làm lịch thực thi không tương đương với một thứ tự tuần tự hợp lệ.

## 1. Vì sao theo dõi hàng đã đọc là chưa đủ?

Giả sử giao dịch `T1` chạy truy vấn:

```sql
SELECT order_id, amount
FROM orders
WHERE status = 'PENDING'
  AND amount >= 100;
```

Truy vấn trả về các đơn hàng `1001` và `1003`. Một hệ thống chỉ ghi nhận hai khóa chính này có thể biết `T1` đã đọc hai hàng đó. Nhưng nó chưa biết rằng `T1` còn phụ thuộc vào điều kiện xác định **hàng nào được phép xuất hiện trong kết quả**.

Trong lúc `T1` đang chạy, `T2` có thể thực hiện một trong các thao tác sau:

- Chèn đơn hàng mới với `status = 'PENDING'` và `amount = 150`.
- Cập nhật một đơn hàng đang có `amount` từ `80` lên `150`.
- Cập nhật một đơn hàng đang `PENDING` thành `CANCELLED`.
- Xóa một đơn hàng đang thỏa điều kiện.

Những thao tác này làm thay đổi tập hàng thỏa điều kiện truy vấn. Nếu `T1` đang thực hiện một quyết định cần tập hàng ổn định, chỉ khóa hai hàng `1001` và `1003` không nhất thiết ngăn được một hàng khác xuất hiện hoặc biến mất.

Đây là lý do hệ thống kiểm soát tuần tự hóa phải quan tâm đến cả hàng đã đọc và phạm vi dữ liệu có thể thỏa điều kiện đọc.

## 2. Điều kiện đọc (read predicate) và tập đọc

Một giao dịch có thể thực hiện nhiều loại thao tác đọc. Có thể mô hình hóa thông tin đọc bằng hai thành phần:

- **Tập hàng đọc** (*row read set*): các hàng hoặc phiên bản cụ thể mà giao dịch đã đọc.
- **Điều kiện đọc** (*read predicate*): điều kiện xác định tập hàng mà truy vấn quan tâm, kể cả những hàng hiện chưa tồn tại hoặc hiện chưa thỏa điều kiện.

Ví dụ, với truy vấn:

```sql
SELECT order_id, amount
FROM orders
WHERE customer_id = 42
  AND status = 'PENDING'
  AND amount BETWEEN 100 AND 500;
```

Tập hàng đọc có thể là `{1001, 1003}`. Điều kiện đọc tương ứng có thể được mô tả là:

```text
orders.customer_id = 42
AND orders.status = 'PENDING'
AND 100 <= orders.amount <= 500
```

Điều kiện này mô tả cả những hàng chưa có trong kết quả. Nếu giao dịch khác chèn một đơn hàng của khách hàng `42` với trạng thái `PENDING` và số tiền `250`, hàng mới sẽ thỏa điều kiện dù không nằm trong tập hàng mà `T1` đã đọc lúc đầu.

Trong hệ quản trị thực tế, việc biểu diễn điều kiện có thể dựa trên chỉ mục, khoảng khóa, trang dữ liệu, biểu thức truy vấn hoặc một cấu trúc nội bộ khác. Không nhất thiết hệ thống lưu nguyên văn câu SQL như một chuỗi để so sánh. Điều quan trọng là nó có đủ thông tin để nhận biết một thao tác ghi có thể ảnh hưởng đến kết quả đọc trước đó.

## 3. Tập ghi và giao điểm với điều kiện đọc

Để phát hiện xung đột, hệ thống cũng cần xem xét các thao tác ghi. Một cách mô hình hóa là tập ghi (*write set*) gồm các mục dữ liệu được giao dịch chèn, cập nhật hoặc xóa.

Một thao tác ghi có thể ảnh hưởng đến điều kiện đọc theo nhiều cách:

| Thao tác ghi | Ảnh hưởng đến điều kiện đọc |
|---|---|
| `INSERT` một hàng mới | Hàng mới có thể thỏa điều kiện và xuất hiện trong kết quả |
| `DELETE` một hàng | Hàng đang thỏa điều kiện có thể biến mất khỏi kết quả |
| `UPDATE` cột được dùng trong điều kiện | Hàng có thể chuyển từ không thỏa sang thỏa, hoặc ngược lại |
| `UPDATE` cột được truy vấn trả về | Tập hàng có thể giữ nguyên nhưng giá trị mà giao dịch đọc dựa vào có thể thay đổi |
| `UPDATE` cột không liên quan | Có thể không ảnh hưởng đến điều kiện hay giá trị đọc; cần xét phụ thuộc thực tế |

Ví dụ, với điều kiện `status = 'PENDING'`, cập nhật một hàng từ `CANCELLED` sang `PENDING` làm hàng đó đi vào tập kết quả. Cập nhật từ `PENDING` sang `CANCELLED` làm hàng rời khỏi tập. Cả hai đều có thể xung đột với giao dịch đang dựa vào kết quả truy vấn đó.

Hệ thống cần phân biệt thao tác ghi thật sự ảnh hưởng đến điều kiện hoặc dữ liệu đọc với thao tác ghi không liên quan. Nếu đánh dấu một phạm vi quá rộng, hệ thống có thể phát hiện xung đột giả (*false positive*) và hủy giao dịch dù lịch thực thi vẫn có thể tuần tự hóa.

## 4. Ví dụ về phantom và thay đổi thành viên của tập kết quả

Giả sử `T1` đếm các đơn hàng đang chờ xử lý có giá trị từ 100 trở lên:

```sql
BEGIN;

SELECT COUNT(*)
FROM orders
WHERE status = 'PENDING'
  AND amount >= 100;

-- T1 tiếp tục công việc dựa trên số lượng vừa đọc.
```

Trong khi `T1` chưa kết thúc, `T2` chèn một hàng:

```sql
BEGIN;

INSERT INTO orders (order_id, status, amount)
VALUES (2001, 'PENDING', 150);

COMMIT;
```

Nếu lần đọc của `T1` dùng ảnh chụp cũ, nó có thể không nhìn thấy hàng `2001`. Nhưng hàng mới vẫn có thể làm thay đổi kết quả của một lần đọc tiếp theo hoặc làm sai một quyết định nghiệp vụ nếu các giao dịch được phép commit theo một thứ tự không hợp lệ.

Một bộ theo dõi chỉ biết `T1` đã đọc những khóa chính nào sẽ không tự động nhận ra hàng `2001`, vì hàng đó chưa tồn tại trong kết quả ban đầu. Bộ theo dõi điều kiện đọc ghi nhận rằng `T1` đã quan tâm đến phạm vi `status = 'PENDING' AND amount >= 100`; thao tác `INSERT` của `T2` có thể được nhận diện là ảnh hưởng đến phạm vi đó.

Đây là bản chất của việc theo dõi predicate: hệ thống theo dõi cả **những hàng đã đọc** và **những hàng có thể xuất hiện nếu dữ liệu thay đổi**.

## 5. Bảo vệ điều kiện đọc bằng khóa phạm vi và khóa vị từ

Một cách ngăn giao dịch khác thay đổi tập kết quả là khóa phạm vi mà truy vấn đọc quan tâm.

### 5.1. Khóa phạm vi (range lock)

Khóa phạm vi bảo vệ một khoảng khóa, thường dựa trên thứ tự của chỉ mục. Ví dụ, nếu truy vấn tìm các đơn hàng có `amount` từ 100 đến 500, hệ quản trị có thể khóa khoảng khóa tương ứng để ngăn giao dịch khác chèn một khóa mới vào khoảng đó hoặc cập nhật một hàng đi vào phạm vi đang được bảo vệ.

Khóa phạm vi có thể ngăn phantom trong phạm vi đã khóa. Phạm vi thực tế phụ thuộc vào chỉ mục, thứ tự khóa, điều kiện truy vấn và cách hệ quản trị triển khai. Một truy vấn không có chỉ mục phù hợp có thể phải khóa một vùng dữ liệu rộng hơn, làm giảm khả năng đồng thời.

### 5.2. Khóa vị từ (predicate lock)

Khóa vị từ là cách biểu diễn trực tiếp hơn ý tưởng bảo vệ một điều kiện logic, chẳng hạn:

```text
customer_id = 42
AND status = 'PENDING'
AND amount >= 100
```

Một thao tác ghi có thể bị xem là xung đột nếu nó làm một hàng bắt đầu hoặc ngừng thỏa vị từ đang được bảo vệ. Khóa vị từ là khái niệm về phạm vi điều kiện; cách triển khai có thể dùng khóa khoảng, khóa chỉ mục, khóa trang hoặc cấu trúc theo dõi xung đột khác.

Không phải mọi khóa vị từ đều chặn thao tác ghi ngay lập tức. Trong một số cơ chế, thông tin đọc được ghi nhận để phát hiện quan hệ phụ thuộc và quyết định hủy một giao dịch khi cần thiết. Vì vậy, cần phân biệt **khóa dùng để chặn** với **dấu vết đọc dùng để phát hiện xung đột**.

### 5.3. Khóa hàng hiện có không bảo vệ toàn bộ điều kiện

Nếu truy vấn trả về hai hàng, khóa độc quyền hoặc chia sẻ trên đúng hai hàng đó chưa chắc ngăn được một hàng thứ ba được chèn vào phạm vi. Muốn bảo vệ điều kiện, hệ thống phải có cơ chế ngăn hoặc theo dõi những thao tác ghi có khả năng làm thay đổi thành viên của tập kết quả.

Đây là điểm khác biệt giữa khóa từng hàng và bảo vệ phạm vi truy vấn. Chọn cơ chế nào cần dựa vào mức cô lập, loại truy vấn và khả năng của hệ quản trị.

## 6. Theo dõi phụ thuộc đọc-ghi để kiểm soát tuần tự hóa

Không phải hệ thống nào cũng chặn giao dịch ghi bằng khóa phạm vi. Một hướng tiếp cận khác là theo dõi quan hệ phụ thuộc giữa các giao dịch.

Giả sử `T1` đọc một phiên bản hoặc một điều kiện đọc, sau đó `T2` ghi một giá trị mới làm thay đổi dữ liệu mà `T1` đã đọc. Nếu thay đổi của `T2` không được nhìn thấy bởi ảnh chụp của `T1`, quan hệ này có thể được mô hình hóa là một **phụ thuộc đọc-ghi** (*read-write dependency*), thường ký hiệu `T1 →rw T2`.

Hướng mũi tên thể hiện thứ tự tuần tự cần có để giữ nguyên quan hệ đọc: `T1` phải được xem là xảy ra trước `T2`, vì `T1` đã đọc trạng thái cũ trước khi `T2` ghi trạng thái mới. Nếu các phụ thuộc đọc-ghi kết hợp với nhau tạo thành chu trình trong đồ thị tuần tự hóa, lịch thực thi không thể tương đương với một thứ tự tuần tự hợp lệ.

Với truy vấn theo điều kiện, phụ thuộc có thể xuất hiện dù hàng mới không có trong kết quả ban đầu. Ví dụ, `T1` đọc vị từ `status = 'PENDING'`; `T2` chèn một hàng mới thỏa điều kiện và commit. Bộ theo dõi predicate có thể ghi nhận `T1 →rw T2` vì thao tác ghi của `T2` ảnh hưởng đến điều kiện mà `T1` đã đọc.

## 7. Ví dụ write skew và lý do cần theo dõi điều kiện đọc

Giả sử có hai bác sĩ đang trực. Quy tắc nghiệp vụ yêu cầu luôn có ít nhất một bác sĩ trực. Bảng `doctors` có hai hàng:

| doctor_id | on_call |
|---|---|
| A | TRUE |
| B | TRUE |

Hai giao dịch đồng thời chạy dưới một cơ chế snapshot isolation:

**T1:**

```sql
BEGIN;

SELECT COUNT(*)
FROM doctors
WHERE on_call = TRUE;

-- Thấy 2 bác sĩ đang trực.
UPDATE doctors
SET on_call = FALSE
WHERE doctor_id = 'A';

COMMIT;
```

**T2:**

```sql
BEGIN;

SELECT COUNT(*)
FROM doctors
WHERE on_call = TRUE;

-- Cũng thấy 2 bác sĩ đang trực trong snapshot của T2.
UPDATE doctors
SET on_call = FALSE
WHERE doctor_id = 'B';

COMMIT;
```

Hai giao dịch ghi vào hai hàng khác nhau nên một cơ chế chỉ phát hiện xung đột ghi trên cùng hàng có thể không nhận ra vấn đề. Tuy nhiên, cả hai đều đọc điều kiện `on_call = TRUE`. Ghi của `T1` làm thay đổi tập hàng thỏa điều kiện mà `T2` đã đọc; ghi của `T2` cũng làm thay đổi tập hàng mà `T1` đã đọc.

Có thể biểu diễn hai phụ thuộc:

```text
T1 ──rw──► T2
 ▲         │
 └──rw─────┘

Chu trình phụ thuộc: không có thứ tự tuần tự nào giữ được cả hai lần đọc
và cả hai lần ghi như lịch thực thi đã xảy ra.
```

Nếu cả hai cùng commit, kết quả là không còn bác sĩ nào trực. Một cơ chế kiểm soát serializable phải ngăn lịch này, chẳng hạn bằng cách khóa điều kiện phù hợp hoặc phát hiện cấu trúc phụ thuộc nguy hiểm và hủy một giao dịch.

Ví dụ cho thấy tại sao theo dõi hàng đã ghi và xung đột ghi trực tiếp là chưa đủ. Hệ thống còn phải biết mỗi giao dịch đã đọc điều kiện nào để phát hiện việc một giao dịch khác làm thay đổi tập dữ liệu mà nó dựa vào.

## 8. Kiểm tra tuần tự hóa lạc quan và SSI

Các thuật toán kiểm soát đồng thời có thể theo dõi điều kiện đọc theo những cách khác nhau.

### 8.1. Kiểm tra khi commit trong điều khiển lạc quan

Trong một thiết kế điều khiển lạc quan (*optimistic concurrency control*), giao dịch có thể thực hiện công việc trên một ảnh chụp mà không giữ khóa chặn trong toàn bộ thời gian đọc. Trước khi commit, hệ thống kiểm tra xem các giao dịch khác có ghi vào dữ liệu mà giao dịch này đã đọc hoặc vào phạm vi predicate mà nó phụ thuộc hay không.

Nếu có xung đột làm kết quả không thể tuần tự hóa, hệ thống từ chối commit hoặc hủy giao dịch để ứng dụng thử lại. Cách kiểm tra cụ thể phụ thuộc thuật toán: có hệ thống kiểm tra tập đọc/tập ghi, có hệ thống theo dõi các quan hệ phụ thuộc trong quá trình chạy.

### 8.2. Serializable Snapshot Isolation (SSI)

SSI là một cách thực hiện mức cô lập serializable trên nền snapshot isolation. Thay vì khóa chặn mọi phạm vi đọc như một số cách tiếp cận 2PL, SSI theo dõi các phụ thuộc đọc-ghi có thể dẫn đến chu trình tuần tự hóa.

Một điều kiện đọc có thể được ghi nhận bằng dấu vết đọc hoặc cơ chế tương tự. Khi giao dịch khác ghi vào phạm vi đó, hệ thống ghi nhận phụ thuộc. Nếu xuất hiện cấu trúc phụ thuộc nguy hiểm có thể dẫn đến lịch không tuần tự hóa được, hệ thống có thể hủy một giao dịch để phá vỡ cấu trúc.

SSI không có nghĩa mọi giao dịch xung đột đều bị chặn ngay lúc truy vấn. Một số xung đột được phát hiện trong quá trình thực thi hoặc khi commit; ứng dụng cần sẵn sàng xử lý lỗi serialization bằng cách thử lại toàn bộ giao dịch theo quy tắc an toàn.

Một số hệ quản trị dùng dấu vết đọc như `SIRead` để theo dõi phạm vi đọc trong SSI. Những dấu vết này phục vụ phát hiện phụ thuộc; chúng không nhất thiết là khóa chặn thông thường khiến thao tác ghi phải chờ. Cách đặt tên, phạm vi và thời điểm giải phóng dấu vết là chi tiết triển khai của hệ quản trị.

## 9. Độ chính xác của phạm vi theo dõi và xung đột giả

Theo dõi một điều kiện đọc chính xác có thể tốn kém. Một truy vấn có thể lọc trên nhiều cột, phép nối, biểu thức hoặc điều kiện phức tạp. Hệ thống có thể dùng một phạm vi gần đúng để giảm chi phí lưu dấu vết.

Ví dụ, truy vấn chỉ quan tâm `customer_id = 42`, nhưng hệ thống chỉ có thể bảo vệ toàn bộ một trang chỉ mục chứa cả khách hàng `42`, `43` và `44`. Một giao dịch ghi hàng của khách hàng `43` có thể bị xem là xung đột dù không ảnh hưởng đến kết quả truy vấn của `T1`.

Đây là xung đột giả (*false positive*): hệ thống bảo thủ đánh dấu một phụ thuộc có thể xảy ra, dù không có xung đột logic thực sự. Xung đột giả có thể làm giao dịch phải chờ hoặc bị hủy, giảm mức đồng thời nhưng vẫn bảo đảm tính đúng đắn.

Một số yếu tố ảnh hưởng đến độ chính xác và chi phí theo dõi:

- Chỉ mục có hỗ trợ ánh xạ điều kiện truy vấn thành khoảng khóa rõ ràng hay không.
- Phạm vi khóa là một hàng, một khóa chỉ mục, một khoảng, một trang hay toàn bảng.
- Truy vấn có dùng biểu thức, phép nối hoặc điều kiện không thể ánh xạ gọn vào chỉ mục hay không.
- Hệ thống có thể nâng cấp dấu vết từ phạm vi nhỏ lên phạm vi lớn khi số lượng dấu vết tăng hay không.
- Giao dịch tồn tại lâu đến mức nào và cần giữ thông tin phụ thuộc trong bao lâu.

Không nên cố loại bỏ mọi xung đột giả bằng cách thu hẹp phạm vi bằng mọi giá. Mục tiêu là cân bằng giữa chi phí theo dõi, mức đồng thời và khả năng bảo đảm serializable.

## 10. Lựa chọn cơ chế theo yêu cầu nghiệp vụ

| Yêu cầu | Cơ chế có thể phù hợp | Điều cần cân nhắc |
|---|---|---|
| Ngăn giao dịch khác chèn hàng vào một khoảng khóa | Khóa phạm vi hoặc khóa khoảng chỉ mục | Phụ thuộc chỉ mục và phạm vi khóa của hệ quản trị |
| Bảo vệ một điều kiện logic trên nhiều hàng | Khóa vị từ hoặc cơ chế theo dõi predicate | Predicate có thể phức tạp và phạm vi theo dõi có thể rộng |
| Cho phép đọc snapshot rồi phát hiện xung đột khi commit | Kiểm tra lạc quan hoặc SSI | Có thể hủy giao dịch; ứng dụng phải retry an toàn |
| Bảo vệ quy tắc nghiệp vụ biểu diễn được bằng ràng buộc | `UNIQUE`, `CHECK`, khóa ngoại hoặc mô hình dữ liệu phù hợp | Ràng buộc chỉ bảo vệ quy tắc mà nó thực sự biểu diễn |
| Đơn giản hóa điều phối qua một tài nguyên chung | Khóa hàng điều phối hoặc hàng cha | Mọi luồng ghi liên quan phải tuân theo cùng quy ước khóa |

Không có một lựa chọn duy nhất phù hợp cho mọi truy vấn. Hãy xác định bất biến nghiệp vụ trước, sau đó chọn cơ chế bảo vệ điều kiện đọc và tập dữ liệu mà bất biến đó phụ thuộc.

## 11. Cách điều tra xung đột predicate trong thực tế

Khi giao dịch bị hủy do serialization hoặc xuất hiện kết quả nghiệp vụ không nhất quán, hãy lần theo cả truy vấn đọc và các thao tác ghi liên quan:

1. Ghi lại câu truy vấn, điều kiện lọc, tham số và tập khóa chính mà truy vấn trả về.
2. Xác định các hàng chưa xuất hiện nhưng có thể thỏa điều kiện nếu được chèn hoặc cập nhật.
3. Tìm các giao dịch đồng thời đã `INSERT`, `DELETE` hoặc `UPDATE` hàng trong phạm vi đó.
4. Kiểm tra thời điểm commit và xác định giao dịch đọc có nhìn thấy phiên bản mới hay không.
5. Xem xét phụ thuộc đọc-ghi giữa các giao dịch và liệu chúng có tạo thành chu trình hoặc cấu trúc nguy hiểm hay không.
6. Xác định hệ quản trị đang dùng khóa phạm vi, khóa vị từ, kiểm tra khi commit hay SSI.
7. Nếu giao dịch bị hủy, kiểm tra mã lỗi serialization/deadlock và bảo đảm ứng dụng thử lại toàn bộ đơn vị giao dịch khi phù hợp.

Một truy vấn trả về cùng số lượng hàng ở hai lần đọc không chứng minh rằng không có xung đột predicate. Hàng có thể biến mất đồng thời với một hàng khác xuất hiện, khiến số lượng giữ nguyên nhưng tập khóa chính đã thay đổi. Vì vậy, khi điều tra, nên so sánh cả danh sách khóa chính hoặc các thuộc tính liên quan, không chỉ so sánh `COUNT(*)`.

## 12. Ghi nhớ

- Tập hàng đọc mô tả những hàng đã được truy vấn trả về; điều kiện đọc mô tả cả những hàng có thể thỏa truy vấn trong tương lai.
- `INSERT`, `DELETE` và `UPDATE` đều có thể làm thay đổi thành viên của tập hàng thỏa điều kiện.
- Theo dõi predicate giúp phát hiện phantom và phụ thuộc đọc-ghi mà việc chỉ theo dõi các hàng đã đọc có thể bỏ sót.
- Khóa phạm vi/khóa vị từ có thể bảo vệ điều kiện bằng cách chặn hoặc ghi nhận thao tác ghi ảnh hưởng đến phạm vi.
- SSI và các cách kiểm tra lạc quan theo dõi phụ thuộc rồi có thể hủy giao dịch khi lịch chạy có nguy cơ không tuần tự hóa được.
- Snapshot isolation không tự động ngăn write skew; cần bảo vệ điều kiện đọc và bất biến nghiệp vụ ở mức serializable hoặc bằng cơ chế tương đương.
- Phạm vi theo dõi rộng có thể tạo xung đột giả, làm giảm mức đồng thời nhưng vẫn giữ an toàn.

Khi phân tích một giao dịch, hãy hỏi: **Ngoài những hàng đã đọc, giao dịch còn dựa vào điều kiện nào để xác định tập kết quả, và giao dịch khác có thể ghi để làm thay đổi điều kiện hoặc thành viên của tập đó hay không?**

# Vì sao khóa hàng không tự bảo vệ mọi điều kiện trên tập dữ liệu

Khóa hàng (*row lock*) giúp điều phối các giao dịch đang đọc hoặc cập nhật **những hàng đã tồn tại**. Tuy nhiên, nhiều quy tắc nghiệp vụ được diễn đạt bằng điều kiện trên cả một tập dữ liệu, chẳng hạn “không có đơn hàng đang chờ nào vượt giới hạn”, “số chỗ đã đặt phải nhỏ hơn sức chứa” hoặc “không tồn tại hai bản ghi trùng khoảng thời gian”. Một truy vấn có thể trả về một tập hàng theo điều kiện, nhưng khóa từng hàng trong tập kết quả không nhất thiết bảo vệ được toàn bộ điều kiện đó.

Lý do là khóa hàng thường gắn với các hàng cụ thể mà truy vấn tìm thấy tại thời điểm thực hiện. Điều kiện truy vấn còn có thể bị ảnh hưởng bởi một hàng chưa tồn tại, một hàng hiện chưa thỏa điều kiện hoặc một hàng khác được cập nhật để bắt đầu thỏa điều kiện. Nếu các hàng đó không thuộc phạm vi khóa, giao dịch khác vẫn có thể làm thay đổi tập kết quả.

Để bảo vệ một điều kiện trên tập dữ liệu, hệ thống cần một cơ chế bảo vệ **phạm vi hoặc vị từ truy vấn** (*range/predicate*), một điểm khóa điều phối chung, một ràng buộc dữ liệu phù hợp hoặc mức cô lập đủ mạnh. Chỉ nhìn thấy `SELECT ... FOR UPDATE` trong câu lệnh chưa đủ để kết luận toàn bộ điều kiện nghiệp vụ đã được bảo vệ.

## 1. Khóa hàng bảo vệ điều gì?

Giả sử bảng `orders` chứa các đơn hàng. Giao dịch chạy truy vấn:

```sql
SELECT order_id, amount
FROM orders
WHERE status = 'PENDING'
  AND amount >= 100
FOR UPDATE;
```

Trong các hệ quản trị hỗ trợ cú pháp này, `FOR UPDATE` thường yêu cầu khóa ghi trên những hàng hiện có được truy vấn trả về. Giao dịch khác muốn cập nhật hoặc khóa xung đột trên chính những hàng đó có thể phải chờ cho đến khi khóa được giải phóng.

Nhưng câu truy vấn gồm hai thành phần khác nhau:

- **Các hàng hiện có trong kết quả:** ví dụ các đơn hàng 1001, 1003 và 1005.
- **Điều kiện xác định kết quả:** `status = 'PENDING' AND amount >= 100`.

Khóa các hàng 1001, 1003 và 1005 bảo vệ những hàng đó theo chế độ khóa được cấp. Điều đó không tự động có nghĩa là giao dịch đã khóa mọi giá trị có thể thỏa điều kiện trong tương lai. Một đơn hàng mới có thể được chèn vào; một đơn hàng đang ở trạng thái `DRAFT` có thể được cập nhật thành `PENDING`; hoặc một đơn hàng có `amount = 80` có thể được cập nhật thành `amount = 150`.

Nếu những thay đổi này không xung đột với các khóa đang giữ, chúng có thể được commit. Lần truy vấn tiếp theo sẽ thấy một tập kết quả khác. Đây là cơ sở của hiện tượng đọc ma (*phantom read*) trong các mức cô lập cho phép hiện tượng đó.

## 2. Ví dụ: hàng mới xuất hiện sau khi đã khóa các hàng phù hợp

Giả sử giao dịch `T1` cần xem các đơn hàng đang chờ xử lý có giá trị từ 100 trở lên. Tại thời điểm đầu, chỉ có ba đơn hàng thỏa điều kiện. `T1` khóa ba hàng đó. Trong lúc `T1` vẫn mở, `T2` chèn một đơn hàng mới thỏa cùng điều kiện rồi commit.

| Thời điểm | Giao dịch T1 | Giao dịch T2 | Tập hàng phù hợp |
|---|---|---|---|
| 1 | Bắt đầu và truy vấn điều kiện | | 1001, 1003, 1005 |
| 2 | Khóa các hàng đã tìm thấy bằng `FOR UPDATE` | | 1001, 1003, 1005 đang bị khóa bởi T1 |
| 3 | Vẫn giữ các khóa trên | Bắt đầu giao dịch | |
| 4 | Vẫn giữ các khóa trên | Chèn đơn hàng 1008, `PENDING`, số tiền 150 | Hàng 1008 chưa tồn tại khi T1 truy vấn lần đầu |
| 5 | Vẫn giữ các khóa trên | `COMMIT` | Tập dữ liệu đã commit có thêm 1008 |
| 6 | Chạy lại truy vấn theo cùng điều kiện | Đã kết thúc | 1001, 1003, 1005, 1008 |

`T1` vẫn giữ khóa trên ba hàng ban đầu, nhưng hàng 1008 không thuộc tập hàng đã tồn tại khi `T1` lấy khóa. Nếu cơ chế khóa của hệ quản trị không bảo vệ khoảng hoặc điều kiện truy vấn, `T2` có thể chèn hàng mới mà không phải chờ các khóa hàng đó.

### Minh họa hai phiên với PostgreSQL ở READ COMMITTED

Ví dụ dưới đây dùng hành vi khóa hàng của PostgreSQL ở mức `READ COMMITTED`. Cú pháp và phạm vi khóa khác nhau giữa các hệ quản trị; không nên xem ví dụ này là quy tắc chung cho mọi cơ sở dữ liệu.

**Phiên A — đọc và khóa những hàng đang tồn tại:**

```sql
BEGIN;

SELECT order_id, amount
FROM orders
WHERE status = 'PENDING'
  AND amount >= 100
FOR UPDATE;

-- Tạm dừng, để phiên B chèn và commit một đơn hàng mới.

-- Chạy lại cùng truy vấn trong giao dịch T1.
SELECT order_id, amount
FROM orders
WHERE status = 'PENDING'
  AND amount >= 100
FOR UPDATE;

COMMIT;
```

**Phiên B — chèn hàng mới:**

```sql
BEGIN;

INSERT INTO orders (order_id, amount, status)
VALUES (1008, 150, 'PENDING');

COMMIT;
```

Thực hiện lần truy vấn đầu ở phiên A, sau đó chạy giao dịch ở phiên B và commit. Cuối cùng chạy lần truy vấn thứ hai ở phiên A. Với PostgreSQL `READ COMMITTED`, mỗi câu lệnh đọc có ảnh chụp dữ liệu mới tại thời điểm câu lệnh bắt đầu. `FOR UPDATE` khóa các hàng được trả về; nó không tự tạo khóa khoảng để ngăn một hàng mới được chèn vào điều kiện. Vì vậy, lần đọc thứ hai có thể thấy đơn hàng 1008.

## 3. Trường hợp không có hàng nào phù hợp còn dễ bị bỏ sót hơn

Giả sử hệ thống kiểm tra xem có bản ghi đặt chỗ nào cho ghế `A-12` hay chưa:

```sql
SELECT booking_id
FROM bookings
WHERE event_id = 7
  AND seat_code = 'A-12'
FOR UPDATE;
```

Nếu chưa có bản ghi nào phù hợp, truy vấn trả về tập rỗng. Trong cách khóa hàng thông thường, không có hàng kết quả để khóa. Hai giao dịch có thể cùng chạy truy vấn, cùng nhận tập rỗng rồi mỗi giao dịch chèn một bản ghi đặt chỗ cho cùng ghế.

Trình tự có thể xảy ra nếu không có ràng buộc hoặc khóa phạm vi thích hợp:

```text
T1: SELECT ... WHERE seat_code = 'A-12' FOR UPDATE  -> 0 hàng
T2: SELECT ... WHERE seat_code = 'A-12' FOR UPDATE  -> 0 hàng
T1: INSERT booking cho A-12
T2: INSERT booking cho A-12
T1: COMMIT
T2: COMMIT
```

Một khóa hàng không thể khóa một hàng chưa tồn tại. Đây là lý do đặc biệt quan trọng khi quy trình có dạng **kiểm tra không tồn tại rồi mới chèn** (*check-then-insert*). Nếu nghiệp vụ yêu cầu duy nhất, cần bảo vệ điều kiện bằng cơ chế có thể xử lý cả trường hợp chưa có hàng.

Ví dụ, có thể tạo ràng buộc duy nhất trên `(event_id, seat_code)`:

```sql
ALTER TABLE bookings
ADD CONSTRAINT uq_booking_event_seat
UNIQUE (event_id, seat_code);
```

Khi hai giao dịch cùng chèn một ghế cho cùng sự kiện, ràng buộc duy nhất khiến tối đa một thao tác thành công. Giao dịch còn lại phải xử lý lỗi trùng khóa hoặc kết quả xung đột theo hệ quản trị. Tên kiểu dữ liệu, cú pháp và cách xử lý lỗi có thể cần điều chỉnh theo hệ quản trị đang dùng.

## 4. Một hàng chưa phù hợp có thể được cập nhật để đi vào tập kết quả

Phantom không nhất thiết đến từ `INSERT`. Một hàng có thể đã tồn tại nhưng chưa thỏa điều kiện nên không được truy vấn trả về và không được khóa bởi câu truy vấn đó.

Ví dụ, `T1` khóa các đơn hàng `PENDING`:

```sql
SELECT order_id
FROM orders
WHERE status = 'PENDING'
FOR UPDATE;
```

Trong khi đó, `T2` cập nhật một đơn hàng `DRAFT` thành `PENDING`:

```sql
UPDATE orders
SET status = 'PENDING'
WHERE order_id = 2001;
```

Nếu hàng 2001 không nằm trong tập kết quả ban đầu của `T1`, khóa hàng của `T1` không nhất thiết xung đột với cập nhật ở `T2`. Sau khi `T2` commit, truy vấn lại ở `T1` có thể nhận thêm hàng 2001. Tình huống tương tự xảy ra khi một giá trị được cập nhật để bắt đầu thỏa điều kiện số, ngày tháng, trạng thái hoặc khoảng thời gian.

Chiều ngược lại cũng đúng: một hàng có thể bị xóa hoặc cập nhật để không còn thỏa điều kiện, khiến nó biến mất khỏi tập kết quả của lần đọc sau. Khi phân tích, cần xét tất cả thao tác có thể làm thay đổi điều kiện lọc, không chỉ thao tác chèn hàng mới.

## 5. Vì sao 2PL với khóa hàng vẫn có thể chưa đủ?

Giao thức khóa hai pha (*Two-Phase Locking — 2PL*) quy định một giao dịch có giai đoạn tăng trưởng để lấy khóa và giai đoạn thu hẹp để nhả khóa. Sau khi nhả khóa đầu tiên, giao dịch không được lấy khóa mới. Với mô hình dữ liệu và tập khóa được bảo vệ đầy đủ, lịch tuân thủ 2PL có thể tuần tự hóa theo xung đột.

Tuy nhiên, 2PL chỉ điều phối các khóa mà hệ thống thực sự lấy. Nếu một giao dịch đọc điều kiện trên tập hàng nhưng chỉ lấy khóa trên các hàng hiện có, thao tác chèn một hàng mới có thể không xung đột với khóa nào mà giao dịch đọc đang giữ. Khi đó, điều kiện truy vấn chưa được biểu diễn thành một tài nguyên khóa được bảo vệ.

Nói cách khác, **tuân thủ quy tắc hai pha không tự động đồng nghĩa với việc đã khóa đúng phạm vi dữ liệu mà nghiệp vụ phụ thuộc vào**. Cần xác định đơn vị logic cần bảo vệ:

- Nếu nghiệp vụ phụ thuộc vào một hàng đã biết, khóa hàng có thể phù hợp.
- Nếu nghiệp vụ phụ thuộc vào mọi hàng có khóa nằm trong một khoảng, cần xem xét khóa phạm vi.
- Nếu nghiệp vụ phụ thuộc vào mọi hàng thỏa một biểu thức lọc, cần xem xét khóa vị từ hoặc cơ chế cô lập bảo vệ điều kiện đó.
- Nếu nghiệp vụ phụ thuộc vào một giới hạn tổng hợp, có thể dùng một hàng điều phối hoặc cập nhật nguyên tử một bộ đếm được bảo vệ.

## 6. Phân biệt khóa hàng, khóa phạm vi và khóa vị từ

Các hệ quản trị có thể dùng nhiều mức hạt khóa khác nhau. Ba khái niệm dưới đây giúp phân biệt phạm vi được bảo vệ.

| Cơ chế | Phạm vi được bảo vệ | Ví dụ tác động |
|---|---|---|
| **Khóa hàng (row lock)** | Một hàng cụ thể đang tồn tại | Ngăn thao tác xung đột trên hàng đó trong thời gian khóa còn hiệu lực |
| **Khóa phạm vi (range lock)** | Một khoảng khóa hoặc khoảng giá trị trong chỉ mục | Có thể ngăn chèn hoặc thay đổi khóa chỉ mục vào khoảng đang được bảo vệ |
| **Khóa vị từ (predicate lock)** | Tập dữ liệu được xác định bởi một điều kiện logic | Bảo vệ việc đọc theo điều kiện, kể cả thay đổi có thể làm hàng bắt đầu thỏa điều kiện |

Khóa phạm vi thường gắn với thứ tự khóa trong chỉ mục. Khóa vị từ mô tả điều kiện logic của truy vấn. Một số hệ quản trị hiện thực hóa bảo vệ điều kiện bằng khóa khoảng; một số hệ thống dùng cơ chế theo dõi xung đột đọc/ghi và có thể hủy giao dịch để bảo đảm tuần tự hóa.

Không nên suy luận rằng việc tạo chỉ mục trên cột lọc tự động tạo khóa phạm vi. Chỉ mục có thể giúp hệ quản trị xác định phạm vi cần khóa, nhưng việc khóa có được áp dụng hay không còn phụ thuộc mức cô lập, loại câu lệnh, kế hoạch truy vấn và cách triển khai của hệ quản trị.

## 7. Hành vi phụ thuộc hệ quản trị và mức cô lập

Tên cú pháp giống nhau không bảo đảm phạm vi khóa giống nhau. Một số khác biệt thường gặp:

| Hệ quản trị / chế độ | Hành vi liên quan |
|---|---|
| **PostgreSQL — `READ COMMITTED`** | `SELECT ... FOR UPDATE` khóa các hàng được truy vấn trả về. Nó không khóa khoảng để ngăn chèn hàng mới thỏa điều kiện. Câu lệnh tiếp theo có thể nhìn thấy hàng đã commit sau câu lệnh trước. |
| **PostgreSQL — `SERIALIZABLE`** | Dùng Serializable Snapshot Isolation (SSI) để theo dõi các phụ thuộc đọc/ghi có thể tạo lịch không tuần tự hóa. Hệ thống có thể hủy một giao dịch với lỗi serialization để ứng dụng thử lại. Cơ chế này không đơn giản là khóa mọi hàng tương lai và có thể phát hiện xung đột thay vì bắt giao dịch chèn phải chờ. |
| **MySQL InnoDB — locking read ở `REPEATABLE READ`** | Có thể dùng khóa khoảng hoặc khóa next-key cho truy vấn phạm vi dựa trên chỉ mục, nhờ đó ngăn một số thao tác chèn vào khoảng đang được bảo vệ. Phạm vi thực tế phụ thuộc chỉ mục, điều kiện và kế hoạch truy vấn. |
| **MySQL InnoDB — `READ COMMITTED`** | Phần lớn khóa khoảng được tắt cho các thao tác tìm kiếm và quét chỉ mục thông thường, ngoại trừ một số trường hợp cần thiết như kiểm tra khóa ngoại hoặc khóa trùng. Vì vậy, không thể giả định cùng câu lệnh sẽ bảo vệ khoảng giống `REPEATABLE READ`. |
| **SQL Server — `SERIALIZABLE`** | Có thể dùng khóa phạm vi khóa chỉ mục để ngăn hàng mới được chèn vào khoảng mà truy vấn đã đọc. Cách khóa cụ thể phụ thuộc chỉ mục và kế hoạch thực thi. |

Các mô tả trên là định hướng để hiểu sự khác biệt, không thay thế tài liệu của đúng phiên bản và cấu hình đang triển khai. Với một truy vấn quan trọng, cần kiểm tra mức cô lập thực tế, loại storage engine, chỉ mục được dùng, kế hoạch thực thi và chế độ khóa mà hệ quản trị đã cấp.

## 8. Các cách bảo vệ điều kiện trên tập dữ liệu

Không có một giải pháp duy nhất cho mọi điều kiện. Hãy chọn cơ chế theo bất biến nghiệp vụ cần duy trì.

### 8.1. Dùng `SERIALIZABLE` khi cần bảo đảm thứ tự tuần tự

`SERIALIZABLE` yêu cầu kết quả của các giao dịch đồng thời tương đương với một thứ tự chạy tuần tự hợp lệ. Tùy hệ quản trị, nó có thể dùng khóa phạm vi, khóa vị từ, theo dõi phụ thuộc hoặc kết hợp nhiều cơ chế.

Một giao dịch có thể phải chờ hoặc bị hủy do xung đột tuần tự hóa. Ứng dụng cần nhận diện lỗi có thể retry, giới hạn số lần thử và bảo đảm thao tác thử lại an toàn. Không nên coi việc nâng mức cô lập là miễn phí: mức này có thể làm giảm thông lượng hoặc tăng số lần retry.

### 8.2. Dùng khóa phạm vi hoặc khóa vị từ khi hệ quản trị hỗ trợ

Nếu nghiệp vụ cần giữ ổn định khoảng giá trị hoặc tập hàng theo điều kiện, hãy dùng cơ chế khóa phạm vi/vị từ phù hợp với hệ quản trị. Ví dụ, truy vấn một khoảng mã đặt chỗ có thể cần bảo vệ cả các khóa chỉ mục chưa có hàng tại thời điểm đọc.

Hãy kiểm tra tài liệu về cú pháp locking read và mức cô lập. `FOR UPDATE` thường có nghĩa là khóa hàng được tìm thấy, nhưng ở một số hệ quản trị và mức cô lập, locking read trên một chỉ mục có thể lấy thêm khóa khoảng. Phạm vi khóa có thể thay đổi nếu truy vấn không dùng chỉ mục dự kiến hoặc kế hoạch truy vấn thay đổi.

### 8.3. Dùng hàng điều phối chung (guard row)

Khi nhiều giao dịch cùng thay đổi một tập dữ liệu có quy tắc chung, có thể tạo một hàng đại diện cho tài nguyên đó. Mọi giao dịch liên quan khóa cùng hàng đại diện trước khi kiểm tra và thay đổi các hàng con.

Ví dụ, bảng `events` có một hàng cho mỗi sự kiện. Quy trình đặt chỗ khóa hàng sự kiện trước khi đếm số chỗ đã đặt:

```sql
BEGIN;

SELECT event_id, capacity
FROM events
WHERE event_id = 7
FOR UPDATE;

SELECT COUNT(*)
FROM bookings
WHERE event_id = 7;

-- Ứng dụng kiểm tra số chỗ còn lại.
-- Nếu còn chỗ, chèn booking mới.

COMMIT;
```

Vì mọi giao dịch đặt chỗ đều khóa cùng hàng `events` trước khi đếm và chèn, chúng được điều phối qua một điểm khóa chung. Thiết kế này chỉ bảo vệ được quy tắc nếu **mọi đường ghi** có thể ảnh hưởng đến sức chứa đều tuân theo cùng giao thức. Một tác vụ quản trị hoặc dịch vụ khác chèn booking mà bỏ qua khóa hàng sự kiện có thể phá vỡ bảo đảm.

### 8.4. Biến điều kiện tổng hợp thành một cập nhật nguyên tử

Với giới hạn sức chứa, một cách khác là lưu số lượng đã sử dụng trên hàng tài nguyên và cập nhật có điều kiện trong một câu lệnh:

```sql
UPDATE events
SET reserved_count = reserved_count + 1
WHERE event_id = 7
  AND reserved_count < capacity;
```

Ứng dụng kiểm tra số hàng bị ảnh hưởng. Nếu một hàng được cập nhật, chỗ đã được giữ thành công; nếu không có hàng nào được cập nhật, sự kiện đã hết chỗ hoặc không tồn tại. Các giao dịch cùng cập nhật một hàng sẽ được cơ sở dữ liệu điều phối theo cơ chế ghi của nó.

Cách này yêu cầu `reserved_count` được duy trì nhất quán với các booking thực tế. Hủy booking, hoàn tiền, nhập dữ liệu và tác vụ sửa chữa đều phải cập nhật bộ đếm theo quy tắc đồng bộ. Có thể kết hợp khóa ngoại, ràng buộc `CHECK` và quy trình cập nhật trong cùng giao dịch để bảo vệ thêm bất biến.

### 8.5. Dùng ràng buộc dữ liệu để chặn trạng thái không hợp lệ

Các quy tắc như duy nhất một mã, không trùng ghế hoặc không trùng khóa có thể được biểu diễn bằng `UNIQUE`, khóa chính, khóa ngoại, `CHECK` hoặc ràng buộc loại trừ nếu hệ quản trị hỗ trợ.

Ràng buộc được kiểm tra ngay tại cơ sở dữ liệu, nên bảo vệ được quy tắc ngay cả khi nhiều ứng dụng cùng ghi. Đây thường là lựa chọn tốt cho bất biến có thể biểu diễn trực tiếp trong schema. Tuy nhiên, một ràng buộc duy nhất không thay thế được mọi quy tắc tổng hợp, chẳng hạn tổng số booking phải nhỏ hơn sức chứa, nếu schema không biểu diễn được điều kiện đó.

### 8.6. Dùng khóa bảng khi cần giải pháp thô nhưng rõ ràng

Một khóa ở mức bảng hoặc cơ chế khóa rộng hơn có thể chặn nhiều loại thay đổi đồng thời trên bảng. Cách này dễ hiểu về phạm vi bảo vệ nhưng thường làm giảm mức đồng thời mạnh, vì các giao dịch không liên quan cũng có thể phải chờ. Chỉ nên dùng khi phạm vi nghiệp vụ và tải hệ thống phù hợp, đồng thời phải kiểm tra chế độ khóa cụ thể của hệ quản trị.

## 9. Chọn giải pháp theo loại bất biến

| Yêu cầu nghiệp vụ | Cơ chế thường phù hợp | Điều cần xác nhận |
|---|---|---|
| Cập nhật một hàng đã biết | Khóa hàng `FOR UPDATE` hoặc cập nhật nguyên tử | Mọi thao tác ghi xung đột có thực sự bị chặn hoặc tuần tự hóa không? |
| Không cho trùng một khóa nghiệp vụ | `UNIQUE` hoặc khóa chính | Các cột tạo nên định danh duy nhất đã đầy đủ chưa? |
| Không có hàng nào trong một khoảng giá trị | Khóa phạm vi/vị từ hoặc `SERIALIZABLE` | Hệ quản trị có bảo vệ cả khoảng chưa có hàng không? |
| Giới hạn tổng số bản ghi hoặc sức chứa | Hàng điều phối, bộ đếm nguyên tử hoặc `SERIALIZABLE` | Mọi đường ghi có cập nhật cùng bộ đếm/điểm khóa không? |
| Báo cáo cần ảnh chụp nhất quán | Snapshot phù hợp hoặc `SERIALIZABLE` tùy yêu cầu | Cần ổn định dữ liệu đọc hay cần bảo đảm cả các giao dịch ghi tuần tự hóa? |

## 10. Cách điều tra khi khóa hàng vẫn xuất hiện phantom

Khi một giao dịch đã dùng `FOR UPDATE` nhưng truy vấn lần sau vẫn nhận thêm hoặc mất hàng, hãy lần theo các câu hỏi sau:

1. Câu truy vấn đầu đã trả về những khóa chính nào? Có trường hợp tập kết quả rỗng không?
2. Cơ chế thực tế đã khóa hàng, trang, bảng, khoảng chỉ mục hay vị từ nào?
3. Có giao dịch khác `INSERT` một hàng thỏa điều kiện hay không?
4. Có giao dịch khác cập nhật một hàng từ trạng thái không phù hợp sang trạng thái phù hợp, hoặc ngược lại, hay không?
5. Giao dịch ghi kia commit vào thời điểm nào so với hai lần đọc?
6. Mức cô lập thực tế là gì? Hệ quản trị dùng khóa hay snapshot/SSI để thực hiện mức đó?
7. Kế hoạch truy vấn có dùng đúng chỉ mục và phạm vi khóa mà thiết kế mong đợi không?
8. Mọi đường ghi liên quan có tuân thủ cùng giao thức khóa hoặc ràng buộc không?

Để quan sát chính xác, hãy xem execution plan, lock monitoring view hoặc công cụ chẩn đoán tương ứng của hệ quản trị. Tên view và cách diễn giải khác nhau giữa các sản phẩm. Không nên chỉ dựa vào tên câu lệnh để kết luận phạm vi khóa.

## 11. Ghi nhớ

- Khóa hàng thường bảo vệ hàng cụ thể đã tồn tại và được truy vấn tìm thấy.
- Điều kiện truy vấn mô tả một tập dữ liệu có thể thay đổi khi hàng mới được chèn, hàng cũ bị xóa hoặc hàng được cập nhật để đi vào/ra điều kiện.
- Nếu truy vấn không tìm thấy hàng nào, khóa hàng thông thường có thể không có hàng nào để giữ; đây là rủi ro lớn với quy trình kiểm tra rồi chèn.
- 2PL điều phối các khóa đã lấy. Nó không tự bảo vệ một điều kiện logic nếu giao dịch chưa lấy khóa cho đúng phạm vi dữ liệu.
- Khóa phạm vi, khóa vị từ, `SERIALIZABLE`, hàng điều phối và ràng buộc dữ liệu là các cách bảo vệ khác nhau; lựa chọn phụ thuộc vào bất biến nghiệp vụ và hệ quản trị.
- `SELECT ... FOR UPDATE` không có cùng phạm vi khóa trên mọi hệ quản trị và mọi mức cô lập. Hãy xác minh bằng tài liệu, execution plan và lock monitoring của môi trường thực tế.

Khi thiết kế một giao dịch, hãy hỏi: **Nghiệp vụ phụ thuộc vào những hàng đang tồn tại, hay phụ thuộc vào mọi hàng có thể thỏa điều kiện này — kể cả hàng chưa tồn tại?** Câu trả lời quyết định liệu khóa hàng có đủ hay cần bảo vệ cả phạm vi truy vấn.

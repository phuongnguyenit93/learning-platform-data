# Khi nào chọn khóa tường minh hoặc SERIALIZABLE thay cho ảnh chụp

Snapshot isolation (cô lập ảnh chụp) cho phép một giao dịch đọc dữ liệu từ một ảnh chụp nhất quán trong khi các giao dịch khác vẫn có thể ghi những phiên bản mới. Cách làm này giảm nhiều tình huống reader phải chờ writer và phù hợp với các workload đọc nhiều. Tuy nhiên, một snapshot nhất quán không đồng nghĩa với việc mọi lịch thực thi đều tương đương một thứ tự chạy tuần tự.

Khi một quy tắc nghiệp vụ phụ thuộc vào nhiều hàng hoặc một tập hàng, hai giao dịch có thể cùng đọc một trạng thái hợp lệ rồi cập nhật những hàng khác nhau theo cách khiến trạng thái cuối vi phạm quy tắc. Đây là dạng **write skew** thường gặp dưới snapshot isolation. Trong trường hợp đó, có thể cần khóa tường minh để các giao dịch phối hợp trên một tài nguyên chung, hoặc dùng mức cô lập `SERIALIZABLE` để DBMS bảo đảm kết quả tương đương một thứ tự tuần tự.

Lựa chọn nên bắt đầu từ bất biến dữ liệu cần bảo vệ. Nếu một ràng buộc khai báo như `UNIQUE`, `FOREIGN KEY` hoặc `CHECK` có thể diễn đạt quy tắc, hãy ưu tiên để DBMS thực thi ràng buộc đó. Nếu cần phối hợp một tài nguyên cụ thể và biết rõ phạm vi khóa, khóa tường minh có thể phù hợp. Nếu tính đúng đắn phụ thuộc vào nhiều lần đọc, điều kiện truy vấn hoặc quan hệ giữa nhiều hàng mà khó khóa thủ công đầy đủ, `SERIALIZABLE` thường là lựa chọn an toàn hơn.

## 1. Snapshot isolation bảo đảm điều gì?

Với snapshot isolation, một giao dịch đọc dữ liệu theo snapshot được xác định tại một thời điểm. Những thay đổi đã commit trước snapshot có thể được nhìn thấy; thay đổi commit sau đó thường không xuất hiện trong snapshot đang dùng. Giao dịch ghi tạo phiên bản mới, còn DBMS giữ phiên bản cũ đủ lâu để các snapshot đang hoạt động tiếp tục đọc nhất quán.

Điều này đem lại một số lợi ích:

- Các câu lệnh đọc có thể tránh chờ nhiều thao tác ghi đang diễn ra.
- Một giao dịch có thể đọc nhiều hàng từ cùng một trạng thái nhất quán.
- Các phiên bản cũ cho phép reader và writer hoạt động đồng thời trong nhiều tình huống.
- Với workload đọc nhiều, snapshot có thể cải thiện thông lượng và giảm blocking.

Nhưng snapshot isolation thường chỉ phát hiện hoặc ngăn một số xung đột ghi trực tiếp. Nếu hai giao dịch cập nhật cùng một hàng, DBMS có thể khiến một giao dịch chờ hoặc báo lỗi xung đột. Nếu mỗi giao dịch cập nhật một hàng khác nhau, cả hai có thể commit dù những lần đọc trước đó đã tạo ra một quyết định không còn đúng khi kết hợp.

Đó là lý do cần phân biệt:

- **Tính nhất quán của snapshot:** một giao dịch nhìn thấy tập phiên bản phù hợp với snapshot của nó.
- **Conflict serializability:** lịch có thể biến đổi thành một thứ tự tuần tự bằng cách hoán đổi các thao tác không xung đột.
- **Serializability:** kết quả của lịch tương đương với một thứ tự chạy tuần tự của các giao dịch.

Snapshot isolation không bảo đảm serializability trong mọi trường hợp. Một số DBMS đặt tên isolation level khác nhau, vì vậy cần kiểm tra hành vi thực tế của hệ quản trị. Ví dụ, PostgreSQL `REPEATABLE READ` sử dụng snapshot isolation và có thể cho phép serialization anomaly; PostgreSQL `SERIALIZABLE` bổ sung cơ chế phát hiện các phụ thuộc nguy hiểm. Không nên suy ra rằng cùng tên `REPEATABLE READ` có cùng triển khai ở mọi sản phẩm.

## 2. Write skew: hai snapshot riêng lẻ hợp lệ nhưng kết quả kết hợp sai

Giả sử một ca trực phải có ít nhất một bác sĩ đang trực. Bảng `doctor_on_call` lưu trạng thái trực của từng bác sĩ:

| shift_id | doctor_id | on_call |
|---|---|---|
| 10 | A | true |
| 10 | B | true |

T1 và T2 cùng bắt đầu ở snapshot isolation. T1 kiểm tra thấy có hai bác sĩ đang trực và quyết định cho A nghỉ. T2 cũng kiểm tra thấy có hai bác sĩ đang trực và quyết định cho B nghỉ.

```text
T1                                      T2
-----------------------------------     -----------------------------------
Đọc số bác sĩ trực = 2                  Đọc số bác sĩ trực = 2
Đặt A.on_call = false                  Đặt B.on_call = false
COMMIT                                  COMMIT
```

Hai giao dịch ghi vào hai hàng khác nhau, nên không có xung đột ghi trực tiếp trên cùng một hàng. Cả hai có thể commit. Kết quả cuối cùng không còn bác sĩ nào trực, vi phạm quy tắc nghiệp vụ.

Đây là write skew: mỗi giao dịch đưa ra quyết định dựa trên snapshot hợp lệ của riêng nó, nhưng các cập nhật độc lập khi kết hợp lại phá vỡ một bất biến chung. Một snapshot nhất quán không tự động khóa toàn bộ tập hàng mà điều kiện truy vấn đã đọc.

Ví dụ SQL mang tính minh họa dưới PostgreSQL `REPEATABLE READ`:

```sql
-- T1
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT count(*)
FROM doctor_on_call
WHERE shift_id = 10 AND on_call;
-- Kết quả: 2

UPDATE doctor_on_call
SET on_call = false
WHERE shift_id = 10 AND doctor_id = 'A';

COMMIT;
```

```sql
-- T2 chạy đồng thời với T1
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT count(*)
FROM doctor_on_call
WHERE shift_id = 10 AND on_call;
-- Cũng có thể thấy kết quả: 2

UPDATE doctor_on_call
SET on_call = false
WHERE shift_id = 10 AND doctor_id = 'B';

COMMIT;
```

Hai lệnh `UPDATE` nhắm đến hai hàng khác nhau. PostgreSQL Repeatable Read có thể cho phép cả hai commit trong lịch này. Hành vi cụ thể của hệ quản trị khác có thể khác; điều cần nhận ra là điều kiện `count(*) >= 1` phụ thuộc vào nhiều hàng, trong khi các giao dịch không cùng ghi một hàng để tạo xung đột trực tiếp.

## 3. Trước tiên hãy xem có thể dùng constraint hay không

Ràng buộc khai báo thường là cách đơn giản và đáng tin cậy nhất để bảo vệ bất biến dữ liệu.

- `PRIMARY KEY` và `UNIQUE` bảo đảm tính duy nhất của một hoặc nhiều giá trị khóa.
- `FOREIGN KEY` bảo đảm tham chiếu đến hàng hợp lệ.
- `CHECK` bảo đảm điều kiện trên giá trị của hàng đang được kiểm tra.
- `NOT NULL` ngăn giá trị thiếu ở cột bắt buộc.

Ví dụ, nếu quy tắc là mỗi người dùng chỉ được có một bản ghi đăng ký cho một sự kiện, hãy dùng unique constraint:

```sql
ALTER TABLE registration
ADD CONSTRAINT uq_registration_event_user
UNIQUE (event_id, user_id);
```

Hai giao dịch đồng thời đăng ký cùng một người dùng vào cùng sự kiện sẽ được DBMS điều phối qua ràng buộc duy nhất. Ứng dụng xử lý lỗi vi phạm unique constraint theo quy tắc nghiệp vụ.

Một `CHECK` constraint thường chỉ kiểm tra dữ liệu của chính hàng đó. Không thể dựa vào một `CHECK` thông thường để đếm số hàng trong bảng rồi bảo đảm tổng số bác sĩ đang trực không xuống dưới một. Với bất biến nhiều hàng, cần một mô hình dữ liệu hoặc cơ chế đồng bộ phù hợp.

Nếu có thể mô hình hóa quy tắc thành một constraint được DBMS hỗ trợ, constraint thường tránh được lỗi do một đường ghi trong ứng dụng quên lấy khóa. Nếu không thể, hãy cân nhắc khóa tường minh hoặc `SERIALIZABLE`.

## 4. Khi nào nên chọn khóa tường minh?

Khóa tường minh (explicit locking) phù hợp khi ứng dụng biết rõ tài nguyên cần bảo vệ và có thể xác định một phạm vi khóa ổn định. Thay vì chỉ đọc snapshot rồi hy vọng các giao dịch khác không thay đổi điều kiện, giao dịch chủ động yêu cầu lock trên hàng hoặc tài nguyên đại diện trước khi kiểm tra và cập nhật.

Các trường hợp thường phù hợp:

- Cập nhật một hàng tồn kho, ví tiền hoặc tài khoản có số dư mà nhiều giao dịch cùng thao tác.
- Claim một công việc từ hàng đợi để chỉ một worker xử lý tại một thời điểm.
- Phối hợp các thao tác trên một nhóm tài nguyên đã xác định trước.
- Bảo vệ một bất biến nhiều hàng bằng một hàng điều phối (guard row) hoặc khóa ứng dụng có quy ước rõ ràng.
- Cần khóa một hàng cụ thể để đọc giá trị mới nhất rồi đưa ra quyết định ghi ngay trong cùng transaction.

Khóa tường minh là lựa chọn mang tính bi quan (pessimistic): giao dịch xin quyền truy cập trước khi thực hiện phần công việc có thể xung đột. Nếu giao dịch khác đang giữ khóa không tương thích, nó chờ thay vì để hai bên cùng thực hiện rồi xử lý xung đột sau.

### 4.1. Khóa hàng tồn kho trước khi kiểm tra

Giả sử một sản phẩm còn 5 đơn vị và nhiều đơn hàng có thể đặt cùng lúc. Mỗi giao dịch cần đọc số lượng, kiểm tra đủ hàng rồi trừ số lượng.

Trong PostgreSQL, có thể khóa hàng tồn kho bằng `SELECT ... FOR UPDATE`:

```sql
BEGIN;

SELECT quantity
FROM inventory
WHERE product_id = 42
FOR UPDATE;

-- Ứng dụng kiểm tra quantity >= số lượng cần đặt.

UPDATE inventory
SET quantity = quantity - 3
WHERE product_id = 42;

COMMIT;
```

`FOR UPDATE` yêu cầu khóa hàng phù hợp và giữ khóa đến khi transaction kết thúc. Giao dịch khác muốn khóa cùng hàng để cập nhật phải chờ. Sau khi giao dịch đầu commit, giao dịch tiếp theo mới tiếp tục và có thể kiểm tra số lượng đã cập nhật.

Đối với một hàng tồn kho, có thể viết điều kiện ngay trong câu lệnh cập nhật để DBMS thực hiện kiểm tra và thay đổi nguyên tử:

```sql
UPDATE inventory
SET quantity = quantity - 3
WHERE product_id = 42
  AND quantity >= 3;
```

Ứng dụng kiểm tra số hàng được cập nhật. Nếu là 0, sản phẩm không tồn tại hoặc không còn đủ số lượng. Cách này thường gọn hơn khi toàn bộ bất biến chỉ phụ thuộc một hàng. Khóa tường minh hữu ích hơn khi quy trình cần đọc nhiều giá trị hoặc phối hợp nhiều thao tác trước khi cập nhật.

### 4.2. Dùng guard row để bảo vệ một bất biến nhiều hàng

Với ví dụ bác sĩ trực, có thể tạo một hàng đại diện cho ca trực:

```sql
CREATE TABLE shift_guard (
    shift_id bigint PRIMARY KEY
);
```

Mỗi transaction thay đổi trạng thái trực phải khóa cùng hàng guard trước khi đếm và cập nhật:

```sql
BEGIN;

SELECT shift_id
FROM shift_guard
WHERE shift_id = 10
FOR UPDATE;

SELECT count(*)
FROM doctor_on_call
WHERE shift_id = 10 AND on_call;

-- Chỉ cho phép một bác sĩ nghỉ nếu số người trực sau cập nhật vẫn >= 1.

UPDATE doctor_on_call
SET on_call = false
WHERE shift_id = 10 AND doctor_id = 'A';

COMMIT;
```

Nếu T1 giữ khóa guard của ca 10, T2 phải chờ trước khi đọc và quyết định thay đổi trạng thái của cùng ca. Sau khi T1 commit, T2 lấy được khóa rồi đọc trạng thái đã commit mới hơn, từ đó thấy điều kiện đã thay đổi.

Chiến lược này chỉ đúng nếu **mọi đường ghi có thể ảnh hưởng đến bất biến đều tuân thủ cùng giao thức khóa guard**. Một tác vụ nền hoặc API khác cập nhật `doctor_on_call` mà bỏ qua guard row vẫn có thể phá vỡ quy tắc.

Guard row cũng phải tồn tại trước khi khóa. `SELECT ... FOR UPDATE` không khóa được một hàng không tồn tại. Nếu tài nguyên đại diện có thể chưa được tạo, cần tạo hoặc bảo đảm hàng đó tồn tại bằng một cơ chế an toàn trước khi bắt đầu phần công việc phụ thuộc.

### 4.3. Khóa hàng hiện có không tự bảo vệ hàng chưa tồn tại

Một lỗi phổ biến là tìm các hàng thỏa điều kiện rồi khóa chúng, nhưng tập kết quả đang rỗng. Ví dụ:

```sql
SELECT *
FROM reservation
WHERE room_id = 8
  AND starts_at = TIMESTAMP '2026-12-01 09:00:00'
FOR UPDATE;
```

Nếu chưa có reservation nào, câu lệnh không khóa một hàng nào. Hai transaction có thể cùng thấy kết quả rỗng rồi cùng chèn một reservation mới, trừ khi có unique/exclusion constraint hoặc cơ chế khóa phạm vi phù hợp.

Các DBMS xử lý khóa phạm vi và predicate khác nhau. PostgreSQL `SELECT FOR UPDATE` khóa các hàng tìm được; nó không phải một khóa khoảng trống tổng quát như một số cơ chế next-key locking của InnoDB. Nếu cần bảo vệ điều kiện trên hàng chưa tồn tại, hãy xem xét constraint, hàng guard, advisory lock hoặc `SERIALIZABLE` tùy DBMS.

### 4.4. Khóa tường minh cần phạm vi và thứ tự rõ ràng

Khi một transaction khóa nhiều hàng, các transaction khác có thể chờ. Nếu T1 khóa A rồi B còn T2 khóa B rồi A, hai bên có thể deadlock. Hãy khóa tài nguyên theo một thứ tự nhất quán, chẳng hạn theo ID tăng dần.

Giữ transaction ngắn và chỉ khóa phần tài nguyên thật sự cần thiết. Không gọi dịch vụ mạng, chờ người dùng hoặc xử lý tệp lâu trong lúc vẫn giữ lock. Cần thiết kế retry cho deadlock và lock timeout nếu DBMS có thể trả các lỗi này.

## 5. Khi nào nên chọn SERIALIZABLE?

`SERIALIZABLE` là mức cô lập cao nhất trong các isolation level chuẩn SQL. Mục tiêu là bảo đảm kết quả commit tương đương với một thứ tự thực thi tuần tự của các transaction, như thể mỗi transaction chạy lần lượt mà không chồng lấn.

Mức này phù hợp khi tính đúng đắn phụ thuộc vào quan hệ giữa nhiều lần đọc và ghi, đặc biệt khi phạm vi dữ liệu được xác định bằng điều kiện truy vấn thay đổi theo thời gian.

Hãy cân nhắc `SERIALIZABLE` khi:

- Một transaction kiểm tra tổng, số lượng hoặc sự tồn tại của một tập hàng rồi cập nhật một phần tập đó.
- Bất biến nghiệp vụ phụ thuộc vào nhiều hàng và không có một hàng đại diện ổn định để khóa.
- Nhiều truy vấn đọc điều kiện trước khi quyết định ghi, và các giao dịch đồng thời có thể làm điều kiện đó thay đổi.
- Việc liệt kê chính xác tất cả hàng hoặc khoảng dữ liệu cần khóa rất khó, dễ bỏ sót đường ghi.
- Tính đúng đắn quan trọng hơn khả năng tránh retry hoặc mức đồng thời tối đa.

`SERIALIZABLE` cho phép ứng dụng diễn đạt yêu cầu ở cấp transaction: DBMS chịu trách nhiệm phát hiện hoặc ngăn lịch không thể tuần tự hóa theo cơ chế của sản phẩm.

### 5.1. Giải quyết write skew bằng SERIALIZABLE

Với ví dụ bác sĩ trực, nếu T1 và T2 chạy ở mức Serializable, DBMS phải bảo đảm không để cả hai cùng commit theo lịch tạo ra trạng thái không tương đương với bất kỳ thứ tự tuần tự nào.

Trong PostgreSQL, `SERIALIZABLE` sử dụng Serializable Snapshot Isolation (SSI). Các transaction vẫn có thể đọc từ snapshot và không nhất thiết phải khóa mọi hàng đọc theo cách bi quan. PostgreSQL theo dõi các phụ thuộc đọc/ghi có thể tạo ra serialization anomaly. Nếu phát hiện một cấu trúc phụ thuộc nguy hiểm, hệ thống có thể hủy một transaction với lỗi serialization để ứng dụng chạy lại.

```sql
-- T1
BEGIN ISOLATION LEVEL SERIALIZABLE;

SELECT count(*)
FROM doctor_on_call
WHERE shift_id = 10 AND on_call;

UPDATE doctor_on_call
SET on_call = false
WHERE shift_id = 10 AND doctor_id = 'A';

COMMIT;
```

```sql
-- T2 chạy đồng thời
BEGIN ISOLATION LEVEL SERIALIZABLE;

SELECT count(*)
FROM doctor_on_call
WHERE shift_id = 10 AND on_call;

UPDATE doctor_on_call
SET on_call = false
WHERE shift_id = 10 AND doctor_id = 'B';

COMMIT;
```

Một trong hai transaction có thể bị hủy với serialization failure thay vì cả hai cùng commit. Ứng dụng phải bắt lỗi tương ứng và thử lại **toàn bộ transaction**, bắt đầu từ lần đọc đầu tiên để quyết định được tính trên snapshot mới.

Không được chỉ chạy lại câu lệnh `UPDATE` cuối cùng. Nếu chạy lại riêng phần ghi, ứng dụng có thể vẫn dùng quyết định được tính từ snapshot cũ và phá vỡ mục tiêu của Serializable.

### 5.2. SERIALIZABLE không nhất thiết có nghĩa mọi thao tác đều khóa và chờ

Tên isolation level mô tả bảo đảm về kết quả, không bắt buộc mọi DBMS phải triển khai bằng cùng một kỹ thuật.

- Một số hệ thống dùng khóa phạm vi hoặc predicate/range locking để ngăn lịch xung đột.
- PostgreSQL dùng SSI trên nền snapshot để phát hiện các phụ thuộc có thể tạo ra lịch không tuần tự hóa, sau đó hủy một transaction nếu cần.
- Các DBMS khác có thể kết hợp khóa, kiểm tra xung đột và cơ chế phát hiện riêng.

Vì vậy, khi bật `SERIALIZABLE`, ứng dụng có thể gặp blocking, deadlock hoặc serialization failure tùy DBMS và lịch thực thi. Không nên giả định mọi giao dịch sẽ chờ cho đến khi có thể chạy tuần tự; một số hệ thống chủ động hủy transaction để bảo đảm tính đúng đắn.

## 6. So sánh snapshot isolation, khóa tường minh và SERIALIZABLE

| Tiêu chí | Snapshot isolation | Khóa tường minh | SERIALIZABLE |
|---|---|---|---|
| Mục tiêu | Đọc nhất quán từ snapshot, cho phép nhiều reader/writer đồng thời | Phối hợp truy cập vào tài nguyên được chỉ định | Bảo đảm kết quả tương đương thứ tự chạy tuần tự |
| Cách xử lý xung đột | Thường phát hiện xung đột ghi trực tiếp; có thể cho phép write skew | Giao dịch xung đột phải chờ hoặc nhận lỗi theo DBMS | DBMS ngăn hoặc phát hiện lịch không tuần tự hóa; có thể chờ hoặc hủy transaction |
| Phạm vi bảo vệ | Snapshot và các quy tắc xung đột của DBMS | Hàng, phạm vi hoặc tài nguyên mà ứng dụng khóa đúng cách | Các phụ thuộc đọc/ghi trong transaction theo mô hình DBMS |
| Chi phí thường gặp | Giữ phiên bản cũ, version store/undo và xử lý xung đột ghi | Blocking, deadlock và chi phí quản lý lock | Theo dõi xung đột, blocking hoặc retry do serialization failure |
| Phù hợp | Đọc nhiều, báo cáo nhất quán, workload ít bất biến liên hàng | Tài nguyên nóng, phạm vi khóa hẹp, giao thức phối hợp rõ | Bất biến phức tạp trên nhiều hàng hoặc predicate khó khóa thủ công |

Không có lựa chọn nào luôn nhanh nhất. Khóa tường minh có thể ít tốn chi phí hơn Serializable khi chỉ cần bảo vệ một hàng hoặc một nhóm tài nguyên nhỏ. Serializable có thể giảm lỗi thiết kế do ứng dụng bỏ sót một đường ghi, nhưng chi phí retry hoặc blocking có thể tăng khi tranh chấp cao. Snapshot isolation có thể đem lại thông lượng tốt nhưng cần constraint hoặc cơ chế bổ sung cho bất biến liên hàng.

## 7. SERIALIZABLE và khóa tường minh có thể dùng cùng nhau

Hai cơ chế không loại trừ lẫn nhau. Một ứng dụng có thể chạy ở `SERIALIZABLE` và vẫn khóa tường minh một tài nguyên nóng để kiểm soát thứ tự hoặc giảm số lần xung đột. Ngược lại, ứng dụng dùng snapshot isolation có thể khóa guard row để bảo vệ một bất biến cụ thể.

Tuy nhiên, không nên thêm lock một cách tùy tiện. Lock không đúng phạm vi có thể làm tăng blocking mà không bảo vệ được bất biến. Nếu dùng nhiều cơ chế, cần xác định rõ:

- Tài nguyên nào là đại diện cho bất biến?
- Tất cả transaction có khả năng thay đổi bất biến có lấy cùng lock không?
- Lock được lấy trước khi đọc điều kiện hay sau khi đã quyết định?
- Các lock được lấy theo thứ tự thống nhất không?
- Nếu Serializable abort hoặc deadlock xảy ra, ứng dụng retry toàn bộ đơn vị công việc như thế nào?

Trong PostgreSQL SSI, `SELECT FOR UPDATE` có thể được dùng để khóa một hàng cụ thể khi cần phối hợp với transaction khác. Tuy nhiên, nó không thay thế việc hiểu các predicate dependency mà Serializable theo dõi. Một khóa tường minh chỉ bảo vệ tài nguyên đã khóa; nó không tự động khóa mọi hàng có thể thỏa một điều kiện truy vấn.

## 8. Khác biệt triển khai giữa các DBMS

Tên isolation level có thể giống nhau nhưng cách triển khai snapshot và Serializable khác nhau. Khi thiết kế, hãy xem tài liệu đúng DBMS và phiên bản đang dùng.

### 8.1. PostgreSQL

- `READ COMMITTED` thường tạo snapshot cho từng câu lệnh.
- `REPEATABLE READ` sử dụng snapshot ổn định cho transaction và có thể cho phép serialization anomaly.
- `SERIALIZABLE` bổ sung Serializable Snapshot Isolation (SSI), theo dõi phụ thuộc và có thể hủy transaction với SQLSTATE `40001`.
- `SELECT ... FOR UPDATE` khóa các hàng được tìm thấy; nó không tự tạo khóa khoảng trống tổng quát cho hàng chưa tồn tại.

### 8.2. MySQL InnoDB

InnoDB dùng MVCC/read view cho consistent read và kết hợp row lock, gap lock hoặc next-key lock tùy isolation level, câu lệnh và access path. Ở `REPEATABLE READ`, locking read và thao tác ghi có thể khóa phạm vi chỉ mục rộng hơn hàng hiện có. `SELECT ... FOR UPDATE` là locking read, khác với consistent read thông thường.

`SERIALIZABLE` của InnoDB thay đổi cách xử lý đọc để tăng bảo vệ trước truy cập đồng thời, thường làm tăng khóa và blocking. Cần kiểm tra kế hoạch truy vấn và chỉ mục vì phạm vi khóa phụ thuộc cách DBMS tìm hàng.

### 8.3. SQL Server

SQL Server có các isolation level dựa trên khóa truyền thống và các lựa chọn row version như Read Committed Snapshot Isolation (RCSI) hoặc Snapshot Isolation. Snapshot Isolation có thể gặp write skew nếu các giao dịch cập nhật các hàng khác nhau dựa trên một điều kiện chung.

SQL Server `SERIALIZABLE` có thể sử dụng key-range lock để bảo vệ phạm vi truy vấn. Các gợi ý như `UPDLOCK` hoặc `HOLDLOCK` thay đổi cách lấy và giữ khóa; cần dùng đúng ngữ nghĩa và chỉ mục, vì phạm vi khóa có thể rộng hơn dự kiến.

### 8.4. Oracle

Oracle cung cấp consistent read dựa trên undo và các cơ chế khóa hàng. `SERIALIZABLE` sử dụng snapshot ở mức transaction và có thể trả lỗi khi transaction cố sửa dữ liệu đã bị transaction khác thay đổi sau snapshot của nó. Khóa tường minh có thể dùng khi ứng dụng cần tuần tự hóa quyền cập nhật một hàng hoặc một tài nguyên cụ thể.

Các ví dụ cú pháp trong bài chủ yếu dùng PostgreSQL. Không sao chép nguyên xi cú pháp `FOR UPDATE`, isolation level hoặc cách xử lý lỗi sang DBMS khác mà chưa kiểm tra tài liệu tương ứng.

## 9. Xử lý lỗi và retry đúng cách

Khi dùng `SERIALIZABLE`, ứng dụng phải xem serialization failure là một kết quả có thể xảy ra trong hoạt động bình thường dưới cạnh tranh. Cần rollback transaction thất bại rồi chạy lại toàn bộ đơn vị công việc trong một transaction mới.

Pseudocode:

```text
for attempt in 1..MAX_RETRIES:
    begin transaction at SERIALIZABLE
    try:
        read all values used for the decision
        validate business invariant
        perform writes
        commit
        return success
    catch serialization_failure:
        rollback
        if attempt == MAX_RETRIES:
            return retryable_error
        wait briefly with bounded backoff
```

Trong PostgreSQL, serialization failure thường có SQLSTATE `40001`. Deadlock detected thường có SQLSTATE `40P01`. Hai lỗi có nguyên nhân khác nhau nhưng đều có thể yêu cầu rollback và retry toàn bộ transaction nếu thao tác có thể chạy lại an toàn.

Một lần retry cần tính lại mọi dữ liệu đã đọc và mọi quyết định nghiệp vụ. Không giữ kết quả tính từ lần thử trước. Nếu transaction thực hiện tác động bên ngoài như gửi email, gọi thanh toán hoặc phát sự kiện, hãy tránh lặp tác động đó khi retry. Có thể dùng transactional outbox, idempotency key hoặc chỉ thực hiện tác động sau khi commit theo một giao thức phù hợp.

Khi dùng khóa tường minh, ứng dụng cũng cần xử lý deadlock victim và lock timeout. Retry không thay thế việc sửa thứ tự khóa gây deadlock; nếu cùng một lịch lặp lại, retry có thể liên tục thất bại.

## 10. Cách chọn theo tình huống nghiệp vụ

### Tình huống A: cập nhật một hàng số dư hoặc tồn kho

Nếu mọi quyết định chỉ phụ thuộc vào một hàng, một câu lệnh cập nhật có điều kiện hoặc `SELECT FOR UPDATE` có thể đủ. Khóa phạm vi hẹp giúp các giao dịch khác nhau trên sản phẩm/tài khoản độc lập tiếp tục đồng thời.

### Tình huống B: bảo đảm tổng số hàng thỏa một điều kiện không vượt ngưỡng

Ví dụ giới hạn số chỗ đặt phòng, số người tham gia hoặc số bác sĩ trực tối thiểu. Nếu có thể dùng constraint hoặc một hàng counter/guard được cập nhật nguyên tử, hãy cân nhắc cách đó. Nếu điều kiện dựa trên tập hàng động và khó khóa đầy đủ, `SERIALIZABLE` có thể bảo vệ quy tắc tốt hơn.

### Tình huống C: claim một công việc trong hàng đợi

Khóa tường minh thường phù hợp vì ứng dụng muốn một worker nhận một hàng cụ thể. PostgreSQL hỗ trợ `FOR UPDATE SKIP LOCKED` cho kiểu lấy công việc mà bỏ qua hàng đang bị worker khác khóa:

```sql
BEGIN;

SELECT job_id
FROM job_queue
WHERE status = 'READY'
ORDER BY priority DESC, job_id
FOR UPDATE SKIP LOCKED
LIMIT 1;

-- Đánh dấu job đã được nhận trong cùng transaction.
UPDATE job_queue
SET status = 'RUNNING'
WHERE job_id = :job_id;

COMMIT;
```

`SKIP LOCKED` phù hợp cho queue vì worker có thể lấy hàng khác thay vì chờ hàng đang được xử lý. Nó không phù hợp cho mọi truy vấn nghiệp vụ: kết quả cố ý bỏ qua hàng đang khóa và do đó không đại diện cho một snapshot đầy đủ của toàn bộ tập dữ liệu.

### Tình huống D: kiểm tra nhiều điều kiện rồi cập nhật nhiều bảng

Nếu các điều kiện phụ thuộc lẫn nhau và khó liệt kê hết phạm vi khóa, Serializable thường dễ diễn đạt yêu cầu đúng hơn. Đổi lại, ứng dụng phải có retry và theo dõi tỷ lệ serialization failure.

### Tình huống E: cần độc quyền một tài nguyên logic không tương ứng với một hàng

Có thể dùng một hàng guard hoặc advisory lock nếu DBMS hỗ trợ. Advisory lock là khóa do ứng dụng định nghĩa theo một khóa logic; DBMS không tự biết bất biến nghiệp vụ nào cần được bảo vệ. Mọi thành phần tham gia phải tuân thủ cùng quy ước lấy và nhả advisory lock.

## 11. Quy trình ra quyết định

Có thể dùng trình tự sau khi thiết kế một transaction có đọc rồi ghi:

1. **Nêu bất biến chính xác.** Ví dụ: số bác sĩ trực của một ca luôn ít nhất là một; số lượng tồn kho không âm; một phòng không có hai đặt chỗ trùng thời gian.
2. **Kiểm tra constraint.** Nếu `UNIQUE`, `CHECK`, foreign key, exclusion constraint hoặc mô hình dữ liệu có thể bảo vệ trực tiếp, hãy dùng constraint.
3. **Xác định phạm vi xung đột.** Quy tắc phụ thuộc một hàng, một hàng guard, một khoảng chỉ mục hay một tập hàng động?
4. **Nếu phạm vi hẹp và ổn định, cân nhắc khóa tường minh.** Lấy lock trước khi đọc điều kiện, khóa mọi tài nguyên liên quan và giữ transaction ngắn.
5. **Nếu phạm vi phụ thuộc predicate hoặc khó liệt kê đầy đủ, cân nhắc SERIALIZABLE.** Bảo đảm ứng dụng retry toàn bộ transaction khi DBMS báo serialization failure.
6. **Đo hành vi dưới tải đồng thời.** Theo dõi blocking, deadlock, serialization failure, thời gian chờ và thông lượng.
7. **Kiểm tra tất cả đường ghi.** Một giao thức khóa chỉ đúng nếu mọi đường ghi có thể phá bất biến đều tuân thủ nó.

## 12. Những sai lầm thường gặp

- **Cho rằng snapshot nhất quán đồng nghĩa với serializable.** Snapshot có thể vẫn cho phép write skew khi các transaction cập nhật những hàng khác nhau.
- **Khóa những hàng đang có rồi nghĩ rằng hàng mới cũng được bảo vệ.** `FOR UPDATE` trên kết quả rỗng không khóa một hàng chưa tồn tại; cần constraint, range lock phù hợp, guard hoặc Serializable.
- **Lấy lock sau khi đã đọc và quyết định.** Khi đó một transaction khác có thể thay đổi điều kiện trong khoảng giữa lần đọc và lúc lấy khóa.
- **Chỉ một phần ứng dụng dùng guard lock.** Một đường ghi bỏ qua giao thức có thể phá vỡ bất biến.
- **Chạy lại riêng câu lệnh cuối sau serialization failure.** Phải chạy lại toàn bộ transaction để đọc lại trạng thái và tính lại quyết định.
- **Cho rằng SERIALIZABLE luôn chặn thay vì abort.** Cách triển khai khác nhau; PostgreSQL SSI có thể hủy transaction để tránh lịch không tuần tự hóa.
- **Bật SERIALIZABLE cho mọi transaction mà không theo dõi.** Mức cô lập cao hơn có thể làm tăng blocking, retry hoặc chi phí phát hiện xung đột. Cần đo trên workload thực tế.
- **Giữ khóa trong lúc chờ mạng hoặc người dùng.** Điều này kéo dài blocking và tăng nguy cơ deadlock.

## 13. Những điểm cần ghi nhớ

- Snapshot isolation giúp đọc nhất quán và tăng đồng thời, nhưng không bảo đảm serializability; write skew có thể xảy ra khi các giao dịch đọc cùng điều kiện rồi ghi những hàng khác nhau.
- Hãy ưu tiên constraint nếu có thể diễn đạt bất biến bằng constraint của DBMS.
- Chọn khóa tường minh khi biết rõ tài nguyên cần phối hợp, có thể khóa trước khi đọc điều kiện và mọi đường ghi tuân thủ cùng giao thức.
- Một hàng guard hoặc advisory lock có thể đại diện cho bất biến nhiều hàng, nhưng phải được mọi transaction liên quan sử dụng.
- Chọn `SERIALIZABLE` khi tính đúng đắn phụ thuộc vào nhiều hàng hoặc predicate khó khóa thủ công; chuẩn bị xử lý serialization failure bằng cách retry toàn bộ transaction.
- `SERIALIZABLE` không có cùng cách triển khai ở mọi DBMS. PostgreSQL dùng SSI; InnoDB và SQL Server có các cơ chế khóa phạm vi; Oracle có quy tắc snapshot và xung đột riêng.
- Khóa tường minh và Serializable có thể kết hợp, nhưng phải xác định phạm vi khóa, thứ tự lấy khóa, thời gian giữ khóa và chiến lược retry.

Khi lựa chọn cơ chế đồng thời, hãy bắt đầu từ bất biến nghiệp vụ và những giao dịch có thể cùng thay đổi nó. Snapshot phù hợp khi đọc nhất quán là đủ; khóa tường minh phù hợp khi có tài nguyên phối hợp rõ ràng; Serializable phù hợp khi DBMS cần bảo vệ quan hệ giữa các lần đọc và ghi phức tạp. Mục tiêu là bảo đảm trạng thái commit luôn thỏa quy tắc nghiệp vụ trong khi vẫn duy trì mức đồng thời phù hợp với tải thực tế.

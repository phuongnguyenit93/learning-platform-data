# Timestamp trong BATCH và giới hạn suy luận thứ tự các câu lệnh

Trong Apache Cassandra, `BATCH` giúp gom nhiều câu lệnh CQL thành một yêu cầu ghi. Tuy nhiên, **thứ tự liệt kê câu lệnh trong BATCH không phải là thứ tự ghi đè được bảo đảm**, và `BATCH` cũng không biến các câu lệnh thành một giao dịch SQL có thứ tự thực thi tuần tự. Muốn hiểu kết quả cuối cùng, cần phân biệt **timestamp của mutation**, **quy tắc phân giải xung đột giữa các bản ghi** và **bảo đảm của từng loại BATCH**.

Bài này thuộc chương **BATCH và counter** của module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Các ví dụ đặt trong bối cảnh Cassandra phân tán, mô hình wide-column, thiết kế theo truy vấn, replication và consistency level; mục tiêu là biết khi nào có thể suy luận từ timestamp và khi nào phải thiết kế lại phép ghi để tránh phụ thuộc vào thứ tự.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích timestamp ghi trong Cassandra là gì, đơn vị đo và vai trò khi hai mutation chạm cùng một ô dữ liệu.
- Phân biệt timestamp mặc định của BATCH, timestamp đặt ở cấp BATCH và timestamp chỉ định trên từng câu lệnh.
- Nêu lý do không thể suy ra thứ tự thực thi, thứ tự nghiệp vụ hoặc tính cô lập chỉ từ thứ tự câu lệnh trong BATCH.
- Dùng `WRITETIME` kiểm tra timestamp của cột thông thường và nhận biết giới hạn của phép kiểm tra này.
- Thiết kế thao tác ghi, retry và xử lý counter sao cho không phụ thuộc vào một giả định thứ tự sai.

## 2. Timestamp là metadata của bản ghi, không phải số thứ tự câu lệnh

Cassandra lưu các mutation theo mô hình phân tán: dữ liệu được xác định bởi **partition key**, trong phân vùng có thể có các hàng theo **clustering key**, và các cột thông thường chứa giá trị cùng metadata ghi. Với các cột thông thường, timestamp của mutation là một cơ sở để Cassandra phân giải xung đột giữa các phiên bản cùng ô dữ liệu khi đọc và hợp nhất dữ liệu giữa các replica.

- Timestamp của Cassandra thường được biểu diễn bằng **số microgiây kể từ Unix epoch (UTC)**. Ví dụ `1700000000000200` là một giá trị microgiây, không phải mili-giây Java `System.currentTimeMillis()`.
- **Timestamp lớn hơn thường thắng** khi hai giá trị cùng một ô cạnh tranh; quy tắc này hay được gọi là *last-write-wins* (LWW). “Last” ở đây là theo **timestamp dùng để hòa giải dữ liệu**, không nhất thiết là yêu cầu đến máy chủ cuối cùng.
- Cùng một hàng không có nghĩa là cùng một ô: hai câu lệnh cập nhật **hai cột khác nhau** có thể tồn tại đồng thời dù timestamp giống nhau.
- Nếu timestamp **bằng nhau** trên cùng ô, Cassandra phải áp dụng quy tắc hòa giải khi hòa nhau (bao gồm ưu tiên tombstone đối với giá trị sống và quy tắc so sánh giá trị đối với hai giá trị sống). **Không dùng thứ tự câu lệnh trong BATCH để dự đoán người thắng**.

Ví dụ hai bản ghi đến theo thứ tự thời gian thực như sau:

| Thời điểm yêu cầu đến | Mutation cùng ô `status` | Timestamp ghi | Kết quả khi hòa giải |
|---|---|---:|---|
| Đến trước | `status = 'PAID'` | `1700000000000200` | Thắng |
| Đến sau | `status = 'CREATED'` | `1700000000000100` | Thua vì timestamp nhỏ hơn |

Kết quả sau khi các replica đã hội tụ là `PAID`, dù yêu cầu `CREATED` đến sau. Timestamp có thể do coordinator gán hoặc do client/driver cung cấp theo giao thức hay CQL; vì vậy **đồng hồ lệch**, timestamp tự đặt hoặc retry có thể khiến thứ tự timestamp khác thứ tự sự kiện ngoài đời.

> **Ranh giới quan trọng:** Timestamp là metadata để giải quyết xung đột ở mức dữ liệu. Nó không phải transaction ID, sequence number đáng tin cậy cho nghiệp vụ, và không xác nhận câu lệnh nào chạy xong trước câu lệnh nào.

## 3. Timestamp được gán như thế nào trong BATCH?

### 3.1. Không khai báo `USING TIMESTAMP`

Một BATCH có timestamp mặc định dùng cho các mutation không tự khai báo timestamp. Với câu lệnh CQL thông thường, các statement trong cùng BATCH sẽ dùng timestamp mặc định chung đó; timestamp thực tế có thể được cung cấp ở mức request bởi driver/client hoặc được gán trong quá trình xử lý tại Cassandra.

```sql
BEGIN BATCH
    UPDATE batch_lab.order_state
    SET status = 'PAID'
    WHERE order_id = 00000000-0000-0000-0000-000000000006;

    UPDATE batch_lab.order_state
    SET updated_by = 'payment-service'
    WHERE order_id = 00000000-0000-0000-0000-000000000006;
APPLY BATCH;
```

Hai cột khác nhau nhận mutation theo cùng timestamp mặc định, nhưng **không thể từ đó kết luận câu lệnh `status` chạy trước câu lệnh `updated_by`**. Hai giá trị chỉ cần được xem như hai phần của kết quả ghi.

### 3.2. Khai báo timestamp cấp BATCH

Có thể đặt timestamp tường minh cho BATCH bằng `USING TIMESTAMP`:

```sql
BEGIN BATCH USING TIMESTAMP 1700000000000300
    UPDATE batch_lab.order_state
    SET status = 'PROCESSING'
    WHERE order_id = 00000000-0000-0000-0000-000000000006;

    UPDATE batch_lab.order_state
    SET updated_by = 'worker-1'
    WHERE order_id = 00000000-0000-0000-0000-000000000006;
APPLY BATCH;
```

Ở đây, các mutation không khai báo timestamp riêng nhận giá trị `1700000000000300`. Đó là **timestamp ghi**, không phải tín hiệu Cassandra sẽ xử lý câu lệnh đầu trước câu lệnh sau. Đặt timestamp cố định cho mọi lần chạy còn có thể tạo nhiều lần ghi cùng timestamp; cần chủ động tránh xung đột nếu chương trình sử dụng lại giá trị này.

### 3.3. Khai báo timestamp cấp câu lệnh

Một mutation có thể chỉ định `USING TIMESTAMP` ngay trong câu lệnh `INSERT`, `UPDATE` hoặc `DELETE`. Timestamp ở cấp câu lệnh được dùng cho mutation đó và thay thế timestamp mặc định của BATCH đối với mutation tương ứng:

```sql
BEGIN BATCH USING TIMESTAMP 1700000000000300
    UPDATE batch_lab.order_state
    USING TIMESTAMP 1700000000000500
    SET status = 'DONE'
    WHERE order_id = 00000000-0000-0000-0000-000000000006;

    UPDATE batch_lab.order_state
    USING TIMESTAMP 1700000000000400
    SET updated_by = 'worker-2'
    WHERE order_id = 00000000-0000-0000-0000-000000000006;
APPLY BATCH;
```

Khi đọc lại, `status` và `updated_by` có thể có hai timestamp khác nhau dù nằm trong cùng hàng và cùng BATCH. Cần đánh giá timestamp **theo từng ô bị cập nhật**, không lấy một con số duy nhất để gán cho “toàn bộ hàng”.

| Phạm vi | Cú pháp | Ý nghĩa |
|---|---|---|
| Mặc định | `BEGIN BATCH ... APPLY BATCH` | Dùng timestamp mặc định của request/BATCH nếu mutation không tự khai báo |
| Cấp BATCH | `BEGIN BATCH USING TIMESTAMP <microseconds>` | Đặt timestamp mặc định chung cho mutation trong BATCH |
| Cấp statement | `UPDATE ... USING TIMESTAMP <microseconds> SET ...` | Chỉ định timestamp cho mutation của statement đó |

## 4. Vì sao không thể suy luận thứ tự từ các câu lệnh trong BATCH?

Xét ví dụ cố ý **ghi hai giá trị khác nhau vào cùng một ô**:

```sql
BEGIN BATCH USING TIMESTAMP 1700000000000600
    UPDATE batch_lab.order_state
    SET status = 'QUEUED'
    WHERE order_id = 00000000-0000-0000-0000-000000000006;

    UPDATE batch_lab.order_state
    SET status = 'RUNNING'
    WHERE order_id = 00000000-0000-0000-0000-000000000006;
APPLY BATCH;
```

**Không được diễn giải rằng `RUNNING` chắc chắn thắng vì nó viết sau `QUEUED`.** Cả hai mutation cạnh tranh cùng ô với cùng timestamp, nên không thể coi cú pháp BATCH là một chuỗi chuyển trạng thái. Nếu một bản Cassandra cho ra kết quả lặp lại ổn định trong thử nghiệm nhỏ, hiện tượng ấy vẫn **không phải hợp đồng thứ tự nghiệp vụ** để ứng dụng dựa vào.

Những nhầm lẫn thường gặp:

| Nhận định | Đánh giá | Giải thích |
|---|---|---|
| “Statement thứ hai trong BATCH luôn thắng statement thứ nhất.” | Sai | Thứ tự văn bản không định nghĩa thứ tự thắng ghi đè; hòa giải dùng timestamp và quy tắc xử lý khi hòa |
| “Cùng timestamp nghĩa là chạy đồng thời chính xác.” | Sai | Timestamp chung là metadata ghi, không đo được lịch thực thi nội bộ |
| “Timestamp cao hơn nghĩa là hành động nghiệp vụ xảy ra sau.” | Không bảo đảm | Client có thể tự đặt timestamp; đồng hồ giữa máy có thể lệch |
| “Logged BATCH có nghĩa là đọc thấy toàn bộ như một transaction SQL.” | Sai | BATCH không cung cấp isolation cho các lượt đọc đồng thời |
| “Nếu ghi hai cột khác nhau thì chúng bắt buộc đè lên nhau.” | Sai | LWW phân giải trên ô/cell bị xung đột, không phải trên toàn bộ hàng |

### 4.1. Atomicity, isolation và statement ordering là ba khái niệm khác nhau

**Logged BATCH** hỗ trợ tính nguyên tử về khả năng các mutation cuối cùng được áp dụng: cơ chế batchlog giúp khôi phục/hoàn thành các phần còn thiếu khi có lỗi. Điều đó **không có nghĩa** các reader đồng thời chỉ nhìn thấy trạng thái “trước toàn bộ” hoặc “sau toàn bộ” BATCH. Đặc biệt với nhiều partition, một reader có thể quan sát dữ liệu đang ở các thời điểm khác nhau.

**Unlogged BATCH** giảm chi phí batchlog nhưng không bảo đảm tính nguyên tử giữa nhiều partition khi lỗi xảy ra. Các mutation trong cùng một partition có bảo đảm nguyên tử ở mức partition của Cassandra, nhưng **không tạo thứ tự thực thi nghiệp vụ cho các câu lệnh**.

**Consistency level** như `ONE`, `QUORUM`, `ALL` quy định số replica cần phản hồi cho thao tác đọc/ghi; nó **không tự thêm một thứ tự tuần tự cho các statement**, không làm BATCH trở thành transaction đa partition, và không biến timestamp thành số thứ tự nghiệp vụ. Tương tự, clustering key quyết định cách sắp xếp hàng khi truy vấn **bên trong một partition**, không quyết định thứ tự các lệnh `UPDATE` trong BATCH.

### 4.2. Ví dụ với nhiều partition

```sql
BEGIN LOGGED BATCH
    UPDATE batch_lab.order_state
    SET status = 'SHIPPED'
    WHERE order_id = 00000000-0000-0000-0000-000000000006;

    UPDATE batch_lab.order_state
    SET status = 'SHIPPED'
    WHERE order_id = 00000000-0000-0000-0000-000000000007;
APPLY BATCH;
```

Hai `order_id` là hai partition. Cơ chế logged batch giúp xử lý việc áp dụng đủ các mutation sau sự cố, nhưng người đọc đồng thời không được giả định luôn quan sát trạng thái đã cập nhật của **cả hai partition cùng lúc**. Logged batch nhiều partition cũng tăng chi phí mạng và ghi batchlog; không nên dùng để “tăng tốc” hàng loạt ghi độc lập, và không nên coi nó là lời giải tổng quát cho consistency đa bản ghi.

## 5. Thực hành CQL: phân biệt timestamp với thứ tự thực thi

Thí nghiệm dành cho môi trường Cassandra học tập. Với cụm một node, keyspace bên dưới chỉ nhằm minh họa; khi triển khai nhiều node, chọn replication strategy và replication factor phù hợp topology thực tế.

### Bước 1: Tạo dữ liệu mẫu

```sql
CREATE KEYSPACE IF NOT EXISTS batch_lab
WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};

CREATE TABLE IF NOT EXISTS batch_lab.order_state (
    order_id uuid PRIMARY KEY,
    status text,
    updated_by text
);

INSERT INTO batch_lab.order_state (order_id, status, updated_by)
VALUES (00000000-0000-0000-0000-000000000006, 'CREATED', 'api')
USING TIMESTAMP 1700000000000100;
```

### Bước 2: Ghi giá trị đến sau nhưng timestamp thấp hơn

```sql
UPDATE batch_lab.order_state
USING TIMESTAMP 1700000000000200
SET status = 'PAID'
WHERE order_id = 00000000-0000-0000-0000-000000000006;

UPDATE batch_lab.order_state
USING TIMESTAMP 1700000000000150
SET status = 'RETRY_CREATED'
WHERE order_id = 00000000-0000-0000-0000-000000000006;

SELECT status, WRITETIME(status)
FROM batch_lab.order_state
WHERE order_id = 00000000-0000-0000-0000-000000000006;
```

**Dự kiến:** `status = 'PAID'` và `writetime(status) = 1700000000000200`. Lệnh `RETRY_CREATED` chạy sau về mặt gửi yêu cầu nhưng có timestamp thấp hơn nên không thay đổi giá trị đã thắng. Để kết quả có thể tái lập, hãy dùng một `order_id` mới nếu đã từng chạy thí nghiệm với timestamp lớn hơn.

### Bước 3: Ghi hai cột trong cùng BATCH và quan sát metadata

```sql
BEGIN BATCH USING TIMESTAMP 1700000000000300
    UPDATE batch_lab.order_state
    SET status = 'PROCESSING'
    WHERE order_id = 00000000-0000-0000-0000-000000000006;

    UPDATE batch_lab.order_state
    SET updated_by = 'worker-1'
    WHERE order_id = 00000000-0000-0000-0000-000000000006;
APPLY BATCH;

SELECT status, updated_by,
       WRITETIME(status), WRITETIME(updated_by)
FROM batch_lab.order_state
WHERE order_id = 00000000-0000-0000-0000-000000000006;
```

**Dự kiến:** Hai cột đều có timestamp `1700000000000300`; đây là bằng chứng về **metadata ghi giống nhau**, không phải bằng chứng về statement nào chạy trước.

### Bước 4: Ghi với timestamp riêng trên từng statement

```sql
BEGIN BATCH USING TIMESTAMP 1700000000000300
    UPDATE batch_lab.order_state
    USING TIMESTAMP 1700000000000500
    SET status = 'DONE'
    WHERE order_id = 00000000-0000-0000-0000-000000000006;

    UPDATE batch_lab.order_state
    USING TIMESTAMP 1700000000000400
    SET updated_by = 'worker-2'
    WHERE order_id = 00000000-0000-0000-0000-000000000006;
APPLY BATCH;

SELECT status, updated_by,
       WRITETIME(status), WRITETIME(updated_by)
FROM batch_lab.order_state
WHERE order_id = 00000000-0000-0000-0000-000000000006;
```

**Dự kiến:** `status = 'DONE'` với timestamp `1700000000000500`; `updated_by = 'worker-2'` với timestamp `1700000000000400`. Mỗi cột hòa giải phiên bản của **chính nó**.

### `WRITETIME` giúp và không giúp điều gì?

`WRITETIME(column)` trả timestamp của giá trị cột thông thường đang có thể đọc được. Đây là công cụ thích hợp để quan sát metadata của ví dụ trên, nhưng không đủ để tái dựng lịch sử đầy đủ:

- Không cho biết thứ tự thực thi, thứ tự request được gửi/nhận hoặc thời điểm mỗi replica hoàn tất ghi.
- Không cho biết tất cả phiên bản đã bị ghi đè; Cassandra không phải hệ thống audit log chỉ nhờ `WRITETIME`.
- Không có ý nghĩa tương tự cho primary key/counter; khi giá trị đã bị xóa, không thể đơn giản đọc `WRITETIME` của giá trị không còn hiển thị để suy ra toàn bộ lịch sử tombstone.
- Nếu timestamp từ client bị sai hoặc cố ý đặt cao, kết quả có thể trái với thứ tự thời gian thực. Dữ liệu đang lưu có thể bị chi phối bởi timestamp đó cho tới khi một mutation mới có timestamp lớn hơn thắng.

## 6. Trường hợp đặc biệt: counter

**Counter** không nên được diễn giải theo mô hình “giá trị lớn nhất theo `USING TIMESTAMP` thắng” của cột thông thường. Counter dùng cơ chế cập nhật tăng/giảm riêng; `COUNTER BATCH` dành cho các mutation counter, không trộn mutation counter với mutation thông thường, và **không dùng `USING TIMESTAMP` để ấn định thứ tự cho các phép cộng/trừ counter**.

```sql
-- Giả sử đã có bảng batch_lab.page_stats
-- với page_id uuid PRIMARY KEY, views counter.
BEGIN COUNTER BATCH
    UPDATE batch_lab.page_stats
    SET views = views + 1
    WHERE page_id = 00000000-0000-0000-0000-000000000006;
APPLY BATCH;
```

Phép tăng counter **không có tính idempotent như gán lại một giá trị cố định**. Khi timeout mà không biết kết quả đã được áp dụng chưa, gửi lại cùng phép tăng có thể gây đếm thêm. Hãy thiết kế retry và cơ chế khử trùng lặp theo yêu cầu nghiệp vụ; đừng kỳ vọng timestamp cấp BATCH xử lý việc này.

## 7. Thiết kế Java và CQL để không phụ thuộc vào thứ tự BATCH

1. **Ghi trạng thái cuối cùng một lần:** Nếu một nghiệp vụ muốn chuyển từ `CREATED` sang `PAID` trong một thao tác, chỉ ghi trạng thái đích vào cột `status`; đừng đưa hai lệnh cập nhật cùng ô vào BATCH để giả vờ tạo tiến trình tuần tự.
2. **Tách dữ liệu sự kiện với trạng thái hiện tại:** Nếu cần lưu `CREATED → PAID → SHIPPED`, dùng bảng sự kiện với khóa có thứ tự nghiệp vụ rõ ràng (ví dụ `event_id`, `event_version` hoặc sequence cấp ứng dụng) và bảng trạng thái hiện tại phục vụ truy vấn. Không lấy timestamp ghi làm nguồn sự thật duy nhất về thứ tự sự kiện.
3. **Khi cần kiểm tra điều kiện cạnh tranh, xem xét LWT:** `UPDATE ... IF ...` (lightweight transaction) có thể bảo vệ một số thay đổi điều kiện trên phạm vi partition theo hỗ trợ của Cassandra; cần đánh giá chi phí Paxos và giới hạn của thao tác. BATCH thông thường không thay thế kiểm soát cạnh tranh kiểu này.
4. **Kiểm soát timestamp do ứng dụng Java cấp:** Nếu dùng driver Java và tự cấp timestamp, đảm bảo đơn vị **microgiây**, quy tắc đồng hồ nhất quán và tránh vô tình dùng mili-giây. Đánh giá cách driver cấu hình timestamp generator và retry; nếu không có yêu cầu đặc biệt, tránh tự tạo timestamp thủ công cho mọi mutation.
5. **Batch theo đúng mục đích:** Ưu tiên gom những ghi liên quan cùng partition khi phù hợp. Với nhiều partition, chỉ dùng logged batch khi thật sự cần bảo đảm hoàn tất eventual của nhóm mutation; giám sát chi phí batchlog và kích thước batch.
6. **Thiết kế đúng mức nhất quán:** Chọn consistency level theo yêu cầu đọc/ghi và replication. Kể cả khi dùng `QUORUM`, ứng dụng vẫn cần mô hình hóa thứ tự nghiệp vụ, xử lý các tình huống concurrent write và timeout một cách tường minh.

Một luồng ứng dụng Java cần bảo đảm “chỉ tiến từ trạng thái A sang trạng thái B nếu vẫn đang ở A” có thể dùng câu lệnh điều kiện ở cấp dữ liệu phù hợp:

```sql
UPDATE batch_lab.order_state
SET status = 'PAID'
WHERE order_id = 00000000-0000-0000-0000-000000000006
IF status = 'CREATED';
```

Ứng dụng phải kiểm tra kết quả `[applied]` do Cassandra trả về và có chính sách xử lý khi điều kiện thất bại. Đây là mục đích khác với BATCH ghi nhiều statement. Không kết hợp một cách tùy tiện `USING TIMESTAMP` với các phép ghi điều kiện mà chưa xác minh ràng buộc CQL và phiên bản Cassandra đang dùng.

## 8. Câu hỏi tự kiểm tra

1. Trong một BATCH có hai `UPDATE` cùng cột, cùng timestamp nhưng giá trị khác nhau, vì sao không thể dựa vào vị trí statement để xác định giá trị cuối?
2. Nếu một lệnh được gửi sau nhưng có timestamp thấp hơn lệnh trước, Cassandra sẽ ưu tiên giá trị nào khi hai lệnh cập nhật cùng ô?
3. `BEGIN BATCH USING TIMESTAMP ...` có chứng minh tất cả các statement chạy đồng thời hoặc reader khác chỉ thấy kết quả toàn phần không?
4. `WRITETIME(status)` chứng minh được điều gì; có thể dùng để tái dựng đầy đủ lịch sử chuyển trạng thái không?
5. Vì sao counter increment và retry sau timeout cần thiết kế khác một lệnh `SET status = 'PAID'`?

**Gợi ý đối chiếu:** (1) Timestamp/hòa giải quyết định kết quả, không có hợp đồng statement order; (2) timestamp cao hơn thường thắng; (3) không, atomicity không đồng nghĩa isolation hoặc order; (4) đọc metadata của giá trị hiện tại, không phải audit log; (5) increment có thể được áp dụng lại và thay đổi tổng.

## Kết luận

Trong Cassandra, **BATCH gom mutation, timestamp hỗ trợ hòa giải dữ liệu, còn thứ tự nghiệp vụ phải do mô hình dữ liệu và logic ứng dụng bảo đảm**. Khi cần biết bản ghi nào thắng, hãy xét **ô dữ liệu, timestamp và quy tắc conflict resolution**. Khi cần một chuỗi thao tác có ý nghĩa nghiệp vụ, hãy dùng version/sự kiện có thứ tự hoặc cơ chế điều kiện phù hợp, thay vì suy luận từ vị trí các câu lệnh trong `BEGIN BATCH ... APPLY BATCH`.

# Kiểm soát đồng thời bi quan và trường hợp nên dùng

**Kiểm soát đồng thời bi quan** (*pessimistic concurrency control*) là cách tổ chức giao dịch dựa trên giả định rằng xung đột có thể xảy ra và cần được ngăn chặn trước khi các giao dịch cùng thay đổi dữ liệu. Một giao dịch lấy khóa trên dữ liệu hoặc tài nguyên mà nó sắp sử dụng. Giao dịch khác muốn thực hiện thao tác không tương thích phải chờ, nhận lỗi hoặc chọn một tài nguyên khác.

Ví dụ, hai khách hàng cùng đặt chiếc ghế cuối cùng của một chuyến xe. Nếu cả hai cùng đọc số ghế còn trống rồi mới cập nhật, họ có thể cùng tin rằng ghế vẫn còn. Với cách kiểm soát bi quan, giao dịch đầu tiên khóa hàng biểu diễn số ghế trước khi kiểm tra và trừ số lượng. Giao dịch thứ hai phải chờ. Sau khi giao dịch đầu tiên kết thúc, giao dịch thứ hai mới tiếp tục và kiểm tra trạng thái mới nhất theo ngữ nghĩa của hệ quản trị.

Chiến lược này phù hợp khi xung đột có khả năng cao, dữ liệu khan hiếm hoặc chi phí phải hủy và chạy lại giao dịch rất lớn. Đổi lại, khóa làm giảm khả năng thực hiện song song, có thể tạo thời gian chờ và deadlock. Vì vậy, cần chọn đúng phạm vi khóa và giữ transaction ngắn.

## 1. Tư duy bi quan trong điều khiển tương tranh

Khi nhiều giao dịch truy cập cùng dữ liệu, hệ thống phải bảo đảm các thao tác xung đột không làm hỏng trạng thái chung. Có hai cách tiếp cận phổ biến:

- **Bi quan:** giả định xung đột có thể xảy ra. Giao dịch xin khóa trước hoặc trong lúc bước vào vùng dữ liệu cần bảo vệ. Giao dịch xung đột phải chờ hoặc thất bại.
- **Lạc quan:** cho phép nhiều giao dịch làm việc mà không giữ khóa loại trừ trong phần lớn thời gian. Khi ghi hoặc commit, hệ thống kiểm tra xem dữ liệu có bị thay đổi theo cách làm giao dịch mất hiệu lực hay không; nếu có, giao dịch có thể phải rollback và retry.

Kiểm soát bi quan thường dùng khóa chia sẻ và khóa độc quyền. Bộ quản lý khóa ghi nhận giao dịch nào đang giữ khóa, giao dịch nào đang chờ, và quyết định có thể cấp yêu cầu mới hay không.

Một nguyên tắc quan trọng là **phải lấy khóa trước khi dựa vào dữ liệu cần được bảo vệ để đưa ra quyết định**. Nếu ứng dụng đọc số lượng tồn kho mà không khóa, tính ra số lượng mới ở bộ nhớ, rồi chỉ xin khóa khi ghi, quyết định ban đầu vẫn có thể dựa trên một giá trị đã cũ.

## 2. Khóa chia sẻ và khóa độc quyền

Hai loại khóa cơ bản thường gặp trong cơ sở dữ liệu quan hệ:

- **Khóa chia sẻ (`S`, shared lock):** cho phép giao dịch đọc dữ liệu. Nhiều giao dịch có thể cùng giữ khóa chia sẻ trên một mục nếu không có khóa độc quyền đang chiếm dụng.
- **Khóa độc quyền (`X`, exclusive lock):** bảo vệ thao tác thay đổi dữ liệu. Khi một giao dịch giữ khóa độc quyền, giao dịch khác không thể đồng thời lấy khóa chia sẻ hoặc độc quyền không tương thích trên cùng mục.

Bảng tương thích cơ bản:

| Khóa đang được giữ | Yêu cầu `S` | Yêu cầu `X` |
|---|---:|---:|
| `S` | Được cấp | Phải chờ |
| `X` | Phải chờ | Phải chờ |

Ví dụ, `T1` giữ `S(A)` để đọc `A`. `T2` cũng có thể lấy `S(A)` để đọc. Nhưng nếu `T3` yêu cầu `X(A)` để cập nhật, `T3` phải chờ cho đến khi các khóa chia sẻ không tương thích được nhả. Ngược lại, khi `T1` giữ `X(A)`, cả yêu cầu đọc có khóa chia sẻ và yêu cầu ghi có khóa độc quyền của giao dịch khác đều phải chờ.

Một số hệ quản trị có thêm các chế độ khóa trung gian, khóa cập nhật (*update lock*), khóa ý định (*intention lock*) hoặc chế độ khóa riêng cho thao tác đọc. Tên gọi và ma trận tương thích chi tiết phụ thuộc engine. Bảng trên là mô hình nền tảng để hiểu khóa chia sẻ và độc quyền.

## 3. Lấy khóa tường minh bằng SQL

Trong cơ sở dữ liệu quan hệ, ứng dụng có thể yêu cầu khóa bằng câu lệnh đọc có khóa. Cú pháp phổ biến là `SELECT ... FOR UPDATE` để khóa các hàng được chọn nhằm chuẩn bị cập nhật.

Ví dụ, bảng `inventory` lưu số lượng sản phẩm:

| product_id | available |
|---:|---:|
| 501 | 3 |

Giao dịch đặt hàng có thể thực hiện:

```sql
BEGIN;

SELECT available
FROM inventory
WHERE product_id = 501
FOR UPDATE;

-- Ứng dụng kiểm tra available >= số lượng cần đặt.

UPDATE inventory
SET available = available - 2
WHERE product_id = 501;

COMMIT;
```

`FOR UPDATE` yêu cầu khóa các hàng phù hợp để những giao dịch khác muốn cập nhật hoặc lấy khóa xung đột trên các hàng đó phải chờ. Sau khi có khóa, giao dịch kiểm tra số lượng và thực hiện cập nhật trong cùng transaction. Khóa thường được giữ đến khi transaction commit hoặc rollback.

Nếu `T1` đã lấy khóa hàng sản phẩm `501`, `T2` muốn đặt cùng sản phẩm phải chờ. Sau khi `T1` commit, `T2` tiếp tục theo quy tắc đọc có khóa của hệ quản trị và kiểm tra số lượng còn lại. Nếu chỉ còn một sản phẩm, yêu cầu đặt hai sản phẩm phải bị từ chối.

Ví dụ trên là mẫu khái niệm. Cú pháp, thời điểm tạo snapshot, cách xử lý hàng đã bị giao dịch khác thay đổi và thời điểm khóa được nhả có thể khác giữa PostgreSQL, MySQL/InnoDB, SQL Server, Oracle và các hệ quản trị khác. Luôn kiểm tra tài liệu của engine và phiên bản đang dùng.

### Khóa chia sẻ cho vùng chỉ cần đọc ổn định

Một số hệ quản trị hỗ trợ cú pháp như `FOR SHARE` hoặc một dạng khóa chia sẻ tương đương. Nó hữu ích khi giao dịch cần đọc một hàng và bảo đảm hàng không bị giao dịch khác cập nhật hoặc xóa trong thời gian đang dựa vào giá trị đó.

Ví dụ, một giao dịch đọc trạng thái cấu hình quan trọng rồi thực hiện nhiều bước nghiệp vụ có thể lấy khóa chia sẻ trên hàng cấu hình. Các giao dịch khác vẫn có thể đọc tương thích, nhưng cập nhật cấu hình phải chờ.

Không phải mọi lần đọc đều cần khóa chia sẻ tường minh. MVCC cho phép nhiều truy vấn đọc thông thường không chặn giao dịch ghi trong nhiều hệ quản trị. Chỉ dùng locking read khi ứng dụng thực sự cần bảo vệ điều kiện hoặc trạng thái giữa thời điểm đọc và thời điểm hoàn tất công việc.

## 4. Ví dụ nghiệp vụ: đặt hàng và trừ tồn kho

Giả sử sản phẩm chỉ còn `3` đơn vị. Hai giao dịch đồng thời muốn đặt mỗi giao dịch `2` đơn vị. Quy tắc nghiệp vụ là không được để tồn kho âm và không được xác nhận đơn hàng vượt số lượng có sẵn.

### Nếu đọc mà không khóa

Một cách triển khai không an toàn:

```text
T1: đọc available = 3
T2: đọc available = 3
T1: kiểm tra 3 >= 2, hợp lệ
T2: kiểm tra 3 >= 2, hợp lệ
T1: ghi available = 1
T2: ghi available = 1
T1: xác nhận đặt 2 sản phẩm
T2: xác nhận đặt 2 sản phẩm
```

Hai đơn hàng được xác nhận tổng cộng bốn sản phẩm trong khi kho chỉ có ba. Nếu cả hai giao dịch ghi `available = 1`, một cập nhật có thể ghi đè cập nhật còn lại; nếu hệ thống trừ số lượng theo cách khác, số tồn có thể âm hoặc trạng thái đơn hàng vẫn vượt hàng có sẵn. Vấn đề bắt nguồn từ việc hai quyết định cùng dựa trên số lượng cũ.

### Dùng khóa bi quan

```text
T1: BEGIN
T1: lấy X lock trên hàng inventory(501)
T1: đọc available = 3
T1: kiểm tra 3 >= 2
T1: cập nhật available = 1

T2: BEGIN
T2: yêu cầu X lock trên inventory(501) -> phải chờ

T1: COMMIT -> nhả khóa

T2: được cấp khóa
T2: đọc trạng thái mới theo locking-read semantics -> available = 1
T2: kiểm tra 1 >= 2 -> không hợp lệ
T2: ROLLBACK
```

Chỉ một giao dịch đặt hàng thành công. Giao dịch thứ hai đọc trạng thái sau khi giao dịch thứ nhất hoàn tất và từ chối yêu cầu không đủ hàng.

Điều quan trọng là khóa, đọc, kiểm tra và cập nhật phải nằm trong cùng transaction. Nếu ứng dụng đọc trước transaction rồi mới mở transaction để khóa và ghi, nó đã bỏ lỡ phần cần được bảo vệ.

### Cập nhật có điều kiện như một cách bảo vệ nguyên tử

Với một số nghiệp vụ, có thể dùng một câu lệnh cập nhật có điều kiện:

```sql
UPDATE inventory
SET available = available - 2
WHERE product_id = 501
  AND available >= 2;
```

Ứng dụng kiểm tra số hàng được cập nhật:

- Một hàng được cập nhật: thao tác trừ kho thành công.
- Không có hàng được cập nhật: sản phẩm không tồn tại hoặc số lượng không đủ, cần xác định nguyên nhân theo mô hình dữ liệu.

Đây là một thao tác nguyên tử được cơ sở dữ liệu thực thi và có thể là lựa chọn đơn giản hơn cho một cập nhật đơn hàng. Nó vẫn dựa vào cơ chế khóa và kiểm tra điều kiện của engine; cần đặt việc tạo đơn hàng, ghi chi tiết đơn và trừ kho trong một transaction phù hợp để tránh trạng thái nửa chừng. Khi nghiệp vụ cần đọc nhiều hàng rồi quyết định dựa trên toàn bộ chúng, locking read tường minh có thể dễ kiểm soát hơn.

## 5. Khóa khi chuyển tiền giữa hai tài khoản

Chuyển tiền là ví dụ điển hình vì giao dịch cần kiểm tra số dư rồi cập nhật hai hàng. Giả sử `A` chuyển `100` cho `B`.

```sql
BEGIN;

SELECT id, balance
FROM accounts
WHERE id IN (10, 20)
ORDER BY id
FOR UPDATE;

-- Kiểm tra tài khoản tồn tại và tài khoản 10 có đủ số dư.

UPDATE accounts
SET balance = balance - 100
WHERE id = 10;

UPDATE accounts
SET balance = balance + 100
WHERE id = 20;

COMMIT;
```

Hai hàng tài khoản được khóa trước khi ứng dụng kiểm tra và cập nhật. Giao dịch khác muốn chuyển tiền từ hoặc đến một trong hai tài khoản phải chờ khóa xung đột.

### Vì sao cần thứ tự khóa nhất quán?

Nếu một giao dịch chuyển từ `A` sang `B` và giao dịch khác chuyển từ `B` sang `A`, thứ tự lấy khóa khác nhau có thể tạo deadlock:

```text
T1 giữ X(A), chờ X(B)
T2 giữ X(B), chờ X(A)
```

Không giao dịch nào có thể tiếp tục nếu không có giao dịch bị hủy. Để giảm nguy cơ này, mọi luồng chuyển tiền nên khóa tài khoản theo cùng một thứ tự xác định, ví dụ tăng dần theo `account_id`, bất kể chiều chuyển tiền.

Sắp xếp thứ tự khóa làm giảm các chu trình chờ do những giao dịch cùng tập tài nguyên tạo ra. Nó không loại bỏ mọi deadlock, bởi một transaction có thể còn khóa thêm bảng hoặc tài nguyên khác. Vì vậy, hệ thống vẫn cần xử lý deadlock và có chính sách retry.

## 6. Phạm vi và mức độ khóa

Khóa có thể được áp dụng ở nhiều mức. Phạm vi khóa càng rộng thì càng dễ bảo vệ nhiều dữ liệu cùng lúc, nhưng càng có khả năng chặn những giao dịch không thực sự xung đột.

| Phạm vi | Mô tả | Khi hữu ích | Đánh đổi |
|---|---|---|---|
| Hàng (*row*) | Khóa một hoặc một số hàng cụ thể | Cập nhật tài khoản, tồn kho, đơn hàng | Cần truy vấn đúng hàng và hiểu index/predicate. |
| Trang (*page*) | Khóa một trang chứa nhiều hàng | Một số engine dùng để quản lý khóa hiệu quả | Có thể chặn giao dịch trên các hàng khác nhau cùng trang. |
| Bảng (*table*) | Khóa phạm vi toàn bảng hoặc chế độ khóa trên bảng | DDL, thao tác bảo trì hoặc thay đổi hàng loạt | Giảm mạnh khả năng song song. |
| Khoảng/predicate | Bảo vệ một khoảng khóa hoặc điều kiện truy vấn | Ngăn một số cạnh tranh liên quan đến phạm vi và hàng mới | Cách hỗ trợ phụ thuộc engine và isolation level. |
| Khóa tư vấn (*advisory lock*) | Khóa một mã logic do ứng dụng quy ước | Tài nguyên không ánh xạ trực tiếp thành một hàng | Chỉ hiệu quả nếu mọi bên liên quan cùng tuân thủ giao thức. |

### Khóa hàng

Khóa hàng thường phù hợp cho thao tác nghiệp vụ trên một thực thể. `SELECT ... FOR UPDATE` có thể khóa những hàng được truy vấn trả về. Tuy nhiên, số hàng thực tế bị khóa và khóa phụ trợ được lấy còn phụ thuộc execution plan, index, engine và isolation level.

Nếu truy vấn không có index phù hợp, hệ thống có thể phải quét nhiều dữ liệu và thời gian giữ khóa có thể tăng. Dùng điều kiện chọn lọc, index phù hợp và chỉ khóa những hàng cần thiết.

### Khóa bảng và khóa phạm vi

Khóa bảng có thể cần cho thao tác ảnh hưởng đến cấu trúc hoặc phần lớn dữ liệu, nhưng không nên dùng chỉ vì cú pháp đơn giản. Nó có thể làm các giao dịch độc lập phải chờ nhau.

Để bảo vệ điều kiện dạng “không có hàng nào thỏa điều kiện” hoặc “không được insert vào khoảng này”, khóa một hàng đang tồn tại chưa chắc đủ. Cần kiểm tra hỗ trợ range lock, gap lock, predicate lock, unique constraint hoặc Serializable của hệ quản trị. Một hàng chưa tồn tại không thể được khóa theo cách khóa hàng thông thường.

### Khóa tư vấn

Advisory lock bảo vệ một tài nguyên logic bằng khóa có mã do ứng dụng định nghĩa, ví dụ `customer:42` hoặc `monthly-report:2026-11`. Nó hữu ích khi không có một hàng cụ thể đại diện cho tài nguyên.

Advisory lock không tự động ngăn một chương trình khác ghi dữ liệu. Nếu một luồng không lấy cùng khóa tư vấn, nó vẫn có thể thay đổi tài nguyên. Vì vậy, khóa tư vấn chỉ bảo vệ được quy tắc khi mọi luồng ghi liên quan đều tuân thủ cùng giao thức. Cú pháp và phạm vi session/transaction của advisory lock khác nhau giữa các hệ quản trị.

## 7. Khóa bi quan trong quan hệ với MVCC và 2PL

MVCC và khóa bi quan không loại trừ nhau. Một hệ quản trị có thể dùng MVCC cho các truy vấn đọc thông thường, đồng thời cấp khóa cho `UPDATE`, `DELETE` hoặc locking read. Khi đó:

- Truy vấn đọc snapshot thông thường có thể đọc một phiên bản cũ phù hợp snapshot mà không phải chờ khóa ghi.
- Truy vấn `SELECT ... FOR UPDATE` yêu cầu quyền khóa trên các hàng được chọn và có thể phải chờ giao dịch đang giữ khóa không tương thích.
- Giao dịch ghi thường cần khóa độc quyền hoặc cơ chế đồng bộ tương đương để tránh hai thay đổi xung đột cùng được áp dụng không kiểm soát.

Vì vậy, không thể suy ra rằng “cơ sở dữ liệu dùng MVCC thì không có khóa”. MVCC quản lý phiên bản để hỗ trợ đọc nhất quán; khóa vẫn cần cho thao tác ghi, locking read và các quy tắc đồng bộ cụ thể.

2PL (*Two-Phase Locking*) là một giao thức quy định cách giao dịch lấy và nhả khóa: giai đoạn tăng trưởng chỉ lấy thêm khóa, giai đoạn thu hẹp chỉ nhả khóa. Nhiều hệ thống khóa bi quan dùng các biến thể của 2PL, đặc biệt là giữ khóa đến khi commit hoặc rollback. Tuy nhiên, hai khái niệm không hoàn toàn đồng nghĩa:

- **Kiểm soát bi quan** nói về chiến lược xử lý xung đột bằng cách khóa trước hoặc trong lúc truy cập.
- **2PL** là một quy tắc giao thức cụ thể về thứ tự lấy và nhả khóa.

Khi đọc tài liệu hệ quản trị, cần xem engine đang dùng giao thức và thời gian giữ khóa nào. Không nên mặc định mọi locking read đều có cùng hành vi ở mọi isolation level.

## 8. Chờ khóa, timeout và deadlock

Khóa bi quan có thể khiến một transaction bị chặn (*blocking*). Một giao dịch đang chờ không thể tiếp tục thao tác cần khóa cho đến khi khóa xung đột được nhả hoặc yêu cầu bị hủy.

Ví dụ:

```text
T1: BEGIN
T1: SELECT ... FOR UPDATE trên hàng A

T2: BEGIN
T2: SELECT ... FOR UPDATE trên hàng A -> WAIT

T1: COMMIT
T2: được tiếp tục hoặc nhận lỗi tùy engine và trạng thái hàng
```

Chờ khóa là hành vi bình thường khi có tranh chấp. Nhưng nếu transaction giữ khóa quá lâu, nhiều giao dịch khác có thể xếp hàng và làm giảm throughput.

### Deadlock

Deadlock xảy ra khi các giao dịch tạo thành một chu trình chờ. Mỗi giao dịch giữ một tài nguyên và chờ tài nguyên mà giao dịch khác đang giữ.

```text
T1 giữ A ───── chờ B
   ▲             │
   │             ▼
T2 chờ A ───── giữ B
```

Hệ quản trị thường phát hiện chu trình trong đồ thị chờ và chọn một transaction làm nạn nhân để hủy, giải phóng khóa cho transaction còn lại. Ứng dụng cần bắt lỗi deadlock, rollback transaction thất bại và cân nhắc retry toàn bộ công việc nếu thao tác có thể thực hiện lại an toàn.

### Lock timeout

Lock timeout xảy ra khi giao dịch chờ lâu hơn giới hạn được cấu hình. Timeout khác deadlock: deadlock có chu trình chờ, còn timeout chỉ cho biết yêu cầu đã chờ quá lâu. Khi timeout, phạm vi rollback phụ thuộc hệ quản trị và cấu hình; ứng dụng cần xác định transaction còn hoạt động hay đã bị hủy trước khi tiếp tục.

### NOWAIT và SKIP LOCKED

Một số hệ quản trị hỗ trợ tùy chọn tương tự:

- `NOWAIT`: nếu hàng cần khóa đang bị khóa không tương thích, trả lỗi ngay thay vì chờ. Phù hợp khi ứng dụng muốn phản hồi nhanh hoặc tự chọn phương án khác.
- `SKIP LOCKED`: bỏ qua các hàng hiện đang bị khóa và trả về những hàng có thể lấy khóa. Có thể dùng cho nhiều worker cùng lấy việc từ một hàng đợi.

Ví dụ ý tưởng cho worker xử lý job:

```sql
BEGIN;

SELECT id
FROM jobs
WHERE status = 'READY'
ORDER BY created_at
FOR UPDATE SKIP LOCKED
LIMIT 1;

-- Đánh dấu job được worker này nhận.
UPDATE jobs
SET status = 'RUNNING'
WHERE id = :job_id;

COMMIT;
```

Worker khác có thể bỏ qua job đang được worker đầu tiên khóa và lấy job khác. Cú pháp giới hạn, thứ tự `LIMIT` và vị trí mệnh đề khóa khác nhau giữa các engine.

`SKIP LOCKED` không tạo ra một góc nhìn đầy đủ, nhất quán về mọi hàng phù hợp. Nó cố ý bỏ qua một phần hàng đang bị khóa, nên phù hợp với hàng đợi hoặc tác vụ phân phối công việc, không phù hợp để tính tổng, kiểm tra đầy đủ một tập dữ liệu hoặc quyết định nghiệp vụ cần xét mọi hàng.

## 9. Khi nào nên dùng kiểm soát đồng thời bi quan?

Không có một mức xung đột duy nhất áp dụng cho mọi ứng dụng. Nên cân nhắc khóa bi quan khi có các dấu hiệu sau:

### Xung đột xảy ra thường xuyên

Nếu nhiều giao dịch liên tục cùng cập nhật một số hàng nóng, phần lớn giao dịch lạc quan có thể thất bại rồi phải chạy lại. Lấy khóa trước giúp xếp hàng các giao dịch ngay tại tài nguyên tranh chấp và tránh thực hiện nhiều công việc rồi mới phát hiện xung đột.

Ví dụ: nhiều nhân viên cùng xử lý một tài khoản, một sản phẩm có số lượng tồn rất thấp, hoặc một bản ghi đại diện cho trạng thái của một quy trình duy nhất.

### Chi phí rollback và retry cao

Một giao dịch có nhiều bước tính toán hoặc nhiều thao tác dữ liệu phụ thuộc vào kết quả đọc trước đó. Nếu xung đột được phát hiện ở cuối, phải chạy lại toàn bộ chuỗi thao tác. Khóa sớm có thể giảm số lần phải làm lại công việc.

Điều này chỉ có lợi khi thời gian giữ khóa vẫn đủ ngắn. Một transaction rất dài có thể khiến hàng loạt giao dịch khác chờ, và chi phí chờ còn lớn hơn chi phí retry.

### Tài nguyên khan hiếm hoặc có giới hạn cứng

Ví dụ:

- Ghế cuối cùng của chuyến bay hoặc sự kiện.
- Số lượng tồn kho giới hạn.
- Một khoản ngân sách hoặc hạn mức có thể bị tiêu thụ bởi nhiều yêu cầu đồng thời.
- Một job chỉ được một worker nhận tại một thời điểm.
- Một quy trình chỉ cho phép một lần chuyển trạng thái tại một thời điểm.

Với các tình huống này, khóa có thể giúp tuần tự hóa quyết định trên tài nguyên chung trước khi ứng dụng xác nhận kết quả.

### Quyết định phụ thuộc vào dữ liệu vừa đọc

Nếu giao dịch cần đọc một hoặc nhiều hàng, kiểm tra một điều kiện, rồi cập nhật dựa trên điều kiện đó, khóa trước khi đọc có thể bảo vệ khoảng thời gian giữa kiểm tra và ghi. Nếu chỉ khóa ở bước ghi, giao dịch có thể đã đưa ra quyết định từ một trạng thái cũ.

### Cần phân phối công việc giữa nhiều worker

Hàng đợi trong cơ sở dữ liệu có thể dùng locking read để worker lấy một job mà không cùng nhận một hàng. `SKIP LOCKED` là lựa chọn trong các hệ quản trị hỗ trợ khi mục tiêu là phân phối các hàng chưa bị worker khác khóa.

## 10. Khi nào không nên mặc định chọn khóa bi quan?

Khóa bi quan không phải giải pháp tốt nhất cho mọi trường hợp.

- **Xung đột hiếm:** nếu phần lớn giao dịch cập nhật các hàng khác nhau, giữ khóa trước có thể tạo overhead mà ít giúp giảm rollback. Cập nhật lạc quan với cột version hoặc kiểm tra điều kiện có thể phù hợp hơn.
- **Đọc nhiều, ghi ít:** truy vấn đọc snapshot thông thường của MVCC có thể chạy song song tốt mà không cần locking read. Khóa mọi hàng chỉ để đọc sẽ làm giảm khả năng song song không cần thiết.
- **Transaction kéo dài:** giữ khóa trong lúc gọi HTTP, gửi email, chờ người dùng hoặc chạy tính toán nặng làm các transaction khác bị chặn. Hãy thu hẹp phần cần khóa hoặc thiết kế lại quy trình.
- **Tài nguyên cực nóng:** nếu mọi giao dịch đều phải khóa một hàng duy nhất, hàng đó trở thành điểm nghẽn. Cần xem xét phân vùng, batching, cập nhật nguyên tử hoặc thiết kế lại dữ liệu.
- **Không kiểm soát được mọi bên ghi:** advisory lock hoặc khóa ứng dụng không bảo vệ dữ liệu nếu một service khác bỏ qua giao thức. Cần ràng buộc ở database hoặc bảo đảm mọi đường ghi dùng chung cơ chế.

Nếu dữ liệu ít tranh chấp và có thể phát hiện xung đột bằng version, cách lạc quan có thể đạt throughput tốt hơn. Nếu dữ liệu tranh chấp cao và quyết định cần bảo vệ trước khi ghi, cách bi quan thường dễ dự đoán hơn.

## 11. So sánh kiểm soát bi quan và lạc quan

| Tiêu chí | Bi quan | Lạc quan |
|---|---|---|
| Giả định | Xung đột có thể xảy ra, cần khóa trước | Xung đột đủ hiếm để kiểm tra sau |
| Cách xử lý | Lấy khóa; giao dịch xung đột chờ hoặc thất bại | Đọc/làm việc trước; xác thực version hoặc phụ thuộc khi ghi/commit |
| Chi phí chính | Chờ khóa, quản lý khóa, deadlock | Rollback, retry và công việc bị làm lại |
| Phù hợp | Tài nguyên nóng, xung đột cao, quyết định cần tuần tự hóa | Xung đột thấp, nhiều thao tác đọc, cập nhật độc lập |
| Rủi ro | Blocking, deadlock, lock contention | Retry liên tục khi tranh chấp cao, xử lý version conflict sai |
| Ví dụ | `SELECT ... FOR UPDATE` | `UPDATE ... WHERE version = :oldVersion` |

Một cách cập nhật lạc quan bằng version:

```sql
UPDATE documents
SET content = :newContent,
    version = version + 1
WHERE id = :id
  AND version = :oldVersion;
```

Nếu số hàng cập nhật bằng `0`, version đã thay đổi hoặc hàng không còn tồn tại; ứng dụng phải đọc lại và quyết định có retry hay báo xung đột. Đây là cơ chế phát hiện xung đột khi ghi, khác với việc khóa hàng trước khi đọc.

Hai cách tiếp cận cũng có thể kết hợp. Ví dụ, ứng dụng dùng MVCC cho đọc thông thường, dùng optimistic version cho phần lớn cập nhật, nhưng dùng `FOR UPDATE` cho một số quy trình cần khóa tài nguyên trước khi kiểm tra.

## 12. Những nguyên tắc triển khai an toàn

### Giữ transaction ngắn

Lấy khóa càng sớm trong vùng cần bảo vệ càng tốt, nhưng chỉ giữ khóa trong khoảng thời gian thực sự cần thiết. Không mở transaction rồi chờ người dùng xác nhận, gọi dịch vụ bên ngoài hoặc xử lý file lớn trước khi commit.

Một cấu trúc thường dễ quản lý:

```text
1. Chuẩn bị dữ liệu đầu vào ngoài transaction nếu có thể.
2. BEGIN.
3. Lấy các khóa cần thiết.
4. Đọc trạng thái đã được bảo vệ.
5. Kiểm tra bất biến nghiệp vụ.
6. Thực hiện các cập nhật liên quan.
7. COMMIT.
8. Thực hiện tác dụng phụ bên ngoài theo cơ chế phù hợp.
```

Nếu phải gửi thông điệp đồng bộ với transaction, cân nhắc transactional outbox thay vì gửi trực tiếp trước commit rồi gặp lỗi rollback.

### Lấy khóa theo thứ tự thống nhất

Nếu một transaction cần nhiều hàng, xác định thứ tự khóa ổn định, chẳng hạn theo loại tài nguyên rồi theo khóa chính tăng dần. Mọi luồng nghiệp vụ có thể khóa cùng tập dữ liệu nên tuân theo thứ tự đó để giảm deadlock.

### Chỉ khóa dữ liệu cần thiết

Truy vấn càng rộng, số hàng hoặc phạm vi khóa càng có thể lớn. Dùng index phù hợp, điều kiện rõ ràng và tránh khóa cả bảng khi chỉ cần một vài hàng. Kiểm tra execution plan và hành vi khóa thực tế của engine.

### Đặt timeout và xử lý lỗi

Thiết lập thời gian chờ phù hợp với SLA. Phân biệt lock timeout, deadlock, lỗi serialization và lỗi nghiệp vụ. Với lỗi yêu cầu hủy transaction, rollback đầy đủ rồi mới retry bằng transaction mới. Retry cần giới hạn số lần, có backoff khi phù hợp và không lặp tác dụng phụ ngoài database.

### Không nhầm khóa hàng với khóa điều kiện

Khóa một hàng hiện có không nhất thiết ngăn transaction khác insert một hàng mới thỏa cùng điều kiện truy vấn. Nếu cần bảo vệ quy tắc dạng “không có bản ghi trùng trong khoảng”, ưu tiên unique constraint khi có thể; nếu không, xem xét range/predicate lock hoặc Serializable theo khả năng của hệ quản trị.

### Kiểm tra hành vi ORM và connection pool

ORM có thể phát câu `SELECT` thường dù mã nguồn thể hiện ý định cập nhật, hoặc chỉ lấy khóa khi flush. Cần kiểm tra SQL thực tế và ranh giới transaction. Connection pool cũng phải trả connection về trạng thái transaction sạch; không để transaction hoặc khóa còn mở khi connection được tái sử dụng.

## 13. Cách phân tích một tình huống để chọn khóa bi quan

Khi thiết kế hoặc review một quy trình đồng thời, hãy trả lời lần lượt:

1. **Bất biến nào phải được bảo vệ?** Ví dụ số tồn không âm, không vượt sức chứa, không có hai người nhận cùng job.
2. **Những hàng hoặc tài nguyên nào quyết định bất biến?** Xác định hàng cụ thể, tập hàng, khoảng giá trị hay tài nguyên logic.
3. **Các giao dịch có thể xung đột ở đâu?** Xác định các thao tác đọc, ghi và thời điểm chúng chạy đồng thời.
4. **Có thể lấy khóa trước khi ra quyết định không?** Nếu chỉ khóa ở bước ghi, dữ liệu đọc trước đó có thể đã cũ.
5. **Phạm vi khóa nhỏ nhất đủ bảo vệ là gì?** Chọn hàng, phạm vi, bảng hoặc khóa tư vấn dựa trên semantics của engine.
6. **Thứ tự lấy khóa có thống nhất không?** Nếu có nhiều tài nguyên, xác định thứ tự chung để giảm deadlock.
7. **Ứng dụng xử lý chờ và lỗi ra sao?** Có timeout, rollback, retry và log để điều tra không?
8. **Có thể dùng constraint hoặc cập nhật nguyên tử thay cho khóa tường minh không?** Để database thực thi quy tắc ở nơi phù hợp nhất.
9. **Cần test cạnh tranh nào?** Dùng hai hoặc nhiều connection độc lập và barrier để tái hiện chính xác thời điểm đọc, khóa, ghi và commit.

Một bài test chỉ chạy các giao dịch lần lượt không chứng minh được cơ chế khóa hoạt động đúng khi có tranh chấp. Cần điều khiển thứ tự chạy và xác nhận giao dịch thứ hai thực sự phải chờ hoặc nhận kết quả xung đột theo thiết kế.

## 14. Kết luận

Kiểm soát đồng thời bi quan dùng khóa để bảo vệ dữ liệu trước khi giao dịch đưa ra quyết định hoặc thực hiện thay đổi. Nó đặc biệt hữu ích khi nhiều giao dịch cùng tranh chấp một tài nguyên, khi dữ liệu khan hiếm hoặc khi chi phí rollback và retry cao. `SELECT ... FOR UPDATE`, khóa chia sẻ, khóa phạm vi và khóa tư vấn là những công cụ có thể dùng tùy theo hệ quản trị và loại bất biến cần bảo vệ.

Khóa cũng tạo ra chi phí: giao dịch phải chờ, deadlock có thể xuất hiện và một hàng nóng có thể trở thành nút thắt hiệu năng. Thiết kế tốt cần xác định đúng dữ liệu cần bảo vệ, lấy khóa trước khi dựa vào dữ liệu đó, giữ transaction ngắn, thống nhất thứ tự lấy khóa và xử lý timeout/deadlock bằng rollback cùng retry an toàn. Khi xung đột hiếm, cập nhật lạc quan hoặc câu lệnh cập nhật nguyên tử có thể phù hợp hơn. Quyết định cuối cùng nên dựa trên tần suất tranh chấp, bất biến nghiệp vụ, ngữ nghĩa khóa của hệ quản trị và kết quả kiểm thử đồng thời.

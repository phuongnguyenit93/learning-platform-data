# Bế tắc do nâng cấp khóa hoặc tương tác chỉ mục

Deadlock (*bế tắc*) xảy ra khi một nhóm transaction tạo thành chu trình chờ: mỗi transaction đang giữ một tài nguyên mà transaction khác cần, đồng thời lại chờ tài nguyên do transaction kia giữ. Hệ quản trị cơ sở dữ liệu thường phát hiện chu trình và hủy một transaction làm nạn nhân để giải phóng khóa.

Không phải mọi lần chờ khóa đều là deadlock. Nếu `T2` chỉ chờ khóa mà `T1` đang giữ và `T1` có thể tiếp tục rồi commit, hệ thống chỉ đang có blocking. Deadlock xuất hiện khi các quan hệ chờ tạo thành chu trình không thể tự tháo gỡ.

Hai nguồn deadlock dễ gây bất ngờ là **nâng cấp khóa** và **tương tác giữa nhiều chỉ mục**. Nâng cấp khóa có thể tạo chu trình khi nhiều transaction cùng đọc bằng khóa chia sẻ rồi cùng muốn chuyển sang khóa độc quyền. Chỉ mục có thể bổ sung các tài nguyên khóa ngoài hàng mà câu lệnh có vẻ đang thao tác: khóa trên khóa chính, khóa trên chỉ mục phụ, khoảng khóa, khóa kiểm tra duy nhất hoặc khóa phục vụ foreign key.

Muốn xử lý đúng, cần xem deadlock graph hoặc thông tin chờ của hệ quản trị để biết transaction đang giữ và chờ tài nguyên nào. Chỉ nhìn hai câu SQL ở tầng ứng dụng thường chưa đủ để xác định nguyên nhân.

## 1. Deadlock và đồ thị chờ

Một transaction có thể giữ nhiều khóa cùng lúc. Khi cần khóa không tương thích đang được transaction khác giữ, nó phải chờ. Hệ quản trị biểu diễn quan hệ này bằng **đồ thị chờ** (*wait-for graph*):

- Mỗi transaction là một đỉnh.
- Có cạnh `Ti → Tj` nếu `Ti` đang chờ tài nguyên do `Tj` giữ.
- Nếu đồ thị có chu trình, các transaction trong chu trình đang deadlock.

Ví dụ:

```text
T1 giữ khóa A, chờ khóa B
T2 giữ khóa B, chờ khóa A

T1 ───── chờ B ─────> T2
 ^                       |
 |                       |
 +────── chờ A ──────────+
```

`T1` không thể lấy `B` trước khi `T2` nhả khóa; `T2` cũng không thể lấy `A` trước khi `T1` nhả khóa. Không transaction nào tự tiến lên để nhả tài nguyên. Database phải phát hiện chu trình và chọn một transaction rollback.

Transaction bị chọn làm nạn nhân có thể nhận lỗi deadlock hoặc serialization tùy hệ quản trị. Transaction còn lại tiếp tục sau khi khóa được giải phóng. Ứng dụng cần rollback phần công việc thất bại và quyết định có retry toàn bộ transaction hay trả lỗi cho caller.

## 2. Deadlock do nâng cấp khóa chia sẻ lên độc quyền

### Tình huống đọc trước, ghi sau

Một giao dịch có thể lấy khóa chia sẻ `S(A)` để đọc hàng `A`. Sau khi kiểm tra dữ liệu, nó quyết định cập nhật và cần khóa độc quyền `X(A)`. Quá trình chuyển từ `S` sang `X` được gọi là **nâng cấp khóa** (*lock upgrade* hoặc lock conversion).

Nếu chỉ có một transaction giữ `S(A)`, nó có thể nâng cấp khi không còn khóa không tương thích khác. Nhưng nếu hai transaction cùng giữ khóa chia sẻ trên `A`, cả hai đều có thể chờ nhau:

```text
T1: lấy S(A)
T2: lấy S(A)             -- S tương thích với S

T1: yêu cầu nâng cấp X(A) -- phải chờ T2 nhả S(A)
T2: yêu cầu nâng cấp X(A) -- phải chờ T1 nhả S(A)
```

Trạng thái khóa:

| Transaction | Đang giữ | Đang chờ |
|---|---|---|
| `T1` | `S(A)` | Nâng cấp lên `X(A)` |
| `T2` | `S(A)` | Nâng cấp lên `X(A)` |

Hai yêu cầu nâng cấp không thể cùng được cấp. `T1` không nhả `S(A)` vì nó đang chờ `T2`; `T2` cũng không nhả `S(A)` vì đang chờ `T1`. Đây là **conversion deadlock**.

Một lock manager có thể xử lý yêu cầu nâng cấp bằng hàng đợi conversion và quy tắc ưu tiên riêng. Chi tiết ai bị chặn trước hoặc ai trở thành deadlock victim phụ thuộc engine. Nhưng nguyên nhân logic vẫn là hai transaction cùng giữ khóa đọc và cùng cần quyền ghi độc quyền trên một tài nguyên.

### Ví dụ SQL mang tính khái niệm

Giả sử hai transaction cần đọc số dư rồi cập nhật cùng tài khoản:

```sql
-- T1
BEGIN;
SELECT balance
FROM accounts
WHERE id = 10
FOR SHARE;

-- Sau khi kiểm tra, T1 muốn cập nhật hàng.
UPDATE accounts
SET balance = balance - 10
WHERE id = 10;
```

```sql
-- T2 chạy gần như đồng thời
BEGIN;
SELECT balance
FROM accounts
WHERE id = 10
FOR SHARE;

UPDATE accounts
SET balance = balance - 20
WHERE id = 10;
```

Nếu cả hai locking read cùng giữ khóa chia sẻ đến khi transaction kết thúc và việc ghi cần nâng cấp lên khóa độc quyền, hai transaction có thể tạo deadlock. Đây là ví dụ về mô hình khóa; cú pháp `FOR SHARE`, loại khóa được lấy và cách engine xử lý chuyển đổi khác nhau giữa PostgreSQL, MySQL/InnoDB, Oracle và các hệ quản trị khác.

### Phân biệt upgrade deadlock với blocking thông thường

Nếu chỉ có `T1` giữ `S(A)` và `T2` yêu cầu `X(A)`, `T2` phải chờ. Khi `T1` kết thúc và nhả `S(A)`, `T2` có thể lấy `X(A)`. Không có chu trình chờ nên đây là blocking, không phải deadlock.

Deadlock xuất hiện khi `T1` cũng đang giữ một khóa mà `T2` cần, hoặc hai transaction cùng giữ `S(A)` rồi cùng chờ nâng cấp. Vì vậy, cần xem toàn bộ tập khóa đang giữ, không chỉ khóa mà câu lệnh hiện tại đang yêu cầu.

## 3. Cách giảm deadlock do nâng cấp khóa

### Xin quyền ghi ngay từ đầu nếu đã biết sẽ cập nhật

Nếu nghiệp vụ chắc chắn cần sửa hàng, hãy dùng thao tác lấy khóa ghi ngay từ đầu thay vì đọc bằng khóa chia sẻ rồi nâng cấp muộn. Ví dụ, dùng locking read dành cho cập nhật như `SELECT ... FOR UPDATE` trên những hệ quản trị hỗ trợ, sau đó mới kiểm tra và cập nhật.

```sql
BEGIN;

SELECT balance
FROM accounts
WHERE id = 10
FOR UPDATE;

-- Kiểm tra điều kiện trên hàng đã được khóa.
UPDATE accounts
SET balance = balance - 10
WHERE id = 10;

COMMIT;
```

Giao dịch thứ hai phải chờ ngay tại bước lấy khóa ghi. Nó không cùng giữ khóa chia sẻ trên hàng rồi cùng cố nâng cấp. Cách này giảm conversion deadlock, nhưng có thể tăng thời gian chờ vì khóa độc quyền được lấy sớm hơn. Chỉ khóa những hàng thực sự cần cập nhật và giữ transaction ngắn.

### Dùng update lock nếu hệ quản trị hỗ trợ

Một số hệ quản trị có chế độ **update lock** (`U`) để hỗ trợ mẫu đọc rồi cập nhật. Trong SQL Server, khóa `U` tương thích với khóa chia sẻ nhưng không tương thích với một khóa `U` khác trên cùng tài nguyên. Khi transaction chuyển từ `U` sang `X`, hệ thống tránh được tình huống hai transaction cùng giữ `S` rồi cùng đòi chuyển lên `X` theo mẫu thông thường.

Ví dụ theo SQL Server:

```sql
BEGIN TRANSACTION;

SELECT balance
FROM dbo.accounts WITH (UPDLOCK)
WHERE id = 10;

UPDATE dbo.accounts
SET balance = balance - 10
WHERE id = 10;

COMMIT TRANSACTION;
```

`UPDLOCK` là hint riêng của SQL Server, không phải cú pháp SQL portable. Nó cũng không loại bỏ mọi deadlock: transaction vẫn có thể giữ các khóa khác theo thứ tự khác nhau, hoặc tranh chấp chỉ mục và tài nguyên khác. Cần kiểm tra hint, isolation level và execution plan thực tế trước khi áp dụng.

### Dùng cập nhật nguyên tử nếu không cần đọc riêng trước đó

Nếu thao tác có thể biểu diễn thành một câu lệnh có điều kiện, hãy để database kiểm tra và thay đổi dữ liệu trong cùng câu lệnh:

```sql
UPDATE accounts
SET balance = balance - 10
WHERE id = 10
  AND balance >= 10;
```

Ứng dụng kiểm tra số hàng bị ảnh hưởng. Nếu một hàng được cập nhật, thao tác trừ tiền đã thỏa điều kiện tại thời điểm cập nhật. Nếu không có hàng nào, tài khoản không tồn tại hoặc số dư không đủ.

Mẫu này loại bỏ bước đọc có khóa chia sẻ rồi nâng cấp, nhưng vẫn có thể phải chờ khóa ghi và vẫn có thể deadlock với transaction khác đang cập nhật nhiều hàng theo thứ tự khác nhau. Nếu nghiệp vụ cần đọc nhiều dữ liệu trước khi quyết định, không nên ép tất cả logic vào một câu lệnh thiếu rõ ràng; hãy thiết kế transaction và thứ tự khóa phù hợp.

### Không giữ khóa đọc lâu rồi mới quyết định ghi

Tránh mở transaction, lấy khóa chia sẻ, thực hiện nhiều tính toán hoặc gọi dịch vụ bên ngoài, rồi mới nâng cấp khóa. Trong thời gian đó, transaction khác có thể lấy các khóa tương thích và sau đó cũng muốn ghi.

Chuẩn bị dữ liệu không cần transaction trước; mở transaction ngay trước vùng cần bảo vệ; lấy khóa phù hợp; kiểm tra và cập nhật; commit sớm.

## 4. Deadlock do thứ tự truy cập hàng và chỉ mục

Một câu `UPDATE` có thể làm thay đổi nhiều cấu trúc nội bộ. Ngoài hàng trong bảng, database có thể phải cập nhật chỉ mục chính, chỉ mục phụ, kiểm tra unique key, kiểm tra foreign key hoặc khóa các mục chỉ mục liên quan đến điều kiện truy vấn.

Vì vậy, hai câu lệnh cập nhật hai hàng có vẻ độc lập ở tầng ứng dụng vẫn có thể chờ các tài nguyên chỉ mục theo thứ tự khác nhau.

### Hai transaction cập nhật nhiều hàng theo thứ tự ngược nhau

Giả sử bảng `accounts` có chỉ mục chính trên `id` và chỉ mục phụ trên `customer_group`. Hai transaction cần cập nhật tài khoản `10` và `20`:

```text
T1: cập nhật account 10
    giữ khóa trên hàng/index entry liên quan đến 10
T2: cập nhật account 20
    giữ khóa trên hàng/index entry liên quan đến 20

T1: tiếp tục cập nhật account 20 -> chờ T2
T2: tiếp tục cập nhật account 10 -> chờ T1
```

Đồ thị chờ có chu trình. Deadlock có thể xuất hiện dù mỗi transaction đều thực hiện các câu lệnh hợp lệ.

Nếu hai transaction luôn truy cập cùng tập tài khoản theo một thứ tự xác định, ví dụ `id` tăng dần, cả hai sẽ tranh chấp cùng tài nguyên đầu tiên. Một transaction có thể chờ trước khi giữ tài nguyên tiếp theo, giúp tránh chu trình do thứ tự ngược.

```sql
SELECT id, balance
FROM accounts
WHERE id IN (10, 20)
ORDER BY id
FOR UPDATE;
```

Đây là cách thể hiện ý định khóa theo thứ tự. Tuy nhiên, không nên mặc định `ORDER BY` luôn quyết định hoàn toàn thứ tự khóa nội bộ: optimizer, kế hoạch truy vấn, loại index và engine có thể ảnh hưởng. Khi thứ tự khóa là điều kiện quan trọng, hãy kiểm tra execution plan và deadlock graph trên hệ quản trị thực tế; trong một số trường hợp, ứng dụng có thể phải lấy khóa từng hàng theo thứ tự rõ ràng.

### Chỉ mục phụ tạo thêm tài nguyên khóa

Một bảng có thể có:

- Chỉ mục clustered hoặc cấu trúc lưu hàng chính.
- Chỉ mục phụ trên email, trạng thái, ngày tạo hoặc khóa ngoại.
- Unique index để bảo vệ tính duy nhất.
- Chỉ mục ghép để hỗ trợ một truy vấn theo nhiều cột.

Khi `UPDATE` thay đổi một cột có index, database có thể phải xóa entry cũ và thêm entry mới. Khi `INSERT`, database phải thêm entry vào các chỉ mục liên quan và kiểm tra unique key. Khi `DELETE`, engine phải loại bỏ entry tương ứng. Những thao tác đó có thể cần khóa trên nhiều mục chỉ mục và hàng.

Một transaction có thể giữ khóa hàng rồi chờ entry trong chỉ mục phụ; transaction khác có thể đang giữ khóa trên entry khác và chờ hàng hoặc entry mà transaction đầu tiên giữ. Deadlock graph có thể hiển thị tài nguyên kiểu `KEY`, `RECORD`, `INDEX` hoặc mã nội bộ thay vì chỉ hiển thị tên hàng.

Đừng kết luận rằng chỉ mục tự nó là lỗi. Chỉ mục giúp truy vấn tìm ít hàng hơn, nhưng cũng làm tăng công việc ghi và số cấu trúc cần duy trì. Cần xem cả execution plan và các tài nguyên khóa thực tế.

## 5. Gap lock, next-key lock và insert intention trong InnoDB

MySQL InnoDB có các loại khóa liên quan đến khoảng trong chỉ mục. Chúng có thể khiến một transaction chờ hoặc deadlock ngay cả khi hai transaction không cập nhật cùng một hàng đã tồn tại.

### Record lock

Record lock khóa một bản ghi chỉ mục cụ thể. Với một truy vấn tìm hàng theo khóa chính, InnoDB có thể khóa record tương ứng tùy câu lệnh và isolation level.

### Gap lock

Gap lock bảo vệ khoảng giữa các giá trị chỉ mục, ngăn transaction khác insert một khóa mới vào khoảng đó trong các trường hợp engine cần bảo vệ. Đây là khóa trên khoảng chỉ mục, không phải một hàng dữ liệu cụ thể.

### Next-key lock

Next-key lock kết hợp record lock với gap lock liền trước record đó. Trong InnoDB, locking read, `UPDATE` hoặc `DELETE` quét một phạm vi index ở `REPEATABLE READ` có thể lấy next-key locks để bảo vệ các bản ghi và khoảng liên quan.

### Insert intention lock

Khi insert một giá trị mới, InnoDB có thể dùng insert intention lock trên khoảng mà giá trị mới sẽ nằm trong đó. Hai insert vào các vị trí khác nhau trong cùng gap có thể không chặn nhau chỉ vì cùng gap, nhưng chúng vẫn có thể bị chặn bởi gap lock hoặc xung đột với các kiểm tra khác.

### Vì sao hai insert có thể deadlock?

Một số lịch insert cạnh tranh có thể tạo ra quan hệ chờ phức tạp quanh gap, unique index hoặc khóa kiểm tra. Chẳng hạn, hai transaction cùng thực hiện locking read trên một phạm vi trống hoặc cùng giữ các khóa gap tương thích theo một tình huống cụ thể, rồi cả hai cùng insert vào khoảng đó. Các insert intention và quy tắc tương thích của InnoDB có thể dẫn đến chờ lẫn nhau.

Không nên suy luận rằng mọi insert cùng khoảng đều deadlock. Kết quả phụ thuộc index, giá trị được insert, loại khóa đã lấy, isolation level và thứ tự thao tác. Khi gặp deadlock InnoDB, cần đọc phần `LATEST DETECTED DEADLOCK` trong `SHOW ENGINE INNODB STATUS` hoặc dữ liệu Performance Schema để biết chính xác index và record/gap đang tranh chấp.

### Vai trò của index và isolation level

Trong InnoDB, truy vấn phạm vi dùng index nào ảnh hưởng đến record và gap được khóa. Nếu thiếu index phù hợp, engine có thể quét và khóa phạm vi rộng hơn, làm tăng cạnh tranh. Ở `READ COMMITTED`, InnoDB giảm hoặc không dùng nhiều gap locks cho các locking read thông thường so với `REPEATABLE READ`, nhưng vẫn có ngoại lệ, chẳng hạn kiểm tra foreign key và duplicate key. Không được xem đổi isolation level là giải pháp mặc định trước khi hiểu yêu cầu nhất quán.

## 6. Tương tác giữa chỉ mục và ràng buộc dữ liệu

Một số thao tác tạo khóa không rõ ràng từ câu SQL:

### Unique index

Khi insert hoặc cập nhật một giá trị có unique index, database phải kiểm tra không có hàng khác sử dụng cùng khóa duy nhất. Transaction có thể phải chờ một transaction khác đang tạo hoặc xóa entry trùng. Các kiểm tra này có thể tham gia deadlock với khóa trên hàng hoặc chỉ mục khác.

Ví dụ, transaction cập nhật email của user A và user B theo hai thứ tự khác nhau, trong khi email mới của mỗi người đang được transaction kia giải phóng. Unique index phải bảo đảm không có hai hàng cùng email; nếu các transaction đồng thời hoán đổi giá trị, thứ tự kiểm tra và khóa có thể tạo chờ hoặc lỗi unique. Cách an toàn thường là thiết kế thao tác đổi giá trị thành một quy trình có trạng thái trung gian hợp lệ hoặc dùng constraint có thể trì hoãn nếu engine hỗ trợ, thay vì giả định hai câu `UPDATE` riêng lẻ luôn hoán đổi được.

### Foreign key

Khi insert hoặc cập nhật khóa ngoại, database phải xác nhận hàng cha được tham chiếu tồn tại. Khi xóa hoặc cập nhật hàng cha, database phải kiểm tra các hàng con và thực hiện hành vi `RESTRICT`, `CASCADE` hoặc quy tắc tương ứng.

Các kiểm tra đó có thể cần khóa trên hàng/index entry của bảng cha và bảng con. Nếu hai transaction truy cập bảng theo thứ tự khác nhau, ví dụ một bên cập nhật bảng cha rồi bảng con còn bên kia cập nhật bảng con rồi bảng cha, deadlock có thể xuất hiện.

Để giảm nguy cơ, xác định thứ tự truy cập bảng và hàng nhất quán trong các luồng nghiệp vụ. Đồng thời bảo đảm cột foreign key có index phù hợp theo yêu cầu của engine; thiếu index có thể làm kiểm tra quan hệ phải quét nhiều hàng và tăng thời gian khóa.

### Chỉ mục trên cột lọc

Một truy vấn cập nhật theo điều kiện:

```sql
UPDATE orders
SET status = 'PROCESSING'
WHERE customer_id = 42
  AND status = 'READY';
```

có thể quét một vùng dữ liệu lớn nếu không có index phù hợp. Tùy engine và isolation level, phạm vi khóa có thể rộng hơn số hàng cuối cùng được cập nhật. Một index như `(customer_id, status)` có thể giúp tìm hàng mục tiêu nhanh hơn và thu hẹp lượng tài nguyên cần khóa.

Tuy nhiên, thêm index cũng làm mọi insert/update/delete phải duy trì thêm cấu trúc. Index mới có thể giảm lock footprint của truy vấn đọc/ghi theo predicate nhưng tăng chi phí ghi và số index entry tham gia transaction. Cần đo lường workload thực tế.

## 7. Deadlock trên chỉ mục khác với latch contention

Các hệ quản trị dùng cả **lock** ở mức transaction và **latch/lightweight lock** để bảo vệ cấu trúc nội bộ trong lúc truy cập bộ nhớ.

- Transaction lock bảo vệ quyền truy cập dữ liệu giữa các transaction và có thể được giữ đến commit hoặc rollback.
- Latch thường bảo vệ một cấu trúc bộ nhớ trong thời gian rất ngắn, chẳng hạn khi đọc hoặc thay đổi trang B-tree, cập nhật buffer hoặc thực hiện page split.

Một page split của B-tree có thể cần latch và gây chờ ngắn. Nhưng không nên gọi mọi latch wait là deadlock transaction. Latch contention thường được chẩn đoán bằng thống kê latch, wait event hoặc công cụ riêng của engine. Transaction deadlock được phân tích bằng chu trình chờ các lock resource.

Một số engine có thể phát hiện deadlock liên quan đến nhiều loại tài nguyên nội bộ, nhưng mô hình và công cụ chẩn đoán khác nhau. Khi deadlock report chỉ ra `KEY` hoặc index record, đó thường là transaction lock trên tài nguyên chỉ mục; khi báo cáo chỉ ra latch/page latch, cần xem cơ chế đồng bộ nội bộ tương ứng.

## 8. Cách đọc deadlock graph và thông tin chờ

Thông tin hữu ích nhất không chỉ là tên hai câu SQL. Hãy xác định:

1. **Victim:** transaction nào bị chọn làm nạn nhân và lỗi được trả về cho ứng dụng.
2. **Resource:** khóa đang tranh chấp là hàng, key trong index, page, table, gap hay tài nguyên khác.
3. **Owner:** transaction nào đang giữ khóa đó và ở chế độ nào.
4. **Waiter:** transaction nào yêu cầu khóa, chế độ khóa yêu cầu là gì.
5. **Statement:** câu SQL đang giữ khóa và câu SQL đang chờ khóa.
6. **Transaction scope:** transaction bắt đầu ở đâu, đã thực hiện các statement nào và giữ khóa bao lâu.
7. **Execution plan/index:** truy vấn dùng index nào, quét bao nhiêu hàng và có truy cập bảng theo thứ tự khác nhau không.

Một deadlock graph có thể cho thấy các statement khác nhau cùng tham gia chu trình. Ví dụ, câu `UPDATE` ở một transaction có thể giữ khóa trên hàng, trong khi một câu `INSERT` ở transaction kia đang chờ unique index; phần tiếp theo của transaction đầu lại cần index entry mà transaction kia giữ.

### SQL Server

SQL Server có thể ghi deadlock graph XML qua Extended Events, thường dùng session `system_health` hoặc một session chuyên biệt theo dõi sự kiện `xml_deadlock_report`. Graph cho biết process list, resource list, owner/waiter và statement liên quan. Với tài nguyên index, report có thể thể hiện `KEY`, `PAGE`, `OBJECT` và HoBT/index metadata.

### MySQL InnoDB

Có thể xem deadlock gần nhất bằng:

```sql
SHOW ENGINE INNODB STATUS;
```

Tìm phần `LATEST DETECTED DEADLOCK`, đọc hai transaction, câu lệnh, index, record/gap và transaction bị rollback. Với hệ thống cần quan sát thường xuyên, xem các bảng Performance Schema như `data_locks` và `data_lock_waits` theo phiên bản MySQL.

### PostgreSQL

PostgreSQL ghi lỗi deadlock vào server log khi phát hiện chu trình. Các cấu hình logging như `log_lock_waits` và `deadlock_timeout` giúp quan sát chờ khóa; thông tin process, transaction và câu lệnh trong log hỗ trợ truy ngược. Có thể xem `pg_locks` kết hợp `pg_stat_activity` để điều tra các phiên đang chờ.

Các ví dụ trên là công cụ theo từng sản phẩm. Không dùng tên tài nguyên hoặc mã khóa của một engine để diễn giải trực tiếp báo cáo của engine khác.

## 9. Quy trình xử lý deadlock do nâng cấp khóa hoặc chỉ mục

Khi deadlock xuất hiện, hãy làm theo trình tự có bằng chứng:

### Bước 1: Thu thập deadlock report

Lưu graph hoặc log gồm transaction victim, statement, resource, owner và waiter. Ghi lại thời điểm, isolation level, schema/index và phiên bản hệ quản trị.

### Bước 2: Xác định chu trình thực tế

Vẽ lại các quan hệ:

```text
T1 giữ resource R1 -> chờ R2
T2 giữ resource R2 -> chờ R1
```

Nếu cùng một hàng xuất hiện với `S` và `X`, xem xét conversion deadlock. Nếu tài nguyên là key/index/gap, tìm thao tác insert/update/delete và index liên quan. Nếu chu trình đi qua nhiều bảng, xem thứ tự truy cập bảng và foreign key.

### Bước 3: Kiểm tra kế hoạch truy vấn

Xem index được dùng, số hàng quét, thứ tự join, phạm vi predicate và số hàng bị khóa. Một thay đổi execution plan có thể làm thứ tự truy cập hoặc phạm vi khóa thay đổi dù câu SQL không đổi.

### Bước 4: Chọn thay đổi nhỏ nhất bảo vệ đúng bất biến

Các hướng thường dùng:

- Lấy khóa ghi ngay từ đầu nếu transaction chắc chắn cập nhật.
- Dùng update lock nếu engine hỗ trợ và mẫu truy cập phù hợp.
- Thống nhất thứ tự lấy khóa trên nhiều hàng và bảng.
- Thu hẹp predicate và tạo index phù hợp để giảm số hàng phải quét.
- Giảm số index không cần thiết, nhưng chỉ sau khi đo tác động truy vấn và ghi.
- Dùng cập nhật nguyên tử có điều kiện nếu nghiệp vụ có thể biểu diễn an toàn.
- Rút ngắn transaction và không gọi dịch vụ ngoài khi đang giữ khóa.

Không nên chỉ tăng timeout để “sửa” deadlock. Timeout giúp giới hạn thời gian chờ nhưng không loại bỏ chu trình. Cũng không nên tắt deadlock detection hoặc giảm isolation level khi chưa xác định bất biến cần bảo vệ.

### Bước 5: Kiểm thử lại dưới cạnh tranh

Tạo test với hai connection hoặc nhiều worker, điều khiển thứ tự bằng barrier/latch để tái hiện đúng lịch gây deadlock. Xác nhận:

- Chu trình không còn xuất hiện trong tình huống đã sửa.
- Bất biến nghiệp vụ vẫn được bảo vệ.
- Các transaction độc lập không bị chặn quá rộng.
- Deadlock còn lại (nếu có) được retry hoặc trả lỗi có kiểm soát.
- Hiệu năng không suy giảm quá mức do lấy khóa sớm hoặc index bổ sung.

## 10. Retry sau deadlock

Deadlock victim bị database rollback để giải phóng tài nguyên. Đây thường là lỗi tạm thời có thể thử lại, nhưng ứng dụng cần retry đúng phạm vi.

### Retry toàn bộ transaction

Một transaction có thể đã đọc dữ liệu, tính toán và thực hiện nhiều cập nhật trước khi deadlock được phát hiện. Sau rollback, không được chỉ chạy lại câu SQL cuối cùng bằng các giá trị đã tính từ snapshot cũ. Hãy bắt đầu transaction mới, đọc lại dữ liệu, kiểm tra lại bất biến và thực hiện lại toàn bộ quy trình.

```text
for attempt in bounded attempts:
    BEGIN transaction mới
        đọc dữ liệu hiện tại
        kiểm tra điều kiện nghiệp vụ
        thực hiện tất cả cập nhật
    COMMIT
    nếu thành công: kết thúc
    nếu deadlock victim: rollback nếu cần, chờ ngắn, thử transaction mới
    nếu lỗi nghiệp vụ/constraint: trả lỗi, không retry mù
```

Nên giới hạn số lần retry và dùng backoff có jitter để nhiều transaction không lập tức tranh chấp lại cùng lúc. Mức backoff phải phù hợp độ trễ và SLA của ứng dụng.

### Mã lỗi phụ thuộc hệ quản trị

Một số ví dụ:

- PostgreSQL thường dùng SQLSTATE `40P01` cho deadlock detected.
- MySQL/InnoDB thường trả error `1213` với SQLSTATE `40001` cho deadlock.
- SQL Server thường trả error `1205` khi transaction bị chọn làm deadlock victim.

Đây là các mã theo từng sản phẩm; cần kiểm tra driver và phiên bản cụ thể. Không nên bắt mọi lỗi `40001` hoặc mọi lỗi database rồi retry vô điều kiện, vì nhóm lỗi có thể bao gồm serialization failure hoặc những tình huống cần xử lý khác.

### Bảo vệ tác dụng phụ ngoài database

Nếu transaction gửi email, gọi HTTP hoặc phát thông điệp trước khi commit, deadlock rollback không thể tự hoàn tác tác dụng phụ bên ngoài. Retry có thể gửi lặp hoặc tạo tác dụng phụ hai lần.

Đặt tác dụng phụ sau commit khi có thể, hoặc dùng transactional outbox, idempotency key và cơ chế deduplication. Mục tiêu là transaction có thể chạy lại mà không nhân đôi hiệu ứng nghiệp vụ.

## 11. Những nguyên tắc phòng ngừa tổng quát

### Thống nhất thứ tự truy cập tài nguyên

Nếu nhiều luồng nghiệp vụ khóa cùng một tập hàng, hãy dùng cùng thứ tự khóa. Có thể quy định thứ tự theo loại bảng, khóa chính tăng dần hoặc một thứ tự nghiệp vụ rõ ràng. Đừng để luồng A khóa `account` rồi `ledger`, trong khi luồng B khóa `ledger` rồi `account`, nếu cả hai có thể chạy đồng thời.

### Khóa đúng chế độ ngay từ đầu

Biết chắc sẽ ghi thì lấy khóa dành cho cập nhật ngay từ đầu, thay vì cùng giữ khóa chia sẻ rồi nâng cấp. Không lấy khóa độc quyền quá sớm nếu chưa cần, vì điều đó làm tăng blocking.

### Giữ transaction ngắn

Không giữ transaction trong lúc chờ người dùng, gọi dịch vụ ngoài hoặc thực hiện tính toán dài. Chuẩn bị dữ liệu trước, mở transaction trong vùng cần bảo vệ, thực hiện thao tác và commit sớm.

### Tạo index theo truy vấn thực tế

Index phù hợp giúp giảm số hàng cần quét và có thể thu hẹp phạm vi khóa. Nhưng mỗi index cũng tăng chi phí duy trì khi ghi. Đánh giá bằng execution plan, thống kê truy vấn, deadlock graph và workload thực tế.

### Kiểm tra cả foreign key và unique index

Các ràng buộc giúp bảo vệ tính đúng đắn nhưng có thể tạo thêm khóa và thứ tự truy cập giữa bảng cha, bảng con hoặc index. Thiết kế luồng cập nhật nhất quán và kiểm thử các thao tác insert/delete/update đồng thời.

### Phân biệt deadlock với serialization failure

Một hệ quản trị dùng Serializable Snapshot Isolation có thể hủy transaction vì phát hiện chu trình phụ thuộc tuần tự hóa, dù không có transaction lock chờ theo kiểu deadlock truyền thống. Đây là serialization failure, không nhất thiết là lock deadlock. Ứng dụng có thể cần retry toàn bộ transaction trong cả hai trường hợp, nhưng chẩn đoán và mã lỗi khác nhau.

## 12. Kết luận

Deadlock do nâng cấp khóa thường xuất hiện khi nhiều transaction cùng giữ khóa chia sẻ trên một tài nguyên rồi cùng muốn chuyển sang khóa độc quyền. Nếu transaction đã biết sẽ cập nhật, lấy khóa ghi ngay từ đầu hoặc dùng update lock khi hệ quản trị hỗ trợ có thể tránh mẫu conversion deadlock đó.

Deadlock liên quan đến chỉ mục xuất hiện vì thao tác ghi có thể khóa nhiều tài nguyên: hàng, khóa chính, entry chỉ mục phụ, khoảng index, unique key hoặc hàng được kiểm tra qua foreign key. Thứ tự truy cập không nhất quán, truy vấn quét phạm vi rộng và các kiểm tra ràng buộc có thể tạo chu trình chờ. Cần đọc deadlock graph để xác định đúng resource, owner và waiter, rồi điều chỉnh thứ tự khóa, phạm vi truy vấn, index hoặc transaction.

Retry có thể giúp giao dịch phục hồi sau khi bị chọn làm nạn nhân, nhưng phải bắt đầu transaction mới và tính toán lại từ dữ liệu mới. Thiết kế tốt kết hợp bất biến được bảo vệ, thứ tự truy cập ổn định, transaction ngắn, index phù hợp và xử lý lỗi có giới hạn. Như vậy hệ thống vừa duy trì tính đúng đắn vừa hạn chế deadlock và chi phí chờ khóa.

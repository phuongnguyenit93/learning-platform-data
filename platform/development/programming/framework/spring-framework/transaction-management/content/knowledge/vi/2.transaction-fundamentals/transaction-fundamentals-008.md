# Vai trò nhật ký, khóa và MVCC ở mức khái niệm

## 1. Ba cơ chế giải quyết ba nỗi lo khác nhau

Một giao dịch cơ sở dữ liệu có thể phải đối phó đồng thời với **mất điện/crash**, **hai người cùng sửa một bản ghi** và **một người đang đọc khi người khác đang ghi**. Đây là ba bài toán liên quan nhưng không giống nhau:

| Cơ chế | Câu hỏi mà cơ chế giải quyết chủ yếu | Đóng góp đối với giao dịch |
| --- | --- | --- |
| **Nhật ký giao dịch (transaction log, thường gắn với WAL)** | Nếu tiến trình chết giữa chừng hoặc dữ liệu còn trong bộ nhớ chưa kịp ghi xuống đĩa, làm sao khôi phục? | Nền tảng cho crash recovery, commit bền vững và việc khôi phục/hoàn tác tùy thiết kế hệ quản trị. |
| **Khóa (locking)** | Hai giao dịch cùng muốn thay đổi dữ liệu, ai được làm trước? | Phối hợp truy cập đồng thời, bảo vệ thay đổi đang diễn ra và hỗ trợ thực thi mức cô lập. |
| **MVCC (Multi-Version Concurrency Control)** | Khi dữ liệu đang được cập nhật, người đọc có thể thấy một phiên bản nhất quán mà không phải chờ mọi ghi không? | Quản lý nhiều phiên bản để phục vụ snapshot/consistent read và giảm xung đột giữa đọc và ghi. |

Điểm mấu chốt: **ba cơ chế không phải ba lựa chọn thay thế nhau**. Một hệ quản trị như PostgreSQL hay MySQL/InnoDB có thể sử dụng nhật ký, khóa và phiên bản dữ liệu *cùng lúc*. Chúng là cơ chế thực thi ở tầng database. Trong Spring Framework, `@Transactional` chủ yếu **xác định ranh giới transaction và yêu cầu commit/rollback**; Spring không tự tạo WAL, cơ chế khóa hay MVCC.

Để học theo đúng nguyên nhân, hãy dùng một bảng tài khoản:

~~~sql
CREATE TABLE tx_account_lab (
    id BIGINT PRIMARY KEY,
    balance BIGINT NOT NULL CHECK (balance >= 0)
);

INSERT INTO tx_account_lab(id, balance) VALUES
    (1, 1000),
    (2, 500);
~~~

Giả sử giao dịch T1 chuyển 100 từ tài khoản 1 sang tài khoản 2: T1 phải cập nhật cả hai hàng, sau đó commit; nếu có lỗi thì rollback cả hai. Cùng thời điểm, T2 có thể đọc hoặc sửa tài khoản 1.

### ACID nhìn từ ba cơ chế

- **Atomicity (nguyên tử):** nghiệp vụ không để lại trạng thái commit dở dang. Recovery, trạng thái transaction và khả năng undo/rollback của engine góp phần bảo đảm điều này.
- **Consistency (nhất quán):** sau transaction hợp lệ, các ràng buộc/điều kiện nghiệp vụ vẫn đúng. Database hỗ trợ bằng constraint và điều phối giao dịch, nhưng quy tắc nghiệp vụ vẫn phải được thiết kế.
- **Isolation (cô lập):** quyết định các transaction đồng thời được phép quan sát/tác động đến nhau thế nào. Khóa, MVCC và kiểm tra xung đột là các công cụ thực hiện.
- **Durability (bền vững):** sau khi hệ quản trị xác nhận commit, thay đổi được bảo vệ trước sự cố theo cam kết và cấu hình durability của nó; WAL/redo log là một thành phần quan trọng.

**Không suy ra một-một** rằng “log = Atomicity, lock = Isolation, MVCC = Consistency”. Thực tế các cơ chế phối hợp, và engine có thể triển khai khác nhau.

## 2. Nhật ký giao dịch: phục hồi khi có sự cố

### Vì sao không chỉ ghi trực tiếp trang dữ liệu?

Các hệ quản trị thường giữ các **trang dữ liệu (data pages)** trong bộ nhớ đệm để xử lý nhanh. Một câu `UPDATE` có thể đã thay đổi trang trong bộ nhớ, trong khi bản tương ứng trên đĩa chưa được ghi ngay. Nếu buộc mỗi lệnh chờ ghi toàn bộ trang dữ liệu xuống đĩa thì hiệu năng sẽ rất thấp.

Ý tưởng của **write-ahead logging (WAL)**: ghi thông tin cần thiết để **làm lại/khôi phục thay đổi** vào log theo quy tắc thứ tự trước khi ghi các trang dữ liệu liên quan ra vùng lưu trữ chính. Khi transaction commit, database thực hiện quy trình bảo đảm thông tin commit/redo đủ bền vững theo cấu hình trước khi xác nhận thành công với ứng dụng.

Hình dung:

~~~text
Ứng dụng: UPDATE / COMMIT
          |
          v
Database đổi trang dữ liệu trong RAM
          |
          +--> Ghi bản ghi thay đổi vào log (WAL/redo)
          |       |
          |       +--> log được flush bền vững theo điều kiện commit
          |
          +--> Trang dữ liệu có thể được flush xuống file dữ liệu về sau
          |
Crash/restart --> đọc thông tin recovery --> phục hồi trạng thái hợp lệ
~~~

Lược đồ này mang tính **khái niệm**: thứ tự, loại log record, cơ chế undo và điều kiện flush thực tế khác nhau giữa engine.

### Redo và undo trả lời hai câu hỏi khác nhau

- **Redo:** thay đổi **đã commit** nhưng trang dữ liệu tương ứng chưa ghi đủ xuống đĩa thì cần phục hồi thế nào? Engine có thể phát lại thông tin redo cần thiết.
- **Undo/rollback:** transaction **chưa commit hoặc bị hủy** đã làm thay đổi trung gian, vậy làm sao loại bỏ tác động chưa hợp lệ? Engine dùng thông tin phục hồi phiên bản cũ, trạng thái transaction hoặc cơ chế undo phù hợp.

Đừng hiểu rằng *mọi* hệ quản trị đều có hai file vật lý tên “redo.log” và “undo.log”. Chẳng hạn PostgreSQL dùng WAL để hỗ trợ redo/crash recovery và quản lý visibility/version cho MVCC; InnoDB có redo log cùng undo records với vai trò riêng. Cấu trúc recovery chính xác là đặc thù của engine.

### Ba thời điểm xảy ra sự cố

| Thời điểm sự cố | Kết quả cần hiểu |
| --- | --- |
| **Trước commit** | Transaction chưa được xác nhận; khi recovery, các thay đổi chưa commit không được hiển thị như dữ liệu commit hợp lệ. |
| **Commit đã được xác nhận và bảo đảm durable** | Recovery phải giữ được kết quả transaction dù một số data page chưa flush; đây là một mục đích của redo/WAL. |
| **Kết nối mất đúng lúc commit** | Client có thể **không biết** lệnh commit đã thành công hay chưa. Cần truy vấn trạng thái nghiệp vụ/idempotency khi thử lại; không đoán rằng cứ mất kết nối là rollback. |

Ví dụ tuần tự:

~~~sql
BEGIN;
UPDATE tx_account_lab SET balance = balance - 100 WHERE id = 1;
UPDATE tx_account_lab SET balance = balance + 100 WHERE id = 2;
COMMIT;
~~~

Nếu hệ thống dừng trước commit, nó không được phục hồi thành “tài khoản 1 mất 100 mà tài khoản 2 chưa nhận”. Nếu commit đã hoàn tất bền vững, engine có trách nhiệm khôi phục kết quả đã commit. **Lập trình viên không tự đọc WAL để rollback**; chỉ ra lệnh `ROLLBACK` (hoặc để Spring quyết định rollback), còn database thực hiện cơ chế phục hồi.

**Phân biệt nhật ký kỹ thuật và nhật ký nghiệp vụ:**

| Nhật ký kỹ thuật của database | Audit log / application log |
| --- | --- |
| Dùng cho crash recovery, replication hoặc cơ chế nội bộ tùy engine | Dùng để biết ai làm gì, thời điểm nào, quyết định nghiệp vụ nào |
| Thường là định dạng nội bộ, phục vụ engine | Thiết kế để ứng dụng/con người tra cứu và quản trị |
| Không mặc nhiên là lịch sử nghiệp vụ có thể đọc/giữ mãi | Không thay được WAL hay tự làm transaction bền vững |

Độ bền còn phụ thuộc cấu hình `fsync`/synchronous commit, phần cứng và cơ chế lưu trữ. Tắt hoặc giảm bảo đảm flush có thể đổi hiệu năng lấy rủi ro mất thay đổi mới xác nhận khi crash. Vì vậy không hứa “không bao giờ mất dữ liệu” chỉ vì đã bật transaction.

## 3. Khóa: điều phối khi nhiều giao dịch truy cập cùng dữ liệu

### Trường hợp hai giao dịch cùng UPDATE một hàng

T1 muốn trừ 100 từ tài khoản 1; T2 muốn trừ 10 cũng từ tài khoản 1. Nếu cả hai được ghi tùy ý mà không có điều phối, thứ tự cập nhật có thể làm mất thay đổi hoặc vi phạm điều kiện nghiệp vụ.

Trong nhiều relational database, lệnh `UPDATE` phải lấy **khóa phù hợp trên bản ghi hoặc tài nguyên liên quan**. Khi T1 đang giữ khóa ghi đối với hàng 1, thao tác ghi cạnh tranh của T2 thường phải **chờ** hoặc gặp lỗi xung đột/timeout tùy trường hợp. Một lịch đơn giản:

~~~text
Thời gian     T1 (connection 1)                T2 (connection 2)
---------     ------------------               ------------------
t1            BEGIN
t2            UPDATE account 1 (-100)
t3                                             BEGIN
t4                                             UPDATE account 1 (-10)
t5                                             -> phải đợi khóa
t6            COMMIT (nhả khóa)
t7                                             tiếp tục UPDATE
t8                                             COMMIT
~~~

Nếu cả hai lệnh được viết dạng tương đối `balance = balance - amount` và điều kiện đủ tiền được kiểm tra **trong SQL**, database có thể thực thi tuần tự hóa việc cập nhật hàng thích hợp. Dù vậy, **khóa không thể tự sửa thuật toán ứng dụng sai**: nếu client tính sẵn số dư từ một giá trị đọc cũ rồi `UPDATE balance = 990`, nó vẫn có thể ghi đè thay đổi mới hơn.

### Các loại khóa cần biết ở mức khái niệm

- **Shared/read lock:** cho phép nhiều người đọc đồng thời trong những cơ chế dùng read lock, nhưng có thể ngăn ghi không tương thích. Một `SELECT` bình thường dưới MVCC không nhất thiết lấy shared row lock.
- **Exclusive/write lock:** hạn chế tác vụ khác ghi/sửa tài nguyên đang được bảo vệ.
- **Row, table, page, key-range/predicate lock:** mức độ và mục đích khác nhau theo engine, câu SQL và isolation level. Khóa theo vùng/điều kiện còn giúp xử lý các tình huống như hàng mới xuất hiện trong phạm vi đang xét.
- **Locking read:** một số thao tác như `SELECT ... FOR UPDATE` chủ động yêu cầu khóa trước khi quyết định cập nhật; đây là loại đọc **có thể chờ khóa**, khác với đọc snapshot bình thường.

Các tên khóa và tính tương thích là chi tiết engine-specific. **Không mặc định mọi `SELECT` sẽ khóa hàng**, hay mọi khóa đều chỉ gắn với một hàng. Engine còn có metadata lock và các loại khóa nội bộ khác.

### Lock wait, timeout và deadlock

**Lock wait:** T2 tạm thời chờ T1 trả khóa. Điều này có thể bình thường, nhưng transaction quá dài sẽ tăng độ trễ và làm cạn connection pool.

**Deadlock:** T1 đã giữ khóa A và cần B; trong khi T2 giữ khóa B và cần A:

~~~text
T1: lock A ---- đợi B
                 ^   |
                 |   v
T2: đợi A <---- lock B
~~~

Cả hai không thể tiến tiếp theo thứ tự ấy. Database thường có cơ chế phát hiện/giải quyết deadlock, ví dụ hủy một transaction và báo lỗi để bên gọi **thử lại toàn bộ nghiệp vụ** theo chính sách phù hợp. Spring `@Transactional` **không tự động retry**. Tránh deadlock bằng cách giữ transaction ngắn, cập nhật nhiều tài nguyên theo thứ tự nhất quán và tránh chờ HTTP/network bên trong transaction.

### Khóa bi quan và kiểm tra phiên bản lạc quan

Khi dự đoán tranh chấp cao, ứng dụng có thể dùng **pessimistic locking** (`SELECT ... FOR UPDATE`) để giữ quyền cập nhật. Một hướng khác là **optimistic concurrency**: đọc một cột `version`, rồi chỉ cập nhật nếu version chưa đổi:

~~~sql
-- Khung ý tưởng: đã đọc version=7 trước đó
UPDATE inventory_item
SET quantity = quantity - 1,
    version = version + 1
WHERE id = 42 AND version = 7 AND quantity >= 1;
-- Nếu số hàng cập nhật = 0: dữ liệu/phiên bản đã đổi hoặc không đủ hàng;
-- cần xử lý xung đột, không được giả định ghi thành công.
~~~

Đây là ví dụ cú pháp trên một bảng minh họa có cột `id, quantity, version`. **Optimistic locking ở tầng ứng dụng không đồng nghĩa MVCC**, dù cả hai cùng có khái niệm “phiên bản”.

## 4. MVCC: nhiều phiên bản để đọc nhất quán

Nếu chỉ dùng khóa đọc/ghi chặt trên mọi thao tác, một giao dịch cập nhật lâu có thể làm nhiều truy vấn đọc phải chờ. **MVCC (Multi-Version Concurrency Control)** cho phép database quản lý các phiên bản của hàng để đọc theo một *snapshot hợp lệ*, thay vì nhất thiết nhìn bản đang được sửa hoặc chặn tất cả truy vấn đọc.

Ví dụ tài khoản 1 có số dư đã commit là 1.000:

~~~text
T0: bản đã commit                balance = 1000
T1: transaction A UPDATE -100    tạo trạng thái mới = 900 (chưa commit)
T2: transaction B SELECT         có thể đọc bản 1000 hợp lệ
T3: A COMMIT                     trạng thái 900 trở thành committed
T4: một SELECT có snapshot mới   có thể đọc 900
~~~

Ở PostgreSQL với `READ COMMITTED`, mỗi câu `SELECT` thông thường có snapshot riêng tại lúc bắt đầu câu lệnh. Vì vậy SELECT trước khi A commit có thể thấy 1.000; một câu SELECT mới sau khi A commit có thể thấy 900. Nếu đang dùng isolation cao hơn/snapshot cố định, **câu SELECT thứ hai không nhất thiết thấy 900**: quy tắc snapshot phụ thuộc engine và isolation.

### Snapshot trả lời “phiên bản nào được phép nhìn thấy?”

Database dùng thông tin về trạng thái/định danh transaction và thời điểm quan sát để quyết định phiên bản nào nhìn thấy được. Một bản cập nhật **chưa commit** của A không tự trở thành dữ liệu hợp lệ cho B chỉ vì nó đã nằm trong RAM.

- Người đọc có thể xem phiên bản **đã commit và phù hợp snapshot**.
- Transaction thường có thể thấy các thay đổi **do chính mình thực hiện**, kể cả chưa commit, theo ngữ nghĩa của engine.
- Khi một phiên bản không còn cần thiết cho bất kỳ snapshot đang sống nào, engine có thể thu dọn tài nguyên/version cũ bằng cơ chế riêng, ví dụ vacuum/purge.
- Transaction giữ lâu làm bản cũ phải tồn tại lâu hơn trong một số engine, tăng áp lực lưu trữ và việc dọn dẹp.

**MVCC không đồng nghĩa không dùng khóa.** MVCC thường giúp **read thường** và **write** ít chặn nhau hơn; nhưng hai transaction **cùng UPDATE** một hàng, hay `SELECT ... FOR UPDATE`, vẫn có thể đụng khóa. Một số engine còn dùng gap/next-key locks hoặc kiểm tra xung đột để đáp ứng chính sách isolation.

### MVCC có giải quyết mọi bất thường đồng thời?

**Không.** Đọc snapshot nhất quán của một câu lệnh chưa chứng minh rằng cả nghiệp vụ an toàn trước mọi concurrency anomaly.

Ví dụ **lost update do logic đọc-rồi-ghi**:

1. B đọc `balance = 1000`.
2. A giảm 100 và commit, đưa số dư về 900.
3. B dùng kết quả cũ để tính `1000 - 10 = 990` rồi gửi `UPDATE account SET balance = 990`.
4. Trong một số mức cô lập/engine, thao tác B có thể thành công sau khi chờ xung đột, làm mất phần giảm 100 của A.

Cách an toàn hơn với phép giảm số dư là cập nhật **tương đối, có điều kiện ngay trong SQL**:

~~~sql
UPDATE tx_account_lab
SET balance = balance - 10
WHERE id = 1 AND balance >= 10;
~~~

Kiểm tra số hàng cập nhật và xử lý trường hợp `0 rows`. Với bài toán phức tạp hơn, dùng locking read, optimistic version check, mức cô lập phù hợp và retry transaction khi có lỗi xung đột. **Snapshot nhất quán khi đọc** và **bất biến nghiệp vụ khi nhiều người ghi** là hai yêu cầu khác nhau.

## 5. Ba cơ chế phối hợp trong một transaction như thế nào?

Xét giao dịch A thực hiện hai `UPDATE` để chuyển 100 giữa tài khoản 1 và 2, đồng thời B muốn đọc và ghi tài khoản 1:

~~~text
               ┌─────────────────────── Database ───────────────────────┐
Spring service ─> Transaction boundary (BEGIN ... COMMIT / ROLLBACK)     │
               │                                                        │
               │  WAL / redo / recovery: giữ khả năng phục hồi sau crash │
               │  Locks: điều phối các UPDATE và xung đột đọc-ghi đặc biệt│
               │  MVCC: chọn phiên bản đọc hợp lệ theo snapshot          │
               │                                                        │
               └────────────────────────────────────────────────────────┘
~~~

Một diễn giải đúng ở mức khái niệm:

1. Khi A bắt đầu transaction, database thiết lập ngữ cảnh transaction. Spring chỉ yêu cầu hoặc tham gia transaction thích hợp.
2. Khi A cập nhật hàng 1 và 2, database phải quản lý thay đổi, thông tin phục hồi và các xung đột ghi (có thể bằng row locks/version checks).
3. B thực hiện `SELECT` thường có thể đọc phiên bản cũ đã commit theo snapshot, thay vì thấy nửa kết quả chưa commit của A.
4. Nếu B muốn `UPDATE` cùng hàng, nó có thể phải chờ A hoặc bị báo conflict.
5. A commit: engine áp dụng các bảo đảm WAL/recovery và công bố trạng thái commit theo quy tắc của nó; khóa ghi được giải phóng theo vòng đời transaction.
6. A rollback hoặc thất bại: các thay đổi chưa commit của A không được để lại như dữ liệu commit hợp lệ; những transaction khác tiếp tục theo quy tắc concurrency của engine.

**Điều được đảm bảo đến đâu còn phụ thuộc** loại giao dịch, isolation level, database, câu SQL và cấu hình bền vững. Không nên suy diễn chi tiết “tạo file log nào”, “khóa ở cấp nào”, “snapshot lúc nào” từ annotation Spring.

## 6. Thực hành quan sát bằng hai phiên PostgreSQL

Bài thực hành này cụ thể hóa sự phối hợp **MVCC cho SELECT** và **khóa cho UPDATE**. Dùng cơ sở dữ liệu PostgreSQL **thử nghiệm**, hai cửa sổ terminal mở hai kết nối `psql` độc lập; không chạy trên dữ liệu thật.

### Chuẩn bị một lần

Nếu đã có PostgreSQL local và quyền tạo database:

~~~bash
createdb tx_lab
psql -d tx_lab
~~~

Trong kết nối chuẩn bị, chạy:

~~~sql
CREATE TABLE tx_account_lab (
    id BIGINT PRIMARY KEY,
    balance BIGINT NOT NULL CHECK (balance >= 0)
);

INSERT INTO tx_account_lab(id, balance) VALUES (1, 1000), (2, 500);
~~~

Đóng hoặc để riêng kết nối chuẩn bị. Mở **hai terminal khác nhau**, cùng kết nối database:

~~~bash
psql -d tx_lab
~~~

### Phiên A: tạo bản cập nhật chưa commit

~~~sql
BEGIN ISOLATION LEVEL READ COMMITTED;
UPDATE tx_account_lab
SET balance = balance - 100
WHERE id = 1;
-- Chưa COMMIT ở thời điểm này.
~~~

A đang giữ transaction mở. Theo cách hoạt động của PostgreSQL, kết quả mới 900 của A chưa commit và các ghi cạnh tranh trên hàng 1 sẽ chịu điều phối khóa.

### Phiên B: đọc trước, rồi thử sửa

~~~sql
BEGIN ISOLATION LEVEL READ COMMITTED;
SELECT balance FROM tx_account_lab WHERE id = 1;
-- Kết quả mong đợi lúc A chưa commit: 1000.

UPDATE tx_account_lab
SET balance = balance - 10
WHERE id = 1;
-- Lệnh UPDATE sẽ chờ trong lúc A còn giữ xung đột trên hàng 1.
~~~

Trình tự quan sát:

- `SELECT` ở B vẫn đọc được 1.000 theo snapshot; đây là ví dụ về đọc không phải đợi commit của người ghi.
- `UPDATE` ở B **chờ** vì cả hai cùng muốn sửa hàng 1; MVCC không làm xung đột ghi biến mất.
- **Trong khi B đang chờ**, quay lại terminal A và chạy `COMMIT;`.
- B tiếp tục hoàn thành lệnh `UPDATE`; sau đó tại B chạy `COMMIT;` và `SELECT balance FROM tx_account_lab WHERE id = 1;`.

Với trình tự trên và không có thao tác thứ ba, **kết quả cuối ở PostgreSQL là 890** (1.000 − 100 − 10). PostgreSQL cập nhật dựa trên giá trị hàng hiện hành phù hợp với ngữ nghĩa `UPDATE` ở `READ COMMITTED`; lệnh tương đối không mất phép trừ của A.

**Thử lại đối chứng:** dùng database thử nghiệm mới (hoặc đưa số dư về 1.000 sau khi đã kết thúc mọi transaction), rồi để B đọc 1.000 và chuẩn bị `UPDATE tx_account_lab SET balance = 990 WHERE id = 1;`. Lệnh ghi một **giá trị tính sẵn từ đọc cũ** có thể ghi đè cập nhật 900 của A sau khi A commit. Chính logic đọc-rồi-ghi là nguy hiểm; khóa chờ một mình không đủ để giữ ý nghĩa của phép tính ở client.

### Quan sát rollback

Sau khi tất cả phiên đã commit và không còn transaction đang chờ, tại một phiên:

~~~sql
SELECT balance FROM tx_account_lab WHERE id = 1;
-- 890 theo kịch bản ở trên.

BEGIN;
UPDATE tx_account_lab SET balance = balance - 50 WHERE id = 1;
ROLLBACK;

SELECT balance FROM tx_account_lab WHERE id = 1;
-- Vẫn là 890: UPDATE -50 chưa được commit đã bị hoàn tác.
~~~

Bài thực hành chứng minh **hiệu ứng quan sát được** của rollback, snapshot và lock wait. Nó không trực tiếp chứng minh chi tiết WAL trên đĩa; muốn kiểm tra cơ chế crash recovery cần đọc tài liệu chính thức và thử nghiệm trong hệ thống được phép tắt/khởi động an toàn.

## 7. Liên hệ với Spring Framework: ranh giới và isolation

Đoạn mã minh họa sau là một **class Spring service**, yêu cầu dự án Java 17+ có Spring JDBC, Spring Transaction, `JdbcTemplate`, `DataSource` và một `PlatformTransactionManager` đúng với database. Đây **không phải** chương trình Java độc lập có thể chạy chỉ bằng `javac`.

**Tệp `src/main/java/com/example/tx/TransferService.java`:**

~~~java
package com.example.tx;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TransferService {
    private final JdbcTemplate jdbc;

    public TransferService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(isolation = Isolation.READ_COMMITTED)
    public void transfer(long fromId, long toId, long amount) {
        if (amount <= 0 || fromId == toId) {
            throw new IllegalArgumentException("Invalid transfer");
        }

        int debited = jdbc.update(
            "UPDATE tx_account_lab " +
            "SET balance = balance - ? " +
            "WHERE id = ? AND balance >= ?",
            amount, fromId, amount
        );
        if (debited != 1) {
            throw new IllegalStateException("Invalid source or insufficient balance");
        }

        int credited = jdbc.update(
            "UPDATE tx_account_lab " +
            "SET balance = balance + ? WHERE id = ?",
            amount, toId
        );
        if (credited != 1) {
            throw new IllegalArgumentException("Target account does not exist");
        }
    }
}
~~~

### Đọc ví dụ theo ba cơ chế

- **Spring:** khi một caller đi **qua Spring proxy** gọi `transfer()`, transaction interceptor yêu cầu transaction manager bắt đầu hoặc tham gia transaction. Hai lệnh `JdbcTemplate.update` cùng tham gia transaction được quản lý khi cấu hình kết nối nhất quán. Kết thúc bình thường thì transaction owner commit; unchecked exception thoát ra thì Spring mặc định rollback hoặc đánh dấu rollback-only.
- **Database log/recovery:** engine quản lý các thay đổi có khả năng recovery; Java service **không cần** tự ghi WAL.
- **Khóa:** hai lần `UPDATE` có thể giữ khóa ghi tương ứng. Nếu người khác đồng thời thay đổi cùng tài khoản, có thể chờ/timeout/deadlock; đoạn mã không loại bỏ nguy cơ đó.
- **MVCC:** các `SELECT` của transaction khác có thể đọc snapshot đã commit trong khi service đang ghi, phụ thuộc database và isolation. `@Transactional` không tự cấu hình “bật MVCC” bằng một câu lệnh riêng.

**Vì sao ghi `isolation = Isolation.READ_COMMITTED`?** Đây là mức cô lập yêu cầu **khi Spring bắt đầu một transaction mới** và database/transaction manager hỗ trợ; nó không thay đổi cơ chế MVCC của engine. Nếu lời gọi chỉ **tham gia transaction có sẵn**, các thuộc tính isolation trên method bên trong không mặc nhiên đổi isolation đang hoạt động. Có thể bỏ tham số này để dùng `Isolation.DEFAULT` (mặc định của database); không xem tên annotation là bằng chứng engine thực sự áp dụng mọi hành vi giống nhau.

**Propagation mặc định:** `@Transactional` dùng `REQUIRED`. Một service method tham gia transaction của caller có thể **chưa commit** khi method trả về; điểm commit do transaction bao ngoài quyết định.

**Quy tắc rollback mặc định:** Spring đánh dấu rollback đối với `RuntimeException` và `Error` thoát ra. Checked exception không mặc định yêu cầu rollback; cân nhắc `rollbackFor` nếu cần. Bắt rồi nuốt lỗi có thể khiến transaction kết thúc bình thường và commit trạng thái sai.

**Proxy/self-invocation:** lời gọi `this.transfer(...)` từ một method khác trong cùng bean thường bỏ qua transaction interceptor ở cơ chế proxy mặc định. Kiểm thử bằng Spring-managed bean thật thay vì tự tạo service bằng `new`.

**`readOnly = true` không phải khóa/đảm bảo bất biến:** đây chủ yếu là hint/tối ưu hóa và có thể làm một số driver/engine từ chối ghi tùy cấu hình; không có nghĩa tự tạo snapshot lâu dài hoặc chắc chắn cấm mọi `UPDATE`.

### Mức cô lập là hợp đồng hành vi, không phải tên thuật toán

| Isolation level | Cách hiểu thực hành | Điều vẫn phải tự kiểm tra |
| --- | --- | --- |
| `READ UNCOMMITTED` | Mức yếu theo chuẩn SQL; cách engine thực hiện có thể khác nhau, một số engine nâng mức thực tế. | Không suy ra chắc chắn sẽ thấy dirty read. |
| `READ COMMITTED` | Tránh đọc dữ liệu chưa commit; trong PostgreSQL snapshot thường theo **từng statement**. | Non-repeatable read và một số dạng read-modify-write race vẫn có thể xảy ra. |
| `REPEATABLE READ` | Hướng tới đọc ổn định hơn trong cùng transaction. | Cơ chế snapshot, locking read, phantom và write conflict khác nhau giữa PostgreSQL/InnoDB. |
| `SERIALIZABLE` | Mục tiêu kết quả tương đương một thứ tự chạy tuần tự của các transaction đã commit. | Database có thể **abort transaction** khi phát hiện xung đột; ứng dụng cần retry **toàn bộ transaction** một cách an toàn. |

Không lấy hành vi snapshot của PostgreSQL trong bài lab áp dụng nguyên xi cho Oracle, SQL Server, MySQL/InnoDB hay mọi phiên bản engine. Hãy đọc tài liệu isolation/concurrency của hệ quản trị đang dùng, và kiểm thử trên môi trường có cấu hình tương đương production.

## 8. Lỗi hiểu nhầm thường gặp

| Ngộ nhận | Điều đúng cần nhớ |
| --- | --- |
| “Có `@Transactional` thì không bao giờ mất dữ liệu.” | Durability phụ thuộc database, log flushing, phần cứng, cấu hình và ranh giới của transaction. |
| “WAL là file ghi lại câu SQL để developer đọc.” | WAL/redo là cơ chế recovery nội bộ; audit log và application log có mục tiêu khác. |
| “Dùng MVCC thì mọi khóa biến mất.” | Ghi cạnh tranh, locking read, DDL và các hoạt động khác vẫn có thể chờ khóa. |
| “Khóa ghi giúp mọi phép tính Java trên giá trị đọc cũ luôn đúng.” | Read-modify-write vẫn có thể ghi đè dữ liệu; dùng SQL atomic, version check hoặc isolation/locking phù hợp. |
| “Đọc snapshot nghĩa là đọc được toàn bộ trạng thái mới nhất.” | Snapshot có thể là một thời điểm trước đó, cố ý che các thay đổi mới commit tùy isolation. |
| “Mỗi câu SELECT dùng shared row lock.” | Trong nhiều MVCC database, SELECT thường được phục vụ từ snapshot mà không giữ shared row lock tương ứng. |
| “`SERIALIZABLE` nghĩa là chắc chắn chờ đến khi chạy được.” | Engine có thể hủy transaction với lỗi serialization/deadlock và yêu cầu retry. |
| “Tăng isolation lên cao nhất luôn là tối ưu.” | Mức cô lập cao hơn có thể tăng tranh chấp, retry, chi phí; lựa chọn theo bất biến cần bảo vệ. |
| “Giao dịch database rollback cả HTTP/email/message.” | Một local database transaction không hoàn tác hiệu ứng bên ngoài; cần kiến trúc phối hợp phù hợp như outbox/saga. |
| “Transaction đã đóng nhưng client không nhận phản hồi thì chắc chưa commit.” | Đây là tình huống kết quả **không chắc chắn** với client; kiểm tra idempotency/status trước khi retry. |

## 9. Cách chọn cơ chế khi thiết kế nghiệp vụ

Đặt ba câu hỏi theo thứ tự:

1. **Nếu crash giữa hai bước cập nhật, phải phục hồi điều gì?** Gom các cập nhật có quan hệ nguyên tử vào **cùng database transaction**, dùng engine/cấu hình có recovery và durability phù hợp. Thử nghiệm rollback khi bước thứ hai thất bại.
2. **Nếu hai người cùng thay đổi dữ liệu, có thể đè/làm sai điều kiện nào?** Dùng điều kiện kiểm tra trong SQL, khóa khi cần, version check, ràng buộc DB, thứ tự truy cập nhất quán và chiến lược retry đối với lỗi tranh chấp.
3. **Nếu một người đọc trong lúc người khác ghi, cần thấy dữ liệu ở thời điểm nào?** Xác định isolation và hành vi snapshot của chính engine. Khi cần đọc để rồi cập nhật, kiểm tra thêm lost update/write skew; không dựa riêng vào giả định “SELECT không chờ” hay “MVCC đã đủ”.

**Minh họa quyết định:** với hệ thống đặt chỗ, transaction giúp tránh ghi nửa đơn hàng; kiểm tra `UPDATE ... WHERE seats_left > 0` hoặc cơ chế khóa phù hợp giúp tránh bán vượt số ghế; MVCC giúp truy vấn hiển thị số ghế trong khi các transaction khác đang thực hiện, nhưng kết quả hiển thị có thể vừa trở nên cũ trước khi người dùng bấm xác nhận. **Kiểm tra và trừ chỗ phải diễn ra lại bên trong transaction khi xác nhận**, không tin tuyệt đối số liệu đã đọc ở màn hình.

## 10. Tự kiểm tra

1. **UPDATE chạy xong trong RAM nhưng database crash trước khi data page được ghi, transaction đã commit bền vững. Cơ chế nào quan trọng?** — WAL/redo và crash recovery giúp phục hồi thay đổi đã commit theo bảo đảm durability.
2. **Hai transaction cùng UPDATE một hàng, liệu MVCC đảm bảo cả hai không cần chờ?** — Không; ghi cùng hàng thường có xung đột được điều phối bằng khóa hoặc cơ chế kiểm tra thích hợp.
3. **Tại PostgreSQL READ COMMITTED, A sửa từ 1.000 xuống 900 nhưng chưa commit. Một SELECT thường ở B nhìn thấy gì?** — Phiên bản đã commit phù hợp snapshot, trong bài lab là 1.000.
4. **Tại sao B đọc 1.000 rồi ghi cố định 990 có thể sai dù UPDATE có khóa?** — Giá trị 990 được tính từ dữ liệu cũ và có thể ghi đè cập nhật của A; khóa chỉ điều phối thời điểm ghi.
5. **Gắn `@Transactional` có tự tạo MVCC không?** — Không. Spring thiết lập/yêu cầu transaction; database quyết định cơ chế log, lock, version và isolation.
6. **Tại sao một long-running transaction có thể làm hệ thống chậm dù chủ yếu đọc?** — Nó có thể giữ snapshot/tài nguyên lâu, cản trở thu gom phiên bản cũ hoặc tăng tranh chấp tùy engine.

**Kết luận học tập:** nhật ký bảo vệ khả năng **phục hồi sau sự cố**; khóa điều phối **xung đột truy cập**; MVCC cho phép **đọc các phiên bản nhất quán** với mức cô lập cụ thể. Spring `@Transactional` là cách khai báo **ranh giới nghiệp vụ** sử dụng các bảo đảm của database. Hiểu rõ vai trò và giới hạn từng cơ chế giúp tránh cả cập nhật dở dang lẫn lỗi đồng thời khó phát hiện.

### Tài liệu tham khảo chính thức

- [PostgreSQL — Write-Ahead Logging](https://www.postgresql.org/docs/current/wal-intro.html)
- [PostgreSQL — Introduction to MVCC](https://www.postgresql.org/docs/current/mvcc-intro.html)
- [PostgreSQL — Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html)
- [Spring Framework — Declarative transaction management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
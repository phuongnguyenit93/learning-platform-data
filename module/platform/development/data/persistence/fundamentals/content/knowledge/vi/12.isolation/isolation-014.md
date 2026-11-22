# Chọn mức cô lập theo bất biến và mẫu truy cập

Một chức năng persistence có thể chạy đúng trong kiểm thử đơn luồng nhưng sai khi hai request đồng thời đọc và thay đổi cùng dữ liệu. Ví dụ hai người cùng mua sản phẩm cuối cùng, hai bác sĩ cùng xin nghỉ trong một ca trực, hay hai yêu cầu đặt phòng cùng nhìn thấy một khoảng trống. Mỗi transaction có thể tuân thủ các bước kiểm tra của nó mà kết quả cuối vẫn vi phạm nghiệp vụ.

Bài này thuộc chương **Tính cô lập** của module **DATA_PERSISTENCE_FUNDAMENTALS**. Ta sẽ chọn mức cô lập dựa trên **bất biến dữ liệu**, **mẫu đọc/ghi của những transaction đồng thời**, và **chi phí bảo vệ**. Cách tiếp cận áp dụng cho ranh giới persistence trong Java với JDBC, Spring và hệ quản trị cơ sở dữ liệu quan hệ.

**Nguyên tắc chính:** hãy mô tả điều kiện cần giữ sau mỗi commit trước khi hỏi nên dùng READ COMMITTED, REPEATABLE READ hay SERIALIZABLE.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

- Viết một bất biến (invariant) nghiệp vụ thành điều kiện có thể kiểm chứng.
- Phân biệt dirty read, non-repeatable read, phantom, lost update và write skew qua lịch chạy hai transaction.
- Giải thích vì sao cùng tên mức cô lập không đồng nghĩa hành vi giống nhau trên mọi database.
- Chọn constraint, SQL nguyên tử, optimistic locking, khóa tường minh hay SERIALIZABLE theo mẫu truy cập.
- Cấu hình mức cô lập trong Java và Spring, đặt retry ở ngoài transaction phải thử lại.
- Thiết kế kiểm thử đồng thời buộc race condition xuất hiện và đánh giá lock wait, abort, throughput cùng độ trễ.

## 2. Xuất phát từ bất biến nghiệp vụ

**Bất biến** là điều kiện luôn phải đúng ở trạng thái dữ liệu được coi là hợp lệ, đặc biệt sau mỗi transaction commit.

| Tình huống | Bất biến | Dữ liệu cần phối hợp |
|---|---|---|
| Bán hàng | Số lượng có thể bán không âm | Một hàng tồn kho theo SKU/kho |
| Tài khoản | Không chi vượt số dư khả dụng khi không cho phép thấu chi | Một hoặc nhiều hàng tiền, giữ tiền |
| Tạo đơn | Mã đơn duy nhất trong phạm vi tenant | Nhiều INSERT có thể trùng khóa |
| Lịch trực | Mỗi ca luôn còn ít nhất một bác sĩ đang trực | Nhiều hàng của một ca |
| Đặt phòng | Không có hai đặt chỗ đã xác nhận trùng phòng và thời gian | Một tập hàng thỏa điều kiện khoảng |
| Báo cáo | Các số liệu đọc trong cùng báo cáo phản ánh một thời điểm logic | Nhiều câu SELECT và bảng |
| Cấp hạn mức | Tổng số lượt cấp không vượt quota chiến dịch | Nhiều người dùng cùng quota |

Đối với từng bất biến, cần trả lời:

1. **Ai có thể ghi?** Chỉ một API hay cả batch job, consumer, migration hoặc dịch vụ khác?
2. **Ai đọc trước khi quyết định ghi?** Đọc theo primary key, theo một khoảng hay đếm cả tập hàng phù hợp?
3. **Các giao dịch có ghi cùng hàng không?** Nếu chúng đọc chung một tập rồi ghi hai hàng khác nhau, xung đột hàng thông thường có thể không đủ để phát hiện lỗi.
4. **Database có biểu diễn điều kiện thành constraint hoặc một câu SQL nguyên tử được không?** Đây thường là bảo vệ đơn giản nhất.
5. **Nếu một attempt bị từ chối, có thể retry toàn bộ công việc an toàn không?** Tác động HTTP, email hoặc thanh toán bên ngoài không tự rollback.

Không nên suy mức cô lập chỉ từ danh sách thao tác SELECT và UPDATE mà bỏ qua cách các request có thể xen kẽ.

## 3. Đọc lịch thực thi đồng thời

Ta ký hiệu T1 và T2 là hai transaction trên hai kết nối độc lập:

~~~text
Thời gian      Transaction T1                 Transaction T2
   |           BEGIN                          BEGIN
   |           SELECT ... -> trạng thái A
   |                                          SELECT ... -> trạng thái A
   |           UPDATE hàng X
   |                                          UPDATE hàng Y
   |           COMMIT
   v                                          COMMIT
~~~

Một transaction thực hiện đúng trình tự đọc, kiểm tra, cập nhật, commit **không đủ** để chứng minh trạng thái cuối đúng. Hai transaction có thể cùng dựa trên dữ liệu cũ để đưa ra những quyết định xung đột về nghiệp vụ.

### 3.1. Dirty read: đọc dữ liệu chưa commit

~~~text
T1: UPDATE accounts SET balance = 20 WHERE id = 1; -- chưa commit
T2: SELECT balance FROM accounts WHERE id = 1;      -- có thể thấy 20
T1: ROLLBACK;
~~~

Nếu T2 thấy 20 rồi tính toán dựa vào nó, quyết định được đưa ra từ trạng thái chưa bao giờ được commit. READ COMMITTED theo định nghĩa ngăn dirty read. PostgreSQL không thực hiện dirty read ngay cả khi yêu cầu READ UNCOMMITTED: chế độ đó được xử lý tương tự READ COMMITTED.

### 3.2. Non-repeatable read: cùng hàng, hai lần đọc hai giá trị

~~~text
T1: BEGIN;
T1: SELECT balance FROM accounts WHERE id = 1; -- 100
T2: UPDATE accounts SET balance = 200 WHERE id = 1; COMMIT;
T1: SELECT balance FROM accounts WHERE id = 1; -- 200 ở READ COMMITTED
T1: COMMIT;
~~~

Trong PostgreSQL READ COMMITTED, từng câu lệnh thường có snapshot riêng của các thay đổi đã commit. Hai SELECT trong cùng transaction vì thế có thể thấy hai phiên bản khác nhau.

Đối với request chỉ lấy một hàng rồi trả kết quả, điều này có thể hoàn toàn chấp nhận được. Đối với một báo cáo phải tính tổng và chi tiết trên cùng snapshot, nó có thể làm kết quả không nhất quán về mặt thời điểm.

### 3.3. Phantom: tập hàng phù hợp điều kiện thay đổi

~~~text
T1: SELECT COUNT(*) FROM bookings
    WHERE room_id = 5 AND status = 'CONFIRMED';  -- 3
T2: INSERT INTO bookings(... room_id=5, status='CONFIRMED');
T2: COMMIT;
T1: SELECT COUNT(*) FROM bookings
    WHERE room_id = 5 AND status = 'CONFIRMED';  -- 4 ở READ COMMITTED
~~~

Non-repeatable read thường minh họa **một hàng thay đổi**. Phantom thường nói về **cả tập hàng** được định nghĩa bởi WHERE: hàng mới được thêm, hoặc hàng không còn thỏa điều kiện.

SQL chuẩn phân biệt REPEATABLE READ và SERIALIZABLE về khả năng phantom. Tuy nhiên **PostgreSQL REPEATABLE READ sử dụng snapshot isolation và không quan sát phantom trong các lần đọc thông thường của cùng transaction**. Hành vi chi tiết phụ thuộc database; không suy ra kết luận chung chỉ từ tên mức.

### 3.4. Lost update: ghi đè thay đổi của nhau

Ban đầu tồn kho bằng 10. Hai transaction đều đọc 10 ở ứng dụng Java, tính 9 rồi lưu 9:

~~~text
T1: SELECT available FROM inventory WHERE sku='A'; -- 10
T2: SELECT available FROM inventory WHERE sku='A'; -- 10
T1: UPDATE inventory SET available=9 WHERE sku='A'; COMMIT;
T2: UPDATE inventory SET available=9 WHERE sku='A'; COMMIT;
~~~

Hai lần bán đã diễn ra nhưng tồn kho chỉ giảm một. Mẫu **read → compute → write** có thể gây lost update khi cơ chế cô lập và câu lệnh cho phép ghi đè giá trị đã tính. PostgreSQL REPEATABLE READ có thể từ chối cập nhật cùng hàng sau xung đột; ở READ COMMITTED, mẫu viết giá trị cố định từ lần đọc cũ vẫn nguy hiểm.

Một cách bảo vệ tốt hơn cho bộ đếm trên một hàng là:

~~~sql
UPDATE inventory
SET available = available - 1
WHERE sku = 'A'
  AND available >= 1
RETURNING available;
~~~

Trong PostgreSQL READ COMMITTED, cập nhật cùng hàng phải phối hợp qua row lock, và điều kiện có thể được đánh giá lại sau khi chờ transaction khác. Khi chỉ còn 1 sản phẩm, hai lần UPDATE có điều kiện không thể cùng trừ thành công nếu các đường ghi đều tuân thủ quy tắc này. Không có hàng trả về nghĩa là không có hàng phù hợp tại thời điểm lệnh được áp dụng; ứng dụng cần phân biệt hết hàng và SKU không tồn tại nếu hợp đồng API yêu cầu.

### 3.5. Write skew: ghi các hàng khác nhau nhưng phá luật chung

Một ca trực phải luôn có ít nhất một bác sĩ đang trực:

~~~sql
CREATE TABLE doctor_shift (
    shift_id  bigint NOT NULL,
    doctor_id bigint NOT NULL,
    on_call   boolean NOT NULL,
    PRIMARY KEY (shift_id, doctor_id)
);
~~~

Ban đầu A và B cùng on_call=true. T1 muốn cho A nghỉ, T2 muốn cho B nghỉ. Cả hai đều làm:

~~~sql
SELECT COUNT(*) FROM doctor_shift
WHERE shift_id = 7 AND on_call = true;

-- Nếu count > 1, cho bác sĩ tương ứng nghỉ.
UPDATE doctor_shift SET on_call = false
WHERE shift_id = 7 AND doctor_id = :doctorId;
~~~

Một lịch chạy nguy hiểm:

| Bước | T1: cho A nghỉ | T2: cho B nghỉ |
|---|---|---|
| 1 | Đọc count = 2 | |
| 2 | | Đọc count = 2 |
| 3 | Ghi hàng A thành false | |
| 4 | | Ghi hàng B thành false |
| 5 | COMMIT | |
| 6 | | COMMIT |
| Kết quả | **Không còn ai đang trực** | |

Các transaction không ghi đè cùng hàng. Ở PostgreSQL REPEATABLE READ, **snapshot isolation có thể cho phép write skew** vì hai giao dịch cùng đưa ra quyết định từ một snapshot hợp lệ rồi ghi những hàng khác nhau.

Trong PostgreSQL SERIALIZABLE, cơ chế kiểm tra phụ thuộc đọc/ghi phát hiện những lịch không thể tuần tự hóa; một giao dịch có thể bị abort với SQLSTATE **40001**. Khi retry toàn bộ transaction, nó sẽ đọc số bác sĩ còn trực sau commit của transaction kia và không cho người cuối cùng nghỉ.

## 4. Hiểu các mức cô lập và khác biệt giữa DBMS

| Mức | Tính chất trọng tâm | Điều phải chú ý |
|---|---|---|
| READ UNCOMMITTED | Theo mô hình lý thuyết có thể dirty read | PostgreSQL thực thi tương đương READ COMMITTED |
| READ COMMITTED | Không thấy các thay đổi chưa commit | Mỗi câu SQL có thể dùng snapshot khác; nhiều bước kiểm tra rồi ghi cần bảo vệ bổ sung |
| REPEATABLE READ | Không thấy non-repeatable read theo SQL chuẩn | PostgreSQL giữ snapshot ổn định cho các lần đọc thường, không thấy phantom nhưng còn nguy cơ write skew |
| SERIALIZABLE | Kết quả của những transaction đã commit tương đương một thứ tự chạy tuần tự | Có thể chờ hoặc abort; ứng dụng cần retry toàn transaction khi được báo lỗi serialization |

**Không đồng nhất hai khái niệm:**

- **Snapshot consistency:** các phép đọc trong một transaction có thể nhìn cùng một phiên bản dữ liệu.
- **Serializability:** toàn bộ các transaction đã commit có kết quả tương đương một lịch chạy tuần tự hợp lệ.

Snapshot nhất quán chưa đủ bảo vệ mọi bất biến nhiều hàng. Lịch bác sĩ là ví dụ: hai transaction cùng đọc count=2 từ snapshot nhất quán, nhưng commit cả hai sẽ vi phạm bất biến.

### 4.1. PostgreSQL

- READ COMMITTED cung cấp snapshot mới cho mỗi câu lệnh; UPDATE có thể chờ hàng đang bị khóa rồi đánh giá lại điều kiện đối với phiên bản đã được commit.
- REPEATABLE READ giữ snapshot cho transaction; những cập nhật cùng hàng sau thay đổi đồng thời có thể bị từ chối thay vì ghi đè, nhưng write skew giữa các hàng khác nhau vẫn có thể xảy ra.
- SERIALIZABLE dựa trên phát hiện những cấu trúc xung đột nguy hiểm để bảo đảm hành vi tuần tự hóa, có thể abort tại câu lệnh hoặc commit; nó **không** có nghĩa là khóa toàn bộ database cho đến khi một transaction chạy xong.

### 4.2. Các hệ quản trị khác

MySQL/InnoDB có khác biệt giữa consistent read và locking/current read, cùng next-key/gap lock ở những tình huống nhất định. SQL Server có những lựa chọn snapshot/read committed snapshot tùy cấu hình. Các hệ khác có thể dùng tên mức cô lập tương tự nhưng khóa và snapshot hoạt động khác.

Nếu cần chứng minh tính đúng đắn, hãy cố định **hệ quản trị, phiên bản, cấu hình isolation, câu SQL, chỉ mục và đường ghi** trước khi kết luận. Không mang nguyên xi mô tả PostgreSQL sang mọi DBMS.

## 5. Chọn công cụ bảo vệ theo dạng bất biến

### 5.1. Constraint: nếu database biểu diễn được luật, hãy để DB cưỡng chế

Ví dụ mỗi tenant có mã đơn riêng:

~~~sql
CREATE TABLE orders (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id bigint NOT NULL,
    order_code text NOT NULL,
    UNIQUE (tenant_id, order_code)
);
~~~

Hai request cùng SELECT kiểm tra mã ABC chưa tồn tại vẫn có thể cùng thấy rỗng. UNIQUE constraint chặn trạng thái cuối có hai hàng trùng cùng khóa. Ứng dụng cần xử lý xung đột UNIQUE hoặc upsert đúng hợp đồng nghiệp vụ.

Các bất biến trên một hàng có thể dùng CHECK:

~~~sql
CREATE TABLE inventory (
    sku text PRIMARY KEY,
    available integer NOT NULL CHECK (available >= 0)
);
~~~

CHECK không tự bảo vệ quy tắc tổng hợp nhiều hàng như “ít nhất một bác sĩ đang trực”. Việc giữ luật đó cần thiết kế khác.

### 5.2. Atomic UPDATE: điều kiện kiểm tra nằm trong câu ghi

~~~sql
UPDATE inventory
SET available = available - :quantity
WHERE sku = :sku AND available >= :quantity
RETURNING available;
~~~

Một câu ghi có điều kiện thường phù hợp hơn chuỗi SELECT, tính toán ở Java rồi UPDATE giá trị cố định. Đảm bảo lượng trừ dương và xử lý kết quả 0 hàng; constraints vẫn cần bảo vệ những đường ghi khác.

### 5.3. Optimistic locking: bảo vệ một entity qua version

~~~sql
CREATE TABLE order_state (
    id bigint PRIMARY KEY,
    status text NOT NULL,
    version bigint NOT NULL DEFAULT 0
);

UPDATE order_state
SET status = 'CONFIRMED', version = version + 1
WHERE id = :orderId
  AND status = 'PENDING'
  AND version = :expectedVersion;
~~~

Nếu UPDATE trả 0 hàng, entity không còn ở trạng thái/version mong đợi. Ứng dụng phải báo xung đột hoặc đọc lại. Trong JPA, @Version hỗ trợ optimistic locking khi các cập nhật đi qua cơ chế entity tương ứng; các bulk SQL hoặc đường ghi khác có thể bỏ qua version nếu không chủ động phối hợp.

Optimistic locking **không** tự giải quyết bất biến trên một tập nhiều hàng chỉ được kiểm tra bằng SELECT COUNT(*).

### 5.4. Guard row: khóa điểm chung trước khi quyết định

Với một ca trực, có thể tạo hàng đại diện ca rồi yêu cầu **mọi đường ghi** khóa hàng đó trước khi đếm và thay đổi bác sĩ:

~~~sql
CREATE TABLE shifts (
    id bigint PRIMARY KEY,
    starts_at timestamptz NOT NULL
);

BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT id FROM shifts WHERE id = 7 FOR UPDATE;

SELECT COUNT(*) FROM doctor_shift
WHERE shift_id = 7 AND on_call = true;

-- Nếu count > 1 và người yêu cầu vẫn on_call:
UPDATE doctor_shift
SET on_call = false
WHERE shift_id = 7 AND doctor_id = 101 AND on_call = true;

COMMIT;
~~~

T2 cùng thay đổi shift=7 phải chờ hàng guard đang khóa. Khi T2 tiếp tục ở READ COMMITTED, nó đếm lại sau commit của T1 và có thể từ chối yêu cầu cho bác sĩ cuối cùng nghỉ.

**Để cách này đúng:** hàng guard tồn tại, tất cả transaction ảnh hưởng đến cùng bất biến phải khóa cùng guard trước lúc kiểm tra/ghi, và các đường ghi tuân thủ quy tắc. Nó tạo tranh chấp trên nhóm quá nóng nhưng thường rất dễ suy luận.

Chỉ sử dụng SELECT ... FOR UPDATE trên các hàng hiện có không mặc nhiên khóa được **hàng chưa tồn tại** hay mọi hàng về sau thỏa một predicate. Cách khóa vùng/predicate tùy database và access path.

### 5.5. SERIALIZABLE: khi luật trải rộng trên một predicate

Nếu không có constraint hoặc điểm phối hợp đơn giản, transaction serializable là lựa chọn phù hợp để phát hiện lịch hai giao dịch cùng đọc predicate rồi ghi các hàng khác nhau:

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*) FROM doctor_shift
WHERE shift_id = 7 AND on_call = true;

-- Chỉ cập nhật nếu điều kiện nghiệp vụ cho phép.
UPDATE doctor_shift
SET on_call = false
WHERE shift_id = 7 AND doctor_id = 101 AND on_call = true;

COMMIT;
~~~

Hai transaction có thể cùng đi qua bước đọc ban đầu nhưng ít nhất một transaction không thể commit thành công trong lịch write skew của PostgreSQL SERIALIZABLE. Khi nhận serialization failure, phải **làm lại toàn bộ transaction** từ việc đọc count, thay vì lặp lại riêng câu UPDATE.

Cần bảo đảm các writer liên quan phối hợp với cơ chế bảo vệ; nếu một luồng cập nhật ngoài transaction hoặc bỏ qua logic kiểm tra, bất biến vẫn có thể bị phá.

## 6. Bảng quyết định theo mẫu truy cập

| Tình huống | Mẫu truy cập | Chiến lược khởi đầu | Cần kiểm tra |
|---|---|---|---|
| Hai request trừ tồn kho cùng SKU | Nhiều UPDATE tranh một hàng | READ COMMITTED + atomic UPDATE + CHECK | Có đường ghi khác bỏ qua điều kiện không? |
| Tạo mã đơn duy nhất | INSERT tranh khóa logic | UNIQUE + xử lý xung đột/idempotency | Phạm vi tenant, trạng thái soft delete |
| Chuyển trạng thái một đơn | Read-modify-write trên một entity | Version compare-and-set hoặc khóa hàng | Request có sử dụng cùng version không? |
| Ít nhất một người trong ca | Đọc COUNT trên tập, ghi hai hàng khác nhau | Guard row + khóa hoặc SERIALIZABLE + retry | Mọi writer có theo quy trình? |
| Booking không trùng giờ | Đọc theo predicate khoảng, INSERT hàng mới | Constraint trên khoảng nếu DB hỗ trợ, guard hoặc SERIALIZABLE | Điều kiện biên, timezone, index, retry |
| Báo cáo nhiều truy vấn cùng snapshot | Đọc lặp nhiều bảng, ít hoặc không ghi | REPEATABLE READ read-only theo DB phù hợp | Snapshot ở đâu, thời lượng transaction |
| Quy trình DB + HTTP + broker | Nhiều tài nguyên không cùng transaction | Local transaction + outbox, Saga, idempotency | Isolation DB không bao phủ dịch vụ ngoài |
| Nhóm hàng ghi rất nóng | Nhiều writer cùng lock/cập nhật | Rút ngắn transaction, giảm điểm nóng, nguyên tử | Lock wait, deadlock, throughput, p95 |

Bảng chỉ là cách bắt đầu thiết kế. Một dự án có thể chọn SERIALIZABLE làm mặc định nếu dữ liệu và tải phù hợp; dự án khác có thể dùng READ COMMITTED và giải quyết phần lớn luật bằng constraint cùng SQL nguyên tử. Điều quan trọng là **có lập luận về bất biến và lịch cạnh tranh**, không áp dụng một mức theo thói quen.

### 6.1. Khi nhiều request cập nhật cùng hàng

Giả sử một SKU rất phổ biến có hàng nghìn giao dịch bán trong một phút. Tăng mức cô lập không loại bỏ điểm nóng: các ghi cùng hàng vẫn cần phối hợp. Nếu mỗi request có thể trừ tồn bằng một câu UPDATE có điều kiện, phương án này thường đơn giản và ít tốn chi phí suy luận hơn.

Theo dõi số hàng được cập nhật, mức tranh chấp ở SKU nóng, thời gian giữ khóa và lượng retry. Khi cần hiệu năng vượt giới hạn một hàng, có thể cân nhắc reservation hoặc partitioning theo kho, nhưng bất biến tổng phải được thiết kế lại tương ứng.

### 6.2. Khi hai request đọc cùng tập nhưng cập nhật khác hàng

Đây là mẫu nguy hiểm cho **write skew**: bác sĩ xin nghỉ, hai quản trị viên hủy reservation cuối cùng, hoặc hai tác vụ cùng kiểm tra tổng quota rồi ghi vào các hàng chi tiết riêng. Khóa cập nhật tại từng hàng đích có thể không chặn hai quyết định mâu thuẫn.

Hãy tìm **điểm đồng bộ chung** mà mọi transaction phải khóa trước khi quyết định, hoặc dùng SERIALIZABLE kèm retry. Đừng chỉ chuyển sang REPEATABLE READ rồi coi snapshot nhất quán là đủ.

### 6.3. Khi transaction chỉ đọc nhiều câu SQL

Ví dụ báo cáo tính số lượng đơn, tổng tiền và khoản hoàn trả bằng các SELECT riêng. Nếu yêu cầu tất cả số liệu cùng snapshot, PostgreSQL REPEATABLE READ có thể phù hợp hơn READ COMMITTED.

Tuy nhiên một báo cáo kéo dài nhiều phút có thể giữ snapshot cũ và ảnh hưởng dọn phiên bản dữ liệu hoặc tài nguyên kết nối. Cần xác định thời gian tối đa, tối ưu SQL và xem xét chụp số liệu/materialized result nếu phù hợp.

### 6.4. Khi predicate bao gồm hàng chưa tồn tại

Kiểm tra “chưa có booking nào chồng khoảng” rồi INSERT là mẫu dễ gặp phantom và race:

~~~sql
SELECT COUNT(*) FROM bookings
WHERE room_id = :roomId
  AND status = 'CONFIRMED'
  AND starts_at < :newEnd
  AND ends_at > :newStart;
~~~

Nếu chưa có hàng trùng, SELECT FOR UPDATE trên kết quả rỗng có thể không khóa được gì trong một số hệ. Với PostgreSQL, một **exclusion constraint** trên khoảng và room_id có thể biểu diễn luật ở mức schema khi điều kiện nghiệp vụ cho phép; nếu không, dùng guard row theo phòng hoặc SERIALIZABLE với retry và thử nghiệm tình huống biên.

Cần xác định rõ khoảng nửa mở [start, end), timezone và các trạng thái booking nào chiếm phòng.

## 7. Thiết lập mức cô lập trong Java/JDBC

Khi tự quản lý giao dịch JDBC, cần đặt isolation cho connection trước khi bắt đầu transaction, thực thi toàn bộ các câu đọc/ghi liên quan trên cùng connection và rollback khi thất bại.

~~~java
try (Connection connection = dataSource.getConnection()) {
    int originalIsolation = connection.getTransactionIsolation();
    boolean originalAutoCommit = connection.getAutoCommit();

    try {
        connection.setTransactionIsolation(
            Connection.TRANSACTION_SERIALIZABLE
        );
        connection.setAutoCommit(false);

        // Toàn bộ thao tác phải dùng connection này.
        validateBusinessInvariant(connection);
        applyBusinessUpdate(connection);

        connection.commit();
    } catch (SQLException | RuntimeException ex) {
        try {
            connection.rollback();
        } catch (SQLException rollbackFailure) {
            ex.addSuppressed(rollbackFailure);
        }
        throw ex;
    } finally {
        connection.setAutoCommit(originalAutoCommit);
        connection.setTransactionIsolation(originalIsolation);
    }
}
~~~

Đây là ví dụ minh họa, chưa phải một tiện ích JDBC dùng ngay trong production. Phải xử lý riêng tình huống commit mất kết nối và kết quả **chưa rõ**, cũng như lỗi khi khôi phục cấu hình connection. Connection pool/framework thường quản lý reset session; chỉ thay đổi isolation theo cơ chế được pool và driver hỗ trợ. Trong Spring không nên tự commit/rollback một connection mà transaction manager đang quản lý.

Một serialization failure trong PostgreSQL thường có SQLSTATE **40001**. Sau khi nhận lỗi này, không thể tiếp tục dùng transaction đã thất bại. Nếu thử lại, phải tạo transaction mới và làm lại **cả phần đọc lẫn quyết định ghi**. Riêng kết quả commit bị mất ACK không mặc nhiên là 40001; cần idempotency hoặc đối soát để tránh lặp tác động.

## 8. Spring @Transactional: ranh giới chính xác quan trọng hơn annotation

Giả sử có repository ghi và đọc dữ liệu lịch trực trong cùng PostgreSQL/DataSource:

~~~java
@Service
public class OnCallTransactionService {
    private final DoctorShiftRepository repository;

    public OnCallTransactionService(DoctorShiftRepository repository) {
        this.repository = repository;
    }

    @Transactional(isolation = Isolation.SERIALIZABLE)
    public void removeFromOnCall(long shiftId, long doctorId) {
        int onCallCount = repository.countOnCall(shiftId);

        if (onCallCount <= 1) {
            throw new IllegalStateException(
                "A shift must have at least one doctor on-call"
            );
        }

        int changed = repository.markOffCall(shiftId, doctorId);
        if (changed != 1) {
            throw new IllegalStateException(
                "Doctor is not on-call for this shift"
            );
        }
    }
}
~~~

Trong repository, markOffCall cần có predicate xác định chính xác hàng đang trực:

~~~sql
UPDATE doctor_shift
SET on_call = false
WHERE shift_id = :shiftId
  AND doctor_id = :doctorId
  AND on_call = true;
~~~

Nếu hai transaction serializable cùng đọc số bác sĩ bằng 2 rồi cập nhật hai người khác nhau, PostgreSQL không cho cả hai commit trong lịch gây write skew; một attempt có thể bị serialization failure. Sau khi retry từ đầu, logic đếm số người sẽ quyết định lại dựa trên trạng thái mới.

**Bẫy quan trọng:** nếu method có @Transactional tham gia transaction đã tồn tại, cấu hình isolation khai báo ở method trong thường không tự nâng mức của transaction ngoài. Khi cần kiểm soát chặt, xác nhận transaction manager, propagation, cách proxy gọi method và cấu hình kiểm tra transaction đã tồn tại, chẳng hạn validateExistingTransactions theo môi trường Spring.

### 8.1. Retry phải ở ngoài transaction

Lớp điều phối nên nằm **ngoài** phương thức @Transactional cần thử lại, để mỗi attempt gọi qua Spring proxy và tạo transaction mới:

~~~java
@Service
public class OnCallCommandService {
    private final OnCallTransactionService txService;

    public OnCallCommandService(OnCallTransactionService txService) {
        this.txService = txService;
    }

    public void remove(long shiftId, long doctorId) {
        for (int attempt = 1; attempt <= 3; attempt++) {
            try {
                txService.removeFromOnCall(shiftId, doctorId);
                return;
            } catch (CannotSerializeTransactionException
                     | DeadlockLoserDataAccessException ex) {
                if (attempt == 3) {
                    throw ex;
                }
                // Backoff có jitter, thời hạn retry và metrics phù hợp.
                // Attempt kế tiếp chạy lại TOÀN BỘ method trong transaction mới.
            }
        }
    }
}
~~~

Các exception trên minh họa loại lỗi mà tầng Spring có thể dịch từ database. Việc phân loại cụ thể cần kiểm tra driver, translation và SQLSTATE. Không retry mù quáng lỗi UNIQUE, lỗi dữ liệu không hợp lệ hoặc ngoại lệ nghiệp vụ “chỉ còn một người trực”: những lỗi đó có thể sẽ không biến mất chỉ vì gọi lại.

Nếu mỗi retry lại gửi email, gọi API thanh toán hay publish message, ứng dụng có thể tạo tác động trùng mà database rollback không thể xóa. Khi cần phát sự kiện sau commit, ghi intent qua **transactional outbox** trong cùng transaction DB và để dispatcher xử lý bền vững ở bước khác.

### 8.2. Những điều Spring không tự làm thay

- Lời gọi qua this.someMethod() bên trong cùng đối tượng thường không đi qua transactional proxy.
- Mức cô lập thuộc **transaction mới được tạo**; khi tham gia transaction hiện có, cấu hình bên ngoài có thể quyết định.
- @Transactional(readOnly = true) là chỉ dẫn tối ưu/khả năng kiểm tra theo từng cấu hình, không thay thế isolation hoặc quyền DB.
- REQUIRES_NEW tạo transaction riêng, không khiến hai transaction commit nguyên tử với nhau.
- Transaction context không tự theo sang thread @Async hay tiến trình khác.
- Hai DataSource/transaction manager độc lập không tự trở thành một transaction duy nhất.
- Giữ transaction mở trong lúc gọi HTTP lâu làm tăng giữ kết nối, lock và rủi ro xung đột.

## 9. SERIALIZABLE: đúng đắn nhưng phải đo chi phí

SERIALIZABLE bảo đảm kết quả của các transaction đã commit tương đương thứ tự thực thi tuần tự phù hợp trong phạm vi cơ sở dữ liệu. Nó không yêu cầu database thực sự xếp hàng tuần tự mọi request; PostgreSQL có thể chạy đồng thời và abort một số attempt khi phát hiện xung đột nguy hiểm.

Chi phí tùy workload:

- Giao dịch càng dài, cơ hội chạm dữ liệu đang bị giao dịch khác sử dụng càng cao.
- Đọc predicate rộng hoặc truy vấn chưa có chỉ mục tốt có thể tăng công việc và phạm vi phụ thuộc xung đột.
- Nhiều writer tranh chấp trên cùng nhóm dữ liệu làm tăng khả năng retry, lock wait và giảm throughput.
- Retry nguyên transaction làm tăng số SQL thực sự được chạy trên một request thành công.
- Transaction giữ lâu ảnh hưởng pool và tài nguyên DB ngay cả khi cuối cùng rollback.

Không có quy tắc SERIALIZABLE luôn chậm gấp một hệ số cố định. Cần đo trên dữ liệu và mức đồng thời đại diện, đồng thời kiểm tra **bất biến vẫn đúng**.

| Chỉ số | Câu hỏi |
|---|---|
| Serialization failure (40001), deadlock (40P01) của PostgreSQL | Có bao nhiêu attempt phải abort? |
| Số attempt trên mỗi request thành công | Retry tăng tải DB bao nhiêu? |
| Lock wait và thời gian transaction | Có transaction dài hoặc một hàng quá nóng? |
| Median, p95, p99 của request | Người dùng có phải chịu độ trễ lớn vì retry? |
| Throughput, CPU, I/O, connection pool | Thay đổi có làm giảm năng lực xử lý tổng thể? |
| Số lần invariant bị vi phạm | Có lỗi đúng đắn ở đường ghi chưa được bảo vệ? |

Với khối lượng ghi xung đột cao, thay đổi mô hình dữ liệu hoặc biến đổi nghiệp vụ thành thao tác nguyên tử có thể phù hợp hơn việc tăng mức cô lập.

## 10. Replica, cache và nhiều tài nguyên: ranh giới của bảo đảm

Giả sử một API ghi đơn hàng vào primary bằng transaction SERIALIZABLE. Ngay sau đó, request khác đọc từ read replica đang chậm đồng bộ và thấy trạng thái cũ. Đây là vấn đề **stale read giữa các tài nguyên**, không phải lỗi write skew giữa những transaction trên cùng primary.

Tương tự, cache chưa invalidated có thể trả phiên bản cũ. Nếu một quyết định cần bảo đảm đã thấy trạng thái mới, phải xác định đọc ở đâu và consistency của nguồn đọc đó. Annotation @Transactional không tự nâng cấp consistency của cache hoặc replica.

Những thay đổi ở cơ sở dữ liệu khác, message broker, HTTP API và object storage cũng không tự thuộc transaction local. Isolation của DB bảo vệ lịch truy cập trong phạm vi DB transaction; cần idempotency, outbox hoặc phối hợp nghiệp vụ phù hợp cho tài nguyên bên ngoài.

## 11. Kiểm thử concurrency để chứng minh lựa chọn

Kiểm thử đơn luồng không tái hiện write skew hoặc lost update. Với bất biến nhiều hàng, cần dùng **hai connection và hai transaction độc lập**, phối hợp các bước bằng barrier/latch để buộc lịch thực thi nguy hiểm xảy ra.

~~~text
Ban đầu: shift=7 có bác sĩ A và B, cả hai on_call=true.

Thread T1                        Thread T2
---------                        ---------
BEGIN                            BEGIN
COUNT on_call -> 2               COUNT on_call -> 2
          \                      /
           barrier: cả hai đã đọc
          /                      \
UPDATE A=false                   UPDATE B=false
COMMIT                           COMMIT

Kiểm tra cuối: COUNT(on_call=true) >= 1
~~~

Trên PostgreSQL REPEATABLE READ, nếu không có guard hoặc ràng buộc khác, cả hai transaction có thể commit và phá luật. Với SERIALIZABLE, database không cho cả hai commit trong lịch gây write skew; sau retry, logic sẽ đọc lại số người và từ chối cho bác sĩ cuối cùng nghỉ.

Với **guard row + READ COMMITTED**, phải khóa guard trước COUNT. Khi kiểm thử, đặt điểm đồng bộ tại chỗ tranh khóa guard, không cố ép cả hai cùng đọc COUNT trước khi khóa vì như vậy đã thay đổi giao thức cần kiểm tra.

Các kịch bản nên có:

1. Hai request cùng trừ món hàng cuối cùng: đúng một lần bán thành công.
2. Hai request cùng tạo mã đơn trùng: dữ liệu vẫn duy nhất.
3. Hai request cập nhật trạng thái bằng version cũ: một lần cập nhật phải phát hiện xung đột.
4. Hai bác sĩ cùng xin nghỉ: bất biến số người đang trực không bị phá.
5. Hai câu SELECT báo cáo xen giữa một transaction khác commit: đánh giá độ nhất quán snapshot.
6. Serialization failure rồi retry nguyên transaction: không lặp tác động ngoài DB.
7. Một worker nền đi đường ghi riêng: vẫn tuân thủ constraint/guard.
8. Mất phản hồi lúc commit: client và server tránh nhân đôi tác vụ bằng idempotency khi cần.

Đừng chỉ chèn Thread.sleep ngẫu nhiên rồi hy vọng bắt được race. Phải dùng lịch có kiểm soát và chạy trên DBMS thực khi hành vi phụ thuộc vào MVCC/locking/SSI. Kết quả cần kiểm chứng là **bất biến sau commit**, không chỉ số exception trong log.

## 12. Quy trình chọn mức cô lập trong dự án Java

**Bước 1 — Viết bất biến.** Ví dụ: “Sau mỗi commit, available không âm”, “Không có hai booking confirmed trùng khoảng” hoặc “Mỗi shift còn ít nhất một người on-call”.

**Bước 2 — Liệt kê writer và đường đọc/ghi.** Bao gồm REST API, scheduled job, consumer và migration. Xác nhận SQL thực sự phát ra từ JPA/JDBC, các predicate được kiểm tra và những hàng có thể được ghi.

**Bước 3 — Vẽ hai transaction cùng chạy.** Xác định chúng có thể cùng đọc điều kiện ban đầu hay không; có ghi cùng hàng, ghi hàng khác, hay INSERT vào vùng hiện chưa có hàng.

**Bước 4 — Chọn bảo vệ đủ mạnh, đơn giản.** Thử constraint và cập nhật nguyên tử trước. Với một entity có version, cân nhắc CAS. Với một nhóm có hàng đại diện, cân nhắc guard row. Với predicate phức tạp, cân nhắc SERIALIZABLE và retry toàn transaction.

**Bước 5 — Giữ transaction ngắn.** Đảm bảo phần đọc kiểm tra và ghi phụ thuộc cùng transaction. Tránh chờ HTTP, broker hoặc thao tác khác ngoài DB. Kiểm tra transaction manager, DataSource, proxy và propagation của Spring.

**Bước 6 — Đo trước khi chốt.** Chạy kiểm thử cạnh tranh ở tải gần thực tế, theo dõi lock wait, serialization failure, số attempt, p95/p99 và throughput. Một giải pháp đúng đắn nhưng gây contention quá lớn có thể cần thiết kế lại phạm vi bất biến hoặc dữ liệu.

~~~mermaid
flowchart TD
    A["Viết bất biến và mọi writer"] --> B{"Constraint hoặc SQL nguyên tử có đủ?"}
    B -->|Có| C["UNIQUE / CHECK / UPDATE có điều kiện"]
    B -->|Không| D{"Có guard row hoặc version phù hợp?"}
    D -->|Có| E["Lock guard hoặc optimistic CAS"]
    D -->|Không| F["SERIALIZABLE + retry transaction"]
    C --> G["Kiểm thử race + đo chi phí"]
    E --> G
    F --> G
    G --> H{"Bất biến đúng và hiệu năng đạt?"}
    H -->|Có| I["Triển khai và theo dõi"]
    H -->|Không| A
~~~

## 13. Hiểu lầm thường gặp

| Nhận định | Cách hiểu đúng |
|---|---|
| “REPEATABLE READ thì không bao giờ có race.” | PostgreSQL REPEATABLE READ vẫn có thể gặp write skew. |
| “SERIALIZABLE khóa tất cả transaction chạy lần lượt.” | DB có thể chạy song song và abort một attempt không tuần tự hóa được. |
| “READ COMMITTED quá yếu cho tồn kho.” | Atomic UPDATE + CHECK đủ cho nhiều bất biến một hàng. |
| “SELECT rồi INSERT ngăn được trùng mã.” | Hai transaction có thể cùng thấy chưa có; cần UNIQUE constraint. |
| “FOR UPDATE khóa được cả hàng chưa có.” | Khóa các hàng hiện tại không mặc nhiên khóa cả predicate tương lai ở mọi DB. |
| “Isolation khai báo ở method con luôn được áp dụng.” | Khi tham gia transaction có sẵn, isolation thường do transaction ngoài quyết định. |
| “Retry riêng câu UPDATE sau 40001 là đủ.” | Phải retry toàn transaction, bao gồm phần đọc và ra quyết định. |
| “SERIALIZABLE giúp replica/cache luôn đọc mới nhất.” | Isolation local không bảo đảm consistency của nguồn dữ liệu ngoài transaction. |

## 14. Bài tập tự kiểm tra

**Bài A — Tồn kho.** Một SKU còn đúng một sản phẩm. Hai request đọc available=1 rồi cả hai ghi available=0 và tạo hai đơn thành công. Hãy nêu bất biến bị phá và SQL phù hợp hơn.

*Gợi ý:* Dùng một câu UPDATE giảm available có điều kiện available >= 1 và kiểm tra có hàng nào được cập nhật. Giữ CHECK available >= 0; thao tác tạo đơn và trừ kho cần nằm trong ranh giới transaction phù hợp.

**Bài B — Lịch trực.** Hai bác sĩ đang trực. Hai transaction PostgreSQL REPEATABLE READ cùng đếm count=2, sau đó cập nhật hai hàng khác nhau. Vì sao snapshot vẫn chưa bảo đảm đúng?

*Gợi ý:* Write skew: mỗi giao dịch hợp lệ theo snapshot riêng nhưng trạng thái tổng không hợp lệ. Dùng guard row hoặc SERIALIZABLE + retry.

**Bài C — Booking.** Hai request cùng thấy chưa có booking trùng khoảng, rồi cùng INSERT. SELECT FOR UPDATE trả 0 hàng. Có thể coi hai INSERT đã được bảo vệ không?

*Gợi ý:* Không. Cần constraint khoảng phù hợp (nếu DB hỗ trợ), guard row theo phòng hoặc serializable với retry và kiểm chứng thời gian/điều kiện biên.

**Bài D — Spring.** Một method đánh dấu SERIALIZABLE tham gia transaction READ COMMITTED đã mở ở tầng ngoài. Có chắc method trong được nâng mức cô lập?

*Gợi ý:* Không. Kiểm tra transaction manager, proxy, propagation và thiết lập kiểm tra transaction hiện có nếu cần.

**Bài E — Retry.** Một transaction SERIALIZABLE bị SQLSTATE 40001. Code bắt lỗi trong method rồi chạy lại riêng UPDATE. Cần sửa thế nào?

*Gợi ý:* Giao dịch đã thất bại; để exception thoát ra, khởi động transaction mới và làm lại tất cả bước đọc/kiểm tra/ghi. Không lặp side effect không idempotent.

## 15. Checklist trước khi triển khai

- [ ] Bất biến được mô tả rõ cho trạng thái sau commit.
- [ ] Đã kiểm kê mọi đường ghi, kể cả job và consumer.
- [ ] Có lịch T1/T2 minh họa trường hợp cạnh tranh nguy hiểm.
- [ ] Đã xem constraint, SQL nguyên tử và optimistic CAS trước khi nâng isolation.
- [ ] Nếu dùng guard, mọi writer khóa cùng điểm trước khi đọc quyết định.
- [ ] Nếu dùng REPEATABLE READ, hiểu semantics và khả năng write skew của DB thực.
- [ ] Nếu dùng SERIALIZABLE, có retry toàn transaction, giới hạn attempt và metrics.
- [ ] Đã kiểm tra Spring proxy, DataSource, transaction manager và propagation.
- [ ] Không có side effect ngoài DB bị lặp khi retry.
- [ ] Không quyết định trên replica/cache stale khi cần đọc dữ liệu mới.
- [ ] Đã kiểm thử race có kiểm soát và đo lock wait, p95/p99, throughput.
- [ ] Có xử lý cho lỗi nghiệp vụ, xung đột và commit outcome chưa rõ.

**Ghi nhớ:** chọn mức cô lập phải bắt đầu từ bất biến và mẫu truy cập. Constraint hoặc câu ghi nguyên tử thường đủ cho luật một hàng; luật trên nhiều hàng và predicate có thể cần khóa điểm phối hợp hoặc SERIALIZABLE cùng retry. Việc lựa chọn chỉ hoàn chỉnh khi lịch cạnh tranh được kiểm chứng và chi phí vận hành được đo trên workload đại diện.

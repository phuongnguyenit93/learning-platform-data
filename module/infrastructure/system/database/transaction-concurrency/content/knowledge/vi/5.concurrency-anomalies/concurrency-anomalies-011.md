# Ảnh chụp dữ liệu cũ khác gì với đọc dữ liệu chưa xác nhận

Trong môi trường có nhiều transaction chạy đồng thời, một truy vấn có thể không nhìn thấy giá trị mới nhất vừa được ghi vào bảng. Điều đó không nhất thiết là lỗi. Cơ sở dữ liệu có thể cho transaction đọc từ một **ảnh chụp dữ liệu (snapshot)** được xác định tại một thời điểm để giữ kết quả đọc nhất quán trong khi transaction khác tiếp tục ghi.

Hiện tượng này khác với **đọc dữ liệu chưa xác nhận (dirty read)**. Dirty read xảy ra khi transaction đọc được thay đổi của transaction khác trước khi thay đổi đó được commit. Nếu transaction ghi sau đó rollback, transaction đọc đã dựa vào dữ liệu chưa bao giờ trở thành kết quả đã xác nhận.

- **Đọc snapshot cũ:** đọc phiên bản dữ liệu đã commit tại thời điểm snapshot được xác định. Phiên bản có thể cũ hơn trạng thái commit mới nhất, nhưng không phải dữ liệu chưa xác nhận.
- **Dirty read:** đọc thay đổi chưa commit của transaction khác. Giá trị có thể biến mất nếu transaction ghi rollback.

Vì vậy, **“không mới nhất” không đồng nghĩa với “chưa xác nhận”**.

## 1. Hai tình huống khác nhau

Giả sử tài khoản A có số dư 1.000. T1 cập nhật số dư thành 800 nhưng chưa commit. T2 đang truy vấn số dư.

### 1.1. Dirty read

```text
T1                                  T2
──────────────────────────────      ──────────────────────────────
BEGIN
UPDATE balance = 800
                                    BEGIN
                                    SELECT balance → 800
                                    -- Đọc giá trị T1 chưa commit
ROLLBACK
                                    -- T2 đã sử dụng giá trị 800
```

T1 rollback, nên số dư chính thức vẫn là 1.000. Nhưng T2 đã đọc và có thể đã dùng giá trị 800. Đây là dirty read vì T2 quan sát thay đổi chưa được xác nhận.

### 1.2. Snapshot cũ

T1 cập nhật thành 800 rồi commit. Tuy nhiên, snapshot mà T2 đã xác lập từ trước commit vẫn mô tả trạng thái cũ.

```text
T1                                  T2
──────────────────────────────      ──────────────────────────────
                                    BEGIN
                                    Snapshot S: A = 1000
UPDATE A = 800
COMMIT
                                    SELECT A theo snapshot S
                                    → 1000
```

T2 đọc 1.000 dù giá trị mới nhất đã commit là 800. Nhưng 1.000 là giá trị đã commit hợp lệ ở thời điểm snapshot được xác định. T2 không đọc thay đổi chưa commit của T1.

## 2. Snapshot là gì?

Snapshot (còn gọi là read view hoặc consistent view trong một số hệ quản trị) mô tả tập phiên bản dữ liệu mà một câu truy vấn hoặc transaction được phép nhìn thấy theo quy tắc isolation.

Với **MVCC (Multi-Version Concurrency Control)**, DBMS duy trì hoặc tái dựng nhiều phiên bản logic của một hàng:

```text
Phiên bản hàng A:

v1: balance = 1000   (được commit trước)
v2: balance = 800    (do T1 ghi, chưa commit)
v3: balance = 900    (một thay đổi khác về sau)

Snapshot của T2 có thể chọn v1.
Truy vấn ở một thời điểm khác có thể chọn phiên bản đã commit mới hơn.
```

Đây là mô hình khái niệm. PostgreSQL lưu tuple versions trong heap và dùng transaction metadata cùng snapshot để xác định visibility. InnoDB dùng dữ liệu hiện tại kết hợp undo information để dựng phiên bản cũ khi consistent read cần.

### 2.1. Snapshot không nhất thiết là bản sao vật lý

Không nên hình dung DBMS sao chép toàn bộ bảng tại thời điểm bắt đầu transaction. Snapshot thường là **quy tắc visibility** dựa trên trạng thái transaction và các phiên bản dữ liệu.

Khi một hàng bị cập nhật, hệ quản trị có thể giữ thông tin phiên bản cũ để transaction có snapshot thích hợp đọc nó. Khi không còn snapshot nào cần phiên bản đó, cơ chế cleanup mới có thể thu hồi dữ liệu cũ.

### 2.2. Snapshot không khóa mọi hàng

Một consistent read trong hệ MVCC thường đọc phiên bản phù hợp mà không cần lấy khóa ghi trên hàng. Vì vậy, transaction đọc có thể tiếp tục trong lúc transaction khác cập nhật hàng.

Điều đó không có nghĩa mọi kiểu đọc đều không khóa. Ví dụ SELECT ... FOR UPDATE là locking read, có mục đích khóa hàng để phối hợp cập nhật; nó khác consistent snapshot read.

## 3. Dirty read và các bất thường đọc liên quan

| Hiện tượng | Ý nghĩa | Có nhất thiết đọc dữ liệu chưa commit? |
|---|---|---|
| **Dirty read** | Đọc thay đổi chưa commit của transaction khác | Có |
| **Non-repeatable read** | Đọc cùng một hàng hai lần nhưng giá trị khác do transaction khác commit xen giữa | Không |
| **Phantom read** | Cùng truy vấn theo điều kiện nhưng tập hàng thay đổi do transaction khác commit | Không |
| **Stale snapshot** | Đọc một phiên bản đã commit cũ hơn trạng thái commit hiện tại | Không |
| **Lost update** | Một cập nhật bị ghi đè hoặc mất do tương tác đồng thời | Không nhất thiết |

Dirty read liên quan đến **trạng thái commit của phiên bản được đọc**. Non-repeatable read và phantom read liên quan đến sự thay đổi giữa các lần quan sát; mỗi lần đọc vẫn có thể chỉ thấy dữ liệu đã commit.

## 4. Non-repeatable read: dữ liệu đã commit nhưng thay đổi giữa hai lần đọc

Ban đầu tài khoản A = 1.000.

```text
T1                                  T2 (READ COMMITTED)
──────────────────────────────      ───────────────────────────────
BEGIN
                                    BEGIN
                                    SELECT balance → 1000
UPDATE A = 800
COMMIT
                                    SELECT balance → 800
                                    COMMIT
```

T2 đọc hai giá trị khác nhau. Lần đầu là 1.000 đã commit; lần thứ hai là 800 cũng đã commit. T2 không đọc dữ liệu chưa xác nhận. Đây là non-repeatable read.

Trong PostgreSQL READ COMMITTED, mỗi statement lấy snapshot mới, nên ví dụ này có thể xảy ra. Với PostgreSQL REPEATABLE READ, các consistent read trong transaction giữ góc nhìn snapshot ổn định hơn.

## 5. Isolation level quyết định transaction có thể quan sát gì

Isolation level quy định các transaction đồng thời được phép nhìn thấy những thay đổi nào. Tuy nhiên, tên isolation giống nhau không bảo đảm mọi hệ quản trị triển khai từng chi tiết giống hệt nhau.

| Isolation level | Dirty read | Snapshot/stale read | Các lần đọc lặp lại |
|---|---|---|---|
| **READ UNCOMMITTED** | Được phép theo mô hình chuẩn; có DBMS không thực sự cung cấp dirty read | Có thể | Không bảo đảm ổn định |
| **READ COMMITTED** | Không đọc thay đổi chưa commit theo mô hình thông thường | Có thể đọc commit cũ tùy thời điểm snapshot của statement | Các statement có thể thấy commit mới xen giữa |
| **REPEATABLE READ** | Không đọc dirty data | Có thể cố ý giữ snapshot cũ trong transaction | Consistent read thường ổn định hơn; phantom/xung đột ghi tùy DBMS |
| **SERIALIZABLE** | Không cho phép dirty read | Có thể dùng snapshot/kiểm tra để đạt tương đương tuần tự | Phải tương đương một lịch tuần tự hợp lệ hoặc transaction bị từ chối |

### 5.1. READ UNCOMMITTED

Theo mô hình SQL, mức này cho phép dirty read. Ứng dụng phải chấp nhận khả năng nhìn thấy giá trị của transaction khác chưa commit, bao gồm giá trị có thể bị rollback.

Nhưng không phải DBMS nào cũng thực sự đọc dirty data khi cấu hình mức này:

- PostgreSQL chấp nhận cú pháp READ UNCOMMITTED nhưng xử lý như READ COMMITTED.
- MySQL/InnoDB có thể thực hiện dirty read ở isolation level này.

Vì vậy, phải kiểm tra tài liệu của DBMS đang dùng.

### 5.2. READ COMMITTED

Đây là mức mặc định phổ biến, trong đó có PostgreSQL. Mỗi statement thường đọc dữ liệu đã commit tại snapshot của statement đó. Hai SELECT trong một transaction có thể nhìn thấy hai tập phiên bản khác nhau nếu transaction khác commit xen giữa.

```sql
BEGIN;

SELECT balance FROM accounts WHERE id = 1;
-- Có thể thấy 1000.

-- Transaction khác commit số dư 800.

SELECT balance FROM accounts WHERE id = 1;
-- PostgreSQL READ COMMITTED có thể thấy 800.

COMMIT;
```

Không có dirty read, nhưng hai câu SELECT không nhất thiết dùng cùng snapshot.

### 5.3. REPEATABLE READ

Mức này giữ tính nhất quán của các lần đọc lặp lại theo quy tắc DBMS. Với PostgreSQL, consistent reads trong transaction thường sử dụng snapshot ổn định; T2 có thể tiếp tục thấy 1.000 dù T1 đã commit 800 sau thời điểm snapshot.

InnoDB cũng cung cấp consistent read với read view, thường dùng snapshot được xác lập ở lần consistent read đầu tiên trong transaction ở REPEATABLE READ. Tuy nhiên, locking read như SELECT ... FOR UPDATE có quy tắc riêng.

Điểm quan trọng: **đọc cùng một phiên bản cũ ổn định** khác với đọc một thay đổi chưa commit.

### 5.4. SERIALIZABLE

Serializable bảo đảm kết quả tương đương một thứ tự tuần tự hợp lệ của các transaction. DBMS có thể chạy song song và kiểm tra xung đột; nếu không thể bảo đảm tính tương đương, một transaction có thể bị hủy với serialization error. Ứng dụng cần retry toàn bộ transaction khi phù hợp.

## 6. Thực hành hai session PostgreSQL

Ví dụ dùng PostgreSQL, với hai session độc lập.

### 6.1. Chuẩn bị

```sql
DROP TABLE IF EXISTS account_demo;

CREATE TABLE account_demo (
    id BIGINT PRIMARY KEY,
    balance NUMERIC(12, 2) NOT NULL
);

INSERT INTO account_demo(id, balance)
VALUES (1, 1000.00);
```

### 6.2. Thử đọc thay đổi chưa commit

**Session 1 (T1):**

```sql
BEGIN;
UPDATE account_demo
SET balance = 800.00
WHERE id = 1;

-- Chưa commit.
```

**Session 2 (T2):**

```sql
BEGIN ISOLATION LEVEL READ UNCOMMITTED;

SELECT balance
FROM account_demo
WHERE id = 1;

-- PostgreSQL vẫn trả 1000.00, không trả 800.00.
COMMIT;
```

T2 không nhìn thấy thay đổi chưa commit của T1. PostgreSQL triển khai READ UNCOMMITTED như READ COMMITTED.

Quay lại T1:

```sql
ROLLBACK;
```

Giá trị cuối vẫn là 1.000. Lịch này không tạo dirty read.

### 6.3. Thử stale snapshot trong REPEATABLE READ

Chạy lại trên hai session.

**Session 1 (T1):**

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT balance
FROM account_demo
WHERE id = 1;
-- 1000.00; snapshot của T1 được xác lập.
```

**Session 2 (T2):**

```sql
BEGIN;

UPDATE account_demo
SET balance = 800.00
WHERE id = 1;

COMMIT;
```

**Quay lại Session 1 (T1):**

```sql
SELECT balance
FROM account_demo
WHERE id = 1;
-- Vẫn thấy 1000.00 trong snapshot của T1.

COMMIT;
```

Sau đó truy vấn trong transaction mới:

```sql
SELECT balance
FROM account_demo
WHERE id = 1;
-- 800.00
```

T1 đọc dữ liệu cũ vì snapshot được xác lập trước commit của T2. Giá trị 1.000 đã commit hợp lệ trước đó; đây không phải dirty read.

Nếu T1 cũng cố cập nhật hàng mà T2 đã thay đổi và commit sau snapshot của T1, PostgreSQL REPEATABLE READ có thể phát sinh serialization error thay vì cho phép ghi đè phiên bản mới. Ứng dụng phải rollback và retry toàn bộ transaction nếu nghiệp vụ cho phép.

## 7. InnoDB: consistent read khác locking read

MySQL/InnoDB cung cấp một cách triển khai MVCC khác.

### 7.1. Consistent read trong REPEATABLE READ

Ở isolation mặc định REPEATABLE READ của InnoDB, một consistent read không khóa thường đọc từ read view. Nhiều lần consistent read trong transaction thường dùng cùng góc nhìn đó sau khi read view được xác lập.

```sql
-- Session T1
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT balance FROM account_demo WHERE id = 1;
-- Giả sử thấy 1000.
```

Trong khi đó T2 cập nhật 800 và commit. T1 tiếp tục consistent read có thể vẫn thấy 1.000:

```sql
-- Session T1
SELECT balance FROM account_demo WHERE id = 1;
-- Đọc phiên bản theo read view của T1.
COMMIT;
```

### 7.2. READ UNCOMMITTED trong InnoDB

Nếu T2 được cấu hình READ UNCOMMITTED, T2 có thể thấy dữ liệu T1 cập nhật nhưng chưa commit. Nếu T1 rollback, T2 đã đọc một giá trị không trở thành trạng thái xác nhận. Đây là dirty read.

### 7.3. Locking read không giống consistent read

InnoDB phân biệt:

- **Consistent nonlocking read:** đọc theo read view/MVCC, thường không lấy khóa hàng để cập nhật.
- **Locking read:** SELECT ... FOR UPDATE hoặc SELECT ... FOR SHARE yêu cầu khóa tương ứng.
- **UPDATE/DELETE:** lấy các khóa cần thiết; ở REPEATABLE READ có thể có next-key/gap lock tùy access path và predicate.

Không nên lấy kết quả SELECT consistent read rồi giả định SELECT FOR UPDATE tiếp theo bắt buộc nhìn cùng phiên bản theo cùng quy tắc.

## 8. Vì sao snapshot cũ hữu ích?

Snapshot cũ không phải lúc nào cũng là thiếu sót. Nó giúp một transaction duy trì góc nhìn nhất quán trong khi transaction khác đang ghi.

### 8.1. Báo cáo nhiều truy vấn

Một báo cáo có thể cần đọc tổng số đơn hàng, tổng doanh thu và danh sách nhóm sản phẩm. Nếu từng truy vấn nhìn một trạng thái commit khác nhau, các con số có thể không khớp cùng thời điểm.

Snapshot ổn định giúp các phép đọc cùng tham chiếu một trạng thái logic. Tùy DBMS/isolation, cần chọn transaction snapshot phù hợp.

### 8.2. Pagination và xử lý batch

Một job quét dữ liệu nhiều trang có thể muốn dữ liệu không thay đổi giữa các trang. Snapshot ổn định giúp tránh bản ghi xuất hiện hoặc biến mất giữa chừng do commit xen giữa.

Tuy nhiên, transaction snapshot dài có chi phí: có thể giữ phiên bản cũ lâu hơn, làm chậm vacuum/purge và tăng áp lực lưu trữ. Với batch dài, cân nhắc keyset pagination, watermark, staging hoặc snapshot riêng thay vì giữ transaction mở quá lâu.

### 8.3. Nhất quán khác với mới nhất

Một báo cáo nhất quán có thể trả số liệu hơi cũ nhưng tất cả phần đọc phù hợp cùng một snapshot. Một báo cáo lấy từng phần mới nhất có thể có các phần không phản ánh cùng một thời điểm.

Yêu cầu sản phẩm cần nói rõ ưu tiên **freshness** (độ mới dữ liệu), **consistency** (nhất quán giữa các phần đọc), hay sự kết hợp nào.

## 9. Hệ quả vận hành của snapshot cũ

### 9.1. Transaction lâu giữ snapshot lâu

Trong PostgreSQL, transaction có snapshot cũ có thể ngăn vacuum loại bỏ tuple versions mà snapshot đó còn cần. Trong InnoDB, read view cũ có thể giữ undo history cần thiết cho consistent read và làm purge chưa dọn được một số phiên bản.

Một transaction chỉ đọc nhưng kéo dài vẫn có thể tạo áp lực dọn dẹp MVCC.

### 9.2. History và dung lượng tăng

Nếu nhiều transaction/snapshot tồn tại lâu:

- PostgreSQL có thể tích tụ dead tuples, tăng công việc vacuum.
- InnoDB có thể tăng history list length và lượng undo history cần giữ.
- Batch dài có thể khiến cleanup bị trì hoãn.

Cần quan sát transaction age, vacuum/purge status và workload, không kết luận chỉ từ một snapshot cũ.

### 9.3. Snapshot có thể làm quyết định nghiệp vụ lỗi thời

T1 đọc giá sản phẩm 100. Sau đó T2 commit giá 120. T1 tiếp tục tính đơn hàng theo snapshot cũ là 100. Nếu nghiệp vụ yêu cầu áp dụng giá tại thời điểm xác nhận cuối cùng, T1 cần tái xác nhận hoặc dùng khóa/version phù hợp.

Snapshot ổn định bảo đảm góc nhìn nhất quán, **không bảo đảm góc nhìn đó còn phù hợp với quyết định tại thời điểm commit**.

## 10. Phòng tránh dirty read và quản lý snapshot

### 10.1. Chọn isolation level theo yêu cầu

Nếu không muốn đọc dữ liệu chưa commit, dùng isolation level tối thiểu bảo đảm điều đó theo DBMS, thường là READ COMMITTED hoặc mạnh hơn. Kiểm tra implementation cụ thể và anomaly mà nghiệp vụ cần tránh.

### 10.2. Không dùng dirty read tùy tiện để tăng hiệu năng

Dirty data có thể tạo số liệu sai hoặc dao động theo rollback. Với DBMS MVCC, consistent read thường đã cho phép nhiều truy vấn đọc mà không phải chặn writer theo mô hình khóa truyền thống.

Cân nhắc reporting replica, snapshot hoặc dữ liệu tổng hợp nếu cần giảm tải.

### 10.3. Dùng optimistic locking khi cập nhật dựa trên dữ liệu đã đọc

```sql
UPDATE products
SET price = 120.00,
    version = version + 1
WHERE id = 10
  AND version = 7;
```

Nếu cập nhật 0 hàng, dữ liệu đã thay đổi kể từ phiên bản ứng dụng đọc. Ứng dụng cần tải lại và giải quyết xung đột hoặc báo người dùng. Trong JPA, annotation @Version hỗ trợ optimistic locking theo mẫu tương tự.

### 10.4. Tái kiểm tra điều kiện khi ghi

```sql
UPDATE accounts
SET balance = balance - 200.00
WHERE id = 1
  AND balance >= 200.00;
```

Điều kiện được gắn ngay vào thao tác ghi thay vì chỉ tin một lần SELECT cũ. Ứng dụng phải kiểm tra row count và xử lý transaction phù hợp.

## 11. Đối chiếu các tình huống

| Tình huống | T2 đọc gì | Trạng thái phiên bản | Phân loại |
|---|---:|---|---|
| T1 cập nhật 800 chưa commit; T2 đọc 800 | 800 | Chưa commit | Dirty read |
| T1 cập nhật 800 rồi rollback; T2 từng đọc 800 | 800 | Không được xác nhận | Dirty read |
| T1 commit 800; snapshot T2 được tạo trước commit | 1000 | Phiên bản đã commit | Snapshot cũ |
| T1 commit 800; T2 READ COMMITTED đọc trước rồi đọc sau | 1000 rồi 800 | Cả hai đã commit | Non-repeatable read |
| T1 commit 800; transaction mới đọc sau đó | 800 | Phiên bản mới tại snapshot mới | Current committed view |
| T1 chưa commit; PostgreSQL T2 READ UNCOMMITTED đọc | Giá trị đã commit trước đó | PostgreSQL không cho dirty read | Hành vi như READ COMMITTED |

## 12. Bài tập phân tích

### Tình huống A: Có dirty read không?

T1 cập nhật giá sản phẩm từ 100 thành 120 nhưng chưa commit. T2 đọc giá 100 từ snapshot được xác lập trước đó.

**Trả lời:** Không. Nếu 100 là phiên bản đã commit mà snapshot cho phép đọc, T2 đang đọc snapshot cũ. T2 không đọc thay đổi chưa commit 120.

### Tình huống B: T2 đọc 120 rồi T1 rollback

T1 cập nhật 100 thành 120 nhưng chưa commit. T2 đọc được 120. Sau đó T1 rollback.

**Trả lời:** Đây là dirty read. T2 đã sử dụng một thay đổi không được xác nhận và bị hủy.

### Tình huống C: Hai lần SELECT khác giá trị

T2 đọc 100, T1 commit 120, T2 đọc lại thành 120 ở READ COMMITTED.

**Trả lời:** Đây là non-repeatable read. Hai giá trị đều đã commit tại thời điểm tương ứng; không phải dirty read.

### Tình huống D: Báo cáo nhiều truy vấn

Một báo cáo đọc tổng doanh thu, sau đó đọc số đơn hàng. Transaction khác commit đơn hàng mới giữa hai truy vấn.

**Trả lời:** Ở isolation tạo snapshot mới cho mỗi statement, điều này có thể xảy ra. Nếu báo cáo phải nhất quán tại một thời điểm, cần transaction/snapshot với semantics phù hợp.

### Tình huống E: Snapshot rất cũ

Job đọc dữ liệu trong transaction mở suốt 45 phút. Writer vẫn commit nhưng vacuum/purge cleanup chậm.

**Trả lời:** Snapshot lâu đời có thể giữ phiên bản cũ mà DBMS chưa được phép dọn. Cần rút ngắn transaction, chia batch hoặc thiết kế snapshot/reporting riêng.

## Kết luận

**Snapshot cũ là góc nhìn có chủ đích về các phiên bản đã commit; dirty read là việc quan sát thay đổi chưa commit của transaction khác.** Snapshot cũ có thể không mới nhất nhưng vẫn nhất quán theo isolation level. Dirty read có thể dẫn đến quyết định dựa trên dữ liệu sẽ bị rollback.

Khi phân tích một kết quả đọc, hãy hỏi: snapshot được xác định lúc nào, phiên bản hàng đã commit chưa, và isolation level/DBMS cho phép transaction nhìn thấy phiên bản nào. Đồng thời phân biệt dirty read với non-repeatable read, phantom read và write skew. Cách phân tích này giúp lựa chọn isolation, thiết kế báo cáo và xử lý đồng thời chính xác hơn.

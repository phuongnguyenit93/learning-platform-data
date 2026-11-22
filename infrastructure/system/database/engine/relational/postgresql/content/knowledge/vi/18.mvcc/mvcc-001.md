# Vì sao cần nhiều phiên bản hàng khi đọc và ghi đồng thời trong PostgreSQL

Khi nhiều người cùng sử dụng một ứng dụng, cơ sở dữ liệu phải giải quyết một yêu cầu tưởng như mâu thuẫn: **người đọc cần thấy dữ liệu nhất quán, trong khi người ghi vẫn phải được phép cập nhật dữ liệu**. Nếu một transaction đang đọc số dư tài khoản, việc transaction khác thay đổi số dư có nên khiến truy vấn đang chạy đọc được một nửa trạng thái cũ và một nửa trạng thái mới? Nếu mỗi lần cập nhật đều phải chờ mọi độc giả kết thúc, hệ thống sẽ xử lý được bao nhiêu yêu cầu đồng thời?

PostgreSQL giải quyết phần quan trọng của bài toán bằng **MVCC — Multi-Version Concurrency Control**, tức *kiểm soát đồng thời bằng nhiều phiên bản*. Thay vì chỉ giữ một giá trị đang thay đổi tại một vị trí logic duy nhất, PostgreSQL có thể lưu **nhiều phiên bản vật lý của cùng một hàng logic** và xác định phiên bản nào được phép hiển thị theo **snapshot** của transaction hoặc statement.

Nhờ vậy, trong nhiều trường hợp thông thường:

- Một câu `SELECT` đang đọc không cần chờ transaction khác `UPDATE` cùng hàng.
- Một `UPDATE` không phải chờ mọi câu `SELECT` thông thường hoàn tất mới được sửa hàng.
- Người đọc không nhìn thấy thay đổi chưa commit của người khác (*dirty read*).
- Một transaction có thể tiếp tục nhìn phiên bản cũ, còn transaction khác đã commit phiên bản mới.
- PostgreSQL vẫn dùng **khóa**, kiểm tra xung đột và quy tắc isolation khi hai bên cùng ghi — MVCC **không phải** cơ chế bỏ qua mọi khóa.

Bài học thuộc chương **MVCC** của module **Database Engine Relational PostgreSQL**. Sau khi học, bạn sẽ có thể tự giải thích **vì sao cần nhiều phiên bản hàng**, quan sát hai phiên `psql` hoạt động song song, phân biệt `READ COMMITTED` với `REPEATABLE READ`, hiểu ý nghĩa cơ bản của `xmin`/`xmax`/`ctid`, và biết tại sao `VACUUM` cùng việc quản lý transaction dài là một phần không thể thiếu của MVCC.

## 1. Bài toán nếu chỉ có một phiên bản hàng

Giả sử database lưu một hàng:

| account_id | owner_name | balance |
| ---: | --- | ---: |
| 1 | An | 100.00 |

Có hai hoạt động diễn ra gần như đồng thời:

- **Phiên A** chạy báo cáo, cần đọc số dư tài khoản 1.
- **Phiên B** chuyển thêm 50 vào tài khoản 1 và commit.

Nếu hệ thống chỉ giữ một bản vật lý duy nhất và cho B ghi đè trực tiếp giá trị 100 thành 150 mà không có cơ chế phối hợp, A có thể quan sát dữ liệu thay đổi giữa quá trình tính toán. Một triển khai khác có thể buộc B chờ A đọc xong hoặc buộc A chờ B ghi xong. Khi có hàng nghìn người dùng, sự chờ đợi này khiến throughput giảm và tăng nguy cơ nghẽn cổ chai.

PostgreSQL chọn cách khác: **phiên bản cũ có thể được giữ lại cho người đọc đã có snapshot**, còn một phiên bản mới được tạo cho thay đổi của người ghi.

~~~text
Cùng một hàng logic account_id = 1

                  Thời gian →
                 ┌───────────────────┐
Phiên bản cũ     │ balance = 100     │
                 │ nhìn thấy với     │
                 │ snapshot cũ       │
                 └───────────────────┘
                          │ UPDATE + COMMIT
                          ▼
                 ┌───────────────────┐
Phiên bản mới    │ balance = 150     │
                 │ nhìn thấy với     │
                 │ snapshot mới      │
                 └───────────────────┘
~~~

Điều này không có nghĩa mọi câu SQL luôn đọc cùng một phiên bản: PostgreSQL quyết định dựa trên snapshot, trạng thái transaction và mức cô lập đang dùng.

## 2. MVCC không tạo nhiều “tài khoản”; nó tạo nhiều phiên bản của một hàng logic

Trong SQL, bảng vẫn có một tài khoản với khóa chính `account_id = 1`. Dữ liệu nghiệp vụ không được xem là có hai tài khoản An chỉ vì storage tạm giữ bản 100 và bản 150.

Để tránh nhầm lẫn, phân biệt:

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| **Hàng logic (logical row)** | Thực thể mà ứng dụng làm việc, ví dụ tài khoản ID 1 |
| **Tuple/phiên bản hàng (row version)** | Bản ghi vật lý trong heap, chứa giá trị cùng metadata phục vụ MVCC |
| **Snapshot** | Thông tin quyết định transaction nào/phiên bản nào được nhìn thấy tại thời điểm đọc |
| **Transaction** | Nhóm thao tác commit hoặc rollback nguyên tử |
| **Visibility** | Quy tắc xác định một tuple có được hiển thị cho snapshot này hay không |
| **Dead tuple** | Phiên bản không còn cần thiết cho bất kỳ transaction/snapshot nào phù hợp và có thể được thu hồi theo quy trình dọn dẹp |

Một câu `UPDATE` thông thường tạo **phiên bản tuple mới**, đánh dấu phiên bản cũ theo metadata giao dịch. `SELECT` của ứng dụng chỉ trả phiên bản được phép nhìn thấy theo quy tắc MVCC.

**MVCC không phải bảng audit:** các phiên bản cũ không được giữ mãi. Khi không còn snapshot nào cần chúng, PostgreSQL có thể dọn dẹp chúng. Muốn lưu lịch sử nghiệp vụ nhiều năm, cần thiết kế audit/temporal history riêng.

## 3. Snapshot là gì?

Một transaction có thể commit hoặc chưa commit. Khi đọc một hàng, PostgreSQL không chỉ hỏi “giá trị nào được viết gần đây nhất?”, mà còn hỏi:

1. Transaction tạo phiên bản này đã commit chưa?
2. Transaction tạo phiên bản đã commit trước mốc snapshot phù hợp chưa?
3. Phiên bản này có bị một transaction khác cập nhật/xóa rồi commit theo cách khiến nó không còn nhìn thấy không?
4. Có thay đổi do **chính transaction hiện tại** thực hiện mà nó phải nhìn thấy không?
5. Mức isolation quy định snapshot được lấy theo từng statement hay được giữ cho transaction?

Snapshot không chỉ là một timestamp đơn giản. PostgreSQL quản lý thông tin transaction ID và những transaction đang hoạt động để xác định khả năng nhìn thấy. Hai transaction có thể bắt đầu trước/sau nhau nhưng thứ tự commit mới quan trọng với nhiều quyết định visibility.

### Minh họa một lần đọc

~~~mermaid
sequenceDiagram
    participant A as Phiên A - Reader
    participant B as Phiên B - Writer
    participant P as PostgreSQL
    A->>P: SELECT balance (snapshot cũ)
    P-->>A: 100
    B->>P: UPDATE balance=150
    B->>P: COMMIT
    A->>P: SELECT tiếp (snapshot phụ thuộc isolation)
    alt READ COMMITTED - statement mới
        P-->>A: Có thể thấy 150
    else REPEATABLE READ - cùng transaction/snapshot
        P-->>A: Vẫn thấy 100
    end
~~~

Trong cả hai nhánh, A **không đọc dữ liệu chưa commit** từ B. Khác biệt nằm ở **khi nào snapshot được làm mới**.

## 4. Mỗi thao tác INSERT, UPDATE, DELETE tác động tới phiên bản như thế nào?

### 4.1. INSERT

`INSERT` tạo một tuple mới. Khi transaction tạo chưa commit, một transaction khác thông thường **chưa được nhìn thấy** tuple đó. Khi commit, các snapshot mới đủ điều kiện có thể thấy nó.

~~~sql
INSERT INTO mvcc_lab.accounts
    (account_id, owner_name, balance)
VALUES (5, 'Em', 300.00);
~~~

### 4.2. UPDATE

`UPDATE` tạo một phiên bản mới mang giá trị đã sửa và làm phiên bản cũ hết hiệu lực đối với những snapshot phù hợp sau khi transaction cập nhật commit.

~~~sql
UPDATE mvcc_lab.accounts
SET balance = balance + 50
WHERE account_id = 1;
~~~

Nếu không có trigger đặc biệt, giá trị logic mới là 150 khi bắt đầu từ 100. **Phiên bản cũ có thể còn tồn tại vật lý** để phục vụ các reader có snapshot cũ.

### 4.3. DELETE

`DELETE` không có nghĩa lập tức xóa sạch mọi byte của tuple ngay tại thời điểm statement chạy. PostgreSQL đánh dấu phiên bản bị xóa theo metadata; các snapshot được phép nhìn thấy phiên bản cũ vẫn có thể tiếp tục đọc nó, còn các snapshot mới sau commit không thấy hàng logic đó nữa.

~~~sql
DELETE FROM mvcc_lab.accounts
WHERE account_id = 5;
~~~

Các phiên bản không còn cần thiết sẽ được dọn dẹp dần. Vì thế **DELETE nhiều hàng không nhất thiết làm file bảng co nhỏ ngay**.

### 4.4. ROLLBACK

Nếu transaction tạo phiên bản mới nhưng sau đó rollback, phiên bản mới không trở thành giá trị đã commit để các transaction khác nhìn thấy. Phiên bản cũ vẫn hợp lệ theo quy tắc visibility.

Việc rollback không đòi PostgreSQL phải “ghi ngược giá trị cũ lên đúng chỗ” trong mọi trường hợp. MVCC và log giao dịch cho phép xác định phiên bản nào có hiệu lực.

## 5. Tạo bộ dữ liệu lab

Ví dụ chạy trên **một database PostgreSQL chỉ dùng để học**. Đoạn chuẩn bị có `DROP SCHEMA ... CASCADE`, vì vậy **không chạy trên hệ thống sản xuất hoặc một schema dùng chung chứa dữ liệu cần giữ**.

~~~sql
-- Chỉ thực hiện trong database lab do bạn quản lý.
DROP SCHEMA IF EXISTS mvcc_lab CASCADE;
CREATE SCHEMA mvcc_lab;

CREATE TABLE mvcc_lab.accounts (
    account_id integer PRIMARY KEY,
    owner_name text NOT NULL,
    balance numeric(12,2) NOT NULL CHECK (balance >= 0),
    row_version bigint NOT NULL DEFAULT 0,
    updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO mvcc_lab.accounts
    (account_id, owner_name, balance, row_version)
VALUES
    (1, 'An',   100.00, 0),
    (2, 'Binh', 200.00, 0),
    (3, 'Chi',   50.00, 0),
    (4, 'Dung', 120.00, 0);
~~~

Dữ liệu khởi tạo:

| account_id | owner_name | balance | row_version |
| ---: | --- | ---: | ---: |
| 1 | An | 100.00 | 0 |
| 2 | Binh | 200.00 | 0 |
| 3 | Chi | 50.00 | 0 |
| 4 | Dung | 120.00 | 0 |

`row_version` ở đây là **cột ứng dụng tự định nghĩa** để minh họa optimistic locking về sau. Nó **không phải** metadata `xmin`/`xmax` của PostgreSQL.

### Chuẩn bị hai phiên làm việc

Mở **hai cửa sổ psql** (hoặc hai kết nối riêng tới cùng database):

- **Phiên A:** dùng để đọc hoặc giữ transaction mở.
- **Phiên B:** dùng để cập nhật và commit trong lúc A còn hoạt động.

Mọi câu lệnh đều áp dụng trên `mvcc_lab.accounts`. Nếu chạy các thí nghiệm theo thứ tự, một số bài sẽ cố ý commit để minh họa snapshot. Khi muốn quay về seed ban đầu, **chỉ sau khi đã kết thúc các transaction ở cả hai phiên**, có thể chạy trong database lab:

~~~sql
UPDATE mvcc_lab.accounts
SET
    balance = CASE account_id
        WHEN 1 THEN 100.00
        WHEN 2 THEN 200.00
        WHEN 3 THEN 50.00
        WHEN 4 THEN 120.00
    END,
    row_version = 0,
    updated_at = now()
WHERE account_id IN (1, 2, 3, 4);
~~~

Đây là thao tác reset **chỉ dành cho dữ liệu lab**. Không dùng nó trên hệ thống thật; không thực hiện khi hai phiên lab vẫn đang chờ nhau vì có thể tạo thêm tranh chấp khóa.

## 6. Thí nghiệm 1: READ COMMITTED nhìn giá trị mới giữa hai SELECT

Mức isolation mặc định của PostgreSQL là **`READ COMMITTED`**. Trong một transaction, mỗi statement đọc dữ liệu thường sử dụng snapshot mới tại lúc statement đó bắt đầu.

Bắt đầu với tài khoản Binh (ID 2) có balance 200.00.

**Phiên A — đọc lần đầu và giữ transaction mở:**

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT account_id, balance
FROM mvcc_lab.accounts
WHERE account_id = 2;

-- Kết quả ban đầu: 200.00.
-- Giữ transaction A mở, chuyển sang phiên B.
~~~

**Phiên B — cập nhật và commit:**

~~~sql
BEGIN;

UPDATE mvcc_lab.accounts
SET
    balance = balance + 25,
    updated_at = now()
WHERE account_id = 2
RETURNING account_id, balance;

COMMIT;
~~~

B đã commit `balance = 225.00`.

**Trở lại phiên A:**

~~~sql
SELECT account_id, balance
FROM mvcc_lab.accounts
WHERE account_id = 2;

COMMIT;
~~~

Lần SELECT thứ hai của A trả **225.00**, dù cả hai SELECT được thực hiện bên trong cùng transaction A.

Điều này không có nghĩa PostgreSQL đã sửa dữ liệu giữa chừng khi A đang đọc **một statement**. Hai câu `SELECT` là hai statement khác nhau và **mỗi statement READ COMMITTED có thể có snapshot riêng**.

### Vì sao gọi là non-repeatable read?

Cùng một truy vấn được thực hiện hai lần trong cùng transaction, nhưng trả kết quả khác nhau vì transaction khác đã commit thay đổi giữa hai statement. Hiện tượng đó gọi là **non-repeatable read** và được cho phép ở `READ COMMITTED`.

Đặc điểm cần nhớ:

- A không thấy thay đổi **chưa commit** của B.
- A có thể thấy thay đổi **đã commit** của B ở statement tiếp theo.
- Đây là hành vi bình thường của mức isolation mặc định, không phải lỗi MVCC.

## 7. Thí nghiệm 2: REPEATABLE READ vẫn thấy phiên bản cũ

Bây giờ dùng tài khoản An (ID 1) với balance ban đầu 100.00.

**Phiên A — đặt REPEATABLE READ trước truy vấn đầu:**

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT account_id, balance
FROM mvcc_lab.accounts
WHERE account_id = 1;

-- Kết quả: 100.00.
-- Giữ transaction A mở.
~~~

**Phiên B — ghi và commit bình thường:**

~~~sql
BEGIN;

UPDATE mvcc_lab.accounts
SET
    balance = balance + 50,
    updated_at = now()
WHERE account_id = 1
RETURNING account_id, balance;

COMMIT;
~~~

B đã commit balance **150.00**.

**Phiên A — đọc lại:**

~~~sql
SELECT account_id, balance
FROM mvcc_lab.accounts
WHERE account_id = 1;

-- Vẫn thấy 100.00 theo snapshot của transaction A.

COMMIT;

-- Bây giờ là statement mới sau khi A đã kết thúc:
SELECT account_id, balance
FROM mvcc_lab.accounts
WHERE account_id = 1;

-- Thấy 150.00.
~~~

Ở `REPEATABLE READ`, snapshot thông thường được cố định từ **statement đầu tiên cần snapshot** của transaction, không đơn thuần từ thời điểm gửi lệnh `BEGIN`. Các câu đọc về sau trong transaction tiếp tục dùng snapshot đó, đồng thời transaction vẫn nhìn thấy các thay đổi của chính nó theo ngữ nghĩa PostgreSQL.

### Điều quan trọng nhất

**Không phải B chờ cho A COMMIT mới được cập nhật.** B có thể ghi và commit trong lúc A đang giữ snapshot cũ. PostgreSQL giữ phiên bản 100 đủ lâu để A có thể tiếp tục đọc, đồng thời cho snapshot mới sau commit thấy 150.

Đây là lý do trực tiếp cần **nhiều phiên bản hàng**: nếu phiên bản 100 bị ghi đè và mất ngay, A không thể tiếp tục có một snapshot nhất quán theo `REPEATABLE READ` mà không phải khóa/chặn việc cập nhật của B.

~~~mermaid
flowchart LR
    V1["Tuple cũ: 100"] -->|"A - snapshot trước B commit"| A["Phiên A đọc 100"]
    V2["Tuple mới: 150"] -->|"Sau B commit"| N["Reader mới đọc 150"]
    V1 -->|"UPDATE tạo phiên bản mới"| V2
~~~

## 8. So sánh READ COMMITTED và REPEATABLE READ

| Câu hỏi | `READ COMMITTED` | `REPEATABLE READ` |
| --- | --- | --- |
| Snapshot được dùng | Thường mới cho mỗi statement | Cố định cho transaction sau khi được thiết lập |
| Hai SELECT cùng hàng sau khi người khác commit | Có thể thấy hai giá trị khác nhau | Vẫn thấy phiên bản tương ứng snapshot cũ |
| Có đọc dữ liệu chưa commit của transaction khác không? | Không | Không |
| Có thể thấy phantom giữa hai câu SELECT không? | Có | PostgreSQL ngăn phantom theo cách triển khai Repeatable Read |
| Nếu muốn UPDATE hàng bị transaction khác thay đổi sau snapshot | Có thể chờ và xử lý lại theo quy tắc READ COMMITTED | Có thể gặp serialization failure, phải retry toàn transaction |
| Hợp với | Nhiều thao tác API/OLTP thông thường | Báo cáo cần snapshot nhất quán hoặc logic đọc nhiều statement |

**Lưu ý:** PostgreSQL xử lý `READ UNCOMMITTED` như `READ COMMITTED`, vì nó không cung cấp dirty read như mức isolation “read uncommitted” được mô tả trong một số hệ quản trị khác.

`REPEATABLE READ` mạnh hơn trong việc bảo toàn snapshot, nhưng không ngăn được mọi bất thường xuyên nhiều hàng. Muốn bảo đảm các bất biến phức tạp ở mức serializable có thể cần `SERIALIZABLE` và cơ chế retry khi PostgreSQL phát hiện xung đột.

## 9. MVCC giúp tránh dirty read như thế nào?

Giả sử B bắt đầu cập nhật nhưng **chưa commit**:

**Phiên B:**

~~~sql
BEGIN;

UPDATE mvcc_lab.accounts
SET balance = balance + 70
WHERE account_id = 3
RETURNING account_id, balance;

-- B thấy 120.00 trong transaction của chính mình.
-- Chưa COMMIT hoặc ROLLBACK.
~~~

**Phiên A, kết nối khác:**

~~~sql
SELECT account_id, balance
FROM mvcc_lab.accounts
WHERE account_id = 3;

-- Vẫn thấy 50.00 nếu chưa có thay đổi đã commit khác.
~~~

A không thấy `balance = 120` đang chờ commit của B. A thấy phiên bản đã commit trước đó mà snapshot của A cho phép.

Sau đó B có thể:

~~~sql
ROLLBACK;
~~~

Khi rollback, giá trị 120 chưa từng trở thành dữ liệu đã commit nhìn thấy từ A.

Nếu hệ thống cho phép A đọc giá trị 120 trước commit, rồi B rollback, A có thể đưa ra quyết định dựa trên một trạng thái **chưa từng thực sự được xác nhận**. Đó là vấn đề dirty read. MVCC của PostgreSQL tránh điều này cho các lần đọc SQL thông thường.

## 10. “Reader không chặn writer” đúng đến đâu?

Một câu thường nghe là:

> Trong PostgreSQL, reader không chặn writer và writer không chặn reader.

Đây là nguyên tắc **thực dụng cho `SELECT` thông thường so với `UPDATE`/`DELETE` cùng dữ liệu**. Nó **không** có nghĩa tất cả truy vấn không bao giờ phải chờ khóa.

### Trường hợp đúng điển hình

**Phiên A:**

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT balance
FROM mvcc_lab.accounts
WHERE account_id = 1;

-- A giữ transaction để minh họa snapshot, không FOR UPDATE.
~~~

**Phiên B:**

~~~sql
UPDATE mvcc_lab.accounts
SET balance = balance + 10
WHERE account_id = 1
RETURNING balance;
~~~

B có thể cập nhật và commit mà không phải chờ A kết thúc **chỉ vì A đã SELECT thông thường**.

### Những ngoại lệ rất quan trọng

- `SELECT ... FOR UPDATE`/`FOR SHARE`/... là **locking read**, có thể xung đột với writer.
- Hai transaction cùng `UPDATE`/`DELETE` một hàng có thể chờ nhau.
- `SELECT` thông thường lấy khóa cấp quan hệ `ACCESS SHARE`, có thể xung đột với DDL cần `ACCESS EXCLUSIVE`.
- Các hoạt động như `ALTER TABLE`, `TRUNCATE`, `VACUUM FULL` và những khóa cấp bảng khác có thể làm reader/writer chờ.
- Lỗi deadlock, áp lực tài nguyên và mức isolation cao vẫn có thể ảnh hưởng tiến độ giao dịch.

Vì vậy, phát biểu chính xác hơn là: **MVCC giảm nhu cầu dùng khóa chặn giữa các reader thông thường và writer trên cùng hàng; PostgreSQL vẫn dùng locking ở những nơi cần thiết để bảo vệ tính đúng đắn.**

## 11. Thí nghiệm 3: hai writer cùng sửa một hàng phải phối hợp

Dùng tài khoản Chi (ID 3) với balance ban đầu 50.00. Hai phiên muốn cộng lần lượt 10 và 20.

**Phiên A:**

~~~sql
BEGIN;

UPDATE mvcc_lab.accounts
SET balance = balance + 10
WHERE account_id = 3
RETURNING account_id, balance;

-- A thấy 60.00, CHƯA COMMIT.
~~~

**Phiên B, chạy trong lúc A giữ transaction mở:**

~~~sql
BEGIN;

UPDATE mvcc_lab.accounts
SET balance = balance + 20
WHERE account_id = 3
RETURNING account_id, balance;

-- B có thể bị chặn khi chờ khóa hàng do A giữ.
~~~

**Phiên A tiếp tục:**

~~~sql
COMMIT;
~~~

B có thể tiếp tục sau khi A commit. Ở mức mặc định `READ COMMITTED`, PostgreSQL phối hợp cập nhật trên phiên bản hàng phù hợp; phép `balance = balance + 20` được áp lên giá trị mới, cho kết quả **80.00** theo lịch thử này.

**Phiên B:**

~~~sql
COMMIT;
~~~

Kết quả cuối:

~~~sql
SELECT account_id, balance
FROM mvcc_lab.accounts
WHERE account_id = 3;
~~~

Là **80.00**.

### Tại sao MVCC không cho hai writer tùy ý ghi?

Nếu A và B cùng thay đổi số dư mà không phối hợp, kết quả có thể đánh mất một trong hai phép cộng. PostgreSQL dùng **row-level locking** và kiểm tra xung đột giữa writer để giữ tính đúng đắn.

Với `REPEATABLE READ` hoặc `SERIALIZABLE`, writer thứ hai có thể nhận lỗi như **`could not serialize access due to concurrent update`**, thay vì tự động áp thay đổi trên phiên bản mới. Ứng dụng cần rollback và retry **toàn transaction** theo chính sách.

**MVCC không đồng nghĩa không có khóa.** Hệ thống vừa giữ nhiều phiên bản cho reader, vừa phải điều phối các writer tranh chấp cùng hàng.

## 12. Thao tác đọc rồi ghi có thể gây lost update ở tầng ứng dụng

Giả sử ứng dụng thực hiện:

~~~text
SELECT balance;
Ứng dụng tính new_balance = old_balance - 10;
UPDATE accounts SET balance = new_balance WHERE id = 4;
~~~

Nếu hai bên đồng thời thao tác, giá trị `new_balance` có thể được tính từ bản đọc cũ.

Ví dụ với Dung (ID 4), balance ban đầu 120.00:

**Phiên A — đọc rồi giữ giá trị 120 ở ứng dụng:**

~~~sql
BEGIN;

SELECT balance
FROM mvcc_lab.accounts
WHERE account_id = 4;

-- A nhận 120.00, dự định trừ 10 => 110.00.
~~~

**Phiên B — có giao dịch khác cộng 25 và commit:**

~~~sql
BEGIN;

UPDATE mvcc_lab.accounts
SET balance = balance + 25
WHERE account_id = 4;

COMMIT;

-- Giá trị đã commit: 145.00.
~~~

**Phiên A — ghi số đã tính từ bản đọc cũ:**

~~~sql
UPDATE mvcc_lab.accounts
SET balance = 110.00
WHERE account_id = 4;

COMMIT;
~~~

Kết quả cuối có thể là **110.00**: phép cộng 25 của B bị ghi đè bởi giá trị cố định A tính từ dữ liệu cũ.

Điều này cho thấy **READ COMMITTED + MVCC không tự bảo vệ mọi quy tắc đọc–tính–ghi của ứng dụng**. Cách cập nhật bằng một giá trị cố định được tính từ dữ liệu cũ không tương đương thao tác cộng/trừ trên phiên bản hàng mới nhất.

### Cách tốt hơn cho phép cộng/trừ một hàng

~~~sql
UPDATE mvcc_lab.accounts
SET balance = balance - 10
WHERE account_id = 4
  AND balance >= 10
RETURNING account_id, balance;
~~~

Phép toán được tính trong câu UPDATE trên phiên bản hàng PostgreSQL xử lý, có điều kiện số dư không âm. Đây là mẫu cơ bản để tránh **lost update do ứng dụng ghi đè giá trị cũ** khi phép toán có thể biểu diễn trực tiếp bằng SQL.

Với nghiệp vụ tiền thật, cần thêm ledger, transaction nhiều hàng, authorization và kiểm soát tính nhất quán toàn hệ thống; ví dụ chỉ nhằm giải thích MVCC và concurrency.

## 13. Optimistic locking: cột version không thay thế MVCC

Có trường hợp ứng dụng phải đọc nhiều trường, cho người dùng chỉnh sửa, rồi ghi cả một bản ghi sau vài phút. Khi đó có thể dùng **optimistic locking** bằng một cột `row_version` do ứng dụng quản lý.

Giả sử hàng có:

~~~text
account_id = 1
row_version = 0
~~~

Ứng dụng đọc version 0 rồi gửi:

~~~sql
BEGIN;

UPDATE mvcc_lab.accounts
SET
    balance = 90.00,
    row_version = row_version + 1,
    updated_at = now()
WHERE account_id = 1
  AND row_version = 0
RETURNING account_id, balance, row_version;

ROLLBACK;
~~~

Nếu version vẫn là 0, UPDATE trả một hàng với version 1. Nếu transaction khác đã cập nhật trước và cũng tăng version, điều kiện `row_version = 0` không khớp, nên UPDATE trả **0 hàng** để ứng dụng phát hiện xung đột.

Phân biệt:

- **MVCC nội bộ:** PostgreSQL quản lý tuple version và snapshot để cung cấp visibility/đồng thời.
- **`row_version` ứng dụng:** một trường nghiệp vụ/kỹ thuật dùng cho compare-and-swap, chống ghi đè từ biểu mẫu cũ.

Không bắt buộc mọi bảng phải có `row_version` để PostgreSQL chạy MVCC. Ngược lại, có MVCC cũng không tự thay thế tất cả optimistic locking ở tầng API.

## 14. SELECT FOR UPDATE thay đổi mô hình chờ

Có lúc ứng dụng cần **đọc một giá trị rồi thực hiện nhiều phép ghi dựa vào nó** trong một transaction. Khi đó locking read có thể phù hợp.

~~~sql
BEGIN;

SELECT account_id, balance
FROM mvcc_lab.accounts
WHERE account_id = 1
FOR UPDATE;

-- Transaction có khóa hàng phục vụ việc phối hợp cập nhật.

UPDATE mvcc_lab.accounts
SET balance = balance - 10
WHERE account_id = 1
  AND balance >= 10;

COMMIT;
~~~

`FOR UPDATE` yêu cầu một khóa hàng đối với các hàng được chọn. Transaction khác muốn UPDATE cùng hàng có thể phải chờ đến khi khóa được giải phóng.

### Khi nào không nên dùng?

Không thêm `FOR UPDATE` vào mọi câu `SELECT` chỉ vì lo concurrency. Việc đó làm tăng tranh chấp, có thể giảm throughput và giữ khóa lâu. Với báo cáo đọc hoặc API chỉ hiển thị, `SELECT` thông thường thường thích hợp hơn.

### NOWAIT và SKIP LOCKED

PostgreSQL hỗ trợ các lựa chọn cho locking reads:

~~~sql
SELECT account_id
FROM mvcc_lab.accounts
WHERE account_id = 1
FOR UPDATE NOWAIT;
~~~

`NOWAIT` có thể báo lỗi nếu không lấy được khóa hàng ngay.

~~~sql
SELECT account_id
FROM mvcc_lab.accounts
ORDER BY account_id
FOR UPDATE SKIP LOCKED;
~~~

`SKIP LOCKED` bỏ qua một số hàng đang bị khóa và có thể hữu ích cho **queue workers**. Nhưng kết quả có thể là **một cái nhìn không đầy đủ**, không phù hợp để khẳng định đã đọc chính xác toàn bộ tập dữ liệu.

**Các câu locking read vẫn phải nằm trong thiết kế transaction hợp lý**, không phải cách xóa bỏ mọi bất thường đồng thời.

## 15. Transaction isolation và hiện tượng đọc

Các hiện tượng thường được bàn khi học đồng thời:

| Hiện tượng | Mô tả ngắn |
| --- | --- |
| **Dirty read** | Đọc dữ liệu transaction khác chưa commit |
| **Non-repeatable read** | Cùng hàng được đọc hai lần trong transaction nhưng thấy giá trị khác do commit mới |
| **Phantom read** | Cùng điều kiện tìm kiếm, số/tập hàng thay đổi giữa hai lần đọc |
| **Serialization anomaly** | Kết quả đồng thời không tương đương một lịch chạy tuần tự hợp lệ |

Đối với PostgreSQL:

| Isolation | Dirty read | Non-repeatable read | Phantom read | Serialization anomaly |
| --- | --- | --- | --- | --- |
| `READ UNCOMMITTED` | Không (được xử lý như READ COMMITTED) | Có thể | Có thể | Có thể |
| `READ COMMITTED` | Không | Có thể | Có thể | Có thể |
| `REPEATABLE READ` | Không | Không | Không | Có thể |
| `SERIALIZABLE` | Không | Không | Không | PostgreSQL cố ngăn; transaction có thể bị abort và cần retry |

Đây là bảng khái quát theo ngữ nghĩa của PostgreSQL, không nên áp các giả định từ hệ quản trị khác mà không kiểm tra. `REPEATABLE READ` của PostgreSQL dùng snapshot isolation, **ngăn phantom** nhưng vẫn có thể gặp một số bất thường mà `SERIALIZABLE` xử lý.

## 16. Vì sao REPEATABLE READ chưa chắc đủ cho bất biến nhiều hàng?

Giả sử hệ thống yêu cầu: “Trong một ca trực phải còn **ít nhất một bác sĩ trực**”.

Hai transaction có thể cùng đọc trạng thái:

~~~text
Doctor A: on_call = true
Doctor B: on_call = true
~~~

Phiên A thấy B đang trực nên cho A nghỉ. Phiên B thấy A đang trực nên cho B nghỉ. Mỗi bên chỉ cập nhật **một hàng khác nhau**. Nếu cùng dùng snapshot cũ dưới `REPEATABLE READ`, cả hai có thể commit và kết quả cuối là **không còn bác sĩ nào trực**.

Đây là ví dụ **write skew**: các transaction không tranh chấp đúng cùng một hàng nhưng cùng phá vỡ bất biến xuyên tập hàng.

~~~text
Phiên A                                 Phiên B
-----------------------------------     -----------------------------------
Đọc A=true, B=true                     Đọc A=true, B=true
UPDATE A.on_call=false                  UPDATE B.on_call=false
COMMIT                                   COMMIT

Kết quả cuối: A=false, B=false
Bất biến "ít nhất một người trực" bị vi phạm.
~~~

Nếu nghiệp vụ đòi một kết quả tương đương lịch chạy tuần tự, có thể dùng `SERIALIZABLE`, constraint hoặc cơ chế khóa được thiết kế phù hợp. Trong PostgreSQL, `SERIALIZABLE` sử dụng cơ chế phát hiện phụ thuộc/xung đột (SSI — Serializable Snapshot Isolation) và có thể **hủy một transaction bằng serialization failure** để bảo vệ tính serializable.

Điểm cần học ở bài này: **nhiều phiên bản giúp reader có snapshot, nhưng không tự chứng minh mọi bất biến nghiệp vụ đa hàng đều đúng**.

## 17. Các cột hệ thống xmin, xmax, ctid cho biết gì?

Trong PostgreSQL, các bảng heap có một số metadata liên quan phiên bản hàng. Có thể quan sát qua các cột hệ thống:

~~~sql
SELECT
    account_id,
    balance,
    xmin::text AS creating_xid,
    xmax::text AS xmax_info,
    ctid::text AS physical_location
FROM mvcc_lab.accounts
ORDER BY account_id;
~~~

Ý nghĩa ở mức nhập môn:

| Cột | Ý nghĩa cơ bản | Không nên hiểu sai |
| --- | --- | --- |
| `xmin` | Transaction ID đã tạo phiên bản tuple | Không phải created_at hay khóa phiên bản nghiệp vụ ổn định |
| `xmax` | Metadata liên quan transaction xóa/cập nhật hoặc khóa tuple | Không phải cứ khác 0 là hàng đã bị xóa và không còn thấy được |
| `ctid` | Vị trí vật lý hiện tại của tuple trong heap | Không phải primary key; có thể đổi sau UPDATE hoặc thao tác bảo trì |

**Cẩn thận với `xmax`:** trường này có thể mang thông tin khóa hàng, transaction chưa commit hoặc đã rollback; muốn kết luận visibility cần xét thêm trạng thái transaction và tuple metadata. Không dùng `WHERE xmax = 0` làm phương pháp chính thức để xác định “hàng đang sống”.

### Quan sát ctid trước và sau UPDATE

~~~sql
BEGIN;

SELECT
    account_id, balance, xmin::text, ctid::text
FROM mvcc_lab.accounts
WHERE account_id = 1;

UPDATE mvcc_lab.accounts
SET balance = balance + 1
WHERE account_id = 1
RETURNING
    account_id, balance, xmin::text, ctid::text;

ROLLBACK;
~~~

Khi UPDATE tạo phiên bản mới, tuple mới có vị trí vật lý mới, nên `ctid` quan sát được có thể thay đổi. Sau rollback, thay đổi không được commit.

Không nên dựa vào giá trị cụ thể của `xmin` hay `ctid` trong đáp án: chúng phụ thuộc trạng thái database, lịch giao dịch và layout trang đĩa.

### xmin không phải transaction timestamp

Transaction ID là một định danh phục vụ quản lý MVCC, không phải số giây hay mốc thời gian người dùng. Nó còn có cơ chế wraparound/freeze cần bảo trì. Không dùng `xmin` làm “ngày cập nhật cuối” hoặc business version lâu dài theo cách chưa được kiểm soát.

## 18. Vì sao UPDATE thường tạo phiên bản mới thay vì sửa trực tiếp?

Nếu cập nhật trực tiếp vào đúng tuple cũ mà không giữ bản trước, một reader có snapshot cũ có thể không còn nguồn dữ liệu nhất quán để đọc. Với nhiều phiên bản, PostgreSQL có thể:

1. Giữ phiên bản cũ đủ lâu cho những snapshot đang cần.
2. Ghi phiên bản mới mang giá trị sau UPDATE.
3. Chờ transaction ghi commit/rollback để quyết định phiên bản nào được hiển thị.
4. Cho snapshot cũ thấy giá trị cũ, snapshot mới thấy giá trị mới theo isolation.
5. Dọn phiên bản cũ sau khi không còn cần thiết.

~~~mermaid
flowchart TD
    A["Tuple v1: balance=100"] --> B["UPDATE balance=150"]
    B --> C["Tuple v1 giữ metadata hết hiệu lực theo transaction"]
    B --> D["Tuple v2: balance=150"]
    C --> E["Snapshot cũ có thể đọc v1"]
    D --> F["Snapshot mới sau commit có thể đọc v2"]
    E --> G["Khi không còn reader cần v1"]
    G --> H["VACUUM/pruning thu hồi không gian đủ điều kiện"]
~~~

Điều này có chi phí lưu trữ. MVCC **đổi chi phí quản lý phiên bản và dọn dẹp** để lấy khả năng đồng thời của đọc–ghi và tính nhất quán theo snapshot.

## 19. UPDATE giá trị “giống cũ” vẫn có thể tạo phiên bản mới

Ví dụ:

~~~sql
BEGIN;

UPDATE mvcc_lab.accounts
SET balance = balance
WHERE account_id = 1
RETURNING account_id, balance, xmin::text, ctid::text;

ROLLBACK;
~~~

Dù giá trị `balance` không đổi, statement vẫn xử lý hàng thỏa `WHERE`. Trong PostgreSQL, UPDATE thông thường có thể tạo một phiên bản tuple mới và gây công việc WAL/index/trigger, kể cả khi phép gán tạo giá trị giống cũ.

Không viết UPDATE lặp chỉ để “chắc chắn dữ liệu như vậy” nếu không có lý do nghiệp vụ. Khi muốn tránh ghi thừa:

~~~sql
UPDATE mvcc_lab.accounts
SET balance = 150.00
WHERE account_id = 1
  AND balance IS DISTINCT FROM 150.00;
~~~

`IS DISTINCT FROM` so sánh an toàn cả với NULL. Trong bảng lab balance NOT NULL, điều kiện `balance <> 150.00` cũng có thể dùng, nhưng `IS DISTINCT FROM` là mẫu chung hơn cho các cột nullable.

**Không đồng nhất “UPDATE làm phát sinh phiên bản” với “mọi UPDATE buộc cập nhật mọi index”.** PostgreSQL có tối ưu **HOT** trong một số điều kiện để giảm chi phí index.

## 20. HOT update là gì?

**HOT — Heap-Only Tuple** là một cơ chế tối ưu cho UPDATE của PostgreSQL. Khi các điều kiện phù hợp, nhất là những cột ảnh hưởng đến index không thay đổi và trang heap có đủ chỗ, PostgreSQL có thể tạo phiên bản mới trên cùng trang heap và **không cần tạo một index entry mới** cho mỗi phiên bản theo cách thông thường.

Ví dụ nếu chỉ đổi `balance` nhưng index của bảng chỉ nằm trên `account_id`, một UPDATE có thể là ứng viên HOT. Tuy nhiên còn tùy fillfactor, chỗ trống trên trang, loại index và các điều kiện nội bộ.

### Điều HOT không làm

- Không biến UPDATE thành thao tác cập nhật tại chỗ theo nghĩa bỏ hoàn toàn MVCC.
- Không xóa nhu cầu VACUUM/pruning.
- Không đảm bảo mọi UPDATE trên cột không index đều thành HOT.
- Không khiến UPDATE miễn phí về WAL, heap storage hoặc lock.

HOT là tối ưu để giảm **chi phí duy trì index**, chứ không phải cơ chế thay thế nhiều phiên bản.

## 21. Vì sao cần VACUUM?

Vì PostgreSQL giữ các phiên bản tuple khi INSERT/UPDATE/DELETE, theo thời gian sẽ có những phiên bản **không còn được bất kỳ snapshot đủ điều kiện nào cần tới**. Nếu không thu hồi, chúng tích tụ và gây:

- Bảng/index phình to (*bloat*).
- Quét nhiều dữ liệu không còn hữu ích.
- Tăng chi phí I/O và bộ nhớ đệm.
- Khó duy trì hiệu năng trong workload ghi thường xuyên.
- Rủi ro quản lý transaction ID nếu hệ thống bỏ qua vacuum/freeze quá lâu.

**`VACUUM`** giúp thu hồi không gian của các tuple đã chết đủ điều kiện, cập nhật các cấu trúc liên quan và hỗ trợ bảo trì transaction ID. PostgreSQL có **autovacuum** để thực hiện công việc này theo cấu hình và nhu cầu.

### Điều VACUUM không làm ngay

- Không nhất thiết trả dung lượng file bảng về hệ điều hành ngay.
- Không thể thu hồi một phiên bản vẫn còn cần thiết cho một snapshot lâu đời.
- Không mặc định là `VACUUM FULL`.
- Không có nghĩa lịch sử nghiệp vụ đã được lưu riêng.

Có thể chạy trong database lab:

~~~sql
VACUUM (ANALYZE) mvcc_lab.accounts;
~~~

Lệnh `VACUUM` thông thường không được chạy trong một transaction block explicit `BEGIN ... COMMIT`. `ANALYZE` cập nhật thống kê hỗ trợ planner; VACUUM xử lý dọn dẹp các phiên bản đủ điều kiện và công việc bảo trì khác.

## 22. Vì sao transaction đọc dài có thể làm bloat tăng?

Quay lại ví dụ `REPEATABLE READ`: A đang nhìn snapshot cũ từ trước khi B cập nhật. B vẫn có thể commit nhiều lần, nhưng PostgreSQL **không được thu hồi một phiên bản cũ còn cần thiết cho snapshot hợp lệ của A**.

~~~text
A mở REPEATABLE READ
    ↓
A đọc snapshot cũ
    ↓
B UPDATE và COMMIT nhiều lần
    ↓
Các phiên bản cũ có thể phải giữ lại
    ↓
A chưa COMMIT/ROLLBACK
    ↓
VACUUM chưa thể dọn hết những phiên bản còn cần cho A
    ↓
Tăng dead tuples/bloat và công việc bảo trì
~~~

Một transaction mở nhiều giờ với snapshot cũ có thể tạo áp lực lên hệ thống ngay cả khi nó **không chủ động UPDATE hàng nào**. Điều này thường gặp khi:

- Mở `BEGIN` rồi người dùng đi làm việc khác.
- Một chương trình stream kết quả nhưng giữ transaction không kết thúc.
- Job báo cáo giữ snapshot quá lâu.
- Kết nối ở trạng thái **idle in transaction**.
- Một số loại replication slot hoặc tác vụ giữ xmin cũng có thể ảnh hưởng việc dọn dẹp.

### Quy tắc vận hành

- Giữ transaction **ngắn nhất có thể theo nhu cầu nghiệp vụ**.
- Không mở transaction rồi đợi network/API bên ngoài trong thời gian dài nếu tránh được.
- Đóng `ResultSet`/cursor và commit/rollback đúng lúc.
- Theo dõi session `idle in transaction` và các transaction giữ snapshot lâu.
- Cấu hình autovacuum, connection timeout và quản lý workload theo dữ liệu thật.

**Không tắt autovacuum để giảm I/O mà chưa hiểu hệ quả MVCC và transaction ID wraparound.**

## 23. Autovacuum, freeze và transaction ID wraparound

PostgreSQL dùng transaction ID để xác định visibility. Các ID này không phải dãy vô hạn đơn giản có thể tăng mãi mà không cần bảo trì. PostgreSQL có cơ chế **freezing** và quy trình vacuum để quản lý tuổi transaction ID, tránh tình trạng wraparound làm sai cách nhìn dữ liệu.

Điều quan trọng ở mức bài này:

1. MVCC dựa vào metadata giao dịch.
2. Transaction ID có vòng đời và giới hạn.
3. `VACUUM`/autovacuum đóng vai trò trong cả **dọn tuple cũ** lẫn **bảo vệ hệ thống trước rủi ro wraparound**.
4. Một transaction/snapshot/slot giữ trạng thái cũ quá lâu có thể gây khó khăn cho việc dọn dẹp và vận hành.

Không nên tự thay đổi các tham số như `autovacuum_freeze_max_age`, tắt worker autovacuum hay chạy lệnh bảo trì phá hủy chỉ dựa trên ví dụ lab. Với database thật, cần khảo sát metric, kích thước bảng, workload và tài liệu đúng phiên bản.

## 24. Quan sát thông tin dead tuple và autovacuum

PostgreSQL cung cấp thống kê để chẩn đoán các bảng có khả năng tích tụ phiên bản cũ:

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count
FROM pg_stat_user_tables
WHERE schemaname = 'mvcc_lab'
ORDER BY relname;
~~~

Trong đó:

- `n_live_tup` là **ước lượng** số tuple sống.
- `n_dead_tup` là **ước lượng** số tuple chết.
- `last_vacuum`/`last_autovacuum` là thời điểm vacuum gần nhất được thống kê.
- Các giá trị có thể chậm cập nhật và không phản ánh hoàn toàn chính xác từng thay đổi ngay lập tức.

**Không lấy n_dead_tup làm số byte dung lượng có thể thu hồi chính xác.** Đây là chỉ báo vận hành, không phải công cụ đo vật lý tuyệt đối.

### Quan sát transaction đang mở

~~~sql
SELECT
    pid,
    usename,
    state,
    xact_start,
    now() - xact_start AS transaction_age,
    backend_xmin,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
~~~

Các cột cần chú ý:

- `xact_start`: thời điểm transaction hiện tại bắt đầu.
- `state = 'idle in transaction'`: session đang giữ transaction mở nhưng không thực thi câu lệnh.
- `backend_xmin`: một chỉ báo liên quan giới hạn snapshot mà backend đang giữ.
- `wait_event_type`/`wait_event`: gợi ý session có đang chờ lock, I/O hoặc điều kiện khác không.

Việc xem thông tin session khác có thể bị giới hạn bởi quyền database. **Không tự động `pg_terminate_backend` trên production** chỉ vì thấy transaction lâu mà chưa xác định chủ sở hữu và ảnh hưởng.

## 25. VACUUM khác VACUUM FULL như thế nào?

| Đặc điểm | `VACUUM` thông thường | `VACUUM FULL` |
| --- | --- | --- |
| Mục tiêu | Dọn dẹp/phân phối lại không gian bên trong để tái sử dụng | Viết lại bảng để thu gọn vật lý |
| Khả năng trả dung lượng về OS | Có giới hạn, tùy cấu trúc | Thường có thể thu nhỏ nhiều hơn |
| Khóa | Được thiết kế hoạt động cùng workload thông thường | Cần khóa mạnh (`ACCESS EXCLUSIVE`) trên bảng |
| Chi phí | Thường nhẹ hơn và có autovacuum | Có thể nặng, cần thêm không gian tạm và thời gian |
| Dùng khi | Bảo trì định kỳ | Trường hợp đặc biệt sau khi đánh giá kỹ |

`VACUUM FULL` không phải câu lệnh nên tự chạy bất cứ khi nào thấy `n_dead_tup` lớn. Trong production, có thể gây gián đoạn đáng kể vì yêu cầu khóa mạnh.

Cách tiếp cận thường ưu tiên là hiểu **nguyên nhân phát sinh dead tuples và lý do autovacuum chưa dọn được**, trước khi quyết định viết lại bảng.

## 26. MVCC và WAL: hai cơ chế khác nhau

Người mới thường nhầm **MVCC** với **WAL (Write-Ahead Log)** vì cả hai liên quan đến thay đổi dữ liệu.

- **MVCC** chủ yếu giải quyết **visibility và đồng thời**: ai thấy phiên bản hàng nào, khi nào?
- **WAL** chủ yếu hỗ trợ **durability, crash recovery và replication**: làm sao phục hồi trạng thái đã commit sau sự cố và truyền thay đổi?

Ví dụ B UPDATE balance 100 → 150:

~~~text
MVCC:
    Reader A có thể thấy bản 100 theo snapshot cũ;
    Reader mới có thể thấy 150 sau commit.

WAL:
    Ghi lại những thay đổi cần thiết để phục hồi dữ liệu
    nếu server gặp crash, theo cơ chế write-ahead logging.
~~~

Hai cơ chế phối hợp nhưng không thay thế nhau. **Có WAL không tự tạo snapshot isolation**, và **có nhiều tuple version không tự bảo đảm dữ liệu bền vững sau mất điện**.

## 27. MVCC không phải hệ thống time travel

Một hiểu lầm là: “PostgreSQL có nhiều phiên bản, vậy tôi có thể SELECT lại mọi giá trị của hôm qua”.

Trong PostgreSQL thông thường, các tuple version cũ chỉ được giữ khi cần cho visibility và sẽ được vacuum/pruning dọn dẹp. Hệ thống **không cung cấp mặc định một lịch sử `AS OF` tùy ý** để truy vấn mọi trạng thái quá khứ của bảng.

Để có lịch sử nghiệp vụ có thể tra nhiều năm, cần thiết kế riêng như:

- Bảng audit lưu trạng thái trước/sau.
- Bảng lịch sử có khoảng hiệu lực.
- Change data capture (CDC) hoặc logical decoding phù hợp.
- Event sourcing khi kiến trúc thực sự yêu cầu.
- Backup và PITR cho nhu cầu phục hồi, không thay thế lịch sử truy vấn theo hàng.

MVCC là công cụ cho **tính nhất quán khi có giao dịch đồng thời**, không phải giải pháp lưu trữ lịch sử vô hạn miễn phí.

## 28. Index phải phối hợp với phiên bản hàng

Giả sử có index trên `account_id`:

~~~sql
CREATE INDEX idx_accounts_owner_name
ON mvcc_lab.accounts(owner_name);
~~~

B-tree index giúp tìm vị trí tuple phù hợp, nhưng bản thân việc tìm thấy khóa index **không đủ** để kết luận hàng được phép hiển thị trong snapshot hiện tại. PostgreSQL còn cần kiểm tra visibility theo MVCC, thường liên quan tới heap tuple hoặc tối ưu thích hợp.

Các điểm cần hiểu:

1. Một hàng logic có thể có các phiên bản vật lý theo thời gian.
2. Index entry cần dẫn tới dữ liệu vật lý mà executor đánh giá visibility.
3. UPDATE có thể làm phát sinh thêm index maintenance, trừ những tối ưu như HOT khi đủ điều kiện.
4. VACUUM có vai trò dọn những tham chiếu/index entry không còn cần thiết.
5. Index-only scan có thể giảm số lần truy cập heap khi visibility map và điều kiện khác cho phép.

**Index không thay thế MVCC.** Một index scan vẫn phải tuân theo snapshot và trạng thái commit/rollback.

## 29. Tác động lên thiết kế API và JDBC

Một repository Java thường sử dụng nhiều connection từ pool, tương ứng nhiều session PostgreSQL. Cần phân biệt:

- **Autocommit bật:** mỗi statement độc lập thường là một transaction.
- **Autocommit tắt hoặc transaction manager:** nhiều statement cùng transaction, chịu isolation và lock tới khi commit/rollback.
- **ResultSet/cursor:** có thể giữ tài nguyên và transaction mở lâu nếu không được đóng đúng cách.

Ví dụ JDBC minh họa transaction đọc với `REPEATABLE READ`:

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public static BigDecimal readBalance(
        Connection connection,
        int accountId
) throws SQLException {

    String sql = """
        SELECT balance
        FROM mvcc_lab.accounts
        WHERE account_id = ?
        """;

    try (PreparedStatement ps =
             connection.prepareStatement(sql)) {
        ps.setInt(1, accountId);

        try (ResultSet rs = ps.executeQuery()) {
            if (!rs.next()) {
                throw new SQLException("Account not found");
            }
            return rs.getBigDecimal("balance");
        }
    }
}
~~~

Phương thức trên **chỉ đọc**; nó không tự thiết lập isolation và không tự commit. Transaction boundary phải nằm ở service hoặc transaction manager đang sở hữu connection.

Ví dụ một transaction do chương trình quản lý:

~~~java
import java.sql.Connection;
import java.sql.SQLException;

boolean previousAutoCommit = connection.getAutoCommit();

try {
    connection.setAutoCommit(false);
    connection.setTransactionIsolation(
        Connection.TRANSACTION_REPEATABLE_READ
    );

    var first = readBalance(connection, 1);

    // Có thể chạy statement khác trong cùng transaction.
    var second = readBalance(connection, 1);

    connection.commit();

} catch (SQLException ex) {
    connection.rollback();
    throw ex;
} finally {
    connection.setAutoCommit(previousAutoCommit);
}
~~~

Đây là ví dụ **connection do phương thức trực tiếp quản lý**; trong Spring hoặc container có transaction manager, không nên tự thay đổi autocommit/isolation bừa bãi trên connection do framework quản lý. Trước khi đưa connection về pool, trạng thái isolation/autocommit phải được reset theo hợp đồng pool.

### Không mở transaction rồi gọi API mạng lâu

Một anti-pattern:

~~~text
BEGIN
SELECT ... (giữ snapshot/khóa)
Gọi dịch vụ bên ngoài trong 30 giây
Đợi phản hồi
UPDATE ...
COMMIT
~~~

Nó kéo dài transaction, có thể giữ phiên bản cũ và lock cần thiết lâu hơn. Nên xem có thể tách bước, dùng outbox/saga hoặc thay đổi giao thức nghiệp vụ để giảm thời gian giữ transaction không.

## 30. Khi có lỗi serialization, phải retry cái gì?

Ở mức isolation cao, PostgreSQL có thể phát hiện transaction không thể commit an toàn theo các quy tắc và trả:

~~~text
SQLSTATE 40001: serialization_failure
~~~

Lúc này thường cần **rollback và chạy lại toàn bộ transaction**, gồm những câu SELECT dùng làm cơ sở cho quyết định, chứ không chỉ chạy lại câu UPDATE cuối cùng.

Ví dụ:

~~~text
Transaction cũ:
    Đọc A, B
    Tính tổng/tính điều kiện
    UPDATE một số hàng
    COMMIT → 40001

Retry đúng:
    Bắt đầu transaction mới
    Đọc lại A, B theo snapshot mới
    Tính lại điều kiện
    UPDATE
    COMMIT
~~~

Với deadlock, PostgreSQL có thể trả `40P01`; ứng dụng cũng cần cơ chế retry có giới hạn theo ngữ cảnh.

**Không retry mù quáng một transaction đã gọi hệ thống bên ngoài có side effect** (trừ tiền qua API, gửi email, xuất kho vật lý) nếu chưa có idempotency/reconciliation riêng. Rollback PostgreSQL không thể tự hoàn tác mọi dịch vụ bên ngoài.

## 31. FAQ: những câu hỏi ngắn về MVCC

### 31.1. PostgreSQL có thật sự giữ hai bản sao hoàn chỉnh của mọi hàng mọi lúc không?

Không. Nhiều phiên bản chỉ xuất hiện theo lịch sử cập nhật/xóa/chèn và được thu hồi khi đủ điều kiện. Không nên hiểu “multi-version” là bảng luôn có chính xác hai bản lưu cho mọi hàng.

### 31.2. Mỗi SELECT có phải tự copy toàn bộ bảng không?

Không. Snapshot là cơ chế thông tin visibility, không phải một bản sao vật lý đầy đủ của mọi hàng trong bảng. Executor dùng metadata tuple/transaction để chọn phiên bản nhìn thấy.

### 31.3. Sau COMMIT, mọi transaction đều thấy giá trị mới ngay chứ?

Không. Một transaction `REPEATABLE READ` đã giữ snapshot từ trước có thể tiếp tục thấy phiên bản cũ. Các statement ở transaction/snapshot mới đủ điều kiện sẽ thấy dữ liệu đã commit.

### 31.4. Nếu writer chưa COMMIT, reader có thấy dữ liệu mới không?

Reader ở transaction khác thông thường không thấy phiên bản chưa commit. Writer **tự thấy thay đổi của chính transaction mình** theo ngữ nghĩa PostgreSQL.

### 31.5. Tại sao writer vẫn có thể bị chờ dù có MVCC?

Vì hai writer có thể tranh cùng hàng/khóa và vì các loại lock, FK, unique constraint hoặc isolation. MVCC giảm xung đột đọc–ghi, không xóa tất cả xung đột ghi–ghi.

### 31.6. Có thể dùng xmin làm version field cho API không?

`xmin` hữu ích để **quan sát nội bộ**, nhưng không nên coi là khóa phiên bản nghiệp vụ bền vững, đa năm, vì đặc tính transaction ID, freeze/wraparound và bảo trì. Một cột `row_version bigint` do ứng dụng kiểm soát thường dễ có hợp đồng rõ ràng hơn.

### 31.7. ROLLBACK có xóa ngay tuple mới không?

Rollback khiến phiên bản chưa commit không trở thành dữ liệu hiển thị; việc thu hồi vật lý có thể diễn ra qua các cơ chế dọn dẹp về sau. Không đồng nhất “transaction rollback thành công” với “mọi byte vật lý đã được xóa ngay”.

### 31.8. DELETE đã commit nhưng file vẫn lớn có phải lỗi không?

Không nhất thiết. MVCC và VACUUM có thể tái sử dụng không gian bên trong bảng mà không lập tức trả dung lượng về hệ điều hành. Cần xem bloat, vacuum, snapshot cũ và workload.

### 31.9. Serializable có nghĩa tất cả transaction chạy tuần tự bằng một khóa toàn database không?

Không. PostgreSQL sử dụng cơ chế kiểm soát đồng thời, bao gồm SSI trong `SERIALIZABLE`, để đạt kết quả tương đương lịch serial khi các transaction commit thành công; một số transaction có thể phải rollback/retry khi phát hiện xung đột. Nó không chỉ đơn giản là đặt một khóa toàn cục cho mỗi transaction.

## 32. Các sai lầm thường gặp

### 32.1. Nghĩ MVCC là “không có lock”

Sai. Reader thông thường có thể không chặn writer, nhưng writer cùng hàng, `FOR UPDATE` và nhiều DDL vẫn sử dụng khóa.

### 32.2. Nghĩ UPDATE sửa trực tiếp một phiên bản duy nhất

UPDATE thường tạo tuple version mới; phiên bản cũ có thể cần được giữ cho snapshot cũ.

### 32.3. Nghĩ mọi SELECT trong một transaction luôn đọc cùng snapshot

Điều này phụ thuộc isolation. `READ COMMITTED` thường có snapshot mới mỗi statement; `REPEATABLE READ` giữ snapshot trong transaction.

### 32.4. Nghĩ REPEATABLE READ chặn writer khác

Writer vẫn có thể cập nhật và commit nếu không bị xung đột khóa; reader giữ snapshot cũ.

### 32.5. Nghĩ PostgreSQL cho phép dirty read ở READ UNCOMMITTED

PostgreSQL xử lý `READ UNCOMMITTED` như `READ COMMITTED`.

### 32.6. Nghĩ snapshot là bản sao vật lý của cả bảng

Không. Snapshot dùng metadata transaction và tuple visibility để quyết định kết quả.

### 32.7. Dùng giá trị cũ từ client để ghi đè không điều kiện

Có thể gây lost update ở tầng logic. Dùng `SET balance = balance + delta`, điều kiện trạng thái hoặc optimistic locking.

### 32.8. Nghĩ UPDATE row=value cũ không tạo chi phí

Nó vẫn có thể tạo tuple version mới, WAL, trigger và công việc bảo trì.

### 32.9. Tắt autovacuum vì thấy tốn CPU

Có thể gây tích tụ dead tuples và rủi ro wraparound. Cần đánh giá trước khi thay cấu hình.

### 32.10. Giữ transaction mở khi user tương tác lâu

Snapshot/lock tồn tại lâu có thể làm vacuum khó dọn và tăng bloat. Dùng transaction ngắn.

### 32.11. Nghĩ VACUUM xóa lịch sử đã commit mà ứng dụng cần tra cứu

MVCC không phải audit history. Nếu phải tra lịch sử, dùng bảng lịch sử/event riêng; không dựa vào tuple version cũ.

### 32.12. Dùng ctid hoặc xmin như ID ổn định

`ctid` là vị trí vật lý có thể đổi; `xmin` là metadata transaction. Dùng `PRIMARY KEY` và business version phù hợp.

### 32.13. Đọc n_dead_tup như số hàng chết tuyệt đối

Đây là thống kê ước lượng, có thể trễ. Cần kết hợp thêm quan sát và chỉ số khác.

### 32.14. Dùng VACUUM FULL tùy tiện trên production

`VACUUM FULL` cần khóa mạnh và có thể gây gián đoạn. Không thay thế việc xử lý transaction dài và autovacuum.

### 32.15. Nhầm MVCC với WAL

MVCC giải quyết phiên bản nhìn thấy và đồng thời; WAL phục vụ durability/recovery/replication.

### 32.16. Nghĩ SERIALIZABLE không cần retry

Hệ thống có thể abort một transaction để tránh anomaly; ứng dụng phải xử lý `40001`.

### 32.17. Nghĩ cùng một SQL luôn thấy số hàng cố định

Ở `READ COMMITTED`, mỗi statement có thể thấy dữ liệu đã commit mới, nên tập hàng có thể thay đổi giữa hai lần chạy. Các predicate có thể chịu concurrency.

### 32.18. Nghĩ transaction càng dài càng an toàn

Transaction quá dài có thể giữ khóa/snapshot, gây bloat và ảnh hưởng vận hành. Mức isolation cao cần đi kèm transaction ngắn và retry đúng.

## 33. Bài tập thực hành có đáp án

Dùng schema `mvcc_lab` mục 5. Với bài thử hai phiên, hãy chạy theo đúng thứ tự A/B và chỉ reset lab sau khi đã kết thúc cả hai transaction.

### Bài 1. Giải thích vấn đề cần nhiều phiên bản

**Câu hỏi:** A đang đọc balance 100, B cần cập nhật thành 150. Nếu chỉ ghi đè mà không giữ dữ liệu cũ hoặc chặn B, chuyện gì có thể xảy ra?

**Đáp án:** A có thể không tiếp tục đọc được snapshot nhất quán. MVCC cho phép giữ phiên bản 100 cho snapshot cũ và tạo 150 cho snapshot mới sau commit, giảm việc reader/writer phải chờ nhau.

### Bài 2. Nhận biết snapshot READ COMMITTED

A `BEGIN READ COMMITTED` và đọc 200. B cập nhật thành 225 rồi commit. A đọc lại trong cùng transaction.

**Đáp án:** A có thể thấy 225 ở SELECT thứ hai vì đó là statement mới với snapshot mới; không phải dirty read vì B đã commit.

### Bài 3. Nhận biết snapshot REPEATABLE READ

A `BEGIN REPEATABLE READ` và đọc 100. B cập nhật thành 150 rồi commit. A đọc lại trước khi kết thúc.

**Đáp án:** A vẫn thấy 100 theo snapshot transaction đã thiết lập. Sau khi A kết thúc và thực hiện SELECT mới, nó có thể thấy 150.

### Bài 4. Dirty read có xuất hiện ở PostgreSQL READ UNCOMMITTED không?

**Đáp án:** Không. PostgreSQL xử lý `READ UNCOMMITTED` như `READ COMMITTED`; dữ liệu chưa commit của transaction khác không trở thành kết quả SELECT thông thường.

### Bài 5. Hai writer và khóa hàng

A UPDATE tài khoản 3 từ 50 lên 60 nhưng chưa commit. B cố UPDATE cùng hàng `+20`.

**Đáp án:** B có thể phải chờ khóa hàng của A; sau A commit, ở READ COMMITTED B có thể áp +20 trên hàng phù hợp và thu 80. Nếu mức isolation khác, B có thể cần retry do serialization failure.

### Bài 6. Cách nào hạn chế lost update?

So sánh hai lệnh:

~~~sql
-- Giá trị 90 được tính từ bản SELECT cũ ở ứng dụng.
UPDATE mvcc_lab.accounts
SET balance = 90
WHERE account_id = 1;

-- Trừ trực tiếp từ phiên bản hàng mà UPDATE xử lý.
UPDATE mvcc_lab.accounts
SET balance = balance - 10
WHERE account_id = 1 AND balance >= 10;
~~~

**Đáp án:** Lệnh thứ hai an toàn hơn cho phép trừ một hàng dưới READ COMMITTED vì công thức và điều kiện nằm trong chính UPDATE. Lệnh thứ nhất có thể ghi đè một thay đổi đã commit sau bản đọc cũ.

### Bài 7. Optimistic locking

~~~sql
BEGIN;

UPDATE mvcc_lab.accounts
SET
    balance = 95,
    row_version = row_version + 1
WHERE account_id = 1
  AND row_version = 0
RETURNING balance, row_version;

ROLLBACK;
~~~

**Đáp án:** Khi version còn 0, UPDATE trả một hàng và version mới 1; nếu đã bị writer khác tăng version, trả 0 hàng.

### Bài 8. Vì sao ctid không phải primary key?

**Đáp án:** `ctid` chỉ vị trí vật lý tuple trong heap, có thể đổi sau UPDATE hoặc bảo trì như viết lại bảng. `account_id` mới là khóa định danh hàng logic.

### Bài 9. Vì sao xmax khác 0 chưa chắc hàng bị xóa?

**Đáp án:** Metadata `xmax` còn có thể chứa thông tin lock hoặc transaction chưa commit/đã rollback. Visibility phải xét trạng thái giao dịch và các metadata khác, không chỉ một con số.

### Bài 10. Vì sao UPDATE có thể làm bảng phình to?

**Đáp án:** UPDATE thường tạo phiên bản tuple mới. Phiên bản cũ có thể phải giữ cho snapshot đang hoạt động, rồi được vacuum/pruning thu hồi sau. Nếu cập nhật nhiều hoặc transaction dài giữ snapshot, dead tuples có thể tích tụ.

### Bài 11. Transaction đọc dài ảnh hưởng VACUUM như thế nào?

**Đáp án:** Snapshot cũ có thể còn cần tuple version cũ nên VACUUM chưa thể dọn hết. Hệ thống có thể tăng bloat; cần quản lý transaction và autovacuum.

### Bài 12. VACUUM và VACUUM FULL khác nhau?

**Đáp án:** VACUUM thông thường dọn/reuse không gian và bảo trì MVCC với khả năng cùng hoạt động với workload; VACUUM FULL viết lại bảng, có thể thu nhỏ file nhưng cần khóa mạnh.

### Bài 13. HOT có xóa MVCC không?

**Đáp án:** Không. HOT là tối ưu giảm index maintenance khi UPDATE đủ điều kiện; phiên bản tuple vẫn tồn tại theo cơ chế MVCC.

### Bài 14. Xem phiên bản hiện tại

~~~sql
SELECT
    account_id,
    balance,
    xmin::text AS creating_xid,
    xmax::text AS xmax_info,
    ctid::text AS location
FROM mvcc_lab.accounts
ORDER BY account_id;
~~~

**Đáp án:** Có thể quan sát metadata của các tuple hiện tại nhìn thấy. Không thể kết luận mọi phiên bản cũ hoặc toàn bộ lịch sử chỉ từ SELECT này.

### Bài 15. MVCC và WAL khác nhau thế nào?

**Đáp án:** MVCC quyết định snapshot nào thấy phiên bản nào và hỗ trợ đọc–ghi đồng thời. WAL ghi thông tin cần cho durability/crash recovery/replication. Hai cơ chế liên quan nhưng phục vụ mục đích khác nhau.

### Bài 16. Vì sao REPEATABLE READ có thể vẫn có write skew?

**Đáp án:** Hai transaction có thể cùng đọc một bất biến dựa trên nhiều hàng rồi cập nhật hai hàng khác nhau. Không có xung đột writer trên cùng hàng nhưng trạng thái cuối vi phạm bất biến. Cần SERIALIZABLE/constraint/khóa phù hợp và retry khi cần.

### Bài 17. Vì sao SELECT FOR UPDATE có thể làm reader chặn writer?

**Đáp án:** Vì đây là locking read, yêu cầu khóa hàng mà writer có thể phải chờ. Nó khác với SELECT thông thường dựa trên snapshot MVCC.

### Bài 18. Khi gặp SQLSTATE 40001 nên retry lệnh nào?

**Đáp án:** Thường cần rollback và retry **toàn transaction**, bao gồm đọc lại dữ liệu, tính lại quyết định và ghi dữ liệu. Không chỉ lặp lệnh UPDATE cuối.

## 34. Checklist khi áp dụng MVCC trong dự án

1. **Xác định mức isolation** của transaction, không giả định mọi SELECT luôn có cùng snapshot.
2. **Phân biệt reader thông thường với locking read** như `FOR UPDATE`.
3. **Giữ transaction ngắn** và luôn commit/rollback đúng lúc.
4. **Tránh stale read–modify–write**: đưa phép tính vào UPDATE hoặc dùng version check.
5. **Đảm bảo writer phối hợp đúng** bằng row lock, constraint và transaction.
6. **Nhận diện bất biến nhiều hàng** có thể cần SERIALIZABLE hoặc locking/constraint khác.
7. **Xử lý serialization/deadlock retry** toàn transaction với giới hạn và backoff.
8. **Không dựa vào xmin/xmax/ctid** để xây hợp đồng định danh lâu dài cho ứng dụng.
9. **Theo dõi autovacuum/dead tuples**, không tắt cơ chế dọn dẹp một cách tùy tiện.
10. **Giám sát transaction lâu và idle in transaction**.
11. **Hiểu VACUUM không tương đương VACUUM FULL** và không tự thu nhỏ file ngay.
12. **Không coi tuple versions là audit history**; xây lịch sử nghiệp vụ riêng nếu cần.
13. **Đánh giá index/HOT/WAL** khi UPDATE với tần suất cao.
14. **Kiểm thử bằng ít nhất hai session** để nhìn rõ hiện tượng đồng thời.
15. **Dùng database lab riêng** cho các thí nghiệm thay đổi và reset dữ liệu.
16. **Rà lại transaction boundary trong JDBC/framework**, tránh giữ snapshot qua các lời gọi mạng dài.

## 35. Tài liệu PostgreSQL chính thức để học sâu

Những chủ đề này được trình bày trong tài liệu PostgreSQL; khi triển khai thực tế, đối chiếu đúng major version của server:

- [Introduction to MVCC](https://www.postgresql.org/docs/current/mvcc-intro.html) — lý do dùng nhiều phiên bản và snapshot visibility.
- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html) — READ COMMITTED, REPEATABLE READ, SERIALIZABLE và hiện tượng đồng thời.
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html) — khóa bảng, khóa hàng, NOWAIT/SKIP LOCKED và deadlock.
- [System Columns](https://www.postgresql.org/docs/current/ddl-system-columns.html) — xmin, xmax, ctid.
- [Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html) — VACUUM, autovacuum, cleanup và freeze.
- [HOT](https://www.postgresql.org/docs/current/storage-hot.html) — Heap-Only Tuple updates.
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html) — pg_stat_activity, pg_stat_user_tables và các thống kê.
- [Write-Ahead Logging](https://www.postgresql.org/docs/current/wal-intro.html) — vai trò của WAL, khác với MVCC.

Đường dẫn `/current/` chỉ tài liệu phiên bản hiện hành trên website. Với hệ thống sử dụng phiên bản PostgreSQL cũ, mở đúng tài liệu major version tương ứng để tránh áp dụng nhầm hành vi hoặc tính năng mới.

## 36. Tổng kết

**PostgreSQL cần nhiều phiên bản hàng vì reader và writer có thể làm việc đồng thời nhưng vẫn cần một cách nhìn dữ liệu nhất quán.** Khi B cập nhật balance từ 100 lên 150, PostgreSQL không buộc phải phá hủy ngay bản 100: reader có snapshot cũ có thể tiếp tục đọc 100, còn reader có snapshot mới sau commit có thể đọc 150.

Bốn nguyên tắc cốt lõi:

1. **Snapshot quyết định phiên bản nào được nhìn thấy.** READ COMMITTED có thể đổi snapshot giữa các statement; REPEATABLE READ giữ snapshot trong transaction.
2. **MVCC giảm việc reader và writer thông thường chặn nhau, không loại bỏ khóa.** Hai writer trên cùng hàng vẫn cần phối hợp; SELECT FOR UPDATE có thể chặn writer.
3. **Giữ phiên bản cũ có chi phí.** UPDATE/DELETE tạo dữ liệu cần dọn; VACUUM/autovacuum và transaction ngắn là yếu tố vận hành thiết yếu.
4. **MVCC không tự giải quyết mọi vấn đề nghiệp vụ.** Lost update do ứng dụng ghi đè, write skew, idempotency, audit và side effect ngoài database vẫn cần thiết kế bổ sung.

Khi hiểu vì sao PostgreSQL không chỉ giữ một bản ghi duy nhất cho mỗi hàng logic, bạn sẽ hiểu sâu hơn **vì sao SELECT có thể không bị UPDATE chặn, vì sao hai transaction đọc thấy giá trị khác nhau, và vì sao VACUUM là thành phần bắt buộc của một hệ thống PostgreSQL có nhiều ghi đồng thời**.

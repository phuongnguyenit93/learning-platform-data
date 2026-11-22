# Global/private temporary table, vòng đời dữ liệu và điều kiện phiên bản

Trong một quy trình xử lý đơn hàng, ứng dụng có thể cần **gom một tập dữ liệu trung gian**, lọc nhiều lần, tính tổng rồi ghi kết quả cuối cùng vào bảng nghiệp vụ. Tập dữ liệu này không cần tồn tại vĩnh viễn sau khi transaction hoặc session kết thúc. Oracle Database cung cấp **global temporary table (GTT)** và, ở những phiên bản mới hơn, **private temporary table (PTT)** để giải quyết một số nhu cầu như vậy.

Hai kiểu bảng này dễ bị hiểu nhầm: chữ *global* **không** có nghĩa mọi user cùng thấy hàng dữ liệu, còn chữ *private* **không** chỉ đơn thuần là bảng được tạo trong một schema riêng. Sự khác biệt chính nằm ở **phạm vi tồn tại của định nghĩa bảng** và **vòng đời của các hàng tạm**, đặc biệt khi có `COMMIT`, `ROLLBACK` và connection pool.

Sau bài học, bạn có thể:

1. Phân biệt bảng thường, GTT và PTT theo metadata, dữ liệu và phạm vi phiên.
2. Dùng `ON COMMIT DELETE ROWS` và `ON COMMIT PRESERVE ROWS` cho GTT đúng mục đích.
3. Dùng `ON COMMIT DROP DEFINITION` và `ON COMMIT PRESERVE DEFINITION` cho PTT trên phiên bản hỗ trợ.
4. Dự đoán kết quả khi `COMMIT`, `ROLLBACK`, kết thúc session hoặc tái sử dụng JDBC connection.
5. Kiểm tra phiên bản, tên bảng và metadata trước khi chạy mã phụ thuộc PTT.

**Phạm vi thực hành:** các lệnh `CREATE`, `INSERT`, `DROP` trong bài chỉ dành cho schema/PDB thử nghiệm có quyền. Không chạy DDL minh họa trực tiếp trên database sản xuất.

## 1. Bảng tạm dùng để làm gì?

Một tình huống điển hình:

~~~mermaid
flowchart LR
    A["Dữ liệu nguồn"] --> B["Tập kết quả trung gian của request/batch"]
    B --> C["Lọc / JOIN / tổng hợp nhiều bước"]
    C --> D["Ghi kết quả chính thức"]
    B --> E["Dữ liệu tạm được dọn theo transaction/session"]
~~~

Ví dụ một đợt tính giá:

- Bước 1 lấy các `ORDER_ID` đủ điều kiện từ nhiều bảng.
- Bước 2 gắn tỷ lệ chiết khấu và dữ liệu kiểm tra.
- Bước 3 tính tổng, loại bản ghi lỗi.
- Bước 4 cập nhật bảng nghiệp vụ hoặc xuất báo cáo.

Nếu cùng một tập trung gian được dùng qua **nhiều câu SQL**, bảng tạm có thể hữu ích hơn việc lặp lại một truy vấn lớn. Tuy nhiên không phải bài toán nào cũng cần tạo bảng: `WITH`/CTE, inline view hay một câu `INSERT ... SELECT` đôi khi đơn giản hơn. Bảng tạm là quyết định thiết kế, không phải kỹ thuật tăng tốc mặc định.

### 1.1 Hai tầng cần tách biệt

Hãy tự hỏi:

**Tầng định nghĩa (metadata):** tên bảng, cột và cấu trúc có còn tồn tại khi session đã đóng không?

**Tầng dữ liệu (rows):** những hàng được một session chèn còn nhìn thấy sau `COMMIT`, `ROLLBACK` hoặc sau khi session kết thúc không?

Đây là hai trục **khác nhau**. GTT thường giữ nguyên định nghĩa qua nhiều session nhưng không giữ dữ liệu lâu dài. PTT có thể tự xóa **cả định nghĩa** theo transaction hoặc session.

## 2. So sánh nhanh bảng thường, GTT và PTT

| Thuộc tính | Bảng thường | Global temporary table (GTT) | Private temporary table (PTT) |
|---|---|---|---|
| Lệnh tạo | `CREATE TABLE` | `CREATE GLOBAL TEMPORARY TABLE` | `CREATE PRIVATE TEMPORARY TABLE` |
| Định nghĩa sau khi session tạo đóng | Vẫn tồn tại | **Vẫn tồn tại** | **Tự biến mất** theo phạm vi được chọn |
| Ai có thể thấy định nghĩa? | Các session đủ quyền | Các session đủ quyền trong phạm vi database/PDB | **Chỉ session tạo PTT** |
| Dữ liệu có chia sẻ giữa session? | Theo quyền truy cập và transaction isolation | **Không**: mỗi session chỉ thấy hàng tạm của mình | **Không**: session khác không thấy cả bảng lẫn hàng |
| Vòng đời dữ liệu | Cho tới khi có DML/DDL thay đổi | Đến cuối transaction hoặc session, tùy `ON COMMIT` | Cùng phạm vi transaction/session với định nghĩa PTT |
| Cú pháp `ON COMMIT` | Không theo cơ chế bảng tạm này | `DELETE ROWS` / `PRESERVE ROWS` | `DROP DEFINITION` / `PRESERVE DEFINITION` |
| Điều kiện phiên bản | Tính năng cơ bản lâu đời | Có từ các Oracle release cũ, kể cả 11g | **Giới thiệu từ Oracle Database 18c** |
| Nhu cầu thường gặp | Dữ liệu nghiệp vụ bền vững | Bảng staging có cấu trúc dùng lặp lại | Bảng tạm ad hoc, cấu trúc riêng của session |

Tên **global** nhấn mạnh rằng **định nghĩa GTT là đối tượng database dùng chung** trong phạm vi schema và quyền; các session có thể tham chiếu cùng tên `LAB_GTT_WORK` nhưng hàng của session A không trở thành hàng của session B. Tên **private** của PTT có nghĩa cả tên/định nghĩa bảng tạm lẫn dữ liệu của nó được giới hạn trong session đã tạo.

~~~mermaid
flowchart TD
    G["Metadata GTT: LAB_GTT_WORK"] --> A["Session A: dữ liệu tạm A"]
    G --> B["Session B: dữ liệu tạm B"]
    A -. "Không chia sẻ hàng" .- B
    C["Session C tạo ORA$PTT_WORK"] --> D["Metadata PTT + dữ liệu chỉ ở C"]
    E["Session D"] -. "Không nhìn thấy PTT của C" .-> D
~~~

## 3. Global temporary table: định nghĩa lâu dài, hàng tạm thời

GTT được tạo một lần trong schema thích hợp, giống một đối tượng database có metadata bền vững. Khi một session thực hiện `INSERT`, Oracle sử dụng vùng dữ liệu tạm dành cho session/transaction đó. Các session khác dùng **cùng định nghĩa** nhưng không đọc được những hàng tạm do session đầu tiên chèn.

Có hai chế độ:

| Chế độ GTT | Vòng đời hàng của một session | Khi nào phù hợp? |
|---|---|---|
| `ON COMMIT DELETE ROWS` | Hàng bị xóa/truncate khi transaction kết thúc, cụ thể khi `COMMIT`; `ROLLBACK` cũng hoàn tác dữ liệu transaction | Staging chỉ cần trong **một transaction** |
| `ON COMMIT PRESERVE ROWS` | Hàng tồn tại qua các lần `COMMIT` trong **cùng session**, dọn khi session kết thúc hoặc có thao tác dọn thích hợp | Staging cần dùng qua **nhiều transaction** trong một session |

Nếu bỏ mệnh đề `ON COMMIT` của GTT, mặc định là **`DELETE ROWS`**. Với bài học, nên viết tường minh để người đọc không phải đoán.

### 3.1 GTT theo transaction: ON COMMIT DELETE ROWS

Tạo một bảng thực hành khi đang ở schema có quyền `CREATE TABLE`:

~~~sql
CREATE GLOBAL TEMPORARY TABLE lab_gtt_tx (
    batch_id   NUMBER(10),
    item_id    NUMBER(10),
    amount     NUMBER(12,2)
)
ON COMMIT DELETE ROWS;
~~~

**Chỉ tạo bảng một lần**. Sau đó, trong **cùng kết nối**:

~~~sql
INSERT INTO lab_gtt_tx (batch_id, item_id, amount)
VALUES (1, 101, 50000);

INSERT INTO lab_gtt_tx (batch_id, item_id, amount)
VALUES (1, 102, 70000);

SELECT COUNT(*) AS rows_before_commit,
       SUM(amount) AS total_amount
FROM lab_gtt_tx;
~~~

Nếu các câu `INSERT` chưa bị autocommit, kết quả trước `COMMIT` là 2 hàng và tổng 120.000:

~~~text
ROWS_BEFORE_COMMIT   TOTAL_AMOUNT
------------------   ------------
2                    120000
~~~

Kết thúc transaction:

~~~sql
COMMIT;

SELECT COUNT(*) AS rows_after_commit
FROM lab_gtt_tx;
~~~

Kết quả `ROWS_AFTER_COMMIT = 0`. **Bảng `LAB_GTT_TX` vẫn tồn tại**; chỉ dữ liệu thuộc transaction của session này đã được dọn. Có thể bắt đầu transaction tiếp theo và tiếp tục `INSERT` mà không phải tạo lại GTT.

**Cảnh báo autocommit:** Nếu công cụ tự commit ngay sau mỗi `INSERT`, hàng GTT ở chế độ `DELETE ROWS` có thể biến mất trước khi bạn kịp chạy `SELECT` tiếp theo. Hãy dùng transaction có kiểm soát khi muốn thực hành đúng trình tự này.

### 3.2 GTT theo session: ON COMMIT PRESERVE ROWS

Tạo bảng khác:

~~~sql
CREATE GLOBAL TEMPORARY TABLE lab_gtt_session (
    batch_id   NUMBER(10),
    item_id    NUMBER(10),
    amount     NUMBER(12,2)
)
ON COMMIT PRESERVE ROWS;
~~~

Chạy:

~~~sql
INSERT INTO lab_gtt_session (batch_id, item_id, amount)
VALUES (2, 201, 30000);

COMMIT;

SELECT COUNT(*) AS rows_after_commit
FROM lab_gtt_session;
~~~

Trong cùng session, `ROWS_AFTER_COMMIT` vẫn là `1`. Nếu tiếp tục transaction mới và chèn thêm hàng, những hàng đã commit trước đó vẫn còn trong **session này**.

Đóng hẳn session rồi tạo một session mới đến cùng PDB/schema:

~~~sql
SELECT COUNT(*) AS rows_new_session
FROM lab_gtt_session;
~~~

Session mới vẫn có thể truy vấn **định nghĩa** `LAB_GTT_SESSION` nếu được cấp quyền, nhưng tập dữ liệu tạm của nó **bắt đầu trống**. Hàng của session cũ không được giữ như dữ liệu nghiệp vụ vĩnh viễn.

### 3.3 ROLLBACK có hành vi gì?

`ROLLBACK` hoàn tác DML chưa commit, kể cả trên bảng tạm. Ví dụ với GTT `PRESERVE ROWS`:

~~~sql
-- Giả sử đang ở session vừa có 1 hàng đã COMMIT.
INSERT INTO lab_gtt_session (batch_id, item_id, amount)
VALUES (2, 202, 40000);

SELECT COUNT(*) AS before_rollback
FROM lab_gtt_session;

ROLLBACK;

SELECT COUNT(*) AS after_rollback
FROM lab_gtt_session;
~~~

Hàng mới `ITEM_ID = 202` bị rollback, trong khi hàng `ITEM_ID = 201` đã commit trước đó vẫn có thể tồn tại trong session. Với GTT `DELETE ROWS`, dữ liệu gắn với transaction được dọn khi transaction kết thúc; vì vậy đừng dùng nó như một bộ nhớ lưu giá trị qua các transaction.

**Không nhầm hai ý:** `COMMIT` không làm dữ liệu `PRESERVE ROWS` bền vững qua session; `ROLLBACK` không xóa những thay đổi **đã commit** ở các transaction trước của GTT `PRESERVE ROWS`.

## 4. Hai session dùng cùng GTT nhưng dữ liệu không trộn

Giả sử GTT `LAB_GTT_SESSION` đã được tạo và hai người mở **hai database session vật lý khác nhau** vào cùng PDB:

| Thời điểm | Session A | Session B |
|---|---|---|
| 1 | `INSERT` hàng có `ITEM_ID = 1001` | Chưa insert |
| 2 | `COMMIT` | `SELECT COUNT(*)` từ GTT → 0 |
| 3 | `SELECT` từ GTT → thấy hàng 1001 | `INSERT` hàng có `ITEM_ID = 2001` |
| 4 | `SELECT` → vẫn chỉ thấy hàng 1001 | `COMMIT`, `SELECT` → chỉ thấy hàng 2001 |
| 5 | Đóng session | Tiếp tục thấy hàng 2001 trong session B |

Trong ví dụ này, cả hai đều tham chiếu **`LAB_GTT_SESSION`**, nhưng Oracle giữ vùng dữ liệu tạm riêng. Nếu session A đóng, dữ liệu tạm của A mất, còn định nghĩa GTT vẫn thuộc schema và session B vẫn có vùng dữ liệu của mình.

Điều này **không phải** row-level security hay phân vùng dữ liệu bằng cột `USER_ID`. Sự cách ly hàng trong GTT do chính cơ chế session/transaction của Oracle thực hiện. Ngược lại, nếu hai request HTTP thực ra dùng **cùng một database session được connection pool tái sử dụng**, chúng có thể nối tiếp nhau nhìn thấy dữ liệu `PRESERVE ROWS` còn sót nếu ứng dụng không dọn.

### 4.1 DDL trên GTT cần cẩn thận

Vì định nghĩa GTT là đối tượng dùng chung, chỉ tạo GTT trong bước triển khai schema thay vì chạy `CREATE GLOBAL TEMPORARY TABLE` ở mỗi HTTP request. GTT tồn tại cho tới khi có thao tác `DROP TABLE` được phép.

Oracle có giới hạn khi thay đổi hoặc drop GTT đang có session “bound” (đã sử dụng GTT theo cơ chế Oracle). Các lệnh như `ALTER TABLE`, `DROP TABLE` hoặc `CREATE INDEX` có thể thất bại, ví dụ `ORA-14452: attempt to create, alter or drop an index on temporary table already in use` hoặc thông báo DDL tương ứng. Đợi các session kết thúc sử dụng/giải phóng binding và phối hợp bảo trì thay vì cố thay đổi cấu trúc trên production.

Với GTT `PRESERVE ROWS`, việc thực hiện dọn dữ liệu và giải phóng binding có thể liên quan `TRUNCATE` trong chính session; trong mọi trường hợp, tránh thực thi DDL dọn bảng mà không hiểu tác động transaction và phiên bản đang dùng.

## 5. Private temporary table: cả định nghĩa và dữ liệu đều tạm

**Private temporary table** được giới thiệu trong **Oracle Database 18c**. Một session có thể tạo tên PTT của riêng nó, dùng cho công việc tạm và để Oracle tự bỏ bảng theo phạm vi đã khai báo. Session khác không nhìn thấy **định nghĩa** PTT này, ngay cả khi hai session sử dụng cùng tên PTT.

Trong môi trường có tính năng PTT, tên bảng phải bắt đầu bằng giá trị tham số `PRIVATE_TEMP_TABLE_PREFIX`. Mặc định là `ORA$PTT_`, ví dụ `ORA$PTT_STAGE_TX` hoặc `ORA$PTT_STAGE_SESSION`.

Nếu có quyền xem tham số:

~~~sql
SELECT name, value
FROM v$parameter
WHERE name = 'private_temp_table_prefix';
~~~

Trong các ví dụ sau giả sử prefix mặc định là `ORA$PTT_`. Nếu hệ thống đã cấu hình prefix khác, **phải đổi tên bảng ví dụ cho phù hợp**; không tự động gõ `ORA$PTT_` rồi cho rằng chắc chắn hợp lệ.

### 5.1 PTT theo transaction: ON COMMIT DROP DEFINITION

Trong schema/PDB thử nghiệm ở Oracle 18c+:

~~~sql
CREATE PRIVATE TEMPORARY TABLE ora$ptt_stage_tx (
    item_id   NUMBER(10),
    amount    NUMBER(12,2)
)
ON COMMIT DROP DEFINITION;
~~~

Đây là chế độ **mặc định** của PTT nếu không ghi mệnh đề `ON COMMIT`. Định nghĩa và dữ liệu PTT có phạm vi transaction. Sau khi tạo, **trước commit**:

~~~sql
INSERT INTO ora$ptt_stage_tx (item_id, amount)
VALUES (501, 100000);

SELECT COUNT(*) AS rows_before_commit
FROM ora$ptt_stage_tx;
~~~

Kết quả dự kiến là 1 hàng. Khi:

~~~sql
COMMIT;
~~~

Oracle dọn **cả nội dung lẫn định nghĩa** của `ORA$PTT_STAGE_TX`. Nếu sau đó cố:

~~~sql
-- Minh họa truy vấn sẽ không còn tìm thấy PTT vừa bị drop tự động.
SELECT * FROM ora$ptt_stage_tx;
~~~

thì có thể gặp `ORA-00942: table or view does not exist`. Đây là hành vi mong đợi của `ON COMMIT DROP DEFINITION`, **khác với GTT DELETE ROWS**: GTT còn bảng để tiếp tục `INSERT`, còn PTT này phải được tạo lại trong transaction mới.

**Chi tiết transaction quan trọng:** Theo quy tắc Oracle cho PTT transaction-specific, `CREATE PRIVATE TEMPORARY TABLE ... ON COMMIT DROP DEFINITION` **không phát sinh implicit commit** và có thể thực hiện trong một transaction đang mở. Vì thế phải kiểm soát rõ ranh giới transaction và tránh bật autocommit nếu muốn dùng bảng qua nhiều câu lệnh trước khi kết thúc transaction.

### 5.2 PTT theo session: ON COMMIT PRESERVE DEFINITION

Tạo PTT theo session:

~~~sql
CREATE PRIVATE TEMPORARY TABLE ora$ptt_stage_session (
    item_id   NUMBER(10),
    amount    NUMBER(12,2)
)
ON COMMIT PRESERVE DEFINITION;
~~~

Sau đó:

~~~sql
INSERT INTO ora$ptt_stage_session (item_id, amount)
VALUES (601, 210000);

COMMIT;

SELECT COUNT(*) AS rows_after_commit
FROM ora$ptt_stage_session;
~~~

Trong **cùng session**, bảng vẫn tồn tại và hàng đã commit vẫn có thể đọc, nên kết quả dự kiến là 1. Khi **session kết thúc**, định nghĩa và dữ liệu PTT này bị dọn. Nếu mở kết nối vật lý mới và chạy `SELECT` theo tên đó mà chưa tạo PTT của chính session mới, Oracle không tìm thấy bảng tạm.

**Chú ý DDL khác biệt:** Theo Oracle SQL Language Reference, việc **tạo PTT `ON COMMIT PRESERVE DEFINITION` có implicit commit**, trong khi tạo PTT `ON COMMIT DROP DEFINITION` thì không. Vì vậy không tạo PTT loại `PRESERVE DEFINITION` giữa một transaction nghiệp vụ chưa hoàn tất mà không cân nhắc hậu quả commit trước đó.

### 5.3 DROP PTT thủ công

Nếu muốn chủ động giải phóng PTT trong **session sở hữu** trước khi nó tự hết hạn:

~~~sql
DROP TABLE ora$ptt_stage_session;
~~~

Lệnh này chỉ phù hợp nếu bảng còn tồn tại tại thời điểm chạy. Không chạy ở session khác rồi kỳ vọng drop được PTT của session gốc. Với PTT, các thao tác DDL được hỗ trợ hạn chế hơn bảng thường; trong Oracle 19c, các lệnh DDL được cho phép về cơ bản là `CREATE`, `DROP` và `TRUNCATE` trên PTT.

## 6. Bảng bốn chế độ vòng đời: phần quan trọng nhất

| Kiểu và khai báo | Khi `COMMIT` | Sau khi đóng session | Định nghĩa có tồn tại cho session khác? |
|---|---|---|---|
| GTT `ON COMMIT DELETE ROWS` | **Hàng biến mất**, GTT còn | GTT còn, hàng của session đã dọn | **Có**, nếu được cấp quyền |
| GTT `ON COMMIT PRESERVE ROWS` | **Hàng còn** trong session | GTT còn, hàng của session đã dọn | **Có**, nếu được cấp quyền |
| PTT `ON COMMIT DROP DEFINITION` | **Cả bảng và hàng biến mất** | Không còn | **Không** |
| PTT `ON COMMIT PRESERVE DEFINITION` | **Bảng và hàng còn** trong session | **Cả bảng và hàng biến mất** | **Không** |

Hai kiểu “giữ qua commit” dễ nhầm:

- GTT `PRESERVE ROWS` giữ **hàng** qua commit; định nghĩa GTT vốn là đối tượng tồn tại lâu dài.
- PTT `PRESERVE DEFINITION` giữ **cả định nghĩa PTT và hàng của session** qua commit; mọi thứ vẫn tự biến mất khi session kết thúc.

Hai kiểu “chỉ trong transaction” cũng khác:

- GTT `DELETE ROWS` dọn **hàng**, để nguyên bảng dùng lại.
- PTT `DROP DEFINITION` dọn **định nghĩa và dữ liệu**, nên lần dùng tiếp phải `CREATE` lại.

### 6.1 Sơ đồ thời gian

~~~mermaid
sequenceDiagram
    participant S as Oracle session
    participant GT as GTT DELETE ROWS
    participant GS as GTT PRESERVE ROWS
    participant PT as PTT DROP DEFINITION
    participant PS as PTT PRESERVE DEFINITION
    S->>GT: INSERT 1 hàng
    S->>GS: INSERT 1 hàng
    S->>PT: CREATE + INSERT 1 hàng
    S->>PS: CREATE + INSERT 1 hàng
    Note over S,PS: Ví dụ khái niệm; tạo PTT PRESERVE có implicit commit nên không xâu chuỗi nguyên xi thứ tự này
    S->>S: COMMIT
    GT-->>S: 0 hàng; định nghĩa còn
    GS-->>S: 1 hàng; định nghĩa còn
    PT-->>S: Bảng không còn
    PS-->>S: 1 hàng; định nghĩa còn trong session
    S->>S: Đóng session
    GS-->>S: Dữ liệu session được dọn
    PS-->>S: Dữ liệu + định nghĩa được dọn
~~~

**Đọc sơ đồ như bảng so sánh độc lập**, không như một script duy nhất tạo tuần tự cả bốn bảng. Việc tạo PTT `PRESERVE DEFINITION` có implicit commit, sẽ làm thay đổi trạng thái của những bảng tạm transaction-specific đang dùng nếu thực hiện trong cùng transaction.

## 7. Tác động của COMMIT, ROLLBACK, autocommit và transaction

### 7.1 COMMIT không phải một sự kiện “phụ”

Với dữ liệu nghiệp vụ, `COMMIT` xác nhận thay đổi của transaction. Với bảng tạm, `COMMIT` **còn là ranh giới vòng đời** theo mệnh đề `ON COMMIT`.

Ví dụ một quy trình:

~~~text
BEGIN TRANSACTION
    INSERT vào bảng tạm theo transaction
    SELECT/JOIN/tính kết quả dựa trên bảng tạm
    INSERT/UPDATE bảng nghiệp vụ kết quả
COMMIT
    Bảng tạm transaction-specific được dọn theo quy tắc
~~~

Nếu chuyển `COMMIT` lên ngay sau bước chèn bảng tạm, truy vấn tiếp theo có thể thấy **0 hàng** hoặc **không còn bảng**, tùy là GTT hay PTT. Vì vậy mốc commit là một phần của thiết kế luồng xử lý.

### 7.2 ROLLBACK không phải “đóng phiên”

`ROLLBACK` hoàn tác những DML chưa commit trong transaction. Với GTT `PRESERVE ROWS`, nó không tự xóa những hàng đã commit từ transaction cũ của cùng session. Với GTT transaction-specific, dữ liệu transaction được dọn khi transaction kết thúc.

Với PTT `DROP DEFINITION`, phạm vi bảng là transaction; khi transaction chấm dứt, định nghĩa/dữ liệu không phải thứ để ứng dụng dựa vào trong transaction tiếp theo. Khi cần phân biệt hành vi rollback và DDL ở một bản release cụ thể, hãy thử trong một schema riêng với mốc transaction rõ ràng và tham chiếu tài liệu Oracle đúng phiên bản.

### 7.3 JDBC autocommit có thể gây mất bảng tạm trước khi đọc

Trong JDBC, `Connection` thường mặc định `autoCommit = true` nếu ứng dụng chưa điều chỉnh. Khi đó mỗi DML statement có thể trở thành một transaction tự commit; đối với GTT `DELETE ROWS`, dữ liệu vừa chèn bị dọn sau câu lệnh; đối với PTT `DROP DEFINITION`, định nghĩa có thể bị drop khi transaction kết thúc.

Mã dễ gây nhầm:

~~~java
// Minh họa rủi ro khi autoCommit=true.
try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO lab_gtt_tx (batch_id, item_id, amount) VALUES (?, ?, ?)")) {
    ps.setLong(1, 9L);
    ps.setLong(2, 901L);
    ps.setBigDecimal(3, new java.math.BigDecimal("1000"));
    ps.executeUpdate(); // Có thể auto-commit ngay sau statement.
}

// SELECT trong cùng session có thể thấy 0 hàng ở GTT DELETE ROWS.
~~~

Muốn thực hiện nhiều câu SQL trên bảng tạm transaction-specific, chúng phải dùng **cùng một connection** và cùng một transaction chưa kết thúc:

~~~java
boolean oldAutoCommit = connection.getAutoCommit();
connection.setAutoCommit(false);

try {
    // 1. INSERT vào GTT transaction-specific.
    try (PreparedStatement ps = connection.prepareStatement(
            "INSERT INTO lab_gtt_tx (batch_id, item_id, amount) VALUES (?, ?, ?)")) {
        ps.setLong(1, 9L);
        ps.setLong(2, 902L);
        ps.setBigDecimal(3, new java.math.BigDecimal("2000"));
        ps.executeUpdate();
    }

    // 2. Đọc bảng tạm trước COMMIT, vẫn dùng connection đó.
    try (PreparedStatement ps = connection.prepareStatement(
            "SELECT COUNT(*) FROM lab_gtt_tx");
         ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            long count = rs.getLong(1);
            System.out.println(count);
        }
    }

    // 3. Kết thúc transaction khi toàn bộ bước nghiệp vụ đã hoàn tất.
    connection.commit();
} catch (SQLException ex) {
    connection.rollback();
    throw ex;
} finally {
    connection.setAutoCommit(oldAutoCommit);
}
~~~

Đoạn Java giả định có `Connection connection`, các import JDBC phù hợp và quyền trên GTT đã tạo. Đây là ví dụ quản lý transaction trực tiếp, **không nên sao chép nguyên xi vào code Spring đang được transaction manager điều khiển**; trong Spring, giữ toàn bộ chuỗi DML/SELECT trong một ranh giới transaction được quản lý và bảo đảm sử dụng cùng physical connection.

Việc khôi phục `autoCommit` có thể tác động tới trạng thái transaction theo quy tắc JDBC; chỉ làm khi đã commit/rollback đúng ý định, tránh trả connection còn transaction dang dở cho pool.

## 8. Connection pool: “đóng connection” có thật sự kết thúc session?

Trong ứng dụng Java/Spring, lời gọi `connection.close()` thường trả connection **logic** về connection pool thay vì đóng ngay database session vật lý. Một session Oracle có thể sống qua nhiều request.

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant P as JDBC connection pool
    participant O as Oracle session vật lý
    participant B as Request B
    A->>P: Mượn connection
    P->>O: SELECT/INSERT vào GTT PRESERVE ROWS
    A->>O: COMMIT
    A->>P: close() -> trả connection
    B->>P: Mượn lại cùng connection vật lý
    B->>O: SELECT GTT PRESERVE ROWS
    O-->>B: Có thể còn hàng từ A
~~~

Đối với GTT `PRESERVE ROWS`, dữ liệu đã commit **vẫn còn trong session vật lý**, nên request B có thể nhìn thấy phần staging cũ nếu pool không dọn/reset trạng thái. Điều đó có thể gây **sai kết quả hoặc rò rỉ thông tin giữa request** trong phạm vi cùng database session.

PTT `PRESERVE DEFINITION` cũng có phạm vi session vật lý. Nếu pool giữ session, bảng PTT có thể vẫn còn sau khi request A kết thúc. Ngược lại, GTT `DELETE ROWS` và PTT `DROP DEFINITION` thường phù hợp hơn khi bảng chỉ phục vụ một transaction được quản lý chặt, nhưng phải chú ý ranh giới commit.

Các chiến lược an toàn:

1. **Ưu tiên bảng theo transaction** khi dữ liệu trung gian chỉ dùng trong một transaction và có thể kiểm soát commit.
2. Nếu dùng bảng tạm theo session, **xóa dữ liệu/chấm dứt phạm vi sử dụng có chủ đích** trước khi trả connection về pool; không tin rằng một `close()` logic là session đã chấm dứt.
3. Bảo đảm nhiều câu SQL của một tác vụ dùng **cùng connection**; chỉ mượn một connection khác từ pool sẽ không thấy hàng tạm của connection đầu.
4. Không sử dụng GTT/PTT làm bộ lưu tạm cross-request khi cần tính bền vững, truy cập từ session khác hoặc khôi phục sau lỗi.
5. Với dữ liệu nhạy cảm, kiểm soát cleanup và timeout theo chính sách ứng dụng, không dựa độc nhất vào việc physical session sẽ tự đóng.

Nếu dữ liệu phải được tiếp tục ở request khác **bất kể kết nối nào được cấp từ pool**, bảng tạm theo session không phải kho lưu phù hợp. Cân nhắc bảng bền vững có `JOB_ID`/`REQUEST_ID`, quyền truy cập và cơ chế dọn dữ liệu được thiết kế rõ ràng.

## 9. Vòng đời định nghĩa: khi nào cần CREATE hoặc DROP?

| Công việc | GTT | PTT |
|---|---|---|
| Triển khai định nghĩa bảng trong migration/schema | **Thường tạo một lần** | Không bắt buộc: có thể tạo trong session khi cần |
| Tạo ở mọi request | Thường **không nên** vì metadata tồn tại và xung đột tên | Có thể phù hợp nếu phiên bản và vòng đời transaction/session được quản lý |
| Hai session cùng dùng tên bảng | Dùng chung định nghĩa, dữ liệu riêng | Mỗi session có định nghĩa PTT của riêng mình |
| Cần đổi schema bảng | Có thể `ALTER`/`DROP` khi không còn session bound, theo quyền | Các DDL được hỗ trợ bị giới hạn; thường drop rồi tạo lại trong session |
| Phiên kết thúc | Định nghĩa GTT vẫn còn | Định nghĩa PTT biến mất |
| Trình triển khai khởi động lại ứng dụng | GTT không cần tạo lại nếu object vẫn tồn tại | PTT cần tạo lại ở session mới trước khi dùng |

Một lỗi triển khai hay gặp là:

~~~sql
-- Không nên đưa lệnh này vào mỗi HTTP request:
CREATE GLOBAL TEMPORARY TABLE lab_gtt_tx (
    id NUMBER
) ON COMMIT DELETE ROWS;
~~~

Sau lần tạo đầu, định nghĩa GTT đã tồn tại; các lần tạo sau có thể báo tên object đã được dùng, ví dụ `ORA-00955`. Đối với GTT, quy trình đúng thường là **tạo bằng migration/DDL một lần**, sau đó mỗi transaction chỉ thực hiện DML với dữ liệu riêng.

Với PTT, việc tạo trong mỗi session/transaction có thể là một phần workflow. Nhưng tạo `ON COMMIT PRESERVE DEFINITION` có implicit commit; không vô ý chạy lệnh đó trong transaction có dữ liệu nghiệp vụ đang chờ commit.

## 10. Điều kiện phiên bản và giới hạn riêng của PTT

### 10.1 PTT chỉ dùng trên Oracle 18c trở lên

GTT là khả năng lâu đời của Oracle. PTT bắt đầu từ **Oracle Database 18c**; vì thế các môi trường **Oracle 11g, 12.1, 12.2** không hỗ trợ `CREATE PRIVATE TEMPORARY TABLE` theo cú pháp này. Không thể thay một từ khóa để biến PTT thành GTT trên phiên bản cũ, vì vòng đời metadata khác nhau.

Trước khi chọn PTT, xác nhận phiên bản của **Oracle Database server**, không chỉ phiên bản client:

~~~sql
SELECT banner
FROM v$version;
~~~

Hoặc, khi được cấp quyền:

~~~sql
SELECT instance_name, version
FROM v$instance;
~~~

Trên CDB/PDB, kiểm tra đúng container hiện tại:

~~~sql
SELECT SYS_CONTEXT('USERENV','CON_NAME') AS current_container,
       SYS_CONTEXT('USERENV','SERVICE_NAME') AS current_service
FROM dual;
~~~

Nếu không có quyền truy vấn `V$VERSION` hoặc `V$INSTANCE`, nhờ DBA cung cấp release/version của server; không suy rằng client SQL Developer mới nghĩa là database đã hỗ trợ PTT.

### 10.2 PTT bắt buộc tuân theo prefix

Tham số `PRIVATE_TEMP_TABLE_PREFIX` mặc định là `ORA$PTT_`. Vì vậy:

~~~sql
-- Hợp lệ với prefix mặc định:
CREATE PRIVATE TEMPORARY TABLE ora$ptt_demo (
    id NUMBER
) ON COMMIT DROP DEFINITION;
~~~

Không dùng tên như `LAB_TEMP` cho PTT khi prefix mặc định còn là `ORA$PTT_`. Nếu PDB/database đã cấu hình prefix khác, ví dụ do DBA chọn, tên phải theo prefix thực tế. Tên có `$` ở đây là cú pháp Oracle hỗ trợ; không nhầm prefix với một tên schema.

### 10.3 Một số hạn chế cần biết ở Oracle 19c

Theo Oracle SQL Language Reference 19c, ngoài các hạn chế chung của temporary table, PTT có những giới hạn đáng chú ý:

| Nhu cầu | PTT Oracle 19c |
|---|---|
| Tạo index trên PTT | **Không hỗ trợ** |
| Định nghĩa cột có `DEFAULT` | **Không hỗ trợ** |
| Tạo materialized view hoặc zone map dựa trên PTT | **Không hỗ trợ** |
| Dùng PTT trong định nghĩa object bền vững như permanent view/trigger | **Không hỗ trợ** |
| Tham chiếu PTT qua database link | **Không hỗ trợ** |
| Một số DDL ngoài `CREATE`, `DROP`, `TRUNCATE` | **Không hỗ trợ** |
| Khai báo foreign key trên temporary table | Có hạn chế chung, **không hỗ trợ** theo tài liệu 19c |

Không nên dịch một DDL GTT có index/constraint/default phức tạp thành PTT chỉ bằng cách đổi `GLOBAL` thành `PRIVATE`. Nếu workload cần nhiều index hoặc những đặc tính schema bền vững, GTT có thể phù hợp hơn; vẫn phải đối chiếu hạn chế từng phiên bản.

Không sử dụng user `SYS` để thử tạo PTT; Oracle quy định PTT được tạo bởi user khác `SYS`. Thực hành trong schema riêng được cấp quyền theo chính sách của tổ chức.

### 10.4 Các phiên bản mới có thể thay đổi chi tiết

Một số giới hạn của PTT/GTT, cách quản lý memory/temp, view giám sát và cú pháp có thể khác giữa Oracle 18c, 19c, 21c, 23ai và release mới hơn. Bài sử dụng **Oracle 19c làm chuẩn cú pháp minh họa**, nên với production hãy kiểm tra tài liệu tương ứng release/patch/edition và chính sách database thực tế.

## 11. Kiểm tra metadata: nhận diện bảng tạm thuộc loại nào

### 11.1 GTT trong data dictionary

Vì GTT có định nghĩa bền vững trong schema, có thể tra metadata:

~~~sql
SELECT table_name,
       temporary,
       duration
FROM user_tables
WHERE table_name IN ('LAB_GTT_TX', 'LAB_GTT_SESSION')
ORDER BY table_name;
~~~

Đối với GTT, `TEMPORARY = 'Y'`; `DURATION` thường biểu diễn phạm vi như `SYS$TRANSACTION` (transaction-specific) hoặc `SYS$SESSION` (session-specific). Đây là thông tin **loại bảng**, không phải số hàng đang có trong session.

Nếu cần xem GTT thuộc schema khác và có quyền:

~~~sql
SELECT owner, table_name, temporary, duration
FROM all_tables
WHERE table_name = 'LAB_GTT_TX';
~~~

`ALL_TABLES` chỉ liệt kê object user được phép quan sát; root/PDB và quyền ảnh hưởng tập kết quả. Không dùng `USER_TABLES` để tìm PTT của session khác vì PTT không có metadata bền vững dùng chung như GTT.

### 11.2 PTT trong view chuyên dụng của session

Trên Oracle 18c+ hỗ trợ view tương ứng:

~~~sql
SELECT table_name, duration
FROM user_private_temp_tables
ORDER BY table_name;
~~~

`USER_PRIVATE_TEMP_TABLES` mô tả các PTT của **session hiện tại**. Cột `DURATION` hỗ trợ phân biệt phạm vi `TRANSACTION` hoặc `SESSION`. Nếu bạn đã commit một PTT `DROP DEFINITION` thì nó có thể **không còn trong kết quả**, bởi định nghĩa đã bị dọn.

Tài khoản quản trị có view `DBA_PRIVATE_TEMP_TABLES` để quan sát PTT trong phạm vi cho phép, với những thông tin bổ sung như session ID và instance ID theo release. **Việc biết tên PTT của một session khác không khiến user thông thường đọc được hàng PTT đó**.

### 11.3 Metadata không chứng minh có hàng trong session

~~~sql
SELECT COUNT(*) AS current_session_rows
FROM lab_gtt_session;
~~~

Kết quả này là số hàng **của session hiện tại**. `USER_TABLES` có thể cho biết GTT tồn tại và có `DURATION = SYS$SESSION` nhưng không thể thay thế câu `COUNT(*)` khi bạn muốn biết session của mình đang có bao nhiêu hàng.

Thống kê optimizer cho GTT và session có cơ chế riêng trong Oracle; không tự diễn giải `NUM_ROWS` từ data dictionary như “số hàng thời gian thực trong GTT của mọi session”.

## 12. GTT/PTT sử dụng lưu trữ tạm, nhưng không có nghĩa không tốn tài nguyên

Dù dữ liệu không được giữ lâu dài, khi insert vào GTT/PTT Oracle vẫn có thể phải cấp **temporary segments**, thực hiện I/O, sử dụng bộ nhớ và xử lý undo/redo theo cơ chế tương ứng. Bảng tạm **không đồng nghĩa một biến Java nằm trong RAM** và không đồng nghĩa “chắc chắn không ghi đĩa”.

Theo cơ chế thông thường, segments của bảng tạm có thể được cấp khi session bắt đầu nạp dữ liệu; loại transaction-specific được giải phóng theo ranh giới transaction, còn loại session-specific theo ranh giới session. Lượng TEMP tiêu thụ phụ thuộc số hàng, thao tác, cấu hình và workload.

Những lưu ý khi thiết kế:

- **TEMP tablespace có giới hạn.** Nhiều session đồng thời nạp dữ liệu trung gian lớn vẫn có thể làm hệ thống thiếu không gian TEMP.
- **Không dùng bảng tạm làm nơi sao lưu dữ liệu nghiệp vụ.** Dữ liệu tạm không có bảo đảm backup/recovery như bảng thường; khi session kết thúc hoặc instance gặp lỗi, không thiết kế ứng dụng dựa trên khả năng phục hồi dữ liệu tạm.
- **Không coi GTT luôn nhanh hơn CTE.** Tốc độ phụ thuộc optimizer, số bước truy cập, lọc/index, I/O và cách xử lý ứng dụng.
- **Không mặc định mọi thao tác GTT/PTT đều không sinh redo.** Metadata, undo và cơ chế Oracle vẫn cần được xét; chẩn đoán hiệu năng bằng số liệu thực tế thay vì khẩu hiệu “temporary = no logging”.

Trong môi trường DBA được phép, các view như `V$TEMPSEG_USAGE` hỗ trợ quan sát sử dụng segment tạm theo session tại thời điểm truy vấn; không dùng một snapshot để kết luận lịch sử tiêu thụ TEMP cả ngày.

## 13. Các lỗi và tình huống dễ nhầm

| Hiện tượng | Khả năng liên quan | Việc cần kiểm tra |
|---|---|---|
| GTT `DELETE ROWS` vừa insert đã `SELECT` ra 0 | Client/JDBC đã autocommit hoặc transaction kết thúc | Xem autocommit, ranh giới `COMMIT` và cùng connection |
| GTT `PRESERVE ROWS` vẫn có dữ liệu ở request sau | Pool tái sử dụng session vật lý, dữ liệu staging chưa dọn | Kiểm tra physical session, cleanup và transaction |
| PTT `DROP DEFINITION` báo `ORA-00942` sau commit | Bảng **đã tự bị drop** theo thiết kế | Tạo PTT lại trong transaction mới |
| PTT có `PRESERVE DEFINITION` nhưng session mới không thấy | PTT có định nghĩa **private của session tạo** | Mở lại PTT trong session mới; không kỳ vọng chia sẻ metadata |
| DDL `CREATE PRIVATE TEMPORARY TABLE` không được nhận | Server trước Oracle 18c hoặc cú pháp/quyền không phù hợp | Xem phiên bản server và SQL Language Reference của release |
| Tên PTT không hợp lệ | Thiếu hoặc sai `PRIVATE_TEMP_TABLE_PREFIX` | Đọc tham số và dùng tên có prefix đúng |
| Tạo index/default column trên PTT bị từ chối | Hạn chế PTT ở release đang dùng | Cân nhắc GTT hoặc thiết kế staging khác |
| `ORA-00955` khi tạo GTT | Định nghĩa GTT đã tồn tại như object bền vững | Tạo GTT một lần ở migration; dùng DML cho các request |
| DDL trên GTT đang sử dụng bị từ chối, có thể `ORA-14452` | GTT còn được một hoặc nhiều session bound | Phối hợp kết thúc sử dụng/giải phóng binding, không ép DROP |
| Hai session cùng GTT nhưng `COUNT(*)` khác nhau | Cách ly dữ liệu tạm theo session | Đối chiếu `SESSION_USER`, connection và thời điểm |
| Dùng bảng tạm rồi dữ liệu mất khi restart | Dữ liệu được thiết kế là tạm | Dữ liệu cần bền vững phải lưu bảng thường với transaction phù hợp |
| Cùng tên bảng nhưng chạy ở PDB khác trả lỗi | Định nghĩa GTT/PTT thuộc phạm vi schema/container thực tế | Xem `CON_NAME`, service và quyền |

### 13.1 Sơ đồ chẩn đoán nhanh

~~~mermaid
flowchart TD
    A["SQL với bảng tạm báo lỗi hoặc không có hàng"] --> B{"GTT hay PTT?"}
    B -->|GTT| C["Tra USER_TABLES: TEMPORARY, DURATION"]
    B -->|PTT| D["Kiểm tra version 18c+, prefix, USER_PRIVATE_TEMP_TABLES"]
    C --> E{"DELETE ROWS hay PRESERVE ROWS?"}
    D --> F{"DROP DEFINITION hay PRESERVE DEFINITION?"}
    E --> G["Kiểm tra COMMIT/ROLLBACK, physical connection"]
    F --> G
    G --> H["Đối chiếu transaction và session tại thời điểm lỗi"]
    H --> I["Sửa vòng đời hoặc thiết kế dữ liệu, không tự nâng quyền"]
~~~

## 14. Bài thực hành theo thứ tự

**Bước 1 — Xác định môi trường.** Đăng nhập vào PDB/schema thực hành, kiểm tra container và phiên bản server. Nếu không có quyền đọc view hệ thống, nhờ DBA xác nhận; không chạy lệnh PTT nếu database dưới 18c.

~~~sql
SELECT USER AS login_user,
       SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name,
       SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name
FROM dual;
~~~

**Bước 2 — Thử GTT transaction.** Tạo `LAB_GTT_TX`, tắt autocommit của client nếu cần. `INSERT` hai hàng, `SELECT COUNT(*)`, sau đó `COMMIT` và `SELECT COUNT(*)` lần nữa. Vì sao bảng vẫn được truy vấn thành công nhưng số hàng bằng 0?

**Bước 3 — Thử GTT session.** Tạo `LAB_GTT_SESSION`, insert và commit. `SELECT COUNT(*)` trong cùng connection rồi dùng một **connection mới** để đọc. Vì sao hai connection có kết quả khác dù cùng schema?

**Bước 4 — Thử rollback.** Trên GTT `PRESERVE ROWS`, commit một hàng, chèn một hàng khác rồi rollback. Xác định hàng nào còn và giải thích bằng ranh giới transaction.

**Bước 5 — Thử PTT transaction trên Oracle 18c+.** Tạo `ORA$PTT_STAGE_TX`, insert một hàng và select trước commit. Sau commit, thử đọc lại bằng một câu lệnh riêng; giải thích tại sao báo không tìm thấy bảng là đúng thiết kế.

**Bước 6 — Thử PTT session.** Tạo `ORA$PTT_STAGE_SESSION`, insert, commit rồi select trong cùng session. Đóng session thật sự và mở session mới; vì sao phải tạo bảng lại?

**Bước 7 — Xem metadata.** Đối chiếu `USER_TABLES` cho GTT với `USER_PRIVATE_TEMP_TABLES` cho PTT. Dùng `DURATION` để liên hệ loại bảng với hành vi đã quan sát.

**Bước 8 — Mô phỏng connection pool.** Một request A dùng GTT `PRESERVE ROWS` rồi trả connection về pool. Request B mượn lại cùng physical connection. Nêu rủi ro và chiến lược cleanup/transaction phù hợp.

**Bước 9 — Thiết kế tương thích.** Dự án có production Oracle 12.2 nhưng dev Oracle 19c. Một module tạo PTT trong mỗi request. Hãy đề xuất phương án không dùng PTT trên production cũ và chỉ rõ thay đổi về vòng đời metadata.

### Gợi ý trả lời sau thực hành

1. **Tại sao `ON COMMIT DELETE ROWS` khác `ON COMMIT DROP DEFINITION`?** Vì GTT chỉ dọn hàng còn PTT dọn cả bảng.
2. **Tại sao cùng GTT nhưng hai session không thấy hàng của nhau?** Vì dữ liệu tạm được cách ly theo session dù metadata chung.
3. **Tại sao `connection.close()` chưa chắc dọn dữ liệu `PRESERVE ROWS`?** Vì pool có thể giữ physical session còn hoạt động.
4. **Tại sao không tạo GTT ở mỗi request?** Vì định nghĩa GTT là object bền vững, tạo lặp lại gây xung đột và tác động DDL.
5. **Tại sao không mặc định PTT dùng được trên mọi Oracle?** Vì PTT cần server Oracle 18c+ và phải tuân thủ hạn chế release, prefix và quyền.

## 15. Khi nào chọn GTT, PTT hoặc giải pháp khác?

| Nhu cầu | Hướng lựa chọn |
|---|---|
| Schema staging được nhiều session/chương trình dùng **về định nghĩa**, dữ liệu riêng | **GTT** tạo sẵn bằng migration |
| Dữ liệu chỉ cần trong một transaction, bảng đã được triển khai | GTT `ON COMMIT DELETE ROWS` |
| Dữ liệu cần qua nhiều commit trong cùng session vật lý | GTT `ON COMMIT PRESERVE ROWS`, kèm cleanup rõ ràng |
| Bảng trung gian ad hoc, định nghĩa chỉ cần trong transaction, Oracle 18c+ | PTT `ON COMMIT DROP DEFINITION` |
| Bảng trung gian ad hoc, định nghĩa cần qua nhiều commit trong một session, Oracle 18c+ | PTT `ON COMMIT PRESERVE DEFINITION`, chú ý implicit commit lúc CREATE |
| Cần truy cập dữ liệu từ nhiều session hoặc request bất kỳ | Bảng **bền vững** kèm khóa tác vụ/ủy quyền, không dùng session-private data |
| Cần một phép biến đổi SQL ngắn | Cân nhắc `WITH`/CTE, inline view hoặc một câu SQL trực tiếp |
| Cần hỗ trợ Oracle 11g/12c đồng thời | Dùng GTT hoặc thiết kế tương thích; **không phụ thuộc PTT** |
| Cần index/default column phức tạp trên bảng staging | Xem GTT hoặc bảng thường; **không mặc định PTT hỗ trợ** |

Một nguyên tắc quan trọng: **chọn vòng đời đúng trước khi tối ưu hiệu năng**. Cần xác định phần dữ liệu tạm được dùng trong *một transaction*, *một session* hay *nhiều session*. Sau đó mới chọn GTT/PTT và quyết định điểm commit, cleanup, connection pool, quyền và metadata.

## 16. Ghi nhớ cuối bài

- **GTT:** *định nghĩa global, dữ liệu private theo session*. `DELETE ROWS` dọn hàng sau transaction; `PRESERVE ROWS` giữ hàng qua commit trong session. Định nghĩa bảng vẫn tồn tại sau khi session kết thúc.
- **PTT (Oracle 18c+):** *định nghĩa và dữ liệu private*. `DROP DEFINITION` dọn cả bảng khi commit; `PRESERVE DEFINITION` giữ bảng và hàng đến khi kết thúc session. Tên PTT phải theo `PRIVATE_TEMP_TABLE_PREFIX`, mặc định `ORA$PTT_`.
- **DDL của PTT không đồng nhất:** tạo PTT theo transaction `DROP DEFINITION` không implicit commit, còn tạo PTT `PRESERVE DEFINITION` có implicit commit theo quy tắc Oracle 19c.
- **JDBC autocommit/connection pool có thể làm sai toàn bộ kỳ vọng vòng đời.** Cùng connection vật lý và transaction đúng là điều kiện cần khi thao tác nhiều bước với bảng tạm.
- **Bảng tạm không phải kho lưu dữ liệu bền vững**, không mặc định không tốn TEMP/I/O, và không cho phép bỏ qua quyền hay giới hạn phiên bản.

### Tham khảo chính thức

- Oracle Database 19c, *SQL Language Reference — CREATE TABLE*: https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-TABLE.html
- Oracle Database 19c, *Administrator's Guide — Managing Tables (Temporary Tables)*: https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-tables.html
- Oracle Database 19c, *Database Reference — USER_PRIVATE_TEMP_TABLES*: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_PRIVATE_TEMP_TABLES.html

Khi triển khai, xác nhận đúng release và PDB, tạo cấu trúc bảng tạm theo nhu cầu thực tế, kiểm soát transaction/session và thử cùng workflow trên **physical connection** thật của ứng dụng. Đó là cách tránh trường hợp “bảng tạm tự mất”, “bảng tạm không thấy hàng” hoặc “request sau nhìn thấy dữ liệu tạm của request trước” dù từng câu SQL riêng lẻ đều hợp lệ.

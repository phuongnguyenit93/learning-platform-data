# Thiết lập môi trường thực nghiệm bằng hai phiên cơ sở dữ liệu độc lập

## 1. Vì sao cần hai phiên làm việc?

Khi nhiều người dùng cùng đọc hoặc thay đổi dữ liệu, hệ quản trị cơ sở dữ liệu (DBMS) phải xử lý các giao dịch (*transaction*) diễn ra đồng thời. Một câu lệnh SQL chạy đúng khi chỉ có một người dùng chưa chắc tạo ra kết quả như mong muốn khi giao dịch khác đang hoạt động. Để quan sát hiện tượng này, cần ít nhất **hai kết nối cơ sở dữ liệu độc lập**, có thể giữ hai giao dịch mở cùng lúc.

Trong bài thực hành, ta dùng **PostgreSQL 16** và hai cửa sổ dòng lệnh:

- **Phiên A**: kết nối thứ nhất, đóng vai trò giao dịch đang đọc hoặc sửa dữ liệu.
- **Phiên B**: kết nối thứ hai, đóng vai trò giao dịch cạnh tranh với A.
- **Một cơ sở dữ liệu dùng chung**: cả A và B phải nhìn vào cùng bảng, cùng hàng dữ liệu thì mới quan sát được tương tác.

“Hai phiên độc lập” ở đây có nghĩa là **hai kết nối riêng đến cùng một hệ quản trị và cùng một cơ sở dữ liệu**, không phải hai máy chủ hay hai bản sao dữ liệu tách biệt. Mỗi kết nối có mã tiến trình phía máy chủ, trạng thái giao dịch và khóa riêng.

```text
     Terminal A / psql A                  Terminal B / psql B
        Phiên kết nối A                      Phiên kết nối B
              |                                   |
              +--------------+--------------------+
                             |
                      PostgreSQL 16
                             |
                    concurrency_lab
                             |
                     public.lab_accounts
```

Nếu gõ hai lệnh `BEGIN` liên tiếp trong **cùng một** cửa sổ `psql`, ta không tạo được hai giao dịch độc lập. PostgreSQL vẫn đang dùng một kết nối, nên việc tạo hai terminal hoặc hai kết nối thật sự là điều kiện đầu tiên của bài.

### Kết quả mong đợi

Sau khi thiết lập, bạn có thể:

1. Mở và giữ giao dịch ở phiên A trong khi phiên B tiếp tục chạy SQL.
2. Xác nhận hai phiên có `pg_backend_pid()` khác nhau nhưng dùng cùng cơ sở dữ liệu.
3. Quan sát phiên B đọc dữ liệu đã commit trong khi A đang có thay đổi chưa commit.
4. Quan sát phiên B phải chờ khi cố sửa cùng một hàng mà A đang khóa.
5. Thực hiện `COMMIT` và `ROLLBACK` độc lập cho mỗi phiên, sau đó trả dữ liệu về trạng thái ban đầu để thử nghiệm tiếp.

## 2. Chuẩn bị công cụ và máy chủ PostgreSQL

Ví dụ này sử dụng **Docker** để tạo một môi trường thực hành riêng, tránh phụ thuộc vào cách cài PostgreSQL trên từng hệ điều hành. Cần có Docker Engine hoặc Docker Desktop đang chạy, một terminal hỗ trợ nhập lệnh tương tác (PowerShell, Windows Terminal, Terminal trên macOS hoặc Linux) và quyền chạy Docker.

Kiểm tra Docker:

```powershell
docker --version
docker info
```

Tạo container PostgreSQL. Có thể chạy lệnh dưới đây trong PowerShell, Bash hoặc terminal tương đương; lệnh nằm trên một dòng nên không phụ thuộc ký tự nối dòng của hệ điều hành:

```powershell
docker run --name tx-concurrency-lab -e POSTGRES_USER=lab_user -e POSTGRES_PASSWORD=lab_pass_123 -e POSTGRES_DB=concurrency_lab -p 127.0.0.1:55432:5432 -d postgres:16
```

Các tham số chính:

| Tham số | Ý nghĩa |
| --- | --- |
| `--name tx-concurrency-lab` | Đặt tên container để các lệnh tiếp theo truy cập đúng máy chủ |
| `POSTGRES_USER=lab_user` | Tạo tài khoản dùng cho phòng thực hành |
| `POSTGRES_PASSWORD=lab_pass_123` | Mật khẩu minh họa chỉ dùng ở môi trường cục bộ |
| `POSTGRES_DB=concurrency_lab` | Tạo cơ sở dữ liệu dùng chung cho A và B |
| `-p 127.0.0.1:55432:5432` | Cho phép công cụ trên máy cá nhân kết nối tới cổng `55432` qua `localhost` |
| `-d postgres:16` | Chạy PostgreSQL 16 ở chế độ nền |

Kiểm tra trạng thái máy chủ:

```powershell
docker ps --filter name=tx-concurrency-lab
docker exec tx-concurrency-lab pg_isready -U lab_user -d concurrency_lab
```

Khi máy chủ sẵn sàng, `pg_isready` thông báo chấp nhận kết nối (*accepting connections*). Trong lần chạy đầu, quá trình khởi tạo cơ sở dữ liệu có thể cần một chút thời gian. Nếu cần xem lỗi khởi động, dùng `docker logs tx-concurrency-lab`.

> Tên tài khoản và mật khẩu trong ví dụ chỉ phục vụ thực nghiệm trên máy cá nhân. Không dùng thông tin này cho hệ thống thật hoặc mở cổng thực hành ra mạng công cộng.

## 3. Khởi tạo dữ liệu chung

Mở **Terminal A** và kết nối đến PostgreSQL trong container:

```powershell
docker exec -it tx-concurrency-lab psql -X -U lab_user -d concurrency_lab
```

Tùy chọn `-it` giữ chế độ nhập SQL tương tác; `-X` bỏ qua cấu hình `psql` cá nhân, giúp môi trường dễ tái hiện. Khi xuất hiện dấu nhắc tương tự `concurrency_lab=#`, phiên A đã kết nối thành công. Các câu lệnh SQL tiếp theo được gõ **bên trong `psql`**, không phải tại dấu nhắc PowerShell.

Trong phiên A, tạo bảng và hai dòng dữ liệu thử nghiệm:

```sql
DROP TABLE IF EXISTS public.lab_accounts;

CREATE TABLE public.lab_accounts (
    account_id INTEGER PRIMARY KEY,
    owner_name TEXT NOT NULL,
    balance INTEGER NOT NULL CHECK (balance >= 0)
);

INSERT INTO public.lab_accounts (account_id, owner_name, balance)
VALUES
    (1, 'An', 1000),
    (2, 'Binh', 1000);

SELECT account_id, owner_name, balance
FROM public.lab_accounts
ORDER BY account_id;
```

Kết quả ban đầu:

| account_id | owner_name | balance |
| ---: | --- | ---: |
| 1 | An | 1000 |
| 2 | Binh | 1000 |

Bảng `lab_accounts` là dữ liệu thực hành, đơn vị số dư chỉ là con số giả định. Lệnh `DROP TABLE IF EXISTS` sẽ xóa bảng cùng tên nếu đã tồn tại trong **cơ sở dữ liệu thực hành**; không chạy đoạn chuẩn bị này trên cơ sở dữ liệu có dữ liệu cần giữ.

Theo mặc định, `psql` cho PostgreSQL thực thi từng câu lệnh riêng lẻ trong giao dịch tự động khi chưa có `BEGIN` (*autocommit*). Vì vậy, sau khi lệnh tạo bảng và `INSERT` chạy thành công, phiên khác có thể đọc dữ liệu vừa tạo.

## 4. Mở phiên B và xác nhận hai kết nối độc lập

Giữ nguyên Terminal A, mở **Terminal B** riêng rồi chạy cùng lệnh kết nối:

```powershell
docker exec -it tx-concurrency-lab psql -X -U lab_user -d concurrency_lab
```

Trong **cả hai** phiên, lần lượt chạy:

```sql
SELECT
    current_database() AS db_name,
    current_user AS db_user,
    pg_backend_pid() AS backend_pid,
    current_setting('transaction_isolation') AS isolation_level;
```

Ví dụ kết quả:

| Thuộc tính | Phiên A | Phiên B |
| --- | --- | --- |
| `db_name` | `concurrency_lab` | `concurrency_lab` |
| `db_user` | `lab_user` | `lab_user` |
| `backend_pid` | 71 | 84 |
| `isolation_level` | `read committed` | `read committed` |

**Các PID chỉ mang tính minh họa**; con số thực tế trên máy bạn sẽ khác. Điều kiện quan trọng là tên cơ sở dữ liệu phải giống nhau và `backend_pid` phải khác nhau. PID khác nhau chứng minh PostgreSQL đang phục vụ hai phiên kết nối riêng.

Trong PostgreSQL, mức cô lập mặc định thường là `READ COMMITTED`. Bạn có thể kiểm tra mặc định của máy chủ bằng:

```sql
SHOW default_transaction_isolation;
```

Các thực nghiệm dưới đây giả định hai phiên sử dụng `READ COMMITTED`. Để thiết lập rõ ràng mức cô lập cho **một giao dịch**, có thể dùng `BEGIN ISOLATION LEVEL READ COMMITTED;` thay cho `BEGIN;`.

### Phân biệt phiên, giao dịch và câu lệnh

| Khái niệm | Phạm vi | Trong thực hành này |
| --- | --- | --- |
| Phiên/kết nối (*session*) | Tồn tại từ khi kết nối cho tới khi thoát `psql` | Terminal A và Terminal B là hai phiên |
| Giao dịch (*transaction*) | Bắt đầu bằng `BEGIN`, kết thúc bằng `COMMIT` hoặc `ROLLBACK` | Mỗi phiên có thể giữ một giao dịch đang mở |
| Câu lệnh (*statement*) | Một lệnh SQL như `SELECT` hoặc `UPDATE` | Nhiều câu lệnh có thể thuộc cùng một giao dịch |
| Khóa (*lock*) | Được DBMS quản lý khi truy cập hoặc thay đổi tài nguyên | Hai lệnh `UPDATE` cùng hàng có thể phải chờ nhau |

Mở hai phiên không có nghĩa là tự động có hai giao dịch đang diễn ra. Muốn chủ động quyết định lúc giao dịch bắt đầu hoặc kết thúc, ta dùng `BEGIN`, `COMMIT`, `ROLLBACK`.

## 5. Thực nghiệm đầu tiên: đọc dữ liệu và tranh chấp khóa

Giữ **hai cửa sổ `psql` cùng mở**, thực hiện lần lượt theo đúng thứ tự dưới đây. Để kết quả có thể so sánh được, bắt đầu với số dư tài khoản `account_id = 1` bằng `1000`.

### Bước 1 — Phiên A cập nhật nhưng chưa commit

Ở **phiên A**:

```sql
BEGIN;

UPDATE public.lab_accounts
SET balance = balance - 100
WHERE account_id = 1
RETURNING account_id, balance;
```

Phiên A nhìn thấy số dư mới `900` trong chính giao dịch của mình. **Chưa chạy `COMMIT` hay `ROLLBACK` ở A.** PostgreSQL giữ thay đổi chưa commit và giữ khóa tương ứng trên hàng được cập nhật.

### Bước 2 — Phiên B đọc cùng hàng

Chuyển sang **phiên B**:

```sql
SELECT account_id, balance
FROM public.lab_accounts
WHERE account_id = 1;
```

Tại `READ COMMITTED`, B dự kiến đọc được `1000`, vì thay đổi xuống `900` ở A **chưa được commit**. Một truy vấn `SELECT` thông thường của PostgreSQL có thể đọc phiên bản dữ liệu đã commit nhờ cơ chế MVCC (*Multi-Version Concurrency Control*) trong khi giao dịch khác đang sửa hàng đó.

Sự khác nhau này có thể ghi lại:

| Thời điểm | Phiên A | Phiên B |
| --- | --- | --- |
| Trước khi A cập nhật | 1000 | 1000 |
| A đã `UPDATE`, chưa `COMMIT` | 900 | 1000 |

Đây là lý do hai kết nối độc lập hữu ích: cùng một bảng, nhưng mỗi giao dịch có thể nhìn thấy dữ liệu khác nhau tại một thời điểm.

### Bước 3 — Phiên B cũng muốn cập nhật hàng đang bị A giữ khóa

Ở **phiên B**, thực thi:

```sql
BEGIN;
SET LOCAL lock_timeout = '15s';

UPDATE public.lab_accounts
SET balance = balance + 50
WHERE account_id = 1
RETURNING account_id, balance;
```

Lệnh `UPDATE` của B sẽ **chờ** do A chưa kết thúc giao dịch đang cập nhật cùng hàng. `SET LOCAL lock_timeout = '15s'` giới hạn thời gian chờ khóa trong giao dịch B; nếu quá 15 giây mà A vẫn chưa giải phóng khóa, PostgreSQL hủy câu lệnh của B với lỗi dạng:

```text
ERROR: canceling statement due to lock timeout
```

Trong lúc B đang chờ, nếu thao tác đủ nhanh, có thể chạy ở **phiên A**:

```sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    pg_blocking_pids(pid) AS blocking_pids
FROM pg_stat_activity
WHERE datname = current_database()
  AND pid <> pg_backend_pid();
```

Kết nối B có thể hiện `wait_event_type = 'Lock'`, và `blocking_pids` chứa PID của A. Nếu B đã hết thời gian chờ trước khi truy vấn, hãy thực hiện lại bước này với `lock_timeout` lớn hơn. Các trường và giá trị chờ thực tế tùy vào thời điểm quan sát.

**Chú ý:** Khi `UPDATE` lỗi bên trong `BEGIN`, giao dịch của B rơi vào trạng thái lỗi (*aborted transaction*). Phải chạy lệnh sau ở **phiên B** trước khi tiếp tục:

```sql
ROLLBACK;
```

Lệnh này bỏ giao dịch lỗi của B. Nó **không** hủy giao dịch đang mở ở A.

### Bước 4 — Phiên A commit, phiên B đọc lại và cập nhật

Chuyển sang **phiên A**:

```sql
COMMIT;
```

Bây giờ B chạy:

```sql
SELECT account_id, balance
FROM public.lab_accounts
WHERE account_id = 1;
```

Kết quả dự kiến là `900`, vì thay đổi của A đã được commit và truy vấn mới của B tại `READ COMMITTED` thấy trạng thái đã commit mới nhất tại thời điểm câu lệnh bắt đầu.

Để xác nhận B có thể sửa hàng sau khi A giải phóng khóa, chạy ở **phiên B**:

```sql
BEGIN;

UPDATE public.lab_accounts
SET balance = balance + 50
WHERE account_id = 1
RETURNING account_id, balance;

COMMIT;
```

Số dư cuối cùng dự kiến là `950` (ban đầu `1000`, A trừ `100`, B cộng `50`). Bước thử này cho thấy việc B chờ ở trên xuất phát từ **giao dịch A còn giữ khóa**, chứ không phải do B mất quyền cập nhật.

### Dòng thời gian tổng hợp

```text
Thời gian     Phiên A                         Phiên B
   t1         BEGIN
   t2         UPDATE account_id=1 -> 900
   t3                                        SELECT -> 1000
   t4                                        BEGIN; UPDATE +50 -> chờ khóa
   t5                                        hết lock_timeout -> lỗi
   t6                                        ROLLBACK
   t7         COMMIT
   t8                                        SELECT -> 900
   t9                                        BEGIN; UPDATE +50; COMMIT -> 950
```

Trên các hệ quản trị khác, chi tiết xử lý MVCC, khóa và mức cô lập có thể khác. Những giá trị dự kiến trên áp dụng cho PostgreSQL với `READ COMMITTED` theo đúng thứ tự thao tác.

## 6. Phép thử đối chiếu: hai phiên cập nhật hai hàng khác nhau

Để phân biệt việc **cùng truy cập bảng** với việc **cùng tranh chấp một hàng**, hãy thử một lần chạy khác. Trước hết đảm bảo A và B không còn giao dịch mở; nếu thấy dấu nhắc có ký hiệu trạng thái giao dịch lỗi, hãy `ROLLBACK;`.

Ở **phiên A**:

```sql
BEGIN;

UPDATE public.lab_accounts
SET balance = balance - 10
WHERE account_id = 1
RETURNING account_id, balance;
```

Không commit ở A. Ngay lúc đó, ở **phiên B**:

```sql
BEGIN;

UPDATE public.lab_accounts
SET balance = balance + 10
WHERE account_id = 2
RETURNING account_id, balance;

COMMIT;
```

B thường hoàn thành ngay dù A vẫn giữ giao dịch mở, vì hai lệnh `UPDATE` tác động lên **hai hàng khác nhau** trong bảng. Cuối cùng, ở A chạy `ROLLBACK;` để loại bỏ thay đổi `-10` của A. Thay đổi `+10` ở tài khoản 2 vẫn được giữ vì đã commit độc lập tại B.

Kết quả này cho thấy giao dịch có thể chạy đồng thời và hoàn tất độc lập. Khóa hàng chỉ là một phần của cơ chế khóa; DDL, ràng buộc, khóa bảng và mức cô lập khác có thể tạo thêm điều kiện chờ, nên không nên khái quát rằng mọi cập nhật khác hàng đều luôn không chặn nhau.

## 7. Đưa dữ liệu về trạng thái ban đầu

Trước mỗi thí nghiệm mới, nên đóng các giao dịch chưa kết thúc bằng `COMMIT;` hoặc `ROLLBACK;` theo mục đích của bài. **Không chạy `COMMIT` chỉ để thoát lỗi:** nếu muốn hủy thao tác đang thử, dùng `ROLLBACK;`.

Khi cả A và B đã kết thúc giao dịch, dùng **một phiên** để đặt lại dữ liệu:

```sql
TRUNCATE TABLE public.lab_accounts;

INSERT INTO public.lab_accounts (account_id, owner_name, balance)
VALUES
    (1, 'An', 1000),
    (2, 'Binh', 1000);

SELECT account_id, balance
FROM public.lab_accounts
ORDER BY account_id;
```

Chạy `TRUNCATE` khi một phiên khác còn giữ giao dịch hoặc đang truy cập bảng có thể khiến lệnh phải chờ khóa. Vì vậy, nên hoàn tất giao dịch ở **cả hai** phiên trước khi đặt lại dữ liệu.

## 8. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `docker` không được nhận diện | Docker chưa được cài hoặc chưa có trong `PATH` | Cài/khởi động Docker Desktop hoặc Docker Engine; chạy lại `docker --version` |
| Container `tx-concurrency-lab` đã tồn tại | Đã chạy bài trước đó | Dùng `docker start tx-concurrency-lab` nếu container đang dừng; không tạo một container trùng tên |
| `pg_isready` chưa sẵn sàng | PostgreSQL còn khởi động hoặc khởi động lỗi | Kiểm tra `docker logs tx-concurrency-lab`; thử lại sau khi máy chủ sẵn sàng |
| Terminal B không thấy bảng | B kết nối nhầm database hoặc A chưa commit lệnh khởi tạo | Kiểm tra `current_database()`, rồi xác nhận bảng đã tạo thành công |
| Hai lần kiểm tra trả về cùng một `backend_pid` | Đang chạy trong cùng một kết nối/terminal | Mở hai tiến trình `psql` bằng hai terminal riêng, kiểm tra lại |
| B không bị chặn khi `UPDATE` cùng hàng | A đã `COMMIT`/`ROLLBACK` hoặc hai phiên sửa khác hàng | Đặt lại dữ liệu và làm lại theo đúng thứ tự, giữ A mở tại bước 1 |
| `current transaction is aborted` | Lệnh trong giao dịch đã lỗi, thường sau `lock_timeout` | Chạy `ROLLBACK;` ở chính phiên đang báo lỗi |
| Dấu nhắc `psql` chưa nhận câu lệnh | Thiếu dấu `;`, dấu nháy chưa đóng hoặc đang nhập tiếp | Kiểm tra cú pháp; có thể dùng `Ctrl+C` để hủy phần nhập dang dở |
| Công cụ GUI mở hai tab nhưng không thấy tương tranh | Hai tab có thể dùng chung connection hoặc tự commit mỗi lệnh | Tạo hai connection vật lý, tắt autocommit khi cần và kiểm tra PID |

Khi một câu lệnh “đứng yên”, hãy xem nó đang **đợi khóa** hay đang **chờ nhập hoàn tất câu SQL**. Ở `psql`, dấu nhắc như `concurrency_lab-#` thường cho biết câu lệnh còn dang dở; dấu nhắc có dấu `*` trong giao dịch thể hiện bạn đang ở giữa `BEGIN` và `COMMIT`/`ROLLBACK`. Nếu nghi bị khóa, `pg_stat_activity` và `pg_blocking_pids()` giúp nhận diện giao dịch đang chặn.

## 9. Kết thúc môi trường thực hành

Thoát từng cửa sổ `psql` bằng lệnh:

```text
\q
```

Khi không dùng nữa, dừng container từ terminal hệ điều hành:

```powershell
docker stop tx-concurrency-lab
```

Có thể khởi động lại sau bằng `docker start tx-concurrency-lab`. Nếu muốn **xóa hẳn môi trường thực hành và dữ liệu nằm trong container**, thực hiện:

```powershell
docker rm tx-concurrency-lab
```

Chỉ chạy `docker rm` khi đã dừng container và chắc chắn không cần dữ liệu thực hành nữa. Môi trường này không gắn Docker volume riêng, nên xóa container cũng làm mất dữ liệu của bài.

## 10. Từ môi trường này sang các thí nghiệm cô lập giao dịch

Sau khi hai kết nối hoạt động độc lập, có thể giữ nguyên cơ sở dữ liệu để tiếp tục học về đọc lặp lại (*repeatable read*), cập nhật đồng thời, thứ tự giành khóa, deadlock, cơ chế MVCC và các mức cô lập `READ COMMITTED`, `REPEATABLE READ`, `SERIALIZABLE`.

Mỗi lần thử nên ghi rõ bốn yếu tố: **lệnh thực hiện ở A, lệnh thực hiện ở B, thời điểm commit/rollback và kết quả từng phiên quan sát được**. Khi so sánh các mức cô lập, cần đặt mức cô lập trước câu lệnh truy vấn dữ liệu đầu tiên của giao dịch và làm mới dữ liệu đầu vào giữa các lượt. Một số hiện tượng theo chuẩn SQL không xuất hiện giống nhau trên mọi DBMS; ví dụ PostgreSQL xử lý `READ UNCOMMITTED` như `READ COMMITTED`, nên cần kiểm tra đặc tính của hệ quản trị trước khi diễn giải kết quả.

Điểm cốt lõi của môi trường là **cùng dữ liệu, hai kết nối thật sự tách biệt và chủ động kiểm soát ranh giới giao dịch**. Ba yếu tố đó giúp tái hiện và giải thích những vấn đề tương tranh một cách có thể kiểm chứng.

# Mất cập nhật (lost update) trong chuỗi đọc–tính toán–ghi

## 1. Bản chất của lỗi mất cập nhật

**Mất cập nhật** (*lost update*) là một bất thường đồng thời xảy ra khi hai giao dịch cùng dựa trên một giá trị đã đọc trước đó, tự tính toán kết quả mới, rồi ghi lại dữ liệu. Một giao dịch có thể ghi đè kết quả của giao dịch kia, khiến một phần thay đổi hợp lệ không còn xuất hiện trong trạng thái cuối.

Mẫu tương tác thường gặp:

```text
Đọc      -> Tính toán ở ứng dụng -> Ghi giá trị mới
  |                                  ^
  +-------- Giao dịch khác xen vào --+
```

Giả sử số dư tài khoản ban đầu là 1.000:

- Giao dịch A muốn cộng 200.
- Giao dịch B muốn trừ 100.
- Cả hai cùng đọc số dư 1.000.
- A tính ra 1.200; B tính ra 900.
- A ghi 1.200, sau đó B ghi 900.

Nếu cả hai thay đổi đều phải được áp dụng, kết quả đúng phải là:

\[
1000 + 200 - 100 = 1100
\]

Nhưng kết quả cuối lại là 900. Phép cộng 200 của A đã bị thao tác ghi sau của B làm mất. Đây là lost update.

Điểm quan trọng nằm ở **chuỗi đọc–tính toán–ghi**: ứng dụng đọc một giá trị, đưa giá trị đó ra ngoài cơ sở dữ liệu để tính kết quả tuyệt đối, rồi ghi kết quả đã tính trở lại. Trong khoảng thời gian ấy, một giao dịch khác có thể đã thay đổi dữ liệu. Câu lệnh ghi sau có thể hợp lệ về cú pháp nhưng dựa trên một đầu vào đã lỗi thời.

Lost update không chỉ xuất hiện với số dư. Nó có thể xảy ra khi nhiều người sửa số lượng tồn kho, số lượt xem, điểm tích lũy, hạn mức sử dụng, số ghế còn trống, trạng thái đơn hàng hoặc bất kỳ giá trị nào được ứng dụng đọc rồi ghi đè bằng một kết quả tính trước.

## 2. Mô hình dữ liệu minh họa

Ta dùng PostgreSQL để minh họa với một bảng tài khoản nhỏ. Dữ liệu ban đầu:

| account_id | owner_name | balance |
| ---: | --- | ---: |
| 101 | An | 1000 |
| 202 | Bình | 500 |

Hai phiên cơ sở dữ liệu độc lập sẽ cùng truy cập tài khoản 101. A đại diện cho một thao tác điều chỉnh tăng số dư 200; B đại diện cho một thao tác giảm số dư 100.

Tạo bảng trong cơ sở dữ liệu thực hành:

```sql
DROP TABLE IF EXISTS public.wallets;

CREATE TABLE public.wallets (
    account_id BIGINT PRIMARY KEY,
    owner_name TEXT NOT NULL,
    balance BIGINT NOT NULL CHECK (balance >= 0)
);

INSERT INTO public.wallets (account_id, owner_name, balance)
VALUES
    (101, 'An', 1000),
    (202, 'Binh', 500);
```

Các lệnh `DROP TABLE` chỉ dùng trong database thực hành vì chúng xóa bảng cùng tên và dữ liệu hiện có. Trong database đang sử dụng thật, không chạy đoạn khởi tạo này.

Một hàng có thể được đọc bởi nhiều giao dịch. Việc hai giao dịch cùng đọc không gây lost update ngay lập tức; vấn đề xuất hiện khi mỗi giao dịch lấy kết quả đọc làm cơ sở để ghi một giá trị mới không còn tương thích với cập nhật của giao dịch kia.

## 3. Tái hiện lost update theo từng bước

Để nhìn rõ lỗi, cần hai kết nối PostgreSQL riêng, gọi là **phiên A** và **phiên B**. Hai cửa sổ terminal có thể kết nối cùng một database nhưng phải là hai backend session khác nhau.

### 3.1. Chuỗi thao tác trong lịch thực thi

Giả sử ứng dụng không gửi phép cộng/trừ trực tiếp cho database. Thay vào đó, nó đọc số dư rồi tự tính kết quả ở tầng ứng dụng.

| Thứ tự | Phiên A | Phiên B |
| ---: | --- | --- |
| 1 | Đọc balance = 1000 | |
| 2 | | Đọc balance = 1000 |
| 3 | Tính 1000 + 200 = 1200 | |
| 4 | | Tính 1000 − 100 = 900 |
| 5 | Ghi balance = 1200 | |
| 6 | Commit | |
| 7 | | Ghi balance = 900 |
| 8 | | Commit |

Lịch đọc/ghi có thể biểu diễn:

```text
T_A:  r_A(X=1000) ---- tính 1200 ---- w_A(X=1200) ---- COMMIT
T_B:       r_B(X=1000) ---- tính 900 ---------------- w_B(X=900) ---- COMMIT
```

Cả hai giao dịch đều đọc cùng giá trị ban đầu. Giao dịch B ghi một giá trị tuyệt đối được tính từ 1.000, nên khi B ghi 900 sau A, kết quả 1.200 của A bị mất.

Đây là bất thường có quan hệ với cả đọc–ghi (RW) lẫn ghi–ghi (WW): B đọc X trước khi A ghi X; sau đó cả hai giao dịch ghi X. Chỉ xét thứ tự các lệnh SQL ghi không đủ để hiểu lỗi; phải xem cả **giá trị nào đã được đọc và dùng để tính kết quả**.

### 3.2. Thực hiện bằng hai phiên PostgreSQL

Trước tiên đặt dữ liệu về trạng thái ban đầu:

```sql
UPDATE public.wallets
SET balance = CASE account_id
    WHEN 101 THEN 1000
    WHEN 202 THEN 500
END
WHERE account_id IN (101, 202);
```

Mở hai cửa sổ `psql` riêng. Ở cả hai, xác nhận database dùng chung nhưng PID khác nhau:

```sql
SELECT current_database(), pg_backend_pid();
```

Nếu hai PID giống nhau, bạn đang thao tác cùng một kết nối và chưa tái hiện đúng hai giao dịch độc lập.

**Phiên A:**

```sql
BEGIN;

SELECT balance
FROM public.wallets
WHERE account_id = 101;
-- Trả về 1000.
```

A giữ nguyên giao dịch và chưa ghi. Chuyển sang **phiên B**:

```sql
BEGIN;

SELECT balance
FROM public.wallets
WHERE account_id = 101;
-- Cũng trả về 1000.
```

Bây giờ ở tầng ứng dụng, A tính 1.200; B tính 900. Để mô phỏng ứng dụng gửi giá trị đã tính, chạy ở **phiên A**:

```sql
UPDATE public.wallets
SET balance = 1200
WHERE account_id = 101;

COMMIT;
```

Sau đó ở **phiên B**, ghi giá trị B đã tính từ lần đọc cũ:

```sql
UPDATE public.wallets
SET balance = 900
WHERE account_id = 101;

COMMIT;
```

Kiểm tra kết quả:

```sql
SELECT account_id, balance
FROM public.wallets
WHERE account_id = 101;
```

Kết quả là 900, trong khi nếu cả hai điều chỉnh đều được áp dụng thì phải là 1.100. Phép cộng 200 của A đã bị ghi đè.

### 3.3. Vì sao hai lệnh UPDATE vẫn có thể thực hiện tuần tự mà lỗi vẫn xảy ra?

PostgreSQL có cơ chế khóa hàng để điều phối hai lệnh `UPDATE` trên cùng một hàng. Trong thí nghiệm trên, B chỉ ghi sau khi A đã commit, nên hai lệnh ghi không nhất thiết chạy đồng thời ở tầng lưu trữ. Tuy nhiên, **B đã đọc và tính kết quả từ trước**. Khóa khi thực hiện lệnh ghi không thể tự suy ra rằng giá trị 900 được ứng dụng tính từ số dư 1.000 đã cũ.

Vì vậy, cần tách hai vấn đề:

- Khóa ghi điều phối quyền thay đổi hàng trong thời điểm câu lệnh cập nhật chạy.
- Bảo vệ chuỗi đọc–tính toán–ghi đòi hỏi dữ liệu được kiểm tra hoặc tính lại trên trạng thái phù hợp, hoặc phải phát hiện rằng phiên bản mà ứng dụng đọc đã thay đổi.

Khóa hàng tại thời điểm ghi, tự nó, không đảm bảo rằng mọi quyết định đã thực hiện trước đó vẫn hợp lệ.

## 4. Lost update và các bất thường gần giống

### 4.1. Lost update khác với dirty read

**Dirty read** xảy ra khi một giao dịch đọc dữ liệu do giao dịch khác ghi nhưng chưa commit. Nếu giao dịch ghi sau đó rollback, giao dịch đọc đã sử dụng một giá trị chưa từng trở thành dữ liệu đã commit.

Lost update không đòi hỏi giao dịch nào đọc dữ liệu chưa commit. Trong ví dụ trên, cả A và B đều đọc giá trị đã commit là 1.000. Sau đó các thao tác ghi theo những kết quả được tính từ giá trị cũ làm mất một cập nhật.

### 4.2. Lost update khác với non-repeatable read

**Non-repeatable read** xảy ra khi một giao dịch đọc cùng một hàng hai lần và nhận hai giá trị khác nhau do một giao dịch khác commit cập nhật ở giữa.

Lost update có thể xảy ra ngay cả khi giao dịch chỉ đọc một lần. B đọc 1.000 một lần, tính 900, rồi ghi 900 sau khi A đã ghi 1.200. Vấn đề chính là B ghi bằng kết quả tính từ giá trị lỗi thời.

### 4.3. Lost update khác với write skew

**Write skew** thường liên quan đến các giao dịch đọc một tập dữ liệu hoặc điều kiện chung, sau đó ghi vào các hàng khác nhau. Mỗi giao dịch có thể không ghi đè cùng một hàng, nhưng kết hợp các kết quả có thể phá vỡ một bất biến liên hàng.

Lost update điển hình là hai giao dịch ghi cùng một đối tượng dữ liệu, trong đó kết quả ghi sau đã bỏ qua một thay đổi trước đó. Cả hai đều là bất thường đồng thời, nhưng giải pháp và cấu trúc phụ thuộc có thể khác nhau.

| Hiện tượng | Quan hệ điển hình | Vấn đề chính |
| --- | --- | --- |
| Dirty read | Ghi chưa commit → đọc | Đọc giá trị có thể bị rollback |
| Non-repeatable read | Đọc → giao dịch khác ghi/commit → đọc lại | Cùng giao dịch thấy các giá trị khác nhau |
| Lost update | Hai giao dịch đọc giá trị cũ rồi ghi kết quả tính toán | Một cập nhật bị ghi đè |
| Write skew | Đọc chung điều kiện, ghi các hàng khác nhau | Bất biến liên hàng bị phá vỡ |

## 5. Các cách phòng tránh lost update

Không có một giải pháp duy nhất phù hợp với mọi hệ thống. Lựa chọn phụ thuộc vào việc có cần tính toán phức tạp ở ứng dụng hay không, mức độ tranh chấp, khả năng retry và mức bảo vệ của DBMS.

### 5.1. Cách 1 — Đưa phép tính vào câu lệnh UPDATE nguyên tử

Với phép tăng/giảm đơn giản, cách thường gọn và an toàn là để database tính từ giá trị hàng hiện hành thay vì gửi một giá trị tuyệt đối đã tính ở ứng dụng.

Thay vì:

```text
balance = giá trị vừa đọc từ database + delta
UPDATE balance = giá trị tuyệt đối mới
```

hãy dùng:

```sql
UPDATE public.wallets
SET balance = balance + 200
WHERE account_id = 101;
```

Và giao dịch khác dùng:

```sql
UPDATE public.wallets
SET balance = balance - 100
WHERE account_id = 101
  AND balance >= 100;
```

PostgreSQL điều phối các lần cập nhật trên hàng. Ở `READ COMMITTED`, nếu câu lệnh UPDATE của một giao dịch phải đợi giao dịch khác cập nhật cùng hàng commit, PostgreSQL có thể tiếp tục kiểm tra hàng hiện tại và tính biểu thức `balance = balance + ...` dựa trên giá trị cập nhật mới. Vì thế, với thứ tự A cộng 200 rồi B trừ 100, kết quả sẽ là 1.100.

**Kiểm tra số hàng tác động:** lệnh trừ tiền có thể cập nhật 0 hàng vì tài khoản không tồn tại hoặc số dư không đủ. Ứng dụng phải kiểm tra số hàng trả về và coi trường hợp đó là kết quả nghiệp vụ thất bại. Nếu lệnh này là một phần của giao dịch nhiều bước, cần rollback khi điều kiện không thỏa.

Ví dụ đầy đủ:

```sql
BEGIN;

UPDATE public.wallets
SET balance = balance + 200
WHERE account_id = 101
RETURNING balance;

-- Chỉ commit nếu các thao tác nghiệp vụ khác cũng thành công.
COMMIT;
```

Đối với lệnh trừ tiền:

```sql
BEGIN;

UPDATE public.wallets
SET balance = balance - 100
WHERE account_id = 101
  AND balance >= 100
RETURNING balance;

-- Nếu UPDATE không trả về hàng, ứng dụng phải ROLLBACK.
COMMIT;
```

Đoạn SQL là mẫu cho đường đi thành công; ứng dụng cần kiểm tra kết quả trước khi quyết định commit.

**Khi nên dùng:** cập nhật bộ đếm, tăng/giảm tồn kho, điều chỉnh điểm hoặc số dư mà công thức có thể diễn đạt trực tiếp trong SQL.

**Giới hạn:** nếu ứng dụng phải đọc nhiều hàng, áp dụng logic phức tạp hoặc kiểm tra quy tắc liên quan tới nhiều đối tượng, một biểu thức UPDATE đơn lẻ có thể chưa đủ. Khi đó cần thêm khóa, ràng buộc, kiểm tra phiên bản hoặc isolation level thích hợp.

### 5.2. Cách 2 — Pessimistic locking với SELECT FOR UPDATE

Nếu ứng dụng cần đọc dữ liệu, tính toán rồi quyết định nhiều thao tác, có thể khóa hàng trước khi đọc để các giao dịch khác không thay đổi hàng ấy cho tới khi giao dịch hiện tại kết thúc.

Mẫu:

```sql
BEGIN;

SELECT account_id, balance
FROM public.wallets
WHERE account_id = 101
FOR UPDATE;

-- Ứng dụng đọc giá trị trong giao dịch hiện tại và tính toán.
-- Sau đó cập nhật dựa trên giá trị vừa khóa.
UPDATE public.wallets
SET balance = balance + 200
WHERE account_id = 101;

COMMIT;
```

`FOR UPDATE` lấy khóa hàng. Nếu giao dịch khác cố cập nhật hoặc lấy khóa xung đột trên cùng hàng, nó phải chờ giao dịch hiện tại commit hoặc rollback. Do đó, một giao dịch khác không thể chen vào giữa lần đọc đã khóa và cập nhật của giao dịch này theo cách tạo stale write trên cùng hàng.

#### Thử nghiệm hai phiên

Đặt lại balance tài khoản 101 về 1.000. Trong **phiên A**:

```sql
BEGIN;

SELECT balance
FROM public.wallets
WHERE account_id = 101
FOR UPDATE;
-- 1000. Giữ giao dịch mở.
```

Trong **phiên B**:

```sql
BEGIN;

UPDATE public.wallets
SET balance = balance - 100
WHERE account_id = 101
RETURNING balance;
-- Câu lệnh phải chờ khóa.
```

Quay lại **phiên A** và cập nhật:

```sql
UPDATE public.wallets
SET balance = balance + 200
WHERE account_id = 101;

COMMIT;
```

Sau khi A commit, B được tiếp tục. Ở `READ COMMITTED`, biểu thức `balance = balance - 100` áp dụng lên giá trị hiện hành, kết quả cuối dự kiến là 1.100. B có thể commit rồi truy vấn kiểm tra.

**Khi nên dùng:** quy trình gồm nhiều bước phải đọc và sau đó cập nhật cùng một nhóm hàng, hoặc nghiệp vụ cần giữ chỗ/giữ tài nguyên trước khi tiếp tục.

**Chi phí và lưu ý:** khóa có thể làm giao dịch khác phải chờ, giảm khả năng xử lý đồng thời. Giữ giao dịch quá lâu làm tăng thời gian chờ và nguy cơ deadlock. Nếu khóa nhiều hàng, nên lấy theo thứ tự ổn định (ví dụ tăng dần `account_id`) để giảm chu trình chờ.

### 5.3. Cách 3 — Optimistic locking với cột version

Khi tranh chấp không thường xuyên hoặc không muốn khóa trong lúc người dùng suy nghĩ, có thể dùng **optimistic locking**. Mỗi hàng có một số phiên bản; khi ứng dụng cập nhật, nó chỉ ghi nếu phiên bản vẫn giống lúc đã đọc.

Bổ sung cột `version`:

```sql
ALTER TABLE public.wallets
ADD COLUMN version BIGINT NOT NULL DEFAULT 0;
```

Ứng dụng đọc:

```sql
SELECT account_id, balance, version
FROM public.wallets
WHERE account_id = 101;
```

Giả sử nhận được `balance = 1000`, `version = 0`. Ứng dụng tính giá trị mới là 1.200. Khi ghi, nó dùng cả giá trị phiên bản mong đợi:

```sql
UPDATE public.wallets
SET balance = 1200,
    version = version + 1
WHERE account_id = 101
  AND version = 0
RETURNING balance, version;
```

Nếu một giao dịch khác đã sửa hàng và tăng version lên 1, lệnh trên tác động 0 hàng. Ứng dụng biết dữ liệu đã thay đổi và **không ghi đè** kết quả mới bằng giá trị tính từ phiên bản cũ.

Mô hình:

```text
Ứng dụng đọc (balance=1000, version=0)
                |
                v
Tính toán kết quả mới
                |
                v
UPDATE ... WHERE version=0
                |
        +-------+-------+
        |               |
   Một hàng trả về    0 hàng trả về
        |               |
        v               v
    Thành công       Xung đột phiên bản
                        |
                        v
                  Đọc lại và xử lý
```

**Khi nên dùng:** biểu mẫu chỉnh sửa, tài liệu cấu hình, thông tin hồ sơ hoặc thao tác mà người dùng có thể mở lâu trước khi bấm lưu.

**Lưu ý:** mọi đường ghi liên quan phải tuân thủ cơ chế version. Nếu một chương trình khác sửa dữ liệu mà không tăng version, optimistic locking không phát hiện được thay đổi đó. Phiên bản cũng cần được kiểm tra cùng điều kiện định danh, và ứng dụng cần thông báo xung đột hoặc xử lý retry phù hợp thay vì âm thầm ghi đè.

### 5.4. Cách 4 — Dùng mức cô lập phù hợp, đặc biệt SERIALIZABLE

Mức cô lập `SERIALIZABLE` hướng tới bảo đảm kết quả của những giao dịch được commit tương đương với một thứ tự thực thi tuần tự hợp lệ. Nếu PostgreSQL phát hiện một cấu trúc phụ thuộc có nguy cơ tạo lịch không tuần tự hóa được, nó có thể hủy một giao dịch với lỗi serialization.

Ví dụ:

```sql
BEGIN ISOLATION LEVEL SERIALIZABLE;

SELECT balance
FROM public.wallets
WHERE account_id = 101;

-- Ứng dụng kiểm tra, tính toán và cập nhật.
UPDATE public.wallets
SET balance = balance + 200
WHERE account_id = 101;

COMMIT;
```

Ở mức này, ứng dụng phải xử lý lỗi serialization (SQLSTATE `40001`) bằng cách **thử lại toàn bộ giao dịch từ đầu**, bao gồm các lần đọc và kiểm tra. Chỉ chạy lại câu lệnh cuối cùng là không đủ vì quyết định ban đầu có thể dựa trên ảnh chụp đã lỗi thời.

`SERIALIZABLE` không có nghĩa mọi giao dịch được xếp hàng chạy lần lượt một cách vật lý. PostgreSQL có thể cho chúng thực thi chồng lấn và phát hiện các phụ thuộc xung đột; một số giao dịch phải bị hủy để bảo đảm kết quả đã commit tương đương lịch tuần tự.

**Khi nên dùng:** bất biến nghiệp vụ trải trên nhiều hàng hoặc nhiều truy vấn, nơi việc khóa chính xác tất cả đối tượng khó hoặc dễ bỏ sót.

**Chi phí:** có thể phát sinh lỗi serialization và retry; khi tải cao, cần quan sát tỷ lệ retry, chọn điểm retry có giới hạn và bảo đảm các tác dụng phụ ngoài database không bị thực hiện lặp.

### 5.5. Chọn biện pháp theo tình huống

| Biện pháp | Cách bảo vệ | Phù hợp khi | Đánh đổi |
| --- | --- | --- | --- |
| UPDATE tính toán trong DB | Dựa vào giá trị hàng hiện hành | Phép cộng/trừ đơn giản trên một hàng | Không thay thế kiểm tra nghiệp vụ liên hàng |
| SELECT FOR UPDATE | Khóa trước khi đọc và tính toán | Cần đọc rồi cập nhật một nhóm hàng | Chờ khóa, giảm thông lượng |
| Optimistic version | Chỉ ghi nếu phiên bản không đổi | Tranh chấp thấp, tương tác người dùng dài | Cần xử lý xung đột và mọi đường ghi phải tăng version |
| SERIALIZABLE | Phát hiện lịch có nguy cơ không tuần tự hóa | Bất biến phức tạp qua nhiều dữ liệu | Có lỗi serialization, phải retry toàn giao dịch |

Không nên chọn mức cô lập cao hơn chỉ vì tên nghe an toàn hơn. Cần xuất phát từ **bất biến nghiệp vụ**, thao tác đọc/ghi thực tế, cách ứng dụng dùng dữ liệu và chi phí khi phải chờ hoặc retry.

## 6. Cách kiểm tra ứng dụng có nguy cơ lost update

Khi rà soát một luồng cập nhật, hãy tìm chuỗi sau:

```text
1. SELECT một giá trị.
2. Chuyển giá trị sang ứng dụng.
3. Ứng dụng tính một kết quả mới.
4. UPDATE ghi kết quả tuyệt đối vào hàng.
```

Một đoạn code minh họa:

```java
Account account = repository.findById(id);
long newBalance = account.getBalance() + adjustment;
repository.updateBalance(id, newBalance);
```

Nếu giữa `findById` và `updateBalance` có giao dịch khác sửa tài khoản, `newBalance` có thể không còn dựa trên số dư mới nhất. Mẫu này không chắc chắn gây lỗi trong mọi lần chạy; nó **có nguy cơ** nếu hai luồng có thể xen kẽ và update không kiểm tra phiên bản hay khóa.

Những dấu hiệu cần chú ý:

- Câu lệnh `UPDATE ... SET value = :calculatedValue` nhận giá trị tuyệt đối từ ứng dụng.
- Việc đọc và ghi nằm ở hai giao dịch độc lập.
- Một màn hình hoặc API giữ dữ liệu lâu rồi mới gửi lệnh lưu.
- Không có cột version, điều kiện theo giá trị đã đọc, khóa hoặc cơ chế cô lập phù hợp.
- Khi cập nhật 0 hàng, ứng dụng bỏ qua mà không báo xung đột.
- Retry chỉ gửi lại lệnh ghi cũ mà không đọc lại và tính toán lại.

Ngược lại, một lệnh `UPDATE SET value = value + delta` trực tiếp trong database có thể tránh dạng lost update này cho một hàng, nhưng vẫn cần kiểm tra ràng buộc, điều kiện và tương tác với các dữ liệu liên quan khác.

## 7. Lost update trong các miền nghiệp vụ khác

### 7.1. Hàng tồn kho

Tồn kho ban đầu là 50. Hai nhân viên cùng đọc 50. Nhân viên A bán 8 và ghi 42; nhân viên B bán 5 nhưng cũng tính từ 50 và ghi 45. Kết quả 45 làm mất thay đổi giảm 8.

Cách cập nhật an toàn cho số lượng bán:

```sql
UPDATE inventory
SET quantity = quantity - 5
WHERE product_id = 9001
  AND quantity >= 5
RETURNING quantity;
```

Nếu cập nhật không trả về hàng, không đủ tồn kho hoặc mã sản phẩm không hợp lệ. Hệ thống không được tiếp tục xác nhận đơn hàng như thể đã trừ kho thành công.

### 7.2. Bộ đếm lượt xem hoặc số lượng sự kiện

Giả sử bộ đếm ban đầu là 100, hai request đều đọc 100 và ghi 101. Kết quả có thể là 101 thay vì 102 nếu cả hai dùng phép gán tuyệt đối.

Dùng câu lệnh:

```sql
UPDATE article_stats
SET view_count = view_count + 1
WHERE article_id = 42;
```

Database sẽ điều phối các lần tăng trên cùng hàng. Khi số lượng sự kiện rất lớn, cần cân nhắc phân vùng bộ đếm, gom lô hoặc hệ thống chuyên xử lý sự kiện; các tối ưu ấy vẫn phải giữ được mục tiêu nhất quán đã chọn.

### 7.3. Chỉnh sửa hồ sơ từ nhiều tab

Một người mở cùng hồ sơ ở hai tab. Tab A đổi số điện thoại; tab B đổi địa chỉ. Nếu cả hai gửi toàn bộ bản ghi với các giá trị được đọc từ đầu phiên, tab lưu sau có thể ghi đè trường đã được tab kia cập nhật.

Một cột `version` hoặc cơ chế cập nhật từng trường phù hợp giúp phát hiện xung đột. Hệ thống có thể yêu cầu người dùng tải bản mới, so sánh các trường thay đổi hoặc hợp nhất có kiểm soát.

## 8. Câu hỏi thường gặp

### Nếu hai giao dịch chỉ đọc rồi một giao dịch ghi thì có lost update không?

Không nhất thiết. Lost update điển hình cần có các kết quả ghi cạnh tranh, trong đó một kết quả được tính từ dữ liệu đã cũ. Một giao dịch chỉ đọc có thể tạo quan hệ phụ thuộc RW, nhưng nếu nó không ghi lại giá trị đã cũ thì không có cập nhật nào bị mất theo nghĩa thông thường.

### PostgreSQL READ COMMITTED có luôn ngăn lost update không?

Không thể kết luận như vậy. PostgreSQL có điều phối các lần cập nhật cùng hàng, và trong một số tình huống `UPDATE` đánh giá lại điều kiện trên phiên bản hàng mới nhất. Nhưng nếu ứng dụng đã đọc một giá trị cũ, tự tính một con số tuyệt đối, rồi ghi con số đó sau, nó vẫn có thể ghi đè thay đổi của giao dịch khác. Mẫu đọc–tính toán–ghi trong ví dụ cần được bảo vệ ở cấp ứng dụng hoặc transaction.

### Có thể giải quyết bằng cách tăng timeout không?

Không. Timeout điều chỉnh thời gian chờ, không sửa cách ứng dụng tính giá trị từ dữ liệu cũ. Có thể kéo dài timeout nhưng kết quả ghi đè vẫn xảy ra nếu chuỗi đọc–tính toán–ghi không được bảo vệ.

### Chỉ cần khóa ở câu UPDATE là đủ không?

Không phải trong mọi tình huống. Database khóa hàng để thực hiện update, nhưng nếu giá trị tuyệt đối đã được tính trước từ một lần đọc cũ, khóa khi ghi không thể tự biết phép tính đó phải kết hợp với thay đổi trước. Hãy dùng biểu thức cập nhật trên giá trị hiện hành, khóa trước khi đọc/tính, hoặc kiểm tra version.

### Có nên retry mọi giao dịch thất bại không?

Không nên retry mù quáng. Chỉ retry các lỗi có thể thử lại, với số lần giới hạn và backoff phù hợp. Khi lỗi serialization, cần chạy lại toàn bộ giao dịch để lấy ảnh chụp và quyết định mới. Với xung đột optimistic version, có thể cần tải lại và yêu cầu người dùng xác nhận thay đổi. Những hành động bên ngoài transaction như gửi email hay gọi API cần cơ chế idempotency để tránh tác dụng phụ lặp.

## 9. Bài tập tự thực hành

### Bài 1 — Dự đoán kết quả

Balance ban đầu là 500. Hai phiên cùng đọc 500. A cộng 70; B trừ 40. Cả hai ghi kết quả tuyệt đối đã tính từ giá trị ban đầu. Nếu A ghi trước và B ghi sau, số dư cuối là bao nhiêu? Nếu cả hai điều chỉnh đều được áp dụng đúng, kết quả phải là bao nhiêu?

**Gợi ý:** phân biệt số dư cuối thực tế với kết quả cộng/trừ theo nghiệp vụ.

### Bài 2 — Sửa câu SQL

Đoạn mã ứng dụng đọc số lượng tồn kho rồi tính `newQuantity = oldQuantity - orderQuantity`, sau đó gọi:

```sql
UPDATE inventory
SET quantity = :newQuantity
WHERE product_id = :id;
```

Hãy viết cách cập nhật trực tiếp trong database có điều kiện tồn kho đủ, và nêu vì sao ứng dụng phải kiểm tra số hàng trả về.

### Bài 3 — Thiết kế optimistic locking

Một bảng `documents` có `document_id`, `content`. Hãy bổ sung cột `version`, viết câu SELECT lấy phiên bản, rồi viết UPDATE chỉ thành công nếu `version` vẫn bằng giá trị mà ứng dụng đã đọc.

### Bài 4 — So sánh hai giải pháp

Với luồng chuyển tiền cần khóa hai tài khoản rồi tính phí dựa trên số dư, hãy so sánh `SELECT FOR UPDATE` với `SERIALIZABLE`. Xem xét phạm vi khóa, khả năng retry, thời gian giao dịch và độ phức tạp logic.

## 10. Kết luận

Lost update phát sinh khi ứng dụng giữ một giá trị đã đọc, tính toán bên ngoài database rồi ghi kết quả tuyệt đối sau khi một giao dịch khác đã thay đổi cùng dữ liệu. Để ngăn lỗi, hãy chọn kỹ thuật phù hợp với cách thao tác: **cập nhật bằng biểu thức trên giá trị hiện hành** cho phép tăng/giảm đơn giản; **khóa hàng trước khi đọc** khi cần một chuỗi quyết định nhiều bước; **optimistic version** khi muốn phát hiện thay đổi từ phiên đọc cũ; và **SERIALIZABLE kèm retry toàn giao dịch** khi cần bảo vệ bất biến phức tạp.

Khi điều tra, hãy ghi lại đúng thứ tự đọc, tính toán, ghi và commit của từng phiên. Kết quả cuối chỉ cho biết một giao dịch thắng sau cùng; lịch thực thi mới giải thích vì sao thay đổi kia biến mất và nên đặt cơ chế bảo vệ ở đâu.

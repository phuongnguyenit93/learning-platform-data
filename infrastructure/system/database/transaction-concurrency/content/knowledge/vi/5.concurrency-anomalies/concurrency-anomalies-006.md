# Đọc lệch (read skew) và trạng thái tổng hợp không nhất quán

Một transaction có thể chỉ đọc dữ liệu đã commit mà vẫn tạo ra một kết quả sai về mặt nghiệp vụ. Điều này xảy ra khi các câu truy vấn trong cùng một thao tác tổng hợp nhìn thấy dữ liệu ở **những thời điểm khác nhau**. Mỗi giá trị riêng lẻ đều có thể hợp lệ, nhưng khi ghép chúng lại, tổ hợp kết quả chưa từng tồn tại như một trạng thái nhất quán của database.

Hiện tượng đó thường được gọi là **read skew** (đọc lệch). Nó đặc biệt dễ xuất hiện trong báo cáo đọc nhiều hàng, nhiều bảng hoặc nhiều câu SQL: tổng tài sản, số dư tài khoản, số lượng hàng tồn, báo cáo doanh thu, dashboard, kiểm tra hạn mức và các phép tính dựa trên nhiều dữ liệu có liên hệ với nhau.

Bài học này giải thích read skew bằng mô hình giao dịch chạy đồng thời, phân biệt nó với dirty read, non-repeatable read và phantom read, rồi trình bày các cách tạo ra một góc nhìn dữ liệu nhất quán: một câu lệnh với snapshot phù hợp, snapshot cấp transaction, khóa hoặc Serializable. Mục tiêu là chọn bảo đảm phù hợp với ý nghĩa của dữ liệu tổng hợp.

## 1. Trạng thái nhất quán và phép đọc tổng hợp

Giả sử một người có hai tài khoản ngân hàng A và B. Tổng số tiền của hai tài khoản là 1.000:

| Tài khoản | Số dư ban đầu |
|---|---:|
| A | 600 |
| B | 400 |
| **Tổng** | **1.000** |

Người dùng chuyển 100 từ A sang B. Nghiệp vụ được thực hiện trong một transaction:

```sql
BEGIN;

UPDATE account
SET balance = balance - 100
WHERE account_id = 'A';

UPDATE account
SET balance = balance + 100
WHERE account_id = 'B';

COMMIT;
```

Sau khi transaction hoàn tất, trạng thái mới là:

| Tài khoản | Số dư sau chuyển |
|---|---:|
| A | 500 |
| B | 500 |
| **Tổng** | **1.000** |

Tổng tiền là một **bất biến nghiệp vụ** (*business invariant*): thao tác chuyển tiền nội bộ không tạo thêm hoặc làm mất tiền. Trạng thái trước và sau giao dịch đều thỏa mãn tổng bằng 1.000.

Một báo cáo khác đọc hai tài khoản để tính tổng có thể chạy đồng thời với transaction chuyển tiền. Nếu báo cáo đọc A trước khi tiền bị trừ, nhưng đọc B sau khi tiền được cộng, nó thu được:

[
600 + 500 = 1.100
]

Nếu đọc A sau khi bị trừ, rồi đọc B trước khi được cộng, nó có thể thu được:

[
500 + 400 = 900
]

Hai kết quả đều sai đối với bất biến tổng tiền. Điều đáng chú ý là database không nhất thiết đã trả về dữ liệu chưa commit. Báo cáo có thể chỉ đọc các giá trị đã commit, nhưng mỗi câu lệnh đọc nhìn vào một thời điểm khác nhau.

**Read skew** là tình huống một transaction quan sát các phần dữ liệu có quan hệ với nhau ở những phiên bản/thời điểm khác nhau, dẫn đến một tổ hợp không nhất quán theo bất biến đang xét.

## 2. Lịch thực thi tạo ra read skew

Gọi transaction chuyển tiền là T1 và báo cáo tổng hợp là T2.

```text
Thời gian       T1: chuyển tiền                 T2: báo cáo
    |           BEGIN
    |           UPDATE A = 500
    |                                           BEGIN
    |                                           SELECT A -> 600
    |           UPDATE B = 500
    |           COMMIT
    |                                           SELECT B -> 500
    |                                           tính tổng = 1.100
    |                                           COMMIT
    v
```

T2 lấy A = 600 từ trạng thái trước khi T1 commit, rồi lấy B = 500 từ trạng thái sau khi T1 commit. T1 đã thay đổi hai hàng trong cùng một transaction và commit nguyên tử; không có trạng thái đã commit nào có A = 600, B = 500. Kết quả tổng 1.100 là một ảnh ghép từ hai thời điểm.

Đây không phải là dirty read: T2 không đọc giá trị A = 500 chưa commit của T1. T2 đọc A = 600 đã commit trước đó và B = 500 đã commit sau đó. Sai lệch đến từ **sự không đồng nhất giữa các lần đọc**, chứ không phải dữ liệu chưa commit.

### Trạng thái trung gian trong transaction không phải trạng thái đã commit

Trong lúc T1 đang thực thi, database có thể nội bộ nhìn thấy những thay đổi chưa commit, nhưng transaction khác không nhất thiết được phép đọc chúng. Ví dụ, sau khi T1 cập nhật A nhưng chưa cập nhật B, dữ liệu nội bộ trong transaction T1 có thể tạm thời là A = 500, B = 400. Đây là trạng thái đang xây dựng để cuối cùng commit thành A = 500, B = 500.

Một transaction khác sử dụng snapshot nhất quán có thể tiếp tục nhìn thấy phiên bản cũ A = 600, B = 400, hoặc nhìn thấy trạng thái mới A = 500, B = 500, tùy thời điểm snapshot được xác lập. Nó không nên ghép A cũ với B mới nếu cơ chế snapshot của database và mức cô lập bảo đảm hai hàng được đọc từ cùng một góc nhìn.

## 3. Phân biệt read skew với các hiện tượng đọc khác

Các khái niệm concurrency có liên hệ nhưng mô tả những cách dữ liệu bị quan sát khác nhau. Phân biệt chúng giúp chọn đúng mức cô lập và cách bảo vệ.

| Hiện tượng | Điều gì thay đổi trong góc nhìn? | Ví dụ |
|---|---|---|
| **Dirty read** | Đọc thay đổi chưa commit của transaction khác | T2 đọc A = 500 trong khi T1 chưa commit; T1 sau đó rollback. |
| **Non-repeatable read** | Cùng một hàng được đọc lại nhưng trả giá trị khác | T2 đọc A = 600; T1 commit A = 500; T2 đọc lại A = 500. |
| **Phantom read** | Tập hàng thỏa một điều kiện truy vấn thay đổi | T2 đếm booking có trạng thái ACTIVE được 3; T1 chèn booking thứ tư rồi commit; T2 đếm lại được 4. |
| **Read skew** | Các phần dữ liệu có liên quan được đọc từ những thời điểm/phiên bản không đồng nhất | Báo cáo đọc A cũ = 600 rồi B mới = 500, tổng thành 1.100. |

Một lần đọc không lặp lại có thể là một thành phần trong read skew, nhưng hai khái niệm không đồng nhất. Non-repeatable read tập trung vào cùng một hàng được đọc nhiều lần và nhận giá trị khác nhau. Read skew tập trung vào **mối quan hệ giữa nhiều giá trị**: mỗi giá trị có thể là dữ liệu đã commit, nhưng tổ hợp của chúng không thỏa trạng thái nhất quán mong muốn.

Phantom read cũng có thể làm một phép tính tổng hợp sai: một truy vấn theo điều kiện nhìn thấy tập hàng khác ở lần sau. Tuy nhiên, read skew có thể xảy ra ngay cả khi các truy vấn chỉ đọc hai hàng đã tồn tại, không có hàng mới nào được thêm hoặc bị xóa.

## 4. Thí nghiệm trên hai kết nối PostgreSQL

Các câu lệnh sau minh họa hành vi của PostgreSQL. Ta dùng hai kết nối độc lập, A và B, để quan sát cùng dữ liệu đồng thời. Ví dụ giả sử bảng tài khoản có khóa chính `account_id` và cột `balance`.

Chuẩn bị dữ liệu:

```sql
CREATE TABLE account (
    account_id TEXT PRIMARY KEY,
    balance NUMERIC(14, 2) NOT NULL CHECK (balance >= 0)
);

INSERT INTO account (account_id, balance)
VALUES ('A', 600.00), ('B', 400.00);
```

### Thí nghiệm A: READ COMMITTED có thể tạo read skew

PostgreSQL mặc định sử dụng `READ COMMITTED`. Mỗi câu lệnh đọc thông thường lấy snapshot tại thời điểm bắt đầu thực thi câu lệnh đó.

**Kết nối B — transaction báo cáo:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT balance
FROM account
WHERE account_id = 'A';
-- 600.00
```

Giữ transaction B mở.

**Kết nối A — transaction chuyển tiền:**

```sql
BEGIN;

UPDATE account
SET balance = balance - 100
WHERE account_id = 'A';

UPDATE account
SET balance = balance + 100
WHERE account_id = 'B';

COMMIT;
```

Quay lại **kết nối B**:

```sql
SELECT balance
FROM account
WHERE account_id = 'B';
-- 500.00

COMMIT;
```

Nếu ứng dụng cộng kết quả hai câu truy vấn, nó nhận 600 + 500 = 1.100. Hai câu SELECT của B đã dùng hai snapshot khác nhau: câu đầu trước khi A commit, câu sau sau khi A commit.

Hãy kiểm tra trạng thái sau cùng bằng một transaction mới hoặc câu truy vấn đơn:

```sql
SELECT
    SUM(balance) AS total_balance
FROM account;
-- 1000.00
```

Tổng hợp từ một snapshot nhất quán cho kết quả 1.000. Điều này cho thấy read skew không nhất thiết để lại dữ liệu sai trong database; nó có thể chỉ làm **phép đọc và quyết định của transaction báo cáo** sai.

### Thí nghiệm B: REPEATABLE READ giữ snapshot cấp transaction

Khởi tạo lại dữ liệu trước thí nghiệm:

```sql
UPDATE account SET balance = 600 WHERE account_id = 'A';
UPDATE account SET balance = 400 WHERE account_id = 'B';
```

**Kết nối B:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT balance
FROM account
WHERE account_id = 'A';
-- 600.00
```

Lần truy vấn đầu tiên xác lập snapshot của transaction B trong PostgreSQL.

**Kết nối A:**

```sql
BEGIN;

UPDATE account SET balance = balance - 100 WHERE account_id = 'A';
UPDATE account SET balance = balance + 100 WHERE account_id = 'B';

COMMIT;
```

Quay lại **kết nối B**:

```sql
SELECT balance
FROM account
WHERE account_id = 'B';
-- 400.00 trong snapshot cũ của B

SELECT SUM(balance) AS total_balance
FROM account;
-- 1000.00 trong snapshot của B

COMMIT;
```

B vẫn quan sát A = 600 và B = 400, nên tổng vẫn bằng 1.000. Transaction mới bắt đầu sau khi A commit có thể thấy A = 500 và B = 500.

Điểm cần nhớ: trong PostgreSQL, `REPEATABLE READ` sử dụng snapshot cấp transaction. Snapshot thông thường được xác lập khi câu lệnh đầu tiên cần snapshot thực thi, không phải nhất thiết ngay khoảnh khắc ứng dụng gửi `BEGIN`.

## 5. Snapshot theo câu lệnh và snapshot theo transaction

Khác biệt quan trọng nhất giữa hai mức cô lập thường dùng trong PostgreSQL là thời điểm chốt snapshot.

### Snapshot theo câu lệnh

Ở `READ COMMITTED`, mỗi câu lệnh có một snapshot mới đối với dữ liệu commit từ transaction khác. Vì vậy:

```text
T2: SELECT A     → trạng thái tại thời điểm t1
T1: chuyển tiền  → COMMIT tại thời điểm t2
T2: SELECT B     → trạng thái tại thời điểm t3
```

Nếu t1 < t2 < t3, T2 có thể ghép A của trạng thái trước và B của trạng thái sau. Đây là lý do một transaction nhiều câu SQL có thể quan sát dữ liệu thay đổi giữa các lần đọc.

### Snapshot theo transaction

Ở `REPEATABLE READ` của PostgreSQL, các câu truy vấn thông thường trong cùng transaction dùng cùng một snapshot đối với thay đổi từ transaction khác:

```text
T2: BEGIN
T2: SELECT A     → chốt snapshot S
T1: chuyển tiền  → COMMIT
T2: SELECT B     → vẫn dùng snapshot S
T2: COMMIT
```

T2 thấy toàn bộ dữ liệu theo snapshot S. Điều đó tạo ra một góc nhìn nhất quán về các thay đổi đã commit tại snapshot, dù transaction khác đã commit thêm sau đó.

**Snapshot nhất quán không có nghĩa dữ liệu luôn mới nhất.** Một báo cáo ở `REPEATABLE READ` có thể nhìn thấy một trạng thái cũ hơn database hiện tại. Nhưng nó có thể cộng các phần dữ liệu thuộc cùng một trạng thái, điều thường quan trọng hơn với một phép tính cần nhất quán.

Bảng so sánh trong PostgreSQL:

| Đặc điểm | READ COMMITTED | REPEATABLE READ |
|---|---|---|
| Snapshot của truy vấn đọc thông thường | Mỗi câu lệnh có snapshot riêng | Dùng snapshot cấp transaction |
| Đọc lại một hàng | Có thể thấy giá trị mới đã commit | Tiếp tục thấy phiên bản trong snapshot, trừ thay đổi do chính transaction thực hiện |
| Đọc nhiều hàng qua nhiều câu lệnh | Có thể ghép các thời điểm khác nhau | Các câu lệnh đọc thông thường cùng nhìn một snapshot |
| Read skew giữa các câu SELECT | Có thể xảy ra | Được ngăn với góc nhìn snapshot cấp transaction |
| Phantom read | Có thể xảy ra | PostgreSQL ngăn phantom trong snapshot |
| Write skew trên nhiều hàng | Có thể xảy ra | Vẫn có thể xảy ra |
| Mục tiêu chính | Mỗi câu lệnh đọc dữ liệu đã commit mới nhất tại snapshot của câu lệnh | Ảnh chụp ổn định trong transaction |

Các tên mức cô lập SQL có quy tắc tối thiểu trong chuẩn, nhưng cách triển khai cụ thể khác nhau giữa hệ quản trị. Bảng này mô tả PostgreSQL; không nên suy rộng mọi chi tiết triển khai của PostgreSQL thành quy tắc nội bộ của MySQL, SQL Server hoặc Oracle.

## 6. Một câu SELECT có thể đủ để tránh read skew giữa các lần đọc

Nếu mục tiêu chỉ là đọc tổng số dư, ta có thể gộp phép tính vào một câu SQL:

```sql
SELECT SUM(balance) AS total_balance
FROM account;
```

Trong PostgreSQL `READ COMMITTED`, một câu SELECT thông thường sử dụng một snapshot cho toàn câu lệnh. Các hàng được đọc bởi cùng câu lệnh sẽ được nhìn theo cùng snapshot. Vì vậy, khi transaction chuyển tiền commit nguyên tử, phép `SUM` sẽ quan sát trạng thái trước hoặc sau transaction (tùy snapshot), thay vì một hàng cũ và một hàng mới.

Tương tự, một báo cáo có thể dùng JOIN hoặc subquery để gom nhiều phép đọc có liên quan vào cùng câu lệnh:

```sql
SELECT
    customer.customer_id,
    customer.name,
    COALESCE(SUM(payment.amount), 0) AS paid_total,
    COALESCE(SUM(refund.amount), 0) AS refunded_total
FROM customer
LEFT JOIN payment
    ON payment.customer_id = customer.customer_id
LEFT JOIN refund
    ON refund.customer_id = customer.customer_id
GROUP BY customer.customer_id, customer.name;
```

Tuy vậy, cần xem xét tính đúng đắn của phép JOIN và phép tổng hợp. JOIN giữa hai bảng quan hệ một-nhiều có thể nhân bản hàng và làm tổng bị đếm lặp; giải quyết lỗi fan-out của phép nối là vấn đề mô hình truy vấn riêng, không phải vấn đề read skew. Một snapshot nhất quán không tự sửa công thức SQL sai.

### Khi một câu lệnh không đủ

Một báo cáo phức tạp có thể cần nhiều câu truy vấn khác nhau:

1. Đọc danh sách tài khoản và số dư.
2. Đọc giao dịch trong kỳ.
3. Đọc thông tin hạn mức.
4. Tổng hợp theo khách hàng hoặc đơn vị.
5. So sánh với số liệu kiểm toán.

Nếu những câu lệnh đó phải cùng mô tả một thời điểm dữ liệu, việc gộp từng phần thành nhiều câu lệnh ở `READ COMMITTED` vẫn có thể tạo báo cáo không đồng nhất. Có hai cách thường gặp:

- Đặt các truy vấn trong một transaction dùng snapshot cấp transaction phù hợp, ví dụ PostgreSQL `REPEATABLE READ`.
- Nếu quyết định dựa trên điều kiện liên quan nhiều hàng và phải bảo vệ tính đúng đắn khi ghi đồng thời, dùng cơ chế mạnh hơn như `SERIALIZABLE` hoặc giao thức khóa được thiết kế cho bất biến đó.

## 7. Một câu lệnh đọc nhất quán chưa đủ để bảo vệ mọi quyết định nghiệp vụ

Cần phân biệt **đọc một báo cáo nhất quán** với **thực hiện một quyết định ghi dựa trên snapshot**.

Giả sử hệ thống có quy tắc: tổng hạn mức của một nhóm tài khoản không được vượt 10.000. Hai transaction đồng thời cùng đọc tổng hiện tại là 9.000. Mỗi transaction muốn tăng hạn mức cho một tài khoản khác nhau thêm 700.

```text
T1: đọc tổng = 9000
T2: đọc tổng = 9000
T1: tăng hạn mức tài khoản A thêm 700
T2: tăng hạn mức tài khoản B thêm 700
T1: COMMIT
T2: COMMIT

Tổng mới = 10400  (vi phạm giới hạn 10000)
```

Hai transaction có thể đọc một snapshot nhất quán, nhưng mỗi transaction dựa vào snapshot đó để ghi một hàng khác nhau. Đây là dạng **write skew**: mỗi quyết định riêng lẻ có vẻ hợp lệ, nhưng tổ hợp hai lần commit phá vỡ bất biến chung.

Do đó:

- Snapshot theo transaction giúp transaction đọc dữ liệu không bị lệch giữa các câu truy vấn.
- Nó không tự ngăn mọi transaction khác cùng đưa ra quyết định dựa trên snapshot cũ rồi ghi các hàng khác nhau.
- Nếu cần bảo đảm bất biến khi đồng thời ghi, phải chọn cơ chế kiểm soát xung đột phù hợp: ràng buộc database, một hàng điều phối được khóa, khóa phạm vi thích hợp hoặc Serializable.

### Một cách thiết kế: hàng tổng hợp làm điểm đồng bộ

Nếu nghiệp vụ cho phép mô hình hóa hạn mức nhóm trong một hàng dùng chung, các transaction có thể khóa/cập nhật hàng đó trước khi quyết định:

```sql
BEGIN;

SELECT total_limit
FROM account_group
WHERE group_id = :group_id
FOR UPDATE;

-- Sau khi có khóa, kiểm tra total_limit + phần tăng mới.
-- Cập nhật account và total_limit trong cùng transaction.

COMMIT;
```

Transaction khác cần cập nhật cùng nhóm phải đợi khóa hàng điều phối. Khi lấy được khóa, nó đọc trạng thái đã cập nhật mới nhất theo logic transaction và kiểm tra lại điều kiện.

Đây là một giao thức ứng dụng: **mọi đường ghi liên quan đều phải tuân thủ cùng quy tắc khóa**. Nếu có đường code bỏ qua hàng điều phối, bảo đảm đồng bộ không còn đầy đủ.

### Một cách khác: SERIALIZABLE

Ở mức `SERIALIZABLE`, database bảo đảm các transaction commit thành công có hiệu ứng tương đương một thứ tự chạy tuần tự. Nếu hai transaction cùng đọc tổng 9.000 và ghi những hàng khác nhau làm vượt hạn mức, database có thể hủy một transaction do phát hiện xung đột serialization. Ứng dụng phải xử lý lỗi và chạy lại toàn bộ transaction nếu thao tác vẫn hợp lệ với dữ liệu mới.

Trong PostgreSQL, lỗi serialization thường có SQLSTATE `40001` (*serialization_failure*). Không chỉ chạy lại câu UPDATE cuối: lần thử mới phải đọc lại tổng, kiểm tra hạn mức và ra quyết định từ đầu.

## 8. Đọc dữ liệu nhất quán trong các loại báo cáo

Read skew có thể xuất hiện ngoài ví dụ tài khoản. Một số tình huống thực tế:

### 8.1. Báo cáo tồn kho và đơn hàng

Một nghiệp vụ xuất kho có thể giảm tồn kho và thay đổi trạng thái đơn hàng trong cùng transaction. Báo cáo đọc số lượng tồn ở truy vấn đầu và số đơn đã xuất ở truy vấn sau tại hai snapshot khác nhau có thể cho thấy tồn kho và đơn hàng không khớp.

Nếu mục tiêu là hiển thị một snapshot báo cáo nhất quán, hãy đọc cả hai tập dữ liệu từ cùng một snapshot. Nếu mục tiêu là quyết định có được phép xuất hàng tiếp hay không, cần thêm cơ chế khóa/cập nhật nguyên tử và ràng buộc đảm bảo tồn kho không âm.

### 8.2. Dashboard doanh thu

Một dashboard có thể tính:

- Doanh thu đã thanh toán.
- Số đơn hàng hoàn tất.
- Số tiền hoàn trả.
- Doanh thu thuần.

Nếu mỗi chỉ số chạy ở một câu truy vấn riêng dưới `READ COMMITTED`, một đơn hàng có thể được chuyển trạng thái hoặc ghi nhận hoàn tiền giữa các truy vấn. Dashboard có nguy cơ ghép số đơn ở trạng thái cũ với tiền hoàn trả ở trạng thái mới.

Giải pháp phụ thuộc kỳ vọng cập nhật:

- Dashboard chấp nhận dữ liệu xấp xỉ/được cập nhật liên tục: có thể chấp nhận các snapshot riêng, nhưng phải hiểu số liệu không đại diện một mốc thời gian chung.
- Báo cáo tài chính/đối soát cần một thời điểm nhất quán: sử dụng snapshot cấp transaction hoặc một phiên bản dữ liệu báo cáo đã được chốt.
- Cần quyết định thay đổi trạng thái ngay trong transaction: dùng cơ chế kiểm soát ghi và bất biến phù hợp.

### 8.3. Báo cáo nhiều dịch vụ hoặc nhiều database

Nếu dữ liệu được đọc từ nhiều database độc lập hoặc từ nhiều service, transaction SQL ở một database không thể tự tạo một snapshot nguyên tử bao trùm tất cả nguồn. Ngay cả khi từng nguồn cung cấp snapshot nhất quán riêng, hai snapshot đó có thể chốt ở thời điểm khác nhau.

Trong kiến trúc phân tán, cần xác định rõ ý nghĩa của báo cáo: dữ liệu eventual consistency, phiên bản/số thứ tự đồng bộ, watermark, thời điểm chốt, hoặc một cơ chế điều phối snapshot chuyên biệt. Không nên hứa “toàn bộ dashboard là cùng một thời điểm” khi hệ thống không có cơ chế đảm bảo điều đó.

## 9. Các chiến lược xử lý và đánh đổi

| Chiến lược | Phù hợp khi | Chi phí / giới hạn |
|---|---|---|
| Gộp phép đọc thành một câu SQL | Các phần dữ liệu có thể lấy trong một truy vấn và cần cùng snapshot câu lệnh | Truy vấn có thể phức tạp; phải kiểm tra fan-out, hiệu năng và semantics |
| Snapshot cấp transaction | Báo cáo nhiều câu SQL phải nhìn cùng một trạng thái | Transaction dài giữ snapshot lâu; có thể trì hoãn dọn phiên bản cũ và tăng tài nguyên |
| Khóa bi quan | Cần phối hợp đọc rồi ghi và có điểm khóa rõ ràng | Chờ khóa, giảm concurrency, nguy cơ deadlock; mọi đường ghi phải cùng tuân thủ giao thức |
| Cập nhật nguyên tử/ràng buộc | Bất biến có thể biểu diễn bằng một UPDATE hoặc constraint | Không giải quyết mọi quy tắc trải trên nhiều hàng |
| SERIALIZABLE | Bất biến phức tạp phụ thuộc nhiều hàng/điều kiện và cần tương đương tuần tự | Có thể hủy transaction khi có xung đột; cần retry toàn bộ và đo chi phí |
| Snapshot/reporting dataset đã chốt | Báo cáo lớn, cần mốc dữ liệu ổn định và có thể chạy offline | Cần quản lý thời điểm tạo, độ mới và quy trình cập nhật snapshot |

### Giữ transaction đọc ngắn

Một transaction báo cáo dài ở snapshot cấp transaction có thể nhìn trạng thái cũ trong thời gian dài. Với MVCC, database có thể phải giữ lại các phiên bản cũ mà snapshot đó còn cần. Ở PostgreSQL, transaction mở lâu có thể làm tăng áp lực vacuum và dung lượng lưu trữ.

Vì vậy:

- Chỉ mở transaction ngay trước nhóm truy vấn cần snapshot.
- Không giữ transaction trong lúc chờ người dùng, gọi API bên ngoài hoặc xử lý file lâu.
- Đọc kết quả cần thiết, kết thúc transaction rồi mới thực hiện công việc ngoài database.
- Theo dõi transaction kéo dài và trạng thái idle-in-transaction.

## 10. JDBC: đọc nhiều phần trong một snapshot

JDBC cho phép đặt nhiều truy vấn trong cùng transaction bằng `setAutoCommit(false)`. Ví dụ đọc số dư hai tài khoản trong một snapshot PostgreSQL `REPEATABLE READ`:

```java
public BigDecimal readTotalBalance(
        DataSource dataSource,
        String firstAccount,
        String secondAccount) throws SQLException {

    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);
        connection.setTransactionIsolation(
                Connection.TRANSACTION_REPEATABLE_READ);

        try {
            BigDecimal first = readBalance(connection, firstAccount);
            BigDecimal second = readBalance(connection, secondAccount);

            BigDecimal total = first.add(second);

            connection.commit();
            return total;
        } catch (SQLException | RuntimeException ex) {
            try {
                connection.rollback();
            } catch (SQLException rollbackFailure) {
                ex.addSuppressed(rollbackFailure);
            }
            throw ex;
        }
    }
}

private BigDecimal readBalance(Connection connection, String accountId)
        throws SQLException {

    String sql = """
        SELECT balance
        FROM account
        WHERE account_id = ?
        """;

    try (PreparedStatement statement = connection.prepareStatement(sql)) {
        statement.setString(1, accountId);

        try (ResultSet result = statement.executeQuery()) {
            if (!result.next()) {
                throw new SQLException("Account not found: " + accountId);
            }
            return result.getBigDecimal("balance");
        }
    }
}
```

Trong ví dụ:

1. Lấy một connection và tắt autocommit.
2. Chọn isolation level trước các câu truy vấn.
3. Thực hiện hai câu đọc trên cùng connection và cùng transaction.
4. Commit/đóng transaction sau khi đọc xong; rollback khi gặp lỗi có thể xử lý.

Cần lưu ý rằng `Connection.TRANSACTION_REPEATABLE_READ` được ánh xạ theo khả năng của driver/database. Mức cô lập và semantics snapshot không giống hệt nhau ở mọi hệ quản trị. Cần xác nhận database đang dùng thực sự cung cấp bảo đảm mà nghiệp vụ yêu cầu.

Nếu chỉ cần tổng số dư, một câu truy vấn thường đơn giản và ít rủi ro hơn:

```sql
SELECT COALESCE(SUM(balance), 0) AS total_balance
FROM account;
```

Đừng mở transaction nhiều câu lệnh nếu một truy vấn có thể trả kết quả cần thiết dưới cùng snapshot câu lệnh.

## 11. Spring: phạm vi @Transactional cho báo cáo

Với Spring, có thể đặt nhiều lần đọc trong một transaction:

```java
@Service
public class AccountReportService {

    private final AccountRepository accountRepository;

    public AccountReportService(AccountRepository accountRepository) {
        this.accountRepository = accountRepository;
    }

    @Transactional(
        readOnly = true,
        isolation = Isolation.REPEATABLE_READ
    )
    public AccountSummary loadSummary(String firstId, String secondId) {
        BigDecimal first = accountRepository.findBalance(firstId)
            .orElseThrow();

        BigDecimal second = accountRepository.findBalance(secondId)
            .orElseThrow();

        return new AccountSummary(first, second, first.add(second));
    }
}
```

Các điểm cần phân biệt:

- `readOnly = true` thể hiện ý định transaction chỉ đọc và có thể giúp framework/driver tối ưu. Nó **không tự động có nghĩa** snapshot nhất quán cấp transaction ở mọi database.
- `isolation = Isolation.REPEATABLE_READ` yêu cầu transaction manager thiết lập mức cô lập tương ứng khi bắt đầu transaction vật lý mới.
- Nếu phương thức tham gia một transaction đã tồn tại, isolation thực tế có thể bị quyết định bởi transaction bên ngoài. Cần kiểm soát ranh giới transaction thay vì chỉ nhìn annotation ở một phương thức con.
- Cấu hình connection pool, transaction manager và database phải nhất quán; thay đổi isolation trên connection cần được reset đúng khi trả connection về pool.

Với báo cáo quan trọng, nên xác minh isolation của transaction thực tế bằng cấu hình và hành vi database, không chỉ dựa vào annotation trên source code.

## 12. Tính nhất quán của báo cáo và thời điểm chụp dữ liệu

Có ba câu hỏi khác nhau khi đọc số liệu:

1. **Dữ liệu có nhất quán không?** Các phần được tổng hợp có cùng thuộc về một trạng thái hợp lệ theo bất biến nghiệp vụ không?
2. **Dữ liệu mới đến đâu?** Snapshot được chốt trước hay sau transaction mới nhất?
3. **Báo cáo có tái lập được không?** Chạy lại cùng một báo cáo có thể lấy đúng phiên bản dữ liệu đã dùng lần trước không?

Snapshot cấp transaction chủ yếu giải quyết câu hỏi thứ nhất trong phạm vi database và transaction đó. Nó không tự đảm bảo snapshot luôn mới nhất, và cũng không tự lưu lại snapshot để có thể tái lập một báo cáo sau nhiều ngày.

Với báo cáo kiểm toán hoặc báo cáo tài chính có yêu cầu tái lập, có thể cần lưu thêm thời điểm chốt, phiên bản dữ liệu, batch ID hoặc bản snapshot đã vật hóa. Thông tin đó cho phép người vận hành biết báo cáo phản ánh dữ liệu nào thay vì cố tái tạo từ database đang tiếp tục thay đổi.

## 13. Cách suy luận một tình huống read skew

Khi gặp báo cáo hoặc thao tác đọc nhiều phần dữ liệu, hãy đi theo trình tự:

1. **Viết bất biến:** Ví dụ A + B phải bằng 1.000 sau chuyển khoản; tổng số booking giao nhau không được vượt giới hạn.
2. **Liệt kê nguồn dữ liệu:** Những hàng, bảng, tập hàng và quan hệ nào góp phần vào kết quả?
3. **Vẽ lịch thực thi:** Câu SELECT nào chạy trước, transaction nào commit giữa các lần đọc?
4. **Xác định snapshot:** Từng câu lệnh dùng snapshot riêng hay cả transaction dùng một snapshot? Truy vấn có chạy trên replica hoặc nhiều nguồn không?
5. **Phân biệt đọc với quyết định ghi:** Chỉ cần một báo cáo nhất quán, hay kết quả đọc được dùng để quyết định một transaction khác ghi dữ liệu?
6. **Chọn bảo đảm:** Một câu SELECT, snapshot cấp transaction, khóa, cập nhật nguyên tử, constraint hoặc Serializable.
7. **Tính đến vận hành:** Transaction dài bao lâu, có retry không, có tác động ngoài database không và báo cáo cần mới tới mức nào?

## 14. Bài tập tự suy luận

### Bài 1: Tổng hai tài khoản

Hai tài khoản A = 700 và B = 300. T1 chuyển 200 từ A sang B. T2 đọc A trước khi T1 commit và đọc B sau khi T1 commit.

- T2 có dirty read không?
- T2 tính được tổng bao nhiêu?
- Vì sao tổng này chưa từng là trạng thái commit của hai tài khoản?
- Snapshot cấp transaction sẽ thay đổi kết quả như thế nào?

### Bài 2: Nhiều câu truy vấn cho dashboard

Một dashboard chạy ba câu SELECT: doanh thu đơn hàng, tổng tiền refund và số đơn đã hoàn tất. Một transaction khác cập nhật trạng thái đơn và ghi refund trong cùng transaction.

- Tại READ COMMITTED, ba truy vấn có thể phản ánh ba snapshot khác nhau không?
- Nếu chuyển sang REPEATABLE READ của PostgreSQL, báo cáo thay đổi thế nào?
- Có thể gom các phép tính thành một câu truy vấn không? Cần kiểm tra điều gì về phép JOIN?

### Bài 3: Snapshot nhất quán nhưng quyết định vẫn sai

Hai transaction cùng đọc tổng hạn mức là 9.000, rồi mỗi transaction tăng một hàng khác nhau thêm 700. Cả hai đều dùng REPEATABLE READ.

- Vì sao snapshot nhất quán không ngăn hai transaction commit?
- Đây có phải read skew không hay là write skew?
- Dùng hàng điều phối có khóa hoặc Serializable để bảo vệ bất biến tổng hạn mức như thế nào?

### Bài 4: Báo cáo từ hai database

Dữ liệu tài khoản nằm ở service A; thông tin giao dịch nằm ở service B. Mỗi service cung cấp snapshot nhất quán riêng. Vì sao tổng hợp kết quả từ hai snapshot đó vẫn có thể không đại diện cùng một thời điểm? Hãy đề xuất một watermark hoặc mốc chốt dữ liệu mà báo cáo có thể công bố.

### Bài 5: Tối ưu truy vấn

Một báo cáo đọc 20 hàng bằng 20 câu SELECT riêng trong một transaction READ COMMITTED. Hãy giải thích cách read skew có thể ảnh hưởng kết quả, rồi so sánh phương án gộp thành một câu SELECT với phương án dùng REPEATABLE READ. Nêu một đánh đổi vận hành của transaction snapshot dài.

## Kết luận

Read skew xảy ra khi một thao tác tổng hợp ghép dữ liệu từ các snapshot hoặc thời điểm khác nhau. Từng giá trị đọc có thể đã commit và hợp lệ riêng lẻ, nhưng tổ hợp của chúng có thể vi phạm bất biến nghiệp vụ hoặc không đại diện cho bất kỳ trạng thái nhất quán nào của database.

Ở PostgreSQL, READ COMMITTED tạo snapshot theo câu lệnh, nên nhiều câu SELECT trong một transaction có thể thấy các commit khác nhau. REPEATABLE READ cung cấp snapshot cấp transaction và giúp báo cáo nhiều câu lệnh nhìn cùng một trạng thái. Một câu SELECT tổng hợp cũng thường đủ nếu tất cả dữ liệu cần thiết có thể đọc trong cùng câu lệnh.

Khi dữ liệu đọc được dùng để ra quyết định ghi, snapshot nhất quán chưa chắc bảo vệ được bất biến trải qua nhiều hàng. Khi đó cần xem xét constraint, cập nhật nguyên tử, khóa điều phối hoặc SERIALIZABLE với retry toàn transaction. Chọn đúng cơ chế phải dựa trên điều hệ thống cần bảo đảm: **một báo cáo nhất quán, một quyết định ghi an toàn hay một snapshot có thể tái lập**.

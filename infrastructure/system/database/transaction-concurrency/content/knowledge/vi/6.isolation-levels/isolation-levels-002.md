# READ UNCOMMITTED và vấn đề dữ liệu chưa xác nhận

## 1. READ UNCOMMITTED là gì?

**READ UNCOMMITTED** là mức cô lập giao dịch thấp nhất trong mô hình bốn mức cô lập thường được giới thiệu theo SQL. Ở mức này, một giao dịch có thể đọc thay đổi mà giao dịch khác đã ghi nhưng **chưa commit**. Giá trị được đọc có thể bị giao dịch ghi hủy bỏ bằng `ROLLBACK`, vì vậy nó chưa phải trạng thái dữ liệu được xác nhận.

Tình huống một giao dịch đọc thay đổi chưa commit của giao dịch khác được gọi là **dirty read** (*đọc bẩn* hoặc đọc dữ liệu chưa xác nhận).

Giả sử tài khoản A có số dư 1.000:

- Giao dịch T1 trừ 300, số dư tạm thời trở thành 700, nhưng chưa commit.
- Giao dịch T2 đọc số dư 700 và dùng nó để quyết định một thao tác khác.
- Sau đó T1 phát hiện lỗi và rollback, số dư trở lại 1.000.
- T2 đã dựa vào giá trị 700, một giá trị không bao giờ trở thành trạng thái đã commit.

READ UNCOMMITTED cho phép quan sát trạng thái trung gian này trong hệ quản trị có hỗ trợ dirty read. Vì vậy, nó có thể làm ứng dụng đưa ra quyết định dựa trên dữ liệu sẽ biến mất.

Cần hiểu đúng hai khái niệm:

- **Chưa commit** không đồng nghĩa với dữ liệu bị ghi sai. Đây có thể là một phần hợp lệ của giao dịch đang chạy.
- **Được phép đọc** một giá trị chưa commit không đồng nghĩa với giá trị đó sẽ được giữ lại. Giao dịch ghi vẫn có thể rollback.

Mức cô lập này có thể giảm một số chờ đợi đọc/ghi ở những hệ quản trị dùng khóa, nhưng đánh đổi bằng việc ứng dụng phải chấp nhận dữ liệu tạm thời, khó dự đoán và có thể không phục hồi theo cách mong đợi.

## 2. Tái hiện dirty read bằng lịch giao dịch

Dùng bảng tài khoản:

| account_id | owner_name | balance |
| ---: | --- | ---: |
| 101 | An | 1000 |
| 202 | Bình | 500 |

Ta mở hai giao dịch độc lập, gọi là T1 và T2. Xét trình tự:

```text
Thời điểm     T1                                      T2
----------------------------------------------------------------
t1            BEGIN
t2            UPDATE tài khoản 101: balance = 700
t3                                                    BEGIN
t4                                                    SELECT balance -> 700
t5            phát hiện lỗi
t6            ROLLBACK
t7                                                    tiếp tục dùng số 700
```

Ở thời điểm t4, T2 đã nhìn thấy thay đổi của T1 dù T1 chưa commit. Tại t6, T1 hủy thay đổi và số dư chính thức trở lại 1.000. T2 có thể tiếp tục tính toán từ 700 và đưa ra quyết định sai.

Một lịch rút gọn:

```text
T1:  w1(X = 700) ------------------ a1
T2:               r2(X = 700) -------- commit hoặc tiếp tục
```

Trong ký hiệu này:

- `w1(X)`: T1 ghi giá trị mới vào X.
- `r2(X)`: T2 đọc X.
- `a1`: T1 abort/rollback.

Đây là quan hệ **ghi–đọc (WR)** giữa hai giao dịch, nhưng vấn đề đặc biệt nằm ở việc T2 đọc phiên bản chưa commit. Không phải mọi quan hệ WR đều là dirty read: nếu T1 commit trước khi T2 đọc, T2 đang đọc dữ liệu đã xác nhận và đó là trường hợp bình thường.

## 3. Ví dụ nghiệp vụ: số dư tạm thời và quyết định thanh toán

Một hệ thống thanh toán có thể kiểm tra số dư trước khi cho phép đặt lệnh. Giả sử:

- Số dư thực sự đã commit là 1.000.
- T1 chuyển 600 ra khỏi tài khoản và tạm ghi số dư 400.
- T2 đọc 400 rồi từ chối một khoản thanh toán 500.
- T1 rollback vì giao dịch chuyển tiền thất bại ở bước tiếp theo.

Sau rollback, số dư vẫn là 1.000. Quyết định từ chối thanh toán của T2 đã được đưa ra dựa trên dữ liệu chưa xác nhận.

Dirty read có thể dẫn đến cả kết quả dương tính giả và âm tính giả trong nghiệp vụ:

- Ứng dụng tưởng số dư đã tăng do giao dịch nạp tiền chưa commit và cho phép chi tiêu.
- Ứng dụng tưởng số dư đã giảm do giao dịch rút tiền chưa commit và từ chối một giao dịch hợp lệ.
- Báo cáo thấy số đơn hàng hoặc lượng tồn kho đã thay đổi từ giao dịch sẽ rollback.
- Một quy trình tiếp theo ghi dữ liệu dựa trên trạng thái tạm thời và tạo ra tác động khó hoàn tác.

Vấn đề không chỉ là “đọc nhầm một con số”. Giá trị chưa commit có thể trở thành đầu vào cho nhiều hành động: tính phí, cấp hạn mức, gửi thông báo, đặt chỗ, ghi nhận kết quả hay gọi một dịch vụ bên ngoài.

## 4. Thực hành dirty read trên DBMS có hỗ trợ

Hành vi cụ thể phụ thuộc hệ quản trị. Một số hệ quản trị có thể thực thi READ UNCOMMITTED bằng cơ chế cho phép đọc thay đổi chưa commit; hệ quản trị khác có thể không hỗ trợ dirty read thật sự hoặc ánh xạ mức này sang mức cô lập cao hơn.

### 4.1. Chuẩn bị bảng thực hành

Ví dụ SQL dưới đây dùng cú pháp phổ biến. Trong database thử nghiệm:

```sql
DROP TABLE IF EXISTS lab_accounts;

CREATE TABLE lab_accounts (
    account_id INTEGER PRIMARY KEY,
    owner_name VARCHAR(50) NOT NULL,
    balance INTEGER NOT NULL
);

INSERT INTO lab_accounts (account_id, owner_name, balance)
VALUES
    (101, 'An', 1000),
    (202, 'Binh', 500);
```

Không chạy `DROP TABLE` trên cơ sở dữ liệu chứa dữ liệu cần giữ. Nên dùng một database riêng cho bài học.

Mở hai cửa sổ kết nối riêng. Để kiểm tra, chạy trong mỗi cửa sổ:

```sql
SELECT CURRENT_DATABASE();
```

Tên cơ sở dữ liệu phải giống nhau. Với hệ quản trị có hàm nhận diện session, hãy kiểm tra hai kết nối có session/connection ID khác nhau.

### 4.2. Trình tự thử

Chỉ sử dụng quy trình này trên DBMS có thực sự cho phép READ UNCOMMITTED quan sát dữ liệu chưa commit. Trước tiên, đặt T2 ở mức cô lập:

```sql
SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;
BEGIN;
```

Cú pháp đặt mức và thứ tự câu lệnh có thể khác theo DBMS. Một số hệ yêu cầu đặt isolation level trước `BEGIN`; hãy dùng cú pháp đúng với hệ quản trị đang thực hành.

Tại **phiên T1**:

```sql
BEGIN;

UPDATE lab_accounts
SET balance = 700
WHERE account_id = 101;

-- Chưa COMMIT. Giữ giao dịch mở.
```

Chuyển sang **phiên T2**:

```sql
SELECT balance
FROM lab_accounts
WHERE account_id = 101;
```

Nếu hệ quản trị thực sự hỗ trợ dirty read ở READ UNCOMMITTED, T2 có thể đọc được `700`. Giữ T2 mở để quan sát tình huống. Quay lại T1:

```sql
ROLLBACK;
```

Ở T2, đọc lại:

```sql
SELECT balance
FROM lab_accounts
WHERE account_id = 101;
```

Giá trị đã commit phải là `1000`. Nếu lần đọc đầu trả về 700 nhưng lần sau là 1000, bạn đã quan sát được dữ liệu chưa xác nhận bị hủy.

Nếu T2 phải chờ hoặc đọc 1000 thay vì 700, không nên lập tức kết luận rằng thí nghiệm sai. DBMS có thể ánh xạ READ UNCOMMITTED sang mức mạnh hơn, dùng MVCC không cho phép đọc phiên bản chưa commit, hoặc áp dụng cơ chế khóa khác. Ghi lại tên DBMS, engine lưu trữ, isolation level thực tế và cấu hình trước khi giải thích kết quả.

## 5. PostgreSQL: READ UNCOMMITTED không tạo dirty read

PostgreSQL có điểm đặc biệt quan trọng: dù chấp nhận câu lệnh đặt mức cô lập `READ UNCOMMITTED`, hệ quản trị **xử lý nó như READ COMMITTED**. Vì vậy, truy vấn thông thường không thể đọc thay đổi chưa commit của một giao dịch khác.

Trong PostgreSQL, có thể kiểm tra:

```sql
BEGIN ISOLATION LEVEL READ UNCOMMITTED;

SHOW transaction_isolation;

COMMIT;
```

Giá trị hiển thị của PostgreSQL vẫn là:

```text
read uncommitted
```

Tên mức được báo lại có thể là `read uncommitted`, nhưng hành vi về dirty read giống READ COMMITTED: thay đổi chưa commit của giao dịch khác không được đọc. PostgreSQL dùng MVCC để cung cấp snapshot của dữ liệu đã commit cho truy vấn thông thường.

### 5.1. Minh họa bằng hai phiên PostgreSQL

Trong T1:

```sql
BEGIN;

UPDATE lab_accounts
SET balance = 700
WHERE account_id = 101;

-- Chưa commit.
```

Trong T2:

```sql
BEGIN ISOLATION LEVEL READ UNCOMMITTED;

SELECT balance
FROM lab_accounts
WHERE account_id = 101;
```

T2 đọc `1000`, không đọc `700`. Khi T1 rollback:

```sql
-- T1
ROLLBACK;
```

T2 vẫn đọc `1000`. Đó là hành vi READ COMMITTED của PostgreSQL, mặc dù T2 đã yêu cầu READ UNCOMMITTED.

Điều này thể hiện một nguyên tắc khi học isolation level: **không được suy luận hành vi của DBMS chỉ từ tên mức cô lập**. Cần tra cứu và kiểm tra triển khai cụ thể. Hai hệ quản trị cùng nhận tên READ UNCOMMITTED có thể có cách thực thi và cơ chế lưu trữ khác nhau.

## 6. READ UNCOMMITTED trong bốn mức cô lập

Bốn mức cô lập thường được trình bày theo thứ tự từ thấp đến cao:

1. READ UNCOMMITTED
2. READ COMMITTED
3. REPEATABLE READ
4. SERIALIZABLE

Mức cô lập mô tả các hiện tượng mà giao dịch có thể quan sát khi chạy đồng thời. Các hiện tượng kinh điển gồm dirty read, non-repeatable read và phantom read. Bảng dưới đây là cách đối chiếu khái niệm tổng quát; triển khai thực tế có thể cung cấp bảo đảm mạnh hơn chuẩn tối thiểu.

| Hiện tượng | READ UNCOMMITTED | READ COMMITTED | REPEATABLE READ | SERIALIZABLE |
| --- | --- | --- | --- | --- |
| Dirty read | Có thể xảy ra theo mô hình | Không | Không | Không |
| Non-repeatable read | Có thể | Có thể | Bị ngăn theo mô hình chuẩn | Bị ngăn |
| Phantom read | Có thể | Có thể | Có thể theo chuẩn SQL | Bị ngăn theo chuẩn SQL |
| Lịch tương đương tuần tự | Không bảo đảm | Không bảo đảm | Không bảo đảm theo chuẩn tối thiểu | Có bảo đảm |

Không nên xem bảng này là mô tả tuyệt đối của mọi engine. Ví dụ PostgreSQL triển khai REPEATABLE READ bằng snapshot isolation nên ngăn phantom read thông thường mạnh hơn mức tối thiểu của chuẩn SQL, nhưng vẫn có thể xảy ra write skew. PostgreSQL SERIALIZABLE dùng Serializable Snapshot Isolation để phát hiện cấu trúc phụ thuộc nguy hiểm và có thể hủy giao dịch cần retry.

### 6.1. READ UNCOMMITTED

Cho phép đọc dữ liệu chưa commit theo mô hình cổ điển. Người đọc có thể nhìn thấy một trạng thái tạm thời rồi bị đảo ngược khi giao dịch ghi rollback.

Ưu điểm thường được nhắc đến là giảm một số chặn đọc/ghi trong mô hình khóa. Đánh đổi là ứng dụng phải chấp nhận dirty read và những quyết định dựa trên dữ liệu không xác nhận. Trên các hệ thống dùng MVCC, yêu cầu READ UNCOMMITTED có thể được xử lý giống READ COMMITTED nên lợi ích kỳ vọng không xuất hiện.

### 6.2. READ COMMITTED

Chỉ cho truy vấn đọc dữ liệu đã commit tại thời điểm câu lệnh bắt đầu. Nếu giao dịch khác đang ghi nhưng chưa commit, truy vấn không nhìn thấy phần thay đổi ấy.

Tuy nhiên, hai câu SELECT riêng trong cùng một giao dịch có thể thấy hai trạng thái đã commit khác nhau nếu có giao dịch khác commit giữa chúng. Đây là nguồn gốc của non-repeatable read.

### 6.3. REPEATABLE READ

Bảo đảm giao dịch có cách nhìn ổn định hơn đối với dữ liệu đã đọc. Ở mức khái niệm, cùng một hàng được đọc lại không thay đổi trong phạm vi giao dịch. Một số DBMS triển khai bằng snapshot; một số dùng khóa phạm vi hoặc cơ chế khác.

Mức này không tự động giải quyết mọi bất biến liên quan nhiều hàng. Trong snapshot isolation, hai giao dịch có thể cùng đọc điều kiện chung rồi cập nhật những hàng khác nhau, dẫn đến write skew.

### 6.4. SERIALIZABLE

Mục tiêu là kết quả của các giao dịch được commit phải tương đương với một thứ tự thực thi tuần tự hợp lệ. Hệ quản trị có thể khóa, phát hiện xung đột hoặc hủy một giao dịch nếu không thể bảo đảm tính tuần tự hóa.

Ứng dụng cần sẵn sàng retry toàn bộ transaction khi nhận lỗi serialization, đồng thời giữ các tác động phụ ngoài database ở trạng thái an toàn khi thử lại.

## 7. Dữ liệu chưa xác nhận có thể gây ra hậu quả gì?

Dirty read là một vấn đề ở tầng dữ liệu nhưng có thể truyền sang nhiều bước nghiệp vụ.

### 7.1. Quyết định sai và lan truyền dữ liệu

Giả sử T1 cập nhật trạng thái đơn hàng từ `PENDING` sang `PAID` nhưng chưa commit. T2 đọc trạng thái `PAID` và bắt đầu giao hàng. Sau đó T1 rollback vì thanh toán bị từ chối. Hệ thống đã giao hàng dựa trên một trạng thái chưa từng được xác nhận.

Tình huống lan truyền:

```text
T1: UPDATE order.status = 'PAID' (chưa commit)
                 |
                 v
T2: đọc 'PAID' qua dirty read
                 |
                 v
T2: tạo lệnh giao hàng / gửi thông báo
                 |
                 v
T1: ROLLBACK -> trạng thái lại là 'PENDING'
                 |
                 v
Hành động của T2 đã xảy ra và không tự biến mất
```

Rollback chỉ hoàn tác thay đổi bên trong giao dịch T1. Nó không thể tự thu hồi email đã gửi, API đã gọi, hàng đã giao hoặc quyết định được dịch vụ khác thực hiện.

### 7.2. Cascading rollback

Một giao dịch có thể tiếp tục dựa trên dữ liệu bẩn mà giao dịch khác đã ghi. Nếu giao dịch nguồn rollback, giao dịch phụ thuộc cũng có thể cần rollback. Chuỗi hoàn tác kéo theo này được gọi là **cascading rollback** hoặc cascading abort.

Ví dụ:

```text
T1 ghi X chưa commit
    |
    v
T2 đọc X và ghi Y chưa commit
    |
    v
T3 đọc Y và ghi Z
    |
    v
T1 rollback
    |
    +--> T2 phải rollback vì Y phụ thuộc vào X
            |
            +--> T3 phải rollback vì Z phụ thuộc vào Y
```

Nếu hệ quản trị cho phép chuỗi đọc bẩn và các giao dịch phụ thuộc đã commit trước giao dịch nguồn, việc phục hồi có thể phức tạp hoặc lịch không thể phục hồi đúng. Vì thế, các hệ thống giao dịch thường cố gắng ngăn dirty read và kiểm soát thứ tự commit của những giao dịch có phụ thuộc dữ liệu.

### 7.3. Khái niệm recoverable schedule

Một lịch được gọi là **recoverable** (*có thể phục hồi*) nếu khi Tj đọc giá trị do Ti ghi, Tj không được commit trước Ti. Nói cách khác, nếu Tj phụ thuộc vào thay đổi của Ti thì Ti phải commit trước khi Tj commit.

Điều kiện:

\[
w_i(X) \rightarrow r_j(X)
\quad \Rightarrow \quad
c_i \text{ phải đứng trước } c_j
\]

Nếu Ti rollback, Tj chưa commit và có thể bị hủy theo. Điều kiện này không tự ngăn dirty read, nhưng bảo đảm thứ tự commit không làm một giao dịch đã xác nhận phụ thuộc vào giao dịch nguồn chưa được xác nhận.

Một **cascadeless schedule** mạnh hơn: Tj chỉ được đọc dữ liệu do Ti tạo sau khi Ti đã commit. Như vậy, không có đọc bẩn và không cần rollback dây chuyền chỉ vì phụ thuộc đọc dữ liệu chưa commit.

## 8. So sánh dirty read với các loại bất thường đồng thời khác

| Hiện tượng | Diễn biến | Hậu quả |
| --- | --- | --- |
| Dirty read | Đọc thay đổi chưa commit của giao dịch khác | Dữ liệu đọc có thể biến mất sau rollback |
| Non-repeatable read | Đọc cùng hàng hai lần, giữa hai lần có commit cập nhật | Giá trị quan sát thay đổi trong một giao dịch |
| Phantom read | Truy vấn theo điều kiện nhiều lần, số/tập hàng thay đổi | Kết quả truy vấn tập hợp thay đổi |
| Lost update | Hai giao dịch đọc cũ rồi ghi giá trị tuyệt đối | Một cập nhật bị ghi đè |
| Write skew | Cùng đọc điều kiện, ghi các hàng khác nhau | Bất biến liên hàng bị phá vỡ |

Dirty read tập trung vào **nguồn gốc chưa commit của phiên bản đọc**. Những hiện tượng còn lại có thể xảy ra dù mọi lần đọc chỉ nhìn dữ liệu đã commit. Vì vậy, tránh dirty read chưa có nghĩa đã giải quyết hết bất thường đồng thời.

## 9. Khi nào người ta cân nhắc READ UNCOMMITTED?

READ UNCOMMITTED đôi khi được nhắc đến trong những truy vấn có tính chất tham khảo, chấp nhận sai lệch ngắn hạn và ưu tiên giảm chờ đọc. Ví dụ, một báo cáo nội bộ gần đúng về hoạt động đang diễn ra có thể không cần phản ánh trạng thái đã commit tuyệt đối.

Tuy nhiên, phải cân nhắc kỹ:

- Dữ liệu được đọc có được dùng để ra quyết định nghiệp vụ hay chỉ để quan sát?
- Nếu giá trị biến mất sau rollback, hậu quả là gì?
- Truy vấn có thể đọc một phần dữ liệu trung gian khi nhiều hàng được cập nhật không?
- Báo cáo có cần tái lập được cùng một kết quả không?
- DBMS thực tế có dirty read hay ánh xạ READ UNCOMMITTED sang mức khác?
- Cơ chế khóa/MVCC có khiến lựa chọn này không đem lại lợi ích hiệu năng như kỳ vọng?

Không dùng READ UNCOMMITTED cho những quyết định trọng yếu như tính số dư khả dụng, xác nhận thanh toán, cấp hạn mức, trừ kho, đặt chỗ cuối cùng hay quyết định chuyển trạng thái không thể đảo ngược. Những luồng đó cần dữ liệu đã xác nhận và cơ chế đồng bộ hóa phù hợp.

Nếu mục tiêu là có báo cáo gần thời gian thực với tải đọc cao, có thể xem xét bản sao đọc, snapshot báo cáo, bảng tổng hợp hoặc luồng sự kiện riêng. Những giải pháp này cần công bố rõ độ trễ dữ liệu và không nên giả vờ rằng dữ liệu gần đúng là dữ liệu giao dịch đã xác nhận.

## 10. Phân tích một lịch: giao dịch đọc có được commit trước không?

Xét lịch:

```text
S = w1(X), r2(X), w2(Y), c2, a1
```

T2 đã đọc X do T1 ghi khi T1 chưa commit. T2 sau đó ghi Y và commit. T1 cuối cùng abort.

Phân tích:

1. `w1(X)` xuất hiện trước `r2(X)`, nên T2 phụ thuộc vào thay đổi của T1.
2. `c2` xảy ra trước `a1`, nghĩa là T2 đã commit trong khi giao dịch nguồn T1 chưa được xác nhận.
3. Khi T1 abort, giá trị X bị hoàn tác.
4. T2 đã commit Y dựa trên X chưa commit. Lịch này **không recoverable** và có thể để lại dữ liệu không nhất quán.

Nếu lịch là:

```text
S = w1(X), r2(X), w2(Y), c1, c2
```

thì T1 commit trước T2. Lịch có đọc dữ liệu trước khi nguồn commit nhưng thứ tự commit là recoverable. Tuy vậy, nếu T1 rollback thay vì commit, T2 phải được rollback; lịch vẫn có nguy cơ cascading abort.

Nếu lịch là:

```text
S = w1(X), c1, r2(X), w2(Y), c2
```

T2 chỉ đọc X sau khi T1 commit. Đây là lịch cascadeless đối với phụ thuộc đang xét.

Các ví dụ này nhấn mạnh rằng phân tích giao dịch phải xét cả thứ tự thao tác và thứ tự commit/abort, không chỉ xem có câu lệnh SELECT hay UPDATE.

## 11. Cách thiết kế ứng dụng để không phụ thuộc dữ liệu chưa xác nhận

### 11.1. Đặt thao tác liên quan trong transaction phù hợp

Nếu một quyết định cần dữ liệu đã commit, dùng mức cô lập không cho dirty read. Với PostgreSQL, READ COMMITTED đã không cho truy vấn thông thường đọc thay đổi chưa commit.

Ví dụ kiểm tra tài khoản:

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT balance
FROM lab_accounts
WHERE account_id = 101;

-- Kiểm tra và thực hiện cập nhật trong cùng giao dịch phù hợp.

COMMIT;
```

Nếu nghiệp vụ yêu cầu bảo vệ nhiều bước đọc–ghi, cần bổ sung khóa hoặc mức cô lập thích hợp; chỉ đặt READ COMMITTED không bảo vệ mọi bất biến.

### 11.2. Không thực hiện side effect bên ngoài trước khi commit

Một lỗi thiết kế thường gặp:

```text
1. UPDATE trạng thái đơn hàng = PAID (chưa commit)
2. Gửi email "Thanh toán thành công"
3. Gọi API giao hàng
4. COMMIT
```

Nếu bước 4 thất bại và rollback, email và yêu cầu giao hàng vẫn đã được gửi. Dù dữ liệu nội bộ không bị dirty read, side effect vẫn xảy ra trước khi kết quả được xác nhận.

Một cách thiết kế phổ biến là **transactional outbox**:

- Trong cùng transaction, cập nhật trạng thái nghiệp vụ và ghi một sự kiện vào bảng outbox.
- Commit transaction.
- Một worker riêng đọc những sự kiện đã commit từ outbox và thực hiện gửi email/gọi API.
- Worker xử lý idempotency để tránh tác dụng phụ lặp khi retry.

Như vậy, sự kiện chỉ được phát ra từ trạng thái nghiệp vụ đã commit. Outbox không tự làm dịch vụ ngoài trở thành một phần của transaction cơ sở dữ liệu, nhưng giúp đồng bộ việc ghi trạng thái và ghi ý định phát sự kiện.

### 11.3. Không nhầm dữ liệu đang hiển thị với dữ liệu được xác nhận

Một giao diện có thể hiển thị tiến trình "đang xử lý" trong khi giao dịch chưa commit. Hãy biểu diễn rõ trạng thái:

- `PENDING`: yêu cầu đã tiếp nhận nhưng chưa hoàn thành.
- `COMMITTED` hoặc trạng thái nghiệp vụ thành công: thay đổi đã được xác nhận.
- `FAILED` hoặc `CANCELLED`: không được xem là kết quả thành công.

Tên trạng thái và quy trình cụ thể phụ thuộc nghiệp vụ. Nguyên tắc là không quảng bá một thay đổi chưa xác nhận như kết quả cuối cùng.

## 12. Câu hỏi và tình huống tự luyện

### Bài 1: Dirty read

Số dư ban đầu 2.000. T1 trừ 500 nhưng chưa commit. T2 đọc được 1.500 rồi tính hạn mức chi tiếp. T1 rollback.

**Câu hỏi:** Số dư đã commit sau rollback là bao nhiêu? T2 đã dựa trên loại dữ liệu nào?

**Gợi ý:** Phân biệt giá trị tạm thời T1 đã ghi với phiên bản đã commit.

### Bài 2: Phân biệt WR thông thường và dirty read

T1 ghi X = 15, commit. Sau đó T2 đọc X = 15.

**Câu hỏi:** Đây có phải dirty read không?

**Gợi ý:** Kiểm tra thời điểm commit của T1 so với thời điểm T2 đọc.

### Bài 3: Recoverability

```text
S = w1(X), r2(X), c2, a1
```

**Câu hỏi:** Vì sao lịch này không recoverable? Nếu T1 abort, điều gì đã xảy ra với kết quả T2?

### Bài 4: PostgreSQL

Một nhà phát triển chạy:

```sql
BEGIN ISOLATION LEVEL READ UNCOMMITTED;
SELECT balance FROM lab_accounts WHERE account_id = 101;
```

Trong khi giao dịch khác đang cập nhật nhưng chưa commit, truy vấn có thể nhìn thấy giá trị chưa commit không?

**Gợi ý:** Phân biệt tên isolation level được yêu cầu và hành vi PostgreSQL triển khai.

### Bài 5: Side effect

Một ứng dụng gửi email xác nhận trước khi transaction commit. Database sau đó rollback.

**Câu hỏi:** Vì sao rollback không thu hồi được email? Hãy đề xuất cách bảo đảm email chỉ được gửi từ yêu cầu đã commit.

## 13. Ghi nhớ khi sử dụng READ UNCOMMITTED

READ UNCOMMITTED cho phép đọc thay đổi chưa commit trong các hệ quản trị thực sự hỗ trợ mức cô lập này. Rủi ro trung tâm là **dirty read**: giao dịch đọc có thể sử dụng dữ liệu mà giao dịch ghi sau đó rollback. Nếu giao dịch đọc đã commit hoặc tạo tác động ngoài database, hậu quả có thể lan rộng và khó phục hồi.

Hãy phân tích theo ba điểm: **giá trị đọc có nguồn từ giao dịch đã commit chưa; giao dịch phụ thuộc có thể commit trước nguồn hay không; và ứng dụng có phát sinh tác động không thể rollback trước khi trạng thái được xác nhận không**. Cần kiểm tra hành vi cụ thể của DBMS thay vì dựa vào tên isolation level; PostgreSQL là ví dụ rõ ràng vì READ UNCOMMITTED được xử lý như READ COMMITTED và không cho dirty read thông thường.

Khi dữ liệu điều khiển quyết định nghiệp vụ quan trọng, hãy ưu tiên đọc dữ liệu đã xác nhận, đặt transaction boundary rõ ràng, điều phối truy cập khi cần và chỉ phát tác dụng phụ bên ngoài sau commit thông qua cơ chế phù hợp.

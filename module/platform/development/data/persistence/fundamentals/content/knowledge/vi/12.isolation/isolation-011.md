# Vai trò của snapshot và kiểm soát đồng thời đa phiên bản (MVCC)

Khi một ứng dụng Java có nhiều người dùng đọc và sửa cùng một dữ liệu, kết quả truy vấn phụ thuộc không chỉ vào **câu SQL** mà còn vào **thời điểm truy vấn lấy ảnh chụp dữ liệu (snapshot)** và các giao dịch đang chạy. Chẳng hạn, một khách hàng xem số dư trong khi một yêu cầu khác đang chuyển tiền: người xem có thấy số dư chưa được xác nhận không? Nếu đọc lại trong cùng giao dịch, con số có đổi không? Nếu hai bác sĩ cùng xin rời ca, vì sao mỗi người đều có thể thấy “vẫn còn bác sĩ trực” và cùng đưa hệ thống về trạng thái không ai trực?

Bài này thuộc chương **Tính cô lập** của module **DATA_PERSISTENCE_FUNDAMENTALS**, nơi người học xây dựng nền tảng persistence cho ứng dụng Java: mô hình dữ liệu, truy vấn, chỉ mục, giao dịch, mức cô lập và kiểm soát đồng thời; từ đó thiết kế ranh giới truy cập dữ liệu và tối ưu hiệu năng khi hệ thống có tải thực tế. Nội dung dùng **PostgreSQL** làm ví dụ chính vì cách triển khai MVCC của hệ này dễ quan sát. **Không suy nguyên hành vi PostgreSQL sang MySQL, Oracle, SQL Server hoặc mọi hệ thống dùng MVCC**: các mức cô lập có tên tương tự vẫn có thể khác nhau trong cách lấy snapshot, xử lý khóa và kiểm tra xung đột.

## 1. Người học cần hiểu được điều gì?

Sau bài học, bạn có thể:

- Giải thích MVCC lưu và sử dụng nhiều phiên bản logic của bản ghi để giảm xung đột giữa người đọc và người ghi.
- Phân biệt **snapshot của một câu lệnh** với **snapshot ổn định cho nhiều câu lệnh** trong cùng giao dịch.
- Dự đoán giá trị mà hai phiên PostgreSQL sẽ đọc ở mức **READ COMMITTED** và **REPEATABLE READ**.
- Nhận diện giới hạn của snapshot isolation, đặc biệt là **write skew** và các quy tắc nghiệp vụ xuyên nhiều hàng.
- Chọn công cụ bổ sung khi MVCC chưa đủ: **UPDATE có điều kiện, ràng buộc, khóa hàng, kiểm soát phiên bản lạc quan hoặc SERIALIZABLE**.
- Quản lý vòng đời giao dịch Java, tránh giữ snapshot lâu và phân tích tình huống đọc dữ liệu không nhất quán.

## 2. Vấn đề mà MVCC giải quyết

Hãy tưởng tượng bảng tài khoản có một hàng:

~~~text
accounts
id = 101, balance = 1 000
~~~

Hai yêu cầu chạy đồng thời:

~~~text
Thời gian --> 

T1 (ghi):     BEGIN --> UPDATE balance = 900 ---------> COMMIT
T2 (đọc):                    SELECT balance
~~~

Khi T2 đọc lúc T1 chưa commit, cơ sở dữ liệu cần trả lời hai câu hỏi:

1. **T2 được phép nhìn thấy dữ liệu chưa commit của T1 không?** Nếu nhìn thấy, rồi T1 rollback, T2 đã sử dụng một giá trị chưa bao giờ trở thành trạng thái xác nhận.
2. **T2 có phải chờ T1 kết thúc mới đọc được không?** Nếu mọi lần đọc phải khóa và chờ người ghi, hệ thống đọc nhiều sẽ mất khả năng phục vụ đồng thời.

**Multi-Version Concurrency Control (MVCC)** là một cách tổ chức quản lý đồng thời: cơ sở dữ liệu duy trì thông tin về **các phiên bản của hàng** và dùng quy tắc hiển thị để quyết định phiên bản nào một giao dịch được thấy. Nhờ đó, ở nhiều trường hợp, truy vấn đọc thông thường có thể đọc một phiên bản đã commit phù hợp với snapshot trong khi giao dịch khác đang sửa hàng đó.

Trong PostgreSQL, một truy vấn **SELECT** thường (không yêu cầu khóa) không phải chờ giao dịch đang sửa cùng hàng chỉ vì hàng ấy được cập nhật. Tuy nhiên, **MVCC không có nghĩa hệ thống không dùng khóa**: nhiều thao tác ghi, DDL và truy vấn khóa tường minh vẫn có thể chờ nhau.

## 3. Phiên bản hàng, commit và snapshot

### 3.1. Bản ghi có thể có nhiều phiên bản vật lý

Giả sử số dư đang là **1 000**. T1 cập nhật thành **900** nhưng chưa commit. Có thể hình dung:

~~~text
Phiên bản v1                         Phiên bản v2
balance = 1 000                      balance = 900
đã commit trước đó                   được tạo bởi T1
       |                                    |
       +--------- snapshot của T2 ---------+
                  |
       T2 có thể vẫn thấy v1
       vì T1 chưa commit
~~~

Sau khi T1 commit, **truy vấn mới** có snapshot phù hợp có thể nhìn thấy v2. Truy vấn trong một giao dịch giữ snapshot cũ có thể tiếp tục nhìn thấy v1, nếu mức cô lập của hệ quản trị quy định như vậy.

Sơ đồ trên mô tả **khái niệm hiển thị**, không phải định dạng lưu trữ bắt buộc của mọi cơ sở dữ liệu. PostgreSQL lưu thông tin phiên bản trong heap tuple, trong đó có các trường hệ thống như **xmin** và **xmax**; các hệ quản trị khác có thể dùng undo log hoặc cấu trúc khác. Một phiên bản cũ còn tồn tại trên đĩa không có nghĩa mọi truy vấn đều được phép đọc nó.

### 3.2. Snapshot là bộ quy tắc nhìn thấy dữ liệu

**Snapshot** là trạng thái quan sát nhất quán theo quy tắc MVCC tại thời điểm được lấy. Trong PostgreSQL, snapshot xét các transaction ID đã hoàn thành, đang hoạt động và những thông tin liên quan để xác định phiên bản nào hiển thị. Có thể hiểu theo hướng thực dụng:

- Những thay đổi **đã commit trước ranh giới snapshot** có thể hiển thị, tùy quy tắc phiên bản.
- Thay đổi của giao dịch khác **chưa commit tại ranh giới snapshot** sẽ không hiển thị trong một truy vấn snapshot thông thường, kể cả nếu giao dịch kia commit trong lúc truy vấn chạy.
- Những thay đổi **do chính giao dịch hiện tại tạo ra** thường có thể được các câu lệnh tiếp theo trong giao dịch đó đọc thấy, theo ngữ nghĩa lệnh và mức cô lập; snapshot không làm giao dịch “mù” với dữ liệu chính nó vừa ghi.
- Bản ghi bị **DELETE** không nhất thiết lập tức bị xóa vật lý; phiên bản có thể phải được giữ lại khi snapshot còn cần nó.

**Snapshot không phải bản sao nguyên bảng**, cũng không đồng nghĩa chụp toàn bộ dữ liệu vào bộ nhớ. Nó chủ yếu là thông tin mà hệ quản trị dùng khi duyệt hàng và xác định tính hiển thị. Vì vậy, việc tạo snapshot không mặc nhiên sao chép hàng triệu bản ghi.

### 3.3. Mốc thời gian thực không đủ để mô tả một snapshot

Đừng hiểu snapshot đơn giản là “mọi hàng có timestamp trước 10:00:00”. Hai giao dịch có thể bắt đầu theo một thứ tự nhưng commit theo thứ tự khác; đồng hồ ứng dụng và đồng hồ DB cũng có thể chênh lệch. Thứ tự **commit**, tập giao dịch còn hoạt động và quy tắc cách ly của hệ quản trị mới quyết định khả năng hiển thị. Cột nghiệp vụ như **created_at** không thay thế snapshot của MVCC.

## 4. Hai cách quan trọng để lấy snapshot

Để hiểu cơ chế cô lập, cần phân biệt thời điểm snapshot được xác lập và việc nó có được dùng lại hay không.

| Cách lấy snapshot | Cách vận hành điển hình | Hệ quả với hai lần SELECT |
| --- | --- | --- |
| **Theo câu lệnh** | Mỗi câu SELECT dùng snapshot mới tại lúc câu lệnh bắt đầu | SELECT sau có thể thấy commit của giao dịch khác xảy ra giữa hai SELECT |
| **Theo giao dịch** | Các lần đọc snapshot thông thường dùng cùng snapshot được xác lập sớm trong giao dịch | Hai SELECT thường tiếp tục thấy cùng trạng thái của dữ liệu do giao dịch khác thay đổi |

Trong PostgreSQL:

- **READ COMMITTED**: mỗi câu lệnh đọc thông thường lấy snapshot mới khi bắt đầu câu lệnh.
- **REPEATABLE READ**: các lần đọc thông thường trong giao dịch dựa trên cùng snapshot giao dịch, được thiết lập khi câu lệnh truy cập dữ liệu phù hợp đầu tiên chạy (không phải nhất thiết ngay tại lệnh **BEGIN**).
- **SERIALIZABLE**: cũng cung cấp góc nhìn snapshot ổn định, đồng thời thêm cơ chế phát hiện các mẫu phụ thuộc nguy hiểm để bảo đảm kết quả tương đương một thứ tự chạy tuần tự nào đó của các giao dịch đã commit.

Tên gọi mức cô lập là một hợp đồng với **hệ quản trị cụ thể**. Ví dụ, PostgreSQL xử lý yêu cầu **READ UNCOMMITTED** như **READ COMMITTED**; không có nghĩa mọi DBMS đều làm thế. Trong MySQL InnoDB, **consistent read** và **locking/current read** có các quy tắc khác nhau; không nên dự đoán hành vi chỉ dựa trên việc mức cô lập cùng mang tên **REPEATABLE READ**.

## 5. Thực nghiệm hai phiên: READ COMMITTED

Sử dụng hai cửa sổ SQL độc lập kết nối đến cùng một cơ sở dữ liệu PostgreSQL. Chuẩn bị dữ liệu trên môi trường thử nghiệm:

~~~sql
CREATE TABLE mvcc_accounts (
    id BIGINT PRIMARY KEY,
    balance NUMERIC(12, 2) NOT NULL CHECK (balance >= 0)
);

INSERT INTO mvcc_accounts (id, balance) VALUES (101, 1000.00);
~~~

**Phiên T1** bắt đầu giao dịch và đọc hàng:

~~~sql
BEGIN ISOLATION LEVEL READ COMMITTED;
SELECT balance FROM mvcc_accounts WHERE id = 101;
-- 1000.00
~~~

Trong lúc T1 còn mở, **phiên T2** chạy:

~~~sql
BEGIN;
UPDATE mvcc_accounts
SET balance = 900.00
WHERE id = 101;
COMMIT;
~~~

Quay lại **T1**:

~~~sql
SELECT balance FROM mvcc_accounts WHERE id = 101;
-- 900.00
COMMIT;
~~~

Sơ đồ thời gian:

~~~text
T1 READ COMMITTED            T2
BEGIN
SELECT --> 1000
                             BEGIN
                             UPDATE --> 900
                             COMMIT
SELECT --> 900
COMMIT
~~~

**Tại sao T1 thấy khác nhau?** Câu SELECT thứ hai lấy snapshot mới sau khi T2 commit. Đây là một ví dụ về **non-repeatable read**: đọc lại một hàng trong cùng giao dịch nhưng nhận giá trị khác do giao dịch khác đã xác nhận thay đổi.

Điểm cần nhớ:

- T1 **không thấy** thay đổi của T2 khi T2 chưa commit, nên ví dụ không có dirty read.
- Mỗi câu SELECT tự nó đọc theo snapshot phù hợp; **READ COMMITTED không bảo đảm nhiều SELECT tách rời nhìn thấy cùng một trạng thái thời gian**.
- Câu **UPDATE** ở mức READ COMMITTED có quy tắc tương tác với khóa, chờ và kiểm tra lại điều kiện sau khi giao dịch đang khóa hàng kết thúc. Không nên suy từ ví dụ SELECT rằng mọi lệnh SQL xử lý snapshot theo đúng một cách duy nhất.

## 6. Thực nghiệm hai phiên: REPEATABLE READ

Đặt lại số dư để tái hiện cùng một kịch bản:

~~~sql
UPDATE mvcc_accounts SET balance = 1000.00 WHERE id = 101;
~~~

**T1**:

~~~sql
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT balance FROM mvcc_accounts WHERE id = 101;
-- 1000.00: xác lập snapshot giao dịch
~~~

**T2**:

~~~sql
BEGIN;
UPDATE mvcc_accounts SET balance = 900.00 WHERE id = 101;
COMMIT;
~~~

Quay lại **T1**:

~~~sql
SELECT balance FROM mvcc_accounts WHERE id = 101;
-- 1000.00: vẫn đọc theo snapshot trước khi T2 commit
COMMIT;
~~~

Sau khi T1 đã kết thúc, một giao dịch **mới** đọc bảng sẽ thấy **900.00** (nếu không có thay đổi khác).

~~~text
T1 REPEATABLE READ           T2
BEGIN
SELECT --> 1000
       snapshot S
                             UPDATE --> 900
                             COMMIT
SELECT --> 1000 (S)
COMMIT
Giao dịch mới --> 900
~~~

Trong PostgreSQL, **REPEATABLE READ** dùng snapshot ổn định cho các lần đọc phù hợp, vì vậy tránh được non-repeatable read và hiện tượng phantom trong các truy vấn snapshot thông thường. Tuy nhiên, điều đó **chưa đủ để bảo đảm mọi quy tắc nghiệp vụ khi có hai giao dịch cùng ghi**.

Một chi tiết dễ nhầm: **BEGIN** không nhất thiết cố định snapshot ngay tại thời điểm gửi BEGIN. Ở PostgreSQL, với giao dịch REPEATABLE READ, snapshot được lấy khi câu lệnh thực sự cần snapshot đầu tiên chạy. Nếu T2 commit sau khi T1 BEGIN nhưng trước SELECT đầu của T1, SELECT đầu của T1 có thể thấy dữ liệu T2 đã commit.

## 7. Snapshot và các hiện tượng bất thường thường gặp

| Hiện tượng | Cách hình dung | MVCC/snapshot có tự giải quyết? |
| --- | --- | --- |
| **Dirty read** | T1 đọc giá trị T2 vừa sửa nhưng T2 chưa commit, sau đó T2 rollback | Snapshot đã commit của PostgreSQL không cho phép kiểu đọc này ở các mức được hỗ trợ |
| **Non-repeatable read** | T1 đọc một hàng hai lần và thấy giá trị khác sau T2 commit | Có thể xảy ra ở PostgreSQL READ COMMITTED; REPEATABLE READ ngăn trong đọc snapshot thông thường |
| **Phantom read** | T1 chạy cùng điều kiện WHERE hai lần, lần sau có hàng mới do T2 commit | Có thể ở READ COMMITTED; PostgreSQL REPEATABLE READ tránh phantom trong đọc snapshot thông thường |
| **Lost update** | Hai tiến trình đọc cùng giá trị cũ và ghi đè kết quả tính toán của nhau | Cần xem cách ghi, khóa và mức cô lập; snapshot không thay thế thiết kế cập nhật an toàn |
| **Write skew** | Hai giao dịch đọc cùng điều kiện trên nhiều hàng rồi ghi hai hàng khác nhau, tạo trạng thái vi phạm quy tắc | Có thể xảy ra trong snapshot isolation; cần kiểm soát phụ thuộc nghiệp vụ |
| **Serialization failure** | DB phát hiện giao dịch không thể cùng commit mà vẫn giữ kết quả tương đương chạy tuần tự | Giao dịch bị hủy và ứng dụng cần retry toàn bộ unit of work khi phù hợp |

Một bảng thuật ngữ không thể thay thế tài liệu isolation của DBMS cụ thể. Đặc biệt, **SQL standard** mô tả các hiện tượng cơ bản, còn PostgreSQL triển khai **REPEATABLE READ** mạnh hơn yêu cầu tối thiểu của mức có tên đó.

## 8. Vì sao snapshot ổn định chưa đủ: write skew

Xét quy tắc bệnh viện: **mỗi ca trực phải còn ít nhất một bác sĩ ở trạng thái on_call = true**. Ban đầu có hai bác sĩ cùng trực:

~~~sql
CREATE TABLE on_call_doctors (
    doctor_id BIGINT PRIMARY KEY,
    shift_id BIGINT NOT NULL,
    on_call BOOLEAN NOT NULL
);

INSERT INTO on_call_doctors (doctor_id, shift_id, on_call)
VALUES (1, 20, TRUE), (2, 20, TRUE);
~~~

Hai bác sĩ xin rời ca trong cùng thời gian. Ứng dụng mỗi bên làm như sau:

1. Đếm người đang trực trong ca 20.
2. Nếu có từ hai người trở lên, cho phép bác sĩ hiện tại chuyển sang **on_call = false**.

Ở PostgreSQL **REPEATABLE READ**, lịch thực thi dưới đây có thể xảy ra:

| Thời điểm | T1: bác sĩ 1 | T2: bác sĩ 2 |
| --- | --- | --- |
| 1 | BEGIN REPEATABLE READ | BEGIN REPEATABLE READ |
| 2 | SELECT COUNT(*) = 2 | SELECT COUNT(*) = 2 |
| 3 | UPDATE doctor_id = 1 thành false | UPDATE doctor_id = 2 thành false |
| 4 | COMMIT thành công | COMMIT thành công |
| Kết quả | Cả hai đều nghỉ | **Không còn ai trực** |

Hai giao dịch cùng đọc trạng thái “có hai bác sĩ” từ snapshot riêng và cập nhật **hai hàng khác nhau**. Chúng không nhất thiết tranh cùng khóa hàng, vì vậy cả hai có thể commit dưới mức REPEATABLE READ mà vi phạm quy tắc trên toàn bộ ca. Đây là **write skew**; nó không cần dirty read hay non-repeatable read.

Có thể thử mô phỏng trực tiếp:

**T1**

~~~sql
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT count(*) FROM on_call_doctors
WHERE shift_id = 20 AND on_call = TRUE;
-- 2

UPDATE on_call_doctors
SET on_call = FALSE
WHERE doctor_id = 1;

-- Chưa COMMIT cho tới khi T2 cũng đã đọc và cập nhật.
~~~

**T2**

~~~sql
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT count(*) FROM on_call_doctors
WHERE shift_id = 20 AND on_call = TRUE;
-- 2

UPDATE on_call_doctors
SET on_call = FALSE
WHERE doctor_id = 2;
COMMIT;
~~~

Sau đó T1 **COMMIT**. Cả hai giao dịch có thể thành công, để lại 0 người trực.

### Những cách bảo vệ quy tắc xuyên nhiều hàng

- **SERIALIZABLE trong PostgreSQL**: khi cả hai giao dịch thực sự đọc tập hàng rồi cập nhật như trên, cơ chế Serializable Snapshot Isolation (**SSI**) có thể phát hiện vòng phụ thuộc nguy hiểm và hủy ít nhất một giao dịch để bảo đảm tính tuần tự hóa. Ứng dụng cần xử lý **SQLSTATE 40001** bằng retry **toàn bộ giao dịch**, không chỉ câu UPDATE cuối.
- **Khóa một hàng chung đại diện cho ca trực** trước khi đếm và quyết định, chẳng hạn hàng trong bảng **shifts** với **SELECT ... FOR UPDATE**. Tất cả đường ghi ảnh hưởng đến quy tắc phải tuân cùng giao thức khóa. Khi các lần ghi được tuần tự hóa bằng khóa chung, giao dịch kế tiếp mới đánh giá điều kiện với trạng thái phù hợp. Chọn mức cô lập và cách khóa nhất quán; tại REPEATABLE READ, nếu snapshot đã cũ, có thể phải hủy/retry thay vì mong khóa cập nhật snapshot cũ.
- **Thiết kế ràng buộc dữ liệu hoặc mô hình lưu trữ khác** để đưa quy tắc về một thao tác có tính nguyên tử nếu khả thi. Không thể giả định một **CHECK** trên một hàng đơn lẻ sẽ kiểm tra được số bác sĩ trực trong cả bảng.

Điều cốt lõi: **snapshot ổn định là góc nhìn nhất quán, không tự động là cam kết rằng mọi quyết định đọc rồi ghi sẽ tương đương một lịch chạy tuần tự**.

## 9. PostgreSQL SERIALIZABLE và cơ chế SSI

PostgreSQL sử dụng **Serializable Snapshot Isolation (SSI)** ở mức SERIALIZABLE. Nó cho phép nhiều giao dịch tiếp tục đọc bằng snapshot, đồng thời theo dõi các quan hệ phụ thuộc cần thiết để phát hiện khi một nhóm giao dịch đã commit sẽ tạo ra kết quả không thể sắp thành thứ tự tuần tự hợp lệ.

Sơ đồ ý tưởng với quy tắc bác sĩ:

~~~text
T1 đọc: cả A và B đang trực   <-- snapshot S1
T2 đọc: cả A và B đang trực   <-- snapshot S2

T1 ghi A nghỉ        T2 ghi B nghỉ
      |                    |
      +---- phụ thuộc -----+
                |
     SSI phát hiện lịch không thể
     tuần tự hóa an toàn
                |
     một giao dịch có thể bị hủy
     (serialization failure, 40001)
~~~

Không nên hiểu SSI chỉ là “khóa toàn bảng” hoặc “luôn chặn một giao dịch trước khi ghi”. **Serializable** không mặc định làm mọi giao dịch chạy nối đuôi nhau; nó bảo đảm kết quả của những giao dịch commit tương đương một lịch tuần tự. Đổi lại, có thể xuất hiện **serialization failure**, kể cả khi không thấy tranh chấp khóa hàng trực tiếp. PostgreSQL có thể xảy ra false positive theo cơ chế theo dõi phụ thuộc, vì vậy ứng dụng phải có chiến lược retry phù hợp.

Ví dụ khai báo mức cô lập:

~~~sql
BEGIN ISOLATION LEVEL SERIALIZABLE;
-- Đọc điều kiện nghiệp vụ, xác nhận, cập nhật.
COMMIT;
~~~

Nếu bị lỗi 40001, cần chạy lại **toàn bộ logic kiểm tra và ghi** trong một giao dịch mới để các quyết định được đưa ra trên snapshot mới. Không phải mọi lỗi đều nên retry; lỗi xác thực, dữ liệu không hợp lệ hay vi phạm quy tắc nghiệp vụ có thể cần trả về người dùng.

## 10. MVCC và khóa: những gì có thể chạy song song

MVCC được thiết kế để giảm nhu cầu người đọc phải chờ người ghi, nhưng không thể loại bỏ việc điều phối khi nhiều giao dịch sửa cùng dữ liệu.

| Tình huống PostgreSQL | Hành vi thường gặp |
| --- | --- |
| SELECT thông thường đọc hàng mà một transaction khác đang UPDATE | Có thể đọc phiên bản đã commit phù hợp snapshot mà không đợi giao dịch ghi hoàn tất |
| Hai transaction cùng UPDATE một hàng | Có thể chờ khóa hàng; sau khi chờ, cách tiếp tục phụ thuộc isolation và điều kiện UPDATE |
| SELECT ... FOR UPDATE trên hàng đang bị transaction khác khóa | Có thể phải chờ hoặc thất bại nếu dùng NOWAIT; SKIP LOCKED có ngữ nghĩa riêng |
| DDL thay đổi cấu trúc bảng khi có truy vấn hoạt động | Có thể tranh chấp khóa ở cấp quan hệ, tùy lệnh |
| VACUUM dọn phiên bản không còn cần thiết | Phụ thuộc snapshot cũ và những cơ chế giữ lại phiên bản; không phải mọi phiên bản cũ đều được xóa ngay |

Ở PostgreSQL, các truy vấn **SELECT ... FOR UPDATE / FOR NO KEY UPDATE / FOR SHARE / FOR KEY SHARE** có ý nghĩa khóa khác nhau. Chỉ chọn khóa khi hiểu điều kiện tranh chấp cần phòng tránh; khóa quá rộng làm tăng thời gian chờ và khả năng deadlock.

### 10.1. Tránh lost update bằng một câu UPDATE nguyên tử

Thay vì:

~~~text
SELECT quantity --> 5
trong Java: newQuantity = 5 - 1
UPDATE quantity = 4
~~~

hãy cân nhắc:

~~~sql
UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 42
  AND quantity >= 1;
~~~

Kiểm tra **số hàng cập nhật** để xác định thao tác có thành công. Cách này giảm nguy cơ hai tiến trình cùng tính từ giá trị cũ khi mục tiêu chỉ là một thay đổi đơn giản trên một hàng. Nếu còn phải tạo đơn, ghi lịch sử hoặc thay đổi nhiều hàng, vẫn cần **giao dịch** bao trùm cả đơn vị nghiệp vụ.

### 10.2. Kiểm soát phiên bản lạc quan

Khi một người dùng đọc bản ghi, sửa trên giao diện rồi lưu sau một khoảng thời gian, có thể dùng một trường **version**:

~~~sql
UPDATE documents
SET title = :new_title,
    version = version + 1
WHERE id = :document_id
  AND version = :version_read_before;
~~~

Nếu số hàng cập nhật là **0**, bản ghi đã bị sửa hoặc không còn tồn tại: ứng dụng cần báo xung đột hoặc tải lại. Đây là **optimistic locking ở tầng ứng dụng**, bổ sung cho MVCC. Nó không tự kiểm tra được quy tắc xuyên nhiều bản ghi nếu mỗi luồng chỉ tăng version của một bản ghi riêng.

## 11. Bảng so sánh ba mức cô lập trong PostgreSQL

| Khía cạnh | READ COMMITTED | REPEATABLE READ | SERIALIZABLE |
| --- | --- | --- | --- |
| Snapshot cho SELECT thông thường | Mới ở mỗi câu lệnh | Một snapshot cho giao dịch | Một snapshot cho giao dịch, thêm kiểm tra tính tuần tự hóa |
| Dirty read | Không | Không | Không |
| Non-repeatable read do transaction khác commit | Có thể | Không trong đọc snapshot thông thường | Không trong đọc snapshot thông thường |
| Phantom read trong các SELECT thông thường | Có thể | Không theo hành vi PostgreSQL | Không theo kết quả của lịch tương đương tuần tự |
| Write skew có thể commit | Có | Có | DB phải ngăn lịch không tuần tự hóa, có thể hủy một giao dịch |
| Cập nhật tranh chấp | Phụ thuộc khóa và câu lệnh | Có thể phát sinh lỗi khi hàng đã thay đổi từ khi lấy snapshot | Có thể chờ hoặc bị serialization failure |
| Việc ứng dụng cần làm | Thiết kế atomic UPDATE, khóa/ràng buộc nếu cần | Bảo vệ quy tắc nhiều hàng; xử lý xung đột ghi | Có retry toàn giao dịch và giữ transaction ngắn |

**Đây là bảng cho PostgreSQL**, không phải định nghĩa triển khai áp dụng nguyên xi cho tất cả DBMS. Chọn isolation dựa trên bất biến nghiệp vụ cần bảo vệ, mức tranh chấp, chi phí retry và kiểm thử thực tế; **SERIALIZABLE không phải công tắc tối ưu cho mọi truy vấn**.

## 12. Snapshot có liên quan gì đến thời gian sống của transaction?

Một phiên bản hàng cũ có thể vẫn cần thiết để phục vụ những transaction đang nhìn qua snapshot cũ. Do đó, MVCC phải có cơ chế **thu hồi phiên bản hết khả năng được nhìn thấy**; ở PostgreSQL, **VACUUM/autovacuum** đóng vai trò quan trọng. Cần phân biệt:

- **Phiên bản logic hiện hành**: dữ liệu mới nhất mà một giao dịch mới có thể nhìn thấy theo quy tắc của nó.
- **Phiên bản cũ vẫn có thể nhìn thấy**: phải được giữ trong một số tình huống để phục vụ transaction/snapshot cũ.
- **Phiên bản đã chết, không còn cần**: có thể được dọn/tái sử dụng bởi cơ chế quản lý lưu trữ.

Một giao dịch mở lâu, nhất là giao dịch giữ snapshot cũ, có thể cản trở việc thu dọn các phiên bản mà nó còn có khả năng nhìn thấy. Với PostgreSQL, ngoài giao dịch dài còn có các nguyên nhân khác giữ lại thông tin cần thiết như replication slot hay cơ chế tương tự; cần phân tích số liệu DB trước khi kết luận nguyên nhân.

Hậu quả vận hành có thể gồm **table/index bloat**, thêm I/O và áp lực lưu trữ, tốc độ dọn dẹp kém hoặc các vấn đề quản lý transaction ID. Không nên chỉ tập trung vào thời gian chạy từng SELECT rồi bỏ qua thời gian giữ transaction mở.

### 12.1. Đọc snapshot lâu có thể gây rủi ro mà không hề ghi dữ liệu

Ví dụ một API mở REPEATABLE READ, đọc danh sách đơn hàng, chờ yêu cầu HTTP khác rồi mới commit:

~~~text
BEGIN REPEATABLE READ
   |
SELECT danh sách đơn
   |
Chờ gọi API ngoài / chờ người dùng / xử lý lâu
   |
COMMIT
~~~

Snapshot và các tài nguyên liên quan có thể được giữ suốt thời gian đó. Tốt hơn là tổ chức giao dịch đọc trong phạm vi ngắn, đóng connection ngay sau khi lấy dữ liệu cần thiết và xử lý phần ngoài DB sau. Nếu nghiệp vụ yêu cầu góc nhìn nhất quán cho báo cáo dài, cần lựa chọn chiến lược phù hợp về snapshot, timeout, tài nguyên và tải hệ thống.

### 12.2. Snapshot MVCC không phải sao lưu

Một snapshot phục vụ truy vấn MVCC **không phải bản backup có thể phục hồi**. Backup nhất quán, WAL/redo log, snapshot ở hệ thống file và point-in-time recovery có mục tiêu và cơ chế riêng. Snapshot truy vấn cũng không tự bảo đảm ứng dụng có thể quay lại đọc phiên bản của tuần trước. Không đánh đồng “cơ sở dữ liệu có nhiều phiên bản” với “lưu lịch sử vô hạn”.

## 13. Hai SELECT có thể mâu thuẫn về mặt nghiệp vụ như thế nào?

Giả sử trang quản trị cần hiển thị **số đơn** và **tổng doanh thu** theo tenant:

~~~sql
SELECT count(*) AS order_count
FROM orders
WHERE tenant_id = 10;

SELECT coalesce(sum(amount), 0) AS total_amount
FROM orders
WHERE tenant_id = 10;
~~~

Ở READ COMMITTED, giữa hai SELECT một giao dịch khác có thể thêm hoặc xóa đơn và commit. Khi đó **order_count** và **total_amount** đến từ **hai trạng thái đã commit khác nhau**, dù từng câu SELECT riêng lẻ hợp lệ.

Có ba hướng xử lý tùy yêu cầu:

1. **Gộp trong một câu truy vấn** khi khả thi, để cả hai phép tính sử dụng cùng snapshot của câu lệnh:

   ~~~sql
   SELECT count(*) AS order_count,
          coalesce(sum(amount), 0) AS total_amount
   FROM orders
   WHERE tenant_id = 10;
   ~~~

2. **Dùng transaction REPEATABLE READ ngắn** khi cần nhiều truy vấn riêng nhưng muốn một góc nhìn thống nhất.
3. **Chấp nhận độ trễ/khác biệt giữa các phép đo** nếu chỉ dùng cho dashboard tham khảo, và ghi rõ ngữ nghĩa thời điểm dữ liệu.

Không nên mở transaction dài chỉ vì tiện gộp hai câu SQL nếu thực tế có thể viết một câu truy vấn rõ ràng hơn.

## 14. JDBC: đọc nhiều câu lệnh từ một snapshot nhất quán

Giả sử **orders(tenant_id, amount)** chứa đơn đã xác định ý nghĩa doanh thu; bài này tập trung vào việc **hai phép tổng hợp dùng cùng snapshot**, không tự định nghĩa quy tắc ghi nhận doanh thu. Đoạn mã dưới đây dùng JDBC với một connection và chế độ REPEATABLE READ:

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class OrderReportRepository {
    private final DataSource dataSource;

    public OrderReportRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public record OrderTotals(long count, BigDecimal amount) {}

    public OrderTotals readConsistentTotals(long tenantId) throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            // Đặt isolation trước khi bắt đầu giao dịch mới.
            connection.setTransactionIsolation(
                    Connection.TRANSACTION_REPEATABLE_READ);
            connection.setAutoCommit(false);

            try {
                long count;
                try (PreparedStatement st = connection.prepareStatement(
                        "SELECT count(*) FROM orders WHERE tenant_id = ?")) {
                    st.setLong(1, tenantId);
                    try (ResultSet rs = st.executeQuery()) {
                        rs.next();
                        count = rs.getLong(1);
                    }
                }

                BigDecimal amount;
                try (PreparedStatement st = connection.prepareStatement(
                        """
                        SELECT coalesce(sum(amount), 0)
                        FROM orders
                        WHERE tenant_id = ?
                        """)) {
                    st.setLong(1, tenantId);
                    try (ResultSet rs = st.executeQuery()) {
                        rs.next();
                        amount = rs.getBigDecimal(1);
                    }
                }

                connection.commit();
                return new OrderTotals(count, amount);
            } catch (SQLException | RuntimeException failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            }
        }
    }
}
~~~

**Vì sao cách này có ý nghĩa?**

- Cả hai SELECT sử dụng **cùng connection và cùng giao dịch**.
- Ở PostgreSQL REPEATABLE READ, cả hai SELECT thông thường quan sát một snapshot ổn định (ngoài các thay đổi do chính giao dịch tạo ra, mà ví dụ này không có).
- SQL dùng **PreparedStatement**, nên giá trị tenant không được ghép vào chuỗi SQL.
- Kết thúc bằng **commit** dù đây là giao dịch chỉ đọc, nhằm đóng ranh giới giao dịch một cách tường minh; nếu có lỗi, gọi **rollback** và giữ exception gốc.

Trong ứng dụng thực tế, truy cập tenant phải đi kèm **xác thực/ủy quyền**; snapshot không giới hạn dữ liệu mà tài khoản DB được phép đọc. Khi dùng pool, cần bảo đảm cấu hình quản lý connection khôi phục isolation và auto-commit trước khi tái sử dụng. Connection trong ví dụ do method sở hữu và được đóng ở cuối; nếu connection do framework/transaction manager quản lý thì để thành phần đó điều phối transaction. Không tự đổi isolation của một giao dịch đang chạy mà chưa nắm rõ quy tắc của driver và DBMS.

### 14.1. Khi nào một giao dịch đọc cần retry?

Ở PostgreSQL, giao dịch REPEATABLE READ **chỉ đọc** với SELECT thông thường không gặp tranh chấp cập nhật hàng như một giao dịch ghi; tuy nhiên lỗi hạ tầng, timeout, hủy truy vấn hoặc chính sách transaction khác vẫn có thể khiến thao tác thất bại. Trong SERIALIZABLE, retry có thể cần thiết cho lỗi **40001**, kể cả với hoạt động đọc tùy quan hệ phụ thuộc và cách hệ quản trị quản lý giao dịch. Không tái thực hiện hàng loạt thao tác bên ngoài (gửi email/thanh toán) chỉ vì DB trả về lỗi retryable.

## 15. Spring: đặt isolation ở ranh giới nghiệp vụ

Nếu ứng dụng dùng Spring transaction manager phù hợp với DataSource/JPA, mức cô lập có thể khai báo ở service:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderReportService {
    private final OrderReportDao dao;

    public OrderReportService(OrderReportDao dao) {
        this.dao = dao;
    }

    @Transactional(
        isolation = Isolation.REPEATABLE_READ,
        readOnly = true
    )
    public ReportSnapshot loadReport(long tenantId) {
        long count = dao.countOrders(tenantId);
        java.math.BigDecimal total = dao.sumOrders(tenantId);
        return new ReportSnapshot(count, total);
    }
}
~~~

Ví dụ giả định **OrderReportDao** tham gia transaction manager của Spring và **ReportSnapshot** là kiểu dữ liệu do ứng dụng định nghĩa. Annotation chỉ phát huy tác dụng nếu method được gọi qua cơ chế quản lý giao dịch đang dùng. Với **Spring proxy** thông thường, lời gọi nội bộ bằng **this.loadReport(...)** từ cùng bean không đi qua proxy; truy vấn có thể không nằm trong giao dịch kỳ vọng.

Các điểm cần chú ý:

- Mức cô lập mới thường được áp dụng khi **mở transaction mới**. Khi method tham gia một transaction đã tồn tại với propagation **REQUIRED**, khai báo isolation ở method bên trong có thể không thay đổi isolation của transaction cha; muốn kiểm tra sự khác biệt có thể cấu hình transaction manager để xác thực các thuộc tính transaction hiện có.
- **readOnly = true** là một tín hiệu cho framework/driver tối ưu, có thể thay đổi flush behavior hoặc được thực thi mạnh hơn ở cấu hình nhất định; nó **không phải cơ chế phân quyền** và không đảm bảo mọi lệnh ghi đều bị DB từ chối.
- Giao dịch phải bao phủ đúng các DAO/repository thực hiện SQL. Tránh tự mở connection không tham gia transaction ở giữa, hoặc tự commit bên trong DAO.
- Với luồng **async**, thread mới hoặc reactive stack, context transaction có quy tắc truyền riêng. Không giả định một local transaction dựa trên thread tự động đi qua mọi ranh giới thực thi.

## 16. MVCC, phân trang và góc nhìn xuyên nhiều request

Một API gọi **GET /orders?page=1**, sau đó vài giây gọi **GET /orders?page=2**. Nếu mỗi request chạy giao dịch riêng, chúng có thể đọc **hai snapshot khác nhau**. Trong lúc đó, đơn mới được thêm hoặc đơn cũ bị xóa, làm cho phân trang **OFFSET/LIMIT** có thể lặp hoặc bỏ sót bản ghi.

Phân trang theo cursor/keyset với thứ tự duy nhất, ví dụ **(created_at DESC, id DESC)**, thường giảm vấn đề trượt offset và cải thiện hiệu năng:

~~~sql
SELECT id, created_at
FROM orders
WHERE tenant_id = :tenantId
  AND (created_at, id) < (:lastCreatedAt, :lastId)
ORDER BY created_at DESC, id DESC
LIMIT :pageSize;
~~~

Ở PostgreSQL, ví dụ so sánh bộ giả định **created_at, id** không NULL và cả hai sắp giảm dần. **Keyset pagination không biến nhiều request thành một snapshot duy nhất**. Bản ghi có thể thay đổi trạng thái, bị xóa hay cập nhật trường sắp xếp giữa các request. Nếu báo cáo bắt buộc phải tái hiện chính xác một tập dữ liệu, cần thiết kế snapshot/export, lưu tập ID, version dữ liệu hoặc cơ chế báo cáo phù hợp; tránh giữ transaction web mở trong toàn bộ phiên duyệt dữ liệu của người dùng.

## 17. Cách quan sát và chẩn đoán trong PostgreSQL

Khi nghi ngờ câu truy vấn thấy dữ liệu cũ, giao dịch giữ snapshot quá lâu hoặc nhiều writer tranh chấp, có thể kiểm tra theo hướng sau trên môi trường được phép:

~~~sql
-- Xem transaction đang mở và tuổi của chúng.
SELECT pid,
       state,
       xact_start,
       now() - xact_start AS transaction_age,
       wait_event_type,
       wait_event
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
~~~

~~~sql
-- Kiểm tra chỉ số dead tuples ở mức thống kê ước lượng.
SELECT relname, n_live_tup, n_dead_tup,
       last_autovacuum, last_vacuum
FROM pg_stat_user_tables
WHERE relname = 'mvcc_accounts';
~~~

Đây là ví dụ về cách **đọc số liệu**, không phải câu lệnh để tự động can thiệp vào transaction khác. Quyền xem thông tin phiên khác có thể bị giới hạn theo vai trò kết nối. **n_dead_tup** là số ước lượng, không phải bản kiểm kê chính xác mọi tuple chưa được dọn.

Khi phân tích cần đối chiếu:

1. **Transaction boundary:** BEGIN/COMMIT/ROLLBACK ở đâu, connection nào, có request nào giữ transaction idle lâu không?
2. **Isolation thực tế:** driver, DataSource, ORM và transaction manager cấu hình gì; liệu method có thật sự tham gia transaction?
3. **Snapshot được xác lập lúc nào:** ở PostgreSQL REPEATABLE READ là khi câu lệnh cần snapshot đầu tiên chạy; dữ liệu từ giao dịch khác có thể commit trước hoặc sau mốc đó.
4. **Lệnh đọc loại nào:** SELECT thông thường hay khóa tường minh; có query từ replica hoặc cache không?
5. **Xung đột ghi và lỗi:** có SQLSTATE **40001**, **40P01** (deadlock) hay timeout? Cần phân biệt lỗi ghi với dữ liệu snapshot nhìn thấy.
6. **Tác động vận hành:** giao dịch dài, lưu lượng cập nhật, vacuum, dead tuples và tỷ lệ đọc/ghi ảnh hưởng hiệu năng ra sao?

Nếu ứng dụng đọc dữ liệu từ **read replica**, độ trễ sao chép còn có thể làm kết quả khác với primary. Đó là một trục nhất quán khác với snapshot trong transaction nội bộ trên một DB; cần kiểm tra nơi thực sự thực thi truy vấn.

## 18. Các ngộ nhận cần tránh

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “MVCC là không dùng khóa.” | MVCC giúp nhiều truy vấn đọc và ghi ít phải chờ nhau; writer, locking read và DDL vẫn có khóa |
| “BEGIN là chụp ảnh tất cả bảng ngay lập tức.” | Snapshot là thông tin hiển thị, không phải sao chép toàn bộ bảng; thời điểm lấy còn tùy DBMS/isolation |
| “READ COMMITTED bảo đảm hai SELECT trong transaction cùng thấy một trạng thái.” | PostgreSQL READ COMMITTED thường dùng snapshot mới cho mỗi câu lệnh |
| “REPEATABLE READ bảo đảm mọi quyết định đọc rồi ghi đều đúng.” | Snapshot ổn định vẫn có thể dẫn đến write skew nếu nhiều transaction sửa các hàng khác nhau |
| “SERIALIZABLE nghĩa là mọi giao dịch bị khóa để chạy lần lượt.” | PostgreSQL SSI cho phép đồng thời và có thể hủy giao dịch khi phát hiện lịch không thể tuần tự hóa |
| “Snapshot là backup có thể khôi phục mọi phiên bản lịch sử.” | MVCC và cơ chế backup/PITR phục vụ mục đích khác nhau |
| “Đã dùng @Transactional là chắc chắn cùng snapshot.” | Còn phụ thuộc mức cô lập, transaction manager, proxy và việc các DAO có thực sự tham gia giao dịch |
| “Chỉ cần retry câu UPDATE thất bại khi gặp 40001.” | Phải chạy lại toàn bộ transaction, gồm bước đọc và quyết định nghiệp vụ |
| “MVCC tự ngăn hai request tạo đơn trùng.” | Cần unique constraint, idempotency key hoặc biện pháp cụ thể phù hợp bất biến |

## 19. Bài tập tự kiểm tra

### Bài 1. Hai lần đọc dưới READ COMMITTED

T1 mở transaction, đọc **balance = 1000**. T2 cập nhật số dư thành **900** và commit. T1 chạy lại SELECT trên cùng hàng. Với PostgreSQL READ COMMITTED, T1 đọc được gì?

**Gợi ý đáp án:** Thông thường là **900** vì SELECT thứ hai nhận snapshot mới khi bắt đầu, sau commit của T2. Nếu T2 chưa commit lúc SELECT bắt đầu, truy vấn vẫn không thấy phiên bản chưa commit.

### Bài 2. Thời điểm lấy snapshot

T1 gửi **BEGIN ISOLATION LEVEL REPEATABLE READ** rồi chưa truy vấn bảng. T2 thay đổi một hàng và commit. Sau đó T1 mới chạy SELECT đầu tiên. T1 có buộc phải thấy phiên bản trước T2 không?

**Gợi ý đáp án:** Không. Với PostgreSQL REPEATABLE READ, snapshot được lấy khi câu lệnh cần snapshot đầu tiên chạy; commit của T2 diễn ra trước đó nên có thể hiển thị.

### Bài 3. Hai bác sĩ cùng rời ca

T1 và T2 đều đếm có hai bác sĩ trực từ snapshot riêng. Mỗi transaction cập nhật một hàng khác nhau thành không trực. Tại sao REPEATABLE READ có thể để lại 0 bác sĩ, và cách sửa?

**Gợi ý đáp án:** Đây là **write skew**; từng transaction đọc một điều kiện trên tập hàng nhưng ghi các hàng khác nhau. Có thể dùng SERIALIZABLE với retry hoặc đồng bộ việc quyết định qua một hàng khóa chung, cộng với thiết kế ràng buộc và kiểm thử nghiệp vụ.

### Bài 4. Báo cáo gồm hai phép tổng hợp

Một endpoint thực hiện SELECT COUNT rồi SELECT SUM ở READ COMMITTED, giữa hai câu SQL có đơn hàng mới được commit. Tại sao số lượng và tổng tiền không khớp cùng một thời điểm?

**Gợi ý đáp án:** Hai câu lệnh lấy hai snapshot khác nhau. Gộp thành một SELECT hoặc dùng transaction REPEATABLE READ ngắn nếu bắt buộc nhiều SELECT cùng một góc nhìn.

### Bài 5. Một truy vấn chỉ đọc nhưng giao dịch mở 30 phút

Trong PostgreSQL, dịch vụ giữ một transaction REPEATABLE READ mở rất lâu dù sau SELECT không xử lý thêm SQL. Điều gì có thể bị ảnh hưởng?

**Gợi ý đáp án:** Snapshot cũ có thể làm chậm thu hồi các phiên bản cũ còn cần thiết; connection cũng bị giữ lâu, gây áp lực pool và có thể góp phần tăng bloat. Cần kết thúc transaction sớm và quan sát số liệu thực tế.

### Bài 6. SERIALIZABLE trả về SQLSTATE 40001

Ứng dụng nhận lỗi serialization failure sau khi đọc rồi ghi dữ liệu. Có thể chỉ chạy lại UPDATE cuối mà giữ nguyên quyết định cũ không?

**Gợi ý đáp án:** Không. Retry toàn bộ transaction, bao gồm đọc điều kiện và ra quyết định mới, với giới hạn số lần thử và bảo vệ idempotency cho tác dụng phụ ngoài DB.

## 20. Ghi nhớ khi thiết kế persistence cho Java

**MVCC** cho phép một truy vấn nhìn thấy **phiên bản phù hợp của dữ liệu** thay vì buộc mọi lần đọc phải chờ mọi lần ghi. **Snapshot** là căn cứ để chọn phiên bản được thấy; **isolation level** quyết định snapshot được lấy lại theo từng câu SQL hay duy trì trong một giao dịch và DB phải ngăn những bất thường đồng thời nào. **READ COMMITTED** phù hợp nhiều tác vụ ngắn nhưng không cho góc nhìn ổn định xuyên nhiều SELECT. **REPEATABLE READ** cho snapshot ổn định trong PostgreSQL, nhưng vẫn có thể xảy ra **write skew**. **SERIALIZABLE** bổ sung bảo đảm tương đương lịch tuần tự, đổi lại có thể phải retry.

Khi triển khai thực tế, luôn thiết kế **ranh giới transaction**, **bất biến nghiệp vụ**, **ràng buộc dữ liệu** và **chiến lược xử lý xung đột** cùng nhau. Giữ giao dịch ngắn, kiểm tra số hàng cập nhật, chọn khóa hoặc atomic UPDATE khi cần, và xác minh hành vi trên đúng DBMS, driver cùng transaction manager mà ứng dụng Java sử dụng.

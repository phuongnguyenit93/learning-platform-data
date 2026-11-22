# Đọc ảnh chụp không đồng nghĩa với bảo vệ bất biến nhiều hàng

MVCC cho phép một giao dịch đọc một ảnh chụp dữ liệu nhất quán (*snapshot*) mà không phải chặn mọi giao dịch đang ghi. Cơ chế này cải thiện khả năng chạy đồng thời, nhưng một ảnh chụp nhất quán không tự bảo đảm rằng các quyết định dựa trên ảnh chụp đó sẽ giữ đúng mọi quy tắc nghiệp vụ liên quan đến nhiều hàng.

Một tình huống dễ gặp là **write skew**: hai giao dịch cùng đọc một trạng thái hợp lệ, mỗi giao dịch sửa một hàng khác nhau, rồi cả hai cùng commit. Vì chúng không ghi đè cùng một hàng, hệ quản trị có thể không thấy xung đột ghi trực tiếp. Tuy vậy, kết quả kết hợp của hai giao dịch lại vi phạm một bất biến toàn cục.

## 1. Ảnh chụp MVCC bảo đảm điều gì?

MVCC (*Multi-Version Concurrency Control*) lưu nhiều phiên bản của một hàng trong một khoảng thời gian. Khi giao dịch đọc, hệ quản trị chọn phiên bản phù hợp với snapshot của giao dịch. Nhờ vậy, thao tác đọc thông thường có thể tiếp tục trong lúc giao dịch khác tạo phiên bản mới, thay vì luôn phải chờ khóa ghi.

Snapshot giúp câu truy vấn nhìn thấy một trạng thái dữ liệu nhất quán theo quy tắc của isolation level đang dùng. Phạm vi thời gian của snapshot phụ thuộc hệ quản trị và mức cô lập:

- Ở mức đọc đã commit (**READ COMMITTED**), nhiều hệ quản trị tạo snapshot mới cho mỗi câu lệnh đọc. Hai câu SELECT trong cùng transaction có thể nhìn thấy hai trạng thái đã commit khác nhau.
- Ở mức đọc lặp lại hoặc snapshot (**REPEATABLE READ / SNAPSHOT**), các lần đọc nhất quán thường dùng cùng một snapshot trong suốt transaction.
- Ở mức tuần tự hóa (**SERIALIZABLE**), hệ quản trị phải bảo đảm kết quả của các transaction tương đương với một thứ tự chạy tuần tự hợp lệ. Hệ thống có thể khóa, chờ hoặc hủy một transaction để giữ bảo đảm này.

Điểm quan trọng là snapshot mô tả **dữ liệu mà giao dịch được phép nhìn thấy**. Nó không tự khóa mọi hàng có liên quan đến một điều kiện nghiệp vụ, cũng không tự bảo đảm rằng nhiều giao dịch đang dùng cùng snapshot sẽ đưa ra các quyết định tương thích với nhau.

## 2. Bất biến nhiều hàng là gì?

Bất biến (*invariant*) là một điều kiện phải luôn đúng đối với dữ liệu đã commit. Có những bất biến chỉ liên quan đến một hàng, ví dụ số dư không được âm. Có những bất biến phụ thuộc vào quan hệ giữa nhiều hàng:

- Mỗi ca trực phải có ít nhất một bác sĩ đang trực.
- Tổng số tiền phân bổ cho các hạng mục không được vượt ngân sách của dự án.
- Một phòng họp không được có hai lượt đặt chỗ giao nhau về thời gian.
- Số lượng chỗ đã xác nhận không được vượt sức chứa của sự kiện.
- Một tài khoản không thể bị đồng thời rút tiền bởi nhiều nghiệp vụ nếu tổng số tiền rút vượt hạn mức chung.

Các bất biến dạng này thường được diễn đạt bằng một điều kiện trên tập hàng, chẳng hạn COUNT(*), SUM(...), hoặc sự tồn tại của ít nhất một hàng thỏa điều kiện. Một transaction có thể đọc tất cả hàng cần thiết và thấy điều kiện đang đúng. Nhưng nếu transaction khác cũng đọc cùng trạng thái rồi thay đổi một phần khác của tập hàng, hai quyết định riêng lẻ vẫn có thể làm điều kiện sai sau khi cùng commit.

## 3. Write skew: hai giao dịch cùng làm mất bác sĩ trực cuối cùng

Giả sử một ca trực có hai bác sĩ. Quy tắc nghiệp vụ là:

> Mỗi ca trực phải luôn có ít nhất một bác sĩ ở trạng thái đang trực.

Bảng dữ liệu minh họa:

~~~sql
CREATE TABLE doctor_shift (
    shift_id  BIGINT  NOT NULL,
    doctor_id BIGINT  NOT NULL,
    on_call   BOOLEAN NOT NULL,
    PRIMARY KEY (shift_id, doctor_id)
);
~~~

Dữ liệu ban đầu của ca trực 42:

| shift_id | doctor_id | on_call |
|---:|---:|---|
| 42 | 1 | TRUE |
| 42 | 2 | TRUE |

Hai giao dịch chạy đồng thời ở mức cô lập snapshot. Cả hai đều kiểm tra số bác sĩ đang trực trước khi thay đổi dữ liệu.

**Giao dịch T1:**

~~~sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*)
FROM doctor_shift
WHERE shift_id = 42
  AND on_call = TRUE;

-- T1 thấy có 2 bác sĩ đang trực.
-- Ứng dụng cho phép bác sĩ 1 kết thúc ca trực.

UPDATE doctor_shift
SET on_call = FALSE
WHERE shift_id = 42
  AND doctor_id = 1;

COMMIT;
~~~

**Giao dịch T2:**

~~~sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*)
FROM doctor_shift
WHERE shift_id = 42
  AND on_call = TRUE;

-- T2 cũng thấy có 2 bác sĩ đang trực.
-- Ứng dụng cho phép bác sĩ 2 kết thúc ca trực.

UPDATE doctor_shift
SET on_call = FALSE
WHERE shift_id = 42
  AND doctor_id = 2;

COMMIT;
~~~

Giả sử hai câu SELECT chạy trước khi một trong hai giao dịch commit. Cả T1 và T2 đều đọc snapshot có hai bác sĩ đang trực. T1 cập nhật hàng của bác sĩ 1; T2 cập nhật hàng của bác sĩ 2.

| Thứ tự | T1 | T2 |
|---|---|---|
| 1 | Đọc snapshot: có 2 bác sĩ trực | |
| 2 | | Đọc cùng trạng thái: có 2 bác sĩ trực |
| 3 | Đặt bác sĩ 1 thành FALSE | |
| 4 | | Đặt bác sĩ 2 thành FALSE |
| 5 | Commit | |
| 6 | | Commit |

Hai giao dịch ghi vào **hai hàng khác nhau**. Vì vậy, chúng không nhất thiết tạo ra xung đột ghi trên cùng một hàng. Cả hai có thể commit thành công trong một hệ quản trị và isolation level cho phép write skew.

Trạng thái cuối cùng:

| doctor_id | on_call |
|---:|---|
| 1 | FALSE |
| 2 | FALSE |

Bất biến “mỗi ca trực có ít nhất một bác sĩ đang trực” đã bị vi phạm.

Đây là write skew: mỗi transaction đưa ra quyết định hợp lệ dựa trên snapshot mà nó nhìn thấy, nhưng kết quả kết hợp của các transaction lại không hợp lệ.

## 4. Vì sao không có xung đột ghi mà dữ liệu vẫn sai?

Cần phân biệt tập dữ liệu được đọc và tập dữ liệu được ghi:

- T1 đọc trạng thái của cả ca trực 42 nhưng chỉ ghi hàng bác sĩ 1.
- T2 cũng đọc trạng thái của cả ca trực 42 nhưng chỉ ghi hàng bác sĩ 2.
- Hai tập ghi không giao nhau, nhưng hai quyết định ghi đều phụ thuộc vào cùng một điều kiện trên toàn bộ ca trực.

Nhiều cơ chế snapshot isolation phát hiện hoặc ngăn trường hợp hai giao dịch cùng sửa một hàng theo cách gây mất cập nhật. Nhưng nếu hai giao dịch sửa hai hàng khác nhau, xung đột ghi trực tiếp có thể không xuất hiện. Hệ quản trị không thể suy ra mọi quan hệ nghiệp vụ giữa các hàng chỉ từ việc quan sát các hàng bị cập nhật.

Có thể hình dung như sau:

~~~mermaid
flowchart TD
    S["Snapshot ban đầu: bác sĩ 1 và 2 đều đang trực"]
    S --> T1["T1 đọc điều kiện: còn 2 người"]
    S --> T2["T2 đọc điều kiện: còn 2 người"]
    T1 --> W1["T1 cập nhật hàng bác sĩ 1"]
    T2 --> W2["T2 cập nhật hàng bác sĩ 2"]
    W1 --> C["Cả hai transaction commit"]
    W2 --> C
    C --> I["Kết quả: không còn bác sĩ nào trực"]
~~~

Snapshot vẫn nhất quán. Vấn đề nằm ở chỗ hệ thống đã cho phép hai hành động độc lập dựa trên cùng một điều kiện toàn cục mà không có bước phối hợp để bảo vệ điều kiện đó.

## 5. Phân biệt write skew với các lỗi đồng thời khác

| Hiện tượng | Đặc điểm | Ví dụ |
|---|---|---|
| Dirty read | Đọc dữ liệu chưa commit của transaction khác | T2 đọc số dư do T1 cập nhật, sau đó T1 rollback |
| Non-repeatable read | Đọc lại cùng hàng trong một transaction và nhận giá trị khác | T1 đọc số dư, T2 cập nhật và commit, T1 đọc lại |
| Lost update | Hai giao dịch cùng cập nhật một giá trị; một thay đổi có thể ghi đè thay đổi kia | Hai giao dịch cùng đọc số lượng 10 rồi cùng ghi 9 |
| Write skew | Các giao dịch đọc cùng điều kiện trên nhiều hàng nhưng ghi những hàng khác nhau | Hai bác sĩ cùng kết thúc ca trực dựa trên snapshot có hai người |

Write skew đặc biệt khó nhận ra vì log có thể cho thấy mỗi câu UPDATE đều thành công và không có hàng nào bị ghi đè. Muốn phát hiện lỗi, cần kiểm tra bất biến sau khi xét kết quả kết hợp của các giao dịch.

## 6. Hành vi phụ thuộc isolation level và hệ quản trị

Không nên đồng nhất mọi mức REPEATABLE READ hoặc mọi chế độ MVCC giữa các hệ quản trị. Tên mức cô lập tương tự không bảo đảm cách triển khai hoàn toàn giống nhau.

| Hệ quản trị | Snapshot/read behavior | Bảo vệ bất biến nhiều hàng |
|---|---|---|
| PostgreSQL | REPEATABLE READ dùng snapshot cấp transaction và có thể cho phép write skew khi các giao dịch sửa những hàng khác nhau. | SERIALIZABLE dùng Serializable Snapshot Isolation (SSI) để theo dõi phụ thuộc đọc–ghi; hệ thống có thể hủy một transaction khi phát hiện nguy cơ không thể tuần tự hóa. |
| MySQL InnoDB | REPEATABLE READ dùng read view cho consistent read. Locking read và câu lệnh ghi có quy tắc đọc phiên bản hiện hành riêng. | SERIALIZABLE cung cấp mức cô lập mạnh hơn; khóa hàng và khóa phạm vi phụ thuộc truy vấn, chỉ mục và cách thực thi. |
| SQL Server | SNAPSHOT cho transaction đọc phiên bản nhất quán. READ_COMMITTED_SNAPSHOT cung cấp snapshot ở phạm vi câu lệnh khi dùng READ COMMITTED. | SERIALIZABLE dùng khóa để ngăn các thay đổi xung đột, bao gồm key-range lock khi cần bảo vệ phạm vi truy vấn. |

Với PostgreSQL, REPEATABLE READ có hành vi gần với snapshot isolation và ví dụ bác sĩ trực có thể xảy ra. SERIALIZABLE bổ sung kiểm tra phụ thuộc để phát hiện những lịch chạy không thể tương đương với thứ tự tuần tự.

Với SQL Server, SNAPSHOT có thể phát hiện xung đột khi hai transaction cập nhật cùng một hàng đã thay đổi kể từ snapshot của chúng. Điều đó không đồng nghĩa mọi write skew trên các hàng khác nhau đều bị phát hiện. READ_COMMITTED_SNAPSHOT cũng không tương đương với transaction-level SNAPSHOT: snapshot của nó gắn với từng câu lệnh.

Với InnoDB, cần phân biệt consistent read thông thường với locking read như SELECT ... FOR UPDATE. Hai loại đọc có thể nhìn phiên bản dữ liệu khác nhau trong cùng một transaction tùy isolation level. Khi điều tra, hãy xác định chính xác câu lệnh, chỉ mục, isolation level và loại khóa thực tế.

## 7. Cách bảo vệ bất biến nhiều hàng

Không có một kỹ thuật duy nhất phù hợp với mọi bất biến. Cần chọn cơ chế phối hợp phù hợp với điều kiện nghiệp vụ và hệ quản trị.

### 7.1. Dùng SERIALIZABLE khi cần kết quả tương đương chạy tuần tự

Nếu quyết định của transaction phụ thuộc vào một điều kiện trên nhiều hàng, SERIALIZABLE là lựa chọn tổng quát để yêu cầu hệ quản trị bảo vệ tính đúng đắn của lịch chạy.

Ví dụ trên PostgreSQL:

~~~sql
BEGIN ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*)
FROM doctor_shift
WHERE shift_id = 42
  AND on_call = TRUE;

-- Chỉ cho phép kết thúc ca nếu số người đang trực lớn hơn 1.
UPDATE doctor_shift
SET on_call = FALSE
WHERE shift_id = 42
  AND doctor_id = 1
  AND on_call = TRUE;

COMMIT;
~~~

Nếu một lịch chạy đồng thời tạo ra write skew, PostgreSQL SSI có thể hủy một transaction bằng lỗi serialization failure. Ứng dụng phải bắt lỗi này và chạy lại toàn bộ transaction trong một transaction mới.

Cách xử lý ở các hệ quản trị khác có thể là chờ khóa, phát hiện deadlock hoặc trả về lỗi serialization. Hãy dựa vào mã lỗi cụ thể của driver và hệ quản trị.

SERIALIZABLE có thể làm giảm khả năng chạy đồng thời hoặc tăng số lần transaction phải thử lại. Mức này cũng không loại bỏ mọi deadlock do thứ tự lấy khóa. Nó cung cấp bảo đảm về kết quả tuần tự hóa; ứng dụng vẫn phải xử lý các lần transaction bị hủy.

### 7.2. Khóa một hàng điều phối chung trước khi kiểm tra điều kiện

Một cách khác là tạo hàng khóa điều phối (*guard row*) cho mỗi nhóm dữ liệu cần bảo vệ. Mọi transaction thay đổi trạng thái của nhóm phải khóa hàng điều phối trước, rồi mới đọc điều kiện và cập nhật các hàng chi tiết.

Ví dụ có bảng:

~~~sql
CREATE TABLE shift_guard (
    shift_id BIGINT PRIMARY KEY
);
~~~

Mỗi ca trực có đúng một hàng tương ứng trong shift_guard. Với PostgreSQL hoặc MySQL InnoDB ở READ COMMITTED, có thể thực hiện:

~~~sql
BEGIN ISOLATION LEVEL READ COMMITTED;

-- Luôn khóa hàng điều phối trước khi đọc trạng thái ca trực.
SELECT shift_id
FROM shift_guard
WHERE shift_id = 42
FOR UPDATE;

-- Đọc sau khi đã lấy được khóa điều phối.
SELECT COUNT(*)
FROM doctor_shift
WHERE shift_id = 42
  AND on_call = TRUE;

-- Ứng dụng chỉ cập nhật nếu vẫn còn người trực khác.
UPDATE doctor_shift
SET on_call = FALSE
WHERE shift_id = 42
  AND doctor_id = 1
  AND on_call = TRUE;

COMMIT;
~~~

Nếu T1 đã lấy khóa điều phối, T2 phải chờ. Sau khi T1 commit, T2 mới lấy được khóa và đọc trạng thái đã được T1 cập nhật. T2 vì vậy có thể thấy chỉ còn một bác sĩ trực và từ chối yêu cầu kết thúc ca.

Cơ chế này chỉ bảo vệ được bất biến khi **mọi đường ghi liên quan đều tuân theo cùng giao thức**:

1. Lấy khóa hàng điều phối trước.
2. Đọc và kiểm tra điều kiện sau khi đã lấy khóa.
3. Cập nhật các hàng chi tiết.
4. Commit rồi mới nhả khóa.

Không được đọc snapshot hoặc kiểm tra điều kiện trước khi lấy khóa điều phối. Với isolation level dùng snapshot cấp transaction, một lần đọc trước đó có thể khiến lần đọc sau vẫn nhìn snapshot cũ. Cần chọn isolation level và loại đọc phù hợp với hệ quản trị.

SQL Server có cú pháp khóa tương ứng riêng, ví dụ đọc hàng điều phối bằng UPDLOCK để giữ update lock trong transaction. Hãy kiểm tra hint và phạm vi khóa cụ thể theo truy vấn.

### 7.3. Dùng một hàng tổng hợp làm điểm đồng bộ nguyên tử

Nếu bất biến có thể biểu diễn bằng bộ đếm hoặc tổng hợp, có thể lưu giá trị đó ở một hàng điều phối và cập nhật bằng một câu lệnh có điều kiện.

Ví dụ, shift_guard lưu số bác sĩ đang trực:

~~~sql
CREATE TABLE shift_guard (
    shift_id BIGINT PRIMARY KEY,
    on_call_count INTEGER NOT NULL CHECK (on_call_count >= 1)
);
~~~

Khi một bác sĩ muốn kết thúc ca, transaction giảm bộ đếm với điều kiện số lượng vẫn lớn hơn 1:

~~~sql
BEGIN;

UPDATE shift_guard
SET on_call_count = on_call_count - 1
WHERE shift_id = 42
  AND on_call_count > 1;

-- Ứng dụng phải kiểm tra đúng 1 hàng được cập nhật.
-- Nếu không, ROLLBACK vì không được phép giảm thêm.

UPDATE doctor_shift
SET on_call = FALSE
WHERE shift_id = 42
  AND doctor_id = 1
  AND on_call = TRUE;

-- Nếu câu UPDATE hàng bác sĩ không cập nhật đúng 1 hàng,
-- ROLLBACK để hoàn tác cả thay đổi bộ đếm.

COMMIT;
~~~

Các transaction đồng thời đều phải cập nhật cùng hàng shift_guard. Hệ quản trị sẽ điều phối các lần ghi vào hàng này. Transaction thứ hai chỉ có thể giảm bộ đếm sau khi kết quả của lần ghi trước được xử lý; điều kiện on_call_count > 1 được đánh giá trên giá trị phù hợp với quy tắc cập nhật của hệ quản trị. Nếu điều kiện không còn đúng, transaction phải rollback.

Bộ đếm chỉ đáng tin khi mọi thao tác thêm, xóa hoặc đổi trạng thái bác sĩ đều cập nhật nó trong cùng transaction. Nếu có luồng cập nhật trực tiếp doctor_shift mà bỏ qua shift_guard, hai nguồn dữ liệu có thể lệch nhau. Cần có quy ước ghi thống nhất, kiểm tra quyền ghi hoặc đóng gói thao tác trong một stored procedure/service phù hợp.

Cách này hữu ích khi một điều kiện tổng hợp được truy cập thường xuyên. Đổi lại, hàng tổng hợp có thể trở thành điểm tranh chấp khi lưu lượng ghi cao.

### 7.4. Dùng constraint khi bất biến có thể diễn đạt trực tiếp

Nên ưu tiên ràng buộc do cơ sở dữ liệu quản lý nếu bất biến phù hợp với các loại constraint có sẵn:

- PRIMARY KEY bảo đảm khóa chính duy nhất.
- UNIQUE bảo đảm không có giá trị hoặc tổ hợp giá trị trùng theo phạm vi ràng buộc.
- FOREIGN KEY bảo đảm quan hệ tham chiếu hợp lệ.
- CHECK bảo đảm điều kiện trên dữ liệu mà constraint hỗ trợ kiểm tra.

Tuy nhiên, CHECK thông thường phù hợp với điều kiện trên một hàng. Không nên giả định rằng một biểu thức CHECK đếm hoặc tổng hợp các hàng khác sẽ bảo vệ được bất biến liên hàng dưới mọi lịch chạy đồng thời. Với điều kiện kiểu “mỗi nhóm phải có ít nhất một hàng đang hoạt động”, cần cơ chế phối hợp như SERIALIZABLE, guard row hoặc bộ đếm nguyên tử.

### 7.5. Không chỉ kiểm tra ở tầng ứng dụng rồi mới ghi

Mẫu sau không đủ an toàn khi có nhiều transaction chạy đồng thời:

1. Ứng dụng SELECT để kiểm tra điều kiện.
2. Ứng dụng thấy điều kiện hợp lệ.
3. Ứng dụng quyết định cho phép cập nhật.
4. Ứng dụng gửi UPDATE sau đó.

Khoảng thời gian giữa bước kiểm tra và bước ghi cho phép một transaction khác thay đổi dữ liệu. Cả hai ứng dụng có thể cùng thấy điều kiện đúng rồi cùng thực hiện hành động làm điều kiện sai.

Kiểm tra nghiệp vụ ở tầng ứng dụng vẫn cần thiết để đưa ra thông báo dễ hiểu. Nhưng việc bảo vệ bất biến phải nằm trong một cơ chế nguyên tử hoặc cơ chế đồng bộ do cơ sở dữ liệu bảo đảm.

## 8. Retry khi hệ quản trị hủy transaction

Khi dùng SERIALIZABLE hoặc các cơ chế khóa, một transaction có thể bị hủy do serialization failure, deadlock hoặc xung đột cập nhật. Đây là một phần của xử lý đồng thời.

Quy trình retry an toàn nên:

1. Nhận diện đúng loại lỗi có thể thử lại từ mã lỗi hoặc exception của hệ quản trị.
2. Rollback hoặc đóng transaction hiện tại.
3. Bắt đầu transaction mới để đọc lại trạng thái mới nhất.
4. Chạy lại toàn bộ thao tác nghiệp vụ, bao gồm bước kiểm tra bất biến.
5. Giới hạn số lần thử và có thể thêm backoff với khoảng chờ tăng dần.
6. Bảo đảm các tác động bên ngoài như gửi email, thu tiền hoặc phát thông điệp không bị thực hiện lặp ngoài ý muốn.

Không chạy lại riêng câu UPDATE trong transaction đã bị hủy. Các quyết định trước đó được đưa ra từ snapshot cũ và cần được tính lại trong transaction mới.

## 9. Cách kiểm thử write skew

Một bài kiểm thử hữu ích cần điều khiển được thời điểm của hai transaction để chúng cùng đọc một snapshot trước khi ghi.

Với ví dụ bác sĩ trực, có thể tổ chức kiểm thử như sau:

1. Chuẩn bị hai hàng bác sĩ cùng có on_call = TRUE.
2. Mở T1 và T2 ở isolation level đang cần kiểm tra.
3. Cho T1 đọc số người đang trực; giữ transaction mở.
4. Cho T2 đọc cùng điều kiện trước khi T1 commit.
5. Cho T1 cập nhật bác sĩ 1.
6. Cho T2 cập nhật bác sĩ 2.
7. Commit cả hai và kiểm tra lại bất biến.

Kết quả mong đợi tùy cơ chế bảo vệ:

- Với snapshot isolation cho phép write skew, kiểm thử có thể cho thấy cả hai commit và bất biến bị vi phạm.
- Với SERIALIZABLE, một transaction có thể phải chờ hoặc bị hủy; sau khi retry, nó phải đọc lại trạng thái và từ chối thao tác nếu chỉ còn một bác sĩ.
- Với guard row, transaction thứ hai phải đợi khóa điều phối rồi kiểm tra trạng thái mới.
- Với bộ đếm nguyên tử, chỉ một lần giảm bộ đếm từ 2 xuống 1 được chấp nhận; lần tiếp theo không được làm thay đổi dữ liệu chi tiết.

Không nên chỉ kiểm thử tuần tự hai lần gọi service. Nếu transaction thứ nhất đã commit trước khi transaction thứ hai đọc, transaction thứ hai sẽ thấy trạng thái mới và không tái hiện write skew.

## 10. Chọn cơ chế theo loại bất biến

| Nhu cầu | Cơ chế phù hợp | Điểm cần quản lý |
|---|---|---|
| Bất biến có thể biểu diễn bằng UNIQUE, FK hoặc CHECK phù hợp | Database constraint | Chọn đúng phạm vi và ngữ nghĩa của constraint |
| Nhiều transaction đọc điều kiện trên nhiều hàng rồi cập nhật | SERIALIZABLE | Xử lý serialization failure và retry toàn bộ transaction |
| Các thao tác thuộc một nhóm cần được tuần tự hóa | Guard row | Mọi writer phải khóa cùng hàng trước khi đọc điều kiện |
| Điều kiện có thể biểu diễn bằng số đếm hoặc tổng hợp | Atomic conditional update trên hàng tổng hợp | Duy trì bộ đếm trong cùng transaction ở mọi luồng ghi |
| Kiểm tra nghiệp vụ cần thông báo thân thiện | Validation ở ứng dụng kết hợp cơ chế nguyên tử | Không dựa riêng vào lần SELECT kiểm tra trước UPDATE |

## 11. Checklist khi thiết kế bất biến nhiều hàng

- [ ] Điều kiện nghiệp vụ có phụ thuộc vào nhiều hàng hoặc một tập hàng được xác định bằng predicate không?
- [ ] Snapshot được tạo ở phạm vi câu lệnh hay transaction?
- [ ] Hai transaction có thể cùng đọc một trạng thái rồi cập nhật các hàng khác nhau không?
- [ ] Isolation level đang dùng có cho phép write skew không?
- [ ] Có thể biểu diễn điều kiện bằng constraint do cơ sở dữ liệu bảo vệ không?
- [ ] Nếu dùng guard row, mọi đường ghi có khóa cùng hàng trước khi đọc điều kiện không?
- [ ] Nếu dùng bộ đếm, mọi thay đổi chi tiết có cập nhật bộ đếm trong cùng transaction không?
- [ ] Nếu dùng SERIALIZABLE, ứng dụng có retry toàn bộ transaction sau lỗi serialization không?
- [ ] Kiểm thử có tạo được hai transaction thực sự chồng lấn và cùng đọc snapshot không?

MVCC giúp các giao dịch đọc dữ liệu nhất quán và giảm việc đọc phải chờ ghi. Nhưng tính nhất quán của một snapshot không đồng nghĩa với việc các quyết định của nhiều transaction sẽ bảo vệ được một bất biến trên nhiều hàng. Khi một quy tắc nghiệp vụ phụ thuộc vào cả tập dữ liệu, cần có cơ chế phối hợp rõ ràng: constraint phù hợp, mức SERIALIZABLE, khóa điều phối chung hoặc một cập nhật nguyên tử trên hàng tổng hợp.

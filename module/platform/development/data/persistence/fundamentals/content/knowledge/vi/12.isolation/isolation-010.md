# Mức SERIALIZABLE và chi phí xử lý xung đột để giữ tính tuần tự tương đương

Trong một ứng dụng Java có tầng **persistence**, các giao dịch thường đọc dữ liệu hiện tại, kiểm tra quy tắc nghiệp vụ rồi ghi kết quả. Khi nhiều giao dịch chạy đồng thời, từng giao dịch có thể đúng nếu chạy riêng lẻ nhưng **kết quả tổng thể lại sai**. Mức cô lập **SERIALIZABLE** giải quyết vấn đề này bằng cách yêu cầu các giao dịch đã commit có hiệu ứng tương đương với **một thứ tự chạy tuần tự hợp lệ**.

Yêu cầu đó có giá: cơ sở dữ liệu phải chặn một số thao tác, theo dõi phụ thuộc, hoặc **hủy giao dịch xung đột để ứng dụng thử lại**, tùy cách triển khai. Bài học thuộc chương **Tính cô lập** trong mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**, liên hệ trực tiếp đến cách Java thiết kế ranh giới transaction, xử lý lỗi, tối ưu truy vấn và kiểm soát đồng thời. Ví dụ chuyên sâu dùng PostgreSQL để minh họa một triển khai cụ thể; các DBMS khác có thể dùng chiến lược khác nhau.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Giải thích **tương đương tuần tự (serial equivalence/serializability)** và phân biệt nó với “chỉ một giao dịch được chạy tại một thời điểm”.
2. Nhận diện tình huống **write skew** mà giao dịch ở mức cô lập thấp hơn có thể không ngăn được.
3. Hiểu vì sao SERIALIZABLE phải xử lý xung đột và vì sao một transaction hợp lệ vẫn có thể bị từ chối lúc commit.
4. Viết giao dịch **SERIALIZABLE** và triển khai **retry toàn bộ transaction** an toàn trong Java.
5. Đánh giá chi phí về khóa, theo dõi phụ thuộc, tỷ lệ retry, thời gian giữ tài nguyên và độ trễ đầu cuối.

## 2. “Tuần tự tương đương” nghĩa là gì?

Giả sử **T1** và **T2** là hai giao dịch, mỗi giao dịch gồm nhiều lần đọc/ghi dữ liệu.

- **Thực thi tuần tự (serial execution):** T1 hoàn thành rồi T2 mới chạy, hoặc ngược lại; hai giao dịch không xen kẽ.
- **Thực thi đồng thời (concurrent execution):** các bước đọc/ghi của T1 và T2 có thể xen kẽ để tận dụng tài nguyên và giảm thời gian chờ.
- **Lịch chạy tuần tự tương đương (serializable schedule):** dù bước thực thi có xen kẽ, hiệu ứng có thể được giải thích như thể những giao dịch đã commit chạy lần lượt theo **một thứ tự nào đó**.

Ví dụ đơn giản: tài khoản có **100 điểm**. T1 cộng 10 điểm, T2 cộng 20 điểm. Nếu hai thao tác tăng đều được thực hiện đúng và ghi nhận như hai transaction, kết quả cuối là 130 điểm, tương thích với thứ tự **T1 → T2** hoặc **T2 → T1**.

Tuy nhiên, **chỉ so kết quả cuối của một cột là chưa đủ** để kiểm tra tính serializable. Cần xét cả kết quả các lần đọc, quyết định dựa trên dữ liệu đã đọc và mối phụ thuộc giữa các transaction. Một lịch chạy có thể trả ra kết quả đọc **không thể xuất hiện trong bất kỳ thứ tự chạy tuần tự nào**.

~~~text
Thực thi tuần tự A:  [ T1: đọc, xử lý, ghi ] [ T2: đọc, xử lý, ghi ]

Thực thi tuần tự B:  [ T2: đọc, xử lý, ghi ] [ T1: đọc, xử lý, ghi ]

Thực thi đồng thời:  T1: đọc ------ xử lý -------- ghi --- commit
                     T2: --- đọc ------ xử lý --- ghi -------- commit

SERIALIZABLE chỉ chấp nhận hiệu ứng có thể quy về một thứ tự tuần tự hợp lệ.
~~~

**SERIALIZABLE không bắt buộc mọi transaction phải đứng chờ nhau từ đầu đến cuối.** DBMS có thể để chúng chạy đồng thời và xử lý các tình huống thật sự xung đột. SERIALIZABLE cũng không tự động có nghĩa là **linearizability/strict serializability**: đó là bảo đảm mạnh hơn về thứ tự thời gian thực giữa các thao tác/giao dịch. Khi hệ thống yêu cầu thứ tự thời gian thực hoặc giao dịch phân tán trên nhiều DB, cần xem chính xác bảo đảm của hạ tầng.

## 3. Ví dụ phản ví dụ: hai bác sĩ cùng rời ca trực

Quy tắc của bệnh viện: **luôn phải có ít nhất một bác sĩ trực**. Có hai người A và B đều đang trực. Mỗi bác sĩ được phép rời ca nếu còn ít nhất một người khác trực.

Bảng minh họa:

~~~sql
-- PostgreSQL
CREATE TABLE duty_doctors (
    id BIGINT PRIMARY KEY,
    on_call BOOLEAN NOT NULL
);

INSERT INTO duty_doctors (id, on_call)
VALUES (101, TRUE), (102, TRUE);
~~~

### 3.1. Hai giao dịch hợp lệ khi chạy riêng

Giao dịch **T1**: bác sĩ 101 xin nghỉ, thấy hai người đang trực, rồi tắt trạng thái trực của mình.

Giao dịch **T2**: bác sĩ 102 làm tương tự.

Nếu chạy T1 xong rồi mới chạy T2:

1. T1 đọc số bác sĩ đang trực là **2**, chuyển bác sĩ 101 thành **FALSE**, rồi commit.
2. T2 đọc số bác sĩ đang trực là **1**, phải từ chối yêu cầu nghỉ, **không được** cập nhật.
3. Kết quả còn bác sĩ 102 trực, quy tắc vẫn đúng.

Thứ tự T2 rồi T1 cho kết quả đối xứng: chỉ một người được nghỉ. **Không có thứ tự tuần tự hợp lệ nào cho phép cả hai cùng nghỉ**, nếu mỗi giao dịch đều thực hiện đúng quy tắc đọc và kiểm tra.

### 3.2. Lỗi write skew khi hai giao dịch cùng đọc ảnh chụp cũ

Hãy xét lịch chạy sau:

| Thời điểm | Giao dịch T1 (bác sĩ 101) | Giao dịch T2 (bác sĩ 102) |
|---|---|---|
| 1 | Bắt đầu, đọc **COUNT(on_call) = 2** | |
| 2 | | Bắt đầu, đọc **COUNT(on_call) = 2** |
| 3 | Cập nhật bác sĩ **101 → FALSE** | |
| 4 | | Cập nhật bác sĩ **102 → FALSE** |
| 5 | COMMIT | |
| 6 | | COMMIT |

Hai giao dịch **ghi hai hàng khác nhau**, nên một cơ chế chỉ ngăn cập nhật đồng thời **cùng một hàng** có thể không phát hiện xung đột nghiệp vụ này. Nếu cả hai commit, số người trực trở thành **0**. Mỗi transaction “đọc đúng tại thời điểm của nó”, nhưng kết quả chung vi phạm bất biến “ít nhất một người trực”.

Đây là **write skew**: các transaction đọc một tập dữ liệu chung để quyết định rồi ghi các hàng khác nhau, khiến những quyết định đồng thời không còn tương thích.

~~~mermaid
flowchart LR
    A["T1 đọc: 2 người trực"] --> B["T1 ghi: bác sĩ 101 nghỉ"]
    C["T2 đọc: 2 người trực"] --> D["T2 ghi: bác sĩ 102 nghỉ"]
    B --> E["Nếu cả hai commit: 0 người trực"]
    D --> E
    E --> F["Vi phạm quy tắc nghiệp vụ"]
~~~

**Ghi chú DBMS:** với PostgreSQL, **REPEATABLE READ** dựa trên snapshot isolation và có thể cho phép lịch chạy kiểu này khi hai transaction cập nhật các hàng khác nhau. Không nên suy rộng kết luận ấy cho mọi cơ sở dữ liệu chỉ từ tên mức cô lập; hiện thực **REPEATABLE READ** giữa các DBMS có thể khác nhau.

## 4. SERIALIZABLE xử lý write skew như thế nào?

Khi cả hai giao dịch ở mức SERIALIZABLE, hệ quản trị phải bảo đảm **những giao dịch được commit** tương đương với một thứ tự tuần tự nào đó. Với ví dụ bác sĩ, nếu cả T1 và T2 cùng đọc số người trực là 2, cùng quyết định nghỉ và cùng thay đổi trạng thái của mình, **không thể để cả hai commit với hiệu ứng ấy**.

Một cách giải quyết là:

1. Cả T1 và T2 được phép đọc, kiểm tra và tiến hành công việc.
2. DBMS nhận ra phụ thuộc đồng thời gây ra lịch không thể tuần tự hóa.
3. DBMS **hủy một giao dịch**, trả lỗi có thể nhận diện (PostgreSQL thường dùng SQLSTATE **40001**, *serialization_failure*).
4. Ứng dụng **rollback nếu cần**, rồi **chạy lại từ đầu** giao dịch bị hủy.
5. Ở lần chạy lại, giao dịch đọc trạng thái mới (chỉ còn một bác sĩ trực) và từ chối yêu cầu nghỉ theo quy tắc nghiệp vụ.

Không có bảo đảm bác sĩ nào “thắng”; kết quả phụ thuộc lịch chạy và cơ chế của DBMS. Lỗi có thể phát sinh trong lúc thực thi câu lệnh hoặc tại **COMMIT**. Một số hệ quản trị cũng dùng khóa để buộc giao dịch chờ, thay vì dựa chủ yếu vào hủy và thử lại.

### 4.1. SERIALIZABLE không thay thế kiểm tra nghiệp vụ

Chỉ nâng mức cô lập không đủ nếu ứng dụng **không đọc/kiểm tra điều kiện** “ít nhất một người trực”, hoặc một con đường ghi khác cố tình bỏ qua quy tắc này. Transaction có thể hoàn toàn serializable nhưng vẫn thực hiện nghiệp vụ sai.

Mục tiêu là kết hợp:

- **Bất biến nghiệp vụ:** tối thiểu một bác sĩ trực.
- **Kiểm tra và cập nhật trong cùng transaction:** đọc COUNT, ra quyết định, cập nhật.
- **Cơ chế cô lập đủ mạnh cho các transaction liên quan:** ngăn kết quả đồng thời vi phạm bất biến.
- **Xử lý retry và kết quả nghiệp vụ:** giao dịch bị hủy không được coi là đã hoàn tất.

Đối với quy tắc có thể diễn đạt bằng **PRIMARY KEY**, **UNIQUE**, **FOREIGN KEY**, **CHECK** hoặc thao tác UPDATE có điều kiện trên cùng một hàng, hãy tận dụng cơ chế đó trước. SERIALIZABLE có ích đặc biệt khi quy tắc phụ thuộc **nhiều hàng hoặc tập kết quả của truy vấn**, khó diễn đạt bằng một ràng buộc hàng đơn lẻ.

## 5. Thực nghiệm SQL trên PostgreSQL

Dùng **hai phiên kết nối SQL riêng biệt** để quan sát cách hai giao dịch xen kẽ. Giả định bảng **duty_doctors** đã được tạo như mục 3 và cả hai hàng có **on_call = TRUE** trước mỗi lượt thử nghiệm.

### 5.1. Thử dưới REPEATABLE READ

**Session A:**

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*) AS on_call_count
FROM duty_doctors
WHERE on_call = TRUE;
-- Mong đợi: 2

-- Chưa COMMIT; chuyển sang Session B để B cũng đọc.
UPDATE duty_doctors
SET on_call = FALSE
WHERE id = 101;

-- COMMIT sau khi Session B đã đọc và ghi hàng của mình.
COMMIT;
~~~

**Session B:**

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*) AS on_call_count
FROM duty_doctors
WHERE on_call = TRUE;
-- Khi cả hai đã có snapshot chứa hai bác sĩ: 2

UPDATE duty_doctors
SET on_call = FALSE
WHERE id = 102;

COMMIT;
~~~

Để tái hiện lịch chạy, **không chạy hết cả Session A rồi mới tới Session B**; hãy dừng các phiên giữa các bước đọc/ghi như bảng thời gian ở mục 3.2. Trong PostgreSQL REPEATABLE READ, nếu hai transaction sử dụng snapshot thích hợp và cập nhật hai hàng khác nhau, cả hai có thể commit, tạo ra write skew.

### 5.2. Đổi sang SERIALIZABLE

Khôi phục dữ liệu thử nghiệm **sau khi các transaction trước đã kết thúc**:

~~~sql
UPDATE duty_doctors SET on_call = TRUE;
~~~

Thực hiện cùng lịch chạy nhưng thay câu lệnh bắt đầu giao dịch ở **cả hai session**:

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;
~~~

Khi hai transaction có mẫu đọc/ghi xung đột như trên, PostgreSQL SSI sẽ ngăn **cả hai cùng commit** thành công. Một bên có thể nhận lỗi tương tự:

~~~text
ERROR: could not serialize access due to read/write dependencies among transactions
SQLSTATE: 40001
~~~

Văn bản lỗi cụ thể và thời điểm phát sinh phụ thuộc tình huống; chương trình **nên phân loại theo SQLSTATE** thay vì khớp nguyên văn chuỗi thông báo.

Thực nghiệm chỉ thể hiện một lịch chạy. Nếu hai transaction không thật sự chồng lấn, chẳng hạn T2 bắt đầu sau khi T1 đã commit và nhìn thấy một người trực, cả hai có thể hoàn tất **không có serialization error**, vì T2 sẽ tự từ chối việc rời ca theo quy tắc.

## 6. Bên trong PostgreSQL: Serializable Snapshot Isolation (SSI)

PostgreSQL hiện thực SERIALIZABLE bằng **Serializable Snapshot Isolation (SSI)**. Đây là một ví dụ tiêu biểu cho chiến lược **cho phép thực thi đồng thời, theo dõi phụ thuộc rồi hủy transaction khi cần**. Không phải mọi DBMS dùng SSI; một số triển khai dùng khóa theo dải, khóa đọc/ghi hoặc cơ chế điều phối khác.

### 6.1. Vì sao “cùng ảnh chụp” chưa đủ?

Snapshot isolation cho transaction thấy một ảnh chụp dữ liệu nhất quán và thường phát hiện xung đột **ghi-ghi** trên cùng hàng. Nhưng write skew ở ví dụ bác sĩ diễn ra qua **đọc-ghi** giữa các hàng:

- T1 đọc rằng bác sĩ 102 còn trực; T2 sau đó ghi trạng thái bác sĩ 102 thành FALSE.
- T2 đọc rằng bác sĩ 101 còn trực; T1 sau đó ghi trạng thái bác sĩ 101 thành FALSE.

Cả hai quyết định đều dựa trên dữ liệu mà transaction còn lại sẽ làm thay đổi. Nếu T1 phải đứng trước T2 để giải thích phụ thuộc thứ nhất, nhưng T2 lại phải đứng trước T1 để giải thích phụ thuộc thứ hai, chúng tạo thành **chu trình phụ thuộc**, không tồn tại thứ tự tuần tự hợp lệ.

~~~text
T1 đọc trạng thái của bác sĩ 102
    \____ (T2 ghi thay đổi dữ liệu T1 đã đọc) ____> T2

T2 đọc trạng thái của bác sĩ 101
    \____ (T1 ghi thay đổi dữ liệu T2 đã đọc) ____> T1

          T1 --------> T2
           ^            |
           |____________|
          Chu trình: không thể tuần tự hóa cả hai
~~~

Trong lý thuyết serializability, đây là dạng **read-write antidependency**. SSI quan sát những quan hệ nguy hiểm và quyết định hủy transaction cần thiết. Mô tả chu trình ở trên giúp hiểu ví dụ; thuật toán SSI thực tế theo dõi **dangerous structures** gồm các phụ thuộc và thông tin commit, phức tạp hơn quy tắc “hễ thấy chu trình trực tiếp thì hủy”.

### 6.2. SIREAD/predicate locking để phát hiện dữ liệu đã đọc

PostgreSQL dùng dấu vết đọc, thường hiển thị là **SIReadLock**, để biết một transaction đã dựa vào dữ liệu hoặc phạm vi truy vấn nào. Khi transaction khác ghi vào dữ liệu đó, DBMS có cơ sở xác định quan hệ đọc-ghi.

Điểm cần phân biệt:

- **SIReadLock không phải khóa đọc thông thường buộc writer phải chờ**. Nó chủ yếu phục vụ phát hiện xung đột SSI.
- Dấu vết có thể gắn ở mức hàng, trang hoặc quan hệ; khi hệ thống thiếu tài nguyên theo dõi chi tiết, phạm vi có thể trở nên rộng hơn.
- Truy vấn quét nhiều hàng hoặc toàn bảng có thể tạo dấu vết đọc rộng và **tăng nguy cơ báo xung đột dư**.
- PostgreSQL có thể hủy transaction vì một lịch sử xung đột có khả năng nguy hiểm, ngay cả khi ứng dụng cho rằng hai yêu cầu “không thực sự tranh chấp”. Đó là **false positive** trong phát hiện bảo thủ, không phải bằng chứng dữ liệu đã hỏng.

SSI giúp tránh việc khóa mọi reader/writer từ đầu nhưng đổi lại cần bộ nhớ, công việc theo dõi xung đột và cơ chế hủy/retry. Dù SIReadLock không chặn ghi theo kiểu shared lock truyền thống, transaction vẫn có thể đợi **khóa ghi, khóa hàng hoặc khóa cấu trúc** vì những lý do khác.

### 6.3. Các điều kiện để lập luận SERIALIZABLE có ý nghĩa

Nếu nhiều đường ghi cùng tác động lên một bất biến, **tất cả các giao dịch liên quan cần dùng cơ chế phối hợp phù hợp**. Trong PostgreSQL, để dựa vào bảo đảm SSI cho ứng dụng, hãy thiết kế các transaction đọc/ghi liên quan cùng sử dụng SERIALIZABLE hoặc có cơ chế bảo vệ khác đủ mạnh. Trộn transaction ở các mức cô lập khác mà không phân tích có thể làm suy yếu giả định nghiệp vụ.

Bảo đảm SERIALIZABLE áp dụng cho các thao tác được cơ sở dữ liệu quản lý trong transaction. Nó **không** tự rollback một email đã gửi, một HTTP call đã thực hiện, hay thao tác trên cơ sở dữ liệu khác nếu không có cơ chế giao dịch/phối hợp bên ngoài.

## 7. Chi phí xử lý xung đột: không có “an toàn miễn phí”

SERIALIZABLE có thể rất phù hợp cho nghiệp vụ quan trọng, nhưng yêu cầu tuần tự tương đương tạo ra chi phí cần đo bằng workload thực tế.

| Loại chi phí | Nguyên nhân | Dấu hiệu quan sát |
|---|---|---|
| **Theo dõi phụ thuộc/khóa** | DBMS phải nhớ tập dữ liệu được đọc và quan hệ xung đột | CPU, bộ nhớ quản lý khóa, truy vấn có phạm vi đọc rộng |
| **Hủy giao dịch** | Một lịch chạy không thể cho phép tất cả commit | Lỗi SQLSTATE **40001**, transaction rollback |
| **Thử lại** | Ứng dụng phải đọc, tính toán và ghi lại từ đầu | Số lần thực thi SQL tăng, độ trễ lớn hơn |
| **Thời gian chờ** | Một số chiến lược SERIALIZABLE dùng khóa/chờ; SSI vẫn có khóa ghi thông thường | Lock wait, connection bận, timeout |
| **Tranh chấp tài nguyên** | Transaction dài giữ snapshot, khóa và connection lâu | Pool cạn, transaction kéo dài, tail latency tăng |
| **Thông lượng giảm** | Nhiều công việc bị hủy hoặc phải chờ | Giao dịch commit/giây thấp dù số lần thử cao |

Không tồn tại quy tắc “SERIALIZABLE luôn chậm hơn X%”. Một workload gần như chỉ đọc, nhiều giao dịch ngắn và ít chồng lấn có thể chịu chi phí rất nhỏ. Trái lại, nhiều giao dịch cùng đọc một tập dữ liệu nóng rồi cập nhật các hàng liên quan có thể tạo nhiều lỗi serialization.

### 7.1. Chi phí kỳ vọng của retry

Giả sử để minh họa, mỗi lần thử transaction có xác suất độc lập **p** bị hủy vì xung đột, còn **1 − p** thành công. Nếu thử lại không giới hạn và xác suất không đổi, số lần thử trung bình để có một thành công là:

\[
E[\text{số lần thử}] = \frac{1}{1-p}
\]

Ví dụ với **p = 0,2**, trung bình lý tưởng là **1,25 lần thử** cho mỗi transaction thành công. Đây **chỉ là mô hình giải thích**: trong hệ thống thật, các lần thử thường **không độc lập**; retry đồng loạt có thể gây va chạm tiếp, giao dịch dài hơn làm tải tăng, và việc giới hạn số lần retry khiến một số yêu cầu phải trả lỗi.

Vì vậy, chỉ nhìn “số transaction cuối cùng thành công” sẽ che giấu nhiều lượt SQL, CPU và I/O đã lãng phí. Cần đo cả **số lần thử**, **tỷ lệ 40001**, **thời gian đến thành công cuối cùng** và **lượng yêu cầu bỏ cuộc sau ngưỡng retry**.

### 7.2. Các mẫu truy vấn làm xung đột dễ tăng

- **Đọc toàn bảng trước khi ghi:** ví dụ đếm toàn bộ hàng có trạng thái TRUE, dù nghiệp vụ chỉ liên quan một nhóm nhỏ.
- **Giao dịch kéo dài:** nhiều thao tác SQL, xử lý Java nặng hoặc gọi dịch vụ mạng trong transaction.
- **Các khóa nóng (hot keys):** nhiều yêu cầu cùng sửa một hàng kiểm soát trạng thái, ví dụ tài khoản tổng hoặc bộ đếm.
- **Quyết định trên tập dữ liệu rộng:** đọc một tập lớn để ra quyết định cập nhật nhỏ khiến nhiều transaction có thể phụ thuộc nhau.
- **Retry ngay và đồng loạt:** tất cả yêu cầu thất bại được gửi lại tức thì, tiếp tục chạm cùng dữ liệu.

Cần cân nhắc riêng: thay việc “đếm tất cả bác sĩ” bằng cách đọc **chỉ các bác sĩ của ca trực cần xét**, có chỉ mục phù hợp, sẽ giảm phạm vi dữ liệu liên quan. Dù vậy, tối ưu chỉ mục không phải cách thay thế bảo đảm transaction.

## 8. Java JDBC: chạy lại toàn bộ transaction khi nhận SQLSTATE 40001

Lỗi serialization là một kết quả dự kiến trong một hệ thống sử dụng SERIALIZABLE dưới tải đồng thời. Đối với PostgreSQL, **SQLSTATE 40001** là tín hiệu thường được dùng để quyết định retry.

**Quy tắc:** sau serialization failure, chạy lại **toàn bộ giao dịch**, gồm **mọi lần đọc dùng để ra quyết định**, không chỉ chạy lại câu UPDATE cuối cùng. Nếu giữ kết quả COUNT cũ, ứng dụng lại ra quyết định dựa trên snapshot đã lỗi thời.

Dưới đây là ví dụ Java dùng JDBC 4.x. Phương thức **leaveDuty** kiểm tra luôn còn ít nhất một bác sĩ trực sau khi người được yêu cầu rời ca. Mỗi lần thử dùng một connection mới từ DataSource, có transaction SERIALIZABLE riêng và tối đa ba lần thử.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class DutyService {
    private static final int MAX_ATTEMPTS = 3;
    private final DataSource dataSource;

    public DutyService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void leaveDuty(long doctorId) throws SQLException {
        for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
            try {
                leaveDutyOnce(doctorId);
                return;
            } catch (SQLException failure) {
                boolean serializationFailure =
                        "40001".equals(failure.getSQLState());

                if (!serializationFailure || attempt == MAX_ATTEMPTS) {
                    throw failure;
                }

                // Một transaction đã thất bại; lần sau mở transaction mới.
                // Production nên dùng bounded backoff + jitter ở đây.
                // KHÔNG tái sử dụng kết quả COUNT hay Connection cũ.
            }
        }
    }

    private void leaveDutyOnce(long doctorId) throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            // Ví dụ này sở hữu transaction mới; không nhận connection
            // đang nằm trong transaction do một tầng khác quản lý.
            if (!connection.getAutoCommit()) {
                throw new SQLException("Connection đã có transaction ngoài");
            }

            int oldIsolation = connection.getTransactionIsolation();
            connection.setTransactionIsolation(
                    Connection.TRANSACTION_SERIALIZABLE);
            connection.setAutoCommit(false);

            boolean transactionEnded = false;
            try {
                int onCallCount;
                try (PreparedStatement query = connection.prepareStatement(
                        "SELECT COUNT(*) FROM duty_doctors WHERE on_call = TRUE");
                     ResultSet result = query.executeQuery()) {
                    result.next();
                    onCallCount = result.getInt(1);
                }

                if (onCallCount <= 1) {
                    throw new IllegalStateException(
                            "Không thể để ca trực không có bác sĩ");
                }

                int updated;
                try (PreparedStatement update = connection.prepareStatement(
                        "UPDATE duty_doctors "
                        + "SET on_call = FALSE "
                        + "WHERE id = ? AND on_call = TRUE")) {
                    update.setLong(1, doctorId);
                    updated = update.executeUpdate();
                }
                if (updated != 1) {
                    throw new IllegalStateException(
                            "Bác sĩ không tồn tại hoặc không còn trực");
                }

                connection.commit();
                transactionEnded = true;
            } catch (SQLException | RuntimeException failure) {
                try {
                    connection.rollback();
                    transactionEnded = true;
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            } finally {
                // Khôi phục khi đã kết thúc giao dịch rõ ràng.
                // Nếu rollback thất bại, không bật auto-commit để tránh
                // vô ý commit phần việc chưa xác định trạng thái.
                if (transactionEnded) {
                    connection.setAutoCommit(true);
                    connection.setTransactionIsolation(oldIsolation);
                }
            }
        }
    }
}
~~~

**Luồng thành công:** transaction đọc số bác sĩ trực, kiểm tra điều kiện, cập nhật đúng một hàng và commit. Nếu một giao dịch đồng thời làm xuất hiện lịch không thể tuần tự hóa, JDBC nhận **SQLException** với SQLSTATE **40001**; code rollback nếu cần, đóng connection ở lượt đó và thử lại từ bước đọc số bác sĩ.

**Luồng bị từ chối nghiệp vụ:** nếu chỉ còn một bác sĩ trực thì phương thức ném **IllegalStateException**; đó là một kết quả nghiệp vụ hợp lệ và **không nên retry mù quáng**. Nếu hết ba lần retry vì 40001, lỗi được đưa lên tầng gọi để trả lỗi tạm thời hoặc sắp xếp thử lại theo chính sách.

**Phạm vi ví dụ:** mã chủ động quản lý connection, transaction và mức cô lập. Trong production cần thêm **backoff ngẫu nhiên có giới hạn**, đo số lần retry, kiểm soát timeout và bảo đảm connection pool có chính sách **reset/discard** kết nối lỗi. Nếu rollback thất bại hoặc trạng thái commit không rõ, không được xem một connection là an toàn để tái sử dụng. Các lỗi khôi phục cấu hình connection cũng cần được ghi nhận và xử lý theo quy tắc của pool. Đoạn mã tập trung minh họa quyết định retry; hệ thống thực tế nên cấu hình pool/framework tương ứng.

### 8.1. Lỗi COMMIT không rõ trạng thái là trường hợp khác

**Serialization failure (40001)** cho biết transaction không được commit như dự kiến, và thích hợp để chạy lại toàn bộ đơn vị công việc sau khi transaction đã được dọn dẹp.

**Lỗi kết nối khi gửi COMMIT** có thể khiến client **không biết** DBMS đã commit trước khi phản hồi mất hay chưa. Không nên coi mọi **SQLException** là 40001 và retry vô điều kiện, đặc biệt với chuyển tiền, đặt hàng hoặc thao tác tính phí.

Với nghiệp vụ có tác dụng không được nhân đôi, sử dụng **operation_id/idempotency key** ổn định được lưu trong cùng transaction, xác minh trạng thái trước khi lặp lại yêu cầu có kết quả commit không rõ. Bên cạnh đó, các side effect ngoài cơ sở dữ liệu (gửi mail, HTTP, publish message) nên được tách khỏi phần có thể retry, ví dụ qua **transactional outbox**.

## 9. Khi dùng Spring: ranh giới retry phải nằm ngoài transaction

Trong Spring, có thể yêu cầu mức cô lập bằng annotation:

~~~java
@Service
public class DutyCommandService {
    private final DutyRepository repository;

    public DutyCommandService(DutyRepository repository) {
        this.repository = repository;
    }

    @Transactional(isolation = Isolation.SERIALIZABLE)
    public void leaveDutyOnce(long doctorId) {
        int count = repository.countOnCall();
        if (count <= 1) {
            throw new IllegalStateException("Phải còn ít nhất một bác sĩ trực");
        }
        if (repository.markOffDuty(doctorId) != 1) {
            throw new IllegalStateException("Không thể cập nhật bác sĩ");
        }
    }
}
~~~

Đây là mã minh họa: các import Spring và hai phương thức **DutyRepository** phải được triển khai trong ứng dụng. Transaction manager thường commit khi method kết thúc; vì thế serialization failure cũng có thể xảy ra **sau khi thân method chạy xong**, ngay tại thời điểm interceptor cố gắng commit.

Do đó:

1. **Lớp gọi bên ngoài transaction** chịu trách nhiệm giới hạn số lượt retry.
2. Mỗi lượt gọi lại **method được @Transactional quản lý qua Spring proxy**, tạo một transaction mới; tránh tự gọi một method annotated từ cùng object khi proxy không được áp dụng.
3. Chỉ retry lỗi được xác định là tạm thời/có thể retry; lớp exception Spring phụ thuộc driver và exception translation. Xác định serialization error bằng mã SQLSTATE/gốc nguyên nhân khi cần.
4. Bảo đảm side effect ở ngoài DB **không bị thực hiện nhiều lần** nếu transaction phải retry.

Nếu dùng **@Retryable** hoặc retry interceptor khác, cần kiểm tra **thứ tự interceptor** để retry bao ngoài toàn bộ transaction. Không trộn commit/rollback thủ công trên connection do Spring đang quản lý.

## 10. Chiến lược giảm xung đột mà vẫn giữ đúng nghiệp vụ

Không có một giải pháp tối ưu cho mọi bài toán. Hãy chọn theo **bất biến dữ liệu, kiểu truy vấn và mức tranh chấp**.

### 10.1. Giữ transaction ngắn

Bắt đầu transaction gần với SQL đầu tiên cần tính nhất quán; kiểm tra/ghi những điều kiện bắt buộc; commit ngay khi đủ thông tin. Tránh giữ transaction mở để gọi HTTP, render PDF, gửi email, đọc file lớn hoặc tính toán không cần khóa dữ liệu.

Trong Java, điều này cũng giảm thời gian giữ JDBC Connection từ pool, thời gian giữ snapshot và xác suất gặp transaction đồng thời.

### 10.2. Thu hẹp tập đọc và có chỉ mục phù hợp

Nếu quy tắc là “ít nhất một bác sĩ trực **trong một ca trực**”, hãy biểu diễn ca trực trong schema và lọc theo **shift_id**, thay vì đếm toàn bệnh viện. Chỉ mục phục vụ truy vấn lọc cụ thể có thể làm giảm số trang cần quét, phạm vi dấu vết đọc và chi phí thực thi.

Ví dụ khi schema có thêm **shift_id**:

~~~sql
-- Ví dụ thiết kế cho mô hình ca trực có shift_id:
SELECT COUNT(*)
FROM duty_doctors
WHERE shift_id = :shift_id AND on_call = TRUE;

-- Cân nhắc chỉ mục phù hợp, sau khi đo truy vấn và tải ghi:
-- CREATE INDEX ... ON duty_doctors(shift_id) WHERE on_call = TRUE;
~~~

Dòng SQL chỉ minh họa biến ràng buộc ở mức ca trực; **shift_id chưa tồn tại trong DDL ở mục 3**, cần cập nhật schema nếu dùng thật. Cú pháp **:shift_id** là named parameter của một số thư viện SQL, không phải cú pháp bind parameter chuẩn của PostgreSQL JDBC; với JDBC thuần sử dụng dấu **?**.

Không tạo chỉ mục chỉ để “chữa SERIALIZABLE” mà không đo **EXPLAIN**, số trang quét, tải ghi và tỷ lệ lỗi 40001.

### 10.3. Tận dụng bất biến tại DB và khóa có chủ đích

Nhiều quy tắc có thể bảo vệ bằng cách đơn giản hơn:

- **UNIQUE** cho yêu cầu mã không được trùng.
- **CHECK** cho điều kiện trên một hàng, như số dư không âm.
- **UPDATE có điều kiện** khi kiểm tra và ghi trên cùng một hàng.
- **Khóa bản ghi điều phối** với **SELECT ... FOR UPDATE**, hoặc cập nhật một hàng tổng đại diện cho tập dữ liệu, nếu được thiết kế để tất cả luồng ghi cùng tuân thủ.

Ví dụ nếu mọi cập nhật ca trực đều phải khóa cùng một hàng đại diện cho ca rồi mới đếm và sửa bác sĩ, các transaction có thể được sắp thứ tự theo khóa đó ngay ở mức cô lập thấp hơn. Cách này có thể **giảm serialization abort nhưng tăng thời gian chờ và điểm nghẽn khóa nóng**. Phải bảo đảm mọi đường ghi đều tuân thủ cùng một giao thức.

### 10.4. Chọn mức cô lập theo nghiệp vụ

| Nhu cầu | Hướng cân nhắc |
|---|---|
| Tra cứu danh mục, đọc thống kê có thể chấp nhận thay đổi trong lúc đọc | Mức cô lập mặc định của DBMS có thể phù hợp; xác định yêu cầu consistency trước |
| Cập nhật đơn hàng theo id với điều kiện được diễn đạt trong một UPDATE | Thao tác nguyên tử/ràng buộc thường quan trọng hơn việc nâng toàn bộ dịch vụ lên SERIALIZABLE |
| Quy tắc liên quan nhiều hàng, dễ gặp write skew hoặc phantom ảnh hưởng quyết định | SERIALIZABLE hoặc giao thức khóa được chứng minh đúng |
| Báo cáo dài, chỉ đọc, cần snapshot nhất quán | Cân nhắc transaction chỉ đọc và mức cô lập phù hợp; tránh giữ snapshot quá lâu |
| Transaction cập nhật hàng nóng với tần suất lớn | Đo chờ khóa, retry và cân nhắc mô hình dữ liệu, phân vùng tải hoặc điều phối |

Không nên mặc định nâng **mọi transaction của toàn ứng dụng** lên SERIALIZABLE nếu phần lớn nghiệp vụ không yêu cầu; việc này có thể thêm chi phí và rủi ro từ lỗi retry ở những luồng chưa được thiết kế để xử lý.

### 10.5. Tối ưu riêng cho giao dịch chỉ đọc

PostgreSQL hỗ trợ chế độ **SERIALIZABLE READ ONLY DEFERRABLE**:

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE READ ONLY DEFERRABLE;

SELECT COUNT(*) FROM duty_doctors WHERE on_call = TRUE;

COMMIT;
~~~

Đối với transaction chỉ đọc, **DEFERRABLE** có thể khiến transaction **đợi một snapshot an toàn** lúc bắt đầu truy vấn để giảm chi phí theo dõi xung đột và tránh serialization failure trong phần đọc sau đó. Cái giá là **thời gian chờ trước khi có thể bắt đầu xử lý**. Đây là tính năng cụ thể của PostgreSQL; không dùng nó cho transaction cần ghi dữ liệu.

## 11. Quan sát và đo chi phí trên hệ thống thật

Để đánh giá hiệu quả, cần đo **đúng tín hiệu** thay vì xem SERIALIZABLE như một hộp đen.

### 11.1. Ở tầng ứng dụng Java

Ghi nhận các metric theo tên nghiệp vụ/truy vấn:

- **transaction_attempts_total**: tổng số lượt thử, gồm lần đầu và retry.
- **transaction_serialization_failures_total**: số lỗi **SQLSTATE 40001**.
- **transaction_retry_exhausted_total**: số yêu cầu hết ngưỡng retry mà chưa thành công.
- **transaction_duration**: độ trễ mỗi attempt và độ trễ **đầu cuối** của yêu cầu tính cả retry.
- **transaction_success_total** và mã lỗi nghiệp vụ: để phân biệt từ chối hợp lệ với xung đột hạ tầng.

Đừng log SQL chứa mật khẩu, token hoặc PII không cần thiết. Có thể gắn **correlation ID** và **operation_id** để đối soát mà không rò rỉ dữ liệu nhạy cảm.

### 11.2. Ở PostgreSQL

Xem thống kê tổng quát theo database:

~~~sql
SELECT
    datname,
    xact_commit,
    xact_rollback,
    deadlocks
FROM pg_stat_database
WHERE datname = current_database();
~~~

**xact_rollback** phản ánh tất cả giao dịch rollback được thống kê, **không phải số lỗi 40001**. **deadlocks** đếm deadlock, không tương đương với serialization failure. Cần kết hợp metric SQLSTATE ở ứng dụng hoặc log cơ sở dữ liệu nếu muốn biết chính xác tần suất serialization failure.

Theo dõi transaction đang mở lâu:

~~~sql
SELECT
    pid,
    state,
    now() - xact_start AS transaction_age,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE datname = current_database()
  AND xact_start IS NOT NULL
ORDER BY xact_start;
~~~

Quan sát dấu vết **SIReadLock** khi cần chẩn đoán SSI:

~~~sql
SELECT locktype, mode, granted, COUNT(*) AS lock_count
FROM pg_locks
WHERE mode = 'SIReadLock'
GROUP BY locktype, mode, granted
ORDER BY lock_count DESC;
~~~

Kết quả **pg_locks** là ảnh chụp tại thời điểm truy vấn; không suy ra tất cả nguyên nhân 40001 chỉ từ số SIReadLock. Quyền truy cập thống kê và mức chi tiết hiển thị còn phụ thuộc quyền người dùng và phiên bản PostgreSQL.

### 11.3. Thí nghiệm tải có kiểm soát

1. Tạo dữ liệu đại diện và xác định **bất biến nghiệp vụ** cần bảo vệ.
2. Chạy nhiều luồng Java trên các nhóm dữ liệu ít tranh chấp rồi tăng dần số luồng cùng truy cập nhóm nóng.
3. Đo cùng lúc **throughput**, tỷ lệ **40001**, số retry/yêu cầu, latency p95/p99 và số kết nối đang bận.
4. So sánh với giải pháp khóa có chủ đích hoặc UPDATE nguyên tử nếu chúng bảo vệ cùng bất biến.
5. Kiểm tra tính đúng của dữ liệu **sau test**; kết quả tốc độ tốt nhưng vi phạm bất biến là không đạt.

Đối với demo hai bác sĩ, bất biến cần khẳng định là **COUNT(*) WHERE on_call = TRUE >= 1** sau mọi transaction đã hoàn tất. Để kiểm chứng nghiêm túc, các lần chạy cần có lịch đồng thời được điều khiển, đủ số lượt thử và ghi nhận trạng thái cuối.

## 12. Các hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| “SERIALIZABLE bắt DB chạy từng transaction một.” | Nó đòi hỏi **hiệu ứng như một thứ tự tuần tự**, vẫn có thể chạy đồng thời. |
| “Không có hai transaction ghi cùng hàng thì không xung đột.” | **Read-write dependency** có thể tạo write skew khi ghi hàng khác nhau. |
| “Một transaction SQL hợp lệ thì commit chắc chắn thành công.” | Có thể bị hủy bằng **40001** do phụ thuộc với transaction khác. |
| “Retry câu SQL bị lỗi là đủ.” | Cần chạy lại **toàn bộ transaction**, gồm các lần đọc làm căn cứ quyết định. |
| “SERIALIZABLE bảo đảm logic ứng dụng đúng.” | Vẫn phải thực hiện kiểm tra nghiệp vụ và ràng buộc dữ liệu đúng. |
| “Lỗi 40001 chính là deadlock.” | **40001** là serialization failure; PostgreSQL deadlock thường có **40P01**. |
| “Càng nhiều retry càng bảo đảm thành công.” | Retry không giới hạn có thể gây bão tải; cần giới hạn và backoff. |
| “Đã dùng SERIALIZABLE thì gửi email trong transaction vẫn an toàn.” | Side effect ngoài DB không tự rollback khi transaction bị hủy. |
| “SERIALIZABLE ở mọi DBMS có cùng cơ chế và chi phí.” | Bảo đảm và thuật toán triển khai phải kiểm tra theo DBMS cụ thể. |
| “Tăng index chắc chắn xóa hết lỗi 40001.” | Index có thể giúp giảm phạm vi đọc nhưng không loại bỏ mọi xung đột nghiệp vụ. |

## 13. Bài tập tự kiểm tra

### Bài 1 — Phân tích một lịch chạy

Hai bác sĩ A và B đều đang trực. T1 và T2 cùng đọc COUNT = 2, rồi lần lượt tắt trạng thái trực của A và B. Nếu cả hai commit, lịch chạy có serializable không?

**Gợi ý đáp án:** Không. Ở mọi thứ tự chạy tuần tự, giao dịch thứ hai phải thấy COUNT = 1 và từ chối nghỉ. Lịch cho cả hai nghỉ không tương đương bất kỳ thứ tự tuần tự hợp lệ nào.

### Bài 2 — Tìm phần bắt buộc phải retry

Giao dịch T1 dùng JDBC:

1. Đọc số chỗ trống của một lớp học.
2. Nếu còn chỗ, tạo dòng đăng ký.
3. Commit nhận **SQLSTATE 40001**.

Khi retry, có được giữ lại “số chỗ trống” đã đọc ở bước 1 không?

**Gợi ý đáp án:** Không. Phải tạo giao dịch mới và đọc lại; kết quả ở bước 1 thuộc snapshot/lịch chạy đã bị từ chối.

### Bài 3 — Chọn giải pháp với khóa điều phối

Một hệ thống có bảng **shift**, mỗi ca trực một hàng, và bảng **duty_doctors**. Mọi thao tác thay đổi bác sĩ trực đều có thể được yêu cầu **SELECT ... FOR UPDATE** trên hàng shift tương ứng trước khi kiểm tra và cập nhật.

Giải pháp đó khác SERIALIZABLE với SSI thế nào?

**Gợi ý đáp án:** Khóa hàng shift giúp các giao dịch cùng ca **chờ nhau và tuần tự hóa có chủ đích** nếu tất cả đường ghi cùng tuân thủ. SSI có thể cho chạy đồng thời rồi hủy một bên khi phát hiện phụ thuộc nguy hiểm. Khóa có thể tăng thời gian chờ; SSI có thể tăng retry.

### Bài 4 — Tính chi phí thử lại

Giả định xác suất một lần thử bị hủy bởi xung đột là **20%**, độc lập giữa các lần thử và không giới hạn retry. Số lần thử trung bình theo mô hình đơn giản là bao nhiêu?

**Gợi ý đáp án:** \(1/(1-0,2) = 1,25\) lần thử cho mỗi giao dịch thành công. Trong hệ thống thật phải đo vì retry làm thay đổi mức tranh chấp.

### Bài 5 — Phân biệt lỗi

Một service nhận hai lỗi SQLSTATE trong hai tình huống:

- **40001** khi transaction bị từ chối vì lịch chạy đồng thời.
- **23505** khi chèn một mã đơn hàng trùng ràng buộc UNIQUE.

Có nên retry vô điều kiện cả hai?

**Gợi ý đáp án:** Không. **40001** thường là trường hợp retry **toàn bộ transaction** phù hợp. **23505** có thể là lỗi nghiệp vụ mã trùng thật; chỉ xử lý/retry nếu thuật toán tạo mã và chính sách nghiệp vụ đã xác định rõ cách giải quyết. Mọi retry cần hữu hạn và bảo vệ idempotency.

### Bài 6 — Đọc hiểu số liệu

Sau khi bật SERIALIZABLE, metric **xact_rollback** của PostgreSQL tăng. Có được kết luận ngay “mọi rollback là lỗi SSI” không?

**Gợi ý đáp án:** Không. xact_rollback bao gồm nhiều nguyên nhân; cần đo **SQLSTATE 40001** tại ứng dụng, xem log và kết hợp các chỉ số khác.

## 14. Ghi nhớ để áp dụng trong tầng persistence

**SERIALIZABLE** bảo đảm hiệu ứng của các transaction đã commit có thể được giải thích bằng một thứ tự chạy tuần tự hợp lệ. Nó ngăn các lịch chạy gây bất thường như **write skew**, ngay cả khi các transaction ghi **các hàng khác nhau** nhưng quyết định dựa trên dữ liệu của nhau.

Bảo đảm mạnh hơn đi kèm chi phí kiểm soát phụ thuộc, chờ, rollback và **thử lại toàn bộ giao dịch**. Trong PostgreSQL, SSI theo dõi phụ thuộc đọc-ghi và có thể trả **SQLSTATE 40001**; ứng dụng Java phải xem đó là tín hiệu thiết kế retry, không phải chỉ là lỗi SQL ngẫu nhiên.

Khi thiết kế persistence cho nghiệp vụ thật, hãy xác định bất biến trước, đặt ranh giới transaction đủ ngắn, sử dụng mức cô lập hoặc khóa phù hợp, bảo đảm mọi luồng ghi cần thiết đều cùng tuân thủ quy tắc, rồi đo tỷ lệ xung đột và độ trễ dưới tải. Với các thao tác có side effect ngoài DB hoặc trạng thái COMMIT không rõ, cần thêm idempotency/outbox và chính sách đối soát. Khi đó, SERIALIZABLE trở thành một công cụ rõ ràng để **giữ tính đúng của dữ liệu khi hệ thống tăng mức đồng thời**, cùng với chi phí vận hành được hiểu và kiểm soát.

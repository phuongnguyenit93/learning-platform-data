# Kiểm chứng bất biến khi chuyển sang cơ chế khả tuần tự

Khi chuyển một nghiệp vụ sang mức cô lập SERIALIZABLE, mục tiêu không chỉ là làm cho transaction ít xung đột hơn hoặc khiến một số truy vấn phải chờ. Mục tiêu là bảo đảm mọi transaction đã commit tạo ra kết quả tương đương với một thứ tự thực thi tuần tự, từ đó giữ các quy tắc nghiệp vụ luôn đúng.

Để kiểm chứng việc chuyển đổi, cần bắt đầu từ **bất biến dữ liệu (invariant)**: điều kiện phải đúng trước và sau mọi transaction được phép commit. Sau đó xây dựng các lịch thực thi đồng thời có khả năng phá vỡ điều kiện đó, chạy chúng trên isolation level đang dùng và SERIALIZABLE, xử lý các transaction bị hủy, rồi đối chiếu trạng thái cuối với một kết quả tuần tự hợp lệ.

SERIALIZABLE không tự sửa logic nghiệp vụ. Nó kiểm soát quan hệ phụ thuộc giữa các transaction. Nếu transaction kiểm tra sai điều kiện, bỏ qua một đường ghi, hoặc ứng dụng không xử lý lỗi serialization đúng cách, chuyển isolation level vẫn chưa đủ để chứng minh nghiệp vụ an toàn.

## 1. Bất biến là gì và vì sao cần xác định trước?

Bất biến là một điều kiện mà dữ liệu phải thỏa mãn ở mọi ranh giới commit hợp lệ. Bất biến có thể áp dụng cho một hàng, một nhóm hàng hoặc toàn bộ tập dữ liệu.

Ví dụ:

- Số dư tài khoản không được âm.
- Mã đơn hàng phải duy nhất.
- Mỗi phòng phải có số người đăng ký không vượt sức chứa.
- Một ca trực luôn phải có ít nhất một nhân viên đang trực.
- Tổng số lượng đã phân bổ không được vượt hạn mức được cấp.
- Mỗi đơn hàng chỉ được thanh toán một lần.

Không phải bất biến nào cũng cần SERIALIZABLE. Nếu một quy tắc có thể biểu diễn bằng CHECK, UNIQUE, khóa ngoại hoặc một câu UPDATE có điều kiện, nên dùng cơ chế ràng buộc dữ liệu trực tiếp. SERIALIZABLE hữu ích khi quy tắc phụ thuộc vào nhiều lần đọc và ghi, nhiều hàng hoặc một tập dữ liệu mà các transaction đồng thời có thể quan sát theo những snapshot khác nhau.

### Phân loại bất biến và cơ chế bảo vệ

| Loại bất biến | Ví dụ | Cơ chế thường phù hợp |
|---|---|---|
| Trên một hàng | quantity không âm | CHECK constraint và UPDATE có điều kiện |
| Duy nhất | email hoặc mã đơn không trùng | UNIQUE constraint |
| Quan hệ giữa hàng | hàng con phải tham chiếu hàng cha tồn tại | Foreign key |
| Tổng hợp nhiều hàng | tổng phân bổ không vượt hạn mức | Ràng buộc dữ liệu phù hợp, hàng tổng hợp/guard row, hoặc SERIALIZABLE |
| Quy tắc phụ thuộc nhiều lần đọc | luôn có ít nhất một nhân viên trực | SERIALIZABLE hoặc giao thức khóa chung được mọi transaction tuân thủ |

Bất biến phải được viết thành một điều kiện có thể kiểm tra. Tránh mô tả chung như “dữ liệu phải nhất quán” mà không nêu rõ dữ liệu nào, phạm vi nào và điều kiện đúng là gì.

Ví dụ, thay vì ghi “ca trực phải được bảo đảm”, hãy ghi:

**Với mỗi ca trực đang hoạt động, số nhân viên có trạng thái ON_CALL phải lớn hơn hoặc bằng 1.**

Điều kiện này cho biết rõ tập hàng cần kiểm tra, phép đếm cần thực hiện và giá trị tối thiểu phải giữ.

## 2. SERIALIZABLE bảo đảm điều gì?

Một lịch thực thi được gọi là khả tuần tự nếu kết quả của nó tương đương với một thứ tự chạy từng transaction một. DBMS có thể vẫn thực thi các transaction chồng lấn về thời gian; nó chỉ phải bảo đảm kết quả đã commit có thể giải thích được bằng một thứ tự tuần tự hợp lệ.

Giả sử hai transaction A và B cùng chạy. Nếu lịch đồng thời có kết quả tương đương với A chạy trước B, hoặc B chạy trước A, lịch đó có thể tuần tự hóa. Nếu không tồn tại thứ tự nào giải thích được kết quả, lịch đó không serializable.

SERIALIZABLE là mức cô lập yêu cầu DBMS ngăn hoặc phát hiện các lịch không đáp ứng điều kiện này. Tùy DBMS, nó có thể:

- Chặn transaction bằng khóa khi cần.
- Theo dõi phụ thuộc đọc/ghi và hủy transaction khi phát hiện lịch nguy hiểm.
- Từ chối một thao tác cập nhật vì dữ liệu mà transaction dựa vào đã thay đổi.
- Yêu cầu ứng dụng retry transaction bị hủy.

Do đó, một transaction chạy ở SERIALIZABLE có thể thất bại dù câu SQL không sai cú pháp và dữ liệu vẫn hợp lệ. Đây là một kết quả điều phối bình thường. Ứng dụng phải xử lý lỗi đó như một nhánh thực thi dự kiến.

### SERIALIZABLE không thay thế bất biến

Giả sử nghiệp vụ yêu cầu số dư không âm nhưng code cho phép trừ quá số dư. SERIALIZABLE có thể thực thi transaction đó một cách tuần tự; kết quả vẫn có thể là số dư âm nếu logic transaction sai.

Tương tự, nếu có một API khác cập nhật dữ liệu mà không kiểm tra quy tắc nghiệp vụ, hoặc một constraint cần thiết chưa được khai báo, SERIALIZABLE không tự tạo ra quy tắc còn thiếu.

Cần có đủ ba lớp:

1. **Bất biến được định nghĩa rõ**: biết điều kiện nào phải luôn đúng.
2. **Transaction bảo vệ quy tắc**: mọi thao tác đọc/ghi liên quan đều thực hiện kiểm tra và cập nhật trong ranh giới transaction phù hợp.
3. **DBMS và ứng dụng xử lý đồng thời đúng**: isolation level, constraint, khóa hoặc cơ chế phát hiện xung đột được cấu hình đúng; lỗi bị hủy được xử lý đúng.

## 3. Ví dụ bất biến nhiều hàng: luôn còn ít nhất một nhân viên trực

Giả sử bảng lưu trạng thái trực:

~~~sql
CREATE TABLE on_call_roster (
    employee_id BIGINT PRIMARY KEY,
    is_on_call BOOLEAN NOT NULL
);

INSERT INTO on_call_roster (employee_id, is_on_call)
VALUES
    (1, TRUE),
    (2, TRUE);
~~~

Bất biến của nghiệp vụ là:

~~~sql
SELECT COUNT(*)
FROM on_call_roster
WHERE is_on_call = TRUE;
~~~

Kết quả phải luôn lớn hơn hoặc bằng 1 sau mỗi transaction commit hợp lệ.

Hai người dùng cùng muốn chuyển một nhân viên sang trạng thái nghỉ trực. Mỗi transaction làm theo quy trình:

1. Đếm số người đang trực.
2. Nếu số người lớn hơn 1, cho phép chuyển người được chọn sang nghỉ.
3. Commit.

Logic có thể được minh họa như sau:

~~~sql
BEGIN;

SELECT COUNT(*)
FROM on_call_roster
WHERE is_on_call = TRUE;

-- Nếu số người trực lớn hơn 1:
UPDATE on_call_roster
SET is_on_call = FALSE
WHERE employee_id = 1;

COMMIT;
~~~

Transaction còn lại thực hiện tương tự với employee_id = 2.

Ở một mức cô lập chỉ cung cấp snapshot ổn định mà không ngăn write skew, hai transaction có thể cùng đếm được 2 người trực. A cập nhật hàng 1; B cập nhật hàng 2. Vì hai transaction ghi hai hàng khác nhau, chúng không nhất thiết gặp xung đột ghi trên cùng một hàng. Cả hai có thể commit, để lại 0 người trực và vi phạm bất biến.

Đây là write skew. Nó cho thấy kiểm tra từng hàng hoặc chỉ quan sát xung đột ghi trên cùng hàng không đủ để bảo vệ một quy tắc tổng hợp.

Khi chạy cùng logic ở SERIALIZABLE, DBMS phải bảo đảm kết quả tương đương với một thứ tự tuần tự. Nếu A được xem như chạy trước, A chuyển người 1 sang nghỉ. Khi B được xét sau A, B phải thấy chỉ còn một người trực và không được chuyển người 2 sang nghỉ. Một DBMS triển khai SERIALIZABLE có thể phát hiện phụ thuộc nguy hiểm và hủy một transaction thay vì để cả hai commit.

### Kiểm tra lại bất biến sau khi thực thi

Sau khi tất cả transaction hoàn tất hoặc được retry, chạy truy vấn kiểm tra:

~~~sql
SELECT COUNT(*) AS active_on_call
FROM on_call_roster
WHERE is_on_call = TRUE;
~~~

Điều kiện mong đợi là:

~~~text
active_on_call >= 1
~~~

Truy vấn kiểm tra cuối là cần thiết nhưng chưa đủ. Một bài kiểm chứng tốt còn phải xác nhận transaction bị hủy đã được ứng dụng xử lý đúng, và lần retry có đọc lại trạng thái mới trước khi quyết định.

## 4. Viết điều kiện trước, lịch cạnh tranh sau

Một lỗi phổ biến khi kiểm thử SERIALIZABLE là chạy nhiều request ngẫu nhiên rồi chỉ nhìn xem có exception hay không. Cách đó không chứng minh được bất biến.

Nên bắt đầu từ một đặc tả ngắn cho từng quy tắc:

| Thành phần | Câu hỏi cần trả lời |
|---|---|
| Phạm vi dữ liệu | Bất biến áp dụng cho hàng, nhóm hàng, tài khoản hay toàn hệ thống? |
| Điều kiện đúng | Biểu thức nào phải luôn đúng? |
| Điểm bắt đầu | Trạng thái ban đầu nào được xem là hợp lệ? |
| Transaction liên quan | Những luồng nào có thể cùng đọc hoặc ghi dữ liệu trong phạm vi này? |
| Lịch nguy hiểm | Các bước đọc/ghi xen kẽ nào có thể làm sai điều kiện? |
| Kết quả hợp lệ | Những trạng thái cuối nào tương đương với một thứ tự tuần tự? |
| Xử lý lỗi | Transaction bị hủy sẽ được retry, báo xung đột hay từ chối nghiệp vụ? |

Sau đó xây dựng lịch thực thi có chủ đích. Ví dụ với ca trực:

~~~text
Trạng thái ban đầu: nhân viên 1 và 2 đều đang trực.

Transaction A                    Transaction B
--------------                    --------------
BEGIN                             BEGIN
Đếm người trực = 2                Đếm người trực = 2
UPDATE nhân viên 1: nghỉ          UPDATE nhân viên 2: nghỉ
COMMIT                            COMMIT hoặc bị hủy
Kiểm tra số người trực             Nếu retry: đọc lại số người trực
                                  Chỉ nghỉ nếu vẫn còn người khác trực
~~~

Lịch này tạo ra tình huống cạnh tranh cụ thể. Nó kiểm tra đúng quan hệ phụ thuộc giữa hai transaction thay vì hy vọng một tải ngẫu nhiên tình cờ tạo ra write skew.

## 5. Đối chiếu với kết quả tuần tự tham chiếu

Một cách kiểm chứng mạnh là xây dựng một kết quả tham chiếu từ logic tuần tự.

Với cùng trạng thái ban đầu và cùng các yêu cầu nghiệp vụ:

1. Chạy A rồi B lần lượt, không có chồng lấn.
2. Ghi lại kết quả, các thao tác được chấp nhận và bất biến sau mỗi commit.
3. Chạy B rồi A lần lượt.
4. Chạy A và B đồng thời ở isolation level cũ.
5. Chạy A và B đồng thời ở SERIALIZABLE, có xử lý retry như production.
6. So sánh kết quả của các lịch đồng thời đã hoàn tất với các kết quả tuần tự hợp lệ.

Không nhất thiết kết quả của mọi thứ tự tuần tự phải giống nhau. Nếu A và B có nghiệp vụ khác nhau, A trước B có thể tạo kết quả khác B trước A. Điều cần chứng minh là kết quả đồng thời phải tương đương với ít nhất một thứ tự tuần tự hợp lệ và bất biến vẫn được giữ.

### Ví dụ với hạn mức phân bổ

Giả sử một chiến dịch có hạn mức 100 đơn vị. Nhiều transaction có thể tạo các khoản phân bổ riêng. Bất biến:

~~~text
SUM(allocation.amount) <= campaign.limit
~~~

Hai transaction cùng đọc tổng phân bổ là 80, mỗi transaction muốn thêm 15. Nếu cả hai cùng kiểm tra trên snapshot cũ và ghi vào hai hàng phân bổ khác nhau, tổng mới có thể thành 110.

Một lịch tuần tự sẽ cho kết quả:

- Transaction A chạy trước: 80 + 15 = 95, được chấp nhận.
- Transaction B chạy sau: 95 + 15 = 110, vượt hạn mức nên bị từ chối.

Hoặc theo thứ tự ngược lại, B được chấp nhận và A bị từ chối. Lịch đồng thời ở SERIALIZABLE phải có kết quả tương đương với một trong hai thứ tự đó, hoặc hủy transaction để ứng dụng thử lại và đưa ra quyết định mới.

Truy vấn kiểm tra:

~~~sql
SELECT
    c.campaign_id,
    c.limit_amount,
    COALESCE(SUM(a.amount), 0) AS allocated_amount
FROM campaigns c
LEFT JOIN allocations a
    ON a.campaign_id = c.campaign_id
GROUP BY c.campaign_id, c.limit_amount;
~~~

Mọi hàng kết quả phải thỏa:

~~~text
allocated_amount <= limit_amount
~~~

Đối với dữ liệu thực tế, cần cân nhắc cách lưu và cập nhật tổng phân bổ, độ chính xác kiểu số và việc các transaction có thể ghi qua nhiều service hay không. Một hàng tổng hợp được cập nhật nguyên tử hoặc một guard row có thể là lựa chọn phù hợp nếu muốn tạo điểm tranh chấp rõ ràng. SERIALIZABLE là một lựa chọn khi quy tắc cần bảo vệ phụ thuộc vào nhiều lần đọc/ghi và DBMS hỗ trợ đúng ngữ nghĩa cần thiết.

## 6. Thiết kế bài kiểm thử đồng thời có thể lặp lại

Một bài test đáng tin cậy phải điều khiển được thứ tự các bước. Không nên dùng sleep cố định để hy vọng hai transaction cùng đọc trước khi một bên ghi. Tốc độ máy, CI và tải nền có thể làm thứ tự thực thi thay đổi.

Nên dùng hai hoặc nhiều connection độc lập và một cơ chế đồng bộ trong test harness như barrier, latch hoặc promise:

1. Tạo dữ liệu ban đầu ở trạng thái hợp lệ.
2. Mở connection A và B.
3. Bắt đầu transaction trên từng connection ở isolation level cần kiểm tra.
4. Cho mỗi transaction đọc phần dữ liệu cần thiết.
5. Chờ cả hai xác nhận đã hoàn tất bước đọc.
6. Cho cả hai thực hiện cập nhật cạnh tranh.
7. Thu nhận kết quả commit, serialization failure, deadlock hoặc timeout.
8. Nếu có retry, chạy lại toàn bộ transaction trên connection/transaction mới theo cách ứng dụng production thực hiện.
9. Đọc trạng thái cuối và đánh giá tất cả bất biến.

Có thể mô tả luồng test:

~~~text
Khởi tạo dữ liệu hợp lệ
          |
          v
Mở connection A và B
          |
          v
Bắt đầu transaction ở isolation level mục tiêu
          |
          v
A đọc dữ liệu ---- B đọc dữ liệu
          |              |
          +--- Barrier --+
                 |
                 v
       A và B cùng thử ghi
                 |
                 v
     Thu kết quả commit hoặc abort
                 |
                 v
      Retry toàn bộ nếu được phép
                 |
                 v
       Kiểm tra invariant cuối
                 |
                 v
    So sánh với lịch tuần tự tham chiếu
~~~

Test phải ghi nhận transaction nào đã commit và transaction nào bị hủy. Chỉ thấy một transaction bị lỗi không có nghĩa kiểm thử thành công; có thể lỗi đến từ cú pháp, timeout không mong đợi hoặc kết nối bị đóng.

### Những trường hợp nên kiểm thử

- Hai transaction cùng thực hiện đúng một nghiệp vụ trên cùng hàng.
- Hai transaction cập nhật hai hàng khác nhau nhưng cùng ảnh hưởng một bất biến tổng hợp.
- Một transaction đọc dữ liệu trong khi transaction khác ghi và commit.
- Transaction bị serialization failure rồi retry thành công.
- Retry tiếp tục gặp xung đột và chạm giới hạn số lần thử.
- Một transaction rollback do lỗi nghiệp vụ giữa nhiều câu lệnh.
- Hai transaction cập nhật nhiều hàng theo thứ tự khóa khác nhau và có nguy cơ deadlock.
- Hai request lặp lại cùng một yêu cầu do client retry sau timeout.

Không chỉ kiểm tra trạng thái cuối. Cần kiểm tra số lần side effect được thực hiện, số lần transaction retry, kết quả trả về cho caller và khả năng phục hồi khi kết nối mất sau commit.

## 7. Kiểm chứng retry: transaction bị hủy phải được chạy lại từ đầu

Với các DBMS có thể hủy transaction do serialization conflict, retry là một phần của hợp đồng ứng dụng.

Giả sử transaction thực hiện:

1. Đọc số người trực.
2. Kiểm tra còn đủ người trực hay không.
3. Cập nhật một người sang trạng thái nghỉ.
4. Ghi lịch sử thay đổi.
5. Commit.

Nếu DBMS hủy transaction ở bước commit hoặc trong một câu lệnh do serialization failure, ứng dụng phải rollback và chạy lại cả quy trình từ bước 1. Không được chỉ gửi lại câu UPDATE cuối cùng, vì quyết định nghỉ trực ban đầu dựa trên snapshot cũ.

Mẫu xử lý khái quát:

~~~text
for attempt in 1..MAX_RETRIES:
    begin transaction at SERIALIZABLE

    try:
        read current state
        validate business invariant
        apply changes
        commit
        return success

    catch serialization conflict:
        rollback
        if attempt reached MAX_RETRIES:
            return retryable conflict
        wait with bounded backoff and jitter

    catch other error:
        rollback
        propagate or map the error
~~~

Mã trên là pseudocode, không phải cú pháp của một driver cụ thể. Cần dùng API transaction và phân loại lỗi tương ứng với DBMS/driver của ứng dụng.

Một số lưu ý:

- Retry phải tạo transaction mới và snapshot mới.
- Giới hạn số lần retry; không lặp vô hạn.
- Có thể dùng exponential backoff với jitter để giảm va chạm đồng loạt.
- Phân biệt serialization failure với validation error. Lỗi nghiệp vụ như “không còn người trực khác” không nên retry liên tục.
- Không thực hiện email, thanh toán hoặc publish message trước khi biết transaction đã commit thành công.
- Nếu cần ghi nhận sự kiện cùng thay đổi dữ liệu, cân nhắc transactional outbox để side effect có thể được phát đi sau commit theo cách idempotent.

### Kiểm chứng tính idempotent của retry

Một request có thể được gửi lại vì client không nhận được phản hồi dù DBMS đã commit. Đây là tình huống khác với serialization failure. Nếu ứng dụng xử lý cả hai bằng cách chạy lại một thao tác cộng/trừ, dữ liệu có thể bị thay đổi hai lần.

Dùng idempotency key hoặc một mã yêu cầu duy nhất để DBMS nhận diện yêu cầu đã được xử lý. Test nên mô phỏng:

1. Transaction commit thành công.
2. Kết nối bị ngắt trước khi client nhận phản hồi.
3. Client gửi lại cùng request id.
4. Ứng dụng trả lại kết quả đã lưu mà không thực hiện side effect lần thứ hai.

SERIALIZABLE không tự giải quyết vấn đề request lặp. Đây là trách nhiệm của thiết kế API và tính idempotent của nghiệp vụ.

## 8. Constraint, guard row và SERIALIZABLE có thể phối hợp

Khi kiểm chứng bất biến, không nên mặc định mọi quy tắc đều cần giải quyết bằng SERIALIZABLE.

### Dùng constraint khi DBMS có thể biểu diễn quy tắc

Ví dụ, số lượng tồn kho không âm:

~~~sql
ALTER TABLE inventory
ADD CONSTRAINT inventory_quantity_nonnegative
CHECK (quantity >= 0);
~~~

Hoặc mã đơn hàng duy nhất:

~~~sql
ALTER TABLE orders
ADD CONSTRAINT orders_order_code_unique
UNIQUE (order_code);
~~~

Constraint bảo vệ quy tắc ở cấp dữ liệu ngay cả khi nhiều ứng dụng cùng ghi. Nếu constraint có thể biểu diễn chính xác bất biến, đó thường là lớp bảo vệ cần ưu tiên.

### Dùng guard row cho bất biến nhiều hàng

Một guard row là hàng đại diện cho một tài nguyên nghiệp vụ chung. Mọi transaction có thể ảnh hưởng đến bất biến đều khóa hoặc cập nhật hàng này theo cùng giao thức trước khi thay đổi các hàng chi tiết.

Ví dụ, mỗi chiến dịch có một hàng campaigns. Transaction phân bổ hạn mức khóa hàng chiến dịch bằng SELECT FOR UPDATE, kiểm tra tổng hiện tại, rồi ghi allocation. Cách này biến một quy tắc nhiều hàng thành một điểm tranh chấp tường minh.

Guard row chỉ hiệu quả khi mọi đường ghi tuân thủ cùng giao thức. Một service ghi allocations trực tiếp mà bỏ qua khóa guard vẫn có thể phá bất biến.

### Dùng SERIALIZABLE cho phụ thuộc đọc/ghi phức tạp

Nếu quy tắc phụ thuộc vào predicate hoặc tập hàng thay đổi theo thời gian, khóa một hàng cụ thể có thể không đủ. SERIALIZABLE giúp DBMS phát hiện các phụ thuộc có thể tạo ra lịch không tuần tự được.

Trong PostgreSQL, SERIALIZABLE dùng SSI để phát hiện các chuỗi phụ thuộc nguy hiểm. Trong hệ quản trị khác, cách triển khai có thể dựa trên khóa, version hoặc cơ chế kiểm soát khác. Cần xác nhận đúng hành vi của DBMS và phiên bản đang triển khai.

## 9. Ma trận kiểm chứng khi chuyển isolation level

Trước khi đưa thay đổi lên production, hãy tạo ma trận test để bao phủ cả tính đúng đắn và khả năng vận hành.

| Nhóm kiểm chứng | Điều kiện cần xác nhận | Bằng chứng mong đợi |
|---|---|---|
| Trạng thái ban đầu | Dữ liệu bắt đầu thỏa mọi invariant | Fixture hợp lệ, truy vấn kiểm tra trả kết quả đúng |
| Lịch tuần tự | Mỗi thứ tự hợp lệ giữ được invariant | Kết quả A→B và B→A được ghi nhận |
| Lịch đồng thời nguy hiểm | Tái hiện được write skew hoặc conflict cần ngăn | Barrier chứng minh cả hai đã đọc trước khi ghi |
| Isolation level cũ | Xác định hành vi hiện tại | Commit/abort và trạng thái cuối được lưu |
| SERIALIZABLE | Không có kết quả đã commit vi phạm invariant | Một thứ tự tuần tự tham chiếu giải thích được kết quả |
| Retry | Transaction bị hủy được chạy lại từ đầu | Lần retry đọc snapshot mới và đưa ra quyết định mới |
| Side effect | Không gửi trùng hoặc thực hiện trước commit | Event/outbox hoặc idempotency record đúng |
| Tải đồng thời | Retry và thời gian chờ nằm trong ngưỡng chấp nhận | Metric về serialization failure, deadlock, latency |
| Khả năng quan sát | Có thể tìm ra transaction gây tranh chấp | Log, trace, mã lỗi và định danh nghiệp vụ |
| Tương thích triển khai | Cấu hình isolation level được áp dụng thật | Integration test trên đúng DBMS và cấu hình production |

Bài test chỉ chạy trên H2 hoặc một DBMS khác với production không đủ để chứng minh chính sách xung đột của PostgreSQL, InnoDB, SQL Server hay Oracle. Những chi tiết như snapshot timing, khóa predicate, update conflict và retry error là đặc tính của hệ quản trị. Hãy chạy integration test trên đúng DBMS, đúng phiên bản chính và cấu hình liên quan.

## 10. Theo dõi vận hành sau khi chuyển đổi

SERIALIZABLE có thể làm tăng số transaction bị hủy và retry. Điều đó không nhất thiết là lỗi; có thể là DBMS đang phát hiện các lịch nguy hiểm mà mức cô lập cũ cho phép. Nhưng nếu tỷ lệ quá cao, ứng dụng có thể giảm thông lượng hoặc tăng độ trễ.

Nên theo dõi:

- Số serialization failure theo endpoint hoặc loại nghiệp vụ.
- Số lần retry trung bình và phân vị cao.
- Tỷ lệ transaction chạm giới hạn retry.
- Deadlock và lock wait timeout.
- Thời gian transaction và thời gian giữ khóa.
- Độ trễ p95/p99 của request.
- Số lượng request thất bại cuối cùng sau khi retry.
- Các invariant check và cảnh báo khi dữ liệu vi phạm.

Log nên có transaction/request id, loại nghiệp vụ, DBMS error code, isolation level và số lần retry. Tránh ghi dữ liệu nhạy cảm hoặc toàn bộ câu SQL có chứa giá trị bí mật.

Một tỷ lệ serialization failure nhỏ có thể chấp nhận được nếu retry nhanh và tổng độ trễ vẫn trong SLA. Nếu một tài nguyên nóng khiến nhiều transaction liên tục tranh chấp, cân nhắc guard row, cập nhật nguyên tử, phân vùng công việc hoặc thiết kế lại phạm vi khóa.

## 11. Quy trình chuyển đổi có kiểm soát

Một quy trình thực tế có thể thực hiện theo các bước:

1. **Liệt kê bất biến**: ghi rõ điều kiện, phạm vi dữ liệu và các nghiệp vụ có thể ảnh hưởng.
2. **Tìm mọi đường ghi**: API, batch job, worker, tác vụ quản trị và service khác có thể thay đổi dữ liệu.
3. **Chọn cơ chế bảo vệ**: constraint, atomic UPDATE, guard row, explicit lock hoặc SERIALIZABLE theo từng bất biến.
4. **Viết test lịch cạnh tranh**: điều khiển thứ tự đọc/ghi bằng barrier trên nhiều connection.
5. **Chạy test trên DBMS thật**: kiểm tra đúng isolation level và cấu hình production.
6. **Triển khai retry**: retry toàn bộ transaction cho đúng nhóm lỗi, có giới hạn và backoff.
7. **Đo hiệu năng và xung đột**: so sánh latency, throughput, abort rate và lock wait với baseline.
8. **Triển khai từng bước**: theo dõi metric, log và invariant check; có phương án quay lại nếu tải hoặc lỗi vượt ngưỡng.
9. **Kiểm tra lại sau triển khai**: xác nhận cấu hình thực tế, không chỉ cấu hình trong code hoặc test.

Nếu bật SERIALIZABLE ở cấp transaction, cần xác nhận mọi đường truy cập quan trọng thật sự chạy trong isolation level đó. Một endpoint dùng SERIALIZABLE không bảo vệ được bất biến nếu một batch job khác cập nhật cùng dữ liệu ở mức thấp hơn và không tuân thủ constraint hoặc giao thức chung.

## 12. Checklist bàn giao kiểm chứng

Trước khi kết luận việc chuyển sang SERIALIZABLE đã bảo vệ đúng bất biến, hãy trả lời được các câu hỏi sau:

- [ ] Mỗi bất biến đã có biểu thức kiểm tra cụ thể chưa?
- [ ] Trạng thái ban đầu và các kết quả tuần tự hợp lệ đã được xác định chưa?
- [ ] Đã xác định tất cả transaction và đường ghi ảnh hưởng đến bất biến chưa?
- [ ] Có test tái hiện lịch cạnh tranh nguy hiểm bằng nhiều connection độc lập chưa?
- [ ] Test đã xác nhận hành vi commit/abort của đúng DBMS và isolation level chưa?
- [ ] Sau retry, transaction có đọc lại dữ liệu và kiểm tra invariant từ đầu không?
- [ ] Các lỗi serialization, deadlock và timeout được phân loại riêng chưa?
- [ ] Side effect bên ngoài có được bảo vệ khỏi việc thực hiện lặp không?
- [ ] Constraint có thể biểu diễn quy tắc đã được dùng ở cấp DBMS chưa?
- [ ] Metric về retry, abort, lock wait và latency có thể quan sát sau triển khai không?
- [ ] Có kiểm tra invariant trên dữ liệu sau triển khai không?

Một kết luận kiểm chứng tốt nên nêu rõ bất biến nào được bảo vệ, lịch cạnh tranh nào đã thử, DBMS/isolation level/cấu hình nào được dùng, transaction nào bị hủy và cách retry hoạt động, cùng với kết quả kiểm tra trạng thái cuối.

Khi chuyển sang SERIALIZABLE, điều cần chứng minh là mọi trạng thái đã commit vẫn thỏa các bất biến nghiệp vụ và có thể giải thích bằng một thứ tự transaction tuần tự hợp lệ. Việc đo được cả kết quả commit, abort, retry và side effect giúp xác nhận hệ thống vừa giữ đúng dữ liệu vừa vận hành được dưới tải đồng thời.

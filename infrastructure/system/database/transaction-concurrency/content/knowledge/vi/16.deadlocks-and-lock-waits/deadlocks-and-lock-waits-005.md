# Cơ chế phát hiện, chọn giao dịch nạn nhân và hủy bỏ

Deadlock (bế tắc) xảy ra khi một nhóm giao dịch chờ lẫn nhau theo một vòng phụ thuộc, khiến không giao dịch nào trong nhóm có thể tiếp tục nếu không có sự can thiệp. Trong cơ sở dữ liệu, tình huống phổ biến là mỗi giao dịch đang giữ một khóa mà giao dịch khác cần, đồng thời lại chờ một khóa do giao dịch kia giữ.

DBMS thường xử lý deadlock theo ba bước: **phát hiện chu trình chờ, chọn một giao dịch làm nạn nhân (victim), rồi hủy/rollback giao dịch đó để giải phóng khóa**. Các giao dịch còn lại có thể tiếp tục khi những khóa cần thiết được trả lại. Cơ chế cụ thể và tiêu chí chọn nạn nhân khác nhau giữa các hệ quản trị, nhưng mục tiêu chung là phá vỡ vòng chờ với chi phí phục hồi hợp lý.

## 1. Deadlock hình thành như thế nào?

Giả sử hệ thống có hai tài khoản `A` và `B`. Giao dịch `T1` chuyển tiền theo hướng `A → B`; giao dịch `T2` chuyển tiền theo hướng `B → A`.

Một lịch thực thi có thể xảy ra như sau:

1. `T1` lấy khóa độc quyền `X(A)` để cập nhật tài khoản A.
2. `T2` lấy khóa độc quyền `X(B)` để cập nhật tài khoản B.
3. `T1` yêu cầu `X(B)`, nhưng B đang bị T2 khóa nên T1 phải chờ.
4. `T2` yêu cầu `X(A)`, nhưng A đang bị T1 khóa nên T2 cũng phải chờ.

```text
T1 giữ X(A)                         T2 giữ X(B)
    │                                  │
    └── yêu cầu X(B)                   └── yêu cầu X(A)
             │                                  │
             └────────── chờ T2                 └────────── chờ T1

T1 chờ T2, đồng thời T2 chờ T1 → không giao dịch nào tự tiếp tục được.
```

Đây là deadlock. Chỉ tăng thời gian chờ không thể giải quyết vòng phụ thuộc: nếu không giao dịch nào bị hủy hoặc chủ động nhả khóa, cả hai tiếp tục chờ.

### Phân biệt deadlock với chờ khóa thông thường

Chờ khóa là hiện tượng bình thường khi một giao dịch yêu cầu tài nguyên đang được giao dịch khác giữ. Nếu giao dịch giữ khóa hoàn tất và commit, khóa được giải phóng, giao dịch đang chờ có thể tiếp tục.

Deadlock khác ở chỗ các giao dịch tạo thành một chu trình chờ. Ví dụ, `T2` chờ `T1` nhưng `T1` vẫn đang chạy và không chờ tài nguyên do T2 giữ thì đây chỉ là chờ khóa, chưa phải deadlock. Một giao dịch có thể chờ rất lâu do truy vấn chậm hoặc giao dịch khác chưa commit mà không tạo thành chu trình.

## 2. Wait-for graph biểu diễn vòng chờ

Một cách phổ biến để mô hình hóa deadlock là **wait-for graph (đồ thị chờ)**. Đồ thị có:

- Mỗi nút đại diện cho một giao dịch đang hoạt động.
- Một cạnh có hướng `Ti → Tj` nghĩa là `Ti` đang chờ một khóa xung đột do `Tj` giữ.

Với ví dụ hai tài khoản:

```text
T1 ─────────▶ T2
 ▲             │
 └─────────────┘
```

`T1 → T2` vì T1 cần khóa B mà T2 đang giữ. `T2 → T1` vì T2 cần khóa A mà T1 đang giữ. Đồ thị có chu trình `T1 → T2 → T1`, do đó tồn tại deadlock trong mô hình chờ khóa này.

### Nhiều giao dịch cùng tham gia

Deadlock không chỉ có hai giao dịch. Ví dụ:

```text
T1 → T2 → T3 → T1
```

`T1` chờ khóa của `T2`, `T2` chờ khóa của `T3`, còn `T3` chờ khóa của `T1`. Mỗi giao dịch đều đang giữ tài nguyên mà giao dịch kế tiếp cần. Hủy một giao dịch trong chu trình có thể phá vòng chờ.

### Chu trình có ý nghĩa gì?

Trong wait-for graph của các giao dịch chờ khóa, một chu trình cho thấy mỗi giao dịch trên chu trình đang chờ một giao dịch khác trong cùng chu trình nhả khóa. Vì các khóa đang được giữ cho đến khi giao dịch kết thúc hoặc chủ động nhả khóa theo quy tắc, chu trình không thể tự tan nếu không có hành động bên ngoài.

Wait-for graph là cách diễn giải ở mức giao dịch. Bên trong DBMS, lock manager có thể theo dõi nhiều loại khóa và phụ thuộc hàng đợi phức tạp hơn. Nếu một yêu cầu đang chờ nhiều khóa, có thể có nhiều cạnh từ giao dịch đó đến các giao dịch đang giữ khóa xung đột.

## 3. Cơ chế phát hiện deadlock

DBMS cần biết giao dịch nào đang chờ và giao dịch nào đang giữ khóa để xác định có chu trình hay không. Cơ chế thường gồm các bước sau:

1. **Ghi nhận yêu cầu khóa:** khi một giao dịch không thể lấy khóa ngay, lock manager ghi nhận giao dịch đang chờ, tài nguyên cần lấy và các giao dịch đang giữ khóa xung đột.
2. **Tạo hoặc cập nhật quan hệ chờ:** các quan hệ đó tạo thành wait-for graph hoặc một cấu trúc tương đương.
3. **Tìm chu trình:** thuật toán duyệt đồ thị để xác định có đường đi quay lại nút ban đầu hay không.
4. **Chọn nạn nhân:** nếu phát hiện chu trình, DBMS quyết định giao dịch nào sẽ bị hủy để phá vòng chờ.
5. **Phục hồi:** DBMS rollback nạn nhân, giải phóng khóa phù hợp và đánh thức các giao dịch đang chờ.

### Tìm chu trình trong đồ thị

Với đồ thị có `V` nút và `E` cạnh, thuật toán duyệt theo chiều sâu (DFS) hoặc thuật toán tìm thành phần liên thông mạnh có thể phát hiện chu trình trong thời gian tuyến tính theo kích thước đồ thị, thường được biểu diễn là `O(V + E)`.

Ví dụ DFS có thể đánh dấu các nút theo trạng thái:

- Chưa thăm.
- Đang nằm trên đường duyệt hiện tại.
- Đã duyệt xong.

Nếu gặp một cạnh đi tới nút đang nằm trên đường duyệt hiện tại, ta tìm thấy chu trình. Đây là mô tả thuật toán khái niệm; DBMS thực tế có thể dùng cấu trúc dữ liệu và thuật toán tối ưu riêng.

### Phát hiện theo sự kiện hay theo chu kỳ

Có nhiều cách kích hoạt việc kiểm tra:

- **Khi một giao dịch phải chờ:** DBMS có thể kiểm tra đồ thị sau khi một yêu cầu khóa bị chặn.
- **Theo chu kỳ:** DBMS định kỳ kiểm tra các giao dịch đang chờ.
- **Sau một khoảng chờ:** một số hệ thống chỉ thực hiện kiểm tra deadlock sau khi giao dịch chờ đủ lâu, nhằm giảm chi phí kiểm tra liên tục.

Không phải mọi DBMS đều kiểm tra ngay khi có cạnh chờ mới. Một khoảng trì hoãn trước khi chạy bộ phát hiện có thể giúp tránh tốn chi phí cho những lần chờ ngắn thường kết thúc tự nhiên.

Ví dụ, PostgreSQL có tham số `deadlock_timeout` để xác định thời gian chờ trước khi thực hiện kiểm tra deadlock. Tham số này là ngưỡng kích hoạt kiểm tra, không đồng nghĩa với `lock_timeout`: hai thiết lập có mục đích khác nhau.

## 4. Phát hiện và chọn nạn nhân là hai quyết định khác nhau

Khi tìm thấy chu trình, DBMS đã biết có deadlock. Nhưng vẫn cần quyết định giao dịch nào bị rollback. Mục tiêu không đơn giản là hủy giao dịch mới nhất hay giao dịch đang chờ lâu nhất; hệ thống cần phá chu trình với chi phí phục hồi thấp và tránh để một giao dịch luôn bị chọn làm nạn nhân.

Ví dụ:

```text
T1: đã cập nhật 1 hàng, giữ 2 khóa, chờ T2
T2: đã cập nhật 100 hàng, giữ 8 khóa, chờ T1

Chu trình: T1 → T2 → T1
```

Nếu chỉ xét số lượng công việc phải hoàn tác, hủy T1 có thể rẻ hơn. Nhưng nếu T1 có mức ưu tiên nghiệp vụ cao hoặc đã nhiều lần bị hủy trước đó, DBMS có thể cân nhắc thêm các yếu tố khác.

## 5. Tiêu chí chọn giao dịch nạn nhân

Các DBMS có thuật toán riêng, nhưng những yếu tố thường có thể được cân nhắc gồm:

### Chi phí rollback

Giao dịch đã thực hiện càng nhiều thay đổi thì việc rollback có thể càng tốn thời gian và I/O. Số lượng bản ghi đã sửa, lượng log cần xử lý và công việc phục hồi là những chỉ báo có thể dùng để ước lượng chi phí.

Nếu hai giao dịch có mức ưu tiên tương đương, chọn giao dịch có chi phí rollback thấp thường giúp giảm lượng công việc bị mất.

### Số lượng khóa đang giữ

Một giao dịch đang giữ nhiều khóa có thể chặn nhiều giao dịch khác. Hủy giao dịch đó có thể giải phóng nhiều tài nguyên và giúp hệ thống tiến triển nhanh hơn. Tuy nhiên, số lượng khóa chỉ là một yếu tố; nó không tự phản ánh đầy đủ chi phí rollback hay mức độ quan trọng của công việc.

### Mức ưu tiên của giao dịch

Ứng dụng hoặc DBMS có thể gán mức ưu tiên khác nhau cho giao dịch. Một giao dịch xử lý thanh toán quan trọng có thể được ưu tiên hơn một tác vụ nền có thể chạy lại sau. Một số DBMS cho phép cấu hình deadlock priority hoặc mức ưu tiên tương đương.

### Thời gian đã chạy và số lần bị hủy

Giao dịch đã chạy lâu có thể đã tiêu tốn nhiều tài nguyên. Nếu DBMS luôn chọn giao dịch mới nhất hoặc giao dịch có chi phí nhỏ nhất, một giao dịch cụ thể có thể liên tục bị hủy khi tải cao. Tuổi giao dịch và số lần đã bị rollback có thể được dùng để giảm nguy cơ starvation (đói tài nguyên).

### Khả năng chạy lại

Một giao dịch nền có đầu vào bền vững và không có side effect bên ngoài thường dễ chạy lại hơn một quy trình tương tác phức tạp. Tuy nhiên, DBMS không phải lúc nào cũng hiểu ngữ nghĩa nghiệp vụ của ứng dụng. Việc retry an toàn vẫn cần được thiết kế ở tầng ứng dụng.

### Bảng tổng hợp

| Tiêu chí | Câu hỏi cần xem xét | Tác động có thể có |
|---|---|---|
| Chi phí rollback | Cần hoàn tác bao nhiêu thay đổi? | Ưu tiên hủy giao dịch có chi phí thấp |
| Số khóa đang giữ | Hủy giao dịch này giải phóng được bao nhiêu khóa? | Có thể giúp nhiều giao dịch khác tiếp tục |
| Mức ưu tiên | Giao dịch nào quan trọng hơn? | Giữ lại giao dịch có ưu tiên cao |
| Tuổi giao dịch | Giao dịch đã chạy bao lâu? | Tránh bỏ phí quá nhiều công việc đã thực hiện |
| Số lần bị hủy | Giao dịch đã từng làm nạn nhân bao nhiêu lần? | Giảm nguy cơ starvation |
| Khả năng retry | Ứng dụng có thể chạy lại an toàn không? | Hỗ trợ chọn tác vụ dễ phục hồi hơn |

Không có một công thức chọn nạn nhân thống nhất cho mọi hệ thống. Một số DBMS dùng chi phí rollback ước lượng; một số hỗ trợ mức ưu tiên do người vận hành cấu hình; một số dùng quy tắc nội bộ không cho ứng dụng kiểm soát trực tiếp.

## 6. Hủy giao dịch nạn nhân và giải phóng khóa

Sau khi chọn nạn nhân, DBMS phải làm cho các thay đổi chưa commit của giao dịch đó không còn hiệu lực và giải phóng các khóa liên quan để phá chu trình.

Với ví dụ hai tài khoản, giả sử DBMS chọn `T1` làm nạn nhân:

1. DBMS yêu cầu `T1` abort.
2. Các thay đổi chưa commit của `T1` được rollback theo cơ chế phục hồi.
3. Các khóa do `T1` giữ, bao gồm `X(A)`, được giải phóng theo quy trình rollback.
4. `T2` được đánh thức và có thể lấy `X(A)`.
5. `T2` tiếp tục nếu trạng thái transaction và điều kiện nghiệp vụ vẫn hợp lệ, rồi commit.

```text
Trước khi phát hiện:

T1 giữ X(A), chờ X(B) của T2
T2 giữ X(B), chờ X(A) của T1

DBMS chọn T1 làm victim:

T1: ABORT → rollback → nhả X(A)
                         │
                         └── T2 lấy được X(A)
                             tiếp tục và có thể COMMIT
```

Điểm quan trọng là khóa không được giải phóng theo cách để giao dịch khác sử dụng các thay đổi chưa commit của nạn nhân. DBMS phải bảo đảm quá trình rollback và phục hồi dữ liệu nhất quán trước khi cho giao dịch khác tiếp tục trên những tài nguyên liên quan.

### Rollback toàn bộ hay một phần?

Hành vi khi bị chọn làm nạn nhân phụ thuộc DBMS. Nhiều hệ thống hủy toàn bộ transaction làm nạn nhân; ứng dụng phải bắt lỗi, rollback hoặc kết thúc transaction hiện tại rồi chạy lại từ đầu nếu muốn thử lại.

Một số hệ quản trị có khả năng rollback về savepoint hoặc phục hồi một phần trong những tình huống nhất định. Tuy nhiên, không nên giả định rằng deadlock victim luôn chỉ bị rollback câu lệnh cuối cùng. Hãy xem tài liệu của DBMS và driver để biết transaction còn dùng được hay đã chuyển sang trạng thái lỗi.

Ví dụ về khác biệt cần lưu ý:

- PostgreSQL thường hủy transaction làm nạn nhân với lỗi deadlock; các câu lệnh tiếp theo trong transaction sẽ không chạy thành công cho đến khi ứng dụng rollback.
- InnoDB thường rollback toàn bộ transaction được chọn làm nạn nhân deadlock.
- SQL Server chọn một transaction làm nạn nhân và rollback transaction đó; ứng dụng nhận lỗi deadlock để xử lý.

Đây là hành vi điển hình, không thay thế tài liệu phiên bản cụ thể. Ứng dụng cần nhận diện đúng mã lỗi và trạng thái transaction của hệ thống đang dùng.

## 7. Ứng dụng cần làm gì sau khi nhận lỗi deadlock?

Khi DBMS chọn transaction làm nạn nhân, ứng dụng không nên chỉ chạy lại câu SQL cuối cùng. Các bước đọc và quyết định trước đó có thể đã dựa trên trạng thái không còn đúng.

Quy trình xử lý phổ biến:

1. Nhận diện lỗi deadlock bằng mã lỗi hoặc loại exception do driver cung cấp.
2. Kết thúc/rollback transaction hiện tại theo yêu cầu của DBMS.
3. Chờ một khoảng ngắn có backoff và jitter nếu cần retry.
4. Bắt đầu transaction mới.
5. Đọc lại dữ liệu, kiểm tra lại điều kiện nghiệp vụ và thực hiện lại toàn bộ thao tác.
6. Giới hạn số lần retry; nếu vẫn thất bại, trả lỗi có thể xử lý hoặc đưa công việc vào hàng đợi thử lại.

Pseudocode:

```text
for attempt from 1 to MAX_RETRIES:
    begin transaction
    try:
        read current data
        validate business rules
        perform all database updates
        commit
        return success
    catch error:
        rollback if transaction is still active

        if error is a deadlock victim and attempt < MAX_RETRIES:
            wait with bounded backoff and jitter
            continue

        raise error
```

Retry phải chạy lại toàn bộ đơn vị nghiệp vụ trong transaction. Nếu ứng dụng chỉ chạy lại `UPDATE` cuối, nó có thể bỏ qua việc đọc và kiểm tra cần thiết, khiến dữ liệu sai hoặc làm phát sinh lỗi mới.

### Cẩn thận với side effect bên ngoài

Rollback database không tự hoàn tác email đã gửi, tin nhắn đã phát, file đã tải lên hoặc lệnh gọi cổng thanh toán đã thực hiện. Nếu transaction bị deadlock rồi ứng dụng retry, side effect có thể bị thực hiện hai lần.

Để retry an toàn, nên:

- Giữ các thay đổi database trong transaction.
- Dùng idempotency key cho yêu cầu có thể được gửi lại.
- Ghi sự kiện cần phát vào transactional outbox cùng transaction, rồi worker gửi sau khi commit.
- Bảo đảm consumer có cơ chế chống xử lý lặp khi nhận lại cùng sự kiện.

## 8. Deadlock victim và starvation

**Starvation (đói tài nguyên)** xảy ra khi một giao dịch liên tục không có cơ hội hoàn tất vì luôn bị giao dịch khác hoặc chính sách hệ thống đẩy lùi. Trong xử lý deadlock, nếu cùng một transaction luôn có chi phí rollback thấp nhất, nó có thể bị chọn làm nạn nhân nhiều lần.

Một số cách giảm nguy cơ:

- Tăng dần chi phí ưu tiên của giao dịch sau mỗi lần bị hủy.
- Xem xét tuổi giao dịch hoặc số lần đã làm nạn nhân khi chọn victim.
- Dùng mức ưu tiên phù hợp với nghiệp vụ, tránh để tác vụ nền luôn bị bỏ đói nếu chúng vẫn cần hoàn thành.
- Giới hạn số lần retry và đưa công việc thất bại lâu dài vào cơ chế xử lý riêng.
- Theo dõi số lần deadlock, số lần retry và tỷ lệ giao dịch thành công sau retry.

Không nên retry vô hạn ngay lập tức. Nhiều giao dịch cùng retry đồng thời có thể tạo thêm tải và lặp lại cùng thứ tự khóa, khiến tình trạng cạnh tranh kéo dài. Backoff ngẫu nhiên giúp các lần thử phân tán hơn theo thời gian.

## 9. Deadlock detection khác lock timeout như thế nào?

Hai cơ chế này đều có thể khiến một câu lệnh đang chờ kết thúc bằng lỗi, nhưng ý nghĩa khác nhau.

| Tiêu chí | Deadlock detection | Lock timeout |
|---|---|---|
| Điều kiện | Phát hiện chu trình phụ thuộc chờ | Thời gian chờ vượt ngưỡng cấu hình |
| Có cần chu trình không? | Có, trong mô hình wait-for graph | Không |
| Mục tiêu | Phá deadlock để các giao dịch khác tiến triển | Giới hạn thời gian một yêu cầu được phép chờ |
| Kết quả | DBMS chọn nạn nhân và hủy transaction theo chính sách | Câu lệnh hoặc transaction bị timeout theo hành vi DBMS |
| Có thể xảy ra khi không deadlock? | Không phải deadlock nếu không có chu trình | Có, ví dụ một giao dịch giữ khóa lâu nhưng không chờ ngược lại |

Ví dụ, `T2` chờ `T1` giữ khóa trong 30 giây. Nếu T1 không chờ khóa nào của T2, không có chu trình. Một `lock timeout` 5 giây có thể làm T2 dừng sau 5 giây, nhưng đó không phải kết quả của deadlock detection.

Ngược lại, một deadlock có thể được phát hiện trước khi bất kỳ lock timeout nào hết hạn. Deadlock detector tìm chu trình; lock timeout chỉ đo thời gian chờ.

### Ví dụ với PostgreSQL

PostgreSQL có hai tham số thường được nhắc đến:

- `deadlock_timeout`: thời gian chờ trước khi hệ thống thực hiện kiểm tra deadlock. Đây là trì hoãn trước khi chạy detector, không phải thời hạn tối đa của mọi lần chờ khóa.
- `lock_timeout`: giới hạn thời gian một câu lệnh chờ để lấy khóa; khi vượt ngưỡng, câu lệnh bị hủy với lỗi timeout.

Hai tham số có thể được cấu hình độc lập. Chọn giá trị quá thấp có thể tạo thêm lỗi timeout hoặc chi phí kiểm tra; chọn quá cao có thể khiến ứng dụng phản hồi chậm khi có vấn đề. Cần điều chỉnh theo đặc tính tải và yêu cầu thời gian phản hồi.

## 10. Đọc ví dụ log deadlock

Khi điều tra deadlock, log hoặc báo cáo chẩn đoán của DBMS thường cho biết:

- Các transaction/session tham gia.
- Tài nguyên hoặc hàng bị khóa.
- Transaction nào đang giữ khóa.
- Transaction nào đang chờ khóa.
- Loại khóa và chế độ khóa xung đột.
- Transaction được chọn làm nạn nhân.
- Câu lệnh hoặc vị trí thực thi có liên quan, nếu DBMS ghi nhận được.

Từ thông tin đó, hãy dựng lại thứ tự lấy khóa. Ví dụ:

```text
Session 1:
  giữ X trên account A
  chờ X trên account B

Session 2:
  giữ X trên account B
  chờ X trên account A

Wait-for graph: S1 → S2 → S1
```

Sau đó kiểm tra mã ứng dụng để tìm hai đường xử lý lấy khóa theo thứ tự khác nhau. Trong ví dụ chuyển tiền, một luồng khóa A rồi B, luồng còn lại khóa B rồi A. Chuẩn hóa thứ tự lấy khóa là một cách trực tiếp để loại bỏ chu trình này.

Không nên chỉ nhìn câu SQL xuất hiện cuối cùng trong log rồi kết luận đó là nguyên nhân duy nhất. Deadlock là kết quả của sự kết hợp giữa nhiều transaction, các khóa chúng đang giữ và thứ tự yêu cầu khóa. Cần xem toàn bộ chu trình.

## 11. Giảm khả năng deadlock trước khi cần chọn victim

Deadlock detection là cơ chế phục hồi khi deadlock đã xảy ra. Ứng dụng vẫn nên thiết kế thao tác để giảm xác suất tạo chu trình.

### Lấy khóa theo thứ tự nhất quán

Nếu nhiều giao dịch cần khóa tài khoản A và B, hãy sắp xếp theo một quy tắc cố định, chẳng hạn tăng dần `account_id`:

```text
Luôn khóa tài khoản có id nhỏ trước,
sau đó mới khóa tài khoản có id lớn.
```

Nhờ vậy, một giao dịch không khóa A rồi chờ B trong khi giao dịch khác khóa B rồi chờ A.

### Giữ transaction ngắn

Không giữ khóa trong lúc chờ người dùng nhập liệu, gọi API bên ngoài hoặc xử lý một lượng lớn công việc không liên quan. Chuẩn bị dữ liệu trước khi mở transaction nếu có thể; sau khi bắt đầu transaction, chỉ thực hiện các bước cần thiết để bảo đảm tính nguyên tử và nhất quán.

### Dùng chỉ mục và điều kiện truy vấn phù hợp

Một truy vấn thiếu index có thể quét và khóa phạm vi lớn hơn dự kiến tùy DBMS và isolation level. Index phù hợp giúp tìm đúng hàng, giảm thời gian giữ khóa và giảm số giao dịch bị chặn.

### Cân nhắc cập nhật nguyên tử

Nếu quy tắc có thể biểu diễn trong một câu `UPDATE` có điều kiện, câu lệnh nguyên tử có thể giảm khoảng thời gian giữa đọc và ghi. Tuy nhiên, nếu nghiệp vụ phụ thuộc nhiều hàng hoặc nhiều bảng, vẫn cần cơ chế bảo vệ đầy đủ.

### Tránh nâng cấp khóa không cần thiết

Một số lịch thực thi có thể tạo deadlock khi nhiều giao dịch cùng đọc bằng khóa chia sẻ rồi đồng thời nâng cấp lên khóa độc quyền. Nếu đã biết thao tác sẽ cập nhật, dùng chiến lược khóa ghi phù hợp ngay từ đầu có thể giảm một số tình huống nâng cấp tranh chấp. Hành vi cụ thể tùy DBMS.

## 12. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| Có một giao dịch chờ khóa lâu là chắc chắn deadlock. | Cần có chu trình chờ; chờ một chiều có thể chỉ là blocking thông thường. |
| Deadlock detector hủy tất cả giao dịch trong chu trình. | Thường chọn một nạn nhân để rollback và phá chu trình; các giao dịch còn lại có thể tiếp tục. |
| Nạn nhân luôn là giao dịch mới nhất. | DBMS có thể cân nhắc chi phí rollback, ưu tiên và các yếu tố khác. |
| Deadlock victim chỉ rollback câu lệnh cuối. | Nhiều DBMS rollback toàn bộ transaction; cần xử lý theo hành vi cụ thể. |
| Lock timeout và deadlock detection là một cơ chế. | Timeout dựa trên thời gian chờ; deadlock detection dựa trên chu trình phụ thuộc. |
| Có thể retry riêng câu SQL bị lỗi. | Thường cần rollback và chạy lại toàn bộ transaction để đọc, kiểm tra và cập nhật nhất quán. |
| Retry ngay lập tức vô hạn sẽ giúp giao dịch thành công. | Retry cần giới hạn, backoff và chống lặp side effect; nếu không có thể làm tải tăng thêm. |

## 13. Tự kiểm tra

**Tình huống 1:** `T1` giữ `X(A)` và chờ `X(B)` do `T2` giữ. `T2` không chờ khóa nào khác và chuẩn bị commit. Đây đã là deadlock chưa?

**Đáp án:** Chưa. Chỉ có `T1` chờ `T2`; chưa có cạnh từ `T2` quay lại `T1`. Khi `T2` commit và nhả B, T1 có thể tiếp tục.

**Tình huống 2:** `T1` chờ `T2`, `T2` chờ `T3`, còn `T3` chờ `T1`. Wait-for graph có dạng gì và điều đó cho biết điều gì?

**Đáp án:** Đồ thị có chu trình `T1 → T2 → T3 → T1`. Đây là deadlock vì mỗi giao dịch trên chu trình đang chờ một giao dịch khác trong cùng chu trình nhả khóa.

**Tình huống 3:** DBMS chọn `T1` làm nạn nhân. Vì sao phải rollback thay đổi của T1 trước khi T2 tiếp tục sử dụng dữ liệu liên quan?

**Đáp án:** Các thay đổi của T1 chưa commit không được để lại như kết quả đã xác nhận. Rollback khôi phục trạng thái dữ liệu và giải phóng khóa, giúp T2 tiếp tục trên trạng thái hợp lệ.

**Tình huống 4:** Một transaction chờ khóa 10 giây rồi bị `lock timeout`. Không có giao dịch nào chờ ngược lại. Có thể kết luận deadlock không?

**Đáp án:** Không. Đây là timeout do vượt thời gian chờ. Deadlock cần một chu trình trong quan hệ chờ.

**Tình huống 5:** Ứng dụng nhận deadlock error rồi chỉ chạy lại câu `UPDATE` cuối cùng. Rủi ro là gì?

**Đáp án:** Các bước đọc và kiểm tra trước đó có thể dựa trên dữ liệu cũ. Cần rollback và chạy lại toàn bộ transaction, bao gồm đọc, kiểm tra và ghi.

**Tình huống 6:** Cùng một transaction bị chọn làm nạn nhân nhiều lần. Hiện tượng nào có thể xảy ra và cần cân nhắc điều gì?

**Đáp án:** Transaction có thể bị starvation. Chính sách chọn nạn nhân có thể cân nhắc tuổi giao dịch, số lần đã bị hủy hoặc ưu tiên để giảm tình trạng một giao dịch luôn bị loại.

Khi xử lý deadlock, hãy dựng wait-for graph từ các khóa đang giữ và các yêu cầu đang chờ, xác nhận chu trình, rồi xem tiêu chí DBMS dùng để chọn nạn nhân. Sau rollback, ứng dụng cần chạy lại toàn bộ transaction một cách có giới hạn và an toàn. Log deadlock chỉ ra chu trình đã xảy ra; việc sửa thứ tự lấy khóa, rút ngắn transaction và điều chỉnh truy vấn mới giúp giảm khả năng chu trình lặp lại.

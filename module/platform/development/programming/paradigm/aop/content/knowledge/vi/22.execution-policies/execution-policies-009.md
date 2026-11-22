# Đánh giá ảnh hưởng của mỗi chính sách tới lỗi và tác dụng phụ trong AOP

## 1. Mục tiêu: một chính sách thực thi không chỉ làm thay đổi luồng điều khiển

Trong lập trình hướng khía cạnh (Aspect-Oriented Programming, **AOP**), một **aspect** có thể áp dụng chính sách tại nhiều **join point** được chọn bằng **pointcut**. Ví dụ, quanh một thao tác nghiệp vụ có thể có advice kiểm tra quyền, mở giao dịch, thử lại lỗi tạm thời, đặt thời hạn chờ, dùng cache, giới hạn tải, ghi log hoặc ghi nhận kết quả.

Chính sách tưởng chừng chỉ bổ sung một hành động phụ nhưng có thể làm thay đổi nhiều đặc điểm quan sát được:

1. **Loại lỗi người gọi nhận được:** lỗi nguyên thủy được truyền tiếp, bị bọc, bị biến đổi, bị nuốt hoặc bị thay thế bởi lỗi của advice.
2. **Số lần hành vi đích chạy:** một lượt, nhiều lượt do retry, không lượt nào do cache hit/deny/open circuit, hoặc vẫn còn chạy sau timeout.
3. **Trạng thái tài nguyên:** transaction đã commit/rollback/chưa xác định, lock được giữ hoặc giải phóng, tài nguyên đã đóng đúng lúc chưa.
4. **Tác dụng phụ (side effects):** ghi dữ liệu, gửi email, gọi dịch vụ ngoài, phát thông điệp, ghi audit, tạo metric… có thể xảy ra một lần, nhiều lần, một phần hoặc không xảy ra.
5. **Thời điểm báo kết quả:** lời gọi trả về, transaction commit, tác vụ bất đồng bộ hoàn tất, hay tín hiệu từ hệ thống bên ngoài.

Bài này tập trung vào **cách đánh giá ảnh hưởng của từng chính sách đối với lỗi và tác dụng phụ**, sau đó ghép chúng thành một chuỗi advice có hành vi nhất quán. Khái niệm áp dụng cho AOP nói chung; cách khai báo thứ tự advice, loại join point và hành vi của cơ chế dệt mã phụ thuộc vào công cụ AOP cụ thể.

### Ba câu hỏi bắt buộc với mọi chính sách

Trước khi triển khai một advice, hãy hỏi:

- **Lỗi:** advice nhận, tạo, nuốt, bọc, chuyển đổi hoặc truyền tiếp những loại lỗi nào?
- **Tác dụng phụ:** proceed() có thể chạy bao nhiêu lần, phần nào có thể được hoàn tác, phần nào không?
- **Hợp đồng quan sát:** người gọi hoặc hệ thống đo lường thấy điều gì là thành công, thất bại, hủy bỏ hoặc kết quả chưa chắc chắn?

Ví dụ, nếu một advice retry gọi proceed() ba lần, tác dụng phụ bên trong có thể xuất hiện ba lần. Nếu một advice timeout ngừng *chờ* sau hai giây, công việc nền có thể tiếp tục tạo tác dụng phụ sau khi người gọi đã nhận lỗi timeout.

## 2. Mô hình đánh giá: join point, advice, policy và effect

**Join point** là điểm thực thi nơi cơ chế AOP có thể can thiệp, chẳng hạn thực thi một phương thức hoặc một lời gọi phương thức, tùy mô hình AOP. **Pointcut** là biểu thức chọn các join point; **advice** thực hiện chính sách khi join point được chọn.

Một around advice được hình dung như phép biến đổi một hành vi:

~~~text
P(action) = action mới được bao quanh bởi policy P

Ví dụ:
Retry(Transaction(action))
Transaction(Retry(action))
Record(Retry(Transaction(action)))
~~~

Các biểu thức trên mô tả **thứ tự lồng nhau**, không phải cú pháp nguồn của một thư viện. Khi advice ở ngoài gọi proceed(), nó chuyển quyền điều khiển vào lớp trong; khi proceed() trả về hoặc ném lỗi, lớp ngoài tiếp tục xử lý theo chính sách của mình.

Để đánh giá một policy, định nghĩa một bản mô tả tác động:

| Chiều đánh giá | Câu hỏi |
| --- | --- |
| Entry | Chính sách có cho chạy proceed() không? Có thể từ chối/chặn/bỏ qua không? |
| Execution count | proceed() được gọi 0, 1 hay nhiều lần? |
| Error channel | Lỗi đồng bộ, thất bại bất đồng bộ, lỗi commit, timeout, hủy có được nhìn thấy? |
| Error mapping | Chính sách rethrow, wrap, fallback, suppress hay tạo lỗi mới? |
| State & transaction | Policy chạy trong hay ngoài transaction? Có rollback-only, savepoint hoặc commit không chắc chắn? |
| Side effects | Effect nào xảy ra trước lỗi? Có được transaction hoàn tác thực sự không? |
| Ordering | Advice nào ở ngoài để thấy outcome cuối; advice nào ở trong để quan sát từng attempt? |
| Observability | Log, metric và audit đang đo một attempt, một invocation hay cả operation? |

Một policy an toàn trong một bối cảnh có thể không an toàn ở bối cảnh khác. Không thể khẳng định “retry luôn tốt”, “timeout luôn dừng tác vụ” hoặc “transaction sẽ rollback mọi thứ” mà chưa xác định ranh giới thực tế.

## 3. Phân loại lỗi trước khi đánh giá chính sách

Không nên gom toàn bộ trạng thái không thành công thành một loại exception chung.

### 3.1. Lỗi trước khi hành vi đích chạy

Ví dụ kiểm tra quyền thất bại, thiếu dữ liệu đầu vào hoặc giới hạn tần suất. Advice có thể **không gọi proceed()**. Như vậy side effect của hành vi đích không xảy ra, nhưng side effect do chính advice thực hiện (ghi log, tăng counter, truy vấn quyền) vẫn có thể xuất hiện.

### 3.2. Lỗi trong hành vi đích

Hành vi đã bắt đầu và có thể tác động một phần lên tài nguyên trước khi ném lỗi. Cần xác định các effect đó thuộc transaction nào và liệu cơ chế rollback có bao phủ chúng không.

### 3.3. Lỗi ở giai đoạn kết thúc

Một phương thức có thể trả về bình thường nhưng commit thất bại, ghi audit bắt buộc không thành công, hoặc gửi phản hồi thất bại. **Return bình thường của hàm nghiệp vụ** không chứng minh mọi nghĩa vụ sau đó đã hoàn tất.

### 3.4. Thất bại bất đồng bộ

Một phương thức trả về CompletionStage/Future/Publisher chưa hoàn tất. Exception xảy ra về sau không tự trở thành ngoại lệ được ném đồng bộ từ proceed(). Đánh giá phải tách **kết thúc lần gọi** khỏi **kết thúc tác vụ logic**.

### 3.5. Timeout, cancellation và kết quả chưa rõ

Timeout nhiều khi chỉ nói rằng người quan sát hết kiên nhẫn chờ; nó **không chứng minh** thao tác đã được hủy hoặc rollback. Một lỗi mạng đúng lúc commit có thể khiến kết quả trở thành **unknown/in-doubt**, cần kiểm tra trạng thái thay vì retry mù.

### 3.6. Lỗi của chính advice

Logging, metrics, cache, bộ kiểm tra quyền hoặc bộ quản lý transaction đều có thể ném lỗi. Phải phân biệt lỗi của **hành vi đích** và lỗi do **policy** tạo ra để không làm sai phân loại, retry ngoài ý muốn hoặc che mất nguyên nhân thực.

Một cách ghi outcome có ích:

~~~text
outcome:
  SUCCESS          hành vi hoàn tất theo hợp đồng
  BUSINESS_REJECT  kết quả hợp lệ nhưng nghiệp vụ từ chối
  RETRYABLE_ERROR  lỗi tạm thời, có thể xem xét thử lại
  PERMANENT_ERROR  lỗi không nên thử lại theo chính sách
  CANCELLED        có tín hiệu hủy theo API
  TIMED_OUT        quá thời hạn chờ đã định
  UNKNOWN          không thể khẳng định thành công hay thất bại
~~~

Đây chỉ là mô hình phân loại để tư duy. Trong hệ thống thật, outcome phụ thuộc hợp đồng API, transaction manager và trạng thái nghiệp vụ; không nhất thiết tất cả trạng thái đều biểu diễn bằng exception.

## 4. Bảng đánh giá các chính sách thường gặp

| Chính sách | Ảnh hưởng đến lỗi | Ảnh hưởng đến tác dụng phụ | Kiểm tra quan trọng |
| --- | --- | --- | --- |
| Kiểm tra đầu vào | Có thể từ chối trước proceed(); nếu đặt sai vị trí có thể bắt lỗi quá muộn | Thường tránh effect của hành vi đích khi từ chối | Validation có diễn ra trước mọi effect có liên quan không? |
| Authorization | Trả lỗi từ chối hoặc không gọi proceed() | Tránh effect khi không được phép; ghi audit từ chối vẫn có thể xảy ra | Có bị cache, fallback hoặc đường gọi khác vượt qua không? |
| Transaction | Commit, rollback hoặc báo trạng thái không chắc chắn | Hoàn tác các thay đổi trên tài nguyên tham gia transaction | Gọi ngoài hệ thống có thực sự tham gia transaction không? |
| Retry | Có thể biến lỗi attempt thành thành công cuối, hoặc ném lỗi cuối | Lặp proceed() và effect bên trong nhiều lần | Thao tác có idempotent không? Có giới hạn attempt/deadline không? |
| Timeout | Có thể tạo lỗi timeout dù công việc còn chạy | Effect có thể tiếp tục sau timeout | Timeout có hủy tác vụ thật không? Ai theo dõi kết quả về sau? |
| Circuit breaker | Có thể từ chối sớm khi mạch mở; giữ lỗi thực ở lượt probe | Không chạy hành vi đích khi bị chặn | Có phân biệt open-circuit rejection và backend failure không? |
| Rate limit/bulkhead | Từ chối hoặc xếp hàng, có thể phát sinh timeout lúc chờ | Giảm số lượt thực thi; tác vụ được nhận có thể còn đang chạy | Tài nguyên permit có được giải phóng ở mọi đường kết thúc? |
| Cache | Cache hit có thể bỏ qua hành vi đích; lỗi cache có thể gây lỗi mới | Bỏ qua cả effect trong action nếu hit; cache write có thể gây thêm effect | Hành vi được cache có thuần đọc hay có effect bắt buộc? |
| Fallback | Chuyển lỗi thành giá trị thay thế | Có thể che effect một phần đã xảy ra trước lỗi | Fallback có tương thích hợp đồng nghiệp vụ không? |
| Logging/metrics | Observer có thể ném lỗi, thay exception gốc nếu thiết kế sai | Tạo effect quan sát; có thể ghi lặp theo từng attempt | Best effort hay bắt buộc? Ghi theo attempt hay operation? |
| Audit bắt buộc | Lỗi audit có thể khiến toàn operation thất bại | Ghi dữ liệu bền, có thể cần transaction riêng/cùng transaction | Audit thất bại có tồn tại sau rollback không? |
| Idempotency/deduplication | Có thể trả kết quả đã lưu hoặc báo conflict | Ngăn effect trùng nếu bảo đảm atomic phù hợp | Key có đúng phạm vi nghiệp vụ, thời hạn và ràng buộc duy nhất không? |

Bảng này là công cụ đặt câu hỏi, không phải cam kết rằng mọi framework thực thi giống nhau. Phần dưới phân tích cơ chế và các tổ hợp quan trọng.

## 5. Chính sách validation và authorization: tác động trước proceed()

Một advice kiểm tra hợp lệ hoặc quyền truy cập thường quyết định:

~~~text
if request invalid or unauthorized:
    reject
else:
    proceed()
~~~

Khi từ chối **trước proceed()**, hành vi đích không chạy. Đây là điểm mạnh: ngăn các effect nghiệp vụ mà hành vi đích có thể tạo. Tuy nhiên vẫn có ba rủi ro:

1. **Điểm cắt không bao phủ đường gọi thật:** một lời gọi không đi qua interception có thể bỏ qua validation/authorization; phải kiểm tra cơ chế weaving và các đường gọi thực tế.
2. **Đặt sai vị trí:** nếu một advice tạo side effect hoặc gọi hàm nghiệp vụ nằm ngoài lớp kiểm tra quyền, side effect ấy vẫn có thể xảy ra dù bên trong bị từ chối.
3. **Ghi nhận và lỗi phụ:** tra cứu quyền hoặc ghi audit từ chối có thể thất bại. Cần quy định hành vi khi hệ thống cấp quyền không sẵn sàng, ưu tiên an toàn cho thao tác nhạy cảm.

Ví dụ:

~~~text
Authorization(Transaction(operation))
~~~

Từ chối quyền trước khi mở transaction ở lớp trong, giảm công việc tài nguyên. Với:

~~~text
Transaction(Authorization(operation))
~~~

transaction được mở trước khi biết yêu cầu có quyền hay không; tùy trường hợp có thể là chi phí không cần thiết. Cả hai đều có thể đúng về mặt chức năng khi không có effect nào trước authorization, nhưng khác chi phí và ranh giới thất bại.

**Không giả định một thứ tự duy nhất luôn tối ưu:** với một số operation, authorization phụ thuộc dữ liệu nhất quán bên trong transaction. Cần phân biệt kiểm tra nhận dạng chung và kiểm tra quyền gắn với bản ghi cụ thể.

## 6. Chính sách transaction: phân loại effect có thể rollback

Transaction không phải “cỗ máy hoàn tác mọi tác dụng phụ”. Ranh giới rollback chỉ bao phủ tài nguyên thực sự tham gia vào transaction theo hợp đồng của resource manager.

### 6.1. Effect nằm trong transaction

Ví dụ cập nhật hai bảng trong cùng một database transaction. Nếu transaction rollback, những cập nhật chưa commit được hoàn tác theo bảo đảm của database.

### 6.2. Effect ngoài transaction

Ví dụ trong cùng một lời gọi:

~~~text
begin database transaction
update order status
send email to customer
error occurs
rollback database
~~~

Email đã gửi không được “thu hồi” bởi rollback database. Nếu retry toàn bộ lời gọi, email có thể bị gửi thêm lần nữa.

Tương tự với cuộc gọi HTTP, thanh toán ngoài, thông điệp gửi trực tiếp sang broker, ghi file hoặc thao tác trên tài nguyên không tham gia transaction.

### 6.3. Lỗi tại commit

Một lời gọi nghiệp vụ có thể trả về thành công nhưng transaction commit xảy ra sau đó và thất bại. Nếu ghi kết quả “thành công đã cam kết” trước commit, log/audit có thể sai.

Một số failure tại commit có trạng thái **không chắc chắn**: phản hồi commit bị mất nhưng thay đổi đã được lưu bền. Retry một thao tác tạo đơn hàng mà không có khóa chống trùng có thể tạo hai đơn.

### 6.4. Lỗi rollback và cleanup

Rollback hoặc đóng tài nguyên cũng có thể ném lỗi. Transaction advice phải giữ đủ thông tin về lỗi ban đầu và lỗi phụ để chẩn đoán. Nếu advice dọn dẹp ném lỗi trong finally, lỗi đó có thể che mất lỗi đích nếu không được xử lý có chủ đích.

### 6.5. Câu hỏi đánh giá transaction

- Transaction bắt đầu trước hành vi nào và commit sau hành vi nào?
- Một transaction mới được tạo hay tham gia transaction có sẵn?
- Những resource nào tham gia cùng ranh giới atomicity?
- Có thể có rollback-only, savepoint, trạng thái aborted hoặc commit in-doubt không?
- Logging/audit/sự kiện ngoài transaction có cần được giữ hoặc chống trùng không?
- Sau khi transaction kết thúc, advice còn giữ connection/lock/context trên thread không?

## 7. Chính sách retry: lỗi bị thử lại và effect bị nhân số lượt

Một retry advice có thể gọi proceed() nhiều lần:

~~~text
for attempt in 1..maxAttempts:
    try:
        return proceed()
    catch error:
        if not retryable(error) or attempt is last:
            throw error
        apply backoff
~~~

Nếu hành vi đích có effect, số lần gọi proceed() là một phần của **hợp đồng thực thi**. Các effect sau có thể nhân theo số attempt: ghi mới một bản ghi không có unique key, phát thông điệp, gửi email, gọi thanh toán, tăng counter, ghi audit per-attempt.

Retry chỉ an toàn khi ít nhất một trong các điều kiện được đáp ứng:

- Hành vi có tính idempotent theo hợp đồng nghiệp vụ.
- Mỗi attempt bị lỗi đã hoàn tác được **toàn bộ effect có liên quan**, không còn effect ngoài transaction.
- Có deduplication/idempotency key bền vững, unique constraint hoặc cơ chế điều phối kiểm soát việc lặp.
- Operation và side effect có cơ chế đối soát khi outcome không chắc chắn.

**Retryable** không đồng nghĩa **retry safe**. Một lỗi mạng có thể chỉ là tạm thời, nhưng thao tác phía server đã hoàn tất trước khi kết nối đứt. Phải đánh giá cả khả năng phục hồi lỗi *và* an toàn khi lặp effect.

Các giới hạn thiết yếu:

1. Max attempts và retry budget để tránh vòng lặp vô hạn.
2. Backoff/jitter để không tạo retry storm khi hệ thống đang quá tải.
3. Deadline tổng để operation không vượt thời gian cam kết.
4. Phân loại lỗi rõ ràng, không retry lỗi dữ liệu hoặc policy/telemetry một cách vô điều kiện.
5. Xử lý cancellation và thread interruption đúng hợp đồng.
6. Phân biệt outcome của từng attempt với outcome cuối sau retry.

Một lỗi cố định như dữ liệu đầu vào không hợp lệ thường không thể được sửa bằng cách lặp lại hành vi giống hệt.

## 8. Thứ tự transaction và retry có thể đổi khả năng phục hồi

Hai chuỗi này có khác biệt cốt lõi:

~~~text
Retry(Transaction(operation))
~~~

~~~text
Transaction(Retry(operation))
~~~

### 8.1. Retry nằm ngoài Transaction

Mỗi lần proceed() đi vào Transaction có thể tạo một giao dịch mới:

~~~text
attempt 1 -> T1 begin -> operation lỗi -> T1 rollback
attempt 2 -> T2 begin -> operation thành công -> T2 commit
~~~

Mô hình này thường phù hợp cho việc retry **toàn bộ đơn vị công việc giao dịch** sau một lỗi khiến transaction không còn an toàn để tiếp tục. Nó cũng cho phép policy retry nhìn thấy cả lỗi được Transaction truyền ra ở commit/rollback.

Nhưng chỉ có transaction mới khi wrapper thực sự **tạo** giao dịch mới. Nếu policy propagation khiến wrapper luôn tham gia transaction ngoài, không thể kết luận mỗi attempt độc lập chỉ từ hình thức lồng nhau.

### 8.2. Transaction nằm ngoài Retry

~~~text
T1 begin
attempt 1 -> operation lỗi
attempt 2 -> operation thành công
T1 commit?
~~~

Một số hệ thống đánh dấu T1 là aborted/rollback-only sau lần lỗi đầu. Retry bắt exception không tự đặt T1 trở về trạng thái hợp lệ. Attempt thứ hai có thể thất bại hoặc commit cuối phải rollback.

Ngoài ra, khi Retry chờ backoff trong transaction, lock và tài nguyên có thể bị giữ lâu, làm nặng thêm tranh chấp.

### 8.3. Savepoint

Nếu muốn retry một phần trong cùng transaction, savepoint có thể phù hợp **nếu** resource manager hỗ trợ việc phục hồi sau loại lỗi đó. Savepoint không giống một transaction top-level mới, không đảm bảo khôi phục effect ngoài database và không cứu được mọi loại lỗi làm transaction bị hủy bỏ.

## 9. Chính sách timeout và cancellation: “không chờ nữa” khác “đã dừng”

Một timeout advice có thể áp đặt thời hạn cho operation. Nhưng cần phân biệt:

- **Timeout của người chờ:** caller ngừng chờ và nhận lỗi; tác vụ có thể vẫn chạy.
- **Timeout của lời gọi mạng:** kết nối hoặc request bị kết thúc ở phía caller; server có thể đã hoàn tất effect.
- **Timeout của transaction:** hệ thống có thể tự đánh dấu transaction rollback/đóng; hành vi cụ thể tùy resource manager.
- **Deadline cho chuỗi retry:** thời hạn của toàn operation, không chỉ từng attempt.

Tình huống:

~~~text
t=0   client gọi createPayment
t=2s  client timeout và trả lỗi cho người dùng
t=3s  server thực tế đã ghi thanh toán
t=4s  client retry mà không có idempotency key
~~~

Retry sau timeout có thể tạo thanh toán thứ hai. Vì vậy timeout cần đi kèm **cancellation semantics**, idempotency và cách kiểm tra outcome.

Một cancellation signal cũng không luôn dừng công việc: có API chỉ hoàn tất future với trạng thái hủy, trong khi underlying task đã bắt đầu vẫn tiếp tục. Không ghi “operation rolled back” chỉ vì cancellation được yêu cầu.

Với tác vụ async, around advice bao **phương thức trả về future** thường chỉ kết thúc lúc future được trả về; nó không tự chờ completion. Nếu policy cần đo timeout hoặc ghi outcome logic, phải theo dõi tín hiệu hoàn tất của API phù hợp và bảo đảm transaction/context có vòng đời tương thích.

## 10. Chính sách circuit breaker, bulkhead và rate limit: lỗi do từ chối

Những chính sách này thường có khả năng **không gọi proceed()**.

### Circuit breaker

Khi circuit mở, lời gọi có thể bị từ chối nhanh mà chưa chạm hệ thống đích. Đây là outcome khác với backend thực sự xử lý rồi thất bại. Trong trạng thái half-open, một số lượt probe được phép gọi để đánh giá khả năng phục hồi.

Điểm cần xác định là **lỗi nào tính vào bộ đếm breaker**. Nếu đếm cả từ chối do validation hoặc lỗi business hợp lệ, breaker có thể mở không đúng nguyên nhân. Nếu Retry nằm trong Breaker, một lượt call breaker có thể bao gồm nhiều attempts; nếu Retry nằm ngoài Breaker, mỗi attempt có thể đi qua breaker riêng và bị chặn tùy trạng thái. Sự khác biệt phải phù hợp mục tiêu quan sát.

### Bulkhead và giới hạn đồng thời

Một bulkhead có thể giới hạn số luồng, semaphore permit hoặc tác vụ được phép chạy. Khi không còn capacity, policy có thể xếp hàng hoặc từ chối.

Những rủi ro thường gặp:

- Nếu permit không được release trong finally hoặc callback hoàn tất đúng vòng đời, tải sẽ giảm dần do leak.
- Nếu giải phóng permit ngay khi phương thức trả về future, trong khi công việc async còn chạy, hệ thống có thể cho phép số tác vụ thực vượt giới hạn mong muốn.
- Retry ngay khi bị từ chối do quá tải có thể làm tải trầm trọng hơn.

### Rate limit

Rate limit thường giới hạn số lượt **được nhận** trong một cửa sổ, không chứng minh các lượt đã được nhận hoàn tất. Nếu nằm trong Retry, mỗi attempt có thể tiêu một quota; nếu ở ngoài, một operation với nhiều attempts có thể chỉ tiêu một quota. Cần quyết định chính sách muốn giới hạn **người dùng tạo operation** hay **tổng số request đi xuống downstream**.

Vì vậy không thể đánh giá rate limiter chỉ qua số lượng lỗi 429/từ chối; phải kiểm tra ranh giới tính quota và số effect thực sự xảy ra.

## 11. Chính sách cache và fallback: thành công có thể không đi qua nghiệp vụ đích

### 11.1. Cache

Ví dụ:

~~~text
Cache(operation)
~~~

Nếu cache hit, advice có thể trả giá trị **mà không gọi operation**. Điều này tốt cho truy vấn thuần đọc có chính sách freshness phù hợp, nhưng nguy hiểm nếu operation còn tạo effect bắt buộc như ghi audit hoặc cập nhật lần truy cập.

Một cache advice có thể làm biến đổi lỗi:

- Cache backend lỗi: fail-open để gọi origin, hay fail-closed báo lỗi?
- Origin lỗi: trả stale value hay truyền lỗi?
- Ghi cache thất bại: có làm thất bại operation đã chạy thành công không?
- Cache key thiếu tenant/permission: có nguy cơ đọc sai dữ liệu hoặc rò thông tin không?

Một cache miss kết hợp retry cũng có thể tạo thundering herd khi nhiều request đồng thời cùng gọi origin; cần đánh giá đồng bộ tải, thời hạn và khả năng quan sát.

### 11.2. Fallback

Fallback có thể chuyển exception thành giá trị thay thế:

~~~text
try:
    return proceed()
catch:
    return fallbackValue
~~~

Điều này chỉ hợp lệ khi **hợp đồng nghiệp vụ cho phép**. Trả “thành công rỗng” khi thao tác đặt hàng đã thất bại có thể che giấu dữ liệu chưa được lưu; trả dữ liệu cache hơi cũ cho màn hình tham khảo có thể chấp nhận nếu người dùng được thông tin rõ.

Một operation có thể đã tạo một phần effect rồi mới ném lỗi. Fallback không đảo ngược các effect đó, nên không được tự coi fallback success là nguyên trạng “chưa có gì xảy ra”.

Cần phân biệt **backend failed**, **fallback applied** và **end-user outcome**. Nếu metric chỉ nhìn thấy giá trị trả về cuối cùng, một failure được che bởi fallback có thể biến mất khỏi thống kê lỗi hạ tầng.

## 12. Chính sách ghi log, metric và audit: quan sát cũng tạo tác dụng phụ

Logging/metrics là concern quan sát, nhưng exporter và recorder vẫn có thể:

- Phân bổ bộ nhớ, giữ tham chiếu, tạo tác vụ nền.
- Gây block khi bộ đệm đầy hoặc kênh lưu trữ chậm.
- Ném exception, làm thay đổi luồng lỗi.
- Ghi trùng do retry hoặc advice áp dụng ở nhiều lớp.
- Ghi dữ liệu nhạy cảm nếu lấy quá nhiều thông tin ở join point.

Cần xác định hai loại:

**Best effort observer:** lỗi của việc ghi log/metric không được làm đổi kết quả nghiệp vụ ngoài ý muốn. Nếu cần, bắt exception của observer và ghi cảnh báo qua kênh dự phòng an toàn, tránh vòng lặp gọi chính recorder đang lỗi.

**Mandatory audit:** bắt buộc ghi bằng chứng theo yêu cầu nghiệp vụ hoặc quy định. Đây là một bước có thể làm operation thất bại; cần thiết kế giao dịch, độ bền và xử lý trùng lặp rõ ràng. Không thể gọi nó là “chỉ quan sát” rồi tùy tiện nuốt lỗi.

### 12.1. Recorder theo attempt và recorder theo operation

Một composition hữu ích:

~~~text
RecordFinal(
    Retry(
        RecordAttempt(
            Transaction(
                operation
            )
        )
    )
)
~~~

- RecordAttempt đặt ngoài Transaction để biết outcome của mỗi attempt **sau xử lý giao dịch**.
- Retry có thể bỏ qua lỗi attempt để tiếp tục attempt mới.
- RecordFinal ở ngoài Retry ghi **kết quả cuối** của cả operation sau tất cả attempts.

Nếu RecordAttempt ghi failure ở attempt đầu nhưng attempt thứ hai thành công, **operation cuối có success**. Đây không phải mâu thuẫn, bởi hai bản ghi có đơn vị đếm khác nhau.

### 12.2. Lỗi recorder có thể kích hoạt retry không mong muốn

Nếu RecordAttempt là lớp nằm **trong Retry** và nó ném lỗi sau khi Transaction đã commit, Retry có thể tưởng operation thất bại và gọi lại toàn bộ nghiệp vụ. Điều này đặc biệt nguy hiểm: **nghiệp vụ đã commit nhưng lại được chạy lần nữa chỉ vì log lỗi**.

Vì vậy, với best effort recorder, phải cô lập lỗi recorder. Với mandatory audit, cần xác định ranh giới transactional và idempotency từ đầu; không tùy tiện đặt recorder trong Retry rồi dùng phân loại exception chung.

### 12.3. Ghi event sau commit và khoảng trống do crash

Thứ tự:

~~~text
database commit
process crash
publish event
~~~

có thể làm event không bao giờ được gửi. Đổi thành publish trước commit lại có thể phát một event cho transaction cuối cùng bị rollback.

Nếu cần gắn cập nhật database và ý định gửi event, một giải pháp phổ biến là **transactional outbox**: trong cùng giao dịch lưu dữ liệu nghiệp vụ và outbox record; worker phát event sau commit và có khả năng retry. Vì lần gửi có thể bị lặp sau crash, consumer vẫn cần idempotency/deduplication. Outbox không tự tạo “exactly once” toàn hệ thống.

## 13. Ví dụ Java 17+: một retry có thể lặp side effect ngoài transaction

Ví dụ sau mô phỏng ba advice bằng các wrapper Java thuần. Nó cố tình tạo một **effect giả định ngoài transaction** trước khi ném lỗi tạm thời ở attempt đầu. Transaction wrapper chỉ ghi các sự kiện begin, commit, rollback để dễ quan sát: **đây không phải một transaction database thật** và bản ghi side effect trong ví dụ không được khôi phục khi rollback.

Tạo tệp **PolicyEffectDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public final class PolicyEffectDemo {
    @FunctionalInterface
    interface Action {
        String run();
    }

    static final class TransientFailure extends RuntimeException {
        TransientFailure() {
            super("temporary failure");
        }
    }

    static final List<String> events = new ArrayList<>();
    static int transactionNumber = 0;
    static int businessNumber = 0;

    static Action transaction(Action next) {
        return () -> {
            int tx = ++transactionNumber;
            events.add("tx " + tx + " begin");
            try {
                String result = next.run();
                events.add("tx " + tx + " commit");
                return result;
            } catch (RuntimeException failure) {
                events.add("tx " + tx + " rollback");
                throw failure;
            }
        };
    }

    static Action retry(Action next, int maxAttempts) {
        if (maxAttempts < 1) {
            throw new IllegalArgumentException("maxAttempts must be positive");
        }
        return () -> {
            for (int attempt = 1; attempt <= maxAttempts; attempt++) {
                events.add("attempt " + attempt);
                try {
                    return next.run();
                } catch (TransientFailure failure) {
                    if (attempt == maxAttempts) {
                        throw failure;
                    }
                }
            }
            throw new AssertionError("unreachable");
        };
    }

    static Action recordFinal(Action next) {
        return () -> {
            try {
                String result = next.run();
                events.add("final success");
                return result;
            } catch (RuntimeException failure) {
                events.add("final failure");
                throw failure;
            }
        };
    }

    static Action business() {
        return () -> {
            int call = ++businessNumber;
            events.add("business " + call);
            // Giả lập một effect bên ngoài transaction của database.
            events.add("external send " + call);
            if (call == 1) {
                throw new TransientFailure();
            }
            return "OK";
        };
    }

    public static void main(String[] args) {
        Action combined = recordFinal(retry(transaction(business()), 2));
        String result = combined.run();

        for (String event : events) {
            System.out.println(event);
        }
        System.out.println("caller " + result);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac PolicyEffectDemo.java
java PolicyEffectDemo
~~~

Stdout chính xác:

~~~text
attempt 1
tx 1 begin
business 1
external send 1
tx 1 rollback
attempt 2
tx 2 begin
business 2
external send 2
tx 2 commit
final success
caller OK
~~~

**Kết luận từ ví dụ:**

- Retry gọi hành vi đích **hai lần**.
- Transaction của attempt thứ nhất xử lý nhánh rollback, attempt thứ hai xử lý nhánh commit.
- “External send” xuất hiện **hai lần**; rollback trong mô hình không có cách tự thu hồi effect ấy.
- RecordFinal ghi **một success cuối** vì operation trả về thành công sau retry.
- Nếu external send là chuyển tiền thật, việc lặp như vậy có thể là lỗi nghiêm trọng. Hệ thống phải đưa vào idempotency/deduplication hoặc tổ chức effect theo một giao thức an toàn hơn.

Không nên dùng code demo này như transaction manager thật. Nó cũng không mô phỏng lỗi commit, thread interruption hay concurrency. Điểm cần học là **thứ tự wrapper quyết định số lần proceed() chạy, trong khi rollback chỉ có tác dụng trong phạm vi tài nguyên nó kiểm soát**.

## 14. Idempotency và bảo đảm không lặp effect

Một thao tác **idempotent** có thể được gọi nhiều lần với cùng ý định nghiệp vụ mà không làm nhân đôi effect theo hợp đồng.

Ví dụ tạo thanh toán:

~~~text
client dùng idempotencyKey = payment-request-104
attempt 1: phía xử lý commit nhưng phản hồi bị mất
attempt 2: cùng key -> hệ thống tìm thấy kết quả đã lưu
           -> trả lại kết quả trước đó, không tạo khoản thu mới
~~~

Để vận hành đúng dưới nhiều request đồng thời, cần cơ chế bền và atomic thích hợp, như unique constraint trên khóa nghiệp vụ cùng logic “tạo hoặc đọc kết quả đã tồn tại” trong transaction. Kiểm tra tồn tại ở một bước riêng rồi insert mà không có ràng buộc có thể vẫn xảy ra race.

Phân biệt:

| ID | Dùng để làm gì? |
| --- | --- |
| Correlation ID | Nhóm log/sự kiện của cùng một luồng xử lý |
| Attempt ID | Phân biệt mỗi lần retry |
| Idempotency key | Chống thực hiện trùng một ý định nghiệp vụ theo hợp đồng |
| Transaction ID | Nhận diện đơn vị giao dịch theo cơ chế tài nguyên |

Không tự lấy một correlation ID cho toàn phiên làm khóa idempotency cho mọi thao tác: một phiên có thể chứa nhiều thanh toán hợp lệ, còn một idempotency key phải xác định đúng **một ý định cần chống lặp**.

Một side effect đã thực hiện có thể không hoàn tác được hoàn toàn. Khi đó thiết kế có thể cần **compensation** (hành động bù) thay vì rollback nguyên tử. Ví dụ hoàn tiền sau khi thanh toán thành công là một nghiệp vụ mới có thể thất bại riêng; nó không tương đương việc thanh toán chưa từng xảy ra.

## 15. Chính sách lỗi cần giữ nguyên nguyên nhân và tính minh bạch

Một around advice thường có nhánh:

~~~text
try:
    return proceed()
catch failure:
    observe(failure)
    throw failure
finally:
    restore context
~~~

Nếu observe() hoặc restore() ném lỗi không kiểm soát, chúng có thể **che lỗi gốc**. Các vấn đề phổ biến:

- Ghi log thất bại làm một lời gọi trước đó thành công trở thành exception.
- Dọn dẹp tài nguyên thất bại che exception ban đầu.
- Fallback bắt quá rộng và biến lỗi lập trình nghiêm trọng thành kết quả giả bình thường.
- Retry bắt mọi RuntimeException, gồm lỗi validation hoặc lỗi của recorder, rồi lặp nghiệp vụ.
- Advice bọc tất cả exception thành một kiểu chung khiến caller mất khả năng phân biệt retryable và permanent.

Không nhất thiết phải luôn giữ nguyên cùng một instance exception: một số tầng API có chủ đích cần chuyển đổi kiểu lỗi. Nhưng phải **giữ causal chain**, ghi rõ hợp đồng error mapping và không đánh tráo business rejection với sự cố hạ tầng.

Với Java, ngoại lệ thứ cấp có thể được đính kèm dưới dạng suppressed exception khi thích hợp, thay vì làm mất nguyên nhân gốc. Với Errors hoặc cancellation, chính sách phải tuân theo hợp đồng runtime, không tùy tiện coi chúng là lỗi thường có thể retry.

## 16. Thứ tự các chính sách quyết định ai nhìn thấy lỗi nào

Xét:

~~~text
Retry(Fallback(operation))
~~~

Nếu Fallback bắt lỗi rồi trả một giá trị thay thế, Retry **không nhìn thấy lỗi** để thử lại. Ngược lại:

~~~text
Fallback(Retry(operation))
~~~

Retry có thể thử đủ số lượt trước, sau đó Fallback mới quyết định trả giá trị thay thế.

Tương tự:

~~~text
Timeout(Retry(operation))
~~~

có thể áp thời hạn tổng cho toàn chuỗi retry, trong khi:

~~~text
Retry(Timeout(operation))
~~~

có thể cho mỗi attempt một thời hạn riêng nhưng làm tổng thời gian lớn hơn dự kiến, nếu không có deadline tổng. Đây là mô hình logic; ngữ nghĩa timeout phụ thuộc implementation và loại tác vụ.

Với cache:

~~~text
Cache(Record(operation))
~~~

cache hit bỏ qua Record bên trong. Nếu cần metric cho **mọi yêu cầu kể cả cache hit**, recorder phải đặt ở lớp nhìn thấy mọi lượt yêu cầu hoặc instrument cache hit riêng. Nếu cache chỉ được phép khi operation có thể bỏ qua an toàn, cần đánh giá effect nghiệp vụ trước khi bật cache.

Với breaker:

~~~text
Retry(Breaker(operation))
~~~

retry có thể liên tục bị từ chối bởi breaker đang mở; tạo thêm attempt mà không chạy backend có thể không giúp ích. Với:

~~~text
Breaker(Retry(operation))
~~~

một lần gọi breaker có thể chứa nhiều backend attempts. Điều cần đo là **backend attempt failure** hay **operation failure**; xác định rõ trước khi chọn thứ tự.

Với recorder:

~~~text
RecordFinal(Retry(RecordAttempt(Transaction(operation))))
~~~

Recorder ngoài cùng thấy outcome cuối; recorder trong retry thấy từng attempt sau khi transaction hoàn tất. Nếu RecordAttempt là best effort, lỗi ghi nhận không được làm Retry chạy lại nghiệp vụ đã commit.

**Quy tắc:** vẽ chuỗi advice theo đúng thứ tự thực thi, liệt kê nơi lỗi có thể phát sinh và từng vị trí có thể bỏ qua proceed(), gọi lại proceed() hoặc biến đổi kết quả.

## 17. Ma trận thất bại và effect để review từng chính sách

Trước khi triển khai, lập bảng theo những failure point thực sự của operation:

| Thời điểm thất bại | Transaction | Retry | Timeout | Recorder/Audit | Tác dụng phụ cần xem |
| --- | --- | --- | --- | --- | --- |
| Bị chặn trước proceed() | Thường chưa cần transaction nếu đặt ở ngoài | Không nên retry vô điều kiện | Không nhất thiết có tác vụ nền | Ghi lý do từ chối theo chính sách | Không có effect của operation; advice vẫn có effect |
| Trong validation/business logic | Rollback những thay đổi có tham gia | Chỉ retry lỗi tạm thời và an toàn | Có thể đang chạy đến lúc deadline | Đánh dấu attempt failure, phân biệt business reject | Effect trước lỗi có thể còn tồn tại |
| Tại commit | Kết quả có thể failure hoặc unknown | Không retry mù nếu commit có thể đã thành công | Timeout có thể che outcome commit | Chỉ ghi committed khi xác nhận | Database có thể đã thay đổi |
| Khi publish ra hệ thống ngoài | DB commit không đồng nghĩa publish thành công | Retry publish có thể phát trùng | Timeout send không chứng minh không nhận | Audit/event cần cơ chế bền | Email/message/payment ngoài transaction |
| Khi observer/metrics lỗi | Thường không liên quan rollback business | Không cho lỗi telemetry tự retry business | Ghi log có thể gây nghẽn | Best effort hoặc mandatory phải rõ | Side effect ghi nhận có thể trùng/mất |
| Khi caller timeout/hủy | Tùy transaction manager/tác vụ | Ngừng tạo attempt nếu hết deadline | Có thể dừng chờ nhưng task còn chạy | Phân biệt timeout với actual failure | Effect có thể xảy ra sau phản hồi lỗi |

Một mẫu đánh giá theo policy trong review:

~~~text
Policy: Retry
Join point: submitPayment(...)
Scope: một payment operation
proceed() count: từ 1 đến 3
Retryable failures: các lỗi hạ tầng cụ thể đã được định nghĩa
Non-retryable: sai dữ liệu, từ chối nghiệp vụ
Transactional resource: database payment records
External effects: payment gateway call
Unknown outcome: có thể nếu timeout/loss of acknowledgment
Idempotency: payment request key, enforced at durable boundary
Logging: attempt riêng; final outcome riêng
Cancellation/deadline: không bắt đầu attempt mới sau deadline
QA: fault injection ở trước commit, tại commit và sau send
~~~

Thông tin trên là **một ví dụ phân tích**, không phải cam kết mọi hệ thanh toán đều có cùng quy tắc retry.

## 18. Đo lường tác động: metric đúng đơn vị

Một chính sách có thể làm tăng số attempt mà không làm tăng số operation gốc.

Ví dụ có 100 operation gốc; trong đó 15 operation cần retry thêm đúng một lần và tất cả cuối cùng đều thành công:

- **operations_total = 100**.
- **attempts_total = 115**.
- **operations_failed_total = 0**.
- **attempts_failed_total = 15** nếu mỗi attempt đầu trong nhóm retry thất bại và các attempt khác thành công.
- **operations_retried_total = 15**.

Nếu dùng số attempt lỗi để báo 15% operation cuối thất bại thì sai. Cần recorder ở đúng ranh giới:

- **Invocation duration:** thời gian một lần lời gọi join point trả về/throw.
- **Attempt duration:** thời gian của một attempt, có thể gồm transaction commit/rollback.
- **Operation duration:** thời gian của toàn operation, gồm backoff/retry.
- **Async completion duration:** thời gian đến tín hiệu hoàn tất logic, không phải chỉ đến khi trả về future.

Để tránh metric cardinality quá cao, không sử dụng correlation ID, attempt ID, idempotency key hoặc mã đơn hàng cá biệt làm nhãn time series. Những ID ấy phù hợp để truy vấn log và trace hơn.

## 19. Kiểm thử chính sách bằng fault injection

Để đánh giá đúng ảnh hưởng tới lỗi và side effect, kiểm tra **chuỗi sự kiện và số lần xảy ra**, không chỉ assert rằng kết quả cuối là "OK".

### Những kịch bản tối thiểu

1. **Thành công ngay attempt đầu:** transaction commit một lần; recorder final ghi success một lần.
2. **Lỗi transient trước side effect:** retry theo budget, kết quả cuối và số effect đúng kỳ vọng.
3. **Lỗi sau side effect nhưng trước commit:** xác minh side effect nào được rollback, side effect nào còn tồn tại; nếu retry thì không nhân đôi effect ngoài ý muốn.
4. **Lỗi tại commit:** phân biệt failure chắc chắn và unknown; không gắn nhãn committed success trước thời điểm xác nhận.
5. **Lỗi permanent:** không retry; người gọi thấy nguyên nhân rõ ràng.
6. **Timeout khi tác vụ vẫn chạy:** kiểm tra có effect xuất hiện sau thời điểm timeout không, cancellation được thực thi theo hợp đồng không.
7. **Recorder best effort gặp lỗi:** không làm business chạy lại hay làm mất lỗi gốc.
8. **Cache hit hoặc breaker mở:** proceed() được gọi 0 lần; metric request vẫn được cập nhật nếu cần.
9. **Concurrent requests cùng idempotency key:** chỉ một effect nghiệp vụ được phép theo hợp đồng, các lượt còn lại nhận kết quả hoặc conflict nhất quán.
10. **Transaction có sẵn ở lớp ngoài:** xác minh chính sách propagation, rollback-only và liệu Retry có thực sự dùng transaction mới.
11. **Async completion thất bại:** advice phải ghi outcome dựa trên completion signal nếu mục tiêu là theo dõi toàn operation.
12. **Nhiều aspect cùng match:** kiểm tra precedence/order được cấu hình thật, kể cả các đường gọi bypass instrumentation.

### Sổ sự kiện cho kiểm thử

Có thể tiêm một recorder đơn giản chỉ tích lũy event trong test:

~~~text
[
  "attempt=1",
  "tx=1 begin",
  "business=1",
  "external-effect=1",
  "tx=1 rollback",
  "attempt=2",
  "tx=2 begin",
  "business=2",
  "external-effect=2",
  "tx=2 commit",
  "final=success"
]
~~~

Sau đó assert **thứ tự**, **số lần side effect xảy ra**, **số transaction commit/rollback** và **outcome đúng cấp**. Với transaction thật, vẫn cần integration test với resource manager; một fake wrapper in sự kiện không chứng minh được rollback, lock và commit semantics của database thực.

### Bảng rủi ro để quyết định

Không nên chỉ gán “pass” cho toàn operation. Với mỗi effect, phân tích mức độ nghiêm trọng:

| Effect | Nếu lặp | Nếu mất | Nếu xảy ra sau timeout | Biện pháp |
| --- | --- | --- | --- | --- |
| Đọc dữ liệu | Thường tăng chi phí | Có thể thiếu kết quả | Có thể hao tài nguyên | Timeout, cache, rate limit |
| Ghi số dư/thanh toán | Có thể mất tiền hoặc thu trùng | Không hoàn tất nghĩa vụ | Người dùng thấy lỗi nhưng đã bị trừ tiền | Idempotency, reconciliation, giao dịch thích hợp |
| Gửi email/thông báo | Spam/thông báo trùng | Người dùng không nhận | Nhầm tình trạng thao tác | Outbox, event ID và consumer deduplication |
| Ghi audit bắt buộc | Trùng bản ghi gây sai phân tích | Mất dấu vết yêu cầu | Audit đến muộn/khó đối chiếu | Lưu bền, unique key, xử lý lỗi riêng |
| Log/metric chẩn đoán | Làm sai đếm hoặc tăng chi phí | Thiếu khả năng quan sát | Timestamp không phản ánh outcome chính | Phân biệt attempt/final, best effort, sampling hợp lý |

Bảng rủi ro là gợi ý kỹ thuật: mức độ và giải pháp cụ thể tùy nghiệp vụ, yêu cầu độ bền và hợp đồng với hệ thống ngoài.

## 20. Cách thiết kế mỗi policy an toàn và minh bạch

Một quy trình review thực dụng:

**Bước 1 — Định nghĩa outcome trước.** Thành công là method return, transaction committed, business approved hay async completion? Timeout/unknown có được phép là trạng thái riêng không?

**Bước 2 — Chỉ rõ tất cả effect.** Liệt kê database writes, messages, emails, payments, files, audit, cache writes và metric. Đánh dấu effect nào có thể rollback và effect nào cần idempotency hoặc compensation.

**Bước 3 — Ghi nhận thuộc tính advice.** Policy có thể gọi proceed() bao nhiêu lần, chặn proceed(), tạo lỗi mới hoặc đổi giá trị trả về không? Các điều kiện nào khiến policy bỏ qua hành vi đích?

**Bước 4 — Vẽ cây order.** Viết dạng Outer(Inner(operation)); đánh dấu các mốc entry, return, commit, rollback, retry và callback completion.

**Bước 5 — Kiểm tra failure paths.** Với mỗi nơi có thể lỗi, xem lớp nào bắt được lỗi, có retry không, effect nào đã xảy ra, recorder ghi ở cấp nào và người gọi nhận trạng thái gì.

**Bước 6 — Kiểm tra concurrency và async.** Transaction/context có đúng phạm vi thread/task không? Timeout có thực sự hủy task không? Callback có thể chạy sau khi lời gọi gốc return không?

**Bước 7 — Xác định chính sách cho uncertainty.** Khi không biết commit/publish đã diễn ra chưa, ưu tiên đối soát và idempotency thay cho lặp vô điều kiện.

**Bước 8 — Kiểm thử và đo lường.** Fault injection ở từng điểm, so chuỗi sự kiện và số effect. Khi chạy thực tế, metric về retry, commit failure, timeout và duplicate prevention giúp phát hiện policy gây tác hại.

## 21. Các lỗi thường gặp trong áp dụng AOP

**Lỗi 1: Gọi proceed() nhiều lần trong retry mà không đánh giá effect.** Kết quả là payment/message có thể bị nhân đôi. Cần phân loại lỗi và idempotency tại nơi tạo effect.

**Lỗi 2: Coi rollback database là rollback cả email hoặc HTTP.** Tác dụng phụ ngoài transaction vẫn còn; thiết kế outbox/deduplication hoặc compensation phù hợp.

**Lỗi 3: Lấy return bình thường làm bằng chứng commit.** Commit có thể thất bại sau khi hành vi đích return. Recorder committed-success phải quan sát ranh giới commit thật.

**Lỗi 4: Đặt recorder có thể throw trong retry.** Lỗi telemetry có thể khiến nghiệp vụ đã commit bị chạy lại. Cần cô lập lỗi best effort hoặc thiết kế recorder bắt buộc như một nghiệp vụ riêng.

**Lỗi 5: Giả định timeout là cancellation thành công.** Task có thể tiếp tục; retry có thể chồng lên task cũ. Cần xác nhận chính sách hủy và idempotency.

**Lỗi 6: Dùng fallback che mọi exception.** Lỗi nghiêm trọng bị biến thành dữ liệu có vẻ hợp lệ. Chỉ fallback với loại lỗi/hợp đồng được phép và ghi nhận backend failure tách biệt.

**Lỗi 7: Cache một hành vi có effect bắt buộc.** Cache hit bỏ qua operation nên effect bị mất. Chỉ cache phù hợp với semantics hoặc đưa effect bắt buộc ra ngoài nhánh cache.

**Lỗi 8: Đếm attempt failure thành operation failure.** Metric sai vì một operation có thể phục hồi. Đo cả hai cấp và giữ denominator nhất quán.

**Lỗi 9: Dùng ThreadLocal làm context vĩnh viễn của tác vụ async.** Thread được tái sử dụng, callback chạy trên thread khác. Capture/restore context theo scope thực thi; không kéo dài ThreadLocal của thread caller đến completion.

**Lỗi 10: Không xác minh aspect có thực sự intercept join point.** Một số đường gọi có thể bỏ qua interception theo mô hình AOP đang dùng. Kiểm tra weaving, precedence và đường gọi thực tế bằng test.

## 22. Bài tập tự kiểm tra

**Câu 1.** Retry(Transaction(operation)) có hai lượt, lượt đầu gọi dịch vụ thanh toán ngoài rồi lỗi database và rollback. Lượt sau thành công. Rollback có chắc loại bỏ lần gọi thanh toán đầu không?

**Đáp án:** Không. Nếu dịch vụ thanh toán không tham gia transaction, hiệu ứng đầu vẫn có thể tồn tại. Cần idempotency/đối soát theo ý định thanh toán.

**Câu 2.** Fallback(Retry(operation)) khác Retry(Fallback(operation)) ở điểm nào?

**Đáp án:** Với Fallback ở ngoài, Retry có thể thử đủ policy rồi Fallback mới biến lỗi cuối thành kết quả thay thế. Với Fallback ở trong, lỗi có thể bị chuyển thành kết quả ngay từng attempt, khiến Retry không còn thấy lỗi để tiếp tục.

**Câu 3.** Transaction(Retry(operation)) bắt được lỗi transient ở attempt 1 rồi tiếp tục trong cùng transaction. Có bảo đảm commit được không?

**Đáp án:** Không. Một số lỗi làm transaction bị aborted/rollback-only. Cần rollback và tạo transaction mới nếu policy yêu cầu, hoặc cơ chế savepoint được hỗ trợ cho chính lỗi đó.

**Câu 4.** Một circuit breaker đang mở trả lỗi ngay. Log “backend xử lý rồi thất bại” có đúng không?

**Đáp án:** Không. proceed() có thể chưa được gọi. Cần ghi outcome “short-circuited/rejected” và đo riêng tỷ lệ lỗi backend thật.

**Câu 5.** Advice gọi logger, logger ném exception sau khi operation đã commit. Retry ở ngoài nhìn thấy exception. Rủi ro?

**Đáp án:** Operation có thể bị gọi lại chỉ vì logger lỗi, tạo effect trùng. Observer best effort phải cô lập lỗi; audit bắt buộc cần hợp đồng transaction/idempotency riêng.

**Câu 6.** Future bị timeout ở phía caller, nhưng server đã ghi bản ghi. Outcome nên gắn nhãn “chắc chắn rollback” không?

**Đáp án:** Không. Timeout phía caller không chứng minh server rollback. Cần trạng thái unknown/in-doubt nếu chưa biết, và cơ chế kiểm tra kết quả theo khóa ổn định.

**Câu 7.** Một endpoint được cache trả kết quả trực tiếp mà không chạy nghiệp vụ. Điều gì cần xác minh?

**Đáp án:** Nghiệp vụ đích phải an toàn khi bỏ qua, dữ liệu cache phải đúng ngữ cảnh quyền/tenant và freshness; các effect bắt buộc không được đặt duy nhất trong nhánh bị cache bỏ qua.

**Câu 8.** Có 100 operation, 15 operation retry một lần rồi đều thành công, các operation khác thành công ngay. Số attempt và số operation thất bại cuối là bao nhiêu?

**Đáp án:** 115 attempts, 0 operation thất bại cuối. Nếu 15 attempt đầu trong nhóm retry đều ném lỗi, có 15 attempt failures, nhưng đó không phải final failures.

## 23. Ghi nhớ

Đánh giá một chính sách AOP phải bắt đầu từ **ranh giới thực thi, phân loại lỗi và danh sách tác dụng phụ**, sau đó xác định advice có thể gọi hoặc bỏ qua proceed() thế nào và tương tác ra sao với các advice khác.

- Transaction chỉ bảo đảm trong phạm vi tài nguyên tham gia và có thể có commit không chắc chắn.
- Retry có thể biến lỗi attempt thành success cuối nhưng cũng có thể nhân đôi side effect.
- Timeout/hủy không chứng minh task hoặc effect đã dừng.
- Cache, circuit breaker, rate limit, authorization và fallback có thể bỏ qua hoàn toàn hành vi đích hoặc đổi outcome người gọi quan sát được.
- Recorder phải phân biệt attempt với operation và không để lỗi telemetry tự gây retry nghiệp vụ.
- Idempotency, outbox, deduplication, compensation và reconciliation xử lý những rủi ro mà thứ tự advice đơn thuần không thể xóa bỏ.

Một policy chỉ được xem là đúng khi **lỗi được truyền hoặc biến đổi theo hợp đồng**, **tác dụng phụ được kiểm soát kể cả khi retry/timeout/crash**, và **log/metric phản ánh chính xác những gì thực sự đã xảy ra**.
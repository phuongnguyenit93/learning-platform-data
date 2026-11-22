# Retryable exception

Trong Spring Batch, retryable exception là loại lỗi mà việc thực hiện lại thao tác có khả năng thành công. Ví dụ, database có thể tạm thời trả về deadlock, dịch vụ HTTP có thể timeout trong lúc mạng chập chờn hoặc một message broker có thể tạm thời từ chối kết nối. Với những lỗi như vậy, Step có thể thử lại thay vì lập tức kết thúc thất bại.

Không phải exception nào cũng nên retry. Dữ liệu sai định dạng, lỗi validation nghiệp vụ, SQL sai cú pháp, thiếu file hoặc credential không hợp lệ thường không tự biến mất khi thực hiện lại. Retry những lỗi này chỉ làm tăng thời gian chạy và tải hệ thống. Muốn cấu hình retry an toàn, cần hiểu bản chất lỗi, giới hạn số lần thử, chọn backoff phù hợp và bảo đảm thao tác có thể được thực hiện lại mà không gây tác dụng phụ trùng lặp.

## 1. Retryable exception là gì?

Một exception có thể retry khi nguyên nhân của nó có khả năng tạm thời và lần thử tiếp theo có cơ hội thành công mà không cần thay đổi dữ liệu đầu vào hay code.

Ví dụ thường gặp:

- Deadlock database: transaction có thể thành công khi được thực hiện lại sau khi lock được giải phóng.
- Lock acquisition timeout: một transaction khác đang giữ tài nguyên trong thời gian ngắn.
- Network timeout: kết nối hoặc dịch vụ đích có thể phục hồi.
- Temporary service unavailable: hệ thống bên ngoài đang quá tải hoặc bảo trì ngắn hạn.
- Broker unavailable: message broker tạm thời không thể nhận hoặc trả message.

Các lỗi thường không nên retry:

- File đầu vào không tồn tại hoặc đường dẫn sai.
- Dữ liệu không đúng schema hoặc không parse được.
- Vi phạm validation nghiệp vụ có tính xác định.
- SQL syntax error hoặc tên bảng/cột sai.
- Credential hết hạn hoặc user không có quyền.
- Lỗi lập trình như NullPointerException do bug.
- Constraint violation phản ánh dữ liệu không hợp lệ hoặc khóa bị trùng theo nghiệp vụ.

Phân loại không chỉ dựa trên tên exception. Cùng một nhóm exception có thể có nguyên nhân khác nhau tùy driver, framework và hệ thống đích. Cần xem root cause, trạng thái resource và khả năng thao tác thành công khi thử lại.

## 2. Phân biệt retryable và non-retryable exception

Một cách phân loại thực tế là xác định lỗi có thể tự hết sau một khoảng thời gian hay cần sửa dữ liệu, cấu hình hoặc code.

| Nhóm lỗi | Ví dụ | Retry? | Lý do |
|---|---|---|---|
| Lỗi tranh chấp tạm thời | Deadlock, lock timeout | Thường có | Transaction khác có thể hoàn tất và giải phóng lock |
| Lỗi mạng tạm thời | Connection reset, transient timeout | Có thể | Kết nối có thể phục hồi |
| Dịch vụ tạm thời quá tải | HTTP 503, broker unavailable | Có thể | Dịch vụ có thể sẵn sàng sau backoff |
| Lỗi dữ liệu | Parse error, validation error | Thường không | Thử lại cùng dữ liệu không sửa được nội dung |
| Lỗi cấu hình | Sai URL, thiếu file, sai schema | Không | Cần sửa cấu hình hoặc resource |
| Lỗi xác thực/phân quyền | HTTP 401/403, credential sai | Thường không | Thử lại cùng credential không giúp ích |
| Lỗi lập trình | NullPointerException, IllegalStateException do bug | Không mặc định | Cần sửa code hoặc trạng thái ứng dụng |

Đây là hướng dẫn, không phải quy tắc tuyệt đối cho mọi hệ thống. Ví dụ HTTP 429 có thể retry sau khoảng thời gian server chỉ định, trong khi HTTP 400 thường là lỗi request không hợp lệ. Một số API trả 500 cho lỗi tạm thời, nhưng cũng có hệ thống dùng 500 cho lỗi không thể phục hồi. Hãy dựa vào hợp đồng của dịch vụ và mã lỗi cụ thể.

## 3. Retry khác skip và fail như thế nào?

Ba hành vi có mục đích khác nhau:

- **Retry:** thử lại cùng thao tác vì lỗi có khả năng tạm thời.
- **Skip:** bỏ qua item lỗi khi nghiệp vụ cho phép không xử lý item đó.
- **Fail:** dừng Step vì lỗi không thể tiếp tục an toàn hoặc đã vượt giới hạn retry/skip.

Ví dụ:

~~~text
Đọc Order 42
    |
    v
Ghi database
    |
    +--> Deadlock
    |       |
    |       v
    |    Retry sau backoff
    |       |
    |       +--> thành công -> tiếp tục
    |       |
    |       +--> hết retry -> fail hoặc skip nếu policy cho phép
    |
    +--> InvalidOrderException
            |
            +--> skip nếu được cấu hình
            |
            +--> fail nếu không được phép skip
~~~

Retry không đồng nghĩa với việc bỏ qua lỗi. Khi hết số lần thử mà exception vẫn xảy ra, Step cần áp dụng chính sách tiếp theo: skip nếu exception được phép skip và ngân sách skip còn lại, hoặc thất bại nếu không.

Không dùng skip để xử lý lỗi hệ thống như database unavailable. Nếu toàn bộ kết nối database đang hỏng, bỏ qua từng item sẽ làm thiếu dữ liệu mà không giải quyết nguyên nhân.

## 4. Cấu hình retry trong chunk-oriented Step

Trong Spring Batch, có thể bật fault tolerance và chỉ định loại exception được retry bằng StepBuilder.

Ví dụ:

~~~java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemProcessor<Order, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .retry(TransientDataAccessException.class)
            .retryLimit(3)
            .build();
}
~~~

Trong ví dụ:

- faultTolerant() bật cấu hình xử lý lỗi như retry và skip cho Step.
- retry(TransientDataAccessException.class) chỉ định nhóm lỗi database tạm thời được retry.
- retryLimit(3) đặt giới hạn retry theo API của phiên bản Spring Batch đang dùng.
- Reader, processor và writer vẫn hoạt động theo chunk lifecycle thông thường.

Hãy kiểm tra semantics của retry limit trong phiên bản cụ thể. Một số API retry biểu diễn số lần thử tối đa bao gồm lần gọi đầu tiên, trong khi tài liệu hoặc cấu hình cấp ứng dụng có thể diễn đạt số lần thử lại sau lần đầu. Không suy ra tổng số lần gọi chỉ từ con số cấu hình; viết integration test để xác nhận số attempt thực tế.

Chỉ khai báo exception cụ thể mà ứng dụng xác định là tạm thời. Tránh retry tất cả Exception.class hoặc Throwable.class, vì cách đó có thể lặp lại lỗi dữ liệu, lỗi lập trình và lỗi cấu hình.

## 5. Chọn exception phù hợp

Spring cung cấp hệ thống exception dịch lỗi database, ví dụ nhóm TransientDataAccessException dành cho lỗi có thể tạm thời. Các exception cụ thể có thể bao gồm deadlock hoặc resource tạm thời không sẵn sàng, tùy driver và cách Spring dịch SQLException.

Ví dụ retry deadlock:

~~~java
.faultTolerant()
.retry(DeadlockLoserDataAccessException.class)
.retryLimit(3)
~~~

Hoặc retry nhóm lỗi truy cập dữ liệu tạm thời:

~~~java
.faultTolerant()
.retry(TransientDataAccessException.class)
.retryLimit(3)
~~~

Cần lưu ý:

- Exception cụ thể phụ thuộc database và driver.
- Một lỗi SQL có thể được bọc trong exception của Spring.
- Cùng một exception tổng quát có thể chứa nhiều root cause khác nhau.
- Nếu phân loại theo cause, cần kiểm tra cách retry policy duyệt exception chain trong phiên bản đang dùng.
- Không retry một exception tổng quát chỉ vì đôi khi nó đại diện cho lỗi tạm thời.

Với HTTP client, hãy phân loại theo mã trạng thái và loại lỗi mạng. Ví dụ timeout hoặc 503 có thể retry; 400 do request sai thường không retry; 429 nên tuân theo Retry-After nếu dịch vụ cung cấp. Nếu client chỉ ném một exception chung, có thể cần adapter chuyển lỗi thành các exception nghiệp vụ rõ ràng trước khi đưa vào Step.

## 6. Loại trừ exception không được retry

Nếu một nhóm lỗi rộng được retry, cần loại trừ những lỗi không thể phục hồi bằng cách thử lại. Một số phiên bản StepBuilder hỗ trợ noRetry(...); nếu API hiện tại không có hoặc quy tắc phức tạp, dùng RetryPolicy tùy chỉnh.

Ví dụ minh họa:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(Exception.class)
        .noRetry(InvalidOrderException.class)
        .noRetry(DataIntegrityViolationException.class)
        .retryLimit(3)
        .build();
~~~

Cấu hình trên chỉ nên dùng khi có lý do rõ ràng để retry nhóm Exception rộng và loại trừ chính xác các lỗi còn lại. Trong đa số trường hợp, khai báo các exception retryable cụ thể dễ hiểu và an toàn hơn.

Nếu exception có quan hệ kế thừa, cần kiểm tra quy tắc phân loại và độ ưu tiên của exception cụ thể so với superclass trong phiên bản Spring Batch/Spring Retry đang dùng. Đừng giả định một cấu hình noRetry(...) luôn ghi đè mọi policy khác nếu đồng thời cung cấp custom RetryPolicy.

## 7. Retry limit và số lần thực hiện

Retry cần giới hạn để Job không lặp vô hạn. Nếu dịch vụ đích không thể phục hồi, retry liên tục sẽ tiêu tốn thread, connection và thời gian mà không tạo thêm cơ hội thành công đáng kể.

Khi chọn giới hạn, hãy phân biệt:

- **Initial attempt:** lần thực hiện đầu tiên.
- **Retry attempt:** lần thực hiện lại sau lỗi.
- **Total attempts:** tổng số lần gọi, gồm lần đầu và các lần retry.

Ví dụ nếu hệ thống cho phép 3 lần retry sau lần đầu, tổng số attempt có thể là 4. Nhưng một API cấu hình maxAttempts có thể tính cả lần đầu trong con số 3. Hãy đọc tài liệu của API cụ thể và xác nhận bằng test.

Nên cân nhắc:

- Thời gian phục hồi dự kiến của resource.
- Timeout của mỗi lần gọi.
- Tổng thời gian tối đa của Step hoặc Job.
- Tải mà retry tạo thêm cho hệ thống đích.
- Mức độ an toàn khi lặp thao tác.
- Chính sách retry của dịch vụ bên ngoài.

Một giới hạn nhỏ thường phù hợp với deadlock hoặc lỗi mạng ngắn hạn. Với dịch vụ có thời gian phục hồi dài, cần cân nhắc backoff, timeout tổng thể hoặc đưa công việc vào hàng đợi để xử lý lại sau, thay vì giữ một worker thread chờ quá lâu.

## 8. Backoff để tránh retry dồn dập

Nếu retry ngay lập tức, nhiều worker có thể cùng thử lại tại một thời điểm và tiếp tục gây quá tải. Backoff chèn khoảng chờ giữa các lần thử.

Các chiến lược phổ biến:

- **Fixed backoff:** chờ một khoảng cố định giữa các lần retry.
- **Exponential backoff:** tăng dần thời gian chờ sau mỗi lần thất bại.
- **Exponential backoff with jitter:** thêm độ ngẫu nhiên để nhiều worker không đồng bộ retry cùng lúc.
- **Server-directed backoff:** dùng thời gian do dịch vụ đích chỉ định, chẳng hạn HTTP Retry-After.

Ví dụ cấu hình exponential backoff:

~~~java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemWriter<Order> writer) {

    ExponentialBackOffPolicy backOff =
            new ExponentialBackOffPolicy();
    backOff.setInitialInterval(500L);
    backOff.setMultiplier(2.0);
    backOff.setMaxInterval(5000L);

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .writer(writer)
            .faultTolerant()
            .retry(TransientDataAccessException.class)
            .retryLimit(3)
            .backOffPolicy(backOff)
            .build();
}
~~~

Ví dụ dùng API Spring Retry được tích hợp trong các phiên bản Spring Batch tương ứng. Package và cách cấu hình có thể thay đổi theo phiên bản. Backoff minh họa tăng khoảng chờ từ 500 ms, nhân đôi sau mỗi lần và không vượt 5 giây.

Không đặt backoff quá dài nếu transaction hoặc connection vẫn đang bị giữ trong thời gian chờ. Hãy xem xét transaction boundary của Step, loại exception và cơ chế retry của framework. Với lỗi mạng gọi API ngoài, nên đặt timeout cho từng request để một attempt không treo vô thời hạn.

## 9. Retry và transaction rollback

Trong chunk-oriented Step, writer thường thực hiện ghi dữ liệu trong transaction của chunk. Khi thao tác ghi ném exception làm transaction rollback, Spring Batch có thể retry theo cấu hình.

Luồng khái quát:

~~~text
Begin chunk transaction
       |
       v
Read / Process
       |
       v
Write chunk
       |
       +--> transient exception
                 |
                 v
              rollback
                 |
                 v
             backoff
                 |
                 v
              retry
                 |
           +-----+------+
           |            |
        success       exhausted
           |            |
           v            v
        commit       fail / skip
~~~

Các thao tác database tham gia transaction hiện tại được rollback khi transaction rollback. Tuy nhiên, một số thao tác ngoài database như gửi email, gọi HTTP hoặc publish message có thể đã xảy ra và không thể được transaction database hoàn tác.

Khi retry, reader hoặc processor cũng có thể được gọi lại tùy giai đoạn lỗi và cách framework phục hồi chunk. Không giả định chỉ đúng một dòng code trong writer được thực hiện lại. Hãy thiết kế toàn bộ đường đi xử lý để chịu được việc thực hiện lặp.

## 10. Idempotency: điều kiện quan trọng để retry an toàn

Một thao tác idempotent có thể được thực hiện nhiều lần mà kết quả cuối vẫn tương đương thực hiện một lần. Đây là thuộc tính quan trọng khi không thể biết chắc một request trước đã thành công hay chưa.

Ví dụ, client gửi yêu cầu tạo hóa đơn. Server xử lý xong nhưng response bị mất do network timeout. Client retry và gửi lại yêu cầu. Nếu server không có cơ chế nhận diện request trùng, hai hóa đơn có thể được tạo.

Các cách tăng idempotency:

- Dùng business key duy nhất và unique constraint trong database.
- Dùng upsert khi phù hợp với quy tắc nghiệp vụ.
- Gửi idempotency key ổn định cho API.
- Lưu message ID đã xử lý để consumer deduplicate.
- Dùng transactional outbox để phát event sau commit.
- Tạo bảng trạng thái theo business key để xác định thao tác đã hoàn tất.

Ví dụ idempotency key:

~~~java
String idempotencyKey =
        "order-" + order.getId() + "-invoice-v1";

paymentClient.createInvoice(
        order,
        idempotencyKey);
~~~

Key phải ổn định giữa các lần retry và restart của cùng một thao tác logic. Không tạo UUID mới cho mỗi lần retry, vì server sẽ coi mỗi request là một thao tác khác.

Idempotency không có nghĩa là bỏ qua mọi duplicate. Hệ thống nhận cần xác nhận request lặp có cùng nội dung và cùng business intent; nếu cùng key nhưng payload khác, nên trả lỗi rõ ràng.

## 11. Retry với HTTP client và dịch vụ ngoài

Khi processor hoặc writer gọi API, cần phân loại lỗi theo hợp đồng HTTP.

Một hướng phân loại phổ biến:

| Kết quả | Hành động thường cân nhắc |
|---|---|
| Connect timeout / read timeout | Retry có giới hạn nếu request an toàn |
| Connection reset | Retry nếu request có idempotency |
| HTTP 429 | Tôn trọng Retry-After và backoff |
| HTTP 502/503/504 | Có thể retry với giới hạn |
| HTTP 400 | Thường không retry; sửa request/dữ liệu |
| HTTP 401/403 | Không retry cùng credential; xử lý xác thực/quyền |
| HTTP 404 | Phụ thuộc hợp đồng; thường không retry nếu resource không tồn tại |
| HTTP 409 | Phụ thuộc ý nghĩa conflict và idempotency |

Không thể dùng bảng này như quy tắc cho mọi API. Ví dụ một dịch vụ có thể trả 404 trong lúc resource chưa được đồng bộ hoặc dùng 409 cho một thao tác có thể thử lại. Hãy dựa trên tài liệu API.

Với API có rate limit, backoff cần tôn trọng thời gian server yêu cầu. Nếu thời gian chờ dài hơn giới hạn vận hành của Job, cân nhắc dừng và đưa item vào hàng đợi retry riêng thay vì giữ Step chạy trong thời gian dài.

## 12. Stateful và stateless retry

Retry có thể giữ trạng thái thử lại trong phạm vi một lần thực thi hoặc cần duy trì trạng thái giữa các lần rollback/re-presentation của item.

- **Stateless retry:** trạng thái retry gắn với một lần thực hiện hiện tại; phù hợp với các lỗi có thể thử lại ngay trong cùng ngữ cảnh.
- **Stateful retry:** cần nhận diện cùng một item qua các lần rollback và xử lý lại, thường dùng key ổn định để giữ retry context.

Trong Spring Batch, cơ chế retry của chunk và transaction có thể yêu cầu stateful behavior để item được nhận diện sau khi transaction rollback và item được đưa lại vào luồng. Chi tiết phụ thuộc loại lỗi, reader, transaction manager và phiên bản framework.

Nếu dùng retry stateful hoặc custom RetryPolicy, cần xác định key cho item. Key phải ổn định và phân biệt được các item khác nhau; dùng object mutable hoặc toString() không ổn định có thể làm retry context bị gắn nhầm.

Không tự xây một retry cache toàn cục nếu framework đã quản lý retry context. Việc cache không được dọn đúng có thể giữ object lâu, làm rò bộ nhớ hoặc làm trạng thái của các JobExecution khác nhau bị trộn.

## 13. Kết hợp retry và skip

Một exception có thể được cấu hình retry trước, rồi sau khi hết retry mới được xem xét theo skip policy nếu nó cũng là loại skippable.

Ví dụ:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(DeadlockLoserDataAccessException.class)
        .retryLimit(3)
        .skip(InvalidOrderException.class)
        .skipLimit(20)
        .build();
~~~

Trong ví dụ, deadlock được retry; lỗi validation được skip. Nếu deadlock vẫn xảy ra sau giới hạn retry và không được cấu hình skip, Step thất bại. Không nên thêm skip cho mọi lỗi database chỉ để Job có thể tiếp tục.

Cần kiểm tra tương tác giữa retry policy, skip policy và rollback classifier của phiên bản Spring Batch đang dùng. Một exception có thể được phân loại khác nhau ở các giai đoạn read, process và write. Hãy viết integration test cho lỗi thực tế thay vì chỉ test từng policy riêng lẻ.

## 14. Không bắt exception rồi tự retry trong component

Một lỗi thiết kế phổ biến là tự viết vòng lặp retry bên trong processor hoặc writer:

~~~java
// Không nên tự triển khai retry loop nếu Step đã quản lý retry.
for (int attempt = 1; attempt <= 3; attempt++) {
    try {
        remoteClient.send(item);
        break;
    } catch (RuntimeException exception) {
        if (attempt == 3) {
            throw exception;
        }
    }
}
~~~

Cách này khiến Spring Batch không biết số lần thử, không quản lý backoff/skip theo cấu hình Step và khó quan sát retry. Nó cũng có thể giữ transaction mở trong lúc chờ.

Hãy để fault-tolerant Step quản lý retry nếu thao tác nằm trong lifecycle của reader/processor/writer. Nếu cần retry ở một client hoặc service độc lập, dùng cơ chế retry có cấu hình rõ ràng và tránh lồng nhiều lớp retry không kiểm soát. Ví dụ HTTP client retry 3 lần, bên trong Step cũng retry 3 lần có thể tạo tối đa nhiều request hơn dự kiến.

Không nuốt exception rồi trả một kết quả giả để Step tiếp tục. Hãy để exception phù hợp truyền ra để retry policy hoặc skip policy quyết định.

## 15. Retry và giới hạn thời gian

Số lần retry không đủ để kiểm soát thời gian tổng. Nếu mỗi request timeout 30 giây và có nhiều attempt, một item có thể giữ worker rất lâu.

Cần xác định:

- Timeout kết nối.
- Timeout đọc response.
- Timeout tổng của request.
- Backoff giữa các attempt.
- Số attempt tối đa.
- Deadline của Job hoặc lịch vận hành.
- Thời gian transaction và connection bị giữ.

Ví dụ, 3 attempt với timeout 20 giây và backoff tăng dần có thể kéo dài hơn một phút cho một item. Với chunk nhiều item, thời gian tổng có thể tăng đáng kể.

Đặt timeout ở client/resource và retry limit ở Step. Không dùng retry để thay thế timeout. Nếu một dịch vụ không thể phục hồi trong khoảng thời gian phù hợp, dừng Step và cho phép scheduler hoặc cơ chế retry ngoài Batch xử lý lại sau.

## 16. Quan sát retry trong vận hành

Retry có thể làm Job chậm mà không làm tăng skip count hoặc write error cuối cùng, vì item cuối cùng vẫn thành công. Do đó, chỉ nhìn status COMPLETED là chưa đủ để biết hệ thống đang retry quá nhiều.

Nên theo dõi:

- Số retry attempt theo Job và Step.
- Loại exception được retry.
- Tỷ lệ retry thành công và retry exhausted.
- Thời gian chờ backoff.
- Thời gian xử lý item/chunk.
- Số transaction rollback.
- Số lỗi cuối cùng dẫn đến fail hoặc skip.

Có thể dùng listener hoặc cơ chế quan sát của Spring Retry/Micrometer phù hợp với phiên bản đang triển khai. Giữ metric tag có cardinality thấp; không đưa Order ID, request ID hoặc JobExecution ID vào tag. Đưa định danh chi tiết vào log/audit nếu cần điều tra.

Log retry nên chứa JobExecution ID, Step name, exception class và attempt number. Không log payload nhạy cảm hoặc toàn bộ request/response body.

## 17. Kiểm thử retryable exception

Cần kiểm thử cả việc phân loại exception và hành vi thực thi thực tế.

Các trường hợp quan trọng:

| Kịch bản | Điều cần xác nhận |
|---|---|
| Lỗi tạm thời xảy ra một lần | Retry và sau đó thành công |
| Lỗi tạm thời liên tục | Dừng sau giới hạn attempt |
| Exception không retryable | Không lặp thao tác |
| Exception bị bọc trong cause | Policy phân loại đúng theo cấu hình |
| Backoff | Khoảng chờ tuân theo policy |
| Writer lỗi trong transaction | Rollback và retry đúng |
| Processor lỗi | Item được xử lý lại theo lifecycle |
| API response bị mất sau khi server xử lý | Idempotency ngăn tác động trùng |
| Retry hết giới hạn và exception skippable | Skip policy được áp dụng đúng nếu cấu hình |
| Retry hết giới hạn và exception không skippable | Step FAILED |
| Restart sau lỗi | Không tạo duplicate hoặc bỏ sót dữ liệu |
| Nhiều worker cùng retry | Backoff không tạo retry storm |

Một unit test có thể dùng mock client để ném exception ở hai lần đầu rồi trả kết quả thành công ở lần thứ ba. Integration test nên chạy Step với transaction manager và writer thực tế hoặc môi trường database test để xác nhận rollback/retry.

Khi kiểm tra số lần gọi, phân biệt initial attempt với retry attempts. Đừng chỉ assert tổng số lần gọi mà không đối chiếu semantics của retryLimit hoặc maxAttempts trong API đang dùng.

## 18. Những lỗi thường gặp khi cấu hình retry

**Retry mọi exception.** Lỗi dữ liệu, lỗi lập trình và lỗi cấu hình không tự hết. Chỉ chọn nhóm lỗi tạm thời.

**Không giới hạn số lần thử.** Job có thể chạy quá lâu hoặc tạo tải lặp lại lên dịch vụ đang lỗi.

**Retry ngay lập tức.** Nhiều worker có thể tạo retry storm. Dùng backoff và jitter khi phù hợp.

**Không đặt timeout.** Một attempt có thể treo lâu hơn toàn bộ thời gian vận hành cho phép.

**Nhầm retry với skip.** Retry giữ item để thử lại; skip bỏ item theo chính sách nghiệp vụ.

**Thao tác không idempotent.** Request có thể đã thành công nhưng response bị mất; retry có thể tạo tác động trùng.

**Lồng nhiều retry layer.** Client, service và Step cùng retry có thể nhân số request lên nhiều lần.

**Nuốt exception.** Framework không nhận được lỗi để áp dụng retry policy hoặc cập nhật metadata đúng.

**Không đo retry.** Job vẫn COMPLETED nhưng thời gian xử lý và tải hệ thống tăng bất thường.

## 19. Quy trình lựa chọn retryable exception

Khi cấu hình retry cho một Step, hãy thực hiện theo thứ tự:

1. Xác định exception thực tế và root cause từ reader, processor hoặc writer.
2. Đánh giá nguyên nhân có khả năng tạm thời hay cần sửa dữ liệu, cấu hình hoặc code.
3. Chọn exception cụ thể hoặc classifier phù hợp; loại trừ lỗi không retryable.
4. Đặt retry limit và xác định rõ tổng attempt bao gồm lần đầu hay không.
5. Chọn backoff, jitter và timeout phù hợp với dịch vụ đích.
6. Kiểm tra transaction rollback và việc component có thể được gọi lại.
7. Bảo đảm thao tác có idempotency hoặc cơ chế chống duplicate.
8. Quyết định exception sau khi hết retry sẽ làm Step fail hay có thể skip.
9. Ghi metric/log cho attempt, exhausted retry và thời gian backoff.
10. Kiểm thử lỗi tạm thời, lỗi vĩnh viễn, restart, partitioning và tác động ngoài transaction.

Retryable exception là một quyết định dựa trên khả năng phục hồi của nguyên nhân lỗi, không chỉ dựa trên tên class. Khi chọn đúng exception, giới hạn attempt, dùng backoff, đặt timeout và bảo vệ thao tác bằng idempotency, Spring Batch có thể tự phục hồi trước các lỗi tạm thời mà vẫn dừng rõ ràng khi dữ liệu hoặc hệ thống gặp vấn đề không thể khắc phục bằng cách thử lại.


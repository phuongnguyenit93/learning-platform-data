# Skip duplicate key

Trong Spring Batch, duplicate key thường xuất hiện khi writer chèn một bản ghi có khóa chính hoặc khóa unique đã tồn tại trong database. Với một số luồng import, việc gặp lại cùng business key là tình huống có thể dự đoán được: dữ liệu đã được nhập ở lần chạy trước, nguồn gửi lại message, hoặc cùng một record xuất hiện nhiều lần trong file đầu vào.

Có thể cấu hình fault-tolerant Step để bỏ qua những item gây ra DuplicateKeyException. Tuy nhiên, skip duplicate chỉ đúng khi nghiệp vụ xác nhận bản ghi trùng có thể được xem là đã xử lý hoặc được cách ly theo chính sách. Một lỗi unique constraint đôi khi cũng báo hiệu dữ liệu xung đột, sai khóa hoặc lỗi mapping. Vì vậy, cần giữ unique constraint ở database, phân biệt duplicate hợp lệ với xung đột dữ liệu, giới hạn số item bị bỏ qua và lưu audit đủ để truy vết.

## 1. Duplicate key xảy ra ở đâu?

Database dùng primary key và unique constraint để bảo đảm một giá trị hoặc một tổ hợp giá trị không xuất hiện nhiều lần. Ví dụ bảng orders có khóa chính order_id và unique constraint trên external_reference.

~~~sql
CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    external_reference VARCHAR(80) NOT NULL UNIQUE,
    customer_id BIGINT NOT NULL,
    amount DECIMAL(12, 2) NOT NULL
);
~~~

Nếu writer cố insert một record có order_id hoặc external_reference đã tồn tại, database từ chối câu lệnh và driver trả lỗi. Với Spring JDBC, lỗi có thể được dịch thành DuplicateKeyException.

Các tình huống thường gặp:

- File đầu vào chứa cùng một order_id nhiều lần.
- Một Job được launch lại với dữ liệu đã nhập trước đó.
- Hai Job đồng thời xử lý cùng business key.
- Một hệ thống upstream gửi lại cùng event.
- Job đã ghi thành công dữ liệu nhưng process dừng trước khi hoàn tất các bước tiếp theo.
- Một khóa unique khác, chẳng hạn external_reference, bị trùng dù primary key khác nhau.

Duplicate key là kết quả của một ràng buộc dữ liệu ở database. Nó không chỉ là vấn đề của Spring Batch và cũng không nên chỉ được kiểm tra bằng logic Java trong reader hoặc processor.

## 2. Unique constraint là nguồn sự thật

Một cách làm không an toàn là query trước xem khóa đã tồn tại hay chưa rồi mới insert:

~~~text
SELECT xem order_id đã tồn tại?
          |
          +--> Chưa tồn tại
                    |
                    v
                  INSERT
~~~

Cách này có race condition. Hai transaction có thể cùng kiểm tra và cùng nhận kết quả chưa tồn tại. Sau đó cả hai cùng insert; chỉ một transaction thành công, transaction còn lại gặp duplicate key.

Vì vậy, pre-check không thể thay thế unique constraint. Nó có thể giảm số exception trong một số workload, nhưng database vẫn phải bảo vệ tính duy nhất.

Mô hình đáng tin cậy:

1. Chuẩn hóa business key.
2. Database áp dụng primary key hoặc unique constraint.
3. Writer thực hiện insert.
4. Ứng dụng xử lý lỗi duplicate theo chính sách đã xác định.
5. Audit ghi nhận item được bỏ qua hoặc xung đột cần điều tra.

Nếu hai transaction cạnh tranh cùng một key, unique constraint là điểm quyết định cuối cùng. Cấu hình skip chỉ quyết định Spring Batch làm gì sau khi database từ chối insert.

## 3. DuplicateKeyException của Spring

Spring DAO exception translation cung cấp DuplicateKeyException trong package org.springframework.dao. Đây là một loại DataIntegrityViolationException, biểu thị thao tác ghi vi phạm ràng buộc duy nhất hoặc khóa.

Với JdbcTemplate, NamedParameterJdbcTemplate và các writer Spring JDBC, SQLException thường được dịch sang hệ exception của Spring dựa trên database metadata và exception translator.

Ví dụ import:

~~~java
import org.springframework.dao.DuplicateKeyException;
~~~

Khi writer ném DuplicateKeyException, fault-tolerant Step có thể được cấu hình để skip exception này.

Không phải mọi JDBC driver đều trả cùng exception shape. Một writer tự viết dùng trực tiếp Connection và PreparedStatement có thể nhận SQLException hoặc BatchUpdateException mà chưa được dịch thành DuplicateKeyException. Khi đó, cấu hình skip đúng class có thể không khớp. Hãy dùng Spring JDBC hoặc exception translator phù hợp, và kiểm thử với database/driver thực tế.

## 4. Cấu hình skip DuplicateKeyException

Với Spring Batch 5, có thể cấu hình Step bằng Java DSL như sau:

~~~java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        ItemWriter<Order> orderWriter,
        SkipListener<Order, Order> duplicateSkipListener) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(200, transactionManager)
            .reader(orderReader)
            .writer(orderWriter)
            .faultTolerant()
            .skip(DuplicateKeyException.class)
            .skipLimit(100)
            .listener(duplicateSkipListener)
            .build();
}
~~~

Các phần quan trọng:

- faultTolerant() bật cấu hình fault tolerance cho Step.
- skip(DuplicateKeyException.class) đánh dấu loại exception được phép bỏ qua.
- skipLimit(100) giới hạn tổng số skip được chấp nhận.
- listener(...) đăng ký listener để ghi nhận item bị skip.

Trong ví dụ này, khi DuplicateKeyException được phân loại là skippable và số skip còn trong giới hạn, Step có thể tiếp tục xử lý các item còn lại. Nếu vượt skip limit, Step sẽ thất bại.

Nên đặt skip limit tường minh theo quy tắc nghiệp vụ. Không coi một con số tùy ý là an toàn cho mọi Job; ngưỡng phù hợp phụ thuộc volume, chất lượng nguồn và tỷ lệ duplicate dự kiến.

## 5. Skip khác với filter và retry

Ba cơ chế này giải quyết các trường hợp khác nhau:

| Cơ chế | Ý nghĩa | Ví dụ |
|---|---|---|
| Filter | Processor trả null vì item không cần ghi | Loại order đã bị hủy theo rule |
| Skip | Item gây lỗi thuộc loại được phép bỏ qua | Insert gặp duplicate key đã được nghiệp vụ chấp nhận |
| Retry | Lỗi có khả năng tạm thời và thao tác có thể thử lại | Deadlock hoặc lỗi kết nối tạm thời |

Nếu một item không hợp lệ theo nghiệp vụ và đã biết trước khi ghi, processor có thể filter hoặc route sang reject writer. Nếu item làm database ném duplicate key, skip policy có thể xử lý lỗi đó.

Không retry vô hạn một duplicate deterministic. Nếu key đã tồn tại và thao tác vẫn là INSERT, retry thường gặp lại cùng lỗi. Retry chỉ hợp lý khi có một lý do transient cụ thể hoặc quy trình retry sẽ đọc lại trạng thái rồi đưa ra quyết định khác.

## 6. Duplicate key có luôn là duplicate hợp lệ không?

Không. DuplicateKeyException chỉ cho biết một ràng buộc duy nhất bị vi phạm; nó không chứng minh hai bản ghi có cùng nội dung nghiệp vụ.

Ví dụ:
- Record nguồn có order_id = 100 nhưng database đã có order 100 với cùng amount và customer. Đây có thể là lần gửi lại vô hại.
- Record nguồn có order_id = 100 nhưng amount khác dữ liệu hiện có. Đây có thể là xung đột cần điều tra.
- order_id khác nhau nhưng external_reference trùng. Đây có thể là mapping sai hoặc upstream tái sử dụng reference.
- Khóa trùng do generator hoặc sequence bị cấu hình sai. Đây là lỗi hệ thống, không phải duplicate có thể bỏ qua.

Chỉ skip khi business rule xác nhận loại duplicate đó được phép. Nếu mọi duplicate đều bị bỏ qua, Job có thể COMPLETED trong khi dữ liệu nguồn xung đột với dữ liệu đích.

Với hệ thống cần idempotency, có thể so sánh business key và một checksum/version của payload hiện có. Cùng key và cùng nội dung có thể được xem là replay; cùng key nhưng khác nội dung cần được xử lý theo conflict policy.

## 7. Cấu hình JdbcBatchItemWriter

Một writer JDBC đơn giản có thể insert Order:

~~~java
@Bean
JdbcBatchItemWriter<Order> orderInsertWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Order>()
            .dataSource(dataSource)
            .sql("""
                    insert into orders
                        (order_id, external_reference, customer_id, amount)
                    values
                        (:id, :externalReference, :customerId, :amount)
                    """)
            .beanMapped()
            .build();
}
~~~

JdbcBatchItemWriter dùng Spring JDBC để thực hiện batch update. Khi database từ chối insert do unique constraint, exception translation có thể tạo DuplicateKeyException để Step phân loại.

Một số lưu ý:

- Tên parameter trong SQL phải khớp property của item hoặc mapping được cung cấp.
- DataSource của writer cần tham gia transaction do Step sử dụng nếu muốn database write rollback cùng chunk.
- Unique constraint phải tồn tại ở database.
- Kiểm thử hành vi batch update với driver đang triển khai.
- Không dùng cùng một writer instance không thread-safe trong nhiều luồng nếu chưa có thiết kế phù hợp.

Thuộc tính assertUpdates của JdbcBatchItemWriter kiểm tra số dòng bị ảnh hưởng trong một số trường hợp update trả về 0. Nó không phải công tắc tắt duplicate key và không thay thế xử lý unique constraint.

## 8. Exception translation và lỗi từ JDBC driver

Khi writer dùng JdbcTemplate hoặc NamedParameterJdbcTemplate, Spring có thể chuyển SQLException thành DataAccessException cụ thể. Tuy nhiên, khi dùng JDBC batch, driver có thể đóng gói lỗi trong BatchUpdateException hoặc cause chain có nhiều lớp.

Một số hệ quản trị có mã lỗi riêng cho duplicate:

| Database | Mã lỗi thường gặp | Mô tả |
|---|---|---|
| PostgreSQL | SQLState 23505 | Unique violation |
| MySQL | Vendor error code 1062 | Duplicate entry |
| Oracle | Vendor error code 1 / ORA-00001 | Unique constraint violated |
| SQL Server | 2601 hoặc 2627 | Duplicate key / unique constraint |

Đây là các ví dụ theo database; cần xác nhận driver version và exception translator trong ứng dụng. Không chỉ dựa vào message text vì message có thể thay đổi theo locale hoặc driver.

Nếu exception không được dịch thành DuplicateKeyException, có thể:
- Dùng Spring JDBC để tận dụng exception translation.
- Cấu hình SQLExceptionTranslator phù hợp.
- Bọc lỗi duplicate đã nhận diện thành custom exception có ý nghĩa nghiệp vụ.
- Dùng SkipPolicy riêng để kiểm tra cause chain, SQLState hoặc vendor code.

Không phân loại tất cả SQLException hoặc DataIntegrityViolationException thành duplicate. Foreign key, not-null, check constraint và lỗi dữ liệu khác có thể cần làm Step thất bại.

## 9. Skip policy rộng hay hẹp?

Có thể cấu hình skip theo class cụ thể:

~~~java
.skip(DuplicateKeyException.class)
~~~

Đây là lựa chọn dễ hiểu khi writer luôn phát DuplicateKeyException cho loại duplicate cần bỏ qua.

Cần thận trọng với các class rộng hơn:

~~~java
.skip(DataIntegrityViolationException.class)
~~~

DataIntegrityViolationException có thể bao gồm nhiều loại vi phạm dữ liệu khác nhau, chẳng hạn foreign key, not-null, check constraint và unique constraint. Skip cả nhóm có thể che giấu lỗi cần dừng Job.

Cũng không nên cấu hình:

~~~java
.skip(Exception.class)
~~~

nếu không có policy rất rõ ràng. Điều đó có thể làm Job bỏ qua lỗi lập trình, lỗi cấu hình, lỗi I/O hoặc lỗi kết nối.

Nếu cùng DuplicateKeyException có thể phát sinh ở nhiều phase nhưng chỉ muốn skip lỗi từ writer, hãy dùng exception riêng được tạo ở writer hoặc một policy có đủ ngữ cảnh để phân biệt. Skip classification cơ bản theo exception type áp dụng cho Step, không phải chỉ riêng một dòng SQL.

## 10. Skip limit và giới hạn chất lượng dữ liệu

skipLimit đặt ngưỡng số skip cho phép. Số skip được tính trên các skip trong các phase read, process và write của Step, không chỉ riêng duplicate trong writer.

Ví dụ:
- skipLimit = 10.
- Step gặp 6 duplicate khi ghi và 3 record lỗi khi đọc.
- Tổng skip là 9, vẫn trong giới hạn.
- Nếu phát sinh thêm skip khiến tổng vượt giới hạn, Step thất bại.

Đặt limit dựa trên hợp đồng dữ liệu:
- Batch nhỏ có thể chỉ chấp nhận vài duplicate.
- Batch lớn có thể chấp nhận một tỷ lệ hoặc số lượng xác định.
- Nếu duplicate là dấu hiệu của upstream replay bình thường, cần đo tỷ lệ thực tế.
- Nếu duplicate hiếm khi xảy ra, một ngưỡng nhỏ giúp phát hiện sớm lỗi.

Skip limit là giới hạn số lượng, không phải tỷ lệ phần trăm. Nếu yêu cầu là "không quá 0,1% input", cần tính và kiểm tra tỷ lệ dựa trên read/write count hoặc dùng policy/monitoring bổ sung. Không chỉ đặt skipLimit rồi giả định nó đại diện cho tỷ lệ.

## 11. Ghi nhận item bị skip bằng SkipListener

SkipListener cho phép ứng dụng nhận biết item bị bỏ qua và lý do. Với duplicate xảy ra trong write, dùng onSkipInWrite.

Ví dụ:

~~~java
@Bean
SkipListener<Order, Order> duplicateSkipListener(
        DuplicateAuditService auditService) {

    return new SkipListener<>() {
        @Override
        public void onSkipInRead(Throwable throwable) {
            // Không xử lý skip ở read trong ví dụ này.
        }

        @Override
        public void onSkipInProcess(
                Order item, Throwable throwable) {
            // Không xử lý skip ở process trong ví dụ này.
        }

        @Override
        public void onSkipInWrite(
                Order item, Throwable throwable) {
            auditService.recordDuplicate(
                    item.getId(),
                    item.getExternalReference(),
                    throwable.getClass().getSimpleName());
        }
    };
}
~~~

Audit nên ghi đủ thông tin để truy vết:
- JobInstance ID và JobExecution ID.
- Step name.
- Business key của item.
- Constraint hoặc route liên quan nếu xác định được.
- Exception class và SQLState/vendor code khi an toàn.
- Thời điểm và rule version.
- Trạng thái duplicate được chấp nhận hay cần điều tra.

Không ghi toàn bộ payload nếu chứa dữ liệu cá nhân hoặc thông tin nhạy cảm. Dùng business key và metadata cần thiết.

## 12. Audit phải phù hợp với transaction

SkipListener là callback của Spring Batch trong quá trình xử lý skip. Nếu audit ghi vào cùng database và cùng transaction, cần hiểu nó có thể rollback nếu chunk transaction thất bại.

Nếu audit được ghi ra file, HTTP hoặc message broker, side effect đó không tự rollback cùng transaction JDBC. Nếu callback bị gọi lại trong một recovery path hoặc process restart, cần thiết kế audit idempotent.

Một số lựa chọn:
- Ghi audit row trong cùng transaction nếu muốn nó commit cùng trạng thái chunk.
- Ghi outbox record trong transaction rồi publisher riêng gửi ra ngoài.
- Dùng idempotency key kết hợp JobInstance ID, item business key và skip phase.
- Đưa item vào reject/quarantine table có unique key.
- Chấp nhận audit độc lập nhưng có cơ chế reconciliation.

Không để lỗi audit bị nuốt âm thầm. Nếu không ghi được audit bắt buộc, cần quyết định rõ Step phải fail hay có fallback khác.

## 13. Hành vi khi lỗi xuất hiện trong writer

Lỗi writer thường xảy ra sau khi reader và processor đã tạo một chunk. Khi một item trong chunk gây duplicate key, thao tác batch có thể thất bại.

Trong fault-tolerant Step, Spring Batch cần rollback chunk transaction trước khi xử lý item được skip. Tùy writer, driver và cấu hình, framework có thể phải xác định item gây lỗi trong chunk; việc này có thể khiến writer được gọi lại với các nhóm item nhỏ hơn hoặc từng item.

Điều đó có các hệ quả:
- Writer phải an toàn khi được gọi lại sau rollback.
- Không thực hiện side effect ngoài transaction trong write mà không có idempotency.
- Một chunk có nhiều duplicate có thể tốn thêm round trip khi framework xác định item lỗi.
- JDBC driver có thể cung cấp thông tin batch failure khác nhau.
- Cần test với đúng database và driver production.

Không giả định một exception từ batch insert luôn xác định chính xác item nào bị trùng. Hãy xác nhận hành vi thực tế của writer và driver.

## 14. Duplicate trong cùng chunk

Giả sử chunk chứa ba item:

~~~text
Chunk:
  Order 101
  Order 102
  Order 102
~~~

Nếu database chưa có Order 102, insert đầu tiên có thể thành công nhưng lần insert thứ hai vi phạm unique constraint. Khi batch statement thất bại, transaction của chunk có thể rollback cả các insert trong cùng transaction. Spring Batch sau đó áp dụng cơ chế skip/recovery để tìm item gây lỗi.

Nếu input có duplicate nội bộ thường xuyên, có thể loại bỏ trước khi writer:
- Dedupe theo business key trong processor hoặc một bước staging.
- Dùng một bảng staging có unique constraint.
- Chọn một record thắng theo timestamp/version.
- Ghi các record trùng nội bộ vào reject output.

Cần định nghĩa rõ record nào được giữ nếu hai item cùng key nhưng payload khác nhau. Chỉ dùng distinct theo object equality có thể không đúng nếu equals/hashCode không dựa trên business key.

## 15. Duplicate đã tồn tại từ lần chạy trước

Một mục tiêu phổ biến là làm import có tính idempotent. Job có thể được chạy lại hoặc nguồn có thể gửi lại record đã nhập trước đó.

Ví dụ:
- Lần đầu import Order 100 thành công.
- Job dừng trước khi gửi acknowledgment hoặc cập nhật trạng thái nguồn.
- Nguồn gửi lại Order 100.
- Database unique constraint từ chối insert thứ hai.
- Step skip DuplicateKeyException và tiếp tục.

Cách này có thể phù hợp nếu duplicate có nghĩa "record này đã được nhập". Nhưng cần xác nhận record hiện có thực sự tương đương với record đang import.

Nếu dữ liệu hiện có khác payload nguồn, skip có thể che giấu một thay đổi cần cập nhật hoặc một xung đột nghiêm trọng. Trong trường hợp đó, cần so sánh version/checksum hoặc dùng upsert theo quy tắc nghiệp vụ.

## 16. Upsert hoặc insert-if-absent có thể phù hợp hơn skip

Nếu duplicate là tình huống bình thường, có thể dùng SQL xử lý conflict trực tiếp thay vì tạo exception cho mỗi item.

Ví dụ PostgreSQL:

~~~sql
INSERT INTO orders (order_id, customer_id, amount)
VALUES (:id, :customerId, :amount)
ON CONFLICT (order_id) DO NOTHING;
~~~

Câu lệnh chỉ bỏ qua conflict trên order_id được chỉ định. Một unique constraint khác vẫn có thể gây lỗi.

Các database khác có cú pháp riêng:
- MySQL có INSERT ... ON DUPLICATE KEY UPDATE.
- Oracle có MERGE.
- SQL Server có thể dùng INSERT có điều kiện hoặc một chiến lược upsert phù hợp với isolation/locking.

Cần kiểm tra semantics của từng cú pháp. Ví dụ "do nothing" và "update existing" là hai chính sách nghiệp vụ khác nhau.

Upsert có ưu điểm:
- Không cần dùng exception làm luồng điều khiển cho duplicate bình thường.
- Có thể xử lý conflict ngay trong database.
- Giảm chi phí rollback/recovery khi duplicate phổ biến.
- Có thể xác định rõ cột nào được cập nhật.

Skip exception vẫn hữu ích khi duplicate là trường hợp hiếm, cần audit theo item hoặc writer không thể dùng câu lệnh conflict-aware. Không dùng INSERT IGNORE một cách rộng rãi nếu nó có thể biến nhiều lỗi dữ liệu khác thành warning hoặc bị bỏ qua ngoài ý muốn.

## 17. Pre-check tồn tại không giải quyết race condition

Có thể kiểm tra trước:

~~~sql
SELECT 1
FROM orders
WHERE order_id = :id;
~~~

Nếu không có dòng, ứng dụng mới insert. Cách này đôi khi giảm số lỗi duplicate khi nguồn chứa nhiều record đã tồn tại, nhưng không bảo đảm insert sẽ thành công vì một transaction khác có thể thêm cùng key sau lần kiểm tra.

Nếu dùng pre-check:
- Vẫn giữ unique constraint.
- Vẫn xử lý DuplicateKeyException ở bước insert.
- Tránh thực hiện một query cho từng item nếu volume lớn.
- Cân nhắc preload key theo page hoặc dùng staging khi phù hợp.
- Đo hiệu năng trước và sau.

Không coi pre-check là cơ chế đồng bộ giữa các Job chạy song song.

## 18. Phân biệt duplicate với lỗi dữ liệu khác

DataIntegrityViolationException có thể bao gồm nhiều vi phạm khác nhau. Ví dụ:

| Lỗi | Ví dụ | Có nên skip như duplicate? |
|---|---|---|
| Unique constraint | order_id đã tồn tại | Chỉ khi nghiệp vụ cho phép |
| Primary key | ID bị lặp | Có thể là replay hoặc lỗi ID generator |
| Foreign key | customer_id không tồn tại | Thường cần xử lý riêng |
| Not-null | customer_id null | Thường là lỗi dữ liệu |
| Check constraint | amount âm khi không được phép | Thường là lỗi nghiệp vụ |
| Length/type violation | Chuỗi quá dài hoặc kiểu không hợp lệ | Cần reject hoặc fail theo policy |

Nếu skip toàn bộ DataIntegrityViolationException, Job có thể bỏ qua các record hỏng mà không phân biệt duplicate hợp lệ với dữ liệu không thể lưu.

Nên dùng class cụ thể hoặc custom exception chỉ cho unique conflict đã được xác nhận. Nếu driver chỉ cung cấp SQLException chung, policy phải kiểm tra SQLState/vendor code và cause chain một cách có chủ đích.

## 19. Skip theo custom policy khi cần nhận diện constraint cụ thể

Có hệ thống có nhiều unique constraint và chỉ một số constraint được phép skip. Ví dụ external_reference duplicate là replay hợp lệ, còn order_id duplicate nhưng payload khác là conflict.

Trong trường hợp này, có thể dùng SkipPolicy riêng thay cho skip theo class đơn giản. Policy cần:
- Duyệt cause chain để tìm SQLException hoặc DataAccessException.
- Nhận diện đúng SQLState hoặc vendor code.
- Xác định constraint nếu driver cung cấp thông tin đó.
- Chỉ trả lời skippable cho loại conflict được nghiệp vụ cho phép.
- Tôn trọng skip limit hoặc giới hạn riêng.
- Ném lỗi cho các loại vi phạm khác.

Tên constraint trong exception message không phải API ổn định trên mọi database. Nếu cần nhận diện theo constraint name, hãy dùng cơ chế driver/database đã được kiểm chứng hoặc thiết kế writer để chuyển lỗi thành custom domain exception.

Không viết policy chỉ dựa trên chuỗi message như "duplicate" hoặc "unique". Message có thể thay đổi theo locale và driver.

## 20. Xử lý xung đột cùng key nhưng khác dữ liệu

Một record trùng khóa có thể có payload khác với record đã tồn tại. Đây là tình huống cần quy tắc rõ ràng.

Ví dụ:

~~~text
Database:
  order_id = 100
  amount = 120.00
  version = 1

Incoming:
  order_id = 100
  amount = 150.00
  version = 2
~~~

Một số lựa chọn:
- **Replay giống hệt:** so sánh checksum hoặc các field nghiệp vụ; ghi nhận đã tồn tại và skip.
- **Bản cập nhật mới hợp lệ:** dùng upsert hoặc versioned update theo optimistic locking.
- **Xung đột:** route vào quarantine để con người hoặc quy trình khác xử lý.
- **Dữ liệu nguồn sai:** fail Step hoặc reject record theo contract.

DuplicateKeyException không chứa đủ thông tin để chọn một trong các chính sách này. Có thể cần query record hiện có sau khi transaction được rollback, hoặc dùng SQL conflict-aware trả về trạng thái đã insert/đã tồn tại.

Không tự động cập nhật mọi cột khi gặp duplicate. Điều đó có thể ghi đè dữ liệu mới hơn bằng dữ liệu cũ được gửi lại.

## 21. Retry, deadlock và duplicate key

Duplicate key thường là lỗi deterministic đối với cùng INSERT và cùng key đã tồn tại. Retry nguyên thao tác thường không làm nó biến mất.

Deadlock hoặc serialization failure có thể là lỗi transient và được xử lý bằng retry nếu transaction có thể chạy lại an toàn.

Ví dụ phân loại khái quát:

| Exception/tình huống | Hướng xử lý thường gặp |
|---|---|
| DuplicateKeyException đã xác định là replay hợp lệ | Skip hoặc insert-if-absent |
| Duplicate key nhưng payload xung đột | Fail hoặc quarantine |
| DeadlockLoserDataAccessException | Retry có giới hạn |
| Lỗi kết nối tạm thời | Retry theo policy và timeout |
| Not-null/foreign key violation | Reject hoặc fail theo nghiệp vụ |
| Lỗi SQL syntax/mapping | Fail, sửa cấu hình/code |

Không cấu hình retry và skip chồng lấn một cách thiếu chủ đích cho cùng exception. Xác định exception nào được retry, exception nào được skip và exception nào phải fail. Khi một thao tác có side effect ngoài transaction, retry cần idempotency.

## 22. Skip exception không thay thế idempotency

Unique constraint giúp database ngăn hai record cùng key, nhưng idempotency còn rộng hơn. Một Job có thể:
- Ghi database thành công nhưng gửi message thất bại.
- Ghi file thành công nhưng metadata Job chưa commit.
- Cập nhật database rồi process dừng trước khi acknowledgment.
- Retry một request tới dịch vụ ngoài đã xử lý lần trước.

Skip duplicate key chỉ giải quyết một kiểu conflict ở database. Nó không tự làm các side effect khác idempotent.

Có thể dùng:
- Idempotency key ổn định từ source event ID.
- Unique constraint trên idempotency key.
- Outbox table cho message publish.
- Inbox/deduplication table cho consumer.
- Upsert có version check.
- Reconciliation job để tìm record thiếu hoặc lệch.

Định danh idempotency nên ổn định qua lần launch và restart, không sinh UUID mới cho mỗi retry.

## 23. SkipListener và kiểm soát dữ liệu bị bỏ qua

Khi skip duplicate, nên lưu lại đủ thông tin để giải thích vì sao item không được insert. Nếu không audit, Job có thể hoàn thành nhưng không ai biết bao nhiêu record bị loại.

Một báo cáo vận hành có thể chứa:

~~~text
Job: importOrders
JobInstance: 52
Step: importOrdersStep

Read count:       10,000
Write count:       9,920
Write skip count:     80
Status: COMPLETED
~~~

Số liệu chỉ có ý nghĩa khi đối chiếu đúng loại skip. Nếu Step còn skip ở read/process, tổng skip count có thể lớn hơn duplicate write skip. Hãy dùng listener hoặc custom metrics để tách lý do và phase.

Có thể lưu:
- Tổng duplicate được chấp nhận.
- Số duplicate cùng payload.
- Số key xung đột payload.
- Số lỗi unique constraint không nhận diện.
- Số item được đưa vào quarantine.

Nếu tỷ lệ duplicate tăng đột ngột, đó có thể là dấu hiệu upstream replay, Job bị chạy trùng hoặc business key được tạo sai.

## 24. Restart và duplicate key

Restart có thể gặp lại item đã ghi thành công trước khi process gặp lỗi ở một bước khác. Tùy transaction và checkpoint, item có thể được đọc/ghi lại.

Unique constraint và idempotent write là lớp bảo vệ hữu ích, nhưng cần phân biệt:
- Item đã commit trong chunk trước: checkpoint thường đã tiến qua item đó.
- Item trong chunk bị rollback: database transaction rollback các insert trong chunk đó.
- Side effect ngoài transaction: có thể tồn tại dù chunk rollback.
- Process crash giữa các hệ thống: trạng thái có thể cần reconciliation.

Nếu writer insert duplicate và Step skip, hãy xác nhận item hiện có là cùng logical event. Đừng coi mọi duplicate sau restart là an toàn; output file, message và audit có thể vẫn bị ghi lặp.

Tên reader/writer, query, identifying JobParameters và thứ tự input cũng cần ổn định qua restart. Nếu JobInstance mới được tạo cho cùng business data, unique key vẫn có thể ngăn insert trùng, nhưng chính sách skip/upsert phải xác định rõ.

## 25. Duplicate giữa các Job chạy đồng thời

Hai JobInstance có thể cùng xử lý một nguồn hoặc cùng business key. Pre-check trước insert không ngăn được race. Unique constraint sẽ chọn transaction thắng và transaction còn lại nhận duplicate.

Cần cân nhắc:
- Có cho phép hai Job cùng xử lý một tenant/batch không?
- Có cơ chế claim hoặc lock input không?
- Unique key có phạm vi toàn hệ thống hay chỉ trong một tenant?
- Job thua cuộc nên skip, retry đọc lại hay fail?
- Audit có thể xác định Job nào tạo record đầu tiên không?
- Output ngoài database có bị tạo hai lần không?

Nếu hai Job cùng chạy là điều không mong muốn, dùng JobParameters identifying phù hợp, lock/claim hoặc orchestration để ngăn launch trùng. Skip duplicate là lớp bảo vệ cuối, không thay thế điều phối Job.

## 26. Kiểm thử duplicate key với database thực tế

Test bằng mock có thể xác nhận cấu hình Step gọi listener, nhưng không chứng minh exception translator của JDBC driver trả đúng loại exception. Nên có integration test với database và driver gần production.

Các tình huống cần kiểm tra:

| Kịch bản | Điều cần xác nhận |
|---|---|
| Insert key mới | Record được insert |
| Insert primary key đã tồn tại | Duplicate được phân loại đúng |
| Trùng unique business key khác | Policy phân biệt đúng constraint nếu cần |
| Duplicate trong cùng chunk | Chỉ item cần skip bị bỏ |
| Duplicate đã có từ Job trước | Job tiếp tục theo chính sách idempotency |
| Payload cùng key nhưng khác nội dung | Conflict được phát hiện, không âm thầm bỏ |
| Vượt skip limit | Step FAILED |
| Lỗi foreign key/not-null | Không bị nhầm thành duplicate hợp lệ |
| Writer dùng JDBC batch | Driver exception được dịch và item lỗi được xác định |
| SkipListener | Audit đúng item và phase |
| Audit failure | Hành vi transaction/Step đúng policy |
| Hai transaction cạnh tranh cùng key | Unique constraint bảo vệ dữ liệu |
| Restart sau chunk commit | Không ghi trùng hoặc bỏ sót item |
| Retry deadlock | Chỉ lỗi transient được retry |

Một integration test cơ bản:
1. Tạo bảng với primary key và unique constraint.
2. Insert sẵn một record đại diện cho duplicate.
3. Launch Job với input gồm một key mới, một key đã tồn tại và một key mới khác.
4. Xác nhận key mới được ghi, duplicate được skip và item sau đó vẫn được xử lý.
5. Xác nhận SkipListener nhận đúng business key.
6. Kiểm tra StepExecution skip count và write count.
7. Thử số duplicate vượt skipLimit và xác nhận Step thất bại.
8. Thử một lỗi integrity khác và xác nhận nó không bị skip nhầm.

## 27. Lỗi thường gặp

**Skip toàn bộ DataIntegrityViolationException.** Foreign key, not-null hoặc check constraint có thể bị che giấu cùng duplicate.

**Dùng pre-check thay cho unique constraint.** Hai Job đồng thời vẫn có thể insert cùng key.

**Retry duplicate không có điều kiện.** Cùng INSERT thường tiếp tục thất bại khi key vẫn tồn tại.

**Coi cùng key là cùng payload.** Record hiện có có thể xung đột với dữ liệu nguồn.

**Không đặt skipLimit rõ ràng.** Một batch có thể bỏ qua quá nhiều item mà không đạt ngưỡng nghiệp vụ.

**Quên skip count tính ở nhiều phase.** Skip limit không chỉ đếm lỗi writer nếu Step còn skip ở read/process.

**Không kiểm tra exception translation.** Driver có thể ném SQLException hoặc BatchUpdateException thay vì DuplicateKeyException.

**Dùng message text để nhận diện duplicate.** Message phụ thuộc driver, locale và version.

**Không ghi audit cho item bị skip.** Khó điều tra tỷ lệ duplicate và record đã bị bỏ qua.

**Audit bằng side effect không idempotent.** Retry/recovery có thể tạo audit trùng.

**Dùng skip để che lỗi ID generator.** Duplicate có thể báo lỗi cấu hình nghiêm trọng.

**Cho rằng filesystem và message rollback cùng database.** External side effect có thể còn tồn tại sau rollback.

**Không kiểm thử với JDBC batch thật.** Mock không thể mô phỏng chính xác hành vi driver khi một item trong batch vi phạm constraint.

## 28. Quy trình triển khai skip duplicate key

Khi cần bỏ qua duplicate key trong Spring Batch, hãy thực hiện theo trình tự:

1. Xác định primary key và unique constraint nào có thể bị trùng.
2. Phân biệt replay hợp lệ với xung đột cùng key nhưng khác payload.
3. Giữ unique constraint ở database làm cơ chế bảo vệ cuối cùng.
4. Dùng Spring JDBC hoặc exception translator để nhận diện DuplicateKeyException ổn định.
5. Cấu hình faultTolerant(), skip(DuplicateKeyException.class) và skipLimit tường minh.
6. Chỉ dùng exception class hẹp; tránh skip mọi DataIntegrityViolationException.
7. Nếu cần nhận diện một constraint cụ thể, dùng custom exception hoặc SkipPolicy dựa trên SQLState/vendor code đã kiểm chứng.
8. Đăng ký SkipListener để audit item bị skip.
9. Xác định transaction semantics của audit và external side effect.
10. Chọn skip cho duplicate hiếm, hoặc upsert/insert-if-absent khi duplicate là luồng bình thường.
11. Dùng retry cho lỗi transient như deadlock; không retry duplicate deterministic một cách mù quáng.
12. Giữ idempotency key và routing rule ổn định qua retry/restart.
13. Kiểm thử duplicate trong cùng chunk, duplicate từ lần chạy trước, concurrent insert và skip limit trên database thật.
14. Theo dõi skip count, tỷ lệ duplicate, xung đột payload và lỗi integrity khác trong vận hành.

Skip duplicate key cho phép Spring Batch tiếp tục khi một item vi phạm unique constraint đã được xác định là có thể bỏ qua. Database vẫn là nơi bảo đảm tính duy nhất; skip policy quyết định lỗi nào được chấp nhận; SkipListener giúp truy vết item bị loại. Khi phân biệt replay hợp lệ với xung đột dữ liệu, đặt giới hạn rõ ràng và kiểm thử đúng driver/transaction, Job có thể xử lý dữ liệu gửi lại mà vẫn phát hiện được lỗi thực sự.


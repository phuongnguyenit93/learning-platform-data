# Deadlock và retry transaction

Trong Spring Batch, một Step thường đọc, xử lý và ghi dữ liệu theo từng chunk. Mỗi chunk được thực hiện trong một transaction do transaction manager quản lý. Khi nhiều Job, Step hoặc ứng dụng cùng truy cập một nhóm dữ liệu, các transaction có thể tranh chấp khóa database. Một tình huống tranh chấp đặc biệt là **deadlock**: hai hoặc nhiều transaction giữ khóa mà transaction còn lại cần, tạo thành vòng chờ không thể tự giải quyết.

Database thường phát hiện deadlock và chọn một transaction làm nạn nhân để rollback. Ứng dụng có thể thử lại transaction đó sau một khoảng chờ ngắn. Trong Spring Batch, retry cần được cấu hình có giới hạn và đặt ở ranh giới phù hợp để lần thử tiếp theo chạy trong transaction mới. Retry giúp xử lý xung đột tạm thời; nó không thay thế việc sửa câu SQL, thứ tự cập nhật hoặc thiết kế khóa gây deadlock.

## 1. Deadlock là gì?

Deadlock xảy ra khi các transaction giữ tài nguyên mà transaction khác đang chờ, tạo thành một chu trình chờ. Database không thể cho tất cả transaction tiếp tục, vì vậy hệ quản trị cơ sở dữ liệu phát hiện chu trình và thường chọn một transaction để rollback nhằm giải phóng khóa.

Ví dụ, hai transaction cập nhật hai tài khoản theo thứ tự ngược nhau:

```text
Transaction A                 Transaction B
--------------                 --------------
LOCK account 10                LOCK account 20
       |                              |
       v                              v
UPDATE account 10              UPDATE account 20
       |                              |
       v                              v
WAIT account 20                WAIT account 10
       |                              |
       +---------- DEADLOCK ----------+
```

Transaction A giữ khóa trên account 10 và chờ account 20. Transaction B giữ khóa trên account 20 và chờ account 10. Mỗi transaction đều chờ khóa do transaction kia nắm giữ. Database phát hiện vòng chờ và rollback một transaction, ví dụ Transaction B. Khi khóa được giải phóng, Transaction A có thể tiếp tục.

Deadlock không nhất thiết chỉ xuất hiện khi hai transaction cập nhật cùng một bảng. Một transaction có thể khóa bảng đơn hàng rồi cần bảng tồn kho, trong khi transaction khác khóa bảng tồn kho rồi cần bảng đơn hàng. Chu trình khóa giữa nhiều bảng vẫn tạo deadlock.

## 2. Phân biệt deadlock với lock wait timeout

Deadlock và lock wait timeout đều liên quan đến việc transaction không lấy được khóa đúng lúc, nhưng bản chất khác nhau.

| Tình huống | Ý nghĩa | Hành vi thường gặp |
|---|---|---|
| Deadlock | Các transaction tạo thành chu trình chờ khóa | Database phát hiện chu trình và rollback một transaction |
| Lock wait timeout | Một transaction chờ khóa lâu hơn thời gian cho phép | Database hoặc cấu hình transaction kết thúc thao tác/transaction đang chờ |
| Optimistic locking conflict | Dữ liệu đã bị transaction khác thay đổi trước khi cập nhật | Cập nhật không khớp version hoặc số hàng mong đợi; ứng dụng phải đọc lại và quyết định xử lý |

Không phải mọi lỗi khóa đều nên được retry giống nhau. Deadlock thường là xung đột có khả năng tự hết sau khi transaction khác kết thúc. Lock timeout cũng có thể tạm thời, nhưng có thể cho thấy transaction khác giữ khóa quá lâu. Optimistic locking conflict có thể yêu cầu đọc lại dữ liệu và tính toán lại theo trạng thái mới.

Ứng dụng nên dựa vào exception được database driver và Spring dịch ra, mã lỗi vendor, cùng quy tắc nghiệp vụ để phân loại. Không nên bắt mọi `DataAccessException` rồi retry, vì lỗi cú pháp SQL, constraint violation hoặc dữ liệu không hợp lệ thường không tự hết khi thử lại.

## 3. Vì sao Spring Batch có thể gặp deadlock?

Deadlock thường xuất hiện khi có nhiều transaction thực hiện thao tác đọc/ghi chồng lấn. Trong một hệ thống batch, các nguồn tranh chấp có thể gồm:

- Nhiều Job cùng cập nhật một bảng hoặc cùng một nhóm tài khoản.
- Một Job chạy song song qua nhiều worker hoặc partition có phạm vi dữ liệu chồng lấn.
- Batch Job và ứng dụng trực tuyến cùng cập nhật dữ liệu nghiệp vụ.
- Các transaction cập nhật nhiều bảng theo thứ tự khác nhau.
- Câu truy vấn quét nhiều hàng do thiếu index phù hợp, khiến phạm vi khóa lớn hơn dự kiến.
- Chunk quá lớn giữ khóa lâu và làm tăng thời gian transaction.
- Một transaction thực hiện thao tác chậm hoặc gọi hệ thống bên ngoài trong lúc đang giữ khóa.

Ví dụ, Job A xử lý đơn hàng theo `order_id` tăng dần nhưng Job B xử lý tồn kho rồi cập nhật đơn hàng theo thứ tự khác. Nếu hai Job khóa các hàng theo thứ tự ngược nhau, chúng có thể tạo chu trình chờ.

Chỉ tăng số thread hoặc số partition không đảm bảo Job chạy nhanh hơn. Mức song song cao hơn có thể tăng throughput khi dữ liệu độc lập, nhưng cũng làm tăng cạnh tranh khóa khi nhiều worker truy cập cùng dữ liệu.

## 4. Database phát hiện và xử lý deadlock như thế nào?

Database quản lý khóa và theo dõi quan hệ chờ giữa các transaction. Khi phát hiện chu trình deadlock, database chọn một transaction làm nạn nhân. Việc chọn có thể dựa trên chi phí rollback, lượng công việc đã thực hiện hoặc quy tắc riêng của hệ quản trị cơ sở dữ liệu.

Transaction bị chọn thường nhận lỗi deadlock và bị rollback. Các transaction còn lại có thể tiếp tục sau khi khóa được giải phóng. Ứng dụng không nên giả định transaction bị rollback luôn là transaction mới nhất hoặc ít dữ liệu nhất; chính sách chọn nạn nhân phụ thuộc database.

Các database cung cấp công cụ để xem thông tin deadlock, chẳng hạn deadlock graph, transaction đang giữ/chờ khóa, câu SQL liên quan và đối tượng bị khóa. Khi sự cố lặp lại, cần thu thập dữ liệu này để tìm nguyên nhân thay vì chỉ tăng retry limit.

## 5. Retry transaction có ý nghĩa gì?

Khi một transaction bị database rollback do deadlock, các thao tác trong transaction đó không thể tiếp tục như chưa có chuyện gì xảy ra. Transaction thường đã bị đánh dấu rollback-only hoặc database đã hủy trạng thái transaction. Thử chạy lại riêng câu SQL trong chính transaction thất bại thường không giải quyết được vấn đề.

Retry đúng nghĩa là thực hiện lại đơn vị công việc trong một transaction mới:

```text
Lần thử 1
  Bắt đầu transaction
  Đọc / xử lý / ghi
  Database báo deadlock
  Rollback transaction
          |
          v
      Chờ backoff
          |
          v
Lần thử 2
  Bắt đầu transaction mới
  Thực hiện lại đơn vị công việc
  Commit nếu thành công
```

Trong Spring Batch, với chunk-oriented Step, transaction thường bao quanh một chunk. Nếu thao tác writer gặp deadlock, chunk có thể rollback. Cơ chế fault tolerance và retry của Step có thể thử lại theo chính sách đã cấu hình. Chi tiết item nào được đọc hoặc xử lý lại phụ thuộc loại exception, reader buffering, retry policy và cấu hình Step; thiết kế phải giả định rằng logic trong chunk có thể được thực hiện lại.

Retry nên có giới hạn. Nếu database đang quá tải hoặc có deadlock liên tục do thiết kế khóa, retry vô hạn chỉ làm tăng tải và kéo dài thời gian Job.

## 6. Cấu hình retry deadlock trong Spring Batch

Với chunk-oriented Step, có thể dùng `faultTolerant()` và chỉ định exception cần retry. Ví dụ sau minh họa Spring Batch 5:

```java
@Bean
Step updateAccountsStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<AccountChange> reader,
        ItemProcessor<AccountChange, AccountChange> processor,
        ItemWriter<AccountChange> writer) {

    return new StepBuilder("updateAccountsStep", jobRepository)
            .<AccountChange, AccountChange>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .retry(PessimisticLockingFailureException.class)
            .retryLimit(3)
            .build();
}
```

`PessimisticLockingFailureException` là nhóm exception của Spring cho lỗi khóa theo cơ chế pessimistic. Tùy database, driver và `SQLExceptionTranslator`, lỗi deadlock cụ thể có thể được ánh xạ sang lớp con khác, chẳng hạn `DeadlockLoserDataAccessException` trong một số phiên bản hoặc `CannotAcquireLockException`. Trong production, nên kiểm tra exception thực tế được ném ra và cấu hình loại hẹp nhất có thể cho lỗi muốn retry. Retry cả nhóm exception rộng có thể khiến những lỗi khóa không phù hợp cũng bị thử lại.

`retryLimit(3)` đặt giới hạn retry theo API của phiên bản đang dùng. Hãy xác nhận cách tính số lần thử của phiên bản Spring Batch trong dự án và ghi rõ giới hạn vận hành. Nếu lỗi vẫn tiếp tục sau số lần cho phép, Step thất bại để người vận hành điều tra.

Không nên cấu hình `.skip(PessimisticLockingFailureException.class)` như một cách xử lý deadlock thông thường. Deadlock không có nghĩa item đầu vào sai; bỏ qua item có thể làm mất cập nhật nghiệp vụ. Thông thường nên retry transaction/chunk, sau đó để Job thất bại nếu không thể hoàn tất.

## 7. Thêm backoff giữa các lần retry

Nếu retry ngay lập tức, transaction mới có thể gặp lại đúng tình trạng cạnh tranh khóa trước khi transaction khác kịp hoàn tất. Backoff tạo một khoảng chờ trước lần thử tiếp theo, giúp giảm khả năng nhiều worker đồng loạt va chạm lại.

Có thể cấu hình `ExponentialBackOffPolicy`:

```java
@Bean
ExponentialBackOffPolicy deadlockBackOffPolicy() {
    ExponentialBackOffPolicy policy = new ExponentialBackOffPolicy();
    policy.setInitialInterval(200L);
    policy.setMultiplier(2.0);
    policy.setMaxInterval(2_000L);
    return policy;
}
```

Gắn policy vào Step:

```java
return new StepBuilder("updateAccountsStep", jobRepository)
        .<AccountChange, AccountChange>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(PessimisticLockingFailureException.class)
        .retryLimit(3)
        .backOffPolicy(deadlockBackOffPolicy)
        .build();
```

Với exponential backoff, thời gian chờ tăng dần theo số lần thử cho đến giới hạn tối đa. Có thể thêm jitter nếu thư viện hoặc policy đang dùng hỗ trợ, để nhiều worker không cùng thức dậy và gửi lại transaction vào một thời điểm.

Backoff cần phù hợp với batch window. Chờ quá lâu có thể khiến Job không kịp hoàn tất; chờ quá ngắn có thể làm deadlock lặp lại. Cần đo thực tế và tránh nhân đôi backoff ở nhiều tầng retry.

## 8. Retry ở đâu để transaction được tạo mới?

Điểm đặt retry rất quan trọng. Nếu code bắt lỗi deadlock bên trong một transaction rồi lặp lại câu SQL ngay trong cùng transaction, database có thể đã đánh dấu transaction rollback-only hoặc hủy transaction. Lần thử tiếp theo không còn một transaction hợp lệ để thực hiện.

Với Spring Batch, nên cấu hình retry ở cơ chế fault tolerance của Step để framework quản lý rollback và thực hiện lần thử lại theo ranh giới transaction. Mỗi lần thử cần có transaction phù hợp mới được mở bởi transaction manager.

Nếu tự xây dựng retry quanh một service dùng `TransactionTemplate`, cấu trúc khái quát cần đặt transaction bên trong vòng retry, để mỗi lần lặp tạo transaction mới:

```text
Retry controller
    |
    +--> Attempt 1 -> Transaction 1 -> deadlock -> rollback
    |
    +--> backoff
    |
    +--> Attempt 2 -> Transaction 2 -> success -> commit
```

Không đặt vòng retry bên trong một phương thức `@Transactional` duy nhất nếu điều đó khiến tất cả lần thử dùng chung transaction đã hỏng. Cũng cần chú ý proxy của Spring: gọi một phương thức `@Transactional` khác trong cùng object bằng self-invocation có thể không đi qua proxy và không tạo transaction mới như mong đợi.

Tránh xếp chồng `@Retryable`, retry của HTTP client và retry của Spring Batch mà không tính tổng số lần thử. Nhiều tầng retry có thể nhân số request hoặc số lần cập nhật lên rất lớn.

## 9. Giảm deadlock từ thiết kế database và transaction

Retry xử lý tình huống tạm thời, nhưng giảm nguyên nhân deadlock thường đem lại hiệu quả lâu dài hơn.

### Khóa các hàng theo cùng một thứ tự

Nếu nhiều transaction cần cập nhật cùng một nhóm hàng, hãy thống nhất thứ tự truy cập. Ví dụ, mọi Job cập nhật tài khoản theo `account_id` tăng dần. Điều này làm giảm khả năng transaction A khóa hàng 10 rồi chờ 20 trong khi transaction B khóa 20 rồi chờ 10.

Với thao tác cập nhật nhiều bảng, nên thống nhất thứ tự bảng và thứ tự hàng giữa các luồng nghiệp vụ.

### Giữ transaction ngắn

Chỉ giữ transaction trong khoảng thời gian cần thiết để đọc/ghi dữ liệu liên quan. Tránh gọi HTTP API, gửi email, chờ người dùng hoặc thực hiện tính toán nặng khi transaction đang giữ khóa. Nếu cần lấy dữ liệu tham chiếu từ hệ thống ngoài, cân nhắc lấy trước hoặc dùng snapshot.

### Tạo index phù hợp

Truy vấn thiếu index có thể quét nhiều hàng, làm tăng số hàng bị khóa hoặc thời gian giữ khóa tùy database và isolation level. Index trên cột lọc, join và khóa cập nhật có thể giúp truy vấn tìm đúng hàng nhanh hơn. Tuy nhiên, index cũng làm tăng chi phí ghi; cần xem execution plan và hành vi khóa của database thực tế.

### Giảm phạm vi cập nhật

Chỉ cập nhật các hàng và cột cần thiết. Tránh giữ khóa trên một tập dữ liệu rộng khi có thể chia thành các phạm vi không chồng lấn. Điều kiện `WHERE` cần đủ chọn lọc và có index phù hợp.

### Giảm kích thước chunk khi phù hợp

Chunk nhỏ hơn có thể làm transaction ngắn hơn và giảm thời gian giữ khóa. Đổi lại, số lần commit tăng và throughput có thể giảm. Hãy thử nhiều chunk size trên dữ liệu đại diện thay vì giảm tùy tiện.

### Kiểm soát mức song song

Giảm số worker hoặc partition đồng thời có thể làm giảm cạnh tranh khóa. Nếu các partition có phạm vi dữ liệu độc lập, hãy phân chia bằng khóa không chồng lấn. Tránh để nhiều worker cùng cập nhật một nhóm tài khoản hoặc cùng một bản ghi tổng hợp.

## 10. Isolation level có thể ảnh hưởng deadlock

Isolation level quy định mức độ một transaction nhìn thấy thay đổi của transaction khác và cách database khóa hoặc kiểm soát phiên bản dữ liệu. Mức cô lập cao hơn có thể tăng khả năng chờ hoặc phạm vi khóa trong một số database; mức thấp hơn có thể cải thiện concurrency nhưng cho phép các hiện tượng đọc khác nhau.

Không nên hạ isolation level chỉ để hết deadlock mà chưa xác định yêu cầu nhất quán dữ liệu. Ví dụ, một Job tính số dư hoặc đối soát có thể cần bảo đảm một tập dữ liệu nhất quán. Thay đổi isolation có thể làm kết quả không còn đáp ứng quy tắc nghiệp vụ.

Hãy kiểm tra:

- Isolation level thực tế của transaction manager và database.
- Câu truy vấn dùng `SELECT ... FOR UPDATE` hay loại khóa đặc biệt nào.
- Database dùng khóa hàng, khóa trang, khóa phạm vi hay cơ chế MVCC ra sao.
- Index và execution plan có làm thay đổi phạm vi khóa không.
- Có thể dùng optimistic locking bằng cột version cho những cập nhật ít xung đột không.

Optimistic locking phát hiện xung đột khi version đã thay đổi, thường thông qua số hàng cập nhật bằng 0 hoặc exception tương ứng. Nó không giống deadlock; ứng dụng thường phải đọc lại dữ liệu và tính toán lại thay đổi dựa trên version mới.

## 11. Idempotency và tác dụng phụ khi retry

Retry có thể khiến một phần logic được thực hiện lại. Nếu toàn bộ thao tác nằm trong cùng transaction database và transaction rollback hoàn toàn, các thay đổi trong transaction đó được hoàn tác. Nhưng các tác dụng phụ ngoài transaction có thể vẫn tồn tại.

Ví dụ, processor gọi API đối tác để tạo giao dịch, sau đó writer cập nhật database và gặp deadlock. Database rollback nhưng giao dịch đối tác đã được tạo. Nếu chunk được retry, API có thể được gọi lại và tạo giao dịch trùng.

Để giảm rủi ro:

- Dùng idempotency key ổn định theo mã nghiệp vụ của item.
- Bảo đảm hệ thống đích kiểm tra key và trả lại kết quả của lần gọi trước thay vì tạo tác dụng phụ mới.
- Ghi sự kiện cần gửi vào transactional outbox rồi phát lại bằng consumer có idempotency.
- Tách thao tác đọc dữ liệu tham chiếu khỏi thao tác tạo tác dụng phụ.
- Có bước đối soát khi kết quả của một lời gọi ngoài không xác định do timeout.

Không nên giả định một request timeout nghĩa là service đích chưa thực hiện thao tác. Có thể server đã commit nhưng response bị mất trên đường truyền. Retry một request ghi mà không có idempotency có thể gây trùng ngay cả khi không có deadlock.

## 12. Theo dõi và điều tra deadlock

Khi Job gặp lỗi khóa, cần thu thập đủ thông tin để xác định nguyên nhân:

- JobExecution ID, StepExecution ID và tên Job/Step.
- Chunk hoặc business key đang được xử lý khi lỗi xảy ra.
- Exception đầy đủ, SQLState, vendor error code và nguyên nhân gốc.
- Câu SQL và thứ tự thao tác cập nhật của transaction.
- Thời điểm bắt đầu/kết thúc transaction và thời gian chờ khóa.
- Deadlock graph hoặc log tương ứng từ database.
- Số lần retry, backoff và kết quả từng lần thử.

Không log dữ liệu nhạy cảm hoặc toàn bộ payload nếu không cần thiết. Có thể log mã bản ghi và correlation ID để truy vết.

Các metrics hữu ích:

| Metric | Điều cần quan sát |
|---|---|
| Deadlock count | Số deadlock theo database, Job và khoảng thời gian |
| Retry count | Số lần transaction/chunk phải thử lại |
| Retry exhausted | Số lần Step thất bại sau khi hết retry |
| Transaction duration | Thời gian transaction và phân bố p95/p99 |
| Lock wait time | Thời gian chờ khóa |
| Chunk duration | Thời gian xử lý từng chunk |
| Job throughput | Số item hoàn tất mỗi giây/phút |

Nếu retry tăng mạnh nhưng Job vẫn hoàn tất, hệ thống có thể đang che giấu một vấn đề cạnh tranh khóa. Nếu deadlock tập trung vào cùng một bảng hoặc nhóm business key, cần điều tra câu SQL và cách phân chia dữ liệu.

## 13. Quy trình xử lý khi Step gặp deadlock

Một quy trình vận hành thực tế có thể gồm:

1. Xác định StepExecution và chunk gặp lỗi từ log cùng metadata Spring Batch.
2. Xem exception, SQLState và vendor error code để xác nhận đó là deadlock hay lock timeout.
3. Kiểm tra deadlock graph/log của database để tìm các transaction, câu SQL và khóa tạo chu trình.
4. Xác định các Job, worker hoặc ứng dụng trực tuyến đang cập nhật cùng dữ liệu.
5. Kiểm tra thứ tự truy cập bảng/hàng, index, transaction duration và chunk size.
6. Sửa nguyên nhân chính, chẳng hạn thống nhất thứ tự khóa hoặc tách phạm vi dữ liệu.
7. Cấu hình retry giới hạn và backoff cho lỗi tạm thời đã xác định.
8. Xác minh writer và service ngoài an toàn khi chunk được thực hiện lại.
9. Chạy lại trong môi trường đại diện, theo dõi deadlock count, retry count và throughput.

Không nên chỉ tăng retry limit để làm biến mất cảnh báo. Nếu deadlock xuất hiện thường xuyên, retry có thể kéo dài Job, tăng tải database và che giấu một thiết kế truy cập dữ liệu không phù hợp.

## 14. Các lỗi thường gặp khi retry transaction

**Retry mọi exception:** lỗi dữ liệu, SQL sai hoặc vi phạm constraint không tự hết khi thử lại. Chỉ retry exception được xác định là tạm thời.

**Retry câu SQL trong transaction đã rollback-only:** transaction cũ không còn hợp lệ. Mỗi lần thử phải chạy trong transaction mới.

**Retry vô hạn:** làm Job kéo dài và tăng tải khi database đang gặp sự cố. Đặt giới hạn, backoff và chính sách thất bại rõ ràng.

**Skip deadlock như lỗi dữ liệu:** có thể bỏ mất cập nhật hợp lệ. Deadlock thường nên retry transaction/chunk thay vì bỏ qua item.

**Giữ transaction trong lúc gọi service ngoài:** thời gian chờ mạng làm khóa được giữ lâu hơn, tăng khả năng deadlock. Tách lời gọi ngoài khỏi vùng transaction khi nghiệp vụ cho phép.

**Không bảo đảm idempotency:** lần retry có thể lặp tác dụng phụ đã xảy ra ngoài database transaction.

**Không kiểm tra exception thực tế:** mỗi database và driver có thể ánh xạ deadlock sang mã lỗi hoặc exception khác nhau. Cần kiểm tra translator và log của hệ thống.

**Chỉ giảm chunk size mà không tìm nguyên nhân:** chunk nhỏ có thể giảm thời gian giữ khóa nhưng không loại bỏ vòng khóa do thứ tự cập nhật ngược nhau.

## Kết luận

Deadlock xảy ra khi các transaction giữ khóa và chờ lẫn nhau theo một chu trình. Database thường rollback một transaction để giải phóng khóa; Spring Batch có thể retry lỗi khóa tạm thời bằng cơ chế fault tolerance của chunk-oriented Step. Retry cần có giới hạn, backoff và phải chạy lại trong transaction mới. Để giảm deadlock lâu dài, hãy thống nhất thứ tự cập nhật hàng và bảng, giữ transaction ngắn, tối ưu index, giảm phạm vi khóa và kiểm soát mức song song. Đồng thời, thiết kế thao tác ghi cùng tác dụng phụ bên ngoài theo hướng idempotent để retry hoặc restart không tạo dữ liệu trùng.

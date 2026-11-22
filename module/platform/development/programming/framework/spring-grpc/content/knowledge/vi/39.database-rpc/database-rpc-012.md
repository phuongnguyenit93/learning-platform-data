# Kiểm thử rollback và retry

## 1. Kiểm thử điều gì trong database RPC?

Trong **SPRING_GRPC**, một unary RPC có thể ghi nhiều bảng trong cùng một nghiệp vụ: tạo order, cập nhật inventory, lưu idempotency record và ghi outbox event. Nếu một bước thất bại, transaction phải rollback toàn bộ thay đổi thuộc cùng đơn vị công việc. Khi lỗi có thể phục hồi như deadlock hoặc serialization conflict, hệ thống có thể thử lại nghiệp vụ trong một transaction mới.

Hai thuộc tính cần chứng minh độc lập:

- **Rollback:** một attempt thất bại không để lại thay đổi database một phần.
- **Retry:** attempt tiếp theo đọc trạng thái mới và chạy lại toàn bộ use case trong transaction riêng.

Kiểm thử chỉ xác nhận RPC trả lỗi là chưa đủ. Server có thể trả lỗi nhưng một số row đã commit; hoặc retry có thể chạy lại trong cùng transaction đã bị đánh dấu rollback-only. Cần quan sát database sau mỗi kịch bản và xác nhận số lần thực thi, transaction boundary, side effect cùng status gRPC.

Bài tập trung vào:

- Tạo failure có kiểm soát sau khi đã ghi dữ liệu.
- Kiểm tra rollback bằng một transaction/connection độc lập.
- Kiểm thử qua gRPC để xác nhận status và observer lifecycle.
- Bảo đảm mỗi retry mở transaction mới.
- Phân loại lỗi transient và permanent.
- Kiểm thử idempotency khi response mất sau commit.
- Dùng Testcontainers, concurrency control và fault injection để giảm test flaky.

## 2. Xác định transaction boundary trước khi viết test

Một use case Spring thường được đặt trong application service có @Transactional. gRPC adapter gọi service qua Spring bean proxy; proxy bắt đầu transaction trước khi chạy method và commit/rollback trước khi trả kết quả về adapter.

Luồng thành công:

1. Adapter nhận và validate request.
2. Application service bắt đầu transaction.
3. Service ghi business data và outbox/idempotency record nếu cần.
4. Method trả kết quả.
5. Spring transaction interceptor commit.
6. Adapter nhận kết quả sau commit và phát onNext/onCompleted.

Luồng thất bại:

1. Service đã thực hiện một hoặc nhiều lệnh ghi.
2. Một lỗi runtime hoặc lỗi database xảy ra.
3. Transaction rollback.
4. Exception thoát khỏi proxy về adapter.
5. Adapter ánh xạ exception thành gRPC status và phát onError.

Với lỗi chỉ xuất hiện khi flush/commit, method target có thể đã chạy tới return nhưng proxy vẫn ném exception khi hoàn tất transaction. Vì vậy, adapter chỉ được gửi response thành công sau khi lời gọi transactional qua proxy trả về bình thường.

## 3. Không dùng test-level transaction để giả lập transaction của gRPC server

Một lỗi phổ biến là đánh dấu test method bằng @Transactional rồi gọi RPC qua channel. Server thường xử lý request trên thread khác và mở transaction riêng. Transaction của test không bao quanh transaction của server.

Điều này có thể gây hiểu nhầm:

- Fixture được tạo trong transaction test chưa commit có thể không nhìn thấy từ server thread.
- Transaction test có thể giữ snapshot hoặc lock làm thay đổi hành vi concurrency.
- Test framework rollback transaction của test khi kết thúc, nhưng transaction server có thể đã commit độc lập.
- Việc đọc assertion trong cùng transaction test có thể không thấy dữ liệu mới do isolation/snapshot.

Để kiểm thử transaction server:

- Tạo fixture bằng transaction đã commit trước khi gọi RPC.
- Không bọc test method trong transaction ngoài nếu mục tiêu là xác minh commit/rollback của server.
- Sau khi RPC kết thúc, đọc database bằng transaction hoặc connection độc lập.
- Dùng ID duy nhất cho từng test và cleanup có chủ đích.
- Với test cần nhiều transaction đồng thời, điều khiển chúng bằng barrier/latch thay vì dựa vào timing.

Có thể dùng @Transactional cho các unit test thuần application service nếu hiểu rõ proxy và transaction test, nhưng integration test qua gRPC cần chứng minh transaction thật của server.

## 4. Tạo lỗi có kiểm soát sau khi đã ghi dữ liệu

Rollback test cần kích hoạt lỗi tại vị trí xác định. Một cách là inject collaborator chỉ dùng trong test để ném exception sau bước ghi đầu tiên:

```java
@Service
@RequiredArgsConstructor
public class PlaceOrderService {
    private final OrderRepository orders;
    private final OutboxRepository outbox;
    private final FailureProbe failureProbe;

    @Transactional
    public OrderResult place(PlaceOrderCommand command) {
        Order order = orders.save(Order.create(command));

        failureProbe.afterOrderSaved();

        outbox.save(OutboxRecord.orderCreated(order));
        return OrderResult.from(order);
    }
}
```

Trong production, FailureProbe có implementation không làm gì; test thay bằng implementation ném exception theo kịch bản. Có thể dùng test profile hoặc bean override, tùy Spring version.

Nếu muốn kiểm tra lỗi database thật, tạo unique constraint violation hoặc lỗi flush có kiểm soát. Gọi repository.flush() trong test path có thể buộc ORM gửi SQL sớm, nhưng commit vẫn có thể phát sinh lỗi khác. Test nên ghi rõ đang kiểm tra exception khi flush hay khi commit.

Không dùng Thread.sleep để “hy vọng” lỗi xảy ra đúng lúc. Fault injection phải xác định và lặp lại được.

## 5. Xác nhận rollback bằng trạng thái database

Ví dụ application service ghi order rồi lỗi trước khi ghi outbox. Sau khi gọi RPC và nhận status lỗi, kiểm tra bằng connection độc lập:

```java
@Test
void rollsBackOrderWhenOutboxStepFails() {
    String orderId = uniqueOrderId();

    StatusRuntimeException error = assertThrows(
        StatusRuntimeException.class,
        () -> blockingStub.placeOrder(requestFor(orderId))
    );

    assertEquals(
        Status.Code.INTERNAL,
        Status.fromThrowable(error).getCode()
    );

    Integer orderCount = jdbcTemplate.queryForObject(
        "select count(*) from orders where id = ?",
        Integer.class,
        orderId
    );

    Integer outboxCount = jdbcTemplate.queryForObject(
        "select count(*) from outbox_event where aggregate_id = ?",
        Integer.class,
        orderId
    );

    assertEquals(0, orderCount);
    assertEquals(0, outboxCount);
}
```

Test trên xác nhận business row và outbox row không để lại một phần. Nếu failure xảy ra sau khi cả hai đã được insert nhưng trước commit, cả hai cũng phải rollback.

Nếu exception xảy ra sau commit, rollback không còn khả thi. Hãy tách rõ test “lỗi trước commit” với test “response bị mất sau commit”; hai trường hợp có expected state khác nhau.

## 6. Kiểm tra rollback-only và checked exception

Spring mặc định rollback với unchecked exception (RuntimeException) và Error. Checked exception không tự động rollback trong cấu hình mặc định, trừ khi khai báo rollbackFor phù hợp hoặc transaction được đánh dấu rollback-only.

Test cần bao phủ policy thực tế:

```java
@Transactional(rollbackFor = ImportRejectedException.class)
public void importRecord(ImportCommand command)
        throws ImportRejectedException {
    repository.save(toEntity(command));
    validateExternalRule(command);
}
```

Kiểm tra các tình huống:

- RuntimeException sau write: transaction rollback.
- Checked exception có rollbackFor: transaction rollback.
- Checked exception không nằm trong rollback rule: hành vi theo policy đã cấu hình, có thể commit.
- Exception bị catch và nuốt trong transactional method: transaction có thể commit nếu không được đánh dấu rollback-only.
- Transaction bị đánh dấu rollback-only: lời gọi hoàn tất có thể ném UnexpectedRollbackException khi commit.

Đừng chỉ assert exception type. Luôn xác nhận row state sau khi transaction kết thúc. Một exception được catch ở tầng adapter không tự quyết định transaction đã rollback hay chưa; transaction interceptor xử lý trước khi exception thoát khỏi proxy.

## 7. Kiểm thử gRPC status và observer lifecycle

Integration test nên gọi server qua gRPC channel để xác nhận cả application behavior lẫn transport mapping.

Với unary RPC:

- Thành công: đúng một response message, sau đó onCompleted.
- Thất bại: không phát response thành công; client nhận status phù hợp.
- Không gọi onNext/onCompleted sau onError.
- Commit failure ở proxy được adapter bắt và ánh xạ đúng.
- Status description không chứa SQL, stack trace hoặc secret.

Một số mapping thường gặp:

| Nguyên nhân | Status thường dùng |
| --- | --- |
| Request sai cấu trúc | INVALID_ARGUMENT |
| Resource không tồn tại | NOT_FOUND |
| Business precondition không thỏa | FAILED_PRECONDITION |
| Optimistic lock conflict | ABORTED |
| Database tạm thời không sẵn sàng sau retry | UNAVAILABLE |
| RPC deadline hết | DEADLINE_EXCEEDED |
| Lỗi nội bộ không dự kiến | INTERNAL |

Không dùng INTERNAL cho mọi lỗi nếu contract đã phân loại rõ hơn. Test phải xác nhận status code trên client, không chỉ kiểm tra exception nội bộ được ném trong application service.

## 8. Retry phải chạy trong transaction mới

Khi transaction đã rollback do deadlock, serialization failure hoặc optimistic lock conflict, persistence context và dữ liệu đã đọc có thể không còn phù hợp. Retry cần đọc lại trạng thái và chạy lại toàn bộ use case trong transaction mới.

Một cấu trúc rõ ràng là tách retry coordinator khỏi transactional attempt bean:

```java
@Service
@RequiredArgsConstructor
public class TransferAttemptService {
    private final AccountRepository accounts;

    @Transactional
    public TransferResult execute(TransferCommand command) {
        Account account = accounts.findById(command.accountId())
            .orElseThrow(AccountNotFoundException::new);

        account.debit(command.amount());
        return TransferResult.from(account);
    }
}
```

```java
@Service
@RequiredArgsConstructor
public class TransferRetryService {
    private final TransferAttemptService attemptService;
    private final RetryPolicy retryPolicy;

    public TransferResult execute(TransferCommand command) {
        for (int attempt = 1; ; attempt++) {
            try {
                return attemptService.execute(command);
            } catch (TransientDataAccessException ex) {
                if (!retryPolicy.mayRetry(attempt, ex)) {
                    throw ex;
                }
                retryPolicy.pauseBeforeNextAttempt(attempt);
            }
        }
    }
}
```

Hai class là hai Spring bean khác nhau. Mỗi lần coordinator gọi attemptService.execute() qua proxy, một transaction mới được mở; exception thoát khỏi method transactional thì transaction attempt đó rollback trước khi coordinator quyết định retry.

Tránh self-invocation như method retry gọi method @Transactional khác trên cùng object trong proxy mode thông thường. Lời gọi nội bộ có thể bypass transaction proxy.

## 9. Chọn lỗi nào được retry

Retry chỉ phù hợp với lỗi có khả năng phục hồi và có policy rõ:

| Lỗi | Retry tự động? | Lưu ý |
| --- | --- | --- |
| Deadlock victim | Thường có thể | Chạy lại toàn bộ transaction |
| Serialization failure | Thường có thể | Đọc lại snapshot trong transaction mới |
| Optimistic lock conflict | Tùy contract | Đọc lại và tính lại; có thể trả ABORTED cho client |
| Connection failure trước khi transaction bắt đầu | Có thể | Xác định outcome trước khi chạy command |
| Validation failure | Không | Sửa request |
| NOT_FOUND | Thường không | Resource cần được tạo hoặc ID phải sửa |
| FAILED_PRECONDITION | Không retry mù | Trạng thái nghiệp vụ cần thay đổi |
| Permission denied | Không | Quyền cần được cấp |
| Database schema/programming error | Không | Sửa lỗi vận hành/code |

Phân loại theo SQLState/vendor code và exception translation của driver/database đang dùng. Không retry mọi DataAccessException hoặc RuntimeException; lỗi constraint, syntax và mapping có thể lặp lại mãi mà không phục hồi.

Optimistic locking có hai policy hợp lệ: server tự retry toàn bộ use case nếu nghiệp vụ có thể tính lại; hoặc trả ABORTED để client đọc lại và quyết định. Không tự retry khi request chứa expected_version mà contract yêu cầu từ chối cập nhật trên version cũ.

## 10. Giới hạn retry theo attempt, backoff và deadline

Retry không được kéo dài vô hạn hoặc tạo retry storm. Policy nên có:

- Maximum attempts rõ ràng.
- Exponential backoff có jitter.
- Deadline tổng cho toàn bộ RPC/use case.
- Query/transaction timeout nhỏ hơn phần deadline còn lại.
- Chỉ retry exception đã phân loại.
- Metrics cho số attempt, success-after-retry và exhausted retry.

Ví dụ pseudocode backoff:

```text
delay = min(max_delay, base_delay × 2^(attempt - 1))
wait  = delay + random_jitter
```

Trước mỗi attempt, kiểm tra remaining deadline. Nếu không còn đủ thời gian cho attempt mới, dừng và trả status phù hợp. Không cấp lại timeout đầy đủ cho mỗi vòng retry.

Không sleep trên gRPC event-loop thread. Nếu retry đồng bộ, chạy trong worker/executor phù hợp và có giới hạn concurrency; với hệ thống bất đồng bộ, dùng scheduler/reactive retry có cancellation.

## 11. Kiểm thử retry với fault injection xác định

Dùng một probe đếm số attempt và ném lỗi transient ở các lần đầu:

```java
@Component
public class RetryFaultProbe {
    private final AtomicInteger failuresRemaining =
        new AtomicInteger(0);

    public void failNext(int count) {
        failuresRemaining.set(count);
    }

    public void beforeCommit() {
        if (failuresRemaining.getAndUpdate(
                value -> Math.max(0, value - 1)) > 0) {
            throw new TransientDataAccessResourceException(
                "Injected transient failure"
            );
        }
    }
}
```

Đặt probe sau khi đã thực hiện write trong transactional attempt. Nếu lần đầu ném exception, transaction phải rollback; lần kế tiếp gọi service qua proxy và bắt đầu transaction mới.

Test có thể cấu hình probe thất bại một lần, gọi retry coordinator rồi xác nhận:

- Attempt count bằng 2.
- Transaction đầu rollback.
- Transaction thứ hai commit.
- Chỉ có một kết quả business cuối cùng.
- Không có row phụ từ attempt thất bại.
- Transaction active ở từng attempt và transaction identity khác nhau nếu test harness có thể quan sát điều đó.

Probe phải được reset giữa các test. Không dùng static mutable state chia sẻ giữa test chạy song song.

## 12. Kiểm thử commit thành công nhưng response bị mất

Đây là kịch bản quan trọng để xác minh retry không tạo side effect trùng:

1. Server xử lý command và commit database.
2. Test fault hook làm response bị ngắt trước khi client nhận.
3. Client retry cùng idempotency key.
4. Server tìm thấy idempotency record đã commit.
5. Server replay kết quả đã lưu.
6. Database chỉ có một business record và một outbox event.

Test này khác rollback test: dữ liệu phải còn sau attempt đầu vì commit đã thành công. Lần retry không được chạy side effect lần hai.

Nếu không có idempotency, không thể chứng minh một retry sau timeout là an toàn cho command không idempotent. Dùng transport test/fault proxy hoặc hook ở adapter sau application service trả về; không giả lập bằng cách ném exception bên trong transaction nếu mục tiêu là mô phỏng lỗi sau commit.

## 13. Kiểm thử concurrency và database thật

H2 hữu ích cho test nhanh nhưng có thể khác database production về locking, isolation, deadlock, SQLState, constraint timing và timeout. Với transaction/retry quan trọng, ưu tiên Testcontainers chạy cùng engine/version gần production.

Concurrency test nên:

1. Tạo dữ liệu ban đầu đã commit.
2. Mở hai transaction độc lập.
3. Dùng CountDownLatch/CyclicBarrier để cả hai đọc cùng version hoặc tranh cùng row.
4. Cho một transaction commit trước.
5. Buộc transaction còn lại gặp conflict/deadlock.
6. Xác nhận loser rollback hoặc retry theo policy.
7. Đọc trạng thái cuối bằng connection độc lập.

Không dựa vào Thread.sleep để tạo race. Barrier/latch và fault probe tạo lịch thực thi có thể lặp lại.

Testcontainers cũng giúp xác minh native SQL, lock timeout và exception translation đúng với database/driver thực tế.

## 14. Kiểm thử outbox và external side effect

Nếu use case cập nhật domain data và tạo outbox event, rollback test phải xác nhận cả hai cùng rollback. Retry test phải xác nhận một command cuối cùng chỉ tạo một business effect và một logical event.

Các tình huống cần kiểm tra:

- Lỗi trước commit: business row và outbox row đều không tồn tại.
- Commit thành công: cả business row và outbox row tồn tại.
- Dispatcher publish rồi crash trước mark: event có thể gửi lại cùng event ID.
- Consumer nhận duplicate: inbox/unique constraint ngăn side effect lần hai.
- Retry command cùng idempotency key: không tạo outbox event mới.
- Worker retry sau lease expiry: xử lý idempotent.

Không kiểm tra “broker nhận đúng một message” như điều kiện duy nhất của outbox. Delivery thường là at-least-once; điều cần bảo đảm là consumer không áp dụng side effect trùng.

## 15. Bộ test tối thiểu cho một database RPC command

| Nhóm | Test bắt buộc | Assertion chính |
| --- | --- | --- |
| Happy path | Command thành công | Row commit, response đúng |
| Rollback | Lỗi sau write đầu tiên | Không có partial row |
| Commit failure | Constraint/flush failure | Không phát response thành công |
| Retry | Transient failure rồi thành công | Attempt mới dùng transaction mới |
| Retry exhausted | Mọi attempt đều lỗi | Không có side effect; status đúng |
| Permanent failure | Validation/permission error | Không retry |
| Lost response | Commit rồi cắt response | Retry cùng key replay |
| Duplicate concurrency | Hai request cùng key | Một logical side effect |
| Optimistic conflict | Hai transaction cùng version | Rollback loser hoặc ABORTED theo policy |
| Outbox | Domain + outbox | Cùng commit/rollback |
| Deadline | Hết ngân sách trong retry | Không bắt đầu attempt mới quá hạn |

Test suite nên tách unit test cho classifier/backoff, integration test cho transaction và gRPC, cùng fault-injection/concurrency test cho failure window. Tránh viết quá nhiều test chỉ lặp lại cùng một assertion mà không chứng minh boundary mới.

## 16. Checklist review

- Test gọi application service qua Spring proxy hoặc gRPC server thật.
- Fixture đã commit trước khi server đọc.
- Không dùng test-level transaction để giả lập transaction trên server thread.
- Failure được inject sau một write xác định.
- Rollback được xác minh bằng transaction/connection độc lập.
- Có test lỗi flush/commit, không chỉ lỗi trước khi SQL chạy.
- Checked exception và rollbackFor được kiểm tra theo policy.
- Adapter chỉ phát response sau commit.
- Retry coordinator gọi transactional bean riêng cho từng attempt.
- Không retry lỗi permanent hoặc exception chưa phân loại.
- Mỗi attempt đọc lại dữ liệu trong transaction mới.
- Backoff, max attempts và deadline tổng được kiểm tra.
- Command có side effect dùng idempotency key.
- Lost-response test chứng minh replay không duplicate.
- Outbox và consumer dedup được kiểm thử khi có external event.
- Test concurrency dùng barrier/latch, không dùng timing tùy tiện.
- Database test gần production về engine, driver và isolation.

Trong **SPRING_GRPC**, kiểm thử rollback phải chứng minh database không còn thay đổi một phần sau lỗi; kiểm thử retry phải chứng minh attempt tiếp theo chạy trong transaction mới và đọc lại trạng thái. Dùng fault injection có kiểm soát, đọc bằng connection độc lập và gọi qua gRPC server để kiểm tra status thực tế. Với command có side effect, bổ sung lost-response test cùng idempotency để bảo đảm commit thành công nhưng response bị mất không tạo hiệu lực lần hai.

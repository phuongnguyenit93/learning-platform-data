# Optimistic locking và ABORTED

## 1. Vì sao optimistic locking cần gắn với gRPC status?

Trong **SPRING_GRPC**, nhiều unary RPC có thể cùng đọc và cập nhật một bản ghi. Ví dụ hai request cùng đọc số dư tài khoản, cùng tính số dư mới rồi ghi lại. Nếu không có cơ chế phát hiện dữ liệu đã thay đổi giữa lúc đọc và ghi, request ghi sau có thể ghi đè kết quả của request trước (lost update).

**Optimistic locking** phát hiện tình huống này bằng một version number hoặc token. Mỗi lần cập nhật thành công, version tăng lên. Khi ghi, database chỉ chấp nhận update nếu version hiện tại vẫn bằng version mà transaction đã đọc. Nếu transaction khác đã cập nhật trước, câu lệnh update không còn khớp và persistence layer báo conflict.

Trong gRPC, conflict do concurrency control thường được biểu diễn bằng status **ABORTED**. Status này báo rằng thao tác bị hủy vì xung đột trong chuỗi đọc-sửa-ghi; caller có thể cần đọc lại trạng thái mới rồi thực hiện lại toàn bộ operation.

Bài tập trung vào cơ chế version check, JPA `@Version` trong Spring, thời điểm conflict xuất hiện ở flush/commit, ánh xạ exception thành gRPC `ABORTED`, phân biệt status, retry an toàn trong transaction mới, idempotency và kiểm thử concurrency.

## 2. Cách optimistic locking hoạt động

Giả sử bảng tài khoản có các cột:

| id | balance | version |
| --- | ---: | ---: |
| acct-17 | 1000 | 4 |

Hai transaction T1 và T2 cùng đọc hàng này, đều nhận `version = 4`.

- T1 tính số dư 900 và cập nhật với điều kiện `version = 4`.
- T1 thành công, ghi `balance = 900`, tăng version thành 5.
- T2 vẫn giữ version 4; khi cập nhật, điều kiện `version = 4` không còn khớp.
- Database cập nhật 0 hàng; ORM nhận ra stale state và báo optimistic locking conflict.

SQL khái quát mà ORM có thể phát ra:

```sql
UPDATE account
SET balance = ?, version = version + 1
WHERE id = ? AND version = ?
```

Nếu update count bằng 0, bản ghi đã bị thay đổi hoặc không còn tồn tại theo điều kiện cập nhật. ORM thường chuyển trường hợp stale version thành optimistic locking exception.

Điểm quan trọng là database thực hiện phép so sánh version ngay trong câu UPDATE. Cách này tránh race condition giữa một câu SELECT kiểm tra version và câu UPDATE riêng biệt.

## 3. Khai báo version bằng JPA @Version

Với Spring Data JPA, khai báo version field trên entity:

```java
@Entity
@Table(name = "account")
public class Account {
    @Id
    private String id;

    private long balance;

    @Version
    private long version;

    public void debit(long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
        if (balance < amount) {
            throw new InsufficientFundsException();
        }
        balance -= amount;
    }

    public long getBalance() {
        return balance;
    }

    public long getVersion() {
        return version;
    }
}
```

JPA provider quản lý việc đọc và tăng version khi entity được cập nhật. Ứng dụng không nên tự set version để ép update qua một conflict.

Có thể dùng kiểu số nguyên hoặc kiểu version khác được provider hỗ trợ. Tránh tái sử dụng version field cho logic nghiệp vụ riêng. Version là token concurrency của persistence layer, không phải số thứ tự đơn hàng hoặc timestamp hiển thị cho người dùng.

Nếu dùng JDBC hoặc SQL thủ công, cần tự đưa version vào điều kiện UPDATE và kiểm tra số hàng bị ảnh hưởng. `@Version` không tự bảo vệ các câu SQL bỏ qua entity lifecycle.

## 4. Ranh giới transaction và thời điểm conflict xuất hiện

Optimistic locking chỉ có ý nghĩa trong một transaction đọc trạng thái, tính thay đổi và ghi lại trạng thái đó. Use case nên nằm trong Spring application service:

```java
@Service
@RequiredArgsConstructor
public class AccountApplicationService {
    private final AccountRepository accounts;

    @Transactional
    public AccountResult debit(String accountId, long amount) {
        Account account = accounts.findById(accountId)
            .orElseThrow(AccountNotFoundException::new);

        account.debit(amount);

        return new AccountResult(
            account.getId(),
            account.getBalance(),
            account.getVersion()
        );
    }
}
```

Khi method transactional trả kết quả qua Spring proxy, transaction interceptor commit trước khi trả quyền điều khiển về gRPC adapter. Nếu version conflict chỉ được phát hiện khi flush/commit, exception có thể xuất hiện lúc proxy hoàn tất transaction, dù code trong method đã chạy tới return.

Vì vậy:

- Adapter chỉ gửi `onNext()` sau khi lời gọi application service qua proxy trả về thành công.
- Nếu commit ném optimistic lock exception, adapter nhận exception và gửi status lỗi.
- Không gửi response thành công trước commit rồi mới phát hiện conflict.
- Không bắt exception trong transactional method rồi trả kết quả bình thường nếu cần rollback.

Có thể gọi `flush()` trong transaction để phát hiện conflict sớm hơn, nhưng transaction vẫn phải commit thành công trước khi adapter báo thành công cho client. Flush không đồng nghĩa commit.

## 5. Ánh xạ optimistic locking conflict sang ABORTED

JPA/Spring có thể bộc lộ conflict qua các exception như:

- `jakarta.persistence.OptimisticLockException`.
- `org.springframework.orm.ObjectOptimisticLockingFailureException`.
- `org.springframework.dao.OptimisticLockingFailureException`.

Loại exception cụ thể phụ thuộc JPA provider, Spring version và vị trí lỗi (flush/commit). Ở lớp adapter hoặc exception mapper tập trung, nhận diện nhóm optimistic locking exception rồi ánh xạ sang `Status.ABORTED`.

Ví dụ minh họa:

```java
try {
    AccountResult result =
        accountApplicationService.debit(
            request.getAccountId(),
            request.getAmount()
        );

    DebitReply reply = DebitReply.newBuilder()
        .setAccountId(request.getAccountId())
        .setBalance(result.balance())
        .setVersion(result.version())
        .build();

    observer.onNext(reply);
    observer.onCompleted();

} catch (OptimisticLockingFailureException ex) {
    observer.onError(
        Status.ABORTED
            .withDescription("Concurrent update; reload and retry")
            .asRuntimeException()
    );
}
```

Ví dụ bắt Spring exception đã được chuẩn hóa. Nếu code bắt thêm JPA exception trực tiếp, kiểm tra hierarchy để tránh multi-catch giữa một exception và subclass của nó trong classpath đang dùng.

Không gửi tên entity, SQL, version nội bộ hoặc stack trace trong status description. Log server nên giữ exception gốc và correlation ID để điều tra.

## 6. Phân biệt ABORTED, FAILED_PRECONDITION và UNAVAILABLE

Các status gRPC biểu đạt nguyên nhân khác nhau và gợi ý hành động khác nhau:

| Status | Ý nghĩa điển hình | Hành động caller |
| --- | --- | --- |
| `ABORTED` | Xung đột concurrency trong một chuỗi thao tác, ví dụ optimistic lock | Đọc lại trạng thái và retry toàn bộ read-modify-write |
| `FAILED_PRECONDITION` | Trạng thái hệ thống/nghiệp vụ hiện tại không đáp ứng điều kiện để thực hiện | Chờ điều kiện thay đổi hoặc sửa trạng thái trước khi gọi lại |
| `UNAVAILABLE` | Service tạm thời không sẵn sàng hoặc lỗi kết nối | Có thể retry call theo policy và backoff |
| `NOT_FOUND` | Resource không tồn tại | Không retry như một conflict |
| `INVALID_ARGUMENT` | Request không hợp lệ | Sửa request trước khi gửi lại |

Ví dụ:

- Hai request cùng cập nhật entity version 4: request thua cuộc nhận `ABORTED`.
- Đơn hàng đang CANCELLED nên không thể ship: thường là `FAILED_PRECONDITION`.
- Server tạm không nhận kết nối: có thể là `UNAVAILABLE`.

Không dùng `ABORTED` cho mọi lỗi database. Việc phân loại đúng giúp client chọn đúng cách phục hồi.

## 7. Retry phải chạy lại toàn bộ use case

Sau optimistic locking conflict, dữ liệu mà transaction đã đọc là stale. Retry riêng câu UPDATE với cùng giá trị tính trước đó không giải quyết được xung đột; nó có thể ghi dựa trên trạng thái cũ và làm sai invariant.

Quy trình retry đúng ở cấp application/client:

1. Bắt `ABORTED`.
2. Bắt đầu transaction mới hoặc gọi lại RPC để server mở transaction mới.
3. Đọc lại entity và version hiện tại.
4. Tính lại quyết định nghiệp vụ từ dữ liệu mới.
5. Thực hiện update với version mới.
6. Nếu tiếp tục conflict, retry có giới hạn rồi trả lỗi cho caller.

Ví dụ, hai request cùng debit 80 từ balance 100. Request đầu commit balance 20. Request thứ hai nhận `ABORTED`; khi đọc lại, nó thấy balance 20 và phải trả lỗi nghiệp vụ insufficient funds, không được lặp lại update dựa trên balance 100.

Retry phải có:

- Số lần thử tối đa.
- Backoff có jitter để tránh nhiều request xung đột lặp lại cùng thời điểm.
- Ngân sách thời gian nằm trong RPC deadline.
- Phân loại exception; chỉ retry conflict có thể phục hồi.
- Giới hạn tải để retry không khuếch đại quá tải database.

Không retry vô hạn ở cả client lẫn server. Nếu nhiều tầng cùng retry, số lần database attempt có thể nhân lên.

## 8. Idempotency và side effects khi retry

Một request có thể commit thành công nhưng response bị mất. Client thấy timeout hoặc mất kết nối và không biết operation đã được thực hiện hay chưa. Đây là tình huống khác với optimistic locking conflict, nhưng thường xuất hiện trong cùng hệ thống retry.

Với command có side effect như tạo đơn hàng, capture payment hoặc chuyển tiền, dùng idempotency key:

- Client gửi một key ổn định cho một ý định nghiệp vụ.
- Database lưu key và kết quả cùng transaction với thay đổi nghiệp vụ.
- Unique constraint bảo vệ khi hai request cùng key đến đồng thời.
- Retry cùng key và cùng payload trả kết quả đã lưu.
- Cùng key nhưng payload khác bị từ chối.

Optimistic locking bảo vệ việc cập nhật entity từ version cũ; idempotency bảo vệ việc thực hiện lặp lại cùng một ý định. Hai cơ chế giải quyết hai vấn đề khác nhau và có thể cần dùng cùng lúc.

Nếu transaction cần phát event, ghi outbox record trong cùng transaction. Không gửi event hoặc gọi service bên ngoài trước commit rồi kỳ vọng optimistic lock rollback được side effect đó.

## 9. Optimistic locking với version do client gửi

Một số API đưa version vào request để client thể hiện rằng thao tác chỉ hợp lệ trên phiên bản mà nó đã đọc:

```proto
message UpdateProfileRequest {
  string profile_id = 1;
  string display_name = 2;
  int64 expected_version = 3;
}

message UpdateProfileReply {
  string profile_id = 1;
  int64 version = 2;
}
```

Server có thể so sánh `expected_version` với version hiện tại và trả `ABORTED` nếu không khớp. Tuy nhiên, kiểm tra bằng SELECT rồi UPDATE riêng vẫn có race condition: transaction khác có thể cập nhật sau bước kiểm tra.

Vì vậy, vẫn cần atomic version check ở database, chẳng hạn JPA `@Version`, câu UPDATE có điều kiện theo version hoặc locking phù hợp. Field `expected_version` trong API là precondition do client cung cấp; version persistence là cơ chế bảo vệ atomic tại database. Chúng có thể được ánh xạ với nhau nhưng không thay thế nhau.

Không cho client tự chọn version mới hoặc ghi đè version nội bộ. Server trả version hiện tại sau khi commit thành công để client dùng cho lần cập nhật tiếp theo.

## 10. Các trường hợp optimistic locking không tự bảo vệ

`@Version` thường bảo vệ entity update qua ORM khi provider đưa version vào câu UPDATE. Nhưng cần chú ý:

- Bulk JPQL update và native SQL có thể bỏ qua version check hoặc không tăng version nếu không được viết rõ.
- Nhiều bảng hoặc aggregate cần invariant liên hàng có thể cần lock/constraint bổ sung.
- Entity không được quản lý hoặc detached entity merge sai cách có thể tạo hành vi khó hiểu.
- Một thao tác chỉ đọc rồi ghi sang hệ thống khác không được bảo vệ bởi version của database.
- Một transaction đọc nhiều entity cần consistency rộng hơn có thể cần isolation/locking phù hợp.

Nếu dùng câu lệnh cập nhật thủ công:

```sql
UPDATE account
SET balance = :newBalance,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion
```

Hãy kiểm tra update count. Nếu bằng 0, phân biệt resource không tồn tại với version conflict nếu API cần phân biệt; có thể cần query bổ sung trong transaction mới. Không giả định native update tự ném cùng loại exception với JPA dirty checking.

## 11. Kiểm thử concurrency có kiểm soát

Một unit test gọi tuần tự hai lần không chứng minh optimistic locking hoạt động. Cần tạo hai transaction thực sự cạnh tranh trên cùng version.

Kịch bản:

1. Tạo account với balance 100 và version 1.
2. T1 đọc entity version 1.
3. T2 đọc cùng entity version 1.
4. T1 cập nhật và commit, version thành 2.
5. T2 cố commit entity đã đọc ở version 1.
6. Xác nhận T2 nhận optimistic lock exception.
7. Qua gRPC, xác nhận caller của T2 nhận `ABORTED`.
8. Retry toàn bộ use case; xác nhận application đọc balance/version mới và áp dụng rule nghiệp vụ đúng.

Nên dùng hai transaction/thread độc lập và barrier/latch để kiểm soát thời điểm đọc/ghi. Testcontainers hoặc database cùng loại với production giúp xác minh locking và exception translation thực tế; H2 có thể không tái hiện mọi khác biệt.

Các assertion quan trọng:

- Chỉ một update dựa trên cùng version cũ commit thành công.
- Version tăng đúng sau commit.
- Request thua cuộc không làm mất update của request thắng.
- Adapter không phát response thành công khi commit conflict.
- Status được ánh xạ thành `ABORTED`.
- Retry mở transaction mới và đọc lại trạng thái.
- Idempotency ngăn side effect trùng khi kết quả commit bị mất khỏi client.

## 12. Quan sát conflict và bảo vệ hệ thống

Theo dõi optimistic locking conflict theo use case/RPC:

- Số conflict và tỷ lệ conflict trên tổng update.
- Entity/aggregate type gây conflict.
- Số retry trung bình và tỷ lệ retry thành công.
- Số request hết deadline trong quá trình retry.
- Lock wait, transaction duration và database load.
- Tỷ lệ `ABORTED` theo method.

Không đưa entity ID, user ID hoặc request value tùy ý vào metric label vì cardinality có thể tăng không giới hạn. Dùng label có giới hạn như RPC method, operation type và outcome; dùng correlation ID trong log để điều tra request cụ thể.

Tỷ lệ `ABORTED` cao có thể cho thấy contention lớn, transaction quá dài, aggregate quá rộng hoặc nhiều request cập nhật cùng một row. Các biện pháp cải thiện gồm rút ngắn transaction, chia aggregate hợp lý, dùng atomic update, partition workload hoặc cân nhắc pessimistic locking cho điểm nóng. Không tăng retry count để che giấu contention vì điều đó có thể làm tải database nặng hơn.

## 13. Checklist review

- Entity cần concurrency control có version field được persistence layer quản lý.
- Mọi đường ghi dữ liệu liên quan đều thực hiện version check; bulk/native SQL đã được rà soát.
- Use case đọc-sửa-ghi nằm trong một transaction ngắn.
- Conflict tại flush/commit được truyền tới adapter hoặc exception mapper.
- Response chỉ được phát sau khi transaction commit thành công.
- Optimistic locking conflict được ánh xạ sang `ABORTED`.
- `FAILED_PRECONDITION` và `UNAVAILABLE` được dùng cho nguyên nhân khác.
- Retry đọc lại dữ liệu và chạy lại toàn bộ use case trong transaction mới.
- Retry có giới hạn, backoff/jitter và tuân thủ deadline.
- Command có side effect dùng idempotency key khi cần.
- External event được phát qua outbox sau commit.
- Có concurrency integration test với hai transaction độc lập.
- Metrics theo dõi conflict/retry mà không tạo high-cardinality labels.

Trong **SPRING_GRPC**, optimistic locking dùng version để ngăn transaction ghi đè dữ liệu đã được request khác cập nhật. Khi version không còn khớp, server nên rollback và trả `ABORTED`, để caller hiểu rằng cần đọc lại rồi thử lại toàn bộ thao tác. Đặt transaction trong application service, chỉ phát response sau commit, và kết hợp retry có giới hạn cùng idempotency để giữ đúng nghiệp vụ dưới tải đồng thời.

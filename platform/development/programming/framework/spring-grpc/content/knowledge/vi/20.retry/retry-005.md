# Retry delay và deadline còn lại

## 1. Retry delay tiêu thụ deadline như thế nào?

Trong **Spring gRPC**, retry không tạo một ngân sách thời gian mới cho mỗi lần thử. Một logical RPC có **một deadline chung**; thời gian xử lý của attempt đầu, thời gian backoff giữa các attempt và các attempt tiếp theo đều tiêu thụ ngân sách đó.

Ví dụ client gọi `GetItem` với deadline 2 giây. Attempt đầu mất 500 ms rồi trả `UNAVAILABLE`; client chờ backoff 300 ms; attempt thứ hai bắt đầu khi chỉ còn khoảng 1,2 giây. Nếu tiếp tục thất bại, lần retry sau chỉ có phần thời gian còn lại của deadline ban đầu.

Điều này có nghĩa:

- Backoff không nằm ngoài deadline.
- Retry không đặt lại deadline về giá trị ban đầu.
- Một RPC có thể dừng trước khi dùng hết `maxAttempts`.
- Nếu deadline hết trong lúc chờ backoff hoặc đang thực hiện attempt, call kết thúc; không có attempt mới trên call đó.

Trong gRPC, deadline là giới hạn thời gian cho **toàn RPC**, còn `initialBackoff`/`maxBackoff` chỉ điều chỉnh thời điểm bắt đầu attempt tiếp theo. Cần thiết kế hai nhóm cấu hình cùng nhau.

## 2. Tính ngân sách thời gian còn lại

Gọi:

- (D): thời điểm deadline tuyệt đối của logical RPC.
- (t): thời điểm hiện tại.
- (R(t)): thời gian còn lại.
- (d_k): thời gian chờ trước attempt kế tiếp.
- (a_k): thời gian attempt kế tiếp tiêu thụ.

Ngân sách còn lại tại thời điểm (t):

[
R(t) = D - t
]

Sau khi chờ backoff (d_k), ngân sách còn lại xấp xỉ:

[
R_{after_wait} = R(t) - d_k
]

Nếu attempt tiếp theo tiêu thụ (a_k), phần ngân sách còn lại sau attempt là:

[
R_{after_attempt} = R(t) - d_k - a_k
]

Đây là mô hình lập kế hoạch. Thời gian thực tế còn bao gồm jitter, scheduling, network và xử lý ở server. gRPC runtime quản lý deadline và retry; ứng dụng không nên tự giả định một attempt chắc chắn hoàn tất chỉ vì lúc bắt đầu còn thời gian.

### 2.1. Ví dụ một deadline 2 giây

Giả sử deadline tổng là 2.000 ms và các thời gian dưới đây chỉ để minh họa:

| Giai đoạn | Thời gian tiêu thụ | Ngân sách còn lại |
| --- | ---: | ---: |
| Bắt đầu logical RPC | 0 ms | 2.000 ms |
| Attempt 1 | 450 ms | 1.550 ms |
| Backoff trước attempt 2 | 200 ms | 1.350 ms |
| Attempt 2 | 500 ms | 850 ms |
| Backoff trước attempt 3 | 400 ms | 450 ms |
| Attempt 3 | tối đa 450 ms còn lại | 0 ms khi deadline hết |

Client có thể bắt đầu attempt 3 nhưng attempt đó chỉ còn khoảng 450 ms trước khi toàn call hết hạn. Nếu server cần nhiều thời gian hơn, client vẫn nhận kết quả deadline thay vì được cấp thêm 2 giây.

Backoff thực tế có thể khác giá trị cơ sở do jitter hoặc server pushback. Vì vậy, hãy dùng timeline để ước lượng và kiểm thử trong biên thời gian, không dùng nó như lịch chạy chính xác.

## 3. Backoff và deadline là hai giới hạn khác nhau

Retry policy thường có các trường:

| Trường | Vai trò | Có đặt lại deadline không? |
| --- | --- | --- |
| `initialBackoff` | Khoảng chờ cơ sở trước retry đầu | Không |
| `backoffMultiplier` | Tăng khoảng chờ sau mỗi lỗi đủ điều kiện | Không |
| `maxBackoff` | Giới hạn khoảng chờ cơ sở | Không |
| `maxAttempts` | Tổng attempt tối đa, gồm lần đầu | Không |
| Deadline của call | Giới hạn thời gian toàn logical RPC | Là giới hạn thời gian chung |

Ví dụ policy cho method unary `catalog.v1.CatalogService/GetItem`:

```json
{
  "methodConfig": [
    {
      "name": [
        {
          "service": "catalog.v1.CatalogService",
          "method": "GetItem"
        }
      ],
      "retryPolicy": {
        "maxAttempts": 4,
        "initialBackoff": "0.2s",
        "maxBackoff": "1s",
        "backoffMultiplier": 2,
        "retryableStatusCodes": ["UNAVAILABLE"]
      }
    }
  ]
}
```

Policy cho phép tối đa bốn attempt nếu mỗi lỗi đủ điều kiện và call chưa commit. Nhưng nếu deadline hết sau attempt thứ hai, client không thể dùng attempt thứ ba và thứ tư chỉ vì policy còn cho phép.

### 3.1. Gắn deadline vào client call

Trong gRPC Java, deadline được đặt trên stub:

```java
import io.grpc.Deadline;
import java.util.concurrent.TimeUnit;

Deadline deadline = Deadline.after(2, TimeUnit.SECONDS);

CatalogGrpc.CatalogBlockingStub callStub =
        catalogStub.withDeadline(deadline);

long remainingBeforeCall =
        deadline.timeRemaining(TimeUnit.MILLISECONDS);

GetItemResponse response = callStub.getItem(
        GetItemRequest.newBuilder()
                .setItemId("item-42")
                .build());
```

`withDeadline(deadline)` gắn một deadline tuyệt đối vào logical RPC. Khi gRPC thực hiện retry, các attempt vẫn nằm trong ngân sách thời gian đó. Trong ứng dụng Spring gRPC, stub thường được inject hoặc tạo từ channel do cấu hình client quản lý; đặt deadline trên stub cho từng lời gọi theo yêu cầu nghiệp vụ.

Không tạo một deadline mới bên trong mỗi lần retry ở tầng ứng dụng nếu mục tiêu là giới hạn toàn bộ thao tác. Làm vậy sẽ vô tình cấp lại ngân sách và khiến tổng thời gian vượt SLA của caller.

## 4. Backoff có thể khiến attempt tiếp theo không còn hữu ích

Giả sử deadline còn 250 ms nhưng backoff cơ sở cho lần retry tiếp theo là 500 ms. Nếu client chờ đủ backoff, deadline sẽ hết trước khi attempt bắt đầu. Runtime sẽ kết thúc call khi deadline hết thay vì tiếp tục vô hạn.

Ngay cả khi deadline còn dài hơn backoff, vẫn cần tính thời gian tối thiểu để một attempt có cơ hội hoàn tất. Ví dụ:

- Deadline còn 700 ms.
- Backoff dự kiến là 200 ms.
- Chỉ còn khoảng 500 ms cho attempt kế tiếp và phần overhead.

Nếu method thường cần 1 giây để xử lý, attempt này khó tạo giá trị. Tuy nhiên, gRPC retry policy không cung cấp một bảo đảm chung rằng runtime sẽ dự đoán chính xác thời gian xử lý cần thiết và chỉ bắt đầu attempt khi đủ ngân sách. Deadline là cơ chế dừng cứng; việc quyết định có nên thử lại khi ngân sách còn ít cần dựa vào SLA và logic ứng dụng.

Với một retry loop do ứng dụng tự quản lý, có thể kiểm tra ngân sách trước khi schedule:

```java
long remainingMs = deadline.timeRemaining(TimeUnit.MILLISECONDS);
long delayMs = computedBackoff.toMillis();
long minimumUsefulAttemptMs = 300;

if (remainingMs <= delayMs + minimumUsefulAttemptMs) {
    completeAsTimedOutOrUnavailable();
    return;
}

scheduler.schedule(this::startNextAttempt,
        delayMs, TimeUnit.MILLISECONDS);
```

Đây là logic **application-level retry**, không phải phần mở rộng tự động của gRPC service config. `minimumUsefulAttemptMs` phải xuất phát từ SLA/đo đạc của method; nó không phải giá trị gRPC có thể tự suy ra. Khi tự quản lý retry, vẫn phải giới hạn attempt, hủy timer khi caller cancel và bảo đảm idempotency.

## 5. Deadline được truyền tới server như thế nào?

gRPC truyền thông tin deadline qua giao thức dưới dạng timeout còn lại. Khi một logical RPC được retry, server của attempt sau nhận phần thời gian còn lại, không được coi đó là một deadline mới đầy đủ như lúc client bắt đầu.

Điều này quan trọng với chuỗi service:

```text
Client (deadline tổng 2 giây)
   |
   |  attempt 1 mất 500 ms, backoff 200 ms
   v
Service A (còn khoảng 1,3 giây khi attempt 2 bắt đầu)
   |
   |  gọi Service B
   v
Service B (nhận ngân sách còn lại của call, không phải 2 giây mới)
```

Nếu Service A gọi Service B mà tạo một deadline mới dài hơn ngân sách còn lại, tổng thời gian có thể vượt giới hạn mà client đặt. Hãy truyền tiếp deadline/cancellation context phù hợp khi tạo downstream call, và không tùy tiện nới deadline.

Trong hệ thống Spring gRPC, metadata/interceptor có thể mang trace ID, tenant hoặc thông tin xác thực. Deadline là cơ chế thời gian của gRPC; không cần tự truyền một header tùy biến thay thế deadline chuẩn.

## 6. Server pushback có thể thay đổi thời gian chờ

Khi server quá tải, server có thể dùng retry pushback để hướng dẫn client chờ lâu hơn hoặc dừng retry. Cơ chế gRPC dùng metadata đặc biệt `grpc-retry-pushback-ms`:

- Giá trị dương biểu thị thời gian chờ trước lần retry tiếp theo.
- Giá trị âm yêu cầu không retry call đó.
- Pushback không cấp thêm deadline; thời gian chờ được chỉ định vẫn tiêu thụ ngân sách của logical RPC.

Ví dụ deadline còn 600 ms nhưng server yêu cầu pushback 1.000 ms. Client không thể chờ hết 1 giây rồi thực hiện attempt trong cùng deadline; call sẽ hết hạn trước đó.

Pushback và backoff không nên được cộng hoặc ghi đè theo suy đoán của ứng dụng. Hãy để gRPC runtime xử lý theo semantics của retry policy; nếu tự triển khai retry, định nghĩa rõ thứ tự ưu tiên giữa backoff, pushback và deadline.

## 7. Chọn deadline và retry delay theo SLA

Thiết kế policy theo thời gian mà người gọi thực sự chấp nhận, không chọn `maxAttempts` trước rồi mới cố nhét vào deadline.

Một quy trình thực tế:

1. Đo latency bình thường và latency khi dependency phục hồi.
2. Xác định SLA tổng của thao tác, gồm thời gian network, xử lý và retry.
3. Chọn deadline cho toàn logical RPC.
4. Chọn `initialBackoff`, `maxBackoff`, multiplier và `maxAttempts` sao cho còn cơ hội cho attempt hữu ích.
5. Chỉ retry status tạm thời và tôn trọng pushback/throttling.
6. Với thao tác ghi, dùng idempotency key vì deadline hết không chứng minh server chưa thực hiện.

Ví dụ method đọc có SLA 2 giây có thể dùng deadline 2 giây và retry tối đa ba attempt với backoff nhỏ. Một thao tác ghi quan trọng có thể cần deadline dài hơn nhưng ít attempt hơn, kèm idempotency và truy vấn trạng thái để xử lý kết quả không xác định.

## 8. Retry delay và streaming RPC

Với unary RPC, mỗi attempt là một lần thực hiện request/response có thể retry nếu call chưa commit. Với client streaming và bidirectional streaming, retry tự động bị giới hạn bởi commitment và retry buffer:

- Khi client nhận response headers hoặc request vượt giới hạn retry buffer, call có thể đã commit.
- Sau khi commit, gRPC không tự replay toàn bộ stream khi một lỗi mới xảy ra.
- Deadline vẫn áp dụng cho toàn bộ stream; thời gian sống của stream và các khoảng backoff đều tiêu thụ ngân sách.
- Không thể dùng `maxAttempts` để khôi phục stream đang hoạt động từ message cuối.

Nếu stream đã commit bị ngắt, ứng dụng cần mở RPC mới và resume bằng `request_id`, sequence/cursor và idempotency. Deadline của RPC mới là ngân sách mới do caller quyết định; không nên tự động đặt lại vô hạn nếu SLA nghiệp vụ đã hết.

## 9. Kiểm thử deadline còn lại

Test nên xác minh thời gian tổng và số attempt, không chỉ status cuối:

| Kịch bản | Assertion |
| --- | --- |
| Attempt đầu thất bại nhanh, còn nhiều deadline | Client có thể chờ backoff và thử lại |
| Backoff gần bằng thời gian còn lại | Call kết thúc theo deadline; không chờ vô hạn |
| Deadline hết trong lúc attempt chạy | Client nhận `DEADLINE_EXCEEDED` hoặc trạng thái kết thúc tương ứng |
| Nhiều attempt trong một logical RPC | Tổng thời gian không vượt deadline đã đặt, ngoài sai số đo nhỏ |
| Server pushback dài hơn thời gian còn lại | Không có attempt hữu ích sau khi deadline hết |
| Downstream call | Nhận ngân sách deadline còn lại, không được cấp lại toàn bộ SLA |
| Caller cancel trong backoff | Timer retry bị hủy và không phát attempt tiếp |
| Retry thao tác ghi sau timeout | Idempotency ngăn tác dụng phụ bị thực hiện hai lần |
| Bidi stream đã commit bị ngắt | Reconnect/resume theo protocol, không giả định retry delay khôi phục stream cũ |

Để test ổn định, dùng server test có thể trả status theo attempt và ghi timestamp nhận request. Kiểm tra thời gian trong một khoảng cho phép vì backoff có jitter và scheduler không chạy chính xác từng mili giây. Với retry tự viết, tiêm clock/scheduler giả để kiểm thử trường hợp deadline còn ít mà không phải đợi thời gian thật.

Metric nên theo dõi gồm thời gian deadline còn lại khi bắt đầu mỗi attempt, backoff thực tế, số attempt, số call kết thúc do deadline, tỷ lệ retry thành công và tỷ lệ attempt bị dừng trước khi bắt đầu do ngân sách không còn đủ.

## 10. Sai lầm thường gặp

1. **Cấp deadline mới cho mỗi attempt.** Điều này biến một giới hạn tổng thành nhiều giới hạn riêng và có thể vượt SLA.
2. **Coi backoff nằm ngoài deadline.** Thời gian chờ retry vẫn tiêu thụ ngân sách logical RPC.
3. **Kỳ vọng dùng hết `maxAttempts`.** Deadline có thể kết thúc call trước khi hết attempt budget.
4. **Cho rằng còn đủ thời gian cho backoff là đủ cho attempt.** Attempt vẫn cần thời gian network và xử lý.
5. **Bỏ qua pushback.** Server có thể yêu cầu chờ lâu hơn hoặc dừng retry; deadline vẫn tiếp tục trôi.
6. **Tạo downstream deadline mới dài hơn deadline còn lại.** Chuỗi service có thể vượt SLA của caller.
7. **Retry sau `DEADLINE_EXCEEDED` mà không idempotency.** Server có thể đã hoàn tất tác dụng phụ trước khi client hết thời gian.
8. **Dùng retry tự động để resume bidi stream.** Stream đã commit cần protocol reconnect/resume ở tầng ứng dụng.

## 11. Bài tập vận dụng

Với `catalog.v1.CatalogService/GetItem`:

1. Đặt deadline tổng 2 giây, `maxAttempts=4`, `initialBackoff=200ms`, `maxBackoff=1s`.
2. Cho server trả `UNAVAILABLE` sau các khoảng xử lý khác nhau; ghi lại ngân sách còn lại trước mỗi attempt.
3. Tạo trường hợp backoff dự kiến dài hơn deadline còn lại; xác minh call dừng đúng hạn.
4. Mô phỏng pushback dài hơn deadline còn lại và kiểm tra không có attempt sau khi call hết hạn.
5. Tạo downstream call từ server, truyền tiếp deadline còn lại và so sánh với trường hợp vô tình cấp deadline mới.
6. Với thao tác ghi, mô phỏng server hoàn tất nhưng response đến sau deadline; xác minh retry dùng cùng idempotency key.

**Tiêu chí hoàn thành:** người học tính được deadline còn lại sau mỗi attempt/backoff, hiểu vì sao retry delay tiêu thụ ngân sách tổng, cấu hình được policy phù hợp SLA và tránh kéo dài call hoặc tạo tác dụng phụ trùng.

### Tài liệu tham khảo

- [gRPC Deadlines](https://grpc.io/docs/guides/deadlines/): deadline và truyền ngân sách thời gian giữa các service.
- [gRPC Retry](https://grpc.io/docs/guides/retry/): retry policy, backoff, commitment và pushback.
- [gRPC Service Config](https://grpc.io/docs/guides/service-config/): cấu hình retry theo service/method.
- [gRPC Java Deadline API](https://grpc.github.io/grpc-java/javadoc/io/grpc/Deadline.html): tạo deadline và truy vấn thời gian còn lại.
- [Spring gRPC Reference](https://docs.spring.io/spring-grpc/reference/): tích hợp gRPC client/server trong Spring.

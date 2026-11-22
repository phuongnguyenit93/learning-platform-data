# Maximum attempts

## 1. Maximum attempts giới hạn điều gì?

Trong gRPC, một lần gọi logic có thể được thực hiện qua nhiều **attempt** nếu client retry sau lỗi đủ điều kiện. Trường `maxAttempts` trong retry policy đặt giới hạn tổng số attempt cho một RPC, **bao gồm attempt đầu tiên**.

Ví dụ `maxAttempts = 4` có nghĩa:

- Attempt 1 là lần gọi ban đầu.
- Nếu attempt 1 thất bại với status được phép retry và call vẫn đủ điều kiện, client có thể thực hiện attempt 2.
- Tương tự, tối đa có attempt 3 và attempt 4.
- Tổng số lần retry bổ sung tối đa là **3**, không phải 4.

Giới hạn này giúp kiểm soát lượng tải phát sinh khi dependency lỗi. Nó không đảm bảo client sẽ thực hiện đủ số attempt: status không retryable, deadline hết, call đã commit hoặc server yêu cầu dừng retry đều có thể làm quá trình kết thúc sớm.

Trong Spring gRPC, `maxAttempts` thuộc **retry policy phía client**, thường được gắn vào một service/method bằng gRPC service config. Server không đặt trường này để buộc client thử lại.

## 2. Phân biệt attempts và retries

Hai khái niệm thường bị nhầm:

| Khái niệm | Ý nghĩa |
| --- | --- |
| Attempt | Một lần thực thi RPC ở tầng transport |
| Initial attempt | Attempt đầu tiên do client khởi tạo |
| Retry | Attempt bổ sung sau khi một attempt trước thất bại đủ điều kiện |
| `maxAttempts` | Tổng số attempt tối đa, bao gồm lần đầu |
| Số retry tối đa | `maxAttempts - 1` |

Với `maxAttempts = N), số attempt thực tế (A) thỏa:

[
1 \le A \le N
]

và số retry thực tế là:

[
R = A - 1 \le N - 1
]

Ví dụ:

| `maxAttempts` | Attempt đầu | Retry bổ sung tối đa |
| ---: | ---: | ---: |
| 2 | 1 | 1 |
| 3 | 1 | 2 |
| 4 | 1 | 3 |
| 5 | 1 | 4 |

Không nên ghi log “retry 1” cho lần gọi ban đầu. Hãy phân biệt `attempt=1` với `retry_number=0`, hoặc dùng một trường attempt nhất quán từ 1 đến N.

## 3. Cấu hình maxAttempts theo method

Ví dụ policy cho RPC unary `catalog.v1.CatalogService/GetItem`:

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
        "maxBackoff": "2s",
        "backoffMultiplier": 2,
        "retryableStatusCodes": ["UNAVAILABLE"]
      }
    }
  ]
}
```

Policy này cho phép tối đa bốn attempt khi method kết thúc bằng `UNAVAILABLE` và vẫn thỏa các điều kiện retry khác. `INVALID_ARGUMENT` không kích hoạt retry theo danh sách trên. Backoff được áp dụng giữa các attempt; thời gian chờ không làm tăng `maxAttempts`.

Tên service và method phải khớp tên đầy đủ trong Protobuf. Một policy riêng cho `GetItem` không tự áp dụng cho `CreateItem` hoặc method khác.

### 3.1. Gắn policy vào gRPC Java channel

Có thể tạo service config dưới dạng `Map` rồi gắn vào channel:

```java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import java.util.List;
import java.util.Map;

Map<String, Object> retryPolicy = Map.of(
        "maxAttempts", 4.0,
        "initialBackoff", "0.2s",
        "maxBackoff", "2s",
        "backoffMultiplier", 2.0,
        "retryableStatusCodes", List.of("UNAVAILABLE"));

Map<String, Object> methodConfig = Map.of(
        "name", List.of(Map.of(
                "service", "catalog.v1.CatalogService",
                "method", "GetItem")),
        "retryPolicy", retryPolicy);

Map<String, Object> serviceConfig =
        Map.of("methodConfig", List.of(methodConfig));

ManagedChannel channel = ManagedChannelBuilder
        .forAddress("catalog.internal", 9090)
        .defaultServiceConfig(serviceConfig)
        .build();
```

Trong ứng dụng Spring gRPC, cấu hình retry phải được áp dụng lên client channel do cấu hình hoặc factory của dự án tạo ra. Cách tích hợp cụ thể tùy phiên bản Spring gRPC; nguyên tắc không đổi là policy thuộc client và phải khớp method cần retry.

## 4. Vì sao không nên đặt maxAttempts quá cao?

Mỗi attempt có thể tạo thêm một request tới server. Nếu nhiều client cùng gặp lỗi, số lần thử lớn làm tăng tải đúng lúc hệ thống đang yếu.

Ví dụ có 2.000 client cùng gọi một method:

| Cấu hình | Request tối đa nếu mọi client dùng hết attempt |
| --- | ---: |
| `maxAttempts = 1` | 2.000 |
| `maxAttempts = 2` | 4.000 |
| `maxAttempts = 3` | 6.000 |
| `maxAttempts = 5` | 10.000 |

Đây là phép tính biên trên đơn giản, giả định mọi attempt đều tới server. Một số attempt có thể thất bại trước khi tới server, và không phải call nào cũng dùng hết giới hạn. Tuy vậy, ví dụ cho thấy tăng `maxAttempts` có thể khuếch đại tải đáng kể.

Chọn giới hạn theo:

- Mức độ tạm thời của lỗi và xác suất phục hồi trong khoảng thời gian ngắn.
- Chi phí xử lý mỗi attempt ở server và dependency.
- Deadline mà caller chấp nhận.
- Tính idempotent của thao tác.
- Retry policy, backoff, jitter, throttling và pushback đang áp dụng.

Một giá trị nhỏ, có backoff và deadline rõ ràng thường dễ vận hành hơn một giới hạn lớn nhằm che giấu lỗi kéo dài.

## 5. maxAttempts và deadline phải được thiết kế cùng nhau

`maxAttempts` chỉ giới hạn **số lần**, còn deadline giới hạn **thời gian tổng**. Một policy có thể cho phép bốn attempt nhưng deadline chỉ còn đủ cho một hoặc hai lần thử.

Ví dụ:

- Deadline tổng: 1,5 giây.
- Attempt đầu tiêu thụ 700 ms.
- Backoff trước lần kế tiếp: 500 ms.
- Chỉ còn khoảng 300 ms cho attempt tiếp theo.

Nếu lần thử mới không còn đủ thời gian để tạo giá trị, lời gọi có thể kết thúc bằng `DEADLINE_EXCEEDED` trước khi dùng hết `maxAttempts`.

Vì vậy:

1. Chọn deadline theo yêu cầu nghiệp vụ.
2. Chọn `maxAttempts` và backoff sao cho có cơ hội thực hiện attempt hữu ích trong deadline đó.
3. Không coi `maxAttempts` là cam kết số lần gọi thực tế.
4. Khi deadline hết, không tự khởi động một vòng retry mới ngoài deadline của caller.

## 6. Retry chỉ xảy ra khi các điều kiện khác cũng thỏa

Đạt giới hạn attempt chưa phải điều kiện duy nhất để retry. Một attempt trước phải kết thúc bằng status được policy cho phép, call chưa commit và còn ngân sách thời gian.

| Điều kiện | Ảnh hưởng đến maxAttempts |
| --- | --- |
| Status nằm trong `retryableStatusCodes` | Có thể dùng attempt tiếp theo |
| Status không nằm trong policy | Dừng, dù còn attempt |
| Call đã commit | Không tự replay call đó |
| Deadline hết | Dừng, dù chưa đạt giới hạn |
| Server pushback yêu cầu dừng | Dừng retry theo tín hiệu |
| Retry throttling hạn chế retry | Có thể giảm hoặc ngăn attempt tiếp theo |
| Đã dùng hết `maxAttempts` | Trả lỗi cuối cho caller |

**Commitment** là ranh giới quan trọng: khi gRPC nhận response headers hoặc request vượt giới hạn retry buffer, call có thể được xem là đã commit. Sau đó runtime không thể tự replay toàn bộ RPC như khi call còn đủ dữ liệu và chưa commit.

Với thao tác ghi, việc call chưa commit cũng không thay thế idempotency. Server có thể đã thực hiện tác dụng phụ trước khi client nhận được response. Hãy dùng idempotency key ổn định để nhiều attempt của cùng thao tác không tạo kết quả trùng.

## 7. maxAttempts với streaming RPC

Không nên hiểu `maxAttempts` là số lần một bidi stream được nối lại từ message cuối cùng. Retry tự động của gRPC bị giới hạn bởi commitment và retry buffer:

- Trước khi call commit, runtime có thể replay request đã được buffer khi gặp lỗi phù hợp.
- Sau khi response headers đã được nhận hoặc dữ liệu vượt giới hạn retry buffer, call đã commit và không còn tự replay.
- Streaming RPC có thể gửi/nhận nhiều message và thường commit trong quá trình hoạt động; không thể dựa vào `maxAttempts` để khôi phục một phiên stream đã chạy lâu.

Nếu stream bị ngắt sau commit, ứng dụng cần mở RPC mới và thực hiện resume:

1. Giữ `request_id` ổn định cho từng command.
2. Lưu cursor hoặc sequence đã được xác nhận.
3. Gửi lại command chưa được xác nhận theo quy tắc idempotency.
4. Server deduplicate request đã xử lý và trả lại trạng thái/kết quả phù hợp.
5. Client bỏ qua event trùng và phát hiện khoảng trống sequence.

Retry một command trong bidi stream là logic tầng ứng dụng, không phải tăng `maxAttempts` của toàn RPC. Một response message `TaskRejected` cũng không phải gRPC status và không tự kích hoạt retry policy.

## 8. Phân biệt giới hạn attempt với các giới hạn khác

| Giới hạn | Phạm vi | Mục tiêu |
| --- | --- | --- |
| `maxAttempts` | Một logical RPC | Giới hạn tổng số lần thực thi RPC |
| Deadline | Một logical RPC | Giới hạn tổng thời gian |
| Backoff/`maxBackoff` | Giữa các attempt | Điều tiết thời điểm retry |
| Semaphore/concurrency limit | Một stream hoặc toàn service | Giới hạn công việc chạy đồng thời |
| Rate limit | Một client, tenant hoặc service | Giới hạn tốc độ request theo thời gian |
| Idempotency | Một thao tác logic | Ngăn tác dụng phụ trùng khi retry |

Ví dụ `maxAttempts=3` không có nghĩa server chỉ xử lý tối đa ba request đồng thời. Một nghìn logical RPC có thể cùng tồn tại, mỗi RPC có ngân sách ba attempt. Cần giới hạn concurrency và rate ở tầng phù hợp để bảo vệ server.

## 9. Kiểm thử maxAttempts

Một test đáng tin cậy cần đếm số attempt server thực sự nhận và kiểm tra các trường hợp dừng sớm. Dùng server test trả status theo thứ tự có kiểm soát:

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| `maxAttempts=4`, ba lần đầu `UNAVAILABLE`, lần thứ tư thành công | Có tối đa bốn attempt; client nhận kết quả |
| `maxAttempts=4`, mọi lần đều `UNAVAILABLE` | Không vượt bốn attempt; trả status cuối |
| Lần đầu trả `INVALID_ARGUMENT` | Chỉ một attempt nếu status không retryable |
| Deadline hết trước lần retry tiếp theo | Dừng sớm, không vượt deadline |
| Server trả pushback dừng retry | Không dùng hết attempt budget một cách mù quáng |
| Call đã commit rồi mới lỗi | Không kỳ vọng tự replay call đã commit |
| Ghi dữ liệu với cùng idempotency key | Nhiều attempt không tạo tác dụng phụ trùng |
| Streaming call ngắt sau commit | Reconnect/resume theo contract ứng dụng |

Khi kiểm thử, phân biệt **số lần client bắt đầu attempt** với **số lần server nhận request**. Một attempt có thể thất bại trước khi tới handler. Dùng metrics hoặc log phía client để đếm attempt, đồng thời ghi nhận số request server thực sự nhận để hiểu đường đi của lỗi.

## 10. Sai lầm thường gặp

1. **Coi `maxAttempts=4` là bốn lần retry.** Thực tế là bốn attempt tổng cộng, gồm lần đầu.
2. **Kỳ vọng luôn dùng hết attempt budget.** Status, commitment, deadline, pushback và throttling có thể làm dừng sớm.
3. **Đặt giới hạn quá cao để tăng độ tin cậy.** Điều này có thể khuếch đại tải và kéo dài thời gian thất bại.
4. **Bỏ qua deadline.** Một attempt được phép về mặt số lượng nhưng không còn đủ thời gian thực hiện.
5. **Dùng maxAttempts để kiểm soát concurrency.** Đây là giới hạn theo logical RPC, không phải giới hạn tổng task của server.
6. **Retry thao tác ghi không idempotent.** Nhiều attempt có thể tạo tác dụng phụ trùng.
7. **Dùng maxAttempts để resume bidi stream.** Streaming call đã commit cần protocol reconnect/resume ở tầng ứng dụng.

## 11. Bài tập vận dụng

Với `catalog.v1.CatalogService/GetItem`:

1. Cấu hình `maxAttempts=3`, `initialBackoff=100ms`, `maxBackoff=1s` và chỉ retry `UNAVAILABLE`.
2. Viết server test trả `UNAVAILABLE` hai lần rồi thành công; xác minh lần thành công là attempt thứ ba.
3. Viết test `INVALID_ARGUMENT` không retry và test deadline hết trước attempt tiếp theo.
4. Tăng số client đồng thời, đo tổng request do retry tạo ra; đánh giá tác động khi tăng `maxAttempts`.
5. Với một thao tác ghi, dùng idempotency key và chứng minh nhiều attempt không tạo tác dụng phụ trùng.
6. Với bidi stream đã commit, triển khai reconnect/resume và giải thích vì sao `maxAttempts` không khôi phục stream cũ.

**Tiêu chí hoàn thành:** người học tính đúng số retry tối đa từ `maxAttempts`, cấu hình giới hạn theo method, giải thích được các điều kiện dừng sớm, phối hợp deadline/idempotency và không nhầm retry attempt với concurrency hoặc stream resume.

### Tài liệu tham khảo

- [gRPC Retry](https://grpc.io/docs/guides/retry/): retry policy, attempt, commitment và giới hạn retry.
- [gRPC Service Config](https://grpc.io/docs/guides/service-config/): cấu hình retry theo service và method.
- [gRPC Status Codes](https://grpc.io/docs/guides/status-codes/): ý nghĩa status kết thúc RPC.
- [gRPC Java ManagedChannelBuilder](https://grpc.github.io/grpc-java/javadoc/io/grpc/ManagedChannelBuilder.html): gắn service config vào client channel.
- [Spring gRPC Reference](https://docs.spring.io/spring-grpc/reference/): tích hợp gRPC client/server trong Spring.

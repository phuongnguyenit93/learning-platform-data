# Backoff và jitter

## 1. Vì sao retry cần backoff và jitter?

Trong dịch vụ **SPRING_GRPC**, khi một dependency tạm thời không khả dụng, nhiều client có thể cùng nhận `UNAVAILABLE` và thử lại. Nếu tất cả gửi lại ngay lập tức, server đang phục hồi sẽ nhận thêm một đợt tải đột biến. Hiện tượng này có thể tạo vòng lặp: quá tải gây lỗi, lỗi kích hoạt retry, retry làm quá tải nặng hơn.

**Backoff** làm tăng khoảng chờ giữa các lần thử. **Jitter** thêm yếu tố ngẫu nhiên vào thời điểm retry để các client không đồng bộ và dồn request vào cùng một thời điểm.

Hai cơ chế giải quyết hai vấn đề liên quan nhưng khác nhau:

- Backoff giảm tần suất retry của **một client** khi lỗi tiếp tục xảy ra.
- Jitter phân tán retry của **nhiều client** cùng gặp sự cố.

Trong gRPC, retry policy của client có thể cấu hình exponential backoff bằng `initialBackoff`, `maxBackoff` và `backoffMultiplier`. Jitter là một phần của cơ chế retry runtime; service config không có trường `jitter` để chọn phân phối ngẫu nhiên cụ thể. Khi tự viết retry ở tầng ứng dụng, đội phát triển phải tự chọn thuật toán jitter và kiểm soát số lần retry.

## 2. Exponential backoff

Exponential backoff tăng thời gian chờ sau mỗi lần thất bại. Gọi:

- (B_0): `initialBackoff`, thời gian chờ trước retry đầu tiên.
- (M): `backoffMultiplier`, hệ số tăng.
- (B_{max}): `maxBackoff`, giới hạn trên.
- (k): số thứ tự lần retry, bắt đầu từ 0.

Khoảng chờ cơ sở của lần retry thứ (k):

[
B_k = \min(B_0 \times M^k,\ B_{max})
]

Ví dụ `initialBackoff = 200 ms`, `backoffMultiplier = 2`, `maxBackoff = 2 s`:

| Lần retry | Khoảng chờ cơ sở |
| --- | ---: |
| 1 | 200 ms |
| 2 | 400 ms |
| 3 | 800 ms |
| 4 | 1.600 ms |
| 5 trở đi | 2.000 ms |

Giới hạn `maxBackoff` ngăn thời gian chờ tăng vô hạn. Nó không có nghĩa client chắc chắn sẽ thực hiện đủ các lần retry: `maxAttempts`, deadline, retryable status, commitment và pushback vẫn có thể làm dừng retry sớm hơn.

## 3. Jitter phân tán thời điểm retry

Nếu một nghìn client cùng thất bại lúc 10:00:00 và đều chờ đúng 1 giây, gần như tất cả sẽ retry lúc 10:00:01. Backoff có thể giảm tần suất nhưng không tự loại bỏ đợt request đồng bộ. Jitter ngẫu nhiên hóa khoảng chờ để phân tán các lần retry.

Có nhiều cách tạo jitter. Các công thức dưới đây mô tả những lựa chọn phổ biến khi **tự triển khai retry ở tầng ứng dụng**; chúng không phải tên cấu hình trong gRPC service config.

### 3.1. Full jitter

Tạo thời gian chờ ngẫu nhiên trong khoảng từ 0 đến giới hạn backoff:

[
D_k \sim U(0, B_k)
]

Ưu điểm là phân tán mạnh và giới hạn được thời gian chờ tối đa. Nhược điểm là một số lần thử có thể xảy ra khá sớm; vì vậy cần giới hạn attempt và đánh giá tải tổng thể.

### 3.2. Equal jitter

Giữ ít nhất một nửa backoff cơ sở rồi ngẫu nhiên hóa nửa còn lại:

[
D_k = \frac{B_k}{2} + U(0, \frac{B_k}{2})
]

Cách này tránh những lần retry quá sát nhau như có thể xảy ra với full jitter, đổi lại thời gian chờ tối thiểu cao hơn.

### 3.3. Decorrelated jitter

Một biến thể dùng khoảng chờ trước đó để tạo khoảng mới:

[
D_k = \min(B_{max}, U(B_0, 3D_{k-1}))
]

Biến thể này có thể tạo chuỗi thời gian chờ ít đồng bộ hơn giữa các client. Cần giới hạn cận dưới/cận trên và kiểm thử phân phối thực tế trước khi dùng.

Không có một thuật toán jitter tối ưu cho mọi tải. Với gRPC built-in retry, hãy dùng policy được runtime hỗ trợ và không phụ thuộc vào một phân phối jitter nội bộ cụ thể. Nếu tự triển khai retry, chọn một thuật toán đã được đánh giá, tiêm nguồn random để test và tránh xếp chồng jitter ở nhiều tầng.

## 4. Cấu hình backoff cho gRPC client

Ví dụ service config cho method unary `catalog.v1.CatalogService/GetItem`:

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

Ý nghĩa:

- `maxAttempts: 4` là tối đa bốn attempt **tính cả lần đầu**, không phải bốn lần retry cộng thêm.
- `initialBackoff` đặt khoảng chờ cơ sở ban đầu.
- `backoffMultiplier` tăng khoảng chờ sau mỗi lần lỗi đủ điều kiện.
- `maxBackoff` giới hạn khoảng chờ cơ sở.
- `retryableStatusCodes` chỉ cho phép retry khi status kết thúc nằm trong danh sách.

gRPC runtime áp dụng jitter cho retry theo cơ chế của nó. Không thêm một vòng lặp retry ngoài chỉ để tạo jitter nếu channel đã có configured retry; hai tầng có thể nhân số attempt và làm khó dự đoán tải.

### 4.1. Gắn policy vào channel Java

Ví dụ tạo service config bằng `Map`:

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

Trong ứng dụng Spring gRPC, policy phải được gắn vào client channel do cấu hình/factory của ứng dụng quản lý. Cách inject channel phụ thuộc phiên bản Spring gRPC và cách dự án tạo stub; các giá trị backoff vẫn thuộc service config phía client. Xác nhận tên service/method khớp với tên đầy đủ trong Protobuf.

## 5. Backoff phải nằm trong deadline

Deadline là ngân sách thời gian cho toàn RPC, không được cấp lại từ đầu ở mỗi attempt. Một lần retry chỉ hữu ích nếu còn thời gian cho khoảng chờ và cho attempt tiếp theo.

Ví dụ:

- Deadline còn 700 ms.
- Backoff dự kiến cho lần kế tiếp là 800 ms.
- Client không nên chờ hết 800 ms rồi mới bắt đầu một attempt gần như chắc chắn không còn ngân sách.

Hãy đặt deadline theo yêu cầu nghiệp vụ, tính cả thời gian queue, network, xử lý và backoff. Nếu client cần trả kết quả trong 2 giây, cấu hình backoff và số attempt phải phù hợp ngân sách đó.

Đối với `DEADLINE_EXCEEDED`, cần thận trọng: server có thể đã thực hiện thao tác nhưng response về muộn. Retry thao tác ghi chỉ an toàn khi có idempotency key hoặc cơ chế kiểm tra trạng thái.

## 6. Server pushback và retry throttling

Client không phải lúc nào cũng tự quyết định thời gian retry. Khi quá tải, server có thể gửi **retry pushback** để hướng dẫn client chờ lâu hơn hoặc dừng retry. Với gRPC, cơ chế pushback được truyền qua metadata đặc biệt `grpc-retry-pushback-ms`:

- Giá trị số dương yêu cầu client chờ số mili giây được chỉ định trước khi retry.
- Giá trị âm báo client không retry call đó.
- Nếu metadata không hợp lệ hoặc không thể diễn giải, hành vi phụ thuộc quy tắc của gRPC runtime; không tự suy ra một khoảng chờ tùy ý ở tầng ứng dụng.

Retry throttling của gRPC cũng có thể giảm retry khi tỷ lệ lỗi tăng. Cấu hình throttling và pushback là công cụ bảo vệ dịch vụ; không nên tạo một vòng retry thủ công bên ngoài để bỏ qua tín hiệu dừng hoặc chờ của server.

Pushback không biến một status không retryable thành retryable. Client vẫn phải thỏa điều kiện retry policy, attempt budget và commitment.

## 7. Tránh retry amplification

Một request có thể đi qua nhiều tầng: client API, service nội bộ, proxy và dependency client. Nếu mỗi tầng đều retry ba lần, một thao tác ban đầu có thể tạo ra nhiều request downstream hơn dự kiến.

Ví dụ hai tầng đều cho phép tối đa ba attempt:

```text
Client gọi service: tối đa 3 attempt
  Service gọi dependency: tối đa 3 attempt cho mỗi attempt bên ngoài

Tối đa lý thuyết ở dependency: 3 × 3 = 9 lần gọi
```

Để hạn chế amplification:

1. Chọn một tầng chịu trách nhiệm retry chính cho mỗi dependency.
2. Giới hạn `maxAttempts` và deadline tổng.
3. Dùng backoff, jitter và retry throttling/pushback.
4. Không retry status do lỗi dữ liệu hoặc quyền.
5. Đặt giới hạn concurrency và rate limit ở server.
6. Ghi nhận attempt count để phát hiện retry lồng nhau.

Jitter chỉ phân tán thời điểm; nó **không giảm tổng số attempt**. Muốn giảm lượng tải, cần giảm số lần thử, từ chối sớm hoặc điều tiết tốc độ request.

## 8. Khi tự triển khai jitter ở tầng ứng dụng

Chỉ tự triển khai retry khi cần semantics không được gRPC policy đáp ứng, ví dụ retry một command riêng trong stream hoặc retry một bước nghiệp vụ sau khi đọc lại state. Một hàm full jitter minh họa:

```java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

static Duration fullJitter(
        Duration initial,
        Duration maximum,
        double multiplier,
        int retryIndex) {

    double scaled = initial.toMillis()
            * Math.pow(multiplier, retryIndex);
    long cap = Math.min(maximum.toMillis(), (long) scaled);
    long delay = ThreadLocalRandom.current().nextLong(cap + 1);
    return Duration.ofMillis(delay);
}
```

`retryIndex = 0` tương ứng lần retry đầu tiên. Code minh họa giả định giá trị duration dương, hữu hạn và không tràn số; implementation production cần validate tham số, xử lý overflow và cho phép inject random source để kiểm thử tái lập.

Khi dùng hàm này:

- Chỉ gọi sau khi xác định lỗi đủ điều kiện retry.
- Kiểm tra deadline còn đủ ngân sách trước khi schedule.
- Giữ nguyên idempotency key qua các lần thử cùng một thao tác.
- Dừng ngay khi caller cancel hoặc hết attempt.
- Không dùng đồng thời với retry tự động trên cùng một RPC nếu không có chủ đích rõ ràng.

Với bidi stream đã commit, retry command ở tầng ứng dụng cần correlation ID, deduplication và quy tắc resume. Không mở một vòng lặp gửi lại toàn bộ stream như thể đó là một unary call.

## 9. Kiểm thử backoff và jitter

Không nên kiểm thử bằng cách yêu cầu một lần retry xảy ra chính xác sau 200 ms. Jitter và scheduler khiến thời điểm thực tế thay đổi. Nên kiểm tra các thuộc tính:

| Kịch bản | Assertion |
| --- | --- |
| Retry liên tiếp với backoff tăng dần | Khoảng chờ cơ sở không vượt `maxBackoff` |
| Nhiều client cùng nhận lỗi | Thời điểm retry được phân tán, không tập trung vào một mốc cố định |
| Đạt `maxAttempts` | Không có attempt vượt giới hạn |
| Deadline hết trong backoff | Không bắt đầu attempt sau deadline |
| Server pushback dương | Client tuân thủ thời gian chờ được chỉ định |
| Server pushback âm | Client dừng retry theo cơ chế hỗ trợ |
| Retry throttling kích hoạt | Tần suất retry giảm theo chính sách |
| Caller cancel trong lúc chờ | Timer retry bị hủy, không gửi attempt mới |
| Retry lồng ở hai tầng | Attempt downstream nằm trong ngân sách đã dự kiến |
| Retry thao tác ghi | Idempotency bảo đảm không tạo tác dụng phụ trùng |

Với retry logic tự viết, inject `Clock`, `Scheduler` và random source giả để test deterministic. Với gRPC configured retry, dùng server test có thể trả status theo attempt và ghi timestamp nhận request; kiểm tra số attempt, deadline và khoảng chờ trong biên hợp lý thay vì khẳng định một giá trị jitter cố định.

Các metric nên theo dõi gồm retry attempt count, thời gian backoff thực tế, số call bị dừng do deadline, tỷ lệ retry thành công, số lần server pushback, số lần throttling và tỷ lệ request bị retry nhiều tầng.

## 10. Sai lầm thường gặp

1. **Dùng backoff nhưng không có jitter.** Nhiều client có thể retry đồng bộ và tạo burst.
2. **Cho rằng jitter giảm số lần retry.** Jitter chỉ phân tán thời điểm; attempt budget mới giới hạn tổng số lần.
3. **Không giới hạn backoff.** Khoảng chờ có thể tăng quá mức và không còn phù hợp deadline.
4. **Cấu hình `maxAttempts` như số lần retry bổ sung.** Giá trị này bao gồm lần đầu.
5. **Bỏ qua pushback/throttling.** Client có thể tiếp tục gây tải khi server đã yêu cầu giảm hoặc dừng retry.
6. **Retry ở nhiều tầng mà không tính tổng attempt.** Một request có thể nhân tải downstream.
7. **Tự thêm jitter ngoài gRPC configured retry.** Có thể tạo hai bộ timer và hai tầng retry khó kiểm soát.
8. **Retry thao tác ghi không idempotent.** Server có thể đã thực hiện trước khi response bị mất.

## 11. Bài tập vận dụng

Với `catalog.v1.CatalogService/GetItem`:

1. Cấu hình exponential backoff với `initialBackoff=200ms`, `maxBackoff=2s`, `backoffMultiplier=2` và giới hạn attempt.
2. Mô phỏng nhiều client cùng nhận `UNAVAILABLE`; quan sát thời điểm retry và đánh giá mức phân tán.
3. Thử deadline ngắn hơn tổng thời gian backoff dự kiến; xác minh client không gửi attempt sau deadline.
4. Mô phỏng server pushback dương và âm; xác minh client tôn trọng chỉ dẫn.
5. Viết unit test full jitter với random source giả, kiểm tra giá trị luôn nằm trong khoảng cho phép.
6. Thêm retry ở tầng dependency có chủ đích rồi tính tổng attempt để phát hiện amplification.

**Tiêu chí hoàn thành:** người học giải thích được exponential backoff, cap và jitter; cấu hình được policy gRPC; phân biệt jitter runtime với jitter tự triển khai; phối hợp deadline, pushback và throttling để bảo vệ server.

### Tài liệu tham khảo

- [gRPC Retry](https://grpc.io/docs/guides/retry/): retry policy, exponential backoff, commitment và pushback.
- [gRPC Service Config](https://grpc.io/docs/guides/service-config/): cấu hình retry theo service và method.
- [gRPC Java ManagedChannelBuilder](https://grpc.github.io/grpc-java/javadoc/io/grpc/ManagedChannelBuilder.html): cấu hình service config trên client channel.
- [Spring gRPC Reference](https://docs.spring.io/spring-grpc/reference/): tích hợp gRPC client/server trong Spring.

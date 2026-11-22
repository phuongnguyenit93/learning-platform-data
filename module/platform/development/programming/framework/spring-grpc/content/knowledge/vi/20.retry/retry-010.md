# Retry qua service config

## 1. Service config điều khiển retry ở đâu?

Trong **Spring gRPC**, retry policy thường được khai báo trong **gRPC service config** ở phía client. Service config gắn hành vi cho một service hoặc method cụ thể, nhờ đó client channel có thể tự retry những RPC đủ điều kiện mà không cần viết vòng lặp gửi lại ở từng nơi gọi stub.

Một service config có thể chứa nhiều `methodConfig`. Mỗi entry xác định một hoặc nhiều method bằng tên service Protobuf và tùy chọn tên method, sau đó gắn các chính sách như retry, timeout hoặc wait-for-ready.

Đối với retry, client channel đọc `retryPolicy` và áp dụng khi:

- RPC khớp tên service/method được cấu hình.
- Attempt kết thúc bằng status nằm trong `retryableStatusCodes`.
- Call chưa commit và runtime còn dữ liệu cần thiết để replay.
- Chưa hết `maxAttempts`, deadline và ngân sách retry.
- Không có pushback hoặc throttling yêu cầu dừng retry.

Service config là cấu hình của **client**. Server vẫn cần trả status đúng nguyên nhân; nó không tự retry request thay client.

## 2. Cấu trúc service config

Ví dụ JSON cho hai method của `catalog.v1.CatalogService`:

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
        "retryableStatusCodes": [
          "UNAVAILABLE"
        ]
      }
    },
    {
      "name": [
        {
          "service": "catalog.v1.CatalogService",
          "method": "SearchItems"
        }
      ],
      "retryPolicy": {
        "maxAttempts": 3,
        "initialBackoff": "0.1s",
        "maxBackoff": "1s",
        "backoffMultiplier": 2,
        "retryableStatusCodes": [
          "UNAVAILABLE",
          "RESOURCE_EXHAUSTED"
        ]
      }
    }
  ]
}
```

Ở đây:

- `GetItem` chỉ retry `UNAVAILABLE`, tối đa bốn attempt tổng cộng.
- `SearchItems` retry `UNAVAILABLE` và `RESOURCE_EXHAUSTED`, tối đa ba attempt.
- Mỗi method có backoff riêng, phù hợp với SLA và khả năng chịu tải khác nhau.

Tên service là tên đầy đủ gồm Protobuf package và service name: `catalog.v1.CatalogService`. Tên method là tên RPC trong service: `GetItem`, không phải tên Java method hoặc tên class stub.

### 2.1. Áp dụng cho toàn service

Nếu một entry trong `name` chỉ có `service` và bỏ `method`, policy áp dụng cho các method thuộc service đó:

```json
{
  "methodConfig": [
    {
      "name": [
        {
          "service": "catalog.v1.CatalogService"
        }
      ],
      "retryPolicy": {
        "maxAttempts": 3,
        "initialBackoff": "0.2s",
        "maxBackoff": "1s",
        "backoffMultiplier": 2,
        "retryableStatusCodes": ["UNAVAILABLE"]
      }
    }
  ]
}
```

Policy cấp service thuận tiện nhưng có thể không phù hợp với mọi method. Ví dụ `GetItem` có thể an toàn để retry trong khi `CreateItem` có side effect. Ưu tiên cấu hình rõ từng method nếu semantics khác nhau; tránh một policy rộng vô tình bật retry cho command không idempotent.

## 3. Ý nghĩa các trường retryPolicy

| Trường | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `maxAttempts` | Tổng attempt tối đa, gồm lần đầu | Không phải số retry bổ sung; runtime có thể áp dụng giới hạn theo implementation |
| `initialBackoff` | Khoảng chờ cơ sở trước retry đầu | Dùng duration dạng chuỗi, ví dụ `"0.2s"` |
| `maxBackoff` | Giới hạn khoảng chờ cơ sở | Không đặt lại deadline |
| `backoffMultiplier` | Hệ số tăng backoff | Thường dùng exponential backoff |
| `retryableStatusCodes` | Các status có thể kích hoạt retry | Chỉ chọn lỗi có khả năng phục hồi |

Một số điểm cần nhớ:

- `maxAttempts = 4` nghĩa là tối đa bốn attempt tổng cộng, tương đương tối đa ba retry bổ sung. Theo retry guide của gRPC, giá trị này bị giới hạn tối đa ở 5.
- gRPC áp dụng backoff và jitter theo cơ chế runtime; service config không có trường `jitter` để chọn thuật toán riêng.
- `DEADLINE_EXCEEDED` không nên được thêm tùy tiện: server có thể đã thực hiện tác dụng phụ nhưng response đến muộn.
- `RESOURCE_EXHAUSTED` chỉ nên retry nếu biểu thị quá tải tạm thời; quota cố định hoặc payload quá lớn không tự phục hồi.
- Status không nằm trong danh sách sẽ kết thúc call mà không retry theo policy đó.

## 4. Gắn service config vào gRPC Java channel

gRPC Java nhận service config dưới dạng `Map<String, ?>`. Có thể tạo map trực tiếp:

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
        .enableRetry()
        .defaultServiceConfig(serviceConfig)
        .build();
```

Trong ví dụ Java, các giá trị số được biểu diễn bằng `Double` (`4.0`, `2.0`) để phù hợp với cách gRPC Java parse service config dạng JSON-like map. Duration vẫn là chuỗi có hậu tố đơn vị.

`enableRetry()` bật retry trên channel. Hãy xác nhận cấu hình channel không gọi `disableRetry()`; nếu retry bị tắt, khai báo policy không tự làm các attempt được gửi lại.

Channel nên được tạo một lần và quản lý vòng đời bởi ứng dụng. Không tạo channel mới cho từng RPC chỉ để thay đổi `maxAttempts`; điều đó làm tăng kết nối, thread và chi phí quản lý.

## 5. Service config mặc định và config từ name resolver

gRPC Java có thể nhận service config từ hai nguồn:

- **Resolver-provided service config:** name resolver, thường gắn với DNS hoặc service discovery, cung cấp config cho target.
- **Default service config:** ứng dụng gắn bằng `defaultServiceConfig(...)` trên channel builder.

`defaultServiceConfig` là cấu hình dự phòng khi resolver không cung cấp service config. Nếu resolver có config riêng, config từ resolver được ưu tiên theo cơ chế service config của gRPC. Vì vậy, cấu hình trong code không nhất thiết là policy cuối cùng đang chạy trong môi trường production.

Điều này quan trọng khi chuyển từ local sang Kubernetes/service discovery:

1. Local có thể dùng default config được khai báo trong ứng dụng.
2. Production DNS resolver có thể nhận service config từ DNS TXT record hoặc resolver tương ứng.
3. Policy thực tế có thể khác giữa môi trường nếu resolver trả config khác.
4. Cần quan sát/cấu hình nguồn service config được phép sử dụng và kiểm tra policy hiệu lực.

Không đặt retry policy xung đột ở nhiều nguồn mà không có quy trình quản trị. Khi sự cố xảy ra, đội vận hành cần biết client đang dùng policy nào, không chỉ policy được ghi trong source code.

## 6. Service config trong ứng dụng Spring gRPC

Spring gRPC quản lý việc tạo client channel/stub theo cấu hình của ứng dụng. Service config phải được gắn vào **builder/channel trước khi channel được build**. Cách tích hợp cụ thể phụ thuộc phiên bản Spring gRPC và cơ chế tạo channel của dự án:

- Nếu ứng dụng tự tạo `ManagedChannel`, gắn `defaultServiceConfig` trực tiếp như ví dụ trên.
- Nếu ứng dụng dùng channel factory hoặc bean do Spring quản lý, cấu hình retry ở điểm tùy biến channel builder được phiên bản đó cung cấp.
- Nếu channel được tạo bởi thư viện khác, xác định rõ nơi cấu hình service config và nơi quản lý shutdown.

Không giả định việc inject generated stub tự động có nghĩa retry đã bật. Stub dùng channel nào thì hành vi retry được quyết định bởi channel và service config hiệu lực của channel đó.

Ví dụ về cách tổ chức cấu hình trong ứng dụng:

```java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import java.util.List;
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import com.example.catalog.v1.CatalogServiceGrpc;

@Configuration
public class CatalogClientConfiguration {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel catalogChannel() {
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

        Map<String, Object> config =
                Map.of("methodConfig", List.of(methodConfig));

        return ManagedChannelBuilder
                .forAddress("catalog.internal", 9090)
                .enableRetry()
                .defaultServiceConfig(config)
                .build();
    }

    @Bean
    CatalogServiceGrpc.CatalogServiceBlockingStub catalogStub(
            ManagedChannel catalogChannel) {
        return CatalogServiceGrpc.newBlockingStub(catalogChannel);
    }
}
```

Đây là ví dụ Spring Java config tự quản lý channel. Nếu dự án đã dùng Spring gRPC channel factory, không tạo thêm channel song song; chuyển cùng cấu hình vào builder/customizer hiện có để giữ một nguồn quản lý kết nối và shutdown.

## 7. Retry throttling trong service config

Khi nhiều RPC liên tục thất bại, retry có thể làm tăng tải vào đúng thời điểm server đang quá tải. Service config hỗ trợ `retryThrottling` ở cấp config:

```json
{
  "retryThrottling": {
    "maxTokens": 10,
    "tokenRatio": 0.1
  },
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

Retry throttling duy trì token budget, khởi tạo ở `maxTokens`:

- Lỗi retryable làm giảm token.
- Thành công làm tăng token theo `tokenRatio`, không vượt `maxTokens`.
- Khi token giảm dưới một nửa `maxTokens`, runtime hạn chế retry cho target.

Throttling giúp giảm retry amplification khi lỗi tăng. Nó không thay thế `maxAttempts`, backoff hoặc deadline; cũng không biến status không retryable thành retryable.

## 8. Server pushback và policy ở client

Service config chỉ định status nào có thể retry và cách backoff. Server vẫn có thể gửi retry pushback để yêu cầu client chờ hoặc dừng retry. Với gRPC, pushback được truyền bằng metadata đặc biệt `grpc-retry-pushback-ms`.

- Giá trị dương yêu cầu chờ số mili giây được chỉ định.
- Giá trị âm yêu cầu không retry call đó.
- Pushback không cấp thêm deadline và không làm tăng `maxAttempts`.

Không tạo vòng lặp retry thủ công bên ngoài để bỏ qua pushback. Nếu server đang bảo vệ tải, client tiếp tục retry có thể làm sự cố nghiêm trọng hơn.

## 9. Method matching và phạm vi policy

Service config khớp RPC theo tên đầy đủ:

```text
/catalog.v1.CatalogService/GetItem
 |--------------------------| |---|
         service              method
```

Những lỗi cấu hình thường gặp:

| Sai cấu hình | Hậu quả |
| --- | --- |
| Dùng Java package thay Protobuf package | Không khớp tên service |
| Dùng tên class generated stub | Không khớp tên service |
| Viết sai hoa/thường tên method | Policy không áp dụng cho RPC |
| Bỏ method khi muốn cấu hình riêng một RPC | Policy có thể áp dụng rộng cho toàn service |
| Cấu hình đúng nhưng stub dùng channel khác | RPC không nhận policy dự kiến |
| Resolver cung cấp config khác | Default config trong code có thể không phải config hiệu lực |

Hãy kiểm tra tên method trong file `.proto` và đường dẫn RPC đầy đủ. Một cách quan sát hữu ích là log tên method từ interceptor phía client/server và so sánh với entry `name` trong service config.

## 10. Điều kiện runtime vẫn giới hạn retry

Service config không bỏ qua các điều kiện cốt lõi của gRPC:

1. **Retryable status:** lỗi kết thúc phải thuộc `retryableStatusCodes`.
2. **Attempt budget:** chưa đạt `maxAttempts`; giá trị này bao gồm attempt đầu và implementation có thể áp dụng giới hạn tối đa.
3. **Commitment:** call chưa commit; nhận response headers hoặc vượt retry buffer có thể làm call commit.
4. **Deadline:** còn ngân sách cho backoff và attempt tiếp theo.
5. **Pushback/throttling:** runtime chưa bị yêu cầu dừng hoặc hạn chế retry.
6. **Replay safety:** thao tác nghiệp vụ phải an toàn khi request được thực thi lại; với command ghi cần idempotency.

Đối với client-streaming và bidirectional streaming, khi call đã commit, service config không thể resume stream từ message cuối. Cần protocol reconnect/resume ở tầng ứng dụng với sequence, cursor hoặc idempotency key.

## 11. Kiểm thử service config

Nên có integration test sử dụng gRPC server/channel thật trên loopback để xác minh runtime áp dụng policy. Server test có thể trả `UNAVAILABLE` hai lần rồi thành công:

```java
import java.util.concurrent.atomic.AtomicInteger;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import com.example.catalog.v1.CatalogServiceGrpc;
import com.example.catalog.v1.GetItemRequest;
import com.example.catalog.v1.GetItemResponse;

AtomicInteger calls = new AtomicInteger();

CatalogServiceGrpc.CatalogServiceImplBase service =
        new CatalogServiceGrpc.CatalogServiceImplBase() {
    @Override
    public void getItem(
            GetItemRequest request,
            StreamObserver<GetItemResponse> responseObserver) {
        int attempt = calls.incrementAndGet();
        if (attempt <= 2) {
            responseObserver.onError(
                    Status.UNAVAILABLE.asRuntimeException());
            return;
        }
        responseObserver.onNext(GetItemResponse.newBuilder()
                .setItemId(request.getItemId())
                .build());
        responseObserver.onCompleted();
    }
};
```

Tạo channel test với service config có `maxAttempts=3`, retry `UNAVAILABLE`, rồi gọi `GetItem`. Assertion cần xác minh client nhận response thành công và server nhận đúng ba attempt. Test này cần bảo đảm server không gửi response headers trước status ở hai lần thất bại, nếu không call có thể đã commit và không retry.

Các trường hợp nên kiểm thử:

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Method khớp config, hai lần `UNAVAILABLE`, sau đó thành công | Client retry và nhận response |
| Method không có entry retry policy | Không áp dụng configured retry của method khác |
| Status `INVALID_ARGUMENT` | Không retry nếu status không nằm trong danh sách |
| Đạt `maxAttempts` | Không có attempt vượt giới hạn |
| Deadline hết trong backoff | Call dừng, không bắt đầu attempt sau deadline |
| Resolver cung cấp service config | Xác minh config hiệu lực theo nguồn resolver |
| Retry throttling giảm token | Retry bị hạn chế khi đạt ngưỡng |
| Server pushback yêu cầu dừng | Client không tiếp tục retry call đó |
| Call đã commit rồi mới lỗi | Không kỳ vọng automatic replay |
| Command ghi được retry | Cùng idempotency key không tạo tác dụng phụ trùng |

Không chỉ kiểm tra JSON/map parse thành công. Phải kiểm tra số attempt thực tế, status cuối, thời gian tổng và hành vi của method không khớp policy.

## 12. Quan sát và vận hành service config

Một policy chỉ hữu ích khi đội vận hành biết nó đang có hiệu lực. Nên theo dõi:

- Tên RPC và service config source (default hoặc resolver).
- Attempt count cho mỗi logical call.
- Status của từng attempt và status cuối.
- Backoff thực tế, deadline còn lại và call kết thúc do timeout.
- Retry throttling/pushback có kích hoạt không.
- Tỷ lệ retry thành công và số request tăng thêm do retry.

Không ghi payload nhạy cảm hoặc credential vào log để điều tra retry. Correlation ID/trace ID nên được giữ xuyên các attempt nếu instrumentation hỗ trợ, đồng thời phân biệt attempt number để trace không bị hiểu nhầm là nhiều thao tác nghiệp vụ độc lập.

Khi thay đổi policy production, triển khai theo phạm vi method, quan sát tỷ lệ lỗi/tải và có phương án rollback. Tăng `maxAttempts` có thể làm tăng tải downstream; không xem đó là biện pháp mặc định để chữa outage.

## 13. Sai lầm thường gặp

1. **Khai báo retry policy nhưng không gắn vào client channel.** Server không tự áp dụng policy thay client.
2. **Dùng sai tên service/method.** Policy tồn tại nhưng không match RPC.
3. **Nghĩ defaultServiceConfig luôn thắng.** Resolver-provided config có thể được ưu tiên.
4. **Tạo channel cho từng request.** Tăng tài nguyên và làm khó quản lý retry state.
5. **Áp dụng retry ở cấp service cho mọi method.** Có thể bật retry cho command không idempotent.
6. **Bỏ qua deadline/commitment.** Config không thể replay call đã commit hoặc vượt deadline.
7. **Retry lồng ở nhiều tầng.** Số request downstream có thể tăng theo cấp số nhân.
8. **Không kiểm thử số attempt.** Response thành công cuối cùng chưa chứng minh policy áp dụng đúng.
9. **Coi retry throttling là rate limit tổng.** Nó điều tiết retry, không thay thế admission control hoặc rate limit cho request mới.

## 14. Bài tập vận dụng

Với `catalog.v1.CatalogService`:

1. Tạo service config riêng cho `GetItem` và `SearchItems`, mỗi method có status, backoff và `maxAttempts` khác nhau.
2. Gắn config vào channel Java; xác minh stub Spring sử dụng đúng channel.
3. Tạo server test trả `UNAVAILABLE` hai lần rồi thành công; kiểm tra attempt count.
4. Thêm method `CreateItem` có side effect và xác minh method đó không bị policy đọc áp dụng nhầm.
5. Thử default service config và resolver-provided config; xác định config hiệu lực.
6. Bật retry throttling, mô phỏng lỗi tăng và quan sát retry bị hạn chế.
7. Đặt deadline ngắn và xác minh call dừng trước khi dùng hết attempt budget.

**Tiêu chí hoàn thành:** người học viết và gắn được service config cho đúng method, hiểu nguồn config hiệu lực, giải thích điều kiện runtime của retry và kiểm thử được attempt count, deadline, throttling cùng phạm vi policy.

### Tài liệu tham khảo

- [gRPC Retry](https://grpc.io/docs/guides/retry/): retry policy, backoff, commitment và throttling.
- [gRPC Service Config](https://grpc.io/docs/guides/service-config/): cấu trúc service config và method matching.
- [gRPC Java ManagedChannelBuilder](https://grpc.github.io/grpc-java/javadoc/io/grpc/ManagedChannelBuilder.html): `defaultServiceConfig()`, `enableRetry()` và cấu hình channel.
- [Spring gRPC Reference](https://docs.spring.io/spring-grpc/reference/): tích hợp client channel và stub trong Spring.

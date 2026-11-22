# Retryable status code

## 1. Retryable status code là gì?

gRPC kết thúc một RPC bằng status, chẳng hạn `OK`, `UNAVAILABLE` hoặc `INVALID_ARGUMENT`. **Retryable status code** là mã trạng thái mà client được cấu hình để thử lại lời gọi khi nhận status đó và khi các điều kiện retry khác vẫn được đáp ứng.

Không phải mọi lỗi đều nên retry. Nếu client gửi payload sai, gửi lại cùng payload thường chỉ tạo thêm một lần thất bại. Nếu dịch vụ tạm thời không khả dụng, retry có backoff có thể giúp lời gọi thành công khi hệ thống phục hồi.

Trong Spring gRPC, cần phân biệt hai trách nhiệm:

- **Server** trả status phản ánh đúng nguyên nhân: lỗi tạm thời, lỗi dữ liệu, lỗi xác thực hay trạng thái nghiệp vụ.
- **Client** cấu hình retry policy để quyết định status nào được thử lại, số lần tối đa và khoảng chờ giữa các lần thử.

Retry là hành vi ở cấp **RPC**. Một lỗi nghiệp vụ được gửi như response message trong stream không tự kích hoạt gRPC retry policy.

## 2. Phân loại status theo khả năng retry

Bảng sau là hướng dẫn lựa chọn phổ biến, không phải quy tắc bắt buộc cho mọi hệ thống. Quyết định cuối cùng phải dựa vào nguyên nhân lỗi và tính an toàn khi thực thi lại thao tác.

| Status | Ý nghĩa thường gặp | Chính sách retry |
| --- | --- | --- |
| `UNAVAILABLE` | Dịch vụ hoặc dependency tạm thời không khả dụng | **Thường phù hợp** với retry có backoff |
| `RESOURCE_EXHAUSTED` | Hết quota, tài nguyên hoặc đang quá tải | Chỉ retry khi nguyên nhân có thể phục hồi; cần backoff/pushback |
| `ABORTED` | Giao dịch bị hủy do xung đột đồng thời | Thường retry ở cấp thao tác/giao dịch cao hơn, sau khi đọc lại trạng thái |
| `DEADLINE_EXCEEDED` | RPC vượt quá thời hạn | Chỉ retry nếu còn ngân sách thời gian và thao tác an toàn; server có thể đã thực hiện xong |
| `INTERNAL` | Lỗi nội bộ ngoài dự kiến | Không bật retry đại trà; chỉ retry khi đã xác định nguyên nhân có tính tạm thời |
| `CANCELLED` | Call bị hủy | Thông thường không retry nếu cancellation đến từ người gọi |
| `INVALID_ARGUMENT` | Dữ liệu đầu vào không hợp lệ | Không retry nếu chưa sửa dữ liệu |
| `FAILED_PRECONDITION` | Trạng thái hệ thống chưa đáp ứng điều kiện | Không retry cho tới khi điều kiện được thay đổi |
| `UNAUTHENTICATED`, `PERMISSION_DENIED` | Thiếu xác thực hoặc không đủ quyền | Không retry tự động; cần sửa credential/quyền |
| `NOT_FOUND`, `ALREADY_EXISTS`, `OUT_OF_RANGE` | Không tìm thấy, đã tồn tại hoặc ngoài phạm vi | Thường là lỗi nghiệp vụ; không retry mù quáng |
| `UNIMPLEMENTED`, `DATA_LOSS` | Phương thức không được hỗ trợ hoặc dữ liệu mất/hỏng | Không retry tự động theo mặc định |

### 2.1. Ba status dễ nhầm

- **`UNAVAILABLE`**: thường có nghĩa lời gọi hiện tại không thể được xử lý do dịch vụ tạm thời không sẵn sàng. Đây là ứng viên retry điển hình.
- **`ABORTED`**: thường biểu thị xung đột trong một thao tác có tính giao dịch. Client có thể cần đọc lại dữ liệu, tính lại thay đổi rồi thử lại toàn bộ thao tác nghiệp vụ, chứ không đơn giản gửi lại đúng RPC cũ.
- **`FAILED_PRECONDITION`**: hệ thống chưa ở trạng thái cho phép thực hiện. Retry chỉ có ý nghĩa sau khi trạng thái được sửa, ví dụ hoàn tất bước khởi tạo hoặc mở khóa tài nguyên.

`RESOURCE_EXHAUSTED` cũng cần phân tích kỹ. Quá tải tạm thời có thể phục hồi sau một khoảng chờ; quota cố định đã hết hoặc message vượt giới hạn kích thước sẽ không tự hết bằng cách retry ngay.

## 3. Retry policy được cấu hình ở client

gRPC dùng **service config** để gắn retry policy vào một service/method. Các trường chính:

| Trường | Ý nghĩa |
| --- | --- |
| `maxAttempts` | Tổng số lần thử tối đa, **bao gồm lần đầu tiên** |
| `initialBackoff` | Khoảng chờ ban đầu trước retry |
| `maxBackoff` | Giới hạn trên của khoảng chờ |
| `backoffMultiplier` | Hệ số tăng backoff sau mỗi lần thất bại |
| `retryableStatusCodes` | Danh sách status cho phép retry |

Ví dụ service config cho phương thức unary `inventory.v1.InventoryService/GetItem`:

```json
{
  "methodConfig": [
    {
      "name": [
        {
          "service": "inventory.v1.InventoryService",
          "method": "GetItem"
        }
      ],
      "retryPolicy": {
        "maxAttempts": 4,
        "initialBackoff": "0.2s",
        "maxBackoff": "2s",
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

Với cấu hình này, client thử tối đa bốn lần tổng cộng. Nếu nhận `INVALID_ARGUMENT`, lời gọi không được retry theo policy trên. Backoff tăng dần và được gRPC áp dụng jitter để giảm tình trạng nhiều client đồng loạt retry cùng một thời điểm.

### 3.1. Cấu hình trên gRPC Java channel

Có thể biểu diễn service config dưới dạng `Map` rồi gắn vào `ManagedChannelBuilder`:

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
        "retryableStatusCodes",
        List.of("UNAVAILABLE", "RESOURCE_EXHAUSTED"));

Map<String, Object> methodConfig = Map.of(
        "name", List.of(Map.of(
                "service", "inventory.v1.InventoryService",
                "method", "GetItem")),
        "retryPolicy", retryPolicy);

Map<String, Object> serviceConfig =
        Map.of("methodConfig", List.of(methodConfig));

ManagedChannel channel = ManagedChannelBuilder
        .forAddress("localhost", 9090)
        .defaultServiceConfig(serviceConfig)
        .build();
```

Trong ứng dụng Spring gRPC, áp dụng service config vào channel do cấu hình/factory của phiên bản Spring gRPC đang dùng tạo ra. Điểm tích hợp cụ thể phụ thuộc cách dự án tạo channel; điều quan trọng là policy phải nằm trên **client channel**, khớp đúng tên service và method. Không đặt retry policy này ở server rồi kỳ vọng client tự retry.

Chỉ cấu hình những method có thể retry an toàn. Không dùng một policy rộng cho toàn bộ service nếu các method có semantics khác nhau.

## 4. Server phải trả đúng status

Client chỉ có thể phân loại retry chính xác khi server dùng status đúng nguyên nhân. Ví dụ lỗi dependency tạm thời:

```java
throw io.grpc.Status.UNAVAILABLE
        .withDescription("Dịch vụ lưu kho tạm thời không sẵn sàng")
        .asRuntimeException();
```

Ví dụ request không hợp lệ:

```java
throw io.grpc.Status.INVALID_ARGUMENT
        .withDescription("item_id không được rỗng")
        .asRuntimeException();
```

Nếu server trả `INTERNAL` cho mọi loại lỗi, client không thể phân biệt lỗi tạm thời với lỗi đầu vào. Nếu server trả `UNAVAILABLE` cho một lỗi dữ liệu cố định, client có thể lặp lại vô ích và làm tăng tải.

Với `RESOURCE_EXHAUSTED`, server nên cung cấp thông tin retry phù hợp nếu cơ chế triển khai hỗ trợ pushback. Khi server báo không nên retry, client cần tôn trọng tín hiệu đó; không tự tạo vòng lặp retry ở tầng ứng dụng để vượt qua chính sách quá tải.

## 5. Retry an toàn phụ thuộc vào idempotency

Retryable status chỉ trả lời câu hỏi **khi nào được phép thử lại theo policy**. Nó không đảm bảo thao tác chưa được thực hiện ở server.

Ví dụ client gọi `CreatePayment`. Server đã ghi giao dịch thành công nhưng kết nối đứt trước khi client nhận response. Client có thể thấy `UNAVAILABLE` hoặc `DEADLINE_EXCEEDED`. Nếu gửi lại lệnh tạo thanh toán mà không có idempotency, server có thể tạo hai giao dịch.

Để retry an toàn:

1. Tạo một `idempotency_key` ổn định cho một thao tác logic; giữ nguyên key qua các lần retry.
2. Server lưu key cùng kết quả hoặc trạng thái xử lý trong storage có tính nhất quán phù hợp.
3. Nếu nhận lại key đã hoàn tất, trả kết quả đã lưu thay vì thực thi lần nữa.
4. Nếu key đang được xử lý, trả trạng thái phù hợp hoặc cho client tiếp tục theo dõi.
5. Nếu cùng key nhưng payload khác, từ chối để tránh tái sử dụng key sai mục đích.

Các thao tác đọc thường dễ retry hơn thao tác ghi. Tuy nhiên, ngay cả một thao tác đọc cũng có thể có tác dụng phụ như tính phí, ghi audit hoặc tạo snapshot; hãy đánh giá semantics thật thay vì chỉ dựa vào tên method.

## 6. Giới hạn retry: deadline, ngân sách và tải

Retry làm tăng số lần request đến server. Khi server đang quá tải, retry không kiểm soát có thể tạo **retry storm** và làm sự cố nghiêm trọng hơn.

Một policy thực tế cần:

- Giới hạn `maxAttempts`; không retry vô hạn.
- Đặt deadline cho toàn lời gọi và bảo đảm còn đủ thời gian cho lần thử tiếp theo.
- Dùng exponential backoff có jitter.
- Chỉ chọn status thực sự có thể phục hồi.
- Tôn trọng pushback hoặc hướng dẫn thời gian chờ từ server nếu được hỗ trợ.
- Theo dõi số attempt, tỷ lệ retry thành công, status cuối và độ trễ tổng.

`DEADLINE_EXCEEDED` đặc biệt nhạy cảm: server có thể đã hoàn tất thao tác nhưng response đến muộn. Trước khi retry một thao tác ghi, cần idempotency key hoặc cơ chế truy vấn trạng thái theo request ID.

## 7. Retry với client streaming và bidirectional streaming

Retry của gRPC không có nghĩa là một stream đang chạy sẽ tự tiếp tục từ đúng message bị lỗi. Cơ chế retry tự động bị giới hạn bởi trạng thái **commit** của RPC. Khi call đã commit — ví dụ client đã nhận response headers hoặc dữ liệu request vượt giới hạn buffer retry — gRPC không thể tự replay call như lúc chưa commit.

Vì bidi stream thường nhận response headers khi bắt đầu trao đổi và có thể gửi/nhận message liên tục, khả năng retry tự động thường chỉ hữu ích ở giai đoạn đầu, trước khi call commit. Khi stream đã hoạt động, nếu kết nối bị lỗi thì ứng dụng thường phải:

1. Mở một RPC mới.
2. Gửi lại thông tin phiên hoặc cursor để server xác định điểm tiếp tục.
3. Replay những command chưa được xác nhận theo quy tắc idempotency.
4. Dùng `request_id`/sequence để server phát hiện bản tin trùng và client phát hiện bản tin thiếu.
5. Không phát lại command không an toàn nếu chưa xác minh trạng thái xử lý ở server.

Một response message nghiệp vụ như `TaskRejected` hoặc `TaskFailed` không phải terminal gRPC status và không kích hoạt retry policy. Nếu muốn retry riêng một command trong bidi stream, client cần xử lý ở tầng ứng dụng bằng request ID, trạng thái task và backoff riêng; không restart toàn RPC chỉ vì một command bị từ chối.

## 8. Kiểm thử retryable status code

Nên kiểm tra cả quyết định của server và hành vi retry của client:

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Server trả `UNAVAILABLE` rồi thành công | Client retry theo policy và cuối cùng nhận kết quả |
| Server trả `INVALID_ARGUMENT` | Không retry theo policy mẫu |
| Server trả `RESOURCE_EXHAUSTED` tạm thời | Retry có backoff hoặc theo pushback |
| Server trả `RESOURCE_EXHAUSTED` do quota cố định | Không tạo vòng lặp retry liên tục |
| Hết `maxAttempts` | Client nhận status cuối cùng |
| Deadline không đủ cho lần thử tiếp | Call kết thúc; không vượt deadline |
| Thao tác ghi được thực hiện nhưng response bị mất | Retry với cùng idempotency key không tạo tác dụng phụ lần hai |
| Bidi stream đã commit rồi bị ngắt | Client mở phiên mới và resume theo contract ứng dụng, không giả định stream cũ được replay toàn bộ |

Trong test retry tự động, dùng server giả lập trả một số status có kiểm soát trước khi thành công và cấu hình channel với service config thật. Kiểm tra số lần server nhận request, status cuối và idempotency. Tránh chỉ kiểm tra rằng client nhận được kết quả; điều đó không chứng minh policy đã retry đúng số lần hoặc không retry status không được phép.

## 9. Sai lầm thường gặp

1. **Retry mọi status:** lỗi dữ liệu, quyền hoặc trạng thái nghiệp vụ không tự biến mất sau một lần gửi lại.
2. **Coi `RESOURCE_EXHAUSTED` luôn retry được:** quota cố định và quá tải tạm thời cần chính sách khác nhau.
3. **Retry `ABORTED` bằng cách gửi lại nguyên RPC:** có thể cần đọc lại và chạy lại cả giao dịch nghiệp vụ.
4. **Bỏ qua idempotency:** server có thể đã thực hiện thao tác trước khi client nhận lỗi.
5. **Đặt `maxAttempts` quá cao hoặc không có deadline:** làm tăng tải và độ trễ.
6. **Cho rằng bidi stream tự resume:** retry tự động không khôi phục một stream đã commit.
7. **Nhầm lỗi message với gRPC status:** response lỗi trong Protobuf không kích hoạt retry policy của RPC.
8. **Trả status sai nguyên nhân:** client không thể chọn retry policy đáng tin cậy nếu server phân loại lỗi không chính xác.

## 10. Bài tập vận dụng

Với service `inventory.v1.InventoryService`:

1. Cấu hình retry policy cho `GetItem` với `UNAVAILABLE` và một số trường hợp `RESOURCE_EXHAUSTED` đã xác định là tạm thời.
2. Không bật retry tự động cho `CreateItem` trước khi triển khai idempotency key.
3. Viết test server trả `UNAVAILABLE` hai lần rồi thành công; xác minh tổng số attempt không vượt `maxAttempts`.
4. Viết test `INVALID_ARGUMENT` chỉ được gọi một lần.
5. Mô phỏng `DEADLINE_EXCEEDED` sau khi thao tác ghi đã hoàn tất; xác minh retry cùng idempotency key không tạo bản ghi thứ hai.
6. Với một bidi stream, mô phỏng lỗi sau khi call đã commit và triển khai reconnect/resume bằng cursor thay vì dựa vào automatic retry.

**Tiêu chí hoàn thành:** người học chọn đúng status cho lỗi tạm thời và lỗi không thể phục hồi, cấu hình retry có giới hạn ở client, bảo vệ thao tác ghi bằng idempotency và hiểu rõ giới hạn retry tự động của streaming RPC.

### Tài liệu tham khảo

- [gRPC Retry](https://grpc.io/docs/guides/retry/): retry policy, backoff, commit và giới hạn retry.
- [gRPC Status Codes](https://grpc.io/docs/guides/status-codes/): ý nghĩa status do ứng dụng và thư viện gRPC trả về.
- [gRPC Service Config](https://grpc.io/docs/guides/service-config/): cấu hình hành vi client theo service và method.
- [gRPC Java ManagedChannelBuilder](https://grpc.github.io/grpc-java/javadoc/io/grpc/ManagedChannelBuilder.html): cấu hình service config trên client channel.
- [Spring gRPC Reference](https://docs.spring.io/spring-grpc/reference/): tích hợp gRPC client/server trong Spring.

# RESOURCE_EXHAUSTED do message hoặc quota

`RESOURCE_EXHAUSTED` là mã trạng thái gRPC cho biết một tài nguyên cần thiết đã cạn hoặc một giới hạn sử dụng đã bị vượt qua. Trong dịch vụ Spring gRPC, lỗi thường xuất hiện khi message protobuf vượt giới hạn nhận, khi client không nhận được response vì response quá lớn, hoặc khi ứng dụng từ chối request do quota và giới hạn tải.

Các nguyên nhân này có cách khắc phục khác nhau. Tăng giới hạn message không giải quyết được quota; retry liên tục cũng không giúp một payload vốn đã quá lớn. Trước khi sửa, cần xác định thành phần phát ra trạng thái và giới hạn nào đã bị chạm tới.

## Nhận diện đúng nguồn lỗi

`RESOURCE_EXHAUSTED` có thể được tạo bởi gRPC runtime, interceptor, service hoặc một thành phần trung gian. Hãy ghi nhận tối thiểu:

- Tên RPC, loại RPC (unary, client streaming, server streaming hay bidirectional streaming) và chiều truyền dữ liệu.
- Mã trạng thái, description, trailers và trace/request ID nếu có.
- Kích thước message thực tế, giới hạn đang áp dụng và thành phần phát hiện vượt giới hạn.
- Tenant hoặc principal đã được xác thực, loại quota và thời điểm quota được làm mới.

Không ghi toàn bộ payload, token xác thực hoặc metadata nhạy cảm vào log. Kích thước message nên được ghi bằng số byte và theo cùng một cách đo ở nơi gửi và nơi nhận.

| Dấu hiệu | Nguồn có khả năng cao | Hướng xử lý |
|---|---|---|
| Request lớn bị từ chối trước khi service xử lý | Giới hạn inbound message của server hoặc proxy | Giảm/chia request hoặc điều chỉnh giới hạn ở receiver sau khi đánh giá bộ nhớ |
| Server trả response lớn, client nhận `RESOURCE_EXHAUSTED` | Giới hạn inbound message của client hoặc gateway | Phân trang/chia response hoặc điều chỉnh giới hạn nhận của client |
| Request nhỏ vẫn bị từ chối sau một số lần gọi | Quota theo tenant, người dùng, API hoặc cửa sổ thời gian | Kiểm tra chính sách quota, tốc độ gọi và thời điểm reset |
| Lỗi tăng khi tải đồng thời tăng | Giới hạn concurrency, hàng đợi hoặc bộ đệm của ứng dụng | Giới hạn tải, áp dụng backpressure và kiểm tra năng lực tài nguyên |

Lưu ý: giới hạn message được kiểm tra tại phía nhận. Vì vậy, cần xem cấu hình của đúng receiver: server nhận request, client nhận response, và cả proxy/gateway nếu luồng RPC đi qua chúng. Giới hạn kích thước metadata là một cấu hình riêng, không thay thế giới hạn message.

## Xử lý message vượt giới hạn

### Xác định chiều và ngưỡng bị vượt

Với unary RPC, đo kích thước request trước khi gửi và response trước khi trả về. Với streaming RPC, kiểm tra kích thước của từng message; nếu ứng dụng còn có quota tổng cho cả stream thì phải đo và kiểm soát tổng đó riêng.

Trong grpc-java, `maxInboundMessageSize` cấu hình kích thước message tối đa mà một receiver chấp nhận. Ví dụ dưới đây minh họa API nền tảng của grpc-java; khi dùng Spring gRPC, hãy áp dụng giá trị tương đương qua điểm mở rộng cấu hình `ServerBuilder` hoặc `ManagedChannelBuilder` mà phiên bản starter đang sử dụng cung cấp.

```java
// Phía server: giới hạn kích thước request mà server nhận.
Server server = ServerBuilder.forPort(port)
    .maxInboundMessageSize(8 * 1024 * 1024)
    .addService(grpcService)
    .build();
```

```java
// Phía client: giới hạn kích thước response mà client nhận.
ManagedChannel channel = ManagedChannelBuilder
    .forAddress(host, port)
    .useTransportSecurity()
    .maxInboundMessageSize(8 * 1024 * 1024)
    .build();
```

Hai ví dụ trên dùng ngưỡng 8 MiB để minh họa, không phải giá trị khuyến nghị cho mọi hệ thống. Đặt giới hạn dựa trên kích thước payload thực tế, heap khả dụng, số RPC đồng thời và số bản sao dữ liệu có thể tồn tại trong quá trình deserialize/xử lý. Một giới hạn lớn có thể làm tăng đột biến bộ nhớ khi nhiều request lớn đến cùng lúc.

Chỉ tăng giới hạn khi payload đó là hợp lệ và hệ thống đủ tài nguyên để xử lý. Nếu dữ liệu vốn lớn, hãy cân nhắc:

- Chia dữ liệu thành các chunk có kích thước giới hạn và truyền qua client/server streaming.
- Phân trang response hoặc cung cấp API truy vấn theo phần.
- Đưa file lớn vào object storage, sau đó gửi URI hoặc định danh cùng metadata cần thiết qua gRPC.
- Dùng compression khi phù hợp để giảm băng thông; vẫn phải duy trì giới hạn kích thước an toàn ở receiver vì compression không thay thế kiểm soát kích thước dữ liệu sau giải nén.

Nếu lỗi xảy ra ở gateway hoặc proxy, thay đổi cấu hình riêng của ứng dụng có thể không có tác dụng. Hãy đối chiếu giới hạn ở toàn bộ đường đi của RPC và kiểm tra log của thành phần trả trạng thái.

## Xử lý quota và giới hạn tải

Quota thường được áp dụng theo tenant, principal, API, loại thao tác hoặc cửa sổ thời gian. Với Spring gRPC, có thể đặt kiểm tra ở interceptor hoặc trong service tùy phạm vi chính sách. Danh tính dùng để tính quota phải lấy từ principal đã xác thực, không lấy trực tiếp một tenant ID chưa được kiểm chứng từ request.

Ví dụ tối giản về service từ chối request khi quota đã hết:

```java
if (!quotaService.tryConsume(authenticatedTenantId, 1)) {
    throw Status.RESOURCE_EXHAUSTED
        .withDescription("Request quota exceeded")
        .asRuntimeException();
}
```

`tryConsume` cần có hành vi nguyên tử khi nhiều instance cùng xử lý request cho một tenant. Nếu quota được lưu trong Redis hoặc kho dữ liệu dùng chung, thao tác kiểm tra và trừ quota phải tránh tình trạng hai instance cùng đọc một mức quota rồi cùng chấp nhận request vượt ngưỡng. Nên xác định rõ quota theo request, theo byte, theo thời gian xử lý hay theo một đơn vị nghiệp vụ có trọng số.

Khi có thể retry sau một khoảng thời gian, hãy trả thông tin đủ rõ để client chờ đúng lúc, chẳng hạn thời gian reset hoặc retry delay. Hệ thống dùng gRPC rich error model có thể đính kèm `google.rpc.QuotaFailure` và `google.rpc.RetryInfo` trong status details. Client cần đọc details theo đúng kiểu đã thỏa thuận; không nên phân tích chuỗi description như một giao thức máy đọc.

Thông báo lỗi nên giúp vận hành xác định quota nào bị vượt nhưng không tiết lộ ngưỡng nội bộ, định danh khách hàng khác hoặc dữ liệu nhạy cảm. Log phía server có thể lưu chi tiết chính sách hơn, gắn với trace ID để tra cứu.

## Xử lý lỗi ở client

Client Java thường nhận lỗi dưới dạng `StatusRuntimeException`. Có thể phân loại mã trạng thái bằng `Status.fromThrowable`:

```java
try {
    Reply reply = blockingStub.withDeadlineAfter(3, TimeUnit.SECONDS)
        .process(request);
    return reply;
} catch (StatusRuntimeException ex) {
    Status status = Status.fromThrowable(ex);

    if (status.getCode() == Status.Code.RESOURCE_EXHAUSTED) {
        // Đọc status details/trailers theo hợp đồng của dịch vụ.
        // Chỉ retry khi lỗi là quota tạm thời và đã biết thời điểm retry.
        throw ex;
    }

    throw ex;
}
```

Đoạn mã trên minh họa điểm phân loại lỗi; chính sách retry cần được triển khai riêng. Với quota tạm thời, client có thể chờ theo `RetryInfo` hoặc thời điểm reset, cộng thêm jitter, giới hạn số lần thử và vẫn tuân thủ deadline tổng của thao tác. Với message quá lớn, retry cùng payload không thay đổi sẽ tiếp tục thất bại; client cần giảm/chia payload hoặc dùng luồng truyền dữ liệu phù hợp.

Chỉ tự động retry thao tác có tính idempotent hoặc đã có cơ chế chống thực hiện trùng. Nếu request có thể tạo giao dịch, gửi thanh toán hoặc ghi dữ liệu, cần idempotency key hay cơ chế tương đương trước khi retry. Không retry ngay lập tức trong vòng lặp vì điều đó làm quota và tình trạng quá tải tệ hơn.

## Streaming và backpressure

Streaming không loại bỏ giới hạn message. Mỗi message vẫn cần nằm trong giới hạn inbound của receiver, và ứng dụng nên đặt thêm giới hạn cho tổng byte, số message, thời lượng stream và số stream đồng thời nếu nghiệp vụ yêu cầu.

Không đưa toàn bộ message đến vào một hàng đợi không giới hạn. Với server streaming hoặc bidirectional streaming, chỉ tạo/gửi phần dữ liệu tiếp theo khi phía nhận sẵn sàng; dùng cơ chế readiness/flow control của gRPC và giữ hàng đợi ở kích thước hữu hạn. Khi hàng đợi đầy, ứng dụng cần có chính sách rõ ràng như tạm dừng đọc, từ chối stream hoặc hủy stream với trạng thái phù hợp.

Quota của stream cũng cần được giải phóng đúng cách khi client hủy RPC, deadline hết hạn hoặc kết nối đóng. Nếu quota được giữ theo thời gian sống của stream, hãy bảo đảm nhánh kết thúc và lỗi đều giải phóng tài nguyên.

## Quy trình điều tra và khắc phục

1. Lấy trace ID, RPC method, mã trạng thái, description và trailers từ client log; tìm request tương ứng trong server/gateway log.
2. Xác định lỗi phát sinh ở server, client, interceptor, service hay proxy; ghi rõ request hay response đang vượt giới hạn.
3. Đối chiếu kích thước message thực tế với `maxInboundMessageSize` tại receiver và các giới hạn của gateway.
4. Nếu là quota, kiểm tra principal/tenant đã xác thực, loại quota, mức tiêu thụ, cửa sổ reset và tính nguyên tử của bộ đếm.
5. Chọn biện pháp phù hợp: giới hạn payload, chia chunk, phân trang, điều chỉnh ngưỡng có kiểm soát, giảm tốc độ gọi hoặc áp dụng backpressure.
6. Kiểm tra client có retry đúng điều kiện, có backoff/jitter, giới hạn lần thử và deadline hay không.
7. Theo dõi tỷ lệ `RESOURCE_EXHAUSTED`, kích thước payload, số request bị quota từ chối, độ sâu hàng đợi, heap và số RPC đồng thời sau khi triển khai.

## Kiểm thử cần có

- Gửi request ngay dưới, đúng bằng và vượt ngưỡng inbound của server; xác minh request vượt ngưỡng bị từ chối có kiểm soát.
- Tạo response lớn hơn giới hạn inbound của client để xác minh chiều response được cấu hình và giám sát riêng.
- Gọi liên tiếp đến khi quota hết, xác minh trạng thái trả về, thông tin reset/retry và thời điểm quota được cấp lại.
- Gửi request đồng thời từ nhiều instance cho cùng tenant để kiểm tra bộ đếm quota không cho phép vượt giới hạn do race condition.
- Kiểm thử stream với message lớn, nhiều message, client cancel và deadline hết hạn; xác minh bộ đệm hữu hạn và tài nguyên được giải phóng.
- Xác minh client không retry payload quá lớn và chỉ retry quota tạm thời theo chính sách đã công bố.

## Tránh các cách sửa sai

- Không tăng giới hạn message hàng loạt khi chưa đo heap và concurrency.
- Không retry liên tục một lỗi quota hoặc gửi lại payload đã biết là quá lớn.
- Không dùng `RESOURCE_EXHAUSTED` cho mọi lỗi đầu vào; dữ liệu sai định dạng thường phù hợp với `INVALID_ARGUMENT`, còn lỗi dịch vụ tạm thời có thể phù hợp với `UNAVAILABLE` tùy nguyên nhân.
- Không phụ thuộc vào nội dung description để client quyết định hành vi; dùng status code và error details có cấu trúc.
- Không bỏ qua gateway/proxy hoặc cấu hình phía nhận khi điều tra lỗi kích thước message.

Khi đã xác định được giới hạn gây lỗi, hãy sửa đúng tầng sở hữu giới hạn đó và kiểm thử cả trường hợp sát ngưỡng lẫn tải đồng thời. Một cấu hình hợp lệ cần giữ được giới hạn bộ nhớ, quota và thời gian xử lý trong điều kiện vận hành thực tế.

# UNKNOWN và lỗi không xác định

Trong gRPC, **`UNKNOWN` là status code số `2`**, dùng khi lỗi xảy ra nhưng không thể phân loại chính xác thành một status cụ thể hơn. Nó cho client biết RPC không hoàn tất thành công, nhưng bản thân mã này không chỉ ra nguyên nhân như request sai, thiếu quyền, server tạm thời không sẵn sàng hay dữ liệu bị hỏng.

Vì vậy, `UNKNOWN` thường là tín hiệu cần điều tra thêm. Khi phát triển **SPRING_GRPC**, server nên chuyển các lỗi nghiệp vụ đã biết thành status phù hợp; những lỗi bất ngờ cần được ghi log ở phía server và trả thông tin an toàn cho client. Client cần đọc status, metadata/trailers và correlation ID để tìm nguyên nhân, thay vì tự động retry mọi lỗi `UNKNOWN`.

## 1. Ý nghĩa của UNKNOWN

gRPC định nghĩa `UNKNOWN` với giá trị số **2**. Đây là trạng thái tổng quát cho lỗi chưa xác định hoặc không có đủ thông tin để ánh xạ sang mã cụ thể hơn. Trong gRPC Java, có thể tham chiếu bằng `io.grpc.Status.UNKNOWN`.

| Góc nhìn | Ý nghĩa |
| --- | --- |
| Client | RPC kết thúc bằng lỗi, nhưng status không xác định được nguyên nhân cụ thể |
| Server | Có lỗi không được phân loại hoặc chuyển đổi rõ ràng trước khi kết thúc RPC |
| gRPC runtime | Truyền status `UNKNOWN` về client theo cơ chế gRPC |
| Nghiệp vụ | Chưa thể kết luận thao tác đã thất bại hoàn toàn hay chưa; cần xem thêm ngữ cảnh |

`UNKNOWN` không đồng nghĩa với “không tìm thấy tài nguyên”. Trường hợp không tìm thấy thường dùng `NOT_FOUND`. Nó cũng không đồng nghĩa “server không chạy”; dịch vụ tạm thời không thể phục vụ thường được biểu diễn bằng `UNAVAILABLE`.

## 2. Vì sao một RPC có thể kết thúc với UNKNOWN?

Một số nguyên nhân thường gặp:

- Server phát sinh exception không được ánh xạ sang một gRPC status cụ thể.
- Một lớp tích hợp hoặc middleware chuyển tiếp exception nhưng làm mất thông tin phân loại ban đầu.
- Lỗi đến từ một hệ thống khác hoặc một tiến trình khác, nhưng thông tin nhận được không đủ để chọn status chính xác hơn.
- Một lỗi ngoài dự kiến xảy ra trong handler, adapter hoặc đoạn xử lý bất đồng bộ.
- Client nhận một throwable không chứa `StatusException`/`StatusRuntimeException` đã được gRPC nhận diện.

Ví dụ Order Service gọi Inventory Service để kiểm tra tồn kho. Trong handler, một lỗi lập trình bất ngờ xảy ra khi xử lý kết quả. Nếu lỗi không được phân loại và runtime/integration chuyển nó thành `UNKNOWN`, client chỉ biết RPC đã thất bại. Client không nên suy đoán rằng SKU sai hoặc database chắc chắn ngừng hoạt động.

**`UNKNOWN` mô tả mức độ hiểu biết về lỗi, không phải nguyên nhân gốc.** Muốn tìm nguyên nhân cần đối chiếu log server, trace, method, thời điểm, status và correlation ID.

## 3. Phân biệt UNKNOWN với các status gần nghĩa

Các status gRPC có semantics khác nhau. Chọn mã phù hợp giúp client biết nên sửa request, kiểm tra quyền, chờ thử lại hay điều tra server.

| Status | Giá trị | Khi nào phù hợp |
| --- | ---: | --- |
| `UNKNOWN` | 2 | Không đủ thông tin để phân loại lỗi cụ thể hơn |
| `INTERNAL` | 13 | Server gặp lỗi nội bộ nghiêm trọng hoặc trạng thái/invariant không mong đợi |
| `UNAVAILABLE` | 14 | Dịch vụ tạm thời không thể phục vụ; có thể liên quan kết nối hoặc quá tải |
| `DATA_LOSS` | 15 | Dữ liệu bị mất hoặc hỏng không thể khôi phục |
| `INVALID_ARGUMENT` | 3 | Request chứa tham số không hợp lệ |
| `NOT_FOUND` | 5 | Tài nguyên được yêu cầu không tồn tại |
| `FAILED_PRECONDITION` | 9 | Hệ thống chưa ở trạng thái cần thiết để thực hiện thao tác |
| `ABORTED` | 10 | Thao tác bị hủy do xung đột, ví dụ transaction conflict |
| `DEADLINE_EXCEEDED` | 4 | RPC không hoàn tất trước deadline |
| `CANCELLED` | 1 | RPC bị hủy, thường do caller |

### 3.1. UNKNOWN và INTERNAL

Dùng `INTERNAL` khi server biết đây là lỗi nội bộ, chẳng hạn invariant bị phá vỡ hoặc một lỗi triển khai khiến server không thể hoàn thành method. `UNKNOWN` phù hợp hơn khi thông tin lỗi không đủ để phân loại.

Không nên dùng `UNKNOWN` như một cách che mọi exception. Nếu đã biết lỗi thuộc loại nào, hãy trả status cụ thể. Ngược lại, không nên gắn `INTERNAL` cho một lỗi chỉ vì exception phát sinh trong server; ví dụ dữ liệu đầu vào sai phải được ánh xạ thành `INVALID_ARGUMENT`.

### 3.2. UNKNOWN và UNAVAILABLE

`UNAVAILABLE` thường cho biết service tạm thời không thể phục vụ hoặc client không thể thiết lập/duy trì kết nối theo cách cần thiết. Một số thao tác có thể retry sau backoff nếu an toàn.

`UNKNOWN` không khẳng định lỗi tạm thời. Retry tự động chỉ dựa vào mã này có thể lặp lại một thao tác ghi đã được thực hiện một phần hoặc đã commit.

### 3.3. UNKNOWN và DATA_LOSS

`DATA_LOSS` dành cho tình huống mất hoặc hỏng dữ liệu nghiêm trọng. Nếu server biết dữ liệu đã bị corruption, không nên hạ mức độ thành `UNKNOWN` chỉ để thông báo chung. `UNKNOWN` là thiếu khả năng phân loại; `DATA_LOSS` là một loại lỗi cụ thể và nghiêm trọng.

## 4. Ánh xạ exception ở server Spring gRPC

Trong ứng dụng Spring, lỗi có thể phát sinh ở nhiều lớp:

```text
gRPC handler
    |
    +-- validation / mapping request
    |
    +-- Spring business service
    |
    +-- repository / database / downstream
    |
    +-- exception mapping
    |
    +-- gRPC status + response trailers
```

Nên xác định ranh giới chuyển đổi exception thành status, thường ở adapter gRPC hoặc một cơ chế xử lý lỗi dùng chung của thư viện tích hợp. Các lỗi đã biết nên được ánh xạ rõ ràng:

| Loại lỗi trong ứng dụng | Status thường cân nhắc |
| --- | --- |
| Tham số không hợp lệ | `INVALID_ARGUMENT` |
| Không tìm thấy tài nguyên | `NOT_FOUND` |
| Chưa xác thực | `UNAUTHENTICATED` |
| Không có quyền | `PERMISSION_DENIED` |
| Xung đột cập nhật | `ABORTED` |
| Trạng thái nghiệp vụ chưa thỏa điều kiện | `FAILED_PRECONDITION` |
| Downstream tạm thời không sẵn sàng | `UNAVAILABLE` nếu đúng semantics |
| Lỗi nội bộ đã xác định | `INTERNAL` |
| Không phân loại được sau khi đã kiểm tra | `UNKNOWN` hoặc status tổng quát phù hợp với chính sách |

### 4.1. Ví dụ mapping trong handler

Đoạn code sau minh họa cách tách lỗi đầu vào, lỗi nghiệp vụ đã biết và lỗi bất ngờ:

```java
@Override
public void checkStock(
        CheckStockRequest request,
        StreamObserver<CheckStockReply> observer) {
    try {
        if (request.getSku().isBlank() || request.getQuantity() <= 0) {
            observer.onError(Status.INVALID_ARGUMENT
                .withDescription("SKU và quantity phải hợp lệ")
                .asRuntimeException());
            return;
        }

        int remaining = inventoryQuery.remaining(request.getSku());
        CheckStockReply reply = CheckStockReply.newBuilder()
            .setAvailable(remaining >= request.getQuantity())
            .setRemaining(remaining)
            .build();

        observer.onNext(reply);
        observer.onCompleted();
    } catch (InventoryNotFoundException ex) {
        observer.onError(Status.NOT_FOUND
            .withDescription("Không tìm thấy mặt hàng")
            .asRuntimeException());
    } catch (IllegalStateException ex) {
        log.error("Inventory state is invalid", ex);
        observer.onError(Status.INTERNAL
            .withDescription("Không thể hoàn tất yêu cầu")
            .asRuntimeException());
    } catch (Exception ex) {
        log.error("Unexpected error in CheckStock", ex);
        observer.onError(Status.UNKNOWN
            .withDescription("Đã xảy ra lỗi không xác định")
            .asRuntimeException());
    }
}
```

Ví dụ giả định `InventoryNotFoundException`, `inventoryQuery` và `log` đã được định nghĩa trong ứng dụng. Nó minh họa chính sách phân loại; một dự án có thể chọn `FAILED_PRECONDITION` hoặc status khác tùy contract. Với lỗi bất ngờ, log phía server giữ stack trace để điều tra, trong khi description trả client không tiết lộ SQL, tên bảng, đường dẫn nội bộ hay dữ liệu bí mật.

Trong một số gRPC Java server stack, exception không được xử lý có thể được chuyển thành `UNKNOWN` khi runtime chuyển throwable sang status. Không nên phụ thuộc vào hành vi mặc định đó: hãy chủ động mapping lỗi đã biết và kiểm thử chính xác status mà client nhận.

### 4.2. Không chuyển mọi exception thành UNKNOWN

Một `catch (Exception)` ở biên handler có thể là lớp bảo vệ cuối cùng để tránh lộ chi tiết lỗi. Nhưng nếu toàn bộ exception đều thành `UNKNOWN`, client mất khả năng phân biệt lỗi request, quyền, xung đột hay service unavailable.

Nên ưu tiên:

1. Giữ nguyên status đã được tạo có chủ đích, chẳng hạn `StatusRuntimeException` hoặc `StatusException`.
2. Ánh xạ exception nghiệp vụ đã biết sang status cụ thể.
3. Ghi log exception bất ngờ với method và correlation ID.
4. Chỉ dùng `UNKNOWN` làm fallback khi thực sự không có phân loại phù hợp.

## 5. Client Java đọc và chẩn đoán UNKNOWN

Với blocking stub, RPC kết thúc bằng status khác `OK` thường được thể hiện qua `StatusRuntimeException`:

```java
try {
    CheckStockReply reply = inventoryStub
        .withDeadlineAfter(400, TimeUnit.MILLISECONDS)
        .checkStock(request);

    // Xử lý response nghiệp vụ.
} catch (StatusRuntimeException ex) {
    Status.Code code = ex.getStatus().getCode();

    if (code == Status.Code.UNKNOWN) {
        log.warn("Inventory RPC returned UNKNOWN; requestId={}", requestId);
        // Tra cứu trace/log bằng requestId; không retry mù quáng.
    } else {
        // Xử lý status khác theo policy.
    }
}
```

Client nên ghi nhận tối thiểu:

- Service và method được gọi.
- gRPC status code.
- Deadline/call options áp dụng.
- Correlation ID hoặc trace ID không nhạy cảm.
- Endpoint/target và phiên bản client nếu cần điều tra tương thích.

Không ghi access token hoặc toàn bộ payload có dữ liệu nhạy cảm. Nếu status description có thông tin do server gửi, xem đó là dữ liệu phục vụ chẩn đoán chứ không phải thông tin đáng tin để quyết định quyền truy cập.

### 5.1. Khi throwable bị bọc nhiều lớp

Một lỗi có thể đi qua `CompletionException`, `ExecutionException` hoặc wrapper của framework. gRPC Java cung cấp `Status.fromThrowable(Throwable)` để tìm status trong chuỗi cause; nếu không tìm thấy status gRPC, kết quả thường là `UNKNOWN` kèm cause:

```java
Status status = Status.fromThrowable(error);

if (status.getCode() == Status.Code.UNKNOWN) {
    log.warn("No specific gRPC status found", error);
}
```

Điều này hữu ích khi xử lý callback hoặc future. Tuy nhiên, `UNKNOWN` từ `Status.fromThrowable` cũng có thể chỉ có nghĩa throwable ban đầu không mang status gRPC; nó không tự xác nhận server đã gửi một trailer `grpc-status = 2`. Khi cần biết status thực sự từ RPC, ưu tiên đọc `StatusRuntimeException`/`StatusException` mà client nhận được và giữ lại ngữ cảnh lỗi.

## 6. UNKNOWN không đủ để quyết định retry

Client không nên có quy tắc “gặp UNKNOWN thì retry ba lần”. Mã này không cho biết lỗi có tạm thời hay không và cũng không nói server đã thực hiện side effect đến đâu.

| Loại thao tác | Cách xử lý khi nhận `UNKNOWN` |
| --- | --- |
| Truy vấn đọc, không side effect | Có thể thử lại theo policy giới hạn nếu deadline còn và retry có ích; vẫn cần backoff |
| Thao tác ghi idempotent | Có thể retry cùng idempotency key theo contract |
| Thao tác ghi không idempotent | Không gửi lại mù quáng; tra cứu trạng thái hoặc yêu cầu xử lý đối soát |
| Streaming | Xác định message nào đã nhận, stream đã kết thúc ở đâu và có cursor/resume không |
| Lỗi lặp lại trên nhiều method | Điều tra server, dependency và rollout; không che bằng retry |

Ví dụ `ReserveStock` có thể đã commit database nhưng response bị mất. Client nhận `UNKNOWN` không chứng minh reservation chưa tồn tại. Cần `request_id`/idempotency key hoặc method tra cứu trạng thái trước khi quyết định gửi lại.

## 7. UNKNOWN trong streaming RPC

Với server streaming hoặc bidirectional streaming, client có thể nhận một số message trước khi stream kết thúc bằng `UNKNOWN`.

Ví dụ:

```text
Client nhận:
  StockUpdate(sequence=1)
  StockUpdate(sequence=2)

RPC kết thúc:
  grpc-status = 2
```

Hai update đã được gửi và nhận không tự biến mất, nhưng toàn bộ stream không hoàn tất thành công. Ứng dụng cần xác định semantics:

- Có thể áp dụng từng update ngay khi nhận hay phải chờ stream hoàn tất?
- Có sequence/cursor để biết điểm cuối đã xử lý?
- Khi reconnect có thể tiếp tục từ sequence cuối hay sẽ đọc lại?
- Consumer có idempotent nếu nhận trùng update không?

Đối với stream quan trọng, nên thiết kế cursor/sequence và quy tắc resume ở tầng ứng dụng. gRPC không tự lưu bền và phát lại toàn bộ message sau khi stream lỗi.

## 8. Quan sát và tìm nguyên nhân gốc

`UNKNOWN` là mã tổng quát, vì vậy log server và distributed tracing đặc biệt quan trọng. Khi status xuất hiện, cần đối chiếu:

| Dữ liệu quan sát | Mục đích |
| --- | --- |
| Service/method | Xác định RPC bị ảnh hưởng |
| Trace ID/correlation ID | Nối log client, server và downstream |
| Exception class và stack trace phía server | Xác định lỗi gốc khi status không đủ chi tiết |
| gRPC status và description | Xác định thông tin client thực nhận |
| Thời điểm, latency và deadline | Phân biệt lỗi tức thời với lỗi sau khi chờ lâu |
| Phiên bản ứng dụng/contract | Phát hiện rollout hoặc client-server version skew |
| Dependency health | Kiểm tra database, service khác, DNS, proxy và network |

Metrics nên đếm `UNKNOWN` theo service/method và theo dõi tỷ lệ theo thời gian. Không gắn exception message, request ID hoặc user ID có cardinality cao vào metric labels. Dùng logs/traces để điều tra từng trường hợp cụ thể.

Nếu `UNKNOWN` tăng đột ngột sau một lần deploy, hãy so sánh phiên bản server/client, thay đổi exception mapping, dependency và log cùng trace. Nếu chỉ một request cá biệt gặp lỗi, kiểm tra dữ liệu và đường đi của request đó trước khi kết luận có sự cố diện rộng.

## 9. Kiểm thử mapping UNKNOWN

Một bài test nên xác minh cả status client nhận được lẫn log/telemetry server:

| Kịch bản | Kết quả cần kiểm tra |
| --- | --- |
| Request sai định dạng/ngữ nghĩa | Server trả `INVALID_ARGUMENT`, không bị gom thành `UNKNOWN` |
| Tài nguyên không tồn tại | Status hoặc response đúng contract, ví dụ `NOT_FOUND` |
| Exception bất ngờ | Client nhận fallback đã định nghĩa; server log có stack trace và correlation |
| Exception đã mang gRPC status | Status gốc được giữ, không bị đổi thành `UNKNOWN` |
| Client nhận throwable bị bọc | `Status.fromThrowable` được dùng đúng, không nhầm fallback với trailer server |
| Streaming phát message rồi lỗi | Client biết stream kết thúc không thành công và xử lý cursor |
| Thao tác ghi bị mất response | Không retry tạo side effect trùng; tra cứu bằng idempotency key |

Unit test gọi trực tiếp handler có thể xác minh mapping. Integration test qua gRPC client/server xác nhận status được truyền đến client như mong đợi. Với Spring, có thể kiểm tra cả exception advice/interceptor hoặc cơ chế mapping của starter đang dùng.

## 10. Những lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách làm tốt hơn |
| --- | --- | --- |
| Dùng `UNKNOWN` cho mọi exception | Client không phân biệt được lỗi đã biết | Map lỗi nghiệp vụ và lỗi hạ tầng sang status cụ thể |
| Coi `UNKNOWN` luôn là lỗi tạm thời | Retry có thể nhân đôi side effect | Đánh giá method, idempotency và trạng thái server |
| Trả exception message/stack trace cho client | Có thể lộ cấu trúc nội bộ hoặc bí mật | Log đầy đủ phía server, trả description an toàn |
| Dựa vào status mà không có correlation ID | Khó nối log giữa client và server | Propagate trace/correlation metadata |
| Nhầm `Status.fromThrowable` fallback với status trailer thực | Chẩn đoán sai nguồn lỗi | Phân biệt throwable không mang status với status nhận từ RPC |
| Gom `UNKNOWN` vào `UNAVAILABLE` | Retry và alert sai | Giữ đúng semantics của từng status |
| Bỏ qua lỗi sau một phần stream | Dữ liệu đã nhận có thể bị xử lý không nhất quán | Dùng sequence/cursor và quy tắc resume |

## 11. Checklist xử lý UNKNOWN

Khi client nhận `UNKNOWN`, hãy kiểm tra theo thứ tự:

1. Xác định service/method, thời điểm, endpoint và correlation/trace ID.
2. Xác nhận `UNKNOWN` là status RPC nhận từ server hay fallback khi chuyển một throwable không mang gRPC status.
3. Tìm log server tương ứng để xác định exception gốc.
4. Kiểm tra exception mapping trong handler, interceptor, advice hoặc starter.
5. Xem dependency, database, proxy và phiên bản client/server quanh thời điểm lỗi.
6. Xác định server có thể đã thực hiện side effect hay chưa.
7. Chỉ retry nếu method an toàn, có idempotency hoặc đã xác định trạng thái.
8. Bổ sung test để lỗi đã biết không bị biến thành `UNKNOWN` và lỗi bất ngờ không làm lộ thông tin nhạy cảm.

## 12. Ghi nhớ

`UNKNOWN` là gRPC status code `2`, dùng cho lỗi không xác định hoặc không đủ thông tin để phân loại cụ thể hơn. Nó báo RPC thất bại nhưng không cho biết nguyên nhân gốc, không khẳng định lỗi tạm thời và không chứng minh server chưa thực hiện nghiệp vụ.

Trong Spring gRPC, hãy ánh xạ lỗi đã biết sang status cụ thể, ghi log exception bất ngờ ở server và trả mô tả an toàn cho client. Client nên kết hợp status với method, deadline, trace và correlation ID để điều tra. **Không retry `UNKNOWN` một cách mù quáng**, nhất là với thao tác ghi hoặc stream đã phát một phần dữ liệu. Khi giữ rõ ranh giới giữa exception, gRPC status và kết quả nghiệp vụ, hệ thống sẽ dễ chẩn đoán và đáng tin cậy hơn.

### Tài liệu tham khảo

- [gRPC – Status codes](https://grpc.io/docs/guides/status-codes/)
- [gRPC – Error handling](https://grpc.io/docs/guides/error/)
- [gRPC Java – Status](https://grpc.github.io/grpc-java/javadoc/io/grpc/Status.html)
- [gRPC Java – StatusRuntimeException](https://grpc.github.io/grpc-java/javadoc/io/grpc/StatusRuntimeException.html)
- [gRPC – Retry](https://grpc.io/docs/guides/retry/)
- [gRPC – Metadata](https://grpc.io/docs/guides/metadata/)

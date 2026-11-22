# OK và kết quả thành công

Trong gRPC, **`OK` là trạng thái cho biết một RPC đã hoàn tất thành công theo hợp đồng của method**. Đây là mã trạng thái số `0`. Tuy nhiên, `OK` không có nghĩa mọi điều kiện nghiệp vụ đều đúng như mong muốn của người dùng. Ví dụ, một lời gọi kiểm tra tồn kho có thể trả `available = false` nhưng vẫn kết thúc với `OK`, vì server đã kiểm tra thành công và trả lời rằng hàng không đủ.

Khi phát triển **SPRING_GRPC**, cần phân biệt kết quả ở ba lớp: giao tiếp/transport, trạng thái RPC và kết quả nghiệp vụ. Protocol Buffers định nghĩa message, gRPC quản lý vòng đời lời gọi và status, còn handler cùng Spring business service quyết định khi nào một thao tác được xem là thành công. Hiểu đúng `OK` giúp thiết kế response, xử lý lỗi, retry và quan sát dịch vụ nhất quán.

## 1. `OK` biểu thị điều gì?

gRPC định nghĩa một tập status code chuẩn. `OK` có giá trị số **0** và có ý nghĩa: **RPC hoàn tất thành công**. Trong gRPC Java, có thể tham chiếu trạng thái này qua `io.grpc.Status.OK`; phía client thường không cần tự đọc số `0`, vì stub thể hiện thành công bằng response hoặc callback hoàn tất.

| Góc nhìn | Khi RPC kết thúc với `OK` |
| --- | --- |
| Client | Lời gọi hoàn tất thành công theo giao thức gRPC; không có terminal RPC error |
| Server | Handler đã hoàn tất lời gọi theo cách thành công |
| Message | Với unary thông thường, client nhận response message; response có thể là message rỗng nếu contract quy định |
| Streaming | Luồng message kết thúc bình thường |
| Nghiệp vụ | Ý nghĩa do contract và ứng dụng quy định; không nhất thiết là “đã tìm thấy”, “đã đủ hàng” hoặc “đã chấp nhận” |

`OK` không phải một HTTP status code. Nó là **gRPC status code**, thường được truyền trong HTTP/2 trailers khi RPC kết thúc. Một gRPC response thông thường có thể dùng HTTP/2 `:status = 200` trong khi kết quả RPC được xác định bởi `grpc-status`.

## 2. Phân biệt thành công giao tiếp, thành công RPC và thành công nghiệp vụ

Ba khái niệm này có liên quan nhưng không thể thay thế cho nhau.

| Lớp | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Transport/HTTP2 | Kết nối và trao đổi frame có diễn ra đủ để gRPC xử lý không? | HTTP/2 stream được thiết lập và dữ liệu được truyền |
| RPC | Method có hoàn tất theo trạng thái gRPC thành công không? | Client nhận response và terminal status `OK` |
| Nghiệp vụ | Yêu cầu của người gọi có đạt điều kiện nghiệp vụ mong muốn không? | Kho có đủ hàng; thanh toán được chấp nhận; tài khoản có tồn tại |

Ví dụ, Order Service gọi Inventory Service:

```protobuf
message CheckStockRequest {
  string sku = 1;
  int32 quantity = 2;
}

message CheckStockReply {
  bool available = 1;
  int32 remaining = 2;
}
```

Nếu SKU hợp lệ nhưng chỉ còn một sản phẩm trong khi người mua yêu cầu hai, Inventory Service có thể trả:

```text
CheckStockReply:
  available = false
  remaining = 1

gRPC status:
  OK
```

Đây là một lần kiểm tra thành công: server hiểu request, truy vấn được dữ liệu và trả kết quả hợp lệ. `available = false` là **kết quả nghiệp vụ**, không phải lỗi giao tiếp.

Ngược lại, nếu request có `quantity = 0` trong khi hợp đồng yêu cầu số lượng dương, server có thể trả `INVALID_ARGUMENT`. Khi đó RPC thất bại vì request vi phạm điều kiện đầu vào, thay vì trả một kết quả kiểm tra bình thường.

## 3. `OK` được truyền về client như thế nào?

Trong gRPC qua HTTP/2, dữ liệu nghiệp vụ và trạng thái kết thúc RPC có vị trí khác nhau:

- **Response message** mang kết quả theo schema Protobuf.
- **gRPC status** cho biết RPC kết thúc thành công hay lỗi.
- **Trailers** thường mang `grpc-status` và có thể có `grpc-message` hoặc metadata kết thúc khác.

Một unary response thành công có thể được mô tả ở mức logic:

```text
HTTP/2 headers:
  :status = 200
  content-type = application/grpc

DATA:
  gRPC-framed CheckStockReply

HTTP/2 trailers:
  grpc-status = 0
```

Đây là biểu diễn dễ đọc, không phải bản dump byte HTTP/2. `grpc-status = 0` là `OK`. Client gRPC runtime đọc status này và trả response cho API stub tương ứng.

### Vì sao HTTP `200` chưa đủ để kết luận RPC thành công?

Với gRPC, HTTP status và gRPC status thuộc hai lớp khác nhau. Một RPC có thể có HTTP/2 `:status = 200` nhưng trailers chứa `grpc-status = 3` (`INVALID_ARGUMENT`) hoặc một mã lỗi khác. Vì vậy:

- Dùng gRPC client/stub để đánh giá kết quả RPC.
- Khi quan sát ở proxy hoặc log HTTP, xem cả gRPC trailers/status.
- Không coi HTTP `200` đơn lẻ là bằng chứng RPC thành công.

Trong trường hợp lỗi xảy ra trước khi gRPC server có thể tạo response thông thường, transport/proxy có thể trả HTTP status khác `200` hoặc reset stream. Client vẫn cần phân loại lỗi theo API gRPC mà nó nhận được.

## 4. Server Java/Spring kết thúc unary RPC bằng `OK`

Với gRPC Java API sinh từ Protobuf, một unary handler thường nhận request và `StreamObserver` để phát response:

```java
@Override
public void checkStock(
        CheckStockRequest request,
        StreamObserver<CheckStockReply> observer) {

    int remaining = inventoryQuery.remaining(request.getSku());

    CheckStockReply reply = CheckStockReply.newBuilder()
        .setAvailable(remaining >= request.getQuantity())
        .setRemaining(remaining)
        .build();

    observer.onNext(reply);
    observer.onCompleted();
}
```

Trong ví dụ:

1. Handler xử lý request và tạo một response message.
2. `onNext(reply)` phát response.
3. `onCompleted()` báo rằng RPC kết thúc bình thường.
4. gRPC runtime hoàn tất lời gọi với status `OK` nếu không có lỗi nào khác trong quá trình xử lý.

`onCompleted()` không phải một response message; nó là tín hiệu kết thúc luồng. Với unary, server chỉ phát một response. Nếu contract dùng `google.protobuf.Empty`, server vẫn có thể hoàn tất thành công mà không cần một payload nghiệp vụ có field.

### Không gọi cả `onError` và `onCompleted` cho cùng một RPC

Nếu validation thất bại, handler có thể kết thúc bằng lỗi:

```java
if (request.getQuantity() <= 0) {
    observer.onError(
        Status.INVALID_ARGUMENT
            .withDescription("quantity phải lớn hơn 0")
            .asRuntimeException());
    return;
}
```

Sau `onError(...)`, không gọi tiếp `onNext(...)` hoặc `onCompleted()` cho cùng observer. Một RPC chỉ có một terminal outcome: hoàn tất bình thường hoặc kết thúc bằng lỗi/hủy theo cơ chế gRPC.

Trong ứng dụng Spring, handler có thể inject bean nghiệp vụ như `InventoryQueryService`. Spring quản lý bean và dependency; gRPC runtime quản lý observer, dispatch và status. Quy tắc chọn trả `OK` hay status lỗi phải xuất phát từ contract và kết quả xử lý, không phải chỉ từ việc method Java không ném exception.

## 5. Client nhận biết thành công ra sao?

### 5.1. Blocking stub

Với unary blocking stub, nếu RPC hoàn tất với `OK`, lời gọi trả về response:

```java
CheckStockReply reply = inventoryStub
    .withDeadlineAfter(300, TimeUnit.MILLISECONDS)
    .checkStock(request);

if (reply.getAvailable()) {
    // Có đủ hàng theo kết quả server trả về.
} else {
    // RPC thành công, nhưng hàng không đủ.
}
```

Nếu RPC kết thúc với status khác `OK`, blocking stub thường ném `StatusRuntimeException`. Vì vậy, việc nhận được một response không đồng nghĩa mọi điều kiện nghiệp vụ đều đúng; client cần đọc các field response.

### 5.2. Async stub

Với asynchronous API, client nhận response qua `onNext` và tín hiệu kết thúc thành công qua `onCompleted`:

```java
stub.checkStock(request, new StreamObserver<>() {
    @Override
    public void onNext(CheckStockReply reply) {
        // Đọc kết quả nghiệp vụ.
    }

    @Override
    public void onError(Throwable error) {
        // RPC kết thúc bằng lỗi.
    }

    @Override
    public void onCompleted() {
        // Luồng response hoàn tất bình thường.
    }
});
```

Đối với unary, client thường nhận một `onNext` rồi `onCompleted`. Với streaming, `onNext` có thể được gọi nhiều lần trước khi kết thúc. Không nên dùng `onNext` như tín hiệu duy nhất chứng minh toàn bộ RPC đã thành công; terminal status mới cho biết kết quả cuối cùng.

## 6. `OK` trong các kiểu RPC

`OK` có cùng ý nghĩa tổng quát ở cả bốn cardinality: RPC kết thúc thành công. Tuy nhiên, cách diễn giải response khác nhau:

| Kiểu RPC | Trao đổi message | Khi nào được xem là hoàn tất `OK`? |
| --- | --- | --- |
| Unary | Một request, một response | Server trả response và kết thúc bình thường |
| Server streaming | Một request, nhiều response | Server gửi xong chuỗi response rồi kết thúc bình thường |
| Client streaming | Nhiều request, một response | Client kết thúc chiều gửi; server xử lý và trả response cuối thành công |
| Bidirectional streaming | Nhiều request và nhiều response | Hai phía hoàn tất trao đổi và RPC kết thúc bình thường |

### Server streaming: có message rồi vẫn có thể lỗi

Client có thể nhận một vài update rồi stream kết thúc bằng status khác `OK`, ví dụ `UNAVAILABLE`. Những message đã nhận không tự biến mất; nhưng toàn bộ RPC **không** được xem là hoàn tất thành công.

Do đó, với luồng dữ liệu quan trọng, client cần quyết định có thể dùng từng message ngay khi nhận hay chỉ chốt kết quả sau khi stream kết thúc `OK`. Quyết định phụ thuộc semantics của ứng dụng.

### Client streaming và bidirectional streaming

Với client streaming, việc client gửi xong request stream không có nghĩa server đã xử lý thành công. Client cần chờ response cuối và terminal status. Với bidirectional streaming, mỗi phía có thể tiếp tục gửi/nhận theo nhịp riêng; trạng thái cuối cùng chỉ được xác định khi RPC kết thúc.

## 7. Khi nào nên trả `OK`, khi nào nên trả status lỗi?

Hãy đặt câu hỏi: **server có thực hiện thành công thao tác mà method cam kết không?**

| Tình huống | Kết quả nên cân nhắc | Lý do |
| --- | --- | --- |
| Kiểm tra tồn kho thành công, còn đủ hàng | Response `available = true`, status `OK` | Request được xử lý thành công |
| Kiểm tra tồn kho thành công, không đủ hàng | Response `available = false`, status `OK` | Đây là kết quả nghiệp vụ hợp lệ |
| SKU không tồn tại | `NOT_FOUND` hoặc response “không tìm thấy” | Chọn theo contract và cách client cần xử lý |
| Quantity âm hoặc bằng 0 không hợp lệ | `INVALID_ARGUMENT` | Request vi phạm điều kiện đầu vào |
| Người gọi chưa xác thực | `UNAUTHENTICATED` | Không thể xác minh danh tính |
| Người gọi không có quyền | `PERMISSION_DENIED` | Danh tính có thể hợp lệ nhưng không được phép |
| Database tạm thời không sẵn sàng | `UNAVAILABLE` hoặc mapping phù hợp | Server không thể hoàn thành thao tác lúc này |
| Server xử lý thành công nhưng client mất response | Client có thể thấy lỗi transport; kết quả nghiệp vụ chưa rõ | Không được suy ra server chưa commit |

Không có quy tắc rằng mọi trường hợp “không tìm thấy” đều phải là lỗi. Nếu method được định nghĩa như phép tìm kiếm và “không có kết quả” là bình thường, response có thể biểu diễn trạng thái đó với `OK`. Nếu method yêu cầu một tài nguyên cụ thể phải tồn tại, `NOT_FOUND` có thể phù hợp hơn. **Contract cần quy định semantics nhất quán cho client.**

## 8. `OK` không đồng nghĩa thao tác ghi đã bền vững theo mọi nghĩa

Một server chỉ nên báo `OK` sau khi đã hoàn tất công việc mà contract cam kết. Với thao tác ghi, điều này thường có nghĩa transaction cần được commit trước khi handler báo hoàn tất thành công.

Ví dụ:

1. `ReserveStock` nhận request.
2. Server kiểm tra và cập nhật database.
3. Transaction commit thành công.
4. Handler trả response và kết thúc RPC với `OK`.

Nếu handler phát `OK` trước khi commit hoàn tất hoặc trước khi một tác vụ bất đồng bộ quan trọng được bảo đảm, client có thể hiểu thành công trong khi hệ thống chưa đạt cam kết đã công bố. Vì vậy, cần xác định rõ `OK` có nghĩa:

- Đã kiểm tra/đọc xong dữ liệu.
- Đã ghi và commit transaction.
- Đã chấp nhận tác vụ vào hàng đợi, nhưng chưa xử lý xong.
- Đã hoàn tất toàn bộ workflow.

Các semantics này khác nhau. Nếu API chỉ **chấp nhận** tác vụ chạy nền, response `OK` nên đi cùng một định danh tác vụ hoặc trạng thái `accepted`, không nên ngụ ý rằng workflow đã hoàn thành.

Ngay cả khi server đã commit và trả `OK`, client vẫn có thể không nhận được response do mạng đứt. Đây là lý do thao tác ghi có side effect cần idempotency key hoặc cách tra cứu kết quả sau timeout; `OK` không loại bỏ partial failure.

## 9. Những lỗi thiết kế thường gặp

| Cách hiểu sai | Cách hiểu đúng |
| --- | --- |
| `OK` nghĩa là hàng có sẵn hoặc thanh toán được chấp nhận | `OK` nghĩa RPC hoàn tất; field response mang kết quả nghiệp vụ |
| HTTP/2 `200` luôn có nghĩa gRPC thành công | Cần kiểm tra `grpc-status`, thường ở trailers |
| Server gọi `onNext` là RPC đã thành công | Cần terminal completion/status; streaming có thể phát message rồi kết thúc lỗi |
| `onCompleted()` là một response rỗng | Đây là tín hiệu kết thúc, không phải message response |
| Mọi trường hợp không đạt mong muốn đều trả lỗi gRPC | Kết quả nghiệp vụ hợp lệ có thể trả response với `OK` |
| Server không ném exception thì chắc chắn nên trả `OK` | Cần xác nhận method đã hoàn tất đúng cam kết nghiệp vụ |
| `OK` chứng minh client đã nhận response | Server có thể gửi xong nhưng response bị mất trên đường về |
| Có `OK` thì thao tác ghi không thể bị lặp | Client có thể timeout/mất response và gửi lại; cần idempotency |

## 10. Checklist thiết kế thành công cho một gRPC method

Trước khi công bố method, hãy trả lời:

1. **Thành công của method là gì?** Đọc xong, commit xong hay chỉ chấp nhận tác vụ?
2. **Kết quả nghiệp vụ bình thường gồm những trạng thái nào?** Trạng thái nào biểu diễn bằng field response?
3. **Điều kiện nào là RPC error?** Invalid argument, not found, quyền truy cập, unavailable hay internal?
4. **Server báo `OK` ở thời điểm nào?** Sau khi hoàn tất đúng cam kết của contract.
5. **Client đọc gì để quyết định?** Response fields, không chỉ dựa vào việc không có exception.
6. **Với streaming, terminal status được xử lý thế nào?** Message đã nhận có thể chưa đại diện cho toàn bộ luồng thành công.
7. **Nếu response bị mất sau commit thì sao?** Có idempotency hoặc cách tra cứu trạng thái không?
8. **Telemetry có phân biệt status và kết quả nghiệp vụ không?** Đo RPC success rate riêng với tỷ lệ nghiệp vụ như “đủ hàng”.

## 11. Ghi nhớ

`OK` là gRPC status code `0`, cho biết **RPC đã kết thúc thành công theo semantics của method**. Nó không tự nói rằng kết quả nghiệp vụ là tích cực. Một response `available = false` vẫn có thể đi cùng `OK`; một RPC trả `INVALID_ARGUMENT` là thất bại ở cấp RPC vì request không hợp lệ.

Trong Spring gRPC, handler quyết định response và status theo contract; gRPC runtime truyền status về client; client stub biểu diễn thành công bằng response hoặc callback hoàn tất. Hãy giữ riêng ba khái niệm **transport**, **RPC status** và **business outcome**. Khi chúng được thiết kế rõ ràng, client dễ xử lý, retry an toàn hơn và dashboard không nhầm “RPC chạy tốt” với “nghiệp vụ đạt kết quả mong muốn”.

### Tài liệu tham khảo

- [gRPC – Status codes](https://grpc.io/docs/guides/status-codes/)
- [gRPC – Core concepts, architecture and lifecycle](https://grpc.io/docs/what-is-grpc/core-concepts/)
- [gRPC – Java basics](https://grpc.io/docs/languages/java/basics/)
- [gRPC – Deadlines](https://grpc.io/docs/guides/deadlines/)
- [Protocol Buffers – Proto3 language guide](https://protobuf.dev/programming-guides/proto3/)

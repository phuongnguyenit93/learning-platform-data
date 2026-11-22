# Kết thúc stream đúng lifecycle

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Mô tả vòng đời của unary, server-streaming, client-streaming và bidirectional streaming RPC.
- Phân biệt kết thúc chiều gửi request với kết thúc toàn bộ RPC.
- Dùng đúng **onCompleted()**, **onError()** và cancellation theo vai trò của từng observer.
- Xác định thời điểm server được phép kết thúc response stream.
- Xử lý deadline, lỗi bất đồng bộ và client disconnect mà không rò rỉ tài nguyên.
- Kiểm thử lifecycle để bảo đảm mỗi chiều stream chỉ có một terminal event.

## 1. Lifecycle của một streaming RPC

Một gRPC call có thời điểm bắt đầu, giai đoạn trao đổi message và một kết quả cuối cùng. Với streaming RPC, mỗi chiều truyền có thể kết thúc ở thời điểm khác nhau. Vì vậy, cần phân biệt **đóng chiều gửi message** với **kết thúc RPC**.

Trong gRPC Java, **StreamObserver<T>** dùng ba callback:

- **onNext(value)**: gửi hoặc nhận một message khi chiều stream còn hoạt động.
- **onCompleted()**: kết thúc thành công chiều stream do observer đó đại diện.
- **onError(error)**: kết thúc chiều stream bằng lỗi.

Đối với observer mà ứng dụng dùng để gửi message, sau **onCompleted()** hoặc **onError()** không được gọi thêm **onNext()** hay terminal callback khác. Với observer do ứng dụng cung cấp để nhận response, gRPC gọi các callback nhận; ứng dụng cần xử lý chúng theo cùng thứ tự lifecycle và không coi chúng là API gửi dữ liệu.

## 2. Một RPC có thể có hai chiều lifecycle độc lập

Trong client-streaming và bidirectional streaming, client có thể hoàn tất việc gửi request trong khi vẫn chờ response từ server. Đây là **half-close**: client tuyên bố không gửi thêm request message, nhưng RPC vẫn có thể đang hoạt động.

Ví dụ:

~~~text
Client request direction:
onNext(chunk 1) -> onNext(chunk 2) -> onCompleted()

Server response direction:
onNext(progress) -> onNext(progress) -> onCompleted()
~~~

**onCompleted()** trên request observer của client chỉ đóng chiều client → server. Nó không có nghĩa server đã hoàn tất công việc hoặc client đã nhận response cuối cùng.

Tương tự, khi server nhận **onCompleted()** trên request observer, điều đó có nghĩa client đã gửi xong request stream. Server có thể tiếp tục xử lý dữ liệu đã nhận, gửi một hoặc nhiều response, rồi mới hoàn tất response observer.

## 3. Lifecycle của bốn kiểu RPC

| Kiểu RPC | Request | Response | Ý nghĩa kết thúc |
| --- | --- | --- | --- |
| **Unary** | Một message | Một message | Server gửi response rồi kết thúc thành công; hoặc call kết thúc bằng lỗi. |
| **Server-streaming** | Một message | Nhiều message | Server gửi hết response rồi hoàn tất chiều response. |
| **Client-streaming** | Nhiều message | Một message | Client half-close request; server xử lý xong rồi trả một response cuối. |
| **Bidirectional** | Nhiều message | Nhiều message | Hai phía gửi độc lập; mỗi chiều có thể kết thúc ở thời điểm khác nhau. |

Sự khác biệt quan trọng nhất nằm ở client-streaming và bidirectional: việc client gọi **requestObserver.onCompleted()** là tín hiệu hết request, không phải tín hiệu kết thúc response stream.

## 4. Unary và server-streaming: server hoàn tất response

Với unary RPC, server thường gửi đúng một response và sau đó gọi **onCompleted()**:

~~~java
@Override
public void getProfile(
        GetProfileRequest request,
        StreamObserver<Profile> responseObserver) {
    try {
        Profile profile = profileService.find(request.getUserId());
        responseObserver.onNext(profile);
        responseObserver.onCompleted();
    } catch (ProfileNotFoundException ex) {
        responseObserver.onError(
            Status.NOT_FOUND
                .withDescription("Profile not found")
                .asRuntimeException());
    }
}
~~~

Không gọi **onCompleted()** trong **finally**, vì nhánh catch có thể đã gọi **onError()**. Cần có đúng một đường kết thúc: thành công hoặc lỗi.

Với server-streaming, server gọi **onNext()** cho từng response. Chỉ gọi **onCompleted()** khi nguồn dữ liệu đã hoàn tất và không còn response nào đang chờ gửi. Nếu producer chạy bất đồng bộ, trạng thái hoàn tất phải được đồng bộ với queue và writer.

## 5. Client-streaming: request half-close trước response

Async stub trả về **StreamObserver<Request>** để client gửi nhiều request. Client gọi **onCompleted()** khi đã gửi xong:

~~~java
StreamObserver<UploadChunk> requestObserver =
    asyncStub.upload(new StreamObserver<UploadResult>() {
        @Override
        public void onNext(UploadResult result) {
            showUploadResult(result);
        }

        @Override
        public void onError(Throwable error) {
            showUploadFailure(error);
        }

        @Override
        public void onCompleted() {
            showUploadFinished();
        }
    });

requestObserver.onNext(firstChunk);
requestObserver.onNext(secondChunk);
requestObserver.onCompleted(); // Half-close request direction.
~~~

Sau khi client half-close, server mới biết không còn chunk nào đến nữa. Server có thể kiểm tra tính toàn vẹn, flush dữ liệu, ghi metadata cuối cùng và tạo **UploadResult**. Response observer của client sẽ nhận **onNext(result)** rồi **onCompleted()** nếu thành công.

Không chờ response cuối trước khi half-close nếu server chỉ trả kết quả sau khi nhận hết input; hai phía khi đó có thể chờ nhau vô hạn cho tới khi deadline hết hạn.

## 6. Bidirectional streaming: hai chiều kết thúc độc lập

Với bidi streaming, client có thể tiếp tục nhận response sau khi đã gọi **onCompleted()** trên request observer. Ví dụ client gửi lệnh đăng ký, nhận cập nhật, rồi half-close khi không cần gửi lệnh mới:

~~~text
Client -> Server: subscribe
Server -> Client: update 1
Client -> Server: filter change
Server -> Client: update 2
Client -> Server: onCompleted()  (không gửi request mới nữa)
Server -> Client: update 3
Server -> Client: onCompleted()  (response stream kết thúc)
~~~

Server không nên kết thúc response chỉ vì request stream đã half-close, trừ khi hợp đồng nghiệp vụ quy định rõ việc đó. Có thể còn dữ liệu đang xử lý hoặc response đã được lên lịch.

Ngược lại, server có thể kết thúc response trước khi client đóng request stream nếu RPC đã hoàn tất hoặc server quyết định dừng call. Client phải ngừng gửi khi nhận terminal result hoặc cancellation; không tiếp tục phát request trên call đã kết thúc.

## 7. onCompleted và onError là terminal event

Mỗi chiều stream chỉ có một kết quả kết thúc:

| Kết quả | Callback | Ý nghĩa |
| --- | --- | --- |
| Thành công | **onCompleted()** | Không còn message nào trong chiều stream đó. |
| Thất bại | **onError(Throwable)** | Chiều stream kết thúc bằng lỗi; status gRPC cho biết nguyên nhân ở phía nhận. |

Không gọi cả hai để “đảm bảo” kết thúc. Không gọi **onNext()** sau terminal event. Với server response observer, **onError()** thường mang một **StatusRuntimeException** hoặc lỗi được ánh xạ sang status phù hợp.

Một lỗi xuất hiện sau khi đã gửi **onCompleted()** không thể đổi kết quả RPC thành thất bại. Ghi nhận lỗi muộn bằng log/metric hoặc xử lý ở workflow riêng; không phát terminal callback thứ hai.

## 8. Client cancel và deadline không phải onCompleted

**Cancellation** xảy ra khi client chủ động hủy call, channel đóng hoặc call bị hủy bởi cơ chế runtime. **Deadline exceeded** xảy ra khi thời hạn RPC hết trước khi hoàn tất. Đây không phải kết thúc thành công.

Ở server, có thể nhận biết call bị hủy bằng **ServerCallStreamObserver.setOnCancelHandler(...)**:

~~~java
ServerCallStreamObserver<Update> call =
    (ServerCallStreamObserver<Update>) responseObserver;

call.setOnCancelHandler(() -> {
    stopUpstreamSubscription();
    cancelPendingWork();
    releaseResources();
});
~~~

Cancellation handler nên phát tín hiệu dừng và trả về nhanh. Không chặn callback này bằng thao tác I/O kéo dài. Cleanup cần an toàn khi nhiều nguyên nhân kết thúc xảy ra gần nhau, chẳng hạn client cancel đồng thời worker phát hiện lỗi.

Không cố gửi thêm **onCompleted()** hoặc **onError()** để phản hồi một call đã bị hủy. Transport đã quản lý kết quả cancellation; ứng dụng cần dừng producer và giải phóng tài nguyên.

## 9. Quản lý tài nguyên theo lifecycle

Một streaming RPC dài hạn có thể giữ database cursor, subscription, file handle, queue, executor task hoặc semaphore permit. Mọi tài nguyên cần được gắn với lifecycle của call:

1. **Khi bắt đầu**: tạo tài nguyên và đăng ký cancellation handler.
2. **Trong khi chạy**: kiểm tra call còn hoạt động trước khi tiếp tục công việc tốn kém.
3. **Khi request half-close**: ngừng nhận input mới, nhưng xử lý nốt dữ liệu đã nhận.
4. **Khi hoàn tất thành công hoặc lỗi**: dừng producer và giải phóng tài nguyên.
5. **Khi cancel/deadline**: hủy upstream, dừng worker và xóa queue còn chờ theo chính sách.

Nên gom cleanup vào một hàm idempotent, có thể gọi nhiều lần nhưng chỉ giải phóng mỗi tài nguyên một lần. Điều này tránh rò rỉ khi cancellation và terminal callback đến gần như đồng thời.

## 10. Tuần tự hóa kết thúc khi có nhiều worker

Một producer bất đồng bộ có thể tạo response từ nhiều thread. Nếu worker A gọi **onCompleted()** trong lúc worker B vẫn chuẩn bị **onNext()**, có thể xảy ra message được gửi sau terminal event.

Không chỉ dùng một boolean rồi kiểm tra riêng:

~~~java
if (!terminated.get()) {
    responseObserver.onNext(update);
}
~~~

Worker khác có thể đặt **terminated = true** và gọi **onCompleted()** sau khi kiểm tra kết thúc nhưng trước khi **onNext()** thực thi. Cần tuần tự hóa cả kiểm tra trạng thái lẫn callback:

- Dùng một serial executor làm nơi duy nhất gọi observer.
- Hoặc dùng một emitter có lock bao trùm thao tác kiểm tra và phát callback.
- Mọi producer chỉ enqueue message hoặc yêu cầu terminal event; không gọi observer trực tiếp.
- Chỉ writer sở hữu quyền phát **onNext**, **onError** và **onCompleted**.

Với server-streaming có readiness, writer còn phải kiểm tra **isReady()** và dừng drain khi không sẵn sàng. Khi producer hoàn tất, chỉ phát **onCompleted()** sau khi queue rỗng và không còn message đang gửi.

## 11. Mẫu client-streaming server kết thúc đúng lúc

Server nhận nhiều chunk và chỉ trả kết quả sau khi client half-close:

~~~java
@Override
public StreamObserver<UploadChunk> upload(
        StreamObserver<UploadResult> responseObserver) {

    UploadSession session = uploadService.openSession();

    return new StreamObserver<>() {
        private boolean finished;

        @Override
        public void onNext(UploadChunk chunk) {
            if (finished) {
                return;
            }
            session.accept(chunk);
        }

        @Override
        public void onError(Throwable error) {
            if (finished) {
                return;
            }
            finished = true;
            session.abort();
        }

        @Override
        public void onCompleted() {
            if (finished) {
                return;
            }
            finished = true;
            try {
                UploadResult result = session.finish();
                responseObserver.onNext(result);
                responseObserver.onCompleted();
            } catch (RuntimeException ex) {
                responseObserver.onError(
                    Status.INTERNAL
                        .withDescription("Upload finalization failed")
                        .withCause(ex)
                        .asRuntimeException());
            } finally {
                session.close();
            }
        }
    };
}
~~~

Đây là skeleton cho một handler tuần tự. Nếu callback có thể được gọi từ nhiều thread hoặc **session.finish()** chạy bất đồng bộ, trạng thái **finished** và việc phát response cần được bảo vệ bằng serial executor/đồng bộ thích hợp. Trong hệ thống thực tế, cancellation cũng phải được nối với **session.abort()** và **session.close()**.

Điểm cốt lõi: **onCompleted()** của request observer là lúc server biết input đã hết. Nó không phải terminal event của response observer; server vẫn cần gửi response cuối và kết thúc response riêng.

## 12. Kiểm thử lifecycle của streaming RPC

Các ca kiểm thử quan trọng:

1. Unary thành công: một response rồi terminal success.
2. Unary lỗi: không có response sau terminal error.
3. Server-streaming: nhận đủ message theo thứ tự rồi **onCompleted()**.
4. Client-streaming: client half-close, server xử lý hết input rồi trả response cuối.
5. Bidirectional: client half-close nhưng vẫn nhận response cho dữ liệu đã gửi.
6. Client cancel giữa stream: server dừng producer và giải phóng subscription/queue.
7. Deadline hết hạn: worker dừng và không phát message tiếp.
8. Worker lỗi đồng thời với cancellation: chỉ một cleanup path có hiệu lực và không có terminal callback lặp.
9. Producer bất đồng bộ hoàn tất trong khi queue còn message: server drain hết trước khi complete.

Khi kiểm thử, không chỉ xác nhận client nhận đúng dữ liệu. Hãy kiểm tra cả việc upstream subscription bị hủy, queue được giải phóng, executor task dừng và observer không nhận callback sau terminal event.

## 13. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Coi request **onCompleted()** là kết thúc toàn RPC | Server/client dừng quá sớm, mất response cuối | Xem đây là half-close của chiều request. |
| Server complete response ngay khi nhận hết request | Bỏ qua công việc bất đồng bộ còn chờ | Chờ xử lý xong và drain response queue. |
| Gọi **onCompleted()** trong **finally** | Có thể gọi sau **onError()** | Chọn một terminal path duy nhất. |
| Gửi **onNext()** sau terminal event | Vi phạm lifecycle observer | Tuần tự hóa trạng thái và callback. |
| Coi cancellation là hoàn tất thành công | Báo sai kết quả và tiếp tục xử lý | Dừng producer, cleanup và không gửi terminal thừa. |
| Không xử lý deadline | RPC giữ tài nguyên quá lâu | Propagate deadline/cancellation tới upstream work. |
| Chỉ cleanup ở nhánh thành công | Rò rỉ tài nguyên khi lỗi hoặc cancel | Dùng cleanup idempotent cho mọi đường kết thúc. |
| Nhiều worker cùng phát response | Race, sai thứ tự hoặc terminal event lặp | Một serial writer cho mỗi observer. |

## 14. Bài tập thực hành

Thiết kế client-streaming RPC nhận các bản ghi và trả tổng số bản ghi hợp lệ:

1. Client gửi nhiều record qua request observer.
2. Client gọi **onCompleted()** khi không còn record; giải thích vì sao đây chỉ là half-close.
3. Server tiếp tục validate và lưu các record đã nhận.
4. Sau khi hoàn tất xử lý, server gửi một **UploadSummary** rồi gọi response **onCompleted()**.
5. Nếu validation lỗi nghiêm trọng, server kết thúc response bằng **onError()** và không gọi **onCompleted()**.
6. Thêm cancellation handler để dừng ghi dữ liệu và đóng session.
7. Viết test cho client half-close, server response cuối, lỗi giữa stream và cancellation.

**Tiêu chí hoàn thành:** phân biệt được lifecycle hai chiều, kết thúc đúng một lần, không mất response cuối và giải phóng tài nguyên ở mọi đường kết thúc.

## 15. Ghi nhớ

- Một streaming RPC có thể có hai chiều gửi/nhận với thời điểm kết thúc khác nhau.
- **onCompleted()** trên request observer của client là half-close request direction; server vẫn có thể gửi response.
- **onCompleted()** trên response observer kết thúc response thành công; **onError()** kết thúc bằng lỗi.
- Không gọi **onNext()** hoặc terminal callback khác sau terminal event.
- Cancellation và deadline không phải thành công; chúng phải dừng producer và kích hoạt cleanup.
- Với xử lý bất đồng bộ, dùng một cổng phát tuần tự và cleanup idempotent.
- Kiểm thử cả half-close, terminal result, cancellation, deadline và tài nguyên nền.

Quản lý đúng lifecycle giúp dịch vụ Spring gRPC kết thúc từng chiều streaming đúng thời điểm, bảo toàn response cuối, tránh callback sau terminal event và giải phóng tài nguyên khi RPC thành công, thất bại hoặc bị hủy.

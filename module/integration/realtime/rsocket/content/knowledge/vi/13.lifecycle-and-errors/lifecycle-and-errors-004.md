# Các mã lỗi tiêu biểu: APPLICATION_ERROR, REJECTED, CANCELED, INVALID

RSocket dùng frame ERROR để thông báo một tương tác không thể tiếp tục bình thường. Mỗi ERROR mang một mã lỗi và thông tin mô tả. Mã lỗi giúp bên nhận phân biệt nguyên nhân ở cấp giao thức hoặc ứng dụng, từ đó quyết định hiển thị lỗi, ghi log, thử lại hay dừng xử lý.

Trong nhóm lỗi ở cấp ứng dụng, bốn mã thường gặp là APPLICATION_ERROR, REJECTED, CANCELED và INVALID. Chúng đều có thể kết thúc một stream, nhưng ý nghĩa khác nhau: lỗi khi xử lý nghiệp vụ, từ chối nhận yêu cầu, hủy yêu cầu và yêu cầu không hợp lệ. Chọn đúng mã giúp client xử lý nhất quán và giúp đội vận hành phân tích lỗi chính xác hơn.

## 1. Mã lỗi và phạm vi ảnh hưởng

RSocket phân biệt lỗi ở cấp stream với lỗi ở cấp connection. Lỗi stream kết thúc một tương tác cụ thể; những stream khác trên cùng connection có thể tiếp tục. Lỗi connection làm phiên giao tiếp không thể tiếp tục và ảnh hưởng tới các stream đang dùng connection đó.

ERROR frame ở cấp stream được gắn với stream ID tương ứng. ERROR frame ở cấp connection sử dụng stream ID bằng 0. Bốn mã trong bài thuộc nhóm lỗi ứng dụng ở cấp stream:

| Mã lỗi | Giá trị hexadecimal | Ý nghĩa khái quát |
| --- | --- | --- |
| APPLICATION_ERROR | <code>0x00000201</code> | Ứng dụng gặp lỗi khi xử lý tương tác. |
| REJECTED | <code>0x00000202</code> | Bên nhận từ chối yêu cầu. |
| CANCELED | <code>0x00000203</code> | Tương tác bị hủy và được báo bằng ERROR. |
| INVALID | <code>0x00000204</code> | Yêu cầu không hợp lệ. |

Các mã này không phải HTTP status code. Ví dụ, không nên ánh xạ máy móc REJECTED thành HTTP 429 hoặc INVALID thành HTTP 400 nếu chưa xét ngữ nghĩa nghiệp vụ và chính sách của hệ thống.

Một số mã khác thuộc phạm vi connection, chẳng hạn CONNECTION_ERROR và CONNECTION_CLOSE. Khi nhận lỗi connection, client cần xử lý vòng đời session và các stream bị ảnh hưởng; khi nhận lỗi stream, client thường chỉ cần xử lý tương tác tương ứng.

## 2. APPLICATION_ERROR — lỗi trong quá trình xử lý ứng dụng

APPLICATION_ERROR biểu thị một lỗi ở tầng ứng dụng khiến tương tác hiện tại không thể hoàn tất bình thường. Nguyên nhân có thể là lỗi nghiệp vụ, exception không dự kiến, lỗi khi gọi dependency hoặc một điều kiện xử lý thất bại mà ứng dụng muốn thông báo cho peer.

Ví dụ:

- Service đọc dữ liệu gặp lỗi cơ sở dữ liệu.
- Một bước tính toán nghiệp vụ phát sinh exception.
- Dịch vụ phụ thuộc trả về lỗi và ứng dụng không có phương án dự phòng.
- Một tác vụ xử lý dữ liệu realtime thất bại sau khi stream đã bắt đầu.

APPLICATION_ERROR là mã tổng quát. Nếu ứng dụng có nhiều loại lỗi nghiệp vụ, nên đưa một mã lỗi miền ổn định vào nội dung mô tả hoặc payload lỗi theo hợp đồng riêng. Không nên phụ thuộc vào stack trace hoặc câu chữ exception nội bộ vì chúng có thể thay đổi theo phiên bản triển khai.

Ví dụ một handler trả về lỗi khi service không thể xử lý:

~~~java
@MessageMapping("reports.generate")
public Mono<Report> generate(ReportRequest request) {
    return reportService.generate(request)
        .doOnError(error ->
            log.error("Không thể tạo report {}", request.reportId(), error));
}
~~~

Khi Publisher trả về kết thúc bằng lỗi, framework RSocket chuyển lỗi đó thành ERROR frame theo quy tắc ánh xạ lỗi của thư viện và ứng dụng. Cần cấu hình hoặc kiểm thử lớp ánh xạ nếu muốn bảo đảm exception miền cụ thể được truyền thành mã APPLICATION_ERROR. Không nên giả định mọi exception Java đều tự động có cùng mã trên dây ở mọi phiên bản framework.

Ở client, APPLICATION_ERROR thường cần được phân loại theo nguyên nhân. Lỗi nghiệp vụ vĩnh viễn không nên retry; lỗi dependency tạm thời có thể retry nếu thao tác an toàn và còn trong ngân sách thời gian.

## 3. REJECTED — yêu cầu bị từ chối

REJECTED biểu thị bên nhận không chấp nhận xử lý yêu cầu. Việc từ chối có thể xuất phát từ chính sách, quyền truy cập, tình trạng tài nguyên hoặc điều kiện vận hành.

Ví dụ:

- Server đang quá tải và không nhận thêm stream mới.
- Client không được phép sử dụng chức năng được yêu cầu.
- Một tenant đã vượt giới hạn tài nguyên được cấp.
- Hệ thống từ chối một yêu cầu theo chính sách nghiệp vụ.

REJECTED không nhất thiết có nghĩa payload sai định dạng. Một yêu cầu có thể hợp lệ về cấu trúc nhưng server vẫn từ chối vì không đủ quyền hoặc không đủ tài nguyên. Đây là điểm khác với INVALID.

Khi từ chối do tải tạm thời, server có thể cung cấp thông tin retry phù hợp trong hợp đồng ứng dụng, chẳng hạn thời gian chờ đề xuất. Client chỉ nên retry sau backoff và khi biết yêu cầu có thể được chấp nhận sau đó. Nếu bị từ chối vì quyền truy cập hoặc chính sách cố định, retry liên tục không giúp ích và có thể làm tăng tải.

Ví dụ kiểm tra điều kiện trước khi mở stream:

~~~java
@MessageMapping("telemetry.watch")
public Flux<Telemetry> watch(WatchRequest request) {
    if (!capacityManager.canOpenStream(request.deviceId())) {
        return Flux.error(
            new StreamCapacityRejectedException("Không đủ capacity")
        );
    }

    return telemetryService.watch(request.deviceId());
}
~~~

Đây là exception miền minh họa. Lớp tích hợp RSocket cần ánh xạ nó sang REJECTED nếu đó là hợp đồng đã chọn. Việc chỉ trả về một exception Java không bảo đảm mã giao thức sẽ là REJECTED nếu chưa cấu hình hoặc xác nhận mapping.

Không nên tiết lộ chi tiết nội bộ trong thông báo từ chối. Ví dụ, thay vì trả thông tin về tên node hoặc trạng thái cluster, hãy trả một lý do công khai như <code>RESOURCE_LIMIT</code> hoặc <code>ACCESS_DENIED</code> theo hợp đồng ứng dụng.

## 4. CANCELED — tương tác bị hủy

CANCELED biểu thị một tương tác bị hủy và được báo bằng ERROR frame. Cần phân biệt mã lỗi CANCELED với frame điều khiển CANCEL:

| Thành phần | Vai trò |
| --- | --- |
| CANCEL frame | Requester chủ động thông báo không còn cần stream đang hoạt động. |
| CANCELED error code | Một bên kết thúc tương tác bằng ERROR để biểu đạt rằng yêu cầu đã bị hủy. |

Trong trường hợp thông thường, khi người dùng rời màn hình và client không còn muốn nhận dữ liệu, client dispose subscription. RSocket gửi CANCEL cho stream tương ứng; server nhận cancellation và nên dừng công việc liên quan. Không cần gửi thêm ERROR với mã CANCELED chỉ để xác nhận CANCEL.

CANCELED hữu ích khi tầng ứng dụng cần biểu đạt một yêu cầu đã bị hủy theo chính sách, ví dụ tác vụ bị hủy do hết thời gian chờ hoặc do một quy trình quản lý tác vụ quyết định dừng. Nếu client đã nhận CANCELED, nó nên kết thúc xử lý stream đó và giải phóng tài nguyên.

Ví dụ quan sát cancellation trong Reactor:

~~~java
@MessageMapping("jobs.progress")
public Flux<JobProgress> progress(JobRequest request) {
    return jobService.progress(request.jobId())
        .doOnCancel(() ->
            log.info("Client đã hủy theo dõi job {}", request.jobId()))
        .doFinally(signal ->
            log.debug("Job stream kết thúc với signal {}", signal));
}
~~~

<code>doOnCancel</code> quan sát việc upstream bị hủy. <code>doFinally</code> quan sát các kiểu kết thúc như complete, error hoặc cancel. Khi nguồn có listener, subscription tới broker hoặc tác vụ nền, cần gắn logic cleanup vào vòng đời Publisher để tài nguyên được giải phóng khi cancellation lan truyền.

Không nên retry tự động một tương tác chỉ vì nhận CANCELED. Trước tiên cần xác định ai hủy, lý do hủy và liệu người dùng hoặc quy trình nghiệp vụ có còn muốn tiếp tục hay không.

## 5. INVALID — yêu cầu không hợp lệ

INVALID biểu thị yêu cầu không hợp lệ về cấu trúc, định dạng hoặc ngữ nghĩa giao thức/ứng dụng. Server không thể xử lý yêu cầu theo hợp đồng hiện tại.

Ví dụ:

- Payload không giải mã được theo data MIME type đã thỏa thuận.
- Trường bắt buộc bị thiếu hoặc có kiểu dữ liệu không đúng.
- Giá trị tham số nằm ngoài miền hợp lệ.
- Metadata bắt buộc bị thiếu hoặc không đúng định dạng.
- Client gửi một dạng yêu cầu mà endpoint không hỗ trợ.

Không phải mọi lỗi nghiệp vụ đều là INVALID. Ví dụ, mã đơn hàng có định dạng đúng nhưng không tồn tại có thể được biểu diễn bằng lỗi miền như NOT_FOUND; payload thiếu trường hoặc mã có định dạng sai mới là trường hợp phù hợp hơn với INVALID.

Ví dụ kiểm tra dữ liệu trước khi gọi service:

~~~java
@MessageMapping("orders.find")
public Mono<OrderView> find(OrderQuery query) {
    if (query == null || query.orderId() == null
            || query.orderId().isBlank()) {
        return Mono.error(
            new InvalidRequestException("orderId là bắt buộc")
        );
    }

    return orderService.find(query.orderId());
}
~~~

<code>InvalidRequestException</code> là exception miền minh họa. Lớp tích hợp cần ánh xạ lỗi xác thực đầu vào này thành INVALID theo hợp đồng RSocket của ứng dụng. Với dữ liệu JSON hoặc Protobuf, lỗi giải mã có thể xảy ra trước khi method handler được gọi; khi đó cần xử lý ở tầng codec hoặc error mapping của framework.

INVALID thường là lỗi không thể khắc phục bằng retry nguyên trạng. Client cần sửa payload, metadata hoặc phiên bản contract trước khi gửi lại.

## 6. So sánh bốn mã lỗi

| Mã | Câu hỏi chẩn đoán | Nguyên nhân thường gặp | Hướng xử lý phía client |
| --- | --- | --- | --- |
| APPLICATION_ERROR | Ứng dụng gặp lỗi gì khi xử lý? | Exception nghiệp vụ hoặc dependency thất bại. | Phân loại nguyên nhân; chỉ retry lỗi tạm thời và thao tác an toàn. |
| REJECTED | Vì sao server không nhận yêu cầu? | Capacity, quyền truy cập hoặc chính sách. | Tôn trọng chính sách; backoff nếu từ chối tạm thời. |
| CANCELED | Ai hoặc điều kiện nào đã hủy tương tác? | Người dùng dừng, timeout hoặc quy trình hủy tác vụ. | Dừng stream và giải phóng tài nguyên; chỉ mở lại khi có nhu cầu mới. |
| INVALID | Thành phần nào của request không hợp lệ? | Payload, metadata hoặc tham số sai hợp đồng. | Sửa request; không retry nguyên trạng. |

Một cách nhớ ngắn:

- APPLICATION_ERROR: đã nhận xử lý nhưng gặp lỗi.
- REJECTED: không chấp nhận xử lý.
- CANCELED: tương tác bị hủy.
- INVALID: request không hợp lệ.

## 7. Phân biệt lỗi stream và lỗi connection

Một lỗi stream chỉ kết thúc tương tác mang stream ID tương ứng. Ví dụ, client theo dõi ba thiết bị trên ba request-stream; một stream nhận INVALID do mã thiết bị sai không nhất thiết làm hai stream còn lại dừng.

Lỗi connection có phạm vi lớn hơn. Khi connection kết thúc, các stream đang chạy trên connection đó đều bị ảnh hưởng và client cần xem xét reconnect. Các mã CONNECTION_ERROR và CONNECTION_CLOSE thuộc nhóm connection-level; chúng khác với bốn mã ứng dụng trong bài.

| Tiêu chí | Lỗi stream | Lỗi connection |
| --- | --- | --- |
| Phạm vi | Một tương tác | Toàn bộ RSocket session/connection |
| Stream ID trong ERROR | ID khác 0 | 0 |
| Stream khác trên connection | Có thể tiếp tục | Bị ảnh hưởng bởi connection đóng |
| Hành động thường gặp | Xử lý lỗi request, có thể đăng ký stream mới | Reconnect và phục hồi các tương tác cần thiết |

Không nên reconnect toàn bộ connection chỉ vì một stream trả APPLICATION_ERROR, REJECTED, CANCELED hoặc INVALID. Trước tiên hãy xác định phạm vi ERROR và trạng thái session.

## 8. Xây dựng chính sách ánh xạ lỗi ở server

Ứng dụng nên có một lớp phân loại lỗi miền trước khi chuyển thành lỗi giao thức. Điều này giúp controller không phải tự quyết định mã RSocket ở mọi method và tránh việc vô tình gửi exception nội bộ ra ngoài.

Ví dụ bảng ánh xạ ở tầng ứng dụng:

| Exception miền | Mã RSocket dự kiến | Lý do |
| --- | --- | --- |
| <code>InvalidRequestException</code> | INVALID | Dữ liệu đầu vào không đáp ứng hợp đồng. |
| <code>StreamCapacityRejectedException</code> | REJECTED | Server chưa thể nhận thêm stream. |
| <code>JobCanceledException</code> | CANCELED | Tác vụ đã bị hủy theo chính sách. |
| Exception xử lý không dự kiến | APPLICATION_ERROR | Lỗi ứng dụng chưa có mã chuyên biệt. |

Đây là chính sách ví dụ, không phải ánh xạ bắt buộc của mọi framework. Cùng một exception có thể cần mã khác tùy ngữ cảnh. Chẳng hạn, lỗi quyền truy cập có thể được biểu diễn bằng REJECTED; lỗi xác thực ở bước SETUP có thể dùng mã setup-level thay vì mã stream-level.

Một bộ phân loại nên:

1. Nhận diện các lỗi đầu vào có thể công khai an toàn.
2. Phân biệt từ chối do quyền, capacity và chính sách.
3. Nhận diện cancellation để không ghi nhận như lỗi ứng dụng thông thường.
4. Chuyển lỗi chưa phân loại thành APPLICATION_ERROR.
5. Ghi log đầy đủ ở server nhưng chỉ trả thông báo an toàn cho client.

Không nên bắt mọi exception rồi chuyển thành REJECTED hoặc INVALID. Việc đó làm mất thông tin quan trọng và khiến client áp dụng sai chính sách retry.

## 9. Xử lý lỗi ở client bằng Reactor

Ở phía client, lỗi RSocket thường xuất hiện dưới dạng terminal error của <code>Mono</code> hoặc <code>Flux</code>. Có thể dùng <code>doOnError</code> để quan sát, <code>onErrorMap</code> để chuẩn hóa lỗi và <code>onErrorResume</code> để chọn luồng dự phòng.

Ví dụ xử lý một request-response:

~~~java
Mono<OrderView> result = requester
    .route("orders.find")
    .data(new OrderQuery("ORD-2026-018"))
    .retrieveMono(OrderView.class)
    .doOnError(error ->
        log.warn("Request orders.find failed", error))
    .onErrorResume(this::isKnownMissingOrder, error -> Mono.empty());
~~~

Ví dụ trên minh họa cách phục hồi một lỗi miền đã được nhận diện. Trong ứng dụng thật, hãy phân biệt lỗi không tìm thấy với INVALID hoặc lỗi transport; không nên biến mọi lỗi thành kết quả rỗng vì như vậy sẽ che giấu lỗi giao thức và lỗi vận hành.

Với retry, chỉ áp dụng cho loại lỗi có khả năng tạm thời và thao tác có thể lặp lại an toàn:

~~~java
Flux<PriceUpdate> prices = requester
    .route("prices.watch")
    .data(new PriceWatchRequest("ACME"))
    .retrieveFlux(PriceUpdate.class)
    .retryWhen(
        Retry.backoff(3, Duration.ofMillis(500))
            .maxBackoff(Duration.ofSeconds(5))
            .filter(this::isTransientFailure)
    );
~~~

Hàm <code>isTransientFailure</code> cần kiểm tra loại exception hoặc mã giao thức sau khi được thư viện giải mã. Không nên retry INVALID, cancellation do người dùng hoặc REJECTED do chính sách cố định. REJECTED do quá tải tạm thời có thể retry sau backoff nếu server cho phép. APPLICATION_ERROR cũng cần được phân loại theo nguyên nhân.

Khi dùng <code>retryWhen</code> trên request-stream, mỗi lần retry có thể tạo một subscription mới. Nếu nguồn phát lại dữ liệu, client cần cursor, sequence number hoặc event ID để xử lý trùng. Retry không tự khôi phục chính xác vị trí đã đọc.

## 10. Thông điệp lỗi và bảo mật

ERROR frame mang mã lỗi cùng thông tin mô tả dạng văn bản. Thông điệp này hữu ích cho chẩn đoán nhưng có thể được gửi tới client bên ngoài hệ thống. Vì vậy:

- Không gửi stack trace, câu truy vấn SQL hoặc đường dẫn file nội bộ.
- Không đưa token, mật khẩu, thông tin cá nhân hoặc dữ liệu nhạy cảm vào error message.
- Dùng mã lỗi miền ổn định như <code>ORDER_NOT_FOUND</code> hoặc <code>RESOURCE_LIMIT</code> trong hợp đồng ứng dụng nếu cần.
- Ghi stack trace và correlation ID ở server; gửi correlation ID an toàn cho client để hỗ trợ tra cứu.
- Không dùng nội dung message để phân loại lỗi nếu có thể dùng mã giao thức hoặc mã miền ổn định.

Mã giao thức cho biết nhóm lỗi; message text giúp con người hiểu chi tiết. Không nên dùng message text làm API contract vì câu chữ có thể thay đổi theo ngôn ngữ hoặc phiên bản.

## 11. Kiểm thử các mã lỗi

Kiểm thử nên xác nhận cả hành vi Publisher và mã lỗi thực tế được truyền qua RSocket. Unit test cho service có thể xác nhận exception miền; integration test cần khởi chạy client/server để xác nhận lớp mapping tạo đúng ERROR code.

Với Reactor, có thể kiểm tra nhánh lỗi bằng <code>StepVerifier</code>:

~~~java
StepVerifier.create(
        Mono.error(new InvalidRequestException("orderId required")))
    .expectError(InvalidRequestException.class)
    .verify();
~~~

Đây mới là unit test cho exception miền. Để xác nhận mã INVALID trên dây, cần integration test đi qua RSocket responder và kiểm tra exception hoặc error code mà client nhận được theo API của phiên bản thư viện đang dùng.

Ma trận kiểm thử nên có:

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Handler gặp lỗi ứng dụng | Stream kết thúc bằng APPLICATION_ERROR theo mapping đã cấu hình. |
| Server từ chối do capacity | Stream kết thúc bằng REJECTED; stream khác vẫn hoạt động. |
| Ứng dụng hủy tác vụ | Cancellation được truyền tới nguồn; nếu biểu đạt qua ERROR thì dùng CANCELED theo hợp đồng. |
| Payload sai cấu trúc | Request bị từ chối bằng INVALID. |
| Một stream lỗi trong connection dùng chung | Các stream không liên quan tiếp tục hoạt động nếu connection còn khỏe. |
| Connection-level failure | Session đóng và client chạy quy trình reconnect. |
| Client chủ động dispose subscription | Server quan sát cancellation; không yêu cầu ERROR CANCELED để xác nhận. |

Ngoài ra, cần kiểm tra client không retry vô hạn với INVALID hoặc REJECTED vĩnh viễn, thông báo lỗi không chứa dữ liệu nhạy cảm và log có correlation ID để truy vết.

## 12. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể có | Cách xử lý |
| --- | --- | --- |
| Client retry liên tục khi payload sai | INVALID bị phân loại nhầm là lỗi tạm thời. | Sửa request và loại INVALID khỏi retry policy. |
| Server quá tải hơn sau khi từ chối | Client retry REJECTED ngay lập tức. | Dùng backoff, jitter và giới hạn số lần thử. |
| Một lỗi stream làm client reconnect toàn bộ | Không phân biệt stream-level và connection-level ERROR. | Kiểm tra stream ID và mã lỗi trước khi đóng session. |
| Client không dừng khi người dùng rời màn hình | Subscription không được dispose hoặc nguồn không nhận cancellation. | Quản lý Disposable theo stream và nối cancellation tới nguồn. |
| Mọi lỗi đều hiện thành APPLICATION_ERROR | Lớp mapping gom tất cả exception vào một mã. | Phân loại INVALID, REJECTED, CANCELED và lỗi ứng dụng riêng. |
| Error message làm lộ thông tin nội bộ | Trả trực tiếp exception message hoặc stack trace. | Chuẩn hóa thông báo công khai và giữ chi tiết trong log server. |

## 13. Ghi nhớ

- APPLICATION_ERROR biểu thị lỗi trong quá trình xử lý ở tầng ứng dụng.
- REJECTED biểu thị bên nhận từ chối yêu cầu dù request có thể hợp lệ về cấu trúc.
- CANCELED là mã lỗi biểu đạt tương tác bị hủy; frame CANCEL là tín hiệu điều khiển để requester hủy stream.
- INVALID biểu thị request không hợp lệ về cấu trúc, định dạng hoặc ngữ nghĩa hợp đồng.
- Bốn mã trên thuộc nhóm lỗi stream; cần phân biệt với CONNECTION_ERROR và CONNECTION_CLOSE.
- Chỉ retry lỗi có khả năng tạm thời và thao tác an toàn; không retry nguyên trạng INVALID hoặc cancellation do người dùng.
- Error mapping phải ổn định, thông điệp gửi ra ngoài phải an toàn và integration test cần xác nhận mã thực tế trên wire.

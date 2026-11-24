# Rò rỉ payload, giải phóng sớm và lỗi đếm tham chiếu

RSocket Java chạy trên Netty có thể dùng các buffer được quản lý bằng reference counting để giảm cấp phát và tái sử dụng direct memory. Khi ứng dụng bật zero-copy hoặc thao tác trực tiếp với `Payload`/`ByteBuf`, mỗi lần nhận, giữ, chuyển giao và giải phóng buffer đều phải tuân theo quyền sở hữu rõ ràng. Một lần `release()` thiếu có thể giữ bộ nhớ ngoài heap; một lần `release()` thừa có thể làm hỏng dữ liệu mà stream khác vẫn đang sử dụng.

Ba lỗi thường gặp là **leak** (không trả reference), **premature release** (trả reference khi nơi khác còn dùng) và **double release** (trả cùng một reference hai lần). Bài này trình bày cách đọc `refCnt`, hiểu ownership của `Payload`, phân biệt `slice` với `retainedSlice`, xử lý cancellation/discard và dùng Netty leak detector để tìm vị trí gây lỗi trong ứng dụng RSocket.

## 1. Vì sao Payload cần reference counting?

Một `Payload` RSocket chứa data và metadata. Trong transport Netty, nội dung có thể nằm trong `ByteBuf` cấp phát từ heap hoặc direct memory pool. Thay vì chờ Garbage Collector xác định object không còn được tham chiếu, Netty dùng bộ đếm tham chiếu để biết khi nào vùng nhớ có thể được giải phóng hoặc trả về pool.

Điều này giúp giảm chi phí cấp phát và copy, nhưng JVM không tự hiểu reference count của Netty. Một `ByteBuf` có thể đã không còn reference Java nào nhưng `refCnt` vẫn lớn hơn 0; vùng nhớ khi đó không được trả về allocator và tạo thành leak. Ngược lại, nếu `refCnt` về 0 trong khi code vẫn giữ một view trỏ vào vùng nhớ, thao tác tiếp theo có thể ném `IllegalReferenceCountException` hoặc đọc dữ liệu không còn hợp lệ.

Trong RSocket, rủi ro tăng lên khi bật `PayloadDecoder.ZERO_COPY`: payload nhận được là các retained slice của frame gốc. Đây là tối ưu giảm copy, nhưng ứng dụng phải giải phóng payload sau khi dùng xong. `PayloadDecoder.DEFAULT` tạo các bản sao độc lập của data và metadata; theo contract của RSocket Java, các payload được decode theo cách mặc định không cần ứng dụng theo dõi và release thủ công.

## 2. Quy tắc reference count cơ bản

Với một object reference-counted mới được cấp phát, giá trị ban đầu thường là `refCnt() == 1`.

| Thao tác | Thay đổi | Ý nghĩa |
| --- | --- | --- |
| `retain()` | Tăng 1 | Tạo thêm một quyền giữ vùng nhớ. |
| `release()` | Giảm 1 | Trả một quyền giữ vùng nhớ. |
| `refCnt() == 0` | Không còn quyền giữ | Buffer được giải phóng hoặc trả về pool. |
| `release()` khi count đã 0 | Không hợp lệ | Có thể ném `IllegalReferenceCountException`. |

Ví dụ:

~~~java
import io.netty.buffer.ByteBuf;
import io.netty.buffer.ByteBufAllocator;

ByteBuf buffer = ByteBufAllocator.DEFAULT.directBuffer();
assert buffer.refCnt() == 1;

buffer.retain();
assert buffer.refCnt() == 2;

buffer.release();
assert buffer.refCnt() == 1;

buffer.release();
assert buffer.refCnt() == 0;
~~~

Mỗi lần `retain()` phải có đúng một lần `release()` tương ứng. Không dựa vào Garbage Collector để trả pooled direct memory. `refCnt()` hữu ích khi debug hoặc viết test, nhưng không nên dùng nó làm cơ chế đồng bộ trong production vì một thread khác có thể thay đổi count ngay sau khi bạn đọc.

## 3. Ownership: ai chịu trách nhiệm release?

Trước khi gọi `retain()` hoặc `release()`, hãy xác định ai đang sở hữu reference hiện tại. Một quy tắc thực dụng là: nơi tạo buffer sở hữu reference ban đầu; khi chuyển quyền sở hữu cho thành phần khác, hợp đồng API phải nói rõ bên nhận sẽ release; nếu hai bên cùng cần giữ dữ liệu, bên tạo thêm một reference bằng `retain()`.

| Tình huống | Trách nhiệm cần xác định |
| --- | --- |
| Ứng dụng tự tạo `Payload`/`ByteBuf` | Ứng dụng sở hữu reference ban đầu cho tới khi chuyển giao theo API. |
| RSocket nhận payload từ transport với `ZERO_COPY` | Payload chứa retained slice; code nhận payload ở tầng raw phải release khi dùng xong. |
| RSocket nhận payload với `PayloadDecoder.DEFAULT` | Data/metadata là bản sao; không cần quản lý release thủ công cho payload decode đó. |
| `RSocket` phát `Payload` response cho subscriber | Subscriber tiêu thụ payload cần release khi đã đọc xong nếu decoder dùng zero-copy. |
| Một task bất đồng bộ cần dùng payload sau khi handler hiện tại kết thúc | Task phải có reference riêng bằng `retain()` và release khi task kết thúc. |
| API đã nhận quyền sở hữu payload để gửi | Không release thêm từ caller sau khi chuyển giao, trừ khi contract của API yêu cầu rõ. |

Không suy đoán ownership chỉ từ kiểu Java. Kiểm tra contract của phiên bản RSocket Java/Netty đang dùng, đặc biệt ở adapter, interceptor và custom `RSocket`. Tránh viết một `finally { payload.release(); }` chung quanh mọi lời gọi nếu payload đã được chuyển quyền cho RSocket stack; thao tác đó có thể trở thành double release.

## 4. PayloadDecoder.DEFAULT và ZERO_COPY

RSocket Java có hai cách giải mã payload phổ biến:

| Decoder | Cách tạo payload | Ứng dụng có cần release payload nhận được? |
| --- | --- | --- |
| `PayloadDecoder.DEFAULT` | Copy data và metadata ra các buffer độc lập. | Không cần quản lý reference count của payload đã decode theo mặc định. |
| `PayloadDecoder.ZERO_COPY` | Tạo retained slice từ `ByteBuf` frame gốc. | Có. Release payload khi không còn sử dụng. |

Cấu hình zero-copy ở server:

~~~java
import io.rsocket.core.RSocketServer;
import io.rsocket.frame.decoder.PayloadDecoder;
import io.rsocket.transport.netty.server.TcpServerTransport;

RSocketServer.create(socketAcceptor)
    .payloadDecoder(PayloadDecoder.ZERO_COPY)
    .bind(TcpServerTransport.create("localhost", 9898))
    .block();
~~~

Client cần cấu hình decoder tương ứng nếu muốn tối ưu chiều nhận:

~~~java
import io.rsocket.core.RSocketConnector;
import io.rsocket.frame.decoder.PayloadDecoder;
import io.rsocket.transport.netty.client.TcpClientTransport;

RSocketConnector.create()
    .payloadDecoder(PayloadDecoder.ZERO_COPY)
    .connect(TcpClientTransport.create("localhost", 9898))
    .block();
~~~

Không bật zero-copy chỉ vì muốn giảm latency. Trước tiên hãy đo allocation, GC và throughput. Nếu phần lớn handler chỉ chuyển đổi payload thành String/DTO rồi bỏ buffer, chế độ copy mặc định có thể đơn giản và ít rủi ro hơn. Chỉ bật zero-copy khi ứng dụng có quy trình ownership và test leak rõ ràng.

## 5. Giải phóng Payload trong raw RSocket handler

Khi triển khai trực tiếp `RSocket` hoặc `SocketAcceptor` và nhận `Payload` ở tầng thấp, với `PayloadDecoder.ZERO_COPY`, hãy đọc nội dung rồi release payload đúng một lần:

~~~java
import io.rsocket.Payload;

String readData(Payload payload) {
    try {
        return payload.getDataUtf8();
    } finally {
        payload.release();
    }
}
~~~

`getDataUtf8()` trả về `String` độc lập với buffer, vì vậy có thể sử dụng chuỗi sau khi payload được release. Nếu cần giữ `ByteBuf`, `ByteBuffer` hoặc một view trỏ vào vùng nhớ gốc, không release payload trước khi việc sử dụng view kết thúc; hãy tạo bản copy hoặc giữ một reference riêng.

Không release riêng `payload.getData()` rồi tiếp tục release `payload`. Data và metadata thuộc cùng payload ownership; hãy release owner theo contract, tránh giảm reference hai lần cho cùng vùng nhớ.

## 6. Tiêu thụ Payload từ Flux và xử lý cancellation

Khi dùng raw `RSocket.requestStream`, subscriber nhận từng `Payload`. Với zero-copy, hãy giải phóng từng payload sau khi chuyển dữ liệu sang kiểu độc lập:

~~~java
import io.rsocket.Payload;
import io.rsocket.RSocket;
import io.rsocket.util.DefaultPayload;
import reactor.core.publisher.Flux;
import reactor.core.scheduler.Schedulers;

Flux<String> readEvents(RSocket socket) {
    return socket.requestStream(DefaultPayload.create("events"))
        .publishOn(Schedulers.parallel())
        .doOnDiscard(Payload.class, Payload::release)
        .map(payload -> {
            try {
                return payload.getDataUtf8();
            } finally {
                payload.release();
            }
        });
}
~~~

`map` giải phóng payload ngay cả khi việc đọc/giải mã phát sinh exception. `doOnDiscard` là lớp bảo vệ bổ sung cho các operator hỗ trợ discard, ví dụ queue bị bỏ khi cancel hoặc filter loại phần tử. Đặt hook ở sau operator có thể discard và kiểm tra hành vi của phiên bản Reactor đang dùng.

`doOnDiscard` không thay thế việc release phần tử đã được phát tới `map`, cũng không tự động xử lý mọi queue của thư viện bên ngoài. Mỗi payload đã được nhận trong callback vẫn cần một đường giải phóng rõ ràng. Với cancellation, hãy kiểm tra operator queue, publisher và custom adapter để bảo đảm phần tử chưa phát được discard đúng cách.

## 7. Giải phóng sớm: use-after-release

Giải phóng sớm xảy ra khi code release payload nhưng một thành phần khác vẫn đang đọc vùng nhớ. Ví dụ sai:

~~~java
import io.netty.buffer.ByteBuf;
import io.rsocket.Payload;
import reactor.core.publisher.Mono;

ByteBuf data = payload.getData().slice();
payload.release();
return Mono.fromCallable(() -> decode(data));
~~~

Đoạn code giữ một view tới vùng nhớ gốc rồi release owner trước khi `decode` chạy. Khi task thực thi, buffer có thể đã về pool hoặc `refCnt` đã bằng 0.

Cách sửa an toàn nhất nếu dữ liệu nhỏ là copy sang kiểu độc lập trước khi release:

~~~java
String text;
try {
    text = payload.getDataUtf8();
} finally {
    payload.release();
}

return Mono.fromCallable(() -> decodeText(text));
~~~

Nếu cần giữ zero-copy qua ranh giới bất đồng bộ, phải retain thêm một reference cho task và release reference đó khi task hoàn tất. Đừng giữ một view không-retain sau khi owner đã release.

## 8. retain khi chuyển giao sang task khác

Ví dụ dưới đây minh họa chuyển một payload từ handler raw sang executor. Handler giữ reference ban đầu; task nhận thêm một reference và tự release khi xử lý xong:

~~~java
import java.util.concurrent.Executor;
import java.util.concurrent.RejectedExecutionException;
import io.rsocket.Payload;

void dispatch(Payload payload, Executor executor) {
    Payload retained = payload.retain();
    try {
        executor.execute(() -> {
            try {
                process(retained);
            } finally {
                retained.release();
            }
        });
    } catch (RejectedExecutionException ex) {
        retained.release();
        throw ex;
    } finally {
        payload.release();
    }
}
~~~

Luồng ownership:

1. Payload đi vào handler với count 1.
2. `retain()` tạo reference cho task, count thành 2.
3. Handler kết thúc và release reference ban đầu, count còn 1.
4. Task xử lý xong và release reference riêng, count về 0.
5. Nếu executor từ chối task, nhánh catch release reference đã retain để không leak.

Đây là ví dụ cho raw handler mà ứng dụng chịu trách nhiệm release inbound payload. Nếu đang ở Spring annotated handler với DTO đã decode, không áp dụng đoạn code này cho object DTO; hãy quản lý `Payload`/`DataBuffer` theo đúng tầng API mà ứng dụng thực sự sở hữu.

## 9. slice, duplicate, retainedSlice và copy

Các phương thức tạo view không giống nhau:

| Phương thức | Vùng nhớ | Tăng refCnt? | Khi nào dùng |
| --- | --- | --- | --- |
| `slice()` / `readSlice()` | Chia sẻ vùng nhớ gốc | Không | Dùng tạm trong cùng lifetime của owner. |
| `duplicate()` | Chia sẻ toàn bộ vùng nhớ gốc, index riêng | Không | Cần view với reader/writer index riêng nhưng cùng lifetime. |
| `retainedSlice()` / `retainedDuplicate()` | Chia sẻ vùng nhớ gốc | Có | Chuyển view sang owner khác hoặc giữ lâu hơn owner hiện tại. |
| `copy()` | Cấp vùng nhớ độc lập | Có reference riêng ban đầu | Cần dữ liệu sống độc lập với buffer gốc. |

Ví dụ:

~~~java
import io.netty.buffer.ByteBuf;
import io.netty.buffer.Unpooled;

ByteBuf parent = Unpooled.buffer().writeByte(7);

ByteBuf view = parent.slice();
// view và parent chia sẻ refCnt; slice() không retain.

ByteBuf retainedView = parent.retainedSlice();
// retainedView giữ thêm một reference.

ByteBuf independentCopy = parent.copy();
// independentCopy có vùng nhớ và vòng đời riêng.

retainedView.release();
independentCopy.release();
parent.release();
~~~

Nếu chuyển `view` sang callback bất đồng bộ nhưng không retain, callback có thể dùng vùng nhớ đã bị giải phóng. Nếu dùng `retainedSlice`, phải release retained view riêng; release parent không thay thế việc đó.

## 10. Leak do thiếu release trên nhánh lỗi

Một lỗi phổ biến là chỉ release ở happy path:

~~~java
// Sai: nếu decode() ném exception, payload không được release.
String value = payload.getDataUtf8();
validate(value);
payload.release();
~~~

Đưa release vào `finally`:

~~~java
String value;
try {
    value = payload.getDataUtf8();
    validate(value);
} finally {
    payload.release();
}
~~~

Khi một pipeline có nhiều bước có thể lỗi, hãy đặt ownership boundary quanh toàn bộ phần xử lý payload. Các đường complete, error, cancel và executor rejection đều phải có cleanup. Đừng chỉ kiểm tra nhánh trả response thành công.

## 11. Double release và IllegalReferenceCountException

Double release thường xuất hiện khi hai thành phần cùng nghĩ mình sở hữu reference ban đầu:

- Handler release payload sau khi dùng, nhưng adapter downstream cũng release.
- Code gọi `payload.release()` và tiếp tục gọi `payload.getData().release()`.
- Một nhánh error release payload, sau đó `doFinally` lại release cùng reference.
- `doOnNext` release payload, nhưng một helper được gọi bên trong cũng release.
- Dùng `safeRelease` ở nhiều lớp để che việc ownership không rõ.

Khi `refCnt` giảm về 0, lần truy cập tiếp theo có thể ném `IllegalReferenceCountException: refCnt: 0`. Nếu release quá số lần retain, count có thể âm hoặc phát exception tương tự.

Đừng dùng `ReferenceCountUtil.safeRelease()` như cách sửa mặc định. Hàm này có thể che exception ở nhánh release nhưng không sửa được thiết kế ownership sai; dữ liệu vẫn có thể bị giải phóng sớm hoặc một nhánh khác tiếp tục dùng buffer đã hết lifetime.

## 12. Spring RSocket: Payload, DataBuffer và DTO

Trong Spring annotated handler, ứng dụng thường nhận DTO, `String`, hoặc `Flux<DTO>` qua `@MessageMapping`. Spring giải mã payload qua `RSocketStrategies` và encoder/decoder; ứng dụng làm việc với object đã decode thay vì quản lý raw `Payload` ở tầng transport.

Vì vậy:

- Nếu handler nhận DTO/String đã decode, không gọi `release()` trên DTO.
- Nếu code tự thao tác với raw `Payload` trong custom `RSocket`/`SocketAcceptor`, áp dụng quy tắc ownership của RSocket Java, nhất là khi bật zero-copy.
- Nếu code trực tiếp giữ `DataBuffer` pooled, dùng API `DataBufferUtils.retain/release` theo contract của Spring.
- Không gọi cả `Payload.release()` và `DataBufferUtils.release()` trên cùng vùng nhớ nếu chưa xác định rõ hai object có chia sẻ ownership hay không.

Spring có các hook nội bộ để xử lý payload/data buffer bị discard trong quá trình encode/decode. Khi viết custom adapter, interceptor hoặc bridge giữa Reactor và API khác, đừng mặc định framework sẽ cleanup một reference mà ứng dụng đã retain thêm.

## 13. DataBufferUtils và Netty ByteBuf

Spring `DataBuffer` có thể bọc một Netty `ByteBuf` pooled. Khi ứng dụng tự giữ một `DataBuffer` qua callback hoặc queue, cần tuân thủ quy tắc retain/release của implementation:

~~~java
import java.util.concurrent.Executor;
import java.util.concurrent.RejectedExecutionException;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferUtils;

void processLater(DataBuffer buffer, Executor executor) {
    DataBuffer retained = DataBufferUtils.retain(buffer);
    try {
        executor.execute(() -> {
            try {
                decode(retained);
            } finally {
                DataBufferUtils.release(retained);
            }
        });
    } catch (RejectedExecutionException ex) {
        DataBufferUtils.release(retained);
        throw ex;
    } finally {
        DataBufferUtils.release(buffer);
    }
}
~~~

Ví dụ giả định method nhận quyền sở hữu reference ban đầu của buffer và task nhận một reference riêng. Nếu buffer không phải pooled hoặc implementation có contract khác, hãy kiểm tra hành vi retain/release cụ thể. Không áp dụng đồng thời quy tắc release của `Payload` và `DataBuffer` cho cùng một reference nếu framework đã chuyển đổi/giải phóng nó.

## 14. Diagnosing leak bằng Netty ResourceLeakDetector

Netty có `ResourceLeakDetector` để lấy dấu vết buffer bị garbage collect khi reference count chưa về 0. Các mức phổ biến:

| Mức | Phạm vi | Cách dùng |
| --- | --- | --- |
| `DISABLED` | Tắt phát hiện | Không dùng khi điều tra leak. |
| `SIMPLE` | Lấy mẫu allocation, chi phí thấp | Có thể dùng ở môi trường chạy bình thường. |
| `ADVANCED` | Báo cáo access record chi tiết hơn | Dùng khi đã khoanh vùng được môi trường có leak. |
| `PARANOID` | Kiểm tra mọi allocation | Dùng trong test hoặc tái hiện có kiểm soát; overhead cao. |

Có thể bật leak detector bằng JVM option:

~~~text
-Dio.netty.leakDetection.level=advanced
~~~

Tên property cũ io.netty.leakDetectionLevel vẫn có thể xuất hiện ở các phiên bản Netty trước; hãy dùng tên property được tài liệu của phiên bản dependency đang chạy hỗ trợ.

Trong test cần bắt leak khó tái hiện:

~~~text
-Dio.netty.leakDetection.level=paranoid
~~~

Hoặc cấu hình trong test:

~~~java
import io.netty.util.ResourceLeakDetector;

ResourceLeakDetector.setLevel(ResourceLeakDetector.Level.PARANOID);
~~~

Khi thấy log dạng `LEAK: ByteBuf.release() was not called before it's garbage-collected`, đọc allocation/access record để tìm nơi tạo và nơi sử dụng cuối cùng. Leak detector lấy mẫu ở các mức thấp nên không có log không chứng minh hệ thống không leak. Chạy `PARANOID` chỉ trong thời gian test vì chi phí đáng kể.

## 15. Phân biệt leak, direct memory pressure và heap leak

Các hiện tượng có thể giống nhau nhưng nguyên nhân khác nhau:

| Triệu chứng | Khả năng nguyên nhân | Cách kiểm tra |
| --- | --- | --- |
| Log `LEAK: ByteBuf.release() was not called` | Reference-counted buffer không được release. | Bật ADVANCED/PARANOID, đọc access record. |
| `IllegalReferenceCountException` | Release thừa hoặc truy cập sau release. | Tìm mọi retain/release và điểm chuyển ownership. |
| `OutOfDirectMemoryError` | Direct memory bị giữ lâu, allocator pressure hoặc cấu hình direct memory không đủ. | Đối chiếu Netty allocator metrics, leak logs, tải và số payload đang giữ. |
| Heap tăng liên tục | DTO, queue, cache hoặc subscriber giữ object graph. | Heap dump, dominator tree và queue/subscription metrics. |
| Direct memory tăng nhưng heap ổn định | ByteBuf/DataBuffer pooled hoặc native allocation. | Theo dõi Netty allocator và native memory, không chỉ heap dump. |

Leak detector không phát hiện mọi loại memory leak. Một queue giữ payload còn reachable có thể không bị báo là leak vì GC chưa thu hồi object; nhưng queue đó vẫn làm memory tăng. Cần kết hợp leak logs với metric số connection/stream, queue depth, direct memory và heap.

## 16. Quy trình điều tra sự cố

Khi production có direct memory tăng, `LEAK` warning hoặc `IllegalReferenceCountException`, thực hiện theo thứ tự:

1. Ghi nhận phiên bản Netty, RSocket Java, Reactor và Spring đang chạy; xác định `PayloadDecoder.DEFAULT` hay `ZERO_COPY`.
2. Xác định lỗi xuất hiện ở chiều inbound hay outbound, route nào và interaction nào.
3. Bật leak detector ở mức ADVANCED trên một instance canary hoặc môi trường tái hiện.
4. Giảm tải hoặc cô lập route để xác định payload/stream gây tăng bộ nhớ.
5. Đọc access record, lần theo mọi nhánh complete/error/cancel và điểm chuyển payload sang executor/queue.
6. Lập ownership ledger: ai tạo, ai retain, ai nhận ownership, ai release và release ở signal nào.
7. Kiểm tra `slice`, `duplicate`, `DataBuffer`, `ByteBuf` và adapter có giữ view qua lifetime của owner không.
8. Sửa một ownership boundary, tái hiện cùng workload và xác nhận warning không còn.
9. Chạy test leak với PARANOID và test cancellation/error trước khi triển khai rộng.

Nếu chỉ xuất hiện khi bật ZERO_COPY, hãy so sánh lại với DEFAULT. Đây là cách khoanh vùng nhanh để xác định lỗi liên quan tới reference management, nhưng không nên coi việc tắt zero-copy là thay thế cho việc sửa ownership nếu ứng dụng vẫn cần zero-copy.

## 17. Kiểm thử retain/release và các nhánh kết thúc

Test nên xác nhận ref count sau mỗi ranh giới ownership:

~~~java
import io.netty.buffer.ByteBuf;
import io.netty.buffer.Unpooled;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

@Test
void retainedSliceHasIndependentOwnershipReference() {
    ByteBuf parent = Unpooled.buffer().writeByte(7);
    ByteBuf child = parent.retainedSlice();

    assertEquals(2, parent.refCnt());

    child.release();
    assertEquals(1, parent.refCnt());

    parent.release();
    assertEquals(0, parent.refCnt());
}
~~~

Test cho pipeline zero-copy nên bao phủ:

- Handler thành công và release đúng một lần.
- Decoder ném exception nhưng `finally` vẫn release.
- Subscriber cancel khi queue còn payload.
- Operator filter/drop/discard kích hoạt cleanup.
- Executor từ chối task sau khi retain.
- Một task bất đồng bộ kết thúc bình thường hoặc lỗi đều release reference riêng.
- Không có code nào truy cập buffer sau khi `refCnt` về 0.

Không chỉ assert `refCnt()` ở happy path. Leak thường nằm ở nhánh hiếm như timeout, disconnect, retry, cancel hoặc lỗi decode.

## 18. Checklist ownership trước khi bật ZERO_COPY

- [ ] Xác định chính xác API nào tạo hoặc nhận `Payload`/`ByteBuf`.
- [ ] Ghi rõ owner ban đầu và điểm chuyển quyền sở hữu.
- [ ] Mỗi `retain()` có một `release()` ở mọi đường kết thúc.
- [ ] Mỗi payload inbound zero-copy được release sau khi tiêu thụ.
- [ ] Payload outbound không bị release trước khi RSocket stack hoàn tất sử dụng.
- [ ] Không giữ `slice()`/`duplicate()` qua lifetime của parent nếu chưa retain.
- [ ] Không release cùng lúc `Payload` và các buffer con của nó.
- [ ] Có cleanup cho error, cancellation, timeout, discard và executor rejection.
- [ ] Có leak detector trong integration test và test tải có kiểm soát.
- [ ] Theo dõi direct memory, heap, connection, stream và queue metrics.

## 19. Những lỗi thường gặp

**Bật ZERO_COPY nhưng không release payload inbound.** Payload dùng retained slice; sau khi đọc xong phải release đúng một lần.

**Release payload trước khi callback bất đồng bộ đọc xong.** Task cần reference riêng bằng retain hoặc phải nhận một bản copy độc lập.

**Gọi release cả Payload và data/metadata ByteBuf.** Hai thao tác có thể trả cùng ownership hai lần; release đúng owner theo contract.

**Dùng slice/duplicate như thể chúng đã retain.** Các view này chia sẻ ref count và không tăng count; dùng retainedSlice/retainedDuplicate khi cần giữ riêng.

**Thiếu release ở nhánh exception.** Đặt cleanup trong finally hoặc cơ chế lifecycle tương đương.

**Quên payload bị discard khi cancel.** Bổ sung discard hook ở đúng vị trí và xác minh operator có hỗ trợ discard.

**Dùng safeRelease để che double release.** Sửa ownership boundary thay vì bỏ qua exception.

**Cho rằng heap dump luôn thấy leak Netty.** Direct memory có thể nằm ngoài heap; dùng Netty leak detector và allocator metrics.

**Cho rằng không có log LEAK nghĩa là không có vấn đề.** Detector lấy mẫu ở mức SIMPLE; object còn reachable trong queue cũng có thể gây memory pressure mà chưa thành leak warning.

## 20. Ghi nhớ

- Netty reference count bắt đầu từ 1; `retain()` tăng và `release()` giảm; về 0 thì vùng nhớ được giải phóng/trả về pool.
- `PayloadDecoder.DEFAULT` copy data/metadata; `ZERO_COPY` dùng retained slice và yêu cầu release khi dùng xong.
- Chỉ release reference mà code đang sở hữu; không release thêm sau khi đã chuyển quyền cho API khác.
- `slice()` và `duplicate()` không retain; `retainedSlice()` và `retainedDuplicate()` tạo thêm reference; `copy()` tạo vùng nhớ độc lập.
- Khi chuyển payload qua async boundary, retain trước khi owner hiện tại release và release reference mới ở task.
- Xử lý cả complete, error, cancel, timeout, discard và executor rejection.
- Spring handler nhận DTO đã decode không cần tự release DTO; raw `Payload` và pooled `DataBuffer` có quy tắc riêng.
- Dùng Netty `ResourceLeakDetector` ADVANCED/PARANOID, đọc access record và theo dõi direct memory để tìm leak.
- `IllegalReferenceCountException` thường báo release thừa hoặc truy cập sau release; `LEAK` warning báo reference chưa được trả.
- Bật zero-copy chỉ khi ownership đã được kiểm thử trên cả happy path lẫn các đường kết thúc bất thường.

## Tài liệu tham khảo

- [Netty — Reference counted objects](https://netty.io/wiki/reference-counted-objects.html)
- [Netty 4.1 — ByteBuf API](https://netty.io/4.1/api/io/netty/buffer/ByteBuf.html)
- [RSocket Java — Zero-copy và PayloadDecoder](https://github.com/rsocket/rsocket-java)
- [RSocket Java 1.1.5 — RSocket API](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/RSocket.html)
- [Spring Framework — RSocket support](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework — DataBufferUtils API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html)

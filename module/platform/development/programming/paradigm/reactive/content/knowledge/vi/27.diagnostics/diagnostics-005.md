# Chẩn đoán

## Quan sát phần tử bị bỏ và lỗi không thể chuyển tiếp

Một pipeline reactive không phải lúc nào cũng chuyển mọi giá trị do nguồn phát xuống subscriber. Một toán tử có thể chủ động loại phần tử theo điều kiện, hủy các phần tử đang nằm trong hàng đợi khi downstream không còn cần chúng, hoặc bỏ dữ liệu khi áp dụng chính sách backpressure. Ngoài ra, nguồn có thể phát một tín hiệu quá muộn sau khi subscription đã bị hủy hoặc chuỗi đã kết thúc. Khi đó, tín hiệu không còn đường hợp lệ để chuyển đến subscriber.

Trong Project Reactor, cần phân biệt ba tình huống:

- **Discard:** một toán tử loại bỏ phần tử theo ngữ nghĩa hoạt động của nó, ví dụ phần tử không qua điều kiện filter hoặc phần tử còn trong hàng đợi khi một nhánh bị hủy.
- **Drop:** một tín hiệu đến nhưng không thể được tiếp nhận hoặc chuyển tiếp, thường do subscription đã bị hủy/kết thúc hoặc do chính sách bỏ dữ liệu được chọn.
- **Error không thể chuyển tiếp:** lỗi đến sau khi downstream đã nhận terminal signal hoặc đã hủy, nên không thể gửi thêm một tín hiệu onError hợp lệ.

Các cơ chế quan sát tương ứng gồm **doOnDiscard** cho những toán tử có hỗ trợ discard, callback riêng của các toán tử drop có chủ đích, và các global hook **Hooks.onNextDropped** cùng **Hooks.onErrorDropped** cho tín hiệu bị bỏ ở cấp Reactor. Chọn đúng cơ chế giúp phát hiện mất dữ liệu, giải phóng tài nguyên và ghi nhận lỗi mà không làm rối luồng lỗi chính.

### 1. Phân biệt discard, drop và error bình thường

Reactive Streams cho phép một Publisher phát các tín hiệu onNext, onError hoặc onComplete theo hợp đồng. Sau onError hoặc onComplete, không được phát thêm tín hiệu hợp lệ cho subscriber đó. Subscriber cũng có thể gửi cancellation để yêu cầu ngừng tiêu thụ.

Các trường hợp thường gặp:

| Tình huống | Điều xảy ra | Cơ chế quan sát phù hợp |
| --- | --- | --- |
| Filter loại phần tử không thỏa điều kiện | Toán tử chủ động discard phần tử | doOnDiscard nếu toán tử hỗ trợ |
| Một toán tử hủy nhánh và loại phần tử đang chờ trong queue | Các phần tử không còn được chuyển tiếp | doOnDiscard nếu toán tử hỗ trợ |
| Nguồn phát onNext sau cancellation hoặc sau khi chuỗi đã kết thúc | Tín hiệu đến quá muộn, không thể chuyển xuống | Hooks.onNextDropped |
| Nguồn phát onError sau terminal signal hoặc cancellation | Lỗi không thể chuyển xuống subscriber | Hooks.onErrorDropped |
| Publisher phát lỗi khi chuỗi vẫn còn hoạt động | Lỗi đi theo kênh onError bình thường | onErrorResume, doOnError, retryWhen |
| Ứng dụng chủ động bỏ phần tử khi downstream thiếu demand | Chính sách backpressure loại phần tử | callback của onBackpressureDrop hoặc hook phù hợp |

Điểm quan trọng là discard thường là một phần của ngữ nghĩa nội bộ toán tử. Drop là tín hiệu không thể tiếp nhận hoặc là quyết định bỏ dữ liệu theo chính sách. Một lỗi bình thường vẫn có thể được phục hồi hoặc quan sát bằng toán tử xử lý lỗi; một dropped error đã không còn khả năng đi theo kênh lỗi chính.

### 2. Quan sát phần tử bị loại bằng doOnDiscard

**doOnDiscard(Class, Consumer)** đăng ký một callback trong Reactor Context để những toán tử có hỗ trợ discard gọi khi chúng loại phần tử. Ví dụ, filter bỏ các giá trị không thỏa điều kiện:

~~~java
import java.util.ArrayList;
import java.util.List;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

List<Integer> discarded = new ArrayList<>();

Flux<Integer> accepted =
    Flux.range(1, 5)
        .filter(value -> value % 2 == 0)
        .doOnDiscard(Integer.class, discarded::add);

StepVerifier.create(accepted)
    .expectNext(2, 4)
    .verifyComplete();

assertEquals(List.of(1, 3, 5), discarded);
~~~

Subscriber chỉ nhận 2 và 4. Các giá trị 1, 3 và 5 bị filter loại bỏ; callback doOnDiscard ghi nhận chúng. Trong pipeline, đặt doOnDiscard ở phía downstream của toán tử cần quan sát để Context của subscriber truyền ngược đến toán tử upstream.

**doOnDiscard** chỉ hoạt động với các toán tử có triển khai discard support. Nó không phải một listener bắt mọi giá trị bị mất ở bất kỳ vị trí nào. Khi dùng toán tử tùy biến hoặc thư viện ngoài, hãy kiểm tra hợp đồng discard của toán tử đó trước khi dựa vào callback.

### 3. Vì sao vị trí doOnDiscard quan trọng?

Reactor truyền Context từ subscriber ngược về upstream khi subscription được thiết lập. **doOnDiscard** bổ sung callback vào Context; toán tử upstream có hỗ trợ discard đọc callback này khi cần loại một phần tử.

~~~text
Assembly:
source -> filter -> doOnDiscard -> subscriber

Context khi subscribe:
subscriber -> doOnDiscard -> filter -> source

Phần tử:
source -> filter -> subscriber
             |
             +-- không đạt điều kiện
                    |
                    v
              doOnDiscard callback
~~~

Vì vậy, đoạn sau đặt callback ở vị trí phù hợp:

~~~java
Flux<DataRecord> records =
    source
        .filter(this::isUseful)
        .doOnDiscard(DataRecord.class, this::releaseRecord);
~~~

Nếu đặt doOnDiscard trước filter, callback không nằm trong Context mà filter nhận được theo hướng subscribe và có thể không quan sát được phần tử bị filter loại. Khi một pipeline có nhiều toán tử discard, đặt callback ở phía downstream của các toán tử cần theo dõi, hoặc gần điểm tiêu thụ cuối cùng để bao phủ các toán tử upstream hỗ trợ.

### 4. Giải phóng tài nguyên của phần tử bị discard

Một số phần tử không chỉ là object Java thông thường. Chúng có thể giữ tài nguyên ngoài heap, buffer tham chiếu đếm, handle hoặc tài nguyên cần giải phóng rõ ràng. Nếu toán tử discard chúng mà ứng dụng không cleanup, tài nguyên có thể bị rò rỉ.

Ví dụ khi làm việc với Netty ByteBuf:

~~~java
import io.netty.buffer.ByteBuf;
import io.netty.util.ReferenceCountUtil;
import reactor.core.publisher.Flux;

Flux<ByteBuf> usefulBuffers =
    inboundBuffers
        .filter(this::isValid)
        .doOnDiscard(
            ByteBuf.class,
            buffer -> ReferenceCountUtil.release(buffer)
        );
~~~

Nếu filter loại một buffer, callback giảm reference count để tài nguyên có thể được thu hồi khi không còn nơi nào sở hữu nó. Cách giải phóng cụ thể phụ thuộc loại tài nguyên; với Spring DataBuffer, có thể dùng tiện ích release tương ứng của Spring.

Chỉ giải phóng tài nguyên khi pipeline thực sự sở hữu trách nhiệm đó. Nếu một thành phần khác vẫn giữ tham chiếu hợp lệ, giải phóng sớm có thể gây lỗi truy cập tài nguyên đã được release. Callback cleanup nên ngắn, an toàn khi chạy trên thread phát tín hiệu và không ném exception.

### 5. Discard khi hủy nhánh hoặc loại phần tử đang chờ

Discard không chỉ xuất hiện ở filter. Một số toán tử có thể giữ phần tử trong queue để phối hợp concurrency hoặc prefetch. Khi downstream hủy hoặc một nhánh không còn cần dữ liệu, các phần tử đang chờ có thể bị loại bỏ.

Ví dụ một pipeline chỉ cần một kết quả đầu tiên:

~~~java
Flux<Result> firstResult =
    source
        .take(1)
        .doOnDiscard(
            Result.class,
            result -> metrics.incrementDiscardedResults()
        );
~~~

Với nguồn và toán tử có prefetch, có thể đã có phần tử được yêu cầu trước khi take hủy upstream. Các toán tử hỗ trợ discard có thể gọi callback cho phần tử bị loại khỏi hàng đợi. Số phần tử thực tế phụ thuộc nguồn, cách lập lịch và cấu hình prefetch; không nên giả định mọi phần tử sau phần tử đầu tiên đều đã được tạo hoặc đều phải đi qua callback.

Đây là lý do nên kiểm thử cleanup với đúng loại nguồn và toán tử dùng trong ứng dụng, thay vì chỉ dựa trên số phần tử cuối cùng subscriber nhận được.

### 6. Chính sách drop do backpressure

Khi nguồn phát nhanh hơn downstream có thể tiêu thụ, ứng dụng phải chọn chính sách điều tiết phù hợp. Một số lựa chọn:

- **onBackpressureDrop:** bỏ phần tử khi downstream chưa có demand; có thể truyền callback để ghi nhận phần tử bị bỏ.
- **onBackpressureLatest:** giữ giá trị mới nhất, thay thế giá trị cũ đang chờ.
- **onBackpressureBuffer:** lưu phần tử trong queue; cần giới hạn dung lượng và xác định hành vi khi đầy.
- **onBackpressureError:** phát lỗi khi không thể chuyển phần tử do thiếu demand.

Ví dụ chọn bỏ phần tử và đếm số lần drop:

~~~java
import reactor.core.publisher.Flux;

Flux<MetricSample> samples =
    metricSource.samples()
        .onBackpressureDrop(sample ->
            metrics.incrementDroppedSamples()
        );
~~~

Chính sách này phù hợp khi dữ liệu cũ không còn giá trị, chẳng hạn một dashboard chỉ cần cập nhật trạng thái gần nhất. Không phù hợp với sự kiện nghiệp vụ cần xử lý đầy đủ như lệnh thanh toán hoặc thay đổi tồn kho.

Callback của onBackpressureDrop là nơi trực tiếp quan sát phần tử bị toán tử này loại bỏ. Không nên giả định doOnDiscard thay thế callback của chính sách drop. Hãy dùng hook được tài liệu toán tử quy định cho đúng loại hành vi.

### 7. Phân biệt onBackpressureDrop với doOnDiscard

Hai cơ chế có mục đích khác nhau:

| Cơ chế | Điều được quan sát | Phạm vi |
| --- | --- | --- |
| doOnDiscard | Phần tử bị toán tử có discard support loại bỏ trong quá trình vận hành | Cục bộ theo subscription thông qua Context |
| onBackpressureDrop(callback) | Phần tử bị chính sách backpressure drop loại bỏ do thiếu demand | Tại toán tử drop cụ thể |
| Hooks.onNextDropped | Tín hiệu onNext không thể chuyển tiếp trong các tình huống dropped signal | Global trong Reactor runtime |

Không nên gom mọi trường hợp vào một bộ đếm “dropped” duy nhất nếu cần chẩn đoán chính xác. Filter loại phần tử không hợp lệ là hành vi nghiệp vụ; backpressure drop là chính sách tải; late onNext sau cancellation có thể là lỗi vòng đời của nguồn. Ba nguyên nhân cần được ghi nhận riêng.

### 8. Quan sát onNext bị bỏ bằng Hooks.onNextDropped

Khi một nguồn phát onNext sau khi subscriber đã hủy hoặc chuỗi đã kết thúc, Reactor không thể chuyển phần tử đó xuống downstream. Global hook **Hooks.onNextDropped** cho phép ghi nhận tín hiệu bị bỏ:

~~~java
import reactor.core.publisher.Hooks;

Hooks.onNextDropped(value ->
    logger.warn("Reactive onNext signal was dropped: {}", value)
);
~~~

Hook này có phạm vi toàn cục trong Reactor runtime. Hãy đăng ký một lần ở giai đoạn khởi tạo ứng dụng, dùng logger hoặc metrics phù hợp và tránh ghi toàn bộ payload nếu dữ liệu có thể chứa thông tin nhạy cảm.

Global hook là công cụ chẩn đoán. Nó không gửi lại phần tử, không khôi phục subscription và không làm downstream sống lại. Nếu cần bảo đảm không mất sự kiện, hãy giải quyết ở nguồn: tuân thủ cancellation, kiểm soát vòng đời callback, hoặc dùng broker/lưu trữ có khả năng replay.

### 9. Quan sát lỗi không thể chuyển tiếp bằng Hooks.onErrorDropped

Một Publisher chỉ được gửi một terminal signal cho subscription. Nếu nguồn gửi onError sau khi đã gửi onComplete, sau khi đã gửi onError khác hoặc sau cancellation, lỗi đến muộn không thể được gửi xuống subscriber như một lỗi chính thứ hai.

Global hook **Hooks.onErrorDropped** cho phép ghi nhận các lỗi đó:

~~~java
import reactor.core.publisher.Hooks;

Hooks.onErrorDropped(error ->
    logger.error("Reactive error signal could not be propagated", error)
);
~~~

Dropped error khác với lỗi bình thường:

~~~text
Lỗi bình thường:
source -> onError -> operator xử lý lỗi -> subscriber

Lỗi không thể chuyển tiếp:
source -> onError
          |
          +-- subscription đã kết thúc hoặc bị hủy
                    |
                    v
             Hooks.onErrorDropped
~~~

**doOnError** chỉ quan sát lỗi đang đi theo kênh onError của pipeline. **onErrorResume** có thể phục hồi lỗi khi nó còn được chuyển đến toán tử. Nếu lỗi đã bị dropped vì subscription không còn nhận tín hiệu, không thể trông chờ onErrorResume phía downstream xử lý nó.

### 10. Tìm nguyên nhân của dropped error

Một dropped error thường là tín hiệu phụ cho thấy một nguồn hoặc callback đã phát lỗi ngoài vòng đời mà downstream còn chấp nhận. Một số nguyên nhân có thể gặp:

- Callback bất đồng bộ của thư viện ngoài chạy sau khi request đã timeout hoặc bị hủy.
- Nguồn tự quản lý thread và tiếp tục báo lỗi sau khi subscriber đã kết thúc.
- Một adapter phát nhiều terminal signal do quản lý trạng thái không đúng.
- Cleanup hoặc callback phụ ném lỗi sau khi lỗi chính đã kết thúc pipeline.
- Một race condition khiến cancellation và callback lỗi xảy ra gần như đồng thời.

Không nên chỉ tắt hook để log biến mất. Hãy truy tìm nguồn phát, kiểm tra vòng đời đăng ký/hủy, bảo đảm callback chỉ phát một terminal signal và xác định lỗi phụ có cần được xử lý ở adapter hay không.

### 11. Kết hợp quan sát cục bộ và global hook

Một chiến lược quan sát có thể dùng cả ba lớp:

1. **doOnDiscard** để cleanup và đếm phần tử bị các toán tử hỗ trợ discard loại bỏ trong một pipeline.
2. Callback của **onBackpressureDrop** để đo số phần tử bị bỏ do chính sách tải đã chọn.
3. **Hooks.onNextDropped** và **Hooks.onErrorDropped** để phát hiện tín hiệu đến muộn hoặc không thể chuyển tiếp ở phạm vi runtime.

Ví dụ kết hợp quan sát discard cục bộ với xử lý lỗi bình thường:

~~~java
Flux<DecodedEvent> events =
    decoder.decode(rawEvents)
        .filter(this::isSupported)
        .doOnDiscard(
            DecodedEvent.class,
            event -> metrics.incrementDiscardedEvents()
        )
        .doOnError(error ->
            logger.error("Event pipeline failed", error)
        )
        .onErrorResume(
            RecoverableDecodeException.class,
            error -> Flux.empty()
        );
~~~

Ở đây, phần tử không hỗ trợ được discard và đếm riêng; lỗi đang đi theo kênh onError được log rồi chỉ phục hồi nếu thuộc loại có thể bỏ qua theo nghiệp vụ. Lỗi dropped sau cancellation vẫn thuộc trách nhiệm của global hook.

Không dùng onErrorResume để âm thầm bỏ mọi lỗi. Nếu lỗi biểu thị dữ liệu hỏng, vi phạm hợp đồng hoặc sự cố hệ thống, cần giữ thông tin và để lỗi được quan sát ở tầng phù hợp.

### 12. Kiểm thử doOnDiscard

Có thể kiểm tra callback discard với một nguồn xác định và toán tử filter:

~~~java
import java.util.ArrayList;
import java.util.List;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

List<Integer> discarded = new ArrayList<>();

StepVerifier.create(
        Flux.range(1, 6)
            .filter(value -> value % 2 == 0)
            .doOnDiscard(Integer.class, discarded::add)
    )
    .expectNext(2, 4, 6)
    .verifyComplete();

assertEquals(List.of(1, 3, 5), discarded);
~~~

Kiểm thử này xác minh cả dữ liệu downstream nhận và phần tử bị filter loại. Khi dùng nguồn bất đồng bộ hoặc toán tử có prefetch, hãy thiết kế test riêng cho hành vi hủy và queue cleanup; không suy ra số lượng discard chỉ từ số phần tử không xuất hiện ở downstream.

### 13. Kiểm thử chính sách backpressure drop

Với một nguồn push có thể phát độc lập với demand, hãy kiểm tra chính sách drop và callback của chính toán tử. Ví dụ sau minh họa cách lắp ghép; bài kiểm thử thực tế nên điều khiển thời điểm phát bằng nguồn test phù hợp để tránh phụ thuộc race của thread:

~~~java
import reactor.core.publisher.Flux;

Flux<Reading> readings =
    externalPushSource.readings()
        .onBackpressureDrop(
            reading -> testMetrics.recordDrop(reading)
        );
~~~

Để kiểm tra xác định, có thể dùng TestPublisher hoặc một nguồn giả có khả năng phát theo bước. Xác minh phần tử nào được phát khi có demand, phần tử nào bị callback ghi nhận khi demand bằng không, và subscriber nhận terminal signal nào khi nguồn hoàn tất.

Không dùng một nguồn compliant chỉ phát theo demand để kết luận chính sách drop đã được kích hoạt. Nếu nguồn tự dừng khi không có demand, sẽ không có phần tử dư để toán tử loại bỏ.

### 14. Kiểm thử global dropped hooks

Global hook ảnh hưởng đến toàn bộ Reactor runtime trong phạm vi tiến trình. Vì vậy, test cần cô lập việc đăng ký và luôn khôi phục trạng thái hook mà test sở hữu:

~~~java
import java.util.ArrayList;
import java.util.List;

import reactor.core.publisher.Hooks;

List<Object> droppedValues = new ArrayList<>();
List<Throwable> droppedErrors = new ArrayList<>();

try {
    Hooks.onNextDropped(droppedValues::add);
    Hooks.onErrorDropped(droppedErrors::add);

    // Chạy adapter/nguồn test được thiết kế để phát tín hiệu muộn.
    // Xác minh hook nhận đúng tín hiệu không thể chuyển tiếp.
} finally {
    Hooks.resetOnNextDropped();
    Hooks.resetOnErrorDropped();
}
~~~

Đoạn mã là khung kiểm thử hook; để tạo dropped signal một cách xác định, cần một nguồn test mô phỏng đúng hành vi phát tín hiệu sau cancellation hoặc terminal signal. Không tạo race ngẫu nhiên bằng sleep rồi kỳ vọng hook luôn được gọi.

Vì hook là global, tránh chạy song song các test thay đổi cùng hook. Trong ứng dụng có nhiều thư viện đăng ký hook, việc reset toàn cục có thể ảnh hưởng cấu hình của thành phần khác; chỉ reset trong môi trường test cô lập hoặc khôi phục đúng cấu hình mà test đã thiết lập.

### 15. Callback quan sát phải an toàn

Callback discard và dropped hook thường chạy trên thread đang xử lý tín hiệu. Nếu callback thực hiện I/O blocking, ghi log đồng bộ chậm hoặc gọi dịch vụ khác, nó có thể làm chậm pipeline và gây thêm áp lực lên event loop.

Hãy giữ callback ngắn:

- Tăng counter hoặc ghi một sự kiện quan sát nhẹ.
- Không block để gửi log hoặc gọi API mạng.
- Không ném exception từ callback cleanup.
- Tránh log toàn bộ payload nếu có dữ liệu cá nhân hoặc bí mật.
- Không giải phóng cùng một tài nguyên ở nhiều callback khác nhau.

Nếu cần xử lý quan sát nặng, hãy đẩy một bản ghi nhỏ sang hệ thống telemetry phù hợp bằng cơ chế có giới hạn. Đừng tạo một pipeline reactive phụ không được quản lý cho mỗi phần tử bị drop; điều đó có thể biến sự cố quá tải thành một nguồn quá tải mới.

### 16. Chọn cơ chế theo mục đích

| Mục đích | Cơ chế |
| --- | --- |
| Ghi nhận phần tử bị filter hoặc toán tử hỗ trợ discard loại bỏ | **doOnDiscard** đặt downstream của toán tử |
| Giải phóng ByteBuf/DataBuffer bị discard | **doOnDiscard** với cleanup tương ứng |
| Đo phần tử bị bỏ vì downstream thiếu demand | Callback **onBackpressureDrop** |
| Giữ giá trị mới nhất và bỏ giá trị cũ | **onBackpressureLatest** |
| Phát hiện onNext đến sau cancellation/terminal signal | **Hooks.onNextDropped** |
| Phát hiện onError không thể chuyển tiếp | **Hooks.onErrorDropped** |
| Xử lý lỗi vẫn đang được truyền trong pipeline | **onErrorResume**, **retryWhen**, **doOnError** |

Trước khi thêm hook, hãy xác định câu hỏi cần trả lời: phần tử bị loại theo điều kiện nghiệp vụ, bị mất do quá tải, hay đến muộn sau khi vòng đời subscription kết thúc? Cùng một con số “dropped” có thể che giấu các nguyên nhân rất khác nhau.

### 17. Quy trình chẩn đoán

Khi thấy phần tử hoặc lỗi không đến subscriber như mong đợi, hãy lần lượt kiểm tra:

1. Nguồn có phát đúng tín hiệu và tuân thủ hợp đồng Reactive Streams không?
2. Toán tử nào có thể discard phần tử theo điều kiện, prefetch hoặc cancellation?
3. Có chính sách backpressure drop/latest/buffer nào đang chủ động bỏ dữ liệu không?
4. Subscription đã bị hủy hoặc đã nhận terminal signal trước khi tín hiệu đến chưa?
5. Có thể đặt **doOnDiscard** ở downstream của toán tử hỗ trợ discard để xác minh không?
6. Có cần callback riêng của toán tử drop hoặc global dropped hook không?
7. Tài nguyên của phần tử bị loại đã được giải phóng đúng một lần chưa?
8. Callback quan sát có block, ném lỗi hoặc tạo thêm tải không?
9. Có thể tái hiện bằng StepVerifier/TestPublisher mà không dựa vào timing ngẫu nhiên không?

Trong module REACTIVE_PROGRAMMING, quan sát discard và dropped signal giúp hiểu những gì xảy ra ngoài luồng dữ liệu bình thường. **doOnDiscard** phục vụ phần tử bị toán tử hỗ trợ loại bỏ; callback backpressure ghi nhận chính sách bỏ dữ liệu có chủ đích; **Hooks.onNextDropped** và **Hooks.onErrorDropped** phát hiện tín hiệu không thể chuyển tiếp. Phân biệt đúng các trường hợp này giúp bảo vệ tài nguyên, phát hiện lỗi vòng đời nguồn và đo lường mất dữ liệu theo nguyên nhân thực tế.

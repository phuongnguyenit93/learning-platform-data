# publishOn thay đổi nơi xử lý các toán tử phía sau

## 1. publishOn giải quyết vấn đề gì?

Trong Project Reactor, một chuỗi **Flux** hoặc **Mono** gồm nhiều toán tử: tạo dữ liệu, lọc, biến đổi, ghi log, gọi dịch vụ, tổng hợp kết quả và trả response. Những bước đó **không tự động chạy trên các luồng (thread) khác nhau**. Mặc định, nhiều nguồn và toán tử đồng bộ chạy trên chính thread đang phát tín hiệu từ toán tử đứng trước.

**publishOn(Scheduler)** là toán tử dùng để tạo **ranh giới chuyển ngữ cảnh thực thi** trong pipeline. Nó nhận các tín hiệu từ upstream và phát tiếp xuống downstream trên một worker của Scheduler được truyền vào. Vì vậy, **những toán tử phía sau publishOn** thường xử lý onNext/onError/onComplete trên thread do Scheduler đó chọn, cho đến khi có một ranh giới lịch thực thi khác, đặc biệt là một publishOn tiếp theo.

Ví dụ:

~~~java
Flux<Integer> numbers = Flux.range(1, 3)
        .map(n -> n * 2)                  // Bước A
        .publishOn(Schedulers.parallel()) // Ranh giới chuyển thread
        .map(n -> n + 10)                 // Bước B
        .filter(n -> n % 2 == 0);        // Bước C
~~~

Đây là **đoạn minh họa** dùng trong dự án có Reactor Core; nó chưa phải chương trình Java độc lập.

- **Bước A** nằm trước publishOn: nó thuộc đường xử lý upstream và **không được publishOn này chuyển thread ngược về trước**.
- **Bước B và C** nằm sau publishOn: chúng thường chạy trên worker được chọn từ Schedulers.parallel() khi nhận các tín hiệu của lượt subscription đó.
- Các bước không tự động chạy song song theo từng phần tử: publishOn **di chuyển nơi xử lý tín hiệu**, không mặc nhiên phân chia 1, 2, 3 cho ba thread.
- Pipeline chỉ mô tả công việc. Với nguồn lạnh như Flux.range, việc xử lý thường bắt đầu khi có **subscription**.

Đây là cách đọc quan trọng: vị trí của **publishOn** trong chuỗi có ý nghĩa nghiệp vụ và hiệu năng. Việc đặt nó **trước hay sau** một toán tử có thể làm toán tử đó chạy trên thread khác.

## 2. Upstream và downstream là gì?

Trong chuỗi:

~~~text
Flux.range(1, 3)
      |
      v
  map(A)
      |
      v
  doOnNext(B)           <- upstream của publishOn
      |
      v
  publishOn(S1)         <- ranh giới Scheduler
      |
      v
  map(C)
      |
      v
  filter(D)             <- downstream của publishOn
      |
      v
  subscribe()
~~~

**Upstream** là phần phía nguồn dữ liệu; **downstream** là phần tiến tới Subscriber. Khi đọc mã Java từ trên xuống, các bước trước publishOn là upstream, còn các bước sau publishOn là downstream.

Về tín hiệu trong Reactive Streams:

- **onNext, onError và onComplete** thường đi từ **upstream xuống downstream**.
- **subscribe**, **request(n)** và **cancel** có đường đi điều phối hướng ngược hoặc liên quan cả hai chiều. Vì vậy, không nên nói publishOn buộc *mọi callback trong pipeline* chạy trên cùng một thread.
- publishOn chủ yếu thay đổi **ngữ cảnh thực thi khi chuyển tiếp tín hiệu xuống các toán tử phía sau**.
- Với nguồn có cơ chế scheduling riêng, event loop hoặc operator bất đồng bộ khác, vị trí thread có thể phụ thuộc nhiều hơn vào **toàn bộ pipeline** chứ không chỉ một publishOn.

Khái niệm **Scheduler** trong Reactor là lớp trừu tượng về nơi và cách công việc được thực thi: nó có thể dùng thread riêng, pool thread, event loop, hoặc thực thi tức thời tùy loại Scheduler. Không nên đồng nhất Scheduler với “tạo một thread mới cho mỗi phần tử”.

## 3. Chính xác publishOn ảnh hưởng phần nào của pipeline?

### 3.1. Toán tử trước publishOn không tự chuyển theo

~~~java
Flux.range(1, 3)
    .map(this::stepBefore)
    .publishOn(Schedulers.parallel())
    .map(this::stepAfter);
~~~

Ở đây **stepBefore** không được publishOn phía sau chuyển sang parallel. **stepAfter** nhận tín hiệu trên worker của parallel, trừ khi bản thân nó hoặc những phần liên quan có quy tắc scheduling đặc biệt.

Nếu gọi **publishOn sau một lời gọi blocking**, thao tác blocking đó có thể đã chặn thread upstream trước khi publishOn được chạy. Đây là một lỗi bố trí phổ biến:

~~~java
Mono.fromCallable(() -> blockingClient.load())
    .map(this::slowBlockingOperation)  // Chặn thread upstream.
    .publishOn(Schedulers.boundedElastic())
    .map(this::format);
~~~

Đoạn mã minh họa có blockingClient và các phương thức do ứng dụng tự định nghĩa. **publishOn đặt sau slowBlockingOperation không bảo vệ thread đã chạy bước blocking trước đó.**

### 3.2. Toán tử sau publishOn dùng ngữ cảnh mới

~~~java
Flux.range(1, 3)
    .publishOn(Schedulers.parallel())
    .map(this::calculate)
    .doOnNext(this::logResult);
~~~

Với nguồn đồng bộ đơn giản, cả **calculate** và **logResult** thường thực thi trên worker của parallel cho lượt subscription. Điều này hữu ích nếu muốn chuyển một đoạn xử lý khỏi thread nơi dữ liệu được nhận.

### 3.3. publishOn thứ hai đổi ngữ cảnh lần nữa

~~~java
Flux.range(1, 3)
    .map(this::prepare)                    // Upstream
    .publishOn(firstScheduler)
    .map(this::transform)                  // Trên firstScheduler
    .publishOn(secondScheduler)
    .doOnNext(this::saveAudit);            // Trên secondScheduler
~~~

**firstScheduler** và **secondScheduler** ở đây là các Scheduler ứng dụng đã tạo/cấu hình. Trong đường truyền tín hiệu thông thường, transform chịu ảnh hưởng của publishOn thứ nhất; saveAudit chịu ảnh hưởng của publishOn thứ hai. Nếu thêm toán tử sau saveAudit mà không có ranh giới mới, nó tiếp tục trong ngữ cảnh downstream của publishOn thứ hai.

Mỗi publishOn thường tạo một lần chuyển luồng và hàng đợi trung gian; đặt nhiều ranh giới liên tục có thể tăng **context switch, latency và bộ nhớ**. Chỉ thêm khi có lý do rõ ràng về cô lập công việc hoặc khả năng vận hành.

### 3.4. publishOn giữ tính tuần tự tín hiệu trên một subscription

Mặc dù Scheduler có thể là một pool nhiều thread, publishOn chọn một **worker cho mỗi lượt subscription** để chuyển tiếp onNext theo thứ tự. Với một subscription thông thường, các tín hiệu downstream được xử lý tuần tự theo hợp đồng Reactive Streams.

Vì vậy:

- **publishOn(Schedulers.parallel()) không có nghĩa mỗi phần tử được xử lý trên một CPU core khác nhau.**
- Nếu một hàm map() sau publishOn tốn 500 ms CPU thì các phần tử của *subscription đó* vẫn có thể phải chờ lần lượt.
- Nếu cần thực sự phân chia công việc giữa nhiều phần tử, xem các cơ chế khác như **flatMap** với nguồn bất đồng bộ, hoặc **parallel().runOn(...).sequential()** khi phù hợp.
- Nhiều subscription độc lập có thể được phân bổ lên các worker/thread khác nhau và chạy đồng thời, phụ thuộc Scheduler và khả năng xử lý thực tế.

## 4. publishOn và subscribeOn: hai mục đích khác nhau

Hai toán tử đều nhận Scheduler nhưng **tác động vào giai đoạn khác nhau**:

| Tiêu chí | publishOn(scheduler) | subscribeOn(scheduler) |
| --- | --- | --- |
| Ý định chính | Chuyển ngữ cảnh **xử lý tín hiệu downstream** từ vị trí đặt toán tử | Chuyển ngữ cảnh **subscription/khởi chạy nguồn** và những tương tác upstream liên quan |
| Vị trí trong chuỗi | **Quan trọng**: phần sau publishOn chịu ảnh hưởng | Thường ảnh hưởng upstream/source dù đặt ở vị trí nào, với lưu ý về các toán tử có quy tắc riêng |
| Nếu dùng nhiều lần | Mỗi publishOn có thể đặt một ranh giới mới | Thêm nhiều subscribeOn thường không có lợi; subscribeOn gần nguồn nhất trong chuỗi downstream là yếu tố chính quyết định lịch subscribe upstream |
| Tác dụng với xử lý từng phần tử | Chuyển nơi chạy toán tử sau nó | Dịch nơi nguồn và các toán tử không có ranh giới scheduler riêng khởi chạy/xử lý |
| Có làm từng phần tử chạy song song không? | **Không tự động** | **Không tự động** |
| Có biến I/O blocking thành non-blocking không? | Không | Không |

Ví dụ có cả hai:

~~~java
Flux.range(1, 3)
    .map(this::prepare)
    .subscribeOn(sourceScheduler)
    .map(this::processBeforeBoundary)
    .publishOn(processingScheduler)
    .map(this::processAfterBoundary);
~~~

Đây là đoạn minh họa có các biến Scheduler và phương thức ứng dụng.

Với một nguồn đồng bộ như Flux.range:

1. **subscribeOn(sourceScheduler)** bố trí subscription/nguồn ở sourceScheduler; prepare và processBeforeBoundary thường chạy tại ngữ cảnh đó khi không có chuyển đổi khác.
2. **publishOn(processingScheduler)** chuyển onNext xuống processAfterBoundary trên worker của processingScheduler.
3. Đặt **subscribeOn phía dưới publishOn** không có nghĩa nó có thể xóa tác dụng của publishOn. Mọi ranh giới downstream vẫn cần được đọc theo vị trí của nó.
4. Nếu nguồn đã dùng event loop hoặc lịch riêng (chẳng hạn Flux.interval hoặc nguồn mạng), cần xem cơ chế của nguồn thay vì suy luận rằng mọi emission luôn ở thread do subscribeOn chọn.

Quy tắc lựa chọn thực dụng:

- Muốn **khởi chạy nguồn blocking ở nơi được phép blocking**: thường dùng **Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())**.
- Muốn **chuyển một đoạn xử lý phía sau** sang scheduler phù hợp: dùng **publishOn(scheduler)** ngay trước đoạn đó.
- Muốn đồng thời nhiều lời gọi I/O bất đồng bộ: thường nối những Mono bằng các operator kết hợp bất đồng bộ phù hợp; thêm publishOn không tự tạo concurrency nếu bản thân tác vụ vẫn tuần tự.

## 5. Một ví dụ chạy được trên Java 17+: quan sát ba vùng thread

Ví dụ tạo một Flux hữu hạn và hai Scheduler riêng. Nó ghi nhận nơi mỗi toán tử thực thi, nhưng **chỉ in các danh sách sau khi toàn bộ pipeline hoàn tất**. Cách này giúp stdout có thứ tự xác định, ngay cả khi thread nguồn và các worker có thể xen kẽ chạy trong thực tế.

Cấu trúc dự án:

~~~text
reactor-publishon/
├── pom.xml
└── src/main/java/PublishOnDemo.java
~~~

Tệp **pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactor-publishon</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.6.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>PublishOnDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tệp **src/main/java/PublishOnDemo.java**:

~~~java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import reactor.core.publisher.Flux;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

public class PublishOnDemo {
    public static void main(String[] args) {
        Thread callingThread = Thread.currentThread();

        Scheduler transform = Schedulers.newSingle("transform-stage");
        Scheduler audit = Schedulers.newSingle("audit-stage");

        List<String> upstreamSeen = new CopyOnWriteArrayList<>();
        List<String> transformSeen = new CopyOnWriteArrayList<>();
        List<String> auditSeen = new CopyOnWriteArrayList<>();

        try {
            List<Integer> result = Flux.range(1, 3)
                    .hide()
                    .doOnNext(n -> upstreamSeen.add(
                            n + ":caller="
                                    + (Thread.currentThread() == callingThread)
                    ))
                    .publishOn(transform)
                    .map(n -> {
                        transformSeen.add(
                                n + ":transform="
                                        + Thread.currentThread()
                                                .getName()
                                                .startsWith("transform-stage-")
                        );
                        return n * 10;
                    })
                    .publishOn(audit)
                    .doOnNext(n -> auditSeen.add(
                            n + ":audit="
                                    + Thread.currentThread()
                                            .getName()
                                            .startsWith("audit-stage-")
                    ))
                    .collectList()
                    .block();

            System.out.println("upstream = " + upstreamSeen);
            System.out.println("transform = " + transformSeen);
            System.out.println("audit = " + auditSeen);
            System.out.println("result = " + result);
        } finally {
            transform.dispose();
            audit.dispose();
        }
    }
}
~~~

Với **JDK 17+**, Maven và quyền tải dependency cho lần chạy đầu, chạy trong thư mục dự án:

~~~bash
mvn -q compile exec:java
~~~

**Các dòng do chương trình in ra:**

~~~text
upstream = [1:caller=true, 2:caller=true, 3:caller=true]
transform = [1:transform=true, 2:transform=true, 3:transform=true]
audit = [10:audit=true, 20:audit=true, 30:audit=true]
result = [10, 20, 30]
~~~

Giải thích:

1. **Flux.range(1,3)** là nguồn đồng bộ. Khi block() thực hiện subscription trên callingThread, nguồn phát 1, 2, 3 trên thread gọi.
2. **hide()** ở đây cố ý ngăn tối ưu hóa **operator fusion** tại ranh giới nguồn. Điều đó giúp quan sát rõ thread phát tín hiệu upstream trong ví dụ; không cần thêm hide() cho mọi ứng dụng thực tế.
3. **doOnNext trước publishOn(transform)** ghi nhận caller=true.
4. **map sau publishOn(transform)** ghi nhận tên thread bắt đầu bằng transform-stage-, nên transform=true, rồi nhân số với 10.
5. **doOnNext sau publishOn(audit)** chạy trên thread bắt đầu bằng audit-stage-, nên audit=true.
6. **collectList().block()** giúp chương trình console chờ pipeline hoàn tất; sau đó mới in các danh sách. Vì thế các dòng stdout không phụ thuộc thứ tự xen kẽ log của những thread.
7. **CopyOnWriteArrayList** giúp việc ghi nhận an toàn giữa các thread. Với một ví dụ nhỏ nó đơn giản và rõ ràng; không nên mặc định dùng cho dữ liệu rất lớn hoặc cập nhật có tần suất cao.
8. **dispose()** giải phóng hai Scheduler do chương trình tạo. Với Scheduler chia sẻ của Reactor, không nên tự ý dispose scheduler toàn cục thuộc ứng dụng khác.

### Vì sao không in trực tiếp trong từng map?

Nếu đặt **System.out.println** trực tiếp ở ba stage đang chạy trên các thread khác nhau, các dòng có thể xen kẽ theo lịch hệ điều hành. Không nên viết một stdout “chính xác” dựa trên thứ tự in không được bảo đảm. Ví dụ trên **lưu ba danh sách riêng** rồi in sau khi block() hoàn tất, để xác nhận nội dung và thứ tự trong từng stage.

**Lưu ý về block():** Chỉ dùng ở ranh giới của chương trình console minh họa. Trong request handler Spring WebFlux, hãy trả lại **Mono/Flux** và để framework subscribe; không dùng block() hoặc blockLast() để lấy dữ liệu đồng bộ trên event loop.

## 6. Đặt publishOn trước hay sau map: một khác biệt quan trọng

Đặt publishOn **trước** phép tính:

~~~java
Flux<Integer> moved = Flux.range(1, 3)
        .publishOn(Schedulers.parallel())
        .map(this::expensiveCalculation);
~~~

Với nguồn bình thường, **expensiveCalculation** chạy trên worker của parallel. Nếu phép tính này là công việc CPU thuần và đủ đáng kể, việc chuyển khỏi event loop có thể hữu ích, nhưng tất cả phần tử của một subscription vẫn được xử lý tuần tự trên worker đó.

Đặt publishOn **sau** phép tính:

~~~java
Flux<Integer> notMoved = Flux.range(1, 3)
        .map(this::expensiveCalculation)
        .publishOn(Schedulers.parallel());
~~~

Lúc này expensiveCalculation vẫn ở phía upstream. Với nguồn đồng bộ như Flux.range, phép tính có thể chạy ngay trên thread đang thực hiện nguồn/subscription; publishOn phía sau chỉ chuyển những tín hiệu/kết quả đã được tính sang downstream.

Một quy tắc dễ nhớ:

**Đặt publishOn ngay trước vùng bạn muốn thay đổi nơi xử lý**, không đặt sau vùng xử lý đã hoàn tất.

Tuy nhiên, kết luận “chạy ở đâu” cần kiểm tra cả các toán tử đặc biệt ở trước đó. Một nguồn tạo tín hiệu trên thread riêng, Flux.interval hoặc publisher được điều phối qua network event loop có thể đã mang thread riêng vào pipeline.

## 7. Chọn Scheduler nào cho vùng downstream?

Project Reactor cung cấp nhiều Scheduler với mục tiêu khác nhau:

| Scheduler | Mô hình mục tiêu | Cách dùng phù hợp |
| --- | --- | --- |
| **Schedulers.immediate()** | Thực thi tại thread hiện tại, không chuyển sang pool riêng | Khi không muốn thêm ranh giới scheduling thực sự; không dùng để cô lập blocking |
| **Schedulers.single()** | Một thread chia sẻ cho các tác vụ của scheduler chung | Công việc tuần tự nhẹ, cần hiểu nguy cơ tranh chấp với các subscription khác |
| **Schedulers.newSingle("name")** | Scheduler một thread được tạo riêng, có vòng đời do ứng dụng quản lý | Thử nghiệm, vùng xử lý cần thread affinity hoặc phân tách rõ |
| **Schedulers.parallel()** | Pool có số worker hữu hạn, thích hợp xử lý CPU nhanh và không blocking | Chuyển đoạn biến đổi CPU, không dùng cho I/O blocking kéo dài |
| **Schedulers.boundedElastic()** | Có khả năng mở rộng có giới hạn cho các công việc có thể blocking | Cô lập API blocking bắt buộc dùng trong hệ thống reactive |
| **Schedulers.fromExecutorService(...)** | Dùng ExecutorService do ứng dụng cung cấp | Tích hợp pool riêng với giới hạn và vòng đời được quản lý |

**parallel() không biến một map thành xử lý song song trên nhiều thread** chỉ vì có nhiều core. Nó là nơi lập lịch. Muốn xử lý nhiều phần tử song song cần thiết kế rõ concurrency.

**boundedElastic() không làm JDBC blocking hoặc Thread.sleep() thành non-blocking I/O.** Nó dành một môi trường thực thi phù hợp hơn cho đoạn blocking, với giới hạn số luồng và hàng đợi; khi quá tải, vẫn có thể chờ và phát sinh nghẽn.

**single()** có thể biến thành điểm nghẽn nếu nhiều subscription cùng đưa tác vụ nặng lên một thread; newSingle không phải mặc định cho mọi request. Trong service thật, ưu tiên Scheduler chung hoặc Scheduler có lifecycle rõ thay vì tạo newSingle ở mỗi yêu cầu HTTP.

## 8. publishOn và công việc blocking: đặt ranh giới đúng vị trí

### Khi phải gọi thư viện đồng bộ

Với một phương thức **blockingClient.fetch(id)**:

~~~java
Mono<Result> result = Mono.fromCallable(
        () -> blockingClient.fetch(id)
).subscribeOn(Schedulers.boundedElastic());
~~~

Đây là **đoạn minh họa** trong dự án có kiểu Result và blockingClient. **subscribeOn(boundedElastic)** phù hợp vì chính **nguồn** fromCallable gọi hàm blocking khi subscribe; cần đặt việc khởi chạy nguồn ở scheduler có khả năng chịu blocking.

Nếu có nguồn đã non-blocking nhưng một **bước phía sau** buộc phải xử lý blocking:

~~~java
Mono<RemoteData> response = remoteClient.fetchReactive(id);

Mono<FinalData> result = response
        .publishOn(Schedulers.boundedElastic())
        .map(data -> legacyBlockingFormatter.format(data));
~~~

Đây là đoạn minh họa với remoteClient/legacyBlockingFormatter do ứng dụng định nghĩa. publishOn nằm **trước** legacyBlockingFormatter, nên chính bước đó được điều phối sang boundedElastic. Nhưng việc chặn vẫn xảy ra trên một thread boundedElastic; cách này là giải pháp tương thích API, không phải chuyển thao tác thành I/O non-blocking.

### Hai lỗi cần tránh

~~~java
// SAI VỊ TRÍ: công việc blocking chạy trước publishOn.
Mono<Result> wrong = Mono.fromCallable(() -> blockingClient.fetch(id))
        .publishOn(Schedulers.boundedElastic());
~~~

publishOn phía sau không tự chuyển phần tạo nguồn ở trước nó. Với fromCallable chưa có subscribeOn, việc gọi blockingClient có thể thực thi trên thread subscribe, bao gồm event loop nếu được dùng trong một request reactive.

~~~java
// Cũng không đủ: nguồn blocking ngay lúc tạo dữ liệu!
Result value = blockingClient.fetch(id);
Mono<Result> tooLate = Mono.just(value)
        .publishOn(Schedulers.boundedElastic());
~~~

Ở ví dụ thứ hai, Java đã gọi blockingClient.fetch(id) **trước khi tạo Mono**. Không toán tử Reactor nào thêm phía sau có thể đảo ngược thao tác blocking đã xảy ra.

## 9. publishOn có prefetch và hàng đợi: tác động đến backpressure

**publishOn** thường dùng một hàng đợi nội bộ để chuyển tín hiệu từ thread upstream sang worker downstream. Nó có thể **yêu cầu trước một lượng phần tử (prefetch)** rồi tái yêu cầu khi tiêu thụ. Vì thế, lượng request ở biên giữa các operator không nhất thiết trùng 1:1 với request của Subscriber cuối.

Một mô hình đơn giản:

~~~text
Upstream Publisher
       |
       | onNext theo demand do publishOn quản lý
       v
  [publishOn queue]
       |
       | worker của Scheduler nhận tín hiệu
       v
  map / filter / Subscriber downstream
       |
       +--- downstream có thể xử lý chậm hơn upstream
~~~

Các điểm cần hiểu:

- **publishOn vẫn phải tôn trọng hợp đồng Reactive Streams**, quản lý demand và không phát onNext xuống Subscriber vượt số phần tử được yêu cầu.
- **Prefetch** cho phép upstream chuẩn bị thêm dữ liệu để giảm chi phí request từng phần tử, nhưng có thể khiến một số phần tử đã được giữ trong queue dù downstream chưa xử lý.
- Có overload như **publishOn(scheduler, prefetch)** để điều chỉnh lượng yêu cầu trước; giá trị cụ thể cần phù hợp đặc điểm nguồn, độ trễ, kích thước phần tử và tài nguyên.
- **Prefetch không phải cam kết giới hạn bộ nhớ toàn bộ hệ thống**: các operator khác, client/broker và nguồn ngoài vẫn có queue hoặc buffer riêng.
- Nếu nguồn ngoài không hỗ trợ giảm tốc, publishOn không thể ép giao thức bên ngoài thực hiện request(n). Phải có chính sách buffer/drop/error rõ ở ranh giới thích ứng.
- Thêm nhiều publishOn có thể thêm nhiều queue, tăng độ trễ, số phần tử in-flight và công việc lập lịch.

Không nên sửa prefetch theo một con số “tối ưu” chung cho mọi ứng dụng. Hãy đo throughput, latency, độ sâu queue, CPU, GC và hành vi khi downstream bị chậm.

## 10. Tương tác với các toán tử tạo concurrency

### flatMap với nguồn bất đồng bộ

~~~java
Flux<Result> results = ids
        .flatMap(id -> remoteClient.fetchReactive(id), 8)
        .publishOn(Schedulers.parallel())
        .map(this::enrich);
~~~

Đây là đoạn minh họa: ids là Flux ID, remoteClient.fetchReactive(id) trả Publisher, enrich là hàm ứng dụng.

**flatMap(..., 8)** có thể cho tối đa tám inner Publisher hoạt động đồng thời theo tham số concurrency; **publishOn(parallel)** phía sau chỉ đổi nơi xử lý enrich. Không nên ghi rằng publishOn tạo ra tám cuộc gọi bất đồng bộ: sự đồng thời đến từ cách phối hợp Publisher của **flatMap** và API client.

### parallel().runOn(...)

~~~java
Flux<Integer> values = Flux.range(1, 100)
        .parallel(4)
        .runOn(Schedulers.parallel())
        .map(this::cpuBoundTransform)
        .sequential();
~~~

Đoạn minh họa dùng cho tình huống CPU-bound có thể chia tác vụ độc lập. **parallel(4)** chia dữ liệu thành bốn rail; **runOn** phân bổ việc xử lý rail lên scheduler; **sequential()** hợp nhất trở lại Flux. Đây là cơ chế khác publishOn. Cần kiểm tra thứ tự, cách phân bố, overhead và liệu xử lý có thực sự đủ nặng để hưởng lợi.

### Một subscription với publishOn đơn lẻ

~~~java
Flux.range(1, 100)
    .publishOn(Schedulers.parallel())
    .map(this::cpuBoundTransform);
~~~

Pipeline này vẫn có một luồng tín hiệu tuần tự cho subscription đó. Pool parallel có nhiều thread **không có nghĩa 100 phần tử tự chia đều 100 tác vụ**.

## 11. Spring WebFlux, Reactor Netty và ranh giới event loop

Trong một ứng dụng Spring WebFlux chạy trên Reactor Netty, I/O mạng thường được điều phối qua **event loop**. Event loop rất có giá trị khi các thao tác không blocking; vì thế, tránh dùng JDBC blocking, Thread.sleep hoặc các hàm đợi đồng bộ trên những thread đó.

Ví dụ service đang có một Publisher từ HTTP client reactive:

~~~java
public Mono<Report> buildReport(String id) {
    return webClient.get()
            .uri("/reports/{id}", id)
            .retrieve()
            .bodyToMono(ReportData.class)
            .publishOn(Schedulers.parallel())
            .map(this::computeReport);
}
~~~

Đây là **đoạn service minh họa** trong dự án đã có webClient, ReportData và Report; không phải ứng dụng standalone. Nếu computeReport là phép tính CPU tương đối nặng nhưng không blocking, publishOn trước map có thể giúp tránh giữ thread gọi callback mạng cho phần tính toán đó.

**publishOn không di chuyển socket Netty sang một thread Java khác để làm network I/O.** Nó chuyển *các tín hiệu downstream* sang worker Scheduler. Vòng đời kết nối HTTP, backpressure transport và cách framework gửi response vẫn do tầng tương ứng quản lý.

Nếu computeReport rất nặng, một Scheduler CPU chung có thể bị nghẽn; cần đo tải và giới hạn concurrency. Nếu computeReport thực ra chặn I/O, **parallel() không phù hợp**, phải lựa chọn API non-blocking hoặc boundedElastic cho đoạn buộc phải blocking.

### Controller nên trả Publisher

~~~java
@GetMapping("/reports/{id}")
public Mono<Report> getReport(@PathVariable String id) {
    return reportService.buildReport(id);
}
~~~

Framework quản lý subscribe, lỗi và hủy theo vòng đời request. Tránh gọi **subscribe()** thủ công hoặc **block()** trong controller để “đảm bảo publishOn được chạy”: điều đó có thể tách tác vụ khỏi việc xử lý HTTP và phá lợi ích non-blocking.

## 12. ThreadLocal, Reactor Context và ghi log qua ranh giới publishOn

Khi tín hiệu được chuyển từ thread A sang thread B, các giá trị lưu trong **ThreadLocal** của A **không tự động xuất hiện** trong ThreadLocal của B. Vì vậy, ghi log với MDC, mã trace, thông tin request hoặc ngữ cảnh bảo mật có thể mất liên kết nếu ứng dụng chỉ dựa trên ThreadLocal truyền thống.

Reactor có **Context** gắn với subscriber để chuyển thông tin bất biến theo pipeline. Ví dụ khái niệm:

~~~java
Mono<String> message =
        Mono.deferContextual(ctx -> Mono.just(
                "trace=" + ctx.getOrDefault("traceId", "unknown")
        ))
        .publishOn(Schedulers.parallel())
        .map(String::toUpperCase)
        .contextWrite(ctx -> ctx.put("traceId", "demo-123"));
~~~

Đoạn này trả Mono có dữ liệu trace sau khi subscribe và không phụ thuộc ThreadLocal. **contextWrite** đóng góp context mà upstream có thể đọc với **deferContextual**; ngữ nghĩa truyền Context là một chủ đề riêng cần thiết kế với Spring Security/observability tương ứng. **Không nhầm Reactor Context với tự động sao chép mọi ThreadLocal**.

Nếu ứng dụng sử dụng framework tracing/MDC có tính năng context propagation, phải cấu hình và kiểm thử theo stack cụ thể; không mặc định publishOn luôn giữ hoặc luôn làm mất mọi trường log.

## 13. Lỗi, hủy và giới hạn thời gian khi đi qua publishOn

Một pipeline có publishOn vẫn tuân theo các tín hiệu **onNext, onError, onComplete** của Reactor:

~~~java
Flux<Integer> source = Flux.just(1, 2, 3)
        .publishOn(Schedulers.parallel())
        .map(n -> {
            if (n == 2) {
                throw new IllegalArgumentException("invalid");
            }
            return n * 10;
        })
        .onErrorResume(error -> Flux.just(-1));
~~~

Đây là đoạn minh họa. Khi map gặp n=2, chuỗi thất bại và **onErrorResume** chuyển thành Publisher fallback theo chính sách ở đây. publishOn **không nuốt lỗi** và không tự retry.

Với cancel:

- Nếu Subscriber hủy, các toán tử trong đường truyền cần ngừng nhận/phát theo hợp đồng và giải phóng tài nguyên phù hợp.
- Các phần tử đã được request/prefetch hoặc công việc đã xếp lịch có thể đang nằm trong queue hay đang chạy. **Cancel không phải lệnh làm mọi hoạt động ngoài hệ thống dừng tức thời.**
- Nếu tác vụ downstream thực hiện side effect, cần xác định chính sách retry/hủy/idempotency; chuyển thread không làm thao tác trở thành transaction.
- Nếu cần timeout, đặt **timeout(...)** theo yêu cầu nghiệp vụ; publishOn không tự đặt deadline cho request.

Một lỗi rất phổ biến là giả định “đã publishOn thì có thể gọi block() ở bất cứ đâu”. **publishOn không làm block() an toàn trên mọi thread**. Nếu toán tử đang chạy trên non-blocking scheduler như parallel/single, gọi các thao tác blocking của Reactor có thể bị từ chối hoặc gây nghẽn. Sử dụng API không blocking hoặc cô lập đoạn blocking đúng cách.

## 14. Kiểm thử publishOn theo điều có thể bảo đảm

### Kiểm thử giá trị của pipeline

Với dependency **reactor-test**, có thể dùng StepVerifier:

~~~java
StepVerifier.create(
        Flux.range(1, 3)
            .publishOn(Schedulers.parallel())
            .map(n -> n * 10)
)
.expectNext(10, 20, 30)
.verifyComplete();
~~~

Đây là **đoạn đặt trong test đã có import Reactor và reactor-test**, không phải chương trình Java độc lập. Nó xác minh **giá trị/thứ tự/onComplete**, không xác minh chính xác tên thread.

### Kiểm thử nơi thực thi

Nếu mục tiêu là chứng minh toán tử sau publishOn chuyển sang Scheduler được chỉ định:

1. Dùng **Scheduler có tên riêng** do test quản lý.
2. Ghi nhận thread hoặc cờ thread ở **toán tử trước và sau** publishOn.
3. Đồng bộ đến khi nguồn hoàn tất bằng StepVerifier hoặc cơ chế phù hợp.
4. Kiểm tra **vùng phía trước/vùng phía sau**, không so sánh các dòng log in xen kẽ từ nhiều thread.
5. Giải phóng Scheduler do test tự tạo.

Ví dụ Java 17+ ở trên thực hiện điều này bằng hai scheduler đặt tên và các danh sách ghi nhận có thứ tự ổn định. **Không lấy tên thread như “parallel-1” làm bảo đảm công khai của ứng dụng**: tên và cách phân bổ có thể thay đổi theo cấu hình, phiên bản hoặc runtime. Cần kiểm tra Scheduler/worker tại điểm phát tín hiệu, không dựa vào một tên thread ngẫu nhiên.

### Những ca tải và hiệu năng cần thử

- **CPU-bound**: đo thời gian xử lý map trước/sau publishOn, throughput và độ trễ P95/P99.
- **Tác vụ blocking**: xác minh không chạy trên event loop/parallel và không làm cạn boundedElastic.
- **Downstream chậm**: quan sát prefetch/queue, memory, backpressure và cancellation.
- **Nhiều subscription**: xem Scheduler có bị tranh chấp hoặc thiếu worker không.
- **Có nhiều publishOn**: đo overhead chuyển thread có vượt lợi ích cô lập tác vụ không.
- **MDC/Context**: xác minh trace/request metadata vẫn đúng qua ranh giới.
- **Lỗi và hủy**: bảo đảm tín hiệu được chuyển đúng, không sinh subscription hoặc side effect lặp ngoài dự kiến.

## 15. Những hiểu sai thường gặp

| Hiểu sai | Cách hiểu đúng |
| --- | --- |
| “Tất cả toán tử trong Flux chạy trên thread của publishOn.” | **Chỉ phần downstream** chịu ảnh hưởng của publishOn đó, cho đến ranh giới scheduling khác. |
| “Đặt publishOn sau một hàm blocking sẽ chuyển hàm đó.” | Hàm **đứng trước** publishOn có thể đã chạy; đặt ranh giới trước bước cần chuyển hoặc dùng subscribeOn cho nguồn blocking. |
| “Schedulers.parallel() khiến mỗi onNext song song với nhau.” | Một publishOn thường dùng **một worker cho một subscription**, giữ onNext tuần tự. |
| “publishOn và subscribeOn thay thế cho nhau.” | subscribeOn liên quan subscription/nguồn; publishOn chuyển xử lý downstream theo vị trí. |
| “Mỗi publishOn luôn tạo một thread mới.” | Nó chọn worker từ Scheduler; có thể dùng thread chia sẻ hoặc thread riêng tùy Scheduler. |
| “publishOn làm I/O trở thành non-blocking.” | Đổi nơi xử lý không thay đổi bản chất API blocking. |
| “publishOn chuyển network socket của WebClient/Netty.” | Nó chuyển xử lý tín hiệu downstream, không tự đổi cơ chế event loop của I/O mạng. |
| “Thêm nhiều publishOn luôn nhanh hơn.” | Có overhead queue, scheduling và context switch; cần đo hiệu năng. |
| “Có publishOn thì dữ liệu không mất và không đầy bộ nhớ.” | Backpressure/prefetch và nguồn ngoài cần được xem xét độc lập; vẫn có thể có queue lớn hoặc overflow. |
| “ThreadLocal tự truyền sang mọi thread.” | Cần Reactor Context hoặc cơ chế context propagation được cấu hình. |
| “block() sẽ an toàn vì đã chuyển scheduler.” | Blocking vẫn có thể bị cấm/gây nghẽn trên scheduler không phù hợp. |

## 16. Checklist đặt publishOn trong thực tế

Khi định thêm publishOn vào một service Spring WebFlux, hãy trả lời:

1. **Toán tử nào thật sự cần đổi nơi thực thi?** Đặt publishOn **trước** toán tử đó.
2. **Upstream đang phát trên thread nào?** Nguồn đồng bộ, event loop, fromCallable, Flux.interval hoặc nguồn có scheduler riêng có thể khác nhau.
3. **Tác vụ phía sau thuộc loại nào?** CPU thuần, I/O bất đồng bộ hay I/O blocking? Chọn parallel, boundedElastic hoặc không cần chuyển tương ứng.
4. **Có cần song song theo phần tử không?** Nếu cần, publishOn đơn lẻ không đủ; thiết kế concurrency bằng operator thích hợp.
5. **Có bao nhiêu ranh giới chuyển thread?** Mỗi publishOn có thể thêm queue/overhead.
6. **Context/trace có đi theo request không?** Kiểm thử MDC, tracing và Reactor Context.
7. **Nguồn có thể vô hạn hay downstream rất chậm không?** Kiểm soát prefetch, bộ đệm, giới hạn tải và hủy.
8. **Kết quả/test có phụ thuộc tên thread hay thứ tự log?** Dùng scheduler đặt tên và cơ chế quan sát có đồng bộ, thay vì đoán từ log xen kẽ.

## 17. Ghi nhớ

**publishOn(scheduler)** đặt một **ranh giới thay đổi thread xử lý tín hiệu downstream** trong Reactor. Các toán tử **trước** publishOn không tự bị chuyển ngược lại; các toán tử **sau** thường nhận tín hiệu trên worker của Scheduler đã chọn **cho đến publishOn tiếp theo**. **subscribeOn** lại nhắm vào giai đoạn subscription và việc khởi chạy upstream.

**Một publishOn không tự song song hóa từng phần tử, không biến I/O blocking thành non-blocking và không bảo đảm an toàn bộ nhớ.** Chọn Scheduler theo công việc, đặt ranh giới đúng chỗ, kiểm tra prefetch và đo hiệu năng thật. Trong Spring WebFlux, bảo vệ event loop bằng API non-blocking hoặc cách cô lập blocking phù hợp, và trả Mono/Flux để framework quản lý.

**Tài liệu tham khảo:**
- [Project Reactor Reference — Threading and Schedulers: publishOn và subscribeOn](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html)
- [Project Reactor Reference — How do I ensure thread affinity using publishOn?](https://projectreactor.io/docs/core/release/reference/faq.html)
- [Project Reactor API — Flux.publishOn](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html)

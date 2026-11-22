# Hủy subscription, tín hiệu hoàn tất và lan truyền cancellation

## 1. Bối cảnh và mục tiêu

RSocket dùng mô hình Reactive Streams để truyền dữ liệu bất đồng bộ qua mạng. Trong Spring Framework, các API RSocket thường làm việc với Reactor: **Mono** biểu diễn tối đa một kết quả, còn **Flux** biểu diễn một chuỗi có thể có từ 0 đến nhiều kết quả. Khi ứng dụng không còn cần một luồng đang chạy, nó có thể hủy subscription. Việc hủy cần đi từ subscriber qua các operator, tới publisher nguồn và, với một request RSocket đang hoạt động, tới đầu bên kia của kết nối.

Bài này tập trung vào ba khái niệm cần phân biệt:

- **Hoàn tất (completion):** publisher kết thúc thành công và phát tín hiệu **onComplete**.
- **Lỗi (error):** publisher kết thúc do lỗi và phát **onError**.
- **Hủy (cancellation):** subscriber yêu cầu publisher dừng phát dữ liệu bằng **Subscription.cancel()**.

Cancellation không phải một dạng completion. Hai trạng thái có thể xuất hiện ở hai vị trí khác nhau trong cùng một pipeline: một operator có thể hủy nguồn upstream rồi tự phát onComplete cho downstream.

Sau bài học, bạn có thể đọc vòng đời một subscription, phân biệt các tín hiệu, theo dõi cancellation trong Reactor, giải thích frame CANCEL của RSocket và triển khai cleanup trong handler Spring.

## 2. Vòng đời subscription trong Reactive Streams

Một **Publisher** phát dữ liệu; một **Subscriber** nhận dữ liệu. Khi subscriber đăng ký, publisher gọi **onSubscribe(Subscription)** và trao cho subscriber một đối tượng Subscription. Subscriber dùng đối tượng đó để yêu cầu dữ liệu hoặc hủy quan hệ đăng ký.

Luồng cơ bản:

~~~text
Publisher -- onSubscribe(subscription) --> Subscriber
Subscriber -- request(n) ----------------> Subscription / Publisher
Publisher -- onNext(value) ---------------> Subscriber   (0 hoặc nhiều lần)
Publisher -- onComplete() ----------------> Subscriber   (kết thúc thành công)
Publisher -- onError(error) --------------> Subscriber   (kết thúc do lỗi)

Subscriber -- cancel() -------------------> Subscription / Publisher
~~~

Các thành phần và tín hiệu:

| Thành phần / tín hiệu | Ý nghĩa |
| --- | --- |
| **Publisher** | Nguồn phát dữ liệu, ví dụ Flux hoặc Mono. |
| **Subscriber** | Thành phần tiêu thụ dữ liệu. |
| **Subscription** | Quan hệ giữa một Publisher và một Subscriber; cung cấp request và cancel. |
| **onSubscribe** | Thông báo subscription đã được thiết lập và trao Subscription cho subscriber. |
| **request(n)** | Yêu cầu publisher phát thêm tối đa n phần tử. n phải lớn hơn 0. |
| **onNext(value)** | Phát một phần tử dữ liệu. |
| **onComplete()** | Kết thúc thành công; sau đó không còn phần tử hay tín hiệu lỗi của subscription đó. |
| **onError(error)** | Kết thúc do lỗi; đây cũng là tín hiệu terminal. |
| **cancel()** | Yêu cầu publisher dừng phát dữ liệu và thu hồi tài nguyên của subscription. |

### 2.1. request(n) là điều khiển nhu cầu, không phải hủy

Reactive Streams dùng backpressure để subscriber điều khiển lượng dữ liệu mà publisher được phép gửi. Subscriber có thể gọi request(5), sau đó request(3); publisher có thể phát tối đa tổng cộng tám phần tử theo nhu cầu đã cấp, miễn là subscription chưa kết thúc.

Không có nhu cầu mới không đồng nghĩa với cancellation. Nếu subscriber chưa gọi request thêm, publisher phải chờ nhu cầu; subscription vẫn có thể còn hoạt động. Ngược lại, cancel yêu cầu kết thúc quan hệ truyền dữ liệu, không chỉ tạm dừng phát.

### 2.2. onComplete và onError là tín hiệu terminal

Một publisher có thể phát 0 hoặc nhiều onNext, rồi kết thúc bằng đúng một trong hai tín hiệu:

- **onComplete:** chuỗi kết thúc thành công. Chuỗi có thể rỗng, nghĩa là không có onNext nào trước đó.
- **onError:** chuỗi kết thúc do lỗi. Sau tín hiệu này, publisher không tiếp tục chuỗi cũ.

Với Reactor, Mono phát tối đa một onNext rồi onComplete, hoặc chỉ onComplete nếu rỗng; nếu lỗi thì phát onError. Mono<Void> thường biểu diễn một thao tác chỉ cần báo hoàn tất mà không trả dữ liệu.

Sau khi subscriber nhận onComplete hoặc onError, subscription được xem là đã kết thúc. Subscriber không cần gọi cancel để xác nhận lại một chuỗi đã terminal.

### 2.3. cancel là yêu cầu từ subscriber

**Subscription.cancel()** là lời yêu cầu publisher ngừng phát dữ liệu và giải phóng tài nguyên liên quan. Đây là thao tác điều khiển theo chiều subscriber → publisher, không phải một tín hiệu onComplete hoặc onError được gửi xuống subscriber.

Cancellation có tính bất đồng bộ. Publisher có thể cần thời gian để nhận biết yêu cầu và dừng công việc. Vì vậy subscriber phải chấp nhận khả năng một số onNext đã được yêu cầu trước đó vẫn đến trong lúc cancellation đang lan truyền. Không nên giả định rằng mọi công việc ở nguồn đã dừng ngay tại thời điểm gọi cancel.

Cancellation cũng không hoàn tác các side effect đã thực hiện. Nếu nguồn đã ghi dữ liệu vào cơ sở dữ liệu hoặc gọi dịch vụ bên ngoài, cancel không tự động rollback những hành động đó.

## 3. Cancellation và completion trong Reactor

Reactor triển khai Reactive Streams bằng **Flux** và **Mono**. Cancellation có thể xuất phát trực tiếp từ code ứng dụng hoặc do một operator quyết định rằng dữ liệu upstream không còn cần thiết.

Một số tình huống thường gặp:

- Người dùng rời màn hình và ứng dụng gọi **Disposable.dispose()** trên subscription.
- **take(n)** đã nhận đủ n phần tử nên hủy nguồn upstream.
- **next()** chỉ lấy phần tử đầu tiên từ một Flux rồi hủy phần còn lại.
- **timeout** chuyển sang nhánh dự phòng sau khi thời gian chờ hết và hủy nguồn đang chờ.
- **switchMap** chuyển sang publisher con mới và hủy publisher con trước đó.

### 3.1. Các hook quan sát vòng đời

| Operator | Được gọi khi nào? | Dùng cho |
| --- | --- | --- |
| **doOnNext** | Mỗi khi có dữ liệu | Ghi log hoặc quan sát phần tử. |
| **doOnComplete** | Khi chuỗi hoàn tất thành công | Xử lý riêng trường hợp hoàn tất. |
| **doOnError** | Khi chuỗi kết thúc do lỗi | Ghi log hoặc đếm lỗi. |
| **doOnCancel** | Khi subscription bị hủy | Phản ứng riêng với cancellation. |
| **doFinally** | Khi kết thúc bởi complete, error hoặc cancel | Cleanup hoặc ghi nhận kiểu kết thúc chung. |

**doOnCancel** chỉ chạy khi có cancellation. Handler của nó được thực thi trước khi tín hiệu cancel tiếp tục lan lên nguồn upstream.

**doFinally** nhận một **SignalType** cho biết nguyên nhân kết thúc: **ON_COMPLETE**, **ON_ERROR** hoặc **CANCEL**. Callback được gọi sau khi tín hiệu terminal tương ứng đã được truyền xuống downstream. Vì vậy callback doFinally phù hợp để ghi nhận mọi kiểu kết thúc và thực hiện cleanup chung.

Không nên chỉ dùng doOnComplete để giải phóng tài nguyên của một stream có thể bị hủy. Nếu subscriber hủy stream, doOnComplete không chạy. Hãy dùng doFinally hoặc cơ chế quản lý tài nguyên phù hợp để xử lý cả ba trường hợp.

Ví dụ quan sát một nguồn bị hủy:

~~~java
Flux.range(1, 5)
    .doOnCancel(() -> log.info("Nguồn nhận cancellation"))
    .doFinally(signal -> log.info("Nguồn kết thúc: {}", signal))
    .take(2)
    .doOnComplete(() -> log.info("Chuỗi downstream hoàn tất"));
~~~

Sau khi nhận hai phần tử, take(2) hủy subscription upstream. Nguồn quan sát cancellation, trong khi take(2) phát onComplete cho downstream vì nó đã hoàn thành nhiệm vụ lấy đủ hai phần tử. Đây là ví dụ cho thấy cancellation upstream và completion downstream không mâu thuẫn.

### 3.2. Cleanup tài nguyên

Đặt cleanup vào đúng vị trí trong pipeline:

- Dùng **doOnCancel** khi cần thực hiện hành động chỉ dành cho cancellation, ví dụ ghi metric hoặc báo rằng client đã rời stream.
- Dùng **doFinally** khi cleanup phải chạy dù chuỗi complete, error hay cancel.
- Với tài nguyên được tạo riêng cho mỗi subscription, ưu tiên các operator quản lý vòng đời tài nguyên như **using** hoặc **usingWhen** thay vì tự mở tài nguyên lúc dựng pipeline rồi hy vọng một callback sẽ luôn đóng đúng cách.

Callback cleanup nên ngắn và không chặn thread xử lý tín hiệu. Nếu cần thao tác cleanup bất đồng bộ, hãy dùng cơ chế quản lý tài nguyên bất đồng bộ thay vì thực hiện một tác vụ blocking kéo dài trong doOnCancel hoặc doFinally.

## 4. RSocket biểu diễn cancellation trên wire như thế nào?

RSocket mang các tương tác Reactive Streams qua một kết nối mạng. Các vai trò trong một request là **requester** (bên mở request) và **responder** (bên nhận request). Một kết nối có thể có request theo cả hai chiều; vì vậy requester không nhất thiết luôn là ứng dụng client.

### 4.1. Frame CANCEL

Khi requester hủy một request RSocket còn hoạt động, giao thức dùng frame **CANCEL**, có mã loại **0x09** và chứa **stream ID** của request cần hủy.

- Requester gửi CANCEL thì stream được kết thúc ở requester.
- Khi responder nhận CANCEL, stream tương ứng được kết thúc ở responder.
- CANCEL tác động lên stream có stream ID đó; nó không có nghĩa là đóng toàn bộ kết nối RSocket.

Với Request-Response, requester có thể hủy trước khi nhận response; theo đặc tả, responder kết thúc stream và không nên gửi response sau khi đã nhận CANCEL. Với Request-Stream, requester có thể hủy trong khi đang nhận các PAYLOAD. Với Request-Channel, requester cũng có thể hủy channel đang hoạt động.

### 4.2. Phân biệt CANCEL, REQUEST_N và COMPLETE

Ba khái niệm này có mục đích khác nhau:

| Frame / cờ | Ý nghĩa |
| --- | --- |
| **REQUEST_N (0x08)** | Cấp thêm credit để responder gửi số PAYLOAD tương ứng. Đây là backpressure. |
| **CANCEL (0x09)** | Hủy request đang hoạt động theo stream ID. |
| **COMPLETE** | Báo một chiều của stream đã hoàn tất thành công. |

Trong frame **PAYLOAD**, RSocket có hai cờ quan trọng:

- **N (Next):** frame chứa một phần tử dữ liệu, tương ứng onNext.
- **C (Complete):** báo hoàn tất, tương ứng onComplete.

Các tổ hợp hợp lệ thường gặp:

| Cờ N | Cờ C | Ý nghĩa |
| --- | --- | --- |
| Có | Không | Có dữ liệu, stream tiếp tục. |
| Không | Có | Chỉ báo hoàn tất, không kèm phần tử dữ liệu. |
| Có | Có | PAYLOAD cuối cùng đồng thời mang phần tử dữ liệu và báo hoàn tất. |

Vì vậy, COMPLETE không phải một frame riêng biệt trong mọi trường hợp: nó có thể được biểu diễn bằng cờ C trong PAYLOAD. CANCEL là frame riêng và mang ý nghĩa hủy request.

### 4.3. Request-Stream và Request-Channel

**Request-Stream** gửi một request ban đầu và nhận một chuỗi response. Requester cấp nhu cầu ban đầu trong REQUEST_STREAM, sau đó có thể gửi REQUEST_N để yêu cầu thêm phần tử. Nếu không cần stream nữa, requester gửi CANCEL.

**Request-Channel** cho phép hai phía gửi chuỗi dữ liệu. Mỗi chiều có thể hoàn tất độc lập:

- COMPLETE từ requester nghĩa là requester không gửi thêm dữ liệu đầu vào. Responder vẫn có thể tiếp tục gửi response.
- COMPLETE từ responder nghĩa là responder đã kết thúc chiều response. Requester có thể đã hoàn tất chiều gửi của mình hoặc vẫn đang gửi.
- Nếu không có ERROR hoặc CANCEL, channel kết thúc khi cả hai phía đã hoàn tất.
- CANCEL từ requester kết thúc stream ở responder.

Đừng nhầm việc requester gửi COMPLETE với việc requester hủy toàn bộ channel. COMPLETE đóng chiều gửi của requester; CANCEL kết thúc request đang hoạt động.

### 4.4. Chuỗi lan truyền cancellation

Với một Request-Stream trong Spring, luồng xử lý thường diễn ra như sau:

~~~text
Ứng dụng requester
    |
    | Disposable.dispose() hoặc operator hủy subscription
    v
Subscription.cancel()
    |
    v
RSocket requester gửi CANCEL(streamId)
    |
    v
RSocket responder nhận CANCEL
    |
    v
Subscription của publisher trong handler bị hủy
    |
    +--> doOnCancel(...)
    |
    +--> doFinally(SignalType.CANCEL)
    |
    v
Nguồn upstream dừng công việc và giải phóng tài nguyên
~~~

Đây là đường đi logic. Thời điểm dừng thực tế phụ thuộc vào việc cancellation đã tới responder hay chưa và publisher nguồn có hợp tác với cancellation hay không. Dữ liệu đã được gửi hoặc đang trên đường truyền có thể đã được xử lý trước khi responder nhận CANCEL.

## 5. Áp dụng trong Spring Framework

Spring hỗ trợ requester qua **RSocketRequester** và responder qua các method **@MessageMapping**. Kiểu tương tác được xác định từ số lượng dữ liệu đầu vào và đầu ra:

- Một đầu vào, nhiều đầu ra (ví dụ Flux) tương ứng Request-Stream.
- Nhiều đầu vào (publisher nhiều phần tử) tương ứng Request-Channel; đầu ra có thể là rỗng, một phần tử hoặc nhiều phần tử.
- Một đầu vào, một đầu ra (ví dụ Mono) tương ứng Request-Response.

### 5.1. Hủy stream từ phía requester

Ví dụ dưới đây giả định **requester** đã được cấu hình và kết nối:

~~~java
import reactor.core.Disposable;
import reactor.core.publisher.Flux;

Flux<String> updates = requester.route("updates.live")
    .data("orders")
    .retrieveFlux(String.class);

Disposable subscription = updates
    .doFinally(signal ->
        System.out.println("Client stream ended: " + signal))
    .subscribe(
        value -> System.out.println("Update: " + value),
        error -> System.err.println("Stream error: " + error),
        () -> System.out.println("Stream completed")
    );

// Gọi khi người dùng rời màn hình hoặc không còn cần dữ liệu:
subscription.dispose();
~~~

**retrieveFlux** trả về Flux cho response dạng stream. **subscribe** bắt đầu tiêu thụ dữ liệu và trả về Disposable. Khi ứng dụng gọi dispose trước khi stream tự kết thúc, Reactor hủy subscription; với request RSocket còn hoạt động, việc hủy được truyền qua giao thức để kết thúc stream tương ứng.

Nếu stream đã complete hoặc error trước khi dispose được gọi, subscription đã terminal; dispose không biến completion thành cancellation.

### 5.2. Quan sát cancellation trong responder

Một handler có thể đặt hook trực tiếp trên publisher được trả về:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;

@Controller
class LiveUpdatesController {

    private final UpdateService updateService;

    LiveUpdatesController(UpdateService updateService) {
        this.updateService = updateService;
    }

    @MessageMapping("updates.live")
    public Flux<String> liveUpdates(@Payload String topic) {
        return updateService.streamFor(topic)
            .doOnCancel(() ->
                System.out.println("Requester cancelled topic: " + topic))
            .doFinally(signal ->
                System.out.println("Responder stream ended: " + signal));
    }
}
~~~

Đây là phần handler trong một ứng dụng Spring đã có bean UpdateService. **streamFor(topic)** cần trả về một publisher có thể hợp tác với cancellation. Khi requester hủy request, cancellation được truyền tới publisher mà handler trả về; doOnCancel và doFinally có thể quan sát việc đó.

Hãy trả publisher từ handler và nối các thao tác bằng operator. Tránh gọi subscribe() bên trong handler rồi trả về một publisher khác. Một subscription tự tạo bằng subscribe() nằm ngoài vòng đời của request RSocket; việc requester hủy request không tự động hủy subscription tách rời đó. Điều này có thể khiến tác vụ nền tiếp tục chạy và giữ tài nguyên sau khi client đã rời stream.

## 6. Ví dụ Reactor chạy độc lập: take hủy nguồn upstream

Ví dụ này dùng Reactor Core để chứng minh sự khác nhau giữa cancellation upstream và completion downstream. Nó không mở kết nối RSocket; phần ánh xạ sang frame CANCEL được giải thích ở trên.

### 6.1. Cấu hình Maven

Tạo project Maven với file **pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>reactor-cancel-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.8.8</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 6.2. Chương trình Java

Tạo file **src/main/java/CancellationDemo.java**:

~~~java
import reactor.core.publisher.Flux;

public class CancellationDemo {

    public static void main(String[] args) {
        Flux.range(1, 5)
            .doOnCancel(() ->
                System.out.println("source: doOnCancel"))
            .doFinally(signal ->
                System.out.println("source: doFinally=" + signal))
            .take(2)
            .doOnComplete(() ->
                System.out.println("downstream: doOnComplete"))
            .subscribe(value ->
                System.out.println("onNext=" + value));
    }
}
~~~

Chạy bằng Java 17+ và Maven:

~~~bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.5.1:java -Dexec.mainClass=CancellationDemo
~~~

Stdout:

~~~text
onNext=1
onNext=2
source: doOnCancel
source: doFinally=CANCEL
downstream: doOnComplete
~~~

Giải thích thứ tự:

1. **Flux.range(1, 5)** tạo nguồn có năm số.
2. **take(2)** chỉ cần hai phần tử. Sau onNext thứ hai, operator hủy subscription của nguồn upstream.
3. **doOnCancel** ở phía nguồn nhận biết cancellation.
4. **doFinally** ở phía nguồn nhận SignalType.CANCEL.
5. **take(2)** đã lấy đủ dữ liệu mà nó cần nên phát onComplete cho downstream; doOnComplete phía downstream chạy.

Kết quả này chứng minh một pipeline có thể ghi nhận CANCEL ở nguồn upstream nhưng vẫn phát onComplete ở phía downstream. Operator take đã kết thúc thành công nhiệm vụ của chính nó sau khi hủy nguồn.

## 7. Lỗi thường gặp và cách xử lý

| Lỗi | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| Chỉ dùng doOnComplete để cleanup | Hook này không chạy khi subscription bị hủy. | Dùng doFinally cho cleanup chung hoặc doOnCancel cho xử lý riêng cancellation. |
| Xem cancel như onError | Cancellation không phải lỗi ứng dụng và không phát onError chỉ vì bị hủy. | Ghi nhận riêng SignalType.CANCEL. |
| Xem cancel như onComplete | cancel là yêu cầu từ subscriber; onComplete là kết quả hoàn tất thành công từ publisher. | Phân biệt tín hiệu điều khiển với tín hiệu terminal. |
| Xem request(0) hoặc không request thêm là hủy | Không có nhu cầu mới chỉ khiến publisher chưa được yêu cầu phát thêm; stream có thể vẫn mở. | Gọi cancel khi không còn cần stream. |
| Gọi subscribe() bên trong handler rồi bỏ subscription | Công việc tách khỏi subscription do RSocket quản lý. | Trả publisher đã compose từ handler để cancellation truyền ngược về nguồn. |
| Giả định cancel dừng mọi việc ngay lập tức | Tín hiệu cần thời gian lan truyền; dữ liệu đang xử lý hoặc đang truyền có thể còn tồn tại. | Viết nguồn có thể hợp tác với cancellation và cleanup an toàn khi có race. |
| Cho rằng CANCEL đóng cả kết nối | CANCEL có stream ID và kết thúc request tương ứng. | Chỉ xử lý stream bị hủy; quản lý connection riêng. |
| Dùng COMPLETE để đóng toàn bộ Request-Channel | COMPLETE từ một phía chỉ hoàn tất chiều gửi của phía đó. | Chờ COMPLETE ở cả hai phía hoặc xử lý ERROR/CANCEL theo giao thức. |
| Cho rằng cancel hoàn tác side effect | Cancellation không rollback thao tác đã thực hiện. | Thiết kế thao tác có tính idempotent, bù trừ hoặc transaction nếu nghiệp vụ yêu cầu. |

## 8. Quy trình kiểm tra cancellation trong ứng dụng

Khi điều tra một stream không dừng sau khi client rời đi, kiểm tra theo thứ tự:

1. **Requester:** xác nhận code thật sự gọi dispose hoặc một operator thực sự hủy subscription.
2. **Reactor phía requester:** đặt doFinally để phân biệt ON_COMPLETE, ON_ERROR và CANCEL.
3. **RSocket:** xác định đúng request/stream ID và kiểm tra requester có gửi CANCEL cho stream đang hoạt động hay không.
4. **Responder:** đặt doOnCancel và doFinally ngay trên publisher được handler trả về.
5. **Nguồn upstream:** kiểm tra nguồn có phản ứng với Subscription.cancel và có giải phóng timer, listener, cursor, socket hoặc tài nguyên tương tự hay không.
6. **Subscription tách rời:** tìm các lệnh subscribe() tự phát, Future hoặc tác vụ nền không được nối với publisher của request.
7. **Race và side effect:** xác định phần dữ liệu hoặc công việc đã bắt đầu trước khi cancellation tới, rồi bảo đảm cleanup không chạy lặp gây lỗi.

Một bài kiểm tra hữu ích nên bao gồm ít nhất ba trường hợp riêng: stream tự complete, stream phát error và requester chủ động cancel. Xác nhận hook phù hợp được gọi cho từng trường hợp, đồng thời xác nhận tài nguyên được giải phóng. Không dùng một bộ đếm completion để đại diện cho cancellation.

## 9. Ghi nhớ

- **request(n)** điều khiển nhu cầu; **cancel()** yêu cầu dừng subscription.
- **onComplete** báo kết thúc thành công; **onError** báo kết thúc do lỗi; **cancel** là thao tác điều khiển từ subscriber.
- Trong Reactor, **doOnCancel** dành cho cancellation; **doFinally** nhận biết complete, error và cancel.
- Trong RSocket, requester hủy một request đang hoạt động bằng frame **CANCEL (0x09)** gắn với stream ID.
- **REQUEST_N** là backpressure; **COMPLETE** là kết thúc thành công một chiều; **CANCEL** kết thúc request.
- Với Request-Channel, COMPLETE từ một phía không tự động đóng chiều còn lại.
- Để cancellation lan truyền trong Spring, hãy trả publisher từ handler và tránh tạo subscription tách rời.

## 10. Tài liệu tham khảo

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): các interaction model, RSocketRequester và @MessageMapping.
- [RSocket Protocol](https://rsocket.io/about/protocol/): frame CANCEL, PAYLOAD với cờ COMPLETE/NEXT, vòng đời Request-Stream và Request-Channel.
- [Reactive Streams for the JVM](https://github.com/reactive-streams/reactive-streams-jvm): hợp đồng Publisher, Subscriber, Subscription, request và cancel.
- [Reactor Core — Mono API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html): doOnCancel, doFinally và các tín hiệu kết thúc.
- [Reactor Core — Reference Guide](https://projectreactor.io/docs/core/release/reference/): cách sử dụng operator và quản lý vòng đời publisher.

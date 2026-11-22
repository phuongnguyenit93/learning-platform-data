# Giới hạn điều tiết xuyên HTTP, bộ đệm mạng và phía khách

**Chủ đề:** Spring Framework Reactive — **Backpressure**.

Reactive Streams giúp một `Subscriber` thông báo nhu cầu qua `Subscription.request(n)`, nhờ đó một `Publisher` tuân thủ hợp đồng không gửi quá số phần tử đã được yêu cầu. Tuy nhiên, một phản hồi HTTP phải đi qua **codec, hàng đợi ghi của HTTP server, bộ đệm socket của hệ điều hành, mạng, proxy và thư viện phía khách**. Ở những ranh giới này, cơ chế điều tiết có thể chuyển từ **đếm phần tử** sang **đếm byte**, đi qua bộ đệm riêng, bị dịch sang tín hiệu transport khác, hoặc không còn được phản ánh trực tiếp tới producer ban đầu.

Vì vậy, câu hỏi khi thiết kế Spring WebFlux không chỉ là “Flux có backpressure không?”, mà là: **khi khách đọc chậm, dữ liệu đang nằm ở đâu, bộ đệm nào có giới hạn, ai có thể làm chậm nguồn phát, và chuyện gì xảy ra khi mọi giới hạn đều chạm ngưỡng?**

Bài này phân biệt rõ điều gì Reactive Streams bảo đảm, điều gì HTTP/TCP điều tiết được, điều gì client thật sự kiểm soát, và cách xử lý ứng dụng streaming an toàn khi có khách chậm hoặc mất kết nối.

## 1. Ranh giới quan trọng: request(n) không phải một thông điệp HTTP

Trong Reactive Streams, mỗi `Subscription` nối **một Publisher với một Subscriber**. Subscriber gọi `request(n)` để cho biết được phép nhận thêm tối đa `n` tín hiệu `onNext`. Hợp đồng cơ bản:

- `request(n)` là **nhu cầu số phần tử**, không phải byte/giây, số HTTP frame hay số gói TCP.
- Publisher không được phát nhiều `onNext` hơn tổng demand chưa dùng. Nó có thể phát ít hơn và hoàn tất.
- `cancel()` yêu cầu dừng subscription; hiệu lực tới I/O, producer hoặc tài nguyên bên ngoài còn phụ thuộc adapter/source.
- Operator như `buffer`, `publishOn`, `flatMap`, `limitRate` có thể **thay đổi lượng request gửi lên upstream**; request của subscriber cuối không nhất thiết đi nguyên xi qua từng operator.
- Backpressure chỉ bảo đảm ở **những thành phần thực sự hỗ trợ/tuân thủ giao thức**. API callback nóng, hệ thống ngoài hoặc một producer có hàng đợi riêng không tự bị điều tiết chỉ vì phía Java nhận `Flux`.

**Trong HTTP thông thường không có một trường hay frame chuẩn có nghĩa “Reactive Streams request 10 object Java tiếp theo”.** Adapter HTTP có thể phối hợp demand với tốc độ đọc/ghi và khả năng tiêu thụ byte ở transport, nhưng quá trình đó là cơ chế nội bộ phụ thuộc server, client, codec và giao thức.

Ví dụ, downstream gọi `request(5)` trên `Flux<Order>`:

- Reactor có thể cấp quyền phát năm **Order** cho một đoạn pipeline.
- Codec chuyển năm object thành JSON, NDJSON hoặc sự kiện SSE; mỗi object có số byte khác nhau.
- Netty có thể xếp byte ra hàng đợi ghi; kernel có thể nhận byte vào socket buffer dù trình duyệt chưa render gì.
- TCP hoặc HTTP/2 có thể ngăn sender gửi thêm **byte** khi receiver hết cửa sổ nhận.
- Trình duyệt có thể đã nhận đủ byte nhưng JavaScript vẫn xử lý chậm.

Do đó, `request(5)` **không tương đương** với “client đã xử lý xong năm đơn hàng”. Cả việc gửi thành công tới socket cũng không đồng nghĩa dữ liệu đã được parse, hiển thị, lưu bền hoặc xác nhận nghiệp vụ ở phía khách.

## 2. Luồng dữ liệu xuyên HTTP đi qua những tầng nào?

```text
ỨNG DỤNG / REACTIVE STREAMS                      TRANSPORT / CLIENT
┌─────────────────┐
│ DB / message bus│  Có thể là nguồn có/không có cơ chế giảm tốc riêng
└────────┬────────┘
         │ event
         ▼
┌────────────────────────┐
│ Flux và các operators  │  request(n), queues, prefetch, drop/error
└────────┬───────────────┘
         ▼
┌────────────────────────┐
│ HTTP codec / DataBuffer│  biến phần tử thành byte, có thể gom/đệm
└────────┬───────────────┘
         ▼
┌────────────────────────┐
│ Netty outbound queue   │  writable / non-writable; watermarks
└────────┬───────────────┘
         ▼
┌────────────────────────┐
│ Kernel TCP send buffer │  nhận byte trước khi phía khách đọc ứng dụng
└────────┬───────────────┘
         │ TCP flow control / congestion; HTTP/2/3 nếu dùng
         ▼
┌────────────────────────┐
│ Reverse proxy / CDN    │  có thể buffer, nén, đóng/mở kết nối riêng
└────────┬───────────────┘
         ▼
┌────────────────────────┐
│ Client receive buffers │  kernel, HTTP client, decoder, event queue
└────────┬───────────────┘
         ▼
┌────────────────────────┐
│ Consumer / browser UI  │  callback, render, lưu dữ liệu, xử lý nghiệp vụ
└────────────────────────┘
```

Sơ đồ là **mô hình các ranh giới có thể có**, không khẳng định mọi triển khai có đầy đủ những hàng đợi riêng hay cùng một thứ tự copy dữ liệu. Với một reverse proxy, có **hai kết nối mạng khác nhau** và hai bộ điều tiết transport khác nhau. Một số codec/transport dùng pooling hoặc zero-copy, nhưng vẫn phải trả lời câu hỏi **bộ nhớ và tài nguyên được sở hữu/giới hạn bởi ai**.

Ở mỗi tầng có thể xảy ra một trong bốn hành động: **chậm lại**, **đợi/buffer có giới hạn**, **bỏ dữ liệu theo chính sách**, hoặc **báo lỗi/ngắt kết nối**. Không hệ thống nào được bảo đảm an toàn nếu mọi tầng đều chọn “đệm vô hạn”.

## 3. Bốn khái niệm backpressure dễ bị lẫn

| Tầng | Tín hiệu điều tiết | Đơn vị | Phạm vi và giới hạn |
|---|---|---|---|
| **Reactive Streams** | `request(n)` / `cancel()` | Số `onNext` | Chỉ trên quan hệ Publisher–Subscriber; operator có thể biến đổi request |
| **Netty / application transport** | Khả năng ghi, trạng thái `Channel.isWritable()`, write queue | Byte/buffer/khả năng ghi | Phụ thuộc channel, codec, watermarks và adapter; có thể vẫn đang giữ dữ liệu |
| **TCP** | Receive window, ACK và kiểm soát tắc nghẽn | Byte gửi/nhận trên kết nối | Receiver điều tiết tốc độ byte; không hiểu item, JSON hoặc trạng thái render |
| **HTTP/2** | `WINDOW_UPDATE` cho stream và connection | Byte của DATA frame | Flow control **theo từng hop**, độc lập với logic `request(n)`; HTTP/3 dùng cơ chế flow control của QUIC |

Thêm một tầng khác là **điều tiết nghiệp vụ**, chẳng hạn khách chỉ được nhận 100 thông báo/giây hoặc chỉ giữ snapshot mới nhất. Đây là quyết định application, không được suy ra từ TCP window hay `request(n)`.

### Đơn vị item và byte không thể đổi 1:1

Một `onNext` có thể là:

- Một object `Order` được mã hóa thành 200 byte.
- Một object có trường mô tả dài tạo 2 MB JSON.
- Một `DataBuffer` mang một chunk byte.
- Một list gồm 10.000 item nhưng chính nó chỉ là **một `onNext`**.

Vì vậy giới hạn “tối đa 100 phần tử” không tự bằng “tối đa 100 KB”. Nếu rủi ro chính là OOM, cần giới hạn **kích thước payload, tổng byte, số lượng kết nối và hàng đợi** ngoài giới hạn số item.

## 4. HTTP/1.1, HTTP/2 và HTTP/3 điều tiết khác nhau

### 4.1. HTTP/1.1 trên TCP

HTTP/1.1 không định nghĩa `Reactive Streams request(n)` trên đường truyền. Khi server stream response:

1. Ứng dụng phát dữ liệu; HTTP encoder tạo byte.
2. Netty/kernel cố gắng ghi dữ liệu vào socket.
3. Bên nhận công bố cửa sổ TCP cho biết còn bao nhiêu byte có thể tiếp nhận; mạng còn chịu cơ chế kiểm soát nghẽn.
4. Nếu client không nhận byte đủ nhanh, các buffer có thể đầy và cuối cùng phía ghi bị giới hạn/không thể tiến tiếp ngay.

Nhưng **server có thể ghi thành công vào kernel send buffer từ lâu trước khi consumer phía khách xử lý item**. Server nhìn thấy “write đã hoàn tất” cũng có thể chỉ có nghĩa một tầng thấp hơn đã nhận dữ liệu, không có nghĩa client application đã nhận và xác nhận.

HTTP/1.1 có thể truyền chunked response để đưa byte dần dần, nhưng chunk boundary **không đồng nghĩa** một item reactive hoặc một lần callback JavaScript. Proxy và codec có thể chia/gộp byte theo cách khác.

### 4.2. HTTP/2: flow control trên stream và connection

HTTP/2 định nghĩa `WINDOW_UPDATE` để người nhận cấp thêm quyền gửi **byte DATA frame**. Có hai cửa sổ:

- **Per-stream window**: giới hạn lượng DATA được phép gửi cho một HTTP/2 stream cụ thể.
- **Per-connection window**: giới hạn tổng DATA được phép gửi trên kết nối chứa nhiều stream.

Sender phải thỏa mãn **cả hai**. RFC 9113 quy định flow control theo **từng hop**; các proxy không chuyển tiếp nguyên vẹn một `WINDOW_UPDATE` từ client về origin như một `request(n)` xuyên suốt.

Ví dụ mô hình, không phải giá trị cấu hình mặc định của ứng dụng: một stream còn 8 KiB credit, connection còn 20 KiB credit. Nếu server muốn gửi 12 KiB DATA cho stream đó, không thể gửi vượt quá 8 KiB credit stream hiện có; nó cần chờ cập nhật window hoặc phát theo phần có thể gửi. Khi gửi xong, việc client parse JSON vẫn là tầng khác.

RFC 9113 đặt initial window 65.535 byte cho cả stream mới và connection, nhưng các endpoint có thể điều chỉnh theo cơ chế giao thức. **Không dùng số này làm suy luận về bộ nhớ thực tế của WebFlux**: còn codec, Netty buffers, socket buffers và proxy.

### 4.3. HTTP/3 / QUIC

HTTP/3 chạy trên QUIC. QUIC có cơ chế flow control riêng cho **stream** và **connection**, cũng điều tiết byte; nó không mang `request(n)` của Reactive Streams. Kiểu giới hạn và ánh xạ xuống API ứng dụng tùy transport và triển khai. Khi debug, cần xác định protocol thực sự được đàm phán; một URL `https://` không tự nói là HTTP/1.1, HTTP/2 hay HTTP/3.

**Kết luận ở ranh giới này:** transport có thể tạo hiệu ứng chậm lại lan truyền lên ứng dụng, nhưng **không có bảo đảm số item người dùng xử lý ở client được ánh xạ chính xác về demand của Publisher tại server**.

## 5. Netty write queue và watermarks không phải bộ đệm vô hạn

Reactor Netty là một transport non-blocking và backpressure-ready thường được dùng cho Spring WebFlux. Bên dưới, Netty quản lý khả năng ghi của `Channel`. `WriteBufferWaterMark` có **mức cao** và **mức thấp**:

- Khi số byte đang được xếp trong write buffer vượt high watermark, `Channel.isWritable()` có thể chuyển về `false`.
- Khi đã đi xuống dưới low watermark, channel có thể chuyển về `true`.
- Đây là **tín hiệu khả năng ghi**, không phải cam kết mọi byte vừa ghi đã tới trình duyệt hay là **hard cap** không thể vượt trên tổng bộ nhớ.

Các lớp có thể tham gia: outbound queue trong Netty, bộ nhớ direct/pooled `ByteBuf`, TLS buffers, kernel send buffer và proxy. Không nên chỉ nhìn Java heap để kết luận hệ thống không bị áp lực: direct memory và network buffers cũng có thể tăng.

**Phân biệt high/low watermark với memory limit:** Watermark thường giúp producer/transport biết nên tạm ngừng đưa thêm dữ liệu vào channel. Một lần ghi lớn, dữ liệu đã ở hàng đợi từ trước hoặc buffer ở tầng khác vẫn có thể sử dụng nhiều bộ nhớ. Hạn mức ứng dụng phải tính tổng những nơi có thể chứa byte, không chỉ một watermark.

Về mặt triển khai, mức độ và cách Reactor Netty truyền tín hiệu writable qua Reactive Streams phụ thuộc adapter/version và loại I/O. Không tự suy luận rằng bất kỳ phản hồi `Flux<T>` nào cũng có chuỗi điều tiết hoàn hảo, bằng nhau về đơn vị, từ browser trở về database.

## 6. Proxy, load balancer, CDN có thể phá giả định end-to-end

Một kiến trúc phổ biến:

```text
WebFlux server
  └── TCP/HTTP kết nối #1
            ▼
      Reverse proxy
      [response buffer]
            ▼
  └── TCP/HTTP kết nối #2
Browser / mobile app
```

Giả sử proxy nhận dữ liệu từ server rất nhanh nhưng gửi tới browser rất chậm. Khi còn đủ chỗ, proxy có thể tiếp tục đọc origin, khiến ứng dụng server chưa thấy áp lực nào từ browser. Chỉ khi proxy bị hạn chế bộ nhớ/đĩa/chính sách mới có thể giảm tốc origin hoặc đóng kết nối. Tùy cấu hình, proxy còn có thể:

- **Buffer toàn bộ hoặc một phần response**, làm việc stream từng event bị trễ.
- **Nén/batching** làm thay đổi thời điểm byte thực sự tới client.
- **Timeout** kết nối nhàn rỗi, giới hạn số kết nối đồng thời, giới hạn kích thước response.
- **Retry** yêu cầu trong một số điều kiện; với streaming hoặc side effect, retry phải theo hợp đồng idempotency.
- Chuyển đổi HTTP/2 từ phía client sang HTTP/1.1 phía origin, làm flow control ở hai hop không giống nhau.

Do đó, khi kiểm thử “slow browser”, cần biết liệu request có đi qua ingress, proxy, gateway, service mesh hoặc CDN. Chỉ kiểm tra trực tiếp vào localhost chưa đánh giá được toàn đường sản xuất.

### Ảnh hưởng tới SSE và NDJSON

- **SSE (`text/event-stream`)** có khung event để client xử lý liên tục; cấu hình proxy buffering sai có thể giữ nhiều event rồi mới flush.
- **NDJSON (`application/x-ndjson`)** cho phép các JSON object phân cách theo dòng, thích hợp stream nhiều item.
- **Một mảng JSON lớn (`application/json`)** có thể được mã hóa dần ở server trong một số cấu hình, nhưng một số codec/client parse theo tài liệu hoàn chỉnh và có thể gom nhiều dữ liệu trước khi ứng dụng nhìn thấy item.
- Streaming encoding không bảo đảm **mỗi item được flush và nhận độc lập tức thì**. Ranh giới chunk, TLS record, HTTP frame và sự kiện ở client có thể khác.

Việc chọn media type là một phần thiết kế streaming; nó không thay thế việc xác minh buffering từ server qua proxy đến client.

## 7. Phía khách đọc chậm: HTTP client chậm khác xử lý nghiệp vụ chậm

Một client có thể chậm tại nhiều vị trí:

| Vị trí chậm | Điều có thể thấy | Điều không thể suy ra |
|---|---|---|
| Đường mạng/client không đọc socket | TCP/QUIC flow control có thể hạn chế byte tiếp theo | Không biết publisher upstream bị dừng chính xác sau bao nhiêu item |
| HTTP client/decoder đọc socket nhưng parse chậm | Buffer trong thư viện và áp lực giải mã tăng | Không chắc server thấy client “chậm” ngay |
| Browser đã nhận event nhưng JS callback bận | Event queue, UI lag, memory của trang tăng | Không tự làm server nhận `request(0)` |
| Ứng dụng đã parse nhưng lưu DB cục bộ chậm | Hàng đợi công việc phía khách tăng | Không thể gọi TCP window là acknowledgment nghiệp vụ |
| Proxy đọc origin nhanh nhưng gửi browser chậm | Buffer bên proxy tăng | Server origin có thể tưởng downstream vẫn nhanh |

#### Browser EventSource

`EventSource` tạo kết nối SSE và dispatch event tới JavaScript. API này không cung cấp `Subscription.request(n)` để trang web yêu cầu “cho thêm ba sự kiện”. Callback JavaScript xử lý chậm **không phải cơ chế credit end-to-end**. Nếu số event quá nhiều, cần giới hạn tần suất, gửi **snapshot mới nhất** thay vì mọi thay đổi, hoặc có cơ chế application-level xác nhận/đồng bộ lại khi mất event.

#### Fetch / Streams API

Với `fetch()` và `ReadableStream`, JavaScript có thể đọc từng chunk qua `getReader().read()`. Điều này giúp chủ động điều khiển cách tiêu thụ trong client và có thể gián tiếp tạo áp lực lên các bộ đệm phía dưới. Tuy nhiên, một lần `read()` là thao tác trên stream byte/chunk của môi trường browser, **không tương ứng 1:1 với `Flux.request(1)` phía server**.

#### Reactive WebClient phía Java

Một `WebClient` có thể cung cấp `Flux<T>` cho body response. Một subscriber với demand hữu hạn có thể làm chậm quá trình đưa object đã giải mã vào downstream. Nhưng network connector và codec vẫn có thể giữ dữ liệu đệm và có chiến lược prefetch riêng; `limitRate(8)` không cam kết server chỉ gửi tám object hoặc chỉ có tám object trong tổng bộ nhớ của hai máy.

## 8. Incoming HTTP request: backpressure chiều client → server

Không chỉ response mới gặp vấn đề. Với upload hoặc request body streaming:

```text
Client producer → client HTTP encoder/socket
→ mạng/proxy → server HTTP decoder → Flux<DataBuffer> / Flux<T>
→ handler/service
```

Khi server xử lý request body chậm, transport có thể ngừng nhận thêm byte một thời gian nếu hỗ trợ điều tiết đọc. Nhưng nếu client/proxy đã gửi trước nhiều dữ liệu và mỗi tầng có buffer riêng, bộ nhớ vẫn có thể tăng. Hãy đặt giới hạn **kích thước request, kích thước phần tử, số request đồng thời, timeout, codec aggregation và tài nguyên downstream**.

Ví dụ WebFlux controller nhận NDJSON liên tục (snippet trong project Spring Boot WebFlux):

```java
@PostMapping(path = "/events",
        consumes = MediaType.APPLICATION_NDJSON_VALUE)
public Mono<Void> ingest(@RequestBody Flux<EventDto> events) {
    return events
            .concatMap(event -> reactiveService.save(event), 8)
            .then();
}
```

Đây là **mã minh họa chưa độc lập**: cần `EventDto`, `reactiveService`, imports và ứng dụng WebFlux. `reactiveService.save(event)` được giả định trả `Mono<?>` thực sự reactive/non-blocking. `concatMap(..., 8)` giữ thứ tự xử lý và dùng prefetch đã định; **không phải cap tổng số byte upload**. Cần limit request size/decoder, kiểm tra dữ liệu, timeout và bảo vệ DB riêng.

Nếu `save` gọi JDBC blocking, `concatMap` không tự biến nó thành non-blocking. Nếu client upload dữ liệu vô hạn và server chỉ parse vào `collectList()`, toàn bộ request có thể tích lũy vào bộ nhớ trước khi lưu. Không gom toàn bộ trừ khi thực sự cần và đã có giới hạn phù hợp.

## 9. Chương trình Java 17+ chạy được: demand chỉ bảo đảm ở pipeline Reactor

Ví dụ sau là **mô phỏng thuần Reactor Core**, không có HTTP. Nó cho thấy `request(n)` điều tiết số item trong một subscription và `cancel()` dừng producer. Sau khi nắm ranh giới này, cần nhớ **không thể suy từ kết quả chương trình rằng TCP/socket/browser cũng được điều tiết theo cùng n**.

Cấu trúc:

```text
reactor-demand-demo/
├── pom.xml
└── src/main/java/demo/DemandBoundaryDemo.java
```

Tệp `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>reactor-demand-demo</artifactId>
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
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.4.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Tệp `src/main/java/demo/DemandBoundaryDemo.java`:

```java
package demo;

import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

public class DemandBoundaryDemo {
    public static void main(String[] args) {
        Flux<Integer> source = Flux.range(1, 5)
                .doOnRequest(n ->
                        System.out.println("source request=" + n));

        BaseSubscriber<Integer> subscriber = new BaseSubscriber<>() {
            @Override
            protected void hookOnSubscribe(Subscription s) {
                System.out.println("subscribed");
                // Cố ý chưa request tại đây.
            }

            @Override
            protected void hookOnNext(Integer item) {
                System.out.println("item=" + item);
            }

            @Override
            protected void hookOnComplete() {
                System.out.println("completed");
            }

            @Override
            protected void hookOnCancel() {
                System.out.println("cancelled");
            }
        };

        source.subscribe(subscriber);

        System.out.println("request(2)");
        subscriber.request(2);

        System.out.println("request(1)");
        subscriber.request(1);

        System.out.println("cancel");
        subscriber.cancel();
    }
}
```

Chạy bằng JDK 17+ và Maven từ thư mục có `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.DemandBoundaryDemo
```

**Standard output của chương trình**, không tính thông báo từ Maven:

```text
subscribed
request(2)
source request=2
item=1
item=2
request(1)
source request=1
item=3
cancel
cancelled
```

Giải thích:

1. Đã subscribe nhưng `hookOnSubscribe` không request, nên chưa có `item`.
2. `request(2)` cho phép `Flux.range` phát 1 và 2. `doOnRequest` ghi nhận demand.
3. `request(1)` cho phép thêm item 3.
4. `cancel()` chấm dứt subscription trước khi item 4, 5 được gửi. Vì không có `onComplete`, callback `hookOnComplete` không chạy.
5. Mọi thao tác trong ví dụ là **đồng bộ trên thread đang request**, nên thứ tự output xác định, không phụ thuộc scheduler hay network.

**Giới hạn suy luận:** chương trình chứng minh hợp đồng Reactive Streams **trong một pipeline trong JVM**. Nếu thay `Flux.range` bằng dữ liệu từ WebClient, Kafka, browser hoặc một source nóng, phải khảo sát **từng adapter và hàng đợi**; không được lấy output này để tuyên bố client thật sự chỉ nhận đúng 3 item trên dây mạng.

## 10. Ví dụ Spring WebFlux: SSE cập nhật trạng thái cho khách chậm

Giả sử endpoint streaming số đo phục vụ dashboard. UI **chỉ cần trạng thái mới nhất**, không cần giữ mọi tick trung gian. Có thể dùng `onBackpressureLatest` gần source cập nhật để khi downstream không kịp tiêu thụ, ưu tiên giá trị mới gần nhất thay cho việc giữ mọi giá trị.

Đây là **class controller Java 17 hoàn chỉnh** về mặt cấu trúc trong project có `spring-boot-starter-webflux`; vẫn cần Spring Boot main class/server. Không dùng ví dụ làm nguồn sự kiện kiểm toán.

```java
import java.time.Duration;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
public class DashboardController {

    public record Snapshot(long tick) { }

    @GetMapping(path = "/dashboard/stream",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<Snapshot>> stream() {
        return Flux.interval(Duration.ofMillis(250))
                .onBackpressureLatest()
                .map(tick -> ServerSentEvent.<Snapshot>builder()
                        .id(Long.toString(tick))
                        .data(new Snapshot(tick))
                        .build())
                .doOnCancel(() ->
                        System.out.println("client subscription cancelled"));
    }
}
```

Luồng xử lý:

1. `Flux.interval` tạo các tick theo scheduler; nguồn không phải trình duyệt. Mỗi subscription có vòng đời riêng.
2. `onBackpressureLatest()` có thể **loại những tick trung gian** để giữ giá trị gần nhất cho downstream chậm, thay vì buffer vô hạn tại operator này. Nó không bảo đảm toàn đường HTTP không có buffer, không bảo đảm mọi tick đều tới khách.
3. `map` tạo SSE object có `id` và body `Snapshot`.
4. Spring WebFlux/HTTP adapter mã hóa và gửi SSE qua transport. Mỗi lớp phía sau còn điều tiết và đệm byte độc lập.
5. `doOnCancel` được gọi khi upstream subscription bị hủy. Đây là điểm quan sát hủy ở pipeline, **không phải bằng chứng client đã đọc xong mọi event**. Khi kết nối đứt, việc phát hiện hủy có thể trễ.

**Rất quan trọng về id SSE:** `id` trong ví dụ chỉ là số tick. Nó không đi kèm event store hoặc cơ chế replay cho `Last-Event-ID`. Nếu browser reconnect và đòi bù event đã mất, ứng dụng thật phải có nguồn lịch sử được lưu bền, sequence và cơ chế replay có ràng buộc. **Không nên dùng `onBackpressureLatest` cho thanh toán, audit log hoặc event cần đúng đủ một lần.**

### Kiểm thử truyền HTTP từ bên ngoài

Sau khi đã chạy ứng dụng có controller trên, có thể quan sát SSE:

```bash
curl -N -H "Accept: text/event-stream" http://localhost:8080/dashboard/stream
```

`-N` (no-buffer) tắt buffering đầu ra của chính `curl`, giúp nhìn dòng SSE ngay hơn. Nó **không tắt bộ đệm Netty, kernel hoặc reverse proxy**, và không bảo đảm mỗi event được gửi cùng một TCP packet.

Để tạo tình huống phía nhận tiêu thụ ít byte/giây trong môi trường kiểm thử, có thể thử:

```bash
curl -N --limit-rate 1k http://localhost:8080/dashboard/stream
```

`--limit-rate 1k` giới hạn tốc độ nhận của `curl` ở mức xấp xỉ 1 KiB/giây. Với event rất nhỏ, tốc độ này có thể vẫn nhanh hơn nguồn phát; **đây không phải kiểm thử chắc chắn khiến server bị backpressure**. Muốn thấy áp lực rõ, cần payload đủ lớn, tốc độ phát phù hợp và công cụ đo queue/socket, đồng thời kiểm tra đường proxy. Không dựa vào số dòng hiển thị ở terminal để kết luận lượng memory phía server.

### Không đánh đồng kết quả SSE với nhu cầu HTTP từ client

Một EventSource phía browser không gọi `request(n)`. Mã `onBackpressureLatest` hoạt động **ở nơi operator nhìn thấy demand giảm**; nếu HTTP adapter vẫn request đủ nhanh rồi đệm byte ở tầng sau, operator có thể không thấy client JavaScript chậm ngay. Vì vậy, việc thêm operator này chỉ là **một điểm kiểm soát**, không thể thay toàn bộ chiến lược giới hạn buffer và kết nối.

## 11. Ví dụ WebClient: giới hạn request upstream không phải giới hạn mạng

Đoạn này mô tả **client Java** nhận nhiều object NDJSON:

```java
Flux<EventDto> events = webClient.get()
        .uri("/events")
        .accept(MediaType.APPLICATION_NDJSON)
        .retrieve()
        .bodyToFlux(EventDto.class)
        .limitRate(16);
```

Đây là snippet cần `webClient`, `EventDto`, `MediaType`, `Flux` và HTTP server có NDJSON endpoint.

- `bodyToFlux(EventDto.class)` trả Publisher các item đã được decode từ response.
- `limitRate(16)` chia/chỉnh request của downstream gửi lên upstream trong **pipeline Reactor**. Cơ chế replenishment, prefetch và batching còn tùy operator.
- **Không có nghĩa** WebClient chỉ tải đúng 16 object qua socket, và cũng **không có nghĩa** mạng chưa nhận các byte của object thứ 17.
- Client codec có thể đã nhận buffer từ transport; một object lớn có thể chiếm nhiều byte, vượt xa số item 16.
- Nếu downstream gọi `collectList()`, bộ sưu tập vẫn có thể tăng tới toàn bộ response; `limitRate` không tự đặt giới hạn tổng phần tử được giữ trong list.

Nếu muốn chặn việc tải quá nhiều dữ liệu khi chỉ cần vài item, hãy làm rõ yêu cầu:

```java
Flux<EventDto> firstTen = events.take(10);
```

`take(10)` giới hạn item **downstream nhận** và có thể cancel upstream sau item thứ 10. Tuy nhiên một số byte đã được gửi/đệm trước đó có thể không thu hồi được, và server có thể đã thực hiện một phần công việc. Với dữ liệu trả phí/side effect, hãy dùng API server-side có limit rõ ràng thay vì tin client cancellation sẽ hoàn tác.

### Codec maxInMemorySize không phải tổng giới hạn bộ nhớ HTTP

Spring WebFlux/WebClient cung cấp cấu hình codec như:

```java
WebClient client = WebClient.builder()
        .codecs(configurer -> configurer
                .defaultCodecs()
                .maxInMemorySize(256 * 1024))
        .build();
```

Đây là snippet về cách cấu hình bộ nhớ aggregate của **một số thao tác decode/encode theo codec**. Khi vượt ngưỡng áp dụng, Spring có thể ném `DataBufferLimitException`. Nó **không đặt hard cap cho tổng Netty direct memory, TLS, kernel socket buffers, mọi pending response của nhiều connection hay tất cả list do ứng dụng tự gom**. Đừng tăng giới hạn codec để “chữa” một nguồn streaming không có giới hạn, khi nguyên nhân là logic tích lũy toàn bộ nội dung.

## 12. Producer nóng và nguồn không thể làm chậm

Không phải mọi nguồn tin vào `request(n)`. Một producer có thể tiếp tục phát bất kể subscriber demand:

- API listener/callback từ bên ngoài hoặc một thiết bị gửi dữ liệu liên tục.
- Kafka/message broker: adapter có thể pause/điều tiết poll trong một phạm vi, nhưng broker, topic và các consumer khác vẫn có tốc độ riêng.
- Price feed, websocket từ dịch vụ ngoài, timer nhanh hoặc luồng sự kiện toàn hệ thống.
- Client khác đã gửi dữ liệu đến ingress, được xếp ở proxy/broker trước khi service subscribe.

Khi nguồn không thể giảm tốc tương ứng, phải xác định **overflow policy**:

| Chiến lược | Tác dụng | Khi phù hợp | Rủi ro |
|---|---|---|---|
| **Buffer có giới hạn** | Giữ tạm tối đa N item hoặc giới hạn byte riêng | Burst ngắn; item quan trọng nhưng tốc độ trung bình cân bằng | Khi buffer đầy phải định nghĩa error/drop/reject |
| **Drop** | Bỏ item khi không thể tiếp nhận | Telemetry/trạng thái không cần tất cả event | Mất sự kiện, cần đo số drop |
| **Latest** | Giữ snapshot mới nhất, bỏ các snapshot cũ chưa dùng | Dashboard/giá trị cảm biến | Không bảo toàn lịch sử |
| **Error / overload response** | Fail fast khi quá tải | Dữ liệu yêu cầu độ chính xác | Client cần retry an toàn và idempotency |
| **Durable broker/queue** | Dời backlog sang hệ thống chuyên lưu bền | Event phải xử lý đủ, chịu burst dài | Độ trễ tăng, vẫn cần quota/retention/retry |
| **Giảm tốc producer thực sự** | Pause đọc/poll hoặc phản hồi flow control tới nguồn | Khi nguồn hỗ trợ | Không phải mọi nguồn hỗ trợ điều tiết đúng mức |

Các operator thường gặp:

```java
Flux<Metric> latestOnly = hotMetrics
        .onBackpressureLatest();

Flux<Metric> bounded = hotMetrics
        .onBackpressureBuffer(100);

Flux<Metric> dropped = hotMetrics
        .onBackpressureDrop();
```

Đây là snippet; cần `Flux<Metric> hotMetrics` và kiểu `Metric`. Ý nghĩa phải đọc cẩn thận:

- `onBackpressureLatest()` chỉ giữ **một phần tử đang chờ tại chính operator**; có thể bỏ item trung gian.
- `onBackpressureBuffer(100)` giới hạn **số phần tử trong queue do operator quản lý**; khi tràn có thể báo lỗi theo overload/chính sách sử dụng. Nó không giới hạn mọi queue khác.
- `onBackpressureDrop()` có thể bỏ item chưa có demand.
- Các toán tử này thường **không làm producer ngoài hệ thống giảm tốc** nếu nguồn phát nóng không hỗ trợ, và có thể thay đổi demand upstream để chủ động nhận và xử lý overflow.
- Nếu item là `DataBuffer`/`ByteBuf` có quản lý reference count, cần đặc biệt chú ý discard/release khi rơi vào nhánh drop/cancel. Đừng lấy các operator với default mà mặc định có cleanup chính xác cho mọi loại buffer.

**Một nguyên tắc nghiệp vụ:** Nếu không thể bỏ bất cứ event nào, `latest`/`drop` không phải chiến lược đúng. Cần durable queue/acknowledgment/cơ chế lưu bền và giới hạn backlog rõ ràng.

## 13. Bài toán định lượng: vì sao buffer tăng dù Flux có request(n)?

Giả sử một nguồn gửi 500 event/giây, client ứng dụng chỉ xử lý 100 event/giây. Nếu mỗi event chiếm **2 KiB sau mã hóa**, phần data tăng trong một buffer nhận tất cả sự kiện khoảng:

```text
Tốc độ đến:             500 event/s
Tốc độ tiêu thụ:         100 event/s
Phần dư:                 400 event/s
Kích thước trung bình:     2 KiB/event

Tăng phần dữ liệu: 400 × 2 KiB/s = 800 KiB/s
Sau 60 giây:     800 × 60 KiB  = 48.000 KiB ≈ 46,9 MiB
```

Đây là **mô hình một queue không drop và không giảm tốc upstream**. Bộ nhớ thực tế thường còn có object overhead, metadata, batch, compression, allocator và các queue khác; tính toán này **không phải benchmark** hay cam kết RAM dùng đúng 46,9 MiB.

Công thức kiểm tra nhanh:

```text
Nếu λ = tốc độ phát (item/giây), μ = tốc độ tiêu thụ,
B = byte trung bình/item và λ > μ:

tốc độ tăng backlog bytes ≈ (λ − μ) × B

Không giảm tốc, không drop, không lỗi:
backlog có thể tăng gần tuyến tính theo thời gian.
```

Nếu một buffer được giới hạn 10.000 item, độ chênh 400 item/s có thể lấp đầy nó sau khoảng 25 giây (bỏ qua lượng có sẵn), lúc đó **phải có chính sách tiếp theo**. Một giới hạn kích thước mà không có chính sách khi chạm ngưỡng chỉ dời thời điểm lỗi.

Ở hệ thống nhiều client: 1.000 client × 1 MiB pending trung bình có thể cần khoảng 1.000 MiB riêng cho phần pending đó, chưa tính phần còn lại. Vì vậy cần metric **per connection** và **tổng hệ thống**, không chỉ một buffer.

### Không dùng throughput duy nhất để đánh giá

Hai hệ thống cùng throughput 10.000 item/s có thể khác rất lớn về:

- Kích thước item/payload.
- Độ trễ client và phân bố client chậm.
- Số concurrent connections.
- Thời gian giữ buffer.
- Chi phí serialize/encode.
- Số phần tử in-flight trước các operator prefetch.
- Đường đi qua proxy/TLS/HTTP/2 multiplexing.

Dùng tải hỗn hợp (nhanh, chậm, ngắt kết nối) và đo memory/queue/latency mới thấy điểm nghẽn thực.

## 14. Khi nào điều tiết tới được upstream, khi nào dừng giữa đường?

### Trường hợp A — cùng JVM, nguồn Pull tuân thủ demand

`Flux.range`/`Flux.generate` có thể sinh theo `request(n)`. Khi downstream ngừng request, nguồn có thể dừng tính thêm item. Đây là trường hợp tương đối trực tiếp.

### Trường hợp B — reactive DB driver thật

Driver có thể đọc/giải mã theo demand và cơ chế protocol riêng, nhưng câu “R2DBC trả Flux” **không đảm bảo** database server lập tức dừng thực thi truy vấn khi browser dừng. Query, network buffers và cursor/prefetch của DB có hành vi riêng; cần đo và kiểm tra driver tương ứng.

### Trường hợp C — nguồn được đưa vào một hàng đợi có sẵn

`Flux.fromIterable(hugeList)` có thể tôn trọng demand khi phát, nhưng list khổng lồ **đã được cấp phát từ trước**. Backpressure bảo vệ nhịp `onNext` mà **không thu hồi** phần bộ nhớ do ứng dụng đã tích lũy trước khi tạo Flux.

### Trường hợp D — message broker hoặc hệ thống độc lập

Consumer có thể giảm tốc poll hoặc demand cục bộ; broker vẫn giữ backlog và producer khác vẫn xuất bản. Việc giảm tốc đã **chuyển chỗ backlog**, không chứng minh end-to-end memory/cost giảm nếu chưa giới hạn retention/quota.

### Trường hợp E — HTTP server + proxy buffer

WebFlux có thể gửi được nhiều byte cho proxy, rồi proxy tự giữ dữ liệu vì browser chậm. Server chỉ nhận thấy áp lực khi proxy giảm tốc đọc hoặc chạm giới hạn; `request(n)` từ client Java không vượt thẳng qua proxy như một tín hiệu thống nhất.

### Trường hợp F — browser event handler chậm

JavaScript callback làm việc lâu nhưng browser/network vẫn có thể đọc trước rồi xếp event. Server không có tín hiệu “client business logic đã xong”. Nếu cần chính xác, thêm **application-level ACK**, quota hoặc protocol riêng cho streaming. **ACK nghiệp vụ là giao thức do ứng dụng thiết kế**, khác với TCP ACK.

## 15. Kiểm thử backpressure xuyên HTTP có ý nghĩa

Muốn kết luận hệ thống chịu được slow client, hãy chạy thí nghiệm có thể quan sát:

1. **Chọn luồng thực**: SSE, NDJSON, file download hay upload? Ghi chính xác protocol (HTTP/1.1, HTTP/2 hoặc HTTP/3), proxy và cấu hình codec.
2. **Cố định sản lượng**: tốc độ item, kích thước trung bình/max, số concurrent clients, tỷ lệ khách chậm.
3. **Làm chậm có kiểm soát**: client giới hạn tốc độ đọc, đọc từng đợt, hoặc không đọc trong thời gian ngắn. Với HTTP/2, kiểm tra đồng thời nhiều stream trên một connection.
4. **Đo mọi tầng**: upstream request/demand, số pending item, queued bytes/netty writability, direct memory/heap, socket send/receive queues, proxy buffered bytes nếu có, client event queue/lag.
5. **Đo hệ quả**: thời gian tới event đầu/đến client, số event drop, số lỗi, độ trễ UI, callback cancellation, số connection và CPU.
6. **Thử các ngưỡng**: buffer đầy, client disconnect, proxy reset, timeout, mạng chập chờn, restart, reconnect và burst lớn.
7. **Xác nhận phục hồi**: sau khi client đọc bình thường trở lại, backlog có giảm? có giữ đúng dữ liệu yêu cầu? có giải phóng tài nguyên khi hủy?

### Những metric đáng theo dõi

Trong ứng dụng Reactor Netty có Micrometer/metrics được bật phù hợp, có thể xem nhóm metric như:

- `reactor.netty.http.server.connections.active`: số kết nối đang xử lý request.
- `reactor.netty.http.server.data.sent` / `reactor.netty.http.server.data.sent.time`: lưu lượng và thời gian gửi dữ liệu.
- `reactor.netty.http.server.response.time`: thời gian xử lý response ở server.
- `reactor.netty.bytebuf.allocator.used.direct.memory`: byte direct memory từ allocator được giám sát.
- Metric riêng: số subscription đang sống, queue size/bytes, số item bị drop, số timeouts và thời gian kể từ lần đọc/ghi thành công cuối.

Tên/khả dụng của metric phụ thuộc phiên bản và cấu hình. **Không coi `data.sent` là client application ACK**. Số byte sent đo một điểm trong pipeline server/transport; không xác nhận UI đã xử lý.

### Lỗi điển hình cần tìm

- `DataBufferLimitException`: codec đang phải giữ/aggregate nhiều dữ liệu hơn giới hạn áp dụng.
- OutOfMemoryError (heap/direct) hoặc leak reference-counted buffer.
- Write queue tăng, channel non-writable kéo dài, send latency tăng.
- Client socket/proxy buffer đầy, chậm hoặc timeout.
- `OverflowException`/lỗi thiếu demand hoặc tín hiệu `FAIL_OVERFLOW` từ sink.
- CPU cao do encoder, compression, xử lý callback hoặc quá nhiều connection.
- Subscription còn sống sau khi client rời đi, khiến producer tiếp tục tạo dữ liệu không ai cần.

Không kết luận chỉ từ một loại lỗi. Ví dụ, tăng `maxInMemorySize` có thể làm hết `DataBufferLimitException` ở một decoder nhưng khiến bộ nhớ tăng thêm; cần kiểm tra xem API có nên stream hay giới hạn payload.

## 16. Chọn chính sách theo loại dữ liệu

| Dữ liệu | Có được bỏ event? | Cách thiết kế hợp lý |
|---|---|---|
| Giá trị dashboard, vị trí con trỏ, số đo tức thời | Thường **có**, nếu trạng thái gần nhất đủ | Latest/coalesce/sample, giới hạn tần suất, hiển thị timestamp/stale |
| Video/audio theo thời gian thực | Có thể phải giảm chất lượng hoặc drop đúng chính sách | Rate adaptation, frame/buffer latency, transport chuyên dụng |
| SSE thông báo quan trọng | Tùy hợp đồng; nếu không được mất | Event ID bền vững, resume/replay, lịch sử có quota, backoff |
| Đơn hàng, thanh toán, audit log | **Không** được mất dữ liệu nghiệp vụ | Durable queue, ACK nghiệp vụ, idempotency, bounded retry, giám sát backlog |
| File download | Không được thiếu byte | Streaming với giới hạn throughput, kiểm tra checksum/range, timeout |
| File upload | Không được nhận vô hạn ngoài quota | Giới hạn kích thước/request, rate, quota, validate, cancel và cleanup |
| Search suggestion theo từng lần gõ | Có thể hủy kết quả cũ | `switchMap`/latest result phù hợp, debounce, cancellation; không cần lưu mọi request |

**Quyết định về mất dữ liệu là quyết định nghiệp vụ**, không phải một option hiệu năng có thể áp dụng chung cho mọi `Flux`.

## 17. Các nhầm lẫn phổ biến

1. **“Reactor backpressure bảo đảm browser đọc chậm thì database tự chậm theo.”** Không bảo đảm. Nhiều tầng codec/network/proxy/broker có buffer và giới hạn riêng.
2. **“`request(10)` nghĩa là HTTP gửi đúng 10 object JSON rồi dừng trên dây.”** Sai. Demand là số `onNext` ở ranh giới Publisher–Subscriber; transport gửi byte theo buffer và protocol.
3. **“TCP ACK nghĩa là user đã đọc event.”** Sai. TCP ACK nói về dữ liệu mạng đến tầng TCP, không xác nhận parse/render/lưu nghiệp vụ.
4. **“Server write thành công nghĩa là đã giao event tới callback JavaScript.”** Sai. Byte có thể đang ở kernel/proxy/client buffer.
5. **“HTTP/2 WINDOW_UPDATE là request(n) của Reactor.”** Sai. WINDOW_UPDATE cấp credit **byte DATA frame**, theo stream và connection, hop-by-hop.
6. **“Proxy nhận dữ liệu nhanh thì browser cũng nhanh.”** Sai. Proxy có thể đệm và gửi chậm ở kết nối khác.
7. **“`limitRate(16)` giới hạn tất cả memory chỉ còn 16 object.”** Sai. Nó điều chỉnh upstream demand tại một điểm; object lớn, operator khác, codec/socket buffer vẫn tồn tại.
8. **“`onBackpressureBuffer()` mặc định là cách làm an toàn.”** Nguy hiểm nếu không có giới hạn rõ ràng. Buffer vô hạn có thể gây OOM.
9. **“`onBackpressureLatest()` không bao giờ mất dữ liệu.”** Sai. Nó có thể bỏ các giá trị trung gian theo chủ đích; phải chấp nhận ngữ nghĩa đó.
10. **“SSE ID tự có replay khi reconnect.”** Sai. ID trong message không tạo durable event store; ứng dụng cần triển khai replay/resume nếu cần.
11. **“`maxInMemorySize` là giới hạn RAM tổng của WebClient.”** Sai. Đây là giới hạn cho những thao tác aggregate của codec, không phải quota mọi buffer.
12. **“Client hủy thì việc phía server/DB đã chắc chắn rollback.”** Sai. Cancellation là tín hiệu vòng đời; side effect và transaction có cơ chế riêng.
13. **“Non-blocking đồng nghĩa không có queue.”** Sai. Non-blocking dùng event-driven và vẫn có các buffer để hấp thụ burst, scheduling và network latency.
14. **“Mọi lần thử qua localhost đều đại diện hệ thống production.”** Sai. Reverse proxy, HTTP version, TLS, client khác và mạng chậm thay đổi điểm nghẽn.
15. **“Càng nhiều buffer càng an toàn.”** Sai. Buffer mua thêm thời gian trước khi quá tải; nếu nguồn lâu dài nhanh hơn tiêu thụ, backlog vẫn tăng tới ngưỡng.

## 18. Checklist review trước khi đưa streaming WebFlux vào production

- **Source:** có thể pause/throttle được không? Nếu không, drop, fail hay queue bền vững?
- **Reactive boundaries:** đã biết operator nào prefetch, buffer, retry hoặc làm mất demand backpressure?
- **Codec/payload:** item lớn nhất bao nhiêu byte? Có aggregate toàn bộ body không? Media type có streaming thực sự không?
- **Netty/socket:** quan sát được write queue, writability, heap/direct memory, số connection, timeout chưa?
- **Protocol:** traffic dùng HTTP/1.1, HTTP/2 hay HTTP/3? Có multiplexing và flow-control window tương ứng không?
- **Proxy/CDN:** có buffering, compression, rate limit, timeout, protocol translation? Đã test đường đi thật chưa?
- **Client:** ứng dụng phía khách tiêu thụ ở tốc độ nào? Có queue riêng, lưu bền, render và backpressure thật không?
- **Data policy:** được bỏ trạng thái trung gian hay phải giữ đầy đủ từng event? Có durable store, ACK và resume nếu cần?
- **Overflow:** giới hạn số item, số byte, thời gian, số client; khi đầy thì xử lý thế nào?
- **Cancel/reconnect:** đã giải phóng subscription/resource và xử lý reconnect mà không nhân bản side effect chưa?
- **Observability:** đo được slow-client, buffered bytes, drop, lag, completion, error và timeouts ở nhiều tầng?
- **Load test:** có khách chậm + nhanh đồng thời, burst, network/proxy delay, HTTP/2 streams và kiểm tra sau khi khách ngắt không?

**Ghi nhớ:** `request(n)` bảo vệ **một ranh giới Reactive Streams theo số phần tử**. HTTP, Netty, TCP/QUIC, proxy và browser điều tiết **byte, buffer và vòng đời theo những cơ chế khác nhau**. Backpressure có thể lan truyền thành việc producer chậm lại, nhưng không nên giả định **đảm bảo end-to-end** nếu chưa kiểm tra từng adapter, giới hạn bộ đệm và chính sách dữ liệu. Một hệ thống tốt là hệ thống biết **backlog xuất hiện ở đâu, bị giới hạn như thế nào, và điều gì xảy ra khi client không thể theo kịp**.

## Tài liệu tham khảo

- Reactive Streams — [JVM Specification: Publisher, Subscriber, Subscription và demand](https://www.reactive-streams.org/).
- Project Reactor — [Backpressure và cách operator thay đổi request](https://projectreactor.io/docs/core/release/reference/subscribe-backpressure.html).
- Project Reactor — [Sinks và overflow behavior](https://projectreactor.io/docs/core/release/reference/coreFeatures/sinks.html).
- Reactor Netty — [HTTP Server Reference: I/O, metrics, connection](https://projectreactor.io/docs/netty/release/reference/http-server.html).
- Netty — [WriteBufferWaterMark API](https://netty.io/4.2/api/io/netty/channel/WriteBufferWaterMark.html).
- IETF — [RFC 9113, HTTP/2 `5.2 Flow Control](https://www.rfc-editor.org/rfc/rfc9113.html#section-5.2).
- Spring Framework — [WebFlux Reactive Core](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html).
- Spring Framework — [WebClient codec configuration và maxInMemorySize](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html).

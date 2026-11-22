# Buffer, pooled data và trách nhiệm giải phóng dữ liệu ở API thấp

Trong RSocket, dữ liệu đi qua nhiều lớp: API Spring, abstraction DataBuffer, API Payload của RSocket và bộ đệm byte của Netty. Khi ứng dụng dùng RSocketRequester cùng Encoder/Decoder, phần lớn vòng đời bộ đệm được framework quản lý. Khi tự viết Decoder, xử lý trực tiếp Payload hoặc giữ dữ liệu qua một luồng bất đồng bộ, lập trình viên phải hiểu rõ ai đang sở hữu từng tham chiếu và lúc nào cần giải phóng nó.

Bài này tập trung vào Spring Framework 6.2/7.x, RSocket Java và Netty. Quy tắc tham chiếu đếm cũng áp dụng cho các phiên bản Spring có các API tương ứng.

## 1. Buffer nằm ở đâu trong RSocket?

Một thông điệp RSocket có phần data và phần metadata tùy chọn. Trong API Java mức thấp, đối tượng đại diện thông điệp là io.rsocket.Payload; data và metadata được cung cấp dưới dạng các buffer byte. RSocket Java được xây dựng trên Project Reactor và các transport TCP/WebSocket của nó thường dùng Reactor Netty.

Spring cung cấp hai mức API:

- RSocketRequester, @MessageMapping và @RSocketExchange làm việc với đối tượng Java. RSocketStrategies chọn Encoder/Decoder để chuyển đổi giữa đối tượng và dữ liệu trên dây.
- API RSocket mức thấp làm việc trực tiếp với io.rsocket.RSocket và io.rsocket.Payload. Ở mức này, ứng dụng có thể nhìn thấy buffer byte và phải quản lý vòng đời của đối tượng được reference-count.

Trong Spring, DataBuffer là abstraction đại diện cho vùng byte. DataBufferFactory tạo hoặc wrap buffer. Khi transport dùng Netty, factory thường là NettyDataBufferFactory và DataBuffer có thể được backed bởi Netty ByteBuf. Với factory khác, buffer có thể không pooled. Vì vậy, không được giả định rằng mọi DataBuffer đều có reference count.

## 2. Pooling và reference counting

Tạo mới một direct buffer có chi phí đáng kể. Direct memory có thể nằm ngoài Java heap và thường hữu ích cho I/O mạng vì giảm một số lần sao chép. Netty và các thư viện mạng có thể tái sử dụng vùng nhớ bằng pool thay vì liên tục cấp phát rồi chờ garbage collector thu hồi.

Pool cần biết chính xác khi nào buffer không còn được dùng. PooledDataBuffer của Spring bổ sung cơ chế reference counting:

1. Một pooled buffer mới được cấp phát với reference count bằng 1.
2. retain() tăng số tham chiếu thêm 1.
3. release() giảm số tham chiếu đi 1.
4. Khi số tham chiếu về 0, buffer được giải phóng hoặc trả vùng nhớ về pool.

Ví dụ, một buffer bắt đầu với count 1. Sau một lần retain(), count là 2. Lần release() đầu đưa count về 1 nên buffer vẫn còn sống; lần release() thứ hai đưa count về 0 và giải phóng buffer.

Điều này khác với vòng đời object Java thông thường. Garbage collector có thể thu hồi object wrapper khi không còn strong reference, nhưng nó không tự thay thế lời gọi release() của Netty. Nếu reference count vẫn lớn hơn 0, vùng nhớ pooled có thể không được trả lại đúng lúc. Vì vậy, heap có thể trông bình thường trong khi direct memory tăng dần.

DataBufferUtils là cách tiện dụng để quản lý buffer Spring mà không phải ép kiểu sang PooledDataBuffer:

- DataBufferUtils.retain(buffer) giữ thêm một tham chiếu nếu buffer hỗ trợ pooling.
- DataBufferUtils.release(buffer) giải phóng một tham chiếu nếu cần. API cũng xử lý CloseableDataBuffer.
- DataBufferUtils.touch(buffer, hint) gắn thông tin gợi ý cho leak tracking nếu implementation hỗ trợ.
- DataBufferUtils.releaseConsumer() trả về Consumer có thể dùng để giải phóng các buffer trong một luồng.

Giá trị boolean từ release() hoặc DataBufferUtils.release() cho biết buffer có được giải phóng ở lần gọi đó hay không. Giá trị false không tự động có nghĩa là lỗi: buffer có thể vẫn còn một tham chiếu khác, hoặc implementation không cần thao tác release.

## 3. Quy tắc ownership: ai dùng cuối cùng thì chịu trách nhiệm

Cần theo dõi ownership của từng tham chiếu, không chỉ ownership của biến Java.

- Khi code cấp phát một pooled buffer, code đó bắt đầu với một tham chiếu cần được giải phóng.
- Khi giữ buffer lâu hơn vòng đời hiện tại hoặc chia sẻ nó với một consumer độc lập, retain() tạo thêm một tham chiếu. Mỗi tham chiếu được retain phải có đúng một lần release tương ứng.
- Khi chuyển quyền sở hữu buffer cho component kế tiếp, component gửi thường không giải phóng tham chiếu đã chuyển. Component nhận chịu trách nhiệm sau khi dùng xong, trừ khi hợp đồng API quy định khác.
- Nếu chỉ đọc hoặc chuyển tiếp một view của buffer, cần biết view đó có dùng chung vùng nhớ và reference count với buffer gốc hay không.
- Đường đi thành công, exception, cancellation và discard đều phải có cách giải phóng rõ ràng.

Trong Netty, slice() và duplicate() thường tạo view chia sẻ vùng nhớ và reference count với buffer gốc; chúng không tự tăng count. Nếu một view phải sống lâu hơn buffer cha, cần retain() trước khi chuyển view sang component khác, hoặc tạo bản copy độc lập. copy() cấp phát vùng nhớ riêng và bản copy đó có vòng đời riêng.

Không release chỉ vì một phương thức đã kết thúc nếu buffer đã được chuyển cho consumer khác. Ngược lại, không giữ buffer trong cache, queue, callback hoặc lambda mà không ghi rõ nơi sẽ release. Hai lỗi phổ biến là leak do thiếu release và IllegalReferenceCountException do release thừa hoặc dùng buffer sau khi count đã về 0.

## 4. Quản lý DataBuffer trong Spring

### 4.1. Consumer đọc xong ngay

Khi một Decoder đọc hết buffer và chuyển dữ liệu thành object độc lập, Decoder nên giải phóng buffer trong finally để cả trường hợp thành công lẫn exception đều được xử lý.

~~~java
static String decodeUtf8(DataBuffer buffer) {
    try {
        byte[] bytes = new byte[buffer.readableByteCount()];
        buffer.read(bytes);
        return new String(bytes, StandardCharsets.UTF_8);
    }
    finally {
        DataBufferUtils.release(buffer);
    }
}
~~~

Đây là mẫu dành cho consumer đang sở hữu buffer đầu vào. Nếu buffer được chuyển tiếp cho một component khác, không release tại đây; ownership phải được chuyển cùng với buffer.

### 4.2. Giữ buffer qua ranh giới bất đồng bộ

Nếu công việc bất đồng bộ cần dùng buffer sau khi callback hiện tại kết thúc, phải retain thêm một tham chiếu cho công việc đó. Consumer hiện tại giải phóng tham chiếu ban đầu; công việc bất đồng bộ giải phóng tham chiếu đã retain sau khi hoàn tất. Cũng cần xử lý trường hợp executor từ chối nhận task.

~~~java
DataBuffer retained = DataBufferUtils.retain(buffer);
try {
    executor.execute(() -> {
        try {
            decodeAndStore(retained);
        }
        finally {
            DataBufferUtils.release(retained);
        }
    });
}
catch (java.util.concurrent.RejectedExecutionException ex) {
    // Executor từ chối nhận task: giải phóng tham chiếu đã retain.
    DataBufferUtils.release(retained);
    throw ex;
}
finally {
    // Consumer hiện tại giải phóng tham chiếu ban đầu.
    DataBufferUtils.release(buffer);
}
~~~

Đoạn code giả định executor không nhận task rồi âm thầm bỏ task. Nếu hàng đợi có chính sách loại bỏ task, chính nhánh loại bỏ cũng phải giải phóng tham chiếu mà task lẽ ra sẽ dùng. Với buffer không pooled, retain/release qua DataBufferUtils không làm thay đổi reference count nhưng vẫn có thể dùng cùng một mẫu code.

### 4.3. Reactor có thể discard buffer

Các operator như filter, skip, flatMap hoặc reduce có thể giữ, bỏ qua hoặc discard phần tử trong một số tình huống. Khi phần tử bị discard, map phía sau có thể không bao giờ nhận được buffer để giải phóng. Với các operator hỗ trợ discard hook, thêm doOnDiscard(DataBuffer.class, DataBufferUtils::release) vào chuỗi. Consumer vẫn phải release buffer mà nó thực sự xử lý.

~~~java
Flux<Command> commands = inboundBuffers
    .filter(this::isCandidate)
    .map(buffer -> {
        try {
            return decodeCommand(buffer);
        }
        finally {
            DataBufferUtils.release(buffer);
        }
    })
    .doOnDiscard(DataBuffer.class, DataBufferUtils::release);
~~~

Trong ví dụ, map giải phóng các buffer được chuyển tới nó; doOnDiscard xử lý buffer bị operator phía trước loại bỏ. Đặt hook ở phía downstream của những operator có khả năng discard để context của hook được truyền ngược lên upstream. Khi dùng các operator có prefetch hoặc cache, hãy kiểm tra operator đó có hỗ trợ discard hook và bảo đảm cả cancellation/error đều có cleanup.

### 4.4. Gom nhiều buffer

DataBufferUtils.join(source, maxByteCount) là cách an toàn để gom một Publisher<DataBuffer> thành một DataBuffer. Tùy implementation, kết quả có thể là composite buffer và không cần sao chép toàn bộ byte. Nếu upstream lỗi hoặc bị cancel trong lúc gom, các buffer đã tích lũy được giải phóng bởi join. Các buffer đầu vào không cần được release thêm lần nữa.

Buffer kết quả của join vẫn thuộc trách nhiệm của consumer. Sau khi decode xong, hãy release nó trong finally. Đặt giới hạn maxByteCount để tránh vô tình gom một payload không giới hạn vào bộ nhớ.

~~~java
Mono<Message> message = DataBufferUtils.join(inboundBuffers, 1_048_576)
    .map(buffer -> {
        try {
            return decodeMessage(buffer);
        }
        finally {
            DataBufferUtils.release(buffer);
        }
    });
~~~

### 4.5. InputStream và leak tracking

DataBuffer.asInputStream() mặc định không giải phóng buffer khi InputStream đóng. Nếu muốn việc đóng stream giải phóng buffer, dùng overload asInputStream(true) và không release cùng buffer thêm lần nữa ở nơi khác. Tương tự, DataBufferUtils.touch(buffer, "rsocket inbound decode") có thể thêm hint hữu ích khi điều tra leak trên implementation hỗ trợ tracking.

## 5. Quản lý Payload ở API RSocket mức thấp

Payload của RSocket chứa data và có thể có metadata. Trong RSocket Java, Payload là đối tượng reference-counted; các ByteBuf lấy từ Payload có thể chia sẻ vòng đời với Payload.

- Khi code sở hữu một Payload và đã đọc xong, release Payload đúng một lần.
- Không release riêng data() hoặc metadata() rồi lại release Payload nếu các view đó chia sẻ reference count. Việc đó có thể làm giảm count quá mức.
- data() và metadata() có thể trả về buffer gốc khi có thể; tài liệu RSocket khuyến nghị sliceData() và sliceMetadata() nếu cần view. Slice vẫn chia sẻ reference count, không tự tạo quyền sở hữu độc lập.
- Nếu cần giữ dữ liệu sau khi Payload bị release, phải retain đúng tham chiếu hoặc copy byte sang vùng nhớ độc lập.

### 5.1. Chuyển Payload thành DataBuffer

Spring cung cấp PayloadUtils.retainDataAndReleasePayload(payload, bufferFactory). Helper này slice phần data, retain và wrap nó thành DataBuffer, đồng thời release Payload. Metadata phải được đọc trước khi gọi helper. Sau đó, downstream chỉ cần làm việc với DataBuffer và phải release DataBuffer khi đọc xong.

~~~java
DataBuffer data = PayloadUtils.retainDataAndReleasePayload(payload, bufferFactory);
try {
    return decoder.decode(data);
}
finally {
    DataBufferUtils.release(data);
}
~~~

Đây là ví dụ decode đồng bộ. Nếu decoder trả về Mono hoặc Flux mà vẫn đọc DataBuffer sau khi phương thức hiện tại trả về, không được release trong finally ngay lập tức. Hãy gắn cleanup với thời điểm reactive work kết thúc, lỗi hoặc bị cancel; hoặc copy dữ liệu sang object độc lập trước khi trả publisher.

### 5.2. Tạo Payload từ DataBuffer

PayloadUtils.createPayload(data) và createPayload(data, metadata) tạo Payload từ DataBuffer. Nếu có NettyDataBuffer, helper có thể tạo ByteBufPayload bằng native ByteBuf hoặc wrapped ByteBuffer; nếu cả hai buffer là DefaultDataBuffer, helper tạo DefaultPayload. Điều này có nghĩa là không nên mặc định rằng việc chuyển đổi luôn tạo một bản copy độc lập. Hãy theo dõi ownership của buffer gốc và Payload theo đúng hợp đồng của phiên bản đang dùng, tránh giải phóng cùng một vùng nhớ qua hai đường sở hữu.

### 5.3. Khi nào không cần tự quản lý Payload?

Với RSocketRequester, @MessageMapping, @RSocketExchange và RSocketStrategies, ứng dụng thường trao đổi object Java và để Encoder/Decoder thực hiện chuyển đổi. Framework quản lý phần lớn vòng đời Payload và buffer trong pipeline của nó. Không tự gọi release cho Payload nội bộ mà framework đã nhận trách nhiệm. Việc quản lý thủ công thường chỉ xuất hiện khi viết custom Encoder/Decoder, can thiệp trực tiếp vào io.rsocket.RSocket, hoặc giữ buffer ngoài pipeline chuẩn.

## 6. Ví dụ Java 17: đọc và giải phóng Payload do ứng dụng tạo

Ví dụ sau tạo một Payload text, đọc nội dung rồi giải phóng Payload trong finally. Nó minh họa vòng đời của Payload do chính chương trình sở hữu; đây chưa phải một kết nối RSocket client/server.

Tạo project Maven với dependency và plugin sau:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>payload-release-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.rsocket</groupId>
            <artifactId>rsocket-core</artifactId>
            <version>1.1.5</version>
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
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tạo file src/main/java/example/PayloadReleaseDemo.java:

~~~java
package example;

import io.rsocket.Payload;
import io.rsocket.util.ByteBufPayload;

public class PayloadReleaseDemo {

    public static void main(String[] args) {
        Payload payload = ByteBufPayload.create("hello");

        try {
            System.out.println(payload.getDataUtf8());
        }
        finally {
            payload.release();
        }
    }
}
~~~

Chạy bằng Java 17 trở lên:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.PayloadReleaseDemo
~~~

Stdout chính xác:

~~~text
hello
~~~

Payload được tạo trong main nên chương trình sở hữu tham chiếu ban đầu và giải phóng nó sau lần đọc cuối. Nếu gọi retain() trước khi chuyển Payload cho một consumer độc lập, mỗi tham chiếu bổ sung phải được giải phóng đúng một lần. Không giữ Payload hoặc ByteBuf sau khi đã release.

### 6.1. Đối chiếu reference count bằng Spring DataBuffer

Đoạn sau là ví dụ minh họa API Spring khi factory dùng Netty pooled allocator. Cần có spring-core và Netty buffer tương thích trong project.

~~~java
NettyDataBufferFactory factory =
        new NettyDataBufferFactory(PooledByteBufAllocator.DEFAULT);

DataBuffer buffer = factory.allocateBuffer(16);
DataBufferUtils.retain(buffer);

System.out.println(DataBufferUtils.release(buffer));
System.out.println(DataBufferUtils.release(buffer));
~~~

Kết quả:

~~~text
false
true
~~~

Lần release đầu chỉ giảm count từ 2 xuống 1 nên buffer chưa được deallocate. Lần thứ hai đưa count về 0. Kết quả này chỉ đúng với buffer pooled trong ví dụ; với buffer không pooled, DataBufferUtils.release có thể trả về false vì không có thao tác deallocation cần thực hiện.

## 7. Lỗi thường gặp và cách điều tra

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| Direct memory tăng dần, xuất hiện log LEAK | Thiếu release trên một nhánh xử lý | Kiểm tra success, error, cancel, discard và queue bị loại bỏ |
| IllegalReferenceCountException | Dùng buffer sau khi count về 0 hoặc release thừa | Theo dõi nơi retain/release và các view slice/duplicate |
| Lỗi chỉ xuất hiện khi tải cao | Prefetch, buffering hoặc concurrency làm lộ đường discard | Kiểm tra doOnDiscard, giới hạn buffer và cancellation |
| Dữ liệu bị hỏng sau khi chuyển sang async | Buffer gốc đã được release trước khi consumer đọc xong | Retain trước khi handoff hoặc copy dữ liệu |
| Heap ổn định nhưng tiến trình hết native memory | Pooled/direct buffer chưa được trả về pool | Bật leak detection và rà soát ownership |

Khi chạy test hoặc điều tra leak với Netty, có thể bật ResourceLeakDetector ở mức ADVANCED hoặc PARANOID. Ví dụ cấu hình trong code:

~~~java
ResourceLeakDetector.setLevel(ResourceLeakDetector.Level.ADVANCED);
~~~

Có thể dùng DataBufferUtils.touch(buffer, "route=orders.stream") để thêm hint cho leak tracker. Leak detection có chi phí, vì vậy nên tăng mức chi tiết trong test hoặc khi điều tra có mục tiêu.

## 8. Checklist trước khi merge code xử lý buffer

- Xác định implementation của DataBuffer: pooled hay không pooled; Netty hay implementation khác.
- Ghi rõ ai cấp phát, ai nhận ownership, ai chuyển tiếp và ai release.
- Mỗi retain có một release tương ứng; không release một tham chiếu hai lần.
- Buffer bị discard, lỗi, cancellation hoặc task bị từ chối đều được cleanup.
- Không giả định slice/duplicate tạo reference count độc lập.
- Khi dùng DataBufferUtils.join, không release lại các buffer đầu vào; release buffer kết quả sau khi dùng.
- Khi dùng PayloadUtils.retainDataAndReleasePayload, đọc metadata trước và release DataBuffer kết quả sau khi dùng.
- Khi dùng RSocketRequester và codec chuẩn, để framework quản lý Payload nội bộ.
- Không giữ ByteBuf/DataBuffer trong cache hoặc callback sau khi đã release.

## Tài liệu tham khảo

- [Spring Framework — Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html)
- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework Javadoc — PayloadUtils](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/PayloadUtils.html)
- [Spring Framework Javadoc — DataBufferUtils](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html)
- [RSocket Java Javadoc — ByteBufPayload](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/util/ByteBufPayload.html)
- [Netty — Reference counted objects](https://netty.io/wiki/reference-counted-objects.html)

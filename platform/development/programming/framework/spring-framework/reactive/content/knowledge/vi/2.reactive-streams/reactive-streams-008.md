# Giới hạn bảo đảm của giao thức khi nguồn không thể giảm tốc

## 1. Bài toán: bên nhận chậm hơn nguồn phát

Giả sử một cảm biến gửi **1.000 sự kiện/giây**, nhưng ứng dụng chỉ xử lý được **100 sự kiện/giây**. Cảm biến được điều khiển bởi thiết bị bên ngoài và vẫn gửi dữ liệu dù ứng dụng yêu cầu ít hơn. Khi đó chênh lệch là **900 sự kiện/giây**; nếu giữ toàn bộ sự kiện trong bộ nhớ, hàng đợi tăng liên tục. Bộ đệm chứa tối đa 9.000 sự kiện sẽ đầy sau khoảng **10 giây** nếu tốc độ ổn định, ban đầu hàng đợi rỗng và không có giới hạn nào khác.

**Reactive Streams** có cơ chế **backpressure**: Subscriber báo cho Publisher số phần tử sẵn sàng nhận thông qua **Subscription.request(n)**. Nhưng tín hiệu này **không phải lệnh điều khiển vật lý** bắt mọi cảm biến, nguồn sự kiện bên ngoài, giao thức mạng hoặc hệ thống gửi dữ liệu phải giảm tốc.

Đây là ranh giới quan trọng nhất của chủ đề:

- **Giao thức Reactive Streams kiểm soát các tín hiệu chuyển từ Publisher đến Subscriber.**
- **Giao thức không bảo đảm nguồn dữ liệu gốc bên ngoài có khả năng tạm dừng, phát lại hoặc phát chậm hơn.**
- Nếu nguồn vẫn tạo dữ liệu nhanh hơn mức tiêu thụ, một thành phần trung gian phải chọn cách xử lý phần dư: **lưu đệm, loại bỏ, giữ bản mới nhất, chuyển sang nơi lưu bền vững, từ chối tải hoặc kết thúc với lỗi**. Mỗi lựa chọn đánh đổi tài nguyên, độ mới, độ đầy đủ và khả năng phục hồi.

Không nên hiểu “có backpressure” là “không bao giờ mất dữ liệu”, “không thể đầy hàng đợi” hoặc “tất cả thành phần ngoài hệ thống đều tự giảm tốc”.

## 2. Reactive Streams thực sự bảo đảm điều gì?

Mô hình Reactive Streams gồm **Publisher**, **Subscriber**, **Subscription** và **Processor** (vừa nhận, vừa phát). Subscriber nhận Subscription trong **onSubscribe**, sau đó phát tín hiệu nhu cầu bằng **request(n)**; Publisher có thể phát **onNext(value)** trong phạm vi nhu cầu đó rồi kết thúc bằng **onComplete** hoặc **onError**. Subscriber cũng có thể **cancel**.

Các ràng buộc giao thức quan trọng:

| Quy tắc | Ý nghĩa thực tế |
| --- | --- |
| **Giới hạn theo demand** | Publisher tuân thủ đặc tả **không phát nhiều tín hiệu onNext hơn tổng số phần tử đã được request** trên cùng Subscription. |
| **request(n) với n dương** | Yêu cầu thêm n phần tử; các lần yêu cầu được cộng dồn, không có nghĩa là nhận đúng n phần tử ngay lập tức. |
| **Nhu cầu chưa được cấp** | Khi chưa có demand, Publisher không được gửi onNext vượt mức yêu cầu; nó có thể chờ, giữ dữ liệu ở một tầng khác hoặc xử lý quá tải theo chính sách của nguồn/adapter. |
| **Tín hiệu cuối** | Một Subscription được kết thúc bởi **onComplete** hoặc **onError**, không phải cả hai; sau tín hiệu cuối không được gửi thêm onNext. Tín hiệu cuối không nhất thiết đòi hỏi request bổ sung. |
| **Tín hiệu tuần tự** | Các lời gọi tín hiệu đến Subscriber phải được tuần tự hóa theo quy tắc đặc tả, kể cả khi nguồn hoạt động trên nhiều luồng. |
| **Hủy** | cancel yêu cầu dừng đăng ký và giải phóng tài nguyên phù hợp; do cạnh tranh giữa các luồng, hủy không đồng nghĩa mọi thao tác đang bay lập tức biến mất. |

Trong ngữ cảnh này, **Publisher “không phát quá demand” là một nghĩa vụ giao thức tại giao diện Publisher–Subscriber**, không phải cam kết mọi thông tin do hệ thống bên ngoài tạo ra đều có đường đi đến Subscriber.

Ví dụ, Subscriber chỉ request(2). Một Publisher tuân thủ đặc tả được phát tối đa hai tín hiệu onNext cho đến khi có thêm request. Nếu adapter đã nhận năm sự kiện từ thiết bị thì ba sự kiện còn lại **không được đẩy thẳng thành onNext vượt demand**. Adapter phải làm gì với chúng phụ thuộc vào chính sách xử lý quá tải; Reactive Streams **không chọn sẵn chính sách ấy**.

**request(Long.MAX_VALUE)** thường được coi là yêu cầu không giới hạn từ phía Subscriber. Khi chủ động yêu cầu không giới hạn, bên nhận đã không dùng demand để giới hạn số phần tử; điều đó vẫn không khiến nguồn bên ngoài tự an toàn về bộ nhớ, tốc độ xử lý hoặc khả năng chịu lỗi.

## 3. Ranh giới giữa nguồn “push” và Publisher tuân thủ Reactive Streams

Hình dung một đường dữ liệu:

~~~text
Cảm biến / UDP / callback bên thứ ba / luồng sự kiện ngoài
           (có thể không hỗ trợ giảm tốc)
                          |
                          v
             Adapter tiếp nhận dữ liệu
           +---------------------------+
           | Bộ đệm và chính sách đầy  |
           | Giới hạn dung lượng       |
           | Drop / latest / error...  |
           +---------------------------+
                          |
                          v
            Publisher tuân thủ demand
                          |
                   Subscription
               request(n), cancel()
                          |
                          v
                      Subscriber
~~~

Adapter có thể nhận sự kiện bằng callback không phụ thuộc demand. Về mặt thiết kế, **callback từ nguồn bên ngoài** và **Subscriber.onNext** là hai biên khác nhau:

1. Nguồn ngoài phát bất cứ khi nào nó có dữ liệu.
2. Adapter đếm demand hiện có, giữ trạng thái hàng đợi và thực hiện chính sách quá tải.
3. Adapter chỉ gọi onNext ở phía downstream khi còn demand phù hợp.
4. Nếu dữ liệu dư không thể lưu hoặc hủy an toàn, adapter cần thông báo lỗi/kết thúc hay chuyển hướng sang tầng lưu trữ khác theo hợp đồng nghiệp vụ.

**Mâu thuẫn giữa tốc độ nguồn và tốc độ nhận được giải quyết tại ranh giới thích ứng**, không tự biến mất nhờ việc đổi kiểu dữ liệu thành Flux hoặc Mono.

Một số hệ thống có cơ chế điều khiển ngược thật sự, chẳng hạn giao thức có credit/flow-control, nguồn hỗ trợ pause/resume, consumer chủ động poll, hoặc hàng đợi có thể lưu backlog. Tuy nhiên, phải kiểm tra **từng connector/driver và toàn bộ đường đi**. Việc một tầng có backpressure không chứng minh tầng trước nó sẽ dừng phát.

## 4. Tại sao không thể bảo đảm “giữ tất cả + bộ nhớ hữu hạn” trong mọi trường hợp?

Ký hiệu:

- **R**: số sự kiện được tạo mỗi giây.
- **C**: số sự kiện được xử lý mỗi giây.
- **B**: số sự kiện tối đa có thể chờ trong bộ đệm.

Khi **R > C** liên tục và nguồn không nhận tín hiệu làm chậm, số phần tử chờ có xu hướng tăng khoảng **(R − C) × t** sau t giây, cho đến khi có chính sách can thiệp. Nếu tốc độ và kích thước sự kiện khác nhau theo thời gian, cần tính cả dao động, độ trễ xử lý, kích thước từng phần tử và lưu trữ phụ.

Với **R = 1.000/giây, C = 100/giây, B = 9.000 phần tử**, bộ đệm đầy sau khoảng B/(R − C) = **10 giây**. Tăng B lên gấp đôi chỉ kéo dài thời gian chịu đựng; không sửa được việc tốc độ tạo dữ liệu luôn lớn hơn tốc độ xử lý.

Nếu nguồn không thể giảm tốc, không thể đồng thời cam kết vô hạn thời gian rằng:

1. **Mọi sự kiện đều được giữ lại và giao đến đúng bên nhận**;
2. **Tổng bộ đệm/lưu trữ luôn hữu hạn**;
3. **Ứng dụng không được chặn, từ chối hoặc hạn chế đầu vào**;
4. **Tốc độ đầu vào luôn lớn hơn tốc độ tiêu thụ**.

Để giữ đầy đủ lâu dài, phải thay đổi ít nhất một giả thiết: tăng khả năng xử lý, giảm tốc nguồn, làm đầu vào bị chặn/từ chối, hoặc đưa dữ liệu ra một hệ thống lưu bền vững có sức chứa và chính sách giữ dữ liệu được quản lý. Ngay cả bộ nhớ đĩa hay message broker cũng có giới hạn về dung lượng, retention, throughput và lỗi.

Đây là **hạn chế vật lý/tài nguyên**, không phải lỗi triển khai riêng của Spring WebFlux, Reactor hoặc Reactive Streams.

## 5. Các chính sách xử lý khi không thể giảm tốc

Không có chính sách “tốt nhất” cho mọi loại dữ liệu. Cần xác định trước **mất một sự kiện có được chấp nhận hay không**, **sự kiện cũ còn giá trị không**, **có thể phát lại không**, và **độ trễ bao nhiêu là chấp nhận được**.

| Chính sách | Hành vi khi bên nhận chậm | Đánh đổi và trường hợp thích hợp |
| --- | --- | --- |
| **Bộ đệm hữu hạn** | Giữ tối đa B phần tử; khi đầy phải chọn hành động tiếp theo. | Chịu được burst ngắn, nhưng không giải quyết quá tải kéo dài; cần quan sát độ đầy. |
| **Drop newest** | Bỏ phần tử mới tới nếu không còn sức chứa/demand. | Giữ dữ liệu đang đợi; phù hợp nếu dữ liệu cũ quan trọng hơn dữ liệu mới. |
| **Drop oldest / latest** | Bỏ phần tử cũ để ưu tiên sự kiện mới hơn, hoặc chỉ giữ giá trị mới nhất chưa giao. | Có ích cho dashboard/trạng thái hiện hành; mất lịch sử và sự kiện trung gian. |
| **Sampling / aggregation** | Giảm số phần tử bằng lấy mẫu hoặc tổng hợp theo cửa sổ thời gian. | Hợp lý cho một số metric/telemetry; không bảo toàn mọi bản ghi gốc. |
| **Error / fail fast** | Phát onError và kết thúc luồng khi vượt giới hạn. | Không âm thầm mất dữ liệu; downstream cần chính sách retry/reconnect/recovery rõ ràng. |
| **Pause, pull, credit** | Làm tầng upstream chậm lại nếu nó thực sự hỗ trợ. | Có thể bảo toàn nhiều dữ liệu hơn tại biên này, nhưng backlog có thể chuyển sang tầng upstream. |
| **Lưu bền vững** | Ghi sự kiện vào log/broker/disk trước khi xử lý bất đồng bộ. | Tăng khả năng phục hồi nhưng thêm độ trễ, chi phí, vận hành và giới hạn retention/dung lượng. |

**Cảnh báo về “buffer không giới hạn”:** Bộ đệm không có trần có thể che giấu quá tải trong một thời gian rồi làm tăng mức sử dụng heap, áp lực GC và cuối cùng gây OutOfMemoryError. Việc bộ đệm không giới hạn *không* phải một bảo đảm giao nhận.

**Cảnh báo về “drop”:** Giao thức vẫn có thể hoàn toàn tuân thủ Reactive Streams khi adapter bỏ sự kiện trước khi phát chúng sang Subscriber. Nhưng **đặc tính nghiệp vụ đã thay đổi**: người dùng có thể chỉ thấy một phần dữ liệu. Việc đó phải là quyết định có chủ đích, có thống kê và được chấp nhận bởi miền nghiệp vụ.

**Cảnh báo về “error”:** Một tín hiệu onError kết thúc Subscription hiện tại. Nó không tự thực hiện retry, tự bảo toàn những sự kiện đã bị mất hoặc tự khôi phục upstream. Retry nếu có cần giới hạn, backoff và xác định idempotency để tránh lặp side effect.

## 6. Ví dụ Reactor: nguồn cứ phát, Subscriber chỉ yêu cầu hai phần tử

Ví dụ sau mô phỏng một **nguồn push không xét request**: producer cố đẩy liên tiếp năm số vào adapter. Adapter sử dụng **FluxSink.OverflowStrategy.DROP** để chỉ giao những phần tử phù hợp demand. Đây là **mô phỏng đồng bộ** nhằm làm rõ hợp đồng Reactive Streams; cảm biến thật có thể phát từ thread/thiết bị/giao thức khác.

Tạo dự án Maven Java 17+:

~~~text
reactive-overflow/
├── pom.xml
└── src/main/java/UnstoppableSourceDemo.java
~~~

Tệp **pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactive-overflow</artifactId>
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
                    <mainClass>UnstoppableSourceDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tệp **src/main/java/UnstoppableSourceDemo.java**:

~~~java
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;
import reactor.core.publisher.FluxSink;

public class UnstoppableSourceDemo {
    public static void main(String[] args) {
        Flux<Integer> source = Flux.create(sink -> {
            // Mô phỏng nguồn bên ngoài không nhìn vào demand.
            for (int i = 1; i <= 5; i++) {
                sink.next(i);
            }
            sink.complete();
        }, FluxSink.OverflowStrategy.DROP);

        source.subscribe(new BaseSubscriber<Integer>() {
            @Override
            protected void hookOnSubscribe(Subscription subscription) {
                System.out.println("Yêu cầu: 2");
                request(2);
            }

            @Override
            protected void hookOnNext(Integer value) {
                System.out.println("Nhận: " + value);
            }

            @Override
            protected void hookOnComplete() {
                System.out.println("Hoàn tất");
            }

            @Override
            protected void hookOnError(Throwable error) {
                System.out.println("Lỗi: " + error.getClass().getSimpleName());
            }
        });
    }
}
~~~

Chạy bằng JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java
~~~

Các dòng do chương trình in ra:

~~~text
Yêu cầu: 2
Nhận: 1
Nhận: 2
Hoàn tất
~~~

**Phân tích:**

1. **hookOnSubscribe** gửi request(2), tức downstream chỉ có hai đơn vị demand.
2. Producer chạy vòng lặp từ 1 đến 5 **bất kể demand** và gọi sink.next năm lần.
3. Adapter **DROP** giao 1 và 2; các giá trị 3, 4, 5 không được chuyển thành onNext vì đã hết demand.
4. Producer gọi sink.complete; Subscriber nhận **onComplete**. “Hoàn tất” nói rằng Publisher đã kết thúc, **không khẳng định downstream đã nhận đủ năm sự kiện gốc**.

Ví dụ này cố ý làm nổi bật khác biệt giữa **producer đã tạo năm sự kiện** và **Subscriber chỉ được giao hai sự kiện**. Đường **Publisher → Subscriber** vẫn tôn trọng demand. Những sự kiện bị bỏ ở adapter không được khôi phục tự động.

Nếu thay **DROP** bằng **ERROR**, việc phát vượt demand có thể dẫn đến tín hiệu lỗi ở adapter theo chính sách đó. Với **BUFFER**, các phần tử chưa được yêu cầu có thể nằm trong hàng đợi và chờ request tiếp; điều đó tăng mức dùng bộ nhớ và cần ràng buộc dung lượng. Với **LATEST**, các phần tử chưa giao có thể bị thay thế bởi phần tử mới nhất. Không nên đổi chiến lược chỉ để “hết lỗi”; phải kiểm tra chính xác hệ quả dữ liệu.

## 7. Những API Reactor liên quan và giới hạn của chúng

**Flux.create** và **Flux.push** thường được dùng khi cần thích ứng API callback/push thành Flux. Hai API này không biến API bên ngoài thành nguồn có khả năng pause; ứng dụng vẫn chịu trách nhiệm quản lý vòng đời đăng ký, hủy, lỗi, tài nguyên và chiến lược quá tải. **Flux.create** hỗ trợ các nguồn callback có thể phát từ nhiều luồng theo thiết kế của nó; **Flux.push** dành cho nguồn phát từ một luồng.

Một số operator và tùy chọn hữu ích:

| Công cụ | Điều làm được | Điều không bảo đảm |
| --- | --- | --- |
| **onBackpressureBuffer(...)** | Xếp hàng khi upstream nhanh hơn downstream; có biến thể giới hạn dung lượng và chính sách overflow. | Không tạo dung lượng vô hạn; bản không giới hạn có thể gây cạn bộ nhớ. |
| **onBackpressureDrop(...)** | Bỏ phần tử không được downstream tiếp nhận kịp; có thể gắn callback quan sát phần tử bị loại. | Không bảo toàn đầy đủ sự kiện. |
| **onBackpressureLatest()** | Giữ phần tử mới nhất đang chờ khi downstream chậm. | Không bảo toàn thứ tự đầy đủ/lịch sử trung gian. |
| **onBackpressureError()** | Báo lỗi khi demand không theo kịp ở ranh giới áp dụng. | Không tự lưu sự kiện để khôi phục sau lỗi. |
| **limitRate(n)** | Điều chỉnh cách operator yêu cầu các lô phần tử ở upstream tuân thủ demand. | Không ra lệnh cho thiết bị hoặc push API không nhận backpressure giảm tốc. |
| **publishOn(scheduler, prefetch)** | Chuyển ngữ cảnh thực thi với cơ chế request/bộ đệm riêng. | Không phải bộ tăng thông lượng miễn phí; buffer và độ trễ cần được đo. |

**Điểm dễ nhầm:** Một số operator xử lý sự kiện *sau khi đã được đưa vào một Publisher có chiến lược phát cụ thể*. Nếu tầng trước đó đã âm thầm bỏ dữ liệu, operator đặt phía sau **không thể phát hiện hay phục hồi** những sự kiện chưa từng tới nó. Cần đặt giám sát ở đúng tầng tiếp nhận nguồn ngoài.

Ngoài ra, các mô hình Reactor phổ biến thường là **cold Publisher**: producer chỉ chạy theo đăng ký, thậm chí có thể tự tuân thủ demand như Flux.range. Khi thử overflow bằng Flux.range, nguồn có thể dừng phát khi thiếu request, nên không tái hiện được bài toán của nguồn push thực sự. Để kiểm thử nguồn không thể giảm tốc, phải mô phỏng **tốc độ đến độc lập với request**.

## 8. Trường hợp thực tế: khi nào sự kiện có thể mất?

### Dashboard nhiệt độ, trạng thái tức thời

Nếu UI chỉ cần giá trị nhiệt độ **mới nhất**, việc bỏ một số giá trị giữa hai lần vẽ có thể hợp lý. Có thể dùng chính sách latest, sampling hoặc gom nhiều lần cập nhật thành một bản trạng thái. Tuy nhiên, nếu dữ liệu dùng để phát hiện vượt ngưỡng an toàn hoặc phân tích lịch sử, không thể mặc định bỏ các giá trị cực trị.

### Log kiểm toán, giao dịch, sự kiện có nghĩa vụ lưu trữ

Nếu **mỗi sự kiện đều quan trọng**, drop là sai về nghiệp vụ. Cần thiết kế ghi bền vững, xác nhận đã lưu, retry, idempotency, giám sát dung lượng và quy tắc khôi phục. Reactive Streams **không tự cung cấp** exactly-once, transaction, retention hay durable delivery. Các bảo đảm đó đến từ giao thức lưu trữ, broker, cơ sở dữ liệu và logic xử lý đã thiết kế.

### Message broker và hàng đợi

Việc consumer chậm có thể được giải quyết bằng cơ chế pause/poll, consumer lag, partition và retention. Tuy nhiên, backlog có thể chỉ chuyển sang **broker**, chứ không biến mất. Khi retention hết hoặc broker đầy, vẫn phải xử lý mất dữ liệu, từ chối ghi hoặc lỗi; không thể suy luận khả năng phát lại vô hạn từ việc có một adapter Flux.

### HTTP streaming, SSE, WebSocket

Spring WebFlux có thể dùng Flux cho phản hồi stream. **request(n)** bên trong Reactor là tín hiệu của Reactive Streams; một client SSE hoặc WebSocket bên ngoài không nhất thiết có cơ chế request(n) tương ứng qua mạng. TCP có flow control ở tầng transport, nhưng **không tương đương** chính sách bảo đảm mọi sự kiện nghiệp vụ được lưu và phát lại. Bộ đệm HTTP/TCP, tốc độ client và timeout vẫn phải được quản lý.

### Nguồn UDP hoặc thiết bị chỉ push

UDP không có cơ chế phản hồi điều khiển tốc độ hay phát lại tích hợp. Nếu ứng dụng nhận quá chậm, datagram có thể rơi tại socket/kernel **trước cả khi callback tạo Flux**. Backpressure của Subscriber không thể khôi phục datagram đã rơi ở tầng transport. Cần đo drop tại nhiều tầng và chọn giao thức lưu/điều khiển phù hợp nếu dữ liệu không được phép mất.

## 9. Tách ba loại “bảo đảm” khi thiết kế hệ thống

Một bản thiết kế tốt cần nói rõ ít nhất ba tầng:

1. **Bảo đảm giao thức Reactive Streams:** Subscriber không bị Publisher tuân thủ đặc tả gọi onNext vượt demand; tín hiệu kết thúc, hủy và tuần tự hóa theo hợp đồng.
2. **Bảo đảm của adapter/bộ đệm:** kích thước queue, khi nào drop, khi nào error, dữ liệu cũ/mới được ưu tiên, có hay không lưu bền vững, hủy thì giải phóng gì.
3. **Bảo đảm end-to-end của nghiệp vụ:** một sự kiện có được ghi nhận, xử lý đúng một lần theo yêu cầu nghiệp vụ, phát lại sau sự cố, bảo toàn thứ tự và chống trùng lặp hay không.

Ba loại bảo đảm này **không tự suy ra nhau**. Một Publisher có thể tuân thủ Reactive Streams tuyệt đối trong khi adapter upstream đã loại sự kiện; một queue có thể chưa đầy dù log nghiệp vụ bị mất tại network; một broker có persistence vẫn cần xử lý duplicate khi retry.

Các câu hỏi cần trả lời trước khi chọn chính sách:

- Nguồn ngoài có hỗ trợ **pause, pull, retry hoặc replay** không? Hỗ trợ ở tầng nào?
- Tốc độ trung bình, đỉnh burst, kích thước sự kiện và độ dài burst là bao nhiêu?
- Queue được phép dùng tối đa bao nhiêu bộ nhớ/disk? Khi đầy, **quy tắc nào là hợp lệ về nghiệp vụ**?
- Có cần bảo toàn **mọi sự kiện, thứ tự, thời gian xảy ra, hoặc chỉ trạng thái mới nhất**?
- Nếu downstream chậm/hủy/kết nối lại, dữ liệu pending xử lý thế nào?
- Ai xác nhận **đã nhận** và ai xác nhận **đã xử lý thành công**? Hai sự kiện này có thể khác nhau.
- Cơ chế giám sát có chỉ ra **drop trước adapter**, **drop tại adapter**, **drop sau adapter** và độ trễ end-to-end hay không?

## 10. Kiểm thử và quan sát quá tải

Không thể kết luận hệ thống an toàn chỉ bằng kiểm thử vài phần tử với Subscriber tiêu thụ ngay. Hãy chủ động mô phỏng **producer không xét demand** và **consumer chậm**.

Một bộ kiểm thử hữu ích gồm:

- **Demand bằng 0:** xác minh không có onNext vượt demand; quan sát buffer/drop/error thực tế.
- **Demand hữu hạn:** request(2), producer tạo nhiều hơn hai; xác minh số onNext, dấu vết drop và tín hiệu cuối theo chiến lược.
- **Burst và quá tải kéo dài:** mô phỏng R > C để kiểm tra queue có trần, giới hạn thời gian chịu tải và hành vi khi trần bị chạm.
- **Cancel, error, reconnect:** kiểm tra nguồn callback/Subscription có được gỡ đăng ký và giải phóng tài nguyên; dữ liệu dang dở có được xử lý đúng hợp đồng hay không.
- **Replay hoặc retry:** kiểm tra duplicate, mất thứ tự và idempotency khi có broker/lưu trữ bền vững.

Các chỉ số nên đo gồm tốc độ **received/accepted/delivered/dropped**, độ sâu queue hiện tại/cực đại, độ trễ end-to-end, số lỗi overflow, thời gian backlog giảm, mức dùng heap/GC, sự kiện hủy và độ trễ consumer. Với ứng dụng WebFlux cần bổ sung các chỉ số event loop, kết nối và buffer network nếu liên quan.

Một lỗi triển khai thường gặp là **chặn event loop** bằng Thread.sleep(), JDBC blocking hoặc block() khi xử lý request. Điều đó làm giảm tốc tiêu thụ và dễ khiến overflow nghiêm trọng hơn. Nếu buộc phải gọi API blocking, cần cô lập hợp lý bằng scheduler/tầng đồng bộ riêng và đo tải; scheduler không tạo ra bảo đảm dữ liệu vô hạn.

## 11. Lỗi hiểu sai và cách sửa

| Hiểu sai | Cách hiểu đúng |
| --- | --- |
| “Đã dùng Flux thì upstream sẽ tự giảm tốc.” | Chỉ upstream thực sự hỗ trợ điều tiết mới phản hồi demand tương ứng. |
| “request(10) là cam kết bên nhận sẽ được đủ 10 giá trị.” | Đó là mức cho phép phát tối đa 10 phần tử bổ sung; Publisher có thể hoàn tất sớm, báo lỗi hoặc không có dữ liệu. |
| “Subscriber nhận onComplete nên mọi sự kiện gốc đã tới.” | onComplete chỉ chốt stream nhìn từ Publisher; adapter có thể đã drop theo chính sách. |
| “Buffer lớn là xử lý xong backpressure.” | Buffer chỉ hấp thụ chênh lệch tạm thời; quá tải kéo dài sẽ chạm giới hạn. |
| “Backpressure luôn chống mất dữ liệu.” | Nhiều chính sách tuân thủ demand bằng cách drop hoặc error; losslessness là hợp đồng bổ sung. |
| “SSE/TCP/WebSocket mặc nhiên mang request(n) ra tận nguồn.” | Điều tiết Reactive Streams là cục bộ giữa các thành phần; các tầng transport/ứng dụng có cơ chế riêng. |
| “onBackpressureLatest phù hợp với mọi event.” | Chỉ phù hợp nếu bỏ qua sự kiện trung gian là hợp lệ; không dùng mặc định cho audit/giao dịch. |
| “Retry sau onError luôn phục hồi dữ liệu cũ.” | Retry có thể đăng ký lại nguồn nhưng cần nguồn hỗ trợ replay và logic chống lặp nếu muốn phục hồi đúng. |

## 12. Kết luận cần nhớ

**Reactive Streams bảo đảm việc phát onNext từ Publisher tuân thủ đặc tả không vượt lượng demand của Subscriber.** Nó cung cấp hợp đồng về subscription, yêu cầu, hủy và tín hiệu kết thúc. **Nó không bảo đảm nguồn vật lý hay API push bên ngoài sẽ chậm lại, không bảo đảm bộ nhớ vô hạn và không mặc định bảo đảm giao nhận đầy đủ.**

Khi **nguồn không thể giảm tốc**, cần đặt ranh giới thích ứng có giới hạn tài nguyên và chính sách rõ ràng: **buffer có trần, drop/latest/sampling nếu được phép, error/fail-fast, điều tiết upstream nếu hỗ trợ hoặc lưu trữ bền vững khi không được mất dữ liệu**. Chọn giải pháp dựa trên hợp đồng nghiệp vụ, kiểm thử producer nhanh hơn consumer và đo cả nơi dữ liệu có thể bị mất *trước khi* tới Publisher.